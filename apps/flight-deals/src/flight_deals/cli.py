"""Console entry point.

``flight-deals`` starts the web app and scheduler on 127.0.0.1 (``--background`` logs to
``flight-deals.log`` next to the database instead of the console). Subcommands:
``telegram-setup`` (find the chat id; no lock, no app, no database, writes no file) and
``autostart install|uninstall|status`` (per-user login autostart on Windows).
"""

from __future__ import annotations

import argparse
import getpass
import logging
import sys
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import uvicorn

import flight_deals.autostart as autostart
from flight_deals.app import (
    SchedulerLockHeldError,
    acquire_scheduler_lock,
    build_autostart_probe,
    build_telegram_setup_client,
    create_app,
    protect_secret,
)
from flight_deals.config import (
    BIND_HOST,
    DEFAULT_DB_PATH,
    DEFAULT_PORT,
    ENV_TELEGRAM_CHAT_ID,
    ENV_TELEGRAM_TOKEN,
    PROJECT_DIR,
    Config,
    ConfigError,
    load_config,
)
from flight_deals.logging_setup import LOG_FILE_NAME, setup_file_logging, setup_logging

log = logging.getLogger("flight_deals")

EXIT_OK = 0
EXIT_FAILED = 1
EXIT_CONFIG = 2
SETUP_WAIT_SECONDS = 60.0
SETUP_LONG_POLL_SECONDS = 10
SETUP_MIN_POLL_GAP_SECONDS = 1.0
# Unconfirmed updates come back at once on every call (offset is never sent).
SETUP_NONEMPTY_GAP_SECONDS = 2.0


def build_uvicorn_kwargs(port: int) -> dict[str, Any]:
    """Single process, no reload: a second worker would start a second scheduler."""
    return {
        "host": BIND_HOST,
        "port": port,
        "reload": False,
        "workers": 1,
        "log_config": None,
        "access_log": False,
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="flight-deals", description="機票低價監看器")
    parser.add_argument("--port", type=int, default=None, help="listen port (default 8795)")
    parser.add_argument("--debug", action="store_true", help="verbose logging")
    parser.add_argument(
        "--background",
        action="store_true",
        help=f"no console: log to {LOG_FILE_NAME} next to the database (login autostart)",
    )
    commands = parser.add_subparsers(dest="command", metavar="<command>")
    commands.add_parser("telegram-setup", help="find your Telegram chat id and send a test")
    auto = commands.add_parser("autostart", help="Windows login autostart (current user)")
    auto.add_argument("action", choices=("install", "uninstall", "status"))
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.command == "telegram-setup":
        return run_telegram_setup()
    if args.command == "autostart":
        return run_autostart(args.action)
    return serve(port=args.port, debug=args.debug, background=args.background)


# ---- service ----------------------------------------------------------------------


def serve(*, port: int | None, debug: bool, background: bool) -> int:
    level = logging.DEBUG if debug else logging.INFO
    if not background:
        setup_logging(level)
    try:
        config = load_config(production=True)
    except ConfigError as exc:
        if background:
            setup_file_logging(DEFAULT_DB_PATH.parent / LOG_FILE_NAME, level)
        log.error("configuration error: %s", exc)
        return EXIT_CONFIG
    if background:
        setup_file_logging(config.db_path.parent / LOG_FILE_NAME, level)
    try:
        return _serve(config, port or config.port)
    except Exception:
        # pythonw has no stderr: without this the traceback of e.g. a failed migration
        # would vanish. Logged through the redacting handler (file or stderr).
        log.exception("startup failed")
        return EXIT_FAILED


def _serve(config: Config, listen_port: int) -> int:
    # Before building the app (and migrating the DB): one scheduler per database.
    try:
        lock = acquire_scheduler_lock(config)
    except SchedulerLockHeldError as exc:
        log.error("refusing to start: %s", exc)
        return EXIT_CONFIG
    try:
        app = create_app(config, scheduler_lock=lock, autostart_probe=build_autostart_probe())
        log.info("flight-deals listening on http://%s:%d", BIND_HOST, listen_port)
        uvicorn.run(app, **build_uvicorn_kwargs(listen_port))
    finally:
        lock.release()
    return EXIT_OK


# ---- telegram-setup ---------------------------------------------------------------

BOTFATHER_STEPS = (
    f"尚未設定 bot token（{ENV_TELEGRAM_TOKEN}）。建立 bot 的步驟：",
    "  1. 在 Telegram 搜尋 @BotFather 並開啟對話",
    "  2. 傳送 /newbot，依指示設定名稱與帳號（帳號須以 bot 結尾）",
    "  3. BotFather 會回覆一串 token（格式像 123456789:ABC…）",
    f"  4. 把 {ENV_TELEGRAM_TOKEN}=<token> 寫進 apps/flight-deals/.env，或設成環境變數",
    "也可以在下方直接貼上 token（輸入時不會顯示，只用於這次設定，不會存檔）。",
)
NOT_INTERACTIVE_TEXT = f"未在互動終端機，無法輸入 token；請設定 {ENV_TELEGRAM_TOKEN} 後重試。"
TIMEOUT_LINES = (
    f"等候 {int(SETUP_WAIT_SECONDS)} 秒，沒有收到任何訊息。請確認：",
    "  1. 傳訊的對象是這個 token 對應的 bot（BotFather 建立的那一個）",
    "  2. 私人對話要先按「開始」（/start）；群組中須 @提及 bot，或在 BotFather 關閉隱私模式",
    "確認後再執行一次 flight-deals telegram-setup。",
)


def _print_out(text: str) -> None:
    print(text, flush=True)


def _print_err(text: str) -> None:
    print(text, file=sys.stderr, flush=True)


def _input(prompt: str) -> str:
    return input(prompt)


def _getpass(prompt: str) -> str:
    return getpass.getpass(prompt)


def _stdin_is_interactive() -> bool:
    """False for NUL / pipes / pythonw (no stdin): never block on a prompt then.

    On Windows ``getpass`` reads the console directly, so a redirected stdin alone would
    not stop it from waiting.
    """
    stream = sys.stdin
    if stream is None:
        return False
    try:
        return bool(stream.isatty())
    except (AttributeError, OSError, ValueError):
        return False


def _monotonic() -> float:
    return time.monotonic()


def _sleep(seconds: float) -> None:
    time.sleep(seconds)


@dataclass
class WizardIO:
    """Console and clock hooks (replaced in tests)."""

    out: Callable[[str], None] = field(default=_print_out)
    err: Callable[[str], None] = field(default=_print_err)
    ask: Callable[[str], str] = field(default=_input)
    ask_secret: Callable[[str], str] = field(default=_getpass)
    monotonic: Callable[[], float] = field(default=_monotonic)
    sleep: Callable[[float], None] = field(default=_sleep)
    interactive: Callable[[], bool] = field(default=_stdin_is_interactive)


def _ask(io: WizardIO, prompt: str, *, secret: bool = False) -> str:
    """Prompt the user; without an interactive terminal take the default (empty)."""
    if not io.interactive():
        return ""
    try:
        return (io.ask_secret if secret else io.ask)(prompt).strip()
    except EOFError:
        return ""


def _load_setup_config() -> Config:
    # Same env / .env rules as the service; source checks do not matter here.
    return load_config(production=False)


def run_telegram_setup(
    *,
    io: WizardIO | None = None,
    config_loader: Callable[[], Config] | None = None,
    client_factory: Callable[[str], Any] | None = None,
) -> int:
    """Find a chat id via ``getUpdates`` and optionally send a test message.

    Prints only; never writes files, takes the scheduler lock, builds the app, or opens
    the database, so it also works while the service is running. The token is never
    accepted from argv and never printed.
    """
    io = io or WizardIO()
    try:
        return _telegram_setup(
            io,
            config_loader or _load_setup_config,
            client_factory or build_telegram_setup_client,
        )
    except KeyboardInterrupt:
        io.err("已取消。")
        return EXIT_FAILED


def _telegram_setup(
    io: WizardIO, config_loader: Callable[[], Config], client_factory: Callable[[str], Any]
) -> int:
    setup_logging(logging.WARNING)
    try:
        token = config_loader().telegram_bot_token
    except ConfigError as exc:
        io.err(f"設定有誤：{exc}")
        return EXIT_CONFIG
    if not token:
        for line in BOTFATHER_STEPS:
            io.out(line)
        if not io.interactive():
            io.err(NOT_INTERACTIVE_TEXT)
            return EXIT_CONFIG
        token = _ask(io, "bot token（直接按 Enter 結束）：", secret=True)
        if not token:
            io.err(f"沒有 bot token，未連線 Telegram。設定 {ENV_TELEGRAM_TOKEN} 後再執行一次。")
            return EXIT_FAILED
    protect_secret(token)  # masked in every later log line or error text
    client = client_factory(token)
    io.out(f"請用 Telegram 對你的 bot 傳一則任意訊息，最多等候 {int(SETUP_WAIT_SECONDS)} 秒…")
    chats = _poll_for_chats(io, client)
    if chats is None:
        return EXIT_FAILED
    if not chats:
        for line in TIMEOUT_LINES:
            io.err(line)
        return EXIT_FAILED
    chosen = _choose_chat(io, chats)
    if chosen is None:
        return EXIT_FAILED
    io.out(f"找到聊天：{chosen.title}（{chosen.chat_type}）")
    io.out(f"chat id：{chosen.chat_id}")
    io.out("請把下面這一行加到 apps/flight-deals/.env（精靈不會修改任何檔案）：")
    io.out(f"{ENV_TELEGRAM_CHAT_ID}={chosen.chat_id}")
    answer = _ask(io, "要發送一則測試訊息到這個聊天嗎？輸入 y 發送，直接按 Enter 略過 [y/N]：")
    if answer.lower() not in ("y", "yes"):
        io.out("未發送測試訊息。")
        return EXIT_OK
    result = client.send_test(str(chosen.chat_id))
    if result.ok:
        io.out("測試訊息已送出，請到 Telegram 確認。")
        return EXIT_OK
    io.err(f"測試訊息送出失敗：{result.error or '未知錯誤'}")
    return EXIT_FAILED


def _poll_for_chats(io: WizardIO, client: Any) -> list[Any] | None:
    """Candidates newest first; [] on timeout; None after an API error (printed).

    The wizard never confirms updates (offset is always None, ADR-0002 FD-7 Decision 11),
    so commands the service has not handled yet are not swallowed.
    """
    deadline = io.monotonic() + SETUP_WAIT_SECONDS
    while True:
        remaining = deadline - io.monotonic()
        if remaining < 1:
            return []
        started = io.monotonic()
        result = client.get_updates(None, int(min(remaining, SETUP_LONG_POLL_SECONDS)))
        if not result.ok:
            io.err(result.error or "Telegram 回應錯誤")
            return None
        if result.chats:
            return sorted(result.chats, key=lambda c: c.update_id, reverse=True)
        if result.next_offset is not None:
            io.sleep(SETUP_NONEMPTY_GAP_SECONDS)
        elif io.monotonic() - started < SETUP_MIN_POLL_GAP_SECONDS:
            io.sleep(SETUP_MIN_POLL_GAP_SECONDS)


def _choose_chat(io: WizardIO, chats: list[Any]) -> Any | None:
    if len(chats) == 1:
        return chats[0]
    io.out(f"收到 {len(chats)} 個不同聊天的訊息：")
    for index, chat in enumerate(chats, start=1):
        newest = "（最新）" if index == 1 else ""
        io.out(f"  {index}. {chat.title}（{chat.chat_type}）chat id {chat.chat_id}{newest}")
    for _attempt in range(3):
        answer = _ask(io, f"選擇編號 1 到 {len(chats)}，直接按 Enter 選 1：")
        if not answer:
            return chats[0]
        if answer.isdigit() and 1 <= int(answer) <= len(chats):
            return chats[int(answer) - 1]
        io.err("編號不正確，請重新輸入。")
    io.err("沒有選到聊天，結束。")
    return None


# ---- autostart --------------------------------------------------------------------


def run_autostart(
    action: str,
    *,
    registry: autostart.Registry | None = None,
    project_dir: Path = PROJECT_DIR,
) -> int:
    try:
        reg = registry if registry is not None else autostart.WindowsRegistry()
    except autostart.AutostartUnavailableError:
        print("登入自動啟動只支援 Windows。", file=sys.stderr)
        return EXIT_CONFIG
    try:
        return _autostart(action, reg, project_dir)
    except OSError as exc:
        print(f"無法存取登入自動啟動設定：{exc}", file=sys.stderr)
        return EXIT_FAILED


def _autostart(action: str, registry: autostart.Registry, project_dir: Path) -> int:
    url = f"http://{BIND_HOST}:{DEFAULT_PORT}"
    if action == "install":
        outcome = autostart.install(project_dir, registry)
        if outcome == "missing_pythonw":
            print(
                f"找不到 {autostart.pythonw_path(project_dir)}。"
                "請先在 apps/flight-deals 執行 uv sync 建立虛擬環境，再重新安裝。",
                file=sys.stderr,
            )
            return EXIT_FAILED
        messages = {
            "created": "已安裝登入自動啟動：之後登入 Windows 時，flight-deals 會在背景啟動。",
            "replaced": "已覆寫既有的登入自動啟動設定（原本指向其他位置）。",
            "unchanged": "登入自動啟動已經安裝，設定相同，未變更。",
        }
        print(messages[outcome])
        print(f"背景執行時沒有視窗，網址 {url}；紀錄檔在資料庫同目錄的 {LOG_FILE_NAME}。")
        return EXIT_OK
    if action == "uninstall":
        if autostart.uninstall(registry) == "removed":
            print("已移除登入自動啟動。目前已在執行的服務不受影響，下次登入起不再自動啟動。")
        else:
            print("尚未安裝登入自動啟動，不需要移除。")
        return EXIT_OK
    state = autostart.status(project_dir, registry)
    if not state.registered:
        print("登入自動啟動：未安裝")
    elif state.points_here:
        print("登入自動啟動：已安裝（指向此專案）")
    else:
        print(f"登入自動啟動：已安裝，但指向其他位置：{state.command}")
    return EXIT_OK


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())

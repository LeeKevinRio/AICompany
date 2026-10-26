"""``flight-deals telegram-setup`` (FD-4 FR-SW, ADR-0002 Decision 7, C-35).

All Telegram traffic goes through ``httpx.MockTransport``; the real network stays blocked.
Every scenario checks that stdout, stderr and captured logs never contain the token.
"""

from __future__ import annotations

import builtins
import json
import logging
import re
from collections.abc import Callable, Iterator
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import httpx
import pytest

from flight_deals import cli
from flight_deals.app import build_telegram_setup_client
from flight_deals.config import Config
from flight_deals.storage import db as db_module

FAKE_TOKEN = "123456:FAKE-TOKEN"
BOT_URL = re.compile(r"bot\d+:")
Handler = Callable[[httpx.Request], httpx.Response]


@dataclass
class Console:
    """WizardIO backed by lists, a scripted keyboard and a fake monotonic clock."""

    answers: list[str] = field(default_factory=list)
    secret_answers: list[str] = field(default_factory=list)
    out: list[str] = field(default_factory=list)
    err: list[str] = field(default_factory=list)
    prompts: list[str] = field(default_factory=list)
    now: float = 1000.0
    slept: float = 0.0

    def io(self) -> cli.WizardIO:
        return cli.WizardIO(
            out=self.out.append,
            err=self.err.append,
            ask=self._ask,
            ask_secret=self._ask_secret,
            monotonic=lambda: self.now,
            sleep=self._sleep,
            interactive=lambda: True,
        )

    def _ask(self, prompt: str) -> str:
        self.prompts.append(prompt)
        if not self.answers:
            raise EOFError
        return self.answers.pop(0)

    def _ask_secret(self, prompt: str) -> str:
        self.prompts.append(prompt)
        return self.secret_answers.pop(0) if self.secret_answers else ""

    def _sleep(self, seconds: float) -> None:
        self.slept += seconds
        self.now += seconds

    @property
    def text(self) -> str:
        return "\n".join(self.out + self.err + self.prompts)


@dataclass
class FakeTelegram:
    handler: Handler
    requests: list[httpx.Request] = field(default_factory=list)

    def transport(self) -> httpx.MockTransport:
        def record(request: httpx.Request) -> httpx.Response:
            self.requests.append(request)
            return self.handler(request)

        return httpx.MockTransport(record)

    def factory(self, token: str) -> Any:
        return build_telegram_setup_client(token, transport=self.transport())


def updates(*chats: tuple[int, int, str, str]) -> dict[str, Any]:
    """(update_id, chat_id, type, title) tuples as a getUpdates body."""
    result = []
    for update_id, chat_id, chat_type, title in chats:
        chat: dict[str, Any] = {"id": chat_id, "type": chat_type}
        chat["title" if chat_type != "private" else "first_name"] = title
        result.append({"update_id": update_id, "message": {"message_id": 1, "chat": chat}})
    return {"ok": True, "result": result}


def config_with(token: str | None) -> Callable[[], Config]:
    return lambda: Config(telegram_bot_token=token)


@pytest.fixture(autouse=True)
def _forbid_lock_app_db_and_writes(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    """C-35: the wizard never takes the lock, builds the app, opens the DB or writes files."""

    def boom(*_args: Any, **_kwargs: Any) -> Any:
        raise AssertionError("telegram-setup must not call this")

    monkeypatch.setattr(cli, "acquire_scheduler_lock", boom)
    monkeypatch.setattr(cli, "create_app", boom)
    monkeypatch.setattr(db_module.Database, "__init__", boom)
    real_open = builtins.open

    def read_only_open(file: Any, mode: str = "r", *args: Any, **kwargs: Any) -> Any:
        if any(flag in mode for flag in "wax+"):
            raise AssertionError(f"telegram-setup must not write files: {file!r}")
        return real_open(file, mode, *args, **kwargs)

    monkeypatch.setattr(builtins, "open", read_only_open)
    yield


def run(
    console: Console,
    telegram: FakeTelegram | None,
    *,
    token: str | None = FAKE_TOKEN,
) -> int:
    factory = telegram.factory if telegram else None
    return cli.run_telegram_setup(
        io=console.io(), config_loader=config_with(token), client_factory=factory
    )


def assert_no_token(
    console: Console, capsys: pytest.CaptureFixture[str], caplog: pytest.LogCaptureFixture
) -> None:
    captured = capsys.readouterr()
    for text in (console.text, captured.out, captured.err, caplog.text):
        assert FAKE_TOKEN not in text
        assert "FAKE-TOKEN" not in text
        assert BOT_URL.search(text) is None, text


@pytest.fixture(autouse=True)
def _verbose_logs(caplog: pytest.LogCaptureFixture) -> None:
    caplog.set_level(logging.DEBUG)


def test_success_single_chat_prints_line_and_skips_test(
    capsys: pytest.CaptureFixture[str], caplog: pytest.LogCaptureFixture
) -> None:  # AC-SW2, AC-SW3 (answer no)
    telegram = FakeTelegram(
        lambda r: httpx.Response(200, json=updates((5, 556677, "private", "K")))
    )
    console = Console(answers=[""])
    assert run(console, telegram) == 0
    assert "FLIGHT_DEALS_TELEGRAM_CHAT_ID=556677" in console.out
    assert any("測試訊息" in p for p in console.prompts)
    assert [r.url.path.rsplit("/", 1)[-1] for r in telegram.requests] == ["getUpdates"]
    assert "未發送測試訊息。" in console.out
    assert_no_token(console, capsys, caplog)


def test_send_test_on_confirm(
    capsys: pytest.CaptureFixture[str], caplog: pytest.LogCaptureFixture
) -> None:  # AC-SW3
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/sendMessage"):
            assert json.loads(request.content)["chat_id"] == "556677"
            return httpx.Response(200, json={"ok": True, "result": {}})
        return httpx.Response(200, json=updates((5, 556677, "private", "K")))

    telegram = FakeTelegram(handler)
    console = Console(answers=["y"])
    assert run(console, telegram) == 0
    assert "測試訊息已送出，請到 Telegram 確認。" in console.out
    assert telegram.requests[-1].url.path.endswith("/sendMessage")
    assert_no_token(console, capsys, caplog)


def test_send_test_failure_reports_reason(
    capsys: pytest.CaptureFixture[str], caplog: pytest.LogCaptureFixture
) -> None:  # AC-SW4
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/sendMessage"):
            return httpx.Response(
                400, json={"ok": False, "description": "Bad Request: chat not found"}
            )
        return httpx.Response(200, json=updates((5, 556677, "private", "K")))

    console = Console(answers=["yes"])
    assert run(console, FakeTelegram(handler)) == 1
    assert any("chat not found" in line for line in console.err)
    assert_no_token(console, capsys, caplog)


def test_multiple_chats_listed_newest_default_and_negative_id(
    capsys: pytest.CaptureFixture[str], caplog: pytest.LogCaptureFixture
) -> None:  # AC-SW6
    body = updates((10, 556677, "private", "Kevin"), (11, -1001234567890, "supergroup", "家庭群"))
    console = Console(answers=["", ""])
    assert run(console, FakeTelegram(lambda r: httpx.Response(200, json=body))) == 0
    listing = "\n".join(console.out)
    assert "556677" in listing and "-1001234567890" in listing
    assert "FLIGHT_DEALS_TELEGRAM_CHAT_ID=-1001234567890" in console.out  # newest
    assert_no_token(console, capsys, caplog)


def test_multiple_chats_explicit_choice() -> None:
    body = updates((10, 556677, "private", "Kevin"), (11, -42, "group", "群"))
    console = Console(answers=["x", "2", ""])
    assert run(console, FakeTelegram(lambda r: httpx.Response(200, json=body))) == 0
    assert "FLIGHT_DEALS_TELEGRAM_CHAT_ID=556677" in console.out
    assert "編號不正確，請重新輸入。" in console.err


def test_timeout_after_60_seconds(
    capsys: pytest.CaptureFixture[str], caplog: pytest.LogCaptureFixture
) -> None:  # AC-SW5
    console = Console()
    polls: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        polls.append(request.url.params["timeout"])
        return httpx.Response(200, json={"ok": True, "result": []})

    assert run(console, FakeTelegram(handler)) == 1
    assert console.now - 1000.0 <= 61
    assert all(int(t) <= 10 for t in polls) and 0 < len(polls) <= 61
    assert any("沒有收到任何訊息" in line for line in console.err)
    assert_no_token(console, capsys, caplog)


@pytest.mark.parametrize(
    ("status", "needle"),
    [
        (401, "401 Unauthorized"),
        (409, "409 Conflict"),
        (500, "HTTP 500"),
    ],
)
def test_api_errors_explained_without_token(
    status: int,
    needle: str,
    capsys: pytest.CaptureFixture[str],
    caplog: pytest.LogCaptureFixture,
) -> None:  # FR-SW9, AC-SW7
    description = f"error for https://api.telegram.org/bot{FAKE_TOKEN}/getUpdates"
    telegram = FakeTelegram(
        lambda r: httpx.Response(status, json={"ok": False, "description": description})
    )
    console = Console()
    assert run(console, telegram) == 1
    assert any(needle in line for line in console.err)
    assert_no_token(console, capsys, caplog)


def test_network_exception_is_redacted(
    capsys: pytest.CaptureFixture[str], caplog: pytest.LogCaptureFixture
) -> None:  # AC-SW7
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError(f"All connection attempts failed for {request.url}")

    console = Console()
    assert run(console, FakeTelegram(handler)) == 1
    assert any("無法連線到 Telegram" in line for line in console.err)
    assert_no_token(console, capsys, caplog)


def test_unexpected_exception_is_contained() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise RuntimeError(f"weird {request.url}")

    console = Console()
    assert run(console, FakeTelegram(handler)) == 1
    assert FAKE_TOKEN not in console.text


def test_no_token_prints_botfather_steps_without_network(
    capsys: pytest.CaptureFixture[str], caplog: pytest.LogCaptureFixture
) -> None:  # AC-SW1
    telegram = FakeTelegram(lambda r: httpx.Response(200, json=updates()))
    console = Console(secret_answers=[""])
    assert run(console, telegram, token=None) == 1
    text = "\n".join(console.out)
    assert "@BotFather" in text and "/newbot" in text
    assert "FLIGHT_DEALS_TELEGRAM_BOT_TOKEN" in text
    assert telegram.requests == []
    assert_no_token(console, capsys, caplog)


def test_token_from_getpass_is_used_and_never_echoed(
    capsys: pytest.CaptureFixture[str], caplog: pytest.LogCaptureFixture
) -> None:
    telegram = FakeTelegram(lambda r: httpx.Response(401, json={"ok": False}))
    console = Console(secret_answers=[FAKE_TOKEN])
    assert run(console, telegram, token=None) == 1
    assert telegram.requests and FAKE_TOKEN in str(telegram.requests[0].url)
    assert_no_token(console, capsys, caplog)


def test_token_is_not_accepted_from_argv() -> None:
    with pytest.raises(SystemExit) as exc:
        cli.main(["telegram-setup", "--token", FAKE_TOKEN])
    assert exc.value.code == 2


def test_main_entry_uses_real_print_and_input(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    caplog: pytest.LogCaptureFixture,
) -> None:  # through ``flight-deals telegram-setup``
    telegram = FakeTelegram(
        lambda r: httpx.Response(200, json=updates((3, 778899, "private", "K")))
    )
    monkeypatch.setattr(cli, "_load_setup_config", config_with(FAKE_TOKEN))
    monkeypatch.setattr(cli, "build_telegram_setup_client", telegram.factory)
    monkeypatch.setattr(builtins, "input", lambda prompt="": "")
    monkeypatch.setattr("getpass.getpass", lambda prompt="": pytest.fail("token was set"))
    assert cli.main(["telegram-setup"]) == 0
    captured = capsys.readouterr()
    assert "FLIGHT_DEALS_TELEGRAM_CHAT_ID=778899" in captured.out
    for text in (captured.out, captured.err, caplog.text):
        assert FAKE_TOKEN not in text and BOT_URL.search(text) is None


def test_setup_leaves_project_files_untouched(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:  # AC-SW8
    monkeypatch.chdir(tmp_path)
    telegram = FakeTelegram(lambda r: httpx.Response(200, json=updates((3, 1, "private", "K"))))
    assert run(Console(answers=[""]), telegram) == 0
    assert list(tmp_path.iterdir()) == []


def test_get_updates_timeout_exceeds_long_poll() -> None:
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(200, json=updates())

    client = build_telegram_setup_client(FAKE_TOKEN, transport=httpx.MockTransport(handler))
    result = client.get_updates(17, 10)
    assert result.ok and result.chats == ()
    assert seen[0].url.params["offset"] == "17" and seen[0].url.params["timeout"] == "10"
    assert seen[0].extensions["timeout"]["read"] > 10


class _NoTty:
    def isatty(self) -> bool:
        return False


def test_no_token_without_terminal_exits_2_without_getpass(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    caplog: pytest.LogCaptureFixture,
) -> None:  # stdin redirected from NUL
    monkeypatch.setattr("sys.stdin", _NoTty())
    monkeypatch.setattr(cli, "_load_setup_config", config_with(None))
    monkeypatch.setattr("getpass.getpass", lambda prompt="": pytest.fail("getpass called"))
    monkeypatch.setattr(builtins, "input", lambda prompt="": pytest.fail("input called"))
    monkeypatch.setattr(
        cli, "build_telegram_setup_client", lambda token: pytest.fail("no network expected")
    )
    assert cli.main(["telegram-setup"]) == 2
    captured = capsys.readouterr()
    assert "@BotFather" in captured.out
    assert "未在互動終端機，無法輸入 token" in captured.err
    assert "FLIGHT_DEALS_TELEGRAM_BOT_TOKEN" in captured.err
    for text in (captured.out, captured.err, caplog.text):
        assert FAKE_TOKEN not in text and BOT_URL.search(text) is None


def test_prompts_take_defaults_without_terminal(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    caplog: pytest.LogCaptureFixture,
) -> None:
    body = updates((10, 556677, "private", "Kevin"), (11, -42, "group", "群"))
    telegram = FakeTelegram(lambda r: httpx.Response(200, json=body))
    monkeypatch.setattr("sys.stdin", _NoTty())
    monkeypatch.setattr(cli, "_load_setup_config", config_with(FAKE_TOKEN))
    monkeypatch.setattr(cli, "build_telegram_setup_client", telegram.factory)
    monkeypatch.setattr(builtins, "input", lambda prompt="": pytest.fail("input called"))
    assert cli.main(["telegram-setup"]) == 0
    captured = capsys.readouterr()
    assert "FLIGHT_DEALS_TELEGRAM_CHAT_ID=-42" in captured.out  # default: newest chat
    assert "未發送測試訊息。" in captured.out  # default: no test message
    assert all(not r.url.path.endswith("/sendMessage") for r in telegram.requests)
    for text in (captured.out, captured.err, caplog.text):
        assert FAKE_TOKEN not in text and BOT_URL.search(text) is None


def test_stdin_missing_counts_as_not_interactive(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("sys.stdin", None)
    assert cli._stdin_is_interactive() is False


def test_chat_title_strips_control_and_escape_characters() -> None:  # qa low
    body = updates((5, 556677, "group", "\x1b[31m紅\x00色\x7f群\u009b組\n"))
    console = Console(answers=[""])
    assert run(console, FakeTelegram(lambda r: httpx.Response(200, json=body))) == 0
    joined = "\n".join(console.out)
    assert "找到聊天：[31m紅色群組（group）" in joined  # single candidate still shown
    assert not any(ch in joined for ch in "\x1b\x00\x7f\u009b")


def test_token_registered_before_client_is_built(
    capsys: pytest.CaptureFixture[str], caplog: pytest.LogCaptureFixture
) -> None:  # qa low: masking must not depend on the factory
    from flight_deals.redact import redact

    seen: list[str] = []
    telegram = FakeTelegram(lambda r: httpx.Response(401, json={"ok": False}))

    def factory(token: str) -> Any:
        # Checked before build_telegram_setup_client registers it a second time.
        seen.append(redact(f"raw {token}"))
        return telegram.factory(token)

    console = Console()
    assert (
        cli.run_telegram_setup(
            io=console.io(), config_loader=config_with(FAKE_TOKEN), client_factory=factory
        )
        == 1
    )
    assert seen and FAKE_TOKEN not in seen[0]
    assert_no_token(console, capsys, caplog)

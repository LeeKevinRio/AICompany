"""Telegram two-way commands (ADR-0002 FD-7 Decisions 1-6, 11; C-49..C-51).

The poller is driven step by step through ``poll_once`` with a fake inbox and the fake
clock; replies go to the fake notifier. Nothing here talks to the network.
"""

from __future__ import annotations

import ast
import io
import logging
import re
import sqlite3
import threading
import time
from collections.abc import Callable, Iterator
from dataclasses import dataclass, field
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from typing import Any

import httpx
import pytest
from fastapi.testclient import TestClient

from flight_deals.app import Assembly, create_app
from flight_deals.config import Config
from flight_deals.domain.commands import MAX_COMMAND_CHARS, parse_command
from flight_deals.domain.messages import (
    BANNED_PHRASES,
    COMMAND_DIGEST_QUEUED,
    COMMAND_FAILED,
    COMMAND_HELP,
    COMMAND_NOT_TEXT,
    COMMAND_REPLY_MAX_CHARS,
    COMMAND_SCAN_DEFERRED,
    COMMAND_SCAN_EXPIRED,
    COMMAND_SCAN_PAUSED,
    COMMAND_SCAN_PENDING,
    COMMAND_SCHEDULER_OFF,
    COMMAND_TOO_LONG,
    COMMAND_UNKNOWN,
    DISCLAIMER,
    SAMPLED_ONLY_NOTE,
)
from flight_deals.domain.models import DatePair, ExplorationSpec
from flight_deals.logging_setup import setup_logging
from flight_deals.notify.telegram import MAX_MESSAGE_LENGTH, TelegramCommandClient
from flight_deals.ports import InboundUpdate, InboxResult
from flight_deals.services.commands import (
    OFFSET_BOT_KEY,
    OFFSET_KEY,
    CommandPoller,
    PollerStatus,
    PollerTiming,
)
from flight_deals.storage.repository import SourceHealthRecord
from tests.conftest import CLIENT_HEADERS, FakeClock, FakeLock, FakeNotifier, ScriptedSource

SRC = Path(__file__).resolve().parents[1] / "src" / "flight_deals"
FAKE_TOKEN = "123456:FAKE-TOKEN"
BOT_ID = "123456"
CHAT = 556677
OTHER_CHAT = 998877
BOT_URL = re.compile(r"bot\d+:")
NOW_UTC = datetime(2026, 10, 25, 4, 0, tzinfo=UTC)


# ---- fakes and harness -----------------------------------------------------------------


@dataclass
class FakeInbox:
    """Scripted ``TelegramInbox``: each call pops one result (or callable)."""

    batches: list[InboxResult | Callable[[], InboxResult]] = field(default_factory=list)
    calls: list[tuple[int | None, int]] = field(default_factory=list)

    def get_updates(self, offset: int | None, long_poll_seconds: int) -> InboxResult:
        self.calls.append((offset, long_poll_seconds))
        if not self.batches:
            return InboxResult(True, ())
        item = self.batches.pop(0)
        return item() if callable(item) else item


def msg(
    update_id: int,
    text: str | None,
    *,
    chat_id: int | None = CHAT,
    chat_type: str = "private",
    kind: str = "message",
    sent_at: datetime | None = None,
) -> InboundUpdate:
    return InboundUpdate(update_id, kind, chat_id, chat_type, text, sent_at)  # type: ignore[arg-type]


@dataclass
class Bot:
    assembly: Assembly
    client: TestClient
    clock: FakeClock
    source: ScriptedSource
    notifier: FakeNotifier
    inbox: FakeInbox
    scans: list[int] = field(default_factory=list)
    digests: list[tuple[int, str]] = field(default_factory=list)

    @property
    def services(self) -> Any:
        return self.assembly.services

    @property
    def repo(self) -> Any:
        return self.assembly.services.watches._repo

    @property
    def poller(self) -> CommandPoller:
        poller = self.assembly.commands.poller
        assert poller is not None
        return poller

    @property
    def commands(self) -> Any:
        return self.assembly.services.commands

    def create_watch(self, **overrides: Any) -> int:
        payload: dict[str, Any] = {
            "destination": "NRT",
            "trip_type": "round_trip",
            "date_mode": "fixed",
            "depart_date": "2026-12-10",
            "return_date": "2026-12-15",
            "budget": 12000,
        }
        payload.update(overrides)
        result = self.services.watches.create(payload)
        assert result.ok, result.errors
        return int(result.watch_id)

    def send(self, *updates: InboundUpdate) -> float:
        stamped = [
            u
            if u.sent_at is not None
            else InboundUpdate(u.update_id, u.kind, u.chat_id, u.chat_type, u.text, self.clock.now)
            for u in updates
        ]
        self.inbox.batches.append(InboxResult(True, tuple(stamped)))
        return self.poller.poll_once()

    def scheduler_on(self) -> None:
        """Pretend the scheduler runs; queued work is recorded instead of run."""
        hooks = self.commands.hooks
        hooks.scheduler_running = lambda: True
        hooks.schedule_scan = self.scans.append
        hooks.schedule_manual_digest = lambda update_id, key: self.digests.append((update_id, key))

    def notifications(self, kind: str | None = None) -> list[Any]:
        rows = self.repo.list_notifications(1000)
        return [r for r in rows if kind is None or r.kind == kind]


def bot_config(
    tmp_path: Path, *, chat_id: str | None = str(CHAT), token: str | None = FAKE_TOKEN
) -> Config:
    return Config(
        db_path=tmp_path / "cmd.db",
        sources=("google_flights",),
        telegram_bot_token=token,
        telegram_chat_id=chat_id,
    )


@pytest.fixture
def bot(
    tmp_path: Path, clock: FakeClock, source: ScriptedSource, notifier: FakeNotifier
) -> Iterator[Bot]:
    inbox = FakeInbox()
    app = create_app(
        bot_config(tmp_path),
        sources=[source],
        notifier=notifier,
        clock=clock,
        start_scheduler=False,
        inbox=inbox,
    )
    with TestClient(app, base_url="http://127.0.0.1") as client:
        yield Bot(app.state.assembly, client, clock, source, notifier, inbox)


def db_dump(bot: Bot) -> str:
    """Every value of every table, as one string (for "not stored anywhere" checks)."""
    conn = sqlite3.connect(bot.assembly.database.path)
    try:
        tables = [r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type = 'table'")]
        return "\n".join(
            repr(row) for table in tables for row in conn.execute(f"SELECT * FROM {table}")
        )
    finally:
        conn.close()


# ---- parse_command (C-51) --------------------------------------------------------------


@pytest.mark.parametrize(
    ("text", "status", "name", "watch_id"),
    [
        ("/list", "ok", "list", None),
        ("/LIST", "ok", "list", None),
        ("/list@mybot", "ok", "list", None),
        ("／ｌｉｓｔ", "ok", "list", None),
        ("  /help  ", "ok", "help", None),
        ("/start", "ok", "start", None),
        ("/watch", "missing_arg", "watch", None),
        ("/watch abc", "bad_arg", "watch", None),
        ("/watch 0", "bad_arg", "watch", None),
        ("/watch 1 2", "bad_arg", "watch", None),
        ("/watch -1", "bad_arg", "watch", None),
        ("/watch 1234567890", "bad_arg", "watch", None),
        ("/watch 12", "ok", "watch", 12),
        ("/Scan@my_bot 3", "ok", "scan", 3),
        ("/list extra", "bad_arg", "list", None),
        ("/add TPE NRT", "unknown", None, None),
        ("/edit 1", "unknown", None, None),
        ("/delete 1", "unknown", None, None),
        ("/set interval 5", "unknown", None, None),
        ("/foo", "unknown", None, None),
        ("你好", "not_command", None, None),
        ("list", "not_command", None, None),
    ],
)
def test_parse_command(text: str, status: str, name: str | None, watch_id: int | None) -> None:
    parsed = parse_command(text)
    assert (parsed.status, parsed.name, parsed.watch_id) == (status, name, watch_id)


def test_parse_command_too_long_and_non_text() -> None:
    parsed = parse_command("/list " + "x" * MAX_COMMAND_CHARS)
    assert parsed.status == "too_long" and len(parsed.text) == MAX_COMMAND_CHARS
    assert parse_command(None).status == "not_command"


def test_parse_command_is_stdlib_domain_code() -> None:
    import sys

    stdlib = set(sys.stdlib_module_names) | {"__future__"}
    tree = ast.parse((SRC / "domain" / "commands.py").read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module:
            assert node.module.split(".")[0] in stdlib | {"flight_deals"}
        elif isinstance(node, ast.Import):
            assert all(a.name.split(".")[0] in stdlib for a in node.names)


# ---- poller model (C-49) ----------------------------------------------------------------


def test_threads_only_in_commands_module_and_no_forbidden_imports() -> None:
    owners = [
        p.relative_to(SRC).as_posix()
        for p in SRC.rglob("*.py")
        if "threading.Thread(" in p.read_text(encoding="utf-8")
    ]
    # sources/_support.py predates FD-7: a per-call timeout thread for source calls.
    assert sorted(owners) == ["services/commands.py", "sources/_support.py"]
    tree = ast.parse((SRC / "services" / "commands.py").read_text(encoding="utf-8"))
    names = [n.module for n in ast.walk(tree) if isinstance(n, ast.ImportFrom) and n.module] + [
        a.name for n in ast.walk(tree) if isinstance(n, ast.Import) for a in n.names
    ]
    for name in names:
        assert not re.match(r"(flight_deals\.(scheduler|notify)|httpx)", name), name
    for path in SRC.rglob("*.py"):
        text = path.read_text(encoding="utf-8")
        if "api.telegram.org" in text:
            assert path.relative_to(SRC).as_posix() == "notify/telegram.py"


def test_no_poller_thread_without_scheduler_lock(bot: Bot) -> None:  # FR-P7
    assert bot.assembly.commands.poller is not None
    assert not bot.poller.started
    assert bot.inbox.calls == []


@pytest.mark.parametrize(
    ("token", "chat_id", "reason"),
    [
        (None, str(CHAT), "unconfigured"),
        (FAKE_TOKEN, None, "unconfigured"),
        (FAKE_TOKEN, "abc", "invalid_chat"),
        (FAKE_TOKEN, "-100123", "group_chat"),
    ],
)
def test_no_poller_without_token_or_private_chat(
    tmp_path: Path, token: str | None, chat_id: str | None, reason: str
) -> None:
    inbox = FakeInbox()
    app = create_app(
        bot_config(tmp_path, chat_id=chat_id, token=token),
        sources=[],
        notifier=FakeNotifier(),
        start_scheduler=True,
        scheduler_lock=FakeLock(),
        inbox=inbox,
    )
    with TestClient(app, base_url="http://127.0.0.1"):
        runtime = app.state.assembly.commands
        assert runtime.poller is None and runtime.unavailable == reason
        view = app.state.assembly.services.views.settings_page()["command_status"]
        assert view["state"] == "unconfigured"
        if reason == "group_chat":
            assert "不支援群組" in view["label"]
    assert inbox.calls == []


class BlockingInbox:
    def __init__(self) -> None:
        self.release = threading.Event()
        self.calls = 0

    def get_updates(self, offset: int | None, long_poll_seconds: int) -> InboxResult:
        self.calls += 1
        self.release.wait(5)
        time.sleep(0.01)
        return InboxResult(True, ())


def test_poller_runs_with_lock_and_does_not_block_jobs(tmp_path: Path) -> None:
    clock = FakeClock(datetime.now(UTC).replace(microsecond=0))
    inbox = BlockingInbox()
    app = create_app(
        bot_config(tmp_path),
        sources=[ScriptedSource(clock)],
        notifier=FakeNotifier(),
        clock=clock,
        start_scheduler=True,
        scheduler_lock=FakeLock(),
        inbox=inbox,
    )
    with TestClient(app, base_url="http://127.0.0.1"):
        assembly = app.state.assembly
        poller = assembly.commands.poller
        assert poller.started
        deadline = time.monotonic() + 5
        while inbox.calls == 0 and time.monotonic() < deadline:
            time.sleep(0.01)
        assert inbox.calls >= 1
        ran = threading.Event()
        assembly.scheduler.scheduler.add_job(ran.set)
        # The long poll is still blocked, yet the worker runs the job (C-49).
        assert ran.wait(5)
        assert not inbox.release.is_set()
        view = assembly.services.views.settings_page()["command_status"]
        assert view["state"] == "running" and view["label"] == "運作中"
        inbox.release.set()
    assert poller.stopped


def test_disabled_switch_sends_no_request(bot: Bot) -> None:  # AC-L4
    bot.services.settings.update({"telegram_commands_enabled": False})
    assert bot.poller.poll_once() == PollerTiming().disabled_wait_seconds
    assert bot.inbox.calls == []
    view = bot.services.views.settings_page()["command_status"]
    assert view["state"] == "stopped"  # not started in this harness (no scheduler lock)


def test_switch_off_during_poll_drops_batch_then_resumes(bot: Bot) -> None:  # AC-L4/L5
    watch_id = bot.create_watch()

    def turn_off_mid_poll() -> InboxResult:
        bot.services.settings.update({"telegram_commands_enabled": "0"})
        return InboxResult(True, (msg(10, f"/pause {watch_id}", sent_at=bot.clock.now),))

    bot.inbox.batches.append(turn_off_mid_poll)
    assert bot.poller.poll_once() == 0
    assert bot.notifier.sent == [] and bot.notifications("command") == []
    assert bot.repo.get_watch(watch_id).status == "active"
    assert bot.repo.get_state([OFFSET_KEY]) == {}
    # While off: no further request at all.
    assert bot.poller.poll_once() == PollerTiming().disabled_wait_seconds
    assert len(bot.inbox.calls) == 1
    bot.services.settings.update({"telegram_commands_enabled": "1"})
    assert bot.send(msg(10, f"/pause {watch_id}")) == 0
    assert bot.inbox.calls[-1][0] is None  # same offset as before: nothing was skipped
    assert bot.repo.get_watch(watch_id).status == "paused"


def test_backoff_grows_to_cap_and_resets(bot: Bot) -> None:  # C-49
    errors = [InboxResult(False, error="boom", error_kind="network")] * 10
    bot.inbox.batches.extend(errors)
    delays = [bot.poller.poll_once() for _ in range(10)]
    assert delays == [2, 4, 8, 16, 32, 64, 128, 256, 300, 300]
    assert bot.poller.status().failing
    view = bot.services.views.settings_page()["command_status"]
    assert view["last_error_label"] and "boom" in view["last_error_label"]
    assert bot.send() == 0
    assert not bot.poller.status().failing


def test_http_5xx_and_429_back_off(bot: Bot) -> None:
    bot.inbox.batches.append(InboxResult(False, error="HTTP 502", error_kind="http"))
    assert bot.poller.poll_once() == 2
    bot.inbox.batches.append(
        InboxResult(False, error="429", error_kind="rate_limited", retry_after_seconds=100)
    )
    assert bot.poller.poll_once() == 100  # retry_after is a floor
    bot.inbox.batches.append(
        InboxResult(False, error="429", error_kind="rate_limited", retry_after_seconds=1)
    )
    assert bot.poller.poll_once() == 8


def test_conflict_waits_60_and_unauthorized_stops(bot: Bot) -> None:
    bot.inbox.batches.append(InboxResult(False, error="409", error_kind="conflict"))
    assert bot.poller.poll_once() == 60
    bot.inbox.batches.append(InboxResult(False, error="401", error_kind="unauthorized"))
    assert bot.poller.poll_once() < 0
    calls = len(bot.inbox.calls)
    assert bot.poller.poll_once() < 0
    assert len(bot.inbox.calls) == calls  # stopped: no more requests
    assert bot.poller.status().unauthorized


def test_inbox_exception_is_contained(bot: Bot) -> None:
    def explode() -> InboxResult:
        raise RuntimeError("unexpected")

    bot.inbox.batches.append(explode)
    assert bot.poller.poll_once() == 2
    assert "RuntimeError" in (bot.poller.status().last_error or "")


def test_no_db_writes_after_stop(bot: Bot) -> None:  # C-49
    bot.create_watch()
    before = db_dump(bot)
    bot.poller.stop()
    bot.inbox.batches.append(InboxResult(True, (msg(1, "/list", sent_at=bot.clock.now),)))
    assert bot.poller.poll_once() < 0
    assert bot.inbox.calls == []
    assert db_dump(bot) == before and bot.notifier.sent == []


def test_stop_during_poll_discards_batch(bot: Bot) -> None:
    def stop_mid_poll() -> InboxResult:
        threading.Thread(target=bot.poller.stop).start()
        time.sleep(0.05)
        return InboxResult(True, (msg(1, "/list", sent_at=bot.clock.now),))

    bot.inbox.batches.append(stop_mid_poll)
    assert bot.poller.poll_once() < 0
    assert bot.notifier.sent == [] and bot.notifications() == []


# ---- authorisation, replay, backlog, redaction (C-50) -----------------------------------


def test_unauthorised_sources_are_ignored_silently(
    bot: Bot, caplog: pytest.LogCaptureFixture
) -> None:  # AC-P2, AC-P3
    caplog.set_level(logging.DEBUG)
    watch_id = bot.create_watch()
    secret_texts = ["/list", f"/pause {watch_id}", "陌生人的悄悄話 xyzzy"]
    updates = [
        msg(1, secret_texts[0], chat_id=OTHER_CHAT),
        msg(2, secret_texts[1], chat_id=OTHER_CHAT),
        msg(3, secret_texts[2], chat_id=OTHER_CHAT),
        msg(4, f"/pause {watch_id}", chat_id=CHAT, chat_type="group"),
        msg(5, f"/pause {watch_id}", chat_id=-100200300, chat_type="supergroup"),
        msg(6, f"/pause {watch_id}", kind="edited_message"),
        msg(7, None, chat_id=OTHER_CHAT),  # a sticker from a stranger
        msg(8, None, kind="other", chat_id=None),
    ]
    assert bot.send(*updates) == 0
    assert bot.notifier.sent == [] and bot.notifier.attempts == 0
    assert bot.notifications() == []
    assert bot.repo.get_watch(watch_id).status == "active"
    # The owner's own edited message (update 6) is skipped but is not "unauthorised".
    assert bot.poller.status().ignored_count == len(updates) - 1
    dump = db_dump(bot)
    for text in ("xyzzy", "陌生人", str(OTHER_CHAT)):
        assert text not in caplog.text and text not in dump
    assert bot.repo.get_state([OFFSET_KEY])[OFFSET_KEY] == "9"
    view = bot.services.views.settings_page()["command_status"]
    assert view["ignored_count"] == len(updates) - 1


def test_authorised_non_text_gets_short_note(bot: Bot) -> None:  # AC-P3
    bot.send(msg(1, None))
    assert bot.notifier.sent == [COMMAND_NOT_TEXT]


def test_same_update_runs_once_even_without_stored_offset(bot: Bot) -> None:  # AC-P4
    bot.scheduler_on()
    bot.send(msg(41, "/digest"))
    bot.repo.save_state({OFFSET_KEY: "0", OFFSET_BOT_KEY: "999"}, bot.clock.now)  # lost
    restarted = make_poller(bot)
    bot.inbox.batches.append(InboxResult(True, (msg(41, "/digest", sent_at=bot.clock.now),)))
    assert restarted.poll_once() == 0
    assert bot.inbox.calls[-1][0] is None  # other bot id: offset starts over
    assert len(bot.digests) == 1 and len(bot.notifier.sent) == 1


def make_poller(bot: Bot) -> CommandPoller:
    return CommandPoller(
        bot.inbox,
        bot.commands,
        bot.services.notifications,
        bot.repo,
        bot.services.settings,
        bot_id=BOT_ID,
        chat_id=CHAT,
        clock=bot.clock,
        redactor=lambda text: str(text),
    )


def test_crash_after_claim_before_offset_never_reruns(
    bot: Bot, monkeypatch: pytest.MonkeyPatch
) -> None:  # C-50
    bot.scheduler_on()
    watch_id = bot.create_watch()
    poller = bot.poller

    def lost(_next: int) -> None:
        raise sqlite3.OperationalError("database is locked")

    monkeypatch.setattr(poller, "_save_offset", lost)
    assert bot.send(msg(7, f"/scan {watch_id}")) > 0  # backoff, not an exception
    assert bot.scans == [watch_id]
    restarted = make_poller(bot)
    bot.inbox.batches.append(
        InboxResult(True, (msg(7, f"/scan {watch_id}", sent_at=bot.clock.now),))
    )
    assert restarted.poll_once() == 0
    assert bot.scans == [watch_id] and len(bot.notifier.sent) == 1
    assert bot.repo.get_state([OFFSET_KEY])[OFFSET_KEY] == "8"


def test_offset_is_stored_per_bot(bot: Bot) -> None:
    bot.send(msg(100, "/help"))
    state = bot.repo.get_state([OFFSET_KEY, OFFSET_BOT_KEY])
    assert state == {OFFSET_KEY: "101", OFFSET_BOT_KEY: BOT_ID}
    restarted = make_poller(bot)
    restarted.poll_once()
    assert bot.inbox.calls[-1][0] == 101


def test_backlog_older_than_ten_minutes_is_not_run(bot: Bot) -> None:  # AC-P5
    watch_id = bot.create_watch()
    now = bot.clock.now
    bot.send(
        msg(1, f"/pause {watch_id}", sent_at=now - timedelta(minutes=20)),
        msg(2, f"/pause {watch_id}", sent_at=now - timedelta(minutes=11)),
        msg(3, "/help", sent_at=now - timedelta(minutes=1)),
    )
    assert bot.repo.get_watch(watch_id).status == "active"
    assert bot.notifier.sent == [
        COMMAND_HELP,
        "有 2 則指令超過 10 分鐘才收到（可能因服務停機、網路中斷或指令功能關閉），"
        "已略過、未執行，請重新傳送。",
    ]
    keys = {r.dedupe_key for r in bot.notifications("command")}
    assert f"cmd-backlog:{BOT_ID}:2" in keys


def test_no_backlog_note_when_everything_is_recent(bot: Bot) -> None:
    now = bot.clock.now
    bot.send(msg(1, "/help", sent_at=now - timedelta(minutes=9)), msg(2, "/help"))
    assert bot.notifier.sent == [COMMAND_HELP, COMMAND_HELP]


def test_command_client_requests_small_batches_of_messages() -> None:  # C-50
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        body = {
            "ok": True,
            "result": [
                {
                    "update_id": 9,
                    "message": {
                        "date": 1_790_000_000,
                        "chat": {"id": 1, "type": "private"},
                        "text": "/list",
                    },
                },
                {
                    "update_id": 8,
                    "edited_message": {"chat": {"id": 1, "type": "private"}, "text": "x"},
                },
                {"update_id": 7, "callback_query": {}},
                {"nope": 1},
            ],
        }
        return httpx.Response(200, json=body)

    client = TelegramCommandClient(FAKE_TOKEN, transport=httpx.MockTransport(handler))
    result = client.get_updates(55, 25)
    params = seen[0].url.params
    assert params["limit"] == "20" and params["offset"] == "55" and params["timeout"] == "25"
    assert params["allowed_updates"] == '["message", "edited_message"]'
    assert [u.update_id for u in result.updates] == [7, 8, 9]
    assert [u.kind for u in result.updates] == ["other", "edited_message", "message"]
    assert result.updates[2].sent_at == datetime.fromtimestamp(1_790_000_000, UTC)


def _raise(exc: Exception) -> Callable[[httpx.Request], httpx.Response]:
    def handler(_request: httpx.Request) -> httpx.Response:
        raise exc

    return handler


URL_WITH_TOKEN = f"https://api.telegram.org/bot{FAKE_TOKEN}/getUpdates"


@pytest.mark.parametrize(
    "handler",
    [
        lambda r: httpx.Response(401, json={"ok": False, "description": URL_WITH_TOKEN}),
        lambda r: httpx.Response(409, json={"ok": False, "description": URL_WITH_TOKEN}),
        lambda r: httpx.Response(500, json={"ok": False, "description": URL_WITH_TOKEN}),
        _raise(httpx.ConnectError(f"cannot reach {URL_WITH_TOKEN}")),
        _raise(httpx.ReadTimeout(f"timed out {URL_WITH_TOKEN}")),
        _raise(ValueError(f"odd {URL_WITH_TOKEN}")),
    ],
    ids=["401", "409", "500", "network", "timeout", "unexpected"],
)
def test_token_never_leaks_from_polling_errors(
    tmp_path: Path,
    handler: Callable[[httpx.Request], httpx.Response],
    capsys: pytest.CaptureFixture[str],
    caplog: pytest.LogCaptureFixture,
) -> None:  # AC-P9, C-50
    caplog.set_level(logging.DEBUG)
    # Production logging (cli.main): redacting handler, httpx request lines quieted.
    stream = io.StringIO()
    installed = setup_logging(logging.DEBUG, stream)
    notifier = FakeNotifier()
    client = TelegramCommandClient(FAKE_TOKEN, transport=httpx.MockTransport(handler))
    app = create_app(
        bot_config(tmp_path), sources=[], notifier=notifier, start_scheduler=False, inbox=client
    )
    with TestClient(app, base_url="http://127.0.0.1") as web:
        poller = app.state.assembly.commands.poller
        poller.poll_once()
        status = poller.status()
        page = web.get("/settings").text
        view = repr(app.state.assembly.services.views.settings_page()["command_status"])
    logging.getLogger().removeHandler(installed)
    captured = capsys.readouterr()
    outputs = (status.last_error or "", page, view, caplog.text, stream.getvalue())
    for text in (*outputs, captured.out, captured.err):
        assert FAKE_TOKEN not in text and "FAKE-TOKEN" not in text
        assert BOT_URL.search(text) is None, text
    assert status.last_error


def test_token_never_leaks_from_command_paths(
    bot: Bot, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:  # AC-P9
    caplog.set_level(logging.DEBUG)

    def boom(_now: datetime) -> str:
        raise RuntimeError(f"failed at {URL_WITH_TOKEN}")

    monkeypatch.setattr(bot.commands, "list_text", boom)
    bot.notifier.fail_with = f"HTTP 400: {URL_WITH_TOKEN}"
    straddling = "/x " + "y" * (MAX_COMMAND_CHARS - 14) + FAKE_TOKEN  # cut inside the token
    bot.send(
        msg(1, "/list"),
        msg(2, f"/watch {FAKE_TOKEN}"),
        msg(3, f"/x {FAKE_TOKEN}"),
        msg(4, straddling),
    )
    texts = [r.message_text + (r.last_error or "") for r in bot.notifications()]
    for text in (*texts, caplog.text, db_dump(bot)):
        assert FAKE_TOKEN not in text and BOT_URL.search(text) is None, text
        assert "123456:FAKE" not in text, text
    assert all(r.status == "failed" for r in bot.notifications())


# ---- commands and replies (C-51) ---------------------------------------------------------


def test_help_unknown_and_usage_replies(bot: Bot) -> None:  # AC-K1, AC-K13, AC-K14
    watch_id = bot.create_watch()
    bot.send(
        msg(1, "/help"),
        msg(2, "/foo"),
        msg(3, "你好"),
        msg(4, "/watch"),
        msg(5, "/watch abc"),
        msg(6, "/watch 999"),
        msg(7, "/pause 0"),
        msg(8, "/x" + "y" * 80),
        msg(9, "/LIST"),
        msg(10, "/list@mybot"),
    )
    sent = bot.notifier.sent
    assert sent[0] == COMMAND_HELP and "新增與修改監看請至網頁" in sent[0]
    assert sent[1] == sent[2] == COMMAND_UNKNOWN and len(COMMAND_UNKNOWN.splitlines()) <= 3
    assert sent[3] == sent[4] == "用法：/watch <編號>（編號可用 /list 查看）"
    assert sent[5] == "找不到編號 999 的監看，可用 /list 查看編號。"
    assert sent[6].startswith("用法：/pause")
    assert sent[7] == COMMAND_TOO_LONG
    assert sent[8] == sent[9] and f"#{watch_id} " in sent[8]
    assert bot.repo.get_watch(watch_id).status == "active"


def test_write_commands_never_change_conditions(bot: Bot) -> None:  # FR-P10, AC-P10
    bot.scheduler_on()
    watch_id = bot.create_watch()
    before = bot.repo.get_watch(watch_id)
    bot.send(
        msg(1, "/add TPE NRT"),
        msg(2, f"/edit {watch_id}"),
        msg(3, f"/delete {watch_id}"),
        msg(4, "/set interval 5"),
        msg(5, f"/pause {watch_id}"),
        msg(6, f"/resume {watch_id}"),
        msg(7, f"/scan {watch_id}"),
        msg(8, "/digest"),
    )
    after = bot.repo.get_watch(watch_id)
    assert after.spec == before.spec and after.revision == before.revision
    assert bot.notifier.sent[:4] == [COMMAND_UNKNOWN] * 4
    assert bot.repo.get_settings().keys() <= {
        OFFSET_KEY,
        OFFSET_BOT_KEY,
    }


def priced_watches(bot: Bot) -> tuple[int, int, int]:
    """Two active watches (one with prices over two runs, one without) and one paused."""
    priced = bot.create_watch(
        date_mode="flexible",
        depart_date="",
        return_date="",
        window_start="2026-12-01",
        window_end="2026-12-08",
        min_trip_days=4,
        max_trip_days=5,
        adults=2,
        children=1,
    )
    empty = bot.create_watch(destination="KIX", name="大阪")
    paused = bot.create_watch(destination="BKK", trip_type="one_way", return_date="")
    bot.services.watches.set_enabled(paused, False)
    bot.source.price_fn = lambda q: 9000 + q.pair.depart.day * 100
    bot.services.scan.scan_watch(priced, "scheduled")
    bot.clock.advance(hours=6)
    bot.source.price_fn = lambda q: 8800 + q.pair.depart.day * 100
    bot.services.scan.scan_watch(priced, "scheduled")
    bot.source.price_fn = None
    bot.source.default_price = None
    bot.services.scan.scan_watch(empty, "scheduled")
    return priced, empty, paused


def test_list_matches_list_page(bot: Bot) -> None:  # AC-K2, AC-K18, C-51
    priced, empty, paused = priced_watches(bot)
    bot.send(msg(1, "/list"))
    reply = bot.notifier.sent[-1]
    lines = {line.split(" ", 1)[0]: line for line in reply.splitlines() if line.startswith("#")}
    page = {row["id"]: row for row in bot.services.views.list_page()["watches"]}
    row = page[priced]
    line = lines[f"#{priced}"]
    assert row["min_price"] in line and row["min_price_dates"] in line
    assert "（2 大 1 小總價）" in line
    arrow = {"down": "↓", "up": "↑"}[row["delta"]["direction"]]
    assert f"較前一輪 {arrow} {row['delta']['amount_label']}" in line
    assert "尚未查到價格" in lines[f"#{empty}"] and " 0" not in lines[f"#{empty}"]
    assert f"#{paused}" not in lines and f"停用中：#{paused}" in reply
    assert DISCLAIMER in reply and len(reply) <= COMMAND_REPLY_MAX_CHARS


def test_list_without_active_watches(bot: Bot) -> None:
    watch_id = bot.create_watch()
    bot.services.watches.set_enabled(watch_id, False)
    bot.send(msg(1, "/list"))
    assert bot.notifier.sent[-1].splitlines()[0] == "[flight-deals] 目前沒有啟用中的監看。"


def test_list_of_200_long_names_fits_and_says_how_many_are_hidden(bot: Bot) -> None:  # AC-K15
    for index in range(200):
        bot.create_watch(name=("名" * 79) + str(index % 10))
    bot.send(msg(1, "/list"))
    reply = bot.notifier.sent[-1]
    assert len(reply) <= COMMAND_REPLY_MAX_CHARS < MAX_MESSAGE_LENGTH
    assert "另有" in reply and DISCLAIMER in reply
    shown = sum(1 for line in reply.splitlines() if line.startswith("#"))
    assert f"另有 {200 - shown} 個未列出" in reply


def test_watch_matches_detail_top_three(bot: Bot) -> None:  # AC-K3, C-51
    priced, empty, paused = priced_watches(bot)
    bot.send(msg(1, f"/watch {priced}"), msg(2, f"/watch {empty}"), msg(3, f"/watch {paused}"))
    reply, empty_reply, paused_reply = bot.notifier.sent[-3:]
    top = bot.services.views.detail_page(priced)["top"][:3]
    positions = []
    for row in top:
        assert f"{row['dates']} {row['amount_text']}（2 大 1 小總價）" in reply
        assert row["booking_url"] in reply
        positions.append(reply.index(row["booking_url"]))
    assert positions == sorted(positions)
    assert (
        "已查到價格中最便宜的 3 組日期" in reply and "上次掃描：" in reply and DISCLAIMER in reply
    )
    assert "（啟用中）" in reply and "日期：彈性" in reply
    assert "已查到價格中最便宜的日期：尚未查到價格" in empty_reply
    assert "（已停用）" in paused_reply


def test_watch_with_two_prices_lists_two(bot: Bot) -> None:
    watch_id = bot.create_watch(
        date_mode="flexible",
        depart_date="",
        return_date="",
        window_start="2026-12-01",
        window_end="2026-12-06",
        min_trip_days=4,
        max_trip_days=4,
    )
    bot.services.scan.scan_watch(watch_id, "scheduled")
    bot.send(msg(1, f"/watch {watch_id}"))
    assert "已查到價格中最便宜的 2 組日期" in bot.notifier.sent[-1]


def test_pause_and_resume(bot: Bot) -> None:  # AC-K11, AC-K12
    watch_id = bot.create_watch()
    bot.send(msg(1, f"/pause {watch_id}"))
    assert bot.repo.get_watch(watch_id).status == "paused"
    assert bot.notifier.sent[-1].startswith(f"已停用監看 #{watch_id}（")
    bot.send(msg(2, f"/pause {watch_id}"))
    assert bot.notifier.sent[-1] == f"該監看已是停用（#{watch_id}）。"
    bot.send(msg(3, f"/resume {watch_id}"))
    assert bot.repo.get_watch(watch_id).status == "active"
    assert bot.notifier.sent[-1].startswith(f"已啟用監看 #{watch_id}（")
    bot.send(msg(4, f"/resume {watch_id}"))
    assert bot.notifier.sent[-1] == f"該監看已是啟用（#{watch_id}）。"


def test_resume_expired_watch_is_refused(bot: Bot) -> None:
    watch_id = bot.create_watch()
    bot.repo.set_watch_status(watch_id, "expired", bot.clock.now)
    bot.send(msg(1, f"/resume {watch_id}"))
    assert "無法啟用" in bot.notifier.sent[-1]
    assert bot.repo.get_watch(watch_id).status == "expired"


def test_scan_branches(bot: Bot) -> None:  # AC-K4, AC-K6, AC-K7, C-51
    watch_id = bot.create_watch()
    paused = bot.create_watch(destination="KIX")
    bot.services.watches.set_enabled(paused, False)
    expired = bot.create_watch(destination="BKK")
    bot.repo.set_watch_status(expired, "expired", bot.clock.now)
    bot.send(msg(1, f"/scan {watch_id}"))
    assert bot.notifier.sent[-1] == COMMAND_SCHEDULER_OFF
    bot.scheduler_on()
    bot.send(msg(2, f"/scan {paused}"), msg(3, f"/scan {expired}"), msg(4, "/scan 999"))
    assert bot.notifier.sent[-3:] == [
        COMMAND_SCAN_PAUSED,
        COMMAND_SCAN_EXPIRED,
        "找不到編號 999 的監看，可用 /list 查看編號。",
    ]
    bot.send(msg(5, f"/scan {watch_id}"))
    assert bot.scans == [watch_id]
    assert bot.notifier.sent[-1].startswith(f"已排入查價：#{watch_id}")
    assert COMMAND_SCAN_DEFERRED not in bot.notifier.sent[-1]
    bot.send(msg(6, f"/scan {watch_id}"))  # its result is still pending
    assert bot.notifier.sent[-1] == COMMAND_SCAN_PENDING and bot.scans == [watch_id]
    assert bot.source.calls == []


def test_scan_refused_without_quota(bot: Bot) -> None:  # AC-K7
    bot.scheduler_on()
    watch_id = bot.create_watch()
    bot.services.settings.update({"global_hourly_query_limit": 1})
    bot.services.scan.scan_watch(bot.create_watch(destination="KIX"), "scheduled")
    calls = len(bot.source.calls)
    bot.send(msg(1, f"/scan {watch_id}"))
    assert bot.notifier.sent[-1].startswith("本小時查詢額度已用完（已用 1／上限 1）")
    assert bot.scans == [] and len(bot.source.calls) == calls


def test_scan_pending_web_job_and_exploration_note(bot: Bot) -> None:
    bot.commands.hooks.scheduler_running = lambda: True
    watch_id = bot.create_watch()
    scheduler = bot.assembly.scheduler
    bot.commands.hooks.schedule_scan = scheduler.trigger_command_scan
    bot.commands.hooks.scan_pending = scheduler.scan_pending
    scheduler.trigger_now(watch_id)  # web "scan now" already queued
    bot.send(msg(1, f"/scan {watch_id}"))
    assert bot.notifier.sent[-1] == COMMAND_SCAN_PENDING
    scheduler.scheduler.remove_job(f"manual:{watch_id}")
    spec = ExplorationSpec("TPE", "NRT", "one_way", 2026, 12, None, None)
    bot.repo.insert_exploration(spec, [DatePair(datetime(2026, 12, 1).date())], bot.clock.now)
    bot.send(msg(2, f"/scan {watch_id}"))
    assert COMMAND_SCAN_DEFERRED in bot.notifier.sent[-1]
    assert scheduler.scheduler.get_job(f"cmdscan:{watch_id}") is not None


def test_scan_result_reply_follows_the_job(bot: Bot) -> None:  # AC-K4, AC-K5, AC-L1
    bot.commands.hooks.scheduler_running = lambda: True
    watch_id = bot.create_watch()
    scheduler = bot.assembly.scheduler
    bot.commands.hooks.schedule_scan = scheduler.trigger_command_scan
    bot.send(msg(5, f"/scan {watch_id}"))
    assert scheduler.scheduler.get_job(f"cmdscan:{watch_id}") is not None
    assert scheduler.next_run_time() is not None
    scheduler._command_scan(watch_id)  # the job body, on this thread
    results = [r for r in bot.notifications("command") if r.dedupe_key.endswith(":result")]
    assert [r.dedupe_key for r in results] == [f"cmd:{BOT_ID}:5:result"]
    reply = bot.notifier.sent[-1]
    assert reply.startswith(f"[flight-deals] /scan #{watch_id}") and "查價完成（成功）" in reply
    assert "目前最低價：TWD 10,000（1 人總價）" in reply and DISCLAIMER in reply
    assert results[0].message_text.startswith(f"/scan {watch_id}（查價結果）")
    assert bot.repo.latest_scan_run_for_watch(watch_id).trigger == "manual"
    scheduler._command_scan(watch_id)  # a second run of the same job: no second reply
    assert len([r for r in bot.notifications("command") if r.dedupe_key.endswith(":result")]) == 1


def test_scan_result_states_failure_reason(bot: Bot) -> None:  # AC-K5
    bot.scheduler_on()
    watch_id = bot.create_watch()
    bot.send(msg(5, f"/scan {watch_id}"))
    bot.source.status_override = "blocked"
    bot.assembly.scheduler._command_scan(watch_id)
    reply = bot.notifier.sent[-1]
    assert "本輪未查到價格：資料源被擋或格式改變" in reply
    assert "目前最低價：尚未查到價格（1 人）" in reply
    assert "0 元" not in reply and "TWD 0" not in reply


def test_digest_is_manual_and_repeatable(bot: Bot) -> None:  # AC-K8, AC-K9, C-51
    bot.commands.hooks.scheduler_running = lambda: True
    scheduler = bot.assembly.scheduler
    bot.commands.hooks.schedule_manual_digest = scheduler.schedule_manual_digest
    bot.create_watch()
    bot.send(msg(1, "/digest"), msg(2, "/digest"))
    assert bot.notifier.sent == [
        COMMAND_DIGEST_QUEUED,
        COMMAND_DIGEST_QUEUED,
    ]  # poller sends no digest
    jobs = sorted(j.id for j in scheduler.scheduler.get_jobs() if j.id.startswith("manual-digest:"))
    assert jobs == ["manual-digest:1", "manual-digest:2"]
    for key in (f"digest-manual:{BOT_ID}:1", f"digest-manual:{BOT_ID}:2"):
        scheduler._manual_digest(key)
    manual = bot.notifications("manual_digest")
    assert len(manual) == 2 and all(r.status == "sent" for r in manual)
    assert bot.notifications("daily_digest") == []
    assert bot.notifier.sent[-1].startswith("[flight-deals] 每日摘要")
    # The scheduled digest of the day is still sent once (not eaten by /digest).
    bot.clock.now = datetime(2026, 10, 26, 1, 0, tzinfo=UTC)  # 09:00 Taipei
    assert bot.services.digest.send_if_due() == "sent"


def test_send_once_kinds_are_never_retried(bot: Bot) -> None:  # FR-L3, C-51
    bot.scheduler_on()
    bot.notifier.fail_with = "HTTP 502"
    watch_id = bot.create_watch()
    bot.send(msg(1, f"/pause {watch_id}"))
    bot.services.digest.send_manual(bot.clock.now, f"digest-manual:{BOT_ID}:9")
    failed = bot.notifications()
    assert {r.kind for r in failed} == {"command", "manual_digest"}
    assert all(r.status == "failed" and r.attempts == 1 for r in failed)
    assert bot.repo.retryable_notifications(10) == []
    bot.notifier.fail_with = None
    assert bot.services.notifications.retry_pending() == 0
    assert bot.repo.get_watch(watch_id).status == "paused"  # effect kept (AC-L3)


def test_one_failing_command_does_not_stop_the_batch(
    bot: Bot, monkeypatch: pytest.MonkeyPatch
) -> None:  # AC-K16, FR-K12
    watch_id = bot.create_watch()

    def broken(_watch: Any, _now: datetime) -> str:
        raise sqlite3.OperationalError("database is locked")

    monkeypatch.setattr(bot.commands, "watch_text", broken)
    bot.send(
        msg(1, f"/pause {watch_id}"),
        msg(2, "/foo"),
        msg(3, f"/watch {watch_id}"),
        msg(4, "/list"),
    )
    sent = bot.notifier.sent
    assert sent[0].startswith("已停用監看") and sent[1] == COMMAND_UNKNOWN
    assert sent[2] == COMMAND_FAILED and "locked" not in sent[2]
    assert sent[3].startswith("[flight-deals]")


def test_command_records_and_labels(bot: Bot) -> None:  # AC-L1
    bot.send(msg(1, "/list"))
    record = bot.notifications("command")[0]
    assert record.message_text.startswith("/list → [flight-deals]")
    assert record.status == "sent" and record.dedupe_key == f"cmd:{BOT_ID}:1"
    page = bot.services.views.notifications_page()["notifications"]
    assert page[0]["kind"] == "指令"
    bot.services.digest.send_manual(bot.clock.now, f"digest-manual:{BOT_ID}:2")
    kinds = {row["kind"] for row in bot.services.views.notifications_page()["notifications"]}
    assert {"指令", "手動摘要"} <= kinds
    html = bot.client.get("/notifications").text
    assert "手動摘要" in html


def test_status_reply(bot: Bot) -> None:  # AC-K10
    now = bot.clock.now
    bot.repo.save_source_health(
        SourceHealthRecord("google_flights", True, "open", 3, now, None, now, "blocked x")
    )
    with bot.assembly.database.connect() as conn:
        conn.execute(
            "INSERT INTO scan_run (watch_id, watch_revision, started_at, finished_at, status,"
            " sampled_pairs, queries_used) VALUES (?, 1, ?, ?, 'ok', '[]', 40)",
            (bot.create_watch(), now.isoformat(), now.isoformat()),
        )
    bot.commands.hooks.scheduler_running = lambda: True
    bot.commands.hooks.next_run_time = lambda: datetime(2026, 10, 25, 6, 30, tzinfo=UTC)
    bot.send(msg(1, "/status"))
    reply = bot.notifier.sent[-1]
    assert "Google Flights 異常" in reply and "斷路器：開啟（暫停查詢）" in reply
    assert "已用 40／上限 60" in reply and "2026-10-25 14:30（台北時間）" in reply
    assert "目前沒有進行中的探索" in reply and "blocked x" not in reply
    spec = ExplorationSpec("TPE", "NRT", "round_trip", 2026, 12, 5, None)
    pairs = [DatePair(datetime(2026, 12, d).date()) for d in range(1, 32)]
    exploration_id = bot.repo.insert_exploration(spec, pairs, now)
    with bot.assembly.database.connect() as conn:
        conn.execute(
            "UPDATE exploration SET status = 'running', done = 12 WHERE id = ?", (exploration_id,)
        )
    bot.send(msg(2, "/status"))
    reply = bot.notifier.sent[-1]
    assert "已查 12／共 31" in reply and "2026 年 12 月" in reply
    assert "可能順延" in reply
    bot.commands.hooks.next_run_time = lambda: now - timedelta(minutes=5)
    bot.send(msg(3, "/status"))
    assert "排程掃描順延至探索結束後" in bot.notifier.sent[-1]


def test_reply_texts_have_no_banned_wording(bot: Bot) -> None:  # AC-K17, C-51
    bot.scheduler_on()
    priced, empty, paused = priced_watches(bot)
    commands = [
        "/help",
        "/list",
        f"/watch {priced}",
        f"/scan {priced}",
        "/digest",
        "/status",
        f"/pause {priced}",
        f"/resume {priced}",
        "/foo",
        "/watch",
        "你好",
    ]
    bot.send(*[msg(i, text) for i, text in enumerate(commands, start=1)])
    bot.commands.on_scan_finished(priced, bot.services.scan.scan_watch(priced, "manual"))
    tree = ast.parse((SRC / "services" / "commands.py").read_text(encoding="utf-8"))
    constants = [
        n.value for n in ast.walk(tree) if isinstance(n, ast.Constant) and isinstance(n.value, str)
    ]
    for text in (*bot.notifier.sent, *constants):
        for phrase in BANNED_PHRASES:
            assert phrase not in text, (phrase, text)


def test_settings_switch_validation_and_header(bot: Bot) -> None:  # AC-L7, C-54
    response = bot.client.post("/api/settings", json={"telegram_commands_enabled": False})
    assert response.status_code == 403
    for bad in ("maybe", 2, None):
        response = bot.client.post(
            "/api/settings", json={"telegram_commands_enabled": bad}, headers=CLIENT_HEADERS
        )
        assert response.status_code == 422
    assert bot.services.settings.current().telegram_commands_enabled is True
    bot.repo.save_settings({"telegram_commands_enabled": "garbage"}, bot.clock.now)
    assert bot.services.settings.current().telegram_commands_enabled is True
    response = bot.client.post(
        "/api/settings", json={"telegram_commands_enabled": False}, headers=CLIENT_HEADERS
    )
    assert response.status_code == 200
    assert bot.services.views.settings_page()["telegram_commands_enabled"] is False


@pytest.mark.parametrize(
    ("status", "enabled", "state", "label"),
    [
        (
            PollerStatus("unconfigured", False, False, False, None, None, None, 0),
            True,
            "unconfigured",
            "未設定 Telegram",
        ),
        (PollerStatus(None, True, False, False, None, None, None, 0), False, "disabled", "已關閉"),
        (PollerStatus(None, True, False, False, None, None, None, 0), True, "running", "運作中"),
        (
            PollerStatus(None, True, False, True, None, NOW_UTC, "逾時", 2),
            True,
            "running",
            "運作中（最近連線失敗，重試中）",
        ),
        (
            PollerStatus(None, True, True, True, None, NOW_UTC, "401", 0),
            True,
            "stopped",
            "已停止（bot token 無效，更新 token 後請重新啟動服務）",
        ),
        (
            PollerStatus(None, False, False, False, None, None, None, 0),
            True,
            "stopped",
            "未執行（此實例沒有持有排程鎖）",
        ),
    ],
)
def test_command_status_states(
    bot: Bot, status: PollerStatus, enabled: bool, state: str, label: str
) -> None:  # FR-L5, AC-L6, C-54
    views = bot.services.views
    views.hooks.command_status = lambda: status
    view = views.command_status_view(enabled)
    assert view is not None and (view["state"], view["label"]) == (state, label)
    assert view["last_command_at_label"] is None
    if status.last_error_at is not None:
        assert view["last_error_label"] == f"2026-10-25 12:00：{status.last_error}"
    views.hooks.command_status = lambda: None
    assert views.command_status_view(True) is None


# ---- risk review (R1-R3) and QA follow-ups -----------------------------------------------


def test_list_marks_stale_watch_and_old_price(bot: Bot) -> None:  # R3
    watch_id = bot.create_watch()
    bot.services.scan.scan_watch(watch_id, "scheduled")
    bot.repo.set_watch_status(watch_id, "stale", bot.clock.now)
    bot.clock.advance(hours=25)
    bot.send(msg(1, "/list"))
    line = next(x for x in bot.notifier.sent[-1].splitlines() if x.startswith(f"#{watch_id} "))
    assert "此價格逾 24 小時未重查" in line and line.endswith("連續查價失敗")
    assert "｜上次查價 10-25 12:00" in line
    assert "差額不代表同一行程的漲跌" in bot.notifier.sent[-1]
    assert SAMPLED_ONLY_NOTE in bot.notifier.sent[-1]


def test_watch_and_detail_skip_departed_and_other_currency(bot: Bot) -> None:  # R1
    watch_id = bot.create_watch(
        date_mode="flexible",
        depart_date="",
        return_date="",
        window_start="2026-10-26",
        window_end="2026-11-05",
        min_trip_days=4,
        max_trip_days=4,
    )
    bot.source.price_fn = lambda q: (
        5_000 if q.pair.depart.day == 26 else 9_000 + (q.pair.depart - date(2026, 10, 26)).days
    )
    bot.services.scan.scan_watch(watch_id, "scheduled")
    bot.clock.advance(days=3)  # today is 10-28: the 10-26 and 10-27 departures are past
    with bot.assembly.database.connect() as conn:  # a cheaper price in another currency
        conn.execute(
            "UPDATE price_observation SET currency = 'JPY', amount_minor = 1"
            " WHERE depart_date = '2026-10-30'"
        )
    bot.send(msg(1, f"/watch {watch_id}"))
    reply = bot.notifier.sent[-1]
    top = bot.services.views.detail_page(watch_id)["top"]
    assert [row["depart"] for row in top][:3] == ["2026-10-28", "2026-10-29", "2026-10-31"]
    for row in top[:3]:
        assert f"{row['dates']} {row['amount_text']}" in reply
    assert "10/26" not in reply and "TWD 5,000" not in reply and "JPY" not in reply
    assert "｜查到 10-25 12:00｜此價格逾 24 小時未重查" in reply
    assert "已查到價格中最便宜的 3 組日期" in reply and SAMPLED_ONLY_NOTE in reply


def test_scan_result_flags_price_from_earlier_run(bot: Bot) -> None:  # R2
    bot.scheduler_on()
    watch_id = bot.create_watch()
    bot.services.scan.scan_watch(watch_id, "scheduled")
    bot.clock.advance(hours=2)
    bot.send(msg(5, f"/scan {watch_id}"))
    bot.source.status_override = "blocked"
    bot.assembly.scheduler._command_scan(watch_id)
    reply = bot.notifier.sent[-1]
    assert "查價完成（失敗）" in reply and "本輪未查到價格：資料源被擋或格式改變" in reply
    assert "目前最低價：TWD 10,000（1 人總價） 12/10–12/15（查到 10-25 12:00）" in reply
    assert "此價格為先前掃描查到，本輪未更新" in reply


def test_scan_result_from_this_run_has_no_carried_over_note(bot: Bot) -> None:  # R2
    bot.scheduler_on()
    watch_id = bot.create_watch()
    bot.send(msg(5, f"/scan {watch_id}"))
    bot.assembly.scheduler._command_scan(watch_id)
    assert "本輪未更新" not in bot.notifier.sent[-1]


def test_crashing_scan_job_still_answers_and_clears_pending(
    bot: Bot, monkeypatch: pytest.MonkeyPatch
) -> None:  # QA 1
    bot.scheduler_on()
    watch_id = bot.create_watch()

    def boom(_watch_id: int, _trigger: str = "scheduled") -> Any:
        raise RuntimeError(f"exploded at {URL_WITH_TOKEN}")

    bot.send(msg(5, f"/scan {watch_id}"))
    monkeypatch.setattr(bot.services.scan, "scan_watch", boom)
    with pytest.raises(RuntimeError):
        bot.assembly.scheduler._command_scan(watch_id)
    reply = bot.notifier.sent[-1]
    assert "未查價：查價執行時發生錯誤" in reply and FAKE_TOKEN not in reply
    assert bot.commands.pending_scans() == {}
    bot.send(msg(6, f"/scan {watch_id}"))
    assert bot.notifier.sent[-1].startswith(f"已排入查價：#{watch_id}")


def test_command_badge_tone_follows_state(bot: Bot) -> None:  # QA 3
    views = bot.services.views
    views.hooks.command_status = lambda: PollerStatus(
        None, True, False, True, None, NOW_UTC, "x", 0
    )
    assert views.command_status_view(True)["tone"] == "warn"
    views.hooks.command_status = lambda: PollerStatus(None, True, True, True, None, None, None, 0)
    assert views.command_status_view(True)["tone"] == "down"

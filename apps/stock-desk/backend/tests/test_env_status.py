"""Start-up secret-status line: reports set / unset per channel and never a value.

Every secret below is a fake. The assertions look at the real stderr output of
the real entry points (API lifespan, scheduler ``main()``), not only at the
formatter, so a value cannot slip in through any later layer.
"""

from __future__ import annotations

import logging
from collections.abc import Iterator
from contextlib import contextmanager

import pytest
from fastapi.testclient import TestClient

import app.scheduler as scheduler_module
from app.alerts.notify import DISCORD_WEBHOOK_ENV, TELEGRAM_CHAT_ID_ENV, TELEGRAM_TOKEN_ENV
from app.data.providers.alpha_vantage import API_KEY_ENV_VAR
from app.data.providers.finmind import TOKEN_ENV_VAR
from app.env_status import SET_LABEL, UNSET_LABEL, describe_env_status
from app.logging_setup import INFO_NAMESPACES, QUIET_NAMESPACES
from app.main import app

# Distinctive fakes: any fragment of these showing up in output is a leak.
FAKE_VALUES = {
    TOKEN_ENV_VAR: "zzfinmindvalue9981",
    API_KEY_ENV_VAR: "zzalphavalue7742",
    DISCORD_WEBHOOK_ENV: "https://discord.example/api/webhooks/5550001/zzdiscordvalue3310",
    TELEGRAM_TOKEN_ENV: "5550002:zztelegramvalue6625",
    TELEGRAM_CHAT_ID_ENV: "zzchatvalue4417",
}
ALL_ENV_NAMES = tuple(FAKE_VALUES)


@pytest.fixture(autouse=True)
def _restore_logger_levels() -> Iterator[None]:
    """configure_logging() mutates global loggers; put every one back afterwards.

    Without this, the ``app`` logger would stay at INFO for later tests and
    swallow their DEBUG records even under ``caplog.at_level(DEBUG)``.
    """
    names = (*INFO_NAMESPACES, *QUIET_NAMESPACES)
    saved = {name: logging.getLogger(name).level for name in names}
    yield
    for name, level in saved.items():
        logging.getLogger(name).setLevel(level)


@contextmanager
def _owned_root() -> Iterator[logging.Logger]:
    """A root logger without handlers, as in a freshly started process."""
    root = logging.getLogger()
    saved_handlers = list(root.handlers)
    saved_level = root.level
    root.handlers = []
    try:
        yield root
    finally:
        root.handlers = saved_handlers
        root.setLevel(saved_level)


def _clear_all(monkeypatch: pytest.MonkeyPatch) -> None:
    for name in ALL_ENV_NAMES:
        monkeypatch.delenv(name, raising=False)


def _set_all(monkeypatch: pytest.MonkeyPatch) -> None:
    for name, value in FAKE_VALUES.items():
        monkeypatch.setenv(name, value)


def _assert_no_value_or_fragment(text: str) -> None:
    for value in FAKE_VALUES.values():
        assert value not in text
        # Not even a part of it: prefixes, suffixes and the distinctive core.
        assert value[:6] not in text
        assert value[-6:] not in text
    assert "zz" not in text


def test_all_unset_reports_unset_for_every_channel() -> None:
    line = describe_env_status({})
    assert line.count(UNSET_LABEL) == 4
    assert SET_LABEL not in line
    for label in ("FINMIND token", "Alpha Vantage key", "Discord webhook", "Telegram"):
        assert label in line


def test_all_set_reports_set_without_any_value() -> None:
    line = describe_env_status(FAKE_VALUES)
    assert line.count(SET_LABEL) == 4
    assert UNSET_LABEL not in line
    _assert_no_value_or_fragment(line)


def test_telegram_needs_both_token_and_chat_id() -> None:
    only_token = {TELEGRAM_TOKEN_ENV: FAKE_VALUES[TELEGRAM_TOKEN_ENV]}
    only_chat = {TELEGRAM_CHAT_ID_ENV: FAKE_VALUES[TELEGRAM_CHAT_ID_ENV]}
    assert f"Telegram：{UNSET_LABEL}" in describe_env_status(only_token)
    assert f"Telegram：{UNSET_LABEL}" in describe_env_status(only_chat)
    both = {**only_token, **only_chat}
    assert f"Telegram：{SET_LABEL}" in describe_env_status(both)


def test_blank_values_count_as_unset() -> None:
    blank = {name: "   " for name in ALL_ENV_NAMES}
    assert SET_LABEL not in describe_env_status(blank)
    empty = {name: "" for name in ALL_ENV_NAMES}
    assert SET_LABEL not in describe_env_status(empty)


def test_reads_the_process_environment_by_default(monkeypatch: pytest.MonkeyPatch) -> None:
    _clear_all(monkeypatch)
    assert SET_LABEL not in describe_env_status()
    monkeypatch.setenv(TOKEN_ENV_VAR, FAKE_VALUES[TOKEN_ENV_VAR])
    assert f"FINMIND token：{SET_LABEL}" in describe_env_status()


def test_api_lifespan_logs_status_and_no_value(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    _set_all(monkeypatch)
    with _owned_root():
        with TestClient(app) as client:
            assert client.get("/health").status_code == 200
        err = capsys.readouterr().err
    status_lines = [line for line in err.splitlines() if "環境設定載入狀態" in line]
    assert len(status_lines) == 1
    assert "backend" in status_lines[0]
    assert f"FINMIND token：{SET_LABEL}" in status_lines[0]
    assert f"Discord webhook：{SET_LABEL}" in status_lines[0]
    assert f"Telegram：{SET_LABEL}" in status_lines[0]
    _assert_no_value_or_fragment(err)


def test_api_lifespan_reports_unset_when_nothing_is_configured(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    _clear_all(monkeypatch)
    with _owned_root():
        with TestClient(app):
            pass
        err = capsys.readouterr().err
    status_lines = [line for line in err.splitlines() if "環境設定載入狀態" in line]
    assert len(status_lines) == 1
    assert status_lines[0].count(UNSET_LABEL) == 4


def test_scheduler_main_logs_status_and_no_value(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    _set_all(monkeypatch)
    ran: list[bool] = []
    monkeypatch.setattr(scheduler_module, "run", lambda: ran.append(True))
    with _owned_root():
        scheduler_module.main()
        err = capsys.readouterr().err
    assert ran == [True]
    status_lines = [line for line in err.splitlines() if "環境設定載入狀態" in line]
    assert len(status_lines) == 1
    assert "scheduler" in status_lines[0]
    assert status_lines[0].count(SET_LABEL) == 4
    _assert_no_value_or_fragment(err)


def test_scheduler_main_reports_unset(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    _clear_all(monkeypatch)
    monkeypatch.setattr(scheduler_module, "run", lambda: None)
    with _owned_root():
        scheduler_module.main()
        err = capsys.readouterr().err
    status_lines = [line for line in err.splitlines() if "環境設定載入狀態" in line]
    assert len(status_lines) == 1
    assert status_lines[0].count(UNSET_LABEL) == 4

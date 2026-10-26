"""Configuration loading (C-15) and offline guarantee (C-5)."""

from __future__ import annotations

import socket
from pathlib import Path

import httpx
import pytest
import uvicorn

from flight_deals import cli
from flight_deals.config import DEFAULT_DB_PATH, ConfigError, load_config, parse_dotenv
from tests.conftest import NetworkBlockedError


def test_production_refuses_fixture_source() -> None:  # C-15
    with pytest.raises(ConfigError, match="fixture"):
        load_config({"FLIGHT_DEALS_SOURCES": "google_flights,fixture"}, dotenv_path=None)
    config = load_config({"FLIGHT_DEALS_SOURCES": "fixture"}, production=False, dotenv_path=None)
    assert config.sources == ("fixture",)


def test_cli_exits_when_fixture_configured(monkeypatch: pytest.MonkeyPatch) -> None:  # C-15
    monkeypatch.setenv("FLIGHT_DEALS_SOURCES", "fixture")
    started: list[object] = []
    monkeypatch.setattr(uvicorn, "run", lambda *a, **k: started.append(a))
    assert cli.main([]) == 2
    assert started == []


def test_unknown_source_rejected() -> None:
    with pytest.raises(ConfigError):
        load_config({"FLIGHT_DEALS_SOURCES": "amadeus"}, dotenv_path=None)


def test_defaults() -> None:
    config = load_config({}, dotenv_path=None)
    assert config.sources == ("google_flights",)
    assert config.port == 8795 and config.host == "127.0.0.1"
    assert config.db_path == DEFAULT_DB_PATH
    assert not config.telegram_configured
    assert config.tunables.scan_interval_minutes == 360
    assert config.tunables.max_pairs_per_scan == 12
    assert config.tunables.drop_threshold_bp == 500
    assert config.tunables.stale_after_hours == 24
    assert config.limits.alert_max_items == 5
    assert config.limits.breaker_failure_threshold == 3
    assert config.limits.breaker_cooldown_minutes == 30
    assert config.limits.watch_stale_after_failed_scans == 3
    assert config.limits.notification_max_attempts == 3


def test_dotenv_loaded_and_env_wins(tmp_path: Path) -> None:
    dotenv = tmp_path / ".env"
    dotenv.write_text(
        '# comment\nFLIGHT_DEALS_TELEGRAM_BOT_TOKEN="111:placeholder"\nFLIGHT_DEALS_PORT=9000\n',
        encoding="utf-8",
    )
    config = load_config({"FLIGHT_DEALS_PORT": "9100"}, dotenv_path=dotenv)
    assert config.telegram_bot_token == "111:placeholder"
    assert config.port == 9100
    assert "111:placeholder" not in repr(config)
    assert parse_dotenv("export A=1\nB='2'\n") == {"A": "1", "B": "2"}


def test_invalid_port() -> None:
    with pytest.raises(ConfigError):
        load_config({"FLIGHT_DEALS_PORT": "abc"}, dotenv_path=None)


def test_outbound_network_is_blocked_in_tests() -> None:  # C-5
    with pytest.raises(NetworkBlockedError):
        socket.create_connection(("93.184.216.34", 443), timeout=1)
    with pytest.raises((NetworkBlockedError, httpx.ConnectError)):
        httpx.get("https://example.com", timeout=1)

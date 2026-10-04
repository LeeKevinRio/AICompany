"""The isolation guards in ``conftest.py`` really guard.

A guard that is never shown to fire is a guess. Each test here provokes the
violation on purpose, asserts the guard saw it, and then undoes the evidence so
the autouse fixture's teardown check passes.
"""

from __future__ import annotations

import os
import socket
from pathlib import Path

import pytest

from app.data.market_panel import MarketPanelStore, resolve_market_db_path
from tests.isolation_helpers import NetworkBlockedError, is_blocked_address

BACKEND_ROOT = Path(__file__).resolve().parent.parent


def test_default_db_paths_resolve_outside_the_repo_data_dir(
    _default_db_paths_must_stay_unused: Path,
) -> None:
    sentinel_dir = _default_db_paths_must_stay_unused
    assert resolve_market_db_path().parent == sentinel_dir
    assert BACKEND_ROOT / "data" not in resolve_market_db_path().parents


def test_a_default_path_store_lands_in_the_sentinel_dir_and_is_detected(
    _default_db_paths_must_stay_unused: Path,
) -> None:
    sentinel_dir = _default_db_paths_must_stay_unused
    assert list(sentinel_dir.iterdir()) == []

    store = MarketPanelStore()  # the mistake the guard exists to catch

    assert store.db_path.parent == sentinel_dir
    created = list(sentinel_dir.iterdir())
    assert created, "the guard's teardown check would have missed this store"
    for path in created:  # erase the evidence so this test's own teardown passes
        path.unlink()


def test_default_market_db_resolution_without_the_env_var(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("STOCK_DESK_MARKET_DB_PATH")
    assert resolve_market_db_path() == Path("./data/stock-desk-market.db")


def test_the_socket_guard_blocks_a_public_address_and_records_it(
    _no_outbound_network: list[str],
) -> None:
    with pytest.raises(NetworkBlockedError):
        socket.create_connection(("93.184.216.34", 443), timeout=1)
    assert _no_outbound_network == ["('93.184.216.34', 443)"]
    _no_outbound_network.clear()  # erase the evidence so this test's own teardown passes


def test_the_socket_guard_blocks_the_configured_proxy_port(
    monkeypatch: pytest.MonkeyPatch, _no_outbound_network: list[str]
) -> None:
    # The sandbox proxy that let the original leak reach TWSE sits on loopback.
    monkeypatch.setenv("HTTPS_PROXY", "http://127.0.0.1:40359")
    with pytest.raises(NetworkBlockedError):
        socket.create_connection(("127.0.0.1", 40359), timeout=1)
    assert len(_no_outbound_network) == 1
    _no_outbound_network.clear()


def test_classifier_allows_loopback_and_unix_but_not_a_proxy_port(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    for name in list(os.environ):
        if name.lower().endswith("_proxy"):
            monkeypatch.delenv(name)
    monkeypatch.setenv("HTTPS_PROXY", "http://user:pw@127.0.0.1:40359")
    assert is_blocked_address(("127.0.0.1", 8000), socket.AF_INET) is False
    assert is_blocked_address(("::1", 8000, 0, 0), socket.AF_INET6) is False
    assert is_blocked_address("/tmp/x.sock", socket.AF_UNIX) is False
    assert is_blocked_address(("127.0.0.1", 40359), socket.AF_INET) is True
    assert is_blocked_address(("example.com", 443), socket.AF_INET) is True
    assert is_blocked_address(("10.0.0.5", 80), socket.AF_INET) is True

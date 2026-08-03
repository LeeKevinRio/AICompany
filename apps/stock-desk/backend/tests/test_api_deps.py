"""Tests for the production dependency wiring in ``app/api/deps.py``.

These construct the *real* adapters (no network call is made at construction
time) against a temp database, so a wiring mistake -- a missing store, a market
map that accidentally claims to cover US -- fails here instead of at runtime.
Every memoized provider is reset around the test so the temp-path instances
never leak into another test.
"""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import pytest

from app.api import deps
from app.data.cache import DEFAULT_DB_PATH
from app.data.providers.alpha_vantage import AlphaVantageAdapter
from app.data.providers.yfinance import YFinanceAdapter
from app.services.index import IndexProviderBridge, IndexSeriesService

_CACHED = (
    deps._default_store,
    deps._default_cache,
    deps._default_yfinance,
    deps._default_resolver,
    deps._default_index_resolver,
    deps._default_valuator,
    deps._default_settings_store,
    deps._default_alert_store,
    deps._default_quota_ledger,
)


@pytest.fixture
def isolated_deps(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    monkeypatch.setenv("STOCK_DESK_DB_PATH", str(tmp_path / "stock-desk.db"))
    for provider in _CACHED:
        provider.cache_clear()
    yield
    for provider in _CACHED:
        provider.cache_clear()


def test_every_provider_is_memoized_per_process(isolated_deps: None) -> None:
    assert deps.get_position_store() is deps.get_position_store()
    assert deps.get_settings_store() is deps.get_settings_store()
    assert deps.get_alert_store() is deps.get_alert_store()
    assert deps.get_valuator() is deps.get_valuator()
    assert deps.get_market_resolver() is deps.get_market_resolver()
    assert deps.get_quota_ledger() is deps.get_quota_ledger()


def test_stores_land_on_the_configured_database_path(
    isolated_deps: None, tmp_path: Path
) -> None:
    expected = tmp_path / "stock-desk.db"
    assert deps.get_position_store().db_path == expected
    assert deps.get_settings_store().db_path == expected
    assert deps.get_alert_store().db_path == expected
    # The quota ledger must land on the *same* file: the counter is only
    # cross-process if the API and the scheduler address one database.
    assert deps.get_quota_ledger().db_path == expected
    # And the default is a relative project path, not an absolute system one.
    assert DEFAULT_DB_PATH.startswith("./")


def test_market_resolver_covers_tw_and_us(isolated_deps: None) -> None:
    resolver = deps.get_market_resolver()
    assert set(resolver) == {"TW", "US"}


def test_the_us_ladder_is_alpha_vantage_then_yfinance(isolated_deps: None) -> None:
    us = deps.get_market_resolver()["US"]
    # Private attributes on purpose: the ordering of the ladder is the whole
    # decision being pinned here (ADR-0005 決策四), and it is not observable
    # from outside without issuing real requests.
    assert isinstance(us._primary, AlphaVantageAdapter)  # type: ignore[attr-defined]
    assert [type(backup) for backup in us._backups] == [  # type: ignore[attr-defined]
        YFinanceAdapter
    ]


def test_cache_first_is_on_for_us_and_index_and_off_for_tw(isolated_deps: None) -> None:
    resolver = deps.get_market_resolver()
    # ADR-0005 D-1: Taiwan has no quota pressure and its behaviour must not move.
    assert resolver["TW"]._cache_first is False  # type: ignore[attr-defined]
    assert resolver["US"]._cache_first is True  # type: ignore[attr-defined]
    index_service = deps.get_index_resolver()["TW"]
    assert isinstance(index_service, IndexSeriesService)
    assert index_service._inner._cache_first is True  # type: ignore[attr-defined]


def test_index_resolver_is_yfinance_only_and_never_alpha_vantage(
    isolated_deps: None,
) -> None:
    resolver = deps.get_index_resolver()
    assert set(resolver) == {"TW", "US"}
    # Both markets share one service; an index's market is the adapter's fact.
    assert resolver["TW"] is resolver["US"]
    inner = resolver["TW"]._inner  # type: ignore[attr-defined]
    bridge = inner._primary
    assert isinstance(bridge, IndexProviderBridge)
    assert isinstance(bridge._provider, YFinanceAdapter)
    # Alpha Vantage must not appear anywhere on the index path: its quota is
    # reserved for the symbols a user actually holds (ADR-0005 決策一 point 2).
    assert inner._backups == ()


def test_the_one_yfinance_adapter_serves_both_of_its_roles(isolated_deps: None) -> None:
    us_backup = deps.get_market_resolver()["US"]._backups[0]  # type: ignore[attr-defined]
    index_bridge = deps.get_index_resolver()["TW"]._inner._primary  # type: ignore[attr-defined]
    # One instance, therefore one client-side throttle against the same host.
    assert us_backup is index_bridge._provider


def test_every_ladder_shares_one_cache(isolated_deps: None) -> None:
    resolver = deps.get_market_resolver()
    index_inner = deps.get_index_resolver()["TW"]._inner  # type: ignore[attr-defined]
    shared = deps._default_cache()
    assert resolver["TW"]._cache is shared  # type: ignore[attr-defined]
    assert resolver["US"]._cache is shared  # type: ignore[attr-defined]
    assert index_inner._cache is shared

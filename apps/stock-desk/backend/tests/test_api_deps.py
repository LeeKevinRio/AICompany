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

_CACHED = (
    deps._default_store,
    deps._default_resolver,
    deps._default_valuator,
    deps._default_settings_store,
    deps._default_alert_store,
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


def test_stores_land_on_the_configured_database_path(
    isolated_deps: None, tmp_path: Path
) -> None:
    expected = tmp_path / "stock-desk.db"
    assert deps.get_position_store().db_path == expected
    assert deps.get_settings_store().db_path == expected
    assert deps.get_alert_store().db_path == expected
    # And the default is a relative project path, not an absolute system one.
    assert DEFAULT_DB_PATH.startswith("./")


def test_market_resolver_covers_tw_only(isolated_deps: None) -> None:
    resolver = deps.get_market_resolver()
    # US has no adapter yet; claiming it would produce fabricated US prices.
    assert set(resolver) == {"TW"}

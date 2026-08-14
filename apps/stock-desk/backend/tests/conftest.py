"""Shared fixtures for the Phase 6 API tests.

The ``api_client`` fixture overrides **every** production dependency with a
temp-directory store or an offline fake, so no test can reach the network or the
developer's real database. It is deliberately separate from the fixture in
``test_positions_api.py``, which predates it and overrides only the store.
"""

from __future__ import annotations

from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.alerts.store import AlertStore
from app.api.deps import (
    get_alert_store,
    get_dividend_store,
    get_fx_provider,
    get_index_resolver,
    get_market_resolver,
    get_position_store,
    get_price_bar_cache,
    get_quota_ledger,
    get_settings_store,
    get_valuator,
)
from app.data.cache import PriceBarCache
from app.data.interface import DataStatus
from app.data.providers.fx import FxRateProvider
from app.data.quota import QuotaLedger
from app.dividends.store import DividendEventStore
from app.main import app
from app.portfolio.valuation import PositionValuator
from app.positions.store import PositionStore
from app.settings.store import SettingsStore
from tests.api_helpers import FakePriceService, UnavailableFxProvider


@dataclass
class ApiHarness:
    """The client plus the fakes behind it, so a test can seed either side."""

    client: TestClient
    price_service: FakePriceService
    #: Index series only, keyed by index code (``^TWII``), never by ETF symbol.
    index_service: FakePriceService
    positions: PositionStore
    alerts: AlertStore
    settings: SettingsStore
    fx_provider: FxRateProvider
    #: Temp-directory ledger; a test reserves against it to drive the
    #: data-source block of ``GET /api/settings``.
    quota: QuotaLedger
    #: Temp-directory 除權息 store, **empty by default** -- the same state a
    #: machine that has never run ``python -m app.dividends.sync`` is in, so the
    #: "未還原" disclosure is what tests see unless they seed events.
    dividends: DividendEventStore
    #: Temp-directory bar cache, read as the trading calendar behind
    #: ``data.trading_days_behind`` (C4). **Empty by default**: the fake price
    #: services never write to it, so unless a test seeds sessions the calendar
    #: has observed nothing and the field is ``null`` -- "cannot judge", which
    #: is the honest answer for a harness with no market history.
    bar_cache: PriceBarCache


@pytest.fixture
def price_service() -> FakePriceService:
    """An empty fake price service; a test seeds it before making a request."""
    return FakePriceService()


@pytest.fixture
def index_service() -> FakePriceService:
    """An empty fake index series service, separate from the security one.

    Kept separate on purpose: an index series must never resolve out of the
    same store as a security's bars, so a test that "works" only because the
    two share a key space would be hiding a real defect.
    """
    return FakePriceService(status=DataStatus.BACKUP)


@pytest.fixture
def fx_provider() -> FxRateProvider:
    """An FX provider that never has a rate; a test swaps in its own if it needs one."""
    return UnavailableFxProvider()


@pytest.fixture
def api_harness(
    tmp_path: Path,
    price_service: FakePriceService,
    index_service: FakePriceService,
    fx_provider: FxRateProvider,
) -> Iterator[ApiHarness]:
    positions = PositionStore(db_path=tmp_path / "positions.db")
    alerts = AlertStore(db_path=tmp_path / "alerts.db")
    settings = SettingsStore(db_path=tmp_path / "settings.db")
    quota = QuotaLedger(db_path=tmp_path / "quota.db")
    dividends = DividendEventStore(db_path=tmp_path / "dividends.db")
    bar_cache = PriceBarCache(db_path=tmp_path / "bars.db")
    valuator = PositionValuator(
        market_services={"TW": price_service},
        fx_provider=fx_provider,
    )

    app.dependency_overrides[get_position_store] = lambda: positions
    app.dependency_overrides[get_alert_store] = lambda: alerts
    app.dependency_overrides[get_settings_store] = lambda: settings
    app.dependency_overrides[get_valuator] = lambda: valuator
    app.dependency_overrides[get_market_resolver] = lambda: {"TW": price_service}
    app.dependency_overrides[get_index_resolver] = lambda: {
        "TW": index_service,
        "US": index_service,
    }
    app.dependency_overrides[get_fx_provider] = lambda: fx_provider
    app.dependency_overrides[get_quota_ledger] = lambda: quota
    app.dependency_overrides[get_dividend_store] = lambda: dividends
    app.dependency_overrides[get_price_bar_cache] = lambda: bar_cache

    with TestClient(app) as test_client:
        yield ApiHarness(
            client=test_client,
            price_service=price_service,
            index_service=index_service,
            positions=positions,
            alerts=alerts,
            settings=settings,
            fx_provider=fx_provider,
            quota=quota,
            dividends=dividends,
            bar_cache=bar_cache,
        )
    app.dependency_overrides.clear()


@pytest.fixture
def api_client(api_harness: ApiHarness) -> TestClient:
    """Just the HTTP client, for tests that do not need the fakes directly."""
    return api_harness.client

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
    get_fx_provider,
    get_market_resolver,
    get_position_store,
    get_settings_store,
    get_valuator,
)
from app.data.providers.fx import FxRateProvider
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
    positions: PositionStore
    alerts: AlertStore
    settings: SettingsStore
    fx_provider: FxRateProvider


@pytest.fixture
def price_service() -> FakePriceService:
    """An empty fake price service; a test seeds it before making a request."""
    return FakePriceService()


@pytest.fixture
def fx_provider() -> FxRateProvider:
    """An FX provider that never has a rate; a test swaps in its own if it needs one."""
    return UnavailableFxProvider()


@pytest.fixture
def api_harness(
    tmp_path: Path, price_service: FakePriceService, fx_provider: FxRateProvider
) -> Iterator[ApiHarness]:
    positions = PositionStore(db_path=tmp_path / "positions.db")
    alerts = AlertStore(db_path=tmp_path / "alerts.db")
    settings = SettingsStore(db_path=tmp_path / "settings.db")
    valuator = PositionValuator(
        market_services={"TW": price_service},
        fx_provider=fx_provider,
    )

    app.dependency_overrides[get_position_store] = lambda: positions
    app.dependency_overrides[get_alert_store] = lambda: alerts
    app.dependency_overrides[get_settings_store] = lambda: settings
    app.dependency_overrides[get_valuator] = lambda: valuator
    app.dependency_overrides[get_market_resolver] = lambda: {"TW": price_service}
    app.dependency_overrides[get_fx_provider] = lambda: fx_provider

    with TestClient(app) as test_client:
        yield ApiHarness(
            client=test_client,
            price_service=price_service,
            positions=positions,
            alerts=alerts,
            settings=settings,
            fx_provider=fx_provider,
        )
    app.dependency_overrides.clear()


@pytest.fixture
def api_client(api_harness: ApiHarness) -> TestClient:
    """Just the HTTP client, for tests that do not need the fakes directly."""
    return api_harness.client

"""API tests for GET /api/portfolio/summary with fake providers (no network)."""

from __future__ import annotations

from datetime import UTC, date, datetime
from decimal import Decimal
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.api.deps import get_position_store, get_valuator
from app.data.interface import DataStatus, Market, PriceBar, ProviderResult
from app.data.providers.fx import FxRate, FxRateProvider, FxRateResult
from app.main import app
from app.portfolio.valuation import PositionValuator, PriceService
from app.positions.models import Currency, PositionInput
from app.positions.store import PositionStore

NOW = datetime(2024, 3, 20, 12, 0, tzinfo=UTC)


class _FakePriceService(PriceService):
    def __init__(self, prices: dict[str, str]) -> None:
        self._prices = prices

    def get_daily_bars(
        self, symbol: str, market: Market, start: date, end: date
    ) -> ProviderResult:
        close = self._prices.get(symbol)
        if close is None:
            return ProviderResult(
                bars=[], status=DataStatus.UNAVAILABLE, as_of=NOW, source="fake"
            )
        bar = PriceBar(
            symbol=symbol,
            market=market,
            date=end,
            open=Decimal(close),
            high=Decimal(close),
            low=Decimal(close),
            close=Decimal(close),
            volume=1,
            currency="TWD" if market == "TW" else "USD",
            as_of=NOW,
            source="fake",
        )
        return ProviderResult(bars=[bar], status=DataStatus.FRESH, as_of=NOW, source="fake")


class _FakeFxProvider(FxRateProvider):
    source_id = "fake_fx"

    def __init__(self, rates: dict[str, list[tuple[date, str]]]) -> None:
        self._rates = rates

    def get_daily_rates(self, pair: str, start: date, end: date) -> FxRateResult:
        raw = [
            FxRate(pair=pair, date=day, rate=Decimal(v), as_of=NOW, source="fake_fx")
            for day, v in self._rates.get(pair, [])
            if start <= day <= end
        ]
        if not raw:
            return FxRateResult(
                rates=[], status=DataStatus.UNAVAILABLE, as_of=NOW, source="fake_fx"
            )
        return FxRateResult(rates=raw, status=DataStatus.FRESH, as_of=NOW, source="fake_fx")


def _make_valuator(
    prices: dict[str, str], fx: dict[str, list[tuple[date, str]]]
) -> PositionValuator:
    shared = _FakePriceService(prices)
    services: dict[Market, PriceService] = {"TW": shared, "US": shared}
    return PositionValuator(
        market_services=services,
        fx_provider=_FakeFxProvider(fx),
        clock=lambda: NOW,
    )


@pytest.fixture
def store(tmp_path: Path) -> PositionStore:
    return PositionStore(db_path=tmp_path / "positions.db")


def _seed(store: PositionStore, *, market: Market, currency: Currency, symbol: str) -> None:
    store.create(
        PositionInput(
            symbol=symbol,
            market=market,
            quantity=Decimal("100") if market == "TW" else Decimal("10"),
            avg_cost=Decimal("500") if market == "TW" else Decimal("100"),
            currency=currency,
            opened_at=date(2024, 1, 15),
            instrument_type="stock",
            note=None,
        ),
        now=NOW,
    )


def _wire(store: PositionStore, valuator: PositionValuator) -> TestClient:
    app.dependency_overrides[get_position_store] = lambda: store
    app.dependency_overrides[get_valuator] = lambda: valuator
    return TestClient(app)


def _teardown() -> None:
    app.dependency_overrides.clear()


def test_summary_no_positions_is_no_data(store: PositionStore) -> None:
    client = _wire(store, _make_valuator({}, {}))
    try:
        body = client.get("/api/portfolio/summary").json()
    finally:
        _teardown()
    assert body["totals"]["status"] == "no_data"
    assert body["positions"] == []
    assert body["totals"]["cost_twd"] == "0"


def test_summary_complete_when_all_positions_valued(store: PositionStore) -> None:
    _seed(store, market="TW", currency="TWD", symbol="2330")
    valuator = _make_valuator({"2330": "550"}, {})
    client = _wire(store, valuator)
    try:
        body = client.get("/api/portfolio/summary").json()
    finally:
        _teardown()
    assert body["totals"]["status"] == "complete"
    assert body["totals"]["unrealized_pnl_twd"] == "5000"
    assert body["totals"]["fx_contribution_twd"] == "0"
    pos = body["positions"][0]
    assert pos["valuation"]["status"] == "ok"
    assert pos["quantity"] == "100"
    assert pos["valuation"]["price"]["data_status"] == "fresh"


def test_summary_partial_totals_cover_only_ok_positions(store: PositionStore) -> None:
    # TW position is priceable; US position has no FX data -> insufficient.
    _seed(store, market="TW", currency="TWD", symbol="2330")
    _seed(store, market="US", currency="USD", symbol="AAPL")
    valuator = _make_valuator({"2330": "550", "AAPL": "110"}, {})  # no FX rates
    client = _wire(store, valuator)
    try:
        body = client.get("/api/portfolio/summary").json()
    finally:
        _teardown()
    assert body["totals"]["status"] == "partial"
    # Totals reflect only the TW position (5000), not the unpriced US one.
    assert body["totals"]["unrealized_pnl_twd"] == "5000"
    statuses = {p["symbol"]: p["valuation"]["status"] for p in body["positions"]}
    assert statuses == {"2330": "ok", "AAPL": "insufficient_data"}


def test_summary_no_data_when_nothing_valued(store: PositionStore) -> None:
    _seed(store, market="US", currency="USD", symbol="AAPL")
    valuator = _make_valuator({"AAPL": "110"}, {})  # price ok but no FX at all
    client = _wire(store, valuator)
    try:
        body = client.get("/api/portfolio/summary").json()
    finally:
        _teardown()
    assert body["totals"]["status"] == "no_data"
    assert body["positions"][0]["valuation"]["status"] == "insufficient_data"


def test_summary_amounts_serialize_as_strings(store: PositionStore) -> None:
    _seed(store, market="TW", currency="TWD", symbol="2330")
    valuator = _make_valuator({"2330": "550"}, {})
    client = _wire(store, valuator)
    try:
        body = client.get("/api/portfolio/summary").json()
    finally:
        _teardown()
    for key in ("cost_twd", "market_value_twd", "unrealized_pnl_twd"):
        assert isinstance(body["totals"][key], str)

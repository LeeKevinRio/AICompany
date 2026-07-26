"""Snapshot assembly, focused on the FX input the risk caps depend on.

A snapshot has no notes list, so the question these tests pin down is whether a
missing or degraded conversion still reaches the reader through ``reason``
instead of quietly turning every price-based cap into ``not_evaluable`` with no
stated cause.
"""

from __future__ import annotations

from datetime import UTC, date, datetime
from decimal import Decimal
from pathlib import Path

import pytest

from app.advice.limits import RiskBudget
from app.alerts.engine import SymbolSnapshot
from app.alerts.snapshot import build_snapshot
from app.data.interface import DataStatus
from app.data.providers.fx import FxRate, FxRateProvider, FxRateResult
from app.portfolio.valuation import PositionValuator
from app.positions.models import PositionInput
from app.positions.store import PositionStore
from tests.api_helpers import (
    FakePriceService,
    UnavailableFxProvider,
    recent_bars,
    trending_closes,
)


class StubFxProvider(FxRateProvider):
    """One flat rate, dated on the requested window's end."""

    source_id = "bank_of_taiwan"

    def __init__(self, rate: str = "31.5") -> None:
        self._rate = Decimal(rate)

    def get_daily_rates(self, pair: str, start: date, end: date) -> FxRateResult:
        now = datetime.now(UTC)
        return FxRateResult(
            rates=[
                FxRate(pair=pair, date=end, rate=self._rate, as_of=now, source=self.source_id)
            ],
            status=DataStatus.FRESH,
            as_of=now,
            source=self.source_id,
        )


@pytest.fixture
def store(tmp_path: Path) -> PositionStore:
    return PositionStore(db_path=tmp_path / "positions.db")


def _price_service(currency: str) -> FakePriceService:
    service = FakePriceService()
    service.seed(
        "2330", recent_bars(trending_closes(60), symbol="2330", currency=currency)
    )
    return service


def _hold(store: PositionStore, currency: str) -> None:
    store.create(
        PositionInput(
            symbol="2330",
            market="TW",
            quantity=Decimal(1000),
            avg_cost=Decimal(600),
            currency=currency,  # type: ignore[arg-type]
            opened_at=date(2024, 1, 2),
            instrument_type="stock",
            note=None,
        )
    )


def _snapshot(
    store: PositionStore, *, currency: str, fx_provider: FxRateProvider | None
) -> SymbolSnapshot:
    service = _price_service(currency)
    return build_snapshot(
        "2330",
        "TW",
        resolver={"TW": service},
        store=store,
        valuator=PositionValuator(
            market_services={"TW": service}, fx_provider=fx_provider or UnavailableFxProvider()
        ),
        budget=RiskBudget(),
        fx_provider=fx_provider,
    )


def test_a_twd_holding_needs_no_rate_and_gains_no_extra_reason(
    store: PositionStore,
) -> None:
    _hold(store, "TWD")
    snapshot = _snapshot(store, currency="TWD", fx_provider=None)
    assert snapshot.reason is None
    weight = next(c for c in snapshot.limits if c.id == "single_position_weight")
    assert weight.status != "not_evaluable"


def test_a_foreign_holding_without_a_provider_says_the_conversion_is_missing(
    store: PositionStore,
) -> None:
    _hold(store, "USD")
    snapshot = _snapshot(store, currency="USD", fx_provider=None)
    reason = snapshot.reason or ""
    assert "無法取得匯率換算" in reason
    assert "不以 1.0 匯率代入" in reason
    weight = next(c for c in snapshot.limits if c.id == "single_position_weight")
    assert weight.status == "not_evaluable"


def test_a_foreign_holding_with_a_rate_states_the_rate_it_used(
    store: PositionStore,
) -> None:
    _hold(store, "USD")
    snapshot = _snapshot(store, currency="USD", fx_provider=StubFxProvider())
    reason = snapshot.reason or ""
    assert "USDTWD" in reason
    assert "31.5" in reason
    assert "fresh" in reason

"""Snapshot assembly, focused on the FX input the risk caps depend on.

A snapshot has no notes list, so the question these tests pin down is whether a
missing or degraded conversion still reaches the reader -- a missing one through
``reason`` (which the engine shows on a skip), an applied one through
``fx_disclosure`` (which the engine puts in the message a fired alert sends) --
instead of quietly turning every price-based cap into ``not_evaluable``, or
quoting a converted figure with no stated provenance.

The last two tests deliberately run the whole chain (snapshot -> engine ->
``AlertEvent.message``): a disclosure that stops anywhere short of the message
is not a disclosure.
"""

from __future__ import annotations

from datetime import UTC, date, datetime
from decimal import Decimal
from pathlib import Path

import pytest

from app.advice.limits import RiskBudget
from app.alerts.engine import EvaluationResult, SymbolSnapshot, evaluate_alerts
from app.alerts.snapshot import build_snapshot
from app.alerts.store import AlertStore
from app.data.interface import DataStatus
from app.data.providers.fx import FxRate, FxRateProvider, FxRateResult
from app.portfolio.valuation import PositionValuator
from app.positions.models import Market, PositionInput
from app.positions.store import PositionStore
from app.services.fx import source_note
from tests.alerts_helpers import add_rule, limit_rule
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


def test_an_applied_rate_carries_its_sources_standing_disclosure(
    store: PositionStore,
) -> None:
    # ADR-0005 F-4. It is a separate field from ``reason`` on purpose: ``reason``
    # is only ever shown on a *skipped* rule, and a rate that was applied is by
    # definition on a snapshot complete enough to fire.
    _hold(store, "USD")
    snapshot = _snapshot(store, currency="USD", fx_provider=StubFxProvider())
    assert snapshot.fx_disclosure == source_note(StubFxProvider.source_id)
    assert "即期買賣中點" in (snapshot.fx_disclosure or "")


def test_a_twd_holding_is_not_given_an_fx_disclosure_it_did_not_use(
    store: PositionStore,
) -> None:
    # No conversion happened, so there is no rate methodology to disclose;
    # padding every alert with the sentence would train the reader to skip it.
    _hold(store, "TWD")
    snapshot = _snapshot(store, currency="TWD", fx_provider=StubFxProvider())
    assert snapshot.fx_disclosure is None
    assert snapshot.reason is None


def test_an_unusable_rate_says_so_without_claiming_a_methodology(
    store: PositionStore,
) -> None:
    # The disclosure qualifies a rate that was applied; when none was, nothing
    # was converted, so the reason must stay on the missing conversion instead.
    _hold(store, "USD")
    snapshot = _snapshot(store, currency="USD", fx_provider=UnavailableFxProvider())
    assert snapshot.fx_disclosure is None
    assert "無法取得匯率換算" in (snapshot.reason or "")


# --- End to end: snapshot -> engine -> the message a user receives ------------


def _fire_limit_alert(
    positions: PositionStore, alerts: AlertStore, *, currency: str, limit_id: str
) -> EvaluationResult:
    """Run a real ``risk_limit_breach`` tick over the real snapshot builder."""
    service = _price_service(currency)
    valuator = PositionValuator(
        market_services={"TW": service}, fx_provider=StubFxProvider()
    )
    # A deliberately tight loss budget: the point of these two tests is the
    # wording of a *fired* message, and the cap has to breach for there to be
    # one. The default 1% happens not to be crossed by this fixture's ATR.
    budget = RiskBudget(max_loss_per_trade=0.001)
    add_rule(alerts, limit_rule(limit_id=limit_id))

    def load(symbol: str, market: Market) -> SymbolSnapshot:
        return build_snapshot(
            symbol,
            market,
            resolver={"TW": service},
            store=positions,
            valuator=valuator,
            budget=budget,
            fx_provider=StubFxProvider(),
        )

    return evaluate_alerts(alerts, load, now=datetime.now(UTC))


def test_a_fired_per_trade_loss_alert_on_a_foreign_holding_discloses_the_rate(
    store: PositionStore, tmp_path: Path
) -> None:
    # The whole chain, because the defect this pins was invisible at either end
    # alone: the snapshot carried the sentence, the engine read a different
    # field, and the message that actually reached Discord/Telegram quoted a
    # loss percentage computed through ``ctx.fx_to_twd`` with no provenance.
    _hold(store, "USD")
    alerts = AlertStore(db_path=tmp_path / "alerts.db")
    result = _fire_limit_alert(store, alerts, currency="USD", limit_id="per_trade_loss")

    assert [outcome.status for outcome in result.outcomes] == ["fired"]
    message = result.events[0].message
    assert "單筆最大可承受虧損" in message
    assert source_note(StubFxProvider.source_id) in message
    # And the same text is what the feed and the push channels read.
    assert alerts.list_events()[0].message == message


def test_a_fired_alert_on_a_twd_holding_stays_free_of_fx_wording(
    store: PositionStore, tmp_path: Path
) -> None:
    _hold(store, "TWD")
    alerts = AlertStore(db_path=tmp_path / "alerts.db")
    result = _fire_limit_alert(store, alerts, currency="TWD", limit_id="per_trade_loss")

    assert [outcome.status for outcome in result.outcomes] == ["fired"]
    message = result.events[0].message
    assert "單筆最大可承受虧損" in message
    assert "匯率" not in message

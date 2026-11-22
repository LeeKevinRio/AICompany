"""F-1b x cap 3: a holding left unvalued by a bad FX rate skips a gross-exposure alert.

Risk RC-656 point 2. An FX rate of 0 or below is no rate (F-1b,
``app.data.price_guard.usable_rate``), so a USD holding on such a rate stays
unvalued and the book is not fully valued. Cap 3 (gross exposure) then reports
``not_evaluable`` instead of a ratio over a numerator that is missing a holding
(``app.advice.limits._check_gross_exposure``), and a ``risk_limit_breach`` rule
watching cap 3 alone has nothing but unevaluated caps, which the engine turns
into a **skip** (``app.alerts.engine._limit_outcome``): no event, no push.

The tick under test is the scheduler's own (:func:`app.scheduler.evaluate_alerts_tick`)
with every provider pointed at a local fake, so the push decision is the
production one. The net worth is set so low that the *valued* holding alone is
far over the cap: a guard that let an incomplete book through would fire here,
and the control with a good rate shows that it does.
"""

from __future__ import annotations

from datetime import UTC, date, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any, ClassVar

import pytest

from app import scheduler as scheduler_module
from app.advice.limits import GROSS_EXPOSURE_INCOMPLETE_BOOK_DETAIL, LIMIT_IDS, LIMIT_NAMES
from app.alerts.engine import EvaluationResult, SymbolSnapshot, evaluate_alerts
from app.alerts.models import AlertEvent
from app.alerts.snapshot import build_snapshot
from app.alerts.store import AlertStore
from app.data.interface import DataStatus
from app.data.providers.fx import FxRate, FxRateProvider, FxRateResult
from app.kelly.store import KellyInputStore
from app.portfolio.valuation import PositionValuator
from app.positions.models import Market, PositionInput
from app.positions.store import PositionStore
from app.settings.models import AppSettings, NetWorthSettings
from app.settings.store import SettingsStore
from tests.alerts_helpers import add_rule, limit_rule
from tests.api_helpers import FakePriceService, recent_bars, trending_closes

TWD_SYMBOL = "2330"
USD_SYMBOL = "AAPL"
#: Far below the TWD holding's own market value (1000 x ~500): the valued part
#: of the book alone is several times the default 100% cap.
NET_WORTH_TWD = 100_000.0
GOOD_RATE = Decimal("31.5")
#: The rates a source can hand back through a validated ``FxRate`` (F-1b KF-6).
BAD_RATES = [
    pytest.param(Decimal("0"), id="zero"),
    pytest.param(Decimal("-1"), id="negative"),
]
#: The rule may sit on either holding: cap 3 is a whole-book cap.
RULE_SYMBOLS = [
    pytest.param((TWD_SYMBOL, "TW"), id="rule-on-valued-twd"),
    pytest.param((USD_SYMBOL, "US"), id="rule-on-unvalued-usd"),
]
#: Cap 3 is "第 3 條" by its 1-based position in ``LIMIT_IDS``.
GROSS_EXPOSURE = LIMIT_IDS[2]
#: The engine's all-unevaluated skip for a rule watching cap 3 alone, pinned whole.
SKIP_REASON = f"監看的上限（{LIMIT_NAMES[GROSS_EXPOSURE]}）缺少輸入，無法判定是否違反。"


class _FlatFx(FxRateProvider):
    """One rate for any window, dated on the window's end."""

    source_id: ClassVar[str] = "bank_of_taiwan"

    def __init__(self, rate: Decimal) -> None:
        self._rate = rate

    def get_daily_rates(self, pair: str, start: date, end: date) -> FxRateResult:
        now = datetime.now(UTC)
        return FxRateResult(
            rates=[FxRate(pair=pair, date=end, rate=self._rate, as_of=now, source=self.source_id)],
            status=DataStatus.FRESH,
            as_of=now,
            source=self.source_id,
        )


def _hold(store: PositionStore, symbol: str, market: Market, currency: str) -> None:
    store.create(
        PositionInput(
            symbol=symbol,
            market=market,
            quantity=Decimal(1000),
            avg_cost=Decimal(500) if currency == "TWD" else Decimal(100),
            currency=currency,  # type: ignore[arg-type]
            opened_at=date(2024, 1, 2),
            instrument_type="stock",
            note=None,
        )
    )


def _wire(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, rate: Decimal
) -> tuple[AlertStore, list[EvaluationResult], list[list[AlertEvent]]]:
    """Point the scheduler's providers at a two-holding book on ``rate``.

    Returns the alert store, every tick's :class:`EvaluationResult` and every
    batch the tick handed to ``notify_all`` (the push).
    """
    tw = FakePriceService(
        {TWD_SYMBOL: recent_bars(trending_closes(200, start=500.0), symbol=TWD_SYMBOL)}
    )
    us = FakePriceService(
        {USD_SYMBOL: recent_bars(trending_closes(200, start=100.5), symbol=USD_SYMBOL, market="US")}
    )
    markets: dict[Market, FakePriceService] = {"TW": tw, "US": us}
    fx = _FlatFx(rate)

    positions = PositionStore(db_path=tmp_path / "positions.db")
    _hold(positions, TWD_SYMBOL, "TW", "TWD")
    _hold(positions, USD_SYMBOL, "US", "USD")
    alerts = AlertStore(db_path=tmp_path / "alerts.db")
    settings = SettingsStore(db_path=tmp_path / "settings.db")
    settings.save(
        AppSettings(
            net_worth=NetWorthSettings(
                total_net_worth_twd=NET_WORTH_TWD, updated_at=datetime.now(UTC).isoformat()
            )
        )
    )
    # Webhooks on (the default), so only "nothing fired" can keep the push quiet.
    assert settings.load().alerts.notify_webhooks is True
    kelly = KellyInputStore(db_path=tmp_path / "kelly.db")

    monkeypatch.setattr(scheduler_module, "get_position_store", lambda: positions)
    monkeypatch.setattr(scheduler_module, "get_alert_store", lambda: alerts)
    monkeypatch.setattr(scheduler_module, "get_settings_store", lambda: settings)
    monkeypatch.setattr(scheduler_module, "get_market_resolver", lambda: dict(markets))
    monkeypatch.setattr(
        scheduler_module,
        "get_valuator",
        lambda: PositionValuator(market_services=dict(markets), fx_provider=fx),
    )
    monkeypatch.setattr(scheduler_module, "get_fx_provider", lambda: fx)
    monkeypatch.setattr(scheduler_module, "get_kelly_input_store", lambda: kelly)

    results: list[EvaluationResult] = []
    pushed: list[list[AlertEvent]] = []

    def recording_evaluate(*args: Any, **kwargs: Any) -> EvaluationResult:
        result = evaluate_alerts(*args, **kwargs)
        results.append(result)
        return result

    def recording_notify(events: list[AlertEvent], **kwargs: Any) -> list[Any]:
        pushed.append(list(events))
        return []

    monkeypatch.setattr(scheduler_module, "evaluate_alerts", recording_evaluate)
    monkeypatch.setattr(scheduler_module, "notify_all", recording_notify)
    return alerts, results, pushed


@pytest.mark.parametrize("rule_on", RULE_SYMBOLS)
@pytest.mark.parametrize("bad", BAD_RATES)
def test_a_bad_rate_skips_a_rule_watching_only_cap_3_and_pushes_nothing(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    bad: Decimal,
    rule_on: tuple[str, Market],
) -> None:
    alerts, results, pushed = _wire(tmp_path, monkeypatch, bad)
    symbol, market = rule_on
    rule = add_rule(alerts, limit_rule(limit_id=GROSS_EXPOSURE, symbol=symbol, market=market))

    assert scheduler_module.evaluate_alerts_tick() == 0

    [result] = results
    [outcome] = result.outcomes
    assert outcome.rule_id == rule.id
    assert outcome.status == "skipped"
    # Pinned whole: cap 3 reads no price, so no FX sentence is appended as a cause.
    assert outcome.reason == SKIP_REASON
    assert outcome.event is None
    assert result.events == []
    assert alerts.list_events() == []
    assert pushed == []


@pytest.mark.parametrize("bad", BAD_RATES)
def test_the_skip_is_the_incomplete_book_not_a_missing_net_worth(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, bad: Decimal
) -> None:
    # The cap's own detail names the cause, so the skip above cannot be passing
    # for a reason other than the unvalued holding (no net worth, empty book).
    alerts, _, _ = _wire(tmp_path, monkeypatch, bad)
    loads: list[SymbolSnapshot] = []

    def spy(*args: Any, **kwargs: Any) -> SymbolSnapshot:
        snap = build_snapshot(*args, **kwargs)
        loads.append(snap)
        return snap

    monkeypatch.setattr(scheduler_module, "build_snapshot", spy)
    add_rule(alerts, limit_rule(limit_id=GROSS_EXPOSURE, symbol=TWD_SYMBOL, market="TW"))

    scheduler_module.evaluate_alerts_tick()

    [snap] = loads
    [check] = [c for c in snap.limits if c.id == GROSS_EXPOSURE]
    assert check.index == 3
    assert check.status == "not_evaluable"
    assert check.detail.startswith(GROSS_EXPOSURE_INCOMPLETE_BOOK_DETAIL)


@pytest.mark.parametrize("rule_on", RULE_SYMBOLS)
def test_control_the_same_book_on_a_good_rate_fires_cap_3_and_pushes_it(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, rule_on: tuple[str, Market]
) -> None:
    # Same book, same net worth, same rule: with every holding valued the cap is
    # crossed, so the skip above is the bad rate's doing and not the fixture's.
    alerts, results, pushed = _wire(tmp_path, monkeypatch, GOOD_RATE)
    symbol, market = rule_on
    rule = add_rule(alerts, limit_rule(limit_id=GROSS_EXPOSURE, symbol=symbol, market=market))

    assert scheduler_module.evaluate_alerts_tick() == 1

    [result] = results
    [outcome] = result.outcomes
    assert outcome.rule_id == rule.id
    assert outcome.status == "fired"
    assert outcome.event is not None
    assert f"第 3 條（{LIMIT_NAMES[GROSS_EXPOSURE]}）" in outcome.event.message
    assert [[event.id for event in batch] for batch in pushed] == [[outcome.event.id]]

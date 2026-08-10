"""The fourth look-ahead guard: back-adjustment must not leak the future.

Back-adjustment is the one place in this backtester where a *later* fact (an
ex-dividend event) touches an *earlier* bar, so it gets its own detection suite
rather than riding on the engine's structural guarantee.

What is proven here, in order of strength:

1. **Containment.** The window a strategy sees on day ``t``, built from the
   fully back-adjusted series, equals the strictly point-in-time series (built
   from events up to ``t`` only) times one positive constant. That is the exact
   claim ``app.dividends.adjust`` makes; here it is measured, not asserted in
   prose.
2. **Decision equivalence.** Every shipped strategy returns the *same weight*
   on every day under both constructions. Whatever the constant is, it never
   reaches a decision.
3. **Teeth.** A deliberately level-dependent strategy (a hard-coded price
   threshold) *does* differ between the two constructions -- so test 2 is
   discriminating, not vacuous, and the documented caveat "do not condition on
   the absolute level of an adjusted price" is shown to be a real hazard.
4. **The engine's own guards still hold** on an adjusted series: the shift
   sensitivity detector from ``tests/test_lookahead_detection.py`` is rerun
   against adjusted bars.
"""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta
from decimal import Decimal

import numpy as np
import pandas as pd
import pytest

from app.backtest.costs import CostModel
from app.backtest.engine import run_backtest
from app.backtest.strategies import STRATEGY_IDS, build_strategy
from app.data.interface import PriceBar
from app.dividends.adjust import back_adjust_bars
from app.dividends.models import DividendEvent
from app.signals.frame import CLOSE, bars_to_frame
from tests.signals_helpers import bars_from_closes

AS_OF = datetime(2026, 8, 10, 12, 0, tzinfo=UTC)
BASE_DATE = date(2024, 1, 1)

ZERO_COST = CostModel(
    tw_broker_fee_rate=0.0,
    tw_tax_rate_stock=0.0,
    tw_tax_rate_etf=0.0,
    us_sell_regulatory_fee_rate=0.0,
    slippage_bps=0.0,
)

#: Same threshold the engine's look-ahead suite uses for "materially different".
SHIFT_SENSITIVITY_THRESHOLD = 0.01


def _cyclical_closes(bars: int = 200) -> list[float]:
    """A path with real reversals so every shipped strategy actually trades."""
    t = np.arange(bars, dtype="float64")
    return list(100.0 + 20.0 * np.sin(2.0 * np.pi * t / 45.0) + 0.05 * t)


def _event_on(offset: int, bars: list[PriceBar], *, payout: str) -> DividendEvent:
    """A dividend on bar ``offset``, sized off the previous bar's real close."""
    previous_close = bars[offset - 1].close
    cash = Decimal(payout)
    return DividendEvent(
        symbol=bars[0].symbol,
        market="TW",
        ex_date=BASE_DATE + timedelta(days=offset),
        previous_close=previous_close,
        reference_price=previous_close - cash,
        cash_dividend=cash,
        source="test",
        as_of=AS_OF,
    )


def _series() -> tuple[list[PriceBar], list[DividendEvent]]:
    bars = bars_from_closes(_cyclical_closes())
    events = [
        _event_on(60, bars, payout="4.0"),
        _event_on(120, bars, payout="3.5"),
        _event_on(170, bars, payout="2.0"),
    ]
    return bars, events


def _point_in_time_window(
    bars: list[PriceBar], events: list[DividendEvent], t: int
) -> list[PriceBar]:
    """The window as it could honestly have been built on day ``t``.

    Only events with an ex-date at or before ``bars[t].date`` exist yet;
    ``back_adjust_bars`` drops anything after the last bar it is given, so
    slicing the bars is enough to make the construction forward-only.
    """
    return back_adjust_bars(bars[: t + 1], events).bars


def test_visible_window_differs_from_the_point_in_time_one_only_by_a_constant() -> None:
    bars, events = _series()
    full = back_adjust_bars(bars, events).bars

    for t in (30, 61, 90, 121, 150, 171, len(bars) - 1):
        pit = _point_in_time_window(bars, events, t)
        ratios = [
            float(full[i].close) / float(pit[i].close) for i in range(t + 1)
        ]
        # One constant for the whole visible window: max/min == 1 to numerical
        # precision (the tolerance covers only the 1e-6 price quantum, i.e. a
        # ~1e-8 relative rounding per bar). Anything larger would mean a future
        # event reshaped the *relative* history -- the leak this test forbids.
        assert max(ratios) / min(ratios) == pytest.approx(1.0, abs=1e-7), (
            f"day {t}: adjusted window is not a constant multiple of the "
            "point-in-time window; a future dividend leaked into its shape"
        )


def test_the_constant_is_not_trivially_one_before_the_last_event() -> None:
    """Guards the test above from passing because there is nothing to contain."""
    bars, events = _series()
    full = back_adjust_bars(bars, events).bars
    pit = _point_in_time_window(bars, events, 30)
    ratio = float(full[0].close) / float(pit[0].close)
    assert ratio < 0.99, "no future events applied -- the containment test would be vacuous"


@pytest.mark.parametrize("strategy_id", STRATEGY_IDS)
def test_each_shipped_strategy_decides_identically_under_both_constructions(
    strategy_id: str,
) -> None:
    bars, events = _series()
    strategy = build_strategy(strategy_id)
    full_frame = bars_to_frame(back_adjust_bars(bars, events).bars)

    decisions_differ = 0
    for t in range(len(bars)):
        from_full = strategy(full_frame.iloc[: t + 1].copy())
        from_pit = strategy(bars_to_frame(_point_in_time_window(bars, events, t)))
        if from_full != pytest.approx(from_pit, abs=1e-12):
            decisions_differ += 1
    assert decisions_differ == 0, (
        f"{strategy_id} decided differently on {decisions_differ} day(s) when the "
        "series carried future dividend factors; it is reading price levels"
    )


def test_a_level_dependent_strategy_does_differ_so_the_guard_has_teeth() -> None:
    """A hard-coded price threshold *is* sensitive to the constant -- by design.

    This is the hazard ``app.dividends.adjust`` documents. Showing it here means
    the equivalence test above discriminates instead of always passing.
    """
    bars, events = _series()
    full_frame = bars_to_frame(back_adjust_bars(bars, events).bars)

    def below_a_fixed_price(window: pd.DataFrame) -> float:
        return 1.0 if float(window[CLOSE].iloc[-1]) < 100.0 else 0.0

    differences = 0
    for t in range(len(bars)):
        from_full = below_a_fixed_price(full_frame.iloc[: t + 1].copy())
        from_pit = below_a_fixed_price(bars_to_frame(_point_in_time_window(bars, events, t)))
        if from_full != from_pit:
            differences += 1
    assert differences > 0


def test_shift_sensitivity_detector_still_fires_on_an_adjusted_series() -> None:
    """The engine's own look-ahead guard, rerun on adjusted bars."""
    bars, events = _series()
    frame = bars_to_frame(back_adjust_bars(bars, events).bars)
    closes = [float(value) for value in frame[CLOSE]]
    future = np.asarray([*closes[1:], closes[-1]], dtype="float64")
    strategy = build_strategy("ma_cross")

    def leaking(window: pd.DataFrame) -> float:
        leaked = window.copy()
        leaked[CLOSE] = future[: len(window)]
        return strategy(leaked)

    base = run_backtest(frame, strategy, initial_cash=10_000.0, cost_model=ZERO_COST)
    assert base.trades
    leaked = run_backtest(frame, leaking, initial_cash=10_000.0, cost_model=ZERO_COST)
    rel_change = abs(leaked.equity_curve[-1] - base.equity_curve[-1]) / base.equity_curve[-1]
    assert rel_change > SHIFT_SENSITIVITY_THRESHOLD


def test_adjustment_raises_measured_return_and_leaves_the_present_price_alone() -> None:
    """The A2 problem, stated as a measurement: the raw series understates."""
    bars, events = _series()
    adjustment = back_adjust_bars(bars, events)

    raw_total = float(bars[-1].close / bars[0].close - 1)
    adjusted_total = float(adjustment.bars[-1].close / adjustment.bars[0].close - 1)
    assert adjusted_total > raw_total
    # The newest bar is the anchor: still the real, tradeable price.
    assert adjustment.bars[-1].close == bars[-1].close
    assert len(adjustment.bars) == len(bars)
    assert [bar.date for bar in adjustment.bars] == [bar.date for bar in bars]

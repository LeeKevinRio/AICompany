"""Engine golden tests and point-in-time structural guarantees."""

from __future__ import annotations

import math

import pandas as pd
import pytest

from app.backtest.costs import CostModel
from app.backtest.engine import run_backtest
from app.signals.frame import bars_to_frame
from tests.signals_helpers import bars_from_closes

TOL = 1e-9

ZERO_COST = CostModel(
    tw_broker_fee_rate=0.0,
    tw_tax_rate_stock=0.0,
    tw_tax_rate_etf=0.0,
    us_sell_regulatory_fee_rate=0.0,
    slippage_bps=0.0,
)


def _always_invested(_window: pd.DataFrame) -> float:
    return 1.0


def test_golden_buy_and_hold_zero_cost() -> None:
    # Prices 100 ->110 ->121, fully invested, no costs. Equity tracks price:
    # buy 100 shares at 100 (cash 0); then equity = 100 * price.
    frame = bars_to_frame(bars_from_closes([100.0, 110.0, 121.0]))
    result = run_backtest(frame, _always_invested, initial_cash=10_000.0, cost_model=ZERO_COST)
    assert result.equity_curve == [10_000.0, 11_000.0, 12_100.0]
    # One buy on day 0, then no further trades (weight already met).
    assert len(result.trades) == 1
    assert result.trades[0].side == "buy"


def test_golden_round_trip_with_tw_costs() -> None:
    # Buy day 0, liquidate day 1. Hand-computed in the module docstring math:
    #   day0 buy 100 @100, fee 14.25 -> cash -14.25, shares 100
    #   day1 sell 100 @110, fee 15.675 + tax 33 = 48.675
    #   end equity = -14.25 + 11000 - 48.675 = 10937.075
    #   realized pnl = (11000-48.675) - (10000+14.25) = 937.075 == equity change
    frame = bars_to_frame(bars_from_closes([100.0, 110.0]))

    def strat(window: pd.DataFrame) -> float:
        return 1.0 if len(window) == 1 else 0.0

    result = run_backtest(frame, strat, initial_cash=10_000.0, cost_model=CostModel())
    assert math.isclose(result.equity_curve[0], 9_985.75, abs_tol=TOL)
    assert math.isclose(result.equity_curve[-1], 10_937.075, abs_tol=1e-6)
    closing = [t for t in result.trades if t.realized_pnl is not None]
    assert len(closing) == 1
    assert math.isclose(closing[0].realized_pnl or 0.0, 937.075, abs_tol=1e-6)
    # Invariant: flat book at end -> realized pnl == equity change.
    assert math.isclose(
        (closing[0].realized_pnl or 0.0),
        result.equity_curve[-1] - result.initial_cash,
        abs_tol=1e-6,
    )


def test_flat_strategy_never_trades() -> None:
    frame = bars_to_frame(bars_from_closes([100.0, 90.0, 120.0]))
    result = run_backtest(frame, lambda _w: 0.0, initial_cash=5_000.0, cost_model=CostModel())
    assert result.trades == []
    assert result.equity_curve == [5_000.0, 5_000.0, 5_000.0]


def test_window_is_point_in_time_only() -> None:
    # Each day the strategy must see exactly the bars up to and including today,
    # and never a future one.
    frame = bars_to_frame(bars_from_closes([10.0, 11.0, 12.0, 13.0]))
    seen_lengths: list[int] = []
    last_dates: list[pd.Timestamp] = []

    def spy(window: pd.DataFrame) -> float:
        seen_lengths.append(len(window))
        last_dates.append(window.index[-1])
        return 0.0

    run_backtest(frame, spy, cost_model=ZERO_COST)
    assert seen_lengths == [1, 2, 3, 4]
    assert last_dates == list(frame.index)


def test_strategy_cannot_reach_a_future_bar() -> None:
    # A strategy that tries to index tomorrow's bar finds it absent (the slice
    # simply does not contain it): look-ahead is impossible, not merely discouraged.
    frame = bars_to_frame(bars_from_closes([10.0, 11.0, 12.0]))

    def peeking(window: pd.DataFrame) -> float:
        _ = window.iloc[len(window)]  # index one past the end -> future bar
        return 1.0

    with pytest.raises(IndexError):
        run_backtest(frame, peeking, cost_model=ZERO_COST)


def test_window_mutation_does_not_leak_into_engine() -> None:
    # The window is a copy; a misbehaving strategy cannot corrupt engine state.
    frame = bars_to_frame(bars_from_closes([10.0, 11.0, 12.0]))

    def mutating(window: pd.DataFrame) -> float:
        window["close"] = 999_999.0
        return 0.0

    result = run_backtest(frame, mutating, cost_model=ZERO_COST)
    assert result.close == [10.0, 11.0, 12.0]


def test_empty_frame_yields_empty_result() -> None:
    empty = bars_to_frame([])
    result = run_backtest(empty, _always_invested)
    assert result.equity_curve == []
    assert result.trades == []

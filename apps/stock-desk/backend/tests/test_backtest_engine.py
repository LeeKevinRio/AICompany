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


# Behaviour pins (風控 2026-10-26 constraint C-3, item 5-BT). The backtest report's standing
# disclosure says, verbatim:
#   「訊號與成交用同一根收盤價：收盤價要到收盤才知道，實際下單做不到這樣成交。」
#   「滑價設為 0 bps：滑價是實際成交價與預期價的差距，這裡沒有計入。」
# (the second one when the configured slippage is 0)
# Both sentences describe the engine as it is today. If the engine starts to fill at the next
# bar's open (t+1), or the default slippage stops being 0, the frontend sentences in
# ``frontend/app/lib/riskRemediationWording.ts`` (5-BT heading and both points, plus the chart
# caption) must be rewritten in the same PR and sent back to risk review (failure condition T5).


def test_a_signal_on_bar_t_fills_at_the_close_of_the_same_bar_t() -> None:
    # The strategy only decides to buy once it sees the 110 close (bar 1). The fill is at that very
    # bar's close -- not at the next bar's price (121) and not at an open (the frame has none).
    frame = bars_to_frame(bars_from_closes([100.0, 110.0, 121.0]))

    def buy_after_seeing_110(window: pd.DataFrame) -> float:
        return 1.0 if float(window["close"].iloc[-1]) >= 110.0 else 0.0

    result = run_backtest(frame, buy_after_seeing_110, initial_cash=11_000.0, cost_model=ZERO_COST)
    assert len(result.trades) == 1
    fill = result.trades[0]
    assert fill.bar_index == 1
    assert fill.date == result.dates[1]
    assert fill.price == 110.0  # the signal bar's own close
    assert fill.price != 121.0  # not the next bar
    assert math.isclose(fill.shares, 100.0, abs_tol=TOL)


def test_every_fill_price_is_the_close_of_its_own_bar() -> None:
    closes = [100.0, 104.0, 99.0, 107.0, 111.0]
    frame = bars_to_frame(bars_from_closes(closes))

    def flip(window: pd.DataFrame) -> float:
        return 1.0 if len(window) % 2 == 1 else 0.0

    result = run_backtest(frame, flip, initial_cash=10_000.0, cost_model=ZERO_COST)
    assert len(result.trades) >= 3
    for trade in result.trades:
        assert trade.price == closes[trade.bar_index]
        assert trade.date == result.dates[trade.bar_index]


def test_the_default_slippage_is_zero_and_a_zero_slippage_prices_nothing() -> None:
    from app.settings.models import CostModelSettings

    assert CostModel().slippage_bps == 0.0
    assert CostModelSettings().slippage_bps == 0.0
    free = CostModel(
        tw_broker_fee_rate=0.0, tw_tax_rate_stock=0.0, tw_tax_rate_etf=0.0, slippage_bps=0.0
    )
    assert (
        free.trade_cost(notional=1_000_000.0, side="buy", market="TW", instrument_type="stock")
        == 0.0
    )
    # And a positive setting does add cost, so the frontend's "{n} bps" variant is a real case.
    assert CostModel(
        tw_broker_fee_rate=0.0, tw_tax_rate_stock=0.0, tw_tax_rate_etf=0.0, slippage_bps=10.0
    ).trade_cost(
        notional=1_000_000.0, side="buy", market="TW", instrument_type="stock"
    ) == pytest.approx(1_000.0)


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

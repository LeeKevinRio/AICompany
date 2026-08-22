"""Report tests: all standard fields present, Buy & Hold peer, IS/OOS separated."""

from __future__ import annotations

import math

import pandas as pd

from app.backtest.costs import CostModel
from app.backtest.engine import BacktestResult, run_backtest
from app.backtest.report import build_segment_report, walk_forward_report
from app.backtest.splits import walk_forward_splits
from app.signals.frame import bars_to_frame
from tests.signals_helpers import bars_from_closes

ZERO_COST = CostModel(
    tw_broker_fee_rate=0.0,
    tw_tax_rate_stock=0.0,
    tw_tax_rate_etf=0.0,
    us_sell_regulatory_fee_rate=0.0,
    slippage_bps=0.0,
)


def _trending_result(n: int = 40) -> BacktestResult:
    frame = bars_to_frame(bars_from_closes([100.0 * (1.01**i) for i in range(n)]))
    return run_backtest(frame, lambda _w: 1.0, initial_cash=100_000.0, cost_model=ZERO_COST)


def test_report_has_all_standard_fields_and_benchmark() -> None:
    report = build_segment_report(_trending_result())
    strat = report.strategy
    # Backtest-protocol standard block: none of these may be silently missing.
    for field in (
        "cagr",
        "annualized_volatility",
        "sharpe",
        "sortino",
        "max_drawdown",
        "max_drawdown_peak_date",
        "max_drawdown_trough_date",
        "win_rate",
        "profit_factor",
        "num_trades",
        "turnover",
    ):
        assert hasattr(strat, field)
    # Buy & Hold peer is always present.
    assert report.buy_and_hold.observations == strat.observations


def test_buy_and_hold_matches_fully_invested_zero_cost_strategy() -> None:
    # A cost-free always-invested strategy IS buy-and-hold, so their equity end
    # points must coincide.
    result = _trending_result()
    report = build_segment_report(result)
    assert report.strategy.end_equity is not None
    assert report.buy_and_hold.end_equity is not None
    assert math.isclose(report.strategy.end_equity, report.buy_and_hold.end_equity, rel_tol=1e-9)


def test_cagr_positive_on_uptrend_and_drawdown_nonpositive() -> None:
    report = build_segment_report(_trending_result())
    assert report.strategy.cagr is not None and report.strategy.cagr > 0
    assert report.strategy.max_drawdown is not None and report.strategy.max_drawdown <= 0


def test_walk_forward_report_keeps_in_and_out_of_sample_separate() -> None:
    result = _trending_result(60)
    folds = walk_forward_splits(60, train_size=20, test_size=10)
    report = walk_forward_report(result, folds)
    # In-sample is the initial training block; out-of-sample is the stitched
    # test region -- different, non-overlapping spans.
    assert report.in_sample.strategy.start_date == result.dates[0]
    assert report.out_of_sample.strategy.start_date == result.dates[folds[0].test_start]
    assert report.out_of_sample.strategy.end_date == result.dates[folds[-1].test_stop - 1]
    assert report.in_sample.strategy.label.startswith("in_sample")
    assert report.out_of_sample.strategy.label.startswith("out_of_sample")


def test_win_rate_and_profit_factor_from_round_trips() -> None:
    # Buy low, sell high once: a single winning closing trade -> win rate 1.0,
    # and no losses so profit factor is undefined (None), reported honestly.
    frame = bars_to_frame(bars_from_closes([100.0, 120.0]))

    def strat(window: pd.DataFrame) -> float:
        return 1.0 if len(window) == 1 else 0.0

    result = run_backtest(frame, strat, initial_cash=10_000.0, cost_model=ZERO_COST)
    report = build_segment_report(result)
    assert report.strategy.num_closing_trades == 1
    assert report.strategy.win_rate == 1.0
    assert report.strategy.profit_factor is None


def _one_holding_period_result(bars: int = 30) -> BacktestResult:
    """Fully invested until the last bar, with real costs.

    The cost drag leaves cash slightly negative, so the engine trims a sliver
    every bar: many closing *fills*, one holding *round trip*.
    """
    closes = [100.0 * (1.01**i) for i in range(bars)]
    frame = bars_to_frame(bars_from_closes(closes))

    def long_then_flat(window: pd.DataFrame) -> float:
        return 1.0 if len(window) < bars else 0.0

    return run_backtest(frame, long_then_flat, initial_cash=100_000.0, cost_model=CostModel())


def test_round_trip_layer_is_reported_beside_the_fill_layer() -> None:
    report = build_segment_report(_one_holding_period_result())
    strat = report.strategy
    # The fill layer counts every sliver; the round-trip layer counts the one
    # holding period they all belong to. Both are reported, neither replaces the
    # other, and the fill-layer numbers keep the meaning they always had.
    assert strat.num_closing_trades > 1
    assert strat.win_rate == 1.0
    assert strat.round_trip_win_rate == 1.0
    assert strat.round_trip_payoff_ratio is None  # no losing round trip: undefined
    # Buy & Hold trades nothing, so it has no round trip to rate.
    assert report.buy_and_hold.round_trip_win_rate is None
    assert report.buy_and_hold.round_trip_payoff_ratio is None


def test_a_round_trip_straddling_the_segment_is_not_credited_to_it() -> None:
    result = _one_holding_period_result()
    folds = walk_forward_splits(30, train_size=10, test_size=5)
    oos = walk_forward_report(result, folds).out_of_sample.strategy
    # The single round trip opened before the out-of-sample window, so the
    # window has no completed round trip of its own -- while the fill layer
    # still rates the fragments that happen to fall inside it. That gap is the
    # reason the Kelly inputs read the round-trip layer.
    assert oos.round_trip_win_rate is None
    assert oos.round_trip_payoff_ratio is None
    assert oos.win_rate == 1.0
    assert oos.num_closing_trades > 0


def test_empty_result_reports_zero_observations() -> None:
    empty = bars_to_frame([])
    result = run_backtest(empty, lambda _w: 1.0)
    report = build_segment_report(result)
    assert report.strategy.observations == 0
    assert report.strategy.cagr is None

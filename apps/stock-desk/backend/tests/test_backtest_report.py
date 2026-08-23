"""Report tests: all standard fields present, Buy & Hold peer, IS/OOS separated."""

from __future__ import annotations

import math

import pandas as pd

from app.backtest.costs import CostModel
from app.backtest.engine import BacktestResult, run_backtest
from app.backtest.episodes import attribute_round_trips
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
    # Buy low, sell high once: a single winning round trip -> win rate 1.0,
    # and no losing round trip so profit factor is undefined (None), reported
    # honestly. (C8: the statistical unit is the round trip; this run has
    # exactly one, which is also its one closing fill.)
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


def test_win_rate_counts_round_trips_not_sliver_fills() -> None:
    # C8 fix (was: fill-layer win_rate beside the round-trip layer). The engine
    # trims a sliver every bar, so this run has many closing *fills* but one
    # holding *round trip* -- and the rate now counts the round trip. The fill
    # count keeps its original meaning (a settlement count) and stays reported.
    report = build_segment_report(_one_holding_period_result())
    strat = report.strategy
    assert strat.num_closing_trades > 1
    assert strat.win_rate == 1.0
    assert strat.round_trip_win_rate == 1.0
    assert strat.round_trip_payoff_ratio is None  # no losing round trip: undefined
    assert strat.profit_factor is None  # no losing round trip: undefined
    # Buy & Hold trades nothing, so it has no round trip to rate.
    assert report.buy_and_hold.round_trip_win_rate is None
    assert report.buy_and_hold.round_trip_payoff_ratio is None
    assert report.buy_and_hold.win_rate is None


def test_win_rate_equals_round_trip_win_rate_single_source() -> None:
    """C8: 同值斷言 -- ``win_rate`` and ``round_trip_win_rate`` share one source.

    Both fields must come from the very same ``RoundTripStats`` supplied by
    ``episodes.attribute_round_trips``; a second computation in ``report.py``
    would eventually drift. Checked on the full segment and both walk-forward
    segments of a run with real costs.
    """
    result = _one_holding_period_result()
    full = build_segment_report(result)
    assert full.strategy.win_rate == full.strategy.round_trip_win_rate

    wf = walk_forward_report(result, walk_forward_splits(30, train_size=10, test_size=5))
    for segment in (wf.in_sample, wf.out_of_sample):
        assert segment.strategy.win_rate == segment.strategy.round_trip_win_rate
        assert segment.buy_and_hold.win_rate == segment.buy_and_hold.round_trip_win_rate


def test_a_round_trip_straddling_the_segment_is_not_credited_to_it() -> None:
    result = _one_holding_period_result()
    folds = walk_forward_splits(30, train_size=10, test_size=5)
    oos = walk_forward_report(result, folds).out_of_sample.strategy
    # The single round trip opened before the out-of-sample window, so the
    # window has no completed round trip of its own. C8 fix: ``win_rate`` /
    # ``profit_factor`` are round-trip statistics now, so they are honestly
    # ``None`` here instead of rating the sliver fills that happen to fall
    # inside the window (the old fill-layer value was 1.0 -- the pollution this
    # test used to document and the C8 fix removes, not a loosened assertion).
    assert oos.round_trip_win_rate is None
    assert oos.round_trip_payoff_ratio is None
    assert oos.win_rate is None
    assert oos.profit_factor is None
    # The fill-layer settlement count keeps its meaning and still sees them.
    assert oos.num_closing_trades > 0


def test_profit_factor_sums_realized_pnl_over_round_trips() -> None:
    """C8: profit factor = round-trip gross profit / gross loss, in currency.

    Two zero-cost round trips -- one win, one loss -- pin the definition:
    numerator sums ``realized_pnl`` over winning round trips, denominator sums
    ``-realized_pnl`` over losing ones, exactly as supplied by ``episodes``.
    """
    frame = bars_to_frame(bars_from_closes([100.0, 120.0, 100.0, 80.0]))

    def in_market_on_odd_windows(window: pd.DataFrame) -> float:
        return 1.0 if len(window) % 2 == 1 else 0.0

    result = run_backtest(
        frame, in_market_on_odd_windows, initial_cash=10_000.0, cost_model=ZERO_COST
    )
    report = build_segment_report(result)
    strat = report.strategy

    trips = attribute_round_trips(result, start=0, stop=len(result.equity_curve))
    assert len(trips.episodes) == 2
    gross_profit = sum(e.realized_pnl for e in trips.episodes if e.realized_pnl > 0)
    gross_loss = -sum(e.realized_pnl for e in trips.episodes if e.realized_pnl < 0)
    assert gross_profit > 0 and gross_loss > 0
    assert strat.profit_factor is not None
    assert math.isclose(strat.profit_factor, gross_profit / gross_loss, rel_tol=1e-12)
    assert strat.win_rate == 0.5
    assert strat.win_rate == strat.round_trip_win_rate


def test_empty_result_reports_zero_observations() -> None:
    empty = bars_to_frame([])
    result = run_backtest(empty, lambda _w: 1.0)
    report = build_segment_report(result)
    assert report.strategy.observations == 0
    assert report.strategy.cagr is None

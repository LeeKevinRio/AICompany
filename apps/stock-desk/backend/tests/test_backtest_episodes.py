"""Round-trip extraction, out-of-sample attribution and the injected f* interval.

The seven guards ADR-0006 (D-5) makes non-negotiable for the Kelly input path:

1. **Attribution purity** -- an out-of-sample sample contains only round trips
   that both opened and closed inside the window.
2. **Boundary sensitivity** -- moving the window edge one bar changes the sample
   by at most one round trip (an edge that moves more is filtering by something
   other than the edge).
3. **Look-ahead displacement** -- feeding the strategy tomorrow's close moves
   both p and b; a p/b pair that ignores bar alignment is already reading it.
4. **Sum invariant** -- over a flat-to-flat span, the round trips account for the
   whole equity change, so treating a holding period as one trade loses no money
   the fills carried.
5. **Injection guard** -- the fraction formula really does come from outside this
   module (a constant injection degenerates the interval, and the call count is
   exactly one per draw plus the point estimate).
6. **``Trade.bar_index`` invariant** -- ``dates[bar_index] == date`` for every
   fill, the premise that lets attribution drop date-string comparisons.
7. **Degenerate resampling** -- both directions are handled explicitly, counted
   separately and never silently dropped.

The strategy under test is a real, price-driven one (``ma_cross``) over a seeded
random walk: a smooth analytic path would make every round trip a winner and
leave b undefined, which is exactly the sample shape these guards must not be
tuned to.
"""

from __future__ import annotations

import math
import random
import re
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from app.advice.limits import kelly_fraction
from app.backtest.costs import CostModel
from app.backtest.engine import BacktestResult, Strategy, Trade, run_backtest
from app.backtest.episodes import (
    POSITION_EPSILON,
    attribute_round_trips,
    bootstrap_fraction_ci,
    extract_episodes,
    oos_window,
    stats_from_returns,
    wilson_interval,
)
from app.backtest.splits import walk_forward_splits
from app.backtest.strategies import ma_cross
from app.signals.frame import CLOSE, bars_to_frame
from tests.import_graph import offenders, reachable_app_modules
from tests.signals_helpers import bars_from_closes

BARS = 200
INITIAL_CASH = 100_000.0
TRAIN_SIZE = 60
TEST_SIZE = 20


def _walk_closes(bars: int = BARS, *, seed: int = 7) -> list[float]:
    """A deterministic random walk: wins and losses in the same run."""
    rnd = random.Random(seed)
    price = 100.0
    closes = [price]
    for _ in range(bars - 1):
        price *= 1.0 + rnd.gauss(0.0004, 0.02)
        closes.append(round(price, 4))
    return closes


def _run(closes: list[float], strategy: Strategy | None = None) -> BacktestResult:
    frame = bars_to_frame(bars_from_closes(closes))
    return run_backtest(
        frame,
        strategy or ma_cross(fast=3, slow=6),
        initial_cash=INITIAL_CASH,
        cost_model=CostModel(),
    )


def _spans(result: BacktestResult) -> list[tuple[int, int]]:
    return [(e.entry_idx, e.exit_idx) for e in extract_episodes(result).episodes]


def _reading_tomorrows_close(strategy: Strategy, closes: list[float]) -> Strategy:
    """``strategy`` handed a close column shifted one bar into the future.

    Mirrors ``tests/test_lookahead_detection.py``: fills still happen at the real
    closes, so only the decisions move.
    """
    future = np.asarray([*closes[1:], closes[-1]], dtype="float64")

    def leaking(window: pd.DataFrame) -> float:
        leaked = window.copy()
        leaked[CLOSE] = future[: len(window)]
        return strategy(leaked)

    return leaking


# --------------------------------------------------------------------------
# (6) Trade.bar_index invariant
# --------------------------------------------------------------------------


def test_every_trade_carries_the_bar_index_of_its_own_date() -> None:
    result = _run(_walk_closes())
    assert result.trades, "the fixture must trade or the invariant is vacuous"
    for trade in result.trades:
        assert result.dates[trade.bar_index] == trade.date
    # Fills arrive in bar order, which is what lets extraction fold them in one pass.
    indices = [t.bar_index for t in result.trades]
    assert indices == sorted(indices)


# --------------------------------------------------------------------------
# Extraction
# --------------------------------------------------------------------------


def test_a_holding_period_is_one_round_trip_not_many_fills() -> None:
    # Fully invested until the last bar: the cost drag leaves cash slightly
    # negative, so the engine trims a sliver every bar. Those slivers are fills,
    # not trades -- one entry and one exit is one round trip.
    closes = _walk_closes(60)
    bars = len(closes)

    def long_then_flat(window: pd.DataFrame) -> float:
        return 1.0 if len(window) < bars else 0.0

    result = _run(closes, long_then_flat)
    extraction = extract_episodes(result)
    closing_fills = [t for t in result.trades if t.realized_pnl is not None]
    assert len(closing_fills) > 1
    assert len(extraction.episodes) == 1
    assert extraction.open_entry_idx is None
    episode = extraction.episodes[0]
    assert (episode.entry_idx, episode.exit_idx) == (0, bars - 1)
    # Every fill's realized P&L is inside the round trip, none of it dropped.
    assert math.isclose(
        episode.realized_pnl,
        sum(t.realized_pnl or 0.0 for t in closing_fills),
        abs_tol=1e-9,
    )


def test_round_trip_return_is_measured_against_pre_entry_equity() -> None:
    result = _run(_walk_closes())
    for episode in extract_episodes(result).episodes:
        expected = (
            result.equity_curve[episode.entry_idx - 1]
            if episode.entry_idx > 0
            else result.initial_cash
        )
        assert episode.entry_equity == expected
        assert math.isclose(
            episode.return_on_entry_equity, episode.realized_pnl / expected, rel_tol=1e-12
        )


def test_a_position_still_open_on_the_last_bar_is_not_a_round_trip() -> None:
    closes = _walk_closes(40)

    def always_long(_window: pd.DataFrame) -> float:
        return 1.0

    result = _run(closes, always_long)
    extraction = extract_episodes(result)
    assert extraction.episodes == ()
    assert extraction.open_entry_idx == 0


def test_position_epsilon_is_an_absolute_share_tolerance() -> None:
    # Documented value and meaning: a share-count tolerance, not a fraction.
    assert POSITION_EPSILON == 1e-9


def _fill(bar_index: int, shares: float, realized_pnl: float | None) -> Trade:
    side = "buy" if shares > 0 else "sell"
    return Trade(
        date=f"2024-01-{bar_index + 1:02d}",
        bar_index=bar_index,
        side=side,
        shares=shares,
        price=100.0,
        notional=shares * 100.0,
        cost=0.0,
        realized_pnl=realized_pnl,
    )


def test_a_fill_inside_the_flat_tolerance_belongs_to_no_round_trip() -> None:
    # A dust liquidation while the book is flat is not a round trip and its P&L
    # is not the neighbouring round trip's either -- assembled by hand because
    # the engine cannot be made to emit one on demand.
    result = BacktestResult(
        dates=["2024-01-01", "2024-01-02", "2024-01-03"],
        equity_curve=[1_000.0, 1_000.0, 1_025.0],
        close=[100.0, 100.0, 102.5],
        weights=[0.0, 1.0, 0.0],
        trades=[
            _fill(0, -POSITION_EPSILON / 2.0, 999.0),
            _fill(1, 10.0, None),
            _fill(2, -10.0, 25.0),
        ],
        initial_cash=1_000.0,
    )
    extraction = extract_episodes(result)
    assert len(extraction.episodes) == 1
    episode = extraction.episodes[0]
    assert (episode.entry_idx, episode.exit_idx) == (1, 2)
    assert episode.realized_pnl == 25.0
    assert episode.entry_equity == 1_000.0


# --------------------------------------------------------------------------
# (1) Attribution purity
# --------------------------------------------------------------------------


def test_out_of_sample_sample_holds_only_fully_contained_round_trips() -> None:
    result = _run(_walk_closes())
    folds = walk_forward_splits(BARS, train_size=TRAIN_SIZE, test_size=TEST_SIZE)
    start, stop = oos_window(folds)
    assert (start, stop) == (folds[0].test_start, folds[-1].test_stop)

    attribution = attribute_round_trips(result, start=start, stop=stop)
    assert attribution.episodes, "the fixture must produce an out-of-sample sample"
    for episode in attribution.episodes:
        assert episode.entry_idx >= start
        assert episode.exit_idx < stop

    all_spans = _spans(result)
    contained = {(e.entry_idx, e.exit_idx) for e in attribution.episodes}
    straddling = [
        span
        for span in all_spans
        if span not in contained and span[1] >= start and span[0] < stop
    ]
    # Straddlers are excluded *and* counted -- never quietly credited or split.
    assert len(straddling) == attribution.excluded_boundary_trips
    assert straddling
    outside = [
        span for span in all_spans if span not in contained and span not in straddling
    ]
    assert len(contained) + len(straddling) + len(outside) == len(all_spans)
    assert attribution.stats.n == len(contained)


def test_an_open_position_at_the_end_is_counted_apart_from_boundary_exclusions() -> None:
    closes = _walk_closes(80)

    def long_from_bar_ten(window: pd.DataFrame) -> float:
        # Flat, one closed round trip, then long to the end: one of each case.
        bar = len(window) - 1
        if 10 <= bar < 20 or bar >= 60:
            return 1.0
        return 0.0

    result = _run(closes, long_from_bar_ten)
    extraction = extract_episodes(result)
    assert extraction.open_entry_idx == 60
    attribution = attribute_round_trips(result, start=0, stop=80)
    assert attribution.open_trip_at_end == 1
    assert attribution.excluded_boundary_trips == 0
    assert [(e.entry_idx, e.exit_idx) for e in attribution.episodes] == [(10, 20)]


# --------------------------------------------------------------------------
# (2) Boundary sensitivity
# --------------------------------------------------------------------------


def test_moving_the_window_edge_one_bar_moves_at_most_one_round_trip() -> None:
    result = _run(_walk_closes())
    stop = BARS

    def sample(start: int) -> set[tuple[int, int]]:
        return {
            (e.entry_idx, e.exit_idx)
            for e in attribute_round_trips(result, start=start, stop=stop).episodes
        }

    changed = 0
    for start in range(TRAIN_SIZE - 1, TRAIN_SIZE + 40):
        difference = sample(start) ^ sample(start + 1)
        assert len(difference) <= 1, (
            f"start={start} -> {start + 1} moved {len(difference)} round trips; "
            "the edge is filtering by something other than the edge"
        )
        changed += len(difference)
    # ...and the guard is not passing merely because nothing ever moves.
    assert changed > 0

    # A window edge landing exactly on an entry drops that round trip when it
    # advances one bar past it, and only that one.
    entry = _spans(result)[8][0]
    assert sample(entry) - sample(entry + 1) == {_spans(result)[8]}


# --------------------------------------------------------------------------
# (3) Look-ahead displacement
# --------------------------------------------------------------------------


def test_p_and_b_move_when_the_strategy_is_fed_tomorrows_close() -> None:
    closes = _walk_closes()
    base = attribute_round_trips(_run(closes), start=0, stop=BARS).stats
    leaked = attribute_round_trips(
        _run(closes, _reading_tomorrows_close(ma_cross(fast=3, slow=6), closes)),
        start=0,
        stop=BARS,
    ).stats
    assert base.round_trip_win_rate is not None and leaked.round_trip_win_rate is not None
    assert base.round_trip_payoff_ratio is not None
    assert leaked.round_trip_payoff_ratio is not None

    win_rate_shift = abs(leaked.round_trip_win_rate - base.round_trip_win_rate)
    payoff_shift = (
        abs(leaked.round_trip_payoff_ratio - base.round_trip_payoff_ratio)
        / base.round_trip_payoff_ratio
    )
    assert win_rate_shift > 0.02, (
        f"p barely moved under a one-bar close shift ({win_rate_shift:.4f}); "
        "the estimator may not depend on bar alignment"
    )
    assert payoff_shift > 0.05, (
        f"b barely moved under a one-bar close shift ({payoff_shift:.4%}); "
        "the estimator may not depend on bar alignment"
    )


# --------------------------------------------------------------------------
# (4) Sum invariant
# --------------------------------------------------------------------------


def test_round_trips_account_for_the_whole_equity_change_of_a_flat_span() -> None:
    result = _run(_walk_closes())
    episodes = extract_episodes(result).episodes
    first, last = episodes[2], episodes[8]
    start, stop = first.entry_idx, last.exit_idx + 1

    attribution = attribute_round_trips(result, start=start, stop=stop)
    # The span opens on an entry and closes on an exit, so the book is flat at
    # both ends and nothing straddles.
    assert attribution.excluded_boundary_trips == 0
    assert attribution.open_trip_at_end == 0
    assert attribution.episodes[0] == first
    assert attribution.episodes[-1] == last

    equity_change = result.equity_curve[stop - 1] - result.equity_curve[start - 1]
    assert math.isclose(
        sum(e.realized_pnl for e in attribution.episodes), equity_change, abs_tol=1e-6
    )


# --------------------------------------------------------------------------
# p / b estimation
# --------------------------------------------------------------------------


def test_p_and_b_come_from_round_trip_returns() -> None:
    returns = [0.10, -0.05, 0.20, -0.03, 0.0]
    stats = stats_from_returns(returns)
    assert stats.n == 5
    assert stats.n_win == 2
    assert stats.n_loss == 2
    # A flat round trip counts in n but is neither a win nor a loss.
    assert stats.round_trip_win_rate == 2 / 5
    assert stats.round_trip_payoff_ratio == pytest.approx(0.15 / 0.04)


def test_b_is_undefined_rather_than_large_without_both_sides() -> None:
    assert stats_from_returns([0.1, 0.2]).round_trip_payoff_ratio is None
    assert stats_from_returns([-0.1, -0.2]).round_trip_payoff_ratio is None
    empty = stats_from_returns([])
    assert empty.round_trip_win_rate is None
    assert empty.round_trip_payoff_ratio is None


def test_wilson_interval_matches_the_published_value_and_brackets_p() -> None:
    interval = wilson_interval(12, 20)
    assert interval is not None
    assert interval.low == pytest.approx(0.38658, abs=1e-5)
    assert interval.high == pytest.approx(0.78119, abs=1e-5)
    assert interval.low < 0.6 < interval.high
    # Even at an edge the interval stays inside [0, 1] -- the reason for Wilson.
    edge = wilson_interval(20, 20)
    assert edge is not None
    assert 0.0 < edge.low < 1.0 and edge.high <= 1.0
    assert wilson_interval(0, 0) is None


# --------------------------------------------------------------------------
# (5) f* injection guard
# --------------------------------------------------------------------------


def test_a_constant_injected_fraction_degenerates_the_interval() -> None:
    calls: list[tuple[float, float]] = []

    def constant(win_rate: float, payoff_ratio: float) -> float:
        calls.append((win_rate, payoff_ratio))
        return 0.5

    returns = [0.1, -0.05, 0.2, -0.08, 0.15, -0.02, 0.07, -0.11]
    interval = bootstrap_fraction_ci(returns, fraction_fn=constant, seed=1234, draws=64)
    # Nothing but the injected callable decides the value: a constant injection
    # can only produce a constant interval. Any formula hidden here would leak.
    assert (interval.point, interval.low, interval.high) == (0.5, 0.5, 0.5)
    # One call per draw, plus the point estimate on the observed sample.
    assert len(calls) == interval.draws + 1 == 65
    assert interval.degenerate_no_loss_draws == 0
    assert interval.degenerate_no_win_draws == 0


def test_fraction_fn_is_keyword_only_and_has_no_default() -> None:
    # The injection is the whole guarantee that the Kelly formula lives in one
    # place; a default would quietly restore a second copy.
    with pytest.raises(TypeError):
        bootstrap_fraction_ci([0.1, -0.1], seed=1, draws=4)  # type: ignore[call-arg]


def test_the_module_contains_no_kelly_shaped_arithmetic() -> None:
    source = (Path(__file__).resolve().parent.parent / "app/backtest/episodes.py").read_text(
        encoding="utf-8"
    )
    for pattern in (r"1(\.0)? - .*win_rate", r"1(\.0)? - p\b", r"- \(1(\.0)? -"):
        assert re.search(pattern, source) is None, (
            f"episodes.py looks like it re-derives the Kelly fraction ({pattern}); "
            "the formula belongs to app/advice/limits.py alone"
        )


def test_episodes_never_reaches_the_advice_or_kelly_layers() -> None:
    reachable = reachable_app_modules(("app.backtest.episodes",))
    assert offenders(reachable, "app.advice") == []
    assert offenders(reachable, "app.kelly") == []


def test_the_bootstrap_is_reproducible_from_its_seed() -> None:
    returns = [0.1, -0.05, 0.2, -0.08, 0.15, -0.02, 0.07, -0.11, 0.04, -0.06]
    first = bootstrap_fraction_ci(returns, fraction_fn=kelly_fraction, seed=99, draws=200)
    again = bootstrap_fraction_ci(returns, fraction_fn=kelly_fraction, seed=99, draws=200)
    assert (first.low, first.high) == (again.low, again.high)
    other = bootstrap_fraction_ci(returns, fraction_fn=kelly_fraction, seed=100, draws=200)
    assert (other.low, other.high) != (first.low, first.high)


def test_the_point_estimate_is_the_injected_fraction_of_the_observed_sample() -> None:
    returns = [0.1, -0.05, 0.2, -0.08, 0.15, -0.02, 0.07, -0.11, 0.04, -0.06]
    stats = stats_from_returns(returns)
    assert stats.round_trip_win_rate is not None
    assert stats.round_trip_payoff_ratio is not None
    expected = kelly_fraction(stats.round_trip_win_rate, stats.round_trip_payoff_ratio)
    interval = bootstrap_fraction_ci(returns, fraction_fn=kelly_fraction, seed=5, draws=200)
    assert interval.point == expected
    assert interval.low <= interval.high
    assert math.isfinite(interval.low) and math.isfinite(interval.high)


# --------------------------------------------------------------------------
# (7) Degenerate resampling, both directions
# --------------------------------------------------------------------------


def test_a_resample_without_losses_is_evaluated_at_an_infinite_payoff_ratio() -> None:
    seen: list[tuple[float, float]] = []

    def spy(win_rate: float, payoff_ratio: float) -> float | None:
        seen.append((win_rate, payoff_ratio))
        return kelly_fraction(win_rate, payoff_ratio)

    returns = [0.05, 0.10, 0.20, 0.15]  # every resample is all wins
    interval = bootstrap_fraction_ci(returns, fraction_fn=spy, seed=3, draws=32)
    assert interval.degenerate_no_loss_draws == 32
    assert interval.degenerate_no_win_draws == 0
    # b is unbounded, not unknown: the injected formula's own arithmetic returns
    # p there, so f* == p̂ == 1.0 without a branch written in episodes.py.
    assert all(math.isinf(payoff) and payoff > 0 for _p, payoff in seen)
    assert (interval.point, interval.low, interval.high) == (1.0, 1.0, 1.0)


def test_a_resample_without_wins_floors_the_draw_without_calling_the_fraction() -> None:
    calls = 0

    def spy(win_rate: float, payoff_ratio: float) -> float | None:  # pragma: no cover
        nonlocal calls
        calls += 1
        return kelly_fraction(win_rate, payoff_ratio)

    returns = [-0.05, -0.10, -0.20, -0.15]  # every resample is all losses
    interval = bootstrap_fraction_ci(returns, fraction_fn=spy, seed=3, draws=32)
    assert interval.degenerate_no_win_draws == 32
    assert interval.degenerate_no_loss_draws == 0
    # b does not exist (there is nothing to average), so the true limit floors
    # the draw. Feeding b = 0 to the formula would return None and the only way
    # to carry on would be to drop the draw -- which lifts the lower bound, the
    # one direction a disclosure interval must not move.
    assert calls == 0
    assert interval.low == -math.inf
    assert interval.high == -math.inf
    assert interval.point == -math.inf


def test_a_degenerate_draw_is_never_silently_dropped() -> None:
    # Mostly winners with a single loser: some resamples miss the loser. Whatever
    # their number, every draw is still one value in the interval.
    returns = [0.05, 0.10, 0.20, 0.15, -0.02]
    interval = bootstrap_fraction_ci(returns, fraction_fn=kelly_fraction, seed=11, draws=500)
    assert interval.degenerate_no_loss_draws > 0
    assert interval.degenerate_no_win_draws == 0
    assert interval.low <= interval.point <= interval.high


def test_bootstrap_rejects_an_empty_sample_or_a_non_positive_draw_count() -> None:
    with pytest.raises(ValueError):
        bootstrap_fraction_ci([], fraction_fn=kelly_fraction, seed=1, draws=10)
    with pytest.raises(ValueError):
        bootstrap_fraction_ci([0.1, -0.1], fraction_fn=kelly_fraction, seed=1, draws=0)


def test_intervals_reject_an_impossible_confidence_level() -> None:
    with pytest.raises(ValueError):
        wilson_interval(6, 10, alpha=0.0)
    with pytest.raises(ValueError):
        bootstrap_fraction_ci(
            [0.1, -0.1], fraction_fn=kelly_fraction, seed=1, draws=4, alpha=1.0
        )


def test_the_out_of_sample_window_refuses_an_empty_fold_set() -> None:
    # Without folds there is no geometry to attribute against, and falling back
    # to "the whole run" would silently rate in-sample bars as out-of-sample.
    with pytest.raises(ValueError):
        oos_window([])


def test_a_fraction_fn_returning_none_fails_loudly() -> None:
    # Dropping the draw would bias the interval; refusing is the honest option.
    with pytest.raises(ValueError):
        bootstrap_fraction_ci(
            [0.1, -0.1], fraction_fn=lambda _p, _b: None, seed=1, draws=4
        )

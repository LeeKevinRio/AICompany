"""F-11 round-trip facts in ``app/backtest/episodes.py`` (PRD D-4..D-12).

The pure functions F-11 adds next to the extraction they read:

* holding bars, the per-side mean returns (F11-A-18: ``==``, never approximate,
  against ``round_trip_payoff_ratio``), the lowest-return round trips (D-10 tie
  rule), the longest losing streak (D-11: ties break it, earliest wins);
* the in-market reading of D-12 with its three test layers (F11-A-39): the
  equivalence lock ``held[t] <=> weights[t] > 0`` for every shipped strategy,
  the characterisation of the three defined differences (a) close <= 0,
  (b) a rebalance too small to fill, (c) a close leaving a residue above
  ``POSITION_EPSILON``, and the {0.0, 1.0} weight guard that covers the rest.
"""

from __future__ import annotations

import random
from datetime import date, timedelta

import pandas as pd
import pytest

from app.backtest.costs import CostModel
from app.backtest.engine import BacktestResult, Trade, run_backtest
from app.backtest.episodes import (
    POSITION_EPSILON,
    Episode,
    EpisodeExtraction,
    RoundTripAttribution,
    extract_episodes,
    held_mask,
    holding_bars,
    in_market_intervals,
    in_market_ratio,
    longest_losing_streak,
    lowest_return_episodes,
    mean_win_loss_returns,
    round_trip_stats,
    stats_from_returns,
)
from app.backtest.report import _trade_stats
from app.backtest.strategies import STRATEGY_IDS, build_strategy
from app.signals.frame import CLOSE, bars_to_frame
from tests.test_golden_backtest_outputs import _REPORT_WALK, _walk_bars


def _episode(entry: int, exit_: int, ret: float, *, equity: float = 1_000_000.0) -> Episode:
    return Episode(
        entry_idx=entry,
        exit_idx=exit_,
        realized_pnl=ret * equity,
        entry_equity=equity,
        return_on_entry_equity=ret,
    )


def _sequence(returns: list[float]) -> list[Episode]:
    """Round trips in entry order, two bars each, one flat bar between them."""
    return [_episode(3 * i + 1, 3 * i + 3, value) for i, value in enumerate(returns)]


def _standard_run(strategy_id: str) -> BacktestResult:
    """The golden fixture (every strategy trades on it), default cash and costs."""
    frame = bars_to_frame(_walk_bars(_REPORT_WALK))
    return run_backtest(frame, build_strategy(strategy_id), cost_model=CostModel())


# --------------------------------------------------------------------------
# D-4 holding bars
# --------------------------------------------------------------------------


def test_holding_bars_is_the_bar_distance_and_at_least_one() -> None:
    assert holding_bars(_episode(10, 11, 0.01)) == 1
    assert holding_bars(_episode(10, 25, 0.01)) == 15
    result = _standard_run("ma_cross")
    episodes = extract_episodes(result).episodes
    assert episodes
    assert all(holding_bars(e) == e.exit_idx - e.entry_idx >= 1 for e in episodes)


def test_holding_bars_equal_the_held_intervals_inside_each_round_trip() -> None:
    """D-4 and D-12 share one unit: bars held inside the span, the span's length."""
    for strategy_id in STRATEGY_IDS:
        result = _standard_run(strategy_id)
        extraction = extract_episodes(result)
        held = held_mask(extraction, len(result.dates))
        for episode in extraction.episodes:
            inside = sum(held[t] for t in range(episode.entry_idx, episode.exit_idx))
            assert inside == holding_bars(episode), (strategy_id, episode)
            assert not held[episode.exit_idx] or any(
                other.entry_idx == episode.exit_idx for other in extraction.episodes
            )


# --------------------------------------------------------------------------
# D-6 / D-7 mean returns and the payoff ratio
# --------------------------------------------------------------------------


def test_the_two_means_divide_to_the_payoff_ratio_bit_for_bit() -> None:
    """F11-A-18: ``==``, over many samples, never an approximate comparison."""
    rnd = random.Random(20261013)
    checked = 0
    for _ in range(500):
        returns = [rnd.uniform(-0.2, 0.2) for _ in range(rnd.randint(1, 60))]
        mean_win, mean_loss = mean_win_loss_returns(returns)
        stats = stats_from_returns(returns)
        if mean_win is None or mean_loss is None:
            assert stats.round_trip_payoff_ratio is None
            continue
        assert mean_win / -mean_loss == stats.round_trip_payoff_ratio
        checked += 1
    assert checked > 400


def test_ac5_four_round_trips() -> None:
    """AC-5: +3%, -1%, +1%, -2% of a chained book."""
    returns = [
        30_000 / 1_000_000,
        -10_300 / 1_030_000,
        10_197 / 1_019_700,
        -20_597.94 / 1_029_897,
    ]
    mean_win, mean_loss = mean_win_loss_returns(returns)
    assert mean_win == pytest.approx(0.02, abs=1e-9)
    assert mean_loss == pytest.approx(-0.015, abs=1e-9)
    assert mean_win is not None and mean_loss is not None
    assert mean_win / -mean_loss == stats_from_returns(returns).round_trip_payoff_ratio
    assert f"{mean_win / -mean_loss:.2f}" == "1.33"


def test_ac5b_equal_entry_equity_still_separates_the_two_ratios() -> None:
    """AC-5b: 2 wins of +3%, 3 losses of -2%, equal pre-entry equity."""
    episodes = _sequence([0.03, -0.02, 0.03, -0.02, -0.02])
    stats = round_trip_stats(episodes)
    assert stats.round_trip_payoff_ratio == pytest.approx(1.5)
    attribution = RoundTripAttribution(
        window_start=0,
        window_stop=100,
        episodes=tuple(episodes),
        excluded_boundary_trips=0,
        open_trip_at_end=0,
        stats=stats,
    )
    _, profit_factor = _trade_stats(attribution)
    assert profit_factor == pytest.approx(1.0)


def test_an_empty_side_has_no_mean_rather_than_zero() -> None:
    assert mean_win_loss_returns([]) == (None, None)
    assert mean_win_loss_returns([0.0, 0.0]) == (None, None)
    win, loss = mean_win_loss_returns([0.01, 0.03])
    assert win == pytest.approx(0.02) and loss is None
    win, loss = mean_win_loss_returns([-0.01, -0.03, 0.0])
    assert win is None and loss == pytest.approx(-0.02)


# --------------------------------------------------------------------------
# D-10 lowest-return round trips
# --------------------------------------------------------------------------


def test_lowest_returns_rank_by_return_and_break_ties_by_entry_bar() -> None:
    a = _episode(40, 42, -0.02)
    b = _episode(10, 12, -0.02)
    c = _episode(20, 22, -0.05)
    d = _episode(30, 32, 0.04)
    e = _episode(5, 7, -0.01)
    f = _episode(50, 52, 0.0)
    lowest = lowest_return_episodes([a, b, c, d, e, f], 5)
    assert lowest == (c, b, a, e, f)


def test_lowest_returns_rank_by_return_not_by_currency() -> None:
    small_book_big_loss = _episode(1, 2, -0.10, equity=100_000.0)  # -10,000
    big_book_small_loss = _episode(5, 6, -0.02, equity=10_000_000.0)  # -200,000
    lowest = lowest_return_episodes([big_book_small_loss, small_book_big_loss], 1)
    assert lowest == (small_book_big_loss,)


def test_fewer_round_trips_than_requested_are_listed_as_they_are() -> None:
    """AC-3: three winners, all three listed, lowest first, nothing padded."""
    winners = [_episode(1, 2, 0.05), _episode(4, 5, 0.01), _episode(7, 8, 0.03)]
    assert [e.return_on_entry_equity for e in lowest_return_episodes(winners, 5)] == [
        0.01,
        0.03,
        0.05,
    ]
    assert lowest_return_episodes([], 5) == ()
    assert lowest_return_episodes(winners, 0) == ()
    with pytest.raises(ValueError):
        lowest_return_episodes(winners, -1)


# --------------------------------------------------------------------------
# D-11 longest losing streak
# --------------------------------------------------------------------------


def test_ac4_streak_counts_round_trips_and_a_tie_breaks_it() -> None:
    episodes = _sequence([0.02, -0.01, -0.03, -0.005, 0.01, -0.02, 0.0, -0.01])
    streak = longest_losing_streak(episodes)
    assert streak == tuple(episodes[1:4])
    assert streak is not None and len(streak) == 3
    # The 0% round trip at position 7 splits the two losses around it.
    shifted = _sequence([-0.01, 0.0, -0.01])
    assert longest_losing_streak(shifted) == (shifted[0],)


def test_equally_long_streaks_report_the_earliest() -> None:
    episodes = _sequence([-0.01, -0.01, 0.01, -0.02, -0.02])
    assert longest_losing_streak(episodes) == (episodes[0], episodes[1])
    # Input order does not matter: the streak is read in entry-bar order.
    assert longest_losing_streak(list(reversed(episodes))) == (episodes[0], episodes[1])


def test_no_round_trip_is_undefined_and_no_loss_is_zero() -> None:
    assert longest_losing_streak([]) is None
    assert longest_losing_streak(_sequence([0.01, 0.0, 0.02])) == ()


def test_streak_invariants_over_random_samples() -> None:
    """``0 <= streak <= n_loss`` and ``streak == 0`` iff ``n_loss == 0`` (n > 0)."""
    rnd = random.Random(7)
    for _ in range(400):
        values = [rnd.choice([-0.02, -0.01, 0.0, 0.01, 0.02]) for _ in range(rnd.randint(1, 30))]
        streak = longest_losing_streak(_sequence(values))
        assert streak is not None
        n_loss = stats_from_returns(values).n_loss
        assert 0 <= len(streak) <= n_loss
        assert (len(streak) == 0) == (n_loss == 0)
        assert all(e.return_on_entry_equity < 0.0 for e in streak)


def _fills_result(spans: list[tuple[int, int, float]], *, slivers: int) -> BacktestResult:
    """Synthetic run whose round trips close through ``slivers`` extra partial sells."""
    bars = 40
    trades: list[Trade] = []
    for entry, exit_, pnl in spans:
        trades.append(Trade(f"d{entry}", entry, "buy", 100.0, 10.0, 1000.0, 0.0, None))
        remaining = 100.0
        for k in range(slivers):
            trades.append(
                Trade(f"d{entry + 1 + k}", entry + 1 + k, "sell", -1.0, 10.0, -10.0, 0.0, 0.0)
            )
            remaining -= 1.0
        trades.append(Trade(f"d{exit_}", exit_, "sell", -remaining, 10.0, -1.0, 0.0, pnl))
    return BacktestResult(
        dates=[f"d{t}" for t in range(bars)],
        equity_curve=[1_000_000.0] * bars,
        close=[10.0] * bars,
        weights=[0.0] * bars,
        trades=trades,
        initial_cash=1_000_000.0,
    )


def test_the_streak_does_not_move_with_the_fill_count() -> None:
    """AC-4 / F11-A-20(d): sliver fills change nothing about round trips."""
    spans = [(1, 6, -100.0), (8, 13, -50.0), (15, 20, 30.0), (22, 27, -10.0)]
    few = extract_episodes(_fills_result(spans, slivers=0)).episodes
    many_result = _fills_result(spans, slivers=3)
    many = extract_episodes(many_result).episodes
    assert len(many_result.trades) > 2 * len(spans)
    assert [(e.entry_idx, e.exit_idx) for e in few] == [(e.entry_idx, e.exit_idx) for e in many]
    streak_few = longest_losing_streak(few)
    streak_many = longest_losing_streak(many)
    assert streak_few is not None and streak_many is not None
    assert len(streak_few) == len(streak_many) == 2


# --------------------------------------------------------------------------
# D-12 in-market intervals
# --------------------------------------------------------------------------


def test_ac17_forty_of_a_hundred_intervals() -> None:
    """101 bars, 100 return intervals, 40 held -> 40%."""
    start, stop = 50, 151
    held = [False] * 200
    for t in range(60, 100):
        held[t] = True
    # The segment's last bar earns a move outside the segment: never counted.
    held[stop - 1] = True
    assert in_market_intervals(held, start=start, stop=stop) == 40
    assert in_market_ratio(held, start=start, stop=stop) == 0.4


def test_a_segment_without_a_return_interval_has_no_ratio() -> None:
    held = [True] * 10
    assert in_market_ratio(held, start=3, stop=4) is None
    assert in_market_ratio(held, start=3, stop=3) is None
    assert in_market_ratio(held, start=3, stop=5) == 1.0


def test_the_held_mask_covers_closed_spans_and_an_open_tail() -> None:
    extraction = EpisodeExtraction(
        episodes=(_episode(2, 5, 0.01), _episode(7, 8, -0.01)), open_entry_idx=10
    )
    held = held_mask(extraction, 13)
    assert [t for t, value in enumerate(held) if value] == [2, 3, 4, 7, 10, 11, 12]


def _synthetic_run(
    *, closes: list[float], weights: list[float], trades: list[Trade], initial_cash: float = 1e6
) -> BacktestResult:
    return BacktestResult(
        dates=[(date(2024, 1, 1) + timedelta(days=t)).isoformat() for t in range(len(closes))],
        equity_curve=[initial_cash] * len(closes),
        close=closes,
        weights=weights,
        trades=trades,
        initial_cash=initial_cash,
    )


def _always_in(_: pd.DataFrame) -> float:
    return 1.0


def _closes_frame(closes: list[float]) -> pd.DataFrame:
    index = pd.DatetimeIndex(
        [pd.Timestamp(2024, 1, 1) + pd.Timedelta(days=t) for t in range(len(closes))]
    )
    return pd.DataFrame({CLOSE: closes}, index=index)


@pytest.mark.parametrize("strategy_id", STRATEGY_IDS)
def test_equivalence_lock_held_iff_positive_weight(strategy_id: str) -> None:
    """F11-A-39(a): on the standard fixture the two readings agree on every bar."""
    result = _standard_run(strategy_id)
    held = held_mask(extract_episodes(result), len(result.dates))
    assert any(held), strategy_id
    assert len(held) == len(result.weights)
    for t, (is_held, weight) in enumerate(zip(held, result.weights, strict=True)):
        assert is_held == (weight > 0.0), (strategy_id, t)


@pytest.mark.parametrize("strategy_id", STRATEGY_IDS)
def test_shipped_strategies_only_emit_all_or_nothing_weights(strategy_id: str) -> None:
    """F11-A-39(c): a fractional weight would need an average-exposure row and a rename."""
    result = _standard_run(strategy_id)
    assert set(result.weights) <= {0.0, 1.0}, strategy_id


def test_difference_a_a_non_positive_close_is_not_held_despite_the_weight() -> None:
    """F11-A-39(b) (a): the engine cannot fill at close <= 0, so the book stays flat."""
    closes = [0.0, 0.0, 0.0, 10.0, 11.0, 12.0, 11.0, 12.0, 13.0, 12.0]
    result = run_backtest(_closes_frame(closes), _always_in, cost_model=CostModel())
    assert result.weights[:3] == [1.0, 1.0, 1.0]
    extraction = extract_episodes(result)
    held = held_mask(extraction, len(closes))
    assert held[:3] == (False, False, False)
    assert held[3:] == (True,) * 7
    # The in-market reading follows the holding, not the weights.
    assert in_market_ratio(held, start=0, stop=len(closes)) == 6 / 9
    by_weight = sum(w > 0 for w in result.weights[:-1]) / 9
    assert by_weight == 1.0


def test_difference_b_a_rebalance_too_small_to_fill_is_not_held() -> None:
    """F11-A-39(b) (b): equity so small the target delta never clears 1e-12."""
    closes = [10.0, 11.0, 12.0, 11.0, 12.0]
    result = run_backtest(_closes_frame(closes), _always_in, initial_cash=1e-13)
    assert result.trades == []
    assert all(w == 1.0 for w in result.weights)
    held = held_mask(extract_episodes(result), len(closes))
    assert in_market_ratio(held, start=0, stop=len(closes)) == 0.0


def test_difference_c_a_residue_above_epsilon_keeps_the_book_in() -> None:
    """F11-A-39(b) (c): built from synthetic fills, not from a huge-book float path."""
    residue = 1e-6
    assert residue > POSITION_EPSILON
    trades = [
        Trade("2024-01-03", 2, "buy", 10.0, 10.0, 100.0, 0.0, None),
        Trade("2024-01-06", 5, "sell", -(10.0 - residue), 10.0, -100.0, 0.0, 5.0),
        Trade("2024-01-07", 6, "sell", -residue, 10.0, -1e-5, 0.0, 0.0),
    ]
    weights = [0.0, 0.0, 1.0, 1.0, 1.0, 0.0, 0.0, 0.0, 0.0, 0.0]
    result = _synthetic_run(closes=[10.0] * 10, weights=weights, trades=trades)
    extraction = extract_episodes(result)
    assert [(e.entry_idx, e.exit_idx) for e in extraction.episodes] == [(2, 6)]
    held = held_mask(extraction, 10)
    # Weights say out from bar 5; the holding, and so the reading, says bar 6.
    assert [t for t, value in enumerate(held) if value] == [2, 3, 4, 5]
    assert in_market_intervals(held, start=0, stop=10) == 4
    assert in_market_ratio(held, start=0, stop=10) == 4 / 9
    # The reconciliation with holding bars still holds on this one flat line.
    assert sum(holding_bars(e) for e in extraction.episodes) == 4

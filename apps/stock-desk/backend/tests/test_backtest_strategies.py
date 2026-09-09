"""Tests for the shipped strategies, including their look-ahead safety."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from app.backtest.costs import CostModel
from app.backtest.engine import run_backtest
from app.backtest.strategies import (
    BREAKOUT_ENTRY_WINDOW,
    BREAKOUT_EXIT_WINDOW,
    DEFAULT_SLOW_WINDOW,
    FIVE_CONDITIONS_WARMUP_BARS,
    FIVE_PULLBACK_MAX_ABS_PCT,
    FIVE_RANGE_MAX_PCT,
    FIVE_RANGE_MIN_BARS,
    FIVE_RSI_HIGH,
    FIVE_RSI_LOW,
    FIVE_STOP_FIXED_RATIO,
    FIVE_TAKE_PROFIT_RATIO,
    FIVE_VOLUME_Z_ABS_MAX,
    RSI_ENTRY_THRESHOLD,
    RSI_EXIT_THRESHOLD,
    STRATEGY_IDS,
    STRATEGY_WARMUP_BARS,
    _replay_with_stop_levels,
    breakout,
    build_strategy,
    five_condition_series,
    five_condition_stop_level,
    five_conditions,
    ma_cross,
    rsi_reversal,
)
from app.signals.frame import CLOSE, bars_to_frame
from app.signals.technical import RSI_PERIOD, rsi, rsi_series, volume_zscore
from tests.signals_helpers import bars_from_closes


def _frame(closes: list[float]) -> pd.DataFrame:
    return bars_to_frame(bars_from_closes(closes))


def test_strategy_is_flat_before_the_slow_window_is_filled() -> None:
    strategy = ma_cross()
    frame = _frame([100.0] * (DEFAULT_SLOW_WINDOW - 1))
    assert strategy(frame) == 0.0


def test_strategy_is_long_when_the_fast_average_leads() -> None:
    strategy = ma_cross()
    # 60 flat bars then a sharp rise: MA20 is pulled above MA60.
    closes = [100.0] * 60 + [200.0] * 20
    assert strategy(_frame(closes)) == 1.0


def test_strategy_is_flat_when_the_fast_average_lags() -> None:
    strategy = ma_cross()
    closes = [200.0] * 60 + [100.0] * 20
    assert strategy(_frame(closes)) == 0.0


def test_strategy_reads_only_the_window_it_is_given() -> None:
    # The engine's guarantee is structural: a strategy that could see the future
    # would behave differently given the same prefix. Here the same prefix must
    # produce the same weight whatever follows it in the full series.
    strategy = ma_cross()
    prefix = [100.0] * 60 + [200.0] * 20
    from_prefix = strategy(_frame(prefix))
    from_longer = strategy(_frame(prefix)[: len(prefix)])
    assert from_prefix == from_longer


def test_windows_must_be_ordered_and_positive() -> None:
    with pytest.raises(ValueError):
        ma_cross(fast=0)
    with pytest.raises(ValueError):
        ma_cross(fast=60, slow=20)
    with pytest.raises(ValueError):
        ma_cross(fast=20, slow=20)


def test_registry_exposes_every_shipped_strategy_with_its_warmup() -> None:
    assert STRATEGY_IDS == ("ma_cross", "rsi_reversal", "breakout", "five_conditions")
    assert STRATEGY_WARMUP_BARS["ma_cross"] == DEFAULT_SLOW_WINDOW
    assert STRATEGY_WARMUP_BARS["rsi_reversal"] == RSI_PERIOD + 1
    assert STRATEGY_WARMUP_BARS["breakout"] == BREAKOUT_ENTRY_WINDOW
    assert STRATEGY_WARMUP_BARS["five_conditions"] == FIVE_CONDITIONS_WARMUP_BARS
    for strategy_id in STRATEGY_IDS:
        assert callable(build_strategy(strategy_id))
    with pytest.raises(KeyError):
        build_strategy("secret_sauce")


# --- FR-10 RSI reversal -------------------------------------------------------

#: Rises (RSI saturated high), then falls far enough to cross the 30 entry line,
#: then recovers through the 50 exit line. Verified against ``rsi_series``:
#: index 36 is the first close at or below 30 and index 48 the first at or above
#: 50, which is what the transition tests below pin.
_RSI_RISE = [100.0 + i for i in range(20)]
_RSI_FALL = [_RSI_RISE[-1] - i for i in range(1, 26)]
_RSI_RECOVERY = [_RSI_FALL[-1] + 2 * i for i in range(1, 16)]
_RSI_PATH = _RSI_RISE + _RSI_FALL + _RSI_RECOVERY

_RSI_ENTRY_INDEX = 36
_RSI_EXIT_INDEX = 48


def _rsi_last(closes: list[float]) -> float:
    """The signal layer's RSI(14) for the same closes, for the agreement test."""
    value = rsi(bars_from_closes(closes)).last["rsi"]
    assert value is not None
    return value


def test_rsi_reversal_stays_flat_until_rsi_is_defined() -> None:
    strategy = rsi_reversal()
    falling = [100.0 - i for i in range(RSI_PERIOD)]  # 14 bars: RSI undefined
    assert strategy(_frame(falling)) == 0.0
    # One more bar makes RSI(14) defined -- and a strictly falling path puts it
    # at the floor, so this is the first day the strategy may act at all.
    falling.append(falling[-1] - 1.0)
    assert strategy(_frame(falling)) == 1.0


def test_rsi_reversal_enters_when_rsi_reaches_the_oversold_line() -> None:
    strategy = rsi_reversal()
    before = _RSI_PATH[:_RSI_ENTRY_INDEX]
    at_entry = _RSI_PATH[: _RSI_ENTRY_INDEX + 1]
    assert _rsi_last(before) > RSI_ENTRY_THRESHOLD
    assert _rsi_last(at_entry) <= RSI_ENTRY_THRESHOLD
    assert strategy(_frame(before)) == 0.0
    assert strategy(_frame(at_entry)) == 1.0


def test_rsi_reversal_holds_between_the_two_thresholds() -> None:
    # Recovering past the entry line is not an exit: the position is held until
    # the mid-line, which is the whole point of the mean-reversion thesis.
    strategy = rsi_reversal()
    mid_zone = _RSI_PATH[:_RSI_EXIT_INDEX]
    assert RSI_ENTRY_THRESHOLD < _rsi_last(mid_zone) < RSI_EXIT_THRESHOLD
    assert strategy(_frame(mid_zone)) == 1.0


def test_rsi_reversal_exits_at_the_mid_line_and_does_not_re_enter() -> None:
    strategy = rsi_reversal()
    at_exit = _RSI_PATH[: _RSI_EXIT_INDEX + 1]
    assert _rsi_last(at_exit) >= RSI_EXIT_THRESHOLD
    assert strategy(_frame(at_exit)) == 0.0
    # The rest of the recovery never revisits the oversold line, so the book
    # stays flat instead of drifting back in on a stale entry.
    assert strategy(_frame(_RSI_PATH)) == 0.0


def test_rsi_reversal_uses_the_same_rsi_as_the_signal_layer() -> None:
    # One definition of RSI(14) in the product: the strategy trades exactly the
    # number ``GET /api/signals`` publishes, not a second implementation of it.
    closes = _RSI_PATH[: _RSI_ENTRY_INDEX + 1]
    from_strategy_input = rsi_series(_frame(closes)[CLOSE]).to_numpy()[-1]
    assert from_strategy_input == pytest.approx(_rsi_last(closes))


def test_rsi_reversal_rejects_inconsistent_thresholds() -> None:
    with pytest.raises(ValueError):
        rsi_reversal(period=0)
    with pytest.raises(ValueError):
        rsi_reversal(entry_level=60.0, exit_level=40.0)
    with pytest.raises(ValueError):
        rsi_reversal(entry_level=0.0)
    with pytest.raises(ValueError):
        rsi_reversal(exit_level=100.0)


# --- FR-11 N-day breakout -----------------------------------------------------

#: 25 rising bars (the 20-day high is made on bar 19) followed by a decline of
#: 2 per bar; the 10-day low is broken on bar 27.
_BREAKOUT_RISE = [100.0 + i for i in range(25)]
_BREAKOUT_FALL = [_BREAKOUT_RISE[-1] - 2 * i for i in range(1, 15)]
_BREAKOUT_PATH = _BREAKOUT_RISE + _BREAKOUT_FALL

_BREAKOUT_ENTRY_INDEX = BREAKOUT_ENTRY_WINDOW - 1
_BREAKOUT_EXIT_INDEX = 27


def test_breakout_stays_flat_until_the_entry_window_is_filled() -> None:
    strategy = breakout()
    partial = _BREAKOUT_PATH[:_BREAKOUT_ENTRY_INDEX]
    assert len(partial) == BREAKOUT_ENTRY_WINDOW - 1
    assert strategy(_frame(partial)) == 0.0


def test_breakout_enters_on_a_new_n_day_closing_high() -> None:
    strategy = breakout()
    assert strategy(_frame(_BREAKOUT_PATH[: _BREAKOUT_ENTRY_INDEX + 1])) == 1.0


def test_breakout_holds_a_pullback_that_has_not_broken_the_exit_line() -> None:
    strategy = breakout()
    pullback = _BREAKOUT_PATH[:_BREAKOUT_EXIT_INDEX]
    assert pullback[-1] < max(pullback)  # already off the high...
    assert strategy(_frame(pullback)) == 1.0  # ...but the exit line still holds


def test_breakout_exits_on_a_new_low_and_stays_out() -> None:
    strategy = breakout()
    assert strategy(_frame(_BREAKOUT_PATH[: _BREAKOUT_EXIT_INDEX + 1])) == 0.0
    assert strategy(_frame(_BREAKOUT_PATH)) == 0.0


def test_breakout_on_a_flat_series_takes_no_position() -> None:
    # Every close ties both the rolling high and the rolling low: the bar says
    # "breakout" and "breakdown" at once, and an ambiguous bar leaves the book
    # flat rather than long (documented in ``_replay``).
    strategy = breakout()
    assert strategy(_frame([100.0] * 40)) == 0.0


def test_breakout_windows_must_be_positive_and_ordered() -> None:
    with pytest.raises(ValueError):
        breakout(entry_window=0)
    with pytest.raises(ValueError):
        breakout(exit_window=0)
    with pytest.raises(ValueError):
        breakout(entry_window=10, exit_window=20)
    assert callable(breakout(entry_window=BREAKOUT_ENTRY_WINDOW, exit_window=BREAKOUT_EXIT_WINDOW))


def test_new_strategies_read_only_the_window_they_are_given() -> None:
    # Same prefix, same answer, whatever comes after it in the longer series --
    # the property that makes the engine's point-in-time slicing meaningful.
    prefix_len = _RSI_ENTRY_INDEX + 1
    for strategy in (rsi_reversal(), breakout()):
        from_prefix = strategy(_frame(_RSI_PATH[:prefix_len]))
        from_longer = strategy(_frame(_RSI_PATH)[:prefix_len])
        assert from_prefix == from_longer


# --- CEO 2026-09-09 回測: the five price-only 觀察條件 --------------------------


def _five_condition_path(n: int = 400, seed: int = 20260909) -> tuple[list[float], list[int]]:
    """A deterministic path on which all five conditions do co-occur.

    Noise is not decoration here. A smooth sine leaves RSI saturated at its
    extremes and a constant volume column leaves the z-score undefined, so a
    textbook wave would keep every one of the five conditions from ever holding
    together and would make this whole section vacuous. The seed is fixed, so
    the indices pinned below are golden values, not a lucky draw.
    """
    rng = np.random.default_rng(seed)
    t = np.arange(n, dtype="float64")
    closes = 100.0 + 12.0 * np.sin(2.0 * np.pi * t / 90.0) + rng.normal(0.0, 1.2, n).cumsum()
    volumes = 20_000.0 + 6_000.0 * np.sin(2.0 * np.pi * t / 13.0) + rng.normal(0.0, 2_500.0, n)
    return [round(float(c), 4) for c in closes], [int(v) for v in volumes]


_FIVE_CLOSES, _FIVE_VOLUMES = _five_condition_path()

#: Verified against ``five_condition_series`` on the path above: bar 128 is the
#: first on which all five conditions hold, the position it opens is stopped out
#: on bar 130, and the position opened on bar 197 leaves on bar 224 through the
#: MA60 exit *alone* (the stop is not touched there) -- which is what lets the
#: three exit branches be told apart end to end.
_FIVE_ENTRY_INDEX = 128
_FIVE_STOP_EXIT_INDEX = 130
_FIVE_SECOND_ENTRY_INDEX = 197
_FIVE_TREND_EXIT_INDEX = 224


def _five_frame(upto: int | None = None) -> pd.DataFrame:
    closes = _FIVE_CLOSES if upto is None else _FIVE_CLOSES[:upto]
    volumes = _FIVE_VOLUMES if upto is None else _FIVE_VOLUMES[:upto]
    return bars_to_frame(bars_from_closes(closes, volumes=volumes))


def test_five_conditions_is_flat_through_the_warmup_window() -> None:
    # 60 bars is the binding requirement (MA60 and the panel's own 60-bar floor
    # for a range position); one bar short means flat, never a partial verdict.
    strategy = five_conditions()
    assert FIVE_CONDITIONS_WARMUP_BARS == 60
    assert strategy(_five_frame(FIVE_CONDITIONS_WARMUP_BARS - 1)) == 0.0


def test_five_conditions_enters_only_when_all_five_hold() -> None:
    strategy = five_conditions()
    series = five_condition_series(_five_frame(_FIVE_ENTRY_INDEX + 1))
    assert bool(series.all_met[-1])
    assert strategy(_five_frame(_FIVE_ENTRY_INDEX + 1)) == 1.0
    # The bar before is the counter-example: at least one condition is missing,
    # so the book is flat rather than "close enough".
    before = five_condition_series(_five_frame(_FIVE_ENTRY_INDEX))
    assert not bool(before.all_met[-1])
    assert strategy(_five_frame(_FIVE_ENTRY_INDEX)) == 0.0


def test_five_conditions_exits_on_the_panel_stop_level() -> None:
    strategy = five_conditions()
    entry_price = _FIVE_CLOSES[_FIVE_ENTRY_INDEX]
    series = five_condition_series(_five_frame(_FIVE_STOP_EXIT_INDEX + 1))
    stop = five_condition_stop_level(entry_price, float(series.atr[-1]))
    assert _FIVE_CLOSES[_FIVE_STOP_EXIT_INDEX] <= stop
    assert strategy(_five_frame(_FIVE_STOP_EXIT_INDEX + 1)) == 0.0
    # Still holding the bar before -- the exit is the stop being reached, not
    # the mere passage of time.
    assert strategy(_five_frame(_FIVE_STOP_EXIT_INDEX)) == 1.0


def test_five_conditions_exits_when_the_trend_leg_breaks_alone() -> None:
    # The entry thesis includes 收盤 > MA60; when only that fails (the stop is
    # nowhere near and the take-profit is far above) the position still ends.
    strategy = five_conditions()
    entry_price = _FIVE_CLOSES[_FIVE_SECOND_ENTRY_INDEX]
    series = five_condition_series(_five_frame(_FIVE_TREND_EXIT_INDEX + 1))
    close = _FIVE_CLOSES[_FIVE_TREND_EXIT_INDEX]
    assert close < float(series.ma60[-1])
    assert close > five_condition_stop_level(entry_price, float(series.atr[-1]))
    assert close < entry_price * FIVE_TAKE_PROFIT_RATIO
    assert strategy(_five_frame(_FIVE_TREND_EXIT_INDEX + 1)) == 0.0
    assert strategy(_five_frame(_FIVE_TREND_EXIT_INDEX)) == 1.0


def test_five_conditions_re_enters_only_on_a_fresh_all_five_bar() -> None:
    # Between the stop-out and the next entry the book is flat: an exit does not
    # leave a stale entry flag that drifts back into a position.
    strategy = five_conditions()
    for index in range(_FIVE_STOP_EXIT_INDEX, _FIVE_SECOND_ENTRY_INDEX):
        assert strategy(_five_frame(index + 1)) == 0.0, index
    assert strategy(_five_frame(_FIVE_SECOND_ENTRY_INDEX + 1)) == 1.0


def test_five_conditions_takes_no_position_without_a_volume_z_score() -> None:
    # A flat volume column has zero variance, so the z-score is undefined and
    # condition 5 can never be met. The strategy stays flat instead of treating
    # an undecidable condition as satisfied -- the same posture the panel takes
    # when it prints 「—」 rather than 「成立」.
    strategy = five_conditions()
    frame = _frame(_FIVE_CLOSES)  # helper's default: one constant volume
    series = five_condition_series(frame)
    assert np.isnan(series.volume_z).all()
    assert not series.volume.any()
    assert not series.all_met.any()
    assert strategy(frame) == 0.0


# --- the five conditions, one boundary at a time -------------------------------


def test_range_position_condition_is_inclusive_at_seventy_percent() -> None:
    # keyLevels.ts takes the range from the trailing highs/lows and the panel
    # calls an exact 70.00% "met" (its own 1e-9 epsilon), so the boundary is
    # inclusive on this side too.
    closes = [100.0, 200.0] + [150.0] * (FIVE_RANGE_MIN_BARS - 3)
    at_boundary = five_condition_series(_frame([*closes, 170.0]))
    assert at_boundary.range_position_pct[-1] == pytest.approx(FIVE_RANGE_MAX_PCT)
    assert bool(at_boundary.range_position[-1])
    above = five_condition_series(_frame([*closes, 170.1]))
    assert above.range_position_pct[-1] > FIVE_RANGE_MAX_PCT
    assert not bool(above.range_position[-1])


def test_range_position_is_undecidable_before_sixty_bars_or_on_a_flat_range() -> None:
    short = five_condition_series(_frame([100.0 + i for i in range(FIVE_RANGE_MIN_BARS - 1)]))
    assert np.isnan(short.range_position_pct[-1])
    assert not bool(short.range_position[-1])
    flat = five_condition_series(_frame([100.0] * FIVE_RANGE_MIN_BARS))
    assert np.isnan(flat.range_position_pct[-1])
    assert not bool(flat.range_position[-1])


def test_trend_condition_is_strictly_above_ma60() -> None:
    # An exact tie is not "above": the panel's comparison is `close > ma60`.
    tie = five_condition_series(_frame([100.0] * 60))
    assert tie.ma60[-1] == pytest.approx(100.0)
    assert not bool(tie.trend[-1])
    above = five_condition_series(_frame([100.0] * 59 + [100.5]))
    assert above.ma60[-1] < 100.5
    assert bool(above.trend[-1])


def test_pullback_condition_is_inclusive_at_three_percent() -> None:
    # Solve for the close that sits exactly +3% above the MA20 it is part of.
    body = [100.0] * 19
    total = sum(body)
    ratio = 1.0 + FIVE_PULLBACK_MAX_ABS_PCT / 100.0
    boundary_close = ratio * total / (20.0 - ratio)
    at_boundary = five_condition_series(_frame([*body, boundary_close]))
    assert bool(at_boundary.pullback[-1])
    beyond = five_condition_series(_frame([*body, boundary_close * 1.001]))
    assert not bool(beyond.pullback[-1])


def test_pullback_condition_is_undecidable_before_ma20_exists() -> None:
    series = five_condition_series(_frame([100.0 + i for i in range(19)]))
    assert np.isnan(series.ma20[-1])
    assert not bool(series.pullback[-1])


def test_momentum_condition_is_the_signal_layer_rsi_mid_band() -> None:
    # Equality against the published RSI(14), bar by bar: the strategy reads the
    # same number ``GET /api/signals`` does, and the band excludes both ends.
    frame = _five_frame()
    series = five_condition_series(frame)
    published = rsi_series(frame[CLOSE], period=RSI_PERIOD).to_numpy()
    expected = (published > FIVE_RSI_LOW) & (published < FIVE_RSI_HIGH)
    assert np.array_equal(series.momentum, expected)
    # Teeth: a saturated RSI is outside the band on both sides.
    assert not bool(five_condition_series(_frame([100.0 + i for i in range(30)])).momentum[-1])
    assert not bool(five_condition_series(_frame([100.0 - i for i in range(30)])).momentum[-1])


def test_volume_condition_is_the_signal_layer_z_score_mid_band() -> None:
    bars = bars_from_closes(_FIVE_CLOSES, volumes=_FIVE_VOLUMES)
    series = five_condition_series(bars_to_frame(bars))
    published = np.asarray(
        [np.nan if z is None else z for z in volume_zscore(bars).series["zscore"]],
        dtype="float64",
    )
    assert series.volume_z == pytest.approx(published, nan_ok=True)
    expected = (published > -FIVE_VOLUME_Z_ABS_MAX) & (published < FIVE_VOLUME_Z_ABS_MAX)
    assert np.array_equal(series.volume, expected)


# --- the path-dependent exit replay --------------------------------------------


def _stop_replay(
    *, closes: list[float], entries: list[bool], atr: list[float], ma60: list[float]
) -> float:
    return _replay_with_stop_levels(
        entries=np.asarray(entries, dtype=bool),
        close=np.asarray(closes, dtype="float64"),
        atr=np.asarray(atr, dtype="float64"),
        ma60=np.asarray(ma60, dtype="float64"),
    )


def test_replay_holds_while_no_exit_level_is_reached() -> None:
    assert _stop_replay(
        closes=[100.0, 99.9], entries=[True, False], atr=[1.0, 1.0], ma60=[90.0, 90.0]
    ) == 1.0


def test_replay_leaves_on_each_exit_branch_independently() -> None:
    # Stop: 100 - 2*ATR(1.0) = 98 is the tighter of the two stops (the fixed one
    # sits at 92), and the close reaches it.
    assert _stop_replay(
        closes=[100.0, 98.0], entries=[True, False], atr=[1.0, 1.0], ma60=[90.0, 90.0]
    ) == 0.0
    # Take profit at +20%.
    assert _stop_replay(
        closes=[100.0, 100.0 * FIVE_TAKE_PROFIT_RATIO],
        entries=[True, False],
        atr=[1.0, 1.0],
        ma60=[90.0, 90.0],
    ) == 0.0
    # Trend break alone: above both stops, far below the target.
    assert _stop_replay(
        closes=[100.0, 99.0], entries=[True, False], atr=[1.0, 1.0], ma60=[90.0, 99.5]
    ) == 0.0


def test_replay_falls_back_to_the_fixed_stop_without_an_atr() -> None:
    fixed = 100.0 * FIVE_STOP_FIXED_RATIO
    assert five_condition_stop_level(100.0, float("nan")) == fixed
    assert _stop_replay(
        closes=[100.0, fixed], entries=[True, False], atr=[np.nan, np.nan], ma60=[90.0, 90.0]
    ) == 0.0
    assert _stop_replay(
        closes=[100.0, fixed + 0.01],
        entries=[True, False],
        atr=[np.nan, np.nan],
        ma60=[90.0, 90.0],
    ) == 1.0


def test_replay_ignores_an_entry_flag_while_already_holding() -> None:
    # A repeated entry flag does not re-anchor the stop on a later, higher close;
    # if it did, the position would be exited by its own follow-through.
    weight = _stop_replay(
        closes=[100.0, 110.0, 105.0],
        entries=[True, True, False],
        atr=[1.0, 1.0, 1.0],
        ma60=[90.0, 90.0, 90.0],
    )
    assert weight == 1.0  # anchored at 100: stop 98, target 120 -- neither reached


def test_replay_can_re_enter_after_an_exit() -> None:
    assert _stop_replay(
        closes=[100.0, 90.0, 95.0],
        entries=[True, False, True],
        atr=[1.0, 1.0, 1.0],
        ma60=[80.0, 80.0, 80.0],
    ) == 1.0


# --- point-in-time and look-ahead ----------------------------------------------


def test_five_condition_series_is_trailing_only() -> None:
    # The event study evaluates the conditions once over the whole frame while
    # the strategy re-evaluates them on each point-in-time slice. If the two ever
    # disagreed, the vectorised one would be reading bars that did not exist yet.
    frame = _five_frame()
    whole = five_condition_series(frame)
    for t in range(FIVE_CONDITIONS_WARMUP_BARS - 1, len(frame)):
        sliced = five_condition_series(frame.iloc[: t + 1].copy())
        assert bool(sliced.all_met[-1]) == bool(whole.all_met[t]), t


def test_five_conditions_reacts_to_a_one_bar_feature_shift() -> None:
    # backtest-protocol rule 2, applied to this strategy: feed it tomorrow's
    # close (fills still happen at the real closes) and the result must move
    # materially. A strategy that barely notices is one already reading ahead.
    frame = _five_frame()
    zero_cost = CostModel(
        tw_broker_fee_rate=0.0,
        tw_tax_rate_stock=0.0,
        tw_tax_rate_etf=0.0,
        us_sell_regulatory_fee_rate=0.0,
        slippage_bps=0.0,
    )
    shifted = np.asarray([*_FIVE_CLOSES[1:], _FIVE_CLOSES[-1]], dtype="float64")

    def leaking(window: pd.DataFrame) -> float:
        leaked = window.copy()
        leaked[CLOSE] = shifted[: len(window)]
        return five_conditions()(leaked)

    base = run_backtest(frame, five_conditions(), initial_cash=10_000.0, cost_model=zero_cost)
    assert base.trades
    leaked = run_backtest(frame, leaking, initial_cash=10_000.0, cost_model=zero_cost)
    relative_change = abs(leaked.equity_curve[-1] - base.equity_curve[-1]) / base.equity_curve[-1]
    assert relative_change > 0.01, (
        f"five_conditions barely changed when fed tomorrow's close ({relative_change:.4%})"
    )

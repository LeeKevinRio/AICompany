"""Tests for the shipped strategies, including their look-ahead safety."""

from __future__ import annotations

import pandas as pd
import pytest

from app.backtest.strategies import (
    BREAKOUT_ENTRY_WINDOW,
    BREAKOUT_EXIT_WINDOW,
    DEFAULT_SLOW_WINDOW,
    RSI_ENTRY_THRESHOLD,
    RSI_EXIT_THRESHOLD,
    STRATEGY_IDS,
    STRATEGY_WARMUP_BARS,
    breakout,
    build_strategy,
    ma_cross,
    rsi_reversal,
)
from app.signals.frame import CLOSE, bars_to_frame
from app.signals.technical import RSI_PERIOD, rsi, rsi_series
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
    assert STRATEGY_IDS == ("ma_cross", "rsi_reversal", "breakout")
    assert STRATEGY_WARMUP_BARS["ma_cross"] == DEFAULT_SLOW_WINDOW
    assert STRATEGY_WARMUP_BARS["rsi_reversal"] == RSI_PERIOD + 1
    assert STRATEGY_WARMUP_BARS["breakout"] == BREAKOUT_ENTRY_WINDOW
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

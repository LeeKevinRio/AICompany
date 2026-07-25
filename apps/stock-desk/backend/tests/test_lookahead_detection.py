"""Look-ahead detection -- the load-bearing safety net of the backtester.

Two complementary guards, per backtest-protocol rule 2 and rule 1:

1. **Shift sensitivity (statistical).** Take a signal-driven strategy, run it,
   then shift the *whole signal series forward one bar* (injecting one bar of
   future knowledge) and run again. A point-in-time-correct pipeline must react
   to that shift: if performance is "unreasonably almost unchanged" the pipeline
   is insensitive to one-bar alignment, which is the fingerprint of a
   look-ahead leak, and the test fails. We also show the detector's teeth by
   demonstrating that a deliberately shift-insensitive (constant) signal
   produces exactly the near-zero change the detector is built to catch.

2. **Structural (direct).** A strategy that tries to read a future bar cannot:
   the engine only ever hands it the sliced-to-today window, so the future bar
   is physically absent (raises), not merely off-limits by convention.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from app.backtest.costs import CostModel
from app.backtest.engine import Strategy, run_backtest
from app.signals.frame import bars_to_frame
from tests.signals_helpers import bars_from_closes

# Relative end-equity change below this, after a one-bar signal shift, is treated
# as "unreasonably almost unchanged" -> a look-ahead red flag.
SHIFT_SENSITIVITY_THRESHOLD = 0.01

ZERO_COST = CostModel(
    tw_broker_fee_rate=0.0,
    tw_tax_rate_stock=0.0,
    tw_tax_rate_etf=0.0,
    us_sell_regulatory_fee_rate=0.0,
    slippage_bps=0.0,
)


def _reversing_closes() -> list[float]:
    # Up, down, up, down: a path where *when* you are long genuinely matters, so
    # a one-bar timing shift must move the result if alignment is real.
    steps = np.concatenate(
        [np.full(15, 1.0), np.full(15, -1.2), np.full(15, 0.8), np.full(15, -0.5)]
    )
    return list(100.0 + np.cumsum(steps))


def _feature_driven_strategy(feature: np.ndarray) -> Strategy:
    """A strategy that returns ``feature[current_index]`` (index = len(window)-1)."""

    def strategy(window: pd.DataFrame) -> float:
        return float(feature[len(window) - 1])

    return strategy


def _end_equity_relative_change(frame: pd.DataFrame, feature: np.ndarray) -> float:
    """Rerun with the feature shifted forward one bar; return relative end-equity change."""
    base = run_backtest(
        frame, _feature_driven_strategy(feature), initial_cash=10_000.0, cost_model=ZERO_COST
    )
    shifted = np.empty_like(feature)
    shifted[:-1] = feature[1:]
    shifted[-1] = feature[-1]
    leaked = run_backtest(
        frame, _feature_driven_strategy(shifted), initial_cash=10_000.0, cost_model=ZERO_COST
    )
    return abs(leaked.equity_curve[-1] - base.equity_curve[-1]) / base.equity_curve[-1]


def test_pipeline_is_sensitive_to_a_one_bar_signal_shift() -> None:
    closes = _reversing_closes()
    frame = bars_to_frame(bars_from_closes(closes))
    lag = 3
    n = len(closes)
    # Point-in-time momentum: feature[t] uses only closes at or before t.
    feature = np.zeros(n)
    for t in range(n):
        feature[t] = 1.0 if t >= lag and closes[t] > closes[t - lag] else 0.0

    rel_change = _end_equity_relative_change(frame, feature)
    # A one-bar shift must move performance; near-zero change would signal that
    # the engine already effectively used shifted (future) data.
    assert rel_change > SHIFT_SENSITIVITY_THRESHOLD, (
        f"performance barely changed under a one-bar shift ({rel_change:.4%}); "
        "possible look-ahead leak"
    )


def test_detector_flags_a_shift_insensitive_pipeline() -> None:
    # A constant signal ignores the shift entirely -> near-zero change. This is
    # exactly the failure fingerprint the detector above is designed to catch,
    # proving the guard discriminates rather than always passing.
    closes = _reversing_closes()
    frame = bars_to_frame(bars_from_closes(closes))
    constant_feature = np.ones(len(closes))
    rel_change = _end_equity_relative_change(frame, constant_feature)
    assert rel_change < SHIFT_SENSITIVITY_THRESHOLD


def test_strategy_reading_future_bar_is_blocked_by_the_engine() -> None:
    frame = bars_to_frame(bars_from_closes([10.0, 11.0, 12.0, 13.0]))

    def peeking(window: pd.DataFrame) -> float:
        # Attempt to read the bar *after* today; it is not in the point-in-time
        # slice, so this raises instead of silently leaking the future.
        _future = window.iloc[len(window)]
        return 1.0

    with pytest.raises(IndexError):
        run_backtest(frame, peeking, cost_model=ZERO_COST)

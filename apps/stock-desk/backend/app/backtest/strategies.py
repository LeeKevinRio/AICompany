"""The built-in, named strategies a backtest request may reference.

A strategy is a :data:`app.backtest.engine.Strategy`: it receives the history
**sliced at the current bar** and returns a target weight. It therefore reads
only ``window`` -- never a captured outer frame -- which is what keeps the
engine's structural no-look-ahead guarantee intact (backtest-protocol rule 1).

Only one strategy ships today (``ma_cross``). It exists to make the backtest
endpoint end-to-end runnable and to give the walk-forward report something real
to measure; it is a textbook example, not a recommendation, and nothing in the
product proposes trading it.
"""

from __future__ import annotations

from collections.abc import Mapping

import pandas as pd

from app.backtest.engine import Strategy
from app.signals.frame import CLOSE

#: Default windows of the shipped moving-average crossover.
DEFAULT_FAST_WINDOW = 20
DEFAULT_SLOW_WINDOW = 60


def ma_cross(
    *, fast: int = DEFAULT_FAST_WINDOW, slow: int = DEFAULT_SLOW_WINDOW
) -> Strategy:
    """Long while ``MA(fast) > MA(slow)``, flat otherwise (long-only, all-or-nothing).

    Before ``slow`` bars exist the slow average is undefined, so the strategy is
    flat rather than acting on a partial window -- the same "missing input means
    no claim" rule the signal layer follows.
    """
    if fast <= 0 or slow <= 0:
        raise ValueError("moving-average windows must be positive")
    if fast >= slow:
        raise ValueError("fast window must be shorter than the slow window")

    def strategy(window: pd.DataFrame) -> float:
        if len(window) < slow:
            return 0.0
        close = window[CLOSE]
        fast_ma = float(close.iloc[-fast:].mean())
        slow_ma = float(close.iloc[-slow:].mean())
        if pd.isna(fast_ma) or pd.isna(slow_ma):  # pragma: no cover - frame is float-clean
            return 0.0
        return 1.0 if fast_ma > slow_ma else 0.0

    return strategy


#: Strategy id -> how many bars it needs before it can take any position. The
#: API validates a request against these keys, so an unknown id is a 422 rather
#: than a lookup of arbitrary code.
STRATEGY_WARMUP_BARS: Mapping[str, int] = {"ma_cross": DEFAULT_SLOW_WINDOW}

#: The strategy ids the API accepts, in a stable order for the schema.
STRATEGY_IDS: tuple[str, ...] = tuple(STRATEGY_WARMUP_BARS)


def build_strategy(name: str) -> Strategy:
    """Return the named strategy, or raise ``KeyError`` for an unknown id."""
    if name == "ma_cross":
        return ma_cross()
    raise KeyError(name)

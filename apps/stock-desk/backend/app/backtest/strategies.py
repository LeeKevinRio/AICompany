"""The built-in, named strategies a backtest request may reference.

A strategy is a :data:`app.backtest.engine.Strategy`: it receives the history
**sliced at the current bar** and returns a target weight. It therefore reads
only ``window`` -- never a captured outer frame -- which is what keeps the
engine's structural no-look-ahead guarantee intact (backtest-protocol rule 1).

Three strategies ship (FR-10/FR-11 added the second and third): ``ma_cross``
(trend following), ``rsi_reversal`` (mean reversion) and ``breakout`` (classic
range breakout). They exist to make the backtest endpoint end-to-end runnable
and to give the walk-forward report something real to measure; each is a
textbook example, not a recommendation, and nothing in the product proposes
trading any of them.

Every strategy here is long-only and all-or-nothing (weight 1.0 or 0.0), matches
``ma_cross``'s "not enough bars -> flat" rule, and takes its parameters from
module constants rather than from the request (FR-10/FR-11 範圍外: the user does
not tune strategy internals from the form).

Two of the three need to know whether they are *currently* in a position, which
a plain "today's weight" function does not carry between calls. They rebuild
that state by replaying their own entry/exit flags over the window they were
handed (:func:`_replay`). Replaying is what keeps them pure functions of the
point-in-time slice: no captured outer frame, no state surviving a rerun, so the
engine's structural no-look-ahead guarantee still holds.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping

import numpy as np
import pandas as pd

from app.backtest.engine import Strategy
from app.signals.frame import CLOSE
from app.signals.technical import RSI_PERIOD, rsi_series

#: Default windows of the shipped moving-average crossover.
DEFAULT_FAST_WINDOW = 20
DEFAULT_SLOW_WINDOW = 60

#: FR-10 thresholds. 30 is Wilder's original oversold line (J. Welles Wilder Jr.,
#: *New Concepts in Technical Trading Systems*, 1978, the paper that defines the
#: RSI this product computes). The exit sits at the 50 mid-line because the trade
#: thesis is "an oversold reading reverts towards the middle": it ends when the
#: middle is reached. Exiting at the 70 overbought line instead would silently
#: turn a mean-reversion strategy into a trend-following one and stop being a
#: complement to ``ma_cross``.
RSI_ENTRY_THRESHOLD = 30.0
RSI_EXIT_THRESHOLD = 50.0

#: FR-11 windows: enter on a 20-day closing high, leave on a 10-day closing low.
#: This 20/10 pair is the published Turtle "System 1" geometry (Faith, *Way of
#: the Turtles*, 2007) -- the canonical parameterisation of a breakout system,
#: chosen for that provenance rather than fitted here. The exit window is the
#: shorter of the two by design: a breakout gives back less of a move when it
#: leaves on a faster line than the one it entered on.
BREAKOUT_ENTRY_WINDOW = 20
BREAKOUT_EXIT_WINDOW = 10


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


def _replay(entries: np.ndarray, exits: np.ndarray) -> float:
    """Fold per-bar entry/exit flags into today's target weight.

    Long-only and all-or-nothing: the book is either fully in or fully out, and
    an entry flag while already long (or an exit flag while already flat) is a
    no-op rather than a second trade. A bar that raises *both* flags leaves the
    book flat -- an ambiguous bar is not a reason to be holding risk.
    """
    holding = False
    for enter, leave in zip(entries, exits, strict=True):
        if holding:
            if leave:
                holding = False
        elif enter and not leave:
            holding = True
    return 1.0 if holding else 0.0


def rsi_reversal(
    *,
    period: int = RSI_PERIOD,
    entry_level: float = RSI_ENTRY_THRESHOLD,
    exit_level: float = RSI_EXIT_THRESHOLD,
) -> Strategy:
    """Long from an oversold RSI until it recovers to the mid-line (FR-10).

    Enters when RSI(``period``) is at or below ``entry_level`` and the book is
    flat; leaves when it is at or above ``exit_level``. While RSI is undefined
    (the first ``period + 1`` bars have not been seen yet) the strategy stays
    flat rather than acting on a partial window -- ``ma_cross``'s rule and the
    signal layer's "missing input means no claim" rule, applied here.

    The RSI itself comes from :func:`app.signals.technical.rsi_series`, so the
    number this trades on is the same number the signal layer publishes.
    """
    if period <= 0:
        raise ValueError("RSI period must be positive")
    if not 0.0 < entry_level < exit_level < 100.0:
        raise ValueError("RSI thresholds must satisfy 0 < entry < exit < 100")

    def strategy(window: pd.DataFrame) -> float:
        if len(window) < period + 1:
            return 0.0
        values = rsi_series(window[CLOSE], period=period).to_numpy()
        defined = ~np.isnan(values)
        entries = defined & (values <= entry_level)
        exits = defined & (values >= exit_level)
        return _replay(entries, exits)

    return strategy


def breakout(
    *,
    entry_window: int = BREAKOUT_ENTRY_WINDOW,
    exit_window: int = BREAKOUT_EXIT_WINDOW,
) -> Strategy:
    """Long on an ``entry_window``-day closing high, out on an ``exit_window``-day low (FR-11).

    "New high" means the close *is* the highest close of the trailing window
    including today (AC-11.1), so a flat series where every close ties the high
    does not read as a fresh breakout on every bar -- it reads as one entry that
    is then held. Before either window is filled the strategy is flat.
    """
    if entry_window <= 0 or exit_window <= 0:
        raise ValueError("breakout windows must be positive")
    if exit_window > entry_window:
        raise ValueError("exit window must not be longer than the entry window")

    def strategy(window: pd.DataFrame) -> float:
        if len(window) < entry_window:
            return 0.0
        close = window[CLOSE]
        highest = close.rolling(window=entry_window, min_periods=entry_window).max()
        lowest = close.rolling(window=exit_window, min_periods=exit_window).min()
        # A NaN (still-seeding) bound compares False, so no flag is raised while
        # the window is incomplete.
        entries = (close >= highest).to_numpy()
        exits = (close <= lowest).to_numpy()
        return _replay(entries, exits)

    return strategy


#: Strategy id -> how many bars it needs before it can take any position. The
#: API validates a request against these keys, so an unknown id is a 422 rather
#: than a lookup of arbitrary code.
STRATEGY_WARMUP_BARS: Mapping[str, int] = {
    "ma_cross": DEFAULT_SLOW_WINDOW,
    # RSI(14) is undefined until one extra bar has supplied the first change.
    "rsi_reversal": RSI_PERIOD + 1,
    "breakout": BREAKOUT_ENTRY_WINDOW,
}

#: The strategy ids the API accepts, in a stable order for the schema.
STRATEGY_IDS: tuple[str, ...] = tuple(STRATEGY_WARMUP_BARS)

#: Builders keyed by the same ids, so a strategy can never be advertised by the
#: API without being constructible (or the reverse).
_BUILDERS: Mapping[str, Callable[[], Strategy]] = {
    "ma_cross": ma_cross,
    "rsi_reversal": rsi_reversal,
    "breakout": breakout,
}

assert frozenset(_BUILDERS) == frozenset(STRATEGY_WARMUP_BARS)


def build_strategy(name: str) -> Strategy:
    """Return the named strategy, or raise ``KeyError`` for an unknown id."""
    return _BUILDERS[name]()

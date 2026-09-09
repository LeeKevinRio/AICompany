"""The built-in, named strategies a backtest request may reference.

A strategy is a :data:`app.backtest.engine.Strategy`: it receives the history
**sliced at the current bar** and returns a target weight. It therefore reads
only ``window`` -- never a captured outer frame -- which is what keeps the
engine's structural no-look-ahead guarantee intact (backtest-protocol rule 1).

Four strategies ship (FR-10/FR-11 added the second and third; CEO 2026-09-09
回測 added the fourth): ``ma_cross`` (trend following), ``rsi_reversal`` (mean
reversion), ``breakout`` (classic range breakout) and ``five_conditions`` (the
price-only rows of the 六項觀察條件 panel). They exist to make the backtest
endpoint end-to-end runnable and to give the walk-forward report something real
to measure; each is a textbook example, not a recommendation, and nothing in the
product proposes trading any of them.

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
from dataclasses import dataclass

import numpy as np
import pandas as pd

from app.backtest.engine import Strategy
from app.signals.frame import CLOSE, HIGH, LOW, VOLUME
from app.signals.technical import (
    ATR_PERIOD,
    RSI_PERIOD,
    VOLUME_Z_THRESHOLD,
    VOLUME_Z_WINDOW,
    rsi_series,
)

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


# --- CEO 2026-09-09 回測：六項觀察條件面板的前五條 ---------------------------
#
# The 六項觀察條件 panel (frontend/app/lib/entryObservation.ts, PRD
# work/stock-desk-進場觀察條件-PRD.md) evaluates six fixed conditions on the
# position page. Five of them are functions of OHLCV alone and can therefore be
# recomputed bar by bar from a point-in-time window; the sixth (「建議引擎本次
# 未命中任何防禦型方向規則」) depends on the holding state and on the advice rule
# engine, neither of which exists inside a price-only backtest, so it is **not**
# part of this strategy and not part of the event study either. Every number
# below is therefore about FIVE conditions, never six -- see
# ``work/stock-desk-五條件回測-方法論.md``.
#
# Thresholds are the panel's own fixed constants, mirrored here as module
# constants: they are never read from a request (a user does not tune strategy
# internals from the form) and never re-derived from anything.

#: Condition 1 位階: trailing range window and the minimum history the panel
#: requires before it will state a range position at all (``keyLevels.ts``:
#: ``RANGE_BARS`` / ``RECENT_BARS``). With fewer than 252 bars the range spans
#: whatever history exists, exactly as the panel does.
FIVE_RANGE_WINDOW = 252
FIVE_RANGE_MIN_BARS = 60
FIVE_RANGE_MAX_PCT = 70.0

#: Condition 2 趨勢 (close > MA60) and condition 3 拉回 (|close/MA20 - 1| <= 3%).
FIVE_TREND_MA_WINDOW = 60
FIVE_PULLBACK_MA_WINDOW = 20
FIVE_PULLBACK_MAX_ABS_PCT = 3.0

#: Conditions 4 動能 and 5 量能 are the panel's "mid band" of ``indicatorBands.ts``:
#: strictly *between* the two levels (30/70 for RSI, ±2 for the volume z-score),
#: endpoints excluded. Both levels are the signal layer's own constants, imported
#: rather than re-typed, so the strategy trades the numbers the API publishes.
#: On the volume side the panel's band and the indicator's own ``anomaly`` flag
#: differ at exactly |z| = 2 (the band excludes it, the flag needs a strict
#: ``>``); the panel defines the condition, so the panel's reading is the one
#: reproduced here.
FIVE_RSI_LOW = 30.0
FIVE_RSI_HIGH = 70.0
FIVE_VOLUME_Z_WINDOW = VOLUME_Z_WINDOW
FIVE_VOLUME_Z_ABS_MAX = VOLUME_Z_THRESHOLD

#: The panel's epsilon on its two ``<=`` comparisons, kept identical so an exact
#: 70.00% / ±3.00% reads the same way on both sides of the product.
FIVE_THRESHOLD_EPSILON = 1e-9

#: Exit parameters, taken from the panel's 關鍵價位參考 block (``keyLevels.ts``):
#: stop = max(entry - 2*ATR(14), entry * 0.92) -- the *tighter* (higher) of the
#: two, which is the level the panel leads with -- and take profit =
#: entry * 1.20. Only the ATR *period* is shared with the signal layer; the panel
#: computes ATR(14) as a **simple mean of the last 14 true ranges**, not Wilder's
#: smoothing, and this strategy reproduces the panel's definition on purpose (the
#: question being backtested is "what did the levels this page shows do", not
#: "what does the signal layer's ATR do"). The divergence is disclosed in the
#: methodology document.
FIVE_STOP_ATR_PERIOD = ATR_PERIOD
FIVE_STOP_ATR_MULTIPLE = 2.0
FIVE_STOP_FIXED_RATIO = 0.92
FIVE_TAKE_PROFIT_RATIO = 1.2

#: Bars needed before any of the five verdicts can be true at once: MA60 and the
#: panel's 60-bar minimum for a range position are the binding ones.
FIVE_CONDITIONS_WARMUP_BARS = max(FIVE_RANGE_MIN_BARS, FIVE_TREND_MA_WINDOW)


@dataclass(frozen=True)
class FiveConditionSeries:
    """Per-bar verdicts (and the numbers behind them) for the five conditions.

    Every array is aligned to the frame it was computed from and is
    **trailing-only**: the value at position ``t`` reads bars ``<= t`` and
    nothing else, which is what lets the same function serve the point-in-time
    strategy (recomputed on each sliced window) and the vectorised event study
    (computed once over the whole frame). ``tests/test_backtest_strategies.py``
    pins that the two agree bar for bar; if they ever stopped agreeing, the
    vectorised path would be the one reading the future.

    A boolean is ``False`` both when the condition is *unmet* and when its input
    is undefined (still seeding, zero-width range, zero-variance volume). The
    panel keeps those two apart on screen ("未成立" vs "無法判定"); a backtest
    cannot act on an undecidable condition either way, so both mean "no entry
    today" here. The observed-value arrays carry ``NaN`` at exactly the
    undefined bars, so the distinction is still recoverable.
    """

    range_position: np.ndarray
    trend: np.ndarray
    pullback: np.ndarray
    momentum: np.ndarray
    volume: np.ndarray
    #: The observed numbers, ``NaN`` where undefined.
    range_position_pct: np.ndarray
    ma20: np.ndarray
    ma60: np.ndarray
    rsi: np.ndarray
    volume_z: np.ndarray
    #: ATR(14) in the panel's simple-mean definition (used by the exit only).
    atr: np.ndarray

    @property
    def all_met(self) -> np.ndarray:
        """True on bars where all five conditions hold at once."""
        met: np.ndarray = (
            self.range_position & self.trend & self.pullback & self.momentum & self.volume
        )
        return met


def five_condition_series(frame: pd.DataFrame) -> FiveConditionSeries:
    """Evaluate the five price-only panel conditions on every bar of ``frame``.

    Rolling windows only, all of them backward-looking with ``min_periods``
    equal to the window (or to the panel's stated minimum), so no value at bar
    ``t`` can depend on a bar after ``t``. Comparisons against ``NaN`` are
    ``False``, which is how an undefined input becomes "no entry" rather than an
    accidental "met".
    """
    close = frame[CLOSE]
    high = frame[HIGH]
    low = frame[LOW]

    # 1) 位階: the panel takes the range from HIGHS and LOWS over the trailing
    # 252 bars but refuses to state a position with fewer than 60 bars, and
    # refuses again when the range has zero width (a halted / flat series).
    range_high = high.rolling(window=FIVE_RANGE_WINDOW, min_periods=FIVE_RANGE_MIN_BARS).max()
    range_low = low.rolling(window=FIVE_RANGE_WINDOW, min_periods=FIVE_RANGE_MIN_BARS).min()
    span = (range_high - range_low).where(range_high > range_low)
    range_position_pct = (close - range_low) / span * 100.0
    range_ok = range_position_pct <= FIVE_RANGE_MAX_PCT + FIVE_THRESHOLD_EPSILON

    # 2) 趨勢 and 3) 拉回.
    ma60 = close.rolling(window=FIVE_TREND_MA_WINDOW, min_periods=FIVE_TREND_MA_WINDOW).mean()
    ma20 = close.rolling(
        window=FIVE_PULLBACK_MA_WINDOW, min_periods=FIVE_PULLBACK_MA_WINDOW
    ).mean()
    trend_ok = close > ma60
    distance_pct = (close / ma20.where(ma20 > 0.0) - 1.0) * 100.0
    pullback_ok = distance_pct.abs() <= FIVE_PULLBACK_MAX_ABS_PCT + FIVE_THRESHOLD_EPSILON

    # 4) 動能: the signal layer's own RSI(14), mid band, endpoints excluded.
    rsi = rsi_series(close, period=RSI_PERIOD)
    momentum_ok = (rsi > FIVE_RSI_LOW) & (rsi < FIVE_RSI_HIGH)

    # 5) 量能: the signal layer's 20-bar population (ddof=0) volume z-score, mid
    # band, endpoints excluded. A zero-variance window leaves z undefined -- the
    # same "missing input means no claim" rule the indicator itself follows.
    volume = frame[VOLUME]
    vol_mean = volume.rolling(window=FIVE_VOLUME_Z_WINDOW, min_periods=FIVE_VOLUME_Z_WINDOW).mean()
    vol_std = volume.rolling(
        window=FIVE_VOLUME_Z_WINDOW, min_periods=FIVE_VOLUME_Z_WINDOW
    ).std(ddof=0)
    volume_z = (volume - vol_mean).where(vol_std != 0.0) / vol_std.where(vol_std != 0.0)
    volume_ok = (volume_z > -FIVE_VOLUME_Z_ABS_MAX) & (volume_z < FIVE_VOLUME_Z_ABS_MAX)

    return FiveConditionSeries(
        range_position=range_ok.to_numpy(dtype=bool),
        trend=trend_ok.to_numpy(dtype=bool),
        pullback=pullback_ok.to_numpy(dtype=bool),
        momentum=momentum_ok.to_numpy(dtype=bool),
        volume=volume_ok.to_numpy(dtype=bool),
        range_position_pct=range_position_pct.to_numpy(dtype="float64"),
        ma20=ma20.to_numpy(dtype="float64"),
        ma60=ma60.to_numpy(dtype="float64"),
        rsi=rsi.to_numpy(dtype="float64"),
        volume_z=volume_z.to_numpy(dtype="float64"),
        atr=_panel_atr(frame, period=FIVE_STOP_ATR_PERIOD).to_numpy(dtype="float64"),
    )


def _panel_atr(frame: pd.DataFrame, *, period: int) -> pd.Series:
    """ATR as the 關鍵價位參考 panel computes it: simple mean of ``period`` TRs.

    Deliberately **not** :func:`app.signals.technical.atr`, which applies
    Wilder's smoothing: the stop level this strategy is measuring is the one the
    panel prints, and reproducing it with a different average would measure a
    level no reader was ever shown. Needs ``period + 1`` bars (the first true
    range has no previous close), same as the panel.
    """
    prev_close = frame[CLOSE].shift(1)
    true_range = pd.concat(
        [
            frame[HIGH] - frame[LOW],
            (frame[HIGH] - prev_close).abs(),
            (frame[LOW] - prev_close).abs(),
        ],
        axis=1,
    ).max(axis=1)
    true_range.iloc[0] = np.nan  # no previous close on the first bar
    return true_range.rolling(window=period, min_periods=period).mean()


def five_condition_stop_level(entry_price: float, atr: float) -> float:
    """The panel's 停損參考水位 for a position opened at ``entry_price``.

    ``max`` of the 2×ATR stop and the fixed −8% stop, i.e. the *tighter* of the
    two, which is the one the panel leads with. An undefined ATR leaves the
    fixed stop as the only candidate -- again the panel's own fallback.
    """
    fixed = entry_price * FIVE_STOP_FIXED_RATIO
    if np.isnan(atr):
        return fixed
    return max(entry_price - FIVE_STOP_ATR_MULTIPLE * atr, fixed)


def _replay_with_stop_levels(
    *,
    entries: np.ndarray,
    close: np.ndarray,
    atr: np.ndarray,
    ma60: np.ndarray,
) -> float:
    """Fold entry flags plus entry-price-dependent exits into today's weight.

    The path-dependent sibling of :func:`_replay`, and it exists because the
    exits here cannot be pre-computed into a flag array: two of the three
    reference the price the position was opened at, which is not a property of
    the bar being tested. Everything else is the same discipline -- long-only,
    all-or-nothing, state rebuilt by replaying the window that was handed in, so
    the strategy stays a pure function of its point-in-time slice.

    Exits, evaluated at each bar's close while holding:

    * ``close <= max(entry - 2*ATR(14), entry * 0.92)`` -- the panel's stop
      reference, recomputed each bar because the panel itself recomputes it from
      the latest ATR against a fixed anchor (the position's cost);
    * ``close >= entry * 1.20`` -- the panel's fixed take-profit reference;
    * ``close < MA60`` -- the entry thesis's trend leg (condition 2) has failed.

    Exits are checked before entries, so a bar can never open and close a
    position at once. Nothing here can fire on the entry bar itself: an entry
    requires ``close > MA60`` and ``close`` sits strictly between the −8% stop
    and the +20% target of itself.
    """
    holding = False
    entry_price = 0.0
    for i in range(len(close)):
        price = close[i]
        if holding:
            stop = five_condition_stop_level(entry_price, atr[i])
            take_profit = entry_price * FIVE_TAKE_PROFIT_RATIO
            trend_broken = not np.isnan(ma60[i]) and price < ma60[i]
            if price <= stop or price >= take_profit or trend_broken:
                holding = False
        elif entries[i]:
            holding = True
            entry_price = price
    return 1.0 if holding else 0.0


def five_conditions() -> Strategy:
    """Long while the five price-only panel conditions all held at entry.

    Enters when every one of 位階 ≤ 70% / 收盤 > MA60 / |收盤÷MA20 − 1| ≤ 3% /
    30 < RSI(14) < 70 / −2 < 成交量 z(20) < 2 is true on the same bar and the
    book is flat. Leaves on the panel's own stop and take-profit references, or
    when the trend leg of the entry breaks (see
    :func:`_replay_with_stop_levels`).

    **The panel's sixth condition is not here.** 「建議引擎本次未命中任何防禦型
    方向規則」 needs the holding state and the advice rule engine, so it cannot
    be evaluated from a price series at all; this strategy therefore answers a
    strictly *narrower* question than the panel asks, and every number it
    produces must be read as "five of the six", never as "the panel".

    Flat until :data:`FIVE_CONDITIONS_WARMUP_BARS` bars exist, matching
    ``ma_cross``'s "not enough bars -> flat" rule.
    """

    def strategy(window: pd.DataFrame) -> float:
        if len(window) < FIVE_CONDITIONS_WARMUP_BARS:
            return 0.0
        series = five_condition_series(window)
        return _replay_with_stop_levels(
            entries=series.all_met,
            close=window[CLOSE].to_numpy(dtype="float64"),
            atr=series.atr,
            ma60=series.ma60,
        )

    return strategy


#: Strategy id -> how many bars it needs before it can take any position. The
#: API validates a request against these keys, so an unknown id is a 422 rather
#: than a lookup of arbitrary code.
STRATEGY_WARMUP_BARS: Mapping[str, int] = {
    "ma_cross": DEFAULT_SLOW_WINDOW,
    # RSI(14) is undefined until one extra bar has supplied the first change.
    "rsi_reversal": RSI_PERIOD + 1,
    "breakout": BREAKOUT_ENTRY_WINDOW,
    "five_conditions": FIVE_CONDITIONS_WARMUP_BARS,
}

#: The strategy ids the API accepts, in a stable order for the schema.
STRATEGY_IDS: tuple[str, ...] = tuple(STRATEGY_WARMUP_BARS)

#: Builders keyed by the same ids, so a strategy can never be advertised by the
#: API without being constructible (or the reverse).
_BUILDERS: Mapping[str, Callable[[], Strategy]] = {
    "ma_cross": ma_cross,
    "rsi_reversal": rsi_reversal,
    "breakout": breakout,
    "five_conditions": five_conditions,
}

assert frozenset(_BUILDERS) == frozenset(STRATEGY_WARMUP_BARS)


def build_strategy(name: str) -> Strategy:
    """Return the named strategy, or raise ``KeyError`` for an unknown id."""
    return _BUILDERS[name]()

"""The one place returns are computed (ADR-0012 D-4, C-18).

Equal weight at the start of the window, held through it:
``R_g(t,L) = mean_{i in C_g(t,L)} (P_i(t) / P_i(t-L) - 1)``. No daily
rebalancing: chaining daily equal-weight returns would rebalance every day and
bias small caps upwards through bid-ask bounce (methodology §2.2).

Everything here reads a :class:`~app.data.panel.PointInTimePanel`, so the only
prices reachable are those knowable at the close of the decision date. The
lookback window is ``L`` visible sessions before the decision date plus the
decision date itself: ``(t-L, t]`` for returns, with ``P(t-L)`` as the base.

Means use :func:`math.fsum` over symbols in sorted order, so a result never
depends on set iteration order -- T-5 compares outputs bit for bit.
"""

from __future__ import annotations

import math
from collections.abc import Collection, Mapping
from datetime import date

import pandas as pd

from app.data.panel import PointInTimePanel

#: Turnover ratio windows (methodology §4: 5-day mean over 20-day mean).
TURNOVER_SHORT_SESSIONS = 5
TURNOVER_LONG_SESSIONS = 20


def require_pit_view(panel: object) -> PointInTimePanel:
    """C-14: the core reads a ``PointInTimePanel`` only -- never raw frames or a MarketPanel."""
    if not isinstance(panel, PointInTimePanel):
        raise TypeError("the sector core accepts a PointInTimePanel only (ADR-0012 C-14)")
    return panel


def trailing_window(panel: PointInTimePanel, sessions_before: int) -> tuple[date, ...] | None:
    """``sessions_before`` visible sessions before the decision date, then the date itself.

    ``None`` when the panel does not reach back that far. The decision date is
    appended even when no bar exists on it yet: every name then lacks the
    closing price and falls into category ① instead of silently shifting the
    window to an earlier day.
    """
    t = require_pit_view(panel).decision_date
    prior = panel.sessions_before(t, sessions_before)
    if len(prior) < sessions_before:
        return None
    return (*prior, t)


def lookback_window(panel: PointInTimePanel, lookback_days: int) -> tuple[date, ...] | None:
    """The ``L + 1`` sessions ``t-L .. t`` a lookback return is built from."""
    return trailing_window(panel, lookback_days)


def window_closes(
    panel: PointInTimePanel, symbols: Collection[str], window: tuple[date, ...]
) -> pd.DataFrame:
    """Closing prices ``window x symbols`` (NaN where a bar is absent)."""
    return require_pit_view(panel).field_matrix("close", window, sorted(symbols))


def complete_symbols(closes: pd.DataFrame) -> frozenset[str]:
    """Symbols with a positive close on every session of the window."""
    ok = closes.notna().all(axis=0) & (closes > 0).all(axis=0)
    return frozenset(str(symbol) for symbol in closes.columns[ok.to_numpy()])


def daily_limit_breaches(closes: pd.DataFrame, limit: float) -> frozenset[str]:
    """Symbols whose close-to-close move inside the window exceeds ``limit`` (category ③)."""
    if len(closes.index) < 2:
        return frozenset()
    moves = (closes / closes.shift(1) - 1.0).iloc[1:]
    breached = (moves.abs() > limit).any(axis=0)
    return frozenset(str(symbol) for symbol in closes.columns[breached.to_numpy()])


def member_returns(
    panel: PointInTimePanel, symbols: Collection[str], lookback_days: int
) -> dict[str, float]:
    """``P_i(t) / P_i(t-L) - 1`` for every symbol with a complete window.

    Symbols with any gap are left out; deciding what a gap means (category ①)
    is :func:`app.sectors.universe.calculation_set`'s job, not this one's.
    """
    window = lookback_window(panel, lookback_days)
    if window is None or not symbols:
        return {}
    closes = window_closes(panel, symbols, window)
    complete = complete_symbols(closes)
    base = closes.iloc[0]
    last = closes.iloc[-1]
    return {symbol: float(last[symbol]) / float(base[symbol]) - 1.0 for symbol in sorted(complete)}


def mean_return(returns: Mapping[str, float], members: Collection[str]) -> float | None:
    """Equal-weight mean of ``returns`` over ``members`` (R_g or R_EW); None when empty."""
    if not members:
        return None
    values = [returns[symbol] for symbol in sorted(members)]
    return math.fsum(values) / len(values)


def up_count(returns: Mapping[str, float], members: Collection[str]) -> int:
    """「上漲 k／n 家」's k: members with a strictly positive lookback return."""
    return sum(1 for symbol in members if returns[symbol] > 0.0)


def top_contributor_share(returns: Mapping[str, float], members: Collection[str]) -> float | None:
    """Largest single member's share of the summed absolute returns (methodology §2.1)."""
    magnitudes = [abs(returns[symbol]) for symbol in sorted(members)]
    total = math.fsum(magnitudes)
    if not magnitudes or total == 0.0:
        return None
    return max(magnitudes) / total


def turnover_value_ratio_5_20(panel: PointInTimePanel, members: Collection[str]) -> float | None:
    """Mean sector traded value over 5 sessions / over 20 (20 includes the 5).

    Descriptive only, detail view only, never a ranking input (C-26). A
    member without a bar on a session contributes 0 that day.
    """
    window = trailing_window(panel, TURNOVER_LONG_SESSIONS - 1)
    if window is None or not members:
        return None
    values = panel.field_matrix("traded_value", window, sorted(members)).fillna(0.0)
    daily = [math.fsum(float(v) for v in row) for row in values.to_numpy()]
    long_mean = math.fsum(daily) / len(daily)
    if long_mean <= 0.0:
        return None
    short_mean = math.fsum(daily[-TURNOVER_SHORT_SESSIONS:]) / TURNOVER_SHORT_SESSIONS
    return short_mean / long_mean

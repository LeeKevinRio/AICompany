"""Shared helpers for the 1.2.0 pre-assessment (T1/T4/L-6/L-7).

Read-only: demo bars are built in memory (app.demo.seed.build_demo_bars), no DB,
no network. Point-in-time: day t sees bars dated [t - 540d, t] only.
"""
from __future__ import annotations

import bisect
import sys
from datetime import date, timedelta

import numpy as np

BACKEND = "/home/user/AICompany/apps/stock-desk/backend"
if BACKEND not in sys.path:
    sys.path.insert(0, BACKEND)

from app.api.signals import DEFAULT_LOOKBACK_DAYS  # noqa: E402
from app.signals.risk import current_drawdown  # noqa: E402

DEMO_END = date(2026, 10, 2)
LOOKBACK = DEFAULT_LOOKBACK_DAYS  # 540 calendar days
WINDOW_BARS = 370  # ~540 calendar days of TW trading days, for synthetic GBM only


def demo_series(end: date = DEMO_END) -> dict[str, tuple[list[date], np.ndarray]]:
    from app.demo.seed import build_demo_bars

    out = {}
    for sym, bars in build_demo_bars(today=end).items():
        bars = sorted(bars, key=lambda b: b.date)
        out[sym] = ([b.date for b in bars], np.array([float(b.close) for b in bars]))
    return out


def pit_drawdown(dates: list[date], closes: np.ndarray, lookback: int = LOOKBACK):
    """Per day: current drawdown, peak index (absolute), window start index, partial flag.

    Uses the app's own ``current_drawdown`` on the exact 540-day window.
    """
    n = len(dates)
    cur = np.full(n, np.nan)
    peak_idx = np.full(n, -1)
    win_start = np.zeros(n, dtype=int)
    partial = np.zeros(n, dtype=bool)
    for i in range(n):
        start = dates[i] - timedelta(days=lookback)
        j0 = bisect.bisect_left(dates, start)
        win_start[i] = j0
        partial[i] = start < dates[0]
        seg = closes[j0 : i + 1]
        res = current_drawdown(seg.tolist())
        if res is None:
            continue
        cur[i] = res[0]
        peak_idx[i] = j0 + res[1]
    return cur, peak_idx, win_start, partial


def sma(x: np.ndarray, k: int) -> np.ndarray:
    out = np.full(len(x), np.nan)
    if len(x) >= k:
        c = np.cumsum(np.insert(x, 0, 0.0))
        out[k - 1 :] = (c[k:] - c[:-k]) / k
    return out


def runs(mask: np.ndarray) -> list[tuple[int, int, bool]]:
    """(start, end_inclusive, value) runs of a boolean array."""
    out = []
    if len(mask) == 0:
        return out
    s = 0
    for i in range(1, len(mask) + 1):
        if i == len(mask) or mask[i] != mask[s]:
            out.append((s, i - 1, bool(mask[s])))
            s = i
    return out

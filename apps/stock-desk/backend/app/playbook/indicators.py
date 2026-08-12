"""Indicators the playbook rules read, computed straight from price bars.

MA25 and BIAS25 do not exist in :mod:`app.signals` (which ships 5/20/60) and the
rule set needs them per symbol on the 依據資料日, together with the index's
monthly line, its run of closes below that line, and the two fast-market
measurements (CEO 裁決六).

Everything here is a measurement over closing prices, returns ``None`` when the
window is longer than the history available, and never pads or interpolates --
an undefined indicator is what makes 鐵律⑤ fire, so faking one would silence the
data-gap rule.
"""

from __future__ import annotations

import math
from collections.abc import Sequence
from decimal import Decimal

from app.data.interface import PriceBar

#: Trading days per year used to annualise the 20-day volatility. Matches
#: ``app.leverage.drag.TRADING_DAYS_PER_YEAR``'s convention; restated here so
#: the playbook does not import the leveraged-ETF package for one constant.
TRADING_DAYS_PER_YEAR = 252

#: 100 as a Decimal, for percentage conversions.
_HUNDRED = Decimal("100")


def sorted_closes(bars: Sequence[PriceBar]) -> list[PriceBar]:
    """Bars ordered oldest -> newest, so every window ends at the latest close."""
    return sorted(bars, key=lambda bar: bar.date)


def moving_average(bars: Sequence[PriceBar], window: int) -> Decimal | None:
    """Simple moving average of the last ``window`` closes, or ``None``."""
    if window <= 0 or len(bars) < window:
        return None
    ordered = sorted_closes(bars)[-window:]
    total = sum((bar.close for bar in ordered), Decimal("0"))
    return total / Decimal(window)


def bias(close: Decimal, ma: Decimal | None) -> Decimal | None:
    """BIAS in percent: ``(close - ma) / ma * 100``; ``None`` without an MA."""
    if ma is None or ma == 0:
        return None
    return (close - ma) / ma * _HUNDRED


def change_pct(bars: Sequence[PriceBar]) -> Decimal | None:
    """漲跌幅 in percent of the latest bar against the one before it."""
    ordered = sorted_closes(bars)
    if len(ordered) < 2:
        return None
    previous = ordered[-2].close
    if previous == 0:
        return None
    return (ordered[-1].close - previous) / previous * _HUNDRED


def consecutive_days_below(bars: Sequence[PriceBar], window: int) -> int:
    """How many trailing sessions closed below their own moving average.

    Walks backwards from the latest bar, recomputing the average at each step,
    so "連 3 日低於月線" is decided on each day's own monthly line rather than on
    today's line applied to older closes. Sessions where the average is not yet
    defined stop the count -- an undefined line is not a session "below" it.
    """
    ordered = sorted_closes(bars)
    count = 0
    for end in range(len(ordered), 0, -1):
        history = ordered[:end]
        ma = moving_average(history, window)
        if ma is None or history[-1].close >= ma:
            break
        count += 1
    return count


def annualized_volatility(bars: Sequence[PriceBar], window: int = 20) -> float | None:
    """Annualised standard deviation of the last ``window`` daily log returns, %.

    ``None`` when fewer than ``window + 1`` closes are available (``window``
    returns need one extra bar) or when a close is non-positive, where the log
    return is undefined. Sample standard deviation (``ddof=1``) is used: this is
    a sample of sessions, not the population of them.
    """
    ordered = sorted_closes(bars)
    if len(ordered) < window + 1:
        return None
    closes = [float(bar.close) for bar in ordered[-(window + 1) :]]
    if any(price <= 0 for price in closes):
        return None
    returns = [math.log(closes[i] / closes[i - 1]) for i in range(1, len(closes))]
    mean = sum(returns) / len(returns)
    variance = sum((value - mean) ** 2 for value in returns) / (len(returns) - 1)
    return math.sqrt(variance) * math.sqrt(TRADING_DAYS_PER_YEAR) * 100.0


def large_move_days(bars: Sequence[PriceBar], *, lookback: int, threshold: Decimal) -> int:
    """Sessions among the last ``lookback`` whose |漲跌幅| reached ``threshold`` %."""
    ordered = sorted_closes(bars)
    if len(ordered) < 2:
        return 0
    moves: list[Decimal] = []
    for index in range(1, len(ordered)):
        previous = ordered[index - 1].close
        if previous == 0:
            continue
        moves.append((ordered[index].close - previous) / previous * _HUNDRED)
    return sum(1 for move in moves[-lookback:] if abs(move) >= threshold)

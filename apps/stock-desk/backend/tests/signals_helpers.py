"""Shared builders for signal/backtest tests: deterministic synthetic bars.

Kept out of ``conftest`` so the factories can be imported explicitly where
golden values depend on the exact construction.
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal

from app.data.interface import Market, PriceBar

_BASE_DATE = date(2024, 1, 1)
_AS_OF = datetime(2024, 3, 1, 14, 0, tzinfo=UTC)


def make_bar(
    *,
    day_offset: int,
    close: float,
    high: float | None = None,
    low: float | None = None,
    open_: float | None = None,
    volume: int = 1_000,
    symbol: str = "TEST",
    market: Market = "TW",
    source: str = "twse",
) -> PriceBar:
    """One bar ``day_offset`` days after the base date. High/low default around close."""
    hi = close if high is None else high
    lo = close if low is None else low
    op = close if open_ is None else open_
    return PriceBar(
        symbol=symbol,
        market=market,
        date=_BASE_DATE + timedelta(days=day_offset),
        open=Decimal(str(op)),
        high=Decimal(str(hi)),
        low=Decimal(str(lo)),
        close=Decimal(str(close)),
        volume=volume,
        currency="TWD" if market == "TW" else "USD",
        as_of=_AS_OF,
        source=source,
    )


def bars_from_closes(
    closes: Sequence[float],
    *,
    symbol: str = "TEST",
    market: Market = "TW",
    volume: int = 1_000,
    source: str = "twse",
) -> list[PriceBar]:
    """Consecutive daily bars from a close series (high=low=open=close)."""
    return [
        make_bar(
            day_offset=i,
            close=c,
            volume=volume,
            symbol=symbol,
            market=market,
            source=source,
        )
        for i, c in enumerate(closes)
    ]

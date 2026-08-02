"""Shared builders for the leveraged-ETF chapter tests.

Kept beside ``signals_helpers`` (same rationale: golden values depend on the
exact construction, so the factories are imported explicitly, not injected).
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import UTC, date, datetime
from decimal import Decimal

from app.data.interface import Market, PriceBar
from app.positions.models import InstrumentType, Position

BASE_DATE = date(2024, 1, 1)


def make_position(
    *,
    symbol: str = "00631L",
    instrument_type: InstrumentType = "leveraged_etf",
    market: Market = "TW",
    opened_at: date | None = BASE_DATE,
    quantity: str = "1000",
    avg_cost: str = "50",
) -> Position:
    """A stored position with the fields this chapter actually reads."""
    now = datetime(2024, 3, 1, 14, 0, tzinfo=UTC)
    return Position(
        id=1,
        symbol=symbol,
        market=market,
        quantity=Decimal(quantity),
        avg_cost=Decimal(avg_cost),
        currency="TWD" if market == "TW" else "USD",
        opened_at=opened_at,
        instrument_type=instrument_type,
        note=None,
        created_at=now,
        updated_at=now,
    )


def zigzag_closes(*, amplitude: float, returns: int, start: float = 100.0) -> list[float]:
    """A perfectly sideways path: up ``amplitude``, back to ``start``, repeat.

    With an even ``returns`` the series ends exactly at ``start``, so the index
    cumulative return is 0 and every bit of the leveraged fund's shortfall is
    daily-reset compounding rather than direction.
    """
    closes = [start]
    for i in range(returns):
        closes.append(start * (1.0 + amplitude) if i % 2 == 0 else start)
    return closes


def ideal_leveraged_closes(
    index_closes: Sequence[float],
    *,
    leverage_factor: float,
    expense_ratio_annual: float = 0.0,
    trading_days_per_year: int = 252,
    start: float = 100.0,
) -> list[float]:
    """A fund that tracks ``leverage_factor`` x the index every single day.

    With ``expense_ratio_annual > 0`` a flat daily fee factor is applied to NAV,
    which is what a real fund does and what the *linear* fee approximation in
    :mod:`app.leverage.drag` only approximates.
    """
    fee_factor = 1.0 - expense_ratio_annual / trading_days_per_year
    closes = [start]
    for i in range(1, len(index_closes)):
        r = index_closes[i] / index_closes[i - 1] - 1.0
        closes.append(closes[-1] * (1.0 + leverage_factor * r) * fee_factor)
    return closes


def bars(
    closes: Sequence[float],
    *,
    symbol: str,
    market: Market = "TW",
    source: str = "twse",
) -> list[PriceBar]:
    """Consecutive daily bars from a close series (open=high=low=close)."""
    out: list[PriceBar] = []
    for i, close in enumerate(closes):
        price = Decimal(str(close))
        out.append(
            PriceBar(
                symbol=symbol,
                market=market,
                date=date.fromordinal(BASE_DATE.toordinal() + i),
                open=price,
                high=price,
                low=price,
                close=price,
                volume=1_000,
                currency="TWD" if market == "TW" else "USD",
                as_of=datetime(2024, 3, 1, 14, 0, tzinfo=UTC),
                source=source,
            )
        )
    return out

"""Fakes and fixtures shared by the Phase 6 API and alert tests.

Everything here is offline by construction: the fake price service and FX
provider satisfy the same protocols the production adapters do, so a router can
be exercised end to end -- dependency wiring, degradation states, response shape
-- without a network call or a real vendor adapter.

Bars are generated **ending today** because the symbol-scoped endpoints request
``[today - lookback, today]``; a fixture pinned to a fixed past date would fall
outside that window and silently test the "no data" path instead.
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal

from app.data.interface import DataStatus, Market, PriceBar, ProviderResult
from app.data.providers.fx import FxRateProvider, FxRateResult

_AS_OF = datetime(2026, 7, 25, 6, 0, tzinfo=UTC)


def recent_bars(
    closes: Sequence[float],
    *,
    symbol: str = "2330",
    market: Market = "TW",
    currency: str | None = None,
    source: str = "fake",
    end: date | None = None,
    volume: int = 10_000,
) -> list[PriceBar]:
    """Consecutive daily bars whose **last** bar is ``end`` (default: today)."""
    last = end if end is not None else date.today()
    unit = currency or ("TWD" if market == "TW" else "USD")
    count = len(closes)
    return [
        PriceBar(
            symbol=symbol,
            market=market,
            date=last - timedelta(days=count - 1 - index),
            open=Decimal(str(close)),
            high=Decimal(str(close)),
            low=Decimal(str(close)),
            close=Decimal(str(close)),
            volume=volume,
            currency=unit,
            as_of=_AS_OF,
            source=source,
        )
        for index, close in enumerate(closes)
    ]


def trending_closes(count: int, *, start: float = 100.0, step: float = 0.5) -> list[float]:
    """A deterministic gently-rising close series (no randomness in a fixture)."""
    return [round(start + step * index, 4) for index in range(count)]


def oscillating_closes(count: int, *, base: float = 100.0, amplitude: float = 10.0) -> list[float]:
    """A deterministic saw-tooth series that makes an MA crossover fire both ways."""
    closes: list[float] = []
    for index in range(count):
        # 120-bar period: long enough that MA20 crosses MA60 in both directions.
        phase = (index % 120) / 120.0
        closes.append(round(base + amplitude * (1.0 - abs(phase - 0.5) * 4.0), 4))
    return closes


class FakePriceService:
    """A ``PriceService`` returning canned bars, filtered by the requested range.

    ``status`` / ``source`` / ``staleness_minutes`` are plain attributes so a
    test can flip the fake onto a degraded rung of the ladder (backup, stale
    cache) and assert the response discloses it.
    """

    def __init__(
        self,
        bars: dict[str, list[PriceBar]] | None = None,
        *,
        status: DataStatus = DataStatus.FRESH,
        source: str = "fake",
        staleness_minutes: int | None = 0,
    ) -> None:
        self.bars = dict(bars or {})
        self.status = status
        self.source = source
        self.staleness_minutes = staleness_minutes
        #: Every call made, so a test can assert the range that was requested.
        self.calls: list[tuple[str, Market, date, date]] = []

    def seed(self, symbol: str, bars: list[PriceBar]) -> None:
        """Make ``symbol`` resolvable to ``bars``."""
        self.bars[symbol] = bars

    def get_daily_bars(
        self, symbol: str, market: Market, start: date, end: date
    ) -> ProviderResult:
        self.calls.append((symbol, market, start, end))
        window = [bar for bar in self.bars.get(symbol, []) if start <= bar.date <= end]
        if not window:
            return ProviderResult(
                bars=[],
                status=DataStatus.UNAVAILABLE,
                as_of=_AS_OF,
                source="none",
                staleness_minutes=None,
            )
        return ProviderResult(
            bars=window,
            status=self.status,
            as_of=_AS_OF,
            source=self.source,
            staleness_minutes=self.staleness_minutes,
        )


class UnavailableFxProvider(FxRateProvider):
    """An FX provider that always reports ``unavailable`` (never fabricates a rate)."""

    source_id = "fake_fx_unavailable"

    def get_daily_rates(self, pair: str, start: date, end: date) -> FxRateResult:
        return FxRateResult(
            rates=[], status=DataStatus.UNAVAILABLE, as_of=_AS_OF, source=self.source_id
        )


def position_payload(**overrides: object) -> dict[str, object]:
    """A valid ``POST /api/positions`` body, ready to be mutated per test."""
    payload: dict[str, object] = {
        "symbol": "2330",
        "market": "TW",
        "quantity": "1000",
        "avg_cost": "600",
        "currency": "TWD",
        "opened_at": "2024-01-02",
        "instrument_type": "stock",
        "note": None,
    }
    payload.update(overrides)
    return payload

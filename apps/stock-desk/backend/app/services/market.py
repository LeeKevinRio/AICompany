"""One market-aware bar loader for every consumer of price data.

``MarketDataService`` is per-market (TW has a provider chain, US has none yet),
so callers need a map from market to service plus a single, consistent answer
for "there is no adapter for this market". :func:`load_bars` is that answer: it
returns a :class:`LoadedBars` whose ``reason`` is a Traditional Chinese sentence
the API can show verbatim, and never raises for an expected failure.

The distinction the whole product rests on is preserved here: **no bars is a
state, not an error**. A market with no adapter, a provider chain that came back
empty, and a cache miss are three different reasons, all reported as
``insufficient_data`` with the reason attached, never as a 500 and never as a
fabricated series.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import date

from app.data.interface import DataStatus, PriceBar
from app.portfolio.valuation import PriceService
from app.positions.models import Market

#: market -> the service that can quote it. A market absent from the map has no
#: adapter at all (US today).
MarketDataResolver = Mapping[Market, PriceService]

NO_ADAPTER_REASON = "目前沒有 {market} 市場的行情來源，無法取得日線資料。"
NO_BARS_REASON = "{market} {symbol} 在指定區間內沒有可用的日線資料（主來源、備援與快取皆無）。"


@dataclass(frozen=True)
class LoadedBars:
    """Bars plus the provenance every downstream response has to carry."""

    bars: list[PriceBar] = field(default_factory=list)
    status: DataStatus = DataStatus.UNAVAILABLE
    source: str = "none"
    staleness_minutes: int | None = None
    reason: str | None = None

    def meta(self) -> dict[str, object]:
        """The ``data`` block echoed on every endpoint that loads bars."""
        first = min((bar.date for bar in self.bars), default=None)
        last = max((bar.date for bar in self.bars), default=None)
        return {
            "status": self.status.value,
            "source": self.source,
            "staleness_minutes": self.staleness_minutes,
            "bar_count": len(self.bars),
            "first_bar_date": first.isoformat() if first is not None else None,
            "last_bar_date": last.isoformat() if last is not None else None,
            "reason": self.reason,
        }


def load_bars(
    resolver: MarketDataResolver,
    *,
    symbol: str,
    market: Market,
    start: date,
    end: date,
) -> LoadedBars:
    """Load daily bars for ``symbol``, degrading to an explained empty result."""
    service = resolver.get(market)
    if service is None:
        return LoadedBars(reason=NO_ADAPTER_REASON.format(market=market))
    result = service.get_daily_bars(symbol, market, start, end)
    if result.status is DataStatus.UNAVAILABLE or not result.bars:
        return LoadedBars(
            status=result.status,
            source=result.source,
            staleness_minutes=result.staleness_minutes,
            reason=NO_BARS_REASON.format(market=market, symbol=symbol),
        )
    return LoadedBars(
        bars=list(result.bars),
        status=result.status,
        source=result.source,
        staleness_minutes=result.staleness_minutes,
    )

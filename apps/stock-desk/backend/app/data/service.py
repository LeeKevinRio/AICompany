"""Degradation orchestration: primary provider -> backup(s) -> cache -> unavailable.

This is the only entry point application code should use to fetch price
bars; it never talks to a vendor adapter directly. Every layer of the
ladder is explicit and every returned ``ProviderResult`` says exactly which
layer answered (``DataStatus``) and how stale the data is.
"""

from __future__ import annotations

import logging
from collections.abc import Callable, Sequence
from datetime import UTC, date, datetime

from app.data.cache import PriceBarCache
from app.data.interface import DataStatus, Market, MarketDataProvider, ProviderResult

logger = logging.getLogger(__name__)


class MarketDataService:
    """Fetch daily bars for a symbol, degrading through providers then cache.

    Order of attempts:
      1. ``primary`` provider -> status=``fresh`` on success.
      2. Each of ``backups`` in order -> status=``backup`` on success.
      3. Local SQLite cache (``cache``) -> status=``cached_stale`` if any
         rows are found for the requested range, regardless of TTL (this is
         the last resort, so partial/old data beats nothing).
      4. ``status=unavailable`` with an empty bar list -- never fabricated
         or interpolated data.

    Every successful live fetch is written through to the cache so it is
    available for a later degrade-to-cache fallback.
    """

    def __init__(
        self,
        *,
        primary: MarketDataProvider,
        backups: Sequence[MarketDataProvider] = (),
        cache: PriceBarCache,
        clock: Callable[[], datetime] = lambda: datetime.now(UTC),
    ) -> None:
        self._primary = primary
        self._backups = tuple(backups)
        self._cache = cache
        self._clock = clock

    def get_daily_bars(
        self, symbol: str, market: Market, start: date, end: date
    ) -> ProviderResult:
        providers: list[tuple[MarketDataProvider, DataStatus]] = [
            (self._primary, DataStatus.FRESH),
            *((backup, DataStatus.BACKUP) for backup in self._backups),
        ]

        for provider, status in providers:
            result = self._try_provider(provider, symbol, start, end)
            if result is None or result.status is DataStatus.UNAVAILABLE or not result.bars:
                continue
            self._cache.put(result.bars, source=result.source, fetched_at=self._clock())
            return ProviderResult(
                bars=result.bars,
                status=status,
                as_of=result.as_of,
                source=result.source,
                staleness_minutes=0,
            )

        return self._fall_back_to_cache(symbol, market, start, end)

    def _try_provider(
        self, provider: MarketDataProvider, symbol: str, start: date, end: date
    ) -> ProviderResult | None:
        try:
            return provider.get_daily_bars(symbol, start, end)
        except Exception:  # a buggy adapter must not take the whole service down
            logger.exception(
                "provider %s raised while fetching %s; degrading to next layer",
                getattr(provider, "source_id", provider.__class__.__name__),
                symbol,
            )
            return None

    def _fall_back_to_cache(
        self, symbol: str, market: Market, start: date, end: date
    ) -> ProviderResult:
        now = self._clock()
        cached = self._cache.get(symbol, market, start, end, now=now)
        if cached is not None:
            logger.warning(
                "all providers unavailable for %s; serving cached data (%d min stale)",
                symbol,
                cached.staleness_minutes,
            )
            return ProviderResult(
                bars=cached.bars,
                status=DataStatus.CACHED_STALE,
                as_of=cached.fetched_at,
                source=cached.source,
                staleness_minutes=cached.staleness_minutes,
            )

        logger.error("no provider and no cache entry available for %s", symbol)
        return ProviderResult(
            bars=[],
            status=DataStatus.UNAVAILABLE,
            as_of=now,
            source="none",
            staleness_minutes=None,
        )

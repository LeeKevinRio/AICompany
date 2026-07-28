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

    ``cache_first`` (ADR-0005 決策四, "TTL 內快取先行" -- a revision to
    ADR-0003's four-layer ladder, adding a "layer 0" ahead of the primary
    provider): when ``True``, a cache entry that is still within its TTL is
    served immediately, without calling any provider at all. This exists
    because Alpha Vantage's daily quota is cheap to burn through on repeat
    requests for the same symbol within the same day (e.g. a page reload),
    and the quota ledger (``app.data.quota.QuotaLedger``) alone cannot help
    with that -- it only stops *new* symbols once the day's budget is spent,
    it does nothing to avoid spending budget on a symbol already fetched an
    hour ago. Per ADR-0005, ``cache_first`` must stay ``False`` for the TW
    service (Taiwan has no comparable quota pressure) so this class's
    existing behaviour for TW is unchanged byte-for-byte when the flag is
    left at its default.
    """

    def __init__(
        self,
        *,
        primary: MarketDataProvider,
        backups: Sequence[MarketDataProvider] = (),
        cache: PriceBarCache,
        clock: Callable[[], datetime] = lambda: datetime.now(UTC),
        cache_first: bool = False,
    ) -> None:
        self._primary = primary
        self._backups = tuple(backups)
        self._cache = cache
        self._clock = clock
        self._cache_first = cache_first

    def get_daily_bars(
        self, symbol: str, market: Market, start: date, end: date
    ) -> ProviderResult:
        if self._cache_first:
            layer_zero = self._try_ttl_fresh_cache(symbol, market, start, end)
            if layer_zero is not None:
                return layer_zero

        providers: list[tuple[MarketDataProvider, DataStatus]] = [
            (self._primary, DataStatus.FRESH),
            *((backup, DataStatus.BACKUP) for backup in self._backups),
        ]

        for provider, status in providers:
            result = self._try_provider(provider, symbol, start, end)
            if result is None:
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

    def _try_ttl_fresh_cache(
        self, symbol: str, market: Market, start: date, end: date
    ) -> ProviderResult | None:
        """``cache_first`` layer 0: serve a still-fresh cache hit, calling nobody.

        Returns ``None`` (meaning "fall through to the normal ladder") when
        there is no cached data for this range, or when what is cached has
        already aged past the TTL -- an expired cache entry must not be
        assumed good enough to skip a live fetch.
        """
        now = self._clock()
        cached = self._cache.get(symbol, market, start, end, now=now)
        if cached is None or not cached.is_within_ttl:
            return None
        logger.info(
            "cache_first: serving %s from cache (%d min old, within TTL); "
            "skipping all live providers for this request",
            symbol,
            cached.staleness_minutes,
        )
        return ProviderResult(
            bars=cached.bars,
            status=DataStatus.CACHED_STALE,
            as_of=cached.fetched_at,
            source=cached.source,
            staleness_minutes=cached.staleness_minutes,
            is_within_ttl=True,
        )

    def _try_provider(
        self, provider: MarketDataProvider, symbol: str, start: date, end: date
    ) -> ProviderResult | None:
        """Call one provider, returning usable bars or ``None`` to degrade on.

        Two distinct failure modes are graded differently in the logs so they
        can be told apart:

          * Expected, in-contract degradation -- the provider returned
            ``status=UNAVAILABLE`` or an empty bar list (see the
            ``MarketDataProvider`` contract: expected failures must NOT raise).
            Logged at INFO level.
          * Unexpected provider error -- the provider raised. Per the contract
            this is a bug in the adapter, not a normal "no data" outcome, so it
            is logged via ``logger.exception`` with an explicit
            "unexpected provider error" tag (higher signal than the INFO line
            above), while still degrading to the next layer rather than taking
            the whole service down.
        """
        provider_label = getattr(provider, "source_id", provider.__class__.__name__)
        try:
            result = provider.get_daily_bars(symbol, start, end)
        except Exception:
            logger.exception(
                "unexpected provider error: %s raised while fetching %s; "
                "degrading to next layer",
                provider_label,
                symbol,
            )
            return None
        if result.status is DataStatus.UNAVAILABLE or not result.bars:
            logger.info(
                "provider %s returned no usable data (status=%s) for %s; "
                "degrading to next layer",
                provider_label,
                result.status.value,
                symbol,
            )
            return None
        return result

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
                is_within_ttl=cached.is_within_ttl,
            )

        logger.error("no provider and no cache entry available for %s", symbol)
        return ProviderResult(
            bars=[],
            status=DataStatus.UNAVAILABLE,
            as_of=now,
            source="none",
            staleness_minutes=None,
        )

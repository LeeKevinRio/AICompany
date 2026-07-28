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

#: Joins several layers' reasons into the one ``reason`` slot a
#: ``ProviderResult`` has, in ladder order.
_REASON_SEPARATOR = "；"

UNEXPECTED_ERROR_REASON = "{provider} 發生非預期錯誤，已降級至下一層。"


def _combine_reasons(reasons: Sequence[str]) -> str | None:
    """Fold every layer's own wording into one sentence, losing none of them.

    A degraded response usually has more than one cause worth stating ("no API
    key" *and* "backup unreachable"); keeping only the first would misattribute
    the failure. Each layer's text is preserved verbatim apart from a trailing
    full stop, which is re-added once at the end so the joined sentence reads
    as one.
    """
    kept = [reason.strip() for reason in reasons if reason and reason.strip()]
    if not kept:
        return None
    return _REASON_SEPARATOR.join(text.rstrip("。") for text in kept) + "。"


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

    Degradation reasons are not swallowed: every rung that declined to answer
    contributes its ``ProviderResult.reason`` to the ``reason`` of whatever
    the ladder ends up returning (the cache rung or ``unavailable``), so the
    API layer can tell a user "the daily quota is spent" instead of a generic
    "no data". A successful fetch carries no reason -- there is nothing to
    explain.
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

        # Every rung that declined to answer states why; those sentences are
        # what the API layer shows when the whole ladder comes up empty.
        reasons: list[str] = []
        for provider, status in providers:
            result, reason = self._try_provider(provider, symbol, start, end)
            if result is None:
                if reason is not None:
                    reasons.append(reason)
                continue
            self._cache.put(result.bars, source=result.source, fetched_at=self._clock())
            return ProviderResult(
                bars=result.bars,
                status=status,
                as_of=result.as_of,
                source=result.source,
                staleness_minutes=0,
            )

        return self._fall_back_to_cache(symbol, market, start, end, reasons)

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
    ) -> tuple[ProviderResult | None, str | None]:
        """Call one provider, returning ``(usable result, degradation reason)``.

        Exactly one side is ever populated: a usable result comes back with no
        reason, and a declined rung comes back as ``(None, reason)`` -- where
        the reason may still be ``None`` if the provider degraded without
        saying anything, which is the provider's own gap, not one this method
        fills in with a guess.

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
            return None, UNEXPECTED_ERROR_REASON.format(provider=provider_label)
        if result.status is DataStatus.UNAVAILABLE or not result.bars:
            logger.info(
                "provider %s returned no usable data (status=%s) for %s; "
                "degrading to next layer",
                provider_label,
                result.status.value,
                symbol,
            )
            return None, result.reason
        return result, None

    def _fall_back_to_cache(
        self,
        symbol: str,
        market: Market,
        start: date,
        end: date,
        reasons: Sequence[str] = (),
    ) -> ProviderResult:
        combined = _combine_reasons(reasons)
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
                # Why the live rungs were skipped travels with the cached
                # answer too: "served from cache" alone does not tell the
                # reader whether the quota ran out or the vendor was down.
                reason=combined,
            )

        logger.error("no provider and no cache entry available for %s", symbol)
        return ProviderResult(
            bars=[],
            status=DataStatus.UNAVAILABLE,
            as_of=now,
            source="none",
            staleness_minutes=None,
            reason=combined,
        )

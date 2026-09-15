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

from app.data.cache import CacheReadResult, PriceBarCache
from app.data.freshness import Verdict, expected_session, judge, next_weekday, policy_for
from app.data.interface import DataStatus, Market, MarketDataProvider, ProviderResult

logger = logging.getLogger(__name__)

#: Joins several layers' reasons into the one ``reason`` slot a
#: ``ProviderResult`` has, in ladder order.
_REASON_SEPARATOR = "；"

UNEXPECTED_ERROR_REASON = "{provider} 發生非預期錯誤，已降級至下一層。"
#: Carried by a cache answer served because the last live ask (inside the
#: market's cooldown) failed or came back partial -- the reader must not be
#: left thinking nothing was wrong (ADR-0003 約束 7). Wording approved by
#: risk-compliance-officer 2026-09-13 (第三輪). Reaches the screen since
#: 2026-09-15: ``load_bars`` forwards ``reason`` on a successful load and
#: ``DataMetaStatusBadge`` shows ``DataMeta.reason`` standing beside the badge.
RECENT_ATTEMPT_FAILED_REASON = "最近一次向來源取得資料未成功，暫以本機快取回覆。"


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

    ``cache_first`` (ADR-0005 決策四 "layer 0", freshness rule revised by
    ADR-0009): when ``True``, a cache that already holds the latest session
    the market has completed and published is served immediately, without
    calling any provider. The judgement is :func:`app.data.freshness.judge`
    -- session-based, not clock-based: a Friday fetch is still current on
    Sunday, and a fetch from an hour ago is *not* current once the market has
    closed and published a newer session. When the cache is short of a
    session but a live source was consulted within the market's
    ``recheck_cooldown`` and had nothing newer (holiday, close not yet
    published), the cache is served too, disclosed as stale
    (``is_within_ttl=False``), so a holiday cannot turn into a live call per
    click. Layer 0 also needs the recorded live-fetch coverage
    (:meth:`PriceBarCache.fetch_coverage`) to reach at least as far back as
    the request; otherwise a widened date range goes to the provider.

    Per ADR-0009 every ladder turns this on (TW included -- ADR-0005 D-1's
    "TW always calls the provider" is superseded); the cooldown per market is
    what protects Alpha Vantage's daily budget (ADR-0005).

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

    def get_daily_bars(self, symbol: str, market: Market, start: date, end: date) -> ProviderResult:
        if self._cache_first:
            layer_zero = self._try_session_fresh_cache(symbol, market, start, end)
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
            fetched_at = self._clock()
            self._cache.put(result.bars, source=result.source, fetched_at=fetched_at)
            # ADR-0009: the attempt log feeds the cooldown; the fetch log
            # (coverage) is written only for a complete answer, so a range
            # with a skipped month is asked for again instead of frozen in.
            self._cache.record_attempt(symbol, market, at=fetched_at)
            if result.complete:
                self._cache.record_fetch(
                    symbol, market, start=start, end=end, fetched_at=fetched_at
                )
            else:
                logger.info(
                    "partial answer for %s from %s: coverage not recorded, "
                    "the range will be asked for again",
                    symbol,
                    result.source,
                )
            return ProviderResult(
                bars=result.bars,
                status=status,
                as_of=result.as_of,
                source=result.source,
                staleness_minutes=0,
                complete=result.complete,
            )

        # Every live rung declined: remember the attempt so the cooldown applies
        # to the *next* click even though nothing was fetched (ADR-0009 R-8).
        self._cache.record_attempt(symbol, market, at=self._clock())
        return self._fall_back_to_cache(symbol, market, start, end, reasons)

    def _try_session_fresh_cache(
        self, symbol: str, market: Market, start: date, end: date
    ) -> ProviderResult | None:
        """``cache_first`` layer 0 (ADR-0009): serve the cache when no newer session can exist.

        Returns ``None`` (meaning "fall through to the normal ladder") when
        there is no cached data for this range, when no complete live fetch
        covering ``start`` is on record and no live attempt was made within
        the cooldown, or when the cache is short of the latest published
        session and nobody has asked a live source within the cooldown.
        """
        now = self._clock()
        cached = self._cache.get(symbol, market, start, end, now=now)
        if cached is None:
            return None
        policy = policy_for(market)
        coverage = self._cache.fetch_coverage(symbol, market)
        last_success = coverage.last_fetched_at if coverage is not None else None
        if coverage is None or coverage.covered_start > start:
            # Never fetched live in full (a seeded, legacy or holed cache), or
            # the request reaches further back than any complete fetch: the
            # ladder must run. The one exception (ADR-0009 R-8): the last live
            # ask -- strictly *after* the last complete success, i.e. one that
            # failed or came back partial -- is inside the cooldown, so serve
            # what we have rather than re-run the whole ladder per click. A
            # widened range right after a successful fetch is not that case.
            attempted = self._cache.last_attempt_at(symbol, market)
            if (
                attempted is not None
                and (last_success is None or attempted > last_success)
                and policy.is_within_cooldown(now, attempted)
            ):
                logger.info(
                    "cache_first: serving %s from cache after a failed live attempt %d min ago",
                    symbol,
                    (now - attempted).total_seconds() // 60,
                )
                # Age is the rows' real fetch time, never the failed attempt's
                # (風控 2026-09-13 R-10: nothing was obtained then).
                return self._cached_result(
                    cached,
                    checked_at=cached.fetched_at,
                    now=now,
                    current=False,
                    reason=RECENT_ATTEMPT_FAILED_REASON,
                )
            return None
        last_bar = max(bar.date for bar in cached.bars)
        verdict = judge(
            policy,
            last_bar_date=last_bar,
            last_checked_at=coverage.last_fetched_at,
            requested_end=end,
            now=now,
        )
        expected = expected_session(policy, requested_end=end, now=now)
        if verdict is Verdict.HAS_LATEST_SESSION and not policy.is_within_cooldown(
            now, coverage.last_fetched_at
        ):
            # ADR-0009 修訂 2026-09-15 (tech-architect S3-1): the one place the
            # session rule can *overclaim* is a close published before the
            # assumed ``publish_cutoff``. If another live series of this market
            # already holds the next weekday's bar, that close is out: fetch
            # now rather than wait for the clock. Monotone -- this only ever
            # adds a fetch -- and bounded to one per cooldown by the guard above.
            later = next_weekday(expected)
            if later <= end and later > last_bar and self._cache.market_has_session(market, later):
                verdict = Verdict.REFETCH
        if verdict is Verdict.REFETCH:
            # ADR-0009 R-8, applied to the covered path too (tech-architect
            # F-2): a live ask newer than the last complete success that is
            # still inside the cooldown means the sources are failing right
            # now -- serve the cache with the reason instead of re-running the
            # whole ladder per click.
            attempted = self._cache.last_attempt_at(symbol, market)
            if (
                attempted is not None
                and attempted > coverage.last_fetched_at
                and policy.is_within_cooldown(now, attempted)
            ):
                return self._cached_result(
                    cached,
                    checked_at=coverage.last_fetched_at,
                    now=now,
                    current=False,
                    reason=RECENT_ATTEMPT_FAILED_REASON,
                )
            return None
        if verdict is Verdict.CHECKED_RECENTLY and coverage.covered_end < expected:
            # The recorded complete fetch never reached the session this
            # request expects (a historical fetch being reused for a request
            # that runs to today): that is a range gap, not a holiday.
            return None
        logger.info(
            "cache_first: serving %s from cache (%s); skipping all live providers",
            symbol,
            verdict.value,
        )
        return self._cached_result(
            cached,
            checked_at=coverage.last_fetched_at,
            now=now,
            current=verdict is Verdict.HAS_LATEST_SESSION,
        )

    @staticmethod
    def _cached_result(
        cached: CacheReadResult,
        *,
        checked_at: datetime,
        now: datetime,
        current: bool,
        reason: str | None = None,
    ) -> ProviderResult:
        """A ``CACHED_STALE`` answer whose age is when the data was last obtained.

        ``checked_at`` is the last *complete* live fetch when one is on record
        (a two-year series fetched this morning is minutes old, not a year --
        ADR-0009 R-2), else the rows' own oldest ``fetched_at``. It is never a
        failed attempt's time: nothing was obtained then (風控 R-10).
        """
        return ProviderResult(
            bars=cached.bars,
            status=DataStatus.CACHED_STALE,
            as_of=checked_at,
            source=cached.source,
            staleness_minutes=max(0, int((now - checked_at).total_seconds() // 60)),
            is_within_ttl=current,
            reason=reason,
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
                "unexpected provider error: %s raised while fetching %s; degrading to next layer",
                provider_label,
                symbol,
            )
            return None, UNEXPECTED_ERROR_REASON.format(provider=provider_label)
        if result.status is DataStatus.UNAVAILABLE or not result.bars:
            logger.info(
                "provider %s returned no usable data (status=%s) for %s; degrading to next layer",
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
            # ADR-0009 R-1: the same session rule decides ``is_within_ttl`` on
            # this path too -- a cache that lacks a published session is never
            # called current just because it was fetched recently.
            current = False
            checked_at = cached.fetched_at
            coverage = self._cache.fetch_coverage(symbol, market)
            if coverage is not None and coverage.covered_start <= start:
                checked_at = coverage.last_fetched_at
                current = (
                    judge(
                        policy_for(market),
                        last_bar_date=max(bar.date for bar in cached.bars),
                        last_checked_at=coverage.last_fetched_at,
                        requested_end=end,
                        now=now,
                    )
                    is Verdict.HAS_LATEST_SESSION
                )
            logger.warning(
                "all providers unavailable for %s; serving cached data (%d min stale)",
                symbol,
                cached.staleness_minutes,
            )
            # Why the live rungs were skipped travels with the cached answer
            # too: "served from cache" alone does not tell the reader whether
            # the quota ran out or the vendor was down.
            return self._cached_result(
                cached, checked_at=checked_at, now=now, current=current, reason=combined
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

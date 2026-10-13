"""Degradation orchestration: primary provider -> backup(s) -> cache -> unavailable.

This is the only entry point application code should use to fetch price
bars; it never talks to a vendor adapter directly. Every layer of the
ladder is explicit and every returned ``ProviderResult`` says exactly which
layer answered (``DataStatus``) and how stale the data is.
"""

from __future__ import annotations

import logging
from collections.abc import Callable, Sequence
from datetime import UTC, date, datetime, timedelta
from typing import Literal, get_args

from app.data.admission import SymbolAdmission
from app.data.cache import CacheReadResult, PriceBarCache
from app.data.freshness import Verdict, expected_session, judge, next_weekday, policy_for
from app.data.gate_wording import GateWording
from app.data.interface import (
    DataStatus,
    Market,
    MarketDataProvider,
    PriceBar,
    ProviderResult,
    Rejection,
)
from app.data.quality import CurrencyVerdict, check_currency, classify_currency

logger = logging.getLogger(__name__)

#: Fixed opening of the one record the service logs at each checkpoint whose
#: bars do not all carry the market's expected currency (task F-9a; format
#: extended by ADR-0024 TA5 R-60). A log line for the operator only -- never
#: shown to a reader, never carried by any response, ``meta()`` or API body
#: (risk-compliance, R-60 suggested) -- so it holds no reader-facing wording
#: and no response body. The fields that follow, in order, are ``symbol``, ``market``,
#: ``expected`` (:data:`EXPECTED_UNKNOWN_LOG_VALUE` when the market has no
#: entry), ``observed`` (every declared currency, deduplicated and sorted by
#: raw value, blanks written :data:`BLANK_CURRENCY_LOG_VALUE`), ``mismatched``
#: (differing bars / total), ``layer``, ``source``, ``verdict``
#: (``mismatch`` or ``missing``, from :func:`app.data.quality.classify_currency`)
#: and ``scope`` (``equity`` or ``index``). ``scope=equity`` logs at WARNING;
#: ``scope=index`` at ERROR, because a currency event on the index path is
#: unreachable under the shipped configuration (ADR-0024 D-4, F9W-31 (b)).
CURRENCY_DIFFERS_LOG_PREFIX = "price bars currency differs from market:"
#: How a blank (empty or whitespace-only) declared currency is written in the
#: ``observed`` field of the record above (TA5 R-60).
BLANK_CURRENCY_LOG_VALUE = "<blank>"
#: How the ``expected`` field reads when the injected lookup has no currency
#: for the market asked about; the checkpoint then counts as a mismatch.
EXPECTED_UNKNOWN_LOG_VALUE = "<none>"

#: Which product path a service answers for (ADR-0024 TA5 R-60, R-56): set
#: explicitly by each construction site -- never defaulted, never inferred
#: from a ``^`` prefix on the symbol.
ServiceScope = Literal["equity", "index"]
#: market -> the currency every bar of that market must carry, or ``None``
#: when the table has no entry (ADR-0024 D-5, TA1 M-6). Asked on every call
#: with that call's ``market``: the index service answers for both markets.
CurrencyLookup = Callable[[Market], str | None]

#: Which refusal wins when one answer carries several (ADR-0024 D-7 (2)).
_REJECTION_PRECEDENCE: tuple[Rejection, ...] = (
    "unit_mismatch",
    "unit_missing",
    "cache_unit_rejected",
)


class CurrencyLookupError(LookupError):
    """The injected lookup had no currency for a market at a gate checkpoint.

    A configuration error, not a data event (ADR-0024 D-4 last point, C-35,
    風控 F9W-39): there is no approved sentence that would be true here, so it
    is raised -- never turned into ``UNAVAILABLE``, a ``rejection``, a missing
    token or any reader-facing wording -- before anything is written.
    """


#: Joins several layers' reasons into the one ``reason`` slot a
#: ``ProviderResult`` has, in ladder order. Each sentence keeps its own full
#: stop and the next starts after a space: a semicolon would collide with the
#: one inside the spliced-sources sentence (風控 2026-09-15 suggested).
_REASON_SEPARATOR = "。 "

UNEXPECTED_ERROR_REASON = "{provider} 發生非預期錯誤，已降級至下一層。"
#: Carried by a cache answer served because the last live ask (inside the
#: market's cooldown) failed or came back partial -- the reader must not be
#: left thinking nothing was wrong (ADR-0003 約束 7). Wording approved by
#: risk-compliance-officer 2026-09-13 (第三輪). Reaches the screen since
#: 2026-09-15: ``load_bars`` forwards ``reason`` on a successful load and
#: ``DataMetaStatusBadge`` shows ``DataMeta.reason`` standing beside the badge.
RECENT_ATTEMPT_FAILED_REASON = "最近一次向來源取得資料未成功，暫以本機快取回覆。"
#: ADR-0005 D-5 (跨來源不得靜默拼接), discharged through ``reason`` since
#: ``ProviderResult`` has no ``notes``: an incremental fetch (ADR-0009 D-7) can
#: leave a series whose head was written by one provider and whose tail by
#: another; every bar keeps its own ``source``, and the reader is told -- on
#: *every* answer that carries such bars, cached ones included, because the
#: splice is permanent while the fetch that made it happens once (風控 R1).
#: Wording fixed verbatim by risk-compliance-officer 2026-09-15 (含失效條件:
#: 不同來源的價格處理可能不同); any change goes back to them. ``{sources}`` is
#: filled head-to-tail, in the order the bars carry them.
MIXED_SOURCES_REASON = (
    "這段日線資料由多個來源拼接（{sources}），每筆保留原本的來源；"
    "不同來源的價格處理方式可能不同，接合處的數值可能出現落差。"
)
#: The cached head could not be read back after a narrowed fetch: returning the
#: tail alone as a full answer would be a silent truncation (tech-architect F-4),
#: so the rung is treated as failed instead.
MERGE_READBACK_FAILED_REASON = "增量抓取後無法讀回本機快取的頭段，已降級至下一層。"
#: ADR-0009 D-8: nothing cached for the series and the last live ask (inside
#: the cooldown) failed -- the ladder is not re-run per click.
#: ``{minutes}`` anchors "最近一次" in time (風控 B-1): with no bars there is no
#: other timestamp on screen for the reader to relate it to. The second sentence
#: states the cooldown length and that nothing retries on its own -- a fact,
#: not a promise (風控 B-2). Wording by creative-lead
#: (`work/stock-desk-ADR-0010-揭露句-文案.md`), fixed verbatim by
#: risk-compliance-officer 2026-09-18 (三審); any change goes back to them.
#: 列管: "約 0 分鐘前" and four-digit minutes on the US cooldown read badly.
COOLDOWN_NO_CACHE_REASON = (
    "本機尚無此標的的日線資料，最近一次向來源取得已於約 {minutes} 分鐘前未成功，冷卻期內暫不重試。"
    "冷卻期為 {cooldown_hours} 小時，冷卻期內系統不會自動重試；"
    "冷卻期結束後的下一次查詢才會重新向來源取得。"
)
#: ADR-0010 D-1: a cache-only read found no rows. Distinct from "the source had
#: nothing" on purpose (tech-architect R-5): no source was asked this time.
#: Wording fixed verbatim by risk-compliance-officer 2026-09-18 (C 核可).
CACHE_ONLY_MISS_REASON = "本機尚無此標的的日線資料；本次未向來源查詢。"


def _combine_reasons(reasons: Sequence[str]) -> str | None:
    """Fold every layer's own wording into one sentence, losing none of them.

    A degraded response usually has more than one cause worth stating ("no API
    key" *and* "backup unreachable"); keeping only the first would misattribute
    the failure. Each layer's text is preserved verbatim; sentences are joined
    with a full stop and a space so each keeps its own boundary.
    """
    kept = [reason.strip() for reason in reasons if reason and reason.strip()]
    if not kept:
        return None
    return _REASON_SEPARATOR.join(text.rstrip("。") for text in kept) + "。"


def mixed_sources_reason(bars: Sequence[PriceBar]) -> str | None:
    """The D-5 disclosure for ``bars``, or ``None`` when they all share one source.

    Sources are listed head-to-tail (first appearance in date order), so the
    reader is not left to guess which provider wrote the older part. Applied
    to whatever is about to be returned -- a live answer, an incremental
    merge or a cache read -- never inferred from how the answer was produced.
    """
    sources = list(dict.fromkeys(bar.source for bar in sorted(bars, key=lambda bar: bar.date)))
    if len(sources) <= 1:
        return None
    return MIXED_SOURCES_REASON.format(sources="、".join(sources))


def _observed_currencies(bars: Sequence[PriceBar]) -> str:
    """The ``observed`` log field: declared values, deduplicated, sorted raw, blanks marked."""
    shown = (
        value if value.strip() else BLANK_CURRENCY_LOG_VALUE
        for value in sorted({bar.currency for bar in bars})
    )
    return ",".join(dict.fromkeys(shown))


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
    "no data". A successful fetch carries a reason only when the series it
    returns is spliced from more than one provider (ADR-0005 D-5 via ADR-0009
    D-7); otherwise there is nothing to explain.

    ``currency_for_market`` and ``scope`` (ADR-0024 D-5, TA5 R-60) are
    required keyword-only arguments with no default:
    the assembly layer (``app.api.deps``) passes a lookup over
    ``app.positions.models.MARKET_CURRENCY`` -- this module does not import
    ``app.positions`` (KX-A1) -- and says whether the service answers for
    ``equity`` (TW, US) or ``index`` series. The lookup is asked with each
    call's ``market``, never fixed at construction, because the one index
    service answers for both markets. At every checkpoint that obtains bars
    (a live provider, the incremental read-back, layer 0, the
    degrade-to-cache rung, the cache-only read) bars that do not all carry
    the expected currency -- or a market the lookup does not know, which
    counts as a mismatch -- produce one record starting with
    :data:`CURRENCY_DIFFERS_LOG_PREFIX`.

    The live rung is gated (ADR-0024 D-2, F-9b): a provider whose bars do not
    all carry the expected currency has declined -- nothing is cached, no fetch
    is recorded -- and states W-c (another unit declared) or W-c' (no unit
    declared) on the equity path, nothing on the index path. After a W-c, no
    cached price is served on the same call (風控 F9W-4 (a)); after a W-c' the
    equity ladder may still fall back to the cache, the index ladder may not
    (D-4). A lookup that cannot answer for a market is refused at construction
    and, should it change its mind later, raises :class:`CurrencyLookupError`
    at the gated checkpoint (C-35).

    Every cache read is gated too (D-2 (5)): layer 0 judges the whole cached
    range before any of its branches, then the degrade-to-cache rung, the
    cache-only read and the incremental read-back each judge what they read.
    A refused cached series is never served and never deleted; the answer
    states T-15 on the equity path (nothing on the index path) and carries
    ``rejection="cache_unit_rejected"`` unless a live refusal outranks it.
    Inside the R-8 cooldown layer 0 answers that way without asking a source;
    outside it, the ladder runs for the whole range, so a source that answers
    overwrites the refused rows.

    Ahead of all of it, at both entries, the injected ``admission`` decides
    whether the symbol may be asked about at all (D-4): a refused symbol reads
    no cache, asks no source and writes nothing, and the equity path states
    W-a (US) or W-b (TW) with ``rejection="symbol_not_admitted"``. ``admission``
    and ``wording`` are required keyword-only arguments like the two above;
    the index ladder is handed an admission that checks no shape and no
    wording (C-6, 風控 F9W-9).
    """

    def __init__(
        self,
        *,
        primary: MarketDataProvider,
        backups: Sequence[MarketDataProvider] = (),
        cache: PriceBarCache,
        clock: Callable[[], datetime] = lambda: datetime.now(UTC),
        cache_first: bool = False,
        currency_for_market: CurrencyLookup,
        scope: ServiceScope,
        admission: SymbolAdmission,
        wording: GateWording | None,
    ) -> None:
        if scope not in ("equity", "index"):
            raise ValueError(f"unknown service scope: {scope!r}")
        # C-35 (b): a market the lookup cannot answer is a configuration error,
        # caught here rather than at the first request for that market.
        for known in get_args(Market):
            currency = currency_for_market(known)
            if currency is None or not currency.strip():
                raise ValueError(f"currency_for_market has no currency for market {known!r}")
        self._primary = primary
        self._backups = tuple(backups)
        self._cache = cache
        self._clock = clock
        self._cache_first = cache_first
        self._currency_for_market = currency_for_market
        self._scope = scope
        #: Which symbols may be asked about at all (D-4); the index ladder is
        #: handed one that checks no shape.
        self._admission = admission
        #: The sentences a refusal states: the equity ladders speak, the index
        #: path never does (ADR-0024 D-4, 風控 F9W-9). Both are injected by the
        #: assembly layer, never derived from ``scope`` or a ``^`` prefix (C-6).
        self._wording = wording

    def get_daily_bars(self, symbol: str, market: Market, start: date, end: date) -> ProviderResult:
        refused = self._refuse_unadmitted(symbol, market)
        if refused is not None:
            return refused
        layer_zero_refused = False
        if self._cache_first:
            layer_zero, layer_zero_refused = self._try_session_fresh_cache(
                symbol, market, start, end
            )
            if layer_zero is not None:
                return layer_zero

        providers: list[tuple[MarketDataProvider, DataStatus]] = [
            (self._primary, DataStatus.FRESH),
            *((backup, DataStatus.BACKUP) for backup in self._backups),
        ]
        # ADR-0009 D-7 (方案 F): when the cache already holds a complete,
        # contiguous head of the range, ask the live source only for the tail.
        # Not when layer 0 refused the cached series (ADR-0024 D-2 (5)(a) step
        # 4): the whole range is asked for, so a live answer overwrites the
        # refused rows instead of being merged with them (``_incremental_start``
        # itself is unchanged, ADR-0019 K-10).
        fetch_start = (
            start if layer_zero_refused else self._incremental_start(symbol, market, start, end)
        )
        #: The incremental read-back was refused this call (D-2 (5)(d)): T-15 is
        #: already among the reasons and the cache is not read again.
        readback_refused = False

        # Every rung that declined to answer states why; those sentences are
        # what the API layer shows when the whole ladder comes up empty.
        reasons: list[str] = []
        #: Every live rung the currency gate refused on this call (D-2 (1)).
        refusals: list[Rejection] = []
        for provider, status in providers:
            result, reason = self._try_provider(provider, symbol, fetch_start, end)
            if result is None:
                if reason is not None:
                    reasons.append(reason)
                continue
            verdict = self._judge_bars(
                symbol, market, result.bars, layer="provider", source=result.source
            )
            if verdict != "ok":
                # ADR-0024 D-2 (1), D-3: the whole series is this rung declining
                # -- nothing is cached, no fetch is recorded, the attempt below
                # is recorded as for any other declined rung (C-2, C-3).
                refusals.append("unit_mismatch" if verdict == "mismatch" else "unit_missing")
                sentence = self._refusal_sentence(provider, market, verdict)
                if sentence is not None:
                    reasons.append(sentence)
                if verdict == "mismatch" or self._scope == "index":
                    # D-2 (2): a later rung is asked for the whole range, so no
                    # cached head is ever read back beside a W-c this call. The
                    # index path applies it to W-c' too (D-4: D-2 (2) holds for
                    # the index service, mismatch and missing alike).
                    fetch_start = start
                continue
            fetched_at = self._clock()
            self._cache.put(result.bars, source=result.source, fetched_at=fetched_at)
            # ADR-0009: the attempt log feeds the cooldown, whatever happens next.
            self._cache.record_attempt(symbol, market, at=fetched_at)
            bars = result.bars
            if fetch_start > start:
                # The answer is the cached head plus the live tail, read back as
                # one series. Every bar keeps its own ``source``; when the head
                # was written by a different provider the reader is told
                # (ADR-0005 D-5 -- never a silent splice).
                merged = self._cache.get(symbol, market, start, end, now=fetched_at)
                if merged is None:
                    # F-4: the tail alone is not the answer that was asked for,
                    # and no coverage is claimed for a range that was not served.
                    logger.error(
                        "incremental fetch for %s: cached head could not be read back; "
                        "degrading past %s",
                        symbol,
                        result.source,
                    )
                    reasons.append(MERGE_READBACK_FAILED_REASON)
                    continue
                if self._cache_refuses(
                    symbol, market, merged.bars, layer="incremental_readback", source=merged.source
                ):
                    # ADR-0024 D-2 (5)(d): T-15 joins this ladder's reasons in
                    # place of MERGE_READBACK_FAILED_REASON; later rungs are asked
                    # for the whole range and the cache is not read again.
                    if self._wording is not None:
                        reasons.append(self._wording.cache_unit_rejected)
                    readback_refused = True
                    fetch_start = start
                    continue
                bars = merged.bars
                logger.info(
                    "incremental fetch for %s: asked %s for %s..%s instead of %s..%s",
                    symbol,
                    result.source,
                    fetch_start,
                    end,
                    start,
                    end,
                )
            # The fetch log (coverage) is written only for a complete answer, so
            # a range with a skipped month is asked for again instead of frozen
            # in. An incremental tail completes the *whole* request: the head
            # was already covered (that is what allowed narrowing) and has just
            # been read back.
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
                bars=bars,
                status=status,
                as_of=result.as_of,
                source=result.source,
                staleness_minutes=0,
                complete=result.complete,
                reason=mixed_sources_reason(bars),
            )

        # Every live rung declined: remember the attempt so the cooldown applies
        # to the *next* click even though nothing was fetched (ADR-0009 R-8).
        self._cache.record_attempt(symbol, market, at=self._clock())
        if "unit_mismatch" in refusals or (refusals and self._scope == "index"):
            # 風控 F9W-4 (a), ADR-0024 D-2 (2): a rung that declared another unit
            # this call means no cached price is served beside it. The index
            # path holds W-c' to the same rule (D-4: it has no sentence that
            # could disclose a cached answer).
            return self._refused_answer(reasons, refusals)
        if readback_refused:
            # D-2 (5)(d): ``_fall_back_to_cache`` does not read the cache again,
            # so T-15 is stated exactly once (C-30).
            return self._refused_answer(reasons, [*refusals, "cache_unit_rejected"])
        return self._fall_back_to_cache(
            symbol, market, start, end, reasons, refusal=_strongest(refusals)
        )

    def get_cached_bars(
        self, symbol: str, market: Market, start: date, end: date
    ) -> ProviderResult:
        """Answer from the local cache only -- never a live call (ADR-0010 D-1).

        For a book-wide valuation that only feeds risk-cap denominators, one
        session of staleness is a rounding error while a minute of blank screen
        is a certain harm, so this read applies the same session rule as layer
        0 (:func:`app.data.freshness.judge`, R-3) but never falls through to
        the ladder. It returns ``CACHED_STALE`` or ``UNAVAILABLE`` only (R-1)
        and writes neither log nor rows (R-2): the attempt log means "a source
        was asked", and nothing was.
        """
        refused = self._refuse_unadmitted(symbol, market)
        if refused is not None:
            return refused
        now = self._clock()
        cached = self._cache.get(symbol, market, start, end, now=now)
        if cached is None:
            return ProviderResult(
                bars=[],
                status=DataStatus.UNAVAILABLE,
                as_of=now,
                source="none",
                staleness_minutes=None,
                reason=CACHE_ONLY_MISS_REASON,
            )
        if self._cache_refuses(
            symbol, market, cached.bars, layer="cache_only", source=cached.source
        ):
            # ADR-0024 D-2 (5)(c): T-15 on the equity path, no sentence on the
            # index path (D-4); nothing written either way (ADR-0010 R-2).
            return self._refused_answer([], ["cache_unit_rejected"])
        coverage = self._cache.fetch_coverage(symbol, market)
        current = False
        checked_at = cached.fetched_at
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
        return self._cached_result(cached, checked_at=checked_at, now=now, current=current)

    def _refuse_unadmitted(self, symbol: str, market: Market) -> ProviderResult | None:
        """The admission, ahead of every cache read and every source (ADR-0024 D-4).

        A refused symbol reads no cache, asks no source, spends no quota and
        writes no attempt log (C-4); no currency record is written either -- it
        is not a currency event (TA5 R-60). The equity path states W-a (US) or
        W-b (TW), the only place either is stated (F9W-7).
        """
        if self._admission(symbol, market):
            return None
        logger.info("symbol not admitted for %s daily bars: %s", market, symbol)
        reason = None if self._wording is None else self._wording.symbol_not_admitted[market]
        return ProviderResult(
            bars=[],
            status=DataStatus.UNAVAILABLE,
            as_of=self._clock(),
            source="none",
            staleness_minutes=None,
            reason=reason,
            rejection="symbol_not_admitted",
        )

    def _cache_refuses(
        self,
        symbol: str,
        market: Market,
        bars: Sequence[PriceBar],
        *,
        layer: str,
        source: str,
    ) -> bool:
        """The cache gate (ADR-0024 D-2 (5)): ``True`` when the series must not be served.

        Any bar declaring a unit other than the market's, or none, refuses the
        whole series; nothing is deleted (D-8). The record is written by
        :meth:`_judge_bars`; a lookup that cannot answer raises (C-35 (c)).
        """
        return self._judge_bars(symbol, market, bars, layer=layer, source=source) != "ok"

    def _refused_answer(
        self, reasons: Sequence[str], refusals: Sequence[Rejection]
    ) -> ProviderResult:
        """``UNAVAILABLE``, no bars, the strongest category (D-7 (2)).

        When the category is the cache gate's and the path speaks (equity), T-15
        closes the reason -- unless it is already there (C-30); the index path
        adds no sentence (D-4 (c)).
        """
        stated = list(reasons)
        if (
            "cache_unit_rejected" in refusals
            and self._wording is not None
            and self._wording.cache_unit_rejected not in stated
        ):
            stated.append(self._wording.cache_unit_rejected)
        now = self._clock()
        return ProviderResult(
            bars=[],
            status=DataStatus.UNAVAILABLE,
            as_of=now,
            source="none",
            staleness_minutes=None,
            reason=_combine_reasons(stated),
            rejection=_strongest(refusals),
        )

    def _judge_bars(
        self,
        symbol: str,
        market: Market,
        bars: Sequence[PriceBar],
        *,
        layer: str,
        source: str,
    ) -> CurrencyVerdict:
        """The currency gate at one checkpoint: the verdict, and one record when it is not ``ok``.

        ``layer`` names the checkpoint (``provider``, ``incremental_readback``,
        ``layer0_cache``, ``fallback_cache``, ``cache_only``). An empty series
        has nothing to judge: ``ok``, no record. The record is written for every
        checkpoint that judges ``mismatch`` or ``missing``, whatever the answer
        then becomes (TA5 R-60, 風控 F9W-35 (c)).

        A market the lookup cannot answer raises :class:`CurrencyLookupError`
        after its record (C-35 (c), 風控 F9W-39).
        """
        if not bars:
            return "ok"
        expected = self._currency_for_market(market)
        verdict: CurrencyVerdict
        if expected is None or not expected.strip():
            verdict = "mismatch"
            mismatched = len(bars)
            expected = None
        else:
            verdict = classify_currency(bars, expected)
            if verdict == "ok":
                return verdict
            mismatched = len(check_currency(bars, expected))
        self._write_record(
            symbol,
            market,
            bars,
            expected=expected,
            mismatched=mismatched,
            layer=layer,
            source=source,
            verdict=verdict,
        )
        if expected is None:
            raise CurrencyLookupError(
                f"no currency for market {market!r} at checkpoint {layer} ({symbol})"
            )
        return verdict

    def _write_record(
        self,
        symbol: str,
        market: Market,
        bars: Sequence[PriceBar],
        *,
        expected: str | None,
        mismatched: int,
        layer: str,
        source: str,
        verdict: CurrencyVerdict,
    ) -> None:
        """The one operator record (:data:`CURRENCY_DIFFERS_LOG_PREFIX`); no reader wording."""
        logger.log(
            logging.ERROR if self._scope == "index" else logging.WARNING,
            CURRENCY_DIFFERS_LOG_PREFIX
            + " symbol=%s market=%s expected=%s observed=%s mismatched=%d/%d layer=%s source=%s"
            " verdict=%s scope=%s",
            symbol,
            market,
            EXPECTED_UNKNOWN_LOG_VALUE if expected is None else expected,
            _observed_currencies(bars),
            mismatched,
            len(bars),
            layer,
            source,
            verdict,
            self._scope,
        )

    def _refusal_sentence(
        self, provider: MarketDataProvider, market: Market, verdict: CurrencyVerdict
    ) -> str | None:
        """W-c or W-c' for a refused live rung, or ``None`` where no sentence applies.

        The index path has none (D-4, F9W-9). ``{provider}`` is the adapter's
        own ``source_id`` and nothing else; an adapter without one gets no
        sentence rather than a guessed name (F9W-3, C-14).
        """
        if self._wording is None:
            return None
        source_id = getattr(provider, "source_id", None)
        if not isinstance(source_id, str) or not source_id.strip():
            return None
        table = self._wording.unit_mismatch if verdict == "mismatch" else self._wording.unit_missing
        return table[market].format(provider=source_id)

    def _incremental_start(self, symbol: str, market: Market, start: date, end: date) -> date:
        """Where a live fetch for ``[start, end]`` may begin without losing anything (D-7).

        The cache can stand in for the head of the range only when a complete
        live fetch is on record from ``start`` onwards *and* the cached series
        runs contiguously into the month the live ask will start from. Then the
        ask begins at the first day of the last cached bar's month: month-shaped
        sources (TWSE / TPEx) then spend one call per month spanned instead of
        one per month of the whole range, and that last month is re-pulled in
        full so an in-month revision is still picked up. Anything less certain
        -- no coverage, a request reaching earlier than the coverage, a cached
        tail that outruns the coverage (a partial fetch left rows past it) --
        falls back to asking for the whole range, exactly as before.
        """
        if not self._cache_first:
            return start
        coverage = self._cache.fetch_coverage(symbol, market)
        if coverage is None or coverage.covered_start > start:
            return start
        last_bar = self._cache.last_trade_date(symbol, market, start, end)
        if last_bar is None:
            return start
        month_start = last_bar.replace(day=1)
        if month_start > coverage.covered_end + timedelta(days=1):
            return start
        return max(start, month_start)

    def _try_session_fresh_cache(
        self, symbol: str, market: Market, start: date, end: date
    ) -> tuple[ProviderResult | None, bool]:
        """Layer 0 behind the cache gate: ``(answer or None, whether the cache was refused)``.

        ADR-0024 D-2 (5)(a), steps 4 and 5 (steps 1-3 read the D-9 marker and
        belong to F-9b2, which inserts them before step 4). The whole cached
        range is read once and judged before every branch below -- the R-8
        cooldown branch included -- so a refused series is never served:

        * step 4, refused and inside the ADR-0009 R-8 cooldown (the last ask is
          newer than the last complete success and recent): ``UNAVAILABLE``
          with T-15 alone (none on the index path), no source asked;
        * step 4, refused otherwise: ``None`` -- run the ladder, asking for the
          whole range (the caller disables the incremental start);
        * step 5, not refused or nothing cached: the ADR-0009 branches as before.
        """
        now = self._clock()
        cached = self._cache.get(symbol, market, start, end, now=now)
        if cached is None or not self._cache_refuses(
            symbol, market, cached.bars, layer="layer0_cache", source=cached.source
        ):
            return self._layer_zero_answer(
                symbol, market, start, end, now=now, cached=cached
            ), False
        coverage = self._cache.fetch_coverage(symbol, market)
        last_success = coverage.last_fetched_at if coverage is not None else None
        attempted = self._cache.last_attempt_at(symbol, market)
        if (
            attempted is not None
            and (last_success is None or attempted > last_success)
            and policy_for(market).is_within_cooldown(now, attempted)
        ):
            # Cooldown facts stay out of the reason (TA4 R-47); nothing is
            # recorded either (C-31: no new ``record_attempt`` call site).
            return self._refused_answer([], ["cache_unit_rejected"]), True
        return None, True

    def _layer_zero_answer(
        self,
        symbol: str,
        market: Market,
        start: date,
        end: date,
        *,
        now: datetime,
        cached: CacheReadResult | None,
    ) -> ProviderResult | None:
        """``cache_first`` layer 0 (ADR-0009): serve the cache when no newer session can exist.

        ``cached`` has already passed the cache gate (or is ``None``).

        Returns ``None`` (meaning "fall through to the normal ladder") when
        there is no cached data for this range, when no complete live fetch
        covering ``start`` is on record and no live attempt was made within
        the cooldown, or when the cache is short of the latest published
        session and nobody has asked a live source within the cooldown.
        """
        policy = policy_for(market)
        coverage = self._cache.fetch_coverage(symbol, market)
        last_success = coverage.last_fetched_at if coverage is not None else None
        if cached is None:
            # ADR-0009 D-8 (tech-architect 2026-09-18): a series that has never
            # been fetched successfully *and* whose sources are failing right
            # now is the case that needs the cooldown most, and used to be the
            # only one without it -- every click re-ran the whole ladder.
            attempted = self._cache.last_attempt_at(symbol, market)
            if (
                attempted is not None
                and (last_success is None or attempted > last_success)
                and policy.is_within_cooldown(now, attempted)
            ):
                minutes_ago = int((now - attempted).total_seconds() // 60)
                logger.info(
                    "cache_first: nothing cached for %s and a live attempt %d min ago failed; "
                    "not re-running the ladder inside the cooldown",
                    symbol,
                    minutes_ago,
                )
                return ProviderResult(
                    bars=[],
                    status=DataStatus.UNAVAILABLE,
                    as_of=now,
                    source="none",
                    staleness_minutes=None,
                    reason=COOLDOWN_NO_CACHE_REASON.format(
                        minutes=minutes_ago,
                        cooldown_hours=int(policy.recheck_cooldown.total_seconds() // 3600),
                    ),
                )
            return None
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

        A cache that holds rows from more than one provider (the lasting
        effect of an incremental fetch, ADR-0009 D-7) says so here as well:
        the splice outlives the fetch that made it, and this is the path that
        answers every later click (風控 2026-09-15 R1).
        """
        return ProviderResult(
            bars=cached.bars,
            status=DataStatus.CACHED_STALE,
            as_of=checked_at,
            source=cached.source,
            staleness_minutes=max(0, int((now - checked_at).total_seconds() // 60)),
            is_within_ttl=current,
            reason=_combine_reasons([reason or "", mixed_sources_reason(cached.bars) or ""]),
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
        *,
        refusal: Rejection | None = None,
    ) -> ProviderResult:
        """The last rung: whatever the cache holds, else ``UNAVAILABLE``.

        ``refusal`` is the category of a live rung the gate refused this call
        (only W-c' reaches here on the equity path, D-2 (4)). A cached answer
        never carries it -- it has bars (D-7 (2)) -- while an empty answer does,
        so ``load_bars`` states the refusal verbatim (W-d) and the valuator
        gives the refused-answer token (C-13 (5), C-19).
        """
        combined = _combine_reasons(reasons)
        now = self._clock()
        cached = self._cache.get(symbol, market, start, end, now=now)
        if cached is not None and self._cache_refuses(
            symbol, market, cached.bars, layer="fallback_cache", source=cached.source
        ):
            # ADR-0024 D-2 (5)(b): every rung's reason, then T-15 (equity only);
            # a live W-c' outranks the cache gate's own category (D-7 (2)).
            refusals: list[Rejection] = [] if refusal is None else [refusal]
            return self._refused_answer(reasons, [*refusals, "cache_unit_rejected"])
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
            rejection=refusal,
        )


def _strongest(refusals: Sequence[Rejection]) -> Rejection | None:
    """The one category an answer carries when several rungs were refused (D-7 (2))."""
    for category in _REJECTION_PRECEDENCE:
        if category in refusals:
            return category
    return None

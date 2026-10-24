"""Index daily series: a series code -> bars, with the refusal reason attached.

Two callers, one data chain:

* **Underlying index of a leveraged ETF** -- ETF symbol -> :class:`IndexRef` ->
  bars. This is the **single** junction between the pure ``app/leverage``
  package and the data layer (ADR-0005 constraint I-1).
  ``app/leverage/index_mapping.py`` answers "which series code, on what return
  basis"; this module answers "who can fetch that code, and what came back".
* **Comparison benchmark of a market** -- market -> :data:`MARKET_BENCHMARK` ->
  bars, used by ``GET /api/signals`` for beta. There is no ETF and no mapping
  row involved, so it does not go through ``index_mapping``; everything below
  the series code (service, cache, disclosure) is the same chain.

Dependency injection on purpose: the resolver is a plain
``market -> PriceService`` mapping (the same shape ``app/services/market.py``
uses), so nothing here imports a concrete adapter and the whole module is
testable offline with a fake service.

Two rules this module exists to enforce:

1. **An unobtainable series is a stated fact, not an error.** A symbol with no
   mapping row, an ``unmapped`` row, a market with no index service, or a
   source that returned nothing all produce an empty result carrying its own
   Traditional Chinese ``reason``; nothing raises and no substitute series is
   ever returned in place of the index.
2. **An index series is never presented as the freshest rung.** The index feed
   is a non-official source (ADR-0005 decision 1.3), so a ``fresh`` provider
   result is disclosed as ``backup``. A ``cached_stale`` result is *not*
   upgraded to ``backup``: hiding staleness to satisfy a label would be the
   opposite of the point.

One deliberate exception to "callers go through ``IndexSeriesService``": the
replay snapshot fetch at the bottom of this module
(:func:`fetch_replay_index_snapshot`, ADR-0005 I-3 解釋性註記, follow-up N-82).
It reads no cache, writes no cache, touches no quota, labels its result
``backup`` / ``unavailable`` itself and fails closed; see its docstring.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from datetime import UTC, date, datetime
from decimal import Decimal
from typing import ClassVar, Protocol

from app.data.interface import (
    DataStatus,
    Market,
    MarketDataProvider,
    PriceBar,
    ProviderResult,
)
from app.leverage.index_mapping import (
    MAPPING_VERIFIED_ON,
    IndexRef,
    lookup_index_ref,
)
from app.portfolio.valuation import PriceService
from app.services.market import with_provider_reason

#: market of the index series -> the service that can quote it.
IndexServiceResolver = Mapping[Market, PriceService]

NO_MAPPING_ROW_REASON = (
    "此標的沒有標的指數對應資料，無法得知要查詢哪一個指數代號，因此不取得指數序列，"
    "也不以其他標的替代。"
)

PROXY_BASIS_REASON = (
    "此列登記的是代理 ETF 序列（basis=proxy_etf），本版本未放行以代理標的作為指數序列，"
    "因此不取得資料；代理標的自身的經理費與追蹤誤差會混進報酬拆解。"
)

NO_SERVICE_REASON = (
    "目前沒有 {market} 指數序列的資料來源，因此取不到 {series_symbol} 的日線；"
    "本模組不會改以其他標的替代。"
)

NO_BARS_REASON = "指數 {series_symbol} 在指定區間內沒有可用的日線資料（來源與快取皆無）。"

UNOFFICIAL_SOURCE_NOTE = (
    "指數序列取自非官方來源，資料狀態一律以 backup 呈現，不標示為即時（fresh）。"
)

UNVERIFIED_MAPPING_NOTE = (
    "標的指數對應表尚未經線上實際查詢查證（verified=false），"
    "序列代號是否確為該基金的標的指數屬待查證狀態。"
)

NO_BENCHMARK_REASON = "目前沒有為 {market} 市場設定比較基準指數，因此不取得基準序列。"

UNVERIFIED_BENCHMARK_NOTE = (
    "比較基準指數代號的可得性尚未經線上實際查詢查證（ADR-0005 尚缺的事實第 3 點）；"
    "市場與基準指數的對應為本版本設定，非官方指定。"
)


@dataclass(frozen=True)
class LoadedIndexBars:
    """Index bars plus the provenance and the refusal reason, when there is one."""

    ref: IndexRef | None = None
    bars: list[PriceBar] = field(default_factory=list)
    status: DataStatus = DataStatus.UNAVAILABLE
    source: str = "none"
    staleness_minutes: int | None = None
    reason: str | None = None
    notes: list[str] = field(default_factory=list)

    @property
    def available(self) -> bool:
        """Whether a usable index series came back."""
        return bool(self.bars)

    def meta(self) -> dict[str, object]:
        """The index provenance block an endpoint can echo verbatim."""
        ref = self.ref
        return {
            "status": self.status.value,
            "source": self.source,
            "staleness_minutes": self.staleness_minutes,
            "bar_count": len(self.bars),
            "series_symbol": ref.series_symbol if ref else None,
            "series_market": ref.series_market if ref else None,
            "basis": ref.basis if ref else None,
            "return_basis": ref.return_basis if ref else None,
            "mapping_verified": bool(ref and ref.verified),
            "mapping_verified_on": MAPPING_VERIFIED_ON,
            "reason": self.reason,
            "notes": list(self.notes),
        }


def disclosed_status(status: DataStatus) -> DataStatus:
    """Downgrade ``fresh`` to ``backup``; leave every other rung untouched.

    ADR-0005 decision 1.3: an index series comes from a non-official source, so
    calling it ``fresh`` would tell the reader it is the official record. The
    stale rungs are left alone because relabelling them would erase real
    staleness -- disclosure only ever moves in the pessimistic direction here.
    """
    return DataStatus.BACKUP if status is DataStatus.FRESH else status


class IndexBarsProvider(Protocol):
    """The slice of an index-capable adapter this module needs.

    Structural (``Protocol``) on purpose: ``app/data/providers/yfinance.py``
    deliberately keeps ``get_index_daily_bars`` *off* the
    ``MarketDataProvider`` ABC -- an index is not a per-security fetch and has
    its own caller -- so the shape is adapted here rather than the adapter
    bending its own contract to fit.
    """

    def get_index_daily_bars(self, index_symbol: str, start: date, end: date) -> ProviderResult: ...


class IndexProviderBridge(MarketDataProvider):
    """``get_index_daily_bars(symbol, start, end)`` -> the provider contract.

    Pure signature translation and nothing else. The symbol is passed through
    verbatim, so every guarantee the index adapter makes stays intact: an index
    code never goes through ``canonical_us_symbol``, Alpha Vantage is not on
    this path at all (so no quota is consumed), and the ``status`` the adapter
    chose -- ``BACKUP`` even on success, ADR-0005 constraint I-3 -- is returned
    unmodified. Deliberately no validation of its own: a second opinion on
    which index codes are supported would be a second table to keep in sync
    with the adapter's.

    Wrapping this in a ``MarketDataService`` is what earns the index path a
    cache and the TTL-first layer 0 (ADR-0005 決策四). That service labels a
    successful *primary* fetch ``FRESH``, which is why callers must see the
    result through :class:`IndexSeriesService` rather than the raw service.
    """

    #: Only ever used for the service's own degradation logging; the source
    #: a user sees comes from the adapter's ``ProviderResult.source``.
    source_id: ClassVar[str] = "index_bridge"

    def __init__(self, provider: IndexBarsProvider) -> None:
        self._provider = provider

    def get_daily_bars(self, symbol: str, start: date, end: date) -> ProviderResult:
        return self._provider.get_index_daily_bars(symbol, start, end)


class IndexSeriesService:
    """A :class:`PriceService` over an index series that never claims ``fresh``.

    ADR-0005 constraint I-3 applies to the index series wherever it is read,
    not only where the adapter produced it: a ``MarketDataService`` re-labels
    whatever its primary provider returns as ``FRESH``, which would undo the
    adapter's own disclosure. This facade re-applies :func:`disclosed_status`
    at the boundary, so anything holding an ``IndexServiceResolver`` sees at
    best ``backup`` no matter how the layers underneath are composed.

    Everything else on the result -- bars, ``source``, ``staleness_minutes``,
    ``is_within_ttl``, ``reason`` -- is passed through untouched.
    """

    def __init__(self, inner: PriceService) -> None:
        self._inner = inner

    def get_daily_bars(self, symbol: str, market: Market, start: date, end: date) -> ProviderResult:
        result = self._inner.get_daily_bars(symbol, market, start, end)
        disclosed = disclosed_status(result.status)
        if disclosed is result.status:
            return result
        return result.model_copy(update={"status": disclosed})

    def get_cached_bars(
        self, symbol: str, market: Market, start: date, end: date
    ) -> ProviderResult:
        """The cache-only read (ADR-0010 D-1), passed through; it never claims ``fresh``."""
        return self._inner.get_cached_bars(symbol, market, start, end)


def load_index_bars(
    resolver: IndexServiceResolver,
    *,
    etf_symbol: str,
    start: date,
    end: date,
) -> LoadedIndexBars:
    """Load the underlying-index series for ``etf_symbol``, or say why not."""
    ref = lookup_index_ref(etf_symbol)
    if ref is None:
        return LoadedIndexBars(reason=NO_MAPPING_ROW_REASON)
    return load_index_series(resolver, ref, start=start, end=end)


def load_index_series(
    resolver: IndexServiceResolver,
    ref: IndexRef,
    *,
    start: date,
    end: date,
) -> LoadedIndexBars:
    """Load the series named by ``ref``, degrading to an explained empty result."""
    notes = [UNOFFICIAL_SOURCE_NOTE]
    if not ref.verified:
        notes.append(UNVERIFIED_MAPPING_NOTE)

    if ref.basis == "unmapped" or ref.series_symbol is None:
        # A stated absence: the mapping's own note is the user-facing reason.
        return LoadedIndexBars(ref=ref, reason=ref.note or NO_MAPPING_ROW_REASON, notes=notes)
    if ref.basis != "official_index":
        return LoadedIndexBars(ref=ref, reason=PROXY_BASIS_REASON, notes=notes)

    service = resolver.get(ref.series_market)
    if service is None:
        return LoadedIndexBars(
            ref=ref,
            reason=NO_SERVICE_REASON.format(
                market=ref.series_market, series_symbol=ref.series_symbol
            ),
            notes=notes,
        )

    result = service.get_daily_bars(ref.series_symbol, ref.series_market, start, end)
    if result.status is DataStatus.UNAVAILABLE or not result.bars:
        return LoadedIndexBars(
            ref=ref,
            status=result.status,
            source=result.source,
            staleness_minutes=result.staleness_minutes,
            # The data layer's own wording (source unreachable, unsupported
            # index code, ...) is appended rather than swallowed: this module's
            # sentence says *that* nothing came back, the provider's says why.
            reason=with_provider_reason(
                NO_BARS_REASON.format(series_symbol=ref.series_symbol), result.reason
            ),
            notes=notes,
        )
    return LoadedIndexBars(
        ref=ref,
        bars=list(result.bars),
        status=disclosed_status(result.status),
        source=result.source,
        staleness_minutes=result.staleness_minutes,
        # A successful answer can still carry the data layer's sentence (served
        # from cache after a failed attempt, spliced from more than one source
        # -- ADR-0009 D-3 / D-7); it is forwarded, never dropped here (風控
        # 2026-09-15 R1-b).
        reason=result.reason,
        notes=notes,
    )


@dataclass(frozen=True)
class BenchmarkIndex:
    """The index a market's relative measures (beta) are computed against."""

    #: Official index code, ``^``-prefixed like every series in this chain.
    series_symbol: str
    #: What the reader is told the comparison was made against.
    label: str


#: market -> its comparison benchmark index.
#:
#: Official index codes only, from the set the index adapter supports (ADR-0005
#: 決策一): a tracking ETF (0050, SPY, QQQ) is never substituted for an index
#: here any more than it is on the leveraged-ETF path -- a proxy's expense ratio
#: and tracking error would quietly become part of the beta it is used to
#: measure. A market absent from this map has no benchmark and says so.
MARKET_BENCHMARK: Mapping[Market, BenchmarkIndex] = {
    "TW": BenchmarkIndex(series_symbol="^TWII", label="臺灣加權股價指數（^TWII）"),
    "US": BenchmarkIndex(series_symbol="^GSPC", label="S&P 500 指數（^GSPC）"),
}


@dataclass(frozen=True)
class LoadedBenchmark:
    """A market's benchmark series plus the reason, when it could not be had.

    Separate from :class:`LoadedIndexBars` because the two answer to different
    tables: everything ``LoadedIndexBars.meta()`` publishes about the mapping
    row (``basis``, ``return_basis``, ``mapping_verified``) is a fact about one
    ETF's registered benchmark and has no meaning for a market-wide index.
    """

    #: Which series was wanted. Populated even when the fetch failed -- "we
    #: could not get ^TWII" is a more useful statement than "no benchmark".
    series_symbol: str | None = None
    label: str | None = None
    bars: list[PriceBar] = field(default_factory=list)
    status: DataStatus = DataStatus.UNAVAILABLE
    source: str = "none"
    staleness_minutes: int | None = None
    reason: str | None = None
    notes: list[str] = field(default_factory=list)

    @property
    def available(self) -> bool:
        """Whether a usable benchmark series came back."""
        return bool(self.bars)

    def meta(self) -> dict[str, object]:
        """The benchmark provenance block an endpoint can echo verbatim."""
        return {
            "series_symbol": self.series_symbol,
            "label": self.label,
            "available": self.available,
            "status": self.status.value,
            "source": self.source,
            "staleness_minutes": self.staleness_minutes,
            "bar_count": len(self.bars),
            "reason": self.reason,
            "notes": list(self.notes),
        }


def load_market_benchmark(
    resolver: IndexServiceResolver,
    *,
    market: Market,
    start: date,
    end: date,
) -> LoadedBenchmark:
    """Load ``market``'s benchmark index series, or say why there is none.

    Degrades exactly like :func:`load_index_series`: an unconfigured market, a
    market with no index service and a source that returned nothing are three
    different sentences, all of them empty results rather than exceptions, and
    none of them a substitute series.
    """
    benchmark = MARKET_BENCHMARK.get(market)
    if benchmark is None:
        return LoadedBenchmark(reason=NO_BENCHMARK_REASON.format(market=market))

    notes = [UNOFFICIAL_SOURCE_NOTE, UNVERIFIED_BENCHMARK_NOTE]
    service = resolver.get(market)
    if service is None:
        return LoadedBenchmark(
            series_symbol=benchmark.series_symbol,
            label=benchmark.label,
            reason=NO_SERVICE_REASON.format(market=market, series_symbol=benchmark.series_symbol),
            notes=notes,
        )

    result = service.get_daily_bars(benchmark.series_symbol, market, start, end)
    if result.status is DataStatus.UNAVAILABLE or not result.bars:
        return LoadedBenchmark(
            series_symbol=benchmark.series_symbol,
            label=benchmark.label,
            status=result.status,
            source=result.source,
            staleness_minutes=result.staleness_minutes,
            reason=with_provider_reason(
                NO_BARS_REASON.format(series_symbol=benchmark.series_symbol), result.reason
            ),
            notes=notes,
        )
    return LoadedBenchmark(
        series_symbol=benchmark.series_symbol,
        label=benchmark.label,
        bars=list(result.bars),
        status=disclosed_status(result.status),
        source=result.source,
        staleness_minutes=result.staleness_minutes,
        # Forwarded, never dropped (風控 2026-09-15 R1-b) -- see load_index_series.
        reason=result.reason,
        notes=notes,
    )


# --------------------------------------------------------------------------- #
# Replay snapshot fetch (ADR-0005 I-3 解釋性註記; ADR-0027 D-3; follow-up N-82)
# --------------------------------------------------------------------------- #
#
# Everything below is the ONE place a replay snapshot of ``^TWII`` is fetched.
# It is deliberately not an ``IndexSeriesService`` / ``MarketDataService`` path:
# those layers read the cache and would re-label a primary-source success
# ``FRESH``, and the replay snapshot needs the raw response fields (timestamp,
# ``meta.exchangeTimezoneName``, ``meta.gmtoffset``) that ``PriceBar`` does not
# carry. The sole caller is ``app/forecast/replay_checks.py``; nothing here may
# be handed to views, the API, valuation, signals or the leverage chapter.

REPLAY_UNSUPPORTED_SYMBOL_REASON = (
    "重放快照只取 {target}，不接受「{requested}」；本次不發出請求，也不以其他指數替代。"
)

REPLAY_FETCH_FAILED_REASON = (
    "重放快照取數失敗（{series_symbol}）：{detail}本次整次作廢，不回傳任何 bar，"
    "不改用快取或其他來源。"
)

REPLAY_MALFORMED_RESPONSE_REASON = (
    "重放快照取數失敗（{series_symbol}）：來源回傳的回應不完整或序號不連續，"
    "本次整次作廢，不回傳任何 bar。"
)


class ReplayChartBarLike(Protocol):
    """One raw bar as the replay adapter hands it over (structural; read-only)."""

    @property
    def raw_timestamp(self) -> object: ...
    @property
    def session_date(self) -> date: ...
    @property
    def open(self) -> Decimal: ...
    @property
    def high(self) -> Decimal: ...
    @property
    def low(self) -> Decimal: ...
    @property
    def close(self) -> Decimal: ...
    @property
    def volume(self) -> int: ...


class ReplayNullGapRowLike(Protocol):
    """An in-range row with a derivable date but a null OHLCV field (not a bar)."""

    @property
    def raw_timestamp(self) -> object: ...
    @property
    def session_date(self) -> date: ...
    @property
    def null_fields(self) -> tuple[str, ...]: ...


class ReplayChartResponseLike(Protocol):
    """One raw chart response: its ``meta`` values verbatim, its bars and null gaps."""

    @property
    def response_seq(self) -> int: ...
    @property
    def exchange_timezone_name(self) -> object: ...
    @property
    def gmtoffset(self) -> object: ...
    @property
    def bars(self) -> Sequence[ReplayChartBarLike]: ...
    @property
    def received_at(self) -> datetime: ...
    @property
    def null_gap_rows(self) -> Sequence[ReplayNullGapRowLike]: ...


class ReplayChartFetchLike(Protocol):
    """The adapter's all-or-nothing answer: ``reason`` set <=> no responses."""

    @property
    def index_symbol(self) -> str: ...
    @property
    def as_of(self) -> datetime: ...
    @property
    def source(self) -> str: ...
    @property
    def responses(self) -> Sequence[ReplayChartResponseLike]: ...
    @property
    def reason(self) -> str | None: ...


class ReplayIndexChartProvider(Protocol):
    """The slice of an index adapter the replay fetch needs.

    Structural, like :class:`IndexBarsProvider`: ``app/services/index.py``
    imports no concrete adapter. The raw-response method is *not* on the
    ``MarketDataProvider`` ABC, which is why the shape is declared here.
    """

    def get_index_raw_responses(
        self, index_symbol: str, start: date, end: date
    ) -> ReplayChartFetchLike: ...


@dataclass(frozen=True)
class ReplayIndexBar:
    """One snapshot bar: raw timestamp, the date derived from it, and OHLCV."""

    raw_timestamp: object
    session_date: date
    open: Decimal
    high: Decimal
    low: Decimal
    close: Decimal
    volume: int


@dataclass(frozen=True)
class ReplayIndexNullGapRow:
    """An in-range row the source reported with a null OHLCV field; never a bar."""

    raw_timestamp: object
    session_date: date
    null_fields: tuple[str, ...]


@dataclass(frozen=True)
class ReplayIndexResponse:
    """One response of the snapshot; ``meta`` values are the source's, untouched.

    ``received_at`` is when the response was received (the row-level
    ``fetched_at`` of ADR-0027); ``null_gap_rows`` are handed over as the
    adapter reported them.
    """

    response_seq: int
    exchange_timezone_name: object
    gmtoffset: object
    bars: tuple[ReplayIndexBar, ...]
    received_at: datetime
    null_gap_rows: tuple[ReplayIndexNullGapRow, ...] = ()


@dataclass(frozen=True)
class ReplayIndexSnapshot:
    """What :func:`fetch_replay_index_snapshot` returns -- for the replay snapshot only.

    Deliberately **not** a ``ProviderResult`` / ``LoadedIndexBars`` /
    ``LoadedBenchmark``, and it has no ``meta()`` and no ``notes``: the
    "backup, from a non-official source" disclosure obligation is carried by the
    replay-result disclosure (事先宣告 §4.7), not by this object (ADR-0005 I-3
    解釋性註記, 輸出去向). ``status`` is ``BACKUP`` or ``UNAVAILABLE`` and
    nothing else. On ``UNAVAILABLE`` there are no responses (and so no bars)
    and ``reason`` is non-empty.

    ``source`` is the source name the provider reported, or ``None`` when no
    source was contacted at all (the unsupported-symbol refusal). ``None`` is
    not a source name: ``replay_checks`` must not write it as one.
    """

    index_symbol: str
    status: DataStatus
    as_of: datetime
    source: str | None
    responses: tuple[ReplayIndexResponse, ...] = ()
    reason: str | None = None

    @property
    def bar_count(self) -> int:
        """Total bars over all responses."""
        return sum(len(response.bars) for response in self.responses)


def _replay_unavailable(
    index_symbol: str, as_of: datetime, source: str | None, reason: str
) -> ReplayIndexSnapshot:
    return ReplayIndexSnapshot(
        index_symbol=index_symbol,
        status=DataStatus.UNAVAILABLE,
        as_of=as_of,
        source=source,
        responses=(),
        reason=reason,
    )


def fetch_replay_index_snapshot(
    provider: ReplayIndexChartProvider,
    *,
    index_symbol: str,
    start: date,
    end: date,
) -> ReplayIndexSnapshot:
    """Fetch the ``^TWII`` replay snapshot live, or fail closed (ADR-0005 I-3 註記).

    * **One symbol.** Only ``MARKET_BENCHMARK["TW"]`` is accepted; any other
      ``index_symbol`` is ``UNAVAILABLE`` and the provider is not called.
    * **Live only.** No cache read or write, no fetch/attempt bookkeeping, no
      quota ledger, no ``MarketDataService`` / ``IndexSeriesService`` layer; the
      only thing called is the injected ``provider``.
    * **Status** is ``BACKUP`` on success (live from a non-official source) and
      ``UNAVAILABLE`` on failure -- never ``FRESH``, never ``CACHED_STALE``.
    * **Fail-closed.** Any provider-reported failure, a result with no
      response, a response without bars, or inconsistent response numbering
      makes the whole call ``UNAVAILABLE`` with no responses and a Traditional
      Chinese reason. Nothing falls back to a cache, another source or another
      symbol.
    * **Exceptions raised by the provider are not swallowed**, so a program
      error is not mixed up with a source failure. ``replay_checks`` must catch
      them, write a ``fetch_failed`` row carrying the exception class and a
      Chinese reason, and not retry within the same call; obligations (4-a) and
      (4-b) in ``work/reviews/2026-10-24-N82設計裁量點裁定-tech-architect.md``.

    The result is for ``app/forecast/replay_checks.py`` to store in the replay
    snapshot within the same call; it must not reach any user-visible surface.
    """
    target = MARKET_BENCHMARK["TW"].series_symbol
    if index_symbol != target:
        return _replay_unavailable(
            index_symbol,
            datetime.now(UTC),
            None,
            REPLAY_UNSUPPORTED_SYMBOL_REASON.format(target=target, requested=index_symbol),
        )

    fetched = provider.get_index_raw_responses(target, start, end)
    if fetched.reason is not None:
        detail = fetched.reason if fetched.reason.endswith("。") else fetched.reason + "。"
        return _replay_unavailable(
            target,
            fetched.as_of,
            fetched.source,
            REPLAY_FETCH_FAILED_REASON.format(series_symbol=target, detail=detail),
        )

    responses = tuple(fetched.responses)
    well_formed = (
        fetched.index_symbol == target
        and bool(responses)
        and [response.response_seq for response in responses] == list(range(1, len(responses) + 1))
        and all(response.bars for response in responses)
    )
    if not well_formed:
        return _replay_unavailable(
            target,
            fetched.as_of,
            fetched.source,
            REPLAY_MALFORMED_RESPONSE_REASON.format(series_symbol=target),
        )

    return ReplayIndexSnapshot(
        index_symbol=target,
        status=DataStatus.BACKUP,
        as_of=fetched.as_of,
        source=fetched.source,
        responses=tuple(
            ReplayIndexResponse(
                response_seq=response.response_seq,
                exchange_timezone_name=response.exchange_timezone_name,
                gmtoffset=response.gmtoffset,
                bars=tuple(
                    ReplayIndexBar(
                        raw_timestamp=bar.raw_timestamp,
                        session_date=bar.session_date,
                        open=bar.open,
                        high=bar.high,
                        low=bar.low,
                        close=bar.close,
                        volume=bar.volume,
                    )
                    for bar in response.bars
                ),
                received_at=response.received_at,
                null_gap_rows=tuple(
                    ReplayIndexNullGapRow(
                        raw_timestamp=gap.raw_timestamp,
                        session_date=gap.session_date,
                        null_fields=tuple(gap.null_fields),
                    )
                    for gap in response.null_gap_rows
                ),
            )
            for response in responses
        ),
        reason=None,
    )

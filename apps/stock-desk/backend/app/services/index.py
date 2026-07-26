"""Underlying-index daily series: ETF symbol -> :class:`IndexRef` -> bars.

This is the **single** junction between the pure ``app/leverage`` package and
the data layer (ADR-0005 constraint I-1). ``app/leverage/index_mapping.py``
answers "which series code, on what return basis"; this module answers "who can
fetch that code, and what came back".

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
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import date

from app.data.interface import DataStatus, Market, PriceBar
from app.leverage.index_mapping import (
    MAPPING_VERIFIED_ON,
    IndexRef,
    lookup_index_ref,
)
from app.portfolio.valuation import PriceService

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

NO_BARS_REASON = (
    "指數 {series_symbol} 在指定區間內沒有可用的日線資料（來源與快取皆無）。"
)

UNOFFICIAL_SOURCE_NOTE = (
    "指數序列取自非官方來源，資料狀態一律以 backup 呈現，不標示為即時（fresh）。"
)

UNVERIFIED_MAPPING_NOTE = (
    "標的指數對應表尚未經線上實際查詢查證（verified=false），"
    "序列代號是否確為該基金的標的指數屬待查證狀態。"
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
            reason=NO_BARS_REASON.format(series_symbol=ref.series_symbol),
            notes=notes,
        )
    return LoadedIndexBars(
        ref=ref,
        bars=list(result.bars),
        status=disclosed_status(result.status),
        source=result.source,
        staleness_minutes=result.staleness_minutes,
        notes=notes,
    )

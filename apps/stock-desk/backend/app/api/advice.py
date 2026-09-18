"""Advice card endpoint for one symbol.

``advice`` is the :func:`app.advice.engine.build_advice` output verbatim, so
every disclaimer, counterargument, invalidation condition and limit check the
engine attaches travels to the UI intact. The endpoint's own job is only to
assemble the two inputs the engine needs:

* the signal output for the symbol (same loader as ``/api/signals``), and
* a :class:`app.advice.limits.PortfolioContext` describing the holding and the
  book around it, built by :func:`app.advice.book.build_book_context`.

A symbol the user does not hold still gets a card: the context is then a
*candidate* (zero position, zero quantity) and ``held`` is ``false``, so the
rules that read position weight or unrealized P&L are skipped with their
missing fields named rather than evaluated against a fabricated position.
Whatever had to be assumed or left out is listed in ``context_notes``.
"""

from __future__ import annotations

from datetime import date, timedelta
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Query
from pydantic import ConfigDict

from app.advice.book import build_book_context, self_reported_net_worth
from app.advice.engine import build_advice
from app.api.common import EnvelopeBase, data_meta, now_iso
from app.api.deps import (
    get_cached_valuator,
    get_fx_provider,
    get_kelly_input_store,
    get_market_resolver,
    get_position_store,
    get_price_bar_cache,
    get_settings_store,
)
from app.api.kelly import kelly_inputs_for
from app.api.signals import DEFAULT_LOOKBACK_DAYS
from app.data.cache import PriceBarCache
from app.data.providers.fx import FxRateProvider
from app.kelly.store import KellyInputStore
from app.portfolio.summary import PortfolioSummary, build_summary
from app.portfolio.valuation import PositionValuator
from app.positions.models import Market
from app.positions.store import PositionStore
from app.services.fx import resolve_fx_quote
from app.services.market import MarketDataResolver, load_bars
from app.settings.store import SettingsStore
from app.signals.service import compute_signals

router = APIRouter(prefix="/api/advice", tags=["advice"])

ResolverDep = Annotated[MarketDataResolver, Depends(get_market_resolver)]
StoreDep = Annotated[PositionStore, Depends(get_position_store)]
#: ADR-0010 D-1: the card values the *book* from the local cache only. The
#: symbol itself is still loaded live (``load_bars`` below, R-6 order).
ValuatorDep = Annotated[PositionValuator, Depends(get_cached_valuator)]
SettingsDep = Annotated[SettingsStore, Depends(get_settings_store)]
FxProviderDep = Annotated[FxRateProvider, Depends(get_fx_provider)]
CalendarDep = Annotated[PriceBarCache, Depends(get_price_bar_cache)]
KellyStoreDep = Annotated[KellyInputStore, Depends(get_kelly_input_store)]


class AdviceResponse(EnvelopeBase):
    """``GET /api/advice/{symbol}``: a ``build_advice`` card plus its inputs."""

    model_config = ConfigDict(frozen=True)

    #: Exactly ``app.advice.engine.build_advice`` output, or ``None``.
    advice: dict[str, Any] | None
    #: Whether the user actually holds this symbol.
    held: bool
    #: Position ids rolled into the context (empty for a candidate).
    position_ids: list[int]
    #: The ``PortfolioContext`` the caps were evaluated against.
    portfolio_context: dict[str, Any]
    #: What had to be assumed, or was deliberately left out, and why.
    context_notes: list[str]


#: ADR-0010 D-1 standing disclosure, first in ``context_notes`` (風控 A-6): the
#: caps' book-level figures were valued from the local cache, not refreshed for
#: this request. States the date range the cached closes run to (a verifiable
#: fact, ADR-0009 D-5 style), the consequence for the caps (A-3) and the one
#: other path, the overview page, as a conditional fact. Wording by creative-lead
#: (`work/stock-desk-ADR-0010-揭露句-文案.md`), fixed verbatim by
#: risk-compliance-officer 2026-09-18 (三審): any change goes back to them, and
#: removing or silencing any of the three variants below reopens D-5.
#: The overview page is named as the other path, as a conditional fact and not
#: a promise of newer figures: its ladders run cache-first too (風控 複審 A-3).
_OVERVIEW_CLAUSE = (
    "總覽頁的整體持倉估值是否向來源查詢，同樣視快取涵蓋範圍而定，不代表其數字比本卡估值更新。"
)
CACHE_ONLY_BOOK_NOTE = (
    "本卡風險上限所用的整體持倉估值取自本機快取，本次未向來源更新；"
    "已估值持倉的價格分別截至 {earliest}～{latest}，上限判定可能建立在較舊的價格上。"
    + _OVERVIEW_CLAUSE
)
#: A-7: the same sentence when every cached close is from one day -- a zero-width
#: range reads like a bug, not like data.
CACHE_ONLY_BOOK_NOTE_SINGLE_DAY = (
    "本卡風險上限所用的整體持倉估值取自本機快取，本次未向來源更新；"
    "已估值持倉的價格皆截至 {date}，上限判定可能建立在較舊的價格上。" + _OVERVIEW_CLAUSE
)
#: A-1: holdings exist but none was valued (no cached price, or a price with
#: no FX rate -- the sentence names neither cause, both are covered). Same rank
#: as the note above, never silence: this is the state in which the reader is
#: least able to tell that the caps have nothing under them. An empty book
#: (no holdings at all) gets no note: there is nothing to qualify.
CACHE_ONLY_BOOK_NOTE_EMPTY = (
    "本卡風險上限所用的整體持倉估值本次未向來源更新，且本機目前沒有任何一筆持倉完成估值；"
    "以總資產為分母的相關比率，本次均無法計算。" + _OVERVIEW_CLAUSE
)


def _book_freshness_notes(summary: PortfolioSummary) -> list[str]:
    """The cache-only disclosure, dated by the cached closes actually *used*.

    Only ``ok`` valuations feed the totals and the caps' denominators, so only
    their dates may set the range (風控 A-2): a holding that has a cached price
    but no FX rate is not in the book, and letting its date pull ``latest``
    forward would make the book look newer than what was actually used. With
    no usable cached price at all the sentence changes, it does not disappear
    (A-1).
    """
    if not summary.positions:
        return []  # nothing held, nothing to qualify (風控 複審 A-1)
    dates = sorted(
        item.valuation.price.as_of
        for item in summary.positions
        if item.valuation.status == "ok" and item.valuation.price is not None
    )
    if not dates:
        return [CACHE_ONLY_BOOK_NOTE_EMPTY]
    if dates[0] == dates[-1]:
        return [CACHE_ONLY_BOOK_NOTE_SINGLE_DAY.format(date=dates[0])]
    return [CACHE_ONLY_BOOK_NOTE.format(earliest=dates[0], latest=dates[-1])]


@router.get("/{symbol}", response_model=AdviceResponse)
def get_advice(
    symbol: str,
    resolver: ResolverDep,
    store: StoreDep,
    valuator: ValuatorDep,
    settings_store: SettingsDep,
    fx_provider: FxProviderDep,
    calendar_source: CalendarDep,
    kelly_store: KellyStoreDep,
    market: Annotated[Market, Query(description="市場別")] = "TW",
) -> AdviceResponse:
    end = date.today()
    loaded = load_bars(
        resolver,
        symbol=symbol,
        market=market,
        start=end - timedelta(days=DEFAULT_LOOKBACK_DAYS),
        end=end,
        # This endpoint is the one that publishes the 資料過舊 notice, so it is
        # the one that pays for the calendar lookup (C4).
        calendar_source=calendar_source,
    )
    summary = build_summary(store, valuator)
    settings = settings_store.load()
    budget = settings.risk_budget
    # The gross-exposure cap's denominator, or ``None`` while the user has not
    # reported one -- in which case that cap stays ``not_evaluable`` as before.
    net_worth = self_reported_net_worth(
        settings.net_worth.total_net_worth_twd, settings.net_worth.updated_at
    )

    latest = max(loaded.bars, key=lambda bar: bar.date) if loaded.bars else None
    signals = compute_signals(symbol, loaded.bars) if loaded.bars else {}
    # The rate is resolved as of the bar being converted, not "today": the caps
    # compare a close from that date, so the conversion has to be from it too.
    fx = (
        resolve_fx_quote(fx_provider, currency=latest.currency, on=latest.date)
        if latest is not None
        else None
    )
    book = build_book_context(
        summary,
        symbol=symbol,
        market=market,
        close=float(latest.close) if latest is not None else None,
        currency=latest.currency if latest is not None else None,
        fx=fx,
        net_worth=net_worth,
        # Cap 5's stored pair for this holding. Absent means "never entered",
        # which is what the cap then says; an expired one still travels, with
        # its age, so the cap can say *that* instead (D-6).
        kelly=kelly_inputs_for(kelly_store, symbol, market),
    )

    if latest is None:
        # Without a price the card would have no evidence at all: every
        # indicator would be missing and every price-based cap not evaluable.
        # Say so instead of emitting an empty card.
        return AdviceResponse(
            symbol=symbol,
            market=market,
            status="insufficient_data",
            reason=loaded.reason,
            advice=None,
            held=book.held,
            position_ids=book.position_ids,
            portfolio_context=book.context.model_dump(),
            # No card, no caps: the freshness note has nothing to qualify here,
            # and the page renders only the insufficient panel (風控 A-8).
            context_notes=book.notes,
            data=data_meta(loaded.meta()),
            as_of=now_iso(),
        )

    card = build_advice(
        symbol=symbol,
        signals=signals,
        portfolio=book.context,
        budget=budget,
    )
    return AdviceResponse(
        symbol=symbol,
        market=market,
        status="ok",
        reason=None,
        advice=card,
        held=book.held,
        position_ids=book.position_ids,
        portfolio_context=book.context.model_dump(),
        # First, not last (風控 A-6): this sentence qualifies every figure the
        # notes after it are about.
        context_notes=[*_book_freshness_notes(summary), *book.notes],
        data=data_meta(loaded.meta()),
        as_of=now_iso(),
    )

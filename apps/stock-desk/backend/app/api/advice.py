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
    get_fx_provider,
    get_market_resolver,
    get_position_store,
    get_settings_store,
    get_valuator,
)
from app.api.signals import DEFAULT_LOOKBACK_DAYS
from app.data.providers.fx import FxRateProvider
from app.portfolio.summary import build_summary
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
ValuatorDep = Annotated[PositionValuator, Depends(get_valuator)]
SettingsDep = Annotated[SettingsStore, Depends(get_settings_store)]
FxProviderDep = Annotated[FxRateProvider, Depends(get_fx_provider)]


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


@router.get("/{symbol}", response_model=AdviceResponse)
def get_advice(
    symbol: str,
    resolver: ResolverDep,
    store: StoreDep,
    valuator: ValuatorDep,
    settings_store: SettingsDep,
    fx_provider: FxProviderDep,
    market: Annotated[Market, Query(description="市場別")] = "TW",
) -> AdviceResponse:
    end = date.today()
    loaded = load_bars(
        resolver,
        symbol=symbol,
        market=market,
        start=end - timedelta(days=DEFAULT_LOOKBACK_DAYS),
        end=end,
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
        context_notes=book.notes,
        data=data_meta(loaded.meta()),
        as_of=now_iso(),
    )

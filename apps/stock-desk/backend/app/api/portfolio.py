"""Portfolio summary and book-level risk-cap endpoints."""

from __future__ import annotations

from datetime import date, timedelta
from typing import Annotated

from fastapi import APIRouter, Depends
from pydantic import BaseModel, ConfigDict

from app.advice.book import self_reported_net_worth
from app.advice.book_limits import (
    BookLimitCheck,
    SymbolMarketInput,
    evaluate_book_limits,
)
from app.api.common import DataMeta, data_meta, now_iso
from app.api.deps import (
    get_fx_provider,
    get_market_resolver,
    get_position_store,
    get_settings_store,
    get_valuator,
)
from app.api.signals import DEFAULT_LOOKBACK_DAYS
from app.data.providers.fx import FxRateProvider
from app.portfolio.summary import PortfolioSummary, build_summary
from app.portfolio.valuation import PositionValuator
from app.positions.models import Market
from app.positions.store import PositionStore
from app.services.fx import resolve_fx_quote
from app.services.market import MarketDataResolver, load_bars
from app.settings.store import SettingsStore
from app.signals.service import (
    SignalConfig,
    TechnicalConfig,
    atr_from_signals,
    compute_signals,
)

router = APIRouter(prefix="/api/portfolio", tags=["portfolio"])

StoreDep = Annotated[PositionStore, Depends(get_position_store)]
ValuatorDep = Annotated[PositionValuator, Depends(get_valuator)]
ResolverDep = Annotated[MarketDataResolver, Depends(get_market_resolver)]
SettingsDep = Annotated[SettingsStore, Depends(get_settings_store)]
FxProviderDep = Annotated[FxRateProvider, Depends(get_fx_provider)]

#: Only cap 4 reads a signal here, and it reads exactly one: ATR(14). Computing
#: the other nine indicators once per holding would cost the whole book's worth
#: of work for numbers nobody in this response looks at.
_ATR_ONLY = SignalConfig(
    enable_risk=False,
    technical=TechnicalConfig(
        moving_averages=False,
        rsi=False,
        macd=False,
        bollinger=False,
        atr=True,
        kd=False,
        volume_zscore=False,
    ),
)


class SymbolDataMeta(BaseModel):
    """Where one holding's bars came from, for the caps that read a price.

    ATR(14) is smoothed over the whole loaded window, so "which rung of the
    ladder answered, and how stale is it" is part of reading cap 4's verdict --
    the same provenance ``/api/advice/{symbol}`` carries, one entry per holding.
    """

    model_config = ConfigDict(frozen=True)

    symbol: str
    market: Market
    data: DataMeta


class PortfolioLimitsResponse(BaseModel):
    """``GET /api/portfolio/limits``: the five caps judged over the whole book."""

    model_config = ConfigDict(frozen=True)

    limits: list[BookLimitCheck]
    #: What the book had to assume or leave out (``app.advice.book`` notes).
    notes: list[str]
    #: One entry per holding whose bars were loaded, in book order.
    sources: list[SymbolDataMeta]
    as_of: str


@router.get("/summary", response_model=PortfolioSummary)
def portfolio_summary(store: StoreDep, valuator: ValuatorDep) -> PortfolioSummary:
    return build_summary(store, valuator)


@router.get("/limits", response_model=PortfolioLimitsResponse)
def portfolio_limits(
    store: StoreDep,
    valuator: ValuatorDep,
    resolver: ResolverDep,
    settings_store: SettingsDep,
    fx_provider: FxProviderDep,
) -> PortfolioLimitsResponse:
    """Judge the whole book against the five risk caps (FR-8).

    The overview used to report all five as ``not_evaluable`` because no
    endpoint aggregated them; this one does the aggregation
    (:mod:`app.advice.book_limits`) from the same inputs the per-symbol advice
    card uses, so a cap that is still ``not_evaluable`` here is one whose input
    is genuinely missing -- and says which.

    Bars are loaded per holding, exactly as the card does for one symbol: cap 4
    needs each holding's ATR(14) and its price in TWD. A holding whose bars (or
    FX rate) could not be resolved is not guessed at -- it is left out of that
    cap's comparison and listed in ``excluded`` with the reason.
    """
    summary = build_summary(store, valuator)
    settings = settings_store.load()
    net_worth = self_reported_net_worth(
        settings.net_worth.total_net_worth_twd, settings.net_worth.updated_at
    )

    market_data: dict[tuple[str, Market], SymbolMarketInput] = {}
    sources: list[SymbolDataMeta] = []
    for symbol, market in _held_symbols(summary):
        loaded = load_bars(
            resolver,
            symbol=symbol,
            market=market,
            start=date.today() - timedelta(days=DEFAULT_LOOKBACK_DAYS),
            end=date.today(),
        )
        sources.append(
            SymbolDataMeta(symbol=symbol, market=market, data=data_meta(loaded.meta()))
        )
        if not loaded.bars:
            continue
        latest = max(loaded.bars, key=lambda bar: bar.date)
        signals = compute_signals(symbol, loaded.bars, config=_ATR_ONLY)
        market_data[(symbol.strip().upper(), market)] = SymbolMarketInput(
            close=float(latest.close),
            currency=latest.currency,
            atr=atr_from_signals(signals),
            # As of the bar being converted, not "today": the caps compare a
            # close from that date, so the conversion has to be from it too.
            fx=resolve_fx_quote(fx_provider, currency=latest.currency, on=latest.date),
        )

    report = evaluate_book_limits(
        summary, settings.risk_budget, net_worth=net_worth, market_data=market_data
    )
    return PortfolioLimitsResponse(
        limits=report.limits, notes=report.notes, sources=sources, as_of=now_iso()
    )


def _held_symbols(summary: PortfolioSummary) -> list[tuple[str, Market]]:
    """Distinct ``(symbol, market)`` pairs in the book, in position order.

    Market is part of the key for the reason
    :func:`app.advice.book_limits._group_positions` gives: the same ticker in two
    markets is two instruments, and they are priced from two different chains.
    """
    seen: dict[tuple[str, Market], str] = {}
    for position in summary.positions:
        seen.setdefault((position.symbol.strip().upper(), position.market), position.symbol)
    return [(symbol, market) for (_, market), symbol in seen.items()]

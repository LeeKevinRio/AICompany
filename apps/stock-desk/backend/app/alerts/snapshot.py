"""Build a :class:`SymbolSnapshot` from the real services.

This is the one place that wires "symbol -> bars -> signals -> risk caps", so
the alert engine, the alert API and the scheduler all observe the same numbers
the ``/api/signals`` and ``/api/advice`` endpoints show. Keeping it out of
``app/alerts/engine.py`` leaves the engine free of data access and therefore
testable without a network or a database.
"""

from __future__ import annotations

from datetime import date, timedelta

from app.advice.book import build_book_context
from app.advice.limits import KellyInputs, RiskBudget, SelfReportedNetWorth, evaluate_limits
from app.alerts.engine import SymbolSnapshot
from app.data.interface import DataStatus
from app.data.providers.fx import FxRateProvider
from app.portfolio.summary import build_summary
from app.portfolio.valuation import PositionValuator
from app.positions.models import Market
from app.positions.store import PositionStore
from app.services.fx import resolve_fx_quote
from app.services.market import MarketDataResolver, load_bars
from app.signals.service import atr_from_signals, compute_signals


def build_snapshot(
    symbol: str,
    market: Market,
    *,
    resolver: MarketDataResolver,
    store: PositionStore,
    valuator: PositionValuator,
    budget: RiskBudget,
    fx_provider: FxRateProvider | None = None,
    net_worth: SelfReportedNetWorth | None = None,
    kelly: KellyInputs | None = None,
    lookback_days: int = 400,
    today: date | None = None,
) -> SymbolSnapshot:
    """Fetch bars, run the signal layer, and evaluate the risk caps for one symbol.

    A missing market adapter, an unavailable provider or an empty bar list all
    produce a thin snapshot with ``reason`` set, which the engine turns into a
    *skipped* rule rather than a silent non-firing one.

    ``fx_provider`` is what makes the price-based caps evaluable for a non-TWD
    holding. Without it (or without a usable rate) those caps stay
    ``not_evaluable``; a snapshot has no notes list, so the sentence naming the
    missing conversion is appended to ``reason``, which the engine shows on the
    resulting **skip**.

    ``net_worth`` is what makes the gross-exposure cap evaluable at all, so a
    ``risk_limit_breach`` rule watching it can only fire once the user has
    reported one and while that report is still fresh. Without it the cap is
    ``not_evaluable`` and the rule reports a skip -- never a silent non-firing.

    ``kelly`` does the same for cap 5, and the caller resolves it for the same
    reason it resolves the net worth: this module reaches the stores it was
    handed and no others. Without it cap 5 reports "nothing entered yet", so a
    loader that has a pair and omits it would make a ``risk_limit_breach`` rule
    silently stop watching an input the user did enter.

    The FX source's standing disclosure (ADR-0005 約束 F-4) travels on its own
    field instead, because it has the opposite destination: it qualifies a rate
    that *was* applied, so it belongs to the risk-cap message a **fired** alert
    sends -- and ``reason`` is read by no fired path. Putting it in ``reason``
    would look like a disclosure while reaching nobody.
    """
    end = today if today is not None else date.today()
    loaded = load_bars(
        resolver, symbol=symbol, market=market, start=end - timedelta(days=lookback_days), end=end
    )
    if not loaded.bars:
        return SymbolSnapshot(symbol=symbol, market=market, reason=loaded.reason)

    latest = max(loaded.bars, key=lambda bar: bar.date)
    close = float(latest.close)
    signals = compute_signals(symbol, loaded.bars)
    atr = atr_from_signals(signals)

    summary = build_summary(store, valuator)
    fx = resolve_fx_quote(fx_provider, currency=latest.currency, on=latest.date)
    book = build_book_context(
        summary,
        symbol=symbol,
        market=market,
        close=close,
        currency=latest.currency,
        atr=atr,
        fx=fx,
        net_worth=net_worth,
        kelly=kelly,
    )
    data_reason = (
        None
        if loaded.status is DataStatus.FRESH
        else f"資料來自 {loaded.status.value} 層（{loaded.source}）。"
    )
    # Disclosed on exactly the condition ``build_book_context`` uses: only a
    # rate that was actually applied to a figure needs its methodology stated.
    # A TWD holding resolves no quote at all, and a failed lookup has nothing to
    # disclose because nothing was converted -- ``book.fx_note`` covers that.
    fx_disclosure = fx.source_note if fx is not None and book.fx_rate is not None else None
    return SymbolSnapshot(
        symbol=symbol,
        market=market,
        close=close,
        currency=latest.currency,
        signals=signals,
        limits=evaluate_limits(budget, book.context),
        as_of=latest.date.isoformat(),
        reason=_joined_reason(data_reason, book.fx_note),
        fx_disclosure=fx_disclosure,
    )


def _joined_reason(*parts: str | None) -> str | None:
    """Join the non-empty qualifiers into one sentence, or ``None`` if there are none."""
    present = [part for part in parts if part]
    return " ".join(present) if present else None

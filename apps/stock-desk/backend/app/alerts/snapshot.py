"""Build a :class:`SymbolSnapshot` from the real services.

This is the one place that wires "symbol -> bars -> signals -> risk caps" for
the alert engine, the alert API and the scheduler. The bars are loaded over the
shared observation window (``app.signals.window.OBSERVATION_LOOKBACK_DAYS``,
ADR-0020) -- the same window ``/api/signals`` and ``/api/advice`` load -- so for
the same symbol, bars and day an alert sees the same window-sensitive numbers
(``drawdown.current``, ``drawdown.max_drawdown``, ``volatility.annualized``) the
advice card shows. Beta is not among them: like the advice card, the snapshot
loads no benchmark (ADR-0021 K-7; ``/api/signals`` alone loads one), which is
why ``beta.value`` is outside :data:`app.advice.context.ALERT_RULE_FIELDS` --
the set of fields a snapshot can produce, and the only fields a new alert rule
may name (ADR-0021 K-1). Keeping this out of ``app/alerts/engine.py`` leaves the
engine free of data access and therefore testable without a network or a
database.
"""

from __future__ import annotations

from datetime import date, timedelta
from typing import Any

from app.advice.book import build_book_context
from app.advice.limits import KellyInputs, RiskBudget, SelfReportedNetWorth, evaluate_limits
from app.alerts.engine import SymbolSnapshot, usable_price
from app.data.interface import DataStatus
from app.data.providers.fx import FxRateProvider
from app.portfolio.summary import build_summary
from app.portfolio.valuation import PositionValuator
from app.positions.models import Market
from app.positions.store import PositionStore
from app.services.fx import resolve_fx_quote
from app.services.market import MarketDataResolver, load_bars
from app.signals.service import atr_from_signals, compute_signals
from app.signals.window import OBSERVATION_LOOKBACK_DAYS


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
    today: date | None = None,
) -> SymbolSnapshot:
    """Fetch bars, run the signal layer, and evaluate the risk caps for one symbol.

    The window is ``[today - OBSERVATION_LOOKBACK_DAYS, today]`` and is not a
    parameter: a caller-chosen length is how this path drifted from the advice
    card's in the first place (ADR-0020).

    A missing market adapter, an unavailable provider or an empty bar list all
    produce a thin snapshot with ``reason`` set and no ``limits``, which the
    engine turns into a *skipped* rule rather than a silent non-firing one:
    ``reason`` is what a price or signal rule shows; a risk-limit rule has no
    caps to read and shows its own fixed sentence. ``reason`` is never the tail
    of a risk-limit skip (see ``price_cap_cause`` below).

    A latest bar whose close is unusable (zero, negative or non-finite -- the
    one definition is :func:`app.alerts.engine.usable_price`) produces an
    empty snapshot too: the signal layer is not run (``signals`` is empty), and
    the risk caps are built with no price and no ATR, so the price-based caps
    report ``not_evaluable`` instead of the whole tick failing on
    ``PortfolioContext.close``. Signals are withheld rather than computed
    because a bad latest bar would feed figures such as ``drawdown.current``
    that a rule could fire on. ``close`` keeps the bar's raw value so the
    engine's own guard names the price as the missing input on a price rule.

    ``fx_provider`` is what makes the price-based caps evaluable for a non-TWD
    holding. Without it (or without a usable rate) those caps stay
    ``not_evaluable``; a snapshot has no notes list, so the sentence naming the
    missing conversion travels on ``price_cap_cause`` -- that sentence alone,
    never the data layer's note or an applied-rate note -- which the engine
    appends to a risk-limit **skip** only when a watched cap that reads the
    price or ATR is among the unevaluated ones and the close itself is usable.
    ``reason`` still ends with the same sentence; its composition is unchanged.

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
        resolver,
        symbol=symbol,
        market=market,
        start=end - timedelta(days=OBSERVATION_LOOKBACK_DAYS),
        end=end,
    )
    if not loaded.bars:
        return SymbolSnapshot(symbol=symbol, market=market, reason=loaded.reason)

    latest = max(loaded.bars, key=lambda bar: bar.date)
    close = float(latest.close)
    priced = usable_price(close)
    signals: dict[str, Any] = {}
    atr: float | None = None
    if priced is not None:
        signals = compute_signals(symbol, loaded.bars)
        atr = atr_from_signals(signals)

    summary = build_summary(store, valuator)
    fx = resolve_fx_quote(fx_provider, currency=latest.currency, on=latest.date)
    book = build_book_context(
        summary,
        symbol=symbol,
        market=market,
        close=priced,
        currency=latest.currency,
        atr=atr,
        fx=fx,
        net_worth=net_worth,
        kelly=kelly,
    )
    # The data layer's own sentence (served from cache, spliced sources -- ADR-0009
    # D-7) is kept next to the layer note, never replaced by it: a spliced series
    # arrives as ``fresh`` and would otherwise say nothing (風控 2026-09-15 R1-a).
    layer_note = (
        None
        if loaded.status is DataStatus.FRESH
        else f"資料來自 {loaded.status.value} 層（{loaded.source}）。"
    )
    data_reason = _joined_reason(layer_note, loaded.reason)
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
        # Only a *failed* conversion is a cause: ``fx_note`` on an applied rate
        # is the methodology sentence, and on a mixed-currency holding it is None.
        price_cap_cause=book.fx_note if book.fx_rate is None else None,
        fx_disclosure=fx_disclosure,
        # Layer note included (風控 R4-a): a crossing judged on a cached bar must
        # say so where the user reads it, not only on the badge the push lacks.
        data_disclosure=data_reason,
    )


def _joined_reason(*parts: str | None) -> str | None:
    """Join the non-empty qualifiers into one sentence, or ``None`` if there are none."""
    present = [part for part in parts if part]
    return " ".join(present) if present else None

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
from app.advice.limits import RiskBudget, evaluate_limits
from app.alerts.engine import SymbolSnapshot
from app.data.interface import DataStatus
from app.data.providers.fx import FxRateProvider
from app.portfolio.summary import build_summary
from app.portfolio.valuation import PositionValuator
from app.positions.models import Market
from app.positions.store import PositionStore
from app.services.fx import resolve_fx_quote
from app.services.market import MarketDataResolver, load_bars
from app.signals.service import compute_signals


def build_snapshot(
    symbol: str,
    market: Market,
    *,
    resolver: MarketDataResolver,
    store: PositionStore,
    valuator: PositionValuator,
    budget: RiskBudget,
    fx_provider: FxRateProvider | None = None,
    lookback_days: int = 400,
    today: date | None = None,
) -> SymbolSnapshot:
    """Fetch bars, run the signal layer, and evaluate the risk caps for one symbol.

    A missing market adapter, an unavailable provider or an empty bar list all
    produce a thin snapshot with ``reason`` set, which the engine turns into a
    *skipped* rule rather than a silent non-firing one.

    ``fx_provider`` is what makes the price-based caps evaluable for a non-TWD
    holding. Without it (or without a usable rate) those caps stay
    ``not_evaluable`` and the reason says the conversion was missing -- a
    snapshot has no notes list, so that sentence is appended to ``reason``
    rather than dropped.
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
    atr = _atr_from_signals(signals)

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
    )
    data_reason = (
        None
        if loaded.status is DataStatus.FRESH
        else f"資料來自 {loaded.status.value} 層（{loaded.source}）。"
    )
    return SymbolSnapshot(
        symbol=symbol,
        market=market,
        close=close,
        currency=latest.currency,
        signals=signals,
        limits=evaluate_limits(budget, book.context),
        as_of=latest.date.isoformat(),
        reason=_joined_reason(data_reason, book.fx_note),
    )


def _joined_reason(*parts: str | None) -> str | None:
    """Join the non-empty qualifiers into one sentence, or ``None`` if there are none."""
    present = [part for part in parts if part]
    return " ".join(present) if present else None


def _atr_from_signals(signals: dict[str, object]) -> float | None:
    """ATR(14) out of a ``compute_signals`` output, or ``None`` if absent."""
    technical = signals.get("technical")
    if not isinstance(technical, dict):  # pragma: no cover - the layer is always on
        return None
    atr_block = technical.get("atr")
    if not isinstance(atr_block, dict):  # pragma: no cover - same
        return None
    last = atr_block.get("last")
    if not isinstance(last, dict):  # pragma: no cover - same
        return None
    value = last.get("atr")
    return float(value) if isinstance(value, int | float) and not isinstance(value, bool) else None

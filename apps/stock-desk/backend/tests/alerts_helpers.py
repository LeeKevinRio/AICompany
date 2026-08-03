"""Builders for the alert tests: rule payloads and canned snapshots."""

from __future__ import annotations

from typing import Any

from app.advice.limits import PortfolioContext, RiskBudget, evaluate_limits
from app.alerts.engine import SymbolSnapshot
from app.alerts.models import AlertRuleInput
from app.alerts.store import AlertStore
from app.positions.models import Market


def price_rule(
    *, above: bool = True, threshold: float = 100.0, symbol: str = "2330", **overrides: Any
) -> dict[str, Any]:
    """A ``price_above`` / ``price_below`` rule payload."""
    payload: dict[str, Any] = {
        "type": "price_above" if above else "price_below",
        "symbol": symbol,
        "market": "TW",
        "params": {"threshold": threshold},
        "enabled": True,
    }
    payload.update(overrides)
    return payload


def signal_rule(
    *,
    field: str = "rsi14.last",
    op: str = "gt",
    value: float = 70.0,
    symbol: str = "2330",
    **overrides: Any,
) -> dict[str, Any]:
    """A ``signal_condition`` rule payload."""
    payload: dict[str, Any] = {
        "type": "signal_condition",
        "symbol": symbol,
        "market": "TW",
        "params": {"condition": {"field": field, "op": op, "value": value}},
        "enabled": True,
    }
    payload.update(overrides)
    return payload


def limit_rule(*, limit_id: str = "any", symbol: str = "2330", **overrides: Any) -> dict[str, Any]:
    """A ``risk_limit_breach`` rule payload."""
    payload: dict[str, Any] = {
        "type": "risk_limit_breach",
        "symbol": symbol,
        "market": "TW",
        "params": {"limit_id": limit_id},
        "enabled": True,
    }
    payload.update(overrides)
    return payload


def add_rule(store: AlertStore, payload: dict[str, Any]) -> Any:
    """Validate ``payload`` and store it, returning the stored rule."""
    return store.create_rule(AlertRuleInput.model_validate(payload))


def snapshot(
    *,
    symbol: str = "2330",
    market: Market = "TW",
    close: float | None = 120.0,
    currency: str = "TWD",
    signals: dict[str, Any] | None = None,
    context: PortfolioContext | None = None,
    budget: RiskBudget | None = None,
    reason: str | None = None,
    fx_disclosure: str | None = None,
) -> SymbolSnapshot:
    """A snapshot with only the parts a test needs; the rest stays empty."""
    limits = (
        evaluate_limits(budget or RiskBudget(), context) if context is not None else ()
    )
    return SymbolSnapshot(
        symbol=symbol,
        market=market,
        close=close,
        currency=currency,
        signals=signals or {},
        limits=limits,
        as_of="2026-07-25",
        reason=reason,
        fx_disclosure=fx_disclosure,
    )


class RecordingLoader:
    """A :data:`SnapshotLoader` that returns one snapshot and records its calls."""

    def __init__(self, snap: SymbolSnapshot) -> None:
        self._snapshot = snap
        self.calls: list[tuple[str, Market]] = []

    def __call__(self, symbol: str, market: Market) -> SymbolSnapshot:
        self.calls.append((symbol, market))
        return self._snapshot


def breaching_context(symbol: str = "2330") -> PortfolioContext:
    """A book whose single-position weight is over the 15% cap."""
    return PortfolioContext(
        symbol=symbol,
        total_equity_twd=1_000_000.0,
        position_market_value_twd=300_000.0,
        quantity=3_000.0,
        close=100.0,
    )


def compliant_context(symbol: str = "2330") -> PortfolioContext:
    """A book comfortably inside every evaluable cap."""
    return PortfolioContext(
        symbol=symbol,
        total_equity_twd=1_000_000.0,
        position_market_value_twd=50_000.0,
        quantity=500.0,
        close=100.0,
        atr=2.0,
    )

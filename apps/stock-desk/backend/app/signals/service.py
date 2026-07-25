"""Aggregate the technical and risk layers for a single symbol.

Produces a machine-readable ``dict`` (later consumed by the API/UI) with a
technical block and a risk block, each layer independently switchable through a
:class:`SignalConfig` flag so a caller can, e.g., request risk only. Every
sub-result keeps its own ``inputs_used`` / ``as_of`` / ``source`` so provenance
survives aggregation.

This is a measurement surface, not an advice surface: it emits numbers and
explicit states only. There is deliberately no target price, score, rating, or
buy/sell field anywhere in the output -- recommendation logic is the later,
separately reviewed M3 phase.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from app.data.interface import PriceBar
from app.signals import risk, technical
from app.signals.frame import provenance


@dataclass(frozen=True)
class TechnicalConfig:
    """Per-indicator on/off switches for the technical layer."""

    moving_averages: bool = True
    rsi: bool = True
    macd: bool = True
    bollinger: bool = True
    atr: bool = True
    kd: bool = True
    volume_zscore: bool = True


@dataclass(frozen=True)
class RiskConfig:
    """Per-metric on/off switches for the (single-symbol) risk layer."""

    volatility: bool = True
    drawdown: bool = True
    beta: bool = True


@dataclass(frozen=True)
class SignalConfig:
    """Top-level switches: whole layers plus per-item toggles."""

    enable_technical: bool = True
    enable_risk: bool = True
    technical: TechnicalConfig = field(default_factory=TechnicalConfig)
    risk: RiskConfig = field(default_factory=RiskConfig)


def compute_signals(
    symbol: str,
    bars: list[PriceBar],
    *,
    benchmark_bars: list[PriceBar] | None = None,
    benchmark_label: str | None = None,
    config: SignalConfig | None = None,
) -> dict[str, Any]:
    """Run the enabled technical and risk layers for one symbol.

    ``benchmark_bars`` (TWSE index for TW, SPY for US) is passed straight to the
    beta calculation; without it beta reports ``insufficient_data`` rather than
    guessing a market proxy.
    """
    cfg = config or SignalConfig()
    as_of, source = provenance(bars)
    output: dict[str, Any] = {
        "symbol": symbol,
        "bar_count": len(bars),
        "as_of": as_of,
        "source": source,
    }

    if cfg.enable_technical:
        tech: dict[str, Any] = {}
        if cfg.technical.moving_averages:
            tech["moving_averages"] = technical.moving_averages(bars).model_dump()
        if cfg.technical.rsi:
            tech["rsi"] = technical.rsi(bars).model_dump()
        if cfg.technical.macd:
            tech["macd"] = technical.macd(bars).model_dump()
        if cfg.technical.bollinger:
            tech["bollinger"] = technical.bollinger(bars).model_dump()
        if cfg.technical.atr:
            tech["atr"] = technical.atr(bars).model_dump()
        if cfg.technical.kd:
            tech["kd"] = technical.kd(bars).model_dump()
        if cfg.technical.volume_zscore:
            tech["volume_zscore"] = technical.volume_zscore(bars).model_dump()
        output["technical"] = tech

    if cfg.enable_risk:
        risk_block: dict[str, Any] = {}
        if cfg.risk.volatility:
            risk_block["volatility"] = risk.volatility(bars).model_dump()
        if cfg.risk.drawdown:
            risk_block["drawdown"] = risk.drawdown(bars).model_dump()
        if cfg.risk.beta:
            risk_block["beta"] = risk.position_beta(
                bars, benchmark_bars, benchmark_label=benchmark_label
            ).model_dump()
        output["risk"] = risk_block

    return output


def compute_correlation(
    symbol_bars: dict[str, list[PriceBar]], *, min_overlap: int = 3
) -> dict[str, Any]:
    """Portfolio-level: pairwise return correlation across several symbols."""
    return risk.correlation_matrix(symbol_bars, min_overlap=min_overlap).model_dump()

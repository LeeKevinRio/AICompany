"""Tests for the signal aggregation service and its layer toggles."""

from __future__ import annotations

from app.signals.service import (
    RiskConfig,
    SignalConfig,
    TechnicalConfig,
    compute_correlation,
    compute_signals,
)
from tests.signals_helpers import bars_from_closes


def test_compute_signals_full_output_shape() -> None:
    bars = bars_from_closes([100.0 + i for i in range(60)], source="finmind")
    out = compute_signals("2330", bars)
    assert out["symbol"] == "2330"
    assert out["bar_count"] == 60
    assert out["source"] == "finmind"
    assert set(out["technical"].keys()) == {
        "moving_averages",
        "rsi",
        "macd",
        "bollinger",
        "atr",
        "kd",
        "volume_zscore",
    }
    assert set(out["risk"].keys()) == {"volatility", "drawdown", "beta"}
    # Beta is insufficient without a benchmark, but present and honest about it.
    assert out["risk"]["beta"]["status"] == "insufficient_data"


def test_compute_signals_with_benchmark_beta_ok() -> None:
    bars = bars_from_closes([100.0 + i * 0.5 for i in range(30)], symbol="AAA")
    bench = bars_from_closes([100.0 + i * 0.25 for i in range(30)], symbol="IDX")
    out = compute_signals("AAA", bars, benchmark_bars=bench, benchmark_label="TWSE")
    assert out["risk"]["beta"]["status"] == "ok"
    assert out["risk"]["beta"]["benchmark"] == "TWSE"


def test_layer_and_indicator_toggles() -> None:
    bars = bars_from_closes([100.0 + i for i in range(60)])
    cfg = SignalConfig(
        enable_risk=False,
        technical=TechnicalConfig(rsi=True, macd=False, moving_averages=False,
                                  bollinger=False, atr=False, kd=False, volume_zscore=False),
    )
    out = compute_signals("X", bars, config=cfg)
    assert "risk" not in out
    assert set(out["technical"].keys()) == {"rsi"}


def test_risk_only_configuration() -> None:
    bars = bars_from_closes([100.0 + i for i in range(30)])
    cfg = SignalConfig(enable_technical=False, risk=RiskConfig(beta=False))
    out = compute_signals("X", bars, config=cfg)
    assert "technical" not in out
    assert set(out["risk"].keys()) == {"volatility", "drawdown"}


def test_no_recommendation_fields_present() -> None:
    # Red line: the signal surface must never emit advice/target-price semantics.
    bars = bars_from_closes([100.0 + i for i in range(60)])
    out = compute_signals("X", bars)
    banned = {"target_price", "recommendation", "rating", "signal_action",
              "buy", "sell", "action", "verdict"}
    flat = str(out).lower()
    for term in banned:
        assert term not in flat


def test_compute_correlation_portfolio_level() -> None:
    up = [100.0 + i for i in range(10)]
    out = compute_correlation(
        {
            "A": bars_from_closes(up, symbol="A"),
            "B": bars_from_closes(up, symbol="B"),
        }
    )
    assert out["status"] == "ok"
    assert out["symbols"] == ["A", "B"]

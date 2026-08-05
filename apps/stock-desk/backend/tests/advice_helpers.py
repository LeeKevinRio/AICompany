"""Builders for advice tests: hand-made signal blocks and rule files.

``make_signals`` produces the exact shape ``compute_signals`` emits (indicator
dicts with ``status``/``last``) but lets a test set only the values a rule
needs, so a rule can be driven to a precise state without reverse-engineering a
price series. ``test_advice_engine`` additionally pins the real
``compute_signals`` output against this shape so the fake cannot drift.
"""

from __future__ import annotations

from datetime import date, timedelta
from pathlib import Path
from typing import Any

import yaml

from app.advice.limits import SelfReportedNetWorth

_AS_OF = "2026-07-24T13:30:00+00:00"
_BAR_COUNT = 120
_LAST_BAR = date(2026, 7, 24)

#: The aligned date index the real indicators publish. An indicator that
#: reported ``insufficient_data`` publishes an empty one, as it does in
#: ``app/signals/technical.py``.
_DATES = [
    (_LAST_BAR - timedelta(days=_BAR_COUNT - 1 - i)).isoformat() for i in range(_BAR_COUNT)
]


def _indicator(name: str, last: dict[str, float | None] | None) -> dict[str, Any]:
    """One indicator block; ``None`` means the indicator had too little data."""
    return {
        "name": name,
        "status": "insufficient_data" if last is None else "ok",
        "params": {},
        "dates": [] if last is None else list(_DATES),
        "series": {},
        "last": {} if last is None else last,
        "inputs_used": {"columns": [], "window": {}, "description": "test fixture"},
        "as_of": _AS_OF,
        "source": "twse",
    }


def make_signals(
    *,
    ma: dict[str, float | None] | None = None,
    rsi: float | None = None,
    macd: dict[str, float | None] | None = None,
    bollinger: dict[str, float | None] | None = None,
    atr: float | None = None,
    kd: dict[str, float | None] | None = None,
    volume_z: float | None = None,
    volatility: float | None = None,
    max_drawdown: float | None = None,
    beta: float | None = None,
    symbol: str = "2330",
    as_of: str | None = _AS_OF,
) -> dict[str, Any]:
    """A ``compute_signals``-shaped dict; every argument left out is missing."""
    return {
        "symbol": symbol,
        "bar_count": _BAR_COUNT,
        "as_of": as_of,
        "source": "twse",
        "technical": {
            "moving_averages": _indicator("moving_averages", ma),
            "rsi": _indicator("rsi", None if rsi is None else {"rsi": rsi}),
            "macd": _indicator("macd", macd),
            "bollinger": _indicator("bollinger", bollinger),
            "atr": _indicator("atr", None if atr is None else {"atr": atr}),
            "kd": _indicator("kd", kd),
            "volume_zscore": _indicator(
                "volume_zscore", None if volume_z is None else {"zscore": volume_z}
            ),
        },
        "risk": {
            "volatility": {
                "status": "insufficient_data" if volatility is None else "ok",
                "annualized_volatility": volatility,
                "daily_volatility": None,
                "observations": 0,
                "inputs_used": {"columns": [], "window": {}, "description": "test fixture"},
                "as_of": as_of,
                "source": "twse",
            },
            "drawdown": {
                "status": "insufficient_data" if max_drawdown is None else "ok",
                "max_drawdown": max_drawdown,
                "peak_date": None,
                "trough_date": None,
                "observations": 0,
                "inputs_used": {"columns": [], "window": {}, "description": "test fixture"},
                "as_of": as_of,
                "source": "twse",
            },
            "beta": {
                "status": "insufficient_data" if beta is None else "ok",
                "beta": beta,
                "observations": 0,
                "benchmark": None,
                "inputs_used": {"columns": [], "window": {}, "description": "test fixture"},
                "as_of": as_of,
                "source": "twse",
            },
        },
    }


def uptrend_signals(**overrides: Any) -> dict[str, Any]:
    """A quiet up-trend: MA stack bullish, nothing extreme anywhere else."""
    defaults: dict[str, Any] = {
        "ma": {"ma_5": 108.0, "ma_20": 105.0, "ma_60": 100.0},
        "rsi": 55.0,
        "macd": {"macd": 1.0, "signal": 0.8, "histogram": 0.2},
        "bollinger": {
            "middle": 105.0,
            "upper": 115.0,
            "lower": 95.0,
            "bandwidth": 0.19,
            "percent_b": 0.7,
        },
        "atr": 2.0,
        "kd": {"k": 60.0, "d": 55.0, "rsv": 60.0},
        "volume_z": 0.5,
        "volatility": 0.25,
        "max_drawdown": -0.05,
        "beta": 1.1,
    }
    defaults.update(overrides)
    return make_signals(**defaults)


def write_rule_file(tmp_path: Path, payload: object, *, name: str = "custom.yaml") -> Path:
    """Dump ``payload`` as YAML into ``tmp_path`` and return the file path."""
    path = tmp_path / name
    path.write_text(
        yaml.safe_dump(payload, allow_unicode=True, sort_keys=False), encoding="utf-8"
    )
    return path


def minimal_rule(**overrides: Any) -> dict[str, Any]:
    """A single valid rule mapping, ready to be mutated into an invalid one."""
    rule: dict[str, Any] = {
        "id": "sample_rule",
        "name": "測試規則",
        "action": "hold",
        "weight": 0.4,
        "condition": {"field": "rsi14.last", "op": "gt", "value": 70},
        "explanation": "測試用的說明。",
        "counterargument": "測試用的反方論點。",
        "invalidation": "測試用的失效條件。",
    }
    rule.update(overrides)
    return rule


def reported_net_worth(
    amount_twd: float = 1_000_000.0, *, age_days: int = 0
) -> SelfReportedNetWorth:
    """A self-reported net worth for the gross-exposure cap (FR-9).

    Fresh by default; ``age_days`` drives the freshness rule directly, which is
    what lets a test cross the 7- and 30-day boundaries without a fake clock.
    """
    return SelfReportedNetWorth(
        amount_twd=amount_twd,
        reported_at=(_LAST_BAR - timedelta(days=age_days)).isoformat(),
        age_days=age_days,
    )


def minimal_ruleset(*rules: dict[str, Any]) -> dict[str, Any]:
    """A rule file mapping wrapping ``rules`` (defaults to one valid rule)."""
    return {
        "version": "1.0.0",
        "updated_at": "2026-07-25",
        "rules": list(rules) or [minimal_rule()],
    }

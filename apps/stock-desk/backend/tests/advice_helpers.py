"""Builders for advice tests: hand-made signal blocks and rule files.

``make_signals`` produces the exact shape ``compute_signals`` emits (indicator
dicts with ``status``/``last``) but lets a test set only the values a rule
needs, so a rule can be driven to a precise state without reverse-engineering a
price series. ``test_advice_engine`` additionally pins the real
``compute_signals`` output against this shape so the fake cannot drift.
"""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from pathlib import Path
from typing import Any

import yaml

from app.advice.limits import KellyInputs, KellyInputSource, SelfReportedNetWorth
from app.data.interface import DataStatus
from app.portfolio.summary import PortfolioSummary, SummaryPosition, Totals
from app.portfolio.valuation import PriceInfo, Valuation

_AS_OF = "2026-07-24T13:30:00+00:00"
_BAR_COUNT = 120
_LAST_BAR = date(2026, 7, 24)
#: The shape the settings store actually writes: an aware UTC timestamp, not a
#: bare date, so the disclosure formatting is exercised on a realistic value.
_REPORTED_AT = datetime(2026, 7, 24, 15, 51, 56, 15754, tzinfo=UTC)
#: The Kelly ageing anchor as cap 5 receives it: a plain calendar day (6-A),
#: never an ISO datetime.
_KELLY_ANCHOR = "2026-07-24"

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
        reported_at=(_REPORTED_AT - timedelta(days=age_days)).isoformat(),
        age_days=age_days,
    )


def kelly_inputs(
    win_rate: float = 0.6,
    payoff_ratio: float = 2.0,
    *,
    source: KellyInputSource = "backtest",
    age_days: int | None = 0,
    anchored_at: str | None = _KELLY_ANCHOR,
    ci_includes_no_edge: bool = False,
    **overrides: Any,
) -> KellyInputs:
    """Cap 5's input, fresh and imported by default (the evaluable case).

    ``age_days`` drives the freshness rule directly, exactly as
    :func:`reported_net_worth` does for cap 3, so a test crosses the 30-day
    boundary without a fake clock. Passing ``age_days=None`` **and**
    ``anchored_at=None`` produces the unanchorable row (g-4) describes.
    """
    return KellyInputs(
        win_rate=win_rate,
        payoff_ratio=payoff_ratio,
        source=source,
        age_days=age_days,
        anchored_at=anchored_at,
        ci_includes_no_edge=ci_includes_no_edge,
        **overrides,
    )


def book_position(
    position_id: int,
    symbol: str,
    *,
    quantity: str = "1000",
    avg_cost: str = "500",
    price: str | None = "600",
    currency: str = "TWD",
    market: str = "TW",
    sector: str | None = None,
    fx_to_twd: str = "1",
) -> SummaryPosition:
    """One valued (or deliberately unvalued) row of a book.

    ``price=None`` produces the ``insufficient_data`` valuation the book layer
    has to leave out of every total -- the state the book-level caps must not
    read as a zero-weight holding.
    """
    valuation = (
        Valuation(
            status="insufficient_data",
            missing=["price"],
            price=None,
            pnl_original=None,
            pnl_twd=None,
            asset_contribution_twd=None,
            fx_contribution_twd=None,
        )
        if price is None
        else Valuation(
            status="ok",
            missing=[],
            price=PriceInfo(
                value=Decimal(price),
                as_of="2026-07-24",
                source="fake",
                data_status=DataStatus.FRESH,
            ),
            pnl_original=None,
            pnl_twd=Decimal(0),
            asset_contribution_twd=Decimal(0),
            fx_contribution_twd=Decimal(0),
        )
    )
    rate = Decimal(fx_to_twd)
    value = None if price is None else Decimal(quantity) * Decimal(price) * rate
    cost = None if price is None else Decimal(quantity) * Decimal(avg_cost) * rate
    return SummaryPosition(
        id=position_id,
        symbol=symbol,
        market=market,  # type: ignore[arg-type]
        quantity=Decimal(quantity),
        avg_cost=Decimal(avg_cost),
        currency=currency,  # type: ignore[arg-type]
        instrument_type="stock",
        opened_at="2024-01-02",
        sector=sector,
        note=None,
        valuation=valuation,
        market_value_twd=value,
        cost_twd=cost,
    )


def book_summary(*positions: SummaryPosition) -> PortfolioSummary:
    """A summary whose ``totals`` are summed from its own ``ok`` rows.

    The book-level caps read ``totals.market_value_twd`` as total equity, so a
    fixture with hand-written totals would test the caps against a book that
    does not exist. Here the totals are always the sum of the rows above them,
    exactly as :func:`app.portfolio.summary.build_summary` produces them.
    """
    valued = [p for p in positions if p.valuation.status == "ok"]
    market_value = sum((p.market_value_twd or Decimal(0) for p in valued), Decimal(0))
    cost = sum((p.cost_twd or Decimal(0) for p in valued), Decimal(0))
    return PortfolioSummary(
        as_of="2026-07-25T00:00:00+00:00",
        totals=Totals(
            cost_twd=cost,
            market_value_twd=market_value,
            unrealized_pnl_twd=market_value - cost,
            asset_contribution_twd=Decimal(0),
            fx_contribution_twd=Decimal(0),
            status=(
                "no_data"
                if not valued
                else "complete"
                if len(valued) == len(positions)
                else "partial"
            ),
        ),
        positions=list(positions),
    )


def minimal_ruleset(*rules: dict[str, Any]) -> dict[str, Any]:
    """A rule file mapping wrapping ``rules`` (defaults to one valid rule)."""
    return {
        "version": "1.0.0",
        "updated_at": "2026-07-25",
        "rules": list(rules) or [minimal_rule()],
    }

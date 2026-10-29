"""Cap 1's default is 0.10 since 2026-10-26 (CEO #61/#62, plan A).

Pins the new default and the cases at its edge (quant constraint 6: exactly
10% is ``violated``, 9.99% is ``passed``, and the add range's upper edge is
the 10% headroom), and cross-checks the settings page's displayed default
against the model (constraint 2) by reading the form's source.

What did *not* move is pinned too: the 0.50 hard ceiling (risk review point
5) and the Kelly fields that cap 5 still reads until batch two (constraint 5).
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from app.advice.limits import (
    DEFAULT_MAX_POSITION_WEIGHT,
    MAX_POSITION_WEIGHT_CEILING,
    PREVIOUS_DEFAULT_MAX_POSITION_WEIGHT,
    PortfolioContext,
    RiskBudget,
    evaluate_limits,
    suggest_quantity_range,
)
from tests.advice_helpers import reported_net_worth

_SETTINGS_FORM = (
    Path(__file__).resolve().parents[2] / "frontend" / "app" / "settings" / "SettingsForm.tsx"
)


def _ctx(**overrides: Any) -> PortfolioContext:
    """The same fully populated context ``tests/test_advice_limits.py`` uses."""
    base: dict[str, Any] = {
        "symbol": "2330",
        "total_equity_twd": 1_000_000.0,
        "position_market_value_twd": 50_000.0,
        "position_cost_twd": 40_000.0,
        "gross_exposure_twd": 500_000.0,
        "net_worth": reported_net_worth(1_000_000.0),
        "book_fully_valued": True,
        "quantity": 500.0,
        "close": 100.0,
        "atr": 2.0,
    }
    base.update(overrides)
    return PortfolioContext(**base)


def _cap1(position_value: float, budget: RiskBudget | None = None) -> str:
    checks = evaluate_limits(
        budget if budget is not None else RiskBudget(),
        _ctx(position_market_value_twd=position_value),
    )
    (check,) = [c for c in checks if c.id == "single_position_weight"]
    return check.status


def test_the_default_is_ten_percent() -> None:
    assert DEFAULT_MAX_POSITION_WEIGHT == 0.10
    assert RiskBudget().max_position_weight == 0.10
    assert PREVIOUS_DEFAULT_MAX_POSITION_WEIGHT == 0.15


def test_the_hard_ceiling_did_not_move() -> None:
    assert MAX_POSITION_WEIGHT_CEILING == 0.50


def test_the_kelly_fields_are_still_on_the_budget() -> None:
    """Constraint 5: batch two must not drop them (``extra="forbid"``)."""
    budget = RiskBudget()
    assert budget.kelly_fraction_cap == 0.25
    assert budget.kelly_position_cap == 0.10


def test_exactly_ten_percent_is_violated() -> None:
    assert _cap1(100_000.0) == "violated"


def test_just_under_ten_percent_is_passed() -> None:
    assert _cap1(99_900.0) == "passed"


def test_twelve_percent_now_violates_what_used_to_pass() -> None:
    assert _cap1(120_000.0) == "violated"
    assert _cap1(120_000.0, RiskBudget(max_position_weight=0.15)) == "passed"


def test_the_add_range_upper_edge_is_the_ten_percent_headroom() -> None:
    """The book grows by what is bought (no cash leg), so the cap grows with it.

    (50,000 + 100x) / (1,000,000 + 100x) < 10% gives x < 555.56: 555 shares sit
    at 9.995%, 556 reach 10.004%, which counts as breached. Under the old 15%
    default the same context allowed 1,176 (``test_advice_limits.py``).
    """
    quantity = suggest_quantity_range(RiskBudget(), _ctx(), action="add")
    assert quantity is not None
    assert quantity.max_shares == 555
    assert quantity.min_shares == 277
    assert "單一標的佔比上限" in quantity.basis


def test_the_reduce_range_sells_down_to_ten_percent() -> None:
    """(200,000 - 100x) / (1,000,000 - 100x) < 10% gives x > 1,111.1."""
    ctx = _ctx(position_market_value_twd=200_000.0, quantity=2_000.0)
    quantity = suggest_quantity_range(RiskBudget(), ctx, action="reduce")
    assert quantity is not None
    assert quantity.min_shares == 1_112
    assert quantity.max_shares == 2_000


def test_a_holding_between_ten_and_fifteen_percent_gets_no_add_range() -> None:
    ctx = _ctx(position_market_value_twd=120_000.0, quantity=1_200.0)
    assert suggest_quantity_range(RiskBudget(), ctx, action="add") is None


def test_the_settings_page_shows_the_same_default() -> None:
    """Constraint 2: the form's printed "預設值" is the model's default."""
    source = _SETTINGS_FORM.read_text(encoding="utf-8")
    block = re.search(
        r'key: "max_position_weight",.*?defaultValue: ([0-9.]+),', source, flags=re.DOTALL
    )
    assert block is not None
    assert float(block.group(1)) == RiskBudget().max_position_weight

"""Tests for the risk budget: every cap, in all three states, plus sizing."""

from __future__ import annotations

from typing import Any

import pytest

from app.advice.limits import (
    LIMIT_IDS,
    LIMIT_NAMES,
    LimitCheck,
    PortfolioContext,
    RiskBudget,
    atr_max_shares,
    evaluate_limits,
    kelly_allowed_weight,
    kelly_fraction,
    limit_status_after,
    notional_caps,
    project_position,
    suggest_quantity_range,
)

BUDGET = RiskBudget()


def _ctx(**overrides: Any) -> PortfolioContext:
    """A fully populated context; override one field per test."""
    base: dict[str, Any] = {
        "symbol": "2330",
        "total_equity_twd": 1_000_000.0,
        "position_market_value_twd": 50_000.0,
        "position_cost_twd": 40_000.0,
        "gross_exposure_twd": 500_000.0,
        "quantity": 500.0,
        "close": 100.0,
        "atr": 2.0,
    }
    base.update(overrides)
    return PortfolioContext(**base)


def _check(ctx: PortfolioContext, limit_id: str, budget: RiskBudget = BUDGET) -> LimitCheck:
    checks = {check.id: check for check in evaluate_limits(budget, ctx)}
    return checks[limit_id]


def _status(ctx: PortfolioContext, limit_id: str, budget: RiskBudget = BUDGET) -> str:
    return _check(ctx, limit_id, budget).status


# --- Defaults and ordering ---------------------------------------------------


def test_default_budget_is_conservative() -> None:
    assert BUDGET.max_position_weight == 0.15
    assert BUDGET.max_sector_weight == 0.30
    assert BUDGET.max_gross_exposure == 1.00
    assert BUDGET.max_loss_per_trade == 0.01
    assert BUDGET.atr_stop_multiple == 2.0
    assert BUDGET.kelly_fraction_cap == 0.25
    assert BUDGET.kelly_position_cap == 0.10


def test_kelly_fraction_cap_cannot_exceed_a_quarter() -> None:
    with pytest.raises(ValueError):
        RiskBudget(kelly_fraction_cap=0.5)
    with pytest.raises(ValueError):
        RiskBudget(kelly_position_cap=0.2)


def test_every_limit_is_reported_once_in_order() -> None:
    checks = evaluate_limits(BUDGET, _ctx())
    assert [check.id for check in checks] == list(LIMIT_IDS)
    assert [check.index for check in checks] == [1, 2, 3, 4, 5]
    assert [check.name for check in checks] == [LIMIT_NAMES[i] for i in LIMIT_IDS]


# --- 1. Single position weight ----------------------------------------------


def test_single_position_weight_passed() -> None:
    assert _status(_ctx(position_market_value_twd=50_000.0), "single_position_weight") == "passed"


def test_single_position_weight_violated_at_the_cap() -> None:
    # Exactly at 15%: the budget is spent, so there is no room left to add.
    check = _check(_ctx(position_market_value_twd=150_000.0), "single_position_weight")
    assert check.status == "violated"
    assert check.observed == pytest.approx(0.15)
    assert check.threshold == 0.15


def test_single_position_weight_violated_above_the_cap() -> None:
    ctx = _ctx(position_market_value_twd=200_000.0)
    assert _status(ctx, "single_position_weight") == "violated"


def test_single_position_weight_not_evaluable_without_equity() -> None:
    assert _status(_ctx(total_equity_twd=None), "single_position_weight") == "not_evaluable"


# --- 2. Sector weight (no sector field on positions yet) --------------------


def test_sector_weight_not_evaluable_without_sector_data() -> None:
    check = _check(_ctx(), "sector_weight")
    assert check.status == "not_evaluable"
    assert "產業別" in check.detail
    assert check.observed is None


def test_sector_weight_passed_when_the_caller_supplies_sector_data() -> None:
    ctx = _ctx(sector="半導體", sector_market_value_twd=200_000.0)
    assert _status(ctx, "sector_weight") == "passed"


def test_sector_weight_violated_when_the_sector_is_over_the_cap() -> None:
    ctx = _ctx(sector="半導體", sector_market_value_twd=350_000.0)
    check = _check(ctx, "sector_weight")
    assert check.status == "violated"
    assert check.observed == pytest.approx(0.35)


def test_sector_weight_not_evaluable_without_equity() -> None:
    ctx = _ctx(sector="半導體", sector_market_value_twd=200_000.0, total_equity_twd=None)
    assert _status(ctx, "sector_weight") == "not_evaluable"


# --- 3. Gross exposure ------------------------------------------------------


def test_gross_exposure_passed() -> None:
    assert _status(_ctx(gross_exposure_twd=600_000.0), "gross_exposure") == "passed"


def test_gross_exposure_violated_at_full_investment() -> None:
    check = _check(_ctx(gross_exposure_twd=1_000_000.0), "gross_exposure")
    assert check.status == "violated"
    assert check.observed == pytest.approx(1.0)


def test_gross_exposure_not_evaluable_without_book_value() -> None:
    assert _status(_ctx(gross_exposure_twd=None), "gross_exposure") == "not_evaluable"


# --- 4. Per-trade loss, derived from ATR ------------------------------------


def test_per_trade_loss_passed_and_quotes_the_stop_basis() -> None:
    # 500 shares x 2 x ATR 2.0 = 2,000 TWD at risk = 0.2% of 1,000,000.
    check = _check(_ctx(), "per_trade_loss")
    assert check.status == "passed"
    assert check.observed == pytest.approx(0.002)
    assert "ATR(14)" in check.detail


def test_per_trade_loss_violated_when_the_stop_out_loss_is_too_large() -> None:
    # 3,000 shares x 4 TWD stop distance = 12,000 = 1.2% > 1%.
    check = _check(_ctx(quantity=3_000.0, position_market_value_twd=300_000.0), "per_trade_loss")
    assert check.status == "violated"
    assert check.observed == pytest.approx(0.012)


def test_per_trade_loss_not_evaluable_without_atr() -> None:
    assert _status(_ctx(atr=None), "per_trade_loss") == "not_evaluable"


def test_per_trade_loss_not_evaluable_with_zero_atr() -> None:
    assert _status(_ctx(atr=0.0), "per_trade_loss") == "not_evaluable"


def test_per_trade_loss_not_evaluable_without_a_share_count() -> None:
    ctx = _ctx(quantity=None, position_market_value_twd=None, close=None)
    assert _status(ctx, "per_trade_loss") == "not_evaluable"


def test_atr_max_shares_uses_the_stop_multiple() -> None:
    # 1% of 1,000,000 = 10,000 TWD risk; stop distance 2 x 2.0 = 4 TWD.
    assert atr_max_shares(BUDGET, _ctx()) == pytest.approx(2_500.0)
    assert atr_max_shares(BUDGET, _ctx(atr=None)) is None
    assert atr_max_shares(BUDGET, _ctx(atr=0.0)) is None
    assert atr_max_shares(BUDGET, _ctx(total_equity_twd=None)) is None


def test_atr_max_shares_converts_a_foreign_currency_stop() -> None:
    ctx = _ctx(close=20.0, atr=0.5, fx_to_twd=32.0)
    # Stop distance = 2 x 0.5 x 32 = 32 TWD; 10,000 / 32 = 312.5 shares.
    assert atr_max_shares(BUDGET, ctx) == pytest.approx(312.5)


# --- 5. Fractional Kelly ----------------------------------------------------


def test_kelly_fraction_matches_the_textbook_formula() -> None:
    # w = 0.6, b = 2  ->  0.6 - 0.4/2 = 0.4
    assert kelly_fraction(0.6, 2.0) == pytest.approx(0.4)
    assert kelly_fraction(0.4, 1.0) == pytest.approx(-0.2)
    assert kelly_fraction(1.5, 2.0) is None
    assert kelly_fraction(0.6, 0.0) is None


def test_kelly_allowed_weight_applies_the_quarter_and_the_hard_cap() -> None:
    # Quarter of 0.4 = 0.10, exactly at the hard cap.
    assert kelly_allowed_weight(BUDGET, _ctx(win_rate=0.6, payoff_ratio=2.0)) == pytest.approx(0.1)
    # A huge edge is still capped at 10%.
    assert kelly_allowed_weight(BUDGET, _ctx(win_rate=0.9, payoff_ratio=5.0)) == pytest.approx(0.1)
    # Quarter of 0.2 = 0.05, below the hard cap.
    assert kelly_allowed_weight(BUDGET, _ctx(win_rate=0.6, payoff_ratio=1.0)) == pytest.approx(0.05)
    # A negative edge allows nothing.
    assert kelly_allowed_weight(BUDGET, _ctx(win_rate=0.3, payoff_ratio=1.0)) == 0.0


def test_kelly_not_evaluable_without_win_rate_or_payoff() -> None:
    check = _check(_ctx(), "kelly_fraction")
    assert check.status == "not_evaluable"
    assert "勝率" in check.detail
    assert _status(_ctx(win_rate=0.6), "kelly_fraction") == "not_evaluable"
    assert _status(_ctx(payoff_ratio=2.0), "kelly_fraction") == "not_evaluable"


def test_kelly_passed_when_the_position_fits_the_edge() -> None:
    ctx = _ctx(win_rate=0.6, payoff_ratio=2.0, position_market_value_twd=50_000.0)
    check = _check(ctx, "kelly_fraction")
    assert check.status == "passed"
    assert check.threshold == pytest.approx(0.1)


def test_kelly_violated_when_the_position_exceeds_the_edge() -> None:
    ctx = _ctx(win_rate=0.6, payoff_ratio=1.0, position_market_value_twd=80_000.0)
    check = _check(ctx, "kelly_fraction")
    assert check.status == "violated"
    assert check.observed == pytest.approx(0.08)
    assert check.threshold == pytest.approx(0.05)


def test_kelly_not_evaluable_without_position_weight() -> None:
    ctx = _ctx(win_rate=0.6, payoff_ratio=2.0, position_market_value_twd=None)
    assert _status(ctx, "kelly_fraction") == "not_evaluable"


# --- Notional caps and quantity ranges --------------------------------------


def test_notional_caps_skip_the_caps_they_cannot_evaluate() -> None:
    caps = notional_caps(BUDGET, _ctx())
    assert set(caps) == {"single_position_weight", "gross_exposure", "per_trade_loss"}
    assert caps["single_position_weight"] == pytest.approx(150_000.0)
    # Gross: 1,000,000 cap less the other 450,000 already invested.
    assert caps["gross_exposure"] == pytest.approx(550_000.0)
    # ATR: 2,500 shares x 100 TWD.
    assert caps["per_trade_loss"] == pytest.approx(250_000.0)


def test_notional_caps_are_empty_without_equity() -> None:
    assert notional_caps(BUDGET, _ctx(total_equity_twd=None)) == {}


def test_notional_caps_include_sector_and_kelly_when_available() -> None:
    ctx = _ctx(sector="半導體", sector_market_value_twd=200_000.0, win_rate=0.6, payoff_ratio=2.0)
    caps = notional_caps(BUDGET, ctx)
    # Sector: 300,000 cap less the 150,000 held by other names in the sector.
    assert caps["sector_weight"] == pytest.approx(150_000.0)
    assert caps["kelly_fraction"] == pytest.approx(100_000.0)


def test_add_range_is_derived_from_the_tightest_cap() -> None:
    quantity = suggest_quantity_range(BUDGET, _ctx(), action="add")
    assert quantity is not None
    # Binding cap 150,000 less 50,000 held = 100,000 / 100 TWD = 1,000 shares --
    # but 1,000 lands exactly on the cap, which counts as breached, so the
    # suggestion stops one share short.
    assert quantity.max_shares == 999
    assert quantity.min_shares == 499
    assert "單一標的佔比上限" in quantity.basis
    assert "未納入計算的上限" in quantity.basis


def test_add_range_is_none_when_the_budget_is_spent() -> None:
    ctx = _ctx(position_market_value_twd=150_000.0, quantity=1_500.0)
    assert suggest_quantity_range(BUDGET, ctx, action="add") is None


def test_add_range_is_none_without_a_price() -> None:
    assert suggest_quantity_range(BUDGET, _ctx(close=None), action="add") is None


def test_add_range_is_none_without_any_evaluable_cap() -> None:
    ctx = _ctx(total_equity_twd=None)
    assert suggest_quantity_range(BUDGET, ctx, action="add") is None


def test_reduce_range_covers_the_excess_up_to_the_whole_holding() -> None:
    ctx = _ctx(position_market_value_twd=200_000.0, quantity=2_000.0)
    quantity = suggest_quantity_range(BUDGET, ctx, action="reduce")
    assert quantity is not None
    # 200,000 held vs a 150,000 cap: 500 shares above the cap, plus one more so
    # the remaining position sits strictly inside the cap rather than on it.
    assert quantity.min_shares == 501
    assert quantity.max_shares == 2_000
    assert "單一標的佔比上限" in quantity.basis


def test_acting_on_the_suggested_add_leaves_the_cap_passing() -> None:
    # The whole point of a suggested quantity: buying it must not put the book
    # into the state the same cap would report as violated.
    ctx = _ctx()
    quantity = suggest_quantity_range(BUDGET, ctx, action="add")
    assert quantity is not None
    for shares in (quantity.min_shares, quantity.max_shares):
        after = project_position(ctx, share_delta=float(shares))
        assert _status(after, "single_position_weight") == "passed"
        assert evaluate_limits(BUDGET, after) == evaluate_limits(BUDGET, after)
        assert not [check for check in evaluate_limits(BUDGET, after) if check.status == "violated"]
    # One share past the upper edge is exactly what the cap rejects.
    over = project_position(ctx, share_delta=float(quantity.max_shares + 1))
    assert _status(over, "single_position_weight") == "violated"


def test_acting_on_the_suggested_reduction_leaves_the_cap_passing() -> None:
    ctx = _ctx(position_market_value_twd=200_000.0, quantity=2_000.0)
    assert _status(ctx, "single_position_weight") == "violated"
    quantity = suggest_quantity_range(BUDGET, ctx, action="reduce")
    assert quantity is not None
    for shares in (quantity.min_shares, quantity.max_shares):
        after = project_position(ctx, share_delta=-float(shares))
        assert _status(after, "single_position_weight") == "passed"
    # One share short of the lower edge still leaves the cap breached.
    under = project_position(ctx, share_delta=-float(quantity.min_shares - 1))
    assert _status(under, "single_position_weight") == "violated"


def test_add_sizing_respects_a_binding_per_trade_loss_cap() -> None:
    # ATR 8 makes the stop distance 16 TWD, so the per-trade cap (625 shares
    # x 100 TWD = 62,500) binds well before the 15% position cap.
    ctx = _ctx(atr=8.0, position_market_value_twd=0.0, quantity=0.0)
    quantity = suggest_quantity_range(BUDGET, ctx, action="add")
    assert quantity is not None
    assert quantity.max_shares == 624
    after = project_position(ctx, share_delta=float(quantity.max_shares))
    assert _status(after, "per_trade_loss") == "passed"
    assert _status(project_position(ctx, share_delta=625.0), "per_trade_loss") == "violated"


def test_limit_status_after_projects_the_whole_book() -> None:
    ctx = _ctx(sector="半導體", sector_market_value_twd=200_000.0)
    after = project_position(ctx, share_delta=1_000.0)
    assert after.position_market_value_twd == pytest.approx(150_000.0)
    assert after.quantity == pytest.approx(1_500.0)
    assert after.gross_exposure_twd == pytest.approx(600_000.0)
    assert after.sector_market_value_twd == pytest.approx(300_000.0)
    # Equity is untouched: a market-price trade swaps cash for shares.
    assert after.total_equity_twd == ctx.total_equity_twd
    assert limit_status_after(
        BUDGET, ctx, limit_id="single_position_weight", share_delta=1_000.0
    ) == "violated"


def test_selling_everything_is_the_floor_when_nothing_else_clears_the_cap() -> None:
    # Gross exposure is over the cap because of *other* holdings, so no partial
    # sale of this name fixes it; the suggestion stops at the whole holding.
    ctx = _ctx(position_market_value_twd=50_000.0, quantity=500.0, gross_exposure_twd=2_000_000.0)
    quantity = suggest_quantity_range(BUDGET, ctx, action="reduce")
    assert quantity is not None
    assert quantity.min_shares == 500
    assert quantity.max_shares == 500


def test_reduce_range_is_none_for_a_compliant_position() -> None:
    assert suggest_quantity_range(BUDGET, _ctx(), action="reduce") is None


def test_hold_and_unknown_actions_get_no_range() -> None:
    over = _ctx(position_market_value_twd=200_000.0, quantity=2_000.0)
    assert suggest_quantity_range(BUDGET, over, action="hold") is None
    assert suggest_quantity_range(BUDGET, over, action="insufficient_data") is None


def test_stop_loss_and_take_profit_share_the_reduce_sizing() -> None:
    ctx = _ctx(position_market_value_twd=200_000.0, quantity=2_000.0)
    for action in ("stop_loss", "take_profit"):
        quantity = suggest_quantity_range(BUDGET, ctx, action=action)
        assert quantity is not None
        assert quantity.min_shares == 501


# --- Context helpers ---------------------------------------------------------


def test_position_weight_and_pnl_helpers() -> None:
    ctx = _ctx()
    assert ctx.position_weight() == pytest.approx(0.05)
    assert ctx.unrealized_pnl_pct() == pytest.approx(0.25)
    assert ctx.price_twd() == pytest.approx(100.0)
    assert ctx.held_shares() == pytest.approx(500.0)


def test_helpers_return_none_on_missing_inputs() -> None:
    assert _ctx(total_equity_twd=0.0).position_weight() is None
    assert _ctx(position_cost_twd=None).unrealized_pnl_pct() is None
    assert _ctx(position_cost_twd=0.0).unrealized_pnl_pct() is None
    assert _ctx(close=None).price_twd() is None
    assert _ctx(quantity=None, close=None).held_shares() is None
    assert _ctx(quantity=None).held_shares() == pytest.approx(500.0)
    assert _ctx(position_market_value_twd=None).unrealized_pnl_pct() is None

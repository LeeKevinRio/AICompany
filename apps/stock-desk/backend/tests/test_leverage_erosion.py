"""Flat-index erosion scenario: golden formula values and refusal to guess."""

from __future__ import annotations

import math

from app.leverage import erosion as E
from tests.leverage_helpers import bars, zigzag_closes

TOL = 1e-12


# --- Pure formula (hand-computed) --------------------------------------------


def test_erosion_at_horizon_golden() -> None:
    # beta=2, sigma=0.20, T=1:
    #   drag_log = -0.5*2*1*0.04*1 = -0.04 -> exp(-0.04)-1 = -0.03921056084767634
    #   fee_log  = -0.01                    -> exp(-0.01)-1 = -0.009950166250831947
    #   total    = exp(-0.05)-1             = -0.04877057549928599
    drag, fee, total = E.erosion_at_horizon(
        leverage_factor=2.0,
        expense_ratio_annual=0.01,
        annualized_sigma=0.20,
        horizon_years=1.0,
    )
    assert math.isclose(drag, -0.03921056084767634, rel_tol=1e-12)
    assert math.isclose(fee, -0.009950166250831947, rel_tol=1e-12)
    assert math.isclose(total, -0.04877057549928599, rel_tol=1e-12)
    # Log-space terms compound; they do not add up arithmetically.
    assert total != drag + fee


def test_inverse_one_x_has_the_same_drag_as_two_x() -> None:
    # -0.5*b*(b-1) is 1 for both b=2 and b=-1, a fact worth pinning.
    two_x = E.erosion_at_horizon(
        leverage_factor=2.0, expense_ratio_annual=0.0, annualized_sigma=0.3, horizon_years=1.0
    )
    inverse = E.erosion_at_horizon(
        leverage_factor=-1.0, expense_ratio_annual=0.0, annualized_sigma=0.3, horizon_years=1.0
    )
    assert math.isclose(two_x[0], inverse[0], rel_tol=1e-12)


def test_unleveraged_fund_has_only_the_fee_term() -> None:
    drag, fee, total = E.erosion_at_horizon(
        leverage_factor=1.0, expense_ratio_annual=0.005, annualized_sigma=0.9, horizon_years=1.0
    )
    assert drag == 0.0
    assert math.isclose(total, fee, rel_tol=1e-12)


# --- Bar-level estimate ------------------------------------------------------


def _estimate(
    *,
    window: int = E.DEFAULT_WINDOW,
    min_observations: int = E.DEFAULT_MIN_OBSERVATIONS,
    leverage_factor: float = 2.0,
    expense_ratio_annual: float = 0.0113,
) -> E.ErosionEstimate:
    index_closes = zigzag_closes(amplitude=0.02, returns=60)
    return E.estimate_erosion(
        index_bars=bars(index_closes, symbol="TW50", source="twse-index"),
        leverage_factor=leverage_factor,
        expense_ratio_annual=expense_ratio_annual,
        window=window,
        min_observations=min_observations,
    )


def test_estimate_reports_both_horizons_and_is_internally_consistent() -> None:
    result = _estimate()
    assert result.status == "ok"
    assert result.observations == 60
    assert result.annualized_volatility is not None
    assert math.isclose(result.annualized_volatility, 0.3170305305189048, rel_tol=1e-9)
    labels = [s.label for s in result.scenarios]
    assert labels == ["1_month", "1_year"]

    monthly, annual = result.scenarios
    assert monthly.horizon_trading_days == 21
    assert annual.horizon_trading_days == 252
    # Longer horizon erodes more; both are losses under a flat index.
    assert annual.total_expected_erosion_pct < monthly.total_expected_erosion_pct < 0.0
    for scenario in result.scenarios:
        expected = E.erosion_at_horizon(
            leverage_factor=2.0,
            expense_ratio_annual=0.0113,
            annualized_sigma=result.annualized_volatility,
            horizon_years=scenario.horizon_years,
        )
        assert math.isclose(scenario.volatility_drag_pct, expected[0], rel_tol=1e-12)
        assert math.isclose(scenario.expense_pct, expected[1], rel_tol=1e-12)
        assert math.isclose(scenario.total_expected_erosion_pct, expected[2], rel_tol=1e-12)


def test_estimate_is_labelled_a_scenario_not_a_forecast() -> None:
    result = _estimate()
    assert "非預測" in result.nature
    assert any("不是預測" in a for a in result.assumptions)
    assert any("橫盤" in a or "期望報酬 0" in a for a in result.assumptions)
    assert len(result.assumptions) >= 5


def test_window_limits_the_returns_used() -> None:
    result = _estimate(window=30, min_observations=10)
    assert result.status == "ok"
    assert result.window == 30
    assert result.observations == 30


def test_provenance_is_carried_through() -> None:
    result = _estimate()
    assert result.source == "twse-index"
    assert result.as_of is not None
    assert result.inputs_used.columns == ["close"]
    assert result.inputs_used.window["lookback_returns"] == 60


# --- insufficient_data paths -------------------------------------------------


def test_too_few_observations_is_insufficient_data() -> None:
    index_closes = zigzag_closes(amplitude=0.02, returns=5)
    result = E.estimate_erosion(
        index_bars=bars(index_closes, symbol="TW50"),
        leverage_factor=2.0,
        expense_ratio_annual=0.0113,
    )
    assert result.status == "insufficient_data"
    assert result.scenarios == []
    assert result.annualized_volatility is None
    assert result.observations == 5
    assert result.reason is not None


def test_no_bars_is_insufficient_data() -> None:
    result = E.estimate_erosion(
        index_bars=[], leverage_factor=2.0, expense_ratio_annual=0.0113
    )
    assert result.status == "insufficient_data"
    assert result.reason is not None
    assert result.as_of is None


def test_degenerate_window_is_insufficient_data() -> None:
    result = _estimate(window=1)
    assert result.status == "insufficient_data"
    assert result.reason is not None


def test_single_return_cannot_produce_a_sigma() -> None:
    result = E.estimate_erosion(
        index_bars=bars([100.0, 102.0], symbol="TW50"),
        leverage_factor=2.0,
        expense_ratio_annual=0.0113,
        window=2,
        min_observations=1,
    )
    assert result.status == "insufficient_data"
    assert result.annualized_volatility is None

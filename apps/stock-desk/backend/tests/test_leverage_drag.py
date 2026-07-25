"""Golden and behavioural tests for the drag decomposition.

The headline golden case is the textbook one, computed by hand below, and the
decomposition identity ``actual - naive == fee + reset + residual`` is asserted
on every ok result -- it is the property that makes the attribution auditable
rather than merely plausible.
"""

from __future__ import annotations

import math
from datetime import date

from app.leverage import drag as G
from tests.leverage_helpers import bars, ideal_leveraged_closes, zigzag_closes

TOL = 1e-12

# Hand-computed reference case
# ----------------------------
# index: 100 -> 110 -> 99          (+10%, then -10%)
# 2x fund tracking perfectly daily: 100 -> 120 -> 96   (+20%, then -20%)
#   R_idx  = 99/100 - 1            = -0.01
#   R_etf  = 96/100 - 1            = -0.04
#   naive  = 2 * -0.01             = -0.02
#   ideal  = 1.2 * 0.8 - 1         = -0.04
#   gap    = -0.04 - (-0.02)       = -0.02
#   fee    = -0.01 * 2/252         = -7.936507936507937e-05
#   reset  = -0.04 - (-0.02)       = -0.02
#   resid  = gap - fee - reset     = +7.936507936507937e-05
# The residual is exactly +fee here because the *price series carries no fee*:
# the linear fee term subtracts a cost the synthetic fund never paid, and the
# residual honestly hands it back instead of hiding the mismatch.
_INDEX_GOLDEN = [100.0, 110.0, 99.0]
_ETF_GOLDEN = [100.0, 120.0, 96.0]
_BETA = 2.0
_EXPENSE = 0.01


def _decompose(
    index_closes: list[float],
    etf_closes: list[float],
    *,
    leverage_factor: float = _BETA,
    expense_ratio_annual: float = _EXPENSE,
    opened_at: date | None = None,
) -> G.DragDecomposition:
    return G.decompose_drag(
        etf_bars=bars(etf_closes, symbol="00631L"),
        index_bars=bars(index_closes, symbol="TW50", source="twse-index"),
        leverage_factor=leverage_factor,
        expense_ratio_annual=expense_ratio_annual,
        opened_at=opened_at,
    )


def _assert_identity(result: G.DragDecomposition) -> None:
    assert result.gap is not None
    assert result.fee_effect is not None
    assert result.reset_effect is not None
    assert result.residual is not None
    assert result.actual_return is not None
    assert result.naive_expected_return is not None
    assert math.isclose(
        result.actual_return - result.naive_expected_return,
        result.fee_effect + result.reset_effect + result.residual,
        abs_tol=1e-15,
    )
    assert result.identity_abs_error is not None
    assert result.identity_abs_error < 1e-15


# --- Golden decomposition ----------------------------------------------------


def test_drag_golden_symmetric_up_down() -> None:
    result = _decompose(_INDEX_GOLDEN, _ETF_GOLDEN)
    assert result.status == "ok"
    assert result.window.trading_days == 2
    assert result.window.aligned_bars == 3
    assert math.isclose(result.index_return or 0.0, -0.01, abs_tol=TOL)
    assert math.isclose(result.actual_return or 0.0, -0.04, abs_tol=TOL)
    assert math.isclose(result.naive_expected_return or 0.0, -0.02, abs_tol=TOL)
    assert math.isclose(result.ideal_daily_reset_return or 0.0, -0.04, abs_tol=TOL)
    assert math.isclose(result.gap or 0.0, -0.02, abs_tol=TOL)
    assert math.isclose(result.fee_effect or 0.0, -7.936507936507937e-05, rel_tol=1e-12)
    assert math.isclose(result.reset_effect or 0.0, -0.02, abs_tol=TOL)
    assert math.isclose(result.residual or 0.0, 7.936507936507937e-05, rel_tol=1e-9)
    _assert_identity(result)


def test_drag_golden_with_fee_accrued_in_price_leaves_second_order_residual() -> None:
    # Same path, but the fund's NAV really pays 1%/252 per day. The linear fee
    # term is charged on the *initial* value while the real fee scales with the
    # (now smaller) NAV, so a small positive residual is expected -- and is
    # exactly the kind of approximation error this field exists to expose.
    etf_closes = ideal_leveraged_closes(
        _INDEX_GOLDEN, leverage_factor=_BETA, expense_ratio_annual=_EXPENSE
    )
    result = _decompose(_INDEX_GOLDEN, etf_closes)
    assert result.status == "ok"
    assert math.isclose(result.actual_return or 0.0, -0.040076188964474735, rel_tol=1e-12)
    assert math.isclose(result.gap or 0.0, -0.020076188964474717, rel_tol=1e-12)
    assert math.isclose(result.fee_effect or 0.0, -7.936507936507937e-05, rel_tol=1e-12)
    assert math.isclose(result.reset_effect or 0.0, -0.02, abs_tol=1e-12)
    assert result.residual is not None
    assert 0.0 < result.residual < 1e-5
    _assert_identity(result)


def test_inverse_fund_also_bleeds_in_a_round_trip() -> None:
    # -1x is not "the mirror image of the index over the period": a round trip
    # leaves it below the naive expectation too.
    etf_closes = ideal_leveraged_closes(_INDEX_GOLDEN, leverage_factor=-1.0)
    result = _decompose(_INDEX_GOLDEN, etf_closes, leverage_factor=-1.0)
    assert result.status == "ok"
    assert result.reset_effect is not None
    assert result.reset_effect < 0.0
    _assert_identity(result)


def test_ideal_daily_reset_path_pure_function() -> None:
    value, wiped = G.ideal_daily_reset_path([0.10, -0.10], 2.0)
    assert math.isclose(value, -0.04, abs_tol=TOL)
    assert wiped is False
    assert G.ideal_daily_reset_path([], 2.0) == (0.0, False)


def test_ideal_path_wipeout_is_floored_and_flagged() -> None:
    # A -60% index day annihilates a 2x fund; NAV floors at -100%, it does not
    # go negative, and the flag says so.
    value, wiped = G.ideal_daily_reset_path([-0.60, 0.50], 2.0)
    assert value == -1.0
    assert wiped is True
    index_closes = [100.0, 40.0, 60.0]
    etf_closes = [100.0, 1.0, 1.2]
    result = _decompose(index_closes, etf_closes)
    assert result.status == "ok"
    assert result.ideal_path_wiped_out is True
    _assert_identity(result)


# --- Theory vs measurement ---------------------------------------------------


def test_theory_and_measurement_agree_in_sign_and_magnitude_when_sideways() -> None:
    # 60 trading days of a +-2% sideways zigzag (annualized sigma ~ 0.317):
    # small daily moves, so the i.i.d./small-return approximation should land
    # close to the measured compounding effect.
    index_closes = zigzag_closes(amplitude=0.02, returns=60)
    for beta in (2.0, 3.0, -1.0):
        etf_closes = ideal_leveraged_closes(index_closes, leverage_factor=beta)
        result = _decompose(index_closes, etf_closes, leverage_factor=beta)
        assert result.status == "ok"
        theory = result.theoretical
        assert theory.status == "ok"
        assert theory.theoretical_drag is not None
        assert theory.measured_reset_effect is not None
        assert theory.theoretical_drag < 0.0
        assert theory.measured_reset_effect < 0.0
        assert math.isclose(
            theory.theoretical_drag, theory.measured_reset_effect, rel_tol=0.15
        )
        assert theory.difference is not None
        assert math.isclose(
            theory.difference,
            theory.theoretical_drag - theory.measured_reset_effect,
            abs_tol=1e-15,
        )


def test_theory_overstates_drag_at_large_beta_and_amplitude_and_we_show_it() -> None:
    # -3x through a +-5% zigzag: the small-return assumption breaks and the
    # closed form overshoots the measured effect by ~50%. Reported as-is, not
    # reconciled -- the disagreement is the information.
    index_closes = zigzag_closes(amplitude=0.05, returns=60)
    etf_closes = ideal_leveraged_closes(index_closes, leverage_factor=-3.0)
    result = _decompose(index_closes, etf_closes, leverage_factor=-3.0)
    theory = result.theoretical
    assert theory.theoretical_drag is not None
    assert theory.measured_reset_effect is not None
    assert theory.theoretical_drag < theory.measured_reset_effect < 0.0
    assert abs(theory.theoretical_drag / theory.measured_reset_effect) > 1.2


def test_theoretical_drag_pure_function_signs() -> None:
    # Negative for every leverage factor outside [0, 1] -- including inverse.
    assert G.theoretical_drag(leverage_factor=2.0, annualized_sigma=0.2, horizon_years=1.0) < 0
    assert G.theoretical_drag(leverage_factor=-1.0, annualized_sigma=0.2, horizon_years=1.0) < 0
    assert math.isclose(
        G.theoretical_drag(leverage_factor=2.0, annualized_sigma=0.2, horizon_years=1.0),
        -0.04,
        abs_tol=TOL,
    )
    # Unleveraged: no reset effect at all.
    assert G.theoretical_drag(leverage_factor=1.0, annualized_sigma=0.5, horizon_years=1.0) == 0.0


def test_small_sample_theory_is_reported_with_its_observation_count() -> None:
    # Two returns: ddof=1 sigma is wildly unstable (here it doubles the drag).
    # We do not suppress the number, but observations makes it auditable.
    result = _decompose(_INDEX_GOLDEN, _ETF_GOLDEN)
    theory = result.theoretical
    assert theory.status == "ok"
    assert theory.observations == 2
    assert theory.theoretical_drag is not None
    assert math.isclose(theory.theoretical_drag, -0.04, rel_tol=1e-9)


# --- Point-in-time and insufficient data -------------------------------------


def test_opened_at_truncates_the_window_to_the_holding_period() -> None:
    index_closes = zigzag_closes(amplitude=0.02, returns=20)
    etf_closes = ideal_leveraged_closes(index_closes, leverage_factor=2.0)
    full = _decompose(index_closes, etf_closes)
    late = _decompose(index_closes, etf_closes, opened_at=date(2024, 1, 11))
    assert full.window.aligned_bars == 21
    assert late.window.aligned_bars == 11
    assert late.window.start_date == "2024-01-11"
    assert late.window.opened_at == "2024-01-11"
    assert late.window.days_since_opened_at == 10
    assert late.window.trading_days == 10
    # Different window, genuinely different numbers -- not a relabelled total.
    assert late.reset_effect != full.reset_effect


def test_missing_index_bars_is_insufficient_data() -> None:
    result = G.decompose_drag(
        etf_bars=bars(_ETF_GOLDEN, symbol="00631L"),
        index_bars=[],
        leverage_factor=_BETA,
        expense_ratio_annual=_EXPENSE,
    )
    assert result.status == "insufficient_data"
    assert result.gap is None
    assert result.reset_effect is None
    assert result.theoretical.status == "insufficient_data"
    assert result.reason is not None
    assert result.window.aligned_bars == 0


def test_single_aligned_bar_is_insufficient_data() -> None:
    result = _decompose([100.0], [100.0])
    assert result.status == "insufficient_data"
    assert result.actual_return is None
    assert result.reason is not None


def test_opened_at_after_all_bars_is_insufficient_data() -> None:
    result = _decompose(_INDEX_GOLDEN, _ETF_GOLDEN, opened_at=date(2024, 6, 1))
    assert result.status == "insufficient_data"
    assert result.window.opened_at == "2024-06-01"


def test_non_positive_start_price_is_insufficient_data() -> None:
    result = _decompose([0.0, 110.0, 99.0], [100.0, 120.0, 96.0])
    assert result.status == "insufficient_data"
    assert result.reason is not None


def test_two_bars_have_too_few_returns_for_the_theory_block() -> None:
    result = _decompose([100.0, 110.0], [100.0, 120.0])
    assert result.status == "ok"
    assert result.theoretical.status == "insufficient_data"
    assert result.theoretical.theoretical_drag is None
    assert result.theoretical.reason is not None
    _assert_identity(result)


def test_provenance_and_assumptions_survive() -> None:
    result = _decompose(_INDEX_GOLDEN, _ETF_GOLDEN)
    assert result.source == "twse"
    assert result.index_source == "twse-index"
    assert result.as_of is not None
    assert result.index_as_of is not None
    assert result.inputs_used.columns == ["close"]
    assert result.inputs_used.window["aligned_bars"] == 3
    assert len(result.assumptions) >= 5


def test_align_closes_intersects_dates() -> None:
    joined = G.align_closes(
        bars([1.0, 2.0, 3.0, 4.0], symbol="A"),
        bars([10.0, 20.0], symbol="B"),
    )
    assert len(joined) == 2

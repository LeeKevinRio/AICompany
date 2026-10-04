"""Golden and behavioural tests for the risk layer."""

from __future__ import annotations

import math

from app.signals import risk as R
from tests.signals_helpers import bars_from_closes

TOL = 1e-9


# --- Pure numeric cores (hand-computed) --------------------------------------


def test_annualized_volatility_golden() -> None:
    # returns +-1% alternating: sample std (ddof=1) of [.01,-.01,.01,-.01]
    # = sqrt(0.0004/3) = 0.0115470; annualized *sqrt(252) = 0.1833030.
    result = R.annualized_volatility([0.01, -0.01, 0.01, -0.01])
    assert result is not None
    daily, annual = result
    assert math.isclose(daily, 0.011547005383792516, rel_tol=TOL)
    assert math.isclose(annual, 0.18330302779823363, rel_tol=TOL)


def test_annualized_volatility_needs_two_points() -> None:
    assert R.annualized_volatility([0.01]) is None
    assert R.annualized_volatility([]) is None


def test_max_drawdown_golden() -> None:
    # path 100 ->120 ->90 ->130. Peak 120 (idx1), trough 90 (idx2), dd=-0.25.
    result = R.max_drawdown([100.0, 120.0, 90.0, 130.0])
    assert result is not None
    worst, peak_i, trough_i = result
    assert math.isclose(worst, -0.25, abs_tol=1e-12)
    assert peak_i == 1
    assert trough_i == 2


def test_max_drawdown_monotonic_up_is_zero() -> None:
    result = R.max_drawdown([10.0, 11.0, 12.0])
    assert result is not None
    assert result[0] == 0.0


def test_current_drawdown_golden() -> None:
    # path 100 ->120 ->90 ->130 ->117. Highest close so far 130 (idx3);
    # current = 117/130 - 1 = -0.1, while the historical max stays -0.25.
    result = R.current_drawdown([100.0, 120.0, 90.0, 130.0, 117.0])
    assert result is not None
    value, peak_i = result
    assert math.isclose(value, -0.1, abs_tol=1e-12)
    assert peak_i == 3
    worst = R.max_drawdown([100.0, 120.0, 90.0, 130.0, 117.0])
    assert worst is not None and math.isclose(worst[0], -0.25, abs_tol=1e-12)


def test_current_drawdown_still_below_the_old_high() -> None:
    # 100 ->120 ->90 ->108: never regained 120, so current = 108/120 - 1 = -0.1.
    result = R.current_drawdown([100.0, 120.0, 90.0, 108.0])
    assert result is not None
    assert math.isclose(result[0], -0.1, abs_tol=1e-12)
    assert result[1] == 1


def test_current_drawdown_is_zero_on_a_new_high() -> None:
    result = R.current_drawdown([100.0, 70.0, 130.0])
    assert result == (0.0, 2)


def test_current_drawdown_peak_is_the_latest_touch_of_the_high() -> None:
    # 120 reached at idx1 and again at idx3: the revisit is reported.
    result = R.current_drawdown([100.0, 120.0, 90.0, 120.0, 108.0])
    assert result is not None
    assert math.isclose(result[0], -0.1, abs_tol=1e-12)
    assert result[1] == 3


def test_current_drawdown_needs_two_points() -> None:
    assert R.current_drawdown([100.0]) is None
    assert R.current_drawdown([]) is None


def test_current_drawdown_is_the_last_point_of_the_underwater_path() -> None:
    paths = (
        [100.0, 120.0, 90.0, 130.0, 117.0],
        [50.0, 40.0, 30.0, 35.0],
        [10.0, 11.0, 12.0],
        [100.0, 100.0, 99.0],
    )
    for path in paths:
        result = R.current_drawdown(path)
        worst = R.max_drawdown(path)
        assert result is not None and worst is not None
        assert result[0] == R.drawdown_series(path)[-1]
        # Current can never be deeper than the window's historical maximum.
        assert worst[0] <= result[0] <= 0.0


def test_beta_golden_two_x() -> None:
    # asset = 2 * benchmark exactly -> beta = 2.
    value = R.beta([0.02, -0.04, 0.06], [0.01, -0.02, 0.03])
    assert value is not None
    assert math.isclose(value, 2.0, rel_tol=1e-9)


def test_beta_zero_variance_benchmark_is_none() -> None:
    assert R.beta([0.01, 0.02, 0.03], [0.0, 0.0, 0.0]) is None
    assert R.beta([0.01], [0.02]) is None
    assert R.beta([0.01, 0.02], [0.01]) is None  # mismatched lengths


# --- Bar-level wrappers ------------------------------------------------------


def test_volatility_wrapper_ok_and_insufficient() -> None:
    bars = bars_from_closes([100.0, 101.0, 100.0, 101.0, 100.0])
    result = R.volatility(bars)
    assert result.status == "ok"
    assert result.annualized_volatility is not None
    assert result.observations == 4
    # Two bars -> one return -> cannot compute a std.
    assert R.volatility(bars_from_closes([100.0, 101.0])).status == "insufficient_data"


def test_drawdown_wrapper_reports_dates() -> None:
    bars = bars_from_closes([100.0, 120.0, 90.0, 130.0])
    result = R.drawdown(bars)
    assert result.status == "ok"
    assert result.max_drawdown is not None
    assert math.isclose(result.max_drawdown, -0.25, abs_tol=1e-12)
    assert result.peak_date == bars[1].date.isoformat()
    assert result.trough_date == bars[2].date.isoformat()


def test_drawdown_wrapper_reports_current_and_its_peak_date() -> None:
    bars = bars_from_closes([100.0, 120.0, 90.0, 130.0, 117.0])
    result = R.drawdown(bars)
    assert result.status == "ok"
    assert result.current is not None
    assert math.isclose(result.current, -0.1, abs_tol=1e-12)
    assert result.current_peak_date == bars[3].date.isoformat()
    # The historical fields are untouched by the new ones (backward compatible).
    assert result.max_drawdown is not None
    assert math.isclose(result.max_drawdown, -0.25, abs_tol=1e-12)
    assert result.peak_date == bars[1].date.isoformat()
    assert result.trough_date == bars[2].date.isoformat()


def test_drawdown_wrapper_insufficient_has_no_current() -> None:
    result = R.drawdown(bars_from_closes([100.0]))
    assert result.status == "insufficient_data"
    assert result.current is None
    assert result.current_peak_date is None


def test_drawdown_result_without_the_new_fields_still_validates() -> None:
    # A payload produced before ``current`` existed (e.g. a stored snapshot)
    # must still load: the two fields are additive with ``None`` defaults.
    legacy = R.drawdown(bars_from_closes([100.0, 120.0, 90.0])).model_dump()
    del legacy["current"]
    del legacy["current_peak_date"]
    restored = R.DrawdownResult.model_validate(legacy)
    assert restored.current is None
    assert restored.max_drawdown == legacy["max_drawdown"]


def test_position_beta_missing_benchmark_is_insufficient() -> None:
    bars = bars_from_closes([100.0, 101.0, 102.0, 103.0])
    result = R.position_beta(bars, None, benchmark_label="TWSE")
    assert result.status == "insufficient_data"
    assert result.benchmark == "TWSE"


def test_position_beta_aligns_on_common_dates() -> None:
    asset = bars_from_closes([100.0, 102.0, 98.0, 104.0], symbol="A")
    bench = bars_from_closes([100.0, 101.0, 99.0, 102.0], symbol="IDX")
    result = R.position_beta(asset, bench, benchmark_label="IDX")
    assert result.status == "ok"
    assert result.beta is not None
    assert result.observations == 3


def test_correlation_matrix_perfect_and_insufficient() -> None:
    up = [100.0, 101.0, 102.0, 103.0, 104.0]
    matrix = R.correlation_matrix(
        {
            "UP": bars_from_closes(up, symbol="UP"),
            "UP2": bars_from_closes(up, symbol="UP2"),
            "SHORT": bars_from_closes([10.0, 11.0], symbol="SHORT"),
        }
    )
    assert matrix.status == "ok"
    # Identical return paths -> correlation 1.
    assert matrix.matrix["UP"]["UP2"] is not None
    assert math.isclose(matrix.matrix["UP"]["UP2"], 1.0, abs_tol=1e-9)
    # SHORT has only one return -> every pair with it is insufficient (null).
    assert matrix.matrix["UP"]["SHORT"] is None
    flagged = set(matrix.insufficient_pairs)
    assert ("SHORT", "UP") in flagged or ("SHORT", "UP2") in flagged


def test_correlation_single_symbol_is_insufficient() -> None:
    result = R.correlation_matrix({"A": bars_from_closes([1.0, 2.0, 3.0])})
    assert result.status == "insufficient_data"

"""``sigma_d`` and ``SigmaEstimate`` (ADR-0027 D-3 N-63; FL-75 (a)-(e), FL-78 (e)(f)).

The fixture definition has ``SIGMA_MIN_VALID = 55`` and ``SIGMA_FLOOR = 0.001``
(test values; the pre-registration's are the same, but nothing is registered).
FL-75 (f)-(h) belong to the store and recorder batches; FL-55 and the single
definition of ``SigmaEstimate`` (FL-75 (i)) are in
``tests/test_forecast_boundaries.py``.
"""

from __future__ import annotations

import inspect
import math
import statistics
import struct
from typing import Any

import pytest

from app.outlook.volatility import E_VOL_DEGENERATE, E_VOL_SHORT, SigmaEstimate, sigma_d
from tests.dirdef_helpers import make_definition

DEFINITION = make_definition(SIGMA_MIN_VALID=55, SIGMA_FLOOR=0.001)


def _series(count: int, *, spread: float = 0.01, nones: int = 0) -> list[float | None]:
    values: list[float | None] = [spread * ((i % 7) - 3) / 3 for i in range(count)]
    return values + [None] * nones


# --- FL-75 (a) valid count -------------------------------------------------------------


@pytest.mark.parametrize("valid", [54, 0])
def test_too_few_valid_returns_give_e_vol_short(valid: int) -> None:
    estimate = sigma_d(_series(valid, nones=60 - valid), definition=DEFINITION)
    assert estimate == SigmaEstimate(
        value=None, valid_returns=valid, raw_std=None, missing_code=E_VOL_SHORT
    )


def test_fifty_five_valid_returns_give_a_value() -> None:
    estimate = sigma_d(_series(55, nones=5), definition=DEFINITION)
    assert estimate.missing_code is None
    assert estimate.valid_returns == 55
    assert estimate.value == estimate.raw_std
    assert estimate.value is not None and math.isfinite(estimate.value) and estimate.value > 0


def test_none_items_do_not_count() -> None:
    series = _series(55)
    with_gaps = series[:20] + [None, None] + series[20:]
    assert sigma_d(with_gaps, definition=DEFINITION) == sigma_d(series, definition=DEFINITION)


def test_the_estimate_is_the_ddof_one_sample_std() -> None:
    series = [v for v in _series(60) if v is not None]
    assert sigma_d(series, definition=DEFINITION).value == statistics.stdev(series)


# --- FL-75 (b) constant series ---------------------------------------------------------


@pytest.mark.parametrize(
    "series",
    [
        pytest.param([0.0] * 60, id="zeros"),
        pytest.param([0.1] * 60, id="tenths"),
        pytest.param([math.log(1.01)] * 55 + [None] * 5, id="log-1.01"),
    ],
)
def test_a_constant_series_is_exactly_zero_and_degenerate(series: list[float | None]) -> None:
    estimate = sigma_d(series, definition=DEFINITION)
    assert estimate.raw_std is not None
    assert struct.pack("<d", estimate.raw_std) == struct.pack("<d", 0.0)
    assert estimate.value is None
    assert estimate.missing_code == E_VOL_DEGENERATE


# --- FL-75 (c) near constant -----------------------------------------------------------


def test_a_near_constant_series_is_degenerate_with_a_finite_raw_std() -> None:
    series = [5e-4 if i % 2 else -5e-4 for i in range(60)]
    estimate = sigma_d(series, definition=DEFINITION)
    assert estimate.value is None
    assert estimate.missing_code == E_VOL_DEGENERATE
    assert estimate.raw_std is not None
    assert 0 < estimate.raw_std < DEFINITION.SIGMA_FLOOR
    assert estimate.raw_std == pytest.approx(5e-4, rel=0.02)


def test_the_floor_is_strict() -> None:
    series = [v for v in _series(60) if v is not None]
    raw = statistics.stdev(series)
    at_floor = make_definition(SIGMA_MIN_VALID=55, SIGMA_FLOOR=raw)
    assert sigma_d(series, definition=at_floor).value == raw


# --- FL-75 (d) non-finite input --------------------------------------------------------


@pytest.mark.parametrize("bad", [math.nan, math.inf, -math.inf])
def test_non_finite_input_raises(bad: float) -> None:
    with pytest.raises(ValueError):
        sigma_d([*_series(59), bad], definition=DEFINITION)


@pytest.mark.parametrize("bad", [1, True, "0.01", [0.01]])
def test_non_float_input_raises(bad: Any) -> None:
    with pytest.raises(TypeError):
        sigma_d([*_series(59), bad], definition=DEFINITION)


def test_non_finite_input_raises_even_when_short() -> None:
    with pytest.raises(ValueError):
        sigma_d([math.nan], definition=DEFINITION)


# --- FL-75 (e) determinism -------------------------------------------------------------


def test_the_same_input_gives_the_same_bits() -> None:
    series = [math.sin(i) / 50 for i in range(60)]
    first = sigma_d(series, definition=DEFINITION)
    second = sigma_d(list(series), definition=DEFINITION)
    assert first.value is not None and second.value is not None
    assert struct.pack("<d", first.value) == struct.pack("<d", second.value)


# --- FL-78 (e)(f) definition passed in -------------------------------------------------


def test_definition_is_keyword_only_without_default() -> None:
    parameter = inspect.signature(sigma_d).parameters["definition"]
    assert parameter.kind is inspect.Parameter.KEYWORD_ONLY
    assert parameter.default is inspect.Parameter.empty


def test_each_definition_judges_degeneracy_by_its_own_floor() -> None:
    series = [0.002 if i % 2 else -0.002 for i in range(60)]
    loose = make_definition(definition_version="dirdef-v1.0", SIGMA_FLOOR=0.001)
    strict = make_definition(definition_version="dirdef-v2.0", SIGMA_FLOOR=0.003)
    assert sigma_d(series, definition=loose).missing_code is None
    assert sigma_d(series, definition=strict).missing_code == E_VOL_DEGENERATE


def test_each_definition_judges_shortness_by_its_own_minimum() -> None:
    series = _series(56)
    assert sigma_d(series, definition=make_definition(SIGMA_MIN_VALID=56)).missing_code is None
    assert (
        sigma_d(series, definition=make_definition(SIGMA_MIN_VALID=57)).missing_code == E_VOL_SHORT
    )


# --- SigmaEstimate contract ------------------------------------------------------------


@pytest.mark.parametrize(
    "fields",
    [
        pytest.param(
            {"value": 0.01, "raw_std": None, "missing_code": E_VOL_SHORT}, id="short-value"
        ),
        pytest.param({"value": None, "raw_std": 0.01, "missing_code": E_VOL_SHORT}, id="short-raw"),
        pytest.param(
            {"value": 0.01, "raw_std": 0.01, "missing_code": E_VOL_DEGENERATE}, id="degen-value"
        ),
        pytest.param(
            {"value": None, "raw_std": None, "missing_code": E_VOL_DEGENERATE}, id="degen-no-raw"
        ),
        pytest.param({"value": None, "raw_std": 0.01, "missing_code": None}, id="no-code-no-value"),
        pytest.param({"value": 0.01, "raw_std": 0.02, "missing_code": None}, id="value-not-raw"),
        pytest.param({"value": 0.01, "raw_std": 0.01, "missing_code": "E-X"}, id="unknown-code"),
    ],
)
def test_a_contradictory_estimate_cannot_be_built(fields: dict[str, Any]) -> None:
    with pytest.raises(ValueError):
        SigmaEstimate(valid_returns=60, **fields)


@pytest.mark.parametrize("bad", [-1, True])
def test_valid_returns_must_be_a_non_negative_int(bad: Any) -> None:
    with pytest.raises(ValueError):
        SigmaEstimate(value=None, valid_returns=bad, raw_std=None, missing_code=E_VOL_SHORT)

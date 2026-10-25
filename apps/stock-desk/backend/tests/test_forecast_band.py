"""``threshold_inputs`` and ``labeled_snapshot_violations`` (ADR-0027 ``band.py``).

Covers the pure-function half of FL-72 (b), (g), (i), FL-79 (e) for the two
functions, and the per-violation judgement of ADR-0027 D-3, N-115 sentence
(N115-10): each violation on its own condition, bool / non-``int``
``valid_returns`` as null, out-of-range ``int`` as +inf or -inf, bit-for-bit
comparison with the definition, and a missing ``sigma_d`` that records nothing
but ``sigma_d_missing``.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any

import pytest

from app.forecast.band import ThresholdInputs, labeled_snapshot_violations, threshold_inputs
from app.forecast.errors import THRESHOLD_VIOLATION_ORDER, ThresholdViolation

#: An int no IEEE 754 double can hold (``float()`` raises ``OverflowError``).
HUGE = 10**400


@dataclass(frozen=True)
class FakeDefinition:
    """One registered dirdef version, as ``band.py`` sees it (``BandDefinition``)."""

    EPS: float = 0.1
    SIGMA_FLOOR: float = 1e-6
    SIGMA_MIN_VALID: int = 60
    ks: dict[int, float] = field(default_factory=lambda: {3: 0.5, 5: 0.6})

    def k_for(self, horizon: int) -> float:
        return self.ks[horizon]


V1 = FakeDefinition()
#: A second definition version whose K differ from V1's.
V2 = FakeDefinition(ks={3: 0.55, 5: 0.65})


def _band(**overrides: Any) -> dict[str, Any]:
    band: dict[str, Any] = {
        "K_h": 0.5,
        "EPS": 0.1,
        "sigma_d": 0.012,
        "valid_returns": 60,
        "up_pct": 0.006,
        "down_pct": 0.006,
    }
    for key, value in overrides.items():
        if value is _ABSENT:
            band.pop(key)
        else:
            band[key] = value
    return band


_ABSENT = object()


def _violations(band: dict[str, Any], *, horizon: int = 3) -> tuple[ThresholdViolation, ...]:
    return labeled_snapshot_violations(band, horizon=horizon, definition=V1)


# --- threshold_inputs ----------------------------------------------------------------


def test_complete_inputs_return_the_three_doubles() -> None:
    result = threshold_inputs(_band(K_h=1, EPS=0.1, sigma_d=0.012))
    assert result == ThresholdInputs(K_h=1.0, EPS=0.1, sigma_d=0.012)
    assert result is not None and type(result.K_h) is float
    # Only the three keys are read; the rest of band_def plays no part.
    assert threshold_inputs({"K_h": 0.5, "EPS": 0.1, "sigma_d": 0.012}) == ThresholdInputs(
        K_h=0.5, EPS=0.1, sigma_d=0.012
    )


@pytest.mark.parametrize(
    "overrides",
    [
        pytest.param({"K_h": _ABSENT}, id="k_h-absent"),
        pytest.param({"EPS": _ABSENT}, id="eps-absent"),
        pytest.param({"sigma_d": _ABSENT}, id="sigma_d-absent"),
        pytest.param({"K_h": None}, id="k_h-null"),
        pytest.param({"EPS": None}, id="eps-null"),
        pytest.param({"sigma_d": None}, id="sigma_d-null"),
        pytest.param({"sigma_d": 0.0}, id="sigma_d-zero"),
        pytest.param({"sigma_d": -0.01}, id="sigma_d-negative"),
        pytest.param({"sigma_d": math.nan}, id="sigma_d-nan"),
        pytest.param({"sigma_d": math.inf}, id="sigma_d-plus-inf"),
        pytest.param({"sigma_d": -math.inf}, id="sigma_d-minus-inf"),
    ],
)
def test_missing_inputs_yield_none(overrides: dict[str, Any]) -> None:
    assert threshold_inputs(_band(**overrides)) is None


@pytest.mark.parametrize(
    "overrides",
    [
        pytest.param({"sigma_d": True}, id="sigma_d-true"),
        pytest.param({"sigma_d": "0.01"}, id="sigma_d-string"),
        pytest.param({"sigma_d": [0.01]}, id="sigma_d-list"),
        pytest.param({"K_h": True}, id="k_h-true"),
        pytest.param({"EPS": {"v": 0.1}}, id="eps-dict"),
    ],
)
def test_bool_or_non_numeric_inputs_count_as_missing(overrides: dict[str, Any]) -> None:
    # FL-79 (e): treated like null, never raised on.
    assert threshold_inputs(_band(**overrides)) is None


def test_an_int_beyond_double_range_counts_as_infinity() -> None:
    assert threshold_inputs(_band(sigma_d=HUGE)) is None
    result = threshold_inputs(_band(K_h=HUGE, EPS=-HUGE))
    assert result is not None
    assert (result.K_h, result.EPS) == (math.inf, -math.inf)


def test_k_h_and_eps_are_judged_for_presence_only() -> None:
    # Known gap carried by the tracking item (N115-10): a non-finite K_h / EPS is
    # "complete" here; the labelled path records *_mismatch for it instead.
    result = threshold_inputs(_band(K_h=math.nan, EPS=math.inf))
    assert result is not None
    assert math.isnan(result.K_h) and result.EPS == math.inf


# --- labeled_snapshot_violations ------------------------------------------------------


def test_a_complete_snapshot_has_no_violation() -> None:
    band = _band()
    before = dict(band)
    assert _violations(band) == ()
    threshold_inputs(band)
    assert band == before  # neither function mutates its input


@pytest.mark.parametrize(
    ("overrides", "expected"),
    [
        pytest.param({"K_h": _ABSENT}, ("k_h_missing",), id="k_h_missing"),
        pytest.param({"K_h": 0.55}, ("k_h_mismatch",), id="k_h_mismatch"),
        pytest.param({"EPS": None}, ("eps_missing",), id="eps_missing"),
        pytest.param({"EPS": 0.2}, ("eps_mismatch",), id="eps_mismatch"),
        pytest.param({"sigma_d": None}, ("sigma_d_missing",), id="sigma_d_missing"),
        pytest.param(
            {"sigma_d": math.nan}, ("sigma_d_not_positive_finite",), id="sigma_d_not_positive"
        ),
        pytest.param({"sigma_d": 1e-9}, ("sigma_d_below_floor",), id="sigma_d_below_floor"),
        pytest.param({"valid_returns": 59}, ("valid_returns_below_min",), id="valid_returns"),
    ],
)
def test_each_violation_value(overrides: dict[str, Any], expected: tuple[str, ...]) -> None:
    assert _violations(_band(**overrides)) == expected


def test_violations_follow_the_closed_order_without_repeats() -> None:
    result = _violations(_band(K_h=None, EPS=0.2, sigma_d=-1.0, valid_returns=None))
    assert result == (
        "k_h_missing",
        "eps_mismatch",
        "sigma_d_not_positive_finite",
        "sigma_d_below_floor",
        "valid_returns_below_min",
    )
    assert list(result) == [v for v in THRESHOLD_VIOLATION_ORDER if v in result]
    # Together with the complement, every value of the closed list is reachable.
    complement = _violations(_band(K_h=0.6, EPS=None, sigma_d=None))
    assert set(result) | set(complement) == set(THRESHOLD_VIOLATION_ORDER)


@pytest.mark.parametrize(
    ("sigma_d", "expected"),
    [
        pytest.param(0.0, ("sigma_d_not_positive_finite", "sigma_d_below_floor"), id="zero"),
        pytest.param(-0.0, ("sigma_d_not_positive_finite", "sigma_d_below_floor"), id="neg-zero"),
        pytest.param(-0.01, ("sigma_d_not_positive_finite", "sigma_d_below_floor"), id="negative"),
        pytest.param(
            -math.inf, ("sigma_d_not_positive_finite", "sigma_d_below_floor"), id="minus-inf"
        ),
        pytest.param(math.nan, ("sigma_d_not_positive_finite",), id="nan"),
        pytest.param(math.inf, ("sigma_d_not_positive_finite",), id="plus-inf"),
        pytest.param(HUGE, ("sigma_d_not_positive_finite",), id="huge-int"),
        pytest.param(
            -HUGE, ("sigma_d_not_positive_finite", "sigma_d_below_floor"), id="huge-negative-int"
        ),
        pytest.param(1e-6, (), id="at-the-floor"),
    ],
)
def test_each_sigma_violation_is_judged_on_its_own(
    sigma_d: object, expected: tuple[str, ...]
) -> None:
    assert _violations(_band(sigma_d=sigma_d)) == expected


@pytest.mark.parametrize(
    "sigma_d",
    [
        pytest.param(_ABSENT, id="absent"),
        pytest.param(None, id="null"),
        pytest.param(True, id="true"),
        pytest.param(False, id="false"),
        pytest.param("0.012", id="string"),
        pytest.param("-1", id="negative-string"),
        pytest.param([0.012], id="list"),
        pytest.param({"v": 0.012}, id="dict"),
    ],
)
def test_a_missing_sigma_d_records_no_other_sigma_violation(sigma_d: object) -> None:
    # Risk suggestion: null / absent / non-numeric is "missing" only, never also
    # "not positive finite" or "below floor".
    assert _violations(_band(sigma_d=sigma_d)) == ("sigma_d_missing",)


@pytest.mark.parametrize(
    "valid_returns",
    [
        pytest.param(_ABSENT, id="absent"),
        pytest.param(None, id="null"),
        pytest.param(True, id="true"),
        pytest.param(60.0, id="float"),
        pytest.param("60", id="string"),
        pytest.param(59, id="below"),
    ],
)
def test_valid_returns_below_min_or_not_an_int(valid_returns: object) -> None:
    assert _violations(_band(valid_returns=valid_returns)) == ("valid_returns_below_min",)


def test_valid_returns_at_or_above_the_minimum_is_fine() -> None:
    assert _violations(_band(valid_returns=60)) == ()
    assert _violations(_band(valid_returns=HUGE)) == ()


@pytest.mark.parametrize(
    ("overrides", "expected"),
    [
        pytest.param({"K_h": True}, ("k_h_missing",), id="k_h-true"),
        pytest.param({"EPS": "0.1"}, ("eps_missing",), id="eps-string"),
        pytest.param({"K_h": [0.5]}, ("k_h_missing",), id="k_h-list"),
        pytest.param({"valid_returns": True}, ("valid_returns_below_min",), id="valid-true"),
    ],
)
def test_bool_or_non_numeric_values_count_as_missing_or_null(
    overrides: dict[str, Any], expected: tuple[str, ...]
) -> None:
    assert _violations(_band(**overrides)) == expected


@pytest.mark.parametrize(
    ("definition", "k_h", "expected"),
    [
        (V1, 0.5, ()),
        (V1, 0.55, ("k_h_mismatch",)),
        (V2, 0.55, ()),
        (V2, 0.5, ("k_h_mismatch",)),
    ],
)
def test_each_definition_version_is_compared_with_its_own_k(
    definition: FakeDefinition, k_h: float, expected: tuple[str, ...]
) -> None:
    band = _band(K_h=k_h)
    assert labeled_snapshot_violations(band, horizon=3, definition=definition) == expected
    # And each horizon with its own K within that version.
    k_5 = definition.k_for(5)
    assert labeled_snapshot_violations(_band(K_h=k_5), horizon=5, definition=definition) == ()


@pytest.mark.parametrize(
    ("overrides", "definition", "expected"),
    [
        pytest.param({"K_h": -0.0}, FakeDefinition(ks={3: 0.0}), ("k_h_mismatch",), id="signed-0"),
        pytest.param(
            {"K_h": math.nan}, FakeDefinition(ks={3: math.nan}), ("k_h_mismatch",), id="nan-k"
        ),
        pytest.param({"K_h": 1}, FakeDefinition(ks={3: 1.0}), (), id="int-equals-double"),
        pytest.param({"K_h": math.nextafter(0.5, 1.0)}, V1, ("k_h_mismatch",), id="one-ulp-apart"),
        pytest.param({"K_h": HUGE}, V1, ("k_h_mismatch",), id="huge-int-k"),
    ],
)
def test_comparison_with_the_definition_is_bit_for_bit(
    overrides: dict[str, Any], definition: FakeDefinition, expected: tuple[str, ...]
) -> None:
    band = _band(**overrides)
    assert labeled_snapshot_violations(band, horizon=3, definition=definition) == expected

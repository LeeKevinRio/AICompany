"""Sector basket series (ADR-0027 D-1 ``basket.py``; FL-56).

FL-56 cells:

* the ratio average differs from the price-level average on the fixture, and the
  function returns the former;
* the 90% valid weight is taken over |S_T|, not over the members with data;
* excluded weight above 10% gives ``E-ADJ-COVERAGE`` (exactly 10% does not),
  driven by a fixture definition with ``BASKET_MIN_MEMBER_WEIGHT = 0.9``; the
  threshold is read from the definition passed in (B2D-3d);
* ``coverage_unknown`` and ``definition`` are keyword-only without default;
  ``coverage_unknown`` naming a non-member is a ``ValueError``;
* no look-ahead: prices after the window's last session change nothing;
* C-10 (a): registered versions, sorted by version number, never set
  ``BASKET_MIN_MEMBER_WEIGHT`` below the first registered (frozen) value;
  the subtraction tripwire (C-10 (b)) is in ``tests/test_forecast_boundaries.py``;
* B1 / B4 use S_{T-h}: the functions read exactly the members passed in, so the
  baseline batch can pass S_{T-h}; members outside the set are ignored;
* the import-graph cell (``basket`` and ``volatility`` never reach
  ``app.sectors``) is in ``tests/test_forecast_boundaries.py``.
"""

from __future__ import annotations

import inspect
import math
from collections.abc import Iterable
from datetime import date, timedelta
from typing import Any

import pytest

from app.dirdef import registry
from app.dirdef.definition import DirectionDefinition
from app.outlook.basket import (
    E_ADJ_COVERAGE,
    BasketHoldRatio,
    basket_hold_ratio,
    basket_log_returns,
)
from tests.dirdef_helpers import make_definition

#: Fixture definition with BASKET_MIN_MEMBER_WEIGHT = 0.9 (B2D-3d).
DEFINITION = make_definition(BASKET_MIN_MEMBER_WEIGHT=0.9)

D0 = date(2026, 10, 1)
WINDOW = [D0 + timedelta(days=i) for i in range(4)]


def _flat(price: float, days: list[date] = WINDOW) -> dict[date, float]:
    return dict.fromkeys(days, price)


def _members(count: int) -> list[str]:
    return [f"m{i:02d}" for i in range(count)]


def test_the_ratio_average_is_used_not_the_level_average() -> None:
    series = {
        "cheap": {WINDOW[0]: 10.0, WINDOW[1]: 11.0},
        "dear": {WINDOW[0]: 1000.0, WINDOW[1]: 990.0},
    }
    result = basket_log_returns(
        ["cheap", "dear"], series, WINDOW[:2], coverage_unknown=(), definition=DEFINITION
    )
    ratio_average = math.log((11.0 / 10.0 + 990.0 / 1000.0) / 2)
    level_average = math.log((11.0 + 990.0) / (10.0 + 1000.0))
    assert ratio_average != pytest.approx(level_average)
    assert len(result.r_t) == 1
    assert result.r_t[0] == pytest.approx(ratio_average)


def test_the_series_has_one_entry_per_return_day() -> None:
    series = {m: _flat(10.0) for m in _members(3)}
    result = basket_log_returns(
        _members(3), series, WINDOW, coverage_unknown=(), definition=DEFINITION
    )
    assert result.dates == tuple(WINDOW[1:])
    assert result.r_t == (0.0, 0.0, 0.0)
    assert result.N_t == (3, 3, 3)
    assert result.V_t == (("m00", "m01", "m02"),) * 3
    assert result.invalid_days == ()
    assert result.missing_code is None


def test_the_valid_weight_is_taken_over_all_members() -> None:
    members = _members(10)
    series = {m: _flat(10.0) for m in members}
    # Day 2: two members lack a bar. 8 / 10 < 90% -> invalid, even though all
    # members with data agree; 8 / 8 would have passed.
    for m in members[:2]:
        del series[m][WINDOW[2]]
    result = basket_log_returns(members, series, WINDOW, coverage_unknown=(), definition=DEFINITION)
    # Day 2 breaks both return days 2 (t-1 = day 1 has data, t = day 2 lacks)
    # and 3 (t-1 = day 2 lacks).
    assert result.N_t == (10, 8, 8)
    assert result.r_t == (0.0, None, None)
    assert result.invalid_days == (WINDOW[2], WINDOW[3])


def test_exactly_ninety_percent_is_valid() -> None:
    members = _members(10)
    series = {m: _flat(10.0) for m in members}
    del series[members[0]][WINDOW[1]]
    result = basket_log_returns(
        members, series, WINDOW[:2], coverage_unknown=(), definition=DEFINITION
    )
    assert result.N_t == (9,)
    assert result.r_t == (0.0,)


@pytest.mark.parametrize(
    ("size", "unknown", "expected"),
    [
        # Risk R-2: exactly 10% (1 of 10 excluded) must not trigger.
        pytest.param(10, 1, None, id="ten-percent-1-of-10-no-code"),
        pytest.param(10, 2, E_ADJ_COVERAGE, id="twenty-percent"),
        pytest.param(9, 1, E_ADJ_COVERAGE, id="eleven-percent"),
        pytest.param(20, 2, None, id="ten-percent-of-twenty"),
        pytest.param(20, 3, E_ADJ_COVERAGE, id="fifteen-percent"),
    ],
)
def test_excluded_weight_above_ten_percent_gives_e_adj_coverage(
    size: int, unknown: int, expected: str | None
) -> None:
    members = _members(size)
    series = {m: _flat(10.0) for m in members}
    result = basket_log_returns(
        members, series, WINDOW, coverage_unknown=members[:unknown], definition=DEFINITION
    )
    assert result.missing_code == expected
    assert result.excluded_members == tuple(members[:unknown])
    assert all(not set(members[:unknown]) & set(valid) for valid in result.V_t)


def test_excluded_members_do_not_enter_the_returns() -> None:
    members = _members(10)
    series = {m: _flat(10.0) for m in members}
    series["m00"] = {WINDOW[0]: 10.0, WINDOW[1]: 20.0, WINDOW[2]: 20.0, WINDOW[3]: 20.0}
    result = basket_log_returns(
        members, series, WINDOW, coverage_unknown=["m00"], definition=DEFINITION
    )
    assert result.r_t == (0.0, 0.0, 0.0)


def test_only_the_members_passed_in_are_read() -> None:
    # B1 / B4 pass S_{T-h}; a member of S_T outside that set must not count.
    s_t_minus_h = _members(3)
    series = {m: _flat(10.0) for m in s_t_minus_h}
    series["joined_later"] = {WINDOW[0]: 10.0, WINDOW[1]: 30.0}
    result = basket_log_returns(
        s_t_minus_h, series, WINDOW[:2], coverage_unknown=(), definition=DEFINITION
    )
    assert result.r_t == (0.0,)
    hold = basket_hold_ratio(s_t_minus_h, series, WINDOW[0], WINDOW[1])
    assert hold == BasketHoldRatio(ratio=1.0, members_used=tuple(s_t_minus_h), members_missing=())


def test_the_hold_ratio_is_the_equal_weight_buy_and_hold_average() -> None:
    series = {
        "a": {WINDOW[0]: 10.0, WINDOW[3]: 12.0},
        "b": {WINDOW[0]: 200.0, WINDOW[3]: 180.0},
        "c": {WINDOW[0]: 5.0},
    }
    hold = basket_hold_ratio(["c", "b", "a"], series, WINDOW[0], WINDOW[3])
    assert hold.ratio == pytest.approx((1.2 + 0.9) / 2)
    assert hold.members_used == ("a", "b")
    assert hold.members_missing == ("c",)


def test_the_hold_ratio_is_none_without_any_usable_member() -> None:
    hold = basket_hold_ratio(["a"], {"a": {WINDOW[0]: 10.0}}, WINDOW[0], WINDOW[1])
    assert hold.ratio is None


@pytest.mark.parametrize(
    ("kwargs", "error"),
    [
        pytest.param({"members": []}, ValueError, id="no-members"),
        pytest.param({"members": ["a", "a"]}, ValueError, id="repeat-member"),
        pytest.param({"window": WINDOW[:1]}, ValueError, id="short-window"),
        pytest.param({"window": [WINDOW[1], WINDOW[0]]}, ValueError, id="unordered-window"),
        pytest.param({"coverage_unknown": ["zz"]}, ValueError, id="unknown-non-member"),
        pytest.param({"series": {"a": {WINDOW[0]: -1.0, WINDOW[1]: 1.0}}}, ValueError, id="neg"),
        pytest.param(
            {"series": {"a": {WINDOW[0]: math.nan, WINDOW[1]: 1.0}}}, ValueError, id="nan"
        ),
        pytest.param({"series": {"a": {WINDOW[0]: "1", WINDOW[1]: 1.0}}}, TypeError, id="str"),
        pytest.param({"series": {"a": {WINDOW[0]: True, WINDOW[1]: 1.0}}}, TypeError, id="bool"),
    ],
)
def test_bad_basket_inputs_raise(kwargs: dict[str, Any], error: type[Exception]) -> None:
    arguments: dict[str, Any] = {
        "members": ["a"],
        "series": {"a": _flat(1.0)},
        "window": WINDOW[:2],
        "coverage_unknown": (),
    }
    arguments.update(kwargs)
    with pytest.raises(error):
        basket_log_returns(
            arguments["members"],
            arguments["series"],
            arguments["window"],
            coverage_unknown=arguments["coverage_unknown"],
            definition=DEFINITION,
        )


def test_an_int_price_is_accepted() -> None:
    result = basket_log_returns(
        ["a"],
        {"a": {WINDOW[0]: 10, WINDOW[1]: 10}},
        WINDOW[:2],
        coverage_unknown=(),
        definition=DEFINITION,
    )
    assert result.r_t == (0.0,)


def test_the_hold_window_must_move_forward() -> None:
    with pytest.raises(ValueError):
        basket_hold_ratio(["a"], {"a": _flat(1.0)}, WINDOW[1], WINDOW[1])


def test_coverage_unknown_and_definition_are_keyword_only_without_default() -> None:
    parameters = inspect.signature(basket_log_returns).parameters
    for name in ("coverage_unknown", "definition"):
        assert parameters[name].kind is inspect.Parameter.KEYWORD_ONLY
        assert parameters[name].default is inspect.Parameter.empty


def test_the_threshold_comes_from_the_definition() -> None:
    members = _members(10)
    series = {m: _flat(10.0) for m in members}
    del series[members[0]][WINDOW[1]]  # 9 / 10 valid on the first return day
    loose = basket_log_returns(
        members, series, WINDOW[:2], coverage_unknown=(), definition=DEFINITION
    )
    strict = basket_log_returns(
        members,
        series,
        WINDOW[:2],
        coverage_unknown=(),
        definition=make_definition(BASKET_MIN_MEMBER_WEIGHT=0.95),
    )
    assert loose.r_t == (0.0,)
    assert strict.r_t == (None,)
    lenient = basket_log_returns(
        members,
        series,
        WINDOW,
        coverage_unknown=members[:1],
        definition=make_definition(BASKET_MIN_MEMBER_WEIGHT=0.95),
    )
    # Retained 9 / 10 = 0.9 is below this definition's 0.95.
    assert lenient.missing_code == E_ADJ_COVERAGE


def test_prices_after_the_window_change_nothing() -> None:
    # FL-56 / qa low: no look-ahead past the window's last session.
    members = _members(10)
    series = {
        m: {d: 10.0 + i + 0.1 * j for j, d in enumerate(WINDOW)} for i, m in enumerate(members)
    }
    before = basket_log_returns(members, series, WINDOW, coverage_unknown=(), definition=DEFINITION)
    later = WINDOW[-1] + timedelta(days=1)
    spiked = {m: {**prices, later: 1e9} for m, prices in series.items()}
    after = basket_log_returns(members, spiked, WINDOW, coverage_unknown=(), definition=DEFINITION)
    assert after == before
    assert basket_hold_ratio(members, spiked, WINDOW[0], WINDOW[-1]) == basket_hold_ratio(
        members, series, WINDOW[0], WINDOW[-1]
    )


def test_one_of_ten_excluded_gives_no_code_at_the_ninety_percent_floor() -> None:
    # Risk R-2 cell, spelled out: 10 members, 1 excluded, BASKET_MIN_MEMBER_WEIGHT = 0.90.
    assert DEFINITION.BASKET_MIN_MEMBER_WEIGHT == 0.9
    members = _members(10)
    series = {m: _flat(10.0) for m in members}
    result = basket_log_returns(
        members, series, WINDOW, coverage_unknown=members[:1], definition=DEFINITION
    )
    assert result.missing_code is None
    assert result.r_t == (0.0, 0.0, 0.0)


# --- C-10 (a): registered versions never lower the basket weight -----------------------


def _version_key(version: str) -> tuple[int, int]:
    """``dirdef-vMAJOR.MINOR`` as numbers, so v1.10 sorts after v1.2."""
    major, minor = version.removeprefix("dirdef-v").split(".")
    return int(major), int(minor)


def _basket_weight_regressions(definitions: Iterable[DirectionDefinition]) -> list[str]:
    """Versions whose weight is below the frozen value (the first registered version's)."""
    ordered = sorted(definitions, key=lambda d: _version_key(d.definition_version))
    if not ordered:
        return []
    frozen = ordered[0].BASKET_MIN_MEMBER_WEIGHT
    return [d.definition_version for d in ordered if d.BASKET_MIN_MEMBER_WEIGHT < frozen]


def test_registered_versions_keep_the_basket_weight_at_or_above_the_frozen_value() -> None:
    # Runs on the empty registry today; live from the first registration.
    published = [entry.definition for entry in registry.PUBLISHED_DIRECTION_DEFINITIONS.values()]
    assert _basket_weight_regressions(published) == []


def test_the_basket_weight_regression_check_has_teeth() -> None:
    versions = [
        make_definition(definition_version="dirdef-v1.10", BASKET_MIN_MEMBER_WEIGHT=0.92),
        make_definition(definition_version="dirdef-v1.0", BASKET_MIN_MEMBER_WEIGHT=0.95),
        make_definition(definition_version="dirdef-v1.2", BASKET_MIN_MEMBER_WEIGHT=0.95),
        make_definition(definition_version="dirdef-v2.0", BASKET_MIN_MEMBER_WEIGHT=1.0),
    ]
    assert _basket_weight_regressions(versions) == ["dirdef-v1.10"]
    assert _basket_weight_regressions(versions[1:]) == []
    assert _basket_weight_regressions([]) == []


def test_the_versions_are_ordered_by_number_not_by_text() -> None:
    # qa F-2: numerically v1.2 < v1.10, so v1.2 (0.92) is the frozen value and v1.10
    # (0.95) is above it. Text order puts "dirdef-v1.10" first and would flag v1.2.
    versions = [
        make_definition(definition_version="dirdef-v1.10", BASKET_MIN_MEMBER_WEIGHT=0.95),
        make_definition(definition_version="dirdef-v1.2", BASKET_MIN_MEMBER_WEIGHT=0.92),
    ]
    assert _basket_weight_regressions(versions) == []

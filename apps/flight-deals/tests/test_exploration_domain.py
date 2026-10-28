"""Exploration domain: conditions, keys, month expansion, validation (FD-6, C-44)."""

from __future__ import annotations

import ast
from dataclasses import replace
from datetime import date
from pathlib import Path
from typing import Any

import pytest

from flight_deals.domain import models
from flight_deals.domain.dates import MAX_MONTH_CELLS, month_pairs, month_weeks
from flight_deals.domain.models import DatePair, ExplorationSpec, WatchSpec, search_for
from flight_deals.domain.validation import (
    ADULTS_RANGE,
    AIRLINES_TOO_MANY,
    DEP_HOUR_PAIR,
    MONTH_INVALID,
    TRIP_DAYS_NOT_INT,
    TRIP_DAYS_RANGE,
    TRIP_DAYS_REQUIRED,
    UNKNOWN_PLACE,
    exploration_months,
    month_range_error,
    unknown_airline,
    validate_exploration,
)

SRC = Path(__file__).resolve().parents[1] / "src" / "flight_deals"
TODAY = date(2026, 10, 29)

SPEC = ExplorationSpec(
    origin="TPE",
    destination="NRT",
    trip_type="round_trip",
    year=2026,
    month=12,
    trip_days=5,
    max_stops=1,
    adults=2,
    children=1,
    cabin="business",
    airlines=("CI", "BR"),
    dep_hour_from=6,
    dep_hour_to=12,
)


def raw(**overrides: Any) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "origin": "TPE",
        "destination": "NRT",
        "trip_type": "round_trip",
        "month": "2026-12",
        "trip_days": 5,
        "max_stops": "",
        "adults": 1,
        "children": 0,
        "cabin": "economy",
        "airlines": [],
        "dep_hour_from": None,
        "dep_hour_to": None,
    }
    payload.update(overrides)
    return payload


# ---- conditions protocol and search_for ---------------------------------------------


def test_search_conditions_protocol_lives_in_domain() -> None:
    assert hasattr(models, "SearchConditions")
    tree = ast.parse((SRC / "domain" / "models.py").read_text(encoding="utf-8"))
    names = {n.name for n in tree.body if isinstance(n, ast.ClassDef)}
    assert {"SearchConditions", "ExplorationSpec"} <= names


def test_equivalent_watch_and_exploration_share_cache_key() -> None:
    watch = WatchSpec(
        name="x",
        origin="TPE",
        destination="NRT",
        trip_type="round_trip",
        date_mode="fixed",
        depart_date=date(2026, 12, 10),
        return_date=date(2026, 12, 15),
        window_start=None,
        window_end=None,
        min_trip_days=None,
        max_trip_days=None,
        max_stops=1,
        budget_amount_minor=None,
        adults=2,
        children=1,
        cabin="business",
        airlines=("BR", "CI"),
        dep_hour_from=6,
        dep_hour_to=12,
    )
    pair = DatePair(date(2026, 12, 10), date(2026, 12, 15))
    from_watch = search_for(watch, pair, "TWD")
    from_exploration = search_for(SPEC, pair, "TWD")
    assert from_watch == from_exploration
    assert from_watch.cache_key() == from_exploration.cache_key()
    assert from_exploration.airlines == ("BR", "CI")  # sorted like a watch's


def test_flight_search_still_built_only_in_domain() -> None:
    hits = [
        p.relative_to(SRC).as_posix()
        for p in SRC.rglob("*.py")
        if "FlightSearch(" in p.read_text(encoding="utf-8")
    ]
    assert hits == ["domain/models.py"]


# ---- condition_key ----------------------------------------------------------------


def test_condition_key_prefix_and_unset_values() -> None:
    plain = ExplorationSpec("TPE", "NRT", "one_way", 2026, 12, None, None)
    assert plain.condition_key() == "v1|TPE|NRT|one_way|2026-12|-|-|1|0|economy|-|-|-|TWD"
    assert SPEC.condition_key().startswith("v1|")
    # max_stops 0 is a value, not "unset".
    assert replace(plain, max_stops=0).condition_key() != plain.condition_key()


def test_condition_key_ignores_airline_order() -> None:  # AC-Q5
    assert replace(SPEC, airlines=("BR", "CI")).condition_key() == SPEC.condition_key()
    assert replace(SPEC, airlines=("CI", "BR", "BR")).condition_key() == SPEC.condition_key()


@pytest.mark.parametrize(
    "change",
    [
        {"origin": "TSA"},
        {"destination": "KIX"},
        {"trip_type": "one_way", "trip_days": None},
        {"year": 2027},
        {"month": 11},
        {"trip_days": 6},
        {"max_stops": None},
        {"adults": 1},
        {"children": 0},
        {"cabin": "economy"},
        {"airlines": ("BR",)},
        {"dep_hour_from": 7},
        {"dep_hour_to": 13},
        {"currency": "JPY"},
    ],
)
def test_condition_key_changes_with_every_condition(change: dict[str, Any]) -> None:  # AC-Q6
    assert replace(SPEC, **change).condition_key() != SPEC.condition_key()


# ---- month_pairs / month_weeks ------------------------------------------------------


def test_month_pairs_current_month_skips_past_days() -> None:  # AC-I6
    spec = replace(SPEC, year=2026, month=10)
    pairs = month_pairs(spec, TODAY)
    assert [p.depart.day for p in pairs] == [29, 30, 31]
    assert pairs[0].return_date == date(2026, 11, 3)  # may cross into next month


def test_month_pairs_full_month_and_year_crossing() -> None:  # AC-I7
    pairs = month_pairs(SPEC, TODAY)
    assert len(pairs) == 31 == MAX_MONTH_CELLS
    assert pairs[-1] == DatePair(date(2026, 12, 31), date(2027, 1, 5))


def test_month_pairs_leap_february() -> None:
    feb = replace(SPEC, year=2028, month=2, trip_days=1)
    assert len(month_pairs(feb, date(2027, 12, 1))) == 29
    assert len(month_pairs(replace(feb, year=2027), date(2026, 12, 1))) == 28


def test_month_pairs_one_way_has_no_return() -> None:  # AC-I5
    one_way = replace(SPEC, trip_type="one_way", trip_days=None)
    pairs = month_pairs(one_way, TODAY)
    assert len(pairs) == 31 and all(p.return_date is None for p in pairs)


def test_month_pairs_drop_dates_past_the_horizon() -> None:  # AC-I8
    # Today + 365 days is 2027-10-29: September 2027 returns may still fit, October not.
    late = replace(SPEC, year=2027, month=10, trip_days=5)
    pairs = month_pairs(late, TODAY)
    assert pairs and pairs[-1].return_date == date(2027, 10, 29)
    assert [p.depart.day for p in pairs] == list(range(1, 25))


def test_month_weeks_start_on_monday_and_pad_with_none() -> None:
    weeks = month_weeks(2026, 11)  # 2026-11-01 is a Sunday
    assert weeks[0] == [None] * 6 + [date(2026, 11, 1)]
    assert all(len(w) == 7 for w in weeks)
    days = [d for w in weeks for d in w if d is not None]
    assert days[0] == date(2026, 11, 1) and days[-1] == date(2026, 11, 30) and len(days) == 30
    assert weeks[-1][0] == date(2026, 11, 30) and weeks[-1][1:] == [None] * 6


# ---- validate_exploration -----------------------------------------------------------


def test_valid_input_builds_spec() -> None:
    outcome = validate_exploration(raw(airlines=["CI", "BR"], max_stops="0"), TODAY)
    assert outcome.errors == {}
    spec = outcome.spec
    assert spec is not None
    assert (spec.year, spec.month, spec.trip_days, spec.max_stops) == (2026, 12, 5, 0)
    assert spec.airlines == ("BR", "CI")


def test_month_choices_and_bounds() -> None:  # AC-I3 (12 months, ADR Decision 2)
    months = exploration_months(TODAY)
    assert months[0] == (2026, 10) and months[-1] == (2027, 9) and len(months) == 12
    for good in ("2026-10", "2027-09"):
        assert validate_exploration(raw(month=good), TODAY).errors == {}, good
    for bad in ("2026-09", "2027-10", "2027-11"):
        assert validate_exploration(raw(month=bad), TODAY).errors == {
            "month": month_range_error(TODAY)
        }, bad
    assert month_range_error(TODAY) == "月份須介於 2026-10 到 2027-09"
    for bad in ("2026-13", "2026-1", "2026/12", "", "abcd-ef", "2026-00"):
        assert validate_exploration(raw(month=bad), TODAY).errors == {"month": MONTH_INVALID}


@pytest.mark.parametrize(
    "overrides,field,message",
    [
        ({"destination": ""}, "destination", "請填寫目的地"),
        ({"destination": "TPE"}, "destination", "出發地與目的地不可相同"),
        ({"destination": "ZZZ"}, "destination", UNKNOWN_PLACE),
        ({"trip_days": ""}, "trip_days", TRIP_DAYS_REQUIRED),
        ({"trip_days": None}, "trip_days", TRIP_DAYS_REQUIRED),
        ({"trip_days": 0}, "trip_days", TRIP_DAYS_RANGE),
        ({"trip_days": 31}, "trip_days", TRIP_DAYS_RANGE),
        ({"trip_days": "abc"}, "trip_days", TRIP_DAYS_NOT_INT),
        ({"adults": 10}, "adults", ADULTS_RANGE),
        ({"airlines": ["ZZ"]}, "airlines", unknown_airline("ZZ")),
        ({"airlines": ["BR", "CI", "JX", "IT", "JL", "NH"]}, "airlines", AIRLINES_TOO_MANY),
        ({"dep_hour_from": 6}, "dep_hour_to", DEP_HOUR_PAIR),
        ({"trip_type": "multi"}, "trip_type", "行程型態不正確"),
        ({"max_stops": 3}, "max_stops", "轉機次數上限須介於 0 到 2，或留空表示不限"),
    ],
)
def test_invalid_inputs_have_zh_messages(
    overrides: dict[str, Any], field: str, message: str
) -> None:  # AC-I4
    outcome = validate_exploration(raw(**overrides), TODAY)
    assert outcome.spec is None and outcome.errors.get(field) == message


def test_trip_days_bounds_accept_1_and_30() -> None:
    for days in (1, 30, "7"):
        assert validate_exploration(raw(trip_days=days), TODAY).errors == {}, days


def test_one_way_ignores_trip_days() -> None:  # FR-I4
    outcome = validate_exploration(raw(trip_type="one_way", trip_days="abc"), TODAY)
    assert outcome.spec is not None and outcome.spec.trip_days is None

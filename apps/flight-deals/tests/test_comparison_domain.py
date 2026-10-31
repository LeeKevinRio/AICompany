"""Comparison domain types and input validation (ADR-0002 FD-9 Decision 2, C-62)."""

from __future__ import annotations

from datetime import date, timedelta
from pathlib import Path
from typing import Any

import pytest

from flight_deals.domain.models import (
    ComparisonSpec,
    ComparisonTarget,
    DatePair,
    ExplorationSpec,
    WatchSpec,
    search_for,
)
from flight_deals.domain.validation import (
    MAX_DESTINATIONS,
    MIN_DESTINATIONS,
    validate_comparison,
)

SRC = Path(__file__).resolve().parents[1] / "src" / "flight_deals"
TODAY = date(2026, 10, 25)
BASE: dict[str, Any] = {
    "origin": "TPE",
    "destinations": ["NRT", "OSA", "SEL"],
    "trip_type": "round_trip",
    "date_input": "fixed",
    "depart_date": "2026-12-10",
    "return_date": "2026-12-15",
    "trip_days": None,
    "max_stops": "",
    "cabin": "economy",
}


def spec(**overrides: Any) -> ComparisonSpec:
    outcome = validate_comparison({**BASE, **overrides}, TODAY)
    assert outcome.spec is not None, outcome.errors
    return outcome.spec


def errors(**overrides: Any) -> dict[str, str]:
    outcome = validate_comparison({**BASE, **overrides}, TODAY)
    assert outcome.spec is None
    return outcome.errors


# ---- types and keys ----------------------------------------------------------------


def test_contract_shape() -> None:
    s = spec()
    assert s.destinations == ("NRT", "OSA", "SEL")
    assert s.pair == DatePair(date(2026, 12, 10), date(2026, 12, 15))
    assert (s.adults, s.children, s.cabin, s.currency) == (1, 0, "economy", "TWD")
    target = s.target("OSA")
    assert isinstance(target, ComparisonTarget)
    assert target.destination == "OSA" and target.airlines == ()
    assert target.dep_hour_from is None and target.dep_hour_to is None
    assert (target.adults, target.children) == (1, 0)
    assert (MIN_DESTINATIONS, MAX_DESTINATIONS) == (2, 8)


def test_condition_key_golden_and_properties() -> None:
    key = spec(destinations=["OSA", "BKK", "NRT"]).condition_key()
    assert key == "cmp1|TPE|BKK,NRT,OSA|round_trip|2026-12-10|2026-12-15|-|1|0|economy|TWD"
    assert key.startswith("cmp1|") and "|1|0|" in key
    # Order of destinations does not matter.
    assert spec(destinations=["NRT", "OSA", "BKK"]).condition_key() == key
    # A stay length equal to the fixed return date is the same key.
    stay = spec(destinations=["BKK", "NRT", "OSA"], date_input="stay", trip_days=5)
    assert stay.condition_key() == key
    one_way = spec(trip_type="one_way").condition_key()
    assert "|one_way|2026-12-10|-|" in one_way


@pytest.mark.parametrize(
    "change",
    [
        {"origin": "KHH"},
        {"destinations": ["NRT", "OSA", "BKK", "SEL"]},
        {"trip_type": "one_way"},
        {"depart_date": "2026-12-11"},
        {"return_date": "2026-12-16"},
        {"max_stops": "0"},
        {"cabin": "business"},
    ],
)
def test_any_condition_change_changes_the_key(change: dict[str, Any]) -> None:
    assert spec(**change).condition_key() != spec().condition_key()


def test_exploration_key_golden_unchanged() -> None:  # C-62
    exploration = ExplorationSpec("TPE", "NRT", "round_trip", 2026, 12, 5, None)
    assert exploration.condition_key() == "v1|TPE|NRT|round_trip|2026-12|5|-|1|0|economy|-|-|-|TWD"


def test_target_cache_key_equals_watch() -> None:  # C-62
    s = spec(max_stops="1", cabin="business")
    watch = WatchSpec(
        name="x",
        origin="TPE",
        destination="OSA",
        trip_type="round_trip",
        date_mode="fixed",
        depart_date=s.depart_date,
        return_date=s.return_date,
        window_start=None,
        window_end=None,
        min_trip_days=None,
        max_trip_days=None,
        max_stops=1,
        budget_amount_minor=None,
        cabin="business",
    )
    ours = search_for(s.target("OSA"), s.pair, s.currency)
    theirs = search_for(watch, s.pair, watch.currency)
    assert ours.cache_key() == theirs.cache_key()


def test_flight_search_built_only_in_domain() -> None:  # C-62
    hits = [
        p.relative_to(SRC).as_posix()
        for p in SRC.rglob("*.py")
        if "FlightSearch(" in p.read_text(encoding="utf-8")
    ]
    assert hits and all(h.startswith("domain/") for h in hits), hits


# ---- validation: 422 matrix ---------------------------------------------------------


@pytest.mark.parametrize(
    "change,key",
    [
        ({"destinations": "NRT,OSA"}, "destinations"),
        ({"destinations": None}, "destinations"),
        ({"destinations": ["NRT", 5]}, "destinations"),
        ({"destinations": ["NRT", "  "]}, "destinations"),
        ({"destinations": ["NRT"]}, "destinations"),
        (
            {"destinations": ["NRT", "OSA", "SEL", "BKK", "SIN", "HKG", "MNL", "CTS", "OKA"]},
            "destinations",
        ),
        ({"destinations": ["NRT", "OSA", "nrt"]}, "destinations"),
        ({"destinations": ["TYO", "NRT"]}, "destinations"),
        ({"destinations": ["NRT", "TYO"]}, "destinations"),
        ({"destinations": ["TPE", "NRT"]}, "destinations"),
        ({"origin": "NRT", "destinations": ["HND", "OSA"]}, "destinations"),
        ({"origin": "NRT", "destinations": ["TYO", "OSA"]}, "destinations"),
        ({"destinations": ["XQZ", "NRT"]}, "destinations"),
        ({"destinations": ["SPK", "NRT"]}, "destinations"),
        ({"origin": ""}, "origin"),
        ({"origin": "XQZ"}, "origin"),
        ({"depart_date": "2026-10-24"}, "depart_date"),
        ({"depart_date": (TODAY + timedelta(days=366)).isoformat()}, "depart_date"),
        ({"depart_date": "2026-1-5"}, "depart_date"),
        ({"depart_date": ""}, "depart_date"),
        ({"return_date": "2026-12-09"}, "return_date"),
        ({"return_date": (TODAY + timedelta(days=366)).isoformat()}, "return_date"),
        ({"return_date": None}, "return_date"),
        ({"date_input": "stay", "trip_days": 0}, "trip_days"),
        ({"date_input": "stay", "trip_days": 31}, "trip_days"),
        ({"date_input": "stay", "trip_days": "abc"}, "trip_days"),
        ({"date_input": "stay", "trip_days": None}, "trip_days"),
        (
            {
                "date_input": "stay",
                "depart_date": (TODAY + timedelta(days=360)).isoformat(),
                "trip_days": 6,
            },
            "trip_days",
        ),
        ({"date_input": "month"}, "date_input"),
        ({"trip_type": "multi"}, "trip_type"),
        ({"max_stops": "3"}, "max_stops"),
        ({"cabin": "luxury"}, "cabin"),
    ],
)
def test_validation_rejects(change: dict[str, Any], key: str) -> None:  # C-62, AC-C4
    found = errors(**change)
    assert key in found and found[key], found


def test_destination_messages_name_the_codes() -> None:
    assert "TYO" in errors(destinations=["TYO", "NRT"])["destinations"]
    assert "NRT" in errors(destinations=["NRT", "OSA", "NRT"])["destinations"]
    assert "XQZ" in errors(destinations=["XQZ", "NRT"])["destinations"]


@pytest.mark.parametrize(
    "change",
    [
        {"destinations": ["NRT", "HND"]},  # two airports of one city
        {"destinations": ["NRT", "OSA", "SEL", "BKK", "SIN", "HKG", "MNL", "OKA"]},  # 8
        {"depart_date": TODAY.isoformat(), "return_date": TODAY.isoformat()},
        {
            "depart_date": (TODAY + timedelta(days=365)).isoformat(),
            "return_date": (TODAY + timedelta(days=365)).isoformat(),
        },
        {"return_date": "2026-12-10"},  # same day as the departure
        {"trip_type": "one_way", "return_date": "2026-01-01", "trip_days": 99},
        {"trip_type": "one_way", "date_input": "stay", "trip_days": "abc"},
        {"adults": 3, "children": 2, "airlines": ["BR"], "dep_hour_from": 6},
        {"date_input": "stay", "trip_days": 30, "return_date": "garbage"},
    ],
)
def test_validation_accepts(change: dict[str, Any]) -> None:  # C-62
    s = spec(**change)
    assert (s.adults, s.children) == (1, 0)
    if s.trip_type == "one_way":
        assert s.return_date is None


def test_ignored_fields_never_reach_the_spec() -> None:  # AC-C6
    s = spec(adults=3, children=2, airlines=["BR", "CI"], dep_hour_from=6, dep_hour_to=12)
    target = s.target("NRT")
    assert (target.adults, target.children, target.airlines) == (1, 0, ())
    assert s.condition_key() == spec().condition_key()


def test_stay_sets_the_return_date() -> None:  # AC-C5
    s = spec(date_input="stay", trip_days=5, return_date="")
    assert s.return_date == date(2026, 12, 15)


def test_codes_are_upper_cased_and_order_kept() -> None:
    assert spec(destinations=[" sel", "nrt "]).destinations == ("SEL", "NRT")

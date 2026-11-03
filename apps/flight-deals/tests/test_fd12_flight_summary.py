"""Shared flight wording (ADR-0002 FD-12, C-98; PRD FR-2 to FR-4)."""

from __future__ import annotations

import ast
import re
from dataclasses import dataclass, fields
from pathlib import Path

import pytest

from flight_deals.domain.flight_summary import (
    FlightSummary,
    day_offset_label,
    flight_summary,
    format_flight_numbers,
    layover_codes,
)
from flight_deals.domain.messages import BANNED_PHRASES, all_static_texts

SRC = Path(__file__).resolve().parents[1] / "src" / "flight_deals"


@dataclass(frozen=True)
class Facts:
    carrier: str | None = "長榮航空"
    stops: int | None = 0
    depart_time: str | None = "06:50"
    duration_minutes: int | None = 220
    flight_numbers: str | None = "BR184"
    arrive_time: str | None = "10:30"
    arrive_day_offset: int | None = 0
    route_airports: str | None = "TPE,NRT"


OLD_ROW = Facts(flight_numbers=None, arrive_time=None, arrive_day_offset=None, route_airports=None)


def summary(facts: Facts, trip: str = "round_trip") -> FlightSummary:
    return flight_summary(facts, trip_type=trip)  # type: ignore[arg-type]


def no_none(value: FlightSummary) -> None:
    for field in fields(value):
        text = getattr(value, field.name)
        assert text is None or "None" not in str(text), field.name


# ---- FR-2 Given / When / Then -------------------------------------------------------------------


def test_nonstop_same_day() -> None:
    s = summary(Facts())
    assert (s.airline, s.flight_numbers, s.times, s.stops) == (
        "長榮航空",
        "BR 184",
        "06:50 → 10:30",
        "直飛",
    )
    assert s.day_offset is None and "+" not in s.times and "−" not in s.times
    assert s.leg_label == "去程" and s.is_outbound_only and s.detailed
    assert s.depart_airport == "TPE" and s.arrive_airport == "NRT"
    assert s.duration == "3 小時 40 分" and s.stops_short == "直飛"
    assert s.sr_text == "去程，長榮航空 BR 184，06:50 出發，10:30 抵達，直飛"
    no_none(s)


def test_next_day_arrival() -> None:
    s = summary(Facts(depart_time="23:55", arrive_time="03:30", arrive_day_offset=1))
    assert s.arrive_time == "03:30" and s.day_offset == "+1"
    assert s.times == "23:55 → 03:30+1" and s.times_compact == "23:55→03:30+1"
    assert s.day_offset_sr == "（隔天）" and "03:30 抵達（隔天）" in s.sr_text


def test_previous_day_arrival_uses_the_minus_sign() -> None:
    s = summary(Facts(arrive_day_offset=-1))
    assert s.day_offset == "−1" and s.times.endswith("10:30−1")
    assert "-" not in s.times  # never the ASCII hyphen
    assert day_offset_label(-1) == "−1" and day_offset_label(2) == "+2"
    assert day_offset_label(0) is None and day_offset_label(None) is None


def test_one_stop_shows_the_layover_and_both_flights() -> None:
    s = summary(Facts(stops=1, flight_numbers="BR198,JL99", route_airports="TPE,HKG,NRT"))
    assert s.stops == "轉機 1 次（HKG）" and s.stops_short == "轉機 1 次"
    assert s.flight_numbers == "BR 198 → JL 99"


def test_two_stops_list_layovers_with_ideographic_comma() -> None:
    s = summary(Facts(stops=2, route_airports="TPE,HKG,ICN,NRT"))
    assert s.stops == "轉機 2 次（HKG、ICN）"


def test_two_airlines_are_listed_once_each() -> None:
    s = summary(Facts(carrier="長榮航空、日本航空", flight_numbers="BR198,JL99", stops=1))
    assert s.airline == "長榮航空、日本航空" and s.flight_numbers == "BR 198 → JL 99"


def test_same_airline_twice_is_listed_once() -> None:
    s = summary(Facts(carrier="長榮航空、長榮航空", flight_numbers="BR198,BR2196", stops=1))
    assert s.airline == "長榮航空"


def test_airline_from_codes_when_carrier_missing() -> None:
    s = summary(Facts(carrier=None, flight_numbers="BR198,JL99,XX1", stops=2))
    assert s.airline == "長榮航空、日本航空、XX"
    assert summary(Facts(carrier=None, flight_numbers=None)).airline == "—"


def test_arrival_without_day_offset_shows_dash() -> None:
    s = summary(Facts(arrive_time="10:30", arrive_day_offset=None))
    assert s.arrive_time == "—" and s.times == "06:50 → —" and s.day_offset is None


def test_unknown_fields_show_dash_never_none() -> None:
    blank = Facts(None, None, None, None, None, None, None, None)
    s = summary(blank, "one_way")
    assert (s.airline, s.flight_numbers, s.depart_time, s.arrive_time, s.stops) == (
        "—",
        "—",
        "—",
        "—",
        "—",
    )
    assert s.times == "— → —" and s.stops_short is None and s.duration is None
    assert not s.detailed and s.sr_text == "航班資訊未提供"
    no_none(s)


def test_old_rows_keep_carrier_and_departure() -> None:  # FR-3
    s = summary(OLD_ROW)
    assert s.airline == "長榮航空" and s.depart_time == "06:50"
    assert s.flight_numbers == "—" and s.arrive_time == "—" and s.stops == "直飛"
    assert not s.detailed and s.depart_airport is None
    no_none(s)


def test_stops_without_route_have_no_brackets() -> None:
    s = summary(Facts(stops=1, route_airports=None))
    assert s.stops == "轉機 1 次"
    s = summary(Facts(stops=2, route_airports="TPE,HKG,NRT"))  # count mismatch
    assert s.stops == "轉機 2 次"


def test_one_way_has_no_outbound_label() -> None:  # FR-4
    s = summary(Facts(), "one_way")
    assert s.leg_label is None and not s.is_outbound_only and "去程" not in s.sr_text


@pytest.mark.parametrize(
    "canonical,expected",
    [
        ("BR184", "BR 184"),
        ("BR198,JL99", "BR 198 → JL 99"),
        ("7C1101", "7C 1101"),
        (None, None),
        ("", None),
        ("br184", None),
        ("BR 184", None),
        ("BR184,", None),
    ],
)
def test_format_flight_numbers(canonical: str | None, expected: str | None) -> None:
    assert format_flight_numbers(canonical) == expected


def test_layover_codes() -> None:
    assert layover_codes("TPE,NRT") == ()
    assert layover_codes("TPE,HKG,NRT") == ("HKG",)
    assert layover_codes(None) is None and layover_codes("TPE") is None
    assert layover_codes("tpe,nrt") is None


# ---- module rules (C-98) ------------------------------------------------------------------


def test_module_imports_stdlib_and_domain_only() -> None:
    tree = ast.parse((SRC / "domain" / "flight_summary.py").read_text(encoding="utf-8"))
    names = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module:
            names.add(node.module)
        elif isinstance(node, ast.Import):
            names.update(a.name for a in node.names)
    project = {n for n in names if n.startswith("flight_deals")}
    assert project and all(n.startswith("flight_deals.domain.") for n in project), project
    assert names - project <= {"__future__", "re", "dataclasses", "typing"}


def test_flight_number_arrows_are_only_built_here() -> None:
    """No other module joins flight numbers with " → " (routes use f-strings)."""
    pattern = re.compile(r"\" → \"\.join|FLIGHT_SEPARATOR")
    hits = [
        p.relative_to(SRC).as_posix()
        for p in SRC.rglob("*.py")
        if pattern.search(p.read_text(encoding="utf-8"))
    ]
    assert hits == ["domain/flight_summary.py"]
    templates = " ".join(
        p.read_text(encoding="utf-8") for p in (SRC / "web" / "templates").glob("*.html")
    )
    assert "flight_numbers|" not in templates and '.split(",")' not in templates


def test_wording_is_policy_checked() -> None:
    texts = all_static_texts()
    assert "轉機 1 次（HKG）" in texts and "去程" in texts
    assert [t for t in texts for p in BANNED_PHRASES if p in t] == []


def test_duration_text_says_connections_exclude_the_layover() -> None:  # risk-gate M3
    direct = summary(Facts())
    assert direct.duration_text == "3 小時 40 分" == direct.duration
    one_stop = summary(Facts(stops=1, duration_minutes=270, route_airports="TPE,KIX,NRT"))
    assert one_stop.duration_text == "飛行 4 小時 30 分（不含轉機等候）"
    assert one_stop.duration == "4 小時 30 分"
    assert summary(Facts(stops=1, duration_minutes=None)).duration_text is None
    assert summary(Facts(stops=None)).duration_text == "3 小時 40 分"

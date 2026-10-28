"""FD-5 adapter: query options, departure time parsing and exact booking links
(ADR-0002 FD-5 Decisions 3, 4, 7; C-39, C-42)."""

from __future__ import annotations

import importlib.metadata
import json
from dataclasses import replace
from datetime import date
from pathlib import Path
from typing import Any

import pytest

from flight_deals.domain.models import DatePair, FlightSearch, search_for
from flight_deals.ports import BookingLinkBuilder, ParseStats
from flight_deals.sources import google_flights
from flight_deals.sources._support import Throttle, TTLCache
from flight_deals.sources.google_flights import (
    BOOKING_BASE_URL,
    SEAT_BY_CABIN,
    VERIFIED_FAST_FLIGHTS_VERSION,
    GoogleFlightsLinkBuilder,
    GoogleFlightsSource,
    build_query,
)
from flight_deals.sources.google_payload import depart_time_text, parse_payload
from tests.conftest import FIXTURES, FakeClock

SRC = Path(__file__).resolve().parents[1] / "src" / "flight_deals"
NRT_BR_FIXTURE = FIXTURES / "payload_TPE_NRT_BR_06_12.json"
SHA_FIXTURE = FIXTURES / "payload_TPE_SHA.json"

# C-42 golden search: one-way, 2 adults + 1 child, business, BR, outbound 06-12.
GOLDEN = FlightSearch(
    origin="TPE",
    destination="NRT",
    pair=DatePair(date(2026, 12, 10)),
    max_stops=None,
    adults=2,
    children=1,
    cabin="business",
    airlines=("BR",),
    dep_hour_from=6,
    dep_hour_to=12,
)
GOLDEN_URL = (
    "https://www.google.com/travel/flights/search"
    "?tfs=GiISCjIwMjYtMTItMTAyAkJSQAZIDGoFEgNUUEVyBRIDTlJUQgMBAQJIA5gBAg%3D%3D"
    "&hl=zh-TW&curr=TWD"
)
ROUND = replace(GOLDEN, pair=DatePair(date(2026, 12, 10), date(2026, 12, 15)), max_stops=1)


def load(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


# ---- build_query (C-39) -------------------------------------------------------------------


class _Recorder:
    def __init__(self) -> None:
        self.legs: list[dict[str, Any]] = []
        self.passengers: dict[str, Any] = {}
        self.create: dict[str, Any] = {}

    def flight_query(self, **kwargs: Any) -> dict[str, Any]:
        self.legs.append(kwargs)
        return kwargs

    def passengers_fn(self, **kwargs: Any) -> str:
        self.passengers = kwargs
        return "passengers"

    def create_query(self, **kwargs: Any) -> str:
        self.create = kwargs
        return "query"


@pytest.fixture
def recorder(monkeypatch: pytest.MonkeyPatch) -> _Recorder:
    rec = _Recorder()
    monkeypatch.setattr(google_flights, "FlightQuery", rec.flight_query)
    monkeypatch.setattr(google_flights, "Passengers", rec.passengers_fn)
    monkeypatch.setattr(google_flights, "create_query", rec.create_query)
    return rec


def test_build_query_passes_party_airlines_and_outbound_window(recorder: _Recorder) -> None:
    build_query(ROUND)
    assert recorder.passengers == {"adults": 2, "children": 1}
    assert recorder.create["passengers"] == "passengers"
    assert recorder.create["seat"] == "business" and recorder.create["trip"] == "round-trip"
    outbound, inbound = recorder.legs
    assert (outbound["from_airport"], inbound["from_airport"]) == ("TPE", "NRT")
    assert outbound["airlines"] == ["BR"] and inbound["airlines"] == ["BR"]  # both legs
    assert outbound["max_stops"] == 1 and inbound["max_stops"] == 1
    assert (outbound["earliest_departure_hour"], outbound["latest_departure_hour"]) == (6, 12)
    # The departure window is outbound only (Decision 3).
    assert (inbound["earliest_departure_hour"], inbound["latest_departure_hour"]) == (None, None)


def test_build_query_omits_empty_airlines_and_window(recorder: _Recorder) -> None:
    build_query(replace(ROUND, airlines=(), dep_hour_from=None, dep_hour_to=None))
    for leg in recorder.legs:
        assert leg["airlines"] is None
        assert leg["earliest_departure_hour"] is None and leg["latest_departure_hour"] is None


@pytest.mark.parametrize(
    "cabin,seat",
    [
        ("economy", "economy"),
        ("premium_economy", "premium-economy"),
        ("business", "business"),
        ("first", "first"),
    ],
)
def test_seat_mapping(recorder: _Recorder, cabin: Any, seat: str) -> None:
    build_query(replace(GOLDEN, cabin=cabin))
    assert recorder.create["seat"] == seat
    assert recorder.create["trip"] == "one-way"


def test_cabin_mapping_lives_only_in_the_adapter() -> None:  # C-39
    hits = [
        p.relative_to(SRC).as_posix()
        for p in SRC.rglob("*.py")
        if "premium-economy" in p.read_text(encoding="utf-8")
    ]
    assert hits == ["sources/google_flights.py"]
    assert set(SEAT_BY_CABIN) == {"economy", "premium_economy", "business", "first"}


def test_real_query_encodes_party_and_seat() -> None:
    query = build_query(ROUND)
    assert query.get_seat_type() == "business" and query.get_trip_type() == "round-trip"
    assert [int(p) for p in query.passengers] == [1, 1, 2]  # ADULT, ADULT, CHILD
    outbound, inbound = query.flight_data
    assert list(outbound.airlines) == ["BR"] and list(inbound.airlines) == ["BR"]
    assert outbound.earliest_departure_hour == 6 and outbound.latest_departure_hour == 12
    assert not inbound.HasField("earliest_departure_hour")
    assert not inbound.HasField("latest_departure_hour")


# ---- departure time (C-39) ------------------------------------------------------------------


@pytest.mark.parametrize(
    "value,expected",
    [
        ([7, 55], "07:55"),
        ([7], "07:00"),
        ([23, 5], "23:05"),
        ([], None),
        (None, None),
        ([24, 0], None),
        (["7", 55], None),
        ([7, 60], None),
        ([None, 31], None),
        ([True, 5], None),
        ([7, 55, 0], None),
        ("07:55", None),
    ],
)
def test_depart_time_shapes(value: Any, expected: str | None) -> None:
    assert depart_time_text(value) == expected


@pytest.mark.parametrize("value", [[7, 55], [7], [], None, [24, 0], ["7", 55]])
def test_odd_depart_time_never_changes_stats_or_status(clock: FakeClock, value: Any) -> None:
    payload = load(SHA_FIXTURE)
    payload[2][0][0][0][2][0][8] = value  # first segment of the cheapest itinerary
    page = parse_payload(payload)
    assert page.stats == ParseStats(
        itineraries=9, priced=7, unpriced=2, malformed=0, best=5, other=4
    )
    assert page.records[0]["depart_time"] == depart_time_text(value)


def test_sha_contract_and_depart_time_read() -> None:  # C-26 numbers (both sections)
    page = parse_payload(load(SHA_FIXTURE))
    assert page.stats == ParseStats(
        itineraries=9, priced=7, unpriced=2, malformed=0, best=5, other=4
    )
    assert [r["price"] for r in page.records] == [4633, 4633, 6221, 7833, 8821, 12655, 14763]
    assert [r["depart_time"] for r in page.records] == [
        "13:40", "15:30", "12:25", "17:35", "13:20", "17:05", "14:30",
    ]  # fmt: skip


def _source(html: str, clock: FakeClock) -> GoogleFlightsSource:
    return GoogleFlightsSource(
        timeout_seconds=5.0,
        max_attempts=1,
        backoff_base_seconds=0.0,
        throttle=Throttle(0.0, sleep=lambda _s: None),
        cache=TTLCache(600.0),
        fetch=lambda _search: html,
        clock=clock,
        sleep=lambda _s: None,
    )


def _page_html(payload: Any) -> str:
    data = json.dumps(payload, ensure_ascii=False)
    script = f"AF_initDataCallback({{key: 'ds:1', hash: '2', data:{data}, sideChannel: {{}}}});"
    return f'<html><body><script class="ds:1" nonce="n">{script}</script></body></html>'


def test_filtered_fixture_only_has_br_inside_the_window(clock: FakeClock) -> None:  # C-39
    """Recorded live 2026-10-28: TPE->NRT 2026-12-10 one-way, BR only, outbound 06-12.

    This recording has no "best flights" section at all (payload[2] is None); a later
    live check with the same query returned one (best 11,348 / 12,721 / 15,911), so the
    split between the sections varies per request.
    """
    payload = load(NRT_BR_FIXTURE)
    assert payload[2] is None
    page = parse_payload(payload)
    assert page.stats == ParseStats(itineraries=2, priced=2, unpriced=0, malformed=0, other=2)
    assert all(r["type"] == "BR" and r["airlines"] == ["長榮航空"] for r in page.records)
    times = [r["depart_time"] for r in page.records]
    assert times == ["07:55", "08:50"]
    assert all("06:00" <= t <= "12:59" for t in times)
    result = _source(_page_html(payload), clock).search(GOLDEN)
    assert result.status == "ok"
    assert sorted(q.amount_minor for q in result.quotes) == [1591100, 1717200]
    assert {q.depart_time for q in result.quotes} == {"07:55", "08:50"}


def test_round_trip_payload_lists_outbound_flights_only() -> None:
    """Recorded round trip TPE<->NRT: every itinerary ends at NRT (no return segments)."""
    records = load(FIXTURES / "fixture_roundtrip_TPE_NRT.json")["flights"]
    assert records
    assert {r["flights"][-1]["to_airport"]["code"] for r in records} == {"NRT"}
    assert {r["flights"][0]["from_airport"]["code"] for r in records} == {"TPE"}


# ---- booking links (C-42) -------------------------------------------------------------------


@pytest.fixture
def no_network(monkeypatch: pytest.MonkeyPatch) -> None:
    def fail(*_args: Any, **_kwargs: Any) -> str:
        raise AssertionError("the link builder must not fetch anything")

    monkeypatch.setattr(google_flights, "fetch_flights_html", fail)
    monkeypatch.setattr(google_flights, "fetch_live", fail)


def test_link_builder_satisfies_the_port() -> None:
    builder: BookingLinkBuilder = GoogleFlightsLinkBuilder()
    assert builder.url(GOLDEN)


def test_golden_url(no_network: None) -> None:
    # Bound to the verified fast_flights release: on upgrade, re-check this URL in a
    # browser and update it together with VERIFIED_FAST_FLIGHTS_VERSION.
    assert importlib.metadata.version("fast-flights") == VERIFIED_FAST_FLIGHTS_VERSION
    url = GoogleFlightsLinkBuilder().url(GOLDEN)
    assert url == GOLDEN_URL
    assert url is not None and url.startswith(BOOKING_BASE_URL + "?tfs=")


@pytest.mark.parametrize(
    "change",
    [
        {"adults": 3},
        {"children": 0},
        {"cabin": "first"},
        {"cabin": "premium_economy"},
        {"airlines": ("BR", "CI")},
        {"airlines": ()},
        {"dep_hour_from": 7},
        {"dep_hour_to": 13},
        {"dep_hour_from": None, "dep_hour_to": None},
        {"max_stops": 0},
        {"pair": DatePair(date(2026, 12, 10), date(2026, 12, 15))},
        {"pair": DatePair(date(2026, 12, 11))},
        {"destination": "HND"},
    ],
)
def test_every_field_changes_the_tfs(no_network: None, change: dict[str, Any]) -> None:
    builder = GoogleFlightsLinkBuilder()
    assert builder.url(replace(GOLDEN, **change)) != builder.url(GOLDEN)


def test_link_for_a_watch_matches_the_scan_query(no_network: None) -> None:
    from flight_deals.domain.validation import validate_watch_input

    outcome = validate_watch_input(
        {
            "destination": "NRT",
            "trip_type": "one_way",
            "depart_date": "2026-12-10",
            "budget": 40000,
            "adults": 2,
            "children": 1,
            "cabin": "business",
            "airlines": ["br"],
            "dep_hour_from": 6,
            "dep_hour_to": 12,
        },
        date(2026, 10, 25),
    )
    assert outcome.spec is not None, outcome.errors
    search = search_for(outcome.spec, DatePair(date(2026, 12, 10)), "TWD")
    assert search == GOLDEN
    assert GoogleFlightsLinkBuilder().url(search) == GOLDEN_URL

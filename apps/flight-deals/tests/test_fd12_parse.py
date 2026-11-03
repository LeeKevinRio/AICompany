"""FD-12 flight details: payload keys, derived quote fields and same-price tie-break
(ADR-0002 FD-12; C-94, C-97)."""

from __future__ import annotations

import copy
import json
import re
from collections.abc import Callable
from dataclasses import replace
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any

import pytest

from flight_deals.domain.models import FlightSearch, PriceQuote, quote_rank_key
from flight_deals.ports import ParseStats, SourceResult
from flight_deals.sources import google_payload
from flight_deals.sources._records import quotes_from_records
from flight_deals.sources.google_payload import depart_time_text, parse_payload
from tests.conftest import FIXTURES, Harness

SRC = Path(__file__).resolve().parents[1] / "src" / "flight_deals"
NRT_BR_FIXTURE = FIXTURES / "payload_TPE_NRT_BR_06_12.json"
SHA_FIXTURE = FIXTURES / "payload_TPE_SHA.json"
DEPART = date(2026, 12, 10)
FETCHED = datetime(2026, 10, 25, 4, 0, tzinfo=UTC)
SHA_STATS = ParseStats(itineraries=9, priced=7, unpriced=2, malformed=0, best=5, other=4)
NEW_FIELDS = ("flight_numbers", "arrive_time", "arrive_day_offset", "route_airports")
OLD_FIELDS = ("amount_minor", "carrier", "stops", "depart_time", "duration_minutes")


def load(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def quotes(payload: Any, *, depart: date = DEPART) -> list[PriceQuote]:
    page = parse_payload(payload)
    return quotes_from_records(
        page.records,
        source="google_flights",
        price_kind="live",
        currency="TWD",
        depart_date=depart,
        return_date=None,
        fetched_at=FETCHED,
    )


def first_other(payload: Any) -> list[Any]:
    """Segments of the first "other flights" itinerary."""
    segments: list[Any] = payload[3][0][0][0][2]
    return segments


def cheapest_best(payload: Any) -> list[Any]:
    """Segments of the first "best flights" itinerary (SHA: CZ 3088 -> CZ 3575)."""
    segments: list[Any] = payload[2][0][0][0][2]
    return segments


# ---- payload keys (C-94) ---------------------------------------------------------------------


def test_payload_flights_carry_seven_new_keys() -> None:
    page = parse_payload(load(NRT_BR_FIXTURE))
    flight = page.records[0]["flights"][0]
    assert flight == {
        "duration": 185,
        "code": "BR",
        "number": "184",
        "from": "TPE",
        "to": "NRT",
        "arrive_time": "12:00",
        "depart_date": "2026-12-10",
        "arrive_date": "2026-12-10",
    }


@pytest.mark.parametrize(
    "value,expected",
    [
        ([2026, 12, 10], "2026-12-10"),
        ([2026, 2, 30], None),
        ([2026, 12], None),
        (["2026", 12, 10], None),
        ([True, 12, 10], None),
        (None, None),
        ("2026-12-10", None),
    ],
)
def test_local_date_shapes(value: Any, expected: str | None) -> None:
    assert google_payload.local_date_text(value) == expected


def test_payload_parser_stays_stdlib_only() -> None:
    source = (SRC / "sources" / "google_payload.py").read_text(encoding="utf-8")
    imported = {m.group(1) for m in re.finditer(r"^(?:from|import) (\S+)", source, re.M)}
    assert imported == {
        "__future__",
        "json",
        "dataclasses",
        "datetime",
        "html.parser",
        "typing",
        "flight_deals.ports",
    }


# ---- derived fields on the recorded fixtures (C-94) -------------------------------------------


def test_br184_fixture_derives_all_four_fields() -> None:
    br = quotes(load(NRT_BR_FIXTURE))[0]
    assert br.amount_minor == 1591100
    assert br.flight_numbers == "BR184"
    assert br.arrive_time == "12:00"
    assert br.arrive_day_offset == 0
    assert br.route_airports == "TPE,NRT"
    assert br.depart_time == "07:55"
    assert br.stops == 0 and br.duration_minutes == 185


def test_sha_fixture_cheapest_and_c39_numbers_unchanged() -> None:
    payload = load(SHA_FIXTURE)
    assert parse_payload(payload).stats == SHA_STATS
    found = quotes(payload)
    assert sorted(q.amount_minor for q in found) == [
        463300, 463300, 622100, 783300, 882100, 1265500, 1476300,
    ]  # fmt: skip
    cheapest = min(found, key=quote_rank_key)
    assert cheapest.amount_minor == 463300
    assert cheapest.route_airports == "TPE,SZX,SHA"
    assert cheapest.flight_numbers == "CZ3088,CZ3575"
    assert cheapest.depart_time == "13:40" and cheapest.arrive_time == "21:15"
    assert cheapest.arrive_day_offset == 0


def test_airport_change_at_connection_leaves_route_unknown() -> None:
    """Recorded SHA itinerary OZ 714 -> KE 2057 lands at ICN and leaves from GMP."""
    oz = next(q for q in quotes(load(SHA_FIXTURE)) if q.amount_minor == 1265500)
    assert oz.route_airports is None
    assert oz.flight_numbers == "OZ714,KE2057"
    # Next-day connection: arrival date 12-11 against departure 12-10.
    assert oz.arrive_time == "09:45" and oz.arrive_day_offset == 1


@pytest.mark.parametrize("path", [NRT_BR_FIXTURE, SHA_FIXTURE])
def test_arrival_matches_itinerary_info_arrival(path: Path) -> None:
    """Cross-check: the last segment's [10] equals the itinerary's own info[8]."""
    payload = load(path)
    page = parse_payload(payload)
    expected: dict[str, str | None] = {}
    for section in (payload[2], payload[3]):
        if not section or not section[0]:
            continue
        for itinerary in section[0]:
            if google_payload.classify_itinerary(itinerary) == "priced":
                key = google_payload.itinerary_key(itinerary)
                assert key is not None
                expected[key] = depart_time_text(itinerary[0][8])
    assert len(expected) == len(page.records)
    assert sorted(str(v) for v in expected.values()) == sorted(
        str(r["flights"][-1]["arrive_time"]) for r in page.records
    )
    assert all(expected.values())


# ---- malformed details never change the price (C-94) -------------------------------------------

Mutation = Callable[[list[Any]], None]


def _set(index: int, value: Any) -> Mutation:
    def mutate(segs: list[Any]) -> None:
        segs[0][index] = value

    return mutate


def _set_flight(index: int, value: Any) -> Mutation:
    def mutate(segs: list[Any]) -> None:
        segs[0][22][index] = value

    return mutate


ARRIVAL = ("arrive_time", "arrive_day_offset")
ANOMALIES: list[tuple[str, Mutation, tuple[str, ...]]] = [
    ("seg22 None", _set(22, None), ("flight_numbers",)),
    ("seg22 not list", _set(22, "BR184"), ("flight_numbers",)),
    ("number 18A", _set_flight(1, "18A"), ("flight_numbers",)),
    ("number int 184", _set_flight(1, 184), ("flight_numbers",)),
    ("number 5 digits", _set_flight(1, "18400"), ("flight_numbers",)),
    ("code br", _set_flight(0, "br"), ("flight_numbers",)),
    ("code 3 letters", _set_flight(0, "EVA"), ("flight_numbers",)),
    ("missing [21]", _set(21, None), ARRIVAL),
    ("[21] 2026-02-30", _set(21, [2026, 2, 30]), ARRIVAL),
    ("first[20] not query day", _set(20, [2026, 12, 9]), ARRIVAL),
    ("offset 4", _set(21, [2026, 12, 14]), ARRIVAL),
    ("offset -2", _set(21, [2026, 12, 8]), ARRIVAL),
    ("arrival [24, 0]", _set(10, [24, 0]), ARRIVAL),
    ("arrival missing", _set(10, None), ARRIVAL),
    ("airport nrt", _set(6, "nrt"), ("route_airports",)),
    ("airport NR", _set(6, "NR"), ("route_airports",)),
]


@pytest.mark.parametrize("name,mutate,unknown", ANOMALIES, ids=[a[0] for a in ANOMALIES])
def test_anomaly_only_blanks_its_own_fields(
    name: str, mutate: Mutation, unknown: tuple[str, ...]
) -> None:
    clean = load(NRT_BR_FIXTURE)
    payload = copy.deepcopy(clean)
    mutate(first_other(payload))
    before, after = quotes(clean)[0], quotes(payload)[0]
    assert parse_payload(payload).stats == parse_payload(clean).stats
    for field in OLD_FIELDS:
        assert getattr(after, field) == getattr(before, field), field
    for field in NEW_FIELDS:
        if field in unknown:
            assert getattr(after, field) is None, field
        else:
            assert getattr(after, field) == getattr(before, field), field


def test_offset_minus_one_is_kept() -> None:
    payload = load(NRT_BR_FIXTURE)
    first_other(payload)[0][21] = [2026, 12, 9]
    q = quotes(payload)[0]
    assert q.arrive_time == "12:00" and q.arrive_day_offset == -1


def test_seven_segments_have_no_flight_numbers_or_route() -> None:
    payload = load(NRT_BR_FIXTURE)
    segs = first_other(payload)
    base = segs[0]
    chain = ["TPE", "HKG", "BKK", "SIN", "KUL", "MNL", "ICN", "NRT"]
    segs[:] = []
    for i in range(7):
        seg = copy.deepcopy(base)
        seg[3], seg[6] = chain[i], chain[i + 1]
        seg[22] = ["BR", str(100 + i), None, "長榮航空"]
        segs.append(seg)
    q = quotes(payload)[0]
    assert q.flight_numbers is None and q.route_airports is None
    assert q.stops == 6 and q.amount_minor == 1591100


def test_six_segments_are_the_limit() -> None:
    payload = load(NRT_BR_FIXTURE)
    segs = first_other(payload)
    base = segs[0]
    chain = ["TPE", "HKG", "BKK", "SIN", "KUL", "MNL", "NRT"]
    segs[:] = []
    for i in range(6):
        seg = copy.deepcopy(base)
        seg[3], seg[6] = chain[i], chain[i + 1]
        seg[22] = ["BR", str(1000 + i), None, "長榮航空"]
        segs.append(seg)
    q = quotes(payload)[0]
    assert q.flight_numbers == "BR1000,BR1001,BR1002,BR1003,BR1004,BR1005"
    assert q.route_airports == "TPE,HKG,BKK,SIN,KUL,MNL,NRT"


def test_partial_segment_details_are_all_or_nothing() -> None:
    payload = load(SHA_FIXTURE)
    cheapest_best(payload)[1][22] = None  # second segment loses its flight block
    q = next(q for q in quotes(payload) if q.depart_time == "13:40")
    assert q.flight_numbers is None
    assert q.route_airports == "TPE,SZX,SHA" and q.arrive_time == "21:15"


# ---- synthetic payloads (PRD common premise) ---------------------------------------------------


def _synthetic(legs: list[dict[str, Any]]) -> Any:
    payload = load(NRT_BR_FIXTURE)
    base = first_other(payload)[0]
    segs = []
    for leg in legs:
        seg = copy.deepcopy(base)
        seg[3], seg[6] = leg["from"], leg["to"]
        seg[8], seg[10] = leg["dep"], leg["arr"]
        seg[20] = leg.get("d20", [2026, 12, 10])
        seg[21] = leg.get("d21", [2026, 12, 10])
        seg[22] = leg.get("flight", ["BR", "184", None, "長榮航空"])
        segs.append(seg)
    first_other(payload)[:] = segs
    return payload


def test_synthetic_next_day_arrival() -> None:
    payload = _synthetic(
        [{"from": "TPE", "to": "NRT", "dep": [23, 55], "arr": [3, 30], "d21": [2026, 12, 11]}]
    )
    q = quotes(payload)[0]
    assert (q.depart_time, q.arrive_time, q.arrive_day_offset) == ("23:55", "03:30", 1)


def test_synthetic_one_stop_two_airlines() -> None:
    payload = _synthetic(
        [
            {"from": "TPE", "to": "HKG", "dep": [7, 0], "arr": [9],
             "flight": ["BR", "198", None, "長榮航空"]},
            {"from": "HKG", "to": "NRT", "dep": [11], "arr": [16, 5],
             "flight": ["JL", "99", None, "日本航空"]},
        ]
    )  # fmt: skip
    q = quotes(payload)[0]
    assert q.flight_numbers == "BR198,JL99"
    assert q.route_airports == "TPE,HKG,NRT"
    assert q.stops == 1 and q.arrive_time == "16:05" and q.arrive_day_offset == 0


def test_synthetic_missing_flight_block_and_arrival_date() -> None:
    payload = _synthetic(
        [{"from": "TPE", "to": "NRT", "dep": [7, 55], "arr": [12], "flight": None, "d21": None}]
    )
    q = quotes(payload)[0]
    assert q.flight_numbers is None and q.arrive_time is None and q.arrive_day_offset is None
    assert q.route_airports == "TPE,NRT" and q.depart_time == "07:55"
    assert q.amount_minor == 1591100


def test_records_without_new_keys_stay_valid() -> None:
    """Fixture source records (pre-FD-12 shape) simply have no details."""
    record = {"price": 9000, "airlines": ["長榮航空"], "flights": [{"duration": 185}]}
    (q,) = quotes_from_records(
        [record],
        source="fixture",
        price_kind="live",
        currency="TWD",
        depart_date=DEPART,
        return_date=None,
        fetched_at=FETCHED,
    )
    assert all(getattr(q, f) is None for f in NEW_FIELDS)
    assert q.stops == 0 and q.duration_minutes == 185


# ---- same-price tie-break (C-97) ---------------------------------------------------------------


def _quote(amount: int = 9000, **kw: Any) -> PriceQuote:
    values: dict[str, Any] = {
        "source": "google_flights",
        "price_kind": "live",
        "depart_date": DEPART,
        "return_date": None,
        "amount_minor": amount,
        "currency": "TWD",
        "as_of": FETCHED,
        "as_of_basis": "fetch_time",
        "fetched_at": FETCHED,
        "carrier": "長榮航空",
        "stops": 0,
        "duration_minutes": 185,
    }
    values.update(kw)
    return PriceQuote(**values)


def test_rank_key_earlier_departure_wins() -> None:
    late, early = _quote(depart_time="08:10"), _quote(depart_time="07:55")
    assert min([late, early], key=quote_rank_key) is early


def test_rank_key_same_time_nonstop_wins() -> None:
    one_stop = _quote(depart_time="07:55", stops=1)
    nonstop = _quote(depart_time="07:55", stops=0)
    assert min([one_stop, nonstop], key=quote_rank_key) is nonstop


def test_rank_key_known_time_wins() -> None:
    unknown, known = _quote(depart_time=None), _quote(depart_time="23:00")
    assert min([unknown, known], key=quote_rank_key) is known


def test_rank_key_lower_price_wins() -> None:
    cheap, dear = _quote(8000, depart_time="23:00"), _quote(9000, depart_time="06:00")
    assert min([dear, cheap], key=quote_rank_key) is cheap


def test_rank_key_flight_numbers_then_payload_order() -> None:
    jl = _quote(depart_time="07:55", flight_numbers="JL99")
    br = _quote(depart_time="07:55", flight_numbers="BR184")
    assert min([jl, br], key=quote_rank_key) is br
    first, second = _quote(depart_time="07:55"), _quote(depart_time="07:55")
    assert min([first, second], key=quote_rank_key) is first


def test_rank_key_defined_once_and_used_by_both_mins() -> None:
    defs = [p for p in SRC.rglob("*.py") if "def quote_rank_key" in p.read_text(encoding="utf-8")]
    assert [p.name for p in defs] == ["models.py"]
    source = (SRC / "services" / "source_query.py").read_text(encoding="utf-8")
    assert source.count("key=quote_rank_key") == 2
    assert "key=lambda q: q.amount_minor" not in source


def _answer(harness: Harness, *made: PriceQuote) -> Callable[[FlightSearch], SourceResult]:
    def handler(query: FlightSearch) -> SourceResult:
        dated = tuple(
            replace(q, depart_date=query.pair.depart, return_date=query.pair.return_date)
            for q in made
        )
        return SourceResult("google_flights", "ok", harness.clock(), quotes=dated)

    return handler


def test_scan_stores_the_tie_break_winner_with_its_own_details(harness: Harness) -> None:
    """The stored row is one quote: price, time and flight number come from the same one."""
    late = _quote(
        900_000,
        depart_time="08:10",
        flight_numbers="JL99",
        arrive_time="12:30",
        arrive_day_offset=0,
        route_airports="TPE,NRT",
        carrier="日本航空",
    )
    early = _quote(
        900_000,
        depart_time="07:55",
        flight_numbers="BR184",
        arrive_time="12:00",
        arrive_day_offset=0,
        route_airports="TPE,NRT",
    )
    mismatch = _quote(800_000, depart_time="06:00", currency="JPY")
    harness.source.handler = _answer(harness, late, early, mismatch)
    watch_id = harness.create_watch()
    harness.scan(watch_id)
    (obs,) = harness.repo.observations_for_watch(watch_id)
    assert obs.amount_minor == 900_000 and obs.currency == "TWD"
    assert (obs.depart_time, obs.flight_numbers, obs.arrive_time) == ("07:55", "BR184", "12:00")
    assert obs.carrier == "長榮航空" and obs.route_airports == "TPE,NRT"
    assert obs.arrive_day_offset == 0


def test_currency_mismatch_fallback_uses_the_same_key(harness: Harness) -> None:
    a = _quote(800_000, depart_time="09:00", currency="JPY", flight_numbers="JL99")
    b = _quote(800_000, depart_time="06:30", currency="JPY", flight_numbers="NH1")
    harness.source.handler = _answer(harness, a, b)
    watch_id = harness.create_watch()
    harness.scan(watch_id)
    (obs,) = harness.repo.observations_for_watch(watch_id)
    assert obs.currency == "JPY" and obs.flight_numbers == "NH1" and obs.depart_time == "06:30"

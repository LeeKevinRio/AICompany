"""FD-5 trip options in the domain: model, validation, airline table, labels, messages
(ADR-0002 FD-5 Decisions 2, 5, 6, 8; C-38, C-40, C-41)."""

from __future__ import annotations

import re
import typing
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any

import pytest

from flight_deals.domain import airlines as airlines_module
from flight_deals.domain.airlines import AIRLINES, MAX_AIRLINES, airlines_label, lookup_airline
from flight_deals.domain.airports import PLACES, is_selectable, route_label
from flight_deals.domain.currency import major_to_minor
from flight_deals.domain.messages import (
    BANNED_PHRASES,
    DIGEST_MAX_CHARS,
    DIGEST_MAX_WATCH_LINES,
    DISCLAIMER,
    NO_PRICE_ALERT_NOTE,
    DigestRow,
    DigestSourceRow,
    all_static_texts,
    daily_digest_message,
    price_alert_message,
)
from flight_deals.domain.models import Cabin, DatePair, FlightSearch, WatchSpec, search_for
from flight_deals.domain.rules import Candidate, TriggeredItem, price_item_key, price_message_key
from flight_deals.domain.trip_labels import (
    BOOKING_FALLBACK_NOTE,
    cabin_label,
    conditions_label,
    dep_window_label,
    filter_line,
    pax_full_label,
    pax_label,
    static_texts,
    total_price_note,
)
from flight_deals.domain.validation import (
    ADULTS_NOT_INT,
    ADULTS_RANGE,
    ADULTS_REQUIRED,
    AIRLINES_INVALID,
    AIRLINES_TOO_MANY,
    CABIN_INVALID,
    CHILDREN_NOT_INT,
    CHILDREN_RANGE,
    DEP_HOUR_NOT_INT,
    DEP_HOUR_ORDER,
    DEP_HOUR_PAIR,
    DEP_HOUR_RANGE,
    PASSENGERS_TOTAL,
    ValidationOutcome,
    unknown_airline,
    validate_watch_input,
)
from flight_deals.notify.telegram import MAX_MESSAGE_LENGTH

TODAY = date(2026, 10, 25)
NOW = datetime(2026, 10, 25, 4, 0, tzinfo=UTC)
SRC = Path(__file__).resolve().parents[1] / "src" / "flight_deals"
BASE: dict[str, Any] = {
    "destination": "NRT",
    "trip_type": "round_trip",
    "date_mode": "fixed",
    "depart_date": "2026-12-10",
    "return_date": "2026-12-15",
    "budget": "40000",
}
# The 34 carriers named in PRD FR-A1.
PRD_AIRLINES = (
    "BR CI JX IT JL NH MM GK TR SQ CX UO KE OZ 7C LJ TG FD VJ VN MH AK PR 5J MU CZ CA MF "
    "UA DL EK QR TK QF"
).split()


def validate(existing: WatchSpec | None = None, **overrides: Any) -> ValidationOutcome:
    return validate_watch_input({**BASE, **overrides}, TODAY, existing)


def ok_spec(**overrides: Any) -> WatchSpec:
    outcome = validate(**overrides)
    assert outcome.spec is not None, outcome.errors
    return outcome.spec


# ---- model --------------------------------------------------------------------------


def test_watch_spec_fields_are_typed() -> None:  # C-38
    hints = typing.get_type_hints(WatchSpec)
    assert hints["cabin"] == Cabin
    assert typing.get_args(Cabin) == ("economy", "premium_economy", "business", "first")
    assert hints["airlines"] == tuple[str, ...]
    assert hints["adults"] is int and hints["children"] is int
    assert hints["dep_hour_from"] == int | None and hints["dep_hour_to"] == int | None


def test_defaults_mean_pre_fd5_watch() -> None:  # FR-C3, AC-P2
    spec = ok_spec()
    assert (spec.adults, spec.children, spec.cabin, spec.airlines) == (1, 0, "economy", ())
    assert (spec.dep_hour_from, spec.dep_hour_to) == (None, None)


def test_search_shape_has_the_six_new_fields_and_not_name_budget_notify() -> None:  # C-38
    spec = ok_spec()
    for field, value in (
        ("adults", 2),
        ("children", 1),
        ("cabin", "business"),
        ("airlines", ("BR",)),
        ("dep_hour_from", 6),
        ("dep_hour_to", 12),
    ):
        changed = WatchSpec(**{**spec.__dict__, field: value})
        assert changed.search_shape() != spec.search_shape(), field
    for field, value in (
        ("name", "other"),
        ("budget_amount_minor", 1),
        ("notify_on_new_low", False),
    ):
        changed = WatchSpec(**{**spec.__dict__, field: value})
        assert changed.search_shape() == spec.search_shape(), field
    a = WatchSpec(**{**spec.__dict__, "airlines": ("CI", "BR")})
    b = WatchSpec(**{**spec.__dict__, "airlines": ("BR", "CI")})
    assert a.search_shape() == b.search_shape()  # set semantics


def test_search_for_copies_every_option_and_cache_key_differs() -> None:  # C-38
    spec = ok_spec(
        adults=2,
        children=1,
        cabin="business",
        airlines=["CI", "BR"],
        dep_hour_from=6,
        dep_hour_to=12,
    )
    pair = DatePair(date(2026, 12, 10), date(2026, 12, 15))
    search = search_for(spec, pair, "TWD")
    assert (search.adults, search.children, search.cabin) == (2, 1, "business")
    assert search.airlines == ("BR", "CI")
    assert (search.dep_hour_from, search.dep_hour_to) == (6, 12)
    one = search_for(ok_spec(), pair, "TWD")
    two = search_for(ok_spec(adults=2), pair, "TWD")
    assert one.cache_key() != two.cache_key()  # parties never share a cache entry
    for field in ("children", "cabin", "airlines", "dep_hour_from", "dep_hour_to"):
        value: Any = {"children": 1, "cabin": "first", "airlines": ("BR",)}.get(field, 3)
        other = FlightSearch(**{**one.__dict__, field: value})
        assert other.cache_key() != one.cache_key(), field


def test_flight_search_is_only_built_in_domain() -> None:  # C-38
    hits = [
        p.relative_to(SRC).as_posix()
        for p in SRC.rglob("*.py")
        if "FlightSearch(" in p.read_text(encoding="utf-8")
    ]
    assert hits == ["domain/models.py"]


# ---- validation ----------------------------------------------------------------------


@pytest.mark.parametrize(
    "overrides,field,message",
    [
        ({"adults": 0}, "adults", ADULTS_RANGE),
        ({"adults": 10}, "adults", ADULTS_RANGE),
        ({"adults": "abc"}, "adults", ADULTS_NOT_INT),
        ({"adults": "1.5"}, "adults", ADULTS_NOT_INT),
        ({"adults": 1.5}, "adults", ADULTS_NOT_INT),
        ({"adults": True}, "adults", ADULTS_NOT_INT),
        ({"adults": ""}, "adults", ADULTS_REQUIRED),
        ({"children": -1}, "children", CHILDREN_RANGE),
        ({"children": 9}, "children", CHILDREN_RANGE),
        ({"children": 10}, "children", CHILDREN_RANGE),
        ({"children": "x"}, "children", CHILDREN_NOT_INT),
        ({"adults": 5, "children": 5}, "children", PASSENGERS_TOTAL),
        ({"adults": 9, "children": 1}, "children", PASSENGERS_TOTAL),
        ({"cabin": "first-class-xyz"}, "cabin", CABIN_INVALID),
        ({"cabin": ""}, "cabin", CABIN_INVALID),
        ({"cabin": "premium-economy"}, "cabin", CABIN_INVALID),
        ({"airlines": ["ZZ"]}, "airlines", unknown_airline("ZZ")),
        ({"airlines": "BR,QQ"}, "airlines", unknown_airline("QQ")),
        ({"airlines": ["BR", "CI", "JX", "IT", "JL", "NH"]}, "airlines", AIRLINES_TOO_MANY),
        ({"airlines": ["BRR"]}, "airlines", AIRLINES_INVALID),
        ({"airlines": [1]}, "airlines", AIRLINES_INVALID),
        ({"airlines": {"BR": 1}}, "airlines", AIRLINES_INVALID),
        ({"dep_hour_from": 6}, "dep_hour_to", DEP_HOUR_PAIR),
        ({"dep_hour_to": 12}, "dep_hour_from", DEP_HOUR_PAIR),
        ({"dep_hour_from": 6, "dep_hour_to": ""}, "dep_hour_to", DEP_HOUR_PAIR),
        ({"dep_hour_from": 8, "dep_hour_to": 8}, "dep_hour_to", DEP_HOUR_ORDER),
        ({"dep_hour_from": 12, "dep_hour_to": 6}, "dep_hour_to", DEP_HOUR_ORDER),
        ({"dep_hour_from": 24, "dep_hour_to": 23}, "dep_hour_from", DEP_HOUR_RANGE),
        ({"dep_hour_from": -1, "dep_hour_to": 6}, "dep_hour_from", DEP_HOUR_RANGE),
        ({"dep_hour_from": 6, "dep_hour_to": 7.5}, "dep_hour_to", DEP_HOUR_NOT_INT),
        ({"dep_hour_from": "早上", "dep_hour_to": 12}, "dep_hour_from", DEP_HOUR_NOT_INT),
    ],
)
def test_trip_option_errors(overrides: dict[str, Any], field: str, message: str) -> None:
    outcome = validate(**overrides)  # C-38, AC-P4, AC-A4, AC-A11
    assert outcome.spec is None
    assert outcome.errors.get(field) == message


def test_error_messages_are_traditional_chinese_and_factual() -> None:
    messages = [
        ADULTS_NOT_INT, ADULTS_RANGE, ADULTS_REQUIRED, AIRLINES_INVALID, AIRLINES_TOO_MANY,
        CABIN_INVALID, CHILDREN_NOT_INT, CHILDREN_RANGE, DEP_HOUR_NOT_INT, DEP_HOUR_ORDER,
        DEP_HOUR_PAIR, DEP_HOUR_RANGE, PASSENGERS_TOTAL, unknown_airline("ZZ"),
    ]  # fmt: skip
    for text in messages:
        assert re.search(r"[一-鿿]", text)
        assert not any(p in text for p in BANNED_PHRASES)
        assert "點前" not in text


@pytest.mark.parametrize(
    "overrides,expected",
    [
        ({"adults": 9, "children": 0}, (9, 0)),
        ({"adults": 1, "children": 8}, (1, 8)),
        ({"adults": "2", "children": "1"}, (2, 1)),
    ],
)
def test_passenger_boundaries_accepted(
    overrides: dict[str, Any], expected: tuple[int, int]
) -> None:  # AC-P5
    spec = ok_spec(**overrides)
    assert (spec.adults, spec.children) == expected


@pytest.mark.parametrize("cabin", ["economy", "premium_economy", "business", "first"])
def test_all_four_cabins_accepted(cabin: str) -> None:  # AC-P3
    assert ok_spec(cabin=cabin).cabin == cabin


def test_airlines_normalised() -> None:  # AC-A5, AC-A6
    assert ok_spec(airlines=["br"]).airlines == ("BR",)
    assert ok_spec(airlines=["BR", "br", " ci "]).airlines == ("BR", "CI")
    assert ok_spec(airlines="ci, br、jx").airlines == ("BR", "CI", "JX")  # no-JS text input
    assert ok_spec(airlines=["BR", "CI", "JX", "IT", "JL"]).airlines == (
        "BR", "CI", "IT", "JL", "JX",
    )  # fmt: skip
    assert ok_spec(airlines=[]).airlines == ()
    assert ok_spec(airlines="").airlines == ()
    assert ok_spec(airlines=None).airlines == ()


def test_unchanged_out_of_table_airline_is_exempt_on_edit() -> None:  # Decision 6
    legacy = WatchSpec(**{**ok_spec().__dict__, "airlines": ("ZZ",)})
    kept = validate(legacy, airlines=["ZZ", "BR"])
    assert kept.spec is not None and kept.spec.airlines == ("BR", "ZZ")
    changed = validate(legacy, airlines=["QQ"])
    assert changed.errors == {"airlines": unknown_airline("QQ")}
    assert validate(None, airlines=["ZZ"]).errors == {"airlines": unknown_airline("ZZ")}


def test_hours_accepted() -> None:  # AC-A9
    spec = ok_spec(dep_hour_from=6, dep_hour_to=12)
    assert (spec.dep_hour_from, spec.dep_hour_to) == (6, 12)
    spec = ok_spec(dep_hour_from="0", dep_hour_to="23")
    assert (spec.dep_hour_from, spec.dep_hour_to) == (0, 23)
    spec = ok_spec(dep_hour_from=None, dep_hour_to="")
    assert (spec.dep_hour_from, spec.dep_hour_to) == (None, None)


# ---- dedupe keys ----------------------------------------------------------------------


def test_dedupe_keys_carry_revision() -> None:  # C-38, Decision 8
    day = date(2026, 12, 10)
    assert price_item_key(3, 2, "live", day, None, 100) == "price:3:r2:live:2026-12-10:-:100"
    assert price_item_key(3, 1, "live", day, None, 100) != price_item_key(
        3, 2, "live", day, None, 100
    )
    item = TriggeredItem(_cand(100), ("below_budget",), None, "k")
    assert price_message_key(3, 2, "live", [item]).startswith("price:3:r2:live:")
    assert price_message_key(3, 1, "live", [item]) != price_message_key(3, 2, "live", [item])


# ---- airline table (C-41) --------------------------------------------------------------


def test_airline_table_rules() -> None:
    codes = [a.code for a in AIRLINES]
    assert 30 <= len(AIRLINES) <= 50
    assert len(set(codes)) == len(codes)
    for airline in AIRLINES:
        assert re.fullmatch(r"[A-Z0-9]{2}", airline.code), airline
        assert not airline.code.isdigit(), airline
        assert 1 <= len(airline.display_name) <= 6, airline
        assert airline.zh_name and airline.en_name and airline.verified_note
    assert set(PRD_AIRLINES) <= set(codes)  # AC-A1


def test_airline_table_header_states_source_date_and_verifier() -> None:
    doc = airlines_module.__doc__ or ""
    assert "Verification (2026-10-28, dev-lead)" in doc
    assert "iata.org" in doc and "payload" in doc


def test_airline_lookup_and_labels() -> None:
    lookup = lookup_airline("br")
    assert lookup is not None and lookup.zh_name == "長榮航空"
    assert lookup_airline("ZZ") is None
    assert airlines_label(["CI", "BR"]) == "長榮、華航"  # table order, not input order
    assert airlines_label(["ZZ", "BR"]) == "長榮、ZZ"
    assert airlines_label([]) == ""
    assert MAX_AIRLINES == 5


# ---- labels (C-40) ----------------------------------------------------------------------


def test_pax_and_cabin_labels() -> None:
    assert pax_label(2, 1) == "2 大 1 小"
    assert pax_label(1, 0) == "1 人" and pax_label(3, 0) == "3 人"
    assert pax_full_label(2, 1) == "2 位成人、1 位兒童"
    assert pax_full_label(1, 0) == "1 位成人"
    assert total_price_note(2, 1) == "（2 大 1 小總價）"
    assert total_price_note(1, 0) == "（1 人總價）"
    assert [cabin_label(c) for c in typing.get_args(Cabin)] == [
        "經濟艙", "豪華經濟艙", "商務艙", "頭等艙",
    ]  # fmt: skip


def test_condition_labels() -> None:
    assert conditions_label((), None, None) == "不限"
    assert conditions_label(("BR", "CI"), 6, 12) == "長榮、華航｜去程 06–12 時"
    assert conditions_label((), 18, 23) == "去程 18–23 時"
    assert dep_window_label(None, None) == "不限" and dep_window_label(6, 12) == "去程 06–12 時"
    assert filter_line((), None, None) is None
    assert filter_line(("BR", "CI"), 6, 12) == "篩選：航空公司 長榮、華航；去程出發 06–12 時"
    assert filter_line(("BR",), None, None) == "篩選：航空公司 長榮"


def test_new_wording_is_in_static_texts_and_clean() -> None:  # C-40
    texts = all_static_texts()
    for text in static_texts():
        assert text in texts
        assert "點前" not in text
        assert not any(phrase in text for phrase in BANNED_PHRASES), text
    assert BOOKING_FALLBACK_NOTE in texts


# ---- push message (C-25 / C-40 re-check) -----------------------------------------------


def _cand(amount: int, day: int = 10) -> Candidate:
    return Candidate(
        observation_id=None,
        depart_date=date(2026, 12, day),
        return_date=date(2026, 12, day + 5),
        amount_minor=amount,
        currency="TWD",
        price_kind="live",
        source="google_flights",
        carrier="長榮航空",
        fetched_at=NOW,
    )


def _items(count: int, amount: int = major_to_minor(18_509, "TWD")) -> list[TriggeredItem]:
    return [
        TriggeredItem(_cand(amount, 1 + i), ("below_budget", "drop_pct", "new_low"), 99, f"k{i}")
        for i in range(count)
    ]


TFS = "https://www.google.com/travel/flights/search?tfs=" + "A" * 160 + "%3D%3D&hl=zh-TW&curr=TWD"


def test_push_has_party_cabin_filters_and_exact_links() -> None:  # AC-V5, AC-V7
    text = price_alert_message(
        watch_name="東京",
        origin="TPE",
        destination="NRT",
        trip_type="round_trip",
        items=_items(2),
        links=[TFS, None],
        adults=2,
        children=1,
        cabin="business",
        airlines=("CI", "BR"),
        dep_hour_from=6,
        dep_hour_to=12,
    )
    lines = text.splitlines()
    assert lines[0].endswith("（來回・2 大 1 小・商務艙）")
    assert lines[1] == "篩選：航空公司 長榮、華航；去程出發 06–12 時"
    assert text.count("TWD 18,509（2 大 1 小總價）") == 2
    assert "   查票連結：" + TFS in lines
    # A missing link falls back to the text search and says what it does not carry.
    assert "q=Flights%20to%20NRT" in text and f"（{BOOKING_FALLBACK_NOTE}）" in text
    assert text.count(BOOKING_FALLBACK_NOTE) == 1
    assert DISCLAIMER in text


def test_push_for_single_adult_economy_still_labelled() -> None:  # AC-V4
    text = price_alert_message(
        watch_name="w",
        origin="TPE",
        destination="NRT",
        trip_type="one_way",
        items=_items(1),
        links=[TFS],
    )
    assert "（單程・1 人・經濟艙）" in text and "（1 人總價）" in text
    assert "篩選：" not in text


def test_push_length_worst_case() -> None:  # C-25 re-check: 5 items, tfs links, longest
    places = sorted(
        (p for p in PLACES if is_selectable(p)), key=lambda p: len(p.display_name), reverse=True
    )
    longest_airlines = tuple(
        a.code for a in sorted(AIRLINES, key=lambda a: len(a.display_name), reverse=True)[:5]
    )
    items = [
        TriggeredItem(
            Candidate(
                observation_id=None,
                depart_date=date(2026, 12, 1 + i),
                return_date=date(2026, 12, 20 + i),
                amount_minor=major_to_minor(9_999_999, "TWD"),
                currency="TWD",
                price_kind="cached",
                source="google_flights",
                carrier="Carrier Name " * 4,
                fetched_at=NOW,
            ),
            ("below_budget", "drop_pct", "new_low"),
            99,
            f"k{i}",
        )
        for i in range(5)
    ]
    text = price_alert_message(
        watch_name="名" * 80,
        origin=places[0].code,
        destination=places[1].code,
        trip_type="round_trip",
        items=items,
        links=[TFS + "x" * 100] * 4 + [None],  # one fallback link with its note
        adults=8,
        children=1,
        cabin="premium_economy",
        airlines=longest_airlines,
        dep_hour_from=0,
        dep_hour_to=23,
    )
    assert len(text) < MAX_MESSAGE_LENGTH
    assert route_label(places[0].code, places[1].code) in text
    for phrase in BANNED_PHRASES:
        assert phrase not in text


# ---- digest (C-34 re-check) ---------------------------------------------------------------


def _digest_row(name: str, origin: str, destination: str, amount: int | None) -> DigestRow:
    return DigestRow(
        name=name,
        origin=origin,
        destination=destination,
        currency="TWD",
        amount_minor=amount,
        depart_date=date(2026, 12, 10) if amount else None,
        return_date=date(2026, 12, 15) if amount else None,
        delta_minor=-60_000 if amount else None,
        data_stale=True,
        watch_stale=True,
        adults=8,
        children=1,
        cabin="premium_economy",
    )


def test_digest_lines_carry_party_and_cabin() -> None:  # AC-V6
    rows = [
        _digest_row("東京", "TPE", "NRT", major_to_minor(18_509, "TWD")),
        _digest_row("大阪", "TPE", "KIX", None),
    ]
    text = daily_digest_message(
        day=date(2026, 10, 26),
        sources=[],
        last_scan_at=None,
        failed_scans_24h=0,
        rows=rows,
        stale_after_hours=24,
    )
    tokyo, osaka = (line for line in text.splitlines() if line.startswith("• "))
    assert "豪華經濟艙｜TWD 18,509（8 大 1 小總價）（12/10–12/15）" in tokyo
    assert "豪華經濟艙｜尚無價格（8 大 1 小）" in osaka
    assert "最低總價" in text  # the delta definition says the change is between totals


def test_digest_length_cap_with_200_watches_and_longest_labels() -> None:  # C-34
    codes = sorted(PLACES, key=lambda p: len(route_label(p.code, p.code)), reverse=True)
    rows = [
        _digest_row("名" * 80, codes[0].code, codes[1].code, major_to_minor(9_999_999, "TWD"))
        for _ in range(200)
    ]
    text = daily_digest_message(
        day=date(2026, 10, 26),
        sources=[DigestSourceRow("google_flights", "異常", "open")],
        last_scan_at=NOW,
        failed_scans_24h=12,
        rows=rows,
        stale_after_hours=24,
    )
    assert len(text) <= DIGEST_MAX_CHARS < MAX_MESSAGE_LENGTH
    watch_lines = [line for line in text.splitlines() if line.startswith("• ")]
    assert 0 < len(watch_lines) <= DIGEST_MAX_WATCH_LINES
    assert f"另有 {200 - len(watch_lines)} 個監看未列出" in text
    assert DISCLAIMER in text and text.rstrip().endswith(NO_PRICE_ALERT_NOTE)

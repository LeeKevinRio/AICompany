"""FD-16: Google's separate-tickets mark and the return flight of the cheapest price."""

from __future__ import annotations

import json
import re
import sqlite3
from dataclasses import dataclass, field, replace
from datetime import date
from pathlib import Path
from typing import Any

import pytest

from flight_deals.app import assemble
from flight_deals.config import Config
from flight_deals.domain.flight_summary import flight_summary
from flight_deals.domain.messages import (
    COMMAND_REPLY_MAX_CHARS,
    DISCLAIMER,
    OVERHEAD_BIN_LABELS,
    OVERHEAD_BIN_NOTE,
    PRICE_SOURCE_NOTE,
    ROUND_TRIP_NOTE,
    SPLIT_TICKET_LABEL,
    WEB_TEXTS,
    command_watch_message,
    daily_digest_message,
    price_alert_message,
    web_static_texts,
)
from flight_deals.domain.models import (
    DatePair,
    FlightSearch,
    PriceQuote,
    ReturnLeg,
    SegmentRef,
)
from flight_deals.notify.telegram import MAX_MESSAGE_LENGTH
from flight_deals.ports import ReturnLegResult
from flight_deals.services import scan as scan_module
from flight_deals.sources.google_flights import (
    GoogleFlightsLinkBuilder,
    GoogleFlightsSource,
    build_query,
    build_return_query,
)
from flight_deals.sources.google_payload import parse_payload
from flight_deals.storage import db as db_module
from flight_deals.storage.db import Database, backup_path
from tests.conftest import FIXTURES, FakeClock, Harness
from tests.test_airports import _items
from tests.test_digest import row as digest_row
from tests.test_fd12_migration import migrated
from tests.test_fd12_pages import (
    BR_DIRECT,
    RETURN_EXPLAIN,
    flexible_round_trip,
    get,
    main_card,
    priced_one_way,
)
from tests.test_fd12_telegram import LONG_NAME, detail
from tests.test_fd12_telegram import row as watch_row
from tests.test_sources import make_source, page_html

PAIRS = FIXTURES / "fd16"
ORIGINAL_MIGRATIONS = db_module.available_migrations
REFS = (SegmentRef("TPE", "2026-12-10", "NRT", "BR", "184"),)
SPLIT = {**BR_DIRECT, "split_ticket": True, "segment_refs": REFS}
ONE_TICKET = {**BR_DIRECT, "split_ticket": False, "segment_refs": REFS}
LEG = ReturnLeg(
    carrier="長榮航空",
    stops=0,
    depart_time="09:45",
    duration_minutes=220,
    flight_numbers="BR185",
    arrive_time="12:30",
    arrive_day_offset=0,
    route_airports="NRT,TPE",
)
LISTED = WEB_TEXTS.return_leg_explain_listed
BAG = OVERHEAD_BIN_LABELS["round_trip"]


def pair(name: str) -> dict[str, Any]:
    return json.loads((PAIRS / f"{name}.json").read_text(encoding="utf-8"))


def rows(payload: Any) -> list[Any]:
    return [k for b in (payload[2], payload[3]) for k in (b or [None])[0] or [] if k[1][0]]


def key(k: Any) -> str:
    return "+".join(s[22][0] + s[22][1] for s in k[0][2])


@dataclass
class Lookup:
    """Scripted ``ReturnLegLookup``."""

    result: ReturnLegResult = field(default_factory=lambda: ReturnLegResult("ok", 1, LEG))
    calls: list[tuple[FlightSearch, PriceQuote]] = field(default_factory=list)
    error: Exception | None = None
    source_name: str = "google_flights"

    def return_leg(self, search: FlightSearch, quote: PriceQuote) -> ReturnLegResult:
        self.calls.append((search, quote))
        if self.error:
            raise self.error
        return self.result


@pytest.fixture
def lookup(harness: Harness) -> Lookup:
    scripted = Lookup()
    harness.services.scan._return_legs = scripted
    return scripted


def scanned(h: Harness, flight: dict[str, Any] = SPLIT, **overrides: Any) -> int:
    h.source.prices[("2026-12-10", "2026-12-15")] = 9_000
    h.source.prices[("2026-12-11", "2026-12-16")] = 8_000
    h.source.flights[("2026-12-10", "2026-12-15")] = flight
    h.source.flights[("2026-12-11", "2026-12-16")] = flight
    watch_id = flexible_round_trip(h, **overrides)
    h.scan(watch_id)
    return watch_id


# ---- the mark on real pages ----------------------------------------------------------------------


@pytest.mark.parametrize(
    "name,expected",
    [
        ("kix_same_airline_split", True),
        ("khh_split", True),
        ("oka_one_ticket", False),
        ("khh_connecting_one_ticket", False),
    ],
)
def test_recorded_pairs_read_the_mark(name: str, expected: bool) -> None:
    recorded = pair(name)
    by_flight = {
        "+".join(f["code"] + f["number"] for f in r["flights"]): r
        for r in parse_payload(recorded["outbound"]).records
    }
    assert by_flight[recorded["flight"]]["split_ticket"] is expected


@pytest.mark.parametrize(
    "value,expected",
    [(1, True), (0, False), (2, None), (True, None), ("1", None), (None, None), (1.0, None)],
)
def test_only_int_zero_or_one_is_read(value: Any, expected: bool | None) -> None:
    payload = pair("oka_one_ticket")["outbound"]
    rows(payload)[0][6] = value
    records = parse_payload(payload).records
    first = key(rows(payload)[0])
    match = next(
        r for r in records if "+".join(f["code"] + f["number"] for f in r["flights"]) == first
    )
    assert match["split_ticket"] is expected


def test_missing_field_only_degrades() -> None:
    payload = pair("oka_one_ticket")["outbound"]
    clean = parse_payload(json.loads(json.dumps(payload)))
    del rows(payload)[0][6:]
    page = parse_payload(payload)
    assert page.stats == clean.stats
    assert page.records[0]["price"] == clean.records[0]["price"]


# ---- the return page -----------------------------------------------------------------------------


def test_selected_flight_is_appended_to_the_outbound_leg() -> None:
    search = FlightSearch("TPE", "KIX", DatePair(date(2027, 2, 17), date(2027, 2, 22)), None)
    refs = (SegmentRef("TPE", "2027-02-17", "KIX", "GK", "54"),)
    assert build_return_query(search, refs).params()["tfs"] == (
        "GjoSCjIwMjctMDItMTdqBRIDVFBFcgUSA0tJWCIeCgNUUEUSCjIwMjctMDItMTcaA0tJWCoCR0syAjU0"
        "GhoSCjIwMjctMDItMjJqBRIDS0lYcgUSA1RQRUIBAUgBmAEB"
    )
    assert build_query(search).params()["tfs"] != build_return_query(search, refs).params()["tfs"]


def test_two_segments_are_both_selected() -> None:
    search = FlightSearch("KHH", "NRT", DatePair(date(2027, 2, 24), date(2027, 3, 1)), None)
    refs = (
        SegmentRef("KHH", "2027-02-24", "HKG", "UO", "131"),
        SegmentRef("HKG", "2027-02-24", "NRT", "UO", "650"),
    )
    assert build_return_query(search, refs).params()["tfs"] == (
        "GlwSCjIwMjctMDItMjRqBRIDS0hIcgUSA05SVCIfCgNLSEgSCjIwMjctMDItMjQaA0hLRyoCVU8yAzEz"
        "MSIfCgNIS0cSCjIwMjctMDItMjQaA05SVCoCVU8yAzY1MBoaEgoyMDI3LTAzLTAxagUSA05SVHIFEgNL"
        "SEhCAQFIAZgBAQ=="
    )


def test_booking_link_does_not_select_a_flight() -> None:  # R6
    search = FlightSearch("TPE", "KIX", DatePair(date(2027, 2, 17), date(2027, 2, 22)), None)
    assert build_query(search).params()["tfs"] in GoogleFlightsLinkBuilder().url(search).replace(
        "%3D", "="
    )


def source_for(clock: FakeClock, name: str) -> tuple[Any, FlightSearch, PriceQuote]:
    recorded = pair(name)
    routes = {
        "kix_same_airline_split": ("TPE", "KIX", date(2027, 2, 17), date(2027, 2, 22)),
        "khh_split": ("KHH", "NRT", date(2027, 2, 24), date(2027, 3, 1)),
        "oka_one_ticket": ("TPE", "OKA", date(2026, 12, 8), date(2026, 12, 12)),
        "khh_connecting_one_ticket": ("KHH", "NRT", date(2027, 2, 24), date(2027, 3, 1)),
    }
    origin, destination, depart, back = routes[name]
    search = FlightSearch(origin, destination, DatePair(depart, back), None)

    def fetch_return(_: FlightSearch, __: tuple[SegmentRef, ...]) -> str:
        return page_html(recorded["return"])

    source, _ = make_source(lambda _: page_html(recorded["outbound"]), clock)
    source._fetch_return = fetch_return
    quotes = source.search(search).quotes
    quote = next(q for q in quotes if q.flight_numbers == recorded["flight"].replace("+", ","))
    return source, search, quote


@pytest.mark.parametrize(
    "name,expected",
    [
        ("kix_same_airline_split", "GK55"),
        ("khh_split", "UO693,UO130"),
        ("oka_one_ticket", "IT231"),
        ("khh_connecting_one_ticket", "UO693,UO130"),
    ],
)
def test_recorded_return_pages_pick_the_flight_with_the_same_total(
    clock: FakeClock, name: str, expected: str
) -> None:
    source, search, quote = source_for(clock, name)
    assert quote.segment_refs
    result = source.return_leg(search, quote)
    assert result.outcome == "ok" and result.attempts == 1
    assert result.leg is not None and result.leg.flight_numbers == expected
    assert result.leg.arrive_time is not None  # dated from the return day


def test_outbound_segments_are_recorded(clock: FakeClock) -> None:
    _, _, quote = source_for(clock, "khh_connecting_one_ticket")
    assert quote.segment_refs == (
        SegmentRef("KHH", "2027-02-24", "HKG", "UO", "131"),
        SegmentRef("HKG", "2027-02-24", "NRT", "UO", "650"),
    )
    assert "segment_refs" not in repr(quote)


def test_other_total_is_no_match(clock: FakeClock) -> None:
    source, search, quote = source_for(clock, "oka_one_ticket")
    result = source.return_leg(search, replace(quote, amount_minor=quote.amount_minor + 100))
    assert result == ReturnLegResult("no_match", 1)


def test_other_marks_are_no_match(clock: FakeClock) -> None:
    source, search, quote = source_for(clock, "oka_one_ticket")
    assert source.return_leg(search, replace(quote, split_ticket=True)).outcome == "no_match"
    assert (
        source.return_leg(search, replace(quote, overhead_bin_excluded=True)).outcome == "no_match"
    )


def test_same_price_with_another_mark_is_skipped(clock: FakeClock) -> None:  # R4
    recorded = pair("oka_one_ticket")
    payload = recorded["return"]
    cheapest = sorted(rows(payload), key=lambda k: k[1][0][1])
    cheapest[1][1][0][1] = cheapest[0][1][0][1]  # same total
    cheapest[0][6] = 1  # the earlier flight is marked, the outbound is not
    source, search, quote = source_for(clock, "oka_one_ticket")
    source._fetch_return = lambda _, __: page_html(payload)
    result = source.return_leg(search, quote)
    assert result.leg is not None
    assert result.leg.flight_numbers == key(cheapest[1])


def test_unknown_mark_or_no_segments_sends_nothing(clock: FakeClock) -> None:
    source, search, quote = source_for(clock, "oka_one_ticket")
    source._fetch_return = None  # would raise if used
    assert source.return_leg(search, replace(quote, split_ticket=None)).attempts == 0
    assert source.return_leg(search, replace(quote, segment_refs=())).attempts == 0


@pytest.mark.parametrize(
    "html,outcome",
    [
        ("<html></html>", "blocked"),
        (page_html([None, None, None, None]), "no_embedded"),
    ],
)
def test_page_problems_are_outcomes(clock: FakeClock, html: str, outcome: str) -> None:
    source, search, quote = source_for(clock, "oka_one_ticket")
    source._fetch_return = lambda _, __: html
    assert source.return_leg(search, quote) == ReturnLegResult(outcome, 1)


def test_fetch_error_is_an_outcome_and_no_retry(clock: FakeClock) -> None:
    source, search, quote = source_for(clock, "oka_one_ticket")
    calls: list[int] = []

    def boom(_: FlightSearch, __: tuple[SegmentRef, ...]) -> str:
        calls.append(1)
        raise OSError("network")

    source._fetch_return = boom
    assert source.return_leg(search, quote) == ReturnLegResult("error", 1)
    assert calls == [1]


@pytest.mark.parametrize(
    "changes",
    [
        {"adults": 2},
        {"children": 1},
        {"cabin": "business"},
    ],
)
def test_mark_only_for_one_adult_in_economy(clock: FakeClock, changes: dict[str, Any]) -> None:
    recorded = pair("kix_same_airline_split")
    source, _ = make_source(lambda _: page_html(recorded["outbound"]), clock)
    search = FlightSearch(
        "TPE", "KIX", DatePair(date(2027, 2, 17), date(2027, 2, 22)), None, **changes
    )
    assert all(q.split_ticket is None for q in source.search(search).quotes)


def test_mark_is_dropped_on_one_way(clock: FakeClock) -> None:
    recorded = pair("kix_same_airline_split")
    source, _ = make_source(lambda _: page_html(recorded["outbound"]), clock)
    search = FlightSearch("TPE", "KIX", DatePair(date(2027, 2, 17), None), None)
    assert all(q.split_ticket is None for q in source.search(search).quotes)


# ---- the scan ------------------------------------------------------------------------------------


def test_one_lookup_for_the_rounds_cheapest(harness: Harness, lookup: Lookup) -> None:
    watch_id = scanned(harness)
    assert len(lookup.calls) == 1
    search, quote = lookup.calls[0]
    assert quote.amount_minor == 800000 and search.pair.depart == date(2026, 12, 11)
    observations = harness.repo.observations_for_watch(watch_id)
    cheap = next(o for o in observations if o.amount_minor == 800000)
    other = next(o for o in observations if o.amount_minor == 900000)
    assert cheap.return_leg == LEG and other.return_leg is None
    assert cheap.amount_minor == 800000  # the update changes only the return columns


def test_same_price_in_a_round_uses_the_snapshot_order(
    harness: Harness, lookup: Lookup
) -> None:  # M3
    harness.source.prices[("2026-12-10", "2026-12-15")] = 8_000
    harness.source.prices[("2026-12-11", "2026-12-16")] = 8_000
    harness.source.flights[("2026-12-10", "2026-12-15")] = SPLIT
    harness.source.flights[("2026-12-11", "2026-12-16")] = SPLIT
    watch_id = flexible_round_trip(harness)
    harness.scan(watch_id)
    assert lookup.calls[0][0].pair.depart == date(2026, 12, 10)
    page = get(harness, f"/watches/{watch_id}")
    card = page.main.find_all("section", "price-card")[0]
    assert "BR 185" in card.text()


def test_lookup_counts_against_queries_and_is_recorded(harness: Harness, lookup: Lookup) -> None:
    watch_id = scanned(harness)
    run = harness.repo.latest_scan_run_for_watch(watch_id)
    assert run.queries_used == 3
    entries = [e for e in run.query_results if e.get("return_lookup")]
    assert [e["return_lookup"] for e in entries] == ["ok"]
    assert entries[0]["depart"] == "2026-12-11"
    assert all("return_lookup" not in t for e in run.query_results for t in e["tries"])


@pytest.mark.parametrize(
    "outcome,attempts",
    [("no_match", 1), ("blocked", 1), ("error", 1), ("no_embedded", 1)],
)
def test_failures_never_change_the_run(
    harness: Harness, lookup: Lookup, outcome: Any, attempts: int
) -> None:
    lookup.result = ReturnLegResult(outcome, attempts)
    watch_id = scanned(harness)
    run = harness.repo.latest_scan_run_for_watch(watch_id)
    assert run.status == "ok" and run.error_summary is None
    assert run.queries_used == 2 + attempts
    assert all(o.return_leg is None for o in harness.repo.observations_for_watch(watch_id))
    assert harness.notifier.sent  # the alert still goes out


def test_exception_stays_inside(harness: Harness, lookup: Lookup) -> None:
    lookup.error = RuntimeError("secret detail")
    watch_id = scanned(harness)
    run = harness.repo.latest_scan_run_for_watch(watch_id)
    assert run.status == "ok"
    assert run.queries_used == 3  # the request may have gone out before the error
    assert [e["return_lookup"] for e in run.query_results if e.get("return_lookup")] == ["error"]
    assert "secret detail" not in json.dumps(run.query_results, ensure_ascii=False)


def test_failed_write_keeps_the_count_and_the_run(harness: Harness, lookup: Lookup) -> None:
    def boom(*_: Any) -> None:
        raise sqlite3.IntegrityError("CHECK constraint failed")

    harness.services.scan._repo.set_observation_return_leg = boom
    watch_id = scanned(harness)
    run = harness.repo.latest_scan_run_for_watch(watch_id)
    assert run.status == "ok" and run.queries_used == 3
    assert [e["return_lookup"] for e in run.query_results if e.get("return_lookup")] == ["error"]
    assert harness.notifier.sent


def test_nothing_sent_counts_nothing(harness: Harness, lookup: Lookup) -> None:
    lookup.result = ReturnLegResult("no_match", 0)
    watch_id = scanned(harness)
    assert harness.repo.latest_scan_run_for_watch(watch_id).queries_used == 2


def test_older_cheaper_price_is_checked_again_and_gets_its_return(
    harness: Harness, lookup: Lookup, monkeypatch: pytest.MonkeyPatch
) -> None:  # FD-18: the main card's pair is pinned into the next round
    harness.source.prices[("2026-12-10", "2026-12-15")] = 7_000
    harness.source.prices[("2026-12-11", "2026-12-16")] = 9_000
    harness.source.flights[("2026-12-10", "2026-12-15")] = SPLIT
    harness.source.flights[("2026-12-11", "2026-12-16")] = SPLIT
    watch_id = flexible_round_trip(harness)
    lookup.result = ReturnLegResult("no_match", 1)
    harness.scan(watch_id)
    harness.clock.advance(hours=7)
    lookup.result = ReturnLegResult("ok", 1, LEG)

    def only_second(pairs: Any, limit: int, offset: int) -> Any:
        return [p for p in pairs if p.depart == date(2026, 12, 11)], offset, True

    monkeypatch.setattr(scan_module, "sample_pairs", only_second)
    harness.scan(watch_id)
    assert lookup.calls[-1][0].pair.depart == date(2026, 12, 10)
    card = get(harness, f"/watches/{watch_id}").main.find_all("section", "price-card")[0]
    assert "7,000" in card.text() and "BR 185" in card.text()


@pytest.mark.parametrize(
    "conditions", [{"adults": 2}, {"adults": 1, "children": 1}, {"cabin": "business"}]
)
def test_no_lookup_for_a_party_or_other_cabin(
    harness: Harness, lookup: Lookup, conditions: dict[str, Any]
) -> None:
    scanned(harness, **conditions)
    assert lookup.calls == []


def test_no_lookup_for_one_way(harness: Harness, lookup: Lookup) -> None:
    priced_one_way(harness)
    assert lookup.calls == []


def test_real_source_is_wired_in(tmp_path: Path) -> None:
    config = Config(db_path=tmp_path / "wired.db", sources=("google_flights",))
    scan = assemble(config).services.scan
    assert isinstance(scan._return_legs, GoogleFlightsSource)
    assert scan._return_legs.source_name == "google_flights"


def test_scripted_sources_get_no_real_lookup(harness: Harness) -> None:
    assert harness.services.scan._return_legs is None


def test_is_closed_never_moves_the_breaker(harness: Harness) -> None:
    health = harness.services.scan._health
    record = health._get("google_flights")
    open_record = replace(record, breaker_state="open", open_until=harness.clock.now)
    harness.repo.save_source_health(open_record)
    assert health.is_closed("google_flights") is False
    assert health._get("google_flights").breaker_state == "open"


def test_no_lookup_without_a_mark_or_segments(harness: Harness, lookup: Lookup) -> None:
    watch_id = scanned(harness, flight=BR_DIRECT)
    run = harness.repo.latest_scan_run_for_watch(watch_id)
    assert lookup.calls == []
    assert [e["return_lookup"] for e in run.query_results if e.get("return_lookup")] == [
        "skipped_no_refs"
    ]


def test_no_lookup_when_the_breaker_is_not_closed(harness: Harness, lookup: Lookup) -> None:
    health = harness.services.scan._health
    health.is_closed = lambda _: False
    watch_id = scanned(harness)
    run = harness.repo.latest_scan_run_for_watch(watch_id)
    assert lookup.calls == []
    assert [e["return_lookup"] for e in run.query_results if e.get("return_lookup")] == [
        "skipped_breaker"
    ]


def test_quota_skips_only_the_lookup(harness: Harness, lookup: Lookup) -> None:
    settings = harness.services.scan._settings
    original = settings.current
    settings.current = lambda: replace(original(), global_hourly_query_limit=2)
    watch_id = scanned(harness)
    run = harness.repo.latest_scan_run_for_watch(watch_id)
    assert lookup.calls == [] and run.status == "ok" and not run.global_limit_reached
    assert [e["return_lookup"] for e in run.query_results if e.get("return_lookup")] == [
        "skipped_quota"
    ]


def test_other_currency_is_not_looked_up(harness: Harness, lookup: Lookup) -> None:
    harness.source.currency = "JPY"
    scanned(harness)
    assert lookup.calls == []


def test_mark_and_return_never_change_alerts(harness: Harness, lookup: Lookup) -> None:  # R7
    def reasons() -> str:
        return next(line for line in harness.notifier.sent[-1].splitlines() if "觸發原因" in line)

    harness.source.prices[("2026-12-10", "2026-12-15")] = 9_000
    harness.source.flights[("2026-12-10", "2026-12-15")] = BR_DIRECT
    plain = harness.create_watch(destination="NRT", name="a")
    harness.scan(plain)
    first = reasons()
    harness.source.flights[("2026-12-10", "2026-12-15")] = SPLIT
    marked = harness.create_watch(destination="KIX", name="b")
    harness.scan(marked)
    assert reasons() == first
    assert SPLIT_TICKET_LABEL in harness.notifier.sent[-1]


# ---- storage -------------------------------------------------------------------------------------


def test_migration_adds_columns_and_backs_up(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    database = migrated(tmp_path, monkeypatch)
    monkeypatch.setattr(db_module, "available_migrations", ORIGINAL_MIGRATIONS)
    assert database.migrate() == 11
    with database.connect() as conn:
        rows_ = conn.execute("SELECT split_ticket FROM comparison_cell").fetchall()
        old = conn.execute(
            "SELECT split_ticket, return_carrier, return_stops, return_depart_time,"
            " return_duration_minutes, return_flight_numbers, return_arrive_time,"
            " return_arrive_day_offset, return_route_airports FROM price_observation"
        ).fetchall()
    assert rows_ and all(r[0] is None for r in rows_)
    assert old and all(value is None for r in old for value in r)
    backup = backup_path(database.path, 11)
    assert backup.is_file() and Database(backup).schema_version() == 10


def test_check_constraints(harness: Harness, lookup: Lookup) -> None:
    scanned(harness)
    bad_updates = [
        ("split_ticket", 0),
        ("split_ticket", 2),
        ("return_stops", -1),
        ("return_depart_time", "25:00"),
        ("return_flight_numbers", "br 1"),
        ("return_route_airports", "TPE"),
        ("return_duration_minutes", 0),
    ]
    with harness.repo.db.connect() as conn:
        for column, value in bad_updates:
            with pytest.raises(sqlite3.IntegrityError):
                conn.execute(f"UPDATE price_observation SET {column} = ?", (value,))
        with pytest.raises(sqlite3.IntegrityError):  # set together
            conn.execute("UPDATE price_observation SET return_arrive_time = '12:00'")
        with pytest.raises(sqlite3.IntegrityError):  # range
            conn.execute(
                "UPDATE price_observation SET return_arrive_time = '12:00',"
                " return_arrive_day_offset = 9"
            )
        conn.execute("UPDATE price_observation SET split_ticket = 1")


def test_false_is_stored_as_null(harness: Harness, lookup: Lookup) -> None:
    watch_id = scanned(harness, flight=ONE_TICKET)
    assert all(o.split_ticket is None for o in harness.repo.observations_for_watch(watch_id))


def test_old_price_row_keeps_nothing_after_a_new_price(harness: Harness, lookup: Lookup) -> None:
    watch_id = scanned(harness)
    harness.clock.advance(hours=7)
    lookup.result = ReturnLegResult("no_match", 1)
    harness.source.prices[("2026-12-11", "2026-12-16")] = 7_000
    harness.scan(watch_id)
    card = get(harness, f"/watches/{watch_id}").main.find_all("section", "price-card")[0]
    assert "BR 185" not in card.text()  # R5: never carried over to a new price


# ---- pages ---------------------------------------------------------------------------------------


def test_detail_card_shows_labels_and_return_flight(harness: Harness, lookup: Lookup) -> None:
    watch_id = scanned(harness)
    page = get(harness, f"/watches/{watch_id}")
    card = page.main.find_all("section", "price-card")[0]
    flights = card.find_all(None, "flight")
    assert len(flights) == 2
    assert flights[1].find_all(None, "sr-only")[0].text().startswith("回程")
    assert "BR 185" in flights[1].text() and "09:45" in flights[1].text()
    for flight in flights:
        assert SPLIT_TICKET_LABEL not in flight.text()
    assert SPLIT_TICKET_LABEL in card.text()
    # FD-22 package E #40: the return-leg sentences sit once in the collapsed panel.
    assert page.count(ROUND_TRIP_NOTE) == 1 and page.count_in_details(ROUND_TRIP_NOTE) == 1
    assert page.count(LISTED) == 1 and page.count_in_details(LISTED) == 1
    assert RETURN_EXPLAIN not in page.html
    assert OVERHEAD_BIN_NOTE not in page.html


def test_labels_keep_their_order(harness: Harness, lookup: Lookup) -> None:
    watch_id = scanned(harness, flight={**SPLIT, "overhead_bin_excluded": True})
    labels = get(harness, f"/watches/{watch_id}").main.find_all(None, "price-labels")[0]
    text = labels.text()
    assert text.index(SPLIT_TICKET_LABEL) < text.index(BAG)


def test_no_return_flight_keeps_the_old_sentence(harness: Harness, lookup: Lookup) -> None:
    lookup.result = ReturnLegResult("no_match", 1)
    watch_id = scanned(harness)
    page = get(harness, f"/watches/{watch_id}")
    assert len(page.main.find_all("section", "price-card")[0].find_all(None, "flight")) == 1
    # FD-22 package E #40: in the collapsed panel.
    assert page.count(RETURN_EXPLAIN) == 1 and page.count_in_details(RETURN_EXPLAIN) == 1
    assert LISTED not in page.html


def test_unmarked_price_shows_nothing_but_keeps_the_note(harness: Harness, lookup: Lookup) -> None:
    watch_id = scanned(harness, flight=ONE_TICKET)
    page = get(harness, f"/watches/{watch_id}")
    # FD-22 ruling section 2: the verbatim summary line says "單張機票" too.
    leftover = page.html.replace(ROUND_TRIP_NOTE, "").replace(WEB_TEXTS.page_summary_round_trip, "")
    assert SPLIT_TICKET_LABEL not in page.html and "單張機票" not in leftover
    assert page.count(ROUND_TRIP_NOTE) == 1 and page.count_in_details(ROUND_TRIP_NOTE) == 1


def test_list_mixes_return_flights(harness: Harness, lookup: Lookup) -> None:
    scanned(harness)
    lookup.result = ReturnLegResult("no_match", 1)
    harness.clock.advance(hours=1)
    other = harness.create_watch(destination="KIX", name="大阪")
    harness.source.flight = BR_DIRECT
    harness.scan(other)
    page = get(harness, "/")
    # FD-22 ruling section 1: the list keeps these once, inside the collapsed panel.
    assert page.count(LISTED) == 1 and page.count_in_details(LISTED) == 1
    assert RETURN_EXPLAIN not in page.html
    assert page.count(ROUND_TRIP_NOTE) == 1 and page.count_in_details(ROUND_TRIP_NOTE) == 1
    cards = page.main.find_all(None, "watch-card")
    main_cards = [main_card(page, int(c.attrs["data-watch-id"])) for c in cards]
    assert sorted(len(c.find_all("div", "flight")) for c in main_cards) == [1, 2]


def test_list_with_one_way_and_round_trip_has_the_round_trip_note(
    harness: Harness, lookup: Lookup
) -> None:
    scanned(harness)
    priced_one_way(harness)
    page = get(harness, "/")
    # FD-22 ruling section 1: inside the collapsed panel on the list.
    assert page.count(ROUND_TRIP_NOTE) == 1 and page.count_in_details(ROUND_TRIP_NOTE) == 1
    assert OVERHEAD_BIN_NOTE not in page.html


def test_one_way_marked_bag_keeps_its_own_note(harness: Harness) -> None:
    harness.source.prices[("2026-12-20", None)] = 5_000
    harness.source.flights[("2026-12-20", None)] = {**BR_DIRECT, "overhead_bin_excluded": True}
    watch_id = harness.create_watch(
        destination="KIX", trip_type="one_way", depart_date="2026-12-20", return_date=None
    )
    harness.scan(watch_id)
    page = get(harness, f"/watches/{watch_id}")
    # FD-22 package E #40: in the collapsed panel.
    assert page.count(OVERHEAD_BIN_NOTE) == 1 and page.count_in_details(OVERHEAD_BIN_NOTE) == 1
    assert ROUND_TRIP_NOTE not in page.html


def test_summary_of_a_return_flight() -> None:
    summary = flight_summary(LEG, trip_type="round_trip", returning=True)
    assert summary.leg_label == "回程" and not summary.is_outbound_only
    assert summary.sr_text.startswith("回程")


# ---- Telegram (R8) -------------------------------------------------------------------------------


def _alert(trip_type: str, split: bool, bag: bool, **kwargs: Any) -> str:
    items = _items(kwargs.pop("count", 1))
    for item in items:
        object.__setattr__(item.candidate, "split_ticket", True if split else None)
        object.__setattr__(item.candidate, "overhead_bin_excluded", True if bag else None)
    args: dict[str, Any] = {
        "watch_name": "沖繩",
        "origin": "TPE",
        "destination": "OKA",
        "trip_type": trip_type,
        "items": items,
        "links": [None] * len(items),
    }
    return price_alert_message(**{**args, **kwargs})


def test_alert_lists_both_labels_after_the_price() -> None:
    lines = _alert("round_trip", True, True).splitlines()
    first = next(i for i, line in enumerate(lines) if line.startswith("1. 查到"))
    assert lines[first + 1 : first + 3] == [f"   {SPLIT_TICKET_LABEL}", f"   {BAG}"]
    assert lines[-3:] == [DISCLAIMER, PRICE_SOURCE_NOTE, ROUND_TRIP_NOTE]


def test_fully_marked_longest_alert_fits() -> None:
    text = _alert(
        "round_trip",
        True,
        True,
        count=5,
        watch_name="名" * 80,
        links=["https://www.google.com/travel/flights/search?tfs=" + "x" * 400] * 5,
        airlines=("BR", "CI", "JX"),
        dep_hour_from=6,
        dep_hour_to=22,
    )
    assert len(text) < MAX_MESSAGE_LENGTH
    assert text.endswith(ROUND_TRIP_NOTE)


def test_watch_format_and_length() -> None:
    rows_ = tuple(
        replace(
            watch_row(
                carrier=f"{LONG_NAME}、{LONG_NAME}、{LONG_NAME}",
                flight_numbers="BR1001,BR1002,BR1003,BR1004,BR1005,BR1006",
            ),
            split_ticket=True,
            overhead_bin_excluded=True,
        )
        for _ in range(3)
    )
    text = command_watch_message(detail(rows_))
    assert len(text) <= COMMAND_REPLY_MAX_CHARS
    assert f"總價）｜{SPLIT_TICKET_LABEL}｜{BAG}｜" in text
    assert text.endswith(ROUND_TRIP_NOTE)


def test_cut_watch_keeps_the_note() -> None:
    long_link = "https://www.google.com/travel/flights/search?tfs=" + "x" * 3000
    rows_ = tuple(replace(watch_row(booking_url=long_link), split_ticket=True) for _ in range(3))
    text = command_watch_message(detail(rows_))
    assert len(text) <= COMMAND_REPLY_MAX_CHARS and text.count(long_link) < 3
    assert text.endswith(ROUND_TRIP_NOTE)


def test_digest_has_no_label() -> None:
    text = daily_digest_message(
        day=date(2026, 10, 26),
        sources=[],
        last_scan_at=None,
        failed_scans_24h=0,
        rows=[digest_row("a")],
        stale_after_hours=12,
    )
    assert SPLIT_TICKET_LABEL not in text and ROUND_TRIP_NOTE not in text


def test_telegram_has_no_return_flight(harness: Harness, lookup: Lookup) -> None:
    scanned(harness)
    assert "BR 185" not in harness.notifier.sent[-1]


# ---- wording (R1) --------------------------------------------------------------------------------


def test_wording_stays_within_the_ruling() -> None:
    forbidden = (
        "此價為分段",
        "此價格為分段",
        "非分段",
        "不用分開",
        "同一訂單",
        "價格已含兩張",
    )
    for text in web_static_texts():
        leftover = text.replace(ROUND_TRIP_NOTE, "").replace(LISTED, "")
        leftover = leftover.replace(SPLIT_TICKET_LABEL, "")
        # FD-22 ruling section 2: the verbatim round-trip summary line says "單張機票".
        leftover = leftover.replace(WEB_TEXTS.page_summary_round_trip, "")
        for phrase in (*forbidden, "單張", "要分開買", "換回程"):
            assert phrase not in leftover, (phrase, text)
    assert re.fullmatch(r"Google 標示此價要分開買", SPLIT_TICKET_LABEL)

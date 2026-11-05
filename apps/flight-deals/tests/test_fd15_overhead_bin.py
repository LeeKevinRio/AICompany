"""FD-15: Google's "fare excludes the overhead bin" mark, parsed, stored and shown."""

from __future__ import annotations

import copy
import json
import sqlite3
from dataclasses import replace
from pathlib import Path
from typing import Any

import pytest

from flight_deals.domain.messages import (
    BANNED_PHRASES,
    BOOKING_FALLBACK_NOTE,
    COMMAND_REPLY_MAX_CHARS,
    COMPARISON_ORDER_NOTE,
    DETAIL_ALL_DEPARTED,
    DISCLAIMER,
    OVERHEAD_BIN_LABELS,
    OVERHEAD_BIN_NOTE,
    PRICE_SOURCE_NOTE,
    ROUND_TRIP_NOTE,
    WEB_TEXTS,
    command_watch_message,
    daily_digest_message,
    price_alert_message,
    web_static_texts,
)
from flight_deals.domain.models import PriceQuote, quote_rank_key
from flight_deals.notify.telegram import MAX_MESSAGE_LENGTH
from flight_deals.sources._records import quotes_from_records
from flight_deals.sources.google_payload import parse_payload
from flight_deals.storage import db as db_module
from flight_deals.storage.db import Database, backup_path
from tests.conftest import FIXTURES, Harness
from tests.test_airports import _items
from tests.test_digest import row
from tests.test_fd12_migration import migrated
from tests.test_fd12_pages import (
    BR_DIRECT,
    RETURN_EXPLAIN,
    ComparisonQueue,
    cheaper_second_round,
    compared,
    done_comparison,
    done_exploration,
    flexible_round_trip,
    get,
    one_way_comparison,
    one_way_exploration,
    priced_one_way,
    priced_round_trip,
)
from tests.test_fd12_telegram import LONG_NAME, detail
from tests.test_fd12_telegram import row as watch_row

ROUND_TRIP = OVERHEAD_BIN_LABELS["round_trip"]
ONE_WAY = OVERHEAD_BIN_LABELS["one_way"]
MARKED = {**BR_DIRECT, "overhead_bin_excluded": True}
BAGGAGE_FIXTURE = FIXTURES / "payload_TPE_KIX_round_trip_baggage.json"
ORIGINAL_MIGRATIONS = db_module.available_migrations


def load(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def itineraries(payload: Any) -> list[Any]:
    return [k for block in (payload[2], payload[3]) for k in (block or [None])[0] or []]


def marked_round_trip(h: Harness) -> int:
    h.source.prices[("2026-12-10", "2026-12-15")] = 9_000
    h.source.prices[("2026-12-11", "2026-12-16")] = 8_000
    h.source.flights[("2026-12-10", "2026-12-15")] = BR_DIRECT
    h.source.flights[("2026-12-11", "2026-12-16")] = MARKED
    watch_id = flexible_round_trip(h)
    h.scan(watch_id)
    return watch_id


def marked_one_way(h: Harness) -> int:
    h.source.prices[("2026-12-20", None)] = 5_000
    h.source.flights[("2026-12-20", None)] = MARKED
    watch_id = h.create_watch(
        name="大阪單程",
        destination="KIX",
        trip_type="one_way",
        depart_date="2026-12-20",
        return_date=None,
    )
    h.scan(watch_id)
    return watch_id


# ---- parsing (C-108, C-109) ----------------------------------------------------------------------


def test_real_page_marks_only_code_three() -> None:
    payload = load(BAGGAGE_FIXTURE)
    entries = [k for k in itineraries(payload) if k[1][0]]
    records = parse_payload(payload).records
    assert {k[4][4] for k in entries} == {1, 3}
    by_flight = {r["flights"][0]["code"] + r["flights"][0]["number"]: r for r in records}
    for k in entries:
        flight = k[0][2][0][22][0] + k[0][2][0][22][1]
        expected = True if k[4][4] == 3 else None
        assert by_flight[flight]["overhead_bin_excluded"] is expected, flight


@pytest.mark.parametrize("fixture", ["payload_TPE_NRT_BR_06_12.json", "payload_TPE_SHA.json"])
def test_recorded_code_one_pages_stay_unknown(fixture: str) -> None:
    payload = load(FIXTURES / fixture)
    assert {k[4][4] for k in itineraries(payload) if k[1][0]} == {1}
    assert all(r["overhead_bin_excluded"] is None for r in parse_payload(payload).records)


@pytest.mark.parametrize(
    "baggage",
    [
        [None, None, None, None, 1],
        [None, None, None, None, 2],
        [None, None, None, None, 0],
        [None, None, None, None, None],
        [None, None, None, None, True],
        [None, None, None, None, 3.0],
        [None, None, None, None, "3"],
        [None, None, None],
        [],
        None,
        "3",
        {"4": 3},
    ],
)
def test_odd_baggage_shapes_only_degrade(baggage: Any) -> None:
    payload = load(BAGGAGE_FIXTURE)
    clean = parse_payload(copy.deepcopy(payload))
    itineraries(payload)[0][4] = baggage
    page = parse_payload(payload)
    assert page.stats == clean.stats
    assert page.records[0]["overhead_bin_excluded"] is None
    assert page.records[0]["price"] == clean.records[0]["price"]
    assert page.records[0]["flights"] == clean.records[0]["flights"]


def test_records_accept_only_true() -> None:
    base = {"price": 1000, "airlines": ["A"], "flights": [], "depart_time": None, "type": None}
    for value, expected in ((True, True), (False, None), (1, None), ("yes", None), (None, None)):
        quotes = quotes_from_records(
            [{**base, "overhead_bin_excluded": value}],
            source="s",
            price_kind="live",
            currency="TWD",
            depart_date=_date(),
            return_date=None,
            fetched_at=_now(),
        )
        assert quotes[0].overhead_bin_excluded is expected
    quotes = quotes_from_records(
        [base],
        source="s",
        price_kind="live",
        currency="TWD",
        depart_date=_date(),
        return_date=None,
        fetched_at=_now(),
    )
    assert quotes[0].overhead_bin_excluded is None


def _date() -> Any:
    from datetime import date

    return date(2026, 12, 10)


def _now() -> Any:
    from datetime import UTC, datetime

    return datetime(2026, 10, 25, 4, tzinfo=UTC)


# ---- storage (C-110) -----------------------------------------------------------------------------


def test_migration_keeps_rows_and_backs_up(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    database = migrated(tmp_path, monkeypatch)
    with database.connect() as conn:
        before = conn.execute("SELECT COUNT(*) FROM comparison_cell").fetchone()[0]
    monkeypatch.setattr(db_module, "available_migrations", ORIGINAL_MIGRATIONS)
    assert database.migrate() == 11
    with database.connect() as conn:
        assert conn.execute("SELECT COUNT(*) FROM comparison_cell").fetchone()[0] == before
        rows = conn.execute("SELECT overhead_bin_excluded FROM comparison_cell").fetchall()
        assert all(r[0] is None for r in rows)
    backup = backup_path(database.path, 10)
    assert backup.is_file() and Database(backup).schema_version() == 9


def test_check_accepts_only_one_or_null(harness: Harness) -> None:
    priced_round_trip(harness)
    done_exploration(harness)
    done_comparison(harness)
    with harness.repo.db.connect() as conn:
        for table in ("price_observation", "exploration_cell", "comparison_cell"):
            assert conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0] > 0, table
            conn.execute(f"UPDATE {table} SET overhead_bin_excluded = 1")
            conn.execute(f"UPDATE {table} SET overhead_bin_excluded = NULL")
            for bad in (0, 2):
                with pytest.raises(sqlite3.IntegrityError):
                    conn.execute(f"UPDATE {table} SET overhead_bin_excluded = ?", (bad,))


def test_observation_round_trip_and_false_is_null(harness: Harness) -> None:
    watch_id = marked_round_trip(harness)
    rows = {o.amount_minor: o for o in harness.repo.observations_for_watch(watch_id)}
    assert rows[800000].overhead_bin_excluded is True
    assert rows[900000].overhead_bin_excluded is None
    harness.source.flights[("2026-12-10", "2026-12-15")] = {
        **BR_DIRECT,
        "overhead_bin_excluded": False,
    }
    harness.clock.advance(hours=7)
    harness.scan(watch_id)  # False must not trip the CHECK and fail the scan
    latest = harness.repo.observations_for_watch(watch_id)
    assert all(o.overhead_bin_excluded is None for o in latest if o.amount_minor == 900000)


# ---- pages (R2, R3, R5, R6, R10) -----------------------------------------------------------------


def test_list_label_is_outside_the_flight_block(harness: Harness) -> None:
    marked_round_trip(harness)
    page = get(harness, "/")
    assert page.count_visible(ROUND_TRIP) == 1
    assert ONE_WAY not in page.html
    assert page.count_visible(ROUND_TRIP_NOTE) == 1
    flights = page.main.find_all(None, "flight")
    assert flights
    for flight in flights:
        assert ROUND_TRIP not in flight.text()
        assert ROUND_TRIP not in flight.find_all(None, "sr-only")[0].text()
    assert ROUND_TRIP_NOTE in page.main.find_all(None, "page-notes")[0].text()


def test_one_way_uses_its_own_wording(harness: Harness) -> None:
    watch_id = marked_one_way(harness)
    for url in ("/", f"/watches/{watch_id}"):
        page = get(harness, url)
        assert ONE_WAY in page.html and ROUND_TRIP not in page.html, url
        assert page.count_visible(OVERHEAD_BIN_NOTE) == 1, url


def test_detail_main_card_and_unmarked_row(harness: Harness) -> None:
    watch_id = marked_round_trip(harness)
    page = get(harness, f"/watches/{watch_id}")
    card = page.main.find_all("section", "price-card")[0]
    assert ROUND_TRIP in card.text()
    assert ROUND_TRIP not in card.find_all(None, "flight")[0].text()
    assert page.count_visible(ROUND_TRIP_NOTE) == 1
    assert page.count_in_details(ROUND_TRIP_NOTE) == 0


def test_note_appears_for_a_label_only_in_the_other_pairs_table(harness: Harness) -> None:
    harness.source.prices[("2026-12-10", "2026-12-15")] = 9_000
    harness.source.prices[("2026-12-11", "2026-12-16")] = 8_000
    harness.source.flights[("2026-12-10", "2026-12-15")] = MARKED
    harness.source.flights[("2026-12-11", "2026-12-16")] = BR_DIRECT
    watch_id = flexible_round_trip(harness)
    harness.scan(watch_id)
    page = get(harness, f"/watches/{watch_id}")
    card = page.main.find_all("section", "price-card")[0]
    assert ROUND_TRIP not in card.text()  # the cheapest pair is not marked
    assert ROUND_TRIP in page.html
    assert page.count_visible(ROUND_TRIP_NOTE) == 1


def test_note_appears_for_an_other_currency_row(harness: Harness) -> None:
    harness.source.currency = "JPY"
    watch_id = marked_round_trip(harness)
    page = get(harness, f"/watches/{watch_id}")
    assert not page.main.find_all("section", "price-card")
    assert ROUND_TRIP in page.html
    assert page.count_visible(ROUND_TRIP_NOTE) == 1


def test_note_stays_when_only_departed_rows_are_marked(harness: Harness) -> None:
    watch_id = marked_round_trip(harness)
    harness.clock.advance(days=120)
    page = get(harness, f"/watches/{watch_id}")
    assert DETAIL_ALL_DEPARTED in page.html
    assert not page.main.find_all("section", "price-card")
    assert page.count_visible(ROUND_TRIP_NOTE) == 1
    assert page.count_in_details(ROUND_TRIP) >= 1  # only the folded records show it


def test_unmarked_old_and_no_price_pages_stay_silent(harness: Harness) -> None:
    empty = harness.create_watch()
    assert OVERHEAD_BIN_NOTE not in get(harness, f"/watches/{empty}").html
    watch_id = priced_round_trip(harness)
    one_way = priced_one_way(harness)
    for url in ("/", f"/watches/{watch_id}", f"/watches/{one_way}"):
        html = get(harness, url).html
        assert OVERHEAD_BIN_NOTE not in html, url
        assert ROUND_TRIP not in html and ONE_WAY not in html, url
        assert "含手提行李" not in html.replace(ROUND_TRIP_NOTE, ""), url


def test_exploration_calendar_top5_and_note(harness: Harness) -> None:
    harness.source.flight = MARKED
    service = harness.services.exploration
    exploration_id = _explored(harness, service)
    page = get(harness, f"/explorations/{exploration_id}")
    assert page.count_visible(ROUND_TRIP_NOTE) == 1
    calendar = page.main.find_all("table", "calendar")[0]
    assert ROUND_TRIP in calendar.text()
    flights = calendar.find_all(None, "flight")
    assert flights
    for flight in flights:
        assert ROUND_TRIP not in flight.text()
    tables = [t for t in page.main.find_all("table") if "calendar" not in t.classes]
    assert any(ROUND_TRIP in t.text() for t in tables)  # the top 5 table


def _explored(h: Harness, service: Any) -> int:
    # done_exploration() sets the flight itself, so its fixture is rebuilt here.
    from tests.conftest import CLIENT_HEADERS
    from tests.test_fd12_pages import MONTH

    queued: list[int] = []
    service.hooks.schedule = queued.append
    service.hooks.scheduler_running = lambda: True
    h.source.default_price = 6_000
    response = h.client.post("/api/explorations", json=MONTH, headers=CLIENT_HEADERS)
    assert response.status_code == 202
    while queued:
        service.run(queued.pop(0))
    return int(response.json()["id"])


def test_exploration_note_stays_for_mismatched_cells(harness: Harness) -> None:
    harness.source.flight = MARKED
    harness.source.currency = "JPY"
    exploration_id = _explored(harness, harness.services.exploration)
    page = get(harness, f"/explorations/{exploration_id}")
    assert RETURN_EXPLAIN not in page.html  # top5 is empty
    assert page.count_visible(ROUND_TRIP_NOTE) == 1


def test_top5_carries_the_order_note(harness: Harness) -> None:
    page = get(harness, f"/explorations/{done_exploration(harness)}")
    assert page.count_visible(COMPARISON_ORDER_NOTE) == 1
    assert OVERHEAD_BIN_NOTE not in page.html  # no mark, no note


def test_one_way_exploration_and_comparison_have_no_label(harness: Harness) -> None:
    for url in (
        f"/explorations/{one_way_exploration(harness)}",
        f"/comparisons/{one_way_comparison(harness)}",
    ):
        assert ONE_WAY not in get(harness, url).html, url


def test_comparison_row_and_note(harness: Harness) -> None:
    comparison_id = done_comparison(harness)
    assert OVERHEAD_BIN_NOTE not in get(harness, f"/comparisons/{comparison_id}").html


def test_marked_comparison_shows_label_and_note(harness: Harness) -> None:
    harness.source.default_price = 7_000
    harness.source.flight = MARKED
    comparison_id = compared(harness, ComparisonQueue(harness.services.comparison))
    page = get(harness, f"/comparisons/{comparison_id}")
    assert page.count_visible(ROUND_TRIP_NOTE) == 1
    assert ROUND_TRIP in page.html
    flights = page.main.find_all(None, "flight")
    assert flights
    for flight in flights:
        assert ROUND_TRIP not in flight.text()


# ---- messages (R4, R7) ---------------------------------------------------------------------------


def _alert(trip_type: str, marks: list[bool], **kwargs: Any) -> str:
    items = _items(len(marks))
    for item, mark in zip(items, marks, strict=True):
        object.__setattr__(item.candidate, "overhead_bin_excluded", True if mark else None)
    args: dict[str, Any] = {
        "watch_name": "沖繩",
        "origin": "TPE",
        "destination": "OKA",
        "trip_type": trip_type,
        "items": items,
        "links": [None] * len(marks),
    }
    return price_alert_message(**{**args, **kwargs})


def test_alert_label_follows_the_price_line_and_note_comes_last() -> None:
    text = _alert("round_trip", [True, False])
    lines = text.splitlines()
    first = next(i for i, line in enumerate(lines) if line.startswith("1. 查到"))
    assert lines[first + 1] == f"   {ROUND_TRIP}"
    assert lines[first + 2].startswith("   觸發原因")
    assert text.count(ROUND_TRIP) == 1
    assert OVERHEAD_BIN_NOTE not in text and text.count(ROUND_TRIP_NOTE) == 1
    assert text.endswith(f"{DISCLAIMER}\n{PRICE_SOURCE_NOTE}\n{ROUND_TRIP_NOTE}")


def test_alert_without_a_mark_is_unchanged() -> None:
    text = _alert("round_trip", [False])
    assert OVERHEAD_BIN_NOTE not in text and ROUND_TRIP not in text
    one_way = _alert("one_way", [True])
    assert f"   {ONE_WAY}" in one_way and ROUND_TRIP not in one_way
    assert one_way.endswith(f"{DISCLAIMER}\n{PRICE_SOURCE_NOTE}\n{OVERHEAD_BIN_NOTE}")


def test_fully_marked_alert_at_the_item_limit_still_fits() -> None:
    text = _alert(
        "round_trip",
        [True] * 5,  # LimitsConfig.alert_max_items
        watch_name="名" * 80,
        links=["https://www.google.com/travel/flights/search?tfs=" + "x" * 400] * 5,
        airlines=("BR", "CI", "JX"),
        dep_hour_from=6,
        dep_hour_to=22,
    )
    assert len(text) < MAX_MESSAGE_LENGTH
    assert text.endswith(ROUND_TRIP_NOTE)


def test_digest_has_no_label_or_note() -> None:
    text = daily_digest_message(
        day=_date(),
        sources=[],
        last_scan_at=None,
        failed_scans_24h=0,
        rows=[row("a")],
        stale_after_hours=12,
    )
    assert OVERHEAD_BIN_NOTE not in text and ROUND_TRIP not in text


def test_wording_stays_within_the_ruling() -> None:
    approved = [ROUND_TRIP_NOTE, OVERHEAD_BIN_NOTE, ROUND_TRIP, ONE_WAY]
    for phrase in BANNED_PHRASES:
        assert all(phrase not in text for text in approved), phrase
    for text in web_static_texts():
        leftover = text
        for sentence in approved:
            leftover = leftover.replace(sentence, "")
        for phrase in (
            "含手提行李",
            "不可攜帶",
            "不能帶",
            "免費手提",
            "須加購",
            "不含行李",
            "回程不含",
            "去程不含",
            "廉航",
            "低成本",
        ):
            assert phrase not in leftover, (phrase, text)


# ---- never ranks or triggers (R8, C-113) ---------------------------------------------------------


def test_rank_key_ignores_the_mark() -> None:
    base = PriceQuote(
        source="s",
        price_kind="live",
        depart_date=_date(),
        return_date=None,
        amount_minor=100,
        currency="TWD",
        as_of=_now(),
        as_of_basis="fetch_time",
        fetched_at=_now(),
        carrier=None,
        stops=None,
        duration_minutes=None,
        depart_time="08:00",
    )
    assert quote_rank_key(base) == quote_rank_key(replace(base, overhead_bin_excluded=True))


def test_mark_changes_neither_price_nor_trigger(harness: Harness) -> None:
    def scan(destination: str) -> tuple[list[int], str]:
        before = len(harness.notifier.sent)
        watch_id = harness.create_watch(destination=destination, name=destination)
        harness.scan(watch_id)
        assert len(harness.notifier.sent) == before + 1
        reason = next(line for line in harness.notifier.sent[-1].splitlines() if "觸發原因" in line)
        return [o.amount_minor for o in harness.repo.observations_for_watch(watch_id)], reason

    harness.source.prices[("2026-12-10", "2026-12-15")] = 9_000
    harness.source.flights[("2026-12-10", "2026-12-15")] = BR_DIRECT
    plain = scan("NRT")
    harness.source.flights[("2026-12-10", "2026-12-15")] = MARKED
    assert scan("KIX") == plain
    assert ROUND_TRIP in harness.notifier.sent[-1]


def test_marked_alert_carries_label_and_note(harness: Harness) -> None:
    marked_round_trip(harness)
    assert ROUND_TRIP in harness.notifier.sent[-1]
    assert ROUND_TRIP_NOTE in harness.notifier.sent[-1]


# ---- risk re-review: /watch limits, real message wording, moved delta note -----------------------


def _marked_rows(count: int = 3, **kwargs: Any) -> tuple[Any, ...]:
    return tuple(replace(watch_row(), overhead_bin_excluded=True, **kwargs) for _ in range(count))


def test_fully_marked_longest_watch_fits_with_every_note() -> None:
    longest = _marked_rows(
        carrier=f"{LONG_NAME}、{LONG_NAME}、{LONG_NAME}",
        flight_numbers="BR1001,BR1002,BR1003,BR1004,BR1005,BR1006",
        route_airports="TPE,HKG,BKK,SIN,KUL,MNL,NRT",
        stops=5,
        booking_note=BOOKING_FALLBACK_NOTE,
    )
    text = command_watch_message(detail(longest))
    assert len(text) <= COMMAND_REPLY_MAX_CHARS
    assert text.count(ROUND_TRIP) == 3
    assert text.endswith(ROUND_TRIP_NOTE)


def test_cut_watch_reply_keeps_the_note() -> None:
    long_link = "https://www.google.com/travel/flights/search?tfs=" + "x" * 3000
    text = command_watch_message(detail(_marked_rows(booking_url=long_link)))
    assert len(text) <= COMMAND_REPLY_MAX_CHARS
    assert text.count(long_link) < 3  # rows were dropped
    assert text.endswith(ROUND_TRIP_NOTE)


def test_real_telegram_output_stays_within_the_ruling() -> None:
    messages = [
        _alert("round_trip", [True, False]),
        _alert("one_way", [True]),
        command_watch_message(detail(_marked_rows())),
    ]
    for text in messages:
        leftover = text
        for sentence in (ROUND_TRIP_NOTE, OVERHEAD_BIN_NOTE, ROUND_TRIP, ONE_WAY):
            leftover = leftover.replace(sentence, "")
        for phrase in (
            "含手提行李",
            "手提行李",
            "不可攜帶",
            "不能帶",
            "免費手提",
            "須加購",
            "不含行李",
            "回程不含",
            "去程不含",
            "捷星不含",
            "長榮含",
            "換回程",
            "此價為分段",
            "非分段",
            "廉航",
            "低成本",
        ):
            assert phrase not in leftover, (phrase, text)


def test_delta_note_is_in_the_card_visible_and_after_the_button(harness: Harness) -> None:
    watch_id = cheaper_second_round(harness)
    page = get(harness, f"/watches/{watch_id}")
    sentence = WEB_TEXTS.delta_explain
    assert page.count_visible(sentence) == 1
    assert page.count_in_details(sentence) == 0
    card = page.main.find_all("section", "price-card")[0]
    nodes = list(card.descendants())
    note = next(n for n in nodes if "delta-explain" in n.classes)
    button = next(n for n in nodes if "cta" in n.classes)
    assert sentence in note.text()
    assert nodes.index(button) < nodes.index(note)


def test_delta_note_uses_body_text_styles() -> None:
    css = (Path(__file__).parents[1] / "src/flight_deals/web/static/app.css").read_text(
        encoding="utf-8"
    )
    assert (
        ".delta-explain > p { margin: 0; font-size: var(--text-base); color: var(--color-text); }"
        in css
    )

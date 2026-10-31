"""Comparison endpoints, result read model and watch prefill (ADR-0002 FD-9 Decision 4,
C-64, C-65, C-66)."""

from __future__ import annotations

import re
import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Any

import pytest

from flight_deals.domain.messages import (
    BANNED_PHRASES,
    COMPARISON_DEFERRED_NOTE,
    COMPARISON_NO_PRICE_NOTE,
    COMPARISON_NOT_FOUND,
    COMPARISON_ORDER_NOTE,
    COMPARISON_PREFILL_MISSING,
    COMPARISON_PREFILL_OK,
    COMPARISON_REFERENCE_NOTE,
    COMPARISON_ROW_LABELS,
    COMPARISON_SINGLE_DATE_NOTE,
    DISCLAIMER,
    all_static_texts,
    comparison_age_note,
    comparison_created_ago,
    comparison_reused_note,
    comparison_static_texts,
    comparison_unfinished_note,
    exploration_age_note,
)
from flight_deals.domain.models import FlightSearch, PriceQuote
from flight_deals.domain.trip_labels import BOOKING_FALLBACK_NOTE
from flight_deals.ports import SourceResult
from flight_deals.services.comparison_views import comparison_order, row_label
from flight_deals.storage.repository import ComparisonCellRecord
from tests.conftest import CLIENT_HEADERS, Harness
from tests.test_comparison_service import TRIP, Queue, compared, set_limit, start, table_rows

SRC = Path(__file__).resolve().parents[1] / "src" / "flight_deals"
ROW_KEYS = {
    "position",
    "destination",
    "destination_label",
    "status",
    "label",
    "priced",
    "amount_label",
    "pax_note",
    "rank_note",
    "carrier",
    "stops_label",
    "duration_label",
    "depart_time",
    "fetched_at_label",
    "booking_url",
    "booking_note",
    "watch_url",
}
# AC-S1 plus the remaining row kinds, in input order.
SIX = ["NRT", "OSA", "SEL", "BKK", "SIN", "HKG"]


@pytest.fixture
def queue(harness: Harness) -> Queue:
    return Queue(harness.services.comparison)


class FakeLinks:
    def __init__(self) -> None:
        self.fail = False

    def url(self, search: FlightSearch) -> str | None:
        if self.fail:
            raise RuntimeError("no tfs")
        return f"https://www.google.com/travel/flights/search?tfs={search.destination}"


@pytest.fixture
def links(harness: Harness) -> FakeLinks:
    fake = FakeLinks()
    harness.services.comparison_views._links = fake
    return fake


def mixed_handler(harness: Harness) -> Any:
    """NRT 9,200 / OSA 7,800 / SEL USD / BKK no data / SIN blocked (5 queries)."""

    def handler(query: FlightSearch) -> SourceResult:
        now = harness.clock()
        code = query.destination
        if code == "BKK":
            return SourceResult("google_flights", "no_data", now)
        if code == "SIN":
            return SourceResult("google_flights", "blocked", now, error="captcha")
        amount, currency = {"NRT": (920_000, "TWD"), "OSA": (780_000, "TWD")}.get(
            code, (30_000, "USD")
        )
        quote = PriceQuote(
            source="google_flights",
            price_kind="live",
            depart_date=query.pair.depart,
            return_date=query.pair.return_date,
            amount_minor=amount,
            currency=currency,
            as_of=now,
            as_of_basis="fetch_time",
            fetched_at=now,
            carrier="長榮航空",
            stops=0 if code == "NRT" else 1,
            duration_minutes=205,
            depart_time="07:55",
        )
        return SourceResult("google_flights", "ok", now, quotes=(quote,))

    return handler


def mixed(harness: Harness, queue: Queue) -> int:
    """Six destinations; the hour runs out after five, so HKG is skipped."""
    harness.source.handler = mixed_handler(harness)
    comparison_id = start(harness, destinations=SIX)
    set_limit(harness, 5)
    queue.run_all()
    set_limit(harness, 60)
    return comparison_id


def cell(position: int, status: str, amount: int | None = None, **extra: Any) -> Any:
    values: dict[str, Any] = {
        "comparison_id": 1,
        "position": position,
        "destination": f"A{position}A",
        "status": status,
        "reason": None,
        "source": "google_flights",
        "price_kind": "live",
        "from_cache": False,
        "attempts": 1,
        "amount_minor": amount,
        "currency": "TWD" if amount is not None else None,
        "carrier": None,
        "stops": None,
        "duration_minutes": None,
        "depart_time": None,
        "as_of": None,
        "fetched_at": None,
        "error": None,
    }
    values.update(extra)
    return ComparisonCellRecord(**values)


# ---- pure ordering (C-65) ----------


def test_order_by_price_then_unpriced_by_position() -> None:  # AC-S1
    cells = [
        cell(0, "ok", 920_000),
        cell(1, "ok", 780_000),
        cell(2, "ok", 1_100_000),
        cell(3, "no_data"),
        cell(4, "blocked"),
    ]
    assert [c.position for c in comparison_order(cells, "TWD")] == [1, 0, 2, 3, 4]


def test_ties_keep_input_order() -> None:  # AC-S2
    cells = [cell(0, "no_data"), cell(1, "ok", 800_000), cell(2, "ok", 800_000)]
    assert [c.position for c in comparison_order(cells, "TWD")] == [1, 2, 0]


def test_currency_mismatch_after_priced_rows() -> None:
    cells = [
        cell(0, "ok", 30_000, currency="USD", reason="currency_mismatch"),
        cell(1, "skipped", reason="global_hourly_limit"),
        cell(2, "ok", 900_000),
    ]
    assert [c.position for c in comparison_order(cells, "TWD")] == [2, 0, 1]


@pytest.mark.parametrize(
    "record,expected",
    [
        (cell(0, "no_data"), "no_data"),
        (cell(0, "no_data", reason="no_embedded_results"), "no_embedded_results"),
        (cell(0, "blocked"), "blocked"),
        (cell(0, "error"), "error"),
        (cell(0, "skipped", reason="global_hourly_limit"), "global_hourly_limit"),
        (cell(0, "skipped", reason="breaker_open"), "breaker_open"),
        (cell(0, "skipped", reason="interrupted"), "interrupted"),
        (cell(0, "skipped", reason=None), "interrupted"),
        (cell(0, "pending"), "pending"),
        (cell(0, "ok", 100, reason="currency_mismatch"), "currency_mismatch"),
    ],
)
def test_every_row_has_a_reason(record: Any, expected: str) -> None:  # AC-S3
    label = row_label(record)
    assert label == COMPARISON_ROW_LABELS[expected]
    assert label.strip() and label != "0"


# ---- result read model (C-65) ----------


def test_result_rows(harness: Harness, queue: Queue, links: FakeLinks) -> None:  # AC-S1, S3
    comparison_id = mixed(harness, queue)
    data = harness.services.comparison_views.comparison_page(comparison_id)
    rows = data["rows"]
    assert all(set(r) == ROW_KEYS for r in rows)
    assert [r["destination"] for r in rows] == ["OSA", "NRT", "SEL", "BKK", "SIN", "HKG"]
    assert [r["amount_label"] for r in rows[:2]] == ["TWD 7,800", "TWD 9,200"]
    assert rows[0]["pax_note"] == "（1 人總價）" and rows[0]["stops_label"] == "轉機 1 次"
    assert rows[1]["stops_label"] == "直飛" and rows[1]["duration_label"] == "3 小時 25 分"
    assert rows[1]["carrier"] == "長榮航空" and rows[1]["depart_time"] == "07:55"
    assert rows[1]["destination_label"].endswith("NRT") and rows[1]["fetched_at_label"]
    assert rows[2]["rank_note"] == COMPARISON_ROW_LABELS["currency_mismatch"]
    labels = {r["destination"]: r["label"] for r in rows}
    assert labels["BKK"] == COMPARISON_ROW_LABELS["no_data"]
    assert labels["SIN"] == COMPARISON_ROW_LABELS["blocked"]
    assert labels["HKG"] == COMPARISON_ROW_LABELS["global_hourly_limit"]
    for row in rows:
        if row["status"] == "skipped":
            assert row["booking_url"] is None and row["watch_url"] is None
        else:
            assert row["booking_url"].endswith(f"tfs={row['destination']}")
            assert row["watch_url"] == (
                f"/watches/new?from_comparison={comparison_id}&destination={row['destination']}"
            )
            assert row["booking_note"] is None


def test_builder_failure_falls_back_to_text_link(
    harness: Harness, queue: Queue, links: FakeLinks
) -> None:
    links.fail = True
    comparison_id = compared(harness, queue)
    rows = harness.services.comparison_views.comparison_page(comparison_id)["rows"]
    assert all(r["booking_url"].startswith("https://www.google.com/travel/flights?") for r in rows)
    assert {r["booking_note"] for r in rows} == {BOOKING_FALLBACK_NOTE}


def test_summary_and_notes(harness: Harness, queue: Queue) -> None:  # AC-S4
    comparison_id = compared(harness, queue, max_stops="0", cabin="business")
    data = harness.services.comparison_views.comparison_page(comparison_id)
    c = data["comparison"]
    assert c["pax_label"] == "1 位成人" and c["pax_note"] == "（1 人總價）"
    assert c["dates_label"] == "2026-12-10 出發，2026-12-15 回程"
    assert (c["max_stops_label"], c["cabin_label"], c["trip_type_label"]) == (
        "僅直飛",
        "商務艙",
        "來回",
    )
    assert data["disclaimer"] == DISCLAIMER and data["reference_note"] == COMPARISON_REFERENCE_NOTE
    assert data["order_note"] == COMPARISON_ORDER_NOTE
    assert data["no_price_note"] == COMPARISON_NO_PRICE_NOTE  # risk R1: always present
    assert data["single_date_note"] == COMPARISON_SINGLE_DATE_NOTE  # risk r4
    assert c["stale"] is False and c["reused_note"] is None and c["error_summary"] is None
    assert c["deferred_note"] is None


def test_page_text(harness: Harness, queue: Queue, links: FakeLinks) -> None:  # C-65
    comparison_id = mixed(harness, queue)
    page = harness.client.get(f"/comparisons/{comparison_id}")
    assert page.status_code == 200
    text = page.text
    for snippet in ("1 位成人", "（1 人總價）", DISCLAIMER, COMPARISON_REFERENCE_NOTE, "TWD 7,800"):
        assert snippet in text, snippet
    assert re.search(r'href="/explore"[^>]*aria-current="page"', text)
    unfinished = comparison_unfinished_note(5, 6, "已達全域每小時查詢上限，1 個目的地未查")
    assert unfinished in text  # AC-S7


def test_stale_note_after_24_hours(harness: Harness, queue: Queue) -> None:  # AC-S5
    comparison_id = compared(harness, queue)
    harness.clock.advance(hours=25)
    data = harness.services.comparison_views.comparison_page(comparison_id)
    assert data["comparison"]["stale"] is True
    assert data["comparison"]["stale_note"] == comparison_age_note(25)
    assert comparison_age_note(25) == exploration_age_note(25)
    text = harness.client.get(f"/comparisons/{comparison_id}").text
    assert comparison_age_note(25) in text
    assert "這是較早前查到的價格" not in text  # risk r6: no template fallback


def test_reused_note_only_for_done(harness: Harness, queue: Queue) -> None:  # AC-K1
    comparison_id = compared(harness, queue)
    harness.clock.advance(hours=3)
    body = harness.client.post("/api/comparisons", json=TRIP, headers=CLIENT_HEADERS).json()
    assert body == {"ok": True, "id": comparison_id, "reused": True}
    page = harness.client.get(f"/comparisons/{comparison_id}?reused=1").text
    assert comparison_reused_note(3) in page
    assert comparison_reused_note(3) not in harness.client.get(f"/comparisons/{comparison_id}").text
    harness.repo.finish_comparison(
        comparison_id,
        status="failed",
        finished_at=harness.clock(),
        skip_reason="interrupted",
        error_summary="x",
    )
    data = harness.services.comparison_views.comparison_page(comparison_id, reused=True)
    assert data["comparison"]["reused_note"] is None


def test_running_page_has_progress_and_deferred_note(harness: Harness, queue: Queue) -> None:
    comparison_id = start(harness)
    data = harness.services.comparison_views.comparison_page(comparison_id)
    assert data["comparison"]["deferred_note"] == COMPARISON_DEFERRED_NOTE
    text = harness.client.get(f"/comparisons/{comparison_id}").text
    assert 'id="comparison-progress"' in text
    assert f'data-status-url="/api/comparisons/{comparison_id}/status"' in text


def test_missing_comparison_page(harness: Harness) -> None:  # C-64, AC-K4
    response = harness.client.get("/comparisons/999")
    assert response.status_code == 404 and COMPARISON_NOT_FOUND in response.text


# ---- SQL counts (C-65) ----------


@contextmanager
def traced(harness: Harness, monkeypatch: pytest.MonkeyPatch) -> Iterator[list[str]]:
    statements: list[str] = []
    database = harness.repo.db
    real = database.connect

    @contextmanager
    def tracing() -> Iterator[sqlite3.Connection]:
        with real() as conn:
            conn.set_trace_callback(statements.append)
            yield conn

    monkeypatch.setattr(database, "connect", tracing)
    yield statements
    monkeypatch.setattr(database, "connect", real)


def queries(statements: list[str]) -> list[str]:
    return [s for s in statements if not s.lstrip().upper().startswith("PRAGMA")]


def test_comparison_page_runs_two_statements(
    harness: Harness, queue: Queue, monkeypatch: pytest.MonkeyPatch
) -> None:
    comparison_id = compared(harness, queue)
    with traced(harness, monkeypatch) as statements:
        assert harness.services.comparison_views.comparison_page(comparison_id) is not None
    assert len(queries(statements)) == 2, statements


def test_compare_page_statements_do_not_grow(
    harness: Harness, queue: Queue, monkeypatch: pytest.MonkeyPatch
) -> None:
    compared(harness, queue)
    with traced(harness, monkeypatch) as statements:
        harness.services.comparison_views.compare_page()
    few = len(queries(statements))
    for index in range(6):
        compared(
            harness, queue, destinations=["NRT", ["OSA", "SEL", "BKK", "SIN", "HKG", "MNL"][index]]
        )
    with traced(harness, monkeypatch) as statements:
        data = harness.services.comparison_views.compare_page()
    assert len(data["recent"]) == 7
    assert len(queries(statements)) == few


# ---- compare page (C-64) ----------


def test_compare_page_context_and_html(harness: Harness, queue: Queue) -> None:
    data = harness.services.comparison_views.compare_page()
    values = data["values"]
    assert (values["origin"], values["trip_type"], values["cabin"]) == (
        "TPE",
        "round_trip",
        "economy",
    )
    assert values["destinations"] == [] and "adults" not in values  # AC-C2
    assert data["quota"] == {
        "hourly_left": 60,
        "reserve": 12,
        "available": 48,
        "min_destinations": 2,
        "max_destinations": 8,
    }
    assert data["active"] is None and data["recent"] == []
    assert (data["today"], data["max_date"]) == ("2026-10-25", "2027-10-25")
    page = harness.client.get("/explore/compare")
    assert page.status_code == 200 and DISCLAIMER in page.text
    assert re.search(r'href="/explore"[^>]*aria-current="page"', page.text)
    assert 'name="adults"' not in page.text


def test_nav_item_count_unchanged(harness: Harness) -> None:  # C-64
    def nav_links(html: str) -> list[str]:
        nav = re.search(r'<nav class="site-nav".*?</nav>', html, re.S)
        assert nav is not None
        return re.findall(r"<a ", nav.group(0))

    home = nav_links(harness.client.get("/").text)
    assert len(home) == 5
    assert len(nav_links(harness.client.get("/explore/compare").text)) == 5


def test_recent_rows_and_active(harness: Harness, queue: Queue) -> None:  # AC-K5
    prices = {"NRT": 9000, "OSA": 8000, "SEL": 9500}
    harness.source.price_fn = lambda q: prices[q.destination]
    done = compared(harness, queue)
    running = start(harness, destinations=["BKK", "SIN"])
    data = harness.services.comparison_views.compare_page()
    assert data["active"] == {
        "kind": "comparison",
        "id": running,
        "done": 0,
        "total": 2,
        "url": f"/comparisons/{running}",
    }
    by_id = {r["id"]: r for r in data["recent"]}
    row = by_id[done]
    assert row["url"] == f"/comparisons/{done}" and row["destination_count"] == 3
    assert row["cheapest_label"] == "TWD 8,000（1 人總價）"
    assert row["cheapest_destination_label"].endswith("OSA")
    assert row["status_label"] == "已完成" and row["finished_at_label"]
    assert by_id[running]["cheapest_label"] is None
    # Risk r3: progress for unfinished rows, age only past 24 hours.
    assert row["progress_label"] is None and row["age_note"] is None
    assert by_id[running]["progress_label"] == "已查 0／共 2"
    harness.clock.advance(hours=30)
    aged = {r["id"]: r for r in harness.services.comparison_views.compare_page()["recent"]}
    assert aged[done]["age_note"] == comparison_created_ago(30)
    assert harness.services.exploration_views.explore_page()["active_comparison"] == {
        "id": running,
        "done": 0,
        "total": 2,
    }
    assert harness.services.views.settings_page()["active_comparison"] == {
        "id": running,
        "done": 0,
        "total": 2,
    }


def test_active_exploration_shown_on_compare_page(harness: Harness) -> None:
    from tests.test_exploration_service import DECEMBER
    from tests.test_exploration_service import Queue as ExploreQueue

    ExploreQueue(harness.services.exploration)
    exploration_id = harness.client.post(
        "/api/explorations", json=DECEMBER, headers=CLIENT_HEADERS
    ).json()["id"]
    active = harness.services.comparison_views.compare_page()["active"]
    assert active["kind"] == "exploration" and active["url"] == f"/explorations/{exploration_id}"


# ---- status endpoint and write protection (C-64) ----------


def test_status_endpoint_whitelist_no_store_no_header(harness: Harness, queue: Queue) -> None:
    comparison_id = start(harness)
    before = {t: table_rows(harness, t) for t in ("comparison", "comparison_cell")}
    response = harness.client.get(f"/api/comparisons/{comparison_id}/status")
    assert response.status_code == 200
    assert response.headers["cache-control"] == "no-store"
    assert response.json() == {
        "comparison_id": comparison_id,
        "status": "queued",
        "total": 3,
        "done": 0,
    }
    assert {t: table_rows(harness, t) for t in before} == before
    missing = harness.client.get("/api/comparisons/999/status")
    assert missing.status_code == 404 and missing.headers["cache-control"] == "no-store"
    assert missing.json() == {"ok": False, "errors": {"_": COMPARISON_NOT_FOUND}}


def test_post_without_header_is_403(harness: Harness, queue: Queue) -> None:
    response = harness.client.post("/api/comparisons", json=TRIP)
    assert response.status_code == 403
    assert table_rows(harness, "comparison") == [] and queue.ids == []


# ---- new-watch prefill (FR-W1, C-64) ----------


def watch_count(harness: Harness) -> int:
    return len(table_rows(harness, "watch"))


@pytest.mark.parametrize(
    "query",
    [
        "from_comparison=abc&destination=NRT",
        "from_comparison=999&destination=NRT",
        "from_comparison={id}&destination=KIX",
        "from_comparison={id}&destination=HKG",  # skipped row
        "from_comparison={id}",
    ],
)
def test_prefill_missing_gives_blank_form(harness: Harness, queue: Queue, query: str) -> None:
    comparison_id = mixed(harness, queue)
    response = harness.client.get(f"/watches/new?{query.format(id=comparison_id)}")
    assert response.status_code == 200
    assert COMPARISON_PREFILL_MISSING in response.text
    assert watch_count(harness) == 0


def test_prefill_values(harness: Harness, queue: Queue) -> None:  # AC-W1
    comparison_id = compared(harness, queue, max_stops="0", cabin="premium_economy")
    base = harness.services.views.form_values(None)
    values, note, sampled = harness.services.comparison_views.watch_prefill(
        base, str(comparison_id), "osa"
    )
    assert note == COMPARISON_PREFILL_OK and sampled is None
    expected = {
        "origin": "TPE",
        "destination": "OSA",
        "trip_type": "round_trip",
        "date_mode": "fixed",
        "depart_date": "2026-12-10",
        "return_date": "2026-12-15",
        "max_stops": "0",
        "adults": 1,
        "children": 0,
        "cabin": "premium_economy",
        "airlines": [],
        "dep_hour_from": None,
        "dep_hour_to": None,
        "budget": "",
        "name": "",
        "window_start": "",
        "window_end": "",
        "min_trip_days": "",
        "max_trip_days": "",
    }
    assert {k: values[k] for k in expected} == expected
    assert set(values) == set(base)
    page = harness.client.get(f"/watches/new?from_comparison={comparison_id}&destination=OSA")
    assert page.status_code == 200 and COMPARISON_PREFILL_OK in page.text
    assert watch_count(harness) == 0


def test_prefill_also_for_unpriced_rows(harness: Harness, queue: Queue) -> None:  # FR-W1
    comparison_id = mixed(harness, queue)
    base = harness.services.views.form_values(None)
    for code in ("BKK", "SIN", "SEL"):
        _, note, _ = harness.services.comparison_views.watch_prefill(base, str(comparison_id), code)
        assert note == COMPARISON_PREFILL_OK, code


def test_exploration_prefill_takes_precedence(harness: Harness, queue: Queue) -> None:
    comparison_id = compared(harness, queue)
    page = harness.client.get(
        f"/watches/new?from_exploration=999&from_comparison={comparison_id}&destination=NRT"
    )
    assert COMPARISON_PREFILL_OK not in page.text


# ---- wording (C-66) ----------

EXTRA_BANNED = ("建議", "最佳", "現在買", "划算", "推薦")


def test_banned_list_has_fd9_additions() -> None:
    assert "推薦" in BANNED_PHRASES and "最佳" in BANNED_PHRASES


def test_comparison_texts_are_in_static_texts_and_clean() -> None:
    texts = all_static_texts()
    for text in comparison_static_texts():
        assert text in texts
        for phrase in (*BANNED_PHRASES, *EXTRA_BANNED):
            assert phrase not in text, (phrase, text)


def test_templates_and_script_have_no_advisory_words() -> None:
    surfaces = [
        SRC / "web" / "templates" / "compare.html",
        SRC / "web" / "templates" / "comparison.html",
        SRC / "web" / "static" / "app.js",
    ]
    for path in surfaces:
        text = path.read_text(encoding="utf-8")
        for phrase in EXTRA_BANNED:
            assert phrase not in text, (path.name, phrase)


def test_page_has_no_advisory_words(harness: Harness, queue: Queue) -> None:
    comparison_id = mixed(harness, queue)
    for url in (f"/comparisons/{comparison_id}", "/explore/compare"):
        text = harness.client.get(url).text
        for phrase in (*BANNED_PHRASES, *EXTRA_BANNED):
            assert phrase not in text, (url, phrase)

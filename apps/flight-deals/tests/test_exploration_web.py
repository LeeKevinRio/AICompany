"""Exploration endpoints, calendar read model and watch prefill (FD-6, C-46, C-47)."""

from __future__ import annotations

import re
from dataclasses import replace
from datetime import date, timedelta
from pathlib import Path
from typing import Any

import pytest

from flight_deals.domain.dates import expand_pairs
from flight_deals.domain.messages import (
    BANNED_PHRASES,
    DISCLAIMER,
    EXPLORATION_CELL_LABELS,
    EXPLORATION_NOT_FOUND,
    EXPLORATION_PREFILL_MISSING,
    EXPLORATION_PREFILL_OK,
    EXPLORATION_REFERENCE_NOTE,
    all_static_texts,
    exploration_age_note,
)
from flight_deals.domain.models import FlightSearch
from flight_deals.domain.trip_labels import BOOKING_FALLBACK_NOTE
from flight_deals.domain.validation import validate_watch_input
from flight_deals.ports import SourceResult
from flight_deals.services.exploration_views import cell_label
from flight_deals.services.views import NO_MATCH_LABEL, price_levels
from tests.conftest import CLIENT_HEADERS, Harness
from tests.test_exploration_service import DECEMBER, Queue, post, start

SRC = Path(__file__).resolve().parents[1] / "src" / "flight_deals"
CELL_KEYS = {
    "date",
    "day",
    "weekday_label",
    "status",
    "label",
    "amount_label",
    "carrier",
    "stops_label",
    "depart_time",
    "level",
    "booking_url",
    "booking_note",
    "watch_url",
    "return_date",
    "rank_note",
}


@pytest.fixture
def queue(harness: Harness) -> Queue:
    return Queue(harness.services.exploration)


class FakeLinks:
    def __init__(self) -> None:
        self.fail = False

    def url(self, search: FlightSearch) -> str | None:
        if self.fail:
            raise RuntimeError("no tfs")
        ret = search.pair.return_date.isoformat() if search.pair.return_date else "-"
        return f"https://www.google.com/travel/flights/search?tfs={search.pair.depart}_{ret}"


@pytest.fixture
def links(harness: Harness) -> FakeLinks:
    fake = FakeLinks()
    harness.services.exploration_views._links = fake
    return fake


def explored(harness: Harness, queue: Queue, **overrides: Any) -> int:
    exploration_id = start(harness, **overrides)
    queue.run_all()
    return exploration_id


def flat_cells(page: dict[str, Any]) -> list[dict[str, Any]]:
    return [c for week in page["weeks"] for c in week if c is not None]


# ---- status endpoint and pages (C-46) ------------------------------------------------


def test_status_endpoint_whitelist_no_store_no_header(harness: Harness, queue: Queue) -> None:
    exploration_id = start(harness)
    before = len(harness.source.calls)
    response = harness.client.get(f"/api/explorations/{exploration_id}/status")
    assert response.status_code == 200
    assert response.headers["cache-control"] == "no-store"
    assert response.json() == {
        "exploration_id": exploration_id,
        "status": "queued",
        "total": 31,
        "done": 0,
    }
    queue.run_all()
    body = harness.client.get(f"/api/explorations/{exploration_id}/status").json()
    assert (body["status"], body["done"]) == ("done", 31)
    assert len(harness.source.calls) == before + 31  # only the job queried
    missing = harness.client.get("/api/explorations/999/status")
    assert missing.status_code == 404 and missing.headers["cache-control"] == "no-store"


def test_status_endpoint_writes_nothing(harness: Harness, queue: Queue) -> None:
    exploration_id = start(harness)
    with harness.repo.db.connect() as conn:
        before = conn.total_changes
    database = harness.repo.db
    real = database.connect
    changes: list[int] = []
    from contextlib import contextmanager

    @contextmanager
    def counting() -> Any:
        with real() as conn:
            yield conn
            changes.append(conn.total_changes)

    database.connect = counting
    try:
        harness.client.get(f"/api/explorations/{exploration_id}/status")
    finally:
        database.connect = real
    assert changes and all(c == 0 for c in changes) and before == 0


def test_post_requires_client_header(harness: Harness, queue: Queue) -> None:
    response = harness.client.post("/api/explorations", json=DECEMBER)
    assert response.status_code == 403
    assert queue.ids == []


def test_post_invalid_is_422_and_creates_nothing(harness: Harness, queue: Queue) -> None:
    response = post(harness, destination="", trip_days=31)
    assert response.status_code == 422
    errors = response.json()["errors"]
    assert set(errors) == {"destination", "trip_days"}
    assert queue.ids == [] and harness.source.calls == []


def test_unknown_exploration_page_is_404_with_message(harness: Harness) -> None:
    response = harness.client.get("/explorations/999")
    assert response.status_code == 404
    assert EXPLORATION_NOT_FOUND in response.text


def test_explore_page_context(harness: Harness, queue: Queue) -> None:
    data = harness.services.exploration_views.explore_page()
    values = data["values"]
    assert (values["origin"], values["trip_type"], values["trip_days"]) == ("TPE", "round_trip", 5)
    assert (values["adults"], values["children"], values["cabin"]) == (1, 0, "economy")
    assert values["airlines"] == [] and values["dep_hour_from"] is None
    assert len(data["month_options"]) == 12
    assert data["month_options"][0] == {"value": "2026-10", "label": "2026 年 10 月"}
    quota = {k: v for k, v in data["quota"].items() if k != "weekday_counts"}  # FD-10
    assert quota == {"hourly_left": 60, "reserve": 12, "max_cells": 31}
    assert data["active"] is None and data["recent"] == [] and data["today"] == "2026-10-25"
    exploration_id = start(harness)
    data = harness.services.exploration_views.explore_page()
    assert data["active"] == {"id": exploration_id, "done": 0, "total": 31}
    page = harness.client.get("/explore")
    assert page.status_code == 200 and 'href="/explore"' in page.text  # nav entry
    settings = harness.client.get("/settings").text
    assert "exploration_reserve_for_scans" in settings  # editable, default 12


def test_recent_list_shows_cheapest_and_hides_old(harness: Harness, queue: Queue) -> None:
    harness.source.prices[("2026-12-07", "2026-12-12")] = 8_000
    exploration_id = explored(harness, queue)
    [row] = harness.services.exploration_views.explore_page()["recent"]
    assert row["id"] == exploration_id and row["month"] == "2026 年 12 月"
    assert row["status_label"] == "已完成" and (row["done"], row["total"]) == (31, 31)
    assert row["cheapest_label"] == "TWD 8,000（1 人總價）"
    harness.clock.advance(days=7, minutes=1)
    assert harness.services.exploration_views.explore_page()["recent"] == []


# ---- calendar read model (C-47) --------------------------------------------------------


def test_calendar_structure_levels_and_links(
    harness: Harness, queue: Queue, links: FakeLinks
) -> None:
    for day, price in ((1, 5_000), (2, 6_000), (3, 7_000)):
        harness.source.prices[(f"2026-12-0{day}", f"2026-12-0{day + 5}")] = price
    exploration_id = explored(harness, queue)
    page = harness.services.exploration_views.exploration_page(exploration_id)
    assert page is not None
    weeks = page["weeks"]
    assert all(len(w) == 7 for w in weeks)
    assert weeks[0][0] is None and weeks[0][1]["date"] == "2026-12-01"  # Tuesday
    cells = flat_cells(page)
    assert len(cells) == 31 and all(set(c) == CELL_KEYS for c in cells)
    first = cells[0]
    assert first["day"] == 1 and first["weekday_label"] == "週二"
    assert first["status"] == "ok" and first["label"] == EXPLORATION_CELL_LABELS["ok"]
    assert first["amount_label"] == "TWD 5,000" and first["carrier"] == "測試航空"
    assert first["stops_label"] == "直飛" and first["level"] == "低"
    assert first["return_date"] == "2026-12-06"
    assert first["booking_url"].endswith("tfs=2026-12-01_2026-12-06")
    assert first["booking_note"] is None
    assert first["watch_url"] == f"/watches/new?from_exploration={exploration_id}&depart=2026-12-01"
    assert {c["level"] for c in cells} == {"低", "中", "高"}
    exploration = page["exploration"]
    assert exploration["pax_note"] == "（1 人總價）"
    assert exploration["month_watch_url"] == (
        f"/watches/new?from_exploration={exploration_id}&mode=month"
    )
    assert EXPLORATION_REFERENCE_NOTE in page["disclaimer"] and DISCLAIMER in page["disclaimer"]
    html = harness.client.get(f"/explorations/{exploration_id}").text
    assert "探索結果為查詢當下參考值" in html and DISCLAIMER in html and "1 人總價" in html


def test_top5_order_ties_and_exclusions(harness: Harness, queue: Queue) -> None:  # AC-S4
    harness.source.default_price = None  # no_data unless priced below
    prices = {3: 9_000, 9: 7_000, 4: 7_000, 20: 8_000, 1: 12_000, 15: 6_500, 28: 11_000, 30: 9_500}
    for day, price in prices.items():
        depart = date(2026, 12, day)
        harness.source.prices[(depart.isoformat(), (depart + timedelta(days=5)).isoformat())] = (
            price
        )
    exploration_id = explored(harness, queue)
    page = harness.services.exploration_views.exploration_page(exploration_id)
    top = [(t["date"], t["amount_label"]) for t in page["top5"]]
    assert top == [
        ("2026-12-15", "TWD 6,500"),
        ("2026-12-04", "TWD 7,000"),  # same price: earlier date first
        ("2026-12-09", "TWD 7,000"),
        ("2026-12-20", "TWD 8,000"),
        ("2026-12-03", "TWD 9,000"),
    ]
    assert all(set(t) == CELL_KEYS for t in page["top5"])
    empty = [c for c in flat_cells(page) if c["status"] == "no_data"]
    assert empty and {c["label"] for c in empty} == {EXPLORATION_CELL_LABELS["no_data"]}
    assert all(c["amount_label"] is None and c["booking_url"] for c in empty)


def test_top5_fewer_and_none(harness: Harness, queue: Queue) -> None:  # AC-S5
    harness.source.default_price = None
    exploration_id = explored(harness, queue)
    assert harness.services.exploration_views.exploration_page(exploration_id)["top5"] == []
    assert "沒有查到價格" in harness.client.get(f"/explorations/{exploration_id}").text


def test_currency_mismatch_is_shown_but_not_ranked(harness: Harness, queue: Queue) -> None:
    harness.source.currency = "JPY"
    exploration_id = explored(harness, queue, month="2026-10")
    page = harness.services.exploration_views.exploration_page(exploration_id)
    assert page["top5"] == []
    cells = [c for c in flat_cells(page) if c["status"] == "ok"]
    assert cells and {c["label"] for c in cells} == {EXPLORATION_CELL_LABELS["currency_mismatch"]}
    assert all(c["level"] is None for c in cells)
    assert {c["rank_note"] for c in cells} == {EXPLORATION_CELL_LABELS["currency_mismatch"]}
    html = harness.client.get(f"/explorations/{exploration_id}").text
    assert EXPLORATION_CELL_LABELS["currency_mismatch"] in html  # shown next to the amount


def test_every_no_price_label(harness: Harness, queue: Queue) -> None:  # AC-S3
    outcomes = {
        "2026-10-25": ("no_data", {"reason": "no_embedded_results"}),
        "2026-10-26": ("blocked", {}),
        "2026-10-27": ("error", {}),
        "2026-10-28": ("no_data", {}),
    }

    def handler(query: FlightSearch) -> SourceResult:
        status, extra = outcomes.get(query.pair.depart.isoformat(), ("no_data", {}))
        return SourceResult("google_flights", status, harness.clock(), extra=extra)  # type: ignore[arg-type]

    harness.source.handler = handler
    exploration_id = explored(harness, queue, month="2026-10")
    page = harness.services.exploration_views.exploration_page(exploration_id)
    by_date = {c["date"]: c for c in flat_cells(page)}
    assert by_date["2026-10-24"]["label"] == EXPLORATION_CELL_LABELS["past"]
    assert by_date["2026-10-24"]["status"] == "not_queried"
    assert by_date["2026-10-24"]["booking_url"] is None
    assert by_date["2026-10-25"]["label"] == "未內嵌結果"
    assert by_date["2026-10-25"]["booking_url"]  # manual check still possible (FR-S4)
    assert by_date["2026-10-26"]["label"] == "被擋"
    assert by_date["2026-10-27"]["label"] == "錯誤"
    assert by_date["2026-10-28"]["label"] == "無資料"
    assert all(c["label"] for c in flat_cells(page))  # never blank (FR-S2)


def test_filtered_no_data_and_skipped_labels(harness: Harness, queue: Queue) -> None:
    harness.source.default_price = None
    exploration_id = explored(harness, queue, month="2026-10", airlines=["BR"])
    page = harness.services.exploration_views.exploration_page(exploration_id)
    queried = [c for c in flat_cells(page) if c["status"] == "no_data"]
    assert {c["label"] for c in queried} == {NO_MATCH_LABEL}
    cell = harness.repo.exploration_cells(exploration_id)[0]
    expected = {
        "global_hourly_limit": "額度不足略過",
        "breaker_open": "資料源暫停略過",
        "interrupted": "中斷未查",
    }
    for reason, label in expected.items():
        assert cell_label(replace(cell, status="skipped", reason=reason), False) == label
    assert cell_label(replace(cell, status="pending", reason=None), False) == "查詢中"


def test_unfinished_header_and_out_of_range(harness: Harness, queue: Queue) -> None:  # AC-S10
    exploration_id = start(harness)
    harness.services.exploration.recover_interrupted()
    page = harness.services.exploration_views.exploration_page(exploration_id)
    exploration = page["exploration"]
    assert exploration["status_label"] == "已中斷"
    assert exploration["error_summary"].startswith("探索未完成（已查 0／共 31），原因：")
    assert {c["label"] for c in flat_cells(page)} == {"中斷未查"}


def test_out_of_range_days_are_labelled(harness: Harness, queue: Queue) -> None:  # AC-I8
    harness.clock.now = harness.clock.now.replace(year=2026, month=10, day=29)
    exploration_id = explored(harness, queue, month="2027-09", trip_days=30)
    page = harness.services.exploration_views.exploration_page(exploration_id)
    by_date = {c["date"]: c for c in flat_cells(page)}
    # Today + 365 = 2027-10-29: a 30-day stay must leave on or before 2027-09-29.
    assert by_date["2027-09-29"]["status"] == "ok"
    assert by_date["2027-09-30"]["label"] == EXPLORATION_CELL_LABELS["out_of_range"]
    assert harness.repo.get_exploration(exploration_id).total == 29


def test_stale_after_24_hours(harness: Harness, queue: Queue) -> None:  # AC-S7
    exploration_id = explored(harness, queue)
    harness.clock.advance(hours=25)
    exploration = harness.services.exploration_views.exploration_page(exploration_id)["exploration"]
    assert exploration["stale"] is True and exploration["stale_note"] == exploration_age_note(25)


def test_booking_link_fallback(harness: Harness, queue: Queue, links: FakeLinks) -> None:
    links.fail = True
    exploration_id = explored(harness, queue, month="2026-10")
    cells = [
        c
        for c in flat_cells(harness.services.exploration_views.exploration_page(exploration_id))
        if c["status"] == "ok"
    ]
    assert cells and all(c["booking_note"] == BOOKING_FALLBACK_NOTE for c in cells)
    assert all("google.com/travel/flights" in c["booking_url"] for c in cells)


def test_price_levels_single_definition_and_semantics() -> None:
    owners = [
        p.relative_to(SRC).as_posix()
        for p in SRC.rglob("*.py")
        if re.search(r"^def price_levels\(", p.read_text(encoding="utf-8"), re.MULTILINE)
    ]
    assert owners == ["services/views.py"]
    assert price_levels([]) == {}
    assert price_levels([("a", 5)]) == {"a": "cheap"}
    assert price_levels([("a", 5), ("b", 9)]) == {"a": "cheap", "b": "mid"}
    assert price_levels([("a", 9), ("b", 5), ("c", 7)]) == {"a": "pricey", "b": "cheap", "c": "mid"}


def test_detail_distribution_unchanged(harness: Harness) -> None:
    watch_id = harness.create_watch(
        date_mode="flexible",
        window_start="2026-12-01",
        window_end="2026-12-09",
        min_trip_days=3,
        max_trip_days=3,
    )
    for day, price in ((1, 5_000), (2, 9_000), (3, 7_000), (4, 6_000), (5, 8_000), (6, 10_000)):
        harness.source.prices[(f"2026-12-0{day}", f"2026-12-0{day + 3}")] = price
    harness.scan(watch_id)
    rows = harness.services.views.detail_page(watch_id)["distribution"]
    levels = {r["depart"]: r["level"] for r in rows}
    assert levels["2026-12-01"] == "cheap" and levels["2026-12-04"] == "cheap"
    assert levels["2026-12-06"] == "pricey" and levels["2026-12-02"] == "pricey"
    assert levels["2026-12-03"] == "mid" and levels["2026-12-05"] == "mid"


def test_new_strings_pass_wording_policy() -> None:  # AC-S8
    texts = all_static_texts()
    for label in EXPLORATION_CELL_LABELS.values():
        assert label in texts
    for text in texts:
        for phrase in BANNED_PHRASES:
            assert phrase not in text, (text, phrase)


# ---- new-watch prefill (Decision 6) ------------------------------------------------------


def prefill(harness: Harness, query: str) -> Any:
    response = harness.client.get(f"/watches/new?{query}")
    assert response.status_code == 200
    return response


def test_prefill_single_day(harness: Harness, queue: Queue) -> None:  # AC-W1
    exploration_id = explored(
        harness,
        queue,
        adults=2,
        children=1,
        cabin="business",
        airlines=["BR"],
        dep_hour_from=6,
        dep_hour_to=12,
        max_stops="1",
    )
    values, note, sampled = harness.services.exploration_views.watch_prefill(
        harness.services.views.form_values(None), str(exploration_id), "2026-12-10", None
    )
    assert note == EXPLORATION_PREFILL_OK and sampled is None
    assert (values["date_mode"], values["depart_date"], values["return_date"]) == (
        "fixed",
        "2026-12-10",
        "2026-12-15",
    )
    assert (values["adults"], values["children"], values["cabin"]) == (2, 1, "business")
    assert values["airlines"] == ["BR"] and (values["dep_hour_from"], values["dep_hour_to"]) == (
        6,
        12,
    )
    assert values["max_stops"] == "1" and values["budget"] == "" and values["name"] == ""
    watches_before = harness.repo.list_watches()
    response = prefill(harness, f"from_exploration={exploration_id}&depart=2026-12-10")
    assert response.context["prefill_note"] == EXPLORATION_PREFILL_OK
    assert response.context["values"]["depart_date"] == "2026-12-10"
    assert harness.repo.list_watches() == watches_before  # AC-W6: nothing written


def test_prefill_one_way(harness: Harness, queue: Queue) -> None:  # AC-W3
    exploration_id = explored(harness, queue, trip_type="one_way", trip_days=None)
    values, note, _ = harness.services.exploration_views.watch_prefill(
        harness.services.views.form_values(None), str(exploration_id), "2026-12-03", None
    )
    assert note == EXPLORATION_PREFILL_OK
    assert (values["trip_type"], values["depart_date"], values["return_date"]) == (
        "one_way",
        "2026-12-03",
        "",
    )


@pytest.mark.parametrize("trip_type,stay", [("round_trip", 5), ("one_way", None)])
def test_prefill_month_covers_every_future_day(
    harness: Harness, queue: Queue, trip_type: str, stay: int | None
) -> None:  # AC-W4
    for month in ("2026-12", "2026-10"):
        exploration_id = explored(harness, queue, trip_type=trip_type, trip_days=stay, month=month)
        values, note, sampled = harness.services.exploration_views.watch_prefill(
            harness.services.views.form_values(None), str(exploration_id), None, "month"
        )
        assert note == EXPLORATION_PREFILL_OK and sampled and "12 組" in sampled
        today = date(2026, 10, 25)
        outcome = validate_watch_input({**values, "budget": "30000"}, today)
        assert outcome.spec is not None, outcome.errors  # AC-W5: valid as prefilled
        departs = {p.depart for p in expand_pairs(outcome.spec, today)}
        year, mon = (int(x) for x in month.split("-"))
        first = date(year, mon, 1)
        last = date(year + mon // 12, mon % 12 + 1, 1) - timedelta(days=1)
        expected = {first + timedelta(days=i) for i in range((last - first).days + 1)}
        assert departs == {d for d in expected if d >= today}
        if stay:
            assert values["min_trip_days"] == values["max_trip_days"] == str(stay)
            assert all(
                (p.return_date - p.depart).days == stay
                for p in expand_pairs(outcome.spec, today)
                if p.return_date
            )
        harness.repo.interrupt_active_explorations(harness.clock(), "x")
        with harness.repo.db.connect() as conn:
            conn.execute("DELETE FROM exploration")


@pytest.mark.parametrize(
    "query",
    [
        "from_exploration=999&depart=2026-12-10",
        "from_exploration=abc&depart=2026-12-10",
        "from_exploration=1&depart=2027-01-10",
        "from_exploration=1&depart=bad",
        "from_exploration=1",
    ],
)
def test_prefill_mismatch_gives_blank_form(harness: Harness, queue: Queue, query: str) -> None:
    explored(harness, queue)
    response = prefill(harness, query)
    context = response.context
    assert context["prefill_note"] == EXPLORATION_PREFILL_MISSING
    assert context["values"] == harness.services.views.form_values(None)  # blank form


def test_prefill_does_not_bypass_validation(harness: Harness, queue: Queue) -> None:  # AC-W5
    exploration_id = explored(harness, queue)
    values, _, _ = harness.services.exploration_views.watch_prefill(
        harness.services.views.form_values(None), str(exploration_id), "2026-12-10", None
    )
    payload = {**values, "destination": "", "budget": "30000"}
    response = harness.client.post("/api/watches", json=payload, headers=CLIENT_HEADERS)
    assert response.status_code == 422 and "destination" in response.json()["errors"]
    payload["destination"] = "NRT"
    assert harness.client.post(
        "/api/watches", json=payload, headers=CLIENT_HEADERS
    ).status_code == (201)


# ---- front-end polling contract, checked statically (C-46) ---------------------------


def exploration_js() -> str:
    text = (SRC / "web" / "static" / "app.js").read_text(encoding="utf-8")
    start = text.index("// ---- exploration progress polling")
    end = text.index("function initExplorationPage")
    return text[start:end]


def test_polling_constants_and_reload() -> None:
    whole = (SRC / "web" / "static" / "app.js").read_text(encoding="utf-8")
    assert "const POLL_INTERVAL_MS = 2000;" in whole  # never below 2 seconds
    assert "const EXPLORE_NO_PROGRESS_MS = 120000;" in whole
    section = exploration_js()
    assert "(total * 30 + 60) * 1000" in section
    assert "await sleep(POLL_INTERVAL_MS)" in section
    assert "window.location.reload()" in section
    assert "textContent" in section
    assert "innerHTML" not in whole


def test_timeout_wording_has_no_failure_word() -> None:
    template = (SRC / "web" / "templates" / "exploration.html").read_text(encoding="utf-8")
    note = re.search(r'<p id="progress-note"[^>]*>([^<]*)</p>', template)
    assert note and "仍在背景執行" in note.group(1)
    assert "失敗" not in note.group(1)
    assert "失敗" not in exploration_js()
    assert "失敗" not in template

"""FD-12 view models: flight keys, card rules, diagnostics never shown, web price notes
(ADR-0002 FD-12 sections 0, 4.3, 4.4, 5; C-99, C-100, C-102)."""

from __future__ import annotations

from collections.abc import Iterator
from datetime import timedelta
from typing import Any

import pytest

from flight_deals.domain.flight_summary import FlightSummary
from flight_deals.domain.messages import (
    DISCLAIMER,
    EXPLORATION_REFERENCE_NOTE,
    SOURCE_PAGE_LIVE_NOTE,
    WEB_BOOKING_FALLBACK_NOTE,
    WEB_TEXTS,
    UiTexts,
    stale_rounds_label,
)
from flight_deals.domain.models import FlightSearch
from flight_deals.ports import SourceResult
from flight_deals.services.views import known_error_label, pair_note, run_note
from tests.conftest import Harness
from tests.test_comparison_service import Queue as ComparisonQueue
from tests.test_comparison_service import compared
from tests.test_exploration_service import Queue as ExplorationQueue
from tests.test_exploration_service import start as start_exploration

BR184 = {
    "flight_numbers": "BR184",
    "arrive_time": "12:00",
    "arrive_day_offset": 0,
    "route_airports": "TPE,NRT",
    "depart_time": "07:55",
    "carrier": "長榮航空",
}
CZ_ONE_STOP = {
    "flight_numbers": "CZ3088,CZ3575",
    "arrive_time": "03:30",
    "arrive_day_offset": 1,
    "route_airports": "TPE,SZX,NRT",
    "depart_time": "23:55",
    "carrier": "中國南方航空",
    "stops": 1,
}
FLEX = {
    "date_mode": "flexible",
    "depart_date": "",
    "return_date": "",
    "window_start": "2026-12-01",
    "window_end": "2026-12-06",
    "min_trip_days": 3,
    "max_trip_days": 3,
}
FAMILY = {"adults": 2, "children": 1, "cabin": "business", "budget": 40000}
DIAGNOSTICS = (
    "no result section",
    "Traceback",
    "Error:",
    "RuntimeError",
    "ValueError",
    "HTTP 503",
    "未在頁面內嵌",
    "未內嵌",
    "查票",
)


class DatedLinks:
    """Booking links that name their date pair, to check where a link comes from."""

    def url(self, search: FlightSearch) -> str | None:
        ret = search.pair.return_date.isoformat() if search.pair.return_date else "-"
        return (
            "https://www.google.com/travel/flights/search"
            f"?tfs={search.destination}_{search.pair.depart.isoformat()}_{ret}"
        )


class BrokenLinks:
    def url(self, search: FlightSearch) -> str | None:
        raise RuntimeError("no tfs")


@pytest.fixture
def links(harness: Harness) -> DatedLinks:
    fake = DatedLinks()
    for service in (
        harness.services.views,
        harness.services.exploration_views,
        harness.services.comparison_views,
    ):
        service._links = fake
    return fake


def only_row(harness: Harness) -> dict[str, Any]:
    (row,) = harness.services.views.list_page()["watches"]
    result: dict[str, Any] = row
    return result


def walk(value: Any) -> Iterator[str]:
    """Every string inside a view model, dataclasses included."""
    if isinstance(value, str):
        yield value
    elif isinstance(value, dict):
        for key, item in value.items():
            yield str(key)
            yield from walk(item)
    elif isinstance(value, (list, tuple)):
        for item in value:
            yield from walk(item)
    elif hasattr(value, "__dataclass_fields__"):
        for name in value.__dataclass_fields__:
            yield from walk(getattr(value, name))


# ---- shared context ---------------------------------------------------------------------------


def test_base_context_carries_ui(harness: Harness) -> None:
    context = harness.services.views.base_context()
    assert context["ui"] is WEB_TEXTS and isinstance(context["ui"], UiTexts)
    assert WEB_TEXTS.booking_button == "到 Google Flights 查看並訂票"
    assert WEB_TEXTS.booking_button_short == "查看並訂票"
    assert WEB_TEXTS.best_card_title == "已查到最低價"


# ---- list card (contract 0.4, 4.3) -----------------------------------------------------------


def test_list_card_price_flight_and_link_come_from_one_observation(
    harness: Harness, links: DatedLinks
) -> None:
    harness.source.prices = {
        ("2026-12-01", "2026-12-04"): 9_000,
        ("2026-12-02", "2026-12-05"): 8_000,
        ("2026-12-03", "2026-12-06"): 9_500,
    }
    harness.source.flights = {
        ("2026-12-01", "2026-12-04"): BR184,
        ("2026-12-02", "2026-12-05"): CZ_ONE_STOP,
        ("2026-12-03", "2026-12-06"): BR184,
    }
    watch_id = harness.create_watch(**FLEX)
    harness.scan(watch_id)
    row = only_row(harness)
    assert row["min_price"] == "TWD 8,000"
    flight = row["flight"]
    assert isinstance(flight, FlightSummary)
    assert flight.flight_numbers == "CZ 3088 → CZ 3575" and flight.times == "23:55 → 03:30+1"
    assert flight.stops == "轉機 1 次（SZX）" and flight.leg_label == "去程"
    assert row["booking_url"].endswith("tfs=NRT_2026-12-02_2026-12-05")
    assert row["booking_note"] is None
    assert row["dates_weekday_label"] == "12/02（週三）–12/05（週六）"
    assert row["cheapest_fetched_label"] == "查到時間 2026-10-25 12:00"
    assert row["stale"] is False and row["stale_rounds_label"] is None
    assert row["manual_check"] is False and row["ended"] is False
    assert row["filters_label"] is None
    assert row["price_caption"] == "來回總價" and row["pax_note"] is None
    assert row["pax_summary"] == "1 位成人・經濟艙"
    for removed in ("no_embedded_note", "no_embedded_streak_label"):
        assert removed not in row
    assert "no_embedded_streak_label" not in harness.services.views.list_page()


def test_list_card_stale_after_threshold_and_setting_change(harness: Harness) -> None:
    watch_id = harness.create_watch()
    harness.scan(watch_id)
    harness.clock.advance(hours=25)
    assert only_row(harness)["stale"] is True
    assert harness.services.settings.update({"stale_after_hours": "48"}) == {}
    assert only_row(harness)["stale"] is False  # follows the setting without a restart


def test_raising_stale_after_hours_clears_the_badge_at_once(harness: Harness) -> None:
    """Only ``stale_after_hours`` changes: the cached list threshold follows (listener)."""
    watch_id = harness.create_watch()
    harness.scan(watch_id)
    harness.clock.advance(hours=7)
    assert harness.services.settings.update({"stale_after_hours": "6"}) == {}
    assert only_row(harness)["stale"] is True
    assert harness.services.settings.update({"stale_after_hours": "8"}) == {}
    assert only_row(harness)["stale"] is False
    html = harness.client.get("/").text
    assert WEB_TEXTS.stale_badge not in html


def test_lowering_stale_after_hours_shows_the_badge_at_once(harness: Harness) -> None:
    """Only ``stale_after_hours`` changes: the cached list threshold follows (listener)."""
    watch_id = harness.create_watch()
    harness.scan(watch_id)
    harness.clock.advance(hours=7)
    assert only_row(harness)["stale"] is False  # default threshold (24 hours)
    assert harness.services.settings.update({"stale_after_hours": "6"}) == {}
    assert only_row(harness)["stale"] is True
    html = harness.client.get("/").text
    assert WEB_TEXTS.stale_badge in html


def test_list_card_without_price_has_manual_link_not_booking(
    harness: Harness, links: DatedLinks
) -> None:
    def handler(query: FlightSearch) -> SourceResult:
        return SourceResult(
            "google_flights", "no_data", harness.clock(), extra={"reason": "no_embedded_results"}
        )

    harness.source.handler = handler
    watch_id = harness.create_watch()
    harness.scan(watch_id)
    row = only_row(harness)
    assert row["min_price"] is None and row["flight"] is None
    assert row["manual_check"] is True and row["stale_rounds_label"] is None
    assert row["booking_url"].endswith("tfs=NRT_2026-12-10_2026-12-15")  # first pair


def test_list_card_streak_label_only_with_a_price(harness: Harness) -> None:
    watch_id = harness.create_watch()
    harness.scan(watch_id)

    def handler(query: FlightSearch) -> SourceResult:
        return SourceResult(
            "google_flights", "no_data", harness.clock(), extra={"reason": "no_embedded_results"}
        )

    harness.source.handler = handler
    for _ in range(3):
        harness.clock.advance(hours=7)
        harness.scan(watch_id)
    row = only_row(harness)
    assert row["min_price"] and row["manual_check"] is False
    assert row["stale_rounds_label"] == stale_rounds_label(3) == "近 3 輪未更新"
    assert row["no_embedded_streak"] is True


def test_list_card_ended_watch_has_no_button(harness: Harness) -> None:
    watch_id = harness.create_watch()
    harness.scan(watch_id)
    harness.clock.now = harness.clock.now + timedelta(days=60)  # every date has passed
    harness.repo.set_watch_status(watch_id, "expired", harness.clock.now)
    row = only_row(harness)
    assert row["ended"] is True and row["status_label"] == "已結束"
    assert row["min_price"] is None and row["booking_url"] is None


def test_list_card_fallback_link_carries_the_web_note(harness: Harness) -> None:
    harness.services.views._links = BrokenLinks()
    watch_id = harness.create_watch()
    harness.scan(watch_id)
    row = only_row(harness)
    assert row["booking_url"].startswith("https://www.google.com/travel/flights?")
    assert row["booking_note"] == WEB_BOOKING_FALLBACK_NOTE


def test_list_card_filters_only_when_set(harness: Harness) -> None:
    harness.create_watch(airlines=["BR"], dep_hour_from=6, dep_hour_to=12)
    assert only_row(harness)["filters_label"] == "長榮｜去程 06–12 時"


# ---- detail page -------------------------------------------------------------------------------


def test_detail_main_card_is_the_snapshot_minimum(harness: Harness, links: DatedLinks) -> None:
    harness.source.prices = {
        ("2026-12-01", "2026-12-04"): 9_000,
        ("2026-12-02", "2026-12-05"): 8_000,
        ("2026-12-03", "2026-12-06"): 9_500,
    }
    harness.source.flights = {("2026-12-02", "2026-12-05"): CZ_ONE_STOP}
    harness.source.flight = BR184
    watch_id = harness.create_watch(**FLEX)
    harness.scan(watch_id)
    harness.clock.advance(hours=7)
    harness.source.prices[("2026-12-02", "2026-12-05")] = 7_500
    harness.scan(watch_id)
    data = harness.services.views.detail_page(watch_id)
    best = data["best"]
    assert best is data["top"][0] and best["amount_text"] == "TWD 7,500"
    assert best["flight"].flight_numbers == "CZ 3088 → CZ 3575"
    assert best["booking_url"].endswith("tfs=NRT_2026-12-02_2026-12-05")
    assert data["best_delta"] == {"direction": "down", "amount_label": "TWD 500"}
    for row in [*data["top"], *data["recent_prices"]]:
        assert isinstance(row["flight"], FlightSummary)
        assert row["kind_badge"] is None and row["source_text"] is None
        assert row["fetched_label"].startswith("查到時間 ")
    assert data["source_note"] == SOURCE_PAGE_LIVE_NOTE
    assert data["manual_check"] is False
    assert data["top_explain"].startswith("每個日期組合取最近一次查到的價格")
    watch = data["watch"]
    assert watch["settings_summary"] == (
        "TPE → NRT・來回・彈性 2026-12-01 ～ 2026-12-06，旅程 3 天・預算 TWD 12,000"
    )
    assert watch["price_caption"] == "來回總價" and watch["pax_summary"] == "1 位成人・經濟艙"
    last_run = data["last_run"]
    for removed in ("error", "no_embedded_note"):
        assert removed not in last_run
    for pair in last_run["pairs"]:
        assert "error" not in pair and "reason" not in pair and "note" in pair
    assert all("error" not in r and "note" in r for r in data["runs"])


def test_detail_old_revision_rows_have_no_flight(harness: Harness) -> None:
    harness.source.flight = BR184
    watch_id = harness.create_watch()
    harness.scan(watch_id)
    harness.client.put(
        f"/api/watches/{watch_id}",
        json={
            "destination": "HND",
            "trip_type": "round_trip",
            "date_mode": "fixed",
            "depart_date": "2026-12-10",
            "return_date": "2026-12-15",
            "budget": "12000",
        },
        headers={"X-Flight-Deals-Client": "1"},
    )
    old = harness.services.views.detail_page(watch_id)["old_prices"]
    assert old and all(r["flight"] is None for r in old)
    assert old[0]["carrier"] == "長榮航空"


def test_detail_cached_rows_show_their_source(harness: Harness) -> None:
    harness.source._kind = "cached"
    watch_id = harness.create_watch()
    harness.scan(watch_id)
    data = harness.services.views.detail_page(watch_id)
    assert data["source_note"] is None
    (row,) = data["recent_prices"]
    assert row["source_text"] == "Google Flights（快取價，非即時）"
    assert row["kind_badge"] == "快取價，非即時；資料時間未知"


# ---- FR-12: diagnostics never reach a page ----------------------------------------------------


def failing_handler(harness: Harness) -> Any:
    def handler(query: FlightSearch) -> SourceResult:
        if query.pair.depart.day == 1:
            return SourceResult(
                "google_flights",
                "no_data",
                harness.clock(),
                error="no result section embedded in the page",
                extra={"reason": "no_embedded_results"},
            )
        if query.pair.depart.day == 2:
            return SourceResult(
                "google_flights", "error", harness.clock(), error="RuntimeError: HTTP 503 Error:"
            )
        return SourceResult(
            "google_flights", "blocked", harness.clock(), error="ValueError: Traceback (most"
        )

    return handler


def test_watch_pages_never_show_adapter_text(harness: Harness) -> None:
    harness.source.handler = failing_handler(harness)
    watch_id = harness.create_watch(**FLEX)
    harness.scan(watch_id)
    run = harness.repo.scan_runs_for_watch(watch_id)[0]
    assert run.error_summary and "RuntimeError" in run.error_summary  # kept in the database
    views = harness.services.views
    models = [views.list_page(), views.detail_page(watch_id)]
    for text in (s for model in models for s in walk(model)):
        for bad in DIAGNOSTICS:
            assert bad not in text, (bad, text)
    pairs = {p["depart"]: p for p in models[1]["last_run"]["pairs"]}
    assert pairs["2026-12-01"]["status"] == WEB_TEXTS.manual_check
    assert pairs["2026-12-01"]["note"] == WEB_TEXTS.manual_check
    assert pairs["2026-12-02"]["note"] == WEB_TEXTS.query_failed
    assert pairs["2026-12-03"]["note"] == WEB_TEXTS.query_failed
    assert models[1]["last_run"]["note"] == "需人工查價；錯誤；被擋或格式改變"
    for url in ("/", f"/watches/{watch_id}"):
        html = harness.client.get(url).text
        for bad in DIAGNOSTICS:
            assert bad not in html, (url, bad)


def test_settings_page_keeps_raw_error_for_technical_details(harness: Harness) -> None:
    harness.source.handler = failing_handler(harness)
    watch_id = harness.create_watch(**FLEX)
    for _ in range(3):
        harness.scan(watch_id)
        harness.clock.advance(hours=7)
    page = harness.services.views.settings_page()
    errors = [h["last_error"] for h in page["health"] if h["last_error"]]
    assert errors  # the raw text is still available, for the collapsed technical details


def test_pair_and_run_note_rules() -> None:
    assert pair_note({"status": "ok", "tries": [{"unpriced": 2}]}) == "略過 2 筆無價格航班"
    assert pair_note({"status": "skipped", "reason": "breaker_open"}) == "資料源斷路器開啟中"
    assert pair_note({"status": "error", "tries": [{"error": "boom"}]}) == "查詢失敗"
    assert pair_note({"status": "no_data", "tries": [{"error": None}]}) is None


def test_known_error_label() -> None:
    known = ("排程器未執行", "已達全域每小時查詢上限")
    assert known_error_label(None, known) is None
    assert known_error_label("排程器未執行", known) == "排程器未執行"
    assert known_error_label("已達全域每小時查詢上限，3 天未查", known) == (
        "已達全域每小時查詢上限，3 天未查"
    )
    assert known_error_label("探索中斷：RuntimeError: boom", known) == "查詢失敗"


def test_run_note_without_summary_is_none(harness: Harness) -> None:
    watch_id = harness.create_watch()
    harness.scan(watch_id)
    run = harness.repo.scan_runs_for_watch(watch_id)[0]
    assert run.error_summary is None and run_note(run) is None


# ---- exploration and comparison --------------------------------------------------------------


def test_exploration_cells_carry_flights_and_manual_check(
    harness: Harness, links: DatedLinks
) -> None:
    queue = ExplorationQueue(harness.services.exploration)

    def handler(query: FlightSearch) -> SourceResult:
        if query.pair.depart.day == 3:
            return SourceResult(
                "google_flights",
                "no_data",
                harness.clock(),
                extra={"reason": "no_embedded_results"},
            )
        return ScriptedAnswer(harness, query)

    harness.source.flight = BR184
    harness.source.handler = handler
    exploration_id = start_exploration(harness)
    queue.run_all()
    page = harness.services.exploration_views.exploration_page(exploration_id)
    assert page is not None
    cells = {c["date"]: c for week in page["weeks"] for c in week if c}
    priced = cells["2026-12-01"]
    assert priced["flight"].flight_numbers == "BR 184" and priced["manual_check"] is False
    assert priced["booking_url"].endswith("tfs=NRT_2026-12-01_2026-12-06")
    missing = cells["2026-12-03"]
    assert missing["flight"] is None and missing["manual_check"] is True
    assert missing["label"] == WEB_TEXTS.manual_check
    assert all(t["flight"] is not None for t in page["top5"])
    assert page["disclaimer"] == DISCLAIMER and page["reference_note"] == EXPLORATION_REFERENCE_NOTE
    assert page["calendar_note"].startswith("每格為該出發日單次查到的最低價")
    e = page["exploration"]
    assert e["pax_note"] is None and e["pax_summary"] == "1 位成人・經濟艙"
    assert e["price_caption"] == "來回總價"


def ScriptedAnswer(harness: Harness, query: FlightSearch) -> SourceResult:  # noqa: N802
    """The default scripted answer (price from the pair) with the opt-in flight."""
    source = harness.source
    handler, source.handler = source.handler, None
    try:
        return source.search(query)
    finally:
        source.handler = handler


def test_comparison_rows_carry_flights(harness: Harness, links: DatedLinks) -> None:
    queue = ComparisonQueue(harness.services.comparison)
    harness.source.flight = BR184
    comparison_id = compared(harness, queue)
    page = harness.services.comparison_views.comparison_page(comparison_id)
    assert page is not None
    for row in page["rows"]:
        assert row["flight"].flight_numbers == "BR 184" and row["manual_check"] is False
        assert row["booking_url"].endswith(f"tfs={row['destination']}_2026-12-10_2026-12-15")
    c = page["comparison"]
    assert c["pax_note"] is None and c["pax_summary"] == "1 位成人・經濟艙"
    assert page["table_caption"] == "各目的地的 1 人總價，由低到高排列"


# ---- C-40 two groups (contract section 5, C-100) ------------------------------------------------


def test_one_traveller_has_summary_lines_and_no_note_next_to_prices(harness: Harness) -> None:
    watch_id = harness.create_watch()
    harness.scan(watch_id)
    row = only_row(harness)
    assert row["pax_note"] is None and row["pax_summary"] == "1 位成人・經濟艙"
    detail = harness.services.views.detail_page(watch_id)
    assert detail["watch"]["pax_note"] is None
    assert detail["watch"]["pax_summary"] == "1 位成人・經濟艙"
    for url in ("/", f"/watches/{watch_id}"):
        html = harness.client.get(url).text
        assert "1 人總價" not in html, url
        # The party summary is in the list's collapsed conditions (FD-22 D#24). The detail
        # page drops it next to the price too (FD-22 ruling D#24 applied to the detail page,
        # task FD-22 round 2) and keeps the party in its watch settings fold.
        if url == "/":
            assert "1 位成人・經濟艙" in html, url
        else:
            assert "<dt>人數</dt><dd>1 位成人</dd>" in html and "<dt>艙等</dt>" in html, url


def test_several_travellers_get_a_note_on_every_price(harness: Harness) -> None:
    watch_id = harness.create_watch(**FAMILY)
    harness.scan(watch_id)
    row = only_row(harness)
    assert row["pax_note"] == "2 大 1 小總價"
    assert row["price_caption"] == "來回・2 大 1 小總價"
    detail = harness.services.views.detail_page(watch_id)
    assert detail["watch"]["pax_note"] == "2 大 1 小總價"
    assert "（2 大 1 小總價）" in detail["watch"]["settings_summary"]  # budget, condition (e)
    for url in ("/", f"/watches/{watch_id}"):
        html = harness.client.get(url).text
        assert "2 大 1 小總價" in html and "1 人總價" not in html, url


def test_telegram_keeps_the_one_person_note(harness: Harness) -> None:
    watch_id = harness.create_watch(budget=20000)
    harness.scan(watch_id)
    assert harness.notifier.sent and "（1 人總價）" in harness.notifier.sent[-1]


def test_exploration_crash_summary_is_not_shown_raw(harness: Harness) -> None:  # FR-12
    ExplorationQueue(harness.services.exploration)  # scheduler "running", job not run
    exploration_id = start_exploration(harness)
    harness.repo.finish_exploration(
        exploration_id,
        status="failed",
        finished_at=harness.clock(),
        skip_reason="interrupted",
        error_summary="探索中斷：RuntimeError: database is locked",
    )
    page = harness.services.exploration_views.exploration_page(exploration_id)
    assert page is not None
    summary = page["exploration"]["error_summary"]
    assert summary.endswith("原因：查詢失敗") and "RuntimeError" not in summary
    html = harness.client.get(f"/explorations/{exploration_id}").text
    assert "RuntimeError" not in html and "database is locked" not in html


def test_comparison_crash_summary_is_not_shown_raw(harness: Harness) -> None:  # FR-12
    from tests.test_comparison_service import start as start_comparison

    ComparisonQueue(harness.services.comparison)  # scheduler "running", job not run
    comparison_id = start_comparison(harness)
    harness.repo.finish_comparison(
        comparison_id,
        status="failed",
        finished_at=harness.clock(),
        skip_reason="interrupted",
        error_summary="比價中斷：OperationalError: disk I/O error",
    )
    page = harness.services.comparison_views.comparison_page(comparison_id)
    assert page is not None
    summary = page["comparison"]["error_summary"]
    assert summary.endswith("原因：查詢失敗") and "OperationalError" not in summary
    html = harness.client.get(f"/comparisons/{comparison_id}").text
    assert "OperationalError" not in html and "disk I/O" not in html


HOSTILE = (
    "https://example.com/travel/flights?tfs=x",
    "http://www.google.com/travel/flights/search?tfs=x",
    "https://www.google.com/not-flights?tfs=x",
    "javascript:alert(1)",
)


@pytest.mark.parametrize("hostile", HOSTILE)
def test_non_google_flights_links_never_reach_a_page(harness: Harness, hostile: str) -> None:
    class HostileLinks:
        def url(self, search: FlightSearch) -> str | None:
            return hostile

    fake = HostileLinks()
    for service in (
        harness.services.views,
        harness.services.exploration_views,
        harness.services.comparison_views,
    ):
        service._links = fake
    watch_id = harness.create_watch()
    harness.scan(watch_id)
    row = only_row(harness)
    assert row["booking_url"].startswith("https://www.google.com/travel/flights?")
    assert row["booking_note"] == WEB_BOOKING_FALLBACK_NOTE
    exploration_queue = ExplorationQueue(harness.services.exploration)
    exploration_id = start_exploration(harness)
    exploration_queue.run_all()
    comparison_id = compared(harness, ComparisonQueue(harness.services.comparison))
    for url in (
        "/",
        f"/watches/{watch_id}",
        f"/explorations/{exploration_id}",
        f"/comparisons/{comparison_id}",
    ):
        html = harness.client.get(url).text
        assert hostile not in html and hostile.replace("&", "&amp;") not in html, url


def test_safe_booking_url_allowlist() -> None:
    from datetime import date

    from flight_deals.domain.models import DatePair
    from flight_deals.services.notifications import is_google_flights_url, safe_booking_url

    search = FlightSearch("TPE", "NRT", DatePair(date(2026, 12, 10)), None)

    class Fixed:
        def __init__(self, url: str) -> None:
            self.value = url

        def url(self, search: FlightSearch) -> str | None:
            return self.value

    good = "https://www.google.com/travel/flights/search?tfs=x"
    assert safe_booking_url(Fixed(good), search) == good
    assert is_google_flights_url("https://google.com/travel/flights?q=x")
    assert is_google_flights_url("https://www.google.com/travel/flights/search?tfs=x")
    assert not is_google_flights_url("https://www.google.com/travel/flightsX")
    assert not is_google_flights_url(184)
    assert not is_google_flights_url("https://google.com@example.com/travel/flights")
    for hostile in HOSTILE:
        assert safe_booking_url(Fixed(hostile), search) is None, hostile


def test_exploration_top5_and_calendar_show_fetched_times(harness: Harness) -> None:
    queue = ExplorationQueue(harness.services.exploration)
    exploration_id = start_exploration(harness)
    queue.run_all()
    page = harness.services.exploration_views.exploration_page(exploration_id)
    assert page is not None
    assert all(t["fetched_label"] == "查到時間 2026-10-25 12:00" for t in page["top5"])
    assert page["fetched_range_label"] == "查到時間：10/25 12:00"
    html = harness.client.get(f"/explorations/{exploration_id}").text
    assert "查到時間：10/25 12:00" in html and "查到時間 2026-10-25 12:00" in html


def test_fetched_range_label_forms() -> None:
    from datetime import UTC, datetime

    from flight_deals.domain.messages import fetched_range_label

    a = datetime(2026, 11, 1, 6, 31, tzinfo=UTC)
    assert fetched_range_label(a, a + timedelta(minutes=2)) == "查到時間：11/01 14:31～14:33"
    assert fetched_range_label(a + timedelta(minutes=2), a) == "查到時間：11/01 14:31～14:33"
    assert fetched_range_label(a, a + timedelta(hours=12)) == "查到時間：11/01 14:31～11/02 02:31"
    assert fetched_range_label(a, a) == "查到時間：11/01 14:31"

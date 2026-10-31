"""FD-9 follow-ups F1-F3 (ADR-0002 FD-9 Decision 5, C-68)."""

from __future__ import annotations

from datetime import date
from typing import Any

from flight_deals.domain.messages import (
    DETAIL_ALL_DEPARTED,
    CommandScanResult,
    command_scan_result_message,
)
from flight_deals.domain.models import WatchSpec
from flight_deals.domain.trip_labels import flight_duration_label, stay_range_label
from flight_deals.services.commands import CommandContext
from flight_deals.services.views import dates_text
from tests.conftest import Harness


def scan_result(**overrides: Any) -> CommandScanResult:
    values: dict[str, Any] = {
        "watch_id": 3,
        "name": "東京",
        "currency": "TWD",
        "adults": 1,
        "children": 0,
        "run_status": "failed",
        "failure_reason": "資料源被擋或格式改變",
        "amount_minor": None,
        "depart_date": None,
        "return_date": None,
        "delta_direction": None,
        "delta_minor": None,
        "sampled": 12,
        "queries_used": 0,
        "skip_notes": (),
    }
    values.update(overrides)
    return CommandScanResult(**values)


# ---- F1: /scan round without outbound queries -----------------------------------------


def test_zero_query_round_states_scheduled_pairs() -> None:  # AC-F1
    text = command_scan_result_message(scan_result())
    assert "本輪排定 12 組日期，未對外查詢" in text
    assert "對外查詢 0 次" not in text and "本輪取樣" not in text


def test_round_with_queries_is_unchanged() -> None:  # AC-F1
    text = command_scan_result_message(scan_result(run_status="ok", queries_used=5))
    assert "本輪取樣 12 組日期，對外查詢 5 次" in text
    assert "本輪排定" not in text


# ---- F2: detail page when every price has departed ------------------------------------


def test_all_departed_has_its_own_note(harness: Harness) -> None:  # AC-F2
    watch_id = harness.create_watch(depart_date="2026-11-01", return_date="2026-11-05")
    harness.scan(watch_id)
    harness.clock.advance(days=8)  # 2026-11-02 in Taipei: the only date has departed
    data = harness.services.views.detail_page(watch_id)
    assert data["has_prices"] is True and data["top"] == []
    assert data["top_empty_note"] == DETAIL_ALL_DEPARTED
    page = harness.client.get(f"/watches/{watch_id}").text
    assert DETAIL_ALL_DEPARTED in page and "尚未查到價格。" not in page


def test_no_prices_keeps_the_old_wording(harness: Harness) -> None:  # AC-F2
    watch_id = harness.create_watch()
    data = harness.services.views.detail_page(watch_id)
    assert data["top_empty_note"] is None
    page = harness.client.get(f"/watches/{watch_id}").text
    assert "尚未查到價格。" in page and DETAIL_ALL_DEPARTED not in page


def test_future_prices_keep_the_table(harness: Harness) -> None:  # AC-F2
    watch_id = harness.create_watch()
    harness.scan(watch_id)
    data = harness.services.views.detail_page(watch_id)
    assert len(data["top"]) == 1 and data["top_empty_note"] is None
    assert DETAIL_ALL_DEPARTED not in harness.client.get(f"/watches/{watch_id}").text


# ---- F3: "N 天" when the shortest and longest stay are equal --------------------------


def test_stay_range_label() -> None:  # AC-F3
    assert stay_range_label(4, 4) == "4 天"
    assert stay_range_label(3, 5) == "3–5 天"


def test_flight_duration_label() -> None:
    assert flight_duration_label(205) == "3 小時 25 分"
    assert flight_duration_label(180) == "3 小時"
    assert flight_duration_label(45) == "45 分"
    assert flight_duration_label(None) is None and flight_duration_label(0) is None


def flexible(min_days: int, max_days: int) -> WatchSpec:
    return WatchSpec(
        name="x",
        origin="TPE",
        destination="NRT",
        trip_type="round_trip",
        date_mode="flexible",
        depart_date=None,
        return_date=None,
        window_start=date(2026, 12, 1),
        window_end=date(2026, 12, 20),
        min_trip_days=min_days,
        max_trip_days=max_days,
        max_stops=None,
        budget_amount_minor=None,
    )


def test_dates_text_uses_the_label() -> None:  # AC-F3
    assert dates_text(flexible(4, 4)) == "彈性 2026-12-01 ～ 2026-12-20，旅程 4 天"
    assert dates_text(flexible(3, 5)) == "彈性 2026-12-01 ～ 2026-12-20，旅程 3–5 天"


def test_list_detail_and_watch_command_agree(harness: Harness) -> None:  # AC-F3
    watch_id = harness.create_watch(
        date_mode="flexible",
        window_start="2026-12-01",
        window_end="2026-12-20",
        min_trip_days=4,
        max_trip_days=4,
    )
    detail = harness.services.views.detail_page(watch_id)
    assert detail["watch"]["stay_label"] == "4 天"
    assert "旅程 4 天" in detail["watch"]["dates"]
    [row] = harness.services.views.list_page()["watches"]
    assert "旅程 4 天" in row["dates"] and "4–4" not in row["dates"]
    page = harness.client.get(f"/watches/{watch_id}").text
    assert "4–4" not in page and "4 天" in page
    reply = harness.services.commands.handle_text(
        f"/watch {watch_id}", harness.clock(), CommandContext(1, "1")
    )
    assert "旅程 4 天" in reply.text and "4–4" not in reply.text

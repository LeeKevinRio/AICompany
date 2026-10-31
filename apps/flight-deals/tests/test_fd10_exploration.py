"""Exploration ranges and weekdays: validation, v2 key and reuse, calendar read model,
prefill (ADR-0002 FD-10 Decisions 4, 6, C-73, C-75, C-76)."""

from __future__ import annotations

import re
from dataclasses import replace
from datetime import date, timedelta
from typing import Any

import pytest

from flight_deals.domain.dates import expand_pairs, month_weekday_counts
from flight_deals.domain.messages import (
    BANNED_PHRASES,
    DISCLAIMER,
    EXPLORATION_CELL_LABELS,
    EXPLORATION_MONTH_WATCH_BUTTON,
    EXPLORATION_NO_DATES,
    EXPLORATION_PREFILL_OK,
    EXPLORATION_RANGE_WATCH_BUTTON,
    EXPLORATION_STALE_FALLBACK,
    EXPLORATION_TOO_MANY_CELLS,
    MONTH_SPAN_TOO_LONG,
    MONTH_TO_BEFORE,
    WEEKDAYS_INVALID,
    WEEKDAYS_NO_MATCH_MONTHS,
    WEEKDAYS_REQUIRED,
    exploration_quota_message,
    exploration_sampled_note,
)
from flight_deals.domain.models import ComparisonSpec, ExplorationSpec
from flight_deals.domain.validation import (
    EXPLORATION_MAX_SPAN_MONTHS,
    MONTH_INVALID,
    month_range_error,
    validate_exploration,
    validate_watch_input,
)
from flight_deals.domain.weekdays import ALL_WEEKDAYS
from tests.conftest import Harness
from tests.test_exploration_service import DECEMBER, Queue, post, set_limit, start

TODAY = date(2026, 10, 25)
V1_DECEMBER = "v1|TPE|NRT|round_trip|2026-12|5|-|1|0|economy|-|-|-|TWD"
WEEKDAY_SUMMARY = re.compile(r"週[一二三四五六日](、週[一二三四五六日])*出發")
FRI_SAT = [4, 5]
THREE_MONTHS: dict[str, Any] = {"month": "2026-12", "month_to": "2027-02"}


@pytest.fixture
def queue(harness: Harness) -> Queue:
    return Queue(harness.services.exploration)


def explored(harness: Harness, queue: Queue, **overrides: Any) -> int:
    exploration_id = start(harness, **overrides)
    queue.run_all()
    return exploration_id


def exploration_count(harness: Harness) -> int:
    with harness.repo.db.connect() as conn:
        return int(conn.execute("SELECT COUNT(*) FROM exploration").fetchone()[0])


# ---- validation and 422 order (C-73) ------------------------------------------------------


@pytest.mark.parametrize(
    ("month_to", "message"),
    [
        ("2026-11", MONTH_TO_BEFORE),
        ("2027-03", MONTH_SPAN_TOO_LONG),  # 2026-12 .. 2027-03 is four months
        ("2027-10", month_range_error(TODAY)),  # beyond the 12 selectable months
        ("2027-2", MONTH_INVALID),
        ("2027-13", MONTH_INVALID),
        ("abc", MONTH_INVALID),
    ],
)
def test_month_to_rejected(month_to: str, message: str) -> None:  # C-73, AC-M4
    outcome = validate_exploration({**DECEMBER, "month_to": month_to}, TODAY)
    assert outcome.errors == {"month_to": message}


def test_span_limit_wording() -> None:
    assert EXPLORATION_MAX_SPAN_MONTHS == 3 and MONTH_SPAN_TOO_LONG == "月份範圍最多連續 3 個月"


@pytest.mark.parametrize("extra", [{}, {"month_to": ""}, {"month_to": "2026-12"}])
def test_single_month_forms_are_the_same_spec(extra: dict[str, Any]) -> None:  # C-73, C-75
    outcome = validate_exploration({**DECEMBER, **extra}, TODAY)
    assert outcome.spec is not None
    assert outcome.spec == validate_exploration(DECEMBER, TODAY).spec
    assert outcome.spec.end_year is None and outcome.spec.month_to_text is None


@pytest.mark.parametrize(
    ("value", "message"),
    [
        ([], WEEKDAYS_REQUIRED),
        ("4,5", WEEKDAYS_INVALID),
        ([7], WEEKDAYS_INVALID),
        ([True], WEEKDAYS_INVALID),
        ([4.0], WEEKDAYS_INVALID),
        (["4"], WEEKDAYS_INVALID),
    ],
)
def test_exploration_weekdays_rejected(value: Any, message: str) -> None:  # C-73
    outcome = validate_exploration({**DECEMBER, "depart_weekdays": value}, TODAY)
    assert outcome.errors == {"depart_weekdays": message}


def no_quota_check(harness: Harness, monkeypatch: pytest.MonkeyPatch) -> None:
    def boom() -> Any:
        raise AssertionError("quota checked before the 422")

    monkeypatch.setattr(harness.services.exploration, "quota", boom)


@pytest.mark.parametrize(
    ("overrides", "errors"),
    [
        ({**THREE_MONTHS}, {"month_to": EXPLORATION_TOO_MANY_CELLS}),  # AC-M3: 90 cells
        # 32 cells: 2026-10 from today (7 days) + 2026-11 (30), Fridays left out.
        (
            {"month": "2026-10", "month_to": "2026-11", "depart_weekdays": [0, 1, 2, 3, 5, 6]},
            {"month_to": EXPLORATION_TOO_MANY_CELLS},
        ),
        ({"month": "2026-10", "depart_weekdays": []}, {"depart_weekdays": WEEKDAYS_REQUIRED}),
        ({"month_to": "2026-11"}, {"month_to": MONTH_TO_BEFORE}),
    ],
)
def test_too_many_cells_and_invalid_are_422_before_anything(
    harness: Harness,
    queue: Queue,
    monkeypatch: pytest.MonkeyPatch,
    overrides: dict[str, Any],
    errors: dict[str, str],
) -> None:  # C-73
    no_quota_check(harness, monkeypatch)
    response = post(harness, **overrides)
    assert response.status_code == 422 and response.json()["errors"] == errors
    assert exploration_count(harness) == 0 and queue.ids == [] and harness.source.calls == []


def test_31_cells_allowed_32_rejected(harness: Harness, queue: Queue) -> None:  # AC-M3
    set_limit(harness, 200)
    no_monday = [1, 2, 3, 4, 5, 6]  # 2026-10-25..31 (6 left) + 2026-11 (25) = 31
    first = start(harness, month="2026-10", month_to="2026-11", depart_weekdays=no_monday)
    assert harness.repo.get_exploration(first).total == 31
    harness.repo.interrupt_active_explorations(harness.clock(), "x")
    no_friday = [0, 1, 2, 3, 5, 6]  # 6 + 26 = 32
    over = post(harness, month="2026-10", month_to="2026-11", depart_weekdays=no_friday)
    assert over.status_code == 422
    assert over.json()["errors"] == {"month_to": EXPLORATION_TOO_MANY_CELLS}
    # Three months of Fridays and Saturdays: 26 cells, allowed.
    created = start(harness, **THREE_MONTHS, depart_weekdays=FRI_SAT)
    assert harness.repo.get_exploration(created).total == 26


def test_zero_cells_message_depends_on_weekdays(
    harness: Harness, queue: Queue, monkeypatch: pytest.MonkeyPatch
) -> None:  # C-73: all weekdays keep EXPLORATION_NO_DATES verbatim
    from flight_deals.services import exploration as exploration_module

    no_quota_check(harness, monkeypatch)
    monkeypatch.setattr(exploration_module, "range_pairs", lambda _spec, _today: [])
    everything = post(harness)
    assert everything.status_code == 422
    assert everything.json()["errors"] == {"month": EXPLORATION_NO_DATES}
    filtered = post(harness, depart_weekdays=[4])
    assert filtered.status_code == 422
    assert filtered.json()["errors"] == {"depart_weekdays": WEEKDAYS_NO_MATCH_MONTHS}
    assert exploration_count(harness) == 0 and queue.ids == [] and harness.source.calls == []


def test_only_friday_zero_days_is_422_on_weekdays(
    harness: Harness, queue: Queue, monkeypatch: pytest.MonkeyPatch
) -> None:  # C-73
    harness.clock.advance(days=6)  # 2026-10-31 (Saturday): only 10/31 is left in October
    no_quota_check(harness, monkeypatch)
    response = post(harness, month="2026-10", depart_weekdays=[4])
    assert response.status_code == 422
    assert response.json()["errors"] == {"depart_weekdays": WEEKDAYS_NO_MATCH_MONTHS}
    assert exploration_count(harness) == 0 and harness.source.calls == []


def test_quota_message_for_a_range(harness: Harness, queue: Queue) -> None:  # FR-M4
    set_limit(harness, 20, reserve=0)
    response = post(harness, **THREE_MONTHS, depart_weekdays=FRI_SAT)
    assert response.status_code == 409
    assert response.json()["message"] == exploration_quota_message(20, 26, 0, months=3)
    assert "所選月份" in response.json()["message"]
    assert exploration_quota_message(20, 31, 12) == exploration_quota_message(20, 31, 12, months=1)
    assert "整月" in exploration_quota_message(20, 31, 12)


# ---- v2 key, reuse and old rows (C-75) --------------------------------------------------


def spec(**changes: Any) -> ExplorationSpec:
    return replace(ExplorationSpec("TPE", "KIX", "round_trip", 2026, 12, 4, None), **changes)


def test_v2_golden() -> None:  # C-75
    assert (
        spec(end_year=2027, end_month=2, depart_weekdays=(4, 5)).condition_key()
        == "v2|TPE|KIX|round_trip|2026-12|2027-02|48|4|-|1|0|economy|-|-|-|TWD"
    )


def test_key_normalization_and_changes() -> None:  # C-75, AC-M9
    base = spec(depart_weekdays=(4, 5))
    assert spec(depart_weekdays=(5, 4)).condition_key() == base.condition_key()
    assert spec().condition_key() == spec(depart_weekdays=ALL_WEEKDAYS).condition_key()
    assert spec().condition_key() == spec(end_year=2026, end_month=12).condition_key()
    for changed in (
        spec(depart_weekdays=(4,)),
        spec(year=2027, month=1, depart_weekdays=(4, 5)),
        spec(end_year=2027, end_month=1, depart_weekdays=(4, 5)),
    ):
        assert changed.condition_key() != base.condition_key()
    keys = {spec(end_year=y, end_month=m).condition_key() for y, m in ((2027, 1), (2027, 2))}
    assert len(keys) == 2


def test_comparison_key_golden_unchanged() -> None:  # C-75
    comparison = ComparisonSpec("TPE", ("NRT", "KIX"), "one_way", date(2026, 12, 10), None, None)
    assert comparison.condition_key() == "cmp1|TPE|KIX,NRT|one_way|2026-12-10|-|-|1|0|economy|TWD"


def test_request_key_order_and_defaults(harness: Harness, queue: Queue) -> None:  # AC-M9
    first = explored(harness, queue, depart_weekdays=[5, 4])
    again = post(harness, depart_weekdays=[4, 5], month_to="2026-12")
    assert again.status_code == 200 and again.json() == {"ok": True, "id": first, "reused": True}
    other = post(harness, depart_weekdays=[4])
    assert other.status_code == 202


def make_v1(harness: Harness, exploration_id: int) -> None:
    with harness.repo.db.connect() as conn:
        conn.execute(
            "UPDATE exploration SET condition_key = ? WHERE id = ?", (V1_DECEMBER, exploration_id)
        )


def test_ac_m8_v1_never_reused(harness: Harness, queue: Queue) -> None:  # AC-M8
    set_limit(harness, 200)
    old = explored(harness, queue)
    make_v1(harness, old)
    harness.clock.advance(hours=1)
    calls = len(harness.source.calls)
    response = post(harness)
    assert response.status_code == 202 and response.json()["id"] != old
    queue.run_all()
    assert len(harness.source.calls) == calls + 31


def test_ac_m8_v2_reused_after_three_hours(harness: Harness, queue: Queue) -> None:  # AC-M8
    first = explored(harness, queue, **THREE_MONTHS, depart_weekdays=FRI_SAT)
    harness.clock.advance(hours=3)
    calls = len(harness.source.calls)
    response = post(harness, **THREE_MONTHS, depart_weekdays=[5, 4])
    assert response.json() == {"ok": True, "id": first, "reused": True}
    assert len(harness.source.calls) == calls


def test_ac_m10_v1_pages_have_no_weekdays_or_range(harness: Harness, queue: Queue) -> None:
    old = explored(harness, queue)
    make_v1(harness, old)
    page = harness.services.exploration_views.exploration_page(old)
    assert page is not None and page["exploration"]["weekdays_label"] is None
    assert "～" not in page["exploration"]["month_label"]
    html = harness.client.get(f"/explorations/{old}").text
    assert not WEEKDAY_SUMMARY.search(html) and "～" not in html
    assert EXPLORATION_CELL_LABELS["weekday_filtered"] not in html
    [row] = harness.services.exploration_views.explore_page()["recent"]
    assert "～" not in row["month"] and not WEEKDAY_SUMMARY.search(row["conditions_label"])


def test_ac_m11_purge_treats_v1_and_v2_alike(harness: Harness, queue: Queue) -> None:
    set_limit(harness, 200)
    old = explored(harness, queue)
    make_v1(harness, old)
    new = explored(harness, queue, **THREE_MONTHS, depart_weekdays=FRI_SAT)
    harness.clock.advance(days=7, minutes=1)
    assert harness.services.exploration.purge_expired() == 2
    assert harness.repo.get_exploration(old) is None and harness.repo.get_exploration(new) is None


# ---- calendar and top 5 (C-76) ------------------------------------------------------------


def cells(page: dict[str, Any]) -> list[dict[str, Any]]:
    return [
        c for m in page["calendar_months"] for week in m["weeks"] for c in week if c is not None
    ]


def test_range_calendar_read_model(harness: Harness, queue: Queue) -> None:  # C-76
    harness.source.prices[("2027-02-05", "2027-02-10")] = 4_000
    harness.source.prices[("2026-12-04", "2026-12-09")] = 4_000
    harness.source.prices[("2027-01-02", "2027-01-07")] = 3_000
    exploration_id = explored(harness, queue, **THREE_MONTHS, depart_weekdays=FRI_SAT)
    page = harness.services.exploration_views.exploration_page(exploration_id)
    assert page is not None
    months = page["calendar_months"]
    assert [(m["year"], m["month"], m["label"]) for m in months] == [
        (2026, 12, "2026 年 12 月"),
        (2027, 1, "2027 年 1 月"),
        (2027, 2, "2027 年 2 月"),
    ]
    assert all(set(m) == {"year", "month", "label", "weeks"} for m in months)
    assert page["weeks"] == months[0]["weeks"]
    every = cells(page)
    assert len(every) == 31 + 31 + 28
    filtered = [c for c in every if c["status"] == "weekday_filtered"]
    queried = [c for c in every if c["status"] != "weekday_filtered"]
    assert len(queried) == 26 == len(harness.repo.exploration_cells(exploration_id))
    assert all(c["label"] == "未查（星期篩選）" for c in filtered)
    assert all(
        c["amount_label"] is None and c["booking_url"] is None and c["watch_url"] is None
        for c in filtered
    )
    assert {date.fromisoformat(c["date"]).weekday() for c in filtered} == {0, 1, 2, 3, 6}
    top = [(t["date"], t["amount_label"]) for t in page["top5"]]
    assert top[:3] == [
        ("2027-01-02", "TWD 3,000"),
        ("2026-12-04", "TWD 4,000"),
        ("2027-02-05", "TWD 4,000"),
    ]
    e = page["exploration"]
    assert e["month_label"] == "2026 年 12 月～2027 年 2 月"
    assert e["weekdays_label"] == "週五、週六出發"
    assert e["conditions_label"] == "週五、週六出發"
    assert e["month_to"] == "2027-02" and e["stale_fallback"] == EXPLORATION_STALE_FALLBACK
    assert e["month_watch_label"] == EXPLORATION_RANGE_WATCH_BUTTON
    assert page["top_scope_note"] == "只比較所選月份內符合出發星期、且有查到價格的出發日。"
    [row] = harness.services.exploration_views.explore_page()["recent"]
    assert row["month"] == "2026 年 12 月～2027 年 2 月"
    assert row["conditions_label"] == "週五、週六出發"


def test_weekday_filter_wins_over_past_and_out_of_range(
    harness: Harness, queue: Queue
) -> None:  # C-76
    exploration_id = explored(harness, queue, month="2026-10", depart_weekdays=[0, 4])
    page = harness.services.exploration_views.exploration_page(exploration_id)
    assert page is not None
    by_day = {c["date"]: c for c in cells(page)}
    assert by_day["2026-10-06"]["status"] == "weekday_filtered"  # past Tuesday
    assert by_day["2026-10-02"]["label"] == EXPLORATION_CELL_LABELS["past"]  # past Friday
    assert by_day["2026-10-05"]["label"] == EXPLORATION_CELL_LABELS["past"]  # past Monday
    assert by_day["2026-10-26"]["status"] == "ok" and by_day["2026-10-30"]["status"] == "ok"
    set_limit(harness, 200)
    # 2027-09 with 30-day stays: from 09-26 the return leaves the 365-day horizon.
    far = explored(harness, queue, month="2027-09", trip_days=30, depart_weekdays=[0])
    page = harness.services.exploration_views.exploration_page(far)
    assert page is not None
    by_day = {c["date"]: c for c in cells(page)}
    assert by_day["2027-09-27"]["label"] == EXPLORATION_CELL_LABELS["out_of_range"]  # Monday
    assert by_day["2027-09-28"]["status"] == "weekday_filtered"  # Tuesday
    assert by_day["2027-09-20"]["status"] == "ok"


def test_all_weekdays_single_month_has_no_filtered_cell(harness: Harness, queue: Queue) -> None:
    exploration_id = explored(harness, queue)  # AC-D11
    page = harness.services.exploration_views.exploration_page(exploration_id)
    assert page is not None and len(page["calendar_months"]) == 1
    assert all(c["status"] != "weekday_filtered" for c in cells(page))
    e = page["exploration"]
    assert e["month_label"] == "2026 年 12 月" and e["weekdays_label"] is None
    assert e["month_watch_label"] == EXPLORATION_MONTH_WATCH_BUTTON
    html = harness.client.get(f"/explorations/{exploration_id}").text
    assert "<h3>" not in html and "未查（星期篩選）" not in html


def test_range_page_html(harness: Harness, queue: Queue) -> None:  # C-76, AC-M6
    set_limit(harness, 200)
    exploration_id = explored(harness, queue, **THREE_MONTHS, depart_weekdays=FRI_SAT)
    html = harness.client.get(f"/explorations/{exploration_id}").text
    for label in ("2026 年 12 月", "2027 年 1 月", "2027 年 2 月"):
        assert f"<h3>{label}</h3>" in html
    assert html.count("<h3>") == 3
    single = harness.client.get(f"/explorations/{explored(harness, queue)}").text
    # Disclaimer and legend once per page, as on a single-month page (not once per month).
    assert html.count(DISCLAIMER) == single.count(DISCLAIMER) >= 1
    assert html.count("分成低／中／高三段") == single.count("分成低／中／高三段") == 1
    assert "未查（星期篩選）" in html
    assert EXPLORATION_RANGE_WATCH_BUTTON in html


# ---- explore page context (contract §4) ---------------------------------------------------


def test_explore_page_new_fields(harness: Harness) -> None:
    data = harness.services.exploration_views.explore_page()
    values = data["values"]
    assert values["month_to"] == values["month"] == "2026-11"
    assert values["depart_weekdays"] == list(ALL_WEEKDAYS)
    assert data["weekday_options"] == [
        {"value": i, "label": label}
        for i, label in enumerate(("週一", "週二", "週三", "週四", "週五", "週六", "週日"))
    ]
    assert data["max_months"] == 3 and data["over_limit_text"] == EXPLORATION_TOO_MANY_CELLS
    counts = data["quota"]["weekday_counts"]
    assert list(counts) == [m["value"] for m in data["month_options"]]
    assert counts["2026-12"] == list(month_weekday_counts(2026, 12, TODAY))
    assert counts["2026-10"] == [1, 1, 1, 1, 1, 1, 1]


# ---- prefill (C-47 extended, Decision 6) --------------------------------------------------


def test_range_prefill_window_and_weekdays(harness: Harness, queue: Queue) -> None:
    exploration_id = explored(harness, queue, **THREE_MONTHS, depart_weekdays=FRI_SAT)
    values, note, sampled = harness.services.exploration_views.watch_prefill(
        harness.services.views.form_values(None), str(exploration_id), None, "month"
    )
    assert note == EXPLORATION_PREFILL_OK and sampled
    assert (values["window_start"], values["window_end"]) == ("2026-12-01", "2027-03-05")
    assert values["depart_weekdays"] == FRI_SAT and values["date_mode"] == "flexible"
    outcome = validate_watch_input({**values, "budget": "30000"}, TODAY)
    assert outcome.spec is not None, outcome.errors
    departs = {p.depart for p in expand_pairs(outcome.spec, TODAY)}
    expected = {
        date(2026, 12, 1) + timedelta(days=i)
        for i in range(90)
        if (date(2026, 12, 1) + timedelta(days=i)).weekday() in (4, 5)
    }
    assert departs == expected
    assert harness.repo.list_watches() == []  # nothing written


def test_range_prefill_end_is_capped_at_the_horizon(harness: Harness, queue: Queue) -> None:
    set_limit(harness, 200)
    exploration_id = explored(
        harness, queue, month="2027-07", month_to="2027-09", depart_weekdays=[0], trip_days=30
    )
    values, note, _ = harness.services.exploration_views.watch_prefill(
        harness.services.views.form_values(None), str(exploration_id), None, "month"
    )
    assert note == EXPLORATION_PREFILL_OK
    assert values["window_end"] == (TODAY + timedelta(days=365)).isoformat()


def test_single_cell_prefill_keeps_all_weekdays(harness: Harness, queue: Queue) -> None:
    exploration_id = explored(harness, queue, **THREE_MONTHS, depart_weekdays=FRI_SAT)
    values, note, _ = harness.services.exploration_views.watch_prefill(
        harness.services.views.form_values(None), str(exploration_id), "2027-02-05", None
    )
    assert note == EXPLORATION_PREFILL_OK and values["date_mode"] == "fixed"
    assert values["depart_date"] == "2027-02-05" and values["depart_weekdays"] == list(ALL_WEEKDAYS)


def test_single_month_prefill_is_unchanged(harness: Harness, queue: Queue) -> None:
    exploration_id = explored(harness, queue)
    values, _, _ = harness.services.exploration_views.watch_prefill(
        harness.services.views.form_values(None), str(exploration_id), None, "month"
    )
    assert (values["window_start"], values["window_end"]) == ("2026-12-01", "2027-01-05")
    assert values["depart_weekdays"] == list(ALL_WEEKDAYS)


def test_new_strings_pass_the_banned_list() -> None:  # C-77
    for text in (
        WEEKDAYS_REQUIRED,
        WEEKDAYS_INVALID,
        WEEKDAYS_NO_MATCH_MONTHS,
        EXPLORATION_TOO_MANY_CELLS,
        MONTH_TO_BEFORE,
        MONTH_SPAN_TOO_LONG,
        EXPLORATION_RANGE_WATCH_BUTTON,
        exploration_quota_message(20, 26, 12, months=3),
    ):
        assert not any(p in text for p in BANNED_PHRASES), text


def test_sampled_note_wording_by_month_count(harness: Harness, queue: Queue) -> None:
    single = "以整月建立的彈性窗監看每輪最多查 12 組日期，輪換取樣"
    assert exploration_sampled_note(12) == exploration_sampled_note(12, months=1) == single
    ranged = exploration_sampled_note(12, months=3)
    assert ranged == "以所選月份建立的彈性窗監看每輪最多查 12 組日期，輪換取樣"
    assert not any(p in ranged for p in BANNED_PHRASES)
    set_limit(harness, 200)
    one = explored(harness, queue)
    assert harness.services.exploration_views.exploration_page(one)["sampled_note"] == single
    many = explored(harness, queue, **THREE_MONTHS, depart_weekdays=FRI_SAT)
    views = harness.services.exploration_views
    assert views.exploration_page(many)["sampled_note"] == ranged
    _, _, note = views.watch_prefill(
        harness.services.views.form_values(None), str(many), None, "month"
    )
    assert note == ranged

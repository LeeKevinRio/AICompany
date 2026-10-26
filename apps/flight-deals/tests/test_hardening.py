"""Hardening from QA review: bounded date windows, timeouts, crashed scans, huge ints."""

from __future__ import annotations

import sqlite3
import threading
import time
from datetime import date, timedelta
from typing import Any

import pytest

from flight_deals.domain.dates import MAX_EXPAND_SPAN_DAYS, expand_pairs, first_pair, is_expired
from flight_deals.domain.models import DatePair, FlightSearch, WatchSpec
from flight_deals.domain.validation import (
    MAX_DAYS_AHEAD,
    setting_rules,
    validate_settings,
    validate_watch_input,
)
from flight_deals.sources._support import (
    Throttle,
    TimeoutRunner,
    TTLCache,
    WorkersExhaustedError,
)
from flight_deals.sources.google_flights import GoogleFlightsSource
from tests.conftest import CLIENT_HEADERS, FakeClock, Harness

TODAY = date(2026, 10, 25)  # FakeClock default, Asia/Taipei


def flexible(start: str, end: str, **extra: Any) -> dict[str, Any]:
    body: dict[str, Any] = {
        "destination": "NRT",
        "trip_type": "round_trip",
        "date_mode": "flexible",
        "window_start": start,
        "window_end": end,
        "min_trip_days": "3",
        "max_trip_days": "10",
        "budget": "12000",
    }
    body.update(extra)
    return body


def raw_spec(**overrides: Any) -> WatchSpec:
    values: dict[str, Any] = dict(
        name="extreme",
        origin="TPE",
        destination="NRT",
        trip_type="round_trip",
        date_mode="flexible",
        depart_date=None,
        return_date=None,
        window_start=date(2026, 11, 1),
        window_end=date(9999, 12, 31),
        min_trip_days=3,
        max_trip_days=10,
        max_stops=None,
        budget_amount_minor=1_200_000,
    )
    values.update(overrides)
    return WatchSpec(**values)


# ---- 1. bounded windows ---------------------------------------------------------


@pytest.mark.parametrize("end", ["2206-12-31", "9999-12-31"])
def test_far_future_window_rejected_by_api(harness: Harness, end: str) -> None:
    response = harness.client.post(
        "/api/watches", json=flexible("2026-11-01", end), headers=CLIENT_HEADERS
    )
    assert response.status_code == 422
    assert "365" in response.json()["errors"]["window_end"]
    assert harness.repo.list_watches() == []


def test_far_future_fixed_dates_rejected() -> None:
    limit = TODAY + timedelta(days=MAX_DAYS_AHEAD)
    ok = validate_watch_input(
        {
            "destination": "NRT",
            "depart_date": limit.isoformat(),
            "return_date": limit.isoformat(),
            "budget": "1",
        },
        TODAY,
    )
    assert ok.spec is not None
    too_far = (limit + timedelta(days=1)).isoformat()
    bad = validate_watch_input(
        {"destination": "NRT", "depart_date": "2026-12-01", "return_date": too_far, "budget": "1"},
        TODAY,
    )
    assert bad.spec is None and "日期不可晚於今天起 365 天" in bad.errors["return_date"]
    bad = validate_watch_input(
        {"destination": "NRT", "trip_type": "one_way", "depart_date": too_far, "budget": "1"},
        TODAY,
    )
    assert "depart_date" in bad.errors


def test_window_longer_than_366_days_rejected_on_edit() -> None:
    existing = raw_spec(window_start=date(2026, 1, 1), window_end=date(2026, 12, 31))
    outcome = validate_watch_input(flexible("2026-01-01", "2027-10-20"), TODAY, existing)
    assert outcome.spec is None
    assert outcome.errors["window_end"] == "彈性窗長度不可超過 366 天"


@pytest.mark.parametrize("end", [date(2206, 12, 31), date(9999, 12, 31), date.max])
def test_is_expired_constant_time_on_extreme_spec(end: date) -> None:
    spec = raw_spec(window_end=end)
    started = time.perf_counter()
    for _ in range(100):
        assert is_expired(spec, TODAY) is False
    assert time.perf_counter() - started < 0.1


def test_expand_pairs_is_capped_for_specs_that_bypass_validation() -> None:
    pairs = expand_pairs(raw_spec(), TODAY)
    assert pairs and pairs[-1].depart <= date(2026, 11, 1) + timedelta(days=MAX_EXPAND_SPAN_DAYS)
    assert len(pairs) < 3000


@pytest.mark.parametrize(
    "spec",
    [
        raw_spec(window_end=date(2026, 12, 20)),
        raw_spec(window_start=date(2026, 10, 1), window_end=date(2026, 10, 30)),
        raw_spec(window_start=date(2026, 10, 1), window_end=date(2026, 10, 27)),
        raw_spec(
            trip_type="one_way",
            min_trip_days=None,
            max_trip_days=None,
            window_end=date(2026, 11, 3),
        ),
        raw_spec(
            date_mode="fixed",
            depart_date=date(2026, 12, 1),
            return_date=date(2026, 12, 5),
            window_start=None,
            window_end=None,
        ),
        raw_spec(
            date_mode="fixed",
            depart_date=date(2026, 10, 1),
            return_date=date(2026, 10, 5),
            window_start=None,
            window_end=None,
        ),
    ],
)
def test_first_pair_matches_full_expansion(spec: WatchSpec) -> None:
    pairs = expand_pairs(spec, TODAY)
    assert first_pair(spec, TODAY) == (pairs[0] if pairs else None)
    assert is_expired(spec, TODAY) == (not pairs)


def test_pages_still_open_with_extreme_watch_data(harness: Harness) -> None:
    watch_id = harness.repo.insert_watch(raw_spec(), harness.clock())
    started = time.perf_counter()
    assert harness.client.get("/").status_code == 200
    assert harness.client.get(f"/watches/{watch_id}").status_code == 200
    assert harness.services.scan.expire_sweep() == []
    assert time.perf_counter() - started < 2.0
    outcome = harness.scan(watch_id)
    assert outcome.status == "ok" and outcome.queries_used <= 12


# ---- 2. timeout runner ----------------------------------------------------------


def test_timed_out_calls_do_not_block_later_calls_until_cap() -> None:
    runner = TimeoutRunner(max_in_flight=2)
    release = threading.Event()
    for _ in range(2):
        with pytest.raises(TimeoutError):
            runner.run(lambda: release.wait(5), 0.05)
    assert runner.in_flight == 2
    with pytest.raises(WorkersExhaustedError, match="workers exhausted"):
        runner.run(lambda: 1, 1.0)
    release.set()
    deadline = time.monotonic() + 2
    while runner.in_flight and time.monotonic() < deadline:
        time.sleep(0.01)
    assert runner.in_flight == 0
    assert runner.run(lambda: 7, 1.0) == 7


def test_timeout_excludes_queueing_time() -> None:
    runner = TimeoutRunner(max_in_flight=4)
    release = threading.Event()
    for _ in range(2):
        with pytest.raises(TimeoutError):
            runner.run(lambda: release.wait(5), 0.05)
    started = time.monotonic()
    assert runner.run(lambda: "fast", 0.5) == "fast"
    assert time.monotonic() - started < 0.4
    release.set()


def test_runner_propagates_exceptions() -> None:
    runner = TimeoutRunner()

    def boom() -> None:
        raise ValueError("bad page")

    with pytest.raises(ValueError, match="bad page"):
        runner.run(boom, 1.0)
    assert runner.in_flight == 0


def test_adapter_reports_workers_exhausted(clock: FakeClock) -> None:
    release = threading.Event()
    source = GoogleFlightsSource(
        timeout_seconds=0.05,
        max_attempts=1,
        backoff_base_seconds=0.0,
        throttle=Throttle(0.0),
        cache=TTLCache(0.0),
        fetch=lambda _q: [] if release.wait(5) else [],
        clock=clock,
        runner=TimeoutRunner(max_in_flight=1),
    )
    search = FlightSearch("TPE", "NRT", DatePair(date(2026, 12, 10)), None)
    first = source.search(search)
    second = source.search(search)
    release.set()
    assert first.status == "error" and "timeout" in (first.error or "")
    assert second.status == "error" and "workers exhausted" in (second.error or "")


# ---- 3. crashed scans are closed --------------------------------------------------


def test_scan_crash_marks_run_failed_and_keeps_query_count(
    harness: Harness, monkeypatch: pytest.MonkeyPatch
) -> None:
    watch_id = harness.create_watch()

    def locked(**_kwargs: Any) -> int:
        raise sqlite3.OperationalError("database is locked")

    monkeypatch.setattr(harness.repo, "insert_observation", locked)
    outcome = harness.scan(watch_id)
    assert outcome.status == "crashed"
    [run] = harness.repo.scan_runs_for_watch(watch_id)
    assert run.status == "failed" and run.finished_at is not None
    assert run.queries_used == 1
    assert run.error_summary and "掃描中斷" in run.error_summary
    assert "database is locked" in run.error_summary
    assert harness.repo.queries_used_since(harness.clock() - timedelta(hours=1)) == 1


# ---- 4. huge integers ------------------------------------------------------------


def test_huge_integer_strings_rejected_not_500(harness: Harness) -> None:
    huge = "9" * 5000
    response = harness.client.post(
        "/api/watches",
        json={
            "destination": "NRT",
            "depart_date": "2026-12-10",
            "return_date": "2026-12-15",
            "budget": huge,
            "max_stops": huge,
        },
        headers=CLIENT_HEADERS,
    )
    assert response.status_code == 422
    assert set(response.json()["errors"]) >= {"budget", "max_stops"}
    settings = harness.client.post(
        "/api/settings", json={"max_pairs_per_scan": huge}, headers=CLIENT_HEADERS
    )
    assert settings.status_code == 422
    assert "數值過大" in settings.json()["errors"]["max_pairs_per_scan"]


def test_huge_json_number_literal_is_not_500(harness: Harness) -> None:
    body = '{"destination": "NRT", "budget": ' + "9" * 5000 + "}"
    response = harness.client.post(
        "/api/watches",
        content=body,
        headers={**CLIENT_HEADERS, "Content-Type": "application/json"},
    )
    # Python's int-digit limit makes the JSON decoder fail; FastAPI answers 400, not 500.
    assert response.status_code == 400


def test_parse_int_length_guard() -> None:
    _, errors = validate_settings({"global_hourly_query_limit": "1" * 13}, setting_rules(30))
    assert errors["global_hourly_query_limit"].endswith("數值過大")
    _, errors = validate_settings({"global_hourly_query_limit": "-" + "1" * 13}, setting_rules(30))
    assert errors["global_hourly_query_limit"].endswith("數值過大")

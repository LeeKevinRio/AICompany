"""Exploration execution, quota, reuse, restart and purge (FD-6 Decision 3, C-45)."""

from __future__ import annotations

import ast
from collections.abc import Iterator
from datetime import timedelta
from pathlib import Path
from typing import Any

import pytest

from flight_deals.domain.messages import (
    EXPLORATION_BUSY,
    EXPLORATION_HOURLY_LIMIT,
    EXPLORATION_RESTARTED,
    exploration_quota_message,
)
from flight_deals.domain.models import FlightSearch
from flight_deals.ports import SourceResult
from flight_deals.scheduler import ScanScheduler
from flight_deals.scheduler.jobs import EXPLORE_PREFIX, PURGE_JOB_ID
from flight_deals.services.exploration import ExplorationService
from tests.conftest import CLIENT_HEADERS, FakeLock, Harness

SRC = Path(__file__).resolve().parents[1] / "src" / "flight_deals"
DECEMBER: dict[str, Any] = {
    "origin": "TPE",
    "destination": "NRT",
    "trip_type": "round_trip",
    "month": "2026-12",
    "trip_days": 5,
    "max_stops": "",
    "adults": 1,
    "children": 0,
    "cabin": "economy",
    "airlines": [],
    "dep_hour_from": None,
    "dep_hour_to": None,
}


class Queue:
    """Stands in for the scheduler: records explore jobs, runs them on demand."""

    def __init__(self, service: ExplorationService) -> None:
        self.service = service
        self.ids: list[int] = []
        service.hooks.schedule = self.ids.append
        service.hooks.scheduler_running = lambda: True

    def run_all(self) -> None:
        while self.ids:
            self.service.run(self.ids.pop(0))


@pytest.fixture
def queue(harness: Harness) -> Iterator[Queue]:
    yield Queue(harness.services.exploration)


def post(harness: Harness, **overrides: Any) -> Any:
    return harness.client.post(
        "/api/explorations", json={**DECEMBER, **overrides}, headers=CLIENT_HEADERS
    )


def start(harness: Harness, **overrides: Any) -> int:
    response = post(harness, **overrides)
    assert response.status_code == 202, response.json()
    body = response.json()
    assert body["ok"] is True and body["reused"] is False
    return int(body["id"])


def table_rows(harness: Harness, table: str) -> list[tuple[Any, ...]]:
    with harness.repo.db.connect() as conn:
        return [tuple(r) for r in conn.execute(f"SELECT * FROM {table} ORDER BY rowid")]


def set_limit(harness: Harness, limit: int, reserve: int = 0) -> None:
    errors = harness.services.settings.update(
        {"global_hourly_query_limit": str(limit), "exploration_reserve_for_scans": str(reserve)}
    )
    assert errors == {}


# ---- creation: no query, one job, quota ---------------------------------------------


def test_post_sends_no_query_and_queues_one_job(harness: Harness, queue: Queue) -> None:
    exploration_id = start(harness)
    assert harness.source.calls == []  # C-45: nothing is queried during the request
    assert queue.ids == [exploration_id]
    record = harness.repo.get_exploration(exploration_id)
    assert record.status == "queued" and record.total == 31 and record.done == 0
    cells = harness.repo.exploration_cells(exploration_id)
    assert len(cells) == 31 and {c.status for c in cells} == {"pending"}


def test_full_month_queries_exactly_31_times(harness: Harness, queue: Queue) -> None:  # AC-R1
    exploration_id = start(harness)
    queue.run_all()
    assert len(harness.source.calls) == 31
    record = harness.repo.get_exploration(exploration_id)
    assert (record.status, record.done, record.queries_used) == ("done", 31, 31)
    assert record.error_summary is None
    cells = harness.repo.exploration_cells(exploration_id)
    assert {c.status for c in cells} == {"ok"}
    assert cells[-1].return_date.isoformat() == "2027-01-05"  # AC-I7
    assert harness.repo.queries_used_since(harness.clock() - timedelta(hours=1)) == 31


def test_current_month_counts_only_remaining_days(harness: Harness, queue: Queue) -> None:
    exploration_id = start(harness, month="2026-10")  # today is 2026-10-25 (Taipei)
    assert harness.repo.get_exploration(exploration_id).total == 7
    queue.run_all()
    departs = [q.pair.depart.isoformat() for q in harness.source.calls]
    assert departs[0] == "2026-10-25" and departs[-1] == "2026-10-31" and len(departs) == 7


def test_quota_refusal_reports_left_and_needed(harness: Harness, queue: Queue) -> None:  # AC-Q1
    set_limit(harness, 20)
    response = post(harness)
    assert response.status_code == 409
    assert response.json() == {
        "ok": False,
        "code": "quota",
        "hourly_left": 20,
        "needed": 31,
        "message": exploration_quota_message(20, 31, 0),
    }
    assert "本小時剩餘額度 20 次" in response.json()["message"]
    assert harness.source.calls == [] and queue.ids == []
    assert harness.repo.list_explorations_since(harness.clock() - timedelta(days=1)) == []


def test_quota_boundary_and_reserve(harness: Harness, queue: Queue) -> None:  # AC-Q2
    set_limit(harness, 30)
    assert post(harness).status_code == 409
    set_limit(harness, 31)
    assert post(harness).status_code == 202
    queue.ids.clear()
    harness.repo.interrupt_active_explorations(harness.clock(), "test")
    # The reserve for scans is held back: 43 - 12 = 31 is enough, 42 - 12 is not.
    set_limit(harness, 42, reserve=12)
    body = post(harness, trip_days=6).json()
    assert body["code"] == "quota" and body["hourly_left"] == 42 and body["needed"] == 31
    set_limit(harness, 43, reserve=12)
    assert post(harness, trip_days=6).status_code == 202


def test_reserve_defaults_to_12(harness: Harness) -> None:
    assert harness.services.settings.current().exploration_reserve_for_scans == 12


def test_quota_compares_needed_days_not_31(harness: Harness, queue: Queue) -> None:  # AC-Q3
    set_limit(harness, 7)
    assert post(harness, month="2026-10").status_code == 202  # 7 days left in October


def test_scheduler_off_is_refused(harness: Harness) -> None:
    response = post(harness)
    assert response.status_code == 409 and response.json()["code"] == "scheduler_off"
    assert harness.source.calls == []


def test_busy_and_same_conditions_while_running(harness: Harness, queue: Queue) -> None:  # AC-I9
    first = start(harness)
    same = post(harness)
    assert same.status_code == 200 and same.json() == {"ok": True, "id": first, "reused": True}
    other = post(harness, destination="KIX")
    assert other.status_code == 409
    body = other.json()
    assert body["code"] == "busy" and body["id"] == first
    assert (
        body["message"].startswith(EXPLORATION_BUSY)
        and f"/explorations/{first}" in (body["message"])
    )
    assert queue.ids == [first]


def test_reuse_within_24_hours_only(harness: Harness, queue: Queue) -> None:  # AC-Q4, AC-Q7
    first = start(harness, airlines=["BR", "CI"])
    queue.run_all()
    calls = len(harness.source.calls)
    harness.clock.advance(hours=3)
    set_limit(harness, 1)  # quota does not matter for a reuse
    again = post(harness, airlines=["CI", "BR"])  # AC-Q5: order does not matter
    assert again.status_code == 200 and again.json() == {"ok": True, "id": first, "reused": True}
    assert len(harness.source.calls) == calls and queue.ids == []
    set_limit(harness, 60)
    harness.clock.advance(hours=22)  # 25 hours after creation
    newer = post(harness, airlines=["BR", "CI"])
    assert newer.status_code == 202 and newer.json()["id"] != first


def test_explorations_with_gaps_or_failed_are_not_reused(harness: Harness, queue: Queue) -> None:
    set_limit(harness, 40)
    first = start(harness)
    # Use up the hour from elsewhere: the exploration stops with skipped cells.
    set_limit(harness, 10)
    queue.run_all()
    record = harness.repo.get_exploration(first)
    assert record.status == "done" and record.done == 10
    set_limit(harness, 60, reserve=0)
    harness.clock.advance(hours=1, minutes=1)
    assert post(harness).status_code == 202  # not reused: it has skipped cells


# ---- running: isolation, transactions, limits, breaker ------------------------------


def test_exploration_never_touches_watch_history(harness: Harness, queue: Queue) -> None:
    watch_id = harness.create_watch()
    harness.scan(watch_id)
    tables = ("watch", "price_observation", "alert_state", "notification", "scan_run")
    before = {t: table_rows(harness, t) for t in tables}
    sent = list(harness.notifier.sent)
    start(harness)
    queue.run_all()
    assert {t: table_rows(harness, t) for t in tables} == before  # AC-R10
    assert harness.notifier.sent == sent


def test_each_cell_commits_with_progress(harness: Harness, queue: Queue) -> None:
    exploration_id = start(harness)
    calls = 0

    def price(query: FlightSearch) -> int:
        nonlocal calls
        calls += 1
        if calls == 5:
            raise KeyboardInterrupt  # not contained by the adapter wrapper
        return 9000

    harness.source.price_fn = price
    with pytest.raises(KeyboardInterrupt):
        queue.run_all()
    record = harness.repo.get_exploration(exploration_id)
    assert record.done == 4 and record.queries_used == 4  # the first k cells are kept
    cells = harness.repo.exploration_cells(exploration_id)
    assert [c.status for c in cells[:4]] == ["ok"] * 4
    # A hard stop still closes the exploration instead of leaving it "running".
    assert record.status == "failed" and "KeyboardInterrupt" in (record.error_summary or "")
    assert {(c.status, c.reason) for c in cells[4:]} == {("skipped", "interrupted")}


def test_crash_marks_failed_and_skips_the_rest(
    harness: Harness, queue: Queue, monkeypatch: pytest.MonkeyPatch
) -> None:
    exploration_id = start(harness)
    real = harness.repo.record_exploration_cell
    count = 0

    def flaky(*args: Any, **kwargs: Any) -> None:
        nonlocal count
        count += 1
        if count == 4:
            raise RuntimeError("disk full")
        real(*args, **kwargs)

    monkeypatch.setattr(harness.repo, "record_exploration_cell", flaky)
    queue.run_all()
    record = harness.repo.get_exploration(exploration_id)
    assert record.status == "failed" and record.done == 3
    assert "RuntimeError" in (record.error_summary or "")
    cells = harness.repo.exploration_cells(exploration_id)
    assert [c.status for c in cells[:3]] == ["ok"] * 3
    assert {(c.status, c.reason) for c in cells[3:]} == {("skipped", "interrupted")}


def test_hourly_limit_mid_run_skips_rest(harness: Harness, queue: Queue) -> None:  # AC-R9
    set_limit(harness, 31)
    exploration_id = start(harness)
    # A scan spends 20 queries after the POST but before the job runs.
    watch_id = harness.create_watch(
        date_mode="flexible",
        window_start="2026-11-01",
        window_end="2026-11-30",
        min_trip_days=3,
        max_trip_days=3,
    )
    assert harness.services.settings.update({"max_pairs_per_scan": "20"}) == {}
    harness.scan(watch_id)
    queue.run_all()
    record = harness.repo.get_exploration(exploration_id)
    assert record.status == "done" and record.done == 11 and record.queries_used == 11
    cells = harness.repo.exploration_cells(exploration_id)
    assert {(c.status, c.reason) for c in cells[11:]} == {("skipped", "global_hourly_limit")}
    assert record.error_summary == f"{EXPLORATION_HOURLY_LIMIT}，20 天未查"


def test_breaker_open_skips_rest_and_alerts_once(harness: Harness, queue: Queue) -> None:  # AC-R5
    exploration_id = start(harness)
    harness.source.status_override = "blocked"
    queue.run_all()
    assert len(harness.source.calls) == 3  # breaker threshold
    record = harness.repo.get_exploration(exploration_id)
    assert record.status == "done" and record.done == 3
    cells = harness.repo.exploration_cells(exploration_id)
    assert {c.status for c in cells[:3]} == {"blocked"}
    assert {(c.status, c.reason) for c in cells[3:]} == {("skipped", "breaker_open")}
    assert "資料源異常" in (record.error_summary or "")
    ops = [n for n in harness.repo.list_notifications() if n.kind == "ops_source_failure"]
    assert len(ops) == 1


def test_no_embedded_results_are_not_failures(harness: Harness, queue: Queue) -> None:  # AC-R6
    def handler(query: FlightSearch) -> SourceResult:
        return SourceResult(
            "google_flights", "no_data", harness.clock(), extra={"reason": "no_embedded_results"}
        )

    harness.source.handler = handler
    exploration_id = start(harness)
    queue.run_all()
    health = harness.repo.get_source_health("google_flights")
    assert health.consecutive_failures == 0 and health.breaker_state == "closed"
    assert harness.repo.list_notifications() == []
    cells = harness.repo.exploration_cells(exploration_id)
    assert {(c.status, c.reason) for c in cells} == {("no_data", "no_embedded_results")}


def test_cached_answers_cost_nothing(harness: Harness, queue: Queue) -> None:
    def handler(query: FlightSearch) -> SourceResult:
        return SourceResult(
            "google_flights", "no_data", harness.clock(), attempts=0, from_cache=True
        )

    harness.source.handler = handler
    exploration_id = start(harness)
    queue.run_all()
    record = harness.repo.get_exploration(exploration_id)
    assert record.done == 31 and record.queries_used == 0


def test_sources_are_the_scan_objects(harness: Harness) -> None:
    scan_sources = harness.services.scan.sources
    explore_sources = harness.services.exploration.sources
    assert len(scan_sources) == len(explore_sources) == 1
    assert all(a is b for a, b in zip(scan_sources, explore_sources, strict=True))
    assert explore_sources[0] is harness.source
    assert harness.services.exploration._scan_lock is harness.services.scan.lock


def test_services_do_not_import_sources() -> None:
    for path in (SRC / "services").glob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom) and node.module:
                assert not node.module.startswith("flight_deals.sources"), path


def test_source_query_is_shared() -> None:
    for name in ("scan.py", "exploration.py"):
        text = (SRC / "services" / name).read_text(encoding="utf-8")
        assert "from flight_deals.services.source_query import" in text
        assert ".search(" not in text  # only source_query.py calls sources


# ---- restart, purge, scheduler -------------------------------------------------------


def test_recover_interrupted_marks_failed_without_requery(harness: Harness, queue: Queue) -> None:
    exploration_id = start(harness)
    harness.repo.start_exploration(exploration_id, harness.clock())
    assert harness.services.exploration.recover_interrupted() == [exploration_id]
    record = harness.repo.get_exploration(exploration_id)
    assert record.status == "failed" and record.error_summary == EXPLORATION_RESTARTED
    queue.run_all()  # a stale job would find it no longer queued
    assert harness.source.calls == []
    assert {c.reason for c in harness.repo.exploration_cells(exploration_id)} == {"interrupted"}


def test_scheduler_recovers_before_queueing_jobs(
    harness: Harness, monkeypatch: pytest.MonkeyPatch
) -> None:
    exploration = harness.services.exploration
    seen: list[int] = []
    scheduler = ScanScheduler(
        harness.services, startup_stagger_seconds=1, new_watch_delay_seconds=1, clock=harness.clock
    )
    real = exploration.recover_interrupted

    def spy() -> list[int]:
        seen.append(len(scheduler.scheduler.get_jobs()))
        return list(real())

    monkeypatch.setattr(exploration, "recover_interrupted", spy)
    try:
        scheduler.start(FakeLock(held=True))
        scheduler.scheduler.pause()  # the fake clock is in the past: keep jobs from firing
        assert seen == [0]
        assert scheduler.scheduler.get_job(PURGE_JOB_ID) is not None
        harness.create_watch()
        scheduler.sync_all()
        scheduler.schedule_exploration(7)
        job = scheduler.scheduler.get_job(f"{EXPLORE_PREFIX}7")
        assert job is not None and job.misfire_grace_time is None and job.max_instances == 1
        scan_jobs = [
            j.next_run_time
            for j in scheduler.scheduler.get_jobs()
            if j.id.startswith(("watch:", "startup:"))
        ]
        assert scheduler.next_run_time() == min(scan_jobs)
        job.remove()
        for j in scheduler.scheduler.get_jobs():
            if j.id.startswith(("watch:", "startup:")):
                j.remove()
        assert scheduler.next_run_time() is None  # purge and explore jobs are not scans
    finally:
        scheduler.shutdown()


def test_purge_keeps_recent_running_and_watch_data(harness: Harness, queue: Queue) -> None:
    watch_id = harness.create_watch()
    harness.scan(watch_id)
    old = start(harness)
    queue.run_all()
    harness.clock.advance(days=1)
    running = start(harness, destination="KIX")
    harness.repo.start_exploration(running, harness.clock())
    harness.clock.advance(days=6, minutes=1)  # old one is now 7 days and 1 minute old
    observations = harness.repo.count_observations()
    assert harness.services.exploration.purge_expired() == 1
    assert harness.repo.get_exploration(old) is None  # AC-Q9
    assert harness.repo.exploration_cells(old) == []
    assert harness.repo.get_exploration(running) is not None  # running is never purged
    assert harness.repo.count_observations() == observations
    assert harness.repo.get_watch(watch_id) is not None


def test_purge_boundary(harness: Harness, queue: Queue) -> None:
    first = start(harness)
    queue.run_all()
    harness.clock.advance(days=7)
    assert harness.services.exploration.purge_expired() == 0  # exactly 7 days: kept
    harness.clock.advance(minutes=1)
    assert harness.services.exploration.purge_expired() == 1
    assert harness.repo.get_exploration(first) is None

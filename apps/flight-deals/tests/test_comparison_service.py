"""Comparison execution, quota, reuse, mutual exclusion, restart and purge
(ADR-0002 FD-9 Decision 3, C-63, C-67)."""

from __future__ import annotations

import ast
import threading
from collections.abc import Iterator
from datetime import timedelta
from pathlib import Path
from typing import Any

import pytest

from flight_deals.domain.messages import (
    COMPARISON_BUSY,
    COMPARISON_HOURLY_LIMIT,
    COMPARISON_RESTARTED,
    COMPARISON_SCHEDULER_OFF,
    comparison_quota_message,
)
from flight_deals.domain.models import FlightSearch
from flight_deals.ports import SourceResult
from flight_deals.redact import register_secret
from flight_deals.scheduler import ScanScheduler
from flight_deals.scheduler.jobs import (
    COMPARE_PREFIX,
    COMPARE_PURGE_JOB_ID,
    NON_SCAN_JOB_IDS,
)
from flight_deals.services.comparison import ComparisonService
from tests.conftest import CLIENT_HEADERS, FakeLock, Harness
from tests.test_exploration_service import DECEMBER
from tests.test_exploration_service import Queue as ExploreQueue

SRC = Path(__file__).resolve().parents[1] / "src" / "flight_deals"
TRIP: dict[str, Any] = {
    "origin": "TPE",
    "destinations": ["NRT", "OSA", "SEL"],
    "trip_type": "round_trip",
    "date_input": "fixed",
    "depart_date": "2026-12-10",
    "return_date": "2026-12-15",
    "trip_days": None,
    "max_stops": "",
    "cabin": "economy",
}
FIVE = ["NRT", "OSA", "SEL", "BKK", "SIN"]


class Queue:
    """Stands in for the scheduler: records compare jobs, runs them on demand."""

    def __init__(self, service: ComparisonService) -> None:
        self.service = service
        self.ids: list[int] = []
        service.hooks.schedule = self.ids.append
        service.hooks.scheduler_running = lambda: True

    def run_all(self) -> None:
        while self.ids:
            self.service.run(self.ids.pop(0))


@pytest.fixture
def queue(harness: Harness) -> Iterator[Queue]:
    yield Queue(harness.services.comparison)


def post(harness: Harness, **overrides: Any) -> Any:
    return harness.client.post(
        "/api/comparisons", json={**TRIP, **overrides}, headers=CLIENT_HEADERS
    )


def start(harness: Harness, **overrides: Any) -> int:
    response = post(harness, **overrides)
    assert response.status_code == 202, response.json()
    body = response.json()
    assert body == {"ok": True, "id": body["id"], "reused": False}
    return int(body["id"])


def compared(harness: Harness, queue: Queue, **overrides: Any) -> int:
    comparison_id = start(harness, **overrides)
    queue.run_all()
    return comparison_id


def set_limit(harness: Harness, limit: int, reserve: int = 0) -> None:
    errors = harness.services.settings.update(
        {"global_hourly_query_limit": str(limit), "exploration_reserve_for_scans": str(reserve)}
    )
    assert errors == {}


def table_rows(harness: Harness, table: str) -> list[tuple[Any, ...]]:
    with harness.repo.db.connect() as conn:
        return [tuple(r) for r in conn.execute(f"SELECT * FROM {table} ORDER BY rowid")]


def no_comparisons(harness: Harness) -> bool:
    return table_rows(harness, "comparison") == [] and table_rows(harness, "comparison_cell") == []


# ---- creation: no query, one job ----------------------------------------------------------


def test_post_sends_no_query_and_queues_one_job(harness: Harness, queue: Queue) -> None:
    comparison_id = start(harness)
    assert harness.source.calls == []  # C-63: nothing is queried during the request
    assert queue.ids == [comparison_id]
    record = harness.repo.get_comparison(comparison_id)
    assert record.status == "queued" and record.total == 3 and record.done == 0
    cells = harness.repo.comparison_cells(comparison_id)
    assert [(c.position, c.destination, c.status) for c in cells] == [
        (0, "NRT", "pending"),
        (1, "OSA", "pending"),
        (2, "SEL", "pending"),
    ]


def test_queries_exactly_n_with_one_date_pair(harness: Harness, queue: Queue) -> None:  # AC-R1
    comparison_id = compared(harness, queue, destinations=FIVE)
    calls = harness.source.calls
    assert [q.destination for q in calls] == FIVE
    assert {(q.origin, q.pair.depart.isoformat(), str(q.pair.return_date)) for q in calls} == {
        ("TPE", "2026-12-10", "2026-12-15")
    }
    assert {(q.adults, q.children, q.cabin, q.airlines) for q in calls} == {(1, 0, "economy", ())}
    record = harness.repo.get_comparison(comparison_id)
    assert (record.status, record.done, record.queries_used) == ("done", 5, 5)
    assert record.error_summary is None
    cells = harness.repo.comparison_cells(comparison_id)
    assert [(c.position, c.destination, c.status) for c in cells] == [
        (i, code, "ok") for i, code in enumerate(FIVE)
    ]
    assert harness.repo.queries_used_since(harness.clock() - timedelta(hours=1)) == 5


def test_adults_in_request_are_ignored(harness: Harness, queue: Queue) -> None:  # AC-C6
    compared(harness, queue, adults=3, children=2, airlines=["BR"])
    assert {(q.adults, q.children, q.airlines) for q in harness.source.calls} == {(1, 0, ())}


def test_stay_input_queries_the_computed_return(harness: Harness, queue: Queue) -> None:  # AC-C5
    compared(harness, queue, date_input="stay", trip_days=5, return_date=None)
    assert {str(q.pair.return_date) for q in harness.source.calls} == {"2026-12-15"}


def test_one_way_ignores_return_and_days(harness: Harness, queue: Queue) -> None:
    compared(harness, queue, trip_type="one_way", date_input="stay", trip_days=5)
    assert {q.pair.return_date for q in harness.source.calls} == {None}


def test_invalid_is_422_without_row_or_query(harness: Harness, queue: Queue) -> None:  # AC-C4
    response = post(harness, destinations=["TYO", "NRT"])
    assert response.status_code == 422
    assert set(response.json()["errors"]) == {"destinations"}
    assert harness.source.calls == [] and queue.ids == [] and no_comparisons(harness)


def test_scheduler_off_is_refused(harness: Harness) -> None:
    response = post(harness)
    assert response.status_code == 409
    assert response.json() == {
        "ok": False,
        "code": "scheduler_off",
        "message": COMPARISON_SCHEDULER_OFF,
    }
    assert harness.source.calls == [] and no_comparisons(harness)


def test_schedule_failure_marks_failed(harness: Harness, queue: Queue) -> None:
    def broken(_id: int) -> None:
        raise RuntimeError("scheduler gone")

    harness.services.comparison.hooks.schedule = broken
    response = post(harness)
    assert response.status_code == 409 and response.json()["code"] == "scheduler_off"
    [record] = harness.repo.list_comparisons_since(harness.clock() - timedelta(days=1))
    assert record.status == "failed"


# ---- quota (C-63: available 0 / N-1 refuse, N / N+1 accept) --------------------------------


@pytest.mark.parametrize(
    "limit,reserve,accepted",
    [(12, 12, False), (2, 0, False), (3, 0, True), (4, 0, True), (14, 12, False), (15, 12, True)],
)
def test_quota_boundaries(
    harness: Harness, queue: Queue, limit: int, reserve: int, accepted: bool
) -> None:  # AC-R3, AC-R4
    set_limit(harness, limit, reserve)
    response = post(harness)
    if accepted:
        assert response.status_code == 202
        return
    assert response.status_code == 409
    assert response.json() == {
        "ok": False,
        "code": "quota",
        "hourly_left": limit,
        "needed": 3,
        "message": comparison_quota_message(limit, 3, reserve),
    }
    assert "本小時額度不足以開始比價，請稍後再試" in response.json()["message"]
    assert harness.source.calls == [] and queue.ids == [] and no_comparisons(harness)


def test_quota_counts_queries_already_used(harness: Harness, queue: Queue) -> None:  # AC-R3
    set_limit(harness, 60, 12)
    watch_id = harness.create_watch(
        date_mode="flexible",
        window_start="2026-11-01",
        window_end="2026-12-30",
        min_trip_days=3,
        max_trip_days=3,
    )
    assert harness.services.settings.update({"max_pairs_per_scan": "45"}) == {}
    harness.scan(watch_id)  # 45 used: 60 - 45 - 12 = 3 available
    eight = ["NRT", "OSA", "SEL", "BKK", "SIN", "HKG", "MNL", "OKA"]
    body = post(harness, destinations=eight).json()
    assert (body["code"], body["hourly_left"], body["needed"]) == ("quota", 15, 8)
    assert post(harness, destinations=eight[:3]).status_code == 202


def test_quota_view_matches_exploration(harness: Harness) -> None:  # C-63
    set_limit(harness, 40, 7)
    ours = harness.services.comparison.quota()
    theirs = harness.services.exploration.quota()
    assert (ours.hourly_left, ours.reserve) == (theirs.hourly_left, theirs.reserve) == (40, 7)
    assert ours.max_cells == 8


# ---- reuse (C-63, FR-K1..K3) ---------------------------------------------------------------


def test_reuse_within_24_hours_any_order_even_without_quota(
    harness: Harness, queue: Queue
) -> None:  # AC-K1, AC-K2
    first = compared(harness, queue)
    calls = len(harness.source.calls)
    harness.clock.advance(hours=3)
    set_limit(harness, 12, 12)  # available 0
    again = post(harness, destinations=["SEL", "NRT", "OSA"])
    assert again.status_code == 200
    assert again.json() == {"ok": True, "id": first, "reused": True}
    assert len(harness.source.calls) == calls and queue.ids == []
    set_limit(harness, 60)
    harness.clock.advance(hours=21, minutes=1)  # 24 hours and 1 minute after creation
    newer = post(harness)
    assert newer.status_code == 202 and newer.json()["id"] != first


def test_other_conditions_are_new_comparisons(harness: Harness, queue: Queue) -> None:  # AC-K2
    first = compared(harness, queue)
    for change in ({"cabin": "business"}, {"max_stops": "0"}, {"destinations": ["NRT", "OSA"]}):
        response = post(harness, **change)
        assert response.status_code == 202 and response.json()["id"] != first
        queue.run_all()


def test_failed_comparison_is_not_reused(harness: Harness, queue: Queue) -> None:  # AC-K3
    start(harness)
    harness.source.status_override = "blocked"
    set_limit(harness, 2)  # only two queries fit: the last destination is skipped
    queue.run_all()
    set_limit(harness, 60)
    harness.source.status_override = None
    harness.clock.advance(hours=2)
    assert post(harness).status_code == 202


# ---- busy and mutual exclusion -------------------------------------------------------------


def test_same_conditions_join_and_others_are_busy(harness: Harness, queue: Queue) -> None:  # AC-R9
    first = start(harness)
    same = post(harness, destinations=["OSA", "SEL", "NRT"])
    assert same.status_code == 200
    assert same.json() == {"ok": True, "id": first, "reused": False}
    other = post(harness, destinations=["NRT", "BKK"])
    assert other.status_code == 409
    body = other.json()
    assert body["code"] == "busy" and body["id"] == first
    assert body["progress_url"] == f"/comparisons/{first}"
    assert (
        body["message"].startswith(COMPARISON_BUSY) and f"/comparisons/{first}" in body["message"]
    )
    assert queue.ids == [first]
    assert len(table_rows(harness, "comparison")) == 1


def test_exploration_in_progress_blocks_comparison(harness: Harness, queue: Queue) -> None:
    explore = ExploreQueue(harness.services.exploration)
    response = harness.client.post("/api/explorations", json=DECEMBER, headers=CLIENT_HEADERS)
    assert response.status_code == 202
    exploration_id = response.json()["id"]
    body = post(harness).json()
    assert body["code"] == "busy" and body["progress_url"] == f"/explorations/{exploration_id}"
    assert "id" not in body and f"/explorations/{exploration_id}" in body["message"]
    assert no_comparisons(harness) and harness.source.calls == []
    assert explore.ids == [exploration_id]


def test_comparison_in_progress_blocks_exploration(harness: Harness, queue: Queue) -> None:
    ExploreQueue(harness.services.exploration)
    comparison_id = start(harness)
    response = harness.client.post("/api/explorations", json=DECEMBER, headers=CLIENT_HEADERS)
    assert response.status_code == 409
    body = response.json()
    assert body["code"] == "busy" and "id" not in body
    assert f"/comparisons/{comparison_id}" in body["message"]
    assert table_rows(harness, "exploration") == []


def test_finished_comparison_does_not_block_exploration(harness: Harness, queue: Queue) -> None:
    ExploreQueue(harness.services.exploration)
    compared(harness, queue)
    response = harness.client.post("/api/explorations", json=DECEMBER, headers=CLIENT_HEADERS)
    assert response.status_code == 202


def test_create_lock_is_shared_with_exploration(harness: Harness) -> None:  # C-63
    services = harness.services
    assert services.comparison._create_lock is services.exploration._create_lock
    assert services.comparison._scan_lock is services.scan.lock


def test_concurrent_creates_make_exactly_one(harness: Harness, queue: Queue) -> None:  # C-63
    ExploreQueue(harness.services.exploration)
    barrier = threading.Barrier(6)
    results: list[str] = []

    def compare(index: int) -> None:
        barrier.wait()
        codes = ["NRT", ["OSA", "SEL", "BKK", "SIN", "HKG"][index]]
        results.append(harness.services.comparison.create({**TRIP, "destinations": codes}).status)

    def explore() -> None:
        barrier.wait()
        results.append(harness.services.exploration.create(DECEMBER).status)

    threads = [threading.Thread(target=compare, args=(i,)) for i in range(5)]
    threads.append(threading.Thread(target=explore))
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    assert sorted(results).count("created") == 1 and results.count("busy") == 5
    created = len(table_rows(harness, "comparison")) + len(table_rows(harness, "exploration"))
    assert created == 1


# ---- running: isolation, transactions, limits, breaker --------------------------------------


def test_comparison_never_touches_watch_history(harness: Harness, queue: Queue) -> None:
    watch_id = harness.create_watch()
    harness.scan(watch_id)
    tables = ("watch", "price_observation", "alert_state", "notification", "scan_run")
    before = {t: table_rows(harness, t) for t in tables}
    sent = list(harness.notifier.sent)
    compared(harness, queue, destinations=FIVE)
    assert {t: table_rows(harness, t) for t in tables} == before  # AC-R11
    assert harness.notifier.sent == sent


def test_crash_after_k_cells(
    harness: Harness, queue: Queue, monkeypatch: pytest.MonkeyPatch
) -> None:  # C-63
    comparison_id = start(harness, destinations=FIVE)
    real = harness.repo.record_comparison_cell
    count = 0

    def flaky(*args: Any, **kwargs: Any) -> None:
        nonlocal count
        count += 1
        if count == 3:
            raise RuntimeError("disk full")
        real(*args, **kwargs)

    monkeypatch.setattr(harness.repo, "record_comparison_cell", flaky)
    queue.run_all()
    record = harness.repo.get_comparison(comparison_id)
    assert record.status == "failed" and record.done == 2
    assert "RuntimeError" in (record.error_summary or "")
    cells = harness.repo.comparison_cells(comparison_id)
    assert [c.status for c in cells[:2]] == ["ok", "ok"]
    assert {(c.status, c.reason) for c in cells[2:]} == {("skipped", "interrupted")}


def test_hard_stop_still_closes(harness: Harness, queue: Queue) -> None:
    comparison_id = start(harness, destinations=FIVE)
    calls = 0

    def price(query: FlightSearch) -> int:
        nonlocal calls
        calls += 1
        if calls == 2:
            raise KeyboardInterrupt
        return 9000

    harness.source.price_fn = price
    with pytest.raises(KeyboardInterrupt):
        queue.run_all()
    record = harness.repo.get_comparison(comparison_id)
    assert record.status == "failed" and record.done == 1
    assert "KeyboardInterrupt" in (record.error_summary or "")


def test_hourly_limit_mid_run(harness: Harness, queue: Queue) -> None:  # AC-R6
    comparison_id = start(harness, destinations=FIVE)
    set_limit(harness, 2)  # someone else used the hour after the POST
    queue.run_all()
    assert len(harness.source.calls) == 2
    record = harness.repo.get_comparison(comparison_id)
    assert record.status == "failed" and record.done == 2 and record.queries_used == 2
    cells = harness.repo.comparison_cells(comparison_id)
    assert {(c.status, c.reason) for c in cells[2:]} == {("skipped", "global_hourly_limit")}
    assert record.error_summary == f"{COMPARISON_HOURLY_LIMIT}，3 個目的地未查"


def test_breaker_open_mid_run(harness: Harness, queue: Queue) -> None:  # AC-R6
    comparison_id = start(harness, destinations=FIVE)
    harness.source.status_override = "blocked"
    queue.run_all()
    assert len(harness.source.calls) == 3  # breaker threshold
    record = harness.repo.get_comparison(comparison_id)
    assert record.status == "failed" and record.done == 3
    cells = harness.repo.comparison_cells(comparison_id)
    assert {c.status for c in cells[:3]} == {"blocked"}
    assert {(c.status, c.reason) for c in cells[3:]} == {("skipped", "breaker_open")}
    assert "資料源異常" in (record.error_summary or "")
    ops = [n for n in harness.repo.list_notifications() if n.kind == "ops_source_failure"]
    assert len(ops) == 1


def test_blocked_and_no_data_do_not_stop(harness: Harness, queue: Queue) -> None:  # AC-R5
    register_secret("sekrit-token-value")

    def handler(query: FlightSearch) -> SourceResult:
        now = harness.clock()
        if query.destination == "OSA":
            return SourceResult("google_flights", "blocked", now, error="403 sekrit-token-value")
        if query.destination == "SEL":
            return SourceResult("google_flights", "no_data", now)
        harness.source.handler = None
        result = harness.source.search(query)
        harness.source.calls.pop()
        harness.source.handler = handler
        return result

    harness.source.handler = handler
    comparison_id = compared(harness, queue, destinations=FIVE)
    record = harness.repo.get_comparison(comparison_id)
    assert record.status == "done" and record.done == 5
    cells = harness.repo.comparison_cells(comparison_id)
    assert [c.status for c in cells] == ["ok", "blocked", "no_data", "ok", "ok"]
    assert "sekrit-token-value" not in (cells[1].error or "") and cells[1].error


def test_no_embedded_results_are_not_failures(harness: Harness, queue: Queue) -> None:  # AC-R7
    def handler(query: FlightSearch) -> SourceResult:
        return SourceResult(
            "google_flights", "no_data", harness.clock(), extra={"reason": "no_embedded_results"}
        )

    harness.source.handler = handler
    first = compared(harness, queue, destinations=FIVE)
    compared(harness, queue, destinations=["HKG", "MNL", "OKA", "CTS", "KHH"])
    health = harness.repo.get_source_health("google_flights")
    assert health.consecutive_failures == 0 and health.breaker_state == "closed"
    assert harness.repo.list_notifications() == [] and harness.notifier.sent == []
    cells = harness.repo.comparison_cells(first)
    assert {(c.status, c.reason) for c in cells} == {("no_data", "no_embedded_results")}
    # The health page's 24-hour ratio counts comparison cells too (C-63).
    summary = harness.services.views.settings_page()["no_embedded_summary"]
    assert summary == {"ratio_pct": 100, "count": 10, "total": 10}


def test_hourly_usage_includes_comparisons(harness: Harness, queue: Queue) -> None:  # AC-R11
    compared(harness, queue)
    assert harness.services.views.settings_page()["hourly_used"] == 3


def test_cached_answers_cost_nothing(harness: Harness, queue: Queue) -> None:
    def handler(query: FlightSearch) -> SourceResult:
        return SourceResult(
            "google_flights", "no_data", harness.clock(), attempts=0, from_cache=True
        )

    harness.source.handler = handler
    record = harness.repo.get_comparison(compared(harness, queue))
    assert record.done == 3 and record.queries_used == 0


def test_sources_are_the_scan_objects(harness: Harness) -> None:  # C-63
    scan = harness.services.scan.sources
    explore = harness.services.exploration.sources
    compare = harness.services.comparison.sources
    assert len(scan) == len(explore) == len(compare) == 1
    assert all(a is b is c for a, b, c in zip(scan, explore, compare, strict=True))
    assert compare[0] is harness.source


# ---- module boundaries (C-67) ----------------------------------------------------------------


def test_services_do_not_import_sources_scheduler_or_web() -> None:
    for name in ("comparison.py", "comparison_views.py"):
        tree = ast.parse((SRC / "services" / name).read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom) and node.module:
                assert not node.module.startswith(
                    ("flight_deals.sources", "flight_deals.scheduler", "flight_deals.web")
                ), (name, node.module)


def test_comparison_uses_shared_source_query() -> None:
    text = (SRC / "services" / "comparison.py").read_text(encoding="utf-8")
    assert "from flight_deals.services.source_query import" in text
    assert "cell_update" in text and ".search(" not in text


# ---- restart, purge, scheduler -------------------------------------------------------------


def test_recover_interrupted_marks_failed_without_requery(harness: Harness, queue: Queue) -> None:
    comparison_id = start(harness)
    harness.repo.start_comparison(comparison_id, harness.clock())
    assert harness.services.comparison.recover_interrupted() == [comparison_id]
    record = harness.repo.get_comparison(comparison_id)
    assert record.status == "failed" and record.error_summary == COMPARISON_RESTARTED
    queue.run_all()  # a stale job finds it no longer queued
    assert harness.source.calls == []
    assert {c.reason for c in harness.repo.comparison_cells(comparison_id)} == {"interrupted"}


def test_scheduler_recovers_before_queueing_jobs(
    harness: Harness, monkeypatch: pytest.MonkeyPatch
) -> None:  # C-63
    comparison = harness.services.comparison
    seen: list[int] = []
    scheduler = ScanScheduler(
        harness.services, startup_stagger_seconds=1, new_watch_delay_seconds=1, clock=harness.clock
    )
    real = comparison.recover_interrupted

    def spy() -> list[int]:
        seen.append(len(scheduler.scheduler.get_jobs()))
        return list(real())

    monkeypatch.setattr(comparison, "recover_interrupted", spy)
    try:
        scheduler.start(FakeLock(held=True))
        scheduler.scheduler.pause()  # the fake clock is in the past: keep jobs from firing
        assert seen == [0]
        assert scheduler.scheduler.get_job(COMPARE_PURGE_JOB_ID) is not None
        assert COMPARE_PURGE_JOB_ID in NON_SCAN_JOB_IDS
        harness.create_watch()
        scheduler.sync_all()
        scheduler.schedule_comparison(7)
        job = scheduler.scheduler.get_job(f"{COMPARE_PREFIX}7")
        assert job is not None and job.misfire_grace_time is None and job.max_instances == 1
        scan_jobs = [
            j.next_run_time
            for j in scheduler.scheduler.get_jobs()
            if j.id.startswith(("watch:", "startup:"))
        ]
        assert scheduler.next_run_time() == min(scan_jobs)
        for j in scheduler.scheduler.get_jobs():
            if j.id.startswith(("watch:", "startup:")):
                j.remove()
        assert scheduler.next_run_time() is None  # compare and purge jobs are not scans
    finally:
        scheduler.shutdown()


def test_purge_keeps_recent_running_and_watch_data(harness: Harness, queue: Queue) -> None:
    watch_id = harness.create_watch()
    harness.scan(watch_id)
    old = compared(harness, queue)
    harness.clock.advance(days=1)
    running = start(harness, destinations=["BKK", "SIN"])
    harness.repo.start_comparison(running, harness.clock())
    harness.clock.advance(days=6, minutes=1)  # old one is now 7 days and 1 minute old
    observations = harness.repo.count_observations()
    assert harness.services.comparison.purge_expired() == 1
    assert harness.repo.get_comparison(old) is None  # AC-K4
    assert harness.repo.comparison_cells(old) == []
    assert harness.repo.get_comparison(running) is not None
    assert harness.repo.count_observations() == observations
    assert harness.repo.get_watch(watch_id) is not None


def test_purge_boundary(harness: Harness, queue: Queue) -> None:
    first = compared(harness, queue)
    harness.clock.advance(days=7)
    assert harness.services.comparison.purge_expired() == 0  # exactly 7 days: kept
    harness.clock.advance(minutes=1)
    assert harness.services.comparison.purge_expired() == 1
    assert harness.repo.get_comparison(first) is None


def test_list_query_reports_cheapest_with_tie_on_position(harness: Harness, queue: Queue) -> None:
    prices = {"NRT": 9000, "OSA": 8000, "SEL": 8000}
    harness.source.price_fn = lambda q: prices[q.destination]
    comparison_id = compared(harness, queue)
    [record] = harness.repo.list_comparisons_since(harness.clock() - timedelta(days=1))
    assert record.id == comparison_id
    assert record.min_amount_minor == 800_000 and record.min_destination == "OSA"

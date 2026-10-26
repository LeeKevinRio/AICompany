"""Scheduler wiring (C-7, FR-B1, FR-B7)."""

from __future__ import annotations

from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from pathlib import Path
from types import SimpleNamespace

import pytest
from apscheduler.events import EVENT_JOB_MAX_INSTANCES
from fastapi.testclient import TestClient

from flight_deals.app import assemble, create_app
from flight_deals.config import Config
from flight_deals.scheduler import ScanScheduler, SchedulerAlreadyRunningError
from tests.conftest import FakeClock, FakeNotifier, ScriptedSource


@pytest.fixture
def real_clock() -> FakeClock:
    return FakeClock(datetime.now(UTC).replace(microsecond=0))


@pytest.fixture
def assembly(tmp_path: Path, real_clock: FakeClock) -> Iterator[object]:
    config = Config(db_path=tmp_path / "sched.db")
    built = assemble(
        config, sources=[ScriptedSource(real_clock)], notifier=FakeNotifier(), clock=real_clock
    )
    yield built
    built.scheduler.shutdown()


def watch_payload(**overrides: object) -> dict[str, object]:
    payload: dict[str, object] = {
        "destination": "NRT",
        "depart_date": "2027-03-10",
        "return_date": "2027-03-15",
        "budget": 12000,
    }
    payload.update(overrides)
    return payload


def test_job_defaults_and_single_worker(assembly: object) -> None:
    scheduler: ScanScheduler = assembly.scheduler  # type: ignore[attr-defined]
    inner = scheduler.scheduler
    assert inner._job_defaults["coalesce"] is True
    assert inner._job_defaults["max_instances"] == 1
    assert inner._executors["default"]._pool._max_workers == 1


def test_second_start_in_same_process_is_refused(tmp_path: Path, assembly: object) -> None:
    scheduler: ScanScheduler = assembly.scheduler  # type: ignore[attr-defined]
    scheduler.start()
    other = assemble(Config(db_path=tmp_path / "other.db"), sources=[], notifier=FakeNotifier())
    with pytest.raises(SchedulerAlreadyRunningError):
        other.scheduler.start()
    scheduler.shutdown()
    other.scheduler.start()  # guard released after shutdown
    other.scheduler.shutdown()


def test_startup_only_catches_up_overdue_watches_staggered(
    assembly: object, real_clock: FakeClock
) -> None:
    services = assembly.services  # type: ignore[attr-defined]
    repo = services.watches._repo
    never = services.watches.create(watch_payload()).watch_id
    recent = services.watches.create(watch_payload(destination="KIX")).watch_id
    old = services.watches.create(watch_payload(destination="BKK")).watch_id
    now = real_clock()
    repo.record_watch_scan(
        recent,
        scanned_at=now - timedelta(minutes=10),
        sample_offset=0,
        consecutive_failed_scans=0,
        status="active",
    )
    repo.record_watch_scan(
        old,
        scanned_at=now - timedelta(days=2),
        sample_offset=0,
        consecutive_failed_scans=0,
        status="active",
    )
    scheduler: ScanScheduler = assembly.scheduler  # type: ignore[attr-defined]
    scheduler.start()
    jobs = {job.id: job for job in scheduler.scheduler.get_jobs()}
    assert f"startup:{recent}" not in jobs
    first = jobs[f"startup:{never}"].next_run_time
    second = jobs[f"startup:{old}"].next_run_time
    assert first == now + timedelta(seconds=20)
    assert second == now + timedelta(seconds=40)
    interval = timedelta(minutes=360)
    assert jobs[f"watch:{recent}"].next_run_time == now - timedelta(minutes=10) + interval
    assert scheduler.next_run_time() == first


def test_crud_rebuilds_jobs(assembly: object, real_clock: FakeClock) -> None:
    services = assembly.services  # type: ignore[attr-defined]
    scheduler: ScanScheduler = assembly.scheduler  # type: ignore[attr-defined]
    scheduler.start()
    watch_id = services.watches.create(watch_payload()).watch_id
    job = scheduler.scheduler.get_job(f"watch:{watch_id}")
    assert job is not None
    assert job.next_run_time == real_clock() + timedelta(seconds=10)
    services.watches.set_enabled(watch_id, False)
    assert scheduler.scheduler.get_job(f"watch:{watch_id}") is None
    services.watches.set_enabled(watch_id, True)
    assert scheduler.scheduler.get_job(f"watch:{watch_id}") is not None
    services.settings.update({"scan_interval_minutes": "120"})
    job = scheduler.scheduler.get_job(f"watch:{watch_id}")
    assert job.trigger.interval == timedelta(minutes=120)
    services.watches.delete(watch_id)
    assert scheduler.scheduler.get_job(f"watch:{watch_id}") is None


def test_max_instance_skip_is_recorded(assembly: object) -> None:
    scheduler: ScanScheduler = assembly.scheduler  # type: ignore[attr-defined]
    scheduler._on_event(SimpleNamespace(code=EVENT_JOB_MAX_INSTANCES, job_id="watch:1"))
    events = assembly.services.watches._repo.recent_events()  # type: ignore[attr-defined]
    assert events[0].kind == "scan_skipped" and "watch:1" in (events[0].detail or "")


def test_scheduler_runs_inside_lifespan(tmp_path: Path, real_clock: FakeClock) -> None:
    app = create_app(
        Config(db_path=tmp_path / "life.db"),
        sources=[ScriptedSource(real_clock)],
        notifier=FakeNotifier(),
        clock=real_clock,
    )
    scheduler: ScanScheduler = app.state.assembly.scheduler
    assert not scheduler.running
    with TestClient(app, base_url="http://127.0.0.1") as client:
        assert scheduler.running
        assert "執行中" in client.get("/settings").text
    assert not scheduler.running

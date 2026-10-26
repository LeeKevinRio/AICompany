"""Scheduler wiring (C-7, FR-B1, FR-B7) and the cross-process lock (C-28, AC-S1..S4)."""

from __future__ import annotations

import logging
import os
import subprocess
import sys
import time
from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest
import uvicorn
from apscheduler.events import EVENT_JOB_MAX_INSTANCES
from fastapi.testclient import TestClient

from flight_deals import cli
from flight_deals.app import (
    acquire_scheduler_lock,
    assemble,
    create_app,
    scheduler_lock_path,
)
from flight_deals.config import Config
from flight_deals.scheduler import (
    FileSchedulerLock,
    ScanScheduler,
    SchedulerAlreadyRunningError,
    SchedulerLockHeldError,
    SchedulerLockNotHeldError,
)
from tests.conftest import FakeClock, FakeLock, FakeNotifier, ScriptedSource


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
    scheduler.start(FakeLock(held=True))
    other = assemble(Config(db_path=tmp_path / "other.db"), sources=[], notifier=FakeNotifier())
    with pytest.raises(SchedulerAlreadyRunningError):
        other.scheduler.start(FakeLock(held=True))
    scheduler.shutdown()
    other.scheduler.start(FakeLock(held=True))  # guard released after shutdown
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
    scheduler.start(FakeLock(held=True))
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
    scheduler.start(FakeLock(held=True))
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


# ---- cross-process scheduler lock (FD-3 Decision 5, C-28) ------------------------------

CHILD_HOLDS_LOCK = """
import os, sys
from pathlib import Path
from flight_deals.scheduler.lock import FileSchedulerLock
lock = FileSchedulerLock(Path(sys.argv[1]))
lock.acquire()
print("locked", flush=True)
sys.stdin.readline()
os._exit(0)  # hard exit: no release, no cleanup
"""


def test_start_requires_held_lock(assembly: object) -> None:
    scheduler: ScanScheduler = assembly.scheduler  # type: ignore[attr-defined]
    with pytest.raises(SchedulerLockNotHeldError):
        scheduler.start(FakeLock(held=False))
    assert not scheduler.running


def test_lock_path_is_derived_next_to_database(tmp_path: Path) -> None:
    config = Config(db_path=tmp_path / "data" / "flight-deals.db")
    assert scheduler_lock_path(config) == tmp_path / "data" / "flight-deals.db.lock"


def test_file_lock_is_exclusive_within_one_process(tmp_path: Path) -> None:
    path = tmp_path / "x.db.lock"
    first = FileSchedulerLock(path)
    second = FileSchedulerLock(path)
    first.acquire()
    try:
        assert first.held
        with pytest.raises(
            SchedulerLockHeldError, match="此資料庫已有另一個實例在執行排程"
        ) as info:
            second.acquire()
        assert f"pid={os.getpid()}" in str(info.value)
        assert not second.held
    finally:
        first.release()
    second.acquire()
    second.release()
    first.release()  # releasing twice is harmless
    assert path.exists(), "the lock file is never deleted"


def test_file_lock_is_exclusive_across_processes_and_freed_on_hard_exit(
    tmp_path: Path,
) -> None:
    path = tmp_path / "x.db.lock"
    child = subprocess.Popen(
        [sys.executable, "-c", CHILD_HOLDS_LOCK, str(path)],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        text=True,
    )
    try:
        assert child.stdout is not None and child.stdin is not None
        assert child.stdout.readline().strip() == "locked"
        ours = FileSchedulerLock(path)
        with pytest.raises(SchedulerLockHeldError):
            ours.acquire()
        child.stdin.write("exit\n")
        child.stdin.flush()
        assert child.wait(timeout=10) == 0
        deadline = time.monotonic() + 10
        while True:  # the OS may need a moment to drop a dead process's lock
            try:
                ours.acquire()
                break
            except SchedulerLockHeldError:
                if time.monotonic() > deadline:
                    raise
                time.sleep(0.05)
        assert ours.held
        ours.release()
    finally:
        if child.poll() is None:
            child.kill()
            child.wait(timeout=10)


def test_create_app_uses_given_lock_and_releases_it(tmp_path: Path, real_clock: FakeClock) -> None:
    lock = FakeLock()
    app = create_app(
        Config(db_path=tmp_path / "fake.db"),
        sources=[ScriptedSource(real_clock)],
        notifier=FakeNotifier(),
        clock=real_clock,
        scheduler_lock=lock,
    )
    assert lock.held and lock.acquire_calls == 1
    with TestClient(app, base_url="http://127.0.0.1"):
        assert app.state.assembly.scheduler.running
    assert not lock.held and lock.release_calls == 1


def test_create_app_refuses_when_lock_is_taken_before_touching_db(tmp_path: Path) -> None:
    db = tmp_path / "taken.db"
    with pytest.raises(SchedulerLockHeldError):
        create_app(
            Config(db_path=db),
            sources=[],
            notifier=FakeNotifier(),
            scheduler_lock=FakeLock(available=False),
        )
    assert not db.exists(), "no migration ran"


def test_web_only_app_takes_no_lock(tmp_path: Path) -> None:
    lock = FakeLock(available=False)
    app = create_app(
        Config(db_path=tmp_path / "web.db"),
        sources=[],
        notifier=FakeNotifier(),
        start_scheduler=False,
        scheduler_lock=lock,
    )
    assert lock.acquire_calls == 0 and app.state.scheduler_lock is None


def test_second_app_on_same_database_is_refused(tmp_path: Path, real_clock: FakeClock) -> None:
    config = Config(db_path=tmp_path / "same.db")

    def build() -> Any:
        return create_app(
            config, sources=[ScriptedSource(real_clock)], notifier=FakeNotifier(), clock=real_clock
        )

    first = build()
    with TestClient(first, base_url="http://127.0.0.1"):
        with pytest.raises(SchedulerLockHeldError):
            build()
    second = build()  # released when the first app's lifespan ended
    with TestClient(second, base_url="http://127.0.0.1"):
        assert second.state.assembly.scheduler.running


def test_cli_exits_2_when_database_is_locked(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    db = tmp_path / "cli.db"
    monkeypatch.setenv("FLIGHT_DEALS_DB_PATH", str(db))
    monkeypatch.setenv("FLIGHT_DEALS_SOURCES", "google_flights")
    started: list[object] = []
    monkeypatch.setattr(uvicorn, "run", lambda *a, **k: started.append(a))
    holder = acquire_scheduler_lock(Config(db_path=db))
    try:
        with caplog.at_level(logging.ERROR, logger="flight_deals"):
            assert cli.main([]) == 2
        assert started == [] and not db.exists()
        assert "此資料庫已有另一個實例在執行排程" in caplog.text
    finally:
        holder.release()
    assert cli.main([]) == 0 and len(started) == 1
    again = acquire_scheduler_lock(Config(db_path=db))  # cli released its lock on exit
    again.release()

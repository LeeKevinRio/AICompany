"""Data retention, purge backups, VACUUM and the health page block
(ADR-0002 FD-7 Decisions 7, 8, 10; C-53, C-54)."""

from __future__ import annotations

import json
import re
import sqlite3
from collections.abc import Sequence
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from typing import Any

import pytest

from flight_deals.app import assemble
from flight_deals.config import Config
from flight_deals.domain.rules import price_item_key
from flight_deals.domain.timeutil import to_utc_iso
from flight_deals.scheduler.jobs import (
    MAINTENANCE_CATCHUP_JOB_ID,
    MAINTENANCE_CHECK_JOB_ID,
    MAINTENANCE_JOB_ID,
)
from flight_deals.services.retention import RetentionService
from flight_deals.storage.db import retention_backup_path
from flight_deals.storage.repository import NotificationItemRecord, Repository
from tests.conftest import (
    CLIENT_HEADERS,
    FakeClock,
    FakeLock,
    FakeNotifier,
    Harness,
    ScriptedSource,
)

SRC = Path(__file__).resolve().parents[1] / "src" / "flight_deals"
NOW = datetime(2026, 10, 25, 4, 0, tzinfo=UTC)  # 12:00 Asia/Taipei, past 08:30


# ---- helpers -----------------------------------------------------------------------------


def retention(h: Harness) -> RetentionService:
    service = h.assembly.services.retention
    assert service is not None
    return service


def repo_of(h: Harness) -> Repository:
    repo: Repository = h.assembly.services.watches._repo
    return repo


def add_run(
    h: Harness,
    watch_id: int,
    finished: datetime | None,
    obs: Sequence[tuple[str, str | None, int]] = (),
    *,
    revision: int = 1,
    status: str = "ok",
) -> int:
    started = finished or NOW
    with h.assembly.database.connect() as conn:
        cur = conn.execute(
            "INSERT INTO scan_run (watch_id, watch_revision, started_at, finished_at, status,"
            " sampled_pairs, query_results, queries_used) VALUES (?, ?, ?, ?, ?, '[]', '[]', 1)",
            (
                watch_id,
                revision,
                to_utc_iso(started),
                to_utc_iso(finished) if finished else None,
                status,
            ),
        )
        run_id = int(cur.lastrowid or 0)
        for depart, ret, amount in obs:
            conn.execute(
                "INSERT INTO price_observation (scan_run_id, watch_id, watch_revision, source,"
                " price_kind, depart_date, return_date, amount_minor, currency, as_of,"
                " as_of_basis, fetched_at) VALUES (?, ?, ?, 'google_flights', 'live', ?, ?, ?,"
                " 'TWD', ?, 'fetch_time', ?)",
                (
                    run_id,
                    watch_id,
                    revision,
                    depart,
                    ret,
                    amount,
                    to_utc_iso(started),
                    to_utc_iso(started),
                ),
            )
    return run_id


def run_ids(h: Harness, watch_id: int | None = None) -> list[int]:
    with h.assembly.database.connect() as conn:
        if watch_id is None:
            rows = conn.execute("SELECT id FROM scan_run ORDER BY id").fetchall()
        else:
            rows = conn.execute(
                "SELECT id FROM scan_run WHERE watch_id = ? ORDER BY id", (watch_id,)
            ).fetchall()
    return [int(r["id"]) for r in rows]


def counts(path: Path) -> dict[str, int]:
    conn = sqlite3.connect(path)
    try:
        return {
            t: conn.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0]
            for t in ("watch", "scan_run", "price_observation", "notification", "notification_item")
        }
    finally:
        conn.close()


def orphans(h: Harness) -> list[Any]:
    with h.assembly.database.connect() as conn:
        bad = conn.execute("PRAGMA foreign_key_check").fetchall()
        bad += conn.execute(
            "SELECT o.id FROM price_observation o LEFT JOIN scan_run s ON s.id = o.scan_run_id"
            " WHERE s.id IS NULL"
        ).fetchall()
        bad += conn.execute(
            "SELECT i.id FROM notification_item i LEFT JOIN notification n"
            " ON n.id = i.notification_id WHERE n.id IS NULL"
        ).fetchall()
    return list(bad)


def old_runs(h: Harness, watch_id: int, ages_days: Sequence[int]) -> list[int]:
    return [add_run(h, watch_id, NOW - timedelta(days=d)) for d in ages_days]


@pytest.fixture
def h(harness: Harness) -> Harness:
    return harness


# ---- timing and locking (C-53) -----------------------------------------------------------


def test_runs_once_per_day_after_digest_plus_30_minutes(h: Harness) -> None:
    service = retention(h)
    assert service.daily_time() == (8, 30)
    assert service.maintain(datetime(2026, 10, 25, 0, 29, tzinfo=UTC)) == "not_due"  # 08:29
    assert service.maintain(datetime(2026, 10, 25, 0, 30, tzinfo=UTC)) == "done"
    assert service.maintain(NOW) == "not_due"  # same Taipei day
    assert service.maintain(NOW + timedelta(days=1)) == "done"


def test_daily_time_follows_digest_time_and_stays_on_the_day(h: Harness) -> None:
    h.services.settings.update({"digest_time": "23:50"})
    assert retention(h).daily_time() == (23, 59)
    h.services.settings.update({"digest_time": "07:15"})
    assert retention(h).daily_time() == (7, 45)


def test_holds_the_scan_lock_and_defers_when_busy(
    h: Harness, monkeypatch: pytest.MonkeyPatch
) -> None:  # AC-R8
    watch_id = h.create_watch()
    old_runs(h, watch_id, range(200, 215))
    lock = h.services.scan.lock
    assert lock.acquire()
    try:
        assert retention(h).maintain(NOW) == "deferred"
    finally:
        lock.release()
    seen: list[bool] = []
    real = repo_of(h).delete_scan_runs

    def spy(ids: Sequence[int]) -> tuple[int, int]:
        seen.append(lock.locked())
        return real(ids)

    monkeypatch.setattr(h.repo, "delete_scan_runs", spy)
    assert retention(h).maintain(NOW) == "done"
    assert seen and all(seen) and not lock.locked()


def test_defers_while_an_exploration_runs(h: Harness) -> None:  # AC-R8
    from flight_deals.domain.models import DatePair, ExplorationSpec

    spec = ExplorationSpec("TPE", "NRT", "one_way", 2026, 12, None, None)
    exploration_id = h.repo.insert_exploration(spec, [DatePair(date(2026, 12, 1))], NOW)
    h.repo.start_exploration(exploration_id, NOW)
    assert retention(h).maintain(NOW) == "deferred"


def test_scheduler_jobs_and_next_run_time(tmp_path: Path) -> None:  # C-54
    clock = FakeClock(datetime.now(UTC).replace(microsecond=0))
    built = assemble(
        Config(db_path=tmp_path / "s.db"),
        sources=[ScriptedSource(clock)],
        notifier=FakeNotifier(),
        clock=clock,
    )
    scheduler = built.scheduler
    try:
        scheduler.start(FakeLock(held=True))
        ids = {job.id for job in scheduler.scheduler.get_jobs()}
        assert {MAINTENANCE_JOB_ID, MAINTENANCE_CHECK_JOB_ID, MAINTENANCE_CATCHUP_JOB_ID} <= ids
        assert scheduler.next_run_time() is None  # no watch: maintenance is not a scan
        scheduler.schedule_manual_digest(5, "digest-manual:1:5")
        assert scheduler.next_run_time() is None
        scheduler.trigger_command_scan(42)
        assert scheduler.next_run_time() is not None
    finally:
        scheduler.shutdown()


# ---- what is deleted and what is kept (C-53) ---------------------------------------------


def test_181_days_deleted_179_kept(h: Harness) -> None:  # AC-R1
    watch_id = h.create_watch()
    a = add_run(h, watch_id, NOW - timedelta(days=181), [("2026-04-01", "2026-04-05", 900_000)])
    b = add_run(h, watch_id, NOW - timedelta(days=179), [("2026-04-01", "2026-04-05", 900_000)])
    recent = [
        add_run(h, watch_id, NOW - timedelta(hours=i), [("2026-12-10", "2026-12-15", 800_000 + i)])
        for i in range(10, 0, -1)
    ]
    assert retention(h).maintain(NOW) == "done"
    assert run_ids(h, watch_id) == [b, *recent]
    assert a not in run_ids(h) and orphans(h) == []
    assert h.repo.count_observations(watch_id) == 11


def test_latest_runs_per_watch_are_always_kept(h: Harness) -> None:  # AC-R4, AC-R5
    h.services.settings.update({"retention_days": 30})
    long_idle = h.create_watch()
    small = h.create_watch(destination="KIX")
    other = h.create_watch(destination="BKK")
    idle_runs = old_runs(h, long_idle, range(100, 85, -1))  # 15 runs, all > 30 days
    small_runs = old_runs(h, small, range(90, 84, -1))  # only 6 runs
    other_runs = old_runs(h, other, range(5, 0, -1))
    assert retention(h).maintain(NOW) == "done"
    assert run_ids(h, long_idle) == idle_runs[-10:]
    assert run_ids(h, small) == small_runs
    assert run_ids(h, other) == other_runs
    response = h.client.post(
        "/api/settings", json={"retention_keep_runs": 2}, headers=CLIENT_HEADERS
    )
    assert response.status_code == 422
    h.services.settings.update({"retention_keep_runs": 3})
    assert retention(h).maintain(NOW + timedelta(days=1)) == "done"
    assert run_ids(h, long_idle) == idle_runs[-3:]
    assert run_ids(h, small) == small_runs[-3:]


def test_running_runs_are_never_deleted(h: Harness) -> None:
    watch_id = h.create_watch()
    with h.assembly.database.connect() as conn:
        conn.execute(
            "INSERT INTO scan_run (watch_id, watch_revision, started_at, status, sampled_pairs)"
            " VALUES (?, 1, ?, 'running', '[]')",
            (watch_id, to_utc_iso(NOW - timedelta(days=400))),
        )
    old_runs(h, watch_id, range(300, 280, -1))
    retention(h).maintain(NOW)
    with h.assembly.database.connect() as conn:
        assert (
            conn.execute("SELECT COUNT(*) FROM scan_run WHERE status = 'running'").fetchone()[0]
            == 1
        )


def scan_rotating_watch(h: Harness, rounds: int) -> int:
    """A flexible one-way window of 20 dates sampled 2 per round (rotation), one round a
    day; round 3 holds the all-time lowest price."""
    h.services.settings.update({"max_pairs_per_scan": 2})
    watch_id = h.create_watch(
        trip_type="one_way",
        date_mode="flexible",
        depart_date="",
        return_date="",
        window_start="2027-03-01",
        window_end="2027-03-20",
        budget=1,
    )
    for index in range(rounds):
        h.source.price_fn = lambda q, i=index: (
            5_000 if i == 3 else 10_000 + (q.pair.depart.day * 37 + i * 53) % 900
        )
        h.scan(watch_id)
        h.clock.advance(days=1)
    return watch_id


def snapshot_texts(h: Harness, watch_id: int, now: datetime) -> dict[str, Any]:
    watch = h.repo.get_watch(watch_id)
    commands = h.services.commands
    assert commands is not None
    return {
        "list_page": h.services.views.list_page(),
        "digest": h.services.digest.compose(now),
        "list_command": commands.list_text(now),
        "min_amount": h.repo.min_amount(
            watch_id=watch_id, revision=watch.revision, price_kind="live", currency="TWD"
        ),
    }


def test_purge_keeps_list_digest_and_baseline_numbers(h: Harness) -> None:  # FR-R6, AC-R6
    watch_id = scan_rotating_watch(h, 40)
    # Every run is now past the 30-day period: only the latest 3 are kept by count, so
    # the other date pairs' newest observations depend on the snapshot protection.
    h.clock.advance(days=35)
    now = h.clock.now
    h.services.settings.update({"retention_days": 30, "retention_keep_runs": 3})
    before = snapshot_texts(h, watch_id, now)
    runs_before = run_ids(h, watch_id)
    assert retention(h).maintain(now) == "done"
    runs_after = run_ids(h, watch_id)
    assert len(runs_after) < len(runs_before)  # something was really purged
    assert runs_before[3] in runs_after  # the all-time lowest price's run stays
    assert snapshot_texts(h, watch_id, now) == before
    assert before["min_amount"] == 500_000
    assert orphans(h) == []


def insert_note(
    h: Harness,
    kind: str,
    age_days: int,
    *,
    watch_id: int | None = None,
    items: Sequence[NotificationItemRecord] = (),
) -> int:
    notification_id = h.repo.insert_notification(
        watch_id=watch_id,
        kind=kind,
        rule="below_budget" if kind == "price_alert" else None,
        price_kind="live" if kind == "price_alert" else None,
        observation_id=None,
        channel="telegram",
        dedupe_key=f"{kind}:{age_days}:{len(items)}:{watch_id}",
        message_text="x",
        created_at=NOW - timedelta(days=age_days),
        items=items,
    )
    assert notification_id is not None
    return int(notification_id)


def item(watch_id: int, depart: str, ret: str | None, amount: int) -> NotificationItemRecord:
    d = date.fromisoformat(depart)
    r = date.fromisoformat(ret) if ret else None
    return NotificationItemRecord(
        item_key=price_item_key(watch_id, 1, "live", d, r, amount),
        depart_date=d,
        return_date=r,
        amount_minor=amount,
        currency="TWD",
        reasons=("below_budget",),
        carrier=None,
        fetched_at=NOW,
    )


def test_notification_retention(h: Harness) -> None:  # AC-R3, AC-S6
    watch_id = h.create_watch()
    old, new = {}, {}
    for kind in ("command", "manual_digest", "daily_digest", "test"):
        old[kind] = insert_note(h, kind, 366)
        new[kind] = insert_note(h, kind, 364)
    past_alert = insert_note(
        h,
        "price_alert",
        366,
        watch_id=watch_id,
        items=[item(watch_id, "2025-10-01", "2025-10-05", 700_000)],
    )
    future_alert = insert_note(
        h,
        "price_alert",
        400,
        watch_id=watch_id,
        items=[item(watch_id, "2026-12-10", "2026-12-15", 900_000)],
    )
    recent_alert = insert_note(
        h,
        "price_alert",
        364,
        watch_id=watch_id,
        items=[item(watch_id, "2025-10-02", "2025-10-05", 710_000)],
    )
    assert retention(h).maintain(NOW) == "done"
    left = {r.id for r in h.repo.list_notifications(1000)}
    assert left.isdisjoint(old.values()) and set(new.values()) <= left
    assert past_alert not in left and {future_alert, recent_alert} <= left
    assert orphans(h) == []
    # Dedupe still knows the future item: the same price is not pushed again.
    h.source.prices[("2026-12-10", "2026-12-15")] = 9_000
    h.scan(watch_id)
    alerts = [r for r in h.repo.list_notifications(1000) if r.kind == "price_alert"]
    assert {r.id for r in alerts} == {future_alert, recent_alert}


def test_purge_never_touches_watches_settings_alert_state_or_explorations(h: Harness) -> None:
    from flight_deals.domain.models import DatePair, ExplorationSpec
    from flight_deals.storage.repository import AlertStateRecord

    h.services.settings.update({"scan_interval_minutes": 120, "retention_days": 30})
    watch_id = h.create_watch()
    old_runs(h, watch_id, range(400, 380, -1))
    h.repo.save_alert_state(watch_id, "live", AlertStateRecord(1, NOW, False))
    spec = ExplorationSpec("TPE", "NRT", "one_way", 2026, 12, None, None)
    h.repo.insert_exploration(spec, [DatePair(date(2026, 12, 1))], NOW - timedelta(days=3))
    tables = ("watch", "alert_state", "exploration", "exploration_cell", "source_health")

    def dump() -> dict[str, list[Any]]:
        with h.assembly.database.connect() as conn:
            result = {t: [tuple(r) for r in conn.execute(f"SELECT * FROM {t}")] for t in tables}
            result["settings"] = [
                tuple(r)
                for r in conn.execute(
                    "SELECT key, value FROM app_setting WHERE key NOT LIKE 'state.%'"
                )
            ]
        return result

    before = dump()
    assert retention(h).maintain(NOW) == "done"
    assert dump() == before


def test_batches_and_resume_after_a_crash(
    h: Harness, monkeypatch: pytest.MonkeyPatch
) -> None:  # FR-S3, AC-S5
    watch_id = h.create_watch()
    with h.assembly.database.connect() as conn:
        old = to_utc_iso(NOW - timedelta(days=300))
        conn.executemany(
            "INSERT INTO scan_run (watch_id, watch_revision, started_at, finished_at, status,"
            " sampled_pairs) VALUES (?, 1, ?, ?, 'ok', '[]')",
            [(watch_id, old, old)] * 1210,
        )
        conn.execute(
            "INSERT INTO price_observation (scan_run_id, watch_id, watch_revision, source,"
            " price_kind, depart_date, amount_minor, currency, as_of, as_of_basis, fetched_at)"
            " SELECT id, watch_id, 1, 'google_flights', 'live', '2026-01-01', 900000 + id, 'TWD',"
            " started_at, 'fetch_time', started_at FROM scan_run"
        )
    sizes: list[int] = []
    real = repo_of(h).delete_scan_runs

    def crash_on_second(ids: Sequence[int]) -> tuple[int, int]:
        sizes.append(len(ids))
        if len(sizes) == 2:
            raise sqlite3.OperationalError("disk I/O error")
        return real(ids)

    monkeypatch.setattr(h.repo, "delete_scan_runs", crash_on_second)
    assert retention(h).maintain(NOW) == "failed"
    assert sizes == [500, 500] and orphans(h) == []
    assert len(run_ids(h)) == 1210 - 500
    view = h.services.views.settings_page()["maintenance"]
    assert "清除未完成" in view["last_run_summary"] and "disk I/O error" in view["last_run_summary"]
    monkeypatch.setattr(h.repo, "delete_scan_runs", real)
    assert retention(h).maintain(NOW) == "done"  # same day: the failed purge is resumed
    # The ten latest runs plus run 1, which holds the all-time lowest price (min_amount).
    assert run_ids(h) == [1, *range(1201, 1211)] and orphans(h) == []
    assert h.assembly.database.integrity_ok()


# ---- backups (C-53) ----------------------------------------------------------------------


def test_backup_comes_first_and_matches_the_data(
    h: Harness, monkeypatch: pytest.MonkeyPatch
) -> None:  # FR-S1, AC-S1
    watch_id = h.create_watch()
    old_runs(h, watch_id, range(300, 280, -1))
    path = h.assembly.database.path
    before = counts(path)
    backup = retention_backup_path(path, date(2026, 10, 25))
    seen: list[bool] = []
    real = repo_of(h).delete_scan_runs

    def spy(ids: Sequence[int]) -> tuple[int, int]:
        seen.append(backup.is_file())
        return real(ids)

    monkeypatch.setattr(h.repo, "delete_scan_runs", spy)
    assert retention(h).maintain(NOW) == "done"
    assert seen == [True]
    assert backup.name == "test.retention-20261025.db" and counts(backup) == before
    view = h.services.views.settings_page()["maintenance"]
    assert backup.name in view["last_backup_label"] and "已先建立備份" in view["last_run_summary"]


def test_no_backup_without_candidates_and_once_per_day(h: Harness) -> None:  # AC-S2
    path = h.assembly.database.path
    assert retention(h).maintain(NOW) == "done"
    assert not list(path.parent.glob("*.retention-*.db"))
    watch_id = h.create_watch()
    old_runs(h, watch_id, range(300, 280, -1))
    h.repo.save_state({"state.retention_last_date": "2026-10-24"}, NOW)
    assert retention(h).maintain(NOW) == "done"
    old_runs(h, watch_id, range(300, 290, -1))
    h.repo.save_state({"state.retention_last_date": "2026-10-24"}, NOW)
    assert retention(h).maintain(NOW) == "done"
    assert [p.name for p in path.parent.glob("*.retention-*.db")] == ["test.retention-20261025.db"]


def test_backup_failure_deletes_nothing_and_is_shown(
    h: Harness, monkeypatch: pytest.MonkeyPatch
) -> None:  # AC-S3
    watch_id = h.create_watch()
    old_runs(h, watch_id, range(300, 280, -1))
    before = run_ids(h)

    def no_space(_day: date) -> tuple[Path, bool]:
        raise OSError(28, "No space left on device")

    monkeypatch.setattr(h.assembly.database, "retention_backup", no_space)
    assert retention(h).maintain(NOW) == "backup_failed"
    assert run_ids(h) == before
    summary = h.services.views.settings_page()["maintenance"]["last_run_summary"]
    assert "備份失敗" in summary and "No space left" in summary
    monkeypatch.undo()
    assert retention(h).maintain(NOW) == "done"  # retried (the day was not closed)
    assert len(run_ids(h)) == 10


def test_only_seven_purge_backups_are_kept(h: Harness) -> None:  # FR-S2, AC-S4
    folder = h.assembly.database.path.parent
    for day in range(1, 8):
        (folder / f"test.retention-202610{day:02d}.db").write_bytes(b"")
    keep = [
        folder / "test.pre-v5.db",
        folder / "other.retention-20200101.db",
        folder / "test.retention-2026101.db",
        folder / "test.retention-20261001.db.tmp",
    ]
    for path in keep:
        path.write_bytes(b"")
    watch_id = h.create_watch()
    old_runs(h, watch_id, range(300, 280, -1))
    assert retention(h).maintain(NOW) == "done"
    backups = sorted(p.name for p in folder.glob("test.retention-????????.db"))
    assert backups == [f"test.retention-202610{d:02d}.db" for d in range(2, 8)] + [
        "test.retention-20261025.db"
    ]
    assert all(p.exists() for p in keep)


def test_file_operations_and_deletes_stay_in_storage() -> None:  # C-53
    for path in SRC.rglob("*.py"):
        rel = path.relative_to(SRC).as_posix()
        text = path.read_text(encoding="utf-8")
        if rel != "storage/db.py":
            assert 'execute("VACUUM' not in text and ".unlink(" not in text, rel
            assert "os.replace(" not in text, rel
        if rel != "storage/repository.py":
            assert "DELETE FROM" not in text, rel


# ---- VACUUM (C-54) -------------------------------------------------------------------------


def test_vacuum_runs_weekly_after_the_purge(h: Harness) -> None:  # FR-S6, AC-S8, AC-S9
    watch_id = h.create_watch()
    old_runs(h, watch_id, range(300, 200, -1))
    path = h.assembly.database.path
    assert retention(h).maintain(NOW) == "done"
    after_purge = counts(path)
    state = h.repo.get_state(["state.vacuum_last_at", "state.vacuum_last_result"])
    result = json.loads(state["state.vacuum_last_result"])
    assert result["status"] == "done" and result["before"] >= result["after"] > 0
    assert counts(path) == after_purge and h.assembly.database.integrity_ok()
    label = h.services.views.settings_page()["maintenance"]["last_vacuum_label"]
    assert re.search(r"（\d+(\.\d)? (KB|MB) → \d+(\.\d)? (KB|MB)）", label), label
    for day in range(1, 7):
        retention(h).maintain(NOW + timedelta(days=day))
        assert h.repo.get_state(["state.vacuum_last_at"]) == {
            "state.vacuum_last_at": state["state.vacuum_last_at"]
        }
    retention(h).maintain(NOW + timedelta(days=7))
    assert (
        h.repo.get_state(["state.vacuum_last_at"])["state.vacuum_last_at"]
        != state["state.vacuum_last_at"]
    )


def test_vacuum_switch_off(h: Harness) -> None:  # AC-S9
    h.services.settings.update({"vacuum_enabled": False})
    assert retention(h).maintain(NOW) == "done"
    assert h.repo.get_state(["state.vacuum_last_at", "state.vacuum_last_result"]) == {}
    assert h.services.views.settings_page()["maintenance"]["last_vacuum_label"] == "尚未執行"


def test_vacuum_skipped_when_disk_is_short(
    h: Harness, monkeypatch: pytest.MonkeyPatch
) -> None:  # AC-S10
    monkeypatch.setattr(h.assembly.database, "disk_free_bytes", lambda: 1024)
    assert retention(h).maintain(NOW) == "done"
    result = json.loads(h.repo.get_state(["state.vacuum_last_result"])["state.vacuum_last_result"])
    assert result["status"] == "skipped"
    assert "state.vacuum_last_at" not in h.repo.get_state(["state.vacuum_last_at"])
    label = h.services.views.settings_page()["maintenance"]["last_vacuum_label"]
    assert "磁碟可用空間不足" in label
    assert h.assembly.database.integrity_ok()


# ---- health page, settings, detail page (C-54) -------------------------------------------


def test_maintenance_block_and_stats_cache(h: Harness, monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[int] = []
    real = repo_of(h).table_counts

    def counting() -> list[tuple[str, int]]:
        calls.append(1)
        return real()

    monkeypatch.setattr(h.repo, "table_counts", counting)
    tick = [0.0]
    monkeypatch.setattr(retention(h), "_monotonic", lambda: tick[0])
    view = h.services.views.settings_page()["maintenance"]
    assert [row["table"] for row in view["table_counts"]] == [
        "監看",
        "掃描輪",
        "價格觀測",
        "通知",
        "探索",
    ]
    assert view["last_run_label"] == "尚未執行" and view["last_backup_label"] == "尚未執行"
    assert view["last_vacuum_label"] == "尚未執行" and view["last_run_summary"] is None
    assert view["stats_at_label"] == "2026-10-25 12:00（台北時間）"  # page adds the label
    assert view["db_size_label"].endswith(("KB", "MB"))
    assert (view["retention_days"], view["notification_retention_days"], view["keep_runs"]) == (
        180,
        365,
        10,
    )
    tick[0] = 299.0
    h.services.views.settings_page()
    assert len(calls) == 1  # cached for five minutes
    tick[0] = 301.0
    h.services.views.settings_page()
    assert len(calls) == 2


@pytest.mark.parametrize(
    "key", ["retention_days", "notification_retention_days", "retention_keep_runs"]
)
@pytest.mark.parametrize("bad", [29, 0, -1, "", "abc", None, 3651, 1.5])
def test_retention_settings_bounds(h: Harness, key: str, bad: Any) -> None:  # AC-R2
    if key == "retention_keep_runs" and bad == 29:
        bad = 2
    if key == "retention_keep_runs" and bad == 3651:
        bad = 101
    before = h.services.settings.current()
    response = h.client.post("/api/settings", json={key: bad}, headers=CLIENT_HEADERS)
    assert response.status_code == 422
    assert h.services.settings.current() == before


def test_retention_settings_accept_lower_bounds_and_header(h: Harness) -> None:
    body = {"retention_days": 30, "notification_retention_days": 30, "retention_keep_runs": 3}
    assert h.client.post("/api/settings", json=body).status_code == 403
    response = h.client.post("/api/settings", json=body, headers=CLIENT_HEADERS)
    assert response.status_code == 200
    current = h.services.settings.current()
    assert (current.retention_days, current.notification_retention_days) == (30, 30)
    assert current.retention_keep_runs == 3
    rows = {row["key"]: row for row in h.services.views.settings_page()["settings"]}
    assert rows["retention_days"]["min"] == 30 and rows["retention_days"]["default"] == 180
    assert rows["retention_keep_runs"]["max"] == 100


def test_vacuum_switch_validation(h: Harness) -> None:
    response = h.client.post("/api/settings", json={"vacuum_enabled": "x"}, headers=CLIENT_HEADERS)
    assert response.status_code == 422
    h.repo.save_settings({"vacuum_enabled": "nonsense"}, NOW)
    assert h.services.settings.current().vacuum_enabled is True
    assert h.services.views.settings_page()["vacuum_enabled"] is True


def test_lowering_retention_only_announces_the_next_purge(h: Harness) -> None:  # AC-R10
    watch_id = h.create_watch()
    old_runs(h, watch_id, range(100, 60, -1))
    before = run_ids(h)
    response = h.client.post("/api/settings", json={"retention_days": 60}, headers=CLIENT_HEADERS)
    assert response.json() == {"ok": True, "notice": "下次清除將刪除超過 60 天的資料"}
    assert run_ids(h) == before
    response = h.client.post("/api/settings", json={"retention_days": 90}, headers=CLIENT_HEADERS)
    assert response.json() == {"ok": True}


def test_detail_page_discloses_the_retention_period(h: Harness) -> None:  # AC-R7
    watch_id = h.create_watch()
    h.services.settings.update({"retention_days": 90})
    assert h.services.views.detail_page(watch_id)["retention_note"] == "價格紀錄保留最近 90 天"


def test_last_observation_before_taipei_midnight_is_kept(h: Harness) -> None:  # FR-R6, QA 5
    """Only the "newest before midnight" rule protects run R1: it is past the retention
    period, outside the latest N runs, not among the pair's newest two, not the minimum."""
    h.services.settings.update({"retention_days": 30, "retention_keep_runs": 3})
    watch_id = h.create_watch()
    pair = ("2026-12-10", "2026-12-15")
    r1 = add_run(h, watch_id, NOW - timedelta(days=40), [(*pair, 900_000)])
    add_run(h, watch_id, NOW - timedelta(hours=3), [(*pair, 950_000)])  # after midnight
    add_run(h, watch_id, NOW - timedelta(hours=2), [(*pair, 800_000)])  # after midnight
    for minutes in (90, 60, 30):
        add_run(h, watch_id, NOW - timedelta(minutes=minutes))  # newest runs, no prices
    before = h.services.digest.compose(NOW)
    assert "較前一日 -TWD 1,000" in before  # 8,000 now vs 9,000 before midnight (run R1)
    assert retention(h).maintain(NOW) == "done"
    assert r1 in run_ids(h, watch_id)
    assert h.services.digest.compose(NOW) == before

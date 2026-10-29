"""Data retention: daily purge, backup first, weekly VACUUM (ADR-0002 FD-7 Decisions 7, 8).

``RetentionService.maintain`` is idempotent and runs from scheduler jobs only (a cron
job ``retention_delay_minutes`` after the digest time, an hourly check and a startup
catch-up). It is due once per Asia/Taipei day; while it runs it holds the scan lock, so
no scan or exploration can write at the same time. Deleted: finished scan runs (with
their observations) past ``retention_days`` that are neither among a watch's latest
``retention_keep_runs`` runs nor needed by the current snapshot, previous-run and
previous-day comparisons or the lowest-price baseline; notifications past
``notification_retention_days`` (price alerts with a future item stay, so dedupe keeps
working); scheduler events past ``retention_days``. Watches, settings, alert state,
source health and explorations are never touched here.
"""

from __future__ import annotations

import json
import logging
import threading
import time
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from typing import Any

from flight_deals.domain.messages import (
    notification_retention_lowered_notice,
    retention_lowered_notice,
)
from flight_deals.domain.timeutil import parse_utc_iso, taipei_date, to_utc_iso
from flight_deals.ports import Clock, Redactor
from flight_deals.services.digest import digest_due_at, taipei_midnight
from flight_deals.services.settings import EffectiveSettings, SettingsService
from flight_deals.storage.db import FileSizes
from flight_deals.storage.repository import Repository

log = logging.getLogger(__name__)

LAST_DATE_KEY = "state.retention_last_date"
LAST_RUN_AT_KEY = "state.retention_last_run_at"
LAST_RESULT_KEY = "state.retention_last_result"
LAST_BACKUP_KEY = "state.retention_last_backup"
LAST_BACKUP_AT_KEY = "state.retention_last_backup_at"
VACUUM_AT_KEY = "state.vacuum_last_at"
VACUUM_RESULT_KEY = "state.vacuum_last_result"
STATE_KEYS = (
    LAST_DATE_KEY,
    LAST_RUN_AT_KEY,
    LAST_RESULT_KEY,
    LAST_BACKUP_KEY,
    LAST_BACKUP_AT_KEY,
    VACUUM_AT_KEY,
    VACUUM_RESULT_KEY,
)
ERROR_LIMIT = 300
LAST_MINUTE_OF_DAY = 23 * 60 + 59


@dataclass(frozen=True)
class PurgePlan:
    run_ids: tuple[int, ...]
    notification_ids: tuple[int, ...]
    events: int

    @property
    def total(self) -> int:
        return len(self.run_ids) + len(self.notification_ids) + self.events


@dataclass(frozen=True)
class StoreStats:
    at: datetime
    sizes: FileSizes
    counts: tuple[tuple[str, int], ...]


def retention_notice(before: EffectiveSettings, after: EffectiveSettings) -> str | None:
    """Settings page note after lowering a retention period (FR-R9); nothing is deleted
    until the next daily purge."""
    notes = []
    if after.retention_days < before.retention_days:
        notes.append(retention_lowered_notice(after.retention_days))
    if after.notification_retention_days < before.notification_retention_days:
        notes.append(notification_retention_lowered_notice(after.notification_retention_days))
    return "；".join(notes) or None


def chunks(ids: Sequence[int], size: int) -> list[Sequence[int]]:
    return [ids[i : i + size] for i in range(0, len(ids), size)]


def _load_json(raw: str | None) -> dict[str, Any] | None:
    if not raw:
        return None
    try:
        value = json.loads(raw)
    except ValueError:
        return None
    return value if isinstance(value, dict) else None


class RetentionService:
    def __init__(
        self,
        repo: Repository,
        settings: SettingsService,
        *,
        scan_lock: threading.Lock,
        clock: Clock,
        redactor: Redactor,
        backups_keep: int = 7,
        delay_minutes: int = 30,
        batch_size: int = 500,
        vacuum_interval_days: int = 7,
        stats_cache_seconds: int = 300,
        monotonic: Callable[[], float] = time.monotonic,
    ) -> None:
        self._repo = repo
        self._db = repo.db
        self._settings = settings
        self._scan_lock = scan_lock
        self._clock = clock
        self._redact = redactor
        self._backups_keep = backups_keep
        self._delay = timedelta(minutes=delay_minutes)
        self._batch = max(1, min(batch_size, 500))
        self._vacuum_interval = timedelta(days=vacuum_interval_days)
        self._stats_ttl = stats_cache_seconds
        self._monotonic = monotonic
        self._stats: tuple[float, StoreStats] | None = None
        self._stats_lock = threading.Lock()

    @property
    def stats_cache_minutes(self) -> int:
        return max(self._stats_ttl // 60, 1)

    # ---- timing --------------------------------------------------------------------

    def daily_time(self, settings: EffectiveSettings | None = None) -> tuple[int, int]:
        """(hour, minute) Asia/Taipei of the daily purge, clamped to the same day."""
        settings = settings or self._settings.current()
        hour, minute = settings.digest_hour_minute
        total = min(hour * 60 + minute + int(self._delay.total_seconds() // 60), LAST_MINUTE_OF_DAY)
        return total // 60, total % 60

    def due_at(self, now: datetime, settings: EffectiveSettings | None = None) -> datetime:
        settings = settings or self._settings.current()
        hour, minute = self.daily_time(settings)
        base = digest_due_at(now, settings)
        return base.replace(hour=hour, minute=minute)

    def is_due(self, now: datetime) -> bool:
        if now < self.due_at(now):
            return False
        last = self._repo.get_state([LAST_DATE_KEY]).get(LAST_DATE_KEY)
        return last != taipei_date(now).isoformat()

    # ---- the daily job -------------------------------------------------------------

    def maintain(self, now: datetime | None = None) -> str:
        """Purge once per day when due; returns what happened (for logs and tests)."""
        now = now or self._clock()
        if not self.is_due(now):
            return "not_due"
        if not self._scan_lock.acquire(blocking=False):
            return "deferred"
        try:
            active = self._repo.active_exploration()
            if active is not None and active.status == "running":
                return "deferred"
            return self._purge(now)
        finally:
            self._scan_lock.release()

    def plan(self, now: datetime, settings: EffectiveSettings | None = None) -> PurgePlan:
        settings = settings or self._settings.current()
        today = taipei_date(now)
        cutoff = now - timedelta(days=settings.retention_days)
        keep = self._repo.retention_keep_recent_runs(settings.retention_keep_runs)
        keep |= self._repo.retention_snapshot_runs(today=today, midnight=taipei_midnight(now))
        runs = tuple(i for i in self._repo.retention_run_candidates(cutoff) if i not in keep)
        notification_cutoff = now - timedelta(days=settings.notification_retention_days)
        notifications = tuple(
            self._repo.retention_notification_candidates(notification_cutoff, today)
        )
        return PurgePlan(runs, notifications, self._repo.count_events_before(cutoff))

    def _purge(self, now: datetime) -> str:
        settings = self._settings.current()
        started = self._monotonic()
        today = taipei_date(now)
        plan = self.plan(now, settings)
        created_backup = False
        if plan.total > 0:
            try:
                path, created_backup = self._db.retention_backup(today)
                if created_backup:
                    self._repo.save_state(
                        {LAST_BACKUP_KEY: path.name, LAST_BACKUP_AT_KEY: to_utc_iso(now)}, now
                    )
                self._db.prune_retention_backups(self._backups_keep)
            except Exception as exc:
                reason = self._reason(exc)
                log.warning("retention backup failed, nothing deleted: %s", reason)
                self._record(now, {"status": "backup_failed", "error": reason})
                return "backup_failed"
        counts = {"runs": 0, "observations": 0, "notifications": 0, "other": 0}
        try:
            for batch in chunks(plan.run_ids, self._batch):
                runs, observations = self._repo.delete_scan_runs(batch)
                counts["runs"] += runs
                counts["observations"] += observations
            for batch in chunks(plan.notification_ids, self._batch):
                counts["notifications"] += self._repo.delete_notifications(batch)
            cutoff = now - timedelta(days=settings.retention_days)
            while True:
                removed = self._repo.delete_events_before(cutoff, self._batch)
                counts["other"] += removed
                if removed < self._batch:
                    break
        except Exception as exc:
            reason = self._reason(exc)
            log.warning("retention purge stopped part way (resumable): %s", reason)
            self._record(now, {"status": "failed", "error": reason, **counts})
            return "failed"
        duration_ms = int((self._monotonic() - started) * 1000)
        result = {
            "status": "done",
            **counts,
            "backup_created": created_backup,
            "duration_ms": duration_ms,
        }
        self._record(now, result, finished_day=today)
        self._repo.insert_event(
            now,
            "retention",
            "runs={runs} observations={observations} notifications={notifications}"
            " other={other}".format(**counts),
        )
        log.info("retention purge done: %s", counts)
        self._vacuum_if_due(now, settings)
        return "done"

    def _record(
        self, now: datetime, result: dict[str, Any], *, finished_day: date | None = None
    ) -> None:
        values = {LAST_RUN_AT_KEY: to_utc_iso(now), LAST_RESULT_KEY: json.dumps(result)}
        if finished_day is not None:
            # Only a complete purge closes the day; a failed one is retried (hourly check).
            values[LAST_DATE_KEY] = finished_day.isoformat()
        self._repo.save_state(values, now)

    def _reason(self, exc: BaseException) -> str:
        return self._redact(f"{type(exc).__name__}: {exc}")[:ERROR_LIMIT]

    # ---- VACUUM (Decision 8) -------------------------------------------------------

    def _vacuum_if_due(self, now: datetime, settings: EffectiveSettings) -> str:
        if not settings.vacuum_enabled:
            return "disabled"
        last_raw = self._repo.get_state([VACUUM_AT_KEY]).get(VACUUM_AT_KEY)
        if last_raw and now - parse_utc_iso(last_raw) < self._vacuum_interval:
            return "not_due"
        sizes = self._db.file_sizes()
        free = self._db.disk_free_bytes()
        need = 2 * sizes.total_bytes
        if free < need:
            self._repo.save_state(
                {
                    VACUUM_RESULT_KEY: json.dumps(
                        {"status": "skipped", "at": to_utc_iso(now), "need": need, "free": free}
                    )
                },
                now,
            )
            log.warning("VACUUM skipped: %d bytes free, about %d needed", free, need)
            return "skipped"
        started = self._monotonic()
        try:
            before, after = self._db.vacuum()
        except Exception as exc:
            reason = self._reason(exc)
            self._repo.save_state(
                {
                    VACUUM_RESULT_KEY: json.dumps(
                        {"status": "failed", "at": to_utc_iso(now), "error": reason}
                    )
                },
                now,
            )
            log.warning("VACUUM failed: %s", reason)
            return "failed"
        result = {
            "status": "done",
            "at": to_utc_iso(now),
            "before": before.total_bytes,
            "after": after.total_bytes,
            "duration_ms": int((self._monotonic() - started) * 1000),
        }
        self._repo.save_state(
            {VACUUM_AT_KEY: to_utc_iso(now), VACUUM_RESULT_KEY: json.dumps(result)}, now
        )
        self._repo.insert_event(now, "vacuum", f"bytes {before.total_bytes} -> {after.total_bytes}")
        return "done"

    # ---- health page ---------------------------------------------------------------

    def stats(self, now: datetime | None = None) -> StoreStats:
        """Sizes and table counts, cached for ``stats_cache_seconds`` (FR-H6)."""
        with self._stats_lock:
            cached = self._stats
            if cached is not None and self._monotonic() - cached[0] < self._stats_ttl:
                return cached[1]
            stats = StoreStats(
                at=now or self._clock(),
                sizes=self._db.file_sizes(),
                counts=tuple(self._repo.table_counts()),
            )
            self._stats = (self._monotonic(), stats)
            return stats

    def last_results(self) -> dict[str, Any]:
        state = self._repo.get_state(list(STATE_KEYS))
        return {
            "run_at": parse_utc_iso(state[LAST_RUN_AT_KEY]) if LAST_RUN_AT_KEY in state else None,
            "result": _load_json(state.get(LAST_RESULT_KEY)),
            "backup": state.get(LAST_BACKUP_KEY),
            "backup_at": (
                parse_utc_iso(state[LAST_BACKUP_AT_KEY]) if LAST_BACKUP_AT_KEY in state else None
            ),
            "vacuum_at": parse_utc_iso(state[VACUUM_AT_KEY]) if VACUUM_AT_KEY in state else None,
            "vacuum": _load_json(state.get(VACUUM_RESULT_KEY)),
        }


__all__ = ["PurgePlan", "RetentionService", "StoreStats", "retention_notice"]

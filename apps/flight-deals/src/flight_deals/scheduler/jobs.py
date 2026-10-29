"""APScheduler 3.x wiring (in-memory jobstore; the ``watch`` table is the source of truth).

One worker thread runs every scan serially; jobs use ``coalesce=True`` and
``max_instances=1``. Startup only catches up overdue watches, staggered. Starting
requires a held cross-process ``SchedulerLock`` (one scheduler per database).

Daily digest jobs (ADR-0002 FD-4 Decision 1) only call ``DigestService.send_if_due``,
which is idempotent: a cron job at the configured Asia/Taipei time, a one-off catch-up
queued after the startup scans, an hourly check (sleep / wake), and a one-off check after
the digest settings change. They run on the same single worker as the scans.

Explorations (ADR-0002 FD-6 Decision 3) run as one-off ``explore:<id>`` date jobs on
that same worker, so scans and "scan now" requests due meanwhile wait in the executor
queue and run afterwards (deferred, never dropped). Explorations cut off by a stop are
marked interrupted at start, before any job is queued; an hourly job purges old ones.

Telegram commands (ADR-0002 FD-7 Decisions 4, 5) add one-off ``cmdscan:<id>`` jobs (a
manual scan followed by the command's result reply) and ``manual-digest:<update_id>``
jobs; both run on the same single worker. The poller itself is a separate thread owned
by ``services.commands`` and is never a job. The daily retention purge (Decision 7) is
called like the digest: a cron job ``maintenance``, an hourly ``maintenance-check`` and a
startup ``maintenance-catchup`` queued after the digest catch-up; it is idempotent.
"""

from __future__ import annotations

import logging
import threading
from datetime import datetime, timedelta
from typing import Any
from zoneinfo import ZoneInfo

from apscheduler.events import EVENT_JOB_ERROR, EVENT_JOB_MAX_INSTANCES
from apscheduler.executors.pool import ThreadPoolExecutor
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger

from flight_deals.scheduler.lock import SchedulerLock
from flight_deals.services import DIGEST_ZONE, Clock, Services, Watch
from flight_deals.services.scan import ScanOutcome
from flight_deals.services.settings import EffectiveSettings

log = logging.getLogger(__name__)

UTC_ZONE = ZoneInfo("UTC")
WATCH_PREFIX = "watch:"
STARTUP_PREFIX = "startup:"
MANUAL_PREFIX = "manual:"
SWEEP_JOB_ID = "expire-sweep"
DIGEST_JOB_ID = "daily-digest"
DIGEST_CATCHUP_JOB_ID = "digest-catchup"
DIGEST_CHECK_JOB_ID = "digest-check"
DIGEST_RECHECK_JOB_ID = "digest-recheck"
EXPLORE_PREFIX = "explore:"
PURGE_JOB_ID = "exploration-purge"
CMDSCAN_PREFIX = "cmdscan:"
MANUAL_DIGEST_PREFIX = "manual-digest:"
MAINTENANCE_JOB_ID = "maintenance"
MAINTENANCE_CHECK_JOB_ID = "maintenance-check"
MAINTENANCE_CATCHUP_JOB_ID = "maintenance-catchup"
MAINTENANCE_JOB_IDS = frozenset(
    {MAINTENANCE_JOB_ID, MAINTENANCE_CHECK_JOB_ID, MAINTENANCE_CATCHUP_JOB_ID}
)
DIGEST_JOB_IDS = frozenset(
    {DIGEST_JOB_ID, DIGEST_CATCHUP_JOB_ID, DIGEST_CHECK_JOB_ID, DIGEST_RECHECK_JOB_ID}
)
# Jobs that are not watch scans; the health page's "next scan" ignores them.
NON_SCAN_JOB_IDS = DIGEST_JOB_IDS | MAINTENANCE_JOB_IDS | {SWEEP_JOB_ID, PURGE_JOB_ID}
JOB_DEFAULTS: dict[str, Any] = {"coalesce": True, "max_instances": 1, "misfire_grace_time": 3600}
WORKER_THREADS = 1

_guard = threading.Lock()
_active: ScanScheduler | None = None


class SchedulerAlreadyRunningError(RuntimeError):
    pass


class SchedulerLockNotHeldError(RuntimeError):
    """``start`` was called without holding the database's scheduler lock."""


def build_background_scheduler() -> BackgroundScheduler:
    return BackgroundScheduler(
        executors={"default": ThreadPoolExecutor(WORKER_THREADS)},
        job_defaults=dict(JOB_DEFAULTS),
        timezone=UTC_ZONE,
    )


def _job_time(job: Any) -> datetime | None:
    """Next run of a job; pending jobs (scheduler not started yet) have no attribute."""
    when = getattr(job, "next_run_time", None)
    if when is None and not hasattr(job, "next_run_time"):
        when = getattr(job.trigger, "run_date", None)
    return when if isinstance(when, datetime) else None


class ScanScheduler:
    def __init__(
        self,
        services: Services,
        *,
        startup_stagger_seconds: int,
        new_watch_delay_seconds: int,
        clock: Clock,
    ) -> None:
        self._services = services
        self._stagger = timedelta(seconds=startup_stagger_seconds)
        self._new_delay = timedelta(seconds=new_watch_delay_seconds)
        self._clock = clock
        self._scheduler = build_background_scheduler()
        self._started = False

    @property
    def scheduler(self) -> BackgroundScheduler:
        return self._scheduler

    @property
    def running(self) -> bool:
        return self._started and bool(self._scheduler.running)

    # ---- lifecycle -----------------------------------------------------------

    def start(self, lock: SchedulerLock) -> None:
        """Start once per process, only while holding the database's scheduler lock.

        A second start in the same process raises instead of double-scheduling; other
        processes are kept out by ``lock`` (the caller acquires and releases it).
        """
        global _active
        if not lock.held:
            raise SchedulerLockNotHeldError("scheduler lock must be held before starting")
        with _guard:
            if _active is not None:
                raise SchedulerAlreadyRunningError("a scan scheduler is already running")
            _active = self
        try:
            # Before any job is queued: a stop or crash never resumes an exploration.
            self._services.exploration.recover_interrupted()
            self._scheduler.add_listener(self._on_event, EVENT_JOB_MAX_INSTANCES | EVENT_JOB_ERROR)
            self._scheduler.start()
            self._started = True
            self._services.scan.expire_sweep()
            self.sync_all(startup=True)
            self._scheduler.add_job(
                self._services.scan.expire_sweep,
                trigger=IntervalTrigger(hours=1, timezone=UTC_ZONE),
                id=SWEEP_JOB_ID,
                replace_existing=True,
            )
            self._scheduler.add_job(
                self._services.exploration.purge_expired,
                trigger=IntervalTrigger(hours=1, timezone=UTC_ZONE),
                id=PURGE_JOB_ID,
                replace_existing=True,
            )
            self.schedule_digest(startup=True)
            self.schedule_maintenance(startup=True)
        except BaseException:
            self.shutdown()
            raise

    def shutdown(self) -> None:
        global _active
        if self._scheduler.running:
            self._scheduler.shutdown(wait=False)
        self._started = False
        with _guard:
            if _active is self:
                _active = None

    # ---- scheduling ----------------------------------------------------------

    def _settings(self) -> EffectiveSettings:
        return self._services.settings.current()

    def _remove_watch_jobs(self, watch_id: int, *, include_manual: bool = False) -> None:
        prefixes = [WATCH_PREFIX, STARTUP_PREFIX]
        if include_manual:
            prefixes += [MANUAL_PREFIX, CMDSCAN_PREFIX]
        for prefix in prefixes:
            job = self._scheduler.get_job(f"{prefix}{watch_id}")
            if job is not None:
                job.remove()

    def _schedule(self, watch: Watch, now: datetime, startup_slot: int | None) -> None:
        interval = timedelta(minutes=self._settings().scan_interval_minutes)
        due = (watch.last_scanned_at + interval) if watch.last_scanned_at else None
        overdue = due is None or due <= now
        if overdue and startup_slot is not None:
            first = now + self._stagger * (startup_slot + 1)
            self._scheduler.add_job(
                self._run,
                trigger="date",
                run_date=first,
                args=[watch.id, "startup"],
                id=f"{STARTUP_PREFIX}{watch.id}",
                replace_existing=True,
            )
            next_run = first + interval
        elif overdue:
            next_run = now + self._new_delay
        else:
            assert due is not None
            next_run = due
        self._scheduler.add_job(
            self._run,
            trigger=IntervalTrigger(minutes=int(interval.total_seconds() // 60), timezone=UTC_ZONE),
            args=[watch.id, "scheduled"],
            id=f"{WATCH_PREFIX}{watch.id}",
            replace_existing=True,
            next_run_time=next_run,
        )

    def sync_all(self, *, startup: bool = False) -> None:
        """Rebuild every watch job from the ``watch`` table."""
        now = self._clock()
        for job in self._scheduler.get_jobs():
            if job.id.startswith(WATCH_PREFIX) or (startup and job.id.startswith(STARTUP_PREFIX)):
                job.remove()
        slot = 0
        for watch in self._services.scan.schedulable_watches():
            interval = timedelta(minutes=self._settings().scan_interval_minutes)
            overdue = watch.last_scanned_at is None or watch.last_scanned_at + interval <= now
            self._schedule(watch, now, slot if startup else None)
            if startup and overdue:
                slot += 1

    def on_watch_changed(self, watch_id: int) -> None:
        self._remove_watch_jobs(watch_id)
        watch = self._services.watches.get(watch_id)
        if watch is None or watch.id not in {
            w.id for w in self._services.scan.schedulable_watches()
        }:
            return
        self._schedule(watch, self._clock(), None)

    def on_watch_deleted(self, watch_id: int) -> None:
        self._remove_watch_jobs(watch_id, include_manual=True)
        if self._services.commands is not None:
            self._services.commands.forget_scan(watch_id)

    def on_settings_changed(self, before: EffectiveSettings, after: EffectiveSettings) -> None:
        """Runs on a web request thread: only (re)schedules jobs, never sends (C-32)."""
        if before.scan_interval_minutes != after.scan_interval_minutes:
            self.sync_all()
        if (before.digest_enabled, before.digest_time) != (after.digest_enabled, after.digest_time):
            self.schedule_digest(startup=False)
        if before.digest_time != after.digest_time:
            self.schedule_maintenance(startup=False)

    # ---- daily digest --------------------------------------------------------

    def schedule_digest(self, *, startup: bool) -> None:
        """(Re)build the digest cron job and queue one idempotent catch-up check."""
        settings = self._settings()
        hour, minute = settings.digest_hour_minute
        self._scheduler.add_job(
            self._digest,
            trigger=CronTrigger(hour=hour, minute=minute, timezone=DIGEST_ZONE),
            id=DIGEST_JOB_ID,
            replace_existing=True,
        )
        now = self._clock()
        if startup:
            self._scheduler.add_job(
                self._digest,
                trigger=IntervalTrigger(hours=1, timezone=UTC_ZONE),
                id=DIGEST_CHECK_JOB_ID,
                replace_existing=True,
            )
            # Queued after the startup scans so the catch-up digest sees fresh prices.
            startup_runs = [
                when
                for job in self._scheduler.get_jobs()
                if job.id.startswith(STARTUP_PREFIX) and (when := _job_time(job)) is not None
            ]
            run_at = max(startup_runs, default=now) + timedelta(seconds=1)
            job_id = DIGEST_CATCHUP_JOB_ID
        else:
            run_at = now
            job_id = DIGEST_RECHECK_JOB_ID
        self._scheduler.add_job(
            self._digest, trigger="date", run_date=run_at, id=job_id, replace_existing=True
        )

    # ---- retention purge (FD-7 Decision 7) ------------------------------------

    def schedule_maintenance(self, *, startup: bool) -> None:
        """(Re)build the daily purge cron job; at startup also the hourly check and one
        catch-up queued right after the digest catch-up."""
        retention = self._services.retention
        if retention is None:
            return
        hour, minute = retention.daily_time(self._settings())
        self._scheduler.add_job(
            self._maintenance,
            trigger=CronTrigger(hour=hour, minute=minute, timezone=DIGEST_ZONE),
            id=MAINTENANCE_JOB_ID,
            replace_existing=True,
        )
        if not startup:
            return
        self._scheduler.add_job(
            self._maintenance,
            trigger=IntervalTrigger(hours=1, timezone=UTC_ZONE),
            id=MAINTENANCE_CHECK_JOB_ID,
            replace_existing=True,
        )
        catchup = self._scheduler.get_job(DIGEST_CATCHUP_JOB_ID)
        after = _job_time(catchup) if catchup is not None else None
        run_at = (after or self._clock()) + timedelta(seconds=1)
        self._scheduler.add_job(
            self._maintenance,
            trigger="date",
            run_date=run_at,
            id=MAINTENANCE_CATCHUP_JOB_ID,
            replace_existing=True,
        )

    def trigger_now(self, watch_id: int) -> None:
        self._scheduler.add_job(
            self._run,
            trigger="date",
            run_date=self._clock(),
            args=[watch_id, "manual"],
            id=f"{MANUAL_PREFIX}{watch_id}",
            replace_existing=True,
        )

    def trigger_command_scan(self, watch_id: int) -> None:
        """``/scan``: one manual scan, then its result reply (FD-7 Decision 4)."""
        self._scheduler.add_job(
            self._command_scan,
            trigger="date",
            run_date=self._clock(),
            args=[watch_id],
            id=f"{CMDSCAN_PREFIX}{watch_id}",
            replace_existing=True,
        )

    def scan_pending(self, watch_id: int) -> bool:
        """A "scan now" (web) or ``/scan`` job of this watch is still queued."""
        return any(
            self._scheduler.get_job(f"{prefix}{watch_id}") is not None
            for prefix in (MANUAL_PREFIX, CMDSCAN_PREFIX)
        )

    def schedule_manual_digest(self, update_id: int, key: str) -> None:
        """``/digest``: one digest under ``key`` on the worker (FD-7 Decision 5)."""
        self._scheduler.add_job(
            self._manual_digest,
            trigger="date",
            run_date=self._clock(),
            args=[key],
            id=f"{MANUAL_DIGEST_PREFIX}{update_id}",
            replace_existing=True,
        )

    def schedule_exploration(self, exploration_id: int) -> None:
        """Queue one exploration now; it never misfires, whatever the delay."""
        self._scheduler.add_job(
            self._explore,
            trigger="date",
            run_date=self._clock(),
            args=[exploration_id],
            id=f"{EXPLORE_PREFIX}{exploration_id}",
            replace_existing=True,
            misfire_grace_time=None,
            max_instances=1,
        )

    def next_run_time(self) -> datetime | None:
        times = [
            when
            for job in self._scheduler.get_jobs()
            if job.id not in NON_SCAN_JOB_IDS
            and not job.id.startswith((EXPLORE_PREFIX, MANUAL_DIGEST_PREFIX))
            and (when := _job_time(job)) is not None
        ]
        return min(times) if times else None

    # ---- execution -----------------------------------------------------------

    def _run(self, watch_id: int, trigger: str) -> None:
        self._services.scan.scan_watch(watch_id, trigger)

    def _command_scan(self, watch_id: int) -> None:
        # Stored as a manual scan: scan_run.trigger keeps its three values (Decision 4).
        # Even if the scan raises, the pending /scan is cleared and answered (finally).
        outcome = ScanOutcome(watch_id, "crashed")
        try:
            outcome = self._services.scan.scan_watch(watch_id, "manual")
        finally:
            if self._services.commands is not None:
                self._services.commands.on_scan_finished(watch_id, outcome)

    def _manual_digest(self, key: str) -> None:
        outcome = self._services.digest.send_manual(self._clock(), key)
        log.info("manual digest: %s", outcome)

    def _maintenance(self) -> None:
        retention = self._services.retention
        if retention is None:
            return
        outcome = retention.maintain(self._clock())
        log.debug("maintenance check: %s", outcome)

    def _explore(self, exploration_id: int) -> None:
        outcome = self._services.exploration.run(exploration_id)
        log.info("exploration %s: %s", exploration_id, outcome)

    def _digest(self) -> None:
        outcome = self._services.digest.send_if_due(self._clock())
        log.debug("digest check: %s", outcome)

    def _on_event(self, event: Any) -> None:
        if event.code == EVENT_JOB_MAX_INSTANCES:
            self._services.health.record_scheduler_event(
                "scan_skipped", f"{event.job_id}: 上一輪掃描尚未結束，本次略過"
            )
            log.info("job %s skipped: previous run still in progress", event.job_id)
        elif event.code == EVENT_JOB_ERROR:
            self._services.health.record_scheduler_event(
                "job_error", f"{event.job_id}: {type(event.exception).__name__}"
            )

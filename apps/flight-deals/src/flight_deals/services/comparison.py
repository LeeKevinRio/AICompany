"""Multi-destination comparison: one date pair queried once per destination
(ADR-0002 FD-9 Decision 3).

``create`` only validates, checks reuse / busy / quota and writes the comparison with
every destination ``pending``; the queries run later in the scheduler's single worker
thread through the ``compare:<id>`` job (``run``), sharing the scan lock, the sources
(cache and throttle live on them), the hourly query limit and the circuit breaker with
scans and explorations. ``create`` shares one lock with ``ExplorationService.create`` so
at most one comparison or exploration is ever queued or running. Comparisons never
write price observations, alert state or price alerts.
"""

from __future__ import annotations

import logging
import threading
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from datetime import timedelta
from typing import Literal

from flight_deals.domain.messages import (
    COMPARISON_BREAKER_OPEN,
    COMPARISON_HOURLY_LIMIT,
    COMPARISON_LOCK_TIMEOUT,
    COMPARISON_RESTARTED,
    COMPARISON_SCHEDULER_OFF,
    comparison_busy_message,
    comparison_crashed,
    comparison_quota_message,
    comparison_skipped_note,
)
from flight_deals.domain.models import search_for
from flight_deals.domain.timeutil import taipei_date
from flight_deals.domain.validation import MAX_DESTINATIONS, validate_comparison
from flight_deals.ports import Clock, FlightPriceSource, Redactor
from flight_deals.services.exploration import QuotaView, cell_update
from flight_deals.services.health import HealthService
from flight_deals.services.notifications import NotificationService
from flight_deals.services.settings import SettingsService
from flight_deals.services.source_query import ERROR_SUMMARY_LIMIT, SourceQuery
from flight_deals.storage.repository import ComparisonRecord, Repository

log = logging.getLogger(__name__)

LOCK_TIMEOUT_SECONDS = 900
ComparisonCreateStatus = Literal[
    "created", "reused", "joined", "invalid", "quota", "busy", "scheduler_off"
]


def _never(_comparison_id: int) -> None:
    return None


def _not_running() -> bool:
    return False


def comparison_url(comparison_id: int) -> str:
    return f"/comparisons/{comparison_id}"


def exploration_url(exploration_id: int) -> str:
    return f"/explorations/{exploration_id}"


@dataclass
class ComparisonHooks:
    """Set by ``app.py`` so services never import the scheduler."""

    schedule: Callable[[int], None] = _never
    scheduler_running: Callable[[], bool] = _not_running


@dataclass(frozen=True)
class ComparisonCreateResult:
    status: ComparisonCreateStatus
    comparison_id: int | None = None
    errors: dict[str, str] = field(default_factory=dict)
    hourly_left: int | None = None
    needed: int | None = None
    message: str | None = None
    progress_url: str | None = None

    @property
    def ok(self) -> bool:
        return self.status in ("created", "reused", "joined")


class ComparisonService:
    def __init__(
        self,
        repo: Repository,
        sources: list[FlightPriceSource],
        health: HealthService,
        notifications: NotificationService,
        settings: SettingsService,
        *,
        scan_lock: threading.Lock,
        create_lock: threading.Lock,
        reuse_hours: int,
        retention_days: int,
        clock: Clock,
        redactor: Redactor,
    ) -> None:
        self._repo = repo
        self._query = SourceQuery(sources, health, clock=clock, redactor=redactor)
        self._health = health
        self._notifications = notifications
        self._settings = settings
        self._scan_lock = scan_lock
        # Shared with ExplorationService.create: one comparison or exploration at a time.
        self._create_lock = create_lock
        self._reuse = timedelta(hours=reuse_hours)
        self._retention = timedelta(days=retention_days)
        self._clock = clock
        self._redact = redactor
        self.hooks = ComparisonHooks()

    @property
    def sources(self) -> list[FlightPriceSource]:
        return self._query.sources

    # ---- web side ------------------------------------------------------------

    def quota(self) -> QuotaView:
        settings = self._settings.current()
        used = self._repo.queries_used_since(self._clock() - timedelta(hours=1))
        return QuotaView(
            hourly_left=max(settings.global_hourly_query_limit - used, 0),
            reserve=settings.exploration_reserve_for_scans,
            max_cells=MAX_DESTINATIONS,
        )

    def create(self, raw: Mapping[str, object]) -> ComparisonCreateResult:
        """Validate, then reuse / join / refuse / queue. Never sends a query (C-63)."""
        now = self._clock()
        outcome = validate_comparison(raw, taipei_date(now))
        if outcome.spec is None:
            return ComparisonCreateResult("invalid", errors=outcome.errors)
        spec = outcome.spec
        key = spec.condition_key()
        needed = len(spec.destinations)
        with self._create_lock:
            reused = self._repo.reusable_comparison(key, now - self._reuse)
            if reused is not None:
                return ComparisonCreateResult("reused", reused.id)
            active = self._repo.active_comparison()
            if active is not None:
                if active.condition_key == key:
                    return ComparisonCreateResult("joined", active.id)
                url = comparison_url(active.id)
                return ComparisonCreateResult(
                    "busy", active.id, message=comparison_busy_message(url), progress_url=url
                )
            exploring = self._repo.active_exploration()
            if exploring is not None:
                url = exploration_url(exploring.id)
                return ComparisonCreateResult(
                    "busy", message=comparison_busy_message(url), progress_url=url
                )
            if not self.hooks.scheduler_running():
                return ComparisonCreateResult("scheduler_off", message=COMPARISON_SCHEDULER_OFF)
            quota = self.quota()
            if quota.hourly_left - quota.reserve < needed:
                return ComparisonCreateResult(
                    "quota",
                    hourly_left=quota.hourly_left,
                    needed=needed,
                    message=comparison_quota_message(quota.hourly_left, needed, quota.reserve),
                )
            comparison_id = self._repo.insert_comparison(spec, now)
        try:
            self.hooks.schedule(comparison_id)
        except Exception:
            log.exception("comparison %s could not be scheduled", comparison_id)
            self._repo.finish_comparison(
                comparison_id,
                status="failed",
                finished_at=self._clock(),
                skip_reason="interrupted",
                error_summary=COMPARISON_SCHEDULER_OFF,
            )
            return ComparisonCreateResult("scheduler_off", message=COMPARISON_SCHEDULER_OFF)
        return ComparisonCreateResult("created", comparison_id)

    def status(self, comparison_id: int) -> dict[str, object] | None:
        """Progress for the poller: a fixed four-field whitelist (C-64)."""
        record = self._repo.get_comparison(comparison_id)
        if record is None:
            return None
        return {
            "comparison_id": record.id,
            "status": record.status,
            "total": record.total,
            "done": record.done,
        }

    # ---- worker side -----------------------------------------------------------

    def run(self, comparison_id: int) -> str:
        """Body of the ``compare:<id>`` job; runs on the scheduler's single worker."""
        if not self._scan_lock.acquire(timeout=LOCK_TIMEOUT_SECONDS):
            self._fail(comparison_id, COMPARISON_LOCK_TIMEOUT)
            return "failed"
        try:
            if not self._repo.start_comparison(comparison_id, self._clock()):
                return "not_queued"
            return self._run(comparison_id)
        except Exception as exc:
            log.exception("comparison %s crashed", comparison_id)
            self._fail(comparison_id, comparison_crashed(f"{type(exc).__name__}: {exc}"))
            return "failed"
        except BaseException as exc:
            # KeyboardInterrupt / SystemExit: never leave the comparison "running".
            self._fail(comparison_id, comparison_crashed(type(exc).__name__))
            raise
        finally:
            self._scan_lock.release()

    def _run(self, comparison_id: int) -> str:
        record = self._repo.get_comparison(comparison_id)
        assert record is not None
        spec = record.spec
        opened: list[tuple[str, str | None]] = []
        skip_reason: str | None = None
        remaining = 0
        try:
            cells = self._repo.comparison_cells(comparison_id)
            pending = [c for c in cells if c.status == "pending"]
            for index, cell in enumerate(pending):
                if self._hourly_left() <= 0:
                    skip_reason = "global_hourly_limit"
                elif not any(self._health.allow(s.name) for s in self._query.sources):
                    skip_reason = "breaker_open"
                if skip_reason is not None:
                    remaining = len(pending) - index
                    break
                query = self._query.query(
                    search_for(spec.target(cell.destination), spec.pair, spec.currency),
                    spec.currency,
                )
                opened.extend(query.opened)
                update = cell_update(query, spec.currency, self._redact, self._clock())
                self._repo.record_comparison_cell(comparison_id, cell.position, update)
                if update.status == "skipped":
                    # Every source's breaker opened between the check and the query.
                    skip_reason = update.reason or "breaker_open"
                    remaining = len(pending) - index - 1
                    break
            summary = None
            if skip_reason is not None:
                text = (
                    COMPARISON_HOURLY_LIMIT
                    if skip_reason == "global_hourly_limit"
                    else COMPARISON_BREAKER_OPEN
                )
                summary = comparison_skipped_note(text, remaining) if remaining else text
            self._repo.finish_comparison(
                comparison_id,
                status="failed" if skip_reason else "done",
                finished_at=self._clock(),
                skip_reason=skip_reason or "interrupted",
                error_summary=summary,
            )
        finally:
            # A breaker newly opened by a comparison query alerts like a scan's (D-2.3).
            for source, error in opened:
                self._notifications.send_ops_failure(source, error)
        return "failed" if skip_reason else "done"

    def _hourly_left(self) -> int:
        limit = self._settings.current().global_hourly_query_limit
        return limit - self._repo.queries_used_since(self._clock() - timedelta(hours=1))

    def _fail(self, comparison_id: int, message: str) -> None:
        try:
            self._repo.finish_comparison(
                comparison_id,
                status="failed",
                finished_at=self._clock(),
                skip_reason="interrupted",
                error_summary=self._redact(message)[:ERROR_SUMMARY_LIMIT],
            )
        except Exception:
            log.exception("could not mark comparison %s as failed", comparison_id)

    def recover_interrupted(self) -> list[int]:
        """At scheduler start: comparisons cut off by a stop or crash become failed;
        they are never resumed or re-queried (FR-R8)."""
        ids = self._repo.interrupt_active_comparisons(self._clock(), COMPARISON_RESTARTED)
        if ids:
            log.info("comparisons interrupted by a restart: %s", ids)
        return ids

    def purge_expired(self) -> int:
        """Hourly: drop comparisons created more than the retention period ago."""
        removed = self._repo.delete_comparisons_created_before(self._clock() - self._retention)
        if removed:
            log.info("purged %d expired comparison(s)", removed)
        return removed

    def get(self, comparison_id: int) -> ComparisonRecord | None:
        return self._repo.get_comparison(comparison_id)

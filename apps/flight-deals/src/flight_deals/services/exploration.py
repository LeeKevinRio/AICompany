"""Exploration mode: one query per departure day of a month (ADR-0002 FD-6 Decision 3).

``create`` only validates, checks reuse / busy / quota and writes the exploration with
every cell ``pending``; the queries run later in the scheduler's single worker thread
through the ``explore:<id>`` job (``run``), sharing the scan lock, the sources (cache
and throttle live on them), the hourly query limit and the circuit breaker with the
scans. Explorations never write price observations, alert state or price alerts.
"""

from __future__ import annotations

import logging
import threading
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Literal

from flight_deals.domain.dates import month_pairs
from flight_deals.domain.messages import (
    EXPLORATION_BREAKER_OPEN,
    EXPLORATION_BUSY,
    EXPLORATION_HOURLY_LIMIT,
    EXPLORATION_NO_DATES,
    EXPLORATION_RESTARTED,
    EXPLORATION_SCHEDULER_OFF,
    comparison_busy_message,
    exploration_quota_message,
    exploration_skipped_note,
)
from flight_deals.domain.models import DatePair, search_for
from flight_deals.domain.timeutil import taipei_date
from flight_deals.domain.validation import validate_exploration
from flight_deals.ports import Clock, FlightPriceSource, Redactor
from flight_deals.services.health import HealthService
from flight_deals.services.notifications import NotificationService
from flight_deals.services.settings import SettingsService
from flight_deals.services.source_query import ERROR_SUMMARY_LIMIT, PairQuery, SourceQuery
from flight_deals.storage.repository import CellUpdate, ExplorationRecord, Repository

log = logging.getLogger(__name__)

LOCK_TIMEOUT_SECONDS = 900
CreateStatus = Literal["created", "reused", "invalid", "quota", "busy", "scheduler_off"]


def _never(_exploration_id: int) -> None:
    return None


def _not_running() -> bool:
    return False


@dataclass
class ExplorationHooks:
    """Set by ``app.py`` so services never import the scheduler."""

    schedule: Callable[[int], None] = _never
    scheduler_running: Callable[[], bool] = _not_running


@dataclass(frozen=True)
class CreateResult:
    status: CreateStatus
    exploration_id: int | None = None
    errors: dict[str, str] = field(default_factory=dict)
    hourly_left: int | None = None
    needed: int | None = None
    message: str | None = None

    @property
    def ok(self) -> bool:
        return self.status in ("created", "reused")


@dataclass(frozen=True)
class QuotaView:
    hourly_left: int
    reserve: int
    max_cells: int


def cell_update(
    query: PairQuery, currency: str, redactor: Redactor, queried_at: datetime
) -> CellUpdate:
    """Map one shared source query onto an exploration cell (cheapest quote only).

    ``fetched_at`` is the quote's fetch time, or ``queried_at`` for answers without a
    price, so the 24-hour "not embedded" ratio can count every real query."""
    entry = query.entry
    status = str(entry.get("status") or "skipped")
    reason = entry.get("reason")
    error = redactor(query.error)[:ERROR_SUMMARY_LIMIT] if query.error else None
    quote = query.cheapest
    if quote is not None:
        mismatch = quote.currency != currency
        return CellUpdate(
            status="ok",
            reason="currency_mismatch" if mismatch else None,
            source=quote.source,
            price_kind=quote.price_kind,
            from_cache=bool(entry.get("from_cache")),
            attempts=query.queries,
            amount_minor=quote.amount_minor,
            currency=quote.currency,
            carrier=quote.carrier,
            stops=quote.stops,
            duration_minutes=quote.duration_minutes,
            depart_time=quote.depart_time,
            as_of=quote.as_of,
            fetched_at=quote.fetched_at,
            error=error if mismatch else None,
        )
    if status not in ("no_data", "blocked", "error"):
        # Nothing was asked: every source's breaker was open.
        status, reason = "skipped", "breaker_open"
    return CellUpdate(
        status=status,
        reason=str(reason) if reason else None,
        source=str(entry["source"]) if entry.get("source") else None,
        from_cache=bool(entry.get("from_cache")),
        attempts=query.queries,
        fetched_at=None if status == "skipped" else queried_at,
        error=error if status in ("blocked", "error") else None,
    )


class ExplorationService:
    def __init__(
        self,
        repo: Repository,
        sources: list[FlightPriceSource],
        health: HealthService,
        notifications: NotificationService,
        settings: SettingsService,
        *,
        scan_lock: threading.Lock,
        max_cells: int,
        reuse_hours: int,
        retention_days: int,
        clock: Clock,
        redactor: Redactor,
        create_lock: threading.Lock | None = None,
    ) -> None:
        self._repo = repo
        self._query = SourceQuery(sources, health, clock=clock, redactor=redactor)
        self._health = health
        self._notifications = notifications
        self._settings = settings
        self._scan_lock = scan_lock
        self._max_cells = max_cells
        self._reuse = timedelta(hours=reuse_hours)
        self._retention = timedelta(days=retention_days)
        self._clock = clock
        self._redact = redactor
        # Serialises create() calls from concurrent web requests (one exploration at a time).
        # app.py shares it with ComparisonService.create (FD-9 Decision 3).
        self._create_lock = create_lock or threading.Lock()
        self.hooks = ExplorationHooks()

    @property
    def sources(self) -> list[FlightPriceSource]:
        return self._query.sources

    @property
    def max_cells(self) -> int:
        return self._max_cells

    # ---- web side ------------------------------------------------------------

    def quota(self) -> QuotaView:
        settings = self._settings.current()
        used = self._repo.queries_used_since(self._clock() - timedelta(hours=1))
        return QuotaView(
            hourly_left=max(settings.global_hourly_query_limit - used, 0),
            reserve=settings.exploration_reserve_for_scans,
            max_cells=self._max_cells,
        )

    def create(self, raw: Mapping[str, object]) -> CreateResult:
        """Validate, then reuse / refuse / queue. Never sends a query (C-45)."""
        now = self._clock()
        today = taipei_date(now)
        outcome = validate_exploration(raw, today)
        if outcome.spec is None:
            return CreateResult("invalid", errors=outcome.errors)
        spec = outcome.spec
        pairs = month_pairs(spec, today)[: self._max_cells]
        if not pairs:
            return CreateResult("invalid", errors={"month": EXPLORATION_NO_DATES})
        key = spec.condition_key()
        with self._create_lock:
            reused = self._repo.reusable_exploration(key, now - self._reuse)
            if reused is not None:
                return CreateResult("reused", reused.id)
            active = self._repo.active_exploration()
            if active is not None:
                if active.condition_key == key:
                    return CreateResult("reused", active.id)
                return CreateResult(
                    "busy",
                    active.id,
                    message=f"{EXPLORATION_BUSY}（進度：/explorations/{active.id}）",
                )
            comparing = self._repo.active_comparison()
            if comparing is not None:
                # FD-9: a running comparison blocks explorations too (no id: not ours).
                return CreateResult(
                    "busy", message=comparison_busy_message(f"/comparisons/{comparing.id}")
                )
            if not self.hooks.scheduler_running():
                return CreateResult("scheduler_off", message=EXPLORATION_SCHEDULER_OFF)
            quota = self.quota()
            if quota.hourly_left - quota.reserve < len(pairs):
                return CreateResult(
                    "quota",
                    hourly_left=quota.hourly_left,
                    needed=len(pairs),
                    message=exploration_quota_message(quota.hourly_left, len(pairs), quota.reserve),
                )
            exploration_id = self._repo.insert_exploration(spec, pairs, now)
        try:
            self.hooks.schedule(exploration_id)
        except Exception:
            log.exception("exploration %s could not be scheduled", exploration_id)
            self._repo.finish_exploration(
                exploration_id,
                status="failed",
                finished_at=self._clock(),
                skip_reason="interrupted",
                error_summary=EXPLORATION_SCHEDULER_OFF,
            )
            return CreateResult("scheduler_off", message=EXPLORATION_SCHEDULER_OFF)
        return CreateResult("created", exploration_id)

    def status(self, exploration_id: int) -> dict[str, object] | None:
        """Progress for the poller: a fixed four-field whitelist (C-46)."""
        record = self._repo.get_exploration(exploration_id)
        if record is None:
            return None
        return {
            "exploration_id": record.id,
            "status": record.status,
            "total": record.total,
            "done": record.done,
        }

    # ---- worker side -----------------------------------------------------------

    def run(self, exploration_id: int) -> str:
        """Body of the ``explore:<id>`` job; runs on the scheduler's single worker."""
        if not self._scan_lock.acquire(timeout=LOCK_TIMEOUT_SECONDS):
            self._fail(exploration_id, "掃描佔用過久，探索未執行")
            return "failed"
        try:
            if not self._repo.start_exploration(exploration_id, self._clock()):
                return "not_queued"
            return self._run(exploration_id)
        except Exception as exc:
            log.exception("exploration %s crashed", exploration_id)
            self._fail(exploration_id, f"探索中斷：{type(exc).__name__}: {exc}")
            return "failed"
        except BaseException as exc:
            # KeyboardInterrupt / SystemExit: never leave the exploration "running".
            self._fail(exploration_id, f"探索中斷：{type(exc).__name__}")
            raise
        finally:
            self._scan_lock.release()

    def _run(self, exploration_id: int) -> str:
        record = self._repo.get_exploration(exploration_id)
        assert record is not None
        spec = record.spec
        opened: list[tuple[str, str | None]] = []
        skip_reason: str | None = None
        try:
            for cell in self._repo.exploration_cells(exploration_id):
                if cell.status != "pending":
                    continue
                if self._hourly_left() <= 0:
                    skip_reason = "global_hourly_limit"
                    break
                if not any(self._health.allow(s.name) for s in self._query.sources):
                    skip_reason = "breaker_open"
                    break
                pair = DatePair(cell.depart_date, cell.return_date)
                query = self._query.query(search_for(spec, pair, spec.currency), spec.currency)
                opened.extend(query.opened)
                self._repo.record_exploration_cell(
                    exploration_id,
                    cell.depart_date,
                    cell_update(query, spec.currency, self._redact, self._clock()),
                )
            skipped = self._repo.finish_exploration(
                exploration_id,
                status="done",
                finished_at=self._clock(),
                skip_reason=skip_reason or "interrupted",
                error_summary=None,
            )
            if skipped and skip_reason:
                text = (
                    EXPLORATION_HOURLY_LIMIT
                    if skip_reason == "global_hourly_limit"
                    else EXPLORATION_BREAKER_OPEN
                )
                self._repo.set_exploration_summary(
                    exploration_id, exploration_skipped_note(text, skipped)
                )
        finally:
            # A breaker newly opened by an exploration query alerts like a scan's (D-2.3).
            for source, error in opened:
                self._notifications.send_ops_failure(source, error)
        return "done"

    def _hourly_left(self) -> int:
        limit = self._settings.current().global_hourly_query_limit
        return limit - self._repo.queries_used_since(self._clock() - timedelta(hours=1))

    def _fail(self, exploration_id: int, message: str) -> None:
        try:
            self._repo.finish_exploration(
                exploration_id,
                status="failed",
                finished_at=self._clock(),
                skip_reason="interrupted",
                error_summary=self._redact(message)[:ERROR_SUMMARY_LIMIT],
            )
        except Exception:
            log.exception("could not mark exploration %s as failed", exploration_id)

    def recover_interrupted(self) -> list[int]:
        """At scheduler start: explorations cut off by a stop or crash become failed;
        they are never resumed or re-queried (FR-R9)."""
        ids = self._repo.interrupt_active_explorations(self._clock(), EXPLORATION_RESTARTED)
        if ids:
            log.info("explorations interrupted by a restart: %s", ids)
        return ids

    def purge_expired(self) -> int:
        """Hourly: drop explorations created more than the retention period ago."""
        removed = self._repo.delete_explorations_created_before(self._clock() - self._retention)
        if removed:
            log.info("purged %d expired exploration(s)", removed)
        return removed

    def get(self, exploration_id: int) -> ExplorationRecord | None:
        return self._repo.get_exploration(exploration_id)

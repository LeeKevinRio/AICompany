"""Scan flow: sample date pairs, query sources, store prices, evaluate alerts."""

from __future__ import annotations

import logging
import threading
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import timedelta
from typing import Any

from flight_deals.domain.dates import expand_pairs, is_expired, sample_pairs
from flight_deals.domain.models import (
    SCANNABLE_STATUSES,
    DatePair,
    FlightSearch,
    PriceKind,
    Watch,
    WatchStatus,
)
from flight_deals.domain.rules import (
    AlertBaseline,
    Candidate,
    evaluate_price_alerts,
    should_rearm,
)
from flight_deals.domain.timeutil import taipei_date
from flight_deals.ports import Clock, FlightPriceSource, Redactor, SourceResult
from flight_deals.services.health import HealthService
from flight_deals.services.notifications import NotificationService
from flight_deals.services.settings import SettingsService
from flight_deals.storage.repository import AlertStateRecord, Repository

log = logging.getLogger(__name__)

ERROR_SUMMARY_LIMIT = 500


@dataclass(frozen=True)
class ScanOutcome:
    watch_id: int
    status: str
    scan_run_id: int | None = None
    queries_used: int = 0
    notification_id: int | None = None


@dataclass
class _PairOutcome:
    entry: dict[str, Any]
    queries: int = 0
    success: bool = False
    failure: bool = False
    candidate: Candidate | None = None
    error: str | None = None


class ScanService:
    def __init__(
        self,
        repo: Repository,
        sources: Sequence[FlightPriceSource],
        health: HealthService,
        notifications: NotificationService,
        settings: SettingsService,
        *,
        alert_max_items: int,
        stale_after_failed_scans: int,
        clock: Clock,
        redactor: Redactor,
    ) -> None:
        self._repo = repo
        self._sources = list(sources)
        self._health = health
        self._notifications = notifications
        self._settings = settings
        self._alert_max_items = alert_max_items
        self._stale_after = stale_after_failed_scans
        self._clock = clock
        self._redact = redactor
        self._lock = threading.Lock()
        self._opened_sources: list[tuple[str, str | None]] = []
        # Outbound queries spent by the current run, updated as soon as each call returns.
        self._spent = 0

    @property
    def source_names(self) -> list[str]:
        return [s.name for s in self._sources]

    @property
    def lock(self) -> threading.Lock:
        return self._lock

    # ---- public entry points ---------------------------------------------------

    def scan_watch(self, watch_id: int, trigger: str = "scheduled") -> ScanOutcome:
        """Scan one watch. Never overlaps with another scan in this process (FR-B7)."""
        if not self._lock.acquire(blocking=False):
            self._health.record_scheduler_event(
                "scan_skipped", f"watch {watch_id}: 上一次掃描仍在執行，本次略過"
            )
            log.info("scan of watch %s skipped: another scan is running", watch_id)
            return ScanOutcome(watch_id, "skipped_running")
        try:
            return self._scan(watch_id, trigger)
        except Exception as exc:
            log.exception("scan of watch %s crashed", watch_id)
            self._health.record_scheduler_event(
                "scan_crashed", f"watch {watch_id}: {type(exc).__name__}: {exc}"
            )
            return ScanOutcome(watch_id, "crashed")
        finally:
            self._lock.release()

    def expire_sweep(self) -> list[int]:
        """Mark watches whose dates are all in the past as expired (FR-A9)."""
        today = taipei_date(self._clock())
        expired: list[int] = []
        for watch in self._repo.list_watches():
            if watch.status != "expired" and is_expired(watch.spec, today):
                self._repo.set_watch_status(watch.id, "expired", self._clock())
                expired.append(watch.id)
        return expired

    def schedulable_watches(self) -> list[Watch]:
        return [w for w in self._repo.list_watches() if w.status in SCANNABLE_STATUSES]

    # ---- internals -------------------------------------------------------------

    def _scan(self, watch_id: int, trigger: str) -> ScanOutcome:
        # Retry alerts that failed in earlier rounds before producing new ones (FR-C7).
        self._notifications.retry_pending()
        watch = self._repo.get_watch(watch_id)
        if watch is None:
            return ScanOutcome(watch_id, "not_found")
        if watch.status not in SCANNABLE_STATUSES:
            return ScanOutcome(watch_id, "not_scannable")
        now = self._clock()
        pairs = expand_pairs(watch.spec, taipei_date(now))
        if not pairs:
            self._repo.set_watch_status(watch.id, "expired", now)
            return ScanOutcome(watch_id, "expired")

        settings = self._settings.current()
        sampled, next_offset, truncated = sample_pairs(
            pairs, settings.max_pairs_per_scan, watch.sample_offset
        )
        run_id = self._repo.insert_scan_run(
            watch_id=watch.id,
            revision=watch.revision,
            trigger=trigger,
            started_at=now,
            sampled_pairs=sampled,
            total_pairs=len(pairs),
            limit_reached=truncated,
        )
        if truncated:
            log.info(
                "watch %s: %d date pairs exceed limit %d; sampled %d (limit reached)",
                watch.id,
                len(pairs),
                settings.max_pairs_per_scan,
                len(sampled),
            )
        self._opened_sources = []
        self._spent = 0
        results: list[dict[str, Any]] = []
        candidates: list[Candidate] = []
        errors: list[str] = []
        queries = 0
        any_success = any_failure = global_hit = False
        try:
            # Soft cap: the check happens before each date pair, and one pair may use
            # several attempts (retries), so an hour can exceed the limit slightly.
            hourly_left = settings.global_hourly_query_limit - self._repo.queries_used_since(
                now - timedelta(hours=1)
            )
            for pair in sampled:
                if queries >= hourly_left:
                    global_hit = True
                    results.append(self._skipped_entry(pair, "global_hourly_limit"))
                    continue
                outcome = self._query_pair(watch, pair, run_id)
                results.append(outcome.entry)
                queries = self._spent
                any_success |= outcome.success
                any_failure |= outcome.failure or not outcome.success
                if outcome.candidate is not None:
                    candidates.append(outcome.candidate)
                if outcome.error:
                    errors.append(outcome.error)
            if global_hit:
                errors.append("已達全域每小時查詢上限，部分日期本輪未查")

            if any_success and not any_failure and not global_hit:
                status = "ok"
            elif any_success:
                status = "partial"
            else:
                status = "failed"
            summary = "；".join(dict.fromkeys(errors)) if errors else None
            finished = self._clock()
            self._repo.finish_scan_run(
                run_id,
                finished_at=finished,
                status=status,
                query_results=results,
                queries_used=queries,
                global_limit_reached=global_hit,
                error_summary=self._redact(summary)[:ERROR_SUMMARY_LIMIT] if summary else None,
            )
        except Exception as exc:
            self._abort_run(run_id, results, self._spent, global_hit, exc)
            raise

        current = self._repo.get_watch(watch.id)
        notification_id: int | None = None
        if current is not None:
            failed_scans = 0 if any_success else current.consecutive_failed_scans + 1
            new_status: WatchStatus = current.status
            if current.status == "stale" and any_success:
                new_status = "active"
            elif current.status == "active" and failed_scans >= self._stale_after:
                new_status = "stale"
            self._repo.record_watch_scan(
                watch.id,
                scanned_at=finished,
                sample_offset=next_offset,
                consecutive_failed_scans=failed_scans,
                status=new_status,
            )
            if (
                current.status in SCANNABLE_STATUSES
                and current.revision == watch.revision
                and candidates
            ):
                notification_id = self._evaluate_alerts(current, run_id, candidates)

        for source, error in self._opened_sources:
            self._notifications.send_ops_failure(source, error)
        return ScanOutcome(watch.id, status, run_id, queries, notification_id)

    def _abort_run(
        self,
        run_id: int,
        results: list[dict[str, Any]],
        queries: int,
        global_hit: bool,
        exc: Exception,
    ) -> None:
        """Close a crashed run as failed, keeping the queries already spent."""
        message = self._redact(f"掃描中斷：{type(exc).__name__}: {exc}")[:ERROR_SUMMARY_LIMIT]
        try:
            self._repo.finish_scan_run(
                run_id,
                finished_at=self._clock(),
                status="failed",
                query_results=results,
                queries_used=queries,
                global_limit_reached=global_hit,
                error_summary=message,
            )
        except Exception:
            log.exception("could not mark scan run %s as failed", run_id)

    @staticmethod
    def _skipped_entry(pair: DatePair, reason: str) -> dict[str, Any]:
        depart, ret = pair.as_json()
        return {
            "depart": depart,
            "return": ret,
            "status": "skipped",
            "reason": reason,
            "source": None,
            "tries": [],
        }

    def _query_pair(self, watch: Watch, pair: DatePair, run_id: int) -> _PairOutcome:
        depart, ret = pair.as_json()
        entry: dict[str, Any] = {
            "depart": depart,
            "return": ret,
            "status": "skipped",
            "reason": None,
            "source": None,
            "from_cache": False,
            "amount_minor": None,
            "currency": None,
            "tries": [],
        }
        outcome = _PairOutcome(entry)
        search = FlightSearch(
            origin=watch.spec.origin,
            destination=watch.spec.destination,
            pair=pair,
            max_stops=watch.spec.max_stops,
            currency=watch.spec.currency,
        )
        for source in self._sources:
            if not self._health.allow(source.name):
                entry["tries"].append({"source": source.name, "status": "skipped_breaker_open"})
                entry["reason"] = "breaker_open"
                outcome.error = f"{source.name} 斷路器開啟中，暫停查詢"
                continue
            result = self._safe_search(source, search)
            outcome.queries += result.attempts
            self._spent += result.attempts
            try_info: dict[str, Any] = {
                "source": source.name,
                "status": result.status,
                "error": result.error,
                "from_cache": result.from_cache,
            }
            stats = result.parse_stats
            if stats is not None:
                # Integer counts only; display text is composed by services/views.py.
                try_info.update(
                    itineraries=stats.itineraries,
                    unpriced=stats.unpriced,
                    malformed=stats.malformed,
                )
            entry["tries"].append(try_info)
            entry.update(source=source.name, status=result.status, from_cache=result.from_cache)
            if not result.from_cache:
                if result.status in ("ok", "no_data"):
                    self._health.record_success(source.name)
                else:
                    if self._health.record_failure(source.name, result.error):
                        self._opened_sources.append((source.name, result.error))
            if result.status == "ok":
                cheapest = min(
                    (q for q in result.quotes if q.currency == watch.spec.currency),
                    key=lambda q: q.amount_minor,
                    default=None,
                )
                if cheapest is None:
                    entry["status"] = "currency_mismatch"
                    outcome.error = "來源回傳幣別與監看幣別不一致，未納入通知判斷"
                    cheapest = min(result.quotes, key=lambda q: q.amount_minor)
                obs_id = self._repo.insert_observation(
                    scan_run_id=run_id, watch_id=watch.id, revision=watch.revision, quote=cheapest
                )
                entry.update(amount_minor=cheapest.amount_minor, currency=cheapest.currency)
                if stats is not None and stats.malformed > 0:
                    # Unpriced itineraries are expected and stay out of error_summary;
                    # unrecognised ones are kept visible as a sign of format drift.
                    note = f"{source.name} 回應中有 {stats.malformed} 筆格式無法辨識"
                    outcome.error = f"{outcome.error}；{note}" if outcome.error else note
                outcome.success = True
                outcome.candidate = Candidate(
                    observation_id=obs_id,
                    depart_date=cheapest.depart_date,
                    return_date=cheapest.return_date,
                    amount_minor=cheapest.amount_minor,
                    currency=cheapest.currency,
                    price_kind=cheapest.price_kind,
                    source=cheapest.source,
                    carrier=cheapest.carrier,
                    fetched_at=cheapest.fetched_at,
                )
                return outcome
            if result.status == "no_data":
                outcome.success = True
                return outcome
            outcome.failure = True
            outcome.error = f"{source.name} {result.status}: {result.error or ''}".strip()
        return outcome

    def _safe_search(self, source: FlightPriceSource, search: FlightSearch) -> SourceResult:
        try:
            return source.search(search)
        except Exception as exc:  # adapters should not raise; contain it if they do
            return SourceResult(
                source=source.name,
                status="error",
                fetched_at=self._clock(),
                error=self._redact(f"{type(exc).__name__}: {exc}")[:ERROR_SUMMARY_LIMIT],
            )

    def _evaluate_alerts(
        self, watch: Watch, run_id: int, candidates: list[Candidate]
    ) -> int | None:
        settings = self._settings.current()
        spec = watch.spec
        last_id: int | None = None
        kinds: list[PriceKind] = sorted({c.price_kind for c in candidates})
        for kind in kinds:
            same = [c for c in candidates if c.price_kind == kind and c.currency == spec.currency]
            if not same:
                continue
            state = self._repo.get_alert_state(watch.id, kind)
            run_min = min(c.amount_minor for c in same)
            armed = state.armed
            if not armed and should_rearm(run_min, spec.budget_amount_minor):
                armed = True
                self._repo.save_alert_state(
                    watch.id,
                    kind,
                    AlertStateRecord(
                        state.last_notified_amount_minor, state.last_notified_at, True
                    ),
                )
            baseline = AlertBaseline(
                last_notified_amount_minor=state.last_notified_amount_minor,
                armed=armed,
                historical_min_amount_minor=self._repo.min_amount(
                    watch_id=watch.id,
                    revision=watch.revision,
                    price_kind=kind,
                    currency=spec.currency,
                    exclude_scan_run_id=run_id,
                ),
            )
            items = evaluate_price_alerts(
                same,
                watch_id=watch.id,
                price_kind=kind,
                currency=spec.currency,
                budget_amount_minor=spec.budget_amount_minor,
                notify_on_new_low=spec.notify_on_new_low,
                drop_threshold_bp=settings.drop_threshold_bp,
                baseline=baseline,
                already_notified_keys=self._repo.notified_item_keys(watch.id, kind),
                max_items=self._alert_max_items,
            )
            if items:
                last_id = self._notifications.send_price_alert(watch, kind, items) or last_id
        return last_id

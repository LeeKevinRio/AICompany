"""Source health and circuit breaker (ADR-0002 D-2.3), plus scheduler skip records."""

from __future__ import annotations

import logging
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import replace
from datetime import datetime, timedelta
from typing import Any

from flight_deals.ports import Clock, Redactor
from flight_deals.storage.repository import Repository, SourceHealthRecord

log = logging.getLogger(__name__)

ERROR_LIMIT = 500
NO_EMBEDDED_REASON = "no_embedded_results"
NO_EMBEDDED_WINDOW = timedelta(hours=24)


def no_embedded_counts(
    scan_results: Iterable[Sequence[Mapping[str, Any]]],
    exploration_counts: Iterable[tuple[str, int, int]] = (),
) -> dict[str, tuple[int, int]]:
    """Per source: (no_embedded_results queries, real queries). Skipped, pending and
    cache-served entries are left out of both numbers (FD-6 Decision 8)."""
    counts: dict[str, list[int]] = {}
    for results in scan_results:
        for entry in results:
            source = entry.get("source")
            status = entry.get("status")
            if not source or status in ("skipped", "pending") or entry.get("from_cache"):
                continue
            bucket = counts.setdefault(str(source), [0, 0])
            bucket[1] += 1
            if status == "no_data" and entry.get("reason") == NO_EMBEDDED_REASON:
                bucket[0] += 1
    for source, total, hits in exploration_counts:
        bucket = counts.setdefault(source, [0, 0])
        bucket[0] += hits
        bucket[1] += total
    return {source: (hits, total) for source, (hits, total) in counts.items()}


def no_embedded_hint(
    counts: Mapping[str, tuple[int, int]], *, min_queries: int, min_ratio_pct: int
) -> dict[str, int] | None:
    """Health-page hint when a source has >= ``min_queries`` queries of which at least
    ``min_ratio_pct`` percent were not embedded; the highest ratio wins. Pure."""
    best: dict[str, int] | None = None
    for hits, total in counts.values():
        if total < min_queries or hits * 100 < min_ratio_pct * total:
            continue
        ratio = hits * 100 // total
        if best is None or ratio > best["ratio_pct"]:
            best = {"ratio_pct": ratio, "count": hits, "total": total}
    return best


def round_not_embedded(results: Sequence[Mapping[str, Any]]) -> bool:
    """One finished round "hits" when it has at least one non-skipped pair and every
    non-skipped pair is ``no_embedded_results``."""
    queried = [r for r in results if r.get("status") != "skipped"]
    return bool(queried) and all(
        r.get("status") == "no_data" and r.get("reason") == NO_EMBEDDED_REASON for r in queried
    )


def no_embedded_streak(rounds: Sequence[Sequence[Mapping[str, Any]]], need: int) -> bool:
    """True when the latest ``need`` rounds (newest first, current revision) all hit."""
    return len(rounds) >= need and all(round_not_embedded(r) for r in rounds[:need])


def describe_source(record: SourceHealthRecord | None) -> tuple[str, str]:
    """(label, key) of a source's state; shared by the health page and the digest."""
    if record is None or (record.last_success_at is None and record.last_failure_at is None):
        return "未知（尚未查詢）", "unknown"
    if record.breaker_state != "closed":
        return "異常", "down"
    if record.consecutive_failures > 0:
        return f"正常（最近連續失敗 {record.consecutive_failures} 次）", "warn"
    return "正常", "ok"


class HealthService:
    def __init__(
        self,
        repo: Repository,
        *,
        failure_threshold: int,
        cooldown_minutes: int,
        clock: Clock,
        redactor: Redactor,
        no_embedded_min_queries: int = 10,
        no_embedded_min_ratio_pct: int = 50,
    ) -> None:
        self._repo = repo
        self._no_embedded_min_queries = no_embedded_min_queries
        self._no_embedded_min_ratio_pct = no_embedded_min_ratio_pct
        self._threshold = failure_threshold
        self._cooldown = timedelta(minutes=cooldown_minutes)
        self._clock = clock
        self._redact = redactor

    @property
    def failure_threshold(self) -> int:
        return self._threshold

    def ensure_sources(self, names: list[str]) -> None:
        for name in names:
            if self._repo.get_source_health(name) is None:
                self._repo.save_source_health(
                    SourceHealthRecord(name, True, "closed", 0, None, None, None, None)
                )

    def _get(self, source: str) -> SourceHealthRecord:
        record = self._repo.get_source_health(source)
        if record is None:
            record = SourceHealthRecord(source, True, "closed", 0, None, None, None, None)
        return record

    def allow(self, source: str) -> bool:
        """Whether a query may be sent now; moves open -> half_open after cooldown."""
        record = self._get(source)
        if record.breaker_state == "closed" or record.breaker_state == "half_open":
            return True
        now = self._clock()
        if record.open_until is not None and now >= record.open_until:
            self._repo.save_source_health(replace(record, breaker_state="half_open"))
            log.info("source %s breaker half-open, sending a trial query", source)
            return True
        return False

    def record_success(self, source: str) -> None:
        record = self._get(source)
        if record.breaker_state != "closed":
            log.info("source %s recovered, breaker closed", source)
        self._repo.save_source_health(
            replace(
                record,
                breaker_state="closed",
                consecutive_failures=0,
                open_until=None,
                last_success_at=self._clock(),
            )
        )

    def record_failure(self, source: str, error: str | None) -> bool:
        """Record a failure; returns True only when the breaker newly trips from closed."""
        record = self._get(source)
        now = self._clock()
        failures = record.consecutive_failures + 1
        message = self._redact(error or "unknown error")[:ERROR_LIMIT]
        newly_opened = False
        state = record.breaker_state
        open_until = record.open_until
        if state == "half_open":
            state, open_until = "open", now + self._cooldown
        elif state == "closed" and failures >= self._threshold:
            state, open_until = "open", now + self._cooldown
            newly_opened = True
        self._repo.save_source_health(
            replace(
                record,
                breaker_state=state,
                consecutive_failures=failures,
                open_until=open_until,
                last_failure_at=now,
                last_error=message,
            )
        )
        if newly_opened:
            log.warning("source %s breaker opened after %d failures", source, failures)
        return newly_opened

    def records(self) -> list[SourceHealthRecord]:
        return self._repo.list_source_health()

    def record_scheduler_event(self, kind: str, detail: str | None) -> None:
        self._repo.insert_event(self._clock(), kind, self._redact(detail) if detail else None)

    def no_embedded_summary(self, now: datetime) -> dict[str, int] | None:
        """24-hour "results not embedded" ratio hint: one scan_run SELECT plus one
        exploration_cell count. Display only: no alert, no breaker effect (FR-H3)."""
        since = now - NO_EMBEDDED_WINDOW
        counts = no_embedded_counts(
            self._repo.scan_query_results_since(since),
            self._repo.exploration_cell_counts_since(since),
        )
        return no_embedded_hint(
            counts,
            min_queries=self._no_embedded_min_queries,
            min_ratio_pct=self._no_embedded_min_ratio_pct,
        )

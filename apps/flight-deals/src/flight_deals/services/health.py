"""Source health and circuit breaker (ADR-0002 D-2.3), plus scheduler skip records."""

from __future__ import annotations

import logging
from dataclasses import replace
from datetime import timedelta

from flight_deals.ports import Clock, Redactor
from flight_deals.storage.repository import Repository, SourceHealthRecord

log = logging.getLogger(__name__)

ERROR_LIMIT = 500


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
    ) -> None:
        self._repo = repo
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

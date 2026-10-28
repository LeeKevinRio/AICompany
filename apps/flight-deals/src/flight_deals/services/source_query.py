"""One date pair against the configured sources (shared by scans and explorations).

Tries each source in order, honours the circuit breaker, records source success and
failure (``no_data`` and its sub-reasons are never failures), and picks the cheapest
quote in the requested currency (ADR-0002 FD-6 Decision 3). Storing the outcome is
left to the caller: scans write ``price_observation``, explorations write a cell.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from typing import Any

from flight_deals.domain.models import DatePair, FlightSearch, PriceQuote
from flight_deals.ports import Clock, FlightPriceSource, Redactor, SourceResult
from flight_deals.services.health import HealthService

ERROR_SUMMARY_LIMIT = 500


@dataclass
class PairQuery:
    """``entry`` is the per-pair JSON stored in ``scan_run.query_results``."""

    entry: dict[str, Any]
    queries: int = 0
    success: bool = False
    failure: bool = False
    # Cheapest quote of an ``ok`` answer (a different currency when none matched).
    cheapest: PriceQuote | None = None
    error: str | None = None
    # Sources whose breaker this query newly opened: (source, error).
    opened: list[tuple[str, str | None]] = field(default_factory=list)


class SourceQuery:
    def __init__(
        self,
        sources: Sequence[FlightPriceSource],
        health: HealthService,
        *,
        clock: Clock,
        redactor: Redactor,
    ) -> None:
        self._sources = list(sources)
        self._health = health
        self._clock = clock
        self._redact = redactor

    @property
    def sources(self) -> list[FlightPriceSource]:
        return list(self._sources)

    def query(
        self,
        search: FlightSearch,
        currency: str,
        *,
        on_spent: Callable[[int], None] | None = None,
    ) -> PairQuery:
        """Query ``search``; ``on_spent`` is told about attempts as soon as each call returns."""
        depart, ret = search.pair.as_json()
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
        outcome = PairQuery(entry)
        for source in self._sources:
            if not self._health.allow(source.name):
                entry["tries"].append({"source": source.name, "status": "skipped_breaker_open"})
                entry["reason"] = "breaker_open"
                outcome.error = f"{source.name} 斷路器開啟中，暫停查詢"
                continue
            result = self._safe_search(source, search)
            outcome.queries += result.attempts
            if on_spent is not None:
                on_spent(result.attempts)
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
                        outcome.opened.append((source.name, result.error))
            if result.status == "ok":
                cheapest = min(
                    (q for q in result.quotes if q.currency == currency),
                    key=lambda q: q.amount_minor,
                    default=None,
                )
                if cheapest is None:
                    entry["status"] = "currency_mismatch"
                    outcome.error = "來源回傳幣別與監看幣別不一致，未納入通知判斷"
                    cheapest = min(result.quotes, key=lambda q: q.amount_minor)
                entry.update(amount_minor=cheapest.amount_minor, currency=cheapest.currency)
                if stats is not None and stats.malformed > 0:
                    # Unpriced itineraries are expected and stay out of error_summary;
                    # unrecognised ones are kept visible as a sign of format drift.
                    note = f"{source.name} 回應中有 {stats.malformed} 筆格式無法辨識"
                    outcome.error = f"{outcome.error}；{note}" if outcome.error else note
                outcome.success = True
                outcome.cheapest = cheapest
                return outcome
            if result.status == "no_data":
                # A sub-reason (e.g. results not embedded) is shown, never counted as failure.
                reason = result.extra.get("reason")
                if reason:
                    entry["reason"] = reason
                    try_info["reason"] = reason
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


def skipped_entry(pair: DatePair, reason: str) -> dict[str, Any]:
    depart, ret = pair.as_json()
    return {
        "depart": depart,
        "return": ret,
        "status": "skipped",
        "reason": reason,
        "source": None,
        "tries": [],
    }

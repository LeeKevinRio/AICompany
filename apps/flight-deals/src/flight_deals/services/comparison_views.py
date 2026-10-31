"""Read models of the comparison pages (ADR-0002 FD-9 Decision 4), zh-TW, ready to render.

``comparison_page`` reads exactly two statements (the comparison and its cells); the
order of the result table is the module-level pure function ``comparison_order``.
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import date, datetime, timedelta
from typing import Any

from flight_deals.domain.airports import place_label
from flight_deals.domain.currency import format_money
from flight_deals.domain.links import google_flights_url
from flight_deals.domain.messages import (
    COMPARISON_DEFERRED_NOTE,
    COMPARISON_NO_PRICE_NOTE,
    COMPARISON_ORDER_NOTE,
    COMPARISON_PAX_LABEL,
    COMPARISON_PREFILL_MISSING,
    COMPARISON_PREFILL_OK,
    COMPARISON_REFERENCE_NOTE,
    COMPARISON_ROW_LABELS,
    COMPARISON_SINGLE_DATE_NOTE,
    COMPARISON_STATUS_LABELS,
    DISCLAIMER,
    TRIP_TYPE_LABELS,
    comparison_age_note,
    comparison_created_ago,
    comparison_dates_label,
    comparison_progress_label,
    comparison_reused_note,
    comparison_stops_label,
    comparison_unfinished_note,
)
from flight_deals.domain.models import CABINS, search_for
from flight_deals.domain.timeutil import format_taipei, taipei_date
from flight_deals.domain.trip_labels import (
    BOOKING_FALLBACK_NOTE,
    cabin_label,
    flight_duration_label,
    total_price_note,
)
from flight_deals.domain.validation import MAX_DAYS_AHEAD, MAX_DESTINATIONS, MIN_DESTINATIONS
from flight_deals.ports import BookingLinkBuilder, Clock
from flight_deals.services.comparison import ComparisonService, comparison_url, exploration_url
from flight_deals.services.exploration_views import stops_label
from flight_deals.services.notifications import safe_booking_url
from flight_deals.services.settings import SettingsService
from flight_deals.services.views import (
    NO_EMBEDDED_REASON,
    active_comparison_view,
    active_exploration_view,
)
from flight_deals.storage.repository import (
    ComparisonCellRecord,
    ComparisonRecord,
    Repository,
)

LIST_DAYS = 7
STALE_HOURS = 24
DEFAULT_TRIP_DAYS = 5

__all__ = [
    "ComparisonViewService",
    "active_comparison_view",
    "comparison_order",
    "rankable",
    "row_label",
]


def rankable(cell: ComparisonCellRecord, currency: str) -> bool:
    """Priced in the comparison currency (no mismatch): the only rows ordered by price."""
    return (
        cell.status == "ok"
        and cell.amount_minor is not None
        and cell.reason != "currency_mismatch"
        and cell.currency == currency
    )


def comparison_order(
    cells: Sequence[ComparisonCellRecord], currency: str
) -> list[ComparisonCellRecord]:
    """Priced rows by (total price, input position), then every other row by position."""
    ranked = sorted(
        (c for c in cells if rankable(c, currency)),
        key=lambda c: (c.amount_minor or 0, c.position),
    )
    rest = sorted((c for c in cells if not rankable(c, currency)), key=lambda c: c.position)
    return [*ranked, *rest]


def row_label(cell: ComparisonCellRecord) -> str:
    """Status text of a result row; never blank or 0 (FR-S3)."""
    labels = COMPARISON_ROW_LABELS
    if cell.status == "ok":
        return labels["currency_mismatch"] if cell.reason == "currency_mismatch" else labels["ok"]
    if cell.status == "no_data":
        if cell.reason == NO_EMBEDDED_REASON:
            return labels["no_embedded_results"]
        return labels["no_data"]
    if cell.status == "skipped":
        return labels.get(cell.reason or "", labels["interrupted"])
    return labels.get(cell.status, labels["error"])


class ComparisonViewService:
    def __init__(
        self,
        repo: Repository,
        settings: SettingsService,
        comparisons: ComparisonService,
        *,
        clock: Clock,
        link_builder: BookingLinkBuilder | None = None,
    ) -> None:
        self._repo = repo
        self._settings = settings
        self._comparisons = comparisons
        self._clock = clock
        self._links = link_builder

    # ---- compare page (form and recent list) -------------------------------------

    def compare_page(self) -> dict[str, Any]:
        now = self._clock()
        today = taipei_date(now)
        quota = self._comparisons.quota()
        values = {
            "origin": "TPE",
            "origin_label": place_label("TPE"),
            "destinations": [],
            "trip_type": "round_trip",
            "date_input": "fixed",
            "depart_date": "",
            "return_date": "",
            "trip_days": DEFAULT_TRIP_DAYS,
            "max_stops": "",
            "cabin": CABINS[0],
        }
        return {
            "values": values,
            "cabin_options": [{"value": c, "label": cabin_label(c)} for c in CABINS],
            "quota": {
                "hourly_left": quota.hourly_left,
                "reserve": quota.reserve,
                "available": max(quota.hourly_left - quota.reserve, 0),
                "min_destinations": MIN_DESTINATIONS,
                "max_destinations": MAX_DESTINATIONS,
            },
            "recent": [
                self._recent_row(r, now)
                for r in self._repo.list_comparisons_since(now - timedelta(days=LIST_DAYS))
            ],
            "active": self._active(),
            "today": today.isoformat(),
            "max_date": (today + timedelta(days=MAX_DAYS_AHEAD)).isoformat(),
            "disclaimer": DISCLAIMER,
        }

    def _active(self) -> dict[str, Any] | None:
        comparing = active_comparison_view(self._repo)
        if comparing is not None:
            return {"kind": "comparison", **comparing, "url": comparison_url(comparing["id"])}
        exploring = active_exploration_view(self._repo)
        if exploring is not None:
            return {"kind": "exploration", **exploring, "url": exploration_url(exploring["id"])}
        return None

    def _recent_row(self, record: ComparisonRecord, now: datetime) -> dict[str, Any]:
        spec = record.spec
        age_hours = int((now - record.created_at).total_seconds() // 3600)
        old = now - record.created_at > timedelta(hours=STALE_HOURS)
        cheapest = (
            format_money(record.min_amount_minor, spec.currency)
            + total_price_note(spec.adults, spec.children)
            if record.min_amount_minor is not None
            else None
        )
        return {
            "id": record.id,
            "url": comparison_url(record.id),
            "origin_label": place_label(spec.origin),
            "destination_count": len(spec.destinations),
            "dates_label": comparison_dates_label(spec.depart_date, spec.return_date),
            "trip_type_label": TRIP_TYPE_LABELS[spec.trip_type],
            "conditions_label": _conditions(record),
            "status": record.status,
            "status_label": COMPARISON_STATUS_LABELS.get(record.status, record.status),
            "created_at_label": format_taipei(record.created_at),
            "finished_at_label": format_taipei(record.finished_at) if record.finished_at else None,
            "progress_label": (
                None
                if record.status == "done"
                else comparison_progress_label(record.done, record.total)
            ),
            "age_note": comparison_created_ago(age_hours) if old else None,
            "cheapest_label": cheapest,
            "cheapest_destination_label": (
                place_label(record.min_destination) if record.min_destination else None
            ),
        }

    # ---- result page -----------------------------------------------------------------

    def comparison_page(self, comparison_id: int, *, reused: bool = False) -> dict[str, Any] | None:
        record = self._repo.get_comparison(comparison_id)
        if record is None:
            return None
        cells = self._repo.comparison_cells(record.id)
        spec = record.spec
        now = self._clock()
        finished = record.finished_at or record.created_at
        age_hours = int((now - finished).total_seconds() // 3600)
        stale = record.status in ("done", "failed") and now - finished > timedelta(
            hours=STALE_HOURS
        )
        error_summary = None
        if record.status == "failed":
            reason = record.error_summary or COMPARISON_ROW_LABELS["interrupted"]
            error_summary = comparison_unfinished_note(record.done, record.total, reason)
        pax_note = total_price_note(spec.adults, spec.children)
        return {
            "comparison": {
                "id": record.id,
                "origin_label": place_label(spec.origin),
                "trip_type": spec.trip_type,
                "trip_type_label": TRIP_TYPE_LABELS[spec.trip_type],
                "depart_date": spec.depart_date.isoformat(),
                "return_date": spec.return_date.isoformat() if spec.return_date else None,
                "dates_label": comparison_dates_label(spec.depart_date, spec.return_date),
                "max_stops_label": comparison_stops_label(spec.max_stops),
                "cabin_label": cabin_label(spec.cabin),
                "pax_label": COMPARISON_PAX_LABEL,
                "pax_note": pax_note,
                "status": record.status,
                "status_label": COMPARISON_STATUS_LABELS.get(record.status, record.status),
                "done": record.done,
                "total": record.total,
                "queries_used": record.queries_used,
                "created_at_label": format_taipei(record.created_at),
                "finished_at_label": (
                    format_taipei(record.finished_at) if record.finished_at else None
                ),
                "error_summary": error_summary,
                "stale": stale,
                "stale_note": comparison_age_note(age_hours) if stale else None,
                "reused_note": (
                    comparison_reused_note(age_hours)
                    if reused and record.status == "done"
                    else None
                ),
                "deferred_note": (
                    COMPARISON_DEFERRED_NOTE if record.status in ("queued", "running") else None
                ),
            },
            "rows": [
                self._row(record, c, pax_note) for c in comparison_order(cells, spec.currency)
            ],
            "order_note": COMPARISON_ORDER_NOTE,
            "no_price_note": COMPARISON_NO_PRICE_NOTE,
            "single_date_note": COMPARISON_SINGLE_DATE_NOTE,
            "reference_note": COMPARISON_REFERENCE_NOTE,
            "disclaimer": DISCLAIMER,
        }

    def _booking(self, record: ComparisonRecord, destination: str) -> tuple[str, str | None]:
        spec = record.spec
        search = search_for(spec.target(destination), spec.pair, spec.currency)
        url = safe_booking_url(self._links, search)
        if url:
            return url, None
        fallback = google_flights_url(spec.origin, destination, spec.depart_date, spec.return_date)
        return fallback, BOOKING_FALLBACK_NOTE

    def _row(
        self, record: ComparisonRecord, cell: ComparisonCellRecord, pax_note: str
    ) -> dict[str, Any]:
        priced = bool(cell.status == "ok" and cell.amount_minor is not None and cell.currency)
        booking_url: str | None = None
        booking_note: str | None = None
        watch_url: str | None = None
        if cell.status != "skipped":
            # Not queried rows get neither link: there is nothing to check (FR-S3, FR-W1).
            booking_url, booking_note = self._booking(record, cell.destination)
            watch_url = f"/watches/new?from_comparison={record.id}&destination={cell.destination}"
        return {
            "position": cell.position,
            "destination": cell.destination,
            "destination_label": place_label(cell.destination),
            "status": cell.status,
            "label": row_label(cell),
            "priced": priced,
            "amount_label": (
                format_money(cell.amount_minor or 0, cell.currency or record.spec.currency)
                if priced
                else None
            ),
            "pax_note": pax_note if priced else None,
            "rank_note": (
                COMPARISON_ROW_LABELS["currency_mismatch"]
                if cell.status == "ok" and cell.reason == "currency_mismatch"
                else None
            ),
            "carrier": cell.carrier if priced else None,
            "stops_label": stops_label(cell.stops) if priced else None,
            "duration_label": flight_duration_label(cell.duration_minutes) if priced else None,
            "depart_time": cell.depart_time if priced else None,
            "fetched_at_label": format_taipei(cell.fetched_at) if cell.fetched_at else None,
            "booking_url": booking_url,
            "booking_note": booking_note,
            "watch_url": watch_url,
        }

    # ---- new-watch prefill -------------------------------------------------------------

    def watch_prefill(
        self, base: dict[str, Any], comparison_id: str | None, destination: str | None
    ) -> tuple[dict[str, Any], str, str | None]:
        """Form values from one comparison row (nothing is written; FR-W1).

        Returns (values, note, None); an unknown id, a destination outside the
        comparison or a skipped row gives the blank form with the "not found" note.
        """
        record = self._record(comparison_id)
        code = (destination or "").strip().upper()
        if record is None or code not in record.spec.destinations:
            return base, COMPARISON_PREFILL_MISSING, None
        cells = self._repo.comparison_cells(record.id)
        cell = next((c for c in cells if c.destination == code), None)
        if cell is None or cell.status == "skipped":
            return base, COMPARISON_PREFILL_MISSING, None
        spec = record.spec
        values = dict(base)
        values.update(
            origin=spec.origin,
            origin_label=place_label(spec.origin),
            destination=code,
            destination_label=place_label(code),
            trip_type=spec.trip_type,
            date_mode="fixed",
            depart_date=spec.depart_date.isoformat(),
            return_date=_iso(spec.return_date),
            window_start="",
            window_end="",
            min_trip_days="",
            max_trip_days="",
            max_stops="" if spec.max_stops is None else str(spec.max_stops),
            adults=spec.adults,
            children=spec.children,
            cabin=spec.cabin,
            airlines=[],
            dep_hour_from=None,
            dep_hour_to=None,
            budget="",
            name="",
        )
        return values, COMPARISON_PREFILL_OK, None

    def _record(self, comparison_id: str | None) -> ComparisonRecord | None:
        text = (comparison_id or "").strip()
        if not text.isdecimal() or len(text) > 12:
            return None
        return self._repo.get_comparison(int(text))


def _conditions(record: ComparisonRecord) -> str:
    spec = record.spec
    return f"{comparison_stops_label(spec.max_stops)}｜{cabin_label(spec.cabin)}"


def _iso(value: date | None) -> str:
    return value.isoformat() if value else ""

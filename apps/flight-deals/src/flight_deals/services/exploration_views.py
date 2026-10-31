"""Read models of the exploration pages (ADR-0002 FD-6 Decisions 5-7), zh-TW, ready to
render. Price levels come from ``views.price_levels`` (one definition for both pages)."""

from __future__ import annotations

from collections.abc import Mapping
from datetime import date, timedelta
from typing import Any

from flight_deals.domain.airports import place_label, route_label
from flight_deals.domain.currency import format_money
from flight_deals.domain.dates import month_days, month_weekday_counts, month_weeks
from flight_deals.domain.links import google_flights_url
from flight_deals.domain.messages import (
    DISCLAIMER,
    EXPLORATION_CELL_LABELS,
    EXPLORATION_DONE_WITH_GAPS,
    EXPLORATION_MAX_SPAN_MONTHS,
    EXPLORATION_MONTH_WATCH_BUTTON,
    EXPLORATION_PREFILL_MISSING,
    EXPLORATION_PREFILL_OK,
    EXPLORATION_RANGE_WATCH_BUTTON,
    EXPLORATION_REFERENCE_NOTE,
    EXPLORATION_STALE_FALLBACK,
    EXPLORATION_STATUS_LABELS,
    EXPLORATION_TOO_MANY_CELLS,
    EXPLORATION_TOP_SCOPE_NOTE,
    TRIP_TYPE_LABELS,
    exploration_age_note,
    exploration_sampled_note,
    exploration_unfinished_note,
    month_label,
    month_range_label,
)
from flight_deals.domain.models import CABINS, DatePair, ExplorationSpec, search_for
from flight_deals.domain.timeutil import format_taipei, taipei_date, weekday_label
from flight_deals.domain.trip_labels import (
    BOOKING_FALLBACK_NOTE,
    NO_LIMIT,
    cabin_label,
    conditions_label,
    depart_weekdays_label,
    total_price_note,
)
from flight_deals.domain.validation import MAX_DAYS_AHEAD, exploration_months
from flight_deals.domain.weekdays import ALL_WEEKDAYS
from flight_deals.ports import BookingLinkBuilder, Clock
from flight_deals.services.exploration import ExplorationService
from flight_deals.services.notifications import safe_booking_url
from flight_deals.services.settings import SettingsService
from flight_deals.services.views import (
    NO_EMBEDDED_REASON,
    NO_MATCH_LABEL,
    ViewService,
    active_comparison_view,
    active_exploration_view,
    price_levels,
)
from flight_deals.storage.repository import (
    ExplorationCellRecord,
    ExplorationRecord,
    Repository,
)

TOP_COUNT = 5
LIST_DAYS = 7
STALE_HOURS = 24
LEVEL_TEXT = {"cheap": "低", "mid": "中", "pricey": "高"}
DEFAULT_TRIP_DAYS = 5


def stops_label(stops: int | None) -> str | None:
    if stops is None:
        return None
    return "直飛" if stops == 0 else f"轉機 {stops} 次"


def max_stops_label(max_stops: int | None) -> str | None:
    if max_stops is None:
        return None
    return "僅直飛" if max_stops == 0 else f"最多轉機 {max_stops} 次"


def exploration_conditions(spec: ExplorationSpec) -> str:
    """Stops, airline / hour filters and weekdays, e.g. "僅直飛｜長榮｜週五、週六出發";
    "不限" with none of them (all weekdays add nothing)."""
    filters = conditions_label(spec.airlines, spec.dep_hour_from, spec.dep_hour_to)
    parts = [
        part
        for part in (
            max_stops_label(spec.max_stops),
            None if filters == NO_LIMIT else filters,
            depart_weekdays_label(spec.depart_weekdays),
        )
        if part is not None
    ]
    return "｜".join(parts) or NO_LIMIT


def spec_month_label(spec: ExplorationSpec) -> str:
    """ "2026 年 12 月", or "2026 年 12 月～2027 年 2 月" for a range."""
    end_year, end_month = spec.end
    return month_range_label(spec.year, spec.month, end_year, end_month)


def has_filters(spec: ExplorationSpec) -> bool:
    return bool(spec.airlines) or spec.dep_hour_from is not None


def cell_label(cell: ExplorationCellRecord, filtered: bool) -> str:
    """Status text of a calendar cell; never blank or 0 (FR-S2)."""
    labels = EXPLORATION_CELL_LABELS
    if cell.status == "ok":
        return labels["currency_mismatch"] if cell.reason == "currency_mismatch" else labels["ok"]
    if cell.status == "no_data":
        if cell.reason == NO_EMBEDDED_REASON:
            return labels["no_embedded_results"]
        return NO_MATCH_LABEL if filtered else labels["no_data"]
    if cell.status == "skipped":
        return labels.get(cell.reason or "", labels["interrupted"])
    return labels.get(cell.status, cell.status)


def rankable(cell: ExplorationCellRecord, currency: str) -> bool:
    """Priced, same currency, no mismatch: the only cells ranked and levelled."""
    return (
        cell.status == "ok"
        and cell.amount_minor is not None
        and cell.reason != "currency_mismatch"
        and cell.currency == currency
    )


class ExplorationViewService:
    def __init__(
        self,
        repo: Repository,
        settings: SettingsService,
        explorations: ExplorationService,
        *,
        clock: Clock,
        link_builder: BookingLinkBuilder | None = None,
    ) -> None:
        self._repo = repo
        self._settings = settings
        self._explorations = explorations
        self._clock = clock
        self._links = link_builder

    # ---- explore page ----------------------------------------------------------

    def explore_page(self) -> dict[str, Any]:
        now = self._clock()
        today = taipei_date(now)
        months = exploration_months(today)
        default_year, default_month = months[1] if len(months) > 1 else months[0]
        quota = self._explorations.quota()
        values = {
            "origin": "TPE",
            "origin_label": place_label("TPE"),
            "destination": "",
            "destination_label": "",
            "trip_type": "round_trip",
            "month": f"{default_year:04d}-{default_month:02d}",
            "month_to": f"{default_year:04d}-{default_month:02d}",
            "depart_weekdays": list(ALL_WEEKDAYS),
            "trip_days": DEFAULT_TRIP_DAYS,
            "max_stops": "",
            "adults": 1,
            "children": 0,
            "cabin": CABINS[0],
            "airlines": [],
            "dep_hour_from": None,
            "dep_hour_to": None,
        }
        return {
            "values": values,
            **ViewService.form_options(values),
            "month_options": [
                {"value": f"{y:04d}-{m:02d}", "label": month_label(y, m)} for y, m in months
            ],
            "max_months": EXPLORATION_MAX_SPAN_MONTHS,
            "over_limit_text": EXPLORATION_TOO_MANY_CELLS,
            "quota": {
                "hourly_left": quota.hourly_left,
                "reserve": quota.reserve,
                "max_cells": quota.max_cells,
                # Queryable departure days per weekday (0 = Monday) of each month option;
                # the page only adds them up (FD-10 Decision 8).
                "weekday_counts": {
                    f"{y:04d}-{m:02d}": list(month_weekday_counts(y, m, today)) for y, m in months
                },
            },
            "recent": [
                self._recent_row(r)
                for r in self._repo.list_explorations_since(now - timedelta(days=LIST_DAYS))
            ],
            "active": active_exploration_view(self._repo),
            "active_comparison": active_comparison_view(self._repo),
            "today": today.isoformat(),
            "disclaimer": DISCLAIMER,
        }

    def _status_label(self, record: ExplorationRecord, gaps: bool) -> str:
        if record.status == "done" and gaps:
            return EXPLORATION_DONE_WITH_GAPS
        return EXPLORATION_STATUS_LABELS.get(record.status, record.status)

    def _recent_row(self, record: ExplorationRecord) -> dict[str, Any]:
        spec = record.spec
        cheapest = (
            format_money(record.min_amount_minor, spec.currency)
            + total_price_note(spec.adults, spec.children)
            if record.min_amount_minor is not None
            else None
        )
        return {
            "id": record.id,
            "route_label": route_label(spec.origin, spec.destination),
            "month": spec_month_label(spec),
            "month_value": spec.month_text,
            "trip_type_label": TRIP_TYPE_LABELS[spec.trip_type],
            "conditions_label": exploration_conditions(spec),
            "status": record.status,
            "status_label": self._status_label(
                record, record.status == "done" and record.done < record.total
            ),
            "done": record.done,
            "total": record.total,
            "created_at_label": format_taipei(record.created_at),
            "cheapest_label": cheapest,
        }

    # ---- result page -------------------------------------------------------------

    def exploration_page(self, exploration_id: int) -> dict[str, Any] | None:
        record = self._repo.get_exploration(exploration_id)
        if record is None:
            return None
        spec = record.spec
        now = self._clock()
        cells = self._repo.exploration_cells(record.id)
        by_day = {c.depart_date: c for c in cells}
        created_day = taipei_date(record.created_at)
        filtered = has_filters(spec)
        ranked = [c for c in cells if rankable(c, spec.currency) and c.price_kind == "live"]
        levels = price_levels([(c.depart_date, c.amount_minor or 0) for c in ranked])

        def view(day: date) -> dict[str, Any]:
            return self._cell_view(record, by_day.get(day), day, created_day, levels, filtered)

        calendar_months = [
            {
                "year": year,
                "month": month,
                "label": month_label(year, month),
                "weeks": [
                    [view(d) if d else None for d in week] for week in month_weeks(year, month)
                ],
            }
            for year, month in spec.months
        ]
        weeks = calendar_months[0]["weeks"]
        top = sorted(
            (c for c in cells if rankable(c, spec.currency)),
            key=lambda c: (c.amount_minor or 0, c.depart_date),
        )[:TOP_COUNT]
        top5 = [view(c.depart_date) for c in top]
        gaps = any(c.status == "skipped" for c in cells)
        finished = record.finished_at or record.created_at
        age_hours = int((now - finished).total_seconds() // 3600)
        stale = now - finished > timedelta(hours=STALE_HOURS)
        error_summary = None
        if record.status == "failed" or gaps:
            reason = record.error_summary or EXPLORATION_CELL_LABELS["interrupted"]
            error_summary = exploration_unfinished_note(record.done, record.total, reason)
        settings = self._settings.current()
        return {
            "exploration": {
                "id": record.id,
                "route_label": route_label(spec.origin, spec.destination),
                "month": spec.month_text,
                "month_to": spec.month_to_text,
                "month_label": spec_month_label(spec),
                "weekdays_label": depart_weekdays_label(spec.depart_weekdays),
                "trip_type": spec.trip_type,
                "trip_type_label": TRIP_TYPE_LABELS[spec.trip_type],
                "trip_days": spec.trip_days,
                "pax_note": total_price_note(spec.adults, spec.children),
                "cabin_label": cabin_label(spec.cabin),
                "conditions_label": exploration_conditions(spec),
                "status": record.status,
                "status_label": self._status_label(record, gaps),
                "done": record.done,
                "total": record.total,
                "queries_used": record.queries_used,
                "created_at_label": format_taipei(record.created_at),
                "finished_at_label": (
                    format_taipei(record.finished_at) if record.finished_at else None
                ),
                "error_summary": error_summary,
                "stale": stale,
                "age_hours": age_hours,
                "stale_note": exploration_age_note(age_hours) if stale else None,
                "stale_fallback": EXPLORATION_STALE_FALLBACK,
                "month_watch_url": f"/watches/new?from_exploration={record.id}&mode=month",
                "month_watch_label": (
                    EXPLORATION_MONTH_WATCH_BUTTON
                    if len(spec.months) == 1
                    else EXPLORATION_RANGE_WATCH_BUTTON
                ),
            },
            "calendar_months": calendar_months,
            "weeks": weeks,
            "top5": top5,
            "top_scope_note": EXPLORATION_TOP_SCOPE_NOTE,
            "disclaimer": f"{EXPLORATION_REFERENCE_NOTE}{DISCLAIMER}",
            "sampled_note": exploration_sampled_note(
                settings.max_pairs_per_scan, months=len(spec.months)
            ),
        }

    def _booking(self, spec: ExplorationSpec, pair: DatePair) -> tuple[str, str | None]:
        url = safe_booking_url(self._links, search_for(spec, pair, spec.currency))
        if url:
            return url, None
        fallback = google_flights_url(spec.origin, spec.destination, pair.depart, pair.return_date)
        return fallback, BOOKING_FALLBACK_NOTE

    def _cell_view(
        self,
        record: ExplorationRecord,
        cell: ExplorationCellRecord | None,
        day: date,
        created_day: date,
        levels: Mapping[date, str],
        filtered: bool,
    ) -> dict[str, Any]:
        base: dict[str, Any] = {
            "date": day.isoformat(),
            "day": day.day,
            "weekday_label": weekday_label(day),
            "return_date": None,
            "amount_label": None,
            "carrier": None,
            "stops_label": None,
            "depart_time": None,
            "level": None,
            "booking_url": None,
            "booking_note": None,
            "watch_url": None,
            # Priced but kept out of ranking and levels (e.g. currency mismatch).
            "rank_note": None,
        }
        if cell is None:
            # Off the selected weekdays first, then past, then beyond the query range.
            if day.weekday() not in record.spec.depart_weekdays:
                label = EXPLORATION_CELL_LABELS["weekday_filtered"]
                return {**base, "status": "weekday_filtered", "label": label}
            key = "past" if day < created_day else "out_of_range"
            return {**base, "status": "not_queried", "label": EXPLORATION_CELL_LABELS[key]}
        spec = record.spec
        url, note = self._booking(spec, DatePair(cell.depart_date, cell.return_date))
        level = levels.get(day)
        priced = cell.status == "ok" and cell.amount_minor is not None and cell.currency
        return {
            **base,
            "status": cell.status,
            "label": cell_label(cell, filtered),
            "return_date": cell.return_date.isoformat() if cell.return_date else None,
            "amount_label": (
                format_money(cell.amount_minor or 0, cell.currency or spec.currency)
                if priced
                else None
            ),
            "carrier": cell.carrier if priced else None,
            "stops_label": stops_label(cell.stops) if priced else None,
            "depart_time": cell.depart_time if priced else None,
            "level": LEVEL_TEXT[level] if level else None,
            "rank_note": (
                EXPLORATION_CELL_LABELS["currency_mismatch"]
                if cell.status == "ok" and cell.reason == "currency_mismatch"
                else None
            ),
            "booking_url": url,
            "booking_note": note,
            "watch_url": (f"/watches/new?from_exploration={record.id}&depart={day.isoformat()}"),
        }

    # ---- new-watch prefill -----------------------------------------------------------

    def watch_prefill(
        self,
        base: dict[str, Any],
        exploration_id: str | None,
        depart: str | None,
        mode: str | None,
    ) -> tuple[dict[str, Any], str, str | None]:
        """Form values from an exploration (nothing is written; Decision 6).

        Returns (values, note, sampled_note); an unknown id or a bad date gives the
        blank form with the "not found" note.
        """
        record = self._record(exploration_id)
        if record is None:
            return base, EXPLORATION_PREFILL_MISSING, None
        spec = record.spec
        today = taipei_date(self._clock())
        days = [day for year, month in spec.months for day in month_days(year, month)]
        values = dict(base)
        values.update(
            origin=spec.origin,
            origin_label=place_label(spec.origin),
            destination=spec.destination,
            destination_label=place_label(spec.destination),
            trip_type=spec.trip_type,
            max_stops="" if spec.max_stops is None else str(spec.max_stops),
            adults=spec.adults,
            children=spec.children,
            cabin=spec.cabin,
            airlines=list(spec.airlines),
            dep_hour_from=spec.dep_hour_from,
            dep_hour_to=spec.dep_hour_to,
            budget="",
            name="",
        )
        stay = spec.trip_days if spec.trip_type == "round_trip" else None
        if mode == "month":
            start = max(days[0], today)
            if start > days[-1]:
                return base, EXPLORATION_PREFILL_MISSING, None
            end = days[-1] + timedelta(days=stay or 0)
            end = min(end, today + timedelta(days=MAX_DAYS_AHEAD))
            values.update(
                date_mode="flexible",
                window_start=start.isoformat(),
                window_end=end.isoformat(),
                min_trip_days="" if stay is None else str(stay),
                max_trip_days="" if stay is None else str(stay),
                depart_date="",
                return_date="",
                depart_weekdays=list(spec.depart_weekdays),
            )
            note = exploration_sampled_note(
                self._settings.current().max_pairs_per_scan, months=len(spec.months)
            )
            return values, EXPLORATION_PREFILL_OK, note
        day = _parse_day(depart)
        if day is None or day not in days:
            return base, EXPLORATION_PREFILL_MISSING, None
        values.update(
            date_mode="fixed",
            depart_date=day.isoformat(),
            return_date=(day + timedelta(days=stay)).isoformat() if stay is not None else "",
            window_start="",
            window_end="",
            min_trip_days="",
            max_trip_days="",
        )
        return values, EXPLORATION_PREFILL_OK, None

    def _record(self, exploration_id: str | None) -> ExplorationRecord | None:
        text = (exploration_id or "").strip()
        if not text.isdecimal() or len(text) > 12:
            return None
        return self._repo.get_exploration(int(text))


def _parse_day(text: str | None) -> date | None:
    try:
        return date.fromisoformat((text or "").strip())
    except ValueError:
        return None

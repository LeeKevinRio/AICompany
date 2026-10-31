"""Date-pair expansion, expiry and rotating equidistant sampling.

Departure weekdays (FD-10) only filter the departure day of a flexible window or an
exploration; returns are never filtered and nothing about weekdays reaches a query.
"""

from __future__ import annotations

import calendar
import math
from datetime import date, timedelta

from flight_deals.domain.models import DatePair, ExplorationSpec, WatchSpec
from flight_deals.domain.validation import MAX_DAYS_AHEAD
from flight_deals.domain.weekdays import is_all_weekdays

# Defensive cap for specs that bypassed validation (validation allows at most 366 days).
MAX_EXPAND_SPAN_DAYS = 366


def _days(start: date, end: date) -> list[date]:
    return [start + timedelta(days=i) for i in range((end - start).days + 1)]


def expand_pairs(spec: WatchSpec, today: date) -> list[DatePair]:
    """All (depart, return) pairs still in the future (depart >= today), sorted.

    Fixed dates and an all-weekdays window take the unfiltered path unchanged; otherwise
    only departures on the selected weekdays are kept (returns are not filtered).
    """
    if spec.date_mode == "flexible" and not is_all_weekdays(spec.depart_weekdays):
        return _expand_filtered(spec, today)
    return _expand_all(spec, today)


def _expand_filtered(spec: WatchSpec, today: date) -> list[DatePair]:
    """``_expand_all`` restricted to departures on the selected weekdays (same order)."""
    if spec.window_start is None or spec.window_end is None:
        return []
    first = max(spec.window_start, today)
    if first > spec.window_end:
        return []
    end = min(spec.window_end, first + timedelta(days=MAX_EXPAND_SPAN_DAYS))
    allowed = set(spec.depart_weekdays)
    departs = [day for day in _days(first, end) if day.weekday() in allowed]
    if spec.trip_type == "one_way":
        return [DatePair(day) for day in departs]

    low = spec.min_trip_days or 0
    high = spec.max_trip_days if spec.max_trip_days is not None else low
    pairs: list[DatePair] = []
    for depart in departs:
        for length in range(low, high + 1):
            ret = depart + timedelta(days=length)
            if ret <= end:
                pairs.append(DatePair(depart, ret))
    return sorted(pairs)


def _expand_all(spec: WatchSpec, today: date) -> list[DatePair]:
    if spec.date_mode == "fixed":
        if spec.depart_date is None or spec.depart_date < today:
            return []
        ret = spec.return_date if spec.trip_type == "round_trip" else None
        return [DatePair(spec.depart_date, ret)]

    if spec.window_start is None or spec.window_end is None:
        return []
    first = max(spec.window_start, today)
    if first > spec.window_end:
        return []
    end = min(spec.window_end, first + timedelta(days=MAX_EXPAND_SPAN_DAYS))
    if spec.trip_type == "one_way":
        return [DatePair(day) for day in _days(first, end)]

    low = spec.min_trip_days or 0
    high = spec.max_trip_days if spec.max_trip_days is not None else low
    pairs: list[DatePair] = []
    for depart in _days(first, end):
        for length in range(low, high + 1):
            ret = depart + timedelta(days=length)
            if ret <= end:
                pairs.append(DatePair(depart, ret))
    return sorted(pairs)


def first_pair(spec: WatchSpec, today: date) -> DatePair | None:
    """The earliest pair ``expand_pairs`` would yield, computed in constant time.

    With a weekday filter at most 7 candidate departure days are checked: the earliest
    one on a selected weekday is the first departure, if any pair fits from it.
    """
    if spec.date_mode == "flexible" and not is_all_weekdays(spec.depart_weekdays):
        return _first_filtered(spec, today)
    return _first_all(spec, today)


def _first_filtered(spec: WatchSpec, today: date) -> DatePair | None:
    if spec.window_start is None or spec.window_end is None:
        return None
    first = max(spec.window_start, today)
    # Same span cap as ``_expand_filtered``, so both agree for any spec.
    end = min(spec.window_end, first + timedelta(days=MAX_EXPAND_SPAN_DAYS))
    allowed = set(spec.depart_weekdays)
    for offset in range(7):
        depart = first + timedelta(days=offset)
        if depart > end:
            return None
        if depart.weekday() not in allowed:
            continue
        if spec.trip_type == "one_way":
            return DatePair(depart)
        # Later departures only leave less room, so this one decides.
        ret = depart + timedelta(days=spec.min_trip_days or 0)
        return DatePair(depart, ret) if ret <= end else None
    return None


def _first_all(spec: WatchSpec, today: date) -> DatePair | None:
    if spec.date_mode == "fixed":
        if spec.depart_date is None or spec.depart_date < today:
            return None
        ret = spec.return_date if spec.trip_type == "round_trip" else None
        return DatePair(spec.depart_date, ret)
    if spec.window_start is None or spec.window_end is None:
        return None
    first = max(spec.window_start, today)
    if first > spec.window_end:
        return None
    if spec.trip_type == "one_way":
        return DatePair(first)
    # The shortest stay from the earliest departure is the first pair, if it fits.
    ret = first + timedelta(days=spec.min_trip_days or 0)
    return DatePair(first, ret) if ret <= spec.window_end else None


def is_expired(spec: WatchSpec, today: date) -> bool:
    """True when no future date pair remains (constant time, no expansion)."""
    return first_pair(spec, today) is None


def weekday_filter_leaves_nothing(spec: WatchSpec, today: date) -> bool:
    """True when the weekday filter alone empties a window that has pairs (AC-D5)."""
    if spec.date_mode != "flexible" or is_all_weekdays(spec.depart_weekdays):
        return False
    return _first_filtered(spec, today) is None and _first_all(spec, today) is not None


def sample_pairs(
    pairs: list[DatePair], limit: int, offset: int
) -> tuple[list[DatePair], int, bool]:
    """Pick at most ``limit`` pairs evenly spread over ``pairs``.

    Returns ``(sampled, next_offset, truncated)``. When truncated, each scan shifts the
    picks by one position so that coverage accumulates across scans.
    """
    total = len(pairs)
    if limit <= 0:
        return [], offset, total > 0
    if total <= limit:
        return list(pairs), 0, False
    step = math.ceil(total / limit)
    shift = offset % step
    indices = sorted({((i * total) // limit + shift) % total for i in range(limit)})
    return [pairs[i] for i in indices], (shift + 1) % step, True


# ---- exploration months (ADR-0002 FD-6 Decision 2) ---------------------------------

MAX_MONTH_CELLS = 31


def month_days(year: int, month: int) -> list[date]:
    last = calendar.monthrange(year, month)[1]
    return [date(year, month, day) for day in range(1, last + 1)]


def range_months(spec: ExplorationSpec) -> list[tuple[int, int]]:
    """(year, month) from the start month to the end month inclusive."""
    return spec.months


def range_pairs(spec: ExplorationSpec, today: date) -> list[DatePair]:
    """One pair per queryable departure day over the month range, month by month.

    Days before ``today`` (Asia/Taipei) or off the selected weekdays are skipped; a
    round trip returns on departure + ``trip_days`` (may fall in the next month).
    Departures or returns past the query horizon (today + MAX_DAYS_AHEAD) are skipped
    as well. Never truncated: the service rejects more than the cell limit.
    """
    horizon = today + timedelta(days=MAX_DAYS_AHEAD)
    allowed = set(spec.depart_weekdays)
    pairs: list[DatePair] = []
    for year, month in range_months(spec):
        for day in month_days(year, month):
            if day < today or day > horizon or day.weekday() not in allowed:
                continue
            if spec.trip_type == "round_trip":
                ret = day + timedelta(days=spec.trip_days or 0)
                if ret > horizon:
                    continue
                pairs.append(DatePair(day, ret))
            else:
                pairs.append(DatePair(day))
    return pairs


def month_pairs(spec: ExplorationSpec, today: date) -> list[DatePair]:
    """Legacy wrapper kept for the FD-6 tests only; services call ``range_pairs``."""
    return range_pairs(spec, today)[:MAX_MONTH_CELLS]


def month_weekday_counts(
    year: int, month: int, today: date
) -> tuple[int, int, int, int, int, int, int]:
    """Queryable departure days of one month per weekday (index 0 = Monday).

    Counts days from ``today`` up to the query horizon; the return-date horizon check
    of ``range_pairs`` is left out, so the estimate may only over-count.
    """
    horizon = today + timedelta(days=MAX_DAYS_AHEAD)
    counts = [0] * 7
    for day in month_days(year, month):
        if today <= day <= horizon:
            counts[day.weekday()] += 1
    return (counts[0], counts[1], counts[2], counts[3], counts[4], counts[5], counts[6])


def month_weeks(year: int, month: int) -> list[list[date | None]]:
    """Calendar rows starting on Monday; days outside the month are None."""
    weeks = calendar.Calendar(firstweekday=0).monthdatescalendar(year, month)
    return [[day if day.month == month else None for day in week] for week in weeks]

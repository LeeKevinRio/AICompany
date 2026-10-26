"""Date-pair expansion, expiry and rotating equidistant sampling."""

from __future__ import annotations

import math
from datetime import date, timedelta

from flight_deals.domain.models import DatePair, WatchSpec

# Defensive cap for specs that bypassed validation (validation allows at most 366 days).
MAX_EXPAND_SPAN_DAYS = 366


def _days(start: date, end: date) -> list[date]:
    return [start + timedelta(days=i) for i in range((end - start).days + 1)]


def expand_pairs(spec: WatchSpec, today: date) -> list[DatePair]:
    """All (depart, return) pairs still in the future (depart >= today), sorted."""
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
    """The earliest pair ``expand_pairs`` would yield, computed in constant time."""
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

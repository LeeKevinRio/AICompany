"""Departure weekday sets (ADR-0002 FD-10 Decision 2).

Weekdays are ``date.weekday()`` integers, 0 = Monday ... 6 = Sunday. The database stores
a set as a bitmask (bit ``d`` set = weekday ``d`` selected); 127 = every weekday, which
also means "no weekday filter". Standard library only.
"""

from __future__ import annotations

from collections.abc import Iterable

ALL_WEEKDAYS: tuple[int, ...] = (0, 1, 2, 3, 4, 5, 6)
ALL_WEEKDAYS_MASK: int = 127


def normalize_weekdays(values: Iterable[int]) -> tuple[int, ...]:
    """Sorted, de-duplicated weekdays; ValueError when empty or any value is not 0..6."""
    items = list(values)
    for value in items:
        if isinstance(value, bool) or not isinstance(value, int) or not 0 <= value <= 6:
            raise ValueError(f"weekday out of range: {value!r}")
    if not items:
        raise ValueError("at least one weekday is required")
    return tuple(sorted(set(items)))


def weekdays_to_mask(weekdays: Iterable[int]) -> int:
    return sum(1 << day for day in normalize_weekdays(weekdays))


def weekdays_from_mask(mask: int) -> tuple[int, ...]:
    if isinstance(mask, bool) or not isinstance(mask, int) or not 1 <= mask <= ALL_WEEKDAYS_MASK:
        raise ValueError(f"weekday mask out of range: {mask!r}")
    return tuple(day for day in ALL_WEEKDAYS if mask & (1 << day))


def is_all_weekdays(weekdays: Iterable[int]) -> bool:
    return set(weekdays) == set(ALL_WEEKDAYS)

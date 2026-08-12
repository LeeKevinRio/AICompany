"""Trading calendar and schedule days (週二／四) for the playbook.

Two facts the rule set needs and the product did not have yet:

* **Which days are trading days.** Every "N 交易日" in the rule set (黑名單 60、
  S3 凍結 10、P3 冷卻 10、EMERGENCY 20) counts trading days, and T+1 execution
  needs the *next* one. The calendar is built from dates the market actually
  produced bars on, so a holiday is absent because no bar exists, not because a
  hard-coded holiday table said so.
* **Which days are schedule days.** 週二／四 that are also trading days. A
  Tuesday the exchange was closed is not a schedule day and is not moved to
  another weekday: the rule set names the weekday, not "twice a week".

Dates beyond the known bar range fall back to the weekday test (Mon-Fri), which
is what a forward-looking 預定執行日 needs before that day's bars exist. The
fallback is stated in :meth:`TradingCalendar.is_trading_day` rather than hidden,
because it is the one place the calendar answers from a rule instead of from an
observation.
"""

from __future__ import annotations

from collections.abc import Iterable
from datetime import date, timedelta

#: Monday is 0 in ``date.weekday()``; the rule set's 排程日 are 週二 and 週四.
SCHEDULE_WEEKDAYS: frozenset[int] = frozenset({1, 3})

#: How far the day-stepping helpers may walk before giving up. A year of
#: calendar days is far past any gap a real exchange takes.
_MAX_STEP_DAYS = 400


class TradingCalendar:
    """Trading days observed from bar dates, with a weekday fallback."""

    def __init__(self, trading_days: Iterable[date]) -> None:
        self._days = frozenset(trading_days)
        self._last_known = max(self._days) if self._days else None
        self._first_known = min(self._days) if self._days else None

    @property
    def known_range(self) -> tuple[date, date] | None:
        """First and last observed trading day, or ``None`` when empty."""
        if self._first_known is None or self._last_known is None:
            return None
        return self._first_known, self._last_known

    def is_trading_day(self, day: date) -> bool:
        """``True`` if the market traded (or, outside the observed range, would).

        Inside the observed range the answer is an observation: the day either
        produced bars or it did not. Outside it -- typically a future date such
        as the 預定執行日 -- the answer is the weekday rule, which cannot know
        about a holiday that has not happened yet.
        """
        if self._first_known is not None and self._last_known is not None:
            if self._first_known <= day <= self._last_known:
                return day in self._days
        return day.weekday() < 5

    def is_schedule_day(self, day: date) -> bool:
        """週二／四 **and** a trading day."""
        return day.weekday() in SCHEDULE_WEEKDAYS and self.is_trading_day(day)

    def next_trading_day(self, day: date) -> date:
        """The first trading day strictly after ``day`` (the 預定執行日 for T)."""
        return self.shift(day, 1)

    def next_schedule_day(self, day: date) -> date:
        """The first 排程日 strictly after ``day``."""
        cursor = day
        for _ in range(_MAX_STEP_DAYS):
            cursor += timedelta(days=1)
            if self.is_schedule_day(cursor):
                return cursor
        raise ValueError(f"no schedule day found within {_MAX_STEP_DAYS} days of {day}")

    def shift(self, day: date, trading_days: int) -> date:
        """``day`` moved by ``trading_days`` trading days (may be negative).

        ``shift(d, 0)`` returns ``d`` untouched even if ``d`` is not a trading
        day: zero means "no move", not "snap to the nearest session".
        """
        if trading_days == 0:
            return day
        step = timedelta(days=1 if trading_days > 0 else -1)
        remaining = abs(trading_days)
        cursor = day
        for _ in range(_MAX_STEP_DAYS):
            cursor += step
            if self.is_trading_day(cursor):
                remaining -= 1
                if remaining == 0:
                    return cursor
        raise ValueError(f"could not shift {day} by {trading_days} trading days")

    def trading_days_between(self, start: date, end: date) -> int:
        """Trading days in ``(start, end]`` -- 0 when ``end <= start``.

        Used by the cooldown checks ("每 10 交易日限一次"), which ask how far
        back the last firing was, so the starting day itself is excluded.
        """
        if end <= start:
            return 0
        count = 0
        cursor = start
        while cursor < end:
            cursor += timedelta(days=1)
            if self.is_trading_day(cursor):
                count += 1
        return count

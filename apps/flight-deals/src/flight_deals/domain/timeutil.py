"""Time helpers.

Timestamps are timezone-aware UTC and stored as ISO 8601. Travel dates are local
calendar dates (``datetime.date``) and are never converted between time zones.
"""

from __future__ import annotations

from datetime import UTC, date, datetime
from zoneinfo import ZoneInfo

TAIPEI = ZoneInfo("Asia/Taipei")


def utc_now() -> datetime:
    return datetime.now(UTC)


def to_utc_iso(moment: datetime) -> str:
    if moment.tzinfo is None:
        raise ValueError("naive datetime is not allowed for timestamps")
    return moment.astimezone(UTC).isoformat(timespec="seconds")


def parse_utc_iso(text: str) -> datetime:
    moment = datetime.fromisoformat(text)
    if moment.tzinfo is None:
        raise ValueError(f"timestamp without timezone: {text!r}")
    return moment.astimezone(UTC)


def taipei_date(moment: datetime) -> date:
    """Calendar date in Asia/Taipei for an aware timestamp (used for 'today')."""
    if moment.tzinfo is None:
        raise ValueError("naive datetime is not allowed for timestamps")
    return moment.astimezone(TAIPEI).date()


def format_taipei(moment: datetime | None) -> str:
    if moment is None:
        return ""
    return moment.astimezone(TAIPEI).strftime("%Y-%m-%d %H:%M")


def parse_travel_date(text: str) -> date:
    return date.fromisoformat(text)


def format_travel_date(day: date) -> str:
    return day.strftime("%m/%d")


WEEKDAY_LABELS = ("一", "二", "三", "四", "五", "六", "日")


def weekday_label(day: date) -> str:
    return "週" + WEEKDAY_LABELS[day.weekday()]

"""``is_final`` (ADR-0030 D-3 point 2; ADR-0028 CS-17).

A bar of session ``d`` is final when the earliest of its stamps is at or after
``d`` 15:00 Asia/Taipei (``TW_POLICY.publish_cutoff``); no stamp, a ``None``
stamp or a naive stamp is not final.
"""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta
from zoneinfo import ZoneInfo

import pytest

from app.data.freshness import TW_POLICY, US_POLICY
from app.data.session_calendar import is_final

TAIPEI = ZoneInfo("Asia/Taipei")
NEW_YORK = ZoneInfo("America/New_York")
T = date(2026, 11, 13)
CUTOFF = datetime(2026, 11, 13, 15, 0, tzinfo=TAIPEI)
JUST_BEFORE = CUTOFF - timedelta(microseconds=1)


def test_the_cutoff_is_the_policy_value_not_a_copy() -> None:
    assert TW_POLICY.publish_cutoff.hour == 15
    assert TW_POLICY.timezone == "Asia/Taipei"


def test_exactly_at_the_cutoff_is_final() -> None:
    assert is_final("TW", T, CUTOFF) is True


def test_one_microsecond_before_the_cutoff_is_not_final() -> None:
    assert is_final("TW", T, JUST_BEFORE) is False


def test_the_cutoff_in_utc_is_the_same_instant() -> None:
    utc_cutoff = datetime(2026, 11, 13, 7, 0, tzinfo=UTC)
    assert is_final("TW", T, utc_cutoff) is True
    assert is_final("TW", T, utc_cutoff - timedelta(microseconds=1)) is False


def test_the_earliest_stamp_decides() -> None:
    later = CUTOFF + timedelta(hours=3)
    assert is_final("TW", T, later, CUTOFF) is True
    assert is_final("TW", T, later, JUST_BEFORE) is False
    assert is_final("TW", T, JUST_BEFORE, later) is False


def test_a_later_day_is_final_and_an_earlier_one_is_not() -> None:
    assert is_final("TW", T, CUTOFF + timedelta(days=1)) is True
    assert is_final("TW", T, datetime(2026, 11, 12, 23, 0, tzinfo=TAIPEI)) is False


def test_the_cutoff_belongs_to_the_session_date_not_to_the_stamp_date() -> None:
    # 15:00 on T-1 is before T's cutoff, even though it is past a 15:00.
    assert is_final("TW", T, datetime(2026, 11, 12, 15, 0, tzinfo=TAIPEI)) is False


def test_no_stamp_is_not_final() -> None:
    assert is_final("TW", T) is False


def test_a_none_stamp_is_not_final() -> None:
    assert is_final("TW", T, CUTOFF, None) is False
    assert is_final("TW", T, None) is False


def test_a_naive_stamp_is_not_final() -> None:
    naive = datetime(2026, 11, 13, 20, 0)
    assert is_final("TW", T, naive) is False
    assert is_final("TW", T, CUTOFF, naive) is False


def test_us_uses_its_own_policy() -> None:
    cutoff = datetime.combine(T, US_POLICY.publish_cutoff, NEW_YORK)
    assert is_final("US", T, cutoff) is True
    assert is_final("US", T, cutoff - timedelta(microseconds=1)) is False


def test_a_datetime_trade_date_is_refused() -> None:
    with pytest.raises(TypeError):
        is_final("TW", datetime(2026, 11, 13, 0, 0), CUTOFF)

"""ADR-0009: the daily-bar cache is fresh by *session*, not by clock.

The one question layer 0 asks is "has the market completed and published a
session this cache does not hold?" -- these tests pin the calendar arithmetic
(weekends, publish cutoff, the requested end date) and the three verdicts.
"""

from __future__ import annotations

from datetime import UTC, date, datetime, time, timedelta
from zoneinfo import ZoneInfo

import pytest

from app.data.freshness import (
    TW_POLICY,
    US_POLICY,
    SessionFreshnessPolicy,
    Verdict,
    judge,
    next_weekday,
    policy_for,
)

_TAIPEI = ZoneInfo("Asia/Taipei")
_NY = ZoneInfo("America/New_York")


def _taipei(y: int, m: int, d: int, hh: int, mm: int = 0) -> datetime:
    return datetime(y, m, d, hh, mm, tzinfo=_TAIPEI)


# --- latest completed session --------------------------------------------------


def test_before_the_cutoff_the_latest_session_is_yesterday() -> None:
    # Tuesday 2026-09-08 14:59 Taipei: today's close is not published yet.
    assert TW_POLICY.latest_completed_session(_taipei(2026, 9, 8, 14, 59)) == date(2026, 9, 7)


def test_at_the_cutoff_today_counts() -> None:
    assert TW_POLICY.latest_completed_session(_taipei(2026, 9, 8, 15, 0)) == date(2026, 9, 8)


def test_weekends_step_back_to_friday() -> None:
    # 2026-09-12 is a Saturday, 2026-09-13 a Sunday.
    assert TW_POLICY.latest_completed_session(_taipei(2026, 9, 12, 10)) == date(2026, 9, 11)
    assert TW_POLICY.latest_completed_session(_taipei(2026, 9, 13, 23)) == date(2026, 9, 11)


def test_monday_morning_is_still_friday() -> None:
    assert TW_POLICY.latest_completed_session(_taipei(2026, 9, 14, 9)) == date(2026, 9, 11)


def test_the_cutoff_is_read_on_the_exchange_clock_not_utc() -> None:
    # 08:00 UTC on Tuesday is 16:00 Taipei (past cutoff) but 04:00 New York.
    moment = datetime(2026, 9, 8, 8, 0, tzinfo=UTC)
    assert TW_POLICY.latest_completed_session(moment) == date(2026, 9, 8)
    assert US_POLICY.latest_completed_session(moment) == date(2026, 9, 7)  # Monday


def test_policies_per_market() -> None:
    assert policy_for("TW") is TW_POLICY and policy_for("US") is US_POLICY
    # The US cooldown is a full day on purpose (Alpha Vantage 25 req/day).
    assert US_POLICY.recheck_cooldown == timedelta(hours=24)
    assert TW_POLICY.recheck_cooldown == timedelta(hours=1)


# --- verdicts ---------------------------------------------------------------------


_POLICY = SessionFreshnessPolicy(
    timezone="Asia/Taipei", publish_cutoff=time(15, 0), recheck_cooldown=timedelta(hours=1)
)


def test_a_cache_holding_the_latest_session_is_served_whatever_its_age() -> None:
    # Fetched Friday evening, read Sunday: nothing can have changed.
    verdict = judge(
        _POLICY,
        last_bar_date=date(2026, 9, 11),
        last_checked_at=_taipei(2026, 9, 11, 18),
        requested_end=date(2026, 9, 13),
        now=_taipei(2026, 9, 13, 20),
    )
    assert verdict is Verdict.HAS_LATEST_SESSION


def test_a_new_session_nobody_has_checked_means_refetch() -> None:
    # Monday 16:00: the market traded today and the cache stops at Friday.
    verdict = judge(
        _POLICY,
        last_bar_date=date(2026, 9, 11),
        last_checked_at=_taipei(2026, 9, 11, 18),
        requested_end=date(2026, 9, 14),
        now=_taipei(2026, 9, 14, 16),
    )
    assert verdict is Verdict.REFETCH


def test_a_recent_live_check_that_found_nothing_newer_is_honoured() -> None:
    # Same Monday, but a live source was asked twenty minutes ago (holiday or
    # not-yet-published close): serve the cache, disclosed as short.
    verdict = judge(
        _POLICY,
        last_bar_date=date(2026, 9, 11),
        last_checked_at=_taipei(2026, 9, 14, 15, 40),
        requested_end=date(2026, 9, 14),
        now=_taipei(2026, 9, 14, 16),
    )
    assert verdict is Verdict.CHECKED_RECENTLY


def test_the_cooldown_expires() -> None:
    verdict = judge(
        _POLICY,
        last_bar_date=date(2026, 9, 11),
        last_checked_at=_taipei(2026, 9, 14, 15, 0),
        requested_end=date(2026, 9, 14),
        now=_taipei(2026, 9, 14, 16, 1),
    )
    assert verdict is Verdict.REFETCH


def test_a_historical_range_never_expects_todays_session() -> None:
    # Asking for history that ends last month: the cache cannot be missing today.
    verdict = judge(
        _POLICY,
        last_bar_date=date(2026, 8, 31),
        last_checked_at=_taipei(2026, 9, 1, 9),
        requested_end=date(2026, 8, 31),
        now=_taipei(2026, 9, 14, 16),
    )
    assert verdict is Verdict.HAS_LATEST_SESSION


def test_a_range_ending_on_a_weekend_expects_the_friday() -> None:
    verdict = judge(
        _POLICY,
        last_bar_date=date(2026, 9, 11),
        last_checked_at=_taipei(2026, 9, 11, 18),
        requested_end=date(2026, 9, 12),  # Saturday
        now=_taipei(2026, 9, 14, 16),
    )
    assert verdict is Verdict.HAS_LATEST_SESSION


@pytest.mark.parametrize("weekday_offset", [0, 1, 2, 3, 4])
def test_every_weekday_after_the_cutoff_is_its_own_session(weekday_offset: int) -> None:
    day = date(2026, 9, 7) + timedelta(days=weekday_offset)  # Mon..Fri
    moment = datetime.combine(day, time(15, 30), tzinfo=_TAIPEI)
    assert _POLICY.latest_completed_session(moment) == day


def test_ny_cutoff_is_evening_local_time() -> None:
    assert US_POLICY.latest_completed_session(datetime(2026, 9, 8, 17, 59, tzinfo=_NY)) == date(
        2026, 9, 7
    )
    assert US_POLICY.latest_completed_session(datetime(2026, 9, 8, 18, 0, tzinfo=_NY)) == date(
        2026, 9, 8
    )


# --- ADR-0009 R-6: clocks that lie -------------------------------------------------


def test_naive_datetimes_are_refused_not_guessed() -> None:
    with pytest.raises(ValueError):
        judge(
            _POLICY,
            last_bar_date=date(2026, 9, 11),
            last_checked_at=datetime(2026, 9, 11, 18),
            requested_end=date(2026, 9, 14),
            now=_taipei(2026, 9, 14, 16),
        )
    with pytest.raises(ValueError):
        judge(
            _POLICY,
            last_bar_date=date(2026, 9, 11),
            last_checked_at=_taipei(2026, 9, 11, 18),
            requested_end=date(2026, 9, 14),
            now=datetime(2026, 9, 14, 16),
        )


def test_a_last_check_in_the_future_means_refetch_not_a_cooldown_that_never_ends() -> None:
    verdict = judge(
        _POLICY,
        last_bar_date=date(2026, 9, 11),
        last_checked_at=_taipei(2026, 9, 14, 18),  # a clock that was set back
        requested_end=date(2026, 9, 14),
        now=_taipei(2026, 9, 14, 16),
    )
    assert verdict is Verdict.REFETCH


def test_is_within_cooldown_matches_judge_on_the_future_clock() -> None:
    now = _taipei(2026, 9, 14, 16)
    assert _POLICY.is_within_cooldown(now, _taipei(2026, 9, 14, 15, 30)) is True
    assert _POLICY.is_within_cooldown(now, _taipei(2026, 9, 14, 14, 59)) is False
    assert _POLICY.is_within_cooldown(now, _taipei(2026, 9, 14, 18)) is False  # future


def test_every_market_cooldown_is_a_whole_number_of_hours() -> None:
    """ADR-0010 D-3's cooldown sentence prints ``{cooldown_hours} 小時`` by integer
    division; a 90-minute cooldown would be shown as "1 小時" -- a false statement.
    Change the sentence before changing a cooldown to a fraction of an hour."""
    for market in ("TW", "US"):
        seconds = policy_for(market).recheck_cooldown.total_seconds()
        assert seconds % 3600 == 0 and seconds >= 3600, market


def test_next_weekday_skips_the_weekend() -> None:
    assert next_weekday(date(2026, 9, 11)) == date(2026, 9, 14)  # Fri -> Mon
    assert next_weekday(date(2026, 9, 9)) == date(2026, 9, 10)  # Wed -> Thu

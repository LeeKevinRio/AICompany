"""Boundary tests for the intraday session window (W3), frozen clock throughout."""

from __future__ import annotations

from datetime import UTC, date, datetime, time, timedelta, timezone

import pytest

from app.data.calendar import TradingCalendar
from app.data.intraday_session import (
    DEFAULT_CONFIG,
    IntradaySessionConfig,
    SessionPhase,
    classify_session,
)

TAIPEI = timezone(timedelta(hours=8))
MONDAY = date(2026, 10, 5)


def _at(hour: int, minute: int, second: int = 0, *, day: date = MONDAY) -> datetime:
    return datetime(day.year, day.month, day.day, hour, minute, second, tzinfo=TAIPEI)


def test_defaults_are_the_adr_values() -> None:
    assert DEFAULT_CONFIG.open_time == time(9, 0)
    assert DEFAULT_CONFIG.window_end == time(13, 25)
    assert DEFAULT_CONFIG.extension_enabled is False


@pytest.mark.parametrize(
    ("moment", "phase"),
    [
        (_at(0, 0), SessionPhase.BEFORE_OPEN),
        (_at(8, 0), SessionPhase.BEFORE_OPEN),
        (_at(8, 59, 59), SessionPhase.BEFORE_OPEN),
        (_at(9, 0), SessionPhase.INTRADAY),
        (_at(9, 0, 1), SessionPhase.INTRADAY),
        (_at(12, 0), SessionPhase.INTRADAY),
        (_at(13, 24, 59), SessionPhase.INTRADAY),
        (_at(13, 25), SessionPhase.AFTER_WINDOW),
        (_at(13, 30), SessionPhase.AFTER_WINDOW),
        (_at(14, 59, 59), SessionPhase.AFTER_WINDOW),
        (_at(15, 0), SessionPhase.AFTER_WINDOW),
        (_at(23, 59, 59), SessionPhase.AFTER_WINDOW),
    ],
)
def test_weekday_boundaries(moment: datetime, phase: SessionPhase) -> None:
    decision = classify_session(moment)
    assert decision.phase == phase
    assert decision.local_date == MONDAY
    assert decision.quotes_allowed is (phase == SessionPhase.INTRADAY)


def test_after_window_never_allows_quotes_by_default() -> None:
    """CEO ruling: 13:30 until the official close is published shows the prior close."""
    for moment in (_at(13, 25), _at(13, 30), _at(14, 0), _at(14, 59)):
        assert classify_session(moment).quotes_allowed is False


@pytest.mark.parametrize("day", [date(2026, 10, 3), date(2026, 10, 4)])
def test_weekend_is_never_a_session(day: date) -> None:
    decision = classify_session(_at(10, 0, day=day))
    assert decision.phase == SessionPhase.NON_TRADING_DAY
    assert decision.quotes_allowed is False
    assert decision.local_date == day


def test_friday_and_monday_around_the_weekend() -> None:
    friday = classify_session(_at(10, 0, day=date(2026, 10, 2)))
    saturday = classify_session(_at(10, 0, day=date(2026, 10, 3)))
    monday = classify_session(_at(10, 0))
    assert friday.phase == SessionPhase.INTRADAY
    assert saturday.phase == SessionPhase.NON_TRADING_DAY
    assert monday.phase == SessionPhase.INTRADAY


def _calendar_with_holiday() -> TradingCalendar:
    """Observed days around a Tuesday holiday (10/06 absent), range 10/01 - 10/09."""
    days = [date(2026, 10, 1), date(2026, 10, 2), date(2026, 10, 5)]
    days += [date(2026, 10, 7), date(2026, 10, 8), date(2026, 10, 9)]
    return TradingCalendar(days)


def test_known_holiday_is_not_a_session() -> None:
    decision = classify_session(
        _at(10, 0, day=date(2026, 10, 6)), calendar=_calendar_with_holiday()
    )
    assert decision.phase == SessionPhase.NON_TRADING_DAY
    assert decision.quotes_allowed is False


def test_observed_trading_day_is_a_session_with_a_calendar() -> None:
    decision = classify_session(
        _at(10, 0, day=date(2026, 10, 7)), calendar=_calendar_with_holiday()
    )
    assert decision.phase == SessionPhase.INTRADAY


def test_day_beyond_the_observed_range_falls_back_to_the_weekday_rule() -> None:
    """The calendar cannot know today's holiday; that is left to the not_today check."""
    calendar = _calendar_with_holiday()
    weekday = classify_session(_at(10, 0, day=date(2026, 10, 12)), calendar=calendar)
    weekend = classify_session(_at(10, 0, day=date(2026, 10, 10)), calendar=calendar)
    assert weekday.phase == SessionPhase.INTRADAY
    assert weekend.phase == SessionPhase.NON_TRADING_DAY


def test_empty_calendar_behaves_like_no_calendar() -> None:
    assert classify_session(_at(10, 0), calendar=TradingCalendar([])).phase == SessionPhase.INTRADAY


def test_naive_clock_is_rejected() -> None:
    with pytest.raises(ValueError, match="timezone-aware"):
        classify_session(datetime(2026, 10, 5, 10, 0, 0))


def test_utc_input_is_judged_on_the_taipei_clock() -> None:
    # 01:00:00 UTC = 09:00:00 Taipei -> open; 00:59:59 UTC = 08:59:59 Taipei -> not yet.
    assert classify_session(datetime(2026, 10, 5, 1, 0, 0, tzinfo=UTC)).phase == (
        SessionPhase.INTRADAY
    )
    assert classify_session(datetime(2026, 10, 5, 0, 59, 59, tzinfo=UTC)).phase == (
        SessionPhase.BEFORE_OPEN
    )
    # 05:24:59 UTC = 13:24:59 Taipei; 05:25:00 UTC = 13:25:00 Taipei.
    assert classify_session(datetime(2026, 10, 5, 5, 24, 59, tzinfo=UTC)).phase == (
        SessionPhase.INTRADAY
    )
    assert classify_session(datetime(2026, 10, 5, 5, 25, 0, tzinfo=UTC)).phase == (
        SessionPhase.AFTER_WINDOW
    )


def test_utc_date_rollover_at_0800_taipei_is_not_a_new_trading_day() -> None:
    """00:00 UTC is 08:00 Taipei: still before the open, on the Taipei date."""
    decision = classify_session(datetime(2026, 10, 5, 0, 0, 0, tzinfo=UTC))
    assert decision.phase == SessionPhase.BEFORE_OPEN
    assert decision.local_date == MONDAY


def test_taipei_date_differs_from_the_utc_date_late_in_the_evening() -> None:
    # Sunday 20:00 UTC is Monday 04:00 Taipei: a weekday, before open.
    decision = classify_session(datetime(2026, 10, 4, 20, 0, 0, tzinfo=UTC))
    assert decision.local_date == MONDAY
    assert decision.phase == SessionPhase.BEFORE_OPEN


# Extension window (P-7), disabled by default ---------------------------------

EXTENDED = IntradaySessionConfig(extension_enabled=True)


@pytest.mark.parametrize(
    ("moment", "phase", "allowed"),
    [
        (_at(13, 24, 59), SessionPhase.INTRADAY, True),
        (_at(13, 25), SessionPhase.AFTER_CLOSE_EXTENSION, True),
        (_at(14, 59, 59), SessionPhase.AFTER_CLOSE_EXTENSION, True),
        (_at(15, 0), SessionPhase.AFTER_WINDOW, False),
    ],
)
def test_extension_window_when_enabled(
    moment: datetime, phase: SessionPhase, allowed: bool
) -> None:
    decision = classify_session(moment, config=EXTENDED)
    assert decision.phase == phase
    assert decision.quotes_allowed is allowed


def test_extension_does_not_reach_weekends() -> None:
    saturday = classify_session(_at(14, 0, day=date(2026, 10, 3)), config=EXTENDED)
    assert saturday.phase == SessionPhase.NON_TRADING_DAY


def test_config_rejects_inverted_windows() -> None:
    with pytest.raises(ValueError, match="open_time"):
        IntradaySessionConfig(open_time=time(14, 0))
    with pytest.raises(ValueError, match="extension_end"):
        IntradaySessionConfig(extension_enabled=True, extension_end=time(13, 0))


def test_custom_window_end_moves_the_boundary() -> None:
    config = IntradaySessionConfig(window_end=time(13, 30))
    assert classify_session(_at(13, 25), config=config).phase == SessionPhase.INTRADAY
    assert classify_session(_at(13, 30), config=config).phase == SessionPhase.AFTER_WINDOW

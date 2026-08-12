"""Calendar and indicator maths: the inputs every rule threshold is read against."""

from __future__ import annotations

from datetime import date
from decimal import Decimal

from app.data.interface import PriceBar
from app.playbook import indicators
from app.playbook.calendar import TradingCalendar
from tests.api_helpers import recent_bars
from tests.playbook_helpers import calendar


def _bars(closes: list[float], *, end: date = date(2026, 8, 11)) -> list[PriceBar]:
    return recent_bars(closes, end=end)


# --- calendar --------------------------------------------------------------


def test_schedule_days_are_tuesdays_and_thursdays_that_traded() -> None:
    days = calendar()
    assert days.is_schedule_day(date(2026, 8, 11)) is True  # Tuesday
    assert days.is_schedule_day(date(2026, 8, 13)) is True  # Thursday
    assert days.is_schedule_day(date(2026, 8, 12)) is False  # Wednesday


def test_a_closed_tuesday_is_not_a_schedule_day() -> None:
    """A holiday is absent from the observed days, so it is simply not one."""
    observed = {date(2026, 8, 10), date(2026, 8, 12), date(2026, 8, 13)}
    days = TradingCalendar(observed)
    assert days.is_trading_day(date(2026, 8, 11)) is False
    assert days.is_schedule_day(date(2026, 8, 11)) is False
    assert days.next_trading_day(date(2026, 8, 10)) == date(2026, 8, 12)


def test_shifting_counts_trading_days_not_calendar_days() -> None:
    days = calendar()
    # Friday + 1 trading day is the following Monday.
    assert days.shift(date(2026, 8, 14), 1) == date(2026, 8, 17)
    assert days.shift(date(2026, 8, 11), 10) == date(2026, 8, 25)
    assert days.shift(date(2026, 8, 11), 0) == date(2026, 8, 11)


def test_trading_days_between_excludes_the_starting_day() -> None:
    days = calendar()
    assert days.trading_days_between(date(2026, 8, 11), date(2026, 8, 11)) == 0
    assert days.trading_days_between(date(2026, 8, 11), date(2026, 8, 18)) == 5


# --- indicators ------------------------------------------------------------


def test_ma25_needs_25_bars() -> None:
    assert indicators.moving_average(_bars([100.0] * 24), 25) is None
    assert indicators.moving_average(_bars([100.0] * 25), 25) == Decimal("100")


def test_bias_is_the_percentage_gap_to_the_moving_average() -> None:
    assert indicators.bias(Decimal("110"), Decimal("100")) == Decimal("10")
    assert indicators.bias(Decimal("110"), None) is None


def test_change_pct_compares_the_last_two_closes() -> None:
    assert indicators.change_pct(_bars([100.0, 103.0])) == Decimal("3")
    assert indicators.change_pct(_bars([100.0])) is None


def test_consecutive_days_below_recomputes_the_line_for_each_session() -> None:
    """Each session is judged against its own monthly line, not today's."""
    closes = [100.0] * 20 + [90.0, 89.0, 88.0]
    assert indicators.consecutive_days_below(_bars(closes), 20) == 3
    assert indicators.consecutive_days_below(_bars([100.0] * 23), 20) == 0


def test_volatility_is_none_without_enough_history() -> None:
    assert indicators.annualized_volatility(_bars([100.0] * 20), 20) is None
    flat = indicators.annualized_volatility(_bars([100.0] * 21), 20)
    assert flat == 0.0


def test_volatility_rises_with_a_choppy_series() -> None:
    choppy = [100.0 + (5.0 if index % 2 else -5.0) for index in range(21)]
    value = indicators.annualized_volatility(_bars(choppy), 20)
    assert value is not None and value > 30.0


def test_large_move_days_counts_sessions_at_or_past_two_percent() -> None:
    closes = [100.0, 103.0, 103.5, 101.0, 101.2, 101.3]
    assert indicators.large_move_days(_bars(closes), lookback=5, threshold=Decimal("2")) == 2

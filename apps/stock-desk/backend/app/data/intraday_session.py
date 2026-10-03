"""Intraday session judgement for Taiwan equities (ADR-0014 D-3).

Answers one question -- "may an intraday quote be requested right now?" -- from
an injected, timezone-aware instant. It never calls ``datetime.now()``: the
caller passes the clock reading, so every boundary is testable with a literal
timestamp. All wall-clock reasoning happens in Asia/Taipei, so a UTC date
rollover (08:00 Taipei) is not mistaken for a new trading day.

The window, by default (P-6, pending 10/05 field verification):

* weekday, ``09:00 <= t < 13:25`` -- :attr:`SessionPhase.INTRADAY`;
* before 09:00 -- :attr:`SessionPhase.BEFORE_OPEN`;
* ``13:25`` onward -- :attr:`SessionPhase.AFTER_WINDOW`. CEO ruling: from the
  end of the window until the official close is published, the product shows the
  previous trading day's close, so quotes are **not** allowed;
* Saturday, Sunday, or a day the calendar knows was a holiday --
  :attr:`SessionPhase.NON_TRADING_DAY`.

The after-close extension (P-7) is disabled by default. When a caller enables
it, ``[window end, publish cutoff)`` becomes :attr:`SessionPhase.AFTER_CLOSE_EXTENSION`
and quotes are allowed again, but the phase stays distinct so the caller can
label such a price differently from an intraday one.

Holidays: this module reuses :class:`app.data.calendar.TradingCalendar`, which
is *observed* from bar dates with a Mon-Fri fallback. A holiday inside the
observed range is therefore recognised, but **today** is almost always beyond
the last observed bar, so a holiday that is happening right now is not known
here. That case is caught from evidence instead (ADR-0014 D-3): a quote whose
trade date is not today is rejected as ``not_today`` by
``app.data.quote_quality``. No hard-coded holiday table is kept.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, time
from enum import StrEnum
from typing import Final
from zoneinfo import ZoneInfo

from app.data.calendar import TradingCalendar
from app.data.freshness import TW_POLICY
from app.data.quote_params import (
    AFTER_CLOSE_EXTENSION_ENABLED,
    INTRADAY_END,
    INTRADAY_OPEN,
)

TAIPEI: Final = ZoneInfo("Asia/Taipei")


class SessionPhase(StrEnum):
    """Where the Taiwan session stands at a given instant."""

    BEFORE_OPEN = "before_open"
    INTRADAY = "intraday"
    AFTER_WINDOW = "after_window"
    AFTER_CLOSE_EXTENSION = "after_close_extension"
    NON_TRADING_DAY = "non_trading_day"


@dataclass(frozen=True)
class IntradaySessionConfig:
    """The window's edges and whether it is extended after the close."""

    #: Start of the window, inclusive.
    open_time: time = INTRADAY_OPEN
    #: P-6, end of the window, exclusive (pending 10/05 field verification).
    window_end: time = INTRADAY_END
    #: P-7, whether the window extends past ``window_end`` (pending 10/05
    #: field verification; disabled by CEO ruling).
    extension_enabled: bool = AFTER_CLOSE_EXTENSION_ENABLED
    #: End of the extension, exclusive: the daily-bar publish cutoff, after
    #: which the official close is expected to be in the daily series.
    extension_end: time = TW_POLICY.publish_cutoff

    def __post_init__(self) -> None:
        if not self.open_time < self.window_end:
            raise ValueError("open_time must be before window_end")
        if self.extension_enabled and not self.window_end < self.extension_end:
            raise ValueError("window_end must be before extension_end")


DEFAULT_CONFIG: Final = IntradaySessionConfig()


@dataclass(frozen=True)
class SessionDecision:
    """The phase at one instant, with the Taipei calendar date it was judged on."""

    phase: SessionPhase
    local_date: date

    @property
    def quotes_allowed(self) -> bool:
        """``True`` when an intraday quote may be requested in this phase."""
        return self.phase in (SessionPhase.INTRADAY, SessionPhase.AFTER_CLOSE_EXTENSION)


def classify_session(
    now: datetime,
    *,
    calendar: TradingCalendar | None = None,
    config: IntradaySessionConfig = DEFAULT_CONFIG,
) -> SessionDecision:
    """Classify the instant ``now`` (timezone-aware, any zone) into a phase.

    Raises ``ValueError`` for a naive datetime: its zone is unknowable, and
    guessing one would silently shift the window by hours.
    """
    if now.tzinfo is None:
        raise ValueError("now must be timezone-aware")
    local = now.astimezone(TAIPEI)
    day = local.date()
    if day.weekday() >= 5 or (calendar is not None and not calendar.is_trading_day(day)):
        return SessionDecision(SessionPhase.NON_TRADING_DAY, day)
    wall = local.time()
    if wall < config.open_time:
        phase = SessionPhase.BEFORE_OPEN
    elif wall < config.window_end:
        phase = SessionPhase.INTRADAY
    elif config.extension_enabled and wall < config.extension_end:
        phase = SessionPhase.AFTER_CLOSE_EXTENSION
    else:
        phase = SessionPhase.AFTER_WINDOW
    return SessionDecision(phase, day)

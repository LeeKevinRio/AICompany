"""Session-based freshness for the daily-bar cache (ADR-0009).

Daily bars change exactly once per trading session, after the exchange
publishes the day's close. A clock-based TTL ("re-fetch if older than 24h")
therefore asks the wrong question: it re-fetches on a Sunday for data that
cannot have changed, and it happily serves a Friday fetch at 09:00 Monday as
"fresh" when the market has since traded a whole session. The question that
matches the data is **"does the cache already hold the latest session the
market has completed and published?"** -- and that is what this module
answers.

The rule, per market:

* ``latest_completed_session(now)`` -- the most recent weekday whose close
  the exchange has had time to publish: today if local time is past the
  market's ``publish_cutoff``, else the previous weekday. Weekends are
  stepped over; exchange holidays are **not** modelled (see below).
* :func:`judge` compares that day with what the cache holds:

  - ``HAS_LATEST_SESSION`` -- the cache's last bar is on or after that day
    (bounded by the requested end date): serve the cache, call nobody.
  - ``CHECKED_RECENTLY`` -- the cache lacks that day, but a live source was
    already consulted within ``recheck_cooldown`` and had nothing newer
    (a holiday, or the close not yet published): serve the cache, disclosed
    as stale, and do not hammer the source.
  - ``REFETCH`` -- the cache lacks that day and nobody has looked lately:
    call the live source.

Two limits are stated rather than hidden:

1. **Publish cutoffs are unverified assumptions** (no egress in the build
   environment; ``data-source-integration`` skill convention). They are set
   conservatively late, and the cooldown makes a wrong cutoff cost at most one
   extra live call per cooldown window, never a silent stale serve past the
   next session.
2. **Holidays are not modelled.** On an exchange holiday the rule expects a
   session that never happens, so the cache looks one day short; the effect
   is one live call per cooldown window while the app is in use, which is
   the price of not maintaining a holiday table (the same trade-off
   ``app/data/calendar.py`` makes).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from enum import StrEnum
from zoneinfo import ZoneInfo

from app.data.interface import Market


class Verdict(StrEnum):
    """What the cache may do for a request, given the session the market has reached."""

    HAS_LATEST_SESSION = "has_latest_session"
    CHECKED_RECENTLY = "checked_recently"
    REFETCH = "refetch"


@dataclass(frozen=True)
class SessionFreshnessPolicy:
    """One market's "a new session exists" rule."""

    #: IANA zone the exchange's clock runs on.
    timezone: str
    #: Local wall time after which the day's close is assumed published.
    #: **Unverified** (ADR-0009): chosen late enough to be safe, and backed by
    #: ``recheck_cooldown`` if it is still too early.
    publish_cutoff: time
    #: Minimum gap between two live checks that both find nothing newer.
    recheck_cooldown: timedelta

    def is_within_cooldown(self, now: datetime, at: datetime) -> bool:
        """``True`` while ``at`` is in the past and less than ``recheck_cooldown`` ago.

        A timestamp in the future (a clock that was set back) is *not* within
        the cooldown: the alternative is a cooldown that never expires.
        """
        since = now - at
        return timedelta(0) <= since < self.recheck_cooldown

    def latest_completed_session(self, now: datetime) -> date:
        """The most recent weekday whose close has (by assumption) been published."""
        local = now.astimezone(ZoneInfo(self.timezone))
        day = local.date()
        if local.time() < self.publish_cutoff:
            day -= timedelta(days=1)
        return _previous_weekday_or_same(day)


def _previous_weekday_or_same(day: date) -> date:
    while day.weekday() >= 5:
        day -= timedelta(days=1)
    return day


#: TWSE publishes the daily quotes after the 13:30 close; the exact release
#: time is not verified here (no egress), 15:00 is the safe-side assumption.
#: No quota pressure on TW (ADR-0005), so a short cooldown is affordable.
TW_POLICY = SessionFreshnessPolicy(
    timezone="Asia/Taipei", publish_cutoff=time(15, 0), recheck_cooldown=timedelta(hours=1)
)

#: US close is 16:00 New York; end-of-day data is usually complete by the
#: evening. 18:00 is the safe-side assumption. The cooldown is a full day
#: because Alpha Vantage's 25 req/day budget (ADR-0005) must not be spent on
#: holiday re-checks -- this keeps the worst case identical to the old 24h TTL.
US_POLICY = SessionFreshnessPolicy(
    timezone="America/New_York",
    publish_cutoff=time(18, 0),
    recheck_cooldown=timedelta(hours=24),
)

_BY_MARKET: dict[Market, SessionFreshnessPolicy] = {"TW": TW_POLICY, "US": US_POLICY}


def policy_for(market: Market) -> SessionFreshnessPolicy:
    return _BY_MARKET[market]


def judge(
    policy: SessionFreshnessPolicy,
    *,
    last_bar_date: date,
    last_checked_at: datetime,
    requested_end: date,
    now: datetime,
) -> Verdict:
    """Decide whether a cache holding bars up to ``last_bar_date`` may answer.

    ``requested_end`` bounds the expectation: a request for history that ends
    last month cannot be missing yesterday's session. It is a plain date from
    the caller's clock (``date.today()`` in the container, in practice UTC);
    that is safe only while the market's ``publish_cutoff`` is later in the
    day than the caller's clock can lag behind the exchange -- 15:00 Taipei is
    seven hours past the UTC midnight, so a Taipei morning request still
    expects yesterday either way. Moving a cutoff earlier than that lag would
    make "today" unreachable and silently freeze the cache; keep cutoffs late.

    ``last_checked_at`` is when a live source was last asked for this series
    and answered in full -- the cache's *fetch log*, deliberately not the bar
    rows' ``fetched_at``: a holiday fetch writes no new bar, so only the log
    can carry "we looked, there was nothing newer".

    Both datetimes must be timezone-aware. A ``last_checked_at`` in the future
    (a clock that was set back) is treated as unknown, which means re-fetch:
    the alternative would be a cooldown that never expires.
    """
    if now.tzinfo is None or last_checked_at.tzinfo is None:
        raise ValueError("judge() needs timezone-aware datetimes")
    if last_bar_date >= expected_session(policy, requested_end=requested_end, now=now):
        return Verdict.HAS_LATEST_SESSION
    if policy.is_within_cooldown(now, last_checked_at):
        return Verdict.CHECKED_RECENTLY
    return Verdict.REFETCH


def expected_session(policy: SessionFreshnessPolicy, *, requested_end: date, now: datetime) -> date:
    """The session a cache serving ``[.., requested_end]`` is expected to hold."""
    return min(policy.latest_completed_session(now), _previous_weekday_or_same(requested_end))

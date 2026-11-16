"""Session finality: whether a daily bar is the exchange's final close.

ADR-0030 D-1 point 3 names this new module as the home of ``is_final`` and
D-3 point 2 adopts the finality test of ADR-0028 CS-17 (and nothing else of
ADR-0028): a bar for session ``trade_date`` is final when the earliest of its
timestamps is not before that day's publish cutoff in the market's own clock.
When ADR-0028 is accepted, this module takes over its session calendar work
rather than a second copy being written.

The two parameters are referenced, never copied (ADR-0028 VS-1, VS-4, CS-7):

* the market clock is ``policy_for(market).timezone``;
* the cutoff is ``policy_for(market).publish_cutoff`` (15:00 Asia/Taipei for TW).

The observed trading-day calendar lives in ``app/data/calendar.py`` and the
publish cutoffs in ``app/data/freshness.py``; this module adds only the
finality judgement on top of the latter and keeps no trading-day list of its
own. ``final_after`` and ``final_session_evidence`` (CS-17) are not written:
ADR-0030 needs ``is_final`` alone.
"""

from __future__ import annotations

from datetime import date, datetime
from zoneinfo import ZoneInfo

from app.data.freshness import policy_for
from app.data.interface import Market


def is_final(market: Market, trade_date: date, *stamps: datetime | None) -> bool:
    """Whether a bar of ``trade_date`` stamped with ``stamps`` is final (ADR-0028 CS-17).

    ``True`` only when at least one stamp is given, every stamp is a
    timezone-aware ``datetime``, and the earliest of them is at or after
    ``trade_date``'s publish cutoff in the market's clock. Anything else --
    no stamp, a ``None`` stamp, a naive stamp -- is ``False``: a bar whose
    finality cannot be shown is not final.
    """
    if isinstance(trade_date, datetime) or not isinstance(trade_date, date):
        raise TypeError("trade_date must be a date, not a datetime")
    if not stamps:
        return False
    aware: list[datetime] = []
    for stamp in stamps:
        if not isinstance(stamp, datetime) or stamp.utcoffset() is None:
            return False
        aware.append(stamp)
    policy = policy_for(market)
    cutoff = datetime.combine(trade_date, policy.publish_cutoff, tzinfo=ZoneInfo(policy.timezone))
    return cutoff <= min(aware)

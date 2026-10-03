"""Ex-date coverage rule (ADR-0016 D-5): can "no known ex-date in the window" be trusted?

The change screen (``app.portfolio.price_change``) withholds a change when a
*known* ex-date falls inside ``(basis_date, price_date]`` (F6). A symbol with no
known ex-date there is only "no event" if the source of ex-dates could have
known about one. This rule answers that, per row, with ``known`` or ``unknown``
-- nothing else, and a row it does not answer counts as ``unknown`` (D-5).

## What counts as proof

TWT48U_ALL lists **upcoming** ex-dates only; once a date passes the row leaves
the table. So a run after the ex-date proves nothing about it. The only proof is
a run that took place while the date was still in the future.

The authoritative source of those runs is the main DB's sync record, per
ADR-0016 D-5.2 (``dividend_sync_runs`` / ``dividend_sync_unparsed``; not yet
implemented). ``app.data.market_panel.MarketPanelReader`` happens to satisfy the
:class:`AnnounceRunSource` Protocol (it reads the capture's ``dividend_announce``
runs), but it is for tests and the ADR-0016 V-1 offline check only: the
positions data chain must never call it (ADR-0012 C-7). Swapping the source
changes the adapter, not the decision core below. A row is ``known`` only when
**all** of these hold:

1. the row is a TW symbol whose latest bar came from ``twse`` (the table covers
   TWSE-listed stocks only: OTC, US and spliced sources are ``unknown``);
2. there is an ``ok`` run whose Taipei date is on or before ``basis_date`` --
   every day of the window was then still in the future. The newest such run is
   the *anchor*; a run recorded after ``basis_date`` cannot anchor anything;
3. ``price_date`` is at most ``min_announce_lead_days`` after the anchor's date,
   i.e. any ex-date in the window must already have been listed by the anchor
   run. A stale anchor does not prove that nothing was listed since;
4. no run from the anchor on holds a row of this symbol that is dated inside the
   window or whose date could not be parsed. Such an event exists (or may
   exist), so "no event" is not a statement this rule can stand behind.

## The one unverified number

``min_announce_lead_days`` is L as defined by ADR-0016 V-1 (see
``MIN_ANNOUNCE_LEAD_DAYS``). It has **not** been verified: this environment has
no egress to TWSE. The default is the smallest value that still lets a daily
sync prove anything, and it errs toward ``unknown``: a Monday row can never be
``known`` under it, because the last anchor is Friday's. Raising it needs
evidence.

## Honest limits

* Granularity is the calendar day (Taipei). An event announced after the anchor
  day's own last capture (21:30) and dated within the lead is outside what this
  rule verified; that is the unverified-lead assumption above, not a proof.

* Rows of the table without a ``Code`` are dropped by the capture before they
  are stored, so they cannot be attributed to a symbol here.
* ``unknown`` is not "an event exists": it means this rule cannot prove there is
  none. Under ``SHOW_WHEN_COVERAGE_UNKNOWN`` the change is still shown.
* The ex-dates F6 itself reads live in the main DB's ``dividend_events``, fed by
  a manual CLI. The test-only market DB reader is a different store; point 4
  only guards against that store knowing an event ``dividend_events`` lacks, it
  does not reconcile the two. D-5.2 moves the proof into the main DB.

One read per book (K-7). This module imports nothing from ``app.portfolio``
beyond the Protocol types it implements, and must not reach
``app.data.market_panel`` (ADR-0012 C-7; pinned by an import-graph test): the
source is a structural Protocol.
"""

from __future__ import annotations

import logging
import sqlite3
from collections.abc import Collection, Mapping, Sequence
from datetime import date, timedelta
from typing import Final, Protocol
from zoneinfo import ZoneInfo

from app.data.interface import DividendAnnounceObservation
from app.portfolio.price_change import CoverageQuery, ExDateCoverage

logger = logging.getLogger(__name__)

#: The only bar source whose symbols TWT48U_ALL (TWSE-listed) can speak for.
LISTED_BAR_SOURCE: Final = "twse"

#: ADR-0016 V-1's L: the largest integer such that, for any TWSE-listed
#: ex-dividend event E, every ok sync from Asia/Taipei 00:00 of day E-L up to
#: (not including) E lists E in TWT48U_ALL. It is when the dataset lists an
#: event, not a legal duty of the issuer to announce. UNVERIFIED lower bound,
#: deliberately the smallest meaningful value (see module docstring). Raising it
#: needs V-1 evidence (e.g. an offline check over accumulated runs); record it
#: in ADR-0016.
MIN_ANNOUNCE_LEAD_DAYS: Final = 1

_TAIPEI: Final = ZoneInfo("Asia/Taipei")


class AnnounceRunSource(Protocol):
    """Read side of the sync record (ADR-0016 D-5.2 source, adapter pending).

    ``MarketPanelReader`` satisfies it structurally, for tests and V-1 offline
    checks only; the positions data chain must not call it (ADR-0012 C-7).
    """

    def dividend_announce_observations(
        self, symbols: Collection[str], recorded_not_before: date
    ) -> Sequence[DividendAnnounceObservation]: ...


class AnnounceRunCoverageRule:
    """:class:`~app.portfolio.price_change.ExDateCoverageRule` over an announce-run source."""

    def __init__(
        self,
        runs: AnnounceRunSource,
        *,
        min_announce_lead_days: int = MIN_ANNOUNCE_LEAD_DAYS,
    ) -> None:
        if min_announce_lead_days < 1:
            # Zero would claim an event can be announced on its own ex-date and
            # still be seen by a run "before" it -- not a lead time at all.
            raise ValueError("min_announce_lead_days must be at least 1")
        self._runs = runs
        self._lead = timedelta(days=min_announce_lead_days)

    def coverage(self, queries: Sequence[CoverageQuery]) -> Mapping[CoverageQuery, ExDateCoverage]:
        answers: dict[CoverageQuery, ExDateCoverage] = {query: "unknown" for query in queries}
        eligible = [query for query in answers if _is_listed_tw(query)]
        if not eligible:
            return answers
        # An anchor must be dated >= price_date - lead (point 3). Taipei is UTC+8,
        # so the UTC date of such a run can be one day earlier: widen by a day.
        earliest = min(query.price_date for query in eligible) - self._lead - timedelta(days=1)
        try:
            observations = self._runs.dividend_announce_observations(
                {_symbol_key(query) for query in eligible}, earliest
            )
        except (sqlite3.Error, OSError, ValueError):
            # An unreadable or corrupt run log (ValueError: a stored timestamp or
            # date that does not parse) proves nothing; it must not blank the
            # column (an exception here would null every row of the book, D-3).
            logger.warning("dividend coverage unknown: run log unreadable", exc_info=True)
            return answers

        run_dates = _run_dates(observations)
        for query in eligible:
            if self._proves(query, observations, run_dates):
                answers[query] = "known"
        return answers

    def _proves(
        self,
        query: CoverageQuery,
        observations: Sequence[DividendAnnounceObservation],
        run_dates: Mapping[int, date],
    ) -> bool:
        before = [day for day in run_dates.values() if day <= query.basis_date]
        if not before:
            return False
        anchor = max(before)
        if query.price_date > anchor + self._lead:
            return False
        for observation in observations:
            if observation.symbol != _symbol_key(query):
                continue
            run_day = run_dates.get(observation.run_id)
            # A run whose date is unknown (naive timestamp) cannot anchor, but the
            # rows it carries are still events: skipping them would fail open.
            if run_day is not None and run_day < anchor:
                continue
            if observation.ex_date is None:
                return False
            if query.basis_date < observation.ex_date <= query.price_date:
                return False
        return True


def _symbol_key(query: CoverageQuery) -> str:
    return query.symbol.strip().upper()


def _is_listed_tw(query: CoverageQuery) -> bool:
    # basis_date >= price_date is not a window at all (F4 already withholds such
    # a row); there is nothing to prove, so it is never answered ``known``.
    return (
        query.market == "TW"
        and query.latest_source == LISTED_BAR_SOURCE
        and query.basis_date < query.price_date
    )


def _run_dates(observations: Sequence[DividendAnnounceObservation]) -> dict[int, date]:
    """Taipei calendar date of each run; a run with a naive timestamp proves nothing."""
    dates: dict[int, date] = {}
    for observation in observations:
        recorded = observation.recorded_at
        if recorded.tzinfo is None:
            continue
        dates[observation.run_id] = recorded.astimezone(_TAIPEI).date()
    return dates


__all__ = [
    "LISTED_BAR_SOURCE",
    "MIN_ANNOUNCE_LEAD_DAYS",
    "AnnounceRunCoverageRule",
    "AnnounceRunSource",
]

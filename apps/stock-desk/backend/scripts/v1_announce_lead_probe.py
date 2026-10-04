"""ADR-0016 V-1 offline probe: how many days ahead does TWT48U_ALL list an ex-dividend event?

Run from ``apps/stock-desk/backend`` on a machine that holds the market DB::

    uv run python scripts/v1_announce_lead_probe.py --db-path ./data/stock-desk-market.db

Read-only by construction: the file is opened with SQLite's ``mode=ro`` URI (the
same way ``MarketPanelReader`` does), it is never created, and nothing is written
-- not to the market DB, not to the main DB, not to disk (output goes to stdout
only). One caveat that is SQLite's, not the script's: reading a WAL-mode database
can leave SQLite's own ``-wal`` / ``-shm`` sidecar files next to it; the database
file itself is byte-identical afterwards. Standard library only: no ``app``
import, so it cannot touch ``app.data.market_panel`` or any application wiring.
It is an offline check, outside the positions data chain (ADR-0012 C-7).

It follows the V-1 criteria of ADR-0016 ("待查證參數"):

1. For every event (symbol, E) it computes ``l = floor((E 00:00 Asia/Taipei - the
   recorded_at of the first ok run that lists it) / 1 day)``. ``min(l)`` over the
   sample is what bounds the new value (new value <= min(l) - 1).
2. Persistence: every ok run from the first listing up to (not including) E 00:00
   Taipei must list the event. Each run that does not is reported, one line per
   (event, run), saying whether the symbol is gone or listed under other dates.
3. Sample: the run period, ok-run and event counts, the weekdays with no ok run,
   and whether a whole June..September season lies inside the run period.

What the numbers mean (and do not)
----------------------------------
* An event already listed in the **first** ok run of the sample is left-censored:
  its real first listing is earlier than the sample, so its computed ``l`` is only
  a lower bound. Such events are flagged ``censored`` and reported separately; they
  never raise ``min(l)`` above the truth, but a ``min(l)`` made of them alone says
  little. The first usable evidence is the events that *appear* during the sample.
* A computed ``l`` is quantized to the run schedule: the real first listing may be
  earlier than the first run that saw it, so ``l`` is a lower bound of the real
  lead time, never an over-estimate (it errs toward a smaller new value).
* The output never says "set V-1 to N". It prints the upper bound the data allows
  and the conditions that must still hold (persistence anomalies explained, a full
  season, the regulation check); changing ``MIN_ANNOUNCE_LEAD_DAYS`` is a decision
  made through ADR-0016 D-5.6, not by this script.
* A run that is ``ok`` but stored no rows (empty table) is treated as listing
  nothing, so it shows up as a persistence anomaly rather than being skipped.
"""

from __future__ import annotations

import argparse
import math
import os
import sqlite3
import sys
from collections import defaultdict
from collections.abc import Mapping, Sequence
from contextlib import closing
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

TAIPEI = ZoneInfo("Asia/Taipei")
DEFAULT_DB_PATH = "./data/stock-desk-market.db"
DB_PATH_ENV_VAR = "STOCK_DESK_MARKET_DB_PATH"
SEASON_FIRST_MONTH = 6
SEASON_LAST_MONTH = 9

#: One ok ``dividend_announce`` run: its id, when it was recorded, what it listed.
RunListing = tuple[int, datetime, frozenset[tuple[str, date]]]

_RUNS_SQL = """
    SELECT run_id, recorded_at, content_hash
    FROM pit_snapshot_runs
    WHERE kind = 'dividend_announce' AND status = 'ok'
    ORDER BY recorded_at, run_id
"""
_ROWS_SQL = "SELECT content_hash, symbol, ex_date FROM pit_dividend_announce_rows"


@dataclass(frozen=True)
class EventLead:
    """The lead time of one event."""

    symbol: str
    ex_date: date
    first_listed_at: datetime
    lead_days: int
    censored: bool
    runs_listing: int


@dataclass(frozen=True)
class Anomaly:
    """One ok run, between first listing and E, that did not list the event."""

    symbol: str
    ex_date: date
    run_id: int
    recorded_at: datetime
    other_dates: tuple[date, ...]


@dataclass(frozen=True)
class Report:
    runs: int
    empty_runs: int
    first_run: datetime
    last_run: datetime
    events: tuple[EventLead, ...]
    anomalies: tuple[Anomaly, ...]
    unparsed_rows: int
    weekdays_without_run: tuple[date, ...]
    complete_seasons: tuple[int, ...]


# ---------------------------------------------------------------- reading


def open_read_only(path: Path) -> sqlite3.Connection:
    """Open ``path`` read-only; refuses a missing file instead of creating one."""
    if not path.is_file():
        raise FileNotFoundError(f"market DB not found: {path}")
    return sqlite3.connect(f"{path.resolve().as_uri()}?mode=ro", uri=True, timeout=5)


def _parse_recorded_at(text: str) -> datetime:
    moment = datetime.fromisoformat(text)
    if moment.tzinfo is None:
        raise ValueError(f"recorded_at without a time zone: {text!r}")
    return moment.astimezone(UTC)


def load_runs(conn: sqlite3.Connection) -> tuple[list[RunListing], int]:
    """Ok runs in time order with the (symbol, ex_date) pairs each listed.

    Returns ``(runs, unparsed_rows)``; ``unparsed_rows`` counts rows with a symbol
    but no parsed ex-date, summed over runs (they cannot be tied to an event).
    """
    by_hash: dict[str, set[tuple[str, date]]] = defaultdict(set)
    unparsed_by_hash: dict[str, int] = defaultdict(int)
    for content_hash, symbol, ex_date in conn.execute(_ROWS_SQL):
        if ex_date is None:
            unparsed_by_hash[str(content_hash)] += 1
            continue
        by_hash[str(content_hash)].add((str(symbol).strip().upper(), date.fromisoformat(ex_date)))
    runs: list[RunListing] = []
    unparsed = 0
    for run_id, recorded_at, content_hash in conn.execute(_RUNS_SQL):
        key = str(content_hash) if content_hash is not None else None
        listed = frozenset(by_hash.get(key, set())) if key is not None else frozenset()
        unparsed += unparsed_by_hash.get(key, 0) if key is not None else 0
        runs.append((int(run_id), _parse_recorded_at(str(recorded_at)), listed))
    runs.sort(key=lambda run: (run[1], run[0]))
    return runs, unparsed


# --------------------------------------------------------------- analysis


def _taipei_midnight_utc(day: date) -> datetime:
    return datetime(day.year, day.month, day.day, tzinfo=TAIPEI).astimezone(UTC)


def lead_days(first_listed_at: datetime, ex_date: date) -> int:
    """``floor((E 00:00 Taipei - first_listed_at) / 1 day)``; may be <= 0 for a late listing."""
    delta = _taipei_midnight_utc(ex_date) - first_listed_at
    return math.floor(delta / timedelta(days=1))


def analyze(runs: Sequence[RunListing], unparsed_rows: int = 0) -> Report:
    """Compute V-1's evidence from ok runs in time order. ``runs`` must be non-empty."""
    if not runs:
        raise ValueError("no ok dividend_announce run to analyze")
    first_run_id = runs[0][0]
    first_seen: dict[tuple[str, date], tuple[int, datetime]] = {}
    for run_id, recorded_at, listed in runs:
        for event in listed:
            first_seen.setdefault(event, (run_id, recorded_at))

    events: list[EventLead] = []
    anomalies: list[Anomaly] = []
    for (symbol, ex_date), (run_id, first_at) in sorted(first_seen.items()):
        deadline = _taipei_midnight_utc(ex_date)
        listing_runs = 0
        for other_id, recorded_at, listed in runs:
            if recorded_at < first_at or recorded_at >= deadline:
                continue
            if (symbol, ex_date) in listed:
                listing_runs += 1
                continue
            other_dates = tuple(sorted(day for sym, day in listed if sym == symbol))
            anomalies.append(Anomaly(symbol, ex_date, other_id, recorded_at, other_dates))
        events.append(
            EventLead(
                symbol=symbol,
                ex_date=ex_date,
                first_listed_at=first_at,
                lead_days=lead_days(first_at, ex_date),
                censored=run_id == first_run_id,
                runs_listing=listing_runs,
            )
        )

    run_days = {run[1].astimezone(TAIPEI).date() for run in runs}
    first_day, last_day = min(run_days), max(run_days)
    missing = tuple(
        day
        for offset in range((last_day - first_day).days + 1)
        if (day := first_day + timedelta(days=offset)).weekday() < 5 and day not in run_days
    )
    seasons = tuple(
        year
        for year in range(first_day.year, last_day.year + 1)
        if first_day <= date(year, SEASON_FIRST_MONTH, 1)
        and last_day >= date(year, SEASON_LAST_MONTH, 30)
    )
    return Report(
        runs=len(runs),
        empty_runs=sum(1 for run in runs if not run[2]),
        first_run=runs[0][1],
        last_run=runs[-1][1],
        events=tuple(events),
        anomalies=tuple(anomalies),
        unparsed_rows=unparsed_rows,
        weekdays_without_run=missing,
        complete_seasons=seasons,
    )


def min_lead(events: Sequence[EventLead], *, uncensored_only: bool = False) -> int | None:
    values = [e.lead_days for e in events if not (uncensored_only and e.censored)]
    return min(values) if values else None


# --------------------------------------------------------------- rendering


def _fmt(moment: datetime) -> str:
    return moment.astimezone(TAIPEI).strftime("%Y-%m-%d %H:%M")


def render(report: Report, *, top: int | None = 30) -> str:
    lines: list[str] = []
    add = lines.append
    uncensored = [e for e in report.events if not e.censored]
    all_min = min_lead(report.events)
    fresh_min = min_lead(report.events, uncensored_only=True)

    add("== V-1 probe (ADR-0016): TWT48U_ALL listing lead time ==")
    add("Read-only; nothing was written. Times are Asia/Taipei.")
    add("")
    add("-- Sample --")
    add(
        f"ok dividend_announce runs : {report.runs} (of which listing no rows: {report.empty_runs})"
    )
    add(f"run period                : {_fmt(report.first_run)} .. {_fmt(report.last_run)}")
    add(
        f"events (symbol, E)        : {len(report.events)} "
        f"(censored: {len(report.events) - len(uncensored)}, seen appearing: {len(uncensored)})"
    )
    add(f"rows with unparsed date   : {report.unparsed_rows} (not tied to any event)")
    if report.weekdays_without_run:
        shown = ", ".join(day.isoformat() for day in report.weekdays_without_run[:40])
        extra = len(report.weekdays_without_run) - 40
        more = f" ... (+{extra} more)" if extra > 0 else ""
        add(f"weekdays with no ok run   : {len(report.weekdays_without_run)}: {shown}{more}")
        add("  (no holiday calendar here: a weekday may be a market holiday)")
    else:
        add("weekdays with no ok run   : none")
    if report.complete_seasons:
        add(f"full Jun-Sep season       : yes, {', '.join(map(str, report.complete_seasons))}")
    else:
        add("full Jun-Sep season       : NO -- the run period does not contain Jun 1 .. Sep 30")
    add("")
    add("-- Lead time l (days) --")
    add(f"min(l), all events        : {all_min if all_min is not None else 'n/a'}")
    add(f"min(l), appearing events  : {fresh_min if fresh_min is not None else 'n/a'}")
    if uncensored:
        histogram: dict[int, int] = defaultdict(int)
        for event in uncensored:
            histogram[event.lead_days] += 1
        add(
            "l histogram (appearing events): "
            + ", ".join(f"{value}d x{histogram[value]}" for value in sorted(histogram))
        )
    add("")
    ordered = sorted(report.events, key=lambda e: (e.lead_days, e.ex_date, e.symbol))
    shown_events = ordered if top is None else ordered[:top]
    add(f"-- Events by ascending l ({len(shown_events)} of {len(report.events)}) --")
    add("symbol   E           first listed        l   censored  runs_listing")
    for event in shown_events:
        add(
            f"{event.symbol:<8} {event.ex_date.isoformat()}  {_fmt(event.first_listed_at)}  "
            f"{event.lead_days:>3}  {'yes' if event.censored else 'no ':<8}  {event.runs_listing}"
        )
    add("")
    add(f"-- Persistence anomalies: {len(report.anomalies)} (event, run) pairs --")
    if not report.anomalies:
        add("none: every ok run from first listing up to E listed the event")
    for anomaly in report.anomalies:
        if anomaly.other_dates:
            what = "listed under other date(s) " + ", ".join(
                d.isoformat() for d in anomaly.other_dates
            )
        else:
            what = "symbol not listed at all"
        add(
            f"{anomaly.symbol:<8} E={anomaly.ex_date.isoformat()} run {anomaly.run_id} "
            f"@ {_fmt(anomaly.recorded_at)}: {what}"
        )
    add("")
    add("-- What the data allows (ADR-0016 V-1 criteria 2-4) --")
    ceiling = all_min - 1 if all_min is not None else None
    if ceiling is None:
        add("no event: nothing to bound V-1 with.")
    else:
        add(f"upper bound for a new value = min(l) - 1 = {ceiling}")
        add("(the current MIN_ANNOUNCE_LEAD_DAYS is 1; a bound below 2 changes nothing)")
    blockers: list[str] = []
    if report.anomalies:
        blockers.append("persistence anomalies above are not explained yet (criterion 2)")
    if not report.complete_seasons:
        blockers.append("the sample has no complete Jun-Sep season (criterion 3)")
    if fresh_min is None:
        blockers.append("no event was seen appearing inside the sample; every l is censored")
    elif all_min is not None and fresh_min != all_min:
        blockers.append("min(l) comes from censored events (lower bounds only)")
    blockers.append("regulation cross-check (criterion 5) is done by a person with network access")
    add("still required before any change:")
    for blocker in blockers:
        add(f"  - {blocker}")
    add("Do not edit MIN_ANNOUNCE_LEAD_DAYS from this output alone: see ADR-0016 D-5.6.")
    return "\n".join(lines)


# ---------------------------------------------------------------- CLI


def main(argv: Sequence[str] | None = None, env: Mapping[str, str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="v1_announce_lead_probe.py",
        description="Read-only V-1 probe over the market DB's dividend_announce runs.",
    )
    parser.add_argument(
        "--db-path",
        default=None,
        help=f"market DB file; default ${DB_PATH_ENV_VAR} or {DEFAULT_DB_PATH}",
    )
    parser.add_argument(
        "--top", type=int, default=30, help="events to list, ascending l (default 30)"
    )
    parser.add_argument("--all", action="store_true", help="list every event")
    args = parser.parse_args(argv)
    environment = os.environ if env is None else env
    raw = args.db_path or environment.get(DB_PATH_ENV_VAR, DEFAULT_DB_PATH)
    try:
        with closing(open_read_only(Path(raw))) as conn:
            runs, unparsed = load_runs(conn)
    except (FileNotFoundError, sqlite3.Error, ValueError) as error:
        print(f"cannot read the market DB: {error}", file=sys.stderr)
        return 2
    if not runs:
        print("no ok dividend_announce run in this DB: nothing to analyze.", file=sys.stderr)
        return 2
    print(render(analyze(runs, unparsed), top=None if args.all else args.top))
    return 0


if __name__ == "__main__":  # pragma: no cover - exercised via the CLI
    raise SystemExit(main())

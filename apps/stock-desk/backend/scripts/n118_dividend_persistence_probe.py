"""N-118 offline probe: does TWT48U_ALL keep listing events until the ex-date, and row_count?

Run from ``apps/stock-desk/backend`` on the machine that holds the market DB::

    uv run python scripts/n118_dividend_persistence_probe.py --db-path ./data/stock-desk-market.db
    # optional, only when section (c) shows vanished_* > 0 (at most 30 events, no names/prices):
    uv run python scripts/n118_dividend_persistence_probe.py \\
        --db-path ./data/stock-desk-market.db --detail 30

It answers the two open questions behind ADR-0027 D-3 "late-data trigger" item 10
(10) (c) and (e):

* (c) The withdrawal rule of D-4 item 2 assumes the source lists an event on every
  trading day before its ex-date. The probe counts, per event, whether any ok run
  before the ex-date failed to list it, and whether it came back afterwards.
* (e) ``row_count`` of a ``dividend_announce`` run is the number of parsed rows
  *before* de-duplication (rows without a ``Code`` are skipped earlier). The rows
  actually stored are de-duplicated on ``symbol|raw Date``. ``stored < row_count``
  therefore means "at least one key collision in that batch".

Read-only by construction: the file is opened with SQLite's ``mode=ro`` URI plus
``PRAGMA query_only=ON``, it is never created, and nothing is written -- not to the
market DB, not to the main DB, not to disk (output goes to stdout only). Exactly two
SELECT statements are issued: ``pit_snapshot_runs`` (run id, kind, status,
session_date, content_hash, row_count) and ``pit_dividend_announce_rows`` (content_hash,
key, symbol, ex_date). ``raw_json`` (hence names and any other source column) is never
selected, and no price table is touched. One caveat that is SQLite's, not the script's:
reading a WAL-mode database can leave SQLite's own ``-wal`` / ``-shm`` sidecar files
next to it; the database file itself is byte-identical afterwards. Standard library
only: no ``app`` import. It is an offline check, outside the positions data chain
(ADR-0012 C-7).

How events are classified
-------------------------
Runs are the usable ok ``dividend_announce`` runs (status ``ok``, ``content_hash`` and
``session_date`` set), ordered by ``(session_date, run_id)``. ``recorded_at`` is never
compared (ADR-0027 item 5: no clock comparison). An event is a key (``symbol|raw Date``)
whose ex-date parsed. "Before the ex-date" means ``session_date < ex_date`` (D-4 item 2).
From the first run that lists the event to the last run before its ex-date:

* ``persistent``: every run lists it.
* ``vanished_gone``: some run does not, and no later run before the ex-date lists it.
* ``vanished_returned``: some run does not, and a later run lists it again (a gap).
* ``single_observation``: only one run before the ex-date; nothing to test.
* ``first_seen_on_or_after_ex``: first listed at or after the ex-date; not tested.

``vanished_gone`` is split by what the same symbol does in the run where the event
first went missing: ``reschedule_candidate`` (a key the previous run did not have),
``symbol_relisted_existing`` (other keys that were already there) or ``symbol_gone``.
Every class is counted ``closed`` (the last usable run is on/after the ex-date) and
``open`` (the sample has not reached the ex-date; a vanished event may still return).

What the numbers mean (and do not)
----------------------------------
* A vanished event is counted, not explained: a real withdrawal and an incomplete
  single response look identical inside the DB. Telling them apart needs the TWSE
  announcements, i.e. a person with network access.
* Only ok runs are visible, and there is no trading calendar, so days without a run
  cannot be seen; the run-gap counters only hint at them.
* Only the first ok run of a session is kept (``pit_snapshot.py``), so within-session
  revisions are invisible.
* The thresholds printed at the end are PROPOSED, pending quant and risk-control
  confirmation. The script does not judge: it never prints "holds" or "does not hold".
"""

from __future__ import annotations

import argparse
import math
import os
import sqlite3
import sys
from collections import Counter, defaultdict
from collections.abc import Mapping, Sequence
from contextlib import closing
from dataclasses import dataclass
from datetime import date
from pathlib import Path

DEFAULT_DB_PATH = "./data/stock-desk-market.db"
DB_PATH_ENV_VAR = "STOCK_DESK_MARKET_DB_PATH"

#: Two consecutive usable ok runs further apart than this many days hint at missed sessions.
RUN_GAP_DAYS = 4
#: A persistent closed event whose last run before the ex-date is further than this many
#: days away was only observed up to a point well before its ex-date.
TAIL_GAP_DAYS = 7
#: How many run ids are listed for mismatches and anomalies.
MAX_LISTED_RUN_IDS = 20

#: PROPOSED reading thresholds, pending quant and risk-control confirmation.
PROPOSED_MIN_TESTABLE_CLOSED = 30
PROPOSED_MIN_USABLE_RUNS = 20
PROPOSED_MIN_BATCH_DROP = 3
PROPOSED_MIN_DROP_SHARE = 0.10

CLASS_NAMES = (
    "persistent",
    "vanished_gone",
    "vanished_returned",
    "single_observation",
    "first_seen_on_or_after_ex",
)
GONE_SPLIT_NAMES = ("reschedule_candidate", "symbol_relisted_existing", "symbol_gone")
TESTABLE_CLASSES = ("persistent", "vanished_gone", "vanished_returned")

CONCLUSION_SENTENCE = "樣本不足或未完成一律視為不成立；成立與否須送風控確認。"
CONCLUSION_SENTENCE_EN = (
    "(An insufficient or unfinished sample counts as NOT established; "
    "whether (c) is established is confirmed by risk control.)"
)

_RUNS_SQL = """
    SELECT run_id, status, session_date, content_hash, row_count
    FROM pit_snapshot_runs
    WHERE kind = 'dividend_announce'
    ORDER BY run_id
"""
_ROWS_SQL = "SELECT content_hash, key, symbol, ex_date FROM pit_dividend_announce_rows"


@dataclass(frozen=True)
class RunRecord:
    """One ``dividend_announce`` run as stored (any status)."""

    run_id: int
    status: str
    session_date: date | None
    content_hash: str | None
    row_count: int

    @property
    def usable(self) -> bool:
        return (
            self.status == "ok" and self.content_hash is not None and self.session_date is not None
        )


#: One stored row of a content: key -> (symbol, parsed ex-date or None).
Content = dict[str, tuple[str, date | None]]


@dataclass(frozen=True)
class VanishedEvent:
    """One event that stopped being listed before its ex-date."""

    key: str
    symbol: str
    ex_date: date
    kind: str  # vanished_gone | vanished_returned
    split: str | None  # only for vanished_gone
    closed: bool
    first_listed_run_id: int
    first_missing_run_id: int
    last_listed_run_id: int


@dataclass(frozen=True)
class Report:
    runs_total: int
    status_counts: tuple[tuple[str, int], ...]
    usable_runs: int
    distinct_hashes: int
    first_session: date | None
    last_session: date | None
    multi_run_sessions: int
    distant_run_pairs: int
    distinct_sessions: int
    events: int
    events_closed: int
    events_censored: int
    unparsed_keys: int
    class_counts: dict[tuple[str, bool], int]  # (class, closed) -> n
    split_counts: dict[tuple[str, bool], int]
    tail_gap_events: int
    drop_episodes: int
    largest_drop: int
    largest_drop_share: float
    row_count_deltas: tuple[int, ...]
    row_drop_largest: int
    row_drop_largest_share: float | None
    row_drop_pairs_over_share: int
    vanished: tuple[VanishedEvent, ...]
    ok_runs: int
    ok_unusable: int
    rc_equal: int
    rc_less: int
    rc_greater: int
    rc_zero_stored: int
    rc_no_hash: int
    rc_nonpositive: int
    deficit_sum: int
    deficit_max: int
    affected_hashes: int
    mismatch_run_ids: tuple[int, ...]
    anomaly_run_ids: tuple[int, ...]

    @property
    def testable_closed(self) -> int:
        return sum(self.class_counts.get((name, True), 0) for name in TESTABLE_CLASSES)


# ---------------------------------------------------------------- reading


def open_read_only(path: Path) -> sqlite3.Connection:
    """Open ``path`` read-only; refuses a missing file instead of creating one."""
    if not path.is_file():
        raise FileNotFoundError(f"market DB not found: {path}")
    conn = sqlite3.connect(f"{path.resolve().as_uri()}?mode=ro", uri=True, timeout=5)
    conn.execute("PRAGMA query_only=ON")
    return conn


def _parse_day(text: object) -> date | None:
    if text is None:
        return None
    try:
        return date.fromisoformat(str(text))
    except ValueError:
        return None


def load(conn: sqlite3.Connection) -> tuple[list[RunRecord], dict[str, Content]]:
    """All ``dividend_announce`` runs plus the stored rows grouped by content hash."""
    contents: dict[str, Content] = defaultdict(dict)
    for content_hash, key, symbol, ex_date in conn.execute(_ROWS_SQL):
        contents[str(content_hash)][str(key)] = (str(symbol), _parse_day(ex_date))
    runs = [
        RunRecord(
            run_id=int(run_id),
            status=str(status),
            session_date=_parse_day(session_date),
            content_hash=str(content_hash) if content_hash is not None else None,
            row_count=int(row_count),
        )
        for run_id, status, session_date, content_hash, row_count in conn.execute(_RUNS_SQL)
    ]
    return runs, dict(contents)


# --------------------------------------------------------------- analysis


def percentile(sorted_values: Sequence[int], pct: int) -> int:
    """Nearest-rank percentile of an ascending, non-empty sequence."""
    rank = max(1, math.ceil(pct / 100 * len(sorted_values)))
    return sorted_values[rank - 1]


def _row_count_change(
    usable: Sequence[RunRecord],
) -> tuple[tuple[int, ...], int, float | None, int]:
    """Deltas of ``row_count`` between consecutive usable ok runs and the drop summary."""
    deltas: list[int] = []
    best: tuple[int, float] | None = None  # (drop rows, share) of the largest drop
    over_share = 0
    for previous, current in zip(usable, usable[1:], strict=False):
        delta = current.row_count - previous.row_count
        deltas.append(delta)
        if delta >= 0:
            continue
        drop = -delta
        share = drop / previous.row_count if previous.row_count > 0 else None
        if share is not None and share >= PROPOSED_MIN_DROP_SHARE:
            over_share += 1
        if best is None or (drop, share or 0.0) > best:
            best = (drop, share or 0.0)
    if best is None:
        return tuple(deltas), 0, None, over_share
    return tuple(deltas), best[0], best[1], over_share


def analyze(runs: Sequence[RunRecord], contents: Mapping[str, Content]) -> Report:
    """Compute the (c) persistence and (e) row_count evidence. Pure: no I/O."""
    usable = sorted(
        (run for run in runs if run.usable), key=lambda r: (r.session_date or date.min, r.run_id)
    )
    sessions: list[date] = [run.session_date for run in usable if run.session_date is not None]
    listed: list[Content] = [contents.get(run.content_hash or "", {}) for run in usable]
    n = len(usable)

    # Presence of every key across usable runs.
    presence: dict[str, list[int]] = defaultdict(list)
    info: dict[str, tuple[str, date | None]] = {}
    for index, content in enumerate(listed):
        for key, (symbol, ex_date) in content.items():
            presence[key].append(index)
            info.setdefault(key, (symbol, ex_date))

    class_counts: Counter[tuple[str, bool]] = Counter()
    split_counts: Counter[tuple[str, bool]] = Counter()
    vanished: list[VanishedEvent] = []
    events = events_closed = censored = unparsed_keys = tail_gap_events = 0
    for key, indexes in presence.items():
        symbol, ex_date = info[key]
        if ex_date is None:
            unparsed_keys += 1
            continue
        events += 1
        closed = n > 0 and sessions[-1] >= ex_date
        events_closed += 1 if closed else 0
        first = indexes[0]
        censored += 1 if first == 0 else 0
        if sessions[first] >= ex_date:
            class_counts[("first_seen_on_or_after_ex", closed)] += 1
            continue
        last_before = max(i for i in range(first, n) if sessions[i] < ex_date)
        window = range(first, last_before + 1)
        if len(window) < 2:
            class_counts[("single_observation", closed)] += 1
            continue
        present = set(indexes)
        missing = [i for i in window if i not in present]
        if not missing:
            class_counts[("persistent", closed)] += 1
            if closed and (ex_date - sessions[last_before]).days > TAIL_GAP_DAYS:
                tail_gap_events += 1
            continue
        gap = missing[0]
        returned = any(i in present for i in window if i > gap)
        kind = "vanished_returned" if returned else "vanished_gone"
        class_counts[(kind, closed)] += 1
        split: str | None = None
        if not returned:
            previous_keys = set(listed[gap - 1])
            same_symbol = [k for k, (sym, _) in listed[gap].items() if sym == symbol]
            if any(k not in previous_keys for k in same_symbol):
                split = "reschedule_candidate"
            elif same_symbol:
                split = "symbol_relisted_existing"
            else:
                split = "symbol_gone"
            split_counts[(split, closed)] += 1
        vanished.append(
            VanishedEvent(
                key=key,
                symbol=symbol,
                ex_date=ex_date,
                kind=kind,
                split=split,
                closed=closed,
                first_listed_run_id=usable[first].run_id,
                first_missing_run_id=usable[gap].run_id,
                last_listed_run_id=usable[max(i for i in indexes if i < last_before + 1)].run_id,
            )
        )
    vanished.sort(key=lambda v: (v.ex_date, v.symbol, v.key))

    # Run-to-run drops: events still in the future that the previous run listed and this one lost.
    drop_episodes = largest_drop = 0
    largest_share = 0.0
    for i in range(1, n):
        pending = [k for k, (_, e) in listed[i - 1].items() if e is not None and e > sessions[i]]
        lost = sum(1 for k in pending if k not in listed[i])
        drop_episodes += lost
        if lost and (lost, lost / len(pending)) > (largest_drop, largest_share):
            largest_drop, largest_share = lost, lost / len(pending)

    deltas, row_drop, row_share, row_over = _row_count_change(usable)

    # (e) row_count versus rows actually stored, over all ok runs.
    ok = [run for run in runs if run.status == "ok"]
    equal = less = greater = zero_stored = no_hash = nonpositive = 0
    deficit_sum = deficit_max = 0
    affected: set[str] = set()
    mismatch: list[int] = []
    anomalies: list[int] = []
    for run in ok:
        bad = False
        if run.row_count <= 0:
            nonpositive += 1
            bad = True
        if run.content_hash is None:
            no_hash += 1
            anomalies.append(run.run_id)
            continue
        stored = len(contents.get(run.content_hash, {}))
        if stored == 0:
            zero_stored += 1
            bad = True
        else:
            if stored == run.row_count:
                equal += 1
            elif stored < run.row_count:
                less += 1
                deficit = run.row_count - stored
                deficit_sum += deficit
                deficit_max = max(deficit_max, deficit)
                affected.add(run.content_hash)
                mismatch.append(run.run_id)
            else:
                greater += 1
                bad = True
        if bad:
            anomalies.append(run.run_id)

    statuses = Counter(run.status for run in runs if run.status != "ok")
    session_counts = Counter(sessions)
    return Report(
        runs_total=len(runs),
        status_counts=tuple(sorted(statuses.items())),
        usable_runs=n,
        distinct_hashes=len({run.content_hash for run in usable}),
        first_session=sessions[0] if n else None,
        last_session=sessions[-1] if n else None,
        multi_run_sessions=sum(1 for count in session_counts.values() if count > 1),
        distant_run_pairs=sum(
            1 for a, b in zip(sessions, sessions[1:], strict=False) if (b - a).days > RUN_GAP_DAYS
        ),
        distinct_sessions=len(session_counts),
        events=events,
        events_closed=events_closed,
        events_censored=censored,
        unparsed_keys=unparsed_keys,
        class_counts=dict(class_counts),
        split_counts=dict(split_counts),
        tail_gap_events=tail_gap_events,
        drop_episodes=drop_episodes,
        largest_drop=largest_drop,
        largest_drop_share=largest_share,
        row_count_deltas=deltas,
        row_drop_largest=row_drop,
        row_drop_largest_share=row_share,
        row_drop_pairs_over_share=row_over,
        vanished=tuple(vanished),
        ok_runs=len(ok),
        ok_unusable=sum(1 for run in ok if not run.usable),
        rc_equal=equal,
        rc_less=less,
        rc_greater=greater,
        rc_zero_stored=zero_stored,
        rc_no_hash=no_hash,
        rc_nonpositive=nonpositive,
        deficit_sum=deficit_sum,
        deficit_max=deficit_max,
        affected_hashes=len(affected),
        mismatch_run_ids=tuple(mismatch),
        anomaly_run_ids=tuple(anomalies),
    )


# --------------------------------------------------------------- rendering


def _line(label: str, value: object) -> str:
    return f"{label:<44}: {value}"


def _ids(run_ids: Sequence[int]) -> str:
    shown = ", ".join(str(i) for i in run_ids[:MAX_LISTED_RUN_IDS])
    extra = len(run_ids) - MAX_LISTED_RUN_IDS
    return f"[{shown}]" + (f" (+{extra} more)" if extra > 0 else "")


def render(report: Report, *, today: date, detail: int = 0) -> str:
    lines: list[str] = []
    add = lines.append

    def pair(counts: Mapping[tuple[str, bool], int], name: str) -> str:
        return f"{counts.get((name, True), 0):>5} / {counts.get((name, False), 0)}"

    add("== N-118 probe: TWT48U_ALL persistence (c) and row_count (e) ==")
    add("Read-only; nothing was written. Counts only (symbols appear only with --detail).")
    add("")
    add("-- Sample --")
    add(_line("usable ok runs (hash and session_date set)", report.usable_runs))
    add(_line("distinct content hashes among them", report.distinct_hashes))
    if report.first_session is not None and report.last_session is not None:
        add(_line("session_date range", f"{report.first_session} .. {report.last_session}"))
    else:
        add(_line("session_date range", "n/a"))
    add(_line("sessions holding more than one ok run", report.multi_run_sessions))
    add(
        _line(
            f"consecutive ok runs more than {RUN_GAP_DAYS} days apart",
            report.distant_run_pairs,
        )
    )
    add(_line("events (keys with a parsed ex_date)", report.events))
    add(_line("  closed (last run on/after ex_date)", report.events_closed))
    add(_line("  open", report.events - report.events_closed))
    add(_line("  already listed in the first usable run", report.events_censored))
    add(_line("keys with unparsed ex_date (not tested)", report.unparsed_keys))
    add("")
    add("-- (c) Persistence classes (closed / open) --")
    for name in CLASS_NAMES:
        add(f"{name:<27}: {pair(report.class_counts, name)}")
    add(_line("testable closed events (>=2 runs)", report.testable_closed))
    add("vanished_gone split (closed / open):")
    for name in GONE_SPLIT_NAMES:
        add(f"  {name:<25}: {pair(report.split_counts, name)}")
    add("")
    add("-- (c) Run-to-run drops (events still in the future that a run lost) --")
    add(_line("drop episodes (event, pair)", report.drop_episodes))
    add(_line("largest drop in one pair", report.largest_drop))
    add(_line("largest drop share of that pair's pending", f"{report.largest_drop_share:.3f}"))
    add(
        _line(
            f"persistent closed, last run >{TAIL_GAP_DAYS} days before ex",
            report.tail_gap_events,
        )
    )
    add("")
    add("-- (c) row_count change between consecutive usable ok runs (incomplete-batch estimate) --")
    deltas = sorted(report.row_count_deltas)
    add(_line("consecutive pairs", len(deltas)))
    if deltas:
        spread = " / ".join(
            str(value)
            for value in (
                deltas[0],
                percentile(deltas, 25),
                percentile(deltas, 50),
                percentile(deltas, 75),
                deltas[-1],
            )
        )
        add(_line("delta min / p25 / median / p75 / max", spread))
        add(_line("largest drop (rows)", report.row_drop_largest))
        share = report.row_drop_largest_share
        add(
            _line(
                "largest drop share of previous row_count",
                f"{share:.3f}" if share is not None else "n/a",
            )
        )
        add(
            _line(
                f"pairs with drop share >= {PROPOSED_MIN_DROP_SHARE:.2f} (PROPOSED)",
                report.row_drop_pairs_over_share,
            )
        )
    else:
        add("fewer than 2 usable ok runs: no change to report")
    add("row_count also moves for legitimate reasons (events pass their ex-date, new events")
    add("appear): this is a reference for how often a batch may be incomplete, not a verdict.")
    add("")
    add("-- (e) row_count vs rows stored (ok runs) --")
    add(_line("ok runs", report.ok_runs))
    add(_line("  of which not usable (no hash or no session_date)", report.ok_unusable))
    add(_line("  row_count == stored", report.rc_equal))
    add(_line("  stored < row_count (key collision)", report.rc_less))
    add(_line("  stored > row_count (anomaly)", report.rc_greater))
    add(_line("  stored == 0 with a hash (anomaly)", report.rc_zero_stored))
    add(_line("  ok but content_hash NULL (anomaly)", report.rc_no_hash))
    add(_line("  ok but row_count <= 0 (anomaly)", report.rc_nonpositive))
    add(_line("sum of (row_count - stored) where less", report.deficit_sum))
    add(_line("max of (row_count - stored) where less", report.deficit_max))
    add(_line("distinct content_hash affected", report.affected_hashes))
    add(_line("mismatch run_ids", _ids(report.mismatch_run_ids)))
    add(_line("anomaly run_ids", _ids(report.anomaly_run_ids)))
    non_ok = ", ".join(f"{name}={count}" for name, count in report.status_counts) or "none"
    add(_line("non-ok dividend_announce runs by status", non_ok))
    if detail > 0:
        add("")
        shown = report.vanished[:detail]
        add(f"-- vanished events ({len(shown)} of {len(report.vanished)}; no names, no prices) --")
        for event in shown:
            label = event.kind + (f"/{event.split}" if event.split else "")
            add(
                f"{event.symbol:<8} E={event.ex_date.isoformat()} {label} "
                f"{'closed' if event.closed else 'open'} "
                f"first_listed_run={event.first_listed_run_id} "
                f"first_missing_run={event.first_missing_run_id} "
                f"last_listed_run={event.last_listed_run_id}"
            )
    add("")
    add(
        "-- Suggested reading thresholds (PROPOSED, pending quant and risk-control confirmation) --"
    )
    add("This script does not judge. Suggested values, not approved rules:")
    add(f"  sample adequacy   : testable closed events >= {PROPOSED_MIN_TESTABLE_CLOSED}")
    add(f"                      and usable ok runs >= {PROPOSED_MIN_USABLE_RUNS}")
    add("  counter-example   : any vanished_returned closed event")
    add(
        f"  whole-batch drop  : largest drop in one pair >= {PROPOSED_MIN_BATCH_DROP} "
        f"and share >= {PROPOSED_MIN_DROP_SHARE:.2f}"
    )
    add("")
    add("-- Conclusion-format fields (for the risk-control confirmation) --")
    add(_line("usable ok runs the reading rests on", report.usable_runs))
    add(_line("distinct session_date among them", report.distinct_sessions))
    add(_line("closed testable events (>=2 runs)", report.testable_closed))
    add(_line("run date (date.today() on the executing machine)", today.isoformat()))
    add(CONCLUSION_SENTENCE)
    add(CONCLUSION_SENTENCE_EN)
    return "\n".join(lines)


# ---------------------------------------------------------------- CLI


def main(argv: Sequence[str] | None = None, env: Mapping[str, str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="n118_dividend_persistence_probe.py",
        description="Read-only N-118 probe over the market DB's dividend_announce runs.",
    )
    parser.add_argument(
        "--db-path",
        default=None,
        help=f"market DB file; default ${DB_PATH_ENV_VAR} or {DEFAULT_DB_PATH}",
    )
    parser.add_argument(
        "--detail",
        type=int,
        default=0,
        help="list at most N vanished events (symbol, ex-date, run ids); default 0 = counts only",
    )
    args = parser.parse_args(argv)
    environment = os.environ if env is None else env
    raw = args.db_path or environment.get(DB_PATH_ENV_VAR, DEFAULT_DB_PATH)
    try:
        with closing(open_read_only(Path(raw))) as conn:
            runs, contents = load(conn)
    except (FileNotFoundError, sqlite3.Error, ValueError) as error:
        print(f"cannot read the market DB: {error}", file=sys.stderr)
        return 2
    if not runs:
        print("no dividend_announce run in this DB: nothing to analyze.", file=sys.stderr)
        return 2
    print(render(analyze(runs, contents), today=date.today(), detail=max(0, args.detail)))
    return 0


if __name__ == "__main__":  # pragma: no cover - exercised via the CLI
    raise SystemExit(main())

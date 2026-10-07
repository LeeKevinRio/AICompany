"""F-3: count cached daily bars whose close is not a usable price (read-only).

Why this exists
---------------
The alert tick used to stop for *every* symbol when one symbol's latest cached
bar had a close of zero or below: ``app/alerts/snapshot.py`` handed that close
to ``PortfolioContext.close`` (``gt=0``), which raised, and the scheduled tick
logged one error and evaluated nothing. Task 2026-10-06 fixes the alert path;
F-3 asks whether such rows actually exist on the CEO's real cache. If none do,
the fix ships in the next release; if some do, every scheduled tick has been
failing and the fix becomes a deploy prerequisite.

What it does
------------
Opens ``--db`` read-only and, for each known daily-bar table present in it,
classifies every row's ``close``:

* ``nonpositive`` -- parses as a finite number ``<= 0`` (the crash case);
* ``null``        -- SQL NULL (the schema forbids it; counted in case an older
  build wrote one);
* ``nonfinite``   -- NaN / Infinity text;
* ``unparseable`` -- anything else that is not a number.

``nonpositive``, ``null`` and ``nonfinite`` together decide the verdict -- the
same "usable close" definition as the app (``app.alerts.engine.usable_price``:
present, finite and > 0). ``nonfinite`` must count: the app's cache reader
(``app/data/cache.py``) only skips rows whose ``Decimal(...)`` raises, and
``Decimal("NaN")`` / ``Decimal("Infinity")`` do not raise, so such a row does
reach the alert and valuation paths. Only ``unparseable`` rows are reported
without deciding the verdict: the cache reader skips them.

"Latest bar" means the newest row the app's cache reader would actually keep:
rows whose ``close`` is ``unparseable`` or whose date is not a valid ISO date
are skipped by the reader, so they are left out when picking each series'
newest date (otherwise a skipped row would hide a bad bar behind it).

Every verdict row is then split two ways (risk-compliance F-1 required item):

* by bar position -- ``latest_bar_bad`` (the row is its series' newest cached
  bar, the one a fresh snapshot / valuation reads) vs ``older_bar_bad``;
* by membership -- ``held`` (the series has any row in ``positions``),
  ``watched`` (it has an *enabled* row in ``alert_rules``), ``held_and_watched``
  (both; the intersection, also counted inside ``held`` and ``watched``) and
  ``other`` (neither).

The escalation rule: any ``latest_bar_bad`` row on a held or watched series
makes the fix a deploy prerequisite for the CEO to rule on; older rows only, or
``other`` series only, do not block deployment (next release).

Membership is matched on ``(symbol, market)`` after ``strip().upper()`` on both
sides, so a case difference can only add matches, never hide one.

Tables (schemas copied from the app, not guessed):

* ``price_bars_cache`` (main DB, ``STOCK_DESK_DB_PATH``, default
  ``./data/stock-desk.db``): ``symbol, market, trade_date, ..., close TEXT``.
  This is the table the alert path reads, and the one the verdict is about.
* ``market_daily_bars`` (market DB, ``STOCK_DESK_MARKET_DB_PATH``, default
  ``./data/stock-desk-market.db``): ``symbol, session_date, market, ..., close
  TEXT``. Not on the alert path (ADR-0012 C-7); reported for reference only.
* ``positions`` (``app/positions/store.py``: ``symbol, market, ...``) and
  ``alert_rules`` (``app/alerts/store.py``: ``symbol, market, enabled, ...``)
  live in the same main DB as ``price_bars_cache`` (all three resolve
  ``STOCK_DESK_DB_PATH``), so they are read from ``--db`` as well. Only the
  ``symbol``, ``market`` and ``enabled`` columns are read -- never quantities,
  costs, rule parameters or notes.

There is no local FX-rate cache to scan (ADR-0011; ``app/data/providers/fx.py``),
so FX rates <= 0 (F-1b) are out of this script's reach and not reported.

Hard guarantees
---------------
* Read-only: SQLite ``mode=ro`` URI plus ``PRAGMA query_only``; only SELECTs.
  The file is never created, migrated or written. Nothing is read from
  ``.env``. No network. Stdlib only.
* ``--db`` has no default on purpose. The output holds symbols, markets, dates
  and counts only -- no prices, quantities, costs, paths or credentials.

Exit codes: 0 = nothing found, 1 = rows found (see the summary and
``escalation``), 2 = error (including a main DB without ``positions`` or
``alert_rules``, since held / watched could not be told apart).

Run::

    python check_nonpositive_close.py --db <path-to-stock-desk.db> --out F-3_out.json
"""

from __future__ import annotations

import argparse
import json
import sqlite3
import sys
from contextlib import closing
from dataclasses import dataclass, field
from datetime import UTC, date, datetime
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any

#: (table, date column, whether the alert path reads it)
KNOWN_TABLES: tuple[tuple[str, str, bool], ...] = (
    ("price_bars_cache", "trade_date", True),
    ("market_daily_bars", "session_date", False),
)

#: Categories that decide the verdict, and the ones only reported.
VERDICT_CATEGORIES = ("nonpositive", "null", "nonfinite")
REPORTED_CATEGORIES = ("unparseable",)
#: Keys of the legacy ``other_unusable_rows`` field, kept for compatibility;
#: ``nonfinite`` is also counted in ``bad_rows`` since it decides the verdict.
LEGACY_OTHER_UNUSABLE = ("nonfinite", "unparseable")

#: Membership tables and the columns read from them (schemas from the app).
POSITIONS_TABLE = "positions"
ALERT_RULES_TABLE = "alert_rules"
MEMBERSHIP_COLUMNS: dict[str, tuple[str, ...]] = {
    POSITIONS_TABLE: ("symbol", "market"),
    ALERT_RULES_TABLE: ("symbol", "market", "enabled"),
}

#: Membership groups, in output order. ``held`` and ``watched`` overlap;
#: ``held_and_watched`` is their intersection; ``other`` is neither.
MEMBERSHIP_GROUPS = ("held", "watched", "held_and_watched", "other")

#: ``escalation`` values.
ESCALATE = "deploy_prerequisite"
NOT_BLOCKING = "next_release"

SeriesKey = tuple[str, str]


def classify_close(value: object) -> str | None:
    """The bad-close category of one stored ``close``, or ``None`` if usable."""
    if value is None:
        return "null"
    if isinstance(value, bytes):
        return "unparseable"
    try:
        number = Decimal(str(value).strip())
    except InvalidOperation:
        return "unparseable"
    if not number.is_finite():
        return "nonfinite"
    if number <= 0:
        return "nonpositive"
    return None


def series_key(symbol: object, market: object) -> SeriesKey:
    """Normalised ``(symbol, market)`` used to match bars against membership."""
    return (str(symbol).strip().upper(), str(market).strip().upper())


def parse_day(value: object) -> date | None:
    """The bar date as the app's cache reader parses it, or ``None`` if invalid."""
    if not isinstance(value, str):
        return None
    try:
        return date.fromisoformat(value)
    except ValueError:
        return None


@dataclass(frozen=True)
class Membership:
    """Series that are held (any position row) or watched (an enabled rule)."""

    held: frozenset[SeriesKey]
    watched: frozenset[SeriesKey]

    def groups(self, key: SeriesKey) -> tuple[str, ...]:
        """The MEMBERSHIP_GROUPS one series falls into."""
        is_held = key in self.held
        is_watched = key in self.watched
        if is_held and is_watched:
            return ("held", "watched", "held_and_watched")
        if is_held:
            return ("held",)
        if is_watched:
            return ("watched",)
        return ("other",)


@dataclass
class SymbolTally:
    rows: int = 0
    first: str | None = None
    last: str | None = None
    latest_bar_bad: bool = False
    older_rows: int = 0


def _empty_split() -> dict[str, int]:
    return {"symbols": 0, "rows": 0}


def _bar_class_json(
    per_symbol: dict[SeriesKey, SymbolTally],
    membership: Membership | None,
    *,
    latest: bool,
) -> dict[str, Any]:
    """Symbol and row counts for one bar class, split by membership group.

    The group counts are ``None`` when membership is unknown (the database has
    no ``positions`` / ``alert_rules``), which only happens off the alert path.
    """
    total = _empty_split()
    groups: dict[str, dict[str, int]] = {name: _empty_split() for name in MEMBERSHIP_GROUPS}
    for (symbol, market), tally in per_symbol.items():
        rows = (1 if tally.latest_bar_bad else 0) if latest else tally.older_rows
        if rows == 0:
            continue
        total["symbols"] += 1
        total["rows"] += rows
        if membership is None:
            continue
        for name in membership.groups(series_key(symbol, market)):
            groups[name]["symbols"] += 1
            groups[name]["rows"] += rows
    body: dict[str, Any] = dict(total)
    for name in MEMBERSHIP_GROUPS:
        body[name] = groups[name] if membership is not None else None
    return body


@dataclass
class TableReport:
    table: str
    on_alert_path: bool
    total_rows: int = 0
    counts: dict[str, int] = field(default_factory=dict)
    first: str | None = None
    last: str | None = None
    per_symbol: dict[SeriesKey, SymbolTally] = field(default_factory=dict)

    @property
    def verdict_rows(self) -> int:
        return sum(self.counts.get(name, 0) for name in VERDICT_CATEGORIES)

    def held_or_watched_latest_bad(self, membership: Membership) -> int:
        """Series whose bad latest bar belongs to a held or watched series."""
        return sum(
            1
            for (symbol, market), tally in self.per_symbol.items()
            if tally.latest_bar_bad and membership.groups(series_key(symbol, market)) != ("other",)
        )

    def as_json(self, membership: Membership | None) -> dict[str, Any]:
        affected = []
        for (symbol, market), tally in sorted(self.per_symbol.items()):
            key = series_key(symbol, market)
            affected.append(
                {
                    "symbol": symbol,
                    "market": market,
                    "rows": tally.rows,
                    "first_date": tally.first,
                    "last_date": tally.last,
                    "latest_cached_bar_is_bad": tally.latest_bar_bad,
                    "latest_is_bad": tally.latest_bar_bad,
                    "older_bad_rows": tally.older_rows,
                    "held": None if membership is None else key in membership.held,
                    "watched": None if membership is None else key in membership.watched,
                }
            )
        return {
            "present": True,
            "on_alert_path": self.on_alert_path,
            "total_rows": self.total_rows,
            "bad_rows": {name: self.counts.get(name, 0) for name in VERDICT_CATEGORIES},
            "bad_rows_total": self.verdict_rows,
            "other_unusable_rows": {
                name: self.counts.get(name, 0) for name in LEGACY_OTHER_UNUSABLE
            },
            "affected_symbols": len(self.per_symbol),
            "date_range": {"first": self.first, "last": self.last},
            "symbols_whose_latest_cached_bar_is_bad": sum(
                1 for tally in self.per_symbol.values() if tally.latest_bar_bad
            ),
            "membership_known": membership is not None,
            "latest_bar_bad": _bar_class_json(self.per_symbol, membership, latest=True),
            "older_bar_bad": _bar_class_json(self.per_symbol, membership, latest=False),
            "affected": affected,
        }


def open_read_only(db_path: Path) -> sqlite3.Connection:
    """Open ``db_path`` read-only; fails rather than creating a missing file."""
    uri = f"{db_path.resolve().as_uri()}?mode=ro"
    conn = sqlite3.connect(uri, uri=True)
    conn.execute("PRAGMA query_only = ON")
    return conn


def _table_exists(conn: sqlite3.Connection, table: str) -> bool:
    row = conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = ?", (table,)
    ).fetchone()
    return row is not None


def scan_table(
    conn: sqlite3.Connection, table: str, date_column: str, *, on_alert_path: bool
) -> TableReport:
    """Classify every row's close in ``table`` (names come from KNOWN_TABLES only)."""
    report = TableReport(table=table, on_alert_path=on_alert_path)
    (report.total_rows,) = conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()
    # Latest date per series, to tell whether a bad row is the one a fresh
    # snapshot would read as "the latest bar". Only rows the app's cache reader
    # keeps are candidates (see the module docstring).
    latest: dict[tuple[object, object], date] = {}
    for symbol, market, day, close in conn.execute(
        f"SELECT symbol, market, {date_column}, close FROM {table}"
    ):
        parsed = parse_day(day)
        if parsed is None or classify_close(close) == "unparseable":
            continue
        key = (symbol, market)
        if key not in latest or parsed > latest[key]:
            latest[key] = parsed
    cursor = conn.execute(f"SELECT symbol, market, {date_column}, close FROM {table}")
    for symbol, market, day, close in cursor:
        category = classify_close(close)
        if category is None:
            continue
        report.counts[category] = report.counts.get(category, 0) + 1
        if category not in VERDICT_CATEGORIES:
            continue
        day_text = str(day)
        report.first = day_text if report.first is None else min(report.first, day_text)
        report.last = day_text if report.last is None else max(report.last, day_text)
        tally = report.per_symbol.setdefault((str(symbol), str(market)), SymbolTally())
        tally.rows += 1
        tally.first = day_text if tally.first is None else min(tally.first, day_text)
        tally.last = day_text if tally.last is None else max(tally.last, day_text)
        parsed = parse_day(day)
        if parsed is not None and latest.get((symbol, market)) == parsed:
            tally.latest_bar_bad = True
        else:
            tally.older_rows += 1
    return report


def _missing_columns(conn: sqlite3.Connection, table: str) -> list[str]:
    present = {row[1] for row in conn.execute(f"PRAGMA table_info({table})")}
    return [column for column in MEMBERSHIP_COLUMNS[table] if column not in present]


def read_membership(conn: sqlite3.Connection) -> Membership | None:
    """Held / watched series from ``--db``, or ``None`` if neither table is there.

    Raises ``LookupError`` when only one of the two tables is present or a
    required column is missing: a half-known membership would silently put
    held or watched series into ``other``.
    """
    present = {table: _table_exists(conn, table) for table in MEMBERSHIP_COLUMNS}
    if not any(present.values()):
        return None
    absent = [table for table, found in present.items() if not found]
    if absent:
        raise LookupError(f"table {', '.join(absent)} is not in this database")
    for table in MEMBERSHIP_COLUMNS:
        missing = _missing_columns(conn, table)
        if missing:
            raise LookupError(f"table {table} has no column {', '.join(missing)}")
    held = frozenset(
        series_key(symbol, market)
        for symbol, market in conn.execute(f"SELECT symbol, market FROM {POSITIONS_TABLE}")
    )
    watched = frozenset(
        series_key(symbol, market)
        for symbol, market in conn.execute(
            f"SELECT symbol, market FROM {ALERT_RULES_TABLE} WHERE enabled = 1"
        )
    )
    return Membership(held=held, watched=watched)


def build_summary(db_path: Path) -> dict[str, Any]:
    """The JSON summary for ``db_path``; raises ``LookupError`` if no table is known."""
    tables: dict[str, Any] = {}
    reports: list[TableReport] = []
    with closing(open_read_only(db_path)) as conn:
        for table, date_column, on_alert_path in KNOWN_TABLES:
            # Placeholder first so the output keeps KNOWN_TABLES order.
            tables[table] = {"present": False, "on_alert_path": on_alert_path}
            if not _table_exists(conn, table):
                continue
            reports.append(scan_table(conn, table, date_column, on_alert_path=on_alert_path))
        if not reports:
            names = ", ".join(table for table, _, _ in KNOWN_TABLES)
            raise LookupError(f"none of the known daily-bar tables ({names}) is in this database")
        membership = read_membership(conn)
    alert_path = [report for report in reports if report.on_alert_path]
    if alert_path and membership is None:
        raise LookupError(
            f"{alert_path[0].table} is here but {POSITIONS_TABLE} and {ALERT_RULES_TABLE} "
            "are not, so held / watched symbols cannot be told apart"
        )
    for report in reports:
        tables[report.table] = report.as_json(membership)
    alert_path_rows = sum(report.verdict_rows for report in alert_path)
    escalating: int | None = None
    escalation: str | None = None
    if not alert_path or membership is None:
        verdict = "alert_path_table_absent"
    else:
        verdict = "found" if alert_path_rows else "none_found"
        escalating = sum(report.held_or_watched_latest_bad(membership) for report in alert_path)
        escalation = ESCALATE if escalating else NOT_BLOCKING
    return {
        "check": "F-3 nonpositive close in cached daily bars",
        "generated_at": datetime.now(UTC).isoformat(timespec="seconds"),
        # The file name only: a full path can carry a user name.
        "db_file_name": db_path.name,
        "verdict": verdict,
        "escalation": escalation,
        "held_or_watched_symbols_whose_latest_bar_is_bad": escalating,
        "membership": (
            None
            if membership is None
            else {"held_symbols": len(membership.held), "watched_symbols": len(membership.watched)}
        ),
        "tables": tables,
    }


def _split_text(body: dict[str, Any]) -> str:
    text = f"{body['symbols']} symbol(s) / {body['rows']} row(s)"
    if body["held"] is None:
        return text + " (held / watched unknown)"
    parts = ", ".join(
        f"{name}={body[name]['symbols']}/{body[name]['rows']}" for name in MEMBERSHIP_GROUPS
    )
    return f"{text} [{parts}]"


def _console_lines(summary: dict[str, Any]) -> list[str]:
    lines = [f"F-3 verdict: {summary['verdict']}"]
    for table, body in summary["tables"].items():
        if not body["present"]:
            lines.append(f"  {table}: not in this database")
            continue
        lines.append(
            f"  {table}: {body['bad_rows_total']} bad row(s) "
            f"(nonpositive={body['bad_rows']['nonpositive']}, null={body['bad_rows']['null']}, "
            f"nonfinite={body['bad_rows']['nonfinite']}) "
            f"across {body['affected_symbols']} symbol(s), "
            f"{body['symbols_whose_latest_cached_bar_is_bad']} with a bad latest bar; "
            f"dates {body['date_range']['first']} .. {body['date_range']['last']}; "
            f"unparseable (skipped by the app): {body['other_unusable_rows']['unparseable']}; "
            f"{'on' if body['on_alert_path'] else 'not on'} the alert path"
        )
        lines.append(f"    latest bar bad: {_split_text(body['latest_bar_bad'])}")
        lines.append(f"    older bar bad:  {_split_text(body['older_bar_bad'])}")
    escalation = summary["escalation"]
    if escalation == ESCALATE:
        lines.append(
            "F-3 escalation: deploy_prerequisite -- "
            f"{summary['held_or_watched_symbols_whose_latest_bar_is_bad']} 檔持有或監看標的的"
            "最新 bar 為壞列（≥ 1）→ 升級部署前置，交 CEO 裁決。"
        )
    elif escalation == NOT_BLOCKING:
        lines.append(
            "F-3 escalation: next_release -- 持有或監看標的的最新 bar 壞列為 0"
            "（只有較舊列、只有 other，或查無）→ 不擋部署，排下一 release。"
        )
    return lines


def _parse_args(argv: list[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="F-3: count cached daily bars whose close is <= 0, NULL, NaN or "
        "Infinity (read-only)."
    )
    parser.add_argument("--db", required=True, type=Path, help="SQLite file to inspect")
    parser.add_argument("--out", type=Path, help="write the JSON summary here (UTF-8)")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    # Windows consoles default to cp950; keep stdout/stderr UTF-8 for redirection.
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure is not None:
            reconfigure(encoding="utf-8")
    args = _parse_args(argv)
    db_path: Path = args.db
    if not db_path.is_file():
        print(f"error: --db is not a file: {db_path.name}", file=sys.stderr)
        return 2
    if args.out is not None and args.out.resolve() == db_path.resolve():
        print("error: --out must not point at the --db file", file=sys.stderr)
        return 2
    try:
        summary = build_summary(db_path)
    except (sqlite3.Error, LookupError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2

    text = json.dumps(summary, ensure_ascii=False, indent=2)
    if args.out is not None:
        try:
            args.out.write_text(text + "\n", encoding="utf-8")
        except OSError as exc:
            print(f"error: cannot write --out file: {exc}", file=sys.stderr)
            return 2
        print(f"summary written to {args.out}", file=sys.stderr)
    else:
        print(text)
    for line in _console_lines(summary):
        print(line, file=sys.stderr)

    if summary["verdict"] == "alert_path_table_absent":
        print(
            "error: price_bars_cache is not in this database; point --db at the main DB",
            file=sys.stderr,
        )
        return 2
    return 1 if summary["verdict"] == "found" else 0


if __name__ == "__main__":
    sys.exit(main())

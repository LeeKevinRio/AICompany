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

``nonpositive`` and ``null`` together decide the verdict. ``nonfinite`` and
``unparseable`` rows are reported but do not, because the app's cache reader
already drops them (``app/data/cache.py``), so they cannot reach the alert path.

Tables (schemas copied from the app, not guessed):

* ``price_bars_cache`` (main DB, ``STOCK_DESK_DB_PATH``, default
  ``./data/stock-desk.db``): ``symbol, market, trade_date, ..., close TEXT``.
  This is the table the alert path reads, and the one the verdict is about.
* ``market_daily_bars`` (market DB, ``STOCK_DESK_MARKET_DB_PATH``, default
  ``./data/stock-desk-market.db``): ``symbol, session_date, market, ..., close
  TEXT``. Not on the alert path (ADR-0012 C-7); reported for reference only.

Hard guarantees
---------------
* Read-only: SQLite ``mode=ro`` URI plus ``PRAGMA query_only``; only SELECTs.
  The file is never created, migrated or written. Nothing is read from
  ``.env``. No network. Stdlib only.
* ``--db`` has no default on purpose. The output holds symbols, markets, dates
  and counts only -- no prices, quantities, costs, paths or credentials.

Exit codes: 0 = nothing found, 1 = rows found (see the summary), 2 = error.

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
from datetime import UTC, datetime
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any

#: (table, date column, whether the alert path reads it)
KNOWN_TABLES: tuple[tuple[str, str, bool], ...] = (
    ("price_bars_cache", "trade_date", True),
    ("market_daily_bars", "session_date", False),
)

#: Categories that decide the verdict, and the ones only reported.
VERDICT_CATEGORIES = ("nonpositive", "null")
REPORTED_CATEGORIES = ("nonfinite", "unparseable")


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


@dataclass
class SymbolTally:
    rows: int = 0
    first: str | None = None
    last: str | None = None
    latest_bar_bad: bool = False


@dataclass
class TableReport:
    table: str
    on_alert_path: bool
    total_rows: int = 0
    counts: dict[str, int] = field(default_factory=dict)
    first: str | None = None
    last: str | None = None
    per_symbol: dict[tuple[str, str], SymbolTally] = field(default_factory=dict)

    @property
    def verdict_rows(self) -> int:
        return sum(self.counts.get(name, 0) for name in VERDICT_CATEGORIES)

    def as_json(self) -> dict[str, Any]:
        affected = [
            {
                "symbol": symbol,
                "market": market,
                "rows": tally.rows,
                "first_date": tally.first,
                "last_date": tally.last,
                "latest_cached_bar_is_bad": tally.latest_bar_bad,
            }
            for (symbol, market), tally in sorted(self.per_symbol.items())
        ]
        return {
            "present": True,
            "on_alert_path": self.on_alert_path,
            "total_rows": self.total_rows,
            "bad_rows": {name: self.counts.get(name, 0) for name in VERDICT_CATEGORIES},
            "bad_rows_total": self.verdict_rows,
            "other_unusable_rows": {name: self.counts.get(name, 0) for name in REPORTED_CATEGORIES},
            "affected_symbols": len(self.per_symbol),
            "date_range": {"first": self.first, "last": self.last},
            "symbols_whose_latest_cached_bar_is_bad": sum(
                1 for tally in self.per_symbol.values() if tally.latest_bar_bad
            ),
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
    # snapshot would read as "the latest bar".
    latest: dict[tuple[str, str], str] = {
        (symbol, market): last
        for symbol, market, last in conn.execute(
            f"SELECT symbol, market, MAX({date_column}) FROM {table} GROUP BY symbol, market"
        )
    }
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
        if latest.get((symbol, market)) == day:
            tally.latest_bar_bad = True
    return report


def build_summary(db_path: Path) -> dict[str, Any]:
    """The JSON summary for ``db_path``; raises ``LookupError`` if no table is known."""
    tables: dict[str, Any] = {}
    reports: list[TableReport] = []
    with closing(open_read_only(db_path)) as conn:
        for table, date_column, on_alert_path in KNOWN_TABLES:
            if not _table_exists(conn, table):
                tables[table] = {"present": False, "on_alert_path": on_alert_path}
                continue
            report = scan_table(conn, table, date_column, on_alert_path=on_alert_path)
            reports.append(report)
            tables[table] = report.as_json()
    if not reports:
        names = ", ".join(table for table, _, _ in KNOWN_TABLES)
        raise LookupError(f"none of the known daily-bar tables ({names}) is in this database")
    alert_path_rows = sum(report.verdict_rows for report in reports if report.on_alert_path)
    alert_path_present = any(report.on_alert_path for report in reports)
    if not alert_path_present:
        verdict = "alert_path_table_absent"
    elif alert_path_rows:
        verdict = "found"
    else:
        verdict = "none_found"
    return {
        "check": "F-3 nonpositive close in cached daily bars",
        "generated_at": datetime.now(UTC).isoformat(timespec="seconds"),
        # The file name only: a full path can carry a user name.
        "db_file_name": db_path.name,
        "verdict": verdict,
        "tables": tables,
    }


def _console_lines(summary: dict[str, Any]) -> list[str]:
    lines = [f"F-3 verdict: {summary['verdict']}"]
    for table, body in summary["tables"].items():
        if not body["present"]:
            lines.append(f"  {table}: not in this database")
            continue
        lines.append(
            f"  {table}: {body['bad_rows_total']} bad row(s) "
            f"(nonpositive={body['bad_rows']['nonpositive']}, null={body['bad_rows']['null']}) "
            f"across {body['affected_symbols']} symbol(s), "
            f"{body['symbols_whose_latest_cached_bar_is_bad']} with a bad latest bar; "
            f"dates {body['date_range']['first']} .. {body['date_range']['last']}; "
            f"other unusable: {body['other_unusable_rows']}; "
            f"{'on' if body['on_alert_path'] else 'not on'} the alert path"
        )
    return lines


def _parse_args(argv: list[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="F-3: count cached daily bars whose close is <= 0 or NULL (read-only)."
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

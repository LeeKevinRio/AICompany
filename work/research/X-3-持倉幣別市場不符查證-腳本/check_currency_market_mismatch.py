"""X-3a: count holdings whose currency does not match their market (read-only).

Why this exists
---------------
A position is valued with the price source and FX leg picked from ``market``
and the cost basis read in ``currency``. The write doors only started refusing
a row where the two disagree in b7d67e1 (``currency_matches_market``); rows
written before that, by raw SQL or from an older backup can still be on the
CEO's real database, and nothing on screen flags them:

* ``US_stored_as_TWD`` (type A) -- a US holding stored in TWD is valued at the
  USD price times 1, about 1/31 of its worth, while the decision card still
  carries the USDTWD source sentence (a false disclosure);
* ``TW_stored_as_USD`` (type B) -- a TW holding stored in USD is multiplied by
  USDTWD, about 31 times its worth, which understates every *other* holding's
  share.

ADR-0017 asked for a read-only inventory of such rows before merging; it was
never run. This script replaces that SQL (task X-3, section 6 and KX-1..KX-5).

What it does
------------
Opens ``--db`` read-only, reads ``id, symbol, market, currency`` from every
``positions`` row (and nothing else: no quantity, cost, note, sector, dates)
and puts each row in exactly one class:

* ``matched``    -- ``currency`` is the one :data:`MARKET_CURRENCY` assigns
  ``market``;
* ``mismatch``   -- both values are in the app's ``Literal`` sets but disagree
  (the X-3 case), split by ``direction``;
* ``unreadable`` -- ``market`` or ``currency`` is outside the ``Literal`` sets
  (``'tw'``, ``' USD'``, ``'HKD'``, NULL ...). The app cannot even load such a
  row (``PositionStore.list_all`` raises), so it is a different failure; the
  raw values are reported with ``repr``.

Comparison is the app's: exact strings, no ``strip()``, no case folding.

``symbol_has_mixed_currencies`` marks a mismatch row whose exact
``(symbol, market)`` also has a row in another currency of the ``Literal`` set
(the E1 / PR-0 "two currencies under one holding" path).

Escalation (risk-compliance C-5): no mismatch and no unreadable row -> ``low``;
any mismatch row -> ``high``; any unreadable row -> ``high``.

Table and columns are the app's (``app/positions/store.py``), all in the main
DB that ``STOCK_DESK_DB_PATH`` points at.

Hard guarantees
---------------
* Read-only: SQLite ``mode=ro`` URI plus ``PRAGMA query_only``; only SELECTs
  and ``PRAGMA table_info``. The file is never created, migrated or written.
  Nothing is read from ``.env``. No network. Stdlib only.
* ``--db`` has no default on purpose. The output holds ids, symbols, markets
  and currencies only -- no quantities, costs, notes, paths or credentials.

Exit codes: 0 = nothing found, 1 = rows found (see ``escalation``), 2 = error
(missing file, no ``positions`` table, a missing column, ``--out`` pointing
at the DB or one of its ``-wal`` / ``-shm`` / ``-journal`` files).

The result is a snapshot of the moment it runs: restoring a backup taken
before b7d67e1, copying the DB from another machine or editing it with an
outside tool calls for a re-run (X3-F4); ``low`` does not mean it cannot
happen later.

Run::

    python check_currency_market_mismatch.py --db <path-to-stock-desk.db> --out X-3_out.json
"""

from __future__ import annotations

import argparse
import json
import sqlite3
import sys
from collections.abc import Mapping
from contextlib import closing
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Final

#: Copied from ``apps/stock-desk/backend/app/positions/models.py``
#: (``MARKET_CURRENCY``); the tests parse that file to keep the two equal.
MARKET_CURRENCY: Final[Mapping[str, str]] = {"TW": "TWD", "US": "USD"}

#: The app's ``Market`` / ``Currency`` ``Literal`` sets (same file).
MARKETS: Final = frozenset(MARKET_CURRENCY)
CURRENCIES: Final = frozenset(MARKET_CURRENCY.values())

#: Direction names of a ``mismatch`` row (``<market>_stored_as_<currency>``),
#: in output order: type A, then type B.
DIRECTIONS: Final[tuple[str, ...]] = ("US_stored_as_TWD", "TW_stored_as_USD")

POSITIONS_TABLE: Final = "positions"
#: The only columns read. Never quantity, avg_cost, note, sector or dates.
COLUMNS: Final[tuple[str, ...]] = ("id", "symbol", "market", "currency")

MATCHED: Final = "matched"
MISMATCH: Final = "mismatch"
UNREADABLE: Final = "unreadable"

ESCALATION_LOW: Final = "low"
ESCALATION_HIGH: Final = "high"

CHECK_NAME: Final = "X-3 position currency does not match market"


def classify(market: object, currency: object) -> str:
    """``matched`` / ``mismatch`` / ``unreadable`` for one stored row (exact match)."""
    if not (isinstance(market, str) and market in MARKETS):
        return UNREADABLE
    if not (isinstance(currency, str) and currency in CURRENCIES):
        return UNREADABLE
    return MATCHED if MARKET_CURRENCY[market] == currency else MISMATCH


def direction(market: str, currency: str) -> str:
    """The direction name of a ``mismatch`` row."""
    return f"{market}_stored_as_{currency}"


def _text(value: object) -> object:
    """A JSON-safe symbol: strings and NULL as they are, anything else as ``repr``."""
    return value if value is None or isinstance(value, str) else repr(value)


@dataclass
class Report:
    total_rows: int = 0
    matched_rows: int = 0
    by_direction: dict[str, int] = field(default_factory=lambda: dict.fromkeys(DIRECTIONS, 0))
    mismatch: list[dict[str, Any]] = field(default_factory=list)
    unreadable: list[dict[str, Any]] = field(default_factory=list)

    @property
    def mismatch_rows(self) -> int:
        return len(self.mismatch)

    @property
    def unreadable_rows(self) -> int:
        return len(self.unreadable)

    def counts_json(self) -> dict[str, Any]:
        return {
            "total_rows": self.total_rows,
            "matched_rows": self.matched_rows,
            "mismatch_rows": self.mismatch_rows,
            "mismatch_by_direction": dict(self.by_direction),
            "unreadable_rows": self.unreadable_rows,
        }


#: SQLite side files next to the DB; ``--out`` must not land on any of them.
SIDE_FILE_SUFFIXES: Final[tuple[str, ...]] = ("-wal", "-shm", "-journal")


def read_only_uri(db_path: Path) -> str:
    """The ``mode=ro`` URI for ``db_path`` (SQLite refuses writes and file creation)."""
    return f"{db_path.resolve().as_uri()}?mode=ro"


def protected_paths(db_path: Path) -> frozenset[Path]:
    """The DB file and its SQLite side files, resolved."""
    db = db_path.resolve()
    return frozenset({db, *(db.with_name(db.name + suffix) for suffix in SIDE_FILE_SUFFIXES)})


def open_read_only(db_path: Path) -> sqlite3.Connection:
    """Open ``db_path`` read-only; fails rather than creating a missing file."""
    conn = sqlite3.connect(read_only_uri(db_path), uri=True)
    conn.execute("PRAGMA query_only = ON")
    return conn


def _table_exists(conn: sqlite3.Connection, table: str) -> bool:
    row = conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = ?", (table,)
    ).fetchone()
    return row is not None


def _missing_columns(conn: sqlite3.Connection) -> list[str]:
    present = {row[1] for row in conn.execute(f"PRAGMA table_info({POSITIONS_TABLE})")}
    return [column for column in COLUMNS if column not in present]


def scan_positions(conn: sqlite3.Connection) -> Report:
    """Classify every ``positions`` row; raises ``LookupError`` on a missing column."""
    missing = _missing_columns(conn)
    if missing:
        raise LookupError(f"table {POSITIONS_TABLE} has no column {', '.join(missing)}")
    rows: list[tuple[Any, ...]] = conn.execute(
        f"SELECT {', '.join(COLUMNS)} FROM {POSITIONS_TABLE} ORDER BY id"
    ).fetchall()
    # Currencies of the Literal set seen per exact (symbol, market): a row the
    # app can load in another currency under the same key is the E1 / PR-0 path.
    currencies_by_key: dict[tuple[object, object], set[str]] = {}
    for _, symbol, market, currency in rows:
        if isinstance(currency, str) and currency in CURRENCIES:
            currencies_by_key.setdefault((symbol, market), set()).add(currency)

    report = Report(total_rows=len(rows))
    for row_id, symbol, market, currency in rows:
        kind = classify(market, currency)
        if kind == MATCHED:
            report.matched_rows += 1
        elif kind == MISMATCH:
            name = direction(market, currency)
            report.by_direction[name] += 1
            report.mismatch.append(
                {
                    "id": row_id,
                    "symbol": _text(symbol),
                    "market": market,
                    "currency": currency,
                    "direction": name,
                    "symbol_has_mixed_currencies": len(currencies_by_key[(symbol, market)]) > 1,
                }
            )
        else:
            report.unreadable.append(
                {
                    "id": row_id,
                    "symbol": _text(symbol),
                    "market_raw": repr(market),
                    "currency_raw": repr(currency),
                }
            )
    return report


def build_summary(db_path: Path) -> dict[str, Any]:
    """The JSON summary for ``db_path``."""
    with closing(open_read_only(db_path)) as conn:
        report = scan_positions(conn) if _table_exists(conn, POSITIONS_TABLE) else None
    summary: dict[str, Any] = {
        "check": CHECK_NAME,
        "generated_at": datetime.now(UTC).isoformat(timespec="seconds"),
        # The file name only: a full path can carry a user name.
        "db_file_name": db_path.name,
    }
    if report is None:
        summary.update(
            verdict="positions_table_absent",
            escalation=None,
            counts=None,
            mismatch=None,
            unreadable=None,
        )
        return summary
    found = report.mismatch_rows + report.unreadable_rows
    summary.update(
        verdict="found" if found else "none_found",
        escalation=ESCALATION_HIGH if found else ESCALATION_LOW,
        counts=report.counts_json(),
        mismatch=report.mismatch,
        unreadable=report.unreadable,
    )
    return summary


def verdict_sentence(summary: dict[str, Any]) -> str:
    """The one-line verdict (Traditional Chinese) printed last on stderr."""
    if summary["verdict"] == "positions_table_absent":
        return (
            "X-3 判定：無法判定——這個資料庫沒有 positions 表；"
            "請把 --db 指到 App 平常用的主資料庫（STOCK_DESK_DB_PATH）後重跑。"
        )
    counts = summary["counts"]
    if summary["escalation"] == ESCALATION_LOW:
        return (
            f"X-3 判定：low（僅代表執行當下）——共 {counts['total_rows']} 列持倉，"
            "幣別與市場不符 0 列、無法讀取 0 列；"
            "X-3 列管為「舊資料在本機不可達」（PR-0 legacy 雙幣別列管一併結案）。"
        )
    parts = []
    if counts["mismatch_rows"]:
        by_direction = counts["mismatch_by_direction"]
        parts.append(
            f"幣別與市場不符 {counts['mismatch_rows']} 列"
            f"（美股記成 TWD {by_direction['US_stored_as_TWD']} 列、"
            f"台股記成 USD {by_direction['TW_stored_as_USD']} 列）"
        )
    if counts["unreadable_rows"]:
        parts.append(
            f"市場或幣別無法讀取 {counts['unreadable_rows']} 列（另案處理，持倉 API 可能已經 500）"
        )
    return f"X-3 判定：high——{'、'.join(parts)}；先不要改任何資料，把 JSON 全文貼回給 coordinator。"


def _console_lines(summary: dict[str, Any]) -> list[str]:
    lines = [f"X-3 verdict: {summary['verdict']}"]
    counts = summary["counts"]
    if counts is not None:
        directions = ", ".join(
            f"{name}={count}" for name, count in counts["mismatch_by_direction"].items()
        )
        lines.append(
            f"  positions: {counts['total_rows']} row(s); matched={counts['matched_rows']}, "
            f"mismatch={counts['mismatch_rows']} ({directions}), "
            f"unreadable={counts['unreadable_rows']}"
        )
    return lines


def _parse_args(argv: list[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="X-3a: count positions whose currency does not match their market (read-only)."
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
    if args.out is not None and args.out.resolve() in protected_paths(db_path):
        print(
            "error: --out must not point at the --db file or its -wal / -shm / -journal file",
            file=sys.stderr,
        )
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
    if summary["verdict"] == "positions_table_absent":
        print(
            "error: positions is not in this database; point --db at the main DB",
            file=sys.stderr,
        )
    print(verdict_sentence(summary), file=sys.stderr)

    if summary["verdict"] == "positions_table_absent":
        return 2
    return 1 if summary["verdict"] == "found" else 0


if __name__ == "__main__":
    sys.exit(main())

"""N-207 pre-deployment inventory runner (N-212).

Run by the CEO on the local machine, against the real DB, before N-207 is deployed::

    python scripts/n207_preflight/run_preflight.py <path to the stock-desk DB>

Contract (TA v3 supplement 9):

* standard library only; no app import, no network;
* the DB is opened read-only through a ``file:<db>?mode=ro`` URI, so a write attempt fails;
* one line per item, ``<item>\\t<value>``; a multi-value item (P-2, P-3) joins its values
  with commas; boolean items print 0 or 1;
* a failing item prints ``<item>\\tERROR`` and the exit status is 1 -- an error is never
  printed as 0, and an incomplete inventory is not a clean one;
* never prints a symbol or an amount; error details are not echoed either;
* ``p4b_LOCAL_ONLY.sql`` lists symbols and is deliberately not in :data:`ITEMS`.
"""

from __future__ import annotations

import sqlite3
import sys
from collections.abc import Sequence
from contextlib import closing
from pathlib import Path
from urllib.parse import quote

SQL_DIR = Path(__file__).resolve().parent

#: Output label -> SQL file stem. Order is the print order. P-4b is not here on purpose.
ITEMS: tuple[tuple[str, str], ...] = (
    ("P-1", "p1"),
    ("P-2", "p2"),
    ("1d", "d1"),
    ("1d-2", "d1_2"),
    ("P-3", "p3"),
    ("P-4a", "p4a"),
    ("P-4c", "p4c"),
    ("P-5", "p5"),
    ("P-6", "p6"),
    ("P-7", "p7"),
    ("P-8", "p8"),
    ("P-9a", "p9a"),
    ("P-9b", "p9b"),
    ("P-9c", "p9c"),
)

ERROR = "ERROR"


def read_only_uri(db_path: str) -> str:
    """``file:`` URI that opens ``db_path`` with ``mode=ro`` (never creates the file)."""
    absolute = Path(db_path).resolve().as_posix()
    return f"file:{quote(absolute, safe='/')}?mode=ro"


def _format_row(row: Sequence[object]) -> str:
    values = []
    for value in row:
        # Only plain integers are printable; NULL or any other type means the SQL did
        # not honour the "count or boolean" contract, which is an error, not a zero.
        if type(value) is not int:
            raise ValueError("non-integer result")
        values.append(str(value))
    return ",".join(values)


def run_item(conn: sqlite3.Connection, stem: str) -> str:
    """Execute one SQL file and return its output value; raises on any problem."""
    sql = (SQL_DIR / f"{stem}.sql").read_text(encoding="utf-8")
    rows = conn.execute(sql).fetchall()
    if len(rows) != 1:
        raise ValueError("expected exactly one row")
    return _format_row(rows[0])


def run(db_path: str) -> tuple[list[str], bool]:
    """Return the output lines and whether every item succeeded."""
    lines: list[str] = []
    ok = True
    try:
        conn = sqlite3.connect(read_only_uri(db_path), uri=True)
    except sqlite3.Error:
        return [f"{label}\t{ERROR}" for label, _ in ITEMS], False
    with closing(conn):
        for label, stem in ITEMS:
            try:
                lines.append(f"{label}\t{run_item(conn, stem)}")
            except (sqlite3.Error, ValueError, OSError):
                lines.append(f"{label}\t{ERROR}")
                ok = False
    return lines, ok


def main(argv: Sequence[str] | None = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    if len(args) != 1:
        print("usage: run_preflight.py <db path>", file=sys.stderr)
        return 2
    lines, ok = run(args[0])
    for line in lines:
        print(line)
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())

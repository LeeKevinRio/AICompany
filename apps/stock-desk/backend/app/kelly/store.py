"""SQLite storage for the effective Kelly input of each ``(symbol, market)``.

Same database file and connection discipline as every other store in this
backend (``STOCK_DESK_DB_PATH`` via ``app.data.cache.resolve_db_path``, one
connection per operation, closed through ``contextlib.closing``); see
``app/positions/store.py`` for the original of that pattern.

One row per key, latest write wins, no history table (ADR-0006 D-2). What would
normally justify a history -- "where did this number come from" -- is answered
by the provenance columns on the row itself, so the question "which value is in
force right now" keeps exactly one answer.

Two rules this store enforces by construction:

* ``updated_at`` is written here and only here. :class:`KellyInputRecord`
  cannot carry one, so a client cannot backdate an input into looking fresher
  than it is.
* an expired row is **never** deleted automatically. Dropping it would erase
  the difference between "never entered" and "entered and gone stale", and
  those two states owe the user different sentences.

The import-attempt log lives in a separate module and a separate class
(:mod:`app.kelly.attempts`) so the read path that answers "what is in force"
and the append-only path that answers "how many times was this tried" cannot be
confused for one another (約束 35).
"""

from __future__ import annotations

import sqlite3
from contextlib import closing
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from app.data.cache import resolve_db_path
from app.kelly.models import KellyInputRecord, KellyInputRow, normalize_symbol
from app.positions.models import Market

_CREATE_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS kelly_inputs (
    symbol TEXT NOT NULL,
    market TEXT NOT NULL,
    win_rate REAL NOT NULL,
    payoff_ratio REAL NOT NULL,
    source TEXT NOT NULL,
    backtest_win_rate REAL,
    backtest_payoff_ratio REAL,
    strategy_id TEXT,
    window_start TEXT,
    window_end TEXT,
    oos_start_date TEXT,
    oos_end_date TEXT,
    produced_at TEXT,
    rates_verified INTEGER,
    dividend_reason_code TEXT,
    adjust_dividends INTEGER,
    oos_round_trips INTEGER,
    oos_win_trips INTEGER,
    oos_loss_trips INTEGER,
    oos_excluded_boundary_trips INTEGER,
    oos_open_trip_at_end INTEGER,
    oos_observations INTEGER,
    p_ci_low REAL,
    p_ci_high REAL,
    f_star REAL,
    f_star_ci_low REAL,
    f_star_ci_high REAL,
    bootstrap_seed INTEGER,
    bootstrap_draws INTEGER,
    bootstrap_degenerate_no_loss_draws INTEGER,
    bootstrap_degenerate_no_win_draws INTEGER,
    spec_hash TEXT,
    low_sample_warning INTEGER,
    k_observed_at_write INTEGER,
    updated_at TEXT NOT NULL,
    PRIMARY KEY (symbol, market)
)
"""

#: The stored columns, in table order. The record model declares exactly these
#: minus the server-written ``updated_at``; the assertion below keeps the two
#: from drifting, because a column that exists in one and not the other would
#: either be silently dropped on write or crash on read.
_COLUMNS: tuple[str, ...] = (*KellyInputRecord.model_fields, "updated_at")

assert _COLUMNS[:2] == ("symbol", "market")

#: Every nullable column with its declared type, for the additive migration
#: below. The two key columns, the effective pair, the source and the write
#: stamp are absent on purpose: they are NOT NULL, and SQLite cannot add a NOT
#: NULL column without a default, so a database missing one of those has to be
#: rebuilt rather than patched -- a state this table has never shipped in.
_OPTIONAL_COLUMN_TYPES: dict[str, str] = {
    "backtest_win_rate": "REAL",
    "backtest_payoff_ratio": "REAL",
    "strategy_id": "TEXT",
    "window_start": "TEXT",
    "window_end": "TEXT",
    "oos_start_date": "TEXT",
    "oos_end_date": "TEXT",
    "produced_at": "TEXT",
    "rates_verified": "INTEGER",
    "dividend_reason_code": "TEXT",
    "adjust_dividends": "INTEGER",
    "oos_round_trips": "INTEGER",
    "oos_win_trips": "INTEGER",
    "oos_loss_trips": "INTEGER",
    "oos_excluded_boundary_trips": "INTEGER",
    "oos_open_trip_at_end": "INTEGER",
    "oos_observations": "INTEGER",
    "p_ci_low": "REAL",
    "p_ci_high": "REAL",
    "f_star": "REAL",
    "f_star_ci_low": "REAL",
    "f_star_ci_high": "REAL",
    "bootstrap_seed": "INTEGER",
    "bootstrap_draws": "INTEGER",
    "bootstrap_degenerate_no_loss_draws": "INTEGER",
    "bootstrap_degenerate_no_win_draws": "INTEGER",
    "spec_hash": "TEXT",
    "low_sample_warning": "INTEGER",
    "k_observed_at_write": "INTEGER",
}

assert set(_OPTIONAL_COLUMN_TYPES) < set(_COLUMNS)

_SELECT_COLUMNS = ", ".join(_COLUMNS)
_PLACEHOLDERS = ", ".join("?" for _ in _COLUMNS)
#: The key columns are the conflict target, so they are never reassigned.
_UPSERT_ASSIGNMENTS = ", ".join(
    f"{column} = excluded.{column}" for column in _COLUMNS[2:]
)


def _missing_optional_columns(conn: sqlite3.Connection) -> list[str]:
    """Declared nullable columns the live table does not have, in table order."""
    existing = {column[1] for column in conn.execute("PRAGMA table_info(kelly_inputs)")}
    return [column for column in _OPTIONAL_COLUMN_TYPES if column not in existing]


def _migrate_add_optional_columns(conn: sqlite3.Connection) -> None:
    """Bring a pre-existing ``kelly_inputs`` up to the declared column set.

    ``ALTER TABLE ... ADD COLUMN`` with no NOT NULL/DEFAULT is the one schema
    change SQLite performs in place, so a database written by an earlier build
    keeps every row: the added columns read NULL, which is exactly the "this
    source recorded nothing here" state a manual input is already in. The
    migration classifies nothing on its own.

    No-op on a fresh database, where ``_CREATE_TABLE_SQL`` already declared
    every column, and idempotent, so it is safe on every store construction.

    Concurrency-safe, which a bare ``PRAGMA``-then-``ALTER`` is not: SQLite
    runs DDL outside the implicit transaction Python's sqlite3 opens for DML,
    so the backend and a CLI starting against the same database can both read
    "column missing" before either writes. The whole step therefore runs inside
    one ``BEGIN IMMEDIATE`` (the same device
    ``app.positions.store._migrate_opened_at_to_nullable`` uses): the write
    lock is taken up front, the loser blocks there until the winner commits and
    then re-checks the schema *inside* the lock, where it finds nothing left to
    do. Adding several columns is also atomic that way -- a crash between two
    ``ALTER``s cannot leave the table half-migrated.

    Must be called outside any open transaction, which holds for
    :meth:`KellyInputStore._init_schema`: everything before it is a PRAGMA or
    DDL, and Python's sqlite3 only opens implicit transactions for DML.
    """
    if not _missing_optional_columns(conn):
        return
    conn.execute("BEGIN IMMEDIATE")
    try:
        missing = _missing_optional_columns(conn)
        if not missing:
            # Another process finished while this one was blocked at BEGIN.
            # COMMIT rather than return, so the write lock is released here and
            # not at whatever later point the caller ends its work.
            conn.execute("COMMIT")
            return
        for column in missing:
            conn.execute(
                f"ALTER TABLE kelly_inputs ADD COLUMN {column} "
                f"{_OPTIONAL_COLUMN_TYPES[column]}"
            )
        conn.execute("COMMIT")
    except BaseException:
        conn.execute("ROLLBACK")
        raise


class KellyInputStore:
    """CRUD for ``kelly_inputs``: one effective row per ``(symbol, market)``."""

    def __init__(self, db_path: str | Path | None = None) -> None:
        self._db_path = Path(db_path) if db_path is not None else resolve_db_path()
        if str(self._db_path) != ":memory:":
            self._db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_schema()

    @property
    def db_path(self) -> Path:
        return self._db_path

    def _connect(self) -> sqlite3.Connection:
        # Callers wrap this in contextlib.closing; see the module docstring.
        return sqlite3.connect(self._db_path)

    def _init_schema(self) -> None:
        with closing(self._connect()) as conn, conn:
            conn.execute("PRAGMA journal_mode=WAL")
            conn.execute(_CREATE_TABLE_SQL)
            _migrate_add_optional_columns(conn)

    def list_all(self) -> list[KellyInputRow]:
        """Every stored input, ordered by key so the output is stable."""
        with closing(self._connect()) as conn:
            rows = conn.execute(
                f"SELECT {_SELECT_COLUMNS} FROM kelly_inputs ORDER BY symbol ASC, market ASC"
            ).fetchall()
        return [_row_to_input(row) for row in rows]

    def get(self, symbol: str, market: Market) -> KellyInputRow | None:
        """The input in force for one key, or ``None`` if none was ever written.

        ``None`` means "never entered". An expired row still comes back here --
        judging its age is the caller's job, and withholding it would leave the
        caller unable to tell the two apart.
        """
        with closing(self._connect()) as conn:
            row = conn.execute(
                f"SELECT {_SELECT_COLUMNS} FROM kelly_inputs WHERE symbol = ? AND market = ?",
                (normalize_symbol(symbol), market),
            ).fetchone()
        return None if row is None else _row_to_input(row)

    def upsert(
        self, record: KellyInputRecord, *, now: datetime | None = None
    ) -> KellyInputRow:
        """Write ``record`` as the input in force for its key; return it stored.

        ``now`` exists for tests and for a caller that already fixed a moment;
        it is still the *server's* clock either way, never a client's claim.
        Re-writing an unchanged pair advances ``updated_at`` on purpose: the
        user restating a figure is them confirming it still holds, which is
        precisely what the freshness rule asks of them.
        """
        moment = (now if now is not None else datetime.now(UTC)).isoformat()
        values = [getattr(record, name) for name in KellyInputRecord.model_fields]
        values.append(moment)
        with closing(self._connect()) as conn, conn:
            conn.execute(
                f"INSERT INTO kelly_inputs ({_SELECT_COLUMNS}) VALUES ({_PLACEHOLDERS}) "
                f"ON CONFLICT(symbol, market) DO UPDATE SET {_UPSERT_ASSIGNMENTS}",
                values,
            )
        stored = self.get(record.symbol, record.market)
        assert stored is not None  # just written within the same store
        return stored

    def delete(self, symbol: str, market: Market) -> bool:
        """Remove one input; ``True`` when a row was actually removed.

        Deliberately narrow: the import-attempt log is a different table in a
        different module and is **not** touched here (約束 35). Clearing an
        input the user no longer trusts must not also erase the record of how
        many imports they tried before keeping one.
        """
        with closing(self._connect()) as conn, conn:
            cursor = conn.execute(
                "DELETE FROM kelly_inputs WHERE symbol = ? AND market = ?",
                (normalize_symbol(symbol), market),
            )
            return cursor.rowcount > 0


def _row_to_input(row: tuple[Any, ...]) -> KellyInputRow:
    # sqlite3 hands back dynamically typed cells (and 0/1 for the boolean
    # columns); the model's validators enforce the real invariants -- including
    # the ranges on the pair -- at construction.
    return KellyInputRow.model_validate(dict(zip(_COLUMNS, row, strict=True)))

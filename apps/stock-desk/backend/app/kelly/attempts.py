"""Append-only log of every ``import-backtest`` attempt (ADR-0006 D-2).

Same database file and connection discipline as ``app/kelly/store.py`` and the
rest of the backend; the append-only shape follows ``alert_events`` in
``app/alerts/store.py``, which is append-only for the same reason: a row here
records *something that happened*, and something that happened does not stop
having happened when the user changes their mind.

A separate module and a separate class from :class:`KellyInputStore` on
purpose (約束 35). These two tables answer questions that must never be
confused:

* ``kelly_inputs`` -- "which pair is in force for this symbol". One row,
  overwritten.
* ``kelly_import_attempts`` -- "how many times was an import tried here, and
  how many of those were refused". Many rows, never rewritten, never removed --
  including the refused ones, which are the majority and the whole point.

The only sanctioned reads are the two counts below (and, later, a distribution
view). Nothing that answers "what is in force" may read this table: the log can
be mined into a version chain of effective values, and that is exactly the
history the single-row rule exists to not keep.

``K_observed`` is what the selection-bias disclosure rests on (約束 30), so
this table grows monotonically by design. Removing rows would under-report it,
which biases the disclosure in the flattering direction.
"""

from __future__ import annotations

import sqlite3
from contextlib import closing
from datetime import UTC, datetime
from pathlib import Path

from app.data.cache import resolve_db_path
from app.kelly.models import KellyAttemptRecord, normalize_symbol
from app.positions.models import Market

_CREATE_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS kelly_import_attempts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    symbol TEXT NOT NULL,
    market TEXT NOT NULL,
    strategy_id TEXT NOT NULL,
    request_spec TEXT NOT NULL,
    spec_hash TEXT NOT NULL,
    outcome TEXT NOT NULL,
    reason_code TEXT,
    win_rate REAL,
    payoff_ratio REAL,
    kelly_fraction REAL,
    oos_round_trips INTEGER,
    oos_win_trips INTEGER,
    oos_loss_trips INTEGER,
    oos_excluded_boundary_trips INTEGER,
    oos_open_trip_at_end INTEGER,
    oos_start_date TEXT,
    oos_end_date TEXT,
    oos_observations INTEGER,
    f_star_ci_low REAL,
    f_star_ci_high REAL,
    attempted_at TEXT NOT NULL
)
"""

_CREATE_INDEX_SQL = """
CREATE INDEX IF NOT EXISTS idx_kelly_attempts_symbol_time
ON kelly_import_attempts (symbol, market, attempted_at DESC)
"""

#: Written columns in table order: the record's fields plus the server stamp.
#: ``id`` is assigned by SQLite and is absent from both.
_COLUMNS: tuple[str, ...] = (*KellyAttemptRecord.model_fields, "attempted_at")

_INSERT_COLUMNS = ", ".join(_COLUMNS)
_PLACEHOLDERS = ", ".join("?" for _ in _COLUMNS)


class KellyAttemptStore:
    """Append and count rows of ``kelly_import_attempts``. Nothing else.

    The class deliberately offers no way to change or remove a row -- not a
    narrow one, not a private one. A reviewer can confirm that by reading this
    file: it contains no statement that would rewrite or drop anything.
    """

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
            conn.execute(_CREATE_INDEX_SQL)

    def append(
        self, record: KellyAttemptRecord, *, attempted_at: datetime | None = None
    ) -> int:
        """Record one attempt; return the id SQLite assigned it.

        Called for every attempt that got past request validation, whatever the
        gate then decided: ``record.outcome`` carries the gate's verdict, not
        whether an input row was subsequently written. The two are decided at
        different moments, which is what lets the attempt be logged first and
        the input written after, with no transaction spanning two stores.

        A failure here must not be swallowed by the caller: an import that
        proceeded without its attempt being recorded would under-report
        ``K_observed`` for good.
        """
        moment = (
            attempted_at if attempted_at is not None else datetime.now(UTC)
        ).isoformat()
        values = [getattr(record, name) for name in KellyAttemptRecord.model_fields]
        values.append(moment)
        with closing(self._connect()) as conn, conn:
            cursor = conn.execute(
                f"INSERT INTO kelly_import_attempts ({_INSERT_COLUMNS}) "
                f"VALUES ({_PLACEHOLDERS})",
                values,
            )
            return int(cursor.lastrowid or 0)

    def k_observed(self, symbol: str, market: Market) -> int:
        """Every attempt ever made on one instrument (約束 30).

        Refused attempts included, every strategy included, no time window --
        the definition is fixed here and restated in the disclosure, so the
        count cannot quietly become the flattering one.
        """
        with closing(self._connect()) as conn:
            row = conn.execute(
                "SELECT COUNT(*) FROM kelly_import_attempts WHERE symbol = ? AND market = ?",
                (normalize_symbol(symbol), market),
            ).fetchone()
        return int(row[0]) if row else 0

    def k_distinct_specs(self, symbol: str, market: Market) -> int:
        """How many *distinct* request specs were tried on one instrument.

        Stored alongside :meth:`k_observed` because the two are biased in
        opposite directions: repeating one spec inflates the first without
        widening the search, and this one hides repetition. The disclosure
        shows both rather than whichever reads better.
        """
        with closing(self._connect()) as conn:
            row = conn.execute(
                "SELECT COUNT(DISTINCT spec_hash) FROM kelly_import_attempts "
                "WHERE symbol = ? AND market = ?",
                (normalize_symbol(symbol), market),
            ).fetchone()
        return int(row[0]) if row else 0

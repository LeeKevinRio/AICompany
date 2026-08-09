"""SQLite-backed CRUD store for portfolio positions.

Shares the same database file as the price-bar cache (the
``STOCK_DESK_DB_PATH`` environment variable, default ``./data/stock-desk.db``)
per ADR-0002's single-machine, single-user deployment. Money columns are
stored as TEXT so ``Decimal`` values round-trip exactly instead of being
coerced through SQLite's float affinity.

Connections are opened per operation and always closed via
``contextlib.closing`` (the sqlite3 connection context manager only handles
the transaction, not the handle).
"""

from __future__ import annotations

import sqlite3
from contextlib import closing
from datetime import UTC, date, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any

from app.data.cache import resolve_db_path
from app.positions.models import Position, PositionInput

#: Parameterised by table name so the schema migration can build the
#: replacement table from the exact same definition as the live one.
_CREATE_TABLE_SQL_TEMPLATE = """
CREATE TABLE IF NOT EXISTS {table} (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    symbol TEXT NOT NULL,
    market TEXT NOT NULL,
    quantity TEXT NOT NULL,
    avg_cost TEXT NOT NULL,
    currency TEXT NOT NULL,
    opened_at TEXT,
    instrument_type TEXT NOT NULL,
    sector TEXT,
    note TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
)
"""

_CREATE_TABLE_SQL = _CREATE_TABLE_SQL_TEMPLATE.format(table="positions")

#: Scratch table used only while rebuilding ``positions`` (see the migration).
_MIGRATION_TABLE = "positions_opened_at_nullable"

_COLUMNS = (
    "id",
    "symbol",
    "market",
    "quantity",
    "avg_cost",
    "currency",
    "opened_at",
    "instrument_type",
    "sector",
    "note",
    "created_at",
    "updated_at",
)

_SELECT_COLUMNS = ", ".join(_COLUMNS)


def _opened_at_to_db(opened_at: date | None) -> str | None:
    """Store an unstated open date as SQL NULL, never as a placeholder date."""
    return None if opened_at is None else opened_at.isoformat()


def _migrate_add_sector(conn: sqlite3.Connection) -> None:
    """Add the nullable ``sector`` column to a database created before FR-12.

    Adding a nullable column is the one schema change SQLite supports in place,
    so no table rebuild is needed here. Existing rows keep a NULL sector, which
    is exactly the "not stated" state (AC-12.3): the migration classifies
    nothing on the user's behalf.

    Runs **before** the ``opened_at`` rebuild below, which copies a fixed column
    list between two tables and would not find ``sector`` on a legacy one.
    Idempotent, so it is safe to call on every startup.
    """
    columns = {column[1] for column in conn.execute("PRAGMA table_info(positions)")}
    if "sector" in columns:
        return
    conn.execute("ALTER TABLE positions ADD COLUMN sector TEXT")


def _migrate_opened_at_to_nullable(conn: sqlite3.Connection) -> None:
    """Drop the legacy ``opened_at TEXT NOT NULL`` constraint if still present.

    Databases created before the open date became optional declare the column
    ``NOT NULL``, and SQLite cannot drop a column constraint in place. The
    documented workaround is to rebuild: create the table under its new
    definition, copy every row over, drop the old one and rename. This table
    has no indexes, triggers or foreign keys, so those steps are all it needs.

    Runs inside the caller's transaction and is a no-op once migrated, so it is
    safe to call on every startup.
    """
    columns = conn.execute("PRAGMA table_info(positions)").fetchall()
    # PRAGMA table_info columns: (cid, name, type, notnull, dflt_value, pk)
    legacy = any(column[1] == "opened_at" and column[3] for column in columns)
    if not legacy:
        return
    conn.execute(f"DROP TABLE IF EXISTS {_MIGRATION_TABLE}")  # leftover of a crash
    conn.execute(_CREATE_TABLE_SQL_TEMPLATE.format(table=_MIGRATION_TABLE))
    conn.execute(
        f"INSERT INTO {_MIGRATION_TABLE} ({_SELECT_COLUMNS}) "
        f"SELECT {_SELECT_COLUMNS} FROM positions"
    )
    conn.execute("DROP TABLE positions")
    conn.execute(f"ALTER TABLE {_MIGRATION_TABLE} RENAME TO positions")


class PositionStore:
    """CRUD access to the ``positions`` table, returning ``Position`` models."""

    def __init__(self, db_path: str | Path | None = None) -> None:
        self._db_path = Path(db_path) if db_path is not None else resolve_db_path()
        if str(self._db_path) != ":memory:":
            self._db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_schema()

    @property
    def db_path(self) -> Path:
        return self._db_path

    def _connect(self) -> sqlite3.Connection:
        # Callers wrap this in contextlib.closing; see module docstring.
        return sqlite3.connect(self._db_path)

    def _init_schema(self) -> None:
        with closing(self._connect()) as conn, conn:
            conn.execute("PRAGMA journal_mode=WAL")
            conn.execute(_CREATE_TABLE_SQL)
            _migrate_add_sector(conn)
            _migrate_opened_at_to_nullable(conn)

    def list_all(self) -> list[Position]:
        """Return every stored position, ordered by id ascending."""
        with closing(self._connect()) as conn:
            cursor = conn.execute(
                f"SELECT {_SELECT_COLUMNS} FROM positions ORDER BY id ASC"
            )
            rows = cursor.fetchall()
        return [self._row_to_position(row) for row in rows]

    def get(self, position_id: int) -> Position | None:
        """Return the position with ``position_id`` or ``None`` if absent."""
        with closing(self._connect()) as conn:
            cursor = conn.execute(
                f"SELECT {_SELECT_COLUMNS} FROM positions WHERE id = ?",
                (position_id,),
            )
            row = cursor.fetchone()
        return self._row_to_position(row) if row is not None else None

    def create(self, data: PositionInput, *, now: datetime | None = None) -> Position:
        """Insert a new position and return it with its assigned id/timestamps."""
        moment = (now if now is not None else datetime.now(UTC)).isoformat()
        with closing(self._connect()) as conn, conn:
            cursor = conn.execute(
                """
                INSERT INTO positions
                    (symbol, market, quantity, avg_cost, currency, opened_at,
                     instrument_type, sector, note, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    data.symbol,
                    data.market,
                    str(data.quantity),
                    str(data.avg_cost),
                    data.currency,
                    _opened_at_to_db(data.opened_at),
                    data.instrument_type,
                    data.sector,
                    data.note,
                    moment,
                    moment,
                ),
            )
            new_id = int(cursor.lastrowid or 0)
        created = self.get(new_id)
        assert created is not None  # just inserted within the same store
        return created

    def update(
        self, position_id: int, data: PositionInput, *, now: datetime | None = None
    ) -> Position | None:
        """Overwrite the user fields of ``position_id``; return the updated row.

        Returns ``None`` if no position with that id exists. ``created_at`` is
        preserved; only ``updated_at`` advances.
        """
        moment = (now if now is not None else datetime.now(UTC)).isoformat()
        with closing(self._connect()) as conn, conn:
            cursor = conn.execute(
                """
                UPDATE positions SET
                    symbol = ?, market = ?, quantity = ?, avg_cost = ?,
                    currency = ?, opened_at = ?, instrument_type = ?,
                    sector = ?, note = ?, updated_at = ?
                WHERE id = ?
                """,
                (
                    data.symbol,
                    data.market,
                    str(data.quantity),
                    str(data.avg_cost),
                    data.currency,
                    _opened_at_to_db(data.opened_at),
                    data.instrument_type,
                    data.sector,
                    data.note,
                    moment,
                    position_id,
                ),
            )
            if cursor.rowcount == 0:
                return None
        return self.get(position_id)

    def delete(self, position_id: int) -> bool:
        """Delete ``position_id``; return ``True`` if a row was removed."""
        with closing(self._connect()) as conn, conn:
            cursor = conn.execute(
                "DELETE FROM positions WHERE id = ?", (position_id,)
            )
            return cursor.rowcount > 0

    @staticmethod
    def _row_to_position(row: tuple[Any, ...]) -> Position:
        # sqlite3 hands back dynamically typed cells; Position's validators
        # (and the enum Literals) enforce the real invariants at construction.
        (
            row_id,
            symbol,
            market,
            quantity,
            avg_cost,
            currency,
            opened_at,
            instrument_type,
            sector,
            note,
            created_at,
            updated_at,
        ) = row
        return Position(
            id=int(row_id),
            symbol=str(symbol),
            market=market,
            quantity=Decimal(str(quantity)),
            avg_cost=Decimal(str(avg_cost)),
            currency=currency,
            opened_at=None if opened_at is None else date.fromisoformat(str(opened_at)),
            instrument_type=instrument_type,
            sector=None if sector is None else str(sector),
            note=None if note is None else str(note),
            created_at=datetime.fromisoformat(str(created_at)),
            updated_at=datetime.fromisoformat(str(updated_at)),
        )

"""Store-level behaviour of the optional open date and its schema migration."""

from __future__ import annotations

import sqlite3
import threading
from contextlib import closing
from datetime import date
from decimal import Decimal
from pathlib import Path
from typing import cast

import pytest

from app.positions.models import PositionInput
from app.positions.store import (
    _MIGRATION_TABLE,
    PositionStore,
    _migrate_add_sector,
    _migrate_opened_at_to_nullable,
)

#: The pre-migration schema, with ``opened_at`` still declared NOT NULL.
_LEGACY_CREATE_TABLE_SQL = """
CREATE TABLE positions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    symbol TEXT NOT NULL,
    market TEXT NOT NULL,
    quantity TEXT NOT NULL,
    avg_cost TEXT NOT NULL,
    currency TEXT NOT NULL,
    opened_at TEXT NOT NULL,
    instrument_type TEXT NOT NULL,
    note TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
)
"""


def _an_input(*, opened_at: date | None, sector: str | None = None) -> PositionInput:
    return PositionInput(
        symbol="2330",
        market="TW",
        quantity=Decimal("1000"),
        avg_cost=Decimal("600.5"),
        currency="TWD",
        opened_at=opened_at,
        instrument_type="stock",
        sector=sector,
        note=None,
    )


def _opened_at_is_nullable(db_path: Path) -> bool:
    with closing(sqlite3.connect(db_path)) as conn:
        columns = conn.execute("PRAGMA table_info(positions)").fetchall()
    return not any(column[1] == "opened_at" and column[3] for column in columns)


def _seed_legacy_db(db_path: Path) -> None:
    with closing(sqlite3.connect(db_path)) as conn, conn:
        conn.execute(_LEGACY_CREATE_TABLE_SQL)
        conn.execute(
            """
            INSERT INTO positions
                (symbol, market, quantity, avg_cost, currency, opened_at,
                 instrument_type, note, created_at, updated_at)
            VALUES ('2330', 'TW', '1000', '600.5', 'TWD', '2024-01-02',
                    'stock', '台積電', '2024-01-02T00:00:00+00:00',
                    '2024-01-02T00:00:00+00:00')
            """
        )


def test_none_opened_at_round_trips_as_null(tmp_path: Path) -> None:
    store = PositionStore(db_path=tmp_path / "positions.db")
    created = store.create(_an_input(opened_at=None))
    assert created.opened_at is None
    assert store.get(created.id) is not None
    assert store.list_all()[0].opened_at is None

    with closing(sqlite3.connect(store.db_path)) as conn:
        stored = conn.execute("SELECT opened_at FROM positions").fetchone()[0]
    assert stored is None  # SQL NULL, not a placeholder date


def test_opened_at_can_be_set_and_cleared_by_update(tmp_path: Path) -> None:
    store = PositionStore(db_path=tmp_path / "positions.db")
    created = store.create(_an_input(opened_at=date(2024, 1, 2)))
    cleared = store.update(created.id, _an_input(opened_at=None))
    assert cleared is not None and cleared.opened_at is None
    restored = store.update(created.id, _an_input(opened_at=date(2024, 1, 2)))
    assert restored is not None and restored.opened_at == date(2024, 1, 2)


def test_legacy_not_null_schema_is_migrated_keeping_rows(tmp_path: Path) -> None:
    db_path = tmp_path / "positions.db"
    _seed_legacy_db(db_path)
    assert not _opened_at_is_nullable(db_path)

    store = PositionStore(db_path=db_path)

    assert _opened_at_is_nullable(db_path)
    existing = store.list_all()
    assert len(existing) == 1
    assert existing[0].id == 1
    assert existing[0].opened_at == date(2024, 1, 2)
    assert existing[0].note == "台積電"
    # The migrated table takes rows the old constraint would have rejected,
    # and ids keep advancing past the copied ones.
    created = store.create(_an_input(opened_at=None))
    assert created.id > 1
    assert created.opened_at is None


def test_migration_is_idempotent(tmp_path: Path) -> None:
    db_path = tmp_path / "positions.db"
    _seed_legacy_db(db_path)
    PositionStore(db_path=db_path)
    reopened = PositionStore(db_path=db_path)
    assert _opened_at_is_nullable(db_path)
    assert len(reopened.list_all()) == 1


# --- FR-12 sector column ------------------------------------------------------


def _has_sector_column(db_path: Path) -> bool:
    with closing(sqlite3.connect(db_path)) as conn:
        columns = conn.execute("PRAGMA table_info(positions)").fetchall()
    return any(column[1] == "sector" for column in columns)


def test_sector_round_trips_and_can_be_cleared(tmp_path: Path) -> None:
    store = PositionStore(db_path=tmp_path / "positions.db")
    created = store.create(_an_input(opened_at=None, sector="半導體業"))
    assert created.sector == "半導體業"
    assert store.list_all()[0].sector == "半導體業"
    cleared = store.update(created.id, _an_input(opened_at=None))
    assert cleared is not None and cleared.sector is None


def test_database_without_the_sector_column_is_migrated_keeping_rows(
    tmp_path: Path,
) -> None:
    # AC-12.3: an existing book survives the migration with every row intact
    # and every sector unstated -- nothing is classified on the user's behalf.
    db_path = tmp_path / "positions.db"
    _seed_legacy_db(db_path)
    assert not _has_sector_column(db_path)

    store = PositionStore(db_path=db_path)

    assert _has_sector_column(db_path)
    existing = store.list_all()
    assert len(existing) == 1
    assert existing[0].sector is None
    assert existing[0].note == "台積電"  # the opened_at rebuild still copied it
    stored = store.create(_an_input(opened_at=None, sector="食品工業"))
    assert store.get(stored.id) is not None
    assert store.get(stored.id).sector == "食品工業"  # type: ignore[union-attr]


def test_sector_migration_is_idempotent(tmp_path: Path) -> None:
    db_path = tmp_path / "positions.db"
    _seed_legacy_db(db_path)
    PositionStore(db_path=db_path)
    reopened = PositionStore(db_path=db_path)
    assert _has_sector_column(db_path)
    assert len(reopened.list_all()) == 1


# --- D7: concurrent migrators (品質債清償批 dispatch, 2026-08-16) -------------


class _FakeCursor:
    """Just enough cursor for the two ways the migrations consume a PRAGMA."""

    def __init__(self, rows: list[tuple[object, ...]]) -> None:
        self._rows = rows

    def fetchall(self) -> list[tuple[object, ...]]:
        return list(self._rows)

    def __iter__(self) -> object:
        return iter(self._rows)


class _StalePragmaConnection:
    """A connection whose ``PRAGMA table_info`` answers from before a migration.

    ``stale_answers`` bounds how many PRAGMA calls get the stale answer
    (``None`` = all of them); everything else is delegated to the real
    connection, so the statements the stale answer provokes hit the
    already-migrated table for real -- exactly what the loser of a
    two-process race sees. Every executed statement is recorded so a test
    can assert which path ran.
    """

    def __init__(
        self,
        conn: sqlite3.Connection,
        rows: list[tuple[object, ...]],
        stale_answers: int | None = None,
    ) -> None:
        self._conn = conn
        self._rows = rows
        self._remaining = stale_answers
        self.executed: list[str] = []

    def execute(self, sql: str) -> object:
        self.executed.append(sql)
        if sql.strip().upper().startswith("PRAGMA TABLE_INFO"):
            if self._remaining is None:
                return _FakeCursor(self._rows)
            if self._remaining > 0:
                self._remaining -= 1
                return _FakeCursor(self._rows)
        return self._conn.execute(sql)


#: ``PRAGMA table_info`` rows for the pre-sector, pre-rebuild schema:
#: (cid, name, type, notnull, dflt_value, pk) -- ``opened_at`` still NOT NULL.
_LEGACY_PRAGMA_ROWS: list[tuple[object, ...]] = [
    (0, "id", "INTEGER", 0, None, 1),
    (1, "symbol", "TEXT", 1, None, 0),
    (2, "market", "TEXT", 1, None, 0),
    (3, "quantity", "TEXT", 1, None, 0),
    (4, "avg_cost", "TEXT", 1, None, 0),
    (5, "currency", "TEXT", 1, None, 0),
    (6, "opened_at", "TEXT", 1, None, 0),
    (7, "instrument_type", "TEXT", 1, None, 0),
    (8, "note", "TEXT", 0, None, 0),
    (9, "created_at", "TEXT", 1, None, 0),
    (10, "updated_at", "TEXT", 1, None, 0),
]


def test_sector_migration_tolerates_a_column_added_between_the_check_and_the_alter(
    tmp_path: Path,
) -> None:
    """The TOCTOU window: the PRAGMA said "missing", the ALTER says "duplicate".

    Reproduced deterministically with a connection that answers ``PRAGMA
    table_info`` from the pre-migration schema while the table on disk is
    already migrated -- the loser of a two-process race swallows the
    ``duplicate column name`` error instead of crashing at startup.
    """
    db_path = tmp_path / "positions.db"
    _seed_legacy_db(db_path)
    PositionStore(db_path=db_path)  # the other process migrates first

    with closing(sqlite3.connect(db_path)) as conn, conn:
        stale = _StalePragmaConnection(conn, _LEGACY_PRAGMA_ROWS)
        _migrate_add_sector(cast(sqlite3.Connection, stale))

    with closing(sqlite3.connect(db_path)) as conn:
        columns = [column[1] for column in conn.execute("PRAGMA table_info(positions)")]
    assert columns.count("sector") == 1
    assert len(PositionStore(db_path=db_path).list_all()) == 1


def test_sector_migration_still_raises_an_unrelated_operational_error(
    tmp_path: Path,
) -> None:
    """Only "duplicate column name" is swallowed; a real failure stays loud."""
    db_path = tmp_path / "missing-table.db"
    with closing(sqlite3.connect(db_path)) as conn, conn:
        with pytest.raises(sqlite3.OperationalError, match="no such table"):
            _migrate_add_sector(conn)


def test_rebuild_migration_loser_rechecks_under_the_lock_and_leaves_data_alone(
    tmp_path: Path,
) -> None:
    """The loser of the rebuild race must no-op, not rebuild a second time.

    Deterministic version of the race: the first legacy check answers "still
    NOT NULL" although the table on disk is already rebuilt -- what a process
    sees when the winner finishes between its check and its ``BEGIN
    IMMEDIATE``. The re-check under the write lock (a real PRAGMA) must then
    stop it before any destructive statement runs.
    """
    db_path = tmp_path / "positions.db"
    _seed_legacy_db(db_path)
    PositionStore(db_path=db_path)  # the winner rebuilds first

    with closing(sqlite3.connect(db_path)) as conn:
        stale = _StalePragmaConnection(conn, _LEGACY_PRAGMA_ROWS, stale_answers=1)
        _migrate_opened_at_to_nullable(cast(sqlite3.Connection, stale))
        executed = stale.executed

    assert not any("DROP TABLE positions" in sql for sql in executed)
    assert not any("INSERT INTO" in sql for sql in executed)
    assert "COMMIT" in executed  # the lock was taken and released, nothing more
    store = PositionStore(db_path=db_path)
    rows = store.list_all()
    assert len(rows) == 1
    assert rows[0].note == "台積電"


def test_rebuild_migration_replaces_a_crash_leftover_scratch_table(tmp_path: Path) -> None:
    """A scratch table an interrupted older build left behind must not block the rebuild."""
    db_path = tmp_path / "positions.db"
    _seed_legacy_db(db_path)
    with closing(sqlite3.connect(db_path)) as conn, conn:
        conn.execute(f"CREATE TABLE {_MIGRATION_TABLE} (junk TEXT)")

    store = PositionStore(db_path=db_path)

    assert _opened_at_is_nullable(db_path)
    assert len(store.list_all()) == 1
    with closing(sqlite3.connect(db_path)) as conn:
        leftover = conn.execute(
            "SELECT name FROM sqlite_master WHERE name = ?", (_MIGRATION_TABLE,)
        ).fetchall()
    assert leftover == []


def test_two_stores_opening_the_same_legacy_database_at_once_both_survive(
    tmp_path: Path,
) -> None:
    """The backend and a CLI starting together must not corrupt the book.

    Both migrations race here: the ``ALTER`` one may hit "duplicate column"
    (swallowed) and the rebuild one is serialised by ``BEGIN IMMEDIATE`` --
    whichever process loses must find the work already done and leave the
    single copied row exactly as the winner wrote it.
    """
    db_path = tmp_path / "positions.db"
    _seed_legacy_db(db_path)
    barrier = threading.Barrier(2)
    failures: list[Exception] = []

    def open_store() -> None:
        try:
            barrier.wait(timeout=10)
            PositionStore(db_path=db_path)
        except Exception as error:  # noqa: BLE001 - collected for the assertion
            failures.append(error)

    threads = [threading.Thread(target=open_store) for _ in range(2)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=30)

    assert failures == []
    assert _opened_at_is_nullable(db_path)
    with closing(sqlite3.connect(db_path)) as conn:
        columns = [column[1] for column in conn.execute("PRAGMA table_info(positions)")]
        leftover = conn.execute(
            "SELECT name FROM sqlite_master WHERE name = ?", (_MIGRATION_TABLE,)
        ).fetchall()
    assert columns.count("sector") == 1
    assert leftover == []
    rows = PositionStore(db_path=db_path).list_all()
    assert len(rows) == 1
    assert rows[0].opened_at == date(2024, 1, 2)
    assert rows[0].note == "台積電"

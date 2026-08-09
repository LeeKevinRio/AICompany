"""Store-level behaviour of the optional open date and its schema migration."""

from __future__ import annotations

import sqlite3
from contextlib import closing
from datetime import date
from decimal import Decimal
from pathlib import Path

from app.positions.models import PositionInput
from app.positions.store import PositionStore

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

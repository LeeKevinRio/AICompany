"""Persistence of the directory's industry category, including the migration.

The migration test is the important one: the CEO's local database already
holds 11,779 directory rows written before the ``sector*`` columns existed,
and adding the feature must not require rebuilding or re-syncing it.
"""

from __future__ import annotations

import sqlite3
import threading
from contextlib import closing
from datetime import UTC, datetime
from pathlib import Path
from typing import cast

import pytest

from app.directory.models import DirectoryEntry, DirectorySectorAssignment
from app.directory.store import SecurityDirectoryStore, _migrate_add_sector_columns
from app.positions.models import PositionInput
from app.positions.store import PositionStore

AS_OF = datetime(2026, 8, 9, 12, 0, tzinfo=UTC)
SECTOR_AS_OF = datetime(2026, 8, 16, 3, 0, tzinfo=UTC)

#: The exact ``security_directory`` definition that shipped before this batch.
_LEGACY_SCHEMA_SQL = """
CREATE TABLE security_directory (
    symbol TEXT NOT NULL,
    market TEXT NOT NULL,
    name TEXT NOT NULL,
    source TEXT NOT NULL,
    as_of TEXT NOT NULL,
    synced_at TEXT NOT NULL,
    PRIMARY KEY (symbol, market)
)
"""


#: The column list that legacy schema produces, in ``PRAGMA table_info`` order.
_LEGACY_COLUMNS = ("symbol", "market", "name", "source", "as_of", "synced_at")


class _StalePragmaConnection:
    """A connection whose ``PRAGMA table_info`` answers from before a migration.

    Everything else is delegated to the real connection, so the ``ALTER`` this
    stale answer provokes hits the already-migrated table for real.
    """

    def __init__(self, conn: sqlite3.Connection, columns: tuple[str, ...]) -> None:
        self._conn = conn
        self._columns = columns

    def execute(self, sql: str) -> object:
        if sql.strip().upper().startswith("PRAGMA TABLE_INFO"):
            return [(index, name, "TEXT", 0, None, 0) for index, name in enumerate(self._columns)]
        return self._conn.execute(sql)


def _column_names(db_path: Path) -> list[str]:
    with closing(sqlite3.connect(db_path)) as conn:
        return [column[1] for column in conn.execute("PRAGMA table_info(security_directory)")]


def _entry(symbol: str, name: str) -> DirectoryEntry:
    return DirectoryEntry(symbol=symbol, name=name, market="TW", source="twse_openapi", as_of=AS_OF)


def _assignment(symbol: str, sector: str) -> DirectorySectorAssignment:
    return DirectorySectorAssignment(
        symbol=symbol,
        market="TW",
        sector=sector,
        source="twse_openapi_t187ap03_L",
        as_of=SECTOR_AS_OF,
    )


def _write_legacy_db(db_path: Path, rows: int) -> None:
    """Create a pre-migration database holding ``rows`` directory entries."""
    with sqlite3.connect(db_path) as conn:
        conn.execute(_LEGACY_SCHEMA_SQL)
        conn.executemany(
            "INSERT INTO security_directory (symbol, market, name, source, as_of, synced_at) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            [
                (f"{1000 + i}", "TW", f"舊資料公司{i}", "twse_openapi", AS_OF.isoformat(),
                 AS_OF.isoformat())
                for i in range(rows)
            ],
        )
    conn.close()


# --------------------------------------------------------------------------
# Migration: an existing, populated database keeps every row
# --------------------------------------------------------------------------


def test_migration_adds_sector_columns_without_touching_existing_rows(tmp_path: Path) -> None:
    db_path = tmp_path / "legacy.db"
    _write_legacy_db(db_path, rows=25)

    store = SecurityDirectoryStore(db_path=db_path)

    assert store.count() == 25  # nothing rebuilt, nothing dropped
    entry = store.resolve("1000")
    assert entry is not None
    assert entry.name == "舊資料公司0"
    # Pre-existing rows are "no category known", never a placeholder value.
    assert entry.sector is None
    assert entry.sector_source is None
    assert entry.sector_as_of is None


def test_migration_is_idempotent_across_reopens(tmp_path: Path) -> None:
    db_path = tmp_path / "legacy.db"
    _write_legacy_db(db_path, rows=3)

    SecurityDirectoryStore(db_path=db_path)
    SecurityDirectoryStore(db_path=db_path)
    store = SecurityDirectoryStore(db_path=db_path)

    assert store.count() == 3
    with sqlite3.connect(db_path) as conn:
        columns = [column[1] for column in conn.execute("PRAGMA table_info(security_directory)")]
    conn.close()
    assert columns.count("sector") == 1
    assert columns.count("sector_source") == 1
    assert columns.count("sector_as_of") == 1


def test_migration_finishes_what_another_process_started(tmp_path: Path) -> None:
    """Only ``sector`` made it in before the other process died; finish the rest."""
    db_path = tmp_path / "legacy.db"
    _write_legacy_db(db_path, rows=4)
    with closing(sqlite3.connect(db_path)) as conn, conn:
        conn.execute("ALTER TABLE security_directory ADD COLUMN sector TEXT")

    store = SecurityDirectoryStore(db_path=db_path)

    assert store.count() == 4
    assert store.apply_sectors([_assignment("1000", "水泥工業")]) == 1


def test_migration_tolerates_a_column_added_between_the_check_and_the_alter(
    tmp_path: Path,
) -> None:
    """The TOCTOU window: the PRAGMA said "missing", the ALTER says "duplicate".

    Reproduced deterministically with a connection that answers ``PRAGMA
    table_info`` from the pre-migration schema while the table on disk is
    already migrated -- exactly what the loser of a two-process race sees.
    """
    db_path = tmp_path / "legacy.db"
    _write_legacy_db(db_path, rows=2)
    SecurityDirectoryStore(db_path=db_path)  # the other process migrates first

    with closing(sqlite3.connect(db_path)) as conn, conn:
        stale = _StalePragmaConnection(conn, _LEGACY_COLUMNS)
        _migrate_add_sector_columns(cast(sqlite3.Connection, stale))

    assert _column_names(db_path).count("sector") == 1
    assert SecurityDirectoryStore(db_path=db_path).count() == 2


def test_migration_still_raises_an_unrelated_operational_error(tmp_path: Path) -> None:
    """Only "duplicate column name" is swallowed; a real failure stays loud."""
    db_path = tmp_path / "missing-table.db"
    with closing(sqlite3.connect(db_path)) as conn, conn:
        with pytest.raises(sqlite3.OperationalError, match="no such table"):
            _migrate_add_sector_columns(conn)


def test_two_stores_opening_the_same_legacy_database_at_once_both_survive(
    tmp_path: Path,
) -> None:
    """The backend and the sync CLI starting together must not fight over the migration."""
    db_path = tmp_path / "legacy.db"
    _write_legacy_db(db_path, rows=5)
    barrier = threading.Barrier(2)
    failures: list[Exception] = []

    def open_store() -> None:
        try:
            barrier.wait(timeout=10)
            SecurityDirectoryStore(db_path=db_path)
        except Exception as error:
            failures.append(error)

    threads = [threading.Thread(target=open_store) for _ in range(2)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=30)

    assert failures == []
    columns = _column_names(db_path)
    for column in ("sector", "sector_source", "sector_as_of"):
        assert columns.count(column) == 1
    assert SecurityDirectoryStore(db_path=db_path).count() == 5


def test_migrated_database_accepts_sectors_and_keeps_them(tmp_path: Path) -> None:
    db_path = tmp_path / "legacy.db"
    _write_legacy_db(db_path, rows=2)
    store = SecurityDirectoryStore(db_path=db_path)

    assert store.apply_sectors([_assignment("1000", "水泥工業")]) == 1

    entry = store.resolve("1000")
    assert entry is not None
    assert entry.sector == "水泥工業"
    assert entry.sector_source == "twse_openapi_t187ap03_L"
    assert entry.sector_as_of == SECTOR_AS_OF


# --------------------------------------------------------------------------
# apply_sectors
# --------------------------------------------------------------------------


def test_apply_sectors_updates_only_existing_rows(tmp_path: Path) -> None:
    store = SecurityDirectoryStore(db_path=tmp_path / "d.db")
    store.upsert([_entry("2330", "台積電")])

    matched = store.apply_sectors([_assignment("2330", "半導體業"), _assignment("9999", "航運業")])

    # The 產業別 dataset naming a symbol the directory never listed does not
    # mint a directory row for it.
    assert matched == 1
    assert store.count() == 1
    assert store.resolve("9999") is None


def test_apply_sectors_is_idempotent(tmp_path: Path) -> None:
    store = SecurityDirectoryStore(db_path=tmp_path / "d.db")
    store.upsert([_entry("2330", "台積電")])

    assert store.apply_sectors([_assignment("2330", "半導體業")]) == 1
    assert store.apply_sectors([_assignment("2330", "半導體業")]) == 1

    entry = store.resolve("2330")
    assert entry is not None
    assert entry.sector == "半導體業"


def test_upsert_rerun_does_not_clear_an_existing_sector(tmp_path: Path) -> None:
    """A name refresh must not blank the category the sector pass established."""
    store = SecurityDirectoryStore(db_path=tmp_path / "d.db")
    store.upsert([_entry("2330", "台積電")])
    store.apply_sectors([_assignment("2330", "半導體業")])

    store.upsert([_entry("2330", "台積電（更新後名稱）")])

    entry = store.resolve("2330")
    assert entry is not None
    assert entry.name == "台積電（更新後名稱）"
    assert entry.sector == "半導體業"


def test_apply_sectors_with_no_assignments_writes_nothing(tmp_path: Path) -> None:
    store = SecurityDirectoryStore(db_path=tmp_path / "d.db")
    store.upsert([_entry("2330", "台積電")])
    assert store.apply_sectors([]) == 0
    assert store.sector_count() == 0


def test_sector_count_counts_only_rows_with_a_category(tmp_path: Path) -> None:
    store = SecurityDirectoryStore(db_path=tmp_path / "d.db")
    store.upsert([_entry("2330", "台積電"), _entry("0050", "元大台灣50")])
    store.apply_sectors([_assignment("2330", "半導體業")])

    assert store.count() == 2
    assert store.sector_count() == 1


def test_search_carries_the_sector_through(tmp_path: Path) -> None:
    store = SecurityDirectoryStore(db_path=tmp_path / "d.db")
    store.upsert([_entry("2330", "台積電")])
    store.apply_sectors([_assignment("2330", "半導體業")])

    items, _truncated = store.search("2330", limit=12)

    assert len(items) == 1
    assert items[0].sector == "半導體業"


# --------------------------------------------------------------------------
# DirectoryEntry's all-or-nothing provenance rule
# --------------------------------------------------------------------------


def test_entry_rejects_a_sector_without_its_provenance() -> None:
    with pytest.raises(ValueError, match="sector_source"):
        DirectoryEntry(
            symbol="2330",
            name="台積電",
            market="TW",
            source="twse_openapi",
            as_of=AS_OF,
            sector="半導體業",
        )


# --------------------------------------------------------------------------
# PositionStore.fill_sector_if_empty -- the narrow write the backfill uses
# --------------------------------------------------------------------------


def _position(store: PositionStore, **overrides: object) -> int:
    payload: dict[str, object] = {
        "symbol": "2330",
        "market": "TW",
        "quantity": "1000",
        "avg_cost": "600.5",
        "currency": "TWD",
        "instrument_type": "stock",
    }
    payload.update(overrides)
    return store.create(PositionInput.model_validate(payload)).id


def test_fill_sector_if_empty_touches_only_the_sector_column(tmp_path: Path) -> None:
    store = PositionStore(db_path=tmp_path / "p.db")
    position_id = _position(store, note="不可被改動")
    before = store.get(position_id)
    assert before is not None

    updated = store.fill_sector_if_empty(position_id, "半導體業")

    assert updated is not None
    assert updated.sector == "半導體業"
    assert updated.quantity == before.quantity
    assert updated.avg_cost == before.avg_cost
    assert updated.note == "不可被改動"
    assert updated.created_at == before.created_at


def test_fill_sector_if_empty_refuses_to_replace_an_existing_category(tmp_path: Path) -> None:
    """The compare-and-set half: the stored value wins, and nothing moves."""
    store = PositionStore(db_path=tmp_path / "p.db")
    position_id = _position(store, sector="其他業")
    before = store.get(position_id)
    assert before is not None

    assert store.fill_sector_if_empty(position_id, "半導體業") is None

    stored = store.get(position_id)
    assert stored is not None
    assert stored.sector == "其他業"
    assert stored.updated_at == before.updated_at  # not even a touch


def test_fill_sector_if_empty_treats_a_blank_stored_value_as_empty(tmp_path: Path) -> None:
    """A row an older build left as ``''`` is "not stated", so it is fillable."""
    store = PositionStore(db_path=tmp_path / "p.db")
    position_id = _position(store)
    with closing(sqlite3.connect(store.db_path)) as conn, conn:
        conn.execute("UPDATE positions SET sector = '  ' WHERE id = ?", (position_id,))

    updated = store.fill_sector_if_empty(position_id, "半導體業")

    assert updated is not None
    assert updated.sector == "半導體業"


def test_fill_sector_if_empty_rejects_a_value_outside_the_closed_list(tmp_path: Path) -> None:
    store = PositionStore(db_path=tmp_path / "p.db")
    position_id = _position(store)

    with pytest.raises(ValueError):
        store.fill_sector_if_empty(position_id, "自創產業")

    stored = store.get(position_id)
    assert stored is not None
    assert stored.sector is None


def test_fill_sector_if_empty_rejects_blank(tmp_path: Path) -> None:
    store = PositionStore(db_path=tmp_path / "p.db")
    position_id = _position(store)

    with pytest.raises(ValueError, match="blank"):
        store.fill_sector_if_empty(position_id, "   ")


def test_fill_sector_if_empty_returns_none_for_an_unknown_position(tmp_path: Path) -> None:
    store = PositionStore(db_path=tmp_path / "p.db")
    assert store.fill_sector_if_empty(9999, "半導體業") is None

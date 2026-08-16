"""Persistence of the directory's industry category, including the migration.

The migration test is the important one: the CEO's local database already
holds 11,779 directory rows written before the ``sector*`` columns existed,
and adding the feature must not require rebuilding or re-syncing it.
"""

from __future__ import annotations

import sqlite3
from datetime import UTC, datetime
from pathlib import Path

import pytest

from app.directory.models import DirectoryEntry, DirectorySectorAssignment
from app.directory.store import SecurityDirectoryStore
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
# PositionStore.set_sector -- the narrow write the backfill uses
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


def test_set_sector_touches_only_the_sector_column(tmp_path: Path) -> None:
    store = PositionStore(db_path=tmp_path / "p.db")
    position_id = _position(store, note="不可被改動")
    before = store.get(position_id)
    assert before is not None

    updated = store.set_sector(position_id, "半導體業")

    assert updated is not None
    assert updated.sector == "半導體業"
    assert updated.quantity == before.quantity
    assert updated.avg_cost == before.avg_cost
    assert updated.note == "不可被改動"
    assert updated.created_at == before.created_at


def test_set_sector_rejects_a_value_outside_the_closed_list(tmp_path: Path) -> None:
    store = PositionStore(db_path=tmp_path / "p.db")
    position_id = _position(store)

    with pytest.raises(ValueError):
        store.set_sector(position_id, "自創產業")

    stored = store.get(position_id)
    assert stored is not None
    assert stored.sector is None


def test_set_sector_rejects_blank(tmp_path: Path) -> None:
    store = PositionStore(db_path=tmp_path / "p.db")
    position_id = _position(store)

    with pytest.raises(ValueError, match="blank"):
        store.set_sector(position_id, "   ")


def test_set_sector_returns_none_for_an_unknown_position(tmp_path: Path) -> None:
    store = PositionStore(db_path=tmp_path / "p.db")
    assert store.set_sector(9999, "半導體業") is None

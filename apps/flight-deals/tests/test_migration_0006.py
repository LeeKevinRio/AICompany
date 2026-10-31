"""Migration 0006: the snapshot covering index and the query plans it buys
(ADR-0002 FD-8 Decisions 4 and 2, C-58)."""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from flight_deals.storage import db as db_module
from flight_deals.storage.db import Database, backup_path, needs_foreign_keys_off
from flight_deals.storage.repository import (
    _SNAPSHOT_SCOPE_WATCH,
    SNAPSHOT_OBSERVATIONS_SQL,
    _snapshot_keep_select,
)
from tests.test_migration_0003 import ORIGINAL_MIGRATIONS, TABLES, counts, only_up_to
from tests.test_migration_0005 import build_v4_db

INDEX_SQL = (
    "CREATE INDEX ix_obs_snapshot ON price_observation(watch_id, watch_revision, price_kind,"
    " currency, depart_date, return_date, fetched_at DESC, id DESC, scan_run_id);"
)
INDEX_KEYS = [
    ("watch_id", 0),
    ("watch_revision", 0),
    ("price_kind", 0),
    ("currency", 0),
    ("depart_date", 0),
    ("return_date", 0),
    ("fetched_at", 1),
    ("id", 1),
    ("scan_run_id", 0),
]
READ_PARAMS = {
    "watch_id": 1,
    "revision": 1,
    "currency": "TWD",
    "today": "2026-10-25",
    "midnight": "2026-10-24T16:00:00+00:00",
}


def sql_0006() -> str:
    return dict(ORIGINAL_MIGRATIONS())[6]


def build_v5_db(path: Path, monkeypatch: pytest.MonkeyPatch) -> Database:
    database = build_v4_db(path, monkeypatch)
    monkeypatch.setattr(db_module, "available_migrations", only_up_to(5))
    assert database.migrate() == 5
    # Later migrations (0007+) have their own tests; stop at 6 here.
    monkeypatch.setattr(db_module, "available_migrations", only_up_to(6))
    return database


def test_0006_is_one_create_index_line() -> None:  # C-58
    sql = sql_0006()
    assert sql.strip() == INDEX_SQL
    assert len(sql.strip().splitlines()) == 1
    assert not needs_foreign_keys_off(sql)
    upper = sql.upper()
    for banned in ("CREATE TABLE", "DROP", "RENAME", "ALTER", "FOREIGN_KEYS"):
        assert banned not in upper, banned


def test_v5_data_survives_and_backup_is_taken(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:  # AC-Q10, C-58
    database = build_v5_db(tmp_path / "flight-deals.db", monkeypatch)
    before = counts(database)
    assert before["price_observation"] > 0
    with database.connect() as conn:
        rows_before = {
            t: [tuple(r) for r in conn.execute(f"SELECT * FROM {t} ORDER BY rowid")] for t in TABLES
        }
        indexes_before = {
            r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='index'")
        }
    assert database.migrate() == 6
    assert counts(database) == before
    with database.connect() as conn:
        for table, rows in rows_before.items():
            assert [tuple(r) for r in conn.execute(f"SELECT * FROM {table} ORDER BY rowid")] == (
                rows
            )
        assert conn.execute("PRAGMA foreign_key_check").fetchall() == []
        assert conn.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
        indexes = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='index'")}
    assert indexes == indexes_before | {"ix_obs_snapshot"}  # nothing dropped
    backup = backup_path(database.path, 6)
    assert backup == tmp_path / "flight-deals.pre-v6.db" and backup.is_file()
    assert Database(backup).schema_version() == 5


def test_new_db_gets_no_backup(tmp_path: Path) -> None:
    database = Database(tmp_path / "fresh.db")
    assert database.migrate() >= 6
    assert sorted(p.name for p in tmp_path.glob("*.db")) == ["fresh.db"]


def test_index_columns_and_directions(tmp_path: Path) -> None:  # C-58
    database = Database(tmp_path / "ix.db")
    database.migrate()
    with database.connect() as conn:
        info = conn.execute("PRAGMA index_xinfo(ix_obs_snapshot)").fetchall()
    keys = [(r["name"], r["desc"]) for r in info if r["key"]]
    assert keys == INDEX_KEYS


# ---- EXPLAIN QUERY PLAN (C-58) -------------------------------------------------------------


def plan_of(database: Database, sql: str) -> str:
    with database.connect() as conn:
        rows = conn.execute("EXPLAIN QUERY PLAN " + sql, READ_PARAMS).fetchall()
    return "\n".join(r["detail"] for r in rows)


@pytest.fixture
def planned(tmp_path: Path) -> Database:
    database = Database(tmp_path / "plan.db")
    database.migrate()
    return database


def test_keep_select_plan_is_a_covering_index_range(planned: Database) -> None:  # C-58 (1)
    text = plan_of(planned, _snapshot_keep_select(_SNAPSHOT_SCOPE_WATCH))
    assert "ix_obs_snapshot" in text and "COVERING INDEX" in text, text
    assert not re.search(r"\bSCAN price_observation\b", text), text
    assert "USE TEMP B-TREE" not in text, text


def test_full_read_plan_never_scans_a_table(planned: Database) -> None:  # C-58 (2)
    text = plan_of(planned, SNAPSHOT_OBSERVATIONS_SQL)
    assert not re.search(r"\bSCAN (price_observation|watch|o)\b", text), text
    assert "ix_obs_snapshot" in text and "COVERING INDEX" in text, text
    assert re.search(r"\bSEARCH o USING INTEGER PRIMARY KEY\b", text), text
    assert text.count("USE TEMP B-TREE") <= 1, text
    assert text.count("USE TEMP B-TREE") == text.count("USE TEMP B-TREE FOR ORDER BY"), text

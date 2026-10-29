"""Migration 0004: exploration tables (ADR-0002 FD-6 Decision 1, C-43)."""

from __future__ import annotations

import re
import sqlite3
from pathlib import Path
from typing import Any

import pytest

from flight_deals.storage import db as db_module
from flight_deals.storage.db import Database, backup_path, needs_foreign_keys_off
from tests.test_migration_0003 import (
    ORIGINAL_MIGRATIONS,
    TABLES,
    TRIP_OPTION_ACCEPTS,
    TRIP_OPTION_REJECTS,
    TS,
    build_v2_db,
    counts,
    only_up_to,
)


def sql_0004() -> str:
    return dict(ORIGINAL_MIGRATIONS())[4]


def build_v3_db(path: Path, monkeypatch: pytest.MonkeyPatch) -> Database:
    """v3 database with the 0003 fixture data (two watches, runs, alerts, items)."""
    database = build_v2_db(path, monkeypatch)
    monkeypatch.setattr(db_module, "available_migrations", only_up_to(3))
    assert database.migrate() == 3
    # Later migrations (0005+) have their own tests; stop at 4 here.
    monkeypatch.setattr(db_module, "available_migrations", only_up_to(4))
    return database


def migrated(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Database:
    database = build_v3_db(tmp_path / "fd.db", monkeypatch)
    assert database.migrate() == 4
    return database


def insert_exploration(conn: sqlite3.Connection, **values: Any) -> int:
    row: dict[str, Any] = {
        "condition_key": "v1|TPE|NRT|one_way|2026-12|-|-|1|0|economy|-|-|-|TWD",
        "origin": "TPE",
        "destination": "NRT",
        "trip_type": "one_way",
        "month": "2026-12",
        "total": 31,
        "created_at": TS,
    }
    row.update(values)
    cols = ", ".join(row)
    marks = ", ".join("?" for _ in row)
    cur = conn.execute(f"INSERT INTO exploration ({cols}) VALUES ({marks})", list(row.values()))
    return int(cur.lastrowid or 0)


def insert_cell(conn: sqlite3.Connection, exploration_id: int, **values: Any) -> None:
    row: dict[str, Any] = {"exploration_id": exploration_id, "depart_date": "2026-12-10"}
    row.update(values)
    cols = ", ".join(row)
    marks = ", ".join("?" for _ in row)
    conn.execute(f"INSERT INTO exploration_cell ({cols}) VALUES ({marks})", list(row.values()))


# ---- the SQL text itself ------------------------------------------------------------


def test_0004_is_purely_additive() -> None:
    sql = sql_0004()
    assert not needs_foreign_keys_off(sql)
    assert "foreign_keys" not in sql.lower()
    code = "\n".join(line for line in sql.splitlines() if not line.lstrip().startswith("--"))
    statements = [s.strip() for s in code.split(";") if s.strip()]
    assert statements and all(
        re.match(r"CREATE (TABLE|INDEX) ", s, re.IGNORECASE) for s in statements
    ), statements
    upper = code.upper()
    for banned in ("DROP ", "RENAME", "ALTER ", "UPDATE ", "DELETE FROM", "INSERT "):
        assert banned not in upper, banned


def test_0004_check_clauses_copy_0003_verbatim() -> None:
    sql_3 = dict(ORIGINAL_MIGRATIONS())[3]
    sql_4 = sql_0004()
    # The passenger, cabin, airline and hour CHECK text is identical to 0003.
    for fragment in (
        "CHECK (cabin IN ('economy','premium_economy','business','first'))",
        "CHECK (typeof(adults) = 'integer' AND adults BETWEEN 1 AND 9)",
        "CHECK (typeof(children) = 'integer' AND children BETWEEN 0 AND 8)",
        "AND airlines NOT GLOB '*[0-9][0-9]*'",
        "CHECK (adults + children <= 9)",
        "AND dep_hour_from < dep_hour_to)",
    ):
        assert fragment in sql_3 and fragment in sql_4, fragment


# ---- upgrading a v3 database with data ------------------------------------------------


def test_v3_data_survives_and_backup_is_taken(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    database = build_v3_db(tmp_path / "flight-deals.db", monkeypatch)
    before = counts(database)
    with database.connect() as conn:
        rows_before = {
            t: [tuple(r) for r in conn.execute(f"SELECT * FROM {t} ORDER BY rowid")] for t in TABLES
        }
    assert database.migrate() == 4
    assert counts(database) == before
    with database.connect() as conn:
        for table, rows in rows_before.items():
            assert [tuple(r) for r in conn.execute(f"SELECT * FROM {table} ORDER BY rowid")] == (
                rows
            )
        assert conn.execute("PRAGMA foreign_key_check").fetchall() == []
        names = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        assert {"exploration", "exploration_cell"} <= names
        indexes = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='index'")}
        assert {
            "idx_exploration_condition",
            "idx_exploration_created",
            "idx_exploration_started",
        } <= indexes
    backup = backup_path(database.path, 4)
    assert backup == tmp_path / "flight-deals.pre-v4.db" and backup.is_file()
    assert Database(backup).schema_version() == 3


def test_new_db_gets_no_backup(tmp_path: Path) -> None:
    database = Database(tmp_path / "fresh.db")
    assert database.migrate() >= 4
    assert sorted(p.name for p in tmp_path.glob("*.db")) == ["fresh.db"]


# ---- CHECK constraints --------------------------------------------------------------


@pytest.mark.parametrize(
    "values",
    [
        {"month": "2026-13"},
        {"month": "2026-1"},
        {"month": "2026-00"},
        {"total": 0},
        {"total": 32},
        {"total": 5, "done": 6},
        {"status": "rejected"},
        {"trip_days": 5},  # one-way must not carry a stay length
        {"trip_type": "round_trip"},  # round trip without trip_days
        {"trip_type": "round_trip", "trip_days": 0},
        {"trip_type": "round_trip", "trip_days": 31},
        {"max_stops": 3},
        {"condition_key": "x"},
    ],
)
def test_exploration_check_rejects(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, values: dict[str, Any]
) -> None:
    database = migrated(tmp_path, monkeypatch)
    with database.connect() as conn, pytest.raises(sqlite3.IntegrityError):
        insert_exploration(conn, **values)


@pytest.mark.parametrize("values", TRIP_OPTION_REJECTS)
def test_trip_option_checks_reject_like_0003(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, values: dict[str, Any]
) -> None:
    database = migrated(tmp_path, monkeypatch)
    with database.connect() as conn, pytest.raises(sqlite3.IntegrityError):
        insert_exploration(conn, **values)


@pytest.mark.parametrize("values", TRIP_OPTION_ACCEPTS)
def test_trip_option_checks_accept_like_0003(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, values: dict[str, Any]
) -> None:
    database = migrated(tmp_path, monkeypatch)
    with database.connect() as conn:
        insert_exploration(conn, **values)


def test_round_trip_and_bounds_accepted(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    database = migrated(tmp_path, monkeypatch)
    with database.connect() as conn:
        insert_exploration(conn, trip_type="round_trip", trip_days=30, total=1, done=1)
        insert_exploration(conn, trip_type="round_trip", trip_days=1, month="2027-09")


@pytest.mark.parametrize(
    "values",
    [
        {"status": "ok"},  # ok without an amount
        {"status": "no_data", "amount_minor": 100},  # non-ok with an amount
        {"status": "ok", "amount_minor": 0},
        {"status": "ok", "amount_minor": -5},
        {"status": "pending", "depart_time": "7:55"},
        {"status": "ok", "amount_minor": 100, "depart_time": "24:00"},
        {"status": "rejected"},
        {"from_cache": 2},
        {"price_kind": "guess"},
    ],
)
def test_cell_check_rejects(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, values: dict[str, Any]
) -> None:
    database = migrated(tmp_path, monkeypatch)
    with database.connect() as conn:
        exploration_id = insert_exploration(conn)
    with database.connect() as conn, pytest.raises(sqlite3.IntegrityError):
        insert_cell(conn, exploration_id, **values)


def test_cell_accepts_and_cascades(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    database = migrated(tmp_path, monkeypatch)
    before = counts(database)
    with database.connect() as conn:
        exploration_id = insert_exploration(conn)
        insert_cell(conn, exploration_id)
        insert_cell(
            conn,
            exploration_id,
            depart_date="2026-12-11",
            status="ok",
            amount_minor=920000,
            depart_time="07:55",
        )
        insert_cell(conn, exploration_id, depart_date="2026-12-12", status="skipped")
    with database.connect() as conn, pytest.raises(sqlite3.IntegrityError):
        insert_cell(conn, 999)  # no such exploration
    with database.connect() as conn, pytest.raises(sqlite3.IntegrityError):
        insert_cell(conn, exploration_id)  # (exploration_id, depart_date) is the key
    with database.connect() as conn:
        conn.execute("DELETE FROM exploration WHERE id = ?", (exploration_id,))
        assert conn.execute("SELECT COUNT(*) FROM exploration_cell").fetchone()[0] == 0
    assert counts(database) == before  # watch data never touched

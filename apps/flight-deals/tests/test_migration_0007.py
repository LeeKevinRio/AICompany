"""Migration 0007: comparison tables (ADR-0002 FD-9 Decision 1, C-61)."""

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
    counts,
    only_up_to,
)
from tests.test_migration_0006 import build_v5_db

PAX_KEYS = {"adults", "children", "cabin"}
# The 0003 passenger / cabin cases, one by one (comparisons have no airline or hour).
PAX_REJECTS = [v for v in TRIP_OPTION_REJECTS if set(v) <= PAX_KEYS]
PAX_ACCEPTS = [v for v in TRIP_OPTION_ACCEPTS if set(v) <= PAX_KEYS]


def sql_0007() -> str:
    return dict(ORIGINAL_MIGRATIONS())[7]


def build_v6_db(path: Path, monkeypatch: pytest.MonkeyPatch) -> Database:
    database = build_v5_db(path, monkeypatch)
    assert database.migrate() == 6
    monkeypatch.setattr(db_module, "available_migrations", only_up_to(7))
    return database


def migrated(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Database:
    database = build_v6_db(tmp_path / "fd.db", monkeypatch)
    assert database.migrate() == 7
    return database


def insert_comparison(conn: sqlite3.Connection, **values: Any) -> int:
    row: dict[str, Any] = {
        "condition_key": "cmp1|TPE|NRT,OSA|one_way|2026-12-10|-|-|1|0|economy|TWD",
        "origin": "TPE",
        "destinations": "NRT,OSA",
        "trip_type": "one_way",
        "depart_date": "2026-12-10",
        "total": 2,
        "created_at": TS,
    }
    row.update(values)
    cols = ", ".join(row)
    marks = ", ".join("?" for _ in row)
    cur = conn.execute(f"INSERT INTO comparison ({cols}) VALUES ({marks})", list(row.values()))
    return int(cur.lastrowid or 0)


def insert_cell(conn: sqlite3.Connection, comparison_id: int, **values: Any) -> None:
    row: dict[str, Any] = {"comparison_id": comparison_id, "position": 0, "destination": "NRT"}
    row.update(values)
    cols = ", ".join(row)
    marks = ", ".join("?" for _ in row)
    conn.execute(f"INSERT INTO comparison_cell ({cols}) VALUES ({marks})", list(row.values()))


# ---- the SQL text itself ------------------------------------------------------------


def test_0007_file_name_and_purely_additive() -> None:  # C-61
    folder = Path(db_module.__file__).parent / "migrations"
    names = sorted(p.name for p in folder.glob("0007_*.sql"))
    assert names == ["0007_comparison.sql"]
    sql = sql_0007()
    assert not needs_foreign_keys_off(sql)
    assert "foreign_keys" not in sql.lower()
    assert "exploration" not in sql.lower()
    code = "\n".join(line for line in sql.splitlines() if not line.lstrip().startswith("--"))
    statements = [s.strip() for s in code.split(";") if s.strip()]
    assert statements and all(
        re.match(r"CREATE (TABLE|INDEX) ", s, re.IGNORECASE) for s in statements
    ), statements
    tables = [s.split()[2] for s in statements if s.upper().startswith("CREATE TABLE")]
    assert tables == ["comparison", "comparison_cell"]
    upper = code.upper()
    for banned in ("DROP ", "RENAME", "ALTER ", "UPDATE ", "DELETE FROM", "INSERT "):
        assert banned not in upper, banned


def test_0007_passenger_and_cabin_checks_copy_0003_verbatim() -> None:
    sql_3 = dict(ORIGINAL_MIGRATIONS())[3]
    sql_7 = sql_0007()
    for fragment in (
        "CHECK (cabin IN ('economy','premium_economy','business','first'))",
        "CHECK (typeof(adults) = 'integer' AND adults BETWEEN 1 AND 9)",
        "CHECK (typeof(children) = 'integer' AND children BETWEEN 0 AND 8)",
        "CHECK (adults + children <= 9)",
    ):
        assert fragment in sql_3 and fragment in sql_7, fragment
    assert "airlines" not in sql_7 and "dep_hour" not in sql_7


# ---- upgrading a v6 database with data ------------------------------------------------


def test_v6_data_survives_and_backup_is_taken(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:  # C-61
    database = build_v6_db(tmp_path / "flight-deals.db", monkeypatch)
    before = counts(database)
    assert before["price_observation"] > 0
    with database.connect() as conn:
        rows_before = {
            t: [tuple(r) for r in conn.execute(f"SELECT * FROM {t} ORDER BY rowid")] for t in TABLES
        }
        indexes_before = {
            r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='index'")
        }
    assert database.migrate() == 7
    assert counts(database) == before
    with database.connect() as conn:
        for table, rows in rows_before.items():
            assert [tuple(r) for r in conn.execute(f"SELECT * FROM {table} ORDER BY rowid")] == (
                rows
            )
        assert conn.execute("PRAGMA foreign_key_check").fetchall() == []
        assert conn.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
        names = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        assert {"comparison", "comparison_cell"} <= names
        indexes = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='index'")}
    assert indexes_before <= indexes  # nothing dropped
    assert {
        "idx_comparison_condition",
        "idx_comparison_created",
        "idx_comparison_started",
    } <= indexes
    backup = backup_path(database.path, 7)
    assert backup == tmp_path / "flight-deals.pre-v7.db" and backup.is_file()
    assert Database(backup).schema_version() == 6


def test_new_db_gets_no_backup(tmp_path: Path) -> None:
    database = Database(tmp_path / "fresh.db")
    assert database.migrate() >= 7
    assert sorted(p.name for p in tmp_path.glob("*.db")) == ["fresh.db"]


# ---- CHECK constraints --------------------------------------------------------------


@pytest.mark.parametrize(
    "values",
    [
        {"condition_key": "v1|TPE|NRT"},
        {"condition_key": "x"},
        {"total": 1, "destinations": "NRT"},
        {"total": 9, "destinations": "AAA,BBB,CCC,DDD,EEE,FFF,GGG,HHH,III"},
        {"done": 3},
        {"status": "rejected"},
        {"return_date": "2026-12-15"},  # one-way carries a return date
        {"trip_type": "round_trip"},  # round trip without a return date
        {"trip_type": "round_trip", "return_date": "2026-12-09"},
        {"depart_date": "2026-1-5"},
        {"destinations": "NRT,OSA,SEL"},  # length does not match total
        {"destinations": "NRT,OS"},
        {"max_stops": 3},
        {"origin": "TP"},
    ],
)
def test_comparison_check_rejects(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, values: dict[str, Any]
) -> None:  # C-61
    database = migrated(tmp_path, monkeypatch)
    with database.connect() as conn, pytest.raises(sqlite3.IntegrityError):
        insert_comparison(conn, **values)


@pytest.mark.parametrize("values", PAX_REJECTS)
def test_passenger_checks_reject_like_0003(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, values: dict[str, Any]
) -> None:
    assert len(PAX_REJECTS) == 7
    database = migrated(tmp_path, monkeypatch)
    with database.connect() as conn, pytest.raises(sqlite3.IntegrityError):
        insert_comparison(conn, **values)


@pytest.mark.parametrize("values", PAX_ACCEPTS)
def test_passenger_checks_accept_like_0003(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, values: dict[str, Any]
) -> None:
    assert len(PAX_ACCEPTS) == 3
    database = migrated(tmp_path, monkeypatch)
    with database.connect() as conn:
        insert_comparison(conn, **values)


def test_bounds_accepted(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    database = migrated(tmp_path, monkeypatch)
    with database.connect() as conn:
        insert_comparison(conn, trip_type="round_trip", return_date="2026-12-10")  # same day
        insert_comparison(
            conn,
            total=8,
            done=8,
            destinations="AAA,BBB,CCC,DDD,EEE,FFF,GGG,HHH",
            status="done",
        )


@pytest.mark.parametrize(
    "values",
    [
        {"position": 8},
        {"position": -1},
        {"position": 1.5},
        {"destination": "TO"},
        {"status": "ok"},  # ok without an amount
        {"status": "no_data", "amount_minor": 100},  # non-ok with an amount
        {"status": "ok", "amount_minor": 0},
        {"status": "pending", "depart_time": "7:55"},
        {"status": "rejected"},
        {"from_cache": 2},
        {"price_kind": "guess"},
    ],
)
def test_cell_check_rejects(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, values: dict[str, Any]
) -> None:  # C-61
    database = migrated(tmp_path, monkeypatch)
    with database.connect() as conn:
        comparison_id = insert_comparison(conn)
    with database.connect() as conn, pytest.raises(sqlite3.IntegrityError):
        insert_cell(conn, comparison_id, **values)


def test_cell_keys_accepts_and_cascades(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    database = migrated(tmp_path, monkeypatch)
    before = counts(database)
    with database.connect() as conn:
        comparison_id = insert_comparison(conn)
        insert_cell(conn, comparison_id)
        insert_cell(
            conn,
            comparison_id,
            position=1,
            destination="OSA",
            status="ok",
            amount_minor=920000,
            depart_time="07:55",
        )
    with database.connect() as conn, pytest.raises(sqlite3.IntegrityError):
        insert_cell(conn, 999)  # no such comparison
    with database.connect() as conn, pytest.raises(sqlite3.IntegrityError):
        insert_cell(conn, comparison_id, destination="SEL")  # (id, position) is the key
    with database.connect() as conn, pytest.raises(sqlite3.IntegrityError):
        insert_cell(conn, comparison_id, position=2)  # same destination twice
    with database.connect() as conn:
        conn.execute("DELETE FROM comparison WHERE id = ?", (comparison_id,))
        assert conn.execute("SELECT COUNT(*) FROM comparison_cell").fetchone()[0] == 0
    assert counts(database) == before  # watch data never touched

"""Migration 0008: departure weekdays and exploration month ranges (ADR-0002 FD-10
Decision 1, C-71)."""

from __future__ import annotations

import re
import sqlite3
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any

import pytest

from flight_deals.domain.dates import range_pairs
from flight_deals.domain.models import ExplorationSpec
from flight_deals.domain.weekdays import ALL_WEEKDAYS
from flight_deals.storage import db as db_module
from flight_deals.storage.db import Database, backup_path, needs_foreign_keys_off
from flight_deals.storage.repository import Repository
from tests.test_migration_0003 import ORIGINAL_MIGRATIONS, TS, only_up_to
from tests.test_migration_0004 import insert_cell, insert_exploration
from tests.test_migration_0007 import build_v6_db, insert_comparison
from tests.test_migration_0007 import insert_cell as insert_comparison_cell

V1_KEY = "v1|TPE|NRT|one_way|2026-12|-|-|1|0|economy|-|-|-|TWD"
V2_KEY = "v2|TPE|NRT|one_way|2026-12|2026-12|127|-|-|1|0|economy|-|-|-|TWD"
NOW = datetime(2026, 10, 25, 4, tzinfo=UTC)
EXPLORATION_INDEXES = {
    "idx_exploration_condition": ["condition_key", "created_at"],
    "idx_exploration_created": ["created_at"],
    "idx_exploration_started": ["started_at"],
}


def sql_0008() -> str:
    return dict(ORIGINAL_MIGRATIONS())[8]


def statements(sql: str) -> list[str]:
    code = "\n".join(line for line in sql.splitlines() if not line.lstrip().startswith("--"))
    return [" ".join(s.split()) for s in code.split(";") if s.strip()]


def build_v7_db(path: Path, monkeypatch: pytest.MonkeyPatch) -> Database:
    """v7 database with data in every table that matters (C-71 fixture).

    Watches 1 (fixed, revision 1) and 2 (flexible, revision 3) with runs, observations,
    alert state and notifications come from the 0003 fixture; added here: a done
    exploration with cells, a failed one with a skipped cell, a comparison with a cell.
    """
    database = build_v6_db(path, monkeypatch)
    assert database.migrate() == 7
    with database.connect() as conn:
        done = insert_exploration(
            conn,
            status="done",
            total=2,
            done=2,
            queries_used=2,
            started_at=TS,
            finished_at=TS,
        )
        insert_cell(conn, done, status="ok", amount_minor=920000, currency="TWD")
        insert_cell(conn, done, depart_date="2026-12-11", status="no_data")
        failed = insert_exploration(
            conn,
            condition_key="v1|TPE|KIX|round_trip|2027-01|5|0|2|1|business|BR,CI|6|12|TWD",
            destination="KIX",
            trip_type="round_trip",
            month="2027-01",
            trip_days=5,
            max_stops=0,
            adults=2,
            children=1,
            cabin="business",
            airlines="BR,CI",
            dep_hour_from=6,
            dep_hour_to=12,
            status="failed",
            total=3,
            done=1,
            error_summary="服務重啟，探索中斷",
        )
        insert_cell(conn, failed, depart_date="2027-01-01", status="error", error="boom")
        insert_cell(conn, failed, depart_date="2027-01-02", status="skipped", reason="breaker")
        insert_cell(conn, failed, depart_date="2027-01-03", status="skipped")
        comparison = insert_comparison(conn)
        insert_comparison_cell(conn, comparison, status="ok", amount_minor=500000)
    monkeypatch.setattr(db_module, "available_migrations", only_up_to(8))
    return database


def all_tables(conn: sqlite3.Connection) -> list[str]:
    return [
        r[0]
        for r in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'"
            " ORDER BY name"
        )
    ]


def snapshot(database: Database) -> dict[str, list[dict[str, Any]]]:
    with database.connect() as conn:
        return {
            t: [dict(r) for r in conn.execute(f"SELECT * FROM {t} ORDER BY rowid")]
            for t in all_tables(conn)
        }


def migrated(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Database:
    database = build_v7_db(tmp_path / "fd.db", monkeypatch)
    assert database.migrate() == 8
    return database


def table_sql(conn: sqlite3.Connection, name: str) -> str:
    row = conn.execute("SELECT sql FROM sqlite_master WHERE name = ?", (name,)).fetchone()
    return str(row[0])


# ---- the SQL text itself ------------------------------------------------------------


def test_0008_file_name_marker_and_statements() -> None:  # C-71
    folder = Path(db_module.__file__).parent / "migrations"
    names = sorted(p.name for p in folder.glob("0008_*.sql"))
    assert names == ["0008_depart_weekdays_and_exploration_range.sql"]
    sql = sql_0008()
    assert sql.splitlines()[0] == "-- flight-deals: foreign_keys=off"
    assert needs_foreign_keys_off(sql)
    assert "RENAME TO exploration_old" not in sql and "legacy_alter_table" not in sql
    found = statements(sql)
    kinds = [re.match(r"(\w+ \w+ \w+)", s).group(1) for s in found]  # type: ignore[union-attr]
    assert kinds == [
        "ALTER TABLE watch",
        "CREATE TABLE exploration_new",
        "INSERT INTO exploration_new",
        "DROP TABLE exploration",
        "ALTER TABLE exploration_new",
        "CREATE INDEX idx_exploration_condition",
        "CREATE INDEX idx_exploration_created",
        "CREATE INDEX idx_exploration_started",
    ]
    # watch: exactly one ADD COLUMN, nothing else.
    watch = [s for s in found if re.search(r"\bwatch\b", s)]
    assert len(watch) == 1 and "ADD COLUMN depart_weekdays" in watch[0]
    assert found[4] == "ALTER TABLE exploration_new RENAME TO exploration"
    for stmt in found:
        for other in ("exploration_cell", "comparison", "scan_run", "price_observation"):
            assert other not in stmt, (other, stmt)
    # Copy lists every column explicitly (ids kept) and selects the same list.
    insert = found[2]
    head, select = insert.split(" SELECT ", 1)
    columns = head[head.index("(") + 1 : head.index(")")]
    assert select.startswith(columns + " FROM exploration")
    assert columns.startswith("id, condition_key,") and "*" not in insert


def test_0008_other_exploration_checks_copy_0004_verbatim() -> None:
    sql_4 = dict(ORIGINAL_MIGRATIONS())[4]
    sql_8 = sql_0008()
    body_4 = sql_4[sql_4.index("CREATE TABLE exploration (") : sql_4.index("CREATE INDEX")]
    lines_8 = set(sql_8.splitlines())
    changed = {"  condition_key TEXT NOT NULL CHECK (condition_key GLOB 'v1|*'),"}
    for line in body_4.splitlines():
        if line.startswith("CREATE TABLE") or line.lstrip().startswith("--") or line in changed:
            continue
        assert line in lines_8, line


# ---- upgrading a v7 database with data ------------------------------------------------


def test_v7_data_survives_and_backup_is_taken(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:  # C-71
    database = build_v7_db(tmp_path / "flight-deals.db", monkeypatch)
    before = snapshot(database)
    assert all(
        len(before[t]) >= 1
        for t in (
            "watch",
            "scan_run",
            "price_observation",
            "alert_state",
            "notification",
            "exploration",
            "exploration_cell",
            "comparison",
            "comparison_cell",
        )
    )
    assert any(w["revision"] > 1 and w["date_mode"] == "flexible" for w in before["watch"])
    with database.connect() as conn:
        cell_sql_before = table_sql(conn, "exploration_cell")
    assert database.migrate() == 8
    after = snapshot(database)
    assert set(after) == set(before)
    for table, rows in before.items():
        if table == "schema_version":
            continue
        assert len(after[table]) == len(rows), table
        if table in ("watch", "exploration"):
            continue
        assert after[table] == rows, table
    for old, new in zip(before["watch"], after["watch"], strict=True):
        assert {k: new[k] for k in old} == old  # every old column equal, revision included
        assert new["depart_weekdays"] == 127
    for old, new in zip(before["exploration"], after["exploration"], strict=True):
        assert {k: new[k] for k in old} == old
        assert new["condition_key"].encode() == old["condition_key"].encode()
        assert new["month_to"] is None and new["depart_weekdays"] == 127
    with database.connect() as conn:
        assert conn.execute("PRAGMA foreign_key_check").fetchall() == []
        assert conn.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
        assert table_sql(conn, "exploration_cell") == cell_sql_before
        assert "REFERENCES exploration(id)" in table_sql(conn, "exploration_cell")
        everything = " ".join(
            str(r[0]) for r in conn.execute("SELECT sql FROM sqlite_master WHERE sql IS NOT NULL")
        )
        assert "exploration_new" not in everything
        names = {r[0] for r in conn.execute("SELECT name FROM sqlite_master")}
        assert "exploration_new" not in names
        for index, columns in EXPLORATION_INDEXES.items():
            info = [r[2] for r in conn.execute(f"PRAGMA index_info({index})")]
            assert info == columns, index
    backup = backup_path(database.path, 8)
    assert backup == tmp_path / "flight-deals.pre-v8.db" and backup.is_file()
    assert Database(backup).schema_version() == 7


def test_foreign_key_and_cascade_after_rebuild(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:  # C-71
    database = migrated(tmp_path, monkeypatch)
    with database.connect() as conn, pytest.raises(sqlite3.IntegrityError):
        insert_cell(conn, 999)
    with database.connect() as conn:
        cells = conn.execute("SELECT COUNT(*) FROM exploration_cell").fetchone()[0]
        conn.execute("DELETE FROM exploration WHERE id = 1")
        left = conn.execute("SELECT COUNT(*) FROM exploration_cell").fetchone()[0]
    assert cells == 5 and left == 3  # exploration 1 had two cells


def test_migrated_records_read_as_all_weekdays(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:  # C-72, AC-D8
    database = build_v7_db(tmp_path / "fd.db", monkeypatch)
    assert database.migrate() == 8
    repo = Repository(database)
    for watch in repo.list_watches():
        assert watch.spec.depart_weekdays == ALL_WEEKDAYS
    flexible = repo.get_watch(2)
    assert flexible is not None and flexible.revision == 3 and flexible.sample_offset == 7
    # search_shape after migration = the FD-9 shape plus the all-weekdays tuple.
    assert flexible.spec.search_shape()[-1] == ALL_WEEKDAYS
    record = repo.get_exploration(1)
    assert record is not None and record.condition_key == V1_KEY
    assert record.spec.end_year is None and record.spec.depart_weekdays == ALL_WEEKDAYS
    assert record.spec.condition_key() == V2_KEY  # a v1 row never matches a new v2 key


def test_new_db_gets_no_backup(tmp_path: Path) -> None:  # C-71
    database = Database(tmp_path / "fresh.db")
    assert database.migrate() == 8
    assert sorted(p.name for p in tmp_path.glob("*.db")) == ["fresh.db"]


# ---- CHECK constraints --------------------------------------------------------------


@pytest.mark.parametrize("value", [0, 128, 1.5, "1.5", "all", -1])
def test_watch_weekday_check_rejects(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, value: object
) -> None:  # C-71
    database = migrated(tmp_path, monkeypatch)
    with database.connect() as conn, pytest.raises(sqlite3.IntegrityError):
        conn.execute("UPDATE watch SET depart_weekdays = ? WHERE id = 1", (value,))


def test_integer_text_is_coerced_not_stored_as_text(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:  # C-71 deviation: INTEGER affinity turns '127' into 127 before the CHECK
    database = migrated(tmp_path, monkeypatch)
    with database.connect() as conn:
        conn.execute("UPDATE watch SET depart_weekdays = '127' WHERE id = 1")
        row = conn.execute(
            "SELECT depart_weekdays, typeof(depart_weekdays) FROM watch WHERE id = 1"
        ).fetchone()
    assert tuple(row) == (127, "integer")


@pytest.mark.parametrize(
    "values",
    [
        {"month_to": "2027-01"},  # v1 key with a range
        {"depart_weekdays": 48},  # v1 key with a weekday filter
        {"condition_key": "v3|TPE"},
        {"condition_key": V2_KEY, "month_to": "2026-12"},  # equal to month
        {"condition_key": V2_KEY, "month_to": "2026-11"},  # before month
        {"condition_key": V2_KEY, "month_to": "2027-2"},
        {"condition_key": V2_KEY, "month_to": "2027-13"},
        {"condition_key": V2_KEY, "depart_weekdays": 0},
        {"condition_key": V2_KEY, "depart_weekdays": 128},
    ],
)
def test_exploration_check_rejects(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, values: dict[str, Any]
) -> None:  # C-71
    database = migrated(tmp_path, monkeypatch)
    with database.connect() as conn, pytest.raises(sqlite3.IntegrityError):
        insert_exploration(conn, **values)


def test_exploration_check_accepts(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    database = migrated(tmp_path, monkeypatch)
    with database.connect() as conn:
        insert_exploration(conn, condition_key=V2_KEY, depart_weekdays=48)
        insert_exploration(conn, condition_key=V2_KEY, month_to="2027-02")
        insert_exploration(conn)  # a v1 row as FD-6 wrote it is still valid


@pytest.mark.parametrize(
    "values",
    [
        {"month": "2026-13"},
        {"total": 32},
        {"total": 5, "done": 6},
        {"status": "rejected"},
        {"trip_days": 5},
        {"max_stops": 3},
        {"adults": 0},
    ],
)
def test_fd6_checks_still_hold_for_v2(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, values: dict[str, Any]
) -> None:  # C-71: other CHECKs copied verbatim
    database = migrated(tmp_path, monkeypatch)
    with database.connect() as conn, pytest.raises(sqlite3.IntegrityError):
        insert_exploration(conn, condition_key=V2_KEY, **values)


def test_repository_round_trip_of_a_range(tmp_path: Path) -> None:  # C-71, contract 3.2
    database = Database(tmp_path / "fd.db")
    database.migrate()
    repo = Repository(database)
    spec = ExplorationSpec(
        "TPE",
        "KIX",
        "round_trip",
        2026,
        12,
        4,
        None,
        end_year=2027,
        end_month=2,
        depart_weekdays=(4, 5),
    )
    pairs = range_pairs(spec, date(2026, 10, 25))
    assert len(pairs) == 26  # Fridays and Saturdays of 2026-12 .. 2027-02
    exploration_id = repo.insert_exploration(spec, pairs, NOW)
    with database.connect() as conn:
        row = conn.execute(
            "SELECT month, month_to, depart_weekdays, condition_key FROM exploration"
        ).fetchone()
    assert tuple(row) == ("2026-12", "2027-02", 48, spec.condition_key())
    record = repo.get_exploration(exploration_id)
    assert record is not None and record.spec == spec
    single = ExplorationSpec("TPE", "KIX", "one_way", 2026, 12, None, None)
    second = repo.insert_exploration(single, range_pairs(single, date(2026, 10, 25)), NOW)
    with database.connect() as conn:
        month_to = conn.execute(
            "SELECT month_to FROM exploration WHERE id = ?", (second,)
        ).fetchone()[0]
    assert month_to is None

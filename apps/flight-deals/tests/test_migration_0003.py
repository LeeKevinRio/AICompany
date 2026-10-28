"""Migration 0003: rebuild ``watch`` for trip options (ADR-0002 FD-5 Decision 1, C-37)."""

from __future__ import annotations

import fnmatch
import re
import sqlite3
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest

from flight_deals.storage import db as db_module
from flight_deals.storage.db import (
    Database,
    available_migrations,
    backup_path,
    needs_foreign_keys_off,
)

ORIGINAL_MIGRATIONS: Callable[[], list[tuple[int, str]]] = available_migrations
LATEST = max(v for v, _ in available_migrations())
TS = "2026-10-25T04:00:00+00:00"
TABLES = (
    "watch",
    "scan_run",
    "price_observation",
    "alert_state",
    "notification",
    "notification_item",
)
CHILD_TABLES = ("scan_run", "price_observation", "alert_state", "notification")
OLD_WATCH_COLUMNS = (
    "id",
    "name",
    "origin",
    "destination",
    "trip_type",
    "date_mode",
    "depart_date",
    "return_date",
    "window_start",
    "window_end",
    "min_trip_days",
    "max_trip_days",
    "max_stops",
    "cabin",
    "adults",
    "currency",
    "budget_amount_minor",
    "notify_on_new_low",
    "status",
    "revision",
    "sample_offset",
    "consecutive_failed_scans",
    "last_scanned_at",
    "created_at",
    "updated_at",
)


def sql_0003() -> str:
    return dict(ORIGINAL_MIGRATIONS())[3]


def only_up_to(version: int) -> Callable[[], list[tuple[int, str]]]:
    return lambda: [m for m in ORIGINAL_MIGRATIONS() if m[0] <= version]


def build_v2_db(path: Path, monkeypatch: pytest.MonkeyPatch) -> Database:
    """v2 database: watch 1 (revision 1) and watch 2 (revision 3) with history."""
    monkeypatch.setattr(db_module, "available_migrations", only_up_to(2))
    database = Database(path)
    assert database.migrate() == 2
    with database.connect() as conn:
        conn.execute(
            "INSERT INTO watch (id, name, destination, trip_type, date_mode, depart_date,"
            " return_date, max_stops, budget_amount_minor, created_at, updated_at)"
            " VALUES (1, 'tokyo', 'NRT', 'round_trip', 'fixed', '2026-12-10', '2026-12-15',"
            " 1, 1200000, ?, ?)",
            (TS, TS),
        )
        conn.execute(
            "INSERT INTO watch (id, name, origin, destination, trip_type, date_mode,"
            " window_start, window_end, status, revision, sample_offset,"
            " consecutive_failed_scans, last_scanned_at, notify_on_new_low, created_at,"
            " updated_at) VALUES (2, 'bkk', 'TSA', 'BKK', 'one_way', 'flexible',"
            " '2026-12-01', '2026-12-20', 'stale', 3, 7, 2, ?, 0, ?, ?)",
            (TS, TS, TS),
        )
        for run_id, watch_id, rev in ((10, 1, 1), (20, 2, 3)):
            conn.execute(
                "INSERT INTO scan_run (id, watch_id, watch_revision, started_at, status,"
                " sampled_pairs) VALUES (?, ?, ?, ?, 'ok', '[]')",
                (run_id, watch_id, rev, TS),
            )
            conn.execute(
                "INSERT INTO price_observation (id, scan_run_id, watch_id, watch_revision,"
                " source, price_kind, depart_date, amount_minor, currency, as_of, as_of_basis,"
                " fetched_at) VALUES (?, ?, ?, ?, 'google_flights', 'live', '2026-12-10',"
                " 950000, 'TWD', ?, 'fetch_time', ?)",
                (run_id * 10, run_id, watch_id, rev, TS, TS),
            )
            conn.execute(
                "INSERT INTO alert_state (watch_id, price_kind, last_notified_amount_minor,"
                " armed) VALUES (?, 'live', 950000, 0)",
                (watch_id,),
            )
        # Price alert of watch 2 (observation revision 3) with two old-format item keys.
        conn.execute(
            "INSERT INTO notification (id, watch_id, kind, rule, price_kind, observation_id,"
            " dedupe_key, status, attempts, message_text, created_at) VALUES (5, 2,"
            " 'price_alert', 'below_budget', 'live', 200, 'price:2:live:2026-12-10:-:950000',"
            " 'sent', 1, 'alert', ?)",
            (TS,),
        )
        # Alert whose observation is gone (observation_id NULL): keys cannot be resolved.
        conn.execute(
            "INSERT INTO notification (id, watch_id, kind, rule, price_kind, observation_id,"
            " dedupe_key, status, attempts, message_text, created_at) VALUES (6, 1,"
            " 'price_alert', 'new_low', 'live', NULL, 'price:1:live:old', 'sent', 1, 'old', ?)",
            (TS,),
        )
        items = (
            (5, "price:2:live:2026-12-10:-:950000"),
            (5, "price:2:live:2026-12-11:-:960000"),
            (6, "price:1:live:2026-12-10:2026-12-15:900000"),
        )
        for notification_id, key in items:
            conn.execute(
                "INSERT INTO notification_item (notification_id, item_key, depart_date,"
                " amount_minor, currency, reasons, fetched_at)"
                " VALUES (?, ?, '2026-12-10', 950000, 'TWD', 'below_budget', ?)",
                (notification_id, key, TS),
            )
    monkeypatch.setattr(db_module, "available_migrations", ORIGINAL_MIGRATIONS)
    return database


def counts(database: Database) -> dict[str, int]:
    with database.connect() as conn:
        return {t: int(conn.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0]) for t in TABLES}


def watch_rows(database: Database) -> list[dict[str, Any]]:
    with database.connect() as conn:
        rows = conn.execute("SELECT * FROM watch ORDER BY id").fetchall()
    return [dict(r) for r in rows]


def insert_watch(conn: sqlite3.Connection, **values: Any) -> None:
    row: dict[str, Any] = {
        "name": "x",
        "destination": "NRT",
        "trip_type": "one_way",
        "date_mode": "fixed",
        "depart_date": "2026-12-10",
        "created_at": TS,
        "updated_at": TS,
    }
    row.update(values)
    cols = ", ".join(row)
    marks = ", ".join("?" for _ in row)
    conn.execute(f"INSERT INTO watch ({cols}) VALUES ({marks})", list(row.values()))


# ---- the SQL text itself ------------------------------------------------------------


def test_sqlite_is_new_enough_for_rename_semantics() -> None:
    # The safe order relies on 3.26+ RENAME rewriting child FKs (ADR-0002 FD-5 Context).
    assert sqlite3.sqlite_version_info >= (3, 26, 0)


def test_0003_marker_and_safe_statement_order() -> None:
    sql = sql_0003()
    assert needs_foreign_keys_off(sql)
    assert sql.splitlines()[0] == "-- flight-deals: foreign_keys=off"
    code = "\n".join(line for line in sql.splitlines() if not line.lstrip().startswith("--"))
    steps = [
        code.index("CREATE TABLE watch_new"),
        code.index("INSERT INTO watch_new"),
        code.index("DROP TABLE watch;"),
        code.index("ALTER TABLE watch_new RENAME TO watch;"),
    ]
    assert steps == sorted(steps)
    assert "RENAME TO watch_old" not in sql
    assert re.search(r"ALTER\s+TABLE\s+watch\s+RENAME", sql, re.IGNORECASE) is None
    assert "legacy_alter_table" not in sql.lower()
    # Columns are listed explicitly (id copied as is), never SELECT *.
    assert "SELECT *" not in code.upper()
    insert = code[code.index("INSERT INTO watch_new") : code.index("FROM watch;")]
    for column in OLD_WATCH_COLUMNS:
        assert re.search(rf"\b{column}\b", insert), column


# ---- upgrading a v2 database with data ------------------------------------------------


def test_v2_data_survives_column_by_column(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    database = build_v2_db(tmp_path / "fd.db", monkeypatch)
    before_counts = counts(database)
    before = watch_rows(database)
    with database.connect() as conn:
        other_before = {
            t: [tuple(r) for r in conn.execute(f"SELECT * FROM {t} ORDER BY rowid")]
            for t in ("scan_run", "alert_state", "notification")
        }
    assert before_counts == {
        "watch": 2,
        "scan_run": 2,
        "price_observation": 2,
        "alert_state": 2,
        "notification": 2,
        "notification_item": 3,
    }
    assert database.migrate() == LATEST
    assert counts(database) == before_counts
    after = watch_rows(database)
    for old, new in zip(before, after, strict=True):
        for column in OLD_WATCH_COLUMNS:
            assert new[column] == old[column], column
        assert (new["children"], new["airlines"]) == (0, None)
        assert (new["dep_hour_from"], new["dep_hour_to"]) == (None, None)
        assert (new["cabin"], new["adults"]) == ("economy", 1)
    assert after[1]["revision"] == 3  # revision untouched (FR-C3)
    with database.connect() as conn:
        for table, rows in other_before.items():
            assert [tuple(r) for r in conn.execute(f"SELECT * FROM {table} ORDER BY rowid")] == (
                rows
            )
        obs = conn.execute("SELECT depart_time FROM price_observation").fetchall()
        assert [r[0] for r in obs] == [None, None]


def test_foreign_keys_still_point_at_watch(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    database = build_v2_db(tmp_path / "fd.db", monkeypatch)
    database.migrate()
    with database.connect() as conn:
        assert conn.execute("PRAGMA foreign_keys").fetchone()[0] == 1
        assert conn.execute("PRAGMA foreign_key_check").fetchall() == []
        for table in CHILD_TABLES:
            ddl = conn.execute("SELECT sql FROM sqlite_master WHERE name = ?", (table,)).fetchone()[
                0
            ]
            assert "REFERENCES watch(id)" in ddl, table
        everything = [
            f"{r[0]} {r[1] or ''}" for r in conn.execute("SELECT name, sql FROM sqlite_master")
        ]
        assert not any("watch_new" in text or "watch_old" in text for text in everything)
        kinds = {r[0] for r in conn.execute("SELECT type FROM sqlite_master")}
        assert kinds <= {"table", "index"}  # no view / trigger to carry over
    with database.connect() as conn, pytest.raises(sqlite3.IntegrityError):
        conn.execute(
            "INSERT INTO scan_run (watch_id, watch_revision, started_at, status, sampled_pairs)"
            " VALUES (999, 1, ?, 'ok', '[]')",
            (TS,),
        )


def test_deleting_a_watch_cascades_to_all_children(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    database = build_v2_db(tmp_path / "fd.db", monkeypatch)
    database.migrate()
    with database.connect() as conn:
        conn.execute("DELETE FROM watch WHERE id = 2")
    assert counts(database) == {
        "watch": 1,
        "scan_run": 1,
        "price_observation": 1,
        "alert_state": 1,
        "notification": 1,
        "notification_item": 1,
    }


def test_old_item_keys_gain_revision(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    database = build_v2_db(tmp_path / "fd.db", monkeypatch)
    database.migrate()
    with database.connect() as conn:
        keys = [
            (r[0], r[1])
            for r in conn.execute(
                "SELECT notification_id, item_key FROM notification_item ORDER BY id"
            )
        ]
        dedupe = conn.execute("SELECT dedupe_key FROM notification WHERE id = 5").fetchone()[0]
    assert keys == [
        (5, "price:2:r3:live:2026-12-10:-:950000"),
        (5, "price:2:r3:live:2026-12-11:-:960000"),
        # observation_id NULL: revision unknown, row left as it was.
        (6, "price:1:live:2026-12-10:2026-12-15:900000"),
    ]
    assert dedupe == "price:2:live:2026-12-10:-:950000"  # message keys are not rewritten


# Trip-option CHECK cases; migration 0004 reuses them verbatim (C-43).
TRIP_OPTION_REJECTS: list[dict[str, Any]] = [
    {"adults": 0},
    {"adults": 10},
    {"children": 9},
    {"adults": 5, "children": 5},
    {"cabin": "luxury"},
    {"airlines": "br"},
    {"airlines": "BR,"},
    {"airlines": ""},
    {"airlines": "BR,CI,JX,IT,JL,NH"},
    {"airlines": "12"},
    {"dep_hour_from": 6, "dep_hour_to": 24},
    {"dep_hour_from": 6},
    {"dep_hour_to": 12},
    {"dep_hour_from": 6, "dep_hour_to": 6},
    {"dep_hour_from": 12, "dep_hour_to": 6},
    {"dep_hour_from": -1, "dep_hour_to": 6},
    # INTEGER affinity keeps 1.5 as a real; typeof() checks reject it (qa B1).
    {"adults": 1.5},
    {"children": 0.5},
    {"dep_hour_from": 6.5, "dep_hour_to": 12},
    {"dep_hour_from": 6, "dep_hour_to": 12.5},
]
TRIP_OPTION_ACCEPTS: list[dict[str, Any]] = [
    {"cabin": "premium_economy"},
    {"cabin": "first", "adults": 9},
    {"adults": 1, "children": 8},
    {"airlines": "BR,CI"},
    {"airlines": "5J,7C,BR,CI,JX"},
    {"dep_hour_from": 0, "dep_hour_to": 23},
]


@pytest.mark.parametrize("values", TRIP_OPTION_REJECTS)
def test_check_constraints_reject(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, values: dict[str, Any]
) -> None:
    database = build_v2_db(tmp_path / "fd.db", monkeypatch)
    database.migrate()
    with database.connect() as conn, pytest.raises(sqlite3.IntegrityError):
        insert_watch(conn, **values)


@pytest.mark.parametrize("values", TRIP_OPTION_ACCEPTS)
def test_check_constraints_accept(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, values: dict[str, Any]
) -> None:
    database = build_v2_db(tmp_path / "fd.db", monkeypatch)
    database.migrate()
    with database.connect() as conn:
        insert_watch(conn, **values)


@pytest.mark.parametrize(
    "value,ok",
    [
        ("07:55", True),
        ("23:59", True),
        ("7:55", False),
        ("24:00", False),
        ("07:60", False),
        (None, True),
    ],
)
def test_depart_time_check(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, value: str | None, ok: bool
) -> None:
    database = build_v2_db(tmp_path / "fd.db", monkeypatch)
    database.migrate()

    def insert() -> None:
        with database.connect() as conn:
            conn.execute(
                "INSERT INTO price_observation (scan_run_id, watch_id, watch_revision, source,"
                " price_kind, depart_date, amount_minor, currency, as_of, as_of_basis,"
                " fetched_at, depart_time) VALUES (10, 1, 1, 'google_flights', 'live',"
                " '2026-12-10', 1, 'TWD', ?, 'fetch_time', ?, ?)",
                (TS, TS, value),
            )

    if ok:
        insert()
    else:
        with pytest.raises(sqlite3.IntegrityError):
            insert()


def test_existing_db_is_backed_up_as_pre_v3(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    database = build_v2_db(tmp_path / "flight-deals.db", monkeypatch)
    database.migrate()
    backup = backup_path(database.path, 3)
    assert backup == tmp_path / "flight-deals.pre-v3.db"
    assert backup.is_file() and fnmatch.fnmatch(backup.name, "*.db")
    copy = Database(backup)
    assert copy.schema_version() == 2
    assert counts(copy)["notification_item"] == 3


def test_new_db_gets_no_backup(tmp_path: Path) -> None:
    database = Database(tmp_path / "fresh.db")
    assert database.migrate() == LATEST
    assert sorted(p.name for p in tmp_path.glob("*.db")) == ["fresh.db"]


def test_failure_mid_migration_leaves_v2_intact(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:  # AC-C7
    database = build_v2_db(tmp_path / "fd.db", monkeypatch)
    before = watch_rows(database)
    broken = sql_0003() + "\nINSERT INTO no_such_table VALUES (1);\n"
    monkeypatch.setattr(db_module, "available_migrations", lambda: [*only_up_to(2)(), (3, broken)])
    with pytest.raises(sqlite3.OperationalError):
        database.migrate()
    assert database.schema_version() == 2
    assert watch_rows(database) == before
    with database.connect() as conn:
        tables = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        cols = {r[1] for r in conn.execute("PRAGMA table_info(price_observation)")}
    assert "watch_new" not in tables and "depart_time" not in cols
    monkeypatch.setattr(db_module, "available_migrations", ORIGINAL_MIGRATIONS)
    assert database.migrate() == LATEST  # the next start upgrades normally
    assert counts(database)["notification_item"] == 3

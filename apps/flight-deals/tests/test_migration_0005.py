"""Migration 0005: notification kinds for commands plus list / purge indexes
(ADR-0002 FD-7 Decisions 6 and 9, C-52)."""

from __future__ import annotations

import re
import sqlite3
from pathlib import Path

import pytest

from flight_deals.storage import db as db_module
from flight_deals.storage.db import Database, backup_path, needs_foreign_keys_off
from tests.test_migration_0003 import ORIGINAL_MIGRATIONS, TABLES, TS, counts, only_up_to
from tests.test_migration_0004 import build_v3_db

NEW_INDEXES = {
    "ix_notification_created",
    "ix_notification_observation",
    "ix_notification_item_notification",
    "ix_price_observation_scan_run",
    "ix_scan_run_watch_id",
    "ix_scan_run_watch_rev",
}


def sql_0005() -> str:
    return dict(ORIGINAL_MIGRATIONS())[5]


def build_v4_db(path: Path, monkeypatch: pytest.MonkeyPatch) -> Database:
    database = build_v3_db(path, monkeypatch)
    assert database.migrate() == 4
    with database.connect() as conn:
        conn.execute(
            "INSERT INTO notification (id, watch_id, kind, dedupe_key, status, attempts,"
            " message_text, created_at) VALUES (7, NULL, 'daily_digest', 'digest:2026-10-25',"
            " 'sent', 1, 'digest', ?)",
            (TS,),
        )
    # Later migrations (0006+) have their own tests; stop at 5 here.
    monkeypatch.setattr(db_module, "available_migrations", only_up_to(5))
    return database


def insert_notification(conn: sqlite3.Connection, kind: str, key: str) -> None:
    conn.execute(
        "INSERT INTO notification (kind, dedupe_key, status, message_text, created_at)"
        " VALUES (?, ?, 'pending', 'x', ?)",
        (kind, key, TS),
    )


def test_0005_rebuilds_only_notification() -> None:  # C-52
    sql = sql_0005()
    assert needs_foreign_keys_off(sql)
    assert re.findall(r"CREATE TABLE (\w+)", sql) == ["notification_new"]
    upper = sql.upper()
    for table in ("SCAN_RUN", "PRICE_OBSERVATION"):
        assert f"CREATE TABLE {table}" not in upper
        assert f"DROP TABLE {table}" not in upper
        assert f"ALTER TABLE {table}" not in upper
    assert re.findall(r"DROP TABLE (\w+)", sql) == ["notification"]
    assert re.findall(r"ALTER TABLE (\w+) RENAME", sql) == ["notification_new"]
    assert set(re.findall(r"CREATE INDEX (\w+)", sql)) == NEW_INDEXES


def test_v4_data_survives_and_backup_is_taken(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:  # AC-H1, C-52
    database = build_v4_db(tmp_path / "flight-deals.db", monkeypatch)
    before = counts(database)
    with database.connect() as conn:
        rows_before = {
            t: [tuple(r) for r in conn.execute(f"SELECT * FROM {t} ORDER BY rowid")] for t in TABLES
        }
    assert database.migrate() == 5
    assert counts(database) == before
    with database.connect() as conn:
        for table, rows in rows_before.items():
            assert [tuple(r) for r in conn.execute(f"SELECT * FROM {table} ORDER BY rowid")] == (
                rows
            )
        assert conn.execute("PRAGMA foreign_key_check").fetchall() == []
        indexes = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='index'")}
    assert NEW_INDEXES | {"ix_notification_item_key", "sqlite_autoindex_notification_1"} <= indexes
    backup = backup_path(database.path, 5)
    assert backup == tmp_path / "flight-deals.pre-v5.db" and backup.is_file()
    assert Database(backup).schema_version() == 4


def test_new_db_gets_no_backup(tmp_path: Path) -> None:
    database = Database(tmp_path / "fresh.db")
    assert database.migrate() >= 5
    assert sorted(p.name for p in tmp_path.glob("*.db")) == ["fresh.db"]


def test_new_kinds_accepted_and_others_still_rejected(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:  # C-52
    database = build_v4_db(tmp_path / "fd.db", monkeypatch)
    database.migrate()
    with database.connect() as conn:
        insert_notification(conn, "command", "cmd:1:1")
        insert_notification(conn, "manual_digest", "digest-manual:1:1")
    with pytest.raises(sqlite3.IntegrityError), database.connect() as conn:
        insert_notification(conn, "chat", "x")
    with pytest.raises(sqlite3.IntegrityError), database.connect() as conn:
        conn.execute(
            "INSERT INTO notification_item (notification_id, item_key, depart_date,"
            " amount_minor, currency, reasons, fetched_at) VALUES (9999, 'k', '2026-12-10', 1,"
            " 'TWD', 'new_low', ?)",
            (TS,),
        )


def test_notification_items_still_cascade(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    database = build_v4_db(tmp_path / "fd.db", monkeypatch)
    database.migrate()
    with database.connect() as conn:
        conn.execute("DELETE FROM notification WHERE id = 5")
        left = conn.execute("SELECT COUNT(*) FROM notification_item WHERE notification_id = 5")
        assert left.fetchone()[0] == 0


def test_list_query_plan_uses_indexes(tmp_path: Path) -> None:  # C-52, Decision 9
    from flight_deals.storage.repository import LIST_WATCHES_SQL

    database = Database(tmp_path / "plan.db")
    database.migrate()
    assert "OVER (" not in LIST_WATCHES_SQL.upper()
    with database.connect() as conn:
        plan = [r["detail"] for r in conn.execute("EXPLAIN QUERY PLAN " + LIST_WATCHES_SQL, (3,))]
    text = "\n".join(plan)
    assert not re.search(r"\bSCAN scan_run\b", text), text
    assert not re.search(r"\bSCAN s\b", text), text
    assert "ix_scan_run_watch_id" in text or "ix_scan_run_watch_rev" in text, text


def test_only_up_to_helper_still_pins_older_versions(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(db_module, "available_migrations", only_up_to(4))
    assert Database(tmp_path / "v4.db").migrate() == 4

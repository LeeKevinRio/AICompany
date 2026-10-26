"""Migration 0002: rebuild ``notification`` with foreign keys off (ADR-0002 FD-4, C-33)."""

from __future__ import annotations

import fnmatch
import sqlite3
from collections.abc import Callable
from pathlib import Path

import pytest

from flight_deals.storage import db as db_module
from flight_deals.storage.db import (
    Database,
    MigrationError,
    available_migrations,
    backup_path,
    needs_foreign_keys_off,
)

ORIGINAL_MIGRATIONS: Callable[[], list[tuple[int, str]]] = available_migrations


def only_up_to(version: int) -> Callable[[], list[tuple[int, str]]]:
    return lambda: [m for m in ORIGINAL_MIGRATIONS() if m[0] <= version]


def build_v1_db(path: Path, monkeypatch: pytest.MonkeyPatch) -> Database:
    """A v1 database with one watch, one price alert and two notification items."""
    monkeypatch.setattr(db_module, "available_migrations", only_up_to(1))
    database = Database(path)
    assert database.migrate() == 1
    with database.connect() as conn:
        conn.execute(
            "INSERT INTO watch (id, name, destination, trip_type, date_mode, depart_date,"
            " return_date, created_at, updated_at) VALUES (1, 'w', 'NRT', 'round_trip',"
            " 'fixed', '2026-12-10', '2026-12-15', '2026-10-25T04:00:00+00:00',"
            " '2026-10-25T04:00:00+00:00')"
        )
        conn.execute(
            "INSERT INTO notification (id, watch_id, kind, rule, price_kind, dedupe_key, status,"
            " attempts, message_text, created_at) VALUES (7, 1, 'price_alert', 'below_budget',"
            " 'live', 'price:1:live:x', 'sent', 1, 'alert text', '2026-10-25T04:00:00+00:00')"
        )
        conn.execute(
            "INSERT INTO notification (id, kind, dedupe_key, status, message_text, created_at)"
            " VALUES (8, 'test', 'test:1', 'failed', 'test text', '2026-10-25T04:01:00+00:00')"
        )
        for key in ("item-a", "item-b"):
            conn.execute(
                "INSERT INTO notification_item (notification_id, item_key, depart_date,"
                " return_date, amount_minor, currency, reasons, fetched_at) VALUES"
                " (7, ?, '2026-12-10', '2026-12-15', 900000, 'TWD', 'below_budget',"
                " '2026-10-25T04:00:00+00:00')",
                (key,),
            )
    monkeypatch.setattr(db_module, "available_migrations", ORIGINAL_MIGRATIONS)
    return database


def counts(database: Database) -> tuple[int, int]:
    with database.connect() as conn:
        n = conn.execute("SELECT COUNT(*) FROM notification").fetchone()[0]
        i = conn.execute("SELECT COUNT(*) FROM notification_item").fetchone()[0]
    return int(n), int(i)


def insert_kind(conn: sqlite3.Connection, kind: str, key: str) -> None:
    conn.execute(
        "INSERT INTO notification (kind, dedupe_key, status, message_text, created_at)"
        " VALUES (?, ?, 'pending', 'x', '2026-10-26T00:00:00+00:00')",
        (kind, key),
    )


def test_0002_is_marked_foreign_keys_off() -> None:
    migrations = dict(available_migrations())
    assert 2 in migrations
    assert needs_foreign_keys_off(migrations[2])
    assert not needs_foreign_keys_off(migrations[1])


def test_v1_data_survives_and_daily_digest_is_writable(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    database = build_v1_db(tmp_path / "fd.db", monkeypatch)
    assert counts(database) == (2, 2)
    assert database.migrate() == 2
    assert counts(database) == (2, 2)
    with database.connect() as conn:
        row = conn.execute("SELECT * FROM notification WHERE id = 7").fetchone()
        assert (row["kind"], row["status"], row["message_text"]) == (
            "price_alert",
            "sent",
            "alert text",
        )
        insert_kind(conn, "daily_digest", "digest:2026-10-26")
    with database.connect() as conn, pytest.raises(sqlite3.IntegrityError):
        insert_kind(conn, "weekly_report", "weekly:1")


def test_foreign_keys_still_enforced_after_rebuild(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    database = build_v1_db(tmp_path / "fd.db", monkeypatch)
    database.migrate()
    with database.connect() as conn:
        assert conn.execute("PRAGMA foreign_keys").fetchone()[0] == 1
        assert conn.execute("PRAGMA foreign_key_check").fetchall() == []
        ddl = conn.execute(
            "SELECT sql FROM sqlite_master WHERE name = 'notification_item'"
        ).fetchone()[0]
        assert "REFERENCES notification(id)" in ddl
    with database.connect() as conn, pytest.raises(sqlite3.IntegrityError):
        conn.execute(
            "INSERT INTO notification_item (notification_id, item_key, depart_date,"
            " amount_minor, currency, reasons, fetched_at)"
            " VALUES (999, 'orphan', '2026-12-10', 1, 'TWD', 'x', 'now')"
        )
    # The cascade still points at the rebuilt table.
    with database.connect() as conn:
        conn.execute("DELETE FROM notification WHERE id = 7")
    assert counts(database) == (1, 0)


def test_indexes_exist_after_rebuild(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    database = build_v1_db(tmp_path / "fd.db", monkeypatch)
    database.migrate()
    with database.connect() as conn:
        names = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type = 'index'")}
        tables = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type = 'table'")}
    assert {"ix_notification_created", "ix_notification_item_key"} <= names
    assert any(n.startswith("sqlite_autoindex_notification") for n in names)  # UNIQUE key
    assert "notification_new" not in tables


def test_existing_db_is_backed_up_next_to_it(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    database = build_v1_db(tmp_path / "flight-deals.db", monkeypatch)
    database.migrate()
    backup = backup_path(database.path, 2)
    assert backup == tmp_path / "flight-deals.pre-v2.db"
    assert backup.is_file()
    assert fnmatch.fnmatch(backup.name, "*.db")  # covered by the app's *.db gitignore
    copy = Database(backup)
    assert copy.schema_version() == 1
    assert counts(copy) == (2, 2)


def test_new_db_gets_no_backup(tmp_path: Path) -> None:
    database = Database(tmp_path / "fresh.db")
    assert database.migrate() == 2
    assert sorted(p.name for p in tmp_path.glob("*.db")) == ["fresh.db"]


def test_rebuild_under_foreign_keys_on_would_cascade(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Why the marker exists: the same SQL with foreign keys ON deletes every item."""
    database = build_v1_db(tmp_path / "fd.db", monkeypatch)
    sql = dict(available_migrations())[2]
    conn = sqlite3.connect(database.path)
    try:
        conn.execute("PRAGMA foreign_keys = ON")
        conn.executescript(sql)
        assert conn.execute("SELECT COUNT(*) FROM notification_item").fetchone()[0] == 0
    finally:
        conn.close()


def test_violation_rolls_back_and_raises(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    database = Database(tmp_path / "fd.db")
    database.migrate()
    bad = (
        "-- flight-deals: foreign_keys=off\n"
        "INSERT INTO notification_item (notification_id, item_key, depart_date, amount_minor,"
        " currency, reasons, fetched_at) VALUES (424242, 'orphan', '2026-12-10', 1, 'TWD',"
        " 'x', 'now');\n"
    )
    monkeypatch.setattr(
        db_module, "available_migrations", lambda: [*ORIGINAL_MIGRATIONS(), (99, bad)]
    )
    with pytest.raises(MigrationError):
        database.migrate()
    assert database.schema_version() == 2
    assert counts(database) == (0, 0)


class _FailingBackupConnection:
    """Delegates to a real connection, but ``backup`` dies after creating the target."""

    def __init__(self, conn: sqlite3.Connection) -> None:
        self._conn = conn

    def backup(self, target: sqlite3.Connection) -> None:
        target.execute("CREATE TABLE partial (x)")
        target.commit()
        raise sqlite3.OperationalError("disk I/O error (simulated)")

    def __getattr__(self, name: str) -> object:
        return getattr(self._conn, name)


def test_failed_backup_leaves_no_partial_file(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:  # qa M2
    database = build_v1_db(tmp_path / "flight-deals.db", monkeypatch)
    real_open = Database._open
    calls = {"n": 0}

    def open_with_failing_backup(self: Database) -> object:
        conn = real_open(self)
        calls["n"] += 1
        return _FailingBackupConnection(conn)

    monkeypatch.setattr(Database, "_open", open_with_failing_backup)
    with pytest.raises(sqlite3.OperationalError):
        database._backup(2, expected_version=1)
    assert calls["n"] == 1
    monkeypatch.setattr(Database, "_open", real_open)
    assert sorted(p.name for p in tmp_path.iterdir() if "pre-v2" in p.name) == []
    assert database.schema_version() == 1
    assert database.migrate() == 2  # a later start backs up and migrates normally
    assert Database(backup_path(database.path, 2)).schema_version() == 1


def test_wrong_existing_backup_is_redone(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    database = build_v1_db(tmp_path / "flight-deals.db", monkeypatch)
    stale = backup_path(database.path, 2)
    stale.write_bytes(b"not a database")
    database.migrate()
    copy = Database(stale)
    assert copy.schema_version() == 1 and counts(copy) == (2, 2)
    assert not stale.with_name(stale.name + ".tmp").exists()

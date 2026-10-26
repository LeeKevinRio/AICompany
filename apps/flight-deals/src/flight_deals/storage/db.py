"""SQLite connection handling and numbered SQL migrations.

A migration whose first line is ``-- flight-deals: foreign_keys=off`` is applied on a
connection with foreign keys disabled (set before ``BEGIN``; the pragma is a no-op
inside a transaction). Every migration runs ``PRAGMA foreign_key_check`` before COMMIT
and rolls back on any violation. An existing database is copied with
``Connection.backup()`` to ``<stem>.pre-v<N>.db`` before migration N is applied.
"""

from __future__ import annotations

import logging
import os
import re
import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from importlib import resources
from pathlib import Path

_MIGRATION_NAME = re.compile(r"^(\d{4})_[a-z0-9_]+\.sql$")
BUSY_TIMEOUT_MS = 5000
FOREIGN_KEYS_OFF_MARKER = "-- flight-deals: foreign_keys=off"

log = logging.getLogger(__name__)


class MigrationError(RuntimeError):
    """A migration left the database inconsistent and was rolled back."""


def needs_foreign_keys_off(sql: str) -> bool:
    lines = sql.lstrip("\ufeff").splitlines()
    return bool(lines) and lines[0].strip() == FOREIGN_KEYS_OFF_MARKER


def backup_path(db_path: Path, version: int) -> Path:
    """Backup taken before applying ``version``: same folder, still matches ``*.db``."""
    return db_path.with_name(f"{db_path.stem}.pre-v{version}.db")


def available_migrations() -> list[tuple[int, str]]:
    """(version, sql) pairs from the bundled ``migrations`` directory, ascending."""
    found: list[tuple[int, str]] = []
    folder = resources.files("flight_deals.storage").joinpath("migrations")
    for entry in folder.iterdir():
        match = _MIGRATION_NAME.match(entry.name)
        if match:
            found.append((int(match.group(1)), entry.read_text(encoding="utf-8")))
    return sorted(found)


def _schema_version_of(path: Path) -> int | None:
    """Schema version of a database file, or None if it cannot be read."""
    try:
        conn = sqlite3.connect(f"file:{path.as_posix()}?mode=ro", uri=True)
        try:
            row = conn.execute("SELECT MAX(version) FROM schema_version").fetchone()
        finally:
            conn.close()
    except sqlite3.Error:
        return None
    return int(row[0]) if row and row[0] is not None else None


class Database:
    """Opens a fresh connection per unit of work (safe across scheduler/web threads)."""

    def __init__(self, path: Path) -> None:
        self.path = path

    def _open(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.path, timeout=BUSY_TIMEOUT_MS / 1000)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        conn.execute(f"PRAGMA busy_timeout = {BUSY_TIMEOUT_MS}")
        return conn

    @contextmanager
    def connect(self) -> Iterator[sqlite3.Connection]:
        conn = self._open()
        try:
            yield conn
            conn.commit()
        except BaseException:
            conn.rollback()
            raise
        finally:
            conn.close()

    def schema_version(self) -> int:
        with self.connect() as conn:
            conn.execute("CREATE TABLE IF NOT EXISTS schema_version (version INTEGER NOT NULL)")
            row = conn.execute("SELECT MAX(version) AS v FROM schema_version").fetchone()
            return int(row["v"] or 0)

    def migrate(self) -> int:
        """Apply pending migrations; returns the resulting schema version."""
        self.path.parent.mkdir(parents=True, exist_ok=True)
        conn = self._open()
        try:
            conn.execute("PRAGMA journal_mode = WAL")
        finally:
            conn.close()
        current = self.schema_version()
        existing = current >= 1  # a brand-new database has nothing worth backing up
        for version, sql in available_migrations():
            if version <= current:
                continue
            if existing:
                self._backup(version, expected_version=current)
            self._apply(version, sql)
            current = version
        return current

    def _backup(self, version: int, *, expected_version: int) -> None:
        """Copy the database before ``version`` is applied (atomic: temp file + replace).

        An existing backup is kept only if it really is the pre-``version`` state.
        """
        target = backup_path(self.path, version)
        if target.exists() and _schema_version_of(target) == expected_version:
            log.info("backup %s already exists; keeping it", target.name)
            return
        temp = target.with_name(target.name + ".tmp")
        try:
            source = self._open()
            try:
                dest = sqlite3.connect(temp)
                try:
                    source.backup(dest)
                finally:
                    dest.close()
            finally:
                source.close()
            os.replace(temp, target)
        except BaseException:
            temp.unlink(missing_ok=True)
            raise
        log.info("database backed up to %s before migration %d", target.name, version)

    def _apply(self, version: int, sql: str) -> None:
        conn = self._open()
        try:
            if needs_foreign_keys_off(sql):
                # Must happen outside a transaction, otherwise SQLite ignores it.
                conn.execute("PRAGMA foreign_keys = OFF")
                if conn.execute("PRAGMA foreign_keys").fetchone()[0] != 0:
                    raise MigrationError(f"migration {version}: could not disable foreign keys")
            conn.executescript("BEGIN;\n" + sql)
            violations = conn.execute("PRAGMA foreign_key_check").fetchall()
            if violations:
                raise MigrationError(
                    f"migration {version}: {len(violations)} foreign key violation(s)"
                )
            conn.execute("INSERT INTO schema_version VALUES (?)", (version,))
            conn.commit()
        except BaseException:
            if conn.in_transaction:
                conn.rollback()
            raise
        finally:
            conn.close()

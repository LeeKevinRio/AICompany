"""SQLite connection helpers shared by every store, whichever database file it owns.

A leaf module (ADR-0012 v10): it imports only the standard library -- no
``app.*`` module, no environment or configuration -- so any store may take
:func:`enable_wal` from here without reaching another store's database path or
tables. Each database keeps its own ``busy_timeout`` policy; this module sets
none and opens no connection. :func:`add_missing_columns` is the shared
in-place column migration, safe against every other connection on the file.
"""

from __future__ import annotations

import sqlite3
from collections.abc import Mapping
from time import monotonic, sleep
from typing import Final

#: Primary result code of ``SQLITE_BUSY`` (extended codes keep it in the low byte).
_SQLITE_BUSY: Final[int] = 5
#: First pause between :func:`enable_wal` attempts; doubles up to the maximum.
_WAL_FIRST_RETRY_DELAY_S: Final[float] = 0.005
_WAL_MAX_RETRY_DELAY_S: Final[float] = 0.1
#: Journal modes :func:`enable_wal` accepts back: ``memory`` is what an
#: in-memory database reports, since it has no file to put into WAL mode.
_WAL_ACCEPTED_MODES: Final[frozenset[str]] = frozenset({"wal", "memory"})


def enable_wal(conn: sqlite3.Connection) -> None:
    """Issue ``PRAGMA journal_mode=WAL`` on ``conn``, riding out a concurrent switch.

    Stores put their database file into WAL mode when constructed. On a
    file not in WAL mode yet -- a database written before WAL was adopted, or
    a brand-new empty one -- the switch is a write: SQLite opens a read
    transaction (shared lock), then upgrades it to an exclusive lock to
    rewrite the file header. When two connections do this at once (the
    backend and a CLI starting against the same file), both hold the shared
    lock, one takes the reserved lock and waits for the other to let go, and
    the other's upgrade is refused with ``SQLITE_BUSY`` *immediately*: SQLite
    skips the busy handler for a lock upgrade out of an open read transaction
    because waiting there could deadlock (``sqlite3_busy_handler`` docs). So
    ``busy_timeout`` does not help and the loser failed with "database is
    locked" within a millisecond.

    The refusal comes before the loser has changed anything, and its read
    transaction ends with the failed statement, so the switch is retried; by
    then the winner has usually converted the file and the retry is a no-op.
    Retries run for as long as the connection's own ``busy_timeout`` allows
    -- the wait any other statement on it would get -- and a lock still held
    past that deadline, like every other error, is raised unchanged. The
    caller therefore sets ``busy_timeout`` first.

    SQLite does not fail a switch it cannot make; it answers with the mode the
    database stayed in. Anything but ``wal`` (or ``memory`` for an in-memory
    database) is therefore raised here, rather than letting the stores run on
    a rollback journal whose readers and writers block each other.

    Must be called outside any open transaction (SQLite refuses to change into
    WAL mode inside one), before the store's own DDL / DML.
    """
    (timeout_ms,) = conn.execute("PRAGMA busy_timeout").fetchone()
    deadline = monotonic() + int(timeout_ms) / 1000
    delay = _WAL_FIRST_RETRY_DELAY_S
    while True:
        try:
            (mode,) = conn.execute("PRAGMA journal_mode=WAL").fetchone()
            break
        except sqlite3.OperationalError as error:
            if (error.sqlite_errorcode & 0xFF) != _SQLITE_BUSY or monotonic() >= deadline:
                raise
        sleep(delay)
        delay = min(delay * 2, _WAL_MAX_RETRY_DELAY_S)
    if str(mode).lower() not in _WAL_ACCEPTED_MODES:
        raise sqlite3.OperationalError(
            f"could not switch the database to WAL journal mode; it stayed in {mode!r}"
        )


def _missing_columns(conn: sqlite3.Connection, table: str, columns: Mapping[str, str]) -> list[str]:
    """Names in ``columns`` the live ``table`` does not have, in ``columns`` order."""
    existing = {str(row[1]) for row in conn.execute(f"PRAGMA table_info({table})")}
    return [column for column in columns if column not in existing]


def add_missing_columns(conn: sqlite3.Connection, table: str, columns: Mapping[str, str]) -> None:
    """``ALTER TABLE table ADD COLUMN`` each of ``columns`` (name -> definition) it lacks.

    For a table created by ``CREATE TABLE IF NOT EXISTS`` before some columns
    were declared: the statement leaves an existing table as it is, so the
    columns are added in place, which SQLite can do for a nullable column or
    one with a constant default.

    Safe when several connections -- threads of one process, or the backend
    and the scheduler as two processes -- construct a store on the same file
    at once, which a bare ``PRAGMA``-then-``ALTER`` is not: SQLite runs DDL
    outside the implicit transaction Python's sqlite3 opens for DML, so two
    of them could both read "column missing" and the loser's ``ALTER`` failed
    with ``duplicate column name`` (N-154). So the work runs inside one
    ``BEGIN IMMEDIATE``: the write lock is taken up front (waiting out the
    connection's ``busy_timeout``), the schema is re-read *under* it, and the
    loser of a race finds nothing left to add. The columns are also added
    atomically -- a failure part-way rolls every one of them back.

    A table that already has every column costs one ``PRAGMA`` and no lock, so
    this is cheap on every store construction. Every error is raised: a
    missing table, a lock still held past ``busy_timeout``, an invalid
    definition -- a migration that silently did nothing would be worse than a
    loud failure.

    ``table`` and the column names and definitions are interpolated into SQL,
    so they must be the caller's own constants, never user input. Must be
    called outside any open transaction (true in a store's schema set-up,
    where everything before it is a PRAGMA or DDL).
    """
    if not _missing_columns(conn, table, columns):
        return
    conn.execute("BEGIN IMMEDIATE")
    try:
        # Empty when another connection finished while this one waited at
        # BEGIN; COMMIT anyway so the write lock is released here, not at
        # whatever later point the caller ends its work.
        for column in _missing_columns(conn, table, columns):
            conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} {columns[column]}")
        conn.execute("COMMIT")
    except BaseException:
        # SQLite may already have rolled back on its own (a full disk, say);
        # a second ROLLBACK would then replace the real error with its own.
        if conn.in_transaction:
            conn.execute("ROLLBACK")
        raise

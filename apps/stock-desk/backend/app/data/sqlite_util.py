"""SQLite connection helpers shared by every store, whichever database file it owns.

A leaf module (ADR-0012 v10): it imports only the standard library -- no
``app.*`` module, no environment or configuration -- so any store may take
:func:`enable_wal` from here without reaching another store's database path or
tables. Each database keeps its own ``busy_timeout`` policy; this module sets
none and opens no connection.
"""

from __future__ import annotations

import sqlite3
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

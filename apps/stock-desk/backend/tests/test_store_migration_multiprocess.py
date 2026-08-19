"""D8④: the legacy-schema migrations raced by two *real* OS processes.

The D7 batch pinned the concurrency story of both stores' migrations with
in-process reproductions: threads racing the real code, plus stale-PRAGMA
connections that force each loser path deterministically
(``test_positions_store.py``, ``test_directory_sector_persist.py``). qa-reviewer
noted (low, ``work/reviews/2026-08-16-品質債清償批-覆核.md``) that none of that
exercises what the docstrings actually promise -- "the backend and the sync CLI
starting together": two interpreters, two connections owned by different
processes, real SQLite file locking between them.

This test does exactly that. Two subprocesses running this repo's real store
constructors are released against the same legacy database file at once (a
file-based barrier keeps them aligned to the migration window), and both must
survive with every row intact. Everything happens on a ``tmp_path`` database
seeded here -- no real data is anywhere near this test.
"""

from __future__ import annotations

import sqlite3
import subprocess
import sys
import time
from contextlib import closing
from pathlib import Path

from app.directory.store import SecurityDirectoryStore
from app.positions.store import _MIGRATION_TABLE, PositionStore

#: ``positions`` before both of its migrations: ``opened_at`` still NOT NULL
#: and no ``sector`` column -- the ALTER migration *and* the rebuild migration
#: both have work to do, so the race covers both shapes at once.
_LEGACY_POSITIONS_SQL = """
CREATE TABLE positions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    symbol TEXT NOT NULL,
    market TEXT NOT NULL,
    quantity TEXT NOT NULL,
    avg_cost TEXT NOT NULL,
    currency TEXT NOT NULL,
    opened_at TEXT NOT NULL,
    instrument_type TEXT NOT NULL,
    note TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
)
"""

#: ``security_directory`` before the three ``sector*`` columns existed.
_LEGACY_DIRECTORY_SQL = """
CREATE TABLE security_directory (
    symbol TEXT NOT NULL,
    market TEXT NOT NULL,
    name TEXT NOT NULL,
    source TEXT NOT NULL,
    as_of TEXT NOT NULL,
    synced_at TEXT NOT NULL,
    PRIMARY KEY (symbol, market)
)
"""

_DIRECTORY_ROWS = 24

#: Run by each racing process (``python -c``). Mirrors the real deployment's
#: startup: construct both stores against the shared database file, then read
#: back through them to prove the connection still works after the race. The
#: ready-file / go-file pair is a cross-process barrier: both processes have
#: imported everything and are one statement away from the migration before
#: either is released, so the whole interpreter startup cost cannot serialise
#: the actual race window.
_WORKER_SOURCE = f"""
import sys
import time
from pathlib import Path

from app.directory.store import SecurityDirectoryStore
from app.positions.store import PositionStore

db_path, ready_path, go_path = sys.argv[1], sys.argv[2], sys.argv[3]
Path(ready_path).touch()
deadline = time.monotonic() + 30
while not Path(go_path).exists():
    if time.monotonic() > deadline:
        sys.exit(2)  # the parent never released the barrier
    time.sleep(0.001)

positions = PositionStore(db_path=db_path)
directory = SecurityDirectoryStore(db_path=db_path)
assert len(positions.list_all()) == 1
assert directory.count() == {_DIRECTORY_ROWS}
"""


def _seed_legacy_db(db_path: Path) -> None:
    """One database file holding both legacy tables, as deployment shares one."""
    with closing(sqlite3.connect(db_path)) as conn, conn:
        conn.execute(_LEGACY_POSITIONS_SQL)
        conn.execute(
            """
            INSERT INTO positions
                (symbol, market, quantity, avg_cost, currency, opened_at,
                 instrument_type, note, created_at, updated_at)
            VALUES ('2330', 'TW', '1000', '600.5', 'TWD', '2024-01-02',
                    'stock', '台積電', '2024-01-02T00:00:00+00:00',
                    '2024-01-02T00:00:00+00:00')
            """
        )
        conn.execute(_LEGACY_DIRECTORY_SQL)
        conn.executemany(
            "INSERT INTO security_directory (symbol, market, name, source, as_of, synced_at) "
            "VALUES (?, 'TW', ?, 'twse_openapi', '2026-08-09T12:00:00+00:00', "
            "'2026-08-09T12:00:00+00:00')",
            [(f"{1000 + i}", f"舊資料公司{i}") for i in range(_DIRECTORY_ROWS)],
        )


def test_two_real_processes_migrating_the_same_legacy_database_both_survive(
    tmp_path: Path,
) -> None:
    db_path = tmp_path / "legacy.db"
    _seed_legacy_db(db_path)

    workers: list[subprocess.Popen[str]] = []
    ready_paths = [tmp_path / f"ready-{index}" for index in range(2)]
    go_path = tmp_path / "go"
    for ready_path in ready_paths:
        workers.append(
            subprocess.Popen(
                [sys.executable, "-c", _WORKER_SOURCE, str(db_path), str(ready_path), str(go_path)],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
            )
        )

    try:
        deadline = time.monotonic() + 30
        while not all(ready_path.exists() for ready_path in ready_paths):
            assert time.monotonic() < deadline, "workers never reached the barrier"
            assert all(worker.poll() is None for worker in workers), [
                worker.communicate() for worker in workers if worker.poll() is not None
            ]
            time.sleep(0.001)
        go_path.touch()

        for worker in workers:
            stdout, stderr = worker.communicate(timeout=60)
            assert worker.returncode == 0, f"worker failed\nstdout: {stdout}\nstderr: {stderr}"
    finally:
        for worker in workers:
            if worker.poll() is None:
                worker.kill()
                worker.communicate()

    # Both migrations finished exactly once, whoever won each of them.
    with closing(sqlite3.connect(db_path)) as conn:
        position_columns = [
            column[1] for column in conn.execute("PRAGMA table_info(positions)")
        ]
        opened_at_not_null = any(
            column[1] == "opened_at" and column[3]
            for column in conn.execute("PRAGMA table_info(positions)").fetchall()
        )
        directory_columns = [
            column[1] for column in conn.execute("PRAGMA table_info(security_directory)")
        ]
        leftover = conn.execute(
            "SELECT name FROM sqlite_master WHERE name = ?", (_MIGRATION_TABLE,)
        ).fetchall()
    assert position_columns.count("sector") == 1
    assert not opened_at_not_null
    assert leftover == []
    for column in ("sector", "sector_source", "sector_as_of"):
        assert directory_columns.count(column) == 1

    # No row was lost or altered by the concurrent rebuild.
    rows = PositionStore(db_path=db_path).list_all()
    assert len(rows) == 1
    assert rows[0].note == "台積電"
    assert rows[0].sector is None
    directory = SecurityDirectoryStore(db_path=db_path)
    assert directory.count() == _DIRECTORY_ROWS
    entry = directory.resolve("1000")
    assert entry is not None
    assert entry.sector is None

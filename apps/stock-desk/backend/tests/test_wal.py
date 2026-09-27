"""The WAL switch every store makes on construction must survive a concurrent one.

The two-thread "open the same legacy database at once" tests in the store
suites hit the race only now and then. These tests pin down the exact state
the loser of that race is in -- another connection already holds the write
lock while this one upgrades out of the read transaction the switch opens --
so a regression fails every time instead of one run in ten.
"""

from __future__ import annotations

import sqlite3
import threading
from collections.abc import Callable
from contextlib import closing
from pathlib import Path
from typing import Protocol

import pytest

from app.alerts.store import AlertStore
from app.data import market_panel
from app.data.cache import BUSY_TIMEOUT_MS, PriceBarCache
from app.data.market_panel import MarketPanelStore
from app.data.quota import QuotaLedger
from app.data.sqlite_util import enable_wal
from app.directory.store import SecurityDirectoryStore
from app.dividends.store import DividendEventStore
from app.kelly.attempts import KellyAttemptStore
from app.kelly.store import KellyInputStore
from app.playbook.store import PlaybookStore
from app.positions.store import PositionStore
from app.research.sector_biased import store as research_store
from app.research.sector_biased.store import ResearchStore
from app.sectors import store as sectors_store
from app.sectors.store import SectorApprovalStore
from app.settings.store import SettingsStore

#: How long the competing writer keeps the lock; well inside the 5 s busy timeout.
_HOLD_SECONDS = 0.3

#: Every store that switches its database file to WAL on construction, with the
#: busy timeout its database's own policy sets. ``MarketPanelStore`` owns the
#: market DB (ADR-0012 D-2) and ``ResearchStore`` the research DB; each keeps
#: its own value, as do the sector stores (their own ``BUSY_TIMEOUT_MS``). The
#: rest share the main file and its ``BUSY_TIMEOUT_MS``. ``QuotaLedger``
#: connects in autocommit mode and sets ``busy_timeout`` per instance (its
#: default is pinned). ``SectorApprovalStore`` has no ``__init__`` of its own
#: and stands in for the shared ``_SectorDb`` constructor (``SectorBoardStore``
#: and ``SectorCardReader`` need a verifier).
_STORES = pytest.mark.parametrize(
    ("open_store", "busy_timeout_ms"),
    [
        pytest.param(PriceBarCache, BUSY_TIMEOUT_MS, id="price_bar_cache"),
        pytest.param(SecurityDirectoryStore, BUSY_TIMEOUT_MS, id="directory"),
        pytest.param(PositionStore, BUSY_TIMEOUT_MS, id="positions"),
        pytest.param(KellyInputStore, BUSY_TIMEOUT_MS, id="kelly"),
        pytest.param(KellyAttemptStore, BUSY_TIMEOUT_MS, id="kelly_attempts"),
        pytest.param(SettingsStore, BUSY_TIMEOUT_MS, id="settings"),
        pytest.param(PlaybookStore, BUSY_TIMEOUT_MS, id="playbook"),
        pytest.param(AlertStore, BUSY_TIMEOUT_MS, id="alerts"),
        pytest.param(DividendEventStore, BUSY_TIMEOUT_MS, id="dividends"),
        pytest.param(QuotaLedger, BUSY_TIMEOUT_MS, id="quota"),
        pytest.param(MarketPanelStore, market_panel._BUSY_TIMEOUT_MS, id="market_panel"),
        pytest.param(SectorApprovalStore, sectors_store.BUSY_TIMEOUT_MS, id="sectors"),
        pytest.param(ResearchStore, research_store.BUSY_TIMEOUT_MS, id="research"),
    ],
)


class _ConnectingStore(Protocol):
    def _connect(self) -> sqlite3.Connection: ...


def _rollback_journal_db(db_path: Path) -> None:
    """A database file that is not in WAL mode yet (legacy or never opened by a store)."""
    with closing(sqlite3.connect(db_path)) as conn, conn:
        conn.execute("CREATE TABLE unrelated (value TEXT)")
    with closing(sqlite3.connect(db_path)) as conn:
        assert conn.execute("PRAGMA journal_mode").fetchone()[0] == "delete"


def _journal_mode(db_path: Path) -> str:
    with closing(sqlite3.connect(db_path)) as conn:
        return str(conn.execute("PRAGMA journal_mode").fetchone()[0])


def _hold_write_lock(db_path: Path) -> sqlite3.Connection:
    """Another process mid-write: a connection that has taken the reserved lock.

    The WAL switch on a rollback-journal file reads first (SHARED lock) and
    then upgrades. SQLite never runs the busy handler for a SHARED -> RESERVED
    upgrade inside an open read transaction (waiting there could deadlock), so
    while this lock is held that upgrade fails at once -- the loser's state in
    a two-process race, reproduced every time.
    """
    holder = sqlite3.connect(db_path, isolation_level=None, check_same_thread=False)
    holder.execute("BEGIN IMMEDIATE")
    return holder


@_STORES
def test_a_store_waits_out_a_writer_instead_of_failing_the_wal_switch(
    tmp_path: Path, open_store: Callable[..., object], busy_timeout_ms: int
) -> None:
    """SQLite refuses this upgrade without calling the busy handler; the store must wait.

    Before the retry, the constructor raised "database is locked" within a
    millisecond although the connection's busy timeout is five seconds.
    """
    db_path = tmp_path / "legacy.db"
    _rollback_journal_db(db_path)
    holder = _hold_write_lock(db_path)
    release = threading.Timer(_HOLD_SECONDS, holder.execute, args=("COMMIT",))
    try:
        release.start()
        open_store(db_path=db_path)
    finally:
        release.join()
        holder.close()

    assert _journal_mode(db_path) == "wal"


def test_enable_wal_raises_once_the_busy_timeout_has_passed(tmp_path: Path) -> None:
    """A lock that is never released still ends in the ordinary "locked" error."""
    db_path = tmp_path / "legacy.db"
    _rollback_journal_db(db_path)
    holder = _hold_write_lock(db_path)
    try:
        with closing(sqlite3.connect(db_path, timeout=0.05)) as conn:
            with pytest.raises(sqlite3.OperationalError, match="database is locked"):
                enable_wal(conn)
    finally:
        holder.execute("ROLLBACK")
        holder.close()

    assert _journal_mode(db_path) == "delete"


def test_enable_wal_does_not_retry_an_error_that_is_not_busy(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Only lock contention is waited out; anything else is raised on the first try."""
    pauses: list[float] = []
    monkeypatch.setattr("app.data.sqlite_util.sleep", pauses.append)
    db_path = tmp_path / "legacy.db"
    _rollback_journal_db(db_path)

    with closing(sqlite3.connect(db_path, isolation_level=None)) as conn:
        conn.execute("BEGIN")
        with pytest.raises(sqlite3.OperationalError, match="within a transaction"):
            enable_wal(conn)
        conn.execute("ROLLBACK")

    assert pauses == []


@pytest.mark.parametrize("already_wal", [False, True], ids=["legacy", "already-wal"])
def test_enable_wal_converts_the_file_without_waiting_when_uncontended(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, already_wal: bool
) -> None:
    pauses: list[float] = []
    monkeypatch.setattr("app.data.sqlite_util.sleep", pauses.append)
    db_path = tmp_path / "legacy.db"
    _rollback_journal_db(db_path)
    if already_wal:
        with closing(sqlite3.connect(db_path)) as conn:
            enable_wal(conn)

    with closing(sqlite3.connect(db_path)) as conn:
        enable_wal(conn)

    assert _journal_mode(db_path) == "wal"
    assert pauses == []


@_STORES
def test_every_store_connection_waits_its_database_busy_timeout(
    tmp_path: Path, open_store: Callable[..., _ConnectingStore], busy_timeout_ms: int
) -> None:
    """``enable_wal`` retries for the connection's busy timeout; pin it, not a driver default."""
    store = open_store(db_path=tmp_path / "stock-desk.db")

    with closing(store._connect()) as conn:
        (timeout_ms,) = conn.execute("PRAGMA busy_timeout").fetchone()

    assert timeout_ms == busy_timeout_ms


def test_enable_wal_raises_when_the_database_stays_out_of_wal_mode() -> None:
    """SQLite reports a switch it cannot make only through the returned mode.

    A temporary on-disk database (empty path) is one SQLite keeps in ``delete``
    mode whatever is asked; a store must not carry on as if it were WAL.
    """
    with closing(sqlite3.connect("")) as conn:
        with pytest.raises(sqlite3.OperationalError, match="stayed in 'delete'"):
            enable_wal(conn)


def test_enable_wal_accepts_an_in_memory_database() -> None:
    """``:memory:`` has no file to put into WAL mode and reports ``memory``."""
    with closing(sqlite3.connect(":memory:")) as conn:
        enable_wal(conn)
        (mode,) = conn.execute("PRAGMA journal_mode").fetchone()

    assert mode == "memory"

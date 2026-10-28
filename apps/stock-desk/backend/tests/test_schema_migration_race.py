"""Store schema migrations survive concurrent construction (N-154).

The backend builds its stores lazily, so the first page load against a brand-new
database file constructs several of them at once from the request threadpool,
while the scheduler -- a separate process -- may open the same file. A
``PRAGMA table_info``-then-``ALTER TABLE`` migration let two constructors both
read "column missing" and the loser's ``ALTER`` failed with ``duplicate column
name`` (``/api/alerts/events`` answered 500). These tests build the same store
from many threads and from many processes at once, on a fresh file and on a
legacy one, and pin the shared :func:`app.data.sqlite_util.add_missing_columns`
contract: no-op once migrated, re-check under the write lock, and every other
``OperationalError`` still raised.
"""

from __future__ import annotations

import multiprocessing
import sqlite3
import threading
from collections.abc import Callable, Iterator
from contextlib import closing
from pathlib import Path
from typing import Any, cast

import pytest

from app.alerts.store import AlertStore
from app.data.sqlite_util import add_missing_columns
from app.directory.store import SecurityDirectoryStore
from app.dividends.store import DividendEventStore
from app.kelly.store import KellyInputStore
from app.playbook.store import PlaybookStore
from app.positions.store import PositionStore
from app.sectors.store import _legacy_stats_rows, ensure_schema

#: Enough concurrent constructors that the check-then-ALTER window is hit
#: reliably without the fix, few enough to keep the spawn cost small.
_PROCESSES = 6
_THREADS = 8
_JOIN_TIMEOUT_S = 120

_FACTORIES: dict[str, Callable[[Path], object]] = {
    "alerts": lambda path: AlertStore(db_path=path),
    "dividends": lambda path: DividendEventStore(db_path=path),
    "playbook": lambda path: PlaybookStore(db_path=path),
    "positions": lambda path: PositionStore(db_path=path),
    "kelly": lambda path: KellyInputStore(db_path=path),
    "directory": lambda path: SecurityDirectoryStore(db_path=path),
    "sectors": lambda path: ensure_schema(path),
}

#: The migrated column each store must end up with exactly once.
_MIGRATED_COLUMN: dict[str, tuple[str, str]] = {
    "alerts": ("alert_events", "bar_as_of"),
    "dividends": ("dividend_events", "stock_dividend_ratio"),
    "playbook": ("playbook_directives", "data_reason"),
    "positions": ("positions", "sector"),
    "kelly": ("kelly_inputs", "oos_round_trips"),
    "directory": ("security_directory", "sector"),
}


def _columns(db_path: Path, table: str) -> list[str]:
    with closing(sqlite3.connect(db_path)) as conn:
        return [str(row[1]) for row in conn.execute(f"PRAGMA table_info({table})")]


def _build_in_child(kind: str, db_path: str, barrier: Any, error_path: str) -> None:
    """Spawned-process target: wait for every sibling, then build the store."""
    try:
        barrier.wait(timeout=60)
        _FACTORIES[kind](Path(db_path))
    except BaseException as error:  # noqa: BLE001 - reported to the parent
        Path(error_path).write_text(f"{type(error).__name__}: {error}", encoding="utf-8")
        raise SystemExit(1) from None


def _build_in_processes(kind: str, db_path: Path, report_dir: Path) -> list[str]:
    """Build ``kind`` on ``db_path`` from ``_PROCESSES`` processes at once; return failures."""
    # spawn, not fork: forking a process that already runs threads (pytest,
    # the request threadpool tests) is unsafe and warned about since 3.12.
    context = multiprocessing.get_context("spawn")
    barrier = context.Barrier(_PROCESSES)
    report_dir.mkdir()
    processes = [
        context.Process(
            target=_build_in_child,
            args=(kind, str(db_path), barrier, str(report_dir / f"{index}.err")),
        )
        for index in range(_PROCESSES)
    ]
    for process in processes:
        process.start()
    for process in processes:
        process.join(timeout=_JOIN_TIMEOUT_S)
    failures = [path.read_text(encoding="utf-8") for path in sorted(report_dir.glob("*.err"))]
    for process in processes:
        if process.is_alive():
            process.kill()
            failures.append(f"pid {process.pid} did not finish")
        elif process.exitcode != 0 and not failures:
            failures.append(f"pid {process.pid} exited {process.exitcode}")
    return failures


def _build_in_threads(kind: str, db_path: Path) -> list[BaseException]:
    """Build ``kind`` on ``db_path`` from ``_THREADS`` threads at once; return failures."""
    barrier = threading.Barrier(_THREADS)
    failures: list[BaseException] = []

    def build() -> None:
        try:
            barrier.wait(timeout=30)
            _FACTORIES[kind](db_path)
        except BaseException as error:  # noqa: BLE001 - collected for the assertion
            failures.append(error)

    threads = [threading.Thread(target=build) for _ in range(_THREADS)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=_JOIN_TIMEOUT_S)
    return failures


# ---------------------------------------------------------------------------
# Legacy databases: the table exists without the migrated column
# ---------------------------------------------------------------------------


def _seed(db_path: Path, *statements: str) -> None:
    """Write a legacy schema in WAL mode, the state every earlier build left behind.

    WAL up front keeps the race below about the migration rather than the
    one-off journal-mode switch, which ``enable_wal`` already rides out.
    """
    with closing(sqlite3.connect(db_path)) as conn, conn:
        conn.execute("PRAGMA journal_mode=WAL")
        for statement in statements:
            conn.execute(statement)


def _seed_legacy_alerts(db_path: Path) -> None:
    _seed(
        db_path,
        """
        CREATE TABLE alert_events (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            rule_id INTEGER NOT NULL,
            rule_type TEXT NOT NULL,
            symbol TEXT NOT NULL,
            market TEXT NOT NULL,
            message TEXT NOT NULL,
            observed TEXT NOT NULL,
            triggered_at TEXT NOT NULL,
            acknowledged INTEGER NOT NULL DEFAULT 0,
            acknowledged_at TEXT
        )
        """,
        "INSERT INTO alert_events (rule_id, rule_type, symbol, market, message, observed,"
        " triggered_at) VALUES (1, 'price', '2330', 'TW', 'legacy', '{}', '2026-07-25T06:00:00')",
    )


def _seed_legacy_dividends(db_path: Path) -> None:
    _seed(
        db_path,
        """
        CREATE TABLE dividend_events (
            symbol TEXT NOT NULL,
            market TEXT NOT NULL,
            ex_date TEXT NOT NULL,
            previous_close TEXT,
            reference_price TEXT,
            cash_dividend TEXT NOT NULL,
            rights_value TEXT NOT NULL,
            source TEXT NOT NULL,
            as_of TEXT NOT NULL,
            synced_at TEXT NOT NULL,
            PRIMARY KEY (symbol, market, ex_date)
        )
        """,
        "INSERT INTO dividend_events VALUES ('2330', 'TW', '2026-08-14', '102.00', '99.00',"
        " '3.00', '0', 'twse_openapi_dividend', '2026-08-01', '2026-08-01T00:00:00+00:00')",
    )


def _seed_legacy_playbook(db_path: Path) -> None:
    _seed(
        db_path,
        """
        CREATE TABLE playbook_directives (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            created_at TEXT NOT NULL,
            rules_version INTEGER NOT NULL,
            symbol TEXT NOT NULL,
            batch_no INTEGER,
            action TEXT NOT NULL,
            shares INTEGER NOT NULL,
            rule_id TEXT NOT NULL,
            rule_summary TEXT NOT NULL,
            data_date TEXT NOT NULL,
            execution_date TEXT NOT NULL,
            reference_price TEXT,
            limit_low TEXT,
            limit_high TEXT,
            data_status TEXT NOT NULL,
            source TEXT NOT NULL,
            status TEXT NOT NULL
        )
        """,
        "INSERT INTO playbook_directives (created_at, rules_version, symbol, action, shares,"
        " rule_id, rule_summary, data_date, execution_date, data_status, source, status)"
        " VALUES ('2026-07-25', 1, '2330', 'buy', 1000, 'R1', 'legacy', '2026-07-24',"
        " '2026-07-25', 'ok', 'twse', 'pending')",
    )


_LEGACY_SEEDS: dict[str, tuple[Callable[[Path], None], str]] = {
    "alerts": (_seed_legacy_alerts, "SELECT message FROM alert_events"),
    "dividends": (_seed_legacy_dividends, "SELECT cash_dividend FROM dividend_events"),
    "playbook": (_seed_legacy_playbook, "SELECT rule_summary FROM playbook_directives"),
}

_LEGACY_ROW: dict[str, str] = {"alerts": "legacy", "dividends": "3.00", "playbook": "legacy"}


def _legacy_rows(db_path: Path, kind: str) -> list[str]:
    with closing(sqlite3.connect(db_path)) as conn:
        return [str(row[0]) for row in conn.execute(_LEGACY_SEEDS[kind][1])]


# ---------------------------------------------------------------------------
# Concurrent construction
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("kind", sorted(_FACTORIES))
def test_processes_building_a_store_on_a_fresh_database_all_succeed(
    tmp_path: Path, kind: str
) -> None:
    """The backend and the scheduler are two processes on one file: both must start."""
    db_path = tmp_path / "fresh.db"

    assert _build_in_processes(kind, db_path, tmp_path / "reports") == []

    if kind in _MIGRATED_COLUMN:
        table, column = _MIGRATED_COLUMN[kind]
        assert _columns(db_path, table).count(column) == 1


@pytest.mark.parametrize("kind", sorted(_LEGACY_SEEDS))
def test_processes_migrating_the_same_legacy_database_all_succeed(
    tmp_path: Path, kind: str
) -> None:
    """Every racer must find the column added once and the legacy row untouched."""
    db_path = tmp_path / "legacy.db"
    _LEGACY_SEEDS[kind][0](db_path)

    assert _build_in_processes(kind, db_path, tmp_path / "reports") == []

    table, column = _MIGRATED_COLUMN[kind]
    columns = _columns(db_path, table)
    assert columns.count(column) == 1
    assert len(columns) == len(set(columns))
    assert _legacy_rows(db_path, kind) == [_LEGACY_ROW[kind]]


def test_request_threads_building_the_alert_store_on_a_fresh_database_all_succeed(
    tmp_path: Path,
) -> None:
    """The reported failure: the first page load builds ``AlertStore`` from several threads."""
    db_path = tmp_path / "fresh.db"

    assert _build_in_threads("alerts", db_path) == []

    assert _columns(db_path, "alert_events").count("bar_as_of") == 1


@pytest.mark.parametrize("kind", sorted(_LEGACY_SEEDS))
def test_threads_migrating_the_same_legacy_database_all_succeed(tmp_path: Path, kind: str) -> None:
    db_path = tmp_path / "legacy.db"
    _LEGACY_SEEDS[kind][0](db_path)

    assert _build_in_threads(kind, db_path) == []

    table, column = _MIGRATED_COLUMN[kind]
    assert _columns(db_path, table).count(column) == 1
    assert _legacy_rows(db_path, kind) == [_LEGACY_ROW[kind]]


@pytest.mark.parametrize("kind", sorted(_LEGACY_SEEDS))
def test_a_database_that_already_has_the_column_is_left_alone(tmp_path: Path, kind: str) -> None:
    """Re-opening a migrated file neither takes the write lock nor issues an ``ALTER``."""
    db_path = tmp_path / "legacy.db"
    _LEGACY_SEEDS[kind][0](db_path)
    _FACTORIES[kind](db_path)  # the first open migrates
    table, column = _MIGRATED_COLUMN[kind]
    before = _columns(db_path, table)

    traced: list[str] = []
    real_connect = sqlite3.connect

    def tracing_connect(*args: Any, **kwargs: Any) -> sqlite3.Connection:
        conn: sqlite3.Connection = real_connect(*args, **kwargs)
        conn.set_trace_callback(traced.append)
        return conn

    with pytest.MonkeyPatch.context() as patch:
        patch.setattr(sqlite3, "connect", tracing_connect)
        _FACTORIES[kind](db_path)

    assert _columns(db_path, table) == before
    assert not any("ALTER TABLE" in sql.upper() for sql in traced)
    assert not any("BEGIN IMMEDIATE" in sql.upper() for sql in traced)
    assert _legacy_rows(db_path, kind) == [_LEGACY_ROW[kind]]


# ---------------------------------------------------------------------------
# Sectors: the empty pre-v9 statistics table is dropped once, under the lock
# ---------------------------------------------------------------------------

_LEGACY_STATS_SQL = """
    CREATE TABLE sector_rank_stats (
        run_id TEXT PRIMARY KEY,
        method_version TEXT NOT NULL,
        regime TEXT NOT NULL CHECK (regime = 'pit'),
        data_regime TEXT NOT NULL CHECK (data_regime = 'forward_pit'),
        source_run_ids TEXT NOT NULL,
        computed_at TEXT NOT NULL
    )
"""


def test_processes_opening_an_empty_pre_v9_sector_table_all_succeed(tmp_path: Path) -> None:
    """Two racers must not both drop it: the loser would hit "no such table"."""
    db_path = tmp_path / "legacy.db"
    _seed(db_path, _LEGACY_STATS_SQL)

    assert _build_in_processes("sectors", db_path, tmp_path / "reports") == []

    assert "source_run_ids" not in _columns(db_path, "sector_rank_stats")
    with closing(sqlite3.connect(db_path)) as conn:
        triggers = {
            str(row[0])
            for row in conn.execute("SELECT name FROM sqlite_master WHERE type = 'trigger'")
        }
    assert {"sector_rank_stats_no_update", "sector_rank_stats_no_delete"} <= triggers


def test_threads_opening_a_pre_v9_sector_table_with_rows_never_touch_it(tmp_path: Path) -> None:
    db_path = tmp_path / "legacy.db"
    _seed(
        db_path,
        _LEGACY_STATS_SQL,
        "INSERT INTO sector_rank_stats VALUES ('old', 'v1', 'pit', 'forward_pit', '[]', 'x')",
    )

    assert _build_in_threads("sectors", db_path) == []

    assert "source_run_ids" in _columns(db_path, "sector_rank_stats")
    with closing(sqlite3.connect(db_path)) as conn:
        (count,) = conn.execute("SELECT COUNT(*) FROM sector_rank_stats").fetchone()
    assert count == 1


# ---------------------------------------------------------------------------
# add_missing_columns
# ---------------------------------------------------------------------------


class _StaleFirstPragma:
    """A connection whose first ``PRAGMA table_info`` answers from before a migration.

    What the loser of the race sees: its unlocked check said "missing", and by
    the time it holds the write lock the winner has already added the column.
    Everything else goes to the real connection.
    """

    def __init__(
        self,
        conn: sqlite3.Connection,
        rows: tuple[tuple[object, ...], ...] = ((0, "id", "INTEGER", 0, None, 1),),
    ) -> None:
        self._conn = conn
        self._rows = rows
        self._stale = True
        self.executed: list[str] = []

    def execute(self, sql: str) -> Any:
        self.executed.append(sql)
        if self._stale and sql.upper().startswith("PRAGMA TABLE_INFO"):
            self._stale = False
            return iter(self._rows)
        return self._conn.execute(sql)

    @property
    def in_transaction(self) -> bool:
        return self._conn.in_transaction


@pytest.fixture
def table_db(tmp_path: Path) -> Iterator[Path]:
    db_path = tmp_path / "helper.db"
    _seed(db_path, "CREATE TABLE things (id INTEGER PRIMARY KEY)", "INSERT INTO things VALUES (1)")
    yield db_path


def test_add_missing_columns_adds_every_missing_column_in_order(table_db: Path) -> None:
    with closing(sqlite3.connect(table_db)) as conn:
        add_missing_columns(conn, "things", {"a": "TEXT", "b": "INTEGER NOT NULL DEFAULT 0"})
        assert not conn.in_transaction
    assert _columns(table_db, "things") == ["id", "a", "b"]


def test_add_missing_columns_loser_rechecks_under_the_lock(table_db: Path) -> None:
    with closing(sqlite3.connect(table_db)) as conn:
        add_missing_columns(conn, "things", {"a": "TEXT"})  # the winner
    with closing(sqlite3.connect(table_db)) as conn:
        stale = _StaleFirstPragma(conn)
        add_missing_columns(cast(sqlite3.Connection, stale), "things", {"a": "TEXT"})
        assert not conn.in_transaction

    assert "BEGIN IMMEDIATE" in stale.executed
    assert "COMMIT" in stale.executed
    assert not any(sql.startswith("ALTER") for sql in stale.executed)
    assert _columns(table_db, "things") == ["id", "a"]


def test_add_missing_columns_still_raises_an_unrelated_operational_error(tmp_path: Path) -> None:
    """Only "already migrated" is quiet; a missing table stays loud and leaves no transaction."""
    with closing(sqlite3.connect(tmp_path / "empty.db")) as conn:
        with pytest.raises(sqlite3.OperationalError, match="no such table"):
            add_missing_columns(conn, "things", {"a": "TEXT"})
        assert not conn.in_transaction


def test_add_missing_columns_raises_when_the_write_lock_stays_taken(table_db: Path) -> None:
    """A lock held past ``busy_timeout`` is a failure, never a silently skipped migration."""
    with closing(sqlite3.connect(table_db, isolation_level=None)) as holder:
        holder.execute("BEGIN IMMEDIATE")
        try:
            with closing(sqlite3.connect(table_db, timeout=0.05)) as conn:
                with pytest.raises(sqlite3.OperationalError, match="locked"):
                    add_missing_columns(conn, "things", {"a": "TEXT"})
        finally:
            holder.execute("ROLLBACK")
    assert _columns(table_db, "things") == ["id"]


def test_add_missing_columns_rolls_back_every_column_when_one_fails(table_db: Path) -> None:
    """Several columns are one transaction: a failure part-way adds none of them."""
    with closing(sqlite3.connect(table_db)) as conn:
        with pytest.raises(sqlite3.OperationalError):
            add_missing_columns(conn, "things", {"a": "TEXT", "b": "TEXT NOT NULL"})
        assert not conn.in_transaction
    assert _columns(table_db, "things") == ["id"]


def _sector_triggers(db_path: Path) -> set[str]:
    with closing(sqlite3.connect(db_path)) as conn:
        return {
            str(row[0])
            for row in conn.execute("SELECT name FROM sqlite_master WHERE type = 'trigger'")
        }


def test_the_sector_loser_rechecks_under_the_lock_and_drops_nothing(tmp_path: Path) -> None:
    """Its unlocked check saw the pre-v9 table; the winner has rebuilt it since.

    Without the re-check the loser counted the rebuilt (empty) table and
    dropped it, taking the winner's triggers with it.
    """
    db_path = tmp_path / "legacy.db"
    _seed(db_path, _LEGACY_STATS_SQL)
    ensure_schema(db_path)  # the winner drops and rebuilds it
    triggers = _sector_triggers(db_path)
    legacy_pragma = ((0, "run_id", "TEXT", 0, None, 1), (1, "source_run_ids", "TEXT", 1, None, 0))

    with closing(sqlite3.connect(db_path)) as conn:
        stale = _StaleFirstPragma(conn, legacy_pragma)
        assert _legacy_stats_rows(cast(sqlite3.Connection, stale)) is None
        assert not conn.in_transaction

    assert "BEGIN IMMEDIATE" in stale.executed
    assert not any(sql.startswith(("DROP", "SELECT COUNT")) for sql in stale.executed)
    assert _sector_triggers(db_path) == triggers
    assert "source_run_ids" not in _columns(db_path, "sector_rank_stats")


def test_the_sector_legacy_check_still_raises_an_unrelated_operational_error(
    tmp_path: Path,
) -> None:
    db_path = tmp_path / "legacy.db"
    _seed(db_path, _LEGACY_STATS_SQL)
    with closing(sqlite3.connect(db_path, isolation_level=None)) as holder:
        holder.execute("BEGIN IMMEDIATE")
        try:
            with closing(sqlite3.connect(db_path, timeout=0.05)) as conn:
                with pytest.raises(sqlite3.OperationalError, match="locked"):
                    _legacy_stats_rows(conn)
        finally:
            holder.execute("ROLLBACK")
    assert "source_run_ids" in _columns(db_path, "sector_rank_stats")


def test_a_failure_inside_the_sector_lock_rolls_back_and_is_raised(tmp_path: Path) -> None:
    db_path = tmp_path / "legacy.db"
    _seed(db_path, _LEGACY_STATS_SQL)

    class _FailingCount(_StaleFirstPragma):
        def execute(self, sql: str) -> Any:
            if sql.startswith("SELECT COUNT"):
                raise sqlite3.OperationalError("disk I/O error")
            return self._conn.execute(sql)

    with closing(sqlite3.connect(db_path)) as conn:
        with pytest.raises(sqlite3.OperationalError, match="disk I/O"):
            _legacy_stats_rows(cast(sqlite3.Connection, _FailingCount(conn)))
        assert not conn.in_transaction
    assert "source_run_ids" in _columns(db_path, "sector_rank_stats")

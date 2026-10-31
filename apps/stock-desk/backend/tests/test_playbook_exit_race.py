"""Concurrent EMERGENCY_EXITs write each sell exactly once (ADR-0033 T-1～T-6).

Before N-166 the exit read the batches, loaded prices, then wrote the freeze and
the lines in two separate transactions with no lock, so two submissions at once
-- or simply one after the other -- both wrote a full set of sells. The fix
re-reads under ``BEGIN IMMEDIATE`` (the N-154 pattern, see
``tests/test_schema_migration_race.py``, whose layout these tests follow): many
threads and many processes at once, a loser whose unlocked read was stale, a
lock that stays taken, a failure half-way through the writes, and the order of
every resolver call against the lock.
"""

from __future__ import annotations

import itertools
import json
import multiprocessing
import sqlite3
import threading
from collections.abc import Sequence
from contextlib import closing
from datetime import date
from pathlib import Path
from typing import Any

import pytest

from app.data.interface import Market, ProviderResult
from app.playbook import store as store_module
from app.playbook import wording
from app.playbook.models import Directive, EmergencyExitResult
from app.playbook.service import PlaybookService
from tests.api_helpers import FakePriceService
from tests.exit_idempotency_helpers import (
    TUESDAY,
    WEDNESDAY,
    already_pending_message,
    emergency_rows,
    fakes,
    open_book,
    seed_held_book,
    state_map,
    unsettled_per_batch,
    until_for,
)

#: Same sizes as the N-154 race tests: enough to hit the window, cheap to spawn.
_PROCESSES = 6
_THREADS = 8
_JOIN_TIMEOUT_S = 120

#: What every loser of the race must answer with, verbatim (S1).
_LOSER_MESSAGE = already_pending_message(
    batches=2,
    shares=500,
    execution_dates=WEDNESDAY.isoformat(),
    executed_at=TUESDAY,
    until=until_for(TUESDAY),
)
_HELD_BATCHES = {("2330", 1): 1, ("2454", 1): 1}


def _assert_one_winner(db_path: Path, outcomes: Sequence[tuple[int, str]]) -> None:
    """T-1/T-2 assertions over ``(new line count, message)`` per caller."""
    assert unsettled_per_batch(db_path) == _HELD_BATCHES
    assert state_map(db_path)["emergency_until"] == until_for(TUESDAY).isoformat()
    winners = [outcome for outcome in outcomes if outcome[0]]
    assert len(winners) == 1, outcomes
    assert winners[0][0] == 2
    losers = [outcome for outcome in outcomes if not outcome[0]]
    assert len(losers) == len(outcomes) - 1
    assert {message for _, message in losers} == {_LOSER_MESSAGE}


# --- T-1 threads -------------------------------------------------------------


def _exit_in_threads(services: Sequence[PlaybookService]) -> list[Any]:
    barrier = threading.Barrier(len(services))
    results: list[EmergencyExitResult] = []
    failures: list[BaseException] = []
    lock = threading.Lock()

    def run(service: PlaybookService) -> None:
        try:
            barrier.wait(timeout=30)
            result = service.emergency_exit(today=TUESDAY)
            with lock:
                results.append(result)
        except BaseException as error:  # noqa: BLE001 - collected for the assertion
            failures.append(error)

    threads = [threading.Thread(target=run, args=(service,)) for service in services]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=_JOIN_TIMEOUT_S)
    assert failures == []
    assert not [thread for thread in threads if thread.is_alive()]
    return results


def test_threads_each_with_their_own_store_write_each_sell_once(tmp_path: Path) -> None:
    """T-1: every request thread builds its own store and service on one file."""
    db_path = tmp_path / "playbook.db"
    seed_held_book(db_path)

    results = _exit_in_threads([open_book(db_path).service for _ in range(_THREADS)])

    assert len(results) == _THREADS
    _assert_one_winner(db_path, [(len(item.directives), item.message) for item in results])
    assert all(not item.directives for item in results if item.message == _LOSER_MESSAGE)


def test_threads_sharing_one_service_write_each_sell_once(tmp_path: Path) -> None:
    """T-1 variant: the backend's lru_cache singleton -- one service, many threads."""
    db_path = tmp_path / "playbook.db"
    seed_held_book(db_path)
    service = open_book(db_path).service

    results = _exit_in_threads([service] * _THREADS)

    _assert_one_winner(db_path, [(len(item.directives), item.message) for item in results])


# --- T-2 processes -----------------------------------------------------------


def _exit_in_child(db_path: str, barrier: Any, report: str) -> None:
    """Spawned-process target: wait for every sibling, then submit the exit."""
    try:
        book = open_book(Path(db_path))
        barrier.wait(timeout=60)
        result = book.service.emergency_exit(today=TUESDAY)
        Path(report + ".json").write_text(
            json.dumps([len(result.directives), result.message], ensure_ascii=False),
            encoding="utf-8",
        )
    except BaseException as error:  # noqa: BLE001 - reported to the parent
        Path(report + ".err").write_text(f"{type(error).__name__}: {error}", encoding="utf-8")
        raise SystemExit(1) from None


def test_processes_submitting_at_once_write_each_sell_once(tmp_path: Path) -> None:
    """T-2: the backend and the scheduler (or two backends) are separate processes."""
    db_path = tmp_path / "playbook.db"
    seed_held_book(db_path)
    report_dir = tmp_path / "reports"
    report_dir.mkdir()
    # spawn, not fork: forking a process that already runs threads is unsafe.
    context = multiprocessing.get_context("spawn")
    barrier = context.Barrier(_PROCESSES)
    processes = [
        context.Process(
            target=_exit_in_child, args=(str(db_path), barrier, str(report_dir / str(index)))
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
    assert failures == []

    outcomes = [
        tuple(json.loads(path.read_text(encoding="utf-8")))
        for path in sorted(report_dir.glob("*.json"))
    ]
    assert len(outcomes) == _PROCESSES
    _assert_one_winner(db_path, [(int(count), str(message)) for count, message in outcomes])


# --- T-3 the loser re-reads under the lock -------------------------------------


def _tracing(monkeypatch: pytest.MonkeyPatch, sink: list[Any], tick: Any = None) -> None:
    real_connect = sqlite3.connect

    def tracing_connect(*args: Any, **kwargs: Any) -> sqlite3.Connection:
        conn: sqlite3.Connection = real_connect(*args, **kwargs)
        if tick is None:
            conn.set_trace_callback(sink.append)
        else:
            conn.set_trace_callback(lambda sql: sink.append((next(tick), sql)))
        return conn

    monkeypatch.setattr(sqlite3, "connect", tracing_connect)


def _writes(statements: Sequence[str]) -> list[str]:
    return [
        sql
        for sql in statements
        if sql.lstrip().upper().startswith(("INSERT", "UPDATE", "DELETE", "REPLACE"))
    ]


def test_a_loser_with_a_stale_unlocked_read_rechecks_under_the_lock(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """T-3: its unlocked read predates the winner's write; the lock re-read wins."""
    db_path = tmp_path / "playbook.db"
    seed_held_book(db_path)
    book = open_book(db_path)
    stale = book.store.list_batches()  # read before the winner wrote anything
    book.service.emergency_exit(today=TUESDAY)  # the winner
    rows = emergency_rows(db_path)
    monkeypatch.setattr(book.store, "list_batches", lambda: stale)
    traced: list[str] = []
    _tracing(monkeypatch, traced)

    loser = book.service.emergency_exit(today=TUESDAY)

    assert "BEGIN IMMEDIATE" in traced
    assert "COMMIT" in traced
    assert _writes(traced) == []
    assert emergency_rows(db_path) == rows
    assert loser.directives == []
    assert loser.message == _LOSER_MESSAGE


def test_a_batch_that_only_appears_under_the_lock_is_liquidated_without_a_price(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """C-3: not preloaded -> NOTHING_LOADED ＋ DATA_GAP_NOTE, never a lookup under the lock."""
    db_path = tmp_path / "playbook.db"
    seed_held_book(db_path)
    book = open_book(db_path)
    # The unlocked read saw no held batch at all, so no symbol was loaded.
    monkeypatch.setattr(book.store, "list_batches", lambda: [])

    result = book.service.emergency_exit(today=TUESDAY)

    assert book.prices.calls == []
    assert [(item.symbol, item.reference_price) for item in result.directives] == [
        ("2330", None),
        ("2454", None),
    ]
    assert {item.data_status for item in result.directives} == {"unavailable"}
    assert result.warnings == [
        wording.DATA_GAP_NOTE.format(symbol=symbol, status="unavailable", source="none")
        for symbol in ("2330", "2454")
    ]
    assert unsettled_per_batch(db_path) == _HELD_BATCHES


# --- T-4 a lock that stays taken -----------------------------------------------


def test_an_exit_raises_when_the_write_lock_stays_taken(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """T-4 / C-11: past busy_timeout is a loud failure, never a silently skipped exit."""
    db_path = tmp_path / "playbook.db"
    seed_held_book(db_path)
    book = open_book(db_path)
    before = state_map(db_path)
    monkeypatch.setattr(store_module, "BUSY_TIMEOUT_MS", 50)

    with closing(sqlite3.connect(db_path, isolation_level=None)) as holder:
        holder.execute("BEGIN IMMEDIATE")
        try:
            with pytest.raises(sqlite3.OperationalError, match="locked"):
                book.service.emergency_exit(today=TUESDAY)
        finally:
            holder.execute("ROLLBACK")

    assert emergency_rows(db_path) == []
    assert state_map(db_path) == before
    assert "emergency_until" not in state_map(db_path)


# --- T-5 all or nothing ----------------------------------------------------------


class _TrackedConnection(sqlite3.Connection):
    """Records whether a transaction was still open when the store closed it."""

    closed_in_transaction: list[bool] = []

    def close(self) -> None:
        type(self).closed_in_transaction.append(self.in_transaction)
        super().close()


def test_a_failure_after_the_first_line_rolls_back_the_lines_and_the_freeze(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """T-5: zero lines, ``emergency_until`` unchanged, no open transaction (附錄 C (ii) 消失)."""
    db_path = tmp_path / "playbook.db"
    seed_held_book(db_path)
    book = open_book(db_path)
    book.store.freeze_emergency(until=date(2026, 8, 1))  # an expired freeze the exit would move
    before = state_map(db_path)
    real_insert = store_module._insert_directives

    def insert_one_then_fail(
        conn: sqlite3.Connection, directives: Sequence[Directive], **kwargs: Any
    ) -> None:
        real_insert(conn, list(directives)[:1], **kwargs)
        assert len(conn.execute("SELECT id FROM playbook_directives").fetchall()) == 1
        raise RuntimeError("disk full after the first line")

    _TrackedConnection.closed_in_transaction = []
    monkeypatch.setattr(store_module, "_insert_directives", insert_one_then_fail)
    monkeypatch.setattr(
        book.store,
        "_connect",
        lambda: sqlite3.connect(db_path, timeout=5, factory=_TrackedConnection),
    )

    with pytest.raises(RuntimeError, match="disk full"):
        book.service.emergency_exit(today=TUESDAY)

    assert emergency_rows(db_path) == []
    assert state_map(db_path) == before
    assert _TrackedConnection.closed_in_transaction
    assert not any(_TrackedConnection.closed_in_transaction)

    # The lock is free again and the next exit goes through whole.
    monkeypatch.undo()
    retried = book.service.emergency_exit(today=TUESDAY)
    assert len(retried.directives) == 2
    assert retried.attribution == wording.EXIT_ATTRIBUTION


# --- T-6 no I/O under the lock ---------------------------------------------------


class _RecordingPrices(FakePriceService):
    """A fake ladder that stamps every resolver call with a shared tick."""

    def __init__(self, source: FakePriceService, tick: Any, sink: list[Any]) -> None:
        super().__init__(source.bars)
        self._tick = tick
        self._sink = sink

    def get_daily_bars(self, symbol: str, market: Market, start: date, end: date) -> ProviderResult:
        self._sink.append((next(self._tick), f"load {symbol}"))
        return super().get_daily_bars(symbol, market, start, end)

    def get_cached_bars(
        self, symbol: str, market: Market, start: date, end: date
    ) -> ProviderResult:
        self._sink.append((next(self._tick), f"load-cached {symbol}"))
        return super().get_cached_bars(symbol, market, start, end)


def test_every_load_happens_before_the_lock_is_taken(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """T-6 / C-3: resolver calls and SQL on one clock; no load after BEGIN IMMEDIATE."""
    db_path = tmp_path / "playbook.db"
    seed_held_book(db_path)
    tick = itertools.count()
    events: list[tuple[int, str]] = []
    prices, index = fakes()
    book = open_book(
        db_path,
        prices=_RecordingPrices(prices, tick, events),
        index=_RecordingPrices(index, tick, events),
    )
    _tracing(monkeypatch, events, tick)

    result = book.service.emergency_exit(today=TUESDAY)

    assert len(result.directives) == 2
    ordered = sorted(events)
    begins = [at for at, what in ordered if what == "BEGIN IMMEDIATE"]
    commits = [at for at, what in ordered if what == "COMMIT"]
    loads = [at for at, what in ordered if what.startswith("load")]
    assert len(begins) == 1 and len(commits) == 1
    assert {what for _, what in ordered if what.startswith("load")} == {
        "load 2330",
        "load 2454",
        "load ^TWII",
    }
    assert loads and max(loads) < begins[0] < commits[0]


# --- C-11 edges (qa NB-R4) -------------------------------------------------------


def _failing_exit(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, failure: Any
) -> tuple[Path, dict[str, str], Any]:
    """A held book whose transaction runs ``failure(conn)`` after the first line."""
    db_path = tmp_path / "playbook.db"
    seed_held_book(db_path)
    book = open_book(db_path)
    book.store.freeze_emergency(until=date(2026, 8, 1))  # the exit would move it
    before = state_map(db_path)
    real_insert = store_module._insert_directives

    def insert_one_then(
        conn: sqlite3.Connection, directives: Sequence[Directive], **kwargs: Any
    ) -> None:
        real_insert(conn, list(directives)[:1], **kwargs)
        failure(conn)

    _TrackedConnection.closed_in_transaction = []
    monkeypatch.setattr(store_module, "_insert_directives", insert_one_then)
    monkeypatch.setattr(
        book.store,
        "_connect",
        lambda: sqlite3.connect(db_path, timeout=5, factory=_TrackedConnection),
    )
    return db_path, before, book


def test_an_error_after_sqlite_rolled_back_on_its_own_is_raised_unchanged(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """C-11 ``in_transaction is False`` branch: no second ROLLBACK to mask the error.

    SQLite ends the transaction itself on some errors (a full disk, say). A
    second ROLLBACK would fail with "no transaction is active" and replace the
    real error; the guard skips it, so the original is what the caller sees.
    """

    def sqlite_gave_up(conn: sqlite3.Connection) -> None:
        conn.execute("ROLLBACK")  # what SQLite does on its own for such errors
        assert not conn.in_transaction
        raise sqlite3.OperationalError("database or disk is full")

    db_path, before, book = _failing_exit(tmp_path, monkeypatch, sqlite_gave_up)

    with pytest.raises(sqlite3.OperationalError, match="disk is full"):
        book.service.emergency_exit(today=TUESDAY)

    assert emergency_rows(db_path) == []
    assert state_map(db_path) == before
    assert _TrackedConnection.closed_in_transaction
    assert not any(_TrackedConnection.closed_in_transaction)


def test_a_base_exception_mid_transaction_rolls_back_and_propagates(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """C-11 catches ``BaseException``: an interrupt half-way leaves nothing written."""

    def interrupted(conn: sqlite3.Connection) -> None:
        raise KeyboardInterrupt

    db_path, before, book = _failing_exit(tmp_path, monkeypatch, interrupted)

    with pytest.raises(KeyboardInterrupt):
        book.service.emergency_exit(today=TUESDAY)

    assert emergency_rows(db_path) == []
    assert state_map(db_path) == before
    assert _TrackedConnection.closed_in_transaction
    assert not any(_TrackedConnection.closed_in_transaction)

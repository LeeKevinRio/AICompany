"""Concurrent evaluations of one 預定執行日 log each decision exactly once (N172-T10～T14).

ADR-0035 Decision 3 / N172-C1: K1 and K2 are re-read, and only new lines are
written with their schedule rows and bound effects, inside one ``BEGIN
IMMEDIATE``. Laid out like ``tests/test_playbook_exit_race.py`` (ADR-0033
T-1～T-6): many threads and many processes at once, a caller whose unlocked
read was stale, a lock that stays taken, a failure half-way through the
writes, and the order of every resolver call against the lock.
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
from app.playbook.models import Directive, PlaybookEvaluation
from app.playbook.service import PlaybookService
from tests.api_helpers import FakePriceService
from tests.same_day_helpers import TUESDAY, WEDNESDAY, bars, log_rows, open_desk, schedule_rows

_PROCESSES = 6
_THREADS = 8
_JOIN_TIMEOUT_S = 120

#: The one line, and the one schedule row, a 排程日 with one symbol produces.
_ONE_ROW = [("2330", 1, "R1", "buy", WEDNESDAY.isoformat(), 0, "pending")]
_ONE_SCHEDULE = [("2330", 1, WEDNESDAY.isoformat(), 0, "R1")]


def _chase_desk(db_path: Path) -> None:
    """An R2 day: the race is also over ``defer_count`` (V2)."""
    desk = open_desk(db_path)
    desk.prices.seed("2330", bars("2330", 100.0, {TUESDAY: 110.0}))


def _assert_once(db_path: Path, outcomes: Sequence[list[tuple[str, int | None]]]) -> None:
    """Exactly one row in the log; every caller lists that one line."""
    assert log_rows(db_path) == _ONE_ROW
    assert schedule_rows(db_path) == _ONE_SCHEDULE
    assert all(outcome == [("R1", 1)] for outcome in outcomes), outcomes


def _listed(evaluation: PlaybookEvaluation) -> list[tuple[str, int | None]]:
    return [(line.rule_id, line.batch_no) for line in evaluation.directives]


# --- T10 threads ---------------------------------------------------------------------


def _evaluate_in_threads(services: Sequence[PlaybookService]) -> list[PlaybookEvaluation]:
    barrier = threading.Barrier(len(services))
    results: list[PlaybookEvaluation] = []
    failures: list[BaseException] = []
    lock = threading.Lock()

    def run(service: PlaybookService) -> None:
        try:
            barrier.wait(timeout=30)
            result = service.evaluate_today(today=TUESDAY)
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


def test_threads_each_with_their_own_store_log_the_buy_once(tmp_path: Path) -> None:
    """T10: every request thread builds its own store and service on one file."""
    db_path = tmp_path / "playbook.db"
    open_desk(db_path)

    results = _evaluate_in_threads(
        [open_desk(db_path, seed=False).service for _ in range(_THREADS)]
    )

    assert len(results) == _THREADS
    _assert_once(db_path, [_listed(item) for item in results])


def test_threads_sharing_one_service_count_one_deferral(tmp_path: Path) -> None:
    """T10 variant: one service (the lru_cache singleton), many threads, an R2 day."""
    db_path = tmp_path / "playbook.db"
    desk = open_desk(db_path)
    desk.prices.seed("2330", bars("2330", 100.0, {TUESDAY: 110.0}))

    results = _evaluate_in_threads([desk.service] * _THREADS)

    assert {tuple(_listed(item)) for item in results} == {(("R2", 1),)}
    assert [row[2:4] for row in log_rows(db_path)] == [("R2", "defer")]
    batch = desk.store.get_batch("2330", 1)
    assert batch is not None and (batch.defer_count, batch.status) == (1, "planned")


# --- T10 processes -------------------------------------------------------------------


def _evaluate_in_child(db_path: str, barrier: Any, report: str) -> None:
    """Spawned-process target: wait for every sibling, then evaluate the 排程日."""
    try:
        desk = open_desk(Path(db_path), seed=False)
        barrier.wait(timeout=60)
        result = desk.service.evaluate_today(today=TUESDAY)
        Path(report + ".json").write_text(json.dumps(_listed(result)), encoding="utf-8")
    except BaseException as error:  # noqa: BLE001 - reported to the parent
        Path(report + ".err").write_text(f"{type(error).__name__}: {error}", encoding="utf-8")
        raise SystemExit(1) from None


def test_processes_evaluating_at_once_log_the_buy_once(tmp_path: Path) -> None:
    """T10: the backend and the scheduler (or two backends) are separate processes."""
    db_path = tmp_path / "playbook.db"
    open_desk(db_path)
    report_dir = tmp_path / "reports"
    report_dir.mkdir()
    # spawn, not fork: forking a process that already runs threads is unsafe.
    context = multiprocessing.get_context("spawn")
    barrier = context.Barrier(_PROCESSES)
    processes = [
        context.Process(
            target=_evaluate_in_child,
            args=(str(db_path), barrier, str(report_dir / str(index))),
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
        [(str(rule), int(batch)) for rule, batch in json.loads(path.read_text(encoding="utf-8"))]
        for path in sorted(report_dir.glob("*.json"))
    ]
    assert len(outcomes) == _PROCESSES
    _assert_once(db_path, [[(rule, batch) for rule, batch in item] for item in outcomes])


# --- T11 a stale unlocked read ---------------------------------------------------------


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


def _writes_inside(statements: Sequence[str]) -> list[str]:
    """Writes between ``BEGIN IMMEDIATE`` and ``COMMIT``."""
    begin = statements.index("BEGIN IMMEDIATE")
    end = statements.index("COMMIT", begin)
    return [
        sql
        for sql in statements[begin:end]
        if sql.lstrip().upper().startswith(("INSERT", "UPDATE", "DELETE", "REPLACE"))
    ]


def test_a_caller_with_a_stale_unlocked_read_rechecks_under_the_lock(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """T11: its batches predate the winner's write (an R2 day); the lock re-read wins."""
    db_path = tmp_path / "playbook.db"
    _chase_desk(db_path)
    desk = open_desk(db_path, seed=False)
    desk.prices.seed("2330", bars("2330", 100.0, {TUESDAY: 110.0}))
    stale = desk.store.list_batches()  # read before the winner wrote anything
    desk.service.evaluate_today(today=TUESDAY)  # the winner
    rows = log_rows(db_path)
    monkeypatch.setattr(desk.store, "list_batches", lambda: stale)
    traced: list[str] = []
    _tracing(monkeypatch, traced)

    loser = desk.service.evaluate_today(today=TUESDAY)

    assert "BEGIN IMMEDIATE" in traced and "COMMIT" in traced
    assert _writes_inside(traced) == []
    assert log_rows(db_path) == rows
    assert _listed(loser) == [("R2", 1)]
    batch = desk.store.get_batch("2330", 1)
    assert batch is not None and batch.defer_count == 1


# --- T12 a lock that stays taken -------------------------------------------------------


def test_an_evaluation_raises_when_the_write_lock_stays_taken(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """T12 / C-11: past busy_timeout is a loud failure, never a silently skipped write."""
    db_path = tmp_path / "playbook.db"
    desk = open_desk(db_path)
    monkeypatch.setattr(store_module, "BUSY_TIMEOUT_MS", 50)
    real_commit = desk.store.commit_evaluation

    def locked_commit(evaluation: PlaybookEvaluation) -> Any:
        with closing(sqlite3.connect(db_path, isolation_level=None)) as holder:
            holder.execute("BEGIN IMMEDIATE")
            try:
                return real_commit(evaluation)
            finally:
                holder.execute("ROLLBACK")

    monkeypatch.setattr(desk.store, "commit_evaluation", locked_commit)

    with pytest.raises(sqlite3.OperationalError, match="locked"):
        desk.service.evaluate_today(today=TUESDAY)

    assert log_rows(db_path) == []
    assert schedule_rows(db_path) == []


# --- T13 all or nothing -----------------------------------------------------------------


class _TrackedConnection(sqlite3.Connection):
    """Records whether a transaction was still open when the store closed it."""

    closed_in_transaction: list[bool] = []

    def close(self) -> None:
        type(self).closed_in_transaction.append(self.in_transaction)
        super().close()


def test_a_failure_after_the_first_line_rolls_back_lines_schedule_and_deferral(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """T13: zero lines, zero schedule rows, ``defer_count`` unchanged, no open transaction."""
    db_path = tmp_path / "playbook.db"
    _chase_desk(db_path)
    desk = open_desk(db_path, seed=False)
    desk.prices.seed("2330", bars("2330", 100.0, {TUESDAY: 110.0}))
    real_insert = store_module._insert_directives

    def insert_then_fail(
        conn: sqlite3.Connection, directives: Sequence[Directive], **kwargs: Any
    ) -> None:
        real_insert(conn, list(directives)[:1], **kwargs)
        assert len(conn.execute("SELECT id FROM playbook_directives").fetchall()) == 1
        defer = conn.execute("SELECT defer_count FROM playbook_batches WHERE batch_no = 1")
        assert defer.fetchone() == (1,)  # the bound effect was already applied
        raise RuntimeError("disk full after the first line")

    _TrackedConnection.closed_in_transaction = []
    monkeypatch.setattr(store_module, "_insert_directives", insert_then_fail)
    real_connect = desk.store._connect
    monkeypatch.setattr(
        desk.store,
        "_connect",
        lambda: sqlite3.connect(db_path, timeout=5, factory=_TrackedConnection),
    )

    with pytest.raises(RuntimeError, match="disk full"):
        desk.service.evaluate_today(today=TUESDAY)

    assert log_rows(db_path) == []
    assert schedule_rows(db_path) == []
    batch = desk.store.get_batch("2330", 1)
    assert batch is not None and (batch.defer_count, batch.status) == (0, "planned")
    assert _TrackedConnection.closed_in_transaction
    assert not any(_TrackedConnection.closed_in_transaction)

    # The lock is free again and the next call goes through whole.
    monkeypatch.setattr(store_module, "_insert_directives", real_insert)
    monkeypatch.setattr(desk.store, "_connect", real_connect)
    retried = desk.service.evaluate_today(today=TUESDAY)
    assert _listed(retried) == [("R2", 1)]
    batch = desk.store.get_batch("2330", 1)
    assert batch is not None and batch.defer_count == 1


def test_an_error_after_sqlite_rolled_back_on_its_own_is_raised_unchanged(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """C-11 ``in_transaction is False`` branch: no second ROLLBACK masks the error."""
    db_path = tmp_path / "playbook.db"
    desk = open_desk(db_path)

    def sqlite_gave_up(conn: sqlite3.Connection, *args: Any, **kwargs: Any) -> None:
        conn.execute("ROLLBACK")  # what SQLite does on its own for such errors
        raise sqlite3.OperationalError("database or disk is full")

    monkeypatch.setattr(store_module, "_insert_schedule", sqlite_gave_up)

    with pytest.raises(sqlite3.OperationalError, match="disk is full"):
        desk.service.evaluate_today(today=TUESDAY)

    assert log_rows(db_path) == []


def test_a_base_exception_mid_transaction_rolls_back_and_propagates(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """C-11 catches ``BaseException``: an interrupt half-way leaves nothing written."""
    db_path = tmp_path / "playbook.db"
    desk = open_desk(db_path)

    def interrupted(conn: sqlite3.Connection, *args: Any, **kwargs: Any) -> None:
        raise KeyboardInterrupt

    monkeypatch.setattr(store_module, "_insert_schedule", interrupted)

    with pytest.raises(KeyboardInterrupt):
        desk.service.evaluate_today(today=TUESDAY)

    assert log_rows(db_path) == []


# --- T14 no I/O under the lock ------------------------------------------------------------


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


def test_every_load_happens_outside_the_evaluation_lock(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """T14 / C2: resolver calls and SQL on one clock; none between BEGIN and COMMIT."""
    db_path = tmp_path / "playbook.db"
    desk = open_desk(db_path)
    tick = itertools.count()
    events: list[tuple[int, str]] = []
    desk.service._markets = {"TW": _RecordingPrices(desk.prices, tick, events)}
    recording_index = _RecordingPrices(desk.index, tick, events)
    desk.service._indices = {"TW": recording_index, "US": recording_index}
    _tracing(monkeypatch, events, tick)

    evaluation = desk.service.evaluate_today(today=TUESDAY)

    assert _listed(evaluation) == [("R1", 1)]
    ordered = sorted(events)
    (begin,) = [at for at, what in ordered if what == "BEGIN IMMEDIATE"]
    # Other writers (effects, the fast-market state) commit on their own too.
    commit = min(at for at, what in ordered if what == "COMMIT" and at > begin)
    loads = [at for at, what in ordered if what.startswith("load")]
    assert loads
    assert not [at for at in loads if begin < at < commit]
    assert max(loads) < begin  # settlement and evaluation load first, then lock

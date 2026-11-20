"""The check before the recorder and the catch-up window (ADR-0030 supplement 10 points 2, 3).

Point 2 (S-20a, scheduler):

* a successful refresh whose newest bar B is stamped at or after t0 calls the
  recorder once, with the very resolver object the refresh was given;
* the refresh raises, ``ok`` is false, there is no B, or ``B.as_of < t0``: the
  recorder is not called, the matching fixed line is logged, no ``forecast_run``
  row is written;
* each line is the fixed string only -- ``getMessage()`` equal to the constant,
  no ``args``, no ``exc_info``, no exception text anywhere in the log
  (risk-compliance RC-267 (a));
* B dated before ``latest_completed_session(t0)``: the recorder is called and
  the third line logged; that rule is used for the log line only;
* ``KeyboardInterrupt`` is not swallowed;
* ``lookback_days`` is the recorder's two constants summed, ``market`` is
  ``recorder.MARKET``; the target check comes first.

Point 3: start-up plus three minutes on a weekday in [13:30, 22:10) Taipei
time sets no catch-up run, and ``add_job`` is then called without
``next_run_time`` (``None`` would add the job paused).

Every database is a ``tmp_path`` file and nothing reaches the network.
"""

from __future__ import annotations

import ast
import logging
import sqlite3
from collections.abc import Callable, Mapping
from contextlib import closing
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

import pytest
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.schedulers.blocking import BlockingScheduler

from app import scheduler as scheduler_module
from app.data.freshness import TW_POLICY
from app.data.service import LiveRefreshOutcome
from app.forecast import recorder as recorder_module
from app.forecast.recorder import RunResult
from app.forecast.schema import create_schema
from app.services.index import ForcedBenchmarkRefresh
from app.settings.store import SettingsStore
from tests.force_refresh_helpers import index_bar
from tests.import_graph import APP_ROOT

TAIPEI = ZoneInfo("Asia/Taipei")
#: t0 of most runs: Wednesday 2026-11-18 22:10 Taipei.
T0 = datetime(2026, 11, 18, 22, 10, tzinfo=TAIPEI).astimezone(UTC)
T = date(2026, 11, 18)
#: An exception message that must never reach the log (RC-267 (a)).
SECRET = r"C:\Users\someone\stock-desk\data\stock-desk.db close=17123.45 on 2026-11-18"
LINES = (
    scheduler_module.FORECAST_RECORD_REFRESH_FAILED,
    scheduler_module.FORECAST_RECORD_BAR_PREDATES_RUN,
    scheduler_module.FORECAST_RECORD_SERIES_ENDS_EARLY,
)


@pytest.fixture
def target(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """``<tmp>/data/stock-desk.db`` with the ledger schema, as the production target."""
    monkeypatch.delenv("STOCK_DESK_DB_PATH", raising=False)
    monkeypatch.chdir(tmp_path)
    (tmp_path / "data").mkdir()
    db = (tmp_path / "data" / "stock-desk.db").resolve()
    with closing(sqlite3.connect(db, isolation_level=None)) as conn:
        create_schema(conn)  # test only: in production only bootstrap creates it
    monkeypatch.setattr(scheduler_module, "production_db_target", lambda: db)
    monkeypatch.setattr(scheduler_module, "_utc_now", lambda: T0)
    return db


class _Flow:
    """Records the order of the job's steps and what each step was given."""

    def __init__(self, monkeypatch: pytest.MonkeyPatch) -> None:
        self.events: list[str] = []
        self.resolver = object()
        self.refreshed: list[tuple[Any, Mapping[str, Any]]] = []
        self.recorded: list[tuple[Any, Mapping[str, Any]]] = []
        self.answer: Callable[[], ForcedBenchmarkRefresh] = lambda: _refresh(T0, T)
        real_record = recorder_module.record_forecasts

        def resolver() -> object:
            self.events.append("resolver")
            return self.resolver

        def refresh(resolver: Any, **kwargs: Any) -> ForcedBenchmarkRefresh:
            self.events.append("refresh")
            self.refreshed.append((resolver, kwargs))
            return self.answer()

        def record(store: Any, **kwargs: Any) -> RunResult:
            self.events.append("record")
            self.recorded.append((store, kwargs))
            return real_record(store, **kwargs)  # the real recorder: gate_closed, one run row

        monkeypatch.setattr(scheduler_module, "get_index_resolver", resolver)
        monkeypatch.setattr(scheduler_module, "force_refresh_benchmark", refresh)
        monkeypatch.setattr(scheduler_module, "record_forecasts", record)


def _refresh(as_of: datetime, day: date, *, ok: bool = True) -> ForcedBenchmarkRefresh:
    bar = index_bar(day, as_of=as_of)
    live = LiveRefreshOutcome(
        ok=ok,
        source="yfinance" if ok else None,
        requested_at=as_of if ok else None,
        written_at=as_of if ok else None,
        live_bar_count=1 if ok else 0,
        live_latest_date=day if ok else None,
        complete=ok,
        reason=None if ok else "source down",
    )
    return ForcedBenchmarkRefresh(live=live, latest_cached_bar=bar if ok else None, reason=None)


def _no_bar() -> ForcedBenchmarkRefresh:
    live = _refresh(T0, T).live
    return ForcedBenchmarkRefresh(live=live, latest_cached_bar=None, reason="empty")


def _raises() -> ForcedBenchmarkRefresh:
    raise RuntimeError(SECRET)


def _runs(db: Path) -> int:
    with closing(sqlite3.connect(db)) as conn:
        return int(conn.execute("SELECT count(*) FROM forecast_run").fetchone()[0])


def _scheduler_records(caplog: pytest.LogCaptureFixture) -> list[logging.LogRecord]:
    return [record for record in caplog.records if record.name == "scheduler"]


# --- the check holds ----------------------------------------------------------------------------


def test_a_fresh_newest_bar_calls_the_recorder_once_with_the_same_resolver(
    target: Path, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    flow = _Flow(monkeypatch)
    with caplog.at_level(logging.INFO, logger="scheduler"):
        result = scheduler_module.run_forecast_record()
    assert result is not None and result.outcome == "gate_closed"  # empty registry
    assert flow.events == ["resolver", "refresh", "record"]
    ((refreshed_with, _),) = flow.refreshed
    ((_, recorded_kwargs),) = flow.recorded
    assert refreshed_with is flow.resolver
    assert recorded_kwargs["resolver"] is flow.resolver
    assert _runs(target) == 1
    assert not {r.getMessage() for r in _scheduler_records(caplog)} & set(LINES)


def test_a_bar_stamped_exactly_at_t0_passes(target: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    flow = _Flow(monkeypatch)
    flow.answer = lambda: _refresh(T0, T)
    assert scheduler_module.run_forecast_record() is not None
    assert len(flow.recorded) == 1


def test_the_arguments_come_from_the_recorder_module(
    target: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    flow = _Flow(monkeypatch)
    scheduler_module.run_forecast_record()
    ((_, kwargs),) = flow.refreshed
    assert kwargs == {
        "market": recorder_module.MARKET,
        "lookback_days": recorder_module.FETCH_CALENDAR_DAYS + recorder_module.FETCH_SLACK_DAYS,
    }
    assert kwargs["lookback_days"] == 531 and kwargs["market"] == "TW"


def test_a_refused_target_asks_nothing(target: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    flow = _Flow(monkeypatch)
    monkeypatch.setenv("STOCK_DESK_DB_PATH", str(target))
    assert scheduler_module.run_forecast_record() is None
    assert flow.events == []


# --- the check fails ----------------------------------------------------------------------------


FAILURES: dict[str, tuple[Callable[[], ForcedBenchmarkRefresh], str]] = {
    "refresh-raises": (_raises, scheduler_module.FORECAST_RECORD_REFRESH_FAILED),
    "not-ok": (lambda: _refresh(T0, T, ok=False), scheduler_module.FORECAST_RECORD_REFRESH_FAILED),
    "no-newest-bar": (_no_bar, scheduler_module.FORECAST_RECORD_REFRESH_FAILED),
    "bar-before-t0": (
        lambda: _refresh(T0 - timedelta(microseconds=1), T),
        scheduler_module.FORECAST_RECORD_BAR_PREDATES_RUN,
    ),
}


@pytest.mark.parametrize("case", list(FAILURES))
def test_a_failed_check_skips_the_run_with_one_fixed_line(
    target: Path,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
    case: str,
) -> None:
    answer, line = FAILURES[case]
    flow = _Flow(monkeypatch)
    flow.answer = answer
    with caplog.at_level(logging.DEBUG):
        assert scheduler_module.run_forecast_record() is None
    assert flow.events == ["resolver", "refresh"]  # the recorder is not called
    assert _runs(target) == 0  # no forecast_run row
    (record,) = _scheduler_records(caplog)
    # RC-267 (a): the fixed string only.
    assert record.levelno == logging.WARNING
    assert record.getMessage() == line
    assert record.msg == line
    assert record.args == ()
    assert record.exc_info is None and record.exc_text is None and record.stack_info is None
    assert SECRET not in caplog.text and "RuntimeError" not in caplog.text
    assert "17123" not in caplog.text and "2026-11-18" not in caplog.text


def test_the_raising_case_passes_through_the_guard_without_a_traceback(
    target: Path,
    settings_store: SettingsStore,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    flow = _Flow(monkeypatch)
    flow.answer = _raises
    job = scheduler_module.build_scheduler(BlockingScheduler(timezone="UTC")).get_job(
        "forecast_record"
    )
    with caplog.at_level(logging.DEBUG):
        job.func()
    messages = [r.getMessage() for r in _scheduler_records(caplog)]
    assert scheduler_module.FORECAST_RECORD_REFRESH_FAILED in messages
    assert all(r.exc_info is None for r in _scheduler_records(caplog))
    assert SECRET not in caplog.text and "Traceback" not in caplog.text


@pytest.mark.parametrize("error", [KeyboardInterrupt, SystemExit])
def test_a_base_exception_is_not_caught(
    target: Path, monkeypatch: pytest.MonkeyPatch, error: type[BaseException]
) -> None:
    flow = _Flow(monkeypatch)

    def interrupted() -> ForcedBenchmarkRefresh:
        raise error

    flow.answer = interrupted
    with pytest.raises(error):
        scheduler_module.run_forecast_record()
    assert "record" not in flow.events and _runs(target) == 0


def test_a_keyboard_interrupt_passes_through_the_guarded_job(
    target: Path, settings_store: SettingsStore, monkeypatch: pytest.MonkeyPatch
) -> None:
    flow = _Flow(monkeypatch)

    def interrupted() -> ForcedBenchmarkRefresh:
        raise KeyboardInterrupt

    flow.answer = interrupted
    job = scheduler_module.build_scheduler(BlockingScheduler(timezone="UTC")).get_job(
        "forecast_record"
    )
    with pytest.raises(KeyboardInterrupt):
        job.func()


# --- the series ends before the latest weekday session ------------------------------------------


def test_an_early_newest_bar_still_calls_the_recorder_and_logs_the_third_line(
    target: Path, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    flow = _Flow(monkeypatch)
    t_minus_1 = T - timedelta(days=1)
    assert t_minus_1 < TW_POLICY.latest_completed_session(T0) == T
    flow.answer = lambda: _refresh(T0 + timedelta(seconds=1), t_minus_1)
    with caplog.at_level(logging.INFO, logger="scheduler"):
        result = scheduler_module.run_forecast_record()
    assert result is not None and len(flow.recorded) == 1 and _runs(target) == 1
    warnings = [r for r in _scheduler_records(caplog) if r.levelno == logging.WARNING]
    (record,) = warnings
    assert record.getMessage() == scheduler_module.FORECAST_RECORD_SERIES_ENDS_EARLY
    assert record.args == () and record.exc_info is None


def test_a_newest_bar_of_the_latest_session_logs_no_warning(
    target: Path, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    _Flow(monkeypatch)
    with caplog.at_level(logging.WARNING, logger="scheduler"):
        scheduler_module.run_forecast_record()
    assert _scheduler_records(caplog) == []


# --- the three lines and how they are logged (static) -------------------------------------------


def test_the_three_lines_are_the_approved_text() -> None:
    assert LINES == (
        "forecast_record: the live index refresh did not succeed; the run is skipped"
        " and the cache is not used",
        "forecast_record: the newest cached index bar predates this run's start;"
        " the run is skipped",
        "forecast_record: the refreshed index series ends before the latest weekday session"
        " (an exchange holiday or a row missing at the source); the run continues",
    )
    for line in LINES:
        assert line.isascii() and "%" not in line and "{" not in line
        assert "/" not in line and "\\" not in line
        assert not any(character.isdigit() for character in line)
    assert not set(LINES) & set(scheduler_module.FORECAST_RECORD_REFUSALS.values())


def _job_function() -> ast.FunctionDef:
    tree = ast.parse((APP_ROOT / "scheduler.py").read_text(encoding="utf-8"))
    return next(
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.FunctionDef) and node.name == "run_forecast_record"
    )


def _log_violations(function: ast.FunctionDef) -> list[str]:
    """Every WARNING call in the job passes one bare name and nothing else (RC-267 (a))."""
    found: list[str] = []
    for node in ast.walk(function):
        if (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and node.func.attr in ("warning", "exception", "error")
        ):
            argument = node.args[0] if len(node.args) == 1 else None
            fixed = isinstance(argument, ast.Name) or (
                isinstance(argument, ast.Subscript)
                and isinstance(argument.value, ast.Name)
                and argument.value.id == "FORECAST_RECORD_REFUSALS"
            )
            if node.func.attr != "warning" or not fixed or node.keywords:
                found.append(ast.unparse(node))
    return found


def test_the_job_logs_each_warning_as_a_bare_constant() -> None:
    function = _job_function()
    assert _log_violations(function) == []
    named = {
        node.args[0].id
        for node in ast.walk(function)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr == "warning"
        and isinstance(node.args[0], ast.Name)
    }
    assert named == {
        "FORECAST_RECORD_REFRESH_FAILED",
        "FORECAST_RECORD_BAR_PREDATES_RUN",
        "FORECAST_RECORD_SERIES_ENDS_EARLY",
    }


def test_the_log_scan_has_teeth() -> None:
    for source in (
        "def run_forecast_record():\n    logger.warning(LINE, exc_info=True)\n",
        "def run_forecast_record():\n    logger.warning('%s', error)\n",
        "def run_forecast_record():\n    logger.warning(LINE + str(error))\n",
        "def run_forecast_record():\n    logger.exception(LINE)\n",
        "def run_forecast_record():\n    logger.warning(LINE, extra={'e': error})\n",
    ):
        function = ast.parse(source).body[0]
        assert isinstance(function, ast.FunctionDef)
        assert _log_violations(function) != []


def test_the_weekday_rule_only_guards_the_third_line() -> None:
    function = _job_function()
    guards = [
        node
        for node in ast.walk(function)
        if isinstance(node, ast.If) and "latest_completed_session" in ast.unparse(node.test)
    ]
    (guard,) = guards
    assert guard.orelse == []
    (statement,) = guard.body
    assert ast.unparse(statement) == "logger.warning(FORECAST_RECORD_SERIES_ENDS_EARLY)"
    tree = ast.parse((APP_ROOT / "scheduler.py").read_text(encoding="utf-8"))
    uses = [
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.Attribute) and node.attr == "latest_completed_session"
    ]
    assert len(uses) == 1  # the one guard above, nowhere else in the scheduler


# --- point 3: the catch-up window ---------------------------------------------------------------


@pytest.fixture
def settings_store(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> SettingsStore:
    store = SettingsStore(db_path=tmp_path / "settings.db")
    monkeypatch.setattr(scheduler_module, "get_settings_store", lambda: store)
    return store


class _RecordingEngine(BlockingScheduler):  # type: ignore[misc]
    """Keeps the keyword arguments each ``add_job`` call was given."""

    def __init__(self) -> None:
        super().__init__(timezone="UTC")
        self.calls: dict[str, dict[str, Any]] = {}

    def add_job(self, func: Any, *args: Any, **kwargs: Any) -> Any:
        self.calls[str(kwargs.get("id"))] = dict(kwargs)
        return super().add_job(func, *args, **kwargs)


def _taipei(day: date, hour: int, minute: int) -> datetime:
    return datetime(day.year, day.month, day.day, hour, minute, tzinfo=TAIPEI).astimezone(UTC)


FRIDAY = date(2026, 11, 20)
SATURDAY = date(2026, 11, 21)


@pytest.mark.parametrize(
    ("started", "catch_up"),
    [
        pytest.param(_taipei(FRIDAY, 13, 27), False, id="13:27"),
        pytest.param(_taipei(FRIDAY, 13, 30), False, id="13:30"),
        pytest.param(_taipei(FRIDAY, 22, 6), False, id="22:06"),
        pytest.param(_taipei(FRIDAY, 13, 26), True, id="13:26"),
        pytest.param(_taipei(FRIDAY, 22, 7), True, id="22:07"),
        pytest.param(_taipei(FRIDAY, 22, 10), True, id="22:10"),
        pytest.param(_taipei(SATURDAY, 16, 0), True, id="saturday-16:00"),
    ],
)
def test_the_catch_up_run_follows_start_up_plus_three_minutes(
    settings_store: SettingsStore,
    monkeypatch: pytest.MonkeyPatch,
    started: datetime,
    catch_up: bool,
) -> None:
    monkeypatch.setattr(scheduler_module, "_utc_now", lambda: started)
    engine = _RecordingEngine()
    scheduler_module.build_scheduler(engine)
    kwargs = engine.calls["forecast_record"]
    if catch_up:
        assert kwargs["next_run_time"] == started + timedelta(minutes=3)
        assert scheduler_module.forecast_record_catch_up_at(started) == kwargs["next_run_time"]
    else:
        assert "next_run_time" not in kwargs  # left out, never None
        assert scheduler_module.forecast_record_catch_up_at(started) is None


def test_without_a_catch_up_the_job_waits_for_its_schedule_and_is_not_paused(
    settings_store: SettingsStore, monkeypatch: pytest.MonkeyPatch
) -> None:
    started = _taipei(FRIDAY, 16, 0)
    monkeypatch.setattr(scheduler_module, "_utc_now", lambda: started)
    engine = scheduler_module.build_scheduler(BackgroundScheduler(timezone="UTC"))
    engine.start(paused=True)
    try:
        job = engine.get_job("forecast_record")
        assert job.next_run_time is not None  # a job added with None would be paused
        assert job.next_run_time > datetime.now(UTC)
        local = job.next_run_time.astimezone(TAIPEI)
        assert (local.weekday() < 5, local.hour, local.minute) == (True, 22, 10)
    finally:
        engine.shutdown(wait=False)


def test_the_window_bounds_are_the_session_close_and_the_first_scheduled_run() -> None:
    assert scheduler_module.FORECAST_RECORD_NO_CATCH_UP_FROM == TW_POLICY.session_close
    assert (
        scheduler_module.FORECAST_RECORD_NO_CATCH_UP_UNTIL
        == (scheduler_module.FORECAST_RECORD_TIMES[0])
    )
    assert (TW_POLICY.session_close.hour, TW_POLICY.session_close.minute) == (13, 30)

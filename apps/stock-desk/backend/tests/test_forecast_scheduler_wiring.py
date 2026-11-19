"""The scheduler's job ``forecast_record`` (ADR-0030 D-3 point 7, CG-4, K-3, K-10, S-4a, S-6).

* schedule: weekdays 22:10 and 23:10 Asia/Taipei, ``max_instances=1``,
  ``coalesce=True``, and one catch-up run three minutes after start-up;
* the job enters the core only through ``app.forecast.recorder`` (AST and
  import graph; K-3) and passes ``app.services.index.load_market_benchmark``
  itself (S-4a: the ``is`` check on what the job actually passes);
* the job has no T, ``as_of`` or clock parameter (K-10, S-6);
* the target (supplement 9 point 3): ``STOCK_DESK_DB_PATH`` set (even
  empty), a main DB other than ``<backend>/data/stock-desk.db``, a missing
  file or a directory -- the recorder is not called, one fixed WARNING line is
  logged and no file is created; the scheduler reads no ``.env`` (AST);
* the ledger schema is created only by ``bootstrap`` (supplement 4 point 2):
  on a main DB without it the run is refused and no ledger object appears; an
  empty registry closes the gate (CG-2, S-7);
* ``KeyboardInterrupt`` is not swallowed by the job's guard.

Every database is a ``tmp_path`` file: the production target function
(``production_db_target``) is pointed at ``<tmp>/data/stock-desk.db``, the
working directory is ``<tmp>`` and ``STOCK_DESK_DB_PATH`` is unset -- the job
itself takes no path (K-10). Nothing is started and nothing reaches the
network.
"""

from __future__ import annotations

import ast
import inspect
import logging
import sqlite3
from collections.abc import Mapping
from contextlib import closing
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

import pytest
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.schedulers.blocking import BlockingScheduler
from apscheduler.triggers.combining import OrTrigger
from apscheduler.triggers.cron import CronTrigger

from app import scheduler as scheduler_module
from app.forecast import recorder as recorder_module
from app.forecast.recorder import RunResult
from app.forecast.schema import SchemaIncompleteError, create_schema
from app.services.index import load_market_benchmark
from app.settings.store import SettingsStore
from tests.import_graph import APP_ROOT, reachable_app_modules

TAIPEI = ZoneInfo("Asia/Taipei")
CORE_PACKAGES = ("app.forecast", "app.outlook", "app.dirdef")
TIME_PARAMS = {"T", "t", "as_of", "clock", "now", "today", "data_as_of", "at", "when"}


@pytest.fixture
def settings(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> SettingsStore:
    store = SettingsStore(db_path=tmp_path / "settings.db")
    monkeypatch.setattr(scheduler_module, "get_settings_store", lambda: store)
    return store


def _job(engine: BlockingScheduler) -> Any:
    job = engine.get_job("forecast_record")
    assert job is not None
    return job


def _fields(trigger: CronTrigger) -> dict[str, str]:
    return {field.name: str(field) for field in trigger.fields}


# --- schedule -----------------------------------------------------------------------------------


def test_the_job_runs_on_weekdays_at_22_10_and_23_10_taipei(settings: SettingsStore) -> None:
    job = _job(scheduler_module.build_scheduler(BlockingScheduler(timezone="UTC")))
    assert job.id == recorder_module.JOB_ID == "forecast_record"
    assert isinstance(job.trigger, OrTrigger)
    crons = job.trigger.triggers
    assert all(isinstance(cron, CronTrigger) for cron in crons)
    assert {str(cron.timezone) for cron in crons} == {"Asia/Taipei"}
    assert sorted(
        (_fields(c)["day_of_week"], _fields(c)["hour"], _fields(c)["minute"]) for c in crons
    ) == [
        ("mon-fri", "22", "10"),
        ("mon-fri", "23", "10"),
    ]
    assert job.max_instances == 1 and job.coalesce is True


@pytest.mark.parametrize(
    ("now", "expected"),
    [
        pytest.param(
            datetime(2026, 11, 16, 21, 0), datetime(2026, 11, 16, 22, 10), id="mon-evening"
        ),
        pytest.param(datetime(2026, 11, 16, 22, 30), datetime(2026, 11, 16, 23, 10), id="retry"),
        pytest.param(datetime(2026, 11, 20, 23, 30), datetime(2026, 11, 23, 22, 10), id="weekend"),
    ],
)
def test_the_next_fire_times(settings: SettingsStore, now: datetime, expected: datetime) -> None:
    job = _job(scheduler_module.build_scheduler(BlockingScheduler(timezone="UTC")))
    fired = job.trigger.get_next_fire_time(None, now.replace(tzinfo=TAIPEI))
    assert fired == expected.replace(tzinfo=TAIPEI)


def test_the_job_also_runs_three_minutes_after_start_up(settings: SettingsStore) -> None:
    engine = scheduler_module.build_scheduler(BackgroundScheduler(timezone="UTC"))
    engine.start(paused=True)
    try:
        started = datetime.now(UTC)
        first = engine.get_job("forecast_record").next_run_time
        assert abs(first - (started + timedelta(minutes=3))) < timedelta(seconds=30)
    finally:
        engine.shutdown(wait=False)


def test_the_job_has_no_time_parameter() -> None:
    assert list(inspect.signature(scheduler_module.run_forecast_record).parameters) == []
    assert not set(inspect.signature(recorder_module.ledger_store).parameters) & TIME_PARAMS


# --- K-3: the only way into the core ------------------------------------------------------------


def _scheduler_tree() -> ast.Module:
    return ast.parse((APP_ROOT / "scheduler.py").read_text(encoding="utf-8"))


def _core_imports(tree: ast.Module) -> list[str]:
    found: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            found += [a.name for a in node.names if a.name.startswith(CORE_PACKAGES)]
        elif isinstance(node, ast.ImportFrom) and node.module:
            if node.module.startswith(CORE_PACKAGES) or node.module == "app":
                if node.module == "app":
                    found += [
                        f"app.{a.name}"
                        for a in node.names
                        if a.name in ("forecast", "outlook", "dirdef")
                    ]
                else:
                    found.append(node.module)
    return found


def test_k3_the_scheduler_imports_only_the_recorder_from_the_core() -> None:
    assert set(_core_imports(_scheduler_tree())) == {"app.forecast.recorder"}


def test_the_core_import_scan_has_teeth() -> None:
    for source in (
        "from app.forecast.store import ForecastStore\n",
        "import app.outlook.engine\n",
        "from app import dirdef\n",
    ):
        assert _core_imports(ast.parse(source)) != []
        assert set(_core_imports(ast.parse(source))) != {"app.forecast.recorder"}


def test_k3_the_scheduler_reaches_no_core_module_the_recorder_does_not() -> None:
    def core(modules: set[str]) -> set[str]:
        # Names imported from the recorder itself are listed as ``module.name``.
        return {
            m
            for m in modules
            if m.startswith(CORE_PACKAGES) and not m.startswith("app.forecast.recorder.")
        }

    via_scheduler = core(set(reachable_app_modules(("app.scheduler",))))
    via_recorder = core(set(reachable_app_modules(("app.forecast.recorder",)))) | {
        "app.forecast.recorder"
    }
    assert "app.forecast.recorder" in via_scheduler
    assert via_scheduler <= via_recorder


def test_the_scheduler_calls_no_schema_or_registration_writer() -> None:
    called = {
        node.func.attr if isinstance(node.func, ast.Attribute) else getattr(node.func, "id", "")
        for node in ast.walk(_scheduler_tree())
        if isinstance(node, ast.Call)
    }
    forbidden = {
        "bootstrap",
        "create_objects",
        "create_schema",
        "register_claim",
        "write_run_records",
    }
    assert called & forbidden == set()


# --- supplement 9 point 3: the production target ------------------------------------------------


@pytest.fixture
def target(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """``<tmp>/data/stock-desk.db`` as the production target; the file is not created here."""
    monkeypatch.delenv("STOCK_DESK_DB_PATH", raising=False)
    monkeypatch.chdir(tmp_path)
    (tmp_path / "data").mkdir()
    db = (tmp_path / "data" / "stock-desk.db").resolve()
    monkeypatch.setattr(scheduler_module, "production_db_target", lambda: db)
    return db


def _files(root: Path) -> list[str]:
    return sorted(str(path.relative_to(root)) for path in root.rglob("*"))


@pytest.mark.parametrize(
    ("case", "key"),
    [
        pytest.param("env-set", "env_db_path", id="env-set"),
        pytest.param("env-empty", "env_db_path", id="env-empty"),
        pytest.param("other-target", "target_not_default", id="other-target"),
        pytest.param("missing", "target_unresolved", id="missing-file"),
        pytest.param("directory", "target_not_regular", id="directory"),
    ],
)
def test_s19a_a_refused_target_does_not_call_the_recorder(
    tmp_path: Path,
    target: Path,
    monkeypatch: pytest.MonkeyPatch,
    caplog: Any,
    case: str,
    key: str,
) -> None:
    if case == "env-set":
        sqlite3.connect(target).close()
        monkeypatch.setenv("STOCK_DESK_DB_PATH", str(target))
    elif case == "env-empty":
        sqlite3.connect(target).close()
        monkeypatch.setenv("STOCK_DESK_DB_PATH", "")
    elif case == "other-target":
        sqlite3.connect(target).close()
        other = tmp_path / "elsewhere"
        monkeypatch.setattr(
            scheduler_module, "production_db_target", lambda: other / "data" / "stock-desk.db"
        )
    elif case == "directory":
        target.mkdir()
    before = _files(tmp_path)
    calls = _spy(monkeypatch)
    with caplog.at_level(logging.WARNING, logger="scheduler"):
        assert scheduler_module.run_forecast_record() is None
    assert calls == []
    messages = [r.getMessage() for r in caplog.records if r.name == "scheduler"]
    assert messages == [scheduler_module.FORECAST_RECORD_REFUSALS[key]]
    assert str(tmp_path) not in messages[0] and "stock-desk.db" not in messages[0]
    assert _files(tmp_path) == before  # nothing created, no SQLite file opened into being


def test_s19a_each_refusal_is_one_fixed_line_without_a_path() -> None:
    lines = scheduler_module.FORECAST_RECORD_REFUSALS
    assert set(lines) == {
        "env_db_path",
        "target_unresolved",
        "target_not_default",
        "target_not_regular",
    }
    assert len(set(lines.values())) == 4
    for line in lines.values():
        assert line.startswith("forecast_record: ") and line.isascii()
        assert "/" not in line and "\\" not in line and "{" not in line and "%" not in line


def test_s19a_the_default_target_calls_the_recorder(
    target: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    sqlite3.connect(target).close()
    calls = _spy(monkeypatch)
    monkeypatch.setattr(scheduler_module, "get_index_resolver", lambda: {})
    assert scheduler_module.run_forecast_record() is not None
    ((store, _),) = calls
    assert store._db_path == target


def test_the_production_target_is_derived_from_the_module_location() -> None:
    backend = Path(scheduler_module.__file__).resolve().parent.parent
    assert scheduler_module.BACKEND_DIR == backend
    # Built from the module location; nothing at that path is opened or stat-ed here.
    assert scheduler_module.production_db_target() == backend / "data" / "stock-desk.db"


def _string_constants(tree: ast.Module) -> list[str]:
    """String constants that are not docstrings."""
    docstrings = {
        id(node.body[0].value)
        for node in ast.walk(tree)
        if isinstance(node, ast.Module | ast.FunctionDef | ast.AsyncFunctionDef | ast.ClassDef)
        and node.body
        and isinstance(node.body[0], ast.Expr)
        and isinstance(node.body[0].value, ast.Constant)
    }
    return [
        node.value
        for node in ast.walk(tree)
        if isinstance(node, ast.Constant)
        and isinstance(node.value, str)
        and id(node) not in docstrings
    ]


def _reads_env_file(tree: ast.Module) -> list[str]:
    found = [text for text in _string_constants(tree) if ".env" in text]
    found += [
        ast.unparse(node)
        for node in ast.walk(tree)
        if isinstance(node, ast.Import | ast.ImportFrom)
        and any("dotenv" in (alias.name or "") for alias in node.names)
        or (isinstance(node, ast.ImportFrom) and "dotenv" in (node.module or ""))
    ]
    return found


def test_s19a_the_scheduler_reads_no_env_file() -> None:
    assert _reads_env_file(_scheduler_tree()) == []
    tree = ast.parse(inspect.getsource(scheduler_module.forecast_record_target))
    names = {n.id for n in ast.walk(tree) if isinstance(n, ast.Name)}
    assert "open" not in names and "connect" not in names


def test_the_env_file_scan_has_teeth() -> None:
    assert _reads_env_file(ast.parse("p = backend / '.env'\n")) != []
    assert _reads_env_file(ast.parse("from dotenv import load_dotenv\n")) != []
    assert _reads_env_file(ast.parse('"""Reads no .env."""\n')) == []


# --- S-4a: the loader passed is the index loader itself -----------------------------------------


def _spy(monkeypatch: pytest.MonkeyPatch) -> list[tuple[Any, Mapping[str, Any]]]:
    calls: list[tuple[Any, Mapping[str, Any]]] = []

    def record_forecasts(store: Any, **kwargs: Any) -> RunResult:
        calls.append((store, kwargs))
        return RunResult(
            run_id=1, outcome="ok", candidate_t=None, records_written=0, error_class=None
        )

    monkeypatch.setattr(scheduler_module, "record_forecasts", record_forecasts)
    return calls


def test_s4a_the_job_passes_load_market_benchmark_itself(
    target: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    sqlite3.connect(target).close()
    resolver = object()
    monkeypatch.setattr(scheduler_module, "get_index_resolver", lambda: resolver)
    calls = _spy(monkeypatch)
    result = scheduler_module.run_forecast_record()
    assert result is not None and result.outcome == "ok"
    ((store, kwargs),) = calls
    assert kwargs["load_benchmark"] is load_market_benchmark
    assert kwargs["resolver"] is resolver
    assert set(kwargs) == {"load_benchmark", "resolver"}
    assert store._db_path == target


def test_the_registered_job_runs_the_recorder_job(
    settings: SettingsStore, target: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    sqlite3.connect(target).close()
    monkeypatch.setattr(scheduler_module, "get_index_resolver", lambda: {})
    calls = _spy(monkeypatch)
    job = _job(scheduler_module.build_scheduler(BlockingScheduler(timezone="UTC")))
    job.func()
    assert len(calls) == 1 and calls[0][1]["load_benchmark"] is load_market_benchmark


def test_a_keyboard_interrupt_passes_through_the_guarded_job(
    settings: SettingsStore, target: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # qa N-5: the guard catches Exception only; an interruption is never swallowed.
    sqlite3.connect(target).close()
    monkeypatch.setattr(scheduler_module, "get_index_resolver", lambda: {})

    def interrupted(store: Any, **kwargs: Any) -> RunResult:
        raise KeyboardInterrupt

    monkeypatch.setattr(scheduler_module, "record_forecasts", interrupted)
    job = _job(scheduler_module.build_scheduler(BlockingScheduler(timezone="UTC")))
    with pytest.raises(KeyboardInterrupt):
        job.func()


# --- supplement 4 point 2: no schema, empty registry ---------------------------------------------


def _ledger_objects(db: Path) -> list[str]:
    with closing(sqlite3.connect(db)) as conn:
        return [
            str(name)
            for (name, table) in conn.execute("SELECT name, tbl_name FROM sqlite_master")
            if str(name).lower().startswith(("forecast_", "plan_"))
            or str(table).lower().startswith(("forecast_", "plan_"))
        ]


def test_without_the_ledger_schema_the_run_is_refused_and_nothing_is_created(
    target: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    with closing(sqlite3.connect(target)) as conn:
        conn.execute("CREATE TABLE positions (id INTEGER PRIMARY KEY, symbol TEXT)")
        conn.execute("INSERT INTO positions (symbol) VALUES ('2330')")
        conn.commit()
    monkeypatch.setattr(scheduler_module, "get_index_resolver", lambda: {})
    with pytest.raises(SchemaIncompleteError):
        scheduler_module.run_forecast_record()
    assert _ledger_objects(target) == []
    with closing(sqlite3.connect(target)) as conn:
        assert conn.execute("SELECT symbol FROM positions").fetchall() == [("2330",)]


def test_the_guarded_job_logs_the_refusal_and_survives(
    settings: SettingsStore, target: Path, monkeypatch: pytest.MonkeyPatch, caplog: Any
) -> None:
    sqlite3.connect(target).close()
    monkeypatch.setattr(scheduler_module, "get_index_resolver", lambda: {})
    job = _job(scheduler_module.build_scheduler(BlockingScheduler(timezone="UTC")))
    with caplog.at_level(logging.ERROR, logger="scheduler"):
        job.func()  # does not raise
    assert any("forecast_record" in r.getMessage() for r in caplog.records)
    assert _ledger_objects(target) == []


def test_an_empty_registry_closes_the_gate_and_writes_only_the_run_rows(
    target: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """CG-2 with an empty registry: ``gate_closed``.

    No ``forecast_record``, ``forecast_input_series`` or ``forecast_claim_registry``
    row is written; the run's ``forecast_run`` and ``forecast_run_end`` rows are
    written as for every run (D-2 points 1-2), the end row with ``gate_closed``
    (qa N-4).
    """
    with closing(sqlite3.connect(target, isolation_level=None)) as conn:
        create_schema(conn)  # test only: in production only bootstrap creates it

    def no_fetch(*args: object, **kwargs: object) -> object:  # pragma: no cover - must not run
        raise AssertionError("a closed gate must not read market data")

    monkeypatch.setattr(scheduler_module, "get_index_resolver", lambda: {})
    monkeypatch.setattr(recorder_module, "_fetch", no_fetch)
    result = scheduler_module.run_forecast_record()
    assert result is not None
    assert (result.outcome, result.records_written, result.error_class) == (
        "gate_closed",
        0,
        "WriteGateClosedError",
    )
    with closing(sqlite3.connect(target)) as conn:
        assert conn.execute("SELECT count(*) FROM forecast_record").fetchone() == (0,)
        assert conn.execute("SELECT count(*) FROM forecast_input_series").fetchone() == (0,)
        assert conn.execute("SELECT count(*) FROM forecast_claim_registry").fetchone() == (0,)
        assert conn.execute("SELECT count(*) FROM forecast_run").fetchone() == (1,)
        assert conn.execute("SELECT outcome FROM forecast_run_end").fetchall() == [("gate_closed",)]

"""The scheduler's job ``forecast_record`` (ADR-0030 D-3 point 7, CG-4, K-3, K-10, S-4a, S-6).

* schedule: weekdays 22:10 and 23:10 Asia/Taipei, ``max_instances=1``,
  ``coalesce=True``, and one catch-up run three minutes after start-up;
* the job enters the core only through ``app.forecast.recorder`` (AST and
  import graph; K-3) and passes ``app.services.index.load_market_benchmark``
  itself (S-4a: the ``is`` check on what the job actually passes);
* the job has no T, ``as_of`` or clock parameter (K-10, S-6);
* the ledger schema is created only by ``bootstrap`` (supplement 4 point 2):
  on a main DB without it the run is refused and no ledger object appears; a
  missing main DB file is not created; an empty registry closes the gate
  (CG-2, S-7) and nothing is recorded.

Every database is a ``tmp_path`` file (``STOCK_DESK_DB_PATH`` points at it);
nothing is started and nothing reaches the network.
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
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    db = tmp_path / "main.db"
    sqlite3.connect(db).close()
    monkeypatch.setenv("STOCK_DESK_DB_PATH", str(db))
    resolver = object()
    monkeypatch.setattr(scheduler_module, "get_index_resolver", lambda: resolver)
    calls = _spy(monkeypatch)
    result = scheduler_module.run_forecast_record()
    assert result is not None and result.outcome == "ok"
    ((store, kwargs),) = calls
    assert kwargs["load_benchmark"] is load_market_benchmark
    assert kwargs["resolver"] is resolver
    assert set(kwargs) == {"load_benchmark", "resolver"}
    assert store._db_path == db  # the main DB every store uses


def test_the_registered_job_runs_the_recorder_job(
    settings: SettingsStore, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    db = tmp_path / "main.db"
    sqlite3.connect(db).close()
    monkeypatch.setenv("STOCK_DESK_DB_PATH", str(db))
    monkeypatch.setattr(scheduler_module, "get_index_resolver", lambda: {})
    calls = _spy(monkeypatch)
    job = _job(scheduler_module.build_scheduler(BlockingScheduler(timezone="UTC")))
    job.func()
    assert len(calls) == 1 and calls[0][1]["load_benchmark"] is load_market_benchmark


# --- supplement 4 point 2: no schema, no file, empty registry -----------------------------------


def _ledger_objects(db: Path) -> list[str]:
    with closing(sqlite3.connect(db)) as conn:
        return [
            str(name)
            for (name, table) in conn.execute("SELECT name, tbl_name FROM sqlite_master")
            if str(name).lower().startswith(("forecast_", "plan_"))
            or str(table).lower().startswith(("forecast_", "plan_"))
        ]


def test_without_the_ledger_schema_the_run_is_refused_and_nothing_is_created(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    db = tmp_path / "main.db"
    with closing(sqlite3.connect(db)) as conn:
        conn.execute("CREATE TABLE positions (id INTEGER PRIMARY KEY, symbol TEXT)")
        conn.execute("INSERT INTO positions (symbol) VALUES ('2330')")
        conn.commit()
    monkeypatch.setenv("STOCK_DESK_DB_PATH", str(db))
    monkeypatch.setattr(scheduler_module, "get_index_resolver", lambda: {})
    with pytest.raises(SchemaIncompleteError):
        scheduler_module.run_forecast_record()
    assert _ledger_objects(db) == []
    with closing(sqlite3.connect(db)) as conn:
        assert conn.execute("SELECT symbol FROM positions").fetchall() == [("2330",)]


def test_the_guarded_job_logs_the_refusal_and_survives(
    settings: SettingsStore, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, caplog: Any
) -> None:
    db = tmp_path / "main.db"
    sqlite3.connect(db).close()
    monkeypatch.setenv("STOCK_DESK_DB_PATH", str(db))
    monkeypatch.setattr(scheduler_module, "get_index_resolver", lambda: {})
    job = _job(scheduler_module.build_scheduler(BlockingScheduler(timezone="UTC")))
    with caplog.at_level(logging.ERROR, logger="scheduler"):
        job.func()  # does not raise
    assert any("forecast_record" in r.getMessage() for r in caplog.records)
    assert _ledger_objects(db) == []


def test_a_missing_main_db_file_is_not_created(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, caplog: Any
) -> None:
    db = tmp_path / "absent" / "main.db"
    monkeypatch.setenv("STOCK_DESK_DB_PATH", str(db))
    calls = _spy(monkeypatch)
    with caplog.at_level(logging.WARNING, logger="scheduler"):
        assert scheduler_module.run_forecast_record() is None
    assert calls == [] and not db.exists() and not db.parent.exists()
    assert [r.getMessage() for r in caplog.records] == [scheduler_module.FORECAST_RECORD_NO_DB]


def test_an_empty_registry_closes_the_gate_and_records_nothing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    db = tmp_path / "main.db"
    with closing(sqlite3.connect(db, isolation_level=None)) as conn:
        create_schema(conn)  # test only: in production only bootstrap creates it
    monkeypatch.setenv("STOCK_DESK_DB_PATH", str(db))

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
    with closing(sqlite3.connect(db)) as conn:
        assert conn.execute("SELECT count(*) FROM forecast_record").fetchone() == (0,)
        assert conn.execute("SELECT count(*) FROM forecast_input_series").fetchone() == (0,)
        assert conn.execute("SELECT count(*) FROM forecast_claim_registry").fetchone() == (0,)

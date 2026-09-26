"""The sector card's two scheduler jobs (ADR-0012 D-5; T-4 / C-11).

* ``pit_snapshot_capture`` and ``sector_board_refresh`` are cron jobs on
  weekdays, Asia/Taipei, at 17:30 / 19:30 / 21:30 and 17:45 / 19:45 / 21:45,
  with ``max_instances=1``, ``coalesce=True`` and a start-up run;
* a capture is followed by a board refresh, and a failing refresh never
  undoes the capture;
* ``app.scheduler`` cannot reach ``app.research`` and names no warm-up
  function -- the scheduler never back-fills, fills gaps or runs research;
* the TAIEX reference is a close-to-close return or nothing, never a guess.

No job is started and nothing touches the network.
"""

from __future__ import annotations

import ast
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from pathlib import Path

import pytest
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.schedulers.blocking import BlockingScheduler
from apscheduler.triggers.cron import CronTrigger

from app import scheduler as scheduler_module
from app.data.interface import DataStatus, PriceBar, ProviderResult
from app.services.pit_snapshot import CaptureSummary
from app.services.sector_board import RefreshResult
from app.settings.store import SettingsStore
from tests.import_graph import APP_ROOT, offenders, reachable_app_modules

SECTOR_JOBS = ("pit_snapshot_capture", "sector_board_refresh")


@pytest.fixture
def settings(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> SettingsStore:
    store = SettingsStore(db_path=tmp_path / "settings.db")
    monkeypatch.setattr(scheduler_module, "get_settings_store", lambda: store)
    return store


def _fields(trigger: CronTrigger) -> dict[str, str]:
    return {field.name: str(field) for field in trigger.fields}


def test_the_sector_jobs_are_weekday_crons_in_taipei_time(settings: SettingsStore) -> None:
    engine = scheduler_module.build_scheduler(BlockingScheduler(timezone="UTC"))
    capture = engine.get_job("pit_snapshot_capture")
    refresh = engine.get_job("sector_board_refresh")
    for job, minute in ((capture, "30"), (refresh, "45")):
        assert isinstance(job.trigger, CronTrigger)
        assert str(job.trigger.timezone) == "Asia/Taipei"
        fields = _fields(job.trigger)
        assert fields["day_of_week"] == "mon-fri"
        assert fields["hour"] == "17,19,21"
        assert fields["minute"] == minute
        assert job.max_instances == 1 and job.coalesce is True


def test_both_sector_jobs_also_run_at_start_up(settings: SettingsStore) -> None:
    engine = scheduler_module.build_scheduler(BackgroundScheduler(timezone="UTC"))
    engine.start(paused=True)
    try:
        started = datetime.now(UTC)
        capture = engine.get_job("pit_snapshot_capture").next_run_time
        refresh = engine.get_job("sector_board_refresh").next_run_time
        assert abs(capture - started) < timedelta(seconds=30)
        # The refresh waits for the capture's own chained refresh, but not long.
        assert timedelta(0) < refresh - started <= timedelta(minutes=3)
    finally:
        engine.shutdown(wait=False)


def test_a_capture_is_followed_by_a_refresh(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[str] = []

    class Adapter:
        def close(self) -> None:
            calls.append("close")

    summary = CaptureSummary(session_date=date(2026, 9, 25), records=())
    monkeypatch.setattr(scheduler_module, "TwseSnapshotAdapter", Adapter)
    monkeypatch.setattr(scheduler_module, "get_market_panel_store", lambda: object())

    def capture(adapter: object, store: object) -> CaptureSummary:
        calls.append("capture")
        return summary

    monkeypatch.setattr(scheduler_module, "capture_once", capture)

    def refresh() -> RefreshResult:
        calls.append("refresh")
        raise RuntimeError("board bug")

    monkeypatch.setattr(scheduler_module, "refresh_sector_board", refresh)
    assert scheduler_module.capture_pit_snapshot() is summary
    assert calls == ["capture", "close", "refresh"]


def test_the_refresh_job_runs_the_service(monkeypatch: pytest.MonkeyPatch) -> None:
    result = RefreshResult(date(2026, 9, 25), date(2026, 9, 1), "b1", None, ("board_unchanged",))

    class Service:
        def refresh(self) -> RefreshResult:
            return result

    monkeypatch.setattr(scheduler_module, "get_sector_board_service", lambda: Service())
    assert scheduler_module.refresh_sector_board() is result


def test_the_scheduler_cannot_reach_research() -> None:
    assert offenders(reachable_app_modules(("app.scheduler",)), "app.research") == []


def _warmup_names(path: Path) -> list[str]:
    found: list[str] = []
    for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
        name = None
        if isinstance(node, ast.Name):
            name = node.id
        elif isinstance(node, ast.Attribute):
            name = node.attr
        elif isinstance(node, ast.alias):
            name = node.asname or node.name
        elif isinstance(node, ast.FunctionDef):
            name = node.name
        if name is not None and "warmup" in name.lower().replace("_", ""):
            found.append(name)
    return found


def test_the_scheduler_names_no_warm_up_function() -> None:
    assert _warmup_names(APP_ROOT / "scheduler.py") == []


def test_the_warm_up_scan_has_teeth(tmp_path: Path) -> None:
    leak = tmp_path / "leak.py"
    leak.write_text(
        "from app.services.pit_snapshot import run_warmup\nrun_warmup(store, client, [])\n",
        encoding="utf-8",
    )
    assert _warmup_names(leak) == ["run_warmup", "run_warmup"]


class _Index:
    def __init__(self, bars: list[PriceBar]) -> None:
        self._bars = bars

    def get_daily_bars(self, symbol: str, market: str, start: date, end: date) -> ProviderResult:
        return ProviderResult(
            bars=self._bars,
            status=DataStatus.BACKUP,
            source="fake",
            as_of=datetime(2026, 9, 25, tzinfo=UTC),
        )


def _bar(day: date, close: str) -> PriceBar:
    price = Decimal(close)
    return PriceBar(
        symbol="^TWII",
        market="TW",
        date=day,
        open=price,
        high=price,
        low=price,
        close=price,
        volume=0,
        currency="TWD",
        as_of=datetime(2026, 9, 25, tzinfo=UTC),
        source="fake",
    )


def test_the_taiex_reference_is_close_to_close_or_nothing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    start, end = date(2026, 9, 18), date(2026, 9, 25)
    bars = [_bar(start, "20000"), _bar(end, "20500")]
    monkeypatch.setattr(scheduler_module, "get_index_resolver", lambda: {"TW": _Index(bars)})
    assert scheduler_module.taiex_reference_return(start, end) == pytest.approx(0.025)
    monkeypatch.setattr(scheduler_module, "get_index_resolver", lambda: {"TW": _Index(bars[:1])})
    assert scheduler_module.taiex_reference_return(start, end) is None

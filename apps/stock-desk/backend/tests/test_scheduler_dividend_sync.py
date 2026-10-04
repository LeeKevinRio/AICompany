"""The ``dividend_sync`` scheduler job (ADR-0016 D-5.2 / D-5.4).

* it is a weekday Asia/Taipei cron at 17:50 / 19:50 / 21:50 -- after the
  capture (17:30) and the board refresh (17:45) -- with ``max_instances=1``,
  ``coalesce=True`` and no start-up run;
* a Taipei date that already has an ``ok`` run is skipped without a fetch; a
  ``failed`` run, an older date or no run at all is not;
* the sync is the CLI's :func:`sync_dividends` with ``trigger="scheduled"``,
  and the run line carries status / event_count / unparsed / unattributed;
* a failure while writing is logged with its traceback and never escapes;
* a missing ``dividend_sync_runs`` table reads as "no run".

Everything runs on ``tmp_path`` databases with a fake adapter; no socket is opened.
"""

from __future__ import annotations

import logging
import re
import socket
import sqlite3
from collections.abc import Iterator, Sequence
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

import pytest
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.schedulers.blocking import BlockingScheduler
from apscheduler.triggers.cron import CronTrigger

from app import scheduler as scheduler_module
from app.dividends.models import DividendEvent
from app.dividends.providers import DividendFetchResult
from app.dividends.store import DividendEventStore, SyncTrigger
from app.settings.store import SettingsStore

TAIPEI = ZoneInfo("Asia/Taipei")
SOURCE = "twse_openapi_dividend"
#: 2026-10-06 is a Tuesday; 09:50 UTC is 17:50 in Taipei.
NOW = datetime(2026, 10, 6, 9, 50, tzinfo=UTC)


@pytest.fixture(autouse=True)
def _no_network(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    def refuse(*_args: object, **_kwargs: object) -> None:
        raise AssertionError("the dividend_sync tests must not open a socket")

    monkeypatch.setattr(socket.socket, "connect", refuse)
    yield


@pytest.fixture
def settings(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> SettingsStore:
    store = SettingsStore(db_path=tmp_path / "settings.db")
    monkeypatch.setattr(scheduler_module, "get_settings_store", lambda: store)
    return store


def _event(symbol: str = "2330") -> DividendEvent:
    return DividendEvent(
        symbol=symbol,
        market="TW",
        ex_date=date(2026, 10, 20),
        cash_dividend=Decimal("3.00"),
        source=SOURCE,
        as_of=NOW,
    )


def _result(
    *,
    ok: bool = True,
    events: Sequence[DividendEvent] | None = None,
    unparsed: tuple[str, ...] = (),
    unattributed: int = 0,
) -> DividendFetchResult:
    return DividendFetchResult(
        events=tuple(events if events is not None else [_event()]) if ok else (),
        ok=ok,
        reason=None if ok else "upstream down",
        source=SOURCE,
        as_of=NOW,
        unparsed_symbols=unparsed,
        unattributed_rows=unattributed,
    )


class FakeAdapter:
    def __init__(self, result: DividendFetchResult | None = None) -> None:
        self.result = result if result is not None else _result()
        self.calls = 0

    def fetch(self) -> DividendFetchResult:
        self.calls += 1
        return self.result

    def close(self) -> None:
        pass


class SpyStore(DividendEventStore):
    """A real store that remembers the triggers it was asked to record."""

    def __init__(self, db_path: Path, *, write: bool = True) -> None:
        super().__init__(db_path)
        self.triggers: list[SyncTrigger] = []
        self._write = write

    def record_sync(self, **kwargs: Any) -> int:
        self.triggers.append(kwargs["trigger"])
        return super().record_sync(**kwargs) if self._write else 1


def _seed_run(
    db: Path, recorded_at: datetime, *, ok: bool = True, trigger: SyncTrigger = "cli"
) -> None:
    """Write one sync run stamped ``recorded_at`` through the store's own writer."""
    store = DividendEventStore(db, clock=lambda: recorded_at)
    result = _result(ok=ok)
    store.record_sync(
        trigger=trigger,
        source=result.source,
        adapter_ok=result.ok,
        reason=result.reason,
        events=list(result.events),
    )


def _run_rows(db: Path) -> list[tuple[str, str]]:
    with sqlite3.connect(db) as conn:
        return [
            (str(row[0]), str(row[1]))
            for row in conn.execute(
                "SELECT status, trigger FROM dividend_sync_runs ORDER BY run_id"
            )
        ]


# --- registration ---------------------------------------------------------


def test_the_job_is_a_weekday_taipei_cron_after_the_capture(settings: SettingsStore) -> None:
    engine = scheduler_module.build_scheduler(BlockingScheduler(timezone="UTC"))
    job = engine.get_job("dividend_sync")
    assert job is not None
    assert isinstance(job.trigger, CronTrigger)
    assert str(job.trigger.timezone) == "Asia/Taipei"
    fields = {field.name: str(field) for field in job.trigger.fields}
    assert fields["day_of_week"] == "mon-fri"
    assert fields["hour"] == "17,19,21"
    assert fields["minute"] == "50"
    assert job.max_instances == 1 and job.coalesce is True
    # Strictly after the capture and the board refresh of the same hour.
    assert scheduler_module.DIVIDEND_SYNC_MINUTE > scheduler_module.SECTOR_REFRESH_MINUTE
    assert scheduler_module.DIVIDEND_SYNC_MINUTE > scheduler_module.PIT_CAPTURE_MINUTE


def test_the_fire_times_are_weekday_taipei_17_50_19_50_21_50(settings: SettingsStore) -> None:
    engine = scheduler_module.build_scheduler(BlockingScheduler(timezone="UTC"))
    trigger = engine.get_job("dividend_sync").trigger
    fires: list[datetime] = []
    moment = datetime(2026, 10, 5, 0, 0, tzinfo=TAIPEI)  # a Monday, midnight Taipei
    previous = None
    for _ in range(15):  # three a day across five weekdays
        fire = trigger.get_next_fire_time(previous, moment)
        assert fire is not None
        fires.append(fire.astimezone(TAIPEI))
        previous, moment = fire, fire + timedelta(seconds=1)
    assert [f.weekday() for f in fires] == [0] * 3 + [1] * 3 + [2] * 3 + [3] * 3 + [4] * 3
    assert {(f.hour, f.minute) for f in fires} == {(17, 50), (19, 50), (21, 50)}
    # The weekend is skipped: the next one after Friday 21:50 is Monday.
    after_friday = trigger.get_next_fire_time(fires[-1], fires[-1] + timedelta(seconds=1))
    assert after_friday is not None and after_friday.astimezone(TAIPEI).weekday() == 0


def test_the_job_does_not_run_at_start_up(settings: SettingsStore) -> None:
    engine = scheduler_module.build_scheduler(BackgroundScheduler(timezone="UTC"))
    engine.start(paused=True)
    try:
        started = datetime.now(UTC)
        first = engine.get_job("dividend_sync").next_run_time
        capture = engine.get_job("pit_snapshot_capture").next_run_time
        assert abs(capture - started) < timedelta(seconds=30)  # the sibling does
        assert first - started > timedelta(seconds=30)
        local = first.astimezone(TAIPEI)
        assert (local.hour, local.minute) in {(17, 50), (19, 50), (21, 50)}
        assert local.weekday() < 5
    finally:
        engine.shutdown(wait=False)


def test_the_registered_job_runs_the_sync_and_survives_its_failure(
    settings: SettingsStore, monkeypatch: pytest.MonkeyPatch
) -> None:
    calls: list[str] = []

    def boom() -> None:
        calls.append("run")
        raise RuntimeError("unexpected")

    monkeypatch.setattr(scheduler_module, "run_dividend_sync", boom)
    engine = scheduler_module.build_scheduler(BlockingScheduler(timezone="UTC"))
    engine.get_job("dividend_sync").func()  # _guarded: must not raise
    assert calls == ["run"]


def test_no_environment_switch_names_the_job() -> None:
    env_names = [name for name in dir(scheduler_module) if name.endswith("_ENV")]
    assert not [name for name in env_names if "DIVIDEND" in name]


# --- the same-day skip ----------------------------------------------------


def test_an_ok_run_on_the_same_taipei_date_skips_the_fetch(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    db = tmp_path / "d.db"
    # 16:30 UTC on the 5th is 00:30 on the 6th in Taipei: the UTC date differs.
    _seed_run(db, datetime(2026, 10, 5, 16, 30, tzinfo=UTC))
    adapter = FakeAdapter()
    with caplog.at_level(logging.INFO, logger="scheduler"):
        result = scheduler_module.run_dividend_sync(
            store=DividendEventStore(db), adapter=adapter, clock=lambda: NOW
        )
    assert result is None
    assert adapter.calls == 0
    assert len(_run_rows(db)) == 1
    assert any("outcome=skipped" in r.getMessage() for r in caplog.records)


def test_an_ok_run_on_an_earlier_taipei_date_does_not_skip(tmp_path: Path) -> None:
    db = tmp_path / "d.db"
    _seed_run(db, datetime(2026, 10, 5, 9, 50, tzinfo=UTC))
    adapter = FakeAdapter()
    scheduler_module.run_dividend_sync(
        store=DividendEventStore(db), adapter=adapter, clock=lambda: NOW
    )
    assert adapter.calls == 1
    assert [row[0] for row in _run_rows(db)] == ["ok", "ok"]


def test_a_failed_run_today_does_not_skip_the_retry(tmp_path: Path) -> None:
    db = tmp_path / "d.db"
    _seed_run(db, datetime(2026, 10, 6, 1, 0, tzinfo=UTC), ok=False)
    adapter = FakeAdapter()
    scheduler_module.run_dividend_sync(
        store=DividendEventStore(db), adapter=adapter, clock=lambda: NOW
    )
    assert adapter.calls == 1
    assert [row[0] for row in _run_rows(db)] == ["failed", "ok"]


def test_the_newest_ok_run_decides_not_an_older_one(tmp_path: Path) -> None:
    db = tmp_path / "d.db"
    _seed_run(db, datetime(2026, 10, 6, 1, 0, tzinfo=UTC))
    _seed_run(db, datetime(2026, 10, 6, 5, 0, tzinfo=UTC), ok=False)
    assert scheduler_module.latest_ok_dividend_sync_date(db) == date(2026, 10, 6)


# --- the call -------------------------------------------------------------


def test_no_run_means_a_scheduled_sync(tmp_path: Path, caplog: pytest.LogCaptureFixture) -> None:
    db = tmp_path / "d.db"
    store = SpyStore(db)
    adapter = FakeAdapter(_result(unparsed=("9999", "9999"), unattributed=3))
    with caplog.at_level(logging.INFO, logger="scheduler"):
        result = scheduler_module.run_dividend_sync(store=store, adapter=adapter, clock=lambda: NOW)
    assert result is not None and result.ok
    assert adapter.calls == 1
    assert store.triggers == ["scheduled"]
    assert _run_rows(db) == [("ok", "scheduled")]
    assert store.count() == 1
    lines = [r for r in caplog.records if r.name == "scheduler"]
    assert len(lines) == 1
    assert lines[0].levelno == logging.INFO
    assert re.fullmatch(
        r"dividend sync run: trigger=scheduled taipei=2026-10-06 status=ok "
        r"event_count=1 unparsed_count=2 unattributed_count=3 duration_ms=\d+",
        lines[0].getMessage(),
    )


def test_an_adapter_failure_is_a_failed_run_and_a_warning_line(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    db = tmp_path / "d.db"
    adapter = FakeAdapter(_result(ok=False))
    with caplog.at_level(logging.INFO, logger="scheduler"):
        result = scheduler_module.run_dividend_sync(
            store=DividendEventStore(db), adapter=adapter, clock=lambda: NOW
        )
    assert result is not None and not result.ok
    assert _run_rows(db) == [("failed", "scheduled")]
    line = next(r for r in caplog.records if r.name == "scheduler")
    assert line.levelno == logging.WARNING
    assert "status=failed event_count=0 unparsed_count=0" in line.getMessage()


def test_an_ok_answer_with_no_events_is_reported_as_failed(tmp_path: Path) -> None:
    db = tmp_path / "d.db"
    scheduler_module.run_dividend_sync(
        store=DividendEventStore(db),
        adapter=FakeAdapter(_result(events=[])),
        clock=lambda: NOW,
    )
    assert _run_rows(db) == [("failed", "scheduled")]


# --- failure containment --------------------------------------------------


def _failing_write_store(db: Path, monkeypatch: pytest.MonkeyPatch) -> DividendEventStore:
    store = DividendEventStore(db)

    def refuse(**_kwargs: object) -> int:
        raise sqlite3.OperationalError("database is locked")

    monkeypatch.setattr(store, "record_sync", refuse)
    return store


def test_a_write_failure_propagates_out_of_the_run(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    db = tmp_path / "d.db"
    store = _failing_write_store(db, monkeypatch)
    with caplog.at_level(logging.INFO, logger="scheduler"), pytest.raises(sqlite3.OperationalError):
        scheduler_module.run_dividend_sync(store=store, adapter=FakeAdapter(), clock=lambda: NOW)
    assert _run_rows(db) == []
    # The run itself logs nothing: the single ERROR line is _guarded's.
    assert not [r for r in caplog.records if r.name == "scheduler"]


def test_a_write_failure_through_the_registered_job_is_one_guarded_error(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
    settings: SettingsStore,
) -> None:
    db = tmp_path / "d.db"
    store = _failing_write_store(db, monkeypatch)
    monkeypatch.setattr(scheduler_module, "get_dividend_store", lambda: store)
    monkeypatch.setattr(scheduler_module, "TwseDividendAdapter", lambda client: FakeAdapter())
    engine = scheduler_module.build_scheduler(BlockingScheduler(timezone="UTC"))
    with caplog.at_level(logging.INFO, logger="scheduler"):
        engine.get_job("dividend_sync").func()  # _guarded: must not raise
    errors = [r for r in caplog.records if r.levelno == logging.ERROR]
    assert len(errors) == 1
    assert "dividend_sync" in errors[0].getMessage()
    assert errors[0].exc_info is not None
    assert errors[0].exc_info[0] is sqlite3.OperationalError
    assert _run_rows(db) == []


# --- the missing table ----------------------------------------------------


def test_a_missing_table_reads_as_no_run(tmp_path: Path) -> None:
    bare = tmp_path / "bare.db"
    sqlite3.connect(bare).close()
    assert scheduler_module.latest_ok_dividend_sync_date(bare) is None


def test_a_missing_table_still_lets_the_sync_run(tmp_path: Path) -> None:
    store = SpyStore(tmp_path / "d.db", write=False)
    with sqlite3.connect(store.db_path) as conn:
        conn.execute("DROP TABLE dividend_sync_runs")
    adapter = FakeAdapter()
    scheduler_module.run_dividend_sync(store=store, adapter=adapter, clock=lambda: NOW)
    assert adapter.calls == 1
    assert store.triggers == ["scheduled"]


def test_an_unreadable_timestamp_reads_as_no_run(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    db = tmp_path / "d.db"
    DividendEventStore(db)
    with sqlite3.connect(db) as conn:
        conn.execute(
            "INSERT INTO dividend_sync_runs (recorded_at, trigger, source, status, event_count, "
            "unparsed_count, unattributed_count) VALUES ('not-a-time', 'cli', 's', 'ok', 1, 0, 0)"
        )
    with caplog.at_level(logging.WARNING, logger="scheduler"):
        assert scheduler_module.latest_ok_dividend_sync_date(db) is None
    assert any("unreadable recorded_at" in r.getMessage() for r in caplog.records)

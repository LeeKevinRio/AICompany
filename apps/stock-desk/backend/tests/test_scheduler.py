"""Tests for the APScheduler-based scheduler: job wiring, guards, intervals.

Nothing here starts the blocking loop or touches the network: jobs are inspected
on a scheduler that is built but never started, and the job bodies are exercised
directly with the production dependency providers monkeypatched onto fakes.
"""

from __future__ import annotations

import signal
from datetime import UTC, date, datetime
from decimal import Decimal
from pathlib import Path

import pytest
from apscheduler.schedulers import SchedulerNotRunningError
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.schedulers.blocking import BlockingScheduler

from app import scheduler as scheduler_module
from app.alerts.store import AlertStore
from app.positions.models import PositionInput
from app.positions.store import PositionStore
from app.settings.models import AlertSettings, AppSettings
from app.settings.store import SettingsStore
from tests.alerts_helpers import add_rule, price_rule
from tests.api_helpers import FakePriceService, recent_bars, trending_closes


@pytest.fixture
def wired(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> dict[str, object]:
    """Point every dependency provider the scheduler uses at a local fake."""
    positions = PositionStore(db_path=tmp_path / "positions.db")
    alerts = AlertStore(db_path=tmp_path / "alerts.db")
    settings = SettingsStore(db_path=tmp_path / "settings.db")
    prices = FakePriceService({"2330": recent_bars(trending_closes(200, start=500.0))})

    monkeypatch.setattr(scheduler_module, "get_position_store", lambda: positions)
    monkeypatch.setattr(scheduler_module, "get_alert_store", lambda: alerts)
    monkeypatch.setattr(scheduler_module, "get_settings_store", lambda: settings)
    monkeypatch.setattr(scheduler_module, "get_market_resolver", lambda: {"TW": prices})
    monkeypatch.setattr(scheduler_module, "get_valuator", lambda: _valuator(prices))
    return {
        "positions": positions,
        "alerts": alerts,
        "settings": settings,
        "prices": prices,
    }


def _valuator(prices: FakePriceService) -> object:
    from app.portfolio.valuation import PositionValuator
    from tests.api_helpers import UnavailableFxProvider

    return PositionValuator(
        market_services={"TW": prices}, fx_provider=UnavailableFxProvider()
    )


def _held(store: PositionStore, symbol: str = "2330") -> None:
    store.create(
        PositionInput(
            symbol=symbol,
            market="TW",
            quantity=Decimal(1000),
            avg_cost=Decimal(500),
            currency="TWD",
            opened_at=date(2024, 1, 2),
            instrument_type="stock",
        )
    )


# --- Heartbeat (kept from the Phase 1 placeholder) ---------------------------


def test_heartbeat_message_timestamp_is_parseable_iso8601() -> None:
    fixed = datetime(2026, 7, 23, 12, 0, 0, tzinfo=UTC)
    message = scheduler_module.heartbeat_message(fixed)
    assert message.startswith("scheduler heartbeat ")
    parsed = datetime.fromisoformat(message.removeprefix("scheduler heartbeat "))
    assert parsed == fixed
    assert parsed.tzinfo is not None


# --- Job registration --------------------------------------------------------


def test_both_jobs_are_registered_with_stable_ids(wired: dict[str, object]) -> None:
    engine = scheduler_module.build_scheduler(BlockingScheduler(timezone="UTC"))
    jobs = {job.id: job for job in engine.get_jobs()}
    assert set(jobs) == {"data_refresh", "alert_evaluation"}
    for job in jobs.values():
        # A slow tick must not stack another behind it, and a missed tick is
        # coalesced into one run rather than replayed.
        assert job.max_instances == 1
        assert job.coalesce is True


def test_alert_interval_comes_from_the_stored_settings(wired: dict[str, object]) -> None:
    settings = wired["settings"]
    assert isinstance(settings, SettingsStore)
    settings.save(AppSettings(alerts=AlertSettings(evaluation_interval_minutes=5)))
    engine = scheduler_module.build_scheduler(BlockingScheduler(timezone="UTC"))
    job = engine.get_job("alert_evaluation")
    assert job.trigger.interval.total_seconds() == 5 * 60


def test_env_overrides_the_intervals(
    wired: dict[str, object], monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv(scheduler_module.DATA_INTERVAL_ENV, "30")
    monkeypatch.setenv(scheduler_module.ALERT_INTERVAL_ENV, "7")
    engine = scheduler_module.build_scheduler(BlockingScheduler(timezone="UTC"))
    assert engine.get_job("data_refresh").trigger.interval.total_seconds() == 30 * 60
    assert engine.get_job("alert_evaluation").trigger.interval.total_seconds() == 7 * 60


def test_nonsense_interval_env_falls_back_to_the_default(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("X_INTERVAL", "not-a-number")
    assert scheduler_module._positive_int_env("X_INTERVAL", 42) == 42
    monkeypatch.setenv("X_INTERVAL", "-5")
    assert scheduler_module._positive_int_env("X_INTERVAL", 42) == 42
    monkeypatch.delenv("X_INTERVAL")
    assert scheduler_module._positive_int_env("X_INTERVAL", 42) == 42


# --- Job bodies --------------------------------------------------------------


def test_data_refresh_only_fetches_held_symbols(wired: dict[str, object]) -> None:
    positions = wired["positions"]
    prices = wired["prices"]
    assert isinstance(positions, PositionStore)
    assert isinstance(prices, FakePriceService)
    assert scheduler_module.refresh_market_data() == 0  # nothing held yet
    _held(positions)
    assert scheduler_module.refresh_market_data() == 1
    assert [call[0] for call in prices.calls] == ["2330"]


def test_data_refresh_survives_a_symbol_with_no_bars(wired: dict[str, object]) -> None:
    positions = wired["positions"]
    assert isinstance(positions, PositionStore)
    _held(positions, symbol="9999")
    assert scheduler_module.refresh_market_data() == 0


def test_alert_tick_fires_and_persists(wired: dict[str, object]) -> None:
    alerts = wired["alerts"]
    positions = wired["positions"]
    assert isinstance(alerts, AlertStore)
    assert isinstance(positions, PositionStore)
    _held(positions)
    add_rule(alerts, price_rule(threshold=100.0))
    assert scheduler_module.evaluate_alerts_tick() == 1
    assert len(alerts.list_events(unacknowledged=True)) == 1


def test_alert_tick_is_skipped_when_alerts_are_disabled(wired: dict[str, object]) -> None:
    alerts = wired["alerts"]
    settings = wired["settings"]
    assert isinstance(alerts, AlertStore)
    assert isinstance(settings, SettingsStore)
    add_rule(alerts, price_rule(threshold=100.0))
    settings.save(AppSettings(alerts=AlertSettings(enabled=False)))
    assert scheduler_module.evaluate_alerts_tick() == 0
    assert alerts.list_events() == []


def test_alert_tick_does_not_deliver_when_webhooks_are_off(
    wired: dict[str, object], monkeypatch: pytest.MonkeyPatch
) -> None:
    alerts = wired["alerts"]
    settings = wired["settings"]
    assert isinstance(alerts, AlertStore)
    assert isinstance(settings, SettingsStore)

    def boom(events: object, **kwargs: object) -> object:  # pragma: no cover - must not run
        raise AssertionError("notify_all must not be called with webhooks disabled")

    monkeypatch.setattr(scheduler_module, "notify_all", boom)
    settings.save(AppSettings(alerts=AlertSettings(notify_webhooks=False)))
    add_rule(alerts, price_rule(threshold=100.0))
    assert scheduler_module.evaluate_alerts_tick() == 1


def test_run_registers_signal_handlers_and_shuts_down_cleanly(
    wired: dict[str, object],
) -> None:
    # BackgroundScheduler subclasses BlockingScheduler and returns from
    # ``start`` immediately, so ``run`` can be driven to completion in-process
    # and the real signal-handler path exercised.
    engine = BackgroundScheduler(timezone="UTC")
    scheduler_module.run(engine)
    assert engine.running is True

    handler = signal.getsignal(signal.SIGTERM)
    assert callable(handler)
    assert signal.getsignal(signal.SIGINT) is handler

    handler(signal.SIGTERM, None)
    assert engine.running is False
    # A second delivery of the same signal must stay a clean stop.
    handler(signal.SIGTERM, None)


def test_a_repeated_shutdown_signal_does_not_raise() -> None:
    # docker stop, a double Ctrl-C, or a supervisor re-sending SIGTERM all
    # deliver a second signal after the scheduler has already stopped. That must
    # stay a clean stop, not a traceback and a non-zero exit.
    # (BackgroundScheduler subclasses BlockingScheduler and does not block on
    # start, so the real shutdown path can be exercised in-process.)
    engine = BackgroundScheduler(timezone="UTC")
    engine.start(paused=True)
    scheduler_module.shutdown(engine)
    assert engine.running is False
    scheduler_module.shutdown(engine)  # must not raise


def test_shutdown_survives_a_race_on_the_running_check(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # The window between "running?" and "shutdown()" is real when the second
    # signal lands mid-call, so the except branch is exercised directly.
    engine = BackgroundScheduler(timezone="UTC")
    engine.start(paused=True)

    def already_stopped(wait: bool = True) -> None:
        raise SchedulerNotRunningError

    monkeypatch.setattr(engine, "shutdown", already_stopped)
    try:
        scheduler_module.shutdown(engine)  # must not raise
    finally:
        monkeypatch.undo()
        engine.shutdown(wait=False)


def test_a_failing_job_is_logged_and_stays_scheduled() -> None:
    calls: list[str] = []

    def explode() -> None:
        calls.append("ran")
        raise RuntimeError("boom")

    guarded = scheduler_module._guarded("test_job", explode)
    guarded()  # must not raise
    guarded()
    assert calls == ["ran", "ran"]

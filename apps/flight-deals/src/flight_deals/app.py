"""Composition root: the only place that wires concrete adapters, services, scheduler, web."""

from __future__ import annotations

import logging
from collections.abc import AsyncIterator, Sequence
from contextlib import asynccontextmanager
from dataclasses import dataclass
from pathlib import Path

from fastapi import FastAPI

from flight_deals.config import PROJECT_DIR, Config, ConfigError
from flight_deals.domain.timeutil import utc_now
from flight_deals.notify.telegram import TelegramNotifier
from flight_deals.ports import Clock, FlightPriceSource, Notifier
from flight_deals.redact import redact, register_secret
from flight_deals.scheduler import ScanScheduler
from flight_deals.services import (
    HealthService,
    NotificationService,
    ScanService,
    Services,
    SettingsService,
    ViewService,
    WatchService,
)
from flight_deals.services.settings import EffectiveSettings
from flight_deals.sources._support import Throttle, TTLCache
from flight_deals.sources.fixture import FixtureSource
from flight_deals.sources.google_flights import GoogleFlightsSource
from flight_deals.storage.db import Database
from flight_deals.storage.repository import Repository
from flight_deals.web import create_web_app

log = logging.getLogger(__name__)

DEFAULT_FIXTURE_PATH = PROJECT_DIR / "tests" / "fixtures" / "fixture_roundtrip_TPE_NRT.json"


def build_sources(
    config: Config, *, fixture_path: Path = DEFAULT_FIXTURE_PATH
) -> list[FlightPriceSource]:
    limits = config.limits
    sources: list[FlightPriceSource] = []
    for name in config.sources:
        if name == "google_flights":
            sources.append(
                GoogleFlightsSource(
                    timeout_seconds=limits.source_timeout_seconds,
                    max_attempts=limits.source_max_attempts,
                    backoff_base_seconds=limits.backoff_base_seconds,
                    throttle=Throttle(limits.throttle_min_seconds, limits.throttle_jitter_seconds),
                    cache=TTLCache(limits.cache_ttl_seconds),
                )
            )
        elif name == "fixture":
            sources.append(FixtureSource(fixture_path, cache=TTLCache(limits.cache_ttl_seconds)))
        else:  # pragma: no cover - config already validates names
            raise ConfigError(f"unknown source {name}")
    return sources


@dataclass
class Assembly:
    services: Services
    database: Database
    scheduler: ScanScheduler


def assemble(
    config: Config,
    *,
    sources: Sequence[FlightPriceSource] | None = None,
    notifier: Notifier | None = None,
    clock: Clock = utc_now,
) -> Assembly:
    for secret in config.secrets():
        register_secret(secret)
    database = Database(config.db_path)
    database.migrate()
    repo = Repository(database)
    limits = config.limits
    tunables = config.tunables

    active_sources = list(sources) if sources is not None else build_sources(config)
    channel = notifier or TelegramNotifier(
        config.telegram_bot_token,
        config.telegram_chat_id,
        timeout_seconds=limits.telegram_timeout_seconds,
    )
    settings = SettingsService(
        repo,
        EffectiveSettings(
            scan_interval_minutes=tunables.scan_interval_minutes,
            max_pairs_per_scan=tunables.max_pairs_per_scan,
            drop_threshold_bp=tunables.drop_threshold_bp,
            stale_after_hours=tunables.stale_after_hours,
            global_hourly_query_limit=tunables.global_hourly_query_limit,
        ),
        min_scan_interval_minutes=limits.min_scan_interval_minutes,
        clock=clock,
    )
    health = HealthService(
        repo,
        failure_threshold=limits.breaker_failure_threshold,
        cooldown_minutes=limits.breaker_cooldown_minutes,
        clock=clock,
        redactor=redact,
    )
    health.ensure_sources([s.name for s in active_sources])
    notifications = NotificationService(
        repo,
        channel,
        max_attempts=limits.notification_max_attempts,
        clock=clock,
        redactor=redact,
    )
    scan = ScanService(
        repo,
        active_sources,
        health,
        notifications,
        settings,
        alert_max_items=limits.alert_max_items,
        stale_after_failed_scans=limits.watch_stale_after_failed_scans,
        clock=clock,
        redactor=redact,
    )
    watches = WatchService(repo, clock=clock)
    views = ViewService(
        repo,
        settings,
        health,
        source_names=[s.name for s in active_sources],
        telegram_configured=channel.is_configured(),
        notification_max_attempts=limits.notification_max_attempts,
        breaker_threshold=limits.breaker_failure_threshold,
        clock=clock,
    )
    services = Services(
        watches=watches,
        views=views,
        settings=settings,
        notifications=notifications,
        scan=scan,
        health=health,
    )
    scheduler = ScanScheduler(
        services,
        startup_stagger_seconds=limits.startup_stagger_seconds,
        new_watch_delay_seconds=limits.new_watch_delay_seconds,
        clock=clock,
    )
    watches.hooks.changed = scheduler.on_watch_changed
    watches.hooks.deleted = scheduler.on_watch_deleted
    watches.hooks.trigger_scan = scheduler.trigger_now
    settings.listeners.append(scheduler.on_settings_changed)
    views.hooks.next_run_time = scheduler.next_run_time
    views.hooks.scheduler_running = lambda: scheduler.running
    return Assembly(services, database, scheduler)


def create_app(
    config: Config,
    *,
    sources: Sequence[FlightPriceSource] | None = None,
    notifier: Notifier | None = None,
    clock: Clock = utc_now,
    start_scheduler: bool = True,
) -> FastAPI:
    assembly = assemble(config, sources=sources, notifier=notifier, clock=clock)

    @asynccontextmanager
    async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
        if start_scheduler:
            assembly.scheduler.start()
            log.info("scheduler started")
        try:
            yield
        finally:
            if start_scheduler:
                assembly.scheduler.shutdown()
                log.info("scheduler stopped")

    app = create_web_app(assembly.services, lifespan=lifespan)
    app.state.assembly = assembly
    return app

"""Composition root: the only place that wires concrete adapters, services, scheduler, web."""

from __future__ import annotations

import logging
import sys
from collections.abc import AsyncIterator, Sequence
from contextlib import asynccontextmanager
from dataclasses import dataclass
from pathlib import Path

from fastapi import FastAPI

import flight_deals.autostart as autostart
from flight_deals.config import PROJECT_DIR, Config, ConfigError
from flight_deals.domain.timeutil import utc_now
from flight_deals.notify.telegram import TelegramNotifier, TelegramSetupClient, Transport
from flight_deals.ports import (
    AutostartProbe,
    AutostartStatus,
    BookingLinkBuilder,
    Clock,
    FlightPriceSource,
    Notifier,
)
from flight_deals.redact import redact, register_secret
from flight_deals.scheduler import (
    FileSchedulerLock,
    ScanScheduler,
    SchedulerLock,
    SchedulerLockHeldError,
)
from flight_deals.services import (
    DigestService,
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
from flight_deals.sources.google_flights import GoogleFlightsLinkBuilder, GoogleFlightsSource
from flight_deals.storage.db import Database
from flight_deals.storage.repository import Repository
from flight_deals.web import create_web_app

log = logging.getLogger(__name__)

__all__ = [
    "Assembly",
    "RegistryAutostartProbe",
    "SchedulerLockHeldError",
    "acquire_scheduler_lock",
    "assemble",
    "build_autostart_probe",
    "build_telegram_setup_client",
    "create_app",
    "protect_secret",
    "scheduler_lock_path",
]

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


class RegistryAutostartProbe:
    """Reads the login autostart entry; any failure means "unknown" (None)."""

    def __init__(self, project_dir: Path, registry: autostart.Registry) -> None:
        self._project_dir = project_dir
        self._registry = registry

    def status(self) -> AutostartStatus | None:
        try:
            state = autostart.status(self._project_dir, self._registry)
        except Exception:
            log.debug("autostart state unavailable", exc_info=True)
            return None
        return AutostartStatus(registered=state.registered, points_here=state.points_here)


def build_autostart_probe(project_dir: Path = PROJECT_DIR) -> AutostartProbe | None:
    """Real HKCU probe on Windows only; elsewhere the health page hides the row."""
    if sys.platform != "win32":
        return None
    return RegistryAutostartProbe(project_dir, autostart.WindowsRegistry())


def protect_secret(value: str) -> None:
    """Register a secret for redaction (for callers that may not import ``redact``)."""
    register_secret(value)


def build_telegram_setup_client(
    token: str, *, transport: Transport | None = None
) -> TelegramSetupClient:
    """Factory for ``flight-deals telegram-setup``: the token is registered for redaction
    before any request can produce an error string."""
    register_secret(token)
    return TelegramSetupClient(token, transport=transport)


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
    autostart_probe: AutostartProbe | None = None,
    link_builder: BookingLinkBuilder | None = None,
) -> Assembly:
    for secret in config.secrets():
        register_secret(secret)
    database = Database(config.db_path)
    database.migrate()
    repo = Repository(database)
    limits = config.limits
    tunables = config.tunables
    # Exact Google Flights links (pure tfs encoding, no network; FD-5 Decision 7).
    links = link_builder or GoogleFlightsLinkBuilder()

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
            digest_enabled=tunables.digest_enabled,
            digest_time=tunables.digest_time,
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
        link_builder=links,
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
        autostart=autostart_probe,
        link_builder=links,
    )
    digest = DigestService(
        repo,
        settings,
        health,
        notifications,
        source_names=[s.name for s in active_sources],
        clock=clock,
    )
    services = Services(
        watches=watches,
        views=views,
        settings=settings,
        notifications=notifications,
        scan=scan,
        health=health,
        digest=digest,
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


def scheduler_lock_path(config: Config) -> Path:
    """One scheduler per database: the lock file sits next to it as ``<db>.lock``."""
    db_path = config.db_path
    return db_path.with_name(db_path.name + ".lock")


def acquire_scheduler_lock(config: Config) -> FileSchedulerLock:
    """Take the database's scheduler lock or raise ``SchedulerLockHeldError``."""
    lock = FileSchedulerLock(scheduler_lock_path(config))
    lock.acquire()
    return lock


def create_app(
    config: Config,
    *,
    sources: Sequence[FlightPriceSource] | None = None,
    notifier: Notifier | None = None,
    clock: Clock = utc_now,
    start_scheduler: bool = True,
    scheduler_lock: SchedulerLock | None = None,
    autostart_probe: AutostartProbe | None = None,
    link_builder: BookingLinkBuilder | None = None,
) -> FastAPI:
    """Build the app. With ``start_scheduler`` the scheduler lock is held from here on.

    The lock is taken now (unless the caller already holds it) so a second instance on
    the same database fails before touching it; it is released when the lifespan ends.
    """
    lock: SchedulerLock | None = None
    if start_scheduler:
        lock = scheduler_lock or FileSchedulerLock(scheduler_lock_path(config))
        if not lock.held:
            lock.acquire()  # raises SchedulerLockHeldError
    try:
        assembly = assemble(
            config,
            sources=sources,
            notifier=notifier,
            clock=clock,
            autostart_probe=autostart_probe,
            link_builder=link_builder,
        )
    except BaseException:
        if lock is not None:
            lock.release()
        raise

    @asynccontextmanager
    async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
        try:
            if lock is not None:
                assembly.scheduler.start(lock)
                log.info("scheduler started")
            yield
        finally:
            if lock is not None:
                assembly.scheduler.shutdown()
                lock.release()
                log.info("scheduler stopped")

    app = create_web_app(assembly.services, lifespan=lifespan)
    app.state.assembly = assembly
    app.state.scheduler_lock = lock
    return app

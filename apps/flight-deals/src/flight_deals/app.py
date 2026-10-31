"""Composition root: the only place that wires concrete adapters, services, scheduler, web."""

from __future__ import annotations

import logging
import re
import sys
import threading
from collections.abc import AsyncIterator, Sequence
from contextlib import asynccontextmanager
from dataclasses import dataclass
from datetime import timedelta
from pathlib import Path

from fastapi import FastAPI

import flight_deals.autostart as autostart
from flight_deals.config import PROJECT_DIR, Config, ConfigError
from flight_deals.domain.timeutil import utc_now
from flight_deals.notify.telegram import (
    TelegramCommandClient,
    TelegramNotifier,
    TelegramSetupClient,
    Transport,
)
from flight_deals.ports import (
    AutostartProbe,
    AutostartStatus,
    BookingLinkBuilder,
    Clock,
    FlightPriceSource,
    Notifier,
    TelegramInbox,
)
from flight_deals.redact import redact, register_secret
from flight_deals.scheduler import (
    FileSchedulerLock,
    ScanScheduler,
    SchedulerLock,
    SchedulerLockHeldError,
)
from flight_deals.services import (
    CommandService,
    ComparisonService,
    ComparisonViewService,
    DigestService,
    ExplorationService,
    ExplorationViewService,
    HealthService,
    NotificationService,
    RetentionService,
    ScanService,
    Services,
    SettingsService,
    ViewService,
    WatchService,
)
from flight_deals.services.commands import (
    CommandPoller,
    CommandRuntime,
    PollerTiming,
    bot_id_of,
    parse_chat_id,
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
    "scheduler_lock_holder_pid",
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
    commands: CommandRuntime


def build_command_runtime(
    config: Config,
    *,
    inbox: TelegramInbox | None,
    service: CommandService,
    notifications: NotificationService,
    repo: Repository,
    settings: SettingsService,
    clock: Clock,
) -> CommandRuntime:
    """A poller only with a bot token and a private (positive integer) chat id."""
    token = config.telegram_bot_token
    chat_id, unavailable = parse_chat_id(config.telegram_chat_id)
    if not token:
        unavailable = "unconfigured"
    if unavailable is not None or chat_id is None or not token:
        return CommandRuntime(None, unavailable or "unconfigured")
    register_secret(token)  # before any request can produce an error string
    limits = config.limits
    poller = CommandPoller(
        inbox or TelegramCommandClient(token),
        service,
        notifications,
        repo,
        settings,
        bot_id=bot_id_of(token),
        chat_id=chat_id,
        clock=clock,
        redactor=redact,
        timing=PollerTiming(
            long_poll_seconds=limits.command_long_poll_seconds,
            backlog=timedelta(minutes=limits.command_backlog_minutes),
        ),
    )
    return CommandRuntime(poller)


def assemble(
    config: Config,
    *,
    sources: Sequence[FlightPriceSource] | None = None,
    notifier: Notifier | None = None,
    clock: Clock = utc_now,
    autostart_probe: AutostartProbe | None = None,
    link_builder: BookingLinkBuilder | None = None,
    inbox: TelegramInbox | None = None,
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
            exploration_reserve_for_scans=tunables.exploration_reserve_for_scans,
            retention_days=tunables.retention_days,
            notification_retention_days=tunables.notification_retention_days,
            retention_keep_runs=tunables.retention_keep_runs,
            telegram_commands_enabled=tunables.telegram_commands_enabled,
            vacuum_enabled=tunables.vacuum_enabled,
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
        no_embedded_min_queries=limits.no_embedded_min_queries,
        no_embedded_min_ratio_pct=limits.no_embedded_min_ratio_pct,
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
        no_embedded_streak_rounds=limits.no_embedded_streak_rounds,
    )
    digest = DigestService(
        repo,
        settings,
        health,
        notifications,
        source_names=[s.name for s in active_sources],
        clock=clock,
    )
    # One create lock for explorations and comparisons: one batch at a time (FD-9).
    batch_create_lock = threading.Lock()
    # Same source objects (cache, throttle) and scan lock as the scans (FD-6 Decision 3).
    exploration = ExplorationService(
        repo,
        scan.sources,
        health,
        notifications,
        settings,
        scan_lock=scan.lock,
        max_cells=limits.exploration_max_cells,
        reuse_hours=limits.exploration_reuse_hours,
        retention_days=limits.exploration_retention_days,
        clock=clock,
        redactor=redact,
        create_lock=batch_create_lock,
    )
    exploration_views = ExplorationViewService(
        repo, settings, exploration, clock=clock, link_builder=links
    )
    # Comparisons share the sources, scan lock, reuse and retention periods (FD-9).
    comparison = ComparisonService(
        repo,
        scan.sources,
        health,
        notifications,
        settings,
        scan_lock=scan.lock,
        create_lock=batch_create_lock,
        reuse_hours=limits.exploration_reuse_hours,
        retention_days=limits.exploration_retention_days,
        clock=clock,
        redactor=redact,
    )
    comparison_views = ComparisonViewService(
        repo, settings, comparison, clock=clock, link_builder=links
    )
    commands = CommandService(
        repo,
        watches,
        settings,
        health,
        notifications,
        source_names=[s.name for s in active_sources],
        clock=clock,
        link_builder=links,
    )
    command_runtime = build_command_runtime(
        config,
        inbox=inbox,
        service=commands,
        notifications=notifications,
        repo=repo,
        settings=settings,
        clock=clock,
    )
    retention = RetentionService(
        repo,
        settings,
        scan_lock=scan.lock,
        clock=clock,
        redactor=redact,
        backups_keep=limits.retention_backups_keep,
        delay_minutes=limits.retention_delay_minutes,
        batch_size=limits.retention_batch_size,
        vacuum_interval_days=limits.vacuum_interval_days,
        stats_cache_seconds=limits.stats_cache_seconds,
    )
    services = Services(
        watches=watches,
        views=views,
        settings=settings,
        notifications=notifications,
        scan=scan,
        health=health,
        digest=digest,
        exploration=exploration,
        exploration_views=exploration_views,
        comparison=comparison,
        comparison_views=comparison_views,
        commands=commands,
        retention=retention,
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
    exploration.hooks.schedule = scheduler.schedule_exploration
    exploration.hooks.scheduler_running = lambda: scheduler.running
    comparison.hooks.schedule = scheduler.schedule_comparison
    comparison.hooks.scheduler_running = lambda: scheduler.running
    commands.hooks.schedule_scan = scheduler.trigger_command_scan
    commands.hooks.scan_pending = scheduler.scan_pending
    commands.hooks.schedule_manual_digest = scheduler.schedule_manual_digest
    commands.hooks.next_run_time = scheduler.next_run_time
    commands.hooks.scheduler_running = lambda: scheduler.running
    views.hooks.command_status = command_runtime.status
    views.retention = retention
    poller = command_runtime.poller
    if poller is not None:

        def wake_poller(before: EffectiveSettings, after: EffectiveSettings) -> None:
            if before.telegram_commands_enabled != after.telegram_commands_enabled:
                poller.wake()

        settings.listeners.append(wake_poller)
    return Assembly(services, database, scheduler, command_runtime)


def scheduler_lock_path(config: Config) -> Path:
    """One scheduler per database: the lock file sits next to it as ``<db>.lock``."""
    db_path = config.db_path
    return db_path.with_name(db_path.name + ".lock")


_HOLDER_PID = re.compile(r"pid=(\d{1,10}) started_at=\S+")


def scheduler_lock_holder_pid(config: Config) -> int | None:
    """PID written in the lock file header by its holder, or None when the header is
    missing or unreadable (display data: the caller must still take the lock)."""
    info = FileSchedulerLock(scheduler_lock_path(config)).holder_info()
    match = _HOLDER_PID.match(info or "")
    return int(match.group(1)) if match else None


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
    inbox: TelegramInbox | None = None,
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
            inbox=inbox,
        )
    except BaseException:
        if lock is not None:
            lock.release()
        raise

    @asynccontextmanager
    async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
        poller = assembly.commands.poller
        try:
            if lock is not None:
                assembly.scheduler.start(lock)
                log.info("scheduler started")
                # Only the lock holder polls Telegram (FD-7 Decision 1).
                if poller is not None:
                    poller.start()
                    log.info("telegram command polling started")
            yield
        finally:
            if lock is not None:
                if poller is not None and poller.started:
                    poller.stop()
                assembly.scheduler.shutdown()
                lock.release()
                log.info("scheduler stopped")

    app = create_web_app(assembly.services, lifespan=lifespan)
    app.state.assembly = assembly
    app.state.scheduler_lock = lock
    return app

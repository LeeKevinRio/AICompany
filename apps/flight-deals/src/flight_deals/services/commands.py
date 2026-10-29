"""Telegram two-way commands (ADR-0002 FD-7 Decisions 1-5, C-49..C-51).

``CommandService`` turns one parsed command into one reply; it only reads through the
same read models as the web pages (snapshot, latest pair, source state) and its only
writes are ``/pause`` / ``/resume`` (watch status, through ``WatchService``) plus queuing
``/scan`` and ``/digest`` through callables wired by ``app.py``.

``CommandPoller`` is a daemon thread that long-polls ``TelegramInbox``. It never runs on
the scheduler worker, never raises, and executes each update at most once: the update
is claimed with a ``cmd:<bot_id>:<update_id>`` notification row before it runs, and the
next offset is stored only after the reply. This module does not import the scheduler,
the Telegram adapter or httpx.
"""

from __future__ import annotations

import logging
import threading
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any, Literal

from flight_deals.domain.airports import route_label
from flight_deals.domain.commands import (
    MAX_COMMAND_CHARS,
    ParsedCommand,
    normalise,
    parse_command,
)
from flight_deals.domain.currency import format_money
from flight_deals.domain.dates import is_expired
from flight_deals.domain.links import google_flights_url
from flight_deals.domain.messages import (
    COMMAND_DIGEST_QUEUED,
    COMMAND_FAILED,
    COMMAND_HELP,
    COMMAND_NOT_TEXT,
    COMMAND_SCAN_DEFERRED,
    COMMAND_SCAN_EXPIRED,
    COMMAND_SCAN_FOLLOW_UP,
    COMMAND_SCAN_PAUSED,
    COMMAND_SCAN_PENDING,
    COMMAND_SCHEDULER_OFF,
    COMMAND_TOO_LONG,
    COMMAND_TOP_N,
    COMMAND_UNKNOWN,
    SCAN_FAILURE_REASONS,
    CommandExplorationStatus,
    CommandPriceRow,
    CommandRunSummary,
    CommandScanResult,
    CommandSourceStatus,
    CommandStatus,
    CommandWatchDetail,
    CommandWatchLine,
    command_already_active,
    command_already_paused,
    command_backlog,
    command_list_message,
    command_not_found,
    command_pause_expired,
    command_paused,
    command_quota_exhausted,
    command_resume_expired,
    command_resumed,
    command_scan_queued,
    command_scan_result_message,
    command_status_message,
    command_usage,
    command_watch_message,
)
from flight_deals.domain.models import SCANNABLE_STATUSES, DatePair, Watch, search_for
from flight_deals.domain.timeutil import taipei_date
from flight_deals.domain.trip_labels import (
    BOOKING_FALLBACK_NOTE,
    airlines_text,
    dep_window_label,
)
from flight_deals.ports import BookingLinkBuilder, Clock, InboundUpdate, Redactor, TelegramInbox
from flight_deals.services.digest import taipei_midnight
from flight_deals.services.health import HealthService, describe_source
from flight_deals.services.notifications import NotificationService, safe_booking_url
from flight_deals.services.price_snapshot import Snapshot, cheapest_pairs
from flight_deals.services.scan import ScanOutcome
from flight_deals.services.settings import SettingsService
from flight_deals.services.views import BREAKER_LABELS, SKIP_REASON_LABELS, dates_text
from flight_deals.services.watches import WatchService
from flight_deals.storage.repository import ObservationRecord, Repository, ScanRunRecord

log = logging.getLogger(__name__)

HOUR = timedelta(hours=1)
# A "running" scan row older than this is a leftover of a crash, not a scan in progress.
RUNNING_SCAN_MAX_AGE = timedelta(hours=1)
OFFSET_KEY = "state.telegram_update_offset"
OFFSET_BOT_KEY = "state.telegram_offset_bot_id"
NON_TEXT_LABEL = "（非文字訊息）"
BACKLOG_LABEL = "（停機期間的指令）"


def _no_scan(_watch_id: int) -> None:
    return None


def _not_pending(_watch_id: int) -> bool:
    return False


def _no_digest(_update_id: int, _key: str) -> None:
    return None


def _no_time() -> datetime | None:
    return None


def _not_running() -> bool:
    return False


@dataclass
class CommandHooks:
    """Set by ``app.py`` so services never import the scheduler."""

    schedule_scan: Callable[[int], None] = _no_scan
    scan_pending: Callable[[int], bool] = _not_pending
    schedule_manual_digest: Callable[[int, str], None] = _no_digest
    next_run_time: Callable[[], datetime | None] = _no_time
    scheduler_running: Callable[[], bool] = _not_running


@dataclass(frozen=True)
class CommandContext:
    """Which update a command came from (keys for its follow-up records)."""

    update_id: int
    bot_id: str


@dataclass(frozen=True)
class CommandReply:
    text: str
    ok: bool = True


def scan_skip_notes(query_results: Sequence[Mapping[str, Any]]) -> tuple[str, ...]:
    """Skipped pairs by reason plus unpriced itineraries, in the detail page's wording."""
    skipped: dict[str, int] = {}
    unpriced = 0
    for entry in query_results:
        if entry.get("status") == "skipped":
            label = SKIP_REASON_LABELS.get(str(entry.get("reason")), "未查")
            skipped[label] = skipped.get(label, 0) + 1
        tries = entry.get("tries") or []
        last = tries[-1] if tries and isinstance(tries[-1], Mapping) else {}
        value = last.get("unpriced")
        if isinstance(value, int) and not isinstance(value, bool) and value > 0:
            unpriced += value
    notes = [f"{label} {count} 組日期" for label, count in skipped.items()]
    if unpriced:
        notes.append(f"略過 {unpriced} 筆無價格航班")
    return tuple(notes)


def scan_failure_reason(run: ScanRunRecord, currency: str) -> str | None:
    """Factual reason when a finished run priced nothing in the watch currency."""
    results = run.query_results
    if any(
        r.get("status") == "ok" and r.get("currency") == currency and r.get("amount_minor")
        for r in results
    ):
        return None
    seen = {str(r.get("reason")) for r in results if r.get("reason")}
    seen |= {str(r.get("status")) for r in results if r.get("status")}
    for key in (
        "global_hourly_limit",
        "breaker_open",
        "blocked",
        "error",
        "no_embedded_results",
        "no_data",
        "currency_mismatch",
    ):
        if key in seen:
            return SCAN_FAILURE_REASONS[key]
    return SCAN_FAILURE_REASONS["no_data"] if results else None


def max_stops_text(max_stops: int | None) -> str:
    if max_stops is None:
        return "不限"
    return "僅直飛" if max_stops == 0 else f"最多轉機 {max_stops} 次"


class CommandService:
    def __init__(
        self,
        repo: Repository,
        watches: WatchService,
        settings: SettingsService,
        health: HealthService,
        notifications: NotificationService,
        *,
        source_names: Sequence[str],
        clock: Clock,
        link_builder: BookingLinkBuilder | None = None,
    ) -> None:
        self._repo = repo
        self._watches = watches
        self._settings = settings
        self._health = health
        self._notifications = notifications
        self._source_names = list(source_names)
        self._clock = clock
        self._links = link_builder
        self.hooks = CommandHooks()
        # watch id -> (update id, bot id) of a /scan waiting for its result (memory only).
        self._pending: dict[int, tuple[int, str]] = {}
        self._pending_lock = threading.Lock()

    # ---- entry points ----------------------------------------------------------

    def handle_text(self, text: str | None, now: datetime, context: CommandContext) -> CommandReply:
        if text is None:
            return CommandReply(COMMAND_NOT_TEXT)
        return self.handle(parse_command(text), now, context)

    def handle(self, cmd: ParsedCommand, now: datetime, context: CommandContext) -> CommandReply:
        if cmd.status == "too_long":
            return CommandReply(COMMAND_TOO_LONG)
        if cmd.status in ("not_command", "unknown") or cmd.name is None:
            return CommandReply(COMMAND_UNKNOWN)
        if cmd.status in ("missing_arg", "bad_arg"):
            return CommandReply(command_usage(cmd.name))
        name = cmd.name
        if name in ("help", "start"):
            return CommandReply(COMMAND_HELP)
        if name == "list":
            return CommandReply(self.list_text(now))
        if name == "status":
            return CommandReply(self.status_text(now))
        if name == "digest":
            return self._digest(context)
        watch_id = cmd.watch_id
        assert watch_id is not None  # parse_command guarantees it for id commands
        watch = self._repo.get_watch(watch_id)
        if watch is None:
            return CommandReply(command_not_found(watch_id))
        if name == "watch":
            return CommandReply(self.watch_text(watch, now))
        if name == "scan":
            return self._scan(watch, now, context)
        if name == "pause":
            return self._set_enabled(watch, enabled=False, now=now)
        return self._set_enabled(watch, enabled=True, now=now)

    def on_scan_finished(self, watch_id: int, outcome: ScanOutcome) -> None:
        """Called on the worker after a ``cmdscan:<id>`` job: one result message."""
        with self._pending_lock:
            pending = self._pending.pop(watch_id, None)
        if pending is None:
            return
        update_id, bot_id = pending
        try:
            text = self.scan_result_text(watch_id, outcome)
            self._notifications.send_command_message(
                f"cmd:{bot_id}:{update_id}:result",
                f"/scan {watch_id}（查價結果）",
                text,
                watch_id=watch_id if self._repo.get_watch(watch_id) else None,
            )
        except Exception as exc:  # never let a reply break the scheduler worker
            log.warning("scan result reply for watch %s failed: %s", watch_id, type(exc).__name__)

    def forget_scan(self, watch_id: int) -> None:
        """A deleted watch drops its pending ``/scan`` result."""
        with self._pending_lock:
            self._pending.pop(watch_id, None)

    def pending_scans(self) -> dict[int, tuple[int, str]]:
        with self._pending_lock:
            return dict(self._pending)

    # ---- read models -------------------------------------------------------------

    def _current_snapshot_rows(self, watch: Watch, now: datetime) -> list[ObservationRecord]:
        """Only the rows a snapshot reads (ADR-0002 FD-8 Decision 1); one SQL query."""
        return self._repo.snapshot_observations_for_watch(
            watch.id,
            revision=watch.revision,
            currency=watch.spec.currency,
            today=taipei_date(now),
            midnight=taipei_midnight(now),
        )

    def _snapshot(self, watch: Watch, now: datetime) -> Snapshot:
        return Snapshot.build(
            self._current_snapshot_rows(watch, now),
            revision=watch.revision,
            currency=watch.spec.currency,
            today=taipei_date(now),
        )

    def _stale(self, fetched_at: datetime, now: datetime, hours: int) -> bool:
        return now - fetched_at > timedelta(hours=hours)

    def list_text(self, now: datetime) -> str:
        stale_hours = self._settings.current().stale_after_hours
        rows: list[CommandWatchLine] = []
        paused: list[int] = []
        expired: list[int] = []
        for watch in self._repo.list_watches():
            if watch.status == "paused":
                paused.append(watch.id)
                continue
            if watch.status == "expired":
                expired.append(watch.id)
                continue
            snapshot = self._snapshot(watch, now)
            cheapest = snapshot.cheapest
            delta = snapshot.delta_since_previous_run()
            spec = watch.spec
            rows.append(
                CommandWatchLine(
                    watch_id=watch.id,
                    name=spec.name,
                    origin=spec.origin,
                    destination=spec.destination,
                    currency=cheapest.currency if cheapest else spec.currency,
                    adults=spec.adults,
                    children=spec.children,
                    cabin=spec.cabin,
                    amount_minor=cheapest.amount_minor if cheapest else None,
                    depart_date=cheapest.depart_date if cheapest else None,
                    return_date=cheapest.return_date if cheapest else None,
                    delta_direction=delta.direction if delta else None,
                    delta_minor=delta.delta_minor if delta else None,
                    last_scanned_at=watch.last_scanned_at,
                    data_stale=bool(
                        cheapest and self._stale(cheapest.fetched_at, now, stale_hours)
                    ),
                    watch_stale=watch.status == "stale",
                )
            )
        return command_list_message(rows, paused, expired, stale_hours)

    def _booking(self, watch: Watch, pair: DatePair) -> tuple[str, str | None]:
        spec = watch.spec
        url = safe_booking_url(self._links, search_for(spec, pair, spec.currency))
        if url:
            return url, None
        fallback = google_flights_url(spec.origin, spec.destination, pair.depart, pair.return_date)
        return fallback, BOOKING_FALLBACK_NOTE

    def top_prices(self, watch: Watch, now: datetime) -> list[CommandPriceRow]:
        """The detail page's ``top`` ranking (``cheapest_pairs``: live, watch currency,
        not departed, newest per pair, cheapest first), first three."""
        current = self._current_snapshot_rows(watch, now)
        ranked = cheapest_pairs(
            current, revision=watch.revision, currency=watch.spec.currency, today=taipei_date(now)
        )
        stale_hours = self._settings.current().stale_after_hours
        rows = []
        for obs in ranked[:COMMAND_TOP_N]:
            url, note = self._booking(watch, DatePair(obs.depart_date, obs.return_date))
            rows.append(
                CommandPriceRow(
                    depart_date=obs.depart_date,
                    return_date=obs.return_date,
                    amount_minor=obs.amount_minor,
                    currency=obs.currency,
                    carrier=obs.carrier,
                    stops=obs.stops,
                    booking_url=url,
                    booking_note=note,
                    fetched_at=obs.fetched_at,
                    data_stale=self._stale(obs.fetched_at, now, stale_hours),
                )
            )
        return rows

    def watch_text(self, watch: Watch, now: datetime) -> str:
        spec = watch.spec
        run = self._repo.latest_finished_scan_run(watch.id)
        summary = (
            CommandRunSummary(
                finished_at=run.finished_at,
                status=run.status,
                sampled=len(run.sampled_pairs),
                queries_used=run.queries_used,
                skip_notes=scan_skip_notes(run.query_results),
            )
            if run
            else None
        )
        detail = CommandWatchDetail(
            watch_id=watch.id,
            name=spec.name,
            status=watch.status,
            origin=spec.origin,
            destination=spec.destination,
            trip_type=spec.trip_type,
            dates=dates_text(spec),
            adults=spec.adults,
            children=spec.children,
            cabin=spec.cabin,
            airlines=airlines_text(spec.airlines),
            dep_window=dep_window_label(spec.dep_hour_from, spec.dep_hour_to),
            max_stops=max_stops_text(spec.max_stops),
            budget=(
                format_money(spec.budget_amount_minor, spec.currency)
                if spec.budget_amount_minor
                else "未設定"
            ),
            prices=tuple(self.top_prices(watch, now)),
            last_run=summary,
            stale_after_hours=self._settings.current().stale_after_hours,
        )
        return command_watch_message(detail)

    def status_text(self, now: datetime) -> str:
        settings = self._settings.current()
        known = {r.source: r for r in self._health.records()}
        sources = []
        for name in self._source_names:
            record = known.get(name)
            label, _key = describe_source(record)
            sources.append(
                CommandSourceStatus(
                    source=name,
                    state_label=label,
                    breaker_label=BREAKER_LABELS.get(record.breaker_state, "—")
                    if record
                    else BREAKER_LABELS["closed"],
                    last_failure_at=record.last_failure_at if record else None,
                )
            )
        active = self._repo.active_exploration()
        exploration = None
        if active is not None:
            spec = active.spec
            exploration = CommandExplorationStatus(
                origin=spec.origin,
                destination=spec.destination,
                trip_type=spec.trip_type,
                year=spec.year,
                month=spec.month,
                trip_days=spec.trip_days,
                done=active.done,
                total=active.total,
            )
        status = CommandStatus(
            now=now,
            sources=tuple(sources),
            hourly_used=self._repo.queries_used_since(now - HOUR),
            hourly_limit=settings.global_hourly_query_limit,
            scheduler_running=self.hooks.scheduler_running(),
            next_scan_at=self.hooks.next_run_time(),
            exploration=exploration,
        )
        return command_status_message(status)

    def scan_result_text(self, watch_id: int, outcome: ScanOutcome) -> str:
        watch = self._repo.get_watch(watch_id)
        now = self._clock()
        run = self._repo.get_scan_run(outcome.scan_run_id) if outcome.scan_run_id else None
        if watch is None:
            spec_name, currency, adults, children = "", "TWD", 1, 0
            cheapest = delta = None
        else:
            spec = watch.spec
            spec_name, currency = spec.name, spec.currency
            adults, children = spec.adults, spec.children
            snapshot = self._snapshot(watch, now)
            cheapest = snapshot.cheapest
            delta = snapshot.delta_since_previous_run()
        if run is None or run.finished_at is None:
            run_status = None
            reason = SCAN_FAILURE_REASONS.get(outcome.status)
        else:
            run_status = run.status
            reason = scan_failure_reason(run, currency)
        # A failed / partial (or missing) run may leave an older price as the lowest.
        carried_over = bool(
            cheapest
            and (run is None or run_status in ("failed", "partial"))
            and (run is None or cheapest.scan_run_id != run.id)
        )
        stale_hours = self._settings.current().stale_after_hours
        result = CommandScanResult(
            watch_id=watch_id,
            name=spec_name,
            currency=cheapest.currency if cheapest else currency,
            adults=adults,
            children=children,
            run_status=run_status,
            failure_reason=reason,
            amount_minor=cheapest.amount_minor if cheapest else None,
            depart_date=cheapest.depart_date if cheapest else None,
            return_date=cheapest.return_date if cheapest else None,
            delta_direction=delta.direction if delta else None,
            delta_minor=delta.delta_minor if delta else None,
            sampled=len(run.sampled_pairs) if run else 0,
            queries_used=run.queries_used if run else 0,
            skip_notes=scan_skip_notes(run.query_results) if run else (),
            fetched_at=cheapest.fetched_at if cheapest else None,
            data_stale=bool(cheapest and self._stale(cheapest.fetched_at, now, stale_hours)),
            carried_over=carried_over,
            stale_after_hours=stale_hours,
        )
        return command_scan_result_message(result)

    # ---- actions -------------------------------------------------------------------

    def _scan_running(self, watch_id: int, now: datetime) -> bool:
        if self.hooks.scan_pending(watch_id):
            return True
        with self._pending_lock:
            if watch_id in self._pending:
                return True
        run = self._repo.latest_scan_run_for_watch(watch_id)
        return bool(
            run is not None
            and run.status == "running"
            and now - run.started_at < RUNNING_SCAN_MAX_AGE
        )

    def _scan(self, watch: Watch, now: datetime, context: CommandContext) -> CommandReply:
        if watch.status == "paused":
            return CommandReply(COMMAND_SCAN_PAUSED)
        if watch.status == "expired" or is_expired(watch.spec, taipei_date(now)):
            return CommandReply(COMMAND_SCAN_EXPIRED)
        if watch.status not in SCANNABLE_STATUSES:  # pragma: no cover - defensive
            return CommandReply(COMMAND_SCAN_PAUSED)
        if not self.hooks.scheduler_running():
            return CommandReply(COMMAND_SCHEDULER_OFF)
        limit = self._settings.current().global_hourly_query_limit
        used = self._repo.queries_used_since(now - HOUR)
        if limit - used <= 0:
            return CommandReply(command_quota_exhausted(used, limit))
        if self._scan_running(watch.id, now):
            return CommandReply(COMMAND_SCAN_PENDING)
        deferred = self._repo.active_exploration() is not None
        with self._pending_lock:
            self._pending[watch.id] = (context.update_id, context.bot_id)
        try:
            self.hooks.schedule_scan(watch.id)
        except Exception:
            with self._pending_lock:
                self._pending.pop(watch.id, None)
            raise
        lines = [command_scan_queued(watch.id, watch.spec.name)]
        if deferred:
            lines.append(COMMAND_SCAN_DEFERRED)
        lines.append(COMMAND_SCAN_FOLLOW_UP)
        return CommandReply("\n".join(lines))

    def _digest(self, context: CommandContext) -> CommandReply:
        if not self.hooks.scheduler_running():
            return CommandReply(COMMAND_SCHEDULER_OFF)
        key = f"digest-manual:{context.bot_id}:{context.update_id}"
        self.hooks.schedule_manual_digest(context.update_id, key)
        return CommandReply(COMMAND_DIGEST_QUEUED)

    def _set_enabled(self, watch: Watch, *, enabled: bool, now: datetime) -> CommandReply:
        expired = watch.status == "expired" or is_expired(watch.spec, taipei_date(now))
        route = route_label(watch.spec.origin, watch.spec.destination)
        if not enabled:
            if watch.status == "paused":
                return CommandReply(command_already_paused(watch.id))
            if watch.status == "expired":
                return CommandReply(command_pause_expired(watch.id))
        else:
            if expired:
                return CommandReply(command_resume_expired(watch.id))
            if watch.status in SCANNABLE_STATUSES:
                return CommandReply(command_already_active(watch.id))
        result = self._watches.set_enabled(watch.id, enabled)
        if not result.ok:
            return CommandReply(
                command_resume_expired(watch.id) if enabled else COMMAND_FAILED, ok=False
            )
        return CommandReply(
            command_resumed(watch.id, route) if enabled else command_paused(watch.id, route)
        )


# ---- poller --------------------------------------------------------------------------

PollerUnavailable = Literal["unconfigured", "group_chat", "invalid_chat"]


@dataclass(frozen=True)
class PollerStatus:
    """Raw poller state for the health page (labels are composed by the views)."""

    unavailable: PollerUnavailable | None
    started: bool
    unauthorized: bool
    failing: bool
    last_command_at: datetime | None
    last_error_at: datetime | None
    last_error: str | None
    ignored_count: int


@dataclass(frozen=True)
class PollerTiming:
    long_poll_seconds: int = 25
    disabled_wait_seconds: float = 30.0
    backoff_min_seconds: float = 2.0
    backoff_max_seconds: float = 300.0
    conflict_wait_seconds: float = 60.0
    backlog: timedelta = timedelta(minutes=10)
    stop_lock_seconds: float = 5.0
    stop_join_seconds: float = 1.0


def bot_id_of(token: str) -> str:
    """The public numeric bot id before the token's colon ("0" if it has none)."""
    head = token.split(":", 1)[0].strip()
    return head if head.isdigit() else "0"


def parse_chat_id(raw: str | None) -> tuple[int | None, PollerUnavailable | None]:
    """Commands only run for a private chat: a positive integer chat id."""
    if not raw:
        return None, "unconfigured"
    text = raw.strip()
    try:
        value = int(text)
    except ValueError:
        return None, "invalid_chat"
    if value < 0:
        return None, "group_chat"
    if value == 0:
        return None, "invalid_chat"
    return value, None


@dataclass
class _Counters:
    ignored: int = 0
    failures: int = 0
    last_command_at: datetime | None = None
    last_error_at: datetime | None = None
    last_error: str | None = None
    unauthorized: bool = False


class CommandPoller:
    """Background long polling of the bot (FD-7 Decision 1). ``poll_once`` is one step."""

    def __init__(
        self,
        inbox: TelegramInbox,
        service: CommandService,
        notifications: NotificationService,
        repo: Repository,
        settings: SettingsService,
        *,
        bot_id: str,
        chat_id: int,
        clock: Clock,
        redactor: Redactor,
        timing: PollerTiming | None = None,
    ) -> None:
        self._inbox = inbox
        self._service = service
        self._notifications = notifications
        self._repo = repo
        self._settings = settings
        self._bot_id = bot_id
        self._chat_id = chat_id
        self._clock = clock
        self._redact = redactor
        self._timing = timing or PollerTiming()
        self._stop = threading.Event()
        self._wake = threading.Event()
        self._processing = threading.Lock()
        self._state_lock = threading.Lock()
        self._counters = _Counters()
        self._offset: int | None = None
        self._offset_loaded = False
        self._thread: threading.Thread | None = None

    # ---- lifecycle -----------------------------------------------------------------

    def start(self) -> None:
        if self._thread is not None:
            return
        self._stop.clear()
        self._thread = threading.Thread(target=self._run, name="telegram-commands", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        """Signal, wait (bounded) for the update being handled, then join briefly."""
        self._stop.set()
        self._wake.set()
        if self._processing.acquire(timeout=self._timing.stop_lock_seconds):
            self._processing.release()
        thread = self._thread
        if thread is not None:
            thread.join(self._timing.stop_join_seconds)

    def wake(self) -> None:
        """Re-check the on/off switch now (called when the setting changes)."""
        self._wake.set()

    @property
    def started(self) -> bool:
        return self._thread is not None

    @property
    def stopped(self) -> bool:
        return self._stop.is_set()

    def status(self) -> PollerStatus:
        with self._state_lock:
            counters = _Counters(**vars(self._counters))
        return PollerStatus(
            unavailable=None,
            started=self._thread is not None,
            unauthorized=counters.unauthorized,
            failing=counters.failures > 0,
            last_command_at=counters.last_command_at,
            last_error_at=counters.last_error_at,
            last_error=counters.last_error,
            ignored_count=counters.ignored,
        )

    def _run(self) -> None:
        while not self._stop.is_set():
            delay = self.poll_once()
            if delay < 0:
                return
            if delay > 0:
                self._wake.wait(delay)
                self._wake.clear()

    # ---- one step ----------------------------------------------------------------

    def _enabled(self) -> bool:
        return self._settings.current().telegram_commands_enabled

    def poll_once(self) -> float:
        """One long poll and its batch. Returns seconds to wait (negative: stop)."""
        if self._stop.is_set():
            return -1
        with self._state_lock:
            if self._counters.unauthorized:
                return -1
        try:
            if not self._enabled():
                return self._timing.disabled_wait_seconds
            offset = self._load_offset()
            result = self._inbox.get_updates(offset, self._timing.long_poll_seconds)
            with self._processing:
                if self._stop.is_set():
                    return -1
                if not result.ok:
                    return self._on_error(
                        result.error_kind, result.error, result.retry_after_seconds
                    )
                with self._state_lock:
                    self._counters.failures = 0
                if not self._enabled():
                    return 0  # switched off while polling: drop the batch, keep the offset
                self._handle_batch(result.updates)
            return 0
        except Exception as exc:  # the thread must survive anything (C-49)
            return self._on_error("network", f"內部錯誤：{type(exc).__name__}", None)

    def _on_error(self, kind: str | None, error: str | None, retry_after: int | None) -> float:
        message = self._redact(error or "未知錯誤")[:300]
        with self._state_lock:
            counters = self._counters
            counters.last_error_at = self._clock()
            counters.last_error = message
            if kind == "unauthorized":
                counters.unauthorized = True
                counters.failures += 1
                log.warning("telegram command polling stopped: %s", message)
                return -1
            counters.failures += 1
            failures = counters.failures
        log.warning("telegram command polling failed (%d): %s", failures, message)
        timing = self._timing
        if kind == "conflict":
            return timing.conflict_wait_seconds
        factor = 1 << min(failures - 1, 20)
        delay = min(timing.backoff_min_seconds * factor, timing.backoff_max_seconds)
        if kind == "rate_limited" and retry_after is not None:
            delay = max(delay, float(retry_after))  # Telegram's retry_after is a floor
        return delay

    # ---- offset (FD-7 Decision 2) ------------------------------------------------

    def _load_offset(self) -> int | None:
        if self._offset_loaded:
            return self._offset
        state = self._repo.get_state([OFFSET_KEY, OFFSET_BOT_KEY])
        offset: int | None = None
        if state.get(OFFSET_BOT_KEY) == self._bot_id:
            raw = state.get(OFFSET_KEY, "")
            offset = int(raw) if raw.isdigit() else None
        self._offset, self._offset_loaded = offset, True
        return offset

    def _save_offset(self, next_offset: int) -> None:
        if self._offset is not None and next_offset <= self._offset:
            return
        self._repo.save_state(
            {OFFSET_KEY: str(next_offset), OFFSET_BOT_KEY: self._bot_id}, self._clock()
        )
        self._offset = next_offset

    # ---- batch -----------------------------------------------------------------

    def _authorized(self, update: InboundUpdate) -> bool:
        return (
            update.kind == "message"
            and update.chat_type == "private"
            and update.chat_id == self._chat_id
        )

    def _own_edit(self, update: InboundUpdate) -> bool:
        return (
            update.kind == "edited_message"
            and update.chat_type == "private"
            and update.chat_id == self._chat_id
        )

    def _handle_batch(self, updates: Sequence[InboundUpdate]) -> None:
        now = self._clock()
        cutoff = now - self._timing.backlog
        backlog = 0
        backlog_max: int | None = None
        for update in sorted(updates, key=lambda u: u.update_id):
            if self._stop.is_set():
                return
            if self._own_edit(update):
                # The owner's edited message: not run, not answered, not counted as foreign.
                self._save_offset(update.update_id + 1)
                continue
            if not self._authorized(update):
                # Never stored, logged or answered: only counted (C-50).
                with self._state_lock:
                    self._counters.ignored += 1
                self._save_offset(update.update_id + 1)
                continue
            if update.sent_at is not None and update.sent_at < cutoff:
                backlog += 1
                backlog_max = update.update_id
                self._save_offset(update.update_id + 1)
                continue
            self._process(update, now)
            self._save_offset(update.update_id + 1)
        if backlog and backlog_max is not None and not self._stop.is_set():
            self._notifications.send_command_message(
                f"cmd-backlog:{self._bot_id}:{backlog_max}",
                BACKLOG_LABEL,
                command_backlog(backlog, int(self._timing.backlog.total_seconds() // 60)),
            )

    def _process(self, update: InboundUpdate, now: datetime) -> None:
        # Redact before cutting, so a secret can never survive half-cut (C-50).
        text = normalise(update.text) if update.text is not None else ""
        shown = self._redact(text)[:MAX_COMMAND_CHARS] or NON_TEXT_LABEL
        notification_id = self._notifications.claim_command(
            f"cmd:{self._bot_id}:{update.update_id}", shown
        )
        if notification_id is None:
            return  # handled before a restart: never executed twice (FR-P4)
        with self._state_lock:
            self._counters.last_command_at = now
        context = CommandContext(update.update_id, self._bot_id)
        try:
            reply = self._service.handle_text(update.text, now, context)
        except Exception as exc:
            log.warning("telegram command %s failed: %s", update.update_id, type(exc).__name__)
            reply = CommandReply(COMMAND_FAILED, ok=False)
        self._notifications.finish_command(notification_id, shown, reply.text)


@dataclass
class CommandRuntime:
    """What the health page needs about commands, whether or not a poller exists."""

    poller: CommandPoller | None
    unavailable: PollerUnavailable | None = None

    def status(self) -> PollerStatus:
        if self.poller is not None:
            return self.poller.status()
        return PollerStatus(
            unavailable=self.unavailable,
            started=False,
            unauthorized=False,
            failing=False,
            last_command_at=None,
            last_error_at=None,
            last_error=None,
            ignored_count=0,
        )

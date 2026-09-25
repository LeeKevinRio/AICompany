"""Background scheduler: data refresh, alert evaluation and the sector card's batch.

Runs as ``python -m app.scheduler`` (unchanged, so the compose service command
does not move) on APScheduler's ``BlockingScheduler``. Two interval jobs:

``data_refresh``
    Warms the price cache for every symbol the user actually holds, so an
    outage of the upstream providers degrades to *recent* cached bars rather
    than to nothing. It fetches through :class:`MarketDataService`, which
    write-throughs to the cache; nothing is computed or stored beyond that.

``alert_evaluation``
    Runs the same :func:`app.alerts.engine.evaluate_alerts` tick the API
    exposes, then pushes any fired events to the configured webhooks. Both the
    interval and the cooldown come from the stored alert settings, re-read each
    tick so a settings change takes effect without a restart.

and two cron jobs for the sector momentum card (ADR-0012 D-5), weekdays only,
Asia/Taipei, each also run once at start-up:

``pit_snapshot_capture`` (17:30 / 19:30 / 21:30)
    One whole-market point-in-time capture into the market DB
    (:func:`app.services.pit_snapshot.capture_once`: the four kinds succeed or
    fail independently; a kind already ``ok`` for the session is skipped). The
    classification kind reads ``t187ap03_L`` only; the directory sync that
    writes positions is not run. Each capture is followed by a board refresh,
    so a session's last board always reflects its last capture (T9 replays
    exactly that view).

``sector_board_refresh`` (17:45 / 19:45 / 21:45)
    :meth:`app.services.sector_board.SectorBoardService.refresh`: D0, the
    board of the latest session with an ``ok`` bars run (written only when it
    changed), and a forward point-in-time evaluation whenever a new H-session
    sample has completed. Serialised with the capture-chained refresh.

Neither job back-fills, fills gaps or runs the biased research (C-11): the
pre-D0 history is a CLI-only step before D0.

Robustness rules, because a scheduler that dies silently is worse than no
scheduler:

* Every job body is wrapped: an exception is logged with a traceback and the
  job stays scheduled. ``max_instances=1`` and ``coalesce=True`` stop a slow
  tick from piling up behind itself.
* SIGTERM/SIGINT shut the scheduler down cleanly (``wait=True``), so an
  in-flight tick finishes instead of being cut off mid-write. Shutdown is
  idempotent: a repeated signal (docker stop, a double Ctrl-C, a supervisor
  re-sending SIGTERM) must not turn a clean stop into a traceback.
"""

from __future__ import annotations

import logging
import os
import signal
from collections.abc import Callable, Collection
from datetime import UTC, date, datetime, timedelta
from functools import lru_cache
from types import FrameType

from apscheduler.schedulers import SchedulerNotRunningError
from apscheduler.schedulers.blocking import BlockingScheduler
from apscheduler.triggers.cron import CronTrigger

from app.advice.book import self_reported_net_worth
from app.alerts.engine import SymbolSnapshot, evaluate_alerts
from app.alerts.notify import notify_all
from app.alerts.snapshot import build_snapshot
from app.alerts.store import AlertStore
from app.api.deps import (
    get_alert_store,
    get_directory_store,
    get_fx_provider,
    get_index_resolver,
    get_kelly_input_store,
    get_market_resolver,
    get_position_store,
    get_settings_store,
    get_valuator,
)
from app.api.kelly import kelly_inputs_for
from app.data.market_panel import MarketPanelStore
from app.data.providers.twse_snapshot import TwseSnapshotAdapter
from app.positions.models import Market
from app.services.index import load_market_benchmark
from app.services.market import load_bars
from app.services.pit_snapshot import CaptureSummary, capture_once
from app.services.sector_board import RefreshResult, SectorBoardService

#: How many calendar days of history the refresh job pulls per symbol.
DATA_REFRESH_LOOKBACK_DAYS = 540

#: Env overrides for the two intervals (minutes). The alert interval falls back
#: to the stored alert settings when unset.
DATA_INTERVAL_ENV = "SCHEDULER_DATA_INTERVAL_MINUTES"
ALERT_INTERVAL_ENV = "SCHEDULER_ALERT_INTERVAL_MINUTES"

DEFAULT_DATA_INTERVAL_MINUTES = 24 * 60

#: ADR-0012 D-5 job ids and schedule (weekdays, exchange time zone).
PIT_CAPTURE_JOB_ID = "pit_snapshot_capture"
SECTOR_REFRESH_JOB_ID = "sector_board_refresh"
SECTOR_JOBS_TIMEZONE = "Asia/Taipei"
SECTOR_JOBS_DAYS = "mon-fri"
SECTOR_JOBS_HOURS = "17,19,21"
PIT_CAPTURE_MINUTE = 30
SECTOR_REFRESH_MINUTE = 45
#: The start-up refresh waits for the start-up capture's own chained refresh.
SECTOR_REFRESH_STARTUP_DELAY = timedelta(minutes=2)

logger = logging.getLogger("scheduler")


def heartbeat_message(now: datetime | None = None) -> str:
    """Return the startup/liveness log message for a given time (defaults to now).

    The timestamp is a UTC ISO8601 string per the company data convention.
    """
    moment = now if now is not None else datetime.now(UTC)
    return f"scheduler heartbeat {moment.isoformat()}"


def _positive_int_env(name: str, default: int) -> int:
    """Read a positive integer from the environment, falling back on nonsense."""
    raw = os.environ.get(name, "").strip()
    if not raw:
        return default
    try:
        value = int(raw)
    except ValueError:
        logger.warning("%s=%r is not an integer; using %d", name, raw, default)
        return default
    if value <= 0:
        logger.warning("%s=%d must be positive; using %d", name, value, default)
        return default
    return value


def refresh_market_data(*, today: date | None = None) -> int:
    """Warm the price cache for every held symbol. Returns the symbols refreshed.

    Only symbols the user holds are fetched: this job exists to keep the
    degradation ladder's cache layer useful, not to crawl a universe.
    """
    resolver = get_market_resolver()
    end = today if today is not None else date.today()
    start = end - timedelta(days=DATA_REFRESH_LOOKBACK_DAYS)
    wanted: set[tuple[str, Market]] = {
        (position.symbol, position.market) for position in get_position_store().list_all()
    }
    refreshed = 0
    for symbol, market in sorted(wanted):
        loaded = load_bars(resolver, symbol=symbol, market=market, start=start, end=end)
        if loaded.bars:
            refreshed += 1
        else:
            logger.info("data refresh: no bars for %s/%s (%s)", market, symbol, loaded.reason)
    logger.info("data refresh: %d/%d symbols refreshed", refreshed, len(wanted))
    return refreshed


def evaluate_alerts_tick(*, store: AlertStore | None = None) -> int:
    """Evaluate every enabled alert rule once and push what fired.

    Returns the number of events raised. Delivery failures are contained inside
    :func:`app.alerts.notify.notify_all` and never lose the stored event.
    """
    settings = get_settings_store().load()
    if not settings.alerts.enabled:
        logger.info("alert evaluation: disabled in settings; skipping tick")
        return 0

    alert_store = store if store is not None else get_alert_store()
    resolver = get_market_resolver()
    position_store = get_position_store()
    valuator = get_valuator()
    fx_provider = get_fx_provider()
    kelly_store = get_kelly_input_store()
    budget = settings.risk_budget
    net_worth = self_reported_net_worth(
        settings.net_worth.total_net_worth_twd, settings.net_worth.updated_at
    )

    def load(symbol: str, market: Market) -> SymbolSnapshot:
        return build_snapshot(
            symbol,
            market,
            resolver=resolver,
            store=position_store,
            valuator=valuator,
            budget=budget,
            fx_provider=fx_provider,
            net_worth=net_worth,
            # The scheduled loop evaluates the same caps the API does, so cap 5
            # reads the same stored pair here as it does there.
            kelly=kelly_inputs_for(kelly_store, symbol, market),
        )

    result = evaluate_alerts(alert_store, load, cooldown_minutes=settings.alerts.cooldown_minutes)
    logger.info(
        "alert evaluation: %d rules evaluated, %d fired", result.evaluated, len(result.events)
    )
    if result.events and settings.alerts.notify_webhooks:
        for delivery in notify_all(result.events):
            logger.info("alert delivery %s: %s", delivery.channel, delivery.status)
    return len(result.events)


@lru_cache(maxsize=1)
def get_market_panel_store() -> MarketPanelStore:
    """The market DB store (its own file, ADR-0012 B3), one per process."""
    return MarketPanelStore()


def directory_names(symbols: Collection[str]) -> dict[str, str]:
    """Display names for listed constituents, from the security directory (display only)."""
    store = get_directory_store()
    names: dict[str, str] = {}
    for symbol in symbols:
        entry = store.resolve(symbol)
        if entry is not None:
            names[symbol] = entry.name
    return names


def taiex_reference_return(start: date, end: date) -> float | None:
    """TAIEX close ``start`` -> close ``end`` over the existing index path (D-9, ``backup``).

    Reference only (the 「詳細」 ``reference_taiex_return_L``): never a ranking
    input or a comparator. Any gap in the series is ``None``, never a guess.
    """
    try:
        loaded = load_market_benchmark(get_index_resolver(), market="TW", start=start, end=end)
    except Exception:
        logger.exception("sector board: TAIEX reference unavailable")
        return None
    closes = {bar.date: bar.close for bar in loaded.bars}
    first, last = closes.get(start), closes.get(end)
    if first is None or last is None or first <= 0:
        return None
    return float(last / first - 1)


@lru_cache(maxsize=1)
def get_sector_board_service() -> SectorBoardService:
    """One service per process: it serialises refreshes and remembers attempted samples."""
    return SectorBoardService(
        market_store=get_market_panel_store(),
        names=directory_names,
        reference_taiex=taiex_reference_return,
    )


def refresh_sector_board() -> RefreshResult:
    """ADR-0012 D-5 ``sector_board_refresh``."""
    result = get_sector_board_service().refresh()
    logger.info(
        "sector board refresh: session=%s board=%s stats=%s notes=%s",
        result.session,
        result.board_id,
        result.stats_run_id,
        ",".join(result.notes),
    )
    return result


def capture_pit_snapshot() -> CaptureSummary:
    """ADR-0012 D-5 ``pit_snapshot_capture``, followed by a board refresh."""
    adapter = TwseSnapshotAdapter()
    try:
        summary = capture_once(adapter, get_market_panel_store())
    finally:
        adapter.close()
    for record in summary.records:
        logger.info(
            "pit capture %s %s: status=%s rows=%d skipped_already_ok=%s",
            summary.session_date,
            record.kind,
            record.status,
            record.row_count,
            record.skipped_already_ok,
        )
    try:
        refresh_sector_board()
    except Exception:
        logger.exception("sector board refresh after capture failed; the capture stands")
    return summary


def _guarded(name: str, job: Callable[[], object]) -> Callable[[], None]:
    """Wrap a job so an exception is logged and the schedule survives it."""

    def run() -> None:
        try:
            job()
        except Exception:
            logger.exception("scheduled job %s failed; it stays scheduled", name)

    return run


def build_scheduler(scheduler: BlockingScheduler | None = None) -> BlockingScheduler:
    """Create the scheduler with both jobs registered (no side effects yet)."""
    engine = scheduler if scheduler is not None else BlockingScheduler(timezone="UTC")
    data_minutes = _positive_int_env(DATA_INTERVAL_ENV, DEFAULT_DATA_INTERVAL_MINUTES)
    alert_minutes = _positive_int_env(
        ALERT_INTERVAL_ENV, get_settings_store().load().alerts.evaluation_interval_minutes
    )

    engine.add_job(
        _guarded("data_refresh", refresh_market_data),
        trigger="interval",
        minutes=data_minutes,
        id="data_refresh",
        name="daily market data refresh",
        # A slow fetch must not stack another fetch behind it, and a tick missed
        # while the process was down is coalesced into one run rather than
        # replayed N times.
        max_instances=1,
        coalesce=True,
        # ADR-0010 D-4: warm the cache as soon as the scheduler starts. An
        # interval trigger otherwise fires first only after one whole interval
        # (24h by default), during which a cache-only book valuation (D-1)
        # would find nothing for a freshly started process.
        next_run_time=datetime.now(UTC),
    )
    engine.add_job(
        _guarded("alert_evaluation", evaluate_alerts_tick),
        trigger="interval",
        minutes=alert_minutes,
        id="alert_evaluation",
        name="alert rule evaluation",
        max_instances=1,
        coalesce=True,
    )
    started = datetime.now(UTC)
    engine.add_job(
        _guarded(PIT_CAPTURE_JOB_ID, capture_pit_snapshot),
        trigger=CronTrigger(
            day_of_week=SECTOR_JOBS_DAYS,
            hour=SECTOR_JOBS_HOURS,
            minute=PIT_CAPTURE_MINUTE,
            timezone=SECTOR_JOBS_TIMEZONE,
        ),
        id=PIT_CAPTURE_JOB_ID,
        name="whole-market point-in-time snapshot capture",
        max_instances=1,
        coalesce=True,
        # D-5: also once at start-up, so a machine that was off at 21:30 catches up.
        next_run_time=started,
    )
    engine.add_job(
        _guarded(SECTOR_REFRESH_JOB_ID, refresh_sector_board),
        trigger=CronTrigger(
            day_of_week=SECTOR_JOBS_DAYS,
            hour=SECTOR_JOBS_HOURS,
            minute=SECTOR_REFRESH_MINUTE,
            timezone=SECTOR_JOBS_TIMEZONE,
        ),
        id=SECTOR_REFRESH_JOB_ID,
        name="sector momentum board refresh",
        max_instances=1,
        coalesce=True,
        next_run_time=started + SECTOR_REFRESH_STARTUP_DELAY,
    )
    logger.info(
        "scheduler jobs registered: data_refresh every %d min, alert_evaluation every %d min, "
        "%s and %s on weekdays at %s (Asia/Taipei)",
        data_minutes,
        alert_minutes,
        PIT_CAPTURE_JOB_ID,
        SECTOR_REFRESH_JOB_ID,
        SECTOR_JOBS_HOURS,
    )
    return engine


def shutdown(engine: BlockingScheduler) -> None:
    """Stop ``engine`` once, idempotently.

    ``wait=True`` lets an in-flight tick finish rather than cutting it off
    halfway through a cache write or an event insert.

    Idempotence matters in practice: docker stop sends SIGTERM and then SIGKILL,
    a supervisor may re-send SIGTERM, and pressing Ctrl-C twice delivers two
    SIGINTs. A second call to APScheduler's ``shutdown`` raises
    ``SchedulerNotRunningError``, which inside a signal handler surfaces as an
    unhandled traceback and a non-zero exit -- a clean stop misreported as a
    crash. Both the state check and the ``except`` are needed: the check covers
    the common case, and the ``except`` closes the window between checking and
    shutting down when the second signal lands mid-call.
    """
    if not engine.running:
        logger.info("scheduler already stopped; ignoring repeated shutdown request")
        return
    try:
        engine.shutdown(wait=True)
    except SchedulerNotRunningError:
        logger.info("scheduler already stopped; ignoring repeated shutdown request")


def run(scheduler: BlockingScheduler | None = None) -> None:
    """Start the scheduler and block until a shutdown signal arrives."""
    engine = build_scheduler(scheduler)

    def handle_signal(_signum: int, _frame: FrameType | None) -> None:
        logger.info("scheduler shutdown requested")
        shutdown(engine)

    signal.signal(signal.SIGTERM, handle_signal)
    signal.signal(signal.SIGINT, handle_signal)

    logger.info(heartbeat_message())
    try:
        engine.start()
    except (KeyboardInterrupt, SystemExit):  # pragma: no cover - process-level path
        shutdown(engine)
    logger.info("scheduler stopped")


def main() -> None:  # pragma: no cover - process entry point
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    run()


if __name__ == "__main__":  # pragma: no cover - process entry point
    main()

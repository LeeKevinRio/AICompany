"""Background scheduler: data refresh, alert evaluation and the sector card's batch.

Runs as ``python -m app.scheduler`` (unchanged, so the compose service command
does not move) on APScheduler's ``BlockingScheduler``. Two core jobs:

``data_refresh`` (once at start-up, then shortly after each market's close)
    Warms the price cache for every symbol the user actually holds, so an
    outage of the upstream providers degrades to *recent* cached bars rather
    than to nothing. It fetches through :class:`MarketDataService`, which
    write-throughs to the cache; nothing is computed or stored beyond that.
    ADR-0010 D-4 (revised 2026-10-03): weekdays at 15:10 / 16:30 / 18:30
    Asia/Taipei for TW, and 18:30 then every half hour to 23:30
    America/New_York for US (daylight saving follows the zone). Whether a
    run actually asks a source is decided only by ADR-0009's ``judge()`` and
    cooldowns -- the later points are the retry table, not a bypass. Setting
    ``SCHEDULER_DATA_INTERVAL_MINUTES`` restores the old fixed interval.

``alert_evaluation`` (interval)
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

One more weekday cron job keeps the main DB's ex-dividend events current
(ADR-0016 D-5.2 / D-5.4):

``dividend_sync`` (17:50 / 19:50 / 21:50, Asia/Taipei, no start-up run)
    The same :func:`app.dividends.sync.sync_dividends` the CLI runs, with
    ``trigger="scheduled"``: one TWT48U fetch, the event upsert and one
    ``dividend_sync_runs`` row in a single transaction. It sits after the
    capture (17:30) and both board refreshes (chained, then 17:45), so the
    two TWT48U chains never fire in the same minute. The three points are a
    retry table: a Taipei date that already has an ``ok`` run is skipped, a
    ``failed`` run (adapter or empty answer) is simply tried again at the next
    point. It is not run at start-up: the table is a forward-looking notice
    that accumulates, so a missed day costs nothing a later run does not
    recover. No environment variable switches it off or changes what it does.

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
import sqlite3
from collections.abc import Callable, Collection
from contextlib import closing
from datetime import UTC, date, datetime, time, timedelta
from functools import lru_cache
from pathlib import Path
from time import monotonic
from types import FrameType
from typing import Literal
from zoneinfo import ZoneInfo

from apscheduler.schedulers import SchedulerNotRunningError
from apscheduler.schedulers.blocking import BlockingScheduler
from apscheduler.triggers.combining import OrTrigger
from apscheduler.triggers.cron import CronTrigger

from app.advice.book import self_reported_net_worth
from app.alerts.engine import SymbolSnapshot, count_unevaluable_rules, evaluate_alerts
from app.alerts.notify import notify_all
from app.alerts.snapshot import build_snapshot
from app.alerts.store import AlertStore
from app.api.deps import (
    get_alert_store,
    get_directory_store,
    get_dividend_store,
    get_fx_provider,
    get_index_resolver,
    get_kelly_input_store,
    get_market_resolver,
    get_position_store,
    get_settings_store,
    get_valuator,
)
from app.api.kelly import kelly_inputs_for
from app.data.cache import BUSY_TIMEOUT_MS
from app.data.freshness import TW_POLICY, US_POLICY
from app.data.http import RateLimitedClient
from app.data.market_panel import MarketPanelStore
from app.data.providers.twse_snapshot import TwseSnapshotAdapter
from app.dividends.providers import TWSE_OPENAPI_BASE_URL, DividendFetchResult, TwseDividendAdapter
from app.dividends.store import DividendEventStore, SyncTrigger
from app.dividends.sync import DividendFetcher, sync_dividends
from app.positions.models import Market
from app.services.index import load_market_benchmark
from app.services.market import load_bars
from app.services.pit_snapshot import CaptureSummary, capture_once
from app.services.sector_board import RefreshResult, SectorBoardService

#: How many calendar days of history the refresh job pulls per symbol. Must cover
#: the shared observation window (``app.signals.window``, ADR-0020 K-5) so every
#: reader finds its whole window warmed; pinned at 540 by ADR-0012 C-13.
DATA_REFRESH_LOOKBACK_DAYS = 540

#: Env overrides for the two intervals (minutes). The alert interval falls back
#: to the stored alert settings when unset. The data interval has no default:
#: unset, ``data_refresh`` runs on the close-of-session cron below; set to a
#: positive integer, it falls back to the legacy fixed interval.
DATA_INTERVAL_ENV = "SCHEDULER_DATA_INTERVAL_MINUTES"
ALERT_INTERVAL_ENV = "SCHEDULER_ALERT_INTERVAL_MINUTES"

#: ADR-0010 D-4 (revised 2026-10-03) ``data_refresh`` cron, weekdays only. The
#: wall times are checked against ``app.data.freshness`` by the tests (K-8):
#:
#: * TW, Asia/Taipei: the first point sits 10 min past ``TW_POLICY``'s
#:   publish cutoff (an earlier run could only expect yesterday); consecutive
#:   points are more than ``recheck_cooldown`` + 20 min apart, because a
#:   "not published yet" check is recorded when the fetch *ends* and the
#:   cooldown is a strict "less than"; the last point sits between the 17:xx
#:   and 19:xx sector batches.
#: * US, America/New_York: the first point sits 30 min past ``US_POLICY``'s
#:   publish cutoff, then every half hour to the end of the window. The 24h
#:   cooldown is counted from the end of the previous day's fetch, so the
#:   same wall time a day later is still inside it; the half-hour points let
#:   ``judge()`` pick the first moment a fetch is allowed.
DATA_REFRESH_JOB_ID = "data_refresh"
DATA_REFRESH_DAYS = "mon-fri"
DATA_REFRESH_TW_TIMES: tuple[time, ...] = (time(15, 10), time(16, 30), time(18, 30))
DATA_REFRESH_US_FIRST = time(18, 30)
DATA_REFRESH_US_RETRY_HOURS = "19-23"
DATA_REFRESH_US_RETRY_MINUTES = "0,30"
#: A data_refresh point missed by up to this much (a busy or briefly paused
#: process) still runs; APScheduler's own default is one second.
DATA_REFRESH_MISFIRE_GRACE_SECONDS = 15 * 60

#: What started a ``data_refresh`` run, as written on its log line.
DataRefreshTrigger = Literal["startup", "cron", "interval"]

_TAIPEI = ZoneInfo(TW_POLICY.timezone)
_NEW_YORK = ZoneInfo(US_POLICY.timezone)

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

#: ADR-0016 D-5.4 ``dividend_sync``: the sector batches' hours and zone, minute
#: 50 -- after the capture (:30) and the board refresh (:45), in a minute
#: of its own. No start-up run and no explicit misfire grace (like the sector
#: jobs): a tick missed by more than a second is covered by the next point.
DIVIDEND_SYNC_JOB_ID = "dividend_sync"
DIVIDEND_SYNC_MINUTE = 50
#: The CLI's own request spacing (``app.dividends.sync.main``).
DIVIDEND_SYNC_MIN_INTERVAL_SECONDS = 0.5

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


def _data_interval_minutes() -> int | None:
    """``SCHEDULER_DATA_INTERVAL_MINUTES`` as a positive integer, else ``None`` (cron).

    Unset or blank keeps the close-of-session cron silently. A value that is
    set but unusable also keeps the cron, with a warning: falling back to a
    made-up interval would silently change the schedule the operator asked
    to override.
    """
    raw = os.environ.get(DATA_INTERVAL_ENV, "").strip()
    if not raw:
        return None
    try:
        value = int(raw)
    except ValueError:
        logger.warning(
            "%s=%r is not an integer; keeping the close-of-session cron", DATA_INTERVAL_ENV, raw
        )
        return None
    if value <= 0:
        logger.warning(
            "%s=%d must be positive; keeping the close-of-session cron", DATA_INTERVAL_ENV, value
        )
        return None
    return value


def data_refresh_cron_trigger() -> OrTrigger:
    """The ``data_refresh`` schedule: five weekday crons, each in its exchange's zone."""
    taipei = [
        CronTrigger(
            day_of_week=DATA_REFRESH_DAYS,
            hour=at.hour,
            minute=at.minute,
            timezone=TW_POLICY.timezone,
        )
        for at in DATA_REFRESH_TW_TIMES
    ]
    new_york = [
        CronTrigger(
            day_of_week=DATA_REFRESH_DAYS,
            hour=DATA_REFRESH_US_FIRST.hour,
            minute=DATA_REFRESH_US_FIRST.minute,
            timezone=US_POLICY.timezone,
        ),
        CronTrigger(
            day_of_week=DATA_REFRESH_DAYS,
            hour=DATA_REFRESH_US_RETRY_HOURS,
            minute=DATA_REFRESH_US_RETRY_MINUTES,
            timezone=US_POLICY.timezone,
        ),
    ]
    return OrTrigger([*taipei, *new_york])


def _data_refresh_plan(interval_minutes: int | None) -> str:
    """The registration log's description of the data_refresh schedule."""
    if interval_minutes is not None:
        return f"legacy interval {interval_minutes} min"
    taipei = ",".join(at.strftime("%H:%M") for at in DATA_REFRESH_TW_TIMES)
    return (
        f"cron {DATA_REFRESH_DAYS} {taipei} ({TW_POLICY.timezone}) and "
        f"{DATA_REFRESH_US_FIRST:%H:%M} then hours {DATA_REFRESH_US_RETRY_HOURS} "
        f"at minutes {DATA_REFRESH_US_RETRY_MINUTES} ({US_POLICY.timezone})"
    )


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


def _utc_now() -> datetime:
    return datetime.now(UTC)


class DataRefreshRun:
    """The ``data_refresh`` job body: one :func:`refresh_market_data` call, one log line.

    The first call in a process is the start-up run (``next_run_time=now``);
    every later one was fired by ``scheduled`` -- the cron, or the legacy
    interval. ``today`` is the Taipei date of ``clock()``, the same date the
    compose containers' ``TZ=Asia/Taipei`` gives ``date.today()``; it is never
    behind New York's, so it cannot lower the session a US series is expected
    to hold.

    The line carries no URL, query, key or response body, and reports
    ``with_bars`` (holdings that came back with bars), not "fetched": whether
    a holding was a cache hit is not visible from here. A failure is logged
    as ``outcome=error`` and re-raised, so :func:`_guarded` still records the
    traceback and the job stays scheduled.
    """

    def __init__(
        self,
        *,
        scheduled: Literal["cron", "interval"],
        clock: Callable[[], datetime] = _utc_now,
    ) -> None:
        self._scheduled: DataRefreshTrigger = scheduled
        self._clock = clock
        self._ran = False

    def __call__(self) -> int:
        trigger: DataRefreshTrigger = self._scheduled if self._ran else "startup"
        self._ran = True
        now = self._clock()
        taipei = now.astimezone(_TAIPEI)
        new_york = now.astimezone(_NEW_YORK)
        began = monotonic()
        try:
            with_bars = refresh_market_data(today=taipei.date())
        except Exception:
            self._log(logging.ERROR, trigger, taipei, new_york, 0, began, "error")
            raise
        self._log(logging.INFO, trigger, taipei, new_york, with_bars, began, "ok")
        return with_bars

    @staticmethod
    def _log(
        level: int,
        trigger: DataRefreshTrigger,
        taipei: datetime,
        new_york: datetime,
        with_bars: int,
        began: float,
        outcome: Literal["ok", "error"],
    ) -> None:
        logger.log(
            level,
            "data refresh run: trigger=%s taipei=%s new_york=%s with_bars=%d "
            "duration_ms=%d outcome=%s",
            trigger,
            taipei.isoformat(timespec="minutes"),
            new_york.isoformat(timespec="minutes"),
            with_bars,
            max(0, round((monotonic() - began) * 1000)),
            outcome,
        )


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


def latest_ok_dividend_sync_date(db_path: Path) -> date | None:
    """Taipei date of the newest ``ok`` ``dividend_sync_runs`` row, or ``None``.

    Read-only (``PRAGMA query_only``): one ``SELECT`` over the existing
    ``(status, recorded_at)`` index. A missing table reads as "no run"; a stored
    timestamp that does not parse is warned about and also reads as "no run",
    because syncing once too often is an idempotent upsert while skipping on a
    value nobody can read could starve the table for good. ``recorded_at`` is
    UTC (store clock) and is converted to Taipei time before taking the date.
    """
    with closing(sqlite3.connect(db_path, timeout=BUSY_TIMEOUT_MS / 1000)) as conn:
        conn.execute("PRAGMA query_only = ON")
        try:
            row = conn.execute(
                "SELECT recorded_at FROM dividend_sync_runs WHERE status = 'ok' "
                "ORDER BY recorded_at DESC LIMIT 1"
            ).fetchone()
        except sqlite3.OperationalError as error:
            if "no such table" in str(error):
                return None
            raise
    if row is None:
        return None
    try:
        recorded = datetime.fromisoformat(str(row[0]))
    except ValueError:
        logger.warning("dividend sync: unreadable recorded_at %r; treating as no ok run", row[0])
        return None
    if recorded.tzinfo is None:
        recorded = recorded.replace(tzinfo=UTC)
    return recorded.astimezone(_TAIPEI).date()


def run_dividend_sync(
    *,
    store: DividendEventStore | None = None,
    adapter: DividendFetcher | None = None,
    clock: Callable[[], datetime] = _utc_now,
) -> DividendFetchResult | None:
    """ADR-0016 D-5.4 ``dividend_sync``: one scheduled TWT48U sync, or a skip.

    Returns the fetch result, or ``None`` when the Taipei date already has an
    ``ok`` run (nothing fetched, nothing written). An adapter failure or an
    answer with no events is a ``failed`` run recorded inside
    :func:`sync_dividends` plus a WARNING line here, and a normal return: the
    job succeeded and the next point retries. Anything unexpected -- notably a
    failure while writing, which ``sync_dividends`` re-raises after rolling the
    whole transaction back -- is deliberately **not** caught here (tech-architect
    ruling): it propagates to :func:`_guarded`, which logs an ERROR with the
    traceback and keeps the schedule alive, so a broken write is not swallowed
    into one more line among the routine warnings. ``adapter`` is for tests; by
    default it is built the way the CLI builds it and closed afterwards.
    """
    trigger: SyncTrigger = "scheduled"
    began = monotonic()
    today = clock().astimezone(_TAIPEI).date()
    target = store if store is not None else get_dividend_store()
    last_ok = latest_ok_dividend_sync_date(target.db_path)
    if last_ok == today:
        logger.info(
            "dividend sync run: trigger=%s taipei=%s outcome=skipped (ok run already today)",
            trigger,
            today.isoformat(),
        )
        return None
    owned: list[TwseDividendAdapter | RateLimitedClient] = []
    try:
        if adapter is None:
            client = RateLimitedClient(
                base_url=TWSE_OPENAPI_BASE_URL,
                min_interval_seconds=DIVIDEND_SYNC_MIN_INTERVAL_SECONDS,
            )
            built = TwseDividendAdapter(client=client)
            owned.extend((built, client))
            adapter = built
        result = sync_dividends(store=target, adapter=adapter, trigger=trigger)
    finally:
        for resource in owned:
            resource.close()
    # Same rule as ``DividendEventStore.record_sync``: an ok adapter answer with
    # no events is recorded as a failed run with zero events.
    usable = result.ok and len(result.events) > 0
    logger.log(
        logging.INFO if usable else logging.WARNING,
        "dividend sync run: trigger=%s taipei=%s status=%s event_count=%d "
        "unparsed_count=%d unattributed_count=%d duration_ms=%d",
        trigger,
        today.isoformat(),
        "ok" if usable else "failed",
        len(result.events) if usable else 0,
        len(result.unparsed_symbols),
        result.unattributed_rows,
        max(0, round((monotonic() - began) * 1000)),
    )
    return result


def _guarded(name: str, job: Callable[[], object]) -> Callable[[], None]:
    """Wrap a job so an exception is logged and the schedule survives it."""

    def run() -> None:
        try:
            job()
        except Exception:
            logger.exception("scheduled job %s failed; it stays scheduled", name)

    return run


def build_scheduler(scheduler: BlockingScheduler | None = None) -> BlockingScheduler:
    """Create the scheduler with every job registered (no side effects yet)."""
    engine = scheduler if scheduler is not None else BlockingScheduler(timezone="UTC")
    data_minutes = _data_interval_minutes()
    alert_minutes = _positive_int_env(
        ALERT_INTERVAL_ENV, get_settings_store().load().alerts.evaluation_interval_minutes
    )

    data_trigger: dict[str, object] = (
        {"trigger": data_refresh_cron_trigger()}
        if data_minutes is None
        else {"trigger": "interval", "minutes": data_minutes}
    )
    engine.add_job(
        _guarded(
            DATA_REFRESH_JOB_ID,
            DataRefreshRun(scheduled="cron" if data_minutes is None else "interval"),
        ),
        **data_trigger,
        id=DATA_REFRESH_JOB_ID,
        name="market data refresh after the close",
        # A slow fetch must not stack another fetch behind it, and a tick missed
        # while the process was down is coalesced into one run rather than
        # replayed N times.
        max_instances=1,
        coalesce=True,
        misfire_grace_time=DATA_REFRESH_MISFIRE_GRACE_SECONDS,
        # ADR-0010 D-4: warm the cache as soon as the scheduler starts, rather
        # than at the next close-of-session point (or one whole interval later
        # in legacy mode), during which a cache-only book valuation (D-1)
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
    engine.add_job(
        _guarded(DIVIDEND_SYNC_JOB_ID, run_dividend_sync),
        trigger=CronTrigger(
            day_of_week=SECTOR_JOBS_DAYS,
            hour=SECTOR_JOBS_HOURS,
            minute=DIVIDEND_SYNC_MINUTE,
            timezone=SECTOR_JOBS_TIMEZONE,
        ),
        id=DIVIDEND_SYNC_JOB_ID,
        name="TWT48U ex-dividend sync",
        max_instances=1,
        coalesce=True,
        # No next_run_time: no start-up run (see the module docstring).
    )
    logger.info(
        "scheduler jobs registered: data_refresh at start-up then %s, "
        "alert_evaluation every %d min, %s and %s on weekdays at %s (Asia/Taipei), "
        "%s on weekdays at %s:%d (Asia/Taipei)",
        _data_refresh_plan(data_minutes),
        alert_minutes,
        PIT_CAPTURE_JOB_ID,
        SECTOR_REFRESH_JOB_ID,
        SECTOR_JOBS_HOURS,
        DIVIDEND_SYNC_JOB_ID,
        SECTOR_JOBS_HOURS,
        DIVIDEND_SYNC_MINUTE,
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


def log_unevaluable_alert_rules(store: AlertStore | None = None) -> int | None:
    """Log how many enabled alert rules name a field alerts cannot evaluate.

    ADR-0021 K-8: a read-only start-up diagnostic. It logs a count and nothing
    else -- no rule ids, symbols or fields -- and changes no rule; such rules
    stay as the user saved them and are skipped on each tick. Returns the
    count, or ``None`` when the store could not be read (which must never stop
    the scheduler from starting).
    """
    try:
        rules = (store if store is not None else get_alert_store()).list_rules(enabled_only=True)
    except Exception:
        logger.exception("alert rule diagnostic: could not read the alert rules")
        return None
    count = count_unevaluable_rules(rules)
    logger.info("alert rule diagnostic: %d enabled rule(s) reference unevaluable fields", count)
    return count


def run(scheduler: BlockingScheduler | None = None) -> None:
    """Start the scheduler and block until a shutdown signal arrives."""
    engine = build_scheduler(scheduler)
    log_unevaluable_alert_rules()

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

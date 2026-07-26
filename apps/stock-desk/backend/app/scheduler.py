"""Background scheduler: daily data refresh and alert evaluation.

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
from collections.abc import Callable
from datetime import UTC, date, datetime, timedelta
from types import FrameType

from apscheduler.schedulers import SchedulerNotRunningError
from apscheduler.schedulers.blocking import BlockingScheduler

from app.alerts.engine import SymbolSnapshot, evaluate_alerts
from app.alerts.notify import notify_all
from app.alerts.snapshot import build_snapshot
from app.alerts.store import AlertStore
from app.api.deps import (
    get_alert_store,
    get_fx_provider,
    get_market_resolver,
    get_position_store,
    get_settings_store,
    get_valuator,
)
from app.positions.models import Market
from app.services.market import load_bars

#: How many calendar days of history the refresh job pulls per symbol.
DATA_REFRESH_LOOKBACK_DAYS = 540

#: Env overrides for the two intervals (minutes). The alert interval falls back
#: to the stored alert settings when unset.
DATA_INTERVAL_ENV = "SCHEDULER_DATA_INTERVAL_MINUTES"
ALERT_INTERVAL_ENV = "SCHEDULER_ALERT_INTERVAL_MINUTES"

DEFAULT_DATA_INTERVAL_MINUTES = 24 * 60

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
    budget = settings.risk_budget

    def load(symbol: str, market: Market) -> SymbolSnapshot:
        return build_snapshot(
            symbol,
            market,
            resolver=resolver,
            store=position_store,
            valuator=valuator,
            budget=budget,
            fx_provider=fx_provider,
        )

    result = evaluate_alerts(
        alert_store, load, cooldown_minutes=settings.alerts.cooldown_minutes
    )
    logger.info(
        "alert evaluation: %d rules evaluated, %d fired", result.evaluated, len(result.events)
    )
    if result.events and settings.alerts.notify_webhooks:
        for delivery in notify_all(result.events):
            logger.info("alert delivery %s: %s", delivery.channel, delivery.status)
    return len(result.events)


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
    logger.info(
        "scheduler jobs registered: data_refresh every %d min, alert_evaluation every %d min",
        data_minutes,
        alert_minutes,
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

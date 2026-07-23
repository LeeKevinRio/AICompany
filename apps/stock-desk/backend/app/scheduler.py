# Phase 1 placeholder, will be replaced by APScheduler in a later phase.
"""Minimal heartbeat scheduler entry point.

Runs as ``python -m app.scheduler`` and logs a heartbeat line every 60
seconds using only the standard library. It shuts down cleanly on SIGTERM
or KeyboardInterrupt so it behaves well as a docker compose service.
"""

import logging
import signal
import threading
from datetime import UTC, datetime
from types import FrameType

HEARTBEAT_INTERVAL_SECONDS = 60

logger = logging.getLogger("scheduler")

# Event that is set when a shutdown signal is received.
_shutdown = threading.Event()


def heartbeat_message(now: datetime | None = None) -> str:
    """Return the heartbeat log message for a given time (defaults to now).

    The timestamp is a UTC ISO8601 string per the company data convention.
    """
    moment = now if now is not None else datetime.now(UTC)
    return f"scheduler heartbeat {moment.isoformat()}"


def _handle_signal(_signum: int, _frame: FrameType | None) -> None:
    """Request a clean shutdown when a termination signal is received."""
    _shutdown.set()


def run() -> None:
    """Emit a heartbeat every interval until a shutdown is requested."""
    signal.signal(signal.SIGTERM, _handle_signal)
    signal.signal(signal.SIGINT, _handle_signal)

    logger.info("scheduler starting (Phase 1 heartbeat placeholder)")
    try:
        while not _shutdown.is_set():
            logger.info(heartbeat_message())
            # Wait returns early if a shutdown is requested mid-interval.
            _shutdown.wait(HEARTBEAT_INTERVAL_SECONDS)
    except KeyboardInterrupt:
        _shutdown.set()
    logger.info("scheduler stopped")


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    run()


if __name__ == "__main__":
    main()

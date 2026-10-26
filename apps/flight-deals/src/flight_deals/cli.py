"""Console entry point: ``flight-deals`` starts the web app and scheduler on 127.0.0.1."""

from __future__ import annotations

import argparse
import logging
import sys
from typing import Any

import uvicorn

from flight_deals.app import SchedulerLockHeldError, acquire_scheduler_lock, create_app
from flight_deals.config import BIND_HOST, ConfigError, load_config
from flight_deals.logging_setup import setup_logging

log = logging.getLogger("flight_deals")


def build_uvicorn_kwargs(port: int) -> dict[str, Any]:
    """Single process, no reload: a second worker would start a second scheduler."""
    return {
        "host": BIND_HOST,
        "port": port,
        "reload": False,
        "workers": 1,
        "log_config": None,
        "access_log": False,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="flight-deals", description="機票低價監看器")
    parser.add_argument("--port", type=int, default=None, help="listen port (default 8795)")
    parser.add_argument("--debug", action="store_true", help="verbose logging")
    args = parser.parse_args(argv)

    setup_logging(logging.DEBUG if args.debug else logging.INFO)
    try:
        config = load_config(production=True)
    except ConfigError as exc:
        log.error("configuration error: %s", exc)
        return 2
    port = args.port or config.port
    # Before building the app (and migrating the DB): one scheduler per database.
    try:
        lock = acquire_scheduler_lock(config)
    except SchedulerLockHeldError as exc:
        log.error("refusing to start: %s", exc)
        return 2
    try:
        app = create_app(config, scheduler_lock=lock)
        log.info("flight-deals listening on http://%s:%d", BIND_HOST, port)
        uvicorn.run(app, **build_uvicorn_kwargs(port))
    finally:
        lock.release()
    return 0


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())

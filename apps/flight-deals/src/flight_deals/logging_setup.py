"""Logging configuration with mandatory secret redaction. Stdlib only."""

from __future__ import annotations

import logging
import sys
from logging.handlers import RotatingFileHandler
from pathlib import Path
from typing import TextIO

from flight_deals.redact import redact

_NOISY_LOGGERS = ("httpx", "httpcore", "primp")
_FORMAT = "%(asctime)s %(levelname)s %(name)s: %(message)s"
LOG_FILE_NAME = "flight-deals.log"
LOG_MAX_BYTES = 1_000_000
LOG_BACKUP_COUNT = 3


class RedactingFilter(logging.Filter):
    """Rewrite each record's message with secrets masked before any handler formats it."""

    def filter(self, record: logging.LogRecord) -> bool:
        record.msg = redact(record.getMessage())
        record.args = None
        if record.exc_info and not record.exc_text:
            record.exc_text = logging.Formatter().formatException(record.exc_info)
        if record.exc_text:
            record.exc_text = redact(record.exc_text)
        if record.stack_info:
            record.stack_info = redact(record.stack_info)
        return True


class RedactingFormatter(logging.Formatter):
    """Second line of defence: redact the fully formatted output too."""

    def format(self, record: logging.LogRecord) -> str:
        return redact(super().format(record))


def _install(handler: logging.Handler, level: int) -> logging.Handler:
    root = logging.getLogger()
    for existing in list(root.handlers):
        if getattr(existing, "_flight_deals", False):
            root.removeHandler(existing)
            existing.close()
    handler.setFormatter(RedactingFormatter(_FORMAT))
    handler.addFilter(RedactingFilter())
    handler._flight_deals = True  # type: ignore[attr-defined]
    root.addHandler(handler)
    if not any(isinstance(f, RedactingFilter) for f in root.filters):
        root.addFilter(RedactingFilter())
    root.setLevel(level)
    for name in _NOISY_LOGGERS:
        logging.getLogger(name).setLevel(logging.WARNING)
    return handler


def setup_logging(level: int = logging.INFO, stream: TextIO | None = None) -> logging.Handler:
    """Install a single redacting handler on the root logger and quiet httpx/httpcore."""
    return _install(logging.StreamHandler(stream or sys.stderr), level)


def setup_file_logging(log_path: Path, level: int = logging.INFO) -> logging.Handler:
    """Background mode: a rotating, redacting log file instead of stdout / stderr.

    ``pythonw.exe`` has no console, so nothing may be written to the standard streams.
    """
    log_path.parent.mkdir(parents=True, exist_ok=True)
    handler = RotatingFileHandler(
        log_path, maxBytes=LOG_MAX_BYTES, backupCount=LOG_BACKUP_COUNT, encoding="utf-8"
    )
    return _install(handler, level)

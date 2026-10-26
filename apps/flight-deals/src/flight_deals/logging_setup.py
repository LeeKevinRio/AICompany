"""Logging configuration with mandatory secret redaction. Stdlib only."""

from __future__ import annotations

import logging
import sys
from typing import TextIO

from flight_deals.redact import redact

_NOISY_LOGGERS = ("httpx", "httpcore", "primp")
_FORMAT = "%(asctime)s %(levelname)s %(name)s: %(message)s"


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


def setup_logging(level: int = logging.INFO, stream: TextIO | None = None) -> logging.Handler:
    """Install a single redacting handler on the root logger and quiet httpx/httpcore."""
    root = logging.getLogger()
    for existing in list(root.handlers):
        if getattr(existing, "_flight_deals", False):
            root.removeHandler(existing)
    handler = logging.StreamHandler(stream or sys.stderr)
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

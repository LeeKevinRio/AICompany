"""Process-wide logging setup shared by the API and the scheduler, plus secret redaction.

Both process entry points call :func:`configure_logging` once at start-up (the
API from its FastAPI lifespan, the scheduler from ``main()``); it is never run
at import time, so importing an app module in a test changes nothing.

What it guarantees, in order of importance:

1. **Secrets stay out of the log.** httpx logs every request URL at INFO, and
   our URLs carry secrets (the Telegram ``bot<token>`` path, the Discord
   webhook URL, FinMind ``token=`` and Alpha Vantage ``apikey=`` query
   parameters). ``httpx`` and ``httpcore`` are therefore pinned to WARNING on
   every call, whoever owns the rest of the logging configuration.
2. **Defence in depth.** The handler installed here carries a
   :class:`SecretRedactionFilter` that rewrites any of those patterns via
   :func:`redact_url` before a line is written, so a future call site that
   forgets rule 1 still does not leak.
3. **Readable lines.** ``time level logger: message``; the root logger stays at
   WARNING and only our own namespaces (``app``, ``scheduler``) log INFO.

When the root logger already has handlers, someone else owns the logging
configuration (pytest, an embedding host); only rule 1 is applied then, so
test log capture and level expectations are left untouched.

:func:`describe_failure` is the one sanctioned way to put an exception into a
log line or a user-visible detail string: it keeps the exception class name and
an HTTP status code, never the exception's message text, whose content depends
on the library version and may embed the request URL.
"""

from __future__ import annotations

import logging
import re
import sys

import httpx

LOG_FORMAT = "%(asctime)s %(levelname)s %(name)s: %(message)s"

#: Our own logger namespaces, the only ones raised to INFO.
INFO_NAMESPACES = ("app", "scheduler")

#: Libraries that log full request URLs at INFO/DEBUG; never below WARNING.
QUIET_NAMESPACES = ("httpx", "httpcore")

REDACTED = "***"

_SAFE_CHARS = r"[^/\s?#&'\"<>]"

#: (pattern, replacement) pairs applied in order by :func:`redact_url`.
_REDACTIONS: tuple[tuple[re.Pattern[str], str], ...] = (
    # Telegram bot token in the path: api.telegram.org/bot<token>/sendMessage.
    (re.compile(rf"(api\.telegram\.org/bot){_SAFE_CHARS}+", re.IGNORECASE), rf"\g<1>{REDACTED}"),
    # The same token shape (<digits>:<secret>) behind /bot on any host.
    (re.compile(rf"(/bot)\d+:{_SAFE_CHARS}+"), rf"\g<1>{REDACTED}"),
    # Discord webhook: /webhooks/<id>/<token>; the id is kept, the token is not.
    (re.compile(rf"(/webhooks/{_SAFE_CHARS}+/){_SAFE_CHARS}+"), rf"\g<1>{REDACTED}"),
    # Query-string credentials: token=, apikey=, api_key=.
    (
        re.compile(r"([?&;](?:token|apikey|api_key)=)[^&#\s'\"<>]*", re.IGNORECASE),
        rf"\g<1>{REDACTED}",
    ),
)


def redact_url(text: str) -> str:
    """Mask every credential-bearing URL fragment in ``text``.

    Works on a bare URL or on free text containing URLs (a log line, a
    traceback). Idempotent: an already-redacted string comes back unchanged,
    and a URL without credentials is never altered.
    """
    for pattern, replacement in _REDACTIONS:
        text = pattern.sub(replacement, text)
    return text


class SecretRedactionFilter(logging.Filter):
    """Rewrite a record's rendered message (and traceback) through :func:`redact_url`."""

    def filter(self, record: logging.LogRecord) -> bool:
        try:
            message = record.getMessage()
        except Exception:
            # A malformed format/args pair: keep the template only, redacted,
            # so the handler's error path cannot echo the raw arguments.
            message = str(record.msg)
        # The rendered message replaces the template so no later formatting
        # pass can re-insert an unredacted argument.
        record.msg = redact_url(message)
        record.args = None
        if record.exc_info and not record.exc_text:
            record.exc_text = logging.Formatter().formatException(record.exc_info)
        if record.exc_text:
            record.exc_text = redact_url(record.exc_text)
        if record.stack_info:
            record.stack_info = redact_url(record.stack_info)
        return True


def configure_logging() -> None:
    """Configure process logging once; safe to call any number of times."""
    for name in QUIET_NAMESPACES:
        logging.getLogger(name).setLevel(logging.WARNING)

    root = logging.getLogger()
    if root.handlers:
        return

    handler = logging.StreamHandler(sys.stderr)
    handler.setFormatter(logging.Formatter(LOG_FORMAT))
    handler.addFilter(SecretRedactionFilter())
    root.addHandler(handler)
    root.setLevel(logging.WARNING)
    for name in INFO_NAMESPACES:
        logging.getLogger(name).setLevel(logging.INFO)


def describe_failure(exc: BaseException) -> str:
    """A log-safe description of ``exc``: class name and HTTP status, nothing else.

    Never includes the exception's message, its arguments, or any URL; the
    result is therefore safe for a log line, a delivery ``detail``, or an alert.
    """
    parts = [f"error_class={type(exc).__name__}"]
    if isinstance(exc, httpx.HTTPStatusError):
        parts.append(f"status={exc.response.status_code}")
    return " ".join(parts)

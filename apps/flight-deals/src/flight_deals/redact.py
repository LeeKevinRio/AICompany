"""Secret redaction for anything that may reach logs or the database.

Stdlib only. External error strings (httpx exceptions embed the full request URL,
which for Telegram contains the bot token) must pass through ``redact`` first.
"""

from __future__ import annotations

import re
import threading

REDACTED = "***"
_BOT_TOKEN_PATTERN = re.compile(r"bot\d+:[A-Za-z0-9_-]+")
_MIN_SECRET_LENGTH = 4

_lock = threading.Lock()
_secrets: set[str] = set()


def register_secret(value: str | None) -> None:
    """Register a loaded secret value so every later ``redact`` call masks it."""
    if value is None:
        return
    value = value.strip()
    if len(value) < _MIN_SECRET_LENGTH:
        return
    with _lock:
        _secrets.add(value)


def clear_secrets() -> None:
    """Forget registered secrets (test helper)."""
    with _lock:
        _secrets.clear()


def redact(text: object) -> str:
    """Return ``text`` as a string with bot tokens and registered secrets masked."""
    result = str(text)
    result = _BOT_TOKEN_PATTERN.sub("bot" + REDACTED, result)
    with _lock:
        secrets = sorted(_secrets, key=len, reverse=True)
    for secret in secrets:
        result = result.replace(secret, REDACTED)
    return result


def redact_truncate(text: object, limit: int = 500) -> str:
    """Redact, then truncate to ``limit`` characters for storage."""
    result = redact(text)
    if len(result) > limit:
        return result[: limit - 3] + "..."
    return result

"""One start-up log line saying which optional secrets this process can see.

The API and the scheduler read their secrets from environment variables only.
When they are started natively (``dev-up.bat`` / ``dev-up.sh``) the variables
come from ``apps/stock-desk/.env`` via ``uv run --env-file``; a missing or
mistyped entry used to fail silently (FinMind answers "unavailable", a push
channel is skipped). This module makes that visible.

**Hard rule: only a boolean per channel ever leaves this module.** The values
are read to test "non-empty after strip" and are dropped immediately; they are
never stored, formatted, sliced or passed to a logger, not even partially. That
holds by construction, independent of the redaction filter in
:mod:`app.logging_setup`, which is only a second line of defence.
"""

from __future__ import annotations

import logging
import os
from collections.abc import Mapping

from app.alerts.notify import DISCORD_WEBHOOK_ENV, TELEGRAM_CHAT_ID_ENV, TELEGRAM_TOKEN_ENV
from app.data.providers.alpha_vantage import API_KEY_ENV_VAR as ALPHA_VANTAGE_ENV
from app.data.providers.finmind import TOKEN_ENV_VAR as FINMIND_ENV

SET_LABEL = "已設定"
UNSET_LABEL = "未設定"


def _present(env: Mapping[str, str], *names: str) -> bool:
    """True when every named variable holds a non-blank value."""
    return all(bool(env.get(name, "").strip()) for name in names)


def describe_env_status(env: Mapping[str, str] | None = None) -> str:
    """A single-line, value-free summary of the optional secrets in ``env``.

    Telegram counts as set only when both the bot token and the chat id are
    present, matching what :func:`app.alerts.notify.notify` needs to deliver.
    """
    source = os.environ if env is None else env
    channels = (
        ("FINMIND token", _present(source, FINMIND_ENV)),
        ("Alpha Vantage key", _present(source, ALPHA_VANTAGE_ENV)),
        ("Discord webhook", _present(source, DISCORD_WEBHOOK_ENV)),
        ("Telegram", _present(source, TELEGRAM_TOKEN_ENV, TELEGRAM_CHAT_ID_ENV)),
    )
    return "；".join(f"{name}：{SET_LABEL if ok else UNSET_LABEL}" for name, ok in channels)


def log_env_status(logger: logging.Logger, process: str) -> None:
    """Log the status line once; ``process`` names the caller (backend / scheduler)."""
    logger.info("%s 啟動，環境設定載入狀態 -> %s", process, describe_env_status())

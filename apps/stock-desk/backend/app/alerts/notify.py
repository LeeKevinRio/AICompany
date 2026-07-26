"""Push a triggered alert to the optional Discord / Telegram webhooks.

Configuration is **environment-only** -- webhook URLs and bot tokens are
secrets and never touch the settings table, the API surface, or a commit:

===============================  ==================================
``ALERT_DISCORD_WEBHOOK_URL``    Discord incoming-webhook URL.
``ALERT_TELEGRAM_BOT_TOKEN``     Telegram bot token.
``ALERT_TELEGRAM_CHAT_ID``       Telegram chat to post into.
===============================  ==================================

A channel with no configuration is simply skipped (reported as ``skipped``, not
as a failure). A channel that is configured but fails -- network down, 4xx from
the provider, a malformed URL -- is logged and reported as ``failed``: an alert
that could not be delivered must never take down the tick that produced it, and
must never be silently swallowed either. The event itself is already persisted
before this module is called, so the record survives any delivery outcome.
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass

import httpx

from app.alerts.models import AlertEvent

logger = logging.getLogger(__name__)

DISCORD_WEBHOOK_ENV = "ALERT_DISCORD_WEBHOOK_URL"
TELEGRAM_TOKEN_ENV = "ALERT_TELEGRAM_BOT_TOKEN"
TELEGRAM_CHAT_ID_ENV = "ALERT_TELEGRAM_CHAT_ID"

TELEGRAM_API_TEMPLATE = "https://api.telegram.org/bot{token}/sendMessage"

#: Seconds before a webhook POST is abandoned. Deliberately short: a slow
#: webhook must not stall the scheduler tick.
REQUEST_TIMEOUT_SECONDS = 5.0


@dataclass(frozen=True)
class DeliveryResult:
    """What happened on one channel for one event."""

    channel: str
    #: ``sent`` / ``skipped`` (not configured) / ``failed``.
    status: str
    detail: str | None = None


def format_message(event: AlertEvent) -> str:
    """Render an event as the plain text pushed to a webhook."""
    return (
        f"[stock-desk 警示] {event.symbol}（{event.market}）\n"
        f"{event.message}\n"
        f"觸發時間：{event.triggered_at.isoformat()}\n"
        "本工具為研究與教育用途，非投資建議。"
    )


def _post(client: httpx.Client, url: str, payload: dict[str, object]) -> None:
    response = client.post(url, json=payload, timeout=REQUEST_TIMEOUT_SECONDS)
    response.raise_for_status()


def _deliver(
    channel: str, url: str | None, payload: dict[str, object], client: httpx.Client
) -> DeliveryResult:
    if not url:
        return DeliveryResult(channel=channel, status="skipped", detail="未設定環境變數")
    try:
        _post(client, url, payload)
    except Exception as exc:
        # Any delivery problem is contained here; the event is already stored.
        logger.warning("alert webhook delivery failed on %s: %s", channel, exc)
        return DeliveryResult(channel=channel, status="failed", detail=str(exc))
    return DeliveryResult(channel=channel, status="sent")


def notify(event: AlertEvent, *, client: httpx.Client | None = None) -> list[DeliveryResult]:
    """Deliver ``event`` to every configured channel; never raises.

    ``client`` is injectable so tests exercise the full path against a mock
    transport and never reach the network.
    """
    text = format_message(event)
    discord_url = os.environ.get(DISCORD_WEBHOOK_ENV, "").strip()
    telegram_token = os.environ.get(TELEGRAM_TOKEN_ENV, "").strip()
    telegram_chat = os.environ.get(TELEGRAM_CHAT_ID_ENV, "").strip()
    telegram_url = (
        TELEGRAM_API_TEMPLATE.format(token=telegram_token)
        if telegram_token and telegram_chat
        else None
    )

    owns_client = client is None
    active = client if client is not None else httpx.Client()
    try:
        results = [
            _deliver("discord", discord_url or None, {"content": text}, active),
            _deliver(
                "telegram",
                telegram_url,
                {"chat_id": telegram_chat, "text": text},
                active,
            ),
        ]
    finally:
        if owns_client:
            active.close()
    return results


def notify_all(
    events: list[AlertEvent], *, client: httpx.Client | None = None
) -> list[DeliveryResult]:
    """Deliver every event over one shared connection pool; never raises."""
    if not events:
        return []
    owns_client = client is None
    active = client if client is not None else httpx.Client()
    try:
        results: list[DeliveryResult] = []
        for event in events:
            results.extend(notify(event, client=active))
        return results
    finally:
        if owns_client:
            active.close()

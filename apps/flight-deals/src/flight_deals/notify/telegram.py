"""Telegram Bot API notifier (``sendMessage``, plain text, no ``parse_mode``).

Never raises on delivery failure; errors are redacted because httpx messages embed the
request URL, which contains the bot token.
"""

from __future__ import annotations

import httpx

from flight_deals.ports import SendResult
from flight_deals.redact import redact_truncate

API_BASE = "https://api.telegram.org"
MAX_MESSAGE_LENGTH = 4096


class TelegramNotifier:
    def __init__(
        self,
        token: str | None,
        chat_id: str | None,
        *,
        timeout_seconds: float = 5.0,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        self._token = token
        self._chat_id = chat_id
        self._timeout = timeout_seconds
        self._transport = transport

    @property
    def channel(self) -> str:
        return "telegram"

    def is_configured(self) -> bool:
        return bool(self._token and self._chat_id)

    def build_payload(self, text: str) -> dict[str, str]:
        if len(text) > MAX_MESSAGE_LENGTH:
            text = text[: MAX_MESSAGE_LENGTH - 1] + "…"
        return {"chat_id": str(self._chat_id), "text": text}

    def send(self, text: str) -> SendResult:
        if not self.is_configured():
            return SendResult(
                ok=False,
                error="Telegram 未設定（缺少 FLIGHT_DEALS_TELEGRAM_BOT_TOKEN 或 CHAT_ID）",
            )
        url = f"{API_BASE}/bot{self._token}/sendMessage"
        try:
            with httpx.Client(timeout=self._timeout, transport=self._transport) as client:
                response = client.post(url, json=self.build_payload(text))
        except httpx.HTTPError as exc:
            return SendResult(ok=False, error=redact_truncate(f"{type(exc).__name__}: {exc}"))
        except Exception as exc:  # defensive: never let a notifier crash a scan
            return SendResult(ok=False, error=redact_truncate(f"{type(exc).__name__}: {exc}"))
        if response.status_code == 200:
            try:
                body = response.json()
            except ValueError:
                body = None
            if isinstance(body, dict) and body.get("ok") is True:
                return SendResult(ok=True)
        description = ""
        try:
            data = response.json()
            if isinstance(data, dict):
                description = str(data.get("description", ""))
        except ValueError:
            description = response.text[:200]
        return SendResult(
            ok=False,
            error=redact_truncate(f"HTTP {response.status_code}: {description}".strip()),
        )

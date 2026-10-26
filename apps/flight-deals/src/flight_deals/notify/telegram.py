"""Telegram Bot API notifier (``sendMessage``, plain text, no ``parse_mode``).

Never raises on delivery failure; errors are redacted because httpx messages embed the
request URL, which contains the bot token. ``TelegramSetupClient`` backs the
``flight-deals telegram-setup`` wizard and is the only place that calls ``getUpdates``.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Literal

import httpx

from flight_deals.domain.messages import telegram_test_message
from flight_deals.domain.timeutil import utc_now
from flight_deals.ports import SendResult
from flight_deals.redact import redact_truncate

API_BASE = "https://api.telegram.org"
MAX_MESSAGE_LENGTH = 4096
Transport = httpx.BaseTransport


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


# ---- setup wizard client (ADR-0002 FD-4 Decision 7, C-35) ----------------------------

SetupErrorKind = Literal["unauthorized", "conflict", "network", "http", "invalid_response"]
SETUP_TIMEOUT_MARGIN_SECONDS = 10.0
SEND_TEST_TIMEOUT_SECONDS = 10.0
UNAUTHORIZED_TEXT = (
    "Telegram 回應 401 Unauthorized：bot token 無效或已被撤銷。"
    "請到 @BotFather 確認 token（/token 可重新產生），"
    "再更新 FLIGHT_DEALS_TELEGRAM_BOT_TOKEN。"
)
CONFLICT_TEXT = (
    "Telegram 回應 409 Conflict：這個 bot 設有 webhook，或有另一個程式正在讀取它的訊息，"
    "因此無法用 getUpdates 取得聊天 ID。請先移除 webhook 或停止另一個讀取程式後再試。"
)
NETWORK_TEXT = "無法連線到 Telegram，請確認這台電腦可以上網"
_UPDATE_KINDS = ("message", "edited_message", "channel_post", "edited_channel_post")
_MEMBER_KINDS = ("my_chat_member", "chat_member")


@dataclass(frozen=True)
class ChatCandidate:
    """A chat seen in ``getUpdates``; ``update_id`` orders candidates (newest last)."""

    chat_id: int
    chat_type: str
    title: str
    update_id: int


@dataclass(frozen=True)
class UpdatesResult:
    ok: bool
    chats: tuple[ChatCandidate, ...] = ()
    next_offset: int | None = None
    error: str | None = None
    error_kind: SetupErrorKind | None = None


# C0 controls, DEL and C1 controls (includes ESC, so no ANSI sequence reaches a terminal).
_CONTROL_CHARS = re.compile(r"[\x00-\x1f\x7f-\x9f]")


def _chat_title(chat: dict[str, Any]) -> str:
    """Printable chat title: control characters removed, at most 60 characters."""
    for key in ("title", "username", "first_name"):
        value = chat.get(key)
        if isinstance(value, str):
            text = _CONTROL_CHARS.sub("", value).strip()
            if text:
                return text[:60]
    return "（未命名）"


def parse_updates(body: object) -> UpdatesResult:
    """Distinct chats from a ``getUpdates`` body, newest update per chat."""
    if not isinstance(body, dict) or body.get("ok") is not True:
        return UpdatesResult(
            False, error="Telegram 回應格式無法辨識", error_kind="invalid_response"
        )
    updates = body.get("result")
    if not isinstance(updates, list):
        return UpdatesResult(
            False, error="Telegram 回應格式無法辨識", error_kind="invalid_response"
        )
    chats: dict[int, ChatCandidate] = {}
    max_update: int | None = None
    for update in updates:
        if not isinstance(update, dict):
            continue
        update_id = update.get("update_id")
        if not isinstance(update_id, int) or isinstance(update_id, bool):
            continue
        max_update = update_id if max_update is None else max(max_update, update_id)
        for kind in (*_UPDATE_KINDS, *_MEMBER_KINDS):
            payload = update.get(kind)
            chat = payload.get("chat") if isinstance(payload, dict) else None
            if not isinstance(chat, dict):
                continue
            chat_id = chat.get("id")
            if not isinstance(chat_id, int) or isinstance(chat_id, bool):
                continue
            previous = chats.get(chat_id)
            if previous is None or update_id > previous.update_id:
                chats[chat_id] = ChatCandidate(
                    chat_id=chat_id,
                    chat_type=str(chat.get("type") or "unknown"),
                    title=_chat_title(chat),
                    update_id=update_id,
                )
            break
    ordered = tuple(sorted(chats.values(), key=lambda c: c.update_id))
    return UpdatesResult(True, ordered, None if max_update is None else max_update + 1)


def _api_description(response: httpx.Response) -> str:
    try:
        data = response.json()
    except ValueError:
        return ""
    return str(data.get("description", "")) if isinstance(data, dict) else ""


class TelegramSetupClient:
    """``getUpdates`` / test send for the wizard. Never raises; every error is redacted."""

    def __init__(self, token: str, *, transport: httpx.BaseTransport | None = None) -> None:
        self._token = token
        self._transport = transport

    def get_updates(self, offset: int | None, long_poll_seconds: int) -> UpdatesResult:
        poll = max(int(long_poll_seconds), 0)
        params: dict[str, int] = {"timeout": poll}
        if offset is not None:
            params["offset"] = offset
        url = f"{API_BASE}/bot{self._token}/getUpdates"
        try:
            # The HTTP timeout must exceed the server-side long poll.
            timeout = poll + SETUP_TIMEOUT_MARGIN_SECONDS
            with httpx.Client(timeout=timeout, transport=self._transport) as client:
                response = client.get(url, params=params)
        except httpx.HTTPError as exc:
            detail = redact_truncate(f"{type(exc).__name__}: {exc}", 200)
            return UpdatesResult(False, error=f"{NETWORK_TEXT}（{detail}）", error_kind="network")
        except Exception as exc:  # defensive: the wizard must never print a traceback
            detail = redact_truncate(type(exc).__name__, 200)
            return UpdatesResult(False, error=f"{NETWORK_TEXT}（{detail}）", error_kind="network")
        if response.status_code == 401:
            return UpdatesResult(False, error=UNAUTHORIZED_TEXT, error_kind="unauthorized")
        if response.status_code == 409:
            return UpdatesResult(False, error=CONFLICT_TEXT, error_kind="conflict")
        if response.status_code != 200:
            description = redact_truncate(_api_description(response), 200)
            message = f"Telegram 回應 HTTP {response.status_code}：{description}".rstrip("：")
            return UpdatesResult(False, error=message, error_kind="http")
        try:
            body = response.json()
        except ValueError:
            body = None
        return parse_updates(body)

    def send_test(self, chat_id: str) -> SendResult:
        notifier = TelegramNotifier(
            self._token,
            chat_id,
            timeout_seconds=SEND_TEST_TIMEOUT_SECONDS,
            transport=self._transport,
        )
        result = notifier.send(telegram_test_message(utc_now()))
        if result.ok:
            return result
        error = result.error or "未知錯誤"
        if error.startswith("HTTP 401"):
            error = UNAUTHORIZED_TEXT
        return SendResult(ok=False, error=redact_truncate(error, 300))

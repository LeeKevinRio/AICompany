"""Tests for webhook delivery. Every request goes to a mock transport, never out.

No test in this file may reach the network: ``httpx.MockTransport`` answers
every request locally, and the "not configured" cases never build a client
request at all.
"""

from __future__ import annotations

from datetime import UTC, datetime

import httpx
import pytest

from app.alerts.models import AlertEvent
from app.alerts.notify import (
    DISCORD_WEBHOOK_ENV,
    TELEGRAM_CHAT_ID_ENV,
    TELEGRAM_TOKEN_ENV,
    format_message,
    notify,
    notify_all,
)

_EVENT = AlertEvent(
    id=1,
    rule_id=1,
    rule_type="price_above",
    symbol="2330",
    market="TW",
    message="2330 最新收盤價 700 TWD，高於設定的門檻 650 TWD。",
    observed={"close": 700.0, "threshold": 650.0},
    triggered_at=datetime(2026, 7, 25, 6, 0, tzinfo=UTC),
    acknowledged=False,
    acknowledged_at=None,
)


@pytest.fixture(autouse=True)
def _clear_webhook_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """Never inherit a real webhook from the developer's environment."""
    for name in (DISCORD_WEBHOOK_ENV, TELEGRAM_TOKEN_ENV, TELEGRAM_CHAT_ID_ENV):
        monkeypatch.delenv(name, raising=False)


def _client(handler: object) -> httpx.Client:
    return httpx.Client(transport=httpx.MockTransport(handler))  # type: ignore[arg-type]


def test_message_states_the_observation_and_the_disclaimer() -> None:
    text = format_message(_EVENT)
    assert "2330" in text
    assert _EVENT.message in text
    assert "非投資建議" in text


def test_both_channels_are_skipped_without_configuration() -> None:
    def handler(request: httpx.Request) -> httpx.Response:  # pragma: no cover - never called
        raise AssertionError("no request may be made when nothing is configured")

    results = notify(_EVENT, client=_client(handler))
    assert {result.channel: result.status for result in results} == {
        "discord": "skipped",
        "telegram": "skipped",
    }


def test_discord_delivery_posts_the_message(monkeypatch: pytest.MonkeyPatch) -> None:
    seen: list[tuple[str, bytes]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append((str(request.url), request.content))
        return httpx.Response(204)

    monkeypatch.setenv(DISCORD_WEBHOOK_ENV, "https://discord.test/hook")
    results = notify(_EVENT, client=_client(handler))
    assert [r.status for r in results] == ["sent", "skipped"]
    assert seen[0][0] == "https://discord.test/hook"
    assert "2330" in seen[0][1].decode()


def test_telegram_needs_both_token_and_chat_id(monkeypatch: pytest.MonkeyPatch) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"ok": True})

    monkeypatch.setenv(TELEGRAM_TOKEN_ENV, "token-123")
    only_token = notify(_EVENT, client=_client(handler))
    assert only_token[1].status == "skipped"

    monkeypatch.setenv(TELEGRAM_CHAT_ID_ENV, "42")
    both = notify(_EVENT, client=_client(handler))
    assert both[1].status == "sent"


def test_a_failing_webhook_is_reported_not_raised(monkeypatch: pytest.MonkeyPatch) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(500, text="boom")

    monkeypatch.setenv(DISCORD_WEBHOOK_ENV, "https://discord.test/hook")
    results = notify(_EVENT, client=_client(handler))
    assert results[0].status == "failed"
    assert results[0].detail


def test_a_transport_error_is_contained(monkeypatch: pytest.MonkeyPatch) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("network down")

    monkeypatch.setenv(DISCORD_WEBHOOK_ENV, "https://discord.test/hook")
    results = notify(_EVENT, client=_client(handler))
    assert results[0].status == "failed"


def test_notify_all_covers_every_event(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(str(request.url))
        return httpx.Response(204)

    monkeypatch.setenv(DISCORD_WEBHOOK_ENV, "https://discord.test/hook")
    second = _EVENT.model_copy(update={"id": 2})
    results = notify_all([_EVENT, second], client=_client(handler))
    assert len(calls) == 2
    assert [r.status for r in results if r.channel == "discord"] == ["sent", "sent"]


def test_notify_all_of_nothing_does_nothing() -> None:
    assert notify_all([]) == []


def test_notify_owns_and_closes_its_client_when_none_is_supplied() -> None:
    # No channel is configured (the autouse fixture cleared the env), so this
    # builds and closes a real client without ever issuing a request.
    results = notify(_EVENT)
    assert [result.status for result in results] == ["skipped", "skipped"]

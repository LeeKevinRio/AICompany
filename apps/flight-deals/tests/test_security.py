"""Secret redaction and Telegram request shape (C-10, C-11)."""

from __future__ import annotations

import io
import json
import logging
from pathlib import Path

import httpx
from fastapi.testclient import TestClient

from flight_deals.app import create_app
from flight_deals.config import Config
from flight_deals.logging_setup import setup_logging
from flight_deals.notify.telegram import TelegramNotifier
from flight_deals.redact import redact, register_secret
from tests.conftest import CLIENT_HEADERS, FakeClock, ScriptedSource

FAKE_TOKEN = "987654321:AAH-fake_TOKEN_valueForRedactionTests"
FAKE_CHAT = "556677"


def failing_transport() -> httpx.MockTransport:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError(
            f"All connection attempts failed for {request.url}", request=request
        )

    return httpx.MockTransport(handler)


def test_redact_masks_bot_urls_and_registered_secrets() -> None:
    text = f"POST https://api.telegram.org/bot{FAKE_TOKEN}/sendMessage failed"
    assert FAKE_TOKEN not in redact(text)
    assert "AAH-fake_TOKEN" not in redact(text)
    register_secret("plain-secret-value")
    assert "plain-secret-value" not in redact("oops plain-secret-value leaked")


def test_telegram_payload_has_no_parse_mode() -> None:  # C-10
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(200, json={"ok": True, "result": {}})

    notifier = TelegramNotifier(FAKE_TOKEN, FAKE_CHAT, transport=httpx.MockTransport(handler))
    result = notifier.send("<b>hello</b> *world*")
    assert result.ok
    [request] = seen
    body = json.loads(request.content)
    assert body == {"chat_id": FAKE_CHAT, "text": "<b>hello</b> *world*"}
    assert "parse_mode" not in body
    assert request.url.path == f"/bot{FAKE_TOKEN}/sendMessage"


def test_telegram_failure_does_not_raise_and_is_redacted() -> None:  # C-10, C-11
    notifier = TelegramNotifier(FAKE_TOKEN, FAKE_CHAT, transport=failing_transport())
    result = notifier.send("x")
    assert not result.ok
    assert result.error and "ConnectError" in result.error
    assert FAKE_TOKEN not in result.error and "AAH-fake" not in result.error


def test_telegram_http_error_reported() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(401, json={"ok": False, "description": "Unauthorized"})

    notifier = TelegramNotifier(FAKE_TOKEN, FAKE_CHAT, transport=httpx.MockTransport(handler))
    result = notifier.send("x")
    assert not result.ok and result.error == "HTTP 401: Unauthorized"


def test_logs_never_contain_token() -> None:  # C-11
    stream = io.StringIO()
    handler = setup_logging(logging.DEBUG, stream=stream)
    try:
        register_secret(FAKE_TOKEN)
        logging.getLogger("httpx").warning(
            "HTTP Request: POST https://api.telegram.org/bot%s/sendMessage", FAKE_TOKEN
        )
        logging.getLogger("httpx").info("info-level httpx lines are silenced %s", FAKE_TOKEN)
        try:
            raise RuntimeError(f"boom https://api.telegram.org/bot{FAKE_TOKEN}/x")
        except RuntimeError:
            logging.getLogger("flight_deals.test").exception("failure with %s", FAKE_CHAT)
        output = stream.getvalue()
        assert "bot***" in output
        assert FAKE_TOKEN not in output and "AAH-fake" not in output
        assert "silenced" not in output
        assert logging.getLogger("httpcore").level == logging.WARNING
    finally:
        logging.getLogger().removeHandler(handler)


def test_db_and_api_never_store_token(tmp_path: Path, clock: FakeClock) -> None:  # C-11
    stream = io.StringIO()
    handler = setup_logging(logging.INFO, stream=stream)
    try:
        config = Config(
            db_path=tmp_path / "sec.db", telegram_bot_token=FAKE_TOKEN, telegram_chat_id=FAKE_CHAT
        )
        notifier = TelegramNotifier(FAKE_TOKEN, FAKE_CHAT, transport=failing_transport())
        source = ScriptedSource(clock)
        app = create_app(
            config, sources=[source], notifier=notifier, clock=clock, start_scheduler=False
        )
        with TestClient(app, base_url="http://127.0.0.1") as client:
            response = client.post("/api/telegram/test", headers=CLIENT_HEADERS)
            assert response.status_code == 502
            assert FAKE_TOKEN not in response.text
            services = app.state.assembly.services
            watch_id = services.watches.create(
                {
                    "destination": "NRT",
                    "depart_date": "2026-12-10",
                    "return_date": "2026-12-15",
                    "budget": 20000,
                }
            ).watch_id
            services.scan.scan_watch(watch_id)
            for page in ("/notifications", "/settings"):
                assert FAKE_TOKEN not in client.get(page).text
        raw = (tmp_path / "sec.db").read_bytes()
        wal = tmp_path / "sec.db-wal"
        if wal.exists():
            raw += wal.read_bytes()
        assert FAKE_TOKEN.encode() not in raw
        assert b"AAH-fake" not in raw
        assert FAKE_TOKEN not in stream.getvalue()
    finally:
        logging.getLogger().removeHandler(handler)

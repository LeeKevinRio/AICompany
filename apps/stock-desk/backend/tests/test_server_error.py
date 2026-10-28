"""An unhandled exception reaches the browser as a 500 it can read (N-154).

Without :class:`CorsVisibleServerErrorMiddleware` Starlette answered from
outside CORS, so the frontend saw a CORS failure and ``net::ERR_FAILED``
instead of the server error.
"""

from __future__ import annotations

import asyncio
from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient
from starlette.types import Message, Receive, Scope, Send

from app.alerts.store import AlertStore
from app.api.deps import get_alert_store
from app.api.server_error import CorsVisibleServerErrorMiddleware
from app.main import FRONTEND_DEV_ORIGIN, app
from tests.api_helpers import CLIENT_HEADERS


class _Boom(RuntimeError):
    pass


def _broken_store() -> AlertStore:
    raise _Boom("store construction failed")


@pytest.fixture
def broken_alerts() -> Iterator[None]:
    app.dependency_overrides[get_alert_store] = _broken_store
    try:
        yield
    finally:
        app.dependency_overrides.clear()


@pytest.mark.usefixtures("broken_alerts")
def test_an_unhandled_exception_is_a_500_that_carries_the_cors_header() -> None:
    headers = {**CLIENT_HEADERS, "Origin": FRONTEND_DEV_ORIGIN}
    with TestClient(app, headers=headers, raise_server_exceptions=False) as client:
        response = client.get("/api/alerts/events", params={"unacknowledged": "true"})

    assert response.status_code == 500
    assert response.text == "Internal Server Error"
    assert response.headers["access-control-allow-origin"] == FRONTEND_DEV_ORIGIN


@pytest.mark.usefixtures("broken_alerts")
def test_the_exception_still_propagates_to_the_server() -> None:
    """The traceback must still be logged: the exception is re-raised, not swallowed."""
    with TestClient(app, headers=CLIENT_HEADERS) as client:
        with pytest.raises(_Boom, match="store construction failed"):
            client.get("/api/alerts/events")


def test_an_exception_after_the_response_started_is_only_re_raised() -> None:
    """A second ``http.response.start`` would be a protocol error; nothing more is sent."""

    async def streaming_then_failing(scope: Scope, receive: Receive, send: Send) -> None:
        await send({"type": "http.response.start", "status": 200, "headers": []})
        raise _Boom("mid-stream")

    sent: list[Message] = []

    async def receive() -> Message:
        return {"type": "http.request", "body": b"", "more_body": False}

    async def send(message: Message) -> None:
        sent.append(message)

    middleware = CorsVisibleServerErrorMiddleware(streaming_then_failing)
    scope: Scope = {"type": "http", "method": "GET", "path": "/", "headers": []}
    with pytest.raises(_Boom, match="mid-stream"):
        asyncio.run(middleware(scope, receive, send))

    assert [message["type"] for message in sent] == ["http.response.start"]
    assert sent[0]["status"] == 200

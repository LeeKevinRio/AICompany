"""Tests for the shared rate-limited / retrying HTTP client wrapper."""

from __future__ import annotations

import httpx
import pytest

from app.data.http import RateLimitedClient


def _make_client(
    handler: httpx.MockTransport,
    *,
    min_interval_seconds: float = 0.0,
    max_retries: int = 3,
    backoff_seconds: tuple[float, ...] = (0.0, 0.0, 0.0),
    sleep_fn: object = None,
) -> RateLimitedClient:
    calls: list[float] = []

    def default_sleep(seconds: float) -> None:
        calls.append(seconds)

    return RateLimitedClient(
        base_url="https://example.test",
        min_interval_seconds=min_interval_seconds,
        max_retries=max_retries,
        backoff_seconds=backoff_seconds,
        transport=handler,
        sleep_fn=sleep_fn if sleep_fn is not None else default_sleep,  # type: ignore[arg-type]
    )


def test_get_returns_response_on_first_success() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"ok": True})

    client = _make_client(httpx.MockTransport(handler))
    response = client.get("/ping")
    assert response.status_code == 200
    assert response.json() == {"ok": True}


def test_does_not_retry_4xx() -> None:
    call_count = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal call_count
        call_count += 1
        return httpx.Response(404)

    client = _make_client(httpx.MockTransport(handler))
    response = client.get("/missing")
    assert response.status_code == 404
    assert call_count == 1


def test_retries_5xx_up_to_max_retries_then_returns_last_response() -> None:
    call_count = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal call_count
        call_count += 1
        return httpx.Response(503)

    sleeps: list[float] = []
    client = _make_client(
        httpx.MockTransport(handler),
        max_retries=2,
        backoff_seconds=(1.0, 2.0, 4.0),
        sleep_fn=lambda s: sleeps.append(s),
    )
    response = client.get("/flaky")
    assert response.status_code == 503
    # 1 initial attempt + 2 retries = 3 calls total.
    assert call_count == 3
    # Backoff schedule observed for the 2 retries.
    assert sleeps == [1.0, 2.0]


def test_recovers_after_transient_5xx() -> None:
    call_count = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal call_count
        call_count += 1
        if call_count < 3:
            return httpx.Response(500)
        return httpx.Response(200, json={"recovered": True})

    client = _make_client(httpx.MockTransport(handler), max_retries=3)
    response = client.get("/eventually-ok")
    assert response.status_code == 200
    assert response.json() == {"recovered": True}
    assert call_count == 3


def test_retries_transport_error_then_raises_after_exhausting() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("boom", request=request)

    sleeps: list[float] = []
    client = _make_client(
        httpx.MockTransport(handler),
        max_retries=2,
        sleep_fn=lambda s: sleeps.append(s),
    )
    with pytest.raises(httpx.ConnectError):
        client.get("/down")
    assert len(sleeps) == 2


def test_recovers_after_transient_transport_error() -> None:
    call_count = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal call_count
        call_count += 1
        if call_count < 2:
            raise httpx.ConnectError("boom", request=request)
        return httpx.Response(200, json={"ok": True})

    client = _make_client(httpx.MockTransport(handler), max_retries=3)
    response = client.get("/flaky-connect")
    assert response.status_code == 200
    assert call_count == 2


def test_rate_limit_enforces_minimum_interval_between_requests() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200)

    sleeps: list[float] = []
    client = _make_client(
        httpx.MockTransport(handler),
        min_interval_seconds=1.0,
        sleep_fn=lambda s: sleeps.append(s),
    )
    client.get("/a")
    client.get("/b")
    # First call: nothing to wait for. Second call: throttled close to 1s.
    assert len(sleeps) == 1
    assert sleeps[0] > 0.9

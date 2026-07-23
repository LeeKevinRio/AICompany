"""Contract tests for the FinMind backup adapter, driven entirely by offline fixtures."""

from __future__ import annotations

import json
from datetime import date
from pathlib import Path

import httpx
import pytest

from app.data.http import RateLimitedClient
from app.data.interface import DataStatus
from app.data.providers.finmind import TOKEN_ENV_VAR, FinMindAdapter

FIXTURES_DIR = Path(__file__).parent / "fixtures"


def _fixture_json(name: str) -> dict[str, object]:
    return json.loads((FIXTURES_DIR / name).read_text(encoding="utf-8"))  # type: ignore[no-any-return]


def _adapter_with_handler(handler: httpx.MockTransport) -> FinMindAdapter:
    client = RateLimitedClient(
        base_url="https://api.finmindtrade.com",
        min_interval_seconds=0.0,
        transport=handler,
        sleep_fn=lambda _seconds: None,
    )
    return FinMindAdapter(client=client)


def test_returns_unavailable_without_raising_when_token_missing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv(TOKEN_ENV_VAR, raising=False)
    call_count = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal call_count
        call_count += 1
        return httpx.Response(200, json={"status": 200, "data": []})

    adapter = _adapter_with_handler(httpx.MockTransport(handler))
    result = adapter.get_daily_bars("2330", date(2024, 1, 1), date(2024, 1, 31))

    assert result.status is DataStatus.UNAVAILABLE
    assert result.bars == []
    assert call_count == 0  # must not even attempt the request without a token


def test_get_daily_bars_parses_fixture_with_token(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(TOKEN_ENV_VAR, "fixture-test-token-not-real")
    payload = _fixture_json("finmind_taiwan_stock_price_2330.json")

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.params["data_id"] == "2330"
        assert request.url.params["token"] == "fixture-test-token-not-real"
        return httpx.Response(200, json=payload)

    adapter = _adapter_with_handler(httpx.MockTransport(handler))
    result = adapter.get_daily_bars("2330", date(2024, 1, 1), date(2024, 1, 31))

    assert result.status is DataStatus.FRESH
    assert result.source == "finmind"
    assert [bar.date for bar in result.bars] == [date(2024, 1, 2), date(2024, 1, 3)]
    first = result.bars[0]
    assert first.volume == 41_393_088
    assert str(first.close) == "594.0"


def test_returns_unavailable_when_body_status_is_not_200(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(TOKEN_ENV_VAR, "fixture-test-token-not-real")

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"status": 402, "msg": "rate limit exceeded"})

    adapter = _adapter_with_handler(httpx.MockTransport(handler))
    result = adapter.get_daily_bars("2330", date(2024, 1, 1), date(2024, 1, 31))
    assert result.status is DataStatus.UNAVAILABLE


def test_returns_unavailable_on_transport_error(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(TOKEN_ENV_VAR, "fixture-test-token-not-real")

    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("boom", request=request)

    client = RateLimitedClient(
        base_url="https://api.finmindtrade.com",
        max_retries=1,
        transport=httpx.MockTransport(handler),
        sleep_fn=lambda _seconds: None,
    )
    adapter = FinMindAdapter(client=client)
    result = adapter.get_daily_bars("2330", date(2024, 1, 1), date(2024, 1, 31))
    assert result.status is DataStatus.UNAVAILABLE

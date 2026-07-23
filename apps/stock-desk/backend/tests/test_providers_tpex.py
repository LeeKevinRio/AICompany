"""Contract tests for the TPEx adapter, driven entirely by offline fixtures."""

from __future__ import annotations

import json
from datetime import date
from pathlib import Path

import httpx

from app.data.http import RateLimitedClient
from app.data.interface import DataStatus
from app.data.providers.tpex import TpexAdapter

FIXTURES_DIR = Path(__file__).parent / "fixtures"


def _fixture_json(name: str) -> dict[str, object]:
    return json.loads((FIXTURES_DIR / name).read_text(encoding="utf-8"))  # type: ignore[no-any-return]


def _adapter_with_handler(handler: httpx.MockTransport) -> TpexAdapter:
    client = RateLimitedClient(
        base_url="https://www.tpex.org.tw",
        min_interval_seconds=0.0,
        transport=handler,
        sleep_fn=lambda _seconds: None,
    )
    return TpexAdapter(client=client)


def test_get_daily_bars_parses_fixture() -> None:
    payload = _fixture_json("tpex_daily_trading_5483_202401.json")

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.params["stkno"] == "5483"
        return httpx.Response(200, json=payload)

    adapter = _adapter_with_handler(httpx.MockTransport(handler))
    result = adapter.get_daily_bars("5483", date(2024, 1, 1), date(2024, 1, 31))

    assert result.status is DataStatus.FRESH
    assert result.source == "tpex"
    assert result.as_of.tzinfo is not None
    assert [bar.date for bar in result.bars] == [date(2024, 1, 2), date(2024, 1, 3)]
    first = result.bars[0]
    assert first.symbol == "5483"
    assert first.market == "TW"
    assert first.currency == "TWD"
    assert first.volume == 1_234_000
    assert str(first.close) == "45.80"


def test_returns_unavailable_on_transport_error_without_raising() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("boom", request=request)

    client = RateLimitedClient(
        base_url="https://www.tpex.org.tw",
        max_retries=1,
        transport=httpx.MockTransport(handler),
        sleep_fn=lambda _seconds: None,
    )
    adapter = TpexAdapter(client=client)
    result = adapter.get_daily_bars("5483", date(2024, 1, 1), date(2024, 1, 31))
    assert result.status is DataStatus.UNAVAILABLE
    assert result.bars == []


def test_returns_unavailable_when_stat_not_ok() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"stat": "error"})

    adapter = _adapter_with_handler(httpx.MockTransport(handler))
    result = adapter.get_daily_bars("0000", date(2024, 1, 1), date(2024, 1, 31))
    assert result.status is DataStatus.UNAVAILABLE

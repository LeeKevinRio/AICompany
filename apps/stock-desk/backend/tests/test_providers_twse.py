"""Contract tests for the TWSE adapter, driven entirely by offline fixtures."""

from __future__ import annotations

import json
from datetime import date
from pathlib import Path

import httpx

from app.data.http import RateLimitedClient
from app.data.interface import DataStatus
from app.data.providers.twse import TwseAdapter

FIXTURES_DIR = Path(__file__).parent / "fixtures"


def _fixture_json(name: str) -> dict[str, object]:
    return json.loads((FIXTURES_DIR / name).read_text(encoding="utf-8"))  # type: ignore[no-any-return]


def _adapter_with_handler(handler: httpx.MockTransport) -> TwseAdapter:
    client = RateLimitedClient(
        base_url="https://www.twse.com.tw",
        min_interval_seconds=0.0,
        transport=handler,
        sleep_fn=lambda _seconds: None,
    )
    return TwseAdapter(client=client)


def test_get_daily_bars_parses_fixture_and_skips_no_trade_rows() -> None:
    payload = _fixture_json("twse_stock_day_2330_202401.json")

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.params["stockNo"] == "2330"
        return httpx.Response(200, json=payload)

    adapter = _adapter_with_handler(httpx.MockTransport(handler))
    result = adapter.get_daily_bars("2330", date(2024, 1, 1), date(2024, 1, 31))

    assert result.status is DataStatus.FRESH
    assert result.source == "twse"
    assert result.as_of.tzinfo is not None
    # The 113/01/04 row is all "--" placeholders and must be skipped, not fabricated.
    expected_dates = [date(2024, 1, 2), date(2024, 1, 3), date(2024, 1, 5)]
    assert [bar.date for bar in result.bars] == expected_dates
    first = result.bars[0]
    assert first.symbol == "2330"
    assert first.market == "TW"
    assert first.currency == "TWD"
    assert first.volume == 41_393_088
    assert str(first.open) == "594.00"
    assert first.source == "twse"


def test_get_daily_bars_filters_to_requested_range() -> None:
    payload = _fixture_json("twse_stock_day_2330_202401.json")

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=payload)

    adapter = _adapter_with_handler(httpx.MockTransport(handler))
    result = adapter.get_daily_bars("2330", date(2024, 1, 2), date(2024, 1, 2))
    assert [bar.date for bar in result.bars] == [date(2024, 1, 2)]


def test_returns_unavailable_on_transport_error_without_raising() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("boom", request=request)

    client = RateLimitedClient(
        base_url="https://www.twse.com.tw",
        max_retries=1,
        transport=httpx.MockTransport(handler),
        sleep_fn=lambda _seconds: None,
    )
    adapter = TwseAdapter(client=client)
    result = adapter.get_daily_bars("2330", date(2024, 1, 1), date(2024, 1, 31))
    assert result.status is DataStatus.UNAVAILABLE
    assert result.bars == []
    assert result.source == "twse"


def test_returns_unavailable_when_stat_not_ok() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"stat": "很抱歉，沒有符合條件的資料！"})

    adapter = _adapter_with_handler(httpx.MockTransport(handler))
    result = adapter.get_daily_bars("9999", date(2024, 1, 1), date(2024, 1, 31))
    assert result.status is DataStatus.UNAVAILABLE
    assert result.bars == []

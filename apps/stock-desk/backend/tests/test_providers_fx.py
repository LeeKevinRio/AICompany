"""Contract tests for the Bank of Taiwan USD/TWD FX adapter, offline fixture only."""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from pathlib import Path

import httpx

from app.data.http import RateLimitedClient
from app.data.interface import DataStatus
from app.data.providers.fx import BankOfTaiwanFxAdapter

FIXTURES_DIR = Path(__file__).parent / "fixtures"
FIXTURE_CSV = (FIXTURES_DIR / "bot_fx_usd_twd_20240102.csv").read_text(encoding="utf-8")


def _adapter_with_handler(handler: httpx.MockTransport) -> BankOfTaiwanFxAdapter:
    client = RateLimitedClient(
        base_url="https://rate.bot.com.tw",
        min_interval_seconds=0.0,
        transport=handler,
        sleep_fn=lambda _seconds: None,
    )
    return BankOfTaiwanFxAdapter(client=client)


def test_get_daily_rates_parses_spot_mid_rate() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("2024-01-02"):
            return httpx.Response(200, text=FIXTURE_CSV)
        return httpx.Response(404)

    adapter = _adapter_with_handler(httpx.MockTransport(handler))
    result = adapter.get_daily_rates("USDTWD", date(2024, 1, 2), date(2024, 1, 2))

    assert result.status is DataStatus.FRESH
    assert result.source == "bank_of_taiwan"
    assert len(result.rates) == 1
    rate = result.rates[0]
    assert rate.date == date(2024, 1, 2)
    # Mid of spot buy 32.195 and spot sell 32.395, NOT the cash rate columns.
    assert rate.rate == (Decimal("32.195") + Decimal("32.395")) / Decimal(2)
    assert rate.as_of.tzinfo is not None


def test_days_without_data_are_absent_not_fabricated() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("2024-01-02"):
            return httpx.Response(200, text=FIXTURE_CSV)
        return httpx.Response(404)

    adapter = _adapter_with_handler(httpx.MockTransport(handler))
    result = adapter.get_daily_rates("USDTWD", date(2024, 1, 2), date(2024, 1, 4))
    assert result.status is DataStatus.FRESH
    assert [rate.date for rate in result.rates] == [date(2024, 1, 2)]


def test_unavailable_when_header_schema_unrecognized() -> None:
    broken_csv = "幣別,幣別,現金,現金\nUSD,美金,31.845,32.515\n"

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, text=broken_csv)

    adapter = _adapter_with_handler(httpx.MockTransport(handler))
    result = adapter.get_daily_rates("USDTWD", date(2024, 1, 2), date(2024, 1, 2))
    assert result.status is DataStatus.UNAVAILABLE
    assert result.rates == []


def test_unavailable_on_transport_error() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("boom", request=request)

    client = RateLimitedClient(
        base_url="https://rate.bot.com.tw",
        max_retries=1,
        transport=httpx.MockTransport(handler),
        sleep_fn=lambda _seconds: None,
    )
    adapter = BankOfTaiwanFxAdapter(client=client)
    result = adapter.get_daily_rates("USDTWD", date(2024, 1, 2), date(2024, 1, 2))
    assert result.status is DataStatus.UNAVAILABLE

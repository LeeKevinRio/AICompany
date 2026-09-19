"""Contract tests for the yfinance-backed FX backup adapter (ADR-0011).

Offline fixture only, per the data-source-integration skill.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from pathlib import Path

import httpx
import pytest

from app.data.http import RateLimitedClient
from app.data.interface import DataStatus
from app.data.providers.fx_yfinance import YFinanceFxAdapter, _to_yahoo_fx_symbol
from app.data.providers.yfinance import YFinanceAdapter

FIXTURES_DIR = Path(__file__).parent / "fixtures"
FIXTURE_TWD_X = (FIXTURES_DIR / "yfinance_chart_twd_x.json").read_text(encoding="utf-8")


def _adapter_with_handler(handler: httpx.MockTransport) -> YFinanceFxAdapter:
    client = RateLimitedClient(
        base_url="https://query1.finance.yahoo.com",
        min_interval_seconds=0.0,
        transport=handler,
        sleep_fn=lambda _seconds: None,
    )
    return YFinanceFxAdapter(adapter=YFinanceAdapter(client=client))


def test_to_yahoo_fx_symbol_usd_base_uses_shorthand() -> None:
    assert _to_yahoo_fx_symbol("USDTWD") == "TWD=X"


def test_to_yahoo_fx_symbol_non_usd_base_uses_general_cross_form() -> None:
    assert _to_yahoo_fx_symbol("EURTWD") == "EURTWD=X"


def test_to_yahoo_fx_symbol_rejects_malformed_pair() -> None:
    with pytest.raises(ValueError):
        _to_yahoo_fx_symbol("US")


def test_get_daily_rates_parses_close_as_the_days_rate() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert "TWD" in request.url.path
        return httpx.Response(200, text=FIXTURE_TWD_X)

    adapter = _adapter_with_handler(httpx.MockTransport(handler))
    result = adapter.get_daily_rates("USDTWD", date(2024, 1, 2), date(2024, 1, 5))

    assert result.status is DataStatus.BACKUP
    assert result.source == "yfinance_fx"
    assert len(result.rates) == 4
    first = result.rates[0]
    assert first.pair == "USDTWD"
    assert first.rate == Decimal("31.305")
    assert first.as_of.tzinfo is not None
    assert [rate.date for rate in result.rates] == sorted(rate.date for rate in result.rates)


def test_status_is_always_backup_never_fresh() -> None:
    """ADR-0011 mirrors ADR-0005's non-official-source discipline: never FRESH."""

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, text=FIXTURE_TWD_X)

    adapter = _adapter_with_handler(httpx.MockTransport(handler))
    result = adapter.get_daily_rates("USDTWD", date(2024, 1, 2), date(2024, 1, 2))
    assert result.status is DataStatus.BACKUP


def test_unavailable_when_yahoo_reports_an_error() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200, json={"chart": {"result": None, "error": {"description": "No data found"}}}
        )

    adapter = _adapter_with_handler(httpx.MockTransport(handler))
    result = adapter.get_daily_rates("USDTWD", date(2024, 1, 2), date(2024, 1, 2))
    assert result.status is DataStatus.UNAVAILABLE
    assert result.rates == []
    assert result.reason is not None


def test_unavailable_on_transport_error() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("boom", request=request)

    adapter = _adapter_with_handler(httpx.MockTransport(handler))
    result = adapter.get_daily_rates("USDTWD", date(2024, 1, 2), date(2024, 1, 2))
    assert result.status is DataStatus.UNAVAILABLE


def test_unsupported_pair_shape_is_unavailable_not_a_raised_exception() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise AssertionError("must not issue a request for a malformed pair")

    adapter = _adapter_with_handler(httpx.MockTransport(handler))
    result = adapter.get_daily_rates("NOTAPAIR", date(2024, 1, 2), date(2024, 1, 2))
    assert result.status is DataStatus.UNAVAILABLE
    assert result.reason is not None


def test_owns_adapter_lifecycle_only_when_not_injected() -> None:
    """When an existing ``YFinanceAdapter`` is passed in, ``close()`` must not close it."""
    closed = {"count": 0}

    class _SpyAdapter(YFinanceAdapter):
        def close(self) -> None:
            closed["count"] += 1
            super().close()

    inner = _SpyAdapter()
    fx_adapter = YFinanceFxAdapter(adapter=inner)
    fx_adapter.close()
    assert closed["count"] == 0

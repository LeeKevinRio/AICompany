"""Contract tests for the TWSE/TPEx directory adapters, offline fixtures only."""

from __future__ import annotations

import json
from pathlib import Path

import httpx

from app.data.http import RateLimitedClient
from app.directory.providers import (
    TPEX_OPENAPI_BASE_URL,
    TWSE_OPENAPI_BASE_URL,
    TpexDirectoryAdapter,
    TwseDirectoryAdapter,
    TwseSectorProfileAdapter,
)

FIXTURES_DIR = Path(__file__).parent / "fixtures"


def _fixture_json(name: str) -> list[object]:
    return json.loads((FIXTURES_DIR / name).read_text(encoding="utf-8"))  # type: ignore[no-any-return]


def _mock_client(base_url: str, handler: httpx.MockTransport) -> RateLimitedClient:
    return RateLimitedClient(
        base_url=base_url, min_interval_seconds=0.0, transport=handler, sleep_fn=lambda _s: None
    )


# --------------------------------------------------------------------------
# TWSE
# --------------------------------------------------------------------------


def test_twse_fetch_parses_fixture_and_skips_blank_code() -> None:
    payload = _fixture_json("twse_openapi_stock_day_all.json")

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=payload)

    client = _mock_client(TWSE_OPENAPI_BASE_URL, httpx.MockTransport(handler))
    adapter = TwseDirectoryAdapter(client=client)
    result = adapter.fetch()

    assert result.ok
    assert result.source == "twse_openapi"
    assert result.as_of.tzinfo is not None
    symbols = {entry.symbol for entry in result.entries}
    assert symbols == {"2330", "0050", "3037"}
    by_symbol = {entry.symbol: entry for entry in result.entries}
    assert by_symbol["2330"].name == "台積電"
    assert by_symbol["2330"].market == "TW"
    assert by_symbol["2330"].source == "twse_openapi"


def test_twse_fetch_reports_transport_error_without_raising() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("connection refused", request=request)

    adapter = TwseDirectoryAdapter(
        client=RateLimitedClient(
            base_url=TWSE_OPENAPI_BASE_URL,
            min_interval_seconds=0.0,
            max_retries=0,
            transport=httpx.MockTransport(handler),
            sleep_fn=lambda _s: None,
        )
    )
    result = adapter.fetch()

    assert result.ok is False
    assert result.entries == ()
    assert result.reason is not None
    assert "連線失敗" in result.reason
    assert "CEO 本機" in result.reason


def test_twse_fetch_reports_non_200_status() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(404, text="not found")

    client = _mock_client(TWSE_OPENAPI_BASE_URL, httpx.MockTransport(handler))
    adapter = TwseDirectoryAdapter(client=client)
    result = adapter.fetch()

    assert result.ok is False
    assert "404" in (result.reason or "")


def test_twse_fetch_reports_non_array_payload() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"stat": "unexpected"})

    client = _mock_client(TWSE_OPENAPI_BASE_URL, httpx.MockTransport(handler))
    adapter = TwseDirectoryAdapter(client=client)
    result = adapter.fetch()

    assert result.ok is False
    assert "schema" in (result.reason or "")


# --------------------------------------------------------------------------
# TPEx
# --------------------------------------------------------------------------


def test_tpex_fetch_parses_fixture_and_skips_blank_name() -> None:
    payload = _fixture_json("tpex_openapi_mainboard_daily_close_quotes.json")

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=payload)

    client = _mock_client(TPEX_OPENAPI_BASE_URL, httpx.MockTransport(handler))
    adapter = TpexDirectoryAdapter(client=client)
    result = adapter.fetch()

    assert result.ok
    assert result.source == "tpex_openapi"
    symbols = [entry.symbol for entry in result.entries]
    # Duplicate 5483 row with blank name must be skipped -- only one 5483 kept.
    assert symbols.count("5483") == 1
    assert set(symbols) == {"5483", "6488", "3105"}
    by_symbol = {entry.symbol: entry for entry in result.entries}
    assert by_symbol["5483"].name == "中美晶"
    assert by_symbol["5483"].market == "TW"


def test_tpex_fetch_reports_transport_error_without_raising() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectTimeout("timed out", request=request)

    adapter = TpexDirectoryAdapter(
        client=RateLimitedClient(
            base_url=TPEX_OPENAPI_BASE_URL,
            min_interval_seconds=0.0,
            max_retries=0,
            transport=httpx.MockTransport(handler),
            sleep_fn=lambda _s: None,
        )
    )
    result = adapter.fetch()

    assert result.ok is False
    assert result.entries == ()
    assert "連線失敗" in (result.reason or "")


# --------------------------------------------------------------------------
# TWSE sector profile (t187ap03_L) -- feeds app.directory.sector_audit only
# --------------------------------------------------------------------------


def test_twse_sector_profile_fetch_parses_fixture_and_skips_blank_rows() -> None:
    payload = _fixture_json("twse_openapi_t187ap03_l.json")

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=payload)

    client = _mock_client(TWSE_OPENAPI_BASE_URL, httpx.MockTransport(handler))
    adapter = TwseSectorProfileAdapter(client=client)
    result = adapter.fetch()

    assert result.ok
    assert result.source == "twse_openapi_t187ap03_L"
    assert result.as_of.tzinfo is not None
    symbols = {entry.symbol for entry in result.entries}
    # Blank-代號 row and blank-產業別 row must both be skipped.
    assert symbols == {"2330", "2317", "1101", "9188", "9921"}
    by_symbol = {entry.symbol: entry for entry in result.entries}
    # 產業別 is TWSE's raw two-digit code (confirmed by CEO's 2026-08-12 real
    # run), not a Chinese name -- resolving it to a name is the comparison
    # layer's job (app.directory.sector_audit), not this adapter's.
    assert by_symbol["2330"].sector == "24"
    assert by_symbol["2330"].name == "台積電"
    assert by_symbol["2330"].source == "twse_openapi_t187ap03_L"
    # Codes this adapter has never seen before (e.g. "99") are kept verbatim
    # too -- flagging an unrecognized code is the comparison layer's job.
    assert by_symbol["9921"].sector == "99"


def test_twse_sector_profile_fetch_reports_transport_error_without_raising() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("connection refused", request=request)

    adapter = TwseSectorProfileAdapter(
        client=RateLimitedClient(
            base_url=TWSE_OPENAPI_BASE_URL,
            min_interval_seconds=0.0,
            max_retries=0,
            transport=httpx.MockTransport(handler),
            sleep_fn=lambda _s: None,
        )
    )
    result = adapter.fetch()

    assert result.ok is False
    assert result.entries == ()
    assert result.reason is not None
    assert "連線失敗" in result.reason
    assert "CEO 本機" in result.reason


def test_twse_sector_profile_fetch_reports_non_array_payload() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"stat": "unexpected"})

    client = _mock_client(TWSE_OPENAPI_BASE_URL, httpx.MockTransport(handler))
    adapter = TwseSectorProfileAdapter(client=client)
    result = adapter.fetch()

    assert result.ok is False
    assert "schema" in (result.reason or "")

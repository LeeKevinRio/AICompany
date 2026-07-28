"""Contract tests for the yfinance adapter, driven entirely by offline fixtures.

Two roles are tested separately: the backup path for individual US
securities (``get_daily_bars``, part of the ``MarketDataProvider`` contract)
and the sole index path (``get_index_daily_bars``, ADR-0005 決策一).
"""

from __future__ import annotations

import json
from datetime import date
from pathlib import Path

import httpx

from app.data.http import RateLimitedClient
from app.data.interface import DataStatus
from app.data.providers.yfinance import INDEX_SYMBOL_METADATA, YFinanceAdapter

FIXTURES_DIR = Path(__file__).parent / "fixtures"


def _fixture_json(name: str) -> dict[str, object]:
    return json.loads((FIXTURES_DIR / name).read_text(encoding="utf-8"))  # type: ignore[no-any-return]


def _adapter_with_handler(handler: httpx.MockTransport) -> YFinanceAdapter:
    client = RateLimitedClient(
        base_url="https://query1.finance.yahoo.com",
        min_interval_seconds=0.0,
        transport=handler,
        sleep_fn=lambda _seconds: None,
    )
    return YFinanceAdapter(client=client)


class TestGetDailyBarsForSecurities:
    def test_parses_fixture_and_skips_null_gap_row(self) -> None:
        payload = _fixture_json("yfinance_chart_tqqq.json")

        def handler(request: httpx.Request) -> httpx.Response:
            assert "/v8/finance/chart/TQQQ" in str(request.url)
            return httpx.Response(200, json=payload)

        adapter = _adapter_with_handler(httpx.MockTransport(handler))
        result = adapter.get_daily_bars("TQQQ", date(2024, 1, 1), date(2024, 1, 31))

        assert result.status is DataStatus.FRESH
        assert result.source == "yfinance"
        # 2024-01-04 has null values across the board and must be skipped.
        assert [bar.date for bar in result.bars] == [
            date(2024, 1, 2),
            date(2024, 1, 3),
            date(2024, 1, 5),
        ]
        first = result.bars[0]
        assert first.symbol == "TQQQ"
        assert first.market == "US"
        assert first.currency == "USD"
        assert str(first.open) == "56.12"

    def test_converts_dotted_symbol_to_hyphenated_wire_form(self) -> None:
        payload = _fixture_json("yfinance_chart_tqqq.json")
        seen_paths: list[str] = []

        def handler(request: httpx.Request) -> httpx.Response:
            seen_paths.append(request.url.path)
            return httpx.Response(200, json=payload)

        adapter = _adapter_with_handler(httpx.MockTransport(handler))
        result = adapter.get_daily_bars("BRK.B", date(2024, 1, 1), date(2024, 1, 31))

        assert seen_paths == ["/v8/finance/chart/BRK-B"]
        # The canonical (dotted) symbol is what lands on the bar, not the
        # hyphenated wire symbol used for the request.
        assert all(bar.symbol == "BRK.B" for bar in result.bars)

    def test_rejects_index_symbol_without_any_http_call(self) -> None:
        call_count = 0

        def handler(request: httpx.Request) -> httpx.Response:
            nonlocal call_count
            call_count += 1
            return httpx.Response(200, json={})

        adapter = _adapter_with_handler(httpx.MockTransport(handler))
        result = adapter.get_daily_bars("^NDX", date(2024, 1, 1), date(2024, 1, 31))

        assert result.status is DataStatus.UNAVAILABLE
        assert call_count == 0

    def test_yahoo_error_envelope_is_reported_as_ambiguous_not_a_guess(self) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(
                200,
                json={
                    "chart": {
                        "result": None,
                        "error": {
                            "code": "Not Found",
                            "description": "No data found, symbol may be delisted",
                        },
                    }
                },
            )

        adapter = _adapter_with_handler(httpx.MockTransport(handler))
        result = adapter.get_daily_bars("ZZZZ", date(2024, 1, 1), date(2024, 1, 31))

        assert result.status is DataStatus.UNAVAILABLE
        assert result.reason is not None
        assert "無法確定" in result.reason

    def test_transport_error_returns_unavailable_without_raising(self) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            raise httpx.ConnectError("boom", request=request)

        client = RateLimitedClient(
            base_url="https://query1.finance.yahoo.com",
            max_retries=0,
            transport=httpx.MockTransport(handler),
            sleep_fn=lambda _seconds: None,
        )
        adapter = YFinanceAdapter(client=client)
        result = adapter.get_daily_bars("AAPL", date(2024, 1, 1), date(2024, 1, 31))
        assert result.status is DataStatus.UNAVAILABLE
        assert result.bars == []

    def test_filters_bars_to_requested_range(self) -> None:
        payload = _fixture_json("yfinance_chart_tqqq.json")

        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(200, json=payload)

        adapter = _adapter_with_handler(httpx.MockTransport(handler))
        result = adapter.get_daily_bars("TQQQ", date(2024, 1, 2), date(2024, 1, 2))
        assert [bar.date for bar in result.bars] == [date(2024, 1, 2)]


class TestGetIndexDailyBars:
    def test_ndx_status_is_always_backup_even_on_success(self) -> None:
        payload = _fixture_json("yfinance_chart_ndx.json")

        def handler(request: httpx.Request) -> httpx.Response:
            assert "/v8/finance/chart/%5ENDX" in str(request.url)
            return httpx.Response(200, json=payload)

        adapter = _adapter_with_handler(httpx.MockTransport(handler))
        result = adapter.get_index_daily_bars("^NDX", date(2024, 1, 1), date(2024, 1, 31))

        assert result.status is DataStatus.BACKUP  # never FRESH, per ADR-0005 I-3
        assert len(result.bars) == 4
        first = result.bars[0]
        assert first.symbol == "^NDX"
        assert first.market == "US"
        assert first.currency == "USD"

    def test_twii_tags_taiwan_market_and_currency(self) -> None:
        payload = _fixture_json("yfinance_chart_twii.json")

        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(200, json=payload)

        adapter = _adapter_with_handler(httpx.MockTransport(handler))
        result = adapter.get_index_daily_bars("^TWII", date(2024, 1, 1), date(2024, 1, 31))

        assert result.status is DataStatus.BACKUP
        first = result.bars[0]
        assert first.symbol == "^TWII"
        assert first.market == "TW"
        assert first.currency == "TWD"

    def test_index_symbols_never_go_through_canonical_us_symbol(self) -> None:
        """`^` would be rejected by canonical_us_symbol; confirm the index path
        never calls it by successfully exercising every ``^``-prefixed symbol
        in the supported table (a call into canonical_us_symbol would instead
        raise/degrade to UNAVAILABLE for every one of them)."""
        payload = _fixture_json("yfinance_chart_ndx.json")

        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(200, json=payload)

        adapter = _adapter_with_handler(httpx.MockTransport(handler))
        for symbol in INDEX_SYMBOL_METADATA:
            assert symbol.startswith("^")
            result = adapter.get_index_daily_bars(symbol, date(2024, 1, 1), date(2024, 1, 31))
            assert result.status is DataStatus.BACKUP

    def test_unsupported_index_symbol_is_unavailable_not_a_proxy(self) -> None:
        call_count = 0

        def handler(request: httpx.Request) -> httpx.Response:
            nonlocal call_count
            call_count += 1
            return httpx.Response(200, json={})

        adapter = _adapter_with_handler(httpx.MockTransport(handler))
        result = adapter.get_index_daily_bars("^SOX", date(2024, 1, 1), date(2024, 1, 31))

        assert result.status is DataStatus.UNAVAILABLE
        assert result.reason is not None
        assert "不在本工具支援" in result.reason
        assert call_count == 0  # never falls through to a live request

    def test_index_status_is_backup_never_fresh_regression_guard(self) -> None:
        payload = _fixture_json("yfinance_chart_ndx.json")

        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(200, json=payload)

        adapter = _adapter_with_handler(httpx.MockTransport(handler))
        result = adapter.get_index_daily_bars("^NDX", date(2024, 1, 1), date(2024, 1, 31))
        assert result.status is not DataStatus.FRESH

    def test_transport_error_on_index_path_returns_unavailable(self) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            raise httpx.ConnectError("boom", request=request)

        adapter = _adapter_with_handler(httpx.MockTransport(handler))
        result = adapter.get_index_daily_bars("^NDX", date(2024, 1, 1), date(2024, 1, 31))
        assert result.status is DataStatus.UNAVAILABLE
        assert result.reason is not None


class TestOwnedClientLifecycle:
    def test_close_closes_a_self_constructed_client(self) -> None:
        adapter = YFinanceAdapter()  # no client passed in -> adapter owns one
        adapter.close()  # must not raise


class TestFetchErrorBranches:
    """Exercises every degrade-without-raising branch inside the shared
    ``_fetch``/``_parse_result`` helpers, using the equity role as the driver."""

    def test_empty_bars_after_parsing_is_reported_as_ambiguous(self) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(
                200,
                json={"chart": {"result": [{"timestamp": [], "indicators": {"quote": [{}]}}]}},
            )

        adapter = _adapter_with_handler(httpx.MockTransport(handler))
        result = adapter.get_daily_bars("AAPL", date(2024, 1, 1), date(2024, 1, 31))
        assert result.status is DataStatus.UNAVAILABLE
        assert result.reason is not None
        assert "無法區分" in result.reason

    def test_non_200_http_status_is_unavailable(self) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(500)

        adapter = _adapter_with_handler(httpx.MockTransport(handler))
        result = adapter.get_daily_bars("AAPL", date(2024, 1, 1), date(2024, 1, 31))
        assert result.status is DataStatus.UNAVAILABLE

    def test_non_json_body_is_unavailable(self) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(200, content=b"not json at all")

        adapter = _adapter_with_handler(httpx.MockTransport(handler))
        result = adapter.get_daily_bars("AAPL", date(2024, 1, 1), date(2024, 1, 31))
        assert result.status is DataStatus.UNAVAILABLE
        assert result.reason is not None and "格式無法解析" in result.reason

    def test_missing_chart_block_is_unavailable(self) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(200, json={"not_chart": {}})

        adapter = _adapter_with_handler(httpx.MockTransport(handler))
        result = adapter.get_daily_bars("AAPL", date(2024, 1, 1), date(2024, 1, 31))
        assert result.status is DataStatus.UNAVAILABLE
        assert result.reason is not None and "缺少預期的 chart" in result.reason

    def test_missing_result_list_is_unavailable(self) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(200, json={"chart": {"result": [], "error": None}})

        adapter = _adapter_with_handler(httpx.MockTransport(handler))
        result = adapter.get_daily_bars("AAPL", date(2024, 1, 1), date(2024, 1, 31))
        assert result.status is DataStatus.UNAVAILABLE
        assert result.reason is not None and "未回傳任何結果區塊" in result.reason

    def test_result_that_is_not_an_object_yields_no_bars(self) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(200, json={"chart": {"result": ["not-an-object"], "error": None}})

        adapter = _adapter_with_handler(httpx.MockTransport(handler))
        result = adapter.get_daily_bars("AAPL", date(2024, 1, 1), date(2024, 1, 31))
        assert result.status is DataStatus.UNAVAILABLE

    def test_malformed_timestamp_or_indicators_yields_no_bars(self) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(
                200,
                json={
                    "chart": {
                        "result": [{"timestamp": "not-a-list", "indicators": {}}],
                        "error": None,
                    }
                },
            )

        adapter = _adapter_with_handler(httpx.MockTransport(handler))
        result = adapter.get_daily_bars("AAPL", date(2024, 1, 1), date(2024, 1, 31))
        assert result.status is DataStatus.UNAVAILABLE

    def test_malformed_quote_block_yields_no_bars(self) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(
                200,
                json={
                    "chart": {
                        "result": [
                            {"timestamp": [1704205800], "indicators": {"quote": "nope"}}
                        ],
                        "error": None,
                    }
                },
            )

        adapter = _adapter_with_handler(httpx.MockTransport(handler))
        result = adapter.get_daily_bars("AAPL", date(2024, 1, 1), date(2024, 1, 31))
        assert result.status is DataStatus.UNAVAILABLE

    def test_null_timestamp_entry_is_skipped_not_fabricated(self) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(
                200,
                json={
                    "chart": {
                        "result": [
                            {
                                "timestamp": [None, 1704205800],
                                "indicators": {
                                    "quote": [
                                        {
                                            "open": [999.0, 56.12],
                                            "high": [999.0, 56.90],
                                            "low": [999.0, 55.40],
                                            "close": [999.0, 55.75],
                                            "volume": [999, 102345600],
                                        }
                                    ]
                                },
                            }
                        ],
                        "error": None,
                    }
                },
            )

        adapter = _adapter_with_handler(httpx.MockTransport(handler))
        result = adapter.get_daily_bars("AAPL", date(2024, 1, 1), date(2024, 1, 31))
        assert result.status is DataStatus.FRESH
        assert len(result.bars) == 1
        assert result.bars[0].date == date(2024, 1, 2)

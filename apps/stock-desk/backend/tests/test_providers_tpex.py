"""Contract tests for the TPEx adapter, driven entirely by offline fixtures.

These fixtures target the *new* ``tradingStock`` endpoint
(``app/data/providers/tpex.py``'s module docstring records why the adapter
was rewritten on 2026-09-19 and that this endpoint is NOT yet verified
against a live response in this sandbox).
"""

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


def test_get_daily_bars_parses_fixture_and_converts_thousands_of_shares() -> None:
    """The 頎邦 (6147) fixture mirrors the live header (CEO 本機 2026-09-19).

    "日 期" carries a space and the volume column is "成交張數" (board lots,
    1 張 = 1,000 shares): both must resolve, and the volume must be scaled.
    """
    payload = _fixture_json("tpex_trading_stock_6147_202609.json")

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/www/zh-tw/afterTrading/tradingStock"
        assert request.url.params["code"] == "6147"
        assert request.url.params["date"] == "2026/09/01"
        assert request.url.params["id"] == ""
        assert request.url.params["response"] == "json"
        return httpx.Response(200, json=payload)

    adapter = _adapter_with_handler(httpx.MockTransport(handler))
    result = adapter.get_daily_bars("6147", date(2026, 9, 1), date(2026, 9, 30))

    assert result.status is DataStatus.FRESH
    assert result.source == "tpex"
    assert result.as_of.tzinfo is not None
    assert [bar.date for bar in result.bars] == [date(2026, 9, 1), date(2026, 9, 2)]
    first = result.bars[0]
    assert first.symbol == "6147"
    assert first.market == "TW"
    assert first.currency == "TWD"
    # Fixture says "1,234" 張 -> 1,234,000 shares.
    assert first.volume == 1_234_000
    assert str(first.close) == "45.80"


def test_a_thousand_shares_header_is_still_scaled() -> None:
    """The documented "成交仟股" wording (public write-ups) keeps working alongside 張."""
    rows = [["115/09/01", "1,234", "56,789", "45.50", "46.00", "45.10", "45.80", "+0.30", "321"]]
    fields = ["日期", "成交仟股", "成交仟元", "開盤", "最高", "最低", "收盤", "漲跌", "筆數"]

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=_month_payload(fields, rows))

    adapter = _adapter_with_handler(httpx.MockTransport(handler))
    result = adapter.get_daily_bars("6147", date(2026, 9, 1), date(2026, 9, 30))
    assert result.bars[0].volume == 1_234_000


def test_get_daily_bars_does_not_scale_a_plain_shares_column() -> None:
    """A "成交股數" header (no 仟/千) must not be multiplied by 1000."""
    payload = _fixture_json("tpex_trading_stock_shares_unit_202609.json")

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=payload)

    adapter = _adapter_with_handler(httpx.MockTransport(handler))
    result = adapter.get_daily_bars("6147", date(2026, 9, 1), date(2026, 9, 30))

    assert result.status is DataStatus.FRESH
    assert result.bars[0].volume == 1_234_000


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
    result = adapter.get_daily_bars("6147", date(2026, 9, 1), date(2026, 9, 30))
    assert result.status is DataStatus.UNAVAILABLE
    assert result.bars == []


def test_returns_unavailable_when_stat_not_ok() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"stat": "error"})

    adapter = _adapter_with_handler(httpx.MockTransport(handler))
    result = adapter.get_daily_bars("0000", date(2026, 9, 1), date(2026, 9, 30))
    assert result.status is DataStatus.UNAVAILABLE
    assert result.bars == []


def test_returns_unavailable_on_non_200_http_status() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(404, text="not found")

    client = RateLimitedClient(
        base_url="https://www.tpex.org.tw",
        max_retries=0,
        transport=httpx.MockTransport(handler),
        sleep_fn=lambda _seconds: None,
    )
    adapter = TpexAdapter(client=client)
    result = adapter.get_daily_bars("6147", date(2026, 9, 1), date(2026, 9, 30))
    assert result.status is DataStatus.UNAVAILABLE
    assert result.bars == []


def test_returns_unavailable_on_non_json_body() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, text="<html>not json</html>")

    adapter = _adapter_with_handler(httpx.MockTransport(handler))
    result = adapter.get_daily_bars("6147", date(2026, 9, 1), date(2026, 9, 30))
    assert result.status is DataStatus.UNAVAILABLE
    assert result.bars == []


def test_missing_expected_columns_is_treated_as_no_data_for_the_month() -> None:
    """An unrecognised response shape is a skipped month (ADR-0009), never guessed at."""

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "stat": "ok",
                "tables": [{"fields": ["日期", "某個未知欄位"], "data": [["115/09/01", "x"]]}],
            },
        )

    adapter = _adapter_with_handler(httpx.MockTransport(handler))
    result = adapter.get_daily_bars("6147", date(2026, 9, 1), date(2026, 9, 30))
    assert result.status is DataStatus.UNAVAILABLE
    assert result.bars == []


def _month_payload(fields: list[str], rows: list[list[str]]) -> dict[str, object]:
    return {"stat": "ok", "tables": [{"fields": fields, "data": rows}]}


_GOOD_FIELDS = ["日 期", "成交張數", "成交仟元", "開盤", "最高", "最低", "收盤", "漲跌", "筆數"]


def test_an_unrecognised_layout_in_one_month_marks_the_answer_incomplete() -> None:
    """qa-reviewer 2026-09-19: a month the adapter cannot read is a *skipped* month (ADR-0009).

    August parses; September's header is unreadable. The bars that did parse
    are returned, but ``complete`` must be False so the service does not record
    the whole range as covered.
    """

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.params["date"] == "2026/08/01":
            rows = [["115/08/03", "1,000", "1", "10.0", "11.0", "9.0", "10.5", "+0.5", "1"]]
            return httpx.Response(200, json=_month_payload(_GOOD_FIELDS, rows))
        return httpx.Response(200, json=_month_payload(["日期", "神秘欄位"], [["115/09/01", "x"]]))

    adapter = _adapter_with_handler(httpx.MockTransport(handler))
    result = adapter.get_daily_bars("6147", date(2026, 8, 1), date(2026, 9, 30))
    assert result.status is DataStatus.FRESH
    assert [bar.date for bar in result.bars] == [date(2026, 8, 3)]
    assert result.complete is False


def test_a_header_keyword_matching_two_columns_is_refused_not_guessed() -> None:
    """qa-reviewer 2026-09-19: two headers containing 股 must not resolve to the first one."""
    fields = ["日期", "發行股數", "成交股數", "開盤", "最高", "最低", "收盤"]
    # Both 發行股數 and 成交股數 contain the bare 股 fallback, but only 成交股數
    # matches the specific keyword tried first -- that one wins, unambiguously.
    rows = [["115/09/01", "999", "1,234", "45.50", "46.00", "45.10", "45.80"]]

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=_month_payload(fields, rows))

    adapter = _adapter_with_handler(httpx.MockTransport(handler))
    result = adapter.get_daily_bars("6147", date(2026, 9, 1), date(2026, 9, 30))
    assert result.bars[0].volume == 1234

    # With no specific header present, two bare-股 columns are ambiguous: skipped month.
    ambiguous = ["日期", "甲股", "乙股", "開盤", "最高", "最低", "收盤"]

    def ambiguous_handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=_month_payload(ambiguous, rows))

    adapter = _adapter_with_handler(httpx.MockTransport(ambiguous_handler))
    result = adapter.get_daily_bars("6147", date(2026, 9, 1), date(2026, 9, 30))
    assert result.status is DataStatus.UNAVAILABLE
    assert result.bars == []


def test_placeholder_and_short_rows_are_skipped_without_fabricating_bars() -> None:
    """A "--" no-trade row and a row shorter than the resolved columns are both dropped."""
    rows = [
        ["115/09/01", "--", "--", "--", "--", "--", "--", "--", "0"],
        ["115/09/02", "1,000"],
        ["115/09/03", "2,000", "1", "10.0", "11.0", "9.0", "10.5", "+0.5", "1"],
    ]

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=_month_payload(_GOOD_FIELDS, rows))

    adapter = _adapter_with_handler(httpx.MockTransport(handler))
    result = adapter.get_daily_bars("6147", date(2026, 9, 1), date(2026, 9, 30))
    assert result.status is DataStatus.FRESH
    assert result.complete is True
    assert [bar.date for bar in result.bars] == [date(2026, 9, 3)]
    assert result.bars[0].volume == 2_000_000

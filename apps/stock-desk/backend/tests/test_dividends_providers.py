"""Contract tests for the TWSE 除權息預告表 adapter -- fixtures only, never the network."""

from __future__ import annotations

import json
from datetime import UTC, date, datetime
from decimal import Decimal
from pathlib import Path

import httpx
import pytest

from app.data.http import RateLimitedClient
from app.data.providers._util import UnparseableRowError
from app.dividends.providers import (
    TWSE_OPENAPI_BASE_URL,
    TwseDividendAdapter,
    parse_dividend_row,
    parse_twse_date,
)

FIXTURES_DIR = Path(__file__).parent / "fixtures"
FIXTURE_NAME = "twse_openapi_twt48u_all.json"
AS_OF = datetime(2026, 8, 10, 12, 0, tzinfo=UTC)


def _fixture() -> list[object]:
    return json.loads((FIXTURES_DIR / FIXTURE_NAME).read_text(encoding="utf-8"))  # type: ignore[no-any-return]


def _row(code: str) -> dict[str, object]:
    for row in _fixture():
        assert isinstance(row, dict)
        if row.get("Code") == code:
            return row
    raise AssertionError(f"no fixture row for Code={code!r}")


def _client(payload: object, *, status: int = 200) -> RateLimitedClient:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(status, json=payload)

    return RateLimitedClient(
        base_url=TWSE_OPENAPI_BASE_URL,
        min_interval_seconds=0.0,
        transport=httpx.MockTransport(handler),
        sleep_fn=lambda _s: None,
    )


def _unreachable_client() -> RateLimitedClient:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("connection refused", request=request)

    return RateLimitedClient(
        base_url=TWSE_OPENAPI_BASE_URL,
        min_interval_seconds=0.0,
        max_retries=0,
        transport=httpx.MockTransport(handler),
        sleep_fn=lambda _s: None,
    )


# --- date parsing ------------------------------------------------------------


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("1150814", date(2026, 8, 14)),  # 7-digit ROC, no separator (TWT48U_ALL's own shape)
        ("1130617", date(2024, 6, 17)),  # 7-digit ROC
        ("113/06/17", date(2024, 6, 17)),  # slash ROC
        ("20240617", date(2024, 6, 17)),  # 8-digit Gregorian
        ("2024-06-17", date(2024, 6, 17)),  # ISO
    ],
)
def test_every_known_date_spelling_parses_to_the_same_day(raw: str, expected: date) -> None:
    assert parse_twse_date(raw) == expected


@pytest.mark.parametrize(
    "raw",
    [
        "",
        "not-a-date",
        "113/13/01",
        "11306",
        "1130699",
        "0000814",  # ROC year 0 -> 1911, outside the plausible window
        "9990814",  # ROC year 999 -> 2910, outside the plausible window
    ],
)
def test_unrecognized_dates_are_refused_never_guessed(raw: str) -> None:
    with pytest.raises(UnparseableRowError):
        parse_twse_date(raw)


# --- row parsing -------------------------------------------------------------


def test_a_normal_cash_only_row_parses_with_previous_close_unset() -> None:
    """TWT48U_ALL never publishes 前一日收盤價; it is filled in later, at
    adjustment time, from the bar series (see app.dividends.adjust)."""
    event = parse_dividend_row(_row("2330"), source="twse_openapi_dividend", as_of=AS_OF)
    assert event.symbol == "2330"
    assert event.market == "TW"
    assert event.ex_date == date(2026, 8, 14)
    assert event.cash_dividend == Decimal("3.000000")
    assert event.stock_dividend_ratio is None
    assert event.previous_close is None
    assert event.reference_price is None
    assert event.adjustment_factor is None  # unusable until previous_close is filled in


def test_all_numeric_fields_blank_is_a_valid_calendar_only_row() -> None:
    """A real TWSE sample row (2026-08-12 capture): ex-date fixed, amount not
    yet announced. Blank means "no component yet", not zero and not an error."""
    event = parse_dividend_row(_row("00401A"), source="s", as_of=AS_OF)
    assert event.cash_dividend == Decimal(0)
    assert event.stock_dividend_ratio is None
    assert event.is_usable is False


def test_a_stock_component_row_is_stored_but_never_yields_a_factor() -> None:
    """CashDividend + StockDividendRatio both present ("息權"): the stock
    ratio is recorded, but the factor is refused rather than computed
    cash-only, since that would silently understate the real drop."""
    event = parse_dividend_row(_row("2884"), source="s", as_of=AS_OF)
    assert event.cash_dividend == Decimal("0.610000")
    assert event.stock_dividend_ratio == Decimal("12.500000")
    assert event.adjustment_factor is None
    assert event.is_usable is False


def test_thousands_separators_in_cash_dividend_are_handled() -> None:
    event = parse_dividend_row(_row("2454"), source="s", as_of=AS_OF)
    assert event.cash_dividend == Decimal("1000.000000")


@pytest.mark.parametrize(
    "row",
    [
        "not-an-object",
        {"Code": "2330", "Exdividend": "息"},  # no date
        {"Date": "1150814", "Exdividend": "息"},  # no symbol
        {"Date": "1150814", "Code": "2330"},  # no Exdividend
        {"Date": "1150814", "Code": "2330", "Exdividend": "?"},  # unrecognized flag
        {"Date": "1150814", "Code": "2330", "Exdividend": "權", "StockDividendRatio": ""},
        {"Date": "1150814", "Code": "2330", "Exdividend": "息", "CashDividend": "-1.0"},
        {
            "Date": "1150814",
            "Code": "2330",
            "Exdividend": "息",
            "StockDividendRatio": "-1.0",
        },
    ],
)
def test_incomplete_or_inconsistent_rows_are_refused_rather_than_filled_in(
    row: object,
) -> None:
    with pytest.raises(UnparseableRowError):
        parse_dividend_row(row, source="s", as_of=AS_OF)


# --- adapter -----------------------------------------------------------------


def test_fetch_parses_the_fixture_and_counts_the_rows_it_refused() -> None:
    adapter = TwseDividendAdapter(client=_client(_fixture()))
    result = adapter.fetch()
    assert result.ok is True
    # 4 parseable rows (2330, 00401A, 2884, 2454); 3 refused (unknown flag,
    # missing symbol, Exdividend="權" with a blank StockDividendRatio).
    assert len(result.events) == 4
    assert result.skipped_rows == 3
    assert {event.symbol for event in result.events} == {"2330", "00401A", "2884", "2454"}


def test_network_failure_is_a_reason_not_an_exception() -> None:
    adapter = TwseDividendAdapter(client=_unreachable_client())
    result = adapter.fetch()
    assert result.ok is False
    assert "連線失敗" in (result.reason or "")
    assert result.events == ()


def test_http_error_names_the_verified_endpoint_as_the_suspect() -> None:
    adapter = TwseDividendAdapter(client=_client([], status=404))
    result = adapter.fetch()
    assert result.ok is False
    assert "404" in (result.reason or "")
    assert "覆核" in (result.reason or "")


def test_non_list_payload_is_a_schema_mismatch_not_a_crash() -> None:
    adapter = TwseDividendAdapter(client=_client({"stat": "OK"}))
    result = adapter.fetch()
    assert result.ok is False
    assert "非陣列" in (result.reason or "")


def test_all_rows_unparseable_fails_loudly_instead_of_returning_empty_success() -> None:
    adapter = TwseDividendAdapter(client=_client([{"unexpected": "shape"}, {"another": 1}]))
    result = adapter.fetch()
    assert result.ok is False
    assert "沒有任何可解析的列" in (result.reason or "")
    assert result.skipped_rows == 2

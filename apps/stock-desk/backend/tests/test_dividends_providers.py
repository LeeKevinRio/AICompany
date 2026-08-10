"""Contract tests for the TWSE 除權息 adapter -- fixtures only, never the network."""

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
FIXTURE_NAME = "twse_openapi_twt49u_exdividend.json"
AS_OF = datetime(2026, 8, 10, 12, 0, tzinfo=UTC)


def _fixture() -> list[object]:
    return json.loads((FIXTURES_DIR / FIXTURE_NAME).read_text(encoding="utf-8"))  # type: ignore[no-any-return]


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
        ("1130617", date(2024, 6, 17)),  # 7-digit ROC
        ("113/06/17", date(2024, 6, 17)),  # slash ROC
        ("20240617", date(2024, 6, 17)),  # 8-digit Gregorian
        ("2024-06-17", date(2024, 6, 17)),  # ISO
    ],
)
def test_every_known_date_spelling_parses_to_the_same_day(raw: str, expected: date) -> None:
    assert parse_twse_date(raw) == expected


@pytest.mark.parametrize("raw", ["", "not-a-date", "113/13/01", "11306", "1130699"])
def test_unrecognized_dates_are_refused_never_guessed(raw: str) -> None:
    with pytest.raises(UnparseableRowError):
        parse_twse_date(raw)


# --- row parsing -------------------------------------------------------------


def test_row_parses_into_an_event_with_the_official_factor() -> None:
    row = _fixture()[0]
    event = parse_dividend_row(row, source="twse_openapi_dividend", as_of=AS_OF)
    assert event.symbol == "2330"
    assert event.market == "TW"
    assert event.ex_date == date(2024, 6, 17)
    assert event.previous_close == Decimal("102.00")
    assert event.reference_price == Decimal("99.00")
    assert event.cash_dividend == Decimal("3.00")
    assert event.adjustment_factor == Decimal("99.00") / Decimal("102.00")


def test_chinese_keys_parse_identically_to_english_keys() -> None:
    """The candidate-key list is the hedge against the unverified schema."""
    english = parse_dividend_row(_fixture()[0], source="s", as_of=AS_OF)
    chinese = parse_dividend_row(
        {
            "日期": "1130617",
            "證券代號": "2330",
            "除權息前收盤價": "102.00",
            "除權息參考價": "99.00",
            "息值": "3.00",
        },
        source="s",
        as_of=AS_OF,
    )
    assert chinese.ex_date == english.ex_date
    assert chinese.adjustment_factor == english.adjustment_factor


def test_thousands_separators_are_handled() -> None:
    event = parse_dividend_row(
        {"Date": "1130617", "Code": "2330", "BeforePrice": "1,020.00", "ReferencePrice": "990.00"},
        source="s",
        as_of=AS_OF,
    )
    assert event.previous_close == Decimal("1020.00")


@pytest.mark.parametrize(
    "row",
    [
        "not-an-object",
        {"Code": "2330", "BeforePrice": "100"},  # no date
        {"Date": "1130617", "BeforePrice": "100"},  # no symbol
        {"Date": "1130617", "Code": "2330"},  # no previous close
        {"Date": "1130617", "Code": "2330", "BeforePrice": "--"},  # placeholder
        {"Date": "1130617", "Code": "2330", "BeforePrice": "0"},  # non-positive
        {"Date": "1130617", "Code": "2330", "BeforePrice": "abc"},  # non-numeric
    ],
)
def test_incomplete_rows_are_refused_rather_than_filled_in(row: object) -> None:
    with pytest.raises(UnparseableRowError):
        parse_dividend_row(row, source="s", as_of=AS_OF)


# --- adapter -----------------------------------------------------------------


def test_fetch_parses_the_fixture_and_counts_the_rows_it_refused() -> None:
    adapter = TwseDividendAdapter(client=_client(_fixture()))
    result = adapter.fetch()
    assert result.ok is True
    # 4 parseable rows (one of which has an implausible factor and is only
    # rejected later, at adjustment time), 2 refused here.
    assert len(result.events) == 4
    assert result.skipped_rows == 2
    assert {event.symbol for event in result.events} == {"2330", "2884", "8888"}


def test_a_parseable_row_with_an_implausible_factor_is_stored_but_unusable() -> None:
    """Refusal happens at the layer that can explain it, not by dropping data."""
    adapter = TwseDividendAdapter(client=_client(_fixture()))
    events = {event.symbol: event for event in adapter.fetch().events}
    assert events["8888"].adjustment_factor is None
    assert events["8888"].is_usable is False


def test_network_failure_is_a_reason_not_an_exception() -> None:
    adapter = TwseDividendAdapter(client=_unreachable_client())
    result = adapter.fetch()
    assert result.ok is False
    assert "連線失敗" in (result.reason or "")
    assert result.events == ()


def test_http_error_names_the_unverified_endpoint_as_the_suspect() -> None:
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

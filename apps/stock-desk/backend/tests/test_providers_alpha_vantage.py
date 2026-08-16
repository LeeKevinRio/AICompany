"""Contract tests for the Alpha Vantage adapter, driven entirely by offline fixtures.

Covers ADR-0005 約束 Q-1..Q-7 as they apply to this adapter, plus the ordinary
parsing/contract behaviour every adapter needs.
"""

from __future__ import annotations

import json
from datetime import UTC, date, datetime
from pathlib import Path

import httpx
import pytest

from app.data.http import RateLimitedClient
from app.data.interface import DataStatus
from app.data.providers.alpha_vantage import API_KEY_ENV_VAR, AlphaVantageAdapter
from app.data.quota import DAILY_LIMIT_ENV_VAR, SAFETY_MARGIN_ENV_VAR, QuotaLedger

FIXTURES_DIR = Path(__file__).parent / "fixtures"


def _fixture_json(name: str) -> dict[str, object]:
    return json.loads((FIXTURES_DIR / name).read_text(encoding="utf-8"))  # type: ignore[no-any-return]


def _adapter_with_handler(
    handler: httpx.MockTransport,
    *,
    ledger: QuotaLedger,
    monkeypatch: pytest.MonkeyPatch,
    api_key: str | None = "fixture-test-key-not-real",
) -> AlphaVantageAdapter:
    if api_key is None:
        monkeypatch.delenv(API_KEY_ENV_VAR, raising=False)
    else:
        monkeypatch.setenv(API_KEY_ENV_VAR, api_key)
    client = RateLimitedClient(
        base_url="https://www.alphavantage.co",
        min_interval_seconds=0.0,
        transport=handler,
        sleep_fn=lambda _seconds: None,
    )
    return AlphaVantageAdapter(client=client, ledger=ledger, min_interval_seconds=0.0)


@pytest.fixture(autouse=True)
def _quota_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(DAILY_LIMIT_ENV_VAR, "10")
    monkeypatch.setenv(SAFETY_MARGIN_ENV_VAR, "0")


def test_parses_fixture_and_skips_unparseable_row(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    payload = _fixture_json("alpha_vantage_daily_aapl.json")
    call_count = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal call_count
        call_count += 1
        return httpx.Response(200, json=payload)

    ledger = QuotaLedger(db_path=tmp_path / "quota.db")
    adapter = _adapter_with_handler(
        httpx.MockTransport(handler), ledger=ledger, monkeypatch=monkeypatch
    )

    # ``start`` is chosen at the fixture's earliest raw date (2023-12-29, the
    # unparseable "N/A" row) rather than further back: this test is about
    # row-level parsing, not the coverage-depth guard exercised separately
    # below, so the requested window must stay fully inside what this
    # (deliberately tiny) compact fixture claims to cover.
    result = adapter.get_daily_bars("AAPL", date(2023, 12, 29), date(2024, 1, 31))

    assert result.status is DataStatus.FRESH
    assert result.source == "alpha_vantage"
    assert result.reason is None
    # The 2023-12-29 row is all "N/A" placeholders and must be skipped.
    assert [bar.date for bar in result.bars] == [
        date(2024, 1, 2),
        date(2024, 1, 3),
        date(2024, 1, 4),
        date(2024, 1, 5),
    ]
    first = result.bars[0]
    assert first.symbol == "AAPL"
    assert first.market == "US"
    assert first.currency == "USD"
    assert str(first.open) == "187.1500"
    assert first.volume == 82_488_700
    assert first.source == "alpha_vantage"
    assert call_count == 1


def test_canonical_symbol_is_used_on_returned_bars_not_provider_wire_symbol(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    payload = _fixture_json("alpha_vantage_daily_aapl.json")
    seen_params: dict[str, str] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen_params.update(request.url.params)
        return httpx.Response(200, json=payload)

    ledger = QuotaLedger(db_path=tmp_path / "quota.db")
    adapter = _adapter_with_handler(
        httpx.MockTransport(handler), ledger=ledger, monkeypatch=monkeypatch
    )

    result = adapter.get_daily_bars("aapl", date(2024, 1, 1), date(2024, 1, 31))

    assert seen_params["symbol"] == "AAPL"  # AV default rule: identity
    assert all(bar.symbol == "AAPL" for bar in result.bars)


def test_missing_api_key_returns_unavailable_without_any_http_call(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    call_count = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal call_count
        call_count += 1
        return httpx.Response(200, json={})

    ledger = QuotaLedger(db_path=tmp_path / "quota.db")
    adapter = _adapter_with_handler(
        httpx.MockTransport(handler), ledger=ledger, monkeypatch=monkeypatch, api_key=None
    )

    result = adapter.get_daily_bars("AAPL", date(2024, 1, 1), date(2024, 1, 31))

    assert result.status is DataStatus.UNAVAILABLE
    assert result.reason is not None
    assert "API key" in result.reason
    assert call_count == 0


def test_invalid_symbol_format_returns_unavailable_without_any_http_call(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    call_count = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal call_count
        call_count += 1
        return httpx.Response(200, json={})

    ledger = QuotaLedger(db_path=tmp_path / "quota.db")
    adapter = _adapter_with_handler(
        httpx.MockTransport(handler), ledger=ledger, monkeypatch=monkeypatch
    )

    result = adapter.get_daily_bars("^GSPC", date(2024, 1, 1), date(2024, 1, 31))

    assert result.status is DataStatus.UNAVAILABLE
    assert result.reason is not None
    assert call_count == 0


def test_quota_exhausted_returns_unavailable_without_any_http_call(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Q-3: rowcount == 0 must short-circuit before any HTTP request."""
    monkeypatch.setenv(DAILY_LIMIT_ENV_VAR, "1")
    monkeypatch.setenv(SAFETY_MARGIN_ENV_VAR, "0")
    call_count = 0
    payload = _fixture_json("alpha_vantage_daily_aapl.json")

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal call_count
        call_count += 1
        return httpx.Response(200, json=payload)

    ledger = QuotaLedger(db_path=tmp_path / "quota.db")
    adapter = _adapter_with_handler(
        httpx.MockTransport(handler), ledger=ledger, monkeypatch=monkeypatch
    )

    first = adapter.get_daily_bars("AAPL", date(2024, 1, 1), date(2024, 1, 31))
    assert first.status is DataStatus.FRESH
    assert call_count == 1

    second = adapter.get_daily_bars("MSFT", date(2024, 1, 1), date(2024, 1, 31))
    assert second.status is DataStatus.UNAVAILABLE
    assert second.reason is not None
    assert "額度" in second.reason
    assert call_count == 1  # unchanged: no second HTTP call was made


def test_failed_request_after_reservation_does_not_refund_quota(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Q-2: the slot is spent even though the downstream call then failed."""
    monkeypatch.setenv(DAILY_LIMIT_ENV_VAR, "1")
    monkeypatch.setenv(SAFETY_MARGIN_ENV_VAR, "0")

    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("boom", request=request)

    ledger = QuotaLedger(db_path=tmp_path / "quota.db")
    adapter = _adapter_with_handler(
        httpx.MockTransport(handler), ledger=ledger, monkeypatch=monkeypatch
    )

    result = adapter.get_daily_bars("AAPL", date(2024, 1, 1), date(2024, 1, 31))
    assert result.status is DataStatus.UNAVAILABLE

    status = ledger.status("alpha_vantage", now=datetime.now(UTC))
    assert status is not None
    assert status.used == 1  # reserved, and NOT refunded despite the failure


def test_error_message_body_is_treated_as_unavailable(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"Error Message": "Invalid API call."})

    ledger = QuotaLedger(db_path=tmp_path / "quota.db")
    adapter = _adapter_with_handler(
        httpx.MockTransport(handler), ledger=ledger, monkeypatch=monkeypatch
    )

    result = adapter.get_daily_bars("AAPL", date(2024, 1, 1), date(2024, 1, 31))
    assert result.status is DataStatus.UNAVAILABLE
    assert result.reason is not None and "Invalid API call" in result.reason


def test_note_rate_limit_body_is_treated_as_unavailable(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"Note": "Thank you for using Alpha Vantage!"})

    ledger = QuotaLedger(db_path=tmp_path / "quota.db")
    adapter = _adapter_with_handler(
        httpx.MockTransport(handler), ledger=ledger, monkeypatch=monkeypatch
    )

    result = adapter.get_daily_bars("AAPL", date(2024, 1, 1), date(2024, 1, 31))
    assert result.status is DataStatus.UNAVAILABLE
    assert result.reason is not None and "頻率限制" in result.reason


def test_empty_series_reports_ambiguous_reason_not_a_guess(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"Meta Data": {}, "Time Series (Daily)": {}})

    ledger = QuotaLedger(db_path=tmp_path / "quota.db")
    adapter = _adapter_with_handler(
        httpx.MockTransport(handler), ledger=ledger, monkeypatch=monkeypatch
    )

    result = adapter.get_daily_bars("ZZZZ", date(2024, 1, 1), date(2024, 1, 31))
    assert result.status is DataStatus.UNAVAILABLE
    assert result.reason is not None
    assert "無法區分" in result.reason


def test_transport_error_returns_unavailable_without_raising(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("boom", request=request)

    ledger = QuotaLedger(db_path=tmp_path / "quota.db")
    client = RateLimitedClient(
        base_url="https://www.alphavantage.co",
        max_retries=0,
        transport=httpx.MockTransport(handler),
        sleep_fn=lambda _seconds: None,
    )
    monkeypatch.setenv(API_KEY_ENV_VAR, "fixture-test-key-not-real")
    adapter = AlphaVantageAdapter(client=client, ledger=ledger, min_interval_seconds=0.0)

    result = adapter.get_daily_bars("AAPL", date(2024, 1, 1), date(2024, 1, 31))
    assert result.status is DataStatus.UNAVAILABLE
    assert result.bars == []


def test_missing_quota_config_returns_unavailable_without_any_http_call(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv(DAILY_LIMIT_ENV_VAR, raising=False)
    call_count = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal call_count
        call_count += 1
        return httpx.Response(200, json={})

    ledger = QuotaLedger(db_path=tmp_path / "quota.db")
    adapter = _adapter_with_handler(
        httpx.MockTransport(handler), ledger=ledger, monkeypatch=monkeypatch
    )

    result = adapter.get_daily_bars("AAPL", date(2024, 1, 1), date(2024, 1, 31))
    assert result.status is DataStatus.UNAVAILABLE
    assert call_count == 0


def test_information_body_is_treated_as_unavailable(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200, json={"Information": "This endpoint requires a premium key."}
        )

    ledger = QuotaLedger(db_path=tmp_path / "quota.db")
    adapter = _adapter_with_handler(
        httpx.MockTransport(handler), ledger=ledger, monkeypatch=monkeypatch
    )

    result = adapter.get_daily_bars("AAPL", date(2024, 1, 1), date(2024, 1, 31))
    assert result.status is DataStatus.UNAVAILABLE
    assert result.reason is not None and "premium key" in result.reason


def test_non_200_http_status_is_unavailable(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(500)

    ledger = QuotaLedger(db_path=tmp_path / "quota.db")
    adapter = _adapter_with_handler(
        httpx.MockTransport(handler), ledger=ledger, monkeypatch=monkeypatch
    )

    result = adapter.get_daily_bars("AAPL", date(2024, 1, 1), date(2024, 1, 31))
    assert result.status is DataStatus.UNAVAILABLE
    assert result.reason is not None and "HTTP 狀態" in result.reason


def test_non_json_body_is_unavailable(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=b"not json at all")

    ledger = QuotaLedger(db_path=tmp_path / "quota.db")
    adapter = _adapter_with_handler(
        httpx.MockTransport(handler), ledger=ledger, monkeypatch=monkeypatch
    )

    result = adapter.get_daily_bars("AAPL", date(2024, 1, 1), date(2024, 1, 31))
    assert result.status is DataStatus.UNAVAILABLE
    assert result.reason is not None and "格式無法解析" in result.reason


def test_row_that_is_not_an_object_is_skipped(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    payload = {
        "Meta Data": {},
        "Time Series (Daily)": {
            "2024-01-02": "not-an-object",
            "2024-01-03": {
                "1. open": "1",
                "2. high": "2",
                "3. low": "1",
                "4. close": "1.5",
                "5. volume": "100",
            },
        },
    }

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=payload)

    ledger = QuotaLedger(db_path=tmp_path / "quota.db")
    adapter = _adapter_with_handler(
        httpx.MockTransport(handler), ledger=ledger, monkeypatch=monkeypatch
    )

    # ``start`` matches the raw series' earliest key (2024-01-02) so this row-
    # skip test stays inside the coverage-depth guard's tolerance; see the
    # dedicated coverage-guard tests below for the boundary itself.
    result = adapter.get_daily_bars("AAPL", date(2024, 1, 2), date(2024, 1, 31))
    assert result.status is DataStatus.FRESH
    assert [bar.date for bar in result.bars] == [date(2024, 1, 3)]


def test_close_closes_a_self_constructed_client(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv(API_KEY_ENV_VAR, "fixture-test-key-not-real")
    adapter = AlphaVantageAdapter()  # no client passed in -> adapter owns one
    adapter.close()  # must not raise


def test_filters_bars_to_requested_range(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    payload = _fixture_json("alpha_vantage_daily_aapl.json")

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=payload)

    ledger = QuotaLedger(db_path=tmp_path / "quota.db")
    adapter = _adapter_with_handler(
        httpx.MockTransport(handler), ledger=ledger, monkeypatch=monkeypatch
    )

    result = adapter.get_daily_bars("AAPL", date(2024, 1, 3), date(2024, 1, 3))
    assert [bar.date for bar in result.bars] == [date(2024, 1, 3)]


# --- Coverage-depth guard (2026-08-16): outputsize=compact cannot satisfy ---
# --- a deep-history request, and must decline rather than truncate ---------


def test_request_deeper_than_compact_coverage_is_declined_not_truncated(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A start earlier than the response's earliest date must not be silently
    served as a partial ``FRESH`` result -- that would let a deep-history
    caller (e.g. the walk-forward backtest) believe it got what it asked for.
    """
    payload = _fixture_json("alpha_vantage_daily_aapl.json")
    call_count = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal call_count
        call_count += 1
        return httpx.Response(200, json=payload)

    ledger = QuotaLedger(db_path=tmp_path / "quota.db")
    adapter = _adapter_with_handler(
        httpx.MockTransport(handler), ledger=ledger, monkeypatch=monkeypatch
    )

    # Fixture's earliest raw date is 2023-12-29; a two-year-back start models
    # a walk-forward backtest's typical deep-history request.
    result = adapter.get_daily_bars("AAPL", date(2022, 1, 3), date(2024, 1, 31))

    assert result.status is DataStatus.UNAVAILABLE
    assert result.bars == []
    assert result.reason is not None
    assert "outputsize=compact" in result.reason
    assert "備援來源" in result.reason
    # The request still happened -- this is a coverage decision made *after*
    # a successful fetch, not a quota short-circuit before one.
    assert call_count == 1


def test_request_within_compact_coverage_is_not_declined(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A start at or after the response's earliest date is ordinary FRESH data."""
    payload = _fixture_json("alpha_vantage_daily_aapl.json")

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=payload)

    ledger = QuotaLedger(db_path=tmp_path / "quota.db")
    adapter = _adapter_with_handler(
        httpx.MockTransport(handler), ledger=ledger, monkeypatch=monkeypatch
    )

    # Fixture's earliest raw date is 2023-12-29; requesting from exactly that
    # date must not trip the guard (equal, not earlier, than what is covered).
    result = adapter.get_daily_bars("AAPL", date(2023, 12, 29), date(2024, 1, 31))

    assert result.status is DataStatus.FRESH
    assert result.reason is None
    assert len(result.bars) == 4

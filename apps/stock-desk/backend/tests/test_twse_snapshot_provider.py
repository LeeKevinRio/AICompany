"""``TwseSnapshotAdapter`` contract tests (ADR-0012 D-3), offline fixtures only."""

from __future__ import annotations

import json
from datetime import UTC, date, datetime
from pathlib import Path

import httpx
import pytest

from app.data.http import RateLimitedClient
from app.data.providers.finmind import FINMIND_BASE_URL, FinMindAdapter
from app.data.providers.twse_snapshot import (
    CHANGE_SEMANTICS_VERIFIED_ON,
    TwseSnapshotAdapter,
    normalize_shares_by_header,
)
from app.directory.providers import TWSE_OPENAPI_BASE_URL

FIXTURES_DIR = Path(__file__).parent / "fixtures"
CANDIDATE = date(2026, 9, 24)


@pytest.fixture(autouse=True)
def _finmind_token(monkeypatch: pytest.MonkeyPatch) -> None:
    # Not a real credential -- FinMindAdapter refuses to call out without
    # *some* value in this env var; the transport is always a MockTransport.
    monkeypatch.setenv("FINMIND_API_TOKEN", "test-token-not-a-secret")


def _fixture_json(name: str) -> list[object]:
    return json.loads((FIXTURES_DIR / name).read_text(encoding="utf-8"))  # type: ignore[no-any-return]


def _twse_client(
    *,
    stock_day_all: list[object] | None = None,
    sector_profile: list[object] | None = None,
    twt48u: list[object] | None = None,
    fail_stock_day_all: bool = False,
) -> RateLimitedClient:
    stock_day_all = (
        stock_day_all
        if stock_day_all is not None
        else _fixture_json("twse_openapi_stock_day_all.json")
    )
    sector_profile = (
        sector_profile
        if sector_profile is not None
        else _fixture_json("twse_openapi_t187ap03_l.json")
    )
    twt48u = twt48u if twt48u is not None else _fixture_json("twse_openapi_twt48u_all.json")

    def handler(request: httpx.Request) -> httpx.Response:
        path = request.url.path
        if path.endswith("STOCK_DAY_ALL"):
            if fail_stock_day_all:
                return httpx.Response(500, json={})
            return httpx.Response(200, json=stock_day_all)
        if path.endswith("t187ap03_L"):
            return httpx.Response(200, json=sector_profile)
        if path.endswith("TWT48U_ALL"):
            return httpx.Response(200, json=twt48u)
        return httpx.Response(404, json={})

    return RateLimitedClient(
        base_url=TWSE_OPENAPI_BASE_URL,
        min_interval_seconds=0.0,
        transport=httpx.MockTransport(handler),
        sleep_fn=lambda _s: None,
    )


def _finmind_matching(stock_day_all: list[object], candidate: date = CANDIDATE) -> FinMindAdapter:
    """A FinMind stub that echoes back exactly what STOCK_DAY_ALL reported for ``candidate``."""
    by_code = {
        row["Code"]: row for row in stock_day_all if isinstance(row, dict) and row.get("Code")
    }

    def handler(request: httpx.Request) -> httpx.Response:
        symbol = dict(request.url.params)["data_id"]
        row = by_code.get(symbol)
        if row is None:
            return httpx.Response(200, json={"status": 200, "data": []})
        data = [
            {
                "date": candidate.isoformat(),
                "stock_id": symbol,
                "Trading_Volume": int(row["TradeVolume"]),
                "Trading_money": int(row["TradeValue"]),
                "open": row["OpeningPrice"],
                "max": row["HighestPrice"],
                "min": row["LowestPrice"],
                "close": row["ClosingPrice"],
                "spread": row["Change"],
                "Trading_turnover": int(row["Transaction"]),
            }
        ]
        return httpx.Response(200, json={"status": 200, "data": data})

    client = RateLimitedClient(
        base_url=FINMIND_BASE_URL,
        min_interval_seconds=0.0,
        transport=httpx.MockTransport(handler),
        sleep_fn=lambda _s: None,
    )
    return FinMindAdapter(client=client)


def _finmind_mismatching() -> FinMindAdapter:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"status": 200, "data": []})

    client = RateLimitedClient(
        base_url=FINMIND_BASE_URL,
        min_interval_seconds=0.0,
        transport=httpx.MockTransport(handler),
        sleep_fn=lambda _s: None,
    )
    return FinMindAdapter(client=client)


def _make_adapter(
    *,
    twse_client: RateLimitedClient,
    finmind: FinMindAdapter,
    candidate: date = CANDIDATE,
) -> TwseSnapshotAdapter:
    return TwseSnapshotAdapter(
        client=twse_client,
        finmind=finmind,
        clock=lambda: datetime(2026, 9, 24, 9, 30, tzinfo=UTC),
        candidate_session_date=lambda: candidate,
        sample_seed=42,
    )


# -- header note ---------------------------------------------------------------


def test_change_semantics_verification_flag_is_unset_by_default() -> None:
    # DE-5 is unverified per the resource evaluation; this must stay None
    # until a real ex-dividend day is checked by CEO.
    assert CHANGE_SEMANTICS_VERIFIED_ON is None


# -- share normalization (張->股) -----------------------------------------------


def test_normalize_shares_is_a_noop_for_a_shares_header() -> None:
    assert normalize_shares_by_header("TradeVolume", 1000) == 1000


def test_normalize_shares_multiplies_for_a_lot_header() -> None:
    assert normalize_shares_by_header("成交張數", 5) == 5000
    assert normalize_shares_by_header("成交仟股", 5) == 5000


# -- happy path ------------------------------------------------------------


def test_happy_path_certifies_session_and_captures_all_four_kinds() -> None:
    stock_day_all = _fixture_json("twse_openapi_stock_day_all.json")
    adapter = _make_adapter(
        twse_client=_twse_client(stock_day_all=stock_day_all),
        finmind=_finmind_matching(stock_day_all),
    )
    result = adapter.get_latest_snapshot()

    assert result.session_date == CANDIDATE
    assert result.session_date_self_certified is True
    assert result.source == "twse_snapshot"

    assert result.bars.status == "ok"
    bar_symbols = {row.symbol for row in result.bars_rows}
    assert bar_symbols == {"2330", "0050", "3037"}  # blank-code row skipped

    # listing = the FULL t187ap03_L resolvable-code population, NOT
    # intersected with STOCK_DAY_ALL's symbol set (qa-reviewer wave-1
    # blocking finding): a symbol absent from today's bars (1101, 2317 here)
    # must still appear in listing, or the bars coverage gate's denominator
    # would shrink along with a degraded STOCK_DAY_ALL response and could
    # never fail no matter how little of the market was actually captured.
    listing_by_symbol = {row.symbol: row.security_type for row in result.listing_rows}
    assert listing_by_symbol == {
        "2330": "common_stock",
        "2317": "common_stock",
        "1101": "common_stock",
        "9188": "tdr",  # code 91, depositary receipt
    }
    # code 99 (9921) is unresolved and dropped from both listing and
    # classification -- never guessed at.
    assert "9921" not in listing_by_symbol

    # classification: resolvable codes only (unknown code 99 dropped)
    classification_by_symbol = {row.symbol: row for row in result.classification_rows}
    assert classification_by_symbol["2330"].sector_code == "24"
    assert "9921" not in classification_by_symbol  # code 99 unresolved
    assert "9188" in classification_by_symbol  # code 91 resolvable (depositary receipts)

    # dividend_announce: full raw fields preserved verbatim
    dividend_by_symbol = {row.symbol: row for row in result.dividend_announce_rows}
    assert dividend_by_symbol["2330"].raw["CashDividend"] == "3.000000"
    assert dividend_by_symbol["2330"].raw["Exdividend"] == "息"
    assert dividend_by_symbol["2330"].ex_date == date(2026, 8, 14)
    # unrecognized flag "?" and inconsistent stock-component rows are still
    # captured verbatim (not silently dropped) as long as they have a symbol.
    assert "9999" in dividend_by_symbol
    assert "8888" in dividend_by_symbol
    # the row with no Code at all cannot be stored (no primary key) and is skipped
    assert len(result.dividend_announce_rows) == 6


# -- self-certification failure paths (D-3, C-12) -------------------------------


def test_session_certification_fails_closed_on_mismatch() -> None:
    stock_day_all = _fixture_json("twse_openapi_stock_day_all.json")
    adapter = _make_adapter(
        twse_client=_twse_client(stock_day_all=stock_day_all),
        finmind=_finmind_mismatching(),
    )
    result = adapter.get_latest_snapshot()

    assert result.session_date is None
    assert result.session_date_self_certified is False
    for kind in ("bars", "listing", "classification", "dividend_announce"):
        outcome = getattr(result, kind)
        assert outcome.status == "failed"
        assert outcome.reason is not None
    assert result.bars_rows == ()
    assert result.listing_rows == ()


def test_never_falls_back_to_the_wall_clock_when_certification_fails() -> None:
    """A failed cross-check must not silently use the candidate date anyway."""
    stock_day_all = _fixture_json("twse_openapi_stock_day_all.json")
    adapter = _make_adapter(
        twse_client=_twse_client(stock_day_all=stock_day_all),
        finmind=_finmind_mismatching(),
        candidate=date(2026, 1, 1),
    )
    result = adapter.get_latest_snapshot()
    assert result.session_date is None


def test_stock_day_all_transport_failure_fails_the_whole_batch() -> None:
    adapter = _make_adapter(
        twse_client=_twse_client(fail_stock_day_all=True),
        finmind=_finmind_mismatching(),
    )
    result = adapter.get_latest_snapshot()
    assert result.session_date is None
    assert result.bars.status == "failed"


def test_depositary_receipt_code_91_is_labelled_tdr_not_common_stock() -> None:
    stock_day_all: list[object] = [
        {
            "Code": "9188",
            "Name": "測試存託憑證",
            "TradeVolume": "1000000",
            "TradeValue": "10000000",
            "OpeningPrice": "10.00",
            "HighestPrice": "10.50",
            "LowestPrice": "9.50",
            "ClosingPrice": "10.20",
            "Change": "0.20",
            "Transaction": "100",
        }
    ]
    sector_profile: list[object] = [
        {"出表日期": "20260810", "公司代號": "9188", "公司名稱": "測試存託憑證", "產業別": "91"}
    ]
    adapter = _make_adapter(
        twse_client=_twse_client(stock_day_all=stock_day_all, sector_profile=sector_profile),
        finmind=_finmind_matching(stock_day_all),
    )
    result = adapter.get_latest_snapshot()
    assert result.session_date == CANDIDATE
    assert {row.symbol: row.security_type for row in result.listing_rows} == {"9188": "tdr"}


def test_sample_seed_is_recorded_and_reproducible() -> None:
    stock_day_all = _fixture_json("twse_openapi_stock_day_all.json")
    adapter_a = TwseSnapshotAdapter(
        client=_twse_client(stock_day_all=stock_day_all),
        finmind=_finmind_matching(stock_day_all),
        clock=lambda: datetime(2026, 9, 24, 9, 30, tzinfo=UTC),
        candidate_session_date=lambda: CANDIDATE,
    )
    assert isinstance(adapter_a._sample_seed, int)  # noqa: SLF001 - white-box check by design
    adapter_b = TwseSnapshotAdapter(
        client=_twse_client(stock_day_all=stock_day_all),
        finmind=_finmind_matching(stock_day_all),
        clock=lambda: datetime(2026, 9, 24, 9, 30, tzinfo=UTC),
        candidate_session_date=lambda: CANDIDATE,
        sample_seed=7,
    )
    assert adapter_b._sample_seed == 7  # noqa: SLF001

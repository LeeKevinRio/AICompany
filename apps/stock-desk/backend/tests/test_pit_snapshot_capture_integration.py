"""End-to-end capture tests driving the REAL ``TwseSnapshotAdapter`` (qa-reviewer wave-1).

``tests/test_pit_snapshot_service.py`` covers ``capture_once``'s own coverage
arithmetic against a hand-built ``StubProvider``, which has no power to
detect a bug in how the *provider* derives ``listing`` -- exactly the wave-1
blocking finding (listing defined as ``STOCK_DAY_ALL ∩ t187ap03_L`` made the
bars coverage denominator shrink together with a degraded STOCK_DAY_ALL
response, so the 0.98 gate could never fail). This file drives
``capture_once`` with the real adapter and offline fixtures so a regression
back to that shape is caught here, not just in a unit test that already
assumes the fix.
"""

from __future__ import annotations

import json
from datetime import UTC, date, datetime
from pathlib import Path

import httpx
import pytest

from app.data.http import RateLimitedClient
from app.data.market_panel import MarketPanelStore
from app.data.providers.finmind import FINMIND_BASE_URL, FinMindAdapter
from app.data.providers.twse_snapshot import TwseSnapshotAdapter
from app.directory.providers import TWSE_OPENAPI_BASE_URL
from app.services.pit_snapshot import capture_once

FIXTURES_DIR = Path(__file__).parent / "fixtures"
CANDIDATE = date(2026, 9, 24)


def _fixture_json(name: str) -> list[object]:
    return json.loads((FIXTURES_DIR / name).read_text(encoding="utf-8"))  # type: ignore[no-any-return]


@pytest.fixture(autouse=True)
def _finmind_token(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("FINMIND_API_TOKEN", "test-token-not-a-secret")


def _twse_client(stock_day_all: list[object], sector_profile: list[object]) -> RateLimitedClient:
    twt48u = _fixture_json("twse_openapi_twt48u_all.json")

    def handler(request: httpx.Request) -> httpx.Response:
        path = request.url.path
        if path.endswith("STOCK_DAY_ALL"):
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


def _finmind_matching(stock_day_all: list[object]) -> FinMindAdapter:
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
                "date": CANDIDATE.isoformat(),
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


def test_a_thin_stock_day_all_response_degrades_bars_but_not_listing(tmp_path: Path) -> None:
    """STOCK_DAY_ALL returning only 1 of 3 common-stock symbols must NOT let
    bars pass the coverage gate, and must NOT shrink the listing snapshot."""
    # Only "2330" trades today, per a thin/degraded STOCK_DAY_ALL response.
    stock_day_all: list[object] = [
        {
            "Code": "2330",
            "Name": "台積電",
            "TradeVolume": "41393088",
            "TradeValue": "24585432000",
            "OpeningPrice": "594.00",
            "HighestPrice": "598.00",
            "LowestPrice": "590.00",
            "ClosingPrice": "594.00",
            "Change": "2.00",
            "Transaction": "12345",
        }
    ]
    # t187ap03_L still lists the full common-stock population (3 common
    # stocks + 1 TDR) regardless of who traded today.
    sector_profile = _fixture_json("twse_openapi_t187ap03_l.json")

    twse_client = _twse_client(stock_day_all, sector_profile)
    finmind = _finmind_matching(stock_day_all)
    adapter = TwseSnapshotAdapter(
        client=twse_client,
        finmind=finmind,
        clock=lambda: datetime(2026, 9, 24, 9, 30, tzinfo=UTC),
        candidate_session_date=lambda: CANDIDATE,
        sample_seed=42,
    )
    store = MarketPanelStore(
        tmp_path / "market.db", clock=lambda: datetime(2026, 9, 24, 9, 30, tzinfo=UTC)
    )

    summary = capture_once(adapter, store)
    by_kind = {r.kind: r for r in summary.records}

    # Listing is the FULL common-stock population (2330, 2317, 1101) plus the
    # one TDR (9188) -- NOT narrowed down to whoever happened to trade today.
    frames = store.load_panel_frames(date(2026, 9, 1), date(2026, 9, 30))
    listing_rows = frames.listing
    assert set(listing_rows["symbol"]) == {"2330", "2317", "1101", "9188"}
    assert listing_rows.loc[listing_rows["symbol"] == "9188", "security_type"].iloc[0] == "tdr"
    assert by_kind["listing"].status == "ok"
    assert by_kind["listing"].row_count == 4

    # Bars coverage = |{"2330"} ∩ {"2330","2317","1101"}| / 3 = 1/3 -- well
    # under the 0.98 gate, so this run MUST be "partial", never "ok".
    assert by_kind["bars"].status == "partial"
    assert by_kind["bars"].expected_count == 3
    assert by_kind["bars"].reason is not None
    assert "0.98" in by_kind["bars"].reason


def test_full_stock_day_all_response_lets_bars_pass(tmp_path: Path) -> None:
    """Sanity counterpart: when every common stock actually traded, bars is ok."""
    stock_day_all: list[object] = [
        {
            "Code": symbol,
            "Name": f"測試{symbol}",
            "TradeVolume": "1000000",
            "TradeValue": "100000000",
            "OpeningPrice": "10.00",
            "HighestPrice": "10.50",
            "LowestPrice": "9.50",
            "ClosingPrice": "10.20",
            "Change": "0.20",
            "Transaction": "100",
        }
        for symbol in ("2330", "2317", "1101")
    ]
    sector_profile = _fixture_json("twse_openapi_t187ap03_l.json")

    twse_client = _twse_client(stock_day_all, sector_profile)
    finmind = _finmind_matching(stock_day_all)
    adapter = TwseSnapshotAdapter(
        client=twse_client,
        finmind=finmind,
        clock=lambda: datetime(2026, 9, 24, 9, 30, tzinfo=UTC),
        candidate_session_date=lambda: CANDIDATE,
        sample_seed=42,
    )
    store = MarketPanelStore(
        tmp_path / "market.db", clock=lambda: datetime(2026, 9, 24, 9, 30, tzinfo=UTC)
    )

    summary = capture_once(adapter, store)
    by_kind = {r.kind: r for r in summary.records}
    assert by_kind["bars"].status == "ok"
    assert by_kind["bars"].expected_count == 3

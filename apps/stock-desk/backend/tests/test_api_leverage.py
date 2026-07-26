"""API tests for ``GET /api/leverage/{symbol}``."""

from __future__ import annotations

from app.api.leverage import NO_INDEX_ADAPTER_NOTE
from tests.api_helpers import position_payload, recent_bars, trending_closes
from tests.conftest import ApiHarness

_LEVERAGED = position_payload(
    symbol="00631L", instrument_type="leveraged_etf", quantity="2000", avg_cost="80"
)


def _seed(harness: ApiHarness, symbol: str, count: int = 300) -> None:
    harness.price_service.seed(symbol, recent_bars(trending_closes(count), symbol=symbol))


def test_leverage_chapter_is_returned_for_a_held_leveraged_etf(
    api_harness: ApiHarness,
) -> None:
    _seed(api_harness, "00631L")
    created = api_harness.client.post("/api/positions", json=_LEVERAGED).json()
    body = api_harness.client.get("/api/leverage/00631L").json()
    assert body["position_id"] == created["id"]
    chapter = body["chapter"]
    assert set(chapter) >= {
        "symbol",
        "position_id",
        "generated_at",
        "disclosure",
        "detection",
        "holding",
        "drag",
        "erosion",
        "notes",
        "chapter_status",
    }
    assert chapter["detection"]["status"] == "ok"
    assert chapter["detection"]["leverage_factor"] == 2.0
    # Registry metadata is still unverified, and the chapter says so.
    assert chapter["detection"]["metadata_verified"] is False


def test_index_blocks_report_insufficient_data_without_an_index_adapter(
    api_harness: ApiHarness,
) -> None:
    _seed(api_harness, "00631L")
    api_harness.client.post("/api/positions", json=_LEVERAGED)
    body = api_harness.client.get("/api/leverage/00631L").json()
    assert body["index_bars_available"] is False
    chapter = body["chapter"]
    # The code path runs end to end; the two index-based blocks are honest.
    assert chapter["drag"]["status"] == "insufficient_data"
    assert chapter["erosion"]["status"] == "insufficient_data"
    assert chapter["chapter_status"] == "insufficient_data"
    assert body["status"] == "insufficient_data"
    assert NO_INDEX_ADAPTER_NOTE in chapter["notes"]


def test_holding_block_is_computed_from_the_etf_bars(api_harness: ApiHarness) -> None:
    _seed(api_harness, "00631L")
    api_harness.client.post("/api/positions", json=_LEVERAGED)
    holding = api_harness.client.get("/api/leverage/00631L").json()["chapter"]["holding"]
    # Bars only cover the last 300 days, well after the 2024 opened_at, so the
    # holding window is measured from the first available bar onwards.
    assert holding["status"] == "ok"
    assert holding["bars_since_opened_at"] == 300


def test_a_plain_stock_is_not_applicable_but_still_a_200(api_harness: ApiHarness) -> None:
    _seed(api_harness, "2330")
    api_harness.client.post("/api/positions", json=position_payload())
    body = api_harness.client.get("/api/leverage/2330").json()
    assert body["status"] == "ok"
    assert body["chapter"]["chapter_status"] == "not_applicable"
    assert body["chapter"]["detection"]["is_daily_reset_leveraged"] is False


def test_missing_holding_is_a_404_with_a_chinese_reason(api_harness: ApiHarness) -> None:
    response = api_harness.client.get("/api/leverage/00631L")
    assert response.status_code == 404
    assert "找不到此標的的持倉" in response.json()["detail"]


def test_chapter_without_bars_still_answers(api_harness: ApiHarness) -> None:
    # Position exists but no price data: the chapter must degrade, not crash.
    api_harness.client.post("/api/positions", json=_LEVERAGED)
    body = api_harness.client.get("/api/leverage/00631L").json()
    assert body["status"] == "insufficient_data"
    assert body["chapter"]["holding"]["status"] == "insufficient_data"
    assert body["data"]["bar_count"] == 0


def test_chapter_carries_no_action_or_target_fields(api_harness: ApiHarness) -> None:
    _seed(api_harness, "00631L")
    api_harness.client.post("/api/positions", json=_LEVERAGED)
    chapter = api_harness.client.get("/api/leverage/00631L").json()["chapter"]
    forbidden = {"action", "rating", "score", "target_price", "holding_period_suggestion"}
    assert forbidden.isdisjoint(chapter)

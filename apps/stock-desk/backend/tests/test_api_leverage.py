"""API tests for ``GET /api/leverage/{symbol}``."""

from __future__ import annotations

from app.leverage.index_mapping import INDEX_MAPPING
from tests.api_helpers import (
    oscillating_closes,
    position_payload,
    recent_bars,
    trending_closes,
)
from tests.conftest import ApiHarness

#: 00631L is an ``unmapped`` row: no queryable index exists for it.
_LEVERAGED = position_payload(
    symbol="00631L", instrument_type="leveraged_etf", quantity="2000", avg_cost="80"
)
#: 00675L is mapped to ``^TWII``, so it exercises the wired-up index path.
_MAPPED_LEVERAGED = position_payload(
    symbol="00675L", instrument_type="leveraged_etf", quantity="2000", avg_cost="80"
)


def _seed(harness: ApiHarness, symbol: str, count: int = 300) -> None:
    harness.price_service.seed(symbol, recent_bars(trending_closes(count), symbol=symbol))


def _seed_index(harness: ApiHarness, series_symbol: str, count: int = 300) -> None:
    harness.index_service.seed(
        series_symbol,
        recent_bars(oscillating_closes(count), symbol=series_symbol),
    )


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


def test_index_blocks_report_insufficient_data_for_an_unmapped_symbol(
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
    # The mapping row's own note is the reason, stated exactly once -- and no
    # index source was consulted, because there is nothing to ask for.
    note = INDEX_MAPPING["00631L"].note
    assert chapter["notes"].count(note) == 1
    assert api_harness.index_service.calls == []


def test_a_mapped_symbol_is_computed_against_its_real_index_series(
    api_harness: ApiHarness,
) -> None:
    _seed(api_harness, "00675L")
    _seed_index(api_harness, "^TWII")
    api_harness.client.post("/api/positions", json=_MAPPED_LEVERAGED)
    body = api_harness.client.get("/api/leverage/00675L").json()

    assert body["index_bars_available"] is True
    # The index was requested by its own code, in the market the mapping names.
    assert [call[:2] for call in api_harness.index_service.calls] == [("^TWII", "TW")]
    chapter = body["chapter"]
    assert chapter["drag"]["status"] == "ok"
    assert chapter["erosion"]["status"] == "ok"
    assert chapter["chapter_status"] == "ok"
    assert body["status"] == "ok"
    # The mapping facts travel with the numbers, still unverified.
    assert chapter["index_mapping"]["series_symbol"] == "^TWII"
    assert chapter["index_mapping_verified"] is False


def test_a_mapped_symbol_with_no_index_source_says_which_series_is_missing(
    api_harness: ApiHarness,
) -> None:
    # ETF bars are available; only the index series is not (offline, or the
    # source refused). The chapter must degrade, not substitute.
    _seed(api_harness, "00675L")
    api_harness.client.post("/api/positions", json=_MAPPED_LEVERAGED)
    body = api_harness.client.get("/api/leverage/00675L").json()

    assert body["index_bars_available"] is False
    assert body["status"] == "insufficient_data"
    assert body["reason"] is not None
    assert "^TWII" in body["reason"]
    assert any("^TWII" in note for note in body["chapter"]["notes"])
    assert body["chapter"]["drag"]["status"] == "insufficient_data"


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


def test_a_plain_stock_is_not_told_it_has_no_index_mapping(
    api_harness: ApiHarness,
) -> None:
    """An ordinary stock has no benchmark to decompose against.

    Saying "this symbol has no underlying-index mapping" on a chapter that
    does not apply reads as a defect report about a non-problem.
    """
    _seed(api_harness, "2330")
    api_harness.client.post("/api/positions", json=position_payload())
    notes = api_harness.client.get("/api/leverage/2330").json()["chapter"]["notes"]
    assert not any("標的指數對應" in note for note in notes)


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

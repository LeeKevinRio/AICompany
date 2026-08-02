"""Chapter assembly: status honesty, provenance, and refusal to substitute data."""

from __future__ import annotations

from datetime import date
from typing import Any

import pytest

from app.leverage import service as S
from app.leverage.index_mapping import INDEX_MAPPING
from app.positions.models import InstrumentType
from tests.leverage_helpers import (
    bars,
    ideal_leveraged_closes,
    make_position,
    zigzag_closes,
)


def _index_closes() -> list[float]:
    return zigzag_closes(amplitude=0.02, returns=60)


def _chapter(
    *,
    symbol: str = "00675L",
    instrument_type: InstrumentType = "leveraged_etf",
    with_index: bool = True,
    opened_at: date | None = date(2024, 1, 1),
    config: S.LeverageChapterConfig | None = None,
) -> dict[str, Any]:
    index_closes = _index_closes()
    etf_closes = ideal_leveraged_closes(
        index_closes, leverage_factor=2.0, expense_ratio_annual=0.0113
    )
    position = make_position(
        symbol=symbol,
        instrument_type=instrument_type,
        opened_at=opened_at,
    )
    return S.build_leverage_chapter(
        position,
        bars(etf_closes, symbol=symbol),
        bars(index_closes, symbol="^TWII", source="twse-index") if with_index else None,
        config=config,
    )


def test_full_chapter_is_ok_and_carries_every_block() -> None:
    chapter = _chapter()
    assert chapter["chapter_status"] == "ok"
    assert chapter["symbol"] == "00675L"
    assert chapter["position_id"] == 1
    assert chapter["generated_at"]
    assert chapter["disclosure"]

    detection = chapter["detection"]
    assert detection["status"] == "ok"
    assert detection["leverage_factor"] == 2.0
    assert detection["metadata_verified"] is False

    holding = chapter["holding"]
    assert holding["status"] == "ok"
    assert holding["opened_at"] == "2024-01-01"
    assert holding["bars_since_opened_at"] == 61
    assert holding["holding_trading_days"] == 60
    assert holding["holding_days"] == 60

    drag = chapter["drag"]
    assert drag["status"] == "ok"
    for key in (
        "actual_return",
        "naive_expected_return",
        "gap",
        "fee_effect",
        "reset_effect",
        "residual",
    ):
        assert drag[key] is not None
    assert drag["theoretical"]["status"] == "ok"
    assert drag["as_of"] is not None
    assert drag["source"] == "twse"

    erosion = chapter["erosion"]
    assert erosion["status"] == "ok"
    assert len(erosion["scenarios"]) == 2
    assert erosion["as_of"] is not None


def test_chapter_numbers_reproduce_the_decomposition_identity() -> None:
    drag = _chapter()["drag"]
    assert abs(
        drag["actual_return"]
        - drag["naive_expected_return"]
        - (drag["fee_effect"] + drag["reset_effect"] + drag["residual"])
    ) < 1e-12
    # Sideways index, 2x fund: the whole shortfall is mechanical, not directional.
    assert abs(drag["index_return"]) < 1e-12
    assert drag["reset_effect"] < 0.0


def test_unknown_leveraged_symbol_yields_insufficient_data_chapter() -> None:
    chapter = _chapter(symbol="00999X")
    assert chapter["chapter_status"] == "insufficient_data"
    assert chapter["detection"]["status"] == "insufficient_data"
    assert chapter["drag"] is None
    assert chapter["erosion"] is None
    assert chapter["reason"] is not None
    # Holding duration is still measurable without metadata; it is not withheld.
    assert chapter["holding"]["status"] == "ok"


def test_plain_stock_yields_not_applicable_chapter() -> None:
    chapter = _chapter(symbol="2330", instrument_type="stock")
    assert chapter["chapter_status"] == "not_applicable"
    assert chapter["drag"] is None
    assert chapter["erosion"] is None


def test_missing_index_series_is_stated_not_substituted() -> None:
    chapter = _chapter(with_index=False)
    assert chapter["chapter_status"] == "insufficient_data"
    assert chapter["drag"]["status"] == "insufficient_data"
    assert chapter["erosion"]["status"] == "insufficient_data"
    assert any("標的指數" in note for note in chapter["notes"])


def test_chapter_carries_the_index_mapping_row_and_its_verification_flag() -> None:
    chapter = _chapter()
    assert chapter["index_mapping_verified"] is False
    mapping = chapter["index_mapping"]
    assert mapping["series_symbol"] == "^TWII"
    assert mapping["basis"] == "official_index"
    assert mapping["return_basis"] == "unknown"
    assert mapping["verified"] is False
    assert mapping["mapping_verified_on"] is None
    assert any("index_mapping_verified=false" in note for note in chapter["notes"])
    # The basis travels into the block that used it, and its unverified
    # dividend treatment is stated as an assumption.
    assert chapter["drag"]["index_basis"] == "official_index"
    assert chapter["drag"]["index_return_basis"] == "unknown"
    assert any("含息口徑未查證" in line for line in chapter["drag"]["assumptions"])


def test_an_unmapped_fund_refuses_both_blocks_with_the_mapping_note() -> None:
    # 00631L's benchmark has no established queryable code, so the chapter
    # refuses even though index bars were handed in.
    chapter = _chapter(symbol="00631L")
    note = INDEX_MAPPING["00631L"].note
    assert chapter["chapter_status"] == "insufficient_data"
    assert chapter["drag"]["status"] == "insufficient_data"
    assert chapter["drag"]["reason"] == note
    assert chapter["erosion"]["status"] == "insufficient_data"
    assert chapter["erosion"]["reason"] == note
    assert note in chapter["notes"]
    assert chapter["index_mapping"]["basis"] == "unmapped"
    assert chapter["index_mapping_verified"] is False
    # The block echoes what it was (not) given rather than implying an index.
    assert chapter["drag"]["index_basis"] == "unmapped"
    assert any("不是官方標的指數" in line for line in chapter["drag"]["assumptions"])


def test_unmapped_reason_does_not_read_as_a_temporary_outage() -> None:
    reason = _chapter(symbol="00632R")["drag"]["reason"]
    for phrase in ("暫時", "稍後", "重試", "故障"):
        assert phrase not in reason


def test_a_registry_row_with_no_mapping_row_still_answers(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # C-3 forbids this state and a test enforces it; if it ever happened the
    # chapter must still refuse cleanly instead of assuming a series.
    monkeypatch.delitem(INDEX_MAPPING, "00675L")
    chapter = _chapter()
    assert chapter["index_mapping"] is None
    assert chapter["index_mapping_verified"] is False
    assert chapter["drag"]["reason"] == S.NO_MAPPING_ROW_REASON
    assert chapter["erosion"]["reason"] == S.NO_MAPPING_ROW_REASON


def test_an_oversized_residual_trips_the_chapter_level_reminder() -> None:
    # The ETF ran away from the index: whatever this gap is, it is not the
    # mechanics the decomposition claims to be attributing.
    position = make_position(symbol="00675L", opened_at=date(2024, 1, 1))
    chapter = S.build_leverage_chapter(
        position,
        bars([100.0, 120.0, 150.0], symbol="00675L"),
        bars([100.0, 110.0, 99.0], symbol="^TWII", source="twse-index"),
    )
    assert chapter["drag"]["status"] == "ok"
    assert chapter["drag"]["residual_alert"] is True
    assert any("殘差異常大" in note for note in chapter["notes"])
    assert any("請勿將本次歸因視為定論" in note for note in chapter["notes"])


def test_a_normal_residual_does_not_trip_the_reminder() -> None:
    chapter = _chapter()
    assert chapter["drag"]["residual_alert"] is False
    assert not any("殘差異常大" in note for note in chapter["notes"])


def test_partial_status_when_only_one_block_computes() -> None:
    # Opened late enough that the drag window is a single aligned bar, while the
    # erosion window (which looks at the index alone) still has plenty of data.
    chapter = _chapter(opened_at=date(2024, 3, 1))
    assert chapter["drag"]["status"] == "insufficient_data"
    assert chapter["erosion"]["status"] == "ok"
    assert chapter["chapter_status"] == "partial"


def test_without_opened_at_the_window_is_untruncated_and_dates_are_null() -> None:
    # No open date stated: the decomposition runs over every available bar
    # (same numbers as opening on the first one), and every "since opened_at"
    # figure is reported as null instead of being filled from a guessed date.
    chapter = _chapter(opened_at=None)
    baseline = _chapter(opened_at=date(2024, 1, 1))

    holding = chapter["holding"]
    assert holding["opened_at"] is None
    assert holding["bars_since_opened_at"] is None
    assert holding["holding_trading_days"] is None
    assert holding["holding_days"] is None
    assert holding["reason"] is not None
    # The bars actually available are still stated honestly.
    assert holding["first_bar_date"] == "2024-01-01"
    assert holding["last_bar_date"] == baseline["holding"]["last_bar_date"]

    drag = chapter["drag"]
    assert drag["status"] == "ok"
    assert drag["window"]["opened_at"] is None
    assert drag["window"]["days_since_opened_at"] is None
    assert drag["window"]["aligned_bars"] == baseline["drag"]["window"]["aligned_bars"]
    assert drag["actual_return"] == baseline["drag"]["actual_return"]
    assert chapter["chapter_status"] == "ok"


def test_holding_block_insufficient_when_no_bars_after_open() -> None:
    chapter = _chapter(opened_at=date(2024, 6, 1))
    assert chapter["holding"]["status"] == "insufficient_data"
    assert chapter["holding"]["holding_days"] is None
    assert chapter["holding"]["reason"] is not None


def test_blocks_can_be_switched_off() -> None:
    chapter = _chapter(config=S.LeverageChapterConfig(enable_drag=False))
    assert chapter["drag"] is None
    assert chapter["erosion"]["status"] == "ok"
    assert chapter["chapter_status"] == "partial"

    both_off = _chapter(
        config=S.LeverageChapterConfig(enable_drag=False, enable_erosion=False)
    )
    assert both_off["chapter_status"] == "insufficient_data"


def test_classification_mismatch_is_surfaced_in_notes() -> None:
    chapter = _chapter(instrument_type="etf")
    assert chapter["detection"]["classification_mismatch"] is True
    assert chapter["chapter_status"] == "ok"
    assert any("instrument_type" in note for note in chapter["notes"])


def test_custom_config_windows_are_honoured() -> None:
    config = S.LeverageChapterConfig(
        erosion_window=30,
        erosion_min_observations=10,
        erosion_horizons=(("1_week", 5),),
    )
    chapter = _chapter(config=config)
    erosion = chapter["erosion"]
    assert erosion["window"] == 30
    assert [s["label"] for s in erosion["scenarios"]] == ["1_week"]

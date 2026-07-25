"""Chapter assembly: status honesty, provenance, and refusal to substitute data."""

from __future__ import annotations

from datetime import date
from typing import Any

from app.leverage import service as S
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
    symbol: str = "00631L",
    instrument_type: InstrumentType = "leveraged_etf",
    with_index: bool = True,
    opened_at: date = date(2024, 1, 1),
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
        bars(index_closes, symbol="TW50", source="twse-index") if with_index else None,
        config=config,
    )


def test_full_chapter_is_ok_and_carries_every_block() -> None:
    chapter = _chapter()
    assert chapter["chapter_status"] == "ok"
    assert chapter["symbol"] == "00631L"
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


def test_partial_status_when_only_one_block_computes() -> None:
    # Opened late enough that the drag window is a single aligned bar, while the
    # erosion window (which looks at the index alone) still has plenty of data.
    chapter = _chapter(opened_at=date(2024, 3, 1))
    assert chapter["drag"]["status"] == "insufficient_data"
    assert chapter["erosion"]["status"] == "ok"
    assert chapter["chapter_status"] == "partial"


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

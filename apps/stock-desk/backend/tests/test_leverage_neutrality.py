"""The red-line guard: this chapter states mechanics, it never tells anyone what to do.

Two scans over the *serialized* chapter (the exact shape that reaches the API
and the UI, not the internal objects):

1. **Field scan** -- no key may name an action, a rating, a score, or a target
   price. A number the UI can render as "do this" must not exist to begin with.
2. **Text scan** -- no free-text string may contain advice vocabulary in
   Traditional Chinese or English.

The scans also run over the source of ``app/leverage`` so a future edit cannot
introduce a banned phrase in a string literal without this test noticing.
"""

from __future__ import annotations

from datetime import date
from pathlib import Path
from typing import Any

import pytest

from app.leverage import service as S
from app.positions.models import InstrumentType
from tests.leverage_helpers import (
    bars,
    ideal_leveraged_closes,
    make_position,
    zigzag_closes,
)

# Field names that would turn a measurement surface into an advice surface.
BANNED_KEYS = frozenset(
    {
        "action",
        "actions",
        "advice",
        "call",
        "grade",
        "rating",
        "recommendation",
        "recommendations",
        "score",
        "signal_action",
        "stance",
        "suggested_action",
        "suggestion",
        "suggestions",
        "target_price",
        "verdict",
    }
)

BANNED_ZH = (
    "該買",
    "該賣",
    "建議",
    "保證",
    "目標價",
    "推薦",
    "應買",
    "應賣",
    "買進",
    "賣出",
    "加碼",
    "減碼",
    "停損",
    "停利",
    "必漲",
    "必跌",
    "穩賺",
    "包賺",
    "無風險",
)

BANNED_EN = (
    "should buy",
    "should sell",
    "recommend",
    "guarantee",
    "buy signal",
    "sell signal",
    "target price",
    "risk-free",
    "sure thing",
)

LEVERAGE_PACKAGE = Path(__file__).resolve().parents[1] / "app" / "leverage"


def _chapters() -> list[dict[str, Any]]:
    """One chapter per interesting state, so every text path is scanned."""
    index_closes = zigzag_closes(amplitude=0.02, returns=60)
    etf_closes = ideal_leveraged_closes(
        index_closes, leverage_factor=2.0, expense_ratio_annual=0.0113
    )
    index_bars = bars(index_closes, symbol="TW50", source="twse-index")

    def build(
        symbol: str,
        instrument_type: InstrumentType,
        *,
        with_index: bool = True,
        opened_at: date = date(2024, 1, 1),
    ) -> dict[str, Any]:
        return S.build_leverage_chapter(
            make_position(
                symbol=symbol, instrument_type=instrument_type, opened_at=opened_at
            ),
            bars(etf_closes, symbol=symbol),
            index_bars if with_index else None,
        )

    return [
        build("00631L", "leveraged_etf"),
        build("00632R", "leveraged_etf"),
        build("TQQQ", "etf"),
        build("00999X", "leveraged_etf"),
        build("2330", "stock"),
        build("00631L", "leveraged_etf", with_index=False),
        build("00631L", "leveraged_etf", opened_at=date(2024, 3, 1)),
    ]


def _walk(node: Any, path: str = "") -> list[tuple[str, Any]]:
    """Flatten a serialized chapter into ``(path, leaf)`` pairs."""
    out: list[tuple[str, Any]] = []
    if isinstance(node, dict):
        for key, value in node.items():
            out.append((f"{path}.{key}", key))
            out.extend(_walk(value, f"{path}.{key}"))
    elif isinstance(node, list | tuple):
        for i, value in enumerate(node):
            out.extend(_walk(value, f"{path}[{i}]"))
    else:
        out.append((path, node))
    return out


@pytest.mark.parametrize("chapter", _chapters())
def test_no_action_shaped_field_exists(chapter: dict[str, Any]) -> None:
    for path, _ in _walk(chapter):
        key = path.rsplit(".", 1)[-1].split("[")[0]
        assert key.lower() not in BANNED_KEYS, f"advice-shaped field at {path}"


@pytest.mark.parametrize("chapter", _chapters())
def test_no_advice_vocabulary_in_any_string(chapter: dict[str, Any]) -> None:
    for path, leaf in _walk(chapter):
        if not isinstance(leaf, str):
            continue
        lowered = leaf.lower()
        for phrase in BANNED_ZH:
            assert phrase not in leaf, f"advice wording {phrase!r} at {path}"
        for phrase in BANNED_EN:
            assert phrase not in lowered, f"advice wording {phrase!r} at {path}"


def test_chapter_ships_its_disclosure_and_assumptions() -> None:
    chapter = _chapters()[0]
    assert "不是預測" in chapter["disclosure"]
    assert len(chapter["drag"]["assumptions"]) >= 5
    assert len(chapter["erosion"]["assumptions"]) >= 5
    assert "情境推估" in chapter["erosion"]["nature"]


def test_source_files_contain_no_advice_vocabulary() -> None:
    # Scoped to the Chinese list on purpose: by the package's language
    # convention every user-facing string is Traditional Chinese, so a banned
    # phrase in the source is necessarily an output string. The English list is
    # not applied here because the English in these files is docstrings that
    # legitimately describe what the module refuses to emit ("no rating, no
    # target price"); English output text is still covered by the chapter-level
    # scan above.
    files = sorted(LEVERAGE_PACKAGE.glob("*.py"))
    assert files
    for file in files:
        text = file.read_text(encoding="utf-8")
        for phrase in BANNED_ZH:
            assert phrase not in text, f"advice wording {phrase!r} in {file.name}"

"""N-190 字面: every sentence is the risk ruling verbatim, re-read from the file (N190-C6).

Sources (ADR-0040 標頭「來源簡稱」):

* [風控-1104] ``work/reviews/2026-11-04-N190重裁-風控.md`` -- N190-I and its two
  item formats;
* [風控-1105] ``work/reviews/2026-11-05-N177修復與N190字面裁示-風控.md`` -- B-2, B-4.

B-1's three sentences are not implemented (ADR-0040 Decision 10, QB-13).
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from app.playbook import wording

REPO = Path(__file__).resolve().parents[4]
RULING_1104 = REPO / "work/reviews/2026-11-04-N190重裁-風控.md"
RULING_1105 = REPO / "work/reviews/2026-11-05-N177修復與N190字面裁示-風控.md"
WORDING_SOURCE = Path(wording.__file__)


def _after_bold(path: Path, marker: str) -> str:
    """The first 「…」 paragraph after the one bold line of ``path`` holding ``marker``."""
    lines = path.read_text(encoding="utf-8").splitlines()
    (heading,) = [index for index, line in enumerate(lines) if marker in line and "**" in line]
    body = next(line for line in lines[heading + 1 :] if line.startswith("「"))
    assert body.endswith("」")
    return body[1:-1]


def _item(path: Path, marker: str) -> str:
    """The first 「…」 on the one line of ``path`` that contains ``marker``."""
    (line,) = [line for line in path.read_text(encoding="utf-8").splitlines() if marker in line]
    found = re.search(r"「([^」]*)」", line)
    assert found is not None
    return found.group(1)


RULED: dict[str, tuple[Path, str, bool]] = {
    # name: (file, marker, whether the marker names a bold heading)
    "SETTLEMENT_EARLIER_SELL_NOT_DEDUCTED_NOTE": (
        RULING_1104,
        "`SETTLEMENT_EARLIER_SELL_NOT_DEDUCTED_NOTE`（N190-I，逐字定稿）",
        True,
    ),
    "SETTLEMENT_EARLIER_SELL_BATCH_ITEM": (RULING_1104, "- 逐批列：「", False),
    "SETTLEMENT_EARLIER_SELL_SYMBOL_ITEM": (RULING_1104, "- S2 列：「", False),
}


def _ruled(name: str) -> str:
    path, marker, bold = RULED[name]
    return _after_bold(path, marker) if bold else _item(path, marker)


@pytest.mark.parametrize("name", sorted(RULED))
def test_every_n190_sentence_is_the_ruling_verbatim(name: str) -> None:
    assert getattr(wording, name) == _ruled(name)


#: 風控 2026-11-04 第二節之 2 自查: N190-I contains none of these, and no exemption.
N190_I_FORBIDDEN = (
    "需",
    "應",
    "建議",
    "務必",
    "盡快",
    "否則",
    "安全",
    "已取消",
    "已撤單",
    "你已買進",
    "對應",
)


@pytest.mark.parametrize(
    "name",
    [
        "SETTLEMENT_EARLIER_SELL_NOT_DEDUCTED_NOTE",
        "SETTLEMENT_EARLIER_SELL_BATCH_ITEM",
        "SETTLEMENT_EARLIER_SELL_SYMBOL_ITEM",
    ],
)
def test_n190_i_carries_no_forbidden_word(name: str) -> None:
    sentence = getattr(wording, name)
    for banned in N190_I_FORBIDDEN:
        assert banned not in sentence, (name, banned)


def test_n190_i_states_both_possibilities_and_that_nothing_is_ordered() -> None:
    sentence = wording.SETTLEMENT_EARLIER_SELL_NOT_DEDUCTED_NOTE
    assert "本系統不下單" in sentence
    assert "若已賣出且成交" in sentence and "若尚未賣出" in sentence
    assert re.findall(r"{(\w+)}", sentence) == ["later_items"]


def test_the_item_formats_take_the_lines_own_values() -> None:
    assert re.findall(r"{(\w+)}", wording.SETTLEMENT_EARLIER_SELL_BATCH_ITEM) == [
        "symbol",
        "batch_no",
        "rule_id",
        "shares",
        "execution_date",
    ]
    assert re.findall(r"{(\w+)}", wording.SETTLEMENT_EARLIER_SELL_SYMBOL_ITEM) == [
        "symbol",
        "rule_id",
        "shares",
        "execution_date",
    ]


#: B-1's own fragment (風控 2026-11-05 B-1; ADR-0040 QB-13).
B1_FRAGMENT = "資料層判定這份快取仍在有效期間內"


def test_b1_is_not_implemented() -> None:
    """QB-13 / QB-14: no B-1 sentence anywhere in ``wording.py`` (Decision 10, 11)."""
    assert WORDING_SOURCE.read_text(encoding="utf-8").count(B1_FRAGMENT) == 0
    assert all(
        B1_FRAGMENT not in value for value in vars(wording).values() if isinstance(value, str)
    )

"""N-171 群組 A wording, verbatim (風控 2026-11-03 第二節之 2; 2026-11-04 第 3、4 點).

Each constant is pinned to the signed-off text; the A-2 of 2026-11-03 is retired
and may not come back. Placeholders are exactly the ones the ruling defines.
"""

from __future__ import annotations

import ast
import string
from pathlib import Path

import pytest

from app.playbook import wording

SIGNED_OFF: dict[str, str] = {
    # A-1
    "PENDING_EXIT_BLOCK_TITLE": ("全部出清產生、尚未結算的賣出指令"),
    # A-2（風控 2026-11-04 修訂版）
    "PENDING_EXIT_BLOCK_LEAD": (
        "本區塊依 {read_at} 讀取的紀錄，列出你先前提交「全部出清」時產生、"
        "帳冊尚未結算，且所屬批次在帳冊仍記為持有的賣出指令；"
        "這些指令是該要求的機械執行結果，非本系統的判斷或建議。它們不由規則集產生，"
        "不列入指令帳冊，也不是依本頁面所載收盤資料重新計算的結果；"
        "本頁其他說明若提到指令帳冊中的指令或未產生指令，不包括本區塊的指令。"
        "所屬批次在帳冊已不再記為持有的出清賣出指令，即使尚未結算，也不列入本區塊；"
        "未列入不代表該指令已經結算或被取消，也不代表你在券商已賣出這批。本系統不下單，"
        "無法得知你是否已依出清賣出指令在券商下單或成交，實際持股以你的券商回報為準。"
    ),
    # A-3
    "PENDING_EXIT_COVERED_LEAD": (
        "下列指令仍涵蓋所列批次。若你已依這些指令在券商賣出且成交，"
        "你在券商已無這幾批的持股，請勿就同一批到券商重複下賣單；"
        "若你在券商仍持有這幾批而尚未賣出（包括未下單或未成交），以下列批次與股數為準。"
        "市價單在跌停或無量時可能無法成交，實際成交結果以你的券商回報為準。"
    ),
    # A-4
    "PENDING_EXIT_UNCLASSIFIED_LEAD": (
        "若你已依下列指令在券商賣出且成交，你在券商已無這幾批的持股，"
        "請勿就同一批到券商重複下賣單；"
        "若你在券商仍持有這幾批而尚未賣出（包括未下單或未成交），以下列批次與股數為準。"
        "市價單在跌停或無量時可能無法成交，實際成交結果以你的券商回報為準。"
    ),
    # A-5
    "PENDING_EXIT_ITEM": (
        "{symbol}第 {batch_no} 批賣出 {shares} 股（預定執行日 {execution_dates} 開盤以市價單送出）"
    ),
    # A-6
    "PENDING_EXIT_PAST_DUE_NOTE": (
        "預定執行日 {past_due_dates} 已過、仍未結算；本系統不下單，"
        "也無法得知你在券商是否已賣出這批，請以你的券商回報為準。"
    ),
    # A-7
    "PENDING_EXIT_COVERED_LABEL": ("仍涵蓋所列批次的指令"),
    # A-8
    "PENDING_EXIT_STALE_LABEL": ("已不再涵蓋該批次、仍未結算的先前指令"),
    # A-9
    "PENDING_EXIT_STALE_LEAD": (
        "下列先前的出清賣出指令至今未能結算："
        "其預定執行日沒有日線開盤價（可能是該日休市，也可能是資料缺漏），"
        "而之後的交易日已有日線資料，因此本系統不再以這些指令涵蓋所列批次。"
        "這些指令並未被取消；若日後補得該日的開盤價，帳冊仍可能依該日開盤價判定，"
        "但同一批次在帳冊的股數不會重複減少，判定的日期與價格可能與你實際賣出的不同。"
        "本系統不下單，無法得知你是否已就這幾批在券商賣出："
        "若你已賣出且成交（不論是否依先前的指令），你在券商已無這幾批的持股，"
        "本區塊所列這幾批的賣出指令都不適用於你，請勿就這幾批到券商重複下賣單；"
        "若尚未賣出（包括該日休市、未下單或未成交），見各列的說明。"
    ),
    # A-11
    "PENDING_EXIT_STALE_ALSO_COVERED_NOTE": (
        "這批另有上列仍涵蓋的賣出指令；若你在券商仍持有這批而尚未賣出，以上列該批的賣出指令為準。"
    ),
    # A-12
    "PENDING_EXIT_STALE_UNCOVERED_NOTE": (
        "這批目前沒有仍涵蓋它的出清賣出指令，帳冊仍記為持有；"
        "若你在券商仍持有這批而尚未賣出，可再次提交全部出清，替這批產生新的賣出指令。"
    ),
    # A-13
    "PENDING_EXIT_UNAUTHORED_NOTE": (
        "目前尚無你本人的規則集設定或修改紀錄，本頁不執行結算，也不載入日線資料："
        "在你確認規則集之前，帳冊不會依預定執行日開盤價判定上列指令，"
        "它們會持續列在本區塊；本頁也無法判斷其中是否有因預定執行日沒有日線開盤價、"
        "已不再涵蓋該批次的指令。本頁其他說明若提到你目前持有某檔、尚未出清，"
        "是指帳冊尚未結算上列指令而仍記為持有，不是指上列指令未產生，"
        "也不代表你在券商的持股狀態。"
    ),
    # A-14
    "PENDING_EXIT_RECEIPT_OVERLAP_NOTE": (
        "本頁若同時顯示以「EMERGENCY_EXIT 已受理」開頭的說明，其中所述、"
        "尚未結算的賣出指令與本區塊所列的是同一組指令，不是另外一組。"
    ),
    # A-15（風控 2026-11-04 第 4 點）
    "PENDING_EXIT_SHARES_REDUCED_NOTE": (
        "這批在出清賣出指令產生之後，帳冊又依其他賣出指令（例如停損、停利）"
        "判定賣出一部分，因此上列股數是帳冊目前仍記為持有的股數，"
        "少於這批出清賣出指令產生時所列的股數。本系統不下單，"
        "無法得知你是否已依那些其他賣出指令在券商賣出：若已賣出且成交，"
        "上列股數已扣除那部分；若未下單或未成交，你在券商的這批持股可能多於上列股數，"
        "多出的股數不在帳冊內，S/P 系列不會評估它們的停損停利，"
        "再次提交全部出清也不會涵蓋它們，實際持股以你的券商回報為準。"
    ),
}

PLACEHOLDERS: dict[str, set[str]] = {
    "PENDING_EXIT_BLOCK_LEAD": {"read_at"},
    "PENDING_EXIT_ITEM": {"symbol", "batch_no", "shares", "execution_dates"},
    "PENDING_EXIT_PAST_DUE_NOTE": {"past_due_dates"},
}

#: The 2026-11-03 A-2, replaced by the 2026-11-04 revision (grep must be 0).
RETIRED_A2 = (
    "本區塊依 {read_at} 讀取的紀錄，列出你先前提交「全部出清」時產生、"
    "帳冊尚未結算的賣出指令；這些指令是該要求的機械執行結果，非本系統的判斷或建議。"
    "它們不由規則集產生，不列入指令帳冊，也不是依本頁面所載收盤資料重新計算的結果；"
    "本頁其他說明若提到指令帳冊中的指令或未產生指令，不包括本區塊的指令。本系統不下單，"
    "無法得知你是否已依這些指令在券商下單或成交，實際持股以你的券商回報為準。"
)


@pytest.mark.parametrize("name", sorted(SIGNED_OFF))
def test_each_block_sentence_is_the_signed_off_text(name: str) -> None:
    assert getattr(wording, name) == SIGNED_OFF[name]


@pytest.mark.parametrize("name", sorted(SIGNED_OFF))
def test_placeholders_are_exactly_the_rulings(name: str) -> None:
    fields = {field for _, field, _, _ in string.Formatter().parse(getattr(wording, name)) if field}
    assert fields == PLACEHOLDERS.get(name, set())


def test_the_stale_row_reuses_the_existing_item_unchanged() -> None:
    """A-10 is ``EMERGENCY_EXIT_STALE_ITEM`` (S10's item), not a new constant."""
    assert not hasattr(wording, "PENDING_EXIT_STALE_ITEM")
    assert wording.EMERGENCY_EXIT_STALE_ITEM == (
        "{symbol}第 {batch_no} 批 {shares} 股（未能結算的指令預定執行日 {stale_dates}）"
    )


def test_the_retired_a2_is_gone_and_the_revision_scopes_to_held_batches() -> None:
    assert wording.PENDING_EXIT_BLOCK_LEAD != RETIRED_A2
    # Adjacent literals are one constant in the AST, so this is a real grep.
    tree = ast.parse(Path(wording.__file__).read_text(encoding="utf-8"))
    literals = [
        node.value
        for node in ast.walk(tree)
        if isinstance(node, ast.Constant) and isinstance(node.value, str)
    ]
    assert not any(RETIRED_A2 in literal for literal in literals)
    assert "所屬批次在帳冊仍記為持有" in wording.PENDING_EXIT_BLOCK_LEAD
    assert wording.PENDING_EXIT_BLOCK_LEAD.count("{read_at}") == 1


def test_a2_and_a15_carry_no_modal_ying_and_get_no_exemption() -> None:
    """風控 2026-11-04 N-171-A 解讀點 6: 「應」 is 0 in A-2 (revised) and A-15, no exemption."""
    for name in ("PENDING_EXIT_BLOCK_LEAD", "PENDING_EXIT_SHARES_REDUCED_NOTE"):
        assert "應" not in getattr(wording, name), name

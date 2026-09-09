"""風控 2026-09-09 REQ-6: the user-facing sentences of the five-condition backtest
are pinned verbatim and scanned against the shared forbidden-term list.

Two surfaces carry them: ``POST /api/backtest``'s ``notes`` (only for
``strategy == "five_conditions"``, rendered as-is by the frontend, so the
frontend's own source scan can never see it) and the event-study CLI report.
A change to any sentence here is a wording change and goes back through
risk-compliance-officer first; this file is what makes that visible.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.api.backtest import FIVE_CONDITIONS_NOTE
from app.backtest.event_study import (
    DEMO_DATA_WARNING,
    FOOTNOTES,
    RESEARCH_USE_NOTICE,
    SCOPE_NOTICE,
    format_report,
    run_event_study,
)
from app.signals.frame import bars_to_frame
from tests.signals_helpers import bars_from_closes
from tests.test_backtest_strategies import _FIVE_CLOSES, _FIVE_VOLUMES

_SHARED_FORBIDDEN_TERMS_PATH = (
    Path(__file__).resolve().parents[2] / "shared" / "forbidden-terms.json"
)

#: The frontend-only terms that matter for text the API hands the browser
#: verbatim (`adviceWording.ts::FRONTEND_FORBIDDEN_TERMS`, the subset a
#: backtest disclosure could plausibly trip) plus the panel PRD's own
#: combinations (R-02). Kept explicit rather than read from the TS file so
#: the backend suite does not parse TypeScript.
_FRONTEND_TERMS = (
    "進場價",
    "出場價",
    "停利價",
    "防守價",
    "支撐位",
    "壓力位",
    "勝率",
    "成功率",
    "命中率",
    "準確率",
    "高機率",
    "即將",
    "有望",
    "可期",
    "可以進場",
    "適合進場",
    "進場條件成立",
    "進場時機",
    "買點",
    "訊號",
    "達標",
    "過關",
    "條件成立",
    "全部成立",
    "全數成立",
)


def _shared_terms() -> tuple[str, ...]:
    payload = json.loads(_SHARED_FORBIDDEN_TERMS_PATH.read_text(encoding="utf-8"))
    return tuple(payload["guarantee"]) + tuple(payload["price_target"])


def _demo_report_text() -> str:
    frame = bars_to_frame(bars_from_closes(_FIVE_CLOSES, volumes=_FIVE_VOLUMES))
    return format_report(run_event_study(frame, symbol="2330", source="demo_synthetic"))


# --- verbatim pins --------------------------------------------------------------


def test_five_conditions_api_note_is_pinned_verbatim() -> None:
    assert FIVE_CONDITIONS_NOTE == (
        "本策略對應個股頁「六項觀察條件」面板中可由日線價量重算的前五條；"
        "第 6 條（防禦型規則）依賴持倉狀態與規則引擎，價格序列無法重算，未納入，"
        "故本報告不是該面板六條的歷史表現。"
        "報告數字另受回測固定採用的出場規則影響："
        "收盤跌破「開倉基準價 − 2×ATR(14)」與「開倉基準價 × 0.92」中較緊者"
        "（ATR 無法計算時只用後者）、"
        "收盤觸及開倉基準價 × 1.2、或收盤低於 MA60，任一觸發即全數出場。"
        "以上為本回測的固定衡量設定，不是操作建議。"
    )


def test_event_study_top_block_sentences_are_pinned_verbatim() -> None:
    assert SCOPE_NOTICE == (
        "本研究僅涵蓋面板六項觀察條件中的前五條；第 6 條（防禦型規則）未納入。"
        "以下數字皆為「五條」，非「面板」。"
    )
    assert DEMO_DATA_WARNING == (
        "警告：本次使用的是離線示範資料（demo_synthetic），不是市場資料。"
        "以下數字只能用來驗證計算管線，不能拿來描述任何真實標的。"
    )


def test_event_study_footnotes_are_pinned_verbatim_and_in_order() -> None:
    assert FOOTNOTES == (
        "本輸出為歷史分布的描述性統計，僅供研究與教育用途，不構成投資建議，也不是任何買賣指示；"
        "歷史分布不預測未來，任何一次結果都可能落在區間之外。",
        "本研究只涵蓋面板六條中的前五條；第 6 條（建議引擎防禦型規則）依賴持倉狀態與規則引擎，"
        "價格序列算不出來，未納入。所有數字都是「五條」，不是「面板」。",
        "前瞻報酬為收盤對收盤的價格變化，未計手續費、證交稅與滑價，因此不是任何策略的報酬；"
        "含成本的版本請看 walk-forward 回測報告（POST /api/backtest, strategy=five_conditions）。",
        "事件常連續出現，前瞻視窗互相重疊，樣本並不獨立；全樣本的 Wilson 區間會低估不確定性，"
        "故每個橫軸另附非重疊子樣本（同一群集只取最早一根）的比例與區間，兩者並列。",
        "前半／後半只是依日期對半切。本研究沒有擬合任何參數（門檻全部取自面板固定值），"
        "所以後半不是「模型的樣本外」，只是同一組固定門檻在另一段期間的穩定度檢查。",
        "中位數與四分位描述分布位置，不是預測；正報酬比例是歷史頻率，不是對未來的機率。"
        "區間為 Wilson 95%，區間之外的結果本來就可能發生。",
    )
    assert FOOTNOTES[0] is RESEARCH_USE_NOTICE


# --- placement --------------------------------------------------------------------


def test_scope_notice_sits_in_the_top_block_before_any_number() -> None:
    text = _demo_report_text()
    lines = text.splitlines()
    scope_at = lines.index(SCOPE_NOTICE)
    # Right under the data-source line, above the demo warning and every table.
    assert "資料來源：demo_synthetic" in lines[scope_at - 1]
    assert lines.index(DEMO_DATA_WARNING) == scope_at + 2
    assert scope_at < next(i for i, line in enumerate(lines) if "【全期】" in line)


def test_research_use_notice_is_the_first_line_under_the_limitations_heading() -> None:
    lines = _demo_report_text().splitlines()
    heading_at = lines.index("說明與限制：")
    assert lines[heading_at + 1] == f"  - {RESEARCH_USE_NOTICE}"


# --- forbidden-term scans -------------------------------------------------------


@pytest.mark.parametrize("term", _shared_terms() + _FRONTEND_TERMS)
def test_api_note_carries_no_forbidden_term(term: str) -> None:
    assert term not in FIVE_CONDITIONS_NOTE


@pytest.mark.parametrize("term", _shared_terms() + _FRONTEND_TERMS)
def test_event_study_report_carries_no_forbidden_term(term: str) -> None:
    assert term not in _demo_report_text()


def test_no_directive_wording_in_either_surface() -> None:
    # 「建議」 may only appear inside a denial (不是…建議 / 不構成…建議); never as a directive.
    for text in (FIVE_CONDITIONS_NOTE, _demo_report_text()):
        for index in [i for i in range(len(text)) if text.startswith("建議", i)]:
            preceding = text[max(0, index - 8) : index]
            is_module_name = text[index : index + 4] == "建議引擎"
            assert "不是" in preceding or "不構成" in preceding or is_module_name, preceding

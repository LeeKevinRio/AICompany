"""The Kelly disclosure sentences risk-compliance signed off, pinned as tests.

Every assertion traces to `work/reviews/2026-08-19-C5-Kelly-文案批審.md` (第一輪
through 第七輪) and to its 落地條件 1-58. Five kinds of guard live here:

* **逐字** -- every approved sentence the repo ships is retyped below and
  compared character
  for character against the constants the application ships. Retyping is the
  point: importing the constant and asserting it equals itself would pass
  through any drift, so the expected text is entered from the review document by
  hand. A one-character difference is a compliance regression (落地條件 1/17).
* **備案不存在** -- the drafts the review rejected must not survive anywhere in
  the shipped source, in a string or in a comment. A vetoed sentence sitting in
  a comment is one copy-paste away from being a vetoed sentence on a screen.
* **勝率白名單** -- 分歧① let the word stand on the condition that it is
  mechanised: an exact-set assertion over the backend modules allowed to contain
  it, zero occurrences on the front end's Kelly surface, the front-end banned
  term left in place, and `shared/forbidden-terms.json` left alone.
* **佔位符** -- no threshold and no date may be written as a literal, and the
  freshness anchor must render as a plain date (落地條件 9/16, 6-A).
* **結構凍結** -- 5-4 raised the shape of the three refusal messages to a
  required property: one sentence, any code in brackets at the end, no measured
  value interpolated.

Scope of the source scans is the two **shipped** trees, `backend/app` and
`frontend/app`: `work/` holds the review documents, which quote the rejected
drafts on purpose, and this file retypes the approved ones.

This file guards the **text**. Where each sentence is attached, and on what
condition, is asserted beside the code that attaches it: cap 5's eight
(the five (g), (a-2), and the sixth round's two) in
``tests/test_advice_limits.py``, and the front-end rendering in K4c.
"""

from __future__ import annotations

import ast
import json
import re
from pathlib import Path

import pytest
from pydantic import ValidationError

from app.api import kelly_wording as wording
from app.api.kelly import KELLY_NON_FINITE_INTERVAL_MESSAGE
from app.kelly import models, sample_gate

_BACKEND_ROOT = Path(__file__).resolve().parents[1]
_APP_ROOT = _BACKEND_ROOT / "app"
_STOCK_DESK_ROOT = _BACKEND_ROOT.parent
_FRONTEND_APP_ROOT = _STOCK_DESK_ROOT / "frontend" / "app"
_SHARED_FORBIDDEN_TERMS = _STOCK_DESK_ROOT / "shared" / "forbidden-terms.json"


# ---------------------------------------------------------------------------
# ① 18 項逐字定稿
# ---------------------------------------------------------------------------

#: Retyped from the review, keyed by its own item ids. 17 of them live in
#: :mod:`app.api.kelly_wording`; the three refusal messages ((5-1) (5-2) (5-3))
#: live in :mod:`app.kelly.sample_gate`, where the gate that produces them is.
CONFIRMED_VERBATIM: dict[str, str] = {
    "a-1": (
        "此次估計的 f*（Kelly 公式算出的比例，尚未套用上限）的 95% 區間為 "
        "{f_star_ci_low_pct} 至 {f_star_ci_high_pct}。"
        "此區間涵蓋『沒有優勢』的可能——以目前的樣本量，本系統無法確定這個策略是否真的有優勢，"
        "即使點估計本身是正值。"
    ),
    "a-2": (
        "本次估計值的區間涵蓋『沒有優勢』的可能：以目前樣本量，本系統無法確定這個策略是否真的有優勢。"
        "完整區間數字可至設定頁查看。"
    ),
    "b-full": (
        "此標的已記錄 {k_observed} 次回測帶入嘗試（K_observed）——"
        "這個數字含被系統拒絕（422）的嘗試、含你試過的所有策略、不限時間範圍；"
        "另有 {k_distinct_specs} 組不同設定被嘗試過（K_distinct_specs，僅計相異參數組合）。"
        "這兩個數字都可能失真：K_observed 可能因重複送出同一組設定而偏高；"
        "K_distinct_specs 只算相異設定，即使只做過細微調整也會被算成新的一組。"
        "兩者也都無法涵蓋你在系統外或腦中比較過的設定，因此都可能低估你實際檢視過的可能性。"
        "已知的方向是：嘗試越多組設定、只把其中最好看的一次帶入，結果越容易被系統性地高估——"
        "問題出在『事後只挑最好的那一次』這個動作本身，不是任何一組設定本身有誤。"
        "本系統無法得知你實際嘗試過幾次，也不會、也無法事後校正這個高估；"
        "這裡呈現的只是系統看得到的下界。"
    ),
    "b-single": (
        "此標的目前記錄到 1 次回測帶入嘗試"
        "（K_observed，含被拒絕的嘗試、含所有策略、不限時間範圍）。"
        "這只代表你送出『帶入』的次數是 1 次，不代表你只檢視過 1 次回測結果——"
        "本系統無法得知你在畫面上比較過幾種設定、又只送出了其中一組。"
    ),
    "c": (
        "本系統的 walk-forward 是把資料依時間先後分段："
        "較早的區段用來看策略在該段的表現，較晚的區段（樣本外／out-of-sample）用同一組參數再看一次。"
        "三支策略的參數是系統寫死的常數，不會依任何輸入被調整，"
        "因此本系統不會用樣本外資料回頭調整參數。"
        "但也因為如此，『樣本外』在本系統中只代表資料的時間區段位置，"
        "對『你自己反覆嘗試多種設定後才挑一次結果』這件事沒有防護作用（詳見選擇偏誤揭露）。"
    ),
    "e": (
        "此處的『勝率』，是這段歷史樣本中納入計算的回合裡，獲利回合所佔的比例；"
        "這是對已經發生過的事做的統計整理，不是你下一筆交易會不會獲利的機率。"
        "Kelly 公式所要求的 p，在數學上是『重複同一分布下注時獲勝的機率』；"
        "本系統在計算這條上限時，放進這個位置的正是前面這個歷史頻率，而不是這個機率——"
        "這是本功能目前的已知限制，不是已經被系統處理掉的問題。"
    ),
    "e-manual": (
        "此處的『勝率』與『盈虧比』，是你自行輸入（或以回測帶入後自行覆寫）的估計值，"
        "不是本系統量測所得的數字。"
        "Kelly 公式所要求的 p，在數學上是『重複同一分布下注時獲勝的機率』；"
        "本系統在計算這條上限時，放進這個位置的正是你自己輸入（或覆寫）的這個數字——"
        "這是本功能目前的已知限制，不是已經被系統處理掉的問題。"
    ),
    "f-full": (
        "此勝率與盈虧比是你自行輸入的估計值，本系統不會查核其正確性，也不會自行調整你輸入的數字；"
        "不代表系統已為你確認過這組數字合理；"
        "若與實際交易狀況不符，本條上限的判定將隨之失真。"
    ),
    "f-tooltip": (
        "此數字是你自行輸入的估計值，系統未驗證正確性，也不會自動調整；"
        "不代表系統已為你確認過這組數字合理。"
    ),
    "d-1-a": (
        "多數標的、多數期間的完整進出次數都達不到本系統設定的門檻；"
        "未達門檻時，系統會拒絕寫入這筆 Kelly 輸入，這是常見情況，不是系統出錯，"
        "也不代表這支策略或這個標的『不好』。這次沒有寫入的原因與實際數字如下："
    ),
    "d-1-b": ("這次被拒絕寫入的嘗試，已經被系統記錄下來，並計入 K_observed（詳見選擇偏誤揭露）。"),
    "3-b": (
        "這次嘗試已經被系統記錄下來，並計入 K_observed（詳見選擇偏誤揭露）；"
        "這筆輸入，這次沒有被寫入。"
    ),
    "h": (
        "本系統計算樣本外（OOS）回合數時，只計入完整包含在樣本外區段內的回合；"
        "跨越樣本內、外邊界的回合，以及在樣本外區段結束時仍未平倉的回合，會被排除在外，並另行計數。"
        "這個排除方式，會優先排除掉存續時間較長的回合；"
        "這對統計結果會造成什麼方向的影響，目前的證據不足以支持任何方向的判斷。"
    ),
    "g-1": (
        "此標的尚未輸入 Kelly 所需的勝率與盈虧比（可透過手動輸入或回測帶入取得），"
        "本條上限目前無法評估。"
    ),
    "g-2": (
        "此標的的 Kelly 輸入（來源：手動輸入）已過期——"
        "上次更新於 {anchored_on}，距今 {age_days} 天，"
        "超過 {days} 天的新鮮期，本條上限暫不評估；請重新確認數字後更新。"
    ),
    "g-3": (
        "此標的的 Kelly 輸入（來源：回測帶入）已過期——樣本外區段結束於 {anchored_on}，"
        "距今 {age_days} 天，超過 {days} 天的新鮮期，本條上限暫不評估；"
        "請重新執行回測並確認後更新。"
    ),
    "g-4": (
        "此標的的 Kelly 輸入（來源：回測帶入）缺少樣本外區段結束日，本系統無法判定其新鮮度，"
        "一律視為已過期，本條上限暫不評估；請重新執行回測並確認後更新。"
    ),
    # 第七輪（2026-08-22）任務 9，主案原文。
    "g-overridden": (
        "此標的的 Kelly 輸入（來源：回測帶入，已手動調整）已過期——"
        "樣本外區段結束於 {anchored_on}，距今 {age_days} 天，超過 {days} 天的新鮮期，"
        "本條上限暫不評估；請重新執行回測並確認後更新。"
    ),
    "5-1": "這次回測沒有產出可用的結果，本次不寫入 Kelly 輸入（狀態代碼：{status}）。",
    "5-2": (
        "你操作的標的（{path_symbol}，{path_market}）"
        "與這次回測請求中的標的（{body_symbol}，{body_market}）不一致，本次不寫入。"
    ),
    "5-3": (
        "本次回測的樣本外勝率與盈虧比，其中至少一項沒有算出數值，"
        "沒有可寫入的完整配對，本次不寫入 Kelly 輸入。"
    ),
    "500-non-finite": (
        "本次計算出的 f* 區間，其上界與下界之中至少有一端不是有限的數字，"
        "超出本系統可寫入的範圍，這次沒有寫入 Kelly 輸入。"
    ),
    # 第六輪（2026-08-22，第五批）。Retyped from the ruling, not copied from the
    # module, per required 2-D.
    "task-1": (
        "以目前輸入的勝率與盈虧比計算，Kelly 公式算出的比例（f*）不是正值："
        "以目前輸入計算，Kelly 公式不支持任何加碼部位，"
        "分數 Kelly 與硬上限取小後，這條上限這次可用的加碼額度為 0%。"
        "本條上限這次只限制新增加碼的額度，不對你目前已持有的部位提出任何處置意見。"
    ),
    "task-2": (
        "「分數 Kelly 部位上限」這次計算出的加碼額度是 0"
        "（原因見第 5 條的說明，不是因為本次缺少資料），因此不列入這個區間的計算基礎；"
        "這個 0，只代表這條上限這次不提供加碼空間，不涉及你目前部位的任何處置。"
    ),
}

#: Where each id is shipped from. Three modules: the refusal messages belong
#: beside the gate that decides to emit them, and 落地條件 25 names the 500 body's
#: constant by module and line, so it stays where the ruling put it.
SHIPPED: dict[str, str] = {
    **{item: text for item, text in wording.RISK_CONFIRMED_WORDING.items()},
    "5-1": sample_gate.INSUFFICIENT_DATA_MESSAGE,
    "5-2": sample_gate.SYMBOL_MISMATCH_MESSAGE,
    "5-3": sample_gate.PB_NONE_MESSAGE,
    "500-non-finite": KELLY_NON_FINITE_INTERVAL_MESSAGE,
}

#: The three sample-size refusals came through both rounds untouched (第一輪
#: (d): 「原樣一字不動」). They are not part of the 18 -- they were approved
#: before this batch -- but they ship from the same module and share 5-4's
#: structural freeze, so they are pinned here too.
SAMPLE_SIZE_VERBATIM: dict[str, str] = {
    "low_round_trips": (
        "樣本外完整回合數為 {count} 筆，未達門檻 {threshold} 筆，本次不寫入 Kelly 輸入。"
    ),
    "low_win_trips": (
        "樣本外獲利回合數為 {count} 筆，未達門檻 {threshold} 筆，本次不寫入 Kelly 輸入。"
    ),
    "low_loss_trips": (
        "樣本外虧損回合數為 {count} 筆，未達門檻 {threshold} 筆，本次不寫入 Kelly 輸入。"
    ),
}

SHIPPED_SAMPLE_SIZE: dict[str, str] = {
    "low_round_trips": sample_gate.LOW_ROUND_TRIPS_MESSAGE,
    "low_win_trips": sample_gate.LOW_WIN_TRIPS_MESSAGE,
    "low_loss_trips": sample_gate.LOW_LOSS_TRIPS_MESSAGE,
}


def test_the_batch_is_every_sentence_the_review_has_closed_on() -> None:
    """21 through the fourth round, plus the two of the fifth batch this lane ships.

    The sixth round closed on eleven items and the seventh on two; the three
    that land in the risk layer are here ((任務 1) f*<=0, (任務 2) zero allowance
    and (g-overridden)). The rest is display-surface copy arriving with K4c,
    which is why this count is 24 and not 34 -- a sentence is added here when it
    ships, so the assertion says what the repo actually carries rather than what
    the review has approved.
    """
    assert len(CONFIRMED_VERBATIM) == 24
    assert set(SHIPPED) == set(CONFIRMED_VERBATIM)


@pytest.mark.parametrize("item", sorted(CONFIRMED_VERBATIM))
def test_each_approved_sentence_ships_character_for_character(item: str) -> None:
    """落地條件 1/17: 逐字守門，含標點。任一字漂移即整句失效須重送風控。"""
    assert SHIPPED[item] == CONFIRMED_VERBATIM[item], (
        f"({item}) 已偏離風控 2026-08-19 逐字定稿；"
        "字面含標點不得改動，漂移須重送 risk-compliance-officer。"
    )


@pytest.mark.parametrize("code", sorted(SAMPLE_SIZE_VERBATIM))
def test_the_three_sample_size_refusals_are_still_untouched(code: str) -> None:
    """第一輪 (d):「三句 CONFIRMED 原樣一字不動」."""
    assert SHIPPED_SAMPLE_SIZE[code] == SAMPLE_SIZE_VERBATIM[code]


def test_no_disclosure_constant_escapes_the_approved_inventory() -> None:
    """A public sentence with no item id is a sentence risk-compliance never saw."""
    public = {
        name: value
        for name, value in vars(wording).items()
        if name.isupper() and isinstance(value, str) and not name.startswith("_")
    }
    assert set(public.values()) == set(wording.RISK_CONFIRMED_WORDING.values()), sorted(
        set(public) - {n for n, v in public.items() if v in SHIPPED.values()}
    )


def test_the_wording_module_imports_no_application_code() -> None:
    """落地條件 2, as an import fact: this module is text and nothing else.

    It sits in ``app/api`` because several sentences describe what the risk
    layer does, and a copy under ``app/kelly`` would have to reach ``app.advice``
    to stay honest -- the exact edge ``tests/test_kelly_boundary.py`` forbids.
    Importing nothing is what keeps it placeable anywhere and readable by every
    layer, and it is also why naming ``f_star`` here cannot become reading it.
    """
    path = _APP_ROOT / "api" / "kelly_wording.py"
    tree = ast.parse(path.read_text(encoding="utf-8"))
    imported = {
        node.module or ""
        for node in ast.walk(tree)
        if isinstance(node, ast.ImportFrom)
    } | {
        alias.name
        for node in ast.walk(tree)
        if isinstance(node, ast.Import)
        for alias in node.names
    }

    assert not any(name.startswith("app") for name in imported), sorted(imported)


def test_the_sentences_that_land_elsewhere_are_named_as_such() -> None:
    """Cap 5's five: (a-2) by 約束 36, the four (g) sentences by D-6.

    All five are attached in ``app/advice/limits.py`` -- the module that owns
    the "may this pair still be used" decision and is therefore the only one
    able to tell the four causes apart. They are *imported* from the wording
    module, never retyped, which is what keeps the approved inventory the one
    copy (落地條件 2); the next test proves the import is what happens.
    """
    assert wording.LANDS_ELSEWHERE == {
        "a-2",
        "g-1",
        "g-2",
        "g-3",
        "g-4",
        "g-overridden",
        "task-1",
        "task-2",
    }
    assert wording.LANDS_ELSEWHERE <= set(wording.RISK_CONFIRMED_WORDING)


def test_cap_5_imports_its_sentences_instead_of_retyping_them() -> None:
    """落地條件 2 守門:「全 repo 無第二份同語意字串」.

    A retyped copy in ``limits.py`` would pass every verbatim assertion in this
    file on the day it was written and drift silently afterwards, which is the
    failure mode the single-copy rule exists for. So the check is structural:
    the risk layer must *import* each of the five, and must contain none of
    them as a literal of its own.
    """
    source = (_BACKEND_ROOT / "app" / "advice" / "limits.py").read_text(encoding="utf-8")
    literals = set(_string_constants(_BACKEND_ROOT / "app" / "advice" / "limits.py"))

    for item in wording.LANDS_ELSEWHERE:
        approved = wording.RISK_CONFIRMED_WORDING[item]
        assert approved not in literals, f"({item}) 被重打在 limits.py，而非 import"
        # Its opening clause must not appear in any literal there either -- a
        # partial copy is still a second copy.
        opening = approved[:16]
        assert not any(opening in text for text in literals), item

    assert "from app.api.kelly_wording import" in source


# ---------------------------------------------------------------------------
# ② 未採用備案不得存在於 repo
# ---------------------------------------------------------------------------

#: Fragments that identify a draft the review rejected, plus the phrases
#: 落地條件 7 bans outright. Each is quoted from the ruling that struck it.
#:
#: The third element is the scan's scope. Most fragments are distinctive enough
#: to be banned across both shipped trees. A few are ordinary Chinese that only
#: became a problem in a Kelly sentence -- 「剛才」 is a recency claim this display
#: cannot keep, and is perfectly fine in the sync CLI's summary -- so those are
#: scanned over the Kelly surface only. The narrower scope is stated per entry
#: rather than by weakening the fragment, because a fragment shortened until it
#: stops firing is a guard that no longer guards.
REJECTED_LITERALS: tuple[tuple[str, str, str], ...] = (
    # 落地條件 7: probability-laundering around the f* interval.
    ("落地條件 7 禁用字面", "有 95% 的機率落在", "shipped"),
    ("落地條件 7 禁用字面", "信心水準", "shipped"),
    ("落地條件 7 禁用字面", "信賴區間", "shipped"),
    ("落地條件 7 禁用字面", "建議比例", "shipped"),
    ("落地條件 7 禁用字面", "最佳倉位", "shipped"),
    # (b) 完整版, first round: the clause that claimed K counts every request.
    ("(b) required 刪除", "只要你對這個標的送出過帶入請求就會被計入", "shipped"),
    # (c), first round: the partition the splitter does not guarantee, and the
    # universal claim the ADR contradicts.
    ("(c) required 修訂", "切成兩段", "shipped"),
    ("(c) required 修訂", "因此不存在", "shipped"),
    # (e), first round: both drafts were vetoed as statements contradicted by
    # kelly_allowed_weight, and the second round's備案 may not coexist with主案.
    ("(e) VETO 備案", "也不會把歷史頻率直接當成未來的機率使用", "shipped"),
    ("(e) VETO 主案", "無法畫上等號", "shipped"),
    ("(e) required 分母", "獲利回合佔全部回合的比例", "shipped"),
    # (5-1), second round: the narrower failure the draft claimed.
    ("(5-1) 刪「樣本外」三字", "沒有產出可用的樣本外結果", "shipped"),
    # (5-3), first round: the engineer words the ruling struck from the pair.
    ("(5-3) 缺值不得渲染", "勝率或賠率為 null", "shipped"),
    ("(5-3) 賠率→盈虧比", "賠率 {payoff_ratio}", "shipped"),
    # (e-manual), third round: the adopted draft had 「剛才」 struck, because the
    # row may be ageing or expired by the time it is displayed, and the
    # alternative carried the same fault plus a phrase implying the limitation
    # is being worked on.
    ("(e-manual) required 刪「剛才」", "剛才", "kelly"),
    ("(e-manual) 備案不採用", "剛剛", "kelly"),
    ("(e-manual) 備案不採用", "尚未解決", "shipped"),
    # 3-B, third round: the alternative borrowed 元件 B's shape for a path that
    # is not a refusal.
    ("(3-B) 備案不採用", "同樣已經被系統記錄", "shipped"),
    # 500 訊息, fourth round (落地條件 29). The universal claim that both bounds
    # are non-finite, and the object that was named wrongly, are both banned
    # outright so a revert cannot pass as a tidy-up.
    ("(500) required 修訂「都不是」", "上界與下界都不是", "shipped"),
    ("(500) required 修訂受詞", "這次沒有數值被寫入", "shipped"),
    ("(500) 出現非有限值（舊稿）", "出現非有限值", "shipped"),
    # 裁決要點 6: neither a retry instruction nor a claim that a retry is
    # pointless may reach code. Scoped to the Kelly surface -- 「請重試」 is
    # ordinary copy elsewhere, and it is this sentence the ruling is about.
    ("(500) 重試句不予採用", "重試無用", "shipped"),
    ("(500) 重試句不予採用", "重試不會有幫助", "shipped"),
    ("(500) 重試句不予採用", "如持續發生可回報", "shipped"),
    ("(500) 重試句不予採用", "重試", "kelly"),
)

#: Everything that can carry a Kelly sentence today. ``LimitsCheckList.tsx`` is
#: on it because cap 5's details land there; the Kelly input section itself does
#: not exist yet (K4b) and is picked up by the glob when it does.
KELLY_SURFACE = (
    "backend/app/kelly",
    "backend/app/api/kelly.py",
    "backend/app/api/kelly_wording.py",
    "frontend/app/position/[symbol]/LimitsCheckList.tsx",
)


def _python_sources() -> list[Path]:
    return sorted(_APP_ROOT.rglob("*.py"))


def _frontend_sources(include_tests: bool = True) -> list[Path]:
    found = [
        path
        for pattern in ("*.ts", "*.tsx")
        for path in _FRONTEND_APP_ROOT.rglob(pattern)
        if "node_modules" not in path.parts
    ]
    if not include_tests:
        found = [path for path in found if "__tests__" not in path.parts]
    return sorted(found)


def _shipped_sources() -> list[Path]:
    return [*_python_sources(), *_frontend_sources()]


def _kelly_surface_sources() -> list[Path]:
    return [
        path
        for path in _shipped_sources()
        if str(path.relative_to(_STOCK_DESK_ROOT)).startswith(KELLY_SURFACE)
    ]


@pytest.mark.parametrize(("ruling", "literal", "scope"), REJECTED_LITERALS)
def test_a_rejected_draft_survives_nowhere_in_the_shipped_source(
    ruling: str, literal: str, scope: str
) -> None:
    """落地條件 17:「未採用備案不得存在於 repo」.

    Comments count: a vetoed sentence parked in one is a copy-paste away from a
    screen, and the reason it was vetoed does not weaken because it is not
    currently rendered.
    """
    scanned = _shipped_sources() if scope == "shipped" else _kelly_surface_sources()
    offenders = [
        str(path.relative_to(_STOCK_DESK_ROOT))
        for path in scanned
        if literal in path.read_text(encoding="utf-8")
    ]
    assert offenders == [], f"{ruling}：「{literal}」不得存在於出貨原始碼，出現於 {offenders}"


def test_the_rejected_literal_scan_actually_reads_the_files_it_claims_to() -> None:
    """A scan over an empty file list would pass every assertion above."""
    assert len(_python_sources()) > 50
    assert len(_frontend_sources()) > 20
    surface = {str(path.relative_to(_STOCK_DESK_ROOT)) for path in _kelly_surface_sources()}
    assert "backend/app/api/kelly_wording.py" in surface
    assert "backend/app/kelly/sample_gate.py" in surface
    assert "frontend/app/position/[symbol]/LimitsCheckList.tsx" in surface


@pytest.mark.parametrize("item", sorted(CONFIRMED_VERBATIM))
def test_an_approved_opening_is_never_followed_by_an_unapproved_remainder(
    item: str,
) -> None:
    """The generic form of the 備案 guard, for drafts whose text is not quoted.

    (f)'s dash variant and (d-1)'s alternatives were not adopted, and the review
    records the ruling without reprinting them, so there is no literal to ban.
    What can be checked is the property they would violate: every string the
    backend ships that *starts* one of these sentences must contain the whole
    approved sentence. A variant that shares an opening and diverges later fails
    here even though nobody wrote its text down.
    """
    approved = CONFIRMED_VERBATIM[item]
    opening = approved[:24]
    for path in _python_sources():
        for value in _string_constants(path):
            if opening in value:
                assert approved in value, (
                    f"{path.relative_to(_STOCK_DESK_ROOT)} 以 ({item}) 的開頭起句，"
                    "但後續字面與逐字定稿不符（未採用版本或漂移）。"
                )


def _string_constants(path: Path) -> list[str]:
    """Every string literal in ``path``, f-string fragments and docstrings included.

    Reading the parsed constants rather than the raw text is what makes the
    scans below survive implicit concatenation: a sentence written across six
    source lines is one value here and six partial lines to a text search.
    """
    tree = ast.parse(path.read_text(encoding="utf-8"))
    return [
        node.value
        for node in ast.walk(tree)
        if isinstance(node, ast.Constant) and isinstance(node.value, str)
    ]


# ---------------------------------------------------------------------------
# ③ 勝率白名單（分歧① required 1-4 / 落地條件 10）
# ---------------------------------------------------------------------------

WIN_RATE_TERM = "勝率"

#: 分歧① required 3: the exact set of backend modules allowed to contain the
#: word in a string, with the count each is allowed. One more anywhere and this
#: goes red, which is the whole mechanism -- the front end's banned-term list
#: cannot see the backend, so this is the only place the sprawl is stopped.
#:
#: Counts are over *string literals* (f-string fragments included), not raw
#: text: a doc comment explaining why a term is restricted is not an occurrence
#: of the term in copy.
WIN_RATE_BACKEND_WHITELIST: dict[str, int] = {
    # 分歧① 明列: cap 5's detail head, the one place the measured win rate is
    # printed. The not-evaluable line that used to be the second occurrence here
    # is now (g-1), imported from the wording module rather than written out
    # (K4b), and the `:g` false precision beside the win rate is closed too
    # (分歧① required 5).
    "app/advice/limits.py": 1,
    # 分歧① 明列: the gate's (5-3) refusal.
    "app/kelly/sample_gate.py": 1,
    # 分歧① 明列「Kelly 揭露常數模組」: (e), (f 完整), (g-1), plus (e-manual) from
    # the third round, which names the field on the hand-keyed branch, plus the
    # 第六輪 (任務 1) f*<=0 sentence, which opens by naming the two inputs it
    # computed from.
    #
    # 落地條件 48（第六輪 2026-08-22，擴充權在風控）allocated that fifth occurrence
    # to ``limits.py``, on the assumption it would be written there. It is
    # imported from here instead, which is the same rule 落地條件 2 applies to
    # every other approved sentence and the reason (g-1) left ``limits.py`` in
    # this lane: one copy, in the inventory, or the verbatim guard is guarding a
    # duplicate. The count moved module, not total -- reported to
    # risk-compliance for confirmation with the lane.
    "app/api/kelly_wording.py": 5,
    # 分歧① 列管（不擋本批，另批復審）: CONFIDENCE_MEANING / WEIGHT_MEANING, both
    # of which use the word inside a denial ("非勝率或機率").
    "app/advice/engine.py": 2,
    # 第五輪微批 required 1-D（落地條件 32）: 白名單第五項 = models.py 的 win_rate
    # 訊息。Approved on the same ground as (g-1) -- the word names the input
    # field being rejected, not a measured quantity. **清單擴充權保留於風控**:
    # a sixth entry is a risk-compliance decision, never a dev one.
    "app/kelly/models.py": 1,
}


def test_only_the_whitelisted_backend_modules_write_the_word() -> None:
    """分歧① required 3:「集合相等斷言允許清單，多一處即紅燈」."""
    observed = {
        str(path.relative_to(_BACKEND_ROOT)): count
        for path in _python_sources()
        if (count := sum(WIN_RATE_TERM in value for value in _string_constants(path)))
    }
    assert observed == WIN_RATE_BACKEND_WHITELIST, (
        "後端「勝率」白名單漂移。新增一處即須回 risk-compliance-officer 核可"
        f"（分歧① required 3）。實測：{observed}"
    )


#: 分歧① required 2: the front end renders backend sentences verbatim and writes
#: none of its own, so the Kelly surface must contain the word zero times. The
#: two entries here are the only non-Kelly occurrences that exist today and both
#: are outside this batch: the banned-term list itself (which required 1 orders
#: kept) and the backtest report's own metric row label. Any third occurrence is
#: a Kelly sentence leaking into the front end.
WIN_RATE_FRONTEND_INVENTORY: dict[str, int] = {
    "lib/adviceWording.ts": 1,
    "backtest/BacktestReportView.tsx": 1,
}


def test_the_front_end_writes_no_kelly_copy_of_its_own() -> None:
    """分歧① required 2, as an inventory: nothing may join these two."""
    observed = {
        str(path.relative_to(_FRONTEND_APP_ROOT)): count
        for path in _frontend_sources(include_tests=False)
        if (count := path.read_text(encoding="utf-8").count(WIN_RATE_TERM))
    }
    assert observed == WIN_RATE_FRONTEND_INVENTORY, (
        "前端出現新的「勝率」字面。Kelly 文案一律由後端常數產出、前端逐字渲染"
        f"（分歧① required 2）。實測：{observed}"
    )


def test_no_approved_kelly_sentence_has_been_copied_into_the_front_end() -> None:
    """落地條件 2 守門:「全 repo 無第二份同語意字串、前端無對應中文字面」."""
    sources = {
        str(path.relative_to(_FRONTEND_APP_ROOT)): path.read_text(encoding="utf-8")
        for path in _frontend_sources()
    }
    for item, approved in CONFIRMED_VERBATIM.items():
        # The opening clause is enough: a front end that hard-coded the sentence
        # would carry it whole, and a truncated copy is itself a violation of
        # 約束 21 (逐字渲染，禁改寫/截斷).
        opening = approved[:16]
        offenders = [name for name, text in sources.items() if opening in text]
        assert offenders == [], f"({item}) 的字面出現在前端 {offenders}"


def test_the_shared_forbidden_term_list_was_not_touched() -> None:
    """分歧① required 1:「也不得加入 shared/forbidden-terms.json」."""
    payload = json.loads(_SHARED_FORBIDDEN_TERMS.read_text(encoding="utf-8"))
    terms = [term for key, values in payload.items() if key != "_meta" for term in values]
    assert WIN_RATE_TERM not in terms
    assert sorted(payload) == ["_meta", "guarantee", "price_target"]


def test_the_front_end_banned_term_stays_banned() -> None:
    """分歧① required 1:「不得刪前端禁詞『勝率』」.

    The whitelist is backend-only *because* the front-end guard still refuses
    the word: deleting it there would turn every future Kelly sentence typed
    into a component into a silent pass.
    """
    source = (_FRONTEND_APP_ROOT / "lib" / "adviceWording.ts").read_text(encoding="utf-8")
    assert f'"{WIN_RATE_TERM}",' in source


# ---------------------------------------------------------------------------
# ④ 佔位符（落地條件 9 / 16, 6-A）
# ---------------------------------------------------------------------------

_PLACEHOLDER = re.compile(r"\{([a-z_]+)\}")

#: Exactly the placeholders each sentence is allowed to carry. An extra one is a
#: value the review never agreed to show; a missing one is usually a literal
#: written in its place.
EXPECTED_PLACEHOLDERS: dict[str, set[str]] = {
    "a-1": {"f_star_ci_low_pct", "f_star_ci_high_pct"},
    "a-2": set(),
    "b-full": {"k_observed", "k_distinct_specs"},
    "b-single": set(),
    "c": set(),
    "e": set(),
    "e-manual": set(),
    "f-full": set(),
    "f-tooltip": set(),
    "d-1-a": set(),
    "d-1-b": set(),
    "3-b": set(),
    "h": set(),
    "g-1": set(),
    "g-2": {"anchored_on", "age_days", "days"},
    "g-3": {"anchored_on", "age_days", "days"},
    "g-4": set(),
    "g-overridden": {"anchored_on", "age_days", "days"},
    "5-1": {"status"},
    "5-2": {"path_symbol", "path_market", "body_symbol", "body_market"},
    "5-3": set(),
    "500-non-finite": set(),
    # Both of the sixth round's two interpolate nothing. The only numbers in
    # them ("0%", "0", "第 5 條") are fixed facts of the branch they appear on,
    # not measurements: the allowance really is zero there, by construction.
    "task-1": set(),
    "task-2": set(),
}

#: The (g) sentences that name an anchor date and an elapsed count. All three
#: carry 6-A's plain-date rule and 落地條件 9's interpolated window; the two
#: unanchorable ones ((g-4) and its overridden cell) are absent because they
#: state outright that no anchor exists.
FRESHNESS_SENTENCES = ("g-2", "g-3", "g-overridden")


@pytest.mark.parametrize("item", sorted(CONFIRMED_VERBATIM))
def test_each_sentence_carries_exactly_its_approved_placeholders(item: str) -> None:
    assert set(_PLACEHOLDER.findall(SHIPPED[item])) == EXPECTED_PLACEHOLDERS[item]


@pytest.mark.parametrize("item", FRESHNESS_SENTENCES)
def test_the_freshness_window_is_never_written_as_a_number(item: str) -> None:
    """落地條件 9:「{days} 常數插值，禁硬寫；測試斷言無裸數字」.

    No digit at all may appear in these two: the window (30 today) is the one a
    literal would freeze, and the age and the anchor are per-row values.
    """
    sentence = SHIPPED[item]
    assert "{days}" in sentence and "{age_days}" in sentence
    assert not any(char.isdigit() for char in sentence), (
        f"({item}) 句中出現裸數字；門檻與日期一律走佔位符。"
    )


@pytest.mark.parametrize("item", FRESHNESS_SENTENCES)
def test_the_anchor_renders_as_a_plain_date(item: str) -> None:
    """6-A/落地條件 16:「{anchored_on} 必須純日期（YYYY-MM-DD）」.

    The backtest anchor's time of day is padded on, so an ISO datetime there
    would be precision the measurement never had.
    """
    assert "{anchored_on}" in SHIPPED[item]
    rendered = SHIPPED[item].format(anchored_on="2026-07-01", age_days=52, days=30)

    assert "2026-07-01" in rendered
    assert "T" not in rendered
    assert re.search(r"\d{2}:\d{2}", rendered) is None
    assert re.search(r"[+-]\d{2}:\d{2}$", rendered) is None
    assert "Z" not in rendered


@pytest.mark.parametrize("item", FRESHNESS_SENTENCES)
def test_the_plain_date_assertion_has_teeth(item: str) -> None:
    """The same check, fed the ISO datetime 6-A forbids, must fail."""
    rendered = SHIPPED[item].format(
        anchored_on="2026-07-01T00:00:00+08:00", age_days=52, days=30
    )

    assert "T" in rendered and re.search(r"\d{2}:\d{2}", rendered) is not None


# ---------------------------------------------------------------------------
# ⑤ 三則 422 訊息結構凍結（5-4，required）
# ---------------------------------------------------------------------------

REFUSAL_MESSAGES = ("5-1", "5-2", "5-3")

#: The engineer words 5-3 struck, plus the term the batch replaced with 盈虧比.
#: None of them may reappear in any refusal the endpoint can return.
FORBIDDEN_IN_A_REFUSAL = ("None", "null", "賠率")


@pytest.mark.parametrize("item", REFUSAL_MESSAGES)
def test_a_refusal_message_is_one_sentence(item: str) -> None:
    """5-4:「單句涵蓋」，升格 required；結構變更即整句失效須重送。"""
    sentence = SHIPPED[item]
    assert sentence.endswith("。")
    assert sentence.count("。") == 1


@pytest.mark.parametrize("item", REFUSAL_MESSAGES)
def test_a_refusal_message_embeds_no_measured_value(item: str) -> None:
    """5-4:「不嵌值」. Identifiers the user recognises are not measured values."""
    sentence = SHIPPED[item]
    for term in FORBIDDEN_IN_A_REFUSAL:
        assert term not in sentence
    assert set(_PLACEHOLDER.findall(sentence)) <= {
        "status",
        "path_symbol",
        "path_market",
        "body_symbol",
        "body_market",
    }


def test_the_range_messages_in_models_use_the_replacement_term() -> None:
    """第五輪微批 required 1-B（落地條件 30）: models.py 兩則訊息「賠率」零出現.

    The batch's scan covers the wording module and the gate; these two live in
    ``app/kelly/models.py`` and were outside it, which the ruling called a 留門.
    Both are user-facing (the PUT body's range refusals), so the replaced term
    has to be gone from them too -- and the assertion is on the constants
    themselves, not on the file, so a copy elsewhere in the module cannot
    satisfy it.
    """
    for message in (
        models.KELLY_WIN_RATE_OUT_OF_RANGE_MESSAGE,
        models.KELLY_PAYOFF_RATIO_OUT_OF_RANGE_MESSAGE,
    ):
        assert "賠率" not in message
    assert "盈虧比" in models.KELLY_PAYOFF_RATIO_OUT_OF_RANGE_MESSAGE
    # required 1-A: the guard's banned list keeps the word. It is the
    # anti-regression fixture, not a literal awaiting the same substitution.
    assert "賠率" in FORBIDDEN_IN_A_REFUSAL


def test_the_range_messages_echo_only_a_number_the_user_could_have_sent() -> None:
    """落地條件 31: ``{value}`` may not render ``nan`` / ``inf`` into the sentence.

    風控 kept the echo itself (a user's own number is what they need to correct
    the entry) and asked for the non-finite cases to be closed without inventing
    copy. ``allow_inf_nan=False`` does that: the value never reaches the range
    check, so it never reaches the sentence, and the refusal is pydantic's
    ordinary type error instead.
    """
    for value in (float("nan"), float("inf"), float("-inf")):
        for field in ("win_rate", "payoff_ratio"):
            payload: dict[str, float] = {"win_rate": 0.55, "payoff_ratio": 1.8}
            payload[field] = value
            with pytest.raises(ValidationError) as caught:
                models.KellyManualInput(**payload)
            rendered = str(caught.value)
            assert models.KELLY_WIN_RATE_OUT_OF_RANGE_MESSAGE[:8] not in rendered
            assert models.KELLY_PAYOFF_RATIO_OUT_OF_RANGE_MESSAGE[:8] not in rendered

    # A finite out-of-range value still gets the approved sentence, echo included.
    with pytest.raises(ValidationError) as caught:
        models.KellyManualInput(win_rate=1.2, payoff_ratio=1.8)
    assert "勝率必須大於 0 且小於 1" in str(caught.value)


def test_the_status_code_sits_in_brackets_at_the_very_end() -> None:
    """5-4:「代碼句尾括號」. A code mid-sentence reads as part of the explanation."""
    assert SHIPPED["5-1"].endswith("（狀態代碼：{status}）。")


def test_the_pair_refusal_interpolates_nothing_at_all() -> None:
    """5-3A: the ``.format()`` call went with the placeholders it fed.

    Leaving the call in place would have been the open door: the sentence names
    no value today, and a re-added argument would have rendered silently.
    """
    assert "{" not in sample_gate.PB_NONE_MESSAGE
    review = sample_gate.review_estimates(None, None)
    assert review.rejection == CONFIRMED_VERBATIM["5-3"]


@pytest.mark.parametrize("code", sorted(SAMPLE_SIZE_VERBATIM))
def test_a_sample_size_refusal_keeps_the_same_shape(code: str) -> None:
    """The three untouched ones share 5-4's structure; they state their numbers."""
    sentence = SHIPPED_SAMPLE_SIZE[code]
    assert sentence.endswith("。")
    assert sentence.count("。") == 1
    assert set(_PLACEHOLDER.findall(sentence)) == {"count", "threshold"}


# ---------------------------------------------------------------------------
# The 500 path's message (qa non-blocking, 2026-08-19)
# ---------------------------------------------------------------------------


#: 落地條件 26's own list, plus the two 落地條件 7 phrases that a re-draft of this
#: sentence would be most likely to reach for. Checked against the constant
#: itself rather than the file, so a doc comment explaining the ruling does not
#: count as a violation of it.
BANNED_IN_THE_NON_FINITE_MESSAGE = (
    "信賴區間",
    "信心水準",
    "拒絕",
    "失敗",
    "錯誤",
    "建議比例",
    # required 修訂 1: 「都不是」 was a universal claim, and the reachable case is
    # one-sided. Listed by 條件 26 as a regression guard, not a style preference.
    "都不是",
)


def test_the_non_finite_interval_message_is_the_approved_one() -> None:
    """落地條件 25/26: 逐字，含標點，並釘住被改掉的那三個字。

    Also structural: nothing is interpolated. On this branch a bound is
    non-finite by construction, so the old ``.format()`` rendered ``inf`` /
    ``-inf`` / ``nan`` into the sentence -- the same fault 5-3 struck at the root
    in PB_NONE by deleting the call rather than guarding it.
    """
    message = KELLY_NON_FINITE_INTERVAL_MESSAGE

    assert message == CONFIRMED_VERBATIM["500-non-finite"]
    assert "{" not in message and "}" not in message
    assert not any(char.isdigit() for char in message)
    for term in BANNED_IN_THE_NON_FINITE_MESSAGE:
        assert term not in message, f"落地條件 26：「{term}」不得出現於本句。"
    for bound in ("inf", "-inf", "nan", "None", "null"):
        assert bound not in message


def test_the_non_finite_message_names_the_object_that_was_not_written() -> None:
    """required 修訂 2: the attempt row *is* written; the Kelly input is not.

    "沒有數值被寫入" was struck as false -- ``_append_attempt`` stores the measured
    columns on this path before the 500 is raised. The sentence names the
    ``KellyInputRow`` instead, which really is what did not land.
    """
    assert KELLY_NON_FINITE_INTERVAL_MESSAGE.endswith("這次沒有寫入 Kelly 輸入。")
    assert "至少有一端不是有限的數字" in KELLY_NON_FINITE_INTERVAL_MESSAGE


def test_the_non_finite_message_gives_no_advice_in_either_direction() -> None:
    """裁決要點 6: no retry instruction, and no claim that a retry is pointless.

    Reproducibility holds only for the same spec over the same bars, and bars
    are refetched, so "trying again will not help" is a claim about a future run
    this code cannot support. It may live in the review record and nowhere else.
    """
    message = KELLY_NON_FINITE_INTERVAL_MESSAGE
    for advice in ("重試", "再試", "請稍後", "可回報", "請聯繫", "請重新"):
        assert advice not in message


def test_the_non_finite_path_still_logs_the_bounds_it_does_not_show() -> None:
    """落地條件 28: the raw ``low``/``high`` stay in ``logger.error``.

    Taking them out of the sentence is only acceptable because they are still
    somewhere -- this is the one record of what the bootstrap actually produced.
    """
    source = (_APP_ROOT / "api" / "kelly.py").read_text(encoding="utf-8")
    call = source[source.index("kelly import produced a non-finite") :]
    head = call[: call.index(")")]

    assert "fraction.low" in head and "fraction.high" in head


def test_the_non_finite_path_gets_its_own_sentence_and_not_the_refusal_one() -> None:
    """落地條件 23, reverse assertion: (d-1 元件 B) 字面不得出現於此路徑.

    The attempt this path logs is ``outcome="ok"`` with no reason code -- every
    gate passed and the storage step failed -- so the refusal sentence would
    misstate the row. 3-B is the sentence for it, and it contains no word for
    refusal at all.
    """
    approved = wording.KELLY_NON_FINITE_ATTEMPT_LOGGED

    assert "拒絕" not in approved
    assert "失敗" not in approved and "錯誤" not in approved
    assert wording.KELLY_REFUSAL_ATTEMPT_LOGGED not in approved
    assert approved != wording.KELLY_REFUSAL_ATTEMPT_LOGGED
    # 修訂 required: 「這次」 may not be trimmed -- an already stored row is
    # untouched by this failure, and dropping it reads as "never written".
    assert approved.endswith("這筆輸入，這次沒有被寫入。")

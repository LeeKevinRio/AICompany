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
from fastapi.testclient import TestClient
from pydantic import ValidationError

from app.api import kelly_wording as wording
from app.api.kelly import KELLY_NON_FINITE_INTERVAL_MESSAGE
from app.kelly import models, sample_gate
from app.main import app

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
    # 第十一輪（2026-08-22）條件 96：(b) 的第三格，採主案刪除級修訂。
    "b-unlogged": (
        "此標的目前查無回測帶入嘗試紀錄（K_observed）——"
        "這是紀錄本身的缺席，不是查到了一個計數的結果；"
        "因此無法呈現選擇偏誤揭露所依據的計數。"
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
    # 第八輪（2026-08-22，第七批）。組三主案：(g-4) 的來源括號插入「，已手動調整」。
    "g-4-overridden": (
        "此標的的 Kelly 輸入（來源：回測帶入，已手動調整）缺少樣本外區段結束日，"
        "本系統無法判定其新鮮度，一律視為已過期，本條上限暫不評估；"
        "請重新執行回測並確認後更新。"
    ),
    # 第八輪組一：四共用元素。
    "e1": "這次回測的報酬計算不含持有期間股利。",
    "e2": "本系統未計算除權息還原後，這裡顯示的勝率與盈虧比會是什麼；方向不明。",
    "e3": "此為回測帶入當下記錄的狀態，顯示時本系統依當時記錄呈現。",
    "e3-never-synced": (
        "此為回測帶入當下記錄的狀態，顯示時本系統依當時記錄呈現（含是否已完成同步）。"
    ),
    "e4": (
        "以上『方向不明』的判斷，僅限於這筆 Kelly 輸入所依據的這次回測算出的完整回合統計"
        "——也就是這裡的勝率與盈虧比。"
    ),
    # 第八輪組一：五則機制事實句。
    "div-disabled": (
        "這筆 Kelly 輸入所依據的回測，回測帶入當時依請求關閉了除權息還原"
        "（adjust_dividends=false）。"
    ),
    "div-never-synced": (
        "這筆 Kelly 輸入所依據的回測，回測帶入當時本機尚未同步過任何除權息資料"
        "（尚未執行 uv run python -m app.dividends.sync）。"
    ),
    "div-no-events-tw": (
        "這筆 Kelly 輸入所依據的回測未進行除權息還原：本機雖有除權息資料，"
        "但這段期間內查無本商品的除權息紀錄。"
        "可能是這段期間確實沒有配息，也可能是資料涵蓋範圍有限"
        "（目前只涵蓋台股上市，不含上櫃），本系統無法判斷是哪一種情況。"
    ),
    "div-no-events-non-tw": (
        "這筆 Kelly 輸入所依據的回測未進行除權息還原：本系統的除權息資料目前只涵蓋台股上市，"
        "不涵蓋這個市場，因此不是『查無配息』，而是『沒有資料可查』。"
    ),
    "div-unusable-events": (
        "這筆 Kelly 輸入所依據的回測未進行除權息還原：查到本商品在此區間的除權息紀錄，"
        "但欄位不足以推算調整因子，已整筆略過而非用推估值代替。"
    ),
    "div-unusable-events-tail": (
        "若日後同步除權息資料後這筆紀錄的欄位轉為可用，仍須重新執行回測並重新帶入，"
        "這裡顯示的這筆 Kelly 輸入才會更新；"
        "如需協助排查，也可回報此代號與區間供人工覆核來源欄位。"
    ),
    # 第八輪組二：任務 7 採備案原文、任務 8 標籤。
    # (任務 8) 第十三輪撤銷：不再是定稿，改列於 REJECTED_LITERALS 零出現守門。
    "task-7": (
        "這裡顯示的勝率與盈虧比，是這筆 Kelly 輸入回測帶入當時、由系統算出的原始值。"
        "這筆輸入後來被你手動調整；但調整的是這筆輸入的生效內容，"
        "這兩個數字本身不曾被覆蓋，仍是原樣保留下來的原始值。"
        "本條上限的計算，用的是目前生效值，不是這裡顯示的原始值；"
        "目前生效的 Kelly 輸入，用的也不是這裡這兩個數字。"
    ),
    # 第六輪（2026-08-22，第五批）display copy, landed by K4c-1. 任務 3's frame,
    # its eleven column labels, 欄位 10's sentence, FR-6's four, the FR-4 badge
    # and the Kelly-side 口徑限定語 -- all retyped from the ruling.
    "task-3": (
        "以下是這筆 Kelly 輸入所依據的回測樣本明細，"
        "供你核對各句所指的『這段歷史樣本』實際是哪一次回測、哪一段期間。"
    ),
    "fr5-1": "策略",
    "fr5-2": "樣本外（OOS）區段（起訖日期）",
    "fr5-3": "完整回合數",
    "fr5-4": "獲利回合數",
    "fr5-5": "虧損回合數",
    "fr5-6": "跨界排除回合數",
    "fr5-7": "期末未平倉回合數",
    "fr5-8": "樣本觀測數（資料點數，非回合數）",
    "fr5-9": "勝率的 95% 區間（Wilson，依完整回合計）",
    "fr5-10": "費率查證狀態",
    "fr5-11": "除權息還原狀態",
    "fr5-10-note": (
        "此標的 Kelly 輸入所依據的回測，其手續費／交易稅／滑價率尚未對照主要來源查證，"
        "這筆勝率與盈虧比應視為待查證狀態。"
    ),
    "fr6-manual": "此標的目前生效的 Kelly 輸入，來源為手動輸入。",
    "fr6-manual-label": "來源：手動輸入。",
    "fr6-overridden": (
        "此標的目前生效的 Kelly 輸入，原本由回測帶入，之後經你手動調整；"
        "調整後的數字才是目前生效值，原始回測帶入的數字仍保留、可以查看。"
    ),
    "fr6-overridden-label": "來源：回測帶入，已手動調整；原始回測值仍保留可查。",
    # 第十輪（2026-08-22）風控直接定稿：第三格來源句與標籤。
    "fr6-backtest": "此標的目前生效的 Kelly 輸入，來源為回測帶入。",
    "fr6-backtest-label": "來源：回測帶入。",
    # 第十輪 條件 86: the payoff ratio's label, whose single definition is in
    # ``app/kelly/models.py`` -- the range refusal is built from it, so the two
    # cannot drift. Retyped here from the ruling like every other item.
    "payoff-label": "盈虧比（平均獲利 ÷ 平均虧損）",
    "badge-absent": "尚未輸入",
    "badge-fresh": "已更新",
    "badge-ageing": "建議更新",
    "badge-expired": "已過期",
    "task-6-kelly": "勝率（依完整回合計）",
    # 第九輪（2026-08-22，第八批）：覆蓋前告知，採備案（依來源拆兩變體）。
    "notice-title": "帶入回測結果 — 執行前請確認",
    "notice-manual-1": (
        "這裡目前生效的勝率與盈虧比，是你自行輸入的估計值；"
        "執行後，本系統會重新執行一次回測，把這個標的目前生效的勝率與盈虧比，"
        "換成這次算出的新結果。"
    ),
    "notice-manual-2": (
        "你自行輸入的這組數字，執行後就不再是生效值。"
        "本系統沒有版本紀錄，這組數字不會留在任何欄位，事後也沒有畫面可以找回。"
    ),
    "notice-overridden-1": (
        "這裡目前生效的勝率與盈虧比，是你在原本回測帶入的基礎上手動調整過的數字，"
        "另外還保留著一組原始回測值供你查看；"
        "執行後，本系統會重新執行一次回測，把這個標的目前生效的勝率與盈虧比，"
        "換成這次算出的新結果。"
    ),
    "notice-overridden-2": (
        "你調整過的這組生效值、以及原本保留的那組原始回測值，執行後都會被這次的新結果取代。"
        "本系統沒有版本紀錄，這兩組舊數字都不會留在這一列的任何欄位，事後也沒有畫面可以找回。"
    ),
    "notice-choices": (
        "點『取消』，這個標的的 Kelly 輸入維持現在的樣子，不會有任何改變；"
        "點『確認帶入，覆蓋目前資料』，才會執行前面所說的動作。"
    ),
    "notice-cancel": "取消",
    "notice-confirm": "確認帶入，覆蓋目前資料",
    # 第十二輪（2026-08-22）條件 102：開啟對話框的觸發按鈕標籤，風控直接定稿。
    "trigger-label": "執行回測並帶入",
    # 第十五輪（2026-08-22）：刪除確認組（第十批主案四段零修訂＋overridden 段一
    # 變體＋兩鍵），以及原始值檢視的兩個控制項。
    "delete-title": "刪除 Kelly 輸入 — 執行前請確認",
    "delete-1": (
        "這個動作會把 {symbol}（{market}）的 Kelly 輸入這一列整列刪除："
        "這一列目前存著的每一個欄位值——包含生效中的勝率與盈虧比在內——都會一併移除。"
    ),
    "delete-1-overridden": (
        "這個動作會把 {symbol}（{market}）的 Kelly 輸入這一列整列刪除："
        "這一列目前存著的每一個欄位值——"
        "包含你調整過的這組生效值、以及原本保留的那組原始回測值在內——都會一併移除。"
    ),
    "delete-2": "本系統沒有版本紀錄，事後也沒有畫面可以找回被刪除的這一列。",
    "delete-3": (
        "刪除的範圍也只有這一列：不論此標的先前是否曾嘗試回測帶入，"
        "嘗試紀錄與其累計計數（K_observed）都不在刪除範圍內，"
        "不會因這次刪除而有任何改變。"
        "刪除後，這個標的回到尚未輸入的狀態，"
        "第 5 條「分數 Kelly 部位上限」隨之回到無法評估；"
        "之後仍可透過手動輸入或回測帶入取得新的一組數字，"
        "但那會是新的輸入，不是找回這次刪除的內容。"
    ),
    "delete-4": (
        "點『取消』，這個標的的 Kelly 輸入維持現在的樣子，不會有任何改變；"
        "點『確認刪除，移除目前資料』，才會執行前面所說的動作。"
    ),
    "delete-confirm": "確認刪除，移除目前資料",
    # 第九輪的取消鍵，第十五輪一併核可用於本對話框；同一字面單一定義。
    "delete-cancel": "取消",
    "original-entry": "查看原始回測值",
    "original-back": "返回",
}

#: Where each id is shipped from. Three modules: the refusal messages belong
#: beside the gate that decides to emit them, and 落地條件 25 names the 500 body's
#: constant by module and line, so it stays where the ruling put it.
SHIPPED: dict[str, str] = {
    **{item: text for item, text in wording.RISK_CONFIRMED_WORDING.items()},
    "payoff-label": models.KELLY_PAYOFF_RATIO_LABEL,
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
    """Everything the backend carries, through the ninth round.

    A sentence is listed here when the backend carries it, so the number tracks
    the repo rather than the review's running total (46 + 1 沿用 after the ninth
    round). The two counts differ on purpose and in one direction only: this one
    is finer. FR-5's eleven column labels are one line of the ruling and eleven
    entries here, FR-6's two pairs are two rulings and four entries, and the
    badge is one追認 and four entries -- each is separately retyped, so a drift
    in one label cannot hide behind its neighbours.

    Landed by K4c-1 and previously the named gap: 任務 3's frame and its eleven
    labels, 欄位 10, FR-6's four, the FR-4 badge, the Kelly-side 口徑限定語, and
    the ninth round's before-overwrite dialog (八 entries: title, two paragraphs
    per source variant, the shared close, and the two button labels).

    The eleventh round's own addition is (b)'s third cell (條件 96), which the
    tenth round had left with no sentence at all; the twelfth added the import
    trigger's label (條件 102); the fifteenth added the delete dialog (title,
    four paragraphs, its overridden 段一 variant, and its confirm key, with the
    ninth round's cancel key carried under a second id) and the two controls the
    original-values view is reached and left by (條件 116).

    One item left in the other direction: (任務 8)'s period label was **revoked**
    in the thirteenth round once 條件 92 took the period off the view it labelled,
    so it is not counted here and its literal is on the zero-occurrence guard
    instead. That is why this total moves by one less than the review's.

    The tenth round closed two gaps this lane reported and both are here:
    (fr6-backtest) with its label (條件 84), and the payoff ratio's label
    (條件 86), which ships from ``app/kelly/models.py`` because that is where its
    single definition is -- the range refusal is composed from it.

    The 口徑限定語's front-end twin (「勝率（依結算筆數計）」 on
    ``BacktestReportView``) is **not** here and is not a backend constant: 條件
    49 pairs the two on a display surface, and the front end owns that half.

    Three of the ids ship from ``app/kelly/sample_gate.py`` and one is the 500
    body, counted here and defined elsewhere.
    """
    assert len(CONFIRMED_VERBATIM) == 82
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
        "g-4-overridden",
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
    # 第九輪 條件 71. The dialog's rejected drafts: the single-sentence主案 (whose
    # identifying fragment is its parenthesised hedge), the two button labels
    # that were not adopted, and the title qualifier struck as a description of
    # an action this system does not perform (條件 78 bans it from the trigger
    # label too). The 方向 (ii) one-liner for the ``backtest`` cell has no quoted
    # text to scan for; it is pinned instead by the four-cell test below, which
    # asserts that cell produces nothing at all.
    ("(告知句) 主案不採用「（若有）」", "（若有）", "kelly"),
    ("(告知句) 按鈕備案否決", "仍要帶入並覆蓋", "shipped"),
    ("(告知句) 按鈕不採用", "取消，保留目前資料", "shipped"),
    ("(告知句) required 刪標題限定語", "最近一次", "kelly"),
    # 第十輪 條件 89: the four that keep the Kelly-copy-surface scan, because no
    # legitimate occurrence of any of them exists. 「最近一次」 above covers its
    # longer form as a prefix, and both are listed so the ruling reads straight.
    ("(告知句) 條件 89 全檔", "最近一次回測結果", "kelly"),
    ("(告知句) 條件 89 全檔", "原始回測值不受影響", "kelly"),
    ("(告知句) 條件 89 全檔", "原始值不會被覆蓋", "kelly"),
    # 第十二輪 條件 104: the second refused trigger candidate. The first
    # (「帶入回測結果」) is a substring of the approved dialog title, so it takes an
    # allowlist rather than a zero scan -- see TRIGGER_LABEL_ALLOWLIST.
    ("(觸發標籤) 候選 (b) 不採用", "重新執行回測並帶入", "shipped"),
    # 第十一輪 條件 100: the 條件 96 沿 drafts that were not adopted -- the備案
    # exposing the storage table, and the五字 phrase the修訂 struck, which said
    # the counts are missing *on this page* and so implied they exist elsewhere.
    # 第十三輪: (任務 8) 的定稿被撤銷（選項二後無承載面），字面就此併入零出現守門。
    # 撤銷不同於未採用：它曾是定稿，所以理由與出處記在這裡，字面則一視同仁。
    ("(任務 8) 第十三輪撤銷", "原始回測的樣本外期間", "shipped"),
    ("(條件 96) 備案不採用", "這張表本身是空的", "shipped"),
    ("(條件 96) required 刪除", "本頁在這裡，", "shipped"),
    ("(條件 96) 備案不採用", "本頁因此無法在這裡", "shipped"),
    # 第十輪 條件 86: the payoff-ratio label draft that was refused --「依…計」
    # hung on a ratio reads as a ratio of round-trip counts, which overstates
    # the edge.
    ("(盈虧比標籤) 不採用", "盈虧比（依完整回合計）", "shipped"),
)

#: 第八輪 條件 61, six literals banned from the 欄位 11 block.
#:
#: Scoped to that block rather than to whole files, because each of the six is
#: legitimate elsewhere and the ruling is about these sentences:
#:
#: * 低估／高估 -- the seventh round's VETO. Restoring dividends re-runs the bars,
#:   so the round set changes and the direction of the move in the pair is not
#:   established; "低估" also happens to point at revising one's own numbers
#:   upward, on a screen carrying an override field. The already-approved (b)
#:   sentence uses both words about ``K_observed``, where the direction *is*
#:   established, and the backtester's own notes use 「會低估」 about a return
#:   series, whose direction is determinate (條件 62).
#: * 本頁／未提供比較／不做比較 -- required 2. Layout claims of the kind 「上方」 and
#:   「策略欄」 were struck for, and denials of disclosures the product does make
#:   (a Buy & Hold comparison and ``DIVIDEND_BIAS_SCOPE_NOTE`` both exist).
#: * 尚未涵蓋上櫃 -- required 4: "尚未" promises coverage on the vendor's behalf.
FIELD_11_FORBIDDEN: tuple[tuple[str, str], ...] = (
    ("required 方向單向陳述", "低估"),
    ("required 方向單向陳述", "高估"),
    ("required 版面指涉", "本頁"),
    ("required 否認既有揭露", "未提供比較"),
    ("required 否認既有揭露", "不做比較"),
    ("required 前瞻宣稱", "尚未涵蓋上櫃"),
)

#: Every 欄位 11 message the module can produce, by ``(reason_code, market)``.
#: ``no_events`` is the one code whose text depends on the market.
FIELD_11_CASES: tuple[tuple[str, str], ...] = (
    ("disabled", "TW"),
    ("never_synced", "TW"),
    ("no_events", "TW"),
    ("no_events", "US"),
    ("unusable_events", "TW"),
)

#: Everything that can carry a Kelly sentence today, as path prefixes. This is a
#: **static tuple and picks nothing up on its own** -- an earlier note here said
#: a glob would cover the Kelly input surface "when it exists", which was simply
#: wrong: :func:`_kelly_surface_sources` filters by these prefixes, so a file not
#: named below is a file the ``kelly``-scoped rejected-literal scan never opens.
#: K4c-2 added four components and one helper, and they are listed (qa
#: 2026-08-22, non-blocking 1). ``LimitsCheckList.tsx`` is here because cap 5's
#: details land there.
#:
#: The rule for adding one: any file that renders, forwards or holds Kelly copy.
#: ``test_the_rejected_literal_scan_actually_reads_the_files_it_claims_to``
#: asserts the front-end members resolve, so a rename cannot silently empty this
#: list.
KELLY_SURFACE = (
    "backend/app/kelly",
    "backend/app/api/kelly.py",
    "backend/app/api/kelly_wording.py",
    "frontend/app/position/[symbol]/LimitsCheckList.tsx",
    "frontend/app/settings/KellyInputsSection.tsx",
    "frontend/app/settings/KellyDisclosuresPanel.tsx",
    "frontend/app/settings/KellyImportDialog.tsx",
    "frontend/app/settings/KellyManualInputForm.tsx",
    "frontend/app/lib/kellyFieldError.ts",
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


# ---------------------------------------------------------------------------
# 欄位 11 組裝（第八輪 條件 59/60/63/69）
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(("reason_code", "market"), FIELD_11_CASES)
def test_each_field_11_message_follows_the_approved_paragraph_order(
    reason_code: str, market: str
) -> None:
    """條件 59: 機制事實 → E1 → E2 → E3 → E4，段序屬定稿一部分."""
    block = wording.kelly_dividend_note(reason_code, market=market)
    assert block is not None

    facts = {
        ("disabled", "TW"): wording.KELLY_DIVIDEND_DISABLED_FACT,
        ("never_synced", "TW"): wording.KELLY_DIVIDEND_NEVER_SYNCED_FACT,
        ("no_events", "TW"): wording.KELLY_DIVIDEND_NO_EVENTS_TW_FACT,
        ("no_events", "US"): wording.KELLY_DIVIDEND_NO_EVENTS_NON_TW_FACT,
        ("unusable_events", "TW"): wording.KELLY_DIVIDEND_UNUSABLE_EVENTS_FACT,
    }
    state = (
        wording.KELLY_DIVIDEND_STATE_AS_RECORDED_NEVER_SYNCED
        if reason_code == "never_synced"
        else wording.KELLY_DIVIDEND_STATE_AS_RECORDED
    )
    ordered = [
        facts[(reason_code, market)],
        wording.KELLY_DIVIDEND_NO_DIVIDEND_IN_RETURNS,
        wording.KELLY_DIVIDEND_DIRECTION_UNKNOWN,
        state,
        wording.KELLY_DIVIDEND_DIRECTION_SCOPE,
    ]

    assert block.startswith(ordered[0])
    positions = [block.index(part) for part in ordered]
    assert positions == sorted(positions), "段序與定稿不符"


@pytest.mark.parametrize(("reason_code", "market"), FIELD_11_CASES)
def test_every_field_11_message_carries_e1_and_e4(reason_code: str, market: str) -> None:
    """條件 63: E1 五則皆須含，缺一 BLOCKING；條件 60: E4 逐字附加於五則."""
    block = wording.kelly_dividend_note(reason_code, market=market)
    assert block is not None

    assert wording.KELLY_DIVIDEND_NO_DIVIDEND_IN_RETURNS in block
    assert wording.KELLY_DIVIDEND_DIRECTION_UNKNOWN in block
    assert wording.KELLY_DIVIDEND_DIRECTION_SCOPE in block


def test_the_shared_elements_are_one_constant_each_not_five_copies() -> None:
    """條件 60: 單一共用常數，五則逐字附加.

    Asserted structurally: each shared element appears exactly once as a string
    literal in the module. Five hand-copied versions would satisfy every text
    assertion above on the day they were written and drift apart afterwards --
    which is the whole reason the ruling asks for one constant.
    """
    literals = _string_constants(_APP_ROOT / "api" / "kelly_wording.py")
    for element in (
        wording.KELLY_DIVIDEND_NO_DIVIDEND_IN_RETURNS,
        wording.KELLY_DIVIDEND_DIRECTION_UNKNOWN,
        wording.KELLY_DIVIDEND_STATE_AS_RECORDED,
        wording.KELLY_DIVIDEND_DIRECTION_SCOPE,
    ):
        assert sum(element in value for value in literals) == 1, element


def test_the_never_synced_state_sentence_keeps_its_parenthesis() -> None:
    """條件 69: 「（含是否已完成同步）」不得刪.

    The code is written once at import and only read afterwards, so a user who
    has since run the sync would otherwise read this line as current.
    """
    block = wording.kelly_dividend_note("never_synced", market="TW")
    assert block is not None
    assert "（含是否已完成同步）" in block
    assert wording.KELLY_DIVIDEND_STATE_AS_RECORDED_NEVER_SYNCED in block

    # And no other branch borrows it.
    for reason_code, market in FIELD_11_CASES:
        if reason_code == "never_synced":
            continue
        other = wording.kelly_dividend_note(reason_code, market=market)
        assert other is not None and "（含是否已完成同步）" not in other


def test_only_the_unusable_branch_carries_the_tail() -> None:
    """The tail is that branch's own: it describes a record that may become usable."""
    for reason_code, market in FIELD_11_CASES:
        block = wording.kelly_dividend_note(reason_code, market=market)
        assert block is not None
        carries = wording.KELLY_DIVIDEND_UNUSABLE_EVENTS_TAIL in block
        assert carries is (reason_code == "unusable_events"), reason_code
        if carries:
            assert block.endswith(wording.KELLY_DIVIDEND_UNUSABLE_EVENTS_TAIL)


def test_no_block_is_produced_for_a_restored_or_unknown_run() -> None:
    """``adjusted`` keeps its own approved note; an unknown code invents nothing."""
    assert wording.kelly_dividend_note("adjusted", market="TW") is None
    assert wording.kelly_dividend_note("something_new", market="TW") is None


@pytest.mark.parametrize(("ruling", "literal"), FIELD_11_FORBIDDEN)
@pytest.mark.parametrize(("reason_code", "market"), FIELD_11_CASES)
def test_no_field_11_message_carries_a_struck_literal(
    reason_code: str, market: str, ruling: str, literal: str
) -> None:
    """條件 61: the six reverse literals, over every assembled message."""
    block = wording.kelly_dividend_note(reason_code, market=market)
    assert block is not None
    assert literal not in block, f"({reason_code}/{market}) {ruling}：「{literal}」"


def test_the_kelly_dividend_notes_are_this_module_s_own(
) -> None:
    """條件 62: backtest.py's constants are neither imported nor spliced in.

    The two families describe the same mechanism to different readers, and the
    backtester's carry a scope qualifier naming a screen column that does not
    exist here plus a determinate direction the seventh round vetoed for
    round-trip statistics. This module importing anything at all is already
    banned; this states the specific consequence.
    """
    backtest_source = (_APP_ROOT / "api" / "backtest.py").read_text(encoding="utf-8")
    assert "DIVIDEND_BIAS_SCOPE_NOTE" in backtest_source  # unchanged and still theirs

    for reason_code, market in FIELD_11_CASES:
        block = wording.kelly_dividend_note(reason_code, market=market)
        assert block is not None
        # Not a substring of the backtester's own notes, and not built from them.
        assert block not in backtest_source


def test_the_rejected_literal_scan_actually_reads_the_files_it_claims_to() -> None:
    """A scan over an empty file list would pass every assertion above."""
    assert len(_python_sources()) > 50
    assert len(_frontend_sources()) > 20
    surface = {str(path.relative_to(_STOCK_DESK_ROOT)) for path in _kelly_surface_sources()}
    assert "backend/app/api/kelly_wording.py" in surface
    assert "backend/app/kelly/sample_gate.py" in surface
    # Every front-end member must resolve to a file that exists: the prefixes are
    # static, so a renamed component would otherwise drop out of the scan in
    # silence and take its scope's guards with it.
    front_end = tuple(entry for entry in KELLY_SURFACE if entry.startswith("frontend/"))
    assert len(front_end) == 6
    for entry in front_end:
        assert (_STOCK_DESK_ROOT / entry).is_file(), entry
        assert entry in surface, entry


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

    Some approved sentences legitimately share an opening -- (g-overridden) and
    (g-4-overridden) differ only after their common source parenthesis, by the
    eighth round's own design -- so a value satisfies this if it carries **any**
    approved sentence starting that way. That is the property the guard is
    after: what may not exist is a string that opens like an approved sentence
    and then matches none of them.

    A value that **is** an approved sentence passes on that ground alone, and
    that exemption is load-bearing rather than a convenience: the fifteenth
    round built the delete dialog's overridden paragraph by quoting the import
    dialog's naming phrase verbatim, on purpose, so one approved sentence now
    opens inside another. It is not an unapproved remainder -- it went through
    the review whole.
    """
    approved = CONFIRMED_VERBATIM[item]
    opening = approved[:24]
    siblings = [text for text in CONFIRMED_VERBATIM.values() if text.startswith(opening)]
    assert approved in siblings
    every_approved = set(CONFIRMED_VERBATIM.values())
    for path in _python_sources():
        for value in _string_constants(path):
            if opening in value and value not in every_approved:
                assert any(sibling in value for sibling in siblings), (
                    f"{path.relative_to(_STOCK_DESK_ROOT)} 以 ({item}) 的開頭起句，"
                    "但後續字面與任一逐字定稿皆不符（未採用版本或漂移）。"
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


def test_no_constant_name_leaks_into_the_copy_it_names() -> None:
    """條件 99: 常數識別字不得出現於任何面向使用者輸出.

    Naming a constant after the state it describes is a convenience for readers
    of the source; a user meeting ``KELLY_SELECTION_BIAS_UNLOGGED`` on a screen
    would be meeting an engineer's word for their own data. The naming bound the
    ruling set is asserted alongside: nothing in this family may be called
    "no bias", "corrected" or "none", because each of those says the disclosure
    was settled rather than that a record is missing.
    """
    names = [
        name
        for module in (wording, models, sample_gate)
        for name in vars(module)
        if name.isupper() and not name.startswith("_")
    ]
    # Every string this surface can put in front of a user: the approved
    # inventory, the two modules that ship copy of their own (qa 2026-08-22
    # non-blocking 3 widened the scan to these), and the two assembly points'
    # finished output.
    shipped = [
        *wording.RISK_CONFIRMED_WORDING.values(),
        models.KELLY_WIN_RATE_OUT_OF_RANGE_MESSAGE,
        models.KELLY_PAYOFF_RATIO_OUT_OF_RANGE_MESSAGE,
        models.KELLY_PAYOFF_RATIO_LABEL,
        sample_gate.INSUFFICIENT_DATA_MESSAGE,
        sample_gate.SYMBOL_MISMATCH_MESSAGE,
        sample_gate.PB_NONE_MESSAGE,
        sample_gate.LOW_ROUND_TRIPS_MESSAGE,
        sample_gate.LOW_WIN_TRIPS_MESSAGE,
        sample_gate.LOW_LOSS_TRIPS_MESSAGE,
        KELLY_NON_FINITE_INTERVAL_MESSAGE,
        *(
            block
            for reason_code, market in FIELD_11_CASES
            if (block := wording.kelly_dividend_note(reason_code, market=market))
        ),
        *(
            paragraph
            for source in ("manual", "backtest_overridden")
            if (body := wording.kelly_overwrite_notice(source)) is not None
            for paragraph in body
        ),
    ]
    for approved in shipped:
        for name in names:
            assert name not in approved, name

    # The naming bound is 條件 99's own and is about **this family**: the (b)
    # cells. ``PB_NONE_MESSAGE`` keeps its name -- it is called after the
    # ``pb_none`` reason code, and that code is not a claim that a disclosure
    # came out clean.
    family = {
        name
        for name, value in vars(wording).items()
        if name.isupper()
        and isinstance(value, str)
        and value in set(SELECTION_BIAS_FAMILY.values())
    }
    assert family == {
        "KELLY_SELECTION_BIAS_FULL",
        "KELLY_SELECTION_BIAS_SINGLE",
        "KELLY_SELECTION_BIAS_UNLOGGED",
    }
    for name in family:
        assert not any(
            banned in name for banned in ("_NO_BIAS", "_CORRECTED", "_NONE")
        ), name


#: (b)'s three cells, by the review's own ids. 條件 98's fourth cell has no
#: sentence by ruling, so it has no entry here.
SELECTION_BIAS_FAMILY: dict[str, str] = {
    item: text
    for item, text in wording.RISK_CONFIRMED_WORDING.items()
    if item.startswith("b-")
}


def test_the_selection_bias_family_is_three_cells_and_this_is_the_third() -> None:
    """條件 96/99: 字面清冊補第三筆——(b) 完整／短／查無紀錄."""
    assert set(SELECTION_BIAS_FAMILY) == {"b-full", "b-single", "b-unlogged"}


#: 條件 104. 「帶入回測結果」 was refused as a *button* label -- it reads as
#: fetching a run this system does not keep -- but it is also the opening of the
#: dialog title the ninth round approved, where the co-text ("— 執行前請確認")
#: rules the fetch reading out. So the guard is an allowlist of exactly one
#: occurrence, at its 出處, and a second one anywhere is a red light.
TRIGGER_LABEL_ALLOWLIST: tuple[tuple[str, str, str], ...] = (
    (
        "app/api/kelly_wording.py",
        'KELLY_OVERWRITE_NOTICE_TITLE = "帶入回測結果 — 執行前請確認"',
        "第九輪 對話框標題定稿（條件 72：aria-label 逐字同用）",
    ),
)


def test_the_refused_trigger_label_survives_only_at_its_one_approved_source() -> None:
    """條件 104: 未採用版本零出現，標題出處顯式 allowlist 一筆，第二處紅燈."""
    observed = tuple(
        (str(path.relative_to(_APP_ROOT.parent)), line.strip())
        for path in _kelly_surface_sources()
        if path.suffix == ".py"
        for line in path.read_text(encoding="utf-8").splitlines()
        if "帶入回測結果" in line
    )

    assert observed == tuple((entry[0], entry[1]) for entry in TRIGGER_LABEL_ALLOWLIST), (
        f"「帶入回測結果」出現於核可出處以外（條件 104）。實測：{observed}"
    )


def test_the_trigger_label_is_the_approved_one_and_neither_candidate() -> None:
    """條件 104, from the other side: what the constant is, not only what it is not."""
    assert wording.KELLY_IMPORT_BACKTEST_TRIGGER_LABEL == "執行回測並帶入"
    assert "帶入回測結果" not in wording.KELLY_IMPORT_BACKTEST_TRIGGER_LABEL
    assert "重新" not in wording.KELLY_IMPORT_BACKTEST_TRIGGER_LABEL
    # 條件 102: the trigger is defined next to the dialog it opens, and is not
    # one of the dialog's own strings.
    assert wording.KELLY_IMPORT_BACKTEST_TRIGGER_LABEL not in (
        wording.KELLY_OVERWRITE_NOTICE_TITLE,
        wording.KELLY_OVERWRITE_CONFIRM_LABEL,
        wording.KELLY_OVERWRITE_CANCEL_LABEL,
        wording.KELLY_OVERWRITE_NOTICE_CHOICES,
    )


#: 條件 111 零出現守門的 allowlist，粒度同本檔其他 allowlist（檔案＋字面＋出處）。
#: 只剩一類：``PositionsTable`` 的持倉刪除 confirm 早於本批、不在 Kelly 面，
#: 第十五輪明示**不追溯**。
#:
#: 曾經還有一類「待清除」——``KellyManualInputForm`` 的 ``window.confirm`` 整句
#: （條件 112）與 ``KellyDisclosuresPanel`` 的兩個英文按鈕（條件 116）。前端已於
#: e3dbe83 落地兩者，所以那三筆連同 :data:`ENGLISH_VIEW_CONTROL_ALLOWLIST`
#: 一併刪除，英文按鈕改為真正的零出現斷言。留痕於此，因為「暫記 allowlist、
#: 對方落地即刪」是這批的作法，不是被遺忘的例外。
FORBIDDEN_DELETE_WORDING_ALLOWLIST: tuple[tuple[str, str, str], ...] = (
    (
        "frontend/app/components/PositionsTable.tsx",
        "此動作無法復原",
        "第十五輪 條件 111：持倉刪除 confirm 早於本批、非 Kelly 面，明示不追溯",
    ),
    (
        "frontend/app/components/PositionsTable.tsx",
        "確定刪除",
        "第十五輪 條件 111：同上一筆同一行",
    ),
    (
        "frontend/app/position/[symbol]/LeverageChapterView.tsx",
        "歸零",
        "既有無關用法（:158「理想路徑…已跌破 -100%（歸零）」）：受詞是部位淨值，"
        "本輪裁決的受詞是已經為零的計數，兩者不同命題",
    ),
    (
        "backend/app/playbook/engine.py",
        "歸零",
        "既有無關用法（順延計數歸零）：受詞是排程順延計數，非 K_observed",
    ),
)


#: 條件 111 的五則禁字。全出貨面掃描，誤傷以上面那張 allowlist 逐筆記名——
#: 這是 條件 89 立下的作法：字面若在別處有正當用途，就記出處而不是縮小掃描面，
#: 因為縮小掃描面等於把「別處」永久豁免掉。
#:
#: 各自被刪的理由不同：全稱不實宣稱（對嘗試紀錄為假）、問句式把疑懼內建進按鈕
#: 語境、不顧勸阻框架、定指主詞預設紀錄存在（對零嘗試標的憑空宣稱）、以及對
#: 本來就是零的計數講「歸零」語意空轉。
STRUCK_DELETE_WORDING: tuple[str, ...] = (
    "此動作無法復原",
    "確定刪除",
    "仍要刪除",
    "嘗試紀錄仍會保留",
    "歸零",
)


@pytest.mark.parametrize("literal", STRUCK_DELETE_WORDING)
def test_a_struck_delete_wording_survives_only_where_the_review_allowed(
    literal: str,
) -> None:
    """條件 111 零出現，allowlist 逐筆出處以外一律紅燈.

    「取消，保留目前資料」 is not in this list because it is already banned
    outright by the ninth round's own entry in :data:`REJECTED_LITERALS`.
    """
    observed = {
        str(path.relative_to(_STOCK_DESK_ROOT))
        for path in _shipped_sources()
        if literal in path.read_text(encoding="utf-8")
    }
    allowed = {
        entry[0] for entry in FORBIDDEN_DELETE_WORDING_ALLOWLIST if entry[1] == literal
    }

    assert observed == allowed, (
        f"「{literal}」出現於核可出處以外（條件 111）。實測：{observed}"
    )


@pytest.mark.parametrize("literal", ["Original values", "Back"])
def test_no_english_control_carries_the_original_values_view(literal: str) -> None:
    """條件 116 零出現: the two placeholders are gone, and may not come back.

    E-5's language floor is the reason this is a guard rather than a preference:
    the only control that keeps (fr6-overridden)'s Traditional-Chinese promise
    ("原始回測帶入的數字仍保留、可以查看") may not itself be English. Both labels
    are backend constants now, and the front end renders them verbatim.

    Matched as a **rendered label**, not a substring: "Back" lives inside
    ``Backend``, ``BacktestForm`` and half the module names in this app, and
    none of those is a control anybody reads. A JSX text node sits alone on its
    line.
    """
    observed = {
        str(path.relative_to(_STOCK_DESK_ROOT))
        for path in _frontend_sources(include_tests=False)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip() == literal
    }

    assert observed == set(), f"「{literal}」仍作為控制項字面存在（條件 116）。實測：{observed}"


def test_every_allowlisted_line_still_exists() -> None:
    """A stale exemption is an exemption granted to nobody.

    The list is checked against the files, so a line that was removed -- by a
    rewrite of that component, say -- cannot leave a permission behind for a
    literal nobody writes any more.
    """
    for name, literal, _ in FORBIDDEN_DELETE_WORDING_ALLOWLIST:
        path = _STOCK_DESK_ROOT / name
        assert path.is_file(), name
        assert literal in path.read_text(encoding="utf-8"), (name, literal)

    # Every entry is 不追溯 and outside the Kelly surface. A Kelly file appearing
    # here would mean the ruling was reinterpreted, not that a guard was tuned.
    for name, _, _ in FORBIDDEN_DELETE_WORDING_ALLOWLIST:
        assert not name.startswith(KELLY_SURFACE), name


def test_the_delete_dialog_ships_no_alternative_third_paragraph() -> None:
    """條件 111: 備案段三（只留範圍句、不講第 5 條後果）不得落地.

    The shorter variant was offered so risk-compliance could choose between an
    even-handed statement and a minimal one; it chose the first, and the second
    may not exist in the source. What identifies it is the absence of the
    aftermath clause from a paragraph that otherwise opens the same way.
    """
    approved = wording.KELLY_DELETE_NOTICE_SCOPE_AND_AFTERMATH
    opening = approved[:20]

    for path in _python_sources():
        for value in _string_constants(path):
            if opening in value:
                assert approved in value, path.relative_to(_STOCK_DESK_ROOT)

    assert "第 5 條「分數 Kelly 部位上限」隨之回到無法評估" in approved
    assert "不是找回這次刪除的內容" in approved


def test_the_assembly_point_imports_its_sentences_instead_of_retyping_them() -> None:
    """條件 56:「import 端不得出現第二份中文字面（反向斷言）」.

    ``app/api/kelly.py`` is the display supply as well as the assembly point
    (D-8), so it is the module most able to end up with a convenience copy of a
    sentence. Every approved item it serves must arrive by import; a literal of
    its own would pass the verbatim guard on the day it was written and drift
    quietly afterwards.
    """
    path = _APP_ROOT / "api" / "kelly.py"
    literals = set(_string_constants(path))

    for item, approved in wording.RISK_CONFIRMED_WORDING.items():
        assert approved not in literals, f"({item}) 被重打在 kelly.py，而非 import"

    assert "from app.api.kelly_wording import" in path.read_text(encoding="utf-8")


# ---------------------------------------------------------------------------
# 覆蓋前告知組裝（第九輪 條件 71-83）
# ---------------------------------------------------------------------------

#: 條件 73's four cells as this module can see them. The fourth ("no row at
#: all") belongs to the API and is asserted in ``tests/test_api_kelly_
#: disclosures.py``; here the ``backtest`` cell stands for the ruling that a
#: measurement replacing a measurement gets **no** dialog -- explicitly, not by
#: falling off the end of a lookup.
OVERWRITE_NOTICE_VARIANTS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("manual", ("notice-manual-1", "notice-manual-2", "notice-choices")),
    (
        "backtest_overridden",
        ("notice-overridden-1", "notice-overridden-2", "notice-choices"),
    ),
)

#: 條件 89 (第十輪): 條件 77's seven literals, split by scope. Four of them exist
#: nowhere legitimately and keep the Kelly-copy-surface scan -- they are in
#: :data:`REJECTED_LITERALS` above with scope ``kelly``. The three below are
#: narrowed to the **assembled dialog**, each because a wider scan has a real
#: collateral hit, and the review accepted the narrowing on that evidence:
#:
#: * 上方 -- struck from (任務 2) as a layout claim, but 「上方」 is ordinary copy
#:   elsewhere in the product and this ruling is about this dialog.
#: * 下方 -- struck from 段三 for the same reason, same collateral.
#: * 原始回測值仍保留 -- a **substring of the sixth round's own approved**
#:   (fr6-overridden) label, which ships and must keep saying it. A repo-wide
#:   reading would therefore fail against approved copy; what the round decided
#:   is that the *dialog* may not claim the original values survive a re-import,
#:   because for this row they do not.
OVERWRITE_NOTICE_FORBIDDEN: tuple[tuple[str, str], ...] = (
    ("條件 77/89 版面指涉", "下方"),
    ("條件 77/89 版面指涉", "上方"),
    ("條件 77/89 保留範圍不實", "原始回測值仍保留"),
)


@pytest.mark.parametrize(("source", "items"), OVERWRITE_NOTICE_VARIANTS)
def test_the_overwrite_dialog_follows_the_approved_paragraph_order(
    source: str, items: tuple[str, ...]
) -> None:
    """條件 82/93: 段序屬定稿，且三段分開交付，不得連成單一字串.

    The order is asserted paragraph by paragraph rather than over a joined
    string, which is what 條件 93 changed: joining them buries 段二 -- the
    paragraph naming what the user loses -- inside a block.
    """
    body = wording.kelly_overwrite_notice(source)

    assert body == tuple(CONFIRMED_VERBATIM[item] for item in items)
    assert not isinstance(body, str)


def test_the_shared_close_is_one_constant_appended_to_both_variants() -> None:
    """條件 82: one constant, not a sentence retyped into each variant."""
    close = wording.KELLY_OVERWRITE_NOTICE_CHOICES
    for source, _ in OVERWRITE_NOTICE_VARIANTS:
        body = wording.kelly_overwrite_notice(source)
        assert body is not None
        assert body[-1] == close
        assert body.count(close) == 1
    literals = _string_constants(_APP_ROOT / "api" / "kelly_wording.py")
    assert literals.count(close) == 1


def test_the_overridden_source_label_still_says_the_original_values_are_kept() -> None:
    """條件 89 追加正向斷言: the narrowed literal is *required* copy elsewhere.

    The dialog may not claim the original values survive a re-import; the
    (fr6-overridden) label must go on saying they are kept, because until that
    re-import happens they are. Pinning both directions is what stops the
    narrowed scan from being read as "this phrase is banned".
    """
    assert wording.KELLY_SOURCE_OVERRIDDEN_LABEL == (
        "來源：回測帶入，已手動調整；原始回測值仍保留可查。"
    )
    assert "原始回測值仍保留" in wording.KELLY_SOURCE_OVERRIDDEN_LABEL


def test_the_backtest_cell_of_the_dialog_is_an_explicit_no() -> None:
    """條件 73:「backtest 格須顯式分支+正向斷言不顯示，禁 default 落空」.

    Re-importing over an imported row replaces a measurement with a measurement:
    nothing hand-keyed is lost, and it is the very action (g-3)/(g-4) tell the
    user to take, so a warning there would point the opposite way to the
    product's own instruction. The lightweight one-line variant drafted for this
    cell was not adopted and is not in the module (條件 71) -- the positive
    assertion is that this cell produces nothing at all.
    """
    assert wording.kelly_overwrite_notice("backtest") is None
    source = (_APP_ROOT / "api" / "kelly_wording.py").read_text(encoding="utf-8")
    assert 'elif source == "backtest":' in source, "backtest 格不得由 default 落空"


def test_an_unknown_source_invents_no_dialog() -> None:
    assert wording.kelly_overwrite_notice("something_new") is None


def test_the_overwrite_dialog_shows_no_measured_value() -> None:
    """條件 75: 常數無 ``{}``、渲染無數字.

    A win rate or payoff ratio on this dialog would drag (e-manual), (f) and the
    whole style floor of 落地條件 4 onto a modal, which is a separate submission.
    Digits are checked on the rendered body rather than only the placeholders,
    because a literal number would evade the placeholder scan entirely.
    """
    rendered = [
        wording.KELLY_OVERWRITE_NOTICE_TITLE,
        wording.KELLY_OVERWRITE_CONFIRM_LABEL,
        wording.KELLY_OVERWRITE_CANCEL_LABEL,
    ]
    for source, _ in OVERWRITE_NOTICE_VARIANTS:
        body = wording.kelly_overwrite_notice(source)
        assert body is not None
        rendered.extend(body)
    for text in rendered:
        assert "{" not in text and "}" not in text, text
        assert not any(character.isdigit() for character in text), text


@pytest.mark.parametrize(("ruling", "literal"), OVERWRITE_NOTICE_FORBIDDEN)
def test_no_overwrite_dialog_text_carries_a_struck_literal(
    ruling: str, literal: str
) -> None:
    """條件 71/77, over every string this dialog can put on a screen."""
    rendered = [
        wording.KELLY_OVERWRITE_NOTICE_TITLE,
        wording.KELLY_OVERWRITE_CONFIRM_LABEL,
        wording.KELLY_OVERWRITE_CANCEL_LABEL,
        *(
            paragraph
            for source, _ in OVERWRITE_NOTICE_VARIANTS
            if (body := wording.kelly_overwrite_notice(source)) is not None
            for paragraph in body
        ),
    ]
    for text in rendered:
        assert literal not in text, f"{ruling}：「{literal}」"


def test_the_manual_variant_claims_no_more_than_the_manual_branch_can_keep() -> None:
    """措辭=行為 for the ninth round's own修訂 reason.

    The manual variant says the pair will be left in **no** field; the overridden
    one says the two sets will not be left in any field **of this row**. The
    difference is not stylistic: a hand-keyed pair never reaches
    ``kelly_import_attempts``, while an overridden row's original values were
    written there by the import that produced them and survive both the
    overwrite and a later ``DELETE`` (約束 35).
    """
    manual = wording.KELLY_OVERWRITE_NOTICE_MANUAL_LOSS
    overridden = wording.KELLY_OVERWRITE_NOTICE_OVERRIDDEN_LOSS
    assert "不會留在任何欄位" in manual
    assert "不會留在這一列的任何欄位" in overridden
    assert "不會留在任何欄位" not in overridden


#: 條件 83. 條件 61's six literals split in two: 低估／高估／本頁 stay scoped to the
#: assembled 欄位 11 messages (three false positives in this module's own
#: commentary are real), and these three keep the whole-file scan the ruling
#: preserved -- with the collateral damage listed explicitly, per
#: 「誤傷顯式 allowlist（檔案+來源行+出處）」. A fourth occurrence turns this red.
CONDITION_83_FULL_FILE_LITERALS: tuple[str, ...] = (
    "未提供比較",
    "不做比較",
    "尚未涵蓋上櫃",
)

CONDITION_83_ALLOWLIST: tuple[tuple[str, str, str], ...] = (
    (
        "app/api/kelly_wording.py",
        '#: draft\'s second clause ("其他計算基礎…本系統未提供比較"): the system *does*',
        "第八輪 required 2：E4 註記引用被刪的第二分句，說明為何現行字面不含它",
    ),
    (
        "app/api/kelly_wording.py",
        '#: "不含上櫃" and never "尚未涵蓋上櫃" (required 4): "尚未" would promise, on the',
        "第八輪 required 4：no_events(TW) 註記引用被改掉的字面，說明改字理由",
    ),
)


def test_the_full_file_literals_appear_only_where_the_review_allowed() -> None:
    """條件 83:「維持全檔掃描」+ 誤傷顯式 allowlist，第四處即紅燈."""
    path = _APP_ROOT / "api" / "kelly_wording.py"
    observed = tuple(
        (str(path.relative_to(_APP_ROOT.parent)), line.strip())
        for line in path.read_text(encoding="utf-8").splitlines()
        if any(literal in line for literal in CONDITION_83_FULL_FILE_LITERALS)
    )
    allowed = tuple((entry[0], entry[1]) for entry in CONDITION_83_ALLOWLIST)
    assert observed == allowed, (
        "kelly_wording 全檔掃描出現新的條件 61 字面（第四處即紅燈）。"
        f"實測：{observed}"
    )


def test_the_condition_83_allowlist_is_commentary_and_not_copy() -> None:
    """Each allowed occurrence is a doc comment, never a shipped string."""
    literals = _string_constants(_APP_ROOT / "api" / "kelly_wording.py")
    for _, line, _ in CONDITION_83_ALLOWLIST:
        assert line.startswith("#")
    for literal in CONDITION_83_FULL_FILE_LITERALS:
        assert not any(literal in value for value in literals), literal


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
    # computed from, plus the 第八輪 three: (E2), (E4) and (任務 7).
    #
    # 落地條件 48（第六輪，擴充權在風控）allocated (任務 1)'s occurrence to
    # ``limits.py``, on the assumption it would be written there. It is imported
    # from here instead, which is the same rule 落地條件 2 applies to every other
    # approved sentence and the reason (g-1) left ``limits.py`` in this lane: one
    # copy, in the inventory, or the verbatim guard is guarding a duplicate.
    #
    # 落地條件 64（第八輪）projected +6 for「欄位 11 五則+任務 7」. The realised
    # increase is +3, and the difference is 條件 60 rather than a missing
    # sentence: E2 and E4 are the only 欄位 11 elements containing the word, and
    # 條件 60 requires them to be **single shared constants appended to the five**
    # rather than retyped into each message. Counting at the definition site is
    # 條件 56's own rule, so five copies would themselves be the violation.
    # 第九輪 §dev 兩回送項 ① confirmed both reallocations (5 -> 8) and 條件 81
    # requires this note on the three shared-constant entries.
    #
    # K4c-1 takes it to 14, all of it already allocated by the reviews:
    # * 落地條件 48（第六輪，擴充權在風控）+3 -- 欄位 9's label, 欄位 10's sentence
    #   and the Kelly-side 口徑限定語, exactly the three that ruling names.
    # * 落地條件 79（第九輪）+2 -- 「限兩變體定義行」: the dialog's two 段一
    #   constants, one per source variant. Its 段二/段三 and both button labels
    #   contain the word nowhere, which is why the increase is two and not five.
    # * 第十五輪 +1 -- the delete dialog's base 段一, which names the two fields it
    #   is about to remove (「生效中的勝率與盈虧比」). Its overridden variant names
    #   the two value *sets* instead and contains the word nowhere, and the other
    #   three paragraphs and both keys do not either.
    "app/api/kelly_wording.py": 14,
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


#: Below this length an approved item is a **label**, not a sentence, and the
#: opening-clause scan below stops being evidence of anything: 「策略」 and 「取消」
#: are ordinary words that every screen in the product already contains, and
#: 條件 47 ① positively *requires* the four badge labels to be the ones
#: ``NetWorthSection`` already ships. The short ones are scanned over the Kelly
#: surface only, where a duplicate really would be a second copy of Kelly copy.
_LABEL_LENGTH = 16


def test_no_approved_kelly_sentence_has_been_copied_into_the_front_end() -> None:
    """落地條件 2 守門:「全 repo 無第二份同語意字串、前端無對應中文字面」."""
    sources = {
        str(path.relative_to(_FRONTEND_APP_ROOT)): path.read_text(encoding="utf-8")
        for path in _frontend_sources()
    }
    for item, approved in CONFIRMED_VERBATIM.items():
        if len(approved) < _LABEL_LENGTH:
            continue
        # The opening clause is enough: a front end that hard-coded the sentence
        # would carry it whole, and a truncated copy is itself a violation of
        # 約束 21 (逐字渲染，禁改寫/截斷).
        opening = approved[:_LABEL_LENGTH]
        offenders = [name for name, text in sources.items() if opening in text]
        assert offenders == [], f"({item}) 的字面出現在前端 {offenders}"


#: The one collateral hit of the short-label scan below, listed the way every
#: other narrowing in this file is (檔案+來源行+出處). 「策略」 is FR-5 欄位 1's
#: label *and* the ordinary word for the field a user picks a strategy in; the
#: occurrence below is the second, on the import spec form, whose chrome the
#: fourteenth round cleared as 同構 with the existing register and carrying no
#: methodological claim. A second occurrence, or one in any other file, is a red
#: light -- that would be the detail table's label being rebuilt in the client.
KELLY_LABEL_ALLOWLIST: tuple[tuple[str, str, str], ...] = (
    (
        "frontend/app/settings/KellyImportDialog.tsx",
        "策略",
        "第十四輪 chrome 放行：帶入設定表單的欄位標籤，非 FR-5 欄位 1 明細標籤",
    ),
)


def test_no_approved_kelly_label_has_been_copied_onto_the_kelly_surface() -> None:
    """The short items, over the surface that renders Kelly copy (落地條件 2/3).

    A label the backend supplies and the front end also spells out is exactly
    the drift 落地條件 3 exists to stop -- the copy would then have two homes and
    only one of them is under a verbatim guard. Scoping this to
    :data:`KELLY_SURFACE` is what lets 條件 47 ① stand at the same time: the four
    badge labels are *deliberately* the ones ``settings/NetWorthSection.tsx``
    already ships, and that file is not a Kelly surface.
    """
    sources = {
        str(path.relative_to(_STOCK_DESK_ROOT)): path.read_text(encoding="utf-8")
        for path in _kelly_surface_sources()
        if path.suffix in {".ts", ".tsx"}
    }
    allowed = {(entry[0], entry[1]) for entry in KELLY_LABEL_ALLOWLIST}
    for item, approved in CONFIRMED_VERBATIM.items():
        if len(approved) >= _LABEL_LENGTH:
            continue
        offenders = [
            name
            for name, text in sources.items()
            if approved in text and (name, approved) not in allowed
        ]
        assert offenders == [], f"({item}) 的標籤字面出現在 Kelly 前端面 {offenders}"

    # The allowlist is checked in both directions: an entry that stopped being
    # true (the field renamed, the file gone) must not sit here granting an
    # exemption nobody needs.
    for name, literal, _ in KELLY_LABEL_ALLOWLIST:
        text = (_STOCK_DESK_ROOT / name).read_text(encoding="utf-8")
        assert text.count(literal) == 1, (name, literal)
        assert 'htmlFor="kelly-import-strategy"' in text


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
    "b-unlogged": set(),
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
    # 第八輪. (g-4-overridden) has no anchor to interpolate (6-B), and組一/組二
    # interpolate nothing at all: every number in them is a fixed fact of the
    # branch, not a measurement.
    "g-4-overridden": set(),
    "e1": set(),
    "e2": set(),
    "e3": set(),
    "e3-never-synced": set(),
    "e4": set(),
    "div-disabled": set(),
    "div-never-synced": set(),
    "div-no-events-tw": set(),
    "div-no-events-non-tw": set(),
    "div-unusable-events": set(),
    "div-unusable-events-tail": set(),
    "task-7": set(),
    # 第六輪 display copy. Every value on the FR-5 detail is bound to its label
    # by the assembly point rather than interpolated into it, so none of the
    # eleven carries a placeholder -- a label with a hole in it would be a
    # sentence, and these were approved as labels.
    "task-3": set(),
    **{f"fr5-{index}": set() for index in range(1, 12)},
    "fr5-10-note": set(),
    "fr6-manual": set(),
    "fr6-manual-label": set(),
    "fr6-overridden": set(),
    "fr6-overridden-label": set(),
    "fr6-backtest": set(),
    "fr6-backtest-label": set(),
    "payoff-label": set(),
    "badge-absent": set(),
    "badge-fresh": set(),
    "badge-ageing": set(),
    "badge-expired": set(),
    "task-6-kelly": set(),
    # 第九輪 條件 75: the dialog interpolates nothing at all, because no measured
    # value may appear on it. An empty set here is the mechanical half of that
    # ruling; ``test_the_overwrite_dialog_shows_no_measured_value`` is the other.
    "notice-title": set(),
    "notice-manual-1": set(),
    "notice-manual-2": set(),
    "notice-overridden-1": set(),
    "notice-overridden-2": set(),
    "notice-choices": set(),
    "notice-cancel": set(),
    "notice-confirm": set(),
    "trigger-label": set(),
    # 條件 113: the delete block's only interpolation, and it is in 段一 alone.
    "delete-title": set(),
    "delete-1": {"symbol", "market"},
    "delete-1-overridden": {"symbol", "market"},
    "delete-2": set(),
    "delete-3": set(),
    "delete-4": set(),
    "delete-confirm": set(),
    "delete-cancel": set(),
    "original-entry": set(),
    "original-back": set(),
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


def test_a_range_refusal_reaches_the_client_as_the_approved_sentence_alone() -> None:
    """qa 2026-08-22 B2（條件 57）: 422 的 detail[].msg 逐字等於核可常數.

    pydantic v2 renders a ``ValueError`` raised inside a validator as
    ``"Value error, "`` + its text, and the front end renders ``detail[].msg``
    as it arrives -- so the shipped sentence was a hybrid: an English wrapper in
    front of copy approved character for character. Both validators now raise
    :class:`~pydantic_core.PydanticCustomError`, whose message is the constant
    and nothing else.

    Asserted through a real request rather than on the constants, because the
    fault was never in the constants: it was in what the framework did to them
    on the way out.
    """
    client = TestClient(app)
    cases = (
        ({"win_rate": 1.4, "payoff_ratio": 1.8}, models.KELLY_WIN_RATE_OUT_OF_RANGE_MESSAGE, 1.4),
        (
            {"win_rate": 0.55, "payoff_ratio": -1.0},
            models.KELLY_PAYOFF_RATIO_OUT_OF_RANGE_MESSAGE,
            -1.0,
        ),
    )

    for body, approved, value in cases:
        response = client.put("/api/kelly-inputs/2330", json=body)
        assert response.status_code == 422
        (error,) = response.json()["detail"]
        assert error["msg"] == approved.format(value=value)
        # No wrapper of any kind, in either language.
        assert "Value error" not in response.text
        # The branchable half moved to ``type``, which is where a client should
        # have been reading it all along.
        assert error["type"].startswith("kelly_")


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

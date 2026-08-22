"""Every Kelly disclosure sentence risk-compliance signed off, in one file.

Same role ``app/playbook/wording.py`` plays for the playbook: one artefact that
can be handed to risk-compliance whole, and no call site free to invent a
sentence of its own.

**Why this module sits in ``app/api`` and not in ``app/kelly``** (落地條件 2,
`work/reviews/2026-08-19-C5-Kelly-文案批審.md`): several of these sentences
describe what the *risk layer* does with the stored pair, so a copy living under
``app/kelly`` would either restate ``app/advice`` behaviour from a package that
must never reach it (約束 13/37, pinned by ``tests/test_kelly_boundary.py``) or
force that package to import it. The assembly point stays ``app/api/kelly.py``,
which is already the one module allowed to touch all three packages (D-8). This
module therefore imports **nothing** -- it is text and nothing else.

House rules, all of them non-negotiable:

* **逐字**. Every string below was approved character by character, punctuation
  included, on 2026-08-19 (第一輪 + 第二輪 + 第三輪). Re-wording, shortening, splitting a
  clause, swapping a dash for a comma or moving a sentence behind a tooltip
  makes the approval lapse: the changed sentence has to go back to
  risk-compliance before it ships. ``tests/test_kelly_wording.py`` pins each one
  by retyping it, so a drift fails the build rather than reaching a user.
* **No threshold is written as a literal**. The freshness window is
  ``{days}``, bound by the caller to the constant in force -- the same rule
  ``NET_WORTH_EXPIRED_DETAIL`` follows. ``{anchored_on}`` is a plain
  ``YYYY-MM-DD`` date and never an ISO datetime: the backtest anchor's time of
  day is padded, so showing it would be precision the measurement does not have
  (6-A).
* **No measured value is embedded in a refusal.** A missing number is described,
  never rendered (5-3): ``None`` and ``null`` are engineer words, and printing
  either beside a Chinese sentence reads as a value that was measured.
* **Not every constant here ships from here.** (a-2) is a ``limits.py``
  disclosure by 約束 36 (that layer only ever branches on a boolean); it is
  recorded here so the approved inventory is complete in one place, and lands
  in cap 5 in K4b. See its own comment.
* **Two approved sentences live outside this module**, by rulings that name
  their location: the three refusal messages are in ``app/kelly/sample_gate.py``
  beside the gate that emits them, and the non-finite-interval 500 body is
  ``app.api.kelly.KELLY_NON_FINITE_INTERVAL_MESSAGE`` (落地條件 25 names that
  constant and that line). ``tests/test_kelly_wording.py`` holds the inventory
  of all 21 in one place, so nothing is only half-tracked.

The item ids in :data:`RISK_CONFIRMED_WORDING` are the review's own ((a-1),
(b 完整), (g-2) ...), so a reader holding the review can check the two against
each other line by line.

Approved is not the same as released. The review's own standing list of what is
still missing (第三輪 §C5 文案面整體狀態) governs: the 500 path's own message is
being redrafted, ``PortfolioContext`` has no source field yet, and several
sentences beyond this batch have never been submitted. Nothing here should be
read as clearing C5 for release.
"""

from __future__ import annotations

from typing import Final

# ---------------------------------------------------------------------------
# (a) f* interval covers "no edge"
# ---------------------------------------------------------------------------

#: (a-1) 風控 2026-08-19 逐字定稿（第一輪，修訂版），字面含標點不得改動，漂移須重送風控。
#: The two placeholders are already-formatted percentages. Describing f* as what
#: the formula computed, rather than as something the system puts forward, is a
#: required correction and not a preference: what is shown is the un-capped f*,
#: while ``kelly_allowed_weight`` releases ``min(max(f*, 0) x 0.25, 0.10)``, so
#: presenting the larger number as a proposal would be the system sizing a
#: position (約束 11). Naming a confidence level was struck for the same class of
#: reason -- the bootstrap's 95% is a construction parameter, and at n=20 the
#: realised coverage is well under the nominal one. 落地條件 6 requires the
#: effective cap on the same screen, at no lesser prominence.
KELLY_F_STAR_INTERVAL_DISCLOSURE = (
    "此次估計的 f*（Kelly 公式算出的比例，尚未套用上限）的 95% 區間為 "
    "{f_star_ci_low_pct} 至 {f_star_ci_high_pct}。"
    "此區間涵蓋『沒有優勢』的可能——以目前的樣本量，本系統無法確定這個策略是否真的有優勢，"
    "即使點估計本身是正值。"
)

#: (a-2) 風控 2026-08-19 逐字定稿（第一輪，修訂版），字面含標點不得改動，漂移須重送風控。
#: **落地於 K4b**: 約束 36 puts this one in ``app/advice/limits.py``, whose Kelly
#: check may branch on ``ci_includes_no_edge`` and nothing finer. It is carried
#: here for inventory only -- this lane does not wire it, and does not touch
#: ``limits.py``.
KELLY_F_STAR_INTERVAL_FLAG_DISCLOSURE = (
    "本次估計值的區間涵蓋『沒有優勢』的可能：以目前樣本量，本系統無法確定這個策略是否真的有優勢。"
    "完整區間數字可至設定頁查看。"
)

# ---------------------------------------------------------------------------
# (b) selection bias over repeated imports
# ---------------------------------------------------------------------------

#: (b 完整) 風控 2026-08-19 逐字定稿（第一輪，修訂版），字面含標點不得改動，漂移須重送風控。
#: Shown when ``K_observed >= 2`` (約束 30). The clause the first round struck
#: out claimed every submitted request is counted; ``KellyAttemptStore.append``
#: only ever sees attempts that already cleared request validation, so keeping
#: it would have described K as more complete than it is. 落地條件 4 forbids
#: collapsing this behind a tooltip or an accordion.
KELLY_SELECTION_BIAS_FULL = (
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
)

#: (b 短) 風控 2026-08-19 逐字定稿（第一輪，主案原文），字面含標點不得改動，漂移須重送風控。
#: Shown when ``K_observed == 1``. The "1" here is a fact of the branch, not a
#: threshold: this string is only ever selected on the K==1 path, which is why
#: it is written out rather than interpolated.
KELLY_SELECTION_BIAS_SINGLE = (
    "此標的目前記錄到 1 次回測帶入嘗試（K_observed，含被拒絕的嘗試、含所有策略、不限時間範圍）。"
    "這只代表你送出『帶入』的次數是 1 次，不代表你只檢視過 1 次回測結果——"
    "本系統無法得知你在畫面上比較過幾種設定、又只送出了其中一組。"
)

# ---------------------------------------------------------------------------
# (c) what walk-forward does and does not protect against
# ---------------------------------------------------------------------------

#: (c) 風控 2026-08-19 逐字定稿（第一輪，修訂版），字面含標點不得改動，漂移須重送風控。
#: The draft said the data is cut into two pieces; ``app/backtest/splits.py``
#: rolls several folds and can leave a tail of bars in neither, so that would
#: have promised a partition the splitter does not guarantee. The subject is
#: narrowed to this system rather than stated universally, because a user tuning
#: by hand really can fit on out-of-sample data (ADR-0006 Consequences).
KELLY_WALK_FORWARD_SCOPE = (
    "本系統的 walk-forward 是把資料依時間先後分段："
    "較早的區段用來看策略在該段的表現，較晚的區段（樣本外／out-of-sample）用同一組參數再看一次。"
    "三支策略的參數是系統寫死的常數，不會依任何輸入被調整，"
    "因此本系統不會用樣本外資料回頭調整參數。"
    "但也因為如此，『樣本外』在本系統中只代表資料的時間區段位置，"
    "對『你自己反覆嘗試多種設定後才挑一次結果』這件事沒有防護作用（詳見選擇偏誤揭露）。"
)

# ---------------------------------------------------------------------------
# (e) the historical frequency standing in for Kelly's p
# ---------------------------------------------------------------------------

#: (e) 風控 2026-08-19 逐字定稿（第二輪，修訂版，採主案），字面含標點不得改動，漂移須重送風控。
#: The sentence states plainly that ``kelly_allowed_weight`` puts the sampled
#: frequency where the formula asks for a probability -- the second of the
#: three things the veto of the first-round drafts required, and the one that
#: may not be softened into a statement about what the system "cannot" do.
#: Two conditions travel with it: 1-A requires the OOS start/end dates on the
#: same screen (otherwise "這段歷史樣本" points at nothing checkable), and 1-B
#: limits it to ``source == "backtest"`` -- a manual or overridden pair is not a
#: sample frequency at all, and its own sentence ((e-manual)) is not yet
#: approved.
KELLY_WIN_RATE_IS_NOT_PROBABILITY = (
    "此處的『勝率』，是這段歷史樣本中納入計算的回合裡，獲利回合所佔的比例；"
    "這是對已經發生過的事做的統計整理，不是你下一筆交易會不會獲利的機率。"
    "Kelly 公式所要求的 p，在數學上是『重複同一分布下注時獲勝的機率』；"
    "本系統在計算這條上限時，放進這個位置的正是前面這個歷史頻率，而不是這個機率——"
    "這是本功能目前的已知限制，不是已經被系統處理掉的問題。"
)

#: (e-manual) 風控 2026-08-19 逐字定稿（第三輪，修訂版，採主案），字面含標點不得改動，
#: 漂移須重送風控。
#: The other side of 1-B's branch. When the effective pair was typed -- ``manual``,
#: or ``backtest_overridden``, whose effective values are hand-keyed with the
#: imported ones kept beside them (約束 4) -- (e)'s first clause would be false,
#: because there is no sample frequency involved at all. Same third obligation
#: as (e), stated of a different number: the formula's p position holds what the
#: user entered.
#: 落地條件 18 makes the two mutually exclusive and exhaustive, and 21 limits
#: this approval to a screen showing the effective values only -- putting the
#: original imported pair beside them needs a distinguishing sentence that has
#: not been drafted. Wired in K4b, once PortfolioContext carries the source
#: (落地條件 19).
KELLY_MANUAL_WIN_RATE_IS_NOT_PROBABILITY = (
    "此處的『勝率』與『盈虧比』，是你自行輸入（或以回測帶入後自行覆寫）的估計值，"
    "不是本系統量測所得的數字。"
    "Kelly 公式所要求的 p，在數學上是『重複同一分布下注時獲勝的機率』；"
    "本系統在計算這條上限時，放進這個位置的正是你自己輸入（或覆寫）的這個數字——"
    "這是本功能目前的已知限制，不是已經被系統處理掉的問題。"
)

# ---------------------------------------------------------------------------
# (f) a hand-typed pair
# ---------------------------------------------------------------------------

#: (f 完整) 風控 2026-08-19 逐字定稿（第二輪，主案分號版原文），字面含標點不得改動，漂移須重送風控。
#: The semicolons are load-bearing: they lift "本系統不會查核其正確性" out of the
#: "若與實際交易狀況不符" clause, which in the first-round draft read as if the
#: lack of checking were conditional. "不會" and not "無法" -- verifying is
#: technically possible and deliberately not done (net_worth.py:41 precedent).
KELLY_MANUAL_INPUT_DISCLOSURE = (
    "此勝率與盈虧比是你自行輸入的估計值，本系統不會查核其正確性，也不會自行調整你輸入的數字；"
    "不代表系統已為你確認過這組數字合理；"
    "若與實際交易狀況不符，本條上限的判定將隨之失真。"
)

#: (f tooltip) 風控 2026-08-19 逐字定稿（第一輪，備案原文），字面含標點不得改動，漂移須重送風控。
#: Approved **only** as a tooltip beside the input field, and only on a screen
#: that also carries :data:`KELLY_MANUAL_INPUT_DISCLOSURE` in full. It is a
#: supplement, never a substitute (落地條件 4).
KELLY_MANUAL_INPUT_TOOLTIP = (
    "此數字是你自行輸入的估計值，系統未驗證正確性，也不會自動調整；"
    "不代表系統已為你確認過這組數字合理。"
)

# ---------------------------------------------------------------------------
# (d-1) the frame around a refused import
# ---------------------------------------------------------------------------

#: (d-1 元件 A) 風控 2026-08-19 逐字定稿（第二輪，原文），字面含標點不得改動，漂移須重送風控。
#: Shown for the three **sample-size** codes only -- ``low_round_trips``,
#: ``low_win_trips``, ``low_loss_trips``. "這是常見情況" is true of those and
#: false of ``symbol_mismatch`` (a front-end bug) and ``insufficient_data``, and
#: attaching reassurance to a fault is the failure mode the NO_SECTOR_DETAILS
#: ruling named. The trailing "：" introduces the gate's own message.
KELLY_REFUSAL_FRAME = (
    "多數標的、多數期間的完整進出次數都達不到本系統設定的門檻；"
    "未達門檻時，系統會拒絕寫入這筆 Kelly 輸入，這是常見情況，不是系統出錯，"
    "也不代表這支策略或這個標的『不好』。這次沒有寫入的原因與實際數字如下："
)

#: (d-1 元件 B) 風控 2026-08-19 逐字定稿（第二輪，原文），字面含標點不得改動，漂移須重送風控。
#: Shown for **all six** refusal codes: ``app/api/kelly.py`` appends the attempt
#: before raising in every one of them, so the count really does move each time.
#: 3-A requires (b) on the same screen, not merely a link -- k_distinct_specs is
#: pushed up too, and a link alone would suggest only K_observed moved. It may
#: **not** be reused on the non-finite-interval 500 path, whose logged attempt
#: is not a refusal (3-B, still open).
KELLY_REFUSAL_ATTEMPT_LOGGED = (
    "這次被拒絕寫入的嘗試，已經被系統記錄下來，並計入 K_observed（詳見選擇偏誤揭露）。"
)

#: (3-B) 風控 2026-08-19 逐字定稿（第三輪，修訂版，採主案），字面含標點不得改動，漂移須重送風控。
#: The non-finite-interval 500 path (約束 27) also appends an attempt, so K moves
#: there too and the user was never told. It needed its own sentence rather than
#: :data:`KELLY_REFUSAL_ATTEMPT_LOGGED`: that row's ``outcome`` is ``"ok"`` with
#: no reason code -- the gates all passed and the storage step is what failed --
#: so calling it a refusal would misstate what the log holds. Hence no word for
#: refusal anywhere in it, pinned by 落地條件 23.
#: "這次" carries weight and may not be trimmed: without it the sentence reads as
#: though the input never is or never will be written, while an already stored
#: row is untouched by this failure. 落地條件 22: (b) on the same screen, per the
#: K branch -- k_distinct_specs is pushed up by this attempt too, and a link is
#: not enough. If the surface cannot hold (b), this sentence does not appear
#: alone.
KELLY_NON_FINITE_ATTEMPT_LOGGED = (
    "這次嘗試已經被系統記錄下來，並計入 K_observed（詳見選擇偏誤揭露）；"
    "這筆輸入，這次沒有被寫入。"
)

# ---------------------------------------------------------------------------
# (h) round trips excluded from the out-of-sample count
# ---------------------------------------------------------------------------

#: (h) 風控 2026-08-19 逐字定稿（第二輪，主案原文），字面含標點不得改動，漂移須重送風控。
#: The paragraph order is part of the approval: the mechanism first, the known
#: asymmetry second. ADR-0006 Consequences forbids calling the exclusion
#: conservative, and with n=10 the evidence supports no direction at all -- which
#: is what the last clause says, and why it may not be shortened to "影響有限".
#: 4-A: "並另行計數" may not gain a "可查看" until FR-5 approves showing those two
#: counts. 4-C: same prominence as (b) and (c), never folded away.
KELLY_BOUNDARY_TRIP_EXCLUSION = (
    "本系統計算樣本外（OOS）回合數時，只計入完整包含在樣本外區段內的回合；"
    "跨越樣本內、外邊界的回合，以及在樣本外區段結束時仍未平倉的回合，會被排除在外，並另行計數。"
    "這個排除方式，會優先排除掉存續時間較長的回合；"
    "這對統計結果會造成什麼方向的影響，目前的證據不足以支持任何方向的判斷。"
)

# ---------------------------------------------------------------------------
# (g) the four ways cap 5 ends up not evaluable
# ---------------------------------------------------------------------------

#: (g-1) 風控 2026-08-19 逐字定稿（第一輪，主案原文），字面含標點不得改動，漂移須重送風控。
#: "勝率" appears here as the *name of an input field*, in a sentence saying the
#: field is empty, which is why it is on the backend whitelist rather than the
#: banned list (分歧①). Lands in ``limits.py`` in K4b.
KELLY_NOT_EVALUABLE_NO_INPUT = (
    "此標的尚未輸入 Kelly 所需的勝率與盈虧比（可透過手動輸入或回測帶入取得），"
    "本條上限目前無法評估。"
)

#: (g-2) 風控 2026-08-19 逐字定稿（第二輪，錨點修訂版），字面含標點不得改動，漂移須重送風控。
#: Absolute anchor first, elapsed days second -- the order NET_WORTH_EXPIRED_DETAIL
#: set. ``{anchored_on}`` is the date the pair was typed, rendered ``YYYY-MM-DD``.
#: ``{days}`` is the freshness window, interpolated from the constant in force
#: (落地條件 9): writing 30 here would leave the sentence behind the next time
#: the window moves.
KELLY_NOT_EVALUABLE_MANUAL_EXPIRED = (
    "此標的的 Kelly 輸入（來源：手動輸入）已過期——上次更新於 {anchored_on}，距今 {age_days} 天，"
    "超過 {days} 天的新鮮期，本條上限暫不評估；請重新確認數字後更新。"
)

#: (g-3) 風控 2026-08-19 逐字定稿（第二輪，錨點修訂版），字面含標點不得改動，漂移須重送風控。
#: Same shape as (g-2) with the anchor an imported pair actually ages from: the
#: end of the out-of-sample segment (D-4), not the moment of import. That anchor
#: is a date whose time of day is padded, so ``{anchored_on}`` must be bound to a
#: plain ``YYYY-MM-DD`` and never to an ISO datetime (6-A).
KELLY_NOT_EVALUABLE_BACKTEST_EXPIRED = (
    "此標的的 Kelly 輸入（來源：回測帶入）已過期——樣本外區段結束於 {anchored_on}，"
    "距今 {age_days} 天，超過 {days} 天的新鮮期，本條上限暫不評估；"
    "請重新執行回測並確認後更新。"
)

#: (g-4) 風控 2026-08-19 逐字定稿（第一輪，主案原文），字面含標點不得改動，漂移須重送風控。
#: No anchor exists, so no placeholder is inserted (6-B) and no stand-in date is
#: invented. "本系統無法判定其新鮮度" is required: the rejected alternative dropped
#: it and read as though staleness had been established, which is the same
#: fabrication as reporting a freshness that was never measured.
KELLY_NOT_EVALUABLE_NO_OOS_END_DATE = (
    "此標的的 Kelly 輸入（來源：回測帶入）缺少樣本外區段結束日，本系統無法判定其新鮮度，"
    "一律視為已過期，本條上限暫不評估；請重新執行回測並確認後更新。"
)


#: The approved inventory, keyed by the review's own item ids. A sentence that is
#: not in here is a sentence risk-compliance never saw:
#: ``tests/test_kelly_wording.py`` asserts this mapping and the module's public
#: constants are the same set, so adding one without an id fails the build.
RISK_CONFIRMED_WORDING: Final[dict[str, str]] = {
    "a-1": KELLY_F_STAR_INTERVAL_DISCLOSURE,
    "a-2": KELLY_F_STAR_INTERVAL_FLAG_DISCLOSURE,
    "b-full": KELLY_SELECTION_BIAS_FULL,
    "b-single": KELLY_SELECTION_BIAS_SINGLE,
    "c": KELLY_WALK_FORWARD_SCOPE,
    "e": KELLY_WIN_RATE_IS_NOT_PROBABILITY,
    "e-manual": KELLY_MANUAL_WIN_RATE_IS_NOT_PROBABILITY,
    "f-full": KELLY_MANUAL_INPUT_DISCLOSURE,
    "f-tooltip": KELLY_MANUAL_INPUT_TOOLTIP,
    "d-1-a": KELLY_REFUSAL_FRAME,
    "d-1-b": KELLY_REFUSAL_ATTEMPT_LOGGED,
    "3-b": KELLY_NON_FINITE_ATTEMPT_LOGGED,
    "h": KELLY_BOUNDARY_TRIP_EXCLUSION,
    "g-1": KELLY_NOT_EVALUABLE_NO_INPUT,
    "g-2": KELLY_NOT_EVALUABLE_MANUAL_EXPIRED,
    "g-3": KELLY_NOT_EVALUABLE_BACKTEST_EXPIRED,
    "g-4": KELLY_NOT_EVALUABLE_NO_OOS_END_DATE,
}

#: The item ids whose sentence is assembled somewhere other than this package,
#: so a reader does not go looking for a call site that is not there. (a-2) is
#: ``limits.py``'s by 約束 36 and is wired in K4b.
LANDS_ELSEWHERE: Final[frozenset[str]] = frozenset({"a-2"})

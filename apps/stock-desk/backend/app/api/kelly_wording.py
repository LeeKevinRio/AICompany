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
* **Not every constant here ships from here.** Nine of them are cap 5's and are
  attached by ``app/advice/limits.py``: (a-2), whose condition that layer sees
  as a single boolean (約束 36); the six (g) sentences, which it chooses between
  by cause; and the sixth round's (任務 1)/(任務 2), which belong to the f*<=0
  verdict and to the sizing exclusion that verdict triggers. They are recorded
  here so the approved inventory stays complete in one place, and imported from
  there rather than retyped -- :data:`LANDS_ELSEWHERE` lists them. The rest are
  display copy: they ship from the surfaces K4c builds, and the only assembly
  this module performs is :func:`kelly_dividend_note`'s fixed paragraph order.
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
still missing (第八輪 §C5 文案面最終狀態) governs. The items this module's own
history named are closed -- the 500 path has its own approved message (第四輪),
``PortfolioContext`` carries the source cap 5 branches on (K4b, 落地條件 19), the
f*≤0 pair was approved in the sixth round and is wired here, and the sixth
round's display copy (FR-5's frame and eleven column labels, 欄位 10, FR-6's four,
the FR-4 badge, the Kelly-side 口徑限定語) lands below with K4c-1, which is the
lane that builds the surface reading them, and 條件 53/68's before-overwrite
notice came back approved in the ninth round and lands with them. What remains
is engineering, not copy: 條件 74's entry gate (every front-end import call site
must go through that dialog first) and 條件 78 (the label on the button that
opens it is **unreviewed** and may not be invented by anyone). Nothing here
should be read as clearing C5 for release.
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
#: **落地於 K4b（已接通）**: 約束 36 puts this one in ``app/advice/limits.py``, whose
#: Kelly check may branch on ``ci_includes_no_edge`` and nothing finer. It is
#: attached to cap 5's ``passed``/``violated`` detail by
#: ``app.advice.limits._kelly_disclosures``, after (e)/(e-manual) and never in a
#: refusal: the sentence qualifies an estimate that was used, and a cap
#: reporting ``not_evaluable`` used none.
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

#: (條件 96 句) 風控 2026-08-22 逐字定稿（第十一輪，修訂版，採主案），字面含標點不得
#: 改動，漂移須重送風控。
#: The third cell of (b), for a row that owes the selection-bias disclosure and
#: has no attempt history to build it from. It states the **absence of the
#: record** and refuses to read that absence as a measurement -- which is the
#: same distinction (g-4) draws about a freshness that was never established,
#: and the reason it may not be replaced by a rendered "0".
#:
#: Reachable in practice: rows written before the attempt log existed upgrade
#: into exactly this state. 條件 98 puts the branch at the assembly point rather
#: than inside the (b) selector, because the 422 and "nothing entered" paths
#: share that selector and this sentence is false on both of them.
#:
#: The 修訂 struck a five-character phrase claiming the counts are missing *on
#: this page* (條件 100 keeps the struck literal out of the source): they are
#: missing everywhere, and saying "here" implies they can be found somewhere
#: else. Naming ``K_observed`` in the parenthesis is kept on purpose -- it names
#: the count, not a value, exactly as (b) does, and it is the same identifier
#: 元件 B and 3-B put in front of the user.
#:
#: 條件 101: it may never share a screen with 元件 B or 3-B's "已計入 K_observed",
#: which asserts K >= 1 and would contradict it outright.
KELLY_SELECTION_BIAS_UNLOGGED = (
    "此標的目前查無回測帶入嘗試紀錄（K_observed）——"
    "這是紀錄本身的缺席，不是查到了一個計數的結果；"
    "因此無法呈現選擇偏誤揭露所依據的計數。"
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

#: (g-overridden) 風控 2026-08-22 逐字定稿（第七輪，主案原文），字面含標點不得改動，
#: 漂移須重送風控。
#: The fifth cell of the (g) table (條件 51). ``backtest_overridden`` ages from
#: ``oos_end_date`` exactly as ``backtest`` does -- only ``manual`` anchors on the
#: write stamp -- but neither (g-2) nor (g-3) states its source truthfully:
#: (g-2)'s "手動輸入" names the wrong anchor mechanism, and (g-3)'s "回測帶入"
#: omits that the effective numbers are the user's own. Hence its own sentence,
#: identical to (g-3) but for the source parenthesis, whose wording is taken
#: verbatim from the already-approved (fr6-overridden) short label.
#:
#: The closing instruction is (g-3)'s and not (g-2)'s, and that is a finding
#: rather than a preference: what expired is the imported anchor, so re-keying
#: the pair by hand cannot refresh it (a hand edit goes through
#: :meth:`KellyInputRecord.overriding`, which carries the old anchor over
#: untouched). Only a fresh backtest moves it.
#:
#: 條件 53 (risk, open, does not block this constant): following that instruction
#: overwrites the user's manual adjustment -- a re-import writes ``source =
#: "backtest"`` -- so any surface offering an import entry point needs a
#: before-overwrite notice, and that notice is separate copy awaiting review.
KELLY_NOT_EVALUABLE_OVERRIDDEN_EXPIRED = (
    "此標的的 Kelly 輸入（來源：回測帶入，已手動調整）已過期——"
    "樣本外區段結束於 {anchored_on}，距今 {age_days} 天，超過 {days} 天的新鮮期，"
    "本條上限暫不評估；請重新執行回測並確認後更新。"
)


# ---------------------------------------------------------------------------
# (任務 1 / 任務 2) a non-positive f*: the cap that allows nothing
# ---------------------------------------------------------------------------

#: (任務 1) 風控 2026-08-22 逐字定稿（第六輪，修訂版），字面含標點不得改動，漂移須重送風控。
#: **落地於 limits.py**, cap 5's ``violated`` detail on the f*<=0 branch and on
#: no other (條件 40). It replaces the general sentence rather than joining it:
#: D-5 forbids reusing the ordinary phrasing here, because "your position is
#: above the allowance" reads as a demand to sell when the allowance is 0.
#:
#: Three things about it are rulings, not choices:
#:
#: * "這次" in the last clause is required. Without it the sentence makes a
#:   universal claim that is false on the f*>0 branch.
#: * The repeated 範圍限定 ("這次可用的加碼額度"、"只限制新增加碼的額度") is kept
#:   deliberately -- the review declined to trim it, because every repetition
#:   lands on the conservative side.
#: * No operating verb anywhere (約束 11): the sentence states what the cap does
#:   not do, and says outright that it offers no view on an existing holding.
#:
#: 條件 41 fixes the order when the interval flag is also set: this sentence
#: first, then (a-2).
KELLY_NON_POSITIVE_FRACTION_DETAIL = (
    "以目前輸入的勝率與盈虧比計算，Kelly 公式算出的比例（f*）不是正值："
    "以目前輸入計算，Kelly 公式不支持任何加碼部位，"
    "分數 Kelly 與硬上限取小後，這條上限這次可用的加碼額度為 0%。"
    "本條上限這次只限制新增加碼的額度，不對你目前已持有的部位提出任何處置意見。"
)

#: (任務 2) 風控 2026-08-22 逐字定稿（第六輪，修訂版），字面含標點不得改動，漂移須重送風控。
#: **落地於 limits.py**, appended to ``suggest_quantity_range``'s ``basis`` as a
#: whole sentence of its own (條件 37), whenever D-5's exclusion dropped cap 5
#: from the sizing inputs for a non-positive edge.
#:
#: It exists because that exclusion would otherwise be invisible or, worse,
#: described wrongly: 條件 35 keeps cap 5 out of the ``skipped`` list on this
#: branch, since the standing sentence there says the cap lacked usable data,
#: and here it had data and computed a definite 0. "上方" was struck from the
#: draft -- cap 5 sits below this range on the card, so the direction was simply
#: untrue -- and the closing clause is the same red line the (任務 1) sentence
#: carries: a zero allowance is not a statement about an existing position.
KELLY_ZERO_ALLOWANCE_RANGE_NOTE = (
    "「分數 Kelly 部位上限」這次計算出的加碼額度是 0"
    "（原因見第 5 條的說明，不是因為本次缺少資料），因此不列入這個區間的計算基礎；"
    "這個 0，只代表這條上限這次不提供加碼空間，不涉及你目前部位的任何處置。"
)


# ---------------------------------------------------------------------------
# (g-4-overridden) an imported-then-edited pair that cannot be aged
# ---------------------------------------------------------------------------

#: (g-4-overridden) 風控 2026-08-22 逐字定稿（第八輪，組三主案），字面含標點不得改動，
#: 漂移須重送風控。
#: The sixth cell of the (g) table, and the one that closes it (條件 66). It is
#: (g-4) with "，已手動調整" inserted in the source parenthesis, and nothing else:
#: the three overridden sentences now state their source in one uniform phrase.
#: 條件 68 extends 條件 53 here -- following the instruction re-imports and
#: overwrites the hand adjustment, so a surface with an import entry point owes
#: the user a before-overwrite notice, which is separate copy still in review.
KELLY_NOT_EVALUABLE_OVERRIDDEN_NO_OOS_END_DATE = (
    "此標的的 Kelly 輸入（來源：回測帶入，已手動調整）缺少樣本外區段結束日，"
    "本系統無法判定其新鮮度，一律視為已過期，本條上限暫不評估；"
    "請重新執行回測並確認後更新。"
)


# ---------------------------------------------------------------------------
# (欄位 11) why this import restored no dividends, per reason code
# ---------------------------------------------------------------------------
#
# Five messages over four codes, each built as 機制事實 -> E1 -> E2 -> E3 -> E4
# (條件 59; the order is part of the approval). The four shared elements are
# single constants appended verbatim rather than retyped into each message
# (條件 60), so a change to one cannot land in four of five places.
#
# These are **Kelly's own** constants (條件 62). The backtester's equivalents in
# ``app/api/backtest.py`` stay exactly as they are and are neither imported nor
# spliced: their scope qualifier names the strategy column of a screen that does
# not exist here, and their bias clause states a *direction* ("會低估") that the
# seventh round vetoed for round-trip statistics -- restoring dividends changes
# the bar series, so the round set itself changes and the direction of the move
# in win rate and payoff ratio is not established. What is stated instead is
# that the system did not compute it (E2), which is what is true.
#
# ``adjusted`` has no entry here: that path keeps ``DIVIDEND_ADJUSTED_NOTE``
# (第六輪, 沿用核可), and reusing it is the assembly point's job -- this module
# imports nothing.

#: (E1) 風控 2026-08-22 逐字定稿（第八輪，組一），字面含標點不得改動，漂移須重送風控。
#: The one determinate fact of the whole block, and required in all five
#: messages (條件 63): with no restoration, the return series excludes dividends
#: paid during the holding period. Its certainty is why it is stated flatly
#: while everything after it is hedged.
KELLY_DIVIDEND_NO_DIVIDEND_IN_RETURNS = "這次回測的報酬計算不含持有期間股利。"

#: (E2) 風控 2026-08-22 逐字定稿（第八輪，組一，修訂版採完整版），字面含標點不得改動，
#: 漂移須重送風控。
#: The direction sentence, and the seventh round's VETO turned around: the
#: earlier drafts said the pair "可能因此被低估", which is a one-way claim the
#: evidence does not support (restoring dividends re-runs the bars, so the round
#: set changes; even frozen, a dividend can turn a losing round into a winning
#: one *and* pull the average win down). It is also the direction that would
#: nudge a user towards revising their own numbers upward, on a screen that
#: offers an override field.
#:
#: "本系統未計算" and not "無法得知" (required 1): a user who re-runs with
#: restoration on can see the answer, so the direction is knowable -- this
#: system simply did not compute it.
KELLY_DIVIDEND_DIRECTION_UNKNOWN = (
    "本系統未計算除權息還原後，這裡顯示的勝率與盈虧比會是什麼；方向不明。"
)

#: (E3) 風控 2026-08-22 逐字定稿（第八輪，組一），字面含標點不得改動，漂移須重送風控。
#: The tense anchor. ``dividend_reason_code`` is written once at import and only
#: ever read afterwards, so this block describes the state as it was then, not
#: as it is now -- without this the four messages read as present-tense claims
#: about the current database.
KELLY_DIVIDEND_STATE_AS_RECORDED = "此為回測帶入當下記錄的狀態，顯示時本系統依當時記錄呈現。"

#: (E3, never_synced 版) 風控 2026-08-22 逐字定稿（第八輪，組一），字面含標點不得改動，
#: 漂移須重送風控。
#: 條件 69: the trailing parenthesis may **not** be dropped. On this branch the
#: recorded state is "nothing had been synced", and a user who has since run the
#: sync would otherwise read the line as current -- it is not, and will not
#: change until the backtest is re-run and re-imported.
KELLY_DIVIDEND_STATE_AS_RECORDED_NEVER_SYNCED = (
    "此為回測帶入當下記錄的狀態，顯示時本系統依當時記錄呈現（含是否已完成同步）。"
)

#: (E4) 風控 2026-08-22 逐字定稿（第八輪，組一，修訂版），字面含標點不得改動，
#: 漂移須重送風控。
#: Bounds E2's "方向不明" to the two numbers on this screen. required 2 struck the
#: draft's second clause ("其他計算基礎…本系統未提供比較"): the system *does*
#: publish a Buy & Hold comparison and does carry ``DIVIDEND_BIAS_SCOPE_NOTE``
#: on the backtest screen, so denying that would have been a false statement
#: about the product's own disclosures.
KELLY_DIVIDEND_DIRECTION_SCOPE = (
    "以上『方向不明』的判斷，僅限於這筆 Kelly 輸入所依據的這次回測算出的完整回合統計"
    "——也就是這裡的勝率與盈虧比。"
)

#: 機制事實句 1/5, ``disabled``. 風控 2026-08-22 逐字定稿（第八輪，組一）。
KELLY_DIVIDEND_DISABLED_FACT = (
    "這筆 Kelly 輸入所依據的回測，回測帶入當時依請求關閉了除權息還原"
    "（adjust_dividends=false）。"
)

#: 機制事實句 2/5, ``never_synced``. 風控 2026-08-22 逐字定稿（第八輪，組一）。
#: The command stays (required 4 allowed it): the actor is the user, so naming
#: the step they have not taken is a fact about this machine, not a forward
#: claim about anyone else's roadmap.
KELLY_DIVIDEND_NEVER_SYNCED_FACT = (
    "這筆 Kelly 輸入所依據的回測，回測帶入當時本機尚未同步過任何除權息資料"
    "（尚未執行 uv run python -m app.dividends.sync）。"
)

#: 機制事實句 3/5, ``no_events`` in TW. 風控 2026-08-22 逐字定稿（第八輪，組一，修訂版）。
#: "不含上櫃" and never "尚未涵蓋上櫃" (required 4): "尚未" would promise, on the
#: vendor's behalf, coverage nobody has committed to.
KELLY_DIVIDEND_NO_EVENTS_TW_FACT = (
    "這筆 Kelly 輸入所依據的回測未進行除權息還原：本機雖有除權息資料，"
    "但這段期間內查無本商品的除權息紀錄。"
    "可能是這段期間確實沒有配息，也可能是資料涵蓋範圍有限"
    "（目前只涵蓋台股上市，不含上櫃），本系統無法判斷是哪一種情況。"
)

#: 機制事實句 4/5, ``no_events`` outside TW. 風控 2026-08-22 逐字定稿（第八輪，組一）。
#: The distinction the backtester's own note makes and for the same reason: "no
#: dividend was found" and "there was nothing to search" are different claims,
#: and only the second one is true here.
KELLY_DIVIDEND_NO_EVENTS_NON_TW_FACT = (
    "這筆 Kelly 輸入所依據的回測未進行除權息還原：本系統的除權息資料目前只涵蓋台股上市，"
    "不涵蓋這個市場，因此不是『查無配息』，而是『沒有資料可查』。"
)

#: 機制事實句 5/5, ``unusable_events``. 風控 2026-08-22 逐字定稿（第八輪，組一）。
KELLY_DIVIDEND_UNUSABLE_EVENTS_FACT = (
    "這筆 Kelly 輸入所依據的回測未進行除權息還原：查到本商品在此區間的除權息紀錄，"
    "但欄位不足以推算調整因子，已整筆略過而非用推估值代替。"
)

#: The ``unusable_events`` tail, appended after E4 on that branch only.
#: 風控 2026-08-22 逐字定稿（第八輪，組一，修訂版）。
#: The seventh round struck "請重跑同步" here: re-syncing does not touch an input
#: that is already stored, so the instruction was inert on this screen. What
#: actually updates the pair is a fresh backtest and a fresh import, and that is
#: what it now says. The closing offer to report the code is approved **as data-
#: quality reporting** and may not be cited as precedent for action wording
#: generally.
KELLY_DIVIDEND_UNUSABLE_EVENTS_TAIL = (
    "若日後同步除權息資料後這筆紀錄的欄位轉為可用，仍須重新執行回測並重新帶入，"
    "這裡顯示的這筆 Kelly 輸入才會更新；"
    "如需協助排查，也可回報此代號與區間供人工覆核來源欄位。"
)


def kelly_dividend_note(reason_code: str, *, market: str) -> str | None:
    """The 欄位 11 block for one ``dividend_reason_code``, or ``None``.

    Assembled here so the paragraph order 條件 59 fixes lives in one place and a
    display surface renders one finished string (約束 21: the front end renders
    verbatim and composes nothing). ``no_events`` is the single code whose fact
    depends on the market, exactly as it is for the backtester's own notes.

    ``None`` comes back for ``adjusted`` -- there was no degradation to explain,
    and that path keeps ``DIVIDEND_ADJUSTED_NOTE`` -- and for any code this
    module has never seen, because inventing a sentence for an unknown state is
    the one thing none of these may do. 條件 42/70 additionally limit the whole
    block to ``source == "backtest"``; that is the caller's gate, not this one's.
    """
    if reason_code == "disabled":
        fact, state = KELLY_DIVIDEND_DISABLED_FACT, KELLY_DIVIDEND_STATE_AS_RECORDED
    elif reason_code == "never_synced":
        fact = KELLY_DIVIDEND_NEVER_SYNCED_FACT
        # 條件 69: this branch's own state sentence, parenthesis included.
        state = KELLY_DIVIDEND_STATE_AS_RECORDED_NEVER_SYNCED
    elif reason_code == "no_events":
        fact = (
            KELLY_DIVIDEND_NO_EVENTS_TW_FACT
            if market == "TW"
            else KELLY_DIVIDEND_NO_EVENTS_NON_TW_FACT
        )
        state = KELLY_DIVIDEND_STATE_AS_RECORDED
    elif reason_code == "unusable_events":
        fact, state = KELLY_DIVIDEND_UNUSABLE_EVENTS_FACT, KELLY_DIVIDEND_STATE_AS_RECORDED
    else:
        return None

    block = (
        fact
        + KELLY_DIVIDEND_NO_DIVIDEND_IN_RETURNS
        + KELLY_DIVIDEND_DIRECTION_UNKNOWN
        + state
        + KELLY_DIVIDEND_DIRECTION_SCOPE
    )
    if reason_code == "unusable_events":
        block += KELLY_DIVIDEND_UNUSABLE_EVENTS_TAIL
    return block


# ---------------------------------------------------------------------------
# (任務 7) the imported pair kept beside an overridden one
# ---------------------------------------------------------------------------

#: (任務 7) 風控 2026-08-22 逐字定稿（第八輪，組二備案原文），字面含標點不得改動，
#: 漂移須重送風控。
#: Shown where a ``backtest_overridden`` row's *original* imported pair is
#: displayed -- the screen 落地條件 21 said could not exist until a distinguishing
#: sentence was approved. This is that sentence.
#:
#: The備案 was taken over the主案 on two grounds the seventh round named: the
#: object of "被你手動調整" is spelled out as "這筆輸入的生效內容" (the主案 left it
#: readable as the two numbers themselves -- precisely the misreading this
#: sentence exists to prevent), and the denial is bounded to named things (the
#: cap's calculation, the effective values) instead of the主案's sweeping "不是
#: 現在用來計算的數字".
KELLY_ORIGINAL_PAIR_DISCLOSURE = (
    "這裡顯示的勝率與盈虧比，是這筆 Kelly 輸入回測帶入當時、由系統算出的原始值。"
    "這筆輸入後來被你手動調整；但調整的是這筆輸入的生效內容，"
    "這兩個數字本身不曾被覆蓋，仍是原樣保留下來的原始值。"
    "本條上限的計算，用的是目前生效值，不是這裡顯示的原始值；"
    "目前生效的 Kelly 輸入，用的也不是這裡這兩個數字。"
)

# (任務 8) 風控 2026-08-22 **定稿撤銷**（第十三輪）。The label that stood over the
# original view's out-of-sample dates is gone from this module, and its literal
# is on the zero-occurrence guard in ``tests/test_kelly_wording.py``: 條件 92
# 選項二 narrowed that view to two numbers and one sentence, so the label has no
# surface to sit on, and a constant kept "for later" is a wording waiting to be
# rendered by the next reader. 條件 65's same-screen requirement lapses with it --
# (任務 7) now lands alone.
#
# Why the period went rather than the sentence: the label carries 「樣本外」, which
# obliges (c) on the same screen, and (c) closes by pointing at the
# selection-bias disclosure, which reaches ``k_observed`` -- rebuilding, on an
# overridden row, the backtest disclosure surface 條件 42 keeps off it and the
# count 約束 7 bans from this view. The thirteenth round also recorded that the
# period was never load-bearing here: it would have carried checkability, and
# what this view needs is uniqueness of reference, which the rendering condition
# already closes (the entry point exists only while the row is overridden with a
# kept pair, and a fresh import rewrites the row and removes it).


# ---------------------------------------------------------------------------
# (任務 3) FR-5: the backtest sample the stored pair was measured on
# ---------------------------------------------------------------------------

#: (任務 3 框架句) 風控 2026-08-22 逐字定稿（第六輪，修訂版），字面含標點不得改動，
#: 漂移須重送風控。
#: The frame over the eleven-column detail. Two clauses were struck on the same
#: ground the (任務 2) "上方" was: "這次量測" pointed at a phrase none of the 21
#: approved sentences contain, and "前面" named a position on a screen this
#: module cannot see. 條件 42 limits the whole block -- this sentence and all
#: eleven rows -- to ``source == "backtest"``: showing it for an overridden row
#: puts the imported sample beside hand-keyed effective values, which is exactly
#: what 落地條件 21 says needs its own distinguishing sentence.
KELLY_BACKTEST_SAMPLE_DETAIL_INTRO = (
    "以下是這筆 Kelly 輸入所依據的回測樣本明細，"
    "供你核對各句所指的『這段歷史樣本』實際是哪一次回測、哪一段期間。"
)

#: (欄位 1-11) 風控 2026-08-22 逐字定稿（第六輪，原文），字面含標點不得改動，
#: 漂移須重送風控。
#: Eleven labels, approved one by one, in the order the review lists them. They
#: are separate constants rather than one dict literal so a drift in any single
#: label fails its own verbatim assertion, and so the inventory below can key
#: each on its own item id.
#:
#: 條件 43 travels with rows 3-5: ``n == n_win + n_loss`` is a guard, not an
#: assumption, and the three may not be displayed side by side unless it holds.
#: 條件 44 travels with rows 6-7: they carry the same prominence as (h), which
#: explains what the two counts are.
#:
#: C8-6 (風控 2026-08-23 批審) 續引 :data:`KELLY_DETAIL_ROUND_TRIPS_LABEL` for the
#: backtest report's own round-trip count row, on the 沿用不審 three-part test
#: (逐字同構、純計數名詞無方法論/機率/後果陳述、語境同類). It is a re-use of this
#: constant, not a new literal -- see :class:`app.api.backtest.BacktestMetricLabels`.
KELLY_DETAIL_STRATEGY_LABEL = "策略"
KELLY_DETAIL_OOS_PERIOD_LABEL = "樣本外（OOS）區段（起訖日期）"
KELLY_DETAIL_ROUND_TRIPS_LABEL = "完整回合數"
KELLY_DETAIL_WIN_TRIPS_LABEL = "獲利回合數"
KELLY_DETAIL_LOSS_TRIPS_LABEL = "虧損回合數"
KELLY_DETAIL_EXCLUDED_BOUNDARY_TRIPS_LABEL = "跨界排除回合數"
KELLY_DETAIL_OPEN_TRIP_AT_END_LABEL = "期末未平倉回合數"
KELLY_DETAIL_OBSERVATIONS_LABEL = "樣本觀測數（資料點數，非回合數）"
KELLY_DETAIL_WIN_RATE_CI_LABEL = "勝率的 95% 區間（Wilson，依完整回合計）"
KELLY_DETAIL_RATES_VERIFIED_LABEL = "費率查證狀態"
KELLY_DETAIL_DIVIDEND_LABEL = "除權息還原狀態"

#: (欄位 10 句) 風控 2026-08-22 逐字定稿（第六輪，主案原文），字面含標點不得改動，
#: 漂移須重送風控。
#: 條件 45 binds it to ``rates_verified is False`` and to nothing else: ``None``
#: means the run never reported on its rates, which is not the same finding, and
#: ``not rates_verified`` would collapse the two. The banned spelling is named in
#: the ruling because it is the one a later reader would reach for.
KELLY_RATES_UNVERIFIED_NOTE = (
    "此標的 Kelly 輸入所依據的回測，其手續費／交易稅／滑價率尚未對照主要來源查證，"
    "這筆勝率與盈虧比應視為待查證狀態。"
)


# ---------------------------------------------------------------------------
# (任務 4) FR-6: which of the three sources the effective pair came from
# ---------------------------------------------------------------------------

#: (fr6-manual) 風控 2026-08-22 逐字定稿（第六輪，原文），字面含標點不得改動，
#: 漂移須重送風控。 The long form and the short label are separate approvals and
#: are not interchangeable: the label is a chip beside the pair, the sentence is
#: the disclosure.
KELLY_SOURCE_MANUAL_STATEMENT = "此標的目前生效的 Kelly 輸入，來源為手動輸入。"
KELLY_SOURCE_MANUAL_LABEL = "來源：手動輸入。"

#: (fr6-overridden) 風控 2026-08-22 逐字定稿（第六輪，原文），字面含標點不得改動，
#: 漂移須重送風控。
#: "可以查看" is a promise about this product, and 條件 46 makes it one that has
#: to be kept: a surface stating it owes the user a reachable path to the
#: original pair. That path is the original-values view ((任務 7)), which
#: ``app/api/kelly.py`` serves for exactly the rows this sentence describes.
KELLY_SOURCE_OVERRIDDEN_STATEMENT = (
    "此標的目前生效的 Kelly 輸入，原本由回測帶入，之後經你手動調整；"
    "調整後的數字才是目前生效值，原始回測帶入的數字仍保留、可以查看。"
)
KELLY_SOURCE_OVERRIDDEN_LABEL = "來源：回測帶入，已手動調整；原始回測值仍保留可查。"

#: (fr6-backtest) 風控 2026-08-22 逐字定稿（第十輪，風控直接定稿），字面含標點不得改動，
#: 漂移須重送風控。
#: The third cell, which the sixth round left empty and K4c-1 reported as a gap.
#: It is a parallel composition of the two above rather than new copy, and it
#: closes 條件 84: the source table now has a value in every cell, with no
#: ``None`` fallback that a reader could mistake for "a sentence nobody wrote".
#:
#: 條件 85 bounds how it may be displayed: it states provenance and nothing about
#: quality, so it may not share a slot with anything that reads as verification
#: (the 費率查證 row is its own row, in the FR-5 detail), and its prominence may
#: not exceed (e)'s -- "imported from a backtest" must not out-shout the sentence
#: saying what that measurement is and is not.
KELLY_SOURCE_BACKTEST_STATEMENT = "此標的目前生效的 Kelly 輸入，來源為回測帶入。"
KELLY_SOURCE_BACKTEST_LABEL = "來源：回測帶入。"


# ---------------------------------------------------------------------------
# (任務 5) FR-4 badge: the four states one input can be in
# ---------------------------------------------------------------------------

#: (badge) 風控 2026-08-22 追認（第六輪，沿用 ``NetWorthSection`` 既有核可字面），
#: 字面不得改動，漂移須重送風控。
#: The fourth state is the one the sixth round added: "never entered" is the
#: absence of a row, and reporting it as a freshness would say an input exists.
#: 條件 47 carries three more rules the surface owes: an ``age_days`` of ``None``
#: may not be rendered with a day suffix (no age was established), an ``expired``
#: badge appears only on a screen that also carries the matching (g) sentence,
#: and "建議更新" may not sit in the same visual group as a trading action.
KELLY_FRESHNESS_BADGE_ABSENT = "尚未輸入"
KELLY_FRESHNESS_BADGE_FRESH = "已更新"
KELLY_FRESHNESS_BADGE_AGEING = "建議更新"
KELLY_FRESHNESS_BADGE_EXPIRED = "已過期"


# ---------------------------------------------------------------------------
# (任務 6) the 口徑限定語 on Kelly's own side
# ---------------------------------------------------------------------------

#: (任務 6 Kelly 面) 風控 2026-08-22 逐字定稿（第六輪，主案原文），字面含標點不得改動，
#: 漂移須重送風控。
#: C5 wrote this qualifier when the two win rates one click apart were counted
#: over different units -- this one over complete round trips
#: (``app/backtest/episodes.py``), the backtest report's own over settled fills.
#: 條件 65 makes it the label over the win rate in the original-values view, and
#: forbids minting a second wording for it there.
#:
#: **狀態更新 (C8, 風控 2026-08-23 批審**
#: ``work/reviews/2026-08-23-C8-顯示語意-風控批審.md``**)**: the C8 fix moved
#: ``app/backtest/report.py`` to the round-trip layer, so the report's win rate
#: is now ``RoundTripStats.round_trip_win_rate`` -- the very same statistic this
#: label names. The premise behind 條件 49 (two denominators needing two
#: qualifiers) therefore no longer holds, and that round's 「依結算筆數計」 twin
#: became a false statement. The 2026-08-23 ruling is 條件 49 的**重送**: it
#: retires that twin, keeps this literal untouched (逐字定稿,一字不動), and makes
#: it the single definition site for **both** surfaces -- ``BacktestReportView``
#: now renders it from the API (:class:`app.api.backtest.BacktestMetricLabels`)
#: instead of holding a literal of its own. 條件 49's pairing obligation is thus
#: discharged by there being one label, not two.
#:
#: Serving it to the report surface is deliberate and not a widening: the same
#: statistic under two spellings would imply two different things, which is the
#: mix-up the qualifier exists to stop.
KELLY_WIN_RATE_ROUND_TRIP_QUALIFIER = "勝率（依完整回合計）"


# ---------------------------------------------------------------------------
# (條件 53/68) the before-overwrite notice, by source
# ---------------------------------------------------------------------------
#
# 風控 2026-08-22 逐字定稿（第九輪，採備案：依來源拆兩變體），字面含標點不得改動，
# 漂移須重送風控。The dialog a surface must show **before** it calls
# ``POST .../import-backtest`` on a row whose effective pair was hand-keyed
# (條件 74). Re-importing writes ``source = "backtest"`` over the whole row, so
# the instruction (g-overridden) and (g-4-overridden) give -- "請重新執行回測並確認
# 後更新" -- destroys the very numbers (任務 7) and (fr6-overridden) told the user
# were kept.
#
# The single-sentence draft was **not** adopted, on a truth condition rather than
# a preference: "不留在任何欄位" is true of a manual pair and false of an
# overridden row's original values, which that row's own import left in
# ``kelly_import_attempts`` for good. One sentence covering both would be false
# on one branch, so there are two variants and a shared close.
#
# 條件 82 freezes the paragraph order (段一 -> 段二 -> 段三) and makes the close a
# single shared constant appended to each variant, never retyped into both.
# 條件 75: nothing here interpolates, and no win rate or payoff ratio may be
# rendered into this dialog -- showing a number here would pull (f)/(e-manual)
# and the whole style floor of 落地條件 4 onto a modal, which is a separate
# submission.

#: (標題, 兩變體共用；aria-label 逐字同用, 條件 72) 風控 2026-08-22 逐字定稿（第九輪，
#: 修訂版）。The draft's opening qualifier -- the one 條件 71/77/78 ban outright and
#: which is therefore not retyped here -- was struck because there is no earlier
#: result to fetch: the import re-runs the backtest here and now
#: (:func:`app.api.kelly.import_kelly_input_from_backtest` takes a request, not a
#: ``backtest_id``), so the struck title described an action this system does not
#: perform. ``tests/test_kelly_wording.py`` carries the banned literal.
KELLY_OVERWRITE_NOTICE_TITLE = "帶入回測結果 — 執行前請確認"

#: (manual 段一) 風控 2026-08-22 逐字定稿（第九輪，原文）。
KELLY_OVERWRITE_NOTICE_MANUAL_EFFECT = (
    "這裡目前生效的勝率與盈虧比，是你自行輸入的估計值；"
    "執行後，本系統會重新執行一次回測，把這個標的目前生效的勝率與盈虧比，"
    "換成這次算出的新結果。"
)

#: (manual 段二) 風控 2026-08-22 逐字定稿（第九輪，原文）。
#: "不會留在任何欄位" is checked and true on this branch and only on this branch:
#: a hand-keyed pair never reaches ``kelly_import_attempts``, so once
#: :meth:`app.kelly.store.KellyInputStore.upsert` overwrites the row the numbers
#: are gone from the database entirely.
KELLY_OVERWRITE_NOTICE_MANUAL_LOSS = (
    "你自行輸入的這組數字，執行後就不再是生效值。"
    "本系統沒有版本紀錄，這組數字不會留在任何欄位，事後也沒有畫面可以找回。"
)

#: (backtest_overridden 段一) 風控 2026-08-22 逐字定稿（第九輪，原文）。
KELLY_OVERWRITE_NOTICE_OVERRIDDEN_EFFECT = (
    "這裡目前生效的勝率與盈虧比，是你在原本回測帶入的基礎上手動調整過的數字，"
    "另外還保留著一組原始回測值供你查看；"
    "執行後，本系統會重新執行一次回測，把這個標的目前生效的勝率與盈虧比，"
    "換成這次算出的新結果。"
)

#: (backtest_overridden 段二) 風控 2026-08-22 逐字定稿（第九輪，修訂版）。
#: 「這一列的」 is the修訂 and is load-bearing: the original imported pair *is*
#: kept somewhere after the overwrite -- the attempt that imported it recorded
#: its own measured columns, and ``DELETE`` does not touch that table (約束 35) --
#: so the unqualified "不留在任何欄位" would have overstated the loss. Qualified to
#: this row, it is verbatim equivalent to what ``upsert`` does.
KELLY_OVERWRITE_NOTICE_OVERRIDDEN_LOSS = (
    "你調整過的這組生效值、以及原本保留的那組原始回測值，執行後都會被這次的新結果取代。"
    "本系統沒有版本紀錄，這兩組舊數字都不會留在這一列的任何欄位，事後也沒有畫面可以找回。"
)

#: (共用段三) 風控 2026-08-22 逐字定稿（第九輪，修訂版）。One constant appended to
#: both variants (條件 82), so the two outcomes are always described in the same
#: sentence, at the same length, in the same place. 「下方」 was struck as a layout
#: claim, and the inner quotes are 『』 -- both are part of the approval.
#: "前面所說的動作" points inside this same block, whose order 條件 82 freezes, so
#: the reference is checkable rather than a claim about a screen.
KELLY_OVERWRITE_NOTICE_CHOICES = (
    "點『取消』，這個標的的 Kelly 輸入維持現在的樣子，不會有任何改變；"
    "點『確認帶入，覆蓋目前資料』，才會執行前面所說的動作。"
)

#: (按鈕) 風控 2026-08-22 逐字定稿（第九輪）。Two drafts were turned down and are
#: not retyped here (條件 71 bans them from the source; the literals live in
#: ``tests/test_kelly_wording.py``): a proceed-anyway confirm label, because a
#: built-in "despite the warning" framing is the system taking a side, and a
#: cancel label carrying its own reassurance, because it prices the two outcomes
#: unevenly and nudges towards cancelling. The symmetry is carried by 段三
#: instead, which describes both outcomes in one sentence of equal length.
KELLY_OVERWRITE_CANCEL_LABEL = "取消"
KELLY_OVERWRITE_CONFIRM_LABEL = "確認帶入，覆蓋目前資料"

#: (條件 78 觸發按鈕) 風控 2026-08-22 逐字定稿（第十二輪，風控直接定稿），字面不得改動，
#: 漂移須重送風控。 It lives beside the dialog because it is what opens it, and
#: 條件 102 puts it here; it is **not** part of the dialog (條件 103), which two
#: of the four cells do not have at all.
#:
#: Both drafted candidates were refused, and the reasons bound what this label
#: may say. One named a *result* to bring in, which would read as fetching a run
#: that already exists -- ``import_kelly_input_from_backtest`` stores no runs and
#: spends a data-source call producing new numbers every time, the same untrue
#: direction the ninth round struck from the dialog title. The other opened with
#: a word presupposing an earlier run, which is false for a symbol that has
#: never been imported and for a hand-typed pair.
#:
#: 「執行回測」 denies the fetch reading outright and 「並帶入」 keeps the action
#: name the rest of this surface已建立; both halves are true in all four cells.
#: No word for overwriting is added: it is false where nothing is stored, and
#: where something is, the consequence is carried in full by the dialog (條件 74).
#:
#: 條件 103: the front end renders this verbatim and its ``aria-label`` is this
#: string exactly. 條件 105: pressing it does not make the import true -- no
#: 「來源：回測帶入」 may appear until one has succeeded.
KELLY_IMPORT_BACKTEST_TRIGGER_LABEL = "執行回測並帶入"


def kelly_overwrite_notice(source: str) -> tuple[str, ...] | None:
    """The before-overwrite dialog paragraphs for one source, or ``None``.

    **Three paragraphs, in order, never one joined string** (條件 93). Running
    them together is not a formatting preference: 段二 is the paragraph stating
    what the user loses, and burying it mid-block visually demotes the one thing
    this dialog exists to say. The literals are untouched -- only the seam
    between them is.

    條件 73 makes the four cells mutually exclusive and exhaustive, and this
    function owns two of them; the caller owns "no row at all". Every branch is
    written out, including the one that returns ``None`` on purpose:

    * ``manual`` / ``backtest_overridden`` -- their own variant, plus 段三.
    * ``backtest`` -- **explicitly** no dialog. A re-import replaces a
      measurement with a measurement, there is nothing hand-keyed to lose, and
      it is the very action (g-3)/(g-4) instruct the user to take: a warning
      there would be a miscalibrated signal pointing the opposite way to the
      product's own advice. The lightweight one-line variant proposed for this
      cell was **not adopted and may not ship** (條件 71).
    * anything else -- ``None``, because inventing copy for a source this module
      has never seen is the one thing none of these may do.

    A ``dict.get`` default would collapse the third and fourth cells into an
    accident; 條件 73 forbids exactly that, so the branch is spelled out and
    tested with a positive assertion.
    """
    if source == "manual":
        variant = (
            KELLY_OVERWRITE_NOTICE_MANUAL_EFFECT,
            KELLY_OVERWRITE_NOTICE_MANUAL_LOSS,
        )
    elif source == "backtest_overridden":
        variant = (
            KELLY_OVERWRITE_NOTICE_OVERRIDDEN_EFFECT,
            KELLY_OVERWRITE_NOTICE_OVERRIDDEN_LOSS,
        )
    elif source == "backtest":
        return None
    else:
        return None
    return (*variant, KELLY_OVERWRITE_NOTICE_CHOICES)


# ---------------------------------------------------------------------------
# (條件 110/111) the before-delete notice, and the one variant it needs
# ---------------------------------------------------------------------------
#
# 風控 2026-08-22 逐字定稿（第十五輪，主案四段零修訂 + overridden 段一變體），
# 字面含標點不得改動，漂移須重送風控。Shown before ``DELETE
# /api/kelly-inputs/{symbol}`` removes a stored pair.
#
# What the four paragraphs have to establish, and why each exists:
#
# * **what disappears** -- the whole row, every column of it, named by symbol and
#   market. 「這一列」 is the ninth round's own unit of loss, reused.
# * **what does not come back** -- two claims, each bounded to a true object:
#   there is no history table (D-2, a design choice, hence 「沒有」 and not
#   「無法」), and no screen can show the deleted row again. The struck 「此動作
#   無法復原」 is a universal that is false of the attempt log, and 條件 111 keeps
#   it out of the source for good.
# * **what is out of scope** (L7) -- the attempt log and ``K_observed`` are
#   untouched, stated as a property of the *delete's reach* rather than of the
#   log's contents, so it is equally true for a symbol that never had an attempt.
#   A source-based branch was rejected on evidence: ``manual`` rows can have
#   K > 0 (refused attempts are logged and do not rewrite the row) and
#   ``backtest`` rows can have K == 0 (條件 96's upgrade path), so branching on
#   source would state something false in two reachable corners.
# * **what the screen becomes** -- (g-1)'s own words for the state the symbol
#   returns to, with the way back stated in the same sentence and at the same
#   length, closed by 「不是找回這次刪除的內容」 so that "you can enter it again"
#   cannot be read as "so it is recoverable".
#
# 條件 82's paragraph order and 條件 93's separate delivery both apply here, and
# 條件 112 requires a ``role="dialog"`` surface: ``window.confirm`` supplies its
# own button labels, so the approved ones could not be rendered at all.

#: (刪除標題, aria-label 逐字同用, 條件 112) 風控 2026-08-22 逐字定稿（第十五輪）。
KELLY_DELETE_NOTICE_TITLE = "刪除 Kelly 輸入 — 執行前請確認"

#: (刪除段一, 基底) 風控 2026-08-22 逐字定稿（第十五輪，第十批主案原文）。
#: The two placeholders are the only interpolation in the whole block (條件 113)
#: and render in the shape this surface already uses, ``2330（TW）``.
KELLY_DELETE_NOTICE_SCOPE = (
    "這個動作會把 {symbol}（{market}）的 Kelly 輸入這一列整列刪除："
    "這一列目前存著的每一個欄位值——包含生效中的勝率與盈虧比在內——都會一併移除。"
)

#: (刪除段一, backtest_overridden 變體) 風控 2026-08-22 逐字定稿（第十五輪，風控直接
#: 定稿；點名片語逐字取自 :data:`KELLY_OVERWRITE_NOTICE_OVERRIDDEN_LOSS`）。
#: The base paragraph's 「每一個欄位值」 already covers the kept pair, but implicit
#: coverage does not withdraw a belief this product built explicitly: (任務 7) and
#: (fr6-overridden) both tell the user the original values are kept, and the
#: thirteenth round let those stand *because* the dialog at the moment of the
#: action takes the belief back. The import dialog names them; a silent delete
#: dialog would honour that premise by half.
KELLY_DELETE_NOTICE_SCOPE_OVERRIDDEN = (
    "這個動作會把 {symbol}（{market}）的 Kelly 輸入這一列整列刪除："
    "這一列目前存著的每一個欄位值——"
    "包含你調整過的這組生效值、以及原本保留的那組原始回測值在內——都會一併移除。"
)

#: (刪除段二) 風控 2026-08-22 逐字定稿（第十五輪，第十批主案原文）。
KELLY_DELETE_NOTICE_NO_RECOVERY = (
    "本系統沒有版本紀錄，事後也沒有畫面可以找回被刪除的這一列。"
)

#: (刪除段三) 風控 2026-08-22 逐字定稿（第十五輪，第十批主案原文）。
#: Both halves of the L7 disclosure and the state transition live in this one
#: paragraph, and 條件 114 makes its second clause a **behaviour anchor**: the
#: attempt log and its count really are untouched by ``DELETE`` (約束 35), and a
#: test asserts that rather than trusting the sentence.
KELLY_DELETE_NOTICE_SCOPE_AND_AFTERMATH = (
    "刪除的範圍也只有這一列：不論此標的先前是否曾嘗試回測帶入，"
    "嘗試紀錄與其累計計數（K_observed）都不在刪除範圍內，"
    "不會因這次刪除而有任何改變。"
    "刪除後，這個標的回到尚未輸入的狀態，"
    "第 5 條「分數 Kelly 部位上限」隨之回到無法評估；"
    "之後仍可透過手動輸入或回測帶入取得新的一組數字，"
    "但那會是新的輸入，不是找回這次刪除的內容。"
)

#: (刪除段四) 風控 2026-08-22 逐字定稿（第十五輪，第十批主案原文）。
#: The ninth round's closing structure with the action swapped, so both outcomes
#: are described in one sentence of equal length.
KELLY_DELETE_NOTICE_CHOICES = (
    "點『取消』，這個標的的 Kelly 輸入維持現在的樣子，不會有任何改變；"
    "點『確認刪除，移除目前資料』，才會執行前面所說的動作。"
)

#: (刪除確認鍵) 風控 2026-08-22 逐字定稿（第十五輪）。Neutral action plus its
#: consequence, the shape :data:`KELLY_OVERWRITE_CONFIRM_LABEL` set. The refused
#: alternatives are on 條件 111's zero-occurrence list, and the bare word for the
#: action is not reused here because it is already the trigger's label.
KELLY_DELETE_CONFIRM_LABEL = "確認刪除，移除目前資料"

#: The cancel key is :data:`KELLY_OVERWRITE_CANCEL_LABEL`, approved for this
#: dialog too (第十五輪) and **not** copied: one literal, one definition
#: (落地條件 2). The inventory below carries it under a second id so the reader
#: holding the review finds both approvals.


def kelly_delete_notice(source: str, *, symbol: str, market: str) -> tuple[str, ...] | None:
    """The delete dialog's four paragraphs for one row, or ``None``.

    條件 111 makes the three cells mutually exclusive and exhaustive, with the
    variant chosen from the source **as it is at the moment of confirmation**
    (條件 94's rule, applied here): ``backtest_overridden`` takes the paragraph
    that names the kept pair, ``manual`` and ``backtest`` take the base one, and
    an unknown source gets nothing rather than a guess. Nothing falls through a
    default -- an empty cell and an unwritten sentence must not look alike.

    The symbol and the market are interpolated here so the surface renders and
    composes nothing (約束 21); they are the only two values this block carries
    (條件 113).
    """
    if source == "backtest_overridden":
        scope = KELLY_DELETE_NOTICE_SCOPE_OVERRIDDEN
    elif source == "manual":
        scope = KELLY_DELETE_NOTICE_SCOPE
    elif source == "backtest":
        scope = KELLY_DELETE_NOTICE_SCOPE
    else:
        return None
    return (
        scope.format(symbol=symbol, market=market),
        KELLY_DELETE_NOTICE_NO_RECOVERY,
        KELLY_DELETE_NOTICE_SCOPE_AND_AFTERMATH,
        KELLY_DELETE_NOTICE_CHOICES,
    )


# ---------------------------------------------------------------------------
# (條件 116) the two controls the original-values view is reached and left by
# ---------------------------------------------------------------------------

#: 風控 2026-08-22 逐字定稿（第十五輪，平行合成），字面不得改動。
#: The entry control's verb is (fr6-overridden)'s own 「可以查看」 and its noun is
#: that sentence's label, so the promise and the control that keeps it are one
#: chain a reader can follow -- which is what E-5 verifies. The way back is a
#: bare navigation verb making no claim at all.
#:
#: 條件 116 requires both to be backend constants with the front end rendering
#: them verbatim, ``aria-label`` included: the English placeholders they replace
#: were the only controls carrying a Chinese promise, and 條件 108's ruling for
#: form-field names does not reach them.
KELLY_ORIGINAL_VALUES_ENTRY_LABEL = "查看原始回測值"
KELLY_ORIGINAL_VALUES_BACK_LABEL = "返回"


#: The approved inventory, keyed by the review's own item ids. A sentence that is
#: not in here is a sentence risk-compliance never saw:
#: ``tests/test_kelly_wording.py`` asserts this mapping and the module's public
#: constants are the same set, so adding one without an id fails the build.
RISK_CONFIRMED_WORDING: Final[dict[str, str]] = {
    "a-1": KELLY_F_STAR_INTERVAL_DISCLOSURE,
    "a-2": KELLY_F_STAR_INTERVAL_FLAG_DISCLOSURE,
    "b-full": KELLY_SELECTION_BIAS_FULL,
    "b-single": KELLY_SELECTION_BIAS_SINGLE,
    # 第十一輪 條件 96: (b)'s third cell.
    "b-unlogged": KELLY_SELECTION_BIAS_UNLOGGED,
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
    "g-overridden": KELLY_NOT_EVALUABLE_OVERRIDDEN_EXPIRED,
    "g-4-overridden": KELLY_NOT_EVALUABLE_OVERRIDDEN_NO_OOS_END_DATE,
    "task-1": KELLY_NON_POSITIVE_FRACTION_DETAIL,
    "task-2": KELLY_ZERO_ALLOWANCE_RANGE_NOTE,
    # 第八輪組一: the four shared elements and the five mechanism facts are
    # tracked as their own items, because each was approved on its own terms and
    # :func:`kelly_dividend_note` only ever concatenates them in a fixed order.
    "e1": KELLY_DIVIDEND_NO_DIVIDEND_IN_RETURNS,
    "e2": KELLY_DIVIDEND_DIRECTION_UNKNOWN,
    "e3": KELLY_DIVIDEND_STATE_AS_RECORDED,
    "e3-never-synced": KELLY_DIVIDEND_STATE_AS_RECORDED_NEVER_SYNCED,
    "e4": KELLY_DIVIDEND_DIRECTION_SCOPE,
    "div-disabled": KELLY_DIVIDEND_DISABLED_FACT,
    "div-never-synced": KELLY_DIVIDEND_NEVER_SYNCED_FACT,
    "div-no-events-tw": KELLY_DIVIDEND_NO_EVENTS_TW_FACT,
    "div-no-events-non-tw": KELLY_DIVIDEND_NO_EVENTS_NON_TW_FACT,
    "div-unusable-events": KELLY_DIVIDEND_UNUSABLE_EVENTS_FACT,
    "div-unusable-events-tail": KELLY_DIVIDEND_UNUSABLE_EVENTS_TAIL,
    # 第八輪組二.
    # (任務 8) 第十三輪撤銷，不再列於清冊；字面改由零出現守門看管。
    "task-7": KELLY_ORIGINAL_PAIR_DISCLOSURE,
    # 第六輪 display copy, landed with K4c-1: the surface that reads it exists
    # now. The eleven column labels keep the review's own numbering.
    "task-3": KELLY_BACKTEST_SAMPLE_DETAIL_INTRO,
    "fr5-1": KELLY_DETAIL_STRATEGY_LABEL,
    "fr5-2": KELLY_DETAIL_OOS_PERIOD_LABEL,
    "fr5-3": KELLY_DETAIL_ROUND_TRIPS_LABEL,
    "fr5-4": KELLY_DETAIL_WIN_TRIPS_LABEL,
    "fr5-5": KELLY_DETAIL_LOSS_TRIPS_LABEL,
    "fr5-6": KELLY_DETAIL_EXCLUDED_BOUNDARY_TRIPS_LABEL,
    "fr5-7": KELLY_DETAIL_OPEN_TRIP_AT_END_LABEL,
    "fr5-8": KELLY_DETAIL_OBSERVATIONS_LABEL,
    "fr5-9": KELLY_DETAIL_WIN_RATE_CI_LABEL,
    "fr5-10": KELLY_DETAIL_RATES_VERIFIED_LABEL,
    "fr5-11": KELLY_DETAIL_DIVIDEND_LABEL,
    "fr5-10-note": KELLY_RATES_UNVERIFIED_NOTE,
    "fr6-manual": KELLY_SOURCE_MANUAL_STATEMENT,
    "fr6-manual-label": KELLY_SOURCE_MANUAL_LABEL,
    "fr6-overridden": KELLY_SOURCE_OVERRIDDEN_STATEMENT,
    "fr6-overridden-label": KELLY_SOURCE_OVERRIDDEN_LABEL,
    # 第十輪 條件 84/85: the third source cell, filled by the review itself.
    "fr6-backtest": KELLY_SOURCE_BACKTEST_STATEMENT,
    "fr6-backtest-label": KELLY_SOURCE_BACKTEST_LABEL,
    "badge-absent": KELLY_FRESHNESS_BADGE_ABSENT,
    "badge-fresh": KELLY_FRESHNESS_BADGE_FRESH,
    "badge-ageing": KELLY_FRESHNESS_BADGE_AGEING,
    "badge-expired": KELLY_FRESHNESS_BADGE_EXPIRED,
    "task-6-kelly": KELLY_WIN_RATE_ROUND_TRIP_QUALIFIER,
    # 第九輪: the before-overwrite dialog, which closes 條件 53/68.
    "notice-title": KELLY_OVERWRITE_NOTICE_TITLE,
    "notice-manual-1": KELLY_OVERWRITE_NOTICE_MANUAL_EFFECT,
    "notice-manual-2": KELLY_OVERWRITE_NOTICE_MANUAL_LOSS,
    "notice-overridden-1": KELLY_OVERWRITE_NOTICE_OVERRIDDEN_EFFECT,
    "notice-overridden-2": KELLY_OVERWRITE_NOTICE_OVERRIDDEN_LOSS,
    "notice-choices": KELLY_OVERWRITE_NOTICE_CHOICES,
    "notice-cancel": KELLY_OVERWRITE_CANCEL_LABEL,
    "notice-confirm": KELLY_OVERWRITE_CONFIRM_LABEL,
    # 第十二輪 條件 102: the trigger that opens the dialog, not part of it.
    "trigger-label": KELLY_IMPORT_BACKTEST_TRIGGER_LABEL,
    # 第十五輪: the delete dialog, its overridden variant, and its two keys. The
    # cancel key is the ninth round's constant, approved again for this dialog
    # and kept as one definition.
    "delete-title": KELLY_DELETE_NOTICE_TITLE,
    "delete-1": KELLY_DELETE_NOTICE_SCOPE,
    "delete-1-overridden": KELLY_DELETE_NOTICE_SCOPE_OVERRIDDEN,
    "delete-2": KELLY_DELETE_NOTICE_NO_RECOVERY,
    "delete-3": KELLY_DELETE_NOTICE_SCOPE_AND_AFTERMATH,
    "delete-4": KELLY_DELETE_NOTICE_CHOICES,
    "delete-confirm": KELLY_DELETE_CONFIRM_LABEL,
    "delete-cancel": KELLY_OVERWRITE_CANCEL_LABEL,
    # 第十五輪 條件 116: the original-values view's entry and exit controls.
    "original-entry": KELLY_ORIGINAL_VALUES_ENTRY_LABEL,
    "original-back": KELLY_ORIGINAL_VALUES_BACK_LABEL,
}

#: The item ids whose sentence is assembled somewhere other than this package,
#: so a reader does not go looking for a call site that is not there. All seven
#: are cap 5's and are attached in ``app/advice/limits.py``: (a-2) by 約束 36;
#: the four (g) sentences because D-6 puts the "is this input still usable"
#: decision inside ``_check_kelly_fraction``, which is therefore the only place
#: that can tell the four causes apart; and (任務 1)/(任務 2) because the f*<=0
#: verdict and D-5's exclusion from the sizing inputs are both decided there.
#: They are imported from here, never retyped, so the approved inventory stays
#: the single copy (落地條件 2).
LANDS_ELSEWHERE: Final[frozenset[str]] = frozenset(
    {
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
)

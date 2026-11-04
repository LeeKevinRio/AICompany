"""Every user-facing sentence the playbook can emit, in one file.

Kept together so the full list can be handed to risk-compliance as one artefact
(each string here appears verbatim in the hand-off report) and so no rule can
invent a sentence at the point of use.

House style for this module, following 風控 required R1/R5/R13/R17:

* **最小事實陳述** -- a line states the measured number, the threshold it met and
  the rule id. It does not argue, reassure or urge.
* **Every line carries its provenance** -- 依據資料日 / 預定執行日 / 參考價 are
  part of the directive line format, never collapsed away.
* **Refusals are neutral** -- 冷卻期 wording states the mechanism and the date,
  with no moral pressure (R13), and never says the change is denied (R14).
* **No threshold is written as a literal** -- every number in :data:`RULE_TEXT`
  is a placeholder bound to a named :class:`~app.playbook.models.RuleParams`
  field and rendered by :func:`rule_text`, so a dated rule change moves the
  sentence with it (覆審 2026-08-12: RULE_TEXT 門檻數字全參數化).

The sentences in this module are the ones risk-compliance signed off verbatim on
2026-08-12 (`work/reviews/快市排程-風控前置意見.md`, 覆審裁決). Chinese
punctuation follows the house convention (full-width); nothing else in an
approved sentence may be re-worded, shortened or moved behind a tooltip.
"""

from __future__ import annotations

from collections.abc import Iterable
from datetime import date
from decimal import Decimal
from typing import NamedTuple

from app.playbook.models import (
    Action,
    BatchStatus,
    Directive,
    Mode,
    RuleParams,
    RuleSetAuthorship,
)

#: 風控 R2 常駐歸屬語, 覆審 VETO-2 A 版逐字. ``{RULE_SET_DATE}`` may only be bound
#: to the effective date of the rule version in force -- never to "today", and
#: never to a date inferred from anything else.
ATTRIBUTION_NOTE = (
    "此指令是你於 {RULE_SET_DATE} 自行設定的規則之機械執行結果，非本系統的判斷或建議。"
)

#: 歸屬語情境 2: the authorship record exists but its 生效日 could not be read.
ATTRIBUTION_NOTE_DATE_MISSING = (
    "此指令是你自行設定的規則之機械執行結果，非本系統的判斷或建議"
    "（規則設定日期缺漏：{RULE_SET_DATE_STATUS}）。"
)

#: The only value ``{RULE_SET_DATE_STATUS}`` may take (覆審: 值域僅此一句).
ATTRIBUTION_DATE_STATUS_UNREADABLE = "規則版本 {version} 的生效日期讀取失敗"

#: 四輪收斂裁決 §6 三句's second sentence, branch (c): the first sentence of
#: :data:`ATTRIBUTION_NO_USER_RULES`, reused rather than retyped so the two can
#: never drift apart. ``ATTRIBUTION_NO_USER_RULES`` is composed from it below.
ATTRIBUTION_NO_USER_RULES_FIRST = "目前使用的是系統預設規則集，尚無你本人的設定或修改紀錄。"

#: 歸屬語情境 1: there is no user submission record at all. The 歸屬語 itself is
#: not shown -- claiming authorship of a system default would be the exact
#: misattribution R2 exists to prevent -- and the module produces no rule-driven
#: directive until the user confirms a rule set.
#:
#: 三輪定稿 (題 8) narrowed sentence two and added sentence three: the block only
#: covers the rule-driven series (進場／停損／停利), and the escape hatch is named
#: in the same breath so no reader can take the block for a disabled exit. The
#: third sentence may not be shortened into a pointer, and de-duplicating this
#: string in a view may not truncate it.
ATTRIBUTION_NO_USER_RULES = (
    ATTRIBUTION_NO_USER_RULES_FIRST + "本模組僅依你設定的規則集產生進場、停損、停利指令，"
    "在你確認規則集之前不會產生這類指令。"
    "你隨時可送出全部出清（EMERGENCY_EXIT），不受此限制。"
)

#: EMERGENCY_EXIT 專用歸屬語 (三輪定稿 題 7). The exit is attributed to the action
#: the user just submitted, not to a rule set, so it is rendered regardless of
#: authorship and :func:`attribution_note` is never consulted for it. Rendered
#: only when the exit actually produced lines: with no batch to sell there is no
#: 指令 for the sentence to be about.
EXIT_ATTRIBUTION = (
    "此指令是你在本次操作中提交的「全部出清」要求之機械執行結果，"
    "非本系統的判斷或建議；EMERGENCY_EXIT 不依賴規則集，"
    "無論規則集是否已確認皆可送出。"
)

#: N-166 風控 S4 (2026-10-31): the ALREADY_PENDING branch's attribution. Every
#: line that branch describes came from an earlier submission, so
#: :data:`EXIT_ATTRIBUTION`'s 「本次操作中提交」 would misdate it.
EXIT_ATTRIBUTION_PRIOR = (
    "此指令是你在先前操作中提交的「全部出清」要求之機械執行結果，"
    "非本系統的判斷或建議；EMERGENCY_EXIT 不依賴規則集，"
    "無論規則集是否已確認皆可送出。"
)

#: N-166 風控 S5: the RESULT branch's attribution when earlier, still unsettled
#: EMERGENCY lines exist next to the ones this submission produced.
EXIT_ATTRIBUTION_MIXED = (
    "本次新產生與先前已有的賣出指令，都是你分別在本次與先前操作中提交的「全部出清」"
    "要求之機械執行結果，非本系統的判斷或建議；EMERGENCY_EXIT 不依賴規則集，"
    "無論規則集是否已確認皆可送出。"
)

#: 三輪定稿 (題 9): 情境 1 with shares still held. The block stops the S/P series
#: from being evaluated, and a held position whose stop loss went unevaluated may
#: not be left to be inferred from the absence of a line (same duty as S-2).
#: ``{symbols}`` lists every un-liquidated symbol in full -- truncating it would
#: hide exactly the holding this sentence exists to disclose.
UNAUTHORED_HOLDING_NOTE = (
    "【S/P 系列停損停利今日未依規則評估】規則集尚無你本人的設定或修改紀錄，"
    "本模組今日不產生規則驅動指令；你目前持有 {symbols} 尚未出清，"
    "其停損/停利（S/P 系列）今日未依規則評估。"
)

#: §6 頁面免責句 (四輪收斂裁決 題 11), three sentences in this fixed order. They
#: are page-level, not per-line: the ledger's own lines carry their provenance
#: already, and this block states what the *page* was computed from before the
#: reader reaches the first line. Rendered above the ledger, never collapsed.
#:
#: ① binds the whole page to the 依據資料日 it was computed on.
PAGE_SUMMARY_DATA_DATE = "本頁面指令依 {data_date} 收盤資料計算。"

#: ② branch (a): the rule version in force and the effective date it carries.
#: ``{rules_effective_date}`` may only be bound to the ``effective_date`` of the
#: :class:`RuleParams` row actually in force -- never to today, never to a date
#: derived from anything else (裁決: 只取 in-force effective_date 禁推斷頂替).
PAGE_SUMMARY_RULES = "採用規則版本 {rules_version}（生效日 {rules_effective_date}）。"

#: ② branch (b): the version is known but its 生效日 is not readable, and the
#: same branch is taken whenever authorship itself cannot be determined
#: (fail-closed). Reuses the one approved 值域 sentence rather than restating it.
PAGE_SUMMARY_RULES_UNREADABLE = ATTRIBUTION_DATE_STATUS_UNREADABLE + "。"

#: ③ 主詞限縮 to the lines actually in today's ledger, so an empty ledger makes
#: the sentence vacuous rather than false, and 「自行設定」 matches the wording
#: used by :data:`ATTRIBUTION_NOTE`.
PAGE_SUMMARY_ATTRIBUTION = (
    "今日指令帳冊中的每筆指令是你自行設定的規則之機械執行結果，"
    "非本系統的判斷或建議；實際成交結果以你的券商回報為準。"
)

#: 四輪收斂裁決 題 12: what an empty ledger means when every rule really was
#: evaluated. It is only ever sent when the completeness flag
#: (:attr:`PlaybookEvaluation.rules_fully_evaluated`) is true, so 「未命中」 and
#: 「未評估」 can be told apart instead of both reading as 「無。」.
NO_RULE_HIT_NOTE = "今日規則已全數評估，無任何規則命中，未產生指令。"

#: action -> the word the user's own rule set uses.
ACTION_LABELS: dict[Action, str] = {
    "buy": "買進",
    "sell": "賣出",
    "defer": "順延",
    "skip": "跳過",
    "none": "無動作",
}

#: 三輪定稿 (題 10) picked 「待確認規則集」 over 「未啟用」: the worst misreading of
#: 「未啟用」 is that the escape hatch is off too, and the exit is always open.
MODE_LABELS: dict[Mode, str] = {
    "normal": "正常",
    "defense": "防守",
    "frozen": "全凍結",
    "emergency_frozen": "緊急出清後凍結",
    "unconfirmed": "待確認規則集",
}

#: rule id -> the one-line restatement shown next to every directive (R1: the
#: rule id, its text and the date may not be collapsed away).
#:
#: Every ``{placeholder}`` is a threshold of the *active* parameter version; see
#: :func:`_rule_text_values` for the binding and :func:`rule_text` to render.
RULE_TEXT: dict[str, str] = {
    "R1": "R1 排程日進場：排程日買進該檔下一批。",
    "R2": (
        "R2 不追價煞車：當日漲幅 >{r2_change_pct_limit}% 或 BIAS25 >+{r2_bias_limit}% 時順延該批。"
    ),
    "R3": "R3 順延上限：同一批順延累計 {r3_max_defers} 次後跳過該批。",
    "R4": "R4 凍結期間不執行進場：凍結或排程暫停期間不產生 R 系列進場。",
    "S1": (
        "S1 單批停損：收盤 < 該批成本 ×{s1_ratio}（防守模式 ×{s1_defense_ratio}）"
        "賣出該批，該檔排程暫停至收盤站回 25MA。"
    ),
    "S2": (
        "S2 整檔停損：收盤 < 該檔均成本 ×{s2_ratio} 出清整檔，"
        "並列入黑名單 {blacklist_days} 交易日。"
        "黑名單期間僅停止新增買進（R 系列），若有未出清批次殘留，"
        "S/P 系列停損停利仍照常評估。"
    ),
    "S3": (
        "S3 組合熔斷：新倉未實現 < {s3_unrealized_pct}% 時全組合凍結 "
        "{s3_freeze_trading_days} 交易日，期間僅產生賣出類指令。"
    ),
    "P1": "P1 停利：收盤 ≥ 該批成本 ×{p1_ratio} 賣出該批 1/3。",
    "P2": (
        "P2 停利：收盤 ≥ 該批成本 ×{p2_ratio} 再賣 1/3，"
        "其餘轉移動停利（跌破 25MA 或波段最高收盤 ×{p2_trailing_peak_ratio} 出清）。"
    ),
    "P3": (
        "P3 過熱：BIAS25 >+{p3_bias_limit}%（高波動清單 >+{p3_bias_limit_high_vol}%）"
        "強制減 1/3，每 {p3_cooldown_trading_days} 交易日限一次。"
    ),
    "M1": (
        "M1 大盤總開關：指數收盤低於月線連續 {m1_consecutive_days} 日進入防守模式，站回月線解除。"
    ),
    "IRON1": (
        "鐵律①現金 {cash_floor_ratio}% 不可破：進場金額使現金低於 "
        "{cash_floor_ratio}% 時縮減該批股數。"
    ),
    "EMERGENCY": (
        "EMERGENCY_EXIT：使用者提交全部出清，系統產生全部持倉的賣出指令，"
        "並自提交日起暫停 R 系列（新倉進場）{freeze_days} 交易日；"
        "S/P 系列停損停利仍照常評估。"
    ),
    "REBALANCE": (
        "季末 REBALANCE：由使用者在季末提交，以提交當日總資產重算 "
        "TOTAL_DEPLOY=總資產 ×{deploy_ratio}%，重算後立即生效；"
        "期中已實現獲利不滾入批量。"
    ),
}

#: The band every non-stop-loss line carries (CEO 裁決七).
LIMIT_BAND_NOTE = (
    "限價帶 {low}–{high}（T 收盤 {reference} ±{pct}%）；開盤價超出即標記 MISSED，不追價。"
)

#: Stop-loss lines have no band at all -- stated, not left blank. 風控 E-1: the
#: sentence may not promise a fill, so the condition under which a market order
#: does not fill is part of the same sentence rather than a footnote.
STOP_LOSS_NO_BAND_NOTE = (
    "停損指令不設滑價帶，T+1 開盤以市價單送出；市價單在跌停或無量時可能無法成交。"
)

#: EMERGENCY_EXIT lines are not stop-loss lines and no longer borrow that
#: sentence (覆審: service.py 不得再掛停損句).
EMERGENCY_EXIT_NO_BAND_NOTE = (
    "EMERGENCY_EXIT 指令不設滑價帶，T+1 開盤以市價單送出；市價單在跌停或無量時可能無法成交。"
)

#: 風控 R17: every reference price says which trading day it came from and what
#: it does not include. Appended to the rendered directive line.
REFERENCE_PRICE_NOTE = "（依據交易日收盤價，不反映今日盤中變動）"

#: R17 空價分支: with no reference price there is no trading day to disclose, so
#: the line says the price is absent instead of qualifying one that is not there.
REFERENCE_PRICE_UNAVAILABLE_NOTE = "（無可用參考價）"

#: 資料缺漏 (鐵律⑤ / 風控 R6): the symbol produces no line at all that day.
DATA_GAP_NOTE = "{symbol} 資料狀態為 {status}（來源 {source}），依鐵律⑤當日不產生指令。"

#: The data layer's own sentence about the 加權指數 series the M1 / fast-market
#: judgement was made on (served from cache, spliced from more than one source
#: -- ADR-0009 D-7). Quoted verbatim under a label, never paraphrased (風控
#: 2026-09-15 R1-b); the trailing clause names what the series feeds
#: (creative-lead, `work/stock-desk-alerts-asof揭露句-文案.md`; fixed verbatim by
#: risk-compliance-officer 2026-09-15 -- the noun-phrase alternative
#: 「（M1 與快市判定之共同輸入）」 may be swapped in without re-review). Format it
#: with :func:`index_data_reason_note` so the quoted sentence's own full stop
#: does not land before the clause.
INDEX_DATA_REASON_NOTE = "加權指數資料：{reason}（用於 M1 與快市判定）。"


def index_data_reason_note(reason: str) -> str:
    """``INDEX_DATA_REASON_NOTE`` with the quoted sentence's full stop moved after the clause."""
    return INDEX_DATA_REASON_NOTE.format(reason=reason.rstrip("。"))


#: S-2: the same gap on a symbol that still holds shares. 「資料缺漏致停損無法
#: 評估須主動顯著揭露不得靜默」, so the missing stop-loss evaluation is named
#: rather than left to be inferred from the absence of a line.
DATA_GAP_HOLDING_NOTE = (
    "【停損今日無法評估】{symbol} 資料狀態為 {status}（來源 {source}），"
    "依鐵律⑤當日不產生指令；本檔目前持有部位，"
    "停損/停利（S/P 系列）今日無法依規則評估。"
)

#: 指數缺漏主句. Split from the deferral clause (覆審): the deferral only happens
#: on a schedule day, so it may not be asserted on a day that had no entry due.
INDEX_DATA_GAP_NOTE = (
    "加權指數資料狀態為 {status}（來源 {source}），M1 今日未評估、沿用前一狀態；當日不新開倉。"
)

#: Rendered only when the R series was actually deferred today (index_gap_defer).
INDEX_DATA_GAP_DEFER_NOTE = "今日為排程日，R 系列進場改為順延並計入順延次數（逐批列示）。"

#: M1-1: 指數缺漏當日 R 系列一律順延（真正的順延，不是靜默跳過）。
INDEX_GAP_DEFER_NOTE = "M1 今日未評估（加權指數資料 {status}），本批順延第 {count} 次。"

#: FM-1: 快市判定在指數資料不可用時沿用前態，不得因資料缺漏首次進入。
FAST_MARKET_CARRIED_NOTE = (
    "加權指數資料狀態為 {status}，快市判定沿用前一次評估結果（{state}，依據資料日 {measured_on}）；"
    "資料缺漏不會使系統首次進入快市。"
)

#: FM-1 的另一半：沒有前次判定可沿用時說清楚本次以「非快市」處理。
FAST_MARKET_NO_HISTORY_NOTE = (
    "加權指數資料狀態為 {status}，尚無前一次快市判定可沿用，本次以「非快市」處理；"
    "資料缺漏不會使系統首次進入快市。"
)
FAST_MARKET_STATE_ACTIVE = "快市"
FAST_MARKET_STATE_INACTIVE = "非快市"

#: E-2: MISSED 重試上限對齊 R3。
MISSED_LIMIT_NOTE = "T+1 未成交（MISSED）累計 {count} 次，達 {limit} 次上限，跳過本批。"

#: R3 skip sentences, lifted out of the engine so every 跳過 line reads the same
#: (覆審 required: engine 就地組字串抽常數送審). Wording unchanged from the
#: strings they replace.
R3_SKIP_AFTER_LIMIT_NOTE = "{detail}，累計達 {limit} 次，跳過本批"
R3_SKIP_DEFERRED_NOTE = "順延已達 {count} 次，跳過本批"
R3_MISSED_SKIP_EFFECT_NOTE = "R3（對齊）：T+1 未成交累計 {count} 次後跳過本批"

#: Modes that suppress the R series; S/P lines are unaffected (CEO 裁決五).
FROZEN_NOTE = "目前為{mode}模式：R 系列進場不執行；S／P 系列停損停利仍照常評估。"

NOT_SCHEDULE_DAY_NOTE = (
    "{data_date} 非排程日（排程日為週二、週四的交易日），不產生 R 系列進場指令。"
)

#: 鐵律① reduced or cancelled an entry.
SHRINK_NOTE = "鐵律①現金 30%：本批股數由 {planned} 股縮減為 {actual} 股。"
SHRINK_TO_ZERO_NOTE = "鐵律①現金 30%：{symbol} 第 {batch_no} 批進場後將跌破現金下限，本批不進場。"

#: ADR-0035 Decision 5 / 風控 CEO #87 回審 二-1 (N-174(c), CEO #86 合併門檻):
#: the 預定執行日's log holds R-series buys this evaluation did not produce --
#: a later run that turned 凍結／防守, lost its index or symbol data, or would
#: now defer under R2. The first decision stands (S-α), so the line stays on the
#: page and this says what it is. Triggered from the lines themselves, never
#: from another sentence; right after FROZEN_NOTE when the page has one,
#: otherwise first. ``{entry_items}`` joins :data:`SAME_DAY_EARLIER_ENTRY_ITEM`
#: with 「、」.
SAME_DAY_EARLIER_ENTRY_NOTE = (
    "指令帳冊中有 {entry_count} 筆 R 系列買進指令，"
    "是同一預定執行日稍早一次評估已產生的指令：{entry_items}。"
    "本次評估沒有產生這些買進指令，但已產生的指令不會因此取消或修改，"
    "帳冊會照常以預定執行日開盤價判定，判定成交即記為持有批次並扣除帳冊現金；"
    "本頁其他說明若提到 R 系列進場不執行、當日不新開倉或當日不產生指令，"
    "是指本次評估不再產生新的指令，不包括上述已產生的指令。本系統不下單，"
    "無法得知你是否已依這些指令在券商下單，也無法替你在券商撤單："
    "若你在券商的買進實際成交，實際持股以你的券商回報為準；"
    "若未成交（包括未下單或已自行撤單），帳冊判定成交的批次將與你的實際持股不符。"
)

#: One ``{entry_items}`` entry, the N-168 item format.
SAME_DAY_EARLIER_ENTRY_ITEM = (
    "{symbol}第 {batch_no} 批買進 {shares} 股（規則 {rule_id}，預定執行日 {execution_date}）"
)

#: 風控 CEO #87 回審 二-3 第 4 點, revised 2026-11-01 (解讀點 (c)): a symbol whose
#: data is unusable on this run but which already has 買賣 lines (action in
#: ORDER_ACTIONS) in the 預定執行日's log; {line_count} counts those lines
#: only, and the sentence is not rendered for zero. Right after that symbol's
#: DATA_GAP_NOTE or DATA_GAP_HOLDING_NOTE, so 「當日不產生指令」 is not read as
#: cancelling an S1 the earlier run issued.
SAME_DAY_EARLIER_LINES_DATA_GAP_NOTE = (
    "{symbol} 本次資料狀態為 {status}，本次未重新評估這檔；"
    "指令帳冊中這檔的 {line_count} 筆買賣指令，"
    "是同一預定執行日稍早這檔資料可用時的評估已產生的指令，"
    "未因本次資料狀態而取消或修改，仍會照常以預定執行日開盤價在帳冊判定。"
)

#: 風控 2026-11-01 解讀點 (c), B 句: the same gap next to the symbol's 順延／跳過
#: records ({decision_count} defer or skip lines, rendered for one or more),
#: which are not orders and are never judged at an opening price. After the
#: DATA_GAP sentence and after A when A is there.
SAME_DAY_EARLIER_DECISIONS_DATA_GAP_NOTE = (
    "指令帳冊中 {symbol} 的 {decision_count} 筆順延或跳過紀錄，"
    "是同一預定執行日稍早這檔資料可用時的評估結果；本次未重新評估這檔，"
    "這些紀錄未因此取消或修改。這幾筆不是買賣指令，帳冊不會依開盤價判定成交。"
)

#: 鐵律④ (T5). Never a denial: the change is recorded and dated.
RULE_CHANGE_PENDING = (
    "規則修改已記錄為待生效，生效日 {effective_date}（版本 {version}）；當日不套用。"
)

#: CEO 裁決六: a fast market raises refusal strength, and the refusal states the
#: measurement it was raised on.
FAST_MARKET_REFUSAL_SUFFIX = (
    "目前符合快市條件（20 日年化波動率 {vol}%、"
    "近 {lookback} 交易日有 {moves} 日 |漲跌幅| ≥{move_pct}%）；快市期間規則不放寬。"
)

#: The same statement when the volatility itself is missing. 覆審: an absent
#: volatility may not be rendered as 「—%」 -- the sentence says the threshold was
#: not used at all, so no reader can take a dash for a measurement.
FAST_MARKET_NO_VOL_NOTE = (
    "目前符合快市條件（近 {lookback} 交易日有 {moves} 日 |漲跌幅| ≥{move_pct}%；"
    "20 日年化波動率資料暫缺，本次未採用波動率門檻）；快市期間規則不放寬。"
)

FAST_MARKET_REASON = (
    "20 日年化波動率 {vol}%；近 {lookback} 交易日 |漲跌幅| ≥{move_pct}% 共 {moves} 日。"
)

#: EMERGENCY_EXIT 回報 (覆審定稿). 「已受理」, never 「已執行／已出清」: what the
#: module produced is an instruction, and the fill is the broker's to report.
EMERGENCY_EXIT_RESULT = (
    "EMERGENCY_EXIT 已受理：已產生 {batches} 批、共 {shares} 股的賣出指令，"
    "預定執行日 {execution_date} 開盤以市價單送出，"
    "市價單在跌停或無量時可能無法成交，實際成交結果以你的券商回報為準；"
    "R 系列（新倉進場）自 {executed_at} 起暫停 {freeze_days} 交易日（依交易日曆），"
    "預計 {until} 恢復；S/P 系列停損停利仍照常評估。"
)

EMERGENCY_EXIT_EMPTY = (
    "EMERGENCY_EXIT 已受理：目前無持有批次，未產生賣出指令；"
    "R 系列（新倉進場）自 {executed_at} 起暫停 {freeze_days} 交易日（依交易日曆），"
    "預計 {until} 恢復；S/P 系列停損停利仍照常評估。"
)

#: N-166 風控 S1 (ADR-0033 C-8 second branch): no new line was written because
#: every held batch already carries an earlier, still unsettled EMERGENCY sell.
#: Self-contained on purpose -- the post-submit banner shows no directive rows,
#: and a user whose first response was lost has to learn the earlier lines from
#: this sentence alone. Its 「若你尚未…為準」 clause may not be dropped (EX-2).
EMERGENCY_EXIT_ALREADY_PENDING = (
    "EMERGENCY_EXIT 已受理：本次未產生新的賣出指令。"
    "目前全部 {pending_batches} 批、共 {pending_shares} 股的持有批次，"
    "都已有你先前提交全部出清時產生、尚未結算的賣出指令"
    "（預定執行日 {pending_execution_dates} 開盤以市價單送出）；"
    "這些先前的指令仍然有效，本次未取消、未修改，也未重新產生。"
    "本次回應不是另一筆賣出指令，請勿據此到券商重複下單；"
    "若你尚未依先前的指令下單，以上述 {pending_batches} 批、共 {pending_shares} 股為準。"
    "市價單在跌停或無量時可能無法成交，實際成交結果以你的券商回報為準；"
    "R 系列（新倉進場）自 {executed_at} 起暫停 {freeze_days} 交易日（依交易日曆），"
    "預計 {until} 恢復；S/P 系列停損停利仍照常評估。"
)

#: N-166 風控 S2: appended to :data:`EMERGENCY_EXIT_RESULT` when this
#: submission wrote lines for some batches and others were already covered.
EMERGENCY_EXIT_PENDING_NOTE = (
    "另有 {pending_batches} 批、共 {pending_shares} 股已有你先前提交全部出清時產生、"
    "尚未結算的賣出指令（預定執行日 {pending_execution_dates} 開盤以市價單送出），"
    "本次未重新產生；這些先前的指令仍然有效，請勿就這 {pending_batches} 批到券商重複下單；"
    "若你尚未依先前的指令下單，以這 {pending_batches} 批、共 {pending_shares} 股為準。"
)

#: N-166 風控 S3: appended after S1 or S2 whenever any earlier line's 預定執行日
#: is before the submission day and it is still unsettled.
EMERGENCY_EXIT_PENDING_PAST_DUE_NOTE = (
    "先前的指令中，預定執行日 {past_due_dates} 已過、仍未結算；"
    "本系統不下單，也無法得知你在券商是否已賣出，請以你的券商回報為準。"
)

#: N-166 風控 S10 (CEO #87／#89 判準 Z): appended after [S3] in the RESULT and
#: ALREADY_PENDING branches when a held batch has an unsettled EMERGENCY sell
#: that no longer covers it -- its 預定執行日 has no daily bar while a later day
#: does. Those lines are not cancelled, so they are disclosed, with both
#: branches of what the user may already have done (EX-2, R10).
EMERGENCY_EXIT_STALE_PENDING_NOTE = (
    "另有 {stale_batches} 批的先前出清賣出指令至今未能結算：{stale_items}。"
    "這些指令的預定執行日沒有日線開盤價（可能是該日休市，也可能是資料缺漏），"
    "而之後的交易日已有日線資料，因此本系統不再以這些指令涵蓋上述批次。"
    "先前的這些指令並未被取消；若日後補得該日的開盤價，帳冊仍可能依該日開盤價判定，"
    "但同一批次在帳冊的股數不會重複減少，判定的日期與價格可能與你實際賣出的不同。"
    "本系統不下單，無法得知你是否已就這幾批在券商賣出："
    "若你已賣出且成交（不論是否依先前的指令），你在券商已無這幾批的持股，"
    "本則回應前段所述這幾批的賣出指令不適用於你，請勿就這幾批到券商重複下賣單；"
    "若尚未賣出（包括該日休市、未下單或未成交），以本則回應前段所述的賣出指令為準。"
)

#: One ``{stale_items}`` entry of S10, joined by 「、」 in (symbol, batch_no)
#: order. ``{shares}`` is the batch's ``remaining_shares``, never a sum of lines.
EMERGENCY_EXIT_STALE_ITEM = (
    "{symbol}第 {batch_no} 批 {shares} 股（未能結算的指令預定執行日 {stale_dates}）"
)

#: N-166 風控 S6 (CEO #77): the last sentence of any of the three branches when
#: this submission moved a running freeze later. Decided from the value read
#: under the write lock and the one written in the same transaction; nothing
#: about it is stored (ADR-0033 C-9).
EMERGENCY_EXIT_FREEZE_EXTENDED_NOTE = (
    "因本次再次提交全部出清，R 系列（新倉進場）的預計恢復日由 {previous_until} 延後至 {until}，"
    "暫停交易日數改自 {executed_at} 起重新計算。"
)

#: N-166 風控 S7 (F-c): replaces the freeze clause of all three branches -- from
#: :data:`_FREEZE_CLAUSE_HEAD` to the end -- when the stored 恢復日 is later
#: than the one this submission computes, so the 「自 {executed_at} 起暫停
#: {freeze_days} 交易日」 count would be untrue.
EMERGENCY_EXIT_FREEZE_KEPT_CLAUSE = (
    "R 系列（新倉進場）維持暫停，預計 {until} 恢復"
    "（依交易日曆；沿用先前已設定、較晚的恢復日，本次未縮短）；S/P 系列停損停利仍照常評估。"
)

#: Where the freeze clause starts in RESULT, EMPTY and ALREADY_PENDING alike;
#: S7 replaces everything from here to the end of the template.
_FREEZE_CLAUSE_HEAD = "R 系列（新倉進場）自 {executed_at} 起暫停"

#: EMERGENCY_EXIT 確認畫面的事實核取句, in display order (文案閘門 版本 1 底本 +
#: 覆審定稿 for 2 and the new 4). None of them may be pre-ticked, none may carry
#: a countdown, and the 快市 note may not appear anywhere in this flow -- the
#: exit is the one path with no friction on it (EX-2 / 出口零摩擦).
EXIT_CONFIRM_CHECKS: tuple[str, ...] = (
    "此操作將對目前持有的全部標的、全部批次送出出清指令；"
    "不可只出清部分標的或部分批次，亦不可指定單一標的"
    "（如需針對單一標的停損，請改用該標的的 S 系列規則）。",
    "送出後，R 系列（新倉進場）暫停 {freeze_days} 個交易日"
    "（預計恢復日：{FREEZE_UNTIL}，依交易日曆計算）。",
    "凍結期間內，S／P 系列（停損／停利）仍照常評估；凍結期間仍可再次送出全部出清。",
    "本操作產生的是賣出指令，不是成交：T+1 開盤以市價單送出，跌停或無量時可能無法成交。",
)

#: 四輪收斂裁決, revised by 風控 Q8 (2026-10-31, 1b): what stands in for check 2
#: whenever the page has no usable ``exit_confirm`` block to show -- the response
#: carried none, or ``/today`` is pending, failed on first load, or failed on a
#: background refetch (the stale block is never used). The fact of the freeze is
#: still disclosed before submit; the two numbers are named as missing. It
#: promises only the 預計恢復日 and only in the result of an **accepted**
#: submission: a failed submit has no result, and after the N-166 F-c branch (S7)
#: that result carries ``{until}`` but no day count, so the earlier "兩者於送出後
#: 的執行結果中顯示" was untrue in both cases. Every accepted message (RESULT,
#: EMPTY, S1, S7) carries ``{until}``; that is pinned backend-side. It is never
#: rendered on the normal path, and it does not block the submit -- a missing
#: field may not become a locked door (EX-2 出口零摩擦).
#:
#: The playbook itself never emits this string: the degraded branch is a client
#: state (no block arrived), so the sentence is mirrored by the client and lives
#: here as its single approved source.
EXIT_CONFIRM_FREEZE_DEGRADED = (
    "送出後，R 系列（新倉進場）暫停；本次未能取得暫停交易日數與預計恢復日，"
    "預計恢復日會在受理後的執行結果中顯示。"
)

#: 風控 Q11 (2026-10-31, R-6): the notice the client shows inside the Step 2/3
#: dialog after it replaced a check sentence and, in doing so, cleared at least
#: one tick the user had already made. Rendered **only** in that case -- never on
#: open, never when ``/today`` merely failed, never when a changed sentence had
#: not been ticked, never while a submit is in flight -- so that "有變動的項目已
#: 改為未勾選" is always true. It is a statement of fact, not a precondition: it
#: blocks nothing, and ticking again lets the flow continue (EX-2 / EX-5 / H-1).
#:
#: Like :data:`EXIT_CONFIRM_FREEZE_DEGRADED`, the playbook never emits it; the
#: client mirrors it and this constant is its single approved source.
EXIT_CONFIRM_CHECKS_UPDATED = (
    "核取句已依最新取得的資料更新，有變動的項目已改為未勾選，請重新閱讀後再勾選。"
)

#: N-166 風控 S9: check 2 in place of the standard one **only** when the
#: max rule (CEO #77) keeps a stored 恢復日 later than ``as_of`` shifted by the
#: freeze length, so 「暫停 N 個交易日」 would understate the pause.
EXIT_CONFIRM_FREEZE_KEPT_CHECK = (
    "送出後，R 系列（新倉進場）維持暫停（預計恢復日：{FREEZE_UNTIL}，依交易日曆計算；"
    "沿用先前已設定、較晚的恢復日）。"
)

#: NB-6 出清失敗面板 (N-166 合併後版本, 風控 2026-10-31 已知限制與 NB-6 合併後字面
#: 裁示 第 3 項): the label and paragraphs 1 and 2. Paragraph 3 is
#: :data:`EXIT_RESULT_UNCONFIRMED_RETRY` below (revised by CEO #87 回審). The panel
#: is shown by the client for **every** failed submit -- 5xx, other non-2xx,
#: network failure, unparsable body -- and nothing else is appended to it (no
#: backend text, no status code). It must assert neither 「已處理」 nor 「未處理」:
#: a 500 may land before the write (state i) or after the commit (state iii); the
#: 「只暫停了」 state (ii) no longer exists since the command and the freeze share
#: one transaction (ADR-0033 C-1). 「安全」「放心」 may never appear. Wording is
#: copied verbatim from the ruling; the playbook never emits these strings -- the
#: client mirrors them and these constants are the single approved source.
#: Release-coupled with N-166 like paragraph 3.
#:
#: Paragraph 2 (:data:`EXIT_RESULT_UNCONFIRMED_BADGE`) is the 風控 2026-11-04 第 3 點
#: second version: three sentences, one paragraph -- never split, merged or
#: reordered. It names the N-171 block by :data:`PENDING_EXIT_BLOCK_TITLE`
#: verbatim and scopes it to batches the book still holds, so it may only ship
#: in a build that carries that block, with a backend no older than the client
#: (風控 2026-11-03 上線耦合); its earlier versions may not come back. Replaced
#: atomically with the client mirror and both guard tests (ADR-0039 Decision 13).
#: Re-reviewed when group B ships.
EXIT_RESULT_UNCONFIRMED_LABEL = "無法確認全部出清的處理結果"
EXIT_RESULT_UNCONFIRMED_STATES = (
    "這次送出未取得可確認結果的回應。目前可能尚未處理，也可能已受理："
    "R 系列（新倉進場）已暫停，持有批次也都已有賣出指令。"
)
EXIT_RESULT_UNCONFIRMED_BADGE = (
    "頁面上方的狀態列在重新取得資料後，其模式徽章會顯示 R 系列（新倉進場）目前是否已暫停，"
    "但不會顯示賣出指令；若這次送出前 R 系列就已暫停，徽章也無法顯示這次是否已受理。"
    "重新取得資料後，"
    "排程台上的「全部出清產生、尚未結算的賣出指令」區塊會列出所屬批次在帳冊仍記為持有、"
    "尚未結算的出清賣出指令；若這次送出前就已有這類指令，該區塊也無法顯示這次是否已受理。"
    "該區塊沒有出現或未列出某一批，不代表這次未受理：例如沒有持有批次時不會產生賣出指令，"
    "指令結算後、或所屬批次在帳冊已不再記為持有時，也不再列於該區塊。"
)

#: NB-6 出清失敗面板 第 3 段，N-166 合併後版本 as revised by 風控 2026-10-31
#: (CEO #87 回審): once 判準 Z can write a second line for a batch, 「不會再重複
#: 產生」 needs its exception stated, or the sentence implies re-sending is
#: always without effect. The paragraph's two sentences are one unit -- never
#: split, merged, trimmed or reordered -- and 「安全」「放心」 may never appear.
#:
#: Release-coupled (風控 硬性條件): only in a build that carries 判準 Z. The client
#: mirror and its guard test belong to the 出清畫面包 (N-164/N-165/N-170, PRD
#: FR-8b／FR-11); this constant is the approved single source the mirror is
#: checked against.
EXIT_RESULT_UNCONFIRMED_RETRY = (
    "你可以再次送出：已有尚未結算之出清賣出指令的持有批次，不會再重複產生賣出指令，"
    "除非該指令的預定執行日沒有日線開盤價、且之後的交易日已有日線資料，"
    "這時會為該批次另行產生賣出指令；但再次送出可能延後 R 系列（新倉進場）的預計恢復日。"
    "再次送出若取得回應，回應會說明該次的處理結果，包括先前已有、尚未結算的賣出指令。"
)

#: N-171 群組 A: the pending-exit block on ``/today`` (ADR-0039 Decision 1, 4, 5;
#: 補充一 S-1, S-2). Verbatim from 風控 2026-11-03 第二節之 2 (A-1, A-3～A-9,
#: A-11～A-14) and 風控 2026-11-04 (A-2 revised, A-15); A-10 is the existing
#: :data:`EMERGENCY_EXIT_STALE_ITEM`. The service composes the block in the fixed
#: order and the client renders it as given -- it never reorders, filters or
#: writes text of its own:
#:
#: * authored: A-1 → A-2 →［A-7］→ A-3 → covering rows (A-5 ＋［A-6］＋［A-15］)
#:   →［A-8 → A-9 → stale rows (STALE_ITEM ＋ A-11 or A-12 ＋［A-15］)］→ A-14;
#: * unauthored: A-1 → A-2 → A-4 → rows (A-5 ＋［A-6］＋［A-15］) → A-13 → A-14.
#:
#: ``{read_at}`` in A-2 is left in place: the client substitutes
#: ``formatDateTime(as_of)`` of the same response, exactly once (P-8). 「建議」
#: appears only in A-2's attribution negation 「非本系統的判斷或建議」 (allowlisted).

#: A-1, the block's title. NB-6 paragraph 2 names the block by this exact text.
PENDING_EXIT_BLOCK_TITLE = "全部出清產生、尚未結算的賣出指令"
#: A-2 (風控 2026-11-04 revision): always rendered with the block, before every row.
PENDING_EXIT_BLOCK_LEAD = (
    "本區塊依 {read_at} 讀取的紀錄，列出你先前提交「全部出清」時產生、帳冊尚未結算，"
    "且所屬批次在帳冊仍記為持有的賣出指令；這些指令是該要求的機械執行結果，"
    "非本系統的判斷或建議。它們不由規則集產生，不列入指令帳冊，"
    "也不是依本頁面所載收盤資料重新計算的結果；"
    "本頁其他說明若提到指令帳冊中的指令或未產生指令，不包括本區塊的指令。"
    "所屬批次在帳冊已不再記為持有的出清賣出指令，即使尚未結算，也不列入本區塊；"
    "未列入不代表該指令已經結算或被取消，也不代表你在券商已賣出這批。本系統不下單，"
    "無法得知你是否已依出清賣出指令在券商下單或成交，實際持股以你的券商回報為準。"
)
#: A-3: the covering section's lead (authored path, one covering row or more).
PENDING_EXIT_COVERED_LEAD = (
    "下列指令仍涵蓋所列批次。若你已依這些指令在券商賣出且成交，你在券商已無這幾批的持股，"
    "請勿就同一批到券商重複下賣單；若你在券商仍持有這幾批而尚未賣出（包括未下單或未成交），"
    "以下列批次與股數為準。市價單在跌停或無量時可能無法成交，"
    "實際成交結果以你的券商回報為準。"
)
#: A-4: the only lead of the unauthored path, whose rows are not classified.
PENDING_EXIT_UNCLASSIFIED_LEAD = (
    "若你已依下列指令在券商賣出且成交，你在券商已無這幾批的持股，"
    "請勿就同一批到券商重複下賣單；若你在券商仍持有這幾批而尚未賣出（包括未下單或未成交），"
    "以下列批次與股數為準。市價單在跌停或無量時可能無法成交，"
    "實際成交結果以你的券商回報為準。"
)
#: A-5: a covering or unclassified row; ``{shares}`` is the batch's ``remaining_shares``.
PENDING_EXIT_ITEM = (
    "{symbol}第 {batch_no} 批賣出 {shares} 股（預定執行日 {execution_dates} 開盤以市價單送出）"
)
#: A-6: on a covering or unclassified row when :func:`app.playbook.service.exit_row_past_due`.
PENDING_EXIT_PAST_DUE_NOTE = (
    "預定執行日 {past_due_dates} 已過、仍未結算；本系統不下單，"
    "也無法得知你在券商是否已賣出這批，請以你的券商回報為準。"
)
#: A-7: the covering section's label, only when the stale section is there too.
PENDING_EXIT_COVERED_LABEL = "仍涵蓋所列批次的指令"
#: A-8: the stale section's label (authored path only).
PENDING_EXIT_STALE_LABEL = "已不再涵蓋該批次、仍未結算的先前指令"
#: A-9: the stale section's lead.
PENDING_EXIT_STALE_LEAD = (
    "下列先前的出清賣出指令至今未能結算：其預定執行日沒有日線開盤價（可能是該日休市，"
    "也可能是資料缺漏），而之後的交易日已有日線資料，因此本系統不再以這些指令涵蓋所列批次。"
    "這些指令並未被取消；若日後補得該日的開盤價，帳冊仍可能依該日開盤價判定，"
    "但同一批次在帳冊的股數不會重複減少，判定的日期與價格可能與你實際賣出的不同。"
    "本系統不下單，無法得知你是否已就這幾批在券商賣出："
    "若你已賣出且成交（不論是否依先前的指令），你在券商已無這幾批的持股，"
    "本區塊所列這幾批的賣出指令都不適用於你，請勿就這幾批到券商重複下賣單；"
    "若尚未賣出（包括該日休市、未下單或未成交），見各列的說明。"
)
#: A-11: on a stale row whose batch also has a covering line.
PENDING_EXIT_STALE_ALSO_COVERED_NOTE = (
    "這批另有上列仍涵蓋的賣出指令；若你在券商仍持有這批而尚未賣出，以上列該批的賣出指令為準。"
)
#: A-12: on a stale row whose batch has no covering line.
PENDING_EXIT_STALE_UNCOVERED_NOTE = (
    "這批目前沒有仍涵蓋它的出清賣出指令，帳冊仍記為持有；若你在券商仍持有這批而尚未賣出，"
    "可再次提交全部出清，替這批產生新的賣出指令。"
)
#: A-13: closes the unauthored path's rows, before A-14.
PENDING_EXIT_UNAUTHORED_NOTE = (
    "目前尚無你本人的規則集設定或修改紀錄，本頁不執行結算，也不載入日線資料："
    "在你確認規則集之前，帳冊不會依預定執行日開盤價判定上列指令，它們會持續列在本區塊；"
    "本頁也無法判斷其中是否有因預定執行日沒有日線開盤價、已不再涵蓋該批次的指令。"
    "本頁其他說明若提到你目前持有某檔、尚未出清，是指帳冊尚未結算上列指令而仍記為持有，"
    "不是指上列指令未產生，也不代表你在券商的持股狀態。"
)
#: A-14: always the block's last sentence; never decided from the receipt store.
PENDING_EXIT_RECEIPT_OVERLAP_NOTE = (
    "本頁若同時顯示以「EMERGENCY_EXIT 已受理」開頭的說明，其中所述、"
    "尚未結算的賣出指令與本區塊所列的是同一組指令，不是另外一組。"
)
#: A-15 (風控 2026-11-04 第 4 點, required): on any row one of whose lines asks for
#: more shares than the batch still holds (:func:`app.playbook.service.exit_row_shares_reduced`).
PENDING_EXIT_SHARES_REDUCED_NOTE = (
    "這批在出清賣出指令產生之後，帳冊又依其他賣出指令（例如停損、停利）判定賣出一部分，"
    "因此上列股數是帳冊目前仍記為持有的股數，少於這批出清賣出指令產生時所列的股數。"
    "本系統不下單，無法得知你是否已依那些其他賣出指令在券商賣出：若已賣出且成交，"
    "上列股數已扣除那部分；若未下單或未成交，你在券商的這批持股可能多於上列股數，"
    "多出的股數不在帳冊內，S/P 系列不會評估它們的停損停利，再次提交全部出清也不會涵蓋它們，"
    "實際持股以你的券商回報為準。"
)

#: T+1 結算 (CEO 裁決七). A line is settled against the 預定執行日's opening
#: price; without that price the line stays pending and is named, never guessed.
SETTLEMENT_NO_OPEN_PRICE = (
    "{symbol} 預定執行日 {execution_date} 尚無日線開盤價（資料狀態 {status}／來源 {source}），"
    "本筆未結算，維持待結算狀態。"
)
SETTLEMENT_SUMMARY = (
    "T+1 結算：依 {settled_on} 開盤價判定，成交 {executed} 筆、"
    "未成交（MISSED）{missed} 筆、未結算 {pending} 筆；"
    "實際成交結果以你的券商回報為準。"
)
SETTLEMENT_NOTHING_PENDING = "T+1 結算：目前沒有待結算指令。"

#: N171-C17′ (ADR-0039 補充一 S-3; 風控 2026-11-04 第 2 點, 逐字定稿): the one
#: warning of ``POST /api/playbook/settle`` while no user rule set exists. Only
#: :meth:`app.playbook.service.PlaybookService.settle_on_request` returns it, and
#: alone -- never with :data:`SETTLEMENT_NOTHING_PENDING` or
#: :data:`SETTLEMENT_SUMMARY`. ``/today`` never carries it: its unauthored path
#: keeps ``settlement=None``. Re-reviewed with A-13 if N-175 ever settles while
#: unauthored, or authorship gains a true→false path (補充一 S-6).
SETTLEMENT_UNAUTHORED_NOTE = (
    "T+1 結算：目前尚無你本人的規則集設定或修改紀錄，本次未執行結算，也未載入日線資料；"
    "本回應的成交筆數與未成交（MISSED）筆數為 0、已結算與未結算清單皆為空，"
    "是因為未執行結算，不代表目前沒有待結算指令。若你先前提交全部出清時已產生賣出指令，"
    "在你確認規則集之前，帳冊不會依預定執行日開盤價判定它們，它們維持待結算狀態。"
    "本系統不下單，無法得知你是否已在券商下單或成交，實際持股以你的券商回報為準。"
)

#: N-166 風控 N1 (CEO #87): appended to :data:`SETTLEMENT_NO_OPEN_PRICE` for an
#: unsettled EMERGENCY sell that meets 判準 Z while its batch is closed or has a
#: later EMERGENCY sell -- the line otherwise reads 「賣出 N 股、待結算」 day
#: after day. ``{batch_clause}`` takes one of the two values below only.
SETTLEMENT_EXIT_STALE_NOTE = (
    "這筆是先前全部出清產生的賣出指令，之後的交易日已有日線資料，本筆仍無法依該日開盤價結算；"
    "帳冊中這一批{batch_clause}，同一批次在帳冊的股數不會因這些賣出指令重複減少。"
    "本系統不下單，無法得知你是否已就這批在券商賣出："
    "若已賣出且成交，你在券商已無這批的持股，請勿再依本筆到券商下賣單；"
    "若尚未賣出，實際持股以你的券商回報為準。"
)
SETTLEMENT_EXIT_STALE_CLOSED = "已無持股"
SETTLEMENT_EXIT_STALE_LATER = "另有預定執行日 {later_dates} 的出清賣出指令"

#: N-166 風控 N1b (suggested, approved): the same line while its batch is still
#: held and no later EMERGENCY sell exists -- re-submitting the exit is what
#: opens the door again (EX-3). 「可」 only (D7).
SETTLEMENT_EXIT_STALE_REOPEN_NOTE = (
    "這批在帳冊仍記為持有；可再次提交全部出清，替這批產生新的賣出指令。"
)

#: N-166 風控 N2: right after :data:`SETTLEMENT_SUMMARY` when an EMERGENCY sell
#: judged executed found its batch already holding nothing, so the book moved
#: no shares and no cash for it (``{exit_items}`` per :data:`SETTLEMENT_EXIT_ITEM`).
SETTLEMENT_EXIT_NOTHING_MOVED_NOTE = (
    "本次判定成交的出清賣出指令中，有 {count} 筆在判定時該批次在帳冊已無持股，"
    "帳冊股數與現金都未因這幾筆變動：{exit_items}。"
    "帳冊中這幾批只依另一筆賣出指令減少一次股數，判定的日期與價格可能與你實際賣出的不同；"
    "實際成交結果以你的券商回報為準。"
)
SETTLEMENT_EXIT_ITEM = "{symbol}第 {batch_no} 批（預定執行日 {execution_date}）"

#: G1 (ADR-0035 Decision 6′, CEO #88; 風控 CEO #87 回審 二-2): the ``unsettled``
#: reason of a buy whose 預定執行日 has its opening price but whose batch is no
#: longer ``planned``, so the book does not fill it. Replaces
#: :data:`SETTLEMENT_NO_OPEN_PRICE` for that line. ``{batch_state}`` takes one
#: of :data:`SETTLEMENT_BATCH_STATES` only; a ``planned`` batch never renders it.
SETTLEMENT_BATCH_ALREADY_FILLED_NOTE = (
    "{symbol}第 {batch_no} 批買進 {shares} 股（規則 {rule_id}，"
    "預定執行日 {execution_date}）：該日已有日線開盤價，"
    "但帳冊中這一批目前{batch_state}，不是待買進狀態，"
    "帳冊不會依本筆判定成交，股數與現金都未因本筆變動；本筆未結算，維持待結算狀態，"
    "之後的結算會繼續列出。本系統不下單，無法得知你是否已依本筆在券商買進："
    "若已買進且成交，你在券商的這檔持股可能多於帳冊所記，多出的股數不在帳冊內，"
    "S/P 系列不會評估它們的停損停利，全部出清也不會涵蓋它們，"
    "實際持股以你的券商回報為準；若未下單或未成交，帳冊不受本筆影響。"
)

#: The three ``{batch_state}`` values, by batch status.
SETTLEMENT_BATCH_STATES: dict[BatchStatus, str] = {
    "open": "已記為持有",
    "closed": "已記為持有後全數賣出",
    "skipped": "已被跳過",
}

#: 季末 REBALANCE (CEO 裁決一 / 風控 D-1).
REBALANCE_RESULT = (
    "季末 REBALANCE 已執行：總資產 {assets}，TOTAL_DEPLOY 由 {previous} 重算為 {new}"
    "（總資產 ×{ratio}%）。"
)
REBALANCE_OVERSHOOT_WARNING = (
    "【超額】目前部位市值 {deployed} 已超過新的 TOTAL_DEPLOY {new}，超額 {overshoot}；"
    "本規則集沒有自動減碼條款，超額部位不會被系統處分，處理方式須由使用者以書面規則修改提交。"
)
#: The REBALANCE line is a statement, not an order -- said on the line itself.
REBALANCE_NO_ORDER_NOTE = (
    "本列為季末資金重算紀錄，不是下單指令；不會產生買賣，執行日與參考價欄位不適用。"
)
REBALANCE_BLOCKED = (
    "季末 REBALANCE 未執行：{symbols} 沒有可用收盤價，總資產無法核算；"
    "依鐵律⑤不以缺漏資料重算 TOTAL_DEPLOY。"
)

MODE_REASON_NORMAL = "正常模式：M1 未觸發，組合未凍結。"
MODE_REASON_DEFENSE = "防守模式：指數收盤低於月線連續 {days} 日（M1）。"
MODE_REASON_FROZEN = "全凍結：{reason}，凍結至 {until}。"

#: 覆審: the day counter lives here and is recomputed on every render from the
#: trading calendar. It is never stored as part of a message, because a stored
#: 「第 3/20 交易日」 is wrong on day four.
MODE_REASON_EMERGENCY = (
    "緊急出清後凍結：R 系列（新倉進場）暫停中"
    "（第 {frozen_day}/{freeze_days} 交易日，依交易日曆），預計 {until} 恢復；"
    "S/P 系列停損停利仍照常評估。"
)

#: N-166 風控 S8: the mode line without the day counter, used **only** while
#: more than ``freeze_days + 1`` trading days remain to the 恢復日 (風控
#: 2026-10-31 第二次裁示; a stored later date kept by the max rule, or data two
#: or more sessions behind). The counter would clamp to 「第 1/N」 for days on
#: end there, which is untrue; this is 風控's one exception to VETO-4. See
#: :func:`app.playbook.engine.emergency_mode_reason`.
MODE_REASON_EMERGENCY_UNCOUNTED = (
    "緊急出清後凍結：R 系列（新倉進場）暫停中，預計 {until} 恢復（依交易日曆）；"
    "S/P 系列停損停利仍照常評估。"
)


def _format_shares(shares: int) -> str:
    return f"{shares:,}"


def _format_price(price: Decimal | None) -> str:
    return "—" if price is None else f"{price:.2f}"


def _threshold(value: Decimal | float | int) -> str:
    """A comparison threshold as the rule set writes it (``3``, ``-8``, ``15``)."""
    return f"{value:g}"


def _ratio(value: Decimal) -> str:
    """A cost multiplier as the rule set writes it (``0.90``, ``1.20``)."""
    return f"{value:.2f}"


def ratio_pct(value: Decimal) -> str:
    """A ratio field written as the percentage the sentence shows (``0.30`` -> ``30``).

    Public because :mod:`app.playbook.service` renders the same percentage into
    ``REBALANCE_RESULT``; a caller outside this module reaching for a private
    name is a review finding, not a convention (qa low, 2026-08-12).

    ``Decimal`` keeps the scale of the multiplication (``0.30 × 100`` is
    ``30.00``), which would put trailing zeros the rule set does not write into
    the sentence, so the scale is dropped here.
    """
    scaled = value * 100
    integral = scaled.to_integral_value()
    return _threshold(integral if scaled == integral else scaled.normalize())


def _rule_text_values(params: RuleParams) -> dict[str, str]:
    """Placeholder -> threshold of the active parameter version.

    Each key is either a :class:`RuleParams` field name or the name 風控 fixed in
    the approved sentence (``blacklist_days``, ``freeze_days``); the percentage
    placeholders render the ratio field they are bound to. Nothing here may be a
    literal, so a dated rule change moves every restatement with it.
    """
    return {
        "r2_change_pct_limit": _threshold(params.r2_change_pct_limit),
        "r2_bias_limit": _threshold(params.r2_bias_limit),
        "r3_max_defers": _threshold(params.r3_max_defers),
        "s1_ratio": _ratio(params.s1_ratio),
        "s1_defense_ratio": _ratio(params.s1_defense_ratio),
        "s2_ratio": _ratio(params.s2_ratio),
        # 覆審 named this placeholder {blacklist_days}; it is s2_blacklist_trading_days.
        "blacklist_days": _threshold(params.s2_blacklist_trading_days),
        "s3_unrealized_pct": _threshold(params.s3_unrealized_pct),
        "s3_freeze_trading_days": _threshold(params.s3_freeze_trading_days),
        "p1_ratio": _ratio(params.p1_ratio),
        "p2_ratio": _ratio(params.p2_ratio),
        "p2_trailing_peak_ratio": _ratio(params.p2_trailing_peak_ratio),
        "p3_bias_limit": _threshold(params.p3_bias_limit),
        "p3_bias_limit_high_vol": _threshold(params.p3_bias_limit_high_vol),
        "p3_cooldown_trading_days": _threshold(params.p3_cooldown_trading_days),
        "m1_consecutive_days": _threshold(params.m1_consecutive_days),
        "cash_floor_ratio": ratio_pct(params.cash_floor_ratio),
        # 覆審 named this placeholder {freeze_days}; it is
        # emergency_freeze_trading_days.
        "freeze_days": _threshold(params.emergency_freeze_trading_days),
        "deploy_ratio": ratio_pct(params.deploy_ratio),
    }


def rule_text(rule_id: str, params: RuleParams) -> str:
    """One rule's restatement, with the thresholds of the version in force."""
    return RULE_TEXT[rule_id].format(**_rule_text_values(params))


def attribution_note(authorship: RuleSetAuthorship) -> str:
    """The 歸屬語 for one response (風控 R2), or the 情境 1 blocking sentence.

    Three branches, exactly as 覆審 defined them: the full sentence with the
    rule set's effective date; the same sentence with the date replaced by the
    one permitted status string; and -- when there is no user record at all --
    the blocking sentence *instead of* the 歸屬語, never a shortened version of
    it.

    EMERGENCY_EXIT does not come through here at all (三輪定稿 題 7): it carries
    :data:`EXIT_ATTRIBUTION` whatever the authorship record says.
    """
    if not authorship.user_authored:
        return ATTRIBUTION_NO_USER_RULES
    if authorship.rule_set_date is None:
        status = ATTRIBUTION_DATE_STATUS_UNREADABLE.format(version=authorship.version)
        return ATTRIBUTION_NOTE_DATE_MISSING.format(RULE_SET_DATE_STATUS=status)
    return ATTRIBUTION_NOTE.format(RULE_SET_DATE=authorship.rule_set_date.isoformat())


def page_summary(
    *,
    data_date: date,
    rules_version: int,
    rules_effective_date: date | None,
    user_authored: bool | None,
) -> list[str]:
    """§6 頁面免責句, the three sentences in their fixed order (題 11).

    Sentence ② has the three branches the ruling defined and is decided by
    ``user_authored`` -- the explicit authorship record, never a date:

    * ``False`` -> (c), the first sentence of :data:`ATTRIBUTION_NO_USER_RULES`.
    * ``True`` with a readable in-force 生效日 -> (a).
    * anything else, **including an undeterminable authorship** -> (b),
      fail-closed. (b) says the date could not be read, which is the weaker of
      the two claims; (a) would assert a 生效日 that is not in evidence.
    """
    if user_authored is False:
        rules_sentence = ATTRIBUTION_NO_USER_RULES_FIRST
    elif user_authored is True and rules_effective_date is not None:
        rules_sentence = PAGE_SUMMARY_RULES.format(
            rules_version=rules_version,
            rules_effective_date=rules_effective_date.isoformat(),
        )
    else:
        rules_sentence = PAGE_SUMMARY_RULES_UNREADABLE.format(version=rules_version)
    return [
        PAGE_SUMMARY_DATA_DATE.format(data_date=data_date.isoformat()),
        rules_sentence,
        PAGE_SUMMARY_ATTRIBUTION,
    ]


def exit_confirm_checks(
    *, freeze_days: int, freeze_until: date, freeze_kept: bool = False
) -> tuple[str, ...]:
    """The EMERGENCY_EXIT confirmation checks, with the dates of this run filled.

    Returned as data so the confirmation screen renders the approved sentences
    and cannot compose its own. ``freeze_kept`` is the F-c case (風控 S9): the
    恢復日 is a stored, later one the exit will keep, so check 2 states that
    instead of a day count that would understate the pause.
    """
    checks = list(EXIT_CONFIRM_CHECKS)
    if freeze_kept:
        checks[1] = EXIT_CONFIRM_FREEZE_KEPT_CHECK
    return tuple(
        check.format(freeze_days=freeze_days, FREEZE_UNTIL=freeze_until.isoformat())
        for check in checks
    )


def date_list(days: Iterable[date]) -> str:
    """De-duplicated, ascending ISO dates joined by 「、」 (風控 N-166 佔位符定義)."""
    return "、".join(day.isoformat() for day in sorted(set(days)))


def freeze_kept_template(template: str) -> str:
    """``template`` with its freeze clause swapped for S7 (風控 F-c).

    Raises rather than appending when the clause is not found: a template that
    lost it would otherwise state both freezes at once.
    """
    head, found, _ = template.partition(_FREEZE_CLAUSE_HEAD)
    if not found:
        raise ValueError("template has no EMERGENCY_EXIT freeze clause to replace")
    return head + EMERGENCY_EXIT_FREEZE_KEPT_CLAUSE


class ExitStale(NamedTuple):
    """One held batch with earlier EMERGENCY lines that no longer cover it (S10).

    ``shares`` is the batch's ``remaining_shares``; ``dates`` are the 預定執行日
    of every such line of the batch.
    """

    symbol: str
    batch_no: int
    shares: int
    dates: tuple[date, ...]


class ExitPending(NamedTuple):
    """The earlier, still unsettled EMERGENCY lines one exit response describes.

    ``batches`` / ``shares`` count the covered **batches** -- de-duplicated by
    ``(symbol, batch_no)``, shares from their ``remaining_shares`` -- never the
    lines: a database written before N-166 can hold two lines for one batch,
    and adding their shares would double the figure again (風控 佔位符定義).

    ``execution_dates`` / ``past_due_dates`` are the opposite: taken from
    **every** line that still covers its batch under 判準 Z, so two such lines
    with two 預定執行日 both show, and a past-due one is never hidden behind a
    later twin (風控 第二次裁示 第 2 項, narrowed by the CEO #87 回審). A line
    that no longer covers is never listed here; it is in ``stale`` and S10
    discloses it, so S3 and S10 never speak about the same line.
    :func:`date_list` de-duplicates the dates for the sentence.
    """

    batches: int
    shares: int
    execution_dates: tuple[date, ...]
    past_due_dates: tuple[date, ...]
    stale: tuple[ExitStale, ...] = ()


def stale_items(stale: Iterable[ExitStale]) -> str:
    """S10 ``{stale_items}``: one entry per batch, (symbol, batch_no) ascending."""
    return "、".join(
        EMERGENCY_EXIT_STALE_ITEM.format(
            symbol=item.symbol,
            batch_no=item.batch_no,
            shares=item.shares,
            stale_dates=date_list(item.dates),
        )
        for item in sorted(stale, key=lambda item: (item.symbol, item.batch_no))
    )


def emergency_exit_message(
    *,
    new_batches: int,
    new_shares: int,
    execution_date: date,
    executed_at: date,
    freeze_days: int,
    until: date,
    pending: ExitPending,
    extended_from: date | None,
    freeze_kept: bool,
) -> str:
    """The EMERGENCY_EXIT message, composed in the order 風控 fixed (N-166).

    * RESULT 支 (lines written now): RESULT ＋［S2］＋［S3］＋［S10］＋［S6］
    * ALREADY_PENDING 支 (none written, some covered): S1 ＋［S3］＋［S10］＋［S6］
    * EMPTY 支 (nothing held): EMPTY ＋［S6］ -- S10 needs a held batch, so never here.

    (The W-B7／W-B1／W-B1p slots 風控 placed between S10 and S6 belong to N-168.)

    ``extended_from`` is the 恢復日 read under the lock when this submission
    moved a running freeze later (S6), else ``None``. ``freeze_kept`` is F-c: a
    stored, later 恢復日 was kept, and the freeze clause becomes S7. The two
    cannot both hold -- a kept date did not move.
    """
    if new_batches:
        template = EMERGENCY_EXIT_RESULT
    elif pending.batches:
        template = EMERGENCY_EXIT_ALREADY_PENDING
    else:
        template = EMERGENCY_EXIT_EMPTY
    if freeze_kept:
        template = freeze_kept_template(template)
    pending_dates = date_list(pending.execution_dates)
    message = template.format(
        batches=new_batches,
        shares=new_shares,
        execution_date=execution_date.isoformat(),
        executed_at=executed_at.isoformat(),
        freeze_days=freeze_days,
        until=until.isoformat(),
        pending_batches=pending.batches,
        pending_shares=pending.shares,
        pending_execution_dates=pending_dates,
    )
    if new_batches and pending.batches:
        message += EMERGENCY_EXIT_PENDING_NOTE.format(
            pending_batches=pending.batches,
            pending_shares=pending.shares,
            pending_execution_dates=pending_dates,
        )
    if pending.batches and pending.past_due_dates:
        message += EMERGENCY_EXIT_PENDING_PAST_DUE_NOTE.format(
            past_due_dates=date_list(pending.past_due_dates)
        )
    if (new_batches or pending.batches) and pending.stale:
        message += EMERGENCY_EXIT_STALE_PENDING_NOTE.format(
            stale_batches=len({(item.symbol, item.batch_no) for item in pending.stale}),
            stale_items=stale_items(pending.stale),
        )
    if extended_from is not None:
        message += EMERGENCY_EXIT_FREEZE_EXTENDED_NOTE.format(
            previous_until=extended_from.isoformat(),
            until=until.isoformat(),
            executed_at=executed_at.isoformat(),
        )
    return message


def emergency_exit_attribution(
    *, new_batches: int, pending_batches: int, stale_batches: int
) -> str | None:
    """Which 歸屬語 an EMERGENCY_EXIT response carries (風控 N-166 對應).

    RESULT 支 without earlier lines -> :data:`EXIT_ATTRIBUTION`; RESULT 支 that
    also describes earlier lines -- covering ones (S2) **or** ones S10 discloses
    -> S5 (CEO #87 回審); ALREADY_PENDING 支 -> S4; EMPTY 支 -> ``None``, because
    no line exists for the sentence to be about.
    """
    if new_batches:
        if pending_batches or stale_batches:
            return EXIT_ATTRIBUTION_MIXED
        return EXIT_ATTRIBUTION
    if pending_batches:
        return EXIT_ATTRIBUTION_PRIOR
    return None


def directive_line(directive: Directive) -> str:
    """The one-line rendering of a directive: 動作／股數／規則／依據資料日.

    Provenance is part of the line, not an expandable detail: 依據資料日,
    預定執行日 and 參考價 always appear (CEO 裁決七 / 風控 R1, R17), and the
    reference price carries what it is *not* (:data:`REFERENCE_PRICE_NOTE`) so no
    reader can take it for a live intraday quote. With no reference price at all
    the line says so (:data:`REFERENCE_PRICE_UNAVAILABLE_NOTE`) rather than
    qualifying a price it does not have.
    """
    action = ACTION_LABELS[directive.action]
    shares = f"{_format_shares(directive.shares)} 股" if directive.shares else "—"
    batch = "" if directive.batch_no is None else f"第 {directive.batch_no} 批"
    head = f"{directive.symbol}{batch}"
    price_note = (
        REFERENCE_PRICE_UNAVAILABLE_NOTE
        if directive.reference_price is None
        else REFERENCE_PRICE_NOTE
    )
    return (
        f"{head}｜{action}｜{shares}｜規則 {directive.rule_id}"
        f"｜依據資料日 {directive.data_date.isoformat()}"
        f"｜預定執行日 {directive.execution_date.isoformat()}"
        f"｜參考價 {_format_price(directive.reference_price)}{price_note}"
    )


def limit_band_note(reference: Decimal, low: Decimal, high: Decimal, pct: Decimal) -> str:
    return LIMIT_BAND_NOTE.format(
        low=_format_price(low),
        high=_format_price(high),
        reference=_format_price(reference),
        pct=f"{pct:g}",
    )


def mode_reason_frozen(reason: str, until: date) -> str:
    return MODE_REASON_FROZEN.format(reason=reason, until=until.isoformat())


def mode_reason_emergency(*, frozen_day: int, freeze_days: int, until: date) -> str:
    """The EMERGENCY_EXIT mode line, counted for the day it is rendered on."""
    return MODE_REASON_EMERGENCY.format(
        frozen_day=frozen_day, freeze_days=freeze_days, until=until.isoformat()
    )


def mode_reason_emergency_uncounted(*, until: date) -> str:
    """S8: the EMERGENCY_EXIT mode line with no counter (風控 N-166 F-c only)."""
    return MODE_REASON_EMERGENCY_UNCOUNTED.format(until=until.isoformat())


def fast_market_note(*, vol: float | None, lookback: int, moves: int, move_pct: Decimal) -> str:
    """快市 statement appended to a refusal, with or without the volatility half."""
    if vol is None:
        return FAST_MARKET_NO_VOL_NOTE.format(
            lookback=lookback, moves=moves, move_pct=_threshold(move_pct)
        )
    return FAST_MARKET_REFUSAL_SUFFIX.format(
        vol=f"{vol:.1f}", lookback=lookback, moves=moves, move_pct=_threshold(move_pct)
    )


def fast_market_reason(*, vol: float | None, lookback: int, moves: int, move_pct: Decimal) -> str:
    """The measurement a 快市 verdict was reached on.

    With no volatility reading the full statement is used instead of the
    two-clause one, because the missing half has to be said rather than dashed
    out (覆審: vol 不可得時禁「—%」).
    """
    if vol is None:
        return FAST_MARKET_NO_VOL_NOTE.format(
            lookback=lookback, moves=moves, move_pct=_threshold(move_pct)
        )
    return FAST_MARKET_REASON.format(
        vol=f"{vol:.1f}", lookback=lookback, moves=moves, move_pct=_threshold(move_pct)
    )

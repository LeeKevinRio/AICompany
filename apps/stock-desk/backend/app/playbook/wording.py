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

from datetime import date
from decimal import Decimal

from app.playbook.models import Action, Directive, Mode, RuleParams, RuleSetAuthorship

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
    "目前使用的是系統預設規則集，尚無你本人的設定或修改紀錄。"
    "本模組僅依你設定的規則集產生進場、停損、停利指令，"
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
        "R2 不追價煞車：當日漲幅 >{r2_change_pct_limit}% 或 "
        "BIAS25 >+{r2_bias_limit}% 時順延該批。"
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
        "M1 大盤總開關：指數收盤低於月線連續 {m1_consecutive_days} 日進入防守模式，"
        "站回月線解除。"
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
    "停損指令不設滑價帶，T+1 開盤以市價單送出；"
    "市價單在跌停或無量時可能無法成交。"
)

#: EMERGENCY_EXIT lines are not stop-loss lines and no longer borrow that
#: sentence (覆審: service.py 不得再掛停損句).
EMERGENCY_EXIT_NO_BAND_NOTE = (
    "EMERGENCY_EXIT 指令不設滑價帶，T+1 開盤以市價單送出；"
    "市價單在跌停或無量時可能無法成交。"
)

#: 風控 R17: every reference price says which trading day it came from and what
#: it does not include. Appended to the rendered directive line.
REFERENCE_PRICE_NOTE = "（依據交易日收盤價，不反映今日盤中變動）"

#: R17 空價分支: with no reference price there is no trading day to disclose, so
#: the line says the price is absent instead of qualifying one that is not there.
REFERENCE_PRICE_UNAVAILABLE_NOTE = "（無可用參考價）"

#: 資料缺漏 (鐵律⑤ / 風控 R6): the symbol produces no line at all that day.
DATA_GAP_NOTE = "{symbol} 資料狀態為 {status}（來源 {source}），依鐵律⑤當日不產生指令。"

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
    "加權指數資料狀態為 {status}（來源 {source}），M1 今日未評估、沿用前一狀態；"
    "當日不新開倉。"
)

#: Rendered only when the R series was actually deferred today (index_gap_defer).
INDEX_DATA_GAP_DEFER_NOTE = (
    "今日為排程日，R 系列進場改為順延並計入順延次數（逐批列示）。"
)

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


def exit_confirm_checks(*, freeze_days: int, freeze_until: date) -> tuple[str, ...]:
    """The EMERGENCY_EXIT confirmation checks, with the dates of this run filled.

    Returned as data so the confirmation screen renders the approved sentences
    and cannot compose its own.
    """
    return tuple(
        check.format(freeze_days=freeze_days, FREEZE_UNTIL=freeze_until.isoformat())
        for check in EXIT_CONFIRM_CHECKS
    )


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


def fast_market_note(
    *, vol: float | None, lookback: int, moves: int, move_pct: Decimal
) -> str:
    """快市 statement appended to a refusal, with or without the volatility half."""
    if vol is None:
        return FAST_MARKET_NO_VOL_NOTE.format(
            lookback=lookback, moves=moves, move_pct=_threshold(move_pct)
        )
    return FAST_MARKET_REFUSAL_SUFFIX.format(
        vol=f"{vol:.1f}", lookback=lookback, moves=moves, move_pct=_threshold(move_pct)
    )


def fast_market_reason(
    *, vol: float | None, lookback: int, moves: int, move_pct: Decimal
) -> str:
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

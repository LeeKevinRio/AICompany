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

The 歸屬語 (R2, a standing sentence naming the user as the author of the rules)
is **not** wired into any response yet: creative-lead drafts it and
risk-compliance signs it off. :data:`ATTRIBUTION_NOTE_TODO` holds the slot so
the gap is visible rather than silently filled.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal

from app.playbook.models import Action, Directive, Mode

#: TODO(risk-gate): 歸屬語 pending creative-lead draft + risk-compliance sign-off
#: (風控 required R2). Deliberately unused -- no response may carry a sentence
#: about authorship that has not been approved.
ATTRIBUTION_NOTE_TODO = "TODO(risk-gate): 歸屬語待 creative-lead 起草、risk-compliance 定稿"

#: action -> the word the user's own rule set uses.
ACTION_LABELS: dict[Action, str] = {
    "buy": "買進",
    "sell": "賣出",
    "defer": "順延",
    "skip": "跳過",
    "none": "無動作",
}

MODE_LABELS: dict[Mode, str] = {
    "normal": "正常",
    "defense": "防守",
    "frozen": "全凍結",
    "emergency_frozen": "緊急出清後凍結",
}

#: rule id -> the one-line restatement shown next to every directive (R1: the
#: rule id, its text and the date may not be collapsed away).
RULE_TEXT: dict[str, str] = {
    "R1": "R1 排程日進場：排程日買進該檔下一批。",
    "R2": "R2 不追價煞車：當日漲幅 >3% 或 BIAS25 >+10% 時順延該批。",
    "R3": "R3 順延上限：同一批順延累計 3 次後跳過該批。",
    "R4": "R4 凍結期間不執行進場：凍結或排程暫停期間不產生 R 系列進場。",
    "S1": (
        "S1 單批停損：收盤 < 該批成本 ×0.90（防守模式 ×0.93）賣出該批，"
        "該檔排程暫停至收盤站回 25MA。"
    ),
    "S2": "S2 整檔停損：收盤 < 該檔均成本 ×0.85 出清整檔，並列入黑名單 60 交易日。",
    "S3": (
        "S3 組合熔斷：新倉未實現 < -8% 時全組合凍結 10 交易日，期間僅產生賣出類指令。"
    ),
    "P1": "P1 停利：收盤 ≥ 該批成本 ×1.20 賣出該批 1/3。",
    "P2": (
        "P2 停利：收盤 ≥ 該批成本 ×1.35 再賣 1/3，"
        "其餘轉移動停利（跌破 25MA 或波段最高收盤 ×0.88 出清）。"
    ),
    "P3": "P3 過熱：BIAS25 >+15%（高波動清單 >+20%）強制減 1/3，每 10 交易日限一次。",
    "M1": "M1 大盤總開關：指數收盤低於月線連續 3 日進入防守模式，站回月線解除。",
    "IRON1": "鐵律①現金 30% 不可破：進場金額使現金低於 30% 時縮減該批股數。",
    "EMERGENCY": (
        "EMERGENCY_EXIT：使用者提交全部出清，執行後所有排程凍結 20 交易日。"
    ),
    "REBALANCE": (
        "季末 REBALANCE：以當時總資產重算 TOTAL_DEPLOY＝總資產 ×70%，次季生效；"
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

#: 風控 R17: every reference price says which trading day it came from and what
#: it does not include. Appended to the rendered directive line.
REFERENCE_PRICE_NOTE = "（依據交易日收盤價，不反映今日盤中變動）"

#: 資料缺漏 (鐵律⑤ / 風控 R6): the symbol produces no line at all that day.
DATA_GAP_NOTE = "{symbol} 資料狀態為 {status}（來源 {source}），依鐵律⑤當日不產生指令。"

#: 文案閘門條件式：此句以行為為準——引擎當日確實會出「順延」指令（M1-1），
#: 所以不能再寫成「不產生指令」。
INDEX_DATA_GAP_NOTE = (
    "加權指數資料狀態為 {status}（來源 {source}），M1 今日未評估、沿用前一狀態；"
    "當日不新開倉，R 系列進場改為順延並計入順延次數。"
)

#: M1-1: 指數缺漏當日 R 系列一律順延（真正的順延，不是靜默跳過）。
INDEX_GAP_DEFER_NOTE = "M1 今日未評估（加權指數資料 {status}），本批順延第 {count} 次。"

#: FM-1: 快市判定在指數資料不可用時沿用前態，不得因資料缺漏首次進入。
FAST_MARKET_CARRIED_NOTE = (
    "加權指數資料狀態為 {status}，快市判定沿用前一次評估結果（{state}，依據資料日 {measured_on}）；"
    "資料缺漏不會使系統首次進入快市。"
)
FAST_MARKET_STATE_ACTIVE = "快市"
FAST_MARKET_STATE_INACTIVE = "非快市"
FAST_MARKET_NO_HISTORY = "尚無前次判定"

#: E-2: MISSED 重試上限對齊 R3。
MISSED_LIMIT_NOTE = "T+1 未成交（MISSED）累計 {count} 次，達 {limit} 次上限，跳過本批。"

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
    "目前符合快市條件（20 日年化波動率 {vol}%、近 {lookback} 交易日有 {moves} 日 |漲跌幅| ≥2%）；"
    "快市期間規則不放寬。"
)

FAST_MARKET_REASON = "20 日年化波動率 {vol}%；近 {lookback} 交易日 |漲跌幅| ≥2% 共 {moves} 日。"

EMERGENCY_EXIT_RESULT = (
    "EMERGENCY_EXIT 已執行：出清 {batches} 批、共 {shares} 股；所有排程凍結至 {until}。"
)

EMERGENCY_EXIT_EMPTY = "EMERGENCY_EXIT 已執行：目前無持有批次；所有排程凍結至 {until}。"

#: T+1 結算 (CEO 裁決七). A line is settled against the 預定執行日's opening
#: price; without that price the line stays pending and is named, never guessed.
SETTLEMENT_NO_OPEN_PRICE = (
    "{symbol} 預定執行日 {execution_date} 尚無日線開盤價（資料狀態 {status}／來源 {source}），"
    "本筆未結算，維持待結算狀態。"
)
SETTLEMENT_SUMMARY = (
    "T+1 結算：成交 {executed} 筆、未成交（MISSED）{missed} 筆、未結算 {pending} 筆。"
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
REBALANCE_NO_ORDER_NOTE = "本列為季末資金重算紀錄，不是下單指令，無執行日與參考價。"
REBALANCE_BLOCKED = (
    "季末 REBALANCE 未執行：{symbols} 沒有可用收盤價，總資產無法核算；"
    "依鐵律⑤不以缺漏資料重算 TOTAL_DEPLOY。"
)

MODE_REASON_NORMAL = "正常模式：M1 未觸發，組合未凍結。"
MODE_REASON_DEFENSE = "防守模式：指數收盤低於月線連續 {days} 日（M1）。"
MODE_REASON_FROZEN = "全凍結：{reason}，凍結至 {until}。"
MODE_REASON_EMERGENCY = "緊急出清後凍結：所有排程凍結至 {until}。"


def _format_shares(shares: int) -> str:
    return f"{shares:,}"


def _format_price(price: Decimal | None) -> str:
    return "—" if price is None else f"{price:.2f}"


def directive_line(directive: Directive) -> str:
    """The one-line rendering of a directive: 動作／股數／規則／依據資料日.

    Provenance is part of the line, not an expandable detail: 依據資料日,
    預定執行日 and 參考價 always appear (CEO 裁決七 / 風控 R1, R17), and the
    reference price carries what it is *not* (:data:`REFERENCE_PRICE_NOTE`) so no
    reader can take it for a live intraday quote.
    """
    action = ACTION_LABELS[directive.action]
    shares = f"{_format_shares(directive.shares)} 股" if directive.shares else "—"
    batch = "" if directive.batch_no is None else f"第 {directive.batch_no} 批"
    head = f"{directive.symbol}{batch}"
    return (
        f"{head}｜{action}｜{shares}｜規則 {directive.rule_id}"
        f"｜依據資料日 {directive.data_date.isoformat()}"
        f"｜預定執行日 {directive.execution_date.isoformat()}"
        f"｜參考價 {_format_price(directive.reference_price)}{REFERENCE_PRICE_NOTE}"
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

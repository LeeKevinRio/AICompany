/**
 * Wording for the risk-remediation batch (CEO ruling #59; risk-compliance final
 * wording `work/reviews/2026-10-26-風控五項整改字面逐字審-風控.md`).
 *
 * Every literal below was fixed verbatim by risk-compliance-officer on
 * 2026-10-26. Not a single character may change here: any edit goes back to
 * risk review. Each constant carries the failure condition (T#) from that review
 * that forces it to be rewritten or removed in the same PR as the program
 * behaviour it describes.
 *
 * Scope of this file: items 1-4 and 5-BT (backtest disclosure) only. The Kelly
 * cap 5 wording (5-K) is deliberately NOT here.
 *
 * Banned-term note: nothing in this file touches `FRONTEND_FORBIDDEN_TERMS`,
 * `shared/forbidden-terms.json`, the backend `BANNED_PHRASES` or any
 * `allowedContexts` (constraint C-1); every sentence passes the existing scans.
 */

/* ---------- Item 1: 1-L / 1-X (confidence chip replaced) ---------- */

/** 1-L; 風控 2026-10-26 定稿；失效條件 T2 */
export const UNVALIDATED_LABEL = "未經歷史驗證";

/** 1-X, revealed on click; 風控 2026-10-26 定稿；失效條件 T2 */
export const UNVALIDATED_EXPLANATION =
  "這個結論所依據的規則、門檻與權重，都還沒用歷史資料驗證過。";

/* ---------- Item 2: limit violations on the main screen ---------- */

/**
 * 2-V, one violated limit. `observed` / `threshold` are already formatted
 * percentages; when either is null the parenthesised part is dropped (the
 * review forbids printing a dash or "null").
 * 風控 2026-10-26 定稿；失效條件 T1
 */
export function buildSingleViolationLine(
  index: number,
  shortName: string,
  observed: string | null,
  threshold: string | null,
): string {
  if (observed === null || threshold === null) {
    return `已違反第 ${index} 條上限：${shortName}`;
  }
  return `已違反第 ${index} 條上限：${shortName} ${observed}（上限 ${threshold}）`;
}

/** 2-M title, two or more violated limits; 風控 2026-10-26 定稿；失效條件 T1 */
export function buildMultiViolationTitle(count: number): string {
  return `已違反 ${count} 條上限：`;
}

/**
 * 2-M, one line per violated limit. Same null handling as 2-V.
 * 風控 2026-10-26 定稿；失效條件 T1
 */
export function buildMultiViolationLine(
  index: number,
  shortName: string,
  observed: string | null,
  threshold: string | null,
): string {
  if (observed === null || threshold === null) {
    return `第 ${index} 條・${shortName}`;
  }
  return `第 ${index} 條・${shortName} ${observed}（上限 ${threshold}）`;
}

/**
 * 2-R. `actionLabel` is `HELD_ACTION_LABELS[action]`, passed in by the caller.
 * It names the three labels of 加碼／續抱／減碼 directly in the sentence, so a
 * rename of any of them forces a rewrite (T9).
 * 風控 2026-10-26 定稿；失效條件 T1、T9
 */
export function buildLimitsDoNotChangeActionNotice(actionLabel: string): string {
  return `「${actionLabel}」不代表你的部位在上限內；目前超過上限只會把加碼參考改為續抱參考，不會改成減碼參考。`;
}

/**
 * 2-O. `withViolation` picks the wording that follows a violation block ("另有")
 * or stands alone ("有").
 * 風控 2026-10-26 定稿；失效條件 T1
 */
export function buildNotEvaluableLimitsNotice(count: number, withViolation: boolean): string {
  const lead = withViolation ? "另有" : "有";
  return `${lead} ${count} 條上限無法評估，不代表已通過；見下方建議卡。`;
}

/* ---------- Item 3: transitional disclaimers ---------- */

/**
 * 3-S, the decision card's short disclaimer. MUST stay character-identical to the
 * backend `DISCLAIMER` in `backend/app/advice/engine.py` (parity test:
 * `__tests__/riskRemediationWording.test.ts` and backend `test_advice_wording.py`).
 * 風控 2026-10-26 定稿；失效條件 T2、T7、T8
 */
export const OPERATION_REFERENCE_DISCLAIMER =
  "依固定規則產生的操作參考，規則與價位未經歷史驗證；可能有誤，照做也可能虧損，是否採用由你決定。日線收盤資料，非即時。";

/**
 * 3-F, the site-wide footer (also mirrored in `apps/stock-desk/README.md`).
 * 風控 2026-10-26 定稿；失效條件 T2、T7、T8
 */
export const SITE_FOOTER_DISCLAIMER =
  "本工具提供的動作、股數與價位，是依固定規則與固定算式產生的操作參考。" +
  "規則與價位都還沒用歷史資料驗證過，可能錯誤，照做也可能造成虧損，是否採用由你自行決定。" +
  "這些參考只用日線收盤資料計算，非即時，不反映最近一次收盤之後的價格變動。";

/* ---------- Item 4: stop-loss qualifiers, take-profit label ---------- */

/** 4-Q; 風控 2026-10-26 定稿；失效條件 T3 */
export const STOP_QUALIFIER = "固定算式・未還原價・可能無法依此價成交";

/** 4-E, shared tail of both versions; 風控 2026-10-26 定稿；失效條件 T3 */
const STOP_EXPLANATION_TAIL =
  "用的是未還原價，沒有把配息、除權調整進去，跨除權息日可能失真。" +
  "實際賣出時，跳空、跌停或成交量不足都可能讓成交價與此價位差很多，甚至無法成交。";

/** 4-E with ATR; 風控 2026-10-26 定稿；失效條件 T3 */
export const STOP_EXPLANATION_WITH_ATR =
  "停損參考由固定公式算出，不是分析結果：以最新收盤為基準，" +
  "取「收盤減 2 倍 ATR（近 14 個交易日的平均波動幅度）」與「收盤的 92%」兩者中較高的一個。" +
  STOP_EXPLANATION_TAIL;

/** 4-E without ATR (`atr14 === null`); 風控 2026-10-26 定稿；失效條件 T3 */
export const STOP_EXPLANATION_WITHOUT_ATR =
  "停損參考由固定公式算出，不是分析結果：以最新收盤為基準，" +
  "因近期日線不足、無法計算 ATR，只取「收盤的 92%」。" +
  STOP_EXPLANATION_TAIL;

/** 4-T, under the take-profit card title in the details; 風控 2026-10-26 定稿；失效條件 T4 */
export const TARGET_FORMULA_TAG = "固定算式，非分析結果";

/** 4-T, the ladder group title for the take-profit group; 風控 2026-10-26 定稿；失效條件 T4 */
export const TARGET_LADDER_GROUP_TITLE = "停利參考（固定算式，非分析結果）";

/** 4-appendix, next to the basis rule when it is a drawdown rule; 風控 2026-10-26 定稿；失效條件 T3 */
export const DRAWDOWN_UNADJUSTED_NOTICE = "以未還原價計算，回撤可能含除權息缺口";

/* ---------- Item 5-BT: backtest standing disclosure ---------- */

/**
 * 5-BT heading, picked by whether the configured slippage is zero.
 * 風控 2026-10-26 定稿；失效條件 T5
 */
export function buildBacktestAssumptionsHeading(slippageIsZero: boolean): string {
  return slippageIsZero
    ? "先看以下假設：前兩項可能讓結果偏樂觀"
    : "先看以下假設：第一項可能讓結果偏樂觀";
}

/** 5-BT point 1; 風控 2026-10-26 定稿；失效條件 T5 */
export const BACKTEST_SAME_CLOSE_FILL_POINT =
  "訊號與成交用同一根收盤價：收盤價要到收盤才知道，實際下單做不到這樣成交。";

/**
 * 5-BT point 2, picked by the configured slippage (`bps`).
 * 風控 2026-10-26 定稿；失效條件 T5
 */
export function buildBacktestSlippagePoint(bps: number): string {
  return bps === 0
    ? "滑價設為 0 bps：滑價是實際成交價與預期價的差距，這裡沒有計入。"
    : `滑價假設 ${bps} bps：滑價是實際成交價與預期價的差距，實際可能較大或較小。`;
}

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

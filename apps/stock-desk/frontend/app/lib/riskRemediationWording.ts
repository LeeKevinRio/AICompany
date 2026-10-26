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

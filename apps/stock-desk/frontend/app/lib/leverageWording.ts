/**
 * User-facing literals of the leverage chapter's drag table.
 * Verbatim approval: work/reviews/2026-10-03-槓桿章節-觀測值字面-風控核可.md
 * (risk-compliance-officer, 2026-10-03). Any change to these strings is drift
 * and must be re-submitted to risk review.
 *
 * `componentWordingScan.test.ts` scans this file for banned terms and
 * `leverageChapterWording.test.ts` pins every literal verbatim.
 */

/** Row label of the observed ETF close-to-close return (unadjusted prices). */
export const LEVERAGE_DRAG_OBSERVED_ROW_LABEL = "ETF 收盤價觀測值（未還原）";

/** Row label of the gap between the observed value and the naive expectation. */
export const LEVERAGE_DRAG_GAP_ROW_LABEL = "Gap（觀測值 − naive）";

/** Row label of the reset (compounding) effect; also reused in the theoretical-drag sentence. */
export const LEVERAGE_DRAG_RESET_EFFECT_LABEL = "重置（複利）效應";

/**
 * Always-visible note under the drag table: states the observed value's price
 * basis (unadjusted, no dividends, no split handling) and that the naive
 * expectation and ideal daily-reset path are theoretical values.
 */
export const LEVERAGE_DRAG_OBSERVED_NOTE =
  "觀測值以未還原權值之原始收盤價計算，不含配息、不處理分割，跨除權息日或分割日可能失真；Naive 期望與理想每日重置路徑為理論值，用來與觀測值對照。";

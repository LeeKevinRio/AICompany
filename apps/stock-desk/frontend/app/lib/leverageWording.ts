/**
 * User-facing literals of the leverage chapter's drag table.
 * Verbatim approval: work/reviews/2026-10-03-槓桿章節-觀測值字面-風控核可.md
 * (risk-compliance-officer, 2026-10-03). Any change to these strings is drift
 * and must be re-submitted to risk review.
 *
 * Section title (LEVERAGE_DRAG_SECTION_TITLE) verbatim approval:
 * work/reviews/2026-10-03-槓桿章節-小節標題-風控核可.md
 * (risk-compliance-officer, 2026-10-03, title T1, landing conditions 6a/6b).
 *
 * Data-date literals W-1 / W-2 (buildLeverageDataAsOfLine / buildErosionIndexAsOf)
 * verbatim approval: work/reviews/2026-10-04-個股頁-資料時間標籤-風控審查.md
 * (risk-compliance-officer, 2026-10-04, section "L-10g 字面", W-1 / W-2, landing
 * conditions 1-6). Dates go through `formatDataAsOfDate` (E-4); never wire any
 * `as_of` / `generated_at` here (ADR-0019 K-13).
 *
 * `componentWordingScan.test.ts` scans this file for banned terms and
 * `leverageChapterWording.test.ts` pins every literal verbatim.
 */

import { formatDataAsOfDate } from "./entryObservationWording";

/** h3 title of the drag section: states that the Gap is observed value minus naive expectation. */
export const LEVERAGE_DRAG_SECTION_TITLE = "Gap 拆解：觀測值與 Naive 期望的差距";

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


/**
 * W-1: data-date line under the drag table. ETF and index dates are always
 * listed separately (no equality or collapse branch); `computed` is the last
 * common trading day the drag figures were computed to (`drag.window.end_date`).
 * Each date prints through `formatDataAsOfDate`: this year `MM-DD`, other years
 * `YYYY-MM-DD`, anything unusable 「日期不明」.
 */
export function buildLeverageDataAsOfLine(
  etf: string | null | undefined,
  index: string | null | undefined,
  computed: string | null | undefined,
): string {
  return `資料截至：ETF ${formatDataAsOfDate(etf ?? null)}｜指數 ${formatDataAsOfDate(index ?? null)}｜計算截至 ${formatDataAsOfDate(computed ?? null)}`;
}

/**
 * W-2 second half: index data date of the erosion volatility window
 * (`erosion.index_last_bar_date`). The first half (「波動估計視窗：…」) is
 * composed in the view; no trailing full stop.
 */
export function buildErosionIndexAsOf(index: string | null | undefined): string {
  return `指數資料截至 ${formatDataAsOfDate(index ?? null)}`;
}

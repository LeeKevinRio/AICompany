/**
 * Single source file for every user-facing literal that contains "盤中"
 * (ADR-0014 W9; copy frozen in `work/copy/盤中價揭露文案-定稿-2026-10-03.md`
 * section 5, 30 sentences; risk-compliance-officer approved 2026-10-03 in
 * `盤中價揭露文案-風控審查-2026-10-03.md` and `-風控複核-2026-10-03.md`).
 *
 * Rules that bind this file (risk conditions (a)-(e), R1-1..R1-4):
 * - This is the ONLY source file (besides the single `"盤中"` element of
 *   `FRONTEND_FORBIDDEN_TERMS` in `adviceWording.ts`) allowed to contain the
 *   term. `__tests__/intradayWording.test.ts` scans every non-test .ts/.tsx
 *   under `app/` and fails on any other occurrence.
 * - Every literal here containing the term must equal one whole allowlist
 *   sentence (split on the full-width period and on newlines). Never build a
 *   sentence by concatenation, never add a prefix or suffix: a changed or new
 *   sentence containing the term must go back to risk-compliance-officer
 *   (condition (e)) and update the pinned list in the test in the same PR.
 * - Placeholders `{N}`, `{M}`, `{MM/DD}`, `{HH:mm}`, `{HH:mm:ss}` stay as
 *   literal text in the template constants. Use `fillIntradayTemplate` to
 *   render; calling it without values (or with the placeholders themselves)
 *   gives back the template byte for byte.
 * - Constants prefixed `PENDING_PRECONDITION_` are approved wording whose
 *   shipping preconditions are not met (C8-2: data-engineer confirmation and
 *   the 10/05 field test; C10-1: backend post-close status value). No
 *   non-test file may import them until the same PR that lifts the
 *   precondition also lifts the guard in the test and is re-sent to risk.
 * - C6 sentence 2 is exported here and, once W15 lands (same PR, I-27), is to
 *   be imported by `adviceWording.ts`; it must never be retyped there. Only
 *   `adviceWording.ts` may import it (R1-4).
 * - Literals use double quotes only and avoid comment-like character pairs,
 *   because the guard test strips comments with a simple scanner.
 */

export type IntradayPlaceholder = "N" | "M" | "MM/DD" | "HH:mm" | "HH:mm:ss";

export type IntradayTemplateValues = Partial<Record<IntradayPlaceholder, string | number>>;

function lookupValue(values: IntradayTemplateValues, key: string): string | null {
  for (const [name, value] of Object.entries(values)) {
    if (name === key && value !== undefined) {
      return String(value);
    }
  }
  return null;
}

/**
 * Single-pass placeholder substitution. A placeholder with no supplied value
 * is left as its literal text, so `fillIntradayTemplate(t)` === `t`. Values
 * are never re-scanned, so a value that looks like a placeholder is inert.
 */
export function fillIntradayTemplate(template: string, values: IntradayTemplateValues = {}): string {
  return template.replace(/\{(N|M|MM\/DD|HH:mm:ss|HH:mm)\}/g, (whole: string, key: string) => {
    return lookupValue(values, key) ?? whole;
  });
}

/** allowlist #1, C1-1. */
export const C1_1_PRICE_LABEL = "盤中 {HH:mm} 成交";

/** allowlist #2, C2-1 tooltip. */
export const C2_1_NO_TRADE_TOOLTIP = "來源目前沒有提供這檔今日的成交價（可能是今日尚未成交），因此不採用盤中價，改用 {MM/DD} 收盤價計算。";

/** allowlist #3, C2-2 badge. */
export const C2_2_COOLDOWN_BADGE = "盤中價暫停查詢";

/** allowlist #4, C2-2 tooltip. */
export const C2_2_COOLDOWN_TOOLTIP = "盤中價的來源近期無法正常取用，本產品暫停查詢一段時間，這檔改用 {MM/DD} 收盤價計算。";

/** allowlist #5, C2-3 badge. */
export const C2_3_NOT_OBTAINED_BADGE = "未取得盤中價";

/** allowlist #6, C2-3 tooltip. */
export const C2_3_NOT_OBTAINED_TOOLTIP = "這次沒有取得這檔的盤中價，改用 {MM/DD} 收盤價計算。";

/** allowlist #7, C2-4 badge. */
export const C2_4_FAILED_CHECK_BADGE = "盤中價未通過檢查";

/** allowlist #8, C2-4 tooltip. */
export const C2_4_FAILED_CHECK_TOOLTIP = "取得的盤中價未通過本產品的資料檢查（例如價格超出檢查範圍、時間異常或來源更新停滯），因此不採用，改用 {MM/DD} 收盤價計算。";

/** allowlist #9, C2-5 tooltip. */
export const C2_5_BOARD_UNKNOWN_TOOLTIP = "本產品無法判定這檔屬於上市或上櫃，因此不查詢盤中價，改用 {MM/DD} 收盤價計算。";

/** allowlist #10, C2-6 tooltip. */
export const C2_6_DEMO_SERIES_TOOLTIP = "示範持倉的價格為模擬資料，不查詢盤中價。";

/** allowlist #11, C2-7. */
export const C2_7_US_CLOSE_ONLY = "美股目前只提供收盤價，不查詢盤中價。";

/** allowlist #12, C2-8. */
export const C2_8_ALL_UNAVAILABLE_LINE = "盤中價目前無法取得，總計全部以各檔收盤價計算。";

/** allowlist #13, C3-1. */
export const C3_1_BASIS_MIXED = "估值基準：含 {N} 檔盤中價、{M} 檔收盤價，各檔價格時點不同";

/** allowlist #14, C3-2（時間不同）. */
export const C3_2_BASIS_ALL_INTRADAY_RANGE = "估值基準：{N} 檔皆為盤中價，成交時間 {HH:mm}～{HH:mm}";

/** allowlist #15, C3-2（時間相同）. */
export const C3_2_BASIS_ALL_INTRADAY_SINGLE = "估值基準：{N} 檔皆為盤中價，成交時間 {HH:mm}";

/** allowlist #16, C4-1（單一日、有盤中價）. */
export const C4_1_RISK_GAUGE_SINGLE_DAY_WITH_INTRADAY = "本卡以 {MM/DD} 收盤計算，不含盤中價，數字可能與總資產卡不同。";

/** allowlist #17, C4-1（日期範圍、有盤中價）. */
export const C4_1_RISK_GAUGE_DATE_RANGE_WITH_INTRADAY = "本卡以 {MM/DD}～{MM/DD} 收盤計算，不含盤中價，數字可能與總資產卡不同。";

/** allowlist #18, C4-2（有盤中價）. */
export const C4_2_SECTOR_MOMENTUM_WITH_INTRADAY = "本卡以 {MM/DD} 收盤計算，不含盤中價。";

/** allowlist #19, C5-2（S2）. */
export const C5_2_CARD_BASIS_MIXED = "含 {N} 檔盤中價、{M} 檔收盤價";

/** allowlist #20, C5-2（S1）. */
export const C5_2_CARD_BASIS_ALL_INTRADAY = "{N} 檔皆為盤中價";

/** allowlist #21, C6 句 2. */
export const C6_SENTENCE_2_OVERVIEW_NOT_IN_PAGE_EVALUATION = "總覽頁持倉估值所用的盤中價（可能有延遲）不納入本頁評估。";

/** allowlist #22, C8-1 market column. */
export const C8_1_MARKET_CELL = "TW（盤中價）";

/** allowlist #23, C8-2 句 1. PENDING_PRECONDITION: not shippable yet; see file header. */
export const PENDING_PRECONDITION_C8_2_SENTENCE_1 = "台股盤中價讀取自臺灣證券交易所基本市況報導網站（TWSE MIS）網頁所用的資料介面。";

/** allowlist #24, C8-2 句 3. PENDING_PRECONDITION: not shippable yet; see file header. */
export const PENDING_PRECONDITION_C8_2_SENTENCE_3 = "盤中價只用於總覽頁的持倉估值顯示，不用於風險上限、警示、建議、訊號與回測。";

/** allowlist #25, C10-1. PENDING_PRECONDITION: not shippable yet; see file header. */
export const PENDING_PRECONDITION_C10_1 = "本產品採用盤中價的時段已結束，尚未取得當日收盤資料，目前顯示 {MM/DD} 收盤價，不使用今日成交價。";

/** allowlist #26, C12-1. */
export const C12_1_AUTO_REFRESH = "盤中價約每 {N} 秒自動重新載入一次，分頁在背景時暫停；重新載入不改變來源資料本身的延遲。";

/** allowlist #27, C12-2. */
export const C12_2_NO_AUTO_REFRESH = "盤中價不會定時自動重新載入，只在開啟頁面、切回此分頁等情況下重新載入；重新載入不改變來源資料本身的延遲。";

/** allowlist #28, C15-1（有日期）. */
export const C15_1_ALERT_WITH_DATE = "警示以 {MM/DD} 收盤評估，不隨盤中價變動。";

/** allowlist #29, C15-1（無日期）. */
export const C15_1_ALERT_NO_DATE = "警示以收盤資料評估，不隨盤中價變動。";

/** allowlist #30, C15-2. */
export const C15_2_ADVICE_CARD = "本卡以 {MM/DD} 收盤資料評估，不使用盤中價。";

/**
 * The 30 approved template sentences (allowlist, section 5), in table order.
 * Includes the three PENDING_PRECONDITION sentences (#23, #24, #25): being on
 * the list lets the scan accept them, it does not make them shippable.
 */
export const INTRADAY_ALLOWED_SENTENCES: readonly string[] = [
  C1_1_PRICE_LABEL,
  C2_1_NO_TRADE_TOOLTIP,
  C2_2_COOLDOWN_BADGE,
  C2_2_COOLDOWN_TOOLTIP,
  C2_3_NOT_OBTAINED_BADGE,
  C2_3_NOT_OBTAINED_TOOLTIP,
  C2_4_FAILED_CHECK_BADGE,
  C2_4_FAILED_CHECK_TOOLTIP,
  C2_5_BOARD_UNKNOWN_TOOLTIP,
  C2_6_DEMO_SERIES_TOOLTIP,
  C2_7_US_CLOSE_ONLY,
  C2_8_ALL_UNAVAILABLE_LINE,
  C3_1_BASIS_MIXED,
  C3_2_BASIS_ALL_INTRADAY_RANGE,
  C3_2_BASIS_ALL_INTRADAY_SINGLE,
  C4_1_RISK_GAUGE_SINGLE_DAY_WITH_INTRADAY,
  C4_1_RISK_GAUGE_DATE_RANGE_WITH_INTRADAY,
  C4_2_SECTOR_MOMENTUM_WITH_INTRADAY,
  C5_2_CARD_BASIS_MIXED,
  C5_2_CARD_BASIS_ALL_INTRADAY,
  C6_SENTENCE_2_OVERVIEW_NOT_IN_PAGE_EVALUATION,
  C8_1_MARKET_CELL,
  PENDING_PRECONDITION_C8_2_SENTENCE_1,
  PENDING_PRECONDITION_C8_2_SENTENCE_3,
  PENDING_PRECONDITION_C10_1,
  C12_1_AUTO_REFRESH,
  C12_2_NO_AUTO_REFRESH,
  C15_1_ALERT_WITH_DATE,
  C15_1_ALERT_NO_DATE,
  C15_2_ADVICE_CARD,
];

/** The PENDING_PRECONDITION subset (#23, #24, #25). Guarded against non-test imports. */
export const PENDING_PRECONDITION_SENTENCES: readonly string[] = [
  PENDING_PRECONDITION_C8_2_SENTENCE_1,
  PENDING_PRECONDITION_C8_2_SENTENCE_3,
  PENDING_PRECONDITION_C10_1,
];

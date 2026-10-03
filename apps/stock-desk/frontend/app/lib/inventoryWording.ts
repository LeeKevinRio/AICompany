/**
 * Every user-visible literal of the inventory page (`/positions`) and its two
 * entry points (NavBar item, home expanded-row link, empty state). Kept in one
 * module so the wording review and the vitest pins have a single source.
 *
 * Provenance: `work/stock-desk-庫存頁-PRD.md` section 6 (S1..S21),
 * `work/stock-desk-庫存頁-視覺規範-2026-10-03.md` section 8 (V1..V3) and the
 * risk-compliance second-pass sign-off (S7 / S8 final text, S20 aria names,
 * D6: no "saved" toast). This is an operations page: no advisory phrasing.
 */

/** S1 / S2: NavBar item and page h1. */
export const INVENTORY_NAV_LABEL = "庫存";
export const INVENTORY_PAGE_TITLE = "庫存";
export const INVENTORY_ROUTE = "/positions";

/** S3: header button that opens the add section. */
export const INVENTORY_ADD_BUTTON = "新增";

/** S4 / S5 / S6: row actions. */
export const ROW_EDIT_LABEL = "修改";
export const ROW_SAVE_LABEL = "儲存";
export const ROW_CANCEL_LABEL = "取消";
export const ROW_MORE_LABEL = "更多";
export const ROW_REMOVE_LABEL = "移除";

/** V1 / V2: pending labels. */
export const ROW_SAVING_LABEL = "儲存中…";
export const ROW_REMOVING_LABEL = "移除中…";

/**
 * S7 (risk-approved final text). `{代號}` is the symbol and `{數量}` is the
 * quantity in the same thousands-separated format the list uses; the builder
 * substitutes both placeholders, so a later wording change only edits this
 * constant.
 */
export const REMOVE_CONFIRM_SENTENCE =
  "確定移除本系統中 {代號} 的持倉紀錄（{數量} 股）？此動作無法復原。";

/** S8 (risk-approved final text); `{代號}` is the symbol. */
export const REMOVED_TOAST = "已移除 {代號} 的持倉紀錄";

/** S9 / S10 / S12: failure labels and the already-gone notice. */
export const REMOVE_FAILED_LABEL = "移除失敗";
export const REMOVED_ALREADY_GONE = "此持倉已不存在";
export const SAVE_FAILED_LABEL = "儲存失敗";

/** S13 / S14: add section. The success line is built by `buildAddedToast`. */
export const ADD_SECTION_TITLE = "新增持倉";
export const ADD_SUBMIT_LABEL = "新增";
export const ADD_PENDING_LABEL = "新增中…";
export const ADD_FAILED_LABEL = "新增失敗";

/** S15: CSV section title. */
export const CSV_SECTION_TITLE = "CSV 匯入";

/** S16: list load failure label plus its retry button. */
export const LIST_LOAD_FAILED_LABEL = "載入失敗";
export const LIST_RETRY_LABEL = "重試";

/** S17 / S18: empty state line and the home-only button. */
export const EMPTY_TITLE = "尚無持倉";
export const EMPTY_ADD_LINK = "新增持倉";

/** S19: link in the home expanded row. Identical on every row. */
export const HOME_LINK_TO_INVENTORY = "到庫存修改";

/** S21 / V4: column and field labels (existing wording, not new). */
export const INVENTORY_COLUMN_LABELS = {
  symbol: "代號",
  market: "市場",
  quantity: "數量",
  avgCost: "平均成本（原幣）",
  note: "備註",
} as const;

/** Screen-reader-only header of the actions column. */
export const INVENTORY_ACTIONS_COLUMN_LABEL = "操作";

/** S20: list accessible name. */
export const LIST_ARIA_LABEL = "持倉列表";

/** V3: optional small line under an edited field, `{原值}` in the display format. */
export const ORIGINAL_VALUE_HINT = "原 {原值}";

function fill(template: string, values: Readonly<Record<string, string>>): string {
  let out = template;
  for (const [key, value] of Object.entries(values)) {
    out = out.split(`{${key}}`).join(value);
  }
  return out;
}

export function buildRemoveConfirmSentence(symbol: string, formattedQuantity: string): string {
  return fill(REMOVE_CONFIRM_SENTENCE, { 代號: symbol, 數量: formattedQuantity });
}

export function buildRemovedToast(symbol: string): string {
  return fill(REMOVED_TOAST, { 代號: symbol });
}

/** S14 success line, e.g. `已新增「2330」`. */
export function buildAddedToast(symbol: string): string {
  return `已新增「${symbol}」`;
}

export function buildOriginalValueHint(formattedOriginal: string): string {
  return fill(ORIGINAL_VALUE_HINT, { 原值: formattedOriginal });
}

/**
 * S20 accessible-name templates for the two names that must contain their
 * visible label text (WCAG 2.5.3 label-in-name); risk-approved final text.
 * Each is a single line: changing the wording means editing only that line.
 * `{代號}` is the symbol.
 */
export const MORE_BUTTON_ARIA_LABEL = "更多：修改 {代號} 的其他欄位";
export const AVG_COST_INPUT_ARIA_LABEL = "{代號} 平均成本（原幣）";

/** S20: accessible names (symbol-qualified so repeated buttons stay distinguishable). */
export function editAriaLabel(symbol: string): string {
  return `修改 ${symbol} 持倉`;
}
export function removeAriaLabel(symbol: string): string {
  return `移除 ${symbol} 持倉`;
}
export function moreAriaLabel(symbol: string): string {
  return fill(MORE_BUTTON_ARIA_LABEL, { 代號: symbol });
}
export function quantityInputAriaLabel(symbol: string): string {
  return `${symbol} 數量`;
}
export function avgCostInputAriaLabel(symbol: string): string {
  return fill(AVG_COST_INPUT_ARIA_LABEL, { 代號: symbol });
}
export function noteInputAriaLabel(symbol: string): string {
  return `${symbol} 備註`;
}
export function disclosureAriaLabel(title: string): string {
  return `展開／收合 ${title}`;
}

/**
 * 頁尾揭露區字面（CEO 裁定 2026-09-06「揭露句下沉頁尾」；
 * `work/stock-desk-揭露下沉頁尾-CEO裁定與方案.md`）。creative-lead 起草，
 * risk-compliance-officer 逐字審；字面（含標點）不得再改動，任何變更視為漂移須重送風控。
 * `componentWordingScan.test.ts` 逐字釘住＋禁用詞掃描。
 */

/** 頁尾區標題（也是各區塊指引句所指的位置）。 */
export const PAGE_FOOTER_DISCLOSURES_TITLE = "本頁揭露與計算依據";

/** 頁尾區導語。 */
export const PAGE_FOOTER_DISCLOSURES_INTRO =
  "以下為本頁各區塊的資料來源、揭露事項與計算方式說明，依區塊分組列示。";

/**
 * 區塊內指引句（風控 L5：帶組名的模板，組名由各區塊的標題常數代入，不得複製字串）。
 * 每個有句子下沉的區塊都必須渲染一次，字級不得低於同區導讀（text-sm / neutral-300）。
 */
export function buildFooterGuidance(groupTitle: string): string {
  return `頁尾「${groupTitle}」涵蓋本區資料來源、揭露事項與計算方式說明。`;
}

/**
 * 頁級變體（風控第二輪 R2）：放在操作摘要正下方、指向頁尾第一組（資料來源與更新頻率）。
 * 不屬於任何區塊，故不自稱「本區」；該組不含計算方式，故不承諾「計算方式」。
 */
export function buildFooterGuidanceForDataSource(groupTitle: string): string {
  return `頁尾「${groupTitle}」說明資料來源與更新頻率。`;
}

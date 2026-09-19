/**
 * 決策卡（`work/stock-desk-一眼一句簡化-派工單.md` §5.4／視覺規範 B.7）新字面。
 *
 * 風控 2026-09-19 預審 APPROVE_WITH_CONDITIONS（派工單 required 條件，逐一對應）：
 *   - 條件 1／2：距離小字固定前綴「距最新收盤 」（含尾空白）取代 creative-lead
 *     草案「距現價」（風控 VETO，此三字不得出現於任何面向使用者的字面）；符號
 *     一律複用 `PriceLadder.tsx` 既有的 `fmtSigned`（四捨五入為 0 印 `0.0%`，
 *     不得 `-0.0%`），本檔不另寫一份格式化邏輯。
 *   - 條件 4：`DECISION_CARD_ARIA_LABEL`「決策摘要」是風控本次唯一核可的標題
 *     字面，只能用於 `<section aria-label>`，不得另外渲染為可見的 `<h2>` 之類
 *     標題（不設可見標題是 creative-lead 推薦案，見
 *     `work/stock-desk-決策卡-文案稿.md` 最終提案）。
 *   - 條件 9：卡片第四格股數標籤——盤點既有釘住常數（`KeyLevelsPanel.tsx`／
 *     `adviceWording.ts`）皆無對應的標籤可沿用，故為新字面，一併列入本批風控
 *     複審清單。
 *
 * 決策卡第二輪修正（風控複審 APPROVE_WITH_CONDITIONS R1）：`DECISION_CARD_QUANTITY_LABEL`
 * 原提案「股數」不予核可，改為「股數參考」（與「停損參考」「停利參考」同一命名
 * 慣例，避免裸詞「股數」讀起來像未附任何限定的絕對數字）。
 *
 * 字面（含標點與空白）不得再改動，任何變更視為漂移須重送風控。
 * `componentWordingScan.test.ts` 逐字釘住。
 */

import { fmtSigned } from "../position/[symbol]/PriceLadder";

/** 風控 required 條件 4：唯一核可的標題字面，只用於 `<section aria-label>`。 */
export const DECISION_CARD_ARIA_LABEL = "決策摘要";

/** 風控 required 條件 1：距離小字固定前綴（含尾空白）；「距現價」為 VETO 字面。 */
export const DECISION_CARD_DISTANCE_PREFIX = "距最新收盤 ";

/**
 * 風控 required 條件 9：股數格標籤新字面（既有常數清單中無對應項）。
 * 第二輪修正 R1：「股數」不予核可，定案為「股數參考」。
 */
export const DECISION_CARD_QUANTITY_LABEL = "股數參考";

/**
 * 風控 required 條件 2：`pct` 由呼叫端依 (水位 − 最新收盤) / 最新收盤 × 100
 * 算出（純算術，複用 `computeKeyLevels` 既有欄位），本函式只負責套上固定前綴
 * 並呼叫既有 `fmtSigned` 決定符號與四捨五入——不得在此重新實作正負號或無條件
 * 捨去邏輯。
 */
export function buildDecisionCardDistance(pct: number): string {
  return `${DECISION_CARD_DISTANCE_PREFIX}${fmtSigned(pct)}`;
}

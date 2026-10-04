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
 * 風控 required 條件 2：`pct` 由呼叫端算出後，本函式只負責套上固定前綴
 * 「距最新收盤 」並呼叫既有 `fmtSigned` 決定符號與四捨五入——不得在此重新實作
 * 正負號或無條件捨去邏輯。
 *
 * Denominator: this is the NOT-crossed branch only, where `pct` is
 * (level - latest close) / latest close x 100, i.e. the latest close is the
 * denominator. When the latest close has crossed a reference level
 * (see `pickDecisionCardDistance`) the card uses the crossed sentence instead,
 * and the denominator becomes the reference level itself. So the latest close
 * is no longer the only denominator on the card.
 */
export function buildDecisionCardDistance(pct: number): string {
  return `${DECISION_CARD_DISTANCE_PREFIX}${fmtSigned(pct)}`;
}

/**
 * Crossed-level sentences (risk review 2026-10-04,
 * `work/reviews/2026-10-04-決策卡-已越過水位-風控審查.md`, wording approved
 * verbatim; case A, display only). Prefixes include the trailing space; the
 * percentage comes from the existing `fmtSigned`, denominator is the reference
 * level itself. No "已", no bare "水位" (always "參考水位"), no colour, no chip.
 * Pinned verbatim by `componentWordingScan.test.ts`; any change is wording
 * drift and must go back to risk review.
 */
export const DECISION_CARD_CROSSED_TARGET_PREFIX = "最新收盤高於此參考水位 ";
export const DECISION_CARD_CROSSED_STOP_PREFIX = "最新收盤低於此參考水位 ";

/**
 * Conditional disclosure line: rendered (once, standing, not collapsed, no
 * tooltip) only when at least one of the two cells shows a crossed sentence,
 * because the action label next to it is decided by rules that do not read
 * these two reference levels (risk review 2026-10-04, required item 4).
 */
export const DECISION_CARD_CROSSED_DISCLOSURE =
  "上方動作由規則判斷，規則未讀取停損參考與停利參考。";

export interface DecisionCardDistance {
  /** The small-print text for the cell. */
  text: string;
  /** True when the crossed sentence is used (drives the disclosure line). */
  crossed: boolean;
}

/**
 * Picks the distance small-print for the stop or target cell.
 *
 * - Crossed (strict comparison on the UNROUNDED raw values, never on rounded
 *   figures): target cell when `close > level`, stop cell when `close < level`.
 *   Text = crossed prefix + `fmtSigned((close - level) / level x 100)`, so the
 *   denominator is the reference level itself.
 * - Otherwise (including equality) the original branch applies:
 *   `buildDecisionCardDistance((level - close) / close x 100)`.
 *
 * The caller must only pass `allowCrossed = true` when the effective anchor
 * source is `"cost"`; for close-not-held / close-unknown / R2 downgrade the
 * crossed sentence must never appear.
 */
export function pickDecisionCardDistance(
  kind: "stop" | "target",
  close: number,
  level: number,
  allowCrossed: boolean,
): DecisionCardDistance {
  if (allowCrossed) {
    if (kind === "target" && close > level) {
      return {
        text: `${DECISION_CARD_CROSSED_TARGET_PREFIX}${fmtSigned(((close - level) / level) * 100)}`,
        crossed: true,
      };
    }
    if (kind === "stop" && close < level) {
      return {
        text: `${DECISION_CARD_CROSSED_STOP_PREFIX}${fmtSigned(((close - level) / level) * 100)}`,
        crossed: true,
      };
    }
  }
  return {
    text: buildDecisionCardDistance(((level - close) / close) * 100),
    crossed: false,
  };
}

/**
 * Prefixes for the decision card's "invalidation condition" line, approved
 * word-for-word by risk-compliance-officer (2026-10-03 review, item 3:
 * `work/reviews/2026-10-03-決策卡-信心與失效條件-風控審查.md`).
 * Full-width colon; prefix and body share one `<p>`, same size and grey.
 * The body is the backend `matched_rules[].invalidation` text, verbatim,
 * trailing "。" kept. `invalidation_conditions.length === 1` uses
 * `DECISION_CARD_INVALIDATION_PREFIX`, `>= 2` uses `..._ONE_OF`.
 * Pinned verbatim by `componentWordingScan.test.ts`; any change is wording
 * drift and must go back to risk review.
 */
export const DECISION_CARD_INVALIDATION_PREFIX = "失效條件：";
export const DECISION_CARD_INVALIDATION_PREFIX_ONE_OF = "失效條件之一：";

/** Prefix by the total count of the card's invalidation conditions. */
export function pickInvalidationPrefix(conditionCount: number): string {
  return conditionCount === 1
    ? DECISION_CARD_INVALIDATION_PREFIX
    : DECISION_CARD_INVALIDATION_PREFIX_ONE_OF;
}

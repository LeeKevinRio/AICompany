/**
 * 股數成因字面（缺陷 2，風控 2026-10-26 定稿：
 * `work/reviews/2026-10-26-遷移未執行與股數成因字面逐字審-風控.md` 第一節「第 2 組」
 * Q-a／Q-b／D-a／D-b／C-0，第四節 J-1～J-5）。
 *
 * Scope: a held card (`kind === "held"`) whose `quantity_range` is null. The
 * decision card's 「股數參考」 cell used to print 「未提供股數」 and the details
 * 「此建議未附帶數量區間（無法從風險上限推導）。」 for every such card, but a
 * hold carries no trade quantity by design, so on a hold that read as "the
 * system did not see the holding" and misstated the cause.
 *
 * - (b) `blocked_action === "add"` and `action === "hold"`: the rules said add,
 *   a risk cap blocked it (Q-b／D-b). Must never share a sentence with (a).
 * - (a) `action === "hold"` and `blocked_action === null`: a plain hold (Q-a／
 *   D-a). Also covers a hold downgraded from add by a defensive rule
 *   (`downgrade_notices` non-empty, `blocked_action` null) — 風控 第二節 第 2 組
 *   第 1 點 accepted that on purpose.
 * - C-0 everything else (candidate included): the existing
 *   `QUANTITY_RANGE_ABSENT_SHORT` / `QUANTITY_RANGE_ABSENCE_TEXT`, unchanged.
 *
 * Action names come from `HELD_ACTION_LABELS` and the cell label from
 * `DECISION_CARD_QUANTITY_LABEL` by interpolation (J-3), so the sentences can
 * never drift from the labels on screen. Every string is pinned verbatim by
 * `quantityAbsenceCause.test.ts` and is in the banned-term scan there and in
 * `componentWordingScan.test.ts`'s source scan. Any change is drift and must
 * go back to risk-compliance-officer. Invalidation conditions: Q-1～Q-11 of
 * the same ruling (notably Q-8: `blocked_action` set after a defensive
 * downgrade; Q-11: a backend cause field replaces this derivation).
 */

import {
  HELD_ACTION_LABELS,
  QUANTITY_RANGE_ABSENCE_TEXT,
  QUANTITY_RANGE_ABSENT_SHORT,
} from "./adviceWording";
import { DECISION_CARD_QUANTITY_LABEL } from "./decisionCardWording";

/** Why a card has no quantity range, as far as the four allowed fields can tell. */
export type QuantityAbsenceCause = "hold" | "hold_blocked_add" | "unspecified";

/**
 * J-1: the only cause derivation. Reads exactly `kind`, `quantity_range`,
 * `action` and `blocked_action` — never `blocked_notices` / `downgrade_notices`
 * text, `matched_rules` or `aggregated_action` — in the fixed order (b), (a),
 * C-0. Returns null when the card does have a quantity range.
 */
export function resolveQuantityAbsenceCause(
  kind: "held" | "candidate",
  quantityRange: object | null,
  action: string,
  blockedAction: string | null,
): QuantityAbsenceCause | null {
  if (quantityRange !== null) return null;
  if (kind !== "held") return "unspecified";
  if (blockedAction === "add" && action === "hold") return "hold_blocked_add";
  if (action === "hold" && blockedAction === null) return "hold";
  return "unspecified";
}

/** Q-a: plain hold, the 「股數參考」 cell. */
export const QUANTITY_ABSENT_SHORT_HOLD = `${HELD_ACTION_LABELS.hold}不附交易股數`;

/** Q-b: add blocked by a risk cap, now hold — the 「股數參考」 cell. */
export const QUANTITY_ABSENT_SHORT_HOLD_BLOCKED_ADD = `${HELD_ACTION_LABELS.add}被風險上限擋下`;

/** D-a: plain hold, the details sentence (replaces `QUANTITY_RANGE_ABSENCE_TEXT` for this cause only). */
export const QUANTITY_ABSENCE_TEXT_HOLD =
  `${HELD_ACTION_LABELS.hold}本身不附交易股數。` +
  `「${DECISION_CARD_QUANTITY_LABEL}」指的是交易股數，不是持有股數。`;

/** D-b: add blocked by a risk cap, now hold — the details sentence. */
export const QUANTITY_ABSENCE_TEXT_HOLD_BLOCKED_ADD =
  `規則原本的結論是${HELD_ACTION_LABELS.add}，被風險上限擋下後改為${HELD_ACTION_LABELS.hold}；` +
  `${HELD_ACTION_LABELS.hold}不附交易股數。` +
  `「${DECISION_CARD_QUANTITY_LABEL}」指的是交易股數，不是持有股數。`;

/** 「股數參考」 cell text per cause; `unspecified` is C-0, the existing short form unchanged. */
export const QUANTITY_ABSENT_SHORT_BY_CAUSE: Record<QuantityAbsenceCause, string> = {
  hold: QUANTITY_ABSENT_SHORT_HOLD,
  hold_blocked_add: QUANTITY_ABSENT_SHORT_HOLD_BLOCKED_ADD,
  unspecified: QUANTITY_RANGE_ABSENT_SHORT,
};

/** Details sentence per cause; `unspecified` is C-0, the existing sentence unchanged. */
export const QUANTITY_ABSENCE_TEXT_BY_CAUSE: Record<QuantityAbsenceCause, string> = {
  hold: QUANTITY_ABSENCE_TEXT_HOLD,
  hold_blocked_add: QUANTITY_ABSENCE_TEXT_HOLD_BLOCKED_ADD,
  unspecified: QUANTITY_RANGE_ABSENCE_TEXT,
};

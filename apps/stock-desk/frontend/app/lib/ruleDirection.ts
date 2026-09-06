import type { AdviceCard, DirectionWeight } from "./types";

/**
 * Per-rule direction for the 命中規則 visual grading (CEO 圖形化 item 3,
 * 2026-09-06). The backend already states which actions belong to which
 * direction in `direction_weights[].actions` (`app/advice/engine.py`
 * `ACTION_DIRECTION`, surfaced per response) — this module READS that map
 * back off the card rather than re-declaring the action→direction table on
 * the client, so the two can never drift. An action the response does not
 * list (should not happen) maps to `null` and the rule renders without a
 * direction chip.
 */

export function actionDirectionMap(directionWeights: readonly DirectionWeight[]): ReadonlyMap<string, string> {
  const map = new Map<string, string>();
  for (const dw of directionWeights) {
    for (const action of dw.actions) {
      if (!map.has(action)) map.set(action, dw.direction);
    }
  }
  return map;
}

export function ruleDirection(advice: Pick<AdviceCard, "direction_weights">, action: string): string | null {
  return actionDirectionMap(advice.direction_weights).get(action) ?? null;
}

export interface DirectionShare {
  readonly direction: string;
  readonly weight: number;
  /** weight / total × 100; 0 when the total is 0. */
  readonly sharePct: number;
}

/**
 * Direction weights as shares of their own total, in the order given by the
 * response (the backend already sorts heaviest first). Used for the 100%
 * stacked bar; the list beneath it still prints the raw weights verbatim.
 */
export function directionShares(directionWeights: readonly DirectionWeight[]): DirectionShare[] {
  const total = directionWeights.reduce((s, dw) => s + (Number.isFinite(dw.weight) ? dw.weight : 0), 0);
  return directionWeights.map((dw) => ({
    direction: dw.direction,
    weight: dw.weight,
    sharePct: total > 0 && Number.isFinite(dw.weight) ? (dw.weight / total) * 100 : 0,
  }));
}

/**
 * Whether the 100% stacked direction bar is drawn at all: at least one
 * direction carries weight. Shared by `DirectionWeightBar` and the 頁尾
 * builder so the R5 qualifier and the bar always appear together.
 */
export function hasDirectionShareBar(advice: Pick<AdviceCard, "direction_weights">): boolean {
  return directionShares(advice.direction_weights).some((s) => s.sharePct > 0);
}

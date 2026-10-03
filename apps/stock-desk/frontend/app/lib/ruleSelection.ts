/**
 * Pick the one matched rule that speaks for a card's action.
 *
 * Mirror of the backend reference `apps/stock-desk/backend/app/advice/selection.py`
 * (`pick_rule_for_action`, risk-compliance review option C, 2026-10-03):
 *
 * 1. only rules whose own `action` equals the requested action are eligible;
 * 2. among those, the heaviest weight wins;
 * 3. equal weights resolve to the earlier rule in array order (the backend
 *    emits `matched_rules` in rule-file order).
 *
 * There is no direction matching and no fallback to the heaviest rule overall:
 * that fallback is what produced a basis / invalidation text reading opposite
 * to the card's conclusion.
 *
 * Callers must only ask when the card's `action` equals its `aggregated_action`.
 * A gate that overrode the call (defensive downgrade, cap blocking an add)
 * means the action was not taken from the rules, and this function cannot see
 * that. The gate is the caller's.
 */

import type { MatchedRule } from "./types";

export function pickRuleForAction(
  matchedRules: readonly MatchedRule[],
  action: string,
): MatchedRule | null {
  let picked: MatchedRule | null = null;
  for (const rule of matchedRules) {
    if (rule.action !== action) continue;
    // Strictly heavier only, so an equal weight keeps the earlier rule.
    if (picked === null || rule.weight > picked.weight) picked = rule;
  }
  return picked;
}

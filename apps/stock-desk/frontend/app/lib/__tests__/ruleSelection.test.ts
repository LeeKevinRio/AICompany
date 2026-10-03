/**
 * Mirror of `apps/stock-desk/backend/tests/test_advice_selection.py`'s
 * selection cases: the frontend carries its own copy of option C
 * (risk-compliance review 2026-10-03), so the same cases must hold here.
 */

import { describe, expect, it } from "vitest";
import { pickRuleForAction } from "../ruleSelection";
import type { MatchedRule } from "../types";

function entry(id: string, action: string, weight: number): MatchedRule {
  return {
    id,
    name: id,
    action,
    weight,
    weight_meaning: "",
    explanation: "",
    invalidation: `${id} 的失效條件。`,
  };
}

describe("pickRuleForAction — the review's counter-example", () => {
  it("uptrend_ma_stack add 0.5 / rsi_overbought reduce 0.4 / kd_high_level_weakening reduce 0.35 -> picks rsi_overbought for reduce", () => {
    const rules = [
      entry("uptrend_ma_stack", "add", 0.5),
      entry("rsi_overbought", "reduce", 0.4),
      entry("kd_high_level_weakening", "reduce", 0.35),
    ];
    const heaviest = rules.reduce((a, b) => (b.weight > a.weight ? b : a));
    expect(heaviest.id).toBe("uptrend_ma_stack"); // the trap option B fell into
    expect(pickRuleForAction(rules, "reduce")).toBe(rules[1]);
  });
});

describe("pickRuleForAction — the selection rule itself", () => {
  it("only rules proposing the action are eligible", () => {
    const rules = [entry("heavy_add", "add", 0.9), entry("light_reduce", "reduce", 0.1)];
    expect(pickRuleForAction(rules, "reduce")?.id).toBe("light_reduce");
  });

  it("heaviest wins regardless of position", () => {
    const rules = [entry("light", "reduce", 0.35), entry("heavy", "reduce", 0.6)];
    expect(pickRuleForAction(rules, "reduce")?.id).toBe("heavy");
  });

  it("equal weights resolve to array (rule-file) order, not alphabetical", () => {
    const rules = [
      entry("earlier", "reduce", 0.6),
      entry("later", "reduce", 0.6),
      entry("lighter", "reduce", 0.5),
    ];
    expect(pickRuleForAction(rules, "reduce")?.id).toBe("earlier");
    expect(pickRuleForAction([rules[1]!, rules[0]!], "reduce")?.id).toBe("later");
  });

  it("returns null when no rule proposes the action", () => {
    expect(pickRuleForAction([], "reduce")).toBeNull();
    expect(pickRuleForAction([entry("only_add", "add", 0.5)], "reduce")).toBeNull();
    expect(pickRuleForAction([entry("only_add", "add", 0.5)], "insufficient_data")).toBeNull();
  });

  it("does not mutate its input and returns one of its items", () => {
    const rules = [entry("a", "reduce", 0.4), entry("b", "add", 0.5)];
    const snapshot = rules.map((r) => ({ ...r }));
    const picked = pickRuleForAction(rules, "reduce");
    expect(rules).toEqual(snapshot);
    expect(picked).toBe(rules[0]);
  });
});

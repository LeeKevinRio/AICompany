/**
 * Unit test for `ruleDescription` — 順手 fix (2026-08-09 e2e finding): a
 * `signal_condition` rule with a `ref` (field-vs-field) comparison rendered
 * as "close 大於 —" in the rule list, silently dropping which field it was
 * compared against. Only the `ref` branch is new; the `value` branch is
 * covered here too as a regression guard against changing existing output.
 */

import { describe, expect, it } from "vitest";
import type { AlertRule } from "../../lib/types";
import { ruleDescription } from "../AlertRulesSection";

function makeRule(overrides: Partial<AlertRule> = {}): AlertRule {
  return {
    id: 1,
    type: "signal_condition",
    symbol: "2330",
    market: "TW",
    params: { condition: { field: "close", op: "gt", value: 600, ref: null } },
    enabled: true,
    note: null,
    created_at: "2026-08-01T00:00:00+08:00",
    updated_at: "2026-08-01T00:00:00+08:00",
    ...overrides,
  };
}

describe("ruleDescription — signal_condition", () => {
  it("names the compared-against field for a ref condition, not '—'", () => {
    const rule = makeRule({
      params: { condition: { field: "ma5.last", op: "gt", value: null, ref: "ma20.last" } },
    });
    expect(ruleDescription(rule)).toBe("ma5.last 大於（>） 20 日均線最新值");
  });

  it("still shows the literal value for a value-side condition (unchanged behaviour)", () => {
    const rule = makeRule({
      params: { condition: { field: "close", op: "gt", value: 600, ref: null } },
    });
    expect(ruleDescription(rule)).toBe("close 大於（>） 600");
  });
});

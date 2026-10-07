/**
 * Unit test for `ruleDescription` — 順手 fix (2026-08-09 e2e finding): a
 * `signal_condition` rule with a `ref` (field-vs-field) comparison rendered
 * as "close 大於 —" in the rule list, silently dropping which field it was
 * compared against. Only the `ref` branch is new; the `value` branch is
 * covered here too as a regression guard against changing existing output.
 */

import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";
import type { AlertEvaluationOutcome, AlertRule } from "../../lib/types";
import { AlertEvaluationFeedback, ruleDescription } from "../AlertRulesSection";

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
    expect(ruleDescription(rule)).toBe("5 日均線最新值 大於（>） 20 日均線最新值");
  });

  it("still shows the literal value for a value-side condition (unchanged behaviour)", () => {
    const rule = makeRule({
      params: { condition: { field: "close", op: "gt", value: 600, ref: null } },
    });
    expect(ruleDescription(rule)).toBe("最新收盤價 大於（>） 600");
  });
});

/**
 * F-4 manual-check feedback wording (risk review 2026-10-07, T1/T2/T3).
 * Expected strings are hard-coded on purpose: do not import the production
 * constants for comparison.
 */
function outcomes(spec: Partial<Record<string, number>>): AlertEvaluationOutcome[] {
  const list: AlertEvaluationOutcome[] = [];
  let id = 1;
  for (const [status, n] of Object.entries(spec)) {
    for (let i = 0; i < (n ?? 0); i += 1) {
      list.push({ rule_id: id, status, reason: null });
      id += 1;
    }
  }
  return list;
}

function render(list: AlertEvaluationOutcome[]): string {
  return renderToStaticMarkup(createElement(AlertEvaluationFeedback, { outcomes: list }));
}

function paragraphs(html: string): string[] {
  return [...html.matchAll(/<p>(.*?)<\/p>/g)].map((m) => m[1] ?? "");
}

describe("AlertEvaluationFeedback — F-4 wording", () => {
  it("(a) 5 evaluated, 0 skipped, 1 fired", () => {
    expect(paragraphs(render(outcomes({ fired: 1, quiet: 4 })))).toEqual([
      "已評估 5 條規則、略過 0 條，本次觸發 1 筆事件。",
    ]);
  });

  it("(b) 3 evaluated, 2 skipped, 0 fired", () => {
    expect(paragraphs(render(outcomes({ quiet: 3, skipped: 2 })))).toEqual([
      "已評估 3 條規則、略過 2 條，本次觸發 0 筆事件。",
    ]);
  });

  it("(c) all skipped", () => {
    expect(paragraphs(render(outcomes({ skipped: 5 })))).toEqual([
      "已評估 0 條規則、略過 5 條，本次觸發 0 筆事件。",
    ]);
  });

  it("(d) fired plus one suppressed adds the cooldown sentence", () => {
    expect(paragraphs(render(outcomes({ fired: 1, suppressed: 1, quiet: 1, skipped: 2 })))).toEqual([
      "已評估 3 條規則、略過 2 條，本次觸發 1 筆事件。",
      "已評估的規則中，1 條符合條件但在冷卻中，本次未觸發事件。",
    ]);
  });

  it("(e) all suppressed", () => {
    expect(paragraphs(render(outcomes({ suppressed: 5 })))).toEqual([
      "已評估 5 條規則、略過 0 條，本次觸發 0 筆事件。",
      "已評估的規則中，5 條符合條件但在冷卻中，本次未觸發事件。",
    ]);
  });

  it("(f) no enabled rules shows only T3, never T1", () => {
    const html = render([]);
    expect(paragraphs(html)).toEqual(["目前沒有啟用中的規則，本次未評估任何規則。"]);
    expect(html).not.toContain("已評估");
  });

  it("(g) unknown status counts toward skipped, never evaluated", () => {
    expect(paragraphs(render(outcomes({ fired: 1, quiet: 1, partial: 2 })))).toEqual([
      "已評估 2 條規則、略過 2 條，本次觸發 1 筆事件。",
    ]);
  });

  it("T1 and T2 live in one role=status container; neutral styling only", () => {
    const html = render(outcomes({ suppressed: 2, quiet: 1 }));
    expect(html.match(/role="status"/g)).toHaveLength(1);
    const container = html.match(/^<div role="status"([^>]*)>(.*)<\/div>$/);
    expect(container).not.toBeNull();
    expect(paragraphs(container?.[2] ?? "")).toHaveLength(2);
    expect(html).toContain("text-neutral-300");
    expect(html).toContain("text-sm");
    expect(html).not.toMatch(/emerald|amber|red-/);
    expect(html).not.toMatch(/nowrap|truncate|line-clamp|text-balance|<svg/);
  });
});

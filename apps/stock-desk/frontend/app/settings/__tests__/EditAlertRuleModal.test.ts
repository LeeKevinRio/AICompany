/**
 * Unit tests for `EditAlertRuleModal.tsx`'s logic (`paramsToForm`,
 * `toFormState`, `isRefCondition`, `buildAlertRulePatch`) — previously zero
 * coverage. This project has no `@testing-library/react`/jsdom yet (see
 * `vitest.config.ts`'s doc comment), so these test the pure functions
 * directly rather than rendering the modal — the same "no test framework
 * for components yet" trade-off `app/lib/__tests__/operationSummary.test.ts`
 * documents.
 *
 * Required by the FE-WIRING BLOCKING retrofit (2026-08-09, qa-reviewer
 * NEEDS_CHANGES): a `signal_condition` rule whose comparison is `ref`-typed
 * (backend `Comparison.ref`, field-vs-field, e.g. "MA5 > MA20") used to have
 * its condition silently rewritten to "MA5 > 0" on save because
 * `paramsToForm` read `condition.value` (undefined for a `ref` condition)
 * into a blank input, and `Number("")` is `0`. The two cases this suite must
 * cover per the retrofit note are marked below.
 */

import { describe, expect, it } from "vitest";
import type { AlertRule } from "../../lib/types";
import { buildAlertRulePatch, isRefCondition, paramsToForm, toFormState } from "../EditAlertRuleModal";

function makeRule(overrides: Partial<AlertRule> = {}): AlertRule {
  return {
    id: 1,
    type: "price_above",
    symbol: "2330",
    market: "TW",
    params: { threshold: 600 },
    enabled: true,
    note: null,
    created_at: "2026-08-01T00:00:00+08:00",
    updated_at: "2026-08-01T00:00:00+08:00",
    ...overrides,
  };
}

const REF_RULE = makeRule({
  id: 42,
  type: "signal_condition",
  symbol: "2317",
  params: { condition: { field: "ma5.last", op: "gt", value: null, ref: "ma20.last" } },
  note: "MA5 站上 MA20",
});

const VALUE_RULE = makeRule({
  id: 7,
  type: "signal_condition",
  symbol: "2454",
  params: { condition: { field: "rsi14.last", op: "lt", value: 30, ref: null } },
});

describe("paramsToForm — signal_condition pre-fill (AC-1.6)", () => {
  it("ref 規則現值正確預填顯示: field/op/ref round-trip verbatim, value stays blank (not coerced)", () => {
    const fields = paramsToForm(REF_RULE);
    expect(fields.field).toBe("ma5.last");
    expect(fields.op).toBe("gt");
    expect(fields.conditionRef).toBe("ma20.last");
    expect(fields.value).toBe("");
  });

  it("a value-side condition pre-fills the numeric value and leaves conditionRef null", () => {
    const fields = paramsToForm(VALUE_RULE);
    expect(fields.field).toBe("rsi14.last");
    expect(fields.op).toBe("lt");
    expect(fields.value).toBe("30");
    expect(fields.conditionRef).toBeNull();
  });

  it("price_above/price_below and risk_limit_breach still pre-fill their own fields", () => {
    expect(paramsToForm(makeRule({ type: "price_above", params: { threshold: 88.5 } })).threshold).toBe("88.5");
    expect(
      paramsToForm(makeRule({ type: "risk_limit_breach", params: { limit_id: "sector_weight" } })).limitId,
    ).toBe("sector_weight");
  });
});

describe("isRefCondition", () => {
  it("is true only for a signal_condition rule with a non-empty conditionRef", () => {
    expect(isRefCondition(toFormState(REF_RULE))).toBe(true);
    expect(isRefCondition(toFormState(VALUE_RULE))).toBe(false);
    expect(isRefCondition(toFormState(makeRule()))).toBe(false);
  });
});

describe("buildAlertRulePatch — AC-1.2 per-field diff", () => {
  it("編輯 ref 規則僅切 enabled → PATCH body 無 params: only `enabled` is sent", () => {
    const form = { ...toFormState(REF_RULE), enabled: false };
    const patch = buildAlertRulePatch(form, REF_RULE);
    expect(patch).toEqual({ enabled: false });
    expect(patch).not.toHaveProperty("params");
  });

  it("editing note alone on a ref rule still omits params", () => {
    const form = { ...toFormState(REF_RULE), note: "調整備註" };
    const patch = buildAlertRulePatch(form, REF_RULE);
    expect(patch).toEqual({ note: "調整備註" });
  });

  it("touching nothing at all yields an empty patch object (never a no-op PATCH with params)", () => {
    const form = toFormState(REF_RULE);
    const patch = buildAlertRulePatch(form, REF_RULE);
    expect(patch).toEqual({});
  });

  it("a genuinely edited value-side condition does produce a params diff", () => {
    const form = { ...toFormState(VALUE_RULE), value: "25" };
    const patch = buildAlertRulePatch(form, VALUE_RULE);
    expect(patch).toEqual({ params: { condition: { field: "rsi14.last", op: "lt", value: 25, ref: null } } });
  });

  it("toggling enabled alone on a value-side condition still omits params (regression guard for the root differencing bug)", () => {
    const form = { ...toFormState(VALUE_RULE), enabled: false };
    const patch = buildAlertRulePatch(form, VALUE_RULE);
    expect(patch).toEqual({ enabled: false });
  });

  it("clearing the note sends clear_note rather than note: ''", () => {
    const ruleWithNote = makeRule({ note: "既有備註" });
    const form = { ...toFormState(ruleWithNote), note: "" };
    const patch = buildAlertRulePatch(form, ruleWithNote);
    expect(patch).toEqual({ clear_note: true });
  });

  it("clearing a required numeric field returns null (incomplete), never a params document built from Number(\"\")", () => {
    const form = { ...toFormState(VALUE_RULE), value: "" };
    expect(buildAlertRulePatch(form, VALUE_RULE)).toBeNull();
  });
});

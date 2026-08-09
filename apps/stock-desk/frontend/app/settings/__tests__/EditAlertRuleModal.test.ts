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
import {
  buildAlertRulePatch,
  decideAlertRuleSubmit,
  isRefCondition,
  paramsToForm,
  toFormState,
} from "../EditAlertRuleModal";

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

/**
 * FE-WIRING NEEDS_CHANGES follow-up (2026-08-09, e2e-reported): filling the
 * edit form with `-5` or `abc` and clicking 儲存變更 used to be a silent
 * no-op — `buildAlertRulePatch` returning `null` made `handleSubmit`
 * `return` before any request went out or any `fieldErrors` UI could
 * render. `decideAlertRuleSubmit` is `handleSubmit`'s full decision logic,
 * pulled out as a pure function precisely so this is testable without
 * jsdom/RTL (this project has neither — see the file's top doc comment).
 */
describe("decideAlertRuleSubmit — FE-WIRING local-validation follow-up", () => {
  it("壞值提交(threshold=-5)→有錯誤訊息、無 PATCH 發出: local_errors, not patch", () => {
    const form = { ...toFormState(makeRule({ params: { threshold: 600 } })), threshold: "-5" };
    const decision = decideAlertRuleSubmit(form, makeRule({ params: { threshold: 600 } }));
    expect(decision).toEqual({ kind: "local_errors", fieldErrors: { threshold: "門檻價格必須是大於 0 的數字。" } });
  });

  it("壞值提交(threshold=abc)→有錯誤訊息、無 PATCH 發出", () => {
    const rule = makeRule({ params: { threshold: 600 } });
    const form = { ...toFormState(rule), threshold: "abc" };
    const decision = decideAlertRuleSubmit(form, rule);
    expect(decision).toEqual({ kind: "local_errors", fieldErrors: { threshold: "門檻價格必須是大於 0 的數字。" } });
  });

  it("壞值提交(signal_condition value=abc)→有錯誤訊息、無 PATCH 發出", () => {
    const form = { ...toFormState(VALUE_RULE), value: "abc" };
    const decision = decideAlertRuleSubmit(form, VALUE_RULE);
    expect(decision).toEqual({ kind: "local_errors", fieldErrors: { value: "比較值必須是數字。" } });
  });

  it("修正後提交成功: a corrected threshold produces a real patch, no local errors", () => {
    const rule = makeRule({ params: { threshold: 600 } });
    const form = { ...toFormState(rule), threshold: "650" };
    const decision = decideAlertRuleSubmit(form, rule);
    expect(decision).toEqual({ kind: "patch", patch: { params: { threshold: 650 } } });
  });

  it("touching nothing at all decides noop (no local errors, no patch, closes the modal)", () => {
    const decision = decideAlertRuleSubmit(toFormState(VALUE_RULE), VALUE_RULE);
    expect(decision).toEqual({ kind: "noop" });
  });

  it("a ref condition is never blocked by local validation even with a stale invalid value", () => {
    const form = { ...toFormState(REF_RULE), value: "abc", enabled: false };
    const decision = decideAlertRuleSubmit(form, REF_RULE);
    expect(decision).toEqual({ kind: "patch", patch: { enabled: false } });
  });
});

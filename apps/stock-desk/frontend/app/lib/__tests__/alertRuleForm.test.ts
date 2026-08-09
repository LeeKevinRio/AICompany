/**
 * Unit tests for `alertRuleForm.ts` — previously zero coverage (see the
 * FE-WIRING BLOCKING follow-up, 2026-08-09: `buildAlertParams` silently
 * turned a `ref` (field-vs-field) `signal_condition` into `value: 0` because
 * `Number("")` is `0`, not `NaN`). Covers both root causes named in the
 * retrofit note:
 *   1. `Number("")` must never pass as a real numeric input (parseRequiredNumber).
 *   2. `ref`-side conditions must round-trip through `buildAlertParams`
 *      byte-for-byte, matching the backend `Comparison` shape exactly so
 *      `paramsEqual` can tell "unchanged" from "changed".
 */

import { describe, expect, it } from "vitest";
import {
  EMPTY_ALERT_PARAM_FORM,
  buildAlertParams,
  paramsEqual,
  parseRequiredNumber,
  validateAlertParamForm,
  type AlertParamFormValues,
} from "../alertRuleForm";

function form(overrides: Partial<AlertParamFormValues> = {}): AlertParamFormValues {
  return { ...EMPTY_ALERT_PARAM_FORM, ...overrides };
}

describe("parseRequiredNumber", () => {
  it("rejects an empty string rather than reading it as 0 (the FE-WIRING trap)", () => {
    expect(parseRequiredNumber("")).toBeNull();
  });

  it("rejects a whitespace-only string", () => {
    expect(parseRequiredNumber("   ")).toBeNull();
  });

  it("rejects a non-numeric string", () => {
    expect(parseRequiredNumber("abc")).toBeNull();
  });

  it("rejects Infinity", () => {
    expect(parseRequiredNumber("Infinity")).toBeNull();
  });

  it("accepts a real number, including a legitimate 0", () => {
    expect(parseRequiredNumber("0")).toBe(0);
    expect(parseRequiredNumber("120.5")).toBe(120.5);
    expect(parseRequiredNumber("  20  ")).toBe(20);
  });
});

describe("buildAlertParams — price_above / price_below", () => {
  it("builds { threshold } for a valid positive number", () => {
    expect(buildAlertParams(form({ type: "price_above", threshold: "150" }))).toEqual({ threshold: 150 });
  });

  it("returns null (incomplete) for a blank threshold, not a 0-threshold document", () => {
    expect(buildAlertParams(form({ type: "price_above", threshold: "" }))).toBeNull();
  });

  it("returns null for a non-positive threshold", () => {
    expect(buildAlertParams(form({ type: "price_below", threshold: "0" }))).toBeNull();
    expect(buildAlertParams(form({ type: "price_below", threshold: "-5" }))).toBeNull();
  });
});

describe("buildAlertParams — signal_condition (value side)", () => {
  it("builds a full Comparison document with both value and ref keys (value set, ref null)", () => {
    const params = buildAlertParams(
      form({ type: "signal_condition", field: "ma5.last", op: "gt", value: "120", conditionRef: null }),
    );
    expect(params).toEqual({ condition: { field: "ma5.last", op: "gt", value: 120, ref: null } });
  });

  it("returns null (incomplete) for a blank value — the exact FE-WIRING regression guard", () => {
    const params = buildAlertParams(
      form({ type: "signal_condition", field: "ma5.last", op: "gt", value: "", conditionRef: null }),
    );
    expect(params).toBeNull();
  });
});

describe("buildAlertParams — signal_condition (ref side)", () => {
  it("builds a Comparison with ref set and value null, ignoring the (stale) value field", () => {
    const params = buildAlertParams(
      form({ type: "signal_condition", field: "ma5.last", op: "gt", value: "", conditionRef: "ma20.last" }),
    );
    expect(params).toEqual({ condition: { field: "ma5.last", op: "gt", value: null, ref: "ma20.last" } });
  });

  it("prefers conditionRef over a leftover value string even if one is present", () => {
    const params = buildAlertParams(
      form({ type: "signal_condition", field: "ma5.last", op: "gt", value: "999", conditionRef: "ma20.last" }),
    );
    expect(params).toEqual({ condition: { field: "ma5.last", op: "gt", value: null, ref: "ma20.last" } });
  });
});

describe("buildAlertParams — risk_limit_breach", () => {
  it("builds { limit_id }", () => {
    expect(buildAlertParams(form({ type: "risk_limit_breach", limitId: "gross_exposure" }))).toEqual({
      limit_id: "gross_exposure",
    });
  });
});

describe("paramsEqual", () => {
  it("treats differently-ordered keys as equal", () => {
    expect(paramsEqual({ a: 1, b: 2 }, { b: 2, a: 1 })).toBe(true);
  });

  it("treats a real value difference as unequal", () => {
    expect(paramsEqual({ threshold: 100 }, { threshold: 101 })).toBe(false);
  });

  it("distinguishes a ref condition from a value condition even with the same field/op", () => {
    const refCondition = { condition: { field: "ma5.last", op: "gt", value: null, ref: "ma20.last" } };
    const valueCondition = { condition: { field: "ma5.last", op: "gt", value: 0, ref: null } };
    expect(paramsEqual(refCondition, valueCondition)).toBe(false);
  });

  it("treats a nested-key reorder (condition object) as equal", () => {
    const a = { condition: { field: "ma5.last", op: "gt", value: null, ref: "ma20.last" } };
    const b = { condition: { ref: "ma20.last", value: null, op: "gt", field: "ma5.last" } };
    expect(paramsEqual(a, b)).toBe(true);
  });
});

/**
 * FE-WIRING NEEDS_CHANGES follow-up (2026-08-09, e2e-reported): submitting
 * with `-5` or `abc` used to fail `buildAlertParams`' guard silently — no
 * request, no error text, `fieldErrors` never populated because nothing
 * produced a field error to display. `validateAlertParamForm` is the fix's
 * source of truth for those messages; it must stay in lockstep with
 * `buildAlertParams`' own conditions (never flag a field `buildAlertParams`
 * would actually accept, and vice versa) — every case below cross-checks
 * both functions on the same input.
 */
describe("validateAlertParamForm — price_above / price_below", () => {
  it("flags a negative threshold (the e2e-reported -5 case)", () => {
    const f = form({ type: "price_above", threshold: "-5" });
    expect(validateAlertParamForm(f)).toEqual({ threshold: "門檻價格必須是大於 0 的數字。" });
    expect(buildAlertParams(f)).toBeNull();
  });

  it("flags a non-numeric threshold (the e2e-reported abc case)", () => {
    const f = form({ type: "price_below", threshold: "abc" });
    expect(validateAlertParamForm(f)).toEqual({ threshold: "門檻價格必須是大於 0 的數字。" });
    expect(buildAlertParams(f)).toBeNull();
  });

  it("flags a zero threshold", () => {
    expect(validateAlertParamForm(form({ type: "price_above", threshold: "0" }))).toEqual({
      threshold: "門檻價格必須是大於 0 的數字。",
    });
  });

  it("is clean (no errors) for a valid positive threshold, matching buildAlertParams succeeding", () => {
    const f = form({ type: "price_above", threshold: "150" });
    expect(validateAlertParamForm(f)).toEqual({});
    expect(buildAlertParams(f)).not.toBeNull();
  });
});

describe("validateAlertParamForm — signal_condition (value side)", () => {
  it("flags a non-numeric value (the e2e-reported abc case)", () => {
    const f = form({ type: "signal_condition", value: "abc", conditionRef: null });
    expect(validateAlertParamForm(f)).toEqual({ value: "比較值必須是數字。" });
    expect(buildAlertParams(f)).toBeNull();
  });

  it("flags a blank value", () => {
    const f = form({ type: "signal_condition", value: "", conditionRef: null });
    expect(validateAlertParamForm(f)).toEqual({ value: "比較值必須是數字。" });
  });

  it("does NOT flag a negative value — signal_condition.value has no positivity constraint, unlike threshold", () => {
    const f = form({ type: "signal_condition", value: "-5", conditionRef: null });
    expect(validateAlertParamForm(f)).toEqual({});
    expect(buildAlertParams(f)).not.toBeNull();
  });
});

describe("validateAlertParamForm — signal_condition (ref side) and risk_limit_breach", () => {
  it("never flags a ref condition, regardless of the (unused) value field", () => {
    const f = form({ type: "signal_condition", value: "abc", conditionRef: "ma20.last" });
    expect(validateAlertParamForm(f)).toEqual({});
    expect(buildAlertParams(f)).not.toBeNull();
  });

  it("never flags risk_limit_breach — it has no numeric field to validate", () => {
    expect(validateAlertParamForm(form({ type: "risk_limit_breach", limitId: "gross_exposure" }))).toEqual({});
  });
});

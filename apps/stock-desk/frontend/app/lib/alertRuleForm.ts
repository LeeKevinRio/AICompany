/**
 * Shared form-state shape and `params`-building logic for an alert rule's
 * type-specific fields, factored out of `AlertRulesSection`'s create form so
 * `EditAlertRuleModal` can reuse the same fieldset component and construction
 * rule instead of re-deriving it (FR-1 AC-1.6: "重用新增表單元件").
 */

import type { AlertRuleInput, AlertType, ComparisonOp, LimitSelector } from "./types";
import { SIGNAL_FIELD_OPTIONS } from "./format";

export interface AlertParamFormValues {
  type: AlertType;
  threshold: string; // price_above / price_below
  field: string; // signal_condition
  op: ComparisonOp; // signal_condition
  value: string; // signal_condition, `value`-side comparison
  /**
   * signal_condition, `ref`-side comparison (backend `Comparison.ref` —
   * app/advice/loader.py: a `Comparison` is `value` XOR `ref`, never both).
   * `null`/absent means this condition is a `value` comparison; a non-empty
   * string means it is a field-vs-field (`ref`) comparison. This form does
   * not offer UI to author or retarget a `ref` comparison (see
   * `EditAlertRuleModal`'s read-only branch) — it only exists here so a
   * *pre-filled* `ref` condition round-trips through `buildAlertParams`
   * byte-for-byte instead of being silently coerced into a `value` of `0`
   * (the FE-WIRING BLOCKING bug this field fixes).
   */
  conditionRef: string | null;
  limitId: LimitSelector; // risk_limit_breach
}

export const EMPTY_ALERT_PARAM_FORM: AlertParamFormValues = {
  type: "price_above",
  threshold: "",
  field: SIGNAL_FIELD_OPTIONS[0]?.value ?? "close",
  op: "gt",
  value: "",
  conditionRef: null,
  limitId: "any",
};

/**
 * Parses a required numeric field, refusing to let `Number("")`'s `0` (or
 * `Number("  ")`'s `0`, or `Number("Infinity")`) pass as a real value.
 * `Number()` treats an empty/whitespace-only string as `0`, which is exactly
 * the trap that let an untouched, blank `value` input silently become a
 * comparison against `0` (FE-WIRING BLOCKING bug) — every numeric field in
 * this form must go through this, not a bare `Number(raw)`.
 */
export function parseRequiredNumber(raw: string): number | null {
  const trimmed = raw.trim();
  if (trimmed === "") return null;
  const value = Number(trimmed);
  return Number.isFinite(value) ? value : null;
}

/**
 * Order-independent deep-equality for `params` documents: the diff in
 * `EditAlertRuleModal`'s patch builder must treat `{a:1,b:2}` and
 * `{b:2,a:1}` as unchanged, and a naive `JSON.stringify(a) !==
 * JSON.stringify(b)` does not — key order in a freshly-built object
 * literal is not guaranteed to match the key order the backend happened to
 * serialize (`app/alerts/models.py`'s `Comparison` always emits both
 * `value` and `ref`, one of them `null`). Used as the single source of
 * truth for "did the user's edits actually change `params`" so that
 * comparison is robust to construction order, not just to today's field
 * ordering.
 */
export function paramsEqual(a: unknown, b: unknown): boolean {
  return stableStringify(a) === stableStringify(b);
}

function stableStringify(value: unknown): string {
  if (value === undefined) return "undefined";
  if (value === null || typeof value !== "object") return JSON.stringify(value);
  if (Array.isArray(value)) return `[${value.map(stableStringify).join(",")}]`;
  const entries = Object.entries(value as Record<string, unknown>)
    .filter(([, v]) => v !== undefined)
    .sort(([keyA], [keyB]) => (keyA < keyB ? -1 : keyA > keyB ? 1 : 0));
  return `{${entries.map(([k, v]) => `${JSON.stringify(k)}:${stableStringify(v)}`).join(",")}}`;
}

/** Builds the `params` document matching `form.type`, or `null` while the type-specific input is incomplete. */
export function buildAlertParams(form: AlertParamFormValues): AlertRuleInput["params"] | null {
  switch (form.type) {
    case "price_above":
    case "price_below": {
      const threshold = parseRequiredNumber(form.threshold);
      return threshold !== null && threshold > 0 ? { threshold } : null;
    }
    case "signal_condition": {
      // Backend `Comparison` (app/advice/loader.py) always carries both keys
      // (one `null`) — mirroring that shape exactly, rather than omitting
      // whichever side is unused, is what lets `paramsEqual` see "unchanged"
      // for a rule whose condition the user never touched.
      if (form.conditionRef !== null && form.conditionRef !== "") {
        return { condition: { field: form.field, op: form.op, value: null, ref: form.conditionRef } };
      }
      const value = parseRequiredNumber(form.value);
      if (value === null) return null;
      return { condition: { field: form.field, op: form.op, value, ref: null } };
    }
    case "risk_limit_breach":
      return { limit_id: form.limitId };
    default:
      return null;
  }
}

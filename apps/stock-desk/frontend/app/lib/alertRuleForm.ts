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
  value: string; // signal_condition
  limitId: LimitSelector; // risk_limit_breach
}

export const EMPTY_ALERT_PARAM_FORM: AlertParamFormValues = {
  type: "price_above",
  threshold: "",
  field: SIGNAL_FIELD_OPTIONS[0]?.value ?? "close",
  op: "gt",
  value: "",
  limitId: "any",
};

/** Builds the `params` document matching `form.type`, or `null` while the type-specific input is incomplete. */
export function buildAlertParams(form: AlertParamFormValues): AlertRuleInput["params"] | null {
  switch (form.type) {
    case "price_above":
    case "price_below": {
      const threshold = Number(form.threshold);
      return Number.isFinite(threshold) && threshold > 0 ? { threshold } : null;
    }
    case "signal_condition": {
      const value = Number(form.value);
      if (!Number.isFinite(value)) return null;
      return { condition: { field: form.field, op: form.op, value } };
    }
    case "risk_limit_breach":
      return { limit_id: form.limitId };
    default:
      return null;
  }
}

"use client";

import { ALERT_FIELD_BETA_NOTE } from "../lib/alertFields";
import { COMPARISON_OP_OPTIONS, LIMIT_SELECTOR_OPTIONS, SIGNAL_FIELD_OPTIONS, signalFieldLabel } from "../lib/format";
import type { AlertParamFormValues } from "../lib/alertRuleForm";

/**
 * The type-specific fields of an alert rule (threshold / signal condition /
 * risk-limit selector), shared by `AlertRulesSection`'s create form and
 * `EditAlertRuleModal` (FR-1 AC-1.6: reuse the create form's field
 * components rather than re-typing the same JSX per surface).
 */
export function AlertParamFields({
  idPrefix,
  values,
  onChange,
  thresholdError,
  valueError,
  storedField,
}: {
  idPrefix: string;
  values: AlertParamFormValues;
  // A patch object rather than a generic `(key, value)` setter: the caller's
  // own form state is a superset of `AlertParamFormValues` (it also carries
  // `symbol`/`market`/... ), and a partial-patch shape merges into that
  // superset structurally without the two sides' generic type parameters
  // having to line up exactly.
  onChange: (patch: Partial<AlertParamFormValues>) => void;
  thresholdError?: string;
  valueError?: string;
  /**
   * The field an edited rule was stored with. When it is no longer in the
   * field menu (an old rule, ADR-0021 K-9) it is kept as an extra option so
   * the controlled select shows the rule's real field instead of silently
   * falling back to the first menu entry.
   */
  storedField?: string;
}) {
  // Fields the select must still be able to show although the menu no longer
  // offers them: the stored one, and whatever the form currently holds.
  const menuValues = new Set(SIGNAL_FIELD_OPTIONS.map((opt) => opt.value));
  const extraFields = [...new Set([storedField, values.field])].filter(
    (field): field is string => field !== undefined && field !== "" && !menuValues.has(field),
  );

  if (values.type === "price_above" || values.type === "price_below") {
    return (
      <div className="max-w-xs">
        <label htmlFor={`${idPrefix}-threshold`} className="block text-sm text-neutral-400">
          門檻價格（原幣）
        </label>
        <input
          id={`${idPrefix}-threshold`}
          required
          inputMode="decimal"
          value={values.threshold}
          onChange={(e) => onChange({ threshold: e.target.value })}
          className="mt-1 w-full rounded-md border border-neutral-700 bg-neutral-900 px-3 py-2 text-sm text-neutral-100"
        />
        {thresholdError && <p className="mt-1 text-xs text-red-400">{thresholdError}</p>}
      </div>
    );
  }

  if (values.type === "signal_condition") {
    return (
      <div className="grid grid-cols-1 gap-3 sm:grid-cols-3">
        <div>
          <label htmlFor={`${idPrefix}-field`} className="block text-sm text-neutral-400">
            訊號欄位
          </label>
          <select
            id={`${idPrefix}-field`}
            value={values.field}
            onChange={(e) => onChange({ field: e.target.value })}
            aria-describedby={`${idPrefix}-field-note`}
            className="mt-1 w-full rounded-md border border-neutral-700 bg-neutral-900 px-3 py-2 text-sm text-neutral-100"
          >
            {extraFields.map((field) => (
              <option key={field} value={field}>
                {signalFieldLabel(field)}
              </option>
            ))}
            {SIGNAL_FIELD_OPTIONS.map((opt) => (
              <option key={opt.value} value={opt.value}>
                {opt.label}
              </option>
            ))}
          </select>
          {/* ADR-0021 W-1: always visible, whichever field is selected — no tooltip, truncation or sr-only. */}
          <p id={`${idPrefix}-field-note`} className="mt-1 text-xs text-neutral-400">
            {ALERT_FIELD_BETA_NOTE}
          </p>
        </div>
        <div>
          <label htmlFor={`${idPrefix}-op`} className="block text-sm text-neutral-400">
            條件
          </label>
          <select
            id={`${idPrefix}-op`}
            value={values.op}
            onChange={(e) => onChange({ op: e.target.value as AlertParamFormValues["op"] })}
            className="mt-1 w-full rounded-md border border-neutral-700 bg-neutral-900 px-3 py-2 text-sm text-neutral-100"
          >
            {COMPARISON_OP_OPTIONS.map((opt) => (
              <option key={opt.value} value={opt.value}>
                {opt.label}
              </option>
            ))}
          </select>
        </div>
        <div>
          <label htmlFor={`${idPrefix}-value`} className="block text-sm text-neutral-400">
            比較值
          </label>
          <input
            id={`${idPrefix}-value`}
            required
            inputMode="decimal"
            value={values.value}
            onChange={(e) => onChange({ value: e.target.value })}
            className="mt-1 w-full rounded-md border border-neutral-700 bg-neutral-900 px-3 py-2 text-sm text-neutral-100"
          />
          {valueError && <p className="mt-1 text-xs text-red-400">{valueError}</p>}
        </div>
      </div>
    );
  }

  return (
    <div className="max-w-xs">
      <label htmlFor={`${idPrefix}-limit`} className="block text-sm text-neutral-400">
        風險上限
      </label>
      <select
        id={`${idPrefix}-limit`}
        value={values.limitId}
        onChange={(e) => onChange({ limitId: e.target.value as AlertParamFormValues["limitId"] })}
        className="mt-1 w-full rounded-md border border-neutral-700 bg-neutral-900 px-3 py-2 text-sm text-neutral-100"
      >
        {LIMIT_SELECTOR_OPTIONS.map((opt) => (
          <option key={opt.value} value={opt.value}>
            {opt.label}
          </option>
        ))}
      </select>
    </div>
  );
}

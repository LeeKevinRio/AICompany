"use client";

import { useEffect, useRef, useState } from "react";
import { ApiError } from "../lib/api";
import {
  ALERT_RULE_UNEVALUABLE_NOTICE,
  conditionUsesUnevaluableField,
} from "../lib/alertFields";
import { ALERT_TYPE_OPTIONS, MARKET_OPTIONS, comparisonOpLabel, signalFieldLabel } from "../lib/format";
import {
  buildAlertParams,
  paramsEqual,
  validateAlertParamForm,
  type AlertParamFormValues,
} from "../lib/alertRuleForm";
import { useUpdateAlert } from "../lib/queries";
import type { AlertRule, AlertRulePatch, AlertType, ComparisonOp, LimitSelector, Market } from "../lib/types";
import { AlertParamFields } from "./AlertParamFields";

export interface FormState extends AlertParamFormValues {
  symbol: string;
  market: Market;
  enabled: boolean;
  note: string;
}

/** Reads a rule's stored `params` back into the flat, type-specific form fields (AC-1.6 pre-fill). */
export function paramsToForm(
  rule: AlertRule,
): Pick<AlertParamFormValues, "threshold" | "field" | "op" | "value" | "conditionRef" | "limitId"> {
  switch (rule.type) {
    case "price_above":
    case "price_below": {
      const { threshold } = rule.params as { threshold: number };
      return { threshold: String(threshold), field: "close", op: "gt", value: "", conditionRef: null, limitId: "any" };
    }
    case "signal_condition": {
      const { condition } = rule.params as {
        condition: { field: string; op: ComparisonOp; value?: number | null; ref?: string | null };
      };
      // A `Comparison` is `value` XOR `ref` (backend `app/advice/loader.py`).
      // A non-null `ref` (a field-vs-field condition, e.g. "MA5 > MA20") has
      // no numeric `value` to pre-fill — reading `condition.value` for it
      // used to read `undefined`/`null` and, downstream, get coerced by
      // `Number("")` into `0`, silently rewriting the rule (FE-WIRING
      // BLOCKING bug). Route it into `conditionRef` instead so it is
      // preserved verbatim rather than reconstructed from a blank input.
      if (condition.ref !== undefined && condition.ref !== null) {
        return { threshold: "", field: condition.field, op: condition.op, value: "", conditionRef: condition.ref, limitId: "any" };
      }
      return {
        threshold: "",
        field: condition.field,
        op: condition.op,
        value: condition.value !== undefined && condition.value !== null ? String(condition.value) : "",
        conditionRef: null,
        limitId: "any",
      };
    }
    case "risk_limit_breach": {
      const { limit_id } = rule.params as { limit_id: LimitSelector };
      return { threshold: "", field: "close", op: "gt", value: "", conditionRef: null, limitId: limit_id };
    }
    default:
      return { threshold: "", field: "close", op: "gt", value: "", conditionRef: null, limitId: "any" };
  }
}

export function toFormState(rule: AlertRule): FormState {
  return {
    type: rule.type,
    symbol: rule.symbol,
    market: rule.market,
    enabled: rule.enabled,
    note: rule.note ?? "",
    ...paramsToForm(rule),
  };
}

/**
 * True when the rule's `signal_condition` compares two context fields
 * (backend `Comparison.ref`) rather than a field against a literal number.
 * This form has no UI to author or retarget that kind of comparison (see
 * the read-only block below) — `condition.field`/`op` stay pinned to the
 * loaded rule's values whenever this is true, which is what keeps
 * `buildAlertRulePatch` from ever including `params` in the PATCH body
 * unless the user actually changes `type`/`symbol`/`market`/`enabled`/`note`
 * (AC-1.2: "僅切啟用時 params 不得進 body").
 */
export function isRefCondition(form: Pick<AlertParamFormValues, "type" | "conditionRef">): boolean {
  return form.type === "signal_condition" && form.conditionRef !== null && form.conditionRef !== "";
}

/**
 * `此規則的比較條件為欄位對欄位，目前不支援在此表單修改。` — new user-facing
 * copy (2026-08-09 FE-WIRING follow-up), flagged for risk-compliance-officer
 * quick review per the retrofit note: it is a functional/UI-limitation
 * notice (not investment/health/legal advice content), but is listed here
 * per the dispatch's own instruction to surface every new sentence.
 */
export const REF_CONDITION_READONLY_HINT = "此規則的比較條件為欄位對欄位，目前不支援在此表單修改。";

/**
 * API field errors the dialog has no per-field slot for, as the backend's own
 * sentences (W-R4, ADR-0021). The dialog renders a message under `symbol` and
 * `note` always, under `threshold` for a price rule, and under `value` for a
 * `value`-side signal condition; everything else — a 422 whose `loc` ends in
 * `params`, `field`, `ref`, `market`, … or any unknown key — would otherwise
 * be swallowed (the generic failure line is hidden whenever `fieldErrors` is
 * non-empty). Messages are returned verbatim (no prefix, no rewording) and
 * de-duplicated.
 */
export function unrenderedFieldErrorMessages(
  fieldErrors: Record<string, string>,
  form: Pick<AlertParamFormValues, "type" | "conditionRef">,
): string[] {
  const rendered = new Set<string>(["symbol", "note"]);
  if (form.type === "price_above" || form.type === "price_below") rendered.add("threshold");
  if (form.type === "signal_condition" && !isRefCondition(form)) rendered.add("value");
  const messages: string[] = [];
  for (const [key, message] of Object.entries(fieldErrors)) {
    if (rendered.has(key) || message === "" || messages.includes(message)) continue;
    messages.push(message);
  }
  return messages;
}

/** Shows `unrenderedFieldErrorMessages` inside the dialog; renders nothing when there are none. */
export function UnrenderedFieldErrors({ messages }: { messages: string[] }) {
  if (messages.length === 0) return null;
  return (
    <div role="alert" className="space-y-1 rounded-md border border-red-900 bg-red-950/40 px-4 py-3 text-sm text-red-300">
      {messages.map((message) => (
        <p key={message}>{message}</p>
      ))}
    </div>
  );
}

/**
 * Brings the first error box (`[role="alert"]`, in document order — the
 * `UnrenderedFieldErrors` block or the generic failure line) into view inside
 * the dialog's own scroll container (W-R8). `block: "nearest"` scrolls only as
 * far as needed and is a no-op when the box is already visible; no `smooth`
 * behavior is used, so `prefers-reduced-motion` is not affected. Takes the
 * minimal `querySelector` shape so it can be unit-tested without a DOM.
 */
export function scrollFirstAlertIntoView(
  root: { querySelector(selectors: string): { scrollIntoView(arg?: ScrollIntoViewOptions): void } | null } | null,
): void {
  root?.querySelector('[role="alert"]')?.scrollIntoView({ block: "nearest" });
}

/**
 * Notice block for a stored rule naming a field alerts cannot evaluate
 * (ADR-0021 K-9 / W-3): the original field's name, then the approved notice
 * directly after it. Pure view so it can be unit-tested without hooks.
 */
export function UnevaluableFieldNotice({ field, refField }: { field: string; refField: string | null }) {
  if (!conditionUsesUnevaluableField(field, refField)) return null;
  return (
    <p className="mt-0.5 border-l-2 border-amber-400 pl-1.5 text-xs leading-snug text-amber-400">
      {ALERT_RULE_UNEVALUABLE_NOTICE}
    </p>
  );
}

/**
 * Builds the `PATCH` body for saving `form`'s edits to `rule`, or `null`
 * while a required type-specific field is incomplete. A pure function of
 * its two arguments (module scope, not a closure over component state) so
 * it can be unit-tested without rendering the modal.
 *
 * Per-field, not whole-document: each key is compared against `rule`'s own
 * stored value and included only if it actually differs (AC-1.2) — `params`
 * in particular is compared with `paramsEqual` (order-independent) against
 * `rule.params` verbatim, not a re-serialized guess, so an untouched `ref`
 * condition (or any condition) never round-trips through the PATCH body.
 */
export function buildAlertRulePatch(form: FormState, rule: AlertRule): AlertRulePatch | null {
  const params = buildAlertParams(form);
  if (params === null) return null;
  const patch: AlertRulePatch = {};
  if (form.type !== rule.type) patch.type = form.type;
  const trimmedSymbol = form.symbol.trim();
  if (trimmedSymbol !== rule.symbol) patch.symbol = trimmedSymbol;
  if (form.market !== rule.market) patch.market = form.market;
  // `params` is one validated document per rule (never merged field-by-field
  // server-side — see `AlertRulePatch` doc comment), so any difference in
  // its shape or a type switch resends the whole thing.
  if (form.type !== rule.type || !paramsEqual(params, rule.params)) {
    patch.params = params;
  }
  if (form.enabled !== rule.enabled) patch.enabled = form.enabled;
  const trimmedNote = form.note.trim();
  const storedNote = rule.note ?? "";
  if (trimmedNote !== storedNote) {
    if (trimmedNote === "") {
      patch.clear_note = true;
    } else {
      patch.note = trimmedNote;
    }
  }
  return patch;
}

/** What `handleSubmit` should do with a given submit attempt, as data rather than side effects — see `decideAlertRuleSubmit`. */
export type AlertRuleSubmitDecision =
  | { kind: "local_errors"; fieldErrors: Record<string, string> }
  | { kind: "noop" }
  | { kind: "patch"; patch: AlertRulePatch };

/**
 * Pure decision function behind `handleSubmit`, factored out (like
 * `buildAlertRulePatch` above it) so the FE-WIRING NEEDS_CHANGES scenario —
 * submitting with an invalid type-specific field (`-5`, `abc`) — is
 * unit-testable without rendering the modal.
 *
 * Runs `validateAlertParamForm` *before* `buildAlertRulePatch`: a locally
 * invalid value must surface as `fieldErrors` (the same slot
 * `ApiError.fieldErrors` renders through), never as the silent
 * `buildAlertRulePatch` → `null` → early `return` that used to leave the
 * modal sitting there with no request and no error text.
 */
export function decideAlertRuleSubmit(form: FormState, rule: AlertRule): AlertRuleSubmitDecision {
  const fieldErrors = validateAlertParamForm(form);
  if (Object.keys(fieldErrors).length > 0) {
    return { kind: "local_errors", fieldErrors };
  }
  const patch = buildAlertRulePatch(form, rule);
  // `validateAlertParamForm` passing means `buildAlertParams` (which it
  // mirrors) also succeeds, so `patch` is never `null` here — the check
  // stays as a defensive fallback rather than a `!` assertion.
  if (patch === null) {
    return { kind: "local_errors", fieldErrors: {} };
  }
  if (Object.keys(patch).length === 0) {
    // Nothing changed — closing without a request avoids a no-op PATCH.
    return { kind: "noop" };
  }
  return { kind: "patch", patch };
}

/**
 * `PATCH /api/alerts/{rule_id}` is used here rather than `PUT` (FR-1, both
 * exist on the backend — see `app/api/alerts.py`): the edit form pre-fills
 * every field (AC-1.6), but only the fields the user actually touched need to
 * travel — `PATCH`'s per-field semantics is what lets toggling `enabled`
 * alone leave everything else provably untouched (AC-1.2), and it is the only
 * one of the two with a `clear_note` flag, which is what distinguishes "the
 * note field is empty because it wasn't touched" from "the note was
 * deliberately cleared" — a distinction `PUT`'s single nullable `note` cannot
 * express (see `AlertRulePatch` in `lib/types.ts`).
 */
export function EditAlertRuleModal({ rule, onClose }: { rule: AlertRule; onClose: () => void }) {
  const [form, setForm] = useState<FormState>(() => toFormState(rule));
  const updateMutation = useUpdateAlert();
  // Local (client-side) validation errors from `decideAlertRuleSubmit`, kept
  // separate from the backend-sourced ones below and merged into the same
  // `fieldErrors` object the existing JSX already renders under each field —
  // this is the fix for the silent-no-op bug: previously nothing set *any*
  // error state for an invalid local value, so the (correct) `fieldErrors`
  // rendering below was unreachable.
  const [localFieldErrors, setLocalFieldErrors] = useState<Record<string, string>>({});
  const apiFieldErrors = updateMutation.error instanceof ApiError ? updateMutation.error.fieldErrors : {};
  const fieldErrors = { ...apiFieldErrors, ...localFieldErrors };
  const extraErrorMessages = unrenderedFieldErrorMessages(fieldErrors, form);
  // The field the rule was stored with: kept selectable even when the menu no
  // longer offers it (ADR-0021 K-9), so the select never silently shows the
  // first menu entry for an old rule.
  const storedField = rule.type === "signal_condition" ? paramsToForm(rule).field : undefined;

  const dialogRef = useRef<HTMLDivElement>(null);
  const showGenericError = updateMutation.isError && Object.keys(fieldErrors).length === 0;
  // Changes whenever an error box appears or its text changes ("" = none), so
  // the scroll below fires on a fresh 422 but not on unrelated re-renders.
  const alertKey = showGenericError
    ? `generic:${updateMutation.error instanceof ApiError ? updateMutation.error.message : ""}`
    : extraErrorMessages.join("\n");

  useEffect(() => {
    if (alertKey === "") return;
    scrollFirstAlertIntoView(dialogRef.current);
  }, [alertKey]);

  useEffect(() => {
    function handleKeyDown(event: KeyboardEvent) {
      if (event.key === "Escape") onClose();
    }
    document.addEventListener("keydown", handleKeyDown);
    return () => document.removeEventListener("keydown", handleKeyDown);
  }, [onClose]);

  function updateField<K extends keyof FormState>(key: K, value: FormState[K]) {
    setForm((prev) => ({ ...prev, [key]: value }));
  }

  function handleSubmit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const decision = decideAlertRuleSubmit(form, rule);
    if (decision.kind === "local_errors") {
      setLocalFieldErrors(decision.fieldErrors);
      return;
    }
    setLocalFieldErrors({});
    if (decision.kind === "noop") {
      // Nothing changed — closing without a request avoids a no-op PATCH.
      onClose();
      return;
    }
    updateMutation.mutate({ id: rule.id, input: decision.patch }, { onSuccess: () => onClose() });
  }

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 px-4 py-8"
      onClick={(event) => {
        if (event.target === event.currentTarget) onClose();
      }}
    >
      <div
        ref={dialogRef}
        role="dialog"
        aria-modal="true"
        aria-labelledby="edit-alert-title"
        className="max-h-full w-full max-w-lg overflow-y-auto rounded-lg border border-neutral-800 bg-neutral-950 p-5"
      >
        <div className="flex items-center justify-between">
          <h2 id="edit-alert-title" className="text-lg font-semibold text-neutral-100">
            編輯警示規則「{rule.symbol}」
          </h2>
          <button
            type="button"
            onClick={onClose}
            aria-label="關閉編輯視窗"
            className="rounded px-1 text-neutral-400 hover:text-neutral-100"
          >
            ✕
          </button>
        </div>

        <form onSubmit={handleSubmit} className="mt-4 space-y-3">
          <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
            <div>
              <label htmlFor="edit-alert-type" className="block text-sm text-neutral-400">
                類型
              </label>
              <select
                id="edit-alert-type"
                value={form.type}
                onChange={(e) => updateField("type", e.target.value as AlertType)}
                className="mt-1 w-full rounded-md border border-neutral-700 bg-neutral-900 px-3 py-2 text-sm text-neutral-100"
              >
                {ALERT_TYPE_OPTIONS.map((opt) => (
                  <option key={opt.value} value={opt.value}>
                    {opt.label}
                  </option>
                ))}
              </select>
            </div>

            <div>
              <label htmlFor="edit-alert-symbol" className="block text-sm text-neutral-400">
                代號
              </label>
              <input
                id="edit-alert-symbol"
                required
                value={form.symbol}
                onChange={(e) => updateField("symbol", e.target.value)}
                className="mt-1 w-full rounded-md border border-neutral-700 bg-neutral-900 px-3 py-2 text-sm text-neutral-100"
              />
              {fieldErrors.symbol && <p className="mt-1 text-xs text-red-400">{fieldErrors.symbol}</p>}
            </div>

            <div>
              <label htmlFor="edit-alert-market" className="block text-sm text-neutral-400">
                市場
              </label>
              <select
                id="edit-alert-market"
                value={form.market}
                onChange={(e) => updateField("market", e.target.value as Market)}
                className="mt-1 w-full rounded-md border border-neutral-700 bg-neutral-900 px-3 py-2 text-sm text-neutral-100"
              >
                {MARKET_OPTIONS.map((opt) => (
                  <option key={opt.value} value={opt.value}>
                    {opt.value}
                  </option>
                ))}
              </select>
            </div>

            <div>
              <label htmlFor="edit-alert-note" className="block text-sm text-neutral-400">
                備註（選填）
              </label>
              <input
                id="edit-alert-note"
                value={form.note}
                onChange={(e) => updateField("note", e.target.value)}
                className="mt-1 w-full rounded-md border border-neutral-700 bg-neutral-900 px-3 py-2 text-sm text-neutral-100"
              />
              {fieldErrors.note && <p className="mt-1 text-xs text-red-400">{fieldErrors.note}</p>}
            </div>
          </div>

          {isRefCondition(form) ? (
            <div className="rounded-md border border-neutral-800 bg-neutral-900/60 p-3">
              <p className="text-sm text-neutral-300">
                訊號欄位：{signalFieldLabel(form.field)}　條件：{comparisonOpLabel(form.op)}　比較欄位：
                {signalFieldLabel(form.conditionRef ?? "")}
              </p>
              <UnevaluableFieldNotice field={form.field} refField={form.conditionRef} />
              <p role="note" className="mt-2 text-xs text-amber-400">
                {REF_CONDITION_READONLY_HINT}
              </p>
            </div>
          ) : (
            <>
              {form.type === "signal_condition" && conditionUsesUnevaluableField(form.field, null) && (
                <div className="rounded-md border border-neutral-800 bg-neutral-900/60 p-3">
                  <p className="text-sm text-neutral-300">訊號欄位：{signalFieldLabel(form.field)}</p>
                  <UnevaluableFieldNotice field={form.field} refField={null} />
                </div>
              )}
              <AlertParamFields
                idPrefix="edit-alert"
                values={form}
                onChange={(patch) => setForm((prev) => ({ ...prev, ...patch }))}
                thresholdError={fieldErrors.threshold}
                valueError={fieldErrors.value}
                storedField={storedField}
              />
            </>
          )}

          <label className="flex items-center gap-2 text-sm text-neutral-300">
            <input
              type="checkbox"
              checked={form.enabled}
              onChange={(e) => updateField("enabled", e.target.checked)}
              className="h-4 w-4"
            />
            啟用中
          </label>

          <UnrenderedFieldErrors messages={extraErrorMessages} />

          <div className="flex gap-3">
            <button
              type="submit"
              disabled={updateMutation.isPending}
              className="rounded-md bg-neutral-100 px-4 py-2 text-sm font-medium text-neutral-900 hover:bg-white disabled:cursor-not-allowed disabled:opacity-50"
            >
              {updateMutation.isPending ? "儲存中…" : "儲存變更"}
            </button>
            <button
              type="button"
              onClick={onClose}
              className="rounded-md border border-neutral-700 px-4 py-2 text-sm font-medium text-neutral-300 hover:bg-neutral-900"
            >
              取消
            </button>
          </div>
        </form>

        {showGenericError && (
          <p
            role="alert"
            className="mt-4 rounded-md border border-red-900 bg-red-950/40 px-4 py-3 text-sm text-red-300"
          >
            儲存失敗：
            {updateMutation.error instanceof ApiError ? updateMutation.error.message : "未知錯誤"}
          </p>
        )}
      </div>
    </div>
  );
}

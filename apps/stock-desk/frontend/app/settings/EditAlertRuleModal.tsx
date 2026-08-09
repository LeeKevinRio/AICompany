"use client";

import { useEffect, useState } from "react";
import { ApiError } from "../lib/api";
import { ALERT_TYPE_OPTIONS, MARKET_OPTIONS } from "../lib/format";
import { buildAlertParams, type AlertParamFormValues } from "../lib/alertRuleForm";
import { useUpdateAlert } from "../lib/queries";
import type { AlertRule, AlertRulePatch, AlertType, ComparisonOp, LimitSelector, Market } from "../lib/types";
import { AlertParamFields } from "./AlertParamFields";

interface FormState extends AlertParamFormValues {
  symbol: string;
  market: Market;
  enabled: boolean;
  note: string;
}

/** Reads a rule's stored `params` back into the flat, type-specific form fields (AC-1.6 pre-fill). */
function paramsToForm(rule: AlertRule): Pick<AlertParamFormValues, "threshold" | "field" | "op" | "value" | "limitId"> {
  switch (rule.type) {
    case "price_above":
    case "price_below": {
      const { threshold } = rule.params as { threshold: number };
      return { threshold: String(threshold), field: "close", op: "gt", value: "", limitId: "any" };
    }
    case "signal_condition": {
      const { condition } = rule.params as { condition: { field: string; op: ComparisonOp; value?: number | null } };
      return {
        threshold: "",
        field: condition.field,
        op: condition.op,
        value: condition.value !== undefined && condition.value !== null ? String(condition.value) : "",
        limitId: "any",
      };
    }
    case "risk_limit_breach": {
      const { limit_id } = rule.params as { limit_id: LimitSelector };
      return { threshold: "", field: "close", op: "gt", value: "", limitId: limit_id };
    }
    default:
      return { threshold: "", field: "close", op: "gt", value: "", limitId: "any" };
  }
}

function toFormState(rule: AlertRule): FormState {
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
  const fieldErrors = updateMutation.error instanceof ApiError ? updateMutation.error.fieldErrors : {};

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

  function buildPatch(): AlertRulePatch | null {
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
    if (form.type !== rule.type || JSON.stringify(params) !== JSON.stringify(rule.params)) {
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

  function handleSubmit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const patch = buildPatch();
    if (patch === null) return;
    if (Object.keys(patch).length === 0) {
      // Nothing changed — closing without a request avoids a no-op PATCH.
      onClose();
      return;
    }
    updateMutation.mutate({ id: rule.id, input: patch }, { onSuccess: () => onClose() });
  }

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 px-4 py-8"
      onClick={(event) => {
        if (event.target === event.currentTarget) onClose();
      }}
    >
      <div
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

          <AlertParamFields
            idPrefix="edit-alert"
            values={form}
            onChange={(patch) => setForm((prev) => ({ ...prev, ...patch }))}
            thresholdError={fieldErrors.threshold}
          />

          <label className="flex items-center gap-2 text-sm text-neutral-300">
            <input
              type="checkbox"
              checked={form.enabled}
              onChange={(e) => updateField("enabled", e.target.checked)}
              className="h-4 w-4"
            />
            啟用中
          </label>

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

        {updateMutation.isError && Object.keys(fieldErrors).length === 0 && (
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

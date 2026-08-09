"use client";

import { useState } from "react";
import { ApiError } from "../lib/api";
import {
  ALERT_TYPE_OPTIONS,
  MARKET_OPTIONS,
  alertTypeLabel,
  comparisonOpLabel,
  formatDateTime,
  limitSelectorLabel,
} from "../lib/format";
import { EMPTY_ALERT_PARAM_FORM, buildAlertParams } from "../lib/alertRuleForm";
import { useAlerts, useCreateAlert, useDeleteAlert, useEvaluateAlertsNow } from "../lib/queries";
import type { AlertRule, AlertRuleInput, AlertType, ComparisonOp, LimitSelector, Market } from "../lib/types";
import { SkeletonBlock } from "../components/SkeletonBlock";
import { AlertParamFields } from "./AlertParamFields";
import { EditAlertRuleModal } from "./EditAlertRuleModal";

interface FormState {
  type: AlertType;
  symbol: string;
  market: Market;
  threshold: string; // price_above / price_below
  field: string; // signal_condition
  op: ComparisonOp; // signal_condition
  value: string; // signal_condition
  limitId: LimitSelector; // risk_limit_breach
  note: string;
}

const EMPTY_FORM: FormState = {
  ...EMPTY_ALERT_PARAM_FORM,
  symbol: "",
  market: "TW",
  note: "",
};

/** Renders the rule's `params` as a compact, type-appropriate description. */
function ruleDescription(rule: AlertRule): string {
  switch (rule.type) {
    case "price_above":
      return `價格 > ${(rule.params as { threshold: number }).threshold}`;
    case "price_below":
      return `價格 < ${(rule.params as { threshold: number }).threshold}`;
    case "signal_condition": {
      const condition = (rule.params as { condition: { field: string; op: ComparisonOp; value?: number | null } })
        .condition;
      return `${condition.field} ${comparisonOpLabel(condition.op)} ${condition.value ?? "—"}`;
    }
    case "risk_limit_breach":
      return `${limitSelectorLabel((rule.params as { limit_id: LimitSelector }).limit_id)} 被觸發`;
    default:
      return "—";
  }
}

export function AlertRulesSection() {
  const alerts = useAlerts(true);
  const createMutation = useCreateAlert();
  const deleteMutation = useDeleteAlert();
  const evaluateMutation = useEvaluateAlertsNow();
  const [form, setForm] = useState<FormState>(EMPTY_FORM);
  const [editingRule, setEditingRule] = useState<AlertRule | null>(null);
  const fieldErrors = createMutation.error instanceof ApiError ? createMutation.error.fieldErrors : {};

  function updateField<K extends keyof FormState>(key: K, value: FormState[K]) {
    setForm((prev) => ({ ...prev, [key]: value }));
  }

  function handleSubmit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const params = buildAlertParams(form);
    if (params === null) return;
    const payload: AlertRuleInput = {
      type: form.type,
      symbol: form.symbol.trim(),
      market: form.market,
      params,
      enabled: true,
      note: form.note.trim() === "" ? null : form.note.trim(),
    };
    createMutation.mutate(payload, { onSuccess: () => setForm(EMPTY_FORM) });
  }

  return (
    <section className="rounded-lg border border-neutral-800 p-5">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <h2 className="text-lg font-semibold text-neutral-100">警示規則</h2>
        <button
          type="button"
          onClick={() => evaluateMutation.mutate()}
          disabled={evaluateMutation.isPending}
          className="rounded-md border border-neutral-700 px-3 py-1 text-xs text-neutral-300 hover:bg-neutral-800 disabled:opacity-50"
        >
          {evaluateMutation.isPending ? "檢查中…" : "手動檢查一次"}
        </button>
      </div>
      {evaluateMutation.isSuccess && (
        <p role="status" className="mt-2 text-xs text-emerald-300">
          已評估 {evaluateMutation.data.evaluated} 條規則，本次觸發 {evaluateMutation.data.fired} 筆事件。
        </p>
      )}

      <form onSubmit={handleSubmit} className="mt-4 space-y-3">
        <div className="grid grid-cols-1 gap-3 sm:grid-cols-4">
          <div>
            <label htmlFor="alert-type" className="block text-sm text-neutral-400">
              類型
            </label>
            <select
              id="alert-type"
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
            <label htmlFor="alert-symbol" className="block text-sm text-neutral-400">
              代號
            </label>
            <input
              id="alert-symbol"
              required
              value={form.symbol}
              onChange={(e) => updateField("symbol", e.target.value)}
              placeholder="2330"
              className="mt-1 w-full rounded-md border border-neutral-700 bg-neutral-900 px-3 py-2 text-sm text-neutral-100"
            />
            {fieldErrors.symbol && <p className="mt-1 text-xs text-red-400">{fieldErrors.symbol}</p>}
          </div>

          <div>
            <label htmlFor="alert-market" className="block text-sm text-neutral-400">
              市場
            </label>
            <select
              id="alert-market"
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
            <label htmlFor="alert-note" className="block text-sm text-neutral-400">
              備註（選填）
            </label>
            <input
              id="alert-note"
              value={form.note}
              onChange={(e) => updateField("note", e.target.value)}
              className="mt-1 w-full rounded-md border border-neutral-700 bg-neutral-900 px-3 py-2 text-sm text-neutral-100"
            />
          </div>
        </div>

        <AlertParamFields
          idPrefix="alert"
          values={form}
          onChange={(patch) => setForm((prev) => ({ ...prev, ...patch }))}
          thresholdError={fieldErrors.threshold}
        />

        <button
          type="submit"
          disabled={createMutation.isPending}
          className="rounded-md bg-neutral-100 px-4 py-2 text-sm font-medium text-neutral-900 hover:bg-white disabled:cursor-not-allowed disabled:opacity-50"
        >
          {createMutation.isPending ? "新增中…" : "新增警示規則"}
        </button>
      </form>

      {createMutation.isError && Object.keys(fieldErrors).length === 0 && (
        <p role="alert" className="mt-3 rounded-md border border-red-900 bg-red-950/40 px-4 py-3 text-sm text-red-300">
          新增失敗：{createMutation.error instanceof ApiError ? createMutation.error.message : "未知錯誤"}
        </p>
      )}

      <div className="mt-5">
        {alerts.isPending && <SkeletonBlock className="h-24 w-full" />}
        {alerts.isError && (
          <p role="alert" className="rounded-md border border-red-900 bg-red-950/40 px-4 py-3 text-sm text-red-300">
            無法載入警示規則：
            {alerts.error instanceof ApiError ? alerts.error.message : "未知錯誤"}
          </p>
        )}
        {alerts.isSuccess && alerts.data.items.length === 0 && (
          <p className="text-sm text-neutral-500">目前尚無警示規則。</p>
        )}
        {alerts.isSuccess && alerts.data.items.length > 0 && (
          <div className="overflow-x-auto rounded-md border border-neutral-800">
            <table className="min-w-[620px] text-left text-sm">
              <thead className="bg-neutral-900 text-neutral-400">
                <tr>
                  <th scope="col" className="px-3 py-2 font-medium">
                    代號
                  </th>
                  <th scope="col" className="px-3 py-2 font-medium">
                    類型
                  </th>
                  <th scope="col" className="px-3 py-2 font-medium">
                    條件
                  </th>
                  <th scope="col" className="px-3 py-2 font-medium">
                    狀態
                  </th>
                  <th scope="col" className="px-3 py-2 font-medium">
                    建立時間
                  </th>
                  <th scope="col" className="px-3 py-2 font-medium">
                    操作
                  </th>
                </tr>
              </thead>
              <tbody>
                {alerts.data.items.map((rule) => (
                  <tr key={rule.id} className="border-t border-neutral-800">
                    <td className="px-3 py-2 text-neutral-100">
                      {rule.symbol}（{rule.market}）
                    </td>
                    <td className="px-3 py-2 text-neutral-300">{alertTypeLabel(rule.type)}</td>
                    <td className="px-3 py-2 text-neutral-300">{ruleDescription(rule)}</td>
                    <td className="px-3 py-2 text-neutral-300">
                      {rule.enabled ? "啟用中" : "已停用"}
                    </td>
                    <td className="px-3 py-2 text-xs text-neutral-500">
                      {formatDateTime(rule.created_at)}
                    </td>
                    <td className="px-3 py-2">
                      <div className="flex gap-3">
                        <button
                          type="button"
                          onClick={() => setEditingRule(rule)}
                          className="text-xs text-sky-400 underline hover:text-sky-300"
                        >
                          編輯
                        </button>
                        <button
                          type="button"
                          onClick={() => deleteMutation.mutate(rule.id)}
                          disabled={deleteMutation.isPending}
                          className="text-xs text-red-400 underline hover:text-red-300 disabled:opacity-50"
                        >
                          刪除
                        </button>
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>

      {editingRule && <EditAlertRuleModal rule={editingRule} onClose={() => setEditingRule(null)} />}
    </section>
  );
}

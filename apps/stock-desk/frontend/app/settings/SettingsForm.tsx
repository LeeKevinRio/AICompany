"use client";

import { useState } from "react";
import { ApiError } from "../lib/api";
import { useUpdateSettings } from "../lib/queries";
import { capWidening, resolveWideningSubmitForFields, type CapWidening } from "../lib/riskWidening";
import type { AlertSettings, CostModelSettings, RiskBudgetSettings, SettingsResponse } from "../lib/types";

/**
 * S4 fix (risk-final-review.md 列管項): the one-time widening confirmation
 * (FR-9 (e)) used to gate `max_gross_exposure` only, even though
 * `max_position_weight` carries the same kind of hard ceiling
 * (`hardCeiling` below, both sourced from `app/advice/limits.py`'s
 * `MAX_POSITION_WEIGHT_CEILING`/`MAX_GROSS_EXPOSURE_CEILING`) and a breach of
 * either one blocks an `add` advice the same way (`blocked_notices` in
 * `app/advice/engine.py`, keyed by `LimitCheck.index`). `limitIndex` mirrors
 * `LIMIT_IDS`'s 1-based order in `app/advice/limits.py` (verified: 1 =
 * single_position_weight, 3 = gross_exposure) so the confirmation sentence
 * names the correct "第 N 條上限" for whichever field is being raised.
 */
const WIDENING_FIELDS: { key: keyof RiskBudgetSettings; label: string; limitIndex: number }[] = [
  { key: "max_position_weight", label: "單一標的佔比上限", limitIndex: 1 },
  { key: "max_gross_exposure", label: "總曝險上限", limitIndex: 3 },
];

interface FieldSpec<T> {
  key: keyof T;
  label: string;
  description: string;
  defaultValue: number | boolean;
  /**
   * A ceiling the backend refuses to write past (`app/advice/limits.py`).
   * Display only: it is rendered beside the field so the boundary is visible
   * *before* typing, and is deliberately not wired to any input constraint.
   * Enforcement stays server-side, so a value above it still reaches
   * `PUT /api/settings` and comes back as a per-field 422 message.
   */
  hardCeiling?: { max: number; reason: string };
}

/** Tail appended to every hard-ceiling note, so the wording lives in one place. */
const HARD_CEILING_NOTE = "放寬需修改程式碼並經風控與 CEO 同意。";

/**
 * FR-9 (e): raising `max_gross_exposure` stays inside the 1.50 hard ceiling and
 * is allowed without a code change — but it is still the user widening a risk
 * gate, and a widening that happens on the same click as "save" is one nobody
 * had to notice. So the first submit that raises it becomes a confirmation, and
 * only the second one writes. It is deliberately per-raise rather than a
 * dismissible-forever preference, and it is not a `window.confirm`: the
 * sentence has to be readable in the page, next to the number it is about.
 *
 * The rule for *which* submits need confirming is in `app/lib/riskWidening.ts`
 * (unit-tested there): editing the value after confirming it re-opens the
 * confirmation, so the number in the sentence is always the number written.
 */
const RISK_WIDENING_TITLE = "你正在放寬風控上限";

/**
 * S4/SettingsForm:42 fix (risk-final-review.md 列管項): the sentence template
 * generalised from its original `max_gross_exposure`-only wording to any
 * field in `WIDENING_FIELDS`. Content and structure are unchanged from the
 * previously risk-approved sentence — only two facts became parameters
 * (which cap's name, and its `limitIndex`) — and「加碼建議」改為「加碼參考」
 * 對齊 `adviceWording.ts` 的 `HELD_ACTION_LABELS.add` 白名單用詞
 * (`SettingsForm.tsx:42` 列管項)。因為改寫涉及使用者可見文案,一併列入本批
 * 回報請風控追認。
 */
function buildWideningBody(label: string, limitIndex: number, before: number, after: number): string {
  return `${label}由 ${before} 調高為 ${after}。放寬後，原本會被第 ${limitIndex} 條上限擋下的加碼參考可能不再被擋下。確認要繼續嗎？`;
}

const RISK_BUDGET_FIELDS: FieldSpec<RiskBudgetSettings>[] = [
  {
    key: "max_position_weight",
    label: "單一標的佔比上限",
    description: "此標的市值占總資產(已估值部位市值)的上限（比例，例如 0.15 代表 15%）。",
    defaultValue: 0.15,
    hardCeiling: { max: 0.5, reason: "單一標的超過總資產的一半時，分散化已無實質意義。" },
  },
  {
    key: "max_sector_weight",
    label: "單一產業佔比上限",
    // 風控核可文案 2026-08-09，修改需重新送審（比照 limits.py 慣例）。
    description:
      "同產業合計市值占總資產(已估值部位市值)的上限。產業別是持倉上的欄位,僅台股持倉可填(台灣證交所產業別,可在持倉編輯或 CSV 匯入填寫),非台股持倉不可填。若該標的沒有持倉、未填產業別、為非台股、或同一標的填了不只一種產業別,這條上限不計算並顯示無法評估;未填產業別的持倉不計入任何產業的市值合計,已計算的產業佔比可能因此被低估。",
    defaultValue: 0.3,
  },
  {
    key: "max_gross_exposure",
    label: "總曝險上限",
    description:
      "組合已估值部位市值合計占你在設定頁自報之帳戶總淨值的上限（比例，可大於 1 代表允許槓桿）。",
    defaultValue: 1.0,
    hardCeiling: { max: 1.5, reason: "容許適度槓桿，但不容許 2 倍的總曝險。" },
  },
  {
    key: "max_loss_per_trade",
    label: "單筆最大可承受虧損",
    description: "以 ATR 停損距離估算，觸及停損時損失占總資產(已估值部位市值)的上限。",
    defaultValue: 0.01,
  },
  {
    key: "atr_stop_multiple",
    label: "ATR 停損倍數",
    description: "停損距離 = 此倍數 × ATR(14)。",
    defaultValue: 2.0,
  },
  {
    key: "kelly_fraction_cap",
    label: "分數 Kelly 上限",
    description: "相對於全額 Kelly 的可用比例，僅允許分數 Kelly（最高 0.25）。",
    defaultValue: 0.25,
  },
  {
    key: "kelly_position_cap",
    label: "Kelly 部位硬上限",
    description: "無論 Kelly 估計的邊際多大，此為部位占總資產(已估值部位市值)的絕對上限。",
    defaultValue: 0.1,
  },
];

const COST_FIELDS: FieldSpec<Omit<CostModelSettings, "verified_on">>[] = [
  {
    key: "tw_broker_fee_rate",
    label: "台股手續費率",
    description: "買賣皆收，占成交金額的比例。",
    defaultValue: 0.001425,
  },
  {
    key: "tw_tax_rate_stock",
    label: "台股股票交易稅率",
    description: "僅賣出收取，占成交金額的比例。",
    defaultValue: 0.003,
  },
  {
    key: "tw_tax_rate_etf",
    label: "台股 ETF 交易稅率",
    description: "僅賣出收取，占成交金額的比例，較股票稅率低。",
    defaultValue: 0.001,
  },
  {
    key: "us_broker_fee_rate",
    label: "美股手續費率",
    description: "買賣皆收，占成交金額的比例。",
    defaultValue: 0.0,
  },
  {
    key: "us_sell_regulatory_fee_rate",
    label: "美股賣出監管費率",
    description: "SEC/TAF 概估費率，僅賣出收取。",
    defaultValue: 0.0000278,
  },
  {
    key: "slippage_bps",
    label: "滑價（bps）",
    description: "以成交金額基點計，買賣雙邊對稱套用。",
    defaultValue: 0.0,
  },
];

const ALERT_SETTINGS_FIELDS: FieldSpec<Omit<AlertSettings, "enabled" | "notify_webhooks">>[] = [
  {
    key: "evaluation_interval_minutes",
    label: "警示評估間隔（分鐘）",
    description: "排程多久檢查一次所有啟用中的警示規則。",
    defaultValue: 60,
  },
  {
    key: "cooldown_minutes",
    label: "同一規則的冷卻時間（分鐘）",
    description: "同一條規則再次觸發前的最短間隔；0 代表不設冷卻。",
    defaultValue: 60,
  },
];

type FormValues = Record<string, string>;

function toFormValues(
  riskBudget: RiskBudgetSettings,
  costModel: CostModelSettings,
  alerts: AlertSettings,
): FormValues {
  const values: FormValues = {};
  for (const field of RISK_BUDGET_FIELDS) {
    values[`risk_budget.${String(field.key)}`] = String(riskBudget[field.key]);
  }
  for (const field of COST_FIELDS) {
    values[`cost_model.${String(field.key)}`] = String(costModel[field.key]);
  }
  for (const field of ALERT_SETTINGS_FIELDS) {
    values[`alerts.${String(field.key)}`] = String(alerts[field.key]);
  }
  return values;
}

function FieldError({ message }: { message: string | undefined }) {
  if (!message) return null;
  return <p className="mt-1 text-xs text-red-400">{message}</p>;
}

function NumberField({
  id,
  spec,
  value,
  onChange,
  error,
}: {
  id: string;
  spec: FieldSpec<never>;
  value: string;
  onChange: (value: string) => void;
  error: string | undefined;
}) {
  return (
    <div>
      <label htmlFor={id} className="block text-sm text-neutral-300">
        {spec.label}
      </label>
      {/*
        A text input (not `type="number"`) on purpose: the browser must not be
        the thing that judges the value. Every entry is sent as typed so the
        backend's own bounds answer, and a rejection comes back as the per-field
        422 message rendered below. A `max` attribute would be inert on a text
        input, so the ceiling is stated in the note under the field instead.
      */}
      <input
        id={id}
        inputMode="decimal"
        value={value}
        onChange={(e) => onChange(e.target.value)}
        className="mt-1 w-full rounded-md border border-neutral-700 bg-neutral-900 px-3 py-2 text-sm text-neutral-100"
      />
      <p className="mt-1 text-xs text-neutral-500">
        {spec.description}預設值：{String(spec.defaultValue)}
      </p>
      {spec.hardCeiling && (
        <p className="mt-1 text-xs text-amber-300">
          硬性上界 {String(spec.hardCeiling.max)}：{spec.hardCeiling.reason}
          {HARD_CEILING_NOTE}
        </p>
      )}
      <FieldError message={error} />
    </div>
  );
}

export function SettingsForm({ settings }: { settings: SettingsResponse }) {
  const [values, setValues] = useState<FormValues>(() =>
    toFormValues(settings.settings.risk_budget, settings.settings.cost_model, settings.settings.alerts),
  );
  const [alertsEnabled, setAlertsEnabled] = useState(settings.settings.alerts.enabled);
  const [notifyWebhooks, setNotifyWebhooks] = useState(settings.settings.alerts.notify_webhooks);
  /**
   * S4 fix: one raise per `WIDENING_FIELDS` entry, keyed by field name
   * (`string(field.key)`), rather than the single `max_gross_exposure`-only
   * slot this used to be. A field absent from the map has nothing pending.
   * Each entry's semantics are unchanged from the original single-field
   * design: it is the raise the confirmation panel is currently showing for
   * *that* field, and clicking submit while any entry is set is the
   * confirmation of that exact pair of numbers.
   */
  const [pendingWidenings, setPendingWidenings] = useState<Partial<Record<string, CapWidening>>>({});
  const mutation = useUpdateSettings();
  const fieldErrors = mutation.error instanceof ApiError ? mutation.error.fieldErrors : {};

  /** The raise `field`'s current form value would write, or `null` for none. */
  function fieldWidening(field: keyof RiskBudgetSettings): CapWidening | null {
    return capWidening(settings.settings.risk_budget[field], Number(values[`risk_budget.${String(field)}`]));
  }

  function handleSubmit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    // Re-derived here, at submit time, per field, and compared with whatever
    // that field's confirmation panel is showing: editing a cap after
    // confirming it must re-open that field's confirmation with the new
    // number rather than write a number nobody agreed to. Decision logic
    // lives in `resolveWideningSubmitForFields` (pure, unit-tested) so it is
    // provably right the same way the single-field version was.
    const current: Record<string, CapWidening | null> = {};
    for (const widened of WIDENING_FIELDS) {
      current[String(widened.key)] = fieldWidening(widened.key);
    }
    const decision = resolveWideningSubmitForFields(current, pendingWidenings);
    if (decision.action === "confirm") {
      setPendingWidenings(decision.pending);
      return;
    }
    setPendingWidenings({});
    const riskBudget = {} as RiskBudgetSettings;
    for (const field of RISK_BUDGET_FIELDS) {
      riskBudget[field.key] = Number(values[`risk_budget.${String(field.key)}`]);
    }
    const costModelPartial = {} as Omit<CostModelSettings, "verified_on">;
    for (const field of COST_FIELDS) {
      costModelPartial[field.key] = Number(values[`cost_model.${String(field.key)}`]);
    }
    const costModel: CostModelSettings = {
      ...costModelPartial,
      verified_on: settings.settings.cost_model.verified_on,
    };
    const alertsPartial = {} as Omit<AlertSettings, "enabled" | "notify_webhooks">;
    for (const field of ALERT_SETTINGS_FIELDS) {
      alertsPartial[field.key] = Number(values[`alerts.${String(field.key)}`]);
    }
    const alerts: AlertSettings = {
      ...alertsPartial,
      enabled: alertsEnabled,
      notify_webhooks: notifyWebhooks,
    };
    mutation.mutate({ risk_budget: riskBudget, cost_model: costModel, alerts });
  }

  return (
    <form onSubmit={handleSubmit} className="space-y-8">
      <section className="rounded-lg border border-neutral-800 p-5">
        <h2 className="text-lg font-semibold text-neutral-100">風險預算（RiskBudget）</h2>
        <p className="mt-1 text-xs text-neutral-500">
          每一項數字都是分數（例如 0.15 = 15%），與後端 `app/advice/limits.py` 的 RiskBudget 欄位一一對應。
        </p>
        <div className="mt-4 grid grid-cols-1 gap-4 sm:grid-cols-2">
          {RISK_BUDGET_FIELDS.map((field) => {
            const key = `risk_budget.${String(field.key)}`;
            return (
              <NumberField
                key={key}
                id={key}
                spec={field as FieldSpec<never>}
                value={values[key] ?? ""}
                onChange={(v) => setValues((prev) => ({ ...prev, [key]: v }))}
                error={fieldErrors[String(field.key)]}
              />
            );
          })}
        </div>
      </section>

      <section className="rounded-lg border border-neutral-800 p-5">
        <div className="flex flex-wrap items-center justify-between gap-2">
          <h2 className="text-lg font-semibold text-neutral-100">費率（回測 CostModel）</h2>
          <span className="rounded bg-neutral-800 px-2 py-0.5 text-xs text-neutral-300">
            查證狀態：
            {settings.settings.cost_model.verified_on
              ? `已查證（${settings.settings.cost_model.verified_on}）`
              : "尚未查證"}
          </span>
        </div>
        {settings.settings.cost_model.verified_on === null && (
          <p className="mt-2 text-xs text-amber-300">
            這些費率來自模型訓練知識，尚未對照主要來源（TWSE/FSC、SEC/FINRA）查證，回測結果應視為待查證狀態。
          </p>
        )}
        <div className="mt-4 grid grid-cols-1 gap-4 sm:grid-cols-2">
          {COST_FIELDS.map((field) => {
            const key = `cost_model.${String(field.key)}`;
            return (
              <NumberField
                key={key}
                id={key}
                spec={field as FieldSpec<never>}
                value={values[key] ?? ""}
                onChange={(v) => setValues((prev) => ({ ...prev, [key]: v }))}
                error={fieldErrors[String(field.key)]}
              />
            );
          })}
        </div>
      </section>

      <section className="rounded-lg border border-neutral-800 p-5">
        <h2 className="text-lg font-semibold text-neutral-100">警示排程</h2>
        <div className="mt-4 grid grid-cols-1 gap-4 sm:grid-cols-2">
          {ALERT_SETTINGS_FIELDS.map((field) => {
            const key = `alerts.${String(field.key)}`;
            return (
              <NumberField
                key={key}
                id={key}
                spec={field as FieldSpec<never>}
                value={values[key] ?? ""}
                onChange={(v) => setValues((prev) => ({ ...prev, [key]: v }))}
                error={fieldErrors[String(field.key)]}
              />
            );
          })}
          <div>
            <label className="flex items-center gap-2 text-sm text-neutral-300">
              <input
                type="checkbox"
                checked={alertsEnabled}
                onChange={(e) => setAlertsEnabled(e.target.checked)}
                className="h-4 w-4"
              />
              啟用警示排程（總開關）
            </label>
          </div>
          <div>
            <label className="flex items-center gap-2 text-sm text-neutral-300">
              <input
                type="checkbox"
                checked={notifyWebhooks}
                onChange={(e) => setNotifyWebhooks(e.target.checked)}
                className="h-4 w-4"
              />
              觸發時推送至已設定的 webhook
            </label>
          </div>
        </div>
      </section>

      <div>
        {Object.keys(pendingWidenings).length > 0 && (
          <div
            role="alert"
            className="mb-3 rounded-md border border-amber-700 bg-amber-950/50 px-4 py-3 text-sm text-amber-200"
          >
            <p className="font-semibold">{RISK_WIDENING_TITLE}</p>
            {WIDENING_FIELDS.map((widened) => {
              const widening = pendingWidenings[String(widened.key)];
              if (!widening) return null;
              return (
                <p key={String(widened.key)} className="mt-1">
                  {buildWideningBody(widened.label, widened.limitIndex, widening.before, widening.after)}
                </p>
              );
            })}
            <button
              type="button"
              onClick={() => setPendingWidenings({})}
              className="mt-2 rounded-md border border-amber-700 px-3 py-1 text-xs text-amber-200 hover:bg-amber-900/40"
            >
              取消，維持原設定
            </button>
          </div>
        )}
        <button
          type="submit"
          disabled={mutation.isPending}
          className="rounded-md bg-neutral-100 px-4 py-2 text-sm font-medium text-neutral-900 hover:bg-white disabled:cursor-not-allowed disabled:opacity-50"
        >
          {mutation.isPending
            ? "儲存中…"
            : Object.keys(pendingWidenings).length > 0
              ? "我了解，仍要放寬並儲存"
              : "儲存設定"}
        </button>
        {mutation.isError && Object.keys(fieldErrors).length === 0 && (
          <p role="alert" className="mt-3 rounded-md border border-red-900 bg-red-950/40 px-4 py-3 text-sm text-red-300">
            儲存失敗：{mutation.error instanceof ApiError ? mutation.error.message : "未知錯誤"}
          </p>
        )}
        {mutation.isSuccess && (
          <p role="status" className="mt-3 rounded-md border border-emerald-900 bg-emerald-950/40 px-4 py-3 text-sm text-emerald-300">
            設定已儲存。
          </p>
        )}
      </div>
    </form>
  );
}

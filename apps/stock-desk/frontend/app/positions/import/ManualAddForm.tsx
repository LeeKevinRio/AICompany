"use client";

import { useState } from "react";
import { ApiError } from "../../lib/api";
import { CURRENCY_OPTIONS, INSTRUMENT_TYPE_OPTIONS, MARKET_OPTIONS } from "../../lib/format";
import { useCreatePosition } from "../../lib/queries";
import type { CreatePositionInput, Currency, InstrumentType, Market } from "../../lib/types";

interface FormState {
  symbol: string;
  market: Market | "";
  instrument_type: InstrumentType | "";
  quantity: string;
  avg_cost: string;
  currency: Currency | "";
  opened_at: string;
  note: string;
}

const EMPTY_FORM: FormState = {
  symbol: "",
  market: "",
  instrument_type: "",
  quantity: "",
  avg_cost: "",
  currency: "",
  opened_at: "",
  note: "",
};

const FIELD_LABELS: Record<keyof FormState, string> = {
  symbol: "代號",
  market: "市場",
  instrument_type: "類型",
  quantity: "數量",
  avg_cost: "平均成本（原幣）",
  currency: "幣別",
  opened_at: "建倉日期",
  note: "備註",
};

function FieldError({ message }: { message: string | undefined }) {
  if (!message) return null;
  return <p className="mt-1 text-xs text-red-400">{message}</p>;
}

export function ManualAddForm() {
  const [form, setForm] = useState<FormState>(EMPTY_FORM);
  const createMutation = useCreatePosition();

  const fieldErrors = createMutation.error instanceof ApiError ? createMutation.error.fieldErrors : {};

  function updateField<K extends keyof FormState>(key: K, value: FormState[K]) {
    setForm((prev) => ({ ...prev, [key]: value }));
  }

  function handleSubmit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    // `required` on the three <select>s below prevents submission while any
    // of them is still at its empty placeholder value.
    if (form.market === "" || form.instrument_type === "" || form.currency === "") return;
    const payload: CreatePositionInput = {
      symbol: form.symbol.trim(),
      market: form.market,
      instrument_type: form.instrument_type,
      quantity: form.quantity.trim(),
      avg_cost: form.avg_cost.trim(),
      currency: form.currency,
      opened_at: form.opened_at.trim(),
      note: form.note.trim() === "" ? null : form.note.trim(),
    };
    createMutation.mutate(payload, {
      onSuccess: () => setForm(EMPTY_FORM),
    });
  }

  return (
    <section className="rounded-lg border border-neutral-800 p-5">
      <h2 className="text-lg font-semibold text-neutral-100">手動新增部位</h2>
      <form onSubmit={handleSubmit} className="mt-4 grid grid-cols-1 gap-4 sm:grid-cols-2">
        <div>
          <label htmlFor="symbol" className="block text-sm text-neutral-400">
            {FIELD_LABELS.symbol}
          </label>
          <input
            id="symbol"
            required
            value={form.symbol}
            onChange={(e) => updateField("symbol", e.target.value)}
            placeholder="例如 2330"
            className="mt-1 w-full rounded-md border border-neutral-700 bg-neutral-900 px-3 py-2 text-sm text-neutral-100"
          />
          <FieldError message={fieldErrors.symbol} />
        </div>

        <div>
          <label htmlFor="market" className="block text-sm text-neutral-400">
            {FIELD_LABELS.market}
          </label>
          <select
            id="market"
            required
            value={form.market}
            onChange={(e) => updateField("market", e.target.value as Market)}
            className="mt-1 w-full rounded-md border border-neutral-700 bg-neutral-900 px-3 py-2 text-sm text-neutral-100"
          >
            <option value="" disabled>
              請選擇
            </option>
            {MARKET_OPTIONS.map((opt) => (
              <option key={opt.value} value={opt.value}>
                {opt.label}
              </option>
            ))}
          </select>
          <FieldError message={fieldErrors.market} />
        </div>

        <div>
          <label htmlFor="instrument_type" className="block text-sm text-neutral-400">
            {FIELD_LABELS.instrument_type}
          </label>
          <select
            id="instrument_type"
            required
            value={form.instrument_type}
            onChange={(e) => updateField("instrument_type", e.target.value as InstrumentType)}
            className="mt-1 w-full rounded-md border border-neutral-700 bg-neutral-900 px-3 py-2 text-sm text-neutral-100"
          >
            <option value="" disabled>
              請選擇
            </option>
            {INSTRUMENT_TYPE_OPTIONS.map((opt) => (
              <option key={opt.value} value={opt.value}>
                {opt.label}
              </option>
            ))}
          </select>
          <FieldError message={fieldErrors.instrument_type} />
        </div>

        <div>
          <label htmlFor="currency" className="block text-sm text-neutral-400">
            {FIELD_LABELS.currency}
          </label>
          <select
            id="currency"
            required
            value={form.currency}
            onChange={(e) => updateField("currency", e.target.value as Currency)}
            className="mt-1 w-full rounded-md border border-neutral-700 bg-neutral-900 px-3 py-2 text-sm text-neutral-100"
          >
            <option value="" disabled>
              請選擇
            </option>
            {CURRENCY_OPTIONS.map((opt) => (
              <option key={opt.value} value={opt.value}>
                {opt.label}
              </option>
            ))}
          </select>
          <FieldError message={fieldErrors.currency} />
        </div>

        <div>
          <label htmlFor="quantity" className="block text-sm text-neutral-400">
            {FIELD_LABELS.quantity}
          </label>
          <input
            id="quantity"
            required
            inputMode="decimal"
            value={form.quantity}
            onChange={(e) => updateField("quantity", e.target.value)}
            placeholder="例如 1000"
            className="mt-1 w-full rounded-md border border-neutral-700 bg-neutral-900 px-3 py-2 text-sm text-neutral-100"
          />
          <FieldError message={fieldErrors.quantity} />
        </div>

        <div>
          <label htmlFor="avg_cost" className="block text-sm text-neutral-400">
            {FIELD_LABELS.avg_cost}
          </label>
          <input
            id="avg_cost"
            required
            inputMode="decimal"
            value={form.avg_cost}
            onChange={(e) => updateField("avg_cost", e.target.value)}
            placeholder="例如 605.5"
            className="mt-1 w-full rounded-md border border-neutral-700 bg-neutral-900 px-3 py-2 text-sm text-neutral-100"
          />
          <FieldError message={fieldErrors.avg_cost} />
        </div>

        <div>
          <label htmlFor="opened_at" className="block text-sm text-neutral-400">
            {FIELD_LABELS.opened_at}
          </label>
          <input
            id="opened_at"
            type="date"
            required
            value={form.opened_at}
            onChange={(e) => updateField("opened_at", e.target.value)}
            className="mt-1 w-full rounded-md border border-neutral-700 bg-neutral-900 px-3 py-2 text-sm text-neutral-100"
          />
          <FieldError message={fieldErrors.opened_at} />
        </div>

        <div className="sm:col-span-2">
          <label htmlFor="note" className="block text-sm text-neutral-400">
            {FIELD_LABELS.note}（選填）
          </label>
          <input
            id="note"
            value={form.note}
            onChange={(e) => updateField("note", e.target.value)}
            className="mt-1 w-full rounded-md border border-neutral-700 bg-neutral-900 px-3 py-2 text-sm text-neutral-100"
          />
          <FieldError message={fieldErrors.note} />
        </div>

        <div className="sm:col-span-2">
          <button
            type="submit"
            disabled={createMutation.isPending}
            className="rounded-md bg-neutral-100 px-4 py-2 text-sm font-medium text-neutral-900 hover:bg-white disabled:cursor-not-allowed disabled:opacity-50"
          >
            {createMutation.isPending ? "新增中…" : "新增部位"}
          </button>
        </div>
      </form>

      {createMutation.isError && Object.keys(fieldErrors).length === 0 && (
        <p role="alert" className="mt-4 rounded-md border border-red-900 bg-red-950/40 px-4 py-3 text-sm text-red-300">
          新增失敗：
          {createMutation.error instanceof ApiError ? createMutation.error.message : "未知錯誤"}
        </p>
      )}

      {createMutation.isSuccess && (
        <p role="status" className="mt-4 rounded-md border border-emerald-900 bg-emerald-950/40 px-4 py-3 text-sm text-emerald-300">
          已新增部位「{createMutation.data.symbol}」
        </p>
      )}
    </section>
  );
}

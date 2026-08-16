"use client";

import { useState } from "react";
import { ApiError } from "../../lib/api";
import { ErrorPanel } from "../../components/ErrorPanel";
import { SymbolCombobox } from "../../components/SymbolCombobox";
import { applyDirectorySelection, sectorAfterDirectorySelection } from "../../lib/directorySearch";
import {
  CURRENCY_OPTIONS,
  INSTRUMENT_TYPE_OPTIONS,
  MARKET_OPTIONS,
  SECTOR_SOURCE_DISCLOSURE,
  SECTOR_US_DISABLED_HINT,
} from "../../lib/format";
import { shouldBlockPositionSubmit, submitButtonState } from "../../lib/positionFormSubmit";
import { useCreatePosition, useSectors } from "../../lib/queries";
import type {
  CreatePositionInput,
  Currency,
  DirectoryItem,
  InstrumentType,
  Market,
} from "../../lib/types";

interface FormState {
  symbol: string;
  market: Market | "";
  instrument_type: InstrumentType | "";
  quantity: string;
  avg_cost: string;
  currency: Currency | "";
  opened_at: string;
  sector: string;
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
  sector: "",
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
  sector: "產業別",
  note: "備註",
};

function FieldError({ message }: { message: string | undefined }) {
  if (!message) return null;
  return <p className="mt-1 text-xs text-red-400">{message}</p>;
}

export function ManualAddForm() {
  const [form, setForm] = useState<FormState>(EMPTY_FORM);
  const createMutation = useCreatePosition();
  const sectors = useSectors(true);

  const fieldErrors = createMutation.error instanceof ApiError ? createMutation.error.fieldErrors : {};
  const submitButton = submitButtonState(createMutation.isPending, "新增部位", "新增中…");

  function updateField<K extends keyof FormState>(key: K, value: FormState[K]) {
    setForm((prev) => ({ ...prev, [key]: value }));
  }

  // AC-12.6: a sector only ever applies to a TW position, so switching market
  // away from TW clears whatever is selected rather than submitting a value
  // the backend would reject. Mirrors `EditPositionModal`'s handler.
  function handleMarketChange(value: Market) {
    setForm((prev) => ({ ...prev, market: value, sector: value === "TW" ? prev.sector : "" }));
  }

  // Picking a candidate fills 代號/市場 and offers the directory's 產業別 as the
  // field's default; `sectorAfterDirectorySelection` owns the never-overwrite
  // and never-guess rules (CEO 指示 2026-08-16).
  function handleSelectSymbolCandidate(item: DirectoryItem) {
    setForm((prev) => ({
      ...applyDirectorySelection(prev, item),
      sector: sectorAfterDirectorySelection({
        item,
        previousSymbol: prev.symbol,
        previousSector: prev.sector,
      }),
    }));
  }

  function handleSubmit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    // CEO 實測 2026-08-16 (EditPositionModal 同批體檢): an Enter-key implicit
    // form submission can bypass the 新增 button's own `disabled` — guard the
    // handler itself so a second mutate() can never fire mid-request.
    if (shouldBlockPositionSubmit(createMutation.isPending)) return;
    // `required` on the three <select>s below prevents submission while any
    // of them is still at its empty placeholder value.
    if (form.market === "" || form.instrument_type === "" || form.currency === "") return;
    const trimmedSector = form.sector.trim();
    const payload: CreatePositionInput = {
      symbol: form.symbol.trim(),
      market: form.market,
      instrument_type: form.instrument_type,
      quantity: form.quantity.trim(),
      avg_cost: form.avg_cost.trim(),
      currency: form.currency,
      opened_at: form.opened_at.trim() === "" ? null : form.opened_at.trim(),
      // Whatever the field shows is what gets stored — a pre-filled value is
      // submitted through the exact same path a hand-picked one is.
      sector: form.market === "TW" && trimmedSector !== "" ? trimmedSector : null,
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
          <SymbolCombobox
            id="symbol"
            required
            value={form.symbol}
            onChange={(value) => updateField("symbol", value)}
            onSelect={handleSelectSymbolCandidate}
            placeholder="例如 2330"
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
            onChange={(e) => handleMarketChange(e.target.value as Market)}
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
            {FIELD_LABELS.opened_at}（選填）
          </label>
          <input
            id="opened_at"
            type="date"
            value={form.opened_at}
            onChange={(e) => updateField("opened_at", e.target.value)}
            className="mt-1 w-full rounded-md border border-neutral-700 bg-neutral-900 px-3 py-2 text-sm text-neutral-100"
          />
          <FieldError message={fieldErrors.opened_at} />
        </div>

        <div>
          <label htmlFor="sector" className="block text-sm text-neutral-400">
            {FIELD_LABELS.sector}（選填）
          </label>
          <select
            id="sector"
            value={form.sector}
            disabled={form.market !== "TW" || sectors.isPending}
            onChange={(e) => updateField("sector", e.target.value)}
            className="mt-1 w-full rounded-md border border-neutral-700 bg-neutral-900 px-3 py-2 text-sm text-neutral-100 disabled:opacity-50"
          >
            <option value="">未填</option>
            {(sectors.data?.items ?? []).map((name) => (
              <option key={name} value={name}>
                {name}
              </option>
            ))}
          </select>
          {form.market === "TW" && (
            // Next to the field, not next to a value — the copy states where
            // the default comes from and deliberately does not mark which
            // values were pre-filled (see SECTOR_SOURCE_DISCLOSURE).
            <p className="mt-1 text-xs text-neutral-400">{SECTOR_SOURCE_DISCLOSURE}</p>
          )}
          {form.market !== "TW" && form.market !== "" && (
            <p className="mt-1 text-xs text-neutral-500">{SECTOR_US_DISABLED_HINT}</p>
          )}
          {form.market === "TW" && sectors.isPending && (
            <p className="mt-1 text-xs text-neutral-500">載入產業別中…</p>
          )}
          {form.market === "TW" && sectors.isError && (
            <p className="mt-1 text-xs text-red-400">
              無法載入產業別清單：
              {sectors.error instanceof ApiError ? sectors.error.message : "未知錯誤"}
            </p>
          )}
          <FieldError message={fieldErrors.sector} />
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
            disabled={submitButton.disabled}
            className="rounded-md bg-neutral-100 px-4 py-2 text-sm font-medium text-neutral-900 hover:bg-white disabled:cursor-not-allowed disabled:opacity-50"
          >
            {submitButton.label}
          </button>
        </div>
      </form>

      {createMutation.isError && Object.keys(fieldErrors).length === 0 && (
        <div className="mt-4">
          <ErrorPanel label="新增失敗" error={createMutation.error} />
        </div>
      )}

      {createMutation.isSuccess && (
        <p role="status" className="mt-4 rounded-md border border-emerald-900 bg-emerald-950/40 px-4 py-3 text-sm text-emerald-300">
          已新增部位「{createMutation.data.symbol}」
        </p>
      )}
    </section>
  );
}

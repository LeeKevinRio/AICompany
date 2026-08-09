"use client";

import { useEffect, useState } from "react";
import { ApiError } from "../lib/api";
import { SymbolCombobox } from "./SymbolCombobox";
import { applyDirectorySelection } from "../lib/directorySearch";
import {
  CURRENCY_OPTIONS,
  INSTRUMENT_TYPE_OPTIONS,
  MARKET_OPTIONS,
  SECTOR_US_DISABLED_HINT,
} from "../lib/format";
import { useSectors, useUpdatePosition } from "../lib/queries";
import type {
  Currency,
  DirectoryItem,
  InstrumentType,
  Market,
  SummaryPositionItem,
  UpdatePositionInput,
} from "../lib/types";

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

// `SummaryPositionItem` carries every `PositionInput` field plus `id`, so
// the edit form can be pre-filled from the row the user clicked without an
// extra fetch.
function toFormState(position: SummaryPositionItem): FormState {
  return {
    symbol: position.symbol,
    market: position.market,
    instrument_type: position.instrument_type,
    quantity: position.quantity,
    avg_cost: position.avg_cost,
    currency: position.currency,
    opened_at: position.opened_at ?? "",
    sector: position.sector ?? "",
    note: position.note ?? "",
  };
}

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

// AC-12.6: a sector only ever applies to a TW position — shared by
// `handleMarketChange` (manual `<select>`) and the symbol combobox's
// `onSelect` (a directory candidate carries its own market) so the same
// clearing rule is not duplicated between the two entry points.
function sectorForMarket(market: Market, currentSector: string): string {
  return market === "TW" ? currentSector : "";
}

/**
 * Modal form to edit an existing position (`PUT /api/positions/{id}`).
 * Mirrors `ManualAddForm`'s field set and styling; kept as a separate
 * component because it edits a specific stored row (pre-filled values, PUT
 * instead of POST) rather than starting from a blank form.
 */
export function EditPositionModal({
  position,
  onClose,
}: {
  position: SummaryPositionItem;
  onClose: () => void;
}) {
  const [form, setForm] = useState<FormState>(() => toFormState(position));
  const updateMutation = useUpdatePosition();
  const sectors = useSectors(true);

  const fieldErrors =
    updateMutation.error instanceof ApiError ? updateMutation.error.fieldErrors : {};

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

  // `sector` only applies to a TW position (AC-12.6); switching away from TW
  // clears whatever was selected so the submit never carries a value the
  // backend would reject.
  function handleMarketChange(value: Market) {
    setForm((prev) => ({ ...prev, market: value, sector: sectorForMarket(value, prev.sector) }));
  }

  function handleSelectSymbolCandidate(item: DirectoryItem) {
    setForm((prev) => ({
      ...applyDirectorySelection(prev, item),
      sector: sectorForMarket(item.market, prev.sector),
    }));
  }

  function handleSubmit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    // `required` on the three <select>s below prevents submission while any
    // of them is still at its empty placeholder value.
    if (form.market === "" || form.instrument_type === "" || form.currency === "") return;
    const trimmedOpenedAt = form.opened_at.trim();
    const trimmedSector = form.sector.trim();
    const payload: UpdatePositionInput = {
      symbol: form.symbol.trim(),
      market: form.market,
      instrument_type: form.instrument_type,
      quantity: form.quantity.trim(),
      avg_cost: form.avg_cost.trim(),
      currency: form.currency,
      opened_at: trimmedOpenedAt === "" ? null : trimmedOpenedAt,
      sector: form.market === "TW" && trimmedSector !== "" ? trimmedSector : null,
      note: form.note.trim() === "" ? null : form.note.trim(),
    };
    updateMutation.mutate(
      { id: position.id, input: payload },
      { onSuccess: () => onClose() },
    );
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
        aria-labelledby="edit-position-title"
        className="max-h-full w-full max-w-lg overflow-y-auto rounded-lg border border-neutral-800 bg-neutral-950 p-5"
      >
        <div className="flex items-center justify-between">
          <h2 id="edit-position-title" className="text-lg font-semibold text-neutral-100">
            編輯部位「{position.symbol}」
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

        <form onSubmit={handleSubmit} className="mt-4 grid grid-cols-1 gap-4 sm:grid-cols-2">
          <div>
            <label htmlFor="edit-symbol" className="block text-sm text-neutral-400">
              {FIELD_LABELS.symbol}
            </label>
            <SymbolCombobox
              id="edit-symbol"
              required
              value={form.symbol}
              onChange={(value) => updateField("symbol", value)}
              onSelect={handleSelectSymbolCandidate}
            />
            <FieldError message={fieldErrors.symbol} />
          </div>

          <div>
            <label htmlFor="edit-market" className="block text-sm text-neutral-400">
              {FIELD_LABELS.market}
            </label>
            <select
              id="edit-market"
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
            <label htmlFor="edit-instrument_type" className="block text-sm text-neutral-400">
              {FIELD_LABELS.instrument_type}
            </label>
            <select
              id="edit-instrument_type"
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
            <label htmlFor="edit-currency" className="block text-sm text-neutral-400">
              {FIELD_LABELS.currency}
            </label>
            <select
              id="edit-currency"
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
            <label htmlFor="edit-quantity" className="block text-sm text-neutral-400">
              {FIELD_LABELS.quantity}
            </label>
            <input
              id="edit-quantity"
              required
              inputMode="decimal"
              value={form.quantity}
              onChange={(e) => updateField("quantity", e.target.value)}
              className="mt-1 w-full rounded-md border border-neutral-700 bg-neutral-900 px-3 py-2 text-sm text-neutral-100"
            />
            <FieldError message={fieldErrors.quantity} />
          </div>

          <div>
            <label htmlFor="edit-avg_cost" className="block text-sm text-neutral-400">
              {FIELD_LABELS.avg_cost}
            </label>
            <input
              id="edit-avg_cost"
              required
              inputMode="decimal"
              value={form.avg_cost}
              onChange={(e) => updateField("avg_cost", e.target.value)}
              className="mt-1 w-full rounded-md border border-neutral-700 bg-neutral-900 px-3 py-2 text-sm text-neutral-100"
            />
            <FieldError message={fieldErrors.avg_cost} />
          </div>

          <div>
            <label htmlFor="edit-opened_at" className="block text-sm text-neutral-400">
              {FIELD_LABELS.opened_at}（選填）
            </label>
            <input
              id="edit-opened_at"
              type="date"
              value={form.opened_at}
              onChange={(e) => updateField("opened_at", e.target.value)}
              className="mt-1 w-full rounded-md border border-neutral-700 bg-neutral-900 px-3 py-2 text-sm text-neutral-100"
            />
            <FieldError message={fieldErrors.opened_at} />
          </div>

          <div>
            <label htmlFor="edit-sector" className="block text-sm text-neutral-400">
              {FIELD_LABELS.sector}（選填）
            </label>
            <select
              id="edit-sector"
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
            {form.market !== "TW" && (
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
            <label htmlFor="edit-note" className="block text-sm text-neutral-400">
              {FIELD_LABELS.note}（選填）
            </label>
            <input
              id="edit-note"
              value={form.note}
              onChange={(e) => updateField("note", e.target.value)}
              className="mt-1 w-full rounded-md border border-neutral-700 bg-neutral-900 px-3 py-2 text-sm text-neutral-100"
            />
            <FieldError message={fieldErrors.note} />
          </div>

          <div className="flex gap-3 sm:col-span-2">
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

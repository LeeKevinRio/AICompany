"use client";

import { useEffect, useState } from "react";
import { ApiError } from "../lib/api";
import { INSTRUMENT_TYPE_OPTIONS, MARKET_OPTIONS, STRATEGY_OPTIONS } from "../lib/format";
import { parseRequiredNumbers, unplacedFieldErrors } from "../lib/formErrors";
import { useRunBacktest, useSettings } from "../lib/queries";
import type { FormSnapshot } from "../lib/eventStudy";
import type {
  BacktestRequest,
  BacktestResponse,
  BacktestStrategy,
  CostModelSettings,
  InstrumentType,
  Market,
} from "../lib/types";

interface FormState {
  symbol: string;
  market: Market;
  instrument_type: InstrumentType;
  strategy: BacktestStrategy;
  start: string;
  end: string;
  initial_cash: string;
  train_size: string;
  test_size: string;
  override_slippage: boolean;
  slippage_bps: string;
}

type NumericKey = "initial_cash" | "train_size" | "test_size" | "slippage_bps";

/** Bare field names the backend's 422 `loc` can name and this form renders. */
const PLACED_ERROR_KEYS = ["symbol", "start", "end", "initial_cash", "train_size", "test_size", "slippage_bps"];

const EMPTY_FORM: FormState = {
  symbol: "",
  market: "TW",
  instrument_type: "stock",
  strategy: "ma_cross",
  start: "",
  end: "",
  initial_cash: "1000000",
  train_size: "252",
  test_size: "63",
  override_slippage: false,
  slippage_bps: "0",
};

export function BacktestForm({
  onResult,
  onFormChange,
}: {
  /** The report and the exact request that produced it (the event study is keyed to that request). */
  onResult: (report: BacktestResponse, request: BacktestRequest) => void;
  /** Live form values, so the page can tell when the form has drifted from the displayed report (風控 REQ-W5). */
  onFormChange?: (snapshot: FormSnapshot) => void;
}) {
  const [form, setForm] = useState<FormState>(EMPTY_FORM);
  useEffect(() => {
    onFormChange?.({
      symbol: form.symbol,
      market: form.market,
      strategy: form.strategy,
      start: form.start,
      end: form.end,
    });
  }, [form.symbol, form.market, form.strategy, form.start, form.end, onFormChange]);
  const mutation = useRunBacktest();
  // Only fetched to build a full `CostModelSettings` override (the backend
  // model has no "just this one field" patch for the per-run `cost` override —
  // see app/api/backtest.py `BacktestRequest.cost: CostModelSettings | None`).
  const settings = useSettings(form.override_slippage);
  const serverFieldErrors = mutation.error instanceof ApiError ? mutation.error.fieldErrors : {};
  /** Blank or non-numeric entries caught before submit; cleared as the field is edited. */
  const [inputErrors, setInputErrors] = useState<Partial<Record<NumericKey, string>>>({});
  const fieldErrors: Partial<Record<string, string>> = { ...serverFieldErrors, ...inputErrors };
  const unplaced = unplacedFieldErrors(serverFieldErrors, PLACED_ERROR_KEYS);

  function updateField<K extends keyof FormState>(key: K, value: FormState[K]) {
    setForm((prev) => ({ ...prev, [key]: value }));
    // Unticking the override hides the slippage field, so its error goes too.
    const cleared = key === "override_slippage" ? "slippage_bps" : key;
    setInputErrors((prev) => ({ ...prev, [cleared]: undefined }));
  }

  function handleSubmit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    // `Number("")` is 0 and `Number("1,000,000")` is NaN (sent as null): both
    // used to come back as a 422 on a field with no message slot, so nothing
    // was shown and the previous report stayed on screen as if it were new.
    const parsed = parseRequiredNumbers({
      initial_cash: form.initial_cash,
      train_size: form.train_size,
      test_size: form.test_size,
      ...(form.override_slippage ? { slippage_bps: form.slippage_bps } : {}),
    } as Record<NumericKey, string>);
    if (Object.keys(parsed.errors).length > 0) {
      setInputErrors(parsed.errors);
      // The previous run's error belongs to a request this submit replaced.
      mutation.reset();
      return;
    }
    let cost: CostModelSettings | undefined;
    if (form.override_slippage && settings.data) {
      cost = { ...settings.data.settings.cost_model, slippage_bps: parsed.values.slippage_bps };
    }
    const payload: BacktestRequest = {
      symbol: form.symbol.trim(),
      market: form.market,
      strategy: form.strategy,
      start: form.start,
      end: form.end,
      instrument_type: form.instrument_type,
      initial_cash: parsed.values.initial_cash,
      train_size: parsed.values.train_size,
      test_size: parsed.values.test_size,
      cost,
    };
    mutation.mutate(payload, {
      onSuccess: (data) => onResult(data, payload),
    });
  }

  return (
    <section className="rounded-lg border border-neutral-800 p-5">
      <h2 className="text-lg font-semibold text-neutral-100">回測參數</h2>
      <form onSubmit={handleSubmit} className="mt-4 grid grid-cols-1 gap-4 sm:grid-cols-2">
        <div>
          <label htmlFor="bt-symbol" className="block text-sm text-neutral-400">
            股票代號
          </label>
          <input
            id="bt-symbol"
            required
            value={form.symbol}
            onChange={(e) => updateField("symbol", e.target.value)}
            placeholder="例如 2330"
            className="mt-1 w-full rounded-md border border-neutral-700 bg-neutral-900 px-3 py-2 text-sm text-neutral-100"
          />
          {fieldErrors.symbol && <p className="mt-1 text-xs text-red-400">{fieldErrors.symbol}</p>}
        </div>

        <div>
          <label htmlFor="bt-market" className="block text-sm text-neutral-400">
            市場
          </label>
          <select
            id="bt-market"
            value={form.market}
            onChange={(e) => updateField("market", e.target.value as Market)}
            className="mt-1 w-full rounded-md border border-neutral-700 bg-neutral-900 px-3 py-2 text-sm text-neutral-100"
          >
            {MARKET_OPTIONS.map((opt) => (
              <option key={opt.value} value={opt.value}>
                {opt.label}
              </option>
            ))}
          </select>
        </div>

        <div>
          <label htmlFor="bt-instrument" className="block text-sm text-neutral-400">
            類型
          </label>
          <select
            id="bt-instrument"
            value={form.instrument_type}
            onChange={(e) => updateField("instrument_type", e.target.value as InstrumentType)}
            className="mt-1 w-full rounded-md border border-neutral-700 bg-neutral-900 px-3 py-2 text-sm text-neutral-100"
          >
            {INSTRUMENT_TYPE_OPTIONS.map((opt) => (
              <option key={opt.value} value={opt.value}>
                {opt.label}
              </option>
            ))}
          </select>
        </div>

        <div>
          <label htmlFor="bt-strategy" className="block text-sm text-neutral-400">
            策略
          </label>
          <select
            id="bt-strategy"
            value={form.strategy}
            onChange={(e) => updateField("strategy", e.target.value as BacktestStrategy)}
            className="mt-1 w-full rounded-md border border-neutral-700 bg-neutral-900 px-3 py-2 text-sm text-neutral-100"
          >
            {STRATEGY_OPTIONS.map((opt) => (
              <option key={opt.value} value={opt.value}>
                {opt.label}
              </option>
            ))}
          </select>
        </div>

        <div>
          <label htmlFor="bt-start" className="block text-sm text-neutral-400">
            開始日期
          </label>
          <input
            id="bt-start"
            type="date"
            required
            value={form.start}
            onChange={(e) => updateField("start", e.target.value)}
            className="mt-1 w-full rounded-md border border-neutral-700 bg-neutral-900 px-3 py-2 text-sm text-neutral-100"
          />
          {fieldErrors.start && <p className="mt-1 text-xs text-red-400">{fieldErrors.start}</p>}
        </div>

        <div>
          <label htmlFor="bt-end" className="block text-sm text-neutral-400">
            結束日期
          </label>
          <input
            id="bt-end"
            type="date"
            required
            value={form.end}
            onChange={(e) => updateField("end", e.target.value)}
            className="mt-1 w-full rounded-md border border-neutral-700 bg-neutral-900 px-3 py-2 text-sm text-neutral-100"
          />
          {fieldErrors.end && <p className="mt-1 text-xs text-red-400">{fieldErrors.end}</p>}
        </div>

        <div>
          <label htmlFor="bt-cash" className="block text-sm text-neutral-400">
            起始資金
          </label>
          <input
            id="bt-cash"
            inputMode="decimal"
            value={form.initial_cash}
            onChange={(e) => updateField("initial_cash", e.target.value)}
            className="mt-1 w-full rounded-md border border-neutral-700 bg-neutral-900 px-3 py-2 text-sm text-neutral-100"
          />
          {fieldErrors.initial_cash && <p className="mt-1 text-xs text-red-400">{fieldErrors.initial_cash}</p>}
        </div>

        <div className="grid grid-cols-2 gap-2">
          <div>
            <label htmlFor="bt-train" className="block text-sm text-neutral-400">
              樣本內天數
            </label>
            <input
              id="bt-train"
              inputMode="numeric"
              value={form.train_size}
              onChange={(e) => updateField("train_size", e.target.value)}
              className="mt-1 w-full rounded-md border border-neutral-700 bg-neutral-900 px-3 py-2 text-sm text-neutral-100"
            />
            {fieldErrors.train_size && <p className="mt-1 text-xs text-red-400">{fieldErrors.train_size}</p>}
          </div>
          <div>
            <label htmlFor="bt-test" className="block text-sm text-neutral-400">
              樣本外天數
            </label>
            <input
              id="bt-test"
              inputMode="numeric"
              value={form.test_size}
              onChange={(e) => updateField("test_size", e.target.value)}
              className="mt-1 w-full rounded-md border border-neutral-700 bg-neutral-900 px-3 py-2 text-sm text-neutral-100"
            />
            {fieldErrors.test_size && <p className="mt-1 text-xs text-red-400">{fieldErrors.test_size}</p>}
          </div>
        </div>

        <div className="sm:col-span-2">
          <label className="flex items-center gap-2 text-sm text-neutral-300">
            <input
              type="checkbox"
              checked={form.override_slippage}
              onChange={(e) => updateField("override_slippage", e.target.checked)}
              className="h-4 w-4"
            />
            自訂本次滑價（不勾選則使用「設定」頁的費率）
          </label>
          {form.override_slippage && (
            <div className="mt-2 max-w-xs">
              <label htmlFor="bt-slippage" className="block text-sm text-neutral-400">
                滑價（bps）
              </label>
              <input
                id="bt-slippage"
                inputMode="decimal"
                value={form.slippage_bps}
                onChange={(e) => updateField("slippage_bps", e.target.value)}
                className="mt-1 w-full rounded-md border border-neutral-700 bg-neutral-900 px-3 py-2 text-sm text-neutral-100"
              />
              {fieldErrors.slippage_bps && <p className="mt-1 text-xs text-red-400">{fieldErrors.slippage_bps}</p>}
              {settings.isPending && <p className="mt-1 text-xs text-neutral-500">載入目前費率中…</p>}
            </div>
          )}
        </div>

        <div className="sm:col-span-2">
          <button
            type="submit"
            disabled={mutation.isPending}
            className="rounded-md bg-neutral-100 px-4 py-2 text-sm font-medium text-neutral-900 hover:bg-white disabled:cursor-not-allowed disabled:opacity-50"
          >
            {mutation.isPending ? "回測中…" : "執行回測"}
          </button>
        </div>
      </form>

      {Object.values(inputErrors).some(Boolean) && (
        <p role="alert" className="mt-4 rounded-md border border-red-900 bg-red-950/40 px-4 py-3 text-sm text-red-300">
          尚未執行回測：有欄位空白或不是數字，請依欄位下方提示修正。
        </p>
      )}
      {mutation.isError && (Object.keys(serverFieldErrors).length === 0 || unplaced.length > 0) && (
        <p role="alert" className="mt-4 rounded-md border border-red-900 bg-red-950/40 px-4 py-3 text-sm text-red-300">
          回測失敗：
          {unplaced.length > 0
            ? unplaced.join(" ")
            : mutation.error instanceof ApiError
              ? mutation.error.message
              : "未知錯誤"}
        </p>
      )}
    </section>
  );
}

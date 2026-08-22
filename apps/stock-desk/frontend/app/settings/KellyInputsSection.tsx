"use client";

/**
 * Settings-page entry point for the Kelly input behind risk cap 5 (ADR-0006
 * D-8, C5 Kelly Lane K4c-2). A settings-page section rather than a
 * per-symbol page, like `NetWorthSection.tsx`/`AlertRulesSection.tsx`, but
 * unlike those two, `GET /api/kelly-inputs/{symbol}/disclosures`
 * (`app/api/kelly.py`) is keyed on `(symbol, market)`, not global — so this
 * component's own job is the symbol picker that chooses *which* row the
 * three pieces below (`KellyDisclosuresPanel`, `KellyManualInputForm`,
 * `KellyImportDialog`) all read.
 *
 * Reuses `SymbolCombobox` exactly as `ManualAddForm.tsx` does (代號目錄
 * autocomplete, FR-4/6/7's degrade path). Picking a candidate fills `market`
 * from the directory entry, the same as every other form that combobox
 * feeds — a manual symbol with no directory hit still submits on a plain
 * "Load" click, market taken from the adjoining `<select>`.
 */

import { useState } from "react";
import { ApiError } from "../lib/api";
import { ErrorPanel } from "../components/ErrorPanel";
import { SkeletonBlock } from "../components/SkeletonBlock";
import { SymbolCombobox } from "../components/SymbolCombobox";
import { applyDirectorySelection } from "../lib/directorySearch";
import { MARKET_OPTIONS } from "../lib/format";
import { useKellyDisclosures } from "../lib/queries";
import type { DirectoryItem, Market } from "../lib/types";
import { KellyDisclosuresPanel } from "./KellyDisclosuresPanel";
import { KellyImportDialog } from "./KellyImportDialog";
import { KellyManualInputForm } from "./KellyManualInputForm";

interface PickerState {
  symbol: string;
  market: Market;
}

const EMPTY_PICKER: PickerState = { symbol: "", market: "TW" };

export function KellyInputsSection() {
  const [picker, setPicker] = useState<PickerState>(EMPTY_PICKER);
  const [active, setActive] = useState<PickerState | null>(null);

  const query = useKellyDisclosures(
    active?.symbol ?? "",
    active?.market ?? "TW",
    active !== null,
  );

  function handleSelectSymbolCandidate(item: DirectoryItem) {
    setPicker((prev) => applyDirectorySelection(prev, item));
  }

  function handleSubmit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const trimmed = picker.symbol.trim();
    if (trimmed.length === 0) return;
    setActive({ symbol: trimmed, market: picker.market });
  }

  return (
    <section className="rounded-lg border border-neutral-800 p-5">
      {/*
        分歧① required 2 (`work/reviews/2026-08-19-C5-Kelly-文案批審.md`): 「勝率」
        is banned from every frontend source file, not just this section's own
        rendered output — so this standing lead-in names the API's own field
        names (`win_rate`/`payoff_ratio`, English) rather than the Chinese noun,
        the same choice `KellyManualInputForm.tsx`'s field labels make.
      */}
      <h2 className="text-lg font-semibold text-neutral-100">Kelly 輸入</h2>
      <p className="mt-1 text-xs text-neutral-500">
        第 5 條「分數 Kelly 部位上限」使用的 win_rate／payoff_ratio 輸入：手動輸入，或從一次回測帶入。
      </p>

      <form onSubmit={handleSubmit} className="mt-4 flex flex-wrap items-end gap-3">
        <div>
          <label htmlFor="kelly-picker-symbol" className="block text-sm text-neutral-400">
            股票代號
          </label>
          <SymbolCombobox
            id="kelly-picker-symbol"
            required
            value={picker.symbol}
            onChange={(value) => setPicker((prev) => ({ ...prev, symbol: value }))}
            onSelect={handleSelectSymbolCandidate}
            placeholder="例如 2330"
          />
        </div>
        <div>
          <label htmlFor="kelly-picker-market" className="block text-sm text-neutral-400">
            市場
          </label>
          <select
            id="kelly-picker-market"
            value={picker.market}
            onChange={(e) => setPicker((prev) => ({ ...prev, market: e.target.value as Market }))}
            className="mt-1 w-full rounded-md border border-neutral-700 bg-neutral-900 px-3 py-2 text-sm text-neutral-100"
          >
            {MARKET_OPTIONS.map((opt) => (
              <option key={opt.value} value={opt.value}>
                {opt.label}
              </option>
            ))}
          </select>
        </div>
        <button
          type="submit"
          className="rounded-md bg-neutral-100 px-4 py-2 text-sm font-medium text-neutral-900 hover:bg-white"
        >
          查詢
        </button>
      </form>

      {active !== null && (
        <div className="mt-4 space-y-4">
          {query.isPending && <SkeletonBlock className="h-40 w-full" />}
          {query.isError && <ErrorPanel label="無法載入 Kelly 輸入" error={query.error} />}
          {query.isSuccess && (
            <>
              <KellyDisclosuresPanel data={query.data} />
              <KellyManualInputForm
                symbol={active.symbol}
                market={active.market}
                current={query.data.kelly_input?.item ?? null}
              />
              <KellyImportDialog
                symbol={active.symbol}
                market={active.market}
                disclosures={query.data.disclosures}
                refetchDisclosures={query.refetch}
              />
            </>
          )}
        </div>
      )}
    </section>
  );
}

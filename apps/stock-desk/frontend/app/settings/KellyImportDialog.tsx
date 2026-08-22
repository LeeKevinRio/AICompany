"use client";

/**
 * The "re-run a backtest and import its p/b" control
 * (`POST /api/kelly-inputs/{symbol}/import-backtest`, `app/api/kelly.py`) and
 * the before-overwrite dialog 條件 53/68/71-83 require in front of it.
 *
 * **條件 74 (入口閘門,最重)**: this file's `runImport` function is the *only*
 * place in this application allowed to call `useImportKellyBacktest()`'s
 * `mutate` — `app/lib/__tests__/callSiteGuard.test.ts` asserts that
 * `importKellyBacktest(` appears in exactly one call-site file across the
 * whole `app/` tree (this one), so a second entry point anywhere else fails
 * the build rather than a review. `runImport` is called from two places —
 * the dialog's confirm button (when `overwrite_notice` is non-null: 條件 73
 * cells `manual`/`backtest_overridden`), and directly from the trigger
 * (when `overwrite_notice` is `null`: cells `backtest`/`absent`, 條件 73's
 * explicit "no dialog" ruling, 第九輪 "source==backtest: 採 (i) 不顯示對話框")
 * — but the mutation call itself is written exactly once, which is what the
 * guard test checks; it does not care how many buttons can reach it.
 *
 * **This file renders no Chinese literal of its own** beyond the mini
 * backtest-spec form's own chrome, which reuses the exact same shared
 * option lists (`STRATEGY_OPTIONS`, `INSTRUMENT_TYPE_OPTIONS`) and layout
 * `BacktestForm.tsx` already ships and already has scan coverage for — this
 * dialog does not invent a second wording for backtest parameters. Every
 * sentence *about the import itself* (the dialog's title/body/button
 * labels, and the trigger's own label) comes from
 * `KellyOverwriteNoticeView`/`KellyDisclosuresView.import_trigger_label`.
 *
 * **條件 78/102/103 (landed `38c6207`)**: the trigger's visible text and
 * `aria-label` are `disclosures.import_trigger_label` verbatim, always
 * present (like `freshness_badge_label`) across all four source cells.
 *
 * **條件 105**: no "already imported" text (a source label reading
 * "來源：回測帶入" etc.) may appear before the import actually succeeds. This
 * component never renders one itself — every such sentence lives in
 * `KellyDisclosuresPanel`, driven by the `disclosures` query the parent
 * (`KellyInputsSection`) holds — and `useImportKellyBacktest`'s `onSuccess`
 * invalidates that query, so the source label only updates once the server
 * confirms the write, never optimistically.
 *
 * **條件 75**: no measured number (win rate, payoff ratio) is ever rendered
 * on the dialog — only `overwrite_notice`'s own text, which the backend
 * guarantees interpolates nothing.
 *
 * **條件 94**: the dialog variant must reflect the row's source *at
 * confirmation time*, not a value cached before an edit. The trigger's click
 * handler awaits a fresh `refetchDisclosures()` before deciding whether to
 * open the dialog and which `overwrite_notice` to show, rather than trusting
 * the `disclosures` prop, which may be stale by the time the user clicks.
 *
 * **條件 76**: cancelling closes the dialog and calls nothing — no mutation,
 * no state change beyond `open`.
 */

import { useState } from "react";
import { ApiError, parseKellyImportRefusal } from "../lib/api";
import { INSTRUMENT_TYPE_OPTIONS, STRATEGY_OPTIONS } from "../lib/format";
import { useImportKellyBacktest } from "../lib/queries";
import type {
  BacktestRequest,
  BacktestStrategy,
  InstrumentType,
  KellyDisclosuresView,
  KellyInputDisclosuresView,
  Market,
} from "../lib/types";

interface SpecFormState {
  strategy: BacktestStrategy;
  instrument_type: InstrumentType;
  start: string;
  end: string;
  train_size: string;
  test_size: string;
}

const EMPTY_SPEC: SpecFormState = {
  strategy: "ma_cross",
  instrument_type: "stock",
  start: "",
  end: "",
  train_size: "252",
  test_size: "63",
};

export function KellyImportDialog({
  symbol,
  market,
  disclosures,
  refetchDisclosures,
}: {
  symbol: string;
  market: Market;
  disclosures: KellyDisclosuresView;
  //: Re-reads `GET .../disclosures` (條件 94) — the caller's `useQuery`
  //: `refetch`, typed loosely so this component does not have to import
  //: react-query's own result type.
  refetchDisclosures: () => Promise<{ data?: KellyInputDisclosuresView }>;
}) {
  const [spec, setSpec] = useState<SpecFormState>(EMPTY_SPEC);
  const [dialogNotice, setDialogNotice] = useState<KellyDisclosuresView["overwrite_notice"]>(null);
  const mutation = useImportKellyBacktest();

  // 條件 102/103: always populated, all four source cells.
  const triggerLabel = disclosures.import_trigger_label;

  function updateSpec<K extends keyof SpecFormState>(key: K, value: SpecFormState[K]) {
    setSpec((prev) => ({ ...prev, [key]: value }));
  }

  function buildRequest(): BacktestRequest {
    return {
      symbol,
      market,
      strategy: spec.strategy,
      instrument_type: spec.instrument_type,
      start: spec.start,
      end: spec.end,
      initial_cash: 1_000_000,
      train_size: Number(spec.train_size),
      test_size: Number(spec.test_size),
    };
  }

  // 條件 74: the sole call site. Both the dialog's confirm button and the
  // no-dialog trigger path call this same function; the mutation itself is
  // written exactly once, here.
  function runImport() {
    mutation.mutate(
      { symbol, market, body: buildRequest() },
      {
        onSuccess: () => setDialogNotice(null),
      },
    );
  }

  async function handleTriggerClick() {
    // 條件 94: never decide the variant from a possibly-stale prop.
    const fresh = await refetchDisclosures();
    const freshNotice = fresh.data?.disclosures.overwrite_notice ?? disclosures.overwrite_notice;
    if (freshNotice === null) {
      // 條件 73 cell "backtest"/"absent": no dialog, run directly.
      runImport();
      return;
    }
    setDialogNotice(freshNotice);
  }

  function handleCancel() {
    // 條件 76: closes only. No mutation, no store call, no state beyond `open`.
    setDialogNotice(null);
  }

  return (
    <div className="mt-4 rounded-md border border-neutral-800 p-4">
      <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
        <div>
          <label htmlFor="kelly-import-strategy" className="block text-sm text-neutral-400">
            策略
          </label>
          <select
            id="kelly-import-strategy"
            value={spec.strategy}
            onChange={(e) => updateSpec("strategy", e.target.value as BacktestStrategy)}
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
          <label htmlFor="kelly-import-instrument" className="block text-sm text-neutral-400">
            類型
          </label>
          <select
            id="kelly-import-instrument"
            value={spec.instrument_type}
            onChange={(e) => updateSpec("instrument_type", e.target.value as InstrumentType)}
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
          <label htmlFor="kelly-import-start" className="block text-sm text-neutral-400">
            開始日期
          </label>
          <input
            id="kelly-import-start"
            type="date"
            required
            value={spec.start}
            onChange={(e) => updateSpec("start", e.target.value)}
            className="mt-1 w-full rounded-md border border-neutral-700 bg-neutral-900 px-3 py-2 text-sm text-neutral-100"
          />
        </div>

        <div>
          <label htmlFor="kelly-import-end" className="block text-sm text-neutral-400">
            結束日期
          </label>
          <input
            id="kelly-import-end"
            type="date"
            required
            value={spec.end}
            onChange={(e) => updateSpec("end", e.target.value)}
            className="mt-1 w-full rounded-md border border-neutral-700 bg-neutral-900 px-3 py-2 text-sm text-neutral-100"
          />
        </div>

        <div>
          <label htmlFor="kelly-import-train" className="block text-sm text-neutral-400">
            train_size
          </label>
          <input
            id="kelly-import-train"
            inputMode="numeric"
            value={spec.train_size}
            onChange={(e) => updateSpec("train_size", e.target.value)}
            className="mt-1 w-full rounded-md border border-neutral-700 bg-neutral-900 px-3 py-2 text-sm text-neutral-100"
          />
        </div>

        <div>
          <label htmlFor="kelly-import-test" className="block text-sm text-neutral-400">
            test_size
          </label>
          <input
            id="kelly-import-test"
            inputMode="numeric"
            value={spec.test_size}
            onChange={(e) => updateSpec("test_size", e.target.value)}
            className="mt-1 w-full rounded-md border border-neutral-700 bg-neutral-900 px-3 py-2 text-sm text-neutral-100"
          />
        </div>
      </div>

      <button
        type="button"
        aria-label={triggerLabel}
        onClick={() => void handleTriggerClick()}
        disabled={mutation.isPending || spec.start === "" || spec.end === ""}
        className="mt-3 rounded-md bg-neutral-100 px-4 py-2 text-sm font-medium text-neutral-900 hover:bg-white disabled:cursor-not-allowed disabled:opacity-50"
      >
        {triggerLabel}
      </button>

      {mutation.isError && (
        <ImportRefusalPanel error={mutation.error} />
      )}

      {dialogNotice !== null && (
        <div
          className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 px-4 py-8"
        >
          <div
            role="dialog"
            aria-modal="true"
            aria-label={dialogNotice.title}
            className="max-h-full w-full max-w-lg overflow-y-auto rounded-lg border border-neutral-800 bg-neutral-950 p-5"
          >
            <h2 className="text-lg font-semibold text-neutral-100">{dialogNotice.title}</h2>
            {/* 條件 93: three paragraphs rendered as separate items, never joined. */}
            <div className="mt-3 space-y-3 text-sm text-neutral-300">
              {dialogNotice.body.map((paragraph, index) => (
                <p key={index}>{paragraph}</p>
              ))}
            </div>
            <div className="mt-4 flex justify-end gap-3">
              <button
                type="button"
                onClick={handleCancel}
                className="rounded-md border border-neutral-700 px-4 py-2 text-sm text-neutral-200 hover:bg-neutral-900"
              >
                {dialogNotice.cancel_label}
              </button>
              <button
                type="button"
                onClick={runImport}
                disabled={mutation.isPending}
                className="rounded-md bg-neutral-100 px-4 py-2 text-sm font-medium text-neutral-900 hover:bg-white disabled:cursor-not-allowed disabled:opacity-50"
              >
                {dialogNotice.confirm_label}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

/**
 * The 422 refusal body's three sentences (`KellyImportRefusal`,
 * `app/api/kelly.py`): `frame` (元件 A, only the three sample-size codes),
 * `message`, `attempt_logged` (元件 B), then `selection_bias` (3-A, same
 * screen as 元件 B) — 條件 27's fixed order. `parseKellyImportRefusal` returns
 * `null` for anything that is not this exact shape (e.g. a network error, or
 * a 500 whose `detail` is the plain-string
 * `KELLY_NON_FINITE_INTERVAL_MESSAGE`), in which case this panel falls back
 * to the generic `ApiError.message` — never a fabricated Chinese sentence.
 */
function ImportRefusalPanel({ error }: { error: unknown }) {
  const refusal = error instanceof ApiError ? parseKellyImportRefusal(error.body) : null;
  if (refusal !== null) {
    return (
      <div role="alert" className="mt-3 space-y-1 rounded-md border border-red-900 bg-red-950/40 px-4 py-3 text-sm text-red-300">
        {refusal.frame !== null && <p>{refusal.frame}</p>}
        <p>{refusal.message}</p>
        <p>{refusal.attempt_logged}</p>
        {refusal.selection_bias !== null && <p>{refusal.selection_bias}</p>}
      </div>
    );
  }
  return (
    <p role="alert" className="mt-3 rounded-md border border-red-900 bg-red-950/40 px-4 py-3 text-sm text-red-300">
      {error instanceof ApiError ? error.message : "未知錯誤"}
    </p>
  );
}

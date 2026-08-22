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
 * **條件 94/74 (B3, qa 補審 2026-08-22, `work/reviews/2026-08-22-C5-K4c2-qa
 * 補審.md`)**: the dialog variant must reflect the row's source *at
 * confirmation time*, not a value cached before an edit — and, the first
 * draft's actual bug, **never a value cached from a failed refresh either**.
 * `resolveImportTriggerDecision` calls `getKellyDisclosures` directly (not
 * the caller's `useQuery` `refetch`, whose `QueryObserverResult` can still
 * carry the *previous* successful `data` after a failed refetch) inside a
 * `try`/`catch`; a network failure returns `{ kind: "abort" }` rather than
 * falling back to the `disclosures` prop. Falling back to that prop was
 * exactly the bug: a stale `overwrite_notice: null` (e.g. the row was
 * `backtest` a moment ago and has since been overridden) would have run the
 * import with **no dialog at all**, defeating 條件 74 in the one case it
 * exists to prevent. `app/lib/__tests__/kellyImportDialog.test.ts` pins the
 * failure path with a fake fetcher that rejects.
 *
 * **條件 76**: cancelling sets `dialogNotice` back to `null` and does nothing
 * else — no mutation, no store call. `handleCancel` itself is not a separate
 * pure function (there is nothing to compute; it is a one-line state setter),
 * so unlike `decideImportTrigger`/`resolveImportTriggerDecision` this
 * particular behaviour has no unit test of its own — the DOM-level guarantee
 * ("cancelling never calls the import endpoint") is qa-e2e's to verify on a
 * real page, consistent with this whole surface's no-jsdom limitation (see
 * `kellyImportDialog.test.ts`'s own doc comment).
 *
 * **B6 (qa 補審)**: `runImport`'s `onError` closes the dialog
 * (`setDialogNotice(null)`). Leaving the dialog open on a refusal — the first
 * draft's bug — kept `ImportRefusalPanel` mounted but visually behind the
 * dialog's own `bg-black/60` full-screen overlay: 元件 A/message/元件 B/(b)
 * were technically in the DOM and practically invisible, which is not what
 * 條件 22/3-A's "同屏" requirement means.
 */

import { useState } from "react";
import { ApiError, getKellyDisclosures, parseKellyImportRefusal } from "../lib/api";
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

export interface SpecFormState {
  strategy: BacktestStrategy;
  instrument_type: InstrumentType;
  start: string;
  end: string;
  //: B4 (qa 補審): editable, 逐字同構 `BacktestForm.tsx`'s own 起始資金 field
  //: and default — a `initial_cash` this dialog silently hard-coded is a
  //: parameter 列管 L11 requires be on screen and user-selected, not implicit.
  initial_cash: string;
  train_size: string;
  test_size: string;
}

const EMPTY_SPEC: SpecFormState = {
  strategy: "ma_cross",
  instrument_type: "stock",
  start: "",
  end: "",
  initial_cash: "1000000",
  train_size: "252",
  test_size: "63",
};

/**
 * Pulled out as a pure function so 條件 73's four-cell branching (no dialog
 * for `absent`/`backtest`, a dialog carrying the row's own variant for
 * `manual`/`backtest_overridden`) is unit-testable without a DOM — this repo
 * has no `@testing-library/react`/jsdom yet (`vitest.config.ts`'s own doc
 * comment; same trade-off `EditAlertRuleModal.tsx`'s `decideAlertRuleSubmit`
 * makes). `app/lib/__tests__/kellyImportDialog.test.ts` covers all four
 * cells directly against this function.
 */
export type ImportTriggerDecision =
  | { kind: "run" }
  | { kind: "open-dialog"; notice: NonNullable<KellyDisclosuresView["overwrite_notice"]> };

export function decideImportTrigger(
  overwriteNotice: KellyDisclosuresView["overwrite_notice"],
): ImportTriggerDecision {
  if (overwriteNotice === null) {
    // 條件 73 cells "absent"/"backtest": explicit no-dialog, run directly.
    return { kind: "run" };
  }
  // 條件 73 cells "manual"/"backtest_overridden": the row's own variant.
  return { kind: "open-dialog", notice: overwriteNotice };
}

/**
 * B3: fetches a fresh `disclosures` read and decides the trigger from it, or
 * aborts — never a stale fallback. `fetchDisclosures` is injected (rather
 * than this function calling `getKellyDisclosures` itself) purely so this
 * suite can pass a fake that rejects without a network layer to mock.
 */
export async function resolveImportTriggerDecision(
  fetchDisclosures: () => Promise<KellyInputDisclosuresView>,
): Promise<ImportTriggerDecision | { kind: "abort" }> {
  let fresh: KellyInputDisclosuresView;
  try {
    fresh = await fetchDisclosures();
  } catch {
    // 條件 94/74: a failed refresh must never fall back to a possibly-stale
    // variant — abort instead of guessing which dialog (or no dialog) to show.
    return { kind: "abort" };
  }
  return decideImportTrigger(fresh.disclosures.overwrite_notice);
}

/**
 * The `BacktestRequest` this dialog's confirm/direct-run path submits — pulled
 * out so the field mapping (and the 列管 L11 fact that every one of these
 * fields is a value the mini spec-form actually shows, never an invented
 * default hidden from the screen) has a unit test independent of rendering.
 */
export function buildKellyImportRequest(
  symbol: string,
  market: Market,
  spec: SpecFormState,
): BacktestRequest {
  return {
    symbol,
    market,
    strategy: spec.strategy,
    instrument_type: spec.instrument_type,
    start: spec.start,
    end: spec.end,
    initial_cash: Number(spec.initial_cash),
    train_size: Number(spec.train_size),
    test_size: Number(spec.test_size),
  };
}

export function KellyImportDialog({
  symbol,
  market,
  disclosures,
}: {
  symbol: string;
  market: Market;
  disclosures: KellyDisclosuresView;
}) {
  const [spec, setSpec] = useState<SpecFormState>(EMPTY_SPEC);
  const [dialogNotice, setDialogNotice] = useState<KellyDisclosuresView["overwrite_notice"]>(null);
  const mutation = useImportKellyBacktest();

  // 條件 102/103: always populated, all four source cells.
  const triggerLabel = disclosures.import_trigger_label;

  function updateSpec<K extends keyof SpecFormState>(key: K, value: SpecFormState[K]) {
    setSpec((prev) => ({ ...prev, [key]: value }));
  }

  // 條件 74: the sole call site. Both the dialog's confirm button and the
  // no-dialog trigger path (`decideImportTrigger`'s `"run"` branch) call this
  // same function; the mutation itself is written exactly once, here.
  function runImport() {
    mutation.mutate(
      { symbol, market, body: buildKellyImportRequest(symbol, market, spec) },
      {
        onSuccess: () => setDialogNotice(null),
        // B6: close the dialog on a refusal too, so `ImportRefusalPanel`
        // (rendered below, outside the dialog's own overlay) is not left
        // visually hidden behind `bg-black/60` while `dialogNotice` stands.
        onError: () => setDialogNotice(null),
      },
    );
  }

  async function handleTriggerClick() {
    const decision = await resolveImportTriggerDecision(() => getKellyDisclosures(symbol, market));
    if (decision.kind === "abort") return;
    if (decision.kind === "run") {
      runImport();
      return;
    }
    setDialogNotice(decision.notice);
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
          <label htmlFor="kelly-import-cash" className="block text-sm text-neutral-400">
            initial_cash
          </label>
          <input
            id="kelly-import-cash"
            inputMode="decimal"
            value={spec.initial_cash}
            onChange={(e) => updateSpec("initial_cash", e.target.value)}
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

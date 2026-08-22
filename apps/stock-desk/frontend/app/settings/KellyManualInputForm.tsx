"use client";

/**
 * The hand-entered `win_rate` / `payoff_ratio` pair behind risk cap 5
 * (`PUT`/`DELETE /api/kelly-inputs/{symbol}`, `app/api/kelly.py`). Sibling in
 * role to `NetWorthSection.tsx` — a settings-page form for one self-reported
 * number the risk layer consumes — but unlike that section, every sentence
 * *about* what this pair means is Kelly-disclosure copy the whole 2026-08-19
 * review governs (`work/reviews/2026-08-19-C5-Kelly-文案批審.md`) and is
 * rendered by `KellyDisclosuresPanel`, never by this form.
 *
 * This form itself renders only two kinds of text: the field labels (the raw
 * API field names `win_rate` / `payoff_ratio`, not the two-character Chinese
 * noun 分歧① required 2 bans from frontend source entirely — 「白名單=僅後端
 * 常數」 — and no backend response gives this plain *input form* a label for
 * a number that has not been measured by anything;
 * `KellyOriginalValuesView.win_rate_label` and
 * `KELLY_PAYOFF_RATIO_LABEL`/`original_values.payoff_ratio_label` exist, but
 * only for an *overridden* row and only to describe the *kept* imported
 * pair, not the input the user is about to type here) and ordinary form
 * chrome (submit/delete, in the same register as every other settings-page
 * form on this page — not disclosure content, so not subject to that rule).
 *
 * 條件 57 (協調人三確認 2, `落地條件 31`): `allow_inf_nan=False` refuses a
 * `nan`/`inf` submission before the backend's own Chinese range message can
 * fire, so the 422 body for that one branch is pydantic's unreviewed English
 * `"Input should be a finite number"`. `isApprovedKellyFieldMessage`
 * (`app/lib/kellyFieldError.ts`) is the gate: a field message that fails it
 * is never rendered here, and the generic top-level rejection banner (already
 * pre-existing, already-shipped copy — `ApiError.message`'s own
 * `請求失敗（HTTP …）` fallback) stands in for it instead.
 *
 * **條件 109 (第十四輪, 出貨閘門): the delete control does not ship yet.**
 * `window.confirm`'s pre-existing "此動作無法復原。" phrasing (逐字同構
 * `PositionsTable.tsx`) does **not** transfer here: a Kelly row's delete does
 * not cascade to the import-attempt log (`store.py:270`, `K_observed`/`K_
 * distinct_specs` survive), and the user has no read surface for that log at
 * all (列管 L7) — "無法復原" is therefore a one-sided claim that everything
 * about this row is gone, which is false in the direction that matters. 條件
 * 110 sends the real disclosure sentence to creative (subject named, "無法
 * 復原" scoped to what actually cannot be recovered, the kept counts stated
 * rather than silently dropped, no induced framing, a button label that does
 * not embed a value judgement). Until that sentence lands: **no delete
 * button, no `window.confirm`, no call site** — `DELETE
 * /api/kelly-inputs/{symbol}` (`deleteKellyInput`/`useDeleteKellyInput`,
 * `app/lib/api.ts`/`queries.ts`) stays wired and untouched for when it does.
 * `app/lib/__tests__/kellyManualInputForm.test.ts` carries the placeholder.
 */

import { useState } from "react";
import { ApiError } from "../lib/api";
import { isApprovedKellyFieldMessage } from "../lib/kellyFieldError";
import { useUpdateKellyInput } from "../lib/queries";
import type { KellyInputRow, Market } from "../lib/types";

function FieldError({ message }: { message: string | undefined }) {
  if (!message) return null;
  return <p className="mt-1 text-xs text-red-400">{message}</p>;
}

export function KellyManualInputForm({
  symbol,
  market,
  current,
}: {
  symbol: string;
  market: Market;
  //: `null` when nothing has ever been entered for this row — the form still
  //: renders (a first write is exactly how a `manual` row is created), just
  //: with both fields blank.
  current: KellyInputRow | null;
}) {
  const [winRate, setWinRate] = useState(current !== null ? String(current.win_rate) : "");
  const [payoffRatio, setPayoffRatio] = useState(
    current !== null ? String(current.payoff_ratio) : "",
  );
  const updateMutation = useUpdateKellyInput();

  const rawFieldErrors = updateMutation.error instanceof ApiError ? updateMutation.error.fieldErrors : {};
  // 條件 57: a field error that is not an approved Chinese sentence is
  // dropped here, not forwarded to the field-level `<FieldError>` below.
  const winRateError = isApprovedKellyFieldMessage(rawFieldErrors.win_rate)
    ? rawFieldErrors.win_rate
    : undefined;
  const payoffRatioError = isApprovedKellyFieldMessage(rawFieldErrors.payoff_ratio)
    ? rawFieldErrors.payoff_ratio
    : undefined;
  const hasApprovedFieldError = winRateError !== undefined || payoffRatioError !== undefined;
  // The generic fallback: rendered whenever the request failed but no
  // approved field-level sentence came back for it (condition 57's fallback
  // branch, and every non-field failure e.g. a network error).
  const genericRejection =
    updateMutation.isError && !hasApprovedFieldError
      ? updateMutation.error instanceof ApiError
        ? updateMutation.error.message
        : undefined
      : undefined;

  function handleSubmit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    // Sent exactly as typed, like `NetWorthSection` — a silently corrected
    // number is one the user would later believe they had entered.
    updateMutation.mutate({
      symbol,
      market,
      input: { win_rate: Number(winRate), payoff_ratio: Number(payoffRatio) },
    });
  }

  return (
    <div className="rounded-md border border-neutral-800 p-4">
      <form onSubmit={handleSubmit} className="grid grid-cols-1 gap-3 sm:grid-cols-2">
        <div>
          <label htmlFor="kelly-win-rate" className="block text-sm text-neutral-400">
            win_rate
          </label>
          <input
            id="kelly-win-rate"
            inputMode="decimal"
            required
            value={winRate}
            onChange={(e) => setWinRate(e.target.value)}
            className="mt-1 w-full rounded-md border border-neutral-700 bg-neutral-900 px-3 py-2 text-sm text-neutral-100"
          />
          <FieldError message={winRateError} />
        </div>

        <div>
          <label htmlFor="kelly-payoff-ratio" className="block text-sm text-neutral-400">
            payoff_ratio
          </label>
          <input
            id="kelly-payoff-ratio"
            inputMode="decimal"
            required
            value={payoffRatio}
            onChange={(e) => setPayoffRatio(e.target.value)}
            className="mt-1 w-full rounded-md border border-neutral-700 bg-neutral-900 px-3 py-2 text-sm text-neutral-100"
          />
          <FieldError message={payoffRatioError} />
        </div>

        <div className="flex items-center gap-3 sm:col-span-2">
          <button
            type="submit"
            disabled={updateMutation.isPending}
            className="rounded-md bg-neutral-100 px-4 py-2 text-sm font-medium text-neutral-900 hover:bg-white disabled:cursor-not-allowed disabled:opacity-50"
          >
            {updateMutation.isPending ? "儲存中…" : "儲存"}
          </button>
          {/*
            條件 109 (第十四輪): the delete control is withheld until 條件 110's
            disclosure sentence is drafted and approved — see the file's own
            doc comment. `current` (whether a row exists to delete) is
            deliberately left unused for that decision here; it stays a prop
            other future logic in this file can read.
          */}
        </div>
      </form>

      {genericRejection && (
        <p role="alert" className="mt-3 rounded-md border border-red-900 bg-red-950/40 px-4 py-3 text-sm text-red-300">
          {genericRejection}
        </p>
      )}
    </div>
  );
}

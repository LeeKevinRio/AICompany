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
 */

import { useState } from "react";
import { ApiError } from "../lib/api";
import { isApprovedKellyFieldMessage } from "../lib/kellyFieldError";
import { useDeleteKellyInput, useUpdateKellyInput } from "../lib/queries";
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
  const [winRate, setWinRate] = useState(current?.win_rate !== undefined && current !== null ? String(current.win_rate) : "");
  const [payoffRatio, setPayoffRatio] = useState(
    current !== null ? String(current.payoff_ratio) : "",
  );
  const updateMutation = useUpdateKellyInput();
  const deleteMutation = useDeleteKellyInput();

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

  function handleDelete() {
    const confirmed = window.confirm(
      `確定刪除 ${symbol}（${market}）的 Kelly 輸入？此動作無法復原。`,
    );
    if (!confirmed) return;
    deleteMutation.mutate(
      { symbol, market },
      {
        onSuccess: () => {
          setWinRate("");
          setPayoffRatio("");
        },
      },
    );
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
          {current !== null && (
            <button
              type="button"
              onClick={handleDelete}
              disabled={deleteMutation.isPending}
              className="rounded-md border border-red-900 px-4 py-2 text-sm font-medium text-red-300 hover:bg-red-950/40 disabled:cursor-not-allowed disabled:opacity-50"
            >
              {deleteMutation.isPending ? "刪除中…" : "刪除"}
            </button>
          )}
        </div>
      </form>

      {genericRejection && (
        <p role="alert" className="mt-3 rounded-md border border-red-900 bg-red-950/40 px-4 py-3 text-sm text-red-300">
          {genericRejection}
        </p>
      )}
      {deleteMutation.isError && (
        <p role="alert" className="mt-3 rounded-md border border-red-900 bg-red-950/40 px-4 py-3 text-sm text-red-300">
          {deleteMutation.error instanceof ApiError ? deleteMutation.error.message : "未知錯誤"}
        </p>
      )}
    </div>
  );
}

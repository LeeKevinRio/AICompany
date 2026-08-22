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
 * **B1 (qa 補審 2026-08-22, `work/reviews/2026-08-22-C5-K4c2-qa補審.md`)**:
 * this component is rendered by `KellyDisclosuresPanel`, inside that file's
 * own "effective" branch — never by `KellyInputsSection` as a sibling. That
 * placement is load-bearing, not cosmetic: this form pre-fills and edits the
 * *effective* pair, which is exactly the "生效值欄位" 條件 46 約束 3 requires
 * to disappear from the DOM whenever the original-values view is open, and
 * only being inside the same ternary that view toggles can guarantee that
 * (`shouldRenderManualInputForm`, `KellyDisclosuresPanel.tsx`).
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
 * **條件 109/112 (第十四/十五輪): the delete control lives in
 * `KellyDeleteDialog.tsx`, a sibling this form does not import.** 條件 109
 * (第十四輪) withheld a delete control entirely until 條件 110's disclosure
 * sentence existed — `window.confirm`'s old "this cannot be undone" style
 * phrasing was a one-sided claim (the import-attempt log outlives a Kelly
 * row's delete, `store.py:270`, and the user had no read surface for it,
 * 列管 L7). 第十五輪
 * CONFIRMED the real sentence and **required `role="dialog"`, banning
 * `window.confirm` outright** (a confirm dialog's buttons are the browser's,
 * not this app's, so the approved button copy could never render through
 * it) — which is why the delete control is not folded back into *this* file:
 * `KellyDisclosuresPanel.tsx` renders `KellyDeleteDialog` beside this form,
 * in the same "effective" branch (both are 「生效值欄位」-adjacent, subject
 * to the same 條件 46 約束 3 mutual exclusion), not inside it.
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

/**
 * qa 補審 (順手, non-blocking suggestion): a light client-side pre-check —
 * `type="number"` is deliberately *not* used on either input, matching this
 * app's existing convention (`NetWorthSection.tsx`, `BacktestForm.tsx`: the
 * browser must not be the thing that judges a value, so it cannot silently
 * clamp/round it) — but sending `Number("abc")` (`NaN`) is not "the browser
 * judging a value", it is a request this backend will refuse outright, and
 * doing so still counts as a submission. This predicate exists only to skip
 * that pointless round trip; it changes no value and clamps nothing.
 */
export function isSubmittableManualInput(winRate: string, payoffRatio: string): boolean {
  return Number.isFinite(Number(winRate)) && Number.isFinite(Number(payoffRatio));
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
    // qa 補審 順手: skip a request that cannot possibly succeed — not a
    // clamp, not a correction, just declining to spend a round trip on
    // `Number("abc")`. Whatever *is* sent still goes exactly as typed, like
    // `NetWorthSection` — a silently corrected number is one the user would
    // later believe they had entered.
    if (!isSubmittableManualInput(winRate, payoffRatio)) return;
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

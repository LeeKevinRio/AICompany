"use client";

/**
 * The delete-confirmation control for one Kelly input row
 * (`DELETE /api/kelly-inputs/{symbol}`, `app/api/kelly.py`) — condition 109's
 * (第十四輪) shipping gate lifted in 第十五輪 once the disclosure sentence
 * (條件 110) was drafted and CONFIRMED, on the explicit condition (條件 112)
 * that it lands as a `role="dialog"` component, never `window.confirm` (a
 * confirm dialog's button labels are supplied by the browser, not this app,
 * so the approved button copy — "確認刪除，移除目前資料" — could never be
 * rendered through it at all).
 *
 * **Mirrors `KellyImportDialog.tsx`'s own architecture deliberately** ("比照
 * 帶入對話框慣例", 第十五輪 item 1): a trigger button, a fresh
 * `getKellyDisclosures` read before the dialog opens (B3/條件 94's own
 * pattern — never a stale cached variant, and here specifically never a
 * stale *source* — an `overridden` row's delete notice names the kept
 * original pair explicitly (條件 111), so confirming against a source that
 * has since changed would show the wrong variant), an abort-on-fetch-failure
 * path, and `onError` closing the dialog so a refusal is never left visually
 * hidden behind the overlay (B6's own fix, reused here even though a delete
 * refusal has no `KellyImportRefusal`-shaped body of its own — the generic
 * `ApiError.message` still deserves to be visible, not covered).
 *
 * **This file renders no Chinese literal of its own for the dialog's
 * content** — title/body/button labels all come from `KellyDeleteNoticeView`
 * (verbatim, condition 115: front end composes nothing). The trigger
 * button's own label, "刪除", is chrome (第十四輪 chrome 判準 "准"), the same
 * treatment "查詢"/"儲存" get elsewhere on this surface.
 *
 * **Field-name alignment**: `disclosures.delete_notice`
 * (`KellyDeleteNoticeView`) was typed here before the backend half existed and
 * is now aligned with it — the landed model (`dada382`, `app/api/kelly.py`)
 * carries the same field name and the same four fields, checked field by
 * field against `app/lib/types.ts`.
 */

import { useState } from "react";
import { ApiError, getKellyDisclosures } from "../lib/api";
import { useDeleteKellyInput } from "../lib/queries";
import type { KellyDeleteNoticeView, Market } from "../lib/types";

export type DeleteTriggerDecision = { kind: "open-dialog"; notice: KellyDeleteNoticeView } | { kind: "abort" };

/**
 * B3-style: fetches a fresh `disclosures` read and opens the dialog with
 * whatever `delete_notice` variant that read carries, or aborts — never a
 * stale fallback and never a `null` opening an empty dialog. Injected
 * `fetchDisclosures` so this is unit-testable without a network layer to
 * mock (`app/lib/__tests__/kellyDeleteDialog.test.ts`).
 */
export async function resolveDeleteTriggerDecision(
  fetchDisclosures: () => Promise<{ disclosures: { delete_notice: KellyDeleteNoticeView | null } }>,
): Promise<DeleteTriggerDecision> {
  let fresh: { disclosures: { delete_notice: KellyDeleteNoticeView | null } };
  try {
    fresh = await fetchDisclosures();
  } catch {
    return { kind: "abort" };
  }
  if (fresh.disclosures.delete_notice === null) {
    // The row disappeared between render and click (e.g. deleted from
    // another tab) — nothing to confirm.
    return { kind: "abort" };
  }
  return { kind: "open-dialog", notice: fresh.disclosures.delete_notice };
}

export function KellyDeleteDialog({
  symbol,
  market,
  hasRow,
}: {
  symbol: string;
  market: Market;
  //: Mirrors the old `current !== null` gate this app used to render a
  //: delete button on directly — no row, no trigger at all.
  hasRow: boolean;
}) {
  const [dialogNotice, setDialogNotice] = useState<KellyDeleteNoticeView | null>(null);
  const mutation = useDeleteKellyInput();

  if (!hasRow) return null;

  async function handleTriggerClick() {
    const decision = await resolveDeleteTriggerDecision(() => getKellyDisclosures(symbol, market));
    if (decision.kind === "abort") return;
    setDialogNotice(decision.notice);
  }

  function handleCancel() {
    // 條件 114: closes only. No mutation, no store call.
    setDialogNotice(null);
  }

  function runDelete() {
    mutation.mutate(
      { symbol, market },
      {
        onSuccess: () => setDialogNotice(null),
        // B6-style: never leave a refusal hidden behind the overlay.
        onError: () => setDialogNotice(null),
      },
    );
  }

  return (
    <div className="mt-3">
      <button
        type="button"
        onClick={() => void handleTriggerClick()}
        disabled={mutation.isPending}
        className="rounded-md border border-red-900 px-4 py-2 text-sm font-medium text-red-300 hover:bg-red-950/40 disabled:cursor-not-allowed disabled:opacity-50"
      >
        刪除
      </button>

      {mutation.isError && (
        <p role="alert" className="mt-3 rounded-md border border-red-900 bg-red-950/40 px-4 py-3 text-sm text-red-300">
          {mutation.error instanceof ApiError ? mutation.error.message : "未知錯誤"}
        </p>
      )}

      {dialogNotice !== null && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 px-4 py-8">
          <div
            role="dialog"
            aria-modal="true"
            aria-label={dialogNotice.title}
            className="max-h-full w-full max-w-lg overflow-y-auto rounded-lg border border-neutral-800 bg-neutral-950 p-5"
          >
            <h2 className="text-lg font-semibold text-neutral-100">{dialogNotice.title}</h2>
            {/* 條件 111 (比照 93): every paragraph rendered as a separate item. */}
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
                onClick={runDelete}
                disabled={mutation.isPending}
                className="rounded-md bg-red-800 px-4 py-2 text-sm font-medium text-neutral-100 hover:bg-red-700 disabled:cursor-not-allowed disabled:opacity-50"
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

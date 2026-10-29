"use client";

import { useEffect, useRef, useState, useSyncExternalStore } from "react";
import { createPortal } from "react-dom";
import { ErrorPanel } from "../components/ErrorPanel";
import { FOCUSABLE_SELECTOR, trapTabTarget } from "../lib/focusTrap";
import { useEmergencyExit } from "../lib/queries";
import {
  allExitChecksConfirmed,
  exitConfirmChecks,
  initialExitChecks,
  shouldRenderAttribution,
  toggleExitCheck,
} from "../lib/playbookView";
import type { PlaybookExitConfirm } from "../lib/types";

type ExitStep = "idle" | "confirm" | "final";

function subscribeNoop(): () => void {
  return () => {};
}

/**
 * False during SSR and the hydration pass, true once mounted on the client, so
 * the portal below only touches `document.body` after hydration (no mismatch,
 * no `document` access on the server).
 */
function useIsClientMounted(): boolean {
  return useSyncExternalStore(
    subscribeNoop,
    () => true,
    () => false,
  );
}

/**
 * EMERGENCY_EXIT control (視覺規範 §4). Button styling is deliberately
 * ordinary — 中性色階, no rose/red, no icon, no animation (§4.2: "成本來自流程
 * 摩擦，不是來自視覺恐嚇") — and the cost lives entirely in the 3-step flow
 * below (§4.3): Step 1 is this button; Step 2 is the fact-checklist modal
 * (`confirm`), which requires every checkbox ticked before advancing; Step 3
 * (`final`) is the second confirmation that actually calls
 * `POST /emergency-exit`. No checkbox is pre-ticked and there is no countdown
 * anywhere in this flow (EX-2 / 出口零摩擦, wording.py's own doc comment on
 * `EXIT_CONFIRM_CHECKS`).
 *
 * Every sentence in the modal is backend-sourced or a risk-compliance
 * pre-approved literal: the Step 2 checks are `today.exit_confirm.checks`,
 * rendered exactly as `wording.exit_confirm_checks` produced them — including
 * the freeze length and 預計恢復日, which are the day's rule parameter and a
 * trading-calendar count, never mirrored here (see `exitConfirmChecks` for the
 * degraded branch when the block is absent). The four button labels are the
 * pre-approved literals the hand-off task named verbatim: 全部出清／我已閱讀，
 * 繼續／確認送出全部出清／取消.
 */
export function EmergencyExitControl({
  exitConfirm,
}: {
  exitConfirm: PlaybookExitConfirm | null;
}) {
  const checkTexts = exitConfirmChecks(exitConfirm);
  const [step, setStep] = useState<ExitStep>("idle");
  const [checks, setChecks] = useState<boolean[]>(() => initialExitChecks(checkTexts.length));
  const mutation = useEmergencyExit();
  const isClientMounted = useIsClientMounted();
  const triggerRef = useRef<HTMLButtonElement>(null);
  const dialogRef = useRef<HTMLDivElement>(null);
  const headingRef = useRef<HTMLHeadingElement>(null);
  const previousStepRef = useRef<ExitStep>("idle");
  const cancelRef = useRef<() => void>(() => {});
  // Synchronous submit lock. `mutation.isPending` only flips after a render, so
  // two activations inside the same tick would both see `false` and fire two
  // irreversible POSTs; a ref is updated immediately.
  const submittingRef = useRef(false);

  // The checklist length only changes when a refetch swaps the degraded
  // fallback for the real block (3 checks <-> 4). Re-seeding keeps a tick
  // bound to the sentence it was given for: a box ticked against a sentence
  // that is no longer on screen may not carry over into the submission.
  if (checks.length !== checkTexts.length) {
    setChecks(initialExitChecks(checkTexts.length));
  }

  function openConfirm() {
    mutation.reset();
    setChecks(initialExitChecks(checkTexts.length));
    setStep("confirm");
  }

  function cancel() {
    // Defence in depth for the aria-disabled cancel button (still focusable and
    // clickable while the submission is in flight): never close mid-submit.
    if (submittingRef.current || mutation.isPending) return;
    setStep("idle");
    setChecks(initialExitChecks(checkTexts.length));
  }

  function submit(event: React.MouseEvent<HTMLButtonElement>) {
    // N-163: the button stays `aria-disabled` (not `disabled`) while pending, so
    // it keeps focus; a second activation (Enter / Space / click) must not
    // fire a second irreversible POST. The ref covers the window before
    // `isPending` is rendered; `isPending` covers a lock that was never set.
    if (submittingRef.current || mutation.isPending) return;
    submittingRef.current = true;
    // Safari / Firefox-on-macOS do not focus a button on click; make it explicit
    // so focus is on a dialog control before the pending state begins.
    event.currentTarget.focus();
    mutation.mutate(undefined, {
      onSuccess: () => setStep("idle"),
      // Release the lock on success and failure alike so a failed submit can
      // be retried.
      onSettled: () => {
        submittingRef.current = false;
      },
    });
  }

  // Keep the latest `cancel` reachable from the document-level Esc listener
  // without re-subscribing on every render.
  useEffect(() => {
    cancelRef.current = cancel;
  });

  // Focus management (the dialog is portalled to the end of <body>, so the
  // browser's natural order no longer puts it right after the trigger). Every
  // step moves focus to the step's heading — not a checkbox, so a stray Space
  // can never tick a fact the user has not read yet — and any close (取消, Esc,
  // successful submit) hands focus back to the 全部出清 trigger.
  useEffect(() => {
    const wasOpen = previousStepRef.current !== "idle";
    previousStepRef.current = step;
    if (step !== "idle") {
      headingRef.current?.focus();
    } else if (wasOpen) {
      triggerRef.current?.focus();
    }
  }, [step]);

  // Esc == 取消: closes the dialog and never submits. Locked while the
  // submission is in flight, same as the (aria-disabled) cancel button and as
  // `EditPositionModal`.
  useEffect(() => {
    if (step === "idle") return;
    function handleKeyDown(event: KeyboardEvent) {
      if (event.key === "Escape" && !mutation.isPending) cancelRef.current();
    }
    document.addEventListener("keydown", handleKeyDown);
    return () => document.removeEventListener("keydown", handleKeyDown);
  }, [step, mutation.isPending]);

  // Focus trap, same approach as `EditPositionModal`: Tab / Shift+Tab wrap
  // inside the dialog instead of leaking to the page behind it.
  function handleDialogKeyDown(event: React.KeyboardEvent<HTMLDivElement>) {
    if (event.key !== "Tab") return;
    const dialog = dialogRef.current;
    if (!dialog) return;
    const focusable = Array.from(dialog.querySelectorAll<HTMLElement>(FOCUSABLE_SELECTOR));
    const target = trapTabTarget(
      focusable.length,
      focusable.findIndex((element) => element === document.activeElement),
      event.shiftKey,
    );
    if (target === null) return;
    event.preventDefault();
    focusable[target]?.focus();
  }

  return (
    <div className="flex flex-col items-end gap-2">
      <button
        ref={triggerRef}
        type="button"
        onClick={openConfirm}
        className="rounded-md border border-neutral-600 bg-neutral-900 px-3 py-1.5 text-sm text-neutral-200 hover:bg-neutral-800"
      >
        全部出清
      </button>

      {/*
        N-159: the overlay is portalled to `document.body`. This control is
        rendered inside `ModeStatusBar`, a `sticky ... backdrop-blur` strip; an
        ancestor with `backdrop-filter` becomes the containing block of
        `position: fixed` descendants, which clipped the overlay to the strip's
        height (~86px), pushed the panel above the viewport and left the rest of
        the page undimmed. Outside the strip, `fixed inset-0` is viewport-relative
        again. The panel itself scrolls when the viewport is shorter than its
        content (`max-h` + `overflow-y-auto`).
      */}
      {step !== "idle" &&
        isClientMounted &&
        createPortal(
        <div
          ref={dialogRef}
          role="dialog"
          aria-modal="true"
          aria-label="全部出清確認"
          onKeyDown={handleDialogKeyDown}
          className="fixed inset-0 z-50 flex items-center justify-center bg-black/70 p-4"
        >
          <div className="max-h-[calc(100vh-2rem)] supports-[height:100dvh]:max-h-[calc(100dvh-2rem)] w-full max-w-lg overflow-y-auto rounded-md border border-neutral-700 bg-neutral-950 p-5">
            {step === "confirm" && (
              <>
                {/* 視覺規範 §4.3 逐字引用（Step 2 標頭）。 */}
                <h2
                  ref={headingRef}
                  tabIndex={-1}
                  className="text-lg font-semibold text-neutral-100"
                >
                  全部出清 — 確認前請閱讀以下事實
                </h2>
                <ul className="mt-4 space-y-3">
                  {checkTexts.map((text, index) => (
                    <li key={index} className="flex items-start gap-2">
                      <input
                        id={`exit-check-${index}`}
                        type="checkbox"
                        checked={checks[index] === true}
                        onChange={() => setChecks((prev) => toggleExitCheck(prev, index))}
                        className="mt-1"
                      />
                      <label htmlFor={`exit-check-${index}`} className="text-sm text-neutral-300">
                        {text}
                      </label>
                    </li>
                  ))}
                </ul>
                <div className="mt-5 flex justify-end gap-2">
                  <button
                    type="button"
                    onClick={cancel}
                    className="rounded-md border border-neutral-700 px-3 py-1.5 text-sm text-neutral-300 hover:bg-neutral-800"
                  >
                    取消
                  </button>
                  <button
                    type="button"
                    disabled={!allExitChecksConfirmed(checks)}
                    onClick={() => setStep("final")}
                    className="rounded-md border border-neutral-500 bg-neutral-800 px-3 py-1.5 text-sm text-neutral-100 hover:bg-neutral-700 disabled:cursor-not-allowed disabled:opacity-50"
                  >
                    我已閱讀，繼續
                  </button>
                </div>
              </>
            )}

            {step === "final" && (
              <>
                <h2
                  ref={headingRef}
                  tabIndex={-1}
                  className="text-lg font-semibold text-neutral-100"
                >
                  全部出清 — 二次確認
                </h2>
                {/* 排程台頁面審查 (suggested): Step 3 的覆述是二次確認前最後
                    一次讀到這些事實，對比度不低於 neutral-300。 */}
                <ul className="mt-4 space-y-2 text-sm text-neutral-300">
                  {checkTexts.map((text, index) => (
                    <li key={index}>{text}</li>
                  ))}
                </ul>
                {mutation.isError && (
                  <div className="mt-3">
                    <ErrorPanel label="全部出清送出失敗" error={mutation.error} />
                  </div>
                )}
                <div className="mt-5 flex justify-end gap-2">
                  {/*
                    N-163: while the submission is pending these two buttons use
                    `aria-disabled`, not the native `disabled`. A focused button
                    that becomes `disabled` drops focus to <body>, and the next
                    Tab then leaves the dialog for the page header link behind the
                    overlay (Enter on it navigates away mid-submit, hiding the
                    outcome of an irreversible action). `aria-disabled` keeps the
                    focused button focused and still announces it as unavailable;
                    `submit` / `cancel` refuse to act while the submit lock is
                    held or the mutation is pending. The attribute is omitted
                    (undefined) when idle, so only the "true" state matches the
                    `aria-disabled:` variants.
                  */}
                  <button
                    type="button"
                    onClick={cancel}
                    aria-disabled={mutation.isPending || undefined}
                    className="rounded-md border border-neutral-700 px-3 py-1.5 text-sm text-neutral-300 hover:bg-neutral-800 aria-disabled:cursor-not-allowed aria-disabled:opacity-50 aria-disabled:hover:bg-transparent"
                  >
                    取消
                  </button>
                  <button
                    type="button"
                    onClick={submit}
                    aria-disabled={mutation.isPending || undefined}
                    className="rounded-md border border-neutral-500 bg-neutral-800 px-3 py-1.5 text-sm text-neutral-100 hover:bg-neutral-700 aria-disabled:cursor-not-allowed aria-disabled:opacity-50 aria-disabled:hover:bg-neutral-800"
                  >
                    {mutation.isPending ? "送出中…" : "確認送出全部出清"}
                  </button>
                </div>
              </>
            )}
          </div>
        </div>,
        document.body,
      )}

      {/*
        視覺規範 §4.4 執行後狀態: 中性色階橫幅，非 rose. The message/mode_reason
        below are `wording.EMERGENCY_EXIT_RESULT`/`EMERGENCY_EXIT_EMPTY` and
        `wording.mode_reason_emergency`, both server-rendered verbatim.
      */}
      {mutation.isSuccess && (
        <div className="max-w-sm rounded-md border border-neutral-700 bg-neutral-900 p-4 text-sm text-neutral-200">
          <p>{mutation.data.message}</p>
          <p className="mt-1 text-neutral-300">{mutation.data.mode_reason}</p>
          {shouldRenderAttribution(mutation.data.attribution) && (
            <p className="mt-1 text-neutral-400">{mutation.data.attribution}</p>
          )}
          {mutation.data.warnings.length > 0 && (
            <ul className="mt-2 list-disc space-y-1 pl-5 text-neutral-400">
              {mutation.data.warnings.map((warning, i) => (
                <li key={i}>{warning}</li>
              ))}
            </ul>
          )}
        </div>
      )}
    </div>
  );
}

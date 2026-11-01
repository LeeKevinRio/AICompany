"use client";

import { useEffect, useLayoutEffect, useReducer, useRef, useState, useSyncExternalStore } from "react";
import type { RefObject } from "react";
import { createPortal } from "react-dom";
import { ErrorPanel } from "../components/ErrorPanel";
import {
  createExitDialogState,
  exitDialogReducer,
  planAdvance,
  planSubmit,
} from "../lib/exitDialogState";
import type { ExitTodayView } from "../lib/exitDialogState";
import { FOCUSABLE_SELECTOR, trapTabTarget } from "../lib/focusTrap";
import { allExitChecksConfirmed, EXIT_CONFIRM_CHECKS_UPDATED } from "../lib/playbookView";
import { nextTaipeiMidnight } from "../lib/taipeiDay";

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
 * EMERGENCY_EXIT 的兩步確認對話框 (視覺規範 §4.3): Step 2 is the fact-checklist
 * (`confirm`), which requires every checkbox ticked before advancing; Step 3
 * (`final`) is the second confirmation that actually calls
 * `POST /emergency-exit`. No checkbox is pre-ticked and there is no countdown
 * anywhere in this flow (EX-2 / 出口零摩擦). The step labels and button texts are
 * the pre-approved literals: 全部出清／我已閱讀，繼續／確認送出全部出清／取消.
 *
 * Mounted by `PlaybookPage` on `isOpen` alone — a sibling of the page content,
 * outside the `today.isSuccess` gate and outside whichever component hosts the
 * trigger (FE-C10, FE-C11, VETO-2) — so it survives every `/today` state
 * (FR-7b, AC-17, AC-22). It is portalled to `document.body` (N-159): an ancestor
 * with `backdrop-filter` would otherwise clip a `fixed inset-0` overlay.
 *
 * Which sentences Step 2/3 show, and what happens to the user's ticks when the
 * data under them changes, is `exitDialogState.ts` (風控 Q8/Q11). This component
 * only feeds it events: the set is chosen from `today` when the dialog mounts
 * (R-1, held in this reducer and dropped on close), and re-evaluated in a layout
 * effect — never in render (FE-C15, FE-C16).
 */
export function EmergencyExitDialog({
  today,
  isPending,
  isError,
  error,
  lockRef,
  onSubmit,
  onClose,
}: {
  /** What `/today` offers right now; built by the page from `isSuccess ? data.exit_confirm : null`. */
  today: ExitTodayView;
  isPending: boolean;
  isError: boolean;
  error: unknown;
  /** The page-level synchronous submit lock (FE-C16: read at effect time, never copied to a variable). */
  lockRef: RefObject<boolean>;
  /** Acquires the lock and fires the request; resolved at page level, not here. */
  onSubmit: () => void;
  onClose: () => void;
}) {
  const [state, dispatch] = useReducer(exitDialogReducer, today, createExitDialogState);
  const [tick, setTick] = useState(0);
  const isClientMounted = useIsClientMounted();
  const dialogRef = useRef<HTMLDivElement>(null);
  // The dialog's own scroll box: the failure panel reveals its label by scrolling it (V-41).
  const scrollRef = useRef<HTMLDivElement>(null);
  const headingRef = useRef<HTMLHeadingElement>(null);
  const cancelRef = useRef<() => void>(() => {});

  const allConfirmed = allExitChecksConfirmed(state.checks);
  // FE-C9: the failure panel needs both the failure and being on Step 3. A step
  // back (R-5) leaves the failure alone, so it is back when the user returns.
  const showFailure = isError && state.step === "final";

  // R-2～R-5 driver (FE-C16). A layout effect, so a swap is committed before
  // paint; its first line reads the lock *now*, so there is no window where the
  // lock is taken but a comparison still runs. `isPending` is a dependency so
  // that, once a failed submit releases the lock, the latest `/today` is
  // compared (R-5: "出清失敗後 R-2～R-4 照樣適用").
  useLayoutEffect(() => {
    if (lockRef.current || isPending) return;
    dispatch({ type: "reconcile", today, now: Date.now() });
  }, [today.status, today.dataUpdatedAt, isPending, tick]);

  // R-4 evaluation moments besides "after every comparison": the next Taipei
  // midnight after the held time, and the tab becoming visible / the window
  // regaining focus (a throttled background timer, a sleeping laptop). While the
  // lock is held the comparison above is skipped, and re-runs on release.
  useEffect(() => {
    if (state.heldAt === null) return;
    const delay = nextTaipeiMidnight(state.heldAt) - Date.now();
    if (delay <= 0) return; // already past; the comparison above handles it
    const id = window.setTimeout(() => setTick((n) => n + 1), delay);
    return () => window.clearTimeout(id);
  }, [state.heldAt, tick]);

  useEffect(() => {
    const bump = () => setTick((n) => n + 1);
    const onVisibility = () => {
      if (document.visibilityState === "visible") bump();
    };
    document.addEventListener("visibilitychange", onVisibility);
    window.addEventListener("focus", bump);
    return () => {
      document.removeEventListener("visibilitychange", onVisibility);
      window.removeEventListener("focus", bump);
    };
  }, []);

  function cancel() {
    // Defence in depth for the aria-disabled cancel button (still focusable and
    // clickable while the submission is in flight): never close mid-submit.
    if (lockRef.current || isPending) return;
    onClose();
  }

  function advance() {
    if (!allConfirmed) return; // aria-disabled, not disabled: still activatable
    // R-4, evaluated synchronously: the click must not carry a stale formal set
    // past step 2. `expire` swaps in the degraded set and un-ticks what changed.
    if (planAdvance(state, Date.now()) === "expire") {
      dispatch({ type: "expire", now: Date.now() });
      return;
    }
    dispatch({ type: "advance" });
  }

  function submit(event: React.MouseEvent<HTMLButtonElement>) {
    // N-163: the button stays `aria-disabled` (not `disabled`) while pending, so
    // it keeps focus; a second activation (Enter / Space / click) must not fire
    // a second irreversible POST. Order is fixed (FE-C17): lock check, R-4
    // check, then the page takes the lock and calls `mutate`.
    const plan = planSubmit(state, Date.now(), lockRef.current || isPending);
    if (plan === "ignore") return;
    if (plan === "stepBack") {
      // A confirmed formal set has crossed a Taipei midnight: the click becomes
      // the R-5 step back, and no request is sent.
      dispatch({ type: "expire", now: Date.now() });
      return;
    }
    // Safari / Firefox-on-macOS do not focus a button on click; make it explicit
    // so focus is on a dialog control before the pending state begins.
    event.currentTarget.focus();
    onSubmit();
  }

  // Keep the latest `cancel` reachable from the document-level Esc listener
  // without re-subscribing on every render.
  useEffect(() => {
    cancelRef.current = cancel;
  });

  // Every step (and the R-5 step back) moves focus to the step's heading — not
  // a checkbox, so a stray Space can never tick a fact the user has not read yet.
  // Closing hands focus back at page level (`useEmergencyExitFlow`). N1 appearing
  // does not run this: it does not change the step, and moves no focus (R-6).
  useEffect(() => {
    headingRef.current?.focus();
  }, [state.step]);

  // Esc == 取消: closes the dialog and never submits. Locked while the
  // submission is in flight, same as the (aria-disabled) cancel button and as
  // `EditPositionModal`.
  useEffect(() => {
    function handleKeyDown(event: KeyboardEvent) {
      if (event.key === "Escape" && !isPending) cancelRef.current();
    }
    document.addEventListener("keydown", handleKeyDown);
    return () => document.removeEventListener("keydown", handleKeyDown);
  }, [isPending]);

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
    <>
      {/*
        N-159: the overlay is portalled to `document.body`. The dialog used to be
        rendered inside `ModeStatusBar`, a `sticky ... backdrop-blur` strip; an
        ancestor with `backdrop-filter` becomes the containing block of
        `position: fixed` descendants, which clipped the overlay to the strip's
        height (~86px). Outside any such ancestor, `fixed inset-0` is
        viewport-relative again. The panel itself scrolls when the viewport is
        shorter than its content (`max-h` + `overflow-y-auto`).
      */}
      {isClientMounted &&
        createPortal(
          <div
            ref={dialogRef}
            role="dialog"
            aria-modal="true"
            aria-label="全部出清確認"
            onKeyDown={handleDialogKeyDown}
            className="fixed inset-0 z-50 flex items-center justify-center bg-black/70 p-4"
          >
            <div
              ref={scrollRef}
              className="max-h-[calc(100vh-2rem)] supports-[height:100dvh]:max-h-[calc(100dvh-2rem)] w-full max-w-lg overflow-y-auto rounded-md border border-neutral-700 bg-neutral-950 p-5"
            >
              {/* 視覺規範 §4.3 逐字引用（Step 2、Step 3 標頭）。One heading node for both steps. */}
              <h2
                ref={headingRef}
                tabIndex={-1}
                className="text-lg font-semibold text-neutral-100"
              >
                {state.step === "confirm" ? "全部出清 — 確認前請閱讀以下事實" : "全部出清 — 二次確認"}
              </h2>

              {/*
                風控 Q11 N1 (R-6, 視覺規範 §13): a permanent, class-less live region
                right under the heading, the same DOM node on both steps and across
                an R-5 step back — a live region must exist before its content
                appears, or screen readers skip the announcement. N1 only goes
                *into* it; it is rendered when the system cleared at least one tick
                (see `exitDialogState`), stays until the dialog closes, and has no
                close button.
              */}
              <div role="status">
                {state.notice && (
                  <p className="mt-3 text-sm text-neutral-300">{EXIT_CONFIRM_CHECKS_UPDATED}</p>
                )}
              </div>

              {state.step === "confirm" && (
                <>
                  <ul className="mt-4 space-y-3">
                    {state.texts.map((text, index) => (
                      <li key={index} className="flex items-start gap-2">
                        <input
                          id={`exit-check-${index}`}
                          type="checkbox"
                          checked={state.checks[index] === true}
                          onChange={() => dispatch({ type: "toggle", index })}
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
                    {/*
                      `aria-disabled`, not the native `disabled`: a sentence swap (R-3)
                      can switch this button off while the user's focus is on it, and a
                      focused element that becomes `disabled` drops focus to <body>
                      (AC-46: activeElement is not moved). Same reasoning as Step 3's
                      buttons (N-163); `advance` refuses to act until every tick is set.
                    */}
                    <button
                      type="button"
                      aria-disabled={!allConfirmed || undefined}
                      onClick={advance}
                      className="rounded-md border border-neutral-500 bg-neutral-800 px-3 py-1.5 text-sm text-neutral-100 hover:bg-neutral-700 aria-disabled:cursor-not-allowed aria-disabled:opacity-50 aria-disabled:hover:bg-neutral-800"
                    >
                      我已閱讀，繼續
                    </button>
                  </div>
                </>
              )}

              {state.step === "final" && (
                <>
                  {/* 排程台頁面審查 (suggested): Step 3 的覆述是二次確認前最後
                      一次讀到這些事實，對比度不低於 neutral-300。 */}
                  <ul className="mt-4 space-y-2 text-sm text-neutral-300">
                    {state.texts.map((text, index) => (
                      <li key={index}>{text}</li>
                    ))}
                  </ul>
                  {showFailure && (
                    <div className="mt-3">
                      <ErrorPanel label="全部出清送出失敗" error={error} />
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
                      aria-disabled={isPending || undefined}
                      className="rounded-md border border-neutral-700 px-3 py-1.5 text-sm text-neutral-300 hover:bg-neutral-800 aria-disabled:cursor-not-allowed aria-disabled:opacity-50 aria-disabled:hover:bg-transparent"
                    >
                      取消
                    </button>
                    <button
                      type="button"
                      onClick={submit}
                      aria-disabled={isPending || undefined}
                      className="rounded-md border border-neutral-500 bg-neutral-800 px-3 py-1.5 text-sm text-neutral-100 hover:bg-neutral-700 aria-disabled:cursor-not-allowed aria-disabled:opacity-50 aria-disabled:hover:bg-neutral-800"
                    >
                      {isPending ? "送出中…" : "確認送出全部出清"}
                    </button>
                  </div>
                </>
              )}
            </div>
          </div>,
          document.body,
        )}
    </>
  );
}

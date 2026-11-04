/**
 * The 受理回執 (the banner shown after `POST /emergency-exit` is accepted) as
 * its own piece of state, deliberately *not* derived from the mutation.
 *
 * Why not `mutation.data` / `useMutationState` (tech-architect Q14, VETO-1):
 * `mutation.reset()`, the next `mutate()` and observer unmount each drop
 * `mutation.data`, and an orphaned mutation is garbage-collected after five
 * minutes. The receipt is the only place the user can read the sell directive
 * the exit produced (`/today` does not disclose it), and 風控's floor (FE-3,
 * V-42) says it ends only on a page reload or when a newer receipt replaces it
 * — never because of what `/today` or the dialog is doing.
 *
 * So the lifecycle is encoded in the reducer's type: one action, `accepted`,
 * and no way to clear. The reducer runs inside the Providers-scope store
 * (`exitReceiptStore.ts`, 風控 2026-11-01 Q15 → 方案 D), in memory only: nothing
 * here may be written to storage, a cookie, the URL or `history.state` (VETO-3),
 * which is why a reload — a new document — ends it, and a SPA navigation does
 * not.
 */

import type { PlaybookEmergencyExitResponse } from "./types";

export interface ExitReceipt {
  /** Strictly increasing per accepted response; the scroll effect keys on it. */
  readonly seq: number;
  readonly response: PlaybookEmergencyExitResponse;
}

/**
 * Everything the store holds (tech-architect ADR-0037 FE-C2): the receipt and
 * the 「already scrolled」 marker, and nothing else — no `exit_confirm`, no dialog
 * state, no lock, no mutation, no in-flight flag (F-1, VETO-5).
 */
export interface ExitReceiptStoreState {
  readonly receipt: ExitReceipt | null;
  /** The highest receipt sequence number a page has already scrolled to (0 = none). */
  readonly scrolledSeq: number;
}

export const INITIAL_EXIT_RECEIPT_STATE: ExitReceiptStoreState = Object.freeze({
  receipt: null,
  scrolledSeq: 0,
});

/** A newer accepted response: seq +1, replaces the receipt. */
export interface ExitReceiptAccepted {
  readonly type: "accepted";
  readonly response: PlaybookEmergencyExitResponse;
}

/** A page has dealt with the scroll for receipt `seq`; the receipt itself is untouched. */
export interface ExitReceiptScrollHandled {
  readonly type: "scrollHandled";
  readonly seq: number;
}

/** The only two actions. There is deliberately no clear / reset / dismiss / setter. */
export type ExitReceiptAction = ExitReceiptAccepted | ExitReceiptScrollHandled;

export function exitReceiptReducer(
  state: ExitReceiptStoreState,
  action: ExitReceiptAction,
): ExitReceiptStoreState {
  switch (action.type) {
    case "accepted":
      return {
        receipt: { seq: (state.receipt?.seq ?? 0) + 1, response: action.response },
        scrolledSeq: state.scrolledSeq,
      };
    case "scrollHandled":
      // max(): the marker only moves forward. Same reference when nothing moves,
      // so a repeated call neither notifies nor re-renders.
      return action.seq > state.scrolledSeq ? { ...state, scrolledSeq: action.seq } : state;
    default:
      return state;
  }
}

/**
 * Whether the banner drops its own `mode_reason` paragraph (FR-5, 風控 必改項 4).
 *
 * Both must hold, decided in the same render as the status bar's own mount
 * condition: the bar is mounted (`today.isSuccess` — the very expression the
 * page gates `ModeStatusBar` with, never "the trigger's container exists", F-6),
 * and `/today`'s `mode_reason` equals the receipt's strictly, character for
 * character (no trim, no normalisation). Otherwise the banner keeps it, so the
 * page-wide count of that sentence is never 0.
 */
export function isReceiptModeReasonHidden(
  todayIsSuccess: boolean,
  todayModeReason: string | null,
  receiptModeReason: string,
): boolean {
  return todayIsSuccess && todayModeReason !== null && todayModeReason === receiptModeReason;
}

/**
 * Whether the page should scroll to the receipt now (FR-3, FE-C8; 風控 FE-3 /
 * tech-architect ADR-0037).
 *
 * Once per *receipt*: the receipt is newer than the marker in the store, so a
 * page mounted again with a receipt it has shown does not scroll, while one that
 * arrived while the user was elsewhere is scrolled to once on return. Never
 * because the banner node mounted (a second receipt may reuse the node) and never
 * because `/today` refetched. Deferred while the dialog is open: the receipt is
 * written by the mutation's own `onSuccess`, one step before the dialog closes
 * and, with the dialog still open behind its overlay, a scroll would move the page
 * under it.
 */
export function shouldScrollForReceipt(
  receiptSeq: number | undefined,
  scrolledSeq: number,
  isOpen: boolean,
): boolean {
  return receiptSeq !== undefined && receiptSeq > scrolledSeq && !isOpen;
}

/** 視覺規範 §4.1: the gap a banner keeps below the sticky status bar, in px. */
export const RECEIPT_BAR_GAP_PX = 16;

/**
 * 視覺規範 §4.1 step 2: scroll only when the banner is hidden behind / too close
 * to the sticky bar, or sits below the top two thirds of the viewport. With no
 * sticky bar (`/today` not successful) pass `barBottom = 0`.
 */
export function receiptNeedsScroll(
  bannerTop: number,
  barBottom: number,
  viewportHeight: number,
): boolean {
  return bannerTop < barBottom + RECEIPT_BAR_GAP_PX || bannerTop > viewportHeight * 0.66;
}

/**
 * After the `scroll-mt-*` scroll, how far to scroll *further* when the bar is
 * taller than the fixed offset assumed (快市啟動 makes it wrap; 風控 必改項 12):
 * a negative number moves the page up so the banner's first line clears the
 * bar. Zero when it already does. This is the "measure the bar as it is now, add 16px"
 * fallback — it never loosens the bar's own height limits.
 */
export function receiptScrollCorrection(bannerTop: number, barBottom: number): number {
  const wanted = barBottom + RECEIPT_BAR_GAP_PX;
  return bannerTop < wanted ? bannerTop - wanted : 0;
}

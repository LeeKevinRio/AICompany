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

export type ExitReceiptState = ExitReceipt | null;

/** The only action. There is deliberately no clear / reset / dismiss. */
export interface ExitReceiptAccepted {
  readonly type: "accepted";
  readonly response: PlaybookEmergencyExitResponse;
}

export type ExitReceiptAction = ExitReceiptAccepted;

export function exitReceiptReducer(
  state: ExitReceiptState,
  action: ExitReceiptAction,
): ExitReceiptState {
  switch (action.type) {
    case "accepted":
      return { seq: (state?.seq ?? 0) + 1, response: action.response };
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
 * Whether a receipt has not been scrolled to yet (FR-3, FE-C8). The scroll runs
 * once per *new receipt* — never because the banner node mounted (a second
 * receipt may reuse the node) and never because `/today` refetched.
 */
export function shouldScrollForReceipt(
  receiptSeq: number | undefined,
  lastHandledSeq: number,
): boolean {
  return receiptSeq !== undefined && receiptSeq > lastHandledSeq;
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

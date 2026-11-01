"use client";

import { useEffect, useReducer, useRef, useState } from "react";
import type { RefObject } from "react";
import {
  exitReceiptReducer,
  receiptNeedsScroll,
  receiptScrollCorrection,
  shouldScrollForReceipt,
} from "../lib/exitReceipt";
import type { ExitReceipt } from "../lib/exitReceipt";
import { useEmergencyExit } from "../lib/queries";

export interface EmergencyExitFlow {
  isOpen: boolean;
  open: () => void;
  close: () => void;
  submit: () => void;
  /** The current receipt, or null before the first accepted exit. Never cleared. */
  receipt: ExitReceipt | null;
  isPending: boolean;
  isError: boolean;
  /** Synchronous submit lock; the dialog reads it at effect time (FE-C16). */
  lockRef: RefObject<boolean>;
  /** The one trigger button currently mounted, in whichever placement. */
  triggerRef: RefObject<HTMLButtonElement | null>;
  focusLostRef: RefObject<boolean>;
  bannerRef: RefObject<HTMLDivElement | null>;
  statusBarRef: RefObject<HTMLDivElement | null>;
}

/**
 * Everything about the 全部出清 flow that must outlive any `/today` state, owned
 * by `PlaybookPage` and nothing below the `today.isSuccess` gate (tech-architect
 * Q14, VETO-2, FE-C1/C4/C9/C10/C19):
 *
 * - the one `useEmergencyExit` observer. If it lived inside the status bar it
 *   would be removed when `/today` fails, and TanStack skips mutate-level
 *   callbacks of an observer with no listener — the lock would never release
 *   and the dialog would never close;
 * - the receipt reducer (the banner's only source — VETO-1);
 * - `isOpen`, the submit lock and the trigger ref;
 * - focus return on close, and the once-per-receipt scroll.
 */
export function useEmergencyExitFlow(): EmergencyExitFlow {
  const mutation = useEmergencyExit();
  const [isOpen, setIsOpen] = useState(false);
  const [receipt, dispatchReceipt] = useReducer(exitReceiptReducer, null);

  // Synchronous submit lock. `mutation.isPending` only flips after a render, so
  // two activations inside the same tick would both see `false` and fire two
  // irreversible POSTs; a ref is updated immediately (N-163). Released only in
  // the mutate-level `onSettled`, i.e. on success and failure alike.
  const lockRef = useRef(false);
  const triggerRef = useRef<HTMLButtonElement | null>(null);
  const focusLostRef = useRef(false);
  const bannerRef = useRef<HTMLDivElement | null>(null);
  const statusBarRef = useRef<HTMLDivElement | null>(null);

  function open() {
    // The only place `reset()` is used: it clears the previous round's failure
    // panel. It cannot clear the receipt, which is not in the mutation (FE-C9).
    mutation.reset();
    setIsOpen(true);
  }

  function close() {
    // Never close mid-submit (defence in depth for the aria-disabled 取消).
    if (lockRef.current || mutation.isPending) return;
    setIsOpen(false);
  }

  function submit() {
    // N-163: the 確認送出 button stays `aria-disabled` (not `disabled`) while
    // pending, so a second activation can still arrive; the ref covers the
    // window before `isPending` renders.
    if (lockRef.current || mutation.isPending) return;
    lockRef.current = true;
    mutation.mutate(undefined, {
      // FE-C4: the receipt is recorded here, in the page-level observer's
      // mutate callback — not in render, not in an effect watching the mutation.
      onSuccess: (response) => {
        dispatchReceipt({ type: "accepted", response });
        setIsOpen(false);
      },
      // Release the lock on success and failure alike so a failed submit can be
      // retried.
      onSettled: () => {
        lockRef.current = false;
      },
    });
  }

  // FE-C19 / FR-13f: any close (取消, Esc, a successful submit) hands focus back
  // to the trigger that exists *now* — the ref follows the placement, so a
  // trigger that swapped while the dialog was open is never missed. Without
  // `preventScroll` the focus call would scroll the receipt away again.
  const wasOpenRef = useRef(false);
  useEffect(() => {
    if (wasOpenRef.current && !isOpen) {
      triggerRef.current?.focus({ preventScroll: true });
    }
    wasOpenRef.current = isOpen;
  }, [isOpen]);

  // FE-C8 / FR-3: scroll the receipt into view once per *new receipt*. The only
  // dependency is its sequence number — never `today.*` — so a `/today` refetch
  // cannot scroll again, and a page that mounts with a receipt (it cannot today)
  // would not either. No focus moves (§2.4: the banner is not focusable).
  const receiptSeq = receipt?.seq;
  const lastHandledSeq = useRef(receipt?.seq ?? 0);
  useEffect(() => {
    if (!shouldScrollForReceipt(receiptSeq, lastHandledSeq.current)) return;
    lastHandledSeq.current = receiptSeq ?? lastHandledSeq.current;
    const banner = bannerRef.current;
    if (banner === null) return;
    const barBottom = () => statusBarRef.current?.getBoundingClientRect().bottom ?? 0;
    if (!receiptNeedsScroll(banner.getBoundingClientRect().top, barBottom(), window.innerHeight)) {
      return;
    }
    // `behavior: "auto"` — instant, never smooth, whatever prefers-reduced-motion
    // says (視覺規範 §4.1). `scroll-mt-*` on the banner supplies the offset.
    banner.scrollIntoView({ block: "start", behavior: "auto" });
    // 風控 必改項 12: with a tall bar (快市啟動) the fixed offset may fall short;
    // measure the bar as it is now and nudge so the first line is not covered.
    const correction = receiptScrollCorrection(banner.getBoundingClientRect().top, barBottom());
    if (correction !== 0) window.scrollBy({ top: correction, behavior: "auto" });
  }, [receiptSeq]);

  return {
    isOpen,
    open,
    close,
    submit,
    receipt,
    isPending: mutation.isPending,
    isError: mutation.isError,
    lockRef,
    triggerRef,
    focusLostRef,
    bannerRef,
    statusBarRef,
  };
}

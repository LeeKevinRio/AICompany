/**
 * The 受理回執 store: Providers-scope, in-memory, one per document (風控 2026-11-01
 * Q15 → 方案 D, FE-1; tech-architect Q14 備案 D).
 *
 * Why not page state (the earlier 方案 A): the receipt must end only on a
 * reload or when a newer receipt replaces it. A SPA navigation — the user
 * clicks 庫存 to look at holdings, then 排程台 again — is not a reload, and the
 * banner's `message` is the only place the app lists the sell directive's
 * batches, shares and execution date (N-171). Page state would drop it on the
 * first navigation, and returning while `/today` is failing would leave the page
 * with no `mode_reason` at all.
 *
 * Definition used (風控 Q15): the 「工作階段」 is one document's lifetime. A
 * reload, a new tab, typing the URL or any hard navigation builds a new
 * document, and with it a new store — empty, because nothing is persisted
 * (VETO-3: no storage, cookie, IndexedDB, URL or `history.state`). The store is
 * created inside a component (`useState(() => …)` in the provider) and handed
 * down by context — never a module-level singleton, which SSR would share
 * across requests.
 *
 * Content: the receipt `{ seq, response }` and the 「已捲過」 marker, nothing
 * else — no `exit_confirm`, no dialog state, no submit lock, no mutation (F-1).
 * The reducer from `exitReceipt.ts` is reused unchanged, so the only way to
 * change the receipt is `accepted`: there is no clear.
 */

import { exitReceiptReducer } from "./exitReceipt";
import type { ExitReceipt, ExitReceiptState } from "./exitReceipt";
import type { PlaybookEmergencyExitResponse } from "./types";

export interface ExitReceiptStore {
  /** The current receipt (a stable reference between changes), or null. */
  getSnapshot: () => ExitReceiptState;
  subscribe: (listener: () => void) => () => void;
  /** Record an accepted response as the newest receipt. Works with no page mounted. */
  accept: (response: PlaybookEmergencyExitResponse) => void;
  /** The highest receipt sequence number that a page has already scrolled to. */
  getScrolledSeq: () => number;
  /**
   * Mark `seq` as scrolled to. Deliberately silent: nothing renders from it, so
   * it does not notify and the snapshot is untouched.
   */
  markScrolled: (seq: number) => void;
}

export function createExitReceiptStore(): ExitReceiptStore {
  let receipt: ExitReceiptState = null;
  let scrolledSeq = 0;
  const listeners = new Set<() => void>();

  return {
    getSnapshot: () => receipt,
    subscribe: (listener) => {
      listeners.add(listener);
      return () => {
        listeners.delete(listener);
      };
    },
    accept: (response) => {
      receipt = exitReceiptReducer(receipt, { type: "accepted", response });
      for (const listener of [...listeners]) listener();
    },
    getScrolledSeq: () => scrolledSeq,
    markScrolled: (seq) => {
      scrolledSeq = Math.max(scrolledSeq, seq);
    },
  };
}

export type { ExitReceipt };

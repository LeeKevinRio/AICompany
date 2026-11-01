/**
 * The 受理回執 store: Providers-scope, in-memory, one per document (風控 2026-11-01
 * Q15 → 方案 D, FE-1; tech-architect ADR-0037 D, FE-C1/C2).
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
 * down by context — never a module-level instance, `globalThis` or `window`
 * member, which SSR would share across requests (VETO-5).
 *
 * State: `{ receipt, scrolledSeq }`, nothing else (FE-C2). The reducer has two
 * actions, `accepted` and `scrollHandled`, and no way to clear. The store never
 * sends a request and holds nothing in flight (VETO-5); the submit lock stays in
 * the page instance — a cross-instance gate is VETO-4.
 */

import { INITIAL_EXIT_RECEIPT_STATE, exitReceiptReducer } from "./exitReceipt";
import type { ExitReceiptStoreState } from "./exitReceipt";
import type { PlaybookEmergencyExitResponse } from "./types";

/**
 * The narrow door the mutation's definition-level `onSuccess` is given
 * (FE-C4): it can record an accepted response and do nothing else.
 */
export interface ExitReceiptSink {
  accept: (response: PlaybookEmergencyExitResponse) => void;
}

export interface ExitReceiptStore extends ExitReceiptSink {
  /** The state; the same reference until something changes. */
  getSnapshot: () => ExitReceiptStoreState;
  /** What the server render sees: always the empty initial state. */
  getServerSnapshot: () => ExitReceiptStoreState;
  subscribe: (listener: () => void) => () => void;
  /** Mark receipt `seq` as scrolled to; no-op (no notification) if it already was. */
  scrollHandled: (seq: number) => void;
}

export interface ExitReceiptStoreOptions {
  /**
   * Where an exception thrown by a *subscriber* goes (FE-C4(b)). Default: rethrow
   * out of band with `void Promise.reject(e)`, the way TanStack treats its own
   * observer callbacks. Injected so a test can observe it.
   */
  onSubscriberError?: (error: unknown) => void;
  /**
   * The state transition. Defaults to {@link exitReceiptReducer}; a test injects a
   * throwing one to prove that a failure *before* the snapshot is committed
   * escapes `accept()` untouched (FE-T13 c2).
   */
  reducer?: typeof exitReceiptReducer;
}

function rethrowOutOfBand(error: unknown): void {
  void Promise.reject(error);
}

export function createExitReceiptStore(options: ExitReceiptStoreOptions = {}): ExitReceiptStore {
  const reduce = options.reducer ?? exitReceiptReducer;
  const onSubscriberError = options.onSubscriberError ?? rethrowOutOfBand;
  let state: ExitReceiptStoreState = INITIAL_EXIT_RECEIPT_STATE;
  const listeners = new Set<() => void>();

  /**
   * The one write path (FE-C4(b)(c)), in this fixed order:
   *
   * 1. the reducer computes the new state;
   * 2. the snapshot is committed;
   * 3. each subscriber is notified, each in its own try/catch.
   *
   * Nothing that can throw may be added before step 2 other than the reducer
   * itself -- no validation, logging or formatting. A throw in 1 or 2 escapes
   * untouched: the mutation then ends in `error` and the NB-6 panel shows, so a
   * success status always means the receipt is in (INV-1). A throw in 3 is
   * handed to `onSubscriberError` and never escapes: by then the receipt is
   * committed, and 「accept() returned」 means 「the snapshot is committed」.
   */
  function dispatch(action: Parameters<typeof exitReceiptReducer>[1]): void {
    const next = reduce(state, action);
    if (next === state) return;
    state = next;
    for (const listener of [...listeners]) {
      try {
        listener();
      } catch (error) {
        try {
          onSubscriberError(error);
        } catch (handlerError) {
          rethrowOutOfBand(handlerError);
        }
      }
    }
  }

  return {
    getSnapshot: () => state,
    getServerSnapshot: () => INITIAL_EXIT_RECEIPT_STATE,
    subscribe: (listener) => {
      listeners.add(listener);
      return () => {
        listeners.delete(listener);
      };
    },
    accept: (response) => dispatch({ type: "accepted", response }),
    scrollHandled: (seq) => dispatch({ type: "scrollHandled", seq }),
  };
}

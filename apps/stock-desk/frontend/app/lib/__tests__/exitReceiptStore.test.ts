/**
 * FE-T1 (store part) / FE-T3: the Providers-scope receipt store (風控 2026-11-01
 * Q15 → 方案 D; ADR-0037 FE-C1, FE-C2): in-memory, one per document, written
 * whether or not a page is mounted, carrying the 「already scrolled」 marker that
 * makes the scroll once per receipt across page instances.
 */

import { describe, expect, it, vi } from "vitest";
import { INITIAL_EXIT_RECEIPT_STATE, shouldScrollForReceipt } from "../exitReceipt";
import { createExitReceiptStore } from "../exitReceiptStore";
import { receiptResponse } from "./exitFixtures";

describe("createExitReceiptStore", () => {
  it("starts empty with nothing scrolled, and the server snapshot is always that empty state", () => {
    const store = createExitReceiptStore();
    expect(store.getSnapshot()).toEqual({ receipt: null, scrolledSeq: 0 });
    expect(store.getServerSnapshot()).toBe(INITIAL_EXIT_RECEIPT_STATE);
    store.accept(receiptResponse());
    expect(store.getServerSnapshot()).toBe(INITIAL_EXIT_RECEIPT_STATE);
  });

  it("accept records the newest receipt, numbered 1, 2, ..., replacing the previous one", () => {
    const store = createExitReceiptStore();
    store.accept(receiptResponse({ message: "first" }));
    expect(store.getSnapshot().receipt?.seq).toBe(1);
    store.accept(receiptResponse({ message: "second" }));
    expect(store.getSnapshot().receipt?.seq).toBe(2);
    expect(store.getSnapshot().receipt?.response.message).toBe("second");
  });

  it("keeps the snapshot reference stable between changes (useSyncExternalStore requirement)", () => {
    const store = createExitReceiptStore();
    store.accept(receiptResponse());
    expect(store.getSnapshot()).toBe(store.getSnapshot());
    const before = store.getSnapshot();
    store.scrollHandled(0);
    expect(store.getSnapshot()).toBe(before);
  });

  it("notifies subscribers on accept and on a scrollHandled that moves the marker, and stops after unsubscribe", () => {
    const store = createExitReceiptStore();
    const listener = vi.fn();
    const unsubscribe = store.subscribe(listener);
    store.accept(receiptResponse());
    expect(listener).toHaveBeenCalledTimes(1);
    store.scrollHandled(1);
    expect(listener).toHaveBeenCalledTimes(2);
    store.scrollHandled(1); // already handled: no change, no notification
    expect(listener).toHaveBeenCalledTimes(2);
    unsubscribe();
    store.accept(receiptResponse());
    expect(listener).toHaveBeenCalledTimes(2);
  });

  it("accepts a response with no subscriber at all (the page has unmounted), and a later mount reads it", () => {
    const store = createExitReceiptStore();
    store.accept(receiptResponse({ message: "arrived while elsewhere" }));
    expect(store.getSnapshot().receipt?.response.message).toBe("arrived while elsewhere");
  });

  it("two stores are independent: there is no shared module state", () => {
    const a = createExitReceiptStore();
    const b = createExitReceiptStore();
    a.accept(receiptResponse());
    a.scrollHandled(1);
    expect(b.getSnapshot()).toEqual({ receipt: null, scrolledSeq: 0 });
  });

  it("commits the snapshot before notifying anyone: a subscriber already sees the new receipt", () => {
    const store = createExitReceiptStore();
    const seen: Array<number | undefined> = [];
    store.subscribe(() => seen.push(store.getSnapshot().receipt?.seq));
    store.accept(receiptResponse());
    expect(seen).toEqual([1]);
  });

  it("a failure in the reducer escapes accept() and commits and notifies nothing", () => {
    const store = createExitReceiptStore({
      reducer: () => {
        throw new Error("reducer exploded");
      },
    });
    const listener = vi.fn();
    store.subscribe(listener);
    const before = store.getSnapshot();
    expect(() => store.accept(receiptResponse())).toThrow("reducer exploded");
    expect(store.getSnapshot()).toBe(before);
    expect(listener).not.toHaveBeenCalled();
  });

  it("a throwing subscriber does not stop the others, does not escape accept(), and is reported once", () => {
    const onSubscriberError = vi.fn();
    const store = createExitReceiptStore({ onSubscriberError });
    const failure = new Error("subscriber exploded");
    const after = vi.fn();
    store.subscribe(() => {
      throw failure;
    });
    store.subscribe(after);
    expect(() => store.accept(receiptResponse())).not.toThrow();
    expect(store.getSnapshot().receipt?.seq).toBe(1);
    expect(after).toHaveBeenCalledTimes(1);
    expect(onSubscriberError).toHaveBeenCalledExactlyOnceWith(failure);
    // The same isolation holds for the scroll marker.
    expect(() => store.scrollHandled(1)).not.toThrow();
    expect(onSubscriberError).toHaveBeenCalledTimes(2);
  });

  it("exposes exactly the sink, the snapshots, subscribe and scrollHandled: no clear, no setter, no request", () => {
    expect(Object.keys(createExitReceiptStore()).sort()).toEqual(
      ["accept", "getServerSnapshot", "getSnapshot", "scrollHandled", "subscribe"].sort(),
    );
  });
});

describe("scroll once per receipt across page instances (風控 FE-3; FE-C8)", () => {
  /** What a freshly mounted page does when its scroll effect runs. */
  function runEffect(store: ReturnType<typeof createExitReceiptStore>, isOpen = false): boolean {
    const { receipt, scrolledSeq } = store.getSnapshot();
    if (receipt === null || !shouldScrollForReceipt(receipt.seq, scrolledSeq, isOpen)) return false;
    store.scrollHandled(receipt.seq);
    return true;
  }

  it("a receipt shown by one page instance is not scrolled to again when the page is mounted again", () => {
    const store = createExitReceiptStore();
    store.accept(receiptResponse());
    expect(runEffect(store)).toBe(true);
    expect(runEffect(store)).toBe(false); // navigate away and back
    expect(runEffect(store)).toBe(false);
  });

  it("a StrictMode double run of the effect scrolls once: the second run re-reads the store", () => {
    const store = createExitReceiptStore();
    store.accept(receiptResponse());
    expect([runEffect(store), runEffect(store)]).toEqual([true, false]);
  });

  it("a receipt that arrived while the page was not mounted is scrolled to once on return", () => {
    const store = createExitReceiptStore();
    store.accept(receiptResponse());
    runEffect(store);
    store.accept(receiptResponse({ message: "arrived elsewhere" }));
    expect(runEffect(store)).toBe(true);
    expect(runEffect(store)).toBe(false);
  });

  it("a receipt written while the dialog is open waits for it to close, then scrolls once", () => {
    const store = createExitReceiptStore();
    store.accept(receiptResponse());
    expect(runEffect(store, true)).toBe(false);
    expect(runEffect(store, false)).toBe(true);
    expect(runEffect(store, false)).toBe(false);
  });

  it("a mount with no receipt never scrolls", () => {
    expect(runEffect(createExitReceiptStore())).toBe(false);
  });
});

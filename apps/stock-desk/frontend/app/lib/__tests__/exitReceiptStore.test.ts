/**
 * The Providers-scope receipt store (風控 2026-11-01 Q15 → 方案 D, FE-1～FE-4):
 * in-memory, one per document, written whether or not a page is mounted, and
 * carrying the 「already scrolled」 marker that makes the scroll once per receipt
 * across page instances.
 */

import { describe, expect, it, vi } from "vitest";
import { shouldScrollForReceipt } from "../exitReceipt";
import { createExitReceiptStore } from "../exitReceiptStore";
import { receiptResponse } from "./exitFixtures";

describe("createExitReceiptStore", () => {
  it("starts empty with nothing scrolled", () => {
    const store = createExitReceiptStore();
    expect(store.getSnapshot()).toBeNull();
    expect(store.getScrolledSeq()).toBe(0);
  });

  it("accept records the newest receipt, numbered 1, 2, ..., replacing the previous one", () => {
    const store = createExitReceiptStore();
    store.accept(receiptResponse({ message: "first" }));
    expect(store.getSnapshot()?.seq).toBe(1);
    store.accept(receiptResponse({ message: "second" }));
    expect(store.getSnapshot()?.seq).toBe(2);
    expect(store.getSnapshot()?.response.message).toBe("second");
  });

  it("keeps the snapshot reference stable between changes (useSyncExternalStore requirement)", () => {
    const store = createExitReceiptStore();
    store.accept(receiptResponse());
    expect(store.getSnapshot()).toBe(store.getSnapshot());
    const before = store.getSnapshot();
    store.markScrolled(1);
    expect(store.getSnapshot()).toBe(before);
  });

  it("notifies subscribers on accept, not on markScrolled, and stops after unsubscribe", () => {
    const store = createExitReceiptStore();
    const listener = vi.fn();
    const unsubscribe = store.subscribe(listener);
    store.accept(receiptResponse());
    expect(listener).toHaveBeenCalledTimes(1);
    store.markScrolled(1);
    expect(listener).toHaveBeenCalledTimes(1);
    unsubscribe();
    store.accept(receiptResponse());
    expect(listener).toHaveBeenCalledTimes(1);
  });

  it("accepts a response with no subscriber at all (the page has unmounted), and a later mount reads it", () => {
    const store = createExitReceiptStore();
    store.accept(receiptResponse({ message: "arrived while elsewhere" }));
    const late = vi.fn();
    store.subscribe(late);
    expect(store.getSnapshot()?.response.message).toBe("arrived while elsewhere");
  });

  it("two stores are independent: there is no shared module state", () => {
    const a = createExitReceiptStore();
    const b = createExitReceiptStore();
    a.accept(receiptResponse());
    expect(b.getSnapshot()).toBeNull();
  });

  it("the scrolled marker only moves forward", () => {
    const store = createExitReceiptStore();
    store.markScrolled(3);
    store.markScrolled(2);
    expect(store.getScrolledSeq()).toBe(3);
  });
});

describe("scroll once per receipt across page instances (風控 FE-3)", () => {
  /** What a freshly mounted page does at mount: scroll iff the receipt was never shown. */
  function mountPage(store: ReturnType<typeof createExitReceiptStore>): boolean {
    const seq = store.getSnapshot()?.seq;
    if (!shouldScrollForReceipt(seq, store.getScrolledSeq())) return false;
    store.markScrolled(seq ?? 0);
    return true;
  }

  it("a receipt shown by one page instance is not scrolled to again when the page is mounted again", () => {
    const store = createExitReceiptStore();
    store.accept(receiptResponse());
    expect(mountPage(store)).toBe(true); // shown, scrolled
    expect(mountPage(store)).toBe(false); // navigate away and back: same receipt
    expect(mountPage(store)).toBe(false);
  });

  it("a receipt that arrived while the page was not mounted is scrolled to once on return", () => {
    const store = createExitReceiptStore();
    store.accept(receiptResponse());
    mountPage(store); // first receipt shown
    store.accept(receiptResponse({ message: "arrived elsewhere" })); // nobody mounted
    expect(mountPage(store)).toBe(true);
    expect(mountPage(store)).toBe(false);
  });

  it("a mount with no receipt never scrolls", () => {
    expect(mountPage(createExitReceiptStore())).toBe(false);
  });
});

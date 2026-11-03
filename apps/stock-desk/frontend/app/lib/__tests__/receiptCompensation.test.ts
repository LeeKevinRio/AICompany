import { describe, expect, it } from "vitest";
import {
  COMPENSATION_MAX_STABLE_WAIT_FRAMES,
  createReceiptCompensation,
  isScrollKey,
  receiptCompensationDelta,
} from "../receiptCompensation";
import type { CompensationMeasure } from "../receiptCompensation";

/** PRD AC-68(h) / spec r3.5a §4.2, V-47: truth table of the compensation conditions. */
describe("receiptCompensationDelta (truth table: obstruction x user scroll x quota x bar)", () => {
  const base = { bannerTop: 100, barBottom: 127, userScrolled: false, quotaUsed: false };

  it("obstructed, no manual scroll, quota left: scroll up to barBottom + 16", () => {
    expect(receiptCompensationDelta(base)).toBe(100 - (127 + 16)); // -43
  });

  it("qa-e2e C group: bar 277px, banner top 160 -> -133 puts the gap at 16", () => {
    expect(receiptCompensationDelta({ ...base, bannerTop: 160, barBottom: 277 })).toBe(-133);
  });

  it("hysteresis: triggers strictly below barBottom + 12, targets barBottom + 16", () => {
    expect(receiptCompensationDelta({ ...base, bannerTop: 127 + 11 })).toBe(127 + 11 - 143);
    expect(receiptCompensationDelta({ ...base, bannerTop: 127 + 12 })).toBe(0);
    expect(receiptCompensationDelta({ ...base, bannerTop: 127 + 15 })).toBe(0); // 12..16: no scroll
  });

  it("not obstructed: no compensation", () => {
    expect(receiptCompensationDelta({ ...base, bannerTop: 250 })).toBe(0);
  });

  it("user already scrolled by hand: no compensation even when covered", () => {
    expect(receiptCompensationDelta({ ...base, userScrolled: true })).toBe(0);
  });

  it("quota used: no compensation even when covered", () => {
    expect(receiptCompensationDelta({ ...base, quotaUsed: true })).toBe(0);
  });

  it("status bar unmounted (refetch failed): never scrolls", () => {
    expect(receiptCompensationDelta({ ...base, barBottom: null, bannerTop: 0 })).toBe(0);
  });

  it("exhaustive: only (obstructed, !userScrolled, !quotaUsed, bar) scrolls", () => {
    for (const obstructed of [true, false])
      for (const userScrolled of [true, false])
        for (const quotaUsed of [true, false])
          for (const hasBar of [true, false]) {
            const delta = receiptCompensationDelta({
              bannerTop: obstructed ? 100 : 300,
              barBottom: hasBar ? 127 : null,
              userScrolled,
              quotaUsed,
            });
            const expected = obstructed && !userScrolled && !quotaUsed && hasBar;
            expect(delta !== 0, JSON.stringify({ obstructed, userScrolled, quotaUsed, hasBar })).toBe(expected);
          }
  });
});

describe("isScrollKey", () => {
  it("covers the keys the spec lists and nothing else", () => {
    for (const k of ["PageUp", "PageDown", "Home", "End", " ", "ArrowUp", "ArrowDown"]) {
      expect(isScrollKey(k), k).toBe(true);
    }
    for (const k of ["Enter", "Tab", "Escape", "a"]) expect(isScrollKey(k), k).toBe(false);
  });
});

/** A fake page: a banner and a bar whose measurements the test sets, and a frame queue. */
function harness(initial: CompensationMeasure | null) {
  let measure = initial;
  const scrolls: number[] = [];
  let nextId = 1;
  const queue = new Map<number, () => void>();
  const controller = createReceiptCompensation({
    measure: () => measure,
    scrollBy: (d) => {
      scrolls.push(d);
      if (measure !== null) measure = { ...measure, bannerTop: measure.bannerTop - d };
    },
    requestFrame: (cb) => {
      queue.set(nextId, cb);
      return nextId++;
    },
    cancelFrame: (id) => {
      queue.delete(id);
    },
  });
  const flushFrames = (n = 10) => {
    for (let i = 0; i < n && queue.size > 0; i++) {
      const [id, cb] = [...queue.entries()][0]!;
      queue.delete(id);
      cb();
    }
  };
  return {
    controller,
    scrolls,
    set: (m: CompensationMeasure | null) => {
      measure = m;
    },
    flushFrames,
    pendingFrames: () => queue.size,
  };
}

const covered: CompensationMeasure = { bannerTop: 160, barBottom: 277, barHeight: 277 };

describe("compensation controller (V-47 a-d, FR-3 iv, AC-33)", () => {
  it("(a) obstructed at the sync point: exactly one compensation, to barBottom + 16", () => {
    const h = harness(covered);
    h.controller.arm(1, true); // refetch already in flight when the first scroll ran
    h.controller.fetchingChanged(false);
    h.flushFrames();
    expect(h.scrolls).toEqual([160 - (277 + 16)]);
  });

  it("waits for the refetch to end: nothing before it, nothing if it never ends", () => {
    const h = harness(covered);
    h.controller.arm(1, false);
    h.flushFrames();
    expect(h.scrolls).toEqual([]);
    h.controller.fetchingChanged(false); // idle without ever having fetched: not a sync point
    h.flushFrames();
    expect(h.scrolls).toEqual([]);
    h.controller.fetchingChanged(true);
    h.controller.fetchingChanged(false);
    h.flushFrames();
    expect(h.scrolls).toHaveLength(1);
  });

  it("(b) not obstructed: scrollY untouched", () => {
    const h = harness({ bannerTop: 300, barBottom: 127, barHeight: 127 });
    h.controller.arm(1, true);
    h.controller.fetchingChanged(false);
    h.flushFrames();
    expect(h.scrolls).toEqual([]);
  });

  it("(c) the user scrolled by hand after the first scroll: no compensation", () => {
    const h = harness(covered);
    h.controller.arm(1, true);
    h.controller.userInput();
    h.controller.fetchingChanged(false);
    h.flushFrames();
    expect(h.scrolls).toEqual([]);
  });

  it("input before arm does not count (it is not 'after the first scroll')", () => {
    const h = harness(covered);
    h.controller.userInput();
    h.controller.arm(1, true);
    h.controller.fetchingChanged(false);
    h.flushFrames();
    expect(h.scrolls).toHaveLength(1);
  });

  it("(d) quota: after one compensation, later growth and later refetches never scroll again", () => {
    const h = harness(covered);
    h.controller.arm(1, true);
    h.controller.fetchingChanged(false);
    h.flushFrames();
    expect(h.scrolls).toHaveLength(1);
    h.set({ bannerTop: 16, barBottom: 400, barHeight: 400 }); // bar grows again
    h.controller.fetchingChanged(true);
    h.controller.fetchingChanged(false);
    h.flushFrames();
    expect(h.scrolls).toHaveLength(1);
  });

  it("(d) a second receipt has its own quota", () => {
    const h = harness(covered);
    h.controller.arm(1, true);
    h.controller.fetchingChanged(false);
    h.flushFrames();
    h.set(covered);
    h.controller.arm(2, true);
    h.controller.fetchingChanged(false);
    h.flushFrames();
    expect(h.scrolls).toHaveLength(2);
  });

  it("arm is idempotent for the same receipt (StrictMode re-run keeps the state)", () => {
    const h = harness(covered);
    h.controller.arm(1, true);
    h.controller.userInput();
    h.controller.arm(1, true);
    h.controller.fetchingChanged(false);
    h.flushFrames();
    expect(h.scrolls).toEqual([]);
  });

  it("status bar unmounted at the sync point (refetch failed): no extra scroll", () => {
    const h = harness({ bannerTop: 5, barBottom: null, barHeight: null });
    h.controller.arm(1, true);
    h.controller.fetchingChanged(false);
    h.flushFrames();
    expect(h.scrolls).toEqual([]);
  });

  it("judges only after the bar height is equal for two consecutive frames", () => {
    const h = harness({ bannerTop: 160, barBottom: 87, barHeight: 87 });
    h.controller.arm(1, true);
    h.controller.fetchingChanged(false);
    h.flushFrames(1); // frame 1: 87
    h.set({ bannerTop: 160, barBottom: 277, barHeight: 277 });
    h.flushFrames(1); // frame 2: 277 != 87 -> keep waiting
    expect(h.scrolls).toEqual([]);
    h.flushFrames(1); // frame 3: 277 == 277 -> judge with the settled height
    expect(h.scrolls).toEqual([160 - 293]);
  });

  it("gives up waiting after the frame cap and still judges once", () => {
    const h = harness(covered);
    let height = 100;
    h.controller.arm(1, true);
    h.controller.fetchingChanged(false);
    for (let i = 0; i < COMPENSATION_MAX_STABLE_WAIT_FRAMES + 2; i++) {
      height += 1; // never stable
      h.set({ bannerTop: 160, barBottom: 277, barHeight: height });
      h.flushFrames(1);
    }
    expect(h.scrolls).toHaveLength(1);
  });

  it("dispose cancels a pending judgement", () => {
    const h = harness(covered);
    h.controller.arm(1, true);
    h.controller.fetchingChanged(false);
    h.controller.dispose();
    expect(h.pendingFrames()).toBe(0);
    h.flushFrames();
    expect(h.scrolls).toEqual([]);
  });
});

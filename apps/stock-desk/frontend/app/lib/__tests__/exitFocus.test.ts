/** FE-T11: the focus hand-off truth table (FE-C20). */

import { describe, expect, it } from "vitest";
import { consumeTriggerMount, recordTriggerUnmount, shouldHandOffFocus } from "../exitFocus";

describe("shouldHandOffFocus", () => {
  it("hands off only when all three conditions hold", () => {
    for (const dialogOpen of [false, true]) {
      for (const lostFocusOnUnmount of [false, true]) {
        for (const activeIsBodyOrNull of [false, true]) {
          const expected = !dialogOpen && lostFocusOnUnmount && activeIsBodyOrNull;
          expect(shouldHandOffFocus({ dialogOpen, lostFocusOnUnmount, activeIsBodyOrNull })).toBe(
            expected,
          );
        }
      }
    }
  });

  it("never takes focus from an element the user chose (focus already elsewhere)", () => {
    expect(
      shouldHandOffFocus({ dialogOpen: false, lostFocusOnUnmount: true, activeIsBodyOrNull: false }),
    ).toBe(false);
  });

  it("does nothing when the old trigger did not hold focus", () => {
    expect(
      shouldHandOffFocus({ dialogOpen: false, lostFocusOnUnmount: false, activeIsBodyOrNull: true }),
    ).toBe(false);
  });

  it("never interferes while the dialog is open", () => {
    expect(
      shouldHandOffFocus({ dialogOpen: true, lostFocusOnUnmount: true, activeIsBodyOrNull: true }),
    ).toBe(false);
  });
});

describe("the focus-lost flag (風控 2026-11-01 FE-8)", () => {
  const idle = { dialogOpen: false, activeIsBodyOrNull: true };

  it("hands off once for the swap that follows an unmount that held focus, then the flag is gone", () => {
    const cell = { current: false };
    recordTriggerUnmount(cell, true);
    expect(consumeTriggerMount(cell, idle)).toBe(true);
    expect(cell.current).toBe(false);
    // A later, unrelated mount does not fire.
    expect(consumeTriggerMount(cell, idle)).toBe(false);
  });

  it("consumes the flag even when it does not hand off, so it cannot linger and fire on a later mount", () => {
    const cell = { current: false };
    recordTriggerUnmount(cell, true);
    expect(consumeTriggerMount(cell, { dialogOpen: true, activeIsBodyOrNull: true })).toBe(false);
    expect(cell.current).toBe(false);
    expect(consumeTriggerMount(cell, idle)).toBe(false);

    recordTriggerUnmount(cell, true);
    expect(consumeTriggerMount(cell, { dialogOpen: false, activeIsBodyOrNull: false })).toBe(false);
    expect(consumeTriggerMount(cell, idle)).toBe(false);
  });

  it("every unmount overwrites: a stale true cannot survive a removal that held no focus", () => {
    const cell = { current: false };
    recordTriggerUnmount(cell, true);
    recordTriggerUnmount(cell, false); // a later removal, focus elsewhere
    expect(cell.current).toBe(false);
    expect(consumeTriggerMount(cell, idle)).toBe(false);
  });

  it("an unmount without a following mount leaves a flag that the very next mount consumes, once", () => {
    const cell = { current: false };
    recordTriggerUnmount(cell, true);
    expect(consumeTriggerMount(cell, idle)).toBe(true);
    expect(consumeTriggerMount(cell, idle)).toBe(false);
  });

  it("the very first mount of a page has nothing to hand off", () => {
    expect(consumeTriggerMount({ current: false }, idle)).toBe(false);
  });
});

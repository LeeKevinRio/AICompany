/** FE-T11: the focus hand-off truth table (FE-C20). */

import { describe, expect, it } from "vitest";
import { shouldHandOffFocus } from "../exitFocus";

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

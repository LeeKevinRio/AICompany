/** V-41 (視覺規範): the scroll amount that brings the failure panel's label into view. */

import { describe, expect, it } from "vitest";
import { FAILURE_REVEAL_MARGIN_PX, failureRevealDelta } from "../exitFailureReveal";

describe("failureRevealDelta", () => {
  const band = { containerTop: 100, containerBottom: 700 };

  it("does nothing when the label is already fully visible", () => {
    expect(failureRevealDelta({ ...band, labelTop: 300, labelBottom: 320 })).toBe(0);
    expect(failureRevealDelta({ ...band, labelTop: 100, labelBottom: 120 })).toBe(0);
    expect(failureRevealDelta({ ...band, labelTop: 680, labelBottom: 700 })).toBe(0);
  });

  it("scrolls down to bring a label below the band to its top edge, with the margin", () => {
    expect(failureRevealDelta({ ...band, labelTop: 900, labelBottom: 920 })).toBe(
      900 - 100 - FAILURE_REVEAL_MARGIN_PX,
    );
  });

  it("scrolls down when the label is only partly below the band (it must be fully visible)", () => {
    expect(failureRevealDelta({ ...band, labelTop: 690, labelBottom: 710 })).toBe(
      690 - 100 - FAILURE_REVEAL_MARGIN_PX,
    );
  });

  it("scrolls up for a label above the band", () => {
    expect(failureRevealDelta({ ...band, labelTop: 40, labelBottom: 60 })).toBe(
      40 - 100 - FAILURE_REVEAL_MARGIN_PX,
    );
  });
});

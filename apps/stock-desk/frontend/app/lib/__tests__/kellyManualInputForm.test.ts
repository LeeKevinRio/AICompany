import { describe, expect, it } from "vitest";
import { isSubmittableManualInput } from "../../settings/KellyManualInputForm";

/**
 * qa 補審 (順手 suggestion): `isSubmittableManualInput` is the light
 * client-side pre-check `KellyManualInputForm.tsx`'s `handleSubmit` uses to
 * skip a request that cannot possibly succeed (`Number("abc")` is `NaN`) —
 * not a clamp, not a correction, just declining a pointless round trip. See
 * the function's own doc comment for why `type="number"` was not used
 * instead (this app's existing "the browser must not judge a value"
 * convention).
 */
describe("isSubmittableManualInput", () => {
  it("accepts two ordinary decimal strings", () => {
    expect(isSubmittableManualInput("0.55", "1.5")).toBe(true);
  });

  it("accepts a negative payoff-ratio-shaped string too — this predicate does not judge range, only shape", () => {
    // Out-of-range values are still submitted and refused server-side with
    // the approved Chinese message (約束 6: refused, not clamped); this
    // predicate exists only to skip garbage the backend cannot parse at all.
    expect(isSubmittableManualInput("0.5", "-3")).toBe(true);
  });

  it("rejects non-numeric text in either field", () => {
    expect(isSubmittableManualInput("abc", "1.5")).toBe(false);
    expect(isSubmittableManualInput("0.5", "abc")).toBe(false);
  });

  it("rejects nan/Infinity-shaped strings (Number() parses the JS literal words)", () => {
    expect(isSubmittableManualInput("NaN", "1.5")).toBe(false);
    expect(isSubmittableManualInput("0.5", "Infinity")).toBe(false);
  });
});

// 條件 109 (第十四輪) withheld the delete control from this file entirely
// until 條件 110's disclosure sentence existed; 第十五輪 CONFIRMED it and
// required a `role="dialog"` component. The control now lives in
// `KellyDeleteDialog.tsx` (a sibling `KellyDisclosuresPanel.tsx` renders
// beside this form, not inside it — see this form's own doc comment) —
// `app/lib/__tests__/kellyDeleteDialog.test.ts` carries its coverage.

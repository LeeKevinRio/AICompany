/**
 * 條件 109 (第十四輪, `work/reviews/2026-08-19-C5-Kelly-文案批審.md`): the
 * delete control (button + confirmation) is withheld from
 * `KellyManualInputForm.tsx` until 條件 110's disclosure sentence is drafted
 * by creative and approved by risk-compliance. This placeholder documents
 * what re-enabling it must satisfy and stays `.skip` until that sentence
 * exists — there is nothing to assert yet, and a passing-vacuously test
 * (e.g. "no delete button renders") would silently stop meaning anything the
 * moment someone adds one back without reading this file.
 */

import { describe, it } from "vitest";

describe.skip("KellyManualInputForm — delete control (blocked on 條件 110)", () => {
  it("renders a delete control gated on `current !== null`, confirms via the 條件 110-approved sentence (subject named, 'cannot be recovered' scoped to what is actually lost, the kept attempt-log counts stated rather than silently dropped), and its confirm handler is the sole call site of `deleteKellyInput`/`useDeleteKellyInput`'s `mutate`", () => {
    // Intentionally empty: re-enable this component only once 條件 110's
    // sentence is CONFIRMED, wire it through `KellyOverwriteNoticeView`-style
    // backend-supplied copy (never a frontend-authored string, per this
    // whole surface's zero-literal rule), and replace this body with real
    // assertions before removing `.skip`.
  });
});

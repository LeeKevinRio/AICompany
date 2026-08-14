/**
 * S6 fix (work/reviews/risk-final-review.md 列管項:「禁用詞清單前後端鏡像漂
 * 移」): `FRONTEND_FORBIDDEN_TERMS` (this app) and the backend's
 * `FORBIDDEN_TERMS`/`FORBIDDEN_ADVICE_TERMS`
 * (`apps/stock-desk/backend/tests/test_advice_wording.py`) had drifted apart
 * — each hand-typed its own §1.3 subset with no automated check tying the
 * two together. Both now read the same `apps/stock-desk/shared/forbidden-
 * terms.json`: this test reads it directly (the way `componentWordingScan
 * .test.ts` already reads raw source text, rather than importing across the
 * package boundary) and asserts every term is present in the frontend's own
 * list, so a future edit to either side that drops a term fails here instead
 * of shipping a silent gap.
 */

import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { describe, expect, it } from "vitest";
import { FRONTEND_FORBIDDEN_TERMS } from "../adviceWording";

const SHARED_TERMS_PATH = fileURLToPath(
  new URL("../../../../shared/forbidden-terms.json", import.meta.url),
);

interface SharedForbiddenTerms {
  guarantee: string[];
  price_target: string[];
}

function loadSharedTerms(): SharedForbiddenTerms {
  const payload = JSON.parse(readFileSync(SHARED_TERMS_PATH, "utf-8")) as SharedForbiddenTerms;
  return payload;
}

describe("FRONTEND_FORBIDDEN_TERMS — synced with the backend's shared/forbidden-terms.json", () => {
  const shared = loadSharedTerms();
  const allSharedTerms = [...shared.guarantee, ...shared.price_target];

  it("shared/forbidden-terms.json is not empty (guards against a silently broken read)", () => {
    expect(allSharedTerms.length).toBeGreaterThan(0);
  });

  for (const term of allSharedTerms) {
    it(`includes the shared term ${JSON.stringify(term)}`, () => {
      expect(FRONTEND_FORBIDDEN_TERMS).toContain(term);
    });
  }
});

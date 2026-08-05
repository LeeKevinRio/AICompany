/**
 * Shared scanning primitives for the §1.3 banned-term guard tests
 * (`adviceWording.test.ts` and `componentWordingScan.test.ts`). Not itself a
 * test file (no `.test.ts` suffix, so `vitest.config.ts`'s `include` glob
 * skips it) — just the two checks both scans need, kept in one place so a
 * future third scan target does not have to reinvent either.
 */

import { expect } from "vitest";

/** Fails with a clear message identifying which banned term leaked through. */
export function assertNoForbiddenTerms(text: string, terms: readonly string[], label: string): void {
  for (const term of terms) {
    expect(text, `${label}: contains banned term ${JSON.stringify(term)}`).not.toContain(term);
  }
}

/**
 * §5.1: "即時"/real-time may only ever appear as part of a denial ("非即時"
 * — asserting the product is *not* real-time). Any occurrence not
 * immediately preceded by "非" is a capability claim and must fail. Returns
 * the offending contexts (rather than throwing directly) so a caller can
 * assert on an empty array and get every violation in one failure message,
 * not just the first.
 */
export function findBareRealtimeClaims(text: string): string[] {
  const violations: string[] = [];
  const pattern = /即時/g;
  let match: RegExpExecArray | null;
  while ((match = pattern.exec(text)) !== null) {
    const precedingChar = text.slice(Math.max(0, match.index - 1), match.index);
    if (precedingChar !== "非") {
      violations.push(text.slice(Math.max(0, match.index - 10), match.index + 12));
    }
  }
  return violations;
}

/**
 * Shared scanning primitives for the §1.3 banned-term guard tests
 * (`adviceWording.test.ts` and `componentWordingScan.test.ts`). Not itself a
 * test file (no `.test.ts` suffix, so `vitest.config.ts`'s `include` glob
 * skips it) — just the two checks both scans need, kept in one place so a
 * future third scan target does not have to reinvent either.
 */

import { expect } from "vitest";

/**
 * Fails with a clear message identifying which banned term leaked through.
 *
 * D3② (risk-fix-review.md N2 列管): the scan is a verbatim substring match,
 * which cannot tell a *prohibited claim* ("勝率 80%，穩賺" — probability
 * laundering) from an *acknowledged-limitation / historical-statistic
 * context* ("勝率" as a backtest's realized win-rate row label, or a
 * sentence denying the product has one). `allowedContexts` is the narrow
 * escape hatch for the second kind: each entry is an exact, longer source
 * string that contains a banned term legitimately; every occurrence of that
 * exact context is masked out before scanning, so the term stays banned
 * everywhere else in the same text — including right next to a whitelisted
 * occurrence. Guard rails:
 *
 * - an entry that contains no banned term at all is rejected loudly: it
 *   would be dead config today and a silent pre-approved hole for whatever
 *   term is added to the list tomorrow;
 * - an entry that does not occur in the text is rejected loudly too, so a
 *   whitelist cannot outlive a reworded source and rot into masking a
 *   future, different occurrence.
 *
 * Keep entries as long as practical (a whole label/sentence, not the bare
 * term): the wider the context string, the less it can accidentally cover.
 */
export function assertNoForbiddenTerms(
  text: string,
  terms: readonly string[],
  label: string,
  allowedContexts: readonly string[] = [],
): void {
  let scanned = text;
  for (const context of allowedContexts) {
    expect(
      terms.some((term) => context.includes(term)),
      `${label}: allowed context ${JSON.stringify(context)} contains no banned term — remove the dead whitelist entry`,
    ).toBe(true);
    expect(
      scanned.includes(context),
      `${label}: allowed context ${JSON.stringify(context)} not found in the scanned text — the source changed, update or remove the whitelist entry`,
    ).toBe(true);
    // Same-length padding of a character no banned term contains keeps every
    // other index untouched, and can never *create* a term across a mask
    // boundary (unlike a space, which "buy point"/"sell point" do contain).
    scanned = scanned.split(context).join("\u0000".repeat(context.length));
  }
  for (const term of terms) {
    expect(scanned, `${label}: contains banned term ${JSON.stringify(term)}`).not.toContain(term);
  }
}

//: Any Han character — the block a zero-literal scan (`kellyDisclosuresPanel
//: .test.ts`, `kellyImportDialog.test.ts`) tests for *complete absence* of,
//: rather than membership in a banned-term list.
const HAN_CHARACTER = /[一-鿿]/;

/**
 * Strips `//` line comments and `/* … *‍/` block comments from `source` before
 * a zero-Chinese-literal scan, so a doc comment citing a review condition
 * number (which is legitimate — this whole codebase's comments are English
 * prose that names Chinese review terms in backticks/quotes) does not fail a
 * scan whose actual target is *rendered* text. Deliberately simple (no string-
 * literal-aware tokenizer): `//` and `/* … *‍/` inside a JS/TS string literal
 * are vanishingly rare in this codebase's style (no `"http://"` URLs appear in
 * the two files this is written for) and 條件 105/97-class rules would rather
 * a caller re-check a false negative by hand than silently widen what counts
 * as "a comment".
 */
export function stripComments(source: string): string {
  return source.replace(/\/\/.*$/gm, "").replace(/\/\*[\s\S]*?\*\//g, "");
}

/**
 * Every Han character found in `source` once comments are stripped —
 * `stripComments` first, so a caller gets the *rendered-text* violations,
 * not the doc comments that legitimately quote a Chinese review term.
 */
export function chineseLiteralsOutsideComments(source: string): string[] {
  const stripped = stripComments(source);
  const matches = stripped.match(new RegExp(HAN_CHARACTER, "g"));
  return matches ?? [];
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

/**
 * Direct tests for the shared scanning primitives (`wordingScanHelpers.ts`),
 * added with D3②'s context-whitelist mechanism (risk-fix-review.md N2 列管:
 * a verbatim scan cannot tell a prohibited claim from an acknowledged
 * historical-statistic / limitation context, so it needed a narrow, loud,
 * self-policing escape hatch rather than ad-hoc file exclusions). The two
 * consumer suites (`adviceWording.test.ts`, `componentWordingScan.test.ts`)
 * only ever exercise the passing path on real sources; the failure paths —
 * the whole point of a guard — are pinned here on synthetic inputs.
 */

import { describe, expect, it } from "vitest";
import { assertNoForbiddenTerms, findBareRealtimeClaims } from "./wordingScanHelpers";

const TERMS = ["勝率", "保證"] as const;

describe("assertNoForbiddenTerms — verbatim scan (existing behaviour)", () => {
  it("passes clean text", () => {
    expect(() => assertNoForbiddenTerms("回測報告的統計欄位。", TERMS, "t")).not.toThrow();
  });

  it("fails on a banned term, naming it", () => {
    expect(() => assertNoForbiddenTerms("本策略勝率極高。", TERMS, "t")).toThrow(/勝率/);
  });
});

describe("assertNoForbiddenTerms — allowedContexts (D3② 語境白名單)", () => {
  it("permits a banned term inside an exactly-matching allowed context", () => {
    expect(() =>
      assertNoForbiddenTerms('{ label: "勝率", render: winRate }', TERMS, "t", ['label: "勝率"']),
    ).not.toThrow();
  });

  it("still fails the same term outside the whitelisted context, even in the same text", () => {
    expect(() =>
      assertNoForbiddenTerms(
        '{ label: "勝率", render: winRate } 本策略勝率極高。',
        TERMS,
        "t",
        ['label: "勝率"'],
      ),
    ).toThrow(/勝率/);
  });

  it("masks every occurrence of the context, not only the first", () => {
    expect(() =>
      assertNoForbiddenTerms(
        '{ label: "勝率" } { label: "勝率" }',
        TERMS,
        "t",
        ['label: "勝率"'],
      ),
    ).not.toThrow();
  });

  it("leaves other banned terms fully enforced beside a whitelisted one", () => {
    expect(() =>
      assertNoForbiddenTerms('{ label: "勝率" } 保證獲利', TERMS, "t", ['label: "勝率"']),
    ).toThrow(/保證/);
  });

  it("rejects a dead whitelist entry that contains no banned term", () => {
    expect(() =>
      assertNoForbiddenTerms("乾淨文字。", TERMS, "t", ["完全無害的語境"]),
    ).toThrow(/contains no banned term/);
  });

  it("rejects a whitelist entry that no longer occurs in the scanned text", () => {
    expect(() =>
      assertNoForbiddenTerms("乾淨文字。", TERMS, "t", ['label: "勝率"']),
    ).toThrow(/not found in the scanned text/);
  });
});

/**
 * D8⑤ (qa-reviewer low, work/reviews/2026-08-16-品質債清償批-覆核.md): when one
 * whitelist entry is a substring of another, masking is order-sensitive.
 * Masking the substring first also nulls it out *inside* the superstring's
 * occurrence, so the superstring's own must-still-occur guard then fires —
 * a false "the source changed" failure on an unchanged source. The failure
 * mode is loud (a test failure to investigate, never a silent pre-approved
 * hole), which is why this stays pinned behaviour rather than being "fixed":
 * the resolution is to order the superstring before its substring. No real
 * scan target trips this today (each file has at most one whitelist entry);
 * these synthetic cases pin the boundary before a second entry ever lands.
 */
describe("assertNoForbiddenTerms — overlapping allowedContexts (D8⑤ 順序陷阱)", () => {
  // "歷史勝率" is a substring of "回測的歷史勝率統計"; the text carries one
  // occurrence of each, plus no other banned term.
  const TEXT = '表格標題為「回測的歷史勝率統計」；欄位 label 為「歷史勝率」。';
  const SUPERSTRING = "回測的歷史勝率統計";
  const SUBSTRING = "歷史勝率";

  it("passes when the superstring entry is listed before its substring entry", () => {
    expect(() =>
      assertNoForbiddenTerms(TEXT, TERMS, "t", [SUPERSTRING, SUBSTRING]),
    ).not.toThrow();
  });

  it("substring-first fails loudly as a stale entry, never as a silent hole", () => {
    // Masking "歷史勝率" first destroys the superstring's only occurrence, so
    // its own occurrence guard reports it stale even though the source text is
    // unchanged — the documented trap. Loud and investigable by design: the
    // guard must never respond to overlap by quietly widening what it masks.
    expect(() =>
      assertNoForbiddenTerms(TEXT, TERMS, "t", [SUBSTRING, SUPERSTRING]),
    ).toThrow(/not found in the scanned text/);
  });
});

describe("findBareRealtimeClaims — unchanged by the whitelist mechanism", () => {
  it("accepts the denial form and flags the bare claim", () => {
    expect(findBareRealtimeClaims("本產品非即時報價系統。")).toEqual([]);
    expect(findBareRealtimeClaims("提供即時報價。")).toHaveLength(1);
  });
});

/**
 * Risk remediation batch (CEO ruling #59; risk-compliance final wording
 * `work/reviews/2026-10-26-風控五項整改字面逐字審-風控.md`).
 *
 * Pins every verbatim literal of the batch against a second, hand-typed copy
 * (a test-side duplicate on purpose: a drift in the constants file fails here)
 * and checks the C-1 guardrails: every new sentence passes the existing banned
 * term scan and the bare-"即時" scan without touching either list.
 *
 * Test kind per block: 字面更新 = an old literal pin replaced by the new literal;
 * 行為新增 = a new assertion that did not exist before.
 */

import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { describe, expect, it } from "vitest";
import { FRONTEND_FORBIDDEN_TERMS } from "../adviceWording";
import { UNVALIDATED_EXPLANATION, UNVALIDATED_LABEL } from "../riskRemediationWording";
import { assertNoForbiddenTerms, findBareRealtimeClaims, stripComments } from "./wordingScanHelpers";

const read = (rel: string) => readFileSync(fileURLToPath(new URL(rel, import.meta.url)), "utf8");

/** Sentences that may never appear in any new literal (review condition 2: no "not advice" denial). */
const DENIAL_PHRASES = ["非投資建議", "不是建議", "僅供參考", "研究與教育用途", "不構成投資建議"];

function assertCleanLiteral(label: string, text: string): void {
  assertNoForbiddenTerms(text, FRONTEND_FORBIDDEN_TERMS, label);
  expect(findBareRealtimeClaims(text), label).toEqual([]);
  for (const phrase of DENIAL_PHRASES) expect(text, `${label} 含否認建議性質的句子`).not.toContain(phrase);
}

describe("1-L／1-X 逐字（字面更新：取代原「信心 低/中/高」chip）", () => {
  it("字面逐字", () => {
    expect(UNVALIDATED_LABEL).toBe("未經歷史驗證");
    expect(UNVALIDATED_EXPLANATION).toBe("這個結論所依據的規則、門檻與權重，都還沒用歷史資料驗證過。");
  });

  it("通過禁用詞與裸即時掃描（C-1），且不含否認建議性質的句子", () => {
    assertCleanLiteral("UNVALIDATED_LABEL", UNVALIDATED_LABEL);
    assertCleanLiteral("UNVALIDATED_EXPLANATION", UNVALIDATED_EXPLANATION);
  });
});

describe("信心 chip 不得回流（行為新增；保護 1-L 的失效條件 T2：信心重新上畫面須同批改寫字面）", () => {
  const SURFACES = [
    "../../position/[symbol]/DecisionCard.tsx",
    "../../position/[symbol]/OperationSummaryPanel.tsx",
  ] as const;

  for (const rel of SURFACES) {
    it(`${rel}：程式碼（不含註解）不引用 CONFIDENCE_PREFIX、summaryConfidenceLabel，也不渲染 confidenceMeaning`, () => {
      const code = stripComments(read(rel));
      expect(code).not.toContain("CONFIDENCE_PREFIX");
      expect(code).not.toContain("summaryConfidenceLabel");
      expect(code).not.toContain("confidenceMeaning");
      expect(code).not.toContain("showConfidence");
    });

    it(`${rel}：渲染 <UnvalidatedNotice />`, () => {
      const code = stripComments(read(rel));
      expect(code).toContain("<UnvalidatedNotice />");
    });
  }

  it("兩個連動 xref 句不再提到「信心等級」（連動 xref 1、2；保護的字面：ENTRY_E2_XREF、ADVICE_CARD_XREF_TO_SUMMARY）", () => {
    const entry = read("../entryObservationWording.ts");
    const tagline = read("../sectionTaglines.ts");
    expect(stripComments(entry)).not.toContain("信心等級");
    expect(stripComments(tagline)).not.toContain("信心等級");
  });
});

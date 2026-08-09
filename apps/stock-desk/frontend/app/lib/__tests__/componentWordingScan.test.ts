/**
 * qa-reviewer Major follow-up on the FR-C1 review: the wording guard
 * (`adviceWording.test.ts`) only scanned `adviceWording.ts`'s exported
 * strings, which does not fully satisfy §1.3's required obligation that
 * "前端文案模板亦須被掃到" — any Traditional-Chinese literal written
 * directly into a component's JSX (a hard-coded label, an inline error
 * message, a `placeholder`, …) would ship unscanned. This suite reads the
 * *raw source text* of every component in the operation-summary surface
 * that can render user-facing copy and scans it against the same
 * `FRONTEND_FORBIDDEN_TERMS` list.
 *
 * Source-text (not rendered-output) scanning is deliberate here, unlike
 * `adviceWording.test.ts`: these three files are consumers, not the wording
 * module itself, so they have no legitimate reason to *name* a banned term
 * in a comment the way `adviceWording.ts`'s own doc comments do (explaining
 * what NOT to write). If that ever changes, narrow the scan the same way
 * `adviceWording.test.ts` does (scan rendered output / an explicit slice)
 * rather than silently widening this list's exceptions.
 */

import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { describe, expect, it } from "vitest";
import { FRONTEND_FORBIDDEN_TERMS } from "../adviceWording";
import { assertNoForbiddenTerms, findBareRealtimeClaims } from "./wordingScanHelpers";

const SCANNED_FILES = [
  "../../position/[symbol]/OperationSummaryPanel.tsx",
  "../../position/[symbol]/page.tsx",
  "../../components/NavBar.tsx",
  // FR-9's settings surface: the net-worth field's label, its hints and the
  // risk-widening confirmation are all hard-coded Traditional Chinese in JSX,
  // which is exactly the class of copy this scan exists to reach.
  "../../settings/NetWorthSection.tsx",
  "../../settings/SettingsForm.tsx",
  // R5 fix (risk-final-review.md): the advice-card surface and its wording
  // helpers had no coverage at all — exactly the gap that let R1/R2's
  // unattributed, non-whitelisted labels ship unscanned.
  "../../position/[symbol]/AdviceCardView.tsx",
  "../format.ts",
  "../../components/RiskGauge.tsx",
  "../../position/[symbol]/LimitsCheckList.tsx",
  "../operationSummary.ts",
  // 風控快審 2026-08-09：掃描覆蓋是文案核可前提，補上兩個原本未被掃到的
  // 持倉/警示規則表面。
  "../../components/EditPositionModal.tsx",
  "../../settings/AlertRulesSection.tsx",
  // FE-WIRING BLOCKING 退修 2026-08-09（qa-reviewer 建議）：ref 型條件的
  // 唯讀提示句是這批新加的硬編碼 JSX 文案，兩個相關檔案原本都未被掃到。
  "../../settings/EditAlertRuleModal.tsx",
  "../../settings/AlertParamFields.tsx",
] as const;

describe("component source scan — §1.3 banned-term coverage on hard-coded JSX text", () => {
  for (const relativePath of SCANNED_FILES) {
    const absolutePath = fileURLToPath(new URL(relativePath, import.meta.url));
    const source = readFileSync(absolutePath, "utf-8");

    it(`${relativePath}: contains none of the §1.3 banned terms`, () => {
      assertNoForbiddenTerms(source, FRONTEND_FORBIDDEN_TERMS, relativePath);
    });

    it(`${relativePath}: every "即時" occurrence is a "非即時" denial, never a bare claim`, () => {
      expect(findBareRealtimeClaims(source)).toEqual([]);
    });
  }
});

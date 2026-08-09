/**
 * §1.3 required test-coverage obligation: "上表須落為單一常數來源，由後端
 * 與前端共用掃描（前端文案模板亦須被掃到）". The backend scan
 * (`apps/stock-desk/backend/tests/test_advice_wording.py`) only reaches
 * Python-side strings; this is the front-end half.
 *
 * Deliberately scans *rendered output* (every exported label and every
 * `build*` template's return value with representative arguments) rather
 * than the module's raw source text: this file's doc comments legitimately
 * *name* several banned phrases as negative examples (e.g. explaining that
 * `CANDIDATE_NOT_SUPPORTIVE_TEXT` must never be softened into "可再觀察"),
 * and a naive source-text scan would flag that explanation as a violation.
 * Scanning what actually reaches a screen is both more precise and what
 * §1.3 asks for ("文案模板").
 *
 * "即時" is deliberately excluded from the plain substring list (a naive
 * `.not.toContain("即時")` would false-positive on `NON_REALTIME_NOTICE`'s
 * required "非即時" denial) — it is instead checked automatically via
 * `findBareRealtimeClaims` (`wordingScanHelpers.ts`), which only fails when
 * "即時" appears *without* an immediately preceding "非" (qa-reviewer
 * BLOCKING/Major follow-up: this was a manual-review `it.todo` before).
 */

import { describe, expect, it } from "vitest";
import { assertNoForbiddenTerms, findBareRealtimeClaims } from "./wordingScanHelpers";
import {
  buildAsOfStatement,
  buildAttributedHeadline,
  buildCandidateCoverageStatement,
  buildCandidateSupportiveComposition,
  buildRulesStatement,
  buildStaleDataProminentNotice,
  CANDIDATE_CONFIDENCE_NOT_COMPARABLE_NOTE,
  CANDIDATE_EVIDENCE_NOTICE,
  CANDIDATE_HEADING_LABEL,
  CANDIDATE_NOT_SUPPORTIVE_TEXT,
  CANDIDATE_QUANTITY_BASIS_NOTE,
  CANDIDATE_SUPPORTIVE_DISCLAIMER,
  FRONTEND_FORBIDDEN_TERMS,
  HELD_ACTION_LABELS,
  NON_REALTIME_NOTICE,
  QUANTITY_RANGE_ABSENCE_TEXT,
  summaryConfidenceLabel,
} from "../adviceWording";
import type { CardAction, Confidence } from "../types";

const HELD_ACTIONS: CardAction[] = ["add", "hold", "reduce", "take_profit", "stop_loss", "insufficient_data"];
const CONFIDENCES: Confidence[] = ["low", "medium", "high"];

/** Every user-facing string this module can ever render, in one flat list. */
const RENDERED_SURFACE: string[] = [
  ...Object.values(HELD_ACTION_LABELS),
  ...HELD_ACTIONS.map(buildAttributedHeadline),
  CANDIDATE_HEADING_LABEL,
  buildCandidateSupportiveComposition(3),
  CANDIDATE_SUPPORTIVE_DISCLAIMER,
  CANDIDATE_NOT_SUPPORTIVE_TEXT,
  CANDIDATE_EVIDENCE_NOTICE,
  CANDIDATE_CONFIDENCE_NOT_COMPARABLE_NOTE,
  buildCandidateCoverageStatement(0.75, 4),
  CANDIDATE_QUANTITY_BASIS_NOTE,
  QUANTITY_RANGE_ABSENCE_TEXT,
  buildRulesStatement("1.0.2"),
  buildAsOfStatement("2026-08-04"),
  buildStaleDataProminentNotice("2026-08-04", 15),
  NON_REALTIME_NOTICE,
  ...CONFIDENCES.map(summaryConfidenceLabel),
];

describe("adviceWording.ts — §1.3 banned-term scan (rendered output)", () => {
  const joined = RENDERED_SURFACE.join("\n");

  it.each(FRONTEND_FORBIDDEN_TERMS)("does not contain the banned term %j", (term) => {
    expect(joined).not.toContain(term);
  });

  it("every '即時' occurrence is part of a '非即時' denial, never a bare capability claim", () => {
    expect(findBareRealtimeClaims(joined)).toEqual([]);
  });

  it("assertNoForbiddenTerms helper agrees with the it.each scan above (belt and suspenders)", () => {
    assertNoForbiddenTerms(joined, FRONTEND_FORBIDDEN_TERMS, "adviceWording.ts rendered surface");
  });
});

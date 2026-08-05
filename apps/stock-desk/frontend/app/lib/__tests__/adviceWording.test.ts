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
 * Known scope limit (documented rather than silently narrowed): "即時" is
 * deliberately excluded from the scanned term list, because this file's
 * only legitimate rendered use of the characters is inside "非即時"
 * (denying real-time capability, which §5.1 requires, not claims it) — see
 * `NON_REALTIME_NOTICE`. A bare `it.todo` records that trade-off instead of
 * a substring rule that would false-positive on the required denial itself.
 */

import { describe, expect, it } from "vitest";
import {
  buildAsOfStatement,
  buildAttributedHeadline,
  buildCandidateCoverageStatement,
  buildCandidateSupportiveComposition,
  buildRulesStatement,
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
  STALE_DATA_PROMINENT_NOTICE,
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
  STALE_DATA_PROMINENT_NOTICE,
  NON_REALTIME_NOTICE,
  ...CONFIDENCES.map(summaryConfidenceLabel),
];

describe("adviceWording.ts — §1.3 banned-term scan (rendered output)", () => {
  const joined = RENDERED_SURFACE.join("\n");

  it.each(FRONTEND_FORBIDDEN_TERMS)("does not contain the banned term %j", (term) => {
    expect(joined).not.toContain(term);
  });

  it.todo(
    "「即時」/real-time capability claims — covered by NON_REALTIME_NOTICE containing only " +
      "negated usage ('非即時報價'); a substring scan for '即時' would false-positive on the " +
      "required denial itself, so this is a documented manual-review item, not an automated one",
  );
});

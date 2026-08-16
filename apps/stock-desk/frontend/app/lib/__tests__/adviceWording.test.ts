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
  AS_OF_AGE_UNKNOWN_STATEMENT,
  AS_OF_DATE_UNKNOWN_FULL_STATEMENT,
  AS_OF_DATE_UNKNOWN_STATEMENT,
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
  AS_OF_DATE_UNKNOWN_STATEMENT,
  // R-D5②-1: the unknown-date slot ships both sentences, so the banned-term
  // scan has to see the追加句 and the full concatenation, not just the first
  // sentence it used to cover.
  AS_OF_AGE_UNKNOWN_STATEMENT,
  AS_OF_DATE_UNKNOWN_FULL_STATEMENT,
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

describe("the unknown-as-of-date slot (R-D5②-1, 風控逐字確認 2026-08-16)", () => {
  it("pins both approved sentences character for character", () => {
    expect(AS_OF_DATE_UNKNOWN_STATEMENT).toBe(
      "本評估未取得收盤資料的日期，無法標示評估所依據的資料時間。",
    );
    expect(AS_OF_AGE_UNKNOWN_STATEMENT).toBe("因此本次也無法判斷這份資料距今多久。");
  });

  it("ships the two sentences as one string, in order, with nothing between them", () => {
    // The disclosure only works as a pair: the first names the missing date,
    // the second names what that costs (no age judgement, hence no 資料過舊
    // notice). Concatenation is what makes "always together" structural rather
    // than a convention a future edit could break.
    expect(AS_OF_DATE_UNKNOWN_FULL_STATEMENT).toBe(
      "本評估未取得收盤資料的日期，無法標示評估所依據的資料時間。因此本次也無法判斷這份資料距今多久。",
    );
    expect(AS_OF_DATE_UNKNOWN_FULL_STATEMENT).toBe(
      AS_OF_DATE_UNKNOWN_STATEMENT + AS_OF_AGE_UNKNOWN_STATEMENT,
    );
    expect(AS_OF_DATE_UNKNOWN_FULL_STATEMENT.startsWith(AS_OF_DATE_UNKNOWN_STATEMENT)).toBe(true);
    expect(AS_OF_DATE_UNKNOWN_FULL_STATEMENT.endsWith(AS_OF_AGE_UNKNOWN_STATEMENT)).toBe(true);
  });

  it("carries no action guidance — it states two facts and stops", () => {
    for (const term of ["請", "建議", "自行", "應", "可以"]) {
      expect(AS_OF_AGE_UNKNOWN_STATEMENT).not.toContain(term);
    }
  });
});

describe("buildStaleDataProminentNotice — the C4 wording change (待風控覆核)", () => {
  it("states the gap in trading days, keeping the 2026-08-09-approved sentence shape", () => {
    // The literal sentence is pinned here so the review of the C4 change has
    // one place to read it: only the unit moved (日曆日 -> 交易日), because the
    // number it qualifies is now an observed trading-session count
    // (`data.trading_days_behind`) and leaving 「日曆日」 over it would be a
    // false statement. Every other word is unchanged from the 2026-08-09
    // 裁決 b sentence, including the 全形 punctuation of the final review.
    expect(buildStaleDataProminentNotice("2026-08-04", 3)).toBe(
      "本評估所依據的收盤資料為 2026-08-04，距今已 3 個交易日未更新，僅供參考，不代表最新市況。",
    );
  });

  it("names the basis date and the magnitude rather than hiding either", () => {
    const notice = buildStaleDataProminentNotice("2026-02-13", 12);
    expect(notice).toContain("2026-02-13");
    expect(notice).toContain("12");
  });
});

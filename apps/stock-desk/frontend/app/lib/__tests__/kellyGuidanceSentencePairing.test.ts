/**
 * 條件 107 (第十四輪): the lead-in sentence on `KellyInputsSection.tsx` pairs a
 * bare cap number ("第 5 條") with cap 5's own official name
 * (`LIMIT_NAMES["kelly_fraction"]` = "分數 Kelly 部位上限", `app/lib/format.ts`
 * `LIMIT_SELECTOR_LABELS.kelly_fraction`) — approved *as a pair*, never as a
 * bare ordinal: "(a) 條號不得裸用，拆開配對即失效". This suite pins that pairing
 * mechanically rather than trusting a future edit not to split it.
 *
 * Since 2026-10-26 (#61 batch one, plan D) the lead is the sunset version,
 * risk-compliance's #3 (`work/reviews/2026-10-26-第1條下修告知字面逐字審-風控.md`),
 * which **replaces** the 條件 107 sentence and lives in `cap1SunsetWording.ts`.
 * That ruling is newer than 條件 107 and departs from it in two places on
 * purpose: after the opening pair, "第 5 條" recurs as the subject of later
 * sentences, and it states that cap 5's figure is「不可靠」. Both are pinned
 * here verbatim instead, so the departure is exactly the approved one and no
 * more. The opening pair and the reverse rule (the name never without its
 * ordinal) still hold and are still asserted.
 */

import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { describe, expect, it } from "vitest";
import { KELLY_STALE_AFTER_DAYS, KELLY_SUNSET_LEAD, KELLY_SUNSET_LEAD_TEMPLATE } from "../cap1SunsetWording";
import { stripComments } from "./wordingScanHelpers";

const CAP_ORDINAL = "第 5 條";
const CAP_NAME = "分數 Kelly 部位上限";
//: The exact approved co-text between the two — a same-sentence pairing, not
//: merely "somewhere in the same file". Retyped rather than imported, so a
//: drift in either file shows up as a diff here.
const APPROVED_PAIRING = `${CAP_ORDINAL}「${CAP_NAME}」`;

//: #3, retyped from the risk table (`{KELLY_STALE_AFTER_DAYS}` interpolated).
const APPROVED_SUNSET_LEAD_TEMPLATE =
  "第 5 條「分數 Kelly 部位上限」使用的 win_rate／payoff_ratio 輸入。新增與修改已暫停（手填與從回測帶入皆同）；刪除仍可使用。已存在的輸入仍照原方式參與第 5 條，直到各自滿 {KELLY_STALE_AFTER_DAYS} 天過期為止。第 5 條的計算方式有誤，算出的數字不可靠；它只會讓該標的的上限比沒有第 5 條時更嚴或相同，不會更寬。刪除某筆輸入後，該標的不再受第 5 條限制，只受其他上限限制，上限可能因此比刪除前寬。";

function source(relative: string): string {
  return stripComments(readFileSync(fileURLToPath(new URL(relative, import.meta.url)), "utf-8"));
}

function kellyInputsSectionSource(): string {
  return source("../../settings/KellyInputsSection.tsx");
}

describe("KellyInputsSection.tsx — 條件 107 (條號＋官方上限名同句配對)", () => {
  it("carries the approved same-sentence pairing verbatim", () => {
    // The pair opens the lead the section renders.
    expect(KELLY_SUNSET_LEAD.startsWith(APPROVED_PAIRING)).toBe(true);
    expect(kellyInputsSectionSource()).toContain("{KELLY_SUNSET_LEAD}");
  });

  it("(a) 條號不得裸用: the first ordinal is paired with the cap's name, and every later bare one is the approved #3 text", () => {
    expect(KELLY_SUNSET_LEAD_TEMPLATE).toBe(APPROVED_SUNSET_LEAD_TEMPLATE);
    expect(KELLY_SUNSET_LEAD.indexOf(CAP_ORDINAL)).toBe(KELLY_SUNSET_LEAD.indexOf(APPROVED_PAIRING));
    // The section itself writes no ordinal of its own.
    expect(kellyInputsSectionSource().split(CAP_ORDINAL).length - 1).toBe(0);
  });

  it("the cap's official name never appears without the ordinal immediately in front of it (reverse direction of the same rule)", () => {
    for (const text of [kellyInputsSectionSource(), KELLY_SUNSET_LEAD]) {
      const nameOccurrences = text.split(CAP_NAME).length - 1;
      const pairedOccurrences = text.split(APPROVED_PAIRING).length - 1;
      expect(pairedOccurrences).toBe(nameOccurrences);
    }
  });

  it("(b) 本句封閉: the section names no number, no data quality, no methodology and no advice word", () => {
    const section = kellyInputsSectionSource();
    for (const banned of ["%", "建議", "應該", "最佳", "準確", "可靠"]) {
      expect(section).not.toContain(banned);
    }
    // The lead: the same list, except the one data-quality statement #3
    // makes on purpose (「不可靠」), which appears exactly once.
    for (const banned of ["%", "建議", "應該", "最佳", "準確"]) {
      expect(KELLY_SUNSET_LEAD).not.toContain(banned);
    }
    expect(KELLY_SUNSET_LEAD.split("可靠").length - 1).toBe(1);
    expect(KELLY_SUNSET_LEAD).toContain("算出的數字不可靠");
  });

  it("interpolates the staleness window rather than writing it", () => {
    expect(KELLY_SUNSET_LEAD_TEMPLATE).toContain("{KELLY_STALE_AFTER_DAYS}");
    expect(KELLY_SUNSET_LEAD_TEMPLATE).not.toContain(String(KELLY_STALE_AFTER_DAYS));
    expect(KELLY_SUNSET_LEAD).toContain(`直到各自滿 ${KELLY_STALE_AFTER_DAYS} 天過期為止`);
  });
});

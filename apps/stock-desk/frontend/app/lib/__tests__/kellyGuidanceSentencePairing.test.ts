/**
 * 條件 107 (第十四輪): the lead-in sentence on `KellyInputsSection.tsx` pairs a
 * bare cap number ("第 5 條") with cap 5's own official name
 * (`LIMIT_NAMES["kelly_fraction"]` = "分數 Kelly 部位上限", `app/lib/format.ts`
 * `LIMIT_SELECTOR_LABELS.kelly_fraction`) — approved *as a pair*, never as a
 * bare ordinal: "(a) 條號不得裸用，拆開配對即失效". This suite pins that pairing
 * mechanically rather than trusting a future edit not to split it.
 */

import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { describe, expect, it } from "vitest";
import { stripComments } from "./wordingScanHelpers";

const CAP_ORDINAL = "第 5 條";
const CAP_NAME = "分數 Kelly 部位上限";
//: The exact approved co-text between the two — a same-sentence pairing, not
//: merely "somewhere in the same file". Retyped from `KellyInputsSection.tsx`
//: rather than imported, so a drift in either file shows up as a diff here.
const APPROVED_PAIRING = `${CAP_ORDINAL}「${CAP_NAME}」`;

function kellyInputsSectionSource(): string {
  const absolutePath = fileURLToPath(
    new URL("../../settings/KellyInputsSection.tsx", import.meta.url),
  );
  return stripComments(readFileSync(absolutePath, "utf-8"));
}

describe("KellyInputsSection.tsx — 條件 107 (條號＋官方上限名同句配對)", () => {
  it("carries the approved same-sentence pairing verbatim", () => {
    expect(kellyInputsSectionSource()).toContain(APPROVED_PAIRING);
  });

  it("(a) 條號不得裸用: every occurrence of the bare cap ordinal is immediately paired with the cap's own name — none stand alone", () => {
    const source = kellyInputsSectionSource();
    const ordinalOccurrences = source.split(CAP_ORDINAL).length - 1;
    const pairedOccurrences = source.split(APPROVED_PAIRING).length - 1;
    expect(ordinalOccurrences).toBeGreaterThan(0);
    expect(pairedOccurrences).toBe(ordinalOccurrences);
  });

  it("the cap's official name never appears without the ordinal immediately in front of it (reverse direction of the same rule)", () => {
    const source = kellyInputsSectionSource();
    const nameOccurrences = source.split(CAP_NAME).length - 1;
    const pairedOccurrences = source.split(APPROVED_PAIRING).length - 1;
    expect(pairedOccurrences).toBe(nameOccurrences);
  });

  it("(b) 本句封閉: the guidance sentence names no number, no data quality, no methodology and no advice word", () => {
    const source = kellyInputsSectionSource();
    for (const banned of ["%", "建議", "應該", "最佳", "準確", "可靠"]) {
      expect(source).not.toContain(banned);
    }
  });
});

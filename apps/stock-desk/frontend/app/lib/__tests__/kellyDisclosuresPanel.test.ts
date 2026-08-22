/**
 * `KellyDisclosuresPanel.tsx` coverage: its one piece of frontend judgement
 * (`showsFreshnessBadge`, 條件 97) as a pure-function unit test, and a source
 * scan asserting the file's *rendered* text carries no Chinese literal of its
 * own — 落地條件 3/約束 21: every sentence a user reads from this surface must
 * be a field straight off `KellyDisclosuresView`, never composed here.
 *
 * DOM-level assertions (the original-values toggle's mutual exclusion, the
 * "back" control's presence) are qa-e2e's to verify on a real page — this
 * repo has no `@testing-library/react`/jsdom yet (`vitest.config.ts`).
 */

import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { describe, expect, it } from "vitest";
import {
  shouldRenderManualInputForm,
  shouldShowOriginalValues,
  showsFreshnessBadge,
} from "../../settings/KellyDisclosuresPanel";
import type { KellyOriginalValuesView } from "../types";
import { chineseLiteralsOutsideComments } from "./wordingScanHelpers";

const ORIGINAL: KellyOriginalValuesView = {
  statement: "s",
  win_rate_label: "wl",
  win_rate: "55.0%",
  payoff_ratio_label: "pl",
  payoff_ratio: "1.50",
};

describe("showsFreshnessBadge — 條件 97 (無 (g) 句畫面不得渲染 expired 徽章)", () => {
  it("withholds the badge only for `expired`", () => {
    expect(showsFreshnessBadge("expired")).toBe(false);
  });

  it("renders normally for fresh/ageing", () => {
    expect(showsFreshnessBadge("fresh")).toBe(true);
    expect(showsFreshnessBadge("ageing")).toBe(true);
  });

  it("renders normally for the absent state (`null` — no row at all, 條件 47 ①)", () => {
    expect(showsFreshnessBadge(null)).toBe(true);
  });
});

describe("shouldShowOriginalValues — 條件 46 約束 3 (互斥檢視)", () => {
  it("shows only when the toggle is on and a kept original pair exists", () => {
    expect(shouldShowOriginalValues(true, ORIGINAL)).toBe(true);
  });

  it("never shows when the row has no kept original pair, even with the toggle on", () => {
    expect(shouldShowOriginalValues(true, null)).toBe(false);
  });

  it("never shows when the toggle is off, even with a kept original pair", () => {
    expect(shouldShowOriginalValues(false, ORIGINAL)).toBe(false);
  });

  it("off and absent together: still false", () => {
    expect(shouldShowOriginalValues(false, null)).toBe(false);
  });
});

/**
 * B1 (qa 補審 2026-08-22, `work/reviews/2026-08-22-C5-K4c2-qa補審.md`): the
 * bidirectional guarantee — `shouldRenderManualInputForm` is the exact
 * complement of `shouldShowOriginalValues`, so the two conditions cannot
 * independently drift into a state where both are true (double-rendered) or
 * both are false (rendered nowhere) at once.
 */
describe("shouldRenderManualInputForm — B1 (互斥檢視雙向)", () => {
  it("renders the form when the original-values view would not show (either direction of shouldShowOriginalValues)", () => {
    for (const [showOriginal, original] of [
      [false, null],
      [false, ORIGINAL],
      [true, null],
    ] as const) {
      expect(shouldRenderManualInputForm(showOriginal, original)).toBe(true);
      expect(shouldShowOriginalValues(showOriginal, original)).toBe(false);
    }
  });

  it("never renders the form in the one state where the original-values view does show", () => {
    expect(shouldRenderManualInputForm(true, ORIGINAL)).toBe(false);
    expect(shouldShowOriginalValues(true, ORIGINAL)).toBe(true);
  });

  it("is the exact complement of shouldShowOriginalValues over every input combination — never equal", () => {
    for (const showOriginal of [true, false]) {
      for (const original of [ORIGINAL, null]) {
        expect(shouldRenderManualInputForm(showOriginal, original)).toBe(
          !shouldShowOriginalValues(showOriginal, original),
        );
      }
    }
  });
});

describe("KellyDisclosuresPanel.tsx — zero Chinese literal outside comments (落地條件 3/約束 21)", () => {
  const absolutePath = fileURLToPath(new URL("../../settings/KellyDisclosuresPanel.tsx", import.meta.url));
  const source = readFileSync(absolutePath, "utf-8");

  it("carries no Han character in its rendered-text source", () => {
    expect(chineseLiteralsOutsideComments(source)).toEqual([]);
  });

  it("B1 structural guard: <KellyManualInputForm renders only inside the effective (else) branch of the mutual-exclusion ternary, never inside the original-values (if) branch", () => {
    // The ternary's own else-branch marker (`) : (`) is the boundary between
    // the two mutually exclusive subtrees this file renders — asserting the
    // form's own JSX tag sits strictly after it (and the file contains
    // exactly one such marker, so "after it" is unambiguous) pins B1's fix
    // at the source-position level, not just via the pure-function pair
    // above (which a future edit could satisfy while still literally
    // rendering the form in the wrong branch).
    const elseBranchMarkers = source.match(/\) : \(/g) ?? [];
    expect(elseBranchMarkers).toHaveLength(1);
    const elseBranchStart = source.indexOf(") : (");
    const formTagIndex = source.indexOf("<KellyManualInputForm");
    expect(formTagIndex).toBeGreaterThan(-1);
    expect(formTagIndex).toBeGreaterThan(elseBranchStart);
  });
});

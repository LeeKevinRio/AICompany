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
import { shouldShowOriginalValues, showsFreshnessBadge } from "../../settings/KellyDisclosuresPanel";
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

describe("KellyDisclosuresPanel.tsx — zero Chinese literal outside comments (落地條件 3/約束 21)", () => {
  it("carries no Han character in its rendered-text source", () => {
    const absolutePath = fileURLToPath(
      new URL("../../settings/KellyDisclosuresPanel.tsx", import.meta.url),
    );
    const source = readFileSync(absolutePath, "utf-8");
    expect(chineseLiteralsOutsideComments(source)).toEqual([]);
  });
});

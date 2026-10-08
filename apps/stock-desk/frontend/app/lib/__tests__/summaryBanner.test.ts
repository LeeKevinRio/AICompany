import { readFileSync, readdirSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";
import { SummaryCards } from "../../components/SummaryCards";
import { FRONTEND_FORBIDDEN_TERMS } from "../adviceWording";
import { SUMMARY_BANNER_NO_DATA, SUMMARY_BANNER_PARTIAL } from "../oneLinerWording";
import type { PortfolioTotals } from "../types";
import { assertNoForbiddenTerms, findBareRealtimeClaims } from "./wordingScanHelpers";

/**
 * X-3c XC-N2 (風控 2026-10-08 第三段 + 任務單「XC-N2 字面核可」段): the home totals
 * banner no longer blames "資料不足". It uses the umbrella term 「無法估值」, counts
 * 部位 (not 標的), and is unchanged in role / amber styling. Tests reference the
 * constants; the verbatim pin lives here once.
 */

function totals(status: PortfolioTotals["status"]): PortfolioTotals {
  return {
    cost_twd: "100000",
    market_value_twd: "105000",
    unrealized_pnl_twd: "5000",
    asset_contribution_twd: "4000",
    fx_contribution_twd: "1000",
    status,
  };
}

function render(status: PortfolioTotals["status"]): string {
  return renderToStaticMarkup(
    createElement(SummaryCards, {
      totals: totals(status),
      asOf: "2026-10-08T00:00:00Z",
      positions: [],
      fxDisclosures: [],
      fxBackupActive: false,
    }),
  );
}

const BANNER_OPEN =
  '<p role="status" class="rounded-md border border-amber-800 bg-amber-950/50 px-4 py-2 text-sm text-amber-300">';

const CASES = [
  { status: "partial", text: SUMMARY_BANNER_PARTIAL, other: SUMMARY_BANNER_NO_DATA },
  { status: "no_data", text: SUMMARY_BANNER_NO_DATA, other: SUMMARY_BANNER_PARTIAL },
  { status: "complete", text: null, other: null },
] as const;

describe("SummaryCards banner — XC-N2 approved wording", () => {
  it("pins the two approved sentences verbatim (19 and 17 characters)", () => {
    expect(SUMMARY_BANNER_PARTIAL).toBe("部分部位無法估值，總計僅含可估值部位。");
    expect(SUMMARY_BANNER_NO_DATA).toBe("所有部位皆無法估值，總計無法計算。");
    expect(SUMMARY_BANNER_PARTIAL).toHaveLength(19);
    expect(SUMMARY_BANNER_NO_DATA).toHaveLength(17);
  });

  for (const c of CASES) {
    it(`status ${c.status}: ${c.text === null ? "no banner" : "the approved sentence in a role=status amber banner, the other sentence absent"}`, () => {
      const html = render(c.status);
      if (c.text === null) {
        expect(html).not.toContain('role="status"');
        expect(html).not.toContain(SUMMARY_BANNER_PARTIAL);
        expect(html).not.toContain(SUMMARY_BANNER_NO_DATA);
        return;
      }
      expect(html).toContain(`${BANNER_OPEN}${c.text}</p>`);
      expect(html).not.toContain(c.other);
      expect(html).not.toContain("資料不足");
    });
  }

  // Mirrors the backend's `test_rx1_each_constant_carries_its_approval`: each
  // approved constant carries its own approval line and both source paths in
  // the JSDoc block directly above it, so neither depends on a shared comment.
  for (const name of ["SUMMARY_BANNER_PARTIAL", "SUMMARY_BANNER_NO_DATA"] as const) {
    it(`${name} carries its own approval note`, () => {
      const source = readFileSync(
        fileURLToPath(new URL("../oneLinerWording.ts", import.meta.url)),
        "utf-8",
      );
      const lines = source.split("\n");
      const index = lines.findIndex((line) => line.startsWith(`export const ${name} = `));
      expect(index, name).toBeGreaterThan(0);
      expect(lines[index - 1]?.trim(), name).toBe("*/");
      let start = index - 1;
      while (start > 0 && !(lines[start] ?? "").trim().startsWith("/**")) start -= 1;
      const block = lines.slice(start, index).join("\n");
      expect(block, name).toContain("風控核可文案,修改須重新送審(2026-10-08)");
      expect(block, name).toContain(
        "work/reviews/2026-10-08-X-3c-第三段-首頁橫幅與關鍵價位錨點-風控裁定.md",
      );
      expect(block, name).toContain(
        "work/dispatch/2026-10-07-任務單-X-3-持倉幣別與市場不符的legacy列.md",
      );
    });
  }

  it("carries no banned term and no bare realtime claim", () => {
    for (const [name, text] of [
      ["SUMMARY_BANNER_PARTIAL", SUMMARY_BANNER_PARTIAL],
      ["SUMMARY_BANNER_NO_DATA", SUMMARY_BANNER_NO_DATA],
    ] as const) {
      assertNoForbiddenTerms(text, FRONTEND_FORBIDDEN_TERMS, name);
      expect(findBareRealtimeClaims(text), name).toEqual([]);
    }
  });

  it("R3: the old banner sentences are gone from the frontend source and tests ", () => {
    const appRoot = fileURLToPath(new URL("../..", import.meta.url));
    const stack = [appRoot];
    const hits: string[] = [];
    // Needles are built from parts so this file does not contain them itself.
    const needles = ["部分標的" + "資料不足", "無可用" + "估值資料"];
    while (stack.length > 0) {
      const dir = stack.pop() as string;
      for (const entry of readdirSync(dir, { withFileTypes: true })) {
        const full = `${dir}/${entry.name}`;
        if (entry.isDirectory()) {
          if (entry.name !== "node_modules" && entry.name !== ".next") stack.push(full);
        } else if (/\.(ts|tsx)$/.test(entry.name)) {
          const src = readFileSync(full, "utf-8");
          if (needles.some((needle) => src.includes(needle))) hits.push(full);
        }
      }
    }
    expect(hits).toEqual([]);
  });
});

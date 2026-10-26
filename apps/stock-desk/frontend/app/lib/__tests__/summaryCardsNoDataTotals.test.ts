import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";
import { SummaryCards } from "../../components/SummaryCards";
import { SUMMARY_BANNER_NO_DATA, SUMMARY_BANNER_PARTIAL } from "../oneLinerWording";
import type { PortfolioTotals } from "../types";

/**
 * A-1 (需求總綱 NP-B4): when no position could be valued (`status ===
 * "no_data"`, the empty book included) the summary has no total, so the four
 * amount cards -- 總資產（市值）, 未實現損益, 標的貢獻, 匯率貢獻 -- must read "—"
 * in a neutral colour, never NT$0. The mask keys on `status`, not on the
 * values. `partial` and `complete` are unchanged: a real zero there still
 * reads NT$0.
 */

function render(totals: PortfolioTotals): string {
  return renderToStaticMarkup(
    createElement(SummaryCards, {
      totals,
      asOf: "2026-10-15T00:00:00Z",
      positions: [],
      fxDisclosures: [],
      fxBackupActive: false,
    }),
  );
}

/** The four amount cells, in render order, as `{ cls, text }`. */
function amountCells(html: string): { cls: string; text: string }[] {
  return [...html.matchAll(/<p class="mt-1 ([^"]*)">([^<]*)<\/p>/g)].map((m) => ({
    cls: m[1] ?? "",
    text: m[2] ?? "",
  }));
}

const ZERO_NO_DATA: PortfolioTotals = {
  cost_twd: "0",
  market_value_twd: "0",
  unrealized_pnl_twd: "0",
  asset_contribution_twd: "0",
  fx_contribution_twd: "0",
  status: "no_data",
};

describe("SummaryCards — no_data totals read as a dash (A-1)", () => {
  it("shows a dash in all four amount cards for the all-zero no_data payload", () => {
    const html = render(ZERO_NO_DATA);
    const cells = amountCells(html);
    expect(cells).toHaveLength(4);
    expect(cells.map((c) => c.text)).toEqual(["—", "—", "—", "—"]);
    expect(html).not.toContain("NT$0");
    expect(html).not.toMatch(/>0</);
    expect(html).toContain(SUMMARY_BANNER_NO_DATA);
  });

  it("masks by status, not by value: a no_data payload with nonzero amounts still reads a dash", () => {
    const html = render({
      cost_twd: "900000",
      market_value_twd: "1031500.0",
      unrealized_pnl_twd: "131500.0",
      asset_contribution_twd: "131500.0",
      fx_contribution_twd: "-2500.0",
      status: "no_data",
    });
    const cells = amountCells(html);
    expect(cells).toHaveLength(4);
    expect(cells.map((c) => c.text)).toEqual(["—", "—", "—", "—"]);
    expect(html).not.toContain("1,031,500");
    expect(html).not.toContain("131,500");
  });

  it("never paints a no_data amount in a gain or loss colour", () => {
    const html = render({ ...ZERO_NO_DATA, unrealized_pnl_twd: "5000", asset_contribution_twd: "-5000" });
    const cells = amountCells(html);
    expect(cells).toHaveLength(4);
    expect(html).not.toContain("text-rose-400");
    expect(html).not.toContain("text-emerald-400");
    for (const cell of cells.slice(1)) {
      expect(cell.cls).toContain("text-neutral-400");
    }
  });

  it("leaves a partial book's amounts as they are", () => {
    const html = render({
      cost_twd: "900000",
      market_value_twd: "1031500.0",
      unrealized_pnl_twd: "131500.0",
      asset_contribution_twd: "131500.0",
      fx_contribution_twd: "0",
      status: "partial",
    });
    const cells = amountCells(html);
    expect(cells.map((c) => c.text)).toEqual([
      "NT$1,031,500",
      "NT$131,500",
      "NT$131,500",
      "NT$0",
    ]);
    expect(html).not.toContain("—");
    expect(html).toContain(SUMMARY_BANNER_PARTIAL);
  });

  it("leaves a complete book's amounts as they are", () => {
    const html = render({
      cost_twd: "1200000",
      market_value_twd: "1494500.0",
      unrealized_pnl_twd: "294500.0",
      asset_contribution_twd: "294500.0",
      fx_contribution_twd: "0",
      status: "complete",
    });
    const cells = amountCells(html);
    expect(cells.map((c) => c.text)).toEqual([
      "NT$1,494,500",
      "NT$294,500",
      "NT$294,500",
      "NT$0",
    ]);
    expect(html).not.toContain("—");
  });

  it("only no_data masks: a complete book whose amounts are truly zero still shows the zeros", () => {
    const html = render({ ...ZERO_NO_DATA, status: "complete" });
    const cells = amountCells(html);
    expect(cells).toHaveLength(4);
    for (const cell of cells) {
      expect(cell.text).toBe("NT$0");
    }
    expect(html).not.toContain("—");
  });
});

/**
 * T1-12 (F3): since the API sends null amounts under `no_data` (the empty book
 * included), the card must render that real payload as "—" too -- and never
 * leak the words "null" or "NaN" -- for every shape a no_data payload can take.
 */
describe("SummaryCards — the null no_data payload (T1-12)", () => {
  const NULL_NO_DATA: PortfolioTotals = {
    cost_twd: null,
    market_value_twd: null,
    unrealized_pnl_twd: null,
    asset_contribution_twd: null,
    fx_contribution_twd: null,
    status: "no_data",
  };

  it("shows a dash in all four amount cards when the payload amounts are null", () => {
    const html = render(NULL_NO_DATA);
    const cells = amountCells(html);
    expect(cells).toHaveLength(4);
    expect(cells.map((c) => c.text)).toEqual(["—", "—", "—", "—"]);
    expect(html).not.toContain("NT$0");
    expect(html).not.toContain("text-rose-400");
    expect(html).not.toContain("text-emerald-400");
    expect(html).toContain(SUMMARY_BANNER_NO_DATA);
  });

  const SHAPES: [string, PortfolioTotals][] = [
    ["zero", ZERO_NO_DATA],
    [
      "nonzero",
      {
        ...ZERO_NO_DATA,
        market_value_twd: "1031500.0",
        unrealized_pnl_twd: "131500.0",
        asset_contribution_twd: "131500.0",
      },
    ],
    ["null", NULL_NO_DATA],
  ];
  for (const [name, totals] of SHAPES) {
    it(`never renders "null" or "NaN" for the ${name} no_data payload`, () => {
      const html = render(totals);
      expect(html).not.toContain("null");
      expect(html).not.toContain("NaN");
      expect(amountCells(html).map((c) => c.text)).toEqual(["—", "—", "—", "—"]);
    });
  }
});

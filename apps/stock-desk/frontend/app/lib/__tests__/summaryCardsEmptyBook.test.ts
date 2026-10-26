import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";
import { SummaryCards } from "../../components/SummaryCards";
import { EMPTY_TITLE } from "../inventoryWording";
import { SUMMARY_BANNER_NO_DATA } from "../oneLinerWording";
import type { PortfolioTotals, SummaryPositionItem } from "../types";

/**
 * Trust defect (2026-10-26 product review, frontend-engineer empty-state note):
 * with no positions at all the home page said 「所有部位皆無法估值，總計無法計算。」
 * and printed NT$0 in all four cards. There is nothing to value, and NT$0 reads
 * as a real zero. The banner now reuses the existing empty-state line
 * 「尚無持倉」 and every amount is 「—」.
 *
 * `GET /api/portfolio/summary` with an empty book: totals are Decimal 0 and
 * `status` is `no_data` (`app/portfolio/summary.py` `_totals_status`).
 */

const ZERO_TOTALS: PortfolioTotals = {
  cost_twd: "0",
  market_value_twd: "0",
  unrealized_pnl_twd: "0",
  asset_contribution_twd: "0",
  fx_contribution_twd: "0",
  status: "no_data",
};

const UNVALUED: SummaryPositionItem = {
  id: 1,
  symbol: "2330",
  market: "TW",
  quantity: "1000",
  avg_cost: "895.44",
  currency: "TWD",
  instrument_type: "stock",
  opened_at: null,
  sector: null,
  note: null,
  valuation: {
    status: "insufficient_data",
    missing: ["price"],
    price: null,
    fx: null,
    fx_open: null,
    pnl_original: null,
    pnl_twd: null,
    asset_contribution_twd: null,
    fx_contribution_twd: null,
  },
  market_value_twd: null,
  cost_twd: null,
  change: null,
};

function render(totals: PortfolioTotals, positions: SummaryPositionItem[]): string {
  return renderToStaticMarkup(
    createElement(SummaryCards, { totals, asOf: "2026-10-26T00:00:00Z", positions, fxDisclosures: [], fxBackupActive: false }),
  );
}

/** The big number of each of the four cards, in page order. */
function amounts(html: string): string[] {
  return [...html.matchAll(/<p class="mt-1 text-(?:3xl font-bold|xl font-semibold)[^"]*">([^<]*)<\/p>/g)].map((m) => m[1] ?? "");
}

describe("SummaryCards — empty book", () => {
  it("no positions: 「尚無持倉」 instead of the 無法估值 banner", () => {
    const html = render(ZERO_TOTALS, []);
    expect(html).toContain(`<p role="status" class="rounded-md border border-neutral-800 px-4 py-2 text-sm text-neutral-300">${EMPTY_TITLE}</p>`);
    expect(html).not.toContain(SUMMARY_BANNER_NO_DATA);
    expect(html).not.toContain("amber");
  });

  it("no positions: all four amounts are 「—」, never NT$0", () => {
    const html = render(ZERO_TOTALS, []);
    expect(amounts(html)).toEqual(["—", "—", "—", "—"]);
    expect(html).not.toContain("NT$0");
  });

  it("positions exist but none could be valued: the approved 無法估值 banner stays, amounts are 「—」 too", () => {
    const html = render(ZERO_TOTALS, [UNVALUED]);
    expect(html).toContain(SUMMARY_BANNER_NO_DATA);
    expect(html).not.toContain(EMPTY_TITLE);
    expect(amounts(html)).toEqual(["—", "—", "—", "—"]);
    expect(html).not.toContain("NT$0");
  });

  it("a valued book that really sums to zero still prints NT$0 (only no_data is masked)", () => {
    const html = render({ ...ZERO_TOTALS, status: "complete" }, []);
    expect(amounts(html)).toEqual(["NT$0", "NT$0", "NT$0", "NT$0"]);
    expect(html).not.toContain(EMPTY_TITLE);
  });
});

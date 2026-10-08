import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";
import { UnavailableReasonBadge } from "../../components/DataStatusBadge";
import { PositionsTableView } from "../../components/PositionsTable";
import { MISSING_LABELS } from "../valuationWording";
import type { PositionFx, PositionValuation, SummaryPositionItem } from "../types";

/**
 * X-3c RX-3 (風控 2026-10-08 第二段, XC-N1): a legacy row whose stored currency does
 * not match its market must show label (a) on the home positions table and must
 * NOT show the "資料不足" badge (that would blame a data outage for an inconsistent
 * record). Ordinary unvalued rows and ok rows keep their existing rendering.
 */

const MISMATCH_LABEL = MISSING_LABELS.currency_market_mismatch as string;
const UNAVAILABLE_BADGE_CLASS =
  "whitespace-nowrap rounded border border-neutral-500 bg-neutral-800 px-1.5 py-0.5 text-xs text-neutral-200";

type ValuationOverride = Partial<PositionValuation>;

function row(symbol: string, valuation: ValuationOverride): SummaryPositionItem {
  const unvalued = valuation.status === "insufficient_data";
  return {
    id: 1,
    symbol,
    market: "US",
    quantity: "10",
    avg_cost: "100",
    currency: "TWD",
    instrument_type: "stock",
    opened_at: "2026-03-12",
    sector: null,
    note: null,
    market_value_twd: unvalued ? null : "110000",
    cost_twd: unvalued ? null : "100000",
    change: null,
    valuation: {
      status: "ok",
      missing: [],
      price: {
        value: "110",
        as_of: "2026-10-02",
        source: "twse",
        price_kind: "daily_close",
        data_status: "fresh",
        is_within_ttl: null,
        reason: null,
      },
      fx: null,
      fx_open: null,
      pnl_original: unvalued ? null : { value: "10000", currency: "TWD" },
      pnl_twd: unvalued ? null : "10000",
      asset_contribution_twd: unvalued ? null : "10000",
      fx_contribution_twd: unvalued ? null : "0",
      ...valuation,
    },
  };
}

function render(position: SummaryPositionItem): string {
  return renderToStaticMarkup(
    createElement(PositionsTableView, {
      positions: [position],
      namesBySymbol: {},
      changeMode: "close_only",
    }),
  );
}

const MISMATCH: ValuationOverride = {
  status: "insufficient_data",
  missing: ["currency_market_mismatch"],
  price: null,
};

interface Case {
  name: string;
  position: SummaryPositionItem;
  expectUnavailableBadge: boolean;
  expectMismatchLabel: boolean;
  expectedMissingText: string | null;
}

const CASES: Case[] = [
  {
    name: "mismatch row (price null, only the mismatch token)",
    position: row("MSFT", MISMATCH),
    expectUnavailableBadge: false,
    expectMismatchLabel: true,
    expectedMissingText: null,
  },
  {
    name: "mismatch token plus a stray extra token is NOT a mismatch row: ordinary path, visible failure",
    position: row("MSFT", { ...MISMATCH, missing: ["currency_market_mismatch", "fx_now"] }),
    expectUnavailableBadge: true,
    expectMismatchLabel: true,
    expectedMissingText: "幣別與市場不符、查無即期匯率",
  },
  {
    name: "ordinary unvalued row, price token (behaviour unchanged)",
    position: row("2330", { status: "insufficient_data", missing: ["price"], price: null }),
    expectUnavailableBadge: true,
    expectMismatchLabel: false,
    expectedMissingText: "查無價格資料",
  },
  {
    name: "ordinary unvalued row, not-queried token (behaviour unchanged)",
    position: row("2330", { status: "insufficient_data", missing: ["price_not_queried"], price: null }),
    expectUnavailableBadge: true,
    expectMismatchLabel: false,
    expectedMissingText: "本次未查價格",
  },
  {
    name: "ordinary unvalued row, fx token (behaviour unchanged)",
    position: row("MSFT", { status: "insufficient_data", missing: ["fx_now"], price: null }),
    expectUnavailableBadge: true,
    expectMismatchLabel: false,
    expectedMissingText: "查無即期匯率",
  },
  {
    name: "ok row (behaviour unchanged)",
    position: row("2330", {}),
    expectUnavailableBadge: false,
    expectMismatchLabel: false,
    expectedMissingText: null,
  },
];

describe("PositionsTable price cell — currency/market mismatch row (RX-3)", () => {
  for (const c of CASES) {
    it(c.name, () => {
      const html = render(c.position);
      expect(html.includes(`<span class="${UNAVAILABLE_BADGE_CLASS}">資料不足</span>`)).toBe(
        c.expectUnavailableBadge,
      );
      expect(html.includes("資料不足")).toBe(c.expectUnavailableBadge);
      expect(html.includes(MISMATCH_LABEL)).toBe(c.expectMismatchLabel);
      if (c.expectedMissingText !== null) expect(html).toContain(c.expectedMissingText);
    });
  }

  it("mismatch row: label (a) appears exactly once, as a badge with the same class as the 資料不足 badge, next to the dash", () => {
    const html = render(row("MSFT", MISMATCH));
    expect(html.split(MISMATCH_LABEL)).toHaveLength(2);
    expect(html).toContain(`<span class="${UNAVAILABLE_BADGE_CLASS}">${MISMATCH_LABEL}</span>`);
    expect(html).toContain('<span class="text-neutral-400">—</span>');
    // no price figure, "MM/DD 收盤" date label or "查無…" misattribution on the row
    expect(html).not.toMatch(/\d{2}\/\d{2} 收盤/);
    expect(html).not.toContain("110.00");
    expect(html).not.toContain("查無");
    expect(html).not.toContain("本次未查");
  });

  it("mismatch row: no small cause line under the chip (label (a) is the only mention)", () => {
    const html = render(row("MSFT", MISMATCH));
    expect(html).not.toContain(`<p class="mt-0.5 text-xs text-neutral-400">${MISMATCH_LABEL}</p>`);
    expect(html).not.toContain("title=\"幣別");
    expect(html).not.toContain("aria-label=\"幣別");
  });

  it("the shared chip component renders its children in the prominent chip style and adds no attributes", () => {
    expect(renderToStaticMarkup(createElement(UnavailableReasonBadge, null, MISMATCH_LABEL))).toBe(
      `<span class="${UNAVAILABLE_BADGE_CLASS}">${MISMATCH_LABEL}</span>`,
    );
  });
});

const FX_UNAVAILABLE: PositionFx = {
  pair: "USDTWD",
  as_of: null,
  source: "none",
  data_status: "unavailable",
  source_note: "",
  is_within_ttl: null,
  reason: null,
};

describe("PositionsTable FX badge on a mismatch row (art-lead R-1)", () => {
  it("contract case: mismatch row with fx === null shows no 匯率 badge of any kind", () => {
    const html = render(row("MSFT", { ...MISMATCH, fx: null }));
    // the fixed detail label 匯率貢獻 is not a badge; the FX badge texts are
    // "匯率 …" (no date) and "MM/DD 匯率" (dated)
    expect(html).not.toContain("匯率 ");
    expect(html).not.toMatch(/\d{2}\/\d{2} 匯率/);
  });

  it("defensive case: even if a mismatch row carried an unavailable fx, no 匯率 資料不足 is rendered", () => {
    const html = render(row("MSFT", { ...MISMATCH, fx: FX_UNAVAILABLE }));
    expect(html).not.toContain("匯率 資料不足");
    expect(html).not.toContain("資料不足");
  });

  it("an ordinary unvalued row with an unavailable fx keeps its 匯率 資料不足 badge (unchanged)", () => {
    const html = render(row("MSFT", { status: "insufficient_data", missing: ["fx_now"], price: null, fx: FX_UNAVAILABLE }));
    expect(html).toContain("匯率 資料不足");
  });
});

import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { describe, expect, it } from "vitest";
import { SummaryCards } from "../../components/SummaryCards";
import { formatTaipeiMonthDayTime } from "../format";
import { buildBasisSentence, buildBasisTooltip, deriveValuationBasis } from "../valuationBasis";
import type { PortfolioTotals, PositionPrice, SummaryPositionItem } from "../types";

const totals: PortfolioTotals = {
  cost_twd: "100000",
  market_value_twd: "105000",
  unrealized_pnl_twd: "5000",
  asset_contribution_twd: "4000",
  fx_contribution_twd: "1000",
  status: "complete",
};

function price(asOf: string): PositionPrice {
  return {
    value: "100",
    as_of: asOf,
    source: "twse",
    price_kind: "daily_close",
    data_status: "fresh",
    is_within_ttl: null,
    reason: null,
  };
}

function position(id: number, priceValue: PositionPrice | null): SummaryPositionItem {
  return {
    id,
    symbol: `S${id}`,
    market: "TW",
    quantity: "1",
    avg_cost: "1",
    currency: "TWD",
    instrument_type: "stock",
    opened_at: null,
    sector: null,
    note: null,
    valuation: {
      status: priceValue === null ? "insufficient_data" : "ok",
      missing: [],
      price: priceValue,
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
}

function render(positions: SummaryPositionItem[], asOf = "2026-10-03T06:05:09Z"): string {
  return renderToStaticMarkup(
    createElement(SummaryCards, { totals, asOf, positions, fxDisclosures: [], fxBackupActive: false }),
  );
}

describe("deriveValuationBasis", () => {
  it("counts only positions that carry a price", () => {
    const basis = deriveValuationBasis([position(1, price("2026-10-02")), position(2, null), position(3, price("2026-10-02"))]);
    expect(basis).toEqual({ pricedCount: 2, earliest: "2026-10-02", latest: "2026-10-02" });
  });

  it("returns the earliest and latest date across positions", () => {
    const basis = deriveValuationBasis([position(1, price("2026-10-02")), position(2, price("2026-09-30")), position(3, price("2026-10-01"))]);
    expect(basis).toEqual({ pricedCount: 3, earliest: "2026-09-30", latest: "2026-10-02" });
  });

  it("orders across a year boundary by full date, not by MM/DD", () => {
    const basis = deriveValuationBasis([position(1, price("2027-01-04")), position(2, price("2026-12-31"))]);
    expect(basis?.earliest).toBe("2026-12-31");
    expect(basis?.latest).toBe("2027-01-04");
  });

  it("returns null with no positions or no priced position", () => {
    expect(deriveValuationBasis([])).toBeNull();
    expect(deriveValuationBasis([position(1, null), position(2, null)])).toBeNull();
  });

  it("returns null instead of guessing when a priced position's as_of is not a date", () => {
    expect(deriveValuationBasis([position(1, price("2026-10-02")), position(2, price("not-a-date"))])).toBeNull();
  });

  it("returns null when as_of is a timestamp, not a bare trading date (never label a quote as a close)", () => {
    expect(deriveValuationBasis([position(1, price("2026-10-02T05:00:00Z"))])).toBeNull();
    expect(deriveValuationBasis([position(1, price("2026-10-02")), position(2, price("2026-10-02T05:00:00+08:00"))])).toBeNull();
  });
});

describe("buildBasisSentence (C3-3, verbatim)", () => {
  it("single date version", () => {
    expect(buildBasisSentence({ pricedCount: 3, earliest: "2026-10-02", latest: "2026-10-02" })).toBe(
      "估值基準：3 檔皆為收盤價（10/02）",
    );
  });

  it("date range version, earliest first", () => {
    expect(buildBasisSentence({ pricedCount: 3, earliest: "2026-09-30", latest: "2026-10-02" })).toBe(
      "估值基準：3 檔皆為收盤價（09/30～10/02）",
    );
  });

  it("N = 1 uses the single date version", () => {
    expect(buildBasisSentence({ pricedCount: 1, earliest: "2026-10-02", latest: "2026-10-02" })).toBe(
      "估值基準：1 檔皆為收盤價（10/02）",
    );
  });
});

describe("formatTaipeiMonthDayTime", () => {
  it("renders the Taipei day and 24h clock, crossing the UTC date line", () => {
    expect(formatTaipeiMonthDayTime("2026-10-03T06:05:09Z")).toEqual({ monthDay: "10/03", time: "14:05:09" });
    // 18:30 UTC is 02:30 the next day in Taipei
    expect(formatTaipeiMonthDayTime("2026-10-03T18:30:00Z")).toEqual({ monthDay: "10/04", time: "02:30:00" });
    // 16:00:00 UTC is Taipei midnight: 00:00:00, never 24:00:00
    expect(formatTaipeiMonthDayTime("2026-10-03T16:00:00Z")).toEqual({ monthDay: "10/04", time: "00:00:00" });
  });

  it("returns null for missing or invalid input", () => {
    expect(formatTaipeiMonthDayTime(null)).toBeNull();
    expect(formatTaipeiMonthDayTime("")).toBeNull();
    expect(formatTaipeiMonthDayTime("garbage")).toBeNull();
  });
});

describe("buildBasisTooltip (C5-1, verbatim)", () => {
  it("joins sentence 1 and sentence 2 with Taipei day and time filled in", () => {
    expect(buildBasisTooltip("2026-10-03T06:05:09Z")).toBe(
      "各檔價格旁標示該檔的成交時間或收盤日期。本頁於 10/03 14:05:09（台北時間）計算，這是本產品算出總計的時間，不是成交時間。",
    );
  });

  it("returns null (no half-filled tooltip) when the timestamp is unusable", () => {
    expect(buildBasisTooltip("garbage")).toBeNull();
  });
});

describe("SummaryCards — valuation basis sentence (C3-3 + C5-1)", () => {
  it("single trading date: shows the single date sentence with the C5-1 tooltip", () => {
    const html = render([position(1, price("2026-10-02")), position(2, price("2026-10-02"))]);
    expect(html).toContain("估值基準：2 檔皆為收盤價（10/02）");
    expect(html).toContain(
      'title="各檔價格旁標示該檔的成交時間或收盤日期。本頁於 10/03 14:05:09（台北時間）計算，這是本產品算出總計的時間，不是成交時間。"',
    );
  });

  it("different trading dates: switches to the range sentence", () => {
    const html = render([position(1, price("2026-10-02")), position(2, price("2026-09-30"))]);
    expect(html).toContain("估值基準：2 檔皆為收盤價（09/30～10/02）");
    expect(html).not.toContain("皆為收盤價（10/02）");
  });

  it("the old 資料時間 line is gone and the response time is not a visible label", () => {
    const html = render([position(1, price("2026-10-02"))]);
    expect(html).not.toContain("資料時間");
    // time only survives inside the title attribute
    const visible = html.replace(/title="[^"]*"/g, "");
    expect(visible).not.toContain("14:05:09");
  });

  it("lives inside the card's <details> as its first item (CEO 2026-10-03), text-xs and not darker than neutral-400", () => {
    const html = render([position(1, price("2026-10-02"))]);
    const sentenceIndex = html.indexOf("估值基準：");
    expect(sentenceIndex).toBeGreaterThan(html.indexOf("NT$"));
    expect(sentenceIndex).toBeLessThan(html.indexOf("未實現損益"));
    const open = html.lastIndexOf("<p", sentenceIndex);
    const tag = html.slice(open, html.indexOf(">", open));
    expect(tag).toContain("text-xs");
    expect(tag).toContain("text-neutral-400");
    expect(tag).not.toMatch(/text-neutral-(500|600|700)/);
    // a <details> encloses it, and the sentence is its first content after <summary>
    const before = html.slice(0, sentenceIndex);
    expect(before.split("<details").length).toBe(before.split("</details>").length + 1);
    const detailsStart = before.lastIndexOf("<details");
    const afterSummary = html.slice(html.indexOf("</summary>", detailsStart) + "</summary>".length);
    expect(afterSummary.startsWith("<p")).toBe(true);
    expect(afterSummary.indexOf("估值基準：")).toBeLessThan(afterSummary.indexOf("</details>"));
  });

  it("main view (everything outside <details>) never shows the basis sentence or the response time", () => {
    const html = render([position(1, price("2026-10-02"))]);
    const mainView = html.replace(/<details[\s\S]*?<\/details>/g, "");
    expect(mainView).not.toContain("估值基準");
    expect(mainView).not.toContain("資料時間");
    expect(mainView).not.toContain("14:05:09");
  });

  it("empty state: no positions, or no priced positions, shows no basis sentence", () => {
    expect(render([])).not.toContain("估值基準");
    expect(render([position(1, null)])).not.toContain("估值基準");
    expect(render([])).not.toContain("資料時間");
  });

  it("an unusable response timestamp keeps the sentence but drops the tooltip", () => {
    const html = render([position(1, price("2026-10-02"))], "garbage");
    expect(html).toContain("估值基準：1 檔皆為收盤價（10/02）");
    expect(html).not.toContain("各檔價格旁標示");
  });

  it("wiring: SummaryCards reads the sentence builders, never the PENDING or ALLOWED exports", () => {
    const src = readFileSync(fileURLToPath(new URL("../../components/SummaryCards.tsx", import.meta.url)), "utf8");
    const lib = readFileSync(fileURLToPath(new URL("../valuationBasis.ts", import.meta.url)), "utf8");
    expect(src).toContain("buildBasisSentence(basis)");
    expect(lib).toContain("C3_3_BASIS_ALL_CLOSE_SINGLE");
    expect(lib).toContain("C3_3_BASIS_ALL_CLOSE_RANGE");
    expect(lib).toContain("C5_1_TOOLTIP_SENTENCE_1");
    expect(lib).toContain("C5_1_TOOLTIP_SENTENCE_2");
    expect(src + lib).not.toMatch(/PENDING_PRECONDITION|INTRADAY_ALLOWED_SENTENCES/);
  });
});

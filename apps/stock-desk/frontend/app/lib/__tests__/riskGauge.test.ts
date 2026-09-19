import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";
import {
  buildLimitGaugeViewModel,
  buildSourcesSummaryViewModel,
  limitBarWidthPercent,
  shouldShowLimitBar,
} from "../riskGauge";
import { RiskGaugeView } from "../../components/RiskGauge";
import type { BookLimitCheck, PortfolioLimitsResponse, SymbolDataMeta } from "../types";

function makeSource(symbol: string, status: string): SymbolDataMeta {
  return {
    symbol,
    market: "TW",
    data: {
      status,
      source: "twse",
      staleness_minutes: null,
      is_within_ttl: null,
      bar_count: 100,
      first_bar_date: "2026-01-01",
      last_bar_date: "2026-08-08",
      trading_days_behind: null,
      reason: null,
    },
  };
}

function makeCheck(overrides: Partial<BookLimitCheck>): BookLimitCheck {
  return {
    index: 1,
    limit_id: "single_position_weight",
    name: "單一標的佔比上限",
    status: "passed",
    observed: 0.05,
    threshold: 0.2,
    detail: "detail",
    worst_symbol: "2330",
    evaluated_count: 3,
    excluded: [],
    ...overrides,
  };
}

describe("shouldShowLimitBar", () => {
  it("never draws a bar when the cap is not_evaluable, even with a real threshold", () => {
    expect(shouldShowLimitBar("not_evaluable", 0.2)).toBe(false);
  });

  it("does not draw a bar when threshold is null (defensive, cap 5)", () => {
    expect(shouldShowLimitBar("passed", null)).toBe(false);
    expect(shouldShowLimitBar("violated", null)).toBe(false);
  });

  it("does not draw a bar when threshold is zero or negative", () => {
    expect(shouldShowLimitBar("passed", 0)).toBe(false);
    expect(shouldShowLimitBar("passed", -0.1)).toBe(false);
  });

  it("draws a bar for a passed or violated cap with a real positive threshold", () => {
    expect(shouldShowLimitBar("passed", 0.2)).toBe(true);
    expect(shouldShowLimitBar("violated", 0.2)).toBe(true);
  });
});

describe("limitBarWidthPercent", () => {
  it("is 0 when observed is null", () => {
    expect(limitBarWidthPercent(null, 0.2)).toBe(0);
  });

  it("is 0 when threshold is null or non-positive", () => {
    expect(limitBarWidthPercent(0.1, null)).toBe(0);
    expect(limitBarWidthPercent(0.1, 0)).toBe(0);
    expect(limitBarWidthPercent(0.1, -0.5)).toBe(0);
  });

  it("computes the observed/threshold ratio as a percentage", () => {
    expect(limitBarWidthPercent(0.05, 0.2)).toBe(25);
    expect(limitBarWidthPercent(0.1, 0.2)).toBe(50);
  });

  it("clamps at 100 when observed has reached or passed threshold (violated)", () => {
    expect(limitBarWidthPercent(0.2, 0.2)).toBe(100);
    expect(limitBarWidthPercent(0.5, 0.2)).toBe(100);
  });

  it("floors at 0 for a negative observed value", () => {
    expect(limitBarWidthPercent(-0.1, 0.2)).toBe(0);
  });
});

describe("buildLimitGaugeViewModel", () => {
  it("a not_evaluable check never shows a bar, regardless of excluded symbols", () => {
    const check = makeCheck({
      status: "not_evaluable",
      observed: null,
      threshold: null,
      worst_symbol: null,
      evaluated_count: 0,
      excluded: [
        { symbol: "2330", market: "TW", reason: "no unvalued reason" },
        { symbol: "AAPL", market: "US", reason: "another reason" },
      ],
    });
    const view = buildLimitGaugeViewModel(check);
    expect(view.showBar).toBe(false);
    expect(view.barWidthPercent).toBe(0);
    expect(view.hasExcluded).toBe(true);
    expect(view.excludedCount).toBe(2);
  });

  it("a not_evaluable check with a borrowed (non-null) threshold still shows no bar", () => {
    // Mirrors app/advice/book_limits.py::_aggregate: the empty-comparable
    // branch borrows `baseline.threshold` even though status is
    // not_evaluable — this must not accidentally satisfy shouldShowLimitBar.
    const check = makeCheck({ status: "not_evaluable", observed: null, threshold: 0.2 });
    const view = buildLimitGaugeViewModel(check);
    expect(view.showBar).toBe(false);
    expect(view.barWidthPercent).toBe(0);
  });

  it("a passed check with no excluded symbols shows a bar and reports zero exclusions", () => {
    const check = makeCheck({ status: "passed", observed: 0.1, threshold: 0.2, excluded: [] });
    const view = buildLimitGaugeViewModel(check);
    expect(view.showBar).toBe(true);
    expect(view.barWidthPercent).toBe(50);
    expect(view.hasExcluded).toBe(false);
    expect(view.excludedCount).toBe(0);
  });

  it("a violated check with a null threshold (defensive) still shows no bar", () => {
    const check = makeCheck({ status: "violated", observed: 0.3, threshold: null });
    const view = buildLimitGaugeViewModel(check);
    expect(view.showBar).toBe(false);
    expect(view.barWidthPercent).toBe(0);
  });
});

describe("buildSourcesSummaryViewModel", () => {
  it("reports no warning when every source is fresh", () => {
    const view = buildSourcesSummaryViewModel([
      makeSource("2330", "fresh"),
      makeSource("2454", "fresh"),
    ]);
    expect(view.allFresh).toBe(true);
    expect(view.staleCount).toBe(0);
  });

  it("reports the stale count when one source is not fresh", () => {
    const view = buildSourcesSummaryViewModel([
      makeSource("2330", "fresh"),
      makeSource("2454", "cached_stale"),
    ]);
    expect(view.allFresh).toBe(false);
    expect(view.staleCount).toBe(1);
  });

  it("counts every non-fresh status (backup/cached_stale/unavailable), not just one kind", () => {
    const view = buildSourcesSummaryViewModel([
      makeSource("2330", "backup"),
      makeSource("2454", "cached_stale"),
      makeSource("AAPL", "unavailable"),
      makeSource("2603", "fresh"),
    ]);
    expect(view.allFresh).toBe(false);
    expect(view.staleCount).toBe(3);
  });

  it("an empty source list counts as all-fresh (no warning)", () => {
    const view = buildSourcesSummaryViewModel([]);
    expect(view.allFresh).toBe(true);
    expect(view.staleCount).toBe(0);
  });
});

/**
 * `RiskGaugeView` rendering coverage (首頁「一眼一句」簡化 §3.2/§4,
 * `work/stock-desk-一眼一句-實作規格.md`): the five-row grid must show
 * name/status/observed for every cap, must never draw a progress bar for a
 * `not_evaluable` cap (H1), and must render `worst_symbol` on the same row
 * (H3) when present.
 */
function makeFullCheck(overrides: Partial<BookLimitCheck>): BookLimitCheck {
  return {
    index: 1,
    limit_id: "single_position_weight",
    name: "單一標的佔比上限",
    status: "passed",
    observed: 0.05,
    threshold: 0.2,
    detail: "detail sentence",
    worst_symbol: null,
    evaluated_count: 3,
    excluded: [],
    ...overrides,
  };
}

const FIVE_CHECKS: BookLimitCheck[] = [
  makeFullCheck({
    index: 1,
    limit_id: "single_position_weight",
    name: "單一標的佔比上限",
    status: "passed",
    observed: 0.05,
    threshold: 0.2,
    worst_symbol: "2330",
  }),
  makeFullCheck({
    index: 2,
    limit_id: "sector_weight",
    name: "單一產業佔比上限",
    status: "violated",
    observed: 0.3,
    threshold: 0.25,
    worst_symbol: "2454",
    excluded: [{ symbol: "AAPL", market: "US", reason: "no sector data" }],
  }),
  makeFullCheck({
    index: 3,
    limit_id: "gross_exposure",
    name: "總曝險上限",
    status: "passed",
    observed: 0.4,
    threshold: 1,
    worst_symbol: null,
  }),
  makeFullCheck({
    index: 4,
    limit_id: "per_trade_loss",
    name: "單筆最大可承受虧損",
    status: "not_evaluable",
    observed: null,
    threshold: null,
    worst_symbol: null,
  }),
  makeFullCheck({
    index: 5,
    limit_id: "kelly_fraction",
    name: "分數 Kelly 部位上限",
    status: "not_evaluable",
    observed: null,
    threshold: null,
    worst_symbol: null,
  }),
];

const FAKE_LIMITS: PortfolioLimitsResponse = {
  limits: FIVE_CHECKS,
  notes: ["假設一", "假設二"],
  sources: [
    {
      symbol: "2330",
      market: "TW",
      data: {
        status: "fresh",
        source: "twse",
        staleness_minutes: null,
        is_within_ttl: null,
        bar_count: 100,
        first_bar_date: "2026-01-01",
        last_bar_date: "2026-09-18",
        trading_days_behind: null,
        reason: null,
      },
    },
  ],
  as_of: "2026-09-19T00:00:00Z",
};

function renderRiskGaugeView(data: PortfolioLimitsResponse): string {
  return renderToStaticMarkup(createElement(RiskGaugeView, { data }));
}

describe("RiskGaugeView — 五列一行式渲染（實作規格 §3.2/§4）", () => {
  it("every one of the five rows contains its name, status label and observed value", () => {
    const html = renderRiskGaugeView(FAKE_LIMITS);
    for (const check of FIVE_CHECKS) {
      expect(html).toContain(`第 ${check.index} 條・${check.name}`);
    }
    expect(html).toContain("通過");
    expect(html).toContain("已違反");
    expect(html).toContain("無法評估");
    // observed/threshold pairs, e.g. 5.00%／20.00%
    expect(html).toMatch(/5\.00%／20\.00%/);
    expect(html).toMatch(/30\.00%／25\.00%/);
  });

  it("H1: a not_evaluable row never draws a progressbar, even alongside rows that do", () => {
    const html = renderRiskGaugeView(FAKE_LIMITS);
    const progressbarCount = (html.match(/role="progressbar"/g) ?? []).length;
    // Only the three non-not_evaluable checks (passed/violated/passed) draw a bar.
    expect(progressbarCount).toBe(3);
  });

  it("H3: worst_symbol renders on the same row as its cap, right after that row's markup", () => {
    const html = renderRiskGaugeView(FAKE_LIMITS);
    const row1Index = html.indexOf("第 1 條・單一標的佔比上限");
    const row2Index = html.indexOf("第 2 條・單一產業佔比上限");
    const worstSymbolIndex = html.indexOf("觀測值最高：2330");
    expect(worstSymbolIndex).toBeGreaterThan(row1Index);
    expect(worstSymbolIndex).toBeLessThan(row2Index);
    // A cap with no worst_symbol must not fabricate one.
    const row3Index = html.indexOf("第 3 條・總曝險上限");
    const row4Index = html.indexOf("第 4 條・單筆最大可承受虧損");
    expect(html.slice(row3Index, row4Index)).not.toContain("觀測值最高");
  });

  it("H2: the excluded-count badge shows on the row that has exclusions, not elsewhere", () => {
    const html = renderRiskGaugeView(FAKE_LIMITS);
    expect(html).toContain("未納入 1 檔");
  });

  it("H4 頂部說明句與 H5 details summary 不在此純呈現元件內（由外層 RiskGauge 負責），但詳細 summary 入口字存在", () => {
    const html = renderRiskGaugeView(FAKE_LIMITS);
    expect(html).toContain("詳細：各項判定依據、假設與資料來源");
  });
});

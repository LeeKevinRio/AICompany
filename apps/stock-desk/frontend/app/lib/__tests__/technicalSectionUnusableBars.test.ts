/**
 * RC-695 (RC-764 ~ RC-770): when ANY daily bar holds a bad close / high / low,
 * the technical-analysis section collapses to ONE sentence. These tests lock
 * the final wording, the shared verdict, and the exact collapse / keep scope.
 * Whole-page harness = seeded React Query cache (same as
 * `entryObservationPending.test.ts`); only next/navigation and next/dynamic
 * are mocked.
 */
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it, vi } from "vitest";
import { TECHNICAL_SECTION_NO_DATA_STATEMENT, evaluateDailyBarsUsability } from "../dailyBarsUsability";
import { computeKeyLevels } from "../keyLevels";
import { KEY_LEVELS_NO_DATA_STATEMENT } from "../../position/[symbol]/KeyLevelsPanel";
import { IndicatorOverviewChipsRow, TechnicalIndicatorsPanel } from "../../position/[symbol]/TechnicalIndicatorsPanel";
import type { Bar, BarsResponse, DataMeta, IndicatorResult, PositionsResponse, SignalsResponse } from "../types";

vi.mock("next/navigation", () => ({
  useParams: () => ({ symbol: "2330" }),
  useSearchParams: () => new URLSearchParams("market=TW"),
}));
vi.mock("next/dynamic", () => ({ default: () => () => null }));

const { default: PositionDetailPage } = await import("../../position/[symbol]/page");

const FINAL_STATEMENT = "目前沒有可用的日線資料，技術分析區的圖表與指標不顯示。";
const CHART_LABEL = 'aria-label="日K線與均線圖"';
const SOURCES_PREFIX = "資料來源：";
const BANNED_WORDS = ["資料錯誤", "損壞", "重新抓取", "暫", "恢復"];

const META: DataMeta = {
  status: "cached_stale",
  source: "demo_synthetic",
  staleness_minutes: 1,
  is_within_ttl: false,
  bar_count: 100,
  first_bar_date: "2026-01-01",
  last_bar_date: "2026-04-12",
  trading_days_behind: null,
  reason: null,
};

function goodBars(): Bar[] {
  return Array.from({ length: 100 }, (_, i) => ({
    date: `2026-0${1 + Math.floor(i / 28)}-${String(1 + (i % 28)).padStart(2, "0")}`,
    open: "900",
    high: "930",
    low: "890",
    close: String(900 + (i % 9) * 2),
    volume: 1000,
    currency: "TWD",
    source: "demo_synthetic",
  }));
}

function withBad(field: "close" | "high" | "low", value: string, index = 40): Bar[] {
  return goodBars().map((b, i) => (i === index ? { ...b, [field]: value } : b));
}

function barsResponse(bars: Bar[]): BarsResponse {
  return { symbol: "2330", market: "TW", status: "ok", reason: null, data: META, as_of: "x", bars };
}

function indicator(name: string, last: Record<string, number>, series: Record<string, (number | null)[]> = {}): IndicatorResult {
  const dates = goodBars().map((b) => b.date);
  return { name, status: "ok", params: {}, dates, series, last, inputs_used: {}, as_of: null, source: null } as unknown as IndicatorResult;
}

const SIGNALS: SignalsResponse = {
  symbol: "2330",
  market: "TW",
  status: "ok",
  reason: null,
  data: META,
  as_of: "x",
  signals: {
    symbol: "2330",
    bar_count: 100,
    as_of: null,
    source: null,
    technical: {
      moving_averages: indicator("moving_averages", { ma_5: 905, ma_20: 906, ma_60: 904 }, {
        ma_5: goodBars().map(() => 905),
        ma_20: goodBars().map(() => 906),
        ma_60: goodBars().map(() => 904),
      }),
      rsi: indicator("rsi", { rsi: 52 }),
      macd: indicator("macd", { macd: 1.2, signal: 1.0, histogram: 0.2 }),
      bollinger: indicator("bollinger", { upper: 920, middle: 906, lower: 892, bandwidth: 0.03, percent_b: 0.5 }),
      atr: indicator("atr", { atr: 12 }),
      kd: indicator("kd", { k: 50, d: 48 }),
      volume_zscore: indicator("volume_zscore", { zscore: 0.3, anomaly: 0 }),
    },
  },
};

const SIGNALS_INSUFFICIENT_REASON = "SIGNALS-INSUFFICIENT-SENTINEL";
const SIGNALS_INSUFFICIENT: SignalsResponse = {
  ...SIGNALS,
  status: "insufficient_data",
  reason: SIGNALS_INSUFFICIENT_REASON,
  signals: null,
};

const NO_POSITIONS: PositionsResponse = { items: [], as_of: "x" };

function renderPage(seed: { bars?: BarsResponse; signals?: SignalsResponse; barsRefetchFailed?: boolean }): string {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  if (seed.bars) client.setQueryData(["bars", "2330", "TW"], seed.bars);
  if (seed.bars && seed.barsRefetchFailed) {
    // A failed refetch: status "error" while the previous (stale) data stays in the cache.
    client.getQueryCache().find({ queryKey: ["bars", "2330", "TW"] })!.setState({ status: "error", error: new Error("refetch failed") });
  }
  if (seed.signals) client.setQueryData(["signals", "2330", "TW"], seed.signals);
  client.setQueryData(["positions"], NO_POSITIONS);
  return renderToStaticMarkup(createElement(QueryClientProvider, { client }, createElement(PositionDetailPage)));
}

function count(haystack: string, needle: string): number {
  return haystack.split(needle).length - 1;
}

const BAD_CASES: Array<[string, Bar[]]> = [
  ["close 0", withBad("close", "0")],
  ["high -1", withBad("high", "-1")],
  ["low 0", withBad("low", "0")],
  ["close non-numeric string", withBad("close", "abc")],
];

describe("RC-695 wording constant (RC-764, RC-770 item 1)", () => {
  it("is the final sentence, byte for byte", () => {
    expect(TECHNICAL_SECTION_NO_DATA_STATEMENT).toBe(FINAL_STATEMENT);
  });

  it("shares the leading clause with KEY_LEVELS_NO_DATA_STATEMENT", () => {
    const prefix = "目前沒有可用的日線資料";
    expect(TECHNICAL_SECTION_NO_DATA_STATEMENT.startsWith(prefix)).toBe(true);
    expect(KEY_LEVELS_NO_DATA_STATEMENT.startsWith(prefix)).toBe(true);
  });

  it("carries none of the banned causal / recovery words (RC-770 item 4)", () => {
    for (const word of BANNED_WORDS) expect(TECHNICAL_SECTION_NO_DATA_STATEMENT).not.toContain(word);
  });
});

describe("evaluateDailyBarsUsability (RC-767, RC-770 item 2)", () => {
  const badValues = ["NaN", "Infinity", "-Infinity", "0", "-1", "abc", ""];
  for (const field of ["close", "high", "low"] as const) {
    for (const value of badValues) {
      it(`${field} = ${JSON.stringify(value)} makes the whole batch unusable`, () => {
        expect(evaluateDailyBarsUsability(withBad(field, value))).toEqual({ status: "unusable" });
      });
    }
  }

  it("a clean batch is usable", () => {
    expect(evaluateDailyBarsUsability(goodBars())).toEqual({ status: "usable" });
  });

  it("a bad open / volume alone does not matter (only close, high, low are checked)", () => {
    const bars = goodBars().map((b, i) => (i === 3 ? { ...b, open: "0", volume: 0 } : b));
    expect(evaluateDailyBarsUsability(bars)).toEqual({ status: "usable" });
  });

  it("agrees with the computeKeyLevels refusal on every bad case and on the good batch", () => {
    for (const [, bars] of BAD_CASES) {
      expect(computeKeyLevels(bars) === null).toBe(evaluateDailyBarsUsability(bars).status === "unusable");
    }
    expect(computeKeyLevels(goodBars())).not.toBeNull();
  });
});

describe("whole page with a bad bar (RC-764, RC-770 items 3 and 4)", () => {
  const normal = renderPage({ bars: barsResponse(goodBars()), signals: SIGNALS });
  const chipsHtml = renderToStaticMarkup(createElement(IndicatorOverviewChipsRow, { payload: SIGNALS.signals! }));
  const cardsHtml = renderToStaticMarkup(
    createElement(TechnicalIndicatorsPanel, { payload: SIGNALS.signals!, lastBarDate: META.last_bar_date }),
  );

  it("sanity: the normal page really contains everything the collapsed page must drop", () => {
    expect(chipsHtml.length).toBeGreaterThan(0);
    expect(cardsHtml.length).toBeGreaterThan(0);
    expect(normal).toContain(CHART_LABEL);
    expect(normal).toContain(chipsHtml);
    expect(normal).toContain(cardsHtml);
    expect(normal).toContain("近 100 根日線，收盤");
    expect(normal).toContain("共 100 根日線");
    expect(normal).not.toContain(FINAL_STATEMENT);
  });

  for (const [name, bars] of BAD_CASES) {
    it(`${name}: the sentence appears once; chart, chips, cards, one-liner and bar-count line are gone`, () => {
      const html = renderPage({ bars: barsResponse(bars), signals: SIGNALS });
      expect(count(html, FINAL_STATEMENT)).toBe(1);
      expect(html).not.toContain(CHART_LABEL);
      expect(html).not.toContain(chipsHtml);
      expect(html).not.toContain(cardsHtml);
      expect(html).not.toContain("近 100 根日線");
      expect(html).not.toContain("共 100 根日線");
      expect(html).toContain(`<p class="mt-3 text-sm text-neutral-400">${FINAL_STATEMENT}</p>`);
    });
  }

  it("keeps the <details>, both source lines with full badges, and the footer guidance", () => {
    const html = renderPage({ bars: barsResponse(withBad("close", "0")), signals: SIGNALS });
    expect(html).toContain("<details");
    expect(count(html, SOURCES_PREFIX)).toBe(count(normal, SOURCES_PREFIX));
    expect(count(html, SOURCES_PREFIX)).toBeGreaterThanOrEqual(2);
    // Compact title badges and full badges all stay: same badge count as the normal page.
    expect(count(html, "demo_synthetic")).toBe(count(normal, "demo_synthetic"));
    const guidance = normal.match(/<p class="text-sm text-neutral-300">[^<]+<\/p>/);
    expect(guidance).not.toBeNull();
    expect(html).toContain(guidance![0]);
  });

  it("signals insufficient panel also collapses (it is part of the collapsed area)", () => {
    const html = renderPage({ bars: barsResponse(withBad("close", "0")), signals: SIGNALS_INSUFFICIENT });
    expect(html).not.toContain(SIGNALS_INSUFFICIENT_REASON);
    expect(count(html, FINAL_STATEMENT)).toBe(1);
    // Same response on a clean batch does show the panel, so the absence above is meaningful.
    expect(renderPage({ bars: barsResponse(goodBars()), signals: SIGNALS_INSUFFICIENT })).toContain(SIGNALS_INSUFFICIENT_REASON);
  });

  it("signals still pending: no skeleton inside the collapsed section", () => {
    const collapsed = renderPage({ bars: barsResponse(withBad("close", "0")) });
    const clean = renderPage({ bars: barsResponse(goodBars()) });
    // Other sections use the same skeleton class, so compare counts: exactly the details skeleton is gone.
    expect(count(clean, "h-40 w-full") - count(collapsed, "h-40 w-full")).toBe(1);
  });

  it("introduces none of the banned words beyond what the normal page already has (RC-770 item 4)", () => {
    const html = renderPage({ bars: barsResponse(withBad("close", "0")), signals: SIGNALS });
    for (const word of BANNED_WORDS) expect(count(html, word), word).toBeLessThanOrEqual(count(normal, word));
  });

  it("no H1 (gap) wording appears (RC-767)", () => {
    const html = renderPage({ bars: barsResponse(withBad("close", "0")), signals: SIGNALS });
    for (const word of ["跳空", "公司行動", "已除權"]) expect(html).not.toContain(word);
  });
});

describe("unchanged branches (RC-764, RC-770 item 5)", () => {
  it("bars query in isError while keeping stale BAD data: details stay as in today's error state, no statement", () => {
    const html = renderPage({ bars: barsResponse(withBad("close", "0")), signals: SIGNALS, barsRefetchFailed: true });
    expect(html).not.toContain(FINAL_STATEMENT);
    expect(html).not.toContain(CHART_LABEL);
    // The details area is not half-collapsed: cards and the bar-count line show as before.
    expect(html).toContain(renderToStaticMarkup(createElement(TechnicalIndicatorsPanel, { payload: SIGNALS.signals!, lastBarDate: META.last_bar_date })));
    // The bar-count line is gated by bars.isSuccess, so in the error state it is absent exactly as before this change.
    expect(html).not.toContain("共 100 根日線");
    expect(html).toContain("無法載入日K線");
  });

  it("bars still loading: no statement", () => {
    expect(renderPage({ signals: SIGNALS })).not.toContain(FINAL_STATEMENT);
  });

  it("bars insufficient_data: the insufficient panel shows, no statement", () => {
    const html = renderPage({
      bars: { ...barsResponse([]), status: "insufficient_data", reason: "BARS-INSUFFICIENT-SENTINEL" },
      signals: SIGNALS,
    });
    expect(html).toContain("BARS-INSUFFICIENT-SENTINEL");
    expect(html).not.toContain(FINAL_STATEMENT);
  });

  it("a clean batch renders the chart label, one-liner and bar-count line, and never the statement", () => {
    const html = renderPage({ bars: barsResponse(goodBars()), signals: SIGNALS });
    expect(html).toContain(CHART_LABEL);
    expect(html).toContain("近 100 根日線，收盤");
    expect(html).toContain("共 100 根日線");
    expect(html).not.toContain(FINAL_STATEMENT);
  });

  it("page.tsx and keyLevels.ts read the shared verdict instead of re-deriving the rule", () => {
    const src = readFileSync(fileURLToPath(new URL("../../position/[symbol]/page.tsx", import.meta.url)), "utf8");
    expect(src).toContain("evaluateDailyBarsUsability(bars.data.bars)");
    expect(src).toContain("TECHNICAL_SECTION_NO_DATA_STATEMENT");
    expect(src).not.toContain("Number.isFinite");
    const keyLevelsSrc = readFileSync(fileURLToPath(new URL("../keyLevels.ts", import.meta.url)), "utf8");
    expect(keyLevelsSrc).toContain("evaluateDailyBarsUsability(bars)");
  });
});

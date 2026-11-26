/**
 * RC-841 permanent lock (risk-gate RC-840 to RC-845; RC-844 item 4).
 *
 * With a CLEAN daily-bar batch, the technical-analysis section of the position
 * page must render exactly what it rendered before RC-695 (the collapse on bad
 * bars) was merged. The block HTML is pinned in a snapshot whose baseline was
 * produced from the pre-RC-695 sources (base 872adcc1) and verified equal to
 * the current output when this test was added.
 *
 * Bar counts are NOT hard-coded: the digits in the "近 N 根日線" / "共 N 根日線"
 * lines are normalised before the snapshot comparison and asserted by regex.
 * Whole-page harness = seeded React Query cache, same as
 * `technicalSectionUnusableBars.test.ts`.
 */
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it, vi } from "vitest";
import { TECHNICAL_SECTION_NO_DATA_STATEMENT } from "../dailyBarsUsability";
import { TECHNICAL_ANALYSIS_TITLE } from "../sectionTitles";
import type { Bar, BarsResponse, DataMeta, IndicatorResult, PositionsResponse, SignalsResponse } from "../types";

vi.mock("next/navigation", () => ({
  useParams: () => ({ symbol: "2330" }),
  useSearchParams: () => new URLSearchParams("market=TW"),
}));
vi.mock("next/dynamic", () => ({ default: () => () => null }));

const { default: PositionDetailPage } = await import("../../position/[symbol]/page");

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

const NO_POSITIONS: PositionsResponse = { items: [], as_of: "x" };

function renderCleanPage(bars: Bar[]): string {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  const barsResponse: BarsResponse = { symbol: "2330", market: "TW", status: "ok", reason: null, data: META, as_of: "x", bars };
  client.setQueryData(["bars", "2330", "TW"], barsResponse);
  client.setQueryData(["signals", "2330", "TW"], SIGNALS);
  client.setQueryData(["positions"], NO_POSITIONS);
  return renderToStaticMarkup(createElement(QueryClientProvider, { client }, createElement(PositionDetailPage)));
}

/** The technical-analysis `<section>` block: from its opening tag to the first closing tag after the title. */
function technicalSectionHtml(page: string): string {
  const titleAt = page.indexOf(`>${TECHNICAL_ANALYSIS_TITLE}</h2>`);
  expect(titleAt, "technical section title present").toBeGreaterThan(-1);
  const start = page.lastIndexOf("<section", titleAt);
  const end = page.indexOf("</section>", titleAt);
  expect(start).toBeGreaterThan(-1);
  expect(end).toBeGreaterThan(titleAt);
  return page.slice(start, end + "</section>".length);
}

/** Replace only the bar-count digits so the snapshot does not pin a fixture size. */
function normaliseBarCounts(html: string): string {
  return html.replace(/(近|共) \d+ 根日線/g, "$1 N 根日線");
}

describe("RC-841 permanent lock: clean daily bars leave the technical section unchanged", () => {
  const section = technicalSectionHtml(renderCleanPage(goodBars()));

  it("matches the pre-RC-695 block HTML (snapshot, bar counts normalised)", () => {
    expect(normaliseBarCounts(section)).toMatchSnapshot();
  });

  it("bar-count lines are present as /近 \\d+ 根日線/ and /共 \\d+ 根日線/, whatever the fixture size", () => {
    expect(section).toMatch(/近 \d+ 根日線/);
    expect(section).toMatch(/共 \d+ 根日線/);
    const shorter = technicalSectionHtml(renderCleanPage(goodBars().slice(0, 70)));
    expect(shorter).toMatch(/近 70 根日線/);
  });

  it("never carries the collapse sentence", () => {
    expect(section).not.toContain(TECHNICAL_SECTION_NO_DATA_STATEMENT);
  });

  it("the lock is not vacuous: the pinned block holds the chart, chips, one-liner and cards", () => {
    expect(section).toContain('aria-label="日K線與均線圖"');
    expect(section).toContain("<details");
    expect(section.length).toBeGreaterThan(1000);
  });
});

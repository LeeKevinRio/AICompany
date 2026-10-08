/**
 * F-7 price-unit chip guard (risk F7-R1..R10, art-lead opinion section 3).
 *
 * Source-text checks read the component files; markup checks render the real
 * components with `renderToStaticMarkup` (the project has no DOM environment),
 * and the page-level checks render the whole stock page against a pre-seeded
 * React Query cache with only `next/navigation` and `next/dynamic` mocked.
 *
 * Known exceptions to "every printed price has a unit" (F7-R5) are listed in
 * `PRICE_WITHOUT_CHIP_EXCEPTIONS` below and each is asserted to still exist.
 */

import { readdirSync, readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it, vi } from "vitest";
import type {
  AdviceCard,
  AdviceResponse,
  Bar,
  BarsResponse,
  DataMeta,
  PositionsResponse,
  SignalsResponse,
} from "../types";
import {
  PRICE_UNIT_BADGE_CLASS,
  PRICE_UNIT_LABEL_TWD,
  PRICE_UNIT_LABEL_USD,
  PRICE_UNIT_MARKET_ONLY,
  PriceUnitBadge,
  resolvePriceUnitLabel,
} from "../../position/[symbol]/PriceUnitBadge";
import { DecisionCardBody } from "../../position/[symbol]/DecisionCard";
import { KEY_LEVELS_PANEL_TITLE, KeyLevelsPanel } from "../../position/[symbol]/KeyLevelsPanel";
import { EntryObservationPanel } from "../../position/[symbol]/EntryObservationPanel";
import { evaluateEntryObservation } from "../entryObservation";
import { ENTRY_E1_QUALIFIER, ENTRY_PANEL_TITLE } from "../entryObservationWording";
import { computeKeyLevels } from "../keyLevels";
import { DECISION_CARD_ARIA_LABEL } from "../decisionCardWording";
import { TECHNICAL_ANALYSIS_TITLE } from "../sectionTitles";
import { MARKET_CURRENCY } from "../currencyMarket";

/* ---------------------------------------------------------------- page mocks */

const nav = vi.hoisted(() => ({ market: "US" }));
vi.mock("next/navigation", () => ({
  useParams: () => ({ symbol: "AAPL" }),
  useSearchParams: () => new URLSearchParams(`market=${nav.market}`),
}));
vi.mock("next/dynamic", () => ({ default: () => () => null }));

const { default: PositionDetailPage } = await import("../../position/[symbol]/page");

/* ------------------------------------------------------------------ fixtures */

const APP_DIR = fileURLToPath(new URL("../../", import.meta.url));
const POSITION_DIR = "position/[symbol]";
const read = (rel: string) => readFileSync(`${APP_DIR}${rel}`, "utf8");
const stripComments = (src: string) => src.replace(/\/\*[\s\S]*?\*\//g, "").replace(/^\s*\/\/.*$/gm, "");

function makeBars(n: number, currency = "USD"): Bar[] {
  return Array.from({ length: n }, (_, i) => ({
    date: `2026-0${1 + Math.floor(i / 28)}-${String(1 + (i % 28)).padStart(2, "0")}`,
    open: "100",
    high: "105",
    low: "95",
    close: String(100 + (i % 7)),
    volume: 1000,
    currency,
    source: "demo",
  }));
}

/** 100 bars, with the one bar at `at` carrying a different currency. */
function barsWithOneOdd(odd: string, base = "USD", at = 40): Bar[] {
  return makeBars(100, base).map((b, i) => (i === at ? { ...b, currency: odd } : b));
}

const META: DataMeta = {
  status: "cached_stale",
  source: "demo",
  staleness_minutes: 5,
  is_within_ttl: true,
  bar_count: 100,
  first_bar_date: "2026-01-01",
  last_bar_date: "2026-04-12",
  trading_days_behind: null,
  reason: null,
};

function makeCard(): AdviceCard {
  return {
    symbol: "AAPL",
    action: "add",
    quantity_range: {
      min_shares: 5,
      max_shares: 10,
      restores_compliance: true,
      basis: "basis sentence",
    },
    matched_rules: [
      {
        id: "uptrend_ma_stack",
        name: "ma stack",
        action: "add",
        weight: 0.5,
        weight_meaning: "weight is rule priority",
        explanation: "explanation",
        invalidation: null,
      },
    ],
    counterarguments: [],
    invalidation_conditions: [],
    confidence: "medium",
    confidence_meaning: "confidence meaning",
    rules_version: "1.0.2",
    as_of: "2026-09-18T09:00:00+08:00",
    observation_window: { start: "2025-05-01", end: "2026-09-18", bars: 300 },
    disclaimer: "disclaimer",
    limits_check: [],
    action_weights: [],
    direction_weights: [],
    has_conflict: false,
    aggregated_action: "add",
    blocked_action: null,
    blocked_notices: [],
    downgrade_notices: [],
    evaluation: { total_rules: 1, evaluated_rules: 1, matched_rules: 1, data_completeness: 1, skipped_rules: [] },
  };
}

function makeAdvice(overrides: Partial<AdviceResponse> = {}): AdviceResponse {
  return {
    symbol: "AAPL",
    market: "US",
    status: "ok",
    reason: null,
    as_of: "2026-09-18T09:00:00+08:00",
    held: false,
    position_ids: [],
    portfolio_context: {
      symbol: "AAPL",
      total_equity_twd: null,
      position_market_value_twd: null,
      position_cost_twd: null,
      gross_exposure_twd: null,
      net_worth: null,
      book_fully_valued: null,
      quantity: null,
      close: null,
      fx_to_twd: 1,
      atr: null,
      sector: null,
      sector_market_value_twd: null,
      win_rate: null,
      payoff_ratio: null,
    },
    context_notes: [],
    advice: makeCard(),
    data: META,
    ...overrides,
  };
}

function barsResponse(bars: Bar[], status: "ok" | "insufficient_data" = "ok"): BarsResponse {
  return { symbol: "AAPL", market: "US", status, reason: status === "ok" ? null : "not enough", data: META, as_of: "x", bars };
}

const SIGNALS_OK: SignalsResponse = {
  symbol: "AAPL",
  market: "US",
  status: "ok",
  reason: null,
  data: META,
  as_of: "x",
  signals: { symbol: "AAPL", bar_count: 100, as_of: null, source: null },
};

const NO_POSITIONS: PositionsResponse = { items: [], as_of: "x" };

const chipHtml = (label: string) => `<span class="${PRICE_UNIT_BADGE_CLASS}">${label}</span>`;
const countOf = (html: string, needle: string) => html.split(needle).length - 1;
const FIRST_PRICE = /\d+\.\d{2}\b/;

function renderBody(
  props: Omit<Parameters<typeof DecisionCardBody>[0], "response" | "anchorSource" | "avgCost"> &
    Partial<Pick<Parameters<typeof DecisionCardBody>[0], "response" | "anchorSource" | "avgCost">>,
): string {
  return renderToStaticMarkup(
    createElement(DecisionCardBody, {
      response: makeAdvice(),
      anchorSource: "close-not-held",
      avgCost: null,
      ...props,
    }),
  );
}

function renderKeyLevels(bars: Bar[], market: string | undefined): string {
  return renderToStaticMarkup(
    createElement(KeyLevelsPanel, { bars, avgCost: null, anchorSource: "close-not-held", market }),
  );
}

function renderEntry(bars: Bar[] | null, market: string | undefined): string {
  const levels = bars === null ? null : computeKeyLevels(bars, null);
  return renderToStaticMarkup(
    createElement(EntryObservationPanel, {
      observation: evaluateEntryObservation(levels, null, null, null),
      rangeBarCount: levels?.rangeBarCount ?? null,
      dataAsOfDates: { bars: null, signals: null, advice: null },
      market,
      bars,
    }),
  );
}

interface Seed {
  market: "US" | "TW";
  bars?: BarsResponse;
  advice?: AdviceResponse;
  signals?: SignalsResponse;
}

function renderPage(seed: Seed): string {
  nav.market = seed.market;
  const client = new QueryClient();
  if (seed.bars) client.setQueryData(["bars", "AAPL", seed.market], seed.bars);
  if (seed.advice) client.setQueryData(["advice", "AAPL", seed.market], seed.advice);
  if (seed.signals) client.setQueryData(["signals", "AAPL", seed.market], seed.signals);
  client.setQueryData(["positions"], NO_POSITIONS);
  return renderToStaticMarkup(createElement(QueryClientProvider, { client }, createElement(PositionDetailPage)));
}

/** Minimal tag-stack walker: ancestors (outermost first) of every exact chip occurrence. */
interface Tag {
  name: string;
  attrs: string;
}
const VOID_TAGS = new Set(["br", "hr", "img", "input", "meta", "link", "path", "circle", "line", "rect"]);
function chipAncestors(html: string, label: string): Tag[][] {
  const out: Tag[][] = [];
  const stack: Tag[] = [];
  const re = /<(\/?)([a-zA-Z][a-zA-Z0-9]*)((?:[^>"']|"[^"]*"|'[^']*')*)>/g;
  const chip = chipHtml(label);
  let m: RegExpExecArray | null;
  while ((m = re.exec(html)) !== null) {
    const closing = m[1] === "/";
    const name = m[2] ?? "";
    const attrs = m[3] ?? "";
    if (closing) {
      while (stack.length > 0 && stack.pop()?.name !== name) {
        /* unwind to the matching opener */
      }
      continue;
    }
    if (name === "span" && html.startsWith(chip, m.index)) {
      out.push([...stack]);
      re.lastIndex = m.index + chip.length;
      continue;
    }
    if (VOID_TAGS.has(name) || attrs.endsWith("/")) continue;
    stack.push({ name, attrs });
  }
  return out;
}

const BANNED_ANCESTOR_BASES = [/^truncate$/, /^overflow-/, /^line-clamp-/, /^text-ellipsis$/, /^hidden$/, /^max-w-/];
function bannedAncestorTokens(tags: Tag[]): string[] {
  const hits: string[] = [];
  for (const tag of tags) {
    const cls = /class="([^"]*)"/.exec(tag.attrs)?.[1] ?? "";
    for (const token of cls.split(/\s+/).filter(Boolean)) {
      const base = token.slice(token.lastIndexOf(":") + 1);
      if (BANNED_ANCESTOR_BASES.some((re) => re.test(base))) hits.push(`${tag.name}.${token}`);
    }
  }
  return hits;
}

/** Number of unclosed `<tag` openers before `index`. */
function openDepth(html: string, index: number, tag: string): number {
  const before = html.slice(0, index);
  return countOf(before, `<${tag} `) + countOf(before, `<${tag}>`) - countOf(before, `</${tag}>`);
}

/* ========================================================================== */

describe("PriceUnitBadge — wording and class are pinned (F7-R4 of the first ruling / art 3.2)", () => {
  it("the two approved strings, verbatim with the full-width colon", () => {
    expect(PRICE_UNIT_LABEL_USD).toBe("價格單位：美元");
    expect(PRICE_UNIT_LABEL_TWD).toBe("價格單位：新台幣");
    expect(PRICE_UNIT_LABEL_USD).toContain("：");
    expect(PRICE_UNIT_LABEL_TWD).toContain("：");
  });

  it("the class is the one art-lead specified, token for token", () => {
    expect(PRICE_UNIT_BADGE_CLASS).toBe(
      "whitespace-nowrap rounded border border-neutral-700 px-1.5 py-0.5 text-xs text-neutral-300",
    );
  });

  it("required tokens present; no low-contrast text, opacity, fill, hue, dark:, clipping or hiding tokens", () => {
    const tokens = PRICE_UNIT_BADGE_CLASS.split(/\s+/);
    for (const t of ["text-neutral-300", "border-neutral-700", "whitespace-nowrap", "text-xs", "px-1.5", "py-0.5", "rounded"]) {
      expect(tokens, t).toContain(t);
    }
    const banned =
      /(text-neutral-(400|500|600)|opacity-|(^|\s)bg-|\b(red|rose|orange|amber|yellow|green|emerald|sky|blue|cyan|violet|purple|pink)-|dark:|truncate|overflow-|hidden|line-clamp|text-ellipsis|max-w-|sr-only)/;
    expect(PRICE_UNIT_BADGE_CLASS).not.toMatch(banned);
  });

  it("the chip markup carries the class and text and nothing else (no title / aria-* / role / hidden attributes)", () => {
    const html = renderToStaticMarkup(createElement(PriceUnitBadge, { market: "US", bars: makeBars(3) }));
    expect(html).toBe(chipHtml(PRICE_UNIT_LABEL_USD));
    const tw = renderToStaticMarkup(createElement(PriceUnitBadge, { market: "TW", bars: makeBars(3, "TWD") }));
    expect(tw).toBe(chipHtml(PRICE_UNIT_LABEL_TWD));
  });

  it("source of PriceUnitBadge.tsx has no title / aria-* / role / sr-only / tooltip and no marketCurrency or FX / holding reads", () => {
    const code = stripComments(read(`${POSITION_DIR}/PriceUnitBadge.tsx`));
    for (const forbidden of ["title=", "aria-", "role=", "sr-only", "tooltip", "marketCurrency", "fx_to_twd", "portfolio_context", "formatMoney"]) {
      expect(code, forbidden).not.toContain(forbidden);
    }
    expect(code).toContain('from "../../lib/currencyMarket"');
    expect(code).toContain("MARKET_CURRENCY");
    expect(code).not.toMatch(/lib\/format"/);
  });

  it("the block wrapper (stand-alone line) is a plain flex div around the same chip", () => {
    const html = renderToStaticMarkup(createElement(PriceUnitBadge, { market: "US", bars: makeBars(3), block: true }));
    expect(html).toBe(`<div class="flex">${chipHtml(PRICE_UNIT_LABEL_USD)}</div>`);
  });
});

describe("F7-R1 / F7-R2 — truth source and fail-closed matrix", () => {
  it("the table it reads is the pinned one (TW -> TWD, US -> USD)", () => {
    expect(MARKET_CURRENCY).toEqual({ TW: "TWD", US: "USD" });
  });

  it("US + all-USD bars -> USD label", () => {
    expect(resolvePriceUnitLabel("US", makeBars(5, "USD"))).toBe(PRICE_UNIT_LABEL_USD);
  });

  it("TW + all-TWD bars -> TWD label", () => {
    expect(resolvePriceUnitLabel("TW", makeBars(5, "TWD"))).toBe(PRICE_UNIT_LABEL_TWD);
  });

  it("US + one bar carrying TWD -> nothing (and the reverse for TW)", () => {
    expect(resolvePriceUnitLabel("US", barsWithOneOdd("TWD", "USD"))).toBeNull();
    expect(resolvePriceUnitLabel("US", barsWithOneOdd("TWD", "USD", 0))).toBeNull();
    expect(resolvePriceUnitLabel("US", barsWithOneOdd("TWD", "USD", 99))).toBeNull();
    expect(resolvePriceUnitLabel("TW", barsWithOneOdd("USD", "TWD"))).toBeNull();
    expect(resolvePriceUnitLabel("US", makeBars(5, "TWD"))).toBeNull();
    expect(resolvePriceUnitLabel("US", barsWithOneOdd("", "USD"))).toBeNull();
    expect(resolvePriceUnitLabel("US", barsWithOneOdd("usd", "USD"))).toBeNull();
  });

  it("unknown market -> nothing, whatever the bars say (format.ts marketCurrency would answer USD)", () => {
    expect(resolvePriceUnitLabel("JP", makeBars(5, "USD"))).toBeNull();
    expect(resolvePriceUnitLabel("JP", makeBars(5, "JPY"))).toBeNull();
    expect(resolvePriceUnitLabel("HK", makeBars(5, "TWD"))).toBeNull();
    expect(resolvePriceUnitLabel("", makeBars(5, "USD"))).toBeNull();
    expect(resolvePriceUnitLabel("us", makeBars(5, "USD"))).toBeNull();
    expect(resolvePriceUnitLabel("toString", makeBars(5, "USD"))).toBeNull();
    expect(resolvePriceUnitLabel("__proto__", makeBars(5, "USD"))).toBeNull();
    expect(resolvePriceUnitLabel("constructor", PRICE_UNIT_MARKET_ONLY)).toBeNull();
    expect(resolvePriceUnitLabel("JP", PRICE_UNIT_MARKET_ONLY)).toBeNull();
    expect(resolvePriceUnitLabel(undefined, makeBars(5, "USD"))).toBeNull();
    expect(resolvePriceUnitLabel(undefined, PRICE_UNIT_MARKET_ONLY)).toBeNull();
  });

  it("no bars (null or empty) -> nothing; market-only basis applies the market check alone (F7-R3 signals path)", () => {
    expect(resolvePriceUnitLabel("US", null)).toBeNull();
    expect(resolvePriceUnitLabel("US", [])).toBeNull();
    expect(resolvePriceUnitLabel("US", PRICE_UNIT_MARKET_ONLY)).toBe(PRICE_UNIT_LABEL_USD);
    expect(resolvePriceUnitLabel("TW", PRICE_UNIT_MARKET_ONLY)).toBe(PRICE_UNIT_LABEL_TWD);
  });

  it("a non-printing component emits no markup and no substitute wording", () => {
    for (const html of [
      renderToStaticMarkup(createElement(PriceUnitBadge, { market: "JP", bars: makeBars(3, "USD") })),
      renderToStaticMarkup(createElement(PriceUnitBadge, { market: "US", bars: barsWithOneOdd("TWD") })),
      renderToStaticMarkup(createElement(PriceUnitBadge, { market: "US", bars: barsWithOneOdd("TWD"), block: true })),
    ]) {
      expect(html).toBe("");
    }
  });

  it("source: nothing under the stock page reads marketCurrency, a position currency, fx_to_twd or portfolio_context for the chip", () => {
    for (const rel of [
      `${POSITION_DIR}/DecisionCard.tsx`,
      `${POSITION_DIR}/KeyLevelsPanel.tsx`,
      `${POSITION_DIR}/EntryObservationPanel.tsx`,
      `${POSITION_DIR}/page.tsx`,
    ]) {
      const code = stripComments(read(rel));
      expect(code, rel).not.toMatch(/marketCurrency\s*\(/);
      for (const m of code.matchAll(/<PriceUnitBadge\b[^>]*>/g)) {
        expect(m[0], rel).not.toMatch(/currency|fx_to_twd|portfolio_context|avgCost/);
      }
    }
  });
});

describe("P0 decision card (gate: levels !== null)", () => {
  const bars = makeBars(100);

  it("US + USD bars: exactly one chip, last child of the badge row, before every price number", () => {
    const html = renderBody({ bars, market: "US" });
    expect(countOf(html, "價格單位")).toBe(1);
    expect(countOf(html, chipHtml(PRICE_UNIT_LABEL_USD))).toBe(1);
    // last child of the badge row span: chip + </span> closes the row, then the row's flex div closes
    expect(html).toContain(`${chipHtml(PRICE_UNIT_LABEL_USD)}</span></div>`);
    const chipIdx = html.indexOf(chipHtml(PRICE_UNIT_LABEL_USD));
    const firstPrice = html.search(FIRST_PRICE);
    expect(firstPrice).toBeGreaterThan(chipIdx);
  });

  it("the chip also follows the not-held and held badges (not-held first, chip last)", () => {
    const notHeld = renderBody({ bars, market: "US", anchorSource: "close-not-held" });
    expect(notHeld.indexOf("價格單位")).toBeGreaterThan(notHeld.indexOf("未持有"));
    const held = renderBody({
      bars,
      market: "US",
      response: makeAdvice({ held: true, position_ids: [1] }),
      anchorSource: "cost",
      avgCost: 100,
    });
    expect(countOf(held, "價格單位")).toBe(1);
    expect(held).not.toContain("未持有");
    expect(held).toContain(`${chipHtml(PRICE_UNIT_LABEL_USD)}</span></div>`);
  });

  it("TW + TWD bars: same component, same place, same markup, other wording", () => {
    const html = renderBody({ bars: makeBars(100, "TWD"), market: "TW" });
    expect(countOf(html, "價格單位")).toBe(1);
    expect(html).toContain(`${chipHtml(PRICE_UNIT_LABEL_TWD)}</span></div>`);
    expect(html).not.toContain("美元");
  });

  it("US + a bar carrying TWD, unknown market, missing market: no chip and no substitute wording", () => {
    for (const html of [
      renderBody({ bars: barsWithOneOdd("TWD"), market: "US" }),
      renderBody({ bars, market: "JP" }),
      renderBody({ bars }),
    ]) {
      expect(html).not.toContain("價格單位");
      expect(html).not.toContain("美元");
      expect(html).not.toContain("新台幣");
    }
  });

  it("gate = the card's own price gate: bars null, too-short bars (levels null) and no_price print dashes and no chip", () => {
    const noPrice = makeAdvice({ status: "insufficient_data", reason: "no price", advice: null });
    const cases: Array<Parameters<typeof renderBody>[0]> = [
      { bars: null, market: "US" },
      { bars: [], market: "US" },
      { bars: makeBars(100), market: "US", response: noPrice },
      // currency-clean bars whose prices cannot be computed (levels === null): the chip's own data check passes, only the gate stops it
      { bars: makeBars(100).map((b, i) => (i === 99 ? { ...b, close: "n/a" } : b)), market: "US" },
    ];
    for (const props of cases) {
      const html = renderBody(props);
      expect(html).not.toContain("價格單位");
      expect(html).not.toMatch(FIRST_PRICE);
    }
  });

  it("whenever the card prints a price the chip is there (price present <=> chip present), across anchors", () => {
    for (const anchorSource of ["cost", "close-not-held", "close-unknown"] as const) {
      const html = renderBody({ bars, market: "US", anchorSource, avgCost: anchorSource === "cost" ? 100 : null });
      expect(FIRST_PRICE.test(html), anchorSource).toBe(true);
      expect(countOf(html, "價格單位"), anchorSource).toBe(1);
    }
  });

  it("source: the DecisionCard chip sits behind the same `levels !== null` gate as closeText, with the card's own bars", () => {
    const code = stripComments(read(`${POSITION_DIR}/DecisionCard.tsx`));
    expect(countOf(code, "<PriceUnitBadge")).toBe(1);
    expect(code).toMatch(/\{levels !== null && <PriceUnitBadge market=\{market\} bars=\{barsForLevels\} \/>\}/);
    expect(code).toContain('const closeText = levels !== null ? fmt(levels.close) : "—";');
    expect(code).not.toMatch(/<details/);
    // wrapper passes the page's market straight through
    expect(code).toMatch(/<DecisionCardBody\b(?:(?!\/>)[\s\S])*?market=\{market\}/);
  });
});

describe("P1 key levels panel (gate: levels !== null)", () => {
  it("US: h2 and chip share a left group, chip right after the h2 (outside it), close line is ml-auto and comes after", () => {
    const html = renderKeyLevels(makeBars(100), "US");
    expect(countOf(html, "價格單位")).toBe(1);
    expect(html).toContain(
      `<div class="flex flex-wrap items-baseline justify-between gap-2"><div class="flex flex-wrap items-center gap-x-2 gap-y-1"><h2 class="text-lg font-semibold text-neutral-100">${KEY_LEVELS_PANEL_TITLE}</h2>${chipHtml(PRICE_UNIT_LABEL_USD)}</div><span class="ml-auto text-sm text-neutral-400">`,
    );
    const h2 = /<h2[^>]*>([\s\S]*?)<\/h2>/.exec(html);
    expect(h2?.[1]).toBe(KEY_LEVELS_PANEL_TITLE);
    expect(html.indexOf("價格單位")).toBeLessThan(html.search(FIRST_PRICE));
  });

  it("TW prints the TWD wording in the same place", () => {
    const html = renderKeyLevels(makeBars(100, "TWD"), "TW");
    expect(html).toContain(`</h2>${chipHtml(PRICE_UNIT_LABEL_TWD)}</div><span class="ml-auto`);
    expect(countOf(html, "價格單位")).toBe(1);
  });

  it("no chip when a bar has another currency, the market is unknown or missing (prices still print)", () => {
    for (const html of [
      renderKeyLevels(barsWithOneOdd("TWD"), "US"),
      renderKeyLevels(makeBars(100), "JP"),
      renderKeyLevels(makeBars(100), undefined),
    ]) {
      expect(html).not.toContain("價格單位");
      expect(html).toMatch(FIRST_PRICE);
    }
  });

  it("no chip in the no-data branch (levels === null)", () => {
    const html = renderKeyLevels([], "US");
    expect(html).not.toContain("價格單位");
    expect(html).not.toMatch(FIRST_PRICE);
    const unparsable = renderKeyLevels(makeBars(100).map((b, i) => (i === 99 ? { ...b, close: "n/a" } : b)), "US");
    expect(unparsable).not.toContain("價格單位");
    expect(unparsable).not.toMatch(FIRST_PRICE);
  });

  it("source: one chip, in the priced branch only, bars are the panel's own", () => {
    const code = stripComments(read(`${POSITION_DIR}/KeyLevelsPanel.tsx`));
    expect(countOf(code, "<PriceUnitBadge")).toBe(1);
    expect(code).toContain("<PriceUnitBadge market={market} bars={bars} />");
    expect(code.indexOf("<PriceUnitBadge")).toBeGreaterThan(code.indexOf("if (levels === null)"));
    // the chip is the second child of the group, directly after the h2
    expect(code).toMatch(/<\/h2>\s*<PriceUnitBadge/);
  });
});

describe("P2 six observation conditions (gate: trend condition printed; only inside <details>)", () => {
  const bars = makeBars(100);

  it("chip is the first child of the details body, before the E1 qualifier and every price; nothing in the main view", () => {
    const html = renderEntry(bars, "US");
    expect(countOf(html, "價格單位")).toBe(1);
    const bodyOpen =
      '<div class="mt-3 space-y-3 border-t border-neutral-800 pt-3 text-xs text-neutral-400">';
    const e1 = renderToStaticMarkup(createElement("p", null, ENTRY_E1_QUALIFIER));
    expect(html).toContain(`${bodyOpen}<div class="flex">${chipHtml(PRICE_UNIT_LABEL_USD)}</div>${e1}`);
    const chipIdx = html.indexOf("價格單位");
    expect(chipIdx).toBeGreaterThan(html.indexOf('<details class="group mt-3">'));
    expect(html.slice(0, html.indexOf("<details"))).not.toContain("價格單位");
    expect(chipIdx).toBeLessThan(html.search(FIRST_PRICE));
    // not on the h2 row
    const h2 = /<h2[^>]*>([\s\S]*?)<\/h2>/.exec(html);
    expect(h2?.[1]).toBe(ENTRY_PANEL_TITLE);
  });

  it("TW wording; not inside a list item", () => {
    const html = renderEntry(makeBars(100, "TWD"), "TW");
    expect(html).toContain(chipHtml(PRICE_UNIT_LABEL_TWD));
    expect(openDepth(html, html.indexOf("價格單位"), "li")).toBe(0);
  });

  it("no chip when trend is unavailable (no data, or fewer than 60 bars), the currency differs, or the market is unknown", () => {
    for (const html of [
      renderEntry(null, "US"),
      renderEntry(makeBars(30), "US"),
      renderEntry(barsWithOneOdd("TWD"), "US"),
      renderEntry(bars, "JP"),
      renderEntry(bars, undefined),
    ]) {
      expect(html).not.toContain("價格單位");
    }
  });

  it("an unavailable trend prints dashes, so the gate (chip) and the price print (observed value) are the same condition", () => {
    const withTrend = renderEntry(bars, "US");
    expect(withTrend).toMatch(FIRST_PRICE);
    const noTrend = renderEntry(makeBars(30), "US");
    expect(noTrend).not.toMatch(FIRST_PRICE);
  });

  it("source: one chip in the details body, gated on the printed trend value, wrapped as a block", () => {
    const code = stripComments(read(`${POSITION_DIR}/EntryObservationPanel.tsx`));
    expect(countOf(code, "<PriceUnitBadge")).toBe(1);
    expect(code).toContain("<PriceUnitBadge market={market} bars={bars} block />");
    expect(code.indexOf("<PriceUnitBadge")).toBeGreaterThan(code.indexOf("<details"));
    expect(code.indexOf("<PriceUnitBadge")).toBeLessThan(code.indexOf("{ENTRY_E1_QUALIFIER}"));
    expect(code).toMatch(/\{showPriceUnit && \(?\s*<PriceUnitBadge/);
    // the gate predicate is the one observedText uses for the trend value
    expect(code).toContain('c.id === "trend" && c.status !== "unavailable"');
  });
});

describe("whole page (seeded query cache)", () => {
  const usBars = barsResponse(makeBars(100, "USD"));
  const twBars = barsResponse(makeBars(100, "TWD"));

  function owners(html: string, label: string): string[] {
    const sorted: Array<{ at: number; who: string }> = [];
    let from = 0;
    for (;;) {
      const at = html.indexOf(chipHtml(label), from);
      if (at < 0) break;
      const anchors: Array<[string, number]> = [
        ["decision-card", html.lastIndexOf(`aria-label="${DECISION_CARD_ARIA_LABEL}"`, at)],
        ["technical", html.lastIndexOf(`${TECHNICAL_ANALYSIS_TITLE}</h2>`, at)],
        ["key-levels", html.lastIndexOf(`${KEY_LEVELS_PANEL_TITLE}</h2>`, at)],
        ["entry", html.lastIndexOf(`aria-label="${ENTRY_PANEL_TITLE}"`, at)],
      ];
      const best = anchors.reduce((a, b) => (b[1] > a[1] ? b : a));
      sorted.push({ at, who: best[0] });
      from = at + 1;
    }
    return sorted.map((s) => s.who);
  }

  it("complete US page: exactly 4 chips, one per block, in page order", () => {
    const html = renderPage({ market: "US", bars: usBars, advice: makeAdvice(), signals: SIGNALS_OK });
    expect(countOf(html, "價格單位")).toBe(4);
    expect(countOf(html, chipHtml(PRICE_UNIT_LABEL_USD))).toBe(4);
    expect(owners(html, PRICE_UNIT_LABEL_USD)).toEqual(["decision-card", "technical", "key-levels", "entry"]);
    expect(html).not.toContain(PRICE_UNIT_LABEL_TWD);
  });

  it("complete TW page: exactly 4 chips with the TWD wording, none with the USD wording", () => {
    const html = renderPage({ market: "TW", bars: twBars, advice: makeAdvice({ market: "TW" }), signals: SIGNALS_OK });
    expect(countOf(html, "價格單位")).toBe(4);
    expect(countOf(html, chipHtml(PRICE_UNIT_LABEL_TWD))).toBe(4);
    expect(owners(html, PRICE_UNIT_LABEL_TWD)).toEqual(["decision-card", "technical", "key-levels", "entry"]);
    expect(html).not.toContain(PRICE_UNIT_LABEL_USD);
  });

  it("technical block: chip directly follows the h2 in a left group, the h2 stays a bare title, and the badge row is untouched", () => {
    const html = renderPage({ market: "US", bars: usBars, advice: makeAdvice() });
    expect(html).toContain(
      `<div class="flex flex-wrap items-center justify-between gap-2"><div class="flex flex-wrap items-center gap-x-2 gap-y-1"><h2 class="text-lg font-semibold text-neutral-100">${TECHNICAL_ANALYSIS_TITLE}</h2>${chipHtml(PRICE_UNIT_LABEL_USD)}</div><span class="flex flex-wrap items-center gap-1.5 text-xs text-neutral-400">`,
    );
    for (const h2 of html.matchAll(/<h2[^>]*>([\s\S]*?)<\/h2>/g)) {
      expect(h2[1], "no markup inside any h2").not.toContain("<");
    }
  });

  it("depth rules: P0 and P1 chips are never inside a <details>, P2 always is; none inside <h2> or <li>", () => {
    const html = renderPage({ market: "US", bars: usBars, advice: makeAdvice(), signals: SIGNALS_OK });
    const chip = chipHtml(PRICE_UNIT_LABEL_USD);
    const positions: number[] = [];
    for (let at = html.indexOf(chip); at >= 0; at = html.indexOf(chip, at + 1)) positions.push(at);
    expect(positions).toHaveLength(4);
    const details = positions.map((at) => openDepth(html, at, "details"));
    expect(details[0]).toBe(0);
    expect(details[1]).toBe(0);
    expect(details[2]).toBe(0);
    expect(details[3]).toBeGreaterThanOrEqual(1);
    for (const at of positions) {
      expect(openDepth(html, at, "h2")).toBe(0);
      expect(openDepth(html, at, "li")).toBe(0);
    }
  });

  it("ancestors of every chip (below the block section) carry no truncate / overflow / line-clamp / ellipsis / hidden / max-w", () => {
    const html = renderPage({ market: "US", bars: usBars, advice: makeAdvice(), signals: SIGNALS_OK });
    const all = chipAncestors(html, PRICE_UNIT_LABEL_USD);
    expect(all).toHaveLength(4);
    for (const chain of all) {
      const lastSection = chain.map((t) => t.name).lastIndexOf("section");
      const own = lastSection >= 0 ? chain.slice(lastSection) : chain;
      expect(bannedAncestorTokens(own)).toEqual([]);
      expect(own.some((t) => t.name === "li" || t.name === "h2")).toBe(false);
    }
  });

  it("F7-R2 end to end: one TWD bar in a US page removes all four chips and prints no substitute wording", () => {
    const html = renderPage({
      market: "US",
      bars: barsResponse(barsWithOneOdd("TWD")),
      advice: makeAdvice(),
    });
    expect(html).not.toContain("價格單位");
    expect(html).not.toContain("美元");
    expect(html).toMatch(FIRST_PRICE); // the prices themselves are still shown
  });

  it("F7-R2 end to end for TW with a USD bar", () => {
    const html = renderPage({
      market: "TW",
      bars: barsResponse(barsWithOneOdd("USD", "TWD")),
      advice: makeAdvice({ market: "TW" }),
    });
    expect(html).not.toContain("價格單位");
  });

  it("gates are independent: no advice -> no decision-card chip but the other three stay; bars gone -> only data-less blocks are bare", () => {
    const noAdvice = renderPage({ market: "US", bars: usBars });
    expect(owners(noAdvice, PRICE_UNIT_LABEL_USD)).toEqual(["technical", "key-levels", "entry"]);
  });

  it("technical gate, bars not ok + signals ok (F7-R3): the chip is printed on the market check alone, once, and no other block prints one", () => {
    const html = renderPage({
      market: "US",
      bars: barsResponse([], "insufficient_data"),
      advice: makeAdvice(),
      signals: SIGNALS_OK,
    });
    expect(owners(html, PRICE_UNIT_LABEL_USD)).toEqual(["technical"]);
    expect(countOf(html, "價格單位")).toBe(1);
    const tw = renderPage({
      market: "TW",
      bars: barsResponse([], "insufficient_data"),
      advice: makeAdvice({ market: "TW" }),
      signals: SIGNALS_OK,
    });
    expect(owners(tw, PRICE_UNIT_LABEL_TWD)).toEqual(["technical"]);
  });

  it("technical gate, neither usable (bars not ok, signals missing or insufficient): no chip", () => {
    const none = renderPage({ market: "US", bars: barsResponse([], "insufficient_data"), advice: makeAdvice() });
    expect(none).not.toContain("價格單位");
    const insufficient: SignalsResponse = { ...SIGNALS_OK, status: "insufficient_data", reason: "x", signals: null };
    const html = renderPage({
      market: "US",
      bars: barsResponse([], "insufficient_data"),
      advice: makeAdvice(),
      signals: insufficient,
    });
    expect(html).not.toContain("價格單位");
    const okNoPayload: SignalsResponse = { ...SIGNALS_OK, signals: null };
    expect(
      renderPage({ market: "US", bars: barsResponse([], "insufficient_data"), advice: makeAdvice(), signals: okNoPayload }),
    ).not.toContain("價格單位");
  });

  it("technical gate is fail-closed when bars are ok but disagree on currency, even if signals are ok", () => {
    const html = renderPage({
      market: "US",
      bars: barsResponse(barsWithOneOdd("TWD")),
      advice: makeAdvice(),
      signals: SIGNALS_OK,
    });
    expect(html).not.toContain("價格單位");
  });

  it("source: technical chip uses the same two conditions that print prices in that block, in a left group after the h2", () => {
    const code = stripComments(read(`${POSITION_DIR}/page.tsx`));
    expect(countOf(code, "<PriceUnitBadge")).toBe(2); // bars branch + signals branch, one rendered at a time
    expect(code).toMatch(
      /\{bars\.isSuccess && bars\.data\.status === "ok" \? \(\s*<PriceUnitBadge market=\{market\} bars=\{bars\.data\.bars\} \/>\s*\) : signals\.isSuccess && signals\.data\.status === "ok" && signals\.data\.signals \? \(\s*<PriceUnitBadge market=\{market\} bars=\{PRICE_UNIT_MARKET_ONLY\} \/>\s*\) : null\}/,
    );
    // the same conditions still gate the one-liner and the indicator panel
    expect(code).toContain('{bars.isSuccess && bars.data.status === "ok" && (');
    expect(code).toContain('{signals.isSuccess && signals.data.status === "ok" && signals.data.signals && (');
    expect(code).toMatch(/<h2 className="text-lg font-semibold text-neutral-100">\{TECHNICAL_ANALYSIS_TITLE\}<\/h2>/);
    // each match is confined to the one JSX tag (no `/>` between the tag name and the prop)
    expect(code).toMatch(/<DecisionCard\b(?:(?!\/>)[\s\S])*?market=\{market\}/);
    expect(code).toMatch(/<KeyLevelsPanel\b(?:(?!\/>)[\s\S])*?market=\{market\}/);
    expect(code).toMatch(/<EntryObservationPanel\b(?:(?!\/>)[\s\S])*?market=\{market\}/);
    expect(code).toMatch(/<EntryObservationPanel\b(?:(?!\/>)[\s\S])*?\sbars=\{/);
  });
});

describe("F7-R5 — 'every printed price has a unit' with its exceptions spelled out", () => {
  /**
   * Prices printed on the stock page WITHOUT a chip of their own. Each entry is asserted
   * to still exist, so the list cannot go stale; anything not listed here must be covered.
   */
  const PRICE_WITHOUT_CHIP_EXCEPTIONS = [
    {
      id: "footer-buildBasisClose",
      reason: "page-footer formula line `buildBasisClose` repeats the top close figure; covered by the key-levels chip",
    },
    { id: "tradingview", reason: "third-party widget with its own currency; switched off (TRADINGVIEW_CHART_ENABLED = false)" },
  ] as const;

  it("the exception list is exactly the two documented ones", () => {
    expect(PRICE_WITHOUT_CHIP_EXCEPTIONS.map((e) => e.id)).toEqual(["footer-buildBasisClose", "tradingview"]);
  });

  it("footer-buildBasisClose exception is real: the footer prints the close and carries no chip; the block chips are the four counted above", () => {
    const html = renderPage({ market: "US", bars: barsResponse(makeBars(100)), advice: makeAdvice(), signals: SIGNALS_OK });
    const close = computeKeyLevels(makeBars(100), null)?.close;
    expect(close).toBeDefined();
    const footerStart = html.lastIndexOf("<footer");
    expect(footerStart).toBeGreaterThan(-1);
    const footer = html.slice(footerStart);
    expect(footer).toMatch(FIRST_PRICE);
    expect(footer).not.toContain("價格單位");
    expect(countOf(html, "價格單位")).toBe(4);
  });

  it("tradingview exception is real: the flag is off and the panel is only mounted behind it", () => {
    const code = stripComments(read(`${POSITION_DIR}/page.tsx`));
    expect(code).toContain("const TRADINGVIEW_CHART_ENABLED = false;");
    expect(code).toContain('TRADINGVIEW_CHART_ENABLED && chartTab === "tradingview"');
  });
});

describe("F7-R4 / single source — wording and class exist once, under position/[symbol]", () => {
  const files = (readdirSync(`${APP_DIR}${POSITION_DIR}`, { recursive: true, encoding: "utf8" }) as string[])
    .map((p) => p.split("\\").join("/"))
    .filter((p) => /\.(ts|tsx)$/.test(p) && !p.split("/").includes("__tests__") && !/\.test\./.test(p));

  it("scans a non-empty set that includes the badge file", () => {
    expect(files.length).toBeGreaterThan(5);
    expect(files).toContain("PriceUnitBadge.tsx");
  });

  it("the chip class string appears in PriceUnitBadge.tsx once and in no other file", () => {
    for (const f of files) {
      const n = countOf(read(`${POSITION_DIR}/${f}`), PRICE_UNIT_BADGE_CLASS);
      expect(n, f).toBe(f === "PriceUnitBadge.tsx" ? 1 : 0);
    }
  });

  it("no second currency wording: 價格單位 / 美元 / 新台幣 / USD / TWD literals live only in PriceUnitBadge.tsx", () => {
    for (const f of files) {
      if (f === "PriceUnitBadge.tsx") continue;
      const code = stripComments(read(`${POSITION_DIR}/${f}`));
      for (const literal of ["價格單位", "美元", "新台幣", '"USD"', '"TWD"']) {
        expect(code, `${f}: ${literal}`).not.toContain(literal);
      }
    }
  });

  it("every consumer renders the shared component rather than its own chip (4 call sites in 4 files)", () => {
    const users = files.filter((f) => read(`${POSITION_DIR}/${f}`).includes("<PriceUnitBadge"));
    expect(users.sort()).toEqual(["DecisionCard.tsx", "EntryObservationPanel.tsx", "KeyLevelsPanel.tsx", "page.tsx"]);
  });
});

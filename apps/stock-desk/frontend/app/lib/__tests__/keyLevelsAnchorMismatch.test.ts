import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";
import { resolveKeyLevelsAnchor } from "../keyLevelsAnchor";
import { DecisionCardBody } from "../../position/[symbol]/DecisionCard";
import {
  KEY_LEVELS_BASIS_ANCHOR,
  KEY_LEVELS_LADDER_RUNG_ANCHOR_CLOSE,
  KEY_LEVELS_LADDER_RUNG_ANCHOR_COST,
  KeyLevelsPanel,
  buildKeyLevelsFooterItems,
  buildStopBasisHeldWithCost,
} from "../../position/[symbol]/KeyLevelsPanel";
import { DECISION_CARD_CROSSED_DISCLOSURE } from "../decisionCardWording";
import type { AdviceCard, AdviceResponse, Bar, Position, PositionsResponse } from "../types";

/**
 * X-3c XC-N4 (風控 2026-10-08 第三段): a lot whose stored currency does not match
 * its market has a cost of unknown unit, so the stock page must not use it as the
 * stop / target anchor. The anchor falls back to "close-unknown" and none of the
 * three consumers (decision card, KeyLevelsPanel, page footer) shows a cost
 * basis label or a crossed sentence. A consistent book is unchanged.
 */

function makeBars(n: number): Bar[] {
  return Array.from({ length: n }, (_, i) => ({
    date: `2026-0${1 + Math.floor(i / 28)}-${String(1 + (i % 28)).padStart(2, "0")}`,
    open: "100",
    high: "105",
    low: "95",
    close: String(100 + (i % 7)),
    volume: 1000,
    currency: "TWD",
    source: "demo",
  }));
}

function makeCard(): AdviceCard {
  return {
    symbol: "X",
    action: "add",
    quantity_range: { min_shares: 500, max_shares: 1000, restores_compliance: true, basis: "basis" },
    matched_rules: [],
    counterarguments: [],
    invalidation_conditions: [],
    confidence: "medium",
    confidence_meaning: "meaning",
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

function makeResponse(symbol: string, market: "TW" | "US"): AdviceResponse {
  return {
    symbol,
    market,
    status: "ok",
    reason: null,
    as_of: "2026-09-18T09:00:00+08:00",
    held: true,
    position_ids: [1],
    portfolio_context: {} as unknown as AdviceResponse["portfolio_context"],
    context_notes: [],
    advice: makeCard(),
    data: {
      status: "fresh",
      source: "twse",
      staleness_minutes: 5,
      is_within_ttl: null,
      bar_count: 300,
      first_bar_date: "2025-05-01",
      last_bar_date: "2026-09-18",
      trading_days_behind: null,
      reason: null,
    },
  };
}

function lot(
  id: number,
  symbol: string,
  market: "TW" | "US",
  currency: "TWD" | "USD",
  avgCost: string,
): Position {
  return {
    id,
    symbol,
    market,
    quantity: "10",
    avg_cost: avgCost,
    currency,
    instrument_type: "stock",
    opened_at: "2026-03-12",
    sector: null,
    note: null,
    created_at: "2026-03-12T00:00:00Z",
    updated_at: "2026-03-12T00:00:00Z",
  };
}

function book(...items: Position[]): PositionsResponse {
  return { items, as_of: "2026-10-08T09:00:00+08:00" };
}

const BARS = makeBars(80);

interface Surfaces {
  card: string;
  panel: string;
  footer: ReturnType<typeof buildKeyLevelsFooterItems>;
}

function surfaces(
  anchor: ReturnType<typeof resolveKeyLevelsAnchor>,
  symbol: string,
  market: "TW" | "US",
): Surfaces {
  return {
    card: renderToStaticMarkup(
      createElement(DecisionCardBody, {
        response: makeResponse(symbol, market),
        bars: BARS,
        anchorSource: anchor.anchorSource,
        avgCost: anchor.avgCost,
      }),
    ),
    panel: renderToStaticMarkup(
      createElement(KeyLevelsPanel, { bars: BARS, avgCost: anchor.avgCost, anchorSource: anchor.anchorSource }),
    ),
    footer: buildKeyLevelsFooterItems(BARS, anchor.avgCost, anchor.anchorSource),
  };
}

const COST_MARKERS = [
  "基準價（持倉平均成本）",
  "本卡以你的持倉平均成本",
  DECISION_CARD_CROSSED_DISCLOSURE,
  "最新收盤高於此參考水位",
  "最新收盤低於此參考水位",
];

const MISMATCH_FIXTURES = [
  // A type: a US stock recorded in TWD -- fixed stop 920 would sit far above a ~100 close.
  { name: "A type (US / TWD)", symbol: "MSFT", market: "US" as const, book: book(lot(1, "MSFT", "US", "TWD", "1000")) },
  // B type: a TW stock recorded in USD.
  { name: "B type (TW / USD)", symbol: "2330", market: "TW" as const, book: book(lot(1, "2330", "TW", "USD", "1000")) },
  {
    name: "one consistent lot plus one mismatched lot of the same symbol",
    symbol: "2330",
    market: "TW" as const,
    book: book(lot(1, "2330", "TW", "TWD", "100"), lot(2, "2330", "TW", "USD", "3")),
  },
];

describe("resolveKeyLevelsAnchor — currency/market mismatch (XC-N4)", () => {
  for (const f of MISMATCH_FIXTURES) {
    it(`${f.name}: close-unknown, no cost, on all three consumers no cost basis label and no crossed sentence`, () => {
      const anchor = resolveKeyLevelsAnchor(f.book, f.symbol, f.market);
      expect(anchor).toEqual({ anchorSource: "close-unknown", avgCost: null });
      const s = surfaces(anchor, f.symbol, f.market);
      for (const marker of COST_MARKERS) {
        expect(s.card, `card: ${marker}`).not.toContain(marker);
        expect(s.panel, `panel: ${marker}`).not.toContain(marker);
        expect(JSON.stringify(s.footer), `footer: ${marker}`).not.toContain(marker);
      }
      expect(s.card).not.toContain("距最新收盤");
      expect(s.panel).not.toContain(KEY_LEVELS_LADDER_RUNG_ANCHOR_COST);
      expect(s.panel).toContain(KEY_LEVELS_LADDER_RUNG_ANCHOR_CLOSE);
      // same output as the existing "cost unknown" path
      const unknown = surfaces({ anchorSource: "close-unknown", avgCost: null }, f.symbol, f.market);
      expect(s).toEqual(unknown);
    });
  }

  it("a mismatched lot of ANOTHER symbol does not affect this symbol", () => {
    const b = book(lot(1, "2330", "TW", "TWD", "100"), lot(2, "MSFT", "US", "TWD", "1000"));
    const anchor = resolveKeyLevelsAnchor(b, "2330", "TW");
    expect(anchor.anchorSource).toBe("cost");
    expect(anchor.avgCost).toBe(100);
  });

  it("an unknown market never matches (fail closed, same as the backend)", () => {
    const odd = { ...lot(1, "ZZZ", "US", "USD", "50"), market: "JP" as unknown as "US" };
    const anchor = resolveKeyLevelsAnchor(book(odd), "ZZZ", "JP" as unknown as "US");
    expect(anchor).toEqual({ anchorSource: "close-unknown", avgCost: null });
  });

  it("consistent books are unchanged: TW/TWD and US/USD keep the cost anchor on all three consumers", () => {
    for (const [symbol, market, currency] of [
      ["2330", "TW", "TWD"],
      ["MSFT", "US", "USD"],
    ] as const) {
      const anchor = resolveKeyLevelsAnchor(book(lot(1, symbol, market, currency, "100")), symbol, market);
      expect(anchor).toEqual({ anchorSource: "cost", avgCost: 100 });
      const s = surfaces(anchor, symbol, market);
      expect(s.card).toContain("基準價（持倉平均成本）");
      expect(s.panel).toContain(KEY_LEVELS_LADDER_RUNG_ANCHOR_COST);
      expect(s.panel).toContain(buildStopBasisHeldWithCost("100.00"));
    }
  });

  it("existing non-mismatch fallbacks are unchanged: no positions -> unknown, no lots -> not held, unusable cost -> unknown", () => {
    expect(resolveKeyLevelsAnchor(undefined, "2330", "TW")).toEqual({ anchorSource: "close-unknown", avgCost: null });
    expect(resolveKeyLevelsAnchor(book(), "2330", "TW")).toEqual({ anchorSource: "close-not-held", avgCost: null });
    expect(resolveKeyLevelsAnchor(book(lot(1, "2330", "TW", "TWD", "0")), "2330", "TW")).toEqual({
      anchorSource: "close-unknown",
      avgCost: null,
    });
  });
});

describe("footer assertion is not vacuous", () => {
  it("the footer is non-empty and serialises its basis items; its content is anchor-independent by construction (no cost number is rendered there)", () => {
    const cost = buildKeyLevelsFooterItems(BARS, 100, "cost");
    const unknown = buildKeyLevelsFooterItems(BARS, null, "close-unknown");
    expect(cost.length).toBeGreaterThan(10);
    expect(JSON.stringify(unknown)).toContain(KEY_LEVELS_BASIS_ANCHOR.formula[0] ?? "");
    expect(JSON.stringify(unknown)).toBe(JSON.stringify(cost));
  });
});

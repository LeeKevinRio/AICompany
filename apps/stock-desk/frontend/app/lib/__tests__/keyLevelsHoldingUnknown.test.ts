import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";
import { resolveKeyLevelsAnchor, type PositionsAnchorInput } from "../keyLevelsAnchor";
import { DecisionCardBody } from "../../position/[symbol]/DecisionCard";
import {
  KEY_LEVELS_LADDER_RUNG_ANCHOR_CLOSE_HELD,
  KEY_LEVELS_STOP_CONDITION_ATR_AVAILABLE,
  KEY_LEVELS_STOP_CONDITION_ATR_UNAVAILABLE,
  KEY_LEVELS_STOP_CARD_TITLE,
  KEY_LEVELS_TARGET_ANCHOR_CROSS_REF,
  KEY_LEVELS_TARGET_CARD_TITLE,
  KEY_LEVELS_TARGET_ROW_2R,
  KEY_LEVELS_TARGET_ROW_FIXED_PCT,
  KeyLevelsPanel,
  buildStopBasisConfirmedNotHeld,
  buildStopBasisHeld,
} from "../../position/[symbol]/KeyLevelsPanel";
import { DECISION_CARD_COST_PNL_UNAVAILABLE, buildCostPnlRow } from "../decisionCardWording";
import { computeKeyLevels } from "../keyLevels";
import type { AdviceCard, AdviceResponse, Bar, Position, PositionsResponse } from "../types";

/**
 * B0 風控 required 1 / required 2 (work/reviews/2026-10-17-A-15-...風控.md, 追加二).
 *
 * required 1: while the holding status is undetermined (positions query pending
 * or failed -> no data) the panel renders none of the held-only literals
 * LM-16 / LM-17 / LM-53 and shows "—" for the anchor-derived numbers, like the
 * decision card. A CONFIRMED holding with an unusable cost still uses
 * LM-16 + LM-17 + LM-53.
 *
 * required 2: the 「大字為…（虧損較小）」 line comes BEFORE LM-16, and LM-16 -> LM-19
 * stay adjacent, so 「（虧損較小）」 is never directly under the cost P&L row.
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

function makeResponse(): AdviceResponse {
  const card: AdviceCard = {
    symbol: "2330",
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
  return {
    symbol: "2330",
    market: "TW",
    status: "ok",
    reason: null,
    as_of: "2026-09-18T09:00:00+08:00",
    held: true,
    position_ids: [1],
    portfolio_context: {} as unknown as AdviceResponse["portfolio_context"],
    context_notes: [],
    advice: card,
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

function lot(avgCost: string): Position {
  return {
    id: 1,
    symbol: "2330",
    market: "TW",
    quantity: "10",
    avg_cost: avgCost,
    currency: "TWD",
    instrument_type: "stock",
    opened_at: "2026-03-12",
    sector: null,
    note: null,
    created_at: "2026-03-12T00:00:00Z",
    updated_at: "2026-03-12T00:00:00Z",
  };
}

function book(...items: Position[]): PositionsResponse {
  return { items, as_of: "2026-10-17T09:00:00+08:00" };
}

const BARS_ATR = makeBars(80); // atr14 available
const BARS_NO_ATR = makeBars(10); // fewer than 15 bars: atr14 unavailable

/** A successfully fetched positions query slice. */
function ok(data: PositionsResponse): PositionsAnchorInput {
  return { isSuccess: true, data };
}

/** First load pending, or first load failed: not success and no data at all. */
const NO_DATA: PositionsAnchorInput = { isSuccess: false, data: undefined };

function panelOf(bars: Bar[], positions: PositionsAnchorInput): string {
  const anchor = resolveKeyLevelsAnchor(positions, "2330", "TW");
  return renderToStaticMarkup(
    createElement(KeyLevelsPanel, { bars, avgCost: anchor.avgCost, anchorSource: anchor.anchorSource }),
  );
}

function closeOf(bars: Bar[]): { x: string; d: string } {
  const levels = computeKeyLevels(bars);
  if (levels === null) throw new Error("fixture bars must be computable");
  return {
    x: levels.close.toLocaleString("zh-TW", { minimumFractionDigits: 2, maximumFractionDigits: 2 }),
    d: levels.closeDate,
  };
}

/** The literals that are only valid on the held branch. */
function heldOnlyLiterals(bars: Bar[]): string[] {
  const { x, d } = closeOf(bars);
  return [buildStopBasisHeld(x, d), KEY_LEVELS_LADDER_RUNG_ANCHOR_CLOSE_HELD, DECISION_CARD_COST_PNL_UNAVAILABLE];
}

describe("B0 required 1: holding status undetermined renders no held-only literal in the panel", () => {
  // First load pending and first load failed are BOTH "not success, no data": one resolver input, so this
  // case cannot tell them apart. A refetch failure that keeps older data is a different input (status
  // "error" WITH data) and has its own cases below (風控 B0 R-1).
  for (const [label, bars] of [
    ["ATR available", BARS_ATR],
    ["ATR unavailable", BARS_NO_ATR],
  ] as const) {
    it(`positions loading or failed (data undefined), ${label}: no LM-16 / LM-17 / LM-53, anchor-derived numbers are "—"`, () => {
      const anchor = resolveKeyLevelsAnchor(NO_DATA, "2330", "TW");
      expect(anchor).toEqual({ anchorSource: "holding-unknown", avgCost: null });
      const html = panelOf(bars, NO_DATA);
      for (const literal of heldOnlyLiterals(bars)) {
        expect(html, literal).not.toContain(literal);
      }
      // Partial-literal guards (no fragment of the held branch either).
      expect(html).not.toContain("為基準計算；相對成本的損益另列於下。");
      expect(html).not.toContain("基準價（最新收盤）");
      expect(html).not.toContain("相對成本損益");
      // The anchor cross-reference sentence of the detail target card is hidden too (M3).
      expect(html).not.toContain(KEY_LEVELS_TARGET_ANCHOR_CROSS_REF);
      // Fail closed like the decision card: no anchor-derived number is shown, and not-held wording is not claimed either.
      const levels = computeKeyLevels(bars);
      expect(levels).not.toBeNull();
      // L3: BOTH big numbers are "—" (each directly under its own card title), not just one of them.
      const BIG_DASH = '<p class="mt-1 font-mono text-xl font-bold text-neutral-100">—</p>';
      expect(html).toContain(`<p class="text-sm text-neutral-400">${KEY_LEVELS_STOP_CARD_TITLE}</p>${BIG_DASH}`);
      expect(html).toContain(`<p class="text-sm text-neutral-400">${KEY_LEVELS_TARGET_CARD_TITLE}</p>${BIG_DASH}`);
      expect(html.split(BIG_DASH).length - 1).toBe(2);
      // L3: both detail rows of the target card are "—" as well.
      const rowDash = (rowLabel: string): string =>
        `<span class="text-sm text-neutral-400">${rowLabel}</span><span class="font-mono text-sm text-neutral-100">—</span>`;
      expect(html).toContain(rowDash(KEY_LEVELS_TARGET_ROW_2R));
      expect(html).toContain(rowDash(KEY_LEVELS_TARGET_ROW_FIXED_PCT));
      expect(html).not.toContain("未持有此標的");
      expect(html).not.toContain("試算");
      expect(html).not.toContain("價位階梯");
      expect(html).not.toContain(KEY_LEVELS_STOP_CONDITION_ATR_AVAILABLE);
      expect(html).not.toContain(KEY_LEVELS_STOP_CONDITION_ATR_UNAVAILABLE);
      if (levels !== null) {
        const fmt = (n: number): string =>
          n.toLocaleString("zh-TW", { minimumFractionDigits: 2, maximumFractionDigits: 2 });
        expect(html).not.toContain(fmt(levels.stopSuggested));
        expect(html).not.toContain(fmt(levels.target2R));
        expect(html).not.toContain(fmt(levels.targetFixedPct));
      }
    });
  }

  it("the decision card is unchanged for a pending / failed positions query: stop / target stay '—', no anchor label", () => {
    const response = makeResponse();
    const anchor = resolveKeyLevelsAnchor(NO_DATA, "2330", "TW");
    const html = renderToStaticMarkup(
      createElement(DecisionCardBody, {
        response,
        bars: BARS_ATR,
        anchorSource: anchor.anchorSource,
        avgCost: anchor.avgCost,
      }),
    );
    expect(html).not.toContain("距最新收盤");
    expect(html).not.toContain(KEY_LEVELS_LADDER_RUNG_ANCHOR_CLOSE_HELD);
    expect(html).not.toContain("基準價");
    // L4: on the decision card "holding-unknown" must behave exactly like "close-unknown" (whole-output equality).
    const closeUnknown = resolveKeyLevelsAnchor(ok(book(lot("0"))), "2330", "TW");
    expect(closeUnknown).toEqual({ anchorSource: "close-unknown", avgCost: null });
    const htmlCloseUnknown = renderToStaticMarkup(
      createElement(DecisionCardBody, {
        response,
        bars: BARS_ATR,
        anchorSource: closeUnknown.anchorSource,
        avgCost: closeUnknown.avgCost,
      }),
    );
    expect(html).toBe(htmlCloseUnknown);
  });

  // R-1 / R-2: the resolver itself decides from the query status, so a refetch FAILURE that still carries the
  // last successful `data` (status "error") is undetermined too -- never the stale held / not-held branches.
  // These cases go red if the page (or resolver) falls back to looking at `data` alone.
  const STALE_BOOKS: ReadonlyArray<readonly [string, PositionsResponse]> = [
    ["stale book still lists the holding", book(lot("100"))],
    ["stale book is an empty list", book()],
  ];
  for (const [label, staleBook] of STALE_BOOKS) {
    it(`refetch failed (status error) but older data kept, ${label}: holding-unknown, no held-only literal, no not-held claim`, () => {
      const errorWithStale: PositionsAnchorInput = { isSuccess: false, data: staleBook };
      expect(resolveKeyLevelsAnchor(errorWithStale, "2330", "TW")).toEqual({
        anchorSource: "holding-unknown",
        avgCost: null,
      });
      // Same result as the no-data input: the panel output is identical.
      expect(panelOf(BARS_ATR, errorWithStale)).toBe(panelOf(BARS_ATR, NO_DATA));
      const html = panelOf(BARS_ATR, errorWithStale);
      for (const literal of heldOnlyLiterals(BARS_ATR)) {
        expect(html, literal).not.toContain(literal);
      }
      expect(html).not.toContain("未持有此標的");
      expect(html).not.toContain("相對成本損益");
    });
  }

  it("a refetch merely in progress keeps status success and the last successful data (documented known limitation)", () => {
    expect(resolveKeyLevelsAnchor(ok(book(lot("100"))), "2330", "TW")).toEqual({ anchorSource: "cost", avgCost: 100 });
    expect(resolveKeyLevelsAnchor(ok(book()), "2330", "TW")).toEqual({ anchorSource: "close-not-held", avgCost: null });
  });
});

describe("B0 required 1: a CONFIRMED holding with an unusable cost keeps LM-16 + LM-17 + LM-53", () => {
  for (const [label, bars] of [
    ["ATR available", BARS_ATR],
    ["ATR unavailable", BARS_NO_ATR],
  ] as const) {
    it(`(c) held, cost unusable (avg_cost 0), ${label}`, () => {
      const anchor = resolveKeyLevelsAnchor(ok(book(lot("0"))), "2330", "TW");
      expect(anchor).toEqual({ anchorSource: "close-unknown", avgCost: null });
      const html = panelOf(bars, ok(book(lot("0"))));
      for (const literal of heldOnlyLiterals(bars)) {
        expect(html, literal).toContain(literal);
      }
      // LM-53 replaces the whole row: no P&L number.
      expect(html).not.toContain("相對成本損益 ");
      // Control for the M3 assertion above: with a confirmed holding the cross-reference sentence IS rendered.
      expect(html).toContain(KEY_LEVELS_TARGET_ANCHOR_CROSS_REF);
    });
  }
});

describe("B0 required 2: DOM order (the 「大字為…」 line before LM-16; LM-16 -> LM-19 adjacent)", () => {
  for (const [label, bars, atrLine] of [
    ["ATR available", BARS_ATR, KEY_LEVELS_STOP_CONDITION_ATR_AVAILABLE],
    ["ATR unavailable", BARS_NO_ATR, KEY_LEVELS_STOP_CONDITION_ATR_UNAVAILABLE],
  ] as const) {
    it(`(d) held with a loss, ${label}: ${atrLine.slice(0, 6)}… < LM-16, LM-16 and LM-19 are adjacent siblings`, () => {
      const { x, d } = closeOf(bars);
      const html = panelOf(bars, ok(book(lot("200")))); // close ~100..106 vs cost 200: a loss
      const lm16 = buildStopBasisHeld(x, d);
      const levels = computeKeyLevels(bars);
      if (levels === null) throw new Error("fixture");
      const lm19 = buildCostPnlRow((levels.close / 200 - 1) * 100);
      expect(lm19).toMatch(/^相對成本損益 -/);

      const iAtr = html.indexOf(atrLine);
      const i16 = html.indexOf(lm16);
      const i19 = html.indexOf(lm19);
      expect(iAtr).toBeGreaterThan(-1);
      expect(i16).toBeGreaterThan(iAtr);
      expect(i19).toBeGreaterThan(i16);

      // LM-16 -> LM-19 directly adjacent ("另列於下"), nothing between them.
      expect(html).toContain(`<p class="mt-1">${lm16}</p><p class="mt-1">${lm19}</p>`);
      // The 「大字為…」 line sits directly above LM-16.
      expect(html).toContain(`<p class="mt-1">${atrLine}</p><p class="mt-1">${lm16}</p>`);
      // Nothing follows LM-19 inside that block: the next element is not the 大字為 line.
      const afterLm19 = html.slice(i19 + lm19.length);
      expect(afterLm19.startsWith("</p></div>")).toBe(true);
    });
  }

  it("confirmed not-held: the 「大字為…」 line comes first and is directly followed by the not-held basis sentence", () => {
    const html = panelOf(BARS_ATR, ok(book()));
    const { x } = closeOf(BARS_ATR);
    const basis = buildStopBasisConfirmedNotHeld(x);
    const iAtr = html.indexOf(KEY_LEVELS_STOP_CONDITION_ATR_AVAILABLE);
    const iBasis = html.indexOf(basis);
    expect(iAtr).toBeGreaterThan(-1);
    expect(iBasis).toBeGreaterThan(iAtr);
    // Adjacent siblings, nothing between them.
    expect(html).toContain(`<p class="mt-1">${KEY_LEVELS_STOP_CONDITION_ATR_AVAILABLE}</p><p class="mt-1">${basis}</p>`);
  });
});

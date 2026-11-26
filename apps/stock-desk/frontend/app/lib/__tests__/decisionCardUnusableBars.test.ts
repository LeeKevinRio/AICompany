/**
 * RC-801 / RC-808 PR-alpha: the two decision-card lines shown when the shared
 * daily-bar verdict (`evaluateDailyBarsUsability`) is "unusable". Final wording
 * is pinned byte for byte; the state matrix, the shared-verdict wiring and the
 * placement / style are locked here.
 */
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it, vi } from "vitest";
import type { AdviceCard, AdviceResponse, Bar, BarsResponse, DataMeta, PositionsResponse } from "../types";
import { DecisionCardBody } from "../../position/[symbol]/DecisionCard";
import {
  KEY_LEVELS_LADDER_RUNG_CLOSE,
  KEY_LEVELS_NO_DATA_STATEMENT,
  KEY_LEVELS_STOP_CARD_TITLE,
} from "../../position/[symbol]/KeyLevelsPanel";
import {
  DECISION_CARD_QUANTITY_LABEL,
  DECISION_CARD_UNUSABLE_BARS_CAUSE,
  DECISION_CARD_UNUSABLE_BARS_SECOND_LINE,
  buildDecisionCardUnusableBarsLine1,
} from "../decisionCardWording";
import { evaluateDailyBarsUsability } from "../dailyBarsUsability";
import type { DailyBarsUsability } from "../dailyBarsUsability";

vi.mock("next/navigation", () => ({
  useParams: () => ({ symbol: "2330" }),
  useSearchParams: () => new URLSearchParams("market=TW"),
}));
vi.mock("next/dynamic", () => ({ default: () => () => null }));

const { default: PositionDetailPage } = await import("../../position/[symbol]/page");

const LINE1 = "「最新收盤」與「停損參考」兩格不顯示數字：目前沒有可用的日線資料。";
const LINE2 = "本卡依規則得出的結論與「股數參考」也用到同一批日線資料，可能同樣受到影響。";
const BANNED = ["資料錯誤", "損壞", "重新抓取", "暫", "恢復", "後端", "照常", "無效", "不要依據"];

const META: DataMeta = {
  status: "fresh",
  source: "twse",
  staleness_minutes: 5,
  is_within_ttl: null,
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
    source: "twse",
  }));
}

function badBars(): Bar[] {
  return goodBars().map((b, i) => (i === 40 ? { ...b, close: "0" } : b));
}

function makeCard(overrides: Partial<AdviceCard> = {}): AdviceCard {
  return {
    symbol: "2330",
    action: "add",
    quantity_range: {
      min_shares: 500,
      max_shares: 1000,
      restores_compliance: true,
      basis: "以「單一標的佔比上限」為最小可用額度換算，最多可再買進 1000 股。",
    },
    matched_rules: [
      {
        id: "uptrend_ma_stack",
        name: "均線多頭排列",
        action: "add",
        weight: 0.5,
        weight_meaning: "權重為規則優先序，非機率、勝率或預期報酬",
        explanation: "5 日、20 日、60 日均線由上而下排列。",
        invalidation: null,
      },
    ],
    counterarguments: [],
    invalidation_conditions: [],
    confidence: "medium",
    confidence_meaning: "信心等級反映規則一致性與資料完整度，非勝率或機率",
    rules_version: "1.0.2",
    as_of: "2026-04-12T09:00:00+08:00",
    observation_window: { start: "2025-05-01", end: "2026-04-12", bars: 300 },
    disclaimer: "依固定規則產生的操作參考，規則與價位未經歷史驗證；可能有誤，照做也可能虧損，是否採用由你決定。日線收盤資料，非即時。",
    limits_check: [],
    action_weights: [],
    direction_weights: [],
    has_conflict: false,
    aggregated_action: "add",
    blocked_action: null,
    blocked_notices: [],
    downgrade_notices: [],
    evaluation: { total_rules: 1, evaluated_rules: 1, matched_rules: 1, data_completeness: 1, skipped_rules: [] },
    ...overrides,
  };
}

function makeResponse(overrides: Partial<AdviceResponse> = {}): AdviceResponse {
  return {
    symbol: "2330",
    market: "TW",
    status: "ok",
    reason: null,
    as_of: "2026-04-12T09:00:00+08:00",
    held: true,
    position_ids: [1],
    portfolio_context: {} as unknown as AdviceResponse["portfolio_context"],
    context_notes: [],
    cap1_migration_notice: null,
    settings_fallback_notice: null,
    advice: makeCard(),
    data: META,
    ...overrides,
  };
}

const HELD = makeResponse();
const CANDIDATE = makeResponse({ held: false, position_ids: [] });
const NO_ACTION = makeResponse({ advice: makeCard({ action: "insufficient_data", quantity_range: null }) });
const NO_PRICE = makeResponse({ status: "insufficient_data", reason: "資料不足，無法計算。", advice: null });

const UNUSABLE: DailyBarsUsability = { status: "unusable" };

function renderBody(
  response: AdviceResponse,
  bars: Bar[] | null,
  barsUsability: DailyBarsUsability | null | undefined,
  anchorSource: "cost" | "close-not-held" | "close-unknown" = "cost",
): string {
  return renderToStaticMarkup(
    createElement(DecisionCardBody, { response, bars, anchorSource, avgCost: 900, market: "TW", barsUsability }),
  );
}

function count(haystack: string, needle: string): number {
  return haystack.split(needle).length - 1;
}

describe("RC-801 wording (RC-808 PR-alpha items 1 to 3, 5)", () => {
  it("line 1 and line 2 are the final sentences, byte for byte", () => {
    expect(buildDecisionCardUnusableBarsLine1(KEY_LEVELS_LADDER_RUNG_CLOSE, KEY_LEVELS_STOP_CARD_TITLE)).toBe(LINE1);
    expect(DECISION_CARD_UNUSABLE_BARS_SECOND_LINE).toBe(LINE2);
  });

  it("the three cell names are the existing constants", () => {
    expect(KEY_LEVELS_LADDER_RUNG_CLOSE).toBe("最新收盤");
    expect(KEY_LEVELS_STOP_CARD_TITLE).toBe("停損參考");
    expect(DECISION_CARD_QUANTITY_LABEL).toBe("股數參考");
    const src = readFileSync(fileURLToPath(new URL("../decisionCardWording.ts", import.meta.url)), "utf8");
    const card = readFileSync(fileURLToPath(new URL("../../position/[symbol]/DecisionCard.tsx", import.meta.url)), "utf8");
    expect(card).toContain(
      "buildDecisionCardUnusableBarsLine1(KEY_LEVELS_LADDER_RUNG_CLOSE, KEY_LEVELS_STOP_CARD_TITLE)",
    );
    // Line 2 is composed from the quantity-label constant, never retyped.
    expect(src).toContain("「${DECISION_CARD_QUANTITY_LABEL}」也用到同一批日線資料，可能同樣受到影響。");
    // The runtime strings are composed, so the cell names must not be retyped as literals in the card.
    expect(card).not.toContain("兩格不顯示數字");
    expect(card).not.toContain("也用到同一批日線資料");
  });

  it("the clause after the colon equals the prefix of KEY_LEVELS_NO_DATA_STATEMENT", () => {
    const afterColon = LINE1.slice(LINE1.indexOf("：") + 1, -1);
    expect(afterColon).toBe(DECISION_CARD_UNUSABLE_BARS_CAUSE);
    expect(KEY_LEVELS_NO_DATA_STATEMENT.startsWith(afterColon)).toBe(true);
    expect(KEY_LEVELS_NO_DATA_STATEMENT.startsWith("目前沒有可用的日線資料")).toBe(true);
  });

  it("carries none of the banned words", () => {
    for (const word of BANNED) {
      expect(LINE1, word).not.toContain(word);
      expect(LINE2, word).not.toContain(word);
    }
  });
});

describe("RC-801 state matrix on the decision card (RC-808 PR-alpha item 4)", () => {
  it("held, unusable: each line exactly once", () => {
    const html = renderBody(HELD, badBars(), UNUSABLE, "cost");
    expect(count(html, LINE1)).toBe(1);
    expect(count(html, LINE2)).toBe(1);
  });

  it("candidate, unusable: each line exactly once", () => {
    const html = renderBody(CANDIDATE, badBars(), UNUSABLE, "close-not-held");
    expect(count(html, LINE1)).toBe(1);
    expect(count(html, LINE2)).toBe(1);
  });

  it("no_action, unusable: line 1 only", () => {
    const html = renderBody(NO_ACTION, badBars(), UNUSABLE, "cost");
    expect(count(html, LINE1)).toBe(1);
    expect(html).not.toContain(LINE2);
  });

  it("no_price, unusable: neither line", () => {
    const html = renderBody(NO_PRICE, badBars(), UNUSABLE, "close-unknown");
    expect(html).not.toContain(LINE1);
    expect(html).not.toContain(LINE2);
  });

  it("usable (normal) bars: neither line, for held / candidate / no_action", () => {
    const usable: DailyBarsUsability = { status: "usable" };
    for (const [response, anchor] of [
      [HELD, "cost"],
      [CANDIDATE, "close-not-held"],
      [NO_ACTION, "cost"],
    ] as const) {
      const html = renderBody(response, goodBars(), usable, anchor);
      expect(html).not.toContain(LINE1);
      expect(html).not.toContain(LINE2);
    }
  });

  it("no verdict passed (null / undefined: loading, failed, insufficient_data envelopes): neither line", () => {
    for (const verdict of [null, undefined]) {
      const html = renderBody(HELD, null, verdict);
      expect(html).not.toContain(LINE1);
      expect(html).not.toContain(LINE2);
    }
  });

  it("RC-842 item 2: empty bars or non-ok envelope (bars null) never show the lines, even with an unusable verdict", () => {
    for (const bars of [[], null] as const) {
      const html = renderBody(HELD, bars === null ? null : [], UNUSABLE, "cost");
      expect(html).not.toContain(LINE1);
      expect(html).not.toContain(LINE2);
    }
  });

  it("the card reads the verdict it is given: a bad batch with a 'usable' verdict shows nothing (no second judgement inside the card)", () => {
    const html = renderBody(HELD, badBars(), { status: "usable" }, "cost");
    expect(html).not.toContain(LINE1);
    expect(html).not.toContain(LINE2);
  });

  it("source: DecisionCard.tsx never calls the shared function or re-checks values", () => {
    const card = readFileSync(fileURLToPath(new URL("../../position/[symbol]/DecisionCard.tsx", import.meta.url)), "utf8");
    expect(card).not.toContain("evaluateDailyBarsUsability(");
    expect(card).toContain("RC-842");
  });
});

describe("RC-801 placement and style (RC-808 PR-alpha item 6)", () => {
  const html = renderBody(HELD, badBars(), UNUSABLE, "cost");

  it("both lines are <p> elements with text-xs text-neutral-400, no lighter", () => {
    expect(html).toContain(`<p class="mt-2 text-xs text-neutral-400">${LINE1}</p>`);
    expect(html).toContain(`<p class="mt-1 text-xs text-neutral-400">${LINE2}</p>`);
    for (const faint of ["text-neutral-500", "text-neutral-600", "opacity-", "sr-only", "line-clamp", "truncate"]) {
      const around = html.slice(html.indexOf(LINE1) - 80, html.indexOf(LINE2) + LINE2.length);
      expect(around, faint).not.toContain(faint);
    }
  });

  it("sits below the three cells and is not inside a <details>", () => {
    expect(html.indexOf(LINE1)).toBeGreaterThan(html.indexOf(`${DECISION_CARD_QUANTITY_LABEL}</p>`));
    expect(html.indexOf(LINE1)).toBeLessThan(html.indexOf(LINE2));
    // Every <details> opened before the lines is closed again before them: the lines are in the main view.
    for (const line of [LINE1, LINE2]) {
      const before = html.slice(0, html.indexOf(line));
      expect(count(before, "<details")).toBe(count(before, "</details>"));
    }
  });
});

describe("RC-801 whole page wiring (shared verdict from page.tsx)", () => {
  const NO_POSITIONS: PositionsResponse = { items: [], as_of: "x" };

  function renderPage(seed: { bars?: BarsResponse; advice?: AdviceResponse }): string {
    const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    if (seed.bars) client.setQueryData(["bars", "2330", "TW"], seed.bars);
    if (seed.advice) client.setQueryData(["advice", "2330", "TW"], seed.advice);
    client.setQueryData(["positions"], NO_POSITIONS);
    return renderToStaticMarkup(createElement(QueryClientProvider, { client }, createElement(PositionDetailPage)));
  }

  function barsResponse(bars: Bar[], status: BarsResponse["status"] = "ok"): BarsResponse {
    return { symbol: "2330", market: "TW", status, reason: null, data: META, as_of: "x", bars };
  }

  it("bad bars: both lines appear exactly once on the page", () => {
    const html = renderPage({ bars: barsResponse(badBars()), advice: HELD });
    expect(count(html, LINE1)).toBe(1);
    expect(count(html, LINE2)).toBe(1);
  });

  it("clean bars: neither line", () => {
    const html = renderPage({ bars: barsResponse(goodBars()), advice: HELD });
    expect(html).not.toContain(LINE1);
    expect(html).not.toContain(LINE2);
  });

  it("bars loading: neither line", () => {
    const html = renderPage({ advice: HELD });
    expect(html).not.toContain(LINE1);
    expect(html).not.toContain(LINE2);
  });

  it("bars insufficient_data: neither line", () => {
    const html = renderPage({ bars: barsResponse([], "insufficient_data"), advice: HELD });
    expect(html).not.toContain(LINE1);
    expect(html).not.toContain(LINE2);
  });

  it("bars ok but empty array: neither line (RC-842 item 2)", () => {
    const html = renderPage({ bars: barsResponse([]), advice: HELD });
    expect(html).not.toContain(LINE1);
    expect(html).not.toContain(LINE2);
  });

  it("page.tsx hands the card the SAME verdict that collapses the technical section", () => {
    const src = readFileSync(fileURLToPath(new URL("../../position/[symbol]/page.tsx", import.meta.url)), "utf8");
    expect(count(src, "evaluateDailyBarsUsability(")).toBe(1);
    expect(src).toContain("barsUsability={dailyBarsUsability}");
    expect(src).toContain('dailyBarsUsability.status === "unusable"');
  });

  it("the card's verdict is the shared function's own result", () => {
    expect(evaluateDailyBarsUsability(badBars())).toEqual(UNUSABLE);
    expect(evaluateDailyBarsUsability(goodBars())).toEqual({ status: "usable" });
  });

  it("bad bars: the cells show 「—」 for close and stop, the quantity cell still shows its value", () => {
    const html = renderPage({ bars: barsResponse(badBars()), advice: HELD });
    const card = html.slice(html.indexOf('aria-label="決策摘要"'), html.indexOf(LINE2));
    expect(card).toContain(`${DECISION_CARD_QUANTITY_LABEL}</p>`);
    expect(card).toMatch(/500/);
    expect(card.split(">—<").length - 1).toBeGreaterThanOrEqual(2);
  });
});

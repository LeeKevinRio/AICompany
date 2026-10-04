/**
 * 波次1文案裁決.md「D 批」複審 (2026-08-10): the opposing-direction sentence
 * (「本次同時命中方向相反的規則…」) was gated on
 * `direction_weights.length > 1`, which also fires for defensive + neutral —
 * a `hold` bucket is a third category, not an opposite side, so that gate
 * claimed an opposition the data does not show. `hasOpposingDirections`
 * requires both actual sides. The sentence itself is unchanged.
 */

import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";
import { buildDataAsOfBadge } from "../../../lib/oneLinerWording";
import type { AdviceCard, DirectionWeight } from "../../../lib/types";
import { AdviceCardView, hasOpposingDirections } from "../AdviceCardView";

function makeAdvice(directions: DirectionWeight[]): AdviceCard {
  return { direction_weights: directions } as AdviceCard;
}

function dw(direction: string): DirectionWeight {
  return { direction, weight: 1, actions: [] };
}

describe("hasOpposingDirections — D2 真對立條件", () => {
  it("is false for defensive + neutral: 中性 is not an opposing side", () => {
    expect(hasOpposingDirections(makeAdvice([dw("defensive"), dw("neutral")]))).toBe(false);
  });

  it("is true for defensive + constructive: a real opposition", () => {
    expect(hasOpposingDirections(makeAdvice([dw("defensive"), dw("constructive")]))).toBe(true);
  });

  it("is false for constructive + neutral", () => {
    expect(hasOpposingDirections(makeAdvice([dw("constructive"), dw("neutral")]))).toBe(false);
  });

  it("is false for a single direction, and for none at all", () => {
    expect(hasOpposingDirections(makeAdvice([dw("defensive")]))).toBe(false);
    expect(hasOpposingDirections(makeAdvice([]))).toBe(false);
  });

  it("is still true when a neutral bucket sits alongside both real sides", () => {
    const advice = makeAdvice([dw("defensive"), dw("constructive"), dw("neutral")]);
    expect(hasOpposingDirections(advice)).toBe(true);
  });
});

/**
 * 風控 D-1 裁示 (b) 2026-10-04: the first line inside the card frame is the existing
 * `buildDataAsOfBadge(last_bar_date)` output, ahead of 「規則版本…」 and 「命中規則」.
 */
function makeFullAdvice(): AdviceCard {
  return {
    symbol: "2330",
    action: "hold",
    quantity_range: null,
    matched_rules: [
      {
        id: "r1",
        name: "Fixture rule",
        action: "reduce",
        weight: 1,
        weight_meaning: "fixture weight",
        explanation: "fixture explanation",
        invalidation: null,
      },
    ],
    counterarguments: [],
    invalidation_conditions: [],
    confidence: "low",
    confidence_meaning: "fixture",
    rules_version: "1.1.0",
    // Deliberately different dates from every `lastBarDate` used below.
    as_of: "2031-07-08T04:00:00Z",
    observation_window: { start: "2031-01-02", end: "2031-02-09", bars: 20 },
    disclaimer: "fixture",
    limits_check: [],
    action_weights: [],
    direction_weights: [],
    has_conflict: false,
    aggregated_action: null,
    blocked_action: null,
    blocked_notices: [],
    downgrade_notices: [],
    evaluation: {
      total_rules: 1,
      evaluated_rules: 1,
      matched_rules: 1,
      data_completeness: 1,
      skipped_rules: [],
    },
  };
}

function renderCard(lastBarDate: string | null): string {
  return renderToStaticMarkup(createElement(AdviceCardView, { advice: makeFullAdvice(), lastBarDate }));
}

describe("AdviceCardView 資料截至行（風控 D-1 (b)）", () => {
  const thisYear = new Date().getFullYear();

  it("卡框內第一行為獨立 <p>，文字等於 buildDataAsOfBadge 輸出（同年 MM-DD）", () => {
    const lastBarDate = `${thisYear}-03-05`;
    const html = renderCard(lastBarDate);
    const expected = buildDataAsOfBadge(lastBarDate);
    expect(expected).toBe("資料截至 03-05");
    const prefix = '<div class="rounded-lg border border-neutral-800 p-5">';
    expect(html.startsWith(`${prefix}<p class="mb-1 text-xs text-neutral-400">${expected}</p>`)).toBe(true);
  });

  it("跨年：文字等於 buildDataAsOfBadge 輸出（YYYY-MM-DD）", () => {
    const html = renderCard("2020-03-05");
    expect(html).toContain(`>${buildDataAsOfBadge("2020-03-05")}</p>`);
    expect(html).toContain(">資料截至 2020-03-05</p>");
  });

  it("位置在「規則版本」與「命中規則」之前", () => {
    const html = renderCard(`${thisYear}-03-05`);
    const badgeIdx = html.indexOf("資料截至");
    expect(badgeIdx).toBeGreaterThan(-1);
    expect(badgeIdx).toBeLessThan(html.indexOf("規則版本"));
    expect(badgeIdx).toBeLessThan(html.indexOf("命中規則"));
  });

  it("樣式 text-xs text-neutral-400，且無 truncate／title／sr-only／aria-hidden", () => {
    const html = renderCard("2020-03-05");
    const start = html.lastIndexOf("<p", html.indexOf("資料截至"));
    const tag = html.slice(start, html.indexOf(">", start) + 1);
    expect(tag).toContain("text-xs");
    expect(tag).toContain("text-neutral-400");
    expect(tag).not.toMatch(/truncate|title=|sr-only|aria-hidden|hidden/);
  });

  it("lastBarDate 為 null：整行不顯示", () => {
    const html = renderCard(null);
    expect(html).not.toContain("資料截至");
    expect(html.startsWith('<div class="rounded-lg border border-neutral-800 p-5"><p class="text-xs text-neutral-500">規則版本')).toBe(true);
  });

  it("日期只取 lastBarDate：不誤用 as_of 或 observation_window.end", () => {
    const html = renderCard("2020-03-05");
    const start = html.lastIndexOf("<p", html.indexOf("資料截至"));
    const line = html.slice(start, html.indexOf("</p>", start));
    expect(line).toContain("2020-03-05");
    expect(line).not.toContain("2031");
    expect(line).not.toContain("07-08");
    expect(line).not.toContain("02-09");
  });
});

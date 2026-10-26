/**
 * Risk remediation 5-BT (CEO ruling #59; risk-compliance final wording
 * `work/reviews/2026-10-26-風控五項整改字面逐字審-風控.md`, constraint C-13; failure condition T5).
 *
 * The backtest report's standing disclosure of the two assumptions that can flatter the numbers:
 * same-bar close fills, and the configured slippage. Test kind: 行為新增 (nothing rendered these
 * sentences before). Literals protected: the 5-BT heading (both versions), point 1, point 2 (both
 * versions) and the chart caption.
 */

import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";
import { EQUITY_CURVE_EMPTY_STATEMENT, EQUITY_CURVE_GUIDANCE } from "../../lib/backtestCurveWording";
import { FRONTEND_FORBIDDEN_TERMS } from "../../lib/adviceWording";
import {
  BACKTEST_SAME_CLOSE_FILL_POINT,
  buildBacktestAssumptionsHeading,
  buildBacktestSlippagePoint,
} from "../../lib/riskRemediationWording";
import { assertNoForbiddenTerms, findBareRealtimeClaims } from "../../lib/__tests__/wordingScanHelpers";
import type { BacktestResponse } from "../../lib/types";
import { BacktestReportView } from "../BacktestReportView";
import { makeResponse } from "./roundTripFixtures";

const HEADING_ZERO = "先看以下假設：前兩項可能讓結果偏樂觀";
const HEADING_POSITIVE = "先看以下假設：第一項可能讓結果偏樂觀";
const POINT_1 = "訊號與成交用同一根收盤價：收盤價要到收盤才知道，實際下單做不到這樣成交。";
const POINT_2_ZERO = "滑價設為 0 bps：滑價是實際成交價與預期價的差距，這裡沒有計入。";
const point2Positive = (n: number): string => `滑價假設 ${n} bps：滑價是實際成交價與預期價的差距，實際可能較大或較小。`;
const DEMO_WARNING = "本次回測使用的是合成示範資料。";

function render(slippageBps: number, overrides: Partial<BacktestResponse> = {}): string {
  const base = makeResponse();
  const report: BacktestResponse = {
    ...base,
    data_warning: DEMO_WARNING,
    cost_model: { ...base.cost_model, slippage_bps: slippageBps },
    ...overrides,
  };
  return renderToStaticMarkup(createElement(BacktestReportView, { report }));
}

describe("5-BT 字面逐字", () => {
  it("標題、第 1 點、第 2 點兩版", () => {
    expect(buildBacktestAssumptionsHeading(true)).toBe(HEADING_ZERO);
    expect(buildBacktestAssumptionsHeading(false)).toBe(HEADING_POSITIVE);
    expect(BACKTEST_SAME_CLOSE_FILL_POINT).toBe(POINT_1);
    expect(buildBacktestSlippagePoint(0)).toBe(POINT_2_ZERO);
    expect(buildBacktestSlippagePoint(7)).toBe(point2Positive(7));
    expect(buildBacktestSlippagePoint(2.5)).toBe(point2Positive(2.5));
  });

  it("圖說（字面更新：舊句補上成交與滑價假設）", () => {
    expect(EQUITY_CURVE_GUIDANCE).toBe("本圖同上方提醒：僅為歷史統計描述，不代表未來會重演；成交與滑價假設見上方。");
  });

  it("通過禁用詞與裸即時掃描（C-1），且不含否認建議性質的句子", () => {
    for (const text of [
      HEADING_ZERO,
      HEADING_POSITIVE,
      POINT_1,
      POINT_2_ZERO,
      point2Positive(7),
      EQUITY_CURVE_GUIDANCE,
    ]) {
      assertNoForbiddenTerms(text, FRONTEND_FORBIDDEN_TERMS, text);
      expect(findBareRealtimeClaims(text)).toEqual([]);
      for (const phrase of ["非投資建議", "不是建議", "僅供參考"]) expect(text).not.toContain(phrase);
    }
  });
});

describe("5-BT 顯示條件（C-13）", () => {
  it("滑價為 0：標題用「前兩項」版，第 2 點用「滑價設為 0 bps」版", () => {
    const html = render(0);
    expect(html).toContain(HEADING_ZERO);
    expect(html).not.toContain(HEADING_POSITIVE);
    expect(html).toContain(POINT_1);
    expect(html).toContain(POINT_2_ZERO);
  });

  it("滑價大於 0：標題用「第一項」版，第 2 點用「滑價假設 {n} bps」版（n 取設定值）", () => {
    const html = render(5);
    expect(html).toContain(HEADING_POSITIVE);
    expect(html).not.toContain(HEADING_ZERO);
    expect(html).toContain(POINT_1);
    expect(html).toContain(point2Positive(5));
    expect(html).not.toContain(POINT_2_ZERO);
  });

  it("位置：在 data_warning 之後、報告層級免責框之前，且在權益曲線區塊之前", () => {
    const html = render(0);
    const warning = html.indexOf(DEMO_WARNING);
    const heading = html.indexOf(HEADING_ZERO);
    const disclaimer = html.indexOf("本回測報告呈現的所有數字皆屬歷史統計描述");
    const chart = html.indexOf(EQUITY_CURVE_EMPTY_STATEMENT);
    for (const [name, idx] of Object.entries({ warning, heading, disclaimer, chart })) {
      expect(idx, name).toBeGreaterThan(-1);
    }
    expect(warning).toBeLessThan(heading);
    expect(heading).toBeLessThan(disclaimer);
    expect(heading).toBeLessThan(chart);
  });

  it("常駐：不在任何 <details> 內，字級 text-sm，不弱於 neutral-300", () => {
    const html = render(0);
    for (const block of html.match(/<details[\s\S]*?<\/details>/g) ?? []) {
      expect(block).not.toContain(HEADING_ZERO);
      expect(block).not.toContain(POINT_1);
    }
    const box = html.match(/<div class="([^"]*)"><p class="[^"]*">先看以下假設/);
    expect(box).not.toBeNull();
    expect(box![1]).toContain("text-sm");
    expect(box![1]).toContain("text-neutral-300");
    expect(box![1]).not.toMatch(/text-xs|truncate|line-clamp|hidden|opacity/);
  });

  it("第 3 點（費率未查證）不採用：揭露框內只有兩點，費率提醒維持原本那一句", () => {
    const html = render(0);
    const box = html.match(/先看以下假設[\s\S]*?<\/ol>/)![0];
    expect((box.match(/<li>/g) ?? []).length).toBe(2);
    expect(box).not.toContain("手續費與交易稅率未查證");
    // The pre-existing alert (rates_verified === false in the fixture) is still there, once.
    expect(html.split("費率未查證：本次回測使用的手續費／交易稅／滑價率").length - 1).toBe(1);
  });

  it("圖說：權益曲線下方的指引句帶「成交與滑價假設見上方」（曲線存在時渲染）", () => {
    // `EquityCurveChart` renders EQUITY_CURVE_GUIDANCE under the chart; the constant is the single source.
    expect(EQUITY_CURVE_GUIDANCE).toContain("成交與滑價假設見上方");
  });
});

/**
 * Risk remediation item 4 (CEO ruling #59; risk-compliance final wording
 * `work/reviews/2026-10-26-風控五項整改字面逐字審-風控.md`, constraints C-3, C-10, C-11, C-12):
 * stop-loss qualifier (4-Q) and explanation (4-E), take-profit moved out of the main view
 * (4-T), and the drawdown notice on the basis line (4-appendix).
 *
 * Test kind: the literal pins and the DOM blocks are 行為新增 (nothing rendered these sentences
 * before); the `computeKeyLevels` block is the C-3 behaviour pin that guards 4-E.
 */

import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";
import type { AdviceCard, AdviceResponse, Bar } from "../types";
import { FRONTEND_FORBIDDEN_TERMS } from "../adviceWording";
import { computeKeyLevels } from "../keyLevels";
import {
  DRAWDOWN_UNADJUSTED_NOTICE,
  STOP_EXPLANATION_WITHOUT_ATR,
  STOP_EXPLANATION_WITH_ATR,
  STOP_QUALIFIER,
  TARGET_FORMULA_TAG,
  TARGET_LADDER_GROUP_TITLE,
} from "../riskRemediationWording";
import { DecisionCardBody } from "../../position/[symbol]/DecisionCard";
import { KeyLevelsPanel, KEY_LEVELS_TARGET_CARD_TITLE } from "../../position/[symbol]/KeyLevelsPanel";
import { SummaryBody } from "../../position/[symbol]/OperationSummaryPanel";
import { assertNoForbiddenTerms, findBareRealtimeClaims } from "./wordingScanHelpers";

function bar(i: number, o: number, h: number, l: number, c: number): Bar {
  return {
    date: `2026-01-${String(1 + (i % 28)).padStart(2, "0")}`,
    open: String(o),
    high: String(h),
    low: String(l),
    close: String(c),
    volume: 1000,
    currency: "TWD",
    source: "demo",
  };
}

/** n flat-ish bars around 100 with a constant true range of 4 (high 102, low 98, close 100). */
function steadyBars(n: number): Bar[] {
  return Array.from({ length: n }, (_, i) => bar(i, 100, 102, 98, 100));
}

describe("4-Q／4-E／4-T／4-附 逐字（行為新增）", () => {
  it("4-Q", () => {
    expect(STOP_QUALIFIER).toBe("固定算式・未還原價・可能無法依此價成交");
  });

  it("4-E（有 ATR）", () => {
    expect(STOP_EXPLANATION_WITH_ATR).toBe(
      "停損參考由固定公式算出，不是分析結果：以最新收盤為基準，取「收盤減 2 倍 ATR（近 14 個交易日的平均波動幅度）」與「收盤的 92%」兩者中較高的一個。" +
        "用的是未還原價，沒有把配息、除權調整進去，跨除權息日可能失真。" +
        "實際賣出時，跳空、跌停或成交量不足都可能讓成交價與此價位差很多，甚至無法成交。",
    );
  });

  it("4-E（無 ATR）：只取收盤的 92%，後兩句與有 ATR 版相同", () => {
    expect(STOP_EXPLANATION_WITHOUT_ATR).toBe(
      "停損參考由固定公式算出，不是分析結果：以最新收盤為基準，因近期日線不足、無法計算 ATR，只取「收盤的 92%」。" +
        "用的是未還原價，沒有把配息、除權調整進去，跨除權息日可能失真。" +
        "實際賣出時，跳空、跌停或成交量不足都可能讓成交價與此價位差很多，甚至無法成交。",
    );
  });

  it("4-T 與階梯組標題", () => {
    expect(TARGET_FORMULA_TAG).toBe("固定算式，非分析結果");
    expect(TARGET_LADDER_GROUP_TITLE).toBe("停利參考（固定算式，非分析結果）");
  });

  it("4-附", () => {
    expect(DRAWDOWN_UNADJUSTED_NOTICE).toBe("以未還原價計算，回撤可能含除權息缺口");
  });

  it("全部通過禁用詞與裸即時掃描（C-1），且不含否認建議性質的句子；4-Q 不含「保證」（改用「可能無法依此價成交」）", () => {
    for (const text of [
      STOP_QUALIFIER,
      STOP_EXPLANATION_WITH_ATR,
      STOP_EXPLANATION_WITHOUT_ATR,
      TARGET_FORMULA_TAG,
      TARGET_LADDER_GROUP_TITLE,
      DRAWDOWN_UNADJUSTED_NOTICE,
    ]) {
      assertNoForbiddenTerms(text, FRONTEND_FORBIDDEN_TERMS, text);
      expect(findBareRealtimeClaims(text)).toEqual([]);
      for (const phrase of ["非投資建議", "不是建議", "僅供參考"]) expect(text).not.toContain(phrase);
    }
    expect(STOP_QUALIFIER).not.toContain("保證");
  });
});

// C-3 behaviour pin. Protects the 4-E sentence: 「收盤減 2 倍 ATR（近 14 個交易日的平均波動幅度）」
// 與「收盤的 92%」兩者中較高的一個；無 ATR 時只取「收盤的 92%」. If any of 2, 0.92, 14 or "take the
// higher one" changes, 4-E (both versions), 4-Q and K-1 must be rewritten in the same PR (failure
// condition T3).
describe("computeKeyLevels：4-E 所述算式的行為釘（C-3）", () => {
  it("有 ATR：停損 = 收盤 −2×ATR(14) 與 收盤×0.92 兩者中較高者（ATR 小 → 取 2×ATR 那條）", () => {
    // 20 bars, true range 4 every bar -> ATR(14) = 4 -> close - 2 x 4 = 92 ... vs 92? use close 100: 100*0.92 = 92 exactly equal; widen.
    const bars = Array.from({ length: 20 }, (_, i) => bar(i, 100, 101, 99, 100)); // TR = 2 -> ATR 2
    const levels = computeKeyLevels(bars)!;
    expect(levels.atr14).toBeCloseTo(2, 10);
    expect(levels.stopAtr).toBeCloseTo(100 - 2 * 2, 10); // 96
    expect(levels.stopFixedPct).toBeCloseTo(100 * 0.92, 10); // 92
    expect(levels.stopSuggested).toBeCloseTo(96, 10); // the higher of 96 and 92
  });

  it("有 ATR：ATR 大 → 收盤×0.92 較高，取 0.92 那條", () => {
    const bars = Array.from({ length: 20 }, (_, i) => bar(i, 100, 110, 90, 100)); // TR = 20 -> ATR 20
    const levels = computeKeyLevels(bars)!;
    expect(levels.atr14).toBeCloseTo(20, 10);
    expect(levels.stopAtr).toBeCloseTo(60, 10); // 100 - 2 x 20
    expect(levels.stopSuggested).toBeCloseTo(92, 10); // the higher of 60 and 92
  });

  it("倍數是 2：ATR 恰為 5 時 stopAtr = 90（1× 或 3× 都會得到別的數）", () => {
    const bars = Array.from({ length: 20 }, (_, i) => bar(i, 100, 102.5, 97.5, 100)); // TR = 5
    const levels = computeKeyLevels(bars)!;
    expect(levels.atr14).toBeCloseTo(5, 10);
    expect(levels.stopAtr).toBeCloseTo(90, 10);
  });

  it("期間是 14：只平均最後 14 根的真實波幅（再往前一根的大波動不計入）", () => {
    // 30 bars with TR 2 everywhere, except the bar 15th from the end, which has TR 100.
    const bars = Array.from({ length: 30 }, (_, i) => bar(i, 100, 101, 99, 100));
    bars[30 - 15] = bar(15, 100, 150, 50, 100); // TR = 100, outside the last 14 bars
    const levels = computeKeyLevels(bars)!;
    expect(levels.atr14).toBeCloseTo(2, 10);
    // And the 14th from the end IS inside the window.
    const inside = Array.from({ length: 30 }, (_, i) => bar(i, 100, 101, 99, 100));
    inside[30 - 14] = bar(16, 100, 150, 50, 100); // TR = 100 -> (13 x 2 + 100) / 14
    expect(computeKeyLevels(inside)!.atr14).toBeCloseTo((13 * 2 + 100) / 14, 10);
  });

  it("近期日線不足（少於 15 根）無法算 ATR：atr14 為 null，停損只取收盤×0.92", () => {
    const levels = computeKeyLevels(steadyBars(14))!;
    expect(levels.atr14).toBeNull();
    expect(levels.stopAtr).toBeNull();
    expect(levels.stopSuggested).toBeCloseTo(92, 10);
    // 15 bars is the first count with an ATR.
    expect(computeKeyLevels(steadyBars(15))!.atr14).not.toBeNull();
  });

  it("基準是最新一根收盤（不是均價、也不是成本）", () => {
    const bars = steadyBars(20);
    bars[19] = bar(19, 100, 102, 98, 120);
    const levels = computeKeyLevels(bars)!;
    expect(levels.stopFixedPct).toBeCloseTo(120 * 0.92, 10);
    expect(levels.anchorPrice).toBe(120);
  });
});

function makeCard(overrides: Partial<AdviceCard> = {}): AdviceCard {
  return {
    symbol: "2330",
    action: "hold",
    quantity_range: null,
    matched_rules: [],
    counterarguments: [],
    invalidation_conditions: [],
    confidence: "medium",
    confidence_meaning: "x",
    rules_version: "1.0.2",
    as_of: "2026-09-18T09:00:00+08:00",
    observation_window: { start: "2025-05-01", end: "2026-09-18", bars: 300 },
    disclaimer: "x",
    limits_check: [],
    action_weights: [],
    direction_weights: [],
    has_conflict: false,
    aggregated_action: "hold",
    blocked_action: null,
    blocked_notices: [],
    downgrade_notices: [],
    evaluation: { total_rules: 1, evaluated_rules: 1, matched_rules: 0, data_completeness: 1, skipped_rules: [] },
    ...overrides,
  };
}

function makeResponse(card: AdviceCard | null, held = true): AdviceResponse {
  return {
    symbol: "2330",
    market: "TW",
    status: card === null ? "insufficient_data" : "ok",
    reason: card === null ? "資料不足，無法計算。" : null,
    as_of: "2026-09-18T09:00:00+08:00",
    held,
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

const card = (bars: Bar[] | null, anchorSource: "cost" | "close-unknown" | "holding-unknown" = "cost"): string =>
  renderToStaticMarkup(
    createElement(DecisionCardBody, {
      response: makeResponse(makeCard()),
      bars,
      anchorSource,
      avgCost: anchorSource === "cost" ? 100 : null,
    }),
  );

const panel = (bars: Bar[], anchorSource: "cost" | "close-not-held" | "close-unknown" | "holding-unknown" = "cost"): string =>
  renderToStaticMarkup(createElement(KeyLevelsPanel, { bars, avgCost: 100, anchorSource }));

/** The `<details>` of the 4-Q qualifier, with its summary text and its explanation paragraph. */
function stopDetails(html: string): { summary: string; explanation: string; block: string } | null {
  const m = html.match(
    /<details class="group mt-0\.5 w-full"><summary class="([^"]*)">[\s\S]*?<\/span>([^<]*)<\/summary><p class="([^"]*)">([^<]*)<\/p><\/details>/,
  );
  if (m === null) return null;
  return { summary: m[2]!, explanation: m[4]!, block: m[0] };
}

describe("決策卡：4-Q／4-E（C-10）與停利格移出（C-11）", () => {
  it("有 ATR（≥ 15 根）：停損格下方是 4-Q，點擊展開 4-E（有 ATR 版）；字級 text-xs、顏色 neutral-400", () => {
    const d = stopDetails(card(steadyBars(30)));
    expect(d).not.toBeNull();
    expect(d!.summary).toBe(STOP_QUALIFIER);
    expect(d!.explanation).toBe(STOP_EXPLANATION_WITH_ATR);
    expect(d!.block).toContain('<p class="mt-1 text-xs text-neutral-400">');
    expect(d!.block).toContain("text-xs text-neutral-400");
    expect(d!.block).not.toMatch(/title=|opacity|sr-only|truncate|line-clamp|neutral-500|neutral-600/);
  });

  it("無 ATR（< 15 根）：展開的是 4-E 無 ATR 版", () => {
    const d = stopDetails(card(steadyBars(10)));
    expect(d).not.toBeNull();
    expect(d!.explanation).toBe(STOP_EXPLANATION_WITHOUT_ATR);
  });

  it("停損數字是「—」時不顯示（bars 不可用、持倉狀態未知）", () => {
    expect(card(null)).not.toContain(STOP_QUALIFIER);
    expect(card(steadyBars(30), "close-unknown")).not.toContain(STOP_QUALIFIER);
    expect(card(steadyBars(30), "holding-unknown")).not.toContain(STOP_QUALIFIER);
  });

  it("no_price：不顯示 4-Q／4-E", () => {
    const html = renderToStaticMarkup(
      createElement(DecisionCardBody, {
        response: makeResponse(null),
        bars: steadyBars(30),
        anchorSource: "cost",
        avgCost: 100,
      }),
    );
    expect(html).not.toContain(STOP_QUALIFIER);
  });

  it("展開時停損格佔滿整列（has-open:col-span-full），不擠在窄格內；不只靠 hover", () => {
    const html = card(steadyBars(30));
    expect(html).toContain("has-open:col-span-full");
    expect(html).not.toMatch(/group-hover|hover:block|hover:inline/);
  });

  it("停利格與停利距離從決策卡移除：沒有「停利參考」標題、沒有 2R 數字、格數為三", () => {
    const html = card(steadyBars(30));
    const levels = computeKeyLevels(steadyBars(30))!;
    const fmt = (n: number): string => n.toLocaleString("zh-TW", { minimumFractionDigits: 2, maximumFractionDigits: 2 });
    // (The LM-16 basis sentence still names 「停利參考」 in prose; the cell label is what must be gone.)
    expect(html).not.toContain('<p class="text-sm text-neutral-400">停利參考</p>');
    expect(html).not.toContain(fmt(levels.target2R));
    expect(html).not.toMatch(/距最新收盤 \+/);
    const cellLabels = html.match(/<p class="text-sm text-neutral-400">[^<]*<\/p>/g) ?? [];
    expect(cellLabels).toHaveLength(3);
  });
});

describe("關鍵價位面板：4-Q／4-E、停利大字移出、4-T（C-10、C-11）", () => {
  it("主視圖停損大字下方有 4-Q，展開 4-E（依 ATR 二選一）", () => {
    const withAtr = stopDetails(panel(steadyBars(30)));
    expect(withAtr?.summary).toBe(STOP_QUALIFIER);
    expect(withAtr?.explanation).toBe(STOP_EXPLANATION_WITH_ATR);
    const without = stopDetails(panel(steadyBars(10)));
    expect(without?.explanation).toBe(STOP_EXPLANATION_WITHOUT_ATR);
  });

  it("持倉狀態未知（停損大字為「—」）：不顯示 4-Q", () => {
    expect(panel(steadyBars(30), "holding-unknown")).not.toContain(STOP_QUALIFIER);
  });

  it("主視圖沒有停利大字；停利參考卡（詳細內）標題下帶 4-T，階梯組標題帶 4-T", () => {
    const html = panel(steadyBars(30));
    const levels = computeKeyLevels(steadyBars(30))!;
    const bigNumbers = html.match(/<p class="mt-1 font-mono text-xl font-bold text-neutral-100">/g) ?? [];
    expect(bigNumbers).toHaveLength(1);
    // The target card (inside <details>) carries the tag directly under its title.
    expect(html).toContain(`<p class="text-neutral-400">${KEY_LEVELS_TARGET_CARD_TITLE}</p><p class="mt-1 text-neutral-400">${TARGET_FORMULA_TAG}</p>`);
    // The ladder's take-profit group title is the 4-T version, and the plain 「停利參考」 title is gone there.
    expect(html).toContain(TARGET_LADDER_GROUP_TITLE);
    // No big-number cell carries the take-profit title any more.
    expect(html).not.toContain(`${KEY_LEVELS_TARGET_CARD_TITLE}</p><p class="mt-1 font-mono text-xl`);
    expect(levels.target2R).toBeGreaterThan(levels.close);
  });
});

describe("操作摘要：4-附（C-12）", () => {
  const rule = (id: string, action: string): AdviceCard["matched_rules"][number] => ({
    id,
    name: `規則 ${id}`,
    action,
    weight: 0.6,
    weight_meaning: "x",
    explanation: "y",
    invalidation: null,
  });
  const render = (ruleId: string, held = true): string =>
    renderToStaticMarkup(
      createElement(SummaryBody, {
        response: makeResponse(
          makeCard({ action: "reduce", aggregated_action: "reduce", matched_rules: [rule(ruleId, "reduce")] }),
          held,
        ),
      }),
    );

  it.each(["drawdown_protection", "deep_drawdown_stop"])("最高權重規則是 %s：依據行同一行出現 4-附，不在 <details> 內", (id) => {
    const html = render(id);
    const mainEnd = html.indexOf('<details class="group mt-1">');
    expect(mainEnd).toBeGreaterThan(-1);
    const main = html.slice(0, mainEnd);
    const line = main.match(/<p class="text-sm text-neutral-300">[\s\S]*?<\/p>/)![0];
    expect(line).toContain(`規則 ${id}`);
    expect(line).toContain(DRAWDOWN_UNADJUSTED_NOTICE);
    expect(html.slice(mainEnd)).not.toContain(DRAWDOWN_UNADJUSTED_NOTICE);
  });

  it("其他規則：不顯示 4-附", () => {
    expect(render("rsi_overbought")).not.toContain(DRAWDOWN_UNADJUSTED_NOTICE);
  });

  it("結論被降級或封頂、沒有依據規則時不顯示", () => {
    const html = renderToStaticMarkup(
      createElement(SummaryBody, {
        response: makeResponse(
          makeCard({
            action: "hold",
            aggregated_action: "reduce",
            matched_rules: [rule("drawdown_protection", "reduce")],
          }),
        ),
      }),
    );
    expect(html).not.toContain(DRAWDOWN_UNADJUSTED_NOTICE);
  });

  it("candidate 沒有「依據」行，不顯示", () => {
    expect(render("drawdown_protection", false)).not.toContain(DRAWDOWN_UNADJUSTED_NOTICE);
  });
});

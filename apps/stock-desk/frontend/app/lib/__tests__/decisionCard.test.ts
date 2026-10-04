/**
 * 決策卡（`work/stock-desk-一眼一句簡化-派工單.md` §5.4／視覺規範 B.7）DOM 驗證。
 * 比照 `operationSummary.test.ts` 的作法：render `DecisionCardBody` 直接透過
 * `renderToStaticMarkup`，覆蓋 held（cost anchor）、not-held、close-unknown、
 * no_action、no_price、bars 為 null 六種狀態；並針對風控 required 條件 1／2
 * （距離小字前綴與符號、0.0% 邊界、「距現價」VETO）與條件 4／9／10（aria-label、
 * 股數＋alert 同層、StaleDataAlert）各自補一則專屬斷言。
 */

import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";
import type { AdviceCard, AdviceResponse, Bar } from "../types";
import { DecisionCardBody } from "../../position/[symbol]/DecisionCard";
import { computeKeyLevels } from "../keyLevels";
import {
  DECISION_CARD_ARIA_LABEL,
  DECISION_CARD_CROSSED_DISCLOSURE,
  DECISION_CARD_INVALIDATION_PREFIX,
  DECISION_CARD_INVALIDATION_PREFIX_ONE_OF,
  DECISION_CARD_QUANTITY_LABEL,
} from "../decisionCardWording";
import {
  CANDIDATE_CONFIDENCE_NOT_COMPARABLE_NOTE,
  CONFIDENCE_PREFIX,
  HELD_ACTION_LABELS,
  INSUFFICIENT_DATA_NO_EVALUATION,
  NOT_HELD_BADGE,
  QUANTITY_RANGE_ABSENT_SHORT,
  RULE_SOURCE_CHIP,
} from "../adviceWording";

function makeBars(
  n: number,
  closeOf: (i: number) => number = (i) => 100 + (i % 7),
): Bar[] {
  return Array.from({ length: n }, (_, i) => ({
    date: `2026-0${1 + Math.floor(i / 28)}-${String(1 + (i % 28)).padStart(2, "0")}`,
    open: "100",
    high: "105",
    low: "95",
    close: String(closeOf(i)),
    volume: 1000,
    currency: "TWD",
    source: "demo",
  }));
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
    as_of: "2026-09-18T09:00:00+08:00",
    observation_window: { start: "2025-05-01", end: "2026-09-18", bars: 300 },
    disclaimer: "本工具為研究與教育用途，非投資建議",
    limits_check: [],
    action_weights: [],
    direction_weights: [],
    has_conflict: false,
    aggregated_action: "add",
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
    ...overrides,
  };
}

function makeResponse(overrides: Partial<AdviceResponse> = {}): AdviceResponse {
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
    ...overrides,
  };
}

function renderCard(props: Parameters<typeof DecisionCardBody>[0]): string {
  return renderToStaticMarkup(createElement(DecisionCardBody, props));
}

describe("DecisionCardBody — held（持倉平均成本為基準）", () => {
  it("動作大字＋RULE_SOURCE_CHIP、四格數字（含距離前綴「距最新收盤 」）、股數、aria-label 皆存在；無「距現價」", () => {
    const bars = makeBars(80);
    const html = renderCard({
      response: makeResponse(),
      bars,
      anchorSource: "cost",
      avgCost: 120,
    });
    expect(html).toContain(HELD_ACTION_LABELS.add);
    expect(html).toContain(RULE_SOURCE_CHIP);
    expect(html).toContain("距最新收盤");
    expect(html).not.toContain("距現價");
    expect(html).toContain("500 ~ 1,000 股");
  });

  it("restores_compliance=false 且防禦型動作：role=alert 的 basis 出現在卡內，與股數同層（required 條件 9）", () => {
    const BASIS_ALERT =
      "目前部位超出「單一產業佔比上限」，建議量 200 股已為持股全數；該上限由其他部位驅動，賣出後仍為違反。";
    const bars = makeBars(80);
    const response = makeResponse({
      advice: makeCard({
        action: "reduce",
        quantity_range: {
          min_shares: 200,
          max_shares: 200,
          restores_compliance: false,
          basis: BASIS_ALERT,
        },
      }),
    });
    const html = renderCard({
      response,
      bars,
      anchorSource: "cost",
      avgCost: 120,
    });
    expect(html).toContain('role="alert"');
    expect(html).toContain(BASIS_ALERT);
    expect(html).toContain("200 ~ 200 股");
  });

  it("符號由算式動態決定（風控 required 條件 2）：avgCost 遠高於收盤，stopSuggested > close，停損距離必為正號", () => {
    // close 落在 100~106 之間（見 makeBars 預設），avgCost 遠高於此，
    // stopFixedPct=avgCost*0.92 仍遠大於 close，distance=(stop-close)/close×100 > 0。
    const bars = makeBars(80);
    const html = renderCard({
      response: makeResponse(),
      bars,
      anchorSource: "cost",
      avgCost: 100000,
    });
    expect(html).toMatch(/距最新收盤 \+\d+(\.\d)?%/);
    expect(html).not.toContain("距最新收盤 -");
  });
});

describe("DecisionCardBody — not-held（候選模式，anchorSource=close-not-held）", () => {
  it("支持分支：CANDIDATE_HEADING_LABEL＋compositionText 與 supportiveDisclaimer 同層、NOT_HELD_BADGE 徽章與 buildStopBasisConfirmedNotHeld 全句常駐", () => {
    const bars = makeBars(80);
    const response = makeResponse({
      held: false,
      advice: makeCard({
        action: "add",
        matched_rules: [makeCard().matched_rules[0]!],
      }),
    });
    const html = renderCard({
      response,
      bars,
      anchorSource: "close-not-held",
      avgCost: null,
    });
    expect(html).toContain("進場評估");
    expect(html).toContain("這不構成進場理由。");
    expect(html).toContain(NOT_HELD_BADGE);
    expect(html).toContain("未持有此標的，以最新收盤");
    expect(html).toContain("試算；此數字不是任何進場暗示。");
  });

  it("不支持分支：CANDIDATE_NOT_SUPPORTIVE_TEXT 常駐，且不含支持分支的 compositionText", () => {
    const bars = makeBars(80);
    const response = makeResponse({
      held: false,
      advice: makeCard({ action: "hold", matched_rules: [] }),
    });
    const html = renderCard({
      response,
      bars,
      anchorSource: "close-not-held",
      avgCost: null,
    });
    expect(html).toContain("本次未支持進場");
  });
});

describe("DecisionCardBody — close-unknown（持倉狀態未知）", () => {
  it("不得顯示「未持有」；停損／停利兩格「—」、不畫距離、不印基準標籤", () => {
    const bars = makeBars(80);
    const html = renderCard({
      response: makeResponse(),
      bars,
      anchorSource: "close-unknown",
      avgCost: null,
    });
    expect(html).not.toContain(NOT_HELD_BADGE);
    expect(html).not.toContain("距最新收盤");
    expect(html).not.toContain("基準價（");
    // 收盤仍照常顯示（不受 anchorSource 影響）——最後一根日線（index 79）收盤
    // 依 `makeBars` 預設公式 100 + (79 % 7) = 102。
    const levelsClose = (102).toLocaleString("zh-TW", {
      minimumFractionDigits: 2,
      maximumFractionDigits: 2,
    });
    expect(html).toContain(levelsClose);
  });

  // Q1（qa high，決策卡第二輪修正）：徽章與 buildStopBasisConfirmedNotHeld 全句
  // 必須同一個閘門，`levels === null`（bars 不可用）時全句仍常駐，價格印「—」。
  it("Q1：bars 為 null 且 anchorSource=close-not-held 時，NOT_HELD_BADGE 徽章與全句仍同時常駐，價格代入「—」", () => {
    const html = renderCard({
      response: makeResponse({
        held: false,
        advice: makeCard({ action: "hold" }),
      }),
      bars: null,
      anchorSource: "close-not-held",
      avgCost: null,
    });
    expect(html).toContain(NOT_HELD_BADGE);
    expect(html).toContain(
      "未持有此標的，以最新收盤 — 試算；此數字不是任何進場暗示。",
    );
  });
});

describe("DecisionCardBody — R2（決策卡第二輪修正）：兩來源矛盾時降級為 close-unknown", () => {
  it('model.kind === "held" 但 anchorSource === "close-not-held"：視同 close-unknown，不顯示未持有徽章／全句／基準標籤，停損停利「—」不畫距離', () => {
    const bars = makeBars(80);
    const html = renderCard({
      response: makeResponse(), // held: true, action: "add"
      bars,
      anchorSource: "close-not-held",
      avgCost: 120,
    });
    expect(html).not.toContain(NOT_HELD_BADGE);
    expect(html).not.toContain("未持有此標的，以最新收盤");
    expect(html).not.toContain("基準價（");
    expect(html).not.toContain("距最新收盤");
    // 動作大字仍照 held 分支正常顯示（矛盾只影響「持有狀態」相關的徽章/標籤/水位，不影響主字）。
    expect(html).toContain(HELD_ACTION_LABELS.add);
    expect(html).toContain(RULE_SOURCE_CHIP);
  });

  it('model.kind === "candidate" 但 anchorSource === "cost"：視同 close-unknown，不顯示未持有徽章／全句／基準標籤，停損停利「—」不畫距離', () => {
    const bars = makeBars(80);
    const html = renderCard({
      response: makeResponse({
        held: false,
        advice: makeCard({ action: "add" }),
      }),
      bars,
      anchorSource: "cost",
      avgCost: 120,
    });
    expect(html).not.toContain(NOT_HELD_BADGE);
    expect(html).not.toContain("未持有此標的，以最新收盤");
    expect(html).not.toContain("基準價（");
    expect(html).not.toContain("距最新收盤");
    // 主字仍照 candidate 分支正常顯示。
    expect(html).toContain("進場評估");
  });

  it("no_price／no_action 不受 R2 影響：即使 anchorSource=close-not-held，仍照 anchorSource 本身的規則常駐未持有徽章與全句", () => {
    const bars = makeBars(80);
    const noActionResponse = makeResponse({
      advice: makeCard({ action: "insufficient_data", quantity_range: null }),
    });
    const html = renderCard({
      response: noActionResponse,
      bars,
      anchorSource: "close-not-held",
      avgCost: null,
    });
    expect(html).toContain(NOT_HELD_BADGE);
    expect(html).toContain("未持有此標的，以最新收盤");
  });
});

describe("DecisionCardBody — no_action（規則引擎回報資料不足）", () => {
  it("主字「資料不足」＋常駐小字 INSUFFICIENT_DATA_NO_EVALUATION，不掛 RULE_SOURCE_CHIP", () => {
    const bars = makeBars(80);
    const response = makeResponse({
      advice: makeCard({ action: "insufficient_data", quantity_range: null }),
    });
    const html = renderCard({
      response,
      bars,
      anchorSource: "cost",
      avgCost: 120,
    });
    expect(html).toContain(HELD_ACTION_LABELS.insufficient_data);
    expect(html).toContain(INSUFFICIENT_DATA_NO_EVALUATION);
    expect(html).not.toContain(RULE_SOURCE_CHIP);
  });

  // Q2（qa medium，決策卡第二輪修正）：no_action 沒有 quantity_range 這個欄位
  // 可言，股數格印「—」，不得借用 held／candidate 專屬的 QUANTITY_RANGE_ABSENT_SHORT。
  it("股數格印「—」，不印 QUANTITY_RANGE_ABSENT_SHORT（Q2）", () => {
    const bars = makeBars(80);
    const response = makeResponse({
      advice: makeCard({ action: "insufficient_data", quantity_range: null }),
    });
    const html = renderCard({
      response,
      bars,
      anchorSource: "cost",
      avgCost: 120,
    });
    expect(html).not.toContain(QUANTITY_RANGE_ABSENT_SHORT);
    expect(html).toContain(
      `${DECISION_CARD_QUANTITY_LABEL}</p><p class="mt-1 break-words font-mono text-xl font-bold text-neutral-100">—</p>`,
    );
  });
});

describe("DecisionCardBody — no_price（連收盤價都沒有）", () => {
  it("主字位為 InsufficientPanel（既有元件），不渲染任何動作大字或 RULE_SOURCE_CHIP", () => {
    const response = makeResponse({
      status: "insufficient_data",
      reason: "資料不足，無法計算。",
      advice: null,
    });
    const html = renderCard({
      response,
      bars: null,
      anchorSource: "close-unknown",
      avgCost: null,
    });
    expect(html).toContain("資料不足，無法計算。");
    expect(html).not.toContain(RULE_SOURCE_CHIP);
  });

  // Q2（qa medium）：no_price 同樣沒有 quantity_range，股數格印「—」。
  it("股數格印「—」，不印 QUANTITY_RANGE_ABSENT_SHORT（Q2）", () => {
    const response = makeResponse({
      status: "insufficient_data",
      reason: "資料不足，無法計算。",
      advice: null,
    });
    const html = renderCard({
      response,
      bars: null,
      anchorSource: "close-unknown",
      avgCost: null,
    });
    expect(html).not.toContain(QUANTITY_RANGE_ABSENT_SHORT);
    expect(html).toContain(
      `${DECISION_CARD_QUANTITY_LABEL}</p><p class="mt-1 break-words font-mono text-xl font-bold text-neutral-100">—</p>`,
    );
  });
});

describe("DecisionCardBody — bars 為 null（日線不可用，與 advice 狀態無關）", () => {
  it("收盤／停損／停利三格印「—」，不畫距離", () => {
    const html = renderCard({
      response: makeResponse(),
      bars: null,
      anchorSource: "cost",
      avgCost: 120,
    });
    expect(html).not.toContain("距最新收盤");
    // 四格數字骨架仍完整掛載（B.7.5：缺席態不拿掉整卡骨架），三格數值印「—」。
    expect(html).toContain("最新收盤");
    expect(html).toContain("停損參考");
    expect(html).toContain("停利參考");
    const dashCount = html.split(">—<").length - 1;
    expect(dashCount).toBeGreaterThanOrEqual(3);
  });

  it("V1／風控 S-新1：距離槽在水位缺席時為不可見佔位（aria-hidden 的 &nbsp;），全卡「—」恰為三個數值格，距離槽不印「—」", () => {
    const html = renderCard({
      response: makeResponse(),
      bars: null,
      anchorSource: "cost",
      avgCost: 120,
    });
    // 收盤／停損／停利三格數值「—」；股數格有值（makeResponse 的 quantity_range）→ 恰三個。
    expect(html.split(">—<").length - 1).toBe(3);
    // 四個距離槽全部是 aria-hidden 佔位（收盤、股數無距離概念；停損、停利水位缺席）。
    // renderToStaticMarkup 會把 &nbsp; 輸出成 U+00A0 或實體，兩種都接受。
    const placeholders = html.match(/<p class="[^"]*" aria-hidden="true">(?:&nbsp;|\u00a0)<\/p>/g) ?? [];
    expect(placeholders).toHaveLength(4);
  });
});

describe("DecisionCardBody — 股數格版面（qa-e2e 第四輪：長字串溢位／貼合）", () => {
  const LONG_RANGES: Array<[number, number, string]> = [
    [3168, 5000, "3,168 ~ 5,000 股"],
    [10000, 12500, "10,000 ~ 12,500 股"],
  ];

  function renderLong(min: number, max: number): string {
    return renderCard({
      response: makeResponse({
        advice: makeCard({
          quantity_range: {
            min_shares: min,
            max_shares: max,
            restores_compliance: true,
            basis: "以「單一標的佔比上限」為最小可用額度換算。",
          },
        }),
      }),
      bars: makeBars(80),
      anchorSource: "cost",
      avgCost: 120,
    });
  }

  for (const [min, max, text] of LONG_RANGES) {
    it(`「${text}」：字面逐字保留，股數格 <p> 不含 whitespace-nowrap、可折行（break-words），字級不小於 text-xl`, () => {
      const html = renderLong(min, max);
      const m = html.match(
        new RegExp(`<p class="([^"]*)">${text}</p>`),
      );
      expect(m).not.toBeNull();
      const cls = m![1]!;
      expect(cls).not.toContain("whitespace-nowrap");
      expect(cls).toContain("break-words");
      expect(cls).toContain("text-xl");
      expect(cls).not.toMatch(/\btext-(xs|sm|base)\b/);
      expect(cls).not.toMatch(/\b(truncate|line-clamp|overflow-hidden)/);
    });

    it(`「${text}」：整張卡不再出現任何 whitespace-nowrap`, () => {
      expect(renderLong(min, max)).not.toContain("whitespace-nowrap");
    });
  }

  it("四格容器有 gap（欄距 gap-x 與列距 gap-y），相鄰數字不貼合；<md 為 2×2、md+ 為四欄", () => {
    const html = renderLong(3168, 5000);
    const m = html.match(/<div class="(grid [^"]*)">/);
    expect(m).not.toBeNull();
    const cls = m![1]!;
    expect(cls).toMatch(/\bgap-x-\d+\b/);
    expect(cls).toMatch(/\bgap-y-\d+\b/);
    expect(cls).toMatch(/\bgrid-cols-2\b/);
    expect(cls).toMatch(/\bmd:grid-cols-2\b/);
    expect(cls).toMatch(/\blg:grid-cols-4\b/);
    expect(cls).not.toMatch(/\bmd:grid-cols-4\b/);
  });

  it("格子本身 min-w-0（讓長字串能在 grid 欄內折行而非撐出頁面）", () => {
    expect(renderLong(10000, 12500)).toMatch(
      /<div class="[^"]*\bmin-w-0\b[^"]*"><p class="text-sm text-neutral-400">/,
    );
  });
});

describe("DecisionCardBody — 0.0% 邊界與 aria-label", () => {
  it("停損距離四捨五入為 0 時印 0.0%，不得印 -0.0%", () => {
    // anchorPrice = avgCost；ATR 不可得時 stopFixedPct = anchorPrice*0.92。
    // 讓 close 恰等於 stopFixedPct（=avgCost*0.92）使距離為 0。
    const avgCost = 100;
    const closeValue = avgCost * 0.92;
    const bars = makeBars(10, () => closeValue); // < 15 根，ATR 不可得。
    const html = renderCard({
      response: makeResponse(),
      bars,
      anchorSource: "cost",
      avgCost,
    });
    expect(html).toContain("距最新收盤 0.0%");
    expect(html).not.toContain("-0.0%");
  });

  it("<section aria-label={DECISION_CARD_ARIA_LABEL}> 存在，卡片不另外渲染 <h2> 可見標題", () => {
    const bars = makeBars(80);
    const html = renderToStaticMarkup(
      createElement(
        "section",
        { "aria-label": DECISION_CARD_ARIA_LABEL },
        createElement(DecisionCardBody, {
          response: makeResponse(),
          bars,
          anchorSource: "cost",
          avgCost: 120,
        }),
      ),
    );
    expect(html).toContain(`aria-label="${DECISION_CARD_ARIA_LABEL}"`);
    expect(html).not.toContain("<h2");
  });
});

describe("DecisionCardBody — StaleDataAlert 渲染在卡片內", () => {
  it("data.trading_days_behind 達過舊門檻時，StaleDataAlert 的 role=alert 通知句出現在卡片輸出中", () => {
    const bars = makeBars(80);
    const response = makeResponse({
      data: {
        status: "fresh",
        source: "twse",
        staleness_minutes: 5,
        is_within_ttl: null,
        bar_count: 300,
        first_bar_date: "2025-05-01",
        last_bar_date: "2026-09-10",
        trading_days_behind: 5,
        reason: null,
      },
    });
    const html = renderCard({
      response,
      bars,
      anchorSource: "cost",
      avgCost: 120,
    });
    expect(html).toMatch(
      /role="alert"[^>]*>[^<]*本評估所依據的收盤資料為 2026-09-10/,
    );
  });
});

// ---------------------------------------------------------------------------
// 決策卡「信心」與「一條失效條件」（風控 2026-10-03 審查 BLOCKING 1～5；CEO 選 K2）
// ---------------------------------------------------------------------------

const RSI_INVALIDATION = "RSI 回落至 50 與 70 之間，且收盤價維持在 20 日均線之上。";
const MA_INVALIDATION = "收盤價跌破 60 日均線，或 5 日均線下彎並跌破 20 日均線。";
const KD_INVALIDATION = "K 值重新向上穿越 D 值，或 K 值回落至 50 以下後止跌。";

function rule(
  id: string,
  action: string,
  weight: number,
  invalidation: string | null,
): AdviceCard["matched_rules"][number] {
  return {
    id,
    name: id,
    action,
    weight,
    weight_meaning: "權重為規則優先序，非機率、勝率或預期報酬",
    explanation: `${id} 的說明。`,
    invalidation,
  };
}

/** The review's counter-example: reduce wins on summed weight, MA stack is the heaviest single rule. */
function counterExampleCard(overrides: Partial<AdviceCard> = {}): AdviceCard {
  return makeCard({
    action: "reduce",
    aggregated_action: "reduce",
    matched_rules: [
      rule("uptrend_ma_stack", "add", 0.5, MA_INVALIDATION),
      rule("rsi_overbought", "reduce", 0.4, RSI_INVALIDATION),
      rule("kd_high_level_weakening", "reduce", 0.35, KD_INVALIDATION),
    ],
    // Deliberately in a different order than matched_rules: the body must come
    // from the picked rule, never from an index into this list.
    invalidation_conditions: [KD_INVALIDATION, MA_INVALIDATION, RSI_INVALIDATION],
    ...overrides,
  });
}

function renderHeld(card: AdviceCard, held = true, anchorSource: "cost" | "close-not-held" = "cost"): string {
  return renderCard({
    response: makeResponse({ held, advice: card }),
    bars: makeBars(80),
    anchorSource,
    avgCost: anchorSource === "cost" ? 120 : null,
  });
}

/** The MainSlot flex row (the first flex row of the card body that holds the action headline). */
function mainSlot(html: string): string {
  const m = html.match(/<div class="flex min-h-\[3\.5rem\][^"]*">([\s\S]*?)<\/div><div class="grid/);
  if (m === null) throw new Error("MainSlot not found");
  return m[1]!;
}

function invalidationParagraph(html: string): string | null {
  const m = html.match(/<p class="[^"]*">失效條件[^<]*<\/p>/);
  return m === null ? null : m[0];
}

const CONFIDENCE_RE = new RegExp(`${CONFIDENCE_PREFIX}(?:<!-- -->)?中`);

describe("DecisionCardBody — 信心行（BLOCKING 2／3；K2）", () => {
  it("held 且 action === aggregated_action：信心在 MainSlot 同一列、緊接 RULE_SOURCE_CHIP 之後，class 為 text-sm text-neutral-400", () => {
    const html = renderHeld(counterExampleCard());
    const slot = mainSlot(html);
    expect(slot).toContain(RULE_SOURCE_CHIP);
    const chipEnd = slot.indexOf(RULE_SOURCE_CHIP) + RULE_SOURCE_CHIP.length;
    const conf = slot.search(CONFIDENCE_RE);
    expect(conf).toBeGreaterThan(chipEnd);
    // Nothing but the chip's closing tag and the confidence span's opening tag in between.
    expect(slot.slice(chipEnd, conf)).toBe('</span><span class="text-sm text-neutral-400">');
    // Not in the footer / elsewhere: exactly one confidence line on the whole card.
    expect(html.match(new RegExp(CONFIDENCE_RE, "g"))).toHaveLength(1);
  });

  it("信心 class 與 OperationSummaryPanel 的信心 chip 完全相同，不上色、無 hover-only／title／tooltip", () => {
    const html = renderHeld(counterExampleCard());
    const m = html.match(/<span class="([^"]*)">信心 /);
    expect(m?.[1]).toBe("text-sm text-neutral-400");
    const tag = html.match(/<span[^>]*>信心 /)![0];
    expect(tag).not.toMatch(/title=|hidden|group-hover|hover:|opacity|sr-only/);
  });

  it("action !== aggregated_action（降級或被上限擋下）：信心與失效條件兩行都不渲染", () => {
    const html = renderHeld(
      counterExampleCard({ action: "hold", aggregated_action: "reduce" }),
    );
    expect(html).not.toMatch(CONFIDENCE_RE);
    expect(html).not.toContain(CONFIDENCE_PREFIX);
    expect(html).not.toContain("失效條件");
    // Heading is still the held conclusion.
    expect(html).toContain(RULE_SOURCE_CHIP);
  });

  it("aggregated_action 為 null 時（action !== aggregated_action）兩行都不渲染", () => {
    const html = renderHeld(counterExampleCard({ aggregated_action: null }));
    expect(html).not.toContain(CONFIDENCE_PREFIX);
    expect(html).not.toContain("失效條件");
  });

  it("K2：候選模式（支持與未支持）都不渲染信心行，也不出現 K1 句", () => {
    const supportive = renderHeld(
      makeCard({
        action: "add",
        aggregated_action: "add",
        matched_rules: [rule("uptrend_ma_stack", "add", 0.5, MA_INVALIDATION)],
        invalidation_conditions: [MA_INVALIDATION],
      }),
      false,
      "close-not-held",
    );
    const notSupportive = renderHeld(
      makeCard({ action: "hold", aggregated_action: "hold", matched_rules: [], invalidation_conditions: [] }),
      false,
      "close-not-held",
    );
    for (const html of [supportive, notSupportive]) {
      expect(html).not.toContain(CONFIDENCE_PREFIX);
      expect(html).not.toContain(CANDIDATE_CONFIDENCE_NOT_COMPARABLE_NOTE);
    }
  });

  it("no_action／no_price 不渲染信心行", () => {
    const noAction = renderHeld(
      counterExampleCard({ action: "insufficient_data", aggregated_action: "insufficient_data", quantity_range: null }),
    );
    const noPrice = renderCard({
      response: makeResponse({ status: "insufficient_data", reason: "資料不足，無法計算。", advice: null }),
      bars: null,
      anchorSource: "close-unknown",
      avgCost: null,
    });
    for (const html of [noAction, noPrice]) {
      expect(html).not.toContain(CONFIDENCE_PREFIX);
      expect(html).not.toContain("失效條件");
    }
  });
});

describe("DecisionCardBody — 失效條件行（BLOCKING 1／3／5）", () => {
  it("反例：減碼參考時取 rsi_overbought 的原文（不是權重最重的均線多頭排列、也不是索引第 0 項），句尾「。」保留、逐字", () => {
    const html = renderHeld(counterExampleCard());
    const p = invalidationParagraph(html);
    expect(p).not.toBeNull();
    expect(p).toContain(`${DECISION_CARD_INVALIDATION_PREFIX_ONE_OF}${RSI_INVALIDATION}</p>`);
    expect(html).not.toContain(MA_INVALIDATION);
    expect(html).not.toContain(KD_INVALIDATION);
  });

  it("前綴：invalidation_conditions.length === 1 → 「失效條件：」；>= 2 → 「失效條件之一：」", () => {
    const one = renderHeld(
      counterExampleCard({ invalidation_conditions: [RSI_INVALIDATION] }),
    );
    expect(invalidationParagraph(one)).toContain(
      `>${DECISION_CARD_INVALIDATION_PREFIX}${RSI_INVALIDATION}</p>`,
    );
    expect(one).not.toContain(DECISION_CARD_INVALIDATION_PREFIX_ONE_OF);
    const many = renderHeld(counterExampleCard());
    expect(invalidationParagraph(many)).toContain(`>${DECISION_CARD_INVALIDATION_PREFIX_ONE_OF}`);
  });

  it("前綴與內文同一個 <p>，class 恰為 text-xs text-neutral-400；無截斷／折疊／更淡／斜體／tooltip 類 class，且不在 <details> 內", () => {
    const html = renderHeld(counterExampleCard());
    const p = invalidationParagraph(html)!;
    expect(p).toMatch(/^<p class="mt-2 text-xs text-neutral-400">/);
    expect(p).not.toMatch(
      /truncate|line-clamp|max-h|overflow|nowrap|italic|neutral-500|neutral-600|opacity|hidden|hover:|title=|sr-only/,
    );
    // Whole-card: no <details> anywhere (the card never folds), no tooltip attribute on the line.
    expect(html).not.toContain("<details");
  });

  it("內文前後不拼接任何祈使或動作語：<p> 內容恰為 前綴＋原文", () => {
    const html = renderHeld(counterExampleCard());
    const text = invalidationParagraph(html)!.replace(/<[^>]+>/g, "");
    expect(text).toBe(`${DECISION_CARD_INVALIDATION_PREFIX_ONE_OF}${RSI_INVALIDATION}`);
  });

  it("invalidation_conditions 為空時整行不渲染", () => {
    const html = renderHeld(counterExampleCard({ invalidation_conditions: [] }));
    expect(html).not.toContain("失效條件");
  });

  it("選出的規則沒有 invalidation 文字（null）時整行不渲染，不退回索引或其他規則", () => {
    const html = renderHeld(
      counterExampleCard({
        matched_rules: [
          rule("uptrend_ma_stack", "add", 0.5, MA_INVALIDATION),
          rule("rsi_overbought", "reduce", 0.4, null),
          rule("kd_high_level_weakening", "reduce", 0.35, KD_INVALIDATION),
        ],
      }),
    );
    expect(html).not.toContain("失效條件");
    expect(html).not.toContain(KD_INVALIDATION);
  });

  it("沒有任何命中規則提議該 action 時整行不渲染", () => {
    const html = renderHeld(
      counterExampleCard({ matched_rules: [rule("uptrend_ma_stack", "add", 0.5, MA_INVALIDATION)] }),
    );
    expect(html).not.toContain("失效條件");
  });

  it("候選支持進場（action add）渲染；候選「本次未支持進場」不渲染", () => {
    const supportive = renderHeld(
      makeCard({
        action: "add",
        aggregated_action: "add",
        matched_rules: [rule("uptrend_ma_stack", "add", 0.5, MA_INVALIDATION)],
        invalidation_conditions: [MA_INVALIDATION],
      }),
      false,
      "close-not-held",
    );
    expect(invalidationParagraph(supportive)).toContain(
      `${DECISION_CARD_INVALIDATION_PREFIX}${MA_INVALIDATION}</p>`,
    );
    // Not supportive: even with an invalidation text and a hold rule on hand.
    const notSupportive = renderHeld(
      makeCard({
        action: "hold",
        aggregated_action: "hold",
        matched_rules: [rule("volume_spike_watch", "hold", 0.3, "成交量回到近 20 日均量附近。")],
        invalidation_conditions: ["成交量回到近 20 日均量附近。"],
      }),
      false,
      "close-not-held",
    );
    expect(notSupportive).not.toContain("失效條件");
    expect(notSupportive).toContain("本次未支持進場");
  });

  it("備選 B 與「此依據的失效條件：」不出現在任何狀態的輸出", () => {
    const outputs = [
      renderHeld(counterExampleCard()),
      renderHeld(counterExampleCard({ invalidation_conditions: [RSI_INVALIDATION] })),
    ];
    for (const html of outputs) {
      expect(html).not.toContain("此依據的失效條件");
      expect(html).not.toContain("（規則一致性與資料完整度）");
      expect(html).not.toMatch(/信心 (?:<!-- -->)?[低中高]（/);
    }
  });
});

/**
 * Risk review 2026-10-04 (`work/reviews/2026-10-04-決策卡-已越過水位-風控審查.md`)
 * required 2: crossed-level small print and the conditional disclosure line.
 * A single bar (< 15 bars, so no ATR) makes the references deterministic:
 * stop = avgCost x 0.92, target = avgCost + 2 x (avgCost - stop) = avgCost x 1.16.
 */
describe("DecisionCardBody — crossed reference levels (risk review 2026-10-04)", () => {
  const DISCLOSURE_P = `<p class="mt-2 text-xs text-neutral-400">${DECISION_CARD_CROSSED_DISCLOSURE}</p>`;
  const BANNED = ["已高於", "已低於", "越過", "已達", "觸發", "跌破此", "此水位 "];

  /** Small-print texts of the stop and target cells, in DOM order. */
  function distances(html: string): string[] {
    return [
      ...html.matchAll(/<p class="mt-0\.5 text-xs text-neutral-400">([^<]*)<\/p>/g),
    ].map((m) => m[1]!);
  }

  function renderCost(close: number, avgCost: number): string {
    return renderCard({
      response: makeResponse(),
      bars: makeBars(1, () => close),
      anchorSource: "cost",
      avgCost,
    });
  }

  function expectNoBanned(html: string): void {
    for (const banned of BANNED) expect(html).not.toContain(banned);
  }

  it("1305 vs target 1191.62: target cell prints 最新收盤高於此參考水位 +9.5% (denominator = target); stop cell keeps 距最新收盤", () => {
    // avgCost 1027.25 -> stop 945.07, target 1191.61.
    const html = renderCost(1305, 1027.25);
    expect(distances(html)).toEqual([
      "距最新收盤 -27.6%",
      "最新收盤高於此參考水位 +9.5%",
    ]);
    expect(html).toContain(DISCLOSURE_P);
    expectNoBanned(html);
  });

  it("900 vs stop 945.08: stop cell prints 最新收盤低於此參考水位 -4.8% (denominator = stop); target cell keeps 距最新收盤", () => {
    const html = renderCost(900, 1027.25);
    expect(distances(html)).toEqual([
      "最新收盤低於此參考水位 -4.8%",
      "距最新收盤 +32.4%",
    ]);
    expect(html).toContain(DISCLOSURE_P);
    expectNoBanned(html);
  });

  it("equality uses the original branch: 距最新收盤 0.0%, no crossed sentence, no disclosure line", () => {
    const levels = computeKeyLevels(makeBars(1, () => 100), 100)!;
    const atTarget = renderCost(levels.target2R, 100);
    expect(distances(atTarget)[1]).toBe("距最新收盤 0.0%");
    expect(atTarget).not.toContain("此參考水位");
    expect(atTarget).not.toContain(DECISION_CARD_CROSSED_DISCLOSURE);
    const atStop = renderCost(levels.stopSuggested, 100);
    expect(distances(atStop)[0]).toBe("距最新收盤 0.0%");
    expect(atStop).not.toContain("此參考水位");
    expect(atStop).not.toContain(DECISION_CARD_CROSSED_DISCLOSURE);
  });

  it("raw value above the level but rounded to 0: 最新收盤高於此參考水位 0.0% (and the stop mirror), strict comparison on raw values", () => {
    const levels = computeKeyLevels(makeBars(1, () => 100), 100)!;
    const above = renderCost(levels.target2R + 0.01, 100);
    expect(distances(above)[1]).toBe("最新收盤高於此參考水位 0.0%");
    expect(above).not.toContain("-0.0%");
    const below = renderCost(levels.stopSuggested - 0.01, 100);
    expect(distances(below)[0]).toBe("最新收盤低於此參考水位 0.0%");
    expect(below).not.toContain("-0.0%");
  });

  it("not crossed (stop < close < target): both cells keep 距最新收盤; disclosure line renders 0 times", () => {
    const html = renderCost(100, 100);
    expect(distances(html)).toEqual(["距最新收盤 -8.0%", "距最新收盤 +16.0%"]);
    expect(html).not.toContain("此參考水位");
    expect(html.split(DECISION_CARD_CROSSED_DISCLOSURE).length - 1).toBe(0);
  });

  it("disclosure line renders exactly once with a fixed class, and once even when both cells could cross", () => {
    const html = renderCost(1305, 1027.25);
    expect(html.split(DECISION_CARD_CROSSED_DISCLOSURE).length - 1).toBe(1);
    expect(html).toContain(DISCLOSURE_P);
    // Exact element string already rules out title / hover / opacity / sr-only / colour on the <p> itself.
    for (const extra of ["title=", "opacity", "sr-only", "<details", "truncate", "line-clamp", "overflow-hidden", "whitespace-nowrap"]) {
      expect(DISCLOSURE_P).not.toContain(extra);
    }
  });

  it("disclosure line sits after the anchor label paragraph", () => {
    const html = renderCost(1305, 1027.25);
    const anchorIdx = html.indexOf("基準價");
    expect(anchorIdx).toBeGreaterThan(-1);
    expect(html.indexOf(DECISION_CARD_CROSSED_DISCLOSURE)).toBeGreaterThan(anchorIdx);
  });

  it("crossed sentence and number share one <p>, with no nowrap / truncate / line-clamp / max-h / overflow-hidden / title", () => {
    for (const html of [renderCost(1305, 1027.25), renderCost(900, 1027.25)]) {
      const crossed = [
        ...html.matchAll(/<p class="[^"]*">最新收盤[高低]於此參考水位 [+-]?\d+\.\d%<\/p>/g),
      ].map((m) => m[0]);
      expect(crossed).toHaveLength(1);
      expect(crossed[0]).toMatch(/^<p class="mt-0\.5 text-xs text-neutral-400">/);
      expect(crossed[0]).not.toMatch(/nowrap|truncate|line-clamp|max-h-|overflow|title=|opacity|sr-only/);
    }
  });

  it("no crossed sentence or disclosure for close-not-held, close-unknown and the R2 downgrades, even if the numbers would cross", () => {
    const bars = makeBars(1, () => 1305);
    const cases: Array<Parameters<typeof DecisionCardBody>[0]> = [
      // close-not-held: anchor is the close itself.
      { response: makeResponse({ held: false, advice: makeCard({ action: "hold" }) }), bars, anchorSource: "close-not-held", avgCost: 1027.25 },
      // close-unknown: levels suppressed entirely.
      { response: makeResponse(), bars, anchorSource: "close-unknown", avgCost: 1027.25 },
      // R2: held advice but close-not-held source.
      { response: makeResponse(), bars, anchorSource: "close-not-held", avgCost: 1027.25 },
      // R2: candidate advice but cost source.
      { response: makeResponse({ held: false, advice: makeCard({ action: "add" }) }), bars, anchorSource: "cost", avgCost: 1027.25 },
    ];
    for (const props of cases) {
      const html = renderCard(props);
      expect(html).not.toContain("此參考水位");
      expect(html).not.toContain(DECISION_CARD_CROSSED_DISCLOSURE);
      expectNoBanned(html);
    }
  });

  it("bars unavailable (null): no crossed sentence or disclosure line", () => {
    const html = renderCard({ response: makeResponse(), bars: null, anchorSource: "cost", avgCost: 1027.25 });
    expect(html).not.toContain("此參考水位");
    expect(html).not.toContain(DECISION_CARD_CROSSED_DISCLOSURE);
  });
});

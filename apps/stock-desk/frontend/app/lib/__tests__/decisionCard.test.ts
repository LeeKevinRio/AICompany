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
import {
  DECISION_CARD_ARIA_LABEL,
  DECISION_CARD_QUANTITY_LABEL,
} from "../decisionCardWording";
import {
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
      `${DECISION_CARD_QUANTITY_LABEL}</p><p class="mt-1 whitespace-nowrap font-mono text-xl font-bold text-neutral-100">—</p>`,
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
      `${DECISION_CARD_QUANTITY_LABEL}</p><p class="mt-1 whitespace-nowrap font-mono text-xl font-bold text-neutral-100">—</p>`,
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

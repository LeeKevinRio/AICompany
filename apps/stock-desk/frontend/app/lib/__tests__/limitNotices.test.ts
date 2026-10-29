/**
 * Risk remediation item 2 (CEO ruling #59; risk-compliance final wording
 * `work/reviews/2026-10-26-風控五項整改字面逐字審-風控.md`, constraints C-5, C-6):
 * the decision card's limit block.
 *
 * Test kind: every block here is 行為新增 (the screen showed none of these
 * sentences before) except the literal pins, which are 字面更新 only in the sense
 * that they pin new literals. Each block names the literal it protects.
 */

import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";
import type { AdviceCard, AdviceResponse, Bar, CardAction, LimitCheck, LimitStatus } from "../types";
import { DecisionCardBody } from "../../position/[symbol]/DecisionCard";
import { FRONTEND_FORBIDDEN_TERMS, HELD_ACTION_LABELS } from "../adviceWording";
import { buildLimitNotices, limitShortName } from "../limitNotices";
import {
  buildLimitsDoNotChangeActionNotice,
  buildMultiViolationLine,
  buildMultiViolationTitle,
  buildNotEvaluableLimitsNotice,
  buildSingleViolationLine,
} from "../riskRemediationWording";
import { assertNoForbiddenTerms, findBareRealtimeClaims } from "./wordingScanHelpers";

function limit(
  index: number,
  id: string,
  name: string,
  status: LimitStatus,
  observed: number | null,
  threshold: number | null,
): LimitCheck {
  return { index, id, name, status, detail: `${name} 的說明句`, observed, threshold };
}

const CAP1_VIOLATED = limit(1, "single_position_weight", "單一標的佔比上限", "violated", 0.3579, 0.15);
const CAP2_NOT_EVALUABLE = limit(2, "sector_weight", "單一產業佔比上限", "not_evaluable", null, 0.3);
const CAP3_PASSED = limit(3, "gross_exposure", "總曝險上限", "passed", 0.5, 1);
const CAP4_VIOLATED = limit(4, "per_trade_loss", "單筆最大可承受虧損", "violated", 0.0152, 0.01);
const CAP5_VIOLATED = limit(5, "kelly_fraction", "分數 Kelly 部位上限", "violated", 0.2, 0.1);
const CAP5_NOT_EVALUABLE = limit(5, "kelly_fraction", "分數 Kelly 部位上限", "not_evaluable", null, null);

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

function makeCard(overrides: Partial<AdviceCard> = {}): AdviceCard {
  return {
    symbol: "2330",
    action: "hold",
    quantity_range: null,
    matched_rules: [],
    counterarguments: [],
    invalidation_conditions: [],
    confidence: "medium",
    confidence_meaning: "信心等級反映規則一致性與資料完整度，非勝率或機率",
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

function makeResponse(card: AdviceCard, held: boolean): AdviceResponse {
  return {
    symbol: "2330",
    market: "TW",
    status: "ok",
    reason: null,
    as_of: "2026-09-18T09:00:00+08:00",
    held,
    position_ids: [1],
    portfolio_context: {} as unknown as AdviceResponse["portfolio_context"],
    context_notes: [],
    cap1_migration_notice: null,
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

function render(card: AdviceCard, held = true): string {
  return renderToStaticMarkup(
    createElement(DecisionCardBody, {
      response: makeResponse(card, held),
      bars: makeBars(80),
      anchorSource: held ? "cost" : "close-not-held",
      avgCost: held ? 120 : null,
    }),
  );
}

describe("字面逐字（保護 2-V／2-M／2-R／2-O 定稿表字面）", () => {
  it("2-V：有數值時帶「（上限 …）」；observed 或 threshold 為 null 時只留簡稱，不印「—」或 null", () => {
    expect(buildSingleViolationLine(1, "單一標的佔比", "35.79%", "15.00%")).toBe(
      "已違反第 1 條上限：單一標的佔比 35.79%（上限 15.00%）",
    );
    expect(buildSingleViolationLine(1, "單一標的佔比", null, "15.00%")).toBe("已違反第 1 條上限：單一標的佔比");
    expect(buildSingleViolationLine(1, "單一標的佔比", "35.79%", null)).toBe("已違反第 1 條上限：單一標的佔比");
  });

  it("2-M：標題與逐條行", () => {
    expect(buildMultiViolationTitle(2)).toBe("已違反 2 條上限：");
    expect(buildMultiViolationLine(4, "單筆最大可承受虧損", "1.52%", "1.00%")).toBe(
      "第 4 條・單筆最大可承受虧損 1.52%（上限 1.00%）",
    );
  });

  it("2-R：動作標籤放進「」；句尾逐字", () => {
    expect(buildLimitsDoNotChangeActionNotice("續抱參考")).toBe(
      "「續抱參考」不代表你的部位在上限內；目前超過上限只會把加碼參考改為續抱參考，不會改成減碼參考。",
    );
  });

  it("2-O：有違反用「另有」，無違反用「有」", () => {
    expect(buildNotEvaluableLimitsNotice(2, true)).toBe("另有 2 條上限無法評估，不代表已通過；見下方建議卡。");
    expect(buildNotEvaluableLimitsNotice(2, false)).toBe("有 2 條上限無法評估，不代表已通過；見下方建議卡。");
  });

  it("2-R 句中直接寫了加碼、續抱、減碼三個標籤，必須與 HELD_ACTION_LABELS 一致（失效條件 T9）", () => {
    const notice = buildLimitsDoNotChangeActionNotice(HELD_ACTION_LABELS.hold);
    expect(notice).toContain(HELD_ACTION_LABELS.add);
    expect(notice).toContain(HELD_ACTION_LABELS.hold);
    expect(notice).toContain(HELD_ACTION_LABELS.reduce);
  });

  it("全部新句通過禁用詞與裸即時掃描，且不含否認建議性質的句子（C-1、審定條件 2）", () => {
    const samples = [
      buildSingleViolationLine(1, "單一標的佔比", "35.79%", "15.00%"),
      buildMultiViolationTitle(3),
      buildMultiViolationLine(4, "單筆最大可承受虧損", "1.52%", "1.00%"),
      buildLimitsDoNotChangeActionNotice("續抱參考"),
      buildNotEvaluableLimitsNotice(1, true),
      buildNotEvaluableLimitsNotice(1, false),
    ];
    for (const text of samples) {
      assertNoForbiddenTerms(text, FRONTEND_FORBIDDEN_TERMS, text);
      expect(findBareRealtimeClaims(text)).toEqual([]);
      for (const phrase of ["非投資建議", "不是建議", "僅供參考"]) expect(text).not.toContain(phrase);
    }
  });
});

describe("buildLimitNotices — 顯示條件（C-5、C-6）", () => {
  it("簡稱：name 去掉結尾的「上限」", () => {
    expect(limitShortName("單一標的佔比上限")).toBe("單一標的佔比");
    expect(limitShortName("單筆最大可承受虧損")).toBe("單筆最大可承受虧損");
  });

  it("1 條違反用 2-V（無標題），數值用 formatPercent", () => {
    const n = buildLimitNotices(makeCard({ limits_check: [CAP1_VIOLATED, CAP3_PASSED] }), "held");
    expect(n.violationTitle).toBeNull();
    expect(n.violationLines).toEqual(["已違反第 1 條上限：單一標的佔比 35.79%（上限 15.00%）"]);
  });

  it("2 條以上違反用 2-M：標題＋逐條行", () => {
    const n = buildLimitNotices(makeCard({ limits_check: [CAP1_VIOLATED, CAP4_VIOLATED] }), "held");
    expect(n.violationTitle).toBe("已違反 2 條上限：");
    expect(n.violationLines).toEqual([
      "第 1 條・單一標的佔比 35.79%（上限 15.00%）",
      "第 4 條・單筆最大可承受虧損 1.52%（上限 1.00%）",
    ]);
  });

  it("violated 但 observed 或 threshold 為 null：不印「—」或 null", () => {
    const n = buildLimitNotices(
      makeCard({ limits_check: [limit(1, "single_position_weight", "單一標的佔比上限", "violated", null, 0.15)] }),
      "held",
    );
    expect(n.violationLines).toEqual(["已違反第 1 條上限：單一標的佔比"]);
    expect(n.violationLines.join("")).not.toMatch(/—|null/);
  });

  // 風控 2026-10-26 D-4 修訂 C-5（方案 D 日落期間）：2-V／2-M／2-R 以第 5 條「狀態」排除，
  // 不以條號排除。日落期間第 5 條仍可能 violated 並擋下加碼，所以照常列入；
  // 5-K 之後它回報 disabled，自然不進入只收 violated 的清單。
  it("D-4：只有第 5 條違反時，照常顯示 2-V 與 2-R（不再以條號排除）", () => {
    const n = buildLimitNotices(makeCard({ limits_check: [CAP3_PASSED, CAP5_VIOLATED] }), "held");
    expect(n.violationLines).toEqual(["已違反第 5 條上限：分數 Kelly 部位 20.00%（上限 10.00%）"]);
    expect(n.actionNotice).not.toBeNull();
  });

  it("D-4：第 5 條計入條數：第 1、5 條違反時是 2-M（2 條）", () => {
    const n = buildLimitNotices(makeCard({ limits_check: [CAP1_VIOLATED, CAP5_VIOLATED] }), "held");
    expect(n.violationTitle).not.toBeNull();
    expect(n.violationLines).toHaveLength(2);
    expect(n.violationLines[1]).toContain("第 5 條・分數 Kelly 部位");
  });

  it("D-4：清單只收 violated，非 violated 狀態的第 5 條一律不進 2-V／2-M／2-R", () => {
    for (const cap5 of [CAP5_NOT_EVALUABLE, limit(5, "kelly_fraction", "分數 Kelly 部位上限", "passed", 0.05, 0.1)]) {
      const n = buildLimitNotices(makeCard({ limits_check: [CAP3_PASSED, cap5] }), "held");
      expect(n.violationLines).toEqual([]);
      expect(n.actionNotice).toBeNull();
    }
  });

  it("2-O 不計第 5 條；有違反用「另有」，無違反用「有」，有幾條 not_evaluable 就寫幾", () => {
    const withViolation = buildLimitNotices(
      makeCard({ limits_check: [CAP1_VIOLATED, CAP2_NOT_EVALUABLE, CAP5_NOT_EVALUABLE] }),
      "held",
    );
    expect(withViolation.notEvaluableNotice).toBe("另有 1 條上限無法評估，不代表已通過；見下方建議卡。");
    const without = buildLimitNotices(
      makeCard({
        limits_check: [CAP2_NOT_EVALUABLE, limit(4, "per_trade_loss", "單筆最大可承受虧損", "not_evaluable", null, 0.01)],
      }),
      "held",
    );
    expect(without.notEvaluableNotice).toBe("有 2 條上限無法評估，不代表已通過；見下方建議卡。");
    expect(without.violationLines).toEqual([]);
  });

  it("只有第 5 條 not_evaluable：2-O 不出現", () => {
    expect(buildLimitNotices(makeCard({ limits_check: [CAP5_NOT_EVALUABLE] }), "held").notEvaluableNotice).toBeNull();
  });

  it("全部通過、沒有任何待顯示內容：hasAny 為 false", () => {
    expect(buildLimitNotices(makeCard({ limits_check: [CAP3_PASSED] }), "held").hasAny).toBe(false);
    expect(buildLimitNotices(makeCard({ limits_check: [] }), "held").hasAny).toBe(false);
  });

  // 行為變更（風控修訂 C-6，2026-10-26 裁定）：2-R 只限 held 且 action 為 hold；
  // reduce／take_profit／stop_loss 原本顯示，現改為不顯示。{動作} 仍取 HELD_ACTION_LABELS[action]。
  const ACTIONS: ReadonlyArray<{ action: CardAction; shown: boolean }> = [
    { action: "hold", shown: true },
    { action: "reduce", shown: false },
    { action: "take_profit", shown: false },
    { action: "stop_loss", shown: false },
    { action: "add", shown: false },
    { action: "insufficient_data", shown: false },
  ];
  for (const { action, shown } of ACTIONS) {
    it(`2-R：held、第 1 條違反、action=${action} → ${shown ? "顯示並取該動作的標籤" : "不顯示"}`, () => {
      const n = buildLimitNotices(makeCard({ action, limits_check: [CAP1_VIOLATED] }), "held");
      expect(n.actionNotice).toBe(shown ? buildLimitsDoNotChangeActionNotice(HELD_ACTION_LABELS[action]) : null);
    });
  }

  // 行為新增（風控修訂 C-6）：00631L 型 fixture——reduce 加上第 1、4 條違反——沒有 2-R，
  // 但 2-M、2-O 照常顯示（保護 2-R 的顯示動作集合只含 hold）。
  it("2-R：reduce 加第 1、4 條違反（00631L 型）→ actionNotice 為 null，2-M 與 2-O 照常顯示", () => {
    const n = buildLimitNotices(
      makeCard({
        action: "reduce",
        aggregated_action: "reduce",
        limits_check: [CAP1_VIOLATED, CAP2_NOT_EVALUABLE, CAP4_VIOLATED, CAP5_NOT_EVALUABLE],
      }),
      "held",
    );
    expect(n.actionNotice).toBeNull();
    expect(n.violationTitle).toBe("已違反 2 條上限：");
    expect(n.violationLines).toHaveLength(2);
    expect(n.notEvaluableNotice).toBe("另有 1 條上限無法評估，不代表已通過；見下方建議卡。");
    expect(n.hasAny).toBe(true);
  });

  it("2-R：沒有任何違反（只有 not_evaluable）不顯示", () => {
    expect(buildLimitNotices(makeCard({ limits_check: [CAP2_NOT_EVALUABLE] }), "held").actionNotice).toBeNull();
  });

  it("candidate：顯示 2-V／2-M／2-O，但沒有 2-R，也沒有加碼被擋句", () => {
    const n = buildLimitNotices(
      makeCard({
        action: "hold",
        limits_check: [CAP1_VIOLATED, CAP2_NOT_EVALUABLE],
        blocked_notices: ["加碼建議被第 1 條上限（單一標的佔比上限）擋下。"],
      }),
      "candidate",
    );
    expect(n.violationLines).toHaveLength(1);
    expect(n.notEvaluableNotice).not.toBeNull();
    expect(n.actionNotice).toBeNull();
    expect(n.blockedNotices).toEqual([]);
  });

  it("加碼被擋句：held 且 blocked_notices 非空時原句上提，一字不改", () => {
    const sentence = "加碼建議被第 1 條上限（單一標的佔比上限）擋下。";
    const n = buildLimitNotices(makeCard({ limits_check: [CAP1_VIOLATED], blocked_notices: [sentence] }), "held");
    expect(n.blockedNotices).toEqual([sentence]);
  });
});

describe("DecisionCardBody — 上限區塊的位置與呈現（C-5、C-6）", () => {
  const BLOCKED = "加碼建議被第 1 條上限（單一標的佔比上限）擋下。";
  const card2330 = makeCard({
    action: "hold",
    aggregated_action: "add",
    blocked_action: "add",
    blocked_notices: [BLOCKED],
    limits_check: [CAP1_VIOLATED, CAP2_NOT_EVALUABLE, CAP4_VIOLATED, CAP5_NOT_EVALUABLE],
  });

  it("held 加碼被擋：順序為 2-M → 被擋句 → 2-R → 2-O，且都在數字格之後、失效條件行之前", () => {
    const html = render(
      makeCard({
        ...card2330,
        matched_rules: [
          {
            id: "uptrend_ma_stack",
            name: "均線多頭排列",
            action: "hold",
            weight: 0.5,
            weight_meaning: "x",
            explanation: "y",
            invalidation: "收盤價跌破 60 日均線。",
          },
        ],
        invalidation_conditions: ["收盤價跌破 60 日均線。"],
        aggregated_action: "hold",
      }),
    );
    const title = html.indexOf("已違反 2 條上限：");
    const line1 = html.indexOf("第 1 條・單一標的佔比 35.79%（上限 15.00%）");
    const line4 = html.indexOf("第 4 條・單筆最大可承受虧損 1.52%（上限 1.00%）");
    const blocked = html.indexOf(BLOCKED);
    const noChange = html.indexOf("不代表你的部位在上限內");
    const notEvaluable = html.indexOf("另有 1 條上限無法評估，不代表已通過；見下方建議卡。");
    const grid = html.indexOf('<div class="grid');
    const invalidation = html.indexOf("失效條件");
    for (const [name, idx] of Object.entries({ title, line1, line4, blocked, noChange, notEvaluable, grid, invalidation })) {
      expect(idx, name).toBeGreaterThan(-1);
    }
    expect(grid).toBeLessThan(title);
    expect(title).toBeLessThan(line1);
    expect(line1).toBeLessThan(line4);
    expect(line4).toBeLessThan(blocked);
    expect(blocked).toBeLessThan(noChange);
    expect(noChange).toBeLessThan(notEvaluable);
    expect(notEvaluable).toBeLessThan(invalidation);
    // 2-R names the action of the headline (hold after the block).
    expect(html).toContain("「續抱參考」不代表你的部位在上限內");
  });

  it("上限區塊在主畫面：不在任何 <details> 內，字級不小於 text-sm", () => {
    const html = render(card2330);
    const detailsBlocks = html.match(/<details[\s\S]*?<\/details>/g) ?? [];
    for (const block of detailsBlocks) {
      expect(block).not.toContain("已違反");
      expect(block).not.toContain("無法評估，不代表已通過");
    }
    const m = html.match(/<div class="([^"]*)"><p class="font-semibold">已違反 2 條上限：/);
    expect(m).not.toBeNull();
    expect(m![1]).toContain("text-sm");
    expect(m![1]).not.toMatch(/text-xs|truncate|line-clamp|hidden/);
  });

  // 行為新增（風控修訂 C-6）：渲染層也確認 reduce 的 00631L 型卡片沒有 2-R，其餘上限句與 3-S 都在。
  it("held reduce（00631L 型）：看不到 2-R，但 2-M、2-O 與 3-S 都在", () => {
    const html = render(
      makeCard({
        action: "reduce",
        aggregated_action: "reduce",
        limits_check: [CAP1_VIOLATED, CAP2_NOT_EVALUABLE, CAP4_VIOLATED, CAP5_NOT_EVALUABLE],
      }),
    );
    expect(html).not.toContain("不代表你的部位在上限內");
    expect(html).toContain("已違反 2 條上限：");
    expect(html).toContain("另有 1 條上限無法評估，不代表已通過；見下方建議卡。");
    expect(html).toContain("依固定規則產生的操作參考");
  });

  it("candidate：看得到違反與無法評估句，看不到 2-R 與被擋句", () => {
    const html = render(card2330, false);
    expect(html).toContain("已違反 2 條上限：");
    expect(html).toContain("另有 1 條上限無法評估");
    expect(html).not.toContain("不代表你的部位在上限內");
    expect(html).not.toContain(BLOCKED);
  });

  it("全部通過時不渲染區塊", () => {
    const html = render(makeCard({ limits_check: [CAP3_PASSED] }));
    expect(html).not.toContain("已違反");
    expect(html).not.toContain("無法評估，不代表已通過");
  });

  it("no_action（insufficient_data）：不渲染上限區塊", () => {
    const html = render(
      makeCard({ action: "insufficient_data", aggregated_action: "insufficient_data", limits_check: [CAP1_VIOLATED] }),
    );
    expect(html).not.toContain("已違反");
  });
});

/**
 * Contract test required by `work/stock-desk-phase8-風控定調.md` §2's
 * "required|測試義務": one test must assert the rendered summary carries
 * all eight required elements *simultaneously*, so a future presentation-
 * layer refactor cannot silently drop one while moving the rest — see
 * `operationSummary.ts`'s doc comment for why this is a plain unit test on
 * a pure function rather than a DOM-rendering test (no test framework
 * existed in this project before this batch; see the frontend-engineer
 * hand-off notes for the "vitest, minimal, no jsdom yet" trade-off).
 */

import { describe, expect, it } from "vitest";
import type { AdviceCard, AdviceResponse } from "../types";
import { buildOperationSummary } from "../operationSummary";
import {
  CANDIDATE_NOT_SUPPORTIVE_TEXT,
  CANDIDATE_SUPPORTIVE_DISCLAIMER,
  HELD_ACTION_LABELS,
  QUANTITY_RANGE_ABSENCE_TEXT,
} from "../adviceWording";

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
    counterarguments: ["均線由過去價格計算，轉折時排列會落後於價格。"],
    invalidation_conditions: ["收盤價跌破 60 日均線。"],
    confidence: "medium",
    confidence_meaning: "信心等級反映規則一致性與資料完整度，非勝率或機率",
    rules_version: "1.0.2",
    as_of: "2026-08-04T09:00:00+08:00",
    observation_window: { start: "2025-05-01", end: "2026-08-04", bars: 300 },
    disclaimer: "本工具為研究與教育用途，非投資建議",
    limits_check: [],
    action_weights: [{ action: "add", weight: 0.5, rule_ids: ["uptrend_ma_stack"] }],
    direction_weights: [{ direction: "constructive", weight: 0.5, actions: ["add"] }],
    has_conflict: false,
    aggregated_action: "add",
    blocked_action: null,
    blocked_notices: [],
    downgrade_notices: [],
    evaluation: {
      total_rules: 12,
      evaluated_rules: 10,
      matched_rules: 1,
      data_completeness: 0.8333,
      skipped_rules: [
        { id: "unrealized_pnl_check", name: "未實現損益檢查", reason: "缺少輸入欄位：未實現損益比率", missing_fields: ["pnl_ratio"] },
      ],
    },
    ...overrides,
  };
}

function makeResponse(
  overrides: Partial<Pick<AdviceResponse, "status" | "reason" | "advice" | "held" | "data">> = {},
): Pick<AdviceResponse, "status" | "reason" | "advice" | "held" | "data"> {
  return {
    status: "ok",
    reason: null,
    advice: makeCard(),
    held: true,
    data: {
      status: "fresh",
      source: "twse",
      staleness_minutes: 5,
      is_within_ttl: null,
      bar_count: 300,
      first_bar_date: "2025-05-01",
      last_bar_date: "2026-08-04",
      reason: null,
    },
    ...overrides,
  };
}

describe("buildOperationSummary — held mode", () => {
  it("carries all eight §2 required elements simultaneously on a normal add card", () => {
    const model = buildOperationSummary(makeResponse());
    expect(model.kind).toBe("held");
    if (model.kind !== "held") throw new Error("unreachable");

    // 1. fixed disclaimer
    expect(model.required.disclaimer).toBe("本工具為研究與教育用途，非投資建議");
    // 2. confidence + its meaning, same frame
    expect(model.required.confidence).toBe("medium");
    expect(model.required.confidenceMeaning).toContain("非勝率或機率");
    // 3. data basis date
    expect(model.required.asOfStatement).toContain("本評估基於");
    expect(model.required.asOfStatement).toContain("收盤資料");
    // 4. non-realtime system disclosure
    expect(model.required.nonRealtimeNotice).toContain("非即時報價");
    expect(model.required.nonRealtimeNotice).toContain("排程啟用時");
    // 5. at least one full counterargument + one full invalidation condition
    expect(model.required.counterarguments.length).toBeGreaterThanOrEqual(1);
    expect(model.required.invalidationConditions.length).toBeGreaterThanOrEqual(1);
    // 6. fixed rule-engine statement carrying the version
    expect(model.required.rulesStatement).toContain("1.0.2");
    expect(model.required.rulesStatement).toContain("非預測模型");
    // 7. quantity range present -> its text is populated, absence reason is not
    expect(model.required.quantityRangeText).not.toBeNull();
    expect(model.required.quantityAbsenceReason).toBeNull();
    // 8. candidate-only evidence notice must NOT appear in held mode
    expect(model.required.candidateEvidenceNotice).toBeNull();

    // Held-mode-specific: attribution + whitelist label present together (§1.1/§1.2).
    expect(model.attributedHeadline).toBe(`規則評估：${HELD_ACTION_LABELS.add}`);
    // AC-C6.1: main basis = the heaviest matched rule, not just "any" matched rule.
    expect(model.topMatchedRule).toEqual({
      name: "均線多頭排列",
      explanation: "5 日、20 日、60 日均線由上而下排列。",
    });
  });

  it("picks the heaviest matched rule as the main basis even when it is not first in the list (AC-C6.1)", () => {
    const model = buildOperationSummary(
      makeResponse({
        advice: makeCard({
          matched_rules: [
            {
              id: "light_rule",
              name: "輕權重規則",
              action: "add",
              weight: 0.2,
              weight_meaning: "權重為規則優先序，非機率、勝率或預期報酬",
              explanation: "輕權重規則的說明。",
            },
            {
              id: "heavy_rule",
              name: "重權重規則",
              action: "add",
              weight: 0.6,
              weight_meaning: "權重為規則優先序，非機率、勝率或預期報酬",
              explanation: "重權重規則的說明。",
            },
          ],
        }),
      }),
    );
    if (model.kind !== "held") throw new Error("unreachable");
    expect(model.topMatchedRule?.name).toBe("重權重規則");
  });

  it("falls back to the generic absence reason, not a rewritten cause, when quantity_range is null", () => {
    const model = buildOperationSummary(makeResponse({ advice: makeCard({ quantity_range: null }) }));
    if (model.kind !== "held") throw new Error("unreachable");
    expect(model.required.quantityRangeText).toBeNull();
    expect(model.required.quantityAbsenceReason).toBe(QUANTITY_RANGE_ABSENCE_TEXT);
  });

  it("surfaces the engine's own non-restoring basis text as a prominent warning (AC-C6.2)", () => {
    const model = buildOperationSummary(
      makeResponse({
        advice: makeCard({
          action: "reduce",
          quantity_range: {
            min_shares: 200,
            max_shares: 200,
            restores_compliance: false,
            basis: "目前部位超出「單一產業佔比上限」，建議量 200 股已為持股全數；該上限由其他部位驅動，賣出後仍為違反。",
          },
        }),
      }),
    );
    if (model.kind !== "held") throw new Error("unreachable");
    expect(model.restoresComplianceWarning).toContain("賣出後仍為違反");
  });

  it("shows insufficient_data with no action word, range, or reference figure (AC-C6.5)", () => {
    const model = buildOperationSummary(
      makeResponse({ advice: makeCard({ action: "insufficient_data", quantity_range: null }) }),
    );
    expect(model.kind).toBe("no_action");
    if (model.kind !== "no_action") throw new Error("unreachable");
    expect(model.reason).toBe(HELD_ACTION_LABELS.insufficient_data);
  });

  it("shows insufficient_data with a reason when there is no price at all (AC-C1.3)", () => {
    const model = buildOperationSummary(
      makeResponse({ status: "insufficient_data", advice: null, reason: "三層資料源皆無日線" }),
    );
    expect(model.kind).toBe("no_price");
    if (model.kind !== "no_price") throw new Error("unreachable");
    expect(model.reason).toBe("三層資料源皆無日線");
  });
});

describe("buildOperationSummary — candidate mode (FR-C7)", () => {
  it("carries all eight §2 required elements, plus the three candidate-only §3 disclosures, on a supportive card", () => {
    const model = buildOperationSummary(makeResponse({ held: false }));
    expect(model.kind).toBe("candidate");
    if (model.kind !== "candidate") throw new Error("unreachable");

    // Same eight, now candidateEvidenceNotice must be non-null (§2.8).
    expect(model.required.disclaimer).toBeTruthy();
    expect(model.required.confidence).toBeTruthy();
    expect(model.required.confidenceMeaning).toBeTruthy();
    expect(model.required.asOfStatement).toContain("本評估基於");
    expect(model.required.nonRealtimeNotice).toBeTruthy();
    expect(model.required.counterarguments.length).toBeGreaterThanOrEqual(1);
    expect(model.required.invalidationConditions.length).toBeGreaterThanOrEqual(1);
    expect(model.required.rulesStatement).toBeTruthy();
    expect(model.required.quantityRangeText !== null || model.required.quantityAbsenceReason !== null).toBe(true);
    expect(model.required.candidateEvidenceNotice).toContain("依賴持倉資料的規則未參與評估");

    // §3.1: `add` is a fact composition, never a positive conclusion, plus the
    // mandatory "does not constitute a reason to enter" sentence.
    expect(model.supportive).toBe(true);
    expect(model.compositionText).toContain("規則評估未命中防禦型規則");
    expect(model.compositionText).toContain("建設性規則命中 1 條");
    expect(model.supportiveDisclaimer).toBe(CANDIDATE_SUPPORTIVE_DISCLAIMER);

    // §3.3: quantified evidence density, not just prose.
    expect(model.coverageStatement).toContain("83.3%");
    expect(model.coverageStatement).toContain("1 條");

    // §3.4: confidence not comparable across modes.
    expect(model.notComparableNote).toContain("不可與持倉評估的等級直接比較");
  });

  it("uses the single fixed 'not supportive' wording for any non-add outcome, never a softened variant (AC-C7.3)", () => {
    const model = buildOperationSummary(
      makeResponse({
        held: false,
        advice: makeCard({
          action: "hold",
          matched_rules: [],
          counterarguments: [],
          invalidation_conditions: [],
        }),
      }),
    );
    if (model.kind !== "candidate") throw new Error("unreachable");
    expect(model.supportive).toBe(false);
    expect(model.notSupportiveText).toBe(CANDIDATE_NOT_SUPPORTIVE_TEXT);
    expect(model.notSupportiveText).not.toMatch(/可再觀察|時機未到|可留意/);
  });
});

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

import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";
import type { AdviceCard, AdviceResponse } from "../types";
import { buildSummaryFooterItems, buildOperationSummary } from "../operationSummary";
import { SummaryBody } from "../../position/[symbol]/OperationSummaryPanel";
import {
  AS_OF_AGE_UNKNOWN_STATEMENT,
  AS_OF_CALENDAR_UNCONFIRMED_STATEMENT,
  AS_OF_DATE_UNKNOWN_FULL_STATEMENT,
  AS_OF_DATE_UNKNOWN_STATEMENT,
  buildAsOfStatement,
  buildStaleDataProminentNotice,
  CANDIDATE_NOT_SUPPORTIVE_TEXT,
  CANDIDATE_NOT_SUPPORTIVE_TEXT_LEGACY,
  CANDIDATE_SUPPORTIVE_DISCLAIMER,
  CONFIDENCE_PREFIX,
  HELD_ACTION_LABELS,
  HELD_ACTION_LABELS_LEGACY,
  INSUFFICIENT_DATA_NO_EVALUATION,
  NOT_HELD_BADGE,
  QUANTITY_RANGE_ABSENCE_TEXT,
  QUANTITY_RANGE_ABSENT_SHORT,
  RULE_BASIS_PREFIX,
  RULE_SOURCE_CHIP,
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
      trading_days_behind: null,
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

    // Held-mode-specific: whitelist label (§1.2). wave3（派工單 §4.3 第 1 點）：
    // `buildAttributedHeadline` 回傳純標籤，不再烤入「規則評估：」前綴——來源
    // 感改由 `OperationSummaryPanel.tsx` 同列的 `RULE_SOURCE_CHIP` 承擔；舊版
    // 前綴串接見 `buildLegacyAttributedHeadline`（`adviceWording.test.ts` 逐字
    // 釘住）。
    expect(model.attributedHeadline).toBe(HELD_ACTION_LABELS.add);
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

  it("uses response.data.last_bar_date — not card.as_of's retrieval timestamp — for the YYYY-MM-DD basis date (qa-reviewer BLOCKING fix)", () => {
    // Deliberately cross-day: `as_of` is the retrieval timestamp of an
    // overnight cron run (`app/signals/frame.py::provenance`), one calendar
    // day *after* the trading date the price actually closed on — the
    // `cached_stale`/backup-source scenario the review flagged. The two
    // previously happened to share a date in every other fixture in this
    // file, which is exactly what let the bug through.
    //
    // trading_days_behind is a known 0 here (not null) so this fixture stays
    // scoped to the date-selection question it exists to test — the null-gap
    // "calendar unconfirmed" addition (句 1 CONFIRMED) has its own dedicated
    // four-branch tests below.
    const model = buildOperationSummary(
      makeResponse({
        advice: makeCard({ as_of: "2026-08-05T02:15:00+08:00" }),
        data: {
          status: "cached_stale",
          source: "twse",
          staleness_minutes: 900,
          is_within_ttl: true,
          bar_count: 300,
          first_bar_date: "2025-05-01",
          last_bar_date: "2026-08-04",
          trading_days_behind: 0,
          reason: null,
        },
      }),
    );
    if (model.kind !== "held") throw new Error("unreachable");
    expect(model.required.asOfStatement).toBe("本評估基於 2026-08-04 收盤資料。");
    // Literal YYYY-MM-DD only — no time-of-day component leaking through.
    expect(model.required.asOfStatement).toMatch(/本評估基於 \d{4}-\d{2}-\d{2} 收盤資料。/);
    expect(model.required.asOfStatement).not.toContain("T");
    expect(model.required.asOfStatement).not.toContain("2026-08-05");
  });

  it("falls back to observation_window.end when the envelope carries no last_bar_date at all", () => {
    // trading_days_behind is a known 0 here (not null) for the same reason as
    // the fixture above — the gap-null case has its own dedicated coverage.
    const model = buildOperationSummary(
      makeResponse({
        advice: makeCard({ observation_window: { start: "2025-05-01", end: "2026-08-03", bars: 299 } }),
        data: {
          status: "fresh",
          source: "twse",
          staleness_minutes: 5,
          is_within_ttl: null,
          bar_count: 300,
          first_bar_date: "2025-05-01",
          last_bar_date: null,
          trading_days_behind: 0,
          reason: null,
        },
      }),
    );
    if (model.kind !== "held") throw new Error("unreachable");
    expect(model.required.asOfStatement).toBe("本評估基於 2026-08-03 收盤資料。");
  });

  it(
    "S5 fix (risk-final-review.md 列管項): states the gap honestly instead of degrading to a dash " +
      "when neither last_bar_date nor observation_window.end is present",
    () => {
      const model = buildOperationSummary(
        makeResponse({
          advice: makeCard({ observation_window: { start: null, end: null, bars: null } }),
          data: {
            status: "fresh",
            source: "twse",
            staleness_minutes: 5,
            is_within_ttl: null,
            bar_count: 300,
            first_bar_date: null,
            last_bar_date: null,
            trading_days_behind: null,
            reason: null,
          },
        }),
      );
      if (model.kind !== "held") throw new Error("unreachable");
      // R-D5②-1 (風控逐字確認 2026-08-16): the slot carries both approved
      // sentences, in this order, as one paragraph. `staleDataNotice` is null
      // in this state (there is no date to measure age from), which is exactly
      // the silence the second sentence explains — asserted together here so a
      // change that drops the sentence while leaving the notice absent fails.
      expect(model.required.asOfStatement).toBe(
        "本評估未取得收盤資料的日期，無法標示評估所依據的資料時間。因此本次也無法判斷這份資料距今多久。",
      );
      expect(model.required.asOfStatement).toBe(AS_OF_DATE_UNKNOWN_FULL_STATEMENT);
      expect(model.required.asOfStatement).toContain(AS_OF_DATE_UNKNOWN_STATEMENT);
      expect(model.required.asOfStatement).toContain(AS_OF_AGE_UNKNOWN_STATEMENT);
      expect(model.staleDataNotice).toBeNull();
      expect(model.required.asOfStatement).not.toContain("—");
      expect(model.required.asOfStatement).not.toContain("本評估基於");
    },
  );

  it("never emits the age sentence when a basis date is known (it would be false there)", () => {
    // The追加句 explains a *missing* date. On a card that has one, the 資料過舊
    // notice is computable, so publishing "無法判斷距今多久" would contradict
    // what the panel shows right above it.
    const model = buildOperationSummary(makeResponse());
    if (model.kind !== "held") throw new Error("unreachable");
    expect(model.required.asOfStatement).not.toContain(AS_OF_AGE_UNKNOWN_STATEMENT);
  });

  it(
    "picks the heaviest matched rule as the main basis even when it points the opposite way from the " +
      "final (defensive-downgraded) action — current behaviour pinned as-is, not a fix: AC-C6.1 only asks " +
      "for \"the heaviest matched rule\", not \"the heaviest rule in the winning direction\", so whether a " +
      "direction-aware pick is required is an open PM/risk-compliance question, not decided by this test",
    () => {
      const model = buildOperationSummary(
        makeResponse({
          advice: makeCard({
            action: "hold",
            aggregated_action: "add",
            matched_rules: [
              {
                id: "defensive_rule",
                name: "防禦型規則",
                action: "stop_loss",
                weight: 0.4,
                weight_meaning: "權重為規則優先序，非機率、勝率或預期報酬",
                explanation: "防禦型規則命中，觸發加碼降級為觀望。",
              },
              {
                id: "add_rule",
                name: "均線多頭排列",
                action: "add",
                weight: 0.6,
                weight_meaning: "權重為規則優先序，非機率、勝率或預期報酬",
                explanation: "5 日、20 日、60 日均線由上而下排列。",
              },
            ],
            downgrade_notices: ["另有 1 條防禦型規則同時命中（防禦型規則），加碼建議改為觀望。"],
          }),
        }),
      );
      if (model.kind !== "held") throw new Error("unreachable");
      expect(model.action).toBe("hold");
      // Pinned: the weight-only pick surfaces the *constructive* rule as the
      // "main basis" even though the card's final action is the defensive
      // "hold" — a reader could misread this as contradicting the headline.
      expect(model.topMatchedRule).toEqual({
        name: "均線多頭排列",
        explanation: "5 日、20 日、60 日均線由上而下排列。",
      });
    },
  );

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
    // D3③: the common no-data case has no bar date to disclose the age of —
    // the notice stays absent, exactly as this screen always rendered.
    expect(model.staleDataNotice).toBeNull();
  });

  // D3③ (risk-fix-review.md N3 列管): the insufficient_data branches used to
  // drop the stale-data notice entirely, so an "insufficient data" screen
  // built over bars the calendar had moved past said nothing about their age.
  // Both branches now carry the same risk-approved sentence, under the same
  // trigger, as the held/candidate cards.
  it("[D3③] the no_action branch carries the stale-data notice when sessions were missed", () => {
    const model = buildOperationSummary(
      makeResponse({
        advice: makeCard({ action: "insufficient_data", quantity_range: null }),
        data: {
          status: "cached_stale",
          source: "twse",
          staleness_minutes: 4000,
          is_within_ttl: false,
          bar_count: 300,
          first_bar_date: "2025-05-01",
          last_bar_date: "2026-08-04",
          trading_days_behind: 5,
          reason: null,
        },
      }),
    );
    if (model.kind !== "no_action") throw new Error("unreachable");
    expect(model.staleDataNotice).toBe(buildStaleDataProminentNotice("2026-08-04", 5));
  });

  it("[D3③] the no_price branch carries the stale-data notice when the envelope still names an outdated bar date", () => {
    const model = buildOperationSummary(
      makeResponse({
        status: "insufficient_data",
        advice: null,
        reason: "資料筆數不足以計算指標",
        data: {
          status: "cached_stale",
          source: "twse",
          staleness_minutes: 4000,
          is_within_ttl: false,
          bar_count: 20,
          first_bar_date: "2026-07-01",
          last_bar_date: "2026-08-04",
          trading_days_behind: 3,
          reason: null,
        },
      }),
    );
    if (model.kind !== "no_price") throw new Error("unreachable");
    expect(model.staleDataNotice).toBe(buildStaleDataProminentNotice("2026-08-04", 3));
  });

  it("[D3③] the no_action branch stays silent when no session was missed", () => {
    const model = buildOperationSummary(
      makeResponse({
        advice: makeCard({ action: "insufficient_data", quantity_range: null }),
      }),
    );
    if (model.kind !== "no_action") throw new Error("unreachable");
    expect(model.staleDataNotice).toBeNull();
  });

  // R4 fix (risk-final-review.md): the "data older than one trading day"
  // notice must key off the age of `last_bar_date`, not off
  // `data.status === "cached_stale"` (a source-degradation signal, not a
  // data-age one). C4 (2026-08-13): "age" is the backend's observed
  // `trading_days_behind`, replacing the B1 calendar-day stand-in — see
  // tradingCalendar.ts's header.
  it("does NOT show the stale-data notice for a same-day cached_stale read (source downgrade alone is not staleness)", () => {
    const today = new Date().toISOString().slice(0, 10);
    const model = buildOperationSummary(
      makeResponse({
        data: {
          status: "cached_stale",
          source: "twse",
          staleness_minutes: 5,
          is_within_ttl: true,
          bar_count: 300,
          first_bar_date: "2025-05-01",
          last_bar_date: today,
          trading_days_behind: 0,
          reason: null,
        },
      }),
    );
    if (model.kind !== "held") throw new Error("unreachable");
    expect(model.staleDataNotice).toBeNull();
  });

  it("DOES show the stale-data notice from one missed trading session, even on a fresh read", () => {
    // C4: the threshold is back to the one 風控複審 2026-08-09 asked for —
    // a single session the market had and this series does not.
    const lastSession = "2026-08-04";
    const model = buildOperationSummary(
      makeResponse({
        data: {
          status: "fresh",
          source: "twse",
          staleness_minutes: 5,
          is_within_ttl: null,
          bar_count: 300,
          first_bar_date: "2025-05-01",
          last_bar_date: lastSession,
          trading_days_behind: 1,
          reason: null,
        },
      }),
    );
    if (model.kind !== "held") throw new Error("unreachable");
    // 風控複審 2026-08-09 裁決 b: the notice must name the actual basis date
    // and the size of the gap, not a vague magnitude-hiding phrase.
    expect(model.staleDataNotice).toBe(buildStaleDataProminentNotice(lastSession, 1));
    expect(model.staleDataNotice).toContain(lastSession);
  });

  it("reports the backend's session count verbatim, not a recomputed one", () => {
    const model = buildOperationSummary(
      makeResponse({
        data: {
          status: "cached_stale",
          source: "twse",
          staleness_minutes: 4000,
          is_within_ttl: false,
          bar_count: 300,
          first_bar_date: "2025-05-01",
          last_bar_date: "2026-08-04",
          trading_days_behind: 5,
          reason: null,
        },
      }),
    );
    if (model.kind !== "held") throw new Error("unreachable");
    expect(model.staleDataNotice).toBe(buildStaleDataProminentNotice("2026-08-04", 5));
  });

  it("[B1] does NOT show the stale-data notice across an unmodelled long closure (0 observed sessions)", () => {
    // The exact regression risk-fix-review.md flagged, now settled on the
    // backend: a 農曆年-length closure produces no bars, so no session is
    // counted and the gap arrives as 0 however many calendar days elapsed.
    const nineDaysAgo = new Date(Date.now() - 9 * 24 * 60 * 60 * 1000).toISOString().slice(0, 10);
    const model = buildOperationSummary(
      makeResponse({
        data: {
          status: "fresh",
          source: "twse",
          staleness_minutes: 5,
          is_within_ttl: null,
          bar_count: 300,
          first_bar_date: "2025-05-01",
          last_bar_date: nineDaysAgo,
          trading_days_behind: 0,
          reason: null,
        },
      }),
    );
    if (model.kind !== "held") throw new Error("unreachable");
    expect(model.staleDataNotice).toBeNull();
  });

  it("[C4 fail-safe] does NOT show the stale-data notice when the backend could not consult a calendar", () => {
    // `trading_days_behind === null` is "unknown", and an unknown gap is never
    // presented as an old one — the direction of failure B1 established.
    const longAgo = new Date(Date.now() - 40 * 24 * 60 * 60 * 1000).toISOString().slice(0, 10);
    const model = buildOperationSummary(
      makeResponse({
        data: {
          status: "fresh",
          source: "twse",
          staleness_minutes: 5,
          is_within_ttl: null,
          bar_count: 300,
          first_bar_date: "2025-05-01",
          last_bar_date: longAgo,
          trading_days_behind: null,
          reason: null,
        },
      }),
    );
    if (model.kind !== "held") throw new Error("unreachable");
    expect(model.staleDataNotice).toBeNull();
  });

  it("does NOT show the stale-data notice when last_bar_date is missing (no false trigger from an absent field)", () => {
    const model = buildOperationSummary(
      makeResponse({
        data: {
          status: "cached_stale",
          source: "twse",
          staleness_minutes: 5,
          is_within_ttl: true,
          bar_count: 300,
          first_bar_date: "2025-05-01",
          last_bar_date: null,
          trading_days_behind: null,
          reason: null,
        },
      }),
    );
    if (model.kind !== "held") throw new Error("unreachable");
    expect(model.staleDataNotice).toBeNull();
  });
});

describe(
  "句 1 CONFIRMED — as-of 語句的『交易日曆無法確認』揭露 " +
    "(2026-08-19, `work/reviews/2026-08-19-句1句3重寫-風控批審.md` 落地條件 1-6)",
  () => {
    it("① date unknown: renders AS_OF_DATE_UNKNOWN_FULL_STATEMENT only, mutually exclusive with the calendar-unconfirmed sentence, regardless of trading_days_behind", () => {
      const model = buildOperationSummary(
        makeResponse({
          advice: makeCard({ observation_window: { start: null, end: null, bars: null } }),
          data: {
            status: "fresh",
            source: "twse",
            staleness_minutes: 5,
            is_within_ttl: null,
            bar_count: 300,
            first_bar_date: null,
            last_bar_date: null,
            trading_days_behind: null,
            reason: null,
          },
        }),
      );
      if (model.kind !== "held") throw new Error("unreachable");
      expect(model.required.asOfStatement).toBe(AS_OF_DATE_UNKNOWN_FULL_STATEMENT);
      expect(model.required.asOfStatement).not.toContain(AS_OF_CALENDAR_UNCONFIRMED_STATEMENT);
    });

    it("② date known + gap known + below threshold: plain as-of sentence only, no calendar-unconfirmed addition", () => {
      const model = buildOperationSummary(
        makeResponse({
          data: {
            status: "fresh",
            source: "twse",
            staleness_minutes: 5,
            is_within_ttl: null,
            bar_count: 300,
            first_bar_date: "2025-05-01",
            last_bar_date: "2026-08-04",
            trading_days_behind: 0,
            reason: null,
          },
        }),
      );
      if (model.kind !== "held") throw new Error("unreachable");
      expect(model.required.asOfStatement).toBe(buildAsOfStatement("2026-08-04"));
      expect(model.required.asOfStatement).not.toContain(AS_OF_CALENDAR_UNCONFIRMED_STATEMENT);
      expect(model.staleDataNotice).toBeNull();
    });

    it("③ date known + gap known + at/above threshold: staleDataNotice fires but the calendar-unconfirmed sentence must NOT appear anywhere (no doubled-up wording with staleDataNotice)", () => {
      const model = buildOperationSummary(
        makeResponse({
          data: {
            status: "fresh",
            source: "twse",
            staleness_minutes: 5,
            is_within_ttl: null,
            bar_count: 300,
            first_bar_date: "2025-05-01",
            last_bar_date: "2026-08-04",
            trading_days_behind: 5,
            reason: null,
          },
        }),
      );
      if (model.kind !== "held") throw new Error("unreachable");
      // Reverse assertion (落地條件 5): the sentence must NOT appear once the
      // calendar has an answer, even a stale one.
      expect(model.required.asOfStatement).toBe(buildAsOfStatement("2026-08-04"));
      expect(model.required.asOfStatement).not.toContain(AS_OF_CALENDAR_UNCONFIRMED_STATEMENT);
      expect(model.staleDataNotice).toBe(buildStaleDataProminentNotice("2026-08-04", 5));
      expect(model.staleDataNotice).not.toContain(AS_OF_CALENDAR_UNCONFIRMED_STATEMENT);
    });

    it("④ date known + gap null (calendar could not be consulted): as-of sentence and the calendar-unconfirmed sentence ship together, as one string, verbatim", () => {
      const model = buildOperationSummary(
        makeResponse({
          data: {
            status: "fresh",
            source: "twse",
            staleness_minutes: 5,
            is_within_ttl: null,
            bar_count: 300,
            first_bar_date: "2025-05-01",
            last_bar_date: "2026-08-04",
            trading_days_behind: null,
            reason: null,
          },
        }),
      );
      if (model.kind !== "held") throw new Error("unreachable");
      expect(model.required.asOfStatement).toBe(
        buildAsOfStatement("2026-08-04") + AS_OF_CALENDAR_UNCONFIRMED_STATEMENT,
      );
      expect(model.required.asOfStatement).not.toBe(AS_OF_DATE_UNKNOWN_FULL_STATEMENT);
      // C4 fail-safe: an unconsulted calendar keeps staleDataNotice silent too
      // — asserted together so this cell's "two silences, one sentence" shape
      // is pinned as a unit.
      expect(model.staleDataNotice).toBeNull();
    });

    it("落地條件 1 rationale: fires off tradingDaysBehind===null, not lastBarDate===null — the observation_window.end fallback cell must trigger it too", () => {
      const model = buildOperationSummary(
        makeResponse({
          advice: makeCard({ observation_window: { start: "2025-05-01", end: "2026-08-03", bars: 299 } }),
          data: {
            status: "fresh",
            source: "twse",
            staleness_minutes: 5,
            is_within_ttl: null,
            bar_count: 300,
            first_bar_date: "2025-05-01",
            last_bar_date: null,
            trading_days_behind: null,
            reason: null,
          },
        }),
      );
      if (model.kind !== "held") throw new Error("unreachable");
      expect(model.required.asOfStatement).toBe(
        buildAsOfStatement("2026-08-03") + AS_OF_CALENDAR_UNCONFIRMED_STATEMENT,
      );
    });
  },
);

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

/**
 * 揭露下沉頁尾（風控第二次裁定後 required）：下沉不得在機制上等同刪除——候選／持有兩分支
 * 的頁尾句逐字、逐序釘住。
 */
describe("buildSummaryFooterItems — 頁尾操作摘要組", () => {
  it("held: asOfStatement、rulesStatement 依序", () => {
    const response = makeResponse({ held: true }) as AdviceResponse;
    const model = buildOperationSummary(response);
    expect(model.kind).toBe("held");
    if (model.kind !== "held") return;
    expect(buildSummaryFooterItems(response)).toEqual([model.required.asOfStatement, model.required.rulesStatement]);
  });

  it("candidate: notComparableNote、coverageStatement、asOfStatement、rulesStatement 依序，且四句皆非空（一眼一句 §2.3 R2：candidateEvidenceNotice 回到面板主視圖，不再下沉頁尾）", () => {
    const response = makeResponse({ held: false }) as AdviceResponse;
    const model = buildOperationSummary(response);
    expect(model.kind).toBe("candidate");
    if (model.kind !== "candidate") return;
    const items = buildSummaryFooterItems(response);
    expect(items).toEqual([
      model.notComparableNote,
      model.coverageStatement,
      model.required.asOfStatement,
      model.required.rulesStatement,
    ]);
    expect(items.every((s) => s.length > 0)).toBe(true);
    // 完整數字不簡化：覆蓋度句保留百分比與條數。
    expect(model.coverageStatement).toMatch(/\d/);
    // candidateEvidenceNotice 本身仍非空（面板主視圖渲染它），只是不再出現在這份頁尾清單裡。
    expect(model.required.candidateEvidenceNotice).toBeTruthy();
    expect(items).not.toContain(model.required.candidateEvidenceNotice);
  });

  it("no_price／no_action: []", () => {
    expect(
      buildSummaryFooterItems(makeResponse({ status: "insufficient_data", reason: "x", advice: null }) as AdviceResponse),
    ).toEqual([]);
    const noAction = makeResponse({ advice: makeCard({ action: "insufficient_data" }) }) as AdviceResponse;
    expect(buildOperationSummary(noAction).kind).toBe("no_action");
    expect(buildSummaryFooterItems(noAction)).toEqual([]);
  });
});

/**
 * 一眼一句實作規格 §2.3 第 4 點（`work/stock-desk-一眼一句-實作規格.md`）：
 * `quantityRangeText` used to bundle "{min} ~ {max} 股" together with the
 * card's own `basis` sentence — and the panel separately rendered
 * `restoresComplianceWarning` (the SAME `basis` text) as a red alert
 * whenever the range did not restore compliance on a defensive action,
 * printing `basis` twice. `quantityRangeShares`／`quantityRangeBasis` split
 * the bundle so the panel can place `basis` exactly once (R4).
 */
describe("quantityRangeShares／quantityRangeBasis 拆分（一眼一句 §2.3 第 4 點）", () => {
  it("拆出的兩個欄位各自對應 quantityRangeText 的兩半，且 quantityRangeText 保持不變（既有測試相容）", () => {
    const model = buildOperationSummary(makeResponse());
    if (model.kind !== "held") throw new Error("unreachable");
    expect(model.required.quantityRangeShares).toBe("500 ~ 1,000 股");
    expect(model.required.quantityRangeBasis).toBe(
      "以「單一標的佔比上限」為最小可用額度換算，最多可再買進 1000 股。",
    );
    expect(model.required.quantityRangeText).toBe(
      `${model.required.quantityRangeShares}。${model.required.quantityRangeBasis}`,
    );
  });

  it("quantity_range 為 null 時，shares／basis 皆為 null（與既有 quantityRangeText/quantityAbsenceReason 一致）", () => {
    const model = buildOperationSummary(makeResponse({ advice: makeCard({ quantity_range: null }) }));
    if (model.kind !== "held") throw new Error("unreachable");
    expect(model.required.quantityRangeShares).toBeNull();
    expect(model.required.quantityRangeBasis).toBeNull();
  });
});

/**
 * R4／FR-3（一眼一句 §2.3 第 4 點）: basis renders exactly once, page-wide —
 * as the `role="alert"` box when the range does not restore compliance on a
 * defensive action, otherwise tucked into `<details>`. Rendered via
 * `renderToStaticMarkup` (not just the model) so this is a true DOM
 * assertion, not just a data-shape one — the bug this guards against was a
 * rendering-layer duplication, not a data one.
 */
describe("basis 全頁只渲染一次（DOM，兩種 restores_compliance 情境）", () => {
  const BASIS_ALERT = "目前部位超出「單一產業佔比上限」，建議量 200 股已為持股全數；該上限由其他部位驅動，賣出後仍為違反。";
  const BASIS_NORMAL = "以「單一標的佔比上限」為最小可用額度換算，最多可再買進 1000 股。";

  function countOccurrences(haystack: string, needle: string): number {
    return haystack.split(needle).length - 1;
  }

  it("restores_compliance=false 且防禦型動作：basis 以 role=alert 呈現，且僅出現一次", () => {
    const response = makeResponse({
      advice: makeCard({
        action: "reduce",
        quantity_range: { min_shares: 200, max_shares: 200, restores_compliance: false, basis: BASIS_ALERT },
      }),
    }) as AdviceResponse;
    const html = renderToStaticMarkup(createElement(SummaryBody, { response }));
    expect(countOccurrences(html, BASIS_ALERT)).toBe(1);
    expect(html).toContain('role="alert"');
  });

  it("restores_compliance=true：basis 不在主視圖以 alert 呈現，且全頁（含 <details>）僅出現一次", () => {
    const response = makeResponse() as AdviceResponse; // restores_compliance: true fixture
    const html = renderToStaticMarkup(createElement(SummaryBody, { response }));
    expect(countOccurrences(html, BASIS_NORMAL)).toBe(1);
  });
});

/**
 * CEO 第二次裁定（2026-09-19 深夜，`work/stock-desk-一眼一句簡化-派工單.md`
 * §4）：disclaimer／confidenceMeaning 移出主視圖，只在 `<details>` 內渲染
 * （字面不變）。用實際渲染輸出（不只是原始碼掃描）驗證這兩句確實只出現在
 * `<details>...</details>` 這一段 HTML 之內。
 */
describe("disclaimer／confidenceMeaning 只在 <details> 內渲染（DOM，CEO 第二次裁定 2026-09-19）", () => {
  function detailsSlice(html: string): string {
    const start = html.indexOf("<details");
    expect(start, "html 應含 <details>").toBeGreaterThan(-1);
    return html.slice(start);
  }

  it("held 分支：disclaimer／confidenceMeaning 只出現在 <details> 片段內", () => {
    const response = makeResponse() as AdviceResponse;
    const html = renderToStaticMarkup(createElement(SummaryBody, { response }));
    const details = detailsSlice(html);
    const disclaimer = "本工具為研究與教育用途，非投資建議";
    const meaning = "信心等級反映規則一致性與資料完整度，非勝率或機率";
    expect(details).toContain(disclaimer);
    expect(details).toContain(meaning);
    // 主視圖（<details> 之前）不得含這兩句。
    const main = html.slice(0, html.indexOf("<details"));
    expect(main).not.toContain(disclaimer);
    expect(main).not.toContain(meaning);
  });

  it("candidate 分支：disclaimer／confidenceMeaning 只出現在 <details> 片段內", () => {
    const response = makeResponse({ held: false }) as AdviceResponse;
    const html = renderToStaticMarkup(createElement(SummaryBody, { response }));
    const disclaimer = "本工具為研究與教育用途，非投資建議";
    const meaning = "信心等級反映規則一致性與資料完整度，非勝率或機率";
    const main = html.slice(0, html.indexOf("<details"));
    const details = detailsSlice(html);
    expect(main).not.toContain(disclaimer);
    expect(main).not.toContain(meaning);
    expect(details).toContain(disclaimer);
    expect(details).toContain(meaning);
  });
});

/**
 * wave3（`work/stock-desk-一眼一句簡化-派工單.md` §4.3，風控逐字核可）：DOM
 * 層驗證新字面確實渲染在正確位置——不只是原始碼位置掃描
 * （`componentWordingScan.test.ts`），而是實際渲染輸出。
 */
describe("wave3 新字面 DOM 驗證（RULE_SOURCE_CHIP／CONFIDENCE_PREFIX／RULE_BASIS_PREFIX／NOT_HELD_BADGE／QUANTITY_RANGE_ABSENT_SHORT／INSUFFICIENT_DATA_NO_EVALUATION）", () => {
  it("held 分支：主視圖含 RULE_SOURCE_CHIP、CONFIDENCE_PREFIX+信心字、RULE_BASIS_PREFIX+規則名，不含舊「規則評估：」複合詞；舊字面搬進 <details>", () => {
    const response = makeResponse() as AdviceResponse;
    const html = renderToStaticMarkup(createElement(SummaryBody, { response }));
    const main = html.slice(0, html.indexOf("<details"));
    expect(main).toContain(RULE_SOURCE_CHIP);
    expect(main).toContain(`${CONFIDENCE_PREFIX}中`);
    // 「依據：」自成一個 <span>，其後緊接規則名的文字節點——分開比對而非找連續子字串。
    expect(main).toContain(RULE_BASIS_PREFIX);
    expect(main).toContain("均線多頭排列");
    expect(main.indexOf(RULE_BASIS_PREFIX)).toBeLessThan(main.indexOf("均線多頭排列"));
    expect(main).not.toContain("規則評估：");
    expect(main).not.toContain("信心等級：");
    const details = html.slice(html.indexOf("<details"));
    expect(details).toContain(`規則評估：${HELD_ACTION_LABELS_LEGACY.add}`);
  });

  it("held 分支：無股數區間時，主視圖印 QUANTITY_RANGE_ABSENT_SHORT，完整原因句只在 <details>", () => {
    const response = makeResponse({ advice: makeCard({ quantity_range: null }) }) as AdviceResponse;
    const html = renderToStaticMarkup(createElement(SummaryBody, { response }));
    const main = html.slice(0, html.indexOf("<details"));
    const details = html.slice(html.indexOf("<details"));
    expect(main).toContain(QUANTITY_RANGE_ABSENT_SHORT);
    expect(main).not.toContain(QUANTITY_RANGE_ABSENCE_TEXT);
    expect(details).toContain(QUANTITY_RANGE_ABSENCE_TEXT);
  });

  it("candidate 分支：主視圖含 NOT_HELD_BADGE 與新版 CANDIDATE_NOT_SUPPORTIVE_TEXT（非 add），CANDIDATE_EVIDENCE_NOTICE 與舊字面只在 <details>", () => {
    const response = makeResponse({
      held: false,
      advice: makeCard({ action: "hold", matched_rules: [], counterarguments: [], invalidation_conditions: [] }),
    }) as AdviceResponse;
    const html = renderToStaticMarkup(createElement(SummaryBody, { response }));
    const main = html.slice(0, html.indexOf("<details"));
    const details = html.slice(html.indexOf("<details"));
    expect(main).toContain(NOT_HELD_BADGE);
    expect(main).toContain(CANDIDATE_NOT_SUPPORTIVE_TEXT);
    expect(main).not.toContain(CANDIDATE_NOT_SUPPORTIVE_TEXT_LEGACY);
    expect(details).toContain(CANDIDATE_NOT_SUPPORTIVE_TEXT_LEGACY);
  });

  it("no_action 分支：主視圖大字為 HELD_ACTION_LABELS.insufficient_data（「資料不足」）＋常駐 INSUFFICIENT_DATA_NO_EVALUATION，不含 RULE_SOURCE_CHIP；舊字面只在 <details>", () => {
    const response = makeResponse({ advice: makeCard({ action: "insufficient_data", quantity_range: null }) }) as AdviceResponse;
    const html = renderToStaticMarkup(createElement(SummaryBody, { response }));
    const main = html.slice(0, html.indexOf("<details"));
    const details = html.slice(html.indexOf("<details"));
    expect(main).toContain(HELD_ACTION_LABELS.insufficient_data);
    expect(main).toContain(INSUFFICIENT_DATA_NO_EVALUATION);
    expect(main).not.toContain(RULE_SOURCE_CHIP);
    expect(details).toContain(HELD_ACTION_LABELS_LEGACY.insufficient_data);
  });
});

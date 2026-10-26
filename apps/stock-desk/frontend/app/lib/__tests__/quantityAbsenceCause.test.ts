import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";
import type { AdviceCard, AdviceResponse, Bar } from "../types";
import {
  FRONTEND_FORBIDDEN_TERMS,
  HELD_ACTION_LABELS,
  QUANTITY_RANGE_ABSENCE_TEXT,
  QUANTITY_RANGE_ABSENT_SHORT,
} from "../adviceWording";
import { DECISION_CARD_QUANTITY_LABEL } from "../decisionCardWording";
import { buildOperationSummary } from "../operationSummary";
import {
  QUANTITY_ABSENCE_TEXT_BY_CAUSE,
  QUANTITY_ABSENCE_TEXT_HOLD,
  QUANTITY_ABSENCE_TEXT_HOLD_BLOCKED_ADD,
  QUANTITY_ABSENT_SHORT_BY_CAUSE,
  QUANTITY_ABSENT_SHORT_HOLD,
  QUANTITY_ABSENT_SHORT_HOLD_BLOCKED_ADD,
  resolveQuantityAbsenceCause,
} from "../quantityAbsenceWording";
import { DecisionCardBody } from "../../position/[symbol]/DecisionCard";
import { SummaryBody } from "../../position/[symbol]/OperationSummaryPanel";
import { assertNoForbiddenTerms, findBareRealtimeClaims } from "./wordingScanHelpers";

/**
 * 缺陷 2「股數成因」— 風控 2026-10-26 定稿
 * (`work/reviews/2026-10-26-遷移未執行與股數成因字面逐字審-風控.md` 第一節第 2 組、
 * 第四節 J-1～J-5). 2330 held 1,000 shares and showed 「未提供股數」: the rule
 * result was add, blocked by cap 1, so the card became a hold, and a hold
 * carries no trade quantity by design — the cell read as "holding not seen".
 */

const Q_A = "續抱參考不附交易股數";
const Q_B = "加碼參考被風險上限擋下";
const D_A = "續抱參考本身不附交易股數。「股數參考」指的是交易股數，不是持有股數。";
const D_B =
  "規則原本的結論是加碼參考，被風險上限擋下後改為續抱參考；續抱參考不附交易股數。「股數參考」指的是交易股數，不是持有股數。";
const C0_SHORT = "未提供股數";
const C0_TEXT = "此建議未附帶數量區間（無法從風險上限推導）。";

function makeCard(overrides: Partial<AdviceCard> = {}): AdviceCard {
  return {
    symbol: "2330",
    action: "hold",
    quantity_range: null,
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
    as_of: "2026-10-26T09:00:00+08:00",
    observation_window: { start: "2025-05-01", end: "2026-10-26", bars: 300 },
    disclaimer: "本工具為研究與教育用途，非投資建議",
    limits_check: [],
    action_weights: [],
    direction_weights: [],
    has_conflict: false,
    aggregated_action: "hold",
    blocked_action: null,
    blocked_notices: [],
    downgrade_notices: [],
    evaluation: { total_rules: 1, evaluated_rules: 1, matched_rules: 1, data_completeness: 1, skipped_rules: [] },
    ...overrides,
  };
}

function makeResponse(card: AdviceCard, held = true): AdviceResponse {
  return {
    symbol: "2330",
    market: "TW",
    status: "ok",
    reason: null,
    as_of: "2026-10-26T09:00:00+08:00",
    held,
    position_ids: held ? [1] : [],
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
      last_bar_date: "2026-10-26",
      trading_days_behind: null,
      reason: null,
    },
  };
}

/** Engine shape of the 2330 case (`engine.py:363-368`): add blocked by cap 1, now hold. */
const BLOCKED_ADD = makeCard({
  action: "hold",
  aggregated_action: "add",
  blocked_action: "add",
  blocked_notices: ["加碼參考被第 1 條「單一標的佔比上限」擋下"],
});

/** Engine shape of a defensive downgrade (`engine.py:346-357`): add → hold, `blocked_action` stays null. */
const DOWNGRADED_HOLD = makeCard({
  action: "hold",
  aggregated_action: "add",
  blocked_action: null,
  downgrade_notices: ["防禦型規則命中，加碼參考改為續抱參考"],
});

/** J-1 fixture: `blocked_action === "add"` but `action !== "hold"`. */
const BLOCKED_NOT_HOLD = makeCard({ action: "add", aggregated_action: "add", blocked_action: "add" });

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

function quantityCell(text: string): string {
  return `${DECISION_CARD_QUANTITY_LABEL}</p><p class="mt-1 break-words font-mono text-xl font-bold text-neutral-100">${text}</p>`;
}

function renderDecisionCard(response: AdviceResponse): string {
  return renderToStaticMarkup(
    createElement(DecisionCardBody, { response, bars: makeBars(80), anchorSource: "cost", avgCost: 120 }),
  );
}

describe("股數成因字面 — 逐字釘死（風控定稿 Q-a／Q-b／D-a／D-b／C-0）", () => {
  it("Q-a / Q-b / D-a / D-b are exactly the approved strings", () => {
    expect(QUANTITY_ABSENT_SHORT_HOLD).toBe(Q_A);
    expect(QUANTITY_ABSENT_SHORT_HOLD_BLOCKED_ADD).toBe(Q_B);
    expect(QUANTITY_ABSENCE_TEXT_HOLD).toBe(D_A);
    expect(QUANTITY_ABSENCE_TEXT_HOLD_BLOCKED_ADD).toBe(D_B);
  });

  it("C-0 is the existing wording, not a single character changed", () => {
    expect(QUANTITY_RANGE_ABSENT_SHORT).toBe(C0_SHORT);
    expect(QUANTITY_RANGE_ABSENCE_TEXT).toBe(C0_TEXT);
    expect(QUANTITY_ABSENT_SHORT_BY_CAUSE).toEqual({ hold: Q_A, hold_blocked_add: Q_B, unspecified: C0_SHORT });
    expect(QUANTITY_ABSENCE_TEXT_BY_CAUSE).toEqual({ hold: D_A, hold_blocked_add: D_B, unspecified: C0_TEXT });
  });

  it("the cell label 「股數參考」 is untouched", () => {
    expect(DECISION_CARD_QUANTITY_LABEL).toBe("股數參考");
  });

  it("J-3: 續抱參考／加碼參考／股數參考 are interpolated from HELD_ACTION_LABELS / DECISION_CARD_QUANTITY_LABEL, never typed", () => {
    expect(HELD_ACTION_LABELS.hold).toBe("續抱參考");
    expect(HELD_ACTION_LABELS.add).toBe("加碼參考");
    const src = readFileSync(fileURLToPath(new URL("../quantityAbsenceWording.ts", import.meta.url)), "utf8");
    const code = src.replace(/\/\*[\s\S]*?\*\//g, "").replace(/\/\/.*$/gm, "");
    for (const label of ["續抱參考", "加碼參考", "股數參考"]) {
      expect(code, `${label} must come from its constant`).not.toContain(label);
    }
    expect(code).toContain("${HELD_ACTION_LABELS.hold}");
    expect(code).toContain("${HELD_ACTION_LABELS.add}");
    expect(code).toContain("${DECISION_CARD_QUANTITY_LABEL}");
  });

  it("Q-b / D-b never share a sentence with Q-a / D-a (隱藏成因 guard)", () => {
    expect(Q_B).not.toBe(Q_A);
    expect(D_B).not.toBe(D_A);
    expect(Q_B).toContain("風險上限");
    expect(D_B).toContain("風險上限");
    expect(Q_A).not.toContain("風險上限");
    expect(D_A).not.toContain("風險上限");
  });

  const NEW_SURFACE = [Q_A, Q_B, D_A, D_B];

  it("banned-term scan (FRONTEND_FORBIDDEN_TERMS + bare 即時 claims)", () => {
    const joined = NEW_SURFACE.join("\n");
    for (const term of FRONTEND_FORBIDDEN_TERMS) expect(joined, term).not.toContain(term);
    assertNoForbiddenTerms(joined, FRONTEND_FORBIDDEN_TERMS, "quantityAbsenceWording.ts");
    expect(findBareRealtimeClaims(joined)).toEqual([]);
  });

  it("風控 (d): no imperative, no 「0 股」, no 「建議」", () => {
    for (const text of NEW_SURFACE) {
      for (const banned of ["建議", "0 股", "0股", "不需", "無需", "請", "應", "可以自行"]) {
        expect(text, `${text} contains ${banned}`).not.toContain(banned);
      }
    }
  });
});

describe("J-1 resolveQuantityAbsenceCause — order (b), (a), C-0; four inputs only", () => {
  it("(b) held, no range, action hold, blocked add", () => {
    expect(resolveQuantityAbsenceCause("held", null, "hold", "add")).toBe("hold_blocked_add");
  });

  it("(a) held, no range, action hold, nothing blocked", () => {
    expect(resolveQuantityAbsenceCause("held", null, "hold", null)).toBe("hold");
  });

  it("C-0: blocked add but action is not hold", () => {
    for (const action of ["add", "reduce", "take_profit", "stop_loss"]) {
      expect(resolveQuantityAbsenceCause("held", null, action, "add"), action).toBe("unspecified");
    }
  });

  it("C-0: any other held action without a range", () => {
    for (const action of ["add", "reduce", "take_profit", "stop_loss"]) {
      expect(resolveQuantityAbsenceCause("held", null, action, null), action).toBe("unspecified");
    }
  });

  it("C-0: candidate never gets (a) or (b)", () => {
    expect(resolveQuantityAbsenceCause("candidate", null, "hold", null)).toBe("unspecified");
    expect(resolveQuantityAbsenceCause("candidate", null, "hold", "add")).toBe("unspecified");
  });

  it("no cause at all when a quantity range exists", () => {
    const range = { min_shares: 1, max_shares: 2, restores_compliance: true, basis: "x" };
    expect(resolveQuantityAbsenceCause("held", range, "hold", "add")).toBeNull();
    expect(resolveQuantityAbsenceCause("held", range, "hold", null)).toBeNull();
  });

  it("source: the signature takes exactly kind, quantity_range, action, blocked_action, and buildRequiredElements passes the card's own fields", () => {
    const wording = readFileSync(fileURLToPath(new URL("../quantityAbsenceWording.ts", import.meta.url)), "utf8");
    const start = wording.indexOf("export function resolveQuantityAbsenceCause(");
    const body = wording.slice(start, wording.indexOf("\n}\n", start));
    expect(body.replace(/\s+/g, " ")).toContain(
      'resolveQuantityAbsenceCause( kind: "held" | "candidate", quantityRange: object | null, action: string, blockedAction: string | null, ): QuantityAbsenceCause | null {',
    );
    const summary = readFileSync(fileURLToPath(new URL("../operationSummary.ts", import.meta.url)), "utf8");
    expect(summary.replace(/\s+/g, " ")).toContain(
      'resolveQuantityAbsenceCause( candidate ? "candidate" : "held", card.quantity_range, card.action, card.blocked_action, )',
    );
    for (const forbidden of ["blocked_notices", "downgrade_notices", "matched_rules", "aggregated_action"]) {
      expect(body, forbidden).not.toContain(forbidden);
    }
  });
});

describe("buildOperationSummary — cause carried into RequiredElements (J-2)", () => {
  function held(card: AdviceCard) {
    const model = buildOperationSummary(makeResponse(card));
    if (model.kind !== "held") throw new Error("expected held");
    return model.required;
  }

  it("2330 shape (blocked add → hold): D-b, blockedAction passed through", () => {
    const required = held(BLOCKED_ADD);
    expect(required.blockedAction).toBe("add");
    expect(required.quantityAbsenceCause).toBe("hold_blocked_add");
    expect(required.quantityAbsenceReason).toBe(D_B);
  });

  it("plain hold: D-a", () => {
    const required = held(makeCard());
    expect(required.blockedAction).toBeNull();
    expect(required.quantityAbsenceCause).toBe("hold");
    expect(required.quantityAbsenceReason).toBe(D_A);
  });

  it("J-1 fixture: downgrade_notices non-empty (defensive downgrade to hold) takes (a)", () => {
    const required = held(DOWNGRADED_HOLD);
    expect(required.quantityAbsenceCause).toBe("hold");
    expect(required.quantityAbsenceReason).toBe(D_A);
  });

  it("J-1 fixture: blocked_action add but action not hold takes C-0", () => {
    const required = held(BLOCKED_NOT_HOLD);
    expect(required.quantityAbsenceCause).toBe("unspecified");
    expect(required.quantityAbsenceReason).toBe(C0_TEXT);
  });

  it("notices text, matched_rules and aggregated_action never change the cause", () => {
    const variants: Partial<AdviceCard>[] = [
      { blocked_notices: [] },
      { blocked_notices: ["加碼參考被風險上限擋下"] },
      { downgrade_notices: ["加碼參考被風險上限擋下"] },
      { matched_rules: [] },
      { aggregated_action: "add" },
      { aggregated_action: null },
    ];
    for (const base of [makeCard(), BLOCKED_ADD, BLOCKED_NOT_HOLD]) {
      const expected = held(base).quantityAbsenceCause;
      for (const overrides of variants) {
        expect(held({ ...base, ...overrides }).quantityAbsenceCause, JSON.stringify(overrides)).toBe(expected);
      }
    }
  });

  it("candidate keeps C-0 even on a hold / blocked add", () => {
    for (const card of [makeCard(), BLOCKED_ADD]) {
      const model = buildOperationSummary(makeResponse(card, false));
      if (model.kind !== "candidate") throw new Error("expected candidate");
      expect(model.required.quantityAbsenceCause).toBe("unspecified");
      expect(model.required.quantityAbsenceReason).toBe(C0_TEXT);
    }
  });

  it("a quantity range means no cause and no absence sentence", () => {
    const required = held(
      makeCard({ action: "add", quantity_range: { min_shares: 1, max_shares: 2, restores_compliance: true, basis: "b" } }),
    );
    expect(required.quantityAbsenceCause).toBeNull();
    expect(required.quantityAbsenceReason).toBeNull();
  });
});

describe("DecisionCardBody — the 「股數參考」 cell text by cause (J-3: text only)", () => {
  it("2330 shape: Q-b", () => {
    const html = renderDecisionCard(makeResponse(BLOCKED_ADD));
    expect(html).toContain(quantityCell(Q_B));
    expect(html).not.toContain(C0_SHORT);
    expect(html).not.toContain(Q_A);
  });

  it("plain hold: Q-a", () => {
    const html = renderDecisionCard(makeResponse(makeCard()));
    expect(html).toContain(quantityCell(Q_A));
    expect(html).not.toContain(C0_SHORT);
  });

  it("defensive downgrade to hold: Q-a", () => {
    expect(renderDecisionCard(makeResponse(DOWNGRADED_HOLD))).toContain(quantityCell(Q_A));
  });

  it("blocked add but action not hold: C-0 「未提供股數」", () => {
    const html = renderDecisionCard(makeResponse(BLOCKED_NOT_HOLD));
    expect(html).toContain(quantityCell(C0_SHORT));
    expect(html).not.toContain(Q_A);
    expect(html).not.toContain(Q_B);
  });

  it("candidate: C-0 「未提供股數」 even on a hold", () => {
    for (const card of [makeCard(), BLOCKED_ADD]) {
      const html = renderDecisionCard(makeResponse(card, false));
      expect(html).toContain(quantityCell(C0_SHORT));
      expect(html).not.toContain(Q_A);
      expect(html).not.toContain(Q_B);
    }
  });

  it("no_action / no_price: still 「—」, never a cause sentence", () => {
    const noAction = renderDecisionCard(makeResponse(makeCard({ action: "insufficient_data" })));
    const noPrice = renderToStaticMarkup(
      createElement(DecisionCardBody, {
        response: { ...makeResponse(makeCard()), status: "insufficient_data", reason: "資料不足，無法計算。", advice: null },
        bars: null,
        anchorSource: "close-unknown",
        avgCost: null,
      }),
    );
    for (const html of [noAction, noPrice]) {
      expect(html).toContain(quantityCell("—"));
      for (const text of [Q_A, Q_B, C0_SHORT]) expect(html).not.toContain(text);
    }
  });
});

describe("SummaryBody — the details sentence by cause", () => {
  it("2330 shape: D-b, never D-a or C-0", () => {
    const html = renderToStaticMarkup(createElement(SummaryBody, { response: makeResponse(BLOCKED_ADD) }));
    expect(html).toContain(`<p>${D_B}</p>`);
    expect(html).not.toContain(D_A);
    expect(html).not.toContain(C0_TEXT);
  });

  it("plain hold: D-a, never C-0", () => {
    const html = renderToStaticMarkup(createElement(SummaryBody, { response: makeResponse(makeCard()) }));
    expect(html).toContain(`<p>${D_A}</p>`);
    expect(html).not.toContain(C0_TEXT);
  });

  it("candidate: C-0 unchanged", () => {
    const html = renderToStaticMarkup(createElement(SummaryBody, { response: makeResponse(makeCard(), false) }));
    expect(html).toContain(`<p>${C0_TEXT}</p>`);
    expect(html).not.toContain(D_A);
    expect(html).not.toContain(D_B);
  });
});

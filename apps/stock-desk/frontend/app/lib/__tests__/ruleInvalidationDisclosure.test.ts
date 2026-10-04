/**
 * Risk review 2026-10-04 (`work/reviews/2026-10-04-回撤規則-1.1.0-字面-風控審查.md`,
 * item 4 / required R1, position B): wherever the invalidation text of
 * `drawdown_protection` or `deep_drawdown_stop` is on screen, that rule's
 * disclosure sentence stands directly beneath it, same size and colour, once.
 * Render points covered: DecisionCard's invalidation line, both
 * OperationSummaryPanel branches' 失效條件 list (held, candidate), and
 * AdviceCardView (which renders no invalidation, so no disclosure).
 */

import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";
import type { AdviceCard, AdviceResponse, Bar, MatchedRule } from "../types";
import { RULE_INVALIDATION_DISCLOSURES } from "../adviceWording";
import { invalidationDisclosureForCondition, invalidationDisclosureForRule } from "../ruleSelection";
import { DECISION_CARD_INVALIDATION_PREFIX, DECISION_CARD_INVALIDATION_PREFIX_ONE_OF } from "../decisionCardWording";
import { DecisionCardBody } from "../../position/[symbol]/DecisionCard";
import { SummaryBody } from "../../position/[symbol]/OperationSummaryPanel";
import { AdviceCardView } from "../../position/[symbol]/AdviceCardView";

const PROTECTION_INV = "價格回到前波高點附近，或回撤幅度收斂至 -10% 以內。";
const DEEP_INV = "回撤幅度收斂至 -20% 以內，且收盤價站回 60 日均線之上。";
const MA_INV = "收盤價跌破 60 日均線，或 5 日均線下彎並跌破 20 日均線。";

const D_PROTECTION = RULE_INVALIDATION_DISCLOSURES["drawdown_protection"]!;
const D_DEEP = RULE_INVALIDATION_DISCLOSURES["deep_drawdown_stop"]!;

const CLASS_CARD = "mt-2 text-xs text-neutral-400";
const CLASS_DISCLOSURE = "mt-1 text-xs text-neutral-400";

function rule(id: string, action: string, weight: number, invalidation: string | null): MatchedRule {
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

const PROTECTION = rule("drawdown_protection", "reduce", 0.6, PROTECTION_INV);
const DEEP = rule("deep_drawdown_stop", "stop_loss", 0.8, DEEP_INV);
const MA = rule("uptrend_ma_stack", "add", 0.5, MA_INV);

function makeCard(overrides: Partial<AdviceCard> = {}): AdviceCard {
  return {
    symbol: "2330",
    action: "reduce",
    quantity_range: null,
    matched_rules: [PROTECTION],
    counterarguments: [],
    invalidation_conditions: [PROTECTION_INV],
    confidence: "medium",
    confidence_meaning: "信心等級反映規則一致性與資料完整度，非勝率或機率",
    rules_version: "1.1.0",
    as_of: "2026-09-18T09:00:00+08:00",
    observation_window: { start: "2025-05-01", end: "2026-09-18", bars: 300 },
    disclaimer: "本工具為研究與教育用途，非投資建議",
    limits_check: [],
    action_weights: [],
    direction_weights: [],
    has_conflict: false,
    aggregated_action: "reduce",
    blocked_action: null,
    blocked_notices: [],
    downgrade_notices: [],
    evaluation: { total_rules: 1, evaluated_rules: 1, matched_rules: 1, data_completeness: 1, skipped_rules: [] },
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
      last_bar_date: "2026-09-18",
      trading_days_behind: null,
      reason: null,
    },
  };
}

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

function renderDecisionCard(card: AdviceCard, held = true): string {
  return renderToStaticMarkup(
    createElement(DecisionCardBody, {
      response: makeResponse(card, held),
      bars: makeBars(80),
      anchorSource: held ? "cost" : "close-not-held",
      avgCost: held ? 120 : null,
    }),
  );
}

function renderSummary(card: AdviceCard, held: boolean): string {
  return renderToStaticMarkup(createElement(SummaryBody, { response: makeResponse(card, held) }));
}

function count(html: string, needle: string): number {
  return html.split(needle).length - 1;
}

function liFor(inv: string, disclosure: string | null): string {
  return disclosure === null
    ? `<li>${inv}</li>`
    : `<li>${inv}<p class="${CLASS_DISCLOSURE}">${disclosure}</p></li>`;
}

describe("RULE_INVALIDATION_DISCLOSURES / helpers — keyed by rule id", () => {
  it("two entries only, keyed drawdown_protection and deep_drawdown_stop", () => {
    expect(Object.keys(RULE_INVALIDATION_DISCLOSURES).sort()).toEqual(["deep_drawdown_stop", "drawdown_protection"]);
  });

  it("invalidationDisclosureForRule: by id, not by wording; null and prototype keys give null", () => {
    expect(invalidationDisclosureForRule(PROTECTION)).toBe(D_PROTECTION);
    expect(invalidationDisclosureForRule(DEEP)).toBe(D_DEEP);
    expect(invalidationDisclosureForRule(MA)).toBeNull();
    expect(invalidationDisclosureForRule(null)).toBeNull();
    expect(invalidationDisclosureForRule(rule("constructor", "reduce", 1, "x"))).toBeNull();
    expect(invalidationDisclosureForRule(rule("rsi_overbought", "reduce", 1, PROTECTION_INV))).toBeNull();
  });

  it("invalidationDisclosureForCondition: ties an entry to its rule via the rule's own invalidation field", () => {
    const rules = [MA, PROTECTION, DEEP];
    expect(invalidationDisclosureForCondition(rules, PROTECTION_INV)).toBe(D_PROTECTION);
    expect(invalidationDisclosureForCondition(rules, DEEP_INV)).toBe(D_DEEP);
    expect(invalidationDisclosureForCondition(rules, MA_INV)).toBeNull();
    // Same wording but no matched rule owns it: nothing.
    expect(invalidationDisclosureForCondition([MA], PROTECTION_INV)).toBeNull();
    // Another rule id carrying identical wording does not earn the disclosure.
    expect(invalidationDisclosureForCondition([rule("other", "reduce", 1, PROTECTION_INV)], PROTECTION_INV)).toBeNull();
  });
});

describe("DecisionCardBody — 揭露句緊接失效條件行（位置 B）", () => {
  it("drawdown_protection 為選中規則：揭露句恰一次，緊接在失效條件 <p> 之後，class 同字級同色", () => {
    const html = renderDecisionCard(makeCard());
    const inv = `<p class="${CLASS_CARD}">${DECISION_CARD_INVALIDATION_PREFIX}${PROTECTION_INV}</p>`;
    const disc = `<p class="${CLASS_DISCLOSURE}">${D_PROTECTION}</p>`;
    expect(count(html, D_PROTECTION)).toBe(1);
    expect(html).toContain(inv + disc);
    expect(count(html, D_DEEP)).toBe(0);
  });

  it("deep_drawdown_stop 為選中規則：只出深度版一次，緊接其後", () => {
    const html = renderDecisionCard(
      makeCard({
        action: "stop_loss",
        aggregated_action: "stop_loss",
        matched_rules: [PROTECTION, DEEP],
        invalidation_conditions: [PROTECTION_INV, DEEP_INV],
      }),
    );
    const inv = `<p class="${CLASS_CARD}">${DECISION_CARD_INVALIDATION_PREFIX_ONE_OF}${DEEP_INV}</p>`;
    const disc = `<p class="${CLASS_DISCLOSURE}">${D_DEEP}</p>`;
    expect(html).toContain(inv + disc);
    expect(count(html, D_DEEP)).toBe(1);
    // The card shows only the picked rule's invalidation, so the other rule's sentence has no anchor here.
    expect(count(html, D_PROTECTION)).toBe(0);
    expect(count(html, PROTECTION_INV)).toBe(0);
  });

  it("同字級同色：揭露句與失效條件行的 text-* 類別完全相同，且無 title／opacity／sr-only／hidden", () => {
    const html = renderDecisionCard(makeCard());
    const invTag = html.match(/<p class="([^"]*)">失效條件[^<]*<\/p>/);
    const discTag = html.match(new RegExp(`<p([^>]*)>${D_PROTECTION}</p>`));
    expect(invTag).not.toBeNull();
    expect(discTag).not.toBeNull();
    const textTokens = (cls: string) => cls.split(/\s+/).filter((t) => t.startsWith("text-")).sort();
    const discClass = discTag![1]!.match(/class="([^"]*)"/)![1]!;
    expect(textTokens(discClass)).toEqual(textTokens(invTag![1]!));
    expect(textTokens(discClass)).toEqual(["text-neutral-400", "text-xs"]);
    expect(discTag![1]).not.toMatch(/title=|opacity|sr-only|hidden|italic|truncate|line-clamp/);
  });

  it("揭露句不在 <details> 內", () => {
    const html = renderDecisionCard(makeCard());
    expect(html).not.toContain("<details");
  });

  it("無該規則時零次：其他規則的失效條件、無命中規則、失效條件為空", () => {
    const other = renderDecisionCard(
      makeCard({ action: "add", aggregated_action: "add", matched_rules: [MA], invalidation_conditions: [MA_INV] }),
    );
    expect(count(other, D_PROTECTION) + count(other, D_DEEP)).toBe(0);
    const none = renderDecisionCard(makeCard({ matched_rules: [], invalidation_conditions: [] }));
    expect(count(none, D_PROTECTION) + count(none, D_DEEP)).toBe(0);
    const emptyConditions = renderDecisionCard(makeCard({ invalidation_conditions: [] }));
    expect(count(emptyConditions, D_PROTECTION)).toBe(0);
  });

  it("失效條件行沒渲染（降級／被上限擋下：action !== aggregated_action）時，揭露句也不渲染", () => {
    const html = renderDecisionCard(makeCard({ aggregated_action: "add" }));
    expect(html).not.toContain("失效條件");
    expect(count(html, D_PROTECTION)).toBe(0);
  });

  it("規則以字面相同但 id 不同的失效條件出現時，不出揭露句（以 id 對應，不以字面）", () => {
    const html = renderDecisionCard(
      makeCard({
        matched_rules: [rule("rsi_overbought", "reduce", 0.6, PROTECTION_INV)],
      }),
    );
    expect(html).toContain(PROTECTION_INV);
    expect(count(html, D_PROTECTION)).toBe(0);
  });
});

describe("SummaryBody（OperationSummaryPanel）— 失效條件清單的揭露句", () => {
  const cases: Array<{ name: string; held: boolean; card: () => AdviceCard }> = [
    { name: "held 分支", held: true, card: () => makeCard() },
    { name: "candidate 分支（不支持進場）", held: false, card: () => makeCard() },
    {
      name: "candidate 分支（支持進場）",
      held: false,
      card: () =>
        makeCard({
          action: "add",
          aggregated_action: "add",
          matched_rules: [MA, PROTECTION],
          invalidation_conditions: [MA_INV, PROTECTION_INV],
        }),
    },
  ];

  for (const c of cases) {
    it(`${c.name}：drawdown_protection 的失效條件 <li> 內緊接揭露句恰一次，其他條目不帶揭露句`, () => {
      const html = renderSummary(c.card(), c.held);
      expect(count(html, D_PROTECTION)).toBe(1);
      expect(html).toContain(liFor(PROTECTION_INV, D_PROTECTION));
      if (html.includes(MA_INV)) expect(html).toContain(liFor(MA_INV, null));
      expect(count(html, D_DEEP)).toBe(0);
    });
  }

  it("兩條同時命中：各一次，各自緊接在自己的失效條件之後", () => {
    for (const held of [true, false]) {
      const html = renderSummary(
        makeCard({
          action: "stop_loss",
          aggregated_action: "stop_loss",
          matched_rules: [MA, PROTECTION, DEEP],
          invalidation_conditions: [MA_INV, PROTECTION_INV, DEEP_INV],
        }),
        held,
      );
      expect(count(html, D_PROTECTION)).toBe(1);
      expect(count(html, D_DEEP)).toBe(1);
      expect(html).toContain(liFor(MA_INV, null));
      expect(html).toContain(liFor(PROTECTION_INV, D_PROTECTION));
      expect(html).toContain(liFor(DEEP_INV, D_DEEP));
    }
  });

  it("class：揭露句與失效條件所在容器同為 text-xs text-neutral-400，無 title／opacity／sr-only／hidden，且與失效條件同在 <details> 容器內", () => {
    const html = renderSummary(makeCard(), true);
    const containerClass = 'class="mt-3 space-y-3 border-t border-neutral-800 pt-3 text-xs text-neutral-400"';
    const containerAt = html.indexOf(containerClass);
    expect(containerAt).toBeGreaterThan(-1);
    const discAt = html.indexOf(`<p class="${CLASS_DISCLOSURE}">${D_PROTECTION}</p>`);
    expect(discAt).toBeGreaterThan(containerAt);
    expect(html.slice(containerAt, discAt)).toContain("<h4");
    const tag = html.match(new RegExp(`<p([^>]*)>${D_PROTECTION}</p>`))![1]!;
    expect(tag).toBe(` class="${CLASS_DISCLOSURE}"`);
    // The <li> carries no class of its own that could dim the entry or the sentence.
    expect(html).not.toMatch(/<li class="[^"]*(?:opacity|text-neutral-[5-9]00)[^"]*">[^<]*(?:價格回到前波高點|回撤幅度收斂)/);
  });

  it("無該規則時零次：其他規則、字面相同但 id 不同、無任何規則擁有該條目", () => {
    const other = renderSummary(
      makeCard({ action: "add", aggregated_action: "add", matched_rules: [MA], invalidation_conditions: [MA_INV] }),
      true,
    );
    expect(count(other, D_PROTECTION) + count(other, D_DEEP)).toBe(0);
    const sameWordingOtherId = renderSummary(
      makeCard({ matched_rules: [rule("rsi_overbought", "reduce", 0.6, PROTECTION_INV)] }),
      true,
    );
    expect(sameWordingOtherId).toContain(PROTECTION_INV);
    expect(count(sameWordingOtherId, D_PROTECTION)).toBe(0);
    const unowned = renderSummary(makeCard({ matched_rules: [MA] }), true);
    expect(unowned).toContain(PROTECTION_INV);
    expect(count(unowned, D_PROTECTION)).toBe(0);
  });
});

describe("DecisionCard 與 SummaryBody 同頁：每個渲染點各自帶揭露句", () => {
  it("同一張卡兩處各一次（決策卡一次、操作摘要詳細一次）", () => {
    const card = makeCard();
    const both = renderDecisionCard(card) + renderSummary(card, true);
    expect(count(both, D_PROTECTION)).toBe(2);
    expect(count(both, PROTECTION_INV)).toBe(2);
  });
});

describe("AdviceCardView — 不渲染任何規則的失效條件，因此不出揭露句", () => {
  it("命中兩條規則（含 invalidation 文字）時，輸出不含失效條件文字亦不含揭露句", () => {
    const html = renderToStaticMarkup(
      createElement(AdviceCardView, {
        advice: makeCard({
          action: "stop_loss",
          aggregated_action: "stop_loss",
          matched_rules: [PROTECTION, DEEP],
          invalidation_conditions: [PROTECTION_INV, DEEP_INV],
        }),
        lastBarDate: null,
      }),
    );
    expect(html).not.toContain(PROTECTION_INV);
    expect(html).not.toContain(DEEP_INV);
    expect(html).not.toContain("失效條件");
    expect(count(html, D_PROTECTION) + count(html, D_DEEP)).toBe(0);
  });

  it("原始碼不讀取 invalidation／invalidation_conditions（若日後加上，須同步加揭露句並更新本測試）", async () => {
    const { readFileSync } = await import("node:fs");
    const { fileURLToPath } = await import("node:url");
    const src = readFileSync(
      fileURLToPath(new URL("../../position/[symbol]/AdviceCardView.tsx", import.meta.url)),
      "utf8",
    );
    expect(src).not.toMatch(/\.invalidation\b|invalidation_conditions\b/);
  });
});

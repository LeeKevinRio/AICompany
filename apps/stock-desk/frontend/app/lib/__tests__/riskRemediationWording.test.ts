/**
 * Risk remediation batch (CEO ruling #59; risk-compliance final wording
 * `work/reviews/2026-10-26-風控五項整改字面逐字審-風控.md`).
 *
 * Pins every verbatim literal of the batch against a second, hand-typed copy
 * (a test-side duplicate on purpose: a drift in the constants file fails here)
 * and checks the C-1 guardrails: every new sentence passes the existing banned
 * term scan and the bare-"即時" scan without touching either list.
 *
 * Test kind per block: 字面更新 = an old literal pin replaced by the new literal;
 * 行為新增 = a new assertion that did not exist before.
 */

import { readFileSync, readdirSync, statSync } from "node:fs";
import { join } from "node:path";
import { fileURLToPath } from "node:url";
import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";
import { FRONTEND_FORBIDDEN_TERMS } from "../adviceWording";
import {
  OPERATION_REFERENCE_DISCLAIMER,
  SITE_FOOTER_DISCLAIMER,
  UNVALIDATED_EXPLANATION,
  UNVALIDATED_LABEL,
} from "../riskRemediationWording";
import { KEY_LEVELS_PANEL_DISCLAIMER, buildFooterSample } from "../../position/[symbol]/KeyLevelsPanel";
import { DecisionCardBody } from "../../position/[symbol]/DecisionCard";
import type { AdviceCard, AdviceResponse } from "../types";
import { assertNoForbiddenTerms, findBareRealtimeClaims, stripComments } from "./wordingScanHelpers";

const read = (rel: string) => readFileSync(fileURLToPath(new URL(rel, import.meta.url)), "utf8");

/** Sentences that may never appear in any new literal (review condition 2: no "not advice" denial). */
const DENIAL_PHRASES = ["非投資建議", "不是建議", "僅供參考", "研究與教育用途", "不構成投資建議"];

function assertCleanLiteral(label: string, text: string): void {
  assertNoForbiddenTerms(text, FRONTEND_FORBIDDEN_TERMS, label);
  expect(findBareRealtimeClaims(text), label).toEqual([]);
  for (const phrase of DENIAL_PHRASES) expect(text, `${label} 含否認建議性質的句子`).not.toContain(phrase);
}

describe("1-L／1-X 逐字（字面更新：取代原「信心 低/中/高」chip）", () => {
  it("字面逐字", () => {
    expect(UNVALIDATED_LABEL).toBe("未經歷史驗證");
    expect(UNVALIDATED_EXPLANATION).toBe("這個結論所依據的規則、門檻與權重，都還沒用歷史資料驗證過。");
  });

  it("通過禁用詞與裸即時掃描（C-1），且不含否認建議性質的句子", () => {
    assertCleanLiteral("UNVALIDATED_LABEL", UNVALIDATED_LABEL);
    assertCleanLiteral("UNVALIDATED_EXPLANATION", UNVALIDATED_EXPLANATION);
  });
});

describe("信心 chip 不得回流（行為新增；保護 1-L 的失效條件 T2：信心重新上畫面須同批改寫字面）", () => {
  const SURFACES = [
    "../../position/[symbol]/DecisionCard.tsx",
    "../../position/[symbol]/OperationSummaryPanel.tsx",
  ] as const;

  for (const rel of SURFACES) {
    it(`${rel}：程式碼（不含註解）不引用 CONFIDENCE_PREFIX、summaryConfidenceLabel，也不渲染 confidenceMeaning`, () => {
      const code = stripComments(read(rel));
      expect(code).not.toContain("CONFIDENCE_PREFIX");
      expect(code).not.toContain("summaryConfidenceLabel");
      expect(code).not.toContain("confidenceMeaning");
      expect(code).not.toContain("showConfidence");
    });

    it(`${rel}：渲染 <UnvalidatedNotice />`, () => {
      const code = stripComments(read(rel));
      expect(code).toContain("<UnvalidatedNotice />");
    });
  }

  it("兩個連動 xref 句不再提到「信心等級」（連動 xref 1、2；保護的字面：ENTRY_E2_XREF、ADVICE_CARD_XREF_TO_SUMMARY）", () => {
    const entry = read("../entryObservationWording.ts");
    const tagline = read("../sectionTaglines.ts");
    expect(stripComments(entry)).not.toContain("信心等級");
    expect(stripComments(tagline)).not.toContain("信心等級");
  });
});

// ---------------------------------------------------------------------------
// Item 3: transitional disclaimers (3-S, 3-F, K-1, K-2)
// ---------------------------------------------------------------------------

/** Joins the quoted pieces of a (possibly parenthesised, multi-line) Python or TS string constant. */
function joinQuoted(block: string): string {
  return [...block.matchAll(/"([^"]*)"/g)].map((m) => m[1]).join("");
}

describe("3-S／3-F 逐字（字面更新：取代「本工具為研究與教育用途，非投資建議」）", () => {
  it("3-S 逐字", () => {
    expect(OPERATION_REFERENCE_DISCLAIMER).toBe(
      "依固定規則產生的操作參考，規則與價位未經歷史驗證；可能有誤，照做也可能虧損，是否採用由你決定。日線收盤資料，非即時。",
    );
  });

  it("3-F 逐字", () => {
    expect(SITE_FOOTER_DISCLAIMER).toBe(
      "本工具提供的動作、股數與價位，是依固定規則與固定算式產生的操作參考。" +
        "規則與價位都還沒用歷史資料驗證過，可能錯誤，照做也可能造成虧損，是否採用由你自行決定。" +
        "這些參考只用日線收盤資料計算，非即時，不反映最近一次收盤之後的價格變動。",
    );
  });

  it("K-1／K-2 逐字（照 creative-lead 原字面）", () => {
    expect(KEY_LEVELS_PANEL_DISCLAIMER).toBe(
      "以下數字皆為本面板依固定算式計算之參考水位，並非分析結果，也未經歷史驗證，亦非任何買賣指示；" +
        "每個數字的計算方式，包括收盤資料的來源，皆在「計算依據」中逐項揭露。",
    );
    expect(buildFooterSample(387, "2026-09-01")).toBe("計算樣本：387 根日線，最後一根 2026-09-01。");
  });

  it("通過禁用詞與裸即時掃描（C-1），且不含否認建議性質的句子", () => {
    assertCleanLiteral("3-S", OPERATION_REFERENCE_DISCLAIMER);
    assertCleanLiteral("3-F", SITE_FOOTER_DISCLAIMER);
    assertCleanLiteral("K-1", KEY_LEVELS_PANEL_DISCLAIMER);
    assertCleanLiteral("K-2", buildFooterSample(387, "2026-09-01"));
  });
});

describe("前後端 parity（行為新增；C-7：前端常數與後端 DISCLAIMER 必須逐字相同）", () => {
  it("前端 OPERATION_REFERENCE_DISCLAIMER 等於後端 engine.py 的 DISCLAIMER（後端測試從另一側讀本檔）", () => {
    const engine = read("../../../../backend/app/advice/engine.py");
    const match = engine.match(/^DISCLAIMER: Final = (\(?[\s\S]*?)\n\n/m);
    expect(match, "engine.py 找不到 DISCLAIMER").not.toBeNull();
    expect(joinQuoted(match![1]!)).toBe(OPERATION_REFERENCE_DISCLAIMER);
  });

  it("apps/stock-desk/README.md 的免責引言等於 3-F（C-8：README 同批更新）", () => {
    const readme = read("../../../../README.md");
    expect(readme).toContain(`> ${SITE_FOOTER_DISCLAIMER}`);
  });

  it("layout.tsx 的頁尾渲染 SITE_FOOTER_DISCLAIMER，且不再含舊句", () => {
    const layout = read("../../layout.tsx");
    expect(layout).toContain("{SITE_FOOTER_DISCLAIMER}");
    expect(layout).toContain('import { SITE_FOOTER_DISCLAIMER } from "./lib/riskRemediationWording"');
  });
});

describe("舊字面在出貨面零出現（行為新增；C-2 grep 的測試版，排除 event_study 與註解）", () => {
  const APP_ROOT = fileURLToPath(new URL("../../", import.meta.url));

  function productionFiles(dir: string): string[] {
    const files: string[] = [];
    for (const entry of readdirSync(dir)) {
      const full = join(dir, entry);
      if (statSync(full).isDirectory()) {
        if (entry === "node_modules" || entry === ".next" || entry === "__tests__") continue;
        files.push(...productionFiles(full));
      } else if (/\.(ts|tsx)$/.test(entry)) {
        files.push(full);
      }
    }
    return files;
  }

  it.each(["研究與教育用途", "非投資建議", "不構成投資建議"])(
    "app/**（不含 __tests__ 與註解）不含「%s」",
    (phrase) => {
      // Event-study wording is backend-sourced (`event_study.py`, deferred to D-11); the frontend carries
      // only its own sentences, so a hit anywhere here is a regression of the old disclaimer.
      const offenders = productionFiles(APP_ROOT).filter((file) =>
        stripComments(readFileSync(file, "utf-8")).includes(phrase),
      );
      expect(offenders).toEqual([]);
    },
  );
});

describe("DecisionCard 的 3-S 呈現（C-7）", () => {
  const card = (overrides: Partial<AdviceCard> = {}): AdviceCard => ({
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
    disclaimer: OPERATION_REFERENCE_DISCLAIMER,
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
  });
  const response = (advice: AdviceCard | null, held: boolean, status: AdviceResponse["status"] = "ok"): AdviceResponse => ({
    symbol: "2330",
    market: "TW",
    status,
    reason: advice === null ? "資料不足，無法計算。" : null,
    as_of: "2026-09-18T09:00:00+08:00",
    held,
    position_ids: [1],
    portfolio_context: {} as unknown as AdviceResponse["portfolio_context"],
    context_notes: [],
    cap1_migration_notice: null,
    advice,
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
  });
  const render = (r: AdviceResponse): string =>
    renderToStaticMarkup(createElement(DecisionCardBody, { response: r, bars: null, anchorSource: "close-unknown", avgCost: null }));

  const KINDS: ReadonlyArray<[string, AdviceResponse]> = [
    ["held", response(card(), true)],
    ["candidate", response(card(), false)],
    ["no_action", response(card({ action: "insufficient_data", aggregated_action: "insufficient_data" }), true)],
    ["no_price", response(null, true, "insufficient_data")],
  ];

  it.each(KINDS)("%s：3-S 恆顯示，<p class=\"mt-3 text-sm text-neutral-300\">，不在 <details> 內，無截斷類 class", (_kind, r) => {
    const html = render(r);
    const m = html.match(/<p class="([^"]*)">依固定規則產生的操作參考[^<]*<\/p>/);
    expect(m, "3-S 應渲染").not.toBeNull();
    expect(m![0]).toContain(OPERATION_REFERENCE_DISCLAIMER);
    expect(m![1]).toBe("mt-3 text-sm text-neutral-300");
    expect(m![1]).not.toMatch(/truncate|line-clamp|max-h|overflow|nowrap|hidden|opacity/);
    for (const block of html.match(/<details[\s\S]*?<\/details>/g) ?? []) expect(block).not.toContain(OPERATION_REFERENCE_DISCLAIMER);
    expect(m![0]).not.toMatch(/title=/);
  });

  it("位置：在上限區塊之後、失效條件行之前（有失效條件的 held 卡）", () => {
    const rule = {
      id: "r1",
      name: "規則一",
      action: "hold",
      weight: 0.5,
      weight_meaning: "x",
      explanation: "y",
      invalidation: "收盤價跌破 60 日均線。",
    };
    const limits: AdviceCard["limits_check"] = [
      { index: 1, id: "single_position_weight", name: "單一標的佔比上限", status: "violated", detail: "d", observed: 0.3, threshold: 0.15 },
    ];
    const html = render(
      response(card({ matched_rules: [rule], invalidation_conditions: ["收盤價跌破 60 日均線。"], limits_check: limits }), true),
    );
    const limitIdx = html.indexOf("已違反第 1 條上限");
    const disclaimerIdx = html.indexOf(OPERATION_REFERENCE_DISCLAIMER);
    const invalidationIdx = html.indexOf("失效條件");
    expect(limitIdx).toBeGreaterThan(-1);
    expect(disclaimerIdx).toBeGreaterThan(limitIdx);
    expect(invalidationIdx).toBeGreaterThan(disclaimerIdx);
  });

  it("R3 指引句（頁尾「本頁揭露與計算依據」…）已撤銷：決策卡不再引用 buildFooterGuidance(PAGE_FOOTER_DISCLOSURES_TITLE)", () => {
    const code = stripComments(read("../../position/[symbol]/DecisionCard.tsx"));
    expect(code).not.toContain("buildFooterGuidance");
    expect(code).not.toContain("PAGE_FOOTER_DISCLOSURES_TITLE");
    expect(code).toContain("{OPERATION_REFERENCE_DISCLAIMER}");
  });
});

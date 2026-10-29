/**
 * N-156 建議端與儀表的 `settings_fallback_notice`（ADR-0032 Decision 2、DL-3；風控
 * 2026-10-29 N-156 字面定稿 第 2、4 項）前端守門。
 *
 * 句子由後端選（N-1／N-2／N-3）、前端原樣渲染。fixture 一律用 `SENTINEL-*`：
 * 輸出裡出現的就是被原樣傳遞的，前端若自撰或改寫就會現形。位置規則：
 *   - `LimitsCheckList`、`RiskGaugeView` 清單層級，各條之上；
 *   - 個股頁主畫面 `<details>` 之外再放一份（決策卡，與 CEO #59 的主畫面限額區塊
 *     同一區），held 與 candidate 兩種模式都要；
 *   - Kelly 的 `effective_cap` 數值旁，字級與數值同級。
 * 一律至少 `text-sm`，不比 neutral-300 淡，不在任何 `<details>` 內。
 *
 * 本專案 vitest 無 jsdom，結構以 `renderToStaticMarkup` 加 `htmlTree` 驗證。
 */

import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";
import { ancestorsOf, elementsOf, findAll, parseHtml, textOf } from "../../backtest/__tests__/htmlTree";
import { RiskGaugeView } from "../../components/RiskGauge";
import { SettingsFallbackNoticeLine } from "../../components/SettingsFallbackNoticeLine";
import { KellyDisclosuresPanel } from "../../settings/KellyDisclosuresPanel";
import { AdviceCardView } from "../../position/[symbol]/AdviceCardView";
import { DecisionCardBody } from "../../position/[symbol]/DecisionCard";
import { LimitsCheckList } from "../../position/[symbol]/LimitsCheckList";
import type {
  AdviceCard,
  AdviceResponse,
  BookLimitCheck,
  KellyInputDisclosuresView,
  LimitCheck,
  PortfolioLimitsResponse,
} from "../types";

const NOTICE = "SENTINEL-FALLBACK-NOTICE";

/** Elements whose text is exactly the sentinel notice (the `<p>` that carries it). */
function noticeElements(html: string) {
  return findAll(parseHtml(html), (el) => el.tag === "p" && textOf(el) === NOTICE);
}

function expectStanding(html: string) {
  const copies = noticeElements(html);
  expect(copies.length).toBeGreaterThan(0);
  for (const copy of copies) {
    expect(ancestorsOf(copy).some((a) => a.tag === "details")).toBe(false);
    const classes = copy.attrs.class ?? "";
    expect(classes).toContain("text-sm");
    expect(classes).not.toMatch(/text-xs|text-neutral-(400|500|600|700)|opacity-|truncate|line-clamp|sr-only/);
  }
}

function limit(overrides: Partial<LimitCheck> = {}): LimitCheck {
  return {
    index: 1,
    id: "single_position_weight",
    name: "單一標的佔比上限",
    status: "passed",
    detail: "CAP_DETAIL",
    observed: 0.05,
    threshold: 0.1,
    ...overrides,
  };
}

/* --- The shared notice line ---------------------------------------------------- */

describe("SettingsFallbackNoticeLine", () => {
  it("逐字渲染傳入的句子，沒有句子就什麼都不渲染", () => {
    const html = renderToStaticMarkup(createElement(SettingsFallbackNoticeLine, { text: NOTICE }));
    expect(textOf(parseHtml(html))).toBe(NOTICE);
    expect(renderToStaticMarkup(createElement(SettingsFallbackNoticeLine, { text: null }))).toBe("");
  });

  it("空字串與 null 一樣不渲染，不會留下空框（NB-7）", () => {
    expect(renderToStaticMarkup(createElement(SettingsFallbackNoticeLine, { text: "" }))).toBe("");
  });

  it("至少 text-sm、琥珀 200（比 neutral-300 亮），不收合", () => {
    const html = renderToStaticMarkup(createElement(SettingsFallbackNoticeLine, { text: NOTICE }));
    expectStanding(html);
    expect(html).toContain("text-amber-200");
  });
});

/* --- LimitsCheckList: list level, above every cap ------------------------------ */

describe("LimitsCheckList — 清單層級，各條之上", () => {
  const limits = [limit(), limit({ index: 3, id: "gross_exposure", name: "總曝險上限" })];

  it("句子出現一次，在第一條之前，不在任何一條 <li> 內", () => {
    const html = renderToStaticMarkup(
      createElement(LimitsCheckList, { limits, settingsFallbackNotice: NOTICE }),
    );
    expect(html.split(NOTICE).length - 1).toBe(1);
    expect(html.indexOf(NOTICE)).toBeLessThan(html.indexOf("第 1 條"));
    for (const li of findAll(parseHtml(html), (el) => el.tag === "li")) {
      expect(textOf(li)).not.toContain(NOTICE);
    }
    expectStanding(html);
  });

  it("沒有句子時不渲染任何揭露，清單其餘部分不變", () => {
    const without = renderToStaticMarkup(createElement(LimitsCheckList, { limits }));
    const withNull = renderToStaticMarkup(createElement(LimitsCheckList, { limits, settingsFallbackNotice: null }));
    expect(withNull).toBe(without);
    expect(without).not.toContain("SENTINEL");
  });

  it("加上句子後，多出來的只有那一句（前端沒有加任何自己的字）", () => {
    const without = renderToStaticMarkup(createElement(LimitsCheckList, { limits }));
    const html = renderToStaticMarkup(createElement(LimitsCheckList, { limits, settingsFallbackNotice: NOTICE }));
    const line = renderToStaticMarkup(createElement(SettingsFallbackNoticeLine, { text: NOTICE, className: "mb-2" }));
    expect(html.replace(line, "")).toBe(without);
  });
});

/* --- RiskGauge (home): list level ----------------------------------------------- */

function bookCheck(overrides: Partial<BookLimitCheck>): BookLimitCheck {
  return {
    index: 1,
    limit_id: "single_position_weight",
    name: "單一標的佔比上限",
    status: "passed",
    observed: 0.05,
    threshold: 0.2,
    detail: "detail sentence",
    worst_symbol: null,
    evaluated_count: 3,
    violated_count: 0,
    excluded: [],
    ...overrides,
  };
}

function gaugeData(notice: string | null): PortfolioLimitsResponse {
  return {
    limits: [
      bookCheck({}),
      bookCheck({ index: 3, limit_id: "gross_exposure", name: "總曝險上限", status: "not_evaluable", observed: null, threshold: null }),
    ],
    notes: [],
    sources: [],
    cap1_migration_notice: null,
    settings_fallback_notice: notice,
    as_of: "2026-10-29T00:00:00Z",
  };
}

describe("RiskGaugeView — 首頁儀表清單層級", () => {
  it("句子出現一次，在各條之上、共用 <details> 之外", () => {
    const html = renderToStaticMarkup(createElement(RiskGaugeView, { data: gaugeData(NOTICE) }));
    expect(html.split(NOTICE).length - 1).toBe(1);
    expect(html.indexOf(NOTICE)).toBeLessThan(html.indexOf("第 1 條"));
    expectStanding(html);
    const details = findAll(parseHtml(html), (el) => el.tag === "details");
    expect(details).toHaveLength(1);
    expect(textOf(details[0]!)).not.toContain(NOTICE);
  });

  it("沒有句子時不渲染，其餘不變", () => {
    const html = renderToStaticMarkup(createElement(RiskGaugeView, { data: gaugeData(null) }));
    expect(html).not.toContain("SENTINEL");
    const withNotice = renderToStaticMarkup(createElement(RiskGaugeView, { data: gaugeData(NOTICE) }));
    const line = renderToStaticMarkup(createElement(SettingsFallbackNoticeLine, { text: NOTICE, className: "mt-3" }));
    expect(withNotice.replace(line, "")).toBe(html);
  });
});

/* --- Position page: main view (decision card) + advice card list ---------------- */

function card(overrides: Partial<AdviceCard> = {}): AdviceCard {
  return {
    symbol: "2330",
    action: "add",
    quantity_range: null,
    matched_rules: [
      {
        id: "uptrend_ma_stack",
        name: "SENTINEL-RULE",
        action: "add",
        weight: 0.5,
        weight_meaning: "SENTINEL-WEIGHT",
        explanation: "SENTINEL-EXPLANATION",
        invalidation: null,
      },
    ],
    counterarguments: [],
    invalidation_conditions: [],
    confidence: "medium",
    confidence_meaning: "SENTINEL-CONFIDENCE",
    rules_version: "1.0.2",
    as_of: "2026-10-29T09:00:00+08:00",
    observation_window: { start: "2025-05-01", end: "2026-10-29", bars: 300 },
    disclaimer: "SENTINEL-DISCLAIMER",
    limits_check: [limit(), limit({ index: 3, id: "gross_exposure", name: "總曝險上限", status: "not_evaluable" })],
    action_weights: [],
    direction_weights: [],
    has_conflict: false,
    aggregated_action: "add",
    blocked_action: null,
    blocked_notices: [],
    downgrade_notices: [],
    evaluation: { total_rules: 1, evaluated_rules: 1, matched_rules: 1, data_completeness: 1, skipped_rules: [] },
    ...overrides,
  };
}

function adviceResponse(overrides: Partial<AdviceResponse> = {}): AdviceResponse {
  return {
    symbol: "2330",
    market: "TW",
    status: "ok",
    reason: null,
    as_of: "2026-10-29T09:00:00+08:00",
    held: true,
    position_ids: [1],
    portfolio_context: {} as unknown as AdviceResponse["portfolio_context"],
    context_notes: [],
    cap1_migration_notice: null,
    settings_fallback_notice: NOTICE,
    advice: card(),
    data: {
      status: "fresh",
      source: "twse",
      staleness_minutes: 5,
      is_within_ttl: null,
      bar_count: 300,
      first_bar_date: "2025-05-01",
      last_bar_date: "2026-10-29",
      trading_days_behind: null,
      reason: null,
    },
    ...overrides,
  };
}

function renderMain(response: AdviceResponse): string {
  return renderToStaticMarkup(
    createElement(DecisionCardBody, { response, bars: null, anchorSource: "cost", avgCost: 120 }),
  );
}

describe("DecisionCardBody — 個股頁主畫面再放一份（風控 第 2 項 required）", () => {
  it("held：主畫面出現一份，不在任何 <details> 內", () => {
    const html = renderMain(adviceResponse({ held: true }));
    expect(noticeElements(html)).toHaveLength(1);
    expectStanding(html);
  });

  it("candidate（未持有）：同樣出現一份", () => {
    const html = renderMain(
      adviceResponse({ held: false, position_ids: [], advice: card({ action: "add" }) }),
    );
    expect(noticeElements(html)).toHaveLength(1);
    expectStanding(html);
  });

  it("與主畫面的限額違反區塊同一區：有違反時，句子緊接在該區塊之後", () => {
    const html = renderMain(
      adviceResponse({
        advice: card({
          limits_check: [limit({ status: "violated", observed: 0.14, threshold: 0.1 })],
        }),
      }),
    );
    const root = parseHtml(html);
    const [copy] = findAll(root, (el) => el.tag === "p" && textOf(el) === NOTICE);
    expect(copy).toBeDefined();
    const violation = findAll(root, (el) => (el.attrs.class ?? "").includes("border-rose-800"))[0];
    expect(violation).toBeDefined();
    expect(copy!.parent).toBe(violation!.parent?.parent ?? null);
  });

  it("沒有限額區塊時也要出現（句子不依賴任何一條上限的狀態）", () => {
    const html = renderMain(adviceResponse({ advice: card({ limits_check: [] }) }));
    expect(noticeElements(html)).toHaveLength(1);
  });

  it("沒有句子時什麼都不加", () => {
    const html = renderMain(adviceResponse({ settings_fallback_notice: null }));
    expect(html).not.toContain("SENTINEL-FALLBACK-NOTICE");
  });

  it("加上句子後，多出來的只有那一句（前端沒有自己的字）", () => {
    const base = renderMain(adviceResponse({ settings_fallback_notice: null }));
    const html = renderMain(adviceResponse());
    const line = renderToStaticMarkup(createElement(SettingsFallbackNoticeLine, { text: NOTICE, className: "mt-3" }));
    expect(html.replace(line, "")).toBe(base);
  });
});

describe("個股頁：主畫面與清單層級各一份，共兩份", () => {
  it("決策卡一份、建議卡的風險上限清單一份；建議卡那份在各條之上", () => {
    const response = adviceResponse();
    const main = renderMain(response);
    const list = renderToStaticMarkup(
      createElement(AdviceCardView, {
        advice: response.advice!,
        lastBarDate: "2026-10-29",
        settingsFallbackNotice: response.settings_fallback_notice,
      }),
    );
    expect(noticeElements(main)).toHaveLength(1);
    expect(noticeElements(list)).toHaveLength(1);
    expect(list.indexOf(NOTICE)).toBeGreaterThan(list.indexOf("風險上限檢查"));
    expect(list.indexOf(NOTICE)).toBeLessThan(list.indexOf("第 1 條"));
  });

  it("page.tsx 把同一個欄位傳給兩處，且決策卡在建議卡的 <details> 之外", () => {
    const page = readFileSync(
      fileURLToPath(new URL("../../position/[symbol]/page.tsx", import.meta.url)),
      "utf8",
    );
    expect(page).toContain("settingsFallbackNotice={advice.data.settings_fallback_notice}");
    expect(page.indexOf("<DecisionCard")).toBeLessThan(page.indexOf("<details"));
    const decisionCard = readFileSync(
      fileURLToPath(new URL("../../position/[symbol]/DecisionCard.tsx", import.meta.url)),
      "utf8",
    );
    expect(decisionCard).toContain("response.settings_fallback_notice");
  });
});

/* --- E2: the reason sentence rides in downgrade_notices, no special case --------- */

describe("E2：理由句在 downgrade_notices，blocked_action 為 null，現有渲染照常顯示", () => {
  const E2_SENTENCE = "SENTINEL-E2-REASON";
  const downgraded = card({
    action: "hold",
    aggregated_action: "add",
    blocked_action: null,
    blocked_notices: [],
    downgrade_notices: [E2_SENTENCE],
  });

  it("建議卡顯示理由句，且不出現「加碼建議被風險上限擋下」", () => {
    const html = renderToStaticMarkup(
      createElement(AdviceCardView, { advice: downgraded, lastBarDate: "2026-10-29" }),
    );
    expect(html).toContain(E2_SENTENCE);
    expect(html).not.toContain("加碼建議被風險上限擋下");
    const copy = findAll(parseHtml(html), (el) => el.tag === "li" && textOf(el) === E2_SENTENCE);
    expect(copy).toHaveLength(1);
  });

  it("前端沒有為 E2 做任何特判", () => {
    for (const file of ["../../position/[symbol]/AdviceCardView.tsx", "../../position/[symbol]/DecisionCard.tsx"]) {
      const source = readFileSync(fileURLToPath(new URL(file, import.meta.url)), "utf8");
      expect(source, file).not.toMatch(/budget_from_default|E2/);
    }
  });
});

/* --- Kelly: beside effective_cap ------------------------------------------------- */

function kellyView(notice: string | null, withCap = true): KellyInputDisclosuresView {
  return {
    kelly_input: null,
    as_of: "2026-10-29T00:00:00+00:00",
    disclosures: {
      import_trigger_label: "SENTINEL-TRIGGER",
      writes_paused_label: null,
      freshness_badge_label: "SENTINEL-BADGE",
      source_statement: null,
      source_label: null,
      win_rate_disclosure: null,
      manual_input_disclosure: null,
      manual_input_tooltip: null,
      selection_bias: null,
      walk_forward: null,
      f_star_interval: withCap ? "SENTINEL-INTERVAL" : null,
      effective_cap: withCap ? { label: "SENTINEL-CAP-LABEL", value: "SENTINEL-CAP-VALUE" } : null,
      settings_fallback_notice: notice,
      boundary_exclusion: null,
      sample_detail: null,
      original_values: null,
      original_values_entry_label: null,
      original_values_return_label: null,
      overwrite_notice: null,
      delete_notice: null,
      k_observed: 0,
      k_distinct_specs: 0,
    },
  };
}

function renderKelly(data: KellyInputDisclosuresView): string {
  const client = new QueryClient();
  return renderToStaticMarkup(
    createElement(
      QueryClientProvider,
      { client },
      createElement(KellyDisclosuresPanel, { data, symbol: "2330", market: "TW" }),
    ),
  );
}

describe("KellyDisclosuresPanel — effective_cap 數值旁（風控 第 4 項）", () => {
  it("句子緊接在 effective_cap 數值那一行之後、同一個方框內，字級與數值同級（text-sm）", () => {
    const html = renderKelly(kellyView(NOTICE));
    const root = parseHtml(html);
    const [copy] = findAll(root, (el) => el.tag === "p" && textOf(el) === NOTICE);
    expect(copy).toBeDefined();
    const valueRow = findAll(root, (el) => el.tag === "p" && textOf(el).includes("SENTINEL-CAP-VALUE"))[0];
    expect(valueRow).toBeDefined();
    expect(copy!.parent).toBe(valueRow!.parent);
    expect(html.indexOf(NOTICE)).toBeGreaterThan(html.indexOf("SENTINEL-CAP-VALUE"));
    expect(valueRow!.attrs.class).toContain("text-sm");
    expectStanding(html);
    // The value itself stays visible: only the disclosure is added.
    expect(html).toContain("SENTINEL-CAP-VALUE");
  });

  it("數值區塊不顯示時，揭露句仍然獨立出現，不會被吞掉", () => {
    const html = renderKelly(kellyView(NOTICE, false));
    expect(noticeElements(html)).toHaveLength(1);
  });

  it("沒有句子時完全不渲染", () => {
    const html = renderKelly(kellyView(null));
    expect(html).not.toContain(NOTICE);
    expect(elementsOf(parseHtml(html)).filter((el) => (el.attrs.class ?? "").includes("border-amber-800"))).toEqual([]);
  });
});

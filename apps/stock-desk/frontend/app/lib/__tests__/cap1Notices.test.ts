/**
 * #61 batch one (CEO #61/#63, 2026-10-26): where the S2 notices and the cap-1
 * ledger summary render.
 *
 * The S2 copy itself is the backend's (verbatim-pinned in
 * `tests/test_settings_migrations.py`); here it is a stand-in string and only
 * *placement* is asserted: the shared sentence on the gauge's cap-1 row and
 * under `LimitsCheckList`'s cap-1 「觀察值／上限」 line, the structured block
 * under the settings field — standing, never a toast, tooltip, `<details>`,
 * `role="status"` or `aria-live` (實作約束 3/4, I-8). The front-end summary
 * copy (#4a/#4b) is pinned verbatim.
 */

import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";
import { RiskGaugeView } from "../../components/RiskGauge";
import { LimitsCheckList } from "../../position/[symbol]/LimitsCheckList";
import { Cap1MigrationNoticeBlock } from "../../settings/SettingsForm";
import {
  buildCap1LedgerSummary,
  CAP1_LEDGER_SUMMARY_TEMPLATE,
  CAP1_LEDGER_SUMMARY_WITH_EXCLUDED_TEMPLATE,
} from "../cap1SunsetWording";
import type { BookLimitCheck, LimitCheck, PortfolioLimitsResponse } from "../types";

const NOTICE = "S2_SHORT_NOTICE_STAND_IN";

function bookCheck(overrides: Partial<BookLimitCheck>): BookLimitCheck {
  return {
    index: 1,
    limit_id: "single_position_weight",
    name: "單一標的佔比上限",
    status: "violated",
    observed: 0.12,
    threshold: 0.1,
    detail: "detail",
    worst_symbol: "2330",
    evaluated_count: 3,
    violated_count: 2,
    excluded: [],
    ...overrides,
  };
}

function gauge(limits: BookLimitCheck[], notice: string | null): string {
  const data: PortfolioLimitsResponse = {
    limits,
    notes: [],
    sources: [],
    cap1_migration_notice: notice,
    settings_fallback_notice: null,
    as_of: "2026-10-27T00:00:00Z",
  };
  return renderToStaticMarkup(createElement(RiskGaugeView, { data }));
}

function mainView(html: string): string {
  return html.slice(0, html.indexOf("<details"));
}

const CAP3: BookLimitCheck = bookCheck({
  index: 3,
  limit_id: "gross_exposure",
  name: "總曝險上限",
  status: "passed",
  observed: 0.5,
  threshold: 1,
  worst_symbol: null,
  violated_count: 0,
});

describe("#4a/#4b ledger summary (實作約束 8)", () => {
  it("pins both templates verbatim", () => {
    expect(CAP1_LEDGER_SUMMARY_TEMPLATE).toBe("{n} 檔持股已達或超過第 1 條上限（{threshold_pct}）。");
    expect(CAP1_LEDGER_SUMMARY_WITH_EXCLUDED_TEMPLATE).toBe(
      "{n} 檔持股已達或超過第 1 條上限（{threshold_pct}）；另有 {m} 檔未納入比較，不在此數內。",
    );
  });

  it("4a: n from the backend's violated_count, threshold through formatPercent", () => {
    expect(buildCap1LedgerSummary(bookCheck({}))).toBe("2 檔持股已達或超過第 1 條上限（10.00%）。");
  });

  it("4b: m is excluded.length and the sentence says they are not in n", () => {
    const check = bookCheck({
      excluded: [
        { symbol: "AAPL", market: "US", reason: "r" },
        { symbol: "0050", market: "TW", reason: "r" },
        { symbol: "2317", market: "TW", reason: "r" },
      ],
    });
    expect(buildCap1LedgerSummary(check)).toBe(
      "2 檔持股已達或超過第 1 條上限（10.00%）；另有 3 檔未納入比較，不在此數內。",
    );
  });

  it("is not shown when n = 0, nor on any other cap", () => {
    expect(buildCap1LedgerSummary(bookCheck({ violated_count: 0, status: "passed" }))).toBeNull();
    expect(buildCap1LedgerSummary(bookCheck({ index: 3, limit_id: "gross_exposure" }))).toBeNull();
  });
});

describe("RiskGaugeView cap-1 row (#2, S1/S1', #4)", () => {
  it("shows「觀測值最高」→ summary → S2 sentence, in that order, in the main view", () => {
    const html = mainView(gauge([bookCheck({}), CAP3], NOTICE));
    const worst = html.indexOf("觀測值最高：2330");
    const summary = html.indexOf("2 檔持股已達或超過第 1 條上限（10.00%）。");
    const notice = html.indexOf(NOTICE);
    expect(worst).toBeGreaterThan(-1);
    expect(summary).toBeGreaterThan(worst);
    expect(notice).toBeGreaterThan(summary);
  });

  it("puts the S2 sentence on the cap-1 row only, once, with no truncation or live region", () => {
    const html = gauge([bookCheck({}), CAP3], NOTICE);
    expect(html.split(NOTICE).length - 1).toBe(1);
    const row = html.slice(html.indexOf("<li"), html.indexOf("</li>"));
    expect(row).toContain(NOTICE);
    expect(row).not.toMatch(/truncate|line-clamp|aria-live|role="status"|title=/);
  });

  it("shows nothing extra when the backend sends no notice", () => {
    const html = gauge([bookCheck({ violated_count: 0, status: "passed" }), CAP3], null);
    expect(html).not.toContain(NOTICE);
    expect(html).not.toContain("檔持股已達或超過");
  });
});

function limit(overrides: Partial<LimitCheck>): LimitCheck {
  return {
    index: 1,
    id: "single_position_weight",
    name: "單一標的佔比上限",
    status: "violated",
    detail: "CAP1_DETAIL",
    observed: 0.12,
    threshold: 0.1,
    ...overrides,
  };
}

describe("LimitsCheckList (#2', S1/S1', I-2)", () => {
  const limits = [limit({}), limit({ index: 3, id: "gross_exposure", name: "總曝險上限", status: "passed" })];

  it("puts the shared sentence under cap 1's 觀察值／上限 line and nowhere else", () => {
    const html = renderToStaticMarkup(createElement(LimitsCheckList, { limits, cap1MigrationNotice: NOTICE }));
    expect(html.split(NOTICE).length - 1).toBe(1);
    const cap1 = html.slice(0, html.indexOf("</li>"));
    expect(cap1.indexOf(NOTICE)).toBeGreaterThan(cap1.indexOf("上限：10.00%"));
  });

  it("renders no notice without one", () => {
    const html = renderToStaticMarkup(createElement(LimitsCheckList, { limits }));
    expect(html).not.toContain(NOTICE);
  });
});

describe("settings-page S2 block (#1, U0–U5)", () => {
  const notice = {
    title: "TITLE",
    items: [
      { label: "L1", body: "B1" },
      { label: "L2", body: "B2" },
    ],
  };

  it("renders the title and every item in order as「標籤｜正文」", () => {
    const html = renderToStaticMarkup(createElement(Cap1MigrationNoticeBlock, { notice }));
    expect(html).toContain("TITLE");
    expect(html.indexOf("L1</span>｜B1")).toBeGreaterThan(-1);
    expect(html.indexOf("L2</span>｜B2")).toBeGreaterThan(html.indexOf("L1</span>｜B1"));
  });

  it("stands expanded at text-xs: no details, tooltip, toast or live region", () => {
    const html = renderToStaticMarkup(createElement(Cap1MigrationNoticeBlock, { notice }));
    expect(html).not.toMatch(/<details|title=|aria-live|role="status"|truncate|line-clamp/);
    expect(html).toContain("text-xs");
    expect(html).toContain("sm:col-span-2");
  });
});

import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";
import { SummaryCards } from "../../components/SummaryCards";
import type { PortfolioTotals } from "../types";

/**
 * ADR-0011; 風控 2026-09-19 條件 (1): `fx_disclosures` must render standing,
 * unabridged, beside 匯率貢獻 — same position/style/font-size as every other
 * disclosure (`text-xs text-neutral-400`), never collapsed behind a
 * `<details>` and never `truncate`d.
 */
describe("SummaryCards — fx_disclosures rendering", () => {
  const totals: PortfolioTotals = {
    cost_twd: "100000",
    market_value_twd: "105000",
    unrealized_pnl_twd: "5000",
    asset_contribution_twd: "4000",
    fx_contribution_twd: "1000",
    status: "complete",
  };

  it("renders nothing extra when fx_disclosures is empty", () => {
    const html = renderToStaticMarkup(
      createElement(SummaryCards, { totals, asOf: "2026-09-19T00:00:00Z", fxDisclosures: [] }),
    );
    expect(html).not.toContain("<ul");
  });

  it("renders every disclosure sentence verbatim, uncollapsed and untruncated", () => {
    const disclosures = [
      "匯率為台灣銀行即期買賣中點的模型值，不是官方收盤匯率；該端點與 CSV 欄位格式未經本環境線上查證（verified=false）。",
      "匯率取自 Yahoo Finance 的每日收盤價（非台灣銀行官方牌告），為本次台灣銀行來源不可用時的備援；其口徑與台銀即期中價不同，換算結果可能與官方牌告有落差。該端點未公開文件化，幣別代號（如 TWD=X）與欄位格式均未經本環境線上查證（verified=false）。",
    ];
    const html = renderToStaticMarkup(
      createElement(SummaryCards, { totals, asOf: "2026-09-19T00:00:00Z", fxDisclosures: disclosures }),
    );
    expect(html).toContain("<ul");
    for (const disclosure of disclosures) {
      expect(html).toContain(disclosure);
    }
    expect(html).not.toContain("<details");
    expect(html).not.toContain("truncate");
    expect(html).toContain('class="mt-2 space-y-0.5 text-xs text-neutral-400"');
  });
});

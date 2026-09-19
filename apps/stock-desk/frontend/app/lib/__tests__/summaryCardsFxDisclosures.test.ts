import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";
import { SummaryCards } from "../../components/SummaryCards";
import { FX_BACKUP_BADGE } from "../oneLinerWording";
import type { PortfolioTotals } from "../types";

/**
 * ADR-0011; CEO 2026-09-19 第二次裁定（派工單 §4.1，wave2-B 純搬移）推翻風控
 * 2026-09-19 條件 (1) 的「同位置常駐、不得摺疊」：`fx_disclosures` 現在收進
 * 匯率貢獻卡內的一個 `<details>`（summary 用既有字面
 * `DETAILS_SUMMARY_GENERIC`＝「詳細說明與依據」），句子本身逐字不變、不截斷。
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
      createElement(SummaryCards, {
        totals,
        asOf: "2026-09-19T00:00:00Z",
        fxDisclosures: [],
        fxBackupActive: false,
      }),
    );
    expect(html).not.toContain("<ul");
  });

  it("renders every disclosure sentence verbatim and untruncated, collapsed behind a <details> in the FX card", () => {
    const disclosures = [
      "匯率為台灣銀行即期買賣中點的模型值，不是官方收盤匯率；該端點與 CSV 欄位格式未經本環境線上查證（verified=false）。",
      "匯率取自 Yahoo Finance 的每日收盤價（非台灣銀行官方牌告），為本次台灣銀行來源不可用時的備援；其口徑與台銀即期中價不同，換算結果可能與官方牌告有落差。該端點未公開文件化，幣別代號（如 TWD=X）與欄位格式均未經本環境線上查證（verified=false）。",
    ];
    const html = renderToStaticMarkup(
      createElement(SummaryCards, {
        totals,
        asOf: "2026-09-19T00:00:00Z",
        fxDisclosures: disclosures,
        fxBackupActive: false,
      }),
    );
    expect(html).toContain("<ul");
    for (const disclosure of disclosures) {
      expect(html).toContain(disclosure);
    }
    // wave2-B（CEO 第二次裁定 §4.1）: collapsed inside a <details> now, using
    // the existing generic summary literal — sentences themselves untouched.
    expect(html).toContain("<details");
    expect(html).toContain("詳細說明與依據");
    expect(html).not.toContain("truncate");
    // The <details> must sit inside the 匯率貢獻 card, not beside 標的貢獻.
    const fxCardIndex = html.indexOf("匯率貢獻");
    const detailsIndex = html.indexOf("<details");
    expect(detailsIndex).toBeGreaterThan(fxCardIndex);
  });
});

/**
 * 第二波（派工單 §4.3，風控逐字審核可）：匯率貢獻卡標題旁的「備援匯率」
 * 徽章——任一部位 backup 即顯示，不設門檻、不得 hover-only（本測試只驗證
 * 渲染輸出本身一定出現，不藏在任何 hover 專屬 class 之後）。
 */
describe("SummaryCards — fxBackupActive badge (派工單 §4.3)", () => {
  const totals: PortfolioTotals = {
    cost_twd: "100000",
    market_value_twd: "105000",
    unrealized_pnl_twd: "5000",
    asset_contribution_twd: "4000",
    fx_contribution_twd: "1000",
    status: "complete",
  };

  it("shows the standing badge when any position's FX rate is backup-sourced", () => {
    const html = renderToStaticMarkup(
      createElement(SummaryCards, {
        totals,
        asOf: "2026-09-19T00:00:00Z",
        fxDisclosures: [],
        fxBackupActive: true,
      }),
    );
    expect(html).toContain(FX_BACKUP_BADGE);
    expect(html).not.toMatch(/hover:(?!bg-neutral)[^"]*(?:opacity-0|invisible|hidden)/);
  });

  it("shows no badge when every position's FX rate is fresh (or TWD-only)", () => {
    const html = renderToStaticMarkup(
      createElement(SummaryCards, {
        totals,
        asOf: "2026-09-19T00:00:00Z",
        fxDisclosures: [],
        fxBackupActive: false,
      }),
    );
    expect(html).not.toContain(FX_BACKUP_BADGE);
  });
});

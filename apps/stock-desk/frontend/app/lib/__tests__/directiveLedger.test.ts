import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";
import { DirectiveLedger } from "../../playbook/DirectiveLedger";
import type { PlaybookDirectiveLine } from "../types";

/**
 * 風控 2026-09-15 R3: the ledger is the most advice-like screen and a spliced
 * series reaches it as `fresh` (no badge), so `Directive.data_reason` is the
 * only way the line can say what data it was decided on. It renders as the
 * same standing, body-size sentence as everywhere else -- never a tooltip.
 */
function line(dataReason: string | null): PlaybookDirectiveLine {
  return {
    line: "2330｜買進｜100 股｜規則 R1｜依據資料日 2026-08-11｜預定執行日 2026-08-12｜參考價 100.00（依據交易日收盤價，不反映今日盤中變動）",
    directive: {
      symbol: "2330",
      batch_no: 1,
      action: "buy",
      shares: 100,
      rule_id: "R1",
      rule_summary: "規則全文",
      data_date: "2026-08-11",
      execution_date: "2026-08-12",
      reference_price: "100.00",
      limit_low: "98.00",
      limit_high: "102.00",
      limit_note: "限價帶",
      data_status: "fresh",
      source: "twse",
      data_reason: dataReason,
      status: "pending",
    },
  };
}

describe("DirectiveLedger data_reason — 風控 2026-09-15 R3", () => {
  const spliced = "這段日線資料由多個來源拼接（finmind、twse），每筆保留原本的來源；不同來源的價格處理方式可能不同，接合處的數值可能出現落差。";

  it("shows the persisted reason on a fresh line, standing, body size, no tooltip", () => {
    const html = renderToStaticMarkup(
      createElement(DirectiveLedger, { directives: [line(spliced)], dataDate: "2026-08-11", noDirectiveNote: null }),
    );
    expect(html).toContain("資料狀態 fresh・來源 twse");
    expect(html).toContain(`<span class="ml-1.5 text-sm text-neutral-400">${spliced}</span>`);
    expect(html).not.toContain("title=");
  });

  it("says nothing extra when the line carries no reason", () => {
    const html = renderToStaticMarkup(
      createElement(DirectiveLedger, { directives: [line(null)], dataDate: "2026-08-11", noDirectiveNote: null }),
    );
    expect(html).toContain("資料狀態 fresh・來源 twse");
    expect(html).not.toContain('class="ml-1.5 text-sm text-neutral-400"');
  });
});

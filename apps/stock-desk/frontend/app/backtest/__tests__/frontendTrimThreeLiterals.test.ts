/**
 * RC-712 ~ RC-718 (risk-compliance verbatim review 2026-11-25, 前端減字三項): verbatim locks
 * for the three trimmed sentences and the alert-event observed-key labelling (RC-717 items 1-4).
 * If someone reverts a literal to the old wording, or brings in "case C" (dropping keys), these go red.
 */

import { readFileSync } from "node:fs";
import { join } from "node:path";
import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";
import { AlertEventList } from "../../components/PendingAlertsPanel";
import type { AlertEvent } from "../../lib/types";
import { BacktestReportView } from "../BacktestReportView";
import { makeResponse } from "./roundTripFixtures";

// RC-730: the example number is 0.01 = 1% (previous example retired).
const SENTENCE_1 = "除 ATR 停損倍數外，每一項數字都是分數（例如 0.01 = 1%）。";
const SENTENCE_1B = "此標的市值占總資產(已估值部位市值,不含現金)的上限（比例，例如 0.01 代表 1%）。";
const SENTENCE_2 = "Buy &amp; Hold 為同期間、未計交易成本的被動持有基準。";
const SENTENCE_3 =
  "費率未查證：本次回測使用的手續費／交易稅／滑價率尚未對照主要來源查證，報告數字應視為待查證狀態。";

function countOf(haystack: string, needle: string): number {
  return haystack.split(needle).length - 1;
}

describe("RC-717 item 1: SettingsForm sentence", () => {
  const source = readFileSync(join(__dirname, "../../settings/SettingsForm.tsx"), "utf8");
  // Developer comments legitimately cite the backend path; only user-visible code is locked.
  const code = source.replace(/\/\*[\s\S]*?\*\//g, "").replace(/^\s*\/\/.*$/gm, "").replace(/\s\/\/ .*$/gm, "");

  it("source holds the approved sentence exactly once", () => {
    expect(countOf(source, SENTENCE_1)).toBe(1);
  });

  it("source holds neither the backend path nor the old one-to-one claim", () => {
    expect(code).not.toContain("app/advice/limits.py");
    expect(code).not.toContain("一一對應");
  });

  // RC-738 A1: both approved sentences appear exactly once in the source.
  it("RC-738 A1: both approved sentences appear exactly once", () => {
    expect(countOf(source, SENTENCE_1)).toBe(1);
    expect(countOf(source, SENTENCE_1B)).toBe(1);
  });

  // RC-738 A2: the retired example is gone from the source (comments included).
  it("RC-738 A2: no old example literal remains", () => {
    expect(source).not.toContain("例如 0.15");
    expect(source).not.toContain("15%");
  });

  // RC-738 A3: consistency lock, both sentences carry the same example.
  it("RC-738 A3: both sentences carry 0.01 and 1%", () => {
    for (const sentence of [SENTENCE_1, SENTENCE_1B]) {
      expect(sentence).toContain("0.01");
      expect(sentence).toContain("1%");
    }
  });

  // RC-738 A4 (= RC-717 item 1 assertions kept): the ATR exclusion prefix stays.
  it("RC-738 A4: ATR exclusion prefix is kept", () => {
    expect(source).toContain("除 ATR 停損倍數外，");
  });
});

describe("RC-717 item 2: rendered backtest report", () => {
  const report = makeResponse();
  const html = renderToStaticMarkup(createElement(BacktestReportView, { report }));

  it("rates alert element text is exactly the approved sentence", () => {
    expect(report.rates_verified).toBe(false);
    const alerts = [...html.matchAll(/<p role="alert"[^>]*>([\s\S]*?)<\/p>/g)].map((m) => m[1] ?? "");
    const ratesAlerts = alerts.filter((text) => text.includes("費率未查證"));
    expect(ratesAlerts).toHaveLength(1);
    expect(ratesAlerts[0]).toBe(SENTENCE_3);
  });

  it("Buy & Hold sentence appears once per sample section (two sections), no backend reference", () => {
    expect(countOf(html, SENTENCE_2)).toBe(2);
    expect(html).not.toContain("見後端");
  });
});

describe("RC-717 item 3: alert event observed values", () => {
  function render(overrides: Partial<AlertEvent>): string {
    const event: AlertEvent = {
      id: 1,
      rule_id: 1,
      rule_type: "price_above",
      symbol: "2330",
      market: "TW",
      message: "m",
      observed: {},
      triggered_at: "2026-11-24T01:00:00Z",
      acknowledged: false,
      acknowledged_at: null,
      ...overrides,
    };
    return renderToStaticMarkup(
      createElement(AlertEventList, { events: [event], onAck: () => {}, ackPending: false }),
    );
  }

  // RC-717 item 4 updated for RC-732 ~ RC-734: the expected literals are the approved labels; the
  // anti-"case C" assertions (entry count, date value visible) are kept.
  it("price event: close is labelled, nothing is dropped, four entries remain", () => {
    const html = render({
      observed: { close: 605, threshold: 600, currency: "TWD", bar_as_of: "2026-11-24" },
    });
    expect(html).toContain("資料日收盤價: 605");
    expect(html).toContain("2026-11-24");
    const line = html.match(/資料日收盤價: 605[^<]*/)![0];
    expect(line.split("　")).toHaveLength(4);
    expect(line).toBe("資料日收盤價: 605　設定的門檻: 600　幣別: TWD　資料日期（日線收盤，非即時）: 2026-11-24");
  });

  it("signal_condition event: signals_as_of stays visible", () => {
    const html = render({
      rule_type: "signal_condition",
      observed: { field: "rsi14.last", value: 71.2, op: "gt", compared_to: 70, signals_as_of: "2026-11-24" },
    });
    expect(html).toContain("資料日期（日線收盤，非即時）: 2026-11-24");
  });
});

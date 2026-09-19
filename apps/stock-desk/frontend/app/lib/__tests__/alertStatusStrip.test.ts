/**
 * `AlertStatusStrip` four-state coverage (首頁「一眼一句」簡化 §3.3/§4,
 * `work/stock-desk-一眼一句-實作規格.md`；R-A3 2026-09-19 追加第四態與優先
 * 序）：沒規則／有規則沒觸發／排程總開關關閉／有事件，加上優先序守門，
 * rendered with `renderToStaticMarkup` against the pure `AlertStatusStripView`
 * (no query client needed).
 */

import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";
import { AlertStatusStripView } from "../../components/AlertStatusStrip";
import type { AlertEvent, AlertRule } from "../types";

function makeRule(overrides: Partial<AlertRule>): AlertRule {
  return {
    id: 1,
    type: "price_above",
    symbol: "2330",
    market: "TW",
    params: { threshold: 600 },
    enabled: true,
    note: null,
    created_at: "2026-09-01T00:00:00Z",
    updated_at: "2026-09-01T00:00:00Z",
    ...overrides,
  };
}

function makeEvent(overrides: Partial<AlertEvent>): AlertEvent {
  return {
    id: 1,
    rule_id: 1,
    rule_type: "price_above",
    symbol: "2330",
    market: "TW",
    message: "收盤價高於門檻",
    observed: { close: 605 },
    triggered_at: "2026-09-19T01:00:00Z",
    acknowledged: false,
    acknowledged_at: null,
    ...overrides,
  };
}

function renderStrip(
  rules: AlertRule[],
  events: AlertEvent[],
  schedulerEnabled: boolean | null = true,
  eventsAsOf = "2026-09-19T02:00:00Z",
) {
  return renderToStaticMarkup(
    createElement(AlertStatusStripView, {
      rules,
      events,
      eventsAsOf,
      schedulerEnabled,
      onAck: () => {},
      ackPending: false,
    }),
  );
}

describe("AlertStatusStripView — 四態（B.4 + R-A3）", () => {
  it("狀態 A：沒有任何規則 —— 尚未設定警示規則 + 去設定連結", () => {
    const html = renderStrip([], []);
    expect(html).toContain("尚未設定警示規則");
    expect(html).toContain("去設定");
    expect(html).toContain('href="/settings"');
    // Not the amber "有事件" treatment.
    expect(html).not.toContain("amber-950");
  });

  it("狀態 B：有規則、沒有待處理事件 —— N 用規則總數（不分 enabled/disabled）+ 查詢時間", () => {
    const rules = [makeRule({ id: 1, enabled: true }), makeRule({ id: 2, enabled: false })];
    const html = renderStrip(rules, [], true, "2026-09-19T03:15:00Z");
    // rules.length = 2, regardless of how many are enabled.
    expect(html).toContain("2 條規則已設定，目前沒有待處理警示");
    expect(html).toContain("查詢時間：");
    expect(html).not.toContain("尚未設定警示規則");
    expect(html).not.toContain("amber-950");
  });

  it("狀態 B：規則全部停用時仍印規則總數，不誤報「0 條規則已設定」", () => {
    const rules = [makeRule({ id: 1, enabled: false }), makeRule({ id: 2, enabled: false })];
    const html = renderStrip(rules, [], true);
    expect(html).toContain("2 條規則已設定，目前沒有待處理警示");
  });

  it("狀態 C：有事件 —— N 條待處理警示 + 管理警示規則連結 + 事件清單", () => {
    const rules = [makeRule({ id: 1 })];
    const events = [makeEvent({ id: 1 }), makeEvent({ id: 2, symbol: "2454" })];
    const html = renderStrip(rules, events);
    expect(html).toContain("2 條待處理警示");
    expect(html).toContain("管理警示規則");
    expect(html).toContain("2330");
    expect(html).toContain("2454");
    expect(html).toContain("標記已處理");
    expect(html).toContain("amber-950");
  });

  it("狀態 D（R-A3）：排程總開關關閉 —— 排程未啟用句 + 管理警示規則連結，非 amber", () => {
    const rules = [makeRule({ id: 1 })];
    const html = renderStrip(rules, [], false);
    expect(html).toContain("排程目前未啟用，警示評估暫不會更新");
    expect(html).toContain("管理警示規則");
    expect(html).not.toContain("amber-950");
    expect(html).not.toContain("尚未設定警示規則");
    expect(html).not.toContain("條規則已設定");
    // Must not contain any of the banned reassuring words.
    expect(html).not.toMatch(/安全|正常|無風險/);
  });

  it("狀態 D：總開關關閉且完全沒有規則時仍是狀態 D，不是狀態 A", () => {
    const html = renderStrip([], [], false);
    expect(html).toContain("排程目前未啟用，警示評估暫不會更新");
    expect(html).not.toContain("尚未設定警示規則");
  });

  it("優先序：事件 >0 時，即使總開關關閉，仍顯示狀態 C（事件優先）", () => {
    const rules = [makeRule({ id: 1 })];
    const events = [makeEvent({ id: 1 })];
    const html = renderStrip(rules, events, false);
    expect(html).toContain("1 條待處理警示");
    expect(html).not.toContain("排程目前未啟用");
  });

  it("優先序：schedulerEnabled 為 null（settings 查詢失敗）時退回 A/B/C 判斷，不進入狀態 D", () => {
    const noRules = renderStrip([], [], null);
    expect(noRules).toContain("尚未設定警示規則");
    expect(noRules).not.toContain("排程目前未啟用");

    const withRules = renderStrip([makeRule({ id: 1 })], [], null);
    expect(withRules).toContain("1 條規則已設定，目前沒有待處理警示");
    expect(withRules).not.toContain("排程目前未啟用");
  });
});

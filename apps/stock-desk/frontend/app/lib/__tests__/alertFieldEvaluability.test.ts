/**
 * ADR-0021 K-9 / T-5 front-end side: alert fields the alert pipeline can never
 * evaluate (`UNEVALUABLE_ALERT_FIELDS`), the W-1 / W-3 risk-approved wording
 * (pinned verbatim), the W-R4 "never swallow a 422" rule, and the U-2 anchor
 * that W-1's pointer ("個股頁「風險量測」區") still points at something real.
 *
 * Rendered with `renderToStaticMarkup` (no jsdom in this project), so the
 * stateful modal is rendered through its initial state only; the W-R4 display
 * is tested through the pure pieces the modal composes.
 */

import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it, vi } from "vitest";
import { FRONTEND_FORBIDDEN_TERMS } from "../adviceWording";
import {
  ALERT_FIELD_BETA_NOTE,
  ALERT_RULE_UNEVALUABLE_NOTICE,
  UNEVALUABLE_ALERT_FIELDS,
  UNEVALUABLE_ALERT_FIELD_LABELS,
  ruleUsesUnevaluableField,
} from "../alertFields";
import { SIGNAL_FIELD_OPTIONS, signalFieldLabel } from "../format";
import type { AlertRule, InputsUsed, SignalsPayload } from "../types";
import { assertNoForbiddenTerms, findBareRealtimeClaims } from "./wordingScanHelpers";
import { AlertParamFields } from "../../settings/AlertParamFields";
import { AlertRulesTable } from "../../settings/AlertRulesSection";
import {
  EditAlertRuleModal,
  UnrenderedFieldErrors,
  buildAlertRulePatch,
  decideAlertRuleSubmit,
  scrollFirstAlertIntoView,
  toFormState,
  unrenderedFieldErrorMessages,
} from "../../settings/EditAlertRuleModal";
import { TechnicalIndicatorsPanel } from "../../position/[symbol]/TechnicalIndicatorsPanel";
import { EMPTY_ALERT_PARAM_FORM } from "../alertRuleForm";

// Risk-approved literals, copied independently of the constants under test so a
// silent edit of the source constant turns this file red.
const W1 = "警示不提供 Beta 作為條件，可在個股頁「風險量測」區查看。";
const W3 = "不會觸發（欄位不提供）";
const W4_BETA = "警示不提供 beta.value（相對指標的 beta）作為條件，請改用其他欄位。";

function makeRule(overrides: Partial<AlertRule> = {}): AlertRule {
  return {
    id: 1,
    type: "signal_condition",
    symbol: "2330",
    market: "TW",
    params: { condition: { field: "rsi14.last", op: "gt", value: 70, ref: null } },
    enabled: true,
    note: null,
    created_at: "2026-08-01T00:00:00+08:00",
    updated_at: "2026-08-01T00:00:00+08:00",
    ...overrides,
  };
}

function valueRule(field: string, overrides: Partial<AlertRule> = {}): AlertRule {
  return makeRule({ params: { condition: { field, op: "gt", value: 1.2, ref: null } }, ...overrides });
}

function refRule(field: string, ref: string, overrides: Partial<AlertRule> = {}): AlertRule {
  return makeRule({ params: { condition: { field, op: "gt", value: null, ref } }, ...overrides });
}

function renderTable(rules: AlertRule[]): string {
  return renderToStaticMarkup(
    createElement(AlertRulesTable, { rules, onEdit: () => undefined, onDelete: () => undefined, deleting: false }),
  );
}

function renderModal(rule: AlertRule): string {
  return renderToStaticMarkup(
    createElement(
      QueryClientProvider,
      { client: new QueryClient() },
      createElement(EditAlertRuleModal, { rule, onClose: () => undefined }),
    ),
  );
}

function renderParamFields(field: string): string {
  return renderToStaticMarkup(
    createElement(AlertParamFields, {
      idPrefix: "alert",
      values: { ...EMPTY_ALERT_PARAM_FORM, type: "signal_condition", field },
      onChange: () => undefined,
    }),
  );
}

function occurrences(haystack: string, needle: string): number {
  return haystack.split(needle).length - 1;
}

describe("不可評估欄位集合（ADR-0021 K-9 / U-5）", () => {
  it("集合內容固定為後端 KNOWN_FIELDS − ALERT_RULE_FIELDS 的三個欄位", () => {
    expect([...UNEVALUABLE_ALERT_FIELDS]).toEqual(["beta.value", "position.weight", "position.unrealized_pnl_pct"]);
  });

  it("原始碼註解註明鏡射後端並由後端測試釘住", () => {
    const source = readFileSync(fileURLToPath(new URL("../alertFields.ts", import.meta.url)), "utf8");
    expect(source).toContain("Mirrors backend KNOWN_FIELDS − ALERT_RULE_FIELDS");
    expect(source).toContain("pinned by backend test");
  });

  it("SIGNAL_FIELD_OPTIONS 不含任何不可評估欄位（特別是 beta.value）", () => {
    const values = SIGNAL_FIELD_OPTIONS.map((opt) => opt.value);
    expect(values).not.toContain("beta.value");
    for (const field of UNEVALUABLE_ALERT_FIELDS) expect(values).not.toContain(field);
  });

  it("L-9 凍結：本單不加入 drawdown.current", () => {
    expect(SIGNAL_FIELD_OPTIONS.map((opt) => opt.value)).not.toContain("drawdown.current");
  });

  it("signalFieldLabel 對舊規則仍顯示標籤，不退化成 raw key", () => {
    expect(signalFieldLabel("beta.value")).toBe("相對指標的 beta");
    expect(signalFieldLabel("position.weight")).toBe("此標的佔投資組合比重");
    expect(signalFieldLabel("position.unrealized_pnl_pct")).toBe("此部位未實現損益率");
    for (const field of UNEVALUABLE_ALERT_FIELDS) {
      expect(signalFieldLabel(field)).toBe(UNEVALUABLE_ALERT_FIELD_LABELS[field]);
      expect(signalFieldLabel(field)).not.toBe(field);
    }
    expect(signalFieldLabel("close")).toBe("最新收盤價");
    expect(signalFieldLabel("no.such.field")).toBe("no.such.field");
  });

  it("ruleUsesUnevaluableField 只由集合決定：field 或 ref，其餘類型一律否", () => {
    for (const field of UNEVALUABLE_ALERT_FIELDS) {
      expect(ruleUsesUnevaluableField(valueRule(field))).toBe(true);
      expect(ruleUsesUnevaluableField(refRule("close", field))).toBe(true);
    }
    for (const opt of SIGNAL_FIELD_OPTIONS) {
      expect(ruleUsesUnevaluableField(valueRule(opt.value))).toBe(false);
      expect(ruleUsesUnevaluableField(refRule("close", opt.value))).toBe(false);
    }
    expect(ruleUsesUnevaluableField(makeRule({ type: "price_above", params: { threshold: 600 } }))).toBe(false);
    expect(ruleUsesUnevaluableField(makeRule({ type: "risk_limit_breach", params: { limit_id: "any" } }))).toBe(false);
  });
});

describe("W-1：訊號欄位 select 下方常駐說明（逐字）", () => {
  it("常數與核可字面逐字相同", () => {
    expect(ALERT_FIELD_BETA_NOTE).toBe(W1);
  });

  it.each(["close", "rsi14.last", "beta.value"])("選 %s 時皆顯示，且在同一欄位 div 內緊接 select", (field) => {
    const html = renderParamFields(field);
    expect(html).toContain(W1);
    expect(occurrences(html, W1)).toBe(1);
    const afterSelect = html.indexOf("</select>");
    expect(html.indexOf(W1)).toBeGreaterThan(afterSelect);
    // Same column div: no `</div>` between the select's close and the note.
    expect(html.slice(afterSelect, html.indexOf(W1))).not.toContain("</div>");
    // It is the first thing after the field select — before the 條件 select.
    expect(html.indexOf(W1)).toBeLessThan(html.indexOf('id="alert-op"'));
  });

  it("不小於 text-xs、不暗於 neutral-400，且無 truncate／line-clamp／tooltip／sr-only／details", () => {
    const html = renderParamFields("close");
    const note = /<p id="alert-field-note" class="([^"]*)">/.exec(html);
    expect(note).not.toBeNull();
    const classes = (note?.[1] ?? "").split(" ");
    expect(classes).toContain("text-xs");
    expect(classes).toContain("text-neutral-400");
    for (const banned of ["truncate", "sr-only", "hidden", "text-neutral-500", "text-neutral-600"]) {
      expect(classes).not.toContain(banned);
    }
    expect(classes.some((c) => c.startsWith("line-clamp"))).toBe(false);
    expect(html).not.toContain("title=");
    expect(html).not.toContain("<details");
  });

  it("select 以 aria-describedby 指向說明", () => {
    const html = renderParamFields("close");
    expect(html).toContain('aria-describedby="alert-field-note"');
    expect(html).toContain('id="alert-field-note"');
  });

  it("價格門檻類型不渲染（說明只屬於訊號欄位）", () => {
    const html = renderToStaticMarkup(
      createElement(AlertParamFields, {
        idPrefix: "alert",
        values: { ...EMPTY_ALERT_PARAM_FORM, type: "price_above" },
        onChange: () => undefined,
      }),
    );
    expect(html).not.toContain(W1);
  });

  it("新建選單不再提供 beta.value 選項", () => {
    expect(renderParamFields("close")).not.toContain('value="beta.value"');
  });

  it("編輯舊 beta 規則：受控 select 顯示原欄位（選項保留並被選取），不默默顯示第一個選項", () => {
    const html = renderParamFields("beta.value");
    expect(html).toContain('<option value="beta.value" selected="">相對指標的 beta</option>');
    expect(html).not.toContain('<option value="close" selected="">');
  });
});

describe("W-3：規則清單「條件」儲存格（逐字、集合決定）", () => {
  it("常數與核可字面逐字相同", () => {
    expect(ALERT_RULE_UNEVALUABLE_NOTICE).toBe(W3);
  });

  it("集合內每個欄位（field 與 ref 兩側）都顯示 W-3；選單內欄位一律不顯示", () => {
    for (const field of UNEVALUABLE_ALERT_FIELDS) {
      expect(occurrences(renderTable([valueRule(field)]), W3), `field ${field}`).toBe(1);
      expect(occurrences(renderTable([refRule("close", field)]), W3), `ref ${field}`).toBe(1);
    }
    for (const opt of SIGNAL_FIELD_OPTIONS) {
      expect(renderTable([valueRule(opt.value)]), `field ${opt.value}`).not.toContain(W3);
      expect(renderTable([refRule("close", opt.value)]), `ref ${opt.value}`).not.toContain(W3);
    }
  });

  it("price／risk_limit 規則不顯示", () => {
    const html = renderTable([
      makeRule({ id: 2, type: "price_above", params: { threshold: 600 } }),
      makeRule({ id: 3, type: "risk_limit_breach", params: { limit_id: "any" } }),
    ]);
    expect(html).not.toContain(W3);
  });

  it("W-3 在第一欄（代號）、緊接 symbol／market 文字之後；條件欄不含 W-3；與「啟用中／已停用」並存", () => {
    const enabled = renderTable([valueRule("beta.value", { enabled: true })]);
    const disabled = renderTable([valueRule("beta.value", { enabled: false })]);
    for (const [html, status] of [
      [enabled, "啟用中"],
      [disabled, "已停用"],
    ] as const) {
      expect(occurrences(html, W3)).toBe(1);
      expect(html).toContain(`>${status}<`);
      const cells = [...html.matchAll(/<td[^>]*>([\s\S]*?)<\/td>/g)].map((m) => m[1] ?? "");
      expect(cells[0]).toContain("2330（TW）");
      expect(cells[0]).toContain(W3);
      expect(cells[0]?.indexOf(W3)).toBeGreaterThan(cells[0]?.indexOf("2330（TW）") ?? Infinity);
      for (const other of cells.slice(1)) expect(other).not.toContain(W3);
      // The condition column carries the description only, with the legacy label (S6-1), not the raw key.
      expect(cells[2]).toBe("相對指標的 beta 大於（&gt;） 1.2");
      expect(cells[3]).toBe(status);
    }
  });

  it("D-12 (b)：窄幅狀態副標在第一欄 W-3 之後（sm:hidden），狀態欄 th／td 僅 sm 以上顯示，每列狀態字面恰好 2 次（互斥顯示）", () => {
    for (const [enabled, status] of [
      [true, "啟用中"],
      [false, "已停用"],
    ] as const) {
      const html = renderTable([valueRule("beta.value", { enabled })]);
      const cells = [...html.matchAll(/<td([^>]*)>([\s\S]*?)<\/td>/g)].map((m) => ({ attrs: m[1] ?? "", inner: m[2] ?? "" }));
      // First column: W-3 stays, then the status subtitle comes after it.
      const first = cells[0]?.inner ?? "";
      const subtitle = /<div class="([^"]*)">([^<]*)<\/div>$/.exec(first);
      expect(subtitle).not.toBeNull();
      expect(subtitle?.[2]).toBe(status);
      const subtitleClasses = (subtitle?.[1] ?? "").split(" ");
      expect(subtitleClasses).toContain("sm:hidden");
      expect(subtitleClasses).toContain("text-neutral-300");
      expect(first.indexOf(status)).toBeGreaterThan(first.indexOf(W3));
      expect(occurrences(first, W3)).toBe(1);
      // Status column: cells[3] is still the status, hidden below sm.
      expect(cells[3]?.inner).toBe(status);
      const tdClasses = (/class="([^"]*)"/.exec(cells[3]?.attrs ?? "")?.[1] ?? "").split(" ");
      expect(tdClasses).toContain("hidden");
      expect(tdClasses).toContain("sm:table-cell");
      // Header: still "狀態" at index 3, hidden below sm.
      const ths = [...html.matchAll(/<th([^>]*)>([\s\S]*?)<\/th>/g)].map((m) => ({ attrs: m[1] ?? "", inner: m[2] ?? "" }));
      expect(ths[3]?.inner).toBe("狀態");
      const thClasses = (/class="([^"]*)"/.exec(ths[3]?.attrs ?? "")?.[1] ?? "").split(" ");
      expect(thClasses).toContain("hidden");
      expect(thClasses).toContain("sm:table-cell");
      // Same text rendered twice (mutually exclusive by breakpoint); keep both in sync.
      expect(occurrences(html, `>${status}<`)).toBe(2);
      expect(html).toContain("min-w-[620px]");
    }
  });

  it("以文字加左側豎線呈現（art-lead 裁示）：text-xs、text-amber-400、max-w-[9rem]、可換行，無 truncate／tooltip", () => {
    const html = renderTable([valueRule("position.weight")]);
    const match = /<div class="([^"]*)">不會觸發（欄位不提供）<\/div>/.exec(html);
    expect(match).not.toBeNull();
    const classes = (match?.[1] ?? "").split(" ");
    expect(classes).toEqual(
      expect.arrayContaining(["text-xs", "text-amber-400", "border-l-2", "border-amber-400", "max-w-[9rem]", "leading-snug", "text-balance"]),
    );
    for (const banned of ["truncate", "sr-only", "whitespace-nowrap", "text-neutral-500", "text-neutral-600"]) {
      expect(classes).not.toContain(banned);
    }
    expect(classes.some((c) => c.startsWith("line-clamp") || c.startsWith("text-ellipsis"))).toBe(false);
    expect(html).not.toContain("title=");
    expect(html).toContain("min-w-[620px]");
    expect(html).toContain("overflow-x-auto");
  });
});

describe("S6-1：規則清單「條件」欄以標籤顯示欄位，不露出原始鍵", () => {
  function conditionCell(rule: AlertRule): string {
    const cells = [...renderTable([rule]).matchAll(/<td[^>]*>([\s\S]*?)<\/td>/g)].map((m) => m[1] ?? "");
    return cells[2] ?? "";
  }

  it("close 規則顯示「最新收盤價」而非 close", () => {
    const cell = conditionCell(valueRule("close"));
    expect(cell).toBe("最新收盤價 大於（&gt;） 1.2");
    expect(cell).not.toContain("close");
  });

  it("ref 型兩側皆為標籤", () => {
    const cell = conditionCell(refRule("ma5.last", "ma20.last"));
    expect(cell).toBe("5 日均線最新值 大於（&gt;） 20 日均線最新值");
    expect(cell).not.toContain("ma5.last");
    expect(cell).not.toContain("ma20.last");
  });

  it("已移除欄位（beta.value／position.*）顯示舊標籤", () => {
    expect(conditionCell(refRule("position.weight", "beta.value"))).toBe(
      "此標的佔投資組合比重 大於（&gt;） 相對指標的 beta",
    );
  });

  it("未知欄位 fallback 為原始鍵，不為空字串或 undefined", () => {
    const cell = conditionCell(valueRule("legacy.unknown_field"));
    expect(cell).toBe("legacy.unknown_field 大於（&gt;） 1.2");
    expect(cell).not.toContain("undefined");
    const refCell = conditionCell(refRule("legacy.unknown_field", "other.unknown"));
    expect(refCell).toBe("legacy.unknown_field 大於（&gt;） other.unknown");
  });
});

describe("W-3：編輯對話框兩分支", () => {
  it("ref 分支：緊接「訊號欄位：…」列顯示 W-3", () => {
    const html = renderModal(refRule("close", "beta.value"));
    expect(html).toContain(W3);
    const row = html.indexOf("訊號欄位：");
    expect(row).toBeGreaterThan(-1);
    expect(html.indexOf("比較欄位：相對指標的 beta")).toBeGreaterThan(row);
    // Directly after the row's own paragraph, before the read-only hint.
    const afterRow = html.slice(html.indexOf("</p>", row));
    expect(afterRow.startsWith(`</p><p class="mt-0.5 border-l-2 border-amber-400 pl-1.5 text-xs leading-snug text-amber-400">${W3}</p>`)).toBe(true);
  });

  it("ref 分支：field 為不可評估欄位也顯示", () => {
    expect(renderModal(refRule("position.weight", "close"))).toContain(W3);
  });

  it("value 分支：先明示原欄位「相對指標的 beta」，W-3 緊鄰其後；select 保留原欄位", () => {
    const html = renderModal(valueRule("beta.value"));
    expect(html).toContain(`訊號欄位：相對指標的 beta</p><p class="mt-0.5 border-l-2 border-amber-400 pl-1.5 text-xs leading-snug text-amber-400">${W3}</p>`);
    expect(html).toContain('<option value="beta.value" selected="">相對指標的 beta</option>');
    expect(html).toContain(W1);
    expect(occurrences(html, W3)).toBe(1);
  });

  it.each(UNEVALUABLE_ALERT_FIELDS)("value 分支：%s 由集合決定而顯示 W-3", (field) => {
    expect(renderModal(valueRule(field))).toContain(W3);
  });

  it("一般規則（兩分支）不顯示 W-3", () => {
    expect(renderModal(valueRule("rsi14.last"))).not.toContain(W3);
    expect(renderModal(refRule("ma5.last", "ma20.last"))).not.toContain(W3);
    expect(renderModal(makeRule({ type: "price_above", params: { threshold: 600 } }))).not.toContain(W3);
  });

  it("只改 enabled／note 後儲存：PATCH 不帶 params，且不被本地驗證擋下", () => {
    for (const rule of [valueRule("beta.value"), refRule("close", "beta.value")]) {
      const toggled = { ...toFormState(rule), enabled: false };
      expect(buildAlertRulePatch(toggled, rule)).toEqual({ enabled: false });
      const noted = { ...toFormState(rule), note: "留存" };
      expect(buildAlertRulePatch(noted, rule)).toEqual({ note: "留存" });
      expect(decideAlertRuleSubmit(toggled, rule)).toEqual({ kind: "patch", patch: { enabled: false } });
    }
  });
});

describe("W-R4：未被接住的 fieldErrors 逐字顯示在對話框內", () => {
  const valueForm = toFormState(valueRule("beta.value"));
  const refForm = toFormState(refRule("close", "beta.value"));
  const priceForm = toFormState(makeRule({ type: "price_above", params: { threshold: 600 } }));

  it("loc 末段為 params：W-4 原句顯示，不加前綴", () => {
    expect(unrenderedFieldErrorMessages({ params: W4_BETA }, valueForm)).toEqual([W4_BETA]);
  });

  it("未知鍵與 field／ref／market 等鍵也顯示", () => {
    expect(unrenderedFieldErrorMessages({ whatever: "A", field: "B", ref: "C", market: "D" }, valueForm)).toEqual([
      "A",
      "B",
      "C",
      "D",
    ]);
  });

  it("已有專屬欄位的鍵不重複顯示：symbol／note 恆有；threshold 只在價格規則；value 只在 value 分支", () => {
    expect(unrenderedFieldErrorMessages({ symbol: "s", note: "n", value: "v", threshold: "t" }, valueForm)).toEqual(["t"]);
    expect(unrenderedFieldErrorMessages({ symbol: "s", note: "n", value: "v", threshold: "t" }, priceForm)).toEqual(["v"]);
    // The ref branch has no 比較值 input, so a `value` error would be invisible there.
    expect(unrenderedFieldErrorMessages({ value: "v" }, refForm)).toEqual(["v"]);
  });

  it("相同訊息只顯示一次；空字串略過；無錯誤時為空", () => {
    expect(unrenderedFieldErrorMessages({ params: W4_BETA, field: W4_BETA, ref: "" }, valueForm)).toEqual([W4_BETA]);
    expect(unrenderedFieldErrorMessages({}, valueForm)).toEqual([]);
  });

  it("UnrenderedFieldErrors 以 role=alert 逐字渲染訊息；無訊息時不渲染", () => {
    const html = renderToStaticMarkup(createElement(UnrenderedFieldErrors, { messages: [W4_BETA] }));
    expect(html).toContain('role="alert"');
    expect(html).toContain(`<p>${W4_BETA}</p>`);
    expect(renderToStaticMarkup(createElement(UnrenderedFieldErrors, { messages: [] }))).toBe("");
  });
});

describe("W-R8：送出 422 後錯誤框捲入對話框可視範圍", () => {
  // This suite runs under the node environment (no jsdom, see vitest.config.ts),
  // so there is no `Element.prototype`; a minimal fake root stands in for the
  // dialog and records the selector the helper asks for.
  type ScrollMock = ReturnType<typeof vi.fn<(arg?: ScrollIntoViewOptions) => void>>;
  function fakeRoot(alertsInDocumentOrder: Array<{ scrollIntoView: ScrollMock }>) {
    const querySelector = vi.fn((selectors: string) => (selectors === '[role="alert"]' ? (alertsInDocumentOrder[0] ?? null) : null));
    return { querySelector };
  }

  it("對第一個 [role=alert] 呼叫 scrollIntoView({ block: 'nearest' })（不用 smooth）", () => {
    const first = { scrollIntoView: vi.fn<(arg?: ScrollIntoViewOptions) => void>() };
    const second = { scrollIntoView: vi.fn<(arg?: ScrollIntoViewOptions) => void>() };
    const root = fakeRoot([first, second]);
    scrollFirstAlertIntoView(root);
    expect(root.querySelector).toHaveBeenCalledWith('[role="alert"]');
    expect(first.scrollIntoView).toHaveBeenCalledTimes(1);
    expect(first.scrollIntoView).toHaveBeenCalledWith({ block: "nearest" });
    expect(second.scrollIntoView).not.toHaveBeenCalled();
  });

  it("root 為 null 或沒有錯誤框時不丟錯", () => {
    expect(() => scrollFirstAlertIntoView(null)).not.toThrow();
    expect(() => scrollFirstAlertIntoView(fakeRoot([]))).not.toThrow();
  });

  it("W-4 句經 422 → unrenderedFieldErrorMessages → UnrenderedFieldErrors：[role=alert] 內逐字為 W-4，且是 helper 選取的那個元素", () => {
    const form = toFormState(valueRule("beta.value"));
    const messages = unrenderedFieldErrorMessages({ params: W4_BETA }, form);
    const html = renderToStaticMarkup(createElement(UnrenderedFieldErrors, { messages }));
    expect(html).toMatch(/^<div role="alert"/);
    expect(html).toContain(`<p>${W4_BETA}</p>`);
  });

  it("EditAlertRuleModal 把 ref 掛在對話框、於錯誤出現時（useEffect）呼叫 helper", () => {
    const src = readFileSync(fileURLToPath(new URL("../../settings/EditAlertRuleModal.tsx", import.meta.url)), "utf8");
    expect(src).toMatch(/ref=\{dialogRef\}\s+role="dialog"/);
    expect(src).toMatch(/useEffect\(\(\) => \{\s+if \(alertKey === ""\) return;\s+scrollFirstAlertIntoView\(dialogRef\.current\);\s+\}, \[alertKey\]\);/);
  });
});

describe("U-2：W-1 指向的「風險量測」區仍存在（改名或搬移即紅，須送回風控重審）", () => {
  const INPUTS: InputsUsed = { columns: ["close"], window: {}, description: "fixture" };
  const payload: SignalsPayload = {
    symbol: "2330",
    bar_count: 300,
    as_of: "2026-10-04T08:00:00Z",
    source: "demo",
    risk: {
      volatility: {
        status: "insufficient_data",
        annualized_volatility: null,
        daily_volatility: null,
        observations: 0,
        inputs_used: INPUTS,
        as_of: null,
        source: null,
      },
      drawdown: {
        status: "insufficient_data",
        max_drawdown: null,
        peak_date: null,
        trough_date: null,
        observations: 0,
        inputs_used: INPUTS,
        as_of: null,
        source: null,
      },
      beta: {
        status: "insufficient_data",
        beta: null,
        observations: 0,
        benchmark: null,
        inputs_used: INPUTS,
        as_of: null,
        source: null,
      },
    },
  };

  it("h4 文字為「風險量測」，Beta 卡在該分組內", () => {
    const html = renderToStaticMarkup(createElement(TechnicalIndicatorsPanel, { payload, lastBarDate: "2026-10-02" }));
    const heading = /<h4 [^>]*>\s*風險量測\s*<\/h4>/.exec(html);
    expect(heading, "h4「風險量測」不存在").not.toBeNull();
    const headingEnd = (heading?.index ?? 0) + (heading?.[0].length ?? 0);
    const betaTitle = html.indexOf("Beta（相對比較基準指數的敏感度）");
    expect(betaTitle).toBeGreaterThan(headingEnd);
    // No other group heading (the uppercase section h4) sits between it and the Beta card.
    expect(html.slice(headingEnd, betaTitle)).not.toContain("uppercase");
    // W-1 names exactly this heading text.
    expect(W1).toContain("「風險量測」區");
  });

  it("元件原始碼中 h4「風險量測」與 BetaCard 位於同一個分組 div", () => {
    const source = readFileSync(
      fileURLToPath(new URL("../../position/[symbol]/TechnicalIndicatorsPanel.tsx", import.meta.url)),
      "utf8",
    );
    const group = /\{risk && \(\s*<div>\s*<h4[^>]*>\s*風險量測\s*<\/h4>[\s\S]*?<BetaCard result=\{risk\.beta\} \/>/.exec(source);
    expect(group, "風險量測 h4 與 BetaCard 不在同一分組").not.toBeNull();
  });
});

describe("字面掃描：W-1／W-3 與渲染輸出不含禁用詞與裸「即時」", () => {
  it("來源常數", () => {
    for (const [label, text] of [
      ["W-1", ALERT_FIELD_BETA_NOTE],
      ["W-3", ALERT_RULE_UNEVALUABLE_NOTICE],
      ...Object.values(UNEVALUABLE_ALERT_FIELD_LABELS).map((l) => [`label ${l}`, l] as const),
    ] as const) {
      assertNoForbiddenTerms(text, FRONTEND_FORBIDDEN_TERMS, label);
      expect(findBareRealtimeClaims(text), label).toEqual([]);
    }
  });

  it("渲染輸出（清單、對話框兩分支、新建表單）", () => {
    const outputs = [
      renderTable([valueRule("beta.value"), refRule("close", "position.weight"), valueRule("position.unrealized_pnl_pct")]),
      renderModal(valueRule("beta.value")),
      renderModal(refRule("close", "beta.value")),
      renderParamFields("close"),
    ];
    for (const [index, html] of outputs.entries()) {
      assertNoForbiddenTerms(html, FRONTEND_FORBIDDEN_TERMS, `rendered output #${index}`);
      expect(findBareRealtimeClaims(html), `rendered output #${index}`).toEqual([]);
    }
  });

  it("不使用「訊號頁」一詞（UI 沒有訊號頁）", () => {
    expect(W1).not.toContain("訊號頁");
    expect(renderParamFields("close")).not.toContain("訊號頁");
  });
});

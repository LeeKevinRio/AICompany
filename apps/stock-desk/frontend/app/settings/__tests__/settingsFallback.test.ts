/**
 * N-156 設定頁揭露與 W-2 覆寫面板的前端守門（ADR-0032 K-6、K-11、DL-2、DL-6；
 * 風控 2026-10-29 N-156 字面定稿 第 1、6 項）。
 *
 * 字面一律由後端下發、前端原樣渲染。這裡的 fixture 全用 `SENTINEL-*` 哨兵字串
 * （比照 `Cap1DisclosureBlock.test.ts`）：真句子只在後端逐字守門；哨兵只可能因
 * 「原樣傳遞」而出現在輸出，前端若自撰、改寫或拼接任何一句，就會在這裡現形。
 * 前端只持有風控第 1 項表格固定、後端不下發的兩個詞（「使用預設值」「無法顯示」）。
 *
 * 本專案的 vitest 跑純 Node、沒有 jsdom（`vitest.config.ts`），所以互動行為
 * （勾選、PUT body、兩道確認的先後）以純函式單元測試釘住，元件則以
 * `renderToStaticMarkup` 驗結構，與既有 `riskWidening` 的作法一致。
 */

import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it, vi } from "vitest";
import { ApiError } from "../../lib/api";
import {
  ancestorsOf,
  elementsOf,
  findAll,
  findOne,
  nextElementSibling,
  parseHtml,
  textOf,
} from "../../backtest/__tests__/htmlTree";
import { chineseLiteralsOutsideComments, stripComments } from "../../lib/__tests__/wordingScanHelpers";
import type { CapWidening } from "../../lib/riskWidening";
import {
  buildFormPatch,
  buildNetWorthPatch,
  carriedFormSections,
  fallbackSectionsOf,
  formFallbackSections,
  isFallbackSection,
  NET_WORTH_FALLBACK_BADGE_LABEL,
  NET_WORTH_FALLBACK_VALUE_LABEL,
  resolveFormSaveStep,
  sectionMarkerOf,
} from "../../lib/settingsFallback";
import type {
  AppSettingsPatch,
  OverwritePanelView,
  SettingsFallbackView,
  SettingsResponse,
} from "../../lib/types";

const mutationState = vi.hoisted(() => ({
  current: undefined as unknown,
}));

vi.mock("../../lib/queries", async (importOriginal) => ({
  ...(await importOriginal<typeof import("../../lib/queries")>()),
  useUpdateSettings: () => mutationState.current,
}));

const { SettingsForm } = await import("../SettingsForm");
const { NetWorthSection } = await import("../NetWorthSection");
const { OverwritePanel } = await import("../OverwritePanel");
const { SettingsFallbackNotice, SectionFallbackMarker } = await import("../SettingsFallbackNotice");

/* --- Fixtures ---------------------------------------------------------------- */

const IDLE_MUTATION = {
  mutate: () => undefined,
  reset: () => undefined,
  isPending: false,
  isError: false,
  isSuccess: false,
  error: null,
  data: undefined,
};

function panel(overrides: Partial<OverwritePanelView> & Pick<OverwritePanelView, "sections">): OverwritePanelView {
  return {
    title: "SENTINEL-PANEL-TITLE",
    paragraphs: ["SENTINEL-PANEL-P1", "SENTINEL-PANEL-P2"],
    checkboxes: [],
    confirm_label: "SENTINEL-CONFIRM",
    cancel_label: "SENTINEL-CANCEL",
    ...overrides,
  };
}

const FORM_PANEL = panel({
  sections: ["risk_budget", "alerts"],
  checkboxes: [
    { section: "risk_budget", label: "SENTINEL-CHECK-RISK" },
    { section: "alerts", label: "SENTINEL-CHECK-ALERTS" },
  ],
});
const NET_WORTH_PANEL = panel({
  sections: ["net_worth"],
  title: "SENTINEL-NW-PANEL-TITLE",
  confirm_label: "SENTINEL-NW-CONFIRM",
  cancel_label: "SENTINEL-NW-CANCEL",
});

function fallbackView(sections: string[]): SettingsFallbackView {
  return {
    sections,
    notice: {
      title: "SENTINEL-NOTICE-TITLE",
      items: [
        { label: "SENTINEL-LABEL-ONE", body: "SENTINEL-BODY-ONE" },
        { label: "SENTINEL-LABEL-TWO", body: "SENTINEL-BODY-TWO" },
      ],
    },
    section_markers: Object.fromEntries(sections.map((s) => [s, `SENTINEL-MARKER-${s.toUpperCase()}`])),
    form_overwrite_panel: sections.some((s) => s !== "net_worth") ? FORM_PANEL : null,
    net_worth_overwrite_panel: sections.includes("net_worth") ? NET_WORTH_PANEL : null,
  };
}

function settingsResponse(overrides: Partial<SettingsResponse> = {}): SettingsResponse {
  return {
    settings: {
      risk_budget: {
        max_position_weight: 0.1,
        max_sector_weight: 0.3,
        max_gross_exposure: 1,
        max_loss_per_trade: 0.01,
        atr_stop_multiple: 2,
        kelly_fraction_cap: 0.25,
        kelly_position_cap: 0.1,
      },
      cost_model: {
        tw_broker_fee_rate: 0.001425,
        tw_tax_rate_stock: 0.003,
        tw_tax_rate_etf: 0.001,
        us_broker_fee_rate: 0,
        us_sell_regulatory_fee_rate: 0.0000278,
        slippage_bps: 0,
        verified_on: null,
      },
      alerts: {
        enabled: true,
        evaluation_interval_minutes: 60,
        cooldown_minutes: 60,
        notify_webhooks: true,
      },
      net_worth: {
        total_net_worth_twd: null,
        updated_at: null,
        valued_book_twd_at_report: null,
      },
    },
    rates_verified: false,
    notes: [],
    net_worth: {
      total_net_worth_twd: null,
      updated_at: null,
      age_days: null,
      freshness: "absent",
      notes: ["SENTINEL-NW-NOTE"],
      warnings: [],
    },
    cap1_migration: null,
    settings_fallback: null,
    partial_save_notice: null,
    as_of: "2026-10-29T00:00:00+00:00",
    ...overrides,
  };
}

const NET_WORTH_FALLBACK_RESPONSE = settingsResponse({
  settings_fallback: fallbackView(["net_worth"]),
  net_worth: {
    total_net_worth_twd: null,
    updated_at: null,
    age_days: null,
    freshness: "fallback",
    notes: ["SENTINEL-NW-NOTE"],
    warnings: [],
  },
});

function render(component: unknown, props: Record<string, unknown>): string {
  mutationState.current ??= IDLE_MUTATION;
  return renderToStaticMarkup(createElement(component as never, props as never));
}

function renderWith(mutation: object, component: unknown, props: Record<string, unknown>): string {
  mutationState.current = mutation;
  try {
    return render(component, props);
  } finally {
    mutationState.current = IDLE_MUTATION;
  }
}

function sourceOf(relativeToThisFile: string): string {
  return readFileSync(fileURLToPath(new URL(relativeToThisFile, import.meta.url)), "utf8");
}

/* --- Header block ------------------------------------------------------------ */

describe("SettingsFallbackNotice — 頁首區塊（風控 第 1 項；K-6 哨兵）", () => {
  const html = render(SettingsFallbackNotice, { fallback: fallbackView(["risk_budget"]) });
  const root = parseHtml(html);

  it("渲染結果逐字等於後端下發的 title 與各 item，順序不變，前端沒有自撰或拼接任何一個字", () => {
    expect(textOf(root)).toBe(
      "SENTINEL-NOTICE-TITLE" +
        "SENTINEL-LABEL-ONE｜SENTINEL-BODY-ONE" +
        "SENTINEL-LABEL-TWO｜SENTINEL-BODY-TWO",
    );
  });

  it("不在任何 <details> 內、不能關閉（沒有按鈕、沒有 summary）、不是 toast／live region", () => {
    expect(html).not.toContain("<details");
    expect(html).not.toContain("<summary");
    expect(findAll(root, (el) => el.tag === "button")).toEqual([]);
    expect(html).not.toMatch(/role="(status|alert)"|aria-live|title="|hidden/);
    for (const element of elementsOf(root)) {
      expect(ancestorsOf(element).some((a) => a.tag === "details")).toBe(false);
    }
  });

  it("至少 text-sm、琥珀色、不用 text-xs，也不用比 neutral-300 淡的灰", () => {
    expect(html).toContain("text-sm");
    expect(html).toContain("text-amber-200");
    expect(html).not.toMatch(/text-xs|text-neutral-(400|500|600|700)|opacity-|sr-only/);
  });
});

describe("SectionFallbackMarker — 各回落段 h2 下方（風控 第 1 項）", () => {
  it("逐字渲染後端下發的標記，text-sm 琥珀色，不可收合", () => {
    const html = render(SectionFallbackMarker, { text: "SENTINEL-MARKER" });
    expect(textOf(parseHtml(html))).toBe("SENTINEL-MARKER");
    expect(html).toContain("text-sm");
    expect(html).toContain("text-amber-300");
    expect(html).not.toMatch(/text-xs|<details|hidden/);
  });

  it("沒有標記時什麼都不渲染", () => {
    expect(render(SectionFallbackMarker, { text: null })).toBe("");
  });
});

/* --- Overwrite panel --------------------------------------------------------- */

describe("OverwritePanel — W-2 覆寫面板（風控 第 6 項；DL-6）", () => {
  const props = { onToggle: () => undefined, onConfirm: () => undefined, onCancel: () => undefined, disabled: false };

  it("每段一個勾選框，預設全部不勾選", () => {
    const html = render(OverwritePanel, { ...props, panel: FORM_PANEL, checked: new Set<string>() });
    const boxes = findAll(parseHtml(html), (el) => el.tag === "input");
    expect(boxes).toHaveLength(2);
    for (const box of boxes) {
      expect(box.attrs.type).toBe("checkbox");
      expect(box.attrs).not.toHaveProperty("checked");
    }
  });

  it("只有使用者勾的段才是勾選狀態，勾選框的標籤與其餘字面逐字等於後端下發", () => {
    const html = render(OverwritePanel, { ...props, panel: FORM_PANEL, checked: new Set(["alerts"]) });
    const root = parseHtml(html);
    const boxes = findAll(root, (el) => el.tag === "input");
    expect(boxes.map((box) => Object.hasOwn(box.attrs, "checked"))).toEqual([false, true]);
    expect(textOf(root)).toBe(
      "SENTINEL-PANEL-TITLE" +
        "SENTINEL-PANEL-P1" +
        "SENTINEL-PANEL-P2" +
        "SENTINEL-CHECK-RISK" +
        "SENTINEL-CHECK-ALERTS" +
        "SENTINEL-CONFIRM" +
        "SENTINEL-CANCEL",
    );
  });

  it("net_worth 版沒有勾選框，確認鈕就是確認；兩顆按鈕都是 type=button，不會順手送出表單", () => {
    const html = render(OverwritePanel, { ...props, panel: NET_WORTH_PANEL, checked: new Set<string>() });
    const root = parseHtml(html);
    expect(findAll(root, (el) => el.tag === "input")).toEqual([]);
    const buttons = findAll(root, (el) => el.tag === "button");
    expect(buttons.map(textOf)).toEqual(["SENTINEL-NW-CONFIRM", "SENTINEL-NW-CANCEL"]);
    expect(buttons.every((button) => button.attrs.type === "button")).toBe(true);
  });

  it("disabled 時兩顆按鈕都帶原生 disabled 與 cursor-not-allowed", () => {
    const html = render(OverwritePanel, { ...props, disabled: true, panel: NET_WORTH_PANEL, checked: new Set<string>() });
    const buttons = findAll(parseHtml(html), (el) => el.tag === "button");
    for (const button of buttons) {
      expect(Object.hasOwn(button.attrs, "disabled")).toBe(true);
      expect(button.attrs.class).toContain("disabled:cursor-not-allowed");
    }
  });
});

/* --- Which sections fell back: from `sections` only (K-6) --------------------- */

describe("回落判斷只看 settings_fallback.sections（K-6）", () => {
  it("沒有 settings_fallback 就是沒有任何回落段，即使數值看起來像預設", () => {
    const response = settingsResponse();
    expect(fallbackSectionsOf(response.settings_fallback)).toEqual([]);
    expect(formFallbackSections(response)).toEqual([]);
    expect(isFallbackSection(response, "net_worth")).toBe(false);
    expect(sectionMarkerOf(response, "risk_budget")).toBeNull();
  });

  it("sections 列出的段才算回落；標記只對回落段給", () => {
    const response = settingsResponse({ settings_fallback: fallbackView(["risk_budget", "net_worth"]) });
    expect(formFallbackSections(response)).toEqual(["risk_budget"]);
    expect(isFallbackSection(response, "net_worth")).toBe(true);
    expect(isFallbackSection(response, "alerts")).toBe(false);
    expect(sectionMarkerOf(response, "risk_budget")).toBe("SENTINEL-MARKER-RISK_BUDGET");
    expect(sectionMarkerOf(response, "alerts")).toBeNull();
  });

  it("前端的判斷來源不含任何由數值推導的寫法", () => {
    const source = stripComments(sourceOf("../../lib/settingsFallback.ts"));
    expect(source).not.toMatch(/freshness/);
    for (const file of ["../NetWorthSection.tsx", "../SettingsForm.tsx"]) {
      const text = stripComments(sourceOf(file));
      expect(text, file).not.toMatch(/freshness\s*===\s*["']fallback["']/);
    }
  });
});

/* --- PUT body (K-11) --------------------------------------------------------- */

describe("沒勾選的回落段不進 PUT body；勾選的段進 overwrite_fallback_sections（K-11）", () => {
  const sections = {
    risk_budget: settingsResponse().settings.risk_budget,
    cost_model: settingsResponse().settings.cost_model,
    alerts: settingsResponse().settings.alerts,
  };

  it("沒有回落段：三段全送，且不帶 overwrite_fallback_sections", () => {
    const { carried, overwrite } = carriedFormSections([], new Set());
    const patch = buildFormPatch(sections, carried, overwrite);
    expect(Object.keys(patch).sort()).toEqual(["alerts", "cost_model", "risk_budget"]);
    expect(patch).not.toHaveProperty("overwrite_fallback_sections");
  });

  it("回落段一個都沒勾：該段完全不在 body，也沒有 overwrite_fallback_sections", () => {
    const { carried, overwrite } = carriedFormSections(["risk_budget", "alerts"], new Set());
    const patch = buildFormPatch(sections, carried, overwrite);
    expect(Object.keys(patch)).toEqual(["cost_model"]);
    expect(patch).not.toHaveProperty("risk_budget");
    expect(patch).not.toHaveProperty("alerts");
    expect(patch).not.toHaveProperty("overwrite_fallback_sections");
  });

  it("只勾一段：只有那一段進 body，並列在 overwrite_fallback_sections；沒勾的仍不在 body", () => {
    const { carried, overwrite } = carriedFormSections(["risk_budget", "alerts"], new Set(["alerts"]));
    const patch = buildFormPatch(sections, carried, overwrite);
    expect(Object.keys(patch).sort()).toEqual(["alerts", "cost_model", "overwrite_fallback_sections"]);
    expect(patch.overwrite_fallback_sections).toEqual(["alerts"]);
    expect(patch).not.toHaveProperty("risk_budget");
  });

  it("勾選一個「不是回落段」的名字不會讓它被當成覆寫", () => {
    const { carried, overwrite } = carriedFormSections(["alerts"], new Set(["risk_budget"]));
    expect(overwrite).toEqual([]);
    expect(carried).toEqual(["risk_budget", "cost_model"]);
  });

  it("三段全回落且都沒勾：body 是空物件（不寫任何段），由後端回部分儲存句", () => {
    const { carried, overwrite } = carriedFormSections(["risk_budget", "cost_model", "alerts"], new Set());
    expect(buildFormPatch(sections, carried, overwrite)).toEqual({});
  });

  it("net_worth：未確認時 body 與過去完全相同；確認後才列 overwrite_fallback_sections", () => {
    expect(buildNetWorthPatch(1_000_000, false)).toEqual({ net_worth: { total_net_worth_twd: 1_000_000 } });
    const confirmed: AppSettingsPatch = buildNetWorthPatch(1_000_000, true);
    expect(confirmed).toEqual({
      net_worth: { total_net_worth_twd: 1_000_000 },
      overwrite_fallback_sections: ["net_worth"],
    });
  });
});

/* --- Order of the two confirmations (DL-6) ------------------------------------ */

describe("先出覆寫面板，再對已勾選的段跑放寬確認（DL-6）", () => {
  const RAISE: Record<string, CapWidening | null> = {
    max_position_weight: { before: 0.1, after: 0.15 },
    max_gross_exposure: null,
  };

  it("有回落段、面板還沒回答：先開覆寫面板，即使同時有放寬也不先跑放寬確認", () => {
    const step = resolveFormSaveStep({ fallback: ["risk_budget"], confirmed: null, widenings: RAISE, shown: {} });
    expect(step).toEqual({ action: "open_overwrite_panel" });
  });

  it("面板答完且勾了風險預算：才跑放寬確認，並且確認的是同一組數字", () => {
    const step = resolveFormSaveStep({
      fallback: ["risk_budget"],
      confirmed: new Set(["risk_budget"]),
      widenings: RAISE,
      shown: {},
    });
    expect(step).toEqual({ action: "confirm_widening", pending: { max_position_weight: { before: 0.1, after: 0.15 } } });
  });

  it("放寬確認答完之後才寫入，且 body 帶 overwrite", () => {
    const step = resolveFormSaveStep({
      fallback: ["risk_budget"],
      confirmed: new Set(["risk_budget"]),
      widenings: RAISE,
      shown: { max_position_weight: { before: 0.1, after: 0.15 } },
    });
    expect(step).toEqual({ action: "write", carried: ["risk_budget", "cost_model", "alerts"], overwrite: ["risk_budget"] });
  });

  it("風險預算回落但沒勾：它不會被寫入，所以不跑放寬確認，直接寫其餘段", () => {
    const step = resolveFormSaveStep({
      fallback: ["risk_budget"],
      confirmed: new Set(),
      widenings: RAISE,
      shown: {},
    });
    expect(step).toEqual({ action: "write", carried: ["cost_model", "alerts"], overwrite: [] });
  });

  it("只有別的段回落、風險預算正常：面板先出，答完後風險預算照舊跑放寬確認", () => {
    expect(
      resolveFormSaveStep({ fallback: ["alerts"], confirmed: null, widenings: RAISE, shown: {} }),
    ).toEqual({ action: "open_overwrite_panel" });
    expect(
      resolveFormSaveStep({ fallback: ["alerts"], confirmed: new Set(), widenings: RAISE, shown: {} }).action,
    ).toBe("confirm_widening");
  });

  it("沒有任何回落段：行為與本案之前完全相同（不開面板；放寬照舊確認）", () => {
    expect(resolveFormSaveStep({ fallback: [], confirmed: null, widenings: RAISE, shown: {} }).action).toBe(
      "confirm_widening",
    );
    expect(
      resolveFormSaveStep({ fallback: [], confirmed: null, widenings: { max_position_weight: null }, shown: {} }),
    ).toEqual({ action: "write", carried: ["risk_budget", "cost_model", "alerts"], overwrite: [] });
  });

  it("SettingsForm 的送出一律經過 resolveFormSaveStep，不在元件內另走一條寫入路徑", () => {
    const source = sourceOf("../SettingsForm.tsx");
    expect(source).toContain("resolveFormSaveStep(");
    expect(source).toContain("buildFormPatch(");
    expect((source.match(/mutation\.mutate\(/g) ?? []).length).toBe(1);
    expect(source).not.toMatch(/mutation\.mutate\(\s*\{/);
    expect(source).not.toContain("resolveWideningSubmitForFields(");
  });
});

/* --- SettingsForm render ------------------------------------------------------ */

describe("SettingsForm — 標記位置、面板預設關閉、409 與部分儲存", () => {
  const withoutFallback = settingsResponse();
  const withFallback = settingsResponse({ settings_fallback: fallbackView(["risk_budget", "alerts"]) });

  it("回落段的 h2 正下方是後端下發的標記；沒回落的段沒有", () => {
    const root = parseHtml(render(SettingsForm, { settings: withFallback }));
    const h2s = findAll(root, (el) => el.tag === "h2");
    const byTitle = (title: string) => {
      const found = h2s.find((el) => textOf(el).includes(title));
      if (found === undefined) throw new Error(`no h2 ${title}`);
      return found;
    };
    const risk = nextElementSibling(byTitle("風險預算"));
    expect(risk && textOf(risk)).toBe("SENTINEL-MARKER-RISK_BUDGET");
    const alerts = nextElementSibling(byTitle("警示排程"));
    expect(alerts && textOf(alerts)).toBe("SENTINEL-MARKER-ALERTS");
    // cost_model did not fall back: its h2 sits in a flex row, and no marker follows that row.
    const costRow = byTitle("費率").parent;
    const afterCost = costRow && nextElementSibling(costRow);
    expect(afterCost && textOf(afterCost)).not.toContain("SENTINEL");
  });

  it("回落時多出來的內容只有標記本身：前端沒有加任何自己的句子（K-6）", () => {
    const base = render(SettingsForm, { settings: withoutFallback });
    const html = render(SettingsForm, { settings: withFallback });
    const marker = (id: string) => `<p class="mt-2 text-sm text-amber-300">SENTINEL-MARKER-${id}</p>`;
    expect(html.replace(marker("RISK_BUDGET"), "").replace(marker("ALERTS"), "")).toBe(base);
  });

  it("面板在使用者按儲存之前不出現，主按鈕仍是「儲存設定」", () => {
    const html = render(SettingsForm, { settings: withFallback });
    expect(html).not.toContain("SENTINEL-PANEL-TITLE");
    expect(html).not.toContain("SENTINEL-CHECK-RISK");
    expect(textOf(parseHtml(html))).toContain("儲存設定");
  });

  it("409：照錄 detail 整句，不加前綴、不改字", () => {
    const html = renderWith(
      { ...IDLE_MUTATION, isError: true, error: new ApiError("SENTINEL-409-DETAIL", 409, {}, { detail: "x" }) },
      SettingsForm,
      { settings: withFallback },
    );
    const alerts = findAll(parseHtml(html), (el) => el.attrs.role === "alert");
    expect(alerts.map(textOf)).toEqual(["SENTINEL-409-DETAIL"]);
    expect(html).not.toContain("儲存失敗");
  });

  it("非 409 的錯誤仍走原本的「儲存失敗：」", () => {
    const html = renderWith(
      { ...IDLE_MUTATION, isError: true, error: new ApiError("SENTINEL-500", 500) },
      SettingsForm,
      { settings: withFallback },
    );
    expect(html).toContain("儲存失敗：");
    expect(html).toContain("SENTINEL-500");
  });

  // The two sentences the backend sends (`fallback_wording.py`: PARTIAL_SAVE_NOTICE
  // and NOTHING_SAVED_NOTICE, 風控 2026-10-29 N-156 K-15 裁示二-4 (b)), typed out
  // verbatim here: the box must carry them untouched, with no wording logic of its own.
  const AMBER_TOKENS = ["border-amber-800", "bg-amber-950/40", "text-sm", "text-amber-200"];
  const EMERALD_TOKENS = ["border-emerald-900", "bg-emerald-950/40", "text-emerald-300"];
  const classTokens = (el: { attrs: Record<string, string> }) => (el.attrs.class ?? "").split(/\s+/);

  it.each([
    ["原句（有帶其他段）", "設定已儲存。風險預算、警示排程沒有寫入，仍使用預設值。"],
    ["「全未寫入」新句（沒有帶任何段）", "沒有儲存任何變更：風險預算、費率、警示排程沒有寫入，仍使用預設值。"],
  ])("部分儲存成功，%s：逐字渲染後端句子，套琥珀框，取代「設定已儲存。」的綠框", (_label, sentence) => {
    const html = renderWith(
      { ...IDLE_MUTATION, isSuccess: true, data: { ...withFallback, partial_save_notice: sentence } },
      SettingsForm,
      { settings: withFallback },
    );
    const statuses = findAll(parseHtml(html), (el) => el.attrs.role === "status");
    expect(statuses.map(textOf)).toEqual([sentence]);
    const [box] = statuses;
    if (box === undefined) throw new Error("no status box");
    const tokens = classTokens(box);
    for (const token of AMBER_TOKENS) expect(tokens, token).toContain(token);
    for (const token of EMERALD_TOKENS) expect(tokens, token).not.toContain(token);
    // The "nothing stored" sentence must never sit beside a bare success line.
    if (sentence.startsWith("沒有儲存任何變更")) expect(html).not.toContain("設定已儲存。");
  });

  it("沒有被略過的段時維持「設定已儲存。」", () => {
    const html = renderWith(
      { ...IDLE_MUTATION, isSuccess: true, data: withoutFallback },
      SettingsForm,
      { settings: withoutFallback },
    );
    const statuses = findAll(parseHtml(html), (el) => el.attrs.role === "status");
    expect(statuses.map(textOf)).toEqual(["設定已儲存。"]);
    // partial_save_notice === null: the plain green success line, and no amber box.
    const [box] = statuses;
    if (box === undefined) throw new Error("no status box");
    const tokens = classTokens(box);
    for (const token of EMERALD_TOKENS) expect(tokens, token).toContain(token);
    expect(tokens).not.toContain("border-amber-800");
    expect(html).not.toContain("amber-950/40");
  });
});

/* --- NetWorthSection: the three places (風控 第 1 項 table) -------------------- */

describe("NetWorthSection — net_worth 回落時三處改動，判斷依 settings_fallback.sections", () => {
  const html = render(NetWorthSection, { settings: NET_WORTH_FALLBACK_RESPONSE });
  const root = parseHtml(html);
  const text = textOf(root);

  it("徽章顯示「使用預設值」", () => {
    expect(NET_WORTH_FALLBACK_BADGE_LABEL).toBe("使用預設值");
    const h2 = findOne(root, (el) => el.tag === "h2", "h2");
    const badge = h2.parent && findAll(h2.parent, (el) => el.tag === "span")[0];
    expect(badge && textOf(badge)).toBe("使用預設值");
  });

  it("「目前儲存的數值：」顯示「無法顯示」", () => {
    expect(NET_WORTH_FALLBACK_VALUE_LABEL).toBe("無法顯示");
    const term = findAll(root, (el) => el.tag === "dt").find((el) => textOf(el) === "目前儲存的數值：");
    const value = term && nextElementSibling(term);
    expect(value && textOf(value)).toBe("無法顯示");
  });

  it("沒有任何一處還寫「尚未輸入」，notes 只有後端給的（不含 NET_WORTH_ABSENT_NOTE）", () => {
    expect(text).not.toContain("尚未輸入");
    expect(text).toContain("SENTINEL-NW-NOTE");
    expect(text).not.toContain("維持 not_evaluable");
  });

  it("h2 正下方是後端下發的標記", () => {
    const h2 = findOne(root, (el) => el.tag === "h2", "h2");
    const row = h2.parent;
    const marker = row && nextElementSibling(row);
    expect(marker && textOf(marker)).toBe("SENTINEL-MARKER-NET_WORTH");
  });

  it("判斷依 sections，不看數值：sections 說回落，即使 net_worth 區塊帶著數字與 fresh，也照回落顯示", () => {
    const contradictory = settingsResponse({
      settings_fallback: fallbackView(["net_worth"]),
      net_worth: {
        total_net_worth_twd: 987_654_321,
        updated_at: "2026-10-01T00:00:00+00:00",
        age_days: 3,
        freshness: "fresh",
        notes: [],
        warnings: [],
      },
    });
    const out = textOf(parseHtml(render(NetWorthSection, { settings: contradictory })));
    expect(out).toContain("使用預設值");
    expect(out).toContain("無法顯示");
    expect(out).not.toContain("987,654,321");
    expect(out).not.toContain("已更新");
  });

  it("反過來：沒有 settings_fallback 時，沒輸入過就是「尚未輸入」，徽章不是「使用預設值」", () => {
    const out = textOf(parseHtml(render(NetWorthSection, { settings: settingsResponse() })));
    expect(out).toContain("尚未輸入");
    expect(out).not.toContain("使用預設值");
    expect(out).not.toContain("無法顯示");
  });

  it("只有其他段回落（net_worth 沒回落）時，net_worth 區塊不受影響", () => {
    const other = settingsResponse({ settings_fallback: fallbackView(["risk_budget"]) });
    const out = textOf(parseHtml(render(NetWorthSection, { settings: other })));
    expect(out).toContain("尚未輸入");
    expect(out).not.toContain("SENTINEL-MARKER");
  });

  it("面板在按下「更新帳戶總淨值」之前不出現", () => {
    expect(html).not.toContain("SENTINEL-NW-PANEL-TITLE");
    expect(html).not.toContain("SENTINEL-NW-CONFIRM");
  });

  it("409：照錄 detail 整句", () => {
    const out = renderWith(
      { ...IDLE_MUTATION, isError: true, error: new ApiError("SENTINEL-409-DETAIL", 409, {}, { detail: "x" }) },
      NetWorthSection,
      { settings: NET_WORTH_FALLBACK_RESPONSE },
    );
    const alerts = findAll(parseHtml(out), (el) => el.attrs.role === "alert");
    expect(alerts.map(textOf)).toEqual(["SENTINEL-409-DETAIL"]);
  });

  it("儲存後若仍有其他段在預設值，顯示後端的 partial_save_notice（原樣）", () => {
    const out = renderWith(
      { ...IDLE_MUTATION, isSuccess: true, data: { ...NET_WORTH_FALLBACK_RESPONSE, partial_save_notice: "SENTINEL-PARTIAL" } },
      NetWorthSection,
      { settings: NET_WORTH_FALLBACK_RESPONSE },
    );
    expect(textOf(parseHtml(out))).toContain("SENTINEL-PARTIAL");
  });
});

/* --- Ticks never outlive an overwrite attempt (DL-6, NB-1) --------------------- */

describe("取消或出錯之後，下一次開啟面板時勾選集合是空的（預設不勾選）", () => {
  const source = stripComments(sourceOf("../SettingsForm.tsx"));
  const closeBody = (() => {
    const start = source.indexOf("function closeOverwriteFlow()");
    const end = source.indexOf("\n  }", start);
    return source.slice(start, end);
  })();

  it("closeOverwriteFlow 同時關面板、清確認狀態、清空勾選", () => {
    expect(closeBody).toContain("setPanelOpen(false)");
    expect(closeBody).toContain("setConfirmedSections(null)");
    expect(closeBody).toContain("setOverwriteChecked(new Set())");
  });

  it("面板只經 closeOverwriteFlow 關閉：取消、放寬取消、解析錯誤、寫入成功、寫入失敗（含 409）全走它", () => {
    // `setPanelOpen(false)` appears twice: inside closeOverwriteFlow, and in
    // confirmOverwritePanel, which hides the panel while the answer it just
    // gave is still in use; that attempt then ends through onSuccess/onError.
    expect(source.match(/setPanelOpen\(false\)/g) ?? []).toHaveLength(2);
    const confirmStart = source.indexOf("function confirmOverwritePanel()");
    const confirmBody = source.slice(confirmStart, source.indexOf("\n  }", confirmStart));
    expect(confirmBody).toContain("setPanelOpen(false)");
    expect(source).toContain("onSuccess: closeOverwriteFlow");
    expect(source).toContain("onError: closeOverwriteFlow");
    // cancel in the panel, cancel in the widening alert, and the parse-error exit.
    expect((source.match(/closeOverwriteFlow\(\);/g) ?? []).length).toBeGreaterThanOrEqual(3);
  });

  it("勾選集合只有兩處會被設值：使用者勾選，與 closeOverwriteFlow 的清空", () => {
    const writes = source.match(/setOverwriteChecked\(/g) ?? [];
    expect(writes).toHaveLength(2);
    expect(source).toContain("useState<ReadonlySet<string>>(() => new Set())");
  });
});

/* --- net_worth badge: fallback wins over the payload (NB-3) --------------------- */

describe("NetWorthSection — 回落時徽章配色與後綴不受矛盾 payload 影響", () => {
  const contradictory = settingsResponse({
    settings_fallback: fallbackView(["net_worth"]),
    net_worth: {
      total_net_worth_twd: 5_000_000,
      updated_at: "2026-09-01T00:00:00+00:00",
      age_days: 58,
      freshness: "expired",
      notes: [],
      warnings: [],
    },
  });
  const root = parseHtml(render(NetWorthSection, { settings: contradictory }));
  const h2 = findOne(root, (el) => el.tag === "h2", "h2");
  const badge = h2.parent && findAll(h2.parent, (el) => el.tag === "span")[0];

  it("徽章只寫「使用預設值」，沒有「（已 N 天未更新）」", () => {
    expect(badge && textOf(badge)).toBe("使用預設值");
  });

  it("配色是回落的琥珀色，不是 expired 的玫瑰色（也不是 fresh 的綠色）", () => {
    expect(badge?.attrs.class).toContain("text-amber-300");
    expect(badge?.attrs.class).not.toMatch(/rose-|emerald-/);
  });
});

/* --- Query invalidation after a settings write (NB-5) --------------------------- */

describe("useUpdateSettings 成功後重新抓取依設定判定的畫面", () => {
  const queries = stripComments(sourceOf("../../lib/queries.ts"));
  const start = queries.indexOf("export function useUpdateSettings()");
  const body = queries.slice(start, queries.indexOf("\nexport function", start + 1));

  it("使 advice、kelly-disclosures 失效（覆寫之後不能繼續寫著「使用預設值」）", () => {
    expect(body).toContain('invalidateQueries({ queryKey: ["advice"] })');
    expect(body).toContain('invalidateQueries({ queryKey: ["kelly-disclosures"] })');
  });

  it("原有的 portfolio-limits、portfolio-summary 失效仍在", () => {
    expect(body).toContain('invalidateQueries({ queryKey: ["portfolio-limits"] })');
    expect(body).toContain('invalidateQueries({ queryKey: ["portfolio-summary"] })');
    expect(body).toContain('setQueryData(["settings"], data)');
  });
});

/* --- Source-level K-6 guard --------------------------------------------------- */

describe("前端不自撰回落字面（K-6）", () => {
  it("新元件的渲染原始碼沒有任何漢字（字面全來自後端）", () => {
    for (const file of [
      "../SettingsFallbackNotice.tsx",
      "../OverwritePanel.tsx",
      "../../components/SettingsFallbackNoticeLine.tsx",
    ]) {
      expect(chineseLiteralsOutsideComments(sourceOf(file)), file).toEqual([]);
    }
  });

  it("settingsFallback.ts 只持有風控第 1 項表格固定的兩個詞", () => {
    expect(chineseLiteralsOutsideComments(sourceOf("../../lib/settingsFallback.ts")).join("")).toBe(
      "使用預設值無法顯示",
    );
  });

  it("設定頁頁首區塊放在 NetWorthSection 之前，且 page.tsx 不把它包進 <details>", () => {
    const page = sourceOf("../page.tsx");
    const noticeAt = page.indexOf("<SettingsFallbackNotice");
    expect(noticeAt).toBeGreaterThan(-1);
    expect(noticeAt).toBeLessThan(page.indexOf("<NetWorthSection"));
    expect(page).not.toContain("<details");
  });
});

/**
 * 風控 2026-10-03 槓桿章節觀測值字面核可
 * (work/reviews/2026-10-03-槓桿章節-觀測值字面-風控核可.md) 前端落地條件：
 * 三個列標／標籤、附註字面、附註 class、附註位置（表格之後、警示之前）、常駐、
 * 不在 details／title，且 LeverageChapterView.tsx 不再含舊字面。
 *
 * 風控 2026-10-03 槓桿章節小節標題核可
 * (work/reviews/2026-10-03-槓桿章節-小節標題-風控核可.md) 落地條件 6a／6b：
 * 標題常數逐字釘住、元件以 {LEVERAGE_DRAG_SECTION_TITLE}</h3> 渲染、h3 class 不變、
 * 不含「已實現」與「報酬拆解（drag）」。
 */

import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";
import { LeverageChapterView } from "../../position/[symbol]/LeverageChapterView";
import {
  buildErosionIndexAsOf,
  buildLeverageDataAsOfLine,
  LEVERAGE_DRAG_GAP_ROW_LABEL,
  LEVERAGE_DRAG_OBSERVED_NOTE,
  LEVERAGE_DRAG_OBSERVED_ROW_LABEL,
  LEVERAGE_DRAG_RESET_EFFECT_LABEL,
  LEVERAGE_DRAG_SECTION_TITLE,
} from "../leverageWording";
import type { DragDecomposition, ErosionEstimate, LeverageChapter } from "../types";

const NOTE_LITERAL =
  "觀測值以未還原權值之原始收盤價計算，不含配息、不處理分割，跨除權息日或分割日可能失真；Naive 期望與理想每日重置路徑為理論值，用來與觀測值對照。";
const NOTE_ELEMENT = `<p class="mt-2 text-xs text-neutral-400">${NOTE_LITERAL}</p>`;

function makeDrag(overrides: Partial<DragDecomposition> = {}): DragDecomposition {
  return {
    status: "ok",
    leverage_factor: 2,
    expense_ratio_annual: 0.01,
    window: {
      start_date: "2026-01-02",
      end_date: "2026-09-30",
      aligned_bars: 120,
      trading_days: 120,
      calendar_days: 271,
      opened_at: "2026-01-02",
      days_since_opened_at: 271,
    },
    index_return: 0.1,
    actual_return: 0.15,
    naive_expected_return: 0.2,
    ideal_daily_reset_return: 0.18,
    gap: -0.05,
    fee_effect: -0.01,
    reset_effect: -0.02,
    residual: -0.02,
    identity_abs_error: 0,
    ideal_path_wiped_out: false,
    theoretical: {
      status: "ok",
      formula: "L(L-1)/2 x sigma^2 x T",
      annualized_volatility: 0.3,
      daily_volatility: 0.019,
      horizon_years: 0.5,
      observations: 120,
      theoretical_drag: -0.02,
      measured_reset_effect: -0.02,
      difference: 0.001,
      reason: null,
    },
    assumptions: ["a"],
    inputs_used: { columns: ["close"], window: {}, description: "fixture" },
    as_of: "2026-09-30T00:00:00+08:00",
    source: "test",
    last_bar_date: "2026-09-30",
    index_as_of: "2026-09-30T00:00:00+08:00",
    index_source: "test",
    index_last_bar_date: "2026-09-30",
    index_basis: "official_index",
    index_return_basis: "price",
    residual_alert: false,
    residual_alert_threshold: 0.05,
    notes: [],
    reason: null,
    ...overrides,
  };
}

function makeErosion(overrides: Partial<ErosionEstimate> = {}): ErosionEstimate {
  return {
    status: "ok",
    nature: "情境推估，非預測。",
    leverage_factor: 2,
    expense_ratio_annual: 0.01,
    window: 60,
    observations: 59,
    min_observations: 20,
    annualized_volatility: 0.25,
    daily_volatility: 0.0157,
    scenarios: [
      {
        label: "半年",
        horizon_trading_days: 120,
        horizon_years: 0.5,
        volatility_drag_pct: -0.02,
        expense_pct: -0.005,
        total_expected_erosion_pct: -0.025,
      },
    ],
    assumptions: ["a"],
    inputs_used: { columns: ["close"], window: {}, description: "fixture" },
    as_of: "2026-09-30T00:00:00+08:00",
    source: "test",
    index_last_bar_date: "2026-09-30",
    reason: null,
    ...overrides,
  };
}

function makeChapter(drag: DragDecomposition | null, erosion: ErosionEstimate | null = null): LeverageChapter {
  return {
    symbol: "00631L",
    position_id: 1,
    generated_at: "2026-10-03T00:00:00+08:00",
    disclosure: "",
    detection: {
      status: "ok",
      symbol: "00631L",
      normalized_symbol: "00631L.TW",
      instrument_type: "etf",
      is_daily_reset_leveraged: true,
      leverage_factor: 2,
      underlying_index: "TWII",
      expense_ratio_annual: 0.01,
      metadata_verified: true,
      metadata_verified_on: "2026-10-01",
      source_note: null,
      classification_mismatch: false,
      reason: null,
      notes: [],
    },
    holding: {
      status: "ok",
      opened_at: "2026-01-02",
      first_bar_date: "2026-01-02",
      last_bar_date: "2026-09-30",
      bars_since_opened_at: 120,
      holding_trading_days: 120,
      holding_days: 271,
      reason: null,
    },
    drag,
    erosion,
    notes: [],
    chapter_status: "ok",
    reason: null,
  };
}

function render(drag: DragDecomposition | null, erosion: ErosionEstimate | null = null): string {
  return renderToStaticMarkup(createElement(LeverageChapterView, { chapter: makeChapter(drag, erosion) }));
}

/** Text content as a reader sees it: React's text-node separators removed. */
function visibleText(html: string): string {
  return html.replace(/<!-- -->/g, "");
}

/** Same definition as componentWordingScan.test.ts `stripComments`: block comments (incl. JSX) and whole-line `//`. */
function stripComments(src: string): string {
  return src.replace(/\/\*[\s\S]*?\*\//g, "").replace(/^\s*\/\/.*$/gm, "");
}

function readSource(rel: string): string {
  return readFileSync(fileURLToPath(new URL(rel, import.meta.url)), "utf-8");
}

const SECTION_H3 = '<h3 class="text-sm font-semibold text-neutral-200">Gap 拆解：觀測值與 Naive 期望的差距</h3>';

describe("槓桿章節 drag 表：風控核可字面逐字釘住", () => {
  it("小節標題常數逐字等於核可字面（T1）", () => {
    expect(LEVERAGE_DRAG_SECTION_TITLE).toBe("Gap 拆解：觀測值與 Naive 期望的差距");
  });

  it("小節標題 wiring：元件以常數渲染 h3，不含舊字面「已實現」「報酬拆解（drag）」", () => {
    const src = readSource("../../position/[symbol]/LeverageChapterView.tsx");
    expect(src).toContain("{LEVERAGE_DRAG_SECTION_TITLE}</h3>");
    expect(src.match(/\{LEVERAGE_DRAG_SECTION_TITLE\}/g)).toHaveLength(1);
    expect(src).not.toContain("已實現");
    expect(src).not.toContain("報酬拆解（drag）");
    expect(src).not.toContain("Gap 拆解：觀測值與 Naive 期望的差距");
  });

  it("小節標題渲染：h3 class 不變、無 title、不在 <details> 內", () => {
    const html = render(makeDrag());
    expect(html).toContain(SECTION_H3);
    expect(html.split(LEVERAGE_DRAG_SECTION_TITLE)).toHaveLength(2); // exactly once
    expect(html).not.toContain("已實現");
    expect(html).not.toContain("報酬拆解（drag）");
    expect(html).not.toMatch(/title="[^"]*Gap 拆解/);
    const titleIdx = html.indexOf(LEVERAGE_DRAG_SECTION_TITLE);
    for (const m of html.matchAll(/<details[\s\S]*?<\/details>/g)) {
      const start = m.index ?? 0;
      expect(titleIdx >= start && titleIdx < start + m[0].length, "title inside <details>").toBe(false);
    }
    // the title is also shown when the drag table itself is not rendered
    expect(render(null)).toContain(SECTION_H3);
  });

  it("三個列標／標籤常數逐字等於核可字面", () => {
    expect(LEVERAGE_DRAG_OBSERVED_ROW_LABEL).toBe("ETF 收盤價觀測值（未還原）");
    expect(LEVERAGE_DRAG_GAP_ROW_LABEL).toBe("Gap（觀測值 − naive）");
    expect(LEVERAGE_DRAG_RESET_EFFECT_LABEL).toBe("重置（複利）效應");
  });

  it("附註常數逐字等於核可字面", () => {
    expect(LEVERAGE_DRAG_OBSERVED_NOTE).toBe(NOTE_LITERAL);
  });

  it("列標渲染為表格 th，且只出現在 th", () => {
    const html = render(makeDrag());
    expect(html).toContain("ETF 收盤價觀測值（未還原）</th>");
    expect(html).toContain("Gap（觀測值 − naive）</th>");
    expect(html).toContain("重置（複利）效應</th>");
  });

  it("附註為獨立 <p>，class 逐字為 mt-2 text-xs text-neutral-400（無寬度專屬 class）", () => {
    const html = render(makeDrag());
    expect(html).toContain(NOTE_ELEMENT);
    expect(html.split(NOTE_LITERAL)).toHaveLength(2); // exactly once
    const src = readSource("../../position/[symbol]/LeverageChapterView.tsx");
    expect(src).toContain('<p className="mt-2 text-xs text-neutral-400">{LEVERAGE_DRAG_OBSERVED_NOTE}</p>');
    expect(src.match(/\{LEVERAGE_DRAG_OBSERVED_NOTE\}/g)).toHaveLength(1);
  });

  it("附註位置：表格（overflow-x-auto div）之後、ideal_path_wiped_out 警示之前", () => {
    const wiped = render(makeDrag({ ideal_path_wiped_out: true }));
    const tableEnd = wiped.indexOf("</table></div>");
    const noteIdx = wiped.indexOf(NOTE_ELEMENT);
    const wipedIdx = wiped.indexOf("理想路徑在此期間已跌破 -100%")  // prefix only: the full sentence carries a struck literal guarded by backend/tests/test_kelly_wording.py;
    expect(tableEnd).toBeGreaterThan(-1);
    expect(noteIdx).toBeGreaterThan(tableEnd);
    expect(wipedIdx).toBeGreaterThan(noteIdx);
    // the note sits directly after the table wrapper, with nothing in between
    expect(wiped).toContain(`</table></div>${NOTE_ELEMENT}`);

    const src = readSource("../../position/[symbol]/LeverageChapterView.tsx");
    const srcTableEnd = src.indexOf("</table>\n            </div>");
    const srcNote = src.indexOf("{LEVERAGE_DRAG_OBSERVED_NOTE}");
    const srcWiped = src.indexOf("{chapter.drag.ideal_path_wiped_out && (");
    expect(srcTableEnd).toBeGreaterThan(-1);
    expect(srcNote).toBeGreaterThan(srcTableEnd);
    expect(srcWiped).toBeGreaterThan(srcNote);
  });

  it("常駐：警示有無都出現，且與 reset_effect／gap 為 null 與否無關", () => {
    for (const drag of [
      makeDrag({ ideal_path_wiped_out: false }),
      makeDrag({ ideal_path_wiped_out: true }),
      makeDrag({ gap: null, reset_effect: null, actual_return: null }),
      makeDrag({ theoretical: { ...makeDrag().theoretical, status: "insufficient_data", reason: "n/a" } }),
    ]) {
      expect(render(drag)).toContain(NOTE_ELEMENT);
    }
  });

  it("drag 表未渲染（drag 為 null 或非 ok）時不出現附註", () => {
    expect(render(null)).not.toContain(NOTE_LITERAL);
    expect(render(makeDrag({ status: "insufficient_data", reason: "r" }))).not.toContain(NOTE_LITERAL);
  });

  it("附註不在 <details>、不在 title 屬性內", () => {
    const html = render(makeDrag());
    const noteIdx = html.indexOf(NOTE_LITERAL);
    // every <details> block is closed before the note, or opens after it
    for (const m of html.matchAll(/<details[\s\S]*?<\/details>/g)) {
      const start = m.index ?? 0;
      const end = start + m[0].length;
      expect(noteIdx >= start && noteIdx < end, "note inside <details>").toBe(false);
    }
    expect(html).not.toMatch(/title="[^"]*觀測值以未還原權值/);
    const src = readSource("../../position/[symbol]/LeverageChapterView.tsx");
    expect(src).not.toMatch(/title=\{?[^>]*LEVERAGE_DRAG_OBSERVED_NOTE/);
  });

  it("LeverageChapterView.tsx 不再含舊字面「實際報酬」「實測」，也不再內嵌三個新字面", () => {
    const src = readSource("../../position/[symbol]/LeverageChapterView.tsx");
    expect(src).not.toContain("實際報酬");
    expect(src).not.toContain("實測");
    expect(src).not.toContain("ETF 收盤價觀測值（未還原）");
    expect(src).not.toContain("Gap（觀測值 − naive）");
    expect(src).not.toContain("觀測值以未還原權值");
  });

  it("理論近似句改用「重置（複利）效應」，渲染結果不含「實測」", () => {
    const html = render(makeDrag());
    expect(html).toContain("與重置（複利）效應差異");
    expect(html).not.toContain("實測");
    expect(html).not.toContain("實際報酬");
  });

  it("字面常數與其他字面常數放同一處（leverageWording.ts 與元件都在禁用詞掃描清單內）", () => {
    const scan = readSource("./componentWordingScan.test.ts");
    expect(scan).toContain('"../leverageWording.ts"');
    expect(scan).toContain('"../../position/[symbol]/LeverageChapterView.tsx"');
  });
});

/**
 * L-10g（風控 2026-10-04 核可，`work/reviews/2026-10-04-個股頁-資料時間標籤-風控審查.md`
 * 末段「L-10g 字面」W-1／W-2／W-4／W-5 與落地 required 1～4）。
 * W-1：`資料截至：ETF {D_e}｜指數 {D_i}｜計算截至 {D_w}`；W-2：`…個報酬｜指數資料截至 {D_i}`；
 * W-4：`建倉日 {opened_at} ～ 資料截至 {last_bar_date}，共 {n} 個交易日（{m} 曆日）。`；W-5：整個「產生時間」<p> 刪除。
 */
describe("L-10g W-1：buildLeverageDataAsOfLine 精確輸出", () => {
  const thisYear = new Date().getFullYear();
  const lastYear = thisYear - 1;
  type Case = readonly [string, string | null | undefined, string | null | undefined, string | null | undefined, string];
  const CASES: readonly Case[] = [
    ["1 三欄相同仍分列", `${thisYear}-10-02`, `${thisYear}-10-02`, `${thisYear}-10-02`, "資料截至：ETF 10-02｜指數 10-02｜計算截至 10-02"],
    ["2 指數延遲一日（計算截至＝指數日）", `${thisYear}-10-03`, `${thisYear}-10-02`, `${thisYear}-10-02`, "資料截至：ETF 10-03｜指數 10-02｜計算截至 10-02"],
    ["3 跨年混合", `${thisYear}-10-02`, `${lastYear}-12-31`, `${lastYear}-12-31`, `資料截至：ETF 10-02｜指數 ${lastYear}-12-31｜計算截至 ${lastYear}-12-31`],
    ["4 三欄皆非今年", `${lastYear}-10-02`, `${lastYear}-10-01`, `${lastYear}-10-01`, `資料截至：ETF ${lastYear}-10-02｜指數 ${lastYear}-10-01｜計算截至 ${lastYear}-10-01`],
    ["5a 單欄缺值（ETF）", null, `${thisYear}-10-02`, `${thisYear}-10-02`, "資料截至：ETF 日期不明｜指數 10-02｜計算截至 10-02"],
    ["5b 單欄缺值（指數）", `${thisYear}-10-02`, null, `${thisYear}-10-02`, "資料截至：ETF 10-02｜指數 日期不明｜計算截至 10-02"],
    ["5c 單欄缺值（計算截至）", `${thisYear}-10-02`, `${thisYear}-10-02`, null, "資料截至：ETF 10-02｜指數 10-02｜計算截至 日期不明"],
    ["6 全缺", null, null, null, "資料截至：ETF 日期不明｜指數 日期不明｜計算截至 日期不明"],
    ["7a undefined", undefined, `${thisYear}-10-02`, `${thisYear}-10-02`, "資料截至：ETF 日期不明｜指數 10-02｜計算截至 10-02"],
    ["7b 空字串", `${thisYear}-10-02`, "", `${thisYear}-10-02`, "資料截至：ETF 10-02｜指數 日期不明｜計算截至 10-02"],
    ["7c ISO 時間戳", `${thisYear}-10-02T07:54:00+08:00`, `${thisYear}-10-02`, `${thisYear}-10-02`, "資料截至：ETF 日期不明｜指數 10-02｜計算截至 10-02"],
    ["7d 斜線格式 2026/10/02", `${thisYear}-10-02`, `${thisYear}-10-02`, "2026/10/02", "資料截至：ETF 10-02｜指數 10-02｜計算截至 日期不明"],
  ];

  for (const [name, e, i, w, expected] of CASES) {
    it(`精確輸出：${name}`, () => {
      expect(buildLeverageDataAsOfLine(e, i, w)).toBe(expected);
    });
  }

  it("負向守門：所有案例以「資料截至：」開頭、「｜」恰 2、「ETF」「指數」「計算截至」各 1 次、不含禁字", () => {
    const forbidden = ["—", "同步", "最新", "即時", "取得", "資料時間", "回應產生時間", "皆", "一致", "相同", "不同"];
    for (const [name, e, i, w] of CASES) {
      const out = buildLeverageDataAsOfLine(e, i, w);
      expect(out.startsWith("資料截至："), name).toBe(true);
      expect(out.split("｜").length - 1, name).toBe(2);
      for (const label of ["ETF", "指數", "計算截至"]) {
        expect(out.split(label).length - 1, `${name} ${label}`).toBe(1);
      }
      expect(out.endsWith("。"), `${name} 無句號`).toBe(false);
      for (const f of forbidden) expect(out, `${name} 不得含「${f}」`).not.toContain(f);
    }
  });

  it("函式只收三參數；不收合（沒有相等分支）", () => {
    expect(buildLeverageDataAsOfLine.length).toBe(3);
    const src = readSource("../leverageWording.ts");
    const start = src.indexOf("export function buildLeverageDataAsOfLine(");
    const end = src.indexOf("export function buildErosionIndexAsOf(");
    expect(start).toBeGreaterThan(-1);
    expect(src.slice(start, end)).not.toMatch(/===|!==/);
  });
});

describe("L-10g W-2：buildErosionIndexAsOf 精確輸出", () => {
  const thisYear = new Date().getFullYear();
  const lastYear = thisYear - 1;

  it("今年 → MM-DD；非今年 → YYYY-MM-DD；缺值／格式不符 → 日期不明", () => {
    expect(buildErosionIndexAsOf(`${thisYear}-10-02`)).toBe("指數資料截至 10-02");
    expect(buildErosionIndexAsOf(`${lastYear}-12-31`)).toBe(`指數資料截至 ${lastYear}-12-31`);
    expect(buildErosionIndexAsOf(null)).toBe("指數資料截至 日期不明");
    expect(buildErosionIndexAsOf(undefined)).toBe("指數資料截至 日期不明");
    expect(buildErosionIndexAsOf("")).toBe("指數資料截至 日期不明");
    expect(buildErosionIndexAsOf(`${thisYear}-10-02T07:54:00+08:00`)).toBe("指數資料截至 日期不明");
    expect(buildErosionIndexAsOf("2026/10/02")).toBe("指數資料截至 日期不明");
  });

  it("負向守門：不含禁字、無句號、無「｜」", () => {
    const forbidden = ["—", "同步", "最新", "即時", "取得", "資料時間", "回應產生時間", "皆", "一致", "相同", "不同"];
    for (const input of [`${thisYear}-10-02`, `${lastYear}-12-31`, null, undefined, "", "2026/10/02"]) {
      const out = buildErosionIndexAsOf(input);
      expect(out.startsWith("指數資料截至 "), String(input)).toBe(true);
      expect(out.endsWith("。"), String(input)).toBe(false);
      expect(out).not.toContain("｜");
      for (const f of forbidden) expect(out, `${String(input)} 不得含「${f}」`).not.toContain(f);
    }
  });
});

describe("L-10g：LeverageChapterView 渲染（W-1／W-2／W-4／W-5）", () => {
  const thisYear = new Date().getFullYear();
  const lastYear = thisYear - 1;
  const W1_CLASS = '<p class="mt-2 text-xs text-neutral-400">';

  it("W-1：Gap 拆解 ok 分支渲染 ETF／指數／計算截至三欄，且接線順序正確（{D_w} 只接 window.end_date）", () => {
    const html = render(
      makeDrag({
        last_bar_date: `${thisYear}-10-03`,
        index_last_bar_date: `${thisYear}-10-02`,
        window: { ...makeDrag().window, end_date: `${thisYear}-10-01` },
        // row-level timestamps must not leak into the line
        as_of: `${thisYear}-10-05T09:00:00+08:00`,
        index_as_of: `${thisYear}-10-06T09:00:00+08:00`,
      }),
    );
    const line = `${W1_CLASS}資料截至：ETF 10-03｜指數 10-02｜計算截至 10-01</p>`;
    expect(visibleText(html)).toContain(line);
    expect(html).not.toContain("10-05");
    expect(html).not.toContain("10-06");
  });

  it("W-1：接線三欄缺值時各自顯示日期不明", () => {
    const html = visibleText(
      render(makeDrag({ last_bar_date: null, index_last_bar_date: null, window: { ...makeDrag().window, end_date: null } })),
    );
    expect(html).toContain("資料截至：ETF 日期不明｜指數 日期不明｜計算截至 日期不明</p>");
  });

  it("W-1：drag 非 ok（含 null）時不渲染該行", () => {
    expect(visibleText(render(null))).not.toContain("資料截至：ETF");
    expect(visibleText(render(makeDrag({ status: "insufficient_data", reason: "r" })))).not.toContain("資料截至：ETF");
  });

  it("W-2：波動估計行整句，接 erosion.index_last_bar_date，不接 as_of", () => {
    const html = visibleText(
      render(
        makeDrag(),
        makeErosion({ index_last_bar_date: `${lastYear}-12-31`, as_of: `${thisYear}-10-05T09:00:00+08:00` }),
      ),
    );
    expect(html).toContain(`${W1_CLASS}波動估計視窗：59／60 個報酬｜指數資料截至 ${lastYear}-12-31</p>`);
    expect(html).not.toContain("10-05");
    const thisYearHtml = visibleText(render(makeDrag(), makeErosion({ index_last_bar_date: `${thisYear}-10-02` })));
    expect(thisYearHtml).toContain("波動估計視窗：59／60 個報酬｜指數資料截至 10-02</p>");
    const missing = visibleText(render(makeDrag(), makeErosion({ index_last_bar_date: null })));
    expect(missing).toContain("波動估計視窗：59／60 個報酬｜指數資料截至 日期不明</p>");
  });

  it("W-4：持有期間整句（日期原樣 YYYY-MM-DD，不套 formatDataAsOfDate）", () => {
    const html = visibleText(render(makeDrag()));
    expect(html).toContain("建倉日 2026-01-02 ～ 資料截至 2026-09-30，共 120 個交易日（271 曆日）。");
    const old = visibleText(
      renderToStaticMarkup(
        createElement(LeverageChapterView, {
          chapter: {
            ...makeChapter(makeDrag()),
            holding: { ...makeChapter(null).holding, opened_at: `${lastYear}-03-04`, last_bar_date: `${thisYear}-10-02` },
          },
        }),
      ),
    );
    expect(old).toContain(`建倉日 ${lastYear}-03-04 ～ 資料截至 ${thisYear}-10-02，共 120 個交易日（271 曆日）。`);
  });

  it("W-5：整頁不出現「產生時間」「日線取得時間」「最新日線」「取得」，也不顯示 generated_at 的日期", () => {
    const html = visibleText(render(makeDrag(), makeErosion()));
    for (const banned of ["產生時間", "日線取得時間", "指數日線取得時間", "最新日線", "取得"]) {
      expect(html, banned).not.toContain(banned);
    }
    expect(html).not.toContain("2026-10-03T00:00:00");
    expect(html).not.toContain("10-03 00:00");
  });
});

describe("L-10g：LeverageChapterView.tsx 檔案層守門（去註解後）", () => {
  const code = stripComments(readSource("../../position/[symbol]/LeverageChapterView.tsx"));

  it("不得含「取得」「最新」「產生時間」、generated_at、formatDateTime", () => {
    for (const banned of ["取得", "最新", "產生時間", "generated_at", "formatDateTime"]) {
      expect(code, banned).not.toContain(banned);
    }
  });

  it("不得再讀列層 as_of／index_as_of", () => {
    expect(code).not.toMatch(/\bas_of\b/);
    expect(code).not.toMatch(/\bindex_as_of\b/);
  });

  it("三日期以建構函式組字，接線欄位逐字：last_bar_date／index_last_bar_date／window.end_date／erosion.index_last_bar_date", () => {
    expect(code).toContain("chapter.drag.last_bar_date,");
    expect(code).toContain("chapter.drag.index_last_bar_date,");
    expect(code).toContain("chapter.drag.window.end_date,");
    expect(code).toContain("buildErosionIndexAsOf(chapter.erosion.index_last_bar_date)");
    expect(code).toContain("資料截至 {chapter.holding.last_bar_date}");
  });

  it("不對三日期做 ===／!== 比較（相同日期不收合）", () => {
    const names = "(?:last_bar_date|index_last_bar_date|end_date)";
    expect(code).not.toMatch(new RegExp(`${names}\\s*[!=]==`));
    expect(code).not.toMatch(new RegExp(`[!=]==\\s*[\\w.?]*${names}`));
  });

  it("formatDateTime import 已移除；format.ts import 只剩實際使用者", () => {
    expect(code).not.toMatch(/import\s*\{[^}]*formatDateTime[^}]*\}/);
  });
});

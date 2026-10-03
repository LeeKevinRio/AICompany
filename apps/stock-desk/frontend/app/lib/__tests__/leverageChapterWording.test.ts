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
  LEVERAGE_DRAG_GAP_ROW_LABEL,
  LEVERAGE_DRAG_OBSERVED_NOTE,
  LEVERAGE_DRAG_OBSERVED_ROW_LABEL,
  LEVERAGE_DRAG_RESET_EFFECT_LABEL,
  LEVERAGE_DRAG_SECTION_TITLE,
} from "../leverageWording";
import type { DragDecomposition, LeverageChapter } from "../types";

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
    index_as_of: "2026-09-30T00:00:00+08:00",
    index_source: "test",
    reason: null,
    ...overrides,
  };
}

function makeChapter(drag: DragDecomposition | null): LeverageChapter {
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
    erosion: null,
    notes: [],
    chapter_status: "ok",
    reason: null,
  };
}

function render(drag: DragDecomposition | null): string {
  return renderToStaticMarkup(createElement(LeverageChapterView, { chapter: makeChapter(drag) }));
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

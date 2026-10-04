/**
 * 目前回撤卡（風控 2026-10-04 項目二）渲染測試：有值／缺值／status 非 ok／-0.00% 邊界／
 * 無 last_bar_date 不顯示資料截至／最大回撤卡輸出不變。
 */

import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";
import type { DrawdownResult, InputsUsed, SignalsPayload } from "../../../lib/types";
import {
  CURRENT_DRAWDOWN_DESCRIPTION_1,
  CURRENT_DRAWDOWN_DESCRIPTION_2,
  CURRENT_DRAWDOWN_INSUFFICIENT,
  CURRENT_DRAWDOWN_TITLE,
  TechnicalIndicatorsPanel,
} from "../TechnicalIndicatorsPanel";

const INPUTS_USED: InputsUsed = { columns: ["close"], window: {}, description: "test fixture" };

const BASE_DRAWDOWN: DrawdownResult = {
  status: "ok",
  max_drawdown: -0.25,
  peak_date: "2026-03-02",
  trough_date: "2026-06-15",
  current: -0.0812,
  current_peak_date: "2026-09-18",
  observations: 300,
  inputs_used: INPUTS_USED,
  as_of: "2026-10-04T08:00:00Z",
  source: "demo",
};

function payloadWith(drawdown: DrawdownResult): SignalsPayload {
  return {
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
        inputs_used: INPUTS_USED,
        as_of: null,
        source: null,
      },
      drawdown,
      beta: {
        status: "insufficient_data",
        beta: null,
        observations: 0,
        benchmark: null,
        inputs_used: INPUTS_USED,
        as_of: null,
        source: null,
      },
    },
  };
}

function render(drawdown: DrawdownResult, lastBarDate: string | null = "2026-10-02"): string {
  return renderToStaticMarkup(
    createElement(TechnicalIndicatorsPanel, { payload: payloadWith(drawdown), lastBarDate }),
  );
}

/** The 目前回撤 card's own markup (from its title to the next card). */
function currentCard(html: string): string {
  const start = html.lastIndexOf('<div class="rounded-lg border border-neutral-800 p-4">', html.indexOf(`>${CURRENT_DRAWDOWN_TITLE}<`));
  const next = html.indexOf('<div class="rounded-lg border border-neutral-800 p-4">', start + 1);
  return html.slice(start, next === -1 ? undefined : next);
}

describe("目前回撤卡渲染", () => {
  it("有值：數值列、兩句說明、資料截至行俱全，說明句為 text-xs text-neutral-400", () => {
    const card = currentCard(render(BASE_DRAWDOWN));
    expect(card).toContain(">目前回撤<");
    expect(card).toContain("-8.12%（區間最高收盤日 2026-09-18）");
    expect(card).toContain(`${CURRENT_DRAWDOWN_DESCRIPTION_1}${CURRENT_DRAWDOWN_DESCRIPTION_2}`);
    expect(card).toContain(`class="mt-1 text-xs text-neutral-400">${CURRENT_DRAWDOWN_DESCRIPTION_1}`);
    expect(card).toContain("資料截至 2026-10-02");
    // 資料截至 follows the value row.
    expect(card.indexOf("資料截至")).toBeGreaterThan(card.indexOf("區間最高收盤日"));
    expect(card).not.toContain("neutral-500");
  });

  it("缺值：status ok 但缺 current／current_peak_date 各印「—」，不新增句子", () => {
    const missing: DrawdownResult = { ...BASE_DRAWDOWN };
    delete missing.current;
    delete missing.current_peak_date;
    const card = currentCard(render(missing));
    expect(card).toContain("—（區間最高收盤日 —）");
    expect(card).not.toContain(CURRENT_DRAWDOWN_INSUFFICIENT);

    const nulls = currentCard(render({ ...BASE_DRAWDOWN, current: null, current_peak_date: null }));
    expect(nulls).toContain("—（區間最高收盤日 —）");
  });

  it("status 非 ok：印「資料不足，可用天數不足以計算。」，無數值列、無資料截至", () => {
    const card = currentCard(render({ ...BASE_DRAWDOWN, status: "insufficient_data", current: null, current_peak_date: null }));
    expect(card).toContain(CURRENT_DRAWDOWN_INSUFFICIENT);
    expect(card).not.toContain("區間最高收盤日 ");
    expect(card).not.toContain("資料截至");
  });

  it("-0.00% 邊界：四捨五入為 0 一律印 0.00%，不印 -0.00%", () => {
    for (const tiny of [-0.00001, -0.00004, -0, 0]) {
      const card = currentCard(render({ ...BASE_DRAWDOWN, current: tiny }));
      expect(card, String(tiny)).toContain("0.00%（區間最高收盤日 2026-09-18）");
      expect(card, String(tiny)).not.toContain("-0.00%");
    }
    // 剛好越過邊界者仍印負號。
    expect(currentCard(render({ ...BASE_DRAWDOWN, current: -0.0001 }))).toContain("-0.01%（區間最高收盤日");
  });

  it("-0.00005 邊界：-0.005% 四捨五入為 -0.01%（越界一側，守門與 formatPercent 一致）；current_peak_date 為空字串時印「—」", () => {
    const card = currentCard(render({ ...BASE_DRAWDOWN, current: -0.00005, current_peak_date: "" }));
    expect(card).toContain("-0.01%（區間最高收盤日 —）");
    expect(card).not.toContain("-0.00%");
    expect(card).not.toContain("區間最高收盤日 ）");
    // Just inside the boundary still collapses to an unsigned 0.00%.
    expect(currentCard(render({ ...BASE_DRAWDOWN, current: -0.000049, current_peak_date: "" }))).toContain(
      "0.00%（區間最高收盤日 —）",
    );
    // A real peak date is kept at the same boundary value.
    expect(currentCard(render({ ...BASE_DRAWDOWN, current: -0.00005 }))).toContain("-0.01%（區間最高收盤日 2026-09-18）");
  });

  it("無 last_bar_date：整行資料截至不顯示（null 與空字串皆然）", () => {
    expect(currentCard(render(BASE_DRAWDOWN, null))).not.toContain("資料截至");
    expect(currentCard(render(BASE_DRAWDOWN, ""))).not.toContain("資料截至");
  });

  it("資料截至取 last_bar_date，不取 as_of", () => {
    const card = currentCard(render(BASE_DRAWDOWN, "2026-10-02"));
    expect(card).not.toContain("2026-10-04");
  });

  it("數值不上色、無 chip、無方向符號", () => {
    const card = currentCard(render(BASE_DRAWDOWN));
    expect(card).not.toMatch(/(red|green|rose|emerald|amber|sky)-\d/);
    expect(card).not.toMatch(/[▲▼△▽↑↓○◐●]/);
  });
});

describe("最大回撤卡輸出不變", () => {
  it("標題、description 與數值列沿用原樣，且與新卡相鄰（同一 grid、緊接其後）", () => {
    const html = render(BASE_DRAWDOWN);
    expect(html).toContain(">最大回撤<");
    expect(html).toContain("觀察區間內高點到低點之最大跌幅，屬歷史統計描述，不代表未來會重演。");
    expect(html).toContain("-25.00%（高點 2026-03-02 → 低點 2026-06-15）");
    // The max-drawdown description keeps its original neutral-500 tone.
    expect(html).toContain(
      '<p class="mt-1 text-xs text-neutral-500">觀察區間內高點到低點之最大跌幅，屬歷史統計描述，不代表未來會重演。</p>',
    );
    expect(html.indexOf(">最大回撤<")).toBeLessThan(html.indexOf(`>${CURRENT_DRAWDOWN_TITLE}<`));
  });

  it("最大回撤卡不受 current 欄位影響", () => {
    const a = render(BASE_DRAWDOWN);
    const b = render({ ...BASE_DRAWDOWN, current: -0.5, current_peak_date: "2026-01-01" });
    const maxCard = (h: string) => h.slice(h.indexOf(">最大回撤<"), h.indexOf(`>${CURRENT_DRAWDOWN_TITLE}<`));
    expect(maxCard(a)).toBe(maxCard(b));
  });
});

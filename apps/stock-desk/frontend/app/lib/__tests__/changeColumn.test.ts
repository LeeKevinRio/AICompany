import { readdirSync, readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";
import { PositionsTableView } from "../../components/PositionsTable";
import {
  CHANGE_COLUMN_RESIDUAL_NOTE,
  CHANGE_HEADER_LABELS,
  FOREIGN_PNL_PERCENT_NOTE,
  allowIntradayFromMode,
  changeHeaderLabel,
  formatChangeBasisLabel,
  isChangeColumnRendered,
  nextSortState,
  resolveChangeCell,
  sortOptionId,
  sortOptions,
  sortPositions,
  sortStateFromOptionId,
} from "../positionsTableView";
import type { ChangeMode, PriceChange, PriceKind, SummaryPositionItem } from "../types";

/**
 * ADR-0016 (收盤版) frontend half, K-9..K-15 and T-7..T-11, plus the risk-approved
 * residual disclosure (`work/reviews/2026-10-03-漲跌欄-剩餘揭露-風控核可.md`
 * required (a)..(e)). Everything here pins wording byte-for-byte; changing any
 * literal needs a fresh risk review.
 */

const APP_DIR = fileURLToPath(new URL("../../", import.meta.url));

function readApp(rel: string): string {
  return readFileSync(fileURLToPath(new URL(`../../${rel}`, import.meta.url)), "utf-8");
}

/** Every non-test .ts/.tsx source under `app/` (relative paths). */
function nonTestSources(dir = APP_DIR, prefix = ""): string[] {
  const out: string[] = [];
  for (const entry of readdirSync(dir, { withFileTypes: true })) {
    if (entry.name === "__tests__" || entry.name === "node_modules" || entry.name === ".next") continue;
    if (entry.isDirectory()) out.push(...nonTestSources(`${dir}${entry.name}/`, `${prefix}${entry.name}/`));
    else if (/\.(ts|tsx)$/.test(entry.name) && !/\.test\.tsx?$/.test(entry.name)) out.push(`${prefix}${entry.name}`);
  }
  return out;
}

function change(overrides: Partial<PriceChange> = {}): PriceChange {
  return { pct: "2.5900", basis_kind: "close", basis_date: "2026-10-01", basis_price: "100.00", ...overrides };
}

function makePosition(
  id: number,
  symbol: string,
  o: {
    change?: PriceChange | null;
    priceKind?: PriceKind;
    price?: SummaryPositionItem["valuation"]["price"];
    currency?: "TWD" | "USD";
  } = {},
): SummaryPositionItem {
  const currency = o.currency ?? "TWD";
  const defaultPrice = {
    value: "110",
    as_of: "2026-10-02",
    source: "twse",
    price_kind: o.priceKind ?? "daily_close",
    data_status: "fresh" as const,
    is_within_ttl: null,
    reason: null,
  };
  return {
    id,
    symbol,
    market: currency === "USD" ? "US" : "TW",
    quantity: "1000",
    avg_cost: "100",
    currency,
    instrument_type: "stock",
    opened_at: "2026-03-12",
    sector: null,
    note: null,
    market_value_twd: "110000",
    cost_twd: "100000",
    change: o.change === undefined ? change() : o.change,
    valuation: {
      status: "ok",
      missing: [],
      price: o.price === undefined ? defaultPrice : o.price,
      fx: null,
      pnl_original: { value: "10000", currency },
      pnl_twd: "10000",
      asset_contribution_twd: "10000",
      fx_contribution_twd: "0",
    },
  };
}

function render(positions: SummaryPositionItem[], mode: ChangeMode = "close_only"): string {
  return renderToStaticMarkup(
    createElement(PositionsTableView, {
      positions,
      namesBySymbol: {},
      changeMode: mode,
      pendingDeleteId: null,
      onEdit: () => {},
      onDelete: () => {},
    }),
  );
}

/** Inner HTML of each change cell (everything after its mobile mini-label), one entry per row. */
function changeCells(html: string): string[] {
  return [...html.matchAll(/md:hidden">(?:收盤漲跌|漲跌)<\/p>(.*?)<\/div>/g)].map((m) => m[1] ?? "");
}

function text(htmlFragment: string): string {
  return htmlFragment.replace(/<[^>]+>/g, "");
}

const DASH_ONLY_CELL = '<p class="text-sm tabular-nums"><span class="text-neutral-400">—</span></p><p class="mt-0.5 text-xs" aria-hidden="true">\u00a0</p>';

describe("字面與常數（T-7）", () => {
  it("兩個表頭、剩餘揭露句逐字釘住", () => {
    expect(CHANGE_HEADER_LABELS.closeOnly).toBe("收盤漲跌");
    expect(CHANGE_HEADER_LABELS.mayIncludeIntraday).toBe("漲跌");
    expect(CHANGE_COLUMN_RESIDUAL_NOTE).toBe("漲跌未計入除權息與分割，可能與實際報酬不同。");
  });

  it("allowIntraday 只由 change_mode 決定；缺值或未知值一律視為 close_only", () => {
    expect(allowIntradayFromMode("may_include_intraday")).toBe(true);
    expect(allowIntradayFromMode("close_only")).toBe(false);
    expect(allowIntradayFromMode(undefined)).toBe(false);
    expect(allowIntradayFromMode("something_else" as unknown as ChangeMode)).toBe(false);
    expect(changeHeaderLabel(false)).toBe("收盤漲跌");
    expect(changeHeaderLabel(true)).toBe("漲跌");
  });

  it("表頭、手機小標、排序第 8／9 項三處指向同一常數（兩種模式）", () => {
    for (const mode of ["close_only", "may_include_intraday"] as const) {
      const label = mode === "close_only" ? CHANGE_HEADER_LABELS.closeOnly : CHANGE_HEADER_LABELS.mayIncludeIntraday;
      const html = render([makePosition(1, "AAA")], mode);
      expect(html, mode).toMatch(new RegExp(`<button[^>]*>${label}<span`));
      expect(html, mode).toContain(`<p class="text-xs text-neutral-400 md:hidden">${label}</p>`);
      const options = sortOptions(mode === "may_include_intraday");
      expect(options).toHaveLength(9);
      expect(options[7]?.label, mode).toBe(`${label} 高到低`);
      expect(options[8]?.label, mode).toBe(`${label} 低到高`);
      expect(html, mode).toContain(`>${label} 高到低</option>`);
      expect(html, mode).toContain(`>${label} 低到高</option>`);
    }
    // the header text is typed once; options and cells go through changeHeaderLabel
    const view = readApp("lib/positionsTableView.ts");
    expect(view.match(/收盤漲跌"/g)).toHaveLength(1);
    expect(view.match(/\bmayIncludeIntraday: "漲跌"/g)).toHaveLength(1);
    const table = readApp("components/PositionsTable.tsx");
    expect(table).not.toMatch(/["'`>]收盤漲跌/);
    expect(table.match(/changeHeaderLabel\(allowIntraday\)/g)).toHaveLength(2);
  });
});

describe("表頭只讀 change_mode（風控 2b，K-9）", () => {
  const fixtures: Record<string, SummaryPositionItem[]> = {
    allValues: [makePosition(1, "A"), makePosition(2, "B")],
    allNull: [makePosition(1, "A", { change: null }), makePosition(2, "B", { change: null })],
    intradayRows: [makePosition(1, "A", { priceKind: "intraday_quote", change: change({ basis_kind: "intraday" }) })],
    mixed: [
      makePosition(1, "A"),
      makePosition(2, "B", { change: null }),
      makePosition(3, "C", { priceKind: "intraday_quote", change: change({ basis_kind: "intraday" }) }),
    ],
  };

  it("close_only：不論資料內容，表頭恆為「收盤漲跌」，不會出現單獨的「漲跌」表頭", () => {
    for (const [name, rows] of Object.entries(fixtures)) {
      const html = render(rows, "close_only");
      expect(html, name).toMatch(/<button[^>]*>收盤漲跌<span/);
      expect(html, name).not.toMatch(/<button[^>]*>漲跌<span/);
      expect(html, name).not.toContain('md:hidden">漲跌</p>');
    }
  });

  it("may_include_intraday：不論資料內容，表頭恆為「漲跌」，不會出現「收盤漲跌」", () => {
    for (const [name, rows] of Object.entries(fixtures)) {
      const html = render(rows, "may_include_intraday");
      expect(html, name).toMatch(/<button[^>]*>漲跌<span/);
      expect(html, name).not.toContain("收盤漲跌");
    }
  });

  it("沒有 NEXT_PUBLIC、環境變數或時間常數參與開關（K-15）", () => {
    for (const rel of ["lib/positionsTableView.ts", "components/PositionsTable.tsx"]) {
      const src = readApp(rel);
      expect(src, rel).not.toContain("NEXT_PUBLIC");
      expect(src, rel).not.toContain("process.env");
      expect(src, rel).not.toMatch(/new Date\(|Date\.now|getHours|session_state|price_basis/);
    }
    // the only derivation of allowIntraday in the component
    const table = readApp("components/PositionsTable.tsx");
    expect(table.match(/allowIntradayFromMode\(/g)).toHaveLength(1);
    expect(readApp("page.tsx")).toContain("changeMode={summary.data.change_mode}");
    expect(readApp("lib/positionsTableView.ts")).toContain('mode === "may_include_intraday"');
  });

  it("舊 placeholder TODAY_CHANGE_SLOT 全專案已刪除（K-9）", () => {
    for (const rel of nonTestSources()) {
      expect(readApp(rel), rel).not.toContain("TODAY_CHANGE_SLOT");
    }
  });
});

describe("基準標籤字串格式（K-12，T-10）", () => {
  it("較 MM/DD 收盤：只做字串格式化，取 basis_date", () => {
    expect(formatChangeBasisLabel("2026-10-01")).toBe("較 10/01 收盤");
    expect(formatChangeBasisLabel("2026-12-31")).toBe("較 12/31 收盤");
  });

  it("空、null、非 YYYY-MM-DD 一律 null（不會印出「較 — 收盤」或空的 MM/DD）", () => {
    for (const bad of [null, "", " ", "garbled", "2026-1-1", "10/01", "2026-10-01T00:00:00Z", "—"]) {
      expect(formatChangeBasisLabel(bad), String(bad)).toBeNull();
    }
  });

  it("月份 01–12、日期 01–31 的純字串範圍檢查；超出即 null（不做日期運算，故 02-31 這類不判斷）", () => {
    for (const bad of ["2026-00-10", "2026-13-10", "2026-10-00", "2026-10-32", "2026-99-99", "2026-10-40"]) {
      expect(formatChangeBasisLabel(bad), bad).toBeNull();
      const html = render([makePosition(1, "A", { change: change({ basis_date: bad }) })]);
      expect(changeCells(html)[0], bad).toBe(DASH_ONLY_CELL);
    }
    for (const ok of ["2026-01-01", "2026-12-31", "2026-10-31"]) {
      expect(formatChangeBasisLabel(ok), ok).toBe(`較 ${ok.slice(5, 7)}/${ok.slice(8, 10)} 收盤`);
    }
  });

  it("不做日期運算：週一的基準日是週五時照字面顯示", () => {
    // 2026-10-05 is a Monday; the backend says the basis is Friday 10/02 and we print exactly that.
    const html = render([makePosition(1, "A", { change: change({ basis_date: "2026-10-02" }) })]);
    expect(text(changeCells(html)[0] ?? "")).toContain("較 10/02 收盤");
  });
});

describe("漲跌格顯示（K-11、K-13，T-9、T-10）", () => {
  it("非 null：百分比帶正負號與 %、紅漲綠跌、第 2 行為與 price_kind 一致的標籤", () => {
    const html = render([
      makePosition(1, "A", { change: change({ pct: "2.5900" }) }),
      makePosition(2, "B", { change: change({ pct: "-1.2346", basis_date: "2026-09-30" }) }),
      makePosition(3, "C", { change: change({ pct: "0.0000" }) }),
    ]);
    const [a, b, c] = changeCells(html);
    expect(a).toContain('<span class="text-rose-400">+2.59%</span>');
    expect(a).toContain(">較 10/01 收盤</p>");
    expect(b).toContain('<span class="text-emerald-400">-1.23%</span>');
    expect(b).toContain(">較 09/30 收盤</p>");
    expect(c).toContain('<span class="text-neutral-400">0.00%</span>');
    expect(c).toContain(">較 10/01 收盤</p>");
  });

  it("標籤 class 為 text-xs text-neutral-400，且不放 title", () => {
    const html = render([makePosition(1, "A")]);
    expect(changeCells(html)[0]).toContain('<p class="mt-0.5 text-xs tabular-nums text-neutral-400">較 10/01 收盤</p>');
    expect(changeCells(html)[0]).not.toContain("title=");
    // never inside the expandable block either
    const detail = html.slice(html.indexOf('id="pos-detail-1"'));
    expect(detail).not.toContain("較 10/01 收盤");
  });

  it("Decimal 安全進位：以字串半數遠離零進位，不經浮點", () => {
    const cases: Array<[string, string]> = [
      ["1.0050", "+1.01%"],
      ["-1.0050", "-1.01%"],
      ["1.0049", "+1.00%"],
      ["0.0049", "0.00%"],
      ["-0.0040", "0.00%"],
      ["-0.0050", "-0.01%"],
      ["99.9950", "+100.00%"],
      ["12", "+12.00%"],
      ["1234.5000", "+1,234.50%"],
    ];
    for (const [pct, shown] of cases) {
      const view = resolveChangeCell(makePosition(1, "A", { change: change({ pct }) }), false);
      expect(view.kind, pct).toBe("value");
      if (view.kind === "value") expect(view.text, pct).toBe(shown);
    }
  });

  it("超大或超長的 pct 一律 fail-closed 為「—」（不顯示 +∞%、不失精度）", () => {
    const tooBig = [
      "9".repeat(400),
      "-" + "9".repeat(400),
      "1" + "0".repeat(20) + ".00",
      "12345678", // 8 integer digits
      "99999999.9999",
    ];
    for (const pct of tooBig) {
      const position = makePosition(1, "A", { change: change({ pct }) });
      expect(resolveChangeCell(position, false), pct.slice(0, 12)).toEqual({ kind: "dash" });
      const html = render([position]);
      expect(changeCells(html)[0]).toBe(DASH_ONLY_CELL);
      expect(html).not.toMatch(/∞|Infinity|NaN/);
    }
    // the boundary: 7 integer digits is still accepted, leading zeros do not count
    const ok = resolveChangeCell(makePosition(1, "A", { change: change({ pct: "0000001234567.5000" }) }), false);
    expect(ok.kind).toBe("value");
    const edge = resolveChangeCell(makePosition(1, "A", { change: change({ pct: "9999999.0000" }) }), false);
    expect(edge.kind).toBe("value");
  });

  it("排序值＝畫面顯示的進位後數值（與顯示一致）", () => {
    const view = resolveChangeCell(makePosition(1, "A", { change: change({ pct: "1.0050" }) }), false);
    expect(view.kind).toBe("value");
    if (view.kind === "value") {
      expect(view.text).toBe("+1.01%");
      expect(view.sortValue).toBe(1.01);
    }
    // 1.0049 and 1.0001 both display +1.00%, so they tie and keep backend order
    const tie = [
      makePosition(1, "A", { change: change({ pct: "1.0049" }) }),
      makePosition(2, "B", { change: change({ pct: "1.0001" }) }),
    ];
    expect(sortPositions(tie, { key: "change", direction: "desc" }).map((p) => p.id)).toEqual([1, 2]);
    expect(sortPositions(tie, { key: "change", direction: "asc" }).map((p) => p.id)).toEqual([1, 2]);
  });

  it("顯示為 0.00% 時（含 -0.0040）顏色為中性，不是綠色", () => {
    const html = render([makePosition(1, "A", { change: change({ pct: "-0.0040" }) })]);
    expect(changeCells(html)[0]).toContain('<span class="text-neutral-400">0.00%</span>');
    expect(changeCells(html)[0]).not.toContain("emerald");
  });

  const invalidCases: Array<[string, SummaryPositionItem]> = [
    ["change 為 null", makePosition(1, "A", { change: null })],
    ["pct 空字串", makePosition(1, "A", { change: change({ pct: "" }) })],
    ["pct 非數字", makePosition(1, "A", { change: change({ pct: "abc" }) })],
    ["pct NaN", makePosition(1, "A", { change: change({ pct: "NaN" }) })],
    ["pct 科學記號", makePosition(1, "A", { change: change({ pct: "1e3" }) })],
    ["pct 帶空白", makePosition(1, "A", { change: change({ pct: " 2.5 " }) })],
    ["basis_date 空字串", makePosition(1, "A", { change: change({ basis_date: "" }) })],
    ["basis_date null", makePosition(1, "A", { change: change({ basis_date: null as unknown as string }) })],
    ["basis_date 格式錯誤", makePosition(1, "A", { change: change({ basis_date: "10/01" }) })],
    ["basis_kind 未知", makePosition(1, "A", { change: change({ basis_kind: "weird" as unknown as "close" }) })],
    ["basis_kind 缺漏", makePosition(1, "A", { change: change({ basis_kind: undefined as unknown as "close" }) })],
    ["basis close 對 price_kind intraday_quote", makePosition(1, "A", { priceKind: "intraday_quote" })],
    ["basis intraday 對 price_kind daily_close", makePosition(1, "A", { change: change({ basis_kind: "intraday" }) })],
    ["有 change 但該列沒有現價", makePosition(1, "A", { price: null })],
  ];

  it("K-11：任一條件成立，整格只剩「—」與不可見佔位，沒有任何基準字樣", () => {
    for (const [name, position] of invalidCases) {
      const html = render([position]);
      const cell = changeCells(html)[0] ?? "";
      expect(cell, name).toBe(DASH_ONLY_CELL);
      for (const word of ["較", "收盤", "昨收", "盤中", "%"]) {
        expect(text(cell), `${name}：不得出現「${word}」`).not.toContain(word);
      }
    }
  });

  it("T-10：不論輸入，任何漲跌格都不會出現「較 — 收盤」、空的 MM/DD 或沒帶 % 的數字", () => {
    const rows = [...invalidCases.map(([, p]) => p), makePosition(2, "B"), makePosition(3, "C", { change: change({ pct: "-3.0000" }) })];
    for (const cell of changeCells(render(rows))) {
      const t = text(cell);
      expect(t).not.toMatch(/較\s*—\s*收盤/);
      expect(t).not.toMatch(/較\s+收盤/);
      expect(t).not.toMatch(/較\s*\/|較\s*undefined|較\s*null|NaN|undefined|null/);
      if (/\d/.test(t.replace(/較 \d{2}\/\d{2} 收盤/, ""))) {
        // any digit left outside the basis label must be a signed percent (or 0.00%)
        expect(t.replace(/較 \d{2}\/\d{2} 收盤/, "")).toMatch(/^(?:[+-]\d[\d,]*\.\d{2}%|0\.00%)$/);
      }
    }
  });

  it("T-9 雙向：每個非 null 格都有標籤，每個 dash 格都沒有標籤", () => {
    const rows = [makePosition(1, "A"), makePosition(2, "B", { change: null }), makePosition(3, "C", { change: change({ pct: "" }) })];
    const cells = changeCells(render(rows));
    expect(cells).toHaveLength(3);
    expect(text(cells[0] ?? "")).toMatch(/^\+2\.59%較 10\/01 收盤$/);
    expect(cells[1]).toBe(DASH_ONLY_CELL);
    expect(cells[2]).toBe(DASH_ONLY_CELL);
  });

  it("前端不自算：fixture 的 basis_price／現價與 pct 不一致時，仍顯示後端給的 pct", () => {
    // 110 / 100 would be +10%, but the backend said 2.59 and the UI must not "fix" it (K-5)
    const html = render([makePosition(1, "A", { change: change({ pct: "2.5900", basis_price: "100.00" }) })]);
    expect(text(changeCells(html)[0] ?? "")).toContain("+2.59%");
    expect(text(changeCells(html)[0] ?? "")).not.toContain("+10.00%");
  });
});

describe("close_only 下的盤中列（K-10、K-14，T-8）", () => {
  const intradayRow = makePosition(1, "AAA", {
    priceKind: "intraday_quote",
    change: change({ basis_kind: "intraday", pct: "4.4400" }),
  });

  it("價格格與漲跌格都只顯示「—」，沒有任何盤中或收盤標籤，也沒有該列的數字", () => {
    const html = render([intradayRow], "close_only");
    expect(changeCells(html)[0]).toBe(DASH_ONLY_CELL);
    expect(html).not.toContain("盤中");
    expect(html).not.toContain("昨收");
    expect(html).not.toContain("4.44");
    expect(html).not.toContain("110.00");
    // the price cell carries no date label ("10/02 收盤") for an intraday row
    expect(html).not.toContain("10/02 收盤");
    expect(html).not.toContain("較 ");
  });

  it("價格格：price_kind 不是 daily_close（未知或缺漏）也只顯示「—」，沒有收盤日期標籤", () => {
    for (const bad of ["weird", undefined]) {
      const position = makePosition(1, "AAA");
      const price = position.valuation.price;
      if (price === null) throw new Error("fixture must carry a price");
      const row: SummaryPositionItem = {
        ...position,
        valuation: { ...position.valuation, price: { ...price, price_kind: bad as unknown as PriceKind } },
      };
      const html = render([row]);
      expect(html, String(bad)).not.toContain("110.00");
      expect(html, String(bad)).not.toContain("10/02 收盤");
      expect(changeCells(html)[0], String(bad)).toBe(DASH_ONLY_CELL);
    }
    // a daily_close row still shows its price and date label
    const ok = render([makePosition(1, "AAA")]);
    expect(ok).toContain("110.00");
    expect(ok).toContain("10/02 收盤");
    // a missing price keeps its own insufficient-data rendering (not touched by the kind rule)
    expect(render([makePosition(1, "AAA", { price: null })])).toContain("資料不足");
  });

  it("契約違反變體（intraday_quote 搭 close 基準）也一樣只剩「—」", () => {
    const html = render([makePosition(1, "AAA", { priceKind: "intraday_quote", change: change({ pct: "4.4400" }) })]);
    expect(changeCells(html)[0]).toBe(DASH_ONLY_CELL);
    expect(html).not.toContain("4.44");
    expect(html).not.toContain("110.00");
  });

  it("T-8：任何 fixture 組合下，「收盤漲跌」表頭下沒有任何一列把 intraday_quote 渲染成數字或標籤", () => {
    const kinds: PriceKind[] = ["daily_close", "intraday_quote"];
    const bases: Array<PriceChange | null> = [
      null,
      change({ basis_kind: "close", pct: "7.7700" }),
      change({ basis_kind: "intraday", pct: "7.7700" }),
    ];
    for (const kind of kinds) {
      for (const basis of bases) {
        const html = render([makePosition(1, "AAA", { priceKind: kind, change: basis })], "close_only");
        expect(html).toMatch(/<button[^>]*>收盤漲跌<span/);
        if (kind === "intraday_quote") {
          expect(html).not.toContain("7.77");
          expect(html).not.toContain("盤中");
          expect(changeCells(html)[0]).toBe(DASH_ONLY_CELL);
          expect(html).not.toContain("110.00");
        }
      }
    }
  });

  it("K-14：may_include_intraday 下 basis_kind intraday 也仍是「—」，「盤中價較昨收」不在任何非測試檔", () => {
    const html = render([intradayRow], "may_include_intraday");
    expect(changeCells(html)[0]).toBe(DASH_ONLY_CELL);
    expect(html).not.toContain("昨收");
    for (const rel of nonTestSources()) {
      expect(readApp(rel), rel).not.toContain("盤中價較昨收");
    }
  });

  it("盤中守門仍成立：「盤中」只允許出現在 intradayWording.ts（持倉表相關檔無此詞）", () => {
    for (const rel of ["lib/positionsTableView.ts", "components/PositionsTable.tsx", "page.tsx"]) {
      expect(readApp(rel), rel).not.toContain("盤中");
    }
  });
});

describe("剩餘揭露句（風控 required (a)～(e)）", () => {
  const noteParagraph = `<p class="mb-2 text-xs text-neutral-400">${CHANGE_COLUMN_RESIDUAL_NOTE}</p>`;
  const foreignParagraph = `<p class="mb-2 text-xs text-neutral-400">${FOREIGN_PNL_PERCENT_NOTE}</p>`;
  const modes: ChangeMode[] = ["close_only", "may_include_intraday"];
  const occurrences = (html: string) => html.split(CHANGE_COLUMN_RESIDUAL_NOTE).length - 1;

  it("字面逐字相同（22 字含標點）", () => {
    expect(CHANGE_COLUMN_RESIDUAL_NOTE).toBe("漲跌未計入除權息與分割，可能與實際報酬不同。");
    expect(CHANGE_COLUMN_RESIDUAL_NOTE).toHaveLength(22);
  });

  it("兩種表頭模式下字面相同、都顯示、全頁只出現一次", () => {
    for (const mode of modes) {
      const html = render([makePosition(1, "A"), makePosition(2, "B")], mode);
      expect(html, mode).toContain(noteParagraph);
      expect(occurrences(html), mode).toBe(1);
    }
  });

  it("與漲跌欄同生滅：0 列持倉時表頭與句子都不出現", () => {
    expect(isChangeColumnRendered([])).toBe(false);
    expect(isChangeColumnRendered([makePosition(1, "A")])).toBe(true);
    for (const mode of modes) {
      const html = render([], mode);
      expect(html, mode).not.toContain(CHANGE_COLUMN_RESIDUAL_NOTE);
      expect(html, mode).not.toContain("漲跌");
    }
  });

  it("與漲跌欄同生滅：全部列皆為「—」時仍出現（兩種模式）", () => {
    const rows = [
      makePosition(1, "A", { change: null }),
      makePosition(2, "B", { change: change({ pct: "" }) }),
      makePosition(3, "C", { priceKind: "intraday_quote", change: change({ basis_kind: "intraday" }) }),
    ];
    for (const mode of modes) {
      const html = render(rows, mode);
      expect(changeCells(html).every((c) => c === DASH_ONLY_CELL), mode).toBe(true);
      expect(html, mode).toContain(noteParagraph);
      expect(occurrences(html), mode).toBe(1);
    }
  });

  it("全部列都有數字時也出現，且與 change 內容無關（觸發只有一個）", () => {
    const withValues = render([makePosition(1, "A"), makePosition(2, "B")]);
    const allDash = render([makePosition(1, "A", { change: null }), makePosition(2, "B", { change: null })]);
    expect(withValues).toContain(noteParagraph);
    expect(allDash).toContain(noteParagraph);
  });

  it("不在 title 內、不在 details（展開區）內、不 truncate／line-clamp／斜體／更淡", () => {
    const html = render([makePosition(1, "A"), makePosition(2, "B")]);
    expect(html).not.toMatch(/title="[^"]*漲跌未計入/);
    expect(html).not.toContain("<details");
    expect(html).not.toMatch(/aria-label="[^"]*漲跌未計入/);
    const at = html.indexOf(CHANGE_COLUMN_RESIDUAL_NOTE);
    expect(at).toBeGreaterThan(-1);
    expect(at).toBeLessThan(html.indexOf('role="table"'));
    // before the first expandable block (and so inside none of them)
    expect(at).toBeLessThan(html.indexOf('id="pos-detail-1"'));
    // exactly the caption class as the foreign-currency sentence: no weaker styling, no width-only variant
    expect(noteParagraph).toBe(foreignParagraph.replace(FOREIGN_PNL_PERCENT_NOTE, CHANGE_COLUMN_RESIDUAL_NOTE));
    for (const weaker of ["truncate", "line-clamp", "italic", "neutral-500", "neutral-600", "hidden", "md:", "sm:"]) {
      expect(noteParagraph, weaker).not.toContain(weaker);
    }
    // not inside any element carrying a hidden attribute
    expect(html.slice(html.lastIndexOf("<", at - 1), at)).not.toContain("hidden");
  });

  it("有外幣口徑句時：緊接其下、兩句分開成兩個 <p>，且都在排序列與表格之前", () => {
    for (const mode of modes) {
      const html = render([makePosition(1, "2330"), makePosition(2, "AAPL", { currency: "USD" })], mode);
      expect(html, mode).toContain(foreignParagraph + noteParagraph);
      expect(html, mode).not.toContain(`${FOREIGN_PNL_PERCENT_NOTE}${CHANGE_COLUMN_RESIDUAL_NOTE}`);
      expect(html.indexOf(noteParagraph), mode).toBeLessThan(html.indexOf('for="positions-sort-select"'));
    }
  });

  it("無外幣口徑句時：揭露句是第一個段落，排序列與表格在其後", () => {
    const html = render([makePosition(1, "2330")]);
    expect(html).not.toContain(FOREIGN_PNL_PERCENT_NOTE);
    expect(html.startsWith(`<div>${noteParagraph}<div class="mb-2 flex`)).toBe(true);
  });

  it("桌機與手機同位置：同一個 DOM 位置，沒有任何寬度專屬的 class", () => {
    const src = readApp("components/PositionsTable.tsx");
    expect(src.match(/\{CHANGE_COLUMN_RESIDUAL_NOTE\}/g)).toHaveLength(1);
    expect(src).toContain('<p className="mb-2 text-xs text-neutral-400">{CHANGE_COLUMN_RESIDUAL_NOTE}</p>');
  });

  it("範圍限制：常數只在持倉表檔案使用；句子與「實際報酬」不在損益％或任何其他畫面", () => {
    const using = nonTestSources().filter((rel) => readApp(rel).includes("CHANGE_COLUMN_RESIDUAL_NOTE"));
    expect(using.sort()).toEqual(["components/PositionsTable.tsx", "lib/positionsTableView.ts"]);
    const literal = nonTestSources().filter((rel) => readApp(rel).includes("漲跌未計入除權息與分割"));
    expect(literal).toEqual(["lib/positionsTableView.ts"]);
    // 損益％ column and every other surface never borrow the phrase (risk required 2). Allowlist:
    // the note's own constant, plus the leverage chapter's legacy row label, which has a task
    // ticket to be reworded; remove that entry once it is.
    const actualReturnAllowlist = ["lib/positionsTableView.ts", "position/[symbol]/LeverageChapterView.tsx"];
    const withPhrase = nonTestSources().filter((rel) => readApp(rel).includes("實際報酬"));
    expect(withPhrase.sort()).toEqual([...actualReturnAllowlist].sort());
    // the 損益％ label stays free of 漲跌／漲幅
    const html = render([makePosition(1, "A")]);
    expect(html).not.toMatch(/台幣損益％[^<]*漲/);
  });

  it("字面常數與其他字面常數放同一處（positionsTableView.ts 在禁用詞掃描清單內）", () => {
    const scan = readFileSync(fileURLToPath(new URL("./componentWordingScan.test.ts", import.meta.url)), "utf-8");
    expect(scan).toContain('"../positionsTableView.ts"');
    expect(scan).toContain('"../../components/PositionsTable.tsx"');
  });
});

describe("排序：漲跌欄（T-11）", () => {
  const rows = [
    makePosition(1, "A", { change: change({ pct: "-1.5000" }) }),
    makePosition(2, "B", { change: null }),
    makePosition(3, "C", { change: change({ pct: "3.2500", basis_date: "2026-09-30" }) }),
    makePosition(4, "D", { change: change({ pct: "0.0000" }) }),
    makePosition(5, "E", { change: change({ pct: "oops" }) }),
    makePosition(6, "F", { priceKind: "intraday_quote", change: change({ basis_kind: "intraday", pct: "9.9900" }) }),
  ];
  const ids = (list: SummaryPositionItem[]) => list.map((p) => p.id);

  it("高到低：數字依大小，「—」（null、無法解析、盤中列）永遠排最後並保持後端順序", () => {
    expect(ids(sortPositions(rows, { key: "change", direction: "desc" }))).toEqual([3, 4, 1, 2, 5, 6]);
  });

  it("低到高：「—」同樣永遠排最後（升降皆然）", () => {
    expect(ids(sortPositions(rows, { key: "change", direction: "asc" }))).toEqual([1, 4, 3, 2, 5, 6]);
  });

  it("混合基準日（有的 09/30、有的 10/01）照常可排", () => {
    const mixed = [
      makePosition(1, "A", { change: change({ pct: "1.0000", basis_date: "2026-10-01" }) }),
      makePosition(2, "B", { change: change({ pct: "2.0000", basis_date: "2026-09-30" }) }),
    ];
    expect(ids(sortPositions(mixed, { key: "change", direction: "desc" }))).toEqual([2, 1]);
    expect(ids(sortPositions(mixed, { key: "change", direction: "asc" }))).toEqual([1, 2]);
  });

  it("排序依顯示規則：被 fail-closed 成「—」的列不用 pct 參與排序", () => {
    // row 6 has pct 9.99 (the largest) but is shown as "—", so it must not lead a descending sort
    expect(ids(sortPositions(rows, { key: "change", direction: "desc" }))[0]).toBe(3);
  });

  it("null 狀態維持後端順序，且不改動傳入陣列", () => {
    const before = ids(rows);
    expect(ids(sortPositions(rows, null))).toEqual(before);
    sortPositions(rows, { key: "change", direction: "desc" });
    expect(ids(rows)).toEqual(before);
  });

  it("下拉第 8、9 項與桌機表頭共用同一個狀態：id 往返、表頭循環 desc → asc → 預設", () => {
    for (const allow of [false, true]) {
      for (const option of sortOptions(allow)) {
        expect(sortStateFromOptionId(sortOptionId(option.state))).toEqual(option.state);
      }
    }
    expect(sortOptionId({ key: "change", direction: "desc" })).toBe("change:desc");
    expect(sortStateFromOptionId("change:asc")).toEqual({ key: "change", direction: "asc" });
    let state = nextSortState(null, "change");
    expect(state).toEqual({ key: "change", direction: "desc" });
    state = nextSortState(state, "change");
    expect(state).toEqual({ key: "change", direction: "asc" });
    expect(nextSortState(state, "change")).toBeNull();
  });
});

describe("版面", () => {
  it("桌機欄序：展開鈕 | 代號 | 現價 | 損益％ | 台幣損益 | 漲跌；漲跌在最後一欄，且仍無橫向捲動", () => {
    const src = readApp("components/PositionsTable.tsx");
    expect(src).toContain("md:grid-cols-[2.75rem_minmax(0,1.4fr)_minmax(0,1.3fr)_6rem_minmax(8rem,1fr)_minmax(7.5rem,1fr)]");
    expect(src).toContain("md:col-start-6");
    expect(src).not.toContain("overflow-x-auto");
    const full = render([makePosition(1, "A")]);
    // the desktop header rowgroup only (the mobile dropdown also lists these names)
    const html = full.slice(full.indexOf('role="rowgroup" class="hidden'), full.indexOf('id="pos-detail-1"'));
    const order = ["代號", "現價", "台幣損益％", "台幣損益<", "收盤漲跌"].map((label) => html.indexOf(`>${label}`));
    expect(order.every((i) => i > -1)).toBe(true);
    expect(order).toEqual([...order].sort((a, b) => a - b));
  });

  it("手機卡片：漲跌在右欄第三組（損益％、台幣損益之後），小標沿用表頭常數", () => {
    const html = render([makePosition(1, "A")]);
    const pct = html.indexOf('md:hidden">台幣損益％');
    const twd = html.indexOf('md:hidden">台幣損益<');
    const chg = html.indexOf('md:hidden">收盤漲跌');
    expect(pct).toBeGreaterThan(-1);
    expect(twd).toBeGreaterThan(pct);
    expect(chg).toBeGreaterThan(twd);
  });

  it("漲跌欄只用既有紅漲綠跌工具（K-13）：沿用 formatSignedPercent 與 pnlColorClass", () => {
    const table = readApp("components/PositionsTable.tsx");
    expect(table).toContain("pnlColorClass(view.colorValue)");
    const view = readApp("lib/positionsTableView.ts");
    expect(view).toContain("formatSignedPercent(numeric)");
  });
});

import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";
import { PositionsTableView } from "../../components/PositionsTable";
import { LimitsCheckList } from "../../position/[symbol]/LimitsCheckList";
import {
  DETAIL_FIELD_LABELS,
  FOREIGN_PNL_PERCENT_NOTE,
  PRIMARY_HEADER_LABELS,
  SORT_CONTROL_LABEL,
  formatSignedPercent,
  hasForeignCurrencyPosition,
  isNavItemActive,
  nextPnlSortDirection,
  nextSortState,
  pnlPercentTwd,
  sortByPnlTwd,
  sortOptionId,
  sortOptions,
  sortPositions,
  sortStateFromOptionId,
} from "../positionsTableView";
import { INVENTORY_NAV_LABEL, INVENTORY_PAGE_TITLE, INVENTORY_ROUTE } from "../inventoryWording";
import { riskGaugeBarFillClass, riskGaugeChipClass } from "../riskGauge";
import type { LimitCheck, LimitStatus, PriceChange, SummaryPositionItem } from "../types";

// Phase-2 sort options for the current (close-only) deployment.
const SORT_OPTIONS = sortOptions(false);

/**
 * 首頁重排第一階段（CEO 2026-10-03；`work/stock-desk-首頁重排-視覺規範-
 * 2026-10-03.md`）：區塊順序、持倉表瘦身（預設欄位／展開區／無 min-w）、
 * 預設維持後端順序＋台幣損益表頭排序、損益％（台幣口徑）、風險儀表非紅綠、
 * NavBar 目前頁。
 */

function readSource(rel: string): string {
  return readFileSync(fileURLToPath(new URL(rel, import.meta.url)), "utf-8");
}

function makePosition(
  id: number,
  symbol: string,
  overrides: {
    pnl_twd?: string | null;
    cost_twd?: string | null;
    currency?: "TWD" | "USD";
    fx?: SummaryPositionItem["valuation"]["fx"];
    price?: SummaryPositionItem["valuation"]["price"];
    change?: PriceChange | null;
  } = {},
): SummaryPositionItem {
  const currency = overrides.currency ?? "TWD";
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
    cost_twd: overrides.cost_twd === undefined ? "100000" : overrides.cost_twd,
    change: overrides.change === undefined ? null : overrides.change,
    valuation: {
      status: "ok",
      missing: [],
      price:
        overrides.price === undefined
          ? { value: "110", as_of: "2026-10-02", source: "twse", price_kind: "daily_close", data_status: "fresh", is_within_ttl: null, reason: null }
          : overrides.price,
      fx: overrides.fx ?? null,
      fx_open: null,
      pnl_original: { value: "10000", currency },
      pnl_twd: overrides.pnl_twd === undefined ? "10000" : overrides.pnl_twd,
      asset_contribution_twd: "10000",
      fx_contribution_twd: "0",
    },
  } as SummaryPositionItem;
}

function render(
  positions: SummaryPositionItem[],
  extra: { initialExpandedIds?: number[]; names?: Record<string, string> } = {},
): string {
  return renderToStaticMarkup(
    createElement(PositionsTableView, {
      positions,
      namesBySymbol: extra.names ?? {},
      initialExpandedIds: extra.initialExpandedIds,
      changeMode: "close_only",
    }),
  );
}

describe("首頁區塊順序", () => {
  it("摘要卡 → 持倉表 → 風險儀表 → 警示列 → 族群動能卡", () => {
    const src = readSource("../../page.tsx");
    const idx = (needle: string) => {
      const i = src.indexOf(needle);
      expect(i, needle).toBeGreaterThan(-1);
      return i;
    };
    const order = [
      idx("<SummaryCards"),
      idx("<PositionsTable "),
      idx("<RiskGauge />"),
      idx("<AlertStatusStrip />"),
      idx("<SectorMomentumCard />"),
    ];
    expect(order).toEqual([...order].sort((a, b) => a - b));
  });
});

describe("損益％（台幣口徑）", () => {
  it("pnl_twd ÷ cost_twd × 100", () => {
    expect(pnlPercentTwd(makePosition(1, "A", { pnl_twd: "12340", cost_twd: "100000" }))).toBeCloseTo(12.34, 6);
    expect(pnlPercentTwd(makePosition(1, "A", { pnl_twd: "-3100", cost_twd: "100000" }))).toBeCloseTo(-3.1, 6);
  });

  it("算不出來就是 null，不捏造（缺損益、缺成本、成本為 0）", () => {
    expect(pnlPercentTwd(makePosition(1, "A", { pnl_twd: null }))).toBeNull();
    expect(pnlPercentTwd(makePosition(1, "A", { cost_twd: null }))).toBeNull();
    expect(pnlPercentTwd(makePosition(1, "A", { cost_twd: "0" }))).toBeNull();
  });

  it("一律帶正負號，四捨五入為 0 時不帶號", () => {
    expect(formatSignedPercent(12.341)).toBe("+12.34%");
    expect(formatSignedPercent(-3.1)).toBe("-3.10%");
    expect(formatSignedPercent(0.001)).toBe("0.00%");
  });
});

describe("損益％（第二階段：標籤、口徑句、顯示）", () => {
  it("字面逐字（風控核可 2026-10-03）", () => {
    expect(PRIMARY_HEADER_LABELS.pnlPercentTwd).toBe("台幣損益％");
    expect(FOREIGN_PNL_PERCENT_NOTE).toBe("外幣持倉的台幣損益％含匯率變動。");
    expect(SORT_CONTROL_LABEL).toBe("排序");
  });

  it("百分比格永遠帶 % 與正負號；算不出來顯示「—」且不帶 %", () => {
    const html = render([
      makePosition(1, "AAA", { pnl_twd: "12340", cost_twd: "100000" }),
      makePosition(2, "BBB", { pnl_twd: "-3100", cost_twd: "100000" }),
      makePosition(3, "CCC", { pnl_twd: "0", cost_twd: "100000" }),
    ]);
    expect(html).toContain(">+12.34%<");
    expect(html).toContain(">-3.10%<");
    expect(html).toContain(">0.00%<");
    // every percent cell (the one right after the mobile mini-label) is "—" or a signed number with %
    const cells = [...html.matchAll(/md:hidden">台幣損益％<\/p><p class="text-sm tabular-nums">(.*?)<\/p>/g)].map((m) =>
      (m[1] ?? "").replace(/<[^>]+>/g, ""),
    );
    expect(cells).toEqual(["+12.34%", "-3.10%", "0.00%"]);

    const dash = render([makePosition(4, "DDD", { pnl_twd: "100", cost_twd: null })]);
    const pct = /<p class="text-xs text-neutral-400 md:hidden">台幣損益％<\/p><p class="text-sm tabular-nums"><span class="text-neutral-400">—<\/span><\/p>/;
    expect(dash).toMatch(pct);
    expect(dash).not.toContain("%<");
  });

  it("標籤：桌機表頭一欄、手機小標同字串", () => {
    const html = render([makePosition(1, "AAA")]);
    // header button text (desktop) + mobile mini-label
    expect(html).toMatch(/<button[^>]*>台幣損益％<span/);
    expect(html).toContain('<p class="text-xs text-neutral-400 md:hidden">台幣損益％</p>');
  });

  it("口徑句：有外幣列才顯示；位置在排序列與表格之前；text-xs text-neutral-400；不放 title", () => {
    const usd = makePosition(2, "AAPL", { currency: "USD" });
    const html = render([makePosition(1, "2330"), usd]);
    expect(html).toContain('<p class="mb-2 text-xs text-neutral-400">外幣持倉的台幣損益％含匯率變動。</p>');
    expect(html.indexOf(FOREIGN_PNL_PERCENT_NOTE)).toBeLessThan(html.indexOf('role="table"'));
    expect(html).not.toContain(`title="${FOREIGN_PNL_PERCENT_NOTE}`);
    // never inside the expandable block
    const detailStart = html.indexOf('id="pos-detail-1"');
    expect(html.indexOf(FOREIGN_PNL_PERCENT_NOTE)).toBeLessThan(detailStart);
    expect(html.split(FOREIGN_PNL_PERCENT_NOTE).length - 1).toBe(1);
  });

  it("全台幣持倉不顯示口徑句", () => {
    const html = render([makePosition(1, "2330"), makePosition(2, "2317")]);
    expect(html).not.toContain(FOREIGN_PNL_PERCENT_NOTE);
    expect(html).not.toContain("含匯率變動");
  });

  it("觸發只看 currency：該列％為「—」或匯率缺失也照樣顯示", () => {
    const noPercent = makePosition(1, "AAPL", { currency: "USD", pnl_twd: null, cost_twd: null, fx: null });
    expect(hasForeignCurrencyPosition([noPercent])).toBe(true);
    expect(render([noPercent])).toContain(FOREIGN_PNL_PERCENT_NOTE);
    expect(hasForeignCurrencyPosition([])).toBe(false);
  });
});

describe("持倉表排序", () => {
  const rows = [
    makePosition(1, "A", { pnl_twd: "-500" }),
    makePosition(2, "B", { pnl_twd: null }),
    makePosition(3, "C", { pnl_twd: "900" }),
    makePosition(4, "D", { pnl_twd: "100" }),
  ];
  const ids = (list: SummaryPositionItem[]) => list.map((p) => p.id);

  it("預設（null）維持後端順序", () => {
    expect(ids(sortByPnlTwd(rows, null))).toEqual([1, 2, 3, 4]);
    // and the rendered default order is the backend's too
    const html = render(rows);
    const at = ["A", "B", "C", "D"].map((s) => html.indexOf(`>${s}</a>`));
    expect(at).toEqual([...at].sort((a, b) => a - b));
    expect(at.every((i) => i > -1)).toBe(true);
  });

  it("表頭循環：desc → asc → 回到預設", () => {
    expect(nextPnlSortDirection(null)).toBe("desc");
    expect(nextPnlSortDirection("desc")).toBe("asc");
    expect(nextPnlSortDirection("asc")).toBeNull();
  });

  it("空值不論方向都排最後", () => {
    expect(ids(sortByPnlTwd(rows, "desc"))).toEqual([3, 4, 1, 2]);
    expect(ids(sortByPnlTwd(rows, "asc"))).toEqual([1, 4, 3, 2]);
  });

  it("不改動傳入陣列", () => {
    const copy = ids(rows);
    sortByPnlTwd(rows, "desc");
    expect(ids(rows)).toEqual(copy);
  });

  it("台幣損益表頭是 button 且帶 aria-sort（預設 none）", () => {
    const html = render(rows);
    expect(html).toMatch(/aria-sort="none"[^>]*><button/);
  });
});

describe("持倉表結構（瘦身）", () => {
  const html = render(
    [
      makePosition(7, "2330", {}),
      makePosition(8, "AAPL", {
        currency: "USD",
        fx: { as_of: "2026-10-02", data_status: "fresh", is_within_ttl: null, reason: null, source_note: null } as never,
      }),
    ],
    { names: { "2330": "台積電" } },
  );

  it("不再有 min-w-[980px] 或 overflow-x-auto（375px 不橫向捲動）", () => {
    expect(html).not.toContain("min-w-[980px]");
    expect(html).not.toContain("overflow-x-auto");
    const src = readSource("../../components/PositionsTable.tsx");
    expect(src).not.toContain("min-w-[980px]");
    expect(src).not.toContain("overflow-x-auto");
    expect(src).not.toContain("<table");
  });

  it("預設可見：代號／名稱、現價＋日期、台幣損益；日期標籤為 neutral-400", () => {
    expect(html).toContain("2330");
    expect(html).toContain("台積電");
    expect(html).toContain("10/02 收盤");
    expect(html).toContain("台幣損益");
    expect(html).toContain("10/02 匯率");
    const dateLabel = /<span class="([^"]*)">10\/02 收盤<\/span>/.exec(html);
    expect(dateLabel?.[1]).toContain("text-neutral-400");
    expect(dateLabel?.[1]).not.toContain("text-neutral-500");
    expect(html).not.toContain("text-neutral-500");
  });

  it("預設全收合：展開鈕 aria-expanded=false、controls 對得到區塊、區塊 hidden", () => {
    expect(html).toContain('aria-expanded="false"');
    expect(html).toContain('aria-controls="pos-detail-7"');
    expect(html).toMatch(/id="pos-detail-7"[^>]*hidden/);
  });

  it("展開鈕為 44×44 並有 focus-visible outline", () => {
    expect(html).toContain("h-11 w-11");
    expect(html).toContain("focus-visible:outline-2");
  });

  it("展開區八個欄位標籤齊全（沿用舊表頭字面）＋「到庫存修改」連結，無編輯／刪除／移除按鈕", () => {
    const detail = html.slice(html.indexOf('id="pos-detail-7"'), html.indexOf('id="pos-detail-8"'));
    for (const label of Object.values(DETAIL_FIELD_LABELS)) {
      expect(detail, label).toContain(label);
    }
    expect(detail).toContain("到庫存修改");
    expect(detail).toContain("min-h-11");
    expect(detail).not.toContain("編輯");
    expect(detail).not.toContain("刪除");
    expect(detail).not.toContain("移除");
    // Up to this row's own end (the next row group starts with its own chevron button).
    const ownDetail = detail.slice(0, detail.indexOf('<div role="rowgroup"') === -1 ? undefined : detail.indexOf('<div role="rowgroup"'));
    expect(ownDetail).not.toContain("<button");
  });

  it("AC-8／S19：連結指向 /positions#pos-{id}，sky 底線、44px、focus-visible；每列字面與 class 一致", () => {
    const detail7 = html.slice(html.indexOf('id="pos-detail-7"'), html.indexOf('id="pos-detail-8"'));
    const link = /<a class="([^"]*)" href="\/positions#pos-7">到庫存修改<\/a>/.exec(detail7);
    expect(link, "link markup").not.toBeNull();
    const cls = link?.[1] ?? "";
    for (const token of ["text-sky-400", "underline", "min-h-11", "focus-visible:outline-sky-400"]) {
      expect(cls, token).toContain(token);
    }
    const detail8 = html.slice(html.indexOf('id="pos-detail-8"'));
    const link8 = /<a class="([^"]*)" href="\/positions#pos-8">到庫存修改<\/a>/.exec(detail8);
    expect(link8?.[1]).toBe(cls);
  });

  it("首頁原始碼不再持有 EditPositionModal／刪除流程，也不依損益或風險改變連結", () => {
    const src = readSource("../../components/PositionsTable.tsx");
    expect(src).not.toContain("EditPositionModal");
    expect(src).not.toContain("useDeletePosition");
    expect(src).not.toContain("window.confirm");
    expect(src).not.toContain("deleteButtonState");
    expect(src).not.toContain("onEdit");
    expect(src).not.toContain("onDelete");
    expect(src).toContain("HOME_LINK_TO_INVENTORY");
  });

  it("展開區的欄位不在預設可見區（預設列內沒有這些標籤）", () => {
    const firstRow = html.slice(0, html.indexOf('id="pos-detail-7"'));
    for (const label of Object.values(DETAIL_FIELD_LABELS)) {
      expect(firstRow, label).not.toContain(label);
    }
  });

  it("initialExpandedIds 可讓指定列展開", () => {
    const open = render([makePosition(7, "2330")], { initialExpandedIds: [7] });
    expect(open).toContain('aria-expanded="true"');
    expect(open).not.toMatch(/id="pos-detail-7"[^>]*hidden/);
  });

  it("漲跌欄已是真實欄位：預設視圖有表頭，舊 placeholder 已刪除（ADR-0016 K-9）", () => {
    expect(html).toContain("收盤漲跌");
    expect(readSource("../positionsTableView.ts")).not.toContain("TODAY_CHANGE_SLOT");
    expect(readSource("../../components/PositionsTable.tsx")).not.toContain("TODAY_CHANGE_SLOT");
  });
});

describe("缺價列", () => {
  it("缺價時顯示「—」與資料不足徽章，缺資料說明句為 neutral-400", () => {
    const html = render([
      {
        ...makePosition(1, "X"),
        valuation: { ...makePosition(1, "X").valuation, status: "insufficient_data", price: null, missing: ["price"] },
      } as SummaryPositionItem,
    ]);
    expect(html).toContain("資料不足");
    expect(html).not.toContain("text-neutral-500");
  });
});

describe("風險儀表配色（非紅綠）", () => {
  const statuses: LimitStatus[] = ["passed", "violated", "not_evaluable"];

  it("chip 與進度條 class 不含 emerald／rose", () => {
    for (const status of statuses) {
      expect(riskGaugeChipClass(status)).not.toMatch(/emerald|rose|green|red-/);
      expect(riskGaugeBarFillClass(status)).not.toMatch(/emerald|rose|green|red-/);
    }
  });

  it("通過＝灰空心、已違反＝橘實心、無法評估＝虛線框", () => {
    expect(riskGaugeChipClass("passed")).toContain("bg-transparent");
    expect(riskGaugeChipClass("violated")).toContain("bg-orange-400");
    expect(riskGaugeChipClass("not_evaluable")).toContain("border-dashed");
    expect(riskGaugeBarFillClass("violated")).toBe("bg-orange-400");
    expect(riskGaugeBarFillClass("passed")).toBe("bg-neutral-400");
  });

  it("個股頁 LimitsCheckList 的狀態 chip 與首頁風險儀表同 class（G4，不另立第三套配色）", () => {
    const limits: LimitCheck[] = statuses.map((status, i) => ({
      id: `limit-${i}`,
      index: i + 1,
      name: `cap-${i}`,
      status,
      detail: "detail",
      observed: 0.1,
      threshold: 0.2,
    }));
    const html = renderToStaticMarkup(createElement(LimitsCheckList, { limits }));
    for (const status of statuses) {
      expect(html).toContain(riskGaugeChipClass(status));
    }
    expect(html).not.toMatch(/emerald|rose|green|red-/);
    const src = readSource("../../position/[symbol]/LimitsCheckList.tsx");
    expect(src).toContain("riskGaugeChipClass(limit.status)");
    expect(src).not.toContain("limitStatusColorClass");
  });

  it("字面不變：RiskGauge 沒有新增 ✓ ✕ ？ 符號", () => {
    const src = readSource("../../components/RiskGauge.tsx");
    expect(src).not.toMatch(/[✓✕？]/);
  });
});

describe("NavBar 目前頁", () => {
  it("總覽：/ 與 /position/<symbol>，但 /positions 不亮總覽", () => {
    expect(isNavItemActive("/", "/")).toBe(true);
    expect(isNavItemActive("/position/2330", "/")).toBe(true);
    expect(isNavItemActive("/positions", "/")).toBe(false);
  });

  it("庫存只亮在 /positions；/position/2330 不亮庫存（只差一個 s）", () => {
    expect(isNavItemActive("/positions", "/positions")).toBe(true);
    expect(isNavItemActive("/position/2330", "/positions")).toBe(false);
    expect(isNavItemActive("/", "/positions")).toBe(false);
  });

  it("其他頁完整路徑段比對", () => {
    expect(isNavItemActive("/playbook", "/playbook")).toBe(true);
    expect(isNavItemActive("/settings", "/settings")).toBe(true);
    expect(isNavItemActive("/settings", "/backtest")).toBe(false);
    expect(isNavItemActive("/backtest/x", "/backtest")).toBe(true);
    expect(isNavItemActive(null, "/")).toBe(false);
  });

  it("NavBar 帶 aria-current、保留 border-b-2 不位移、字面未改", () => {
    const src = readSource("../../components/NavBar.tsx");
    expect(src).toContain('aria-current={active ? "page" : undefined}');
    expect(src).toContain("border-b-2");
    expect(src).toContain("label: INVENTORY_NAV_LABEL");
    expect(src).toContain("href: INVENTORY_ROUTE");
    expect(src).not.toContain("匯入／新增");
    expect(src).not.toContain("匯入 / 新增部位");
    expect(src).not.toContain("font-medium\" : \"");
  });
});

describe("手機排序下拉（< md）", () => {
  const rows = [
    makePosition(1, "B", { pnl_twd: "-500", cost_twd: "1000" }),
    makePosition(2, "C", { pnl_twd: null }),
    makePosition(3, "A", { pnl_twd: "900", cost_twd: "1000" }),
    makePosition(4, "D", { pnl_twd: "100", cost_twd: "1000" }),
  ];
  const ids = (list: SummaryPositionItem[]) => list.map((p) => p.id);

  it("選項字面與順序逐字釘住（9 項；收盤漲跌表頭下第 8、9 項為「收盤漲跌」）", () => {
    expect(SORT_OPTIONS.map((o) => o.label)).toEqual([
      "預設順序",
      "代號 小到大",
      "代號 大到小",
      "台幣損益％ 高到低",
      "台幣損益％ 低到高",
      "台幣損益 高到低",
      "台幣損益 低到高",
      "收盤漲跌 高到低",
      "收盤漲跌 低到高",
    ]);
    const html = render(rows);
    expect([...html.matchAll(/<option /g)]).toHaveLength(9);
  });

  it("選項欄名引用表頭同一字串常數（不是第二份手打）", () => {
    expect(SORT_OPTIONS[1]?.label.startsWith(`${PRIMARY_HEADER_LABELS.symbol} `)).toBe(true);
    expect(SORT_OPTIONS[3]?.label.startsWith(`${PRIMARY_HEADER_LABELS.pnlPercentTwd} `)).toBe(true);
    expect(SORT_OPTIONS[5]?.label.startsWith(`${PRIMARY_HEADER_LABELS.pnlTwd} `)).toBe(true);
    const src = readSource("../positionsTableView.ts");
    const optionsBlock = src.slice(src.indexOf("export function sortOptions"), src.indexOf("/** The dropdown option id"));
    expect(optionsBlock).not.toMatch(/[\u4e00-\u9fff]/);
    expect(optionsBlock).toContain("PRIMARY_HEADER_LABELS.pnlPercentTwd");
    expect(optionsBlock).toContain("changeHeaderLabel(allowIntraday)");
  });

  it("可見 <label> 綁 <select>，只在 < md 顯示，min-h-11", () => {
    const html = render(rows);
    expect(html).toMatch(/<label for="positions-sort-select"[^>]*>排序<\/label>/);
    expect(html).toMatch(/<select id="positions-sort-select"[^>]*min-h-11/);
    expect(html).toMatch(/class="mb-2 flex items-center justify-end gap-2 md:hidden"/);
    expect(html).not.toMatch(/<select[^>]*aria-label/);
  });

  it("預設選第一項「預設順序」", () => {
    expect(render(rows)).toMatch(/<option value="default" selected="">預設順序<\/option>/);
  });

  it("代號排序：小到大／大到小", () => {
    expect(ids(sortPositions(rows, { key: "symbol", direction: "asc" }))).toEqual([3, 1, 2, 4]);
    expect(ids(sortPositions(rows, { key: "symbol", direction: "desc" }))).toEqual([4, 2, 1, 3]);
  });

  it("損益％與台幣損益排序：空值永遠最後", () => {
    // pnl%: A 90, D 10, B -50, C null
    expect(ids(sortPositions(rows, { key: "pnlPercentTwd", direction: "desc" }))).toEqual([3, 4, 1, 2]);
    expect(ids(sortPositions(rows, { key: "pnlPercentTwd", direction: "asc" }))).toEqual([1, 4, 3, 2]);
    expect(ids(sortPositions(rows, { key: "pnlTwd", direction: "desc" }))).toEqual([3, 4, 1, 2]);
    expect(ids(sortPositions(rows, { key: "pnlTwd", direction: "asc" }))).toEqual([1, 4, 3, 2]);
    expect(ids(sortPositions(rows, null))).toEqual([1, 2, 3, 4]);
  });

  it("與桌機表頭共用同一 state：表頭循環與下拉 id 互相對得上", () => {
    // header cycle per column: default direction -> reverse -> backend order
    let state = nextSortState(null, "symbol");
    expect(state).toEqual({ key: "symbol", direction: "asc" });
    state = nextSortState(state, "symbol");
    expect(state).toEqual({ key: "symbol", direction: "desc" });
    expect(nextSortState(state, "symbol")).toBeNull();
    expect(nextSortState(null, "pnlPercentTwd")).toEqual({ key: "pnlPercentTwd", direction: "desc" });
    expect(nextSortState({ key: "pnlTwd", direction: "desc" }, "pnlPercentTwd")).toEqual({
      key: "pnlPercentTwd",
      direction: "desc",
    });
    // every reachable state has a dropdown option and round-trips
    for (const option of SORT_OPTIONS) {
      expect(sortStateFromOptionId(sortOptionId(option.state))).toEqual(option.state);
    }
    expect(sortStateFromOptionId("nonsense")).toBeNull();
    expect(nextSortState(null, "change")).toEqual({ key: "change", direction: "desc" });
    // one `useState<SortState>` drives both the headers and the select
    const src = readSource("../../components/PositionsTable.tsx");
    expect(src.match(/useState<SortState>/g)).toHaveLength(1);
    expect(src).toContain("onChange={(e) => setSort(sortStateFromOptionId(e.target.value))}");
  });

  it("桌機表頭：代號、台幣損益％、台幣損益、收盤漲跌四欄皆為 button＋aria-sort，現價不可排序", () => {
    const html = render(rows);
    expect([...html.matchAll(/aria-sort="none"[^>]*><button/g)]).toHaveLength(4);
    expect(html).not.toMatch(/<button[^>]*>現價/);
  });

  it("展開鈕 aria-label 維持 {代號} 持倉明細", () => {
    expect(render(rows)).toContain('aria-label="B 持倉明細"');
  });
});

describe("NavBar 第二階段（庫存、< 768px 兩列）", () => {
  const src = readSource("../../components/NavBar.tsx");

  it("導覽第三項為「庫存」→ /positions（S1），舊字面不在導覽；頁面 h1 為「庫存」（S2）", () => {
    expect(INVENTORY_NAV_LABEL).toBe("庫存");
    expect(INVENTORY_ROUTE).toBe("/positions");
    expect(src).toContain("{ href: INVENTORY_ROUTE, label: INVENTORY_NAV_LABEL }");
    expect(src).not.toContain("匯入／新增");
    expect(src).not.toContain("匯入 / 新增部位");
    expect(INVENTORY_PAGE_TITLE).toBe("庫存");
    expect(readSource("../../positions/page.tsx")).toContain("{INVENTORY_PAGE_TITLE}");
  });

  it("導覽順序：總覽、排程台、庫存、回測、設定，且 NAV 區塊內無 /positions/import", () => {
    const start = src.indexOf("const NAV_ITEMS");
    const block = src.slice(start, src.indexOf("] as const", start));
    const order = ["總覽", "/playbook", "INVENTORY_ROUTE", "/backtest", "/settings"].map((n) => block.indexOf(n));
    expect(order.every((i) => i > -1)).toBe(true);
    expect(order).toEqual([...order].sort((a, b) => a - b));
    expect(block).not.toContain("/positions/import");
  });

  it("< 768px logo 自成一列、導覽單列；≥ 768px 才並排（斷點為 md，不是 sm）", () => {
    expect(src).toContain("flex flex-col gap-2 md:flex-row md:items-center md:justify-between md:gap-4");
    expect(src).toContain("flex flex-wrap justify-between gap-x-4 gap-y-1 md:justify-start");
    expect(src).toContain("md:flex-row md:items-center md:justify-between");
    expect(src).not.toContain("sm:flex-row");
  });
});

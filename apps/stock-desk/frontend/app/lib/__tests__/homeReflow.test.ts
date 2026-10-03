import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";
import { PositionsTableView } from "../../components/PositionsTable";
import {
  DETAIL_FIELD_LABELS,
  TODAY_CHANGE_SLOT,
  formatSignedPercent,
  isNavItemActive,
  nextPnlSortDirection,
  pnlPercentTwd,
  sortByPnlTwd,
} from "../positionsTableView";
import { riskGaugeBarFillClass, riskGaugeChipClass } from "../riskGauge";
import type { LimitStatus, SummaryPositionItem } from "../types";

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
    valuation: {
      status: "ok",
      missing: [],
      price:
        overrides.price === undefined
          ? { value: "110", as_of: "2026-10-02", source: "twse", data_status: "fresh", is_within_ttl: null, reason: null }
          : overrides.price,
      fx: overrides.fx ?? null,
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
      pendingDeleteId: null,
      onEdit: () => {},
      onDelete: () => {},
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

  it("phase 1 renders no percentage in the default row (risk veto 2026-10-03: unlabelled TWD-basis % pending wording)", () => {
    for (const pnl of [null, "12340", "-3100"]) {
      const html = render([makePosition(1, "AAA", { pnl_twd: pnl })]);
      expect(html).not.toMatch(/\d%</);
      expect(html).not.toContain("+12.34%");
      expect(html).not.toContain("-3.10%");
    }
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

  it("展開區八個欄位標籤齊全（沿用舊表頭字面）＋編輯／刪除", () => {
    const detail = html.slice(html.indexOf('id="pos-detail-7"'), html.indexOf('id="pos-detail-8"'));
    for (const label of Object.values(DETAIL_FIELD_LABELS)) {
      expect(detail, label).toContain(label);
    }
    expect(detail).toContain("編輯");
    expect(detail).toContain("刪除");
    expect(detail).toContain("min-h-11");
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

  it("今日漲跌：槽位預留但不渲染", () => {
    expect(TODAY_CHANGE_SLOT.enabled).toBe(false);
    expect(html).not.toContain("漲跌");
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

  it("字面不變：RiskGauge 沒有新增 ✓ ✕ ？ 符號", () => {
    const src = readSource("../../components/RiskGauge.tsx");
    expect(src).not.toMatch(/[✓✕？]/);
  });
});

describe("NavBar 目前頁", () => {
  it("總覽：/ 與 /position/<symbol>，但 /positions/import 不亮總覽", () => {
    expect(isNavItemActive("/", "/")).toBe(true);
    expect(isNavItemActive("/position/2330", "/")).toBe(true);
    expect(isNavItemActive("/positions/import", "/")).toBe(false);
  });

  it("匯入／新增只亮在 /positions/import", () => {
    expect(isNavItemActive("/positions/import", "/positions/import")).toBe(true);
    expect(isNavItemActive("/position/2330", "/positions/import")).toBe(false);
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
    expect(src).toContain("匯入 / 新增部位");
    expect(src).not.toContain("font-medium\" : \"");
  });
});

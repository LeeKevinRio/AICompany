/**
 * Pure view logic for the home-page holdings table (home reflow,
 * `work/stock-desk-首頁重排-視覺規範-2026-10-03.md` §2).
 *
 * Phase 1 reused only pre-reflow labels. Phase 2 adds the strings below, all
 * word-for-word from the risk-approved draft
 * (`work/reviews/2026-10-03-首頁重排-第二階段字面-風控核可.md`); changing any of
 * them needs a fresh risk review and the pinned tests in `homeReflow.test.ts`.
 */

import type { SummaryPositionItem } from "./types";

/**
 * Labels of the fields moved into each row's expandable block. Byte-for-byte
 * the pre-reflow column headers (spec §2.1 / L4: only their position changes).
 */
export const DETAIL_FIELD_LABELS = {
  market: "市場",
  instrumentType: "類型",
  quantity: "數量",
  avgCost: "平均成本（原幣）",
  openedAt: "建倉日期",
  pnlOriginal: "原幣損益",
  assetContribution: "標的貢獻",
  fxContribution: "匯率貢獻",
} as const;

/** Pre-reflow header strings still used by the default (collapsed) view. */
export const PRIMARY_HEADER_LABELS = {
  symbol: "代號",
  price: "現價",
  pnlTwd: "台幣損益",
  /** Desktop header and mobile mini-label share this one string (spec §2.2). */
  pnlPercentTwd: "台幣損益％",
} as const;

/**
 * Basis sentence for the TWD P&L percentage. Shown between the section h2 and
 * the table/list, at both widths, whenever at least one listed position is
 * non-TWD (risk condition: the trigger looks only at `currency`, never at
 * whether that row's percentage is computable or the FX lookup succeeded).
 * Never a `title`, never inside the expandable block.
 */
export const FOREIGN_PNL_PERCENT_NOTE = "外幣持倉的台幣損益％含匯率變動。";

/** True when any listed row is held in a currency other than TWD. */
export function hasForeignCurrencyPosition(
  positions: readonly Pick<SummaryPositionItem, "currency">[],
): boolean {
  return positions.some((p) => p.currency !== "TWD");
}

/** Visible label of the mobile (< md) sort dropdown; bound to the select via `<label htmlFor>`. */
export const SORT_CONTROL_LABEL = "排序";

/** Option for "back to backend order" in the mobile sort dropdown. */
export const SORT_DEFAULT_OPTION_LABEL = "預設順序";

/** Direction words used in the mobile sort options. */
const SORT_WORDS = {
  text: { asc: "小到大", desc: "大到小" },
  number: { asc: "低到高", desc: "高到低" },
} as const;

/**
 * Reserved slot for the 今日漲跌 column (spec §3). Phase 1 deliberately does
 * not render it: the backend has no such field and its header wording is
 * still pending risk review. Flip `enabled` only together with the API field
 * and the approved wording; no render path reads it today.
 */
export const TODAY_CHANGE_SLOT = { enabled: false } as const;

/**
 * TWD-basis P&L percentage: `pnl_twd / cost_twd * 100`. Returns `null` when
 * either figure is missing, unparseable, or the cost is not positive — the
 * caller then leaves the line blank rather than inventing a number.
 */
export function pnlPercentTwd(position: SummaryPositionItem): number | null {
  const { pnl_twd: pnl } = position.valuation;
  const cost = position.cost_twd;
  if (pnl === null || cost === null) return null;
  const pnlNum = Number(pnl);
  const costNum = Number(cost);
  if (!Number.isFinite(pnlNum) || !Number.isFinite(costNum) || costNum <= 0) return null;
  return (pnlNum / costNum) * 100;
}

/** `+12.34%` / `-3.10%` / `0.00%` — the sign is always explicit (colour is not the only channel). */
export function formatSignedPercent(value: number): string {
  const rounded = Math.round(value * 100) / 100;
  if (rounded === 0) return "0.00%";
  const text = Math.abs(rounded).toLocaleString("zh-Hant-TW", {
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  });
  return `${rounded > 0 ? "+" : "-"}${text}%`;
}

/** `null` = backend order (the default); the header click cycles desc -> asc -> null. */
export type PnlSortDirection = "desc" | "asc" | null;

export function nextPnlSortDirection(current: PnlSortDirection): PnlSortDirection {
  if (current === null) return "desc";
  if (current === "desc") return "asc";
  return null;
}

/**
 * Sorts by signed 台幣損益. `null` direction returns the input order untouched.
 * Missing values (`null` or unparseable) always sort last, in either
 * direction. `Array.prototype.sort` is stable, so equal rows keep backend order.
 */
export function sortByPnlTwd(
  positions: readonly SummaryPositionItem[],
  direction: PnlSortDirection,
): SummaryPositionItem[] {
  if (direction === null) return [...positions];
  const sign = direction === "desc" ? -1 : 1;
  const numeric = (p: SummaryPositionItem): number | null => {
    const raw = p.valuation.pnl_twd;
    if (raw === null) return null;
    const n = Number(raw);
    return Number.isFinite(n) ? n : null;
  };
  return [...positions].sort((a, b) => {
    const av = numeric(a);
    const bv = numeric(b);
    if (av === null && bv === null) return 0;
    if (av === null) return 1;
    if (bv === null) return -1;
    return (av - bv) * sign;
  });
}

/** Columns the user can sort by. The price column is deliberately not sortable (spec §2.4). */
export type SortKey = "symbol" | "pnlPercentTwd" | "pnlTwd";
export type SortDirection = "asc" | "desc";
/** `null` = backend order. One state shared by the desktop headers and the mobile dropdown. */
export type SortState = { key: SortKey; direction: SortDirection } | null;

/** Direction of a column's first click (spec §2.4): symbol small-to-large, P&L large-to-small. */
export function defaultSortDirection(key: SortKey): SortDirection {
  return key === "symbol" ? "asc" : "desc";
}

/** Header click cycle per column: default direction -> reverse -> backend order. */
export function nextSortState(current: SortState, key: SortKey): SortState {
  const first = defaultSortDirection(key);
  if (current === null || current.key !== key) return { key, direction: first };
  if (current.direction === first) return { key, direction: first === "asc" ? "desc" : "asc" };
  return null;
}

export interface SortOption {
  /** Stable value for the `<select>`. */
  id: string;
  /** Visible text; the column name is the same constant the table header uses. */
  label: string;
  state: SortState;
}

function sortOption(key: SortKey, direction: SortDirection, columnLabel: string, kind: "text" | "number"): SortOption {
  return {
    id: `${key}:${direction}`,
    label: `${columnLabel} ${SORT_WORDS[kind][direction]}`,
    state: { key, direction },
  };
}

/**
 * Mobile sort dropdown options, in display order. Column names come straight
 * from `PRIMARY_HEADER_LABELS` (risk required: never hand-typed a second time).
 * Phase 2 renders seven options; the two change-column options wait for the
 * backend field.
 */
export const SORT_OPTIONS: readonly SortOption[] = [
  { id: "default", label: SORT_DEFAULT_OPTION_LABEL, state: null },
  sortOption("symbol", "asc", PRIMARY_HEADER_LABELS.symbol, "text"),
  sortOption("symbol", "desc", PRIMARY_HEADER_LABELS.symbol, "text"),
  sortOption("pnlPercentTwd", "desc", PRIMARY_HEADER_LABELS.pnlPercentTwd, "number"),
  sortOption("pnlPercentTwd", "asc", PRIMARY_HEADER_LABELS.pnlPercentTwd, "number"),
  sortOption("pnlTwd", "desc", PRIMARY_HEADER_LABELS.pnlTwd, "number"),
  sortOption("pnlTwd", "asc", PRIMARY_HEADER_LABELS.pnlTwd, "number"),
];

/** The dropdown option id that represents `state` (every reachable state has one). */
export function sortOptionId(state: SortState): string {
  if (state === null) return "default";
  return `${state.key}:${state.direction}`;
}

/** Resolves a `<select>` value back to a sort state; unknown values fall back to backend order. */
export function sortStateFromOptionId(id: string): SortState {
  return SORT_OPTIONS.find((o) => o.id === id)?.state ?? null;
}

function numericOrNull(raw: string | null): number | null {
  if (raw === null) return null;
  const n = Number(raw);
  return Number.isFinite(n) ? n : null;
}

/**
 * Sorts by any sortable column. `null` state returns the input order
 * untouched. Missing values (symbol empty, percentage/P&L not computable)
 * always sort last in either direction; the sort is stable so ties keep
 * backend order.
 */
export function sortPositions(
  positions: readonly SummaryPositionItem[],
  state: SortState,
): SummaryPositionItem[] {
  if (state === null) return [...positions];
  const sign = state.direction === "desc" ? -1 : 1;
  const value = (p: SummaryPositionItem): number | string | null => {
    switch (state.key) {
      case "symbol":
        return p.symbol === "" ? null : p.symbol;
      case "pnlPercentTwd":
        return pnlPercentTwd(p);
      case "pnlTwd":
        return numericOrNull(p.valuation.pnl_twd);
    }
  };
  const compare = (a: number | string, b: number | string): number => {
    if (typeof a === "number" && typeof b === "number") return a - b;
    const as = String(a);
    const bs = String(b);
    return as < bs ? -1 : as > bs ? 1 : 0;
  };
  return [...positions].sort((a, b) => {
    const av = value(a);
    const bv = value(b);
    if (av === null && bv === null) return 0;
    if (av === null) return 1;
    if (bv === null) return -1;
    return compare(av, bv) * sign;
  });
}

/**
 * NavBar current-page rule (spec §6.1). Whole path segments are compared:
 * `/position/<symbol>` (single-stock page, reached from 總覽) highlights 總覽,
 * and must never be confused with `/positions/import` — they differ by one
 * `s`, so a bare `startsWith("/position")` would be wrong.
 */
export function isNavItemActive(pathname: string | null, href: string): boolean {
  if (pathname === null) return false;
  if (href === "/") return pathname === "/" || pathname.startsWith("/position/");
  return pathname === href || pathname.startsWith(`${href}/`);
}

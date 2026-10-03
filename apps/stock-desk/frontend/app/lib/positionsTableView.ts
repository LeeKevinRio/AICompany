/**
 * Pure view logic for the home-page holdings table (first-phase reflow,
 * `work/stock-desk-首頁重排-視覺規範-2026-10-03.md` §2).
 *
 * Nothing in here introduces a user-visible string: every label is reused
 * from the pre-reflow table headers, and the percentage is derived from the
 * TWD figures the backend already returns.
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

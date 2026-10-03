/**
 * Pure view logic for the home-page holdings table (home reflow,
 * `work/stock-desk-首頁重排-視覺規範-2026-10-03.md` §2).
 *
 * Phase 1 reused only pre-reflow labels. Phase 2 adds the strings below, all
 * word-for-word from the risk-approved draft
 * (`work/reviews/2026-10-03-首頁重排-第二階段字面-風控核可.md`); changing any of
 * them needs a fresh risk review and the pinned tests in `homeReflow.test.ts`.
 */

import { formatTradingDateMonthDay } from "./format";
import type { ChangeMode, SummaryPositionItem } from "./types";

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
 * Change column (ADR-0016 K-9..K-15). Header wording, risk-approved
 * word-for-word (`work/reviews/2026-10-03-首頁重排-第二階段字面-風控核可.md`
 * item 2a / 2b). The header, the mobile mini-label and sort options 8/9 all read
 * these two constants through `changeHeaderLabel`; nothing else types them.
 */
export const CHANGE_HEADER_LABELS = {
  closeOnly: "收盤漲跌",
  mayIncludeIntraday: "漲跌",
} as const;

/**
 * The single derived switch (K-9): true only when the backend says the column
 * may hold intraday rows. Anything else - including a missing or unknown
 * value - is treated as close-only (fail closed). Header, mobile mini-label,
 * sort options 8/9 and "may an intraday row render" read only this.
 */
export function allowIntradayFromMode(mode: ChangeMode | undefined): boolean {
  return mode === "may_include_intraday";
}

/** Header / mobile mini-label / sort-option column name for the change column. */
export function changeHeaderLabel(allowIntraday: boolean): string {
  return allowIntraday ? CHANGE_HEADER_LABELS.mayIncludeIntraday : CHANGE_HEADER_LABELS.closeOnly;
}

/**
 * Basis label under a change figure, close basis only (risk 2c): `較 MM/DD 收盤`.
 * `MM/DD` is the backend's `basis_date`, string-formatted and never
 * date-computed (K-12). Returns `null` unless the input is a well-formed
 * `YYYY-MM-DD`, so an empty or garbled date can never print `較 — 收盤`.
 */
export function formatChangeBasisLabel(basisDate: string | null): string | null {
  // String range check only (month 01-12, day 01-31); never date arithmetic.
  if (basisDate === null || !/^\d{4}-(?:0[1-9]|1[0-2])-(?:0[1-9]|[12]\d|3[01])$/.test(basisDate)) return null;
  return `較 ${formatTradingDateMonthDay(basisDate)} 收盤`;
}

/**
 * Residual-risk disclosure for the change column (ADR-0016 D-6; risk
 * approved word-for-word 2026-10-03, `work/reviews/2026-10-03-漲跌欄-剩餘揭露-
 * 風控核可.md`). Rendered once, as its own paragraph directly under the
 * foreign-currency basis sentence (if any), at both widths, and only while the
 * change column itself is rendered (`isChangeColumnRendered`). It must never
 * read `change` nullness or `change_mode`, never go into a `title` or the
 * expandable block, and must appear nowhere else in the app: no other column,
 * page or label may reuse it or the phrase "實際報酬" (risk required 2).
 */
export const CHANGE_COLUMN_RESIDUAL_NOTE = "漲跌未計入除權息與分割，可能與實際報酬不同。";

/**
 * Whether the change column is rendered at all. The column is part of every
 * table render, so this is true exactly when there is at least one listed
 * position; it deliberately ignores every cell's content and `change_mode`.
 * `PositionsTableView` assumes its caller already blocks the empty list
 * (`PositionsTable` shows `EmptyPositionsState`); given an empty array it
 * returns `null` rather than render a column-less frame.
 */
export function isChangeColumnRendered(positions: readonly unknown[]): boolean {
  return positions.length > 0;
}

/** Largest integer-digit count accepted for a backend `pct` before the cell fails closed. */
const MAX_PCT_INTEGER_DIGITS = 7;

/**
 * Rounds a decimal string to two places, half away from zero, using integer
 * arithmetic only (no float rounding). Returns `null` for anything that is
 * not a plain decimal (`"2.5900"`, `"-0.0040"`, `"3"`), and for more than
 * `MAX_PCT_INTEGER_DIGITS` integer digits (a percentage that large is a
 * contract violation, and it would lose precision or overflow as a double).
 */
function roundDecimalStringTo2dp(raw: string): string | null {
  const match = /^(-?)(\d+)(?:\.(\d+))?$/.exec(raw);
  if (match === null) return null;
  const sign = match[1] ?? "";
  const intPart = match[2] ?? "";
  if (intPart.replace(/^0+(?=\d)/, "").length > MAX_PCT_INTEGER_DIGITS) return null;
  const fracPadded = (match[3] ?? "").padEnd(3, "0");
  let scaled = BigInt(intPart + fracPadded.slice(0, 2));
  if (fracPadded.charCodeAt(2) >= 53) scaled += BigInt(1); // third digit >= "5"
  const digits = scaled.toString().padStart(3, "0");
  const text = `${digits.slice(0, -2)}.${digits.slice(-2)}`;
  return scaled === BigInt(0) ? text : `${sign}${text}`;
}

/** What one change cell shows. `dash` = the whole cell is only "—", with no basis wording at all. */
export type ChangeCellView =
  | { kind: "dash" }
  | {
      kind: "value";
      /** Signed percent text with `%`, e.g. `+2.59%`. */
      text: string;
      /** Two-place decimal string the text was rounded from; feeds the red/green class. */
      colorValue: string;
      /** `較 MM/DD 收盤`. */
      basisLabel: string;
      /** The rounded value that is displayed, so ordering matches what the user sees. */
      sortValue: number;
    };

const DASH_VIEW: ChangeCellView = { kind: "dash" };

/**
 * Decides what a row's change cell shows. Fail-closed: the cell is a bare "—"
 * unless every condition holds (K-10, K-11, K-14):
 * - `change` present and `pct` parses as a plain decimal;
 * - `basis_date` is a well-formed date (never null, empty or garbled);
 * - `basis_kind` is a known kind and matches the row's own `price_kind`
 *   (`close` with `daily_close`);
 * - no intraday row renders while the mode is close-only (K-10), and intraday
 *   basis stays "—" in every mode until its wording is approved into code (K-14).
 * The frontend never recomputes `pct` and never infers a kind (K-5).
 */
export function resolveChangeCell(position: SummaryPositionItem, allowIntraday: boolean): ChangeCellView {
  const { change } = position;
  if (change === null || change === undefined) return DASH_VIEW;
  const priceKind = position.valuation.price?.price_kind;
  if (!allowIntraday && priceKind === "intraday_quote") return DASH_VIEW;
  if (change.basis_kind === "intraday") return DASH_VIEW;
  if (change.basis_kind !== "close") return DASH_VIEW;
  if (priceKind !== "daily_close") return DASH_VIEW;
  const basisLabel = formatChangeBasisLabel(change.basis_date);
  if (basisLabel === null) return DASH_VIEW;
  const rounded = roundDecimalStringTo2dp(change.pct);
  if (rounded === null) return DASH_VIEW;
  const numeric = Number(rounded);
  if (!Number.isFinite(numeric)) return DASH_VIEW;
  return {
    kind: "value",
    text: formatSignedPercent(numeric),
    colorValue: rounded,
    basisLabel,
    sortValue: numeric,
  };
}

/**
 * True when the price cell must show only "—": a present price whose
 * `price_kind` is not `daily_close` (an intraday row has no approved price
 * label in this build; an unknown or missing kind is never guessed at).
 * Mirrors the change cell's fail-closed rule. A missing price is handled by the
 * cell's own insufficient-data branch.
 */
export function isNonDailyClosePrice(position: SummaryPositionItem): boolean {
  const { price } = position.valuation;
  return price !== null && price !== undefined && price.price_kind !== "daily_close";
}

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
export type SortKey = "symbol" | "pnlPercentTwd" | "pnlTwd" | "change";
export type SortDirection = "asc" | "desc";
/** `null` = backend order. One state shared by the desktop headers and the mobile dropdown. */
export type SortState = { key: SortKey; direction: SortDirection } | null;

/** Direction of a column's first click (spec §2.4): symbol small-to-large, P&L and change large-to-small. */
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
 * Mobile sort dropdown options, in display order (nine items). Column names
 * come straight from `PRIMARY_HEADER_LABELS` and `changeHeaderLabel` (risk
 * required: never hand-typed a second time); items 8 and 9 follow the same
 * `allowIntraday` switch as the change column header (K-9).
 */
export function sortOptions(allowIntraday: boolean): readonly SortOption[] {
  const changeLabel = changeHeaderLabel(allowIntraday);
  return [
    { id: "default", label: SORT_DEFAULT_OPTION_LABEL, state: null },
    sortOption("symbol", "asc", PRIMARY_HEADER_LABELS.symbol, "text"),
    sortOption("symbol", "desc", PRIMARY_HEADER_LABELS.symbol, "text"),
    sortOption("pnlPercentTwd", "desc", PRIMARY_HEADER_LABELS.pnlPercentTwd, "number"),
    sortOption("pnlPercentTwd", "asc", PRIMARY_HEADER_LABELS.pnlPercentTwd, "number"),
    sortOption("pnlTwd", "desc", PRIMARY_HEADER_LABELS.pnlTwd, "number"),
    sortOption("pnlTwd", "asc", PRIMARY_HEADER_LABELS.pnlTwd, "number"),
    sortOption("change", "desc", changeLabel, "number"),
    sortOption("change", "asc", changeLabel, "number"),
  ];
}

/** The dropdown option id that represents `state` (every reachable state has one). */
export function sortOptionId(state: SortState): string {
  if (state === null) return "default";
  return `${state.key}:${state.direction}`;
}

/** Resolves a `<select>` value back to a sort state; unknown values fall back to backend order. */
export function sortStateFromOptionId(id: string): SortState {
  // Ids are the same in both modes (only the label text differs).
  return sortOptions(false).find((o) => o.id === id)?.state ?? null;
}

function numericOrNull(raw: string | null): number | null {
  if (raw === null) return null;
  const n = Number(raw);
  return Number.isFinite(n) ? n : null;
}

/**
 * Sorts by any sortable column. `null` state returns the input order
 * untouched. Missing values (symbol empty, percentage/P&L not computable, a
 * change cell that shows "—") always sort last in either direction; the sort
 * is stable so ties keep backend order. The change column orders by exactly
 * what it displays, so a fail-closed "—" row is always last; `allowIntraday`
 * defaults to the fail-closed close-only reading.
 */
export function sortPositions(
  positions: readonly SummaryPositionItem[],
  state: SortState,
  allowIntraday = false,
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
      case "change": {
        const cell = resolveChangeCell(p, allowIntraday);
        return cell.kind === "value" ? cell.sortValue : null;
      }
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

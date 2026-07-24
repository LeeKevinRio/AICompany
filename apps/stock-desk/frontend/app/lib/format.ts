/**
 * Formatting helpers for money, quantities and timestamps.
 *
 * Colour convention: this product follows the Taiwan retail-investor
 * convention of "獲利紅、虧損綠" (profit shown in red, loss shown in
 * green) — the mirror image of the "red up / green down" convention
 * used for daily price change elsewhere. This is a deliberate product
 * choice, not a bug; see `pnlColorClass` below.
 */

import type { Currency, InstrumentType, Market } from "./types";

const INSTRUMENT_TYPE_LABELS: Record<InstrumentType, string> = {
  stock: "股票",
  etf: "一般 ETF",
  leveraged_etf: "槓桿型 ETF",
  futures_etf: "期貨型 ETF",
};

/** `<select>` options for the manual add form, in a stable display order. */
export const INSTRUMENT_TYPE_OPTIONS: { value: InstrumentType; label: string }[] = [
  { value: "stock", label: INSTRUMENT_TYPE_LABELS.stock },
  { value: "etf", label: INSTRUMENT_TYPE_LABELS.etf },
  { value: "leveraged_etf", label: INSTRUMENT_TYPE_LABELS.leveraged_etf },
  { value: "futures_etf", label: INSTRUMENT_TYPE_LABELS.futures_etf },
];

export function instrumentTypeLabel(value: InstrumentType): string {
  return INSTRUMENT_TYPE_LABELS[value];
}

// Backend `Market = Literal["TW", "US"]` (app/positions/models.py) — this is
// the actual enum, not an invented restriction, so the manual form uses a
// <select> instead of free text.
const MARKET_LABELS: Record<Market, string> = {
  TW: "台股（TW）",
  US: "美股（US）",
};

export const MARKET_OPTIONS: { value: Market; label: string }[] = [
  { value: "TW", label: MARKET_LABELS.TW },
  { value: "US", label: MARKET_LABELS.US },
];

export function marketLabel(value: Market): string {
  return MARKET_LABELS[value];
}

// Backend `Currency = Literal["TWD", "USD"]` (app/positions/models.py).
const CURRENCY_LABELS: Record<Currency, string> = {
  TWD: "TWD（新台幣）",
  USD: "USD（美元）",
};

export const CURRENCY_OPTIONS: { value: Currency; label: string }[] = [
  { value: "TWD", label: CURRENCY_LABELS.TWD },
  { value: "USD", label: CURRENCY_LABELS.USD },
];

function currencyPrefix(currency: string): string {
  switch (currency) {
    case "TWD":
      return "NT$";
    case "USD":
      return "US$";
    default:
      return `${currency} `;
  }
}

/** Parses a stringified Decimal for display only — never for arithmetic. */
function toDisplayNumber(value: string): number | null {
  const n = Number(value);
  return Number.isFinite(n) ? n : null;
}

export function formatMoney(
  value: string | null,
  currency: string,
  decimals = 2,
): string {
  if (value === null) return "—";
  const n = toDisplayNumber(value);
  if (n === null) return "—";
  const formatted = n.toLocaleString("zh-Hant-TW", {
    minimumFractionDigits: decimals,
    maximumFractionDigits: decimals,
  });
  return `${currencyPrefix(currency)}${formatted}`;
}

export function formatQuantity(value: string): string {
  const n = toDisplayNumber(value);
  if (n === null) return "—";
  return n.toLocaleString("zh-Hant-TW", { maximumFractionDigits: 4 });
}

export function formatDateTime(iso: string | null | undefined): string {
  if (!iso) return "資料時間不明";
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return "資料時間不明";
  return new Intl.DateTimeFormat("zh-Hant-TW", {
    timeZone: "Asia/Taipei",
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
    hour12: false,
  }).format(d);
}

/** Minutes elapsed between the given ISO timestamp and now, floored at 0. */
export function staleMinutesSince(iso: string): number {
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return 0;
  const diffMs = Date.now() - d.getTime();
  return Math.max(0, Math.round(diffMs / 60000));
}

/**
 * Profit -> red, loss -> green (see module doc comment for rationale).
 * Neutral/unknown values stay in the default text colour.
 */
export function pnlColorClass(value: string | null): string {
  if (value === null) return "text-neutral-400";
  const n = toDisplayNumber(value);
  if (n === null || n === 0) return "text-neutral-400";
  return n > 0 ? "text-rose-400" : "text-emerald-400";
}

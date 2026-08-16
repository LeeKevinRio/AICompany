import type { Market } from "./types";

/**
 * TradingView symbol mapping for the Advanced Chart Widget embed
 * (`position/[symbol]/TradingViewChartPanel.tsx`).
 *
 * CEO 派工單 2026-08-16 (TradingView 嵌入):
 *   - TW → `TWSE:<代號>` (上市) by default; `TPEX:<代號>` (上櫃) only when the
 *     caller explicitly passes that hint.
 *   - US → the bare ticker, upper-cased, letting TradingView's own symbol
 *     resolver pick the exchange (NASDAQ/NYSE/…) — this frontend has no
 *     listing-exchange data of its own to prefix a US ticker with.
 *
 * `DirectoryItem` (`./types.ts`, backend `app/api/directory.py`, verified)
 * carries no listed-vs-OTC field today, so every current call site omits
 * `exchangeHint` and gets the TWSE default — the "無法確定就用 TWSE 形式"
 * fallback the CEO's brief calls for. This is a deliberate, honest default,
 * not a guess dressed up as fact: if the widget is given a 上櫃 TW symbol
 * under its TWSE default, TradingView's own "symbol not found" error surface
 * inside the widget iframe is what the reader sees, not a silently wrong
 * chart. If a future directory sync starts distinguishing 上市/上櫃, pass
 * `"TPEX"` explicitly from that new field rather than adding guessing logic
 * here.
 */
export type TradingViewExchangeHint = "TWSE" | "TPEX";

export function toTradingViewSymbol(
  symbol: string,
  market: Market,
  exchangeHint?: TradingViewExchangeHint,
): string {
  const trimmed = symbol.trim();
  if (market === "US") {
    return trimmed.toUpperCase();
  }
  const exchange: TradingViewExchangeHint = exchangeHint ?? "TWSE";
  return `${exchange}:${trimmed}`;
}

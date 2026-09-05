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
 *
 * Security fix (qa-reviewer NEEDS_CHANGES on 4938eb5, critical reflected
 * XSS): the caller's `symbol` for this page is `decodeURIComponent(params.symbol)`
 * from the URL (`position/[symbol]/page.tsx`) — an attacker-controlled string
 * that was previously interpolated into `TradingViewChartPanel`'s widget
 * config with no validation at all, and that config is rendered via
 * `dangerouslySetInnerHTML`. This is the first of two independent defensive
 * layers (the second is the script-context-safe JSON serialization in
 * `TradingViewChartPanel.tsx` itself): a real TW/US ticker only ever contains
 * letters, digits, `.`, and `-` (US tickers use both, e.g. `BRK.B`,
 * `BF-B`; TW tickers are plain alphanumerics), so anything outside that
 * whitelist is rejected outright rather than passed through. On rejection
 * this returns `null` — never a silently-substituted or partially-sanitized
 * value — so the caller must render a neutral "invalid symbol" state instead
 * of ever reaching the dangerous sink.
 */
export type TradingViewExchangeHint = "TWSE" | "TPEX";

/** TW/US ticker whitelist: letters, digits, `.`, `-` only — see doc comment above. */
const ALLOWED_SYMBOL_PATTERN = /^[A-Za-z0-9.-]+$/;

export function toTradingViewSymbol(
  symbol: string,
  market: Market,
  exchangeHint?: TradingViewExchangeHint,
): string | null {
  const trimmed = symbol.trim();
  if (!ALLOWED_SYMBOL_PATTERN.test(trimmed)) {
    return null;
  }
  if (market === "US") {
    return trimmed.toUpperCase();
  }
  const exchange: TradingViewExchangeHint = exchangeHint ?? "TWSE";
  return `${exchange}:${trimmed}`;
}

/**
 * Derive the TW exchange hint from whichever data-chain identifiers the page
 * already holds — the bars envelope's `DataMeta.source` (`"twse"` / `"tpex"`
 * provider ids) and the directory entry's `source` (TWSE / TPEx listing
 * feeds). The first identifier that names an exchange wins; anything else
 * (FinMind, Alpha Vantage, demo, unknown) yields `undefined` so the caller
 * keeps `toTradingViewSymbol`'s TWSE default. Fixes the bug where every TW
 * symbol was sent as `TWSE:` and 上櫃 stocks rendered as an invalid symbol
 * inside the widget.
 */
export function inferTradingViewExchange(
  ...sources: (string | null | undefined)[]
): TradingViewExchangeHint | undefined {
  for (const source of sources) {
    if (!source) continue;
    const lower = source.toLowerCase();
    if (lower.includes("tpex")) return "TPEX";
    if (lower.includes("twse")) return "TWSE";
  }
  return undefined;
}

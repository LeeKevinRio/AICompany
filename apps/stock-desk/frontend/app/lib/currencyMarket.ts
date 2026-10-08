/**
 * The currency a holding's cost must be stated in, per market. A typed copy of
 * `apps/stock-desk/shared/market-currency.json`, which mirrors the backend's
 * `MARKET_CURRENCY` / `currency_matches_market` in `app/positions/models.py`.
 * `marketCurrencyShared.test.ts` fails if this table and the shared JSON differ,
 * so the rule has one definition and cannot drift (X-3c XC-N4).
 */
export const MARKET_CURRENCY: Readonly<Record<string, string>> = {
  TW: "TWD",
  US: "USD",
};

/** Same semantics as the backend's `currency_matches_market`; an unknown market never matches. */
export function currencyMatchesMarket(market: string, currency: string): boolean {
  return Object.hasOwn(MARKET_CURRENCY, market) && MARKET_CURRENCY[market] === currency;
}

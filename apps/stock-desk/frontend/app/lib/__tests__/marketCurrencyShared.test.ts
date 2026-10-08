import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { describe, expect, it } from "vitest";
import { MARKET_CURRENCY, currencyMatchesMarket } from "../currencyMarket";

/**
 * X-3c XC-N4: the market -> currency rule has one definition,
 * `apps/stock-desk/shared/market-currency.json`, mirrored by the backend's
 * `MARKET_CURRENCY` (`app/positions/models.py`). The frontend copy must equal
 * the shared file exactly, so the two cannot drift.
 *
 * The backend side is pinned in
 * `apps/stock-desk/backend/tests/test_x3c_currency_market_mismatch.py`
 * (`test_xcn4_*`): it loads the same JSON, asserts
 * `dict(MARKET_CURRENCY) == json["market_currency"]`, and checks that
 * `currency_matches_market(m, c)` is True exactly for the pairs in the file.
 */
const SHARED_PATH = fileURLToPath(
  new URL("../../../../shared/market-currency.json", import.meta.url),
);

describe("currencyMarket — synced with shared/market-currency.json", () => {
  const shared = JSON.parse(readFileSync(SHARED_PATH, "utf-8")) as {
    market_currency: Record<string, string>;
  };

  it("the shared file is not empty (guards against a silently broken read)", () => {
    expect(Object.keys(shared.market_currency).length).toBeGreaterThan(0);
  });

  it("the frontend table equals the shared table exactly", () => {
    expect({ ...MARKET_CURRENCY }).toEqual(shared.market_currency);
  });

  it("currencyMatchesMarket is true exactly for the pairs in the shared file", () => {
    const markets = [...Object.keys(shared.market_currency), "XX", "toString", ""];
    const currencies = [...Object.values(shared.market_currency), "JPY", ""];
    for (const m of markets) {
      for (const c of currencies) {
        expect(currencyMatchesMarket(m, c), `${m}/${c}`).toBe(shared.market_currency[m] === c);
      }
    }
  });
});

import { describe, expect, it } from "vitest";
import { FRONTEND_FORBIDDEN_TERMS } from "../adviceWording";
import {
  CURRENCY_MARKET_MISMATCH_TOKEN,
  MISSING_LABELS,
  isCurrencyMarketMismatch,
  missingLabel,
  missingSummary,
} from "../valuationWording";
import { assertNoForbiddenTerms, findBareRealtimeClaims } from "./wordingScanHelpers";

/**
 * 風控 2026-09-18 C-1（ADR-0010 D-1）：`Valuation.missing` 的 token 不得以英文原樣上畫面，
 * 且「查了沒有」與「本次沒去查」必須一眼可分。字面為 creative-lead 草案，風控核可後逐字釘住。
 */
describe("valuationWording — Valuation.missing token labels", () => {
  it("labels every token the backend can emit, each within eight characters", () => {
    expect(Object.keys(MISSING_LABELS).sort()).toEqual([
      "currency_market_mismatch",
      "fx_now",
      "fx_open",
      "price",
      "price_not_queried",
    ]);
    for (const label of Object.values(MISSING_LABELS)) {
      expect(label.length).toBeLessThanOrEqual(8);
      expect(label).not.toMatch(/[A-Za-z_]/);
    }
  });

  it("keeps 'asked and found nothing' and 'not asked this time' as two distinct shapes", () => {
    expect(missingLabel("price")).toMatch(/^查無/);
    expect(missingLabel("fx_now")).toMatch(/^查無/);
    expect(missingLabel("fx_open")).toMatch(/^查無/);
    expect(missingLabel("price_not_queried")).toMatch(/^本次未查/);
    expect(missingLabel("price_not_queried")).not.toMatch(/查無/);
  });

  it("labels the X-3c mismatch token with the risk-approved 7-character noun phrase, distinct from both query shapes (風控 2026-10-08 第二段 RX-2)", () => {
    expect(missingLabel("currency_market_mismatch")).toBe("幣別與市場不符");
    expect(missingLabel("currency_market_mismatch")).toHaveLength(7);
    expect(missingLabel("currency_market_mismatch")).not.toBe("查無價格資料");
    expect(missingLabel("currency_market_mismatch")).not.toMatch(/^查無/);
    expect(missingLabel("currency_market_mismatch")).not.toMatch(/^本次未查/);
    expect(missingLabel("currency_market_mismatch")).not.toContain("資料不足");
    expect(CURRENCY_MARKET_MISMATCH_TOKEN).toBe("currency_market_mismatch");
  });

  it("treats a row as mismatch only when missing is exactly the one token (art-lead R-2)", () => {
    expect(isCurrencyMarketMismatch(["currency_market_mismatch"])).toBe(true);
    expect(isCurrencyMarketMismatch(["currency_market_mismatch", "price"])).toBe(false);
    expect(isCurrencyMarketMismatch(["price", "currency_market_mismatch"])).toBe(false);
    expect(isCurrencyMarketMismatch(["price"])).toBe(false);
    expect(isCurrencyMarketMismatch([])).toBe(false);
  });

  it("carries no banned term and no bare realtime claim (qa 2026-09-18: the labels live here, not in the scanned .tsx)", () => {
    for (const [token, label] of Object.entries(MISSING_LABELS)) {
      assertNoForbiddenTerms(label, FRONTEND_FORBIDDEN_TERMS, `MISSING_LABELS.${token}`);
      expect(findBareRealtimeClaims(label), token).toEqual([]);
    }
  });

  it("joins a list the way the positions table shows it and never hides an unknown token", () => {
    expect(missingSummary(["price", "fx_now"])).toBe("查無價格資料、查無即期匯率");
    expect(missingSummary(["something_new"])).toBe("something_new");
  });
});

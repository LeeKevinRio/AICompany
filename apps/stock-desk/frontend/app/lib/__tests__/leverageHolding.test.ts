/**
 * F-8: the stock page only asks for the leverage chapter when the symbol is
 * held. `hasLeverageHolding` must mirror the backend's `_pick_position`
 * (app/api/leverage.py) exactly, otherwise a holder would lose the chapter
 * (false negative) or a non-holder would get a console 404 (false positive).
 */
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { describe, expect, it } from "vitest";
import { hasLeverageHolding, isLeverageQueryEnabled } from "../leverageHolding";
import type { Market, Position, PositionsResponse } from "../types";

function lot(overrides: Partial<Position> = {}): Position {
  return {
    id: 1,
    symbol: "00631L",
    market: "TW",
    quantity: "1000",
    avg_cost: "150",
    currency: "TWD",
    opened_at: "2026-01-02",
    instrument_type: "leveraged_etf",
    note: null,
    created_at: "2026-01-02T00:00:00Z",
    updated_at: "2026-01-02T00:00:00Z",
    ...overrides,
  };
}

describe("hasLeverageHolding — mirrors backend _pick_position", () => {
  it("matches an exact symbol and market", () => {
    expect(hasLeverageHolding([lot()], "00631L", "TW")).toBe(true);
  });

  it("is case-insensitive in both directions", () => {
    expect(hasLeverageHolding([lot({ symbol: "00631L" })], "00631l", "TW")).toBe(true);
    expect(hasLeverageHolding([lot({ symbol: "tqqq", market: "US" })], "TQQQ", "US")).toBe(true);
    expect(hasLeverageHolding([lot({ symbol: "TQQQ", market: "US" })], "tqqq", "US")).toBe(true);
  });

  it("trims surrounding whitespace on both sides", () => {
    expect(hasLeverageHolding([lot({ symbol: "  00631L " })], "00631L", "TW")).toBe(true);
    expect(hasLeverageHolding([lot()], " 00631L\t", "TW")).toBe(true);
  });

  it("requires the market to be strictly equal", () => {
    expect(hasLeverageHolding([lot({ symbol: "AAPL", market: "TW" })], "AAPL", "US")).toBe(false);
    expect(hasLeverageHolding([lot({ symbol: "AAPL", market: "US", currency: "USD" })], "AAPL", "TW")).toBe(false);
  });

  it("does not match a different symbol (no prefix or substring match)", () => {
    expect(hasLeverageHolding([lot()], "00631", "TW")).toBe(false);
    expect(hasLeverageHolding([lot({ symbol: "00631" })], "00631L", "TW")).toBe(false);
  });

  it("returns false for an empty list", () => {
    expect(hasLeverageHolding([], "00631L", "TW")).toBe(false);
  });

  it("finds the symbol among several lots and unrelated holdings", () => {
    const items = [
      lot({ id: 1, symbol: "2330" }),
      lot({ id: 2, symbol: "00631L", opened_at: "2026-03-01" }),
      lot({ id: 3, symbol: "00631L", opened_at: null }),
    ];
    expect(hasLeverageHolding(items, "00631L", "TW")).toBe(true);
    expect(hasLeverageHolding(items, "2330", "TW")).toBe(true);
    expect(hasLeverageHolding(items, "0050", "TW")).toBe(false);
  });

  it("does not filter on quantity, cost or currency (unlike resolveKeyLevelsAnchor)", () => {
    expect(hasLeverageHolding([lot({ quantity: "0" })], "00631L", "TW")).toBe(true);
    expect(hasLeverageHolding([lot({ avg_cost: "0" })], "00631L", "TW")).toBe(true);
    expect(hasLeverageHolding([lot({ quantity: "abc", avg_cost: "n/a" })], "00631L", "TW")).toBe(true);
    // currency does not match the market: the backend still serves the chapter.
    expect(hasLeverageHolding([lot({ currency: "USD" })], "00631L", "TW")).toBe(true);
  });
});

describe("isLeverageQueryEnabled — enabling rule (pending / error / success+held / success+not held)", () => {
  const held: PositionsResponse = { items: [lot()], as_of: "x" };
  const notHeld: PositionsResponse = { items: [lot({ symbol: "2330" })], as_of: "x" };
  const empty: PositionsResponse = { items: [], as_of: "x" };
  const enabled = (
    state: { isError: boolean; isSuccess: boolean; data: PositionsResponse | undefined },
    symbol = "00631L",
    market: Market = "TW",
  ) => isLeverageQueryEnabled(state, symbol, market);

  it("pending: not enabled", () => {
    expect(enabled({ isError: false, isSuccess: false, data: undefined })).toBe(false);
  });

  it("error: enabled, so the old fallback path (and its quiet 404) still works", () => {
    expect(enabled({ isError: true, isSuccess: false, data: undefined })).toBe(true);
  });

  it("success and held: enabled", () => {
    expect(enabled({ isError: false, isSuccess: true, data: held })).toBe(true);
  });

  it("success and not held: not enabled", () => {
    expect(enabled({ isError: false, isSuccess: true, data: notHeld })).toBe(false);
    expect(enabled({ isError: false, isSuccess: true, data: empty })).toBe(false);
    expect(enabled({ isError: false, isSuccess: true, data: held }, "00631L", "US")).toBe(false);
  });

  it("success without data never enables", () => {
    expect(enabled({ isError: false, isSuccess: true, data: undefined })).toBe(false);
  });
});

describe("source guard — the page no longer queries leverage unconditionally", () => {
  const read = (rel: string) => readFileSync(fileURLToPath(new URL(rel, import.meta.url)), "utf-8");
  const page = read("../../position/[symbol]/page.tsx");

  it("page.tsx does not call useLeverageChapter with a literal true", () => {
    expect(page).not.toContain("useLeverageChapter(symbol, market, true)");
    expect(page).toContain("useLeverageChapter(symbol, market, leverageQueryEnabled)");
  });

  it("the helper does not reuse resolveKeyLevelsAnchor", () => {
    const helper = read("../leverageHolding.ts");
    expect(helper).not.toContain("resolveKeyLevelsAnchor");
    expect(helper).toContain("_pick_position");
  });

  it("the footer still carries the disclosure item (componentWordingScan relies on it)", () => {
    expect(page).toContain("[leverage.data.chapter.disclosure]");
  });
});

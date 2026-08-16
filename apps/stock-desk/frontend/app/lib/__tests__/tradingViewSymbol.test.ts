import { describe, expect, it } from "vitest";
import { toTradingViewSymbol } from "../tradingViewSymbol";

describe("toTradingViewSymbol", () => {
  it("maps a TW symbol to the TWSE-prefixed form by default (上市, no exchange hint)", () => {
    expect(toTradingViewSymbol("2330", "TW")).toBe("TWSE:2330");
  });

  it("maps a TW symbol to TPEX only when the caller passes that explicit hint (上櫃)", () => {
    expect(toTradingViewSymbol("6488", "TW", "TPEX")).toBe("TPEX:6488");
  });

  it("still defaults to TWSE for TW when the hint is explicitly TWSE", () => {
    expect(toTradingViewSymbol("2317", "TW", "TWSE")).toBe("TWSE:2317");
  });

  it("returns a bare, upper-cased ticker for US, letting TradingView resolve the exchange", () => {
    expect(toTradingViewSymbol("aapl", "US")).toBe("AAPL");
    expect(toTradingViewSymbol("MSFT", "US")).toBe("MSFT");
  });

  it("trims surrounding whitespace before mapping, for both markets", () => {
    expect(toTradingViewSymbol("  2330  ", "TW")).toBe("TWSE:2330");
    expect(toTradingViewSymbol("  aapl  ", "US")).toBe("AAPL");
  });

  it("ignores an exchange hint entirely for US (no TW-only concept leaks across markets)", () => {
    expect(toTradingViewSymbol("aapl", "US", "TPEX")).toBe("AAPL");
  });
});

import { describe, expect, it } from "vitest";
import { inferTradingViewExchange, toTradingViewSymbol } from "../tradingViewSymbol";

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

  it("accepts a US ticker containing `.` and `-` (e.g. BRK.B, BF-B)", () => {
    expect(toTradingViewSymbol("brk.b", "US")).toBe("BRK.B");
    expect(toTradingViewSymbol("bf-b", "US")).toBe("BF-B");
  });
});

/**
 * Regression tests for qa-reviewer's NEEDS_CHANGES on 4938eb5 (critical
 * reflected XSS): `position/[symbol]/page.tsx`'s
 * `decodeURIComponent(params.symbol)` is attacker-controlled and previously
 * flowed unvalidated into `TradingViewChartPanel`'s `dangerouslySetInnerHTML`
 * sink through this function. These lock in the whitelist (layer 1 of the
 * two-layer fix — layer 2 is `scriptSafeJson.test.ts`'s coverage of the
 * script-context-safe serialization `TradingViewChartPanel.tsx` applies to
 * whatever this function returns).
 */
describe("toTradingViewSymbol — XSS whitelist regression (qa-reviewer NEEDS_CHANGES on 4938eb5)", () => {
  it("rejects a symbol containing a literal `</script>` fragment (TW and US)", () => {
    expect(toTradingViewSymbol("2330</script><script>alert(1)</script>", "TW")).toBeNull();
    expect(toTradingViewSymbol("AAPL</script><script>alert(1)</script>", "US")).toBeNull();
  });

  it('rejects a symbol containing a double quote (`"`)', () => {
    expect(toTradingViewSymbol('2330","evil":"1', "TW")).toBeNull();
    expect(toTradingViewSymbol('AAPL"};alert(1);//', "US")).toBeNull();
  });

  it("rejects a symbol that is `</script>` after URL-decoding (%3C%2Fscript%3E)", () => {
    // The real attack surface: `page.tsx` calls `decodeURIComponent(params.symbol)`
    // before this function ever sees the value, so the *decoded* form (what
    // this function actually receives) is what must be rejected.
    const decoded = decodeURIComponent("%3C%2Fscript%3E");
    expect(decoded).toBe("</script>");
    expect(toTradingViewSymbol(decoded, "TW")).toBeNull();
    expect(toTradingViewSymbol(decoded, "US")).toBeNull();
  });

  it("rejects other non-whitelisted characters (spaces, angle brackets, ampersand, semicolon)", () => {
    expect(toTradingViewSymbol("2330 OR 1=1", "TW")).toBeNull();
    expect(toTradingViewSymbol("<img src=x onerror=alert(1)>", "TW")).toBeNull();
    expect(toTradingViewSymbol("AAPL&x=1", "US")).toBeNull();
    expect(toTradingViewSymbol("2330;drop", "TW")).toBeNull();
  });

  it("rejects an empty symbol (whitespace-only input trims to nothing)", () => {
    expect(toTradingViewSymbol("   ", "TW")).toBeNull();
  });
});

describe("inferTradingViewExchange", () => {
  it("picks TPEX when any identifier names the TPEx chain", () => {
    expect(inferTradingViewExchange("tpex", null)).toBe("TPEX");
    expect(inferTradingViewExchange(undefined, "tpex_openapi_mainboard")).toBe("TPEX");
  });

  it("picks TWSE when an identifier names the TWSE chain", () => {
    expect(inferTradingViewExchange("twse", undefined)).toBe("TWSE");
    expect(inferTradingViewExchange("demo_synthetic", "twse_openapi_t187ap03_l")).toBe("TWSE");
  });

  it("first identifier that names an exchange wins (bars provider before directory), in both directions", () => {
    expect(inferTradingViewExchange("tpex", "twse_openapi")).toBe("TPEX");
    expect(inferTradingViewExchange("twse", "tpex_openapi")).toBe("TWSE");
  });

  it("returns undefined for chains that do not identify the exchange, keeping the TWSE default downstream", () => {
    expect(inferTradingViewExchange("finmind", "demo_synthetic")).toBeUndefined();
    expect(inferTradingViewExchange(null, undefined)).toBeUndefined();
    expect(toTradingViewSymbol("2330", "TW", inferTradingViewExchange("finmind"))).toBe("TWSE:2330");
  });
});

import { describe, expect, it } from "vitest";
import { toScriptSafeJson } from "../scriptSafeJson";

/**
 * Regression tests for qa-reviewer's NEEDS_CHANGES on 4938eb5 (critical
 * reflected XSS), layer 2 of 2: `TradingViewChartPanel.tsx` used to embed
 * plain `JSON.stringify(config)` via `dangerouslySetInnerHTML` on a
 * `<script>` element. These test the serializer itself, in isolation from
 * `toTradingViewSymbol`'s whitelist (layer 1, `tradingViewSymbol.test.ts`) —
 * defense-in-depth: even a value that reached this function unvalidated must
 * not be able to break out of the surrounding `<script>` tag.
 */
describe("toScriptSafeJson", () => {
  it("escapes a literal `</script>` fragment so it cannot close the host <script> tag", () => {
    const out = toScriptSafeJson({ symbol: "2330</script><script>alert(1)</script>" });
    expect(out).not.toContain("</script>");
    expect(out).toContain("\\u003c/script\\u003e");
  });

  it('leaves a double quote (`"`) as JSON.stringify\'s own `\\"` escape and round-trips it intact', () => {
    const input = { symbol: 'AAPL"};alert(1);//' };
    const out = toScriptSafeJson(input);
    // JSON.stringify already escapes the embedded quote to `\"` — the
    // wrapper must not defeat that, and the value must decode back unchanged.
    expect(out).toContain('\\"');
    expect(JSON.parse(out)).toEqual(input);
  });

  it("escapes a symbol that is `</script>` after URL-decoding (%3C%2Fscript%3E)", () => {
    const decoded = decodeURIComponent("%3C%2Fscript%3E");
    const out = toScriptSafeJson({ symbol: decoded });
    expect(out).not.toContain("</script>");
    expect(out).toContain("\\u003c/script\\u003e");
  });

  it("escapes `<`, `>`, and `&` throughout the serialized output, not just inside one field", () => {
    const out = toScriptSafeJson({ a: "<b>", c: "x & y" });
    expect(out).not.toMatch(/[<>&]/);
    expect(out).toContain("\\u003cb\\u003e");
    expect(out).toContain("x \\u0026 y");
  });

  it("round-trips back to the original value once parsed as JSON (widget-visible content is unchanged)", () => {
    const config = { symbol: "TWSE:2330", allow_symbol_change: false, note: "<tag> & \"quoted\"" };
    const out = toScriptSafeJson(config);
    expect(JSON.parse(out)).toEqual(config);
  });
});

/**
 * RC-738 C items 1-8 (risk-compliance verbatim review 2026-11-25, RC-730 ~ RC-739):
 * verbatim locks for the alert-event `observed` labels. Reverting any label to its old wording,
 * dropping an entry, or adding a filter makes these go red.
 */

import { readFileSync } from "node:fs";
import { join } from "node:path";
import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";
import { AlertEventList } from "../../components/PendingAlertsPanel";
import { COMPARISON_OP_OPTIONS } from "../format";
import { OBSERVED_KEY_LABELS } from "../alertObservedLabels";
import type { AlertEvent } from "../types";

const PRICE_LINE = "資料日收盤價: 605　設定的門檻: 600　幣別: TWD　資料日期（日線收盤，非即時）: 2026-11-24";
const SIGNAL_LINE =
  "判斷欄位: 14 日 RSI 最新值　該欄位數值: 28.4　比較方式: 小於（<）　比較對象數值: 30　資料日期（日線收盤，非即時）: 2026-11-24";
const LIMIT_LINE = "觸發的上限: 單一標的佔比上限、總曝險上限　觸發的上限數量: 2";

const RAW_KEYS = [
  "close",
  "threshold",
  "currency",
  "bar_as_of",
  "field",
  "value",
  "op",
  "compared_to",
  "signals_as_of",
  "violated_limit_ids",
  "violated_count",
];

function decode(text: string): string {
  return text.replace(/&lt;/g, "<").replace(/&gt;/g, ">").replace(/&quot;/g, '"').replace(/&amp;/g, "&");
}

/** Renders one event and returns the decoded observed line (the `<p>` after the message). */
function observedLine(observed: AlertEvent["observed"]): string {
  const event: AlertEvent = {
    id: 1,
    rule_id: 1,
    rule_type: "price_above",
    symbol: "2330",
    market: "TW",
    message: "m",
    observed,
    triggered_at: "2026-11-24T01:00:00Z",
    acknowledged: false,
    acknowledged_at: null,
  };
  const html = renderToStaticMarkup(
    createElement(AlertEventList, { events: [event], onAck: () => {}, ackPending: false }),
  );
  const match = html.match(/<p class="mt-1 text-xs text-neutral-500">([\s\S]*?)<\/p>/);
  expect(match).not.toBeNull();
  return decode(match![1] ?? "");
}

const PRICE = { close: 605, threshold: 600, currency: "TWD", bar_as_of: "2026-11-24" };
const SIGNAL = { field: "rsi14.last", value: 28.4, op: "lt", compared_to: 30, signals_as_of: "2026-11-24" };
const LIMIT = { violated_limit_ids: "single_position_weight、gross_exposure", violated_count: 2 };

describe("RC-738 C1-C3: approved screen strings are verbatim", () => {
  it("C1 price event", () => {
    expect(observedLine(PRICE)).toBe(PRICE_LINE);
  });
  it("C2 signal event (decoded text, `<` is escaped by the renderer)", () => {
    expect(observedLine(SIGNAL)).toBe(SIGNAL_LINE);
  });
  it("C3 risk-limit event", () => {
    expect(observedLine(LIMIT)).toBe(LIMIT_LINE);
  });
});

describe("RC-738 C4: no raw engineering strings on screen", () => {
  const lines = [observedLine(PRICE), observedLine(SIGNAL), observedLine(LIMIT)];
  it("outputs contain none of the 11 raw keys or raw values", () => {
    for (const line of lines) {
      for (const key of RAW_KEYS) expect(line).not.toContain(key);
      for (const raw of ["rsi14.last", "single_position_weight", "gross_exposure", ": lt"]) {
        expect(line).not.toContain(raw);
      }
    }
  });
  it("price event never says 最新收盤價", () => {
    expect(lines[0]).not.toContain("最新收盤價");
  });
});

describe("RC-738 C5: entry count and order follow the input", () => {
  it("each fixture keeps its entry count", () => {
    expect(observedLine(PRICE).split("　")).toHaveLength(4);
    expect(observedLine(SIGNAL).split("　")).toHaveLength(5);
    expect(observedLine(LIMIT).split("　")).toHaveLength(2);
  });
  it("a shuffled fixture keeps the shuffled order", () => {
    const line = observedLine({ bar_as_of: "2026-11-24", currency: "TWD", close: 605, threshold: 600 });
    expect(line).toBe("資料日期（日線收盤，非即時）: 2026-11-24　幣別: TWD　資料日收盤價: 605　設定的門檻: 600");
  });
});

describe("RC-738 C6: unknown keys and values fall back to the raw string", () => {
  it("unknown key", () => {
    expect(observedLine({ legacy_key: "x" })).toBe("legacy_key: x");
  });
  it("unknown op", () => {
    expect(observedLine({ op: "zz" })).toBe("比較方式: zz");
  });
  it("unknown field", () => {
    expect(observedLine({ field: "zzz.last" })).toBe("判斷欄位: zzz.last");
  });
  it("partly unknown limit ids", () => {
    expect(observedLine({ violated_limit_ids: "per_trade_loss、new_cap" })).toBe(
      "觸發的上限: 單筆最大可承受虧損、new_cap",
    );
  });
  it("null value prints a dash", () => {
    expect(observedLine({ currency: null })).toBe("幣別: —");
  });
  it("prototype names are not resolved as keys", () => {
    expect(observedLine({ constructor: "x", toString: "y" })).toBe("constructor: x　toString: y");
  });
  it("values of non-converted keys pass through even if they look like codes", () => {
    expect(observedLine({ currency: "lt" })).toBe("幣別: lt");
  });
});

describe("RC-738 C7: source has no entry filtering", () => {
  const files = ["../../components/PendingAlertsPanel.tsx", "../alertObservedLabels.ts"];
  for (const file of files) {
    it(`${file} has no filter / sort / slice call`, () => {
      const source = readFileSync(join(__dirname, file), "utf8");
      expect(source).not.toMatch(/\.(filter|sort|slice)\(/);
    });
  }
  it("key table has exactly the 11 approved keys", () => {
    expect([...OBSERVED_KEY_LABELS.keys()]).toEqual(RAW_KEYS);
  });
});

describe("RC-738 C8: all 8 operator codes map to the existing labels", () => {
  const expected: [string, string][] = [
    ["gt", "大於（>）"],
    ["gte", "大於等於（≥）"],
    ["lt", "小於（<）"],
    ["lte", "小於等於（≤）"],
    ["eq", "等於（=）"],
    ["ne", "不等於（≠）"],
    ["abs_gt", "絕對值大於（|x|>）"],
    ["abs_lt", "絕對值小於（|x|<）"],
  ];
  it("the existing option table has exactly these 8 codes", () => {
    expect(COMPARISON_OP_OPTIONS.map((o) => o.value)).toEqual(expected.map(([code]) => code));
  });
  it.each(expected)("op %s", (code, label) => {
    expect(observedLine({ op: code })).toBe(`比較方式: ${label}`);
  });
});

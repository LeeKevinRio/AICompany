import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";
import type { Bar } from "../types";
import {
  KEY_LEVELS_NO_DATA_STATEMENT,
  KEY_LEVELS_PANEL_TITLE,
  KeyLevelsPanel,
} from "../../position/[symbol]/KeyLevelsPanel";

function bars(n: number): Bar[] {
  return Array.from({ length: n }, (_, i) => ({
    date: `2026-0${1 + Math.floor(i / 28)}-${String(1 + (i % 28)).padStart(2, "0")}`,
    open: "100",
    high: "105",
    low: "95",
    close: String(100 + (i % 7)),
    volume: 1000,
    currency: "TWD",
    source: "demo",
  }));
}

describe("KeyLevelsPanel — null branch when a bar holds a non-positive value", () => {
  const cases: Array<[string, (b: Bar[]) => Bar[]]> = [
    ["close 0 on the latest bar", (b) => b.map((x, i) => (i === b.length - 1 ? { ...x, close: "0" } : x))],
    ["high -1 in the middle", (b) => b.map((x, i) => (i === 40 ? { ...x, high: "-1" } : x))],
    ["low 0 in the middle", (b) => b.map((x, i) => (i === 40 ? { ...x, low: "0" } : x))],
  ];
  for (const [name, mutate] of cases) {
    it(`${name}: renders only the title and the existing no-data sentence`, () => {
      const html = renderToStaticMarkup(
        createElement(KeyLevelsPanel, { bars: mutate(bars(80)), avgCost: 100, anchorSource: "cost" }),
      );
      expect(html).toContain(KEY_LEVELS_PANEL_TITLE);
      expect(html).toContain(KEY_LEVELS_NO_DATA_STATEMENT);
      expect(html).not.toContain("收盤 ");
      expect(html).not.toContain("價格單位");
      expect(html).not.toContain("基準價");
    });
  }
});

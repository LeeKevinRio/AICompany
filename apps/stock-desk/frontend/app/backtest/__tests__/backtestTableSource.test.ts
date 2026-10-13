/**
 * Source and rendered-class pins for the two metric tables (F11-A-57 .. A-62,
 * A-55, A-59, A-60; 風控 F11-W-9(a)(c), W-28(a)(d), W-30(a)).
 *
 * A source test only proves a declaration exists. Whether Tailwind produced CSS
 * for it and what the browser lays out is measured by qa-e2e (G1 .. G8); these
 * tests stop the declarations from drifting in the meantime.
 */

import { renderToStaticMarkup } from "react-dom/server";
import { createElement } from "react";
import { describe, expect, it } from "vitest";
import { BacktestReportView } from "../BacktestReportView";
import type { HtmlElement } from "./htmlTree";
import { ancestorsOf, classTokens, elementChildren, findAll, parseHtml, textOf } from "./htmlTree";
import { makeResponse } from "./roundTripFixtures";
import { readReportViewSource, stripComments } from "./sourceScan";

const source = readReportViewSource();
const code = stripComments(source);

const root = parseHtml(renderToStaticMarkup(createElement(BacktestReportView, { report: makeResponse() })));
const metricTables = findAll(
  root,
  (el) => el.tag === "table" && elementChildren(el).some((child) => child.tag === "colgroup"),
);

function rowsOf(table: HtmlElement): HtmlElement[] {
  const body = elementChildren(table).find((child) => child.tag === "tbody");
  if (body === undefined) throw new Error("table without tbody");
  return elementChildren(body);
}

/** The 15 pre-F-11 labels as the fixture renders them. */
const EXISTING_LABELS = [
  "期間",
  "觀測筆數",
  "起始權益",
  "結束權益",
  "總報酬率",
  "CAGR",
  "年化波動度",
  "Sharpe",
  "Sortino",
  "最大回撤",
  "<win-rate-label>",
  "<round-trips-label>",
  "獲利因子",
  "交易次數",
  "週轉率",
];

describe("A-57 / A-62: the fixed-layout table", () => {
  it("there are exactly two metric tables, one per segment, rendered by one shared component", () => {
    expect(metricTables).toHaveLength(2);
    expect(code.match(/function SegmentTable\(/g) ?? []).toHaveLength(1);
    expect(code.match(/<SegmentTable\b/g) ?? []).toHaveLength(2);
  });

  it("the <table> carries w-full, min-w-[520px], table-fixed, text-left and text-sm", () => {
    for (const table of metricTables) {
      const tokens = classTokens(table);
      for (const required of ["w-full", "min-w-[520px]", "table-fixed", "text-left", "text-sm"]) {
        expect(tokens, required).toContain(required);
      }
    }
  });

  it("the first child of <table> is the one <colgroup> with exactly three <col>", () => {
    for (const table of metricTables) {
      expect(elementChildren(table)[0]?.tag).toBe("colgroup");
      expect(findAll(table, (el) => el.tag === "colgroup")).toHaveLength(1);
      const cols = findAll(table, (el) => el.tag === "col");
      expect(cols).toHaveLength(3);
      expect(cols[0]?.attrs.class).toBe("w-[7rem] sm:w-[11rem]");
    }
  });

  it("W-30(a): the second and third <col> have no class and no style at all", () => {
    for (const table of metricTables) {
      const cols = findAll(table, (el) => el.tag === "col");
      for (const col of cols.slice(1)) {
        expect(col.attrs).toEqual({});
      }
    }
  });

  it("source: exactly one <colgroup> element and one width-bearing <col>", () => {
    expect(code.match(/<colgroup>/g) ?? []).toHaveLength(1);
    expect(code.match(/<col\b/g) ?? []).toHaveLength(3);
    expect(code).toContain('<col className="w-[7rem] sm:w-[11rem]" />');
  });

  it("the scroll container declares an inline-size container for 100cqw", () => {
    for (const table of metricTables) {
      const container = table.parent;
      if (container === null) throw new Error("table without a container");
      expect(container.tag).toBe("div");
      expect(classTokens(container)).toEqual(expect.arrayContaining(["overflow-x-auto", "@container"]));
    }
  });
});

describe("A-57(c) / W-28(a): the fifteen pre-F-11 rows keep their classes character for character", () => {
  it("every pre-F-11 <tr> and <td> has the exact pre-F-11 class string", () => {
    for (const table of metricTables) {
      const rows = rowsOf(table).filter((tr) => EXISTING_LABELS.includes(textOf(elementChildren(tr)[0] ?? "")));
      expect(rows).toHaveLength(15);
      for (const tr of rows) {
        expect(tr.attrs.class).toBe("border-t border-neutral-800");
        const cells = elementChildren(tr);
        expect(cells.map((cell) => cell.attrs.class)).toEqual([
          "px-3 py-2 text-neutral-500",
          "px-3 py-2 text-neutral-100",
          "px-3 py-2 text-neutral-300",
        ]);
        // F11-A-59: the pre-F-11 label cells are not wrapped
        const labelCell = cells[0];
        if (labelCell === undefined) throw new Error("row without a label cell");
        expect(elementChildren(labelCell)).toHaveLength(0);
      }
    }
  });

  it("the three <th> are unchanged, in the order 指標 / 策略 / Buy & Hold (W-28(d))", () => {
    for (const table of metricTables) {
      const ths = findAll(table, (el) => el.tag === "th");
      expect(ths.map(textOf)).toEqual(["指標", "策略", "Buy & Hold"]);
      for (const th of ths) {
        expect(th.attrs.class).toBe("px-3 py-2 font-medium");
        expect(th.attrs.scope).toBe("col");
      }
    }
  });

  it("W-28(d): nothing in the tables is hidden at any breakpoint or moved out of the table", () => {
    for (const table of metricTables) {
      for (const el of [table, ...findAll(table, () => true)]) {
        for (const token of classTokens(el)) {
          expect(token, `${el.tag}.${token}`).not.toMatch(/(^|:)(hidden|table-cell|invisible|sr-only)$/);
        }
        expect(el.attrs.hidden).toBeUndefined();
      }
    }
  });
});

describe("A-59 / A-60: new label cells are width-limited by a plain wrapper and nothing else", () => {
  const ADDED_LABELS = ["盈虧比", "平均獲利回合報酬率", "平均虧損回合報酬率", "最長連續虧損回合數", "在場時間比例"];

  it("only the five added data rows wrap their label, with exactly `block max-w-[8.75rem]`", () => {
    for (const table of metricTables) {
      const wrappers = findAll(table, (el) => el.tag === "span");
      expect(wrappers.map(textOf)).toEqual(ADDED_LABELS);
      for (const wrapper of wrappers) {
        expect(wrapper.attrs.class).toBe("block max-w-[8.75rem]");
        expect(wrapper.parent?.attrs.class).toBe("px-3 py-2 text-neutral-500");
      }
    }
    expect(code.match(/block max-w-\[8\.75rem\]/g) ?? []).toHaveLength(1);
  });

  it("no cell or wrapper carries min-w, w-, nowrap, truncate, line-clamp, overflow-hidden or break-keep", () => {
    const banned = /^(min-w-|w-\[|w-\d|whitespace-nowrap|truncate|line-clamp-|overflow-hidden|break-keep)/;
    for (const table of metricTables) {
      for (const el of findAll(table, (node) => ["td", "th", "span", "tr"].includes(node.tag))) {
        if (el.parent?.tag === "tr" && el.tag === "td" && el.attrs.colSpan !== undefined) continue; // definition cell
        for (const token of classTokens(el)) {
          expect(token, `${el.tag} ${el.attrs.class}`).not.toMatch(banned);
        }
      }
    }
  });

  it("the whole component source holds none of the truncating constructs", () => {
    for (const construct of [
      "whitespace-nowrap",
      "truncate",
      "line-clamp",
      "overflow-hidden",
      "break-keep",
      "max-h-",
      "text-ellipsis",
    ]) {
      expect(code, construct).not.toContain(construct);
    }
  });
});

describe("A-55 / F11-W-9: the sticky definition block", () => {
  it("sticky appears once in the source, in the one definition-cell className, with left-0 and none of the banned classes", () => {
    expect(code.match(/\bsticky\b/g) ?? []).toHaveLength(1);
    const className = code.match(/className="([^"]*\bsticky\b[^"]*)"/)?.[1];
    expect(className).toBeDefined();
    const tokens = (className ?? "").split(/\s+/);
    expect(tokens).toContain("left-0");
    expect(tokens).toContain("w-[100cqw]");
    expect(tokens).toContain("text-sm");
    for (const token of tokens) {
      expect(token).not.toMatch(
        /^(top-|bottom-|z-|overflow-hidden|truncate|line-clamp|max-h-|whitespace-nowrap|inset-|right-)/,
      );
    }
  });

  it("rendered: every sticky element is the inner block of a colSpan-3 definition cell; 4 per table", () => {
    for (const table of metricTables) {
      const sticky = findAll(table, (el) => classTokens(el).includes("sticky"));
      expect(sticky).toHaveLength(4);
      for (const block of sticky) {
        expect(block.tag).toBe("div");
        expect(classTokens(block)).toContain("left-0");
        expect(block.parent?.tag).toBe("td");
        expect(block.parent?.attrs.colSpan).toBe("3");
        expect(block.parent?.parent?.tag).toBe("tr");
      }
    }
    expect(findAll(root, (el) => classTokens(el).some((token) => token.includes("sticky")))).toHaveLength(8);
  });

  it("W-9(c): definition text is not neutral-500, 600 or 700, and is never in a tooltip, details or text-xs", () => {
    for (const table of metricTables) {
      for (const block of findAll(table, (el) => classTokens(el).includes("sticky"))) {
        const tokens = classTokens(block);
        expect(tokens.some((token) => /^text-neutral-(500|600|700)$/.test(token))).toBe(false);
        expect(tokens).not.toContain("text-xs");
        for (const el of [block, ...findAll(block, () => true), ...ancestorsOf(block)]) {
          expect(el.tag).not.toBe("details");
          expect(el.attrs.title).toBeUndefined();
          expect(classTokens(el)).not.toContain("text-xs");
        }
      }
    }
  });

  it("the other tables on the page (round-trip lists) never use sticky", () => {
    const listTables = findAll(root, (el) => el.tag === "table" && !metricTables.includes(el));
    expect(listTables.length).toBeGreaterThan(0);
    for (const table of listTables) {
      expect(findAll(table, (el) => classTokens(el).includes("sticky"))).toHaveLength(0);
    }
  });
});

/**
 * Render-level guards for F-11's page content (PRD AC-1, 2, 6, 7, 8, 10, 11, 16,
 * 17, 20, 21, 22, 23, 25, 27; 風控 F11-W-15, W-20, W-24, W-25, W-26; F11-A-46).
 *
 * Everything is asserted against the markup `BacktestReportView` renders from a
 * hand-built response. The page holds no copy of its own for F-11: each sentence
 * below is typed in `roundTripFixtures.ts` as the backend would send it, and the
 * tests check it arrives verbatim, in the right place, in the right state.
 */

import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";
import type { BacktestResponse, RoundTripEmptyState } from "../../lib/types";
import { BacktestReportView, RoundTripFullListView } from "../BacktestReportView";
import type { HtmlElement } from "./htmlTree";
import {
  ancestorsOf,
  classTokens,
  elementChildren,
  findAll,
  findOne,
  nextElementSibling,
  parseHtml,
  textOf,
} from "./htmlTree";
import {
  EXCLUDED_HEADING,
  IN_SAMPLE_TITLE,
  L02N,
  L09,
  L10,
  L11A,
  L11N,
  L12,
  L13,
  L14_EXCLUDED_ONLY,
  L14_NO_POSITION,
  L18A,
  L18B,
  LAST_BAR_DATE,
  OUT_OF_SAMPLE_TITLE,
  POINTER_IN_SAMPLE,
  POINTER_OUT_OF_SAMPLE,
  detailLabels,
  makeDetail,
  makeEmptyDetail,
  makeResponse,
  makeRows,
} from "./roundTripFixtures";
import { requireDetail } from "./sourceScan";

function markupOf(report: BacktestResponse): string {
  return renderToStaticMarkup(createElement(BacktestReportView, { report }));
}

function treeOf(report: BacktestResponse): HtmlElement {
  return parseHtml(markupOf(report));
}

function metricTables(root: HtmlElement): HtmlElement[] {
  return findAll(root, (el) => el.tag === "table" && elementChildren(el).some((child) => child.tag === "colgroup"));
}

/** Label cell text -> [strategy cell, Buy & Hold cell] of one metric table (definition rows skipped). */
function cellsByLabel(table: HtmlElement): Map<string, [string, string]> {
  const body = elementChildren(table).find((child) => child.tag === "tbody");
  if (body === undefined) throw new Error("table without tbody");
  const rows = new Map<string, [string, string]>();
  for (const tr of elementChildren(body)) {
    const cells = elementChildren(tr);
    if (cells.length !== 3) continue;
    const [label, strategy, peer] = cells;
    if (label === undefined || strategy === undefined || peer === undefined) continue;
    rows.set(textOf(label), [textOf(strategy), textOf(peer)]);
  }
  return rows;
}

function inSampleTable(root: HtmlElement): HtmlElement {
  const [first] = metricTables(root);
  if (first === undefined) throw new Error("no metric table");
  return first;
}

function outOfSampleTable(root: HtmlElement): HtmlElement {
  const second = metricTables(root)[1];
  if (second === undefined) throw new Error("no second metric table");
  return second;
}

function subBlock(root: HtmlElement, title: string): HtmlElement {
  const heading = findOne(root, (el) => el.tag === "h3" && textOf(el) === title, `h3 "${title}"`);
  if (heading.parent === null) throw new Error("heading without parent");
  return heading.parent;
}

function isInsideScrollContainerOrCollapsed(el: HtmlElement): boolean {
  return ancestorsOf(el).some((ancestor) => classTokens(ancestor).includes("overflow-x-auto") || ancestor.attrs.hidden !== undefined);
}

describe("A-46: every new row renders a real number from a non-null value", () => {
  const root = treeOf(makeResponse());
  const strategyRows = cellsByLabel(inSampleTable(root));

  it("shows each new row's strategy value", () => {
    expect(strategyRows.get("盈虧比")?.[0]).toBe("1.37");
    expect(strategyRows.get("平均獲利回合報酬率")?.[0]).toBe("2.13%（18 筆獲利回合）");
    expect(strategyRows.get("平均虧損回合報酬率")?.[0]).toBe("-1.56%（16 筆虧損回合）");
    expect(strategyRows.get("最長連續虧損回合數")?.[0]).toBe("3（2025-02-03 至 2025-03-10）");
    expect(strategyRows.get("在場時間比例")?.[0]).toBe("42.13%");
  });

  it("the profit factor row still shows its existing value beside the new rows", () => {
    expect(strategyRows.get("獲利因子")?.[0]).toBe("1.31");
  });
});

describe("F11-W-20 / 條件 L-05: the mean cells are formatPercent(value) + the backend suffix, nothing between", () => {
  it("non-null: the cell equals the formatted value glued to the suffix", () => {
    const report = makeResponse({ inSample: makeDetail({ mean_winning_return: 0.0213, mean_losing_return: -0.0156 }) });
    const detail = requireDetail(report);
    const row = cellsByLabel(inSampleTable(treeOf(report)));
    expect(row.get("平均獲利回合報酬率")?.[0]).toBe(`2.13%${detail.labels.in_sample.mean_winning_return_suffix}`);
    expect(row.get("平均虧損回合報酬率")?.[0]).toBe(`-1.56%${detail.labels.in_sample.mean_losing_return_suffix}`);
  });

  it("null side: the whole cell is 「—」 plus the suffix, i.e. L-05c/d filled with a dash and a zero", () => {
    const report = makeResponse({
      inSample: makeDetail({
        mean_winning_return: null,
        num_winning_round_trips: 0,
        mean_losing_return: null,
        num_losing_round_trips: 0,
      }),
    });
    const row = cellsByLabel(inSampleTable(treeOf(report)));
    expect(row.get("平均獲利回合報酬率")?.[0]).toBe("—（0 筆獲利回合）");
    expect(row.get("平均虧損回合報酬率")?.[0]).toBe("—（0 筆虧損回合）");
    // L-05e is the same template as L-05c/d with those two values
    const template = (side: string, count: string) => "{value}（{n} 筆".replace("{value}", "—").replace("{n}", count) + `${side}回合）`;
    expect(row.get("平均獲利回合報酬率")?.[0]).toBe(template("獲利", "0"));
    expect(row.get("平均虧損回合報酬率")?.[0]).toBe(template("虧損", "0"));
  });
});

describe("AC-21 / F11-R-7: the three strategy-column states stay apart (no ?? 0 flattening)", () => {
  function states(overrides: Parameters<typeof makeDetail>[0], metrics: NonNullable<Parameters<typeof makeResponse>[0]>["inSampleMetrics"]) {
    const report = makeResponse({ inSample: makeDetail(overrides), inSampleMetrics: metrics });
    return cellsByLabel(inSampleTable(treeOf(report)));
  }

  it("(a) n = 0: means, payoff ratio, profit factor and streak are all 「—」, the count row says 0", () => {
    const report = makeResponse({
      inSample: makeEmptyDetail("no_position"),
      inSampleMetrics: { num_round_trips: 0, profit_factor: null, round_trip_payoff_ratio: null, win_rate: null },
    });
    const rows = cellsByLabel(inSampleTable(treeOf(report)));
    expect(rows.get("<round-trips-label>")?.[0]).toBe("0");
    expect(rows.get("<win-rate-label>")?.[0]).toBe("—");
    expect(rows.get("獲利因子")?.[0]).toBe("—");
    expect(rows.get("盈虧比")?.[0]).toBe("—");
    expect(rows.get("平均獲利回合報酬率")?.[0]).toBe("—（0 筆獲利回合）");
    expect(rows.get("平均虧損回合報酬率")?.[0]).toBe("—（0 筆虧損回合）");
    expect(rows.get("最長連續虧損回合數")?.[0]).toBe("—");
  });

  it("(b) n > 0 and no losing round trip: streak is 0, loss mean / payoff ratio / profit factor are 「—」", () => {
    const rows = states(
      {
        num_winning_round_trips: 34,
        num_losing_round_trips: 0,
        mean_losing_return: null,
        longest_losing_streak: { length: 0, start_date: null, end_date: null },
      },
      { profit_factor: null, round_trip_payoff_ratio: null, win_rate: 1 },
    );
    expect(rows.get("最長連續虧損回合數")?.[0]).toBe("0");
    expect(rows.get("平均虧損回合報酬率")?.[0]).toBe("—（0 筆虧損回合）");
    expect(rows.get("平均獲利回合報酬率")?.[0]).toBe("2.13%（34 筆獲利回合）");
    expect(rows.get("盈虧比")?.[0]).toBe("—");
    expect(rows.get("獲利因子")?.[0]).toBe("—");
  });

  it("(c) n > 0 and only losing round trips: profit factor is 0.00 (shown, not dashed), win mean and payoff ratio are 「—」", () => {
    const rows = states(
      {
        num_winning_round_trips: 0,
        num_losing_round_trips: 34,
        mean_winning_return: null,
        longest_losing_streak: { length: 34, start_date: "2025-01-02", end_date: "2025-12-30" },
      },
      { profit_factor: 0, round_trip_payoff_ratio: null, win_rate: 0 },
    );
    expect(rows.get("獲利因子")?.[0]).toBe("0.00");
    expect(rows.get("平均獲利回合報酬率")?.[0]).toBe("—（0 筆獲利回合）");
    expect(rows.get("盈虧比")?.[0]).toBe("—");
    expect(rows.get("最長連續虧損回合數")?.[0]).toBe("34（2025-01-02 至 2025-12-30）");
  });

  it("a zero payoff ratio is shown as a number, never dashed", () => {
    const rows = states({}, { round_trip_payoff_ratio: 0 });
    expect(rows.get("盈虧比")?.[0]).toBe("0.00");
  });
});

describe("AC-20: Buy & Hold column of the F-11 rows", () => {
  it("round-trip-layer rows are always 「—」; the in-market row shows the backend's definition value", () => {
    const rows = cellsByLabel(inSampleTable(treeOf(makeResponse())));
    for (const label of ["盈虧比", "平均獲利回合報酬率", "平均虧損回合報酬率", "最長連續虧損回合數"]) {
      expect(rows.get(label)?.[1], label).toBe("—");
    }
    expect(rows.get("在場時間比例")?.[1]).toBe("100.00%");
  });

  it("an absent Buy & Hold path shows 「—」, never a hard-coded 100%", () => {
    const report = makeResponse({ inSample: makeDetail({ buy_and_hold_in_market_ratio: null }) });
    const rows = cellsByLabel(inSampleTable(treeOf(report)));
    expect(rows.get("在場時間比例")?.[1]).toBe("—");
  });

  it("the strategy in-market cell is 「—」 when the backend cannot compute it (AC-17 a)", () => {
    const report = makeResponse({
      inSample: makeDetail({ in_market_ratio: null, buy_and_hold_in_market_ratio: null }),
    });
    const rows = cellsByLabel(inSampleTable(treeOf(report)));
    expect(rows.get("在場時間比例")).toEqual(["—", "—"]);
  });

  it("a zero in-market share is shown as 0.00%, not dashed", () => {
    const report = makeResponse({ inSample: makeDetail({ in_market_ratio: 0 }) });
    expect(cellsByLabel(inSampleTable(treeOf(report))).get("在場時間比例")?.[0]).toBe("0.00%");
  });
});

describe("F11-W-15: realized P&L cells carry the currency prefix", () => {
  const pnlCells = (report: BacktestResponse, title: string): string[] => {
    const block = subBlock(treeOf(report), title);
    return findAll(block, (el) => el.tag === "tr")
      .map((tr) => elementChildren(tr))
      .filter((cells) => cells.length === 5 && cells[0]?.tag === "td")
      .map((cells) => textOf(cells[4] as HtmlElement));
  };

  it("TW market: both the lowest list and the full list use NT$", () => {
    const cells = pnlCells(makeResponse({ market: "TW" }), IN_SAMPLE_TITLE);
    expect(cells).toHaveLength(5 + 34);
    for (const cell of cells) expect(cell).toMatch(/^NT\$-?[\d,]+\.\d{2}$/);
    expect(cells[0]).toBe("NT$10,250.50");
  });

  it("US market: US$", () => {
    const cells = pnlCells(makeResponse({ market: "US" }), OUT_OF_SAMPLE_TITLE);
    for (const cell of cells) expect(cell).toMatch(/^US\$-?[\d,]+\.\d{2}$/);
  });

  it("negative P&L keeps its sign after the prefix and carries no colour class", () => {
    const rows = makeRows(2);
    const report = makeResponse({
      inSample: makeDetail({ round_trips: rows, lowest_return_round_trips: rows }),
    });
    const block = subBlock(treeOf(report), IN_SAMPLE_TITLE);
    const cells = findAll(block, (el) => el.tag === "td").filter((td) => textOf(td).includes("NT$"));
    expect(cells.map(textOf)).toContain("NT$-10,561.75");
    for (const cell of cells) {
      expect(classTokens(cell)).toEqual(["px-3", "py-2", "text-neutral-100"]);
    }
  });
});

describe("F11-W-24 (b): L-06p renders exactly the approved text per segment", () => {
  const root = treeOf(makeResponse());

  function pointerParagraph(table: HtmlElement): string {
    const blocks = findAll(table, (el) => classTokens(el).includes("sticky"));
    const payoff = blocks.find((block) => textOf(block).startsWith("盈虧比＝"));
    if (payoff === undefined) throw new Error("payoff definition missing");
    const paragraphs = elementChildren(payoff).map(textOf);
    expect(paragraphs).toHaveLength(2);
    return paragraphs[1] ?? "";
  }

  it("in-sample: the pointer is the in-sample text, with the in-sample L-01 and not the out-of-sample one", () => {
    const text = pointerParagraph(inSampleTable(root));
    expect(text).toBe(POINTER_IN_SAMPLE);
    expect(text).toContain(IN_SAMPLE_TITLE);
    expect(text).not.toContain(OUT_OF_SAMPLE_TITLE);
    expect(text).toContain(EXCLUDED_HEADING);
    expect(text).not.toMatch(/[{}]/);
  });

  it("out-of-sample: likewise", () => {
    const text = pointerParagraph(outOfSampleTable(root));
    expect(text).toBe(POINTER_OUT_OF_SAMPLE);
    expect(text).toContain(OUT_OF_SAMPLE_TITLE);
    expect(text).not.toContain(IN_SAMPLE_TITLE);
    expect(text).not.toMatch(/[{}]/);
  });

  it("the pointer sits in the same cell as L-06d, after it, with the same size and colour; no row of its own", () => {
    const table = inSampleTable(root);
    const blocks = findAll(table, (el) => classTokens(el).includes("sticky"));
    const payoff = blocks.find((block) => textOf(block).startsWith("盈虧比＝"));
    if (payoff === undefined) throw new Error("payoff definition missing");
    const [definition, pointer] = elementChildren(payoff);
    expect(textOf(definition ?? "")).toBe(requireDetail(makeResponse()).labels.payoff_ratio_definition);
    expect(pointer?.tag).toBe("p");
    expect(pointer?.attrs.class).toBe(definition?.attrs.class);
    // no row in the table contains the pointer apart from that cell
    const rowsWithPointer = findAll(table, (el) => el.tag === "tr" && textOf(el).includes("被排除的回合數與說明"));
    expect(rowsWithPointer).toHaveLength(1);
    // one pointer per table
    expect(textOf(table).split("被排除的回合數與說明").length - 1).toBe(1);
  });
});

describe("F11-W-25: L-06p and the L-11 block go in together, with whole-number counts", () => {
  type Case = [string, BacktestResponse];
  const emptyCodes: RoundTripEmptyState[] = ["no_position", "excluded_only"];
  const cases: Case[] = [
    ["n > 0, tail", makeResponse({ withTail: true })],
    ["n > 0, no tail", makeResponse({ withTail: false })],
    ["n = 0 no_position, both segments", makeResponse({ inSample: makeEmptyDetail("no_position"), outOfSample: makeEmptyDetail("no_position") })],
    ["n = 0 excluded_only, both segments", makeResponse({ inSample: makeEmptyDetail("excluded_only"), outOfSample: makeEmptyDetail("excluded_only") })],
    [
      "excluded_only with zero in-market intervals (AC-10 c/d)",
      makeResponse({
        inSample: makeEmptyDetail("excluded_only", { in_market_ratio: 0, excluded_boundary_trips: 1 }),
        outOfSample: makeEmptyDetail("excluded_only", { in_market_ratio: 0, excluded_boundary_trips: 0, open_trip_at_end: 1 }),
      }),
    ],
    ["mixed", makeResponse({ inSample: makeEmptyDetail(emptyCodes[0] ?? "no_position"), withTail: false })],
  ];

  it.each(cases)("%s", (_name, report) => {
    const root = treeOf(report);
    const detail = requireDetail(report);
    for (const [table, segment, title] of [
      [inSampleTable(root), detail.in_sample, detail.labels.in_sample.detail_title],
      [outOfSampleTable(root), detail.out_of_sample, detail.labels.out_of_sample.detail_title],
    ] as const) {
      const pointer = textOf(table).includes("被排除的回合數與說明");
      const block = subBlock(root, title);
      const heading = findAll(block, (el) => el.tag === "h4" && textOf(el) === EXCLUDED_HEADING);
      expect(pointer).toBe(true);
      expect(heading).toHaveLength(1);
      const counts = findAll(block, (el) => el.tag === "dd").map(textOf);
      expect(counts).toEqual([
        segment.excluded_boundary_trips.toLocaleString("zh-Hant-TW"),
        segment.open_trip_at_end.toLocaleString("zh-Hant-TW"),
      ]);
      for (const count of counts) expect(count).toMatch(/^\d[\d,]*$/);
      expect(textOf(block)).toContain(L11A);
      expect(textOf(block)).toContain(L11N);
    }
  });

  it("a missing count is a data-contract error: the page throws instead of printing 「—」", () => {
    const broken: BacktestResponse = JSON.parse(JSON.stringify(makeResponse()));
    if (broken.round_trip_detail === null) throw new Error("fixture");
    Object.assign(broken.round_trip_detail.in_sample, { excluded_boundary_trips: null });
    expect(() => markupOf(broken)).toThrow(/whole-number count/);

    const missing: BacktestResponse = JSON.parse(JSON.stringify(makeResponse()));
    if (missing.round_trip_detail === null) throw new Error("fixture");
    Reflect.deleteProperty(missing.round_trip_detail.out_of_sample, "open_trip_at_end");
    expect(() => markupOf(missing)).toThrow(/whole-number count/);
  });

  it("a successful report without round_trip_detail throws rather than rendering a table without its definitions", () => {
    const broken: BacktestResponse = { ...makeResponse(), round_trip_detail: null };
    expect(() => markupOf(broken)).toThrow(/round_trip_detail/);
  });

  it("the two exclusion counts are shown separately, with no total and no derived row (KT-R-8)", () => {
    const root = treeOf(makeResponse());
    for (const title of [IN_SAMPLE_TITLE, OUT_OF_SAMPLE_TITLE]) {
      const block = subBlock(root, title);
      expect(findAll(block, (el) => el.tag === "dd")).toHaveLength(2);
      expect(findAll(block, (el) => el.tag === "dt")).toHaveLength(2);
    }
  });
});

describe("F11-W-26 / AC-16 (g): L-11h is in the sub-block, outside the collapsed area and every scroll container", () => {
  const root = treeOf(makeResponse());

  it.each([IN_SAMPLE_TITLE, OUT_OF_SAMPLE_TITLE])("%s", (title) => {
    const block = subBlock(root, title);
    expect(block.tag).toBe("section");
    const heading = findOne(block, (el) => el.tag === "h4" && textOf(el) === EXCLUDED_HEADING, "L-11h");
    expect(ancestorsOf(heading)).toContain(block);
    expect(isInsideScrollContainerOrCollapsed(heading)).toBe(false);

    // the region the L-16 control owns
    const button = findOne(block, (el) => el.tag === "button", "L-16 control");
    const panel = findOne(block, (el) => el.attrs.id === button.attrs["aria-controls"], "controlled panel");
    expect(findAll(panel, (el) => el === heading)).toHaveLength(0);

    // so is every other disclosure sentence of the block
    for (const sentence of [L13, L12, L11A, L11N]) {
      const holder = findAll(block, (el) => ["p", "dt"].includes(el.tag) && textOf(el).includes(sentence.slice(0, 15)));
      expect(holder.length, sentence).toBeGreaterThan(0);
      for (const element of holder) expect(isInsideScrollContainerOrCollapsed(element)).toBe(false);
    }
  });

  it("L-11 is not inside either metric table", () => {
    for (const table of metricTables(root)) {
      expect(textOf(table)).not.toContain(EXCLUDED_HEADING.concat("\u0000"));
      expect(findAll(table, (el) => el.tag === "h4")).toHaveLength(0);
      expect(findAll(table, (el) => el.tag === "dl")).toHaveLength(0);
    }
  });
});

describe("AC-7 / AC-8: L-09 follows the backend flag alone; L-10 is on every segment", () => {
  function l09Count(report: BacktestResponse): number {
    return markupOf(report).split(L09).length - 1;
  }

  it("L-09 renders once per flagged segment, and not for an unflagged one", () => {
    expect(l09Count(makeResponse())).toBe(0);
    expect(l09Count(makeResponse({ inSample: makeDetail({ below_display_minimum: true }) }))).toBe(1);
    expect(
      l09Count(
        makeResponse({
          inSample: makeDetail({ below_display_minimum: true }),
          outOfSample: makeDetail({ below_display_minimum: true }),
        }),
      ),
    ).toBe(2);
  });

  it("the flag, not the count, decides: 29 rows unflagged show nothing, 100 rows flagged show it", () => {
    expect(l09Count(makeResponse({ outOfSample: makeDetail({ round_trips: makeRows(29), below_display_minimum: false }) }))).toBe(0);
    expect(l09Count(makeResponse({ outOfSample: makeDetail({ round_trips: makeRows(100), below_display_minimum: true }) }))).toBe(1);
  });

  it("L-09 sits in the segment's section directly after its title, before L-10 and the table", () => {
    const root = treeOf(makeResponse({ outOfSample: makeDetail({ below_display_minimum: true }) }));
    const title = findOne(root, (el) => el.tag === "h3" && textOf(el).startsWith("樣本外（"), "out-of-sample title");
    const siblings = elementChildren(title.parent as HtmlElement);
    expect(siblings.slice(0, 4).map((el) => el.tag)).toEqual(["h3", "p", "p", "div"]);
    expect(textOf(siblings[1] as HtmlElement)).toBe(L09);
    expect(textOf(siblings[2] as HtmlElement)).toBe(L10);
    expect(classTokens(siblings[1] as HtmlElement)).toContain("text-sm");
    expect(classTokens(siblings[1] as HtmlElement).join(" ")).not.toMatch(/red|amber|rose/);
  });

  it("L-10 renders on every segment whatever its count, including n = 0 and n = 1", () => {
    for (const detail of [
      makeEmptyDetail("no_position"),
      makeDetail({ round_trips: makeRows(1), below_display_minimum: true }),
      makeDetail({ round_trips: makeRows(30), below_display_minimum: false }),
      makeDetail({ round_trips: makeRows(300), below_display_minimum: false }),
    ]) {
      const markup = markupOf(makeResponse({ inSample: detail, outOfSample: detail }));
      expect(markup.split(L10).length - 1).toBe(2);
    }
  });

  it("the only thing that changes with the flag is the L-09 paragraph itself", () => {
    const flagged = markupOf(makeResponse({ inSample: makeDetail({ below_display_minimum: true }) }));
    const plain = markupOf(makeResponse({ inSample: makeDetail({ below_display_minimum: false }) }));
    const l09Paragraph = `<p class="mt-2 rounded-md border border-neutral-700 bg-neutral-900/60 px-4 py-2 text-sm text-neutral-300">${L09}</p>`;
    expect(flagged).toContain(l09Paragraph);
    expect(flagged.replace(l09Paragraph, "")).toBe(plain);
  });

  it("L-09 is not inside a scroll container or a collapsed area", () => {
    const root = treeOf(makeResponse({ inSample: makeDetail({ below_display_minimum: true }) }));
    const holder = findOne(root, (el) => el.tag === "p" && textOf(el) === L09, "L-09");
    expect(isInsideScrollContainerOrCollapsed(holder)).toBe(false);
    const reminder = findAll(root, (el) => el.tag === "p" && textOf(el) === L10);
    for (const element of reminder) expect(isInsideScrollContainerOrCollapsed(element)).toBe(false);
  });
});

describe("AC-10 / F11-A-23: the empty state follows the backend code, never a count", () => {
  it.each<[RoundTripEmptyState, string]>([
    ["no_position", L14_NO_POSITION],
    ["excluded_only", L14_EXCLUDED_ONLY],
  ])("%s shows its sentence in place of the list, with no control", (code, sentence) => {
    const report = makeResponse({ outOfSample: makeEmptyDetail(code) });
    const block = subBlock(treeOf(report), OUT_OF_SAMPLE_TITLE);
    const holder = findAll(block, (el) => el.tag === "p" && textOf(el) === sentence);
    expect(holder).toHaveLength(1);
    expect(findAll(block, (el) => el.tag === "button")).toHaveLength(0);
    expect(findAll(block, (el) => el.tag === "table")).toHaveLength(0);
    expect(findAll(block, (el) => el.tag === "h4").map(textOf)).toEqual([EXCLUDED_HEADING]);
    const other = code === "no_position" ? L14_EXCLUDED_ONLY : L14_NO_POSITION;
    expect(textOf(block)).not.toContain(other);
  });

  it("a contradictory payload proves the code decides: no_position text even with exclusions counted", () => {
    const report = makeResponse({
      outOfSample: makeEmptyDetail("no_position", { excluded_boundary_trips: 3, open_trip_at_end: 1 }),
    });
    const text = textOf(subBlock(treeOf(report), OUT_OF_SAMPLE_TITLE));
    expect(text).toContain(L14_NO_POSITION);
    expect(text).not.toContain(L14_EXCLUDED_ONLY);
  });

  it("a null code with a zero count still renders the list and the control (no count comparison)", () => {
    const report = makeResponse({
      outOfSample: makeDetail({ num_round_trips: 0, empty_state: null, round_trips: makeRows(2), lowest_return_round_trips: makeRows(2) }),
    });
    const block = subBlock(treeOf(report), OUT_OF_SAMPLE_TITLE);
    expect(findAll(block, (el) => el.tag === "button")).toHaveLength(1);
    expect(textOf(block)).not.toContain(L14_NO_POSITION);
  });

  it("the other metric rows still render beside an empty segment, and L-09 / L-10 still appear", () => {
    const report = makeResponse({ outOfSample: makeEmptyDetail("excluded_only") });
    const markup = markupOf(report);
    expect(markup).toContain(L09);
    expect(markup).toContain(L10);
  });
});

describe("AC-22: the full list starts collapsed in every state, labelled with the backend's n", () => {
  const states: Array<[string, ReturnType<typeof makeDetail>]> = [
    ["n = 1", makeDetail({ round_trips: makeRows(1), below_display_minimum: true })],
    ["n = 29", makeDetail({ round_trips: makeRows(29), below_display_minimum: true })],
    ["n = 30", makeDetail({ round_trips: makeRows(30) })],
    ["n = 300", makeDetail({ round_trips: makeRows(300) })],
    ["all winners", makeDetail({ num_losing_round_trips: 0, mean_losing_return: null })],
    ["all losers", makeDetail({ num_winning_round_trips: 0, mean_winning_return: null })],
  ];

  it.each(states)("%s: collapsed, 展開 label, panel hidden", (_name, detail) => {
    const report = makeResponse({ inSample: detail, outOfSample: detail });
    const root = treeOf(report);
    const labels = requireDetail(report).labels;
    for (const [title, segmentLabels] of [
      [IN_SAMPLE_TITLE, labels.in_sample],
      [OUT_OF_SAMPLE_TITLE, labels.out_of_sample],
    ] as const) {
      const block = subBlock(root, title);
      const button = findOne(block, (el) => el.tag === "button", "L-16 control");
      expect(button.attrs["aria-expanded"]).toBe("false");
      expect(button.attrs.type).toBe("button");
      expect(textOf(button)).toBe(segmentLabels.expand_control);
      expect(button.attrs["aria-label"]).toBe(segmentLabels.expand_control_aria);
      const panel = findOne(block, (el) => el.attrs.id === button.attrs["aria-controls"], "panel");
      expect(panel.attrs.hidden).toBeDefined();
    }
  });

  it("the control's count is the backend's n, not the number of rows the page was handed", () => {
    const detail = makeDetail({ round_trips: makeRows(3), num_round_trips: 999 });
    const labels = detailLabels(detail, detail, L18B);
    const report = makeResponse({ inSample: detail });
    const tampered: BacktestResponse = {
      ...report,
      round_trip_detail: report.round_trip_detail && {
        ...report.round_trip_detail,
        labels: { ...labels },
      },
    };
    const block = subBlock(treeOf(tampered), IN_SAMPLE_TITLE);
    const button = findOne(block, (el) => el.tag === "button", "control");
    expect(textOf(button)).toBe("展開全部 999 筆完整回合明細");
    expect(button.attrs["aria-label"]).toBe("樣本內：展開全部 999 筆完整回合明細");
  });

  it("the control has the interactive states: focus-visible, hover and active classes, a 44px target, a type", () => {
    const block = subBlock(treeOf(makeResponse()), IN_SAMPLE_TITLE);
    const tokens = classTokens(findOne(block, (el) => el.tag === "button", "control"));
    for (const token of ["hover:bg-neutral-800", "focus-visible:outline-2", "focus-visible:outline-offset-2", "active:bg-neutral-700", "min-h-11"]) {
      expect(tokens, token).toContain(token);
    }
    expect(tokens.some((token) => token.startsWith("focus-visible:outline-") && token !== "focus-visible:outline-2" && token !== "focus-visible:outline-offset-2")).toBe(true);
  });

  it("expanded view: collapse label, aria-expanded true, panel visible, rows in the order received", () => {
    const rows = makeRows(4).reverse();
    const labels = requireDetail(makeResponse()).labels;
    const html = renderToStaticMarkup(
      createElement(RoundTripFullListView, {
        expanded: true,
        onToggle: () => undefined,
        panelId: "panel-x",
        rows,
        labels,
        segmentLabels: labels.in_sample,
        currency: "TWD",
      }),
    );
    const root = parseHtml(html);
    const button = findOne(root, (el) => el.tag === "button", "control");
    expect(button.attrs["aria-expanded"]).toBe("true");
    expect(textOf(button)).toBe(labels.in_sample.collapse_control);
    expect(button.attrs["aria-label"]).toBe(labels.in_sample.collapse_control_aria);
    const panel = findOne(root, (el) => el.attrs.id === "panel-x", "panel");
    expect(panel.attrs.hidden).toBeUndefined();
    const dates = findAll(panel, (el) => el.tag === "tbody")
      .flatMap((body) => elementChildren(body))
      .map((tr) => textOf(elementChildren(tr)[0] ?? ""));
    expect(dates).toEqual(rows.map((row) => row.entry_date));
  });
});

describe("AC-1 / AC-2 / AC-3: the lists render what the backend sent, as sent", () => {
  it("lowest list: L-03 heading, L-02 headers, L-02n, rows in received order, no rank labels", () => {
    const received = makeRows(5).reverse();
    const report = makeResponse({ outOfSample: makeDetail({ lowest_return_round_trips: received }) });
    const detail = requireDetail(report);
    const block = subBlock(treeOf(report), OUT_OF_SAMPLE_TITLE);
    const headings = findAll(block, (el) => el.tag === "h4").map(textOf);
    expect(headings).toEqual([EXCLUDED_HEADING, detail.labels.out_of_sample.lowest_returns_heading]);
    expect(detail.labels.out_of_sample.lowest_returns_heading).toBe(
      "回合報酬率最低的幾筆（由低到高排列）：列出 5 筆／共 34 筆",
    );
    expect(textOf(block)).toContain(L02N);
    const tables = findAll(block, (el) => el.tag === "table");
    expect(tables).toHaveLength(2);
    const firstTable = tables[0] as HtmlElement;
    expect(findAll(firstTable, (el) => el.tag === "th").map(textOf)).toEqual([
      "進場日",
      "出場日",
      "持有日數（日線根數）",
      "回合報酬率（相對進場前權益）",
      "已實現損益",
    ]);
    const body = findOne(firstTable, (el) => el.tag === "tbody", "tbody");
    expect(elementChildren(body).map((tr) => textOf(elementChildren(tr)[0] ?? ""))).toEqual(
      received.map((row) => row.entry_date),
    );
    expect(textOf(firstTable)).not.toMatch(/第\s*\d|名次|#\d/);
  });

  it("each row has exactly five cells: entry, exit, bars, return, P&L", () => {
    const rows = makeRows(2);
    const report = makeResponse({ inSample: makeDetail({ round_trips: rows, lowest_return_round_trips: rows }) });
    const block = subBlock(treeOf(report), IN_SAMPLE_TITLE);
    const first = findAll(block, (el) => el.tag === "tbody")[0];
    const row = elementChildren(first as HtmlElement)[0];
    expect(elementChildren(row as HtmlElement).map(textOf)).toEqual([
      rows[0]?.entry_date,
      rows[0]?.exit_date,
      "2",
      "1.10%",
      "NT$10,250.50",
    ]);
  });

  it("three round trips that are all winners are listed under the same neutral heading (AC-3)", () => {
    const rows = makeRows(3).map((row) => ({ ...row, return_on_entry_equity: 0.02, realized_pnl: 5000 }));
    const report = makeResponse({
      outOfSample: makeDetail({ round_trips: rows, lowest_return_round_trips: rows }),
    });
    const text = textOf(subBlock(treeOf(report), OUT_OF_SAMPLE_TITLE));
    expect(text).toContain("列出 3 筆／共 3 筆");
    expect(text).not.toMatch(/虧損|最差|最壞/);
  });
});

describe("AC-23: sub-block order and the 「資料截至」 line", () => {
  it("title -> L-13 -> source/as-of -> L-12 -> L-11 -> lowest -> full list", () => {
    const block = subBlock(treeOf(makeResponse()), IN_SAMPLE_TITLE);
    const children = elementChildren(block);
    expect(children.map((el) => el.tag)).toEqual(["h3", "p", "p", "p", "div", "div", "div"]);
    expect(textOf(children[0] as HtmlElement)).toBe(IN_SAMPLE_TITLE);
    expect(textOf(children[1] as HtmlElement)).toBe(L13);
    expect(textOf(children[2] as HtmlElement)).toBe(`來源：twse｜資料截至 ${LAST_BAR_DATE}`);
    expect(textOf(children[3] as HtmlElement)).toBe(L12);
    expect(textOf(findOne(children[4] as HtmlElement, (el) => el.tag === "h4", "L-11h"))).toBe(EXCLUDED_HEADING);
    expect(textOf(findOne(children[5] as HtmlElement, (el) => el.tag === "h4", "L-03"))).toContain("回合報酬率最低的幾筆");
    expect(findAll(children[6] as HtmlElement, (el) => el.tag === "button")).toHaveLength(1);
  });

  it("L-13 and L-12 are text-sm and not neutral-500/600/700", () => {
    const block = subBlock(treeOf(makeResponse()), IN_SAMPLE_TITLE);
    for (const sentence of [L13, L12]) {
      const holder = findOne(block, (el) => el.tag === "p" && textOf(el) === sentence, sentence.slice(0, 8));
      const tokens = classTokens(holder);
      expect(tokens).toContain("text-sm");
      expect(tokens.some((token) => /^text-neutral-(500|600|700)$/.test(token))).toBe(false);
    }
  });

  it("the L-11b label is the backend's text (its date is not recomputed from the page header)", () => {
    const report = makeResponse();
    const detail = requireDetail(report);
    const tampered: BacktestResponse = {
      ...report,
      round_trip_detail: {
        ...detail,
        labels: { ...detail.labels, excluded_open_trips: "OPEN-LABEL-FROM-BACKEND" },
      },
    };
    const block = subBlock(treeOf(tampered), IN_SAMPLE_TITLE);
    expect(findAll(block, (el) => el.tag === "dt").map(textOf)).toContain("OPEN-LABEL-FROM-BACKEND");
  });
});

describe("AC-25 / F11-W-14: the tail disclosure", () => {
  it("r > 0 shows L-18a once; r = 0 shows L-18b once and no tail sentence", () => {
    const withTail = markupOf(makeResponse({ withTail: true }));
    expect(withTail.split(L18A).length - 1).toBe(1);
    expect(withTail).not.toContain(L18B);
    const without = markupOf(makeResponse({ withTail: false }));
    expect(without.split(L18B).length - 1).toBe(1);
    expect(without).not.toContain("不屬於樣本內");
  });

  it.each([true, false])("withTail=%s: one render point, text-sm, between the fold line and the first segment title", (withTail) => {
    const root = treeOf(makeResponse({ withTail }));
    const sentence = withTail ? L18A : L18B;
    const holder = findOne(root, (el) => el.tag === "p" && textOf(el) === sentence, "tail paragraph");
    const tokens = classTokens(holder);
    expect(tokens).toContain("text-sm");
    expect(tokens).not.toContain("text-xs");
    expect(isInsideScrollContainerOrCollapsed(holder)).toBe(false);
    const previous = elementChildren(holder.parent as HtmlElement)[elementChildren(holder.parent as HtmlElement).indexOf(holder) - 1];
    expect(textOf(previous as HtmlElement)).toMatch(/^Walk-forward 折數：/);
    expect(classTokens(previous as HtmlElement)).toContain("text-xs");
    const next = nextElementSibling(holder);
    expect(textOf(findOne(next as HtmlElement, (el) => el.tag === "h3", "next title"))).toBe("樣本內（in-sample）");
  });
});

describe("A-34 / AC-11: block order and what sits between the two metric tables", () => {
  const root = treeOf(makeResponse({ outOfSample: makeDetail({ below_display_minimum: true }) }));
  const section = findOne(root, (el) => el.tag === "section" && el.attrs.class?.includes("rounded-lg") === true, "report section");
  const children = elementChildren(section);

  it("segment tables first, then the two detail sub-blocks, in-sample before out-of-sample", () => {
    const tags = children.map((el) => `${el.tag}:${el.tag === "section" ? textOf(elementChildren(el)[0] ?? "") : ""}`);
    const tail = tags.slice(-4);
    expect(tail).toEqual(["div:", "div:", `section:${IN_SAMPLE_TITLE}`, `section:${OUT_OF_SAMPLE_TITLE}`]);
  });

  it("the two SegmentTable blocks are adjacent siblings; the second adds only its title, L-09 and L-10 before its table", () => {
    const [first, second] = children.slice(-4, -2);
    expect(first?.tag).toBe("div");
    expect(second?.tag).toBe("div");
    // first block ends with the existing Buy & Hold footnote (text-xs) and nothing new
    const firstKids = elementChildren(first as HtmlElement);
    expect(firstKids.map((el) => el.tag)).toEqual(["h3", "p", "div", "p"]);
    expect(classTokens(firstKids[3] as HtmlElement)).toContain("text-xs");
    const secondKids = elementChildren(second as HtmlElement);
    expect(secondKids.map((el) => el.tag)).toEqual(["h3", "p", "p", "div", "p"]);
    expect(textOf(secondKids[1] as HtmlElement)).toBe(L09);
    expect(textOf(secondKids[2] as HtmlElement)).toBe(L10);
  });

  it("the standing sentences precede every F-11 element (disclaimer, stamp, fee alert, notes)", () => {
    const markup = markupOf(makeResponse());
    const firstF11 = Math.min(
      markup.indexOf(L18A),
      markup.indexOf(L10),
      markup.indexOf(IN_SAMPLE_TITLE),
    );
    for (const anchor of [
      "產出時間：",
      "本回測報告呈現的所有數字皆屬歷史統計描述，不代表未來會重演。",
      "費率未查證：",
      "note-one",
      "Walk-forward 折數：",
    ]) {
      const at = markup.indexOf(anchor);
      expect(at, anchor).toBeGreaterThan(-1);
      expect(at, anchor).toBeLessThan(firstF11);
    }
  });
});

describe("AC-19 / AC-26 (render side): nothing the page prints is a front-end sentence", () => {
  it("every CJK text node of an F-11 element is a backend label or a formatted value", () => {
    const report = makeResponse();
    const detail = requireDetail(report);
    const allowed = new Set<string>([
      ...Object.values(detail.labels).filter((value): value is string => typeof value === "string"),
      ...Object.values(detail.labels.in_sample),
      ...Object.values(detail.labels.out_of_sample),
    ]);
    const root = treeOf(report);
    for (const title of [IN_SAMPLE_TITLE, OUT_OF_SAMPLE_TITLE]) {
      const block = subBlock(root, title);
      for (const element of findAll(block, (el) => ["p", "dt", "h3", "h4", "th", "button"].includes(el.tag))) {
        const text = textOf(element);
        if (!/[㐀-鿿]/.test(text)) continue;
        if (text.startsWith("來源：")) continue; // the report header's own source line, reused as is
        expect(allowed.has(text), text).toBe(true);
      }
    }
  });
});

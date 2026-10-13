/**
 * F11-A-50 (a)-(d): the equivalence lock between `metricRows` (what the two C8
 * guard suites read) and `segmentTableRows` (what the table renders), plus the
 * V2 row order of A-33 / W-12 and the definition-row rules of A-53.
 *
 * The C8 suites (`kellyWinRateQualifierPairing`, `backtestRoundTripCountRender`)
 * stay untouched; they keep guarding `metricRows`. This file closes the gap A-50
 * names: after the table started rendering a composed list, those suites no
 * longer watched the list on screen.
 */

import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";
import { BacktestReportView, metricRows, segmentTableRows } from "../BacktestReportView";
import type { SegmentTableRow } from "../BacktestReportView";
import type { HtmlElement } from "./htmlTree";
import { classTokens, elementChildren, findAll, nextElementSibling, parseHtml, textOf } from "./htmlTree";
import { requireDetail, stripComments } from "./sourceScan";
import { makeDetail, makeEmptyDetail, makeMetrics, makeResponse } from "./roundTripFixtures";

const source = readFileSync(fileURLToPath(new URL("../BacktestReportView.tsx", import.meta.url)), "utf-8");

const LABELS = { win_rate: "<win-rate-label>", round_trips: "<round-trips-label>" } as const;

/** The fifteen rows that existed before F-11, by id, in their original order. */
const EXISTING_IDS = [
  "period",
  "observations",
  "start_equity",
  "end_equity",
  "total_return",
  "cagr",
  "annualized_volatility",
  "sharpe",
  "sortino",
  "max_drawdown",
  "win_rate",
  "round_trips",
  "profit_factor",
  "num_trades",
  "turnover",
];

const response = makeResponse();
const detail = requireDetail(response);

function compose(): SegmentTableRow[] {
  return segmentTableRows(LABELS, makeDetail(), detail.labels, detail.labels.in_sample);
}

function firstCellText(tr: HtmlElement): string {
  const first = elementChildren(tr)[0];
  if (first === undefined) throw new Error("row without cells");
  return textOf(first);
}

const composed = compose();

describe("A-50 (a): the pre-F-11 rows inside the composed list are exactly metricRows", () => {
  const base = metricRows(LABELS);
  const existing = composed.filter((row) => EXISTING_IDS.includes(row.id));

  it("keeps all fifteen ids, once each, in the original relative order", () => {
    expect(base.map((row) => row.id)).toEqual(EXISTING_IDS);
    expect(existing.map((row) => row.id)).toEqual(EXISTING_IDS);
  });

  it("each pre-F-11 row has the same label and renders the same text for both columns", () => {
    const strategy = makeMetrics();
    const peer = makeMetrics({ win_rate: null, num_round_trips: null, profit_factor: null });
    existing.forEach((row, index) => {
      const original = base[index];
      expect(original).toBeDefined();
      if (row.kind !== "metric" || original === undefined) throw new Error("existing rows are metric rows");
      expect(row.label).toBe(original.label);
      expect(row.added).toBe(false);
      expect(row.render(strategy, "TWD")).toBe(original.render(strategy, "TWD"));
      expect(row.render(peer, "TWD")).toBe(original.render(peer, "TWD"));
      expect(row.renderBuyAndHold).toBeUndefined();
    });
  });
});

describe("A-50 (b)(c): the round-trip count row stays directly below the win-rate row", () => {
  it("count index = win-rate index + 1, each exactly once, in the composed list", () => {
    const ids = composed.map((row) => row.id);
    expect(ids.filter((id) => id === "win_rate")).toHaveLength(1);
    expect(ids.filter((id) => id === "round_trips")).toHaveLength(1);
    expect(ids.indexOf("round_trips")).toBe(ids.indexOf("win_rate") + 1);
  });

  it("the backend labels of those two rows are the labels rendered, one row each", () => {
    const labels = composed.flatMap((row) => (row.kind === "metric" ? [row.label] : []));
    expect(labels.filter((label) => label === LABELS.win_rate)).toHaveLength(1);
    expect(labels.filter((label) => label === LABELS.round_trips)).toHaveLength(1);
  });
});

describe("A-33 / W-12: V2 order, insertions only at the two anchors", () => {
  it("is exactly the V2 sequence", () => {
    expect(composed.map((row) => row.id)).toEqual([
      ...EXISTING_IDS.slice(0, 13), // period .. profit_factor
      "profit_factor_definition",
      "payoff_ratio",
      "payoff_ratio_definition",
      "num_trades",
      "turnover",
      "mean_winning_return",
      "mean_losing_return",
      "longest_losing_streak",
      "longest_losing_streak_definition",
      "in_market_ratio",
      "in_market_ratio_definition",
    ]);
  });

  it("nothing is inserted between the win-rate row and the count row, nor between any two pre-F-11 rows except at the anchors", () => {
    const ids = composed.map((row) => row.id);
    for (let i = 0; i < EXISTING_IDS.length - 1; i += 1) {
      const here = ids.indexOf(EXISTING_IDS[i] ?? "");
      const next = ids.indexOf(EXISTING_IDS[i + 1] ?? "");
      const gap = next - here - 1;
      // only profit_factor -> num_trades has insertions in between
      expect(gap, `${EXISTING_IDS[i]} -> ${EXISTING_IDS[i + 1]}`).toBe(EXISTING_IDS[i] === "profit_factor" ? 3 : 0);
    }
  });

  it("the trades and turnover rows are still present and still metric rows (L-C8-3)", () => {
    for (const id of ["num_trades", "turnover", "round_trips"]) {
      const row = composed.find((candidate) => candidate.id === id);
      expect(row?.kind).toBe("metric");
    }
  });

  it("both segments compose the same id sequence whatever their data (W-12(c))", () => {
    const sequences = [
      compose().map((row) => row.id),
      segmentTableRows(
        LABELS,
        makeEmptyDetail("no_position"),
        detail.labels,
        detail.labels.out_of_sample,
      ).map((row) => row.id),
      segmentTableRows(
        LABELS,
        makeEmptyDetail("excluded_only"),
        detail.labels,
        detail.labels.out_of_sample,
      ).map((row) => row.id),
    ];
    expect(sequences[1]).toEqual(sequences[0]);
    expect(sequences[2]).toEqual(sequences[0]);
  });

  it("ids are unique, so they are valid React keys", () => {
    const ids = composed.map((row) => row.id);
    expect(new Set(ids).size).toBe(ids.length);
  });
});

describe("A-53: definition rows", () => {
  const definitions = composed.filter((row) => row.kind === "definition");

  it("exist for exactly four anchors, one each, directly after the anchor", () => {
    expect(definitions.map((row) => row.id)).toEqual([
      "profit_factor_definition",
      "payoff_ratio_definition",
      "longest_losing_streak_definition",
      "in_market_ratio_definition",
    ]);
    const ids = composed.map((row) => row.id);
    const anchorOf: Record<string, string> = {
      profit_factor_definition: "profit_factor",
      payoff_ratio_definition: "payoff_ratio",
      longest_losing_streak_definition: "longest_losing_streak",
      in_market_ratio_definition: "in_market_ratio",
    };
    for (const definition of definitions) {
      expect(ids.indexOf(definition.id)).toBe(ids.indexOf(anchorOf[definition.id] ?? "") + 1);
    }
  });

  it("the payoff-ratio definition holds L-06d and then L-06p, in one row", () => {
    const row = composed.find((candidate) => candidate.id === "payoff_ratio_definition");
    if (row?.kind !== "definition") throw new Error("payoff definition row missing");
    expect(row.paragraphs).toEqual([detail.labels.payoff_ratio_definition, detail.labels.in_sample.payoff_ratio_pointer]);
  });

  it("the other three carry exactly one paragraph, the backend sentence", () => {
    const byId = (id: string) => {
      const row = composed.find((candidate) => candidate.id === id);
      if (row?.kind !== "definition") throw new Error(`${id} missing`);
      return row.paragraphs;
    };
    expect(byId("profit_factor_definition")).toEqual([detail.labels.profit_factor_definition]);
    expect(byId("longest_losing_streak_definition")).toEqual([detail.labels.longest_losing_streak_definition]);
    expect(byId("in_market_ratio_definition")).toEqual([detail.labels.in_sample.in_market_ratio_definition]);
  });
});

describe("A-50 (d): SegmentTable renders the composed list, not metricRows itself", () => {
  const tableBody = source.slice(source.indexOf("function SegmentTable("), source.indexOf("function SourceAndAsOf"));

  it("SegmentTable builds its rows with segmentTableRows and never calls metricRows", () => {
    expect(tableBody).toContain("segmentTableRows(labels, detail, detailLabels, segmentLabels)");
    expect(tableBody).not.toContain("metricRows(");
  });

  it("metricRows is called in exactly one place besides its own definition", () => {
    expect(stripComments(source).match(/\bmetricRows\(/g) ?? []).toHaveLength(2); // the definition and the one call
    expect(source.match(/export function metricRows\(/g) ?? []).toHaveLength(1);
  });

  it("segmentTableRows is defined in this file (so the C8 source scans cover it) and keyed by id", () => {
    expect(source).toContain("export function segmentTableRows(");
    expect(tableBody).toContain("key={row.id}");
    expect(tableBody).not.toMatch(/key=\{row\.label\}/);
  });

  it("the rendered table has one body row per composed row, in composed order", () => {
    const root = parseHtml(renderToStaticMarkup(createElement(BacktestReportView, { report: response })));
    const tables = findAll(root, (el) => el.tag === "table" && elementChildren(el).some((c) => c.tag === "colgroup"));
    expect(tables).toHaveLength(2);
    for (const table of tables) {
      const body = elementChildren(table).find((child) => child.tag === "tbody");
      if (body === undefined) throw new Error("table without tbody");
      const rows = elementChildren(body);
      const expected = compose();
      expect(rows).toHaveLength(expected.length);
      rows.forEach((tr, index) => {
        const want = expected[index];
        const cells = elementChildren(tr);
        if (want?.kind === "definition") {
          expect(cells).toHaveLength(1);
          expect(cells[0]?.attrs.colSpan).toBe("3");
        } else {
          expect(cells).toHaveLength(3);
          expect(firstCellText(tr)).toBe(want?.kind === "metric" ? want.label : "");
        }
      });
    }
  });

  it("G4: each definition row is the next sibling <tr> of its anchor <tr>, in both tables", () => {
    const root = parseHtml(renderToStaticMarkup(createElement(BacktestReportView, { report: response })));
    const tables = findAll(root, (el) => el.tag === "table" && elementChildren(el).some((c) => c.tag === "colgroup"));
    const anchors: Array<[string, string]> = [
      ["獲利因子", detail.labels.profit_factor_definition],
      ["盈虧比", detail.labels.payoff_ratio_definition],
      ["最長連續虧損回合數", detail.labels.longest_losing_streak_definition],
      ["在場時間比例", ""],
    ];
    for (const table of tables) {
      const trs = findAll(table, (el) => el.tag === "tr");
      for (const [label, sentence] of anchors) {
        const anchor = trs.find((tr) => firstCellText(tr) === label);
        if (anchor === undefined) throw new Error(`anchor row ${label} missing`);
        const next = nextElementSibling(anchor);
        if (next === null) throw new Error(`no row after ${label}`);
        expect(elementChildren(next)[0]?.attrs.colSpan).toBe("3");
        expect(textOf(next).startsWith(sentence.slice(0, 20))).toBe(true);
        expect(classTokens(next)).toContain("border-t");
      }
    }
  });
});

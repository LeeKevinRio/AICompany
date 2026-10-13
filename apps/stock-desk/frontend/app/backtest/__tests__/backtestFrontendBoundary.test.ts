/**
 * What the report page may and may not do with F-11's data (PRD FR-16 前端邊界;
 * F11-A-13, A-23, A-24, A-30, A-46; 風控 F11-W-24).
 *
 * The page formats and places. It never compares a count with a threshold,
 * never sorts, filters, sums, averages or divides what the backend sent, holds
 * no sentence of its own for F-11, and mirrors the backend models key for key.
 * These are source scans of `BacktestReportView.tsx` (comments removed) plus a
 * cross-language check of `types.ts` against the backend models.
 */

import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { describe, expect, it } from "vitest";
import { readReportViewSource, stripComments } from "./sourceScan";

const code = stripComments(readReportViewSource());

/** Every field of the round-trip detail (and the neighbouring metrics) the page must not compute on. */
const DATA_FIELDS = [
  "num_round_trips",
  "num_winning_round_trips",
  "num_losing_round_trips",
  "excluded_boundary_trips",
  "open_trip_at_end",
  "in_market_ratio",
  "buy_and_hold_in_market_ratio",
  "warmup_flat_intervals",
  "holding_bars",
  "return_on_entry_equity",
  "realized_pnl",
  "mean_winning_return",
  "mean_losing_return",
  "unattributed_tail_bars",
  "below_display_minimum",
  "empty_state",
  "round_trip_payoff_ratio",
  "profit_factor",
  "win_rate",
];
const FIELD = `\\b(?:${DATA_FIELDS.join("|")})\\b`;

describe("A-23 / A-24: no comparison, arithmetic or reshaping of backend values", () => {
  it("no field is compared with anything but null", () => {
    const after = new RegExp(`${FIELD}\\s*(?:<=|>=|===|!==|==|!=|<(?![/=])|>(?!=))(?!=)\\s*(?!null\\b)\\S`, "g");
    const before = new RegExp(`(?:\\S\\s*)(?:<=|>=|===|!==|==|!=)\\s*[\\w.]*${FIELD}`, "g");
    const hits = [...(code.match(after) ?? []), ...(code.match(before) ?? [])];
    // `empty_state === null` style null checks are code reads; the regexes skip them
    expect(hits).toEqual([]);
  });

  it("no arithmetic operator is applied to a field", () => {
    const afterField = new RegExp(`${FIELD}\\)?\\s*[-*/%]\\s*[\\w(]`, "g");
    const beforeField = new RegExp(`[-*/%]\\s*[\\w.]*${FIELD}`, "g");
    expect([...(code.match(afterField) ?? []), ...(code.match(beforeField) ?? [])]).toEqual([]);
  });

  it("no sort, filter, reduce, slice, reverse or Math call touches the data (only the row-insertion helper slices its own array)", () => {
    const insertAfter = code.slice(code.indexOf("function insertAfter("), code.indexOf("function definitionRow("));
    expect(insertAfter.length).toBeGreaterThan(0);
    const rest = code.replace(insertAfter, "");
    for (const banned of [
      /\.(?:sort|toSorted|reverse|toReversed|filter|reduce|reduceRight|slice|splice|flatMap|find|findIndex|some|every|concat)\(/,
      /\bMath\./,
      /\bNumber\(/,
      /\bparse(?:Int|Float)\(/,
    ]) {
      expect(rest, String(banned)).not.toMatch(banned);
    }
  });

  it("the only .length uses are the two that existed before F-11 (notes, fold count)", () => {
    expect(code.match(/\.length\b/g) ?? []).toHaveLength(2);
    expect(code).toContain("report.notes.length > 0");
    expect(code).toContain("report.folds.length");
  });

  it("no threshold, no flag constant and no hard-coded 100% or fallback zero", () => {
    for (const banned of [/N_MIN_DISPLAY/, /N_WORST/, /display_params/, /\bMIN_DISPLAY\b/, /(?<![\w/.-])30(?![\w/.])/, /\?\?\s*0\b/, /\|\|\s*0\b/]) {
      expect(code, String(banned)).not.toMatch(banned);
    }
    // no stand-alone 100 either; the only 100 in the file is the container-query width of the definition block
    expect(code.match(/(?<![\w/.-])100(?![\w/.])/g) ?? []).toEqual([]);
    expect(code).toContain("w-[100cqw]");
    expect(code).not.toMatch(/\b1\.0\b|1_?00%|"100/);
  });

  it("the Buy & Hold in-market cell reads the backend field (a dash for a missing path), not a literal", () => {
    expect(code).toContain("renderBuyAndHold: () => formatPercent(detail.buy_and_hold_in_market_ratio)");
  });

  it("the sample flag and the empty-state code are read as they are", () => {
    expect(code).toContain("detail.below_display_minimum && (");
    expect(code).toContain("detail.empty_state === null ? (");
    expect(code).toContain("emptyStateText[detail.empty_state]");
  });

  it("the full list starts collapsed unconditionally: useState(false), no override prop", () => {
    expect(code.match(/useState\(/g) ?? []).toHaveLength(1);
    expect(code).toContain("useState(false)");
    expect(code).not.toMatch(/useState\(\s*(?!false\))/);
    expect(code).not.toMatch(/defaultOpen|initialExpanded|defaultExpanded|\bopen=/);
  });
});

describe("A-30 / F11-W-24: the page holds no F-11 sentence and assembles none", () => {
  const CJK = /[㐀-鿿]+/g;
  /** Every CJK run in the file before F-11, as a multiset; the file may not gain one. */
  const BASELINE_RUNS = [
    "不代表未來會重演",
    "交易次數",
    "交易稅",
    "交易稅",
    "來源",
    "台股",
    "台股手續費率",
    "台股股票交易稅",
    "回測報告",
    "回測資料不足",
    "報告數字應視為待查證狀態",
    "尚未同步過",
    "年化波動度",
    "折數",
    "指標",
    "文件說明",
    "最大回撤",
    "期間",
    "未參與任何參數選擇",
    "未計交易成本的被動持有基準",
    "本回測報告呈現的所有數字皆屬歷史統計描述",
    "本次回測使用的手續費",
    "樣本內",
    "樣本內取第一折的訓練窗",
    "樣本外",
    "樣本外為所有折測試窗銜接",
    "滑價",
    "滑價率尚未對照主要來源查證",
    "為",
    "為同期間",
    "無法計算",
    "獲利因子",
    "產出時間",
    "策略",
    "結束權益",
    "結算",
    "總報酬率",
    "美股手續費率",
    "美股賣出監管費率",
    "見後端",
    "觀測筆數",
    "費率未查證",
    "資料不足",
    "資料截至",
    "起始權益",
    "週轉率",
    "除權息資料最近同步時間",
  ];

  it("no Traditional-Chinese run was added to the component (comments excluded)", () => {
    const now = [...(code.match(CJK) ?? [])].sort();
    expect(now).toEqual([...BASELINE_RUNS].sort());
  });

  it("the source/as-of text is one shared fragment, not a second copy", () => {
    expect(code.match(/資料截至/g) ?? []).toHaveLength(1);
    expect(code.match(/來源：/g) ?? []).toHaveLength(1);
    expect(code.match(/<SourceAndAsOf\b/g) ?? []).toHaveLength(2);
  });

  it("no placeholder, no .format/.replace, and no template literal around a label", () => {
    expect(code).not.toMatch(/\{(?:detail_title|excluded_heading|last_bar_date|tail_bars|tail_start_date|tail_end_date|n_win|n_loss|n_min_display|warmup_flat_intervals|segment|label|length|start_date|end_date|value|k|n)\}/);
    expect(code).not.toMatch(/\.(?:format|replace|replaceAll)\(/);
    expect(code).not.toMatch(/\$\{[^}]*[lL]abels?\b[^}]*\}/);
  });

  it("the only string concatenations of backend copy are the two L-05 cells (value, then the backend suffix)", () => {
    const joins = code.match(/[\w.]*[lL]abels?\.[\w.]*\s*\+|\+\s*[\w.]*[lL]abels?\.[\w.]+/g) ?? [];
    expect(joins).toHaveLength(2);
    expect(code).toContain("formatPercent(detail.mean_winning_return) + segmentLabels.mean_winning_return_suffix");
    expect(code).toContain("formatPercent(detail.mean_losing_return) + segmentLabels.mean_losing_return_suffix");
  });

  it("L-06p is the backend's per-segment field, passed through as its own paragraph", () => {
    expect(code).toContain("segmentLabels.payoff_ratio_pointer");
    expect(code).not.toMatch(/payoff_ratio_pointer\s*[+,]\s*[\w.]*payoff_ratio_definition/);
  });
});

/** The names of a pydantic model's fields, in declaration order. */
function pythonFields(source: string, className: string): string[] {
  const lines = source.split("\n");
  const start = lines.findIndex((line) => new RegExp(`^class ${className}\\(`).test(line));
  if (start === -1) throw new Error(`backend class ${className} not found`);
  const names: string[] = [];
  for (const line of lines.slice(start + 1)) {
    if (/^\S/.test(line)) break;
    const match = /^    ([a-z_][a-z0-9_]*):\s/.exec(line);
    if (match?.[1] !== undefined) names.push(match[1]);
  }
  return names;
}

/** The names of an exported TS interface's members, in declaration order. */
function interfaceFields(source: string, name: string): string[] {
  const lines = source.split("\n");
  const start = lines.findIndex((line) => new RegExp(`^export interface ${name}\\b`).test(line));
  if (start === -1) throw new Error(`interface ${name} not found`);
  const names: string[] = [];
  for (const line of lines.slice(start + 1)) {
    if (line.startsWith("}")) break;
    const match = /^ {2}([a-z_][a-z0-9_]*)\??:/.exec(line);
    if (match?.[1] !== undefined) names.push(match[1]);
  }
  return names;
}

describe("A-46 / AC-24: types.ts mirrors the backend models key for key", () => {
  const read = (relative: string) => readFileSync(fileURLToPath(new URL(relative, import.meta.url)), "utf-8");
  const types = read("../../lib/types.ts");
  const report = read("../../../../backend/app/backtest/report.py");
  const wording = read("../../../../backend/app/api/backtest_wording.py");
  const api = read("../../../../backend/app/api/backtest.py");

  const pairs: Array<[string, string, string]> = [
    ["RoundTripRow", "RoundTripRow", "report"],
    ["LosingStreak", "LosingStreak", "report"],
    ["SegmentRoundTripDetail", "SegmentRoundTripDetail", "report"],
    ["RoundTripCoverage", "RoundTripCoverage", "report"],
    ["SegmentRoundTripLabels", "SegmentRoundTripLabels", "wording"],
    ["RoundTripDetailLabels", "RoundTripDetailLabels", "wording"],
    ["RoundTripDetail", "RoundTripDetail", "api"],
  ];

  it.each(pairs)("interface %s has the backend %s's fields, in the same order", (tsName, pyName, where) => {
    const source = where === "report" ? report : where === "wording" ? wording : api;
    const backend = pythonFields(source, pyName);
    expect(backend.length).toBeGreaterThan(0);
    expect(interfaceFields(types, tsName)).toEqual(backend);
  });

  it("round_trip_detail sits on BacktestResponse beside curves, as the backend declares it", () => {
    const backend = pythonFields(api, "BacktestResponse");
    const frontend = interfaceFields(types, "BacktestResponse");
    expect(backend).toContain("round_trip_detail");
    expect(frontend).toContain("round_trip_detail");
    expect(frontend.indexOf("round_trip_detail")).toBe(frontend.indexOf("curves") + 1);
    expect(backend.indexOf("round_trip_detail")).toBe(backend.indexOf("curves") + 1);
  });

  it("the payoff ratio the backend always served is typed (A-46), and the top-level detail has exactly four keys (A-38)", () => {
    expect(pythonFields(report, "PerformanceMetrics")).toContain("round_trip_payoff_ratio");
    expect(interfaceFields(types, "PerformanceMetricsWithPayoff")).toEqual(["round_trip_payoff_ratio"]);
    expect(interfaceFields(types, "RoundTripDetail")).toEqual(["in_sample", "out_of_sample", "coverage", "labels"]);
  });

  it("the empty-state codes are the backend's two", () => {
    const backend = /RoundTripEmptyState = Literal\[([^\]]*)\]/.exec(report)?.[1];
    const frontend = /export type RoundTripEmptyState = ([^;]*);/.exec(types)?.[1];
    const names = (text: string | undefined) => [...(text ?? "").matchAll(/"([a-z_]+)"/g)].map((match) => match[1]);
    expect(names(frontend)).toEqual(names(backend));
    expect(names(frontend)).toEqual(["no_position", "excluded_only"]);
  });

  it("coverage.last_bar_date is typed string | null, as the backend declares it", () => {
    expect(report).toMatch(/last_bar_date: str \| None/);
    expect(types).toMatch(/export interface RoundTripCoverage \{\s*last_bar_date: string \| null;/);
  });
});

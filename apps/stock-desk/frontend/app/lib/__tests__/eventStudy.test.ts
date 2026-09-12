import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { describe, expect, it } from "vitest";
import { createRequestSequencer, eventStudyRequestFrom, formMatchesReport, reportKey } from "../eventStudy";
import * as W from "../eventStudyWording";
import type { BacktestRequest } from "../types";

const REQUEST: BacktestRequest = {
  symbol: "2330",
  market: "TW",
  strategy: "five_conditions",
  start: "2024-09-04",
  end: "2026-09-01",
  instrument_type: "stock",
  initial_cash: 1_000_000,
  train_size: 252,
  test_size: 63,
};

describe("eventStudy helpers — 風控 REQ-W4 / REQ-W5", () => {
  it("derives the study request from the backtest request that produced the report, not the form", () => {
    expect(eventStudyRequestFrom(REQUEST)).toEqual({
      symbol: "2330",
      market: "TW",
      start: "2024-09-04",
      end: "2026-09-01",
    });
  });

  it("the form matches only while every field still says what the report was run with", () => {
    const form = { symbol: " 2330 ", market: "TW" as const, strategy: "five_conditions", start: "2024-09-04", end: "2026-09-01" };
    expect(formMatchesReport(form, REQUEST)).toBe(true);
    expect(formMatchesReport({ ...form, start: "2024-09-05" }, REQUEST)).toBe(false);
    expect(formMatchesReport({ ...form, symbol: "2317" }, REQUEST)).toBe(false);
    expect(formMatchesReport({ ...form, strategy: "ma_cross" }, REQUEST)).toBe(false);
    expect(formMatchesReport({ ...form, market: "US" }, REQUEST)).toBe(false);
  });

  it("a re-run of the same parameters is a new report (new as_of) and therefore a new key", () => {
    expect(reportKey(REQUEST, "2026-09-12T10:00:00Z")).not.toBe(reportKey(REQUEST, "2026-09-12T10:05:00Z"));
    expect(reportKey(REQUEST, "t")).toBe(reportKey({ ...REQUEST }, "t"));
  });
});

describe("createRequestSequencer — stale responses never re-populate a cleared study (qa 2026-09-12)", () => {
  it("a response that resolves after the study was cleared is dropped", async () => {
    const seq = createRequestSequencer();
    const shown: string[] = [];
    let release!: () => void;
    const slow = new Promise<void>((resolve) => {
      release = resolve;
    });
    const show = async (label: string, wait: Promise<void>) => {
      const ticket = seq.begin();
      await wait;
      if (!seq.isCurrent(ticket)) return;
      shown.push(label);
    };
    const first = show("old report", slow);
    seq.invalidate(); // the screen moved on (new report / drifted form / unmount)
    release();
    await first;
    expect(shown).toEqual([]);
  });

  it("only the latest request may write; an earlier one is retired by a later begin()", async () => {
    const seq = createRequestSequencer();
    const a = seq.begin();
    const b = seq.begin();
    expect(seq.isCurrent(a)).toBe(false);
    expect(seq.isCurrent(b)).toBe(true);
    seq.invalidate();
    expect(seq.isCurrent(b)).toBe(false);
    const c = seq.begin();
    expect(seq.isCurrent(c)).toBe(true);
  });
});

describe("eventStudyWording — 逐字釘住（creative-lead 2026-09-12）", () => {
  it("shell sentences", () => {
    expect(W.EVENT_STUDY_SECTION_TITLE).toBe("五項觀察條件 事件研究");
    expect(W.EVENT_STUDY_BUTTON_LABEL).toBe("顯示五項觀察條件事件研究");
    expect(W.EVENT_STUDY_SEPARATOR_SENTENCES).toEqual([
      "上方為含手續費、證交稅與滑價的策略績效；本節為收盤對收盤、未計成本的價格分布。",
      "兩組數字衡量基礎不同，不可互推，亦不宜並列比較。",
      "本節不評價優劣，亦不代表兩者互相驗證或預測未來。",
    ]);
    expect(W.EVENT_STUDY_STALE_FORM_HINT).toBe("事件研究僅按目前回測報告的參數計算，請先重新執行回測。");
    expect(W.EVENT_STUDY_LOADING).toBe("正在計算五項觀察條件事件研究，請稍候。");
    expect(W.EVENT_STUDY_ERROR).toBe("事件研究本次未能算出結果；請先確認代號、市場與區間是否被接受，再重新查詢。");
    expect(W.BACKTEST_PAGE_INTRO).toBe("依策略回測單一標的，附同期 Buy & Hold 對照與樣本內／外分列結果。");
  });
});

describe("EventStudySection source — ADR-0008 D-2 / D-5, 風控 REQ-W8", () => {
  const src = readFileSync(resolve(__dirname, "../../backtest/EventStudySection.tsx"), "utf8");

  it("has exactly one innerHTML sink and it is the backend SVG", () => {
    // Count the JSX attribute, not the doc comment that names it.
    const sinks = src.match(/dangerouslySetInnerHTML=\{/g) ?? [];
    expect(sinks).toHaveLength(1);
    expect(src).toMatch(/dangerouslySetInnerHTML=\{\{ __html: section\.svg \}\}/);
  });

  it("renders every header item in order (no filter, no reorder) and every footnote", () => {
    expect(src).toMatch(/result\.page\.header\.map\(/);
    expect(src).not.toMatch(/page\.header\.filter\(/);
    expect(src).not.toMatch(/page\.header\.sort\(/);
    expect(src).toMatch(/result\.page\.footnotes\.map\(/);
  });

  it("guards the async show() with the sequencer: ticket taken before the await, checked before every setState", () => {
    expect(src).toMatch(/const ticket = sequencer\.current\.begin\(\);/);
    expect(src).toMatch(/if \(!sequencer\.current\.isCurrent\(ticket\)\) return;\s*setResult\(response\);/);
    // Every clearing path retires in-flight tickets: new report key, drifted form, unmount.
    expect(src.match(/sequencer\.current\.invalidate\(\)|current\.invalidate\(\)/g) ?? []).toHaveLength(3);
  });

  it("carries no backend event-study sentence as a TypeScript literal (ADR-0008 constraint 6)", () => {
    for (const fragment of ["本研究僅涵蓋", "不構成投資建議", "五條同時成立", "Wilson 95%", "非重疊子樣本"]) {
      expect(src).not.toContain(fragment);
    }
  });
});

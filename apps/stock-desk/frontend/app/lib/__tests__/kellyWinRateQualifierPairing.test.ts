/**
 * 條件 95 (`work/reviews/2026-08-19-C5-Kelly-文案批審.md` 第十輪批審) as **re-issued
 * by C8-4** (`work/reviews/2026-08-23-C8-顯示語意-風控批審.md`, 2026-08-23).
 *
 * The original rule — "前端出現 Kelly 限定語而 BacktestReportView 仍未限定即紅燈" —
 * existed because two win rates with the same underlying Chinese name were
 * computed over *different* denominators (Kelly's over complete round trips,
 * the backtest report's over settled fills) and were reachable from one
 * another. Two qualified labels had to land or revert together so that no
 * screen ever showed one qualified number beside one bare one.
 *
 * **What changed (C8)**: `app/backtest/report.py` moved to the round-trip
 * layer, so the report's win rate now *is* `RoundTripStats.round_trip_win_rate`
 * — the same statistic, from the same object, as Kelly's. One denominator means
 * one label: the 2026-08-23 ruling is 條件 49 的重送, it retires the fill-level
 * twin as a false statement, and C8-3 路徑 (a) makes the surviving label
 * backend copy with a single definition site (`app/api/kelly_wording.py`
 * `KELLY_WIN_RATE_ROUND_TRIP_QUALIFIER`, served on
 * `BacktestResponse.metric_labels.win_rate`).
 *
 * **What this file guards now.** C8-4 keeps three obligations and forbids
 * dropping any of them; path (a) moves their subject from "the literal in this
 * file" to "the API field this file renders", so each is re-expressed as an
 * equivalent, mechanical check that still fails on the same regressions:
 *
 * 1. *限定語標籤存在且恰一次* — the report table renders the qualifier exactly
 *    once, via exactly one `label:` slot fed from `metric_labels.win_rate`.
 *    Asserted on the built row list (below), which is the rendering decision
 *    itself, plus a source-level check that only one row reads that field.
 * 2. *不得回退為裸 `label: "勝率",` 或舊字面* — asserted as the strictly stronger
 *    property that **no** hard-coded win-rate row label may exist in this
 *    component in any form. Stating the retired literal here to test for its
 *    absence would itself violate the ruling's 零出現要求 (the retired label
 *    must not occur anywhere under `apps/` — source, comments and assertion
 *    strings alike), so the
 *    check is a pattern over `label:` slots instead; it covers the bare form,
 *    the retired qualified form and any future re-typing in one assertion. The
 *    retired literal's own zero-occurrence scan — which does have to spell it
 *    out once, in a guard tuple outside the shipped tree — is
 *    `backend/tests/test_kelly_wording.py`'s `REJECTED_LITERALS`, whose
 *    `shipped` scope reads this frontend tree too.
 * 3. *該檔「勝率」不得出現於限定語之外* — with path (a) the file has no Chinese
 *    win-rate literal at all, so the count of the banned bare term in its
 *    source must be zero. That is asserted directly here (and independently by
 *    `componentWordingScan.test.ts`, whose allowlist entry for this file C8-2
 *    deleted).
 *
 * The backend half of the pairing is asserted where the string is produced:
 * `backend/tests/test_api_backtest.py` (the served label is the constant
 * itself) and `backend/tests/test_kelly_wording.py` (the constant is still the
 * risk-approved literal, character for character).
 *
 * L-C8-4 (2026-08-23 列管): this file's earlier header stated 「回測頁是 Kelly
 * 帶入動作所在」, which has not been true since the import entry point moved to
 * `settings/KellyInputsSection.tsx:127`. Corrected here per the ruling's
 * instruction to fix it when this file is next touched. If the entry point ever
 * does move onto the backtest page, that triggers L-C8-1(b) and this whole
 * screen goes back to risk review.
 */

import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { describe, expect, it } from "vitest";
import { metricRows } from "../../backtest/BacktestReportView";

const absolutePath = fileURLToPath(new URL("../../backtest/BacktestReportView.tsx", import.meta.url));
const source = readFileSync(absolutePath, "utf-8");

/** A stand-in for whatever the backend serves, so the test asserts wiring, not copy. */
const LABELS = { win_rate: "<win-rate-label>", round_trips: "<round-trips-label>" } as const;

describe("BacktestReportView.tsx — C8-4 限定語守門(路徑 a:後端供給、前端逐字渲染)", () => {
  it("① renders the backend-supplied win-rate label exactly once, as a row label", () => {
    const labels = metricRows(LABELS).map((row) => row.label);
    expect(labels.filter((label) => label === LABELS.win_rate)).toHaveLength(1);
  });

  it("① only one row label reads `labels.win_rate` in the source", () => {
    expect(source.match(/label:\s*labels\.win_rate\b/g) ?? []).toHaveLength(1);
  });

  it("② no win-rate row label is hard-coded here, in any form (bare or qualified)", () => {
    // Covers the pre-任務6 bare literal, the C8-retired qualified one, and any
    // future re-typing of the approved qualifier: every `label:` slot must be
    // either a plain functional heading or a `labels.*` field, and none of them
    // may contain the banned bare term.
    const hardCodedLabels = source.match(/label:\s*"[^"]*"/g) ?? [];
    expect(hardCodedLabels.filter((slot) => slot.includes("勝率"))).toEqual([]);
  });

  it("③ the banned bare term does not appear anywhere in the file", () => {
    expect(source.match(/勝率/g) ?? []).toEqual([]);
  });

  it("C8-6: the round-trip count row is present exactly once and is backend-labelled", () => {
    const labels = metricRows(LABELS).map((row) => row.label);
    expect(labels.filter((label) => label === LABELS.round_trips)).toHaveLength(1);
    expect(source.match(/label:\s*labels\.round_trips\b/g) ?? []).toHaveLength(1);
  });

  it("C8-8 顯著度: the round-trip count row sits in the same table, directly below the win rate", () => {
    const labels = metricRows(LABELS).map((row) => row.label);
    expect(labels.indexOf(LABELS.round_trips)).toBe(labels.indexOf(LABELS.win_rate) + 1);
  });
});

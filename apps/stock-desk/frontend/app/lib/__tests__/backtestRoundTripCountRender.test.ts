/**
 * C8-13 (風控追加裁示 2026-08-23,
 * `work/reviews/2026-08-23-C8-顯示語意-風控批審.md` 追加裁示 4).
 *
 * The 完整回合數 row carries **three** states, and the ruling turned on all
 * three staying apart *on screen*:
 *
 * - `null` → 「—」: no round-trip attribution was ever run for this column
 *   (the Buy & Hold peer, `_metrics(..., round_trips=None)` in
 *   `app/backtest/report.py`). Rendering `0` here would claim a measurement was
 *   taken and came back empty, which is untrue.
 * - `0` → 「0」: attribution ran and found no complete round trip — the
 *   「唯一回合跨界被排除」 window, whose win rate also renders 「—」 while its
 *   settlement count is non-zero. This is the state the row exists to explain.
 * - `> 0` → the count itself, the denominator the win rate was measured over.
 *
 * The two `—`-win-rate columns are told apart **only** by this row, so flatten
 * `null` into `0` (or vice versa) and the screen silently loses the very
 * distinction C8-6 was required for.
 *
 * Why this file exists at all: both backends already pin the data layer
 * (`backend/tests/test_api_backtest.py`
 * `test_the_round_trip_count_ships_on_every_metric_block`,
 * `backend/tests/test_backtest_report.py`
 * `test_a_segment_with_no_completed_round_trip_reports_zero_not_absent`), but
 * `BacktestReportView.tsx`'s `formatCount` had no coverage whatsoever. A single
 * `?? 0`-style null normalisation in the renderer would erase the distinction
 * with every existing test still green. Asserted against `metricRows`, i.e. the
 * row list the table actually renders, not against `formatCount` directly, so
 * re-pointing the row at some other formatter is caught too.
 */

import { describe, expect, it } from "vitest";
import { metricRows } from "../../backtest/BacktestReportView";
import type { BacktestMetricLabels, PerformanceMetrics } from "../types";

/** Stand-ins for the backend copy, so this suite asserts rendering, not wording. */
const LABELS: BacktestMetricLabels = {
  win_rate: "<win-rate-label>",
  round_trips: "<round-trips-label>",
};

const CURRENCY = "TWD";

/** A metrics block shaped like the backend's, with only the fields under test set. */
function metricsWith(overrides: Partial<PerformanceMetrics>): PerformanceMetrics {
  return {
    label: "策略",
    start_date: "2024-01-02",
    end_date: "2024-06-28",
    observations: 120,
    start_equity: 1_000_000,
    end_equity: 1_050_000,
    total_return: 0.05,
    cagr: 0.1,
    annualized_volatility: 0.2,
    sharpe: 0.5,
    sortino: 0.6,
    max_drawdown: -0.08,
    max_drawdown_peak_date: null,
    max_drawdown_trough_date: null,
    win_rate: null,
    profit_factor: null,
    num_trades: 2,
    num_closing_trades: 1,
    turnover: 0.3,
    num_round_trips: null,
    ...overrides,
  };
}

function render(label: string, metrics: PerformanceMetrics): string {
  const row = metricRows(LABELS).find((candidate) => candidate.label === label);
  if (row === undefined) {
    throw new Error(`no row labelled ${label} — the C8-6 row was renamed or removed`);
  }
  return row.render(metrics, CURRENCY);
}

const renderRoundTrips = (num_round_trips: number | null): string =>
  render(LABELS.round_trips, metricsWith({ num_round_trips }));

describe("BacktestReportView 完整回合數列 — C8-13 渲染層三態守門", () => {
  it("renders a measured zero as 「0」, never as the not-applicable dash", () => {
    expect(renderRoundTrips(0)).toBe("0");
  });

  it("renders absent attribution as 「—」, never as a zero it never measured", () => {
    expect(renderRoundTrips(null)).toBe("—");
  });

  it("keeps the two states distinguishable: 0 and null never render the same string", () => {
    expect(renderRoundTrips(0)).not.toBe(renderRoundTrips(null));
  });

  it("renders a positive count as the count itself", () => {
    expect(renderRoundTrips(34)).toBe("34");
    expect(renderRoundTrips(1234)).toBe("1,234");
  });

  it("風控 理由 5 的情境: both columns show 「—」 for the win rate, and only this row tells them apart", () => {
    // Left: attribution ran, the window's only round trip crossed the boundary.
    const noCompleteRoundTrip = metricsWith({ win_rate: null, num_round_trips: 0, num_closing_trades: 1 });
    // Right: the Buy & Hold peer, which has no round-trip attribution at all.
    const noAttribution = metricsWith({ win_rate: null, num_round_trips: null, num_closing_trades: 0 });

    expect(render(LABELS.win_rate, noCompleteRoundTrip)).toBe(render(LABELS.win_rate, noAttribution));
    expect(render(LABELS.round_trips, noCompleteRoundTrip)).not.toBe(
      render(LABELS.round_trips, noAttribution),
    );
  });
});

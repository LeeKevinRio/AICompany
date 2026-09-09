import type { SegmentCurves, WalkForwardCurves } from "./types";

/**
 * Pure helpers behind `EquityCurveChart` (CEO 2026-09-09「像曲線圖那樣」;
 * creative-lead 方案: two lines indexed to 100, in-sample / out-of-sample
 * split, strategy drawdown underneath).
 *
 * Every segment is re-based to 100 at its **own** first bar, for both series.
 * That mirrors the report table, which compares each segment's own
 * `total_return` (Buy & Hold restarts from `initial_cash` at the segment
 * start on the backend, so a single continuous index would put the two lines
 * on different footings inside the out-of-sample window). The chart draws the
 * two segments as separate series of the same colour, so the re-base never
 * shows up as a vertical connector.
 */

export const INDEX_BASE = 100;

/**
 * 風控 2026-09-09 REQ-2: a segment is drawn only when BOTH series have at least
 * this many points. A single re-based point would sit at exactly 100 for both
 * lines and read as "identical performance", which is arithmetic, not a
 * measurement; a segment missing one series would show a lone line under a
 * two-entry legend.
 */
export const MIN_SEGMENT_POINTS = 2;

export interface IndexedPoint {
  time: string;
  value: number;
}

export interface SegmentIndexedSeries {
  strategy: IndexedPoint[];
  buyAndHold: IndexedPoint[];
  /** Strategy drawdown as a percentage (<= 0), e.g. -15.49. */
  drawdown: IndexedPoint[];
  /** Both series reach `MIN_SEGMENT_POINTS`; false segments are not drawn (REQ-2). */
  drawable: boolean;
  /** True when the backend sent no bars at all for this segment (vs. too few). */
  absent: boolean;
}

export interface EquityCurveSeries {
  inSample: SegmentIndexedSeries;
  outOfSample: SegmentIndexedSeries;
  splitDate: string | null;
  tradeCount: number;
}

function indexTo100(dates: string[], values: number[]): IndexedPoint[] {
  const base = values[0];
  if (base === undefined || !Number.isFinite(base) || base <= 0) return [];
  const n = Math.min(dates.length, values.length);
  const out: IndexedPoint[] = [];
  for (let i = 0; i < n; i += 1) {
    const v = values[i]!;
    if (!Number.isFinite(v)) continue;
    out.push({ time: dates[i]!, value: (v / base) * INDEX_BASE });
  }
  return out;
}

function drawdownPct(dates: string[], values: number[]): IndexedPoint[] {
  const n = Math.min(dates.length, values.length);
  const out: IndexedPoint[] = [];
  for (let i = 0; i < n; i += 1) {
    const v = values[i]!;
    if (!Number.isFinite(v)) continue;
    out.push({ time: dates[i]!, value: v * 100 });
  }
  return out;
}

export function indexSegment(segment: SegmentCurves): SegmentIndexedSeries {
  const strategy = indexTo100(segment.dates, segment.strategy);
  const buyAndHold = indexTo100(segment.dates, segment.buy_and_hold);
  return {
    strategy,
    buyAndHold,
    drawdown: drawdownPct(segment.dates, segment.drawdown),
    drawable: strategy.length >= MIN_SEGMENT_POINTS && buyAndHold.length >= MIN_SEGMENT_POINTS,
    absent: segment.dates.length === 0,
  };
}

export function buildEquityCurveSeries(curves: WalkForwardCurves): EquityCurveSeries {
  return {
    inSample: indexSegment(curves.in_sample),
    outOfSample: indexSegment(curves.out_of_sample),
    splitDate: curves.split_date,
    tradeCount: curves.trades.length,
  };
}

/** True when neither segment is drawable (REQ-5: both series are checked, not just the strategy). */
export function isEquityCurveEmpty(series: EquityCurveSeries): boolean {
  return !series.inSample.drawable && !series.outOfSample.drawable;
}

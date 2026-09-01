import type { Bar } from "./types";

/**
 * Key reference levels derived from the verified bars chain — price position
 * within its own trailing range, pullback references, and stop-loss /
 * take-profit reference levels computed from this panel's own fixed formula
 * parameters (2×ATR stop, −8% fixed stop, +20% target, 2R target) — panel-
 * chosen constants, not statistics about anyone's actual behaviour (risk R8).
 *
 * MVP scope note (CEO 需求 2026-09-01): computed client-side from the bars the
 * position page already fetches. These are *display-layer derived numbers*,
 * every formula is disclosed next to its value, and the wording is
 * reference-level only ("參考水位"), never an instruction. Formal home for
 * this logic is the backend advice layer (quant-researcher methodology +
 * risk-compliance sign-off tracked as follow-up); nothing here feeds any
 * calculation elsewhere.
 *
 * All fields are nullable: a short history degrades field-by-field instead of
 * hiding the whole panel, and callers must render an honest "insufficient
 * data" state for null fields (never 0 or a made-up number).
 */
export interface KeyLevels {
  /** Latest close and its trade date (the basis of every level below). */
  close: number;
  closeDate: string;
  /** Trailing ~52-week (252-bar) range; null with fewer than 60 bars. */
  rangeHigh: number | null;
  rangeLow: number | null;
  /** 0–100: where close sits inside [rangeLow, rangeHigh]. */
  rangePositionPct: number | null;
  /** Simple moving averages of close; null when history is shorter. */
  ma20: number | null;
  ma60: number | null;
  /** (close / ma60 − 1) × 100; null when ma60 is null. */
  ma60DeviationPct: number | null;
  /** Lowest low of the last 60 bars (one of this panel's pullback levels). */
  recentLow60: number | null;
  /** ATR(14), simple mean of true ranges; null with fewer than 15 bars. */
  atr14: number | null;
  /**
   * Entry price the stop/target references are anchored on: the position's
   * average cost when held, otherwise the latest close (a simulation the UI
   * must label as such).
   */
  anchorPrice: number;
  anchoredOnCost: boolean;
  /** anchor − 2×ATR(14); null when atr14 is null. */
  stopAtr: number | null;
  /** anchor × 0.92 (this panel's fixed −8% stop parameter). */
  stopFixedPct: number;
  /**
   * The tighter (higher) of the two stops — the conservative reference the
   * UI leads with; equals stopFixedPct when ATR is unavailable.
   */
  stopSuggested: number;
  /** anchor × 1.20 (this panel's fixed +20% parameter). */
  targetFixedPct: number;
  /** anchor + 2 × (anchor − stopSuggested) — the panel's 2R formula. */
  target2R: number;
  /** Number of bars the calculations actually saw (for the meta line). */
  barCount: number;
  /**
   * Bars actually inside the range window: min(barCount, 252). The UI must
   * state this number instead of claiming any fixed period (risk R2) — with
   * fewer than 252 bars the "range" is only as long as the history it saw.
   */
  rangeBarCount: number;
  /**
   * Why `rangePositionPct` is null (risk R15): "too-few-bars" (< 60 bars) and
   * "flat-range" (enough bars but rangeHigh === rangeLow, e.g. a halted or
   * filler-padded series) need DIFFERENT user-facing sentences — the
   * too-few-bars wording is false in the flat case. Null when the position
   * percentage is available.
   */
  rangeUnavailableCause: "too-few-bars" | "flat-range" | null;
}

const RANGE_BARS = 252;
const RECENT_BARS = 60;
const ATR_PERIOD = 14;
const ATR_STOP_MULTIPLE = 2;
const FIXED_STOP_RATIO = 0.92;
const FIXED_TARGET_RATIO = 1.2;

function toNum(value: string): number {
  return Number.parseFloat(value);
}

function mean(values: number[]): number {
  return values.reduce((a, b) => a + b, 0) / values.length;
}

/**
 * Compute every reference level from a chronologically ascending bar series.
 * Returns null when there is no usable bar at all. Bars with non-finite
 * numbers are rejected up front (whole-series refusal beats silently
 * computing on partly-garbage data — same posture as the repository layer).
 */
export function computeKeyLevels(bars: Bar[], avgCost: number | null): KeyLevels | null {
  if (bars.length === 0) return null;
  const closes = bars.map((b) => toNum(b.close));
  const highs = bars.map((b) => toNum(b.high));
  const lows = bars.map((b) => toNum(b.low));
  if ([...closes, ...highs, ...lows].some((n) => !Number.isFinite(n))) return null;

  const close = closes[closes.length - 1]!;
  const closeDate = bars[bars.length - 1]!.date;

  const rangeSlice = { highs: highs.slice(-RANGE_BARS), lows: lows.slice(-RANGE_BARS) };
  const hasRange = bars.length >= RECENT_BARS;
  const rangeHigh = hasRange ? Math.max(...rangeSlice.highs) : null;
  const rangeLow = hasRange ? Math.min(...rangeSlice.lows) : null;
  const rangePositionPct =
    rangeHigh !== null && rangeLow !== null && rangeHigh > rangeLow
      ? ((close - rangeLow) / (rangeHigh - rangeLow)) * 100
      : null;
  const rangeUnavailableCause: "too-few-bars" | "flat-range" | null =
    rangePositionPct !== null ? null : hasRange ? "flat-range" : "too-few-bars";

  const ma20 = closes.length >= 20 ? mean(closes.slice(-20)) : null;
  const ma60 = closes.length >= 60 ? mean(closes.slice(-60)) : null;
  const ma60DeviationPct = ma60 !== null ? (close / ma60 - 1) * 100 : null;
  const recentLow60 = bars.length >= RECENT_BARS ? Math.min(...lows.slice(-RECENT_BARS)) : null;

  let atr14: number | null = null;
  if (bars.length >= ATR_PERIOD + 1) {
    const trs: number[] = [];
    for (let i = bars.length - ATR_PERIOD; i < bars.length; i++) {
      const prevClose = closes[i - 1]!;
      trs.push(Math.max(highs[i]! - lows[i]!, Math.abs(highs[i]! - prevClose), Math.abs(lows[i]! - prevClose)));
    }
    atr14 = mean(trs);
  }

  const anchoredOnCost = avgCost !== null && Number.isFinite(avgCost) && avgCost > 0;
  const anchorPrice = anchoredOnCost ? (avgCost as number) : close;

  const stopFixedPct = anchorPrice * FIXED_STOP_RATIO;
  const stopAtr = atr14 !== null ? anchorPrice - ATR_STOP_MULTIPLE * atr14 : null;
  // The tighter stop is the HIGHER price (the smaller loss); with no ATR the
  // fixed-percent stop is the only candidate.
  const stopSuggested = stopAtr !== null ? Math.max(stopAtr, stopFixedPct) : stopFixedPct;

  const targetFixedPct = anchorPrice * FIXED_TARGET_RATIO;
  const target2R = anchorPrice + 2 * (anchorPrice - stopSuggested);

  return {
    close,
    closeDate,
    rangeHigh,
    rangeLow,
    rangePositionPct,
    ma20,
    ma60,
    ma60DeviationPct,
    recentLow60,
    atr14,
    anchorPrice,
    anchoredOnCost,
    stopAtr,
    stopFixedPct,
    stopSuggested,
    targetFixedPct,
    target2R,
    barCount: bars.length,
    rangeBarCount: Math.min(bars.length, RANGE_BARS),
    rangeUnavailableCause,
  };
}

/**
 * The stop/target anchor's provenance, decided by the caller (risk R10/R11):
 * "cost" = held with a usable average cost; "close-not-held" = the position
 * query CONFIRMED the symbol is not held; "close-unknown" = holding status or
 * cost could not be determined (query pending/failed/fields missing) — the UI
 * must never claim "未持有" in that state.
 */
export type AnchorSource = "cost" | "close-not-held" | "close-unknown";

/** 位階三分類的門檻（≤30 低位、≥70 高位、其餘中位）。 */
export type RangeZone = "low" | "mid" | "high";

export function classifyRangeZone(rangePositionPct: number): RangeZone {
  if (rangePositionPct <= 30) return "low";
  if (rangePositionPct >= 70) return "high";
  return "mid";
}

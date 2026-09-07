import type { KeyLevels } from "./keyLevels";
import { rsiBand, volumeZBand } from "./indicatorBands";
import { ruleDirection } from "./ruleDirection";
import type { AdviceCard, SignalsPayload } from "./types";

/**
 * 進場觀察條件 (CEO 需求 2026-09-06「進場點的觀察」; PRD
 * `work/stock-desk-進場觀察條件-PRD.md`): six FIXED observation conditions,
 * each evaluated to a tri-state — met / unmet / unavailable — from data the
 * position page already holds (KeyLevels from bars, the signals payload, the
 * advice card). Nothing here is a signal or an instruction: the thresholds
 * are this panel's own textbook constants (same nature as the −8% stop and
 * the 30/70 RSI bands), the count of met conditions is a count and nothing
 * more, and every observed value travels with its verdict so the UI can print
 * the number next to the word.
 *
 * `unavailable` is never folded into `unmet`: a condition the data cannot
 * answer stays visibly undecided (same posture as the 「—」 rule elsewhere).
 */

export type ConditionStatus = "met" | "unmet" | "unavailable";

export type ConditionId = "range" | "trend" | "pullback" | "momentum" | "volume" | "rules";

export const ENTRY_CONDITION_IDS: readonly ConditionId[] = ["range", "trend", "pullback", "momentum", "volume", "rules"];

/** Threshold constants — printed on the page beside each condition, so keep them here as the single source. */
export const ENTRY_RANGE_MAX_PCT = 70;
export const ENTRY_PULLBACK_MAX_ABS_PCT = 3;

export interface ConditionResult {
  readonly id: ConditionId;
  readonly status: ConditionStatus;
  /**
   * The number(s) the verdict was read from, already formatted for display by
   * the caller's formatter; `null` when unavailable. Kept as raw numbers here
   * so tests can assert on values, not strings.
   */
  readonly observed: number | null;
  /** A second observed number where the condition compares two (close vs MA60). */
  readonly reference: number | null;
}

export interface EntryObservation {
  readonly conditions: readonly ConditionResult[];
  readonly metCount: number;
  readonly unmetCount: number;
  readonly unavailableCount: number;
  /** True when every condition is unavailable — the UI shows its no-data sentence instead of a count. */
  readonly allUnavailable: boolean;
  /** MA20 ±3% band, or null when MA20 is unavailable (the ladder then marks nothing). */
  readonly observationBand: { readonly low: number; readonly high: number } | null;
}

function fin(n: number | null | undefined): number | null {
  return typeof n === "number" && Number.isFinite(n) ? n : null;
}

function rangeCondition(levels: KeyLevels | null): ConditionResult {
  const pct = fin(levels?.rangePositionPct);
  if (pct === null) return { id: "range", status: "unavailable", observed: null, reference: null };
  // Same epsilon posture as the pullback condition: an exact 70.00% is met.
  return { id: "range", status: pct <= ENTRY_RANGE_MAX_PCT + 1e-9 ? "met" : "unmet", observed: pct, reference: null };
}

function trendCondition(levels: KeyLevels | null): ConditionResult {
  const close = fin(levels?.close);
  const ma60 = fin(levels?.ma60);
  if (close === null || ma60 === null) return { id: "trend", status: "unavailable", observed: null, reference: null };
  return { id: "trend", status: close > ma60 ? "met" : "unmet", observed: close, reference: ma60 };
}

function pullbackCondition(levels: KeyLevels | null): ConditionResult {
  const close = fin(levels?.close);
  const ma20 = fin(levels?.ma20);
  if (close === null || ma20 === null || ma20 <= 0) {
    return { id: "pullback", status: "unavailable", observed: null, reference: null };
  }
  const distPct = (close / ma20 - 1) * 100;
  return {
    id: "pullback",
    // Tiny epsilon so an exact ±3.00% (103/100) is not tipped over by binary rounding.
    status: Math.abs(distPct) <= ENTRY_PULLBACK_MAX_ABS_PCT + 1e-9 ? "met" : "unmet",
    observed: distPct,
    reference: ma20,
  };
}

function momentumCondition(signals: SignalsPayload | null): ConditionResult {
  const rsiResult = signals?.technical?.rsi;
  const rsi = rsiResult && rsiResult.status === "ok" ? fin(rsiResult.last.rsi) : null;
  const band = rsiBand(rsi);
  if (band === null) return { id: "momentum", status: "unavailable", observed: null, reference: null };
  return { id: "momentum", status: band === "mid" ? "met" : "unmet", observed: rsi, reference: null };
}

function volumeCondition(signals: SignalsPayload | null): ConditionResult {
  const vz = signals?.technical?.volume_zscore;
  const z = vz && vz.status === "ok" ? fin(vz.last.zscore) : null;
  const band = volumeZBand(z);
  if (band === null) return { id: "volume", status: "unavailable", observed: null, reference: null };
  return { id: "volume", status: band === "mid" ? "met" : "unmet", observed: z, reference: null };
}

/**
 * "No defensive-direction rule matched this time." Direction per rule is read
 * back from the card's own `direction_weights` (never re-derived); a matched
 * rule whose action the card does not list is counted as unknown and makes
 * the condition unavailable rather than silently met.
 */
function rulesCondition(advice: AdviceCard | null, held: boolean | null): ConditionResult {
  // 風控 RED-1 路徑 (a): in candidate mode (not held, or holding status
  // undetermined) the position-dependent defensive rules are skipped by the
  // engine, which would bias this condition towards "met" exactly for the
  // reader who is considering an entry — so it is undecidable here, never met.
  if (!advice || held !== true) return { id: "rules", status: "unavailable", observed: null, reference: null };
  let defensive = 0;
  for (const rule of advice.matched_rules) {
    const direction = ruleDirection(advice, rule.action);
    if (direction === null) return { id: "rules", status: "unavailable", observed: null, reference: null };
    if (direction === "defensive") defensive += 1;
  }
  return { id: "rules", status: defensive === 0 ? "met" : "unmet", observed: defensive, reference: null };
}

export function evaluateEntryObservation(
  levels: KeyLevels | null,
  signals: SignalsPayload | null,
  advice: AdviceCard | null,
  /** `AdviceResponse.held`; `null` while the holding status is undetermined. */
  held: boolean | null,
): EntryObservation {
  const conditions: ConditionResult[] = [
    rangeCondition(levels),
    trendCondition(levels),
    pullbackCondition(levels),
    momentumCondition(signals),
    volumeCondition(signals),
    rulesCondition(advice, held),
  ];
  const metCount = conditions.filter((c) => c.status === "met").length;
  const unmetCount = conditions.filter((c) => c.status === "unmet").length;
  const unavailableCount = conditions.length - metCount - unmetCount;
  const ma20 = fin(levels?.ma20);
  const observationBand =
    ma20 !== null && ma20 > 0
      ? { low: ma20 * (1 - ENTRY_PULLBACK_MAX_ABS_PCT / 100), high: ma20 * (1 + ENTRY_PULLBACK_MAX_ABS_PCT / 100) }
      : null;
  return {
    conditions,
    metCount,
    unmetCount,
    unavailableCount,
    allUnavailable: unavailableCount === conditions.length,
    observationBand,
  };
}

/** Whether a price sits inside the MA20 ±3% band (used by the ladder's 觀察區 marking). */
export function isInObservationBand(price: number, band: EntryObservation["observationBand"]): boolean {
  return band !== null && price >= band.low && price <= band.high;
}

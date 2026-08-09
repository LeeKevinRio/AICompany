/**
 * Pure rendering-decision logic for `RiskGauge` (FR-8), split out of the
 * component so the risk-compliance-mandated invariants below can be asserted
 * with a plain unit test, without a DOM.
 *
 * Risk-compliance ruling carried forward unchanged from the previous
 * (all-`not_evaluable`) version of `RiskGauge.tsx` (commit
 * "fix: RiskGauge 對比度升級並移除 not_evaluable 空進度條"): a cap whose
 * `status` is `not_evaluable` must never draw a progress bar, not even an
 * empty (0-width) one — a bar reads as "this was measured", which is false
 * for a cap the backend could not evaluate. `shouldShowLimitBar` is the one
 * place that decision is made; every call site must go through it rather
 * than re-deriving the condition.
 */

import type { BookLimitCheck, LimitStatus, SymbolDataMeta } from "./types";

/**
 * Whether one cap's row should draw a progress bar. `status` alone decides
 * the `not_evaluable` case; `threshold` is guarded separately because a
 * `null` or non-positive threshold has no denominator to draw a ratio
 * against, whatever the status says (defensive — `app/advice/book_limits.py`
 * only ever pairs a non-`not_evaluable` status with a real threshold today,
 * but this function must not assume that invariant holds forever).
 */
export function shouldShowLimitBar(status: LimitStatus, threshold: number | null): boolean {
  return status !== "not_evaluable" && threshold !== null && threshold > 0;
}

/**
 * `observed / threshold` as a 0-100 percentage, clamped to the track's
 * range. A violated cap (`observed` past `threshold`) still draws a full
 * bar rather than overflowing the track; a negative `observed` (not
 * expected from any current cap, but not excluded by the type) floors at 0.
 */
export function limitBarWidthPercent(observed: number | null, threshold: number | null): number {
  if (observed === null || threshold === null || threshold <= 0) return 0;
  return Math.min(100, Math.max(0, (observed / threshold) * 100));
}

/** What `LimitGaugeItem` needs to decide, computed once per cap. */
export interface LimitGaugeViewModel {
  showBar: boolean;
  barWidthPercent: number;
  hasExcluded: boolean;
  excludedCount: number;
}

export function buildLimitGaugeViewModel(check: BookLimitCheck): LimitGaugeViewModel {
  const showBar = shouldShowLimitBar(check.status, check.threshold);
  return {
    showBar,
    barWidthPercent: showBar ? limitBarWidthPercent(check.observed, check.threshold) : 0,
    hasExcluded: check.excluded.length > 0,
    excludedCount: check.excluded.length,
  };
}

/**
 * FR-8 風控快審附帶條件（work/reviews/股數區間文案裁決.md，2026-08-09）：the
 * sources block's summary line must carry a warning whenever any source is
 * not `fresh`, and the `<details>` must default to *open* in that case — a
 * collapsed-by-default disclosure is not an acceptable place to hide "some
 * of this data is stale" from the reader. Only when every source is `fresh`
 * does the block stay collapsed by default.
 */
export interface SourcesSummaryViewModel {
  allFresh: boolean;
  staleCount: number;
  defaultOpen: boolean;
}

export function buildSourcesSummaryViewModel(sources: SymbolDataMeta[]): SourcesSummaryViewModel {
  const staleCount = sources.filter((source) => source.data.status !== "fresh").length;
  const allFresh = staleCount === 0;
  return { allFresh, staleCount, defaultOpen: !allFresh };
}

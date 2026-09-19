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
 * not `fresh`.
 *
 * 2026-09-19 H5 取代 2026-08-09「非 fresh 時 details 預設展開」條件，改為主
 * 視圖保留新鮮度半句（`work/stock-desk-一眼一句-實作規格.md` §3.2）：
 * `RiskGauge` 的共用 `<details>` 不再因任一 source 非 fresh 而自動展開，改成
 * summary 右側常駐附一句「其中 N 檔非即時」，使用者不用展開就看得到警示訊號。
 * `allFresh`/`staleCount` 仍是這句半句的唯一資料來源；原本的 `defaultOpen`
 * 欄位已無任何消費者，移除。
 */
export interface SourcesSummaryViewModel {
  allFresh: boolean;
  staleCount: number;
}

export function buildSourcesSummaryViewModel(sources: SymbolDataMeta[]): SourcesSummaryViewModel {
  const staleCount = sources.filter((source) => source.data.status !== "fresh").length;
  const allFresh = staleCount === 0;
  return { allFresh, staleCount };
}

/**
 * H2 status-chip colour upgrade (首頁「一眼一句」簡化，
 * `work/stock-desk-一眼一句-視覺規範.md` B.3): a translucent-background chip
 * replacing the plain-text colour `limitStatusColorClass` (`app/lib/format.ts`)
 * still uses. Kept as a separate, `RiskGauge`-only function rather than
 * changing `limitStatusColorClass` itself, because that function is shared
 * with the individual position page's `LimitsCheckList.tsx`, which this batch
 * does not touch and whose visual is out of scope here.
 */
const RISK_GAUGE_CHIP_CLASS: Record<LimitStatus, string> = {
  passed: "border-emerald-800 bg-emerald-950/40 text-emerald-300",
  violated: "border-rose-800 bg-rose-950/40 text-rose-300",
  not_evaluable: "border-amber-800 bg-amber-950/40 text-amber-300",
};

export function riskGaugeChipClass(status: LimitStatus): string {
  return RISK_GAUGE_CHIP_CLASS[status];
}

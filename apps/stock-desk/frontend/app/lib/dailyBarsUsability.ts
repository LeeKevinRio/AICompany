import type { Bar } from "./types";

/**
 * RC-767 / RC-764: ONE shared verdict on whether a daily-bar series can be
 * used at all. The key-levels calculation, the technical-analysis section and
 * (later) the decision card and the entry conditions must all read this same
 * result instead of re-deriving it.
 *
 * Rule (identical to the refusal in `computeKeyLevels`): if ANY bar has a
 * close, high or low that is not a finite number or is <= 0, the WHOLE batch
 * is unusable. Bad bars are never dropped to compute on the remainder.
 *
 * RC-767 plan P: H1 will add a third state, "gap" (carrying `{d}`, `{x}`,
 * `{k}`), to this union. Evaluation order is fixed: bad-value check on the
 * whole batch first, gap detection only if that passes, and never for
 * non-TW markets. Only "usable" / "unusable" exist today. Consumers should
 * branch on `status === "unusable"` (not `!== "usable"`) so a future "gap"
 * state does not collapse the technical section.
 */
export type DailyBarsUsability = { status: "usable" } | { status: "unusable" };

/**
 * RC-764 (final wording, risk-approved): shown once, in place of the chart,
 * indicator chips, one-line conclusion, indicator cards and the bar-count
 * line. Its leading clause must stay identical to the prefix of
 * `KEY_LEVELS_NO_DATA_STATEMENT` (RC-770 locks this in a test).
 */
export const TECHNICAL_SECTION_NO_DATA_STATEMENT =
  "目前沒有可用的日線資料，技術分析區的圖表與指標不顯示。";

/** Same parse as `computeKeyLevels` (parseFloat, finite, > 0). */
function isUsablePrice(raw: string): boolean {
  const n = Number.parseFloat(raw);
  return Number.isFinite(n) && n > 0;
}

/**
 * An empty series has no bad bar, so it is "usable" here; callers that need
 * "at least one bar" (e.g. `computeKeyLevels`) keep their own length check.
 */
export function evaluateDailyBarsUsability(bars: readonly Bar[]): DailyBarsUsability {
  for (const b of bars) {
    if (!isUsablePrice(b.close) || !isUsablePrice(b.high) || !isUsablePrice(b.low)) {
      return { status: "unusable" };
    }
  }
  return { status: "usable" };
}

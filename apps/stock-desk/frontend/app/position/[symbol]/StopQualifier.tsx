import {
  STOP_EXPLANATION_WITHOUT_ATR,
  STOP_EXPLANATION_WITH_ATR,
  STOP_QUALIFIER,
} from "../../lib/riskRemediationWording";

/**
 * The qualifier under the stop figure (risk remediation 4-Q) with its click-to-open
 * explanation (4-E); constraint C-10. Rendered in two places: the decision card's stop
 * cell and the key-levels panel's stop figure. The caller renders it only when the stop
 * figure is not 「—」.
 *
 * `atr14Available` picks the 4-E version (`atr14 !== null` -> with ATR). Presentation
 * floor: `text-xs text-neutral-400` (the neighbouring distance line is the baseline);
 * native `<details>`, so it is keyboard reachable and never hover-only.
 * 風控 2026-10-26 定稿；失效條件 T3.
 */
export function StopQualifier({ atr14Available }: { atr14Available: boolean }) {
  return (
    <details className="group mt-0.5 w-full">
      <summary className="inline-flex cursor-pointer list-none items-baseline gap-1 text-xs text-neutral-400 hover:text-neutral-300 [&::-webkit-details-marker]:hidden">
        <span aria-hidden="true" className="inline-block text-xs transition-transform duration-150 group-open:rotate-90">
          ▸
        </span>
        {STOP_QUALIFIER}
      </summary>
      <p className="mt-1 text-xs text-neutral-400">
        {atr14Available ? STOP_EXPLANATION_WITH_ATR : STOP_EXPLANATION_WITHOUT_ATR}
      </p>
    </details>
  );
}

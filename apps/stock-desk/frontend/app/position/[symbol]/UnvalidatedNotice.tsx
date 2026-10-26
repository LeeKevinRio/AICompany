import { UNVALIDATED_EXPLANATION, UNVALIDATED_LABEL } from "../../lib/riskRemediationWording";

/**
 * Standing 「未經歷史驗證」 label with its click-to-open explanation (risk remediation
 * 1-L / 1-X; constraint C-4). Replaces the old 「信心 {低/中/高}」 chip in both
 * `DecisionCard` and `OperationSummaryPanel`.
 *
 * Presentation floor: `text-sm text-neutral-400` is never weaker than the chip it
 * replaces; native `<details>` keeps it keyboard reachable and never hover-only.
 * 風控 2026-10-26 定稿；失效條件 T2 (rules validated by event study, or confidence returns).
 */
export function UnvalidatedNotice() {
  return (
    <details className="group">
      <summary className="inline-flex cursor-pointer list-none items-center gap-1 text-sm text-neutral-400 hover:text-neutral-300 [&::-webkit-details-marker]:hidden">
        <span aria-hidden="true" className="inline-block text-xs transition-transform duration-150 group-open:rotate-90">
          ▸
        </span>
        {UNVALIDATED_LABEL}
      </summary>
      <p className="mt-1 max-w-prose text-sm text-neutral-400">{UNVALIDATED_EXPLANATION}</p>
    </details>
  );
}

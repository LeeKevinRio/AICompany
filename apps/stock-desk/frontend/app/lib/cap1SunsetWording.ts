/**
 * #61 batch one (CEO #61/#62/#63, 2026-10-26): the front-end copy of the cap-1
 * cut to 10%. Every string is verbatim from a risk-compliance finalised table;
 * none may be edited here. The S2 migration
 * notices are **not** here — the backend fills and chooses those
 * (`app/settings/migrations.py`, 遷移未執行逐字審 I-1) and this app renders them.
 *
 * Sources:
 * - `work/reviews/2026-10-26-第1條下修告知字面逐字審-風控.md` #4a/#4b (ledger
 *   summary, 實作約束 8).
 */

import { formatPercent } from "./format";
import type { BookLimitCheck } from "./types";

/** #4a: m = 0. */
export const CAP1_LEDGER_SUMMARY_TEMPLATE = "{n} 檔持股已達或超過第 1 條上限（{threshold_pct}）。";

/** #4b: m ≥ 1 — the excluded holdings are not in {n}, and it says so. */
export const CAP1_LEDGER_SUMMARY_WITH_EXCLUDED_TEMPLATE =
  "{n} 檔持股已達或超過第 1 條上限（{threshold_pct}）；另有 {m} 檔未納入比較，不在此數內。";

/**
 * The gauge's cap-1 summary line, or `null`. `{n}` is the backend's
 * `violated_count` — counted off the same per-holding checks `worst_symbol`
 * came from, never recounted here — and `{m}` is `excluded.length`
 * (實作約束 8). Not shown when n = 0 or on any other cap.
 */
export function buildCap1LedgerSummary(check: BookLimitCheck): string | null {
  if (check.index !== 1 || check.violated_count < 1) return null;
  const excluded = check.excluded.length;
  const template = excluded === 0 ? CAP1_LEDGER_SUMMARY_TEMPLATE : CAP1_LEDGER_SUMMARY_WITH_EXCLUDED_TEMPLATE;
  return template
    .replace("{n}", String(check.violated_count))
    .replace("{threshold_pct}", formatPercent(check.threshold))
    .replace("{m}", String(excluded));
}

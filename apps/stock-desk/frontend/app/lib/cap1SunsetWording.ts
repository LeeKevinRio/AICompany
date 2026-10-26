/**
 * #61 batch one (CEO #61/#62/#63, 2026-10-26): the front-end copy of the cap-1
 * cut to 10% and of plan D's Kelly sunset. Every string is verbatim from a
 * risk-compliance finalised table; none may be edited here. The S2 migration
 * notices are **not** here — the backend fills and chooses those
 * (`app/settings/migrations.py`, 遷移未執行逐字審 I-1) and this app renders them.
 *
 * Sources:
 * - `work/reviews/2026-10-26-第1條下修告知字面逐字審-風控.md` #3 (Kelly lead),
 *   #4a/#4b (ledger summary, 實作約束 8);
 * - `work/reviews/2026-10-26-第1條上限下修審查-風控.md` 日落期間字面表 (cap 5 line).
 *
 * Batch two (5-K) must withdraw `KELLY_SUNSET_LEAD` (R-2) and
 * `CAP5_SUNSET_UNRELIABLE_NOTE` (R-3) in the same PR.
 */

import { formatPercent } from "./format";
import type { BookLimitCheck, LimitStatus } from "./types";

/**
 * Mirrors `KELLY_STALE_AFTER_DAYS` in `app/kelly/models.py` and
 * `app/advice/limits.py`; `tests/test_cap1_sunset_frontend.py` on the backend
 * reads this file and fails if the three drift apart. Interpolated into the
 * lead, never written into it (實作約束 1).
 */
export const KELLY_STALE_AFTER_DAYS = 30;

/** #3: the Kelly inputs section's lead during the sunset (replaces the old `:72`). */
export const KELLY_SUNSET_LEAD_TEMPLATE =
  "第 5 條「分數 Kelly 部位上限」使用的 win_rate／payoff_ratio 輸入。新增與修改已暫停（手填與從回測帶入皆同）；刪除仍可使用。已存在的輸入仍照原方式參與第 5 條，直到各自滿 {KELLY_STALE_AFTER_DAYS} 天過期為止。第 5 條的計算方式有誤，算出的數字不可靠；它只會讓該標的的上限比沒有第 5 條時更嚴或相同，不會更寬。刪除某筆輸入後，該標的不再受第 5 條限制，只受其他上限限制，上限可能因此比刪除前寬。";

export const KELLY_SUNSET_LEAD = KELLY_SUNSET_LEAD_TEMPLATE.replace(
  "{KELLY_STALE_AFTER_DAYS}",
  String(KELLY_STALE_AFTER_DAYS),
);

/**
 * 日落期間字面表: one sentence after cap 5's `detail`, on the same item, only
 * while cap 5 is `passed` or `violated` (the zero-allowance branch included,
 * which is a `violated`).
 */
export const CAP5_SUNSET_UNRELIABLE_NOTE = "計算方式有誤，算出的數字不可靠。";

/** Whether `CAP5_SUNSET_UNRELIABLE_NOTE` follows this cap's detail. */
export function showsCap5SunsetNote(limitId: string, status: LimitStatus): boolean {
  return limitId === "kelly_fraction" && (status === "passed" || status === "violated");
}

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

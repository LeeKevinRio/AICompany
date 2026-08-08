/**
 * Minimal trading-day gap helper for AC-C8.2's "resource is more than one
 * trading day old" prominent notice (`operationSummary.ts`).
 *
 * R4 fix (risk-final-review.md): the notice used to fire off `data.status
 * === "cached_stale"`, a *source-degradation* signal, not a data-age one —
 * a genuinely fresh `cached_stale` read on a normal trading day produced a
 * false "data is old" alarm, while a long weekend/holiday gap on a `fresh`
 * read could under-report age. This module computes the actual trading-day
 * gap from `last_bar_date` instead; `cached_stale` continues to be surfaced
 * on its own by `DataMetaStatusBadge`, unrelated to this notice.
 *
 * Deliberately not a full market calendar: only weekends and a small set of
 * fixed-date (non-lunar) holidays are modelled. Taiwan's Lunar New Year and
 * similar movable holidays are NOT covered, so this can under-count the gap
 * around those — an acceptable false negative (a missed "still normal"
 * classification never becomes a false accusation of stale data) rather than
 * a false positive.
 */

const FIXED_HOLIDAYS_MD = new Set<string>([
  "01-01", // New Year's Day
  "12-25", // Christmas
]);

function isWeekend(date: Date): boolean {
  const day = date.getUTCDay();
  return day === 0 || day === 6;
}

function isFixedHoliday(date: Date): boolean {
  const month = String(date.getUTCMonth() + 1).padStart(2, "0");
  const day = String(date.getUTCDate()).padStart(2, "0");
  return FIXED_HOLIDAYS_MD.has(`${month}-${day}`);
}

function isTradingDay(date: Date): boolean {
  return !isWeekend(date) && !isFixedHoliday(date);
}

/** Parses a `YYYY-MM-DD` (or `YYYY-MM-DDT...`) date-only prefix as a UTC calendar date. */
function parseDateOnly(value: string): Date | null {
  const match = /^(\d{4})-(\d{2})-(\d{2})/.exec(value);
  if (!match) return null;
  const [, y, m, d] = match;
  const parsed = new Date(Date.UTC(Number(y), Number(m) - 1, Number(d)));
  return Number.isNaN(parsed.getTime()) ? null : parsed;
}

/**
 * Number of trading days strictly after `lastBarDate` up to and including
 * `now`'s own calendar date. Returns 0 when `lastBarDate` cannot be parsed
 * or is not before `now` (never a negative gap, never a false trigger from a
 * malformed date).
 */
export function tradingDaysSince(lastBarDate: string, now: Date = new Date()): number {
  const start = parseDateOnly(lastBarDate);
  if (start === null) return 0;
  const end = new Date(Date.UTC(now.getUTCFullYear(), now.getUTCMonth(), now.getUTCDate()));
  if (end.getTime() <= start.getTime()) return 0;

  let count = 0;
  const cursor = new Date(start.getTime());
  while (cursor.getTime() < end.getTime()) {
    cursor.setUTCDate(cursor.getUTCDate() + 1);
    if (isTradingDay(cursor)) count += 1;
  }
  return count;
}

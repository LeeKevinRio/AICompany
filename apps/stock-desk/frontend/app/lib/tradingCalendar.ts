/**
 * Data-age heuristic backing AC-C8.2's "resource is more than one trading
 * day old" prominent notice (`operationSummary.ts`).
 *
 * R4 fix (risk-final-review.md): the notice used to fire off `data.status
 * === "cached_stale"`, a *source-degradation* signal, not a data-age one —
 * a genuinely fresh `cached_stale` read on a normal trading day produced a
 * false "data is old" alarm, while a long weekend/holiday gap on a `fresh`
 * read could under-report age. This module computes the age of
 * `last_bar_date` instead; `cached_stale` continues to be surfaced on its
 * own by `DataMetaStatusBadge`, unrelated to this notice.
 *
 * B1 fix (risk-fix-review.md): the R4 replacement modelled a trading-day
 * gap by enumerating weekends plus two fixed-date holidays (New Year's Day
 * and — wrongly, it is not a TWSE holiday — Christmas). Taiwan's Lunar New
 * Year and other movable/adjusted holidays were NOT modelled, so every
 * unmodelled closed day was counted as a trading day. That is an
 * OVER-count of the gap, not the "under-count / false-negative-only" safety
 * direction the previous header claimed — on the first trading day after a
 * multi-day closure this produced exactly the false "data is old" alarm R4
 * was meant to eliminate, and it recurs every year around Lunar New Year.
 *
 * Rather than try to enumerate every movable TWSE holiday (fragile, needs
 * yearly upkeep, and the backend does not expose a trading calendar via the
 * advice/bars API today — see `apps/stock-desk/backend/app/api/advice.py`
 * and `app/api/bars.py`, neither returns anything calendar-shaped), this
 * module deliberately drops trading-day modelling entirely and instead
 * counts plain CALENDAR days elapsed since `last_bar_date`, firing only
 * once that exceeds `STALE_CALENDAR_DAY_THRESHOLD` — a buffer wide enough
 * to absorb TWSE's longest realistic continuous closure (Lunar New Year
 * plus its adjoining weekends, historically up to ~10 calendar days).
 *
 * This is a deliberate, documented trade-off, not an oversight: a genuine
 * data outage lasting a handful of trading days *within* a normal
 * (non-holiday) week will NOT be flagged by this check, because its
 * calendar-day span stays under the buffer — an accepted false negative.
 * It is chosen because the cost of the false "data is old" alarm this
 * module used to produce every long-weekend/holiday (a real recurring
 * regression, confusing on the very first day trading resumes) outweighs
 * briefly under-reporting genuine short staleness. If the backend ever
 * exposes an actual trading-calendar / previous-trading-day field on the
 * as-of response, prefer that over this heuristic.
 *
 * Timezone note (N1, risk-fix-review.md): `last_bar_date` arrives as a
 * plain `YYYY-MM-DD` trading date (TWSE's own local calendar date, no
 * timezone attached). `now` is the caller's local clock, which in this
 * codebase always runs in the browser/Node process's own zone — NOT
 * necessarily Taipei. To avoid an off-by-one day near local midnight for a
 * TWSE product, `now` is explicitly converted to its Asia/Taipei (UTC+8,
 * no DST) calendar date via a fixed +8h offset before diffing, rather than
 * relying on the environment's own timezone or raw UTC.
 */

/** TWSE's longest realistic continuous closure, in calendar days. See header. */
export const STALE_CALENDAR_DAY_THRESHOLD = 10;

const DAY_MS = 24 * 60 * 60 * 1000;
const TAIPEI_UTC_OFFSET_MS = 8 * 60 * 60 * 1000;

/** Parses a `YYYY-MM-DD` (or `YYYY-MM-DDT...`) date-only prefix as a UTC calendar date. */
function parseDateOnly(value: string): Date | null {
  const match = /^(\d{4})-(\d{2})-(\d{2})/.exec(value);
  if (!match) return null;
  const [, y, m, d] = match;
  const parsed = new Date(Date.UTC(Number(y), Number(m) - 1, Number(d)));
  return Number.isNaN(parsed.getTime()) ? null : parsed;
}

/**
 * Converts an instant to its Asia/Taipei (UTC+8, no DST) calendar date,
 * represented as a UTC-midnight `Date` so it can be diffed against a
 * `parseDateOnly` result on equal footing (see the N1 timezone note above).
 */
function toTaipeiCalendarDate(date: Date): Date {
  const shifted = new Date(date.getTime() + TAIPEI_UTC_OFFSET_MS);
  return new Date(Date.UTC(shifted.getUTCFullYear(), shifted.getUTCMonth(), shifted.getUTCDate()));
}

/**
 * Plain calendar days elapsed between `lastBarDate` and `now`'s Taipei
 * calendar date. Returns 0 when `lastBarDate` cannot be parsed or is not
 * before `now` (never negative, never a false trigger from a malformed or
 * future-dated value).
 */
export function calendarDaysSince(lastBarDate: string, now: Date = new Date()): number {
  const start = parseDateOnly(lastBarDate);
  if (start === null) return 0;
  const end = toTaipeiCalendarDate(now);
  const diffMs = end.getTime() - start.getTime();
  if (diffMs <= 0) return 0;
  return Math.round(diffMs / DAY_MS);
}

/**
 * Whether `last_bar_date` is stale enough to warrant AC-C8.2's prominent
 * notice. See the module header for the calendar-day-threshold trade-off
 * this encodes.
 */
export function isDataStaleByCalendar(lastBarDate: string, now: Date = new Date()): boolean {
  return calendarDaysSince(lastBarDate, now) > STALE_CALENDAR_DAY_THRESHOLD;
}

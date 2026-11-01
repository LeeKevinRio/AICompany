/**
 * Asia/Taipei calendar-day arithmetic for R-4 (風控 Q11: a formal check set
 * held from an earlier Taipei calendar day is no longer trusted).
 *
 * Fixed UTC+8 arithmetic — Taiwan has had no DST since 1979 — rather than
 * `Intl`, so the result is a pure function of the epoch milliseconds: it cannot
 * vary with the browser's own time zone, and it is exact at the boundary
 * (15:59:59.999Z is still the old day, 16:00:00.000Z the new one). Both ends of
 * every comparison must come from the same client clock (`Date.now()` and
 * TanStack's `dataUpdatedAt`); a wrong system clock moves the day boundary with
 * it, which is accepted and recorded (tech-architect Q14 前提 2).
 */

const TAIPEI_OFFSET_MS = 8 * 60 * 60 * 1000;
const DAY_MS = 24 * 60 * 60 * 1000;

/** Whole days since 1970-01-01 on the Taipei calendar (a comparable day id). */
export function taipeiDayKey(epochMs: number): number {
  return Math.floor((epochMs + TAIPEI_OFFSET_MS) / DAY_MS);
}

export function isSameTaipeiDay(a: number, b: number): boolean {
  return taipeiDayKey(a) === taipeiDayKey(b);
}

/** Epoch ms of the first instant of the Taipei day after the one containing `epochMs`. */
export function nextTaipeiMidnight(epochMs: number): number {
  return (taipeiDayKey(epochMs) + 1) * DAY_MS - TAIPEI_OFFSET_MS;
}

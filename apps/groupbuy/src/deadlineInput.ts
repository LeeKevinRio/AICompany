// UI ↔ storage boundary helpers for the group deadline field.
//
// Storage format is unchanged by this file: `deadlineAt` on a Group is (and remains)
// an absolute epoch millisecond number (or undefined = no deadline). All countdown /
// auto-close semantics live in deadline.ts and are untouched here — this module only
// converts between that stored epoch value and the string a native
// <input type="datetime-local"> works with, plus a 24-hour display formatter.

/** Zero-pad a number to at least 2 digits (e.g. 5 -> "05"). */
function pad2(n: number): string {
  return String(n).padStart(2, '0');
}

/**
 * Convert a Date (read as local wall-clock time) into the value string a
 * <input type="datetime-local"> expects: "YYYY-MM-DDTHH:mm".
 */
export function dateToDatetimeLocalValue(d: Date): string {
  return `${d.getFullYear()}-${pad2(d.getMonth() + 1)}-${pad2(d.getDate())}T${pad2(
    d.getHours(),
  )}:${pad2(d.getMinutes())}`;
}

/**
 * Convert epoch milliseconds into a <input type="datetime-local"> value string,
 * for pre-filling the field from an already-stored deadlineAt.
 */
export function epochToDatetimeLocalValue(epochMs: number): string {
  return dateToDatetimeLocalValue(new Date(epochMs));
}

/**
 * Convert a <input type="datetime-local"> value (local wall-clock string, no
 * timezone) into epoch milliseconds. Empty string or an unparsable value -> undefined
 * (= no deadline set), matching the existing optional `deadlineAt` semantics.
 */
export function datetimeLocalValueToEpoch(value: string): number | undefined {
  if (!value) return undefined;
  const ts = new Date(value).getTime();
  return Number.isFinite(ts) ? ts : undefined;
}

/**
 * Human-readable absolute date/time for display, always in 24-hour clock.
 * Plain `Date#toLocaleString('zh-TW')` defaults to a 12-hour clock with 上午/下午
 * markers, which is exactly the "unclear time format" complaint — force `hour12:
 * false` here so every place that shows an absolute deadline reads unambiguously.
 */
export function formatDeadlineDateTime(epochMs: number): string {
  return new Date(epochMs).toLocaleString('zh-TW', {
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
    hour12: false,
  });
}

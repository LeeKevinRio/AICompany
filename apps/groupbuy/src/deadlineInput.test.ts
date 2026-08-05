import { describe, expect, it } from 'vitest';
import {
  dateToDatetimeLocalValue,
  datetimeLocalValueToEpoch,
  epochToDatetimeLocalValue,
  formatDeadlineDateTime,
} from './deadlineInput';

describe('dateToDatetimeLocalValue', () => {
  it('formats as YYYY-MM-DDTHH:mm with zero-padding', () => {
    const d = new Date(2026, 0, 5, 8, 3); // 2026-01-05 08:03 local time
    expect(dateToDatetimeLocalValue(d)).toBe('2026-01-05T08:03');
  });
});

describe('datetimeLocalValueToEpoch', () => {
  it('parses a datetime-local value into epoch ms matching the same local Date', () => {
    const d = new Date(2026, 6, 20, 20, 0); // 2026-07-20 20:00 local time
    const value = dateToDatetimeLocalValue(d);
    expect(datetimeLocalValueToEpoch(value)).toBe(d.getTime());
  });

  it('returns undefined for an empty string (no deadline set)', () => {
    expect(datetimeLocalValueToEpoch('')).toBeUndefined();
  });

  it('returns undefined for an unparsable value', () => {
    expect(datetimeLocalValueToEpoch('not-a-date')).toBeUndefined();
  });
});

describe('epochToDatetimeLocalValue / datetimeLocalValueToEpoch roundtrip', () => {
  it('roundtrips epoch -> input value -> epoch losslessly (minute precision)', () => {
    const d = new Date(2026, 11, 31, 23, 59);
    const epoch = d.getTime();
    const value = epochToDatetimeLocalValue(epoch);
    expect(datetimeLocalValueToEpoch(value)).toBe(epoch);
  });
});

describe('formatDeadlineDateTime', () => {
  it('always renders a 24-hour clock (no AM/PM marker), even for an afternoon time', () => {
    const d = new Date(2026, 7, 5, 20, 5); // 20:05 local time (would be "下午8:05" in 12h)
    const formatted = formatDeadlineDateTime(d.getTime());
    expect(formatted).toContain('20:05');
    expect(formatted).not.toMatch(/上午|下午|AM|PM/i);
  });

  it('zero-pads a single-digit hour to 24-hour format (e.g. 08:00, not 8:00 AM)', () => {
    const d = new Date(2026, 7, 5, 8, 0);
    const formatted = formatDeadlineDateTime(d.getTime());
    expect(formatted).toContain('08:00');
    expect(formatted).not.toMatch(/上午|下午|AM|PM/i);
  });
});

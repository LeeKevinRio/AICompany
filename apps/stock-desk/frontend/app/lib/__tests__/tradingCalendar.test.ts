import { describe, expect, it } from "vitest";
import { calendarDaysSince, isDataStaleByCalendar, STALE_CALENDAR_DAY_THRESHOLD } from "../tradingCalendar";

describe("calendarDaysSince", () => {
  it("returns 0 when last_bar_date is today", () => {
    expect(calendarDaysSince("2026-08-06", new Date(Date.UTC(2026, 7, 6, 12)))).toBe(0);
  });

  it("returns 0 when last_bar_date is in the future relative to now", () => {
    expect(calendarDaysSince("2026-08-07", new Date(Date.UTC(2026, 7, 6, 12)))).toBe(0);
  });

  it("returns 0 for an unparsable date, never a false trigger", () => {
    expect(calendarDaysSince("not-a-date", new Date(Date.UTC(2026, 7, 6, 12)))).toBe(0);
  });

  it("counts a plain next-day gap (Thursday -> Friday) as 1", () => {
    // 2026-08-06 is a Thursday, 2026-08-07 is a Friday.
    const gap = calendarDaysSince("2026-08-06", new Date(Date.UTC(2026, 7, 7, 12)));
    expect(gap).toBe(1);
  });

  it("counts a weekend span (Friday -> following Monday) as 3 calendar days", () => {
    // 2026-08-07 is a Friday, 2026-08-10 is the following Monday.
    const gap = calendarDaysSince("2026-08-07", new Date(Date.UTC(2026, 7, 10, 12)));
    expect(gap).toBe(3);
  });

  it("counts a genuine multi-trading-day outage in a normal week as its raw calendar-day span", () => {
    // 2026-08-07 Fri -> 2026-08-11 Tue: no holiday involved, 4 calendar days elapsed.
    const gap = calendarDaysSince("2026-08-07", new Date(Date.UTC(2026, 7, 11, 12)));
    expect(gap).toBe(4);
  });

  it("[N1] treats `now` as its Asia/Taipei calendar date, not its raw UTC date", () => {
    // 2026-08-06T16:30:00Z is already 2026-08-07T00:30 in Taipei (UTC+8) —
    // a naive UTC-date comparison would still see 2026-08-06 and report a
    // 0-day gap; the Taipei-aware conversion must report 1.
    const nowJustAfterTaipeiMidnight = new Date(Date.UTC(2026, 7, 6, 16, 30));
    expect(calendarDaysSince("2026-08-06", nowJustAfterTaipeiMidnight)).toBe(1);
  });

  it("[N1] does not roll over a day early for an instant still before Taipei midnight", () => {
    // 2026-08-06T15:59:00Z is 2026-08-06T23:59 in Taipei — still the same
    // Taipei calendar day as the bar date, so the gap must stay 0.
    const nowJustBeforeTaipeiMidnight = new Date(Date.UTC(2026, 7, 6, 15, 59));
    expect(calendarDaysSince("2026-08-06", nowJustBeforeTaipeiMidnight)).toBe(0);
  });
});

describe("isDataStaleByCalendar", () => {
  it("does not flag a normal weekend gap", () => {
    // Friday -> following Monday: 3 calendar days, well under the buffer.
    expect(isDataStaleByCalendar("2026-08-07", new Date(Date.UTC(2026, 7, 10, 12)))).toBe(false);
  });

  it("[B1] does not flag the first trading day after an unmodelled long holiday (simulated Lunar New Year closure)", () => {
    // Simulates a ~9-calendar-day Lunar New Year closure: last bar the
    // Friday before the holiday, market reopens the second Monday after —
    // none of the intervening days are modelled as holidays by this module
    // (see header), but the calendar-day gap (9) stays under the buffer, so
    // this must NOT trigger the stale-data notice.
    const lastBarBeforeHoliday = "2026-02-13"; // Friday
    const firstTradingDayBack = new Date(Date.UTC(2026, 1, 22, 12)); // second following Monday
    expect(calendarDaysSince(lastBarBeforeHoliday, firstTradingDayBack)).toBe(9);
    expect(isDataStaleByCalendar(lastBarBeforeHoliday, firstTradingDayBack)).toBe(false);
  });

  it("does not flag exactly at the threshold (gap == STALE_CALENDAR_DAY_THRESHOLD)", () => {
    const now = new Date(Date.UTC(2026, 7, 6 + STALE_CALENDAR_DAY_THRESHOLD, 12));
    expect(calendarDaysSince("2026-08-06", now)).toBe(STALE_CALENDAR_DAY_THRESHOLD);
    expect(isDataStaleByCalendar("2026-08-06", now)).toBe(false);
  });

  it("flags a gap exceeding the threshold as stale (e.g. a genuinely broken feed)", () => {
    const now = new Date(Date.UTC(2026, 7, 6 + STALE_CALENDAR_DAY_THRESHOLD + 1, 12));
    expect(calendarDaysSince("2026-08-06", now)).toBe(STALE_CALENDAR_DAY_THRESHOLD + 1);
    expect(isDataStaleByCalendar("2026-08-06", now)).toBe(true);
  });
});

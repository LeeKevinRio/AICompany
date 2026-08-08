import { describe, expect, it } from "vitest";
import { tradingDaysSince } from "../tradingCalendar";

describe("tradingDaysSince", () => {
  it("returns 0 when last_bar_date is today", () => {
    expect(tradingDaysSince("2026-08-06", new Date(Date.UTC(2026, 7, 6, 12)))).toBe(0);
  });

  it("returns 0 when last_bar_date is in the future relative to now", () => {
    expect(tradingDaysSince("2026-08-07", new Date(Date.UTC(2026, 7, 6, 12)))).toBe(0);
  });

  it("returns 0 for an unparsable date, never a false trigger", () => {
    expect(tradingDaysSince("not-a-date", new Date(Date.UTC(2026, 7, 6, 12)))).toBe(0);
  });

  it("counts a normal next-trading-day gap (Thursday -> Friday) as 1, not stale", () => {
    // 2026-08-06 is a Thursday, 2026-08-07 is a Friday.
    const gap = tradingDaysSince("2026-08-06", new Date(Date.UTC(2026, 7, 7, 12)));
    expect(gap).toBe(1);
  });

  it("counts Friday's bar as still fresh on the following Monday (weekend does not add gap)", () => {
    // 2026-08-07 is a Friday, 2026-08-10 is the following Monday.
    const gap = tradingDaysSince("2026-08-07", new Date(Date.UTC(2026, 7, 10, 12)));
    expect(gap).toBe(1);
  });

  it("flags a bar two trading days old (Friday -> Tuesday) as stale", () => {
    // 2026-08-07 Fri -> 2026-08-11 Tue: Mon (10th) and Tue (11th) are trading days => gap 2.
    const gap = tradingDaysSince("2026-08-07", new Date(Date.UTC(2026, 7, 11, 12)));
    expect(gap).toBe(2);
    expect(gap).toBeGreaterThan(1);
  });

  it("skips a fixed-date holiday inside the range (Christmas)", () => {
    // 2026-12-24 Thu -> 2026-12-26 Sat: Dec 25 is a holiday (skipped), Dec 26 is a
    // weekend (skipped) => gap 0, none of the days in between are trading days.
    const gap = tradingDaysSince("2026-12-24", new Date(Date.UTC(2026, 11, 26, 12)));
    expect(gap).toBe(0);
  });

  it("counts the first trading day after a holiday correctly", () => {
    // 2026-12-24 Thu -> 2026-12-28 Mon: Dec 25 (holiday, skip), Dec 26-27 (weekend,
    // skip), Dec 28 (Monday, counts) => gap 1, not stale.
    const gap = tradingDaysSince("2026-12-24", new Date(Date.UTC(2026, 11, 28, 12)));
    expect(gap).toBe(1);
  });
});

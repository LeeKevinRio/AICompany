import { describe, expect, it } from "vitest";
import { isDataStaleByTradingDays, STALE_TRADING_DAY_THRESHOLD } from "../tradingCalendar";

/**
 * C4 (2026-08-13): the browser no longer models trading days at all — the
 * backend publishes `data.trading_days_behind` from an observed calendar, and
 * this module only applies the threshold. The tests that used to pin the
 * calendar-day arithmetic (weekend spans, the Asia/Taipei rollover, the >10
 * buffer) moved to `backend/tests/test_market_calendar_staleness.py`, where
 * the calendar now lives; what is left to pin here is the threshold and the
 * two non-firing cases.
 */
describe("isDataStaleByTradingDays", () => {
  it("keeps the threshold the 風控複審 asked for: one missed session", () => {
    expect(STALE_TRADING_DAY_THRESHOLD).toBe(1);
  });

  it("does not flag a series the market has not moved past", () => {
    expect(isDataStaleByTradingDays(0)).toBe(false);
  });

  it("flags a single missed session (the threshold boundary)", () => {
    expect(isDataStaleByTradingDays(STALE_TRADING_DAY_THRESHOLD)).toBe(true);
  });

  it("flags a multi-session outage", () => {
    expect(isDataStaleByTradingDays(4)).toBe(true);
  });

  it("[fail-safe] treats an unknown gap as not-stale, never as stale", () => {
    // `null` is what the backend reports when no trading calendar could be
    // consulted. Guessing "old" there is the false alarm B1 was raised about;
    // guessing "fresh" would be a claim nobody made. Neither is asserted — the
    // notice simply does not fire.
    expect(isDataStaleByTradingDays(null)).toBe(false);
  });

  it("[fail-safe] does not flag an unmodelled closure, which reports 0 sessions", () => {
    // 農曆年 / 颱風假 / an ad-hoc suspension produces no bars, so the backend
    // counts no sessions and the gap arrives as 0 — the exact case that used
    // to fire a false 「資料過舊」 alarm on the first trading day back.
    expect(isDataStaleByTradingDays(0)).toBe(false);
  });
});

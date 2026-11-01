/** FE-T9: the Taipei calendar-day boundary, independent of the host time zone. */

import { afterEach, describe, expect, it, vi } from "vitest";
import { isSameTaipeiDay, nextTaipeiMidnight, taipeiDayKey } from "../taipeiDay";

const LAST_MS = Date.UTC(2026, 7, 11, 15, 59, 59, 999); // 2026-08-11 23:59:59.999 +08:00
const FIRST_MS = Date.UTC(2026, 7, 11, 16, 0, 0, 0); // 2026-08-12 00:00:00.000 +08:00

afterEach(() => {
  vi.unstubAllEnvs();
});

describe("Asia/Taipei day arithmetic", () => {
  it("splits the day at 15:59:59.999Z / 16:00:00.000Z", () => {
    expect(isSameTaipeiDay(LAST_MS, FIRST_MS)).toBe(false);
    expect(taipeiDayKey(FIRST_MS)).toBe(taipeiDayKey(LAST_MS) + 1);
    expect(isSameTaipeiDay(LAST_MS - 1, LAST_MS)).toBe(true);
    expect(isSameTaipeiDay(FIRST_MS, FIRST_MS + 1)).toBe(true);
  });

  it("treats 00:00 and 23:59:59.999 Taipei as one day", () => {
    const start = Date.UTC(2026, 7, 10, 16, 0, 0, 0); // 2026-08-11 00:00 +08:00
    expect(isSameTaipeiDay(start, LAST_MS)).toBe(true);
    expect(isSameTaipeiDay(start - 1, start)).toBe(false);
  });

  it("nextTaipeiMidnight is the first instant of the following Taipei day", () => {
    expect(nextTaipeiMidnight(LAST_MS)).toBe(FIRST_MS);
    expect(nextTaipeiMidnight(Date.UTC(2026, 7, 11, 4, 0, 0))).toBe(FIRST_MS);
    expect(nextTaipeiMidnight(Date.UTC(2026, 7, 10, 16, 0, 0, 0))).toBe(FIRST_MS);
    // At the boundary itself the next midnight is a full day later.
    expect(nextTaipeiMidnight(FIRST_MS)).toBe(FIRST_MS + 24 * 60 * 60 * 1000);
  });

  it("gives the same answers whatever time zone the host runs in", () => {
    for (const tz of ["UTC", "Asia/Taipei", "America/Los_Angeles", "Pacific/Kiritimati"]) {
      vi.stubEnv("TZ", tz);
      expect(isSameTaipeiDay(LAST_MS, FIRST_MS)).toBe(false);
      expect(isSameTaipeiDay(FIRST_MS, FIRST_MS + 86_399_999)).toBe(true);
      expect(nextTaipeiMidnight(LAST_MS)).toBe(FIRST_MS);
    }
  });

  it("is a function of the epoch alone (no Date, no Intl)", async () => {
    const { readFileSync } = await import("node:fs");
    const { dirname, resolve } = await import("node:path");
    const { fileURLToPath } = await import("node:url");
    const source = readFileSync(
      resolve(dirname(fileURLToPath(import.meta.url)), "../taipeiDay.ts"),
      "utf-8",
    ).replace(/\/\*[\s\S]*?\*\//g, "");
    expect(source).not.toMatch(/new Date|Date\.now|Intl\./);
  });
});

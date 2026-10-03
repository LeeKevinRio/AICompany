import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { afterEach, describe, expect, it, vi } from "vitest";
import {
  DataStatusBadge,
  STALE_CACHE_FALLBACK_REASON,
  priceDateTooltip,
} from "../../components/DataStatusBadge";
import { formatTradingDateMonthDay } from "../format";
import type { PositionPrice } from "../types";

/**
 * CEO 2026-10-02「先修延遲標示」: the home-page holdings table used to print
 * "資料延遲 N 分鐘" computed from a bare trading date read as UTC midnight
 * (1000–4000+ minutes even on a current cache). The badge now shows the
 * trading date as "MM/DD 收盤", warns "資料較舊" only for a cache known (or
 * not known) to be behind, and never mentions minutes of delay.
 */
describe("DataStatusBadge — trading date and honest freshness label", () => {
  function price(overrides: Partial<PositionPrice>): PositionPrice {
    return {
      value: "550",
      as_of: "2026-09-30",
      source: "twse",
      price_kind: "daily_close",
      data_status: "fresh",
      is_within_ttl: null,
      reason: null,
      ...overrides,
    };
  }

  function render(p: PositionPrice | null): string {
    return renderToStaticMarkup(createElement(DataStatusBadge, { price: p }));
  }

  afterEach(() => {
    vi.unstubAllEnvs();
  });

  it("fresh shows only the trading date, no warning label", () => {
    const html = render(price({ data_status: "fresh" }));
    expect(html).toContain("09/30 收盤");
    expect(html).not.toContain("資料較舊");
    expect(html).not.toContain("備援源");
    expect(html).not.toContain("資料不足");
  });

  it("cached_stale + is_within_ttl === true is treated as current: no warning label", () => {
    const html = render(price({ data_status: "cached_stale", is_within_ttl: true }));
    expect(html).toContain("09/30 收盤");
    expect(html).not.toContain("資料較舊");
    expect(html).not.toContain("title=");
  });

  it("cached_stale + is_within_ttl === false shows 資料較舊 with the reason as title", () => {
    const html = render(
      price({
        data_status: "cached_stale",
        is_within_ttl: false,
        reason: "最近一次更新失敗，沿用快取。",
      }),
    );
    expect(html).toContain("資料較舊");
    expect(html).toContain('title="最近一次更新失敗，沿用快取。"');
    expect(html).toContain("09/30 收盤");
  });

  it("cached_stale with no reason falls back to 可能未含最近交易日", () => {
    for (const isWithinTtl of [false, null] as const) {
      for (const reason of [null, "", "  "]) {
        const html = render(
          price({ data_status: "cached_stale", is_within_ttl: isWithinTtl, reason }),
        );
        expect(html).toContain("資料較舊");
        expect(html).toContain(`title="${STALE_CACHE_FALLBACK_REASON}"`);
      }
    }
    expect(STALE_CACHE_FALLBACK_REASON).toBe("可能未含最近交易日");
  });

  it("backup and unavailable keep their existing labels", () => {
    expect(render(price({ data_status: "backup" }))).toContain("備援源");
    expect(render(price({ data_status: "unavailable" }))).toContain("資料不足");
    expect(render(null)).toContain("資料不足");
  });

  it("never mentions 延遲 or 分鐘, in any state", () => {
    const states: PositionPrice[] = [
      price({ data_status: "fresh" }),
      price({ data_status: "backup" }),
      price({ data_status: "cached_stale", is_within_ttl: true }),
      price({ data_status: "cached_stale", is_within_ttl: false, reason: "原因" }),
      price({ data_status: "cached_stale", is_within_ttl: null }),
      price({ data_status: "unavailable" }),
    ];
    for (const p of states) {
      const html = render(p);
      expect(html).not.toContain("延遲");
      expect(html).not.toContain("分鐘");
    }
    expect(render(null)).not.toContain("延遲");
  });

  it("the component no longer imports staleMinutesSince or calls new Date()", () => {
    const source = readFileSync(
      fileURLToPath(new URL("../../components/DataStatusBadge.tsx", import.meta.url)),
      "utf-8",
    );
    expect(source).not.toContain("staleMinutesSince");
    expect(source).not.toContain("new Date(");
  });

  it("the date is the calendar date in the string regardless of the process timezone", () => {
    for (const tz of ["UTC", "Asia/Taipei", "America/Los_Angeles", "Pacific/Kiritimati"]) {
      vi.stubEnv("TZ", tz);
      expect(formatTradingDateMonthDay("2026-09-30")).toBe("09/30");
      expect(formatTradingDateMonthDay("2026-01-01")).toBe("01/01");
      expect(render(price({ as_of: "2026-01-01" }))).toContain("01/01 收盤");
    }
  });

  it("an unparseable as_of is shown as-is rather than guessed at", () => {
    expect(formatTradingDateMonthDay("not-a-date")).toBe("not-a-date");
  });
});

describe("PositionsTable price tooltip — date only, no invented time of day", () => {
  it("formats as 資料日期 MM/DD（日線收盤，非即時）", () => {
    expect(priceDateTooltip("2026-09-30")).toBe("資料日期 09/30（日線收盤，非即時）");
  });

  it("PositionsTable no longer runs the price date through formatDateTime", () => {
    const source = readFileSync(
      fileURLToPath(new URL("../../components/PositionsTable.tsx", import.meta.url)),
      "utf-8",
    );
    expect(source).not.toContain("formatDateTime");
    expect(source).toContain("priceDateTooltip(valuation.price.as_of)");
  });
});

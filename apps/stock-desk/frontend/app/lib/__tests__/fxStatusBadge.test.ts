import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { afterEach, describe, expect, it, vi } from "vitest";
import { STALE_CACHE_FALLBACK_REASON } from "../../components/DataStatusBadge";
import { FxStatusBadge } from "../../components/FxStatusBadge";
import type { PositionFx } from "../types";

/**
 * ADR-0011 匯率梯子揭露 + CEO 2026-10-03 匯率標示修正: the badge used to print
 * "匯率 資料延遲 N 分鐘" computed from a bare rate date read as UTC midnight
 * (1000+ minutes even on a current rate). It now shows the rate date as
 * "MM/DD 匯率", warns "資料較舊" only for a rate known (or not known) to be
 * behind, and never mentions minutes of delay. It reuses `DataStatusBadge`'s
 * literals ("備援源" / "資料較舊" / "資料不足") and invents none of its own.
 * `fresh` gets no warning label, and a `null` `fx` (a TWD position) renders
 * nothing at all.
 */
describe("FxStatusBadge — rate date and honest freshness label", () => {
  function fx(overrides: Partial<PositionFx>): PositionFx {
    return {
      pair: "USDTWD",
      as_of: "2026-10-02",
      source: "bank_of_taiwan",
      data_status: "fresh",
      source_note: "",
      is_within_ttl: null,
      reason: null,
      ...overrides,
    };
  }

  function render(value: PositionFx | null): string {
    return renderToStaticMarkup(createElement(FxStatusBadge, { fx: value }));
  }

  /** Visible text only: tags (and their attributes, e.g. `title`) stripped. */
  function text(value: PositionFx | null): string {
    return render(value).replace(/<[^>]*>/g, "");
  }

  afterEach(() => {
    vi.unstubAllEnvs();
  });

  it("fx === null renders nothing (a TWD position, no conversion)", () => {
    expect(render(null)).toBe("");
  });

  it("fresh shows only the rate date, no warning label", () => {
    const html = render(fx({ data_status: "fresh" }));
    expect(text(fx({ data_status: "fresh" }))).toBe("10/02 匯率");
    expect(html).not.toContain("資料較舊");
    expect(html).not.toContain("rounded");
  });

  it("cached_stale with an up-to-date cache gets no warning label", () => {
    expect(text(fx({ data_status: "cached_stale", is_within_ttl: true }))).toBe("10/02 匯率");
  });

  it("cached_stale known to be behind shows 資料較舊 with the reason as title", () => {
    const html = render(
      fx({ data_status: "cached_stale", is_within_ttl: false, reason: "快取未含最近一個交易日。" }),
    );
    expect(text(fx({ data_status: "cached_stale", is_within_ttl: false }))).toBe(
      "10/02 匯率資料較舊",
    );
    expect(html).toContain('title="快取未含最近一個交易日。"');
    expect(html).toContain("bg-neutral-800");
  });

  it("cached_stale without a reason falls back to 可能未含最近交易日", () => {
    for (const reason of [null, "", "   "]) {
      const html = render(fx({ data_status: "cached_stale", is_within_ttl: null, reason }));
      expect(html).toContain("資料較舊");
      expect(html).toContain(`title="${STALE_CACHE_FALLBACK_REASON}"`);
    }
    expect(STALE_CACHE_FALLBACK_REASON).toBe("可能未含最近交易日");
  });

  it("backup keeps the amber 備援源 badge and source_note as title", () => {
    const value = fx({
      data_status: "backup",
      source: "yfinance_fx",
      source_note: "匯率取自 Yahoo Finance 的每日收盤價。",
    });
    const html = render(value);
    expect(text(value)).toBe("10/02 匯率備援源");
    expect(html).toContain("bg-amber-900/40");
    expect(html).toContain("text-amber-300");
    expect(html).toContain('title="匯率取自 Yahoo Finance 的每日收盤價。"');
  });

  it("unavailable (no rate, no date) keeps 匯率 資料不足", () => {
    const value = fx({ data_status: "unavailable", as_of: null, source: "none", source_note: "" });
    expect(text(value)).toBe("匯率 資料不足");
    expect(render(value)).not.toContain("title=");
  });

  it("the word 匯率 never appears twice", () => {
    for (const status of ["fresh", "backup", "cached_stale", "unavailable"] as const) {
      for (const as_of of ["2026-10-02", null]) {
        const visible = text(fx({ data_status: status, as_of }));
        expect(visible.split("匯率").length - 1).toBeLessThanOrEqual(1);
      }
    }
  });

  it("never mentions delay or minutes, in any state", () => {
    for (const status of ["fresh", "backup", "cached_stale", "unavailable"] as const) {
      for (const is_within_ttl of [true, false, null]) {
        const html = render(fx({ data_status: status, is_within_ttl }));
        expect(html).not.toContain("延遲");
        expect(html).not.toContain("分鐘");
      }
    }
  });

  it("never invents user-facing literals beyond the shared vocabulary", () => {
    for (const status of ["fresh", "backup", "cached_stale", "unavailable"] as const) {
      const visible = text(fx({ data_status: status }));
      expect(visible).toMatch(/^(\d{2}\/\d{2} 匯率)?(備援源|資料較舊|(匯率 )?資料不足)?$/);
    }
  });

  it("the date is the calendar date in the string regardless of the process timezone", () => {
    for (const tz of ["UTC", "Asia/Taipei", "America/Los_Angeles", "Pacific/Kiritimati"]) {
      vi.stubEnv("TZ", tz);
      expect(text(fx({ as_of: "2026-10-02" }))).toBe("10/02 匯率");
      expect(text(fx({ as_of: "2026-01-01" }))).toBe("01/01 匯率");
    }
  });

  it("the component no longer imports staleMinutesSince or calls new Date()", () => {
    const source = readFileSync(
      fileURLToPath(new URL("../../components/FxStatusBadge.tsx", import.meta.url)),
      "utf-8",
    );
    expect(source).not.toContain("staleMinutesSince");
    expect(source).not.toContain("new Date(");
  });
});

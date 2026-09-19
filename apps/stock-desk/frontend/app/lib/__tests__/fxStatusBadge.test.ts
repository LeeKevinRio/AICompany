import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";
import { FxStatusBadge } from "../../components/FxStatusBadge";
import type { PositionFx } from "../types";

/**
 * ADR-0011 匯率梯子揭露: `FxStatusBadge` reuses `DataStatusBadge`'s exact
 * literals ("備援源" / "資料不足" / "資料延遲 N 分鐘") — it invents none of
 * its own, per the frontend-engineer B task's red line. `fresh` renders
 * nothing, same "無標" convention as the price badge, and a `null` `fx`
 * (a TWD position) renders nothing at all.
 */
describe("FxStatusBadge — four-state ADR-0011 fx ladder", () => {
  function fx(overrides: Partial<PositionFx>): PositionFx {
    return {
      pair: "USDTWD",
      as_of: "2026-09-18",
      source: "bank_of_taiwan",
      data_status: "fresh",
      source_note: "",
      ...overrides,
    };
  }

  it("fx === null renders nothing (a TWD position, no conversion)", () => {
    expect(renderToStaticMarkup(createElement(FxStatusBadge, { fx: null }))).toBe("");
  });

  it("fresh renders nothing", () => {
    const html = renderToStaticMarkup(
      createElement(FxStatusBadge, { fx: fx({ data_status: "fresh" }) }),
    );
    expect(html).toBe("");
  });

  it("backup renders the amber 備援源 badge with the 匯率 prefix and source_note as title", () => {
    const html = renderToStaticMarkup(
      createElement(FxStatusBadge, {
        fx: fx({
          data_status: "backup",
          source: "yfinance_fx",
          source_note: "匯率取自 Yahoo Finance 的每日收盤價。",
        }),
      }),
    );
    expect(html).toContain("匯率 備援源");
    expect(html).toContain("bg-amber-900/40");
    expect(html).toContain("text-amber-300");
    expect(html).toContain('title="匯率取自 Yahoo Finance 的每日收盤價。"');
  });

  it("cached_stale renders 資料延遲 N 分鐘 with the 匯率 prefix", () => {
    const staleAsOf = new Date(Date.now() - 90 * 60 * 1000).toISOString().slice(0, 10);
    const html = renderToStaticMarkup(
      createElement(FxStatusBadge, {
        fx: fx({ data_status: "cached_stale", as_of: staleAsOf }),
      }),
    );
    expect(html).toContain("匯率 資料延遲");
    expect(html).toContain("分鐘");
    expect(html).toContain("bg-neutral-800");
  });

  it("unavailable renders 資料不足 with the 匯率 prefix", () => {
    const html = renderToStaticMarkup(
      createElement(FxStatusBadge, {
        fx: fx({ data_status: "unavailable", as_of: null, source: "none", source_note: "" }),
      }),
    );
    expect(html).toContain("匯率 資料不足");
    expect(html).not.toContain("title=");
  });

  it("never invents new user-facing literals beyond the existing four", () => {
    for (const status of ["fresh", "backup", "cached_stale", "unavailable"] as const) {
      const html = renderToStaticMarkup(
        createElement(FxStatusBadge, { fx: fx({ data_status: status }) }),
      );
      if (html) {
        expect(html).toMatch(/備援源|資料不足|資料延遲 \d+ 分鐘/);
      }
    }
  });
});

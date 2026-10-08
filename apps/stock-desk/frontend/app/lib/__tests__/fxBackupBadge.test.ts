import { readFileSync } from "node:fs";
import { join } from "node:path";
import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";
import { SummaryCards } from "../../components/SummaryCards";
import { hasBackupFx } from "../fxBackupBadge";
import { FX_BACKUP_BADGE } from "../oneLinerWording";
import type {
  PortfolioTotals,
  PositionFx,
  PriceDataStatus,
  SummaryPositionItem,
  ValuationStatus,
} from "../types";

/**
 * PR-RK5c (task RK-5, RK5-R3, W5-T5/T6): the standing "備援匯率" badge shows when
 * any ok (valued) position's `fx` or `fx_open` is backup-sourced. A position that
 * is not ok never counts; null / non-backup rates never count.
 */

type FxKind = "backup" | "fresh" | "cached_stale" | "unavailable" | "null";

function fx(kind: FxKind, source: string): PositionFx | null {
  if (kind === "null") return null;
  const data_status: PriceDataStatus = kind;
  return {
    pair: "USDTWD",
    as_of: "2026-10-02",
    source,
    data_status,
    source_note: "",
    is_within_ttl: null,
    reason: null,
  };
}

function row(
  status: ValuationStatus,
  fxKind: FxKind,
  fxOpenKind: FxKind,
  opts: { fxSource?: string; fxOpenSource?: string; missing?: string[] } = {},
): SummaryPositionItem {
  const ok = status === "ok";
  return {
    id: 1,
    symbol: "AAPL",
    market: "US",
    quantity: "10",
    avg_cost: "100",
    currency: "USD",
    instrument_type: "stock",
    opened_at: "2026-03-12",
    sector: null,
    note: null,
    market_value_twd: ok ? "110000" : null,
    cost_twd: ok ? "100000" : null,
    change: null,
    valuation: {
      status,
      missing: opts.missing ?? (ok ? [] : ["price"]),
      price: null,
      fx: fx(fxKind, opts.fxSource ?? "bank_of_taiwan"),
      fx_open: fx(fxOpenKind, opts.fxOpenSource ?? "bank_of_taiwan"),
      pnl_original: null,
      pnl_twd: ok ? "10000" : null,
      asset_contribution_twd: ok ? "10000" : null,
      fx_contribution_twd: ok ? "0" : null,
    },
  };
}

const totals: PortfolioTotals = {
  cost_twd: "100000",
  market_value_twd: "105000",
  unrealized_pnl_twd: "5000",
  asset_contribution_twd: "4000",
  fx_contribution_twd: "1000",
  status: "complete",
};

function badgeHtml(active: boolean): string {
  return renderToStaticMarkup(
    createElement(SummaryCards, {
      totals,
      asOf: "2026-10-02T00:00:00Z",
      positions: [],
      fxDisclosures: [],
      fxBackupActive: active,
    }),
  );
}

describe("hasBackupFx — single-row table (RK5-R3)", () => {
  const table: Array<[string, ValuationStatus, FxKind, FxKind, boolean]> = [
    // ok rows: either rate backup shows the badge
    ["ok, fx backup, fx_open backup", "ok", "backup", "backup", true],
    ["ok, fx backup, fx_open fresh", "ok", "backup", "fresh", true],
    ["ok, fx backup, fx_open null", "ok", "backup", "null", true],
    ["ok, fx fresh, fx_open backup", "ok", "fresh", "backup", true],
    ["ok, fx null, fx_open backup", "ok", "null", "backup", true],
    ["ok, fx cached_stale, fx_open backup", "ok", "cached_stale", "backup", true],
    // ok rows: no backup anywhere
    ["ok, fx fresh, fx_open fresh", "ok", "fresh", "fresh", false],
    ["ok, fx fresh, fx_open null", "ok", "fresh", "null", false],
    ["ok, fx null, fx_open fresh", "ok", "null", "fresh", false],
    ["ok, fx null, fx_open null (TWD row)", "ok", "null", "null", false],
    ["ok, fx cached_stale, fx_open cached_stale", "ok", "cached_stale", "cached_stale", false],
    ["ok, fx unavailable, fx_open unavailable", "ok", "unavailable", "unavailable", false],
    // non-ok rows never count, whichever rate is backup
    ["non-ok, fx backup, fx_open fresh", "insufficient_data", "backup", "fresh", false],
    ["non-ok, fx fresh, fx_open backup", "insufficient_data", "fresh", "backup", false],
    ["non-ok, fx backup, fx_open backup", "insufficient_data", "backup", "backup", false],
    ["non-ok, fx backup, fx_open null", "insufficient_data", "backup", "null", false],
    ["non-ok, fx fresh, fx_open fresh", "insufficient_data", "fresh", "fresh", false],
  ];

  it.each(table)("%s", (_label, status, fxKind, fxOpenKind, expected) => {
    expect(hasBackupFx([row(status, fxKind, fxOpenKind)])).toBe(expected);
  });
});

describe("hasBackupFx — mixed books, empty book, X-3c mismatch row", () => {
  it("is false for an empty book", () => {
    expect(hasBackupFx([])).toBe(false);
  });

  it("is true when only one of several rows is an ok row with backup fx_open", () => {
    expect(
      hasBackupFx([
        row("ok", "fresh", "fresh"),
        row("ok", "fresh", "backup"),
        row("insufficient_data", "fresh", "fresh"),
      ]),
    ).toBe(true);
  });

  it("is true when only one of several rows is an ok row with backup fx", () => {
    expect(hasBackupFx([row("ok", "fresh", "null"), row("ok", "backup", "fresh")])).toBe(true);
  });

  it("is false when the only backup rates sit on non-ok rows", () => {
    expect(
      hasBackupFx([
        row("ok", "fresh", "fresh"),
        row("insufficient_data", "backup", "backup"),
        row("insufficient_data", "fresh", "backup"),
      ]),
    ).toBe(false);
  });

  it("is false when every ok row is fresh or null", () => {
    expect(
      hasBackupFx([
        row("ok", "fresh", "fresh"),
        row("ok", "null", "null"),
        row("insufficient_data", "backup", "null"),
      ]),
    ).toBe(false);
  });

  it("treats an X-3c currency/market mismatch row (fx and fx_open both null) as no backup", () => {
    const mismatch = row("insufficient_data", "null", "null", {
      missing: ["currency_market_mismatch"],
    });
    expect(mismatch.valuation.fx).toBeNull();
    expect(mismatch.valuation.fx_open).toBeNull();
    expect(hasBackupFx([mismatch])).toBe(false);
    // ... and it does not mask a real backup row next to it.
    expect(hasBackupFx([mismatch, row("ok", "backup", "fresh")])).toBe(true);
  });

  it("does not read a null rate as backup", () => {
    expect(hasBackupFx([row("ok", "null", "null")])).toBe(false);
  });
});

/**
 * W5-T5 (badge coupling): every fixture in which the mixed-source sentence
 * (W-RK5-1) would appear -- an ok row whose `fx` and `fx_open` have different
 * source ids -- must light the badge. On the two-rung ladder (bank_of_taiwan
 * fresh, yfinance_fx backup) any mixed-source pair has exactly one backup side,
 * in either direction, so the standing badge always covers it.
 */
describe("W5-T5 badge coupling with mixed-source fixtures", () => {
  const mixedFixtures: Array<[string, SummaryPositionItem]> = [
    [
      "fx_now backup (yfinance_fx), fx_open fresh (bank_of_taiwan)",
      row("ok", "backup", "fresh", { fxSource: "yfinance_fx", fxOpenSource: "bank_of_taiwan" }),
    ],
    [
      "fx_now fresh (bank_of_taiwan), fx_open backup (yfinance_fx)",
      row("ok", "fresh", "backup", { fxSource: "bank_of_taiwan", fxOpenSource: "yfinance_fx" }),
    ],
  ];

  it.each(mixedFixtures)("%s -> source ids differ and the badge is true and rendered", (_l, position) => {
    const { fx: now, fx_open: open } = position.valuation;
    expect(now).not.toBeNull();
    expect(open).not.toBeNull();
    expect(now?.source).not.toBe(open?.source);
    expect(position.valuation.status).toBe("ok");

    const active = hasBackupFx([position]);
    expect(active).toBe(true);
    expect(badgeHtml(active)).toContain(FX_BACKUP_BADGE);
  });

  it("a same-source fresh fixture (no mixed sentence) shows no badge", () => {
    const same = row("ok", "fresh", "fresh");
    expect(same.valuation.fx?.source).toBe(same.valuation.fx_open?.source);
    const active = hasBackupFx([same]);
    expect(active).toBe(false);
    expect(badgeHtml(active)).not.toContain(FX_BACKUP_BADGE);
  });
});

/**
 * RK5-R3 / W5-T6: the home page must delegate to the helper (not re-inline a
 * narrower rule), and no new user-visible string is introduced.
 */
describe("home page wiring and wording (W5-T6)", () => {
  const page = readFileSync(join(__dirname, "..", "..", "page.tsx"), "utf8");

  it("page.tsx feeds fxBackupActive from hasBackupFx", () => {
    expect(page).toContain("fxBackupActive={hasBackupFx(summary.data.positions)}");
    expect(page).not.toMatch(/data_status === "backup"/);
  });

  it("the badge literal is unchanged", () => {
    expect(FX_BACKUP_BADGE).toBe("備援匯率");
  });

  it("the helper module contains no CJK literal (no new visible string)", () => {
    const helper = readFileSync(join(__dirname, "..", "fxBackupBadge.ts"), "utf8");
    expect(helper).not.toMatch(/[一-鿿]/);
  });
});

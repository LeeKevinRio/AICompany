/**
 * F-8 page-level guard: renders the whole stock page against a pre-seeded
 * React Query cache (same technique as priceUnitBadge.test.ts; the project has
 * no DOM environment). A spy on `useLeverageChapter` records the `enabled`
 * flag the page passes, because server rendering never runs fetches.
 *
 * C-4: a disabled TanStack Query still returns cached data, so the render and
 * footer gates must hide a stale chapter once the position is gone.
 */
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { beforeEach, describe, expect, it, vi } from "vitest";
import type { LeverageResponse, Market, Position, PositionsResponse } from "../../../lib/types";
import { LEVERAGE_CHAPTER_TITLE } from "../../../lib/sectionTitles";

const nav = vi.hoisted(() => ({ symbol: "00631L", market: "TW" }));
vi.mock("next/navigation", () => ({
  useParams: () => ({ symbol: nav.symbol }),
  useSearchParams: () => new URLSearchParams(`market=${nav.market}`),
}));
vi.mock("next/dynamic", () => ({ default: () => () => null }));
vi.mock("../../../lib/queries", async (importOriginal) => {
  const actual = await importOriginal<typeof import("../../../lib/queries")>();
  return { ...actual, useLeverageChapter: vi.fn(actual.useLeverageChapter) };
});

const queries = await import("../../../lib/queries");
const { default: PositionDetailPage } = await import("../page");

const DISCLOSURE_SENTINEL = "LEVERAGE-DISCLOSURE-SENTINEL";

function lot(symbol: string, market: Market): Position {
  return {
    id: 1,
    symbol,
    market,
    quantity: "1000",
    avg_cost: "150",
    currency: market === "TW" ? "TWD" : "USD",
    opened_at: "2026-01-02",
    instrument_type: "leveraged_etf",
    note: null,
    created_at: "2026-01-02T00:00:00Z",
    updated_at: "2026-01-02T00:00:00Z",
  };
}

function positionsOf(...items: Position[]): PositionsResponse {
  return { items, as_of: "x" };
}

function leverageResponse(symbol: string, market: Market): LeverageResponse {
  return {
    symbol,
    market,
    status: "insufficient_data",
    reason: null,
    data: {
      status: "cached_stale",
      source: "demo",
      staleness_minutes: 5,
      is_within_ttl: true,
      bar_count: 0,
      first_bar_date: null,
      last_bar_date: null,
      trading_days_behind: null,
      reason: null,
    },
    as_of: "x",
    position_id: 1,
    index_bars_available: false,
    chapter: {
      symbol,
      position_id: 1,
      generated_at: "2026-10-12T00:00:00Z",
      disclosure: DISCLOSURE_SENTINEL,
      detection: {
        status: "insufficient_data",
        symbol,
        normalized_symbol: symbol,
        instrument_type: "leveraged_etf",
        is_daily_reset_leveraged: true,
        leverage_factor: null,
        underlying_index: null,
        expense_ratio_annual: null,
        metadata_verified: false,
        metadata_verified_on: null,
        source_note: null,
        classification_mismatch: false,
        reason: "r",
        notes: [],
      },
      holding: {
        status: "insufficient_data",
        opened_at: "2026-01-02",
        first_bar_date: null,
        last_bar_date: null,
        bars_since_opened_at: 0,
        holding_trading_days: null,
        holding_days: null,
        reason: "r",
      },
      drag: null,
      erosion: null,
      notes: [],
      chapter_status: "insufficient_data",
      reason: null,
    },
  };
}

interface Seed {
  symbol: string;
  market: Market;
  /** `undefined` leaves the positions query pending. */
  positions?: PositionsResponse;
  positionsError?: boolean;
  /** A chapter already sitting in the cache (e.g. from an earlier visit). */
  cachedChapter?: boolean;
  /** A failed leverage query already sitting in the cache (e.g. a 500 seen while positions were down). */
  cachedLeverageError?: boolean;
}

async function renderPage(seed: Seed): Promise<string> {
  nav.symbol = seed.symbol;
  nav.market = seed.market;
  // `retryOnMount: false` keeps a pre-seeded failed positions query in its error state during the
  // server render (otherwise the optimistic result would report it as pending again).
  const client = new QueryClient({ defaultOptions: { queries: { retry: false, retryOnMount: false } } });
  if (seed.positions) client.setQueryData(["positions"], seed.positions);
  if (seed.cachedChapter) {
    client.setQueryData(["leverage", seed.symbol, seed.market], leverageResponse(seed.symbol, seed.market));
  }
  if (seed.cachedLeverageError) {
    await client
      .fetchQuery({
        queryKey: ["leverage", seed.symbol, seed.market],
        queryFn: () => Promise.reject(new Error("boom")),
        retry: false,
      })
      .catch(() => undefined);
  }
  if (seed.positionsError) {
    // Drive the positions query into the error state without a real network call.
    await client
      .fetchQuery({ queryKey: ["positions"], queryFn: () => Promise.reject(new Error("boom")), retry: false })
      .catch(() => undefined);
  }
  return renderToStaticMarkup(createElement(QueryClientProvider, { client }, createElement(PositionDetailPage)));
}

/** The `enabled` flag of the most recent `useLeverageChapter` call. */
function lastEnabledFlag(): boolean {
  const calls = vi.mocked(queries.useLeverageChapter).mock.calls;
  const last = calls[calls.length - 1];
  if (!last) throw new Error("useLeverageChapter was not called");
  return last[2];
}

beforeEach(() => {
  vi.mocked(queries.useLeverageChapter).mockClear();
});

describe("stock page — leverage query gate (F-8)", () => {
  it("does not enable the leverage query while positions are pending", async () => {
    await renderPage({ symbol: "AAPL", market: "US" });
    expect(lastEnabledFlag()).toBe(false);
  });

  it("does not enable the leverage query for a symbol that is not held", async () => {
    await renderPage({ symbol: "AAPL", market: "US", positions: positionsOf(lot("2330", "TW")) });
    expect(lastEnabledFlag()).toBe(false);
  });

  it("does not enable the leverage query for a held symbol in the other market", async () => {
    await renderPage({ symbol: "2330", market: "US", positions: positionsOf(lot("2330", "TW")) });
    expect(lastEnabledFlag()).toBe(false);
  });

  it("enables the leverage query when the positions request failed (old fallback path)", async () => {
    await renderPage({ symbol: "AAPL", market: "US", positionsError: true });
    expect(lastEnabledFlag()).toBe(true);
  });

  it("enables the leverage query once the symbol is held", async () => {
    await renderPage({ symbol: "00631L", market: "TW", positions: positionsOf(lot("00631L", "TW")) });
    expect(lastEnabledFlag()).toBe(true);
  });

  it("enables it with a case difference between the URL and the stored symbol", async () => {
    await renderPage({ symbol: "tqqq", market: "US", positions: positionsOf(lot("TQQQ", "US")) });
    expect(lastEnabledFlag()).toBe(true);
  });
});

describe("stock page — cached chapter follows the gate (C-4)", () => {
  it("shows the cached chapter and its footer disclosure while the symbol is held", async () => {
    const html = await renderPage({
      symbol: "00631L",
      market: "TW",
      positions: positionsOf(lot("00631L", "TW")),
      cachedChapter: true,
    });
    expect(html).toContain(`<h2 class="text-lg font-semibold text-neutral-100">${LEVERAGE_CHAPTER_TITLE}</h2>`);
    expect(html).toContain(DISCLOSURE_SENTINEL);
  });

  it("hides a stale cached chapter (view and footer) once the position is gone", async () => {
    const html = await renderPage({
      symbol: "00631L",
      market: "TW",
      positions: positionsOf(),
      cachedChapter: true,
    });
    expect(html).not.toContain(DISCLOSURE_SENTINEL);
    expect(html).not.toContain(`>${LEVERAGE_CHAPTER_TITLE}</h2>`);
  });

  it("hides a cached chapter while positions are still pending", async () => {
    const html = await renderPage({ symbol: "00631L", market: "TW", cachedChapter: true });
    expect(html).not.toContain(DISCLOSURE_SENTINEL);
  });
});

describe("stock page — cached leverage error follows the gate", () => {
  const ERROR_LABEL = "無法載入槓桿專章";

  it("renders the error panel while the query is enabled (control)", async () => {
    const html = await renderPage({
      symbol: "00631L",
      market: "TW",
      positions: positionsOf(lot("00631L", "TW")),
      cachedLeverageError: true,
    });
    expect(html).toContain(ERROR_LABEL);
  });

  it("does not render a cached leverage error once the symbol is no longer held", async () => {
    const html = await renderPage({
      symbol: "00631L",
      market: "TW",
      positions: positionsOf(),
      cachedLeverageError: true,
    });
    expect(lastEnabledFlag()).toBe(false);
    expect(html).not.toContain(ERROR_LABEL);
  });
});

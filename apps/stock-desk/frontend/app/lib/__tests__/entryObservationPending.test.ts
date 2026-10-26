import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it, vi } from "vitest";
import { computeKeyLevels } from "../keyLevels";
import type { KeyLevels } from "../keyLevels";
import type {
  AdviceCard,
  AdviceResponse,
  Bar,
  BarsResponse,
  DataMeta,
  IndicatorResult,
  PositionsResponse,
  SignalsPayload,
  SignalsResponse,
  SignalsTechnicalBlock,
} from "../types";
import { evaluateEntryObservation, isEntryObservationPending } from "../entryObservation";
import { ENTRY_PANEL_TITLE, ENTRY_STATUS_LABELS, buildConditionCount } from "../entryObservationWording";
import { EntryObservationPanel } from "../../position/[symbol]/EntryObservationPanel";
import { PriceChart } from "../../position/[symbol]/PriceChart";

/**
 * Trust defect (2026-10-26 product review, frontend-engineer issue 4 / qa-e2e
 * issue 4): the first load of `/position/2330` printed 「均線資料不足，未繪製
 * MA5/20/60 疊圖。」 and 「6 條中成立 3 條，其中 2 條無法判定。」, the reload
 * printed three MA lines and 「6 條中成立 5 條。」 — same bars (386), same day.
 * Cause: `/api/signals` lands seconds after `/api/bars` on a cold backend, and
 * the page read "signals not arrived yet" as "signals insufficient". These
 * tests pin that a query still on its first load never produces a verdict.
 */

const MA_NOTE = "均線資料不足，未繪製 MA5/20/60 疊圖。";

/* Whole-page harness: same approach as `priceUnitBadge.test.ts` (seeded React
   Query cache; only `next/navigation` and `next/dynamic` mocked). A query whose
   key is not seeded stays `isPending` — exactly the "not arrived yet" state. */
vi.mock("next/navigation", () => ({
  useParams: () => ({ symbol: "2330" }),
  useSearchParams: () => new URLSearchParams("market=TW"),
}));
vi.mock("next/dynamic", () => ({ default: () => () => null }));

const { default: PositionDetailPage } = await import("../../position/[symbol]/page");

function levels(): KeyLevels {
  return {
    close: 918.66,
    closeDate: "2026-10-26",
    rangeHigh: 1004.44,
    rangeLow: 705.36,
    rangePositionPct: 71.3,
    ma20: 923.44,
    ma60: 906.93,
    ma60DeviationPct: 1.3,
    recentLow60: 844.38,
    atr14: 17.54,
    anchorPrice: 918.66,
    stopAtr: 859.89,
    stopFixedPct: 823.8,
    stopSuggested: 859.89,
    targetFixedPct: 1074.53,
    target2R: 966.54,
    barCount: 386,
    rangeBarCount: 252,
    rangeUnavailableCause: null,
  };
}

function signals(): SignalsPayload {
  const ok = (last: Record<string, number>): IndicatorResult =>
    ({ status: "ok", last, name: "", params: {}, dates: [], series: {}, inputs_used: {}, as_of: null, source: null }) as unknown as IndicatorResult;
  return {
    symbol: "2330",
    bar_count: 386,
    as_of: null,
    source: null,
    technical: {
      rsi: ok({ rsi: 55.2 }),
      volume_zscore: ok({ zscore: 0.4 }),
    } as Partial<SignalsTechnicalBlock> as SignalsTechnicalBlock,
  };
}

function advice(): AdviceCard {
  return {
    matched_rules: [{ id: "r0", name: "", action: "add", weight: 1, weight_meaning: "", explanation: "", invalidation: null }],
    direction_weights: [{ direction: "constructive", actions: ["add"], weight: 1 }],
  } as unknown as AdviceCard;
}

/** One render of the panel exactly as `page.tsx` wires it, for a given arrival state. */
function renderPanel(arrived: { bars: boolean; signals: boolean; advice: boolean }): string {
  const observation = evaluateEntryObservation(
    arrived.bars ? levels() : null,
    arrived.signals ? signals() : null,
    arrived.advice ? advice() : null,
    arrived.advice ? true : null,
  );
  const pending = isEntryObservationPending([
    { isPending: !arrived.bars },
    { isPending: !arrived.signals },
    { isPending: !arrived.advice },
  ]);
  return renderToStaticMarkup(
    createElement(EntryObservationPanel, {
      observation,
      rangeBarCount: arrived.bars ? 252 : null,
      dataAsOfDates: { bars: null, signals: null, advice: null },
      market: "TW",
      bars: null,
      pending,
    }),
  );
}

/** Every count sentence the panel can print for 0..6 met and 0..6 undecided. */
function printedCounts(html: string): string[] {
  const found: string[] = [];
  for (let met = 0; met <= 6; met += 1) {
    for (let unavailable = 0; met + unavailable <= 6; unavailable += 1) {
      const sentence = buildConditionCount(met, unavailable);
      if (html.includes(sentence)) found.push(sentence);
    }
  }
  return found;
}

describe("isEntryObservationPending", () => {
  it("is pending while any of the three queries is on its first load", () => {
    expect(isEntryObservationPending([{ isPending: false }, { isPending: true }, { isPending: false }])).toBe(true);
    expect(isEntryObservationPending([{ isPending: true }, { isPending: true }, { isPending: true }])).toBe(true);
  });

  it("is settled once every query has settled (success or final error alike)", () => {
    expect(isEntryObservationPending([{ isPending: false }, { isPending: false }, { isPending: false }])).toBe(false);
  });
});

describe("EntryObservationPanel — no verdict before the data has arrived", () => {
  it("signals still loading (the cold-start order): no count, no dots, no 無法判定 row", () => {
    const html = renderPanel({ bars: true, signals: false, advice: true });
    expect(html).toContain(ENTRY_PANEL_TITLE);
    expect(html).toContain('aria-busy="true"');
    expect(printedCounts(html)).toEqual([]);
    expect(html).not.toContain(ENTRY_STATUS_LABELS.unavailable);
    expect(html).not.toContain("—");
  });

  it("same data, any arrival order: exactly one count is ever printed", () => {
    const orders: { bars: boolean; signals: boolean; advice: boolean }[][] = [
      // bars → advice → signals (the observed cold start)
      [
        { bars: true, signals: false, advice: false },
        { bars: true, signals: false, advice: true },
        { bars: true, signals: true, advice: true },
      ],
      // signals → bars → advice
      [
        { bars: false, signals: true, advice: false },
        { bars: true, signals: true, advice: false },
        { bars: true, signals: true, advice: true },
      ],
      // all at once (the warm reload)
      [{ bars: true, signals: true, advice: true }],
    ];
    const seen = new Set<string>();
    for (const order of orders) {
      for (const state of order) {
        for (const sentence of printedCounts(renderPanel(state))) seen.add(sentence);
      }
    }
    const full = evaluateEntryObservation(levels(), signals(), advice(), true);
    expect([...seen]).toEqual([buildConditionCount(full.metCount, full.unavailableCount)]);
  });

  it("a settled query that has no answer is still reported as undecidable (not hidden)", () => {
    // signals failed for good: not pending, so the count prints with its 無法判定 part.
    const observation = evaluateEntryObservation(levels(), null, advice(), true);
    const html = renderToStaticMarkup(
      createElement(EntryObservationPanel, {
        observation,
        rangeBarCount: 252,
        dataAsOfDates: { bars: null, signals: null, advice: null },
        market: "TW",
        bars: null,
        pending: false,
      }),
    );
    expect(printedCounts(html)).toEqual([buildConditionCount(observation.metCount, observation.unavailableCount)]);
    expect(observation.unavailableCount).toBe(2);
  });
});

describe("PriceChart — 「均線資料不足」 only when the MA data is really insufficient", () => {
  const bars: Bar[] = [
    { date: "2026-10-26", open: "910", high: "920", low: "905", close: "918.66", volume: 1000, currency: "TWD", source: "demo_synthetic" },
  ];

  it("signals still loading: the note is withheld", () => {
    const html = renderToStaticMarkup(
      createElement(PriceChart, { bars, movingAverages: undefined, movingAveragesPending: true }),
    );
    expect(html).not.toContain(MA_NOTE);
  });

  it("signals settled without MA (insufficient / error): the note is shown", () => {
    const html = renderToStaticMarkup(createElement(PriceChart, { bars, movingAverages: undefined, movingAveragesPending: false }));
    expect(html).toContain(MA_NOTE);
    const insufficient = { status: "insufficient_data" } as unknown as IndicatorResult;
    expect(renderToStaticMarkup(createElement(PriceChart, { bars, movingAverages: insufficient }))).toContain(MA_NOTE);
  });
});

describe("page.tsx wiring", () => {
  const pageSrc = readFileSync(fileURLToPath(new URL("../../position/[symbol]/page.tsx", import.meta.url)), "utf8");

  it("gates the panel on all three queries and the MA note on the signals query", () => {
    expect(pageSrc).toContain("isEntryObservationPending([bars, signals, advice])");
    expect(pageSrc).toContain("pending={entryObservationPending}");
    expect(pageSrc).toContain("movingAveragesPending={signals.isPending}");
  });

  // 風控 2026-10-26 結案確認 R4（重開條件絆線）：此測試一旦要改，即觸發風控 2026-10-26
  // 第 1 點的重開條件，須送回風控重審。A disabled query with no data stays
  // `isPending` forever (E-4 would vanish for good), and placeholder / initial /
  // previous data would print a count from another symbol's payload.
  it("R4: the three queries are always enabled and never seeded with placeholder / initial / previous data", () => {
    for (const call of ["useSignals(symbol, market, true)", "useBars(symbol, market, true)", "useAdvice(symbol, market, true)"]) {
      expect(pageSrc).toContain(call);
    }
    const queriesSrc = readFileSync(fileURLToPath(new URL("../queries.ts", import.meta.url)), "utf8");
    for (const hook of ["useSignals", "useBars", "useAdvice"]) {
      const start = queriesSrc.indexOf(`export function ${hook}(`);
      expect(start, hook).toBeGreaterThan(-1);
      const body = queriesSrc.slice(start, queriesSrc.indexOf("\n}\n", start));
      expect(body, hook).toContain("enabled: enabled && symbol.length > 0,");
      for (const banned of ["placeholderData", "keepPreviousData", "initialData"]) expect(body, `${hook} ${banned}`).not.toContain(banned);
    }
    const providersSrc = readFileSync(fileURLToPath(new URL("../../providers.tsx", import.meta.url)), "utf8");
    expect(providersSrc).toContain("new QueryClient()");
    expect(providersSrc).not.toContain("defaultOptions");
  });
});

/* ------------------------------------------------------------ whole page */

const META: DataMeta = {
  status: "cached_stale",
  source: "demo_synthetic",
  staleness_minutes: 1,
  is_within_ttl: false,
  bar_count: 100,
  first_bar_date: "2026-01-01",
  last_bar_date: "2026-04-12",
  trading_days_behind: null,
  reason: null,
};

function pageBars(): Bar[] {
  return Array.from({ length: 100 }, (_, i) => ({
    date: `2026-0${1 + Math.floor(i / 28)}-${String(1 + (i % 28)).padStart(2, "0")}`,
    open: "900",
    high: "930",
    low: "890",
    close: String(900 + (i % 9) * 2),
    volume: 1000 + (i % 5) * 10,
    currency: "TWD",
    source: "demo_synthetic",
  }));
}

const BARS: BarsResponse = { symbol: "2330", market: "TW", status: "ok", reason: null, data: META, as_of: "x", bars: pageBars() };

function indicator(name: string, last: Record<string, number>, series: Record<string, (number | null)[]> = {}): IndicatorResult {
  const dates = BARS.bars.map((b) => b.date);
  return { name, status: "ok", params: {}, dates, series, last, inputs_used: {}, as_of: null, source: null } as unknown as IndicatorResult;
}

const SIGNALS: SignalsResponse = {
  symbol: "2330",
  market: "TW",
  status: "ok",
  reason: null,
  data: META,
  as_of: "x",
  signals: {
    symbol: "2330",
    bar_count: 100,
    as_of: null,
    source: null,
    technical: {
      moving_averages: indicator("moving_averages", { ma_5: 905, ma_20: 906, ma_60: 904 }, {
        ma_5: BARS.bars.map(() => 905),
        ma_20: BARS.bars.map(() => 906),
        ma_60: BARS.bars.map(() => 904),
      }),
      rsi: indicator("rsi", { rsi: 52 }),
      macd: indicator("macd", { macd: 1.2, signal: 1.0, histogram: 0.2 }),
      bollinger: indicator("bollinger", { upper: 920, middle: 906, lower: 892, bandwidth: 0.03, percent_b: 0.5 }),
      atr: indicator("atr", { atr: 12 }),
      kd: indicator("kd", { k: 50, d: 48 }),
      volume_zscore: indicator("volume_zscore", { zscore: 0.3, anomaly: 0 }),
    },
  },
};

const SIGNALS_INSUFFICIENT: SignalsResponse = { ...SIGNALS, status: "insufficient_data", reason: "not enough", signals: null };

const ADVICE: AdviceResponse = {
  symbol: "2330",
  market: "TW",
  status: "ok",
  reason: null,
  as_of: "2026-04-12T09:00:00+08:00",
  held: false,
  position_ids: [],
  portfolio_context: {
    symbol: "2330",
    total_equity_twd: null,
    position_market_value_twd: null,
    position_cost_twd: null,
    gross_exposure_twd: null,
    net_worth: null,
    book_fully_valued: null,
    quantity: null,
    close: null,
    fx_to_twd: 1,
    atr: null,
    sector: null,
    sector_market_value_twd: null,
    win_rate: null,
    payoff_ratio: null,
  },
  context_notes: [],
  advice: {
    symbol: "2330",
    action: "hold",
    quantity_range: null,
    matched_rules: [],
    counterarguments: [],
    invalidation_conditions: [],
    confidence: "low",
    confidence_meaning: "confidence meaning",
    rules_version: "1.0.2",
    as_of: "2026-04-12T09:00:00+08:00",
    observation_window: { start: "2025-05-01", end: "2026-04-12", bars: 100 },
    disclaimer: "disclaimer",
    limits_check: [],
    action_weights: [],
    direction_weights: [],
    has_conflict: false,
    aggregated_action: "hold",
    blocked_action: null,
    blocked_notices: [],
    downgrade_notices: [],
    evaluation: { total_rules: 1, evaluated_rules: 1, matched_rules: 0, data_completeness: 1, skipped_rules: [] },
  },
  data: META,
};

const NO_POSITIONS: PositionsResponse = { items: [], as_of: "x" };

function renderPage(seed: { signals?: SignalsResponse }): string {
  const client = new QueryClient();
  client.setQueryData(["bars", "2330", "TW"], BARS);
  client.setQueryData(["advice", "2330", "TW"], ADVICE);
  if (seed.signals) client.setQueryData(["signals", "2330", "TW"], seed.signals);
  client.setQueryData(["positions"], NO_POSITIONS);
  return renderToStaticMarkup(createElement(QueryClientProvider, { client }, createElement(PositionDetailPage)));
}

describe("whole page (seeded query cache) — first load vs reload of the same data", () => {
  const full = evaluateEntryObservation(computeKeyLevels(BARS.bars), SIGNALS.signals, ADVICE.advice, ADVICE.held);
  const fullCount = buildConditionCount(full.metCount, full.unavailableCount);

  it("signals not arrived yet (cold first load): no MA verdict and no count on the page", () => {
    const html = renderPage({});
    expect(html).not.toContain(MA_NOTE);
    expect(printedCounts(html)).toEqual([]);
    expect(html).toContain(ENTRY_PANEL_TITLE);
  });

  it("signals arrived (reload): the count from the complete data, and no MA note", () => {
    const html = renderPage({ signals: SIGNALS });
    expect(html).not.toContain(MA_NOTE);
    expect(printedCounts(html)).toEqual([fullCount]);
  });

  it("the two loads never print two different counts for the same data", () => {
    const seen = new Set([...printedCounts(renderPage({})), ...printedCounts(renderPage({ signals: SIGNALS }))]);
    expect([...seen]).toEqual([fullCount]);
  });

  it("signals settled as insufficient: the MA note and the 無法判定 part are real and shown", () => {
    const html = renderPage({ signals: SIGNALS_INSUFFICIENT });
    expect(html).toContain(MA_NOTE);
    const partial = evaluateEntryObservation(computeKeyLevels(BARS.bars), null, ADVICE.advice, ADVICE.held);
    expect(printedCounts(html)).toEqual([buildConditionCount(partial.metCount, partial.unavailableCount)]);
  });
});

/* ------------------------------------------------------ 風控 2026-10-26 R1 */

/**
 * 風控 2026-10-26 裁定第 1 點 R1（required）: E-4 is withheld only while the
 * three queries are on their first load, and only together with the count.
 * Once `pending` is false, E-4's full sentence renders in every case —
 * including settled-without-data cases where 「日期不明」 is the truth.
 * (The file-level half of R1 lives in `entryObservationE4Guard.test.ts`.)
 */
const E4_PREFIX = "資料截至：日線 ";
const THIS_YEAR = new Date().getFullYear();
const D1002 = `${THIS_YEAR}-10-02`;
const D1001 = `${THIS_YEAR}-10-01`;

type Settled = "pending" | "ok" | "failed";
type QueryStates = { bars: Settled; signals: Settled; advice: Settled };

/** The panel as `page.tsx` wires it: payloads only from `ok` queries, `isPending` only from `pending` ones. */
function renderSettlement(state: QueryStates, dates: { bars: string | null; signals: string | null; advice: string | null }): string {
  const observation = evaluateEntryObservation(
    state.bars === "ok" ? levels() : null,
    state.signals === "ok" ? signals() : null,
    state.advice === "ok" ? advice() : null,
    state.advice === "ok" ? true : null,
  );
  return renderToStaticMarkup(
    createElement(EntryObservationPanel, {
      observation,
      rangeBarCount: state.bars === "ok" ? 252 : null,
      dataAsOfDates: dates,
      market: "TW",
      bars: null,
      pending: isEntryObservationPending([
        { isPending: state.bars === "pending" },
        { isPending: state.signals === "pending" },
        { isPending: state.advice === "pending" },
      ]),
    }),
  );
}

describe("風控 R1：pending=false 時 E-4 整句一定渲染", () => {
  const cases: [string, QueryStates, { bars: string | null; signals: string | null; advice: string | null }, string][] = [
    [
      "三份皆 ok",
      { bars: "ok", signals: "ok", advice: "ok" },
      { bars: D1002, signals: D1001, advice: D1002 },
      "資料截至：日線 10-02｜指標 10-01｜規則評估 10-02",
    ],
    [
      "signals 為 error（查詢失敗，沒有 data）",
      { bars: "ok", signals: "failed", advice: "ok" },
      { bars: D1002, signals: null, advice: D1002 },
      "資料截至：日線 10-02｜指標 日期不明｜規則評估 10-02",
    ],
    [
      "signals 為 insufficient（回應已到，帶 data meta 日期）",
      { bars: "ok", signals: "failed", advice: "ok" },
      { bars: D1002, signals: D1002, advice: D1002 },
      "資料截至：日線 10-02｜指標 10-02｜規則評估 10-02",
    ],
    [
      "三份日期皆 null（三份皆 ok）",
      { bars: "ok", signals: "ok", advice: "ok" },
      { bars: null, signals: null, advice: null },
      "資料截至：日線 日期不明｜指標 日期不明｜規則評估 日期不明",
    ],
    [
      "三份日期皆 null（三份皆失敗，六條全無法判定、計數不出）",
      { bars: "failed", signals: "failed", advice: "failed" },
      { bars: null, signals: null, advice: null },
      "資料截至：日線 日期不明｜指標 日期不明｜規則評估 日期不明",
    ],
    [
      "bars 與 advice 為 error",
      { bars: "failed", signals: "ok", advice: "failed" },
      { bars: null, signals: D1002, advice: null },
      "資料截至：日線 日期不明｜指標 10-02｜規則評估 日期不明",
    ],
  ];

  for (const [label, state, dates, sentence] of cases) {
    it(label, () => {
      const html = renderSettlement(state, dates);
      expect(html).not.toContain('aria-busy="true"');
      expect(html).toContain(`<p>${sentence}</p>`);
    });
  }

  it("whole page, signals ok: E-4 full sentence from the three queries' data.last_bar_date", () => {
    const d = THIS_YEAR === 2026 ? "04-12" : "2026-04-12";
    expect(renderPage({ signals: SIGNALS })).toContain(`<p>資料截至：日線 ${d}｜指標 ${d}｜規則評估 ${d}</p>`);
  });

  it("whole page, signals insufficient: E-4 full sentence is still rendered", () => {
    const d = THIS_YEAR === 2026 ? "04-12" : "2026-04-12";
    expect(renderPage({ signals: SIGNALS_INSUFFICIENT })).toContain(`<p>資料截至：日線 ${d}｜指標 ${d}｜規則評估 ${d}</p>`);
  });

  it("whole page, signals not arrived yet: neither E-4 nor the count", () => {
    const html = renderPage({});
    expect(html).not.toContain(E4_PREFIX);
    expect(printedCounts(html)).toEqual([]);
  });
});

describe("風控 R1：計數句與 E-4 同進同出", () => {
  const settlements: Settled[] = ["pending", "ok", "failed"];
  const allStates: QueryStates[] = settlements.flatMap((b) =>
    settlements.flatMap((s) => settlements.map((a) => ({ bars: b, signals: s, advice: a }))),
  );
  const dateSets = [
    { bars: D1002, signals: D1001, advice: D1002 },
    { bars: null, signals: null, advice: null },
  ];

  it("every one of the 27 query states × 2 date sets: count ⇒ E-4; pending ⇒ neither; settled ⇒ E-4", () => {
    let withCount = 0;
    let pendingStates = 0;
    for (const state of allStates) {
      const pending = Object.values(state).includes("pending");
      for (const dates of dateSets) {
        const html = renderSettlement(state, dates);
        const hasCount = printedCounts(html).length > 0;
        const hasE4 = html.includes(E4_PREFIX);
        const where = `${JSON.stringify(state)} ${JSON.stringify(dates)}`;
        if (hasCount) {
          withCount += 1;
          expect(hasE4, `count without E-4: ${where}`).toBe(true);
        }
        if (pending) {
          pendingStates += 1;
          expect(hasCount, `count while pending: ${where}`).toBe(false);
          expect(hasE4, `E-4 while pending: ${where}`).toBe(false);
        } else {
          expect(hasE4, `E-4 missing once settled: ${where}`).toBe(true);
        }
      }
    }
    // Non-vacuous: both sides of the implication were exercised.
    expect(withCount).toBeGreaterThan(0);
    expect(pendingStates).toBe((27 - 8) * 2);
  });
});

/**
 * 風控 2026-10-26 裁定第 1 點 R2（required）: pending has one source only —
 * React Query `isPending`. Never `isFetching` / `isRefetching` / `isError`,
 * never a data value or a date comparison (that would be the L-10b collapse).
 * `page.tsx`'s wiring is pinned in "page.tsx wiring" above.
 */
describe("風控 R2：isEntryObservationPending 只讀 isPending", () => {
  /** A query-like object that records every property read on it. */
  function recorded(fields: Record<string, unknown>, reads: Set<PropertyKey>): { readonly isPending: boolean } {
    return new Proxy(fields, {
      get(target, key, receiver) {
        reads.add(key);
        return Reflect.get(target, key, receiver);
      },
    }) as unknown as { readonly isPending: boolean };
  }

  const fullResult = (isPending: boolean) => ({
    isPending,
    isFetching: true,
    isRefetching: true,
    isError: true,
    isLoading: true,
    isSuccess: true,
    isPaused: true,
    status: "error",
    fetchStatus: "fetching",
    data: { status: "ok", data: { last_bar_date: D1002 } },
    error: new Error("x"),
  });

  it("reads no property other than isPending on any query", () => {
    for (const flags of [
      [false, false, false],
      [true, false, false],
      [false, true, false],
      [false, false, true],
      [true, true, true],
    ]) {
      const reads = new Set<PropertyKey>();
      isEntryObservationPending(flags.map((p) => recorded(fullResult(p), reads)));
      expect([...reads].filter((k) => k !== "isPending"), `flags ${flags.join(",")}`).toEqual([]);
    }
  });

  it("isFetching / isRefetching / isError / isPaused / data / dates never make it pending", () => {
    const notPending = [fullResult(false), fullResult(false), fullResult(false)];
    expect(isEntryObservationPending(notPending)).toBe(false);
    const noData = [{ isPending: false, data: undefined }, { isPending: false, data: undefined }, { isPending: false, data: undefined }];
    expect(isEntryObservationPending(noData)).toBe(false);
  });

  it("isPending alone makes it pending, whatever the other fields say", () => {
    const quiet = { isPending: true, isFetching: false, isRefetching: false, isError: false, data: { status: "ok" } };
    expect(isEntryObservationPending([fullResult(false), quiet, fullResult(false)])).toBe(true);
  });

  it("source: the helper's input type exposes only isPending and its body reads only isPending", () => {
    const src = readFileSync(fileURLToPath(new URL("../entryObservation.ts", import.meta.url)), "utf8");
    const start = src.indexOf("export function isEntryObservationPending(");
    expect(start).toBeGreaterThan(-1);
    const end = src.indexOf("\n}\n", start);
    const fn = src.slice(start, end + 2).replace(/\s+/g, " ");
    expect(fn).toBe(
      "export function isEntryObservationPending( queries: readonly { readonly isPending: boolean }[], ): boolean { return queries.some((query) => query.isPending); }",
    );
  });
});

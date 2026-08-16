"use client";

import { useState } from "react";
import Link from "next/link";
import dynamic from "next/dynamic";
import { useParams, useSearchParams } from "next/navigation";
import { ApiError } from "../../lib/api";
import { formatDateTime, marketLabel } from "../../lib/format";
import { useAdvice, useBars, useDirectoryResolve, useLeverageChapter, useSignals } from "../../lib/queries";
import type { Market } from "../../lib/types";
import { SkeletonBlock } from "../../components/SkeletonBlock";
import { DataMetaStatusBadge } from "../../components/DataMetaStatusBadge";
import { ErrorPanel } from "../../components/ErrorPanel";
import { InsufficientPanel } from "../../components/InsufficientPanel";
import { PriceChart } from "./PriceChart";
import { AdviceCardView } from "./AdviceCardView";
import { LeverageChapterView } from "./LeverageChapterView";
import { TechnicalIndicatorsPanel } from "./TechnicalIndicatorsPanel";
import { OperationSummaryPanel } from "./OperationSummaryPanel";

/**
 * CEO 派工單 2026-08-16 (TradingView 嵌入) 第 2 點: loaded via `next/dynamic`
 * with `ssr: false` — the panel injects a third-party `<script src=...>` into
 * the DOM directly (bypassing React's own tree), which has no useful
 * server-rendered form and must only ever run client-side.
 */
const TradingViewChartPanel = dynamic(
  () => import("./TradingViewChartPanel").then((mod) => mod.TradingViewChartPanel),
  { ssr: false, loading: () => <SkeletonBlock className="h-[480px] w-full" /> },
);

function isMarket(value: string | null): value is Market {
  return value === "TW" || value === "US";
}

type ChartTab = "tradingview" | "local";

/**
 * CEO 派工單 2026-08-16 (TradingView 嵌入): TradingView is the default tab —
 * the self-built K-line (bound to this system's verified data chain, used
 * for indicator overlay comparison) stays available one click away, never
 * removed.
 */
const CHART_TABS: { key: ChartTab; label: string }[] = [
  { key: "tradingview", label: "互動圖表（TradingView）" },
  { key: "local", label: "本地圖表" },
];

export default function PositionDetailPage() {
  const params = useParams<{ symbol: string }>();
  const searchParams = useSearchParams();
  const symbol = decodeURIComponent(params.symbol);
  // FR-5/Q3 (CEO 裁示 2026-08-09): the manual market `<select>` is gone —
  // market is now system-determined, never user-picked, on this page. The
  // `?market=` query param itself is kept for backward compatibility with
  // existing links/bookmarks and as the NavBar combobox's own navigation
  // target (Q3's "保守解": still a displayed, not user-editable, value);
  // whether to drop it entirely was explicitly left open by the PRD for a
  // later pass, not decided here.
  const marketParam = searchParams.get("market");
  const market: Market = isMarket(marketParam) ? marketParam : "TW";

  const signals = useSignals(symbol, market, true);
  const bars = useBars(symbol, market, true);
  const advice = useAdvice(symbol, market, true);
  // The leverage chapter needs a stored position (opened_at) to build against;
  // a symbol with no matching holding is a real 404 (app/api/leverage.py,
  // verified), rendered as its own quiet note rather than an alarming error.
  const leverage = useLeverageChapter(symbol, market, true);
  const leverageNotFound = leverage.isError && leverage.error instanceof ApiError && leverage.error.status === 404;

  // FR-6: company name from the security directory. `data` is `null` (not
  // an error) on a directory miss, so the title deliberately shows the
  // symbol alone in that case rather than any placeholder text (AC-13).
  const directory = useDirectoryResolve(symbol, true);

  // CEO 派工單 2026-08-16 (TradingView 嵌入): only the active tab's panel is
  // mounted (see the render logic below) — switching tabs re-creates the
  // other one from already-cached query data, rather than keeping a hidden,
  // zero-width chart container around. Known trade-off: no zoom/scroll state
  // survives a tab switch (see 已知限制 in the handoff report).
  const [chartTab, setChartTab] = useState<ChartTab>("tradingview");

  return (
    <main className="mx-auto max-w-5xl px-4 py-8">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div className="flex items-center gap-3">
          <h1 className="text-2xl font-bold text-neutral-100">
            {symbol}
            {directory.data && (
              <span className="ml-2 text-lg font-normal text-neutral-400">{directory.data.name}</span>
            )}
          </h1>
          <span
            aria-label="市場"
            className="rounded-md border border-neutral-700 bg-neutral-900 px-2 py-1 text-sm text-neutral-300"
          >
            {marketLabel(market)}
          </span>
        </div>
        <Link href="/" className="text-sm text-sky-400 underline hover:text-sky-300">
          回總覽
        </Link>
      </div>

      {/*
        --- Operation summary (FR-C1 AC-C1.1 / FR-C6 / FR-C7 / FR-C8) --------
        Deliberately placed above the fold, ahead of the four-facet sections,
        and driven by its own `useAdvice` query instance so a failure or
        `insufficient_data` here never blocks the technical-analysis section
        below (AC-C1.2 / AC-C1.3) — this is the same query the advice-card
        section further down uses; React Query dedupes it into one request.
      */}
      <div className="mt-6">
        <OperationSummaryPanel advice={advice} />
      </div>

      {/*
        --- Technical analysis (FR-C1 information architecture + FR-C2 indicator
        surfacing) -----------------------------------------------------------
        Two independently-loaded subsections under one heading, each with its
        own DataMeta badge (bars vs signals are separate API calls — AC-C1.2 /
        AC-C8.1): a failure or `insufficient_data` in one never blocks the
        other. FR-C3/C4/C5 (fundamentals/chip/news) are not part of this batch
        — their spikes (S-1/S-2/S-3) have not landed — so this section only
        covers what FR-C2 asks for.
      */}
      <section className="mt-6 rounded-lg border border-neutral-800 p-4">
        <h2 className="text-lg font-semibold text-neutral-100">技術分析</h2>

        {/* --- K-line + MA overlay ---------------------------------------- */}
        <div className="mt-4">
          <div className="flex flex-wrap items-center justify-between gap-2">
            <h3 className="text-sm font-semibold text-neutral-200">日K線與均線</h3>
            {chartTab === "local" && bars.isSuccess && (
              <span className="flex items-center text-xs text-neutral-500">
                資料時間：{formatDateTime(bars.data.as_of)}｜來源：{bars.data.data.source}
                <DataMetaStatusBadge
                  status={bars.data.data.status}
                  stalenessMinutes={bars.data.data.staleness_minutes}
                  isWithinTtl={bars.data.data.is_within_ttl}
                />
              </span>
            )}
          </div>

          {/*
            CEO 派工單 2026-08-16 (TradingView 嵌入): TradingView 為預設頁籤，
            本地圖表（既有、綁已驗證資料，供指標對照）保留於第二頁籤，非移除。
          */}
          <div role="tablist" aria-label="圖表來源" className="mt-3 flex gap-1 border-b border-neutral-800">
            {CHART_TABS.map((tab) => (
              <button
                key={tab.key}
                type="button"
                role="tab"
                aria-selected={chartTab === tab.key}
                onClick={() => setChartTab(tab.key)}
                className={`-mb-px rounded-t-md border border-b-0 px-3 py-1.5 text-sm ${
                  chartTab === tab.key
                    ? "border-neutral-700 bg-neutral-900 text-neutral-100"
                    : "border-transparent text-neutral-500 hover:text-neutral-300"
                }`}
              >
                {tab.label}
              </button>
            ))}
          </div>

          {/*
            Each panel only renders while its tab is active (not just CSS
            `hidden`): `PriceChart`'s `lightweight-charts` canvas sizes itself
            from its container's actual width via `autosize`, which a
            `display:none` container reports as zero — mounting fresh on
            activation, rather than toggling visibility on an already-mounted
            zero-width canvas, is what keeps it correctly sized every time.
            The `bars`/`signals` React Query results this reads are already
            cached, so re-mounting costs no extra network round-trip.
          */}
          {chartTab === "tradingview" && (
            <div role="tabpanel" className="mt-3">
              <TradingViewChartPanel symbol={symbol} market={market} />
            </div>
          )}

          {chartTab === "local" && (
            <div role="tabpanel">
              {(bars.isPending || signals.isPending) && <SkeletonBlock className="mt-3 h-[360px] w-full" />}
              {bars.isError && <div className="mt-3"><ErrorPanel label="無法載入日K線" error={bars.error} /></div>}
              {bars.isSuccess && bars.data.status === "insufficient_data" && (
                <div className="mt-3"><InsufficientPanel reason={bars.data.reason} /></div>
              )}
              {bars.isSuccess && bars.data.status === "ok" && (
                <div className="mt-3">
                  <PriceChart
                    bars={bars.data.bars}
                    movingAverages={signals.data?.signals?.technical?.moving_averages}
                  />
                  <p className="mt-2 text-xs text-neutral-500">
                    共 {bars.data.bars.length} 根日線（{bars.data.data.first_bar_date ?? "—"} ~{" "}
                    {bars.data.data.last_bar_date ?? "—"}）。
                  </p>
                </div>
              )}
            </div>
          )}
        </div>

        {/* --- Technical indicators (new, FR-C2) --------------------------- */}
        <div className="mt-8 border-t border-neutral-800 pt-6">
          <div className="flex flex-wrap items-center justify-between gap-2">
            <h3 className="text-sm font-semibold text-neutral-200">技術指標</h3>
            {signals.isSuccess && (
              <span className="flex items-center text-xs text-neutral-500">
                資料時間：{formatDateTime(signals.data.as_of)}｜來源：{signals.data.data.source}
                <DataMetaStatusBadge
                  status={signals.data.data.status}
                  stalenessMinutes={signals.data.data.staleness_minutes}
                  isWithinTtl={signals.data.data.is_within_ttl}
                />
              </span>
            )}
          </div>
          {signals.isPending && <SkeletonBlock className="mt-3 h-40 w-full" />}
          {signals.isError && (
            <div className="mt-3"><ErrorPanel label="無法載入技術指標" error={signals.error} /></div>
          )}
          {signals.isSuccess && signals.data.status === "insufficient_data" && (
            <div className="mt-3"><InsufficientPanel reason={signals.data.reason} /></div>
          )}
          {signals.isSuccess && signals.data.status === "ok" && signals.data.signals && (
            <div className="mt-3">
              <TechnicalIndicatorsPanel payload={signals.data.signals} />
            </div>
          )}
        </div>
      </section>

      {/* --- Advice card ----------------------------------------------- */}
      <section className="mt-8">
        <h2 className="text-lg font-semibold text-neutral-100">建議卡</h2>
        <div className="mt-3">
          {advice.isPending && <SkeletonBlock className="h-64 w-full" />}
          {advice.isError && <ErrorPanel label="無法載入建議" error={advice.error} />}
          {advice.isSuccess && advice.data.status === "insufficient_data" && (
            <InsufficientPanel reason={advice.data.reason} />
          )}
          {advice.isSuccess && advice.data.status === "ok" && advice.data.advice && (
            <>
              <p className="mb-3 text-xs text-neutral-500">
                {advice.data.held
                  ? `以目前持倉評估（部位 ID：${advice.data.position_ids.join("、")}）。`
                  : "目前未持有此標的，以候選部位（0 股）評估。"}
              </p>
              {/*
                S3 fix (risk-final-review.md 列管項):曾以 <details> 預設收合,
                把「風險預算輸入的假設與限制」藏在需要額外點擊才看得到的地方
                ——與反面論點/失效條件(OperationSummaryPanel 的
                RequiredElementsFooter)「never behind a <details>」的既有原則
                矛盾,故改為與該處一致的常駐可見清單。文字內容不變。
              */}
              {advice.data.context_notes.length > 0 && (
                <div className="mb-3 text-xs text-neutral-500">
                  <p className="font-semibold text-neutral-400">
                    風險預算輸入的假設與限制（{advice.data.context_notes.length}）
                  </p>
                  <ul className="mt-2 list-disc space-y-1 pl-5">
                    {advice.data.context_notes.map((note, i) => (
                      <li key={i}>{note}</li>
                    ))}
                  </ul>
                </div>
              )}
              <AdviceCardView advice={advice.data.advice} />
            </>
          )}
        </div>
      </section>

      {/* --- Leverage chapter (conditional) ----------------------------- */}
      {leverage.isSuccess && leverage.data.chapter && (
        <LeverageChapterView chapter={leverage.data.chapter} />
      )}
      {leverage.isError && !leverageNotFound && (
        <div className="mt-8">
          <ErrorPanel label="無法載入槓桿專章" error={leverage.error} />
        </div>
      )}
    </main>
  );
}

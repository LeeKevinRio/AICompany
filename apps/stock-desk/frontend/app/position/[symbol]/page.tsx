"use client";

import { useState } from "react";
import Link from "next/link";
import dynamic from "next/dynamic";
import { useParams, useSearchParams } from "next/navigation";
import { ApiError } from "../../lib/api";
import { formatDateTime, formatNumber, marketLabel } from "../../lib/format";
import { inferTradingViewExchange } from "../../lib/tradingViewSymbol";
import { useAdvice, useBars, useDirectoryResolve, useLeverageChapter, usePositions, useSignals } from "../../lib/queries";
import type { Market } from "../../lib/types";
import { SkeletonBlock } from "../../components/SkeletonBlock";
import { DataMetaStatusBadge } from "../../components/DataMetaStatusBadge";
import { KEY_LEVELS_PANEL_TITLE, KeyLevelsPanel, buildKeyLevelsFooterItems } from "./KeyLevelsPanel";
import { EntryObservationPanel } from "./EntryObservationPanel";
import { evaluateEntryObservation } from "../../lib/entryObservation";
import { computeKeyLevels } from "../../lib/keyLevels";
import { ENTRY_PANEL_TITLE, buildEntryFooterItems } from "../../lib/entryObservationWording";
import { PageFooterDisclosures } from "../../components/PageFooterDisclosures";
import type { FooterGroup } from "../../components/PageFooterDisclosures";
import { NON_REALTIME_NOTICE } from "../../lib/adviceWording";
import { buildSummaryFooterItems } from "../../lib/operationSummary";
import { buildFooterGuidance } from "../../lib/footerDisclosureWording";
import { ADVICE_CARD_XREF_TO_SUMMARY, PAGE_LEVEL_DISCLOSURE_SECTION_TITLE } from "../../lib/sectionTaglines";
import { ADVICE_CARD_TITLE, LEVERAGE_CHAPTER_TITLE, OPERATION_SUMMARY_TITLE, TECHNICAL_ANALYSIS_TITLE } from "../../lib/sectionTitles";
import {
  buildDataAsOfBadge,
  DETAILS_SUMMARY_TECHNICAL,
  buildAdviceHitCount,
  buildTechOneLiner,
} from "../../lib/oneLinerWording";
import type { AnchorSource } from "../../lib/keyLevels";
import type { PositionsResponse } from "../../lib/types";
import { ErrorPanel } from "../../components/ErrorPanel";
import { InsufficientPanel } from "../../components/InsufficientPanel";
import { PriceChart } from "./PriceChart";
import { AdviceCardView, buildAdviceFooterItems } from "./AdviceCardView";
import { LeverageChapterView } from "./LeverageChapterView";
import { IndicatorOverviewChipsRow, TechnicalIndicatorsPanel, buildTechnicalFooterItems } from "./TechnicalIndicatorsPanel";
import { OperationSummaryPanel } from "./OperationSummaryPanel";
import { DecisionCard } from "./DecisionCard";

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

/**
 * 風控 R13/R14: the 關鍵價位 anchor cost comes straight from the stored
 * positions' native-currency `avg_cost` — never reconstructed by dividing
 * TWD book totals through `fx_to_twd` (that recovers P0×F0/F1, not the
 * average cost, and the backend's fx placeholder 1.0 is a contract value that
 * must never touch foreign amounts). Multiple lots of the same symbol are
 * combined as a quantity-weighted average in the lots' own (shared)
 * currency. Tri-state (風控 R10/R11): a confirmed cost, a CONFIRMED not-held
 * state, or "unknown" while the positions query is pending / a lot's cost is
 * unusable — the panel never claims 未持有 on "unknown". Shared by the panel
 * and the 頁尾揭露 builder so both see the same anchor.
 */
function resolveKeyLevelsAnchor(
  positions: PositionsResponse | undefined,
  symbol: string,
  market: Market,
): { anchorSource: AnchorSource; avgCost: number | null } {
  if (!positions) return { anchorSource: "close-unknown", avgCost: null };
  const lots = positions.items.filter((p) => p.symbol === symbol && p.market === market);
  if (lots.length === 0) return { anchorSource: "close-not-held", avgCost: null };
  let qtySum = 0;
  let costSum = 0;
  for (const lot of lots) {
    const qty = Number.parseFloat(lot.quantity);
    const cost = Number.parseFloat(lot.avg_cost);
    if (!Number.isFinite(qty) || qty <= 0 || !Number.isFinite(cost) || cost <= 0) {
      // Held, but a lot's cost is unusable — never claim 未持有.
      return { anchorSource: "close-unknown", avgCost: null };
    }
    qtySum += qty;
    costSum += cost * qty;
  }
  return { anchorSource: "cost", avgCost: costSum / qtySum };
}

function isMarket(value: string | null): value is Market {
  return value === "TW" || value === "US";
}

type ChartTab = "tradingview" | "local";

/**
 * CEO 2026-09-16: the TradingView embed never rendered on the CEO's machine,
 * so the tab is switched off and the self-built K-line (bound to this
 * system's verified data chain) is the only chart shown. Nothing is removed:
 * `TradingViewChartPanel`, its risk-approved wording and the symbol mapping
 * stay in place, and flipping this back on restores the two-tab layout of
 * CEO 派工單 2026-08-16 (TradingView as the default tab).
 */
const TRADINGVIEW_CHART_ENABLED = false;

const ALL_CHART_TABS: { key: ChartTab; label: string }[] = [
  { key: "tradingview", label: "互動圖表（TradingView）" },
  { key: "local", label: "本地圖表" },
];

const CHART_TABS = ALL_CHART_TABS.filter((tab) => TRADINGVIEW_CHART_ENABLED || tab.key !== "tradingview");

const DEFAULT_CHART_TAB: ChartTab = TRADINGVIEW_CHART_ENABLED ? "tradingview" : "local";

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
  // 關鍵價位面板的基準成本來源（風控 R13/R14）：直接取持倉原幣別 avg_cost。
  const positions = usePositions(true);
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
  const [chartTab, setChartTab] = useState<ChartTab>(DEFAULT_CHART_TAB);

  // TradingView exchange prefix for TW symbols (fix: 上櫃 stocks were always
  // sent as `TWSE:` and rendered as an invalid symbol). Inferred from the bars
  // provider id first, then the directory listing source; `undefined` keeps
  // the TWSE default. Part of the panel's `key` below so the widget remounts
  // with the right prefix once the data chain answers.
  const tvExchangeHint = inferTradingViewExchange(bars.data?.data.source, directory.data?.source);

  const keyLevelsAnchor = resolveKeyLevelsAnchor(positions.data, symbol, market);

  /*
    --- 六項觀察條件 (CEO 2026-09-06; PRD §4b) ---------------------------------
    Evaluated from the same three payloads the sections below render; each
    condition degrades to 無法判定 on its own when its payload is missing. The
    rules condition additionally needs a CONFIRMED held position (風控 RED-1
    路徑 a) — `advice.data.held` is only trusted on an ok envelope.
  */
  const entryLevels =
    bars.data && bars.data.status === "ok"
      ? computeKeyLevels(bars.data.bars, keyLevelsAnchor.anchorSource === "cost" ? keyLevelsAnchor.avgCost : null)
      : null;
  const entryObservation = evaluateEntryObservation(
    entryLevels,
    signals.data?.status === "ok" ? (signals.data.signals ?? null) : null,
    advice.data?.status === "ok" ? advice.data.advice : null,
    advice.data?.status === "ok" ? advice.data.held : null,
  );

  /*
    --- 頁尾揭露區（CEO 裁定 2026-09-06 揭露句下沉頁尾；風控 ACCEPT_WITH_CONDITIONS）---
    Fixed group order = page order (L3); each title is the SAME constant its
    section renders (L4). Two layers (L6-4): the 資料來源 group is a static
    constant that exists whatever the queries do; the other groups appear
    exactly when their section's data exists.
  */
  // 一眼一句 §2.1: 分組順序寫死為頁面順序（技術分析 → 操作摘要 → 關鍵價位參考 →
  // 六項觀察條件 → 建議卡 → 槓桿專章），L3/L4 沿用既有標題常數 import。
  const footerGroups: FooterGroup[] = [
    { title: PAGE_LEVEL_DISCLOSURE_SECTION_TITLE, items: [NON_REALTIME_NOTICE] },
    {
      title: TECHNICAL_ANALYSIS_TITLE,
      items:
        signals.data && signals.data.status === "ok" && signals.data.signals
          ? buildTechnicalFooterItems(signals.data.signals)
          : [],
    },
    { title: OPERATION_SUMMARY_TITLE, items: advice.data ? buildSummaryFooterItems(advice.data) : [] },
    {
      title: KEY_LEVELS_PANEL_TITLE,
      items:
        bars.data && bars.data.status === "ok"
          ? buildKeyLevelsFooterItems(bars.data.bars, keyLevelsAnchor.avgCost, keyLevelsAnchor.anchorSource)
          : [],
    },
    // 風控 REQ-1: the six thresholds are static facts — this group exists whatever the queries do.
    { title: ENTRY_PANEL_TITLE, items: buildEntryFooterItems(entryLevels?.rangeBarCount ?? null) },
    {
      title: ADVICE_CARD_TITLE,
      items: advice.data?.status === "ok" && advice.data.advice ? buildAdviceFooterItems(advice.data.advice) : [],
    },
    {
      title: LEVERAGE_CHAPTER_TITLE,
      // Mirrors LeverageChapterView's own gate (it renders nothing for not_applicable).
      items:
        leverage.data?.chapter && leverage.data.chapter.chapter_status !== "not_applicable"
          ? [leverage.data.chapter.disclosure]
          : [],
    },
  ];

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
        --- Decision card (派工單 §5.4 dev-lead 草案／CEO 第三次裁定 §5.1／§5.3；
        視覺規範 B.7) --------------------------------------------------------
        整頁第一張卡，放在標題列與技術分析之間；動作大字＋收盤／停損／停利／
        股數四格，全部沿用既有計算（`buildOperationSummary`／`computeKeyLevels`），
        不新增任何模型或算式。`bars` 只在 `ok` envelope 時傳入真正的日線，否則
        傳 `null`（`DecisionCard` 內部把「—」與「無法判定基準」分開處理）。
      */}
      <DecisionCard
        advice={advice}
        bars={bars.data && bars.data.status === "ok" ? bars.data.bars : null}
        anchorSource={keyLevelsAnchor.anchorSource}
        avgCost={keyLevelsAnchor.avgCost}
      />

      {/*
        --- Technical analysis (FR-C1 information architecture + FR-C2 indicator
        surfacing) -----------------------------------------------------------
        一眼一句 §2.1/§2.2: moved to the top of the body (標題列之後、操作摘要之前).
        Main view: h2 + bars badge + signals badge (風控 R-A1: provenance and
        the signals error/insufficient states stay outside the fold), `PriceChart`,
        chips row, one-line conclusion (`TECH_ONE_LINER`). `<details>` holds the
        signals pending skeleton, the full `IndicatorOverview` (title+legend
        pointer), the seven indicator cards, the three risk cards and the
        sample-size sentence.
        A failure or `insufficient_data` in bars vs signals never blocks the
        other (AC-C1.2 / AC-C8.1) — each still has its own gate below.
      */}
      <section className="mt-6 rounded-lg border border-neutral-800 p-4">
        <div className="flex flex-wrap items-center justify-between gap-2">
          <h2 className="text-lg font-semibold text-neutral-100">{TECHNICAL_ANALYSIS_TITLE}</h2>
          {/*
            CEO 第二次裁定 2026-09-19：主視圖只留徽章本體；「資料時間：…｜
            來源：…」前綴文字改印在下方「詳細」的第一行（字面不動）。

            wave3（派工單 §4.3 第 5／9 點）：bars／signals 兩顆徽章合併同一列
            （R-A1 只要求 signals 徽章本體留在主視圖，未要求另佔一行）；徽章本
            身換成「資料截至 {MM-DD}」（取 bars 的 last_bar_date，本區塊唯一的
            「資料截至」徽章）＋各自的 compact 狀態 chip，前綴「日線」「指標」
            沿用 `buildDataTimesLine` 既有字面（entryObservationWording.ts）的
            同一組子字串，不新造。完整版徽章與「資料時間：…｜來源：…」前綴改
            印在下方「詳細」第一、二行。
          */}
          <span className="flex flex-wrap items-center gap-1.5 text-xs text-neutral-500">
            {bars.isSuccess && buildDataAsOfBadge(bars.data.data.last_bar_date) !== null && (
              <span className="rounded border border-neutral-700 px-1.5 py-0.5 text-neutral-400">
                {buildDataAsOfBadge(bars.data.data.last_bar_date)}
              </span>
            )}
            {bars.isSuccess && (
              <span className="flex items-center gap-1">
                日線
                <DataMetaStatusBadge
                  status={bars.data.data.status}
                  stalenessMinutes={bars.data.data.staleness_minutes}
                  isWithinTtl={bars.data.data.is_within_ttl}
                  lastBarDate={bars.data.data.last_bar_date}
                  reason={bars.data.data.reason}
                  compact
                />
              </span>
            )}
            {/* R-A1（風控逐字審 R5 破線修正）: signals 徽章「本體」（compact）留在主視圖，不得收進 <details>。 */}
            {signals.isSuccess && (
              <span className="flex items-center gap-1">
                指標
                <DataMetaStatusBadge
                  status={signals.data.data.status}
                  stalenessMinutes={signals.data.data.staleness_minutes}
                  isWithinTtl={signals.data.data.is_within_ttl}
                  lastBarDate={signals.data.data.last_bar_date}
                  reason={signals.data.data.reason}
                  compact
                />
              </span>
            )}
          </span>
        </div>

        {/*
          CEO 派工單 2026-08-16 (TradingView 嵌入): TradingView 為預設頁籤，
          本地圖表（既有、綁已驗證資料，供指標對照）保留於第二頁籤，非移除。
          CEO 2026-09-16: TradingView 頁籤以 `TRADINGVIEW_CHART_ENABLED` 關閉，
          只剩本地圖表時不渲染 tablist（見上方常數說明）。
        */}
        {CHART_TABS.length > 1 && (
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
        )}

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
        {TRADINGVIEW_CHART_ENABLED && chartTab === "tradingview" && (
          <div role="tabpanel" className="mt-3">
            {/*
              Security fix (qa-reviewer NEEDS_CHANGES on 4938eb5, Medium
              finding): `key` moved here, one level up from the inner
              `<script>` tag it used to sit on — this forces a full
              unmount/remount of the *whole* panel (host container +
              copyright link + script, not just the script) whenever the
              symbol or market changes, closing the stale-iframe overlap gap
              an inner-only key left open on a same-page symbol change.
            */}
            <TradingViewChartPanel
              key={`${market}:${symbol}:${tvExchangeHint ?? ""}`}
              symbol={symbol}
              market={market}
              exchangeHint={tvExchangeHint}
            />
          </div>
        )}

        {chartTab === "local" && (
          <div role="tabpanel">
            {/*
              CEO 2026-09-17: the K-line waits for the bars query only. The
              MA overlay comes from the (slower) signals query and is drawn
              once it lands; before that the chart still shows the bars,
              instead of sitting behind a skeleton until every indicator is in.
            */}
            {bars.isPending && <SkeletonBlock className="mt-3 h-[360px] w-full" />}
            {bars.isError && <div className="mt-3"><ErrorPanel label="無法載入日K線" error={bars.error} /></div>}
            {bars.isSuccess && bars.data.status === "insufficient_data" && (
              <div className="mt-3"><InsufficientPanel reason={bars.data.reason} /></div>
            )}
            {bars.isSuccess && bars.data.status === "ok" && (
              <>
                <div className="mt-3">
                  <PriceChart
                    bars={bars.data.bars}
                    movingAverages={signals.data?.signals?.technical?.moving_averages}
                  />
                </div>
                {/* R-A1（風控逐字審 R5 破線修正）: signals 的 Error／Insufficient 移回主視圖（chips 列位置），不得收進 <details>。 */}
                {signals.isError && <div className="mt-3"><ErrorPanel label="無法載入技術指標" error={signals.error} /></div>}
                {signals.isSuccess && signals.data.status === "insufficient_data" && (
                  <div className="mt-3"><InsufficientPanel reason={signals.data.reason} /></div>
                )}
                {signals.isSuccess && signals.data.status === "ok" && signals.data.signals && (
                  <IndicatorOverviewChipsRow payload={signals.data.signals} />
                )}
                {/* 一眼一句 §2.2 一句結論：TECH_ONE_LINER＝「近 {n} 根日線，收盤 {x}。」 */}
                <p className="mt-2 text-sm text-neutral-200">
                  {buildTechOneLiner(
                    bars.data.bars.length,
                    formatNumber(Number(bars.data.bars[bars.data.bars.length - 1]?.close ?? NaN), 2),
                  )}
                </p>
              </>
            )}
          </div>
        )}

        <details className="group mt-3">
          <summary className="flex cursor-pointer list-none items-center gap-1.5 text-sm text-neutral-400 hover:text-neutral-300 [&::-webkit-details-marker]:hidden">
            <span aria-hidden="true" className="inline-block text-xs transition-transform duration-150 group-open:rotate-90">
              ▸
            </span>
            {DETAILS_SUMMARY_TECHNICAL}
          </summary>
          <div className="mt-3 space-y-3 border-t border-neutral-800 pt-3 text-xs text-neutral-400">
            {/*
              CEO 第二次裁定 2026-09-19：兩段「資料時間：…｜來源：…」前綴文字，
              字面與主視圖徽章列原本一致。wave3（派工單 §4.3 追加第 9 點）：
              完整版徽章（非 compact，含分鐘數／括號句／reason）同一行接在後
              面——主視圖只留 compact 版，完整版一字不刪，只搬到這裡。
            */}
            {bars.isSuccess && (
              <p>
                資料時間：{formatDateTime(bars.data.as_of)}｜來源：{bars.data.data.source}
                <DataMetaStatusBadge
                  status={bars.data.data.status}
                  stalenessMinutes={bars.data.data.staleness_minutes}
                  isWithinTtl={bars.data.data.is_within_ttl}
                  lastBarDate={bars.data.data.last_bar_date}
                  reason={bars.data.data.reason}
                />
              </p>
            )}
            {signals.isSuccess && (
              <p>
                資料時間：{formatDateTime(signals.data.as_of)}｜來源：{signals.data.data.source}
                <DataMetaStatusBadge
                  status={signals.data.data.status}
                  stalenessMinutes={signals.data.data.staleness_minutes}
                  isWithinTtl={signals.data.data.is_within_ttl}
                  lastBarDate={signals.data.data.last_bar_date}
                  reason={signals.data.data.reason}
                />
              </p>
            )}
            {/* signals 徽章列／Error／Insufficient 已移回主視圖（R-A1）；詳細只留 pending skeleton 與完整指標卡。 */}
            {signals.isPending && <SkeletonBlock className="h-40 w-full" />}
            {signals.isSuccess && signals.data.status === "ok" && signals.data.signals && (
              <TechnicalIndicatorsPanel payload={signals.data.signals} />
            )}
            {bars.isSuccess && bars.data.status === "ok" && (
              <p>
                共 {bars.data.bars.length} 根日線（{bars.data.data.first_bar_date ?? "—"} ~{" "}
                {bars.data.data.last_bar_date ?? "—"}）。
              </p>
            )}
            <p className="text-sm text-neutral-300">{buildFooterGuidance(TECHNICAL_ANALYSIS_TITLE)}</p>
          </div>
        </details>
      </section>

      {/*
        --- Operation summary (FR-C1 AC-C1.1 / FR-C6 / FR-C7 / FR-C8) --------
        Driven by its own `useAdvice` query instance so a failure or
        `insufficient_data` here never blocks the sections around it
        (AC-C1.2 / AC-C1.3) — this is the same query the advice-card section
        further down uses; React Query dedupes it into one request.
      */}
      <div className="mt-6">
        <OperationSummaryPanel advice={advice} />
      </div>

      {/*
        --- 關鍵價位參考 (CEO 需求 2026-09-01 MVP; 風控 R10–R12 修訂) --------
        Number-first digest of range position / pullback / stop / target
        reference levels, fed by the same bars query as the 技術分析 chart
        above (React Query dedupes). Rendered only on an `ok` bars envelope
        (risk R12: this panel's gate must be no looser than the chart's). The
        anchor is a tri-state (risk R10/R11): a confirmed average cost taken
        from the stored positions' native-currency `avg_cost` (risk R13/R14),
        a CONFIRMED not-held state, or "unknown" while the positions query is
        pending or a lot's cost is unusable — the panel words each state
        differently and never claims 未持有 on "unknown".
      */}
      {bars.data && bars.data.status === "ok" && (
        <KeyLevelsPanel
          bars={bars.data.bars}
          anchorSource={keyLevelsAnchor.anchorSource}
          avgCost={keyLevelsAnchor.avgCost}
          observationBand={entryObservation.observationBand}
        />
      )}

      {/* 一眼一句 §2.1: 操作摘要 → 關鍵價位參考 → 六項觀察條件 → 建議卡. */}
      <EntryObservationPanel
        observation={entryObservation}
        rangeBarCount={entryLevels?.rangeBarCount ?? null}
        dataTimes={{
          bars: bars.data?.as_of ?? null,
          signals: signals.data?.as_of ?? null,
          advice: advice.data?.as_of ?? null,
        }}
      />

      {/*
        --- Advice card（一眼一句 §2.6：整卡預設收合）---------------------
        pending／error／insufficient 三態不包 `<details>`，直接渲染在 h2 之下；
        `ok` 狀態才包進 `<details>`，summary 承載 h2＋命中數＋R9 交叉引用句
        （`ADVICE_CARD_XREF_TO_SUMMARY`，`AdviceCardView` 本身不再重複渲染）。
      */}
      <section className="mt-8">
        {advice.isPending && (
          <>
            <h2 className="text-lg font-semibold text-neutral-100">{ADVICE_CARD_TITLE}</h2>
            <div className="mt-3"><SkeletonBlock className="h-64 w-full" /></div>
          </>
        )}
        {advice.isError && (
          <>
            <h2 className="text-lg font-semibold text-neutral-100">{ADVICE_CARD_TITLE}</h2>
            <div className="mt-3"><ErrorPanel label="無法載入建議" error={advice.error} /></div>
          </>
        )}
        {advice.isSuccess && advice.data.status === "insufficient_data" && (
          <>
            <h2 className="text-lg font-semibold text-neutral-100">{ADVICE_CARD_TITLE}</h2>
            <div className="mt-3"><InsufficientPanel reason={advice.data.reason} /></div>
          </>
        )}
        {advice.isSuccess && advice.data.status === "ok" && advice.data.advice && (
          <details className="group rounded-lg border border-neutral-800">
            <summary className="flex cursor-pointer list-none flex-col gap-1 p-4 [&::-webkit-details-marker]:hidden">
              <span className="flex flex-wrap items-center gap-2">
                <span aria-hidden="true" className="inline-block text-xs transition-transform duration-150 group-open:rotate-90">
                  ▸
                </span>
                <h2 className="text-lg font-semibold text-neutral-100">{ADVICE_CARD_TITLE}</h2>
                <span className="text-sm text-neutral-400">{buildAdviceHitCount(advice.data.advice.matched_rules.length)}</span>
              </span>
            </summary>
            <div className="space-y-3 border-t border-neutral-800 p-5">
              {/* CEO 第二次裁定 2026-09-19：R9 交叉引用句從 summary 第二行移進展開內容第一行，字面不動。 */}
              <p className="text-xs text-neutral-400">{ADVICE_CARD_XREF_TO_SUMMARY}</p>
              <p className="text-xs text-neutral-500">
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
            </div>
          </details>
        )}
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

      {/* 頁尾揭露區：頁面最後一個節點（風控 L6-5）；CEO 第三次裁定 2026-09-19 收成 <details>（派工單 §5）。 */}
      <PageFooterDisclosures groups={footerGroups} />
    </main>
  );
}

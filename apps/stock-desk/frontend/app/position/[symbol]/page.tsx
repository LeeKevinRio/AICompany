"use client";

import Link from "next/link";
import { useParams, useRouter, useSearchParams } from "next/navigation";
import { ApiError } from "../../lib/api";
import { formatDateTime } from "../../lib/format";
import { useAdvice, useBars, useLeverageChapter, useSignals } from "../../lib/queries";
import type { Market } from "../../lib/types";
import { MARKET_OPTIONS } from "../../lib/format";
import { SkeletonBlock } from "../../components/SkeletonBlock";
import { DataMetaStatusBadge } from "../../components/DataMetaStatusBadge";
import { PriceChart } from "./PriceChart";
import { AdviceCardView } from "./AdviceCardView";
import { LeverageChapterView } from "./LeverageChapterView";

function isMarket(value: string | null): value is Market {
  return value === "TW" || value === "US";
}

function ErrorPanel({ label, error }: { label: string; error: unknown }) {
  return (
    <p role="alert" className="rounded-md border border-red-900 bg-red-950/40 px-4 py-3 text-sm text-red-300">
      {label}：{error instanceof ApiError ? error.message : "未知錯誤"}
    </p>
  );
}

function InsufficientPanel({ reason }: { reason: string | null }) {
  return (
    <p className="rounded-md border border-amber-800 bg-amber-950/40 px-4 py-3 text-sm text-amber-300">
      {reason ?? "資料不足，無法計算。"}
    </p>
  );
}

export default function PositionDetailPage() {
  const params = useParams<{ symbol: string }>();
  const searchParams = useSearchParams();
  const router = useRouter();
  const symbol = decodeURIComponent(params.symbol);
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

  function changeMarket(next: Market) {
    router.push(`/position/${encodeURIComponent(symbol)}?market=${next}`);
  }

  return (
    <main className="mx-auto max-w-5xl px-4 py-8">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div className="flex items-center gap-3">
          <h1 className="text-2xl font-bold text-neutral-100">{symbol}</h1>
          <select
            value={market}
            onChange={(e) => changeMarket(e.target.value as Market)}
            className="rounded-md border border-neutral-700 bg-neutral-900 px-2 py-1 text-sm text-neutral-100"
            aria-label="市場"
          >
            {MARKET_OPTIONS.map((opt) => (
              <option key={opt.value} value={opt.value}>
                {opt.label}
              </option>
            ))}
          </select>
        </div>
        <Link href="/" className="text-sm text-sky-400 underline hover:text-sky-300">
          回總覽
        </Link>
      </div>

      {/* --- K-line + MA overlay ----------------------------------------- */}
      <section className="mt-6 rounded-lg border border-neutral-800 p-4">
        <div className="flex flex-wrap items-center justify-between gap-2">
          <h2 className="text-lg font-semibold text-neutral-100">日K線與均線</h2>
          {bars.isSuccess && (
            <span className="flex items-center text-xs text-neutral-500">
              資料時間：{formatDateTime(bars.data.as_of)}｜來源：{bars.data.data.source}
              <DataMetaStatusBadge
                status={bars.data.data.status}
                stalenessMinutes={bars.data.data.staleness_minutes}
              />
            </span>
          )}
        </div>
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
              {advice.data.context_notes.length > 0 && (
                <details className="mb-3 text-xs text-neutral-500">
                  <summary className="cursor-pointer text-neutral-400">
                    風險預算輸入的假設與限制（{advice.data.context_notes.length}）
                  </summary>
                  <ul className="mt-2 list-disc space-y-1 pl-5">
                    {advice.data.context_notes.map((note, i) => (
                      <li key={i}>{note}</li>
                    ))}
                  </ul>
                </details>
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

"use client";

import {
  formatDateTime,
  formatPercent,
  limitStatusColorClass,
  limitStatusLabel,
  marketLabel,
} from "../lib/format";
import { usePortfolioLimits } from "../lib/queries";
import { buildLimitGaugeViewModel, buildSourcesSummaryViewModel } from "../lib/riskGauge";
import type { BookLimitCheck, SymbolDataMeta } from "../lib/types";
import { DataMetaStatusBadge } from "./DataMetaStatusBadge";
import { ErrorPanel } from "./ErrorPanel";
import { SkeletonBlock } from "./SkeletonBlock";

/**
 * FR-8: the book-level view of the same five caps `app.advice.limits`
 * checks per symbol (verified source), now backed by `GET
 * /api/portfolio/limits` (`app/api/portfolio.py` + `app/advice/book_limits.py`,
 * verified). That endpoint runs the per-symbol check on every holding in the
 * book, exactly as the individual advice card does, and reports the worst
 * verdict per cap with what it had to leave out — this component renders
 * that response as-is (`status`/`observed`/`threshold`/`detail` verbatim);
 * it does not re-derive any of it client-side.
 *
 * Risk-compliance ruling carried forward unchanged from the previous
 * (all-`not_evaluable`) version of this file: a cap whose `status` is
 * `not_evaluable` must never draw a progress bar, not even an empty one —
 * see `shouldShowLimitBar` in `../lib/riskGauge.ts`, the single place that
 * decision is enforced now that real `observed`/`threshold` pairs exist to
 * draw a bar from for the other two statuses.
 */
function LimitBar({ check }: { check: BookLimitCheck }) {
  const view = buildLimitGaugeViewModel(check);
  if (!view.showBar) return null;
  const fillColorClass = check.status === "violated" ? "bg-rose-500" : "bg-emerald-500";
  return (
    <div
      className="mt-2 h-1.5 w-full overflow-hidden rounded-full bg-neutral-800"
      role="progressbar"
      aria-label={check.name}
      aria-valuenow={Math.round(view.barWidthPercent)}
      aria-valuemin={0}
      aria-valuemax={100}
    >
      <div className={`h-full rounded-full ${fillColorClass}`} style={{ width: `${view.barWidthPercent}%` }} />
    </div>
  );
}

/**
 * Rule 2 of `app/advice/book_limits.py`: what was left out travels with the
 * verdict, reason verbatim.
 *
 * 風控快審 FR-8 八句（2026-08-09，work/reviews/股數區間文案裁決.md）UI 附帶條件：
 * excluded 與判定句同層級可見，不得摺疊——不可用 `<details>` 收合；有 excluded
 * 時不得只渲染綠色通過，未納入檔數與狀態同視覺層級（見 `LimitGaugeItem` 標頭徽章）。
 */
function ExcludedList({ excluded }: { excluded: BookLimitCheck["excluded"] }) {
  if (excluded.length === 0) return null;
  return (
    <div className="mt-2 rounded-md border border-amber-900/40 bg-amber-950/10 p-2">
      <p className="text-xs font-semibold text-amber-300">未納入的標的（{excluded.length}）</p>
      <ul className="mt-1 list-disc space-y-1 pl-5 text-xs text-neutral-400">
        {excluded.map((item) => (
          <li key={`${item.symbol}-${item.market}`}>
            {item.symbol}（{marketLabel(item.market)}）：{item.reason}
          </li>
        ))}
      </ul>
    </div>
  );
}

/**
 * 風控快審附帶條件（work/reviews/股數區間文案裁決.md，2026-08-09）：任一 source
 * 非 fresh 時，summary 行必須帶警示且該情況下改為預設展開；全部 fresh 才維持
 * 收合。判斷邏輯見 `buildSourcesSummaryViewModel`（純函式，riskGauge.ts）。
 */
function SourcesSection({ sources }: { sources: SymbolDataMeta[] }) {
  if (sources.length === 0) return null;
  const summary = buildSourcesSummaryViewModel(sources);
  return (
    <details className="mt-3 text-xs text-neutral-400" open={summary.defaultOpen}>
      <summary className="cursor-pointer text-neutral-400">
        各標的資料來源（{sources.length}）
        {!summary.allFresh && `——其中 ${summary.staleCount} 檔非即時`}
      </summary>
      <ul className="mt-2 space-y-1">
        {sources.map((source) => (
          <li key={`${source.symbol}-${source.market}`} className="flex flex-wrap items-center">
            {source.symbol}（{marketLabel(source.market)}）
            <DataMetaStatusBadge
              status={source.data.status}
              stalenessMinutes={source.data.staleness_minutes}
              isWithinTtl={source.data.is_within_ttl}
            />
          </li>
        ))}
      </ul>
    </details>
  );
}

function LimitGaugeItem({ check }: { check: BookLimitCheck }) {
  const hasExcluded = check.excluded.length > 0;
  return (
    <li className="rounded-md border border-neutral-800 p-3 text-sm">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <span className="font-medium text-neutral-100">
          第 {check.index} 條・{check.name}
        </span>
        <div className="flex items-center gap-2">
          {/* 風控 UI 附帶條件：未納入檔數與狀態同視覺層級，故與狀態文字同排、
              同字級呈現，而非只留在下方的清單裡。 */}
          {hasExcluded && (
            <span className="rounded bg-amber-900/40 px-1.5 py-0.5 text-xs font-semibold text-amber-300">
              未納入 {check.excluded.length} 檔
            </span>
          )}
          <span className={`text-xs font-semibold ${limitStatusColorClass(check.status)}`}>
            {limitStatusLabel(check.status)}
          </span>
        </div>
      </div>
      <LimitBar check={check} />
      {/* §2.1 對比度裁量（沿用既有升級）：這句是每條上限唯一的敘述文字，不得低於
          text-neutral-400。 */}
      <p className="mt-2 text-neutral-400">{check.detail}</p>
      <p className="mt-1 text-xs text-neutral-400">
        觀察值：{formatPercent(check.observed)}　上限：{formatPercent(check.threshold)}
        {/* 風控退修:沿用後端 WORST_SYMBOL_PREFIX(book_limits.py)「觀測值最高」
            這個限定語,不能只寫「最高」——這是逐檔比較裡「觀測值」最高的那一檔,
            不是隨便一種「最高」。 */}
        {check.worst_symbol !== null && <>　觀測值最高：{check.worst_symbol}</>}
      </p>
      <ExcludedList excluded={check.excluded} />
    </li>
  );
}

export function RiskGauge() {
  const limits = usePortfolioLimits(true);

  return (
    <div className="rounded-lg border border-neutral-800 p-5">
      <h2 className="text-lg font-semibold text-neutral-100">風險儀表</h2>
      {/* 風控裁決(work/reviews/股數區間文案裁決.md,2026-08-09)核可全文,修改須重新送審。 */}
      <p className="mt-1 text-xs text-neutral-400">
        單一標的佔比、單一產業佔比、單筆最大可承受虧損三條為逐檔比較，回報最差結果；總曝險與 Kelly
        部位上限為帳本層單一判定。未納入比較的標的列於各條之下。
      </p>

      {limits.isPending && (
        <div className="mt-3 space-y-2">
          <SkeletonBlock className="h-16 w-full" />
          <SkeletonBlock className="h-16 w-full" />
          <SkeletonBlock className="h-16 w-full" />
          <SkeletonBlock className="h-16 w-full" />
          <SkeletonBlock className="h-16 w-full" />
        </div>
      )}

      {limits.isError && (
        <div className="mt-3">
          <ErrorPanel label="無法載入風險儀表" error={limits.error} />
        </div>
      )}

      {limits.isSuccess && (
        <>
          {/* 風控退修附帶:as_of 是伺服器回應時間,不是行情時間——行情新鮮度由下方
              sources 徽章承載,這裡不得暗示「資料的時間」。 */}
          <p className="mt-2 text-xs text-neutral-500">判定產生時間：{formatDateTime(limits.data.as_of)}</p>

          <ul className="mt-3 space-y-2">
            {limits.data.limits.map((check) => (
              <LimitGaugeItem key={check.limit_id} check={check} />
            ))}
          </ul>

          {limits.data.notes.length > 0 && (
            <details className="mt-3 text-xs text-neutral-500">
              <summary className="cursor-pointer text-neutral-400">
                風險預算輸入的假設與限制（{limits.data.notes.length}）
              </summary>
              <ul className="mt-2 list-disc space-y-1 pl-5">
                {limits.data.notes.map((note, i) => (
                  <li key={i}>{note}</li>
                ))}
              </ul>
            </details>
          )}

          <SourcesSection sources={limits.data.sources} />
        </>
      )}
    </div>
  );
}

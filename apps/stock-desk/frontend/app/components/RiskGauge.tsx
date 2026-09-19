"use client";

import {
  formatDateTime,
  formatPercent,
  limitStatusLabel,
  marketLabel,
} from "../lib/format";
import { usePortfolioLimits } from "../lib/queries";
import {
  buildLimitGaugeViewModel,
  buildSourcesSummaryViewModel,
  riskGaugeChipClass,
} from "../lib/riskGauge";
import { DETAILS_SUMMARY_RISK_GAUGE } from "../lib/oneLinerWording";
import type { BookLimitCheck, PortfolioLimitsResponse, SymbolDataMeta } from "../lib/types";
import { DataMetaStatusBadge } from "./DataMetaStatusBadge";
import { ErrorPanel } from "./ErrorPanel";
import { SkeletonBlock } from "./SkeletonBlock";

/**
 * FR-8: the book-level view of the same five caps `app.advice.limits`
 * checks per symbol (verified source), backed by `GET /api/portfolio/limits`
 * (`app/api/portfolio.py` + `app/advice/book_limits.py`, verified). Renders
 * that response as-is (`status`/`observed`/`threshold`/`detail` verbatim); it
 * does not re-derive any of it client-side.
 *
 * 首頁「一眼一句」簡化（`work/stock-desk-一眼一句-實作規格.md` §3.2，
 * risk-compliance 2026-09-19 附錄 H1–H5）: the five caps collapsed from a
 * multi-line card each into one grid row (name｜status chip｜thin bar｜
 * observed/threshold), with the full `detail` sentence, the `excluded`
 * reasons, the notes list and the per-symbol sources list all moved into one
 * shared `<details>`. Every literal below is byte-for-byte the same as the
 * previous version — this batch only changes *where* each one renders, per
 * that spec's 鐵律 1/2.
 *
 * Second pass (CEO 2026-09-19 深夜第二次裁定 §4.1，派工單同章節，wave2-B，
 * 純搬移): the CEO's second ruling explicitly overturns H4 (頂部說明句常駐)
 * — the top explanatory sentence and the "判定產生時間" timestamp move from
 * the main view into the same shared `<details>` (as its first two lines),
 * so the main view now shows only the h2 title, the five rows and the
 * details summary line. Literal text unchanged, only *where* it renders.
 *
 * Risk-compliance ruling carried forward unchanged: a cap whose `status` is
 * `not_evaluable` must never draw a progress bar, not even an empty one —
 * `shouldShowLimitBar` in `../lib/riskGauge.ts` is the one place that
 * decision is enforced (H1).
 */
function LimitBar({ check }: { check: BookLimitCheck }) {
  const view = buildLimitGaugeViewModel(check);
  if (!view.showBar) return null;
  const fillColorClass = check.status === "violated" ? "bg-rose-500" : "bg-emerald-500";
  return (
    <div
      className="h-1 w-full overflow-hidden rounded-full bg-neutral-800"
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
 * verdict, reason verbatim. Now rendered inside the shared `<details>`
 * (H2 keeps only the excluded *count* badge on the main row — see
 * `LimitGaugeRow` — the reasons themselves move here).
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

/** One cap's full disclosure, restated inside the shared `<details>` (§3.2). */
function LimitDetailItem({ check }: { check: BookLimitCheck }) {
  return (
    <li className="rounded-md border border-neutral-800 p-3">
      <p className="font-medium text-neutral-200">
        第 {check.index} 條・{check.name}
      </p>
      <p className="mt-1 text-neutral-400">{check.detail}</p>
      {/* 風控退修:沿用後端 WORST_SYMBOL_PREFIX(book_limits.py)「觀測值最高」
          這個限定語,不能只寫「最高」——這是逐檔比較裡「觀測值」最高的那一檔,
          不是隨便一種「最高」。 */}
      {check.worst_symbol !== null && <p className="mt-1 text-neutral-400">觀測值最高：{check.worst_symbol}</p>}
      <ExcludedList excluded={check.excluded} />
    </li>
  );
}

/**
 * 風控快審附帶條件（work/reviews/股數區間文案裁決.md，2026-08-09）：任一 source
 * 非 fresh 時揭露義務不變——清單本身仍完整列出。H5（本批新增）：這份清單現在
 * 併入外層共用的 `<details>`，本身不再有自己的巢狀 `<details>`；非 fresh 的
 * 訊號改成半句掛在外層 summary 上（見 `RiskGaugeView`），details 不再因此
 * 自動展開（風控核可的犧牲：使用者要先點開「詳細」才看得到清單本身）。
 */
function SourcesList({ sources }: { sources: SymbolDataMeta[] }) {
  if (sources.length === 0) return null;
  return (
    <div>
      <p className="font-semibold text-neutral-400">各標的資料來源（{sources.length}）</p>
      <ul className="mt-2 space-y-1">
        {sources.map((source) => (
          <li key={`${source.symbol}-${source.market}`} className="flex flex-wrap items-center">
            {source.symbol}（{marketLabel(source.market)}）
            <DataMetaStatusBadge
              status={source.data.status}
              stalenessMinutes={source.data.staleness_minutes}
              isWithinTtl={source.data.is_within_ttl}
              lastBarDate={source.data.last_bar_date}
              reason={source.data.reason}
            />
          </li>
        ))}
      </ul>
    </div>
  );
}

/** One cap's five-column-grid row (B.3): name｜status chip (+ H2 badge)｜thin bar｜observed/threshold. */
/**
 * 375px 手機視口修正（qa 自我檢查，實作規格未明訂窄螢幕行為）：一開始用固定
 * `grid-cols-[minmax(0,1fr)_auto_6rem_7rem]`（視覺規範 B.3 原樣）在 375px 下，
 * 固定的 `auto`/`6rem`/`7rem` 三欄合計已逼近容器寬度，`minmax(0,1fr)` 的名稱欄
 * 被壓到只剩個位數 px、名稱幾乎整個消失（哪一條上限都看不出來）。改用
 * `flex flex-wrap`：名稱固定不縮（`shrink-0`），狀態/進度條/數值合成一組，
 * 空間不夠時整組換到下一行，而不是把名稱擠沒——桌面寬度下兩者仍同一行，
 * 不影響視覺規範原意的單行密度；只是窄螢幕改成最多兩行，字面與資訊量不變。
 *
 * qa 追加（2026-09-19）：名稱不再 `truncate`（會用刪節號吃掉看不完的字）——
 * 容器已是 `flex-wrap`，改成讓名稱在窄螢幕自然換行，確保完整字面永遠可讀。
 */
function LimitGaugeRow({ check }: { check: BookLimitCheck }) {
  const hasExcluded = check.excluded.length > 0;
  return (
    <li className="border-t border-neutral-800 py-2 text-sm first:border-t-0">
      <div className="flex flex-wrap items-center gap-x-3 gap-y-1">
        <span className="max-w-full shrink-0 text-neutral-200">
          第 {check.index} 條・{check.name}
        </span>
        <div className="ml-auto flex flex-wrap items-center justify-end gap-x-3 gap-y-1">
          <span className="flex items-center gap-1">
            <span
              className={`inline-flex items-center justify-center rounded-md border px-2 py-0.5 text-xs font-semibold ${riskGaugeChipClass(check.status)}`}
            >
              {limitStatusLabel(check.status)}
            </span>
            {/* H2：未納入檔數與狀態同視覺層級，故同排、同字級呈現。 */}
            {hasExcluded && (
              <span className="whitespace-nowrap rounded bg-amber-900/40 px-1.5 py-0.5 text-xs font-semibold text-amber-300">
                未納入 {check.excluded.length} 檔
              </span>
            )}
          </span>
          <div className="w-16 shrink-0 sm:w-24">
            <LimitBar check={check} />
          </div>
          <span className="shrink-0 text-right font-mono text-xs text-neutral-400">
            {formatPercent(check.observed)}／{formatPercent(check.threshold)}
          </span>
        </div>
      </div>
      {/* H3：worst_symbol 同列（第二行）。 */}
      {check.worst_symbol !== null && (
        <p className="mt-1 text-xs text-neutral-400">觀測值最高：{check.worst_symbol}</p>
      )}
    </li>
  );
}

/**
 * Pure presentational half of the gauge, split out for unit testing without
 * a query client (`RiskGauge` below wires it to `usePortfolioLimits`).
 */
export function RiskGaugeView({ data }: { data: PortfolioLimitsResponse }) {
  const sourcesSummary = buildSourcesSummaryViewModel(data.sources);
  return (
    <>
      <ul className="mt-3">
        {data.limits.map((check) => (
          <LimitGaugeRow key={check.limit_id} check={check} />
        ))}
      </ul>

      {/* H5：新鮮度訊號改成 summary 右側半句，details 不因此自動展開。 */}
      <details className="group mt-3 text-xs text-neutral-400">
        <summary className="cursor-pointer text-neutral-400">
          {DETAILS_SUMMARY_RISK_GAUGE}
          {!sourcesSummary.allFresh && `——其中 ${sourcesSummary.staleCount} 檔非即時`}
        </summary>
        <div className="mt-3 space-y-3 border-t border-neutral-800 pt-3">
          {/* CEO 2026-09-19 第二次裁定（§4.1）推翻 H4：頂部說明句原本常駐主
              視圖，本批純搬移進詳細第一行——字面（含標點）一字不改，只改出現
              層級。原風控裁決（work/reviews/股數區間文案裁決.md,2026-08-09）
              核可的是這段文字本身，不是它的常駐位置。 */}
          <p>
            單一標的佔比、單一產業佔比、單筆最大可承受虧損三條為逐檔比較，回報最差結果；總曝險與 Kelly
            部位上限為帳本層單一判定。未納入比較的標的列於各條之下。
          </p>
          {/* 「判定產生時間」原在主視圖標題列右側；同批一併搬進詳細。 */}
          <p>判定產生時間：{formatDateTime(data.as_of)}</p>
          <ul className="space-y-2">
            {data.limits.map((check) => (
              <LimitDetailItem key={check.limit_id} check={check} />
            ))}
          </ul>

          {data.notes.length > 0 && (
            <div>
              <p className="font-semibold text-neutral-400">
                風險預算輸入的假設與限制（{data.notes.length}）
              </p>
              <ul className="mt-2 list-disc space-y-1 pl-5">
                {data.notes.map((note, i) => (
                  <li key={i}>{note}</li>
                ))}
              </ul>
            </div>
          )}

          <SourcesList sources={data.sources} />
        </div>
      </details>
    </>
  );
}

export function RiskGauge() {
  const limits = usePortfolioLimits(true);

  return (
    <div className="rounded-lg border border-neutral-800 p-5">
      <h2 className="text-lg font-semibold text-neutral-100">風險儀表</h2>
      {/* 風控退修附帶（沿用不變）:as_of 是伺服器回應時間,不是行情時間——行情
          新鮮度由下方 sources 徽章承載,這裡不得暗示「資料的時間」。「判定產生
          時間」與頂部說明句（原 H4）已隨 CEO 第二次裁定（§4.1）搬進
          `RiskGaugeView` 的共用 `<details>`，主視圖只留 h2、五列與 summary。 */}

      {limits.isPending && (
        <div className="mt-3 space-y-2">
          <SkeletonBlock className="h-8 w-full" />
          <SkeletonBlock className="h-8 w-full" />
          <SkeletonBlock className="h-8 w-full" />
          <SkeletonBlock className="h-8 w-full" />
          <SkeletonBlock className="h-8 w-full" />
        </div>
      )}

      {limits.isError && (
        <div className="mt-3">
          <ErrorPanel label="無法載入風險儀表" error={limits.error} />
        </div>
      )}

      {limits.isSuccess && <RiskGaugeView data={limits.data} />}
    </div>
  );
}

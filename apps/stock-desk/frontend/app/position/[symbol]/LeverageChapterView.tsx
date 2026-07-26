import type { LeverageChapter } from "../../lib/types";
import {
  chapterStatusLabel,
  detectionStatusLabel,
  formatDateTime,
  formatNumber,
  formatPercent,
} from "../../lib/format";
import { MeasureStatusBadge } from "../../components/MeasureStatusBadge";

function AssumptionsList({ items }: { items: string[] }) {
  if (items.length === 0) return null;
  return (
    <details className="mt-2 text-xs text-neutral-500">
      <summary className="cursor-pointer text-neutral-400">假設清單（{items.length}）</summary>
      <ul className="mt-2 list-disc space-y-1 pl-5">
        {items.map((text, i) => (
          <li key={i}>{text}</li>
        ))}
      </ul>
    </details>
  );
}

/**
 * Neutral rendering of `build_leverage_chapter()` (app/leverage/service.py,
 * verified source). Every number carries its status: this chapter never
 * substitutes a computed number for one that came back `insufficient_data`.
 */
export function LeverageChapterView({ chapter }: { chapter: LeverageChapter }) {
  if (chapter.chapter_status === "not_applicable") return null;

  return (
    <div className="mt-8 rounded-lg border border-amber-900/60 bg-amber-950/10 p-5">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <h2 className="text-lg font-semibold text-neutral-100">槓桿型 ETF 專章</h2>
        <span className="rounded bg-neutral-800 px-2 py-0.5 text-xs text-neutral-300">
          {chapterStatusLabel(chapter.chapter_status)}
        </span>
      </div>
      <p className="mt-2 text-xs text-neutral-400">{chapter.disclosure}</p>
      {chapter.reason && (
        <p className="mt-2 text-sm text-amber-300">{chapter.reason}</p>
      )}
      {chapter.notes.length > 0 && (
        <ul className="mt-2 list-disc space-y-1 pl-5 text-xs text-neutral-500">
          {chapter.notes.map((note, i) => (
            <li key={i}>{note}</li>
          ))}
        </ul>
      )}

      {/* --- Detection / metadata ------------------------------------- */}
      <section className="mt-4">
        <h3 className="text-sm font-semibold text-neutral-200">
          偵測與 Metadata（{detectionStatusLabel(chapter.detection.status)}）
        </h3>
        {chapter.detection.status === "ok" ? (
          <div className="mt-2 grid grid-cols-1 gap-x-6 gap-y-1 text-sm text-neutral-300 sm:grid-cols-2">
            <p>倍數：{chapter.detection.leverage_factor}x</p>
            <p>標的指數：{chapter.detection.underlying_index}</p>
            <p>年費用率：{formatPercent(chapter.detection.expense_ratio_annual)}</p>
            <p>
              Metadata 查證狀態：
              {chapter.detection.metadata_verified
                ? `已查證（${chapter.detection.metadata_verified_on ?? "—"}）`
                : "尚未查證（verified=false）"}
            </p>
          </div>
        ) : (
          <p className="mt-2 text-sm text-neutral-500">{chapter.detection.reason}</p>
        )}
        {chapter.detection.source_note && (
          <p className="mt-1 text-xs text-neutral-500">{chapter.detection.source_note}</p>
        )}
      </section>

      {/* --- Holding period --------------------------------------------- */}
      <section className="mt-4">
        <h3 className="text-sm font-semibold text-neutral-200">
          持有期間
          <MeasureStatusBadge status={chapter.holding.status} />
        </h3>
        {chapter.holding.status === "ok" ? (
          <p className="mt-1 text-sm text-neutral-400">
            建倉日 {chapter.holding.opened_at} ～ 最新日線 {chapter.holding.last_bar_date}，共{" "}
            {chapter.holding.holding_trading_days} 個交易日（{chapter.holding.holding_days} 曆日）。
          </p>
        ) : (
          <p className="mt-1 text-sm text-neutral-500">{chapter.holding.reason}</p>
        )}
      </section>

      {/* --- Drag decomposition ------------------------------------------ */}
      <section className="mt-4">
        <h3 className="text-sm font-semibold text-neutral-200">已實現報酬拆解（drag）</h3>
        {chapter.drag === null || chapter.drag.status !== "ok" ? (
          <p className="mt-1 text-sm text-neutral-500">
            {chapter.drag?.reason ?? "本項未啟用或未計算。"}
          </p>
        ) : (
          <>
            <div className="mt-2 overflow-x-auto">
              <table className="min-w-[480px] text-left text-sm">
                <tbody className="text-neutral-300">
                  <tr>
                    <th scope="row" className="py-1 pr-4 font-normal text-neutral-500">
                      實際報酬
                    </th>
                    <td>{formatPercent(chapter.drag.actual_return)}</td>
                  </tr>
                  <tr>
                    <th scope="row" className="py-1 pr-4 font-normal text-neutral-500">
                      Naive 期望（β×指數報酬）
                    </th>
                    <td>{formatPercent(chapter.drag.naive_expected_return)}</td>
                  </tr>
                  <tr>
                    <th scope="row" className="py-1 pr-4 font-normal text-neutral-500">
                      理想每日重置路徑
                    </th>
                    <td>{formatPercent(chapter.drag.ideal_daily_reset_return)}</td>
                  </tr>
                  <tr>
                    <th scope="row" className="py-1 pr-4 font-normal text-neutral-500">
                      Gap（實際 − naive）
                    </th>
                    <td>{formatPercent(chapter.drag.gap)}</td>
                  </tr>
                  <tr>
                    <th scope="row" className="py-1 pr-4 font-normal text-neutral-500">
                      費用效應
                    </th>
                    <td>{formatPercent(chapter.drag.fee_effect)}</td>
                  </tr>
                  <tr>
                    <th scope="row" className="py-1 pr-4 font-normal text-neutral-500">
                      重置（複利）效應
                    </th>
                    <td>{formatPercent(chapter.drag.reset_effect)}</td>
                  </tr>
                  <tr>
                    <th scope="row" className="py-1 pr-4 font-normal text-neutral-500">
                      殘差
                    </th>
                    <td>{formatPercent(chapter.drag.residual)}</td>
                  </tr>
                  <tr>
                    <th scope="row" className="py-1 pr-4 font-normal text-neutral-500">
                      恆等式誤差
                    </th>
                    <td>{formatNumber(chapter.drag.identity_abs_error, 6)}</td>
                  </tr>
                </tbody>
              </table>
            </div>
            {chapter.drag.ideal_path_wiped_out && (
              <p className="mt-1 text-xs text-rose-300">理想路徑在此期間已跌破 -100%（歸零）。</p>
            )}
            <p className="mt-2 text-xs text-neutral-500">
              理論近似 drag（{chapter.drag.theoretical.formula}）：
              {chapter.drag.theoretical.status === "ok"
                ? `${formatPercent(chapter.drag.theoretical.theoretical_drag)}（與實測重置效應差異 ${formatPercent(
                    chapter.drag.theoretical.difference,
                  )}）`
                : chapter.drag.theoretical.reason}
            </p>
            <p className="mt-2 text-xs text-neutral-600">
              資料時間：ETF {formatDateTime(chapter.drag.as_of)}／指數 {formatDateTime(chapter.drag.index_as_of)}
            </p>
            <AssumptionsList items={chapter.drag.assumptions} />
          </>
        )}
      </section>

      {/* --- Erosion scenarios -------------------------------------------- */}
      <section className="mt-4">
        <h3 className="text-sm font-semibold text-neutral-200">橫盤情境侵蝕推估（erosion）</h3>
        <p className="mt-1 text-xs text-neutral-500">
          {chapter.erosion?.nature ?? "情境推估，非預測。"}
        </p>
        {chapter.erosion === null || chapter.erosion.status !== "ok" ? (
          <p className="mt-1 text-sm text-neutral-500">
            {chapter.erosion?.reason ?? "本項未啟用或未計算。"}
          </p>
        ) : (
          <>
            <div className="mt-2 overflow-x-auto rounded-md border border-neutral-800">
              <table className="min-w-[480px] text-left text-sm">
                <thead className="bg-neutral-900 text-neutral-400">
                  <tr>
                    <th scope="col" className="px-3 py-2 font-medium">
                      情境
                    </th>
                    <th scope="col" className="px-3 py-2 font-medium">
                      波動侵蝕
                    </th>
                    <th scope="col" className="px-3 py-2 font-medium">
                      費用侵蝕
                    </th>
                    <th scope="col" className="px-3 py-2 font-medium">
                      合計侵蝕
                    </th>
                  </tr>
                </thead>
                <tbody>
                  {chapter.erosion.scenarios.map((scenario) => (
                    <tr key={scenario.label} className="border-t border-neutral-800">
                      <td className="px-3 py-2 text-neutral-300">
                        {scenario.label}（{scenario.horizon_trading_days} 交易日）
                      </td>
                      <td className="px-3 py-2 text-neutral-300">
                        {formatPercent(scenario.volatility_drag_pct)}
                      </td>
                      <td className="px-3 py-2 text-neutral-300">
                        {formatPercent(scenario.expense_pct)}
                      </td>
                      <td className="px-3 py-2 font-medium text-neutral-100">
                        {formatPercent(scenario.total_expected_erosion_pct)}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            <p className="mt-2 text-xs text-neutral-600">
              波動估計視窗：{chapter.erosion.observations}／{chapter.erosion.window} 個報酬｜資料時間：
              {formatDateTime(chapter.erosion.as_of)}
            </p>
            <AssumptionsList items={chapter.erosion.assumptions} />
          </>
        )}
      </section>

      <p className="mt-4 text-xs text-neutral-600">
        產生時間：{formatDateTime(chapter.generated_at)}
      </p>
    </div>
  );
}

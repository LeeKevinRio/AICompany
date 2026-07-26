"use client";

import { ApiError } from "../lib/api";
import { formatPercent, limitStatusColorClass, limitStatusLabel } from "../lib/format";
import { useSettings } from "../lib/queries";
import type { LimitStatus, RiskBudgetSettings } from "../lib/types";
import { SkeletonBlock } from "./SkeletonBlock";

interface PortfolioLimitGauge {
  id: string;
  name: string;
  status: LimitStatus;
  threshold: number;
  reason: string;
}

/**
 * Book-level view of the same five caps `app.advice.limits.evaluate_limits`
 * checks per symbol (verified source). None of them can be honestly computed
 * from `GET /api/portfolio/summary` alone — that endpoint has no per-position
 * market value in TWD, no sector field, no per-symbol ATR, and no win-rate/
 * payoff-ratio source (all confirmed absent by reading
 * `app/portfolio/summary.py` / `app/portfolio/valuation.py` /
 * `app/positions/models.py`). Rather than approximate a number that would
 * misrepresent real risk, every cap here is reported `not_evaluable` with its
 * threshold (from settings) and the specific reason — the risk-compliance
 * requirement is to never let a gap in computability read as "passed". The
 * fully computed, per-symbol version of each cap (real `observed` numbers) is
 * on `/position/[symbol]` via the advice card's own `limits_check`.
 */
function buildGauges(budget: RiskBudgetSettings): PortfolioLimitGauge[] {
  return [
    {
      id: "single_position_weight",
      name: "單一標的佔比上限",
      status: "not_evaluable",
      threshold: budget.max_position_weight,
      reason: "總覽頁未提供各部位台幣市值明細，無法計算單一標的佔總資產比重；請至個股頁面查看。",
    },
    {
      id: "sector_weight",
      name: "單一產業佔比上限",
      status: "not_evaluable",
      threshold: budget.max_sector_weight,
      reason: "持倉資料目前沒有產業別欄位，這條上限尚未能被檢查（與個股建議卡狀態一致）。",
    },
    {
      id: "gross_exposure",
      name: "總曝險上限",
      status: "not_evaluable",
      threshold: budget.max_gross_exposure,
      reason: "系統未記錄部位以外的現金部位，無法確定「總資產」與「總曝險」的比例關係。",
    },
    {
      id: "per_trade_loss",
      name: "單筆最大可承受虧損",
      status: "not_evaluable",
      threshold: budget.max_loss_per_trade,
      reason: "此上限需要逐檔的 ATR(14) 訊號；總覽頁未逐檔查詢訊號，請至個股頁面查看。",
    },
    {
      id: "kelly_fraction",
      name: "分數 Kelly 部位上限",
      status: "not_evaluable",
      threshold: budget.kelly_position_cap,
      reason: "缺少勝率或盈虧比，目前沒有資料來源提供這兩項輸入（與個股建議卡狀態一致）。",
    },
  ];
}

export function RiskGauge() {
  const settings = useSettings(true);

  return (
    <div className="rounded-lg border border-neutral-800 p-5">
      <h2 className="text-lg font-semibold text-neutral-100">風險儀表</h2>
      <p className="mt-1 text-xs text-neutral-500">
        總覽頁僅能顯示各上限「是否可被評估」；完整的逐檔觀察值請至個股頁面查看建議卡。
      </p>

      {settings.isPending && (
        <div className="mt-3 space-y-2">
          <SkeletonBlock className="h-10 w-full" />
          <SkeletonBlock className="h-10 w-full" />
          <SkeletonBlock className="h-10 w-full" />
        </div>
      )}
      {settings.isError && (
        <p role="alert" className="mt-3 rounded-md border border-red-900 bg-red-950/40 px-4 py-3 text-sm text-red-300">
          無法載入風險預算設定：
          {settings.error instanceof ApiError ? settings.error.message : "未知錯誤"}
        </p>
      )}
      {settings.isSuccess && (
        <ul className="mt-3 space-y-2">
          {buildGauges(settings.data.settings.risk_budget).map((gauge) => (
            <li key={gauge.id} className="rounded-md border border-neutral-800 p-3 text-sm">
              <div className="flex flex-wrap items-center justify-between gap-2">
                <span className="font-medium text-neutral-100">{gauge.name}</span>
                <span className={`text-xs font-semibold ${limitStatusColorClass(gauge.status)}`}>
                  {limitStatusLabel(gauge.status)}
                </span>
              </div>
              <div className="mt-2 h-1.5 w-full overflow-hidden rounded-full bg-neutral-800" aria-hidden="true">
                <div className="h-full w-0 rounded-full bg-neutral-600" />
              </div>
              <p className="mt-1 text-xs text-neutral-500">
                上限：{formatPercent(gauge.threshold)}｜{gauge.reason}
              </p>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

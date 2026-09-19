import type { PortfolioTotals } from "../lib/types";
import { formatDateTime, formatMoney, pnlColorClass } from "../lib/format";
import { DETAILS_SUMMARY_GENERIC, FX_BACKUP_BADGE } from "../lib/oneLinerWording";

function StatusBanner({ status }: { status: PortfolioTotals["status"] }) {
  if (status === "partial") {
    return (
      <p
        role="status"
        className="rounded-md border border-amber-800 bg-amber-950/50 px-4 py-2 text-sm text-amber-300"
      >
        部分標的資料不足，總計僅含可估值部位。
      </p>
    );
  }
  if (status === "no_data") {
    return (
      <p
        role="status"
        className="rounded-md border border-amber-800 bg-amber-950/50 px-4 py-2 text-sm text-amber-300"
      >
        目前所有部位皆無可用估值資料，總計無法計算。
      </p>
    );
  }
  return null;
}

export function SummaryCards({
  totals,
  asOf,
  fxDisclosures,
  fxBackupActive,
}: {
  totals: PortfolioTotals;
  asOf: string;
  //: ADR-0011; disclosure sentences for every FX source actually used this
  //: pass (`PortfolioSummaryResponse.fx_disclosures`), rendered verbatim
  //: inside the 匯率貢獻 card. CEO 2026-09-19 第二次裁定（派工單 §4.1）推翻
  //: 風控 2026-09-19 條件 (1) 的「同位置常駐、不得摺疊」要求：句子字面不改，
  //: 只改出現層級——本批純搬移進卡內的 `<details>`（wave2-B，鐵律 1/2）。
  fxDisclosures: string[];
  //: 第二波（派工單 §4.3，風控逐字審核可）：true when *any* position's
  //: `valuation.fx?.data_status === "backup"` (`page.tsx` derives this from
  //: `summary.data.positions`). Drives the standing `FX_BACKUP_BADGE` badge
  //: beside the 匯率貢獻 title — no threshold, never hover-only.
  fxBackupActive: boolean;
}) {
  return (
    <div className="space-y-3">
      <StatusBanner status={totals.status} />

      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
        <div className="rounded-lg border border-neutral-800 p-5">
          <p className="text-sm text-neutral-400">總資產（市值）</p>
          <p className="mt-1 text-3xl font-bold text-neutral-100">
            {formatMoney(totals.market_value_twd, "TWD", 0)}
          </p>
          <p className="mt-1 text-xs text-neutral-500">
            資料時間：{formatDateTime(asOf)}
          </p>
        </div>
        <div className="rounded-lg border border-neutral-800 p-5">
          <p className="text-sm text-neutral-400">未實現損益</p>
          <p
            className={`mt-1 text-3xl font-bold ${pnlColorClass(totals.unrealized_pnl_twd)}`}
          >
            {formatMoney(totals.unrealized_pnl_twd, "TWD", 0)}
          </p>
          {/* 「資料時間」原本兩卡各印一次，字面完全重複；本批只留總資產卡一處
              （wave2-B 純搬移，句子本身不改字）。 */}
        </div>
      </div>

      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
        <div className="rounded-lg border border-neutral-800 p-4">
          <p className="text-sm text-neutral-400">標的貢獻</p>
          <p
            className={`mt-1 text-xl font-semibold ${pnlColorClass(totals.asset_contribution_twd)}`}
          >
            {formatMoney(totals.asset_contribution_twd, "TWD", 0)}
          </p>
        </div>
        <div className="rounded-lg border border-neutral-800 p-4">
          <p className="flex flex-wrap items-center gap-1.5 text-sm text-neutral-400">
            匯率貢獻
            {/* 第二波（派工單 §4.3）：任一部位匯率為備援源即常駐顯示，不設
                門檻、不得 hover-only；配色沿用 DataStatusBadge/FxStatusBadge
                的 backup 樣式。 */}
            {fxBackupActive && (
              <span className="rounded bg-amber-900/40 px-1.5 py-0.5 text-xs text-amber-300">
                {FX_BACKUP_BADGE}
              </span>
            )}
          </p>
          <p
            className={`mt-1 text-xl font-semibold ${pnlColorClass(totals.fx_contribution_twd)}`}
          >
            {formatMoney(totals.fx_contribution_twd, "TWD", 0)}
          </p>
          {fxDisclosures.length > 0 && (
            <details className="group mt-2 text-xs text-neutral-400">
              <summary className="cursor-pointer text-neutral-400">{DETAILS_SUMMARY_GENERIC}</summary>
              <ul className="mt-2 space-y-0.5">
                {fxDisclosures.map((disclosure) => (
                  <li key={disclosure}>{disclosure}</li>
                ))}
              </ul>
            </details>
          )}
        </div>
      </div>
    </div>
  );
}

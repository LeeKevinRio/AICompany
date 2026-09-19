import type { PortfolioTotals } from "../lib/types";
import { formatDateTime, formatMoney, pnlColorClass } from "../lib/format";

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
}: {
  totals: PortfolioTotals;
  asOf: string;
  //: ADR-0011; 風控 2026-09-19 條件 (1): standing disclosure sentences for
  //: every FX source actually used this pass (`PortfolioSummaryResponse
  //: .fx_disclosures`), rendered verbatim beside the 匯率貢獻 card. Never
  //: truncated or collapsed — same position, style and font size as every
  //: other disclosure.
  fxDisclosures: string[];
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
          <p className="mt-1 text-xs text-neutral-500">
            資料時間：{formatDateTime(asOf)}
          </p>
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
          <p className="text-sm text-neutral-400">匯率貢獻</p>
          <p
            className={`mt-1 text-xl font-semibold ${pnlColorClass(totals.fx_contribution_twd)}`}
          >
            {formatMoney(totals.fx_contribution_twd, "TWD", 0)}
          </p>
          {fxDisclosures.length > 0 && (
            <ul className="mt-2 space-y-0.5 text-xs text-neutral-400">
              {fxDisclosures.map((disclosure) => (
                <li key={disclosure}>{disclosure}</li>
              ))}
            </ul>
          )}
        </div>
      </div>
    </div>
  );
}

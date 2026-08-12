import { formatMoney, pnlColorClass } from "../lib/format";
import { formatScaledPercent } from "../lib/playbookView";
import type { PlaybookBatchSnapshot } from "../lib/types";

// 視覺規範 §7 逐字沿用欄位名稱；不含「距下一停利/停損門檻」距離列（§7 明列
// 排除，歸入 Phase 2）。
const COLUMN_HEADERS = ["標的", "批次序號", "批次成本", "現價", "盈虧%", "波段最高收盤"];

/**
 * 第 2 層部位快照 (視覺規範 §7): 沿用站內既有表格慣例
 * (`work/stock-desk-視覺規範-捲軸與表格.md` / `PositionsTable.tsx`) —
 * `rounded-md` 外框、`thead bg-neutral-900 text-neutral-400`、
 * `border-t border-neutral-800` 列分隔。盈虧% 仍用既有 `pnlColorClass`
 * （紅漲綠跌，全站價格語彙，不受帳冊列的規則家族色彙軸約束，§7 明文）。
 */
export function PositionSnapshotTable({ snapshot }: { snapshot: PlaybookBatchSnapshot[] }) {
  return (
    <section className="mt-6">
      <h2 className="text-lg font-semibold text-neutral-100">部位快照</h2>
      {snapshot.length === 0 ? (
        <p className="mt-3 text-sm text-neutral-400">無。</p>
      ) : (
        <div className="mt-3 overflow-x-auto rounded-md border border-neutral-800">
          <table className="w-full min-w-[640px] text-left text-sm">
            <caption className="sr-only">部位快照</caption>
            <thead className="bg-neutral-900 text-neutral-400">
              <tr>
                {COLUMN_HEADERS.map((header) => (
                  <th key={header} scope="col" className="whitespace-nowrap px-3 py-2 font-medium">
                    {header}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {snapshot.map((batch) => (
                <tr key={`${batch.symbol}-${batch.batch_no}`} className="border-t border-neutral-800">
                  <td className="whitespace-nowrap px-3 py-2 font-medium text-neutral-100">
                    {batch.symbol}
                  </td>
                  <td className="whitespace-nowrap px-3 py-2 text-neutral-300">第 {batch.batch_no} 批</td>
                  <td className="whitespace-nowrap px-3 py-2 text-neutral-300">
                    {formatMoney(batch.cost, "TWD", 2)}
                  </td>
                  <td className="whitespace-nowrap px-3 py-2 text-neutral-300">
                    {formatMoney(batch.close, "TWD", 2)}
                  </td>
                  <td className={`whitespace-nowrap px-3 py-2 ${pnlColorClass(batch.unrealized_pct)}`}>
                    {formatScaledPercent(batch.unrealized_pct)}
                  </td>
                  <td className="whitespace-nowrap px-3 py-2 text-neutral-300">
                    {formatMoney(batch.peak_close, "TWD", 2)}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </section>
  );
}

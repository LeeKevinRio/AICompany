import type { PnlOriginal, SummaryPositionItem } from "../lib/types";
import {
  formatDateTime,
  formatMoney,
  formatQuantity,
  instrumentTypeLabel,
  marketLabel,
  pnlColorClass,
} from "../lib/format";
import { DataStatusBadge } from "./DataStatusBadge";
import { EmptyPositionsState } from "./EmptyPositionsState";

const COLUMN_HEADERS = [
  "代號",
  "市場",
  "類型",
  "數量",
  "平均成本（原幣）",
  "現價",
  "原幣損益",
  "台幣損益",
  "標的貢獻",
  "匯率貢獻",
];

// NOTE: price/pnl_original/pnl_twd/asset_contribution_twd/fx_contribution_twd
// all live under `position.valuation`, never as sibling fields on the
// position itself — verified against backend/app/portfolio/valuation.py.
function PriceCell({ position }: { position: SummaryPositionItem }) {
  const { valuation } = position;
  if (valuation.status === "insufficient_data" || valuation.price === null) {
    return (
      <div>
        <span className="text-neutral-500">—</span>
        <DataStatusBadge price={valuation.price} />
        {valuation.missing.length > 0 && (
          <p className="mt-0.5 text-xs text-neutral-500">
            缺：{valuation.missing.join("、")}
          </p>
        )}
      </div>
    );
  }
  return (
    <div>
      <span
        title={`資料來源：${valuation.price.source}／${formatDateTime(valuation.price.as_of)}`}
      >
        {formatMoney(valuation.price.value, position.currency, 2)}
      </span>
      <DataStatusBadge price={valuation.price} />
    </div>
  );
}

// `pnl_original` is an object `{ value, currency }`, not a bare string, so
// it gets its own cell renderer rather than reusing `MoneyOrDash`.
function PnlOriginalCell({ pnlOriginal }: { pnlOriginal: PnlOriginal | null }) {
  if (pnlOriginal === null) return <span className="text-neutral-500">—</span>;
  return (
    <span className={pnlColorClass(pnlOriginal.value)}>
      {formatMoney(pnlOriginal.value, pnlOriginal.currency, 2)}
    </span>
  );
}

function MoneyOrDash({
  value,
  currency,
  decimals,
}: {
  value: string | null;
  currency: string;
  decimals: number;
}) {
  if (value === null) return <span className="text-neutral-500">—</span>;
  return <span className={pnlColorClass(value)}>{formatMoney(value, currency, decimals)}</span>;
}

export function PositionsTable({ positions }: { positions: SummaryPositionItem[] }) {
  if (positions.length === 0) {
    return <EmptyPositionsState />;
  }

  return (
    <div className="overflow-x-auto rounded-lg border border-neutral-800">
      <table className="w-full min-w-[880px] text-left text-sm">
        <caption className="sr-only">持倉明細表</caption>
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
          {positions.map((position) => (
            <tr key={position.id} className="border-t border-neutral-800">
              <td className="whitespace-nowrap px-3 py-2 font-medium text-neutral-100">
                {position.symbol}
              </td>
              <td className="whitespace-nowrap px-3 py-2 text-neutral-300">
                {marketLabel(position.market)}
              </td>
              <td className="whitespace-nowrap px-3 py-2 text-neutral-300">
                {instrumentTypeLabel(position.instrument_type)}
              </td>
              <td className="whitespace-nowrap px-3 py-2 text-neutral-300">
                {formatQuantity(position.quantity)}
              </td>
              <td className="whitespace-nowrap px-3 py-2 text-neutral-300">
                {formatMoney(position.avg_cost, position.currency, 2)}
              </td>
              <td className="whitespace-nowrap px-3 py-2">
                <PriceCell position={position} />
              </td>
              <td className="whitespace-nowrap px-3 py-2">
                <PnlOriginalCell pnlOriginal={position.valuation.pnl_original} />
              </td>
              <td className="whitespace-nowrap px-3 py-2">
                <MoneyOrDash value={position.valuation.pnl_twd} currency="TWD" decimals={0} />
              </td>
              <td className="whitespace-nowrap px-3 py-2">
                <MoneyOrDash
                  value={position.valuation.asset_contribution_twd}
                  currency="TWD"
                  decimals={0}
                />
              </td>
              <td className="whitespace-nowrap px-3 py-2">
                <MoneyOrDash
                  value={position.valuation.fx_contribution_twd}
                  currency="TWD"
                  decimals={0}
                />
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

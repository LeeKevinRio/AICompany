"use client";

import Link from "next/link";
import { useState } from "react";
import type { PnlOriginal, SummaryPositionItem } from "../lib/types";
import {
  formatDateTime,
  formatMoney,
  formatQuantity,
  instrumentTypeLabel,
  marketLabel,
  pnlColorClass,
} from "../lib/format";
import { deleteButtonState } from "../lib/positionFormSubmit";
import { useDeletePosition, useDirectoryNames } from "../lib/queries";
import { DataStatusBadge } from "./DataStatusBadge";
import { EditPositionModal } from "./EditPositionModal";
import { EmptyPositionsState } from "./EmptyPositionsState";
import { ErrorPanel } from "./ErrorPanel";

const COLUMN_HEADERS = [
  "代號",
  "市場",
  "類型",
  "數量",
  "平均成本（原幣）",
  "建倉日期",
  "現價",
  "原幣損益",
  "台幣損益",
  "標的貢獻",
  "匯率貢獻",
  "操作",
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
  const [editingPosition, setEditingPosition] = useState<SummaryPositionItem | null>(null);
  // `useDeletePosition()` is a *single* mutation instance shared by every
  // row's button below — `pendingDeleteId` (not `deleteMutation.variables`)
  // is what actually tracks which row is in flight, because keying off the
  // shared instance's `variables` breaks the moment a second row's delete is
  // confirmed before the first finishes (see `deleteButtonState`'s doc
  // comment in `lib/positionFormSubmit.ts` — this is the delete-side half of
  // the CEO's 2026-08-16 送出體驗 UX 缺陷 report).
  const [pendingDeleteId, setPendingDeleteId] = useState<number | null>(null);
  const deleteMutation = useDeletePosition();
  // FR-6/AC-14: company name next to the symbol link. A directory miss
  // simply leaves that symbol out of the map, so the row falls back to
  // showing the symbol alone — no placeholder text (same rule as the
  // individual position page's title).
  const namesBySymbol = useDirectoryNames(positions.map((p) => p.symbol));

  if (positions.length === 0) {
    return <EmptyPositionsState />;
  }

  function handleDelete(position: SummaryPositionItem) {
    // Blocks both a re-click on the same row and a click on a *different*
    // row while a delete is already in flight — the latter is what used to
    // silently steal the first row's pending indicator on the shared
    // mutation instance.
    if (pendingDeleteId !== null) return;
    const confirmed = window.confirm(
      `確定刪除 ${position.symbol} 的持倉？此動作無法復原。`,
    );
    if (!confirmed) return;
    setPendingDeleteId(position.id);
    deleteMutation.mutate(position.id, {
      onSettled: () => setPendingDeleteId(null),
    });
  }

  return (
    <div>
      {deleteMutation.isError && (
        <div className="mb-3">
          <ErrorPanel label="刪除失敗" error={deleteMutation.error} />
        </div>
      )}
      <div className="overflow-x-auto rounded-md border border-neutral-800">
        <table className="w-full min-w-[980px] text-left text-sm">
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
                <td className="whitespace-nowrap px-3 py-2 font-medium">
                  <Link
                    href={`/position/${encodeURIComponent(position.symbol)}?market=${position.market}`}
                    className="text-sky-400 underline hover:text-sky-300"
                  >
                    {position.symbol}
                  </Link>
                  {namesBySymbol[position.symbol] && (
                    <span className="ml-1 text-xs font-normal text-neutral-500">
                      {namesBySymbol[position.symbol]}
                    </span>
                  )}
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
                <td className="whitespace-nowrap px-3 py-2 text-neutral-300">
                  {position.opened_at ?? "—"}
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
                <td className="whitespace-nowrap px-3 py-2">
                  <div className="flex gap-2">
                    <button
                      type="button"
                      onClick={() => setEditingPosition(position)}
                      disabled={pendingDeleteId === position.id}
                      aria-label={`編輯 ${position.symbol} 持倉`}
                      className="rounded-md border border-neutral-700 px-2 py-1 text-xs text-neutral-300 hover:bg-neutral-800 disabled:cursor-not-allowed disabled:opacity-50"
                    >
                      編輯
                    </button>
                    <button
                      type="button"
                      onClick={() => handleDelete(position)}
                      disabled={deleteButtonState(pendingDeleteId, position.id).disabled}
                      aria-label={`刪除 ${position.symbol} 持倉`}
                      className="rounded-md border border-red-900 px-2 py-1 text-xs text-red-300 hover:bg-red-950/40 disabled:cursor-not-allowed disabled:opacity-50"
                    >
                      {deleteButtonState(pendingDeleteId, position.id).label}
                    </button>
                  </div>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {editingPosition && (
        <EditPositionModal position={editingPosition} onClose={() => setEditingPosition(null)} />
      )}
    </div>
  );
}

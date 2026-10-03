"use client";

import Link from "next/link";
import { useState } from "react";
import type { Dispatch, SetStateAction } from "react";
import type { ChangeMode, PnlOriginal, SummaryPositionItem } from "../lib/types";
import {
  formatMoney,
  formatQuantity,
  instrumentTypeLabel,
  marketLabel,
  pnlColorClass,
} from "../lib/format";
import { deleteButtonState } from "../lib/positionFormSubmit";
import {
  CHANGE_COLUMN_RESIDUAL_NOTE,
  DETAIL_FIELD_LABELS,
  FOREIGN_PNL_PERCENT_NOTE,
  PRIMARY_HEADER_LABELS,
  SORT_CONTROL_LABEL,
  allowIntradayFromMode,
  changeHeaderLabel,
  formatSignedPercent,
  hasForeignCurrencyPosition,
  isChangeColumnRendered,
  isNonDailyClosePrice,
  nextSortState,
  pnlPercentTwd,
  resolveChangeCell,
  sortOptionId,
  sortOptions,
  sortPositions,
  sortStateFromOptionId,
} from "../lib/positionsTableView";
import type { SortDirection, SortKey, SortState } from "../lib/positionsTableView";
import { useDeletePosition, useDirectoryNames } from "../lib/queries";
import { missingSummary } from "../lib/valuationWording";
import { DataStatusBadge, priceDateTooltip } from "./DataStatusBadge";
import { FxStatusBadge } from "./FxStatusBadge";
import { EditPositionModal } from "./EditPositionModal";
import { EmptyPositionsState } from "./EmptyPositionsState";
import { ErrorPanel } from "./ErrorPanel";

// NOTE: price/pnl_original/pnl_twd/asset_contribution_twd/fx_contribution_twd
// all live under `position.valuation`, never as sibling fields on the
// position itself — verified against backend/app/portfolio/valuation.py.
//
// Home reflow, phase 1 (CEO 2026-10-03: "simple, inventory status and market
// risk at a glance"; `work/stock-desk-首頁重排-視覺規範-2026-10-03.md` §2).
// Default view keeps only symbol/name, price + date, TWD P&L (with the
// TWD-basis percentage); the other eight fields move into a per-row expandable
// block with their labels unchanged. No fixed min-width or horizontal scroll:
// desktop uses grid columns, mobile (< md) re-flows the same DOM into a
// two-column card.
// Phase 2 adds the change column (ADR-0016 K-9..K-15): the header, the mobile
// mini-label and sort options 8/9 all read one derived value,
// `allowIntraday` (from the backend's `change_mode`); every cell is fail-closed
// through `resolveChangeCell`; nothing is recomputed or inferred here.

/**
 * Row grid shared by the header and every row. Mobile: name+price | pnl%, pnl
 * and change stacked | chevron. Desktop: chevron | name | price | pnl% (96px)
 * | pnl | change.
 */
const ROW_GRID =
  "grid grid-cols-[minmax(0,1fr)_minmax(5.5rem,40%)_2.75rem] gap-x-3 md:grid-cols-[2.75rem_minmax(0,1.4fr)_minmax(0,1.3fr)_6rem_minmax(8rem,1fr)_minmax(7.5rem,1fr)]";

const PLACEHOLDER = <span className="text-neutral-400">—</span>;

function PriceCell({ position }: { position: SummaryPositionItem }) {
  const { valuation } = position;
  // K-10 / K-14: any price whose kind is not `daily_close` (an intraday row has
  // no approved label in this build; an unknown kind is never guessed) shows a
  // bare "—": no "收盤" date label, no intraday label.
  if (isNonDailyClosePrice(position)) return <div>{PLACEHOLDER}</div>;
  if (valuation.status === "insufficient_data" || valuation.price === null) {
    return (
      <div>
        {PLACEHOLDER}
        <div className="mt-0.5">
          <DataStatusBadge price={valuation.price} />
        </div>
        {/* 風控 2026-09-18 C-1: tokens are labelled, never printed raw; each label
            says whether the system asked and found nothing, or did not ask. */}
        {valuation.missing.length > 0 && (
          <p className="mt-0.5 text-xs text-neutral-400">{missingSummary(valuation.missing)}</p>
        )}
      </div>
    );
  }
  return (
    <div>
      <span
        className="text-sm tabular-nums text-neutral-100"
        title={`資料來源：${valuation.price.source}／${priceDateTooltip(valuation.price.as_of)}`}
      >
        {formatMoney(valuation.price.value, position.currency, 2)}
      </span>
      <div className="mt-0.5">
        <DataStatusBadge price={valuation.price} />
      </div>
    </div>
  );
}

// `pnl_original` is an object `{ value, currency }`, not a bare string, so
// it gets its own cell renderer rather than reusing `MoneyOrDash`.
function PnlOriginalCell({ pnlOriginal }: { pnlOriginal: PnlOriginal | null }) {
  if (pnlOriginal === null) return PLACEHOLDER;
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
  if (value === null) return PLACEHOLDER;
  return <span className={pnlColorClass(value)}>{formatMoney(value, currency, decimals)}</span>;
}

/**
 * 台幣損益％ (home reflow phase 2, spec §8 L3). Risk-approved label
 * `PRIMARY_HEADER_LABELS.pnlPercentTwd`; the value always carries `%` and an
 * explicit sign (`formatSignedPercent`), and shows "—" when it cannot be
 * computed. The small label is mobile-only (desktop has the column header).
 */
function PnlPercentCell({ position }: { position: SummaryPositionItem }) {
  const percent = pnlPercentTwd(position);
  return (
    <div className="text-right">
      <p className="text-xs text-neutral-400 md:hidden">{PRIMARY_HEADER_LABELS.pnlPercentTwd}</p>
      <p className="text-sm tabular-nums">
        {percent === null ? (
          PLACEHOLDER
        ) : (
          <span className={pnlColorClass(position.valuation.pnl_twd)}>{formatSignedPercent(percent)}</span>
        )}
      </p>
    </div>
  );
}

/**
 * Change column cell (ADR-0016). Line 1 is the signed percentage (`+2.59%`,
 * always with `%`, red up / green down via `pnlColorClass`) and line 2 is the
 * basis label `較 MM/DD 收盤`: a number always has its label, and a "—" never
 * has any basis wording. When there is no label, line 2 is an invisible
 * placeholder that keeps the row height (art-lead spec §3). The small label is
 * mobile-only (desktop has the column header) and is the same constant as the
 * header. No `title`, no expandable block.
 */
function ChangeCell({ position, allowIntraday }: { position: SummaryPositionItem; allowIntraday: boolean }) {
  const view = resolveChangeCell(position, allowIntraday);
  return (
    <div className="text-right">
      <p className="text-xs text-neutral-400 md:hidden">{changeHeaderLabel(allowIntraday)}</p>
      <p className="text-sm tabular-nums">
        {view.kind === "dash" ? (
          PLACEHOLDER
        ) : (
          <span className={pnlColorClass(view.colorValue)}>{view.text}</span>
        )}
      </p>
      {view.kind === "dash" ? (
        <p className="mt-0.5 text-xs" aria-hidden="true">
          &nbsp;
        </p>
      ) : (
        <p className="mt-0.5 text-xs tabular-nums text-neutral-400">{view.basisLabel}</p>
      )}
    </div>
  );
}

/** 台幣損益 + FX provenance (the FX date and badge are disclosures and stay in the default view). */
function PnlTwdCell({ position }: { position: SummaryPositionItem }) {
  return (
    <div className="text-right">
      <p className="text-xs text-neutral-400 md:hidden">{PRIMARY_HEADER_LABELS.pnlTwd}</p>
      <p className="text-sm tabular-nums">
        <MoneyOrDash value={position.valuation.pnl_twd} currency="TWD" decimals={0} />
      </p>
      <div className="mt-0.5">
        <FxStatusBadge fx={position.valuation.fx} />
      </div>
    </div>
  );
}

function DetailField({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className="min-w-0">
      <dt className="text-xs text-neutral-400">{label}</dt>
      <dd className="mt-0.5 break-words text-sm text-neutral-300">{children}</dd>
    </div>
  );
}

export interface PositionsTableViewProps {
  positions: SummaryPositionItem[];
  namesBySymbol: Record<string, string>;
  /** Ids of the rows whose block is open; defaults to none (all collapsed). */
  initialExpandedIds?: readonly number[];
  /** Backend `change_mode`; the only input that decides the change column's header and options. */
  changeMode: ChangeMode;
  pendingDeleteId: number | null;
  onEdit: (position: SummaryPositionItem) => void;
  onDelete: (position: SummaryPositionItem) => void;
}

function ariaSortValue(
  state: SortState,
  key: SortKey,
): "ascending" | "descending" | "none" {
  if (state === null || state.key !== key) return "none";
  return state.direction === "desc" ? "descending" : "ascending";
}

function directionArrow(direction: SortDirection | null): string {
  if (direction === "desc") return "▾";
  if (direction === "asc") return "▴";
  return "↕";
}

/**
 * Desktop sortable column header. Accessible name = the visible label; the
 * direction is announced through `aria-sort` on the enclosing columnheader.
 * The arrow is neutral grey on purpose (never red/green).
 */
function SortableHeader({
  label,
  sortKey,
  sort,
  onSort,
  align,
}: {
  label: string;
  sortKey: SortKey;
  sort: SortState;
  onSort: (next: SortState) => void;
  align: "left" | "right";
}) {
  const active = sort !== null && sort.key === sortKey;
  return (
    <span
      role="columnheader"
      aria-sort={ariaSortValue(sort, sortKey)}
      className={align === "right" ? "text-right" : undefined}
    >
      <button
        type="button"
        onClick={() => onSort(nextSortState(sort, sortKey))}
        className={`inline-flex min-h-8 items-center gap-1 whitespace-nowrap rounded px-1 font-medium hover:text-neutral-100 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-sky-400 ${
          active ? "text-neutral-100" : "text-neutral-400"
        }`}
      >
        {label}
        <span aria-hidden="true" className="text-xs text-neutral-400">
          {directionArrow(active ? sort.direction : null)}
        </span>
      </button>
    </span>
  );
}

const SORT_SELECT_ID = "positions-sort-select";

function toggleId(setter: Dispatch<SetStateAction<ReadonlySet<number>>>, id: number) {
  setter((current) => {
    const next = new Set(current);
    if (next.has(id)) next.delete(id);
    else next.add(id);
    return next;
  });
}

/**
 * Presentational half (no query client needed) so the structure can be
 * unit-tested with `renderToStaticMarkup`. Default order is the backend's;
 * clicking a sortable header cycles default direction -> reverse -> backend
 * order. The mobile (< md) dropdown reads and writes the same `sort` state.
 */
export function PositionsTableView({
  positions,
  namesBySymbol,
  initialExpandedIds = [],
  changeMode,
  pendingDeleteId,
  onEdit,
  onDelete,
}: PositionsTableViewProps) {
  const [expanded, setExpanded] = useState<ReadonlySet<number>>(() => new Set(initialExpandedIds));
  const [sort, setSort] = useState<SortState>(null);
  // K-9: the one derived value. Header, mobile mini-label, sort options 8/9 and
  // whether an intraday row may render all read only this.
  const allowIntraday = allowIntradayFromMode(changeMode);
  const rows = sortPositions(positions, sort, allowIntraday);
  // The change column (and so its residual note) exists only while the table has rows.
  if (!isChangeColumnRendered(positions)) return null;

  return (
    <div>
    {/* Basis sentence: between the page h2 and the table/list, both widths, never a title or inside the expandable block. */}
    {hasForeignCurrencyPosition(positions) && (
      <p className="mb-2 text-xs text-neutral-400">{FOREIGN_PNL_PERCENT_NOTE}</p>
    )}
    {/* Change column residual disclosure (ADR-0016 D-6): its own paragraph right under the
        foreign-currency sentence, same class, both widths. Gated only by the column being
        rendered: never by `change` nullness, never by `change_mode`; never a title or details. */}
    <p className="mb-2 text-xs text-neutral-400">{CHANGE_COLUMN_RESIDUAL_NOTE}</p>
    <div className="mb-2 flex items-center justify-end gap-2 md:hidden">
      <label htmlFor={SORT_SELECT_ID} className="text-sm text-neutral-300">
        {SORT_CONTROL_LABEL}
      </label>
      <select
        id={SORT_SELECT_ID}
        value={sortOptionId(sort)}
        onChange={(e) => setSort(sortStateFromOptionId(e.target.value))}
        className="min-h-11 rounded-md border border-neutral-700 bg-neutral-900 px-2 text-sm text-neutral-100 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-sky-400"
      >
        {sortOptions(allowIntraday).map((option) => (
          <option key={option.id} value={option.id}>
            {option.label}
          </option>
        ))}
      </select>
    </div>
    <div
      role="table"
      aria-label="持倉明細表"
      className="overflow-hidden rounded-md border border-neutral-800"
    >
      <div role="rowgroup" className="hidden bg-neutral-900 text-neutral-400 md:block">
        <div role="row" className={`${ROW_GRID} items-center px-3 py-2 text-sm font-medium`}>
          <span role="columnheader" aria-hidden="true" />
          <SortableHeader
            label={PRIMARY_HEADER_LABELS.symbol}
            sortKey="symbol"
            sort={sort}
            onSort={setSort}
            align="left"
          />
          <span role="columnheader">{PRIMARY_HEADER_LABELS.price}</span>
          <SortableHeader
            label={PRIMARY_HEADER_LABELS.pnlPercentTwd}
            sortKey="pnlPercentTwd"
            sort={sort}
            onSort={setSort}
            align="right"
          />
          <SortableHeader
            label={PRIMARY_HEADER_LABELS.pnlTwd}
            sortKey="pnlTwd"
            sort={sort}
            onSort={setSort}
            align="right"
          />
          <SortableHeader
            label={changeHeaderLabel(allowIntraday)}
            sortKey="change"
            sort={sort}
            onSort={setSort}
            align="right"
          />
        </div>
      </div>

      {rows.map((position) => {
        const open = expanded.has(position.id);
        const detailId = `pos-detail-${position.id}`;
        const deleteState = deleteButtonState(pendingDeleteId, position.id);
        const name = namesBySymbol[position.symbol];
        return (
          <div key={position.id} role="rowgroup" className="border-t border-neutral-800 first:border-t-0">
            <div role="row" className={`${ROW_GRID} items-start px-3 py-2.5`}>
              <div className="min-w-0 space-y-1 md:contents">
                <div role="cell" className="min-w-0">
                  <p className="font-medium">
                    <Link
                      href={`/position/${encodeURIComponent(position.symbol)}?market=${position.market}`}
                      className="text-sky-400 underline hover:text-sky-300"
                    >
                      {position.symbol}
                    </Link>
                  </p>
                  {name && <p className="truncate text-xs text-neutral-400">{name}</p>}
                </div>
                <div role="cell" className="min-w-0">
                  <PriceCell position={position} />
                </div>
              </div>
              <div className="min-w-0 space-y-1 md:contents">
                <div role="cell" className="min-w-0 md:col-start-4 md:row-start-1">
                  <PnlPercentCell position={position} />
                </div>
                <div role="cell" className="min-w-0 md:col-start-5 md:row-start-1">
                  <PnlTwdCell position={position} />
                </div>
                <div role="cell" className="min-w-0 md:col-start-6 md:row-start-1">
                  <ChangeCell position={position} allowIntraday={allowIntraday} />
                </div>
              </div>
              <div
                role="cell"
                className="flex justify-end md:col-start-1 md:row-start-1 md:justify-center"
              >
                <button
                  type="button"
                  aria-expanded={open}
                  aria-controls={detailId}
                  aria-label={`${position.symbol} 持倉明細`}
                  onClick={() => toggleId(setExpanded, position.id)}
                  className="group inline-flex h-11 w-11 items-center justify-center rounded text-neutral-400 hover:text-neutral-100 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-sky-400 active:text-neutral-100"
                >
                  <span
                    aria-hidden="true"
                    className="inline-block text-xs transition-transform duration-150 group-aria-expanded:rotate-90 motion-reduce:transition-none"
                  >
                    ▸
                  </span>
                </button>
              </div>
            </div>

            {/* Always in the DOM (hidden while collapsed) so `aria-controls` resolves. */}
            <div role="row" id={detailId} hidden={!open}>
              <div
                role="cell"
                className="border-t border-neutral-800 bg-neutral-900/40 px-3 py-3"
              >
                <dl className="grid grid-cols-2 gap-x-4 gap-y-3 md:grid-cols-4 md:gap-x-6">
                  <DetailField label={DETAIL_FIELD_LABELS.market}>{marketLabel(position.market)}</DetailField>
                  <DetailField label={DETAIL_FIELD_LABELS.instrumentType}>
                    {instrumentTypeLabel(position.instrument_type)}
                  </DetailField>
                  <DetailField label={DETAIL_FIELD_LABELS.quantity}>
                    {formatQuantity(position.quantity)}
                  </DetailField>
                  <DetailField label={DETAIL_FIELD_LABELS.avgCost}>
                    {formatMoney(position.avg_cost, position.currency, 2)}
                  </DetailField>
                  <DetailField label={DETAIL_FIELD_LABELS.openedAt}>{position.opened_at ?? "—"}</DetailField>
                  <DetailField label={DETAIL_FIELD_LABELS.pnlOriginal}>
                    <PnlOriginalCell pnlOriginal={position.valuation.pnl_original} />
                  </DetailField>
                  <DetailField label={DETAIL_FIELD_LABELS.assetContribution}>
                    <MoneyOrDash
                      value={position.valuation.asset_contribution_twd}
                      currency="TWD"
                      decimals={0}
                    />
                  </DetailField>
                  <DetailField label={DETAIL_FIELD_LABELS.fxContribution}>
                    <MoneyOrDash
                      value={position.valuation.fx_contribution_twd}
                      currency="TWD"
                      decimals={0}
                    />
                  </DetailField>
                </dl>
                <div className="mt-3 flex gap-2 md:justify-end">
                  <button
                    type="button"
                    onClick={() => onEdit(position)}
                    disabled={pendingDeleteId === position.id}
                    aria-label={`編輯 ${position.symbol} 持倉`}
                    className="min-h-11 flex-1 rounded-md border border-neutral-700 px-3 py-1 text-xs text-neutral-300 hover:bg-neutral-800 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-sky-400 active:bg-neutral-700 disabled:cursor-not-allowed disabled:opacity-50 md:min-h-8 md:flex-none"
                  >
                    編輯
                  </button>
                  <button
                    type="button"
                    onClick={() => onDelete(position)}
                    disabled={deleteState.disabled}
                    aria-label={`刪除 ${position.symbol} 持倉`}
                    className="min-h-11 flex-1 rounded-md border border-red-900 px-3 py-1 text-xs text-red-300 hover:bg-red-950/40 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-sky-400 active:bg-red-950/60 disabled:cursor-not-allowed disabled:opacity-50 md:min-h-8 md:flex-none"
                  >
                    {deleteState.label}
                  </button>
                </div>
              </div>
            </div>
          </div>
        );
      })}
    </div>
    </div>
  );
}

export function PositionsTable({
  positions,
  changeMode,
}: {
  positions: SummaryPositionItem[];
  changeMode: ChangeMode;
}) {
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
      <PositionsTableView
        positions={positions}
        namesBySymbol={namesBySymbol}
        changeMode={changeMode}
        pendingDeleteId={pendingDeleteId}
        onEdit={setEditingPosition}
        onDelete={handleDelete}
      />

      {editingPosition && (
        <EditPositionModal position={editingPosition} onClose={() => setEditingPosition(null)} />
      )}
    </div>
  );
}

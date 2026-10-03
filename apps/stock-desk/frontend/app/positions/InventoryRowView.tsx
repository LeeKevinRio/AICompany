import Link from "next/link";
import type { KeyboardEvent, Ref } from "react";
import { ApiError } from "../lib/api";
import { ErrorPanel } from "../components/ErrorPanel";
import { formatMoney, formatQuantity, marketLabel } from "../lib/format";
import {
  INVENTORY_ACTIONS_COLUMN_LABEL,
  INVENTORY_COLUMN_LABELS,
  ROW_CANCEL_LABEL,
  ROW_EDIT_LABEL,
  ROW_MORE_LABEL,
  ROW_SAVE_LABEL,
  ROW_SAVING_LABEL,
  SAVE_FAILED_LABEL,
  avgCostInputAriaLabel,
  buildOriginalValueHint,
  editAriaLabel,
  moreAriaLabel,
  noteInputAriaLabel,
  quantityInputAriaLabel,
  removeAriaLabel,
} from "../lib/inventoryWording";
import {
  inlineKeyAction,
  originalValueHints,
  positionAnchorId,
  positionEditButtonId,
  positionFieldInputId,
  positionRemoveButtonId,
  positionSaveButtonId,
  routeSaveError,
} from "../lib/inventoryEdit";
import type { InlineDraft, InlineField } from "../lib/inventoryEdit";
import { deleteButtonState } from "../lib/positionFormSubmit";
import type { Position } from "../lib/types";

/**
 * Desktop (>= 1024px, `lg`) six-column grid; below that the same DOM reflows
 * into a card (visual spec 3.1 / 3.2). Shared by the header and every row.
 */
export const INVENTORY_ROW_GRID =
  "grid grid-cols-[minmax(0,1fr)_auto] gap-x-3 gap-y-3 lg:grid-cols-[minmax(150px,1.3fr)_minmax(90px,0.7fr)_minmax(110px,1fr)_minmax(130px,1fr)_minmax(140px,1.4fr)_208px] lg:items-center";

const FOCUS_RING =
  "focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-sky-400";

const BUTTON_SECONDARY = `min-h-11 rounded-md border border-neutral-700 px-4 py-1 text-sm text-neutral-300 hover:bg-neutral-800 active:bg-neutral-700 disabled:cursor-not-allowed disabled:opacity-50 ${FOCUS_RING}`;
const BUTTON_DANGER = `min-h-11 rounded-md border border-red-900 px-4 py-1 text-sm text-red-300 hover:bg-red-950/40 active:bg-red-950/60 disabled:cursor-not-allowed disabled:opacity-50 ${FOCUS_RING}`;
const BUTTON_PRIMARY = `min-h-11 rounded-md bg-neutral-100 px-4 py-1 text-sm font-medium text-neutral-900 hover:bg-white disabled:cursor-not-allowed disabled:opacity-50 ${FOCUS_RING}`;
const BUTTON_TEXT = `min-h-11 px-2 text-sm text-sky-400 underline hover:text-sky-300 disabled:cursor-not-allowed disabled:opacity-50 ${FOCUS_RING}`;

const INPUT_BASE = `min-h-11 w-full rounded-md border bg-neutral-900 px-3 py-2 text-base text-neutral-100 disabled:opacity-50 lg:text-sm ${FOCUS_RING}`;

/** Header row, desktop only; the actions column header is screen-reader-only. */
export function InventoryTableHeader() {
  return (
    <div role="rowgroup" className="hidden bg-neutral-900 text-neutral-400 lg:block">
      <div role="row" className={`${INVENTORY_ROW_GRID} px-3 py-2 text-sm font-medium`}>
        <span role="columnheader">{INVENTORY_COLUMN_LABELS.symbol}</span>
        <span role="columnheader">{INVENTORY_COLUMN_LABELS.market}</span>
        <span role="columnheader" className="text-right">
          {INVENTORY_COLUMN_LABELS.quantity}
        </span>
        <span role="columnheader" className="text-right">
          {INVENTORY_COLUMN_LABELS.avgCost}
        </span>
        <span role="columnheader">{INVENTORY_COLUMN_LABELS.note}</span>
        <span role="columnheader" className="sr-only">
          {INVENTORY_ACTIONS_COLUMN_LABEL}
        </span>
      </div>
    </div>
  );
}

function FieldSlot({
  id,
  error,
  hint,
}: {
  id: string;
  error: string | undefined;
  hint: string | undefined;
}) {
  // Reserved 16px slot so showing a message never moves the row.
  return (
    <p
      id={id}
      role={error ? "alert" : undefined}
      className={`mt-1 min-h-4 break-words text-xs ${error ? "text-red-400" : "text-neutral-400"}`}
    >
      {error ?? (hint === undefined ? null : buildOriginalValueHint(hint))}
    </p>
  );
}

export interface InventoryRowViewProps {
  position: Position;
  /** Company name from the directory; `undefined` on a miss (nothing is printed). */
  name: string | undefined;
  /** True for the row an `#pos-{id}` link pointed at. */
  highlighted: boolean;
  mode: "display" | "edit";
  draft: InlineDraft;
  onDraftChange: (field: InlineField, value: string) => void;
  /** The failed PATCH, if any; routed to the field slots or the row's error panel. */
  saveError: unknown;
  saving: boolean;
  /** Id of the row whose remove request is in flight, `null` when none. */
  pendingDeleteId: number | null;
  onEdit: () => void;
  onSave: () => void;
  onCancel: () => void;
  onMore: () => void;
  onRemove: () => void;
  editButtonRef?: Ref<HTMLButtonElement>;
  quantityInputRef?: Ref<HTMLInputElement>;
}

/**
 * One inventory row (presentational: no query client needed, so the markup is
 * unit-testable with `renderToStaticMarkup`). Only quantity / average cost /
 * note become inputs in edit mode; symbol, market and currency stay text.
 */
export function InventoryRowView({
  position,
  name,
  highlighted,
  mode,
  draft,
  onDraftChange,
  saveError,
  saving,
  pendingDeleteId,
  onEdit,
  onSave,
  onCancel,
  onMore,
  onRemove,
  editButtonRef,
  quantityInputRef,
}: InventoryRowViewProps) {
  const { id, symbol } = position;
  const editing = mode === "edit";
  const removeState = deleteButtonState(pendingDeleteId, id);
  const removing = pendingDeleteId === id;
  const routed = routeSaveError(saveError);
  const hints = editing ? originalValueHints(position, draft) : {};
  const market = marketLabel(position.market);
  const markedRow = editing || highlighted;

  function handleInputKeyDown(event: KeyboardEvent<HTMLInputElement>) {
    const action = inlineKeyAction({
      key: event.key,
      isComposing: event.nativeEvent.isComposing,
      keyCode: event.nativeEvent.keyCode,
    });
    if (action === "save") {
      event.preventDefault();
      onSave();
    } else if (action === "cancel") {
      event.preventDefault();
      onCancel();
    }
  }

  const inputBorder = (field: InlineField) =>
    routed.inline[field] ? "border-red-900" : "border-neutral-700";

  const actions =
    mode === "display" ? (
      <div
        role="cell"
        className="col-start-2 row-start-1 flex items-start justify-end gap-3 lg:col-start-6 lg:items-center"
      >
        <button
          type="button"
          id={positionEditButtonId(id)}
          ref={editButtonRef}
          onClick={onEdit}
          disabled={removing}
          aria-label={editAriaLabel(symbol)}
          className={BUTTON_SECONDARY}
        >
          {ROW_EDIT_LABEL}
        </button>
        <button
          type="button"
          id={positionRemoveButtonId(id)}
          onClick={onRemove}
          disabled={removeState.disabled}
          aria-label={removeAriaLabel(symbol)}
          className={BUTTON_DANGER}
        >
          {removeState.label}
        </button>
      </div>
    ) : (
      <div
        role="cell"
        className="col-span-2 flex items-center gap-3 lg:col-span-1 lg:col-start-6 lg:row-start-1 lg:justify-end lg:gap-2"
      >
        <button
          type="button"
          id={positionSaveButtonId(id)}
          onClick={onSave}
          disabled={saving}
          className={`${BUTTON_PRIMARY} flex-1 lg:flex-none lg:px-3`}
        >
          {saving ? ROW_SAVING_LABEL : ROW_SAVE_LABEL}
        </button>
        <button
          type="button"
          onClick={onCancel}
          disabled={saving}
          className={`${BUTTON_SECONDARY} flex-1 lg:flex-none lg:px-3`}
        >
          {ROW_CANCEL_LABEL}
        </button>
        <button
          type="button"
          onClick={onMore}
          disabled={saving}
          aria-label={moreAriaLabel(symbol)}
          className={BUTTON_TEXT}
        >
          {ROW_MORE_LABEL}
        </button>
      </div>
    );

  return (
    <div
      role="row"
      id={positionAnchorId(id)}
      tabIndex={-1}
      className={`${INVENTORY_ROW_GRID} scroll-mt-4 border-l-2 border-t border-neutral-800 px-3 py-3 first:border-t-0 target:border-l-neutral-100 target:bg-neutral-900/40 focus-visible:outline-2 focus-visible:-outline-offset-2 focus-visible:outline-sky-400 lg:py-2.5 ${
        markedRow ? "border-l-neutral-100 bg-neutral-900/40" : "border-l-transparent"
      } ${removing ? "opacity-60" : ""}`}
    >
      <div role="cell" className="min-w-0 lg:col-start-1 lg:row-start-1">
        <p className="flex flex-wrap items-baseline gap-x-2 font-medium">
          <Link
            href={`/position/${encodeURIComponent(symbol)}?market=${position.market}`}
            className={`inline-flex min-h-11 items-center text-sky-400 underline hover:text-sky-300 ${FOCUS_RING}`}
          >
            {symbol}
          </Link>
          <span className="text-xs font-normal text-neutral-400 lg:hidden">
            {market} · {position.currency}
          </span>
        </p>
        {name && <p className="truncate text-xs text-neutral-400">{name}</p>}
      </div>

      <div role="cell" className="hidden min-w-0 lg:col-start-2 lg:row-start-1 lg:block">
        <p className="text-sm text-neutral-300">{market}</p>
        <p className="text-xs text-neutral-400">{position.currency}</p>
      </div>

      {mode === "display" && actions}

      <div className="col-span-2 grid grid-cols-2 gap-x-3 lg:contents">
        <div role="cell" className="min-w-0 lg:col-start-3 lg:row-start-1 lg:text-right">
          {editing ? (
            <>
              <label
                htmlFor={positionFieldInputId(id, "quantity")}
                className="block text-xs text-neutral-400 lg:sr-only"
              >
                {INVENTORY_COLUMN_LABELS.quantity}
              </label>
              <input
                id={positionFieldInputId(id, "quantity")}
                ref={quantityInputRef}
                inputMode="decimal"
                autoComplete="off"
                aria-label={quantityInputAriaLabel(symbol)}
                aria-invalid={routed.inline.quantity ? true : undefined}
                aria-describedby={`pos-${id}-quantity-hint`}
                value={draft.quantity}
                disabled={saving}
                onChange={(e) => onDraftChange("quantity", e.target.value)}
                onKeyDown={handleInputKeyDown}
                className={`${INPUT_BASE} ${inputBorder("quantity")} lg:text-right`}
              />
              <FieldSlot
                id={`pos-${id}-quantity-hint`}
                error={routed.inline.quantity}
                hint={hints.quantity}
              />
            </>
          ) : (
            <>
              <p className="text-xs text-neutral-400 lg:hidden">{INVENTORY_COLUMN_LABELS.quantity}</p>
              <p className="text-sm tabular-nums text-neutral-100">{formatQuantity(position.quantity)}</p>
            </>
          )}
        </div>

        <div role="cell" className="min-w-0 lg:col-start-4 lg:row-start-1 lg:text-right">
          {editing ? (
            <>
              <label
                htmlFor={positionFieldInputId(id, "avg_cost")}
                className="block text-xs text-neutral-400 lg:sr-only"
              >
                {INVENTORY_COLUMN_LABELS.avgCost}
              </label>
              <input
                id={positionFieldInputId(id, "avg_cost")}
                inputMode="decimal"
                autoComplete="off"
                aria-label={avgCostInputAriaLabel(symbol)}
                aria-invalid={routed.inline.avg_cost ? true : undefined}
                aria-describedby={`pos-${id}-avg_cost-hint`}
                value={draft.avg_cost}
                disabled={saving}
                onChange={(e) => onDraftChange("avg_cost", e.target.value)}
                onKeyDown={handleInputKeyDown}
                className={`${INPUT_BASE} ${inputBorder("avg_cost")} lg:text-right`}
              />
              <FieldSlot
                id={`pos-${id}-avg_cost-hint`}
                error={routed.inline.avg_cost}
                hint={hints.avg_cost}
              />
            </>
          ) : (
            <>
              <p className="text-xs text-neutral-400 lg:hidden">{INVENTORY_COLUMN_LABELS.avgCost}</p>
              <p className="text-sm tabular-nums text-neutral-100">
                {formatMoney(position.avg_cost, position.currency, 2)}
              </p>
            </>
          )}
        </div>
      </div>

      <div role="cell" className="col-span-2 min-w-0 lg:col-span-1 lg:col-start-5 lg:row-start-1">
        {editing ? (
          <>
            <label htmlFor={positionFieldInputId(id, "note")} className="block text-xs text-neutral-400 lg:sr-only">
              {INVENTORY_COLUMN_LABELS.note}
            </label>
            <input
              id={positionFieldInputId(id, "note")}
              autoComplete="off"
              aria-label={noteInputAriaLabel(symbol)}
              aria-invalid={routed.inline.note ? true : undefined}
              aria-describedby={`pos-${id}-note-hint`}
              value={draft.note}
              disabled={saving}
              onChange={(e) => onDraftChange("note", e.target.value)}
              onKeyDown={handleInputKeyDown}
              className={`${INPUT_BASE} ${inputBorder("note")}`}
            />
            <FieldSlot id={`pos-${id}-note-hint`} error={routed.inline.note} hint={hints.note} />
          </>
        ) : (
          <div className="flex gap-2 lg:block">
            <span className="text-xs text-neutral-400 lg:hidden">{INVENTORY_COLUMN_LABELS.note}</span>
            {position.note !== null && position.note.trim() !== "" ? (
              <span className="min-w-0 break-words text-sm text-neutral-300 lg:line-clamp-2">
                {position.note}
              </span>
            ) : (
              <span className="text-sm text-neutral-400">—</span>
            )}
          </div>
        )}
      </div>

      {mode === "edit" && actions}

      {editing && (routed.residual.length > 0 || routed.showGeneric) && (
        <div
          role="cell"
          className="col-span-2 space-y-2 lg:col-span-6 lg:col-start-1 lg:row-start-2"
        >
          {routed.residual.map((message) => (
            <ErrorPanel
              key={message}
              label={SAVE_FAILED_LABEL}
              error={new ApiError(message, saveError instanceof ApiError ? saveError.status : 0)}
            />
          ))}
          {routed.showGeneric && <ErrorPanel label={SAVE_FAILED_LABEL} error={saveError} />}
        </div>
      )}
    </div>
  );
}

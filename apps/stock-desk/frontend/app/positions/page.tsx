"use client";

import { useEffect, useRef, useState } from "react";
import { ApiError } from "../lib/api";
import { EmptyPositionsState } from "../components/EmptyPositionsState";
import { ErrorPanel } from "../components/ErrorPanel";
import { formatQuantity } from "../lib/format";
import {
  focusTargetAfterRemoval,
  parsePositionAnchor,
  positionAnchorId,
  positionEditButtonId,
  positionRemoveButtonId,
} from "../lib/inventoryEdit";
import type { RemovalFocusTarget } from "../lib/inventoryEdit";
import {
  ADD_SECTION_TITLE,
  CSV_SECTION_TITLE,
  INVENTORY_ADD_BUTTON,
  INVENTORY_PAGE_TITLE,
  LIST_LOAD_FAILED_LABEL,
  LIST_RETRY_LABEL,
  REMOVED_ALREADY_GONE,
  REMOVE_FAILED_LABEL,
  buildAddedToast,
  buildRemoveConfirmSentence,
  buildRemovedToast,
} from "../lib/inventoryWording";
import { useDeletePosition, usePositions } from "../lib/queries";
import type { Position } from "../lib/types";
import { DisclosureSection } from "./DisclosureSection";
import { ImportCsvSection } from "./ImportCsvSection";
import { InventoryList, InventoryListSkeleton } from "./InventoryList";
import { ManualAddForm } from "./ManualAddForm";

const ADD_SECTION_ID = "inventory-add";
/** Element id of the symbol input inside `ManualAddForm`. */
const ADD_SYMBOL_INPUT_ID = "symbol";

const FOCUS_RING =
  "focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-sky-400";

function isNotFound(error: unknown): boolean {
  return error instanceof ApiError && error.status === 404;
}

/**
 * Inventory page (`/positions`): every position, inline edit of quantity /
 * average cost / note, remove, add, and CSV import. Data comes from
 * `GET /api/positions` only, so a failing quote or FX source never blocks it.
 */
export default function InventoryPage() {
  const positions = usePositions(true);
  const deleteMutation = useDeletePosition();
  // One shared mutation instance feeds every row's remove button, so the
  // in-flight id is tracked locally (see `deleteButtonState`).
  const [pendingDeleteId, setPendingDeleteId] = useState<number | null>(null);
  const [status, setStatus] = useState<{ text: string; tone: "success" | "neutral" } | null>(null);
  // `null` = follow the default: expanded only while the inventory is empty.
  const [addOverride, setAddOverride] = useState<boolean | null>(null);
  const [csvOpen, setCsvOpen] = useState(false);
  const [highlightedId, setHighlightedId] = useState<number | null>(null);

  const headingRef = useRef<HTMLHeadingElement | null>(null);
  const addFocusRequested = useRef(false);
  const handledHash = useRef<string | null>(null);
  const pendingRemoveFailureFocus = useRef<number | null>(null);
  const pendingRemovalFocus = useRef<{ removedId: number; target: RemovalFocusTarget } | null>(null);

  const items = positions.data?.items;
  const addOpen = addOverride ?? (items !== undefined && items.length === 0);

  // Header "add": expand, scroll to the section and focus the symbol input.
  useEffect(() => {
    if (!addFocusRequested.current || !addOpen) return;
    addFocusRequested.current = false;
    document.getElementById(ADD_SECTION_ID)?.scrollIntoView({ block: "start", behavior: "auto" });
    document.getElementById(ADD_SYMBOL_INPUT_ID)?.focus({ preventScroll: true });
  });

  // `/positions#pos-{id}` (home link): the target row only exists once the
  // list has loaded, so the hash is handled after that, once per hash value.
  useEffect(() => {
    if (items === undefined) return;
    function applyHash() {
      const hash = window.location.hash;
      if (handledHash.current === hash) return;
      const id = parsePositionAnchor(hash);
      if (id === null) return;
      const row = document.getElementById(positionAnchorId(id));
      if (!row) return;
      handledHash.current = hash;
      setHighlightedId(id);
      row.scrollIntoView({ block: "start", behavior: "auto" });
      row.focus({ preventScroll: true });
    }
    applyHash();
    window.addEventListener("hashchange", applyHash);
    return () => window.removeEventListener("hashchange", applyHash);
  }, [items]);

  // After a removal the list re-fetches; once the row is gone, move focus to
  // the next row's edit button (or the heading) so it never falls to `body`.
  useEffect(() => {
    const pending = pendingRemovalFocus.current;
    if (!pending || items === undefined) return;
    if (items.some((item) => item.id === pending.removedId)) return;
    pendingRemovalFocus.current = null;
    const target =
      pending.target.kind === "row"
        ? document.getElementById(positionEditButtonId(pending.target.id))
        : null;
    (target ?? headingRef.current)?.focus();
  }, [items]);

  useEffect(() => {
    const id = pendingRemoveFailureFocus.current;
    if (id === null || pendingDeleteId !== null) return;
    pendingRemoveFailureFocus.current = null;
    document.getElementById(positionRemoveButtonId(id))?.focus();
  }, [pendingDeleteId]);

  function handleAddButton() {
    addFocusRequested.current = true;
    setAddOverride(true);
  }

  function handleAdded(symbol: string) {
    setStatus({ text: buildAddedToast(symbol), tone: "success" });
    setAddOverride(true);
  }

  function handleRemove(position: Position) {
    // Blocks a re-click and a click on another row while a request is in flight.
    if (pendingDeleteId !== null) return;
    const confirmed = window.confirm(
      buildRemoveConfirmSentence(position.symbol, formatQuantity(position.quantity)),
    );
    if (!confirmed) return;
    const ids = (items ?? []).map((item) => item.id);
    setPendingDeleteId(position.id);
    deleteMutation.mutate(position.id, {
      onSuccess: () => {
        setStatus({ text: buildRemovedToast(position.symbol), tone: "success" });
        pendingRemovalFocus.current = {
          removedId: position.id,
          target: focusTargetAfterRemoval(ids, position.id),
        };
      },
      onError: (error) => {
        if (isNotFound(error)) {
          // Already removed elsewhere: the list is re-fetched by the hook.
          setStatus({ text: REMOVED_ALREADY_GONE, tone: "neutral" });
          pendingRemovalFocus.current = {
            removedId: position.id,
            target: focusTargetAfterRemoval(ids, position.id),
          };
        } else {
          setStatus(null);
          // Every remove button was disabled while the request ran, so focus
          // fell to `body`; it returns to this row's button once re-enabled.
          pendingRemoveFailureFocus.current = position.id;
        }
      },
      onSettled: () => setPendingDeleteId(null),
    });
  }

  const removeError = deleteMutation.isError && !isNotFound(deleteMutation.error);

  return (
    <main className="mx-auto max-w-5xl px-4 py-8">
      <div className="flex items-center justify-between gap-3">
        <h1
          ref={headingRef}
          tabIndex={-1}
          className={`text-2xl font-bold text-neutral-100 ${FOCUS_RING}`}
        >
          {INVENTORY_PAGE_TITLE}
        </h1>
        <button
          type="button"
          onClick={handleAddButton}
          className={`min-h-11 rounded-md bg-neutral-100 px-4 text-sm font-medium text-neutral-900 hover:bg-white ${FOCUS_RING}`}
        >
          {INVENTORY_ADD_BUTTON}
        </button>
      </div>

      {/* Live region exists before any message so a screen reader announces it; empty = no height. */}
      <div role="status">
        {status !== null && (
          <p
            className={`mt-4 rounded-md border px-3 py-2 text-sm ${
              status.tone === "success"
                ? "border-emerald-900 bg-emerald-950/40 text-emerald-300"
                : "border-neutral-800 bg-neutral-900/40 text-neutral-300"
            }`}
          >
            {status.text}
          </p>
        )}
      </div>

      {removeError && (
        <div className="mt-4">
          <ErrorPanel label={REMOVE_FAILED_LABEL} error={deleteMutation.error} />
        </div>
      )}

      <div className="mt-4">
        {items !== undefined ? (
          items.length === 0 ? (
            <EmptyPositionsState withAddLink={false} />
          ) : (
            <InventoryList
              positions={items}
              highlightedId={highlightedId}
              pendingDeleteId={pendingDeleteId}
              onRemove={handleRemove}
            />
          )
        ) : positions.isError ? (
          <div className="space-y-3">
            <ErrorPanel label={LIST_LOAD_FAILED_LABEL} error={positions.error} />
            <button
              type="button"
              onClick={() => {
                void positions.refetch();
              }}
              className={`min-h-11 rounded-md border border-neutral-700 px-4 py-1 text-sm text-neutral-300 hover:bg-neutral-800 active:bg-neutral-700 ${FOCUS_RING}`}
            >
              {LIST_RETRY_LABEL}
            </button>
          </div>
        ) : (
          <InventoryListSkeleton />
        )}
      </div>

      <div className="mt-8 space-y-4">
        <DisclosureSection
          id={ADD_SECTION_ID}
          title={ADD_SECTION_TITLE}
          open={addOpen}
          onToggle={() => setAddOverride(!addOpen)}
        >
          <ManualAddForm onSuccess={handleAdded} />
        </DisclosureSection>
        <DisclosureSection
          id="inventory-csv"
          title={CSV_SECTION_TITLE}
          open={csvOpen}
          onToggle={() => setCsvOpen((open) => !open)}
        >
          <ImportCsvSection />
        </DisclosureSection>
      </div>
    </main>
  );
}

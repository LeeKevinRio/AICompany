"use client";

import { useEffect, useRef, useState } from "react";
import { EditPositionModal } from "../components/EditPositionModal";
import {
  buildPositionPatch,
  draftFromPosition,
  isEmptyPatch,
  positionFieldInputId,
  positionSaveButtonId,
  saveErrorFocusTarget,
} from "../lib/inventoryEdit";
import type { InlineDraft, InlineField } from "../lib/inventoryEdit";
import { shouldBlockPositionSubmit } from "../lib/positionFormSubmit";
import { usePatchPosition } from "../lib/queries";
import type { Position } from "../lib/types";
import { InventoryRowView } from "./InventoryRowView";

/**
 * Stateful inventory row. Owns this row's edit mode, draft and its own PATCH
 * mutation instance, so rows edit independently of each other (one row saving
 * or failing never touches another's inputs).
 *
 * Inline saves go through `PATCH /api/positions/{id}` only, with just the
 * changed subset of `{quantity, avg_cost, note}`; the full-object PUT stays
 * behind the "more" modal. A failed save never leaves edit mode.
 */
export function InventoryRow({
  position,
  name,
  highlighted,
  pendingDeleteId,
  onRemove,
}: {
  position: Position;
  name: string | undefined;
  highlighted: boolean;
  pendingDeleteId: number | null;
  onRemove: (position: Position) => void;
}) {
  const [mode, setMode] = useState<"display" | "edit">("display");
  const [draft, setDraft] = useState<InlineDraft>(() => draftFromPosition(position));
  const [moreOpen, setMoreOpen] = useState(false);
  const patch = usePatchPosition();
  const editButtonRef = useRef<HTMLButtonElement | null>(null);
  const quantityInputRef = useRef<HTMLInputElement | null>(null);
  // Focus is restored after the commit that renders the target element.
  const pendingFocus = useRef<"quantity" | "edit" | null>(null);

  useEffect(() => {
    if (pendingFocus.current === "quantity" && mode === "edit") {
      pendingFocus.current = null;
      quantityInputRef.current?.focus();
      quantityInputRef.current?.select();
    } else if (pendingFocus.current === "edit" && mode === "display" && !moreOpen) {
      pendingFocus.current = null;
      editButtonRef.current?.focus();
    }
  });

  // A failed save leaves edit mode on screen, but the inputs and buttons were
  // disabled while saving so focus fell to `body`. Once the failed state has
  // committed (controls enabled again), move focus to the first field with an
  // error, or to the save button when no field is to blame.
  useEffect(() => {
    if (patch.status !== "error" || mode !== "edit") return;
    const target = saveErrorFocusTarget(patch.error);
    const id =
      target === "save" ? positionSaveButtonId(position.id) : positionFieldInputId(position.id, target);
    document.getElementById(id)?.focus();
  }, [patch.status, patch.error, mode, position.id]);

  function handleEdit() {
    patch.reset();
    setDraft(draftFromPosition(position));
    pendingFocus.current = "quantity";
    setMode("edit");
  }

  function leaveEditMode() {
    patch.reset();
    pendingFocus.current = "edit";
    setMode("display");
  }

  function handleCancel() {
    if (patch.isPending) return;
    leaveEditMode();
  }

  function handleSave() {
    // Enter reaches this handler even while a save is in flight (the inputs
    // are disabled, but keep the guard at the handler like the other forms).
    if (shouldBlockPositionSubmit(patch.isPending)) return;
    const input = buildPositionPatch(position, draft);
    // Nothing changed: no request, straight back to display mode.
    if (isEmptyPatch(input)) {
      leaveEditMode();
      return;
    }
    patch.mutate(
      { id: position.id, input },
      {
        onSuccess: () => {
          pendingFocus.current = "edit";
          setMode("display");
        },
      },
    );
  }

  function handleMore() {
    if (patch.isPending) return;
    leaveEditMode();
    setMoreOpen(true);
  }

  function handleModalClose() {
    pendingFocus.current = "edit";
    setMoreOpen(false);
  }

  function handleDraftChange(field: InlineField, value: string) {
    setDraft((prev) => ({ ...prev, [field]: value }));
  }

  return (
    <>
      <InventoryRowView
        position={position}
        name={name}
        highlighted={highlighted}
        mode={mode}
        draft={draft}
        onDraftChange={handleDraftChange}
        saveError={patch.isError ? patch.error : null}
        saving={patch.isPending}
        pendingDeleteId={pendingDeleteId}
        onEdit={handleEdit}
        onSave={handleSave}
        onCancel={handleCancel}
        onMore={handleMore}
        onRemove={() => onRemove(position)}
        editButtonRef={editButtonRef}
        quantityInputRef={quantityInputRef}
      />
      {moreOpen && <EditPositionModal position={position} onClose={handleModalClose} />}
    </>
  );
}

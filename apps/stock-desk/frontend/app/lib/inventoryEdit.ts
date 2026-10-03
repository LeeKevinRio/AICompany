/**
 * Pure logic behind the inventory page's inline edit (no React, no network):
 * the PATCH body subset, error routing, keyboard handling, and the anchor /
 * focus helpers. Kept separate so the rules can be unit-tested under plain
 * Node.
 */

import { ApiError } from "./api";
import { formatMoney, formatQuantity } from "./format";
import type { Currency, PositionPatchInput } from "./types";

export type InlineField = "quantity" | "avg_cost" | "note";

export const INLINE_FIELDS: readonly InlineField[] = ["quantity", "avg_cost", "note"];

export interface InlineDraft {
  quantity: string;
  avg_cost: string;
  note: string;
}

/** The slice of a stored position the inline editor reads. */
export interface InlineEditable {
  quantity: string;
  avg_cost: string;
  currency: Currency;
  note: string | null;
}

export function draftFromPosition(position: InlineEditable): InlineDraft {
  return {
    quantity: position.quantity,
    avg_cost: position.avg_cost,
    note: position.note ?? "",
  };
}

const PLAIN_DECIMAL = /^[+-]?\d+(\.\d+)?$/;

/**
 * Canonical form for comparing two decimal strings ("1000" equals "1000.00",
 * "+5" equals "5"). Anything that is not a plain decimal is compared as its
 * trimmed text, so the backend gets to reject it with its own message.
 */
export function normalizeDecimalString(value: string): string {
  const text = value.trim();
  if (!PLAIN_DECIMAL.test(text)) return text;
  const negative = text.startsWith("-");
  const unsigned = text.replace(/^[+-]/, "");
  const [intPart = "", fracPart = ""] = unsigned.split(".");
  const intNormalized = intPart.replace(/^0+(?=\d)/, "");
  const fracNormalized = fracPart.replace(/0+$/, "");
  const body = fracNormalized === "" ? intNormalized : `${intNormalized}.${fracNormalized}`;
  return negative && body !== "0" ? `-${body}` : body;
}

function decimalChanged(original: string, draft: string): boolean {
  return normalizeDecimalString(original) !== normalizeDecimalString(draft);
}

function noteChanged(original: string | null, draft: string): boolean {
  return draft.trim() !== (original ?? "").trim();
}

/** Which of the three editable fields differ from the stored position. */
export function changedFields(position: InlineEditable, draft: InlineDraft): InlineField[] {
  const changed: InlineField[] = [];
  if (decimalChanged(position.quantity, draft.quantity)) changed.push("quantity");
  if (decimalChanged(position.avg_cost, draft.avg_cost)) changed.push("avg_cost");
  if (noteChanged(position.note, draft.note)) changed.push("note");
  return changed;
}

/**
 * Body for `PATCH /api/positions/{id}`: only the changed keys, and only from
 * `{quantity, avg_cost, note}`. Decimals are sent as the user's trimmed text
 * (never parsed to a float); an emptied note is sent as `null`. No client-side
 * validation: an empty or non-positive value goes through and the backend's
 * own message comes back.
 */
export function buildPositionPatch(position: InlineEditable, draft: InlineDraft): PositionPatchInput {
  const patch: PositionPatchInput = {};
  for (const field of changedFields(position, draft)) {
    if (field === "note") {
      const trimmed = draft.note.trim();
      patch.note = trimmed === "" ? null : trimmed;
    } else {
      patch[field] = draft[field].trim();
    }
  }
  return patch;
}

export function isEmptyPatch(patch: PositionPatchInput): boolean {
  return Object.keys(patch).length === 0;
}

/**
 * V3 (optional hint): the original value of each changed field, formatted
 * exactly like the display mode of that field, and nothing else (no delta,
 * ratio, percentage or arrow).
 */
export function originalValueHints(
  position: InlineEditable,
  draft: InlineDraft,
): Partial<Record<InlineField, string>> {
  const hints: Partial<Record<InlineField, string>> = {};
  for (const field of changedFields(position, draft)) {
    if (field === "quantity") hints.quantity = formatQuantity(position.quantity);
    else if (field === "avg_cost") hints.avg_cost = formatMoney(position.avg_cost, position.currency, 2);
    else hints.note = position.note !== null && position.note.trim() !== "" ? position.note : "—";
  }
  return hints;
}

export interface RoutedSaveError {
  /** Backend messages for fields that have an input in the row. */
  inline: Partial<Record<InlineField, string>>;
  /** Backend messages for fields with no input in the row (body, currency, symbol...). */
  residual: string[];
  /** True when there is an error but no field-level detail: show the error itself. */
  showGeneric: boolean;
}

/**
 * Routes a failed PATCH to where it can be shown. Nothing is swallowed: a
 * field error with an input goes under that input, any other field error goes
 * to the row's error panel, and an error without field detail (404, 5xx,
 * network) is shown as a whole.
 */
export function routeSaveError(error: unknown): RoutedSaveError {
  const result: RoutedSaveError = { inline: {}, residual: [], showGeneric: false };
  if (error === null || error === undefined) return result;
  if (!(error instanceof ApiError)) {
    result.showGeneric = true;
    return result;
  }
  const entries = Object.entries(error.fieldErrors);
  if (entries.length === 0) {
    result.showGeneric = true;
    return result;
  }
  for (const [field, message] of entries) {
    if ((INLINE_FIELDS as readonly string[]).includes(field)) {
      result.inline[field as InlineField] = message;
    } else {
      result.residual.push(message);
    }
  }
  return result;
}

export type InlineKeyAction = "save" | "cancel" | null;

/**
 * Enter saves, Escape cancels. A key pressed while an IME is composing
 * (zhuyin / cangjie candidate selection) never counts: `isComposing` is the
 * standard flag, `keyCode === 229` covers engines that report the committing
 * keydown after composition has already ended.
 */
export function inlineKeyAction(event: {
  key: string;
  isComposing: boolean;
  keyCode?: number;
}): InlineKeyAction {
  if (event.isComposing || event.keyCode === 229) return null;
  if (event.key === "Enter") return "save";
  if (event.key === "Escape") return "cancel";
  return null;
}

/** Row element id, also the `/positions#pos-{id}` anchor. */
export function positionAnchorId(id: number): string {
  return `pos-${id}`;
}

export function positionRemoveButtonId(id: number): string {
  return `pos-remove-${id}`;
}

export function positionSaveButtonId(id: number): string {
  return `pos-save-${id}`;
}

export function positionFieldInputId(id: number, field: InlineField): string {
  return `pos-${id}-${field}`;
}

/**
 * Where focus goes after a failed inline save (the inputs were disabled while
 * saving, so focus has fallen to `body`): the first field with an error, in
 * visual order, else the 儲存 button.
 */
export function saveErrorFocusTarget(error: unknown): InlineField | "save" {
  const routed = routeSaveError(error);
  for (const field of INLINE_FIELDS) {
    if (routed.inline[field] !== undefined) return field;
  }
  return "save";
}

export function positionEditButtonId(id: number): string {
  return `pos-edit-${id}`;
}

/** `#pos-12` -> 12; anything else (including `#pos-1x`, `#pos-0`) -> null. */
export function parsePositionAnchor(hash: string): number | null {
  const match = /^#pos-(\d+)$/.exec(hash);
  if (!match) return null;
  const id = Number(match[1]);
  return Number.isSafeInteger(id) && id > 0 ? id : null;
}

export type RemovalFocusTarget = { kind: "row"; id: number } | { kind: "heading" };

/**
 * Where keyboard focus goes after a row is removed: the next row's 修改
 * button, else the previous row's, else (list now empty) the page heading.
 * Focus must never fall back to `body`.
 */
export function focusTargetAfterRemoval(
  ids: readonly number[],
  removedId: number,
): RemovalFocusTarget {
  const index = ids.indexOf(removedId);
  const remaining = ids.filter((id) => id !== removedId);
  const next = remaining[index === -1 ? 0 : Math.min(index, remaining.length - 1)];
  return next === undefined ? { kind: "heading" } : { kind: "row", id: next };
}

/**
 * Backend messages for field errors that have no input in a form (for example
 * the model-level `body` error of a market / currency mismatch). Forms render
 * these in an error panel so a refusal is never silent.
 */
export function unmappedFieldMessages(
  error: unknown,
  knownFields: readonly string[],
): string[] {
  if (!(error instanceof ApiError)) return [];
  return Object.entries(error.fieldErrors)
    .filter(([field]) => !knownFields.includes(field))
    .map(([, message]) => message);
}

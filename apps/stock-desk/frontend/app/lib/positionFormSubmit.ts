/**
 * Pure guard/state-derivation functions behind the pending-state fix for the
 * four持倉 submit surfaces (EditPositionModal 儲存, ManualAddForm 新增,
 * ImportCsvSection 匯入, PositionsTable 刪除 — CEO 實測 2026-08-16:「編輯現有
 * 庫存時按下儲存不會馬上更新且畫面沒有 loading」).
 *
 * Every one of the four already rendered a "動作中…" label from
 * `mutation.isPending` and disabled its button on it — that half worked.
 * What was missing on three of the four (edit/add/import share a single
 * `<form onSubmit>`) is a *handler-level* guard: pressing Enter in a text
 * field inside the form falls through to `<form onSubmit>` regardless of
 * whether the submit `<button>` itself carries `disabled` (browsers only
 * skip a form's *implicit* Enter-submission when the form has no submit
 * button at all — a disabled one still lets the keypress reach `onSubmit`
 * in some engines; `SymbolCombobox.tsx`'s own `handleKeyDown` doc comment
 * already documents an adjacent instance of the same fallthrough for plain
 * text). `shouldBlockPositionSubmit` is that guard, called as the first line
 * of every `handleSubmit` so a second mutate() can never fire while the
 * first is still in flight, regardless of which input path triggered it.
 *
 * The delete action is different in shape: `PositionsTable` shares one
 * `useDeletePosition()` mutation *instance* across every row (a single hook
 * call feeding many buttons), so keying a row's pending indicator off
 * `mutation.variables` (the id of whichever delete request is most recently
 * in flight) breaks the moment a second row's delete is confirmed before the
 * first finishes: the shared instance's `variables` moves to the new id and
 * the first row's button silently stops looking disabled while its request
 * is still outstanding — a second click there fires a *second* DELETE for
 * the same id. `deleteButtonState` derives every row's button from a
 * locally-tracked `pendingDeleteId` instead (owned by `PositionsTable`) and
 * disables *every* row's button while any delete is in flight, so two
 * deletes can never race on the one shared mutation instance.
 */

export interface SubmitButtonState {
  disabled: boolean;
  label: string;
}

/**
 * Whether a submit reaching a handler (via button click or a native
 * Enter-key implicit form submission) should be allowed to actually call
 * `mutation.mutate(...)`. `true` means "block it" — callers `return` early.
 */
export function shouldBlockPositionSubmit(pending: boolean): boolean {
  return pending;
}

/**
 * `disabled` + label for a single-instance submit button (儲存 / 新增 /
 * 匯入), all of which follow the same "動作中…" convention established by
 * `RuleSetConfirmPanel`'s 送出中…. `idleLabel`/`pendingLabel` are each
 * caller's own existing verbatim button text — this function only decides
 * which one is showing and whether the button is disabled, not the words
 * themselves.
 */
export function submitButtonState(
  pending: boolean,
  idleLabel: string,
  pendingLabel: string,
): SubmitButtonState {
  return { disabled: pending, label: pending ? pendingLabel : idleLabel };
}

/**
 * Per-row 刪除 button state derived from a locally-tracked in-flight id
 * (see module doc comment for why this cannot simply read
 * `deleteMutation.variables` off the shared mutation instance). Every row is
 * disabled while any delete is pending; only the row actually being deleted
 * shows the "刪除中…" label.
 */
export function deleteButtonState(pendingDeleteId: number | null, rowId: number): SubmitButtonState {
  return {
    disabled: pendingDeleteId !== null,
    label: pendingDeleteId === rowId ? "刪除中…" : "刪除",
  };
}

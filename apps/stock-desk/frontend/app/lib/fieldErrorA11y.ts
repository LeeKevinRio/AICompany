/**
 * Accessibility wiring for a form field's inline error line. The error `<p>`
 * is only rendered while there is a message, so the input only points at it
 * (`aria-describedby`) and is only marked invalid under the same condition;
 * the `<p>` itself carries `role="alert"` so the message is announced when it
 * appears. Same contract as the inline 422 slots of the inventory rows.
 */

/** Id of the error line that belongs to the input with id `fieldId`. */
export function fieldErrorId(fieldId: string): string {
  return `${fieldId}-error`;
}

export interface FieldErrorAria {
  "aria-invalid"?: true;
  "aria-describedby"?: string;
}

/** Spread onto the input / select: empty while the field has no error. */
export function fieldErrorAria(fieldId: string, message: string | undefined): FieldErrorAria {
  if (!message) return {};
  return { "aria-invalid": true, "aria-describedby": fieldErrorId(fieldId) };
}

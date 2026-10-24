/**
 * Two ways a form submit used to fail without telling anyone:
 *
 * 1. `Number("")` is `0`, so a cleared numeric field was sent as a real zero
 *    and accepted (a broker fee of 0, a cooldown of 0). Every required numeric
 *    field goes through {@link parseRequiredNumbers} before anything is sent.
 * 2. A 422 whose `loc` names a key the form has no slot for (a model-level
 *    check lands on `body`, a nested field on its own name) produced no visible
 *    message at all, because the generic error is hidden whenever field errors
 *    exist. {@link unplacedFieldErrors} returns exactly those messages so the
 *    generic error can show them.
 */

import { parseRequiredNumber } from "./alertRuleForm";

export const REQUIRED_NUMBER_MESSAGE = "請輸入數字，空白不會當成 0。";

export interface ParsedNumbers<K extends string> {
  /** Every key parsed; only meaningful when `errors` is empty. */
  values: Record<K, number>;
  /** Keys whose raw value was blank or not a finite number. */
  errors: Partial<Record<K, string>>;
}

export function parseRequiredNumbers<K extends string>(raw: Record<K, string>): ParsedNumbers<K> {
  const values = {} as Record<K, number>;
  const errors: Partial<Record<K, string>> = {};
  for (const key of Object.keys(raw) as K[]) {
    const parsed = parseRequiredNumber(raw[key]);
    if (parsed === null) {
      errors[key] = REQUIRED_NUMBER_MESSAGE;
    } else {
      values[key] = parsed;
    }
  }
  return { values, errors };
}

/** Pydantic's prefix on a `ValueError` raised by a validator; not for the reader. */
const PYDANTIC_VALUE_ERROR_PREFIX = "Value error, ";

/** The 422 messages whose key no field in the form renders. */
export function unplacedFieldErrors(
  fieldErrors: Record<string, string>,
  placed: readonly string[],
): string[] {
  return Object.entries(fieldErrors)
    .filter(([key]) => !placed.includes(key))
    .map(([, message]) =>
      message.startsWith(PYDANTIC_VALUE_ERROR_PREFIX)
        ? message.slice(PYDANTIC_VALUE_ERROR_PREFIX.length)
        : message,
    );
}

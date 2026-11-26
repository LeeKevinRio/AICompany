/**
 * Pure label module for `AlertEvent.observed` (RC-732 ~ RC-735, risk-approved wording 2026-11-25).
 *
 * Contract (RC-735):
 * - Key labels come from a dedicated 11-entry table, looked up with `Map.get` so that prototype
 *   names such as `constructor` can never resolve to something inherited.
 * - Values are converted only for the keys `op`, `field` and `violated_limit_ids`. Everything
 *   else (numbers, dates, currency codes) is printed as-is; null is printed as "—".
 * - Unknown keys or unknown values fall back to the raw string. Nothing is ever dropped.
 * - `close` deliberately does NOT go through `signalFieldLabel` (RC-734): that would show
 *   "最新收盤價" and bring back the "latest price" misreading on events that sit for days.
 *
 * INVALIDATION CONDITION (RC-733, required): the two date labels say "日線收盤，非即時"
 * (daily close, not real-time). That claim is the same one made by `ALERT_DISCLAIMER_LINE` in
 * `backend/app/alerts/notify.py`. If alerts ever start reading intraday or non-daily data, or if
 * the backend makes `bar_as_of` and `signals_as_of` come from different sources (today both are
 * `snapshot.as_of`), these labels become wrong: rewrite them in the SAME PR as that change and
 * send them to risk-compliance-officer for a verbatim review.
 */
import { COMPARISON_OP_OPTIONS, LIMIT_SELECTOR_OPTIONS, signalFieldLabel } from "./format";

/** The approved date label, verbatim the same as the parenthesis in `priceDateTooltip` (RC-733). */
const AS_OF_LABEL = "資料日期（日線收盤，非即時）";

/** RC-732 verbatim key labels: exactly 11 entries, one per backend `observed` key. */
export const OBSERVED_KEY_LABELS: ReadonlyMap<string, string> = new Map([
  ["close", "資料日收盤價"],
  ["threshold", "設定的門檻"],
  ["currency", "幣別"],
  ["bar_as_of", AS_OF_LABEL],
  ["field", "判斷欄位"],
  ["value", "該欄位數值"],
  ["op", "比較方式"],
  ["compared_to", "比較對象數值"],
  ["signals_as_of", AS_OF_LABEL],
  ["violated_limit_ids", "觸發的上限"],
  ["violated_count", "觸發的上限數量"],
]);

/** Separator the backend uses to join `violated_limit_ids` (and the one we join back with). */
const LIMIT_ID_SEPARATOR = "、";

function opValueLabel(value: string): string {
  return COMPARISON_OP_OPTIONS.find((opt) => opt.value === value)?.label ?? value;
}

function limitIdLabel(value: string): string {
  return LIMIT_SELECTOR_OPTIONS.find((opt) => opt.value === value)?.label ?? value;
}

export function observedKeyLabel(key: string): string {
  return OBSERVED_KEY_LABELS.get(key) ?? key;
}

/** Converts a value by its key; only three keys are converted (RC-735), the rest pass through. */
export function observedValueText(key: string, value: number | string | null): string {
  if (value === null || value === undefined) return "—";
  if (typeof value !== "string") return String(value);
  if (key === "op") return opValueLabel(value);
  // `signalFieldLabel` already falls back to the raw field key for unknown paths.
  if (key === "field") return signalFieldLabel(value);
  if (key === "violated_limit_ids") {
    return value.split(LIMIT_ID_SEPARATOR).map(limitIdLabel).join(LIMIT_ID_SEPARATOR);
  }
  return value;
}

/** One entry as shown on screen: "<key label>: <value text>". Separator ": " is unchanged. */
export function observedEntryText(key: string, value: number | string | null): string {
  return `${observedKeyLabel(key)}: ${observedValueText(key, value)}`;
}

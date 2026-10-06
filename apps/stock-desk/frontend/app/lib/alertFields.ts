import type { AlertRule } from "./types";

/**
 * Alert fields the alert pipeline can never evaluate (ADR-0021 K-9 / U-5).
 *
 * Mirrors backend KNOWN_FIELDS − ALERT_RULE_FIELDS
 * (backend/app/advice/context.py); pinned by backend test (T-5 reads this
 * file and compares the tuple in both directions). Do not edit one side
 * without the other.
 *
 * Two things hang off this single set and nothing else:
 *   1. the alert-field menu must not offer any of these (`SIGNAL_FIELD_OPTIONS`
 *      in `format.ts` is checked against it);
 *   2. whether a stored rule shows the W-3 "will not fire" notice is decided
 *      ONLY by membership in this set (risk-compliance binding U-5 (ii)) —
 *      never hard-code a single field such as beta at a call site.
 *
 * If the backend ever makes any of these evaluable, W-1 and W-3 below are
 * void and must go back through risk review (U-5 (iii)).
 */
export const UNEVALUABLE_ALERT_FIELDS = [
  "beta.value",
  "position.weight",
  "position.unrealized_pnl_pct",
] as const;

export type UnevaluableAlertField = (typeof UNEVALUABLE_ALERT_FIELDS)[number];

/**
 * Display labels for old rules that still name one of the fields above, so
 * `signalFieldLabel` never degrades to the raw key. Copied verbatim from the
 * backend `FIELD_LABELS` (backend/app/advice/context.py); the labels are not
 * in the field menu any more, hence this separate legacy table.
 */
export const UNEVALUABLE_ALERT_FIELD_LABELS: Record<UnevaluableAlertField, string> = {
  "beta.value": "相對指標的 beta",
  "position.weight": "此標的佔投資組合比重",
  "position.unrealized_pnl_pct": "此部位未實現損益率",
};

/** Type guard: true when `field` is one of the fields alerts can never evaluate. */
export function isUnevaluableAlertField(field: string | null | undefined): field is UnevaluableAlertField {
  return field != null && (UNEVALUABLE_ALERT_FIELDS as readonly string[]).includes(field);
}

/** Legacy label for an unevaluable field, or `undefined` for any other key. */
export function unevaluableAlertFieldLabel(field: string): string | undefined {
  return isUnevaluableAlertField(field) ? UNEVALUABLE_ALERT_FIELD_LABELS[field] : undefined;
}

/** True when a `signal_condition` names an unevaluable field on either side (`field` or `ref`). */
export function conditionUsesUnevaluableField(field: string, ref: string | null | undefined): boolean {
  return isUnevaluableAlertField(field) || isUnevaluableAlertField(ref);
}

/**
 * True when a stored rule is a `signal_condition` whose `field` or `ref` is in
 * `UNEVALUABLE_ALERT_FIELDS`. Reads the stored params defensively (the
 * document comes from the API); any other rule type is never flagged.
 */
export function ruleUsesUnevaluableField(rule: Pick<AlertRule, "type" | "params">): boolean {
  if (rule.type !== "signal_condition") return false;
  const params: unknown = rule.params;
  if (typeof params !== "object" || params === null || !("condition" in params)) return false;
  const condition: unknown = params.condition;
  if (typeof condition !== "object" || condition === null) return false;
  const field = "field" in condition && typeof condition.field === "string" ? condition.field : "";
  const ref = "ref" in condition && typeof condition.ref === "string" ? condition.ref : null;
  return conditionUsesUnevaluableField(field, ref);
}

/**
 * ADR-0021 W-1 (risk-approved verbatim, 2026-10-06): always-visible note under
 * the 訊號欄位 select. Do not reword; "Beta" has half-width spaces on both
 * sides only where the approved text does.
 */
export const ALERT_FIELD_BETA_NOTE = "警示不提供 Beta 作為條件，可在個股頁「風險量測」區查看。";

/**
 * ADR-0021 W-3 (risk-approved verbatim, 2026-10-06): marker shown next to a
 * stored rule whose field or ref is in `UNEVALUABLE_ALERT_FIELDS`.
 */
export const ALERT_RULE_UNEVALUABLE_NOTICE = "不會觸發（欄位不提供）";

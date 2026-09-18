/**
 * User-facing labels for `Valuation.missing` tokens (backend
 * `app/portfolio/valuation.py`). Two fixed shapes, on purpose: 「查無…」 means
 * the system asked and there was nothing; 「本次未查…」 means no source was
 * asked this time (a cache-only read, ADR-0010 D-1). Every token the backend
 * emits today is labelled here, and 「缺」 is gone: it mislabelled "not asked"
 * as "missing" (風控 2026-09-18 C-1). A token this map does not know is shown
 * as-is on purpose -- a visible failure that the label table lags the backend,
 * rather than a silently hidden cause. Wording by creative-lead
 * (`work/stock-desk-ADR-0010-揭露句-文案.md`), fixed by risk-compliance-officer
 * 2026-09-18 (C 核可).
 */
export const MISSING_LABELS: Record<string, string> = {
  price: "查無價格資料",
  price_not_queried: "本次未查價格",
  fx_now: "查無即期匯率",
  fx_open: "查無建倉匯率",
};

/** The label for one token; an unknown token is shown as-is rather than hidden. */
export function missingLabel(token: string): string {
  return MISSING_LABELS[token] ?? token;
}

/** The labels for a `missing` list, joined the way the positions table shows them. */
export function missingSummary(tokens: readonly string[]): string {
  return tokens.map(missingLabel).join("、");
}

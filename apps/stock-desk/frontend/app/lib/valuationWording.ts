/**
 * User-facing labels for `Valuation.missing` tokens (backend
 * `app/portfolio/valuation.py`). Three fixed shapes, on purpose: 「查無…」 means
 * the system asked and there was nothing; 「本次未查…」 means no source was
 * asked this time (a cache-only read, ADR-0010 D-1); the third is a noun
 * phrase (「幣別與市場不符」) that states the stored record itself is
 * inconsistent -- nothing was queried and it is not a data outage (風控
 * 2026-10-08 第二段裁定第 6 項). Every token the backend
 * emits today is labelled here, and 「缺」 is gone: it mislabelled "not asked"
 * as "missing" (風控 2026-09-18 C-1). A token this map does not know is shown
 * as-is on purpose -- a visible failure that the label table lags the backend,
 * rather than a silently hidden cause. Wording by creative-lead
 * (`work/stock-desk-ADR-0010-揭露句-文案.md`), fixed by risk-compliance-officer
 * 2026-09-18 (C 核可); third shape approved 2026-10-08
 * (`work/reviews/2026-10-08-X-3c-幣別與市場不符-揭露字面-風控審查.md`, 第二段).
 */
export const MISSING_LABELS: Record<string, string> = {
  price: "查無價格資料",
  price_not_queried: "本次未查價格",
  fx_now: "查無即期匯率",
  fx_open: "查無建倉匯率",
  // 風控核可文案,修改須重新送審(2026-10-08)
  // work/reviews/2026-10-08-X-3c-幣別與市場不符-揭露字面-風控審查.md (第二段, label (a), 7 字)
  currency_market_mismatch: "幣別與市場不符",
};

/**
 * Backend token for a legacy position whose stored currency does not match its
 * market (X-3c). When present, `Valuation.missing` is exactly this one token,
 * `status` is `insufficient_data` and `price` is null; the row must never be
 * labelled as a price-data outage (風控 2026-10-08 第二段 RX-3).
 */
export const CURRENCY_MARKET_MISMATCH_TOKEN = "currency_market_mismatch";

/**
 * True only when `missing` is exactly `[currency_market_mismatch]` (風控 2026-10-08
 * 顯示條件 (a); art-lead R-2). Any other shape, including a stray extra token,
 * is not a mismatch row here and keeps the ordinary unvalued path, so a broken
 * contract stays a visible failure instead of being swallowed.
 */
export function isCurrencyMarketMismatch(tokens: readonly string[]): boolean {
  return tokens.length === 1 && tokens[0] === CURRENCY_MARKET_MISMATCH_TOKEN;
}

/** The label for one token; an unknown token is shown as-is rather than hidden. */
export function missingLabel(token: string): string {
  return MISSING_LABELS[token] ?? token;
}

/** The labels for a `missing` list, joined the way the positions table shows them. */
export function missingSummary(tokens: readonly string[]): string {
  return tokens.map(missingLabel).join("、");
}

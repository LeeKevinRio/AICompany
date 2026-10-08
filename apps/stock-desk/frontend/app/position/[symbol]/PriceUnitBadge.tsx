import type { Bar } from "../../lib/types";
import { MARKET_CURRENCY } from "../../lib/currencyMarket";

/**
 * F-7 price-unit chip (risk-compliance-officer F7-R1..R10, art-lead opinion
 * `work/reviews/2026-10-08-F-7-幣別標示-美術意見.md`). The ONLY place on the stock
 * page that spells a currency in words; every price block renders this one
 * component, so wording and class live in exactly one file.
 *
 * Truth source (F7-R1/R2): the currency comes from the pinned `MARKET_CURRENCY`
 * table (never `format.ts` `marketCurrency`, which maps every non-TW market to
 * USD), and a bars-based block prints the chip only when EVERY bar's own
 * `currency` equals it. Unknown market, empty/absent bars or any mismatching bar
 * prints nothing and emits no substitute wording. Nothing here reads a position
 * currency, an FX quote or the portfolio context.
 */

/**
 * 風控核可文案,修改須重新送審(2026-10-08)
 * Approved wording, verbatim (full-width colon U+FF1A). Any change goes back to risk review.
 * Review records:
 *   work/reviews/2026-10-08-F-7-幣別標示字面逐字審-F7-R1～R8-風控.md (second edition, F7-R1..R10)
 *   work/reviews/2026-10-08-F-7-技術分析閘門偏離裁定-F7-R11至R14.md
 */
export const PRICE_UNIT_LABEL_USD = "價格單位：美元";
export const PRICE_UNIT_LABEL_TWD = "價格單位：新台幣";

const PRICE_UNIT_LABEL_BY_CURRENCY: Readonly<Record<string, string>> = {
  USD: PRICE_UNIT_LABEL_USD,
  TWD: PRICE_UNIT_LABEL_TWD,
};

/** The single copy of the chip class (art-lead 3.2). No hue, no fill, no opacity, no clipping. */
export const PRICE_UNIT_BADGE_CLASS =
  "whitespace-nowrap rounded border border-neutral-700 px-1.5 py-0.5 text-xs text-neutral-300";

/**
 * Marker for a block whose prices do not come from bars (the indicator values
 * printed from the signals payload): only the market check (F7-R1) applies.
 */
export const PRICE_UNIT_MARKET_ONLY = "market-only";

type PriceUnitBasis = readonly Bar[] | null | typeof PRICE_UNIT_MARKET_ONLY;

/** The approved label for a market, or null when the market is unknown (fail closed). */
function labelForMarket(market: string | undefined): { currency: string; label: string } | null {
  if (market === undefined || !Object.hasOwn(MARKET_CURRENCY, market)) return null;
  const currency = MARKET_CURRENCY[market];
  if (currency === undefined || !Object.hasOwn(PRICE_UNIT_LABEL_BY_CURRENCY, currency)) return null;
  const label = PRICE_UNIT_LABEL_BY_CURRENCY[currency];
  return label === undefined ? null : { currency, label };
}

/** Approved label, or null when the chip must not be printed. */
export function resolvePriceUnitLabel(market: string | undefined, basis: PriceUnitBasis): string | null {
  const hit = labelForMarket(market);
  if (hit === null) return null;
  if (basis === PRICE_UNIT_MARKET_ONLY) return hit.label;
  if (basis === null || basis.length === 0) return null;
  return basis.every((bar) => bar.currency === hit.currency) ? hit.label : null;
}

/**
 * Callers own the gate (the SAME condition that lets the block print its prices);
 * this component only adds the data check above. `block` wraps the chip in a
 * `flex` row for use as a stand-alone line (details body).
 */
export function PriceUnitBadge({
  market,
  bars,
  block = false,
}: {
  market?: string;
  bars: PriceUnitBasis;
  block?: boolean;
}) {
  const label = resolvePriceUnitLabel(market, bars);
  if (label === null) return null;
  const chip = <span className={PRICE_UNIT_BADGE_CLASS}>{label}</span>;
  return block ? <div className="flex">{chip}</div> : chip;
}

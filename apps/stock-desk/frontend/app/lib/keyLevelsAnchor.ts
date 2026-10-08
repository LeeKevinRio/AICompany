import type { AnchorSource } from "./keyLevels";
import { currencyMatchesMarket } from "./currencyMarket";
import type { Market, PositionsResponse } from "./types";

/**
 * 風控 R13/R14: the 關鍵價位 anchor cost comes straight from the stored
 * positions' native-currency `avg_cost` — never reconstructed by dividing
 * TWD book totals through `fx_to_twd` (that recovers P0×F0/F1, not the
 * average cost, and the backend's fx placeholder 1.0 is a contract value that
 * must never touch foreign amounts). Multiple lots of the same symbol are
 * combined as a quantity-weighted average in the lots' own (shared)
 * currency. Tri-state (風控 R10/R11): a confirmed cost, a CONFIRMED not-held
 * state, or "unknown" while the positions query is pending / a lot's cost is
 * unusable — the panel never claims 未持有 on "unknown". Shared by the panel
 * and the 頁尾揭露 builder so both see the same anchor.
 *
 * X-3c XC-N4 (風控 2026-10-08 第三段): if ANY lot's stored currency does not match
 * its market, the lot's `avg_cost` has no known unit (it may be off by ~31x), so
 * the anchor is "close-unknown" -- the same outcome as an unusable cost, with
 * no new wording. The rule is `currencyMatchesMarket` (shared with the backend).
 */
export function resolveKeyLevelsAnchor(
  positions: PositionsResponse | undefined,
  symbol: string,
  market: Market,
): { anchorSource: AnchorSource; avgCost: number | null } {
  if (!positions) return { anchorSource: "close-unknown", avgCost: null };
  const lots = positions.items.filter((p) => p.symbol === symbol && p.market === market);
  if (lots.length === 0) return { anchorSource: "close-not-held", avgCost: null };
  if (lots.some((lot) => !currencyMatchesMarket(lot.market, lot.currency))) {
    return { anchorSource: "close-unknown", avgCost: null };
  }
  let qtySum = 0;
  let costSum = 0;
  for (const lot of lots) {
    const qty = Number.parseFloat(lot.quantity);
    const cost = Number.parseFloat(lot.avg_cost);
    if (!Number.isFinite(qty) || qty <= 0 || !Number.isFinite(cost) || cost <= 0) {
      // Held, but a lot's cost is unusable — never claim 未持有.
      return { anchorSource: "close-unknown", avgCost: null };
    }
    qtySum += qty;
    costSum += cost * qty;
  }
  return { anchorSource: "cost", avgCost: costSum / qtySum };
}

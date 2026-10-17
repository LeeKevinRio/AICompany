import type { AnchorSource } from "./keyLevels";
import { currencyMatchesMarket } from "./currencyMarket";
import type { Market, PositionsResponse } from "./types";

/** The slice of a positions query result the anchor resolver needs (a `useQuery` result satisfies it). */
export interface PositionsAnchorInput {
  isSuccess: boolean;
  data: PositionsResponse | undefined;
}

/**
 * 風控 R13/R14: the 關鍵價位 anchor cost comes straight from the stored
 * positions' native-currency `avg_cost` — never reconstructed by dividing
 * TWD book totals through `fx_to_twd` (that recovers P0×F0/F1, not the
 * average cost, and the backend's fx placeholder 1.0 is a contract value that
 * must never touch foreign amounts). Multiple lots of the same symbol are
 * combined as a quantity-weighted average in the lots' own (shared)
 * currency. Tri-state plus (風控 R10/R11): a confirmed cost, a CONFIRMED not-held
 * state, "close-unknown" (CONFIRMED held, a lot's cost unusable) or
 * "holding-unknown" (positions query not in the `success` state: still loading, failed first
 * time, OR failed on a refetch while still carrying the last successful data) — the panel never claims
 * 未持有 on either unknown, and renders no held-only wording on "holding-unknown". A refetch that is
 * merely IN PROGRESS keeps `success` status and keeps using the last successfully fetched data (a known
 * limitation, 風控 B0 2b); only a non-success status is treated as undetermined. Shared by the panel
 * and the 頁尾揭露 builder so both see the same anchor.
 *
 * X-3c XC-N4 (風控 2026-10-08 第三段): if ANY lot's stored currency does not match
 * its market, the lot's `avg_cost` has no known unit (it may be off by ~31x), so
 * the anchor is "close-unknown" -- the same outcome as an unusable cost, with
 * no new wording. The rule is `currencyMatchesMarket` (shared with the backend).
 */
export function resolveKeyLevelsAnchor(
  positions: PositionsAnchorInput,
  symbol: string,
  market: Market,
): { anchorSource: AnchorSource; avgCost: number | null } {
  // Holding status itself undetermined: distinct from a CONFIRMED holding with an unusable
  // cost, so held-only wording can fail closed (風控 B0 required 1). Undetermined means the
  // query is not in `success` -- including `error` that still carries stale `data` from an
  // earlier success (風控 B0 R-1). The decision lives here, not at the call site, so it is unit-testable.
  const book = positions.isSuccess ? positions.data : undefined;
  if (!book) return { anchorSource: "holding-unknown", avgCost: null };
  const lots = book.items.filter((p) => p.symbol === symbol && p.market === market);
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

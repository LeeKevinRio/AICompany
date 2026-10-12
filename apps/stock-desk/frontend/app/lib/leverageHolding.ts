import type { Market, Position, PositionsResponse } from "./types";

/**
 * Whether `symbol` in `market` is a stored holding, as far as the leverage
 * endpoint is concerned.
 *
 * This deliberately mirrors the backend's `_pick_position`
 * (`app/api/leverage.py`): the symbol is compared after `strip().upper()` on
 * both sides, the market must be strictly equal, and nothing else is looked
 * at (no quantity, cost or currency filter). The endpoint answers 404 exactly
 * when this returns `false`, so the page can skip the request for non-holdings.
 *
 * Do NOT swap in the key-levels anchor resolver: it is case-sensitive and reports
 * "unknown" for a currency mismatch, which would hide the chapter from a
 * holder the backend would happily serve.
 */
export function hasLeverageHolding(
  items: readonly Pick<Position, "symbol" | "market">[],
  symbol: string,
  market: Market,
): boolean {
  const wanted = symbol.trim().toUpperCase();
  return items.some((p) => p.symbol.trim().toUpperCase() === wanted && p.market === market);
}

/** The slice of a positions query result the enabling rule needs. */
export interface PositionsQueryState {
  isError: boolean;
  isSuccess: boolean;
  data: PositionsResponse | undefined;
}

/**
 * Whether the leverage chapter query should run:
 * - positions pending: no (we do not know yet; avoids a speculative 404);
 * - positions failed: yes (fall back to asking the backend, which stays the
 *   source of truth; its quiet-404 handling on the page still applies);
 * - positions loaded: only when the symbol is held.
 */
export function isLeverageQueryEnabled(positions: PositionsQueryState, symbol: string, market: Market): boolean {
  if (positions.isError) return true;
  return positions.isSuccess && positions.data !== undefined && hasLeverageHolding(positions.data.items, symbol, market);
}

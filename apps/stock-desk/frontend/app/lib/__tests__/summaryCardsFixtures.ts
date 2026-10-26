import type { SummaryPositionItem } from "../types";

/**
 * Shared fixture for the `SummaryCards` tests: one held position that could
 * not be valued (no price). A `no_data` summary with this position is "the
 * book exists but nothing could be valued" (approved 無法估值 banner); the same
 * `no_data` summary with `positions: []` is the empty book (「尚無持倉」).
 */
export const UNVALUED_POSITION: SummaryPositionItem = {
  id: 1,
  symbol: "2330",
  market: "TW",
  quantity: "1000",
  avg_cost: "895.44",
  currency: "TWD",
  instrument_type: "stock",
  opened_at: null,
  sector: null,
  note: null,
  valuation: {
    status: "insufficient_data",
    missing: ["price"],
    price: null,
    fx: null,
    fx_open: null,
    pnl_original: null,
    pnl_twd: null,
    asset_contribution_twd: null,
    fx_contribution_twd: null,
  },
  market_value_twd: null,
  cost_twd: null,
  change: null,
};

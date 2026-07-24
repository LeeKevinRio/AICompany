/**
 * Domain types for the stock-desk frontend.
 *
 * All monetary and quantity fields are transmitted by the backend as
 * stringified `Decimal` values (per the API contract) to avoid floating
 * point precision loss in transit. We only convert them to `number` at
 * the point of display formatting, never for further arithmetic — any
 * aggregation (totals, contributions) is computed server-side and must
 * be rendered verbatim.
 *
 * Every shape below has been verified directly against the backend
 * source (not just the prose contract), to avoid the class of bug where
 * a self-consistent-but-wrong TS type passes `tsc` while the real API
 * response shape differs at runtime:
 *   - backend/app/positions/models.py       (PositionInput / Position)
 *   - backend/app/api/positions.py          (PositionListResponse)
 *   - backend/app/portfolio/valuation.py    (PriceInfo / PnlOriginal / Valuation)
 *   - backend/app/portfolio/summary.py      (Totals / SummaryPosition / PortfolioSummary)
 *   - backend/app/data/interface.py         (DataStatus)
 */

export interface HealthResponse {
  status: string;
  service?: string;
  as_of: string;
}

export type Market = "TW" | "US";
export type Currency = "TWD" | "USD";
export type InstrumentType = "stock" | "etf" | "leveraged_etf" | "futures_etf";

/**
 * Backend `PositionInput` — the POST/PUT request body (everything the user
 * supplies about a position, excluding id/timestamps). Also the shape a
 * validated CSV import row must satisfy.
 */
export interface PositionInput {
  symbol: string;
  market: Market;
  quantity: string;
  avg_cost: string;
  currency: Currency;
  opened_at: string; // date, e.g. "2026-07-24"
  instrument_type: InstrumentType;
  note: string | null;
}

/** Backend `Position` — a stored position: `PositionInput` + id + audit timestamps. */
export interface Position extends PositionInput {
  id: number;
  created_at: string;
  updated_at: string;
}

export interface PositionsResponse {
  items: Position[];
  as_of: string;
}

export type CreatePositionInput = PositionInput;
export type UpdatePositionInput = PositionInput;

/** Backend `DataStatus` (StrEnum) — the four-layer price degradation ladder. */
export type PriceDataStatus = "fresh" | "backup" | "cached_stale" | "unavailable";

/** Backend `PriceInfo`. */
export interface PositionPrice {
  value: string;
  as_of: string;
  source: string;
  data_status: PriceDataStatus;
}

/** Backend `PnlOriginal` — unrealized P&L in the position's own currency. */
export interface PnlOriginal {
  value: string;
  currency: Currency;
}

export type ValuationStatus = "ok" | "insufficient_data";

/**
 * Backend `Valuation` — nested under `SummaryPosition.valuation`. IMPORTANT:
 * `price`/`pnl_original`/`pnl_twd`/`asset_contribution_twd`/`fx_contribution_twd`
 * live here, NOT as sibling fields directly on the position (see
 * backend/app/portfolio/valuation.py::Valuation).
 */
export interface PositionValuation {
  status: ValuationStatus;
  missing: string[];
  price: PositionPrice | null;
  pnl_original: PnlOriginal | null;
  pnl_twd: string | null;
  asset_contribution_twd: string | null;
  fx_contribution_twd: string | null;
}

/**
 * Backend `SummaryPosition` — one position's identity fields plus its
 * nested `valuation`. Deliberately NOT `Position` + valuation, because the
 * backend does not echo back `created_at`/`updated_at` here.
 */
export interface SummaryPositionItem {
  id: number;
  symbol: string;
  market: Market;
  quantity: string;
  avg_cost: string;
  currency: Currency;
  instrument_type: InstrumentType;
  opened_at: string;
  note: string | null;
  valuation: PositionValuation;
}

export type SummaryStatus = "complete" | "partial" | "no_data";

/** Backend `Totals`. */
export interface PortfolioTotals {
  cost_twd: string;
  market_value_twd: string;
  unrealized_pnl_twd: string;
  asset_contribution_twd: string;
  fx_contribution_twd: string;
  status: SummaryStatus;
}

/** Backend `PortfolioSummary` — `as_of` is always present at the top level. */
export interface PortfolioSummaryResponse {
  as_of: string;
  totals: PortfolioTotals;
  positions: SummaryPositionItem[];
}

/** Backend `RowError`. */
export interface ImportPositionError {
  row: number;
  field: string;
  reason: string;
}

/** Backend `ImportResult`. */
export interface ImportPositionsResponse {
  imported: number;
  errors: ImportPositionError[];
}

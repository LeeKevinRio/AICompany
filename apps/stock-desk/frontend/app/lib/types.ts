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

/* ============================================================================
 * M7 (Phase 6): signals / advice / leverage / backtest / settings / alerts
 *
 * Every shape below was re-verified directly against dev-lead's router source
 * once it landed mid-implementation (an earlier draft of this file had to
 * guess several of these before the routers existed; that draft has been
 * discarded in favour of this one). Sources actually read:
 *   - backend/app/api/common.py         (EnvelopeBase / DataMeta / PayloadStatus)
 *   - backend/app/api/signals.py        (SignalsResponse)
 *   - backend/app/api/advice.py         (AdviceResponse)
 *   - backend/app/api/leverage.py       (LeverageResponse)
 *   - backend/app/api/backtest.py       (BacktestRequest / BacktestResponse)
 *   - backend/app/api/settings.py       (SettingsResponse)
 *   - backend/app/api/alerts.py         (rule/event list envelopes, evaluate)
 *   - backend/app/settings/models.py    (AppSettings / CostModelSettings / AlertSettings)
 *   - backend/app/alerts/models.py      (AlertRule / AlertEvent / discriminated params)
 *   - backend/app/advice/book.py        (PortfolioContext assembly + its notes)
 *   - backend/app/backtest/strategies.py (STRATEGY_IDS)
 *   - backend/app/signals/service.py / models.py / technical.py / risk.py
 *   - backend/app/advice/engine.py      (build_advice card dict)
 *   - backend/app/advice/limits.py      (LimitCheck / QuantityRange / RiskBudget / LIMIT_IDS)
 *   - backend/app/leverage/service.py + detect.py + drag.py + erosion.py
 *
 * Known gap (not a bug in this file): no endpoint returns raw OHLC bars, only
 * computed indicators (`compute_signals` never included them, and no bars
 * router exists). `PriceChart` therefore cannot draw candlesticks against real
 * data and says so explicitly instead of inventing bars — see its component
 * doc comment.
 * ==========================================================================*/

/** Backend `PayloadStatus` (app/api/common.py). */
export type PayloadStatus = "ok" | "insufficient_data";

/** Backend `DataMeta` (app/api/common.py) — provenance of the bars behind a response. */
export interface DataMeta {
  status: string;
  source: string;
  staleness_minutes: number | null;
  /**
   * Backend `DataMeta.is_within_ttl` (app/api/common.py). Only meaningful when
   * `status === "cached_stale"`: `true` means the cached data is still inside
   * its TTL and was served without calling any provider, `false` means it
   * really is out of date. `null` on every live rung, where the question does
   * not apply (ADR-0005 D-2).
   */
  is_within_ttl: boolean | null;
  bar_count: number;
  first_bar_date: string | null;
  last_bar_date: string | null;
  reason: string | null;
}

/** Fields shared by every symbol-scoped envelope (backend `EnvelopeBase`). */
export interface EnvelopeBase {
  symbol: string;
  market: string;
  status: PayloadStatus;
  reason: string | null;
  data: DataMeta;
  as_of: string;
}

/** Backend `app.signals.models.Status` / `app.leverage.*` `Status`. */
export type MeasureStatus = "ok" | "insufficient_data";

/** Backend `InputsUsed` (app/signals/models.py). */
export interface InputsUsed {
  columns: string[];
  window: Record<string, number>;
  description: string;
}

/** Backend `IndicatorResult` (app/signals/models.py). */
export interface IndicatorResult {
  name: string;
  status: MeasureStatus;
  params: Record<string, number>;
  dates: string[];
  series: Record<string, (number | null)[]>;
  last: Record<string, number | null>;
  inputs_used: InputsUsed;
  as_of: string | null;
  source: string | null;
}

/** Backend `VolatilityResult` (app/signals/risk.py). */
export interface VolatilityResult {
  status: MeasureStatus;
  annualized_volatility: number | null;
  daily_volatility: number | null;
  observations: number;
  inputs_used: InputsUsed;
  as_of: string | null;
  source: string | null;
}

/** Backend `DrawdownResult` (app/signals/risk.py). */
export interface DrawdownResult {
  status: MeasureStatus;
  max_drawdown: number | null;
  peak_date: string | null;
  trough_date: string | null;
  observations: number;
  inputs_used: InputsUsed;
  as_of: string | null;
  source: string | null;
}

/** Backend `BetaResult` (app/signals/risk.py). */
export interface BetaResult {
  status: MeasureStatus;
  beta: number | null;
  observations: number;
  benchmark: string | null;
  inputs_used: InputsUsed;
  as_of: string | null;
  source: string | null;
}

/** The `technical` block of a `compute_signals` output (app/signals/service.py). */
export interface SignalsTechnicalBlock {
  moving_averages: IndicatorResult;
  rsi: IndicatorResult;
  macd: IndicatorResult;
  bollinger: IndicatorResult;
  atr: IndicatorResult;
  kd: IndicatorResult;
  volume_zscore: IndicatorResult;
}

/** The `risk` block of a `compute_signals` output (app/signals/service.py). */
export interface SignalsRiskBlock {
  volatility: VolatilityResult;
  drawdown: DrawdownResult;
  beta: BetaResult;
}

/**
 * `compute_signals()` return dict verbatim (app/signals/service.py) — the
 * `signals` field of `GET /api/signals/{symbol}` (app/api/signals.py,
 * verified). No `bars` field: `compute_signals` is signals-only by design and
 * no endpoint anywhere returns raw OHLC (confirmed by reading every router).
 */
export interface SignalsPayload {
  symbol: string;
  bar_count: number;
  as_of: string | null;
  source: string | null;
  technical?: SignalsTechnicalBlock;
  risk?: SignalsRiskBlock;
}

/** Backend `SignalsResponse` (app/api/signals.py, verified). */
export interface SignalsResponse extends EnvelopeBase {
  signals: SignalsPayload | null;
}

/**
 * Backend `Bar` (app/api/bars.py, verified) — one daily OHLCV bar as the chart
 * consumes it. OHLC are `Decimal` and serialize as strings (project-wide
 * convention, see `PositionInput` above); `volume` stays a plain integer.
 * `symbol`/`market`/`as_of` are dropped here because the envelope already
 * carries them.
 */
export interface Bar {
  date: string;
  open: string;
  high: string;
  low: string;
  close: string;
  volume: number;
  currency: string;
  source: string;
}

/**
 * Backend `BarsResponse` (app/api/bars.py, verified) — `GET /api/bars/{symbol}`.
 * IMPORTANT: `bars` is a top-level field, a sibling of `data` (`DataMeta`), NOT
 * nested inside it. Ascending by date; empty when `status` is
 * `"insufficient_data"`. Uses the same default `lookback_days` (540) and the
 * same loader as `/api/signals`, so the two responses cover the same range and
 * a K-line + MA overlay lines up bar-for-bar.
 */
export interface BarsResponse extends EnvelopeBase {
  bars: Bar[];
}

/* --- Advice (backend/app/api/advice.py + advice/engine.py + advice/book.py) */

/** Backend `CardAction` (app/advice/engine.py). */
export type CardAction =
  | "add"
  | "hold"
  | "reduce"
  | "stop_loss"
  | "take_profit"
  | "insufficient_data";

/** Backend `Confidence` (app/advice/engine.py). */
export type Confidence = "low" | "medium" | "high";

/** Backend `LimitStatus` (app/advice/limits.py). */
export type LimitStatus = "passed" | "violated" | "not_evaluable";

/** Backend `LimitCheck` (app/advice/limits.py). */
export interface LimitCheck {
  index: number;
  id: string;
  name: string;
  status: LimitStatus;
  detail: string;
  observed: number | null;
  threshold: number | null;
}

/**
 * Backend `QuantityRange` (app/advice/limits.py, verified). `restores_compliance`
 * is the machine-readable half of what `basis` says in prose: whether acting on
 * the suggested quantity actually leaves the binding cap non-violated. Always
 * `true` on the buy side; can be `false` on the sell side when the cap is
 * driven by *other* positions, so selling this whole holding still does not
 * clear it — that case must be surfaced as prominently as `blocked_notices`,
 * not left to the `basis` prose alone.
 */
export interface QuantityRange {
  min_shares: number;
  max_shares: number;
  restores_compliance: boolean;
  basis: string;
}

/** One entry of `build_advice()`'s `matched_rules` (app/advice/engine.py). */
export interface MatchedRule {
  id: string;
  name: string;
  action: string;
  weight: number;
  weight_meaning: string;
  explanation: string;
}

/** One entry of `build_advice()`'s `evaluation.skipped_rules`. */
export interface SkippedRule {
  id: string;
  name: string;
  reason: string;
  missing_fields: string[];
}

/** One entry of `build_advice()`'s `action_weights`. */
export interface ActionWeight {
  action: string;
  weight: number;
  rule_ids: string[];
}

/** One entry of `build_advice()`'s `direction_weights`. */
export interface DirectionWeight {
  direction: string;
  weight: number;
  actions: string[];
}

/** `build_advice()`'s `evaluation` block. */
export interface AdviceEvaluation {
  total_rules: number;
  evaluated_rules: number;
  matched_rules: number;
  data_completeness: number;
  skipped_rules: SkippedRule[];
}

/** `build_advice()`'s `observation_window` block. */
export interface ObservationWindow {
  start: string | null;
  end: string | null;
  bars: number | null;
}

/**
 * Backend `build_advice()` return dict (app/advice/engine.py), verbatim as
 * the `advice` field of `GET /api/advice/{symbol}` (app/api/advice.py).
 */
export interface AdviceCard {
  symbol: string;
  action: CardAction;
  quantity_range: QuantityRange | null;
  matched_rules: MatchedRule[];
  counterarguments: string[];
  invalidation_conditions: string[];
  confidence: Confidence;
  confidence_meaning: string;
  rules_version: string;
  as_of: string | null;
  observation_window: ObservationWindow;
  disclaimer: string;
  limits_check: LimitCheck[];
  action_weights: ActionWeight[];
  direction_weights: DirectionWeight[];
  has_conflict: boolean;
  aggregated_action: string | null;
  blocked_action: string | null;
  blocked_notices: string[];
  downgrade_notices: string[];
  evaluation: AdviceEvaluation;
}

/**
 * Backend `PortfolioContext.model_dump()` (app/advice/limits.py), as returned
 * on `AdviceResponse.portfolio_context` (app/api/advice.py). Built by
 * `app.advice.book.build_book_context` — `total_equity_twd` there is *defined*
 * as the book's valued market value (no cash/account balance exists anywhere
 * in this product); that assumption always rides along in `context_notes`.
 */
export interface PortfolioContextOut {
  symbol: string;
  total_equity_twd: number | null;
  position_market_value_twd: number | null;
  position_cost_twd: number | null;
  gross_exposure_twd: number | null;
  quantity: number | null;
  close: number | null;
  fx_to_twd: number;
  atr: number | null;
  sector: string | null;
  sector_market_value_twd: number | null;
  win_rate: number | null;
  payoff_ratio: number | null;
}

/** Backend `AdviceResponse` (app/api/advice.py, verified). */
export interface AdviceResponse extends EnvelopeBase {
  advice: AdviceCard | null;
  held: boolean;
  position_ids: number[];
  portfolio_context: PortfolioContextOut;
  context_notes: string[];
}

/* --- Leverage chapter (backend/app/api/leverage.py + leverage/service.py) - */

/** Backend `ChapterStatus` (app/leverage/service.py). */
export type ChapterStatus = "ok" | "partial" | "insufficient_data" | "not_applicable";

/** Backend `DetectionStatus` (app/leverage/detect.py). */
export type DetectionStatus = "ok" | "insufficient_data" | "not_applicable";

/** Backend `LeverageDetection` (app/leverage/detect.py). */
export interface LeverageDetection {
  status: DetectionStatus;
  symbol: string;
  normalized_symbol: string;
  instrument_type: InstrumentType;
  is_daily_reset_leveraged: boolean;
  leverage_factor: number | null;
  underlying_index: string | null;
  expense_ratio_annual: number | null;
  metadata_verified: boolean;
  metadata_verified_on: string | null;
  source_note: string | null;
  classification_mismatch: boolean;
  reason: string | null;
  notes: string[];
}

/** `build_leverage_chapter()`'s `holding` block (app/leverage/service.py `_holding_block`). */
export interface LeverageHolding {
  status: MeasureStatus;
  opened_at: string;
  first_bar_date: string | null;
  last_bar_date: string | null;
  bars_since_opened_at: number;
  holding_trading_days: number | null;
  holding_days: number | null;
  reason: string | null;
}

/** Backend `HoldingWindow` (app/leverage/drag.py). */
export interface DragHoldingWindow {
  start_date: string | null;
  end_date: string | null;
  aligned_bars: number;
  trading_days: number;
  calendar_days: number | null;
  opened_at: string | null;
  days_since_opened_at: number | null;
}

/** Backend `TheoreticalDrag` (app/leverage/drag.py). */
export interface TheoreticalDrag {
  status: MeasureStatus;
  formula: string;
  annualized_volatility: number | null;
  daily_volatility: number | null;
  horizon_years: number | null;
  observations: number;
  theoretical_drag: number | null;
  measured_reset_effect: number | null;
  difference: number | null;
  reason: string | null;
}

/** Backend `DragDecomposition` (app/leverage/drag.py). */
export interface DragDecomposition {
  status: MeasureStatus;
  leverage_factor: number;
  expense_ratio_annual: number;
  window: DragHoldingWindow;
  index_return: number | null;
  actual_return: number | null;
  naive_expected_return: number | null;
  ideal_daily_reset_return: number | null;
  gap: number | null;
  fee_effect: number | null;
  reset_effect: number | null;
  residual: number | null;
  identity_abs_error: number | null;
  ideal_path_wiped_out: boolean;
  theoretical: TheoreticalDrag;
  assumptions: string[];
  inputs_used: InputsUsed;
  as_of: string | null;
  source: string | null;
  index_as_of: string | null;
  index_source: string | null;
  reason: string | null;
}

/** Backend `ErosionScenario` (app/leverage/erosion.py). */
export interface ErosionScenario {
  label: string;
  horizon_trading_days: number;
  horizon_years: number;
  volatility_drag_pct: number;
  expense_pct: number;
  total_expected_erosion_pct: number;
}

/** Backend `ErosionEstimate` (app/leverage/erosion.py). */
export interface ErosionEstimate {
  status: MeasureStatus;
  nature: string;
  leverage_factor: number;
  expense_ratio_annual: number;
  window: number;
  observations: number;
  min_observations: number;
  annualized_volatility: number | null;
  daily_volatility: number | null;
  scenarios: ErosionScenario[];
  assumptions: string[];
  inputs_used: InputsUsed;
  as_of: string | null;
  source: string | null;
  reason: string | null;
}

/** Backend `build_leverage_chapter()` return dict (app/leverage/service.py). */
export interface LeverageChapter {
  symbol: string;
  position_id: number;
  generated_at: string;
  disclosure: string;
  detection: LeverageDetection;
  holding: LeverageHolding;
  drag: DragDecomposition | null;
  erosion: ErosionEstimate | null;
  notes: string[];
  chapter_status: ChapterStatus;
  reason: string | null;
}

/**
 * Backend `LeverageResponse` (app/api/leverage.py, verified). A symbol with no
 * matching stored position is a 404 (`ApiError`), not this shape — the
 * chapter needs a real holding's `opened_at` to measure from.
 */
export interface LeverageResponse extends EnvelopeBase {
  chapter: LeverageChapter | null;
  position_id: number | null;
  index_bars_available: boolean;
}

/* --- Backtest (backend/app/api/backtest.py + backtest/report.py + strategies.py) */

/** Backend `PerformanceMetrics` (app/backtest/report.py). */
export interface PerformanceMetrics {
  label: string;
  start_date: string | null;
  end_date: string | null;
  observations: number;
  start_equity: number | null;
  end_equity: number | null;
  total_return: number | null;
  cagr: number | null;
  annualized_volatility: number | null;
  sharpe: number | null;
  sortino: number | null;
  max_drawdown: number | null;
  max_drawdown_peak_date: string | null;
  max_drawdown_trough_date: string | null;
  win_rate: number | null;
  profit_factor: number | null;
  num_trades: number;
  num_closing_trades: number;
  turnover: number | null;
}

/** Backend `SegmentReport` (app/backtest/report.py). */
export interface SegmentReport {
  strategy: PerformanceMetrics;
  buy_and_hold: PerformanceMetrics;
}

/** Backend `WalkForwardReport` (app/backtest/report.py). */
export interface WalkForwardReport {
  in_sample: SegmentReport;
  out_of_sample: SegmentReport;
}

/**
 * Mirrors backend `CostModelSettings` (app/settings/models.py) — a validating
 * mirror of `CostModel` (app/backtest/costs.py) with the same rate-provenance
 * contract: `verified_on: null` means UNVERIFIED. Used both as the cost block
 * inside `GET/PUT /api/settings` and as the optional per-run override on
 * `POST /api/backtest`.
 */
export interface CostModelSettings {
  tw_broker_fee_rate: number;
  tw_tax_rate_stock: number;
  tw_tax_rate_etf: number;
  us_broker_fee_rate: number;
  us_sell_regulatory_fee_rate: number;
  slippage_bps: number;
  verified_on: string | null;
}

/** Backend `STRATEGY_IDS` (app/backtest/strategies.py) — only one strategy ships. */
export type BacktestStrategy = "ma_cross";

/** Backend `BacktestRequest` (app/api/backtest.py, verified). */
export interface BacktestRequest {
  symbol: string;
  market: Market;
  strategy: BacktestStrategy;
  start: string; // date, e.g. "2024-01-01"
  end: string; // date
  instrument_type: InstrumentType;
  initial_cash: number;
  train_size: number;
  test_size: number;
  //: Per-run cost overrides; omitted -> the stored settings are used.
  cost?: CostModelSettings;
}

/** One fold's index geometry (app/api/backtest.py `folds` list). */
export interface WalkForwardFoldInfo {
  fold: number;
  train_start: number;
  train_stop: number;
  test_start: number;
  test_stop: number;
}

/** Backend `BacktestResponse` (app/api/backtest.py, verified). */
export interface BacktestResponse {
  symbol: string;
  market: string;
  strategy: string;
  status: PayloadStatus;
  reason: string | null;
  report: WalkForwardReport | null;
  folds: WalkForwardFoldInfo[];
  cost_model: CostModelSettings;
  rates_verified: boolean;
  notes: string[];
  data: DataMeta;
  as_of: string;
}

/* --- Settings (backend/app/api/settings.py + settings/models.py) --------- */

/** Mirrors backend `RiskBudget` (app/advice/limits.py) field-for-field. */
export interface RiskBudgetSettings {
  max_position_weight: number;
  max_sector_weight: number;
  max_gross_exposure: number;
  max_loss_per_trade: number;
  atr_stop_multiple: number;
  kelly_fraction_cap: number;
  kelly_position_cap: number;
}

/** Backend `AlertSettings` (app/settings/models.py). */
export interface AlertSettings {
  enabled: boolean;
  evaluation_interval_minutes: number;
  cooldown_minutes: number;
  notify_webhooks: boolean;
}

/** Backend `AppSettings` (app/settings/models.py) — the full settings document. */
export interface AppSettings {
  risk_budget: RiskBudgetSettings;
  cost_model: CostModelSettings;
  alerts: AlertSettings;
}

/** Backend `SettingsResponse` (app/api/settings.py, verified). */
export interface SettingsResponse {
  settings: AppSettings;
  rates_verified: boolean;
  notes: string[];
  as_of: string;
}

/**
 * Backend `AppSettingsPatch` (app/settings/models.py) — the `PUT` body. Each
 * section is optional and replaced *as a whole* when present; an omitted
 * section is left untouched server-side. This app always submits every
 * section together (see `SettingsForm`), so in practice all three are sent.
 */
export interface AppSettingsPatch {
  risk_budget?: RiskBudgetSettings;
  cost_model?: CostModelSettings;
  alerts?: AlertSettings;
}

/* --- Alerts (backend/app/api/alerts.py + alerts/models.py) --------------- */

/** Backend `AlertType` (app/alerts/models.py). */
export type AlertType = "price_above" | "price_below" | "signal_condition" | "risk_limit_breach";

/** Backend `ComparisonOp` (app/advice/loader.py), reused verbatim by `signal_condition` rules. */
export type ComparisonOp = "gt" | "gte" | "lt" | "lte" | "eq" | "ne" | "abs_gt" | "abs_lt";

/** Backend `Comparison` (app/advice/loader.py) as embedded in `SignalConditionParams`. */
export interface ComparisonInput {
  field: string;
  op: ComparisonOp;
  value?: number | null;
  ref?: string | null;
}

/** Backend `PriceThresholdParams` (app/alerts/models.py) — `price_above` / `price_below`. */
export interface PriceThresholdParams {
  threshold: number;
}

/** Backend `SignalConditionParams` (app/alerts/models.py). */
export interface SignalConditionParams {
  condition: ComparisonInput;
}

/** Backend `LimitSelector` (app/alerts/models.py) — a named cap, or `"any"`. */
export type LimitSelector =
  | "any"
  | "single_position_weight"
  | "sector_weight"
  | "gross_exposure"
  | "per_trade_loss"
  | "kelly_fraction";

/** Backend `RiskLimitParams` (app/alerts/models.py) — `risk_limit_breach`. */
export interface RiskLimitParams {
  limit_id: LimitSelector;
}

export type AlertParams = PriceThresholdParams | SignalConditionParams | RiskLimitParams;

/** Backend `AlertRuleInput` (app/alerts/models.py) — the `POST /api/alerts` body. */
export interface AlertRuleInput {
  type: AlertType;
  symbol: string;
  market: Market;
  params: AlertParams;
  enabled: boolean;
  note: string | null;
}

/** Backend `AlertRule` (app/alerts/models.py) — a stored rule. */
export interface AlertRule extends AlertRuleInput {
  id: number;
  created_at: string;
  updated_at: string;
}

/** Backend `AlertRuleListResponse` (app/api/alerts.py). */
export interface AlertRuleListResponse {
  items: AlertRule[];
  as_of: string;
}

/** Backend `AlertEvent` (app/alerts/models.py) — one firing of one rule. */
export interface AlertEvent {
  id: number;
  rule_id: number;
  rule_type: AlertType;
  symbol: string;
  market: Market;
  message: string;
  observed: Record<string, number | string | null>;
  triggered_at: string;
  acknowledged: boolean;
  acknowledged_at: string | null;
}

/** Backend `AlertEventListResponse` (app/api/alerts.py). */
export interface AlertEventListResponse {
  items: AlertEvent[];
  as_of: string;
}

/** One entry of `EvaluationResponse.outcomes` (app/api/alerts.py `_evaluation_response`). */
export interface AlertEvaluationOutcome {
  rule_id: number;
  status: string;
  reason: string | null;
}

/** Backend `EvaluationResponse` (app/api/alerts.py) — `POST /api/alerts/evaluate`. */
export interface AlertEvaluationResponse {
  evaluated: number;
  fired: number;
  events: AlertEvent[];
  outcomes: AlertEvaluationOutcome[];
  as_of: string;
}

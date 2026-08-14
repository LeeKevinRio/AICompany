/**
 * Formatting helpers for money, quantities and timestamps.
 *
 * Colour convention: this product follows the Taiwan retail-investor
 * convention of "獲利紅、虧損綠" (profit shown in red, loss shown in
 * green) — the mirror image of the "red up / green down" convention
 * used for daily price change elsewhere. This is a deliberate product
 * choice, not a bug; see `pnlColorClass` below.
 */

import type {
  AlertType,
  BacktestStrategy,
  CardAction,
  ChapterStatus,
  ComparisonOp,
  Confidence,
  Currency,
  DetectionStatus,
  InstrumentType,
  LimitSelector,
  LimitStatus,
  Market,
} from "./types";
import { HELD_ACTION_LABELS } from "./adviceWording";

const INSTRUMENT_TYPE_LABELS: Record<InstrumentType, string> = {
  stock: "股票",
  etf: "一般 ETF",
  leveraged_etf: "槓桿型 ETF",
  futures_etf: "期貨型 ETF",
};

/** `<select>` options for the manual add form, in a stable display order. */
export const INSTRUMENT_TYPE_OPTIONS: { value: InstrumentType; label: string }[] = [
  { value: "stock", label: INSTRUMENT_TYPE_LABELS.stock },
  { value: "etf", label: INSTRUMENT_TYPE_LABELS.etf },
  { value: "leveraged_etf", label: INSTRUMENT_TYPE_LABELS.leveraged_etf },
  { value: "futures_etf", label: INSTRUMENT_TYPE_LABELS.futures_etf },
];

export function instrumentTypeLabel(value: InstrumentType): string {
  return INSTRUMENT_TYPE_LABELS[value];
}

// Backend `Market = Literal["TW", "US"]` (app/positions/models.py) — this is
// the actual enum, not an invented restriction, so the manual form uses a
// <select> instead of free text.
const MARKET_LABELS: Record<Market, string> = {
  TW: "台股（TW）",
  US: "美股（US）",
};

/**
 * S7 fix (risk-final-review.md 列管項:「美股選項無 adapter 卻可選」;裁決僅有
 * 方向、無既定字面,本句為自擬保守句,待風控覆核): the market *picker* (every
 * `<select>` built from `MARKET_OPTIONS`) used to offer "US" with the exact
 * same bare label as "TW", even though the US chain (`Alpha Vantage` 主 +
 * `yfinance` 備援, `app/api/deps.py::_default_resolver`, verified) has never
 * been exercised against a real Alpha Vantage account — see this batch's
 * report for the D4 draft covering the same three-way state (接線／需金鑰／
 * 未經真實驗證) for the settings-page data-source table. Only the *option*
 * text carries the caveat, not `marketLabel()` (used to label already-held
 * US positions everywhere else): repeating a selection-time caveat next to
 * every row of an existing position would be noise, not disclosure, at that
 * point the data already flowed through the chain regardless of caveat.
 */
const US_MARKET_OPTION_CAVEAT = "（資料來源未經真實環境驗證）";

export const MARKET_OPTIONS: { value: Market; label: string }[] = [
  { value: "TW", label: MARKET_LABELS.TW },
  { value: "US", label: `${MARKET_LABELS.US}${US_MARKET_OPTION_CAVEAT}` },
];

export function marketLabel(value: Market): string {
  return MARKET_LABELS[value];
}

// Backend `Currency = Literal["TWD", "USD"]` (app/positions/models.py).
const CURRENCY_LABELS: Record<Currency, string> = {
  TWD: "TWD（新台幣）",
  USD: "USD（美元）",
};

export const CURRENCY_OPTIONS: { value: Currency; label: string }[] = [
  { value: "TWD", label: CURRENCY_LABELS.TWD },
  { value: "USD", label: CURRENCY_LABELS.USD },
];

export function marketCurrency(market: Market): Currency {
  return market === "TW" ? "TWD" : "USD";
}

/**
 * Sector dropdown's disabled hint for a non-TW position (FR-12, AC-12.6).
 * Verbatim copy of the backend's `SECTOR_US_REJECTED_MESSAGE`
 * (`app/positions/sectors.py`, verified) — reused rather than reworded so the
 * disabled state states exactly the reason the backend would give if the
 * field were submitted anyway, with no new sentence introduced.
 */
export const SECTOR_US_DISABLED_HINT =
  "美股持倉目前不可填產業別：台灣證交所產業別分類不適用於美股，" +
  "美股的分類標準尚未定案；請留空，該部位的單一產業佔比上限會如實顯示無法評估。";

function currencyPrefix(currency: string): string {
  switch (currency) {
    case "TWD":
      return "NT$";
    case "USD":
      return "US$";
    default:
      return `${currency} `;
  }
}

/** Parses a stringified Decimal for display only — never for arithmetic. */
function toDisplayNumber(value: string): number | null {
  const n = Number(value);
  return Number.isFinite(n) ? n : null;
}

export function formatMoney(
  value: string | null,
  currency: string,
  decimals = 2,
): string {
  if (value === null) return "—";
  const n = toDisplayNumber(value);
  if (n === null) return "—";
  const formatted = n.toLocaleString("zh-Hant-TW", {
    minimumFractionDigits: decimals,
    maximumFractionDigits: decimals,
  });
  return `${currencyPrefix(currency)}${formatted}`;
}

/** Same as `formatMoney` but for a plain `number` (backtest equity, not a stringified Decimal). */
export function formatMoneyNumber(value: number | null, currency: string, decimals = 2): string {
  if (value === null || !Number.isFinite(value)) return "—";
  const formatted = value.toLocaleString("zh-Hant-TW", {
    minimumFractionDigits: decimals,
    maximumFractionDigits: decimals,
  });
  return `${currencyPrefix(currency)}${formatted}`;
}

export function formatQuantity(value: string): string {
  const n = toDisplayNumber(value);
  if (n === null) return "—";
  return n.toLocaleString("zh-Hant-TW", { maximumFractionDigits: 4 });
}

/**
 * S1 fix (risk-final-review.md 列管項): the value below has always been
 * computed in `Asia/Taipei`, but the rendered string never said so — a
 * reader in another timezone (or simply unsure) had no way to tell which
 * clock the number was on. The suffix is appended here, once, so every one
 * of this function's ~15 call sites across the app picks it up without a
 * per-call-site wording decision.
 */
export function formatDateTime(iso: string | null | undefined): string {
  if (!iso) return "資料時間不明";
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return "資料時間不明";
  const formatted = new Intl.DateTimeFormat("zh-Hant-TW", {
    timeZone: "Asia/Taipei",
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
    hour12: false,
  }).format(d);
  return `${formatted}（台北時間）`;
}

/** Minutes elapsed between the given ISO timestamp and now, floored at 0. */
export function staleMinutesSince(iso: string): number {
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return 0;
  const diffMs = Date.now() - d.getTime();
  return Math.max(0, Math.round(diffMs / 60000));
}

/**
 * Profit -> red, loss -> green (see module doc comment for rationale).
 * Neutral/unknown values stay in the default text colour.
 */
export function pnlColorClass(value: string | null): string {
  if (value === null) return "text-neutral-400";
  const n = toDisplayNumber(value);
  if (n === null || n === 0) return "text-neutral-400";
  return n > 0 ? "text-rose-400" : "text-emerald-400";
}

/* ============================================================================
 * M7 additions: plain-number (not stringified Decimal) formatting for the
 * signals/advice/leverage/backtest surfaces, plus their label vocabularies.
 * ==========================================================================*/

/** Formats a plain `number | null` fraction (e.g. 0.153) as a percentage string. */
export function formatPercent(value: number | null, decimals = 2): string {
  if (value === null || !Number.isFinite(value)) return "—";
  return `${(value * 100).toLocaleString("zh-Hant-TW", {
    minimumFractionDigits: decimals,
    maximumFractionDigits: decimals,
  })}%`;
}

/** Formats a plain `number | null` with fixed decimals; never used for Decimal amounts. */
export function formatNumber(value: number | null, decimals = 2): string {
  if (value === null || !Number.isFinite(value)) return "—";
  return value.toLocaleString("zh-Hant-TW", {
    minimumFractionDigits: decimals,
    maximumFractionDigits: decimals,
  });
}

/** Same colour convention as `pnlColorClass`, for plain-number fields (獲利紅、虧損綠). */
export function numberColorClass(value: number | null): string {
  if (value === null || !Number.isFinite(value) || value === 0) return "text-neutral-400";
  return value > 0 ? "text-rose-400" : "text-emerald-400";
}

/**
 * R2 fix (risk-final-review.md): the action *label* used to live here as a
 * second, unattributed vocabulary ("加碼"/"減碼"/…) that duplicated and
 * contradicted `adviceWording.ts`'s single source of truth
 * (`HELD_ACTION_LABELS` + `buildAttributedHeadline`, §1.1/§1.2). Callers must
 * import the label from there now; this module only keeps the colour
 * mapping, which is presentation, not wording.
 */

/** Background/text colour class per action, dark-mode first. */
export function cardActionColorClass(action: CardAction): string {
  switch (action) {
    case "add":
      return "bg-rose-950/50 text-rose-300 border-rose-800";
    case "reduce":
    case "stop_loss":
      return "bg-emerald-950/50 text-emerald-300 border-emerald-800";
    case "take_profit":
      return "bg-sky-950/50 text-sky-300 border-sky-800";
    case "insufficient_data":
      return "bg-neutral-800 text-neutral-300 border-neutral-700";
    case "hold":
    default:
      return "bg-amber-950/50 text-amber-300 border-amber-800";
  }
}

const CONFIDENCE_LABELS: Record<Confidence, string> = {
  low: "低",
  medium: "中",
  high: "高",
};

export function confidenceLabel(value: Confidence): string {
  return CONFIDENCE_LABELS[value];
}

const LIMIT_STATUS_LABELS: Record<LimitStatus, string> = {
  passed: "通過",
  violated: "已違反",
  not_evaluable: "無法評估",
};

export function limitStatusLabel(value: LimitStatus): string {
  return LIMIT_STATUS_LABELS[value];
}

export function limitStatusColorClass(value: LimitStatus): string {
  switch (value) {
    case "passed":
      return "text-emerald-300";
    case "violated":
      return "text-rose-300";
    case "not_evaluable":
    default:
      return "text-amber-300";
  }
}

const CHAPTER_STATUS_LABELS: Record<ChapterStatus, string> = {
  ok: "完整",
  partial: "部分可算",
  insufficient_data: "資料不足",
  not_applicable: "不適用",
};

export function chapterStatusLabel(value: ChapterStatus): string {
  return CHAPTER_STATUS_LABELS[value];
}

const DETECTION_STATUS_LABELS: Record<DetectionStatus, string> = {
  ok: "已辨識",
  insufficient_data: "資料不足",
  not_applicable: "不適用",
};

export function detectionStatusLabel(value: DetectionStatus): string {
  return DETECTION_STATUS_LABELS[value];
}

/**
 * Mirrors `app.backtest.strategies.STRATEGY_IDS` (backend/app/backtest/strategies.py,
 * verified). Labels are descriptive nouns naming the mechanism only — no
 * performance implication, no recommendation wording (§1.3): each strategy is
 * a textbook example the walk-forward engine can measure, not advice to trade
 * it (see the backend module's own doc comment).
 */
const BACKTEST_STRATEGY_LABELS: Record<BacktestStrategy, string> = {
  ma_cross: "均線交叉",
  rsi_reversal: "RSI 反轉",
  breakout: "N 日突破",
};

export const STRATEGY_OPTIONS: { value: BacktestStrategy; label: string }[] = (
  Object.keys(BACKTEST_STRATEGY_LABELS) as BacktestStrategy[]
).map((value) => ({ value, label: BACKTEST_STRATEGY_LABELS[value] }));

export function strategyLabel(value: BacktestStrategy): string {
  return BACKTEST_STRATEGY_LABELS[value];
}

/** Mirrors `app.advice.loader.ComparisonOp` (verified source), reused by `signal_condition` alert rules. */
const COMPARISON_OP_LABELS: Record<ComparisonOp, string> = {
  gt: "大於（>）",
  gte: "大於等於（≥）",
  lt: "小於（<）",
  lte: "小於等於（≤）",
  eq: "等於（=）",
  ne: "不等於（≠）",
  abs_gt: "絕對值大於（|x|>）",
  abs_lt: "絕對值小於（|x|<）",
};

export const COMPARISON_OP_OPTIONS: { value: ComparisonOp; label: string }[] = (
  Object.keys(COMPARISON_OP_LABELS) as ComparisonOp[]
).map((value) => ({ value, label: COMPARISON_OP_LABELS[value] }));

export function comparisonOpLabel(value: ComparisonOp): string {
  return COMPARISON_OP_LABELS[value];
}

/** Mirrors `app.alerts.models.AlertType` (backend/app/alerts/models.py, verified). */
const ALERT_TYPE_LABELS: Record<AlertType, string> = {
  price_above: "價格高於門檻",
  price_below: "價格低於門檻",
  signal_condition: "訊號條件",
  risk_limit_breach: "風險上限被觸發",
};

export const ALERT_TYPE_OPTIONS: { value: AlertType; label: string }[] = (
  Object.keys(ALERT_TYPE_LABELS) as AlertType[]
).map((value) => ({ value, label: ALERT_TYPE_LABELS[value] }));

export function alertTypeLabel(value: AlertType): string {
  return ALERT_TYPE_LABELS[value];
}

/** Mirrors `app.alerts.models.LimitSelector` / `app.advice.limits.LIMIT_NAMES` (verified). */
const LIMIT_SELECTOR_LABELS: Record<LimitSelector, string> = {
  any: "任一上限",
  single_position_weight: "單一標的佔比上限",
  sector_weight: "單一產業佔比上限",
  gross_exposure: "總曝險上限",
  per_trade_loss: "單筆最大可承受虧損",
  kelly_fraction: "分數 Kelly 部位上限",
};

export const LIMIT_SELECTOR_OPTIONS: { value: LimitSelector; label: string }[] = (
  Object.keys(LIMIT_SELECTOR_LABELS) as LimitSelector[]
).map((value) => ({ value, label: LIMIT_SELECTOR_LABELS[value] }));

export function limitSelectorLabel(value: LimitSelector): string {
  return LIMIT_SELECTOR_LABELS[value];
}

/**
 * Mirrors `app.advice.context.FIELD_LABELS` (backend/app/advice/context.py,
 * verified source) — the closed vocabulary of fields the signal/advice layer
 * can name. Reused here so an alert rule can only target a field that layer
 * actually produces.
 */
export const SIGNAL_FIELD_OPTIONS: { value: string; label: string }[] = [
  { value: "close", label: "最新收盤價" },
  { value: "ma5.last", label: "5 日均線最新值" },
  { value: "ma20.last", label: "20 日均線最新值" },
  { value: "ma60.last", label: "60 日均線最新值" },
  { value: "rsi14.last", label: "14 日 RSI 最新值" },
  { value: "macd.last", label: "MACD 快慢線差最新值" },
  { value: "macd.signal", label: "MACD 訊號線最新值" },
  { value: "macd.histogram", label: "MACD 柱狀圖最新值" },
  { value: "bollinger.middle", label: "布林通道中軌" },
  { value: "bollinger.upper", label: "布林通道上軌" },
  { value: "bollinger.lower", label: "布林通道下軌" },
  { value: "bollinger.bandwidth", label: "布林通道寬度" },
  { value: "bollinger.percent_b", label: "布林通道 %B" },
  { value: "atr14.last", label: "ATR(14) 最新值" },
  { value: "kd.k", label: "KD 指標 K 值" },
  { value: "kd.d", label: "KD 指標 D 值" },
  { value: "volume_z.last", label: "成交量 z 分數最新值" },
  { value: "volatility.annualized", label: "年化波動度" },
  { value: "drawdown.max_drawdown", label: "區間最大回撤" },
  { value: "beta.value", label: "相對指標的 beta" },
];

/**
 * Looks up a signal field's display label from `SIGNAL_FIELD_OPTIONS`,
 * falling back to the raw field key for anything not in that closed
 * vocabulary (defensive only — every field a rule can store is validated
 * against it server-side). Single source of truth for this lookup: reused
 * by `EditAlertRuleModal`'s ref-condition read-only block and
 * `AlertRulesSection`'s rule-list description (順手 fix, 2026-08-09 —
 * the list used to read only `condition.value` for a `signal_condition`
 * row and show "close 大於 —" for a `ref` (field-vs-field) rule instead of
 * naming the compared-against field).
 */
export function signalFieldLabel(value: string): string {
  return SIGNAL_FIELD_OPTIONS.find((opt) => opt.value === value)?.label ?? value;
}

/**
 * D2 item 3 (限制清單 #10 / 機會清單 D2): labels for `AdviceCard.direction_weights`
 * (backend `ACTION_DIRECTION`, `app/advice/engine.py`, verified source) — the
 * per-direction aggregation the card computes but did not render. "建設性"
 * and "防禦型" are not new vocabulary: they are the exact words already
 * shipped and risk-approved in `adviceWording.ts`'s
 * `buildCandidateSupportiveComposition` ("...建設性規則命中...") and the
 * backend's own `downgrade_notices` ("...防禦型規則同時命中..."). "中性" (for
 * the backend's `hold` direction) has no such precedent and is a plain
 * factual category label, not a judgement — flagged for
 * risk-compliance-officer to confirm alongside this batch's other new
 * strings.
 */
const RULE_DIRECTION_LABELS: Record<string, string> = {
  constructive: "建設性",
  defensive: "防禦型",
  neutral: "中性",
};

export function ruleDirectionLabel(direction: string): string {
  return RULE_DIRECTION_LABELS[direction] ?? direction;
}

/**
 * Best-effort label for one of `direction_weights[].actions` — always a
 * `CardAction` value at the engine's current implementation, but read here
 * from a wider `Record<string, string>` (not a `CardAction`-keyed lookup)
 * so an unrecognised future value degrades to its raw string instead of the
 * lookup throwing or needing a type assertion.
 */
export function actionRawLabel(action: string): string {
  return (HELD_ACTION_LABELS as Record<string, string>)[action] ?? action;
}

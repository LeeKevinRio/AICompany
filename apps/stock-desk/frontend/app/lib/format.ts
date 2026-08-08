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

export const MARKET_OPTIONS: { value: Market; label: string }[] = [
  { value: "TW", label: MARKET_LABELS.TW },
  { value: "US", label: MARKET_LABELS.US },
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

export function formatDateTime(iso: string | null | undefined): string {
  if (!iso) return "資料時間不明";
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return "資料時間不明";
  return new Intl.DateTimeFormat("zh-Hant-TW", {
    timeZone: "Asia/Taipei",
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
    hour12: false,
  }).format(d);
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

const CARD_ACTION_LABELS: Record<CardAction, string> = {
  add: "加碼",
  hold: "觀望",
  reduce: "減碼",
  stop_loss: "停損",
  take_profit: "停利",
  insufficient_data: "資料不足，本次不提供操作評估",
};

export function cardActionLabel(action: CardAction): string {
  return CARD_ACTION_LABELS[action];
}

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

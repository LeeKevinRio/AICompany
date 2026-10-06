import type { PositionPrice } from "../lib/types";
import { formatTradingDateMonthDay } from "../lib/format";

function assertNever(value: never): never {
  throw new Error(`未處理的資料狀態: ${String(value)}`);
}

/** Shown as the `title` of a stale-cache badge when the data layer gave no reason. */
export const STALE_CACHE_FALLBACK_REASON = "可能未含最近交易日";

/**
 * The price cell's tooltip date part. `as_of` is a bare trading date (daily
 * close), not an instant, so it is shown as a date only — never run through a
 * time-of-day formatter, which would invent a "08:00" that never existed.
 */
export function priceDateTooltip(asOf: string): string {
  return `資料日期 ${formatTradingDateMonthDay(asOf)}（日線收盤，非即時）`;
}

const MUTED_BADGE_CLASS =
  "whitespace-nowrap rounded bg-neutral-800 px-1.5 py-0.5 text-xs text-neutral-400";

/**
 * 風控 2026-10-06 O-3 / art-lead: "資料不足" is the most severe state, so it is
 * brighter and bordered (no red) instead of sharing the muted chip look.
 */
const UNAVAILABLE_BADGE_CLASS =
  "whitespace-nowrap rounded border border-neutral-500 bg-neutral-800 px-1.5 py-0.5 text-xs text-neutral-200";

/**
 * The price's trading date, always shown next to the price as "MM/DD 收盤".
 * `as_of` is a bare trading date (`"2026-09-30"`), so it is formatted as a
 * string — never via the `Date` constructor, which would invent a time of day.
 */
function TradingDateLabel({ asOf }: { asOf: string }) {
  return (
    <span className="whitespace-nowrap text-xs tabular-nums text-neutral-400">
      {formatTradingDateMonthDay(asOf)} 收盤
    </span>
  );
}

function StatusLabel({ price }: { price: PositionPrice }) {
  switch (price.data_status) {
    case "fresh":
      return null;
    case "backup":
      return (
        <span className="whitespace-nowrap rounded bg-amber-900/40 px-1.5 py-0.5 text-xs text-amber-300">
          備援源
        </span>
      );
    case "cached_stale":
      // Served from the local cache. `is_within_ttl === true` means the cache
      // already holds the latest completed session — as current as a live
      // fetch, so no warning. Anything else is known (or not known) to be
      // behind, and says so with the data layer's own reason.
      if (price.is_within_ttl === true) return null;
      return (
        <span
          className={MUTED_BADGE_CLASS}
          title={price.reason?.trim() ? price.reason : STALE_CACHE_FALLBACK_REASON}
        >
          資料較舊
        </span>
      );
    case "unavailable":
      return <span className={UNAVAILABLE_BADGE_CLASS}>資料不足</span>;
    default:
      return assertNever(price.data_status);
  }
}

/**
 * Renders the data-quality badge next to a position's current price: the
 * price's trading date, plus a warning label only when the price is not
 * the latest (`fresh` and an up-to-date cache get none — per spec "無標").
 * Every warning is an explicit, honest label so we never imply a price is
 * live when it is not.
 */
export function DataStatusBadge({ price }: { price: PositionPrice | null }) {
  if (price === null) {
    return <span className={UNAVAILABLE_BADGE_CLASS}>資料不足</span>;
  }
  // The date label sits on its own line under the price (CEO 2026-10-03 首頁
  // 重排); badges share that line and wrap between tags, never inside one.
  return (
    <span className="flex flex-wrap items-center gap-x-1.5 gap-y-1">
      <TradingDateLabel asOf={price.as_of} />
      <StatusLabel price={price} />
    </span>
  );
}

import type { PositionFx } from "../lib/types";
import { formatTradingDateMonthDay } from "../lib/format";
import { STALE_CACHE_FALLBACK_REASON } from "./DataStatusBadge";

function assertNever(value: never): never {
  throw new Error(`未處理的匯率資料狀態: ${String(value)}`);
}

const MUTED_BADGE_CLASS =
  "whitespace-nowrap rounded bg-neutral-800 px-1.5 py-0.5 text-xs text-neutral-400";

/**
 * The rate's calendar date, shown next to the converted figures as
 * "MM/DD 匯率". `as_of` is a bare date (`"2026-10-02"`), so it is formatted as
 * a string — never via the `Date` constructor, which would read it as UTC
 * midnight and turn it into a fake "delayed N minutes".
 */
function RateDateLabel({ asOf }: { asOf: string }) {
  return (
    <span className="whitespace-nowrap text-xs tabular-nums text-neutral-400">
      {formatTradingDateMonthDay(asOf)} 匯率
    </span>
  );
}

/**
 * `prefix` is the leading "匯率 " that tells this badge apart from the price
 * badge. It is dropped when the "MM/DD 匯率" date label already sits right
 * before it, so the word never appears twice in a row.
 */
function StatusLabel({ fx, prefix }: { fx: PositionFx; prefix: string }) {
  switch (fx.data_status) {
    case "fresh":
      return null;
    case "backup":
      return (
        <span
          className="whitespace-nowrap rounded bg-amber-900/40 px-1.5 py-0.5 text-xs text-amber-300"
          title={fx.source_note || undefined}
        >
          {prefix}備援源
        </span>
      );
    case "cached_stale":
      // Same rule as the price badge: only an up-to-date cache
      // (`is_within_ttl === true`) goes unlabelled. The FX data layer has no
      // cache rung today (ADR-0011), so this branch is defensive.
      if (fx.is_within_ttl === true) return null;
      return (
        <span
          className={MUTED_BADGE_CLASS}
          title={fx.reason?.trim() ? fx.reason : STALE_CACHE_FALLBACK_REASON}
        >
          {prefix}資料較舊
        </span>
      );
    case "unavailable":
      return (
        <span className={MUTED_BADGE_CLASS} title={fx.source_note || undefined}>
          {prefix}資料不足
        </span>
      );
    default:
      return assertNever(fx.data_status);
  }
}

/**
 * Renders the FX-rate provenance next to a non-TWD position's TWD-converted
 * figures (ADR-0011 匯率梯子揭露). `fx === null` means a TWD position with no
 * conversion at all, so nothing renders. Whenever a rate was found its date
 * is shown as "MM/DD 匯率"; a warning label follows only when the rate is
 * not the latest (`fresh` gets none — same "無標" convention as
 * `DataStatusBadge`), reusing the price badge's exact wording so the two
 * badges never invent separate vocabularies for the same ladder.
 */
export function FxStatusBadge({ fx }: { fx: PositionFx | null }) {
  if (fx === null) return null;
  const hasDate = fx.as_of !== null;
  return (
    <span className="flex flex-wrap items-center justify-end gap-x-1.5 gap-y-1">
      {fx.as_of !== null && <RateDateLabel asOf={fx.as_of} />}
      <StatusLabel fx={fx} prefix={hasDate ? "" : "匯率 "} />
    </span>
  );
}

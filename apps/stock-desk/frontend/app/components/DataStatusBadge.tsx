import type { PositionPrice } from "../lib/types";
import { staleMinutesSince } from "../lib/format";

function assertNever(value: never): never {
  throw new Error(`未處理的資料狀態: ${String(value)}`);
}

/**
 * Renders the data-quality badge next to a position's current price.
 * `fresh` renders nothing (per spec: "無標"); every other status gets
 * an explicit, honest label so we never imply a price is live when it
 * is not.
 */
export function DataStatusBadge({ price }: { price: PositionPrice | null }) {
  if (price === null) {
    return (
      <span className="ml-1.5 rounded bg-neutral-800 px-1.5 py-0.5 text-xs text-neutral-400">
        資料不足
      </span>
    );
  }

  switch (price.data_status) {
    case "fresh":
      return null;
    case "backup":
      return (
        <span className="ml-1.5 rounded bg-amber-900/40 px-1.5 py-0.5 text-xs text-amber-300">
          備援源
        </span>
      );
    case "cached_stale": {
      const minutes = staleMinutesSince(price.as_of);
      return (
        <span className="ml-1.5 rounded bg-neutral-800 px-1.5 py-0.5 text-xs text-neutral-400">
          資料延遲 {minutes} 分鐘
        </span>
      );
    }
    case "unavailable":
      return (
        <span className="ml-1.5 rounded bg-neutral-800 px-1.5 py-0.5 text-xs text-neutral-400">
          資料不足
        </span>
      );
    default:
      return assertNever(price.data_status);
  }
}

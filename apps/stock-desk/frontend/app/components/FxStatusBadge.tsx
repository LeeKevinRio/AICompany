import type { PositionFx } from "../lib/types";
import { staleMinutesSince } from "../lib/format";

function assertNever(value: never): never {
  throw new Error(`未處理的匯率資料狀態: ${String(value)}`);
}

/**
 * Renders the FX-rate provenance badge next to a non-TWD position's
 * TWD-converted figures (ADR-0011 匯率梯子揭露). `fx === null` means a TWD
 * position with no conversion at all, so nothing renders. `fresh` also
 * renders nothing (same "無標" convention as `DataStatusBadge`) — only a
 * degraded rung earns an explicit label, reusing the exact same wording
 * `DataStatusBadge` already uses for price so the two badges cannot drift
 * into inventing separate vocabularies for the same four-layer ladder. The
 * leading "匯率" prefix is what tells the two badges apart when both sit
 * beside the same cell.
 */
export function FxStatusBadge({ fx }: { fx: PositionFx | null }) {
  if (fx === null) return null;

  switch (fx.data_status) {
    case "fresh":
      return null;
    case "backup":
      return (
        <span
          className="ml-1.5 rounded bg-amber-900/40 px-1.5 py-0.5 text-xs text-amber-300"
          title={fx.source_note || undefined}
        >
          匯率 備援源
        </span>
      );
    case "cached_stale": {
      const minutes = fx.as_of === null ? 0 : staleMinutesSince(fx.as_of);
      return (
        <span
          className="ml-1.5 rounded bg-neutral-800 px-1.5 py-0.5 text-xs text-neutral-400"
          title={fx.source_note || undefined}
        >
          匯率 資料延遲 {minutes} 分鐘
        </span>
      );
    }
    case "unavailable":
      return (
        <span
          className="ml-1.5 rounded bg-neutral-800 px-1.5 py-0.5 text-xs text-neutral-400"
          title={fx.source_note || undefined}
        >
          匯率 資料不足
        </span>
      );
    default:
      return assertNever(fx.data_status);
  }
}

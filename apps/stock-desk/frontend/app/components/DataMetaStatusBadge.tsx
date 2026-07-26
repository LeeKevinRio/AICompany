/**
 * Same four-layer degradation-ladder convention as `DataStatusBadge`
 * (`fresh` -> no badge, `backup`/`cached_stale`/`unavailable` -> explicit
 * label), adapted for `DataMeta` (app/api/common.py, verified) instead of a
 * position's `PriceInfo`: `DataMeta.status` is the same
 * `app.data.interface.DataStatus` value serialized as a plain string, and it
 * already carries `staleness_minutes` precomputed server-side, so no client
 * date math is needed here (unlike `DataStatusBadge`, which derives it from
 * `as_of`).
 */
export function DataMetaStatusBadge({
  status,
  stalenessMinutes,
}: {
  status: string;
  stalenessMinutes: number | null;
}) {
  switch (status) {
    case "fresh":
      return null;
    case "backup":
      return (
        <span className="ml-1.5 rounded bg-amber-900/40 px-1.5 py-0.5 text-xs text-amber-300">
          備援源
        </span>
      );
    case "cached_stale":
      return (
        <span className="ml-1.5 rounded bg-neutral-800 px-1.5 py-0.5 text-xs text-neutral-400">
          資料延遲{stalenessMinutes !== null ? ` ${stalenessMinutes} 分鐘` : ""}
        </span>
      );
    case "unavailable":
      return (
        <span className="ml-1.5 rounded bg-neutral-800 px-1.5 py-0.5 text-xs text-neutral-400">
          資料不足
        </span>
      );
    default:
      return (
        <span className="ml-1.5 rounded bg-neutral-800 px-1.5 py-0.5 text-xs text-neutral-400">
          {status}
        </span>
      );
  }
}

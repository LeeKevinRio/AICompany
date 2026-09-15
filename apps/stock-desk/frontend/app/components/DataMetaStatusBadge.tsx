/**
 * Same four-layer degradation-ladder convention as `DataStatusBadge`
 * (`fresh` -> no badge, `backup`/`cached_stale`/`unavailable` -> explicit
 * label), adapted for `DataMeta` (app/api/common.py, verified) instead of a
 * position's `PriceInfo`: `DataMeta.status` is the same
 * `app.data.interface.DataStatus` value serialized as a plain string, and it
 * already carries `staleness_minutes` precomputed server-side, so no client
 * date math is needed here (unlike `DataStatusBadge`, which derives it from
 * `as_of`).
 *
 * `cached_stale` copy (ADR-0005 決策四 / D-2, superseded by ADR-0009 D-5;
 * 風控 2026-09-13 第二輪核可方案 A 八句): the badge
 * states a *verifiable fact* -- the date the data runs to
 * (`DataMeta.last_bar_date`) and when it was last obtained -- instead of a
 * clock claim (「今日已更新」 was false on any weekend) or an inference
 * (「已含最近交易日」 reads as "today" during the session). `isWithinTtl`
 * (backend: "cache holds the latest published session") only picks the
 * frame: `true` → 本機快取; `false`/`null` (the field only ever applies to
 * this status, so `null` means "unknown") → 快取資料 + 「可能未含最近交易日」.
 * A missing date or minute count truncates the sentence rather than
 * fabricating a value. Neither branch may read as live.
 */
export function cachedStaleLabel({
  stalenessMinutes,
  isWithinTtl,
  lastBarDate,
}: {
  stalenessMinutes: number | null;
  isWithinTtl: boolean | null;
  lastBarDate: string | null;
}): string {
  const obtained = stalenessMinutes !== null ? `${stalenessMinutes} 分鐘前取得` : null;
  if (isWithinTtl === true) {
    if (lastBarDate !== null) {
      return obtained !== null ? `本機快取，資料截至 ${lastBarDate}（${obtained}）` : `本機快取，資料截至 ${lastBarDate}`;
    }
    return obtained !== null ? `本機快取（${obtained}）` : "本機快取";
  }
  if (lastBarDate !== null) {
    return obtained !== null
      ? `快取資料，資料截至 ${lastBarDate}（${obtained}，可能未含最近交易日）`
      : `快取資料，資料截至 ${lastBarDate}（可能未含最近交易日）`;
  }
  return obtained !== null ? `快取資料，${obtained}，可能未含最近交易日` : "快取資料（取得時間不明，可能未含最近交易日）";
}

export function DataMetaStatusBadge({
  status,
  stalenessMinutes,
  isWithinTtl,
  lastBarDate = null,
  reason = null,
}: {
  status: string;
  stalenessMinutes: number | null;
  isWithinTtl: boolean | null;
  /** `DataMeta.last_bar_date`; omit only where the payload carries no bar dates. */
  lastBarDate?: string | null;
  /**
   * `DataMeta.reason` -- the backend's own sentence about the answer: why it
   * is the cache (the last live ask failed, ADR-0009 D-3), or that the series
   * is spliced from more than one source (ADR-0009 D-7, ADR-0005 D-5). It is
   * shown standing beside the badge in *every* status, `fresh` included -- a
   * spliced series is served as `fresh` and would otherwise say nothing --
   * and never folded into a tooltip (風控 2026-09-13 第三輪).
   */
  reason?: string | null;
}) {
  const badge = statusBadge({ status, stalenessMinutes, isWithinTtl, lastBarDate });
  if (!reason) return badge;
  return (
    <>
      {badge}
      {/* 風控 2026-09-15 條件式核可：the reason is disclosure prose, body size (text-sm), never smaller than the line it explains. */}
      <span className="ml-1.5 text-sm text-neutral-400">{reason}</span>
    </>
  );
}

function statusBadge({
  status,
  stalenessMinutes,
  isWithinTtl,
  lastBarDate,
}: {
  status: string;
  stalenessMinutes: number | null;
  isWithinTtl: boolean | null;
  lastBarDate: string | null;
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
          {cachedStaleLabel({ stalenessMinutes, isWithinTtl, lastBarDate })}
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

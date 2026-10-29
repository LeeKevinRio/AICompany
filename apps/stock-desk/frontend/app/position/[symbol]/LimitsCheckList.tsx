import type { LimitCheck } from "../../lib/types";
import { formatPercent, limitStatusLabel } from "../../lib/format";
import { riskGaugeChipClass } from "../../lib/riskGauge";
import { CAP5_SUNSET_UNRELIABLE_NOTE, showsCap5SunsetNote } from "../../lib/cap1SunsetWording";
import { SettingsFallbackNoticeLine } from "../../components/SettingsFallbackNoticeLine";

/**
 * Renders every risk-budget cap (`app.advice.limits.LimitCheck`, verified
 * source) with its own status. `not_evaluable` caps are shown with the same
 * prominence as `passed`/`violated` ones and always carry their `detail`
 * reason — this list must never collapse to "全部通過" when some caps
 * could not actually be checked (risk-compliance requirement).
 */
export function LimitsCheckList({
  limits,
  cap1MigrationNotice = null,
  settingsFallbackNotice = null,
}: {
  limits: LimitCheck[];
  /**
   * `AdviceResponse.settings_fallback_notice` (ADR-0032 N-1／N-2／N-3), the
   * backend's verbatim: list level, above every cap. `null` = none.
   */
  settingsFallbackNotice?: string | null;
  /**
   * The S2 sentence (CEO #63) for cap 1, the backend's verbatim
   * (`AdviceResponse.cap1_migration_notice`) — the same one the risk gauge's
   * cap-1 row shows (#2', S1/S1', I-2). `null` = none.
   */
  cap1MigrationNotice?: string | null;
}) {
  return (
    <>
      <SettingsFallbackNoticeLine text={settingsFallbackNotice} className="mb-2" />
      <ul className="space-y-2">
        {limits.map((limit) => (
          <li
            key={limit.id}
            className="rounded-md border border-neutral-800 p-3 text-sm"
          >
            <div className="flex flex-wrap items-center justify-between gap-2">
              <span className="font-medium text-neutral-100">
                第 {limit.index} 條・{limit.name}
              </span>
              <span
                className={`inline-flex items-center justify-center rounded-md border px-2 py-0.5 text-xs font-semibold ${riskGaugeChipClass(limit.status)}`}
              >
                {limitStatusLabel(limit.status)}
              </span>
            </div>
            <p className="mt-1 text-neutral-400">{limit.detail}</p>
            {/* Plan D sunset (日落期間字面表, required): after cap 5's detail. */}
            {showsCap5SunsetNote(limit.id, limit.status) && (
              <p className="mt-1 text-neutral-400">{CAP5_SUNSET_UNRELIABLE_NOTE}</p>
            )}
            <p className="mt-1 text-xs text-neutral-400">
              觀察值：{formatPercent(limit.observed)}　上限：{formatPercent(limit.threshold)}
            </p>
            {/* #2' / S1, S1' (I-2): under the 觀察值／上限 line, cap 1 only.
                同位原則：隨第 1 條狀態走 — it stays in the same <li> as cap 1's
                status chip, never in a nested <details>, no truncation
                (風控 2026-10-26 四項裁定 第三節).
                F-i: if cap 1's status chip, its blocked notice or any cap-1
                「已違反」 reaches the position page's main view, or the advice
                card stops being collapsed, this sentence moves with cap 1's
                status and goes back to risk-compliance. */}
            {limit.index === 1 && cap1MigrationNotice !== null && (
              <p className="mt-1 text-xs text-amber-300">{cap1MigrationNotice}</p>
            )}
          </li>
        ))}
      </ul>
    </>
  );
}

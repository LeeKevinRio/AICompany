import type { LimitCheck } from "../../lib/types";
import { formatPercent, limitStatusColorClass, limitStatusLabel } from "../../lib/format";

/**
 * Renders every risk-budget cap (`app.advice.limits.LimitCheck`, verified
 * source) with its own status. `not_evaluable` caps are shown with the same
 * prominence as `passed`/`violated` ones and always carry their `detail`
 * reason — this list must never collapse to "全部通過" when some caps
 * could not actually be checked (risk-compliance requirement).
 */
export function LimitsCheckList({ limits }: { limits: LimitCheck[] }) {
  return (
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
            <span className={`text-xs font-semibold ${limitStatusColorClass(limit.status)}`}>
              {limitStatusLabel(limit.status)}
            </span>
          </div>
          <p className="mt-1 text-neutral-400">{limit.detail}</p>
          <p className="mt-1 text-xs text-neutral-500">
            觀察值：{formatPercent(limit.observed)}　上限：{formatPercent(limit.threshold)}
          </p>
        </li>
      ))}
    </ul>
  );
}

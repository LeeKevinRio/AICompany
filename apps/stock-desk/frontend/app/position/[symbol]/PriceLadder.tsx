import { ladderBarGeometry } from "../../lib/keyLevelsVisuals";
import type { LadderGroup, LadderRung, LadderViewModel } from "../../lib/keyLevelsVisuals";

/**
 * 價位階梯 (CEO 圖形化 item 2, 2026-09-06): every reference level the panel
 * computes, on ONE list sorted from highest to lowest price, each row carrying
 * a distance bar measured against the anchor (基準價) line in the middle.
 *
 * Why a sorted list with distance bars rather than a true-scale vertical
 * axis: with up to nine levels, several of which routinely sit within a
 * percent of each other (2×ATR vs −8%, MA20 vs close), true-scale labels
 * collide; evenly spaced rows keep every label legible while the bar still
 * conveys magnitude (dataviz: label collisions → leader lines / list, never
 * stacked nudged labels).
 *
 * Colour policy (risk S1 carried forward; 風控 2026-09-06 S-c): the distance
 * bars are NEUTRAL grey on both sides of the anchor — sky is already the
 * page's 停利／進場 hue (`work/stock-desk-快市排程-視覺規範.md` §3.4), so a
 * sky bar on a stop row would cross wires. Direction is carried by which side
 * of the centre line the bar sits on and by the signed percentage; the group
 * is carried by its text tag, so there are no colour dots at all.
 *
 * Wording: the rung labels and group tags are the panel's existing pinned
 * constants, injected by the panel (`rungLabel` / `groupLabel`) so this file
 * does not import from `KeyLevelsPanel.tsx` (no module cycle). The ladder's
 * own strings below are exported and pinned by `componentWordingScan.test.ts`.
 */

export const KEY_LEVELS_LADDER_TITLE = "價位階梯";

export const KEY_LEVELS_LADDER_INTRO =
  "本面板各參考價位由高至低排列；橫條為各價位相對基準價的百分比距離，右為高於基準價，左為低於基準價。";

export const KEY_LEVELS_LADDER_HEADLINE_TAG = "大字所示";

export const KEY_LEVELS_LADDER_DISTANCE_HEADER = "相對基準價";

export const KEY_LEVELS_LADDER_NOTE =
  "排序與距離皆為算式結果，不代表價格會依此順序或幅度到達任一價位。";

function fmtSigned(pct: number): string {
  if (!Number.isFinite(pct)) return "—";
  // Values that round to 0.0 print as "0.0%", never "-0.0%" (風控 suggested).
  const rounded = Math.round(pct * 10) / 10;
  if (rounded === 0) return "0.0%";
  return `${rounded > 0 ? "+" : ""}${rounded.toFixed(1)}%`;
}

export function PriceLadder({
  model,
  rungLabel,
  groupLabel,
  fmt,
}: {
  model: LadderViewModel;
  rungLabel: (rung: LadderRung) => string;
  groupLabel: (group: LadderGroup) => string | null;
  fmt: (n: number) => string;
}) {
  return (
    <div className="mt-4 rounded-md border border-neutral-800 bg-neutral-900/60 p-3">
      <h3 className="text-sm font-semibold text-neutral-200">{KEY_LEVELS_LADDER_TITLE}</h3>
      <p className="mt-1 text-sm text-neutral-400">{KEY_LEVELS_LADDER_INTRO}</p>

      <div className="mt-3 overflow-x-auto">
        <table className="w-full min-w-[640px] text-left text-sm">
          <thead>
            <tr className="border-b border-neutral-800 text-xs text-neutral-500">
              <th className="py-1 pr-3 font-normal" scope="col">
                項目
              </th>
              <th className="py-1 pr-3 text-right font-normal" scope="col">
                價位
              </th>
              <th className="py-1 pr-3 text-right font-normal" scope="col">
                {KEY_LEVELS_LADDER_DISTANCE_HEADER}
              </th>
              <th className="w-[40%] py-1 font-normal" scope="col" aria-hidden="true" />
            </tr>
          </thead>
          <tbody>
            {model.rungs.map((rung) => {
              const geo = ladderBarGeometry(rung.distancePct, model.maxAbsDistancePct);
              const isAnchor = rung.group === "anchor";
              const group = groupLabel(rung.group);
              return (
                <tr
                  key={rung.id}
                  className={`border-b border-neutral-800/60 ${isAnchor ? "bg-neutral-800/40" : ""}`}
                >
                  <td className="py-1.5 pr-3">
                    <span className="flex items-center gap-2 whitespace-nowrap">
                      <span className={isAnchor ? "font-semibold text-neutral-100" : "text-neutral-200"}>
                        {rungLabel(rung)}
                      </span>
                      {group !== null && (
                        <span className="rounded border border-neutral-700 px-1 text-xs text-neutral-400">{group}</span>
                      )}
                      {rung.isHeadline && (
                        <span className="rounded bg-neutral-800 px-1 text-xs text-neutral-300">
                          {KEY_LEVELS_LADDER_HEADLINE_TAG}
                        </span>
                      )}
                    </span>
                  </td>
                  <td className="py-1.5 pr-3 text-right font-mono tabular-nums text-neutral-100">{fmt(rung.price)}</td>
                  <td className="py-1.5 pr-3 text-right font-mono tabular-nums text-neutral-300">
                    {isAnchor ? "—" : fmtSigned(rung.distancePct)}
                  </td>
                  <td className="py-1.5">
                    {/* Distance bar: ≤24px thick, grows from the anchor line at 50%; anchor row draws only the line. */}
                    <div className="relative h-3 w-full" aria-hidden="true">
                      <div className="absolute inset-y-0 left-1/2 w-px bg-neutral-600" />
                      {geo.widthPct > 0 && (
                        <div
                          className={`absolute inset-y-0 bg-neutral-400/70 ${
                            rung.distancePct > 0 ? "rounded-r-sm" : "rounded-l-sm"
                          }`}
                          style={{ left: `${geo.leftPct}%`, width: `${geo.widthPct}%` }}
                        />
                      )}
                    </div>
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
      <p className="mt-2 text-sm text-neutral-400">{KEY_LEVELS_LADDER_NOTE}</p>
    </div>
  );
}

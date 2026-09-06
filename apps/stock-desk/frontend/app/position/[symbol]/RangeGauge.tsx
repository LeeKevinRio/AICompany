import { GAUGE_ZONE_BANDS, gaugeMarkerLeftPct } from "../../lib/keyLevelsVisuals";
import type { RangeZone } from "../../lib/keyLevels";

/**
 * 位階量表 (CEO 圖形化 item 1, 2026-09-06): a horizontal track showing where
 * the latest close sits inside its own trailing range, with the three zones
 * `classifyRangeZone` already defines (≤30 / 30–70 / ≥70) drawn as bands.
 *
 * Colour policy (risk S1 carried forward from the 位階 大字): the bands are
 * three steps of ONE hue (sky), sequential by position — never red/green, so
 * the gauge cannot read as 便宜／貴 or 買／賣. The marker is the accent step
 * with a 2px surface ring. All numbers are also printed as text (both ends,
 * the marker label), so the picture never gates a value.
 *
 * The three zone words and the two end labels are exported constants pinned
 * by `componentWordingScan.test.ts`; the zone words are the SAME constants the
 * 大字 uses (passed in by the panel) so the gauge and the label can never
 * disagree.
 */

export const KEY_LEVELS_GAUGE_LOW_END_LABEL = "區間最低";
export const KEY_LEVELS_GAUGE_HIGH_END_LABEL = "區間最高";
/** 風控 S-b (2026-09-06): 「收盤位於 41%」 — never 「收盤 41%」, which reads as a change. */
export const KEY_LEVELS_GAUGE_MARKER_LABEL = "收盤位於";

export function buildGaugeAriaLabel(n: number, pct: number, zoneLabel: string): string {
  return `近 ${n} 根日線位階量表：收盤位於區間的 ${pct.toFixed(0)}%，${zoneLabel}`;
}

const ZONE_BAND_CLASS: Record<RangeZone, string> = {
  low: "bg-sky-950",
  mid: "bg-sky-900",
  high: "bg-sky-800",
};

export function RangeGauge({
  rangeBarCount,
  rangePositionPct,
  zone,
  zoneLabels,
  rangeLabel,
  lowText,
  highText,
}: {
  rangeBarCount: number;
  rangePositionPct: number;
  zone: RangeZone;
  zoneLabels: Record<RangeZone, string>;
  /** The panel's pinned 「近 N 根區間」 label, shown between the two end values. */
  rangeLabel: string;
  lowText: string;
  highText: string;
}) {
  const left = gaugeMarkerLeftPct(rangePositionPct);
  return (
    <figure
      role="img"
      aria-label={buildGaugeAriaLabel(rangeBarCount, rangePositionPct, zoneLabels[zone])}
      className="mt-3"
    >
      {/* Marker label rides above the track at the marker's x; clamped by translate so it never overflows. */}
      <div className="relative h-5">
        <span
          className="absolute -translate-x-1/2 whitespace-nowrap font-mono text-sm text-neutral-200"
          style={{ left: `${left}%` }}
        >
          {KEY_LEVELS_GAUGE_MARKER_LABEL} {rangePositionPct.toFixed(0)}%
        </span>
      </div>
      <div className="relative h-3 w-full">
        {/*
          Zone bands: one hue, three steps, 2px surface gaps between them. Widths
          are flex-grow ratios (not percentages) so the gaps come out of the
          bands proportionally instead of overflowing the track (qa-reviewer nit).
        */}
        <div className="absolute inset-0 flex gap-0.5 overflow-hidden rounded-full">
          {GAUGE_ZONE_BANDS.map((band) => (
            <div
              key={band.zone}
              className={`h-full ${ZONE_BAND_CLASS[band.zone]} ${zone === band.zone ? "" : "opacity-60"}`}
              style={{ flex: `${band.toPct - band.fromPct} 1 0%` }}
            />
          ))}
        </div>
        {/* Marker: ≥8px dot, 2px surface ring. */}
        <span
          aria-hidden="true"
          className="absolute top-1/2 h-4 w-4 -translate-x-1/2 -translate-y-1/2 rounded-full bg-sky-300 ring-2 ring-neutral-950"
          style={{ left: `${left}%` }}
        />
      </div>
      {/* Zone words under their bands, then the two end values. */}
      <div className="mt-1 flex text-xs text-neutral-400">
        {GAUGE_ZONE_BANDS.map((band) => (
          <span
            key={band.zone}
            className={`text-center ${zone === band.zone ? "font-semibold text-neutral-200" : ""}`}
            style={{ width: `${band.toPct - band.fromPct}%` }}
          >
            {zoneLabels[band.zone]}
          </span>
        ))}
      </div>
      {/* 風控 S-a: the two end values are the formula's denominator inputs — text-sm like every other value row. */}
      <figcaption className="mt-1 flex justify-between text-sm text-neutral-400">
        <span>
          {KEY_LEVELS_GAUGE_LOW_END_LABEL} <span className="font-mono text-neutral-200">{lowText}</span>
        </span>
        <span className="text-neutral-500">{rangeLabel}</span>
        <span>
          {KEY_LEVELS_GAUGE_HIGH_END_LABEL} <span className="font-mono text-neutral-200">{highText}</span>
        </span>
      </figcaption>
    </figure>
  );
}

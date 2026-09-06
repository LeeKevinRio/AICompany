import type { AnchorSource, KeyLevels } from "./keyLevels";

/**
 * Pure view-model builders for the two graphical forms the 關鍵價位參考 panel
 * renders (CEO 圖形化 items 1 & 2, 2026-09-06): the range-position gauge and
 * the price ladder. Nothing here computes a new number — every value is read
 * from `KeyLevels` (`computeKeyLevels`) and only *arranged* (clamped to a
 * track, sorted by price, expressed as a distance from the anchor) so the
 * JSX can stay a dumb renderer and the geometry can be unit-tested without a
 * DOM.
 *
 * Colour policy (risk S1 carried forward): neither form encodes 多/空 or
 * 好/壞 in colour. The gauge zones are three steps of ONE hue (sequential by
 * position, never red/green); the ladder's distance bars use the same single
 * hue on both sides of the anchor — direction is carried by which side of the
 * centre line the bar sits on and by the signed percentage label.
 */

/* ---------- 位階量表 ---------- */

export interface GaugeZoneBand {
  /** `low` / `mid` / `high` — same meaning as `classifyRangeZone`. */
  readonly zone: "low" | "mid" | "high";
  /** Track span in percent of width. */
  readonly fromPct: number;
  readonly toPct: number;
}

/** The three bands are the same thresholds `classifyRangeZone` uses (≤30 / ≥70). */
export const GAUGE_ZONE_BANDS: readonly GaugeZoneBand[] = [
  { zone: "low", fromPct: 0, toPct: 30 },
  { zone: "mid", fromPct: 30, toPct: 70 },
  { zone: "high", fromPct: 70, toPct: 100 },
];

/**
 * Marker offset along the track, clamped to [0, 100]. `rangePositionPct` is
 * already within that range by construction (close lies inside
 * [rangeLow, rangeHigh]), but the clamp is kept so a rounding artefact can
 * never push the marker off the track.
 */
export function gaugeMarkerLeftPct(rangePositionPct: number): number {
  if (!Number.isFinite(rangePositionPct)) return 0;
  return Math.min(100, Math.max(0, rangePositionPct));
}

/* ---------- 價位階梯 ---------- */

/** Which reference family a rung belongs to; drives the rung's tag label. */
export type LadderGroup = "target" | "anchor" | "close" | "pullback" | "stop";

export interface LadderRung {
  /** Stable id for React keys and tests. */
  readonly id:
    | "target-fixed"
    | "target-2r"
    | "anchor"
    | "close"
    | "ma20"
    | "ma60"
    | "recent-low60"
    | "stop-atr"
    | "stop-fixed";
  readonly group: LadderGroup;
  readonly price: number;
  /** (price / anchor − 1) × 100, signed. */
  readonly distancePct: number;
  /**
   * True for the one stop and the one target the panel's 大字 shows
   * (`stopSuggested` / `target2R`) — rendered as a small tag, so the reader can
   * connect the ladder row to the tile above without re-deriving the rule.
   */
  readonly isHeadline: boolean;
}

export interface LadderViewModel {
  /** Rungs sorted by price, highest first; ties keep the declaration order. */
  readonly rungs: readonly LadderRung[];
  /**
   * Largest |distancePct| across the rungs — the half-width scale every
   * distance bar is drawn against, so the longest bar fills its half-track.
   * 0 when every rung sits on the anchor (degenerate but possible).
   */
  readonly maxAbsDistancePct: number;
  readonly anchorPrice: number;
  readonly anchorSource: AnchorSource;
}

/**
 * Builds the ladder from `KeyLevels`. Null levels (short history) are simply
 * absent — the ladder never invents a rung, and the panel's own 「—」 notice
 * plus the 計算依據 list already explain the gaps.
 *
 * `close` is always a rung: when the anchor IS the close (not held / cost
 * unknown) the close rung is dropped rather than duplicated at 0% — the
 * anchor rung's label already says the anchor is the latest close.
 */
export function buildLadderViewModel(levels: KeyLevels, anchorSource: AnchorSource): LadderViewModel {
  const anchor = levels.anchorPrice;
  const dist = (price: number): number => (anchor > 0 ? (price / anchor - 1) * 100 : 0);

  const candidates: Array<Omit<LadderRung, "distancePct"> | null> = [
    { id: "target-fixed", group: "target", price: levels.targetFixedPct, isHeadline: false },
    { id: "target-2r", group: "target", price: levels.target2R, isHeadline: true },
    { id: "anchor", group: "anchor", price: anchor, isHeadline: false },
    anchorSource === "cost" ? { id: "close", group: "close", price: levels.close, isHeadline: false } : null,
    levels.ma20 !== null ? { id: "ma20", group: "pullback", price: levels.ma20, isHeadline: false } : null,
    levels.ma60 !== null ? { id: "ma60", group: "pullback", price: levels.ma60, isHeadline: false } : null,
    levels.recentLow60 !== null
      ? { id: "recent-low60", group: "pullback", price: levels.recentLow60, isHeadline: false }
      : null,
    levels.stopAtr !== null
      ? { id: "stop-atr", group: "stop", price: levels.stopAtr, isHeadline: levels.stopSuggested === levels.stopAtr }
      : null,
    {
      id: "stop-fixed",
      group: "stop",
      price: levels.stopFixedPct,
      // With ATR available and equal to the fixed stop, `stopSuggested` equals
      // both; the ATR rung already carries the tag, so avoid tagging twice.
      isHeadline: levels.stopAtr === null || levels.stopSuggested !== levels.stopAtr,
    },
  ];

  const rungs: LadderRung[] = candidates
    .filter((c): c is Omit<LadderRung, "distancePct"> => c !== null)
    .map((c) => ({ ...c, distancePct: dist(c.price) }));

  // Stable sort, highest price first.
  const sorted = rungs
    .map((rung, index) => ({ rung, index }))
    .sort((a, b) => b.rung.price - a.rung.price || a.index - b.index)
    .map((x) => x.rung);

  const maxAbsDistancePct = sorted.reduce((m, r) => Math.max(m, Math.abs(r.distancePct)), 0);

  return { rungs: sorted, maxAbsDistancePct, anchorPrice: anchor, anchorSource };
}

/**
 * Bar geometry for one rung, in percent of the full track width, with the
 * anchor line at 50%. A rung above the anchor extends rightwards from the
 * centre, one below extends leftwards; a rung on the anchor draws nothing.
 */
export function ladderBarGeometry(
  distancePct: number,
  maxAbsDistancePct: number,
): { leftPct: number; widthPct: number } {
  if (maxAbsDistancePct <= 0 || !Number.isFinite(distancePct) || distancePct === 0) {
    return { leftPct: 50, widthPct: 0 };
  }
  const half = Math.min(50, (Math.abs(distancePct) / maxAbsDistancePct) * 50);
  return distancePct > 0 ? { leftPct: 50, widthPct: half } : { leftPct: 50 - half, widthPct: half };
}

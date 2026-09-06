/**
 * Numeric-band classification for the 技術指標 at-a-glance layer (CEO 圖形化
 * item 3, 2026-09-06). Each function maps an indicator's latest value onto a
 * three-step band — `low` / `mid` / `high` — using only the textbook
 * threshold pairs stated beside each one (RSI 30/70, KD 20/80, %B 0/1,
 * |z| 2). The band is a statement about WHERE a number sits in its own scale,
 * nothing more: no direction, no 多/空, no action — the chip label wording
 * (`TechnicalIndicatorsPanel.tsx`) and the one-line legend rendered with the
 * chips say exactly that, and the colour mapping in the component is one hue
 * in three steps, never red/green (風控 2026-09-06 R2). A close-vs-MA relation
 * is deliberately NOT a band here (R3): it is binary, not a position on a
 * scale, and its inputs would cross two API payloads (R4).
 *
 * A `null` value (indicator insufficient) yields `null` — the chip is then
 * simply not drawn; the card's own insufficient-data note remains the single
 * explanation.
 */

export type IndicatorBand = "low" | "mid" | "high";

function bandBetween(value: number | null, lowMax: number, highMin: number): IndicatorBand | null {
  if (value === null || !Number.isFinite(value)) return null;
  if (value <= lowMax) return "low";
  if (value >= highMin) return "high";
  return "mid";
}

/** RSI(14): ≤30 low, ≥70 high. */
export function rsiBand(value: number | null): IndicatorBand | null {
  return bandBetween(value, 30, 70);
}

/** KD's K line: ≤20 low, ≥80 high. */
export function kdBand(kValue: number | null): IndicatorBand | null {
  return bandBetween(kValue, 20, 80);
}

/** Bollinger %B: <0 below the lower band, >1 above the upper band, else inside. */
export function percentBBand(value: number | null): IndicatorBand | null {
  if (value === null || !Number.isFinite(value)) return null;
  if (value < 0) return "low";
  if (value > 1) return "high";
  return "mid";
}

/**
 * Volume z-score (20-day): |z| ≥ 2 is the 偏離 band the backend's own
 * `anomaly` flag uses; sign decides low/high, magnitude below 2 is `mid`.
 */
export function volumeZBand(value: number | null): IndicatorBand | null {
  if (value === null || !Number.isFinite(value)) return null;
  if (value <= -2) return "low";
  if (value >= 2) return "high";
  return "mid";
}

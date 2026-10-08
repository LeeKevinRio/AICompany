import type { PositionFx, SummaryPositionItem } from "./types";

/** True when this FX rate came from the backup source (the existing `fx` rule). */
function isBackupFx(fx: PositionFx | null | undefined): boolean {
  return fx?.data_status === "backup";
}

/**
 * Whether the standing backup-FX badge on the FX contribution card is shown
 * (PR-RK5c, task RK-5, RK5-R3).
 *
 * True when any ok (valued) position has a backup-sourced `fx` or `fx_open`.
 * A position that is not ok put no rate into any figure, so it never counts;
 * a null rate (TWD row, no `opened_at`, X-3c mismatch row) is not backup.
 *
 * The `origin_status === "backup"` branch for cache-served rates belongs to
 * W11-5 (R5-10a): `PositionFx` has no such field today, so it is not here.
 */
export function hasBackupFx(positions: readonly SummaryPositionItem[]): boolean {
  return positions.some(
    ({ valuation }) =>
      valuation.status === "ok" && (isBackupFx(valuation.fx) || isBackupFx(valuation.fx_open)),
  );
}

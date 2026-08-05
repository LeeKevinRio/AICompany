/**
 * Shared "insufficient_data" panel. Extracted out of
 * `position/[symbol]/page.tsx` (Phase 8 FR-C1) — see `ErrorPanel.tsx` for
 * the sibling extraction and why.
 */
export function InsufficientPanel({ reason }: { reason: string | null }) {
  return (
    <p className="rounded-md border border-amber-800 bg-amber-950/40 px-4 py-3 text-sm text-amber-300">
      {reason ?? "資料不足，無法計算。"}
    </p>
  );
}

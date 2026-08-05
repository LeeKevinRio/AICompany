import { ApiError } from "../lib/api";

/**
 * Shared transient-failure panel. Extracted out of
 * `position/[symbol]/page.tsx` (Phase 8 FR-C1) so the new operation-summary
 * panel can render the same failure treatment as the technical-analysis and
 * advice-card sections it sits beside.
 */
export function ErrorPanel({ label, error }: { label: string; error: unknown }) {
  return (
    <p role="alert" className="rounded-md border border-red-900 bg-red-950/40 px-4 py-3 text-sm text-red-300">
      {label}：{error instanceof ApiError ? error.message : "未知錯誤"}
    </p>
  );
}

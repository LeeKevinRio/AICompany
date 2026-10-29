/**
 * The short `settings_fallback_notice` (ADR-0032 N-1／N-2／N-3; 風控 2026-10-29
 * N-156 字面定稿 第 2 項) beside the risk caps. The backend sends the sentence,
 * choosing among the three cases; this renders it as sent and returns nothing
 * for `null`.
 *
 * Standing: never inside a `<details>`, no truncation, no tooltip. At least
 * `text-sm` and in amber-200, which is lighter than `neutral-300` on the dark
 * surface. It is used at list level (`LimitsCheckList`, `RiskGaugeView`) and
 * once more in the position page's main view, outside the collapsed advice
 * card, beside the limit block.
 */
export function SettingsFallbackNoticeLine({
  text,
  className = "",
}: {
  text: string | null;
  className?: string;
}) {
  // `null` and an empty string both mean "no sentence": an empty box must
  // never stand in the main view looking like a disclosure.
  if (text === null || text === "") return null;
  return (
    <p
      className={`rounded-md border border-amber-800 bg-amber-950/40 px-3 py-2 text-sm text-amber-200 ${className}`.trim()}
    >
      {text}
    </p>
  );
}

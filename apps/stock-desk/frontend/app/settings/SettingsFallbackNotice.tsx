import type { SettingsFallbackView } from "../lib/types";

/**
 * The settings-page header block for sections that fell back to their defaults
 * (ADR-0032 Decision 2; 風控 2026-10-29 N-156 字面定稿 第 1 項).
 *
 * Title and every「標籤｜正文」item are the backend's, in the backend's order,
 * with the conditional items (F-3/F-4/F-5) already chosen there; this renders
 * them and composes nothing. It is a standing block: no `<details>`, no
 * dismiss control, no toast, tooltip, `role="status"` or `aria-live` region,
 * at `text-sm` and in amber like the widening confirmation, never lighter
 * than `neutral-300`.
 */
export function SettingsFallbackNotice({ fallback }: { fallback: SettingsFallbackView }) {
  const { notice } = fallback;
  return (
    <section
      aria-labelledby="settings-fallback-title"
      className="rounded-md border border-amber-700 bg-amber-950/50 px-4 py-3 text-sm text-amber-200"
    >
      <p id="settings-fallback-title" className="font-semibold">
        {notice.title}
      </p>
      <ol className="mt-2 space-y-2">
        {notice.items.map((item, i) => (
          <li key={i}>
            <span className="font-semibold">{item.label}</span>｜{item.body}
          </li>
        ))}
      </ol>
    </section>
  );
}

/**
 * The line directly under a fallback section's h2 (`section_markers`): at
 * least `text-sm`, amber, standing. The text is the backend's, verbatim.
 */
export function SectionFallbackMarker({ text }: { text: string | null }) {
  if (text === null) return null;
  return <p className="mt-2 text-sm text-amber-300">{text}</p>;
}

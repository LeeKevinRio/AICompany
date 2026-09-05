import { NON_REALTIME_NOTICE } from "../lib/adviceWording";
import { PAGE_LEVEL_DISCLOSURE_SECTION_INTRO, PAGE_LEVEL_DISCLOSURE_SECTION_TITLE } from "../lib/sectionTaglines";

/**
 * 頁級揭露區（個股頁減負 FR-3；風控預審 C1–C4）：`NON_REALTIME_NOTICE` 在整頁只
 * 完整出現一次的唯一主位置。
 *
 * - C1: rendered directly under the page H1, above the fold, never collapsed,
 *   ≥ text-sm / ≥ neutral-400.
 * - C2: everything here is a static constant — this component takes no props
 *   and reads no query state, so it can never disappear on a failed or
 *   pending fetch (the exact moment the notice matters most).
 * - C3: `operationSummary.ts` §2 八要素 relies on this block for the
 *   non-realtime element; `componentWordingScan.test.ts` guards that
 *   `page.tsx` renders it and that it renders the notice.
 * - C4: the merge is approved for `NON_REALTIME_NOTICE` only — do not add
 *   other disclosures here.
 */
export function PageDisclosureSection() {
  return (
    <section
      aria-label={PAGE_LEVEL_DISCLOSURE_SECTION_TITLE}
      className="mt-4 rounded-lg border border-neutral-800 bg-neutral-900/40 px-4 py-3"
    >
      <h2 className="text-sm font-semibold text-neutral-300">{PAGE_LEVEL_DISCLOSURE_SECTION_TITLE}</h2>
      <p className="mt-1 text-sm text-neutral-400">{PAGE_LEVEL_DISCLOSURE_SECTION_INTRO}</p>
      <p className="mt-1 text-sm text-neutral-400">{NON_REALTIME_NOTICE}</p>
    </section>
  );
}

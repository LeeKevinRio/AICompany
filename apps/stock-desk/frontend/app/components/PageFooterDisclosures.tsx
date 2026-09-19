import type { BasisItem } from "../position/[symbol]/KeyLevelsPanel";
import { PAGE_FOOTER_DISCLOSURES_INTRO, PAGE_FOOTER_DISCLOSURES_TITLE } from "../lib/footerDisclosureWording";

/**
 * 頁尾揭露區（CEO 裁定 2026-09-06「揭露句下沉頁尾」；
 * `work/stock-desk-揭露下沉頁尾-CEO裁定與方案.md`）。
 *
 * The single page-bottom home for every disclosure / qualifier sentence the
 * position page used to render inside its own sections. Rules of this block:
 * - COLLAPSED BY DEFAULT (CEO 第三次裁定 2026-09-19「頁尾那段也收成詳細」,
 *   `work/stock-desk-一眼一句簡化-派工單.md` §5, overriding the 2026-09-06
 *   「常駐不摺疊」 ruling and 風控 L2's no-collapse clause): the whole block
 *   sits inside one `<details>` whose `<summary>` is the block title itself
 *   (`PAGE_FOOTER_DISCLOSURES_TITLE`, an existing pinned constant -- no new
 *   wording). Everything inside is still rendered in full on expand: no
 *   clipping, truncation, lazy mounting or virtualisation (the remaining L2
 *   constructs stay forbidden and the scan test still enforces them). The
 *   static groups stay unconditional (資料來源 is a constant; the other groups
 *   appear when their section's data exists).
 * - VERBATIM: every sentence arrives here unchanged from its pinned constant
 *   or builder; this component only arranges them. Formula items
 *   (`BasisItem`) keep their monospace formula lines + qualifier pairing.
 * - GROUPED by source section, in page order, each group titled with the
 *   same heading its section uses, so a reader following an in-section
 *   pointer sentence lands on the right group.
 * - Size floor is text-xs / neutral-400: the CEO ruling lowers the previous
 *   text-sm floor, 風控 L1 keeps the colour at neutral-400 (neutral-500 fails
 *   WCAG AA on this surface). Guarded by `componentWordingScan.test.ts`
 *   together with the L2 scan.
 */

/** A plain sentence, a formula item, or a sub-heading inside a group (e.g. 「計算依據（逐項揭露）」). */
export type FooterItem = string | BasisItem | { readonly heading: string };

export interface FooterGroup {
  /** Same heading as the source section on the page. */
  readonly title: string;
  readonly items: readonly FooterItem[];
}

function isBasisItem(item: FooterItem): item is BasisItem {
  return typeof item !== "string" && "formula" in item;
}

function isHeading(item: FooterItem): item is { readonly heading: string } {
  return typeof item !== "string" && "heading" in item;
}

export function PageFooterDisclosures({ groups }: { groups: readonly FooterGroup[] }) {
  const visible = groups.filter((g) => g.items.length > 0);
  return (
    <footer
      // Inside <main> a <footer> carries no landmark role; role="region" keeps it reachable by AT (qa-reviewer).
      role="region"
      aria-label={PAGE_FOOTER_DISCLOSURES_TITLE}
      className="mt-10 rounded-lg border border-neutral-800 bg-neutral-900/40 px-4 py-4"
    >
      {/*
        Same `<details>` idiom as every section above (一眼一句 視覺規範 B.3): chevron + summary text, native marker suppressed.
        `print-expand` (globals.css): 風控 F-3 -- printed / saved-as-PDF output carries the whole block even while collapsed on screen.
      */}
      <details className="group print-expand">
        <summary className="flex cursor-pointer list-none items-center gap-1.5 [&::-webkit-details-marker]:hidden">
          <span aria-hidden="true" className="inline-block text-xs text-neutral-400 transition-transform duration-150 group-open:rotate-90">
            ▸
          </span>
          <h2 className="text-sm font-semibold text-neutral-300">{PAGE_FOOTER_DISCLOSURES_TITLE}</h2>
        </summary>
        <p className="mt-2 text-xs text-neutral-400">{PAGE_FOOTER_DISCLOSURES_INTRO}</p>
        <div className="mt-3 space-y-4">
          {visible.map((group) => (
            <section key={group.title} aria-label={group.title}>
              <h3 className="text-xs font-semibold text-neutral-400">{group.title}</h3>
              <ul className="mt-1 list-disc space-y-1 pl-5 text-xs text-neutral-400">
                {group.items.map((item, i) =>
                  isHeading(item) ? (
                    <li key={i} className="list-none -ml-5 pt-1 text-xs font-semibold text-neutral-400">
                      {item.heading}
                    </li>
                  ) : isBasisItem(item) ? (
                    // 算式行與限定語同一 <li>、同字級同顏色；等寬字型只在算式行（沿用 P2 落地條件）。
                    <li key={i} className="text-xs text-neutral-400">
                      {item.formula.map((line, j) => (
                        <span key={j} className="block whitespace-pre-wrap font-mono text-xs text-neutral-400">
                          {line}
                        </span>
                      ))}
                      {item.qualifier !== null && <span className="block text-xs text-neutral-400">{item.qualifier}</span>}
                    </li>
                  ) : (
                    <li key={i} className="text-xs text-neutral-400">
                      {item}
                    </li>
                  ),
                )}
              </ul>
            </section>
          ))}
        </div>
      </details>
    </footer>
  );
}

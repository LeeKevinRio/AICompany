import type { ReactNode } from "react";
import { disclosureAriaLabel } from "../lib/inventoryWording";

/**
 * Collapsible block used for 新增持倉 and CSV 匯入 (visual spec 3.3). The
 * content stays in the DOM while collapsed (`hidden`), so `aria-controls`
 * always resolves and form state survives a collapse. Controlled: the page
 * owns `open`.
 */
export function DisclosureSection({
  id,
  title,
  open,
  onToggle,
  children,
}: {
  id: string;
  title: string;
  open: boolean;
  onToggle: () => void;
  children: ReactNode;
}) {
  const contentId = `${id}-content`;
  return (
    <section id={id} className="max-w-3xl scroll-mt-4 rounded-lg border border-neutral-800">
      <h2>
        <button
          type="button"
          aria-expanded={open}
          aria-controls={contentId}
          aria-label={disclosureAriaLabel(title)}
          onClick={onToggle}
          className="group flex min-h-11 w-full items-center justify-between rounded-lg px-5 py-3 text-left text-lg font-semibold text-neutral-100 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-sky-400"
        >
          <span>{title}</span>
          <span
            aria-hidden="true"
            className="inline-block text-xs text-neutral-400 transition-transform duration-150 group-aria-expanded:rotate-90 motion-reduce:transition-none"
          >
            ▸
          </span>
        </button>
      </h2>
      <div id={contentId} hidden={!open} className="p-5 pt-0">
        {children}
      </div>
    </section>
  );
}

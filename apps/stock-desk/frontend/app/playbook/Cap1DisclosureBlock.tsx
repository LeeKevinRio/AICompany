import { useId } from "react";
import type { PlaybookCap1Disclosure } from "../lib/types";

/**
 * 排程台 x 第 1 條 disclosure block (N-155, ADR-0031; 風控 2026-10-28 #68 裁決
 * and its supplement, section 3).
 *
 * This component renders the backend-sent `title` and then each entry of
 * `lines`, in the order received, and nothing else. It holds no wording of its
 * own, converts nothing, parses nothing and joins no strings: every sentence
 * (numbers included) is final when it arrives, and the verbatim text is
 * guarded on the backend side. `Cap1DisclosureBlock.test.ts` pins this from
 * outside with sentinel strings and a source scan (F-1, F-2).
 *
 * Presentation (ruling): always on screen, never collapsed, no tooltip, no
 * dismiss control. `text-sm` on `neutral-300` like the section-6 summary block
 * it must not be weaker than, with a neutral border and no warning colour or
 * icon: this is a statement of fact about the rule set, not a verdict.
 *
 * Whether it appears does not depend on the mode or on any value inside the
 * disclosure (F-4): the only reason to render nothing is that the backend did
 * not send the field at all (an older backend), and then nothing is written in
 * its place. Where it appears is decided by the caller, exactly once per
 * screen (`cap1DisclosureHost` in `lib/playbookView.ts`).
 */
export function Cap1DisclosureBlock({
  disclosure,
  headingLevel,
}: {
  disclosure: PlaybookCap1Disclosure | undefined;
  headingLevel: 2 | 3;
}) {
  const headingId = useId();
  if (disclosure === undefined) return null;
  const Heading = headingLevel === 2 ? "h2" : "h3";

  return (
    <section
      aria-labelledby={headingId}
      className="mt-4 space-y-1 rounded-md border border-neutral-800 bg-neutral-900/60 px-3 py-2"
    >
      <Heading id={headingId} className="text-sm font-medium text-neutral-200">
        {disclosure.title}
      </Heading>
      {disclosure.lines.map((line, i) => (
        <p key={i} className="text-sm text-neutral-300">
          {line}
        </p>
      ))}
    </section>
  );
}

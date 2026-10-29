/**
 * N-159 guard: the EMERGENCY_EXIT dialog must not be a DOM descendant of
 * `ModeStatusBar`'s `sticky ... backdrop-blur` strip.
 *
 * Why: an ancestor with `backdrop-filter` becomes the containing block of its
 * `position: fixed` descendants, so a `fixed inset-0` overlay rendered inside
 * the strip was clipped to the strip's own height (~86px), its panel was pushed
 * above the viewport (Step 2 heading and first fact cut off, Step 3 heading
 * invisible) and the rest of the page was not dimmed.
 *
 * This repo has no jsdom / @testing-library (see `vitest.config.ts`), and the
 * dialog only mounts after a click, so the guard is a source-structure scan:
 * the dialog root must be the first argument of `createPortal(..., document.body)`
 * and nothing outside that call may use `fixed` positioning. Layout itself
 * (overlay covers the viewport, panel inside it, still true after scrolling) is
 * qa-e2e's real-browser check.
 */

import { readFileSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import { describe, expect, it } from "vitest";

const here = dirname(fileURLToPath(import.meta.url));

function readSource(file: string): string {
  return readFileSync(resolve(here, "..", file), "utf-8");
}

/** Drop block and line comments so prose cannot satisfy or break a scan. */
function stripComments(source: string): string {
  return source.replace(/\/\*[\s\S]*?\*\//g, "").replace(/^\s*\/\/.*$/gm, "");
}

const control = stripComments(readSource("EmergencyExitControl.tsx"));
const statusBar = stripComments(readSource("ModeStatusBar.tsx"));

/** Index of the matching closing paren for the `(` at `openIndex`. */
function matchingParen(source: string, openIndex: number): number {
  let depth = 0;
  for (let i = openIndex; i < source.length; i += 1) {
    if (source[i] === "(") depth += 1;
    if (source[i] === ")") {
      depth -= 1;
      if (depth === 0) return i;
    }
  }
  throw new Error("unbalanced parentheses");
}

function portalCall(): string {
  const start = control.indexOf("createPortal(");
  expect(start).toBeGreaterThan(-1);
  const open = start + "createPortal".length;
  return control.slice(open, matchingParen(control, open) + 1);
}

describe("EmergencyExitControl dialog is portalled out of ModeStatusBar (N-159)", () => {
  it("imports createPortal from react-dom and targets document.body", () => {
    expect(control).toMatch(/import\s*\{\s*createPortal\s*\}\s*from\s*"react-dom"/);
    expect(portalCall()).toMatch(/,\s*document\.body\s*,?\s*\)$/);
  });

  it("renders the dialog root (role=dialog, aria-modal) inside the portal call", () => {
    const portal = portalCall();
    expect(portal).toContain('role="dialog"');
    expect(portal).toContain('aria-modal="true"');
    expect(portal).toContain('aria-label="全部出清確認"');
    // Exactly one dialog root in the whole file, and it is the portalled one.
    expect(control.match(/role="dialog"/g)).toHaveLength(1);
  });

  it("uses fixed positioning only inside the portal, never in the inline tree", () => {
    const portal = portalCall();
    const outside = control.replace(portal, "");
    expect(outside).not.toMatch(/\bfixed\b/);
    expect(portal).toMatch(/\bfixed inset-0\b/);
  });

  it("only mounts the portal after the client has mounted (SSR safe)", () => {
    expect(control).toContain("useSyncExternalStore");
    expect(control).toMatch(/isClientMounted\s*&&\s*createPortal\(/);
  });

  it("keeps the panel inside the viewport and scrollable when the viewport is short", () => {
    const portal = portalCall();
    expect(portal).toContain("max-h-[calc(100vh-2rem)]");
    expect(portal).toContain("overflow-y-auto");
  });

  it("ModeStatusBar still embeds the control but renders no dialog or fixed layer itself", () => {
    expect(statusBar).toContain("<EmergencyExitControl");
    expect(statusBar).not.toContain('role="dialog"');
    expect(statusBar).not.toMatch(/\bfixed\b/);
  });
});

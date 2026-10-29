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
 * and nothing outside that call may use `fixed` positioning. The focus
 * management / Esc / focus-trap tests below are scans of the same kind: they
 * catch removal or rewiring of those pieces (ref on the headings and trigger,
 * the step -> idle focus return, Esc routed through cancel and locked while
 * pending, the trap helper on the dialog root) but not live focus behaviour,
 * which needs a real browser (qa-e2e). Layout itself
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

/** `fixed` as a whole class token (does not match `table-fixed`, `fixed-x`). */
const FIXED_CLASS = /(?<![\w-])fixed(?![\w-])/;

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
    expect(outside).not.toMatch(FIXED_CLASS);
    expect(portal).toMatch(/(?<![\w-])fixed inset-0(?![\w-])/);
  });

  it("keeps the overlay at z-50, above every other fixed layer (same as the other dialogs)", () => {
    expect(portalCall()).toMatch(/(?<![\w-])z-50(?![\w-])/);
  });

  it("only mounts the portal after the client has mounted (SSR safe)", () => {
    expect(control).toMatch(
      /useSyncExternalStore\(\s*subscribeNoop,\s*\(\)\s*=>\s*true,\s*\(\)\s*=>\s*false,?\s*\)/,
    );
    expect(control).toMatch(/isClientMounted\s*&&\s*createPortal\(/);
  });

  it("keeps the panel inside the viewport and scrollable when the viewport is short", () => {
    const portal = portalCall();
    // 100vh is the fallback; 100dvh (mobile browser chrome) wins where supported.
    // `supports-[...]` is emitted after the base utility, so the cascade order
    // is deterministic (two bare max-h utilities would be sorted by value).
    expect(portal).toContain("max-h-[calc(100vh-2rem)]");
    expect(portal).toContain("supports-[height:100dvh]:max-h-[calc(100dvh-2rem)]");
    expect(portal).toContain("overflow-y-auto");
  });

  it("ModeStatusBar still embeds the control but renders no dialog or fixed layer itself", () => {
    expect(statusBar).toContain("<EmergencyExitControl");
    expect(statusBar).not.toContain('role="dialog"');
    expect(statusBar).not.toMatch(FIXED_CLASS);
  });
});

describe("EmergencyExitControl focus management, Esc and focus trap (N-159 a11y)", () => {
  it("moves focus to the step heading on every step (not to a checkbox)", () => {
    // Both step headings carry the ref and are programmatically focusable.
    expect(control.match(/<h2\s+ref=\{headingRef\}\s+tabIndex=\{-1\}/g)).toHaveLength(2);
    expect(control).toMatch(/if \(step !== "idle"\) \{\s*headingRef\.current\?\.focus\(\);/);
    expect(control).toMatch(/\}, \[step\]\);/);
  });

  it("returns focus to the 全部出清 trigger after any close, via the step -> idle transition", () => {
    expect(control).toMatch(/<button\s+ref=\{triggerRef\}/);
    expect(control).toMatch(/else if \(wasOpen\) \{\s*triggerRef\.current\?\.focus\(\);/);
    // Every close path (取消, Esc, successful submit) goes through setStep("idle").
    expect(control).toMatch(/onSuccess: \(\) => setStep\("idle"\)/);
  });

  it("closes on Esc through cancel(), locked while submitting, and never calls the submit", () => {
    const listener = control.slice(control.indexOf("function handleKeyDown(event: KeyboardEvent)"));
    const body = listener.slice(0, listener.indexOf("document.addEventListener"));
    expect(body).toMatch(/event\.key === "Escape"/);
    expect(body).toContain("!mutation.isPending");
    expect(body).toContain("cancelRef.current()");
    expect(body).not.toContain("mutate");
    expect(body).not.toContain("submit");
    // The listener is only registered while the dialog is open, and re-bound
    // when the step or the pending state changes.
    expect(control).toMatch(/if \(step === "idle"\) return;/);
    expect(control).toMatch(/\[step, mutation\.isPending\]/);
    expect(control).toContain("cancelRef.current = cancel;");
    expect(control).toContain('document.addEventListener("keydown", handleKeyDown)');
    expect(control).toContain('document.removeEventListener("keydown", handleKeyDown)');
  });

  it("traps Tab inside the dialog with the shared trapTabTarget helper", () => {
    expect(control).toContain('from "../lib/focusTrap"');
    expect(control).toContain("trapTabTarget(");
    expect(control).toMatch(/ref=\{dialogRef\}[\s\S]*?onKeyDown=\{handleDialogKeyDown\}/);
    // The dialog root is the element that carries the trap.
    const portal = portalCall();
    expect(portal.indexOf("ref={dialogRef}")).toBeLessThan(portal.indexOf('role="dialog"'));
  });
});

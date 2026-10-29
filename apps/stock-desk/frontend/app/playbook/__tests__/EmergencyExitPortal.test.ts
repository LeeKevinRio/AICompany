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

/** Body of `function <name>(...) { ... }` (brace-balanced), comments already stripped. */
function functionBody(name: string): string {
  const start = control.indexOf(`function ${name}(`);
  expect(start).toBeGreaterThan(-1);
  const open = control.indexOf("{", control.indexOf(")", start));
  let depth = 0;
  for (let i = open; i < control.length; i += 1) {
    if (control[i] === "{") depth += 1;
    if (control[i] === "}") {
      depth -= 1;
      if (depth === 0) return control.slice(open, i + 1);
    }
  }
  throw new Error("unbalanced braces");
}

/** The Step 3 (`final`) subtree: from its heading to the end of the portal call. */
function finalStepSource(): string {
  const portal = portalCall();
  const start = portal.indexOf('step === "final"');
  expect(start).toBeGreaterThan(-1);
  return portal.slice(start);
}

describe("EmergencyExitControl keeps focus inside the dialog while submitting (N-163)", () => {
  it("Step 3 buttons use aria-disabled while pending, never the native disabled attribute", () => {
    const finalStep = finalStepSource();
    // Native `disabled` on the focused button drops focus to <body>; the next
    // Tab then leaves the dialog for the page header link behind the overlay.
    expect(finalStep).not.toMatch(/(?<![-\w])disabled=\{/);
    expect(finalStep).not.toMatch(/(?<![-\w:])disabled(?![-\w])(?=[\s>/])/);
    expect(control).not.toMatch(/(?<![-\w])disabled=\{mutation\.isPending\}/);
    // Both 取消 and 確認送出 carry aria-disabled bound to the pending state.
    // `|| undefined` omits the attribute when idle, so only "true" is ever
    // rendered and the `aria-disabled:` variants (`[aria-disabled=true]`) match.
    expect(finalStep.match(/aria-disabled=\{mutation\.isPending \|\| undefined\}/g)).toHaveLength(2);
  });

  it("styles the aria-disabled state (cursor, opacity, no hover highlight) on both buttons", () => {
    const finalStep = finalStepSource();
    expect(finalStep.match(/aria-disabled:cursor-not-allowed/g)).toHaveLength(2);
    expect(finalStep.match(/aria-disabled:opacity-50/g)).toHaveLength(2);
    expect(finalStep.match(/aria-disabled:hover:bg-/g)).toHaveLength(2);
    // The old `disabled:` variants would silently stop applying; none may remain here.
    expect(finalStep).not.toMatch(/(?<![-\w])disabled:/);
  });

  it("refuses to submit again while pending or locked (a focused aria-disabled button can still be activated)", () => {
    const body = functionBody("submit");
    const guard = "if (submittingRef.current || mutation.isPending) return;";
    expect(body.indexOf(guard)).toBeGreaterThan(-1);
    expect(body.indexOf(guard)).toBeLessThan(body.indexOf("mutation.mutate("));
  });

  it("refuses to cancel while pending or locked, whatever triggers it", () => {
    const body = functionBody("cancel");
    const guard = "if (submittingRef.current || mutation.isPending) return;";
    expect(body.indexOf(guard)).toBeGreaterThan(-1);
    expect(body.indexOf(guard)).toBeLessThan(body.indexOf('setStep("idle")'));
    // Esc stays locked on its own as well (asserted in the Esc test above).
  });

  it("holds a synchronous ref lock across the mutate call and releases it on success and failure", () => {
    // `isPending` only flips after a render, so a second activation in the same
    // tick would otherwise fire a second irreversible POST.
    expect(control).toContain("const submittingRef = useRef(false);");
    const body = functionBody("submit");
    const mutate = body.indexOf("mutation.mutate(");
    expect(mutate).toBeGreaterThan(-1);
    const check = body.indexOf("submittingRef.current ||");
    const acquire = body.indexOf("submittingRef.current = true;");
    expect(check).toBeGreaterThan(-1);
    expect(acquire).toBeGreaterThan(check);
    expect(acquire).toBeLessThan(mutate);
    // Released in onSettled (runs for success and failure), never only in onSuccess,
    // so a failed submit can be retried.
    const options = body.slice(mutate);
    expect(options).toMatch(/onSettled:\s*\(\)\s*=>\s*\{\s*submittingRef\.current = false;\s*\}/);
    expect(control.match(/submittingRef\.current = false/g)).toHaveLength(1);
    expect(control.match(/submittingRef\.current = true/g)).toHaveLength(1);
  });

  it("focuses the clicked submit button before the request starts (browsers that do not focus on click)", () => {
    const body = functionBody("submit");
    expect(body).toContain("event.currentTarget.focus()");
    expect(body.indexOf("event.currentTarget.focus()")).toBeLessThan(body.indexOf("mutation.mutate("));
    expect(control).toMatch(/onClick=\{submit\}/);
  });

  it("does not move or drop focus when the pending state flips (failure keeps focus on 確認送出)", () => {
    // The focus effect is keyed on `step` only; pending / error never re-run it,
    // and nothing in the file blurs or re-targets focus on those transitions.
    expect(control).toMatch(/\}, \[step\]\);/);
    expect(control).not.toContain(".blur(");
    expect(control.match(/\.focus\(\)/g)).toHaveLength(4);
  });
});

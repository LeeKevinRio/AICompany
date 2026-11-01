/**
 * N-159 guard: the EMERGENCY_EXIT dialog must not be a DOM descendant of
 * `ModeStatusBar`'s sticky strip — and, since the Q14 restructure (tech-architect
 * FE-C10/FE-C11, VETO-2), not of anything gated by `today.isSuccess` either.
 *
 * Why the portal: an ancestor with `backdrop-filter` becomes the containing block
 * of its `position: fixed` descendants, so a `fixed inset-0` overlay rendered
 * inside the strip was clipped to the strip's own height (~86px), its panel was
 * pushed above the viewport and the rest of the page was not dimmed.
 *
 * This repo has no jsdom / @testing-library (see `vitest.config.ts`), and the
 * dialog only mounts after a click, so the guard is a source-structure scan:
 * the dialog root must be the first argument of `createPortal(..., document.body)`
 * and nothing outside that call may use `fixed` positioning. The focus
 * management / Esc / focus-trap tests below are scans of the same kind: they
 * catch removal or rewiring of those pieces (ref on the heading and trigger, the
 * close -> trigger focus return, Esc routed through cancel and locked while
 * pending, the trap helper on the dialog root) but not live focus behaviour,
 * which needs a real browser (qa-e2e). Layout itself (overlay covers the
 * viewport, panel inside it, still true after scrolling) is qa-e2e's check.
 *
 * Structure after the restructure: `EmergencyExitDialog.tsx` (dialog),
 * `useEmergencyExitFlow.ts` (observer, lock, open/close, receipt, focus return),
 * `ExitTriggerButton.tsx` (the trigger), `page.tsx` (mounts the dialog).
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

const dialog = stripComments(readSource("EmergencyExitDialog.tsx"));
const flow = stripComments(readSource("useEmergencyExitFlow.ts"));
const trigger = stripComments(readSource("ExitTriggerButton.tsx"));
const statusBar = stripComments(readSource("ModeStatusBar.tsx"));
const page = stripComments(readSource("page.tsx"));

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
  const start = dialog.indexOf("createPortal(");
  expect(start).toBeGreaterThan(-1);
  const open = start + "createPortal".length;
  return dialog.slice(open, matchingParen(dialog, open) + 1);
}

describe("EmergencyExitDialog is portalled out of ModeStatusBar (N-159)", () => {
  it("imports createPortal from react-dom and targets document.body", () => {
    expect(dialog).toMatch(/import\s*\{\s*createPortal\s*\}\s*from\s*"react-dom"/);
    expect(portalCall()).toMatch(/,\s*document\.body\s*,?\s*\)$/);
  });

  it("renders the dialog root (role=dialog, aria-modal) inside the portal call", () => {
    const portal = portalCall();
    expect(portal).toContain('role="dialog"');
    expect(portal).toContain('aria-modal="true"');
    expect(portal).toContain('aria-label="全部出清確認"');
    // Exactly one dialog root in the whole file, and it is the portalled one.
    expect(dialog.match(/role="dialog"/g)).toHaveLength(1);
  });

  it("uses fixed positioning only inside the portal, never in the inline tree", () => {
    const portal = portalCall();
    const outside = dialog.replace(portal, "");
    expect(outside).not.toMatch(FIXED_CLASS);
    expect(portal).toMatch(/(?<![\w-])fixed inset-0(?![\w-])/);
  });

  it("keeps the overlay at z-50, above every other fixed layer (same as the other dialogs)", () => {
    expect(portalCall()).toMatch(/(?<![\w-])z-50(?![\w-])/);
  });

  it("only mounts the portal after the client has mounted (SSR safe)", () => {
    expect(dialog).toMatch(
      /useSyncExternalStore\(\s*subscribeNoop,\s*\(\)\s*=>\s*true,\s*\(\)\s*=>\s*false,?\s*\)/,
    );
    expect(dialog).toMatch(/isClientMounted\s*&&\s*createPortal\(/);
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

  it("ModeStatusBar hosts only the trigger it is handed: no dialog, no fixed layer, no exit flow import", () => {
    expect(statusBar).toContain("{trigger}");
    expect(statusBar).not.toContain('role="dialog"');
    expect(statusBar).not.toMatch(FIXED_CLASS);
    expect(statusBar).not.toMatch(/EmergencyExit|useEmergencyExit|useMutation/);
    expect(statusBar).not.toMatch(/createPortal/);
  });

  it("the page mounts the dialog on isOpen alone, as a sibling after <main>, outside any today.* condition (FE-C11)", () => {
    expect(page.match(/<EmergencyExitDialog/g)).toHaveLength(1);
    const at = page.indexOf("<EmergencyExitDialog");
    const gate = page.slice(page.lastIndexOf("{", at), at);
    expect(gate.replace(/\s+/g, " ")).toBe("{flow.isOpen && ( ");
    expect(at).toBeGreaterThan(page.indexOf("</main>"));
    // Nothing between </main> and the dialog is conditional on /today.
    expect(page.slice(page.indexOf("</main>"), at)).not.toMatch(/today\./);
  });
});

describe("EmergencyExitDialog focus management, Esc and focus trap (N-159 a11y)", () => {
  it("moves focus to the step heading on every step (not to a checkbox)", () => {
    // One heading node serves both steps and is programmatically focusable.
    expect(dialog.match(/<h2\s+ref=\{headingRef\}\s+tabIndex=\{-1\}/g)).toHaveLength(1);
    expect(dialog).toMatch(/useEffect\(\(\) => \{\s*headingRef\.current\?\.focus\(\);\s*\}, \[state\.step\]\);/);
  });

  it("returns focus to the trigger that exists now after any close, via isOpen true -> false (FE-C19)", () => {
    expect(trigger).toMatch(/<button\s+ref=\{buttonRef\}/);
    expect(flow).toMatch(
      /if \(wasOpenRef\.current && !isOpen && trigger !== null && document\.activeElement !== trigger\) \{\s*trigger\.focus\(\{ preventScroll: true \}\);/,
    );
    expect(flow).toMatch(/\}, \[isOpen\]\);/);
    // Every close path (取消, Esc, successful submit) goes through setIsOpen(false).
    expect(flow.match(/setIsOpen\(false\)/g)).toHaveLength(2);
    expect(flow).toMatch(/onSuccess: \(\) => \{\s*setIsOpen\(false\);/);
  });

  it("closes on Esc through cancel(), locked while submitting, and never calls the submit", () => {
    const listener = dialog.slice(dialog.indexOf("function handleKeyDown(event: KeyboardEvent)"));
    const body = listener.slice(0, listener.indexOf("document.addEventListener"));
    expect(body).toMatch(/event\.key === "Escape"/);
    expect(body).toContain("!isPending");
    expect(body).toContain("cancelRef.current()");
    expect(body).not.toContain("mutate");
    expect(body).not.toContain("submit");
    // The listener lives as long as the dialog and is re-bound when the pending
    // state changes (the dialog itself only exists while open).
    expect(dialog).toMatch(/\}, \[isPending\]\);/);
    expect(dialog).toContain("cancelRef.current = cancel;");
    expect(dialog).toContain('document.addEventListener("keydown", handleKeyDown)');
    expect(dialog).toContain('document.removeEventListener("keydown", handleKeyDown)');
  });

  it("traps Tab inside the dialog with the shared trapTabTarget helper", () => {
    expect(dialog).toContain('from "../lib/focusTrap"');
    expect(dialog).toContain("trapTabTarget(");
    expect(dialog).toMatch(/ref=\{dialogRef\}[\s\S]*?onKeyDown=\{handleDialogKeyDown\}/);
    // The dialog root is the element that carries the trap.
    const portal = portalCall();
    expect(portal.indexOf("ref={dialogRef}")).toBeLessThan(portal.indexOf('role="dialog"'));
  });
});

/** Body of `function <name>(...) { ... }` (brace-balanced) in `source`, comments already stripped. */
function functionBody(source: string, name: string): string {
  const start = source.indexOf(`function ${name}(`);
  expect(start).toBeGreaterThan(-1);
  const open = source.indexOf("{", source.indexOf(")", start));
  let depth = 0;
  for (let i = open; i < source.length; i += 1) {
    if (source[i] === "{") depth += 1;
    if (source[i] === "}") {
      depth -= 1;
      if (depth === 0) return source.slice(open, i + 1);
    }
  }
  throw new Error("unbalanced braces");
}

/** The Step 3 (`final`) subtree: from its branch to the end of the portal call. */
function finalStepSource(): string {
  const portal = portalCall();
  const start = portal.indexOf('state.step === "final"');
  expect(start).toBeGreaterThan(-1);
  return portal.slice(start);
}

describe("EmergencyExitDialog keeps focus inside the dialog while submitting (N-163)", () => {
  it("Step 3 buttons use aria-disabled while pending, never the native disabled attribute", () => {
    const finalStep = finalStepSource();
    // Native `disabled` on the focused button drops focus to <body>; the next
    // Tab then leaves the dialog for the page header link behind the overlay.
    expect(finalStep).not.toMatch(/(?<![-\w])disabled=\{/);
    expect(finalStep).not.toMatch(/(?<![-\w:])disabled(?![-\w])(?=[\s>/])/);
    expect(dialog).not.toMatch(/(?<![-\w])disabled=\{isPending\}/);
    // Both 取消 and 確認送出 carry aria-disabled bound to the pending state.
    // `|| undefined` omits the attribute when idle, so only "true" is ever
    // rendered and the `aria-disabled:` variants (`[aria-disabled=true]`) match.
    expect(finalStep.match(/aria-disabled=\{isPending \|\| undefined\}/g)).toHaveLength(2);
  });

  it("styles the aria-disabled state (cursor, opacity, no hover highlight) on both buttons", () => {
    const finalStep = finalStepSource();
    expect(finalStep.match(/aria-disabled:cursor-not-allowed/g)).toHaveLength(2);
    expect(finalStep.match(/aria-disabled:opacity-50/g)).toHaveLength(2);
    expect(finalStep.match(/aria-disabled:hover:bg-/g)).toHaveLength(2);
    // The old `disabled:` variants would silently stop applying; none may remain here.
    expect(finalStep).not.toMatch(/(?<![-\w])disabled:/);
  });

  it("「我已閱讀，繼續」also keeps focus when a sentence swap switches it off (AC-46: activeElement is not moved)", () => {
    // A focused native `disabled` button loses focus; the swap (R-3) can happen
    // while the user is on it.
    expect(dialog).not.toMatch(/(?<![-\w])disabled=\{/);
    expect(dialog).not.toMatch(/(?<![-\w:])disabled(?![-\w])(?=[\s>/])/);
    expect(dialog).toMatch(/aria-disabled=\{!allConfirmed \|\| undefined\}/);
    // The handler refuses to act until every sentence is ticked.
    expect(functionBody(dialog, "advance")).toMatch(/if \(!allConfirmed\) return;/);
  });

  it("refuses to submit again while pending or locked (a focused aria-disabled button can still be activated)", () => {
    // Dialog side: the plan is computed first and an `ignore` returns before anything else.
    const dialogSubmit = functionBody(dialog, "submit");
    expect(dialogSubmit).toContain("planSubmit(state, Date.now(), lockRef.current || isPending)");
    expect(dialogSubmit.indexOf('plan === "ignore"')).toBeLessThan(dialogSubmit.indexOf("onSubmit()"));
    // Page side: the same guard sits in front of the lock and the request.
    const flowSubmit = functionBody(flow, "submit");
    const guard = "if (lockRef.current || mutation.isPending) return;";
    expect(flowSubmit.indexOf(guard)).toBeGreaterThan(-1);
    expect(flowSubmit.indexOf(guard)).toBeLessThan(flowSubmit.indexOf("mutation.mutate("));
  });

  it("refuses to cancel while pending or locked, whatever triggers it", () => {
    const cancel = functionBody(dialog, "cancel");
    const guard = "if (lockRef.current || isPending) return;";
    expect(cancel.indexOf(guard)).toBeGreaterThan(-1);
    expect(cancel.indexOf(guard)).toBeLessThan(cancel.indexOf("onClose()"));
    // The page's close() holds the same guard (a second line of defence).
    const close = functionBody(flow, "close");
    expect(close.indexOf("if (lockRef.current || mutation.isPending) return;")).toBeLessThan(
      close.indexOf("setIsOpen(false)"),
    );
    // Esc stays locked on its own as well (asserted in the Esc test above).
  });

  it("holds a synchronous ref lock across the mutate call and releases it on success and failure (FE-C17)", () => {
    // `isPending` only flips after a render, so a second activation in the same
    // tick would otherwise fire a second irreversible POST.
    expect(flow).toContain("const lockRef = useRef(false);");
    const body = functionBody(flow, "submit");
    const mutate = body.indexOf("mutation.mutate(");
    expect(mutate).toBeGreaterThan(-1);
    const check = body.indexOf("lockRef.current ||");
    const acquire = body.indexOf("lockRef.current = true;");
    expect(check).toBeGreaterThan(-1);
    expect(acquire).toBeGreaterThan(check);
    expect(acquire).toBeLessThan(mutate);
    // Released in onSettled (runs for success and failure), never only in onSuccess,
    // so a failed submit can be retried.
    const options = body.slice(mutate);
    expect(options).toMatch(/onSettled:\s*\(\)\s*=>\s*\{\s*lockRef\.current = false;\s*\}/);
    expect(flow.match(/lockRef\.current = false/g)).toHaveLength(1);
    expect(flow.match(/lockRef\.current = true/g)).toHaveLength(1);
    // The dialog never touches the lock's value: it only reads it.
    expect(dialog).not.toMatch(/lockRef\.current\s*=[^=]/);
  });

  it("orders the dialog's submit as lock check, R-4 check, then the page takes the lock (FE-C17)", () => {
    const body = functionBody(dialog, "submit");
    const ignore = body.indexOf('plan === "ignore"');
    const stepBack = body.indexOf('plan === "stepBack"');
    const focus = body.indexOf("event.currentTarget.focus()");
    const submit = body.indexOf("onSubmit()");
    expect(ignore).toBeGreaterThan(-1);
    expect(ignore).toBeLessThan(stepBack);
    expect(stepBack).toBeLessThan(focus);
    expect(focus).toBeLessThan(submit);
    expect(dialog).toMatch(/onClick=\{submit\}/);
  });

  it("does not move or drop focus when the pending state flips (failure keeps focus on 確認送出)", () => {
    // The step-heading focus effect is keyed on `state.step` only; pending / error
    // never re-run it, and nothing in the file blurs or re-targets focus on those
    // transitions. The only `.focus(` calls are the heading, the trap, and the
    // clicked submit button.
    expect(dialog).toMatch(/\}, \[state\.step\]\);/);
    expect(dialog).not.toContain(".blur(");
    expect(dialog.match(/\.focus\(/g)).toHaveLength(3);
  });
});

/**
 * FE-T5 / FE-T3 (tech-architect Q14): source scans that pin the architecture of
 * the 全部出清 flow — who owns what, and what is forbidden. Each test names the
 * constraint (FE-C*) or veto (VETO-*) it holds.
 *
 * These are scans, not behaviour: they catch the structure being rewired back
 * (receipt derived from the mutation, dialog hosted under the `isSuccess` gate,
 * a comparison in render, a persisted receipt). Behaviour is covered by the pure
 * reducers' tests, `PlaybookPageStates.test.ts`, and qa-e2e's FE-T12 list.
 */

import { readFileSync, readdirSync, statSync } from "node:fs";
import { dirname, join, relative, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import { describe, expect, it } from "vitest";

const here = dirname(fileURLToPath(import.meta.url));
const APP_ROOT = resolve(here, "../..");
const PLAYBOOK = resolve(here, "..");

function stripComments(source: string): string {
  return source.replace(/\/\*[\s\S]*?\*\//g, "").replace(/^\s*\/\/.*$/gm, "");
}

function read(path: string): string {
  return stripComments(readFileSync(path, "utf-8"));
}

/** Every non-test source file under `dir`, with comments stripped. */
function sources(dir: string): Array<{ file: string; text: string }> {
  const found: Array<{ file: string; text: string }> = [];
  function walk(current: string): void {
    for (const name of readdirSync(current)) {
      if (name === "__tests__" || name === "node_modules" || name === ".next") continue;
      const full = join(current, name);
      if (statSync(full).isDirectory()) walk(full);
      else if (/\.(ts|tsx)$/.test(name)) found.push({ file: relative(APP_ROOT, full), text: read(full) });
    }
  }
  walk(dir);
  return found;
}

const playbook = sources(PLAYBOOK);
const app = sources(APP_ROOT);
/** JSX comments `{/* ... *\/}` leave an empty `{}` once stripped; drop those shells too. */
const page = read(join(PLAYBOOK, "page.tsx")).replace(/\{\s*\}/g, "");
const flow = read(join(PLAYBOOK, "useEmergencyExitFlow.ts"));
const dialog = read(join(PLAYBOOK, "EmergencyExitDialog.tsx"));

/** The exit-flow libs, with the playbook components. */
const exitFiles = [
  ...playbook,
  ...["exitReceipt.ts", "exitDialogState.ts", "taipeiDay.ts", "exitFocus.ts"].map((name) => ({
    file: `lib/${name}`,
    text: read(join(APP_ROOT, "lib", name)),
  })),
];

describe("the receipt is store state, never mutation state (VETO-1: FE-C1, FE-C3, FE-C4; Q15 方案 D)", () => {
  it("nothing under app/playbook reads the mutation's data or success, or the mutation cache", () => {
    for (const { file, text } of playbook) {
      expect(text, file).not.toMatch(/\bmutation\.data\b|\bmutation\.isSuccess\b/);
      expect(text, file).not.toMatch(/useMutationState|getMutationCache|MutationCache/);
    }
  });

  it("the page reads the receipt from the Providers-scope store; the banner gets only the response", () => {
    expect(flow).toMatch(/useSyncExternalStore\(\s*receiptStore\.subscribe,\s*receiptStore\.getSnapshot,/);
    expect(flow).toContain("useExitReceiptStore()");
    expect(page).toMatch(/response=\{receipt\.response\}/);
    expect(read(join(PLAYBOOK, "ExitReceiptBanner.tsx"))).not.toMatch(/useMutation|mutation/);
  });

  it("the receipt is written only by the mutation's definition-level onSuccess, so it survives an unmounted page (風控 FE-2; FE-C4)", () => {
    const queries = read(join(APP_ROOT, "lib/queries.ts"));
    expect(queries.match(/receipts\.accept\(/g)).toHaveLength(1);
    const factory = queries.slice(
      queries.indexOf("export function emergencyExitMutationOptions("),
      queries.indexOf("export function useEmergencyExit("),
    );
    // The factory depends on the narrow sink only.
    expect(factory).toMatch(/emergencyExitMutationOptions\(queryClient: QueryClient, receipts: ExitReceiptSink\)/);
    // First statement of onSuccess, synchronous, fenced, rethrown out of band.
    expect(factory).toMatch(
      /onSuccess: \(response: PlaybookEmergencyExitResponse\): void => \{\s*(?:\/\/[^\n]*\n\s*)*try \{\s*receipts\.accept\(response\);\s*\} catch \(error\) \{\s*void Promise\.reject\(error\);\s*\}\s*\},/,
    );
    expect(factory).not.toMatch(/async |await |\.then\(/);
    // ... and touches no UI state.
    const onSuccess = factory.slice(factory.indexOf("onSuccess:"), factory.indexOf("onSettled:"));
    expect(onSuccess).not.toMatch(/setIsOpen|lockRef|focus|scroll|\.current/);
    // The page's mutate-level callbacks never write a receipt.
    expect(flow).not.toMatch(/\.accept\(|"accepted"/);
    expect(playbook.filter(({ text }) => /\.accept\(|"accepted"/.test(text))).toEqual([]);
    // Not from render, an effect watching the mutation, a MutationCache config,
    // setMutationDefaults or a cache subscription.
    expect(flow).not.toMatch(/useEffect\([^)]*mutation\.(isSuccess|data|status)/);
    for (const { file, text } of app) {
      expect(text, file).not.toMatch(/setMutationDefaults|new MutationCache|mutationCache:|getMutationCache/);
    }
  });

  it("the store is created in a component, never at module level, on globalThis or on window (FE-C1, VETO-5)", () => {
    const store = read(join(APP_ROOT, "lib/exitReceiptStore.ts"));
    const context = read(join(APP_ROOT, "lib/exitReceiptContext.tsx"));
    expect(store).toMatch(/export function createExitReceiptStore\(\): ExitReceiptStore \{/);
    expect(store).toContain("exitReceiptReducer(state, action)");
    // No top-level mutable state in the store module: every `let` is indented
    // (inside the factory), and there is no top-level instance anywhere.
    expect(store).not.toMatch(/^(let|var) /m);
    expect(store).not.toMatch(/globalThis|window|document|self\./);
    for (const { file, text } of app) {
      expect(text, file).not.toMatch(/^(export )?(const|let|var) \w+\s*(:[^=]+)?=\s*createExitReceiptStore\(/m);
      expect(text, file).not.toMatch(/(globalThis|window)\.\w*[Rr]eceipt/);
    }
    expect(context).toContain("useState(() => createExitReceiptStore())");
    const providers = read(join(APP_ROOT, "providers.tsx"));
    expect(providers).toContain("<ExitReceiptStoreProvider>");
    // FE-C1: the QueryClient literal is untouched (the 風控 R4 tripwire in
    // entryObservationPending.test.ts watches it), and Providers stays free of
    // mutation-cache plumbing and of the playbook.
    expect(providers).toContain("new QueryClient()");
    expect(providers).not.toMatch(/defaultOptions|mutationCache|MutationCache|setMutationDefaults/);
    expect(providers).not.toMatch(/from "\.\/playbook|playbook\//);
    expect(providers).not.toMatch(/\bkey=/);
  });

  it("the store holds exactly { receipt, scrolledSeq } and sends nothing (FE-C2, VETO-5)", () => {
    const receipt = read(join(APP_ROOT, "lib/exitReceipt.ts"));
    const state = receipt.slice(receipt.indexOf("export interface ExitReceiptStoreState"), receipt.indexOf("export const INITIAL_EXIT_RECEIPT_STATE"));
    expect([...state.matchAll(/readonly (\w+):/g)].map((m) => m[1])).toEqual(["receipt", "scrolledSeq"]);
    const store = read(join(APP_ROOT, "lib/exitReceiptStore.ts"));
    expect(store).not.toMatch(/fetch\(|postPlaybook|useMutation|useQuery|XMLHttpRequest|isPending|inFlight/);
  });

  it("only app/playbook reads or renders a receipt; Providers and queries.ts touch the store's factory, provider or sink only (FE-C21, FE-4)", () => {
    const readers = app
      .filter(({ text }) => /ExitReceiptBanner|useExitReceiptStore|useExitReceipt\b/.test(text))
      .map(({ file }) => file)
      .sort();
    expect(readers).toEqual([
      "lib/exitReceiptContext.tsx", // defines useExitReceiptStore
      "playbook/ExitReceiptBanner.tsx",
      "playbook/page.tsx",
      "playbook/useEmergencyExitFlow.ts",
    ]);
    expect(app.filter(({ text }) => /<ExitReceiptBanner/.test(text)).map(({ file }) => file)).toEqual([
      "playbook/page.tsx",
    ]);
    const imports = (name: string) => [...read(join(APP_ROOT, name)).matchAll(/import[^;]*?from "([^"]+)"/g)].map((m) => m[1]);
    expect(imports("providers.tsx").filter((m) => /exitReceipt/.test(m ?? ""))).toEqual(["./lib/exitReceiptContext"]);
    expect(imports("lib/queries.ts").filter((m) => /exitReceipt/.test(m ?? ""))).toEqual(["./exitReceiptStore"]);
    // queries.ts takes the sink as a type only.
    expect(read(join(APP_ROOT, "lib/queries.ts"))).toContain('import type { ExitReceiptSink } from "./exitReceiptStore";');
    expect(read(join(APP_ROOT, "lib/queries.ts"))).not.toMatch(/exitReceiptContext|useExitReceiptStore/);
  });

  it("nothing in the exit flow can gate, delay or queue a submit across page instances (VETO-4: FE-C22)", () => {
    for (const { file, text } of exitFiles) {
      expect(text, file).not.toMatch(/\bscope:|useIsMutating|useMutationState|getMutationCache/);
    }
    const queries = read(join(APP_ROOT, "lib/queries.ts"));
    const factory = queries.slice(queries.indexOf("export function emergencyExitMutationOptions("), queries.indexOf("export function useEmergencyExit("));
    // networkMode may only be "always" (FE-R1; asserted in emergencyExitOffline.test.ts);
    // `retry`, `scope` and keys would each defer or queue a submit.
    expect(factory).not.toMatch(/\bscope\b|\bmutationKey\b|\bretry\b/);
    expect(factory.match(/networkMode/g)).toHaveLength(1);
    // The lock is a ref in the page-instance hook, nowhere else (the page only hands it to the dialog).
    const lockUsers = app.filter(({ text }) => /lockRef/.test(text)).map(({ file }) => file).sort();
    expect(lockUsers).toEqual(["playbook/EmergencyExitDialog.tsx", "playbook/page.tsx", "playbook/useEmergencyExitFlow.ts"]);
    expect(flow).toContain("const lockRef = useRef(false);");
  });

  it("the store holds the receipt and the scrolled marker only: no exit_confirm, dialog state, lock or mutation (F-1)", () => {
    const store = read(join(APP_ROOT, "lib/exitReceiptStore.ts"));
    expect(store).not.toMatch(/exit_confirm|exitConfirm|lockRef|useMutation|dialog|ExitDialogState/i);
  });

  it("mutation.reset() is used in exactly one place: opening the dialog, to clear the previous round's failure panel (FE-C9)", () => {
    const uses = playbook.filter(({ text }) => /\.reset\(\)/.test(text));
    expect(uses.map(({ file }) => file)).toEqual(["playbook/useEmergencyExitFlow.ts"]);
    expect(flow.match(/mutation\.reset\(\)/g)).toHaveLength(1);
    const open = flow.slice(flow.indexOf("function open()"), flow.indexOf("function close()"));
    expect(open).toContain("mutation.reset()");
  });

  it("the failure panel shows only on Step 3 while the failure stands: isError && step === final (FE-C9, FR-14g)", () => {
    expect(dialog).toMatch(/const showFailure = isError && state\.step === "final";/);
  });
});

describe("nothing about the receipt or exit_confirm is persisted (VETO-3: FE-C5)", () => {
  it("no storage, cookie, IndexedDB, URL or history.state use in the exit flow", () => {
    for (const { file, text } of exitFiles) {
      expect(text, file).not.toMatch(
        /sessionStorage|localStorage|indexedDB|document\.cookie|history\.state|history\.(push|replace)State|location\.(hash|search)|URLSearchParams|persistQueryClient|persister/,
      );
    }
  });
});

describe("the dialog and the observer sit above the isSuccess gate (VETO-2: FE-C10, FE-C11)", () => {
  it("useEmergencyExit is called exactly once in app/playbook, in the flow hook that the page calls", () => {
    const callers = playbook.filter(({ text }) => /useEmergencyExit\(/.test(text.replace(/export function useEmergencyExit\(/, "")));
    expect(callers.map(({ file }) => file)).toEqual(["playbook/useEmergencyExitFlow.ts"]);
    expect(page.match(/useEmergencyExitFlow\(\)/g)).toHaveLength(1);
    expect(page.match(/usePlaybookToday\(/g)).toHaveLength(1);
  });

  it("neither ModeStatusBar nor the trigger imports the dialog or the exit mutation", () => {
    for (const name of ["ModeStatusBar.tsx", "ExitTriggerButton.tsx"]) {
      const text = read(join(PLAYBOOK, name));
      expect(text, name).not.toMatch(/EmergencyExitDialog|useEmergencyExit|useMutation|createPortal/);
    }
  });

  it("the dialog takes `today` as a prop and opens no query observer of its own (FE-C14)", () => {
    expect(dialog).not.toMatch(/usePlaybookToday|useQuery|useEmergencyExit|useQueryClient/);
    expect(dialog).toMatch(/useReducer\(exitDialogReducer, today, createExitDialogState\)/);
  });

  it("exit_confirm reaches the dialog only through `today.isSuccess ? today.data.exit_confirm : null` (Q8 F-1)", () => {
    for (const { file, text } of app) {
      expect(text, file).not.toMatch(/data\?\.exit_confirm/);
    }
    expect(page.match(/exit_confirm/g)).toHaveLength(1);
    expect(page).toContain("exitConfirm: today.isSuccess ? today.data.exit_confirm : null,");
  });

  it("the last successful exit_confirm is stored nowhere outside the dialog's own reducer (Q11 F-1)", () => {
    const holders = exitFiles.filter(({ text }) => /exit_confirm|exitConfirm/.test(text)).map(({ file }) => file);
    // page.tsx builds the view; the libs consume it; nothing else mentions it.
    expect(holders.sort()).toEqual(["lib/exitDialogState.ts", "playbook/page.tsx"]);
    for (const { file, text } of exitFiles) {
      expect(text, file).not.toMatch(/useRef<[^>]*[Ee]xitConfirm/);
    }
  });
});

describe("the receipt scroll keys on the receipt alone (FE-C8, FE-T3, 風控 FE-4)", () => {
  it("the scroll effect depends on exactly [receiptSeq, scrolledSeq, isOpen] and re-reads the store when it runs (FE-C8, FE-T3)", () => {
    const start = flow.indexOf("useEffect(() => {\n    const latest = receiptStore.getSnapshot();");
    expect(start).toBeGreaterThan(-1);
    const effect = flow.slice(start, flow.indexOf("[receiptSeq, scrolledSeq, isOpen]);", start) + "[receiptSeq, scrolledSeq, isOpen]);".length);
    expect(effect).toMatch(/\}, \[receiptSeq, scrolledSeq, isOpen\]\);$/);
    expect(effect).toContain("receiptStore.getSnapshot()");
    expect(effect).toContain("shouldScrollForReceipt(seq, latest.scrolledSeq, isOpen)");
    expect(effect).not.toMatch(/today/);
    expect(flow).not.toMatch(/usePlaybookToday|\btoday\b/);
    // The marker is written after the scroll, synchronously, and only there.
    expect(flow.match(/receiptStore\.scrollHandled\(/g)).toHaveLength(1);
    expect(effect.indexOf("scrollIntoView")).toBeLessThan(effect.indexOf("scrollHandled("));
  });

  it("the 「already scrolled」 marker is in the store, not the page instance: no lastHandledSeq (FE-3)", () => {
    expect(flow).not.toMatch(/lastHandledSeq|useRef\(receipt|useRef\(0\)/);
    expect(flow).toContain("receiptStore.getServerSnapshot");
    // FE-C1: no copy of the receipt in page state; it is only read through the store.
    for (const { file, text } of playbook) {
      expect(text, file).not.toMatch(/use(State|Reducer|Ref)(<[^>(]*)?(Receipt|receipt)/);
    }
  });

  it("scrolls instantly, never smoothly, and never moves focus", () => {
    expect(flow).toContain('banner.scrollIntoView({ block: "start", behavior: "auto" })');
    expect(flow).not.toMatch(/behavior: "smooth"/);
    const effect = flow.slice(flow.indexOf("const receiptSeq"));
    expect(effect).not.toMatch(/\.focus\(/);
  });
});

describe("R-2～R-5 are driven from a layout effect, not from render (FE-C15, FE-C16)", () => {
  it("the old render-time re-seed is gone and nothing compares in render", () => {
    expect(dialog).not.toMatch(/checks\.length !== /);
    expect(dialog).not.toMatch(/setChecks\(/);
    expect(dialog).not.toMatch(/useState<boolean\[\]>/);
  });

  it("the comparison effect: useLayoutEffect, lock read first at effect time, the four documented dependencies", () => {
    const start = dialog.indexOf("useLayoutEffect(() => {");
    expect(start).toBeGreaterThan(-1);
    const end = dialog.indexOf("]);", start) + 3;
    const effect = dialog.slice(start, end);
    expect(effect).toMatch(
      /^useLayoutEffect\(\(\) => \{\s*if \(lockRef\.current \|\| isPending\) return;\s*dispatch\(\{ type: "reconcile", today, now: Date\.now\(\) \}\);\s*\}, \[today\.status, today\.dataUpdatedAt, isPending, tick\]\);$/,
    );
    // The lock's value is never copied into a render-time variable first.
    expect(dialog).not.toMatch(/const\s+\w*[lL]ock\w*\s*=\s*lockRef\.current/);
  });

  it("R-4 is also evaluated on the next Taipei midnight, on becoming visible, and on window focus", () => {
    expect(dialog).toContain("nextTaipeiMidnight(state.heldAt)");
    expect(dialog).toContain('document.addEventListener("visibilitychange"');
    expect(dialog).toContain('window.addEventListener("focus"');
    // ... and synchronously at the head of the continue and submit handlers.
    expect(dialog).toContain("planAdvance(state, Date.now())");
    expect(dialog).toContain("planSubmit(state, Date.now()");
  });
});

describe("focus moves only where FE-C19 / FE-C20 allow", () => {
  it("every programmatic focus of a trigger passes preventScroll", () => {
    const trigger = read(join(PLAYBOOK, "ExitTriggerButton.tsx"));
    for (const text of [flow, trigger]) {
      for (const call of text.match(/\.focus\([^)]*\)/g) ?? []) {
        expect(call).toBe(".focus({ preventScroll: true })");
      }
    }
  });
});

describe("the page layout the 風控 floor rests on (FE-C6, FE-C12, 視覺規範 §2.1 / §10)", () => {
  it("the role=status container is class-less, key-less, and directly follows the h1 row", () => {
    expect(page).toMatch(/<\/div>\s*<div role="status">/);
    expect(page).not.toMatch(/<div role="status" /);
    expect(page.match(/role="status"/g)).toHaveLength(1);
    // Not inside any today.* conditional: the opening tag is preceded by the h1 row's close.
    const at = page.indexOf('<div role="status">');
    expect(page.slice(page.lastIndexOf("</div>", at - 1), at).replace(/\s+/g, "")).toBe("</div>");
  });

  it("the trigger is placed by the same today.isSuccess test that gates the status bar", () => {
    expect(page).toMatch(/\{today\.isSuccess && \(\s*<ModeStatusBar today=\{today\.data\} trigger=\{trigger\}/);
    expect(page).toMatch(/\{!today\.isSuccess && trigger\}/);
  });

  it("the receipt's mode_reason is hidden by `today.isSuccess` and string equality, not by any container's existence (F-6)", () => {
    const at = page.indexOf("isReceiptModeReasonHidden(");
    const call = page.slice(at, page.indexOf(");", at));
    expect(call).toMatch(/^isReceiptModeReasonHidden\(\s*today\.isSuccess,/);
    expect(call).not.toMatch(/trigger|isOpen|Ref|h1/);
  });

  it("the h1 row is a plain flex row: no bar-like classes, not sticky, not a landmark", () => {
    const at = page.indexOf('<div className="flex items-center justify-between gap-3">');
    expect(at).toBeGreaterThan(-1);
    expect(page.slice(at, page.indexOf(">", at))).not.toMatch(/bg-|border|shadow|sticky|fixed|role|aria-|backdrop/);
  });

  it("ModeStatusBar is the opaque bg-black strip with no clipping of its text (風控 必改項 8)", () => {
    const bar = read(join(PLAYBOOK, "ModeStatusBar.tsx"));
    expect(bar).toContain("sticky top-0 z-10 border-b border-neutral-800 bg-black");
    expect(bar).not.toMatch(/bg-black\/|backdrop-|max-h-|overflow-|line-clamp|truncate/);
  });
});

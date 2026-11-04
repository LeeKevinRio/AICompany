/**
 * N-171 group A front end (ADR-0039 C7, C19, C22, T19, T22, T27; art spec
 * 2026-11-04 r1 VP clauses that can be checked without a layout engine; 風控
 * 2026-11-04 R-1..R-6).
 *
 * The suite runs on `renderToStaticMarkup` (the project has no jsdom), and a
 * small parser below turns the markup into a tree so structure and
 * `textContent` can be asserted. Computed-style, geometry and viewport clauses
 * are listed for qa-automation in the delivery report, not faked here.
 *
 * Sentinel strings are used on purpose: every visible word must be a value the
 * test passed in, so any front-end authored text is an immediate leak.
 */

import { readFileSync } from "node:fs";
import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it, vi } from "vitest";
import { formatDateTime } from "../../lib/format";
import { EXIT_FAILURE_WORDING } from "../../lib/playbookView";
import type {
  PlaybookPendingExitBlock,
  PlaybookPendingExitRow,
  PlaybookPendingExitSection,
  PlaybookTodayResponse,
} from "../../lib/types";
import { ExitFailurePanel } from "../ExitFailurePanel";
import { todayResponse } from "./pageFixtures";

const state = vi.hoisted(() => ({
  today: undefined as unknown,
  status: "success" as "success" | "pending" | "error",
}));

vi.mock("../../lib/queries", () => ({
  usePlaybookToday: () => ({
    status: state.status,
    dataUpdatedAt: 0,
    fetchStatus: "idle",
    isPending: state.status === "pending",
    isError: state.status === "error",
    isSuccess: state.status === "success",
    error: state.status === "error" ? new Error("x") : null,
    data: state.status === "success" ? state.today : undefined,
  }),
  usePlaybookRuleSet: () => ({ isPending: false, isError: false, isSuccess: true, error: null, data: undefined }),
  useConfirmPlaybookRules: () => ({ mutate: () => undefined, isPending: false, isError: false, error: null }),
  useEmergencyExit: () => ({
    mutate: () => undefined,
    reset: () => undefined,
    isPending: false,
    isError: false,
    error: null,
  }),
}));

const { PendingExitBlock, leadWithReadAt, withNoBreakDates } = await import("../PendingExitBlock");
const { default: PlaybookPage } = await import("../page");
const { ExitReceiptStoreProvider } = await import("../../lib/exitReceiptContext");

/* ---------------------------------------------------------------- parser */

interface Node {
  tag: string;
  attrs: Record<string, string>;
  children: (Node | string)[];
  parent: Node | null;
}

function decode(s: string): string {
  return s
    .replace(/&lt;/g, "<")
    .replace(/&gt;/g, ">")
    .replace(/&quot;/g, '"')
    .replace(/&#x27;/g, "'")
    .replace(/&amp;/g, "&");
}

function parse(markup: string): Node {
  const root: Node = { tag: "#root", attrs: {}, children: [], parent: null };
  let cur = root;
  for (const m of markup.matchAll(/<(\/?)([a-zA-Z0-9]+)([^>]*)>|([^<]+)/g)) {
    if (m[4] !== undefined) {
      cur.children.push(decode(m[4]));
    } else if (m[1] === "/") {
      if (cur.parent === null) throw new Error("unbalanced markup");
      cur = cur.parent;
    } else {
      const attrs: Record<string, string> = {};
      for (const a of (m[3] ?? "").matchAll(/([\w-]+)(?:="([^"]*)")?/g)) attrs[a[1]!] = decode(a[2] ?? "");
      const node: Node = { tag: m[2]!, attrs, children: [], parent: cur };
      cur.children.push(node);
      if (!/^(br|hr|img|input|meta|link)$/.test(node.tag)) cur = node;
    }
  }
  return root;
}

function text(n: Node | string): string {
  return typeof n === "string" ? n : n.children.map(text).join("");
}
function elems(n: Node): Node[] {
  return n.children.filter((c): c is Node => typeof c !== "string");
}
function all(n: Node): Node[] {
  return elems(n).flatMap((c) => [c, ...all(c)]);
}
function byTestId(n: Node, id: string): Node[] {
  return all(n).filter((e) => e.attrs["data-testid"] === id);
}

/* -------------------------------------------------------------- fixtures */

function row(i: number, over: Partial<PlaybookPendingExitRow> = {}): PlaybookPendingExitRow {
  return {
    symbol: `SYM${i}`,
    batch_no: i,
    shares: 100 * i,
    coverage: "covering",
    batch_has_covering: true,
    execution_dates: ["2026-11-05"],
    text: `SENTINEL-TEXT-${i}`,
    notes: [],
    entry_before_exit_note: null,
    ...over,
  };
}

function section(
  kind: PlaybookPendingExitSection["kind"],
  label: string | null,
  rows: PlaybookPendingExitRow[],
): PlaybookPendingExitSection {
  return { kind, label, lead: `SENTINEL-LEAD-${kind}`, rows };
}

function block(over: Partial<PlaybookPendingExitBlock> = {}): PlaybookPendingExitBlock {
  return {
    title: "SENTINEL-TITLE",
    lead_template: "SENTINEL-LEAD-A {read_at} SENTINEL-LEAD-B",
    sections: [
      section("covering", "SENTINEL-LABEL-covering", [
        row(1, { notes: ["SENTINEL-NOTE-1A", "SENTINEL-NOTE-1B"], entry_before_exit_note: "SENTINEL-ENTRY-1" }),
        row(2),
      ]),
      section("stale", "SENTINEL-LABEL-stale", [
        row(3, { coverage: "stale", text: "SENTINEL-STALE-TEXT-3", notes: ["SENTINEL-NOTE-3A"] }),
      ]),
    ],
    closing_notes: ["SENTINEL-CLOSING-1", "SENTINEL-CLOSING-2"],
    ...over,
  };
}

function body(b: PlaybookPendingExitBlock | null | "absent", extra: Partial<PlaybookTodayResponse> = {}) {
  const base = todayResponse({ mode: "normal", ...extra });
  if (b === "absent") return base;
  return { ...base, pending_exit_block: b };
}

function renderBlock(b: PlaybookPendingExitBlock | null | "absent"): string {
  state.status = "success";
  state.today = body(b);
  return renderToStaticMarkup(createElement(PendingExitBlock));
}

function renderPage(b: PlaybookPendingExitBlock | null | "absent", extra: Partial<PlaybookTodayResponse> = {}): string {
  state.status = "success";
  state.today = body(b, extra);
  return renderToStaticMarkup(createElement(ExitReceiptStoreProvider, null, createElement(PlaybookPage)));
}

function blockNode(markup: string): Node {
  const found = byTestId(parse(markup), "pending-exit-block");
  expect(found).toHaveLength(1);
  return found[0]!;
}

/* ------------------------------------------------------------------ tests */

describe("render condition (VP-19, VP-20, AC-N171-21)", () => {
  it.each([
    ["null", null],
    ["absent key", "absent" as const],
    ["no sections", block({ sections: [] })],
    ["sections without rows", block({ sections: [section("covering", null, [])] })],
  ])("%s renders nothing", (_name, b) => {
    expect(renderBlock(b)).toBe("");
  });

  it.each(["pending", "error"] as const)("a /today in %s state renders no block, not even a title", (status) => {
    state.status = status;
    state.today = body(block());
    const markup = renderToStaticMarkup(createElement(PendingExitBlock));
    expect(markup).toBe("");
  });

  it("a page with null / absent block is byte-identical to one without the feature's key (no empty slot)", () => {
    const absent = renderPage("absent");
    expect(renderPage(null)).toBe(absent);
    expect(renderPage(block({ sections: [] }))).toBe(absent);
    expect(absent).not.toContain("pending-exit-block");
  });

  it("a failed /today renders no block on the page", () => {
    state.status = "error";
    state.today = body(block());
    const markup = renderToStaticMarkup(createElement(ExitReceiptStoreProvider, null, createElement(PlaybookPage)));
    expect(markup).not.toContain("pending-exit-block");
    expect(markup).not.toContain("SENTINEL-TITLE");
  });
});

describe("position (VP-1, C7)", () => {
  it("is the next sibling of the role=status slot and precedes attribution, summary, warnings", () => {
    const main = all(parse(renderPage(block()))).find((n) => n.tag === "main")!;
    const kids = elems(main);
    const slot = kids.findIndex((k) => k.attrs["role"] === "status");
    expect(slot).toBeGreaterThanOrEqual(0);
    expect(kids[slot + 1]!.attrs["data-testid"]).toBe("pending-exit-block");
    const flat = text(main);
    const at = (s: string) => flat.indexOf(s);
    expect(at("SENTINEL-TITLE")).toBeGreaterThan(-1);
    for (const later of ["SENTINEL-ATTRIBUTION", "SENTINEL-SUMMARY-ONE", "SENTINEL-WARNING"]) {
      expect(at(later)).toBeGreaterThan(at("SENTINEL-CLOSING-2"));
    }
  });

  it("is not inside the live region, a dialog or any role-bearing ancestor", () => {
    const node = blockNode(renderPage(block()));
    for (let p = node.parent; p !== null; p = p.parent) {
      expect(p.attrs["role"]).toBeUndefined();
      expect(p.attrs["aria-live"]).toBeUndefined();
    }
    expect(node.parent!.tag).toBe("main");
  });

  it("the page source mounts it as the first child of the today.isSuccess fragment", () => {
    const src = readFileSync(new URL("../page.tsx", import.meta.url), "utf8");
    const frag = src.indexOf("{today.isSuccess && data !== undefined && (");
    const open = src.indexOf("<>", frag);
    expect(src.slice(open + 2).trimStart().replace(/^\{\/\*[\s\S]*?\*\/\}\s*/, "")).toMatch(/^<PendingExitBlock \/>/);
  });
});

describe("content order and text (VP-10, T22, C19)", () => {
  it("renders title, lead, then each section (label, lead, rows), then closing notes, verbatim and in order", () => {
    const node = blockNode(renderBlock(block()));
    const stamp = formatDateTime("2026-10-28T00:00:00+00:00");
    expect(elems(node).map((e) => e.tag)).toEqual(["h2", "p", "section", "section", "p", "p"]);
    expect(text(node)).toBe(
      "SENTINEL-TITLE" +
        `SENTINEL-LEAD-A ${stamp} SENTINEL-LEAD-B` +
        "SENTINEL-LABEL-covering" + "SENTINEL-LEAD-covering" +
        "SENTINEL-TEXT-1" + "SENTINEL-NOTE-1A" + "SENTINEL-NOTE-1B" + "SENTINEL-ENTRY-1" +
        "SENTINEL-TEXT-2" +
        "SENTINEL-LABEL-stale" + "SENTINEL-LEAD-stale" +
        "SENTINEL-STALE-TEXT-3" + "SENTINEL-NOTE-3A" +
        "SENTINEL-CLOSING-1" + "SENTINEL-CLOSING-2",
    );
  });

  it("does not re-sort sections or rows (stale before covering stays that way)", () => {
    const b = block();
    const reversed = block({ sections: [...b.sections].reverse() });
    const flat = text(blockNode(renderBlock(reversed)));
    expect(flat.indexOf("SENTINEL-LABEL-stale")).toBeLessThan(flat.indexOf("SENTINEL-LABEL-covering"));
    const rowsReversed = block({
      sections: [section("covering", null, [row(2), row(1)])],
    });
    const t = text(blockNode(renderBlock(rowsReversed)));
    expect(t.indexOf("SENTINEL-TEXT-2")).toBeLessThan(t.indexOf("SENTINEL-TEXT-1"));
  });

  it("T22: {read_at} is replaced exactly once with formatDateTime(as_of) of the same response", () => {
    const stamp = formatDateTime("2026-10-28T00:00:00+00:00");
    const t = text(blockNode(renderBlock(block())));
    expect(t.split(stamp)).toHaveLength(2);
    expect(t).not.toContain("{read_at}");
    expect(leadWithReadAt("x {read_at} y", "2026-10-28T00:00:00+00:00")).toBe(`x ${stamp} y`);
    // Only the first placeholder is touched; a template without one is unchanged.
    expect(leadWithReadAt("no placeholder", "2026-10-28T00:00:00+00:00")).toBe("no placeholder");
  });

  it("uses this response's as_of, not another instant", () => {
    state.status = "success";
    state.today = body(block(), { as_of: "2026-11-03T06:30:00+00:00" });
    const t = text(blockNode(renderToStaticMarkup(createElement(PendingExitBlock))));
    expect(t).toContain(formatDateTime("2026-11-03T06:30:00+00:00"));
    expect(t).not.toContain(formatDateTime("2026-10-28T00:00:00+00:00"));
  });

  it("adds no decoration: the text is exactly the backend strings (VP-6)", () => {
    const node = blockNode(renderBlock(block()));
    expect(text(node)).not.toMatch(/[：•·✓✔✅☑✗❌⚠–—]/u);
    expect(all(node).filter((e) => ["svg", "img", "canvas", "i"].includes(e.tag))).toHaveLength(0);
  });
});

describe("row structure (VP-11, R-1, A-15 same-row order, null leaves no gap)", () => {
  it("li children are exactly text, notes in order, entry note; nothing in between (R-1)", () => {
    const node = blockNode(renderBlock(block()));
    const lis = byTestId(node, "pending-exit-row");
    expect(lis).toHaveLength(3);
    expect(elems(lis[0]!).map((e) => [e.tag, text(e)])).toEqual([
      ["p", "SENTINEL-TEXT-1"],
      ["p", "SENTINEL-NOTE-1A"],
      ["p", "SENTINEL-NOTE-1B"],
      ["p", "SENTINEL-ENTRY-1"],
    ]);
    // No stray text nodes directly in the li either.
    for (const li of lis) expect(li.children.every((c) => typeof c !== "string")).toBe(true);
  });

  it("null entry_before_exit_note renders no element: li has 1 + notes.length paragraphs", () => {
    const node = blockNode(renderBlock(block()));
    const lis = byTestId(node, "pending-exit-row");
    expect(elems(lis[1]!)).toHaveLength(1);
    expect(elems(lis[2]!)).toHaveLength(2);
  });

  it("the entry note is always after the notes, never before, whatever the array contents", () => {
    const b = block({
      sections: [
        section("covering", null, [
          row(1, { notes: ["N-A6", "N-A15"], entry_before_exit_note: "N-W-B2L" }),
          row(2, { coverage: "stale", notes: ["N-A11", "N-A15"], entry_before_exit_note: null }),
        ]),
      ],
    });
    const lis = byTestId(blockNode(renderBlock(b)), "pending-exit-row");
    expect(elems(lis[0]!).map(text)).toEqual(["SENTINEL-TEXT-1", "N-A6", "N-A15", "N-W-B2L"]);
    expect(elems(lis[1]!).map(text)).toEqual(["SENTINEL-TEXT-2", "N-A11", "N-A15"]);
  });

  it("notes carry no indent, divider, background or opacity and are at least as strong as the lead (R-2)", () => {
    const node = blockNode(renderBlock(block()));
    const lead = elems(node)[1]!.attrs["class"]!;
    for (const li of byTestId(node, "pending-exit-row")) {
      for (const p of elems(li).slice(1)) {
        const cls = p.attrs["class"]!;
        expect(cls).toBe("mt-1 break-words text-sm text-neutral-300");
        expect(cls).not.toMatch(/\b(pl-|ml-|border|bg-|opacity|text-xs|font-light|italic)/);
      }
    }
    expect(lead).toContain("text-sm text-neutral-300");
  });

  it("closing notes are outside every li and every section", () => {
    const node = blockNode(renderBlock(block()));
    const closings = byTestId(node, "pending-exit-closing");
    expect(closings.map(text)).toEqual(["SENTINEL-CLOSING-1", "SENTINEL-CLOSING-2"]);
    for (const c of closings) expect(c.parent).toBe(node);
  });

  it("never renders an empty p, h3 or li (VP-11)", () => {
    const node = blockNode(renderBlock(block()));
    for (const e of all(node).filter((n) => ["p", "h2", "h3", "li"].includes(n.tag))) {
      expect(text(e).trim()).not.toBe("");
    }
  });
});

describe("sections and labels (VP-17, R-3)", () => {
  it("h3 exists iff label is non-null; a null label leaves neither h3 nor aria-labelledby", () => {
    const b = block({ sections: [section("unclassified", null, [row(1)])] });
    const node = blockNode(renderBlock(b));
    const sec = elems(node).find((e) => e.tag === "section")!;
    expect(all(sec).filter((e) => e.tag === "h3")).toHaveLength(0);
    expect(sec.attrs["aria-labelledby"]).toBeUndefined();
    expect(sec.attrs["data-kind"]).toBe("unclassified");
    // first child of an unlabelled section is the lead, with no mt-1
    expect(elems(sec)[0]!.attrs["class"]).toBe("break-words text-sm text-neutral-300");
  });

  it("labelled sections point aria-labelledby at their h3 (VP-23)", () => {
    const node = blockNode(renderBlock(block()));
    for (const sec of elems(node).filter((e) => e.tag === "section")) {
      const h3 = elems(sec).find((e) => e.tag === "h3")!;
      expect(sec.attrs["aria-labelledby"]).toBe(h3.attrs["id"]);
    }
  });

  it("R-6(a): the root points aria-labelledby at its h2 and the ids are unique", () => {
    const node = blockNode(renderBlock(block()));
    const h2 = elems(node).find((e) => e.tag === "h2")!;
    expect(node.attrs["aria-labelledby"]).toBe(h2.attrs["id"]);
    const ids = all(node).map((e) => e.attrs["id"]).filter((x): x is string => x !== undefined);
    expect(new Set(ids).size).toBe(ids.length);
  });

  it("R-3: only stale gets the solid 2px neutral-500 top rule with pt-4 (>=16px) below it", () => {
    const node = blockNode(renderBlock(block()));
    const [cov, stale] = elems(node).filter((e) => e.tag === "section");
    expect(stale!.attrs["class"]).toBe("mt-6 border-t-2 border-neutral-500 pt-4");
    expect(cov!.attrs["class"]).toBe("mt-4");
    for (const e of [node, ...all(node)]) {
      expect(e.attrs["class"] ?? "").not.toMatch(/border-(dashed|dotted|double)|divide-(dashed|dotted)/);
    }
  });

  it("R-3(c): rows and notes of stale and covering sections use identical classes", () => {
    const node = blockNode(renderBlock(block()));
    const [cov, stale] = elems(node).filter((e) => e.tag === "section");
    const sig = (sec: Node) => {
      const ul = elems(sec).find((e) => e.tag === "ul")!;
      const li = elems(ul)[0]!;
      const ps = elems(li);
      return {
        ul: ul.attrs["class"],
        li: li.attrs["class"],
        text: ps[0]!.attrs["class"],
        note: ps[1]!.attrs["class"],
      };
    };
    expect(sig(stale!)).toEqual(sig(cov!));
    const staleClasses = all(stale!).map((e) => e.attrs["class"] ?? "").join(" ");
    expect(staleClasses).not.toMatch(/opacity|line-through|text-neutral-(400|500|600)|italic|text-xs/);
    expect(stale!.attrs["style"]).toBeUndefined();
  });
});

describe("forbidden classes and attributes (風控 4.3, VP-12, VP-15, VP-23, R-6(b))", () => {
  const markup = renderBlock(block());
  const node = blockNode(markup);
  const nodes = [node, ...all(node)];
  const classes = nodes.map((e) => e.attrs["class"] ?? "").join(" ");

  it.each([
    "truncate", "line-clamp", "overflow-", "max-h-", "break-all", "sticky", "fixed", "absolute",
    "hidden", "sr-only", "invisible", "opacity-", "text-ellipsis", "whitespace-pre", "keep-all",
    "line-through", "underline", "italic", "uppercase", "flex", "grid", "table", "rounded", "shadow",
    "transition", "animate", "list-disc", "list-decimal",
  ])("no %s class", (bad) => {
    expect(classes).not.toContain(bad);
  });

  it("no breakpoint-prefixed class and no colour class", () => {
    expect(classes).not.toMatch(/(^|\s)(sm|md|lg|xl|2xl|max-sm|max-md|max-lg):/);
    expect(classes).not.toMatch(
      /(text|bg|border|divide|ring|outline|decoration|fill|stroke)-(red|rose|orange|amber|yellow|lime|green|emerald|teal|cyan|sky|blue|indigo|violet|purple|fuchsia|pink)/,
    );
  });

  it("only text-lg and text-sm, only neutral-100/300 text", () => {
    expect([...new Set(classes.match(/text-(xs|sm|base|lg|xl|\dxl)/g))].sort()).toEqual(["text-lg", "text-sm"]);
    expect([...new Set(classes.match(/text-neutral-\d+/g))].sort()).toEqual(["text-neutral-100", "text-neutral-300"]);
  });

  it("no aria-label, title, aria-describedby, aria-live, role, tabindex, style, or interactive element", () => {
    for (const e of nodes) {
      for (const a of ["aria-label", "title", "aria-describedby", "aria-live", "aria-atomic", "aria-busy", "role", "tabindex", "style", "hidden", "onclick"]) {
        expect(e.attrs[a], `${e.tag}[${a}]`).toBeUndefined();
      }
      expect(["a", "button", "input", "select", "textarea", "details", "summary"]).not.toContain(e.tag);
    }
    expect(markup).not.toMatch(/role="(status|alert|log)"/);
  });

  it("heading levels go h2 then h3, and only data-testid / data-kind data attributes exist", () => {
    expect(nodes.filter((e) => /^h\d$/.test(e.tag)).map((e) => e.tag)).toEqual(["h2", "h3", "h3"]);
    for (const e of nodes) {
      for (const k of Object.keys(e.attrs)) {
        if (k.startsWith("data-")) expect(["data-testid", "data-kind"]).toContain(k);
      }
    }
  });

  it("the component source contains none of the forbidden tokens either", () => {
    const src = readFileSync(new URL("../PendingExitBlock.tsx", import.meta.url), "utf8");
    const code = src.replace(/\/\*[\s\S]*?\*\//g, "").replace(/^\s*\/\/.*$/gm, "");
    for (const bad of ["truncate", "line-clamp", "overflow-", "max-h-", "break-all", "sticky", "aria-label=", "title=", "aria-describedby", "aria-live", "role="]) {
      expect(code, bad).not.toContain(bad);
    }
  });
});

/* ------------------------------------------------- ISO date no-break (VP-14) */

const ISO_DATE_FULL = /^\d{4}-\d{2}-\d{2}$/;

/** Elements carrying a nowrap class that are NOT a bare ISO-date span inside a p. */
function nowrapViolations(root: Node): Node[] {
  return [root, ...all(root)].filter((e) => {
    if (!(e.attrs["class"] ?? "").includes("nowrap")) return false;
    const ok =
      e.tag === "span" &&
      e.attrs["class"] === "whitespace-nowrap" &&
      Object.keys(e.attrs).length === 1 &&
      e.children.length === 1 &&
      typeof e.children[0] === "string" &&
      ISO_DATE_FULL.test(e.children[0]) &&
      e.parent !== null &&
      e.parent.tag === "p";
    return !ok;
  });
}

function datedBlock(): PlaybookPendingExitBlock {
  return block({
    sections: [
      section("covering", "SENTINEL-LABEL-covering", [
        row(1, {
          text: "T-A 2026-11-11 T-B 2026-11-12/2026-11-13 T-C",
          notes: ["2026-11-05", "N-B no date", "N-C 2026-11-02 end"],
          entry_before_exit_note: "ENTRY 2026-11-11 kept",
        }),
        row(2, { text: "SHARES 200 LOT 12345-67-891 AND 2026-1-1 AND 20261-11-11 AND 2026-11-111" }),
        row(3, { text: "SENTINEL-PLAIN-3" }),
      ]),
    ],
  });
}

describe("ISO date no-break span (VP-14, spec r1 section 7 exception)", () => {
  const DATED_TEXT = "T-A 2026-11-11 T-B 2026-11-12/2026-11-13 T-C";

  function datedRows(): Node[] {
    return byTestId(blockNode(renderBlock(datedBlock())), "pending-exit-row");
  }

  it("wraps every ISO date in text, notes and the entry note, and nothing else is nowrap", () => {
    const node = blockNode(renderBlock(datedBlock()));
    const spans = all(node).filter((e) => e.tag === "span");
    expect(spans.map(text)).toEqual([
      "2026-11-11", "2026-11-12", "2026-11-13", "2026-11-05", "2026-11-02", "2026-11-11",
    ]);
    expect(nowrapViolations(node)).toEqual([]);
  });

  it("each span holds only date characters, one text child, a class and nothing else", () => {
    for (const span of all(blockNode(renderBlock(datedBlock()))).filter((e) => e.tag === "span")) {
      expect(text(span)).toMatch(ISO_DATE_FULL);
      expect(span.children).toHaveLength(1);
      expect(span.attrs).toEqual({ class: "whitespace-nowrap" });
      expect(span.parent!.tag).toBe("p");
    }
  });

  it("textContent of every row paragraph equals the backend string byte for byte", () => {
    const lis = datedRows();
    expect(text(elems(lis[0]!)[0]!)).toBe(DATED_TEXT);
    expect(elems(lis[0]!).slice(1).map(text)).toEqual(["2026-11-05", "N-B no date", "N-C 2026-11-02 end", "ENTRY 2026-11-11 kept"]);
  });

  it("adds no whitespace, no empty string and no extra text node around a span", () => {
    const p = elems(datedRows()[0]!)[0]!;
    expect(p.children.map((c) => (typeof c === "string" ? c : `<${text(c)}>`))).toEqual([
      "T-A ", "<2026-11-11>", " T-B ", "<2026-11-12>", "/", "<2026-11-13>", " T-C",
    ]);
    // A date that is the whole string leaves exactly one child.
    const only = elems(datedRows()[0]!)[1]!;
    expect(only.children).toHaveLength(1);
    expect(text(only)).toBe("2026-11-05");
    expect(only.attrs["class"]).toBe("mt-1 break-words text-sm text-neutral-300");
  });

  it("the paragraph stays white-space: normal (no nowrap on it or any container)", () => {
    const node = blockNode(renderBlock(datedBlock()));
    for (const e of all(node).filter((n) => n.tag !== "span")) expect(e.attrs["class"] ?? "").not.toContain("nowrap");
    expect(node.attrs["class"]).toBe("mb-6 mt-6");
    expect(elems(datedRows()[0]!)[0]!.attrs["class"]).toBe("break-words text-sm text-neutral-100");
  });

  it("does not wrap digit runs that are not a lone ISO date", () => {
    const p = elems(datedRows()[1]!)[0]!;
    expect(p.children.every((c) => typeof c === "string")).toBe(true);
    expect(text(p)).toBe("SHARES 200 LOT 12345-67-891 AND 2026-1-1 AND 20261-11-11 AND 2026-11-111");
  });

  it("a string with no date is returned unchanged and renders identically to a plain string", () => {
    expect(withNoBreakDates("SENTINEL-PLAIN-3")).toBe("SENTINEL-PLAIN-3");
    expect(withNoBreakDates("")).toBe("");
    const p = elems(datedRows()[2]!)[0]!;
    expect(p.children).toEqual(["SENTINEL-PLAIN-3"]);
  });

  it("lead, section lead and closing notes get the same treatment; title and labels are untouched; stamp is never wrapped", () => {
    expect(formatDateTime("2026-10-28T00:00:00+00:00")).not.toMatch(/\d{4}-\d{2}-\d{2}/);
    const stamp = formatDateTime("2026-10-28T00:00:00+00:00");
    const b = datedBlock();
    b.lead_template = "LEAD 2026-11-11 {read_at}";
    b.sections[0]!.lead = "SLEAD 2026-11-11";
    b.title = "TITLE 2026-11-11";
    b.closing_notes = ["CLOSE 2026-11-11"];
    const node = blockNode(renderBlock(b));
    const [h2, lead, sec] = elems(node);
    const closing = byTestId(node, "pending-exit-closing")[0]!;
    expect(all(h2!).filter((n) => n.tag === "span")).toHaveLength(0);
    for (const e of [lead!, elems(sec!)[1]!, closing]) {
      expect(all(e).filter((n) => n.tag === "span").map(text)).toEqual(["2026-11-11"]);
    }
    expect(text(h2!)).toBe("TITLE 2026-11-11");
    expect(text(lead!)).toBe(`LEAD 2026-11-11 ${stamp}`);
    expect(text(closing)).toBe("CLOSE 2026-11-11");
    expect(nowrapViolations(node)).toEqual([]);
  });

  it("never substitutes U+2011 or any other character for the hyphen (r2 constraint 3)", () => {
    const markup = renderBlock(datedBlock());
    expect(markup).not.toContain("\u2011");
    expect(withNoBreakDates("2026-11-11")).toMatchObject({ props: { children: [expect.objectContaining({ props: expect.objectContaining({ children: "2026-11-11" }) })] } });
    const src = readFileSync(new URL("../PendingExitBlock.tsx", import.meta.url), "utf8");
    expect(src).not.toMatch(/\u2011|\u2010|\u00ad/i);
    expect(src).not.toContain("\u2011");
  });

  it("the guard turns red when nowrap appears anywhere but on a bare date span", () => {
    const bad = (m: string) => parse(m);
    expect(nowrapViolations(bad('<p class="whitespace-nowrap">x</p>'))).toHaveLength(1);
    expect(nowrapViolations(bad('<p><span class="whitespace-nowrap">not a date</span></p>'))).toHaveLength(1);
    expect(nowrapViolations(bad('<p><span class="whitespace-nowrap" title="x">2026-11-11</span></p>'))).toHaveLength(1);
    expect(nowrapViolations(bad('<p><span class="a whitespace-nowrap">2026-11-11</span></p>'))).toHaveLength(1);
    expect(nowrapViolations(bad('<div><span class="whitespace-nowrap">2026-11-11</span></div>'))).toHaveLength(1);
    expect(nowrapViolations(bad('<section class="text-nowrap"><p>x</p></section>'))).toHaveLength(1);
    expect(nowrapViolations(bad('<p><span class="whitespace-nowrap">2026-11-11</span></p>'))).toHaveLength(0);
  });

  it("the source keeps exactly one nowrap token, on the date span", () => {
    const src = readFileSync(new URL("../PendingExitBlock.tsx", import.meta.url), "utf8");
    const code = src.replace(/\/\*[\s\S]*?\*\//g, "").replace(/^\s*\/\/.*$/gm, "");
    expect(code.match(/nowrap/g)).toHaveLength(1);
    expect(code).toContain('className="whitespace-nowrap"');
  });
});

describe("independence (C7, C19, C22, T27)", () => {
  const src = readFileSync(new URL("../PendingExitBlock.tsx", import.meta.url), "utf8");
  const code = src.replace(/\/\*[\s\S]*?\*\//g, "").replace(/^\s*\/\/.*$/gm, "");

  it("imports only the today query, format and types; no receipt store, mutation or other hook", () => {
    const imports = [...code.matchAll(/from "([^"]+)"/g)].map((m) => m[1]);
    expect(imports.sort()).toEqual(["../lib/format", "../lib/queries", "../lib/types", "react"]);
    expect(code).toContain("usePlaybookToday(true)");
    expect(code).not.toMatch(/useEmergencyExit|useMutation|useQueryClient|ReceiptStore|exitReceipt|useConfirmPlaybookRules|setQueryData/);
  });

  it("T27: never reads pending_exit_directives (source)", () => {
    expect(code).not.toContain("pending_exit_directives");
    expect(code).not.toContain("entry_before_exit_directives");
  });

  it("T27: raw pending_exit_directives in the response never reach the screen", () => {
    state.status = "success";
    const raw = {
      ...body(block()),
      pending_exit_directives: [
        { symbol: "LEAK", action: "sell", text: "SENTINEL-RAW-LEAK", shares: 1, entry_before_exit_note: "SENTINEL-RAW-NOTE" },
      ],
    };
    state.today = raw;
    expect(renderToStaticMarkup(createElement(PendingExitBlock))).not.toContain("SENTINEL-RAW");
    // Same block, different raw list: the block's markup is unchanged.
    state.today = { ...raw, pending_exit_directives: [] };
    const a = renderToStaticMarkup(createElement(PendingExitBlock));
    state.today = { ...raw, pending_exit_directives: undefined };
    expect(renderToStaticMarkup(createElement(PendingExitBlock))).toBe(a);
  });

  it("T27: with a null block, a populated raw list renders nothing", () => {
    state.status = "success";
    state.today = {
      ...body(null),
      pending_exit_directives: [{ symbol: "LEAK", text: "SENTINEL-RAW-LEAK" }],
    };
    const markup = renderToStaticMarkup(createElement(ExitReceiptStoreProvider, null, createElement(PlaybookPage)));
    expect(markup).not.toContain("SENTINEL-RAW-LEAK");
    expect(markup).not.toContain("pending-exit-block");
  });

  it("T27: no other source under app/ (outside tests and types) reads pending_exit_directives to render", () => {
    for (const f of ["../page.tsx", "../DirectiveLedger.tsx", "../ModeStatusBar.tsx", "../ExitReceiptBanner.tsx"]) {
      expect(readFileSync(new URL(f, import.meta.url), "utf8")).not.toContain("pending_exit_directives");
    }
  });

  it("the block draws no text of its own: every text node is a passed-in sentinel or the stamp", () => {
    const node = blockNode(renderBlock(block()));
    const stamp = formatDateTime("2026-10-28T00:00:00+00:00");
    for (const e of all(node)) {
      for (const c of e.children) {
        if (typeof c === "string") expect(c.replaceAll(stamp, "")).toMatch(/^[ A-Za-z0-9-]*$/);
      }
    }
  });
});

describe("NB-6 panel, paragraph 2 (風控 N171A 解讀點 3 (d), C8)", () => {
  it("renders the second version's paragraph in full: one p, textContent equal, no fold or clamp", () => {
    const markup = renderToStaticMarkup(
      createElement(ExitFailurePanel, { wording: EXIT_FAILURE_WORDING, scrollContainerRef: { current: null } }),
    );
    const ps = all(parse(markup)).filter((e) => e.tag === "p");
    expect(ps).toHaveLength(4);
    const second = ps[2]!;
    expect(text(second)).toBe(EXIT_FAILURE_WORDING.body[1]);
    expect(text(second).length).toBe(EXIT_FAILURE_WORDING.body[1].length);
    expect(second.children).toHaveLength(1);
    expect(second.attrs["class"]).toBe("mt-2 text-sm text-neutral-300");
    expect(markup).not.toMatch(/truncate|line-clamp|overflow-|max-h-|<details|<summary|hidden/);
    // The second version's own marks: three sentences, the 11-03 clauses are gone.
    expect(text(second).match(/。/g)).toHaveLength(3);
    expect(text(second)).toContain("所屬批次在帳冊仍記為持有");
    expect(text(second)).toContain("該區塊沒有出現或未列出某一批，不代表這次未受理");
    expect(text(second)).not.toContain("會列出目前尚未結算");
    expect(text(second)).not.toContain("該區塊沒有出現，");
    expect(text(second)).not.toContain("指令結算後也不再列於該區塊");
  });
});

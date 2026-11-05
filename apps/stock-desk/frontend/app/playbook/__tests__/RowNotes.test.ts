/**
 * N-168 same-row notes (art spec 2026-11-04 r1): DirectiveRow (1.3),
 * PositionSnapshotTable (3.2), collectRowNotes (7.1), withNoBreakDates (6).
 * Runs on renderToStaticMarkup (no jsdom); geometry and computed styles are
 * qa-e2e's VP-168 clauses. Sentinel strings only: no real wording is retyped.
 */
import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";
import { collectRowNotes } from "../../lib/rowNotes";
import type { PlaybookBatchSnapshot, PlaybookDirectiveLine } from "../../lib/types";
import { DirectiveLedger } from "../DirectiveLedger";
import { PositionSnapshotTable } from "../PositionSnapshotTable";

const LONG = `SENTINEL-LONG ${"長".repeat(310)} 2026-11-11 與 2026-11-12。`;

function line(note?: string | null, withKey = true): PlaybookDirectiveLine {
  const base: PlaybookDirectiveLine = {
    line: "賣出｜100 股｜規則 S2｜x｜依據資料日 2026-11-03｜預定執行日 2026-11-04｜參考價 10",
    directive: {
      symbol: "2330",
      batch_no: null,
      action: "sell",
      shares: 100,
      rule_id: "S2",
      rule_summary: "SENTINEL-SUMMARY",
      data_date: "2026-11-03",
      execution_date: "2026-11-04",
      reference_price: "10",
      limit_low: null,
      limit_high: null,
      limit_note: "SENTINEL-LIMIT",
      data_status: "fresh",
      source: "SENTINEL-SRC",
      data_reason: null,
      status: "pending",
    },
  };
  return withKey ? { ...base, entry_before_exit_note: note ?? null } : base;
}

function ledger(item: PlaybookDirectiveLine): string {
  return renderToStaticMarkup(
    createElement(DirectiveLedger, { directives: [item], dataDate: "2026-11-03", noDirectiveNote: null }),
  );
}

function batch(
  n: number,
  extra: Partial<PlaybookBatchSnapshot> = {},
): PlaybookBatchSnapshot {
  return {
    symbol: "2330",
    batch_no: n,
    status: "open",
    entry_date: null,
    cost: "10",
    close: "11",
    remaining_shares: 100,
    peak_close: "12",
    unrealized_pct: "10",
    ...extra,
  } as PlaybookBatchSnapshot;
}

function table(snapshot: PlaybookBatchSnapshot[]): string {
  return renderToStaticMarkup(
    createElement(PositionSnapshotTable, {
      snapshot,
      dataDate: "2026-11-03",
      asOf: "2026-11-03T08:00:00+00:00",
    }),
  );
}

const text = (html: string) => html.replace(/<[^>]+>/g, "");

describe("collectRowNotes", () => {
  it("drops missing, null and empty strings; keeps text verbatim", () => {
    expect(collectRowNotes({})).toEqual([]);
    expect(collectRowNotes({ entry_before_exit_note: null })).toEqual([]);
    expect(collectRowNotes({ entry_before_exit_note: "" })).toEqual([]);
    expect(collectRowNotes({ entry_before_exit_note: "A  B。C" })).toEqual(["A  B。C"]);
  });

  it("returns the composed W-B2LS+W-B2LSr string as ONE entry (C-1)", () => {
    const composed = "SENTINEL-LS。SENTINEL-LSr。";
    expect(collectRowNotes({ entry_before_exit_note: composed })).toEqual([composed]);
  });

  it("only the W-B2L family is wired: N-188/N-189 slots render nothing", () => {
    const extra = { n188: "X", n189_d1: "Y", n189_d2: "Z", entry_before_exit_note: "W" };
    expect(collectRowNotes(extra)).toEqual(["W"]);
  });
});

describe("DirectiveRow note", () => {
  it("renders row-notes between the grid and limit_note, one p, spec 1.3 classes", () => {
    const html = ledger(line("SENTINEL-NOTE"));
    expect(html).toContain('data-testid="row-notes" class="mt-2 space-y-1"');
    expect(html).toContain('<p class="break-words text-sm text-neutral-300">SENTINEL-NOTE</p>');
    const grid = html.indexOf("sm:grid-cols-3");
    const notes = html.indexOf('data-testid="row-notes"');
    const limit = html.indexOf("SENTINEL-LIMIT");
    expect(grid).toBeLessThan(notes);
    expect(notes).toBeLessThan(limit);
    // never spliced into `line`
    expect(html.match(/SENTINEL-NOTE/g)).toHaveLength(1);
  });

  it.each([
    ["null", line(null)],
    ["empty string", line("")],
    ["missing key", line(undefined, false)],
  ])("renders no container when the note is %s (SEAM-T8 shape)", (_n, item) => {
    const html = ledger(item);
    expect(html).not.toContain("row-notes");
    expect(html).toContain("SENTINEL-LIMIT");
  });

  it("shows a ~310-char sentence whole: no truncation, folding or tooltip", () => {
    const html = ledger(line(LONG));
    const box = html.slice(html.indexOf('data-testid="row-notes"'), html.indexOf("SENTINEL-LIMIT"));
    expect(text(box).replace(/^[^S]*/, "")).toContain(LONG);
    expect(box).not.toMatch(/truncate|line-clamp|overflow|max-h|break-all|title=|aria-|<details|hidden|sr-only/);
  });

  it("wraps ISO dates in nowrap spans only, containers never nowrap", () => {
    const html = ledger(line(LONG));
    const box = html.slice(html.indexOf('data-testid="row-notes"'), html.indexOf("SENTINEL-LIMIT"));
    expect(box.match(/<span class="whitespace-nowrap">\d{4}-\d{2}-\d{2}<\/span>/g)).toHaveLength(2);
    expect(box.replace(/<span class="whitespace-nowrap">[^<]*<\/span>/g, "")).not.toContain("whitespace-nowrap");
  });
});

describe("PositionSnapshotTable sub-row", () => {
  const html = table([
    batch(1, { entry_before_exit_label: "SENTINEL-LABEL", entry_before_exit_note: "SENTINEL-NOTE 2026-11-11" }),
    batch(2),
    batch(3, { entry_before_exit_label: "SENTINEL-LABEL-C", entry_before_exit_note: LONG }),
  ]);

  it("emits a sub-row only for batches with a label or note", () => {
    expect(html.match(/data-testid="snapshot-batch-row"/g)).toHaveLength(3);
    expect(html.match(/data-testid="snapshot-note-row"/g)).toHaveLength(2);
    const second = html.split('data-testid="snapshot-batch-row"')[2] ?? "";
    expect(second.split("</tr>")[1] ?? "").not.toContain("snapshot-note-row");
  });

  it("puts label above notes inside the sticky pin, single td colSpan=6", () => {
    expect(html).toContain('<td colSpan="6" class="px-3 pb-3 pt-0">');
    expect(html).toContain('data-testid="snapshot-note-pin" class="sticky left-3 w-[calc(100cqw-1.5rem)]"');
    expect(html).toContain('<p class="break-words text-sm font-semibold text-neutral-100">SENTINEL-LABEL</p>');
    expect(html.indexOf("SENTINEL-LABEL<")).toBeLessThan(html.indexOf('data-testid="row-notes" class="mt-1 space-y-1"'));
    expect(html).toContain('<span class="whitespace-nowrap">2026-11-11</span>');
  });

  it("keeps column widths: @container scroller, min-w-[640px], batch cells nowrap, pb-1 pt-2 only with sub-row", () => {
    expect(html).toContain("@container mt-3 overflow-x-auto");
    expect(html).toContain("min-w-[640px]");
    const rows = html.split('data-testid="snapshot-batch-row"').slice(1);
    expect(rows[0]).toContain("whitespace-nowrap px-3 pb-1 pt-2");
    const plain = (rows[1] ?? "").split("</tr>")[0] ?? "";
    expect(plain).toContain("whitespace-nowrap px-3 py-2");
    expect(plain).not.toContain("pb-1");
  });

  it("renders the long sentence whole, new nodes carry no nowrap/overflow/title", () => {
    const sub = html.slice(html.lastIndexOf('data-testid="snapshot-note-row"'));
    expect(text(sub)).toContain(LONG);
    const noDates = sub.replace(/<span class="whitespace-nowrap">[^<]*<\/span>/g, "");
    expect(noDates).not.toMatch(/nowrap|truncate|line-clamp|overflow|max-h|break-all|title=|aria-|hidden/);
  });

  it("renders label-only and note-only without an empty container", () => {
    const labelOnly = table([batch(1, { entry_before_exit_label: "SENTINEL-L" })]);
    expect(labelOnly).toContain("snapshot-note-row");
    expect(labelOnly).not.toContain("row-notes");
    const noteOnly = table([batch(1, { entry_before_exit_note: "SENTINEL-N" })]);
    expect(noteOnly).toContain("row-notes");
    expect(noteOnly).not.toContain("mt-1 space-y-1");
    expect(noteOnly).not.toContain('<p class="break-words text-sm font-semibold');
  });

  it("old body without the keys renders no sub-row", () => {
    const old = table([batch(1)]);
    expect(old).not.toContain("snapshot-note-row");
    expect(old).toContain("whitespace-nowrap px-3 py-2");
  });
});

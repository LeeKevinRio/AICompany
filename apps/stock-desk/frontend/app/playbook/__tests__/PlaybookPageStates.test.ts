/**
 * FE-T4 (tech-architect Q14): `PlaybookPage` rendered with `renderToStaticMarkup`
 * in the four `/today` states — pending, error without data, error *with* data
 * (a failed background refetch), success — each with and without a receipt.
 *
 * It asserts the structure the 風控 floor and 視覺規範 §2.1 / §10 (方案 B) rest on:
 * exactly one 「全部出清」 trigger in every state; exactly one `role="status"`
 * container, the h1 row's next sibling, holding the receipt; the status bar (and
 * only the status bar) gated by `today.isSuccess`; the banner keeping its
 * `mode_reason` unless the bar is mounted and shows the identical sentence.
 *
 * Static markup cannot show live behaviour (node identity across a state change,
 * focus, scroll, per-frame counts); those are qa-e2e's FE-T12 list. What it can
 * show is that each single frame is built correctly.
 */

import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { ApiError } from "../../lib/api";
import type { ExitReceipt } from "../../lib/exitReceipt";
import type { PlaybookTodayResponse } from "../../lib/types";
import type { EmergencyExitFlow } from "../useEmergencyExitFlow";
import { MODE_LABEL, MODE_REASON, receiptResponse, todayResponse } from "./pageFixtures";

const flowState = vi.hoisted(() => ({ receipt: null as ExitReceipt | null, isOpen: false }));

// Only the flow hook is replaced (it needs a QueryClient mutation and React
// state); `usePlaybookToday` stays real and reads the QueryClient seeded below.
vi.mock("../useEmergencyExitFlow", () => ({
  useEmergencyExitFlow: (): EmergencyExitFlow => ({
    isOpen: flowState.isOpen,
    open: () => undefined,
    close: () => undefined,
    submit: () => undefined,
    receipt: flowState.receipt,
    isPending: false,
    isError: false,
    lockRef: { current: false },
    triggerRef: { current: null },
    focusLostRef: { current: false },
    bannerRef: { current: null },
    statusBarRef: { current: null },
  }),
}));

const { default: PlaybookPage } = await import("../page");

type TodayState = "pending" | "error-no-data" | "error-with-data" | "success";
const STATES: TodayState[] = ["pending", "error-no-data", "error-with-data", "success"];

function render(state: TodayState, today = todayResponse()): string {
  const client = new QueryClient({ defaultOptions: { queries: { retryOnMount: false } } });
  const key = ["playbook-today"];
  if (state === "success") {
    client.setQueryData(key, today);
  } else if (state !== "pending") {
    const query = client
      .getQueryCache()
      .build<PlaybookTodayResponse, Error, PlaybookTodayResponse>(client, {
        queryKey: key,
        queryFn: () => Promise.reject(new Error("unused")),
      });
    query.setState({
      status: "error",
      fetchStatus: "idle",
      error: new ApiError("boom", 500),
      errorUpdatedAt: Date.now(),
      ...(state === "error-with-data" ? { data: today, dataUpdatedAt: Date.now() - 60_000 } : {}),
    });
  }
  return renderToStaticMarkup(
    createElement(QueryClientProvider, { client }, createElement(PlaybookPage)),
  );
}

function count(haystack: string, needle: string): number {
  return haystack.split(needle).length - 1;
}

/** The markup between the first `<main` and its closing tag. */
function mainOf(markup: string): string {
  const start = markup.indexOf("<main");
  const end = markup.indexOf("</main>");
  expect(start).toBeGreaterThan(-1);
  return markup.slice(start, end);
}

const H1_ROW_OPEN = '<div class="flex items-center justify-between gap-3">';
const TRIGGER_BUTTON = "全部出清</button>";

beforeEach(() => {
  flowState.receipt = null;
  flowState.isOpen = false;
});

describe.each(STATES)("PlaybookPage with /today = %s", (state) => {
  it("has exactly one 全部出清 trigger", () => {
    expect(count(render(state), TRIGGER_BUTTON)).toBe(1);
  });

  it("has exactly one role=status inside <main>, the h1 row's next sibling, empty when there is no receipt", () => {
    const main = mainOf(render(state));
    expect(count(main, 'role="status"')).toBe(1);
    // Right after the h1 row's closing tag, class-less and empty (FE-C6, V-26).
    expect(main).toMatch(/<\/div><div role="status"><\/div>/);
    const rowEnd = main.indexOf('<div role="status">');
    expect(main.slice(main.indexOf(H1_ROW_OPEN), rowEnd).endsWith("</div>")).toBe(true);
  });

  it("the h1 row is the first child of <main> and carries no background, border, shadow, role or label (V-33)", () => {
    const main = mainOf(render(state));
    expect(main).toMatch(/^<main[^>]*>/);
    expect(main.replace(/^<main[^>]*>/, "").startsWith(H1_ROW_OPEN)).toBe(true);
    // The row's own tag: one class list, nothing that could paint a bar.
    expect(H1_ROW_OPEN).not.toMatch(/\b(bg-|border|shadow|sticky|fixed|backdrop|aria-|role=|id=)/);
    const row = main.slice(main.indexOf(H1_ROW_OPEN), main.indexOf('<div role="status"'));
    expect(row).not.toMatch(/(狀態|模式)/);
    expect(row).not.toMatch(/aria-|role=/);
  });

  it("with a receipt, the banner is inside that same role=status container, before everything else", () => {
    flowState.receipt = { seq: 1, response: receiptResponse() };
    const main = mainOf(render(state));
    const container = main.indexOf('<div role="status">');
    const banner = main.indexOf("SENTINEL-RECEIPT-MESSAGE");
    expect(container).toBeGreaterThan(-1);
    expect(banner).toBeGreaterThan(container);
    // Banner text is followed by its own closing div(s) and then the page body
    // (skeleton / error panel / content): nothing of the banner sits after them.
    expect(count(main, "SENTINEL-RECEIPT-MESSAGE")).toBe(1);
    // message, mode_reason (kept here: no bar, or a different sentence), attribution,
    // warnings: one container, in the signed-off order (風控 必改項 6).
    const attribution = main.indexOf("SENTINEL-RECEIPT-ATTRIBUTION");
    const warning = main.indexOf("SENTINEL-RECEIPT-WARNING");
    expect(banner).toBeLessThan(attribution);
    expect(attribution).toBeLessThan(warning);
    // The container closes right after the banner: the page body follows it.
    const containerEnd = main.indexOf("</ul></div></div>", warning);
    expect(containerEnd).toBeGreaterThan(warning);
  });

  it("a receipt adds no second status container and no second trigger", () => {
    flowState.receipt = { seq: 3, response: receiptResponse() };
    const markup = render(state);
    expect(count(mainOf(markup), 'role="status"')).toBe(1);
    expect(count(markup, TRIGGER_BUTTON)).toBe(1);
  });
});

describe("the status bar and the trigger's placement follow today.isSuccess alone (FE-C12, V-36)", () => {
  it("success: the sticky bar holds the trigger; the h1 row holds only the heading", () => {
    const markup = render("success");
    const beforeMain = markup.slice(0, markup.indexOf("<main"));
    expect(beforeMain).toContain("sticky top-0");
    expect(count(beforeMain, TRIGGER_BUTTON)).toBe(1);
    const row = markup.slice(markup.indexOf(H1_ROW_OPEN), markup.indexOf('<div role="status"'));
    expect(row).toBe(`${H1_ROW_OPEN}<h1 class="text-2xl font-bold text-neutral-100">排程台</h1></div>`);
  });

  it.each(["pending", "error-no-data", "error-with-data"] as const)(
    "%s: no sticky bar anywhere; the h1 row is the heading plus the trigger and nothing else",
    (state) => {
      const markup = render(state);
      expect(markup).not.toContain("sticky");
      expect(markup).not.toContain("backdrop");
      expect(markup).not.toMatch(/(?<![\w-])fixed(?![\w-])/);
      expect(markup.slice(0, markup.indexOf("<main"))).not.toContain(TRIGGER_BUTTON);
      const row = markup.slice(markup.indexOf(H1_ROW_OPEN), markup.indexOf('<div role="status"'));
      expect(row.replace(/<[^>]+>/g, "|").split("|").filter(Boolean)).toEqual(["排程台", "全部出清"]);
    },
  );

  it("the trigger carries no label, title, description or disabled state in any state (風控 F-4)", () => {
    for (const state of STATES) {
      const markup = render(state);
      const start = markup.lastIndexOf("<button", markup.indexOf(TRIGGER_BUTTON));
      const button = markup.slice(start, markup.indexOf(TRIGGER_BUTTON) + TRIGGER_BUTTON.length);
      expect(button).not.toMatch(/aria-|title=|disabled|hidden|inert/);
      expect(button).toContain("border-neutral-600");
      expect(button).not.toMatch(/(rose|red|amber|orange)-/);
    }
  });

  it("a failed background refetch renders the load-failure panel and never the stale mode (風控 必改項 3, V-19)", () => {
    const markup = render("error-with-data");
    expect(markup).toContain("無法載入排程台資料");
    expect(markup).not.toContain(MODE_LABEL);
    expect(markup).not.toContain("SENTINEL-SUMMARY-ONE");
    expect(markup).not.toContain("SENTINEL-ATTRIBUTION");
  });
});

describe("the receipt's mode_reason paragraph (FR-5, F-6, V-16/V-17/V-20)", () => {
  it("success + identical sentence: shown once, in the status bar only — the banner paragraph is unmounted", () => {
    flowState.receipt = { seq: 1, response: receiptResponse({ mode_reason: MODE_REASON }) };
    const markup = render("success");
    expect(count(markup, MODE_REASON)).toBe(1);
    expect(markup.indexOf(MODE_REASON)).toBeLessThan(markup.indexOf("<main"));
    // Removal is unmounting: no hidden copy, no reserved height (風控 必改項 5).
    const container = mainOf(markup);
    const banner = container.slice(container.indexOf('<div role="status">'), container.indexOf("SENTINEL-SUMMARY-ONE"));
    expect(banner).toContain("SENTINEL-RECEIPT-MESSAGE");
    expect(banner).not.toMatch(/sr-only|aria-hidden|invisible|min-h-|visibility|display/);
  });

  it("success + a different sentence: both are shown (never zero)", () => {
    flowState.receipt = { seq: 1, response: receiptResponse({ mode_reason: `${MODE_REASON}.` }) };
    const markup = render("success");
    expect(count(markup, MODE_REASON)).toBe(2); // the bar's, and the banner's superstring
    expect(mainOf(markup)).toContain(`${MODE_REASON}.`);
  });

  it("success + a sentence differing only by whitespace: not hidden (strict equality)", () => {
    flowState.receipt = { seq: 1, response: receiptResponse({ mode_reason: ` ${MODE_REASON}` }) };
    expect(mainOf(render("success"))).toContain(` ${MODE_REASON}`);
  });

  it.each(["pending", "error-no-data", "error-with-data"] as const)(
    "%s: the banner keeps it, even when /today's own sentence is identical — the page total is never 0",
    (state) => {
      flowState.receipt = { seq: 1, response: receiptResponse({ mode_reason: MODE_REASON }) };
      const markup = render(state);
      expect(count(markup, MODE_REASON)).toBe(1);
      expect(mainOf(markup)).toContain(MODE_REASON);
    },
  );
});

describe("the dialog is a sibling outside <main>, mounted on isOpen alone (FE-C11)", () => {
  it.each(STATES)("%s: opening it does not change the page structure", (state) => {
    const closed = render(state);
    flowState.isOpen = true;
    const open = render(state);
    // SSR renders no portal (client-mount gate), so the markup is unchanged: the
    // dialog adds nothing to, and removes nothing from, the gated page.
    expect(open).toBe(closed);
  });
});

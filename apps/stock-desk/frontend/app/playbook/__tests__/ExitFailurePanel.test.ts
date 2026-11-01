/**
 * The 出清失敗面板 (視覺規範 §11, V-39 / V-40; PRD FR-8b, AC-29): structure and
 * class contract, with sentinel text. The signed-off wording itself is pinned
 * against `wording.py` in `app/lib/__tests__/exitWordingMirror.test.ts`; here the
 * panel is shown to render whatever it is given, verbatim and separately.
 */

import { readFileSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";
import { ExitFailurePanel, type ExitFailureWording } from "../ExitFailurePanel";

const WORDING: ExitFailureWording = {
  label: "SENTINEL-LABEL",
  body: ["SENTINEL-BODY-ONE", "SENTINEL-BODY-TWO", "SENTINEL-BODY-THREE"],
};

function render(wording: ExitFailureWording = WORDING): string {
  return renderToStaticMarkup(
    createElement(ExitFailurePanel, { wording, scrollContainerRef: { current: null } }),
  );
}

describe("ExitFailurePanel structure (V-40)", () => {
  it("is one alert with exactly four separate paragraphs: the label, then three sentences, in order", () => {
    const markup = render();
    expect(markup.match(/<p /g)).toHaveLength(4);
    expect(markup).not.toContain("<br");
    expect(markup.match(/role="alert"/g)).toHaveLength(1);
    const texts = [...markup.matchAll(/<p [^>]*>([^<]*)<\/p>/g)].map((m) => m[1]);
    expect(texts).toEqual(["SENTINEL-LABEL", "SENTINEL-BODY-ONE", "SENTINEL-BODY-TWO", "SENTINEL-BODY-THREE"]);
  });

  it("renders the given text verbatim and appends nothing (no backend message, status or exception)", () => {
    const markup = render();
    expect(markup.replace(/<[^>]+>/g, "")).toBe(
      "SENTINEL-LABEL" + "SENTINEL-BODY-ONE" + "SENTINEL-BODY-TWO" + "SENTINEL-BODY-THREE",
    );
  });

  it("uses the signed-off classes: label semibold neutral-100, sentences neutral-300 with mt-2", () => {
    const markup = render();
    expect(markup).toContain(
      '<div role="alert" class="mt-4 rounded-md border border-neutral-500 bg-neutral-900 px-4 py-3">',
    );
    expect(markup).toContain('<p class="text-sm font-semibold text-neutral-100">SENTINEL-LABEL</p>');
    for (const body of WORDING.body) {
      expect(markup).toContain(`<p class="mt-2 text-sm text-neutral-300">${body}</p>`);
    }
  });

  it("is neutral grey only: no colour token, no left border, no icon, no animation", () => {
    const markup = render();
    expect(markup).not.toMatch(/(rose|red|amber|orange|yellow|emerald|sky|indigo|violet|teal)-/);
    expect(markup).not.toMatch(/border-l-|text-red|bg-red/);
    expect(markup).not.toMatch(/<svg|<img|transition|animate|shadow/);
  });

  it("never takes focus, never clips, never closes (N-163, V-40)", () => {
    const markup = render();
    expect(markup).not.toMatch(/tabindex|<button|aria-describedby|aria-live/i);
    expect(markup).not.toMatch(/max-h|overflow|line-clamp|truncate/);
  });

  it("is not the shared ErrorPanel, and the shared ErrorPanel is untouched (AC-29)", () => {
    const here = dirname(fileURLToPath(import.meta.url));
    const panel = readFileSync(resolve(here, "../ExitFailurePanel.tsx"), "utf-8").replace(
      /\/\*[\s\S]*?\*\//g,
      "",
    );
    expect(panel).not.toMatch(/ErrorPanel/);
    const shared = readFileSync(resolve(here, "../../components/ErrorPanel.tsx"), "utf-8");
    expect(shared).toContain("border-red-900 bg-red-950/40");
    expect(shared).toContain("{label}：{error instanceof ApiError ? error.message : \"未知錯誤\"}");
  });

  it("reveals its label by scrolling the dialog's container, never by focus or scrollIntoView", () => {
    const here = dirname(fileURLToPath(import.meta.url));
    const panel = readFileSync(resolve(here, "../ExitFailurePanel.tsx"), "utf-8").replace(
      /\/\*[\s\S]*?\*\//g,
      "",
    );
    expect(panel).toContain('container.scrollTo({ top: container.scrollTop + delta, behavior: "auto" })');
    expect(panel).not.toMatch(/\.focus\(|scrollIntoView|smooth/);
  });
});

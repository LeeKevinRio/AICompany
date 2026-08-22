/**
 * 條件 74 (`work/reviews/2026-08-19-C5-Kelly-文案批審.md`, "入口閘門,最重"):
 * every front-end path to `POST /api/kelly-inputs/{symbol}/import-backtest`
 * must go through `KellyImportDialog.tsx`'s confirm handler — no second entry
 * point anywhere in the app. The wiring is two layers
 * (`app/lib/api.ts`'s `importKellyBacktest` -> `app/lib/queries.ts`'s
 * `useImportKellyBacktest` -> `KellyImportDialog.tsx`), so the gate is two
 * call-site-count assertions, one per layer: nobody but the query hook may
 * call the raw API function, and nobody but the dialog may call the hook.
 * Either count going to 2 means a second entry point was added and this test
 * fails the build rather than waiting for a review to catch it.
 */

import { readdirSync, readFileSync, statSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { join, relative } from "node:path";
import { describe, expect, it } from "vitest";
import { stripComments } from "./wordingScanHelpers";

const APP_ROOT = fileURLToPath(new URL("../../", import.meta.url));
//: This file's own path (absolute) — excluded from the scan below. Its test
//: descriptions and doc comment necessarily *name* both guarded identifiers
//: as literal call-shaped substrings (`` `importKellyBacktest(` ``) to explain
//: what the guard checks, which would otherwise count as a third call site of
//: its own and make this test self-defeating.
const SELF_PATH = fileURLToPath(import.meta.url);

function listSourceFiles(dir: string): string[] {
  const entries = readdirSync(dir);
  const files: string[] = [];
  for (const entry of entries) {
    const full = join(dir, entry);
    const stat = statSync(full);
    if (stat.isDirectory()) {
      if (entry === "node_modules" || entry === ".next") continue;
      files.push(...listSourceFiles(full));
    } else if (/\.(ts|tsx)$/.test(entry) && full !== SELF_PATH) {
      files.push(full);
    }
  }
  return files;
}

/**
 * Every occurrence of `needle` as a call (`needle(`), one entry per file it
 * appears in, with the count. Comments are stripped first (`stripComments`)
 * so a doc comment that *names* the guarded function in backticks — this
 * file's own doc comment does exactly that, and so does
 * `KellyImportDialog.tsx`'s — is not itself counted as a call site.
 */
function callSitesOf(needle: string, files: string[]): Map<string, number> {
  const sites = new Map<string, number>();
  const pattern = new RegExp(`${needle}\\(`, "g");
  for (const file of files) {
    const source = stripComments(readFileSync(file, "utf-8"));
    const matches = source.match(pattern);
    if (matches && matches.length > 0) {
      sites.set(relative(APP_ROOT, file), matches.length);
    }
  }
  return sites;
}

describe("條件 74 call-site guard — POST .../import-backtest", () => {
  const files = listSourceFiles(APP_ROOT);

  it("`importKellyBacktest(` is called from exactly one file: lib/queries.ts's mutation wrapper (api.ts's own definition line does not match, since a definition reads `function importKellyBacktest(` and this pattern still matches that literal substring — asserted explicitly below)", () => {
    const sites = callSitesOf("importKellyBacktest", files);
    // api.ts necessarily contains one match too (`export function importKellyBacktest(`,
    // the definition itself) — the call-site set is everything *besides* that.
    const callSites = new Map(sites);
    callSites.delete("lib/api.ts");
    expect(Object.fromEntries(callSites)).toEqual({ "lib/queries.ts": 1 });
  });

  it("`useImportKellyBacktest(` is called from exactly one file: settings/KellyImportDialog.tsx", () => {
    const sites = callSitesOf("useImportKellyBacktest", files);
    const callSites = new Map(sites);
    // queries.ts's own `export function useImportKellyBacktest(` definition.
    callSites.delete("lib/queries.ts");
    expect(Object.fromEntries(callSites)).toEqual({ "settings/KellyImportDialog.tsx": 1 });
  });

  it("api.ts's own occurrence of `importKellyBacktest(` is exactly one (the definition, no accidental second copy in that file)", () => {
    const sites = callSitesOf("importKellyBacktest", files);
    expect(sites.get("lib/api.ts")).toBe(1);
  });

  it("queries.ts's own occurrence of `useImportKellyBacktest(` is exactly one (the definition)", () => {
    const sites = callSitesOf("useImportKellyBacktest", files);
    expect(sites.get("lib/queries.ts")).toBe(1);
  });
});

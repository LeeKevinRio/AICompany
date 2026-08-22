/**
 * 條件 108 (第十四輪): `KellyManualInputForm.tsx`'s two field labels are the
 * raw API field names (`win_rate` / `payoff_ratio`, `KellyManualInput`,
 * `app/kelly/models.py`), not a Chinese noun — approved on two conditions:
 *
 * (a) the label text is the field name **verbatim**, no beautification (a
 *     humanised variant like "Win rate" or "win rate" would be new copy and
 *     needs its own submission);
 * (b) the form never renders standalone, outside `KellyDisclosuresPanel`'s
 *     same screen — the Chinese meaning of "勝率"/"盈虧比" is carried by (f)/
 *     (e-manual) and the field-level 422 sentences on *that* panel, and an
 *     English field name with nothing else on screen would mean nothing to a
 *     reader who has not seen those sentences (L13).
 */

import { readFileSync, readdirSync, statSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { join } from "node:path";
import { describe, expect, it } from "vitest";

function readSettingsFile(name: string): string {
  const absolutePath = fileURLToPath(new URL(`../../settings/${name}`, import.meta.url));
  return readFileSync(absolutePath, "utf-8");
}

describe("KellyManualInputForm.tsx — 條件 108(a): labels are the API field names verbatim", () => {
  const source = readSettingsFile("KellyManualInputForm.tsx");

  it("renders `win_rate` as the win-rate field's own label text (not a humanised variant)", () => {
    expect(source).toMatch(/<label htmlFor="kelly-win-rate"[^>]*>\s*win_rate\s*<\/label>/);
  });

  it("renders `payoff_ratio` as the payoff-ratio field's own label text", () => {
    expect(source).toMatch(/<label htmlFor="kelly-payoff-ratio"[^>]*>\s*payoff_ratio\s*<\/label>/);
  });

  it("never beautifies either field name (no capitalised/spaced/'Win Rate'-style variant anywhere in the file)", () => {
    for (const beautified of ["Win rate", "Win Rate", "Payoff ratio", "Payoff Ratio", "win rate", "payoff ratio"]) {
      expect(source).not.toContain(beautified);
    }
  });
});

describe("條件 108(b): KellyManualInputForm never renders outside KellyDisclosuresPanel's own screen", () => {
  const appRoot = fileURLToPath(new URL("../../", import.meta.url));

  function listSourceFiles(dir: string): string[] {
    const entries = readdirSync(dir);
    const files: string[] = [];
    for (const entry of entries) {
      const full = join(dir, entry);
      const stat = statSync(full);
      if (stat.isDirectory()) {
        if (entry === "node_modules" || entry === ".next" || entry === "__tests__") continue;
        files.push(...listSourceFiles(full));
      } else if (/\.tsx$/.test(entry)) {
        files.push(full);
      }
    }
    return files;
  }

  const files = listSourceFiles(appRoot);
  const filesRenderingForm = files.filter((file) =>
    readFileSync(file, "utf-8").includes("<KellyManualInputForm"),
  );
  const filesRenderingPanel = files.filter((file) =>
    readFileSync(file, "utf-8").includes("<KellyDisclosuresPanel"),
  );

  it("at least one production file renders the form (the guard is not vacuous)", () => {
    expect(filesRenderingForm.length).toBeGreaterThan(0);
  });

  it("every file that renders <KellyManualInputForm also renders <KellyDisclosuresPanel — never split across two screens", () => {
    const offenders = filesRenderingForm.filter((file) => !filesRenderingPanel.includes(file));
    expect(offenders).toEqual([]);
  });
});

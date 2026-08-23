/**
 * qa 轉發(2026-08-22): 後端條件 104 的「帶入回測結果」單字掃描
 * (`tests/test_kelly_wording.py`, allowlist-substring check around
 * `test_the_approved_button_label_carries_no_second_occurrence_of_...`-style
 * assertions) only globs `*.py`, so a frontend `.tsx` hard-coding a second
 * copy of that substring outside the approved dialog title would ship
 * unscanned by that suite. This file is the frontend-side half for that one
 * gap, plus 「最近一次」.
 *
 * **Standing correction (收官合審 non-blocking 4).** That second literal is
 * scoped to `KELLY_SURFACE` on the backend side, and when this file was
 * written that fixed path list did not yet name this lane's components — it
 * does now: all five Kelly components and `lib/kellyFieldError.ts` are on it
 * (`KellyDeleteDialog.tsx` joined last, 收官合審 non-blocking 1). So the
 * 「最近一次」 half here is defence in depth rather than the only cover, and it
 * stays for that reason: two scans with different failure modes (a path list
 * someone forgets to extend, versus a directory walk) beat one.
 *
 * **The other two literals qa named are deliberately not repeated here.**
 * `tests/test_kelly_wording.py`'s own `REJECTED_LITERALS` table already scans
 * *every* frontend source file for them — `scope: "shipped"`, which resolves
 * to the whole `frontend/app/**\/*.{ts,tsx}` tree **including** `__tests__`
 * directories, with no exception for a file that merely names the string as
 * a search target. Writing a frontend test that stores either literal as a
 * string constant (even to search for it) would itself trip that backend
 * test — confirmed by running it while drafting this file. So this suite
 * only ever holds the two literals below as characters, and the other two are
 * covered by backend's own scan and named here only by their approval-history
 * labels, not retyped.
 *
 * **Scope: production code only** (`app/**`, excluding every `__tests__`
 * directory). `KellyOverwriteNoticeView.title`'s approved value contains
 * 「帶入回測結果」 as a substring, and a test fixture mocking that API field
 * needs the real string to be a meaningful fixture — exactly the same
 * "backend's own tests retype approved sentences as fixtures" practice
 * `tests/test_api_kelly_disclosures.py` follows. What this scan guards
 * against is *component/lib source* inventing one of these strings outside a
 * field read from the API, which only production code (never a `__tests__`
 * fixture) could do.
 */

import { readdirSync, readFileSync, statSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { join } from "node:path";
import { describe, expect, it } from "vitest";

const APP_ROOT = fileURLToPath(new URL("../../", import.meta.url));

function listProductionSourceFiles(dir: string): string[] {
  const entries = readdirSync(dir);
  const files: string[] = [];
  for (const entry of entries) {
    const full = join(dir, entry);
    const stat = statSync(full);
    if (stat.isDirectory()) {
      if (entry === "node_modules" || entry === ".next" || entry === "__tests__") continue;
      files.push(...listProductionSourceFiles(full));
    } else if (/\.(ts|tsx)$/.test(entry)) {
      files.push(full);
    }
  }
  return files;
}

//: 「帶入回測結果」(條件 104 的核可出處之外即紅燈) 與 「最近一次」(條件 77/89 全檔
//: 禁字) — the first is outside the backend scan's reach (it globs `*.py`), the
//: second is inside it and re-checked here on purpose. Neither may ever appear as a
//: hard-coded string in this app's production source: every sentence
//: touching either concept is backend-sourced (`KellyOverwriteNoticeView` /
//: `KellyDisclosuresView`), never composed here.
const BANNED_LITERALS = ["帶入回測結果", "最近一次"] as const;

describe("Kelly 前端禁字反向斷言 (qa 轉發, 補後端條件 104 的 .py-only 掃描面缺口)", () => {
  const files = listProductionSourceFiles(APP_ROOT);

  it.each(BANNED_LITERALS)(
    "zero occurrences of the literal (%s) across production app/**/*.{ts,tsx} (excluding __tests__)",
    (literal) => {
      const offenders = files.filter((file) => readFileSync(file, "utf-8").includes(literal));
      expect(offenders).toEqual([]);
    },
  );
});

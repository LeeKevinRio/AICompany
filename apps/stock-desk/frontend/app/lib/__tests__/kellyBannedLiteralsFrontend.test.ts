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

//: 風控 2026-10-26 定稿 3-F（全站頁尾）逐字含「不反映最近一次收盤之後的價格變動」。這裡的
//: 「最近一次」指「最近一次收盤」，與 Kelly 條件 77/89 所禁的「最近一次回測／帶入」是兩件事。
//: 例外只開這一個檔、這一句整句，且必須真的存在於該檔（過期或多餘的條目會讓下方斷言轉紅）；
//: 該字面本身仍受 riskRemediationWording.test.ts 逐字釘住。其餘任何檔案出現「最近一次」照舊紅燈。
const ALLOWED_CONTEXTS: ReadonlyArray<{ literal: string; file: string; context: string }> = [
  {
    literal: "最近一次",
    file: join("lib", "riskRemediationWording.ts"),
    context: "不反映最近一次收盤之後的價格變動",
  },
];

/** Production source with the allowed contexts for `literal` masked out (same-length padding). */
function scannableSource(file: string, literal: string): string {
  let source = readFileSync(file, "utf-8");
  for (const allowed of ALLOWED_CONTEXTS) {
    if (allowed.literal !== literal || !file.endsWith(allowed.file)) continue;
    source = source.split(allowed.context).join("\u0000".repeat(allowed.context.length));
  }
  return source;
}

describe("Kelly 前端禁字反向斷言 (qa 轉發, 補後端條件 104 的 .py-only 掃描面缺口)", () => {
  const files = listProductionSourceFiles(APP_ROOT);

  it.each(BANNED_LITERALS)(
    "zero occurrences of the literal (%s) across production app/**/*.{ts,tsx} (excluding __tests__)",
    (literal) => {
      const offenders = files.filter((file) => scannableSource(file, literal).includes(literal));
      expect(offenders).toEqual([]);
    },
  );

  it("每個例外條目都真的存在於指定檔案、且含被禁字面（過期或多餘的例外不得留著）", () => {
    for (const allowed of ALLOWED_CONTEXTS) {
      expect(allowed.context, "例外語境必須含被禁字面，否則是多餘條目").toContain(allowed.literal);
      const file = files.find((f) => f.endsWith(allowed.file));
      expect(file, `${allowed.file} 應存在於 production 掃描範圍`).toBeDefined();
      expect(readFileSync(file!, "utf-8")).toContain(allowed.context);
    }
  });
});

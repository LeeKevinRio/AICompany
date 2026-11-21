# CG-2 登記 PR：M-9 補充核對用證據（RC-496 (a)～(e)，新 head cc9e302）

- 產出者：coordinator（由 dev-lead 以唯讀 git 指令與 scratchpad 腳本產生，coordinator 逐字轉存）
- 日期：2026-11-21
- 新 head：`cc9e30239ad8acbb76706d2bef71b2379b4fac86`；舊 head：`9d5bbf480948d3a94fcef0966293bbfca7702089`（`feat/nm5-cg2-registration`）
- (f) 由 qa 確認句提供：`work/reviews/2026-11-21-CG2登記PR-M9補充最終審查-qa.md` 末段。

```
# RC-496 evidence at new CG-2 head cc9e30239ad8acbb76706d2bef71b2379b4fac86 (old head 9d5bbf480948d3a94fcef0966293bbfca7702089)
# produced by dev-lead, 2026-11-21; read-only git in an isolated worktree checked out at the new head
# (clean work tree); no database opened, no .env* read, nothing committed
## (a) changed files
$ git diff --name-status 9d5bbf480948d3a94fcef0966293bbfca7702089 cc9e30239ad8acbb76706d2bef71b2379b4fac86
M	apps/stock-desk/backend/app/forecast/claims.py
M	apps/stock-desk/backend/scripts/cg2_register.py
M	apps/stock-desk/backend/tests/test_cg2_register_addendum3.py
M	apps/stock-desk/backend/tests/test_cg2_register_flow.py
M	apps/stock-desk/backend/tests/test_cg2_register_values.py
M	apps/stock-desk/backend/tests/test_forecast_claims_bootstrap.py
## (b) no diff in the M-2 / M-3 / M-6 inputs
$ git diff 9d5bbf480948d3a94fcef0966293bbfca7702089 cc9e30239ad8acbb76706d2bef71b2379b4fac86 -- "work/research/2026-10-15-3日5日方向判斷-事先宣告草案.md" "work/dispatch/2026-11-15-C8決策紀錄-F2B.md" "apps/stock-desk/backend/app/outlook/rules/" "apps/stock-desk/backend/app/dirdef/" "apps/stock-desk/backend/app/forecast/definitions.py" "apps/stock-desk/backend/app/advice/banned_phrases.py"
(no output)
$ git diff 9d5bbf480948d3a94fcef0966293bbfca7702089 cc9e30239ad8acbb76706d2bef71b2379b4fac86 -- "work/research/2026-10-15-3日5日方向判斷-事先宣告草案.md" "work/dispatch/2026-11-15-C8決策紀錄-F2B.md" "apps/stock-desk/backend/app/outlook/rules/" "apps/stock-desk/backend/app/dirdef/" "apps/stock-desk/backend/app/forecast/definitions.py" "apps/stock-desk/backend/app/advice/banned_phrases.py" | wc -c
0
$ git ls-files -- <the six paths of (b)>   # the paths exist at the new head
apps/stock-desk/backend/app/advice/banned_phrases.py
apps/stock-desk/backend/app/dirdef/__init__.py
apps/stock-desk/backend/app/dirdef/definition.py
apps/stock-desk/backend/app/dirdef/guard.py
apps/stock-desk/backend/app/dirdef/hashing.py
apps/stock-desk/backend/app/dirdef/registry.py
apps/stock-desk/backend/app/dirdef/rules.py
apps/stock-desk/backend/app/dirdef/strings.py
apps/stock-desk/backend/app/dirdef/v1_0.py
apps/stock-desk/backend/app/forecast/definitions.py
apps/stock-desk/backend/app/outlook/rules/h3.yaml
apps/stock-desk/backend/app/outlook/rules/h5.yaml
work/dispatch/2026-11-15-C8決策紀錄-F2B.md
work/research/2026-10-15-3日5日方向判斷-事先宣告草案.md
## (c) M-2 prereg
$ git rev-parse cc9e30239ad8acbb76706d2bef71b2379b4fac86:"work/research/2026-10-15-3日5日方向判斷-事先宣告草案.md"
d1e4d06a4e1c1a06158ad33a481050fe44bf8ae1
$ git cat-file blob cc9e30239ad8acbb76706d2bef71b2379b4fac86:"work/research/2026-10-15-3日5日方向判斷-事先宣告草案.md" | sha256sum
7c45b0ba79e04a7a74a2b8bc91603cb0bfbd78101b51ab8403cc4ed45a4b406e  -
## (c) M-3 C-8 record
$ git rev-parse cc9e30239ad8acbb76706d2bef71b2379b4fac86:"work/dispatch/2026-11-15-C8決策紀錄-F2B.md"
e664f147f2c5339e321ae333b7ce3c7d35ebcda7
$ git cat-file blob cc9e30239ad8acbb76706d2bef71b2379b4fac86:"work/dispatch/2026-11-15-C8決策紀錄-F2B.md" | sha256sum
c942642c1958e6259545c4f64b4202fbafecf585f1f2cbe513961190af0ea54f  -
## (c) eol
$ git -c core.quotepath=false -C <worktree at cc9e30239ad8acbb76706d2bef71b2379b4fac86> ls-files --eol -- "work/dispatch/2026-11-15-C8決策紀錄-F2B.md" "work/research/2026-10-15-3日5日方向判斷-事先宣告草案.md"
i/lf    w/lf    attr/text eol=lf      	work/dispatch/2026-11-15-C8決策紀錄-F2B.md
i/lf    w/lf    attr/text eol=lf      	work/research/2026-10-15-3日5日方向判斷-事先宣告草案.md
## (d) M-6 banned phrase scan (code at cc9e30239ad8acbb76706d2bef71b2379b4fac86, definitions.registration_phrase_scan)
$ git archive cc9e30239ad8acbb76706d2bef71b2379b4fac86 apps/stock-desk/backend | tar -x -C <scratch>/rc496_py312
$ cd <scratch>/rc496_py312/apps/stock-desk/backend && uv sync --frozen --python 3.12 --no-dev
$ <scratch>/rc496_py312/apps/stock-desk/backend/.venv/bin/python -I -B <scratch>/rc496_tools/phrase_scan.py <scratch>/rc496_py312/apps/stock-desk/backend
# python 3.12.3; app loaded from /tmp/claude-0/-home-user-AICompany/3f76d891-50d3-55e1-b39d-925b8a90241a/scratchpad/rc496_py312/apps/stock-desk/backend
outlook-market-v1.0-h3: hits 0 rules_strings 159 definition_strings 12 phrases 10
    banned phrase scan (NFKC, whitespace and zero-width removed): rules 159 strings, definition 12 strings, 10 phrases, hits 0
outlook-market-v1.0-h5: hits 0 rules_strings 159 definition_strings 12 phrases 10
    banned phrase scan (NFKC, whitespace and zero-width removed): rules 159 strings, definition 12 strings, 10 phrases, hits 0
# phrase_scan.py (full text):
"""M-6 re-run: definitions.registration_phrase_scan for h3 and h5 (no database).

argv: <backend dir extracted from the commit>
"""

import platform
import sys
from pathlib import Path

backend = Path(sys.argv[1]).resolve()
sys.path.insert(0, str(backend))
from app.forecast import claims, definitions  # noqa: E402

assert Path(definitions.__file__).resolve().is_relative_to(backend), definitions.__file__
print(f"# python {platform.python_version()}; app loaded from {backend}")
definition = definitions.get_definition("dirdef-v1.0")
for version in ("outlook-market-v1.0-h3", "outlook-market-v1.0-h5"):
    scan = definitions.registration_phrase_scan(definitions.get_ruleset(version), definition)
    print(
        f"{version}: hits {len(scan.hits)} rules_strings {scan.rules_strings}"
        f" definition_strings {scan.definition_strings} phrases {scan.phrases}"
    )
    for line in claims._phrase_scan_lines(scan):
        print(f"    {line}")
## (e) full diff of the one-click script
$ git diff 9d5bbf480948d3a94fcef0966293bbfca7702089 cc9e30239ad8acbb76706d2bef71b2379b4fac86 -- apps/stock-desk/backend/scripts/cg2_register.py
diff --git a/apps/stock-desk/backend/scripts/cg2_register.py b/apps/stock-desk/backend/scripts/cg2_register.py
index 9b865fd..e1ca317 100644
--- a/apps/stock-desk/backend/scripts/cg2_register.py
+++ b/apps/stock-desk/backend/scripts/cg2_register.py
@@ -100,7 +100,9 @@ def preflight_file_name(stamp: str) -> str:
 
 DB_NAME: Final = "stock-desk.db"
 ENV_VAR: Final = "STOCK_DESK_DB_PATH"
-ENV_KEY_PATTERN: Final = re.compile(r"^\s*STOCK_DESK_DB_PATH\s*=")
+#: An ``.env`` line setting the key: optional ``export`` prefix, any case (as ``_ENV_FILE_KEY`` of
+#: ``app.forecast.claims``; a test keeps the pattern and the flags equal).
+ENV_KEY_PATTERN: Final = re.compile(r"^\s*(?:export\s+)?STOCK_DESK_DB_PATH\s*=", re.IGNORECASE)
 PORT: Final = 8000
 #: The two ledger prefixes (``app.forecast.schema.LEDGER_PREFIXES``; a test keeps them equal).
 LEDGER_PREFIXES: Final = ("forecast_", "plan_")
@@ -171,7 +173,7 @@ REAL_PINS: Final = Pins(
             "0a385de3e2f4118bc1e7c2c5dd1a667ce0a9067399ccd1b6e7c4dbab19d5707c",
         ),
     ),
-    app_tree_id="9c157d8640fb97d7e90dc7edc3f5ff0252aa00d7",
+    app_tree_id="d631a75a4aba2ace76c44e8647d1bd11180662d5",
     definition_version=DEFINITION_VERSION,
     definition_sha256="2a58bca61c647931ecaf56aa5d17e4bfffc048c30944f3550feceadbfdacc4d0",
     definition_logic_sha256="4cc1fe80054a017f47030805a486ad81e1bda249d730c7c1f6bd2c73c01d1afa",
@@ -190,7 +192,8 @@ REAL_PINS: Final = Pins(
         ),
     ),
     # Final list (coordinator, addendum 3 point 4): records that approve or check the content.
-    # The last two are written after the final review; until they are in HEAD the run time
+    # The M-9 records (the two of 2026-11-17 and their two 2026-11-21 supplements for the
+    # re-pinned head) are written after the final review; until they are in HEAD the run time
     # check (check_review_refs) stops, which is the intended state.
     review_refs=(
         "work/reviews/2026-11-15-凍結包第2輪單項確認-風控.md",
@@ -198,6 +201,8 @@ REAL_PINS: Final = Pins(
         "work/reviews/2026-11-15-C8決策紀錄檔確認-風控.md",
         "work/reviews/2026-11-17-CG2登記PR-M9核對M2M3M6-風控.md",
         "work/reviews/2026-11-17-CG2登記PR-M9最終審查-qa.md",
+        "work/reviews/2026-11-21-CG2登記PR-M9補充核對M2M3M6-風控.md",
+        "work/reviews/2026-11-21-CG2登記PR-M9補充最終審查-qa.md",
     ),
 )

## note: where the M-9 records live
$ git -c core.quotepath=false ls-tree --name-only origin/product/stock-desk work/reviews/ | grep "CG2登記PR-M9"   # origin/product/stock-desk = d56cd7d1be6c40ec59de0057de1563b23cd7fcce at fetch time
work/reviews/2026-11-17-CG2登記PR-M9最終審查-qa.md
work/reviews/2026-11-17-CG2登記PR-M9核對M2M3M6-風控.md
work/reviews/2026-11-17-CG2登記PR-M9證據-coordinator.md
dev-lead 意見：同意。check_review_refs 是在執行一鍵檔的那個 checkout 裡，以 HEAD 做 `git cat-file -e HEAD:<ref>`；R-1 又要求 HEAD 必須在 origin/product/stock-desk 上，所以實際執行時的 HEAD 是 CG-2 合併進 product 之後的 commit，裡面會有 product 上那兩份 11-17 紀錄。11-21 的兩份補充紀錄，只要在合併前 commit 到 product，同樣會在 HEAD 裡。附帶兩點：(1) 在還沒合併的 CG-2 分支本身上，test_the_review_refs_all_exist_at_head 會一直失敗，並列出 4 條，原因是分支本身不含這些紀錄，不是缺陷；(2) 我先前交件說「coordinator 要 commit 4 份」，那是只看 CG-2 分支得出的結論，依這個理解應更正為：只需要把 11-21 那兩份 commit 到 product。
```

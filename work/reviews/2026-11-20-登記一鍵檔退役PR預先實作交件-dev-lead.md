# 登記一鍵檔退役 PR 預先實作交件

- 審查者：dev-lead
- 日期：2026-11-20
- 轉存：coordinator，逐字轉存 subagent 最終回報

---

## 本次結論
退役分支已備妥並 push：`chore/nm5-cg2-oneclick-retire`，head 是 `c559b4afacf8ee6336dd8ffa2a9737a3d4e31749`（本地與 origin 一致），從 `9d5bbf48` 開出，沒有 merge 產品線，沒有開 PR。
- 補充九第 1 點的 9 個檔已一次刪除，另新增一支守門測試。
- `app/` 零差異，tree id 仍是 `9c157d8640fb97d7e90dc7edc3f5ff0252aa00d7`；`tests/test_cg2_registration_values.py` 零差異。
- 全套在 3.12、3.13 都通過：12186 passed、0 failed、2 xfailed，coverage 97.81%。
- 和 `feat/nm5-wiring` 試合併沒有衝突。
- 已照 tech-architect 題二的裁示調整；剩一項請 tech-architect 確認（見「下一步」第 1 點）。

## 各項回報

**Commit（3 個）**
- `72e0ed0753082813744faaef417fa969410c552e` chore: 刪除 CG-2 正式登記一鍵檔與其專屬測試
- `1a3b4d30fba32fbfb8121f04f626516a406157b7` test: 新增登記一鍵檔已退役的守門測試
- `c559b4afacf8ee6336dd8ffa2a9737a3d4e31749` test: 守門測試改用可區分的退役檔引用樣式（依題二裁示）

**第 1 項：檔案核對**
9 個檔在 `9d5bbf48` 上都存在，名稱與數量和清單相符，沒有差異。清單中的 `scripts/`、`tests/` 實際位置都在 `apps/stock-desk/backend/` 下：
- `backend/scripts/cg2_register.py`
- `backend/scripts/verify_cg2_instruction.py`
- `apps/stock-desk/cg2-preflight.bat`
- `apps/stock-desk/cg2-register.bat`
- `backend/tests/test_cg2_register_values.py`
- `backend/tests/test_cg2_register_flow.py`
- `backend/tests/test_cg2_register_addendum3.py`
- `backend/tests/cg2_register_world.py`
- `backend/tests/cg2_register_loader.py`

**第 2 項：殘留引用**
刪除後，在 `apps/stock-desk` 用四個原始字樣 grep，只命中兩處：
- `backend/tests/test_dirdef_v1_0_fields.py:94` 的 `def test_cg2_registers_exactly_dirdef_v1_0_and_the_two_rule_sets()`
- `backend/tests/test_outlook_rule_files.py:193` 的 `def test_cg2_registers_both_files_with_their_bytes_hash()`

兩處都是測試函式名稱，只是子字串碰巧相符。依題二，它們不算引用，不改名，也沒有動。

其他類別都沒有命中，所以沒有清除任何引用，也沒有修改任何既有檔：
- **`.gitattributes`**：根目錄只有 `*.bat text eol=crlf` 這種萬用規則，沒有逐檔規則；`backend/.gitattributes` 沒有命中。
- **其他測試**：沒有任何測試 import 已刪的 helper。
- **白名單、清單、雜湊**：沒有任何既有測試把這些檔列進去。tree id 的釘選只在已刪的檔裡。
- **`app/`**：沒有命中。
- **README**：沒有命中。
- **`tests/test_cg2_registration_values.py`**：沒有命中（`cg2_registration` 不含 `cg2_register`）。

我也做了更寬的檢查：不分大小寫比對 `cg2[-_ ]?regist(er|ry)|cg2[-_]preflight|verify_cg2`，同樣只有上面兩處，沒有其他類似的子字串誤中。

**第 3 項：守門測試**
`apps/stock-desk/backend/tests/test_oneclick_retirement.py`，共 6 個測試：
- `test_the_four_retired_files_do_not_exist`：四個檔在磁碟上不存在，也不在 git index 裡。
- `test_no_tracked_file_refers_to_a_retired_file`：命中必須等於空。
- `test_the_two_cg2_registers_test_names_are_still_there_and_out_of_scope`：斷言那兩行仍在、含 `cg2_register`，但不被樣式命中。
- `test_the_scan_covers_this_folder_and_excludes_only_this_file`：不排除任何檔時，多出來的命中恰好只有本檔。
- `test_the_pattern_matches_each_retired_name`
- `test_the_scan_is_case_sensitive_and_skips_the_excluded_file`

測試的做法：
- **掃描範圍**：只讀 `apps/stock-desk` 下 `git ls-files --cached` 列出的檔，所以 `.env`、`data/*.db`、venv、快取都不會被開啟。
- **排除**：只排除本檔，以 `Path(__file__).resolve()` 的路徑完全相等來判斷。
- **白名單**：裁示後已移除。那兩個 `test_cg2_registers_*` 改列在 `NOT_A_REFERENCE`，用斷言說明它們為何不在範圍內。
- **樣式**：用的是 `cg2_register(?!s)|cg2-register|cg2-preflight|verify_cg2_instruction`，偏離了題二的範例，原因見「下一步」第 1 點。

**有沒有 teeth**：做了以下暫時變動，跑完都已還原：
- 新增一個含 `from scripts import cg2_register` 的追蹤檔：2 個測試失敗。
- 還原 `cg2-preflight.bat`（第一版時是 `cg2-register.bat`）：3 個測試失敗。
- 把 `test_cg2_registers_both_files` 改名：1 個測試失敗。

**第 4 項：非純刪除的差異**
依題二，9 個檔只刪不改，`app/` 與 `test_cg2_registration_values.py` 零差異，這幾點都成立。
- 非刪除的差異只有一處：新增 `apps/stock-desk/backend/tests/test_oneclick_retirement.py`（+139 行）。
- 沒有修改任何既有檔，也沒有改寫任何句子（`git diff --name-status --diff-filter=d` 只列出這一個 A）。

**第 6 項：和接線分支的試合併**
- 用 `git merge-tree --write-tree` 試合併 `c559b4af` 與 `59b23e29`，沒有衝突。merge-base 就是 `9d5bbf48`，接線分支沒有改過任何被刪的檔。合併結果的 tree 是 `06607a352d54e1105ca53d5d1ce4ac74f63d09de`。
- 合併後的 `apps/stock-desk`：
  - 用可區分的樣式 grep，除了守門測試本身之外沒有任何命中。
  - 被刪的 9 個檔都不存在。
  - 那兩個 `test_cg2_registers_*` 都還在。
- 補充一點：接線分支上釘住 `app_tree_id` 的地方，只在 `cg2_register.py`、`test_cg2_register_values.py`、`test_cg2_register_addendum3.py`、`cg2_register_world.py` 這幾個被刪的檔裡。所以合併退役之後，接線分支上 R-1 tree id 的那個失敗會隨著檔案一起消失。
- 我沒有開暫時的 worktree，只用 merge-tree，所以沒有東西要移除。

## 驗證
- **diff 範圍**：
  - `git diff --stat 9d5bbf48 HEAD` 共 10 個檔，+139 / −5253。9 個是刪除：cg2_register.py −1384、verify_cg2_instruction.py −312、cg2_register_loader.py −42、cg2_register_world.py −345、test_cg2_register_addendum3.py −815、test_cg2_register_flow.py −1540、test_cg2_register_values.py −737、兩個 .bat 各 −39；另 1 個是新增的 test_oneclick_retirement.py +139。
  - `-- apps/stock-desk/backend/app` 為空。
  - `test_cg2_registration_values.py` 的 diff 為空。
  - `git rev-parse HEAD:apps/stock-desk/backend/app` 是 `9c157d8640fb97d7e90dc7edc3f5ff0252aa00d7`。
- **其他一鍵檔零差異**：`pipeline_acceptance_real.py`、`pipeline-acceptance.bat`、`r2-probe.bat`、`r2_first_run.py`、`pipeline_real_world.py`、`test_pipeline_acceptance_real_{bars,eol,flow}.py`、`test_r2_first_run.py`，以及 `work/`，都零差異。
- **全套（在最後一個 commit `c559b4af` 上跑）**：

| 版本 | passed | failed | xfailed | coverage | 結束碼 |
|---|---|---|---|---|---|
| 3.12 | 12186 | 0 | 2 | 97.81%（門檻 90%） | 0 |
| 3.13 | 12186 | 0 | 2 | 97.81%（門檻 90%） | 0 |

- **2 個 xfailed**：是 `tests/test_adr0019_pending.py` 的 T-1、T-4 兩個 strict xfail，在 `9d5bbf48` 就已存在，這次沒有動。它們和派工所說「這個分支沒有預期失敗」不一致，供你核對。
- **coverage**：只量 `app`，被刪的腳本不在範圍內。我沒有跑 `9d5bbf48` 的基準，所以沒有前後比較。
- **靜態檢查**：`ruff check` 是 All checks passed；`ruff format --check` 是 550 files already formatted；`mypy app tests` 是 Success: no issues found in 538 source files。
- **已登記值測試**：`test_cg2_registration_values.py` 另外單獨跑了一次（3.13），連同 adr0019 共 26 passed、2 xfailed；在全套中也通過。
- **輸出檔**：
  - /tmp/claude-0/-home-user-AICompany/3f76d891-50d3-55e1-b39d-925b8a90241a/scratchpad/retire-full-py312.txt
  - /tmp/claude-0/-home-user-AICompany/3f76d891-50d3-55e1-b39d-925b8a90241a/scratchpad/retire-full-py313.txt
  - 兩個檔的首行都是 `HEAD=c559b4af…`，檔尾都是 `EXIT_CODE=0`。
- **重跑說明**：最早在 `1a3b4d30` 啟動的一輪全套，收到題二裁示後我主動中止了，因為之後還要新增 commit。上面的數字全部來自 `c559b4af` 那一輪。

## 下一步
1. **待 tech-architect 確認樣式的字面**：題二的範例 `cg2_register\.py|cg2_register_|…` 會漏掉沒有 `.py` 也沒有 `_` 的裸模組引用，例如 `from scripts import cg2_register`。所以我改用 `cg2_register(?!s)`：它比範例更嚴，仍然排除那兩個 `test_cg2_registers_*`，而且在退役分支和合併後的 tree 上，兩種樣式的結果相同（都是零命中）。
   - 如果要和範例逐字一致，只需改測試裡的一行常數和對應的探針。
   - 另外，S-19a 那條 grep 用 PCRE 才能寫 `(?!s)`，要寫成 `git grep -P` 或 `grep -P`。這一點請一併確認。
2. **合併前的條件（不屬於我的範圍）**：
   - 登記 PR 合併、`register_result=DONE`、登記紀錄 commit 之後，把產品線 merge 進本分支並重驗。
   - coordinator 依 RC-244 起草 CEO 通知，送風控審查。
   - PR 說明要附回貼與登記紀錄 commit，並記載題二的讀法和上面那一處非刪除差異。
3. **送審**：交 qa-reviewer 審查（含 Codex 第二意見）。

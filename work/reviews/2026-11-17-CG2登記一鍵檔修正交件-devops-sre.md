# CG-2 登記一鍵檔修正交件（修正單 A～I，head 7b3fef0）

- 審查者：devops-sre
- 日期：2026-11-17
- 轉存：coordinator，逐字轉存 subagent 最終回報

---

## 本次結論

修正單 A～I 已全部完成，已 fast-forward push 到 `origin/feat/nm5-cg2-registration`。
- head：`7b3fef0fcbdc5b615d50179ce29c2faa44665231`（`git ls-remote` 與本地相同，工作樹乾淨）。
- 全套測試 3.12、3.13 各 12611 passed、2 xfailed，**只有 1 個預期失敗**，ruff 與 mypy 全過。
- 預期失敗的測試：`tests/test_cg2_register_values.py::test_the_review_refs_all_exist_at_head`。
  - 它獨立成一個測試，沒有 skip、xfail 或削弱。
  - 失敗的路徑只有 `work/reviews/2026-11-17-CG2登記PR-M9核對M2M3M6-風控.md` 與 `work/reviews/2026-11-17-CG2登記PR-M9最終審查-qa.md`。
  - 兩者落檔之後它會轉綠。
- 沒有遇到需要停下回報的衝突。
  - ADR 附記三與風控定稿之間沒有互相衝突。
  - 沒有需要新增的、風控沒定稿的畫面英文句。
  - 備份有位元組決定性，兩份在有、無 `-wal` 都逐位元組相同，所以沒有改用 `iterdump`，RC-209「兩份完全相同」字面成立。

**備註**
- 一鍵檔的 `app/` tree id 常數不變（`9c157d86…`）。dev-lead 補修沒有動 `app/`，merge 之後 `git rev-parse HEAD:apps/stock-desk/backend/app` 仍是這個值。
- 預檢綁定讓所有登記模式測試都需要一份通過的預檢。測試 world 會在登記前先靜默做一份預檢，不影響螢幕輸出與備份計數。這份靜默預檢用的探針是替身，不計入 `runner.probes`。

## 各部門回報（devops-sre）

**Commits（從 `3a3fccbf` 接續，由舊到新）**
- `8b2d85b`：merge `origin/product/stock-desk`（上一輪中斷前已建立，這次先 push）。
- `97763c3`：程式修正 A～G，加 `.bat`（RC-198），加既有測試調整。
- `f4ebee0`：附記三 S-15c 逐條測試，加 qa 低度項目 I。
- `7b3fef0`：操作說明套用風控定稿，加驗證腳本更新。
- 全部是 fast-forward，沒有 rebase、amend、force push。

**修正單 A～I 逐項對應**

- **A B-1 兩份備份**
  - `make_backup(db, folder, stamp)` 先取第一份，通過讀回後依同一規則取 `-verify` 第二份。
  - 檔名由 `backup_file_name` 與 `verify_file_name` 產生，驗證腳本核對它與說明文件逐字一致。
  - 兩份 sha256 不相等時 STOP `backup_mismatch`（RC-201 句），兩份都不刪，畫面不印 `backup_sha256`（因為沒有達成一致的值）。相等時回貼的 `backup_sha256` 是那個值。
- **A B-2 `review_refs`**
  - `check_review_refs`：預檢與登記都在探針之前，對每個路徑跑 `git cat-file -e HEAD:<path>`，不存在就 STOP `review_refs_missing`（RC-200 句）。
  - `REAL_PINS.review_refs` 寫死你給的 5 個路徑，已移除 `PENDING coordinator`。
- **A B-3 `main` 的 `KeyboardInterrupt`**：`state.late` 為真時結束碼 5 並留 `register_result=UNCONFIRMED` 回貼，否則 2。
- **B R-1 收緊**
  - 監看範圍加入 `scripts/cg2_register.py` 與兩個 `.bat`。
  - 每個 git 呼叫加 `-c core.fsmonitor=false -c core.untrackedCache=false`。
  - 新增 `git ls-files -v -z`，任何列標記不是 `H` 就 STOP `git_dirty`。
  - 不釘 `code_digest` 常數（`code_digest` 仍只印在回貼）。
- **C 預檢綁定**
  - `check_preflight_binding`：登記檔在探針與備份之前，讀 `paste-backs` 中檔名時間戳最新的 `preflight-*.txt`，只以文字讀。
  - 五種不符都 STOP `preflight_mismatch`（RC-200 句）、結束碼 3：讀不到；任一行不在白名單；沒有 `preflight_result=PASS`；`git_head` 不符；`script_sha256_lf` 不符。
  - 這個檢查排在前置檢查之後，所以前置檢查的 STOP 優先。
- **D 啟動前後**
  - 鍵入 0 或 1 之後、啟動子行程之前重驗 port 8000：有監聽就 STOP `port_listening`（原句）、結束碼 3、畫面最後仍印 `backup_sha256=`、不啟動子行程。R-4 不重驗。
  - 改用 `Popen` 加 `communicate(timeout=…)`，成功回傳後才設 `late=True`。
  - `Popen` 拋 `OSError` → STOP `claims_not_started`（RC-201 句）、結束碼 3。
  - 逾時 kill 子行程，判 `written_unknown`、結束碼 5、留 `UNCONFIRMED` 回貼。等待中被中斷也會 kill 子行程。
- **E 拒絕原因**
  - 子行程結束碼 3、4 時，在 STOP 句之後加印 `refusal_reason=<code>`，只印畫面，不寫回貼檔。
  - 腳本自己保留 `REFUSALS_EXIT_4`、`REFUSALS_EXIT_3` 兩張表，不 import `claims`。
  - stderr 去掉結尾換行後，與該結束碼的表中某句完全相等才印該鍵，否則 `unknown`。stderr 原文絕不轉出。結束碼 5 與其他不印。
  - 代號集合共 19 個，即 18 個鍵加 `unknown`。
- **F 改名**：`WRITTEN_UNCHECKED` → `UNCONFIRMED`，白名單、程式、測試、說明一致。
- **G 探針與禁詞行**
  - 預檢模式也執行探針，不符就 STOP `claims_unreachable`。
  - 子行程輸出的兩行 `banned_phrase_scan` 必須等於本次預檢算出的那兩行，否則視為輸出不符（結束碼 5）。
- **H 風控定稿字面**
  - **程式內固定句**由腳本從風控報告抽出再寫入：`PROMPT_SEEN`（RC-186a）、`bad_answer`（RC-194）、四句新 STOP（RC-200、RC-201 表格第一欄）。`usage` 句加 `_TELL`。
  - **說明文件**用 `scratchpad/cg2out/build_doc2.py` 建立。驗證腳本 `scripts/verify_cg2_instruction.py` 逐字核對：
    - RC-182、區塊五、RC-186b、RC-187、RC-195（來自 `...RC185至RC198-風控.md`）；
    - RC-202～RC-211 與第八節表格最後四列（來自 `...RC199至RC212-風控.md`）。
  - 驗證腳本也核對：程式內固定句等於風控定稿、備份檔名與程式實際檔名一致、沒有保證性字眼、已移除「待風控定稿」字樣與檢查。
  - 狀態說明已改為「已套用風控 RC-185～RC-211」。
  - RC-198：`usage` 句加 `_TELL`；兩個 `.bat` 的 `After installing, run this script again.` 改為 `Tell the coordinator.`。
    - 相關 `.bat` 測試只調整一處：「只含 r2 launcher 既有行」的例外集合加入 `  echo Tell the coordinator.`。
- **I qa 低度項目**
  - `test_cg2_register_flow.py` 的條件式斷言（原約 1476～1481 行）改為對 `schema.EXPECTED_OBJECTS` 的確定性斷言：5 張表的名稱逐一相等。
  - 放行 `unlink` 的測試（原約 1516 行）已移除，由新測試 `test_i_no_delete_rename_or_replace_is_called_from_the_script` 取代。它以呼叫端檔名斷言：沒有任何一次刪除、改名、取代是從腳本本身呼叫的。
  - `--backend-dir`、`--home` 保留，程式註解標明 `TEST ONLY`。`test_i_the_two_test_only_flags_are_never_in_a_launcher` 指出 `.bat` 不傳這兩個旗標。
  - 補「主 DB 旁有 `-wal`」的測試 `test_i_a_wal_beside_the_main_database_leaves_the_logic_alone_and_only_a_shm_may_appear`，記錄的行為：
    - 唯讀連線之後 `-wal` 仍在；
    - 最多多一個 `-shm`；
    - 沒有 `-journal`；
    - 主 DB 的 `iterdump` 不變。
  - 不做 scheduler 行程偵測。

## 驗證

**全套（head `7b3fef0`，兩個版本同時在背景跑，輸出在 `scratchpad/cg2out/`）**
- Python 3.12.3（專屬 venv `venv312-devops`）：`1 failed, 12611 passed, 2 xfailed, 1 warning`，耗時 2063.88s，輸出 `full2_312.txt`。
- Python 3.13.17（`venv313-devops`）：`1 failed, 12611 passed, 2 xfailed, 34 warnings`，耗時 1858.32s，輸出 `full2_313.txt`。34 個 warnings 是既有的 ResourceWarning，與本次無關。
- 兩邊 ruff check 與 ruff format --check 皆全過（`ruff2_*.txt`）。
- 兩邊 `mypy app tests` 皆 542 個檔無問題（`mypy2_*.txt`）。
- 唯一失敗的就是上面那個預期失敗的測試。
- 我的測試檔：
  - `test_cg2_register_flow.py`
  - `test_cg2_register_values.py`
  - `test_cg2_register_addendum3.py`（新增，111 個）
  - `cg2_register_world.py`（helper）

**「不得動」清單零 diff**
- 指令：`git diff --name-only 8b2d85b HEAD -- <清單>`，輸出為空。
- 清單：`app/`、三個 harness helper、`scripts/pipeline_acceptance_real.py`、`uv.lock`、backend 與 repo 根的 `.gitattributes`、`work/research`、`work/dispatch/.gitattributes`、`pipeline-acceptance.bat`。
- 規則 YAML 在 `app/` 之內。事先宣告在 `work/research`，C-8 紀錄檔與驗收操作說明在 `work/dispatch` 的既有檔。
- `git diff --name-only 8b2d85b HEAD -- work/dispatch` 只列出本次的 CEO 說明草稿，沒有動到 C-8 紀錄檔與驗收操作說明。
- 相對 `8b2d85b` 共改 9 個檔，全是本任務的檔案。

**S-15c 逐條對應的測試（皆在 `tests/test_cg2_register_addendum3.py`，除另標）**

- **第 1 點**
  - `test_p1_each_new_watched_file_with_an_uncommitted_change_stops`：script、兩個 `.bat` 各一，預檢與登記兩種模式。
  - `test_p1_a_hidden_change_is_a_stop`：`--assume-unchanged` 與 `--skip-worktree` 各對 5 個路徑。
  - `test_p1_the_hidden_change_would_pass_without_the_tag_check`
  - `test_p1_every_git_call_disables_fsmonitor_and_the_untracked_cache`
  - `test_p1_no_code_digest_constant_is_pinned_and_the_tree_id_constant_stays`
- **第 2 點**
  - `test_p2_no_preflight_file`
  - `test_p2_an_empty_paste_back_folder`
  - `test_p2_the_file_cannot_be_read_as_text`
  - `test_p2_a_line_is_off_the_whitelist`
  - `test_p2_no_pass_line`
  - `test_p2_the_git_head_is_not_this_runs`
  - `test_p2_the_script_hash_is_not_this_runs`
  - `test_p2_the_newest_file_decides`
  - `test_p2_the_binding_comes_after_the_prechecks`
  - 每個不符測試都斷言：沒呼叫探針、沒有備份、沒有啟動子行程、沒有問答、主 DB 邏輯狀態不變。
- **第 3 點**
  - `test_p3_the_two_backups_are_equal_and_the_recorded_hash_is_theirs`：有、無 `-wal` 各一，逐位元組相同。
  - `test_p3_two_backups_that_differ_are_a_stop_and_both_stay`：兩次之間注入一筆合成寫入。
  - `test_p3_the_port_is_checked_again_after_the_typed_answer`
  - `test_p3_popen_that_cannot_start_the_child_is_exit_3_and_not_late`
  - `test_p3_an_error_that_is_not_oserror_while_starting_is_still_before_the_registration`
  - `test_p3_late_starts_only_after_the_child_exists`
  - `test_p3_a_child_that_times_out_is_unconfirmed_exit_5`
  - flow 檔的 `test_d_a_child_that_runs_too_long_is_killed_and_the_result_is_unknown`、`test_d_an_interrupt_while_waiting_kills_the_child`、`test_the_real_subprocess_runner_builds_the_documented_command`（Popen 參數）
- **第 4 點**
  - `test_p4_a_review_record_that_is_not_in_head_stops`：兩個模式、兩個路徑，不呼叫探針。
  - `test_p4_every_path_is_asked_of_git_with_cat_file_e`
  - `test_p4_the_paths_in_the_constants_have_no_whitespace`
  - values 檔：`test_the_review_refs_are_the_final_list_in_repo_relative_form_without_spaces`（格式與無空白）
  - values 檔：`test_the_review_refs_all_exist_at_head`（預期失敗）
- **第 5 點**
  - `test_p5_the_tables_equal_the_two_tables_of_claims`
  - `test_p5_each_code_is_shown_after_the_stop_sentence_and_only_on_the_screen`：18 個代號各一。
  - `test_p5_anything_else_is_unknown_and_never_shown`：`unknown`，12 種組合。
  - `test_p5_a_sentence_of_the_other_exit_codes_table_is_unknown`
  - `test_p5_a_crlf_line_end_is_removed_before_the_comparison`
  - `test_p5_exit_5_and_the_others_print_no_reason`
  - `test_p5_the_reason_line_is_a_closed_set_and_screen_only`
  - `test_p5_the_real_program_refuses_and_the_code_is_the_one_of_its_sentence`：真正的 `claims.main` 對 9 種情況拒絕，代號與它的句子一致。
  - `test_p5_the_database_symlink_case_gives_db_not_default`
  - `test_p5_the_script_does_not_import_claims`
  - 螢幕輸出都經 `on_screen` 逐行 fullmatch（RC-162）。
- **第 6 點**
  - `test_p6_an_interrupt_while_starting_is_exit_2_with_no_paste_back`
  - `test_p6_an_interrupt_after_the_start_is_exit_5_and_leaves_an_unconfirmed_paste_back`
  - `test_p6_an_interrupt_at_the_port_check_after_the_answer_is_exit_2`
  - `test_p6_every_stage_before_the_start_gives_exit_2`
  - flow 檔：`test_rc162_ctrl_c_prints_one_fixed_sentence_at_every_stage`（啟動前 2，啟動後 5）
- **第 7 點與 G**
  - `test_p7_the_preflight_runs_the_probe`
  - `test_p7_a_probe_that_does_not_match_stops_the_preflight`
  - `test_g_the_childs_scan_lines_must_equal_the_preflights`

**驗證腳本輸出全文（`python scripts/verify_cg2_instruction.py`，結束碼 0，共 31 行 OK）**
```
OK   rc182 verbatim, exactly once as a quote block (1)
OK   block5 verbatim, exactly once as a quote block (1)
OK   區塊 RC-186b verbatim, exactly once (1)
OK   區塊 RC-187 verbatim, exactly once (1)
OK   區塊 RC-195 verbatim, exactly once (1)
OK   RC-202 verbatim, exactly once (1)
OK   RC-203 verbatim, exactly once (1)
OK   RC-204 verbatim, exactly once (1)
OK   RC-205 verbatim, exactly once (1)
OK   RC-206 verbatim, exactly once (1)
OK   RC-207 verbatim, exactly once (1)
OK   RC-208 verbatim, exactly once (1)
OK   RC-209 verbatim, exactly once (1)
OK   RC-210 verbatim, exactly once (1)
OK   RC-211 verbatim, exactly once (1)
OK   the four RC-200/201 rows are in (4)
OK   literal '## 六、登記被拒絕（結束碼 3 或 4）' is in the report and the instruction
OK   literal '以下引文為風控定稿（RC-182）：' is in the report and the instruction
OK   literal '## 七、登記開始之後無法確認結果（結束碼 5 ' is in the report and the instruction
OK   literal '登記程式回報已經寫入，但寫入之後的自我核對沒有通' is in the report and the instruction
OK   literal '見本節下方引文。' is in the report and the instruction
OK   the four new script sentences equal RC-200/201
OK   PROMPT_SEEN equals RC-186a
OK   bad_answer equals RC-194
OK   the usage sentence ends with the tell suffix
OK   the backup file names are the ones the script makes
OK   every fixed sentence is in the instruction (missing 0)
OK   every table row says not to fix it yourself (bad 0)
OK   no guarantee wording in the own text (found [])
OK   no awaiting-risk marker is left
OK   the status line names the applied risk conditions
```
- 驗證腳本有竄改測試證明會失敗：被軟化的引文、被截斷的引文、被改的備份檔名、被改的表格列、保證字眼、回到「待風控定稿」、缺「不要自己」的表格列。這些都在 `test_the_verifier_has_teeth`。

**用合成假主 DB 重跑的預檢、登記與一次拒絕（完整輸出在 `scratchpad/cg2out/demo2_out.txt`）**
- 預檢：exit 0。螢幕輸出與預檢回貼檔逐行相同，共 30 行，從 `cg2_oneclick version=1` 到 `done_at_utc=…`，含 `preflight_result=PASS`。
- 登記：exit 0。
  - 螢幕輸出 47 行，回貼檔相同。
  - 登記後假主 DB：5 張表、15 個 trigger、2 列。
  - 備份兩份：`stock-desk-before-cg2-20261120-211000.db` 與 `stock-desk-before-cg2-20261120-211000-verify.db`。
  - 回貼的 `backup_sha256=c9f5eae0fff50396d97010273a929ee5f6c7264eaea61b59a0b2bf0a960dcc3f`，與兩份備份的 sha256 相同。
- 這兩份回貼的主體（雜湊與格式）和上一輪交件貼的全文相同，差別只有：預檢多一行 `probe` 已含在內的版本，沒有新增行；登記多兩行。
  - 倒數第二行是 `register_result=DONE`（不是 `UNCONFIRMED`）。
  - 兩份備份的指紋相同，所以只多一行 `backup_sha256=`，不是兩行。
- 結束碼 3 的拒絕（子行程看到一個一鍵檔沒看到的 `STOCK_DESK_DB_PATH`，真實的 `claims.main` 拒絕）：
```
STOP: the registration was refused (exit 4). No data was added, changed or deleted. Do not change any setting or file yourself; tell the coordinator.
refusal_reason=env_db_path
backup_sha256=c9f5eae0fff50396d97010273a929ee5f6c7264eaea61b59a0b2bf0a960dcc3f
```
  - 腳本結束碼為 3，沒有產生任何回貼檔。

## 下一步

**你自擬而未經風控定稿的字句（請回送風控單項確認）**
1. 說明文件的檔頭三個條列（整理、風控引文出處、狀態）。
2. 第一節第 1 點，以及「兩個檔都沒有上網的動作。」
3. 第三節引文之後的結尾段：「鍵入之後程式會呼叫登記程式。完成時記事本會自動跳出…」與「登記完成之後不能再登記第二次：再執行登記檔會在預檢停下來。」
4. 第六節表格前的導入句，以及兩列 `refused_3`、`refused_4` 的「意思」與「您要做的事」（「意思」欄接 RC-190 的「見本節下方引文。」）。
5. 第七節表格 `written_5` 列的「您要做的事」。
6. 第八節表格中我自擬的各列「意思」與「您要做的事」：
   - `git_dirty` 的意思擴寫了一鍵檔與 `.bat`，以及被標記成不追蹤變動。
   - `port_listening` 的意思加上「鍵入後再檢查一次」，並區分預檢與登記的處理。
   - `claims_unreachable` 的意思加上「預檢檔與登記檔都會檢查」。
   - 其餘各列沿用上一輪已送審的文字。
7. 第八節「預期之外的錯誤與中斷」表格各列。
8. 第九節與第十節各行意思：
   - `backup_sha256=` 改為「兩份備份相同的指紋」；
   - 兩行 `banned_phrase_scan` 加註「程式會核對與預檢相同」；
   - 其餘沿用。
9. 第十一節新增一條：「畫面上的 `refusal_reason=` 行只出現在畫面上，不會寫進回貼檔。」

沒有新增任何程式內的畫面英文句。所有 CEO 可見的英文句（含 `refusal_reason=` 的形式）都來自 RC-186a、RC-194、RC-200、RC-201、RC-197，或沿用上一輪已審的固定句。

**需要 coordinator 或 TA 知道**
1. 預期失敗的測試要等兩個最終審查紀錄落檔後才會轉綠。落檔時路徑必須與 `REAL_PINS.review_refs` 的字串逐字相同。
2. 因為 `review_refs` 的檢查在執行期做，在那兩個檔進入 `HEAD` 之前，預檢與登記兩種模式都會 STOP `review_refs_missing`。這是預期行為。
3. `backup_mismatch` 不印 `backup_sha256`。理由：兩份不一致，沒有一個可以當還原點的指紋。若 coordinator 認為應該印第一份的指紋，需要另外裁示。
4. 逾時的 kill 與 `communicate(timeout=600)` 的數值沿用原本 600 秒，沒有新的裁示依據。

**Windows 上沒有實測的部分**（與上次相同，加上本次新增）
- 兩個 `.bat` 的執行與自動開記事本。
- Windows 上 `Popen` 的 kill 與 Ctrl+C 對子行程的傳遞。
- `git ls-files -v -z` 與 `core.fsmonitor=false` 在 Windows 上的輸出。
- 預檢綁定讀檔時 `paste-backs` 資料夾被雲端同步或防毒軟體鎖定的情況。
- OneDrive 目錄下備份的行為。
- 其餘與上次相同：`-I` 下 `app` 的解析、Windows 路徑的 SQLite URI 與 `immutable=1`、防毒鎖定備份讀回、`input()` 換行。

相關路徑（皆在 `/home/user/AICompany/.claude/worktrees/agent-a8e9a751d60cca098/` 之下）：
- `apps/stock-desk/backend/scripts/cg2_register.py`
- `apps/stock-desk/backend/scripts/verify_cg2_instruction.py`
- `apps/stock-desk/cg2-preflight.bat`
- `apps/stock-desk/cg2-register.bat`
- `apps/stock-desk/backend/tests/test_cg2_register_addendum3.py`
- `apps/stock-desk/backend/tests/test_cg2_register_flow.py`
- `apps/stock-desk/backend/tests/test_cg2_register_values.py`
- `apps/stock-desk/backend/tests/cg2_register_world.py`
- `work/dispatch/2026-11-17-正式登記操作說明-CEO.md`

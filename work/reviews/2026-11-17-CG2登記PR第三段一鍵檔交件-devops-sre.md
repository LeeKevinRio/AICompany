# CG-2 登記 PR 第三段：預檢與登記一鍵檔交件

- 審查者：devops-sre
- 日期：2026-11-17
- 轉存：coordinator，逐字轉存 subagent 最終回報

---

## 本次結論

CG-2 登記 PR 第三段（預檢與登記的一鍵檔）已完成，已 fast-forward push 到 `origin/feat/nm5-cg2-registration`。
- head：`3a3fccbf1e673d56c3fb5e6dee6639bceeaf86cc`（`git ls-remote` 已確認與本地相同）。
- 起點是 `5be3b953437da2b327a1fbaf37c581571e16cd2c`，沒有 rebase、amend、force push。
- Python 3.12 與 3.13 全套都通過，ruff 與 mypy 全過。
- 「不得動」清單零 diff。

需要 TA 或 coordinator 裁示的有五點，見下方「下一步」。第 1、2 點在正式登記前必須先定。

**這次用到主 DB 的操作（照 ADR 自行核對的結果）**
- 預檢 R-4 與備份來源只用 `mode=ro` 連線。
- 檢查補充六 (b) 的「主 DB 不得被任何 SQLite 連線開啟」後，我認為沒有衝突。
  - RC-158b 與附記第 2 點把它限定在驗收腳本。
  - 補充四第 4 點明文要求 backup API，補充七附記二第 1 點明文要求 R-4 用 `mode=ro`。
- 一鍵檔本身的寫入連線只有一條：寫入新備份檔。
  - 這條不是主 DB。我把它理解為不違反「一鍵檔不開寫入連線」，請 TA 確認這個讀法。

## 各部門回報（devops-sre）

**Commits（皆在 `5be3b95` 之後，由舊到新）**
- `990fdd1`：`cg2_register.py` 與兩個 `.bat`。
- `564f415`：流程、STOP、M-8、RC-181、RC-162、e2e 測試，以及合成世界 helper。
- `b36e66d`：常數、白名單、AST 邊界、`.bat` 語法測試。
- `0ded820`：操作說明草稿與引文驗證腳本。
- `80bcc5b`：mypy 型別修正。
- `3a3fccb`：已忽略的 `__pycache__` 不得讓預檢誤判 `app/` 有變動。

**新增檔案（共 9 個，全是新增，沒有修改任何既有檔）**
- `apps/stock-desk/backend/scripts/cg2_register.py`
- `apps/stock-desk/backend/scripts/verify_cg2_instruction.py`
- `apps/stock-desk/cg2-preflight.bat`
- `apps/stock-desk/cg2-register.bat`
- `apps/stock-desk/backend/tests/cg2_register_loader.py`
- `apps/stock-desk/backend/tests/cg2_register_world.py`
- `apps/stock-desk/backend/tests/test_cg2_register_flow.py`
- `apps/stock-desk/backend/tests/test_cg2_register_values.py`
- `work/dispatch/2026-11-17-正式登記操作說明-CEO.md`

**從驗收腳本複製的邏輯（沒有 import 它，它零差異）**
- 最前面的三個 hook、`warnings.simplefilter`、`logging.disable`。
- `sys.path` 插入 backend 的做法。
- `say`、`sha256_file`。
- `run_git`：另外加了移除 `GIT_*` 環境變數與 `--no-replace-objects`。
- `core_autocrlf`、`inside_git_work_tree`、`port_is_listening`。
- `env_file_sets_db_path` 與 `ENV_KEY_PATTERN`：只掃鍵名。
- `ls-files --eol` 的欄位讀法：改為 `-z`，並多讀 `attr/` 欄。
- 白名單逐行 fullmatch、`utf-8-sig` 寫檔、`os.startfile` 開記事本。
- `main` 的 `BaseException` 外層，與 `--backend-dir`、`--home` 測試用覆寫。
- `immutable` 的決定規則（取自 `copy_uri`）。

**設計摘要**
- 預檢順序：R-3、R-1、R-2、M-8 雜湊加 R-6、R-4。
- 登記順序：重跑全部預檢，接著依序：
  1. 探針：問子行程它要處理哪個 backend，不符就 STOP。
  2. R-5 備份。
  3. R-8 鍵入。
  4. 子行程呼叫 `bootstrap --production`。
  5. 結束碼處理。
  6. 16 行逐行驗證。
  7. 回貼檔。
- 備份位置：`<家目錄>\stock-desk-cg2-registration\backups\stock-desk-before-cg2-<時間戳>.db`。
- 回貼檔位置：`<家目錄>\stock-desk-cg2-registration\paste-backs\{preflight|register}-<時間戳>.txt`。
- 這個資料夾與驗收的 `stock-desk-pipeline-acceptance` 不同名。
- 腳本全程不刪除、不改名、不計算主 DB 的雜湊、不用 `open()` 開主 DB。
- 腳本結束碼：0 完成；1 非預期錯誤；2 中斷；3 停止且未寫入；5 已寫入或不確定是否寫入，不得重跑。

**子行程的 sys.path 與工作目錄**
- 子行程是 `sys.executable -I -X utf8 -m app.forecast.claims ...`，`cwd` 為 backend，輸出全部 `capture_output`，從不轉出。
- `-I` 不會把 `cwd` 或 `PYTHONPATH` 放進 `sys.path`，所以 `app` 必須來自該環境對這個 backend 的 editable 安裝。
- 因此登記前先跑一個探針子行程，印出 `claims.BACKEND_DIR`。與 `--backend-dir` 不同或探針失敗，就 STOP `claims_unreachable`，不備份、不呼叫 `bootstrap`。
- 驗收腳本是自己 `sys.path.insert`，那是它與這支腳本的差異。

## 驗證

**全套測試（head `3a3fccb`，各 12494 passed、2 xfailed、0 failed，覆蓋率 97.81%）**
- Python 3.12.3：1961.50s。venv 為 `scratchpad/venv312-devops`，照「合併前檢查改用 CI 的 Python 版本」用 `uv sync --frozen` 建立。
- Python 3.13.17：1816.54s。venv 為 `scratchpad/venv313-devops`。
- 3.13 有 34 個 ResourceWarning，來自既有測試 `test_api_playbook_cap1_disclosure.py`，與本次無關。
- `ruff check .`、`ruff format --check .`：3.12 與 3.13 皆全過。
- `mypy app tests`：541 個檔，3.12 與 3.13 皆無問題。
- 輸出檔在 `/tmp/claude-0/-home-user-AICompany/3f76d891-50d3-55e1-b39d-925b8a90241a/scratchpad/cg2out/`：`full312.txt`、`full313.txt`、`ruff312.txt`、`ruff313.txt`、`mypy312.txt`、`mypy313.txt`。
- 我的兩個測試檔：flow 228 個、values 86 個。

**「不得動」清單零 diff**
- 指令：`git diff --name-only 5be3b953…HEAD -- <清單>`，輸出為空。
- 清單：`app/`、三個 harness helper、`scripts/pipeline_acceptance_real.py`、`uv.lock`、backend 與 repo 根的 `.gitattributes`、`work/research`、`work/dispatch/.gitattributes`、C-8 紀錄檔、`pipeline-acceptance.bat`、驗收操作說明。
- `git diff --stat` 顯示全部是 9 個新增檔。

**M-8 常數重算（與 dev-lead 的值完全一致）**
- 重算方式：`git cat-file blob HEAD:<path>` 加 sha256，以及用程式算 `definition_sha256`、`rules_sha256`、`rules_logic_sha256`。
- 事先宣告：`7c45b0ba79e04a7a74a2b8bc91603cb0bfbd78101b51ab8403cc4ed45a4b406e`。
- C-8 紀錄檔：`c942642c1958e6259545c4f64b4202fbafecf585f1f2cbe513961190af0ea54f`。
- definition：`2a58bca61c647931ecaf56aa5d17e4bfffc048c30944f3550feceadbfdacc4d0` / `4cc1fe80054a017f47030805a486ad81e1bda249d730c7c1f6bd2c73c01d1afa`。
- h3、h5 的 `rules_sha256` 等於 YAML 的 blob sha256，與 dev-lead 的值一致。
- 規則雜湊：
  - h3：`f4f366a5…3443` / `ddd3c51a…4484`
  - h5：`0a385de3…707c` / `e5310b8e…f1bb`
- 全 64 碼寫在 `cg2_register.py` 的 `REAL_PINS`，並由測試與 `tests/test_cg2_registration_values.py` 的常數互相核對。
- 另釘 `app/` 的 git tree id：`9c157d8640fb97d7e90dc7edc3f5ff0252aa00d7`。

**測試對應**（全在 `tests/test_cg2_register_flow.py`，標 values 者在 `test_cg2_register_values.py`）

- **R-1**（STOP `head_unpublished`、`git_dirty`、`app_changed`、`git_unusable`）：
  - `test_r1_head_not_on_the_published_branch`
  - `test_r1_a_watched_path_has_uncommitted_changes`
  - `test_r1_an_untracked_file_in_app_is_dirty_too`
  - `test_r1_the_app_tree_differs_from_the_cg2_pr`
  - `test_r1_git_unusable`
  - `test_r1_the_loaded_app_is_not_the_backend`
  - `test_r1_frozen_commit_is_head_even_after_new_unrelated_commits`
  - `test_r1_ignored_bytecode_in_app_does_not_make_the_tree_dirty`
  - values：`test_r1_the_app_tree_constant_is_the_app_tree_of_this_checkout`
- **R-2**（STOP `frozen_bytes`、`frozen_eol`）：
  - `test_r2_a_constant_that_differs_from_the_file`
  - `test_r2_crlf_in_the_work_tree_stops_on_the_raw_bytes`
  - `test_r2_crlf_in_the_work_tree_stops_with_the_real_status_too`
  - `test_r2_the_eol_attribute_is_missing`
  - `test_r2_the_yaml_attribute_is_missing`
  - `test_r2_each_of_the_three_evidences_alone_stops`（六種單獨竄改）
  - `test_r2_nothing_is_changed_by_the_stop`
- **R-3**（STOP `env_db_path`、`env_file_db_path`、`no_db`、`port_listening`、`work_in_git`）：
  - `test_r3_the_environment_sets_the_variable`
  - `test_r3_the_env_file_sets_the_key`
  - `test_r3_the_env_file_is_only_searched_for_the_key`
  - `test_r3_no_main_database_at_the_default_location`
  - `test_r3_port_8000_is_listening`
  - `test_r3_the_work_folder_inside_a_git_work_tree`
  - `test_r3_the_real_port_check_sees_a_listener`
- **R-4**（STOP `ledger_objects`、`db_unreadable`）：
  - `test_r4_any_ledger_object_stops_before_anything_else`（表、`plan_`、大小寫、view、index 共 6 種，兩種模式）
  - `test_r4_sees_objects_that_exist_only_in_the_wal`（有、無 `-wal`）
  - `test_r4_the_prefixes_and_the_verdict_are_the_ones_of_the_schema_module`（與 `schema._ledger_objects` 逐形對照）
  - `test_r4_names_that_only_contain_the_prefix_do_not_stop`
  - `test_r4_unreadable_database_is_a_stop`
- **R-5**（STOP `backup_failed`、`backup_integrity`、`backup_has_ledger`）：
  - `test_r5_the_backup_target_already_exists`
  - `test_r5_the_backup_fails_the_integrity_check`
  - `test_r5_the_backup_holds_a_ledger_object`
  - `test_r5_the_backup_cannot_be_made`
  - `test_r5_the_backup_sha256_must_not_change_while_it_is_read_back`
  - `test_r5_a_wal_main_database_is_backed_up_with_its_wal_rows`
  - `test_r5_the_backup_is_outside_the_work_tree_and_named_apart_from_the_acceptance`
- **R-6 與 M-8 雜湊**（STOP `banned_phrase`、`hashes_differ`）：
  - `test_r6_a_banned_phrase_hit_stops`
  - `test_r6_the_scan_lines_are_the_same_text_the_registration_program_prints`
  - `test_m8_each_hash_constant_that_differs_from_the_program_stops`（6 個雜湊逐一）
  - `test_m8_an_unpublished_version_is_a_stop`
- **R-7**（結束碼）：
  - `test_r7_each_exit_code_has_its_fixed_sentence`（3、4、5、1、2、7）
  - `test_r7_exit_5_says_written_do_not_rerun_tell_the_coordinator`
  - `test_r7_exit_5_leaves_an_unchecked_paste_back_with_the_backup_hash`
  - `test_r7_a_changed_line_of_the_sixteen_stops_as_unverified`（16 行逐行）
  - `test_r7_the_wrong_number_or_order_of_lines_stops_as_unverified`
  - `test_r7_a_well_formed_line_with_a_value_that_is_not_this_runs_stops_as_unverified`
- **R-8**（STOP `bad_answer`）：
  - `test_r8_an_answer_that_is_not_exactly_0_or_1_stops_and_calls_nothing`（11 種，含空白、全形 `１`）
  - `test_r8_end_of_input_is_an_invalid_answer`
  - `test_r8_the_answer_is_passed_on_unchanged_and_asked_once_with_the_fixed_prompt`
  - `test_r8_there_is_no_confirmation_loop_and_no_default`
  - `test_r8_the_value_1_registers_like_the_value_0`
  - `test_r8_preflight_never_asks_for_the_answer`
  - values：`test_ast_the_typed_answer_has_no_default_and_no_other_source`
- **M-8（補充四第 2 點每個拒絕條件）**：
  - `test_m8_the_target_resolves_elsewhere`
  - `test_m8_the_program_sees_the_variable_the_one_click_did_not`
  - `test_m8_ledger_objects_appear_between_the_preflight_and_the_registration`
  - `test_m8_the_claims_in_the_wrong_order`
  - `test_m8_a_replacement_is_refused`
  - `test_m8_only_one_claim_is_refused`
  - `test_m8_a_refusal_of_the_program_writes_nothing`（三種：commit、sha256、鍵入值 2）
  - 另有 R-3 的環境變數、`.env`、無 DB 各測試。
- **M-8（整筆回滾）**：
  - `test_m8_the_whole_transaction_rolls_back_when_the_store_gives_up`
  - `test_m8_a_failure_after_the_first_row_rolls_the_schema_back_too`
- **M-8（回傳不含路徑與代號）**：
  - `test_m8_the_paste_back_has_no_path_claim_id_or_rule_version`
  - `test_preflight_passes_and_writes_the_whitelisted_paste_back`（毒藥字串 9 種）
- **RC-181 三項**：
  - ①R-4 STOP 不呼叫 `bootstrap`：`test_rc181_1_an_r4_stop_never_calls_bootstrap`（6 種）。
  - ②備份先於 `bootstrap`：`test_rc181_2_the_backup_is_complete_before_bootstrap_is_called`、`test_rc181_2_no_backup_means_no_bootstrap`，加 values 的 `test_ast_the_order_probe_backup_typed_answer_child`。
  - ③不以主 DB 檔案雜湊為證據：`test_rc181_3_no_file_hash_of_the_main_database_is_taken_or_shown`、`test_rc181_3_the_one_click_never_reads_the_bytes_of_the_main_database`、values 的 `test_ast_the_main_database_is_never_opened_hashed_or_read_by_bytes`。
- **RC-162**（整段 stdout 與 stderr 每行 fullmatch 白名單或固定句）：
  - `test_rc162_every_screen_line_of_a_normal_run_is_on_the_whitelist`
  - `test_rc162_an_unexpected_exception_prints_one_fixed_sentence`（7 個階段）
  - `test_rc162_ctrl_c_prints_one_fixed_sentence_at_every_stage`（7 個階段）
  - `test_rc162_an_interrupt_after_the_backup_still_shows_the_backup_hash`
  - `test_rc162_usage_errors_print_the_fixed_stop_sentence_only`
  - `test_rc162_a_failing_opener_is_silent`
  - `test_rc162_the_hook_sentence_is_the_error_sentence`
  - `test_rc162_threads_warnings_unraisables_and_uncaught_errors_print_the_fixed_sentence`
  - `test_rc162_the_cli_stop_through_a_real_isolated_interpreter`
  - values：hooks 為第一批敘述的 AST 測試
- **e2e**：
  - `test_e2e_the_preflight_only_reads_the_main_database`：監聽 `sqlite3.connect`、`open`、`os.open`、`os.remove` 與 `shutil.*` 等；R-4 連線 URI 都含 `mode=ro`，主 DB 沒有任何 `open`，也沒有任何檔案操作。
  - `test_e2e_the_register_run_only_opens_the_main_database_read_only`：登記流程中一鍵檔自己只有 R-4 與備份來源兩條 `mode=ro` 連線。
  - `test_e2e_no_side_file_appears_beside_the_main_database`：沒有 `-wal` 時，R-4 與備份不產生側檔。
  - `test_e2e_the_monitor_has_teeth`
  - `test_e2e_after_a_successful_registration_the_database_has_the_whole_ledger`：5 表、15 trigger、2 列；備份存在且不含 `forecast_`；第二次執行被 R-4 擋下。
  - 另有 `test_e2e_register_creates_the_ledger_two_rows_and_a_backup`（0 與 1 各一）。
- **毒藥測試**：見上方 M-8 的回傳內容測試。
- **兩個 `.bat`**：values 的 `test_the_bat_is_a_crlf_launcher_that_clears_uv_env_file_first`、`test_the_bat_has_no_non_cmd_syntax_and_only_r2_launcher_lines_besides_its_own`、`test_the_two_bats_differ_only_in_the_mode_title_and_comments` 等。非 REM 行沒有 `/dev/null`、`&&`、`||`、`2>&1`，只有 r2 launcher 既有的行加自己的行。

**用合成假主 DB 跑一次預檢與一次登記（`typed=0`；完整輸出在 `scratchpad/cg2out/demo_out.txt`）**

預檢回貼（exit 0）：
```
cg2_oneclick version=1
mode=preflight
script_sha256_lf=1c33f118fbcde14d109ec01401f7f95deb3271a799dc19bdddf406e054e37a97
git_head=82c313017e8213841c4238f0c6b8ed1bcc115670
git_clean=yes
core_autocrlf=unset
head_published=yes
app_unchanged=yes
code_digest=f55f9243d34692298f892f0b1babf35c0f885d02594e4ed67055dec9cea63ca1
frozen_prereg_sha256=cbb62b8d1e658727a1c2bfe4736d422614bc53ab35d68c73508512ecf747f574
frozen_c8_sha256=e169d0c07840dfaadeeb636cf7b631bcb074c0f2bde2b27c92f19ba995084a09
frozen_h3_sha256=c5c5a2420ba9b4156640a3c20d7d0c4acbf76a2f5e25540913bacc81d41fde32
frozen_h5_sha256=74f5adcb92e1e1acc409dcfb62e21719b87fc236d35f1a8599bbfd7df49f1280
eol_check=ok
attr_check=ok
definition_sha256=2a58bca61c647931ecaf56aa5d17e4bfffc048c30944f3550feceadbfdacc4d0
definition_logic_sha256=4cc1fe80054a017f47030805a486ad81e1bda249d730c7c1f6bd2c73c01d1afa
rules_sha256_h3=f4f366a5d5e66fd7fd49c916f5bb31401e84c2f23b3bb7a534f55be406fb3443
rules_logic_sha256_h3=ddd3c51a1cb9b30a3e957a5a98888ca48916deb35f66027f2f49e7b824f34484
rules_sha256_h5=0a385de3e2f4118bc1e7c2c5dd1a667ce0a9067399ccd1b6e7c4dbab19d5707c
rules_logic_sha256_h5=e5310b8e6ce14525e81616eedd4368d45a682cb8a4647129ea5617a41cedf1bb
hashes_pinned=ok
env_db_path=unset
db_location=default
port_8000_listening=no
ledger_objects=none
banned_phrase_scan_h3=hits 0 rules_strings 159 definition_strings 12 phrases 10
banned_phrase_scan_h5=hits 0 rules_strings 159 definition_strings 12 phrases 10
preflight_result=PASS
done_at_utc=2026-11-20T13:05:09Z
```

登記回貼（exit 0；前面各行與預檢相同，只有第二行是 `mode=register`，且沒有兩行 `banned_phrase_scan` 與 `preflight_result`）：
```
cg2_oneclick version=1
mode=register
script_sha256_lf=1c33f118fbcde14d109ec01401f7f95deb3271a799dc19bdddf406e054e37a97
git_head=82c313017e8213841c4238f0c6b8ed1bcc115670
git_clean=yes
core_autocrlf=unset
head_published=yes
app_unchanged=yes
code_digest=f55f9243d34692298f892f0b1babf35c0f885d02594e4ed67055dec9cea63ca1
frozen_prereg_sha256=cbb62b8d1e658727a1c2bfe4736d422614bc53ab35d68c73508512ecf747f574
frozen_c8_sha256=e169d0c07840dfaadeeb636cf7b631bcb074c0f2bde2b27c92f19ba995084a09
frozen_h3_sha256=c5c5a2420ba9b4156640a3c20d7d0c4acbf76a2f5e25540913bacc81d41fde32
frozen_h5_sha256=74f5adcb92e1e1acc409dcfb62e21719b87fc236d35f1a8599bbfd7df49f1280
eol_check=ok
attr_check=ok
definition_sha256=2a58bca61c647931ecaf56aa5d17e4bfffc048c30944f3550feceadbfdacc4d0
definition_logic_sha256=4cc1fe80054a017f47030805a486ad81e1bda249d730c7c1f6bd2c73c01d1afa
rules_sha256_h3=f4f366a5d5e66fd7fd49c916f5bb31401e84c2f23b3bb7a534f55be406fb3443
rules_logic_sha256_h3=ddd3c51a1cb9b30a3e957a5a98888ca48916deb35f66027f2f49e7b824f34484
rules_sha256_h5=0a385de3e2f4118bc1e7c2c5dd1a667ce0a9067399ccd1b6e7c4dbab19d5707c
rules_logic_sha256_h5=e5310b8e6ce14525e81616eedd4368d45a682cb8a4647129ea5617a41cedf1bb
hashes_pinned=ok
env_db_path=unset
db_location=default
port_8000_listening=no
ledger_objects=none
backup_integrity=ok
backup_ledger_objects=none
backup_sha256=c9f5eae0fff50396d97010273a929ee5f6c7264eaea61b59a0b2bf0a960dcc3f
bootstrap=ok
banned_phrase_scan_h3=hits 0 rules_strings 159 definition_strings 12 phrases 10
banned_phrase_scan_h5=hits 0 rules_strings 159 definition_strings 12 phrases 10
registered_rows=2
frozen_commit=82c313017e8213841c4238f0c6b8ed1bcc115670
prereg_doc_sha256=cbb62b8d1e658727a1c2bfe4736d422614bc53ab35d68c73508512ecf747f574
definition_sha256=2a58bca61c647931ecaf56aa5d17e4bfffc048c30944f3550feceadbfdacc4d0
definition_logic_sha256=4cc1fe80054a017f47030805a486ad81e1bda249d730c7c1f6bd2c73c01d1afa
rules_sha256_h3=f4f366a5d5e66fd7fd49c916f5bb31401e84c2f23b3bb7a534f55be406fb3443
rules_logic_sha256_h3=ddd3c51a1cb9b30a3e957a5a98888ca48916deb35f66027f2f49e7b824f34484
registered_at_h3=2026-11-20T13:00:01.000000+00:00
rules_sha256_h5=0a385de3e2f4118bc1e7c2c5dd1a667ce0a9067399ccd1b6e7c4dbab19d5707c
rules_logic_sha256_h5=e5310b8e6ce14525e81616eedd4368d45a682cb8a4647129ea5617a41cedf1bb
registered_at_h5=2026-11-20T13:00:02.000000+00:00
provisional_results_seen=0
post_commit_check=ok
register_result=DONE
done_at_utc=2026-11-20T13:05:09Z
```
- 登記後假主 DB：5 張 `forecast_` 表、15 個 trigger、登記表 2 列。
- 備份檔：`stock-desk-before-cg2-20261120-211000.db`。
- 登記回貼中有 7 個雜湊鍵出現兩次，一次來自預檢、一次來自登記程式輸出。兩者經程式比對相等，保留當作交叉核對。
- 這些 `frozen_*` 與 `code_digest` 是合成 repo 的值，真實值會不同。

**CEO 操作說明（`work/dispatch/2026-11-17-正式登記操作說明-CEO.md`，草稿）**
- 結構：兩段各三步驟、備份位置、還原方式（只描述，一律先告訴 coordinator）、STOP 與 ERROR 對照表、兩種回貼各行的意思。
- 逐字風控定稿 2 段：RC-182 放在「登記被拒絕（結束碼 3 或 4）」節，區塊五放在「登記時是否看過暫定對照」節。
- 引文是用腳本抽出再寫入，不是手打。抽取規則：
  - RC-182：風控報告中 `RC-182` 條目後的 `  > ` 引文段。
  - 區塊五：該標題下的 `> ` 引文段。
- 驗證腳本 `scripts/verify_cg2_instruction.py` 的結果（已納入 CI 測試，並有竄改測試證明它會失敗）：
```
OK   rc182 verbatim, exactly once as a quote block (found 1)
OK   block5 verbatim, exactly once as a quote block (found 1)
OK   every fixed sentence is in the instruction (missing 0)
OK   every table row says not to fix it yourself (bad 0)
OK   no guarantee wording outside the quotes (found [])
OK   the exit 5 text is marked as awaiting the risk final text
```
- 結束碼 5 一節已標「待風控定稿（TA 的 Q-7b）」，內容是我自擬。

## 下一步

**停下待裁示（影響寫入條件或 CEO 看到的內容）**

1. **R-1 的「CG-2 合併 commit」（請 TA 確認）**
   - 合併前它不存在，所以我用等價做法，沒有用字面的 diff：
     - `HEAD` 可由 `origin/product/stock-desk` 到達；
     - `app/` 與兩份文件的工作樹乾淨；
     - `git rev-parse HEAD:apps/stock-desk/backend/app` 必須等於常數 `9c157d86…00d7`（本 PR 的 `app/` tree id）；
     - 兩份文件的 sha256 由 R-2 常數把關。
   - 代價：之後 `app/` 若有任何變動（例如 dev-lead 補修），常數必須重釘並重審。
   - values 測試 `test_r1_the_app_tree_constant_is_the_app_tree_of_this_checkout` 會在這時失敗並提示。接線 PR 合併後這支一鍵檔退役，這個測試要一併退役。
   - 另一個選項是合併後由 coordinator 填入 `CG2_MERGE_COMMIT` 常數，再走一輪審查。
   - **dev-lead 的補修交件 `work/reviews/2026-11-17-CG2登記PR補修交件-dev-lead.md` 不在分支，也不在 `origin/product/stock-desk`。** 我以 `5be3b95` 的程式為準，沒讀到補修內容。若補修有改 `app/`，tree id 要重釘。
2. **`--review-refs` 要傳哪些路徑（請 coordinator 決定）**
   - 這會永久寫進登記表。
   - 我暫放 5 個已存在的風控紀錄：
     - `work/reviews/2026-11-15-凍結包第2輪單項確認-風控.md`
     - `work/reviews/2026-11-15-事先宣告v0.32套用單項確認-風控.md`
     - `work/reviews/2026-11-15-C8決策紀錄檔確認-風控.md`
     - `work/reviews/2026-11-15-真實資料一鍵檔Q1Q2確認-風控.md`
     - `work/reviews/2026-11-16-補充七附記二三點判定RC179至RC184-風控.md`
   - 測試只驗格式與在 `HEAD` 存在。
   - 本 PR 的 qa 審查紀錄與 harness 通過紀錄尚不存在，需要 coordinator 決定是否納入。
   - 常數在 `REAL_PINS.review_refs`，已標 `PENDING coordinator`。
3. **R-8 的 ASCII 提示句（請風控審）**
   - 這是 CEO 看到的內容，ADR 沒寫字面，我自擬：`Type 0 if you have NOT seen any provisional comparison, or 1 if you have, then press Enter: `。
   - 只接受剛好 `0` 或 `1`，連多一個空白都 STOP，不 trim、不重問。
4. **結束碼 3、4、5、其他時畫面的句子**
   - 只用我定的固定句，不轉出登記程式的 stderr。
   - 代價：coordinator 看不到是 `not_empty` 還是其他拒絕原因。若要顯示封閉集合的原因代號，需要另行核可。
5. **結束碼 5 的中文說明**：我自擬的版本待風控定稿（TA 的 Q-7b）。

**其他自定解讀（可推翻）**
- R-6 禁詞比對放在備份之前（屬「重跑全部預檢」），登記程式內還會再比對一次。ADR 條列的順序是備份在先，我讀為預檢先、備份後，不影響 `bootstrap` 之前完成備份。
- R-4 與備份來源的 URI 是 `mode=ro`，只有在主 DB 旁沒有 `-wal` 與 `-journal` 時才加 `immutable=1`。這是沿用驗收腳本 `copy_uri` 的規則，目的是不在主 DB 旁產生 `-wal`、`-shm`。有 `-wal` 時只用 `mode=ro`。測試已涵蓋有、無 `-wal` 兩種。
- 備份讀回用 `mode=ro&immutable=1`，並在讀回前後各算一次 sha256，必須相等。備份永不刪除，連失敗的備份也不刪。
- 結束碼 0 但 16 行不符形狀、順序、或值與本次 `HEAD`、M-8 常數、鍵入值不符，一律視為已寫入但無法驗證，結束碼 5。
- 登記啟動之後的任何例外、中斷、逾時，都印「可能已寫入，不要重跑」。
  - 這類情況會寫一份標 `register_result=WRITTEN_UNCHECKED` 的回貼檔。
  - 備份之後的任何非成功結束，畫面最後多印一行 `backup_sha256=`，因為它是 CG-3 要記的還原點。
- `PROMPT_CLOSE`（請關閉三個視窗後按 Enter）沿用驗收的做法，兩個模式都問。
- 預檢檔只在 `paste-backs` 下寫回貼檔，不建立 `backups` 資料夾，也不產生備份。

**Windows 上沒有實測的部分**
- 兩個 `.bat` 的實際執行。
- `os.startfile` 自動開記事本。
- `-I` 下 `app` 是否由 editable 安裝解析；已有探針把關，但沒在 Windows 上跑過。
- Windows 路徑（含中文使用者名稱、空白）下 `Path.as_uri()` 轉成的 SQLite URI 與 `immutable=1` 行為。
- 防毒軟體對備份檔讀回的鎖定。
- git for Windows 在 `core.autocrlf=true` 時 `ls-files --eol` 與 `check-attr` 的實際輸出。
- `input()` 在 cmd 的換行處理。
- 在 CEO 的真實 repo 上，`git status` 對 `app/` 與兩份文件的行為。
- 所有測試都在 Linux 的合成世界跑，沒有碰任何真實資料庫，也沒有執行任何 `.bat`。

相關路徑（皆在 `/home/user/AICompany/.claude/worktrees/agent-a8e9a751d60cca098/` 之下）：
- `apps/stock-desk/backend/scripts/cg2_register.py`
- `apps/stock-desk/backend/scripts/verify_cg2_instruction.py`
- `apps/stock-desk/cg2-preflight.bat`
- `apps/stock-desk/cg2-register.bat`
- `apps/stock-desk/backend/tests/cg2_register_world.py`
- `apps/stock-desk/backend/tests/cg2_register_loader.py`
- `apps/stock-desk/backend/tests/test_cg2_register_flow.py`
- `apps/stock-desk/backend/tests/test_cg2_register_values.py`
- `work/dispatch/2026-11-17-正式登記操作說明-CEO.md`

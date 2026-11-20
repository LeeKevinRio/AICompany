# 狀態報告一鍵檔交件

- 審查者：devops-sre
- 日期：2026-11-20
- 轉存：coordinator，逐字轉存 subagent 最終回報

---

## 本次結論
- 狀態報告一鍵檔已完成並推上遠端，沒有開 PR。分支 `feat/forecast-status-oneclick`，head `9f6fd279f77936f9a36503cbacf524c3bce6bad8`，從 `38b4855bd697c7db189c18e9d24792103183fe7a` 長出。
- 輸出時機照「逐段印出、最後一次寫檔」定稿實作（取代派工第 3 項），也含 RC-303（記事本開啟失敗靜默略過）。
- 有一個「唯讀」的實證發現要你決定：WAL 主 DB 留有未 checkpoint 的 `-wal` 時，這支工具若是最後一個連線，關閉連線會把內容 checkpoint 進主 DB 本體，主 DB 位元組會變，`-wal`、`-shm` 會被刪（RC-294 第 vi 項）。
- 500 筆時 `verify --all` 中位數約 31 秒，遠低於 10 分鐘，不必退回 tech-architect。

提交：
| commit | 說明 |
|---|---|
| `4db805d` | `feat: 新增預測紀錄帳狀態報告腳本（status 加 verify --all，唯讀）` |
| `b9bb71a` | `feat: 新增狀態報告一鍵檔 forecast-status.bat` |
| `f80ebd8` | `test: 狀態報告腳本與一鍵檔的測試（S-21a，九句固定句逐字比對）` |
| `9f6fd27` | `test: 修正狀態報告測試的型別標註（mypy）` |

新增檔案（絕對路徑，都在 `/home/user/AICompany/.claude/worktrees/agent-ab5f1bf75d430b1de/apps/stock-desk/` 下）：
- `backend/scripts/forecast_status.py`
- `forecast-status.bat`
- `backend/tests/test_forecast_status_flow.py`（92 個測試）
- `backend/tests/forecast_status_world.py`

不改任何既有檔。`.gitattributes` 沒有動：根目錄的 `*.bat text eol=crlf` 已涵蓋，測試用 `git check-attr` 確認 `text: set`、`eol: crlf`。

## 各項回報

**執行順序（照定稿，集中在 `flow`；輸出只有 `say`／`show` 一個口）**
1. 檢查環境變數 `STOCK_DESK_DB_PATH`（含空字串）→ STOP，不開連線。
2. 決定存檔資料夾並做 git 工作樹檢查，此時不建資料夾 → STOP。
3. 執行 `status`，stdout 與 stderr 都攔進記憶體。
4. 回傳 0 才印第一段與分隔句，再執行 `verify --all`（同樣攔截）。
5. 印第二段；`verify` 結束碼 1 時接著印行動句；結束碼 3、4 時第二段改印 RC-299 的 STOP 句。
6. 把已印出的內容寫入 `status.txt.tmp`，改名為 `status.txt`，再開記事本。

- 四種情形都照定稿。(d) 含 `SystemExit(2)`、其他結束碼、例外、中斷、寫檔失敗：印 ERROR 句，已印出的內容不收回，不留 `status.txt` 或暫存檔。
- 失敗清理時，若 `stock-desk-status` 資料夾是這次才建的，會一併移除。
- 改名成功之後，開記事本失敗靜默略過，畫面、檔案與結束碼維持原樣（RC-303）。
- 同一秒再跑會建 `<時間>-2`、`-3` 資料夾，不覆蓋舊檔。
- 工具結束碼：正常完成 0（含 `verify` 結束碼 1、3、4），STOP 3，ERROR 1，中斷 2。

**九句固定句出處與比對測試**
- 出處：RC-291 六句在 `2026-11-20-補充十一與退役通知判定RC284至RC297-風控.md`；RC-298 分隔句、行動句與 RC-299 STOP 句在 `2026-11-20-補充十一增修確認與三句固定行RC298至RC302-風控.md`。
- 常數由 `/tmp/claude-0/-home-user-AICompany/3f76d891-50d3-55e1-b39d-925b8a90241a/scratchpad/fstatus/gen_sentences.py` 從兩份報告抽出填入（模板在同目錄 `forecast_status.template.py`），不是手打。
- 測試 `test_the_fixed_sentence_is_the_risk_control_text_verbatim[九個名稱]` 從報告逐字比對。
- `test_the_hook_sentence_is_the_error_sentence_verbatim` 比對 hook 內的字面。
- `test_the_extraction_fails_on_a_missing_report_or_label` 證明找不到報告、標籤重複或缺反引號時測試會失敗，不是跳過。

**測試與 S-21a 對應**
- AST（子命令字面、`--all`、不讀 `sys.argv`、import 範圍、不讀 `work/`、唯一輸出口、hooks 在最前、執行順序）：
  - `test_ast_the_only_subcommands_are_status_and_verify_and_verify_takes_only_all`
  - `test_ast_the_script_does_not_read_sys_argv_or_take_a_parameter`
  - `test_ast_imports_are_the_standard_library_and_report_only`
  - `test_the_script_loads_no_other_forecast_module_than_report_and_its_dependencies`
  - `test_ast_the_script_names_no_file_of_work_and_reads_no_env_file`
  - `test_ast_there_is_one_screen_port_and_it_is_the_say_function`
  - `test_ast_say_is_called_only_by_the_stops_the_show_function_and_the_handlers`
  - `test_ast_the_hooks_are_the_first_effective_statements`
  - `test_the_main_database_is_derived_from_the_scripts_place`
- 前置檢查：
  - `test_stock_desk_db_path_set_stops_before_any_connection`（三種值）
  - `test_the_environment_is_read_from_the_process_by_default`
  - `test_a_status_folder_inside_a_git_work_tree_stops_before_anything_is_read`
  - `test_a_status_folder_below_a_git_work_tree_also_stops`（STOP 時無連線、`report` 未被呼叫、沒建資料夾）
- 合成 ledger：
  - `test_the_two_parts_are_the_report_outputs_verbatim_with_only_the_separator_between`
  - `test_the_file_has_the_same_content_as_the_screen_in_utf8_sig_and_is_opened`
  - `test_a_second_run_gets_its_own_folder_and_never_overwrites_an_old_file`
  - `test_the_main_database_is_only_read_and_nothing_is_written_outside_the_status_folder`
  - `test_the_script_reads_the_ledger_through_a_query_only_connection`
  - `test_verify_exit_1_is_shown_and_saved_with_the_action_sentence_after_the_closing_line`
  - `test_the_action_sentence_is_absent_when_everything_is_consistent`
  - `test_status_exit_4_…`、`test_status_exit_3_…`（garbage、no-schema 兩種真實 `report` 結束碼 3）
  - `test_verify_exit_3_or_4_keeps_part_one_and_the_separator_then_the_stop_sentence`
  - `test_any_other_exit_code_or_exception_prints_the_error_sentence_and_leaves_no_file`（7 種情形 × 注入 status／verify 兩處）
  - `test_an_interrupt_prints_the_interrupted_sentence_and_leaves_no_file`
- stderr 攔截：
  - `test_argparse_usage_on_stderr_is_not_shown`
  - `test_the_report_stderr_is_on_neither_the_screen_nor_the_file`
  - `test_the_refusal_sentences_of_report_never_reach_the_screen`
- 寫檔與 RC-303：
  - `test_a_failure_while_writing_leaves_no_status_file_no_temporary_file_and_no_folder`（open、write、rename 三種）
  - `test_an_interrupt_during_the_rename_leaves_no_file_and_no_folder`
  - `test_the_text_is_written_to_a_temporary_file_that_is_then_renamed`
  - `test_a_status_root_that_cannot_be_made_is_the_error_sentence_after_the_shown_parts`
  - `test_rc303_an_opener_that_fails_leaves_the_saved_file_the_screen_and_the_exit_code`（OSError、RuntimeError、KeyboardInterrupt）
  - `test_no_opener_is_used_off_windows`
  - `test_the_windows_opener_is_notepad_on_the_status_file`
- 標籤、基準預測與 hash 檢查：
  - `test_the_ledger_has_passed_records_with_labels_and_the_screen_still_has_none`：先斷言合成 ledger 同時有已過與未過的紀錄。
  - `test_the_fixed_sentences_alone_contain_no_label_baseline_or_hash`
- D-4：`test_the_whole_screen_passes_the_d4_checker`（正常、不一致、verify 3 三種）。對九句也各跑 `d4_violations`，結果為空，風控分隔句與行動句沒有觸發既有規則，我沒有改規則或字面。
- e2e 子行程：
  - `test_e2e_a_real_interpreter_run_on_a_synthetic_backend_shows_and_saves_the_two_parts`
  - `test_e2e_the_environment_variable_stops_a_real_interpreter`
  - `test_e2e_an_exception_or_an_interrupt_shows_only_what_was_shown_and_the_fixed_sentence`（3 種例外 × status／verify 兩處）
  - `test_e2e_threads_warnings_unraisables_and_uncaught_errors_print_the_fixed_sentence`
  - `test_e2e_an_exception_in_a_thread_during_the_run_shows_only_the_fixed_sentence`
  - e2e 把腳本複製到假 backend，由腳本位置導出 DB 路徑；子行程內擋住任何指向真實 `data/` 的 `sqlite3.connect`。
- `.bat`：
  - `test_the_bat_is_a_crlf_launcher_that_clears_uv_env_file_first`
  - `test_the_bat_differs_from_the_precedent_only_in_the_listed_lines`
  - `test_the_bat_has_no_non_cmd_redirect_and_only_r2_lines_besides_its_own`
  - `test_git_checks_the_bat_out_with_crlf`
  - `test_the_script_and_the_launcher_are_outside_app`
- 防護：測試用 `tmp_path`，不碰 `.env`；沿用 conftest 的網路封鎖與預設 DB 路徑 sentinel；監控所有 `sqlite3.connect` 目標與寫入模式的 `open`。

**`.bat` 與 `pipeline-acceptance.bat` 逐行差異**（共 6 行，總行數相同，CRLF）
1. `title stock-desk pipeline-acceptance` 改為 `title stock-desk forecast-status`
2. 第 5 行註解改為 `REM One-click forecast status report: a thin launcher. All logic lives in`
3. 第 6 行註解改為 `REM backend\scripts\forecast_status.py (ADR-0030 supplement 11 points 2 and 4).`
4. 第 7 行註解改為 `REM The script only reads the main database (no copy, no write); this launcher never`
5. `echo After installing, run this script again.` 改為 `echo Tell the coordinator.`
6. 指令行的腳本名改為 `scripts\forecast_status.py`

其餘（`UV_ENV_FILE` 清空、`where uv`、`cd /d`、`uv run --no-sync python -I -X utf8`、`pause`、NOTE 行）不變。`[MISSING] uv - install from https://…` 那行我保留，因為 RC-291 只要求換「After installing」那句；是否也要改，請你或風控裁示。

**RC-294 實證**（腳本 `/tmp/claude-0/-home-user-AICompany/3f76d891-50d3-55e1-b39d-925b8a90241a/scratchpad/fstatus/rc294_probe.py`，輸出 `/tmp/claude-0/-home-user-AICompany/3f76d891-50d3-55e1-b39d-925b8a90241a/scratchpad/fstatus-rc294-output.txt`；實測時兩套全套測試同時在跑，耗時偏長）
- 主 DB 的 journal 模式：由 `app/data/cache.py` 的 `PriceBarCache._init_schema`（第 168 行起；第 170 行 `enable_wal(conn)`）設定。實作在 `app/data/sqlite_util.py` 的 `enable_wal`，其他 store 的 `_init_schema` 也呼叫它。`app/forecast/store.py` 自己不設 journal 模式，只設 `busy_timeout`（第 186 行，值為 5000 ms），測試用的 `file_ledger` 預設不是 WAL。
- (i) WAL 合成 DB，另一個行程連續以唯讀連線讀 `status` 與 `verify`：recorder 的 40 次完整 `record_forecasts`（含 `begin_run`、`write_run_records`、`end_run`）全部 commit，沒有 busy。讀者 12 次讀取、0 錯誤。最後 runs 48、ends 48。
  - 無讀者時中位數 0.185 秒（最大 0.337）。
  - 有讀者時中位數 0.260 秒（最大 0.542）。
- (ii) 讀取發生在 `begin_run` 與 `end_run` 之間：`status` 顯示「沒有 end 列=1」，不報錯，工具結束碼 0。產品線版沒有「最近一次執行」那行，符合預期。`end_run` 之後同一行變成「沒有 end 列=0」。
- (iii) 對照：讀者持讀鎖 3 秒時，rollback journal 模式下寫入者一次完整 recorder 執行等了 3.15 秒，之後成功（`busy_timeout` 5000 ms，讀者若持鎖超過 5 秒就會拋 busy）。WAL 模式同條件下 0.12 秒。
- (v) 一次正常 `record_forecasts`（合成資料，到 end 列）：連跑 250 次，第一次 0.193 秒、中位數 0.173 秒、最大 0.337 秒。
- (vi) 額外發現，需要你決定：在 WAL 模式、有未 checkpoint 的 `-wal`、沒有其他連線時跑這支工具，前後對照：
  - 主 DB 的 sha 與 mtime 都變了；
  - `-wal`、`-shm` 被刪；
  - 原因是 SQLite 在最後一個連線關閉時 checkpoint。
  - 「經 `_read`（query_only）讀取」擋得住 SQL 寫入，擋不住這種位元組層級的變化，內容在邏輯上不變。
  - 補充十一第 2 點與 RC-294 的文字是否需要改，請裁示；我沒有自行處理。

**`verify --all` 耗時與整支工具耗時**（腳本 `/tmp/claude-0/-home-user-AICompany/3f76d891-50d3-55e1-b39d-925b8a90241a/scratchpad/fstatus/verify_timing.py`，輸出 `/tmp/claude-0/-home-user-AICompany/3f76d891-50d3-55e1-b39d-925b8a90241a/scratchpad/fstatus-verify-timing-output.txt`；各跑 3 次取中位數；量測時有兩個全套測試同時在跑，所以是偏保守的數字）
| 紀錄筆數 | `verify --all` 中位數（3 次） | `status` 中位數 | 整支工具（行程內 `main`）中位數 |
|---|---|---|---|
| 0 | 0.04 秒（0.04、0.05、0.04） | 0.01 秒 | 0.06 秒 |
| 250 | 16.34 秒（15.26、16.34、16.72） | 1.27 秒 | 17.60 秒 |
| 500 | 30.71 秒（33.67、30.71、28.06） | 1.99 秒 | 32.93 秒 |

- 500 筆沒有超過 10 分鐘，不必退回 tech-architect。
- 真實直譯器端到端（`python -I -X utf8`，不含 uv 啟動，腳本 `/tmp/claude-0/-home-user-AICompany/3f76d891-50d3-55e1-b39d-925b8a90241a/scratchpad/fstatus/e2e_timing.py`，輸出 `/tmp/claude-0/-home-user-AICompany/3f76d891-50d3-55e1-b39d-925b8a90241a/scratchpad/fstatus-e2e-timing-output.txt`）：0 筆 0.5 秒，500 筆中位數 32.6 秒（28.8、32.6、34.5）。
- 雙擊到畫面完成還要加 `uv run` 啟動與 Windows 的行程開銷，我沒有在 Windows 實測，不報數字。

**全套與品質檢查**（最後 commit 前啟動；最後一個 commit `9f6fd27` 只改一處 mypy 型別標註 `str(...)`，之後單獨重跑這支工具的測試，3.12 與 3.13 都是 92 passed）
- 這支工具的測試：3.12 為 92 passed（45.8 秒，改型別後 50.7 秒）；3.13 為 92 passed（51.3 秒，改型別後 50.5 秒）。
- 全套 3.12：12159 passed、2 xfailed、1 warning，48 分 6 秒，coverage 97.81%（門檻 90%），結束碼 0。輸出 `/tmp/claude-0/-home-user-AICompany/3f76d891-50d3-55e1-b39d-925b8a90241a/scratchpad/fstatus-full-312.txt`。
- 全套 3.13：12159 passed、2 xfailed、34 warnings，44 分 5 秒，coverage 97.81%，結束碼 0。輸出 `/tmp/claude-0/-home-user-AICompany/3f76d891-50d3-55e1-b39d-925b8a90241a/scratchpad/fstatus-full-313.txt`。
- 2 個 xfailed 是既有測試，不是我加的。
- 全套是在最後一個 commit 之前啟動的；若你要求嚴格「最後 commit 之後全套」，需要再跑一次。
- `ruff check .`、`ruff format --check .`、`mypy app tests`：全綠（536 個來源檔）。

**交件檢查**
- `git diff --name-status 38b4855 HEAD`（以我分支點為基準）只有 4 個 `A`。若直接對最新 `origin/product/stock-desk` 比，還會出現 `work/` 下的 M／D，那是產品線在我分支之後新增的 coordinator 提交，不是我的變更。
- `git diff --stat origin/product/stock-desk HEAD -- apps/stock-desk/backend/app` 為空。
- `git rev-parse HEAD:apps/stock-desk/backend/app` 為 `07b5e1fd95fa933d969ba4f5adecb3c982be0a62`，與目前產品線相同。

**突變檢查**（腳本 `/tmp/claude-0/-home-user-AICompany/3f76d891-50d3-55e1-b39d-925b8a90241a/scratchpad/fstatus/mutate.py`，輸出 `/tmp/claude-0/-home-user-AICompany/3f76d891-50d3-55e1-b39d-925b8a90241a/scratchpad/fstatus-mutations-output.txt`；每次突變後都還原，`git status` 乾淨）
| 突變 | 結果 |
|---|---|
| stderr 漏出（不攔 `report` 的 stderr） | 多個測試失敗（status 3／4、verify 3／4、其他結束碼等） |
| 分隔句改一個字 | 1 failed，91 passed（逐字比對失敗） |
| `status` 失敗仍執行 `verify` | 2 failed（`test_status_exit_4_…`、`test_the_refusal_sentences_…[4]`），88 passed |
| 失敗時仍留檔（清理不執行） | 4 failed（寫檔失敗三種加改名中斷） |
| 開記事本失敗的例外外洩 | 3 failed（RC-303 測試） |

**四種結束情形的畫面樣本**（合成資料，完整輸出在 `/tmp/claude-0/-home-user-AICompany/3f76d891-50d3-55e1-b39d-925b8a90241a/scratchpad/fstatus-samples-output.txt`，腳本 `/tmp/claude-0/-home-user-AICompany/3f76d891-50d3-55e1-b39d-925b8a90241a/scratchpad/fstatus/samples.py`）
- (a) status 結束碼 4：只有 `STOP: stock-desk.db was not found at the default location. Do not change any setting or file yourself; tell the coordinator.`；結束碼 3 時是 `STOP: the execution status could not be read from the database, so nothing was shown. Do not change any setting or file yourself; tell the coordinator.`；都不寫檔。
- (b) status 0、verify 0：第一段（11 行起，從「執行狀態（只含執行狀態，不含任何標籤或對照）」到兩行「重審觸發」）＋分隔句＋第二段（首行 `verify（D-5 第 3 點：…）`，每筆一行，末行 `verify：全部一致`）。verify 1 時，在 `verify：有不一致（F-3：停止記錄並查明）` 之後多一行行動句。
- (c) status 0、verify 3：第一段＋分隔句＋`STOP: the recomputation check could not be read from the database, so it was not shown. Do not change any setting or file yourself; tell the coordinator.`，有存檔。
- (d) 例外：第一段＋分隔句＋`ERROR: unexpected failure. Tell the coordinator.`，不存檔。status 執行中就失敗時，畫面只有 ERROR 句。

**產品線版與接線版 `report.main` 介面差異**
- 沒有差異：`main(argv=None, *, clock=None)`，從 `def run_command` 到檔尾兩版完全相同，`diff` 為空，結束碼 0／1／3／4 的意義與寫到 stderr 的拒絕句都相同。
- 其餘差異只在 render 部分：接線版少 `f2_window`，多 `_fill`、`_f2_line`、`_latest_run_line`、`_grid_line`。
- 產品線版的 `status` 輸出已含 F-2 計數與重審觸發行，沒有「最近一次執行」行。

## 驗證
- 以上所有數字都是實際跑出來的。
- 全程沒有讀 `.env` 的值，沒有碰 `apps/stock-desk/backend/data/*.db`，沒有執行任何 `.bat`，沒有連網，沒有對真實 DB 執行腳本。

## 下一步與待決
**留給接線 PR 的測試**：最近一次執行、F-2 兩句、兩行缺日加註出現在第一段。這些需要接線版 `report`，這次沒做。

**未在 Windows 實測**
- `.bat` 本身的執行與 `uv run`。
- 以 `notepad.exe` 開啟（只測了呼叫的 argv）。
- cmd 主控台顯示中文：`-X utf8` 輸出 UTF-8，舊式 code page（如 950）的主控台可能亂碼，這是待決項，見下。
- 實際雙擊耗時。

**待決（我沒有自行決定）**
1. 主控台中文編碼：`status` 與 `verify` 原樣輸出中文，加上 RC-298 的中文分隔句與行動句，cmd 在舊 code page 下可能亂碼。`.bat` 比照前例沒有 `chcp 65001`。記事本開啟的檔案是 `utf-8-sig`，內容不受影響。要不要加 `chcp 65001 >nul`（會改變 `.bat` 與前例的差異），請裁示。
2. 上述 RC-294 (vi)：最後一個連線關閉時 checkpoint 會改動主 DB 本體；補充十一與 RC-294 的「唯讀」措辭是否要補充，請 tech-architect 與風控裁示。
3. `.bat` 的 `[MISSING] uv - install from https://…` 一行是否也要改成不請 CEO 自行安裝，請風控裁示。
4. 固定句測試依賴 `work/reviews/` 的兩份風控報告（往上層資料夾尋找）。CI 若沒有這兩份報告，測試會依規定失敗（不跳過）。合併進產品線前請確認 CI 能取得；我沒有加環境變數覆寫路徑。
5. 失敗時 `~/stock-desk-status` 資料夾若是這次才建的會一併移除；若早已存在且非空則保留。這是我的實作取捨，規格沒有明講。
6. 程序環境變數檢查與 git 工作樹檢查都在跑 `status` 之前，STOP 時完全沒有連線。
7. 量測腳本與輸出都在 scratchpad（可能被清理）。要永久保存或納入 `scripts/`，請告知；這次只新增了被指定的檔案。

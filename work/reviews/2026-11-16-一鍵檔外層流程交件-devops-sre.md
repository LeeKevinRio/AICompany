# 真實資料一鍵檔外層流程交件

- 審查者：devops-sre
- 日期：2026-11-16
- 轉存：coordinator，逐字轉存 subagent 最終回報

---

## 本次結論

一鍵檔第二段已完成並 push 到 `origin/feat/nm5-pipeline-acceptance-oneclick`（e5f4411..6c2253f，fast-forward）。外層流程、`.bat`、eol 檢查、測試、CEO 說明全部到位，並已套用 TA 六點差異、C-1～C-9、補充六／附記／附記二、RC-158～RC-167。沒有讀 `.env`、沒碰 `data/*.db`、沒上網取數、沒 rebase／amend／force push。測試只用 `tmp_path` 與合成資料。

**head（40 碼）：`6c2253f2984c9415f82b8538c107376b8d0d36ef`**

| commit | 內容 |
|---|---|
| `b38e452fbf25776a3b9840cb9cc74b617e8d43ea` | merge `origin/product/stock-desk`（附記六） |
| `fea9194371dd51c5927e8ee930d0288f424dc7bd` | 再 merge 一次（附記二、RC-167、TA 的 WAL 裁示） |
| `efc75883dcede722155d9392069cbc3931b35d2a` | `feat:` 外層流程；hooks；`tests/pipeline_real_loader.py`；dev-lead 測試改用 loader |
| `25ff350449509298391b4d0649f40a4008fc010d` | `ci:` `backend/.gitattributes` 加 `uv.lock text eol=lf`，加測 `check_pinned_eol` 與真 git 前置檢查 |
| `f4f775f51f154c352aa310e2e9ba7eee96226e55` | `test:` e2e 監聽、STOP、白名單、毒藥、RC-162 中斷測試 |
| `900d419bb50df4a5845a131516fb1c9638ddf763` | `feat:` `pipeline-acceptance.bat` |
| `6c2253f2984c9415f82b8538c107376b8d0d36ef` | `docs:` CEO 操作說明 |

## 各部門回報

### devops-sre 實作摘要
- **hooks（RC-162 附記第 5 點）**：檔案最前面（docstring、`__future__`、`import sys/threading/warnings` 之後）先換三個 excepthook 並執行 `warnings.simplefilter("ignore")`，`app` 與 harness 在這之後才 import。`main` 最外層攔 `BaseException`，只印固定句（`KeyboardInterrupt` 印另一句固定句），`finally` 照常清理後回非零結束碼。
- **流程順序**：前置檢查、掃除殘留、三檔位元組複製（只 `"rb"` 讀主 DB）、複本雜湊比對、守門反例測試、`read_twii_bars`、刪複本（在 `finally` 內，刪不掉就 RC-158c STOP）、`check_depth`、`bars_sha256`（只算一次）、P-0／P-1 各一次、白名單過濾、寫 `paste-back.txt`（`utf-8-sig`）、清理。主控台一律 ASCII，所有輸出在最後才一次印出，所以中斷時不會有半截輸出。
- **AcceptanceResult**：只讀 `.passed`，另外呼叫 `render_summary`。不輸出 `where`。「視窗定案 session 數」列為已知不輸出，不計入 `summary_lines_dropped`。
- **dev-lead 測試**：他的 47 個測試維持全過。載入方式改為共用 `tests/pipeline_real_loader.py`，保存並還原三個 hook 與 warnings filter。
- **dev-lead 測試的三處必要調整**（原本是整檔掃描，與外層流程衝突）：
  - 「無 `open`」改為只掃 reader 區段（`# === the outer flow` 標記線以上）。
  - 「網路模組」允許 `socket` 只出現在 `port_is_listening` 的函式內 import，這是 loopback 8000 埠檢查，r2 前例，也維持 `-I` 載入時 `sys.modules` 不含 socket。
  - 外層的字串常數要避開他的 SQL 關鍵字掃描（例如 STOP 句用 "Remove" 而非 "Delete"）。
- **WAL 判斷集中處（待 TA／風控的事項已結案）**：判斷只在 `copy_uri` 一處，由複本旁有無 `-wal` 決定，外層沒有繞過；有測試 `test_the_wal_decision_is_made_in_one_place_from_the_copy` 守住。附記二已定案採 A。若日後改為「有 `-wal` 就停止」，只需改 `copy_uri` 與新增 STOP 種類。
- **其他 TA 判定**：
  - `_snapshot_bar` 同一物件的測試已加。
  - 非有限數值走固定 ERROR 句，不新增 STOP 種類，已測。

### 回報事項：CEO 說明文件
`work/dispatch/2026-11-16-真實資料管線驗收操作說明-CEO.md`，已確認被 git 追蹤（`work/.gitignore` 的 `!dispatch/**` 放行）。內容有三步驟、區塊一（RC-166 新版）到區塊五、RC-158c 中文句、STOP／ERROR 對照表（共 19 句）。沒有列九個失敗代號、沒有解釋任何代號。引文是用腳本從風控報告抽出再寫入，STOP 英文句取自腳本自己的表。

## 驗證

**全套（head `6c2253f`）**：
- `uv run pytest --cov=app --cov-fail-under=90`：**11977 passed、2 xfailed**，覆蓋率 **97.80%**（22642 行、miss 497），耗時 31 分 16 秒。
- 新增 129 個測試（dev-lead 交件時為 11848）。
- `ruff check .`：All checks passed。`ruff format --check .`：545 files already formatted。
- `mypy app tests scripts/pipeline_acceptance_real.py`：Success，534 source files。

**反向驗證**（暫時改壞腳本、確認測試擋下，已用 `cmp` 確認還原）：
- RC-158c 刪除失敗的判斷改成永遠通過：3 個測試失敗。
- 拿掉 `warnings.simplefilter`：2 個測試失敗。
- 取消「視窗定案 session 數」行的跳過：3 個測試失敗。

**「不得動」清單零 diff**：
```
git diff --stat origin/product/stock-desk...HEAD -- apps/stock-desk/backend/app \
  apps/stock-desk/backend/tests/forecast_pipeline_harness.py \
  apps/stock-desk/backend/tests/dirdef_helpers.py \
  apps/stock-desk/backend/tests/outlook_helpers.py \
  apps/stock-desk/backend/uv.lock .gitattributes
```
輸出為空。整個分支相對 product 只動 10 個檔：`backend/.gitattributes`、`scripts/pipeline_acceptance_real.py`、`tests/` 下 5 個檔（含 dev-lead 的 `test_import_graph.py` 與 `test_pipeline_acceptance_real_bars.py`）、`pipeline-acceptance.bat`、CEO 說明。

**`git ls-files --eol -- uv.lock`（加 `.gitattributes` 後，在本 worktree 實跑）**：
```
i/lf    w/lf    attr/text eol=lf      	uv.lock
```
**臨時 repo 實證**：
- 加屬性後，`git checkout HEAD -- uv.lock` 能把 CRLF 工作樹修回 LF：`test_the_attribute_makes_checkout_head_repair_a_crlf_work_tree`。
- `core.autocrlf=true` 加屬性後，重新 checkout 仍是 LF：`test_with_autocrlf_true_the_attribute_keeps_a_fresh_checkout_lf`。
- 對照組：沒有屬性時，`autocrlf=true` 的 checkout 會寫出 CRLF 並被判停止：`test_control_without_the_attribute_autocrlf_true_writes_crlf`。

**風控定稿逐字比對**（腳本與指令在 `/tmp/claude-0/-home-user-AICompany/3f76d891-50d3-55e1-b39d-925b8a90241a/scratchpad/build_doc.py` 與 `verify_doc.py`；驗證指令 `python3 …/verify_doc.py "$PWD"`，在 worktree 根目錄執行）。驗證法：另用 regex 從原報告抽出引文，檢查說明文件裡的連續 `> ` 引文區塊逐字包含，並逐行包含。結果：
```
區塊一(RC-166新版): 行數=4 字元=458 連續區塊逐字包含=True 逐行包含=True
區塊二: 行數=2 字元=202 連續區塊逐字包含=True 逐行包含=True
區塊三: 行數=1 字元=99  連續區塊逐字包含=True 逐行包含=True
區塊四: 行數=1 字元=197 連續區塊逐字包含=True 逐行包含=True
區塊五: 行數=1 字元=221 連續區塊逐字包含=True 逐行包含=True
RC-158c STOP句: 行數=1 字元=85 連續區塊逐字包含=True 逐行包含=True
舊區塊一的舊片語不在文件中: True
文件中出現的失敗種類代號: []
where 不在文件中: True
ALL OK
```
腳本在 scratchpad，未進 repo。

**合成假主 DB 完整流程的 `paste-back.txt`**（340 根合成 `^TWII`，`git_head`／雜湊為合成環境的值，不是真實值）：
```
管線驗收：使用歷史資料，不是前瞻紀錄；只驗證程式流程，不是績效證據，不計入任何驗證統計；規則未經驗證。
本次使用佔位規則，輸出不是任何將登記規則的判斷。
pipeline_acceptance_real version=1
script_sha256_lf=946faea30f0f49dbde5b258ee30a9342a20b1cd68e443362b6ef8890e431fe9f
harness_sha256_lf=08245a45e8db1739f3f47b193d4b07408a03e3b89ad3c26f6e1f0f765d5bb9d2
git_head=aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa
git_clean=yes
core_autocrlf=unset
eol_check=ok
code_digest=af3aa64b5f7c12f07e26df511a78bd909306c8190a51bc604469ed383943f751
lockfile_sha256=38f903b16cada05a21faee6070b870d582a81fbc38c415ce39259a01f832c19e
definition_sha256=a0d0a34d5fad3593b902c755b3c060497901acc2ba923c71fef5b9ebe89bd6e2
definition_logic_sha256=4cc1fe80054a017f47030805a486ad81e1bda249d730c7c1f6bd2c73c01d1afa
db_location=default
port_8000_listening=no
copy_check=SAME
copy_check=absent_both
copy_check=absent_both
refusal_guard=ok
cache_depth=sufficient
bars_sources=yfinance
bars_sha256=0fba2a1f9eb6c56cf45703d43555685944cae2037dda36db8a1e7d30670cd3bd
管線驗收 P-0：通過
執行次數：ok=21
失敗種類：無
暫存帳 sha256：1277afb5f23e9c5b6347cab2fce99a214e90a2f7196c72de17d89b74a2da8cc0
輸出 sha256：368c20d1b78eb20a315f8ed9f36dca11b8c654d90a820ad89471d378e3e9beef
管線驗收 P-1：通過
執行次數：ok=21
失敗種類：無
暫存帳 sha256：d7ff1e086e05a92a6a6d089320f3e7cc0f39940332d28ffeb832f00aa0368539
輸出 sha256：f238f28f58207a782022e2eb861a05002d7f6e7fb2b728fd800295124e84466d
acceptance_result=PASS
cleanup=ok
summary_lines_dropped=0
done_at_utc=2026-11-16T11:55:52Z
```
跑完後工作資料夾只剩 `paste-back.txt`。

### S-13b、S-13c、S-13d 對應測試表

測試檔簡稱：**F** = `tests/test_pipeline_acceptance_real_flow.py`；**B** = `tests/test_pipeline_acceptance_real_bars.py`（dev-lead）；**E** = `tests/test_pipeline_acceptance_real_eol.py`；**G** = `tests/test_import_graph.py`（dev-lead）。

| 條款 | 測試（檔） |
|---|---|
| S-13b 1：e2e 監聽，主 DB 只被 `open("rb")`，從未 connect | `test_e2e_the_main_database_is_only_opened_rb_and_never_connected`（F） |
| S-13b 1：connect 目標 ⊆ {複本, 兩 ledger} | `test_e2e_every_connect_target_is_the_copy_or_a_ledger`（F） |
| S-13b 1：import 不含 (c) 模組（AST＋執行期 `sys.modules`） | `test_the_script_has_no_forbidden_import_in_ast_and_at_run_time`（F）、`test_the_script_imports_no_forbidden_module`、`test_the_isolated_import_is_silent_and_loads_no_forbidden_module`（B） |
| S-13b 1：socket 換成拋例外的替身仍完成 | `test_the_run_completes_with_the_socket_replaced`（F）、`test_reading_works_with_the_socket_replaced`（B）、`test_the_script_has_no_network_call_in_the_flow`（F） |
| S-13b 1：列對應與 `PriceBarCache` 逐欄相同 | `test_the_mapping_equals_the_cache_read_except_as_of`（B） |
| S-13b 1 (e)：每個停止條件各一測試 | `test_stop_of_the_reader_and_the_depth[no_rows／unparseable_row／demo_source／foreign_source／cache_short]`（F，e2e）；`test_no_rows_stops`、`test_an_unparseable_row_stops_and_no_row_is_skipped`、`test_a_demo_row_stops`、`test_a_row_from_another_source_stops`、`test_a_short_cache_stops`（B） |
| 外層各 STOP | `test_stop_env_db_path`、`test_stop_env_file_db_path`、`test_stop_no_db`、`test_stop_port_listening`、`test_stop_work_folder_inside_a_git_work_tree`、`test_stop_git_unusable`、`test_stop_git_dirty`、`test_stop_head_not_published`、`test_stop_eol_second_evidence`、`test_stop_eol_bytes_differ_from_the_blob`、`test_stop_copy_changed_while_copying`、`test_stop_copy_presence_differs`、`test_stop_guard_never_refuses`、`test_stop_guard_refuses_the_ledger_too`（F） |
| S-13b 1：複本在第一次 `run_acceptance` 前已刪除 | `test_the_copy_is_gone_before_the_first_run_acceptance`（F） |
| S-13b 1：`app/` 不可達 `scripts/` 與 harness | `test_import_graph.py` 內 dev-lead 加的測試（G） |
| S-13b 2：`as_of` 為當日 20:00 Taipei | `test_every_as_of_is_twenty_hundred_taipei_on_its_own_session`（B）、`test_the_flow_injects_20_hundred_taipei_stamps`（F） |
| S-13b 2：SELECT 不含 `as_of`、`fetched_at`（AST） | `test_the_script_has_one_select_of_the_eight_columns_and_no_write`（B）、`test_the_only_select_never_names_as_of_or_fetched_at`（F） |
| S-13b 3：只存取 `passed`＋呼叫 `render_summary`（AST） | `test_ast_the_result_is_only_read_for_passed_and_rendered`（F） |
| S-13b 3：結束後只剩回貼檔 | `test_after_the_run_only_the_paste_back_file_is_left`（F） |
| S-13b 3：殘留掃除不動格式不符的資料夾 | `test_residue_of_earlier_runs_is_swept_and_other_folders_are_left`（F）；另 `test_a_stale_ledger_folder_that_cannot_be_deleted_reports_cleanup_failed` |
| S-13b 4：白名單每樣式各一測試 | `test_whitelist_shape[…]` 對 29 個樣式參數化，`test_every_whitelist_shape_has_a_sample` 保證樣式與測試一一對應（F） |
| S-13b 4：無關行被丟棄並計數 | `test_unrelated_lines_are_dropped_and_counted_and_the_window_line_is_not_counted`、`test_e2e_extra_summary_lines_are_dropped_counted_and_never_shown`（F） |
| S-13b 4：session 數行不輸出也不計入 | `test_the_window_line_is_neither_printed_nor_counted`（F） |
| S-13b 4：毒藥測試，不含 `T=`、`claim_id`、輸出任一行、禁詞 | `test_poison_no_label_comparison_or_output_line_reaches_the_screen_or_the_file`（F，含「fixture 確實有標籤」的前置斷言）、`test_a_failing_harness_result_prints_only_kinds_and_never_where` |
| S-13b 4：兩組標籤分佈，除雜湊／`bars_sha256`／執行次數外逐行相同 | `test_two_label_distributions_give_the_same_paste_back_but_hashes_and_counts`（F） |
| S-13b 4：`bars_sha256` 等於獨立 `content_sha256`，兩規則集共用一個值 | `test_bars_sha256_is_the_independent_content_sha256_printed_once`（F）、`test_bars_sha256_is_the_content_sha256_of_the_injected_series`、`test_bars_sha256_has_no_serialisation_of_its_own`（B） |
| S-13b 4：`bars_sources` 封閉集 | `test_bars_sources_is_the_closed_set`（F） |
| S-13b 7／C-8：eol | `test_lf_work_tree_is_ok`、`test_crlf_work_tree_is_a_stop`、`test_check_pinned_eol_changes_nothing`、`test_the_second_evidence_alone_also_stops` 等（E）；`test_the_backend_attribute_file_pins_uv_lock_to_lf`、`test_git_ls_files_eol_of_the_real_uv_lock_is_lf_lf`、`test_the_root_attribute_file_is_not_changed_by_this_work` |
| S-13c 1 (RC-158a)：監聽涵蓋 `open`／`os.open`／`remove`／`unlink`／`rename`／`replace`／`utime`／`chmod`／`truncate`／`shutil.move`／`shutil.copy*` 目的地 | `test_e2e_the_main_database_is_only_opened_rb_and_never_connected`；監聽器自身的 `test_the_monitor_has_teeth` |
| S-13c 3 (RC-158c)：刪除失敗，harness 未呼叫、輸出只有該 STOP 句 | `test_rc158c_a_copy_that_cannot_be_deleted_stops_before_the_harness`、`test_rc158c_only_the_shm_cannot_be_deleted`、`test_a_copy_left_by_an_earlier_run_that_cannot_be_deleted_stops`、`test_the_delete_is_retried_five_times_with_pauses`（F） |
| S-13c 4 (RC-160c)：去重、排序、不帶次數 | `test_failure_kinds_are_deduplicated_sorted_and_carry_no_count`（F；同種多次只列一次、順序不同輸出相同） |
| S-13c 5 (RC-162 a)：hooks 為第一批敘述（AST） | `test_ast_the_hooks_are_the_first_effective_statements`、`test_the_hook_sentence_is_the_error_sentence`（F） |
| S-13c 5 (RC-162 b、d)：`BaseException`、整段 stdout／stderr 每行 fullmatch 白名單或固定句 | `test_rc162_the_normal_screen_is_closed`、`test_rc162_every_stop_screen_is_closed`、`test_the_stop_and_error_sentences_are_fixed_ascii_without_values` |
| S-13c 5：harness 拋例外 | `test_rc162_a_failing_harness_prints_only_the_fixed_sentence` |
| S-13c 5：`KeyboardInterrupt`（取數中、harness 中、清理中，另加等待 Enter 時） | `test_rc162_a_keyboard_interrupt_prints_the_fixed_sentence_and_cleans_up[read／harness／cleanup／wait]`、`test_rc162_an_interrupt_while_deleting_the_copy_is_the_fixed_sentence_too` |
| S-13c 5：執行緒例外、警告、unraisable、未攔截例外 | `test_rc162_threads_warnings_unraisables_and_uncaught_errors_print_the_fixed_sentence`（真實 `python -I` 子行程） |
| 真實 CLI 路徑 | `test_the_cli_stop_through_a_real_isolated_interpreter`（`python -I -X utf8`，真 stdin） |
| S-13d：有 `-wal` 的複本，`.db`／`-wal` sha256 不變、只多 `-shm` | `test_wal_copy_reads_the_uncheckpointed_row_and_adds_only_a_shm`（F）、`test_a_copied_wal_is_read_and_not_written`（B） |
| S-13d：無 `-wal` 不產生側檔、URI 帶 `immutable=1` | `test_a_copy_without_wal_gets_immutable_and_no_side_file`（F）、`test_the_uri_is_read_only`、`test_reading_changes_no_byte_and_creates_no_side_file`（B） |
| S-13d：AST 連線只執行 `query_only` 與 `_SELECT_SQL` | `test_ast_the_connection_runs_only_query_only_and_the_select`（F） |
| S-13d：`copy_check` 在第一次 `sqlite3.connect` 之前完成 | `test_e2e_copy_check_is_done_before_the_first_connect`（F） |
| S-13d：清理後複本三檔都不存在 | `test_the_copy_files_do_not_exist_after_the_run`（F）、`test_e2e_a_wal_main_database_is_copied_read_and_deleted` |
| **RC-167b**：讀取前後主 DB 三檔 sha256 與 mtime 不變 | `test_the_main_database_files_are_unchanged_in_bytes_and_mtime`（F，單 `.db`）；`test_e2e_a_wal_main_database_is_copied_read_and_deleted`（F，真有 `-wal`＋`-shm`，斷言 3 個檔，且只被 `"rb"` 開啟） |
| **RC-167c**：WAL 測試斷言讀出的列含未 checkpoint 的列 | `test_a_copied_wal_is_read_and_not_written`（B，dev-lead 既有，**確認存在**，斷言最後一根只在 `-wal` 的 bar 被讀出）；`test_wal_copy_reads_the_uncheckpointed_row_and_adds_only_a_shm`（F）；`test_e2e_a_wal_main_database_is_copied_read_and_deleted`（F，`bars_sha256` 涵蓋只在 `-wal` 的三根）。qa 請親自重驗。 |
| TA (i) | `test_recorder_and_bars_sha256_use_the_same_snapshot_bar_object`（F） |
| TA (ii) | `test_a_non_finite_value_is_the_fixed_error_sentence_and_the_harness_never_runs`（F） |
| `.bat` | `test_the_bat_is_a_crlf_launcher_that_clears_uv_env_file_first`（F） |

## 下一步

1. **qa-reviewer（含 Codex）**：
   - 依 S-13b／c／d 與 RC-158b、RC-167c 審查。
   - 逐字比對說明文件區塊一到五與 RC-158c 句。
   - RC-158b 的 AST 掃描也涵蓋我新增的測試檔：我沒在測試裡引用 `read_twii_bars` 的名稱字串，改用 `real.read_twii_bars.__name__`。
2. **coordinator**：確認附記第 6 點的四項前提（本 PR 的測試、qa PASS 加 CI 綠、說明文件逐字、coordinator 確認）後，才通知 CEO 執行時機。

## 我自定的解讀與已知限制（請 qa／TA 看過）

1. **`copy_check` 的形式**：我把 `-wal`、`-shm` 在主 DB 兩邊都不存在的情況印成 `copy_check=absent_both`。附記與補充六第 6 點 (a) 寫的是「三行 `copy_check=SAME`」。若 CEO 的主 DB 乾淨關閉而沒有 `-wal`，上例的合成回貼就長這樣，CG-2 的核對條件要接受 `absent_both`，否則會誤判。**這點請 TA 確認。**
2. **主控台只有兩類固定文字**：白名單行，以及 STOP／ERROR 固定句。另外有一個 `input()` 提示句（`PROMPT`），是主控台上唯一非白名單、非 STOP 的文字，不含資料。e2e 的整段輸出檢查把它列為固定句。程式沒有印任何說明與結尾文字，這些都放在說明文件。
3. **STOP 與 ERROR 時不產生 `paste-back.txt`、不開記事本**：與風控 RC-166「沒有產生回貼檔」一致。r2 前例會寫一份只有 STOP 句的回貼檔，這裡不寫。
4. **STOP 句英文為我自擬**：每句都是固定 ASCII、不含值或路徑。RC-158c 的英文句是我寫的，中文說明逐字用風控定稿。
5. **殘留掃除**：上次殘留的 `copy` 刪不掉時同樣走 RC-158c STOP；殘留的 `p0`、`p1` 刪不掉則回貼 `cleanup=FAILED`，不 STOP。
6. **重試**：刪除重試 5 次、間隔 0.5 秒、先 `gc.collect()`。
7. **`git status` 範圍**：只檢查 backend 下的 `app`、`tests`、`scripts`、`uv.lock`，包含 untracked。
8. **匯入失敗**：若 harness 或 `app` 匯入失敗（例如沒跑過 `dev-up.bat`），只會印 hook 的固定 ERROR 句，沒有專屬提示。
9. **RC-158a 監聽**：`msvcrt.locking` 只在 win32 才掛，Linux 上沒有實測。
10. **`getattr` 動態取名稱**：RC-158b 掃描抓不到，這是 dev-lead 已揭露的漏洞，我沒改。
11. **本機 Python 3.13**：CI 為 3.12。

**Windows 上沒有實測的部分**：
- `.bat` 本體：`UV_ENV_FILE` 清除、`uv run --no-sync`、`pause`、CRLF 在 Windows 上實際行為。
- `os.startfile` 開記事本。
- Windows 檔案鎖與防毒軟體對 SQLite 檔刪除的影響；重試邏輯只用注入失敗測過。
- cmd 實際出現的系統文字，例如 `^C`、「要終止批次工作嗎」。
- `core.autocrlf=true` 的真實 Windows git 行為：只在 Linux 的臨時 repo 實證。
- 真實主 DB：完全未碰，所以真實 `^TWII` 的 `source`、`market`、深度，以及真實 WAL 狀態，都要等 CEO 第一次執行才會暴露。

# 帳外缺日比對一鍵檔交件

- 審查者：devops-sre
- 日期：2026-11-19
- 轉存：coordinator，逐字轉存 subagent 最終回報

---

## 本次結論

帳外唯讀缺日比對一鍵檔已完成，並已 push 到 `origin/feat/gap-check-oneclick`（base 為 `origin/product/stock-desk` 的 `b36309e`）。Python 3.12 與 3.13 的 ruff check、ruff format、mypy 與全套 pytest 都通過。

- 新增 5 個檔案、零刪改：`gap_check.py`、`gap-check.bat`，以及 3 個測試檔。
- 腳本只用標準函式庫，沒有 import `app` 或 `tests`。不讀 `.env` 值，不寫主 DB 與快取。
- 規格版本：任務指定的是補充八第二版，但 origin/product 上已有「最終版」`work/reviews/2026-11-19-補充八最終版-併入RC233至RC236-tech-architect.md`。我比對了第 5 點：(a)～(h) 只有文字潤飾，實質內容與第二版相同。
- 最終版有實質改動的是 (i)「定期重做」，改為讀 `forecast_input_series.bars_json` 的 session_date。那是日後另一支腳本，這次沒做。
- 沒有需要停下回報的項目：沒遇到會影響讀正式 DB 的方式、對外網站、或 CEO 看到內容的規格缺口。第 4 點的自定解讀和第 3 點的待確認句子請見後文。

## 各部門回報（devops-sre）

### Commit 與 head（40 碼）

| commit | 內容 |
|---|---|
| `9234a151e6911a527e4c9c1bea309a743ca0f8f3` | 腳本與 `.bat` |
| `c387798fa4b39ee2d8fff431ee722ed50ee255e5` | 邏輯測試（日曆、限速、結果代號） |
| `5e175fff948e3d85105f8a26f1a3a76791e5d909` | 流程、輸出途徑、側檔實測測試 |
| `443173b9fa1d041de0e3bb0e3c113ba9f44444b6` | mypy 與 import 排序修正（= head，本機與 origin 一致） |

### 檔案

- `/home/user/AICompany/.claude/worktrees/agent-acec04b09d9a79ee5/apps/stock-desk/backend/scripts/gap_check.py`
- `/home/user/AICompany/.claude/worktrees/agent-acec04b09d9a79ee5/apps/stock-desk/gap-check.bat`
- `/home/user/AICompany/.claude/worktrees/agent-acec04b09d9a79ee5/apps/stock-desk/backend/tests/gap_check_world.py`
- `/home/user/AICompany/.claude/worktrees/agent-acec04b09d9a79ee5/apps/stock-desk/backend/tests/test_gap_check_logic.py`
- `/home/user/AICompany/.claude/worktrees/agent-acec04b09d9a79ee5/apps/stock-desk/backend/tests/test_gap_check_flow.py`

### 流程

1. 提示「關閉 stock-desk 視窗後按 Enter」。
2. 前置檢查。
3. 清掉前次殘留的複本。
4. 用 SQLite backup API 取複本，路徑為 `~/stock-desk-gap-check/<時間>/copy/`。
5. 對複本執行那一句 SQL，然後立刻刪除複本（含側檔，刪不掉就 STOP）。
6. 抓官方日曆。
7. 比對。
8. 每行先驗白名單，再寫 `paste-back.txt`（`utf-8-sig`）、印畫面、開記事本。

這個複本資料夾名稱與既有兩支（`stock-desk-pipeline-acceptance`、`stock-desk-cg2-registration`）不同，並有測試。

### 採用的前置檢查（供 TA 確認）

- **採用**：
  - `STOCK_DESK_DB_PATH` 未設。
  - `.env` 只掃鍵名（用同一條 regex，不讀值，並有 AST 測試）。
  - 主 DB 在預設位置。
  - port 8000 無人監聽。
  - 複本資料夾不在 git 工作樹內。
  - git 可用。
  - `app`、`tests`、`scripts`、`uv.lock` 無未提交變更。
  - HEAD 已在 `origin/product/stock-desk`。
  - HEAD 全碼寫進輸出的 `git_head`。
- **不採用**：
  - 複本逐檔 sha256 比對：改用 backup API。
  - 拒絕防護自我檢查：它屬於 harness，不適用。
  - `uv.lock` 行尾檢查：腳本用 `--no-sync`，與讀 DB 無關。
- 「git 乾淨」與「HEAD 已發佈」兩項是我加的。它們不是讀主 DB 的檢查，是為了讓輸出的 `git_head` 與腳本 hash 對得上 origin 的版本。若 TA 認為多餘，可刪。

### 從前例複製的邏輯（均複製，未 import）

- **來自 `pipeline_acceptance_real.py`**：
  - 三個 hooks、關閉警告、`logging.disable`、固定句機制。
  - `say`（只印 ASCII）。
  - `copy_uri` 的 immutable 判斷。
  - `delete_with_retry`（5 次、間隔 0.5 秒）、`delete_copy`、`sweep_residue`、`copy_left_behind`、`cleanup`。
  - `port_is_listening`、`inside_git_work_tree`、`env_file_sets_db_path`。
  - `preflight` 的檢查順序與 STOP 種類。
  - 外層 `BaseException`／`KeyboardInterrupt` 結構，以及 RC-158c 的「殘留複本不得靜默」。
  - `utf-8-sig` 回貼檔與 `os.startfile`。
- **來自 `cg2_register.py`（git show 讀）**：
  - `run_git` 的環境隔離（移除 `GIT_*`、`--no-optional-locks`、`--no-replace-objects`、關閉 fsmonitor 與 untrackedCache）。
  - `main_db_uri`（我併成 `db_uri`，主 DB 與複本共用）。
  - 用 `source.backup(dest)` 取複本，來源連線為 `mode=ro`。
  - `normalised_source` 的 LF 正規化（來自 `app.forecast.canonical`，複製而非 import）。
- **`.bat`**：由 `pipeline-acceptance.bat` 逐行改出，只換標題、腳本名與註解。

### 對外連線完整清單

- 只有一個主機：`https://www.twse.com.tw`。
- 路徑只有 `/rwd/zh/TAIEX/MI_5MINS_HIST?response=json&date=YYYYMM01`。
- 次數：每次執行最多 17 次（檢查期間 2025-07 到 2026-11 共 17 個月，每月 1 次），不重試。
- 順序：由新到舊。
- 間隔：至少 6 秒；失敗後下一次改為 12 秒。
- 停手：
  - 403／429／503 立即停止，其餘月份列為未檢查。
  - 連續 3 次失敗也停止。
  - 不跟隨轉址，307 視為該月取不到。
- 標頭：只有 `User-Agent: gap-check/1.0 (read-only, low rate)`。
  - 沒有 cookie（opener 沒有 cookie 處理器，並有測試）。
  - 沒有金鑰，也沒有任何使用者資訊。
  - timeout 30 秒，回應上限 1 MiB。
- 另有一次本機 `127.0.0.1:8000` 連線，只用於檢查 port 有沒有人監聽。
- 限速沿用 `work/research/2026-10-16-Phase1資料源探測指令-CEO本機代跑.md` 的守則：
  - 間隔 6 秒。
  - 遇 403／429／503 停手。
  - 不跟隨轉址。
  - 加上 data-engineer 在 2026-11-19 實測的 307 與 5～12 秒恢復。

## 驗證

### 環境與全套結果（head `443173b9`）

- 兩個 venv 都是 scratchpad 下新建的 `venv312`、`venv313`，用 `uv sync --frozen`（PYV 讀自 CI 設定為 3.12）。
- 全套 pytest 輸出檔：
  - `/tmp/claude-0/-home-user-AICompany/3f76d891-50d3-55e1-b39d-925b8a90241a/scratchpad/gapci_312.txt`
  - `/tmp/claude-0/-home-user-AICompany/3f76d891-50d3-55e1-b39d-925b8a90241a/scratchpad/gapci_313.txt`

| 版本 | ruff check | ruff format | mypy app tests | pytest（覆蓋率門檻 90） |
|---|---|---|---|---|
| 3.12.3 | 通過 | 550 個檔案已格式化 | 537 檔無問題 | 12198 passed、2 xfailed，覆蓋率 97.81% |
| 3.13.17 | 通過 | 550 個檔案已格式化 | 537 檔無問題 | 12198 passed、2 xfailed，覆蓋率 97.81% |

- 新增測試共 145 個，3.12 與 3.13 都已單獨跑過並通過。
- 突變檢查：
  - 把「讀完立刻刪複本」拿掉，6 個測試失敗。
  - 把 SQL 加欄位，AST 測試失敗。
  - 讓刪不掉不再 STOP，4 個測試失敗。

### 「不得動」零 diff 證明

`git diff --name-status b36309e HEAD` 只有 5 個 `A`（新增）。對下列路徑的 diff 為 0：

- `apps/stock-desk/backend/app`
- `uv.lock`
- `pipeline_acceptance_real.py`
- `pipeline-acceptance.bat`
- `dev-up.bat`
- `r2-probe.bat`
- 兩份 `.gitattributes`
- `work/`

`origin/product/stock-desk` 在我工作期間前進了（`7fdeb65`，coordinator 新增 work 文件）。我的分支沒有 merge 它，所以直接對 origin tip 比較會看到 work 檔「被刪」，這只是 base 差異，不是我刪的。

### 補充八第 5 點與 S-18a 逐條對應的測試

#### 第 5 點 (c)

- **不 import `app.forecast`、`app.outlook`**：
  - `test_ast_the_script_imports_only_the_standard_library_and_nothing_of_app`
  - `test_an_isolated_import_is_silent_and_loads_nothing_of_app_or_tests`（真實 `python -I` 子行程）
- **SQL 恰一句**：
  - `test_ast_the_sql_is_exactly_one_select_of_trade_date_from_the_cache_for_twii`
  - `test_the_select_names_the_real_cache_columns`：欄名與 `app/data/cache.py` 的 schema 對照，`trade_date`、`symbol` 與實際相同，無差異，且只讀原始碼文字。
  - `test_only_the_one_select_and_the_readonly_pragma_run_and_only_on_main_and_the_copy`：執行期以 trace 確認只有那一句與 `PRAGMA query_only=ON`，連線目標只有主 DB 與複本。
- **輸出不含非日期值**：`test_no_price_label_cash_holding_or_claim_reaches_the_screen_or_the_file`。
  - 合成主 DB 含 OHLCV、持股、現金、`forecast_claim` 表，都放特殊值。
  - 檢查畫面與回貼檔不含這些值，且每個值只能是日期、月份、計數、hash 或固定代號。
- **刪除先於第一行結果**：`test_the_copy_is_deleted_before_the_calendar_is_asked_and_before_the_first_result_line`。
- **注入刪除失敗 → STOP 且無結果行**：
  - `test_an_injected_delete_failure_stops_and_no_result_line_is_printed`（主檔、`-shm`、資料夾三種）
  - `test_an_earlier_copy_that_cannot_be_deleted_stops`
  - `test_a_copy_with_side_files_is_deleted_with_them`
- **e2e 擷取整段 stdout 與 stderr**（真實子行程，真實 hooks）：
  - `test_e2e_a_normal_end_every_line_of_stdout_is_whitelisted_and_stderr_is_empty`
  - `test_e2e_an_error_is_the_fixed_sentence`（例外）
  - `test_e2e_warnings_thread_errors_and_unraisables_never_show_their_text`（警告、執行緒例外、unraisable）
  - `test_e2e_an_interrupt_in_fetching_comparing_or_deleting_is_the_fixed_sentence`（取日曆中、比對中、刪除中的 `KeyboardInterrupt`）
  - `test_e2e_an_interrupt_while_deleting_that_leaves_the_copy_shows_the_copy_stop`
  - `test_e2e_a_stop_through_a_real_isolated_interpreter`
- **`mode=ro` 直連主 DB 路徑**：未實作（依指示）。

#### 第 5 點 (d)、(f)

六種情形在 logic 測試（直接測 `compare`）與 flow 測試（走完整流程）都各有：

- 全部月份取不到 → `calendar_unavailable`：`test_every_month_unobtainable_is_calendar_unavailable`
- 有缺日也有未檢查月份 → `gaps_found`：`test_a_gap_with_unchecked_months_is_gaps_found`
- 只有「快取有、官方無」 → `gaps_found`：`test_only_a_cache_day_the_official_calendar_lacks_is_gaps_found`
- 只有「快取未涵蓋」 → `no_gaps_in_checked_months` 且不是 `gaps_found`：`test_only_days_the_cache_does_not_cover_are_not_gaps`
- 有未檢查月份、無缺口 → `no_gaps_in_checked_months`：`test_unchecked_months_without_a_gap_are_no_gaps_in_checked_months`
- 全檢查、無缺口、快取全涵蓋 → `no_gaps_found`：`test_all_checked_no_gap_and_full_coverage_is_no_gaps_found`

另有：

- `test_decide_takes_the_first_condition_that_holds`：依序套用，第一個成立者勝出。
- `test_the_flow_gives_the_result_code_of_each_ruling_case`：六種情形走完整流程。
- `test_a_cache_day_in_an_unchecked_month_is_not_judged`
- `test_an_empty_cache_period_lists_every_official_day_as_not_covered`
- `test_cache_days_outside_the_period_do_not_widen_the_coverage_or_count`

#### 第 5 點 (g)

腳本每次新開時間戳資料夾、不覆蓋。`test_a_copy_left_by_an_earlier_run_is_swept_and_other_folders_are_left` 驗證舊回貼檔保留。逐字 commit 與附固定說明句是 coordinator 的事，腳本不做。

#### 任務額外要求的測試

- 民國年轉換與月份邊界：
  - `test_roc_year_is_converted_to_the_western_year`（含 ` 92/01/02`、`99/12/31`、閏日、無效日）
  - `test_months_between_crosses_the_year_boundary`
  - `test_the_check_period_is_500_days_before_the_run_date_through_the_day_before`
  - `test_a_month_with_a_row_of_another_month_is_unusable`
- 307 安全頁與壞 JSON 視為未檢查：
  - `test_an_unexpected_body_makes_the_month_unchecked`（16 種壞內容）
  - `test_a_non_200_answer_is_unchecked_even_with_a_good_body`
  - `test_a_network_error_makes_the_month_unchecked_and_is_not_estimated`
- 限速（假時鐘，不真的 sleep）：
  - `test_requests_are_newest_first_one_per_month_and_at_least_six_seconds_apart`
  - `test_the_gap_after_a_failed_request_is_doubled_and_then_returns_to_six`
  - `test_a_block_status_ends_the_fetching_and_the_rest_is_unchecked`
  - `test_three_failures_in_a_row_end_the_fetching_two_do_not`
- HTTP 層（假 opener，不連網）：
  - `test_the_request_carries_only_a_generic_user_agent_and_the_fixed_url`
  - `test_the_opener_follows_no_redirect_and_has_no_cookie_handler`
  - `test_a_307_answer_comes_back_as_a_status_not_a_followed_redirect`
- `.bat` 語法：
  - `test_the_bat_is_a_crlf_launcher_that_clears_uv_env_file_first`
  - `test_the_bat_matches_the_pipeline_acceptance_launcher_except_its_own_lines`
- 前置檢查各一個 STOP 測試；兩個測試檔都有 autouse 的網路守門，任何 socket connect 都會讓測試失敗。

### RC-218～RC-221 逐條對應

- **RC-218（四個結果代號）**：`decide` 依序判定，常數 `RESULT_CODES` 有測試，白名單只允許這四個，`ok` 不存在。`no_gaps_found` 另外要求「快取未涵蓋」為空，這是 TA 第二版的收緊，已實作。
- **RC-219（快取未涵蓋）**：
  - 輸出 `cache_range_start`、`cache_range_end`，只有日期。
  - 涵蓋範圍外的官方日另列 `cache_not_covered_*`，不觸發 `gaps_found`。
- **RC-220（輸出途徑與讀 DB）**：
  - hooks 在最前面（AST 測試 `test_ast_the_hooks_are_the_first_effective_statements`）。
  - 關閉警告與 logging，外層攔 `BaseException`。
  - `say` 與 `render` 都驗白名單，不符則整批不印。
  - 複本先刪再印，刪不掉就 STOP。
  - SQL 只有一句。
  - 授權依據寫在腳本檔頭，指向補充八第 5 點，沒有援引補充六 (b)。
  - `mode=ro` 直連路徑未做。
- **RC-221（每次完整輸出由 coordinator 逐字 commit，不得覆蓋）**：腳本端是每次新資料夾，永不覆蓋，回貼檔與畫面逐行相同。commit 動作在 coordinator。

### backup 來源連線對側檔的實測（合成 DB）

SQLite 3.45.1，3.12 與 3.13 結果相同。測試是 `test_backup_source_*` 與 `test_contrast_*`。

| 情況 | 結果 |
|---|---|
| A：WAL 模式、乾淨關閉、無 `-wal` | 連線用 `mode=ro&immutable=1`。主 DB 目錄的檔案集合、bytes、mtime 全部不變，不產生任何側檔。 |
| A 對照：同一個 DB 用普通 `mode=ro`（不加 immutable） | 會在旁邊新產生 `-wal` 與 `-shm`。這就是 `db_uri` 在無 `-wal` 時加 `immutable=1` 的原因。 |
| B：寫入端還開著，有 `-wal`＋`-shm`，含未 checkpoint 的列 | 檔案集合不變。主檔與 `-wal` 的 bytes 與 mtime 不變。複本讀得到 WAL 內的列。但 `-shm` 的內容 hash 變了（mtime 不變）。 |
| C：只有主檔＋`-wal`、沒有 `-shm`（寫入端異常結束的狀態） | 主檔與 `-wal` 不變，但會在主 DB 旁新產生 `-shm`。 |

- **對 qa 判讀的意義**：只有「乾淨關閉、無 `-wal`」這個常態是完全零接觸。有 `-wal` 時，backup 來源連線仍會動到 `-shm`，C 情形還會新建 `-shm`。`-shm` 是可重建的共享記憶體索引，不含資料。
- 這個結論也說明了為何補充八要求「直連 `mode=ro` 須先有 WAL 實證」。我在這裡給的是證據，不是放行。
- 流程上 port 檢查與「先關視窗」的提示，會使常態落在 A。

## 下一步

### 1. 新增固定句，請送風控定稿

只有 1 句是我新寫的：

- `copy_unreadable`：`STOP: the database copy could not be read. Do not change any setting or file yourself; tell the coordinator.`
  - 觸發時機：複本能產生，但 `price_bars_cache` 表不存在或查詢失敗。

### 2. 全部固定句清單與出處

- **逐字沿用 `pipeline_acceptance_real.py`**（product 上，已核可）：
  - `STOP: STOCK_DESK_DB_PATH is set in the environment.`
  - `STOP: STOCK_DESK_DB_PATH is set in the .env file of the app.`
  - `STOP: stock-desk.db was not found at the default location.`
  - `STOP: something is listening on port 8000; close the stock-desk windows and run again.`
  - `STOP: the work folder would be inside a git work tree.`
  - `STOP: git could not be used on the code folder.`
  - `STOP: the code folder has uncommitted changes.`
  - `STOP: this code version is not on origin/product/stock-desk.`
  - `STOP: the database copy could not be deleted, so the check did not continue. Remove the whole work folder without opening it, do not send it to anyone, and tell the coordinator.`
  - `STOP: the cache copy holds no TWII rows.`
  - `STOP: a TWII row of the cache copy cannot be read.`
  - `ERROR: unexpected failure; no paste-back file was made. Tell the coordinator.`
  - `ERROR: interrupted; no paste-back file was made.`
  - 提示語：`Close the stock-desk backend, scheduler and frontend windows, then press Enter.`
- **逐字沿用 `cg2_register.py`**（來源是 `feat/nm5-cg2-registration`，尚未合併，我無法確認其風控核可狀態，請 TA 確認）：
  - `STOP: the main database could not be read in read-only mode. Do not change any setting or file yourself; tell the coordinator.`

### 3. 自定解讀與待 TA／風控確認

1. **檢查期間月份**：以「期間涵蓋到的每個月」為單位向 TWSE 請求。月內落在期間外的官方日，用日期過濾掉，不納入比對。
2. **未檢查月份的判準**：HTTP 非 200、網路錯誤、非 JSON、`stat` 不是 `OK`、第一欄名稱不是「日期」、`data` 為空、任一日期無效或不在該月，都視為整個月未檢查。
   - 沒有部分採用。
   - 「`data` 為空」也算未檢查。
3. **限速參數**：我挑的是 6 秒基本間隔、失敗後改 12 秒、連續 3 次失敗停手、不重試、由新到舊。
   - 6 秒、停手條件沿用 10-16 守則。
   - 12 秒與連續 3 次是我依 data-engineer 的 5～12 秒觀察自訂。
   - 由新到舊的理由是被擋時最近的月份優先檢查。請 data-engineer 或 TA 確認。
4. **「快取有、官方無」的範圍**：只判已檢查月份內的快取日。未檢查月份內的快取日不判。
5. **`calendar_unavailable` 時**：`cache_not_covered` 等欄位照算，但官方日為空，所以多為 0。
6. **日期清單格式**：一行、逗號分隔、無則 `none`，筆數另列一行。
7. **輸出不含 (e) 以外的行**：沒有 `done_at_utc`、`cleanup`、`db_location`、`port` 等前例有的行。它們不在 (e) 白名單內。
8. **執行日期**：以台北時間（固定 UTC+8，不依賴 tzdata）。
9. **沒有進度提示行**：抓日曆約需 2 到 4 分鐘（17 次、每次至少 6 秒），期間畫面只有提示語、沒有任何輸出，前例也是如此。
   - 是否加一句固定進度句，屬 CEO 看到的內容，我沒加。
   - 建議由 creative-lead 在操作說明中提醒「要等幾分鐘」，或另送一句固定句給風控。
10. **「兩種模式」**：任務說的「兩種模式的完整畫面輸出樣本」，我讀成「畫面」與「回貼檔」。腳本只有一種模式，兩者內容逐行相同。差別是畫面第一行有提示語，回貼檔是 `utf-8-sig`。若你指的是別的兩種模式，請告知。

### 4. 四個結果代號的輸出樣本（合成資料）

全部樣本檔：`/tmp/claude-0/-home-user-AICompany/3f76d891-50d3-55e1-b39d-925b8a90241a/scratchpad/samples_out.txt`。日期清單在檔內為單行長行。以下是畫面（第一行為提示語，回貼檔無）。`git_head` 與 `script_sha256_lf` 為合成值，實際為 CEO 本機值。

**no_gaps_found**
```
Close the stock-desk backend, scheduler and frontend windows, then press Enter.
gap_check version=1
git_head=bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb
script_sha256_lf=08b7b159150d0ef884477e3c98cdd631381f8bb5bc6b19b3f091bf339dedbf15
calendar_source=twse_mi_5mins_hist
period_start=2025-07-07
period_end=2026-11-18
months_checked=2025-07,2025-08,2025-09,2025-10,2025-11,2025-12,2026-01,2026-02,2026-03,2026-04,2026-05,2026-06,2026-07,2026-08,2026-09,2026-10,2026-11
months_unchecked=none
cache_range_start=2025-07-07
cache_range_end=2026-11-18
cache_not_covered_count=0
cache_not_covered_dates=none
official_not_in_cache_count=0
official_not_in_cache_dates=none
cache_not_in_official_count=0
cache_not_in_official_dates=none
result=no_gaps_found
```

**no_gaps_in_checked_months**（2025-12 與 2026-03 未檢查，且快取從 2025-08-01 起，所以 2025-07 有 19 個官方日「快取未涵蓋」）
```
months_checked=2025-07,2025-08,2025-09,2025-10,2025-11,2026-01,2026-02,2026-04,2026-05,2026-06,2026-07,2026-08,2026-09,2026-10,2026-11
months_unchecked=2025-12,2026-03
cache_range_start=2025-08-01
cache_range_end=2026-11-18
cache_not_covered_count=19
cache_not_covered_dates=2025-07-07,2025-07-08,…（共 19 個）
official_not_in_cache_count=0
official_not_in_cache_dates=none
cache_not_in_official_count=0
cache_not_in_official_dates=none
result=no_gaps_in_checked_months
```
（其餘行同上，包含版本行、`git_head`、`script_sha256_lf`、`calendar_source`、`period_*`。）

**gaps_found**
```
months_checked=2025-07,2025-08,2025-10,…,2026-11
months_unchecked=2025-09
cache_range_start=2025-08-01
cache_range_end=2026-11-18
cache_not_covered_count=19
cache_not_covered_dates=…（19 個）
official_not_in_cache_count=2
official_not_in_cache_dates=2026-04-15,2026-04-16
cache_not_in_official_count=1
cache_not_in_official_dates=2026-10-10
result=gaps_found
```

**calendar_unavailable**
```
months_checked=none
months_unchecked=2025-07,2025-08,…,2026-11（17 個月）
cache_range_start=2025-07-07
cache_range_end=2026-11-18
cache_not_covered_count=0
cache_not_covered_dates=none
official_not_in_cache_count=0
official_not_in_cache_dates=none
cache_not_in_official_count=0
cache_not_in_official_dates=none
result=calendar_unavailable
```

### 5. 回貼檔各行的鍵名與意思（供 creative-lead）

固定順序，共 17 行：

| 鍵 | 意思 |
|---|---|
| `gap_check version=1` | 工具版本行 |
| `git_head` | CEO 本機的 HEAD（40 碼） |
| `script_sha256_lf` | 腳本內容 hash（行尾正規化為 LF） |
| `calendar_source` | 官方日曆來源代號，固定 `twse_mi_5mins_hist` |
| `period_start`、`period_end` | 檢查期間：執行日前 500 天到執行日前一日 |
| `months_checked` | 成功取得官方日曆的月份 |
| `months_unchecked` | 取不到的月份（照實列出，不推估） |
| `cache_range_start`、`cache_range_end` | 期間內快取 `^TWII` 的最早與最晚交易日；沒有則 `none` |
| `cache_not_covered_count`、`cache_not_covered_dates` | 官方有、但在快取涵蓋範圍之外的日期（可能含來源缺日；**不算缺日**） |
| `official_not_in_cache_count`、`official_not_in_cache_dates` | 官方有、快取沒有的日期（涵蓋範圍內）。這才是缺日。 |
| `cache_not_in_official_count`、`cache_not_in_official_dates` | 快取有、官方沒有的日期（僅限已檢查月份） |
| `result` | 四個結果代號之一 |

### 6. Windows 上未實測的部分

- `.bat` 本身（cmd.exe 執行、`pause`、`where uv`）。
- `os.startfile` 開記事本。
- 刪除複本時 Windows 檔案鎖的實際行為。
- `Path.as_uri()` 與 SQLite URI 在 Windows 路徑上的表現（測試只在 Linux）。
- `urllib` 在 Windows、公司 proxy 或憑證環境下的連線。
- 真實 TWSE 的回應格式與限流實況：沒有任何連網。日曆解析依據 data-engineer 報告描述的欄位與民國年格式，若實際回應有差異，結果會是該月「未檢查」，不會誤判為缺日。
- 長時間（約 2 到 4 分鐘）執行時的主控台行為。

### 7. 其他提醒

- 第 5 點 (h)、(g)、(a)、(b)：執行時點、coordinator 的 AskUserQuestion、結果 commit、「接線 PR 前已 commit」，都不在腳本內，請 coordinator 與 qa 處理。
- 這支檔案依指示不寫給 CEO 的操作說明。
- 全部測試只用 `tmp_path` 與合成資料，沒有碰 `.env` 值或 `apps/stock-desk/backend/data/*.db`，也沒有執行 `.bat`，也沒有連網。
- 兩個 3.12／3.13 完整輸出已存在 scratchpad（上方路徑）。

# 帳外缺日比對一鍵檔修改交件

- 審查者：devops-sre
- 日期：2026-11-20
- 轉存：coordinator，逐字轉存 subagent 最終回報

---

## 本次結論

補充十第 7 點 (a)(b)(g)、S-1／S-2／S-3、N-6、N-8、限速、RC-273 全部做完，每項一個 commit，已 push 到 `feat/gap-check-oneclick`。
- 新 head：`ec205945da5fa5430a1c0df35bb985985bcf9efe`，與 `origin/feat/gap-check-oneclick` 相同，工作目錄乾淨。
- `git diff --name-status b36309e HEAD` 只有五個 `A`：`gap_check.py`、`gap-check.bat`、`gap_check_world.py`、`test_gap_check_flow.py`、`test_gap_check_logic.py`。`app/`、`uv.lock`、其他一鍵檔零差異。
- 這次沒有改 `gap-check.bat`，也沒有新增測試檔。
- 兩個要先知道的發現，見「各項回報」第 7 項與第 1 項：
  1. 「最多 17 次請求」不成立，檢查期間涵蓋 17 或 18 個月，最壞時間上限要看 18 次。
  2. S-1／S-2／S-3 的逐字比對測試要讀風控報告，而報告目前不在 repo 的 `work/reviews` 裡，CI 會失敗，見待決。

## 各項回報

### commit 清單（由舊到新）

| commit（40 碼） | 內容 |
|---|---|
| `8e6c69b20a9c530ae75c5579664698e2a671c7d2` | feat：第 1 點 (a)，主 DB 一律 immutable，側檔與複本期間改動即 STOP，新增 `db_in_use`（S-1） |
| `3fc97e6d8ee7f95535c177463a76d775cf5f0ae2` | fix：S-3，`db_unreadable` 改名 `copy_failed`，S-2 改為抽出比對 |
| `8525855286dda55c210b41ba70dbda2f18c2ed3b` | refactor：拿掉 `PRAGMA query_only=ON`（第 7 點 (b)） |
| `7e84da7aae57f810f508a3dd4010c7c1c124363a` | fix：N-6，`\d` 全改 `[0-9]`，`render` 加 `isascii` |
| `d2511cbf720b0ffd2de990747f5f1bbf66daf8e7` | fix：N-8，git 乾淨檢查納入 `../gap-check.bat`（第 7 點 (g)） |
| `f83745bef9a91386a84b337ebfb201c4871e6c6d` | fix：限速改 8 秒與 20 秒 |
| `0c7bf424806b8966307f4896334ff487b4701573` | test：RC-273 以假時鐘釘住時間上限算式，並在腳本常數處註明 |
| `ec205945da5fa5430a1c0df35bb985985bcf9efe` | docs：授權依據補第 7 點的守門測試 |

### 第 1 項：主 DB 側檔與複本期間的改動

- **做法**：`make_copy` 先查側檔，再取 `stat`，才開連線。
  - 取複本前，主 DB 旁有 `-wal` 或 `-journal` 就 `RunStop("db_in_use")`。這時還沒有任何連線，也沒有 `copy` 資料夾。
  - 取複本前後各記一次 `(st_size, st_mtime_ns)`，只用 `stat`。
  - backup 完成、兩條連線都關閉後，若簽章不同或出現側檔，就拋 `db_in_use`。
  - 先刪複本再顯示 STOP：既有的 `flow` 的 `finally: delete_copy` 先跑，STOP 才在 `main` 印出。
  - 複本刪不掉時，`delete_copy` 在 `finally` 內拋 `copy_not_deleted`，取代 S-1，只印那一句。
  - 事後 `stat` 本身失敗，視為「有改動」（fail closed）。
- **純 `mode=ro` 的移除**：`db_uri` 現在一律回傳 `mode=ro&immutable=1`。
  - 已刪除的測試：「有 live `-wal` 時純 ro 來源保持 db 與 wal 的 bytes」、「有 `-wal` 無 `-shm` 時」兩支，因為那條路徑不存在了。
  - 對照用的 `test_contrast_a_plain_readonly_connection...` 保留，它是 immutable 的理由。
  - 偏離說明：我連複本的讀取也改成一律 immutable。複本由 backup 產生，連線關閉後不會有有效的側檔，所以不會多出風險。若你要保留複本的條件式分支，需另告知。
- **測試**（在 `test_gap_check_flow.py`）：
  - `test_a_live_wal_writer_stops_the_run_before_any_connection_is_opened`：真實 WAL 寫入端、零連線、所有檔案 bytes 與 mtime 不變、沒有新增 `-shm`。
  - `test_a_wal_or_journal_beside_the_main_database_stops_with_no_connection_and_no_copy[-wal|-journal]`
  - `test_a_change_of_the_main_database_during_the_copy_deletes_the_copy_then_stops[size|mtime_only|wal_appears|journal_appears]`：先刪複本、只印 S-1、沒有結果行、沒抓日曆、沒回貼檔、`say` 之前已刪除。
  - `test_when_the_delete_also_fails_the_copy_stop_is_shown_not_the_changed_file_stop[四種]`
  - `test_a_failed_backup_with_a_changed_main_database_shows_the_changed_file_stop[四種]`（S-3 的 suggested：優先顯示 S-1）
  - `test_a_failed_backup_with_an_unchanged_main_database_is_the_copy_could_not_be_made`
  - `test_the_main_database_is_signed_by_stat_before_and_after_and_never_opened_for_it`
  - `test_the_main_database_uri_is_always_read_only_and_immutable`
- **前提實證**（合成 DB、SQLite 3.45.1、Linux 檔案系統）：

| 情形 | 實測結果 | 對應測試 |
|---|---|---|
| WAL 模式，寫入端 `BEGIN IMMEDIATE` 並 `INSERT` | `-wal` 與 `-shm` 立即出現，主檔 `stat` 完全沒變 | `test_measured_in_wal_mode_a_writer_that_begins_to_write_makes_a_wal_file_appear` |
| WAL 模式，寫入已 commit 但未 checkpoint | 側檔仍在，主檔 `stat` 仍不變 | 同上 |
| WAL 模式，視窗內寫入、commit、關閉 | `-wal` 被 checkpoint 並刪除，主檔 mtime 變；此例大小沒變，只靠 mtime 偵測 | `test_measured_in_wal_mode_a_write_finished_inside_the_window_changes_the_stat` |
| rollback 模式，寫入中 | `-journal` 出現，主檔 `stat` 尚未變 | `test_measured_in_rollback_mode_a_writer_makes_a_journal_and_a_commit_changes_the_stat` |
| rollback 模式，commit 後 | journal 消失，同大小的 UPDATE 只有 mtime 變，大小沒變 | 同上 |

  tech-architect 的前提成立，但要補一句：WAL 模式下 `-wal` 是在寫入端開連線、開始讀寫時就出現，早於「開始寫」。偵測靠的是側檔檢查加 `stat` 比對兩者互補，單靠 `stat` 抓不到進行中的 WAL 寫入。
- **偵測不到的情形**（照實寫出）：
  - 同大小、原地寫入，而且寫完後被人用 `utime` 把 mtime 還原，且沒有側檔：偵測不到。`test_known_limit_a_same_size_write_that_restores_the_mtime_is_not_detected` 把這個限制寫成測試，並確認資料確實變了。這需要刻意呼叫 `utime`，一般寫入不會發生。
  - 時間解析度：我在本機跑 200 次連續 commit，沒有出現兩次相同的 `mtime_ns`（探測腳本，未提交）。這只代表 Linux 這個檔案系統。**Windows NTFS（100ns 單位，實際更新粒度可能較粗）與防毒軟體對 mtime 的影響我沒有測，未在 Windows 實證。**
  - 備援：視窗內「寫入完成且 `-wal` 已被 checkpoint 掉」且 mtime 恰好相同，理論上也偵測不到。
  - 另外，寫入若發生在「第一次側檔檢查之前、`stat` 之後」的極短間隔，會被後面的檢查抓到；發生在 backup 之後則不影響複本。這些都沒有掩飾，也沒有宣稱能偵測所有情形。

### 第 2 項：S-1／S-2／S-3 與出處

- 三句都由 `/tmp/claude-0/-home-user-AICompany/3f76d891-50d3-55e1-b39d-925b8a90241a/scratchpad/gc10/inject_stops.py` 自風控報告抽出寫入。腳本找「項目：S-n」下一行的「定稿全文：」，要求同一項的所有出現都完全相同。
- 出處：`/home/user/AICompany/work/reviews/2026-11-20-補充十修訂版與三句STOP判定RC265至RC274-風控.md`。
  - S-1：第 128～129 行與第 239～240 行，對應 key `db_in_use`。
  - S-2：第 135～136 行與第 242～243 行，對應 `copy_unreadable`，字面不變。
  - S-3：第 147～148 行與第 245～246 行，對應 `copy_failed`。
- `db_unreadable` 已改名為 `copy_failed`，所有引用與測試一併改。
- 逐字比對測試：`test_the_three_stops_are_the_risk_control_sentences_verbatim[S-1-db_in_use | S-2-copy_unreadable | S-3-copy_failed]`。它從同一份報告抽出，用相等比對。
- 另有 `test_the_old_cg2_wording_is_gone_and_the_stop_kinds_are_the_expected_set`。
- 既有的 AST 守門「字串常數不得含 select／delete 等 SQL 字樣」會擋到 S-1（原文有 "delete"）。我改為排除 `FIXED_SENTENCES` 內的固定句，其他字串仍受同一道守門。這是調整守門，不是削弱斷言。

### 第 3 項：PRAGMA

- 常數與執行都已移除。
- 執行期 trace 測試 `test_only_the_one_select_runs_on_the_copy_no_pragma_and_nothing_on_main` 斷言 `statements == [SELECT_SQL]`，沒有任何 PRAGMA，也沒有 `READ_ONLY_PRAGMA` 屬性。
- AST 測試斷言 `execute` 只有 `SELECT_SQL` 一處。

### 第 4 項：N-6

- 白名單、民國日期、`RUN_FOLDER_PATTERN`、`read_trade_dates` 的解析，全部改 `[0-9]`。`render` 每行加 `isascii`。
- 測試：
  - `test_a_value_written_in_other_digits_is_on_no_whitelist_shape[三種文字]`：全形、阿拉伯-印度、天城文，涵蓋全部含數字的白名單形狀。
  - `test_a_roc_date_in_other_digits_is_unreadable[三種]`
  - `test_the_run_folder_pattern_takes_ascii_digits_only[三種]`
  - `test_render_refuses_a_non_ascii_line_even_if_the_whitelist_were_to_pass_it`
  - `test_no_pattern_of_the_script_uses_the_shorthand_digit_class`（AST 與編譯後的樣式都不得含 `\d`）
  - `test_the_trade_date_check_of_the_copy_reads_ascii_digits_only`
  - `test_stop_a_trade_date_that_is_not_a_plain_iso_date` 新增全形與阿拉伯-印度兩個參數。

### 第 5 項：N-8

- `CLEAN_PATHS` 加入 `../gap-check.bat`。
- 測試：
  - `test_stop_when_gap_check_bat_has_uncommitted_changes`（依路徑回報的假 git）
  - `test_a_clean_launcher_does_not_stop_and_the_other_paths_still_do`
  - `test_the_clean_check_names_the_launcher_beside_the_backend_folder`
  - `test_real_git_reports_a_changed_or_untracked_launcher_through_the_clean_paths`：真實 git 在 tmp repo 驗證 pathspec 有效。
- 發現：`git status --porcelain` 的路徑是相對 repo 根，所以輸出是 `gap-check.bat`，不是 `../gap-check.bat`。判斷只看輸出是否為空，不受影響。

### 第 6 項：限速

- 基本間隔 8.0 秒，失敗後 20.0 秒。停手條件不變，請求數不變（由新到舊、不重試）。
- 測試：
  - `test_the_rate_limit_constants_and_the_stop_conditions_are_the_ruled_ones`
  - `test_requests_are_newest_first_one_per_month_and_at_least_eight_seconds_apart`
  - `test_the_gap_after_a_failed_request_is_twenty_seconds_and_then_returns_to_eight`
  - 403／429／503 與連續 3 次失敗的既有測試不變。

### 第 7 項：RC-273 算式與時間（供 CEO 說明文件引用）

**先講發現**：檢查期間是「執行日前 500 天到前一天」，涵蓋 17 或 18 個月。我實測 2024–2029 年的每個執行日，約 61% 是 17 個月、39% 是 18 個月。所以「最多 17 次」只對部分執行日成立。
- 從 2026-11-20 到 2026-12-01 執行是 17 次。
- 2026-12-02 到 2026-12-13 執行是 18 次。
- 2026-12-14 到 2027-01-01 回到 17 次，2027-01-02 到 2027-01-13 又是 18 次。
- 測試 `test_a_check_period_spans_17_or_18_months_so_a_run_asks_17_or_18_times` 釘住這個事實。我沒有改程式的行為，因為你指示停手與次數條件不變。

**日曆段最壞情況**（自按 Enter 後的日曆請求階段；假設每次請求都跑滿 30 秒）：
- 失敗次序要盡量多、但不能連 3 次（否則停手）。形式是「失敗、失敗、成功」循環。每次失敗後的間隔是 20 秒，成功後是 8 秒。
- 17 次：間隔共 16 個。長間隔 `16 − ⌊16/3⌋ = 11` 個（20 秒），短間隔 5 個（8 秒）。
  - 時間 = 17×30 + 11×20 + 5×8 = 510 + 220 + 40 = **770 秒 ≈ 12.8 分鐘**。
- 18 次：間隔 17 個，長間隔 12 個，短間隔 5 個。
  - 時間 = 18×30 + 12×20 + 5×8 = 540 + 240 + 40 = **820 秒 ≈ 13.7 分鐘**。
- 已用假時鐘模擬並釘成測試：兩個數字都吻合；窮舉前 8 次的成敗組合，沒有任何組合超過；連續 3 次失敗即停是 3×30 + 2×20 = 130 秒。
- 風控估的「約 15 分鐘」與這個結果同量級；我算的是在「每次請求至多 30 秒」假設下的上限。

**一般情況（全部成功）**：
- 間隔共 (次數 − 1) × 8 秒，加上每次請求自己的時間 d。
- 17 次是 128 + 17d 秒，18 次是 136 + 18d 秒。
- d 取 1 秒時 17 次是 145 秒（約 2.4 分鐘），d 取 10 秒時是 298 秒（約 5.0 分鐘）。
- 這是算式，不是實測，d 沒有真實量測。

**日曆段之外、程式碼裡有上限的等待**（從按 Enter 到出現結果行還要加）：
- port 檢查 timeout 1 秒。
- 複本刪除：每個檔 5 次、間隔 0.5 秒，每檔最多 2 秒；5 個路徑（主檔、`-wal`、`-shm`、`-journal`、資料夾）共最多 10 秒（有測試）。
- git：4 次呼叫，每次 subprocess timeout 120 秒，理論上限 480 秒。平常小於 1 秒；逾時會變成 `git_unusable` STOP，不會有結果行。
- 若把以上全部算進去，結果路徑的理論上限約 1261 秒（17 次）或 1311 秒（18 次），約 21 至 22 分鐘。這是我自己的加總。CEO 文件要引用哪個數字（只算日曆段約 13.7 分鐘，或含 git 的約 22 分鐘）請決定，禁說句式依風控 RC-274。

**理論上沒有硬上限的條件**：
- `REQUEST_TIMEOUT_SECONDS=30` 是 urllib 對單次 socket 操作（連線、每次 recv）的 timeout，不是整個請求的總時限。慢速滴水式回應（回應大小上限 1 MiB）可讓單次請求遠超過 30 秒。DNS 解析也不在 socket timeout 內。
- `sweep_residue` 對每個殘留資料夾各有最多 10 秒，資料夾數量沒有上限。
- 本機 backup 的時間隨 DB 大小而定，沒有上限。
- 總時限（qa N-7）這次不加，已在腳本常數處註明「沒有硬上限」。

### 第 9 項：授權依據

- 腳本檔頭 docstring 已寫「補充八第 5 點，經補充十第 7 點讀法與收緊」，隨第一個 commit 寫入。
- 測試檔頭同樣註明；`test_the_header_names_supplement_10_point_7_as_part_of_the_authority` 守住它。

### 沒做的事

- 沒有加對象標示行、尾端旗標行、殘留複本已清除說明句、進度提示句；沒改輸出白名單的鍵名與順序；沒改四個結果代號的判定。qa N-7 未辦。
- 沒有 skip、xfail、刪測試或改弱斷言。全套的 2 個 xfailed 是既有的，不是我加的。

## 驗證

**最後一個 commit（`ec20594`）之後重跑**（`ruff`／`mypy` 只在 3.12 跑）：

| 項目 | 3.12 | 3.13 |
|---|---|---|
| 這支工具的測試（flow 與 logic） | 197 passed | 197 passed |
| 全套（`--cov=app --cov-report=term-missing --cov-fail-under=90`） | 12250 passed、2 xfailed、coverage 97.81%，耗時 39:18 | 12250 passed、2 xfailed、coverage 97.81%，耗時 35:06 |

- `ruff check .`：All checks passed。`ruff format --check .`：550 files already formatted。`mypy app tests`：no issues in 537 source files。
- 輸出檔的完整絕對路徑：
  - `/tmp/claude-0/-home-user-AICompany/3f76d891-50d3-55e1-b39d-925b8a90241a/scratchpad/gc10_full312.txt`
  - `/tmp/claude-0/-home-user-AICompany/3f76d891-50d3-55e1-b39d-925b8a90241a/scratchpad/gc10_full313.txt`
  - `/tmp/claude-0/-home-user-AICompany/3f76d891-50d3-55e1-b39d-925b8a90241a/scratchpad/gc10_tool312.txt`
  - `/tmp/claude-0/-home-user-AICompany/3f76d891-50d3-55e1-b39d-925b8a90241a/scratchpad/gc10_tool313.txt`
- 兩個全套同時背景執行，各用獨立的 `COVERAGE_FILE`（避免互相覆蓋）。
- **突變檢查**：十個，每個都有測試失敗，之後已還原（`git status` 乾淨）。腳本：`/tmp/claude-0/-home-user-AICompany/3f76d891-50d3-55e1-b39d-925b8a90241a/scratchpad/gc10/mutate.py`。

| 突變 | 失敗數 | 代表的失敗測試 |
|---|---|---|
| M1 拿掉取複本前的側檔 STOP | 3 | `test_a_wal_or_journal_beside_the_main_database_stops_with_no_connection_and_no_copy` 等 |
| M2 拿掉前後 `stat` 比對 | 5 | `test_a_change_of_the_main_database_during_the_copy_...[size]`、`[mtime_only]` 等 |
| M3 拿掉複本後的側檔檢查 | 4 | `[wal_appears]`、`[journal_appears]` 等 |
| M4 S-1 改一個字元（句尾 `.` 改 `!`） | 1 | `test_the_three_stops_are_the_risk_control_sentences_verbatim[S-1-db_in_use]` |
| M5 日期形狀的 `[0-9]` 改回 `\d` | 4 | `test_a_value_written_in_other_digits_is_on_no_whitelist_shape` |
| M6 民國日期的 `[0-9]` 改回 `\d` | 4 | `test_a_roc_date_in_other_digits_is_unreadable` |
| M7 乾淨檢查拿掉 `.bat` | 3 | `test_stop_when_gap_check_bat_has_uncommitted_changes` 等 |
| M8 `render` 拿掉 `isascii` | 1 | `test_render_refuses_a_non_ascii_line_...` |
| M9 間隔改回 6 秒 | 6 | `test_the_rate_limit_constants_and_...` 等 |
| M10 backup 失敗時不優先 S-1 | 5 | `test_a_failed_backup_with_a_changed_main_database_shows_the_changed_file_stop` 等 |

- **四個結果代號的輸出樣本**：舊腳本（`443173b`）與新腳本在同一組合成 DB 與假日曆下逐行比對，排除必然不同的 `script_sha256_lf` 一行。
  - `calendar_unavailable`、`gaps_found`、`no_gaps_in_checked_months`、`no_gaps_found` 四個都完全相同（各 16 行）。**沒有任何變動。**
  - 比對腳本：`/tmp/claude-0/-home-user-AICompany/3f76d891-50d3-55e1-b39d-925b8a90241a/scratchpad/gc10/samples.py`。
- 鐵則遵守：沒有執行 `gap-check.bat`，沒有對真實 DB 跑 `gap_check.py`，沒有讀 `.env`，沒有碰 `data/*.db`；測試只用 `tmp_path` 與合成 DB，網路守門保留；沒有 force push、rebase、amend；沒有 merge `origin/product/stock-desk`。

## 下一步

**待決與偏離（需 coordinator 或 tech-architect 處理）**
1. **逐字比對測試依賴風控報告，目前 CI 會失敗。**
   - 測試先看環境變數 `GAP_CHECK_RC_REPORT`，否則從測試檔往上找各層的 `work/reviews/2026-11-20-補充十修訂版與三句STOP判定RC265至RC274-風控.md`。
   - 在這個 worktree 能找到，是因為往上走到 `/home/user/AICompany/work/reviews/`。
   - 在乾淨 checkout 上，報告必須已 commit 到該分支可見的 `work/reviews/`，否則測試會失敗。我不能用 skip 處理，也不能動這五個檔以外的檔，所以交給 coordinator：合併前把報告 commit 到產品線，或決定改以其他方式提供。
2. **請求次數是 17 或 18**，不是「最多 17」。請 tech-architect 與 coordinator 確認說明文件與 RC-274 的上限用哪個數字，我建議引用 18 次的 820 秒（13.7 分鐘）。
3. **複本讀取一律 immutable**（上面第 1 項的偏離說明）。
4. **風控 RC-272 要求**：`work/dispatch/2026-11-19-帳外缺日比對操作說明-CEO-草稿.md` 第 218 行要跟著改，那是 creative-lead 的工作，我沒有動。

**仍未在 Windows 實測的項目**
- `.bat` 在 `cmd.exe` 的實際行為、`pause`、`os.startfile`。
- Windows 上 `Path.as_uri()` 加 SQLite URI（含 `immutable=1`）的表現，與 Windows 內建 SQLite 版本是否和 3.45.1 行為一致。
- NTFS 上 `mtime` 的更新粒度，以及防毒軟體與檔案鎖對複本刪除的影響。
- 真實 TWSE 回應與限流，以及真實計時（全為假時鐘模擬）。
- 側檔與 `stat` 比對的實證都在 Linux 檔案系統上做。

**後續**
- 交 qa-reviewer 複審，之後才合併。依 tech-architect 與風控，第一次執行要等補充十第 7 點 append、RC-269 重出，且 STOP 句已定稿（S-1、S-3 現已套用定稿字面）。
- 第一次執行前還需要風控 RC-273（本報告）與 RC-274（CEO 說明文件）。

**相關檔案（絕對路徑）**
- `/home/user/AICompany/.claude/worktrees/agent-acec04b09d9a79ee5/apps/stock-desk/backend/scripts/gap_check.py`
- `/home/user/AICompany/.claude/worktrees/agent-acec04b09d9a79ee5/apps/stock-desk/gap-check.bat`（未改）
- `/home/user/AICompany/.claude/worktrees/agent-acec04b09d9a79ee5/apps/stock-desk/backend/tests/gap_check_world.py`（未改）
- `/home/user/AICompany/.claude/worktrees/agent-acec04b09d9a79ee5/apps/stock-desk/backend/tests/test_gap_check_flow.py`
- `/home/user/AICompany/.claude/worktrees/agent-acec04b09d9a79ee5/apps/stock-desk/backend/tests/test_gap_check_logic.py`

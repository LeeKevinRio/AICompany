# R2 探測一鍵檔交件

- 審查者：data-engineer
- 日期：2026-11-13
- 轉存：coordinator，逐字轉存 subagent 最終回報

---

## 本次結論
一鍵版已完成並推到 `origin/feat/r2-probe-oneclick`。CEO 雙擊 `apps/stock-desk/r2-probe.bat`，按一次 Enter，最後記事本會開出 `paste-back.txt`，全選複製貼回即可。
- head SHA：`26f23915cf796e791a82b1c1b51c0ac646faec7a`（單一 commit，只動 3 個新檔）。
- 分支基底是我開工時 fetch 到的 `origin/product/stock-desk`。之後 product 多了一個 docs commit `8f00695`，我沒有 rebase 也沒有 merge，不影響這 3 個新檔。
- 沒有 merge、沒有 force push、沒有 rebase，只推自己的新分支。

## 各部門回報（data-engineer）
交付三個檔案（絕對路徑）：
- `/home/user/AICompany/.claude/worktrees/agent-a9d19445f1ec725ec/apps/stock-desk/r2-probe.bat`
- `/home/user/AICompany/.claude/worktrees/agent-a9d19445f1ec725ec/apps/stock-desk/backend/scripts/r2_first_run.py`
- `/home/user/AICompany/.claude/worktrees/agent-a9d19445f1ec725ec/apps/stock-desk/backend/tests/test_r2_first_run.py`

行為摘要：
- 流程依你的 a 到 j 實作：英文說明後等 Enter，再依序做 STOP 檢查（環境變數、`.env` 有無該鍵、預設位置有無 DB、8000 埠、工作資料夾是否在 git 工作樹內）。
- 通過後把三個檔複製到 `backup` 並逐檔比對 SHA-256，再複製一份到 `probe`。接著做 N-208 計數，再用 subprocess 跑偵測工具。
- `.env` 只做逐行正則比對有無 `STOCK_DESK_DB_PATH` 這個鍵，不保存、不解析、不印任何內容。
- N-208 的邏輯與輸出行逐字取自原說明檔。測試會從說明檔抽出 `$N208_COUNT = @'` 到 `'@` 之間的原始程式，對 7 種合成 DB 加缺檔各跑一次，斷言輸出與結束碼相同。
- 偵測工具失敗時只寫 `probe_exit=<code>` 與 `probe_stderr_lines=<行數>`。stdout 只留白名單前綴的行，`report_md=`、`report_json=` 一律丟棄。
- 未預期例外只印固定字串並以 1 結束。STOP 情況以 3 結束，並寫出只含標頭與 STOP 那一行的 `paste-back.txt`。
- 沒有 import `app`，沒有 import 偵測工具，沒有讀它產生的 `report.md` / `report.json`，沒有連網（只有一次連 127.0.0.1:8000）。

需要你知道的偏離與取捨：
1. 原說明第 4 步的輸出含中文「未設定」。為了逐字相同，`paste-back.txt` 照原樣寫入 UTF-8。視窗上的回顯則用 ASCII 轉義，會顯示成 `未設定`，避免 cmd 亂碼。只有「規則參數未設定」時才會出現。程式原始碼本身是純 ASCII，用的是 `\u` 轉義。
2. 我新增了原版沒有的 `ERROR: db copy unreadable` 加 `N208_COUNT_RESULT=21`，用於複本不是資料庫時。原版在這種情況會直接丟例外。這樣 `paste-back.txt` 仍會產生。
3. 工作資料夾落在 git 工作樹內時屬於 STOP 情況，仍會在該處寫入只含標頭與 STOP 行的 `paste-back.txt`，因為你要求所有 STOP 都要寫出。
4. 測試用的覆寫參數是 `--backend-dir` 與 `--home`（argparse 說明隱藏），bat 完全不使用。注入點是 `run()` 的參數：`port_check`、`wait`、`opener`、`copier`、`now`。
5. 測試用的偽 backend 目錄裡複製了一份偵測工具，所以偵測工具算出的「正本位置」落在 `tmp_path`，沒有 stat 到真正的 `backend/data/*.db`。
6. 全程沒有讀 `.env`、沒有碰真正的 `data/*.db`，沒有修改 `app/` 與 `n177_n190_backtrack_probe.py`。

## 驗證
CI 等效檢查在 `apps/stock-desk/backend` 實跑：
- `uv sync --frozen`：成功。
- `uv run ruff check .`：All checks passed。
- `uv run ruff format --check .`：498 files already formatted。
- `uv run mypy app tests`：Success, no issues found in 487 source files。
- `uv run pytest --cov=app --cov-report=term-missing --cov-fail-under=90`：10139 passed, 1 skipped, 2 xfailed，總覆蓋率 97.62%（門檻 90%），耗時 14 分 44 秒。
- 全量跑完後我只改了結語一行文字，之後重跑 `tests/test_r2_first_run.py`：32 passed。ruff check 與 format 在該改動後重跑也通過；mypy 與全量 pytest 沒有在改動後重跑，改動內容只是 `OUTRO` 的一行文字。

### bat 全文（commit 內為 LF，`.gitattributes` 會轉成 CRLF）
```
@echo off
setlocal
title stock-desk r2-probe

REM One-click R2 probe: a thin launcher. All logic lives in backend\scripts\r2_first_run.py.
REM The script copies the database and only reads the copy; this launcher never updates the code.
REM Paths derive from the folder of this file (%~dp0), so it can be double-clicked from anywhere.

set "APP_DIR=%~dp0"
set "BACKEND_DIR=%APP_DIR%backend"

where uv >nul 2>nul
if errorlevel 1 (
  echo [MISSING] uv - install from https://docs.astral.sh/uv/getting-started/installation/
  echo After installing, run this script again.
  goto fail
)

cd /d "%BACKEND_DIR%"
if errorlevel 1 (
  echo [ERROR] Cannot find the backend folder next to this file.
  goto fail
)

uv run --no-sync python -I -X utf8 scripts\r2_first_run.py
set "RC=%errorlevel%"
echo.
if not "%RC%"=="0" echo [NOTE] The tool ended with code %RC%. Read the messages above.
pause
exit /b %RC%

:fail
echo.
pause
exit /b 1
```

### 冒煙測試 `paste-back.txt` 全文
做法：臨時目錄偽裝 backend 佈局，合成 DB 放在 `<臨時>/stock-desk/backend/data/stock-desk.db`，含 3 個代號、各 2 批次、無 rule_params。實際執行 `python3 -I -X utf8 scripts/r2_first_run.py --backend-dir ... --home ...`，stdin 餵一個換行。結束碼 0。
```
r2_first_run version=1
copied: stock-desk.db
not present: stock-desk.db-wal
not present: stock-desk.db-shm
stock-desk.db: SAME
stock-desk.db-wal: absent_both
stock-desk.db-shm: absent_both
(a) distinct_symbols: 3
(a2) symbols_with_planned_or_open: 3
(b) batches_per_symbol_distribution:
    2 batches: 3 symbols
(b2) symbols_whose_batch_no_is_not_1..k: 0
(c) batches_by_status:
    planned: 6
    open: 0
    closed: 0
    skipped: 0
    other_status: 0
(d) rule_params_in_force_on (UTC date, same basis as backend): 2026-11-13
    n_targets: 未設定 (NOT_SET; default 5 from app/playbook/models.py:88)
    batches_per_target: 未設定 (NOT_SET; default 3 from app/playbook/models.py:89)
    pending_versions_after_today: 0
(e) distinct_symbols == n_targets: False
(e2) symbols_with_planned_or_open == n_targets: False
(e3) every symbol has batches_per_target batches: False
N208_COUNT_RESULT=0
n177_n190_backtrack_probe version=2
gate_affected_symbols=0
n199_a_rows=0
n199_b_rows=0
n199_c_rows=0
script_sha256_lf=7ab9e89053a765a8abe1957a786cde06235fd1204626ce052a5a78abaa63faad
db_sha256_before=37bf61435513682c3e3cf49cf5b865410081698b0a560c7b3a7da39c83e5fb6d
db_sha256_after=37bf61435513682c3e3cf49cf5b865410081698b0a560c7b3a7da39c83e5fb6d
run_at_utc=2026-11-13T15:38:31.015056+00:00
probe_exit=0
db_location=default
port_8000_listening=no
```
`script_sha256_lf` 等於說明檔記載的第 2 版雜湊 `7ab9e890…3faad`。

### 測試名稱（32 個，`tests/test_r2_first_run.py`）
- 正常流程與輸出：
  - `test_normal_flow_paste_back_is_whitelisted_and_clean`
  - `test_normal_flow_console_output_is_ascii_and_has_no_symbols`
  - `test_folders_are_created_and_report_stays_in_work_folder`
  - `test_original_unchanged_and_no_new_files_in_data_folder`
  - `test_wal_and_shm_files_are_copied_when_present`
  - `test_empty_database_uses_fixed_not_set_text`
- N-208 與原說明檔逐字比對：
  - `test_n208_output_is_identical_to_the_instructions_snippet[populated / no_params / key_absent / unreadable / no_rows / gap_batches / no_table]`（7 個）
  - `test_n208_missing_file_matches_the_snippet`
  - `test_n208_never_writes_to_the_database`
- STOP 情況：
  - `test_stop_when_env_var_is_set`
  - `test_stop_when_env_file_has_the_key`（`.env` 內另放假祕密值，斷言不出現在輸出）
  - `test_env_file_without_the_key_does_not_stop`
  - `test_stop_when_default_db_is_missing`
  - `test_stop_when_port_8000_is_listening`
  - `test_stop_when_copy_differs_from_original`
  - `test_stop_when_presence_differs`
  - `test_stop_when_work_folder_is_inside_a_git_work_tree`
- 偵測工具失敗與穩健性：
  - `test_probe_failure_writes_only_exit_code_and_line_count`
  - `test_probe_stdout_noise_and_stderr_never_reach_the_file`
  - `test_unexpected_exception_prints_fixed_text_and_exits_nonzero`
  - `test_opener_failure_is_reported_without_a_path`
  - `test_port_check_detects_a_listener_on_loopback`
  - `test_cli_main_with_overrides`
- 靜態檢查：
  - `test_script_imports_only_the_standard_library`（AST 檢查，不含 `app`）
  - `test_bat_is_ascii_thin_and_does_not_pull`
  - `test_script_source_is_ascii`

白名單測試的做法：`paste-back.txt` 每一行都要符合正則白名單；不含 3 個種入的代號、`tmp_path` 字串、`/`、`\`、磁碟代號。

## 實測與只能讀碼的項目
**Linux sandbox 實測過：**
- Python 流程全部：複製、雜湊比對、N-208 計數、subprocess 跑偵測工具、白名單過濾、各種 STOP、固定字串例外處理。
- 與原說明檔內嵌程式的逐字比對。
- 以真實 loopback socket 驗證 `port_is_listening`（連得上與連不上兩種）。
- 端到端冒煙（如上）。
- bat 檔為純 ASCII、含 `r2_first_run.py`、不含 `git pull`（測試斷言）。

**無法在此實測，只能靠讀碼：**
- bat 本身在 cmd 的執行：`%~dp0` 推路徑、`where uv`、`cd /d`、`errorlevel` 判斷、`pause`、結束碼傳遞。
- `uv run --no-sync python -I -X utf8 scripts\r2_first_run.py` 在 Windows 上的實際行為。
- `os.startfile` 開記事本。測試只用注入的假 opener，真正呼叫只在 `sys.platform == "win32"` 才會走到。
- Windows 上 `Path.home()` 的位置，以及 `input()` 在雙擊視窗中的行為。
- Windows 上 `paste-back.txt` 的換行：預設文字模式寫入會變 CRLF，記事本應可正常顯示，但未實測。
- 偵測工具在 Windows 上被 subprocess 呼叫，只有 Linux 實測過。
- cmd 視窗對 ASCII 回顯的顯示。
- `-I`（isolated 模式）在 Windows 上下，腳本只靠 `Path(__file__)` 定位 backend，沒有依賴 `sys.path`，讀碼判斷不受影響。

## 下一步
1. qa-reviewer 審查這個分支，並做 Codex 第二意見。需要特別審的有：白名單過濾邏輯、`.env` 只比對鍵名的做法，以及上面列的取捨 1 到 3。
2. 需要有 Windows 的人實測 bat：雙擊、按 Enter、記事本是否跳出、`paste-back.txt` 內容。實測結果回到 coordinator。
3. coordinator 決定是否把 CEO 的操作說明改為「雙擊 `r2-probe.bat`」。這次我沒有動 `work/` 下的文件。
4. 若要更新員工能力或合併進 product，需另走 PR，並由 coordinator 或 tech-architect 處理。我沒有做 merge。

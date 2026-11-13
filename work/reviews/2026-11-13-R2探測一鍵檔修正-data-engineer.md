# R2 探測一鍵檔修正（qa M-1、M-2 與小修）

- 審查者：data-engineer
- 日期：2026-11-13
- 轉存：coordinator，逐字轉存 subagent 最終回報

---

## 本次結論
M-1、M-2 與三項小修都已完成，已在同分支追加一個 commit 並推送（沒有 amend、沒有 rebase、沒有 force push）。新的 head SHA：`35d18d52f8acce617fbf7f3f442316f29cdd6995`（上一個是 `26f23915`）。

- 全套 CI 等效檢查都是在最後一次改動之後才跑的。
- 第一次全套 pytest 發現 mypy 抱怨 `read_text(newline=)`，我中止後修正，再重跑 ruff、format、mypy，然後重跑全套。

## 各部門回報（逐項對應）
所有測試都在 `apps/stock-desk/backend/tests/test_r2_first_run.py`。

**M-1 隱私縱深**
- 偵測工具 stdout 改成整行 fullmatch：
  - `n177_n190_backtrack_probe version=\d+`
  - `gate_affected_symbols=\d+`
  - `n199_[abc]_rows=\d+`
  - `script_sha256_lf=[0-9a-f]{64}`
  - `db_sha256_(before|after)=[0-9a-f]{64}`
  - `run_at_utc=[0-9T:.+Z-]+`
- 不符的行丟棄，並寫一行 `probe_lines_dropped=<行數>`。`report_md=`、`report_json=` 與空白行不計入，所以正常情況是 `probe_lines_dropped=0`。
- 負向測試：`test_probe_lines_are_matched_whole_and_bad_ones_dropped_and_counted`
  - 假 subprocess 回傳 `gate_affected_symbols=2330,2317`、`=ABC`、`n199_a_rows=1 2330`、`script_sha256_lf=/secret/path`、63 位與大寫的雜湊、`run_at_utc=` 後面帶路徑，共 7 行壞行。
  - 斷言這些內容不出現在 `paste-back.txt` 與視窗輸出，且 `probe_lines_dropped=7`。
- 正常與失敗情形的測試：`test_normal_run_reports_zero_dropped_lines`、`test_probe_stdout_noise_and_stderr_never_reach_the_file`（現在斷言 `probe_lines_dropped=1`，`report_*` 不計）。
- N-208 的 `n_targets`、`batches_per_target`：值若不是 `type(v) is int`（bool 不算），印固定的 `NON_INTEGER`。
  - 比較用不等於任何數字的哨兵物件，所以 `(e)`、`(e2)`、`(e3)` 一律印 False，不丟例外、不印原值。
  - 順帶處理：payload 是 JSON 但不是 dict（例如 list）時，印 `payload: UNREADABLE`。原版此情況會丟例外。
- 測試：`test_non_integer_rule_params_print_marker_and_never_the_value`，涵蓋字串、含代號樣字串、list、float、bool、巢狀 dict、含路徑字串、非 dict 的 payload（6 組參數）。
- 逐字比對測試維持在整數、未設定、KEY_ABSENT、UNREADABLE 等原有情形，共 7 種合成 DB 加缺檔，都通過。

**M-2 測試不再依賴 work/ 文件**
- 原說明檔 `$N208_COUNT = @'` 到 `'@` 之間的程式，逐字存成 `/home/user/AICompany/.claude/worktrees/agent-a9d19445f1ec725ec/apps/stock-desk/backend/tests/fixtures/n208_count_original.py.txt`。
  - 本體沒有加任何字元，檔尾無換行（2944 字元）。
  - 副檔名是 `.txt`。測試讀檔後自己補一個換行再餵給 stdin。
- 來源檔名與抽取日期（2026-11-13）記在測試檔頭註解，以及 `tests/fixtures/README.md` 新增的一節。
- 測試改讀 fixture，`test_n208_output_is_identical_to_the_instructions_snippet[...]` 共 7 組與 `test_n208_missing_file_matches_the_snippet`。

**一行修正**
- `.env` 改用 `encoding="utf-8-sig"`。測試：`test_env_file_with_bom_and_key_on_first_line_stops`。
- 環境變數判斷改成 `ENV_VAR in env`，空字串也 STOP。測試：`test_env_var_set_to_empty_string_still_stops`。

**取捨 3 特例**
- 工作資料夾落在 git 工作樹內時，不建資料夾、不寫檔，只在視窗印固定 STOP 行，並以 3 結束。
- 我把這個規則放在 `stop()` 內，所以**任何一種 STOP** 只要工作資料夾在 git 工作樹內，都不會寫檔。這比你要求的略廣，原因是否則「無 DB」等 STOP 一樣會在 repo 內建檔。
- 測試：`test_stop_inside_git_work_tree_creates_nothing`（前後樹狀比對，無任何新增檔案或資料夾）、`test_stop_in_git_work_tree_for_any_stop_writes_nothing`。

**INTRO**
- 補了兩行英文：若 backend 或 scheduler 以 NSSM 或 Windows Task Scheduler 常駐，先不要繼續，改告訴 coordinator。
- 測試：`test_intro_mentions_supervisors_and_three_windows`。

**未做（照你的指示）**：UNC 路徑改 `pushd`、Ctrl+C 的 traceback、補程序檢查。

## 驗證（最後一次改動之後的實跑結果）
- `uv run ruff check .`：All checks passed。
- `uv run ruff format --check .`：498 files already formatted。
- `uv run mypy app tests`：Success, no issues found in 487 source files。
- `uv run pytest --cov=app --cov-report=term-missing --cov-fail-under=90`：**10151 passed, 1 skipped, 2 xfailed**，總覆蓋率 **97.62%**（門檻 90%），耗時 14 分 17 秒。上一版是 10139 passed，多出的 12 個是新增測試。
- `tests/test_r2_first_run.py` 單獨跑：44 passed。
- 冒煙：與上一版相同做法（臨時目錄偽裝 backend 佈局、合成 DB、stdin 餵換行），結束碼 0。視窗第 8 行已顯示新增的 NSSM 提示。`paste-back.txt` 全文如下，其中 `probe_lines_dropped=0`。

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
db_sha256_before=22dd67e998cb6c77bb7368f0d09283981a9c17985d1102981def2d98b0576fc8
db_sha256_after=22dd67e998cb6c77bb7368f0d09283981a9c17985d1102981def2d98b0576fc8
run_at_utc=2026-11-13T15:51:43.352268+00:00
probe_lines_dropped=0
probe_exit=0
db_location=default
port_8000_listening=no
```

仍未變的限制：bat、`os.startfile`、Windows 上的 `input()` 與換行行為無法在 Linux 實測，只有讀碼。

## 下一步
1. qa-reviewer 對 `35d18d52` 做複審。重點是整行 fullmatch 白名單，以及 `stop()` 在 git 工作樹內不寫檔的範圍（比要求略廣）。
2. 說明文件需要補：`N208_COUNT_RESULT=21` 代表複本不是資料庫；`NON_INTEGER` 與 `probe_lines_dropped` 這兩個新行的意義。
3. 合併前由 devops-sre 在 merge commit 上重跑完整 CI；Windows 實機雙擊一次仍是必要的。
4. 凍結後待辦（你已登錄）：UNC 路徑改 `pushd`、Ctrl+C 的 traceback、補程序檢查。

# gap_check .env 鍵名 regex 修正提交交件

- 審查者：devops-sre
- 日期：2026-11-21
- 轉存：coordinator，逐字轉存 subagent 最終回報

---

## 補件：gap_check 的 .env 鍵名 regex 修正（已提交並推送）

**本次結論**：已完成。fast-forward 推送 `1faae4a..243596c`，沒有 rebase、amend 或 force。新 head 完整 SHA 是 `243596c45616469c35b4b9b7585480cebf614c3b`。推送前先 fetch，遠端 head 確認是 `1faae4a73636d7d276d3748da10ff2ee9e3311f6`。commit 訊息是 `fix: gap_check 的 .env 鍵名比對涵蓋 export 寫法與大小寫`，含你指定的兩行 trailer。

**變更**
- `apps/stock-desk/backend/scripts/gap_check.py` 第 90 行改成 `re.compile(r"^\s*(?:export\s+)?STOCK_DESK_DB_PATH\s*=", re.IGNORECASE)`。
- `apps/stock-desk/backend/tests/test_gap_check_logic.py` 在檔尾新增測試，檔案原有內容未動。
- 補了 3 個例子。正例有 `"export\tSTOCK_DESK_DB_PATH=/x"` 與 `"EXPORT STOCK_DESK_DB_PATH="`，反例有 `"  # export STOCK_DESK_DB_PATH=/x"`。
- BOM 正例改成跳脫寫法 `"﻿STOCK_DESK_DB_PATH=/x"`。我上一版在原始碼裡放了字面 BOM 字元，這次已移除，我新增的行都是純 ASCII。
- 正例共 9 個，反例共 8 個，另有一個斷言驗證 pattern 字面與 `IGNORECASE`。

**驗證**
- 相對 `1faae4a…` 的 `--name-status` 只有兩項：`M apps/stock-desk/backend/scripts/gap_check.py` 與 `M apps/stock-desk/backend/tests/test_gap_check_logic.py`。
- `gap_check.py` 的 `-U0` diff 只有一個 hunk，`@@ -90 +90 @@`。STOCK_DESK_DB_PATH 的 STOP 字面與 `env_file_sets_db_path` 函式本體都在 hunk 之外，零差異。
- 測試檔的 `-U0` diff 只有一個 hunk，`@@ -701,0 +702,53 @@`，純新增，沒有任何刪除行。所以 `test_ast_the_env_file_is_only_searched_for_the_key_never_read_for_values` 零差異。
- `tests/fixtures` 對 `1faae4a…` 的 diff 為空，輸出 0 位元組。
- 退役守門 `git grep -nP 'cg2_register(?!s)|cg2-register|cg2-preflight|verify_cg2_instruction' HEAD -- apps/stock-desk`：零命中。
- ruff check：All checks passed。ruff format --check：550 files already formatted。mypy app tests：no issues found in 537 source files。
- `pytest tests/test_gap_check_flow.py tests/test_gap_check_logic.py`：221 passed（修正前是 203，新增 18 個）。
- 新 pattern，供 qa 與 `cc9e302` 的 `claims._ENV_FILE_KEY` 人工比對，我是用 `importlib` 載入腳本後印出：
  - `.pattern` = `'^\\s*(?:export\\s+)?STOCK_DESK_DB_PATH\\s*='`，即 `^\s*(?:export\s+)?STOCK_DESK_DB_PATH\s*=`。
  - `.flags` = `34`，也就是 `re.UNICODE`（32）加 `re.IGNORECASE`（2）。

**回滾方式**：`git revert 243596c`，用新 commit 退回，不改寫歷史。

**沒有查證的事**
- 沒有讀 `cc9e302` 的 `claims._ENV_FILE_KEY`，上面是只列出我這端的值，等 qa 比對。
- 沒有送 qa 與 Codex，那一步由你協調。
- 只跑 gap_check 兩個測試檔，全套測試留給 RC-399 (d) 的重跑。
- 相等斷言依裁示留待 gap-check 合併後另案，我沒有補。
- 沒有讀 `.env*`、沒碰 `backend/data/`、沒執行 `.bat`。測試都用 `tmp_path`。

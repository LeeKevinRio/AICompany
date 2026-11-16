# 真實資料一鍵檔 qa 修正交件

- 審查者：devops-sre
- 日期：2026-11-16
- 轉存：coordinator，逐字轉存 subagent 最終回報

---

## 本次結論

qa 的 2 項 BLOCKING（B-1、B-2）與 S-13e、logging、port 檢查測試都已在同一分支修完，已 fast-forward push（6c2253f..ba043fd），並用 `git ls-remote` 確認遠端 head 等於本地 head。這次沒有動說明文件，也沒有動 `app/`、harness、`dirdef_helpers`、`outlook_helpers`、`uv.lock` 與根目錄 `.gitattributes`（零 diff，已驗證）。

**新 head（40 碼）：`ba043fdf62438c00bbaefb0937ec1730686742a9`**

- 本批只有一個修正 commit：`ba043fdf62438c00bbaefb0937ec1730686742a9`，`fix:` 開頭。
- 此外，為取得 qa 審查報告與 ADR-0030 補充六附記三，merge 了一次 `origin/product/stock-desk`：`9ddc45dae010ca4bed430165d696c63d06840672`。

## 各部門回報

**B-1（`.bat`）**
- `where uv >/dev/null 2>nul` 已改成 `>nul 2>nul`。
- 我把整支 `.bat` 逐行與 `r2-probe.bat` 做 diff，除了標題、REM 註解、`set "UV_ENV_FILE="` 與執行指令那一行，其餘都相同，沒有其他非 cmd 語法。
- 新測試 `test_the_bat_has_no_non_cmd_redirect_and_matches_the_r2_launcher`：
  - 斷言非 REM 行不得含 `/dev/null`。
  - 斷言 `where uv >nul 2>nul` 存在。
  - 斷言 `.bat` 的所有非 REM 指令行，除了本工具自己的四行，都必須是 `r2-probe.bat` 的指令行。

**B-2（複本刪除失敗不得靜默）**
- 最後一次清理之後，只要複本資料夾還在，就印出 `copy_not_deleted` 的固定 STOP 句，並回結束碼 3。
- 原本要印的 STOP 或 ERROR 句保留，先印，`copy_not_deleted` 句接在後面。如果流程本來就已經拋出並印了 `copy_not_deleted`，不會重複印。
- 畫面上每一行仍然 fullmatch 固定句。
- 新測試（`tests/test_pipeline_acceptance_real_flow.py`）：
  - `test_b2_copy_changed_and_the_copy_cannot_be_deleted_shows_the_copy_stop`
  - `test_b2_guard_failed_and_the_copy_cannot_be_deleted_shows_the_copy_stop`
  - `test_b2_an_interrupt_or_error_before_the_reader_and_a_stuck_copy_shows_the_copy_stop`，參數化為 `KeyboardInterrupt`、`RuntimeError`，位置在 `copy_db_files` 之後、reader 之前。
  - `test_b2_the_copy_stop_is_shown_once_when_the_flow_already_raised_it`
  - 以上測試都斷言：harness 沒被呼叫、`assert_screen_is_closed` 成立、輸出與結束碼與上述一致。

**S-13e**
- `test_s13e_a_main_database_with_only_the_db_file_gives_same_then_absent_twice`：回貼的 `copy_check` 三行依序為 `SAME`、`absent_both`、`absent_both`。
- `-wal`、`-shm` 都存在時三行皆 `SAME`，由既有的 `test_e2e_a_wal_main_database_is_copied_read_and_deleted` 涵蓋。
- 主 DB 缺 `.db` 時，在 `copy_check` 之前就 STOP，由 `test_stop_no_db` 涵蓋。
- 白名單樣式只接受 `SAME|absent_both`，由 `test_whitelist_shape[copy_check]` 涵蓋。

**logging**
- 在 hooks 之後、任何 `app` import 之前加 `logging.disable(logging.CRITICAL)`。AST 測試 `test_ast_the_hooks_are_the_first_effective_statements` 已更新為 5 個 hook 敘述，並要求 `import logging` 在 hooks 之前。
- `tests/pipeline_real_loader.py` 現在也保存並還原 `logging.disable` 的狀態。
- 新測試：
  - `test_logging_is_disabled_and_nothing_a_logger_says_reaches_the_screen`：真實 `python -I` 子行程載入腳本後，觸發 `DISK_DIFFERS_WARNING` 與其他 logger 的 warning、error、critical；結束碼 0，stdout 與 stderr 皆為空。
  - `test_the_flow_with_a_logger_warning_keeps_every_screen_line_fixed`：流程中觸發 logger warning，stdout 每行都 fullmatch 白名單，stderr 為空。
  - `test_the_loader_leaves_logging_enabled_in_the_test_process`：確認 loader 還原了 logging 狀態。

**port 檢查**
- 兩個測試只用真的 `port_is_listening`，只換掉 `socket.create_connection`，不改行為：
  - `test_the_real_port_check_returns_false_when_the_connect_fails`：替身拋 `OSError` 回 `False`。
  - `test_the_real_port_check_returns_true_when_it_connects_and_only_to_loopback`：連得上回 `True`。
  - 兩個都斷言連線位址只有 `("127.0.0.1", 8000)`。

## 驗證

- **全套測試**：`uv run pytest --cov=app --cov-fail-under=90`，**11989 passed、2 xfailed**，覆蓋率 **97.80%**（22642 行、miss 497），耗時 30 分 28 秒。比上次多 12 個測試。
- **`ruff check`**：通過。**`ruff format`** 已套用。**`mypy app tests scripts/pipeline_acceptance_real.py`**：Success，534 source files。
- **反向驗證**（暫時改壞、確認測試擋下，之後已用 `cmp` 還原腳本、用 `sed` 還原 `.bat`）：
  - 把 B-2 的最後檢查改成 `if False:`：`-k b2_` 的 5 個測試中 **4 個失敗**，只有「流程已拋出就不重複印」那個仍通過，這符合預期。
  - 拿掉 `logging.disable`：2 個測試失敗，一個是 logging 子行程測試，一個是 hooks 的 AST 測試。
  - 把 `.bat` 改回 `>/dev/null`：新的 bat 測試失敗。
- **「不得動」清單零 diff**：`git diff --stat origin/product/stock-desk...HEAD` 針對 `app/`、harness、`dirdef_helpers`、`outlook_helpers`、`uv.lock`、根目錄 `.gitattributes`，輸出為空。
- **push**：`git push origin HEAD:feat/nm5-pipeline-acceptance-oneclick` 輸出 `6c2253f..ba043fd`，`git ls-remote` 回 `ba043fdf62438c00bbaefb0937ec1730686742a9`。

## 下一步

1. **qa-reviewer**：請在新 head `ba043fd` 重審 B-1、B-2，並確認 S-13e、logging、port 三項補測。
2. **風控**：說明文件沒動，等風控審完我自擬的字句。有要改的字再傳給我。
3. **已知限制**：
   - `copy_not_deleted` 的最後檢查只看複本資料夾是否還在，不另外列舉資料夾內是哪一檔。
   - 在原本 STOP 或 ERROR 句之後再補印一句，畫面上最多兩行固定句。
   - Windows 上沒實測的部分與上次回報相同（`.bat` 本體、`os.startfile`、檔案鎖與防毒、cmd 系統文字、真實 Windows git 的 `autocrlf`、真實主 DB）。

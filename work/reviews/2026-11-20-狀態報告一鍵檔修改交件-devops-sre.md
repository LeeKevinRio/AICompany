# 狀態報告一鍵檔修改交件（E2、N-1、N-3、N-5、N-6、E3、RC-310、RC-318）

- 審查者：devops-sre
- 日期：2026-11-20
- 轉存：coordinator，逐字轉存 subagent 最終回報

---

## 本次結論
修改單 7 項加追加的 RC-318 都改完並推到同一支分支。

- 新 head：`d0bd41589453d5b8704e07bafb80007a2311155a`，以一般 push 推上（`9f6fd27..d0bd415`），沒有 amend、rebase 或 force。
- 全套兩個版本都綠，工具自己的測試共 103 個。
- `app/` 差異為 0。
- 沒有任何一項碰到九句固定句，一個字都沒動。
- 沒有「這次不做」的項目。

歸屬標記：你訊息裡寫的是 `Claude Fable 5.2`，但我環境指定的是 `Claude Sonnet 5.5`，所以 commit 的 Co-Authored-By 用 Sonnet 5.5，Claude-Session 行照舊。若要改，請你另行處理，我不 rewrite 歷史。

## 各項回報

檔案路徑都在 `/home/user/AICompany/.claude/worktrees/agent-ab5f1bf75d430b1de/apps/stock-desk/` 下。以下是 6 個 commit，由舊到新：

| commit | 內容 |
|---|---|
| `19ab053` | E2：`status` 成功而 `verify` 結束碼 3、4 時，工具結束碼改為 3 |
| `b75d087` | N-3：失敗清理只移除本次建立的資料夾 |
| `119821f` | RC-310：`.bat` 找不到 `uv` 的那行改成定稿句 |
| `2ce8f90` | 其餘測試：E2、N-1、N-3、N-5、N-6、E3、RC-310 |
| `71142cd` | RC-318：`.bat` 加印定稿句 |
| `d0bd415` | 差異測試更新與 RC-318 位元組測試 |

1. **E2**（`backend/scripts/forecast_status.py`）
   - 在 `flow` 加入 `stopped`，結尾改為 `return EXIT_STOP if stopped else EXIT_DONE`。檔頭的情形說明補一行。
   - 其他組合不動：`verify` 結束碼 1 仍回 0，STOP 3，ERROR 1，中斷 2。
   - 測試 `test_verify_exit_3_or_4_keeps_part_one_and_the_separator_then_the_stop_sentence[3]` 與 `[4]` 改為斷言結束碼 3。
   - 突變（把回傳改回 `EXIT_DONE`）後這兩個測試失敗。
2. **N-1**（`backend/tests/test_forecast_status_flow.py`）
   - 舊測試是恆真的，已刪除。
   - 新測試 `test_every_read_connection_refuses_a_write_while_it_is_open`：包住 `ForecastStore._read`，在連線開啟期間嘗試 `CREATE TABLE`。斷言每次都拋 `OperationalError` 且訊息含 `readonly`，事後資料庫裡沒有該表。
   - 另加對照測試 `test_the_write_probe_has_teeth_on_a_connection_that_is_not_query_only`：一般連線寫得進去，`query_only` 連線寫不進去，證明探針會失敗。
3. **N-3**（`scripts/forecast_status.py` 的 `State.created_parents`、`save`、`cleanup`）
   - `save` 在建資料夾前，記下 `wanted` 往上、尚不存在的資料夾。
   - `cleanup` 只 `rmdir` 本次執行自己的資料夾與這些「本次建立的上層」。原本就存在的上層（包括空的）一律保留，任何非本次建立的檔案或資料夾都不動。
   - 新測試：
     - `test_n3_a_failed_run_removes_only_what_it_created`（上層是空的、上層含舊執行，各搭配改名失敗與寫檔失敗，共 4 組）：上層與舊檔仍在。
     - `test_n3_a_failed_run_removes_every_folder_it_made_above_its_own`：多層新建的上層全部移除。
     - `test_n3_a_folder_that_existed_above_the_root_is_never_removed`：`home` 內原有 `mine.txt` 保留。
   - 突變（讓既有上層也被移除）後相關測試失敗。
4. **N-5**
   - 新測試 `test_n5_the_screen_equals_two_real_python_m_report_runs_word_for_word`。
   - 真實跑一次工具子行程，再跑一次 `python -X utf8 -m app.forecast.report status --db …`，逐字比對（兩段 stdout 加分隔句）。
   - `verify` 段限制：合成 ledger 的登記表需要先發佈，所以用 `runpy.run_module('app.forecast.report', run_name='__main__')` 在 driver 內執行，等同 `-m` 啟動，但不是字面的 `python -m` 命令列。
5. **N-6**
   - 刪掉裝飾性的 `"bullish" in forbidden | set(LABEL_WORDS)`，改成斷言資料庫裡確實有 bullish、bearish 或 range 標籤。
   - e2e 的殘留檢查改為 `list(home.rglob("*")) == []`。
6. **E3**
   - 新測試 `test_e3_output_goes_only_through_sys_stdout_write_and_the_bat_has_no_chcp`。
   - 斷言 `sys.stdout` 的屬性只有 `write` 與 `flush`（`flush` 是 `say` 需要的，沒有 `buffer` 或 `reconfigure`），沒有 `print`。
   - 斷言 `.bat` 不含 `chcp`。
7. **RC-310**
   - 用 `scratchpad/fstatus/fill_bat.py`，從 `2026-11-20-補充十一E1確認與缺少uv提示定稿RC305至RC312-風控.md` 取字套入 `.bat` 第 18 行；第 19 行 `Tell the coordinator.` 不變。
   - 測試 `test_rc310_the_missing_uv_line_is_the_risk_control_sentence_verbatim` 從同一份報告抽字比對，並檢查 `.bat` 內沒有 `install from` 或 `http`。
8. **RC-318**
   - 用 `scratchpad/fstatus/fill_bat2.py`，從 `2026-11-20-兩份CEO文件判定RC313至RC324-風控.md` 取字，加在 `[ERROR]` 行之下（`.bat` 第 26 行）。
   - 測試 `test_rc318_the_backend_error_line_is_followed_by_the_risk_control_sentence` 從報告抽字比對，並斷言該行位元組含 `;`、不含 `& | < > ^ % ! ( ) "` 和反斜線（cmd 的 `echo` 會原樣印出分號）。
   - 這句在真實 cmd 上的顯示我沒有實測，只能靠位元組檢查。
   - 差異測試改用 `difflib` 比對：與前例相比，被換掉或移除的行共 7 行，新版相對多 8 行，總行數多 1。
     - 1 行 title；
     - 3 行 REM；
     - RC-310 與原「After installing」2 行；
     - RC-318 新增 1 行（相對前例是新增，不屬於被換掉的 7 行）；
     - 指令 1 行。
   - 所有 `echo` 內容的 `own` 集合同步更新。

**九句固定句逐字核對**
- 腳本裡九個常數與兩份風控報告抽出的文字比對，全部 True。
- 九個比對測試也都過，包含 hook 內的 ERROR 字面。
- 這一輪 diff 沒有動到這九個常數。

## `.bat` 的 `[MISSING]`、`[ERROR]`、`[NOTE]` 各行（逐字，CRLF，行號為 `.bat` 內行號）
- 第 18 行：`  echo [MISSING] uv was not found. Do not install or update anything yourself.`
- 第 19 行：`  echo Tell the coordinator.`
- 第 25 行：`  echo [ERROR] Cannot find the backend folder next to this file.`
- 第 26 行：`  echo Do not move or change any file or folder yourself; tell the coordinator.`
- 第 33 行：`if not "%RC%"=="0" echo [NOTE] The tool ended with code %RC%. Read the messages above.`

## 驗證
**靜態檢查（最後一個 commit 後）**：`ruff check .`、`ruff format --check .`（549 個檔案）、`mypy app tests`（536 個來源檔）全過。

**全套測試（最後一個 commit 後，各自專用 venv，`--cov=app --cov-fail-under=90`）**
- Python 3.12：12170 passed、2 xfailed、0 failed、1 warning，61 分 36 秒，coverage 97.81%，結束碼 0。輸出 `/tmp/claude-0/-home-user-AICompany/3f76d891-50d3-55e1-b39d-925b8a90241a/scratchpad/fstatus2-full-312.txt`。
- Python 3.13：12170 passed、2 xfailed、0 failed、34 warnings，58 分 11 秒，coverage 97.81%，結束碼 0。輸出 `/tmp/claude-0/-home-user-AICompany/3f76d891-50d3-55e1-b39d-925b8a90241a/scratchpad/fstatus2-full-313.txt`。
- 2 個 xfailed 是既有測試，不是我加的。
- 全套已涵蓋工具自己的測試（103 個）。工具測試單獨在最後 commit 後的重跑，只做了 3.12 的 `-k "bat or rc310 or rc318"` 子集（18 passed）。
- 這一輪 E2 與 N-3 各做了一次突變：E2 使 2 個測試失敗，N-3 使 2 個失敗，之後都還原。

**其他數字**
- `git diff 9f6fd27..HEAD --stat`：`scripts/forecast_status.py` 23 行異動，`tests/test_forecast_status_flow.py` 247 行異動，`forecast-status.bat` 3 行異動；共 3 個檔案，233 insertions、40 deletions。沒有新增或刪除檔案。
- `app/` 差異為 0：`git diff 38b4855..HEAD --stat -- apps/stock-desk/backend/app` 為空；`git rev-parse HEAD:apps/stock-desk/backend/app` 為 `07b5e1fd95fa933d969ba4f5adecb3c982be0a62`，等於產品線目前的值。
- 過程中我曾中止第一次的全套重跑（因為追加了 RC-318 會改動 `.bat`），以上結果都是最後 commit 之後重跑的完整結果。

**沒驗證到的**
- 沒有 Windows 實測：`.bat`、`uv run`、記事本、cmd 對該分號句的實際顯示、主控台中文顯示。
- `python -m` 對照中 `verify` 段是以 `runpy` 的 `-m` 等價方式啟動（原因見 N-5 一節）。

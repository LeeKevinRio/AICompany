# R2 探測一鍵檔修正複審

- 審查者：qa-reviewer
- 日期：2026-11-13
- 轉存：coordinator，逐字轉存 subagent 最終回報

---

## 本次結論
**程式碼審查結論：PASS，`BLOCKING_ISSUES=false`。**
- 審查範圍：`git diff 26f23915...origin/feat/r2-probe-oneclick`，新 head `35d18d52`，4 個檔，沒有超出範圍。
- 六項都已解決，沒有新的洩漏路徑、寫入正本路徑或會卡住 CEO 的行為。
- `codex --version` 回 `command not found`，所以是**單家審查，沒有 Codex 第二意見**。
- 測試數字未經我重現。合併前須由 devops-sre 在 merge commit 上重跑完整 CI。

## 各部門回報（逐項判定）
1. **M-1：已解決。**
   - 偵測工具輸出改為整行 `fullmatch`（`r2_first_run.py` 的 `PROBE_LINE_PATTERNS`）：版本、計數 `\d+`、sha256 `[0-9a-f]{64}`、時間 `[0-9T:.+Z-]+`。
   - `probe_lines_dropped` 的規則：空行與 `report_md=`／`report_json=` 不計；其他不符合的行只計數、不寫內容。
   - 負向測試（`BAD_PROBE_STDOUT`）真能抓到洩漏。它放了 `gate_affected_symbols=2330,2317`、`gate_affected_symbols=ABC`、`n199_a_rows=1 2330`、`script_sha256_lf=/secret/path`、63 位與大寫的 sha256、`run_at_utc=… C:\Users\x`。測試斷言這 7 行全被丟、`probe_lines_dropped=7`，只留 3 行合法行，且檔案與視窗都不含 `2330`、`secret`、`Users`、`C:`。我數過：7 行不合法加 3 行合法加 2 行 `report_*`，吻合。若改回前綴比對，此測試必失敗。
   - `n_targets`、`batches_per_target` 改走 `_param_line`：`type(value) is not int` 就印 `NON_INTEGER`，並回傳永不相等的 `_NO_MATCH`。所以 `(e)`、`(e2)`、`(e3)` 為 False，不丟例外，也不印原值。`bool` 被當成非整數，合理。
   - 參數化測試涵蓋字串、陣列、浮點、布林、巢狀、整個 payload 是陣列，並斷言不出現 `2330`、`secret`、`[`、`{`。
2. **M-2：已解決。**
   - 測試改讀 `tests/fixtures/n208_count_original.py.txt`，不再碰 `work/`。
   - 我把 fixture（62 行）與說明檔第 94～155 行（62 行）逐行對照，內容相同，包括 `\u672a\u8a2d\u5b9a` 轉義與檔尾無換行。測試再補一個 `\n`，與原抽取邏輯等價。
   - 限制：我只能用 `git diff` 看 fixture，位元組層級的空白與換行字元是目視對照，不是機械比對。說明檔本身沒有行尾空白。
   - 副檔名 `.txt` 讓 pytest、ruff、mypy 不會碰它。
3. **`.env` 與環境變數：已解決。**
   - `.env` 改 `utf-8-sig`，有 BOM 且鍵在第一行的測試會 STOP，且 `SENTINEL` 不外洩。
   - 環境變數改 `ENV_VAR in env`，空字串也 STOP，有測試。
4. **工作資料夾在 git 工作樹內：已解決，且範圍略廣沒有造成新問題。**
   - 現在 `stop()` 內只要工作資料夾在工作樹內，就不建資料夾、不寫檔，只在視窗印固定文字。
   - 兩個測試：樹內 STOP 前後的檔案樹不變；沒有 DB 這種原本會寫檔的 STOP 在樹內也不寫。
   - 較廣的範圍只讓「home 本身在 git 工作樹內」的人所有 STOP 都沒有檔案可貼。視窗訊息已叫他回報是哪個 STOP，而這種人本來就無法完成流程，所以不會讓 CEO 多卡。
5. **新的洩漏、寫入正本、卡住：沒有。**
   - 新增的寫入點只有 `probe_lines_dropped=<整數>`，已列入白名單測試。
   - `INTRO` 新增 NSSM／Task Scheduler 的固定文字，有測試。
   - 沒有新增正本寫入。複製與雜湊邏輯沒變。
   - `run_at_utc` 的正規式放寬到 `[0-9T:.+Z-]+`，仍不可能夾帶代號或路徑。
6. **`payload: UNREADABLE`（JSON 非 dict）：合理。**
   - 原版在這種 payload 會丟例外而沒有輸出；現在沿用同一個既有標記，並以固定文字說明，不印內容。
   - 無效 JSON 與非 dict 各只印一次，不重複。
   - 這是相對原版的刻意加強，與 `N208_COUNT_RESULT=21` 同性質。

## 驗證
- 讀過全部 4 個檔的 diff，並對照原說明檔第 94～155 行。
- 未執行測試、未重現測試數字、未做 Windows 實測。
- 唯讀權限判準常數：未觸及（本次 4 個檔都不是 `validate_agents.py`，也沒有 `READONLY_AGENTS`／`READONLY_ALLOWED_BASH` 改動）。

## 下一步
1. devops-sre：在 merge commit 上重跑完整 CI。
2. 有 Windows 的人雙擊 `r2-probe.bat` 實機驗證一次（上一輪結論未變）。
3. coordinator：說明文件補上 `N208_COUNT_RESULT=21`、`NON_INTEGER`、`probe_lines_dropped=` 的意義。
4. 凍結後待辦：
   - 部署閘門那次補程序檢查（scheduler 程序）。
   - `r2-probe.bat` 的 `cd /d` 改 `pushd`，涵蓋 UNC 路徑。
   - 視窗的 Ctrl+C traceback 與「傳截圖」提示，請叮嚀只貼 Notepad 內容。

相關檔案：
- `/home/user/AICompany/apps/stock-desk/backend/scripts/r2_first_run.py`
- `/home/user/AICompany/apps/stock-desk/backend/tests/test_r2_first_run.py`
- `/home/user/AICompany/apps/stock-desk/backend/tests/fixtures/n208_count_original.py.txt`
- `/home/user/AICompany/apps/stock-desk/backend/tests/fixtures/README.md`
（以上均在 `origin/feat/r2-probe-oneclick`）

---

## coordinator 註記（2026-11-13）
- qa 註明 fixture 與說明檔是目視對照。coordinator 以腳本做位元組比對：分支上的 `tests/fixtures/n208_count_original.py.txt` 與 `work/dispatch/2026-11-13-R2探測操作說明-CEO.md` 中 `$N208_COUNT = @'` 到 `'@` 之間的內容完全相同（2944 字元）。

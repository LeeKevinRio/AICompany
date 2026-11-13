# R2 探測一鍵檔程式碼審查

- 審查者：qa-reviewer
- 日期：2026-11-13
- 轉存：coordinator，逐字轉存 subagent 最終回報

---

## 本次結論
**程式碼審查結論：PASS，`BLOCKING_ISSUES=false`。**
- 審查範圍：`git diff origin/product/stock-desk...origin/feat/r2-probe-oneclick`，head `26f23915`，只有 3 個新檔，沒有超出範圍。
- 隱私與唯讀六項檢查，本次讀碼都成立（第 6 項見下方，只差一個未來維護風險）。
- 有 2 項 medium（不擋合併）、數項低風險待辦。
- 測試與覆蓋率數字（`10139 passed`、97.62%）我未重現。合併前須在 merge commit 上由 devops-sre 重跑完整 CI。
- bat 無法在 Linux 實測，我的結論只來自讀碼，仍需 Windows 實機雙擊一次。
- `codex` 指令不存在（`command not found`），所以這是**單家審查，沒有 Codex 第二意見**。

## 各部門回報（逐項判定）

**1. paste-back 與視窗輸出：成立。** 我逐一追了每個寫入點與 `print`：
- `r2_first_run.py` 的 `HEADER`、各 `STOP:` 訊息、`copied:`／`not present:`、`compare_copy` 的 `<檔名>: <verdict>`，全是固定字串。
- N-208 各行（`:87-148`）只印計數、布林、UTC 日期，不印股票代號。
- 偵測工具 stdout 只留 `PROBE_PREFIXES` 開頭的行（`:279`），`report_md=`、`report_json=` 被丟棄。
- 我讀了 `n177_n190_backtrack_probe.py:2244-2252`：這 9 個前綴後面目前只有版本、計數、sha256、時間，所以現況不會洩漏。
- 偵測工具失敗只寫 `probe_exit=<code>` 與 `probe_stderr_lines=<行數>`（`:281-283`），stderr 內容不進檔。
- 例外路徑（`:341-343`）只印固定的 `UNEXPECTED`。STOP 路徑只寫標頭與固定 STOP 行。
- 視窗上的 `_say`（`:61-63`）是 ASCII 轉義，不印路徑。`OUTRO` 只用資料夾名稱。

**2. 唯讀：成立。**
- 正本只被 `.exists()`、`.is_file()`、`copyfile` 的來源端與 `sha256_file(open "rb")` 碰到。
- N-208 對複本使用 `mode=ro` 加 `PRAGMA query_only=ON`（`:101-102`），且沒有任何寫入語句。
- 偵測工具由我讀到的版本只對 `--db-path`（複本）運作；它不在本 diff 內，也沒被 import。

**3. `.env`：成立。**
- `env_file_sets_db_path`（`:150-155`）逐行 `ENV_KEY_PATTERN.match`，回傳布林，內容不保存、不印、不寫。
- 有測試用 `SENTINEL-SECRET` 與 `SENTINEL-DB` 釘住不外洩。

**4. 其他邊界：成立。**
- 沒有讀 `report.md`／`report.json`，沒有 import `app`（有 AST 測試），沒有連網（只有一次連 `127.0.0.1:8000`）。

**5. 工作資料夾在 repo 外：成立。** `inside_git_work_tree`（`:146-148`）從工作資料夾往上找 `.git`，找到就 STOP。

**6. N-208 逐字相同：成立。**
- 我逐行對照 `n208_count` 與原說明檔的內嵌程式，`print`／`" ".join` 的輸出、`未設定` 的 `\u` 轉義、`nt`／`bpt` 預設值邏輯都一致。
- 測試（`test_r2_first_run.py` 約 `:196-231`）從說明檔抽出原程式，對 7 種合成 DB 加缺檔各跑一次，比對輸出與結束碼。
- 唯一的行為差異是新增的 `21`，見第 7 項。

**7. 取捨 1～3：可接受。**
- 取捨 1（檔案寫中文、視窗用轉義）：可接受。現行 Notepad 預設能辨識 UTF-8；只有規則參數「未設定」時才會出現中文。
- 取捨 2（新增 `N208_COUNT_RESULT=21`）：可接受，原版此情況是丟例外。coordinator 要在說明文件補上「21 = 複本不是資料庫」。
- 取捨 3（STOP 時仍在工作資料夾寫 `paste-back.txt`，含落在 git 工作樹內）：可接受，無洩漏風險。
  - 檔案只有標頭與一行固定 STOP 文字，沒有路徑、代號或金額。
  - 誤 commit 的最壞後果只是把兩行無害文字送進該 repo。
  - 副作用是會在那個工作樹內建立 `stock-desk-n208/<時間戳>/` 並使其變髒。建議放入「凍結後待辦」：此特例改成只印視窗、不寫檔。

**8. 停機檢查只看 8000 埠：第一次探測可接受，部署閘門那次不足。**
- 配合「複製後逐檔 SHA-256 比對，不同就停」，能擋住複製期間來源被改動的情況：
  - 複製期間 checkpoint 讓主檔改變，會被比出 `DIFFERENT`。
  - 主檔與 WAL 在複製時間差內被寫入，會被比出 `DIFFERENT`。
- 這次探測本身只讀複本，所以對探測結果不構成風險。
- 漏掉的情況：
  - 閒置的 scheduler 還在，且複製期間剛好沒寫入。它會被判成「已停機」，`paste-back.txt` 也看不出來。
  - NSSM／工作排程器之類的監督程式。若只有 scheduler 被自動重啟，8000 埠查不到。
  - 末尾的 `port_8000_listening=no` 與 `db_location=default` 是**固定字串**（`:278`），不是當下偵測結果。
- 部署閘門（N-177a 上線停機那次）要的是「確定沒有任何寫入者」，只看埠不夠。建議到時補程序檢查，例如用 `subprocess` 呼叫 PowerShell 的 `Get-CimInstance` 並只取筆數。列為凍結後待辦，不擋這次。
- 另外，`INTRO` 只叫 CEO 關三個視窗，沒涵蓋 NSSM／工作排程器常駐的情況。這個在原說明有，一鍵版沒有。

**9. `r2-probe.bat` 逐行讀碼：沒有找到會直接失敗的錯誤。**
- 引號：
  - `set "APP_DIR=%~dp0"` 與 `set "BACKEND_DIR=%APP_DIR%backend"` 正確。`%~dp0` 帶結尾反斜線，直接接 `backend` 沒問題。
  - `cd /d "%BACKEND_DIR%"` 有加引號，路徑含空白可用。
- `where uv >nul 2>nul` 加 `if errorlevel 1 ( … goto fail )`：括號區塊內的 `echo` 沒有未跳脫的 `)`、`&`、`%`，正確。
- `cd /d` 後立刻 `if errorlevel 1`，正確。
- `uv run … ` 之後緊接 `set "RC=%errorlevel%"`，中間沒有夾其他指令，結束碼傳遞正確。
- `if not "%RC%"=="0" echo …` 是單行，不在括號區塊內，安全。
- `pause` 之後 `exit /b %RC%`，在 `setlocal` 範圍內展開正確。
- 檔尾 `:fail` 標籤在 `exit /b` 之後，不會被誤入。
- LF 與 CRLF：product 分支的 `.gitattributes` 有 `*.bat text eol=crlf`（我讀過），檢出會是 CRLF，標籤與 `goto` 沒問題。
- 低風險備註：
  - 在 UNC 路徑（網路磁碟）上雙擊，`cd /d` 會失敗，訊息是「找不到 backend 資料夾」，有點誤導。改用 `pushd` 可解，列待辦。
  - 路徑含目前 OEM 碼頁表示不了的字元時，與 `dev-up.bat` 有同樣的限制。
  - `--no-sync` 要求 `.venv` 已存在；CEO 先跑過 `dev-up.bat` 就會有。
- 需 Windows 實機確認的只有：`input()` 在雙擊視窗的行為，以及 `os.startfile` 開 Notepad。

**10. 測試鑑別力：整體夠，有一個缺口（見 M-1）。**
- 白名單測試（約 `:111-148`）對 `paste-back.txt` 每一行逐一比對正規表示式，另加代號、路徑、`/`、`\`、磁碟代號不得出現。
- 常態流程使用的是真實偵測工具，它輸出 `report_md=<路徑>`，若拿掉前綴過濾，這個測試會失敗。
- `test_probe_stdout_noise_and_stderr_never_reach_the_file` 以假 subprocess 餵入 `report_md=`、`/secret/path`，拿掉過濾會失敗。
- `.env` 的 SENTINEL 測試拿掉 `.env` 處理會失敗。
- 沒有發現必定通過的測試。`test_bat_is_ascii_thin_and_does_not_pull` 與 `test_script_source_is_ascii` 只做子字串或編碼檢查，鑑別力偏弱，但功能性斷言在其他測試。

### Findings

**M-1（medium，隱私縱深，不擋合併）：過濾強度低於 docstring 宣稱的「closed whitelist」。**
- `r2_first_run.py:279` 只比對前綴（`startswith`），前綴之後的內容原樣寫入。
- 目前偵測工具 v2 在這 9 行後面只有計數、雜湊、時間，所以不洩漏。但偵測工具改版時，例如 `gate_affected_symbols=` 後面改成代號清單，會直接進檔，測試也不會抓到。
- `n_targets`／`batches_per_target` 的值（`:122-127`）是來自 DB payload 的任意 JSON，沒有限定為整數。
- 現行測試的正規表示式白名單比程式碼嚴格，但只驗證「這次真實輸出」。沒有「前綴合法、內容夾帶代號」的負向測試。
- 建議：
  - 對偵測工具各行改用 `fullmatch`，例如 `=\d+` 與 `=[0-9a-f]{64}`。
  - 另補一個假 subprocess 回傳 `gate_affected_symbols=2330` 的測試。
  - `n_targets` 與 `batches_per_target` 的值非整數時印固定字串。

**M-2（medium，CI 脆弱度，不擋合併）：測試依賴 `work/dispatch/2026-11-13-R2探測操作說明-CEO.md` 的特定格式。**
- `test_r2_first_run.py` 約 `:196` 以正規表示式 `\$N208_COUNT = @'\n(.*?)\n'@` 抽原程式。
- coordinator 日後把這份說明改成「雙擊一鍵檔」時，只要刪掉或改動內嵌程式，CI 會失敗；以後有人整理 `work/` 也會連帶弄壞 product 的測試。
- 該檔目前確實存在於 `origin/product/stock-desk`，所以現在不會失敗。
- 建議：把原程式凍結成 `tests/` 內的固定檔案，保留原件作為參照。

### 凍結後待辦（不擋合併）
1. `r2_first_run.py:150-155`：`.env` 開檔改用 `encoding="utf-8-sig"`。目前開頭若有 BOM 且鍵在第一行，`^\s*` 比對不到 `﻿`，會漏判。原說明用 `Select-String` 會處理 BOM，這是相對原手動流程的退步，但應用本身也不一定認得這種 `.env`。
2. `:178`（`env.get(ENV_VAR)`）：環境變數被設成空字串時為 falsy，不會 STOP。改用 `ENV_VAR in env`。
3. 停機檢查補程序檢查（第 8 項），於部署閘門那次必做。
4. 工作資料夾在 git 工作樹內的 STOP，不要在該處寫檔（取捨 3）。
5. `INTRO` 補一句：NSSM／工作排程器常駐的人要先停用監督程式，做不到就停在這裡回報。
6. Ctrl+C 中斷會印 Python traceback（含 backend 路徑）到視窗。這只影響視窗，不影響 `paste-back.txt`，但請在說明中叮嚀只貼 Notepad 的內容，不要截整個視窗。
7. `UNEXPECTED` 提示「send a screenshot of this window」：視窗可能含 uv 輸出的路徑，與原說明相同，coordinator 可改為先看過再傳。
8. 取捨 2 新增的 `21` 要寫進說明文件。

## 唯讀權限判準常數
未觸及。兩道機械檢查結果：
- `git diff --name-only`：3 個檔，沒有 `scripts/validate_agents.py`。
- `git diff -G"READONLY_AGENTS|READONLY_ALLOWED_BASH"`：無輸出，也沒有 shadow 定義或常數值被改。
- 本次也沒有異動任何 agent 定義檔，`READONLY_AGENTS` 沒有成員資格異動。

## 驗證
- 讀過：全部 3 個檔（逐行）、原說明檔、交件報告、偵測工具的 stdout 輸出段（`n177_n190_backtrack_probe.py:2244-2252`）、product 分支的 `.gitattributes` 與 `dev-up.bat`（對照 bat 寫法）。
- 未做：沒有執行任何測試，也沒有 Windows 實測。
- 第二意見：Codex 不可用，單家審查。

## 下一步
1. 實作者（data-engineer）：處理 M-1、M-2；待辦第 1、2 項是一行修正，建議順手做。
2. devops-sre：合併前在 merge commit 上重跑完整 CI（ruff、format、mypy、pytest 與覆蓋率）。
3. 找一位有 Windows 的人雙擊 `apps/stock-desk/r2-probe.bat`，確認：按 Enter 後流程跑完、Notepad 跳出、`paste-back.txt` 內容符合白名單。
4. coordinator：把 CEO 的操作說明改為「雙擊 `r2-probe.bat`」前，先處理 M-2；並補上 `N208_COUNT_RESULT=21` 的說明。
5. 部署閘門那次執行前，補上程序檢查（待辦第 3 項）。

相關檔案：
- `/home/user/AICompany/apps/stock-desk/r2-probe.bat`（在 `origin/feat/r2-probe-oneclick`）
- `/home/user/AICompany/apps/stock-desk/backend/scripts/r2_first_run.py`（同上）
- `/home/user/AICompany/apps/stock-desk/backend/tests/test_r2_first_run.py`（同上）
- `/home/user/AICompany/work/dispatch/2026-11-13-R2探測操作說明-CEO.md`

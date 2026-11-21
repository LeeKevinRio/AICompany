# dev-up.bat 缺工具與失敗提示改字分支交件（RC-336、RC-337 (a)、RC-340 (a)）

- 審查者：devops-sre
- 日期：2026-11-21
- 轉存：coordinator，逐字轉存 subagent 最終回報

---

## 本次結論

分支 `chore/dev-up-missing-tool-wording` 已推到 origin，沒有合併、沒有開 PR。

- **分支 head：`315a087bc39cf99df424ec03702a434ad41c1f5c`**。`git ls-remote origin refs/heads/chore/dev-up-missing-tool-wording` 回傳相同的 40 碼。
- 分支從 `origin/product/stock-desk` 的 tip `404ac40f3928a27d91f219c00d5cb3f8ae49ff8b` 長出來，共 4 個 commit，沒有 amend、rebase 或 force push。
- RC-336 五處和 RC-337 (a) 三處都已逐字套用。RC-337 (a) 的控制流程沒有問題：三處的新行都在 `goto fail` 之前，也都在 `if errorlevel 1 (` 區塊內，一定會執行到。`:fail` 段只印空行、`pause`、`exit /b 1`，沒有重複的句子，所以不用回報給你。
- 全套 pytest 通過：12086 passed、2 xfailed、1 warning，覆蓋率 97.81%（門檻 90%），耗時 1973.35 秒（32 分 53 秒）。

## 各部門回報（devops-sre）

### Commit 清單（舊到新，`git show --stat` 摘要）

| commit | 內容 | 異動 |
|---|---|---|
| `04225d7` | `chore: dev-up.bat 缺工具與找不到資料夾時改為通知 coordinator（RC-336）` | `apps/stock-desk/dev-up.bat`，5 增 4 減 |
| `e9a6221` | `chore: dev-up.bat 執行中失敗時也加一句通知 coordinator（RC-337 a）` | `apps/stock-desk/dev-up.bat`，3 增 |
| `e155e09` | `test: 釘住 dev-up.bat 缺工具與失敗提示的字面（RC-336、RC-337 a）` | 新增 `apps/stock-desk/backend/tests/test_dev_up_missing_tool_wording.py`，156 行 |
| `315a087` | `docs: 新增缺工具時的安裝引導內部文件（RC-340 a）` | 新增 `work/dispatch/2026-11-21-缺工具時的安裝引導-內部-devops-sre.md`，60 行 |

### `.bat` 完整 diff（兩個 commit 合計，相對 `origin/product/stock-desk`）

```
@@ -35,21 +35,21 @@ REM ---- 1. prerequisites ----
 where git >nul 2>nul
 if errorlevel 1 (
-  echo [MISSING] git - install from https://git-scm.com/download/win
+  echo [MISSING] git was not found. Do not install or update anything yourself.
 ...
-  echo [MISSING] uv - install from https://docs.astral.sh/uv/getting-started/installation/
+  echo [MISSING] uv was not found. Do not install or update anything yourself.
 ...
-  echo [MISSING] npm - install Node.js from https://nodejs.org
+  echo [MISSING] npm was not found. Do not install or update anything yourself.
 ...
 if defined MISSING (
-  echo After installing, run this script again.
+  echo Tell the coordinator.
   goto fail
@@ -61,6 +61,7 @@
   echo [ERROR] Not a git repo: !REPO_ROOT!
+  echo Do not move or change any file or folder yourself; tell the coordinator.
   goto fail
@@ -84,6 +85,7 @@
     echo [ERROR] Branch switch failed
+    echo Tell the coordinator.
     goto fail
@@ -131,6 +133,7 @@
   echo [ERROR] Backend uv sync failed
+  echo Tell the coordinator.
   goto fail
@@ -140,6 +143,7 @@
   echo [ERROR] Frontend npm install failed
+  echo Tell the coordinator.
   goto fail
```

為了縮短，上面省略了 diff 中間不變的 context 行，異動行完整。

- 換行：索引裡存 LF，`.gitattributes` 的 `*.bat text eol=crlf` 讓工作樹檢出為 CRLF。我改完用 `file` 和 `grep -c $'\r$'` 確認：改前改後都是 CRLF、ASCII，共 303 行全部 CRLF。
- 新增的第 87 行因為在巢狀 `if` 裡，縮排是 4 格，我沿用原行的縮排，其他兩處是 2 格。
- 其餘行沒動，包含 self-update guard、所有 `REM`、`:fail` 段、第 14、71、112、202、207 行附近的提示。

### 測試檔（`test_dev_up_missing_tool_wording.py`，19 個測試）

- 讀法：只用 `BACKEND.parent / "dev-up.bat"` 以位元組讀取，**不依賴 `work/`**。風控字面直接寫成測試內的常數，不從報告檔取。
- 斷言內容：
  - 三個 `[MISSING]` 行各自的字面、前後行結構，以及各只出現 1 次。
  - `[MISSING]` 行不含 `http`、`install from`。
  - 檔內不得再有 `After installing, run this script again.` 或 `run this script again`。
  - `if defined MISSING` 區塊的收尾句。
  - 第 63 行後的分號句，只出現 1 次，後面接 `goto fail`。
  - 三個 runtime `[ERROR]` 行之後是 `Tell the coordinator.`，再接 `goto fail`。
  - `Tell the coordinator.` 全檔恰好 4 次（1 次收尾句加 3 次 runtime）。
  - `:fail` 段結構不變。
  - 新 echo 文字全為 ASCII，且不含 `( ) & | < > ^ % !`。
  - 範圍外 5 行（第 14、71、112、202、207 行附近）逐字未變且各只出現 1 次。
  - CRLF、ASCII，以及 self-update guard 檔頭。
- 限制：我沒有做「把舊檔放進去看測試會不會失敗」的突變驗證，這點沒有查證。

### 既有測試與設定是否受影響（第 5 項）

- 我查了 `backend/tests`、frontend、`.github/workflows`、`scripts/`、`.github`。
- 沒有任何測試或設定讀 `dev-up.bat` 的內容。
- `backend/tests/test_r2_first_run.py` 第 295 行只斷言輸出文字含 `"dev-up.bat"`。第 739～746 行的 `test_bat_is_ascii_thin_and_does_not_pull` 讀的是 `r2-probe.bat`（`BAT_PATH = BACKEND.parent / "r2-probe.bat"`），不是 `dev-up.bat`。兩處都不受影響，不需更新。
- `backend/app/env_status.py` 與 `backend/scripts/r2_first_run.py` 只有字串提到 `dev-up.bat`，我沒碰。
- frontend 沒有任何 `.bat` 內容測試。frontend 的 `.bat` grep 命中只是 `.batch` 之類的字串。

### 內部文件（RC-340 (a)）

- 檔頭寫明「給 coordinator 用的內部文件，不是給 CEO 的文件」。
- 內容有三個原網址、各工具建議版本與依據、RC-340 (b)(c)(d) 的處理步驟。
- `work/.gitignore` 的 `!dispatch/**` 有放行，檔案確實在 commit `315a087` 內（`git commit --stat` 有列），已追蹤。
- 版本查證（查證日 2026-11-21）：
  - **Node.js：已查證。**
    - 讀 `https://nodejs.org/dist/index.json`，Node 22 版線最新是 v22.23.5（2026-11-11 發布，LTS 代號 Jod，隨附 npm 10.9.9）。
    - 專案固定在 Node 22（Dockerfile、CI、README），所以建議留在 22 版線。
    - 同一份清單另有 v24.22.3 與 v26.13.1 兩條 LTS 線，專案沒驗證過，不建議換。
  - **uv：部分查證。**
    - 只查到 PyPI 最新 0.13.9（2026-11-17 上傳）。
    - 官方安裝頁與 GitHub release 在沙盒被擋（HTTP 403）。
    - 專案 README 第 149 行寫的實測版本是 0.11.32。
    - 0.13.9 與本專案 `uv.lock` 是否相容，**我沒有驗證**。文件建議先在乾淨環境跑一次 `uv sync --locked`。
  - **git：未查證，如實寫「未查證」。** git-scm.com 與 GitHub 在沙盒被擋。部署手冊裡的 `git 2.43.0` 是 Linux 沙盒版本，我明確標示不可當建議版本。
- 檔案內沒有模型名稱、祕密，也沒有執行任何 `.bat`。

## 驗證

環境：Python 3.12 專屬 venv（`UV_PROJECT_ENVIRONMENT` 放在 scratchpad，工作樹外），`uv sync --frozen --python /usr/bin/python3.12`，之後都用 `uv run --frozen --python /usr/bin/python3.12`。

| 檢查 | 結果 |
|---|---|
| `ruff check .` | All checks passed! |
| `ruff format --check .` | 547 files already formatted |
| `mypy app tests` | Success: no issues found in 535 source files |
| 新測試檔 | 19 passed（最終版本重跑過） |
| 全套 `pytest --cov=app --cov-report=term-missing --cov-fail-under=90 -q -p no:cacheprovider` | **12086 passed, 2 xfailed, 1 warning in 1973.35s**；Total coverage 97.81%，Required test coverage of 90% reached |

- 全套是在 commit `e155e09` 的狀態下跑的。之後只多了 `315a087` 一個 `docs` commit，只新增 `work/` 底下一個 md，不影響測試。
- 所有 commit 前 `git status` 乾淨，沒有留下 `.coverage` 之類的檔案。
- 我沒有執行 `.bat`，沒有讀 `.env`，沒有碰 `backend/data/`，沒有動 `backend/app/`、`pipeline-acceptance.bat`、`r2-probe.bat`，也沒有 push `product/stock-desk`。

## 另外回報

### A. RC-341：`族群動能-主機部署手冊.md` 現況（只查不改，共 452 行）

我只能回報事實，不能判定它「是否仍交給 CEO 使用」，因為那是 coordinator 的書面紀錄項目。事實如下：

- **文件本身的定位**（第 1～12 行）：適用對象是 CEO（Windows PowerShell），範圍是族群動能功能（ADR-0012 C-52）的「判定程序與 API 程序從同一個 git checkout 在主機上直接執行」這個部署形態。檔頭沒有「已不適用」標註。
- **誰引用它**：
  - 我 grep 過 `apps/stock-desk/README.md`、`.claude/skills/local-run/SKILL.md` 與 `dev-up.bat`，三者都**沒有**引用這份手冊。
  - 只有 `work/research/`、`work/reviews/` 的歷史審查紀錄提到它。
  - 所以現行給 CEO 的日常入口文件沒有指向它。
- **逐節對照**：
  - **0.1 git、uv 版本**：
    - 叫 CEO 自己去裝並附網址與 `winget` 指令，和新口徑衝突，這點風控已指出。
    - `dev-up.bat` 現在會偵測這三個工具缺了就停下來，這部分已被取代。
    - 手冊本節沒有 Node.js，因為它是針對判定與 API 程序，不含前端。
  - **0.2 `.env`**：
    - 手冊要求用 PowerShell 片段把 `.env` 載入成環境變數。
    - `dev-up.bat` 已改用 `UV_ENV_FILE`，讀 `apps\stock-desk\.env`，後端與 scheduler 都會讀到。
    - 這節的做法（`backend\.env` 加手動載入）已被取代，位置也不同。
    - 變數名稱表仍是只有手冊才有的完整清單。我沒有逐項比對它與 README 第 276 行附近的表，這點沒有查證。
  - **0.3 三個 DB 路徑**：
    - 手冊建議顯式指定 `C:\stock-desk\data\...` 三個路徑。
    - `dev-up.bat` 沒有設 `STOCK_DESK_*_DB_PATH`，靠「從 `backend/` 目錄啟動」讓三顆 DB 落在 `backend\data\`（見 `local-run` 與 `dev-up.bat` 檔頭註解）。
    - 兩種做法不同，沒有誰取代誰，要看 CEO 實際怎麼跑。
  - **1. 首次部署**：
    - clone、`uv sync --frozen`、啟動 API 與 scheduler 這些步驟，`dev-up.bat` 已取代（它用 `uv sync --locked`、`start` 開視窗）。
    - **步驟 4（`scripts\attest_sector_gate.py`，產生 build attestation）`dev-up.bat` 沒有做**。我 grep 過 `dev-up.bat`、`local-run`、README，都沒有 `attest`。
    - `backend/scripts/attest_sector_gate.py` 檔案存在，`backend/app/_build/` 目錄目前不存在。手冊說沒有 attestation 時判定會恆為 NE-7（fail-closed）。
    - 手冊的啟動指令綁 `--host 127.0.0.1`、把 log 導向 `logs\`，`dev-up.bat` 沒有這些。
  - **2. 暖身回補**（`python -m app.services.pit_snapshot --warmup`）：
    - 只有這份手冊有寫，`dev-up.bat`、`local-run`、README 都沒有。
    - 手冊稱這是 D0 前的一次性操作。我沒有查證 D0 現在是否已過。
  - **3. 每次更新**：
    - `git pull` 與 `uv sync` 已被 `dev-up.bat` 取代。
    - **重新產生 attestation 這一步 `dev-up.bat` 沒有做**，只有手冊寫。
  - **4. 備份**：
    - `local-run` 的「資料與備份」與 README 第 90 行起已有原生路徑的「停機後成套複製 `*.db`、`*.db-wal`、`*.db-shm`」版本。
    - 手冊另有 4.4「WAL 模式下的安全備份做法」，內容是 `sqlite3 .backup` 與 PowerShell 版本。
    - 我沒有讀完 4.1～4.4 的全文，所以細節是否都已被取代，這點沒有查證。
    - 但 `local-run` 與 README 只有「停機複製」，**手冊 4.4 的線上備份作法只有這份手冊有**。
  - **5. 監控與告警**：
    - 手冊列出 `attestation:` 五種問題碼及告警規則。
    - 我 grep `dev-up.bat`、`local-run`、README，都沒有這些問題碼的說明，所以只有手冊有。
  - **6、7**（為什麼不能用 compose image 做判定、P95 量測）：只有手冊有，與 `dev-up.bat` 無關。
- **小結**：0.1、1（clone／sync／啟動部分）、3（pull／sync 部分）已被 `dev-up.bat` 部分取代。attestation、暖身回補、`sqlite3 .backup` 備份、監控問題碼、第 6／7 節仍然只有手冊有寫。手冊並非整份失效，這是我的觀察，不是判定。
- **沒有查證**：這台主機（CEO 的機器）實際走哪條路徑，是 `dev-up.bat` 還是手冊的 PowerShell 流程。這需要問 CEO 或 coordinator。

### B. RC-339：`windows-latest` job 評估（只評估，沒動 `.github/workflows`）

**可行性：可行。** GitHub-hosted Windows runner 有 `cmd.exe`、`where`、`powershell`，也預設裝了 git、Node.js，以及可用 `astral-sh/setup-uv` 裝 uv。**但我沒有 Windows 環境，也不能執行 `.bat`，下面全是推論，沒有實證。**

**作法草案：**
1. 新增獨立 job `windows-bat-wording`，`runs-on: windows-latest`，觸發路徑只限 `apps/stock-desk/*.bat`、對應測試與這個 workflow 檔，避免拖慢整套 CI。
2. 製造「缺工具」：在 job 內用 `cmd /c` 執行 `.bat`，但先把 `PATH` 縮到只含 `%SystemRoot%\System32`（讓 `where git/uv/npm` 都找不到）。
   - `where` 本身在 System32，所以不會連 `where` 都找不到。
   - 這樣 `dev-up.bat` 會依序印三行 `[MISSING]`、`Tell the coordinator.`，然後 `goto fail` 的 `pause`。
3. `pause` 會卡住：用 `cmd /c "...bat" < NUL` 或 `echo. | cmd /c ...` 讓 stdin 結束。注意 `dev-up.bat` 啟動時會先把自己複製到 `%TEMP%` 再執行副本，副本路徑要放行。
4. 比對輸出：把輸出存檔，與預期字串逐行比對（分號句也一起比），不是「包含就好」。
5. 「找不到資料夾」路徑：複製 `.bat` 到一個沒有 `backend` 的暫存資料夾去跑（`forecast-status.bat`、`gap-check.bat`、`pipeline-acceptance.bat`、`r2-probe.bat` 的 `cd /d "%BACKEND_DIR%"` 會失敗）。
   - 這四支可以跑得到。
   - `dev-up.bat` 的 `Not a git repo` 要在沒有 `.git` 的位置才觸發，要先確保 `where git` 通過，路徑才會走到第 63 行那一段。
6. 這樣做只實測 `echo` 行與 `where`／`cd` 的分支，不會真的跑 `uv`、`npm`、`git pull`，也不會碰資料。

**成本：**
- 開發 1～2 小時加除錯（cmd 的 `PATH` 縮減、`pause`、巢狀 `if` 的實際行為都得在 runner 上試）。
- CI 時間約 1～2 分鐘一次（只跑這幾個 `.bat` 加比對）。
- GitHub-hosted 的 Windows runner 分鐘數計費倍率比 Linux 高。若 repo 是 public，標準 runner 免費；若 private 要看方案額度，我沒有查證本 repo 是 public 還是 private，這點若要採用需 CEO 確認。

**風險：**
1. 這是第一個會「真的執行 `.bat`」的 CI job，我這次的限制是不執行 `.bat`，要採用需 coordinator 與 CEO 明確同意並由 qa 審查。
2. 縮減 `PATH` 做法若寫錯，可能意外跑到 runner 預裝的 git/uv，測不到缺工具路徑。要加一個前置斷言確認 `where git` 失敗。
3. runner 的 cmd 與 CEO 的 Windows 版本、語系、`%TEMP%` 位置可能不同，**通過不代表 CEO 實機一定相同**，只能當實證加強，不能取代實機驗證。
4. 驗證分號句（RC-339）用 CI 實證有價值：如果輸出和預期不同，風控已預先核可的備用句要五支一起換，改動範圍會跨五支 `.bat` 與它們的測試。
5. 這個 job 要在 `product/stock-desk` 分支上才會觸發，而 `.github/workflows` 的修改有可能碰到 CI 保護規則，要按流程送 qa。

## 下一步

- **qa-reviewer**：複審這四個 commit，逐字核對風控字面（可對照本報告上方 diff 與測試檔常數）、確認 CRLF、確認其他行沒有變動；再送風控做 RC-343 單項確認。
- **coordinator**：
  - 決定 RC-337 (a) 是否併入這個 PR（目前以獨立 commit `e9a6221` 放在同一分支，想拆開時可單獨 revert 或移除）。
  - 依 RC-341 查明部署手冊現況並寫書面紀錄，合併前處理。
  - 合併前確認 CEO 決策 #156 期間，且這個 PR 不得夾帶其他程式改動（RC-284）。
- **devops-sre（我）**：RC-338 的 `pipeline-acceptance.bat`、`r2-probe.bat` 改字等兩支新一鍵檔合併後再做。B 的 Windows CI job 等 coordinator 決定是否採用再動手。
- **補查證**：git 的當下 stable 版號、uv 0.13.9 與 `uv.lock` 的相容性，需要能連網的環境。

## 沒有查證或無法查證的事

- 沒有 Windows 實機：`.bat` 的實際印出、分號句、`where` 行為、PATH 生效時機都沒驗證。
- git 版號未查證；uv 版號只查到 PyPI，沒查官方頁；GitHub API 與 git-scm.com、astral.sh 在沙盒被擋。
- Node.js 版本資料來自 nodejs.org 的 `index.json`，沒有再與下載頁交叉核對。
- 新測試沒有做突變驗證（拿舊 `.bat` 確認會失敗）。
- 手冊 4.1～4.4 與 0.2 的變數表沒有逐項與其他文件比對。
- repo 是 public 還是 private，以及 Windows runner 的計費，沒有查證。

## 相關檔案

- `/home/user/AICompany/.claude/worktrees/agent-a9629b70c09d9bd6a/apps/stock-desk/dev-up.bat`
- `/home/user/AICompany/.claude/worktrees/agent-a9629b70c09d9bd6a/apps/stock-desk/backend/tests/test_dev_up_missing_tool_wording.py`
- `/home/user/AICompany/.claude/worktrees/agent-a9629b70c09d9bd6a/work/dispatch/2026-11-21-缺工具時的安裝引導-內部-devops-sre.md`

# 缺工具時的安裝引導（內部文件）

> **本文件是給 coordinator 用的內部文件，不是給 CEO 的文件。**
> 不要把本文件整份、或其中的網址與指令直接轉貼給 CEO。引導 CEO 時由 coordinator 逐步說明（見第 4 節）。

- 作者：devops-sre
- 日期：2026-11-21
- 依據：風控 RC-336（`dev-up.bat` 缺工具改為「不要自己安裝，告訴 coordinator」）、RC-340（coordinator 收到 `[MISSING]` 回報時的處理）
- 風控定稿來源：`work/reviews/2026-11-21-三支舊一鍵檔缺工具提示定稿RC336至RC343-風控.md`

## 1. 原本 `.bat` 裡的三個官方安裝網址（保存用，RC-340 (a)）

這三個網址原本寫在 `apps/stock-desk/dev-up.bat` 的 `[MISSING]` 行，改字後從 `.bat` 移除，改由本文件保存：

| 工具 | 原本 `.bat` 裡的網址 |
|---|---|
| git | `https://git-scm.com/download/win` |
| uv | `https://docs.astral.sh/uv/getting-started/installation/` |
| npm（隨 Node.js 一起安裝） | `https://nodejs.org` |

注意：這些網址只給 coordinator 查閱。風控禁說「照畫面上的網址自己裝就好」；舊網址不得再被說成現行指引。

## 2. 各工具建議安裝的版本與依據

查證日：**2026-11-21**。查證環境是沙盒，只能連到部分站台，下表分開寫「查到了什麼」與「沒查到什麼」。

| 工具 | 建議 | 依據 | 狀態 |
|---|---|---|---|
| Node.js（含 npm） | 22 版線的最新 LTS：**v22.23.5**（2026-11-11 發布，LTS 代號 Jod，隨附 npm 10.9.9） | 讀取 `https://nodejs.org/dist/index.json` 當日內容。專案目前固定在 Node 22：`apps/stock-desk/frontend/Dockerfile`（`node:22-alpine`）、`.github/workflows/stock-desk.yml`（`node-version: "22"`）、`apps/stock-desk/README.md`（Node 22 + npm）。同一份清單當日另有 v24.22.3（Krypton）與 v26.13.1（Lithium）兩條 LTS 線，**專案未驗證過**，不建議為了「最新」而換版線 | 已查證 |
| uv | **0.13.9**（2026-11-17 上傳），是 PyPI 上當日的最新版；但專案文件中實測過的版本是 **0.11.32**（`apps/stock-desk/README.md` 第 149 行「實測 uv 0.11.32」；該 README 的「已查證版本」表沒有列 uv） | 讀取 `https://pypi.org/pypi/uv/json`。`https://docs.astral.sh` 與 GitHub 的 release 頁在沙盒被擋，**沒有查到官方安裝頁與 release note 對該版本的說明**。專案沒有用 `required-version` 鎖定 uv 版本（`backend/pyproject.toml` 無此設定）；依賴版本由 `uv.lock` 鎖定，`dev-up.bat` 用 `uv sync --locked` | 部分查證（版號來自 PyPI，不是官方安裝頁）；0.13.9 是否與本專案的 `uv.lock` 相容**未驗證**，建議 coordinator 引導安裝前先請 devops-sre 在乾淨環境用該版跑一次 `uv sync --locked` |
| git（Windows 版） | **未查證** | `https://git-scm.com` 與 GitHub release 頁在沙盒被擋，查不到當下 stable 版號。`apps/stock-desk/docs/族群動能-主機部署手冊.md` 寫過沙盒內的 `git 2.43.0`，那只是 Linux 沙盒當時可用的版本，不是 Windows stable，也不是當下版本，**不可當建議版本** | 未查證 |

手冊原第 0.1 節記載的 `uv 0.8.17`、`git 2.43.0`，是沙盒實測可用的版本（當時 `uv sync --frozen` 對本專案 `uv.lock` 成功），**不是建議版本**。手冊第 0.1 節改寫後，這兩個版號會從手冊消失，改在這裡保存。

另外：本專案的 Python 需求是 `>=3.12`（`backend/pyproject.toml`）。依 `uv.lock` 處理的是套件版本；Python 本身是否由 uv 自動取得，要看 uv 的設定與 CEO 的環境，**未查證**。「CEO 不需要另外安裝 Python」這句話沒有依據，**不得轉述給 CEO**。

要在能連網的環境補查證時：git 看 git-scm.com 的 Windows 下載頁標示的版號，uv 看 astral.sh 安裝頁與其 release note，Node.js 看 nodejs.org 的下載頁；查完請把版號與查證日期補回本檔第 2 節。

## 3. 為什麼先通知 tech-architect、再引導安裝（RC-340 (b) 的背景）

風控沒有查證 `verify` 輸出裡「程式與環境是否相同」涵蓋哪些內容，所以不能說安裝或升級工具「不會影響紀錄」。devops-sre 也**沒有查證**這一項。因此下面第 4 節的步驟 2 是硬性要求。

## 4. coordinator 收到 `[MISSING]` 回報時的處理步驟（RC-340）

CEO 的回報應是一行 `[MISSING] <工具> was not found. ...`。

1. **確認事實**：缺的是哪一樣（git、uv、npm）。這幾行出現時，`dev-up.bat` 還沒更新程式，也還沒啟動 stock-desk。請 CEO 不要自己安裝、更新或搬動任何東西。
2. **（RC-340 (b)）預測紀錄期間先通知 tech-architect**：只要已經過了第一筆 `forecast_run`，在引導安裝之前，先通知 tech-architect，請他判斷安裝或升級該工具會不會影響 `verify` 的「程式與環境是否相同」。等他回覆再往下。第一筆 `forecast_run` 之前不適用，但仍建議在紀錄裡寫明「尚未進入預測記錄期間」。
3. **決定版本**：依第 2 節；git 目前沒有查證過的版號，需先請 devops-sre 在能連網的環境補查，或由 coordinator 明確決定用官方下載頁標示的當下版本並記錄。
4. **逐步引導 CEO 安裝**（RC-340 (d)：不得只叫 CEO「照原本的網址裝」就不管了）：
   - 由 coordinator 告訴 CEO 要裝什麼、裝哪個版本、從哪個官方來源取得，並在 CEO 操作期間陪著確認每一步。
   - 必說三點（風控第七節）：這些行表示工具還沒開始執行、`dev-up.bat` 還沒更新程式也沒啟動；要裝什麼與版本由 coordinator 決定；裝好之後要不要再執行、何時執行，由 coordinator 決定。
   - 禁說：「照畫面上的網址自己裝就好」；「安裝不會影響任何東西」或「不會影響紀錄」；「這些訊息以後不會再出現」；把這次改字說成「為了保護資料」或「安全性升級」；把舊字面當成現行字面。
5. **確認安裝結果**：請 CEO 開新的命令提示字元，執行 `git --version`、`uv --version`、`npm --version`，把畫面上的版本文字貼回來（新開視窗是為了讓 PATH 生效）。若仍缺，回到步驟 1。
6. **（RC-340 (c)）在 `work/` 寫一筆紀錄**：日期、缺的是哪一樣、安裝後的版本、是誰引導的；若走過步驟 2，一併記下 tech-architect 的回覆。建議放在 `work/dispatch/`，檔名帶日期與工具名。
7. **何時再跑 `dev-up.bat`**：由 coordinator 決定，不由 CEO 自行決定。

## 5. coordinator 收到 `[ERROR]`、`[TIMEOUT]`、`[STOP]`、`[FAILED]`、`[FAIL]` 或要求重新開機的回報時的處理（RC-337 (a)、RC-383 (a)、RC-437、RC-438）

合併後，CEO 也會因為下面幾處失敗來找 coordinator。5.1 的三處畫面是一行 `[ERROR] ...`，下一行是 `Tell the coordinator.`；5.2 是 `dev-up.bat` 其餘會停下來或印出失敗字樣的行。**這些情形都不能套用第 4 節的「還沒更新程式、也還沒啟動」**，因為它們發生的時間點比 `[MISSING]` 晚（`[MISSING]` 以外，只有 5.2 的最前面幾列發生在 `git pull` 之前，各列逐一寫明）。

### 5.1 三種 `[ERROR]` + `Tell the coordinator.`

下表的行號是目前分支上 `apps/stock-desk/dev-up.bat` 的行號（共 306 行），依實際控制流程整理。「前面已執行」是指程式跑到該行之前，已經跑過的、會改動狀態的步驟。

| 畫面上的行 | `.bat` 行號（`[ERROR]` 行／`Tell the coordinator.` 行） | 前面已經執行過的步驟 | 還沒執行的步驟 |
|---|---|---|---|
| `[ERROR] Branch switch failed` | 87／88 | 複製自己到 `%TEMP%`（10～20 行）；檢查 git、uv、npm（35～54 行）；確認是 git repo（61～65 行）；確認追蹤檔案沒有未提交改動（69～73 行）；偵測到目前不在 `product/stock-desk`，CEO 回答 Y 同意切換（77～84 行）；執行 `git checkout`（85 行，失敗） | `git pull`（112 行）、停止舊程序（121～126 行）、`uv sync`（132 行）、`npm install`（142 行）、啟動三個視窗（154～171 行） |
| `[ERROR] Backend uv sync failed` | 135／136 | 上一列在「分支正確」的情形下的全部步驟，再加：`git pull --ff-only` 已成功（112 行；有新 commit 時**程式已更新**）；檢查 8000／3000 埠與舊 scheduler（121～126 行，若有舊程序且 CEO 回答 Y，**舊的 stock-desk 已被停掉**）；`uv sync --locked`（132 行，失敗） | `npm install`（142 行）、啟動三個視窗（154～171 行） |
| `[ERROR] Frontend npm install failed` | 145／146 | 同上一列，再加：`uv sync --locked` 已成功；`npm install --no-save`（142 行，失敗） | 啟動三個視窗（154～171 行） |

說明：

- `Branch switch failed`：失敗發生在 `git pull` 之前，但 `git checkout` 失敗後的工作樹與分支狀態，`.bat` 沒有再檢查。目前在哪個分支、工作樹是否乾淨，**要由 coordinator 查明**，不能假設沒有改動。
- `Backend uv sync failed`、`Frontend npm install failed`：發生在 `git pull` 與「停止舊程序」之後。`git pull` 已成功（有新 commit 時程式碼已更新到最新），舊的 stock-desk 視窗可能已經被結束。`.bat` 只在 CEO 回答 Y 時才會停舊程序（261、294 行附近的 `choice`），所以「是否已被停掉」也要由 coordinator 查明，不能假設。
- 這些行出現時，`:fail` 段（目前 214～217 行）只印空行、`pause`、`exit /b 1`，不會再印別的句子。
- 以上控制流程是我讀 `.bat` 得出的，沒有在 Windows 實機執行過。

### 5.2 其餘會停下來或印出失敗字樣的行（RC-438 連動）

行號同樣是目前分支上 `apps/stock-desk/dev-up.bat` 的行號（共 306 行）。這些行都不屬於 `[MISSING]`，也不套用第 4 節。

| 畫面上的行 | `.bat` 行號 | 前面已經執行過的步驟 | 還沒執行的步驟 |
|---|---|---|---|
| `[ERROR] Cannot copy dev-up.bat to the temp folder ...` | 14 | 只有檢查 `DEVUP_SRC_DIR` 並嘗試複製自己到 `%TEMP%`（10～12 行，失敗）。尚未檢查任何工具，也沒有碰 git 或任何程序 | 之後全部（35 行起） |
| `[ERROR] Not a git repo: ...`（63 行），下一行是另一句提醒（64 行） | 63／64 | 複製自己（10～20 行）；檢查 git、uv、npm（35～54 行）；偵測 curl（56～58 行）；`git rev-parse` 判斷不是 git repo（61 行） | 追蹤檔案改動檢查（69～73 行）、分支檢查、`git pull`（112 行）、停止舊程序、`uv sync`、`npm install`、啟動三個視窗 |
| `[STOP] You have local changes to tracked files ...` | 72 | 上一列之前的全部步驟，再加：確認是 git repo（61 行）；`git status --porcelain` 發現追蹤檔案有改動（70 行） | 分支檢查與切換（77～91 行）、`git pull`（112 行）、停止舊程序、`uv sync`、`npm install`、啟動三個視窗。這一列沒有改動任何東西，但**工作樹有未提交改動這件事本身要由 coordinator 查明** |
| `[ERROR] git pull failed ...` | 114 | 分支檢查通過（或 CEO 回答 Y 並切換成功，77～91 行）；顯示 `.env` 狀況（96～107 行）；`git pull --ff-only`（112 行，失敗） | 停止舊程序（121～126 行）、`uv sync`（132 行）、`npm install`（142 行）、啟動三個視窗（154～171 行）。`git pull` 失敗後工作樹與分支狀態要由 coordinator 查明，不能假設沒有改動 |
| `[FAILED] Port 8000 is still in use ...` 或 `[FAILED] Port 3000 is still in use ...`（同一行字面，埠號不同） | 270 | `git pull --ff-only` 已成功（112 行；有新 commit 時程式已更新）；偵測到該埠有程序，CEO 回答 Y（261 行）；對該埠的 PID 執行 `taskkill`（266 行）；等候並再次掃描後仍有程序（268～269 行）。若這是 3000 埠，8000 埠的程序可能已在前一輪被停掉（121 行） | 另一個埠（若這是 8000）、舊 scheduler 檢查（125 行）、`uv sync`、`npm install`、啟動三個視窗 |
| `[FAILED] Scheduler is still running ...` | 303 | 同上，兩個埠都已通過（121～124 行，其中任一埠若有舊程序且 CEO 回答 Y，**舊的 stock-desk 已被停掉**）；偵測到舊 scheduler，CEO 回答 Y（294 行）；對它執行 `taskkill`（299 行）；等候並再次掃描後仍在執行（301～302 行） | `uv sync`（132 行）、`npm install`（142 行）、啟動三個視窗（154～171 行）。這一列的 `taskkill` 已經執行過，但舊 scheduler 仍在 |
| 要求重新開機的那一句：`PID 4 is a Windows system process and cannot be stopped. Reboot and try again.` | 256（前面一行 253 是 `[NOTICE] Port ... is already in use:`，後面 257 行直接結束該段） | `git pull --ff-only` 已成功（112 行）；掃描埠時發現 PID 4 佔用 8000 或 3000（250 行）。若這是 3000 埠，8000 埠的程序可能已在前一輪被停掉（121 行）。這一列**還沒有**問「Stop the old process?」，也沒有對 PID 4 執行 `taskkill` | 另一個埠、舊 scheduler 檢查（125 行）、`uv sync`、`npm install`、啟動三個視窗。注意：這句不是以 `[` 開頭的行，容易被漏掉 |
| `[TIMEOUT] Backend did not become healthy in time ...`（backend 健康檢查逾時，60 秒） | 206（由 163 行跳入 204 行） | 到 `uv sync`、`npm install` 為止的全部步驟（含 `git pull`、停舊程序；若有舊程序且 CEO 回答 Y，**舊的 stock-desk 與舊 scheduler 已被停掉**）；已啟動 backend 視窗（154 行）並輪詢 `/health` 30 次未通過（157～165 行） | 啟動 scheduler 與 frontend 視窗（170～171 行）、等候 frontend、狀態列（189～193 行）、開啟瀏覽器（195 行）。**scheduler 在這一列沒有啟動過**，而舊的可能已被停掉 |
| `[TIMEOUT] Frontend did not start in time ...`（frontend 逾時，90 秒） | 211（由 180 行跳入 209 行） | 同上，再加：backend 健康檢查已通過（167 行）；已啟動 scheduler 與 frontend 視窗（170～171 行）；輪詢 `:3000` 45 次未通過（173～182 行） | 狀態列（189～193 行）、開啟瀏覽器（195 行）、`Done.`（197 行）。scheduler 視窗已經啟動，但沒有經過狀態列確認它有沒有在跑 |
| `[FAIL] backend   not answering at ...`、`[FAIL] scheduler not found running ...`（第 191 行字面已依 RC-446 改過，整行見風控判定檔）、`[FAIL] frontend  not answering at ...`（狀態列，三行各自獨立） | 189、191、193 | 全部步驟都已執行完，三個視窗都已啟動，frontend 已回應（173～184 行） | 無。**這三行不經過 `:fail` 段**：之後 `.bat` 仍會開啟瀏覽器（195 行）並印 `Done.`（197 行），結束碼是 0（202 行）。所以畫面上同時有 `[FAIL]` 與 `Done.` 是可能的 |

說明：

- 本表沒有列 `Cancelled.`（82、263、296 行，CEO 回答 N 時印出）與 `[NOTICE]`（253、292 行）。它們不是上列開頭字樣；CEO 若回報，是否比照處理，由 devops-sre 與風控另行判斷，本文件不先下結論。
- 5.2 各列的 B／D 歸類（B：`dev-up.bat` 在停掉舊 scheduler 之後才失敗；D：依 tech-architect R4 的界線）要由 devops-sre 在 RC-438 (b) 的當天書面回覆裡逐案判斷。本文件只列出「前面已執行／尚未執行」的事實，**不預先替任何一列歸類**。前端逾時（211 行）算不算 B，風控也列為待 devops-sre 分類。
- 這些控制流程同樣是讀 `.bat` 得出的，沒有在 Windows 實機執行過；`choice`、`taskkill` 與 `netstat` 的實際行為未驗證。

### 5.3 處理要求

1. **不得**對 CEO 說「還沒更新程式」「沒有改動」「原本的 stock-desk 還開著」，或任何意思相同的話。
2. **不得**叫 CEO 升級 uv 或 npm，也不得叫 CEO 刪除 `.venv` 或 `node_modules`，或自己重跑 `uv sync`、`npm install`。
3. coordinator 對 CEO 只用風控已核可的字面（RC-342 固定句，以及風控核可的 `.bat` 畫面字面）。**要新寫任何對 CEO 的句子，必須先送風控**。本節不提供任何新的對 CEO 說的話。
4. 預測紀錄期間（第一筆 `forecast_run` 之後），在採取任何會改動環境的動作之前，先通知 tech-architect（比照第 4 節步驟 2，RC-340 (b)）。
5. 比照 RC-340 (c)，在 `work/` 寫一筆紀錄：日期、是哪一處失敗、coordinator 查明的分支與工作樹狀態、處理經過、是誰處理的。
6. 之後要不要再執行 `dev-up.bat`，由 coordinator 決定。
7. **與風控 R3-0／R3 的對應**（出處：`work/reviews/2026-11-21-手冊改判處理路徑與重啟請求R3-RC427至RC441-風控.md`，RC-437、RC-438；本節只引用條件編號，不抄訊息字面，要用的字面一律回到該報告取用）：
   - CEO 回報 5.1、5.2 列出的任一種畫面行（含 `[ERROR]`、`[TIMEOUT]`、`[FAILED]`、`[STOP]`、`[FAIL]` 開頭的行，以及要求重新開機的那一句）時，coordinator 的**第一次回覆**用風控的「R3-0」。
   - 之後是否請 CEO 再執行 `dev-up.bat`，依 RC-438 的條件判斷，要送時用風控的「R3」。其中 (b) 要求 devops-sre **當天書面**寫明四件事：屬 B 或 D 的哪一種；造成失敗的原因已排除或判斷為暫時性；除了再執行一次 CEO 不需要做任何事；本節所要求的分支與工作樹狀態已查明（第 1 點起各列的「要由 coordinator 查明」項目）。四件事缺一，不得送 R3。
   - `[MISSING]` 照 RC-340（第 4 節），**不用 R3-0**。
   - 需要 CEO 安裝、更新或刪除任何東西時，**不得用 R3**（RC-438 (d)），改走 RC-340 與第 4 節；裝好之後若要請 CEO 再執行，才可用 R3。
   - 預測紀錄期間，排除原因時凡會動到環境的動作，事前先通知 tech-architect（RC-438 (c)，即上面第 4 點）。
   - 只從 CEO 貼回的狀態報告看出、CEO 沒有回報過畫面行的情形，不得用 R2 或 R3，照原因未明處理（RC-439）。
   - 同一次回報至多送一次 R3；再執行又出現畫面行時不得再送，轉 tech-architect（RC-438 (e)）。
   - 5.2 的 `[FAIL]` 三行可能與 `Done.` 同時出現；`Done.` 不代表三個程序都在跑，coordinator 不得以 `Done.` 當成成功的依據。

## 6. 這份文件沒有涵蓋的事

- 沒有 Windows 實機，上述 `where` 偵測、PATH 生效時機與 `echo` 實際印出，都沒有在 Windows 上驗證。
- 手冊（`族群動能-主機部署手冊.md`）：第 0.1 節已依風控 RC-385 改寫；手冊整體依 RC-427 改判為不是 CEO 的操作文件（保留為團隊工程參考，檔頭標註與就地警示另案處理）。本文件不處理手冊內容。
- `pipeline-acceptance.bat`、`r2-probe.bat` 的改字尚未做（排在兩支新一鍵檔合併之後）。

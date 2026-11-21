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

## 5. coordinator 收到「`[ERROR]` 加 `Tell the coordinator.`」回報時的處理（RC-337 (a)、RC-383 (a)）

合併後，CEO 也會因為下面三處失敗來找 coordinator。這三處的畫面是一行 `[ERROR] ...`，下一行是 `Tell the coordinator.`。**這三種情形不能套用第 4 節的「還沒更新程式、也還沒啟動」**，因為它們發生的時間點比 `[MISSING]` 晚。

下表的行號是目前分支上 `apps/stock-desk/dev-up.bat` 的行號（共 306 行），依實際控制流程整理。「前面已執行」是指程式跑到該行之前，已經跑過的、會改動狀態的步驟。

| 畫面上的行 | `.bat` 行號（`[ERROR]` 行／`Tell the coordinator.` 行） | 前面已經執行過的步驟 | 還沒執行的步驟 |
|---|---|---|---|
| `[ERROR] Branch switch failed` | 87／88 | 複製自己到 `%TEMP%`（10～20 行）；檢查 git、uv、npm（35～54 行）；確認是 git repo（61～65 行）；確認追蹤檔案沒有未提交改動（69～73 行）；偵測到目前不在 `product/stock-desk`，CEO 回答 Y 同意切換（77～84 行）；執行 `git checkout`（85 行，失敗） | `git pull`（112 行）、停止舊程序（121～126 行）、`uv sync`（132 行）、`npm install`（142 行）、啟動三個視窗（154～171 行） |
| `[ERROR] Backend uv sync failed` | 135／136 | 上一列在「分支正確」的情形下的全部步驟，再加：`git pull --ff-only`（112 行，**程式已更新**）；檢查 8000／3000 埠與舊 scheduler（121～126 行，若有舊程序且 CEO 回答 Y，**舊的 stock-desk 已被停掉**）；`uv sync --locked`（132 行，失敗） | `npm install`（142 行）、啟動三個視窗（154～171 行） |
| `[ERROR] Frontend npm install failed` | 145／146 | 同上一列，再加：`uv sync --locked` 已成功；`npm install --no-save`（142 行，失敗） | 啟動三個視窗（154～171 行） |

說明：

- `Branch switch failed`：失敗發生在 `git pull` 之前，但 `git checkout` 失敗後的工作樹與分支狀態，`.bat` 沒有再檢查。目前在哪個分支、工作樹是否乾淨，**要由 coordinator 查明**，不能假設沒有改動。
- `Backend uv sync failed`、`Frontend npm install failed`：發生在 `git pull` 與「停止舊程序」之後。程式碼已經更新到最新，舊的 stock-desk 視窗可能已經被結束。`.bat` 只在 CEO 回答 Y 時才會停舊程序（261、294 行附近的 `choice`），所以「是否已被停掉」也要由 coordinator 查明，不能假設。
- 這些行出現時，`:fail` 段（目前 214～217 行）只印空行、`pause`、`exit /b 1`，不會再印別的句子。
- 以上控制流程是我讀 `.bat` 得出的，沒有在 Windows 實機執行過。

處理要求：

1. **不得**對 CEO 說「還沒更新程式」「沒有改動」「原本的 stock-desk 還開著」，或任何意思相同的話。
2. **不得**叫 CEO 升級 uv 或 npm，也不得叫 CEO 刪除 `.venv` 或 `node_modules`，或自己重跑 `uv sync`、`npm install`。
3. coordinator 對 CEO 只用風控已核可的字面（RC-342 固定句，以及風控核可的 `.bat` 畫面字面）。**要新寫任何對 CEO 的句子，必須先送風控**。本節不提供任何新的對 CEO 說的話。
4. 預測紀錄期間（第一筆 `forecast_run` 之後），在採取任何會改動環境的動作之前，先通知 tech-architect（比照第 4 節步驟 2，RC-340 (b)）。
5. 比照 RC-340 (c)，在 `work/` 寫一筆紀錄：日期、是哪一處失敗、coordinator 查明的分支與工作樹狀態、處理經過、是誰處理的。
6. 之後要不要再執行 `dev-up.bat`，由 coordinator 決定。

## 6. 這份文件沒有涵蓋的事

- 沒有 Windows 實機，上述 `where` 偵測、PATH 生效時機與 `echo` 實際印出，都沒有在 Windows 上驗證。
- `RC-341`（`族群動能-主機部署手冊.md` 第 0.1 節與新口徑衝突）不在本文件範圍，由 coordinator 另行處理。
- `pipeline-acceptance.bat`、`r2-probe.bat` 的改字尚未做（排在兩支新一鍵檔合併之後）。

# dev-up 分支追加：手冊第 0.1 節定稿與內部文件補件（RC-383、RC-384、RC-385）

- 審查者：devops-sre
- 日期：2026-11-21
- 轉存：coordinator，逐字轉存 subagent 最終回報

---

## 本次結論

RC-383、RC-384、RC-385 已辦完，在同一分支追加 3 個 commit，一般 push（沒有 amend、rebase、force）。

- **新 head：`f4f93a72c2c3caf4df2a2de683af9d52e84137a0`**。`git ls-remote origin refs/heads/chore/dev-up-missing-tool-wording` 回傳相同的 40 碼。
- `dev-up.bat` 與 `test_dev_up_missing_tool_wording.py` 一個字都沒動：`git diff 315a087 HEAD --stat` 只有手冊與內部文件兩個檔。
- 行數更正確認：`dev-up.bat` 改前 302 行（`origin/product/stock-desk` 上 `wc -l` 為 302），改後 306 行。我上次寫的「303 行」是誤記。
- 手冊第 0.1 節已與風控定稿逐位元組相同。

## 各部門回報（devops-sre）

### 新增 commit

| commit | type | 內容 |
|---|---|---|
| `61c2c1c` | docs | 手冊第 0.1 節換成風控定稿（RC-385、RC-386） |
| `68e682c` | docs | 內部文件補 RC-383 (a)(b) |
| `f4f93a7` | docs | 內部文件補 RC-384 (a)(b)（commit C） |

我把 B 與 C 分成兩個 commit（你說可以合併也可以分開）。三個 commit 都沒有動程式、測試、`.github/`。

### commit A：手冊（`61c2c1c`）

- **換行**：手冊是 LF。腳本用 `newline=""` 讀寫，沒有改換行。
- **套用方式**：腳本 `/tmp/claude-0/-home-user-AICompany/3f76d891-50d3-55e1-b39d-925b8a90241a/scratchpad/apply01.py`，不是手打。
  - 從風控報告 `[RC-385]` 之後第一組四反引號區塊擷取 22 行。內嵌的三反引號小區塊原樣保留，最後一行是空行。
  - 套用前斷言第 16 行是 `### 0.1 git、uv 版本`、第 36 行以 `### 0.2` 開頭、第 35 行是空行。
  - 套用後斷言 `### 0.2` 標題前恰有一行空行（再前一行非空）。
- **逐位元組證據**：
  - 手冊新第 0.1 節（從 `### 0.1 需要的工具（git、uv）` 到 `### 0.2` 前一行，加結尾換行）的 sha256：`c295d6a5a2c8387e170564dc323cece4da7c79ee64f707811b1d4abee8eecb5e`
  - 風控定稿區塊的 sha256：`c295d6a5a2c8387e170564dc323cece4da7c79ee64f707811b1d4abee8eecb5e`
  - 兩者相同，腳本內以 assert 檢查通過。
- **diff 範圍**：`git diff --numstat` 為 21 增 19 減，只有一個 hunk（`@@ -13,25 +13,27 @@`），涵蓋原第 16～35 行。第 43 行附近的「你」沒有動。
- **完整 diff**（檔案 `apps/stock-desk/docs/族群動能-主機部署手冊.md`）：

```
 ## 0. 前置需求
 
-### 0.1 git、uv 版本
-
-**本項未在 CEO 本機實測，以下為裝機前必查證項目**（devops-sre 職責，見公司章程
-§「查證依賴的當下 stable 版本」）：
-
-- 本次撰寫手冊時，devops-sre 只能在本沙盒環境確認到 `git 2.43.0`、`uv 0.8.17`
-  可正常運作（`uv sync --frozen` 對本專案 `uv.lock` 成功）；**本沙盒沒有對外
-  網路，無法查到 git-scm.com / astral.sh 當下真正的最新穩定版**，上面兩個版號
-  只能當作「已知可用的下限」，不是「當下 stable」。
-- CEO 部署前請在自己機器上查證並安裝當下穩定版：
-  - git：<https://git-scm.com/download/win>，或 `winget install --id Git.Git -e`。
-  - uv：<https://docs.astral.sh/uv/getting-started/installation/>，或
-    `winget install --id=astral-sh.uv -e`（`uv` 本身可以再用
-    `uv python install 3.12` 幫忙裝好 Python 3.12，不需要另外手動裝 Python）。
-  - 裝完後執行 `git --version`、`uv --version`，把實際版號記回本檔案這一節
-    （比照 `apps/stock-desk/README.md`「已查證版本」表的作法）。
-- Python 版本需求：`>=3.12`（`apps/stock-desk/backend/pyproject.toml`
-  `requires-python`）；`uv sync` 會依 `uv.lock` 鎖定所有 Python 套件版本，
-  不吃系統既有的套件版本。
+### 0.1 需要的工具（git、uv）
+
+本手冊的步驟會用到 git 與 uv。電腦上找不到這兩樣工具時，請不要自己安裝、更新或移除任何程式，先告訴 coordinator。
+
+用 `apps/stock-desk/dev-up.bat` 啟動時，它會先檢查 git、uv 與 npm。缺少其中一樣時，畫面會出現以 `[MISSING]` 開頭的英文行。例如缺 git 時：
+
+```
+[MISSING] git was not found. Do not install or update anything yourself.
+Tell the coordinator.
+```
+
+缺 uv 或 npm 時，第一行的工具名稱不同，其餘相同。同時缺兩樣以上時，會有好幾行 `[MISSING]`，最後才是一行 `Tell the coordinator.`。出現這些行時，`dev-up.bat` 還沒更新程式，也還沒啟動 stock-desk。
+
+照本手冊自己輸入指令時，畫面若說找不到 `git` 或 `uv` 這個指令，請停在那一步，不要往下做。
+
+不論是哪一種情形：
+
+- 不要自己安裝、更新或移除任何程式，也不要照網路上或其他文件裡的安裝說明自己操作。
+- 把畫面上的那幾行照實告訴 coordinator；停在本手冊的某一步時，也說明是哪一步。
+- 要裝什麼、裝哪個版本，由 coordinator 告訴您。
+- 裝好之後要不要再執行、從哪一步繼續、什麼時候執行，由 coordinator 決定。
 
 ### 0.2 `.env`：放哪、有哪些變數（只列名稱，不寫真值）
```

### commit B（`68e682c`）：內部文件 RC-383

檔案：`work/dispatch/2026-11-21-缺工具時的安裝引導-內部-devops-sre.md`。

- **(a) 新增第 5 節**，原「這份文件沒有涵蓋的事」順延為第 6 節。內容：
  - 一張表，列三處失敗各自「前面已執行」與「還沒執行」的步驟，並附 `dev-up.bat` 行號（以目前 306 行版本為準）：
    - **`Branch switch failed`（87／88 行）**：已執行的有複製自己到 `%TEMP%`（10～20）、檢查 git／uv／npm（35～54）、確認是 git repo（61～65）、確認追蹤檔案無未提交改動（69～73）、CEO 回答 Y 同意切換（77～84）、`git checkout`（85，失敗）。尚未執行的有 `git pull`（112）、停舊程序（121～126）、`uv sync`（132）、`npm install`（142）、啟動視窗（154～171）。
    - **`Backend uv sync failed`（135／136）**：另加 `git pull --ff-only`（112，**程式已更新**）、埠與舊 scheduler 檢查（121～126，CEO 回答 Y 時舊程序**已被停掉**）、`uv sync --locked`（132，失敗）。
    - **`Frontend npm install failed`（145／146）**：再加 `uv sync` 已成功、`npm install --no-save`（142，失敗）。
  - 說明：`checkout` 失敗後的分支與工作樹狀態 `.bat` 沒再檢查，要由 coordinator 查明；舊程序是否被停掉取決於 CEO 是否回答 Y（`choice` 在 261、294 行），也要查明；`:fail` 段（214～217 行）只印空行與 `pause`，不印別的句子。
  - 處理要求六項：
    1. 不得說「還沒更新程式」「沒有改動」「原本的 stock-desk 還開著」。
    2. 不得叫 CEO 升級 uv／npm、刪除 `.venv` 或 `node_modules`、自行重跑 `uv sync` 或 `npm install`。
    3. 只用風控已核可的字面，要新寫對 CEO 的句子先送風控。
    4. 預測紀錄期間先通知 tech-architect（比照 RC-340 (b)）。
    5. 在 `work/` 寫紀錄。
    6. 是否再跑 `dev-up.bat` 由 coordinator 決定。
  - 本節**沒有任何「對 CEO 說的話」的新字面**。禁說句只出現在「不得說」的清單裡。
- **(b)** 原「CEO 不需要另外安裝 Python」改為：Python 本身是否由 uv 自動取得要看 uv 設定與 CEO 環境，**未查證**；該句沒有依據，**不得轉述給 CEO**。

### commit C（`f4f93a7`）：RC-384

- (a) 「可作為『官方當下最新』的參考」改為「是 PyPI 上當日的最新版」。
- (b) 第 2 節補一行：手冊原 0.1 節的 `uv 0.8.17`、`git 2.43.0` 是沙盒實測可用的版本，不是建議版本，手冊改寫後在此保存。
- RC-384 (c) 已在本報告更正行數（302 改前、306 改後）。

## 驗證

| 檢查 | 結果 |
|---|---|
| `tests/test_dev_up_missing_tool_wording.py` | 19 passed |
| `ruff check .` | All checks passed! |
| `ruff format --check .` | 547 files already formatted |
| 有沒有測試或設定讀手冊 | Grep `主機部署手冊`、`族群動能-主機`（涵蓋 `apps/stock-desk/backend`〔含 `tests`、`scripts`〕、根目錄 `scripts/`、`.github/`）全部 0 筆，沒有需要另跑的測試 |
| 全套 pytest | 依你的指示沒有重跑。上一輪在 `e155e09` 的結果是 12086 passed、2 xfailed、覆蓋率 97.81%。新增的三個 commit 只動 `.md` 文件 |

- `git status` 在 commit 前後都乾淨。
- 沒有讀 `.env`，沒有碰 `backend/data/`，沒有執行 `.bat`，沒有動 `app/`、`pipeline-acceptance.bat`、`r2-probe.bat`、`.github/`，也沒有 push `product/stock-desk`。
- 我沒有看到內部文件裡有模型名稱或 ID。注意：這是我人工檢查，上一次想用 grep 一併檢查被工具擋下，沒有重跑。

## 下一步

- **qa-reviewer**：核對手冊 diff 只有原第 16～35 行、與 RC-385 逐字相同（sha256 如上）；核對 RC-383 已寫入且沒有新增對 CEO 的字面。
- **風控**：RC-385／RC-386 的單項確認，只需對第 0.1 節比對定稿。
- **coordinator**：
  - 第 6 節的 `RC-341` 一句（「不在本文件範圍，由 coordinator 另行處理」）我沒改，現在手冊已套用，如要更新請另告知。
  - 合併前仍要符合 RC-284、#156、qa N-4、追蹤清單一列等既有條件。

## 沒有查證的事

- 沒有 Windows 實機；表中的控制流程是讀 `.bat` 推得，沒有實際執行。
- 內部文件第 5 節的「CEO 回答 Y 才會停舊程序」是依 `choice` 與 `ensure_port_free`／`ensure_scheduler_free` 的結構判斷，沒有在實機走過。
- 風控報告第 6 節對 RC-341 的書面紀錄（追蹤清單那一列），我沒讀到。

## 相關檔案

- `/home/user/AICompany/.claude/worktrees/agent-a9629b70c09d9bd6a/apps/stock-desk/docs/族群動能-主機部署手冊.md`
- `/home/user/AICompany/.claude/worktrees/agent-a9629b70c09d9bd6a/work/dispatch/2026-11-21-缺工具時的安裝引導-內部-devops-sre.md`
- `/tmp/claude-0/-home-user-AICompany/3f76d891-50d3-55e1-b39d-925b8a90241a/scratchpad/apply01.py`（套用手冊用的腳本，在 scratchpad，未進 repo）

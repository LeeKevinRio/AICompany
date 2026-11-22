# RC-529 補普查（6 份漏列文件與再掃）

- 審查者：tech-architect
- 日期：2026-11-22
- 轉存：coordinator，逐字轉存 subagent 最終回報

---

# tech-architect 回報：RC-529 補普查（6 份漏列文件，加上 work/ 與 apps/stock-desk/ 再掃一次）

全程唯讀，只用了 Read、Glob、Grep。沒有寫檔，沒有讀任何 `.env*`，沒有碰 `apps/stock-desk/backend/data/`，沒有看 `.claude/worktrees/`。本報告不含任何對 CEO 的字面；凡是 CEO 看得到的字，一律標「字面待風控定稿」。

標記沿用原普查：〔事實〕有出處；〔推論〕沒有實機驗證；〔建議〕是我的處置建議。優先序沿用原普查表的定義：P0 在接線 PR 合併前；P1 在所列觸發條件之前；P2 接線後可以處理。

---

## 本次結論

1. **RC-529 的 6 份全部建議比照 P2 五份處理，也就是「檔頭標註＋就地警示」。** 6 份第 1 行都把對象寫成 CEO 本機執行（「給 CEO 本機執行」「CEO 本機操作指令」「CEO 本機執行說明」），都要替換。
   - 句型照 RC-523 第 2 點的規則（Grep 到 `STOCK_DESK_DB_PATH` 才加附加句）：
     - F-3、L-12、X-3 用「基本句＋附加句」；
     - N-118、V-1、實測指令只用基本句。
   - 就地警示共建議 8 處必加，另有 9 處可選，交風控判定。
2. **其中 4 份的任務可能還沒結束，所以另列一個 P1 觸發條件。** 這 4 份是 N-118、F-3、X-3、L-12。
   - 〔事實〕追蹤清單第 205 行寫 N-118「待 CEO 本機執行回貼」；決策包二補遺第 53 行對 CEO 說「之後會另給指令」。
   - 〔事實〕F-3 與 X-3a 是 R0-2 簽核包 D-5、D-6 的部署前置。
   - 〔推論，依全員評價第 49 行〕L-12 仍是規則集 1.2.0 的前置。
   - 規則：任何請 CEO 執行其中一項的通知送出之前，要比照 RC-525 另擬新文件送風控，不得沿用舊文件。
3. **原普查與 RC-529 之外，新找到 4 份應該標註：**
   - **`work/dispatch/2026-10-08-CEO知悉簽核包-R0-2.md`（最要緊）：** 讀者就是 CEO。D-5、D-6 把 X-3a、F-3 的本機步驟整段抄進來，第 382 行也有「若你改過 `STOCK_DESK_DB_PATH` 就用你改的路徑」。等於是 RC-529 那兩份 README 的第二個出處，RC-529 沒有涵蓋它。
   - **`work/stock-desk-phase8-spike-盤點.md`：** §6 叫 CEO `pip install httpx`、在本機設 `ALPHA_VANTAGE_API_KEY`，對應 RC-524 第 4、5 條。
   - **`work/research/規則集-1.1.0-回撤改目前值-命中差異-2026-10-04.md`：** §6 標題就是「CEO 本機唯讀對照指令」，內容是在 backend 目錄裡 `uv run`，第 229 行也提到 `STOCK_DESK_DB_PATH`。
   - **`work/research/2026-08-16-行情FAIL修正評估.md`：** §1.5、§2.4 的標題是「給 CEO 的 PowerShell 探測指令」，只做對外 GET。這份不符合 RC-524 任何一條，建議只加檔頭，也可以只用 RC-476，由風控選。
4. **另有約 12 份只需 RC-476 行為規則。** 它們是內部文件裡附帶的 CEO 本機項目，或是已被一鍵檔取代的步驟，詳見下表。
5. **範圍外的發現，要轉風控與 dev-lead：** 產品 API 回給畫面的揭露句裡寫著 `uv run python -m app.dividends.sync`。〔事實〕出處：
   - `apps/stock-desk/backend/app/api/backtest.py:140`
   - `app/api/kelly_wording.py:539`
   - `app/backtest/event_study.py:584`

   這是 CEO 可能在畫面上看到的指令字面。〔事實〕scheduler 現在已經會自己跑除權息同步（`scheduler.py:49`），所以這句可能已經過時。前端有沒有實際顯示這句，我沒有查證。這不屬於文件標註，要另案處理。
6. **RC-524 的六條判準沒有涵蓋 git 操作。** `實測指令-盤中` 叫 CEO `git pull`，還要 `git add`、`git commit`、`git push origin product/stock-desk`（第 24、58～63 行）。
   - 這可能在「預檢到登記完成」期間推送 product（#156）。〔推論〕本機多了 commit，也可能讓 `dev-up.bat` 下一次 `git pull` 失敗。
   - 建議風控考慮在 RC-524 加一條：「`git pull`、`commit`、`push` 等 git 寫入動作」。

## 各部門回報（tech-architect）

### 一、RC-529 的 6 份逐份分類

分類欄依序是：讀者、有沒有本機指令、提到哪些敏感項、是否一次性、仍可能被照做的程度、優先序。行號都是插入前的現況，以標題原文定位。

| 路徑 | 分類 | 理由 | 建議處置 | 行號 |
|---|---|---|---|---|
| `/home/user/AICompany/work/research/N118-除權息預告表持續列出與row_count查證-查證指令-2026-10-24.md` | 讀者：CEO（第 1 行「給 CEO 本機執行」）。本機指令：有（bash：`export`、`cd`、`uv run`、`git rev-parse HEAD`）。提到：`STOCK_DESK_MARKET_DB_PATH`（設在視窗裡）、`backend/data/` 的市場 DB 路徑；沒有提到 `.env`、金鑰、重新啟動、`STOCK_DESK_DB_PATH`。一次性：是。仍可能照做：**高**（追蹤清單第 205 行「待 CEO 本機執行回貼」，決策包二補遺第 53 行）。**P2 標註；P1 另擬（N-118 執行通知送出前）** | 第 13 行要讀者在終端機設環境變數；第 18、24 行在 backend 目錄裡 `uv run`，沒有 `--frozen` 或 `--no-sync`。〔推論，依 uv 一般行為〕這樣可能同步環境。〔事實〕本 checkout 的 `app/forecast/claims.py` Grep 不到 `STOCK_DESK_MARKET_DB_PATH`；對記錄有沒有作用，我沒有查證 | 檔頭標註（基本句）＋第 1 行替換＋就地警示 1 處。字面待風控定稿。附加句只點名 `STOCK_DESK_DB_PATH`，要不要像 SPK-2 那樣在警示裡寫「不要設定本節寫到的環境變數」，由風控決定 | 第 1 行替換；檔頭插在第 2 行之後、第 3 行（`- 日期`）之前；警示：`## 一、怎麼跑`（第 8 行），插在第 9 行空行之後、第 10 行 code fence 之前（RC-524 第 5 條是否涵蓋 `uv run`，由風控判定） |
| `/home/user/AICompany/work/research/V-1-除權息列出前置天數-查證指令-2026-10-04.md` | 讀者：CEO（第 1 行）。本機指令：有（`cd`、`uv run`，第 48 行把輸出導向 `work/research/`）。提到：`backend/data/` 的市場 DB 路徑；第 15 行說明 `STOCK_DESK_MARKET_DB_PATH`；沒有提到 `.env`、金鑰、重新啟動。一次性：是。仍可能照做：中（ADR-0016 V-1 仍是「待查證」；Glob 在 `work/reviews/` 找不到 CEO 回傳的結果檔）。**P2；P1 另擬（請 CEO 做 V-1 查證之前）** | 理由同上，`uv run` 沒有 `--frozen`。第 48 行把檔案寫進 repo 工作樹。〔事實〕`dev-up.bat` 第 69 行用 `--untracked-files=no`，新增未追蹤檔不會觸發 `[STOP]` | 檔頭（基本句）＋第 1 行替換＋就地警示 1 處，另 1 處可選 | 檔頭插在第 2 行之後；警示：`## 一、怎麼跑`（第 8 行，插在第 9 行之後、第 10 行之前）；可選：`## 四、CEO 跑完請回傳`（第 46 行，插在第 47 行之後） |
| `/home/user/AICompany/work/research/實測指令-盤中-2026-10-05.md` | 讀者：CEO（第 1 行「CEO 本機操作指令」）。本機指令：有（PowerShell：`git pull`、`uv sync --locked`、五次 `uv run`、`git add`／`commit`／`push`）。提到：沒有 `.env`、`STOCK_DESK_DB_PATH`、金鑰（第 52 行寫明不需要）。一次性：是（日期是 10/05，但第 47 行「之後任一交易日再跑」沒有期限）。仍可能照做：低到中（`work/research/` 裡沒有 `驗證結果-盤中-*`，〔推論〕當時可能沒有執行或沒有 commit）。**P2** | 第 26 行 `uv sync --locked` 屬 RC-524 第 5 條。第 24 行 `git pull`、第 58～63 行 commit 與 push 到 `product/stock-desk`，不在 RC-524 六條內，但牴觸常設規則「不 `git pull`」，也牴觸 #156。第 3～5 行引言又叫讀者 commit 與 push。**RC-529 列的第 53 行 Ctrl+C 是中斷探測腳本，不是停 backend 或 scheduler，不符合 RC-524 第 2 條** | 檔頭（基本句）＋第 1 行替換＋就地警示 2 處。第 2 處依建議新增的 git 判準，由風控決定 | 檔頭插在第 2 行之後、第 3 行（引言第 3～5 行）之前，不會切斷引言；警示：`## 事前（週日或週一 08:20 前）`（第 18 行，插在第 19 行之後、第 20 行之前）；`## 跑完之後`（第 56 行，插在第 57 行之後、第 58 行 code fence 之前） |
| `/home/user/AICompany/work/research/F-3-快取非正值收盤價查證-腳本/README.md` | 讀者：CEO（第 1 行「CEO 本機執行說明」）。本機指令：有（`cd`、`.venv\Scripts\python`，對**主 DB** 唯讀）。提到：`STOCK_DESK_DB_PATH`（第 29、100、104 行）；`.env`（第 37、57 行，都是「不要打開」，方向一致）；複製 DB（第 59 行）。一次性：是。仍可能照做：中到高（R0-2 D-6「☐ 尚未執行」；R0-2 第 407 行寫當時找不到回貼紀錄）。**P2；P1 另擬（F-3 執行通知前）** | 第 29 行「若你有改過 `STOCK_DESK_DB_PATH` 就用你改的路徑」，等於叫讀者確認這個變數，屬 RC-524 第 1 條。第 96～105 行的表把三個 DB 環境變數教給讀者。腳本本身是 `mode=ro`，不用 `uv`（第 156 行） | 檔頭（**基本句＋附加句**）＋第 1 行替換＋就地警示 1 處，另 2 處可選 | 檔頭插在第 2 行之後、第 3 行（段落第 3～5 行）之前；警示：`## 執行步驟（Windows）`（第 20 行，插在第 21 行之後、第 22 行之前）；可選：`### 關於「純讀取」`（第 54 行，第 59 行複製 DB）、`### 三個資料庫環境變數各對應哪個檔`（第 96 行） |
| `/home/user/AICompany/work/research/L-12-公司行動查證-腳本/README.md` | 讀者：CEO（第 1 行）。本機指令：有（同 F-3）。提到：`STOCK_DESK_DB_PATH`（第 25 行）；`.env`（第 35、52 行，「不要打開」）；複製 DB（第 55 行）。一次性：是。仍可能照做：中（全員評價第 49 行把 L-12 列為待辦，R2 前置）。**P2；P1 另擬（規則集 1.2.0 送審、請 CEO 執行前）** | 第 25 行同 F-3，屬第 1 條。第 28 行要讀者自己填「DB 檔完整路徑」 | 檔頭（**基本句＋附加句**）＋第 1 行替換＋就地警示 1 處，另 1 處可選 | 檔頭插在第 2 行之後、第 3 行之前；警示：`## 執行步驟（Windows）`（第 16 行，插在第 17 行之後、第 18 行之前）；可選：`### 關於「純讀取」`（第 50 行） |
| `/home/user/AICompany/work/research/X-3-持倉幣別市場不符查證-腳本/README.md` | 讀者：CEO（第 1 行）。本機指令：有（同 F-3）。提到：`STOCK_DESK_DB_PATH`（第 29、69 行）；`.env`（「不要打開」）；**從舊備份還原 DB、從其他機器複製 DB**（第 113～115、172 行）；在畫面上修改持倉幣別與成本後重跑（第 135～140 行）。一次性：**大致是，但附有條件式重跑**（第 111 行「就要重跑一次」）。仍可能照做：中到高（X3-R2 部署前置，R0-2 D-5）。**P2；P1 另擬（X-3a 執行通知前）** | 第 29 行屬第 1 條。第 109～117 行把「從備份還原」寫成會發生、發生後要重跑的正常事件；第 172 行「備份檔若日後要還原」也是。這兩處都和 RC-524 第 3 條同性質。第 131～148 行叫 CEO 自己改持倉資料，不在六條內。基本句寫「一次性指令」，和本檔的「條件式重跑」字面是否相合，由風控判斷 | 檔頭（**基本句＋附加句**）＋第 1 行替換＋就地警示 3 處，另 2 處可選 | 檔頭插在第 2 行之後、第 3 行之前；警示：`## 執行步驟（Windows）`（第 20 行，插在第 21 行之後）；`## 結果只代表執行當下`（第 109 行，插在第 110 行之後）；`## 本腳本看不到什麼`（第 166 行，插在第 167 行之後，第 172 行是還原）；可選：`### 查到時（escalation: high）`（第 131 行，插在第 132 行之後）、`### 三個資料庫環境變數各對應哪個檔`（第 65 行） |

6 份共同的事項：
- 第 1 行只換括號內或冒號後的對象字面，檔名不改。
- 6 份都視為不維護，比照 RC-525。
- 所列插入點標題在各自檔內都只出現一次（Read 全文確認）。
- 每個插入點的標題下一行都是空行，「標題、空行、警示、空行、原內容」的形式可以直接套用。

### 二、原普查、RC-529 之外的再掃結果

| 路徑 | 分類 | 理由 | 建議處置 | 行號 |
|---|---|---|---|---|
| `/home/user/AICompany/work/dispatch/2026-10-08-CEO知悉簽核包-R0-2.md` | 讀者：**CEO**（簽核包，第 10 行「部分要你在本機執行指令」）。本機指令：有（D-5、D-6 的 `cd` 與 `.venv\Scripts\python`）。提到：`STOCK_DESK_DB_PATH`（第 382 行）、從舊備份還原與從其他機器複製 DB 後要重跑（第 389 行）、本機 `git log -1`（第 24 行）。一次性：是（10-08 的簽核）。仍可能照做：**中到高**（勾選欄有「☐ 尚未執行，預計日期」；CEO 是否已經回覆，我沒有查證）。**P1（現在就先確認簽核狀態）／P2（標註）** | RC-529 那兩份 README 的步驟在這裡有一份 CEO 直接讀的副本，RC-529 沒有涵蓋。如果簽核還沒完成，加上「請不要照著做」會和「請簽核」互相矛盾 | 〔建議〕先由 coordinator 確認 R0-2 是否已回覆，再分兩路：(a) 已回覆：檔頭（基本句＋附加句，句子是否要改成「簽核包」的說法，字面待風控定稿）＋2 處就地警示；第 1 行標題要不要換，由風控判斷。(b) 未回覆：D-5、D-6 不能原樣再送，要另擬並送風控，其他簽核項另案處理。在那之前，RC-476 先暫行套用到這份 | 檔頭插在第 2 行之後、第 3 行（`- 整理日期`）之前；警示：`### D-5…`（第 378 行）、`### D-6…`（第 395 行）。**注意：這兩個標題下一行就是內容，沒有空行**，照「標題、空行、警示、空行」插入，每處淨增 3 行，不是 2 行；可選：`## 怎麼用這份文件`（第 8 行） |
| `/home/user/AICompany/work/stock-desk-phase8-spike-盤點.md` | 讀者：內部（data-engineer 盤點）。但第 14 行與 §6 直接對 CEO 下指令。本機指令：有（`uv run --with httpx`、`pip install httpx`、本機設 `ALPHA_VANTAGE_API_KEY`）。一次性：是。仍可能照做：中（需求總綱第 317、670 行與 C1-phase8 交付盤點第 37、58 行仍把它列為 CEO 待辦；是否已被 11-01 財務 spike 取代，我沒有查證）。**P2** | 第 154 行屬 RC-524 第 5 條（安裝依賴）；第 155 行「自行在本機環境變數設定」金鑰，屬第 4 條 | 檔頭（基本句）＋就地警示 1 處。第 1 行沒有寫 CEO，不用換 | 檔頭插在第 2 行之後、第 3 行（`**撰寫者**`）之前；警示：`## 6. 待確認事項與下一步`（第 152 行，插在第 153 行之後、第 154 行之前） |
| `/home/user/AICompany/work/research/規則集-1.1.0-回撤改目前值-命中差異-2026-10-04.md` | 讀者：內部（quant 分析），§6 標題寫明給 CEO 本機。本機指令：有（backend 目錄裡 `uv run`、`curl` localhost）。提到：`STOCK_DESK_DB_PATH`（第 229 行「預設讀」）。一次性：是。仍可能照做：低到中（規則集 1.2.0 §8 第 10 項 T2 仍列為「CEO 本機」）。**P2（後段）** | 第 9 行與 §6 叫 CEO 在真實快取上重跑；第 235 行自己寫明 API 那條路「不是嚴格唯讀」，會寫回快取 | 檔頭（照 RC-523 規則，Grep 有命中，所以用基本句＋附加句）＋就地警示 1 處 | 檔頭插在第 2 行之後；警示：`## 6. CEO 本機唯讀對照指令`（第 222 行，插在第 223 行之後、第 224 行之前） |
| `/home/user/AICompany/work/research/2026-08-16-行情FAIL修正評估.md` | 讀者：內部（data-engineer 寫給 TA），但 §1.5、§2.4 的標題寫「給 CEO」，還寫「可直接複製執行」。本機指令：有（PowerShell 對外 GET，在目前目錄寫輸出檔）。提到：沒有 DB、`.env`、金鑰、重新啟動。一次性：是（08-16）。仍可能照做：低。**P2（後段）** | 不符合 RC-524 任何一條，性質和 Phase 1 §1～§5 的 GET 探測相同（RC-524 判定為由檔頭涵蓋） | 〔建議〕只加檔頭，不加就地警示；由風控選擇改用 RC-476 也可以 | 檔頭插在第 2 行之後、第 3 行（`**日期**`）之前；§1.5 在第 89 行、§2.4 在第 207 行（第 208 行我沒有讀） |
| `/home/user/AICompany/work/reviews/2026-11-07-N177實作規格與偵測回溯工具-tech-architect.md` §6.8；`/home/user/AICompany/work/reviews/2026-11-07-N177N190偵測回溯工具交件-data-engineer.md` 第 174～198 行 | 讀者：內部規格與交件，內含「給 CEO 的執行步驟」：關掉 scheduler、`docker compose stop/start`、複製 DB、重開 `dev-up.bat`。已被 R2 一鍵檔取代（決策包二補遺 #141）。**P1（隨 R2 第二次通知）** | 性質和 N-208 第 1 部分相同。它是過程紀錄，加檔頭不合適 | 只需 RC-476 行為規則。另外補一條：R2 第二次執行的通知不得沿用 §6.8 的步驟（併入原普查表 R2 那一列的 P1） | §6.8 在第 573 行 |
| `/home/user/AICompany/work/dispatch/2026-10-16-決策包二-Phase0與Phase1待CEO事項.md` 第 15 行 | CEO 讀的決策包，連到 Phase 1 探測指令（「指令已備妥」） | Phase 1 已經有 P2 標註，連過去的人會先讀到檔頭 | 只需 RC-476 | 15 |
| `/home/user/AICompany/work/dispatch/2026-10-17-決策包二補遺-新增CEO事項.md` 第 53 行（#22） | CEO 讀的補遺，承諾 N-118「之後會另給指令」 | 這是 N-118 那個 P1 觸發條件的來源 | 只需 RC-476；N-118 的新文件要送風控 | 53 |
| `/home/user/AICompany/work/dispatch/2026-10-07-任務單-X-3-…legacy列.md`、`2026-10-06-任務單-單一標的收盤價…`、`2026-10-07-任務單-F-1b-…`、`2026-10-08-任務單-F-9-…`、`2026-08-09-frontend-wiring.md`（第 180 行 `python -m app.directory.sync`）、`2026-08-09-p0-sprint.md` | 內部任務單，提到「CEO 本機執行」，但沒有對 CEO 的步驟。只有 frontend-wiring 第 180 行寫了一條指令 | 不是 CEO 文件 | 只需 RC-476 | — |
| `/home/user/AICompany/work/research/決策卡-停利參考低於現價-評估-2026-10-04.md` 第 94～98 行；`規則集-1.2.0-前置評估-…-2026-10-04.md` 第 445～455、482 行；`work/stock-desk-族群動能-資料評估.md` 第 146 行；`work/stock-desk-排程台標的設定-PRD.md`（P-1～P-9 由 CEO 本機執行） | 內部分析或 PRD，附帶寫 CEO 本機要做的事或指令 | 不是 CEO 讀的文件；規則集-1.2.0 §7 是工程重現用的 demo，不碰 DB | 只需 RC-476 | — |
| `/home/user/AICompany/work/dispatch/2026-11-16-合併前檢查改用CI的Python版本.md`、`work/mahjong-app-架構.md` 第 147 行、`work/C8-修復回歸對照.md`、`work/stock-desk-五條件回測-方法論.md`、`apps/stock-desk/backend/tests/fixtures/README.md` | 工程文件，讀者是 agent 或開發者 | 沒有對 CEO 的步驟 | 不需處理 | — |
| `apps/stock-desk/` 底下的 `*.md`（README、`backend/README.md`、主機部署手冊） | 已在原普查表（RC-434、P1、RC-428） | — | 不重列 | — |
| 〔範圍外〕`apps/stock-desk/backend/app/api/backtest.py:140`、`app/api/kelly_wording.py:539`、`app/backtest/event_study.py:584` | 產品揭露句含 `uv run python -m app.dividends.sync`（creative 稿 `work/stock-desk-C5-Kelly-揭露文案起草.md` 第 996、1044 等行逐字承接） | CEO 可能在畫面上看到一條指令；scheduler 已經會同步，這句可能過時 | 轉風控與 dev-lead 另案，不屬文件標註 | 見左 |

### 三、給風控的待決事項（只列事實與選項，不定字面）

1. 6 份加上新找到 3 份（R0-2、phase8、規則集-1.1.0）的檔頭、第 1 行與就地警示字面。行話評估那份要不要標註也一起定。字面一律待風控定稿。
2. RC-524 第 5 條「`uv sync` 等」是否涵蓋沒有帶 `--frozen` 或 `--no-sync` 的 `uv run`。牽涉 N-118、V-1、實測、規則集-1.1.0。
3. 是否在 RC-524 加第 7 條：git 寫入或同步動作（`git pull`、`commit`、`push`）。
4. N-118 在視窗設的是 `STOCK_DESK_MARKET_DB_PATH`，附加句沒有涵蓋，警示要不要點名。
5. X-3 的「條件式重跑」和基本句「一次性」是否相合；「在畫面上改持倉」要不要加警示。
6. R0-2 的處理分兩路（已回覆或未回覆）。確認之前，RC-476 先暫行套用到 R0-2。
7. 判定「只需 RC-476」的各份：依 RC-529，RC-476 對這些即時轉為常設，需要風控明示把範圍延伸到它們。

## 驗證

**讀過：**
- RC-523～RC-530 全文（415 行）；
- 我 11-21 的普查全文（423 行）；
- RC-529 的 6 份全文：N-118（65 行）、V-1（58 行）、實測（66 行）、F-3（180 行）、L-12（115 行）、X-3（173 行）；
- R0-2 第 1～30、360～419 行，加 Grep；
- phase8-spike 第 1～15、145～158 行；
- 行情FAIL 第 1～20、86～165 行，加 Grep 標題；
- 決策卡評估第 1～12、88～117 行；
- 規則集-1.1.0 第 1～12、218～247 行；
- 規則集-1.2.0 第 1～16、436～485 行；
- N-177 規格第 560～639 行；
- 合併前檢查第 1～40 行；
- 數據核實報告（research）第 1～20 行；
- 追蹤清單第 205、740～749 行。

**Grep pattern：**
- 本機指令字樣：`CEO 本機|CEO本機|請執行|雙擊|\.bat|PowerShell|\$env:|cd apps|uv run|uv sync`。依序跑在 `work/research/`、`work/dispatch/`、`work/` 其餘目錄（glob `!{reviews,dispatch,research}/**`）、`apps/stock-desk/` 的 `*.md`。
- 6 份的敏感項：`STOCK_DESK_DB_PATH|\.env|uv sync|uv run|git (pull|push|commit|add)|Ctrl\+C|重啟|重新啟動|還原|備份`。
- 對 CEO 下指令的句型：`CEO ?本機|雙擊|請執行|請 ?CEO.{0,20}(執行|跑|打開|開啟|輸入)`。
- `work/reviews/` 的標題：`^#{1,3} .*(給 ?CEO|CEO ?本機|CEO 操作|CEO 執行|請 CEO)`，**逾時，結果不完整**。
- `work/reviews/` 的 code fence：`` ```(powershell|bat|cmd) ``，依日期分段跑。
- 引用處：用 6 份檔名查 `work/dispatch/`。
- 程式：`app.dividends.sync`、`STOCK_DESK_MARKET_DB_PATH`、`STOCK_DESK_(MARKET_)?DB_PATH`（`forecast/`、`scheduler.py`）；`dev-up.bat` 的 `status|STOP`。

**沒有查證：**
- 這 6 份與新找到的 4 份是否被 `product/stock-desk` 追蹤；`/home/user/AICompany` 目前在哪個分支。所以上面的程式事實只限這個 checkout。
- 各份是否已經執行過；R0-2 是否已經回覆；phase8 spike 是否已被財務 spike 取代。
- `uv run` 在 CEO 的 uv 版本上會不會同步環境。
- 產品畫面有沒有實際顯示 `dividends.sync` 那句。
- `work/reviews/` 的普查不完整：標題 Grep 逾時，只靠 code fence 補掃。
- `.claude/skills/` 的其他 skill、`work/copy/`、`work/prd/` 只用關鍵字掃過，沒有逐份讀。
- 行情FAIL 第 208 行是不是空行。

## 下一步

1. **coordinator：**
   - 追蹤清單加上本補普查表；
   - 確認 R0-2 簽核狀態，回報風控；
   - RC-476 的暫行範圍加上 R0-2；
   - 6 份的第 1～10 行、對象行與 Grep 結果，比照 RC-473 整理，送風控。
2. **risk-compliance-officer：**
   - 定稿字面，裁定第三節 1～7；
   - 決定「只需 RC-476」各份轉為常設；
   - 決定範圍外那句揭露句的處理。
3. **devops-sre：**
   - 確認追蹤分支；
   - 依定稿另開一支只改文件的 PR，一份一個 commit，不得併入 `docs/p2-oneoff-ceo-notice`；
   - 不在預檢到登記完成之間 push（#156）。
4. **qa-reviewer（含 Codex）：** 比照 RC-526 核對 diff。R0-2 兩處每處淨增 3 行，要特別核對。
5. **dev-lead：** 查證 `dividends.sync` 揭露句在畫面上是否顯示、是否過時，事實交風控。
6. **CEO：** 本件沒有需要決定或操作的事。

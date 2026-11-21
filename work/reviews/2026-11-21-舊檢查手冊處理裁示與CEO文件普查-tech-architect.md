# RC-448 檢查手冊處理裁示與 CEO 文件普查

- 審查者：tech-architect
- 日期：2026-11-21
- 轉存：coordinator，逐字轉存 subagent 最終回報

---

# tech-architect 回報：RC-448 檢查手冊的處理裁示，以及 CEO 文件普查

全程唯讀，只用了 Read、Glob、Grep。沒有寫檔，沒有讀任何 `.env*`，沒有碰 `apps/stock-desk/backend/data/`。本報告不含任何對 CEO 的字面。

標記說明：〔事實〕是有出處、讀過程式或文件確認的；〔推論〕是依程式或一般行為推得、沒有實機驗證的；〔裁示〕〔建議〕是 tech-architect 的決定與建議。

---

# 第一件：族群動能無資料檢查手冊（RC-448）

## 本次結論

1. **〔裁示〕採「甲＋就地警示」**，比照 RC-427 對主機部署手冊的做法：
   - 檔頭加「給 CEO」標註，第 5 行「讀者」改一行；
   - 在 5 個標題下各插入一行警示；
   - 內文一字不改，不刪檔，不搬檔，也不改寫。
2. 不只做甲（只加檔頭），理由：
   - 全文 334 行，要 CEO 動手的步驟在第 77～293 行，離檔頭很遠。
   - 至少有一份 CEO 文件直接連到內文中段：`work/stock-desk-警示評估載入失敗-檢查手冊-2026-10-07.md` 第 129 行指向本檔「步驟 3」，那一節正好在講 `STOCK_DESK_DB_PATH`。
3. 不改寫（乙），理由：
   - 改寫等於多一份 CEO 操作文件，違反 RC-435 甲案「給 CEO 的處置只寫在 README 的 CEO 操作段」。
   - 而且接線之後，這份手冊的步驟沒有一步該由 CEO 做。改寫完的內容只會剩「告訴 coordinator」。
4. 不刪也不搬（丙），理由：
   - 它被 4 個檔引用，其中需求總綱第 537 行引用了它的行號 L61、L303，搬了或刪了這些引用就斷掉。
   - 它是根因分析的紀錄。
   - 它已在 `work/.gitignore` 第 88 行放行、進了版控，刪掉 git 歷史仍留著，對 CEO 也收不回已經讀過的內容。
5. **〔裁示〕性質改判**：從 CEO 操作文件，改為「2026-10-03 的工程紀錄（歷史文件，不維護）」。
   - 和主機部署手冊不同，它沒有維護者，所以**不做** RC-436 那一類的工程內容更正。
   - 已經過時的事實列在下面 1. 的表中，日後有人要引用時以那張表為準。
6. 時點：接線 PR 合併前。放在只改文件的 PR，不得和接線 PR 同一個 PR（RC-284）。diff 規則比照 RC-430：只能有檔頭區塊、第 5 行、5 處插入。

## 各部門回報（tech-architect）

### 1. 逐段盤點：要 CEO 親手做的步驟、和現行規則的衝突、事實是否仍成立

**對照的規則：**
- 常設規則：不自己重抓資料、不改設定（含 `.env`、`STOCK_DESK_DB_PATH`）、不重新啟動、不 `git pull`、不安裝或更新、不用備份覆蓋 DB，有問題一律告訴 coordinator。
- RC-428 檔頭的邏輯：不在 PowerShell 輸入手冊裡的指令。
- RC-432 (a)、(c)；RC-444、RC-446（`[FAIL]` 不自己判讀，告訴 coordinator）。
- ADR-0030：補充九第 3 點（只要有 `STOCK_DESK_DB_PATH` 就拒絕記錄）；補充十三第 4 點 (f)（不得要 CEO 重抓資料、修改設定或改變開機習慣）；F-8。
- 補充十第 3 點，加上我先前報告的重啟損失表（跨過 22:10、23:10，到 24:00 之後才重開，會損失紀錄；執行中被結束，會留下一筆沒有 end 列的執行）。

**對照的程式：**
- product `apps/stock-desk/dev-up.bat`（303 行）；
- 改字分支 `.claude/worktrees/agent-a9629b70c09d9bd6a/apps/stock-desk/dev-up.bat`；
- product `backend/app/` 用 Grep 查。

| 行 | 要 CEO 做什麼 | 衝突 | 事實現在是否成立 |
|---|---|---|---|
| 11～15、311 | 無（說明「給 CEO」） | 無指令。內容是 10-03 的狀態，「今天週六」等已過時 | 過時 |
| 61 | 無（說明） | — | **部分過時**〔事實〕：`app/` 底下確實沒有 dotenv；但「`.env` 只對 docker compose 有效」已不成立，`dev-up.bat` 從 10-26 起經 `UV_ENV_FILE` 載入 `apps\stock-desk\.env`（product 第 26～27、91～105 行）。「`dev-up.bat` L130 的註解」也已位移，第 130 行現在是 `uv sync --locked` |
| 69 | 指向主機部署手冊第 2 節 | RC-432 (a)：不得把 CEO 導向手冊 | 手冊現在有「給 CEO」標註（RC-428） |
| 83 | 看 `[OK]`／`[FAIL] scheduler` 那一行；`[FAIL]` 時「直接看該視窗的錯誤訊息」 | RC-444、RC-446：`[FAIL]` 不自己判讀，要告訴 coordinator | `[OK]   scheduler running - window 'stock-desk scheduler'` 仍成立，RC-446 不改 else 分支。`[FAIL] scheduler not running` 現在仍成立（product 第 187 行、改字分支第 191 行）；**RC-446 合併後換成 `[FAIL] scheduler not found running - …`，這句引文就不成立了** |
| 84 | 關掉全部視窗，`git pull --ff-only` 後重跑 `dev-up.bat` | 不 `git pull`、不重新啟動 | 三個視窗標題仍成立（第 150、166、167 行）。`dev-up.bat` 本身就會 `git pull`（第 110 行），手動 pull 是多餘的。「`518b1e5` 起才開 scheduler」我沒有查證 |
| 85～91 | 在 PowerShell 執行 `Get-CimInstance …`，自己判讀有沒有輸出 | 在 PowerShell 輸入指令（RC-428 邏輯）；自己判讀（RC-444 轉述的 RC-315） | 指令和 `:check_scheduler`（第 274 行）同一個邏輯，事實成立 |
| 93～120 | 捲 scheduler 視窗看 log，照表判讀 | 自己判讀；補充十三 (g) 只要 CEO 照樣告知 `forecast_record:` 行，不要判讀 | 第 102、103、109、115、116、117 行的 log 字面和程式一致（`scheduler.py` 477、495、613 行；`finmind.py` 104 行；`sectors.py` 382 行；`sector_board.py` 381 行）。**第 100 行已過時**：登記行（`scheduler.py` 704～716 行）現在在 17,19,21 之後還接一段 `dividend_sync`，「結尾為…」和「結尾沒有 `pit_snapshot_capture` 就是舊版」的判讀都不成立。第 118 行的字面沒有查證 |
| 109 | 「補 token（見第 4 節 A）」 | 修改設定 | 見第 227～241 行 |
| 117～118 | 把 traceback 截圖給工程團隊 | 方向一致（告訴團隊）。但接線後應該經 coordinator，不是自己判斷要不要給 | — |
| 122～140 | 在 PowerShell 查 `$env:`、使用者層的 `STOCK_DESK_DB_PATH`、`STOCK_DESK_MARKET_DB_PATH`，以及 token 是否存在 | 在 PowerShell 輸入指令；自己查設定（RC-432 (c)「維持現狀」；我先前報告「不得叫 CEO 自己去查設定」）。第 129 行把設這兩個變數寫成正常選項，和補充九第 3 點相反 | 預設路徑的說法成立。但「使用者層的變數會被 dev-up 繼承」只是一般行為，沒有查證 |
| 142～201 | 到 `backend` 目錄，用 `uv run python -` 執行唯讀 SQL，讀主 DB 與市場 DB | 在 PowerShell 輸入指令；自己判讀；`uv run` 預設會同步環境〔推論，依 uv 的一般行為，沒有查證 CEO 的 uv 版本〕，算是安裝或更新 | 程式是 `mode=ro`，不寫入。〔推論〕WAL 下的 ro 連線可能建立 `-shm`；在 scheduler 執行中讀主 DB 不會造成 F-8，但不在任何定稿流程裡 |
| 203～209 | `curl.exe` 查 API | 在 PowerShell 輸入指令 | 唯讀 |
| 213～221 | 照表判讀；第 220 行「重啟 backend」 | 自己判讀；重新啟動 | — |
| 227～241 | `setx FINMIND_API_TOKEN`，或在 PowerShell 設 `$env:` 後執行 `cmd /c dev-up.bat` | 修改設定；重新啟動。**從自己設過環境變數的 PowerShell 啟動 `dev-up.bat` 時，那個視窗若也設了 `STOCK_DESK_DB_PATH`（第 3 步或主機手冊會引導到），子程序會繼承，預測紀錄就被拒絕**（補充九第 3 點；`dev-up.bat` 第 165 行註解寫明會繼承） | 已過時：token 現在可以放在 `apps\stock-desk\.env`（但依 RC-432 (c)，CEO 不得自己改）。〔事實〕README 第 26 行「Windows 已設的同名變數優先於 `.env`」只有部分查證（我先前報告）；`setx` 留下的使用者層 token 會蓋過日後 `.env` 裡的值 |
| 243～255 | 自己判斷 D0，然後執行 `--warmup` | 重抓資料（補充十三 (f)）；在 PowerShell 輸入指令 | CLI 與 `WarmupAfterD0Error` 都還在（`pit_snapshot.py` 24、271、375、470～481 行）。現在是不是已經過了 D0，我**沒有查證** |
| 257～277 | 手動擷取與重算 board（`uv run python -m …`、`-c "…capture_pit_snapshot()"`） | 重抓資料；市場 DB 只增不刪，失敗列會永久留著（ADR-0012 C-10）。和 scheduler 同時寫主 DB〔推論：可能鎖住；兩邊的環境變數不同時，資料會分成兩份〕 | 函式名稱我沒有逐一查證 |
| 279～283 | 「不要自行刪 DB 檔」 | **沒有衝突，方向一致** | 成立 |
| 285～293 | 照時間表做；第 293 行「電腦要在 17:30 前後開著」 | 改變開機習慣（補充十三 (f)） | 日期全部過時（2026-10） |
| 315～327 | 無（給工程的建議） | — | 實作狀態沒有查證。改字分支第 99 行顯示 #3（印出設定是否存在）可能已部分落地 |
| 332 | 「要退回：刪除本檔即可」 | 不是給 CEO 的步驟 | — |

**對 F-8 的結論**〔事實〕：手冊裡沒有任何步驟會整檔還原、更換或重建主 DB，第 283 行還明寫不要刪 DB。它和 ADR-0030 的衝突，都落在補充九第 3 點、補充十三 (f)，以及常設規則。

**〔推論〕CEO 過去若照做過，對帳本有什麼影響：**
- `setx` 只設了 FinMind token；暖身和手動擷取只寫市場 DB。依 K-2，預測紀錄核心不讀市場 DB，也不 import `app.sectors`。
- 所以過去照做過，對帳本沒有直接影響。
- 留下來的只有兩件：使用者層 token 的優先順序問題；市場 DB 裡永久的失敗列（屬 ADR-0012 的範圍）。
- 還沒查證的一點：預測紀錄的大盤強制重抓是不是也用 FinMind。`app/services/index.py` 用 Grep 查不到 FinMind 字樣，但 resolver 的實際來源我沒有追。如果是，暖身用掉 FinMind 額度，可能讓當晚的 `forecast_record` 失敗。

### 2. 處理方式比較與裁示

| 方案 | 優點 | 缺點 | 風險 |
|---|---|---|---|
| (甲) 只加檔頭標註 | diff 最小，前例清楚 | 擋不住直接連到「步驟 3」的讀者（警示手冊第 129 行）。內容 334 行，步驟離檔頭遠 | 照第 3 步或第 4 節 A 做，會改到設定、重新啟動，甚至設定 `STOCK_DESK_DB_PATH` |
| **(甲＋就地警示)（採用）** | 和 RC-427 一致；不動內文，保留紀錄與行號引用 | 要風控定稿警示字面；之後有常設保護 | 低 |
| (乙) 整份改寫 | 內容最新 | 多一份 CEO 操作文件，違反 RC-435 甲案；改完只剩「告訴 coordinator」；沒有人維護 | 兩套 CEO 處置方式並存 |
| (丙) 搬移或刪除 | CEO 看不到 | 斷掉 4 處引用（含行號引用）；失去根因紀錄；git 歷史仍在 | 引用者找不到出處，又重寫一份 |

**引用處**〔事實〕，用 Grep 查，排除 `.claude/worktrees/`，搜尋曾逾時，結果可能不完整：
- `work/.gitignore:88`（放行）；
- `work/dispatch/2026-10-17-後續追蹤清單.md:702`（RC-448 過渡規則）；
- `work/research/2026-10-15-外部prompt需求對照盤點.md:156`；
- `work/stock-desk-新定位-需求總綱與分期-2026-10-15.md:537`（引用 L61、L303）；
- `work/stock-desk-警示評估載入失敗-檢查手冊-2026-10-07.md:129、194`。

**〔裁示〕套用規格：**
- 檔頭區塊：插在第 1 行標題、第 2 行空行之後。
- 第 5 行「讀者：CEO（…）」換成一行新字面，第 6、7 行不動。
- 就地警示：插在下面 5 個標題之後，形式比照 RC-429，即標題、空行、警示、空行、原內容：
  - `## 3. 逐步檢查`（第 77 行）；
  - `### 步驟 1`（第 81 行，有 `git pull`）；
  - `### 步驟 3`（第 122 行，警示手冊直接連到這裡，內容是 `STOCK_DESK_DB_PATH`）；
  - `### 步驟 4`（第 142 行，`uv run` 加 SQL）；
  - `## 4. 立即可做的補救`（第 225 行，token、暖身、擷取）。
- 第 0、1、2、5、6、7 節不加：沒有要 CEO 執行的步驟，由檔頭涵蓋。
- 常設規則比照 RC-430：標註和警示日後不得刪除、移位或弱化，要改先送風控。這份文件本來就不維護，所以沒有工程改寫的例外。
- diff 由 qa 核對，只能有上面三樣。
- 放在只改文件的 PR，不和接線 PR 放在一起。可以和 RC-416 那個 PR 分開，也可以併入新開的文件 PR。不得讓 RC-430 那個 PR 的 diff 範圍變大。
- 由誰套用：devops-sre（原作者）。
- 這份檔在哪個分支被追蹤，我沒有查證。devops-sre 要確認，PR 開在追蹤它的那個分支上。

### 3. 原本的問題（族群動能卡片沒有資料）現在 CEO 遇到時的正確路徑（只寫事實與分工）

**事實：**
- 卡片沒有資料的成因都在團隊這一側：沒有可用的 board、成分股為 0、除權息預告覆蓋不足、判定關卡 NE-1～NE-7。補充一草稿已寫明 `dev-up.bat` 路徑下判定恆為 NE-7，被編號較小的原因遮住。
- 這些都是 fail-closed，只會少顯示，不會多顯示。
- 依 K-2，這些和預測紀錄帳彼此獨立。卡片沒有資料，不會讓記錄停止，也沒有任何東西在等 CEO 搶時間（推論，理由同我先前對還原的判斷）。
- CEO 這一側能提供的觀察只有：畫面上看到什麼；`dev-up.bat` 的三行狀態（RC-444）；每週的狀態報告（不含族群資料）。**目前沒有任何不需要 CEO 輸入指令、就能把族群資料狀態帶回來的管道。**

**路徑：**
1. CEO 告訴 coordinator。coordinator 照實記錄，不請 CEO 執行或查看任何東西，也不引用這份手冊（RC-448 過渡規則；檔頭合併後轉為常設）。回覆字面歸風控。
2. coordinator 當天轉給：
   - devops-sre（scheduler 是否在跑、token 是否存在、`.env` 的載入狀態）；
   - data-engineer（PIT 擷取、board、D0、暖身狀態）；
   - 涉及卡片字面時加上 dev-lead。
3. 團隊先從已有的資料判斷：程式、最近的 `[OK]`／`[FAIL]` 三行、CEO 主動提過的畫面內容。**預設處置是等待**：token 若存在，平日擷取成功之後 board 會自己出現。
4. 真的需要 CEO 這一側的資料或動作時：
   - (a) **讀取狀態**〔建議〕：做成唯讀一鍵檔，也就是原手冊第 6 節 #7 的 `--status`。約束如下：
     - 不寫任何 DB；用 `uv run --frozen` 或 `--no-sync`，不同步環境；
     - 不 import `app.forecast`，不動 `code_digest` 涵蓋的檔案；
     - 避開平日 22:00～23:30；只輸出固定欄位；
     - 由 qa（含 Codex）審查，畫面字面送風控；
     - 經 coordinator，以風控定稿的字面請 CEO 執行。
   - (b) **補 token**：要改 `.env`，又要重新啟動，屬於修改設定加重新啟動。只能經 coordinator、用風控定稿的一次性字面。現有的 R1、R2、R3 都不適用（觸發條件不同），要新訂。
     - 前置：tech-architect 先確認加入 token 會不會改變 `forecast_record` 的資料來源或執行環境紀錄（上面列為未查證）。
     - 預測紀錄期間，事前要通知 tech-architect（RC-438 (c) 的精神）。
   - (c) **暖身或手動擷取**：不由 CEO 做。如果 D0 前仍需要暖身，由 devops-sre 設計受限的執行方式，再照 (b) 的流程走，並確認 FinMind 額度不和預測紀錄衝突。
   - (d) 已經過了 D0、歷史不足時：照原手冊第 4 節 D，要改只能修訂 ADR-0012，並由 CEO 核可。現在沒有觸發。
5. 不得做的事：叫 CEO 查環境變數、看 log 判讀、`git pull`、重開視窗；把卡片沒有資料說成 CEO 的操作問題。

### 4. creative-lead 起草檔頭標註需要的事實條列

**必須涵蓋的事實：**
- 這份文件是 2026-10-03 為當時的狀況寫的檢查紀錄，原本寫讀者是 CEO。現在它不是 CEO 的操作文件，保留作團隊紀錄。
- 文件裡的步驟一律不要照做。範圍包括：
  - `git pull`；
  - 在 PowerShell 輸入任何指令，包括查環境變數、執行 SQL、`curl`；
  - 設定 FinMind token，不論用 `setx`、`$env:` 或改 `.env`；
  - 從 PowerShell 啟動 `dev-up.bat`；
  - 暖身、手動擷取、重算；
  - 重新啟動 backend 或任何視窗；
  - 照 log 或對照表自己判斷原因。
- 文件裡引用的 `dev-up.bat` 畫面字面，有的已經改了，有的會再改（`[FAIL] scheduler …` 那一行）。畫面上出現 `[FAIL]` 等行時的處理，以 coordinator 另外說的為準，不以本文件為準。
- 不要設定 `STOCK_DESK_DB_PATH`（第 3 步提到它）。不要自己刪改 `.env`，不要刪除或覆蓋資料庫檔（本文件第 283 行也這樣寫）。
- 時間表，以及「電腦要在 17:30 前後開著」已經過時，不是請 CEO 改變開關機習慣。
- 族群動能卡片沒有資料時，告訴 coordinator 即可，不需要自己找原因。
- 已經照做過的話（例如設過 token），不要自己復原或刪除，先告訴 coordinator。

**刻意不寫**〔建議〕：
- `.env` 的位置，token 的寫法；
- `UV_ENV_FILE`、D0、暖身、board、K-2、F-8、refusal 等機制與內部代號；
- 「卡片沒資料不影響預測紀錄」這一類的句子。它是事實，但接近 RC-433 的禁說「沒有影響」，要不要寫由風控決定。

**另外要定的字面：**
- 第 5 行的新字面；
- 5 處就地警示（可以比照 RC-429 通用警示的句型；步驟 3 那一處比照 0.2、0.3 用警示，點名 `STOCK_DESK_DB_PATH`）。

**要不要告知 CEO**（比照 RC-433）：由風控判斷。我的事實是：過去照做過對帳本沒有直接影響（推論，見 1.），唯一留下的是 token 的優先順序。

## 驗證

- 讀過：
  - 檢查手冊全文（334 行）；
  - product `dev-up.bat` 全文；改字分支 `dev-up.bat` 用 Grep 查（第 82、111、114、189～193、263、296 行）；
  - RC-442～RC-455 全文；RC-427～RC-441 全文；
  - 我先前報告第 1～466 行；
  - `work/.gitignore` 全文；追蹤清單第 700～702 行；
  - 補充九最終版（`2026-11-19-收盤定案時點重新定案與補充十-tech-architect.md` 第 135～233 行）；
  - 補充十三組版檔（Grep「CEO」）；
  - product `scheduler.py` 第 170～185、690～729 行與 Grep；接線版 `scheduler.py` 第 744～818 行與 Grep；
  - `finmind.py`、`sectors.py`、`sector_board.py`、`pit_snapshot.py`（Grep）。
- 沒有查證：
  - `518b1e5`；第 118 行的 log 字面；第 264～268 行的函式名稱；
  - D0 是否已到；CEO 本機 token 與 `.env` 的現況；過去有沒有照做；
  - 預測紀錄的大盤來源是否用 FinMind；
  - `uv run` 在 CEO 的 uv 版本上會不會同步環境；
  - 這份檔在哪個分支被追蹤；原手冊第 6 節各建議的實作狀態；
  - 接線版的 scheduler 登記行字面。

## 下一步

1. creative-lead：依 4. 起草檔頭區塊、第 5 行、5 處警示，送風控。
2. 風控：定稿；決定要不要告知 CEO；同意把 RC-448 的過渡規則延伸到第二件列出的文件（見第二件）。
3. devops-sre：確認分支；開只改文件的 PR 套用；PR 說明附 diff 範圍。
4. qa-reviewer：依 RC-430 的方式核對 diff，含 Codex 第二意見。
5. 時點：接線 PR 合併前合併。

---

# 第二件：CEO 文件普查

## 本次結論

1. **找到的未處理文件裡，除了 RC-448，還有 3 件必須在接線 PR 合併前處理：**
   - `work/stock-desk-警示評估載入失敗-檢查手冊-2026-10-07.md`：叫讀者關掉 scheduler、用 `uv run` 手動重開 scheduler、重啟 scheduler，而且直接連到 RC-448 那一份的步驟 3。
   - `work/stock-desk-產品說明.md`：「快速啟動」把 Docker 列為「推薦」。Docker 路徑不記錄預測紀錄，資料也是另一份。另外有手動 `uv run`、示範資料寫進 DB、改規則檔後重啟。
   - `.claude/skills/local-run/SKILL.md`：會在新會話自動觸發，並要求「必用、輸出固定指令」。內含 `git checkout`、`git pull`、手動啟動、還原、`taskkill /F`。
2. 另有 4 件有觸發條件（在該文件或其後續通知送出前處理）：R2 探測的第二次執行、帳外缺日比對草稿、N-208 第 2 部分、README 連到 `backend/README.md` 的示範段。
3. 一次性指令文件 5 份，可以在接線後一起標註。
4. **〔裁示〕`local-run` 和現行規則有衝突。** 接線後要改成不含產品細節的「轉介」版本，在接線 PR 合併前合併進 main 並同步到 product。改好之前，coordinator 不得對 CEO 輸出它的任何指令。
5. **更正我先前報告的一個事實**：RC-435 方案比較寫「`work/stock-desk-產品說明.md` 檔頭寫明對象是 CEO」。我這次讀第 1～20 行，檔頭沒有寫讀者是 CEO。它是給使用者的產品說明，CEO 是唯一使用者，所以我仍把它歸為 CEO 會讀的文件（推論）。

## 各部門回報（tech-architect）

### 1. 普查表

**狀態欄說明：**
- 「已處理／處理中」只標狀態，不重複分析；
- 「一次性」指只為一次任務寫的指令，任務是否已經結束，我沒有逐一查證。

**優先序：**
- P0：接線 PR 合併前；
- P1：在所列觸發條件之前；
- P2：接線後可以處理。

| 檔案 | 行號 | 叫讀者做什麼 | 衝突的規則 | 狀態 | 建議處置與優先序 |
|---|---|---|---|---|---|
| `work/stock-desk-族群動能無資料-檢查手冊-2026-10-03.md` | 83～91、109、122～140、142～221、227～277、293 | 見第一件 | 見第一件 | 處理中（RC-448） | 第一件的「甲＋就地警示」。**P0** |
| `work/stock-desk-警示評估載入失敗-檢查手冊-2026-10-07.md`（第 5 行：讀者是 CEO 與工程同事） | 90～96 | 關掉 scheduler 視窗，在 PowerShell 用 `uv run python -m app.scheduler … \| Tee-Object` 手動重開 | 不重新啟動；不手動 `uv run`。下次執行 `dev-up.bat` 時，它會以 `taskkill /F /T` 結束這個手動 scheduler，可能留下沒有 end 列的執行（`dev-up.bat` 第 283～302 行）。從自己設過變數的視窗啟動時，也可能繼承 `STOCK_DESK_DB_PATH`（補充九第 3 點） | **未處理（新發現）** | 同第一件：檔頭標註、第 5 行改一行、就地警示插在 `## 2.`（59）、`### 2.2`（85）、`## 3.`（133）。**P0** |
| 同上 | 155、163 | 「重啟 scheduler 一次」「關 scheduler 視窗後重開 dev-up」「`docker compose restart`」 | 不重新啟動 | 未處理 | 同上（第 3 節的警示涵蓋） |
| 同上 | 149 | 確認 backend 與 scheduler 的 `STOCK_DESK_DB_PATH` 是同一個檔 | 自己查設定；把它當成正常設定 | 未處理 | 同上 |
| 同上 | 129、194 | 指向 RC-448 那份手冊的步驟 3 | RC-448 過渡規則 | 未處理 | 不改這兩行。由 RC-448 步驟 3 的就地警示接住 |
| 同上 | 110～113、141、176 | 按「立即檢查」或 `POST /api/alerts/evaluate`；`git log`；每週自己 grep | 指令本身唯讀，但都是在 PowerShell 輸入指令並自己判讀 | 未處理 | 由第 2 節的警示涵蓋 |
| `work/stock-desk-產品說明.md` | 437～450 | Docker「推薦」：`cp .env.example .env`、`docker compose up --build` | Docker 路徑顯式設定 `STOCK_DESK_DB_PATH`，**不記錄**，資料也是另一份（補充九第 3 點；我先前報告 README 第 41～53 行同一件事）。另外有修改設定 | **未處理** | 檔頭標註，加就地警示於 `## 快速啟動`（437）、`## 離線示範模式`（395）、`## 常見問題`（487）。依 RC-435 甲案，CEO 的啟動方式只連到 README 的 CEO 操作段，不在這裡另寫。**P0** |
| 同上 | 452～466 | 手動 `uv sync`、`uv run uvicorn`、`npm install` | 安裝或更新；手動啟動；和 `dev-up.bat` 混用 | 未處理 | 同上 |
| 同上 | 405～420、468～483 | 執行 `app.demo.seed`、`--reset`；第 407 行建議設 `STOCK_DESK_DB_PATH` | 示範持倉會寫進正式主 DB；設定 `STOCK_DESK_DB_PATH` 就拒絕記錄 | 未處理 | 同上 |
| 同上 | 504～508 | 編輯 `app/advice/rules/default.yaml` 後重啟後端 | 修改檔案；重新啟動。〔推論〕改了被追蹤的檔，下次 `dev-up.bat` 會在第 71 行 `[STOP]`，不更新也不啟動 | 未處理 | 同上 |
| 同上 | 245～252、515 | 用環境變數設定推播通道 | 修改設定（RC-432 (c)；我先前報告 ADR-0029 D-10 第 2 項） | 未處理 | 同上；日後推播設定的處置寫進 README 的 CEO 操作段（RC-435） |
| `.claude/skills/local-run/SKILL.md` | 見第 2 點 | 見第 2 點 | 見第 2 點 | **未處理**（還原段在我先前報告列為待辦） | 第 2 點。**P0** |
| `apps/stock-desk/README.md` | 13、19、21～23、26、32～37、41～53、94～109、129～150、261～263、272～292 | 多處 | 已列在我先前報告 A 節第 3 點 | 處理中（RC-434，creative-lead 起草中） | 照舊。補一項：第 309 行把讀者導向 `backend/README.md` 的示範段，那一段建議設 `STOCK_DESK_DB_PATH`（`backend/README.md` 第 109～116、142 行）。改寫時這個連結要移除或加註。**P0（併入 RC-434）** |
| `apps/stock-desk/docs/族群動能-主機部署手冊.md` | — | — | — | 處理中（RC-428～RC-430、RC-442 已確認，RC-443 待合併時再確認） | 照舊 |
| `apps/stock-desk/backend/README.md` | 13、21、54、109～116、142、160 | 手動 `uv sync`、`uv run`；示範資料；`STOCK_DESK_DB_PATH` | 讀者是工程人員，沒有寫 CEO。只因 README 第 309 行的連結而可能被 CEO 讀到 | 未處理（工程文件） | 不加 CEO 標註，從 README 那一側切斷連結即可。**P1（隨 RC-434）** |
| `apps/stock-desk/frontend/README.md` | 13 | `npm install` | 工程文件 | — | 不處理 |
| `work/dispatch/2026-11-13-R2探測操作說明-CEO.md` | 6、10、13 | 執行 `dev-up.bat` 後關掉三個視窗（含 scheduler），執行 `r2-probe.bat`，再重開 `dev-up.bat` | 接線後關掉 scheduler，就有我先前報告重啟表上的損失；要避開 22:00～23:30，而且要在當晚 24:00 前重開 | 第一次執行已完成（`work/reviews/2026-11-14-R2探測第一次執行結果-CEO回傳.md` 存在）；第二次（部署閘門）「coordinator 另行通知」，還沒發出（推論）。`r2-probe.bat` 仍在 product | 不改這份。**第二次執行的通知若在接線後送出，字面要重新送風控**，對齊 R 系列（避開時段、當晚重開、`[OK]`／`[FAIL]` 三行、不自己重試）。**P1（送出第二次通知之前）** |
| `work/dispatch/2026-11-13-R2探測手動步驟-備用.md` | 17、28～59、89、188 | 自己 `git pull`（經 dev-up）、PowerShell 查 `.env` 的 `STOCK_DESK_DB_PATH`、Ctrl+C 停服務、停用 NSSM、重新啟動 | 在 PowerShell 輸入指令；查設定；重新啟動。第 43 行引用主機手冊的 `$env:STOCK_DESK_DB_PATH`（RC-427 已點名） | 備用，只有 coordinator 請 CEO 改用時才用 | 過渡規則：coordinator 不得改用這份；需要時另擬，字面送風控。**P1**（和上一列同時） |
| `work/reviews/2026-11-08-N208手動換標的操作說明-dev-lead.md` | 14～168（「給 CEO」一節）、307～314、512～524 | 第 1 部分：PowerShell 停服務、複製、計數。第 2 部分（標示 DRAFT DO NOT RUN）：寫入 DB，以及**用備份整檔覆蓋正本** | 第 1 部分已被 R2 一鍵檔取代。第 2 部分的整檔還原，在帳本建立後屬 F-8 與補充九第 2 點 | 第 1 部分被取代；第 2 部分暫停 | 第 2 部分恢復之前，由 dev-lead 改寫並經我核對：不得有整檔還原；CEO 的步驟經 coordinator、以風控定稿字面提出。**P1（N-208 第 2 部分恢復或 N-207 上線前）** |
| `work/dispatch/2026-11-19-帳外缺日比對操作說明-CEO-草稿.md` | 153、163、177、303 | 更新程式（`dev-up.bat`），關掉三個視窗，執行 `gap-check.bat`，再重開；第 303 行「要再執行時，先把三個視窗關掉」 | 關掉 scheduler 和重開的時段（同 R2）；第 303 行等於允許 CEO 自己重開 | 處理中：第三版草稿，待風控最後定稿，還沒發出 | 風控最後定稿時對齊 R 系列與避開時段。**P1（定稿發出前）**。`gap-check.bat` 的合併狀態我沒有查證 |
| `work/dispatch/2026-11-20-登記一鍵檔退役通知-CEO-草稿.md`、`work/dispatch/2026-11-21-驗收一鍵檔退役通知-CEO-草稿.md` | 68／10 | 只是事實陳述「下次用 `dev-up.bat` 時程式會更新」，沒有要 CEO 額外操作 | 沒有衝突 | 草稿，風控審查中 | 不處理 |
| `work/dispatch/2026-11-20-狀態報告操作說明-CEO-草稿.md`、`…預測記錄條件通知-CEO-草稿.md` | — | — | — | 已處理（風控逐字審） | — |
| `work/dispatch/2026-11-16-真實資料管線驗收操作說明-CEO.md` | — | — | — | 進行中的驗收（不分析）；有退役通知草稿 | — |
| `work/research/N152-未收盤殘留檢測-執行指令-2026-10-26.md` | 38～48、58～59、68、71、105 | 停程序；`git fetch`、`git worktree add`；**在 PowerShell 設 `$env:STOCK_DESK_DB_PATH`**；`uv run --frozen`（第一次會同步依賴） | 在 PowerShell 輸入指令；git；設定 `STOCK_DESK_DB_PATH`（只在該視窗有效；同一個視窗再啟動 `dev-up.bat` 就會拒絕記錄）；安裝 | 一次性（是否已執行沒有查證） | 批次檔頭標註「一次性，已結束，不要再照做」。**P2**。過渡：coordinator 不得重送，要重跑就另擬並送風控 |
| `work/research/N172-重複指令偵測-執行指令-2026-10-31.md` | 54～61、115～116、123、164～167 | 停 backend 與 scheduler、`Stop-Process`；`git worktree`；`uv run --frozen`；「照平常方式重新啟動」 | 重新啟動；git；安裝 | 一次性（沒有查證） | 同上。**P2** |
| `work/research/財務資料源spike-執行指令-2026-11-01.md` | 59～79、87～88、100、144 | 在視窗設 API key 等環境變數；`git worktree`；`uv run --frozen` | 修改設定（只限該視窗）；git；安裝 | 一次性（沒有查證） | 同上。**P2** |
| `work/research/2026-10-16-Phase1資料源探測指令-CEO本機代跑.md` | 31～250（helper 與 curl 探測）、235～249、339 | 建立資料夾、執行 GET 探測，FinMind 要 token | 在終端機輸入指令。〔推論〕FinMind 額度和日常擷取共用 | 一次性（第 7 行寫「全部尚未執行」，是 10-16 當時的狀態） | 同上。**P2** |
| `work/stock-desk-數據核實操作說明.md` | 13～15、22～23、48～51 | `export` token；`uv sync`；執行驗證腳本 | 修改設定；安裝 | 一次性（08 月） | 同上。**P2** |
| `work/stock-desk-排程台標的設定-PRD.md`、`…REBALANCE畫面入口-PRD.md`、`work/dispatch/2026-10-07-任務單-…` | — | 被 Grep 的「給 CEO」命中，但都是 PRD 或任務單的內部敘述，沒有操作步驟 | — | 不是 CEO 操作文件 | 不處理 |

**〔建議〕P0 的三件（第一件、警示手冊、產品說明）怎麼處理：**
- 可以放在同一個只改文件的 PR，各自獨立 commit；
- 字面由 creative-lead 一次起草、風控一次審，句型比照 RC-428、RC-429；
- 不得和接線 PR 放在一起；不得讓 RC-430 那個 PR 的 diff 變大；
- 套用人：前兩份是 devops-sre，產品說明由 devops-sre 或 tech-writer。

### 2. `.claude/skills/local-run/SKILL.md`

**事實：和現行規則的衝突**

| 行 | 內容 | 衝突 |
|---|---|---|
| 3、10～11 | CEO 說「重啟」「啟動」時「必用」，「直接輸出本文件的固定指令」 | 接線後，請 CEO 重新執行只能用 R1、R2、R3（風控定稿、有送出條件 RC-412、RC-438）；CEO 自己的重啟受常設規則限制。skill 叫 coordinator 跳過這些 |
| 15～29 | 「建議」`bash dev-up.sh`；第 26 行要讀者自己 `lsof`、`pgrep` | CEO 用 Windows；sh 路徑不偵測舊程序，可能讓兩個 scheduler 同時跑 |
| 42～48 | 環境變數（`STOCK_DESK_DB_PATH` 等）由父程序繼承；第 48 行「CEO 填了 `.env` 卻看到未設定時，先查檔案位置與變數名稱」 | 叫 CEO 查、改 `.env`（RC-432 (c)）；沒有提到 `STOCK_DESK_DB_PATH` 會造成拒絕記錄（補充九第 3 點） |
| 56～96 | 手動 `git checkout`、`git pull`、`uv run --env-file`，手動起 backend、scheduler、frontend | 不 `git pull`；不手動啟動；和 `dev-up.bat` 混用時會被 `taskkill /F /T`，留下沒有 end 列的執行（`dev-up.bat` 第 283～302 行）；手動 `uv run` 不帶 `--locked`〔推論：可能同步環境，`uv.lock` 和 `pyproject.toml` 不一致時可能改寫被追蹤的 `uv.lock`，讓下次 `dev-up.bat` 在第 71 行 `[STOP]`〕 |
| 108～111 | 備份要停三個程序；還原要刪掉現有檔再複製回去 | 還原在帳本建立後屬 F-8 與補充九第 2 點（我先前報告已列）；備份會關掉 scheduler（時段和當晚重開） |
| 112～113 | `docker compose stop`、`sqlite3 .backup` | Docker 路徑不記錄 |
| 118～120 | `lsof -ti:8000 \| xargs kill`、`taskkill /PID <pid> /F` | 強制結束可能留下沒有 end 列的執行；屬於重新啟動 |

**〔事實〕優先順序**：章程第 2 節寫明「與 accepted ADR 衝突時以 ADR 為準」。ADR-0030 補充九、補充十三的要求，優先於這個 skill。

**〔事實〕結構問題**：
- 章程第 1 節要求 main 保持零產品耦合。這個 skill 從頭到尾綁死 stock-desk 的路徑、port、DB 檔名與 `dev-up.bat` 的內部細節。
- 這是既有的違規，不是這次才出現。
- 也是它會和產品規則脫節的根因：產品的規則變了（接線、R 系列），main 上的 skill 不會跟著變。

**〔裁示〕接線後的改法**（從 origin/main 開 `chore/agent-local-run-*`）：
1. **只保留轉介，不帶產品細節**：
   - 觸發時（CEO 說啟動、重啟、跑起來），coordinator 不臨場輸出任何指令；
   - 去找該產品分支 README 裡「給 CEO 的操作」那一段（RC-435 甲案的單一 CEO 文件），只轉述那一段裡風控定稿的字面；
   - 產品若有常設的「不要自己重新啟動」規則，或有進行中的紀錄，重新執行的請求一律走該產品的定稿請求（stock-desk 是 R1、R2、R3、R3-0、R3-0C、RC-447），照送出條件辦。
2. **明寫禁止事項，逐條可檢查：**
   - 不得對 CEO 輸出手動啟動、`git` 指令、`taskkill`、`kill`、`lsof`、備份或還原步驟、`.env` 或環境變數的檢查與修改；
   - 不得叫 CEO 判讀視窗訊息。
3. **產品工程內容搬回產品分支**：手動指令、DB 檔表、`dev-up.bat` 的內部說明，放到 product 上的工程文件（例如主機部署手冊或 README 的工程段，受 RC-430 保護），由 devops-sre 在 product 分支另一個 commit 處理。不放 main。
4. **frontmatter `description`**：把「必用：輸出下列固定指令」換成觸發後要先做的「查產品的 CEO 操作段，以及有沒有常設限制」。
5. **時點：P0。**
   - 理由：skill 依 description 在新會話自動觸發；新會話不一定讀過追蹤清單裡的過渡規則。只靠過渡規則，擋不住下一個會話照著 skill 輸出 `git pull` 或 `taskkill`。
   - 所以要合併進 main，並由 product `merge origin/main` 同步，兩者都在接線 PR 合併前完成。
   - 流程：qa-reviewer 審查（含 Codex 第二意見）。skill 沒有對 CEO 的字面，不必送風控；但要確認沒有抄入任何對 CEO 的字面。
   - `scripts/validate_agents.py` 不檢查 skill，所以沒有 CI 保護；skill 名稱與章程第 5 節的清單不變。
6. 「產品分支 README 的 CEO 操作段」還沒寫好之前（RC-434 起草中），轉介目標可以暫時寫成「coordinator 依該產品追蹤清單中的常設規則」，CEO 操作段落地後再改指向。這一句由 qa 確認不含產品路徑。

**〔事實與規則〕改好之前 coordinator 要遵守的：**
- 不得對 CEO 輸出 local-run 的任何指令或步驟，包括第 15～29、56～96、108～113、118～120 行，以及第 48 行的 `.env` 檢查。還原段本來就已依 RC-434 禁止轉述。
- CEO 要「啟動」，而 stock-desk 沒有開著：這是 CEO 原有的習慣（雙擊 `dev-up.bat`，README 第 12～15 行；RC-428 檔頭、RC-433 告知都寫明不變）。coordinator 只能用風控已定稿、提到 `dev-up.bat` 的句子回覆；沒有合適的定稿句時，先送風控。
- CEO 要「重啟」，或 stock-desk 已經開著還要再執行：
  - 屬於重新啟動。coordinator 不輸出指令，照實記錄，當天轉 devops-sre；
  - 若 CEO 同時回報了畫面行，照 R3-0、R3-0C 與 RC-438 辦；
  - 若是 coordinator 要請 CEO 重新執行，只能用 R1、R2、R3 及其送出條件。
  - **CEO 主動要求重啟時要怎麼回覆，目前沒有定稿字面，要送風控新訂。**
- 不得在預檢到登記完成之間，以及任何「不得執行 `dev-up.bat`」的期間，回答啟動或重啟的方式（RC-438 (g) 的精神）。
- 我在 `/home/user/AICompany` 讀到的 local-run，可能是 product 合併過來的副本，和 origin/main 是否相同沒有查證。改的時候以 origin/main 為準。

### 3. 根因與防止再發（〔建議〕，不是這次的閘門）

- 風控三次各自發現，根因是 CEO 文件沒有登錄處：
  - `work/` 裡讀者含 CEO 的文件，散在根目錄、`dispatch/`、`research/`、`reviews/`；
  - 沒有統一的狀態欄（現行、已不適用、一次性已結束）。
- 建議：
  - (a) 凡讀者含 CEO 的文件，檔頭第一個清單項要有「狀態」行；
  - (b) README 的 CEO 操作段是唯一現行的 CEO 操作文件（RC-435），其他文件一律標為過程文件，只能連到它；
  - (c) qa 在只改文件的 PR 核對 (a)。
- 這是員工線的流程變更（`docs/handoff-protocol.md` 或 creative-lead 的定義），要另外從 `chore/agent-*` 提，由 CEO 核可。不擋接線。

## 驗證

- 普查方法：
  - `work/`：以 Glob 查檔名含 `CEO`、`操作說明`、`檢查手冊`、`產品說明`、`執行指令`、`手動步驟`；以 Grep 查檔頭「讀者」「對象」「給 CEO」（排除 `reviews/`）。
  - `apps/stock-desk/` 下非依賴目錄的 `*.md`：共 4 份。
  - `local-run`。
  - 以上各檔再用 Grep 查任務指定的動作字樣。
- 全文讀過：警示手冊（201 行）、R2 操作說明（61 行）、兩份退役通知、`local-run`（121 行）。
- 只讀了部分：
  - 產品說明第 1～20、395～524 行，加 Grep；
  - R2 備用第 1～60 行，加 Grep；
  - 帳外缺日草稿第 1～30 行，加 Grep；
  - 數據核實第 1～15 行，加 Grep；
  - N-152、N-172、財務 spike、Phase 1 探測、N-208 只用 Grep；
  - README 與 `backend/README.md` 只用 Grep；
  - 我先前的報告讀了第 1～466 行（共 579 行）；
  - 追蹤清單只讀了第 700～702 行。
- 沒有涵蓋：
  - `work/reviews/` 內以「給 CEO」為節名、但檔名不含關鍵字的文件（只抓到 N-208）；
  - `work/copy/`、`work/prd/`；
  - `.claude/worktrees/` 內的副本，例如 11-17 正式登記操作說明（它由登記退役通知涵蓋）；
  - 其他 skill（例如 `release-flow`、`e2e-fallback`）會不會對 CEO 輸出指令。
  - 幾次全 repo 的 Glob、Grep 逾時，所以結果可能不完整。
- 沒有查證：
  - 一次性指令是否都已執行完；R2 第二次執行的時程；`gap-check.bat` 的狀態；
  - 這些 `work/` 檔在哪個分支被追蹤；
  - `local-run` 在 origin/main 上的版本；
  - `uv run` 在 CEO 的 uv 版本上的同步行為；
  - 改規則 YAML 之後 `dev-up.bat` 會不會 `[STOP]`（依第 69～72 行推論）。

## 下一步

1. coordinator：
   - 追蹤清單加上本報告的 P0、P1、P2 表；
   - 把 `local-run` 的過渡規則（第二件第 2 點末）記成常設規則，直到改版合併並同步；
   - 把下面「送風控」各項轉過去。
2. devops-sre：
   - 確認 P0 三份 `work/` 檔所在的分支；
   - 套用定稿（只改文件的 PR）；
   - 開 `chore/agent-local-run-*` 改 `local-run`；
   - 把產品工程內容搬到 product 的工程文件（另一個 commit，守 RC-430）。
3. qa-reviewer（含 Codex）：核對 P0 文件 PR 的 diff 範圍；審 `local-run` 改版，確認沒有產品路徑、沒有對 CEO 的字面，而且禁止事項逐條都在。
4. creative-lead：起草第一件第 4 點的檔頭與警示；用同一句型起草警示手冊與產品說明的標註與警示；P2 的批次標註句可以之後再起草。

---

# 彙整

**送風控：**
1. 族群手冊的檔頭區塊、第 5 行、5 處警示（creative-lead 起草後送）。
2. 要不要比照 RC-433 告知 CEO（事實見第一件 1. 末）。
3. 把 RC-448 的過渡規則延伸到警示評估手冊、產品說明的 3 個段落、R2 備用手動步驟，以及 P2 的一次性指令文件。
4. 警示評估手冊、產品說明的標註與警示字面。
5. 新訂一項：CEO 主動要求「重啟」時 coordinator 的回覆字面。
6. 新訂一項：日後若需要 CEO 補 FinMind token（改 `.env` 再重新執行）的一次性請求字面。不急，等真的需要時再訂。
7. R2 第二次執行通知、帳外缺日比對定稿：發出前對齊 R 系列。
8. 「卡片沒資料不影響預測紀錄」這一類句子要不要出現在任何 CEO 文件。

**要 creative-lead 起草：** 上面第 1、4 項；之後第 5、6 項的初稿；P2 的批次標註句。

**要 devops-sre 做：**
- 確認分支；套用 P0 文件 PR；
- `chore/agent-local-run-*` 改版，以及 product 同步；
- 產品工程內容搬到 product 的工程文件；
- 第一件 3. 的 (a) 唯讀狀態一鍵檔設計（日後有需要時）；
- 和 data-engineer 確認 CEO 本機的 D0 與暖身狀態（不經 CEO）。

**要 tech-architect 自己做：**
- 查證預測紀錄的大盤 resolver 是否用 FinMind（關係到 token 和額度）；
- 核對 N-208 第 2 部分恢復前的改寫。

**要 dev-lead 做：** N-208 第 2 部分恢復前的改寫（P1）。

**必須由 CEO 決定的事：** 沒有。

# 相關路徑

- `/home/user/AICompany/work/stock-desk-族群動能無資料-檢查手冊-2026-10-03.md`
- `/home/user/AICompany/work/stock-desk-警示評估載入失敗-檢查手冊-2026-10-07.md`
- `/home/user/AICompany/work/stock-desk-產品說明.md`
- `/home/user/AICompany/.claude/skills/local-run/SKILL.md`
- `/home/user/AICompany/apps/stock-desk/dev-up.bat`（第 26～27、71、91～105、110、165、187、283～302 行）
- `/home/user/AICompany/.claude/worktrees/agent-a9629b70c09d9bd6a/apps/stock-desk/dev-up.bat`（第 191 行）
- `/home/user/AICompany/apps/stock-desk/README.md`（第 309 行）、`/home/user/AICompany/apps/stock-desk/backend/README.md`（第 109～116、142 行）
- `/home/user/AICompany/work/dispatch/2026-11-13-R2探測操作說明-CEO.md`、`/home/user/AICompany/work/dispatch/2026-11-13-R2探測手動步驟-備用.md`
- `/home/user/AICompany/work/dispatch/2026-11-19-帳外缺日比對操作說明-CEO-草稿.md`
- `/home/user/AICompany/work/reviews/2026-11-08-N208手動換標的操作說明-dev-lead.md`
- `/home/user/AICompany/work/research/N152-未收盤殘留檢測-執行指令-2026-10-26.md`、`/home/user/AICompany/work/research/N172-重複指令偵測-執行指令-2026-10-31.md`、`/home/user/AICompany/work/research/財務資料源spike-執行指令-2026-11-01.md`、`/home/user/AICompany/work/research/2026-10-16-Phase1資料源探測指令-CEO本機代跑.md`、`/home/user/AICompany/work/stock-desk-數據核實操作說明.md`
- `/home/user/AICompany/work/.gitignore`（第 88、98 行）
- `/home/user/AICompany/work/reviews/2026-11-21-手冊標註單項確認與重啟請求修訂與Cancelled處理RC442至RC455-風控.md`
- `/home/user/AICompany/work/reviews/2026-11-21-手冊改判處理路徑與重啟請求R3-RC427至RC441-風控.md`
- `/home/user/AICompany/work/reviews/2026-11-21-README備份還原事實與下游ADR連動與ADR-0012補充一草稿-tech-architect.md`

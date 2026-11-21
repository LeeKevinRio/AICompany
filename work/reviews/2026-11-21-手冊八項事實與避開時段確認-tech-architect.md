# 風控 RC-415 的 8 項事實、手冊另外三處問題、R1／R2「避開時段」的確認

- 審查者：tech-architect
- 日期：2026-11-21
- 轉存：coordinator，逐字轉存 subagent 最終回報

---

# tech-architect 補充回報：風控 RC-415 的 8 項事實、手冊另外三處問題、R1／R2 的「避開時段」

這份是前一份回報的補件，併入其中「第二件」。前一份第一件（確認書複核）的結論不變。這次另外讀了風控 RC-407～RC-421 的判定與 B 草稿第 109～111 行。全程唯讀，沒有讀 `.env`，沒有碰 `backend/data/`。行號都以接線版工作樹 `agent-a352324c9d164984b` 為準，除非另外註明。

---

# 第二件（補）：RC-415 的 8 項事實、手冊另外三處問題

## 本次結論

1. 8 項事實逐項列在下面。最影響改寫的有三點：
   - 第 3 項：另外兩個路徑變數不會造成任何拒絕，也不是預測紀錄的輸入。
   - 第 5 項：程式並不檢查是用什麼方式啟動的。B 第 1 點是「我們支援的條件」，不是程式強制的條件。手冊第 1 節照現有字面做，會被拒絕；所以**整個第 1 節都要處理**，coordinator 要重新檢視 RC-341。
   - 第 7 項：帳本固定在 `backend\data\stock-desk.db`；資料位置由 tech-architect 決定。
2. 風控指出的另外三處同類問題，加上第 4 步的 attestation，事實都成立，見第 2 節。
3. 我收回前一份的一個建議：前一份建議把 0.2／0.3 節的改寫放進 `dev-up.bat` 改字分支。改照風控 RC-416：另開一個只改文件的 PR，在接線 PR 合併之前合併。
4. 更正前一份的一處未查證：指數的強制重抓只走 yfinance，**和 `FINMIND_API_TOKEN` 無關**（見第 8 項）。

## 各部門回報（tech-architect）

### 1. RC-415 的 8 項事實

**事實 1：用 `dev-up.bat` 啟動時，三顆 DB 的位置；API 與 scheduler 是否解析到同一組**
- 是 `apps\stock-desk\backend\data\` 底下的三個檔：
  - `stock-desk.db`（`cache.py` 28、101 行）
  - `stock-desk-market.db`（`market_panel.py` 95、241 行）
  - `stock-desk-research.db`（研究 `store.py` 46、126～127 行）
- 三者都是相對於程序工作目錄的路徑。`dev-up.bat` 啟動 backend（150 行）和 scheduler（166 行）之前，都先 `cd /d "%BACKEND_DIR%"`；`BACKEND_DIR` 定義在第 30 行。
- 研究 DB 只有在執行研究程式時才會開，API 永遠不開。
- API 與 scheduler 會解析到同一組：
  - 兩者從同一個父程序啟動，工作目錄相同，環境也相同（同樣繼承 `UV_ENV_FILE`）。
  - 例外：兩個視窗啟動之間，Windows 層的變數被改過；或有人在個別視窗裡另外設了變數。
  - 這是依程式結構推得的結論，沒有在 Windows 上實際驗證。

**事實 2：`.env` 的實際讀取方式**
- `dev-up.bat` 讀的是 `apps\stock-desk\.env`：
  - 第 94 行定出路徑；檔案存在時，第 96 行設 `UV_ENV_FILE`；
  - backend 與 scheduler 經 `uv run` 載入。`app/env_status.py` 第 5 行的說明也這樣寫。
- **`backend\.env` 沒有被任何程式或一鍵檔讀取：**
  - `app/` 沒有 dotenv；
  - 會讀 `.env` 的程式只有登記與驗收類工具（`claims.py` 405 行、`cg2_register.py` 865 行、`pipeline_acceptance_real.py` 648 行、`r2_first_run.py` 288 行），讀的都是 `<backend>/../.env`，也就是 `apps\stock-desk\.env`，而且只找 `STOCK_DESK_DB_PATH` 這個名稱；
  - 讀 `backend\.env` 的只有手冊自己的 PowerShell 片段。
- `dev-up.bat` 第 27 行註解「Windows 已設的變數優先於檔案」：**未查證。** 這取決於 uv 的行為，我手上沒有 uv 的原始碼或文件可以確認。

**事實 3：`STOCK_DESK_MARKET_DB_PATH`、`STOCK_DESK_RESEARCH_DB_PATH`**
- **在預測紀錄、狀態報告、登記預檢中，都沒有任何拒絕條件。**
  - scheduler 只看 `STOCK_DESK_DB_PATH`（`scheduler.py` 699 行）；
  - 狀態報告只看 `STOCK_DESK_DB_PATH`（`forecast_status.py` 224 行）；
  - 登記的 bootstrap 與 preflight 也只看它（`claims.py` 403～406 行、`cg2_register.py` 863～865 行）。
  - 這兩個變數名稱，只出現在各自的模組（`market_panel.py`、研究 `store.py`）和 scripts 裡。
- **記錄期間改這兩個變數，不會改變預測紀錄的輸入**：
  - `app/forecast`、`app/outlook`、`app/dirdef` 都沒有引用 `market_panel` 或 research（Grep 零筆）；
  - 預測的指數資料來自主 DB 的 `price_bars_cache`（`deps.py` 58～65、178～189 行）；
  - 這兩個變數也都不在 `code_digest` 涵蓋範圍內。
  - 這是依 import 的 Grep 推得的結論，沒有逐一追蹤每一條呼叫路徑。
- 它們影響的是族群動能：市場 DB 是 ADR-0012 的資料，手冊 4.1 寫它「完全無法重建」。
  - API 與 scheduler、或兩種啟動方式之間設定不一致時，市場 DB 會分成兩份。
- （tech-architect 建議）手冊不再建議顯式指定這兩個變數，改為「不需要設定」：
  - 顯式指定對預測紀錄沒有好處；
  - 在 `dev-up.bat` 路徑下，預設值已經保證 API 與 scheduler 用同一組檔；
  - 多設一個變數，就多一個兩邊設定不一致的機會。

**事實 4：完全不設路徑變數時**
- 三顆 DB 都落在「工作目錄\data\」下，在 `dev-up.bat` 路徑下就是 `backend\data\`（事實 1）。
- 預測紀錄的目標核對通過的條件：主 DB 解析後等於 `<backend>/data/stock-desk.db`，而且是存在的一般檔案（`scheduler.py` 701～708 行）。
- 狀態報告固定讀同一個檔（`forecast_status.py` 7、161 行）。
- 登記的目標也是同一個檔（`claims.py` 407～410 行）。
- 所以四者一致。**這是唯一一種讓一般功能、記錄、狀態報告、登記都指向同一個檔的設定。**

**事實 5：手冊第 1 節的手動啟動路徑會不會記錄；和 B 第 1 點是否一致**
- 程式不檢查是用哪一種方式啟動的。scheduler 只核對兩件事：程序環境裡沒有 `STOCK_DESK_DB_PATH`；主 DB 是 `<backend>/data/stock-desk.db`。
  - 手冊第 6 步是先 `cd apps\stock-desk\backend` 再啟動，所以工作目錄是對的。
  - 只要那個視窗裡沒有這個變數，**手動啟動也會記錄**。
- **照手冊現有字面做，不會記錄：**
  - 0.3 節的 `$env:STOCK_DESK_DB_PATH = …`，或在 `backend\.env` 寫了這個變數、再用第 3 步的片段載入，都會讓變數進入 scheduler 的程序環境，每次被拒絕（`scheduler.py` 699～700、785 行）。
  - 0.3 節的路徑本身也不是 `<backend>/data/stock-desk.db`。
- 和 B 第 1 點「只有在本機用 `dev-up.bat` 啟動，而且沒有設定 `STOCK_DESK_DB_PATH` 時，才會記錄」比對：
  - 技術上不完全一致。B 比程式嚴：沒有設變數的手動啟動，程式照樣記錄。
  - 但方向是「CEO 以為不會記錄的情形，其實會記錄」，不會讓 CEO 誤以為正在記錄。
  - （tech-architect 判斷）B 不需要改字。B 第 1 點應該讀為「我們支援的記錄條件」，不是程式強制的條件。
  - 手冊第 1 節（第 3、5、6 步）、第 3 節（更新與重啟）、第 5 節（依賴檔案 log 的監控）都和 B 指定的啟動方式不同。**手冊的第 1 節要整節處理**：在預測記錄期間標為不適用於 CEO，或改由團隊引導；不能只改 0.2、0.3。
  - RC-341「手冊仍有效」的判斷，請 coordinator 重新檢視。
- 混用的事實：
  - 手動啟動的 scheduler 開著時執行 `dev-up.bat`，會被當成舊 scheduler，提示後以 `taskkill /F /T` 結束（`dev-up.bat` 277～302 行，比對的條件是命令列含有 `app.scheduler`）。
  - 手動啟動的 API 佔著 port 8000 時，也會出現提示（244～269 行）。

**事實 6：空值 `STOCK_DESK_DB_PATH=`**
- **寫在 `apps\stock-desk\.env`：**
  - 登記的 bootstrap 與 preflight：**一定拒絕**。它們把檔案當文字讀，只要有一行符合 `^\s*STOCK_DESK_DB_PATH\s*=` 就拒絕，空值也算（`claims.py` 291、385～390 行；`cg2_register.py` 103、650 行）。以 `#` 開頭的註解行不算。
  - scheduler：取決於 uv 會不會把空值放進程序環境，**未查證**。
    - 會放進去：每次拒絕（699 行，看的是名稱存不存在，不看值）。另外 `resolve_db_path` 會得到 `Path("")`，也就是 `.`，一般功能推論開不了主 DB（沒有實際執行）。
    - 不會放進去：執行時沒有影響，但登記照樣拒絕。
  - 狀態報告：沒有影響。它的 `.bat` 清空了 `UV_ENV_FILE`，本身也不讀 `.env`。
- **設成 Windows 環境變數：** 在 Windows 上，`set X=`、`$env:X=""`、`SetEnvironmentVariable(…, "")` 一般的效果是刪掉變數，不會留下空值。所以實務上空值的環境變數應該不會出現（依 Windows 與 .NET 的一般行為推論，未實機驗證）。
  - 萬一真的存在：scheduler 拒絕；狀態報告 STOP（`forecast_status.py` 11 行，空值也算）；登記拒絕（`claims.py` 403 行）。
- 沒有查證的寫法：`export STOCK_DESK_DB_PATH=`、大小寫不同的名稱。登記的比對抓不到這兩種寫法，uv 會不會照樣載入，沒有查證。

**事實 7：已經設過、而且指向非預設檔時，由誰決定、技術上怎麼收拾**
- 決定權：
  - **資料位置由 tech-architect 決定。** 依據：ADR-0030 補充九第 3 點末款「要在其他位置記錄，屬 D-8 第 3 點與 F-8 的 DB 路徑改變，須先修訂本 ADR」；補充九第 2 點（主 DB 整檔還原或替換後再 bootstrap，須先修訂 ADR）。
  - 對 CEO 的字面由風控定。
  - 涉及取捨，例如要保留哪一份持倉與設定時，由 CEO 決定。
  - devops-sre 只在決定之後執行技術步驟。CEO 不自己處理。
- 技術事實：
  - 帳本固定在 `backend\data\stock-desk.db`：bootstrap 只寫這個檔（`claims.py` 407 行），scheduler 也只記錄到這個檔。所以**任何處置都不能替換或移走這個檔**，替換就是 F-8。
  - 變數指向別的檔時，API 與 scheduler 的持倉、設定、警示、價格快取都在那個檔裡；預設檔裡則只有帳本與登記當時存在的內容。
  - 拿掉變數，一般功能就會改用預設檔，可能看不到原本的持倉與設定。
  - 把非預設檔搬到預設位置，等於替換帳本所在的檔案，不可以。
  - 兩檔合併不是現成的功能，屬於要另外設計的資料遷移。
- 時點證據：登記成功本身證明，登記當時 Windows 層的變數（以 preflight 視窗看得到的為準）和 `apps\stock-desk\.env` 都沒有設這個變數，而且預設檔存在（`cg2_register.py` 861～866 行）。但它不涵蓋 `backend\.env`、個別 PowerShell 視窗，也不涵蓋登記之後的變更。

**事實 8：0.2 表中其餘變數放在 `apps\stock-desk\.env`，用 `dev-up.bat` 啟動時是否就會生效**
- 會，對 backend 與 scheduler 生效。前提是 uv 照 `UV_ENV_FILE` 載入，這是依 `dev-up.bat` 第 92 行與 `env_status.py` 第 5 行的說明，沒有實機驗證。
- 會生效的變數：`FINMIND_API_TOKEN`（`finmind.py` 71 行）、`ALERT_DISCORD_WEBHOOK_URL`、`ALERT_TELEGRAM_BOT_TOKEN`、`ALERT_TELEGRAM_CHAT_ID`（`notify.py` 38～40 行）、`SCHEDULER_DATA_INTERVAL_MINUTES`、`SCHEDULER_ALERT_INTERVAL_MINUTES`（`scheduler.py` 166～167 行，只有 scheduler 會用）。
- 前端不會拿到這些變數；狀態報告等一鍵檔也刻意不帶。
- CEO 看得到的佐證：backend 與 scheduler 視窗啟動時，各印一行「FINMIND token／Alpha Vantage key／Discord webhook／Telegram：已設定或未設定」，不印值（`env_status.py` 35～53 行；`dev-up.bat` 99 行）。
- 手冊表格沒有列 `ALPHA_VANTAGE_API_KEY`（`alpha_vantage.py` 147 行），但程式會讀它。要不要補進表格，由 creative-lead 判斷。
- 同一個變數同時設在 Windows 層和 `.env` 時，哪一個生效，見事實 2，未查證。
- **更正前一份**：`FINMIND_API_TOKEN` 和預測紀錄無關。指數的服務只用 yfinance 一個來源（`deps.py` 178～189 行；`yfinance.py` 413 行寫明它是「指數序列唯一的 adapter」）。

### 2. 風控指出的另外三處，加上第 4 步（product 現行手冊的行號）

- **第 1 節第 3 步（115～118 行）在 PowerShell 載入 `.env`：** 載入的是 `backend\.env`，沒有任何程式或一鍵檔會讀這個檔，載入的效果只在那一個視窗裡。用 `dev-up.bat` 啟動時，這一步完全用不到；檔案裡若有 `STOCK_DESK_DB_PATH`，從那個視窗啟動的 scheduler 就會被拒絕。**事實上可以整段刪除。**
- **第 6 步的「務必也載入同一份環境變數」（142 行）：** scheduler 不需要任何路徑變數，需要的只是 FinMind、警示、排程間隔這幾個變數。用 `dev-up.bat` 啟動時，backend 與 scheduler 自動會拿到同一份。
- **0.2 節的 `'User'`／`'Machine'` 永久設定（56～58 行）：** 就是前一份的情形 (i)。之後啟動的每一個程序都看得到，包括 `dev-up.bat` 的兩個視窗、狀態報告（會 STOP）、登記預檢（會拒絕），重開機也還在。用這個方式設 `STOCK_DESK_DB_PATH` 的後果最嚴重，而且不會自己消失。
- **第 1 節第 4 步（120～132 行），以及第 3 節第 3 步（211～212 行），叫 CEO 自己執行 attestation 並排除問題：** 事實成立，和「不得請 CEO 自己執行 attestation」衝突。
  - attestation 要求工作樹連未追蹤檔都沒有；`dev-up.bat` 路徑本來就沒有這一步，這是已知缺口，依前一份裁示的限期 (b) 處理。
  - （tech-architect 建議）從給 CEO 的段落中移除，改寫成「由團隊處理」一類的字面，字面歸風控；RC-420 的告知照原計畫。

## 驗證
- 讀過：
  - 風控判定的 42～117、200～269 行；
  - B 草稿第 109～111 行；
  - `env_status.py` 全文；
  - `http.py` 1～200 行；
  - `deps.py` 58～65、150～189 行；
  - `yfinance.py` 410～434 行；
  - `recorder.py` 190～209、355～473、530～559、660～676 行；
  - `store.py` 1290～1305 行。
- Grep：
  - 各模組的環境變數名稱；
  - `app/forecast`、`app/outlook`、`app/dirdef`、`app/services` 對 `market_panel`、research 的引用（只有 `pit_snapshot`、`sector_board` 兩檔有）；
  - backend 所有 `.py` 裡出現 `.env` 的位置。
- 沒有查證：
  - uv 對 `UV_ENV_FILE` 的空值、`export`、優先順序的處理；
  - Windows 上的空值行為；
  - `.env.example` 的內容（權限擋下）；
  - 在 Windows 上實機執行。

## 下一步
1. creative-lead：依上面的事實，起草 0.2、0.3 節，加上第 1 節第 3、4、6 步、第 3 節第 3 步，以及手冊開頭的適用範圍；送風控。照 RC-416，另開一個只改文件的 PR，在接線 PR 合併之前合併。
2. coordinator：重新檢視 RC-341「手冊仍有效」的判斷；照 RC-417 辦理過渡期。
3. devops-sre：回答 `.env.example` 裡有沒有 `STOCK_DESK_DB_PATH` 這一行。
4. 沒有需要 CEO 決定的事。

---

# 第三件：R1／R2 的「請避開平日晚上 10 點到 11 點半之間執行」

## 本次結論

**照原句可用。**（tech-architect 確認）
- 這段時間涵蓋 22:10、23:10 兩次執行在正常與一般失敗情形下可能進行的時段。開始前留了 10 分鐘，23:10 之後留了 20 分鐘。
- 22:10 之前的啟動補跑時段，以及其他時段，都不必避開。
- 理由如下。要說清楚的一點：23:10 那一次「一定」在 23:30 前結束，程式上沒有保證，因為沒有整次執行的逾時。但真的超過 23:30 還沒結束的執行，屬於卡住（原因 E），那正是 R2 要用重啟解決的情形。

## 各部門回報（tech-architect）

### (a) `taskkill` 結束正在執行的 `forecast_record` 時

- **會留下一筆沒有 end 列的執行。**
  - `forecast_run` 在 `begin_run` 時就寫入（`recorder.py` 363 行）；end 列要等 `_run` 結束、或 except 區塊執行時才寫（370～392 行）。
  - `taskkill /F`（`dev-up.bat` 295 行）是強制結束，except 區塊和 SIGTERM 的處理都來不及執行。
  - 前提成立時才會發生：正在跑的必須是接線後的 scheduler。接線前的 scheduler 沒有這個 job，什麼都不會留下。
- **對紀錄本身的影響：**
  - 快照與紀錄是在同一個 transaction 寫入的（444～462 行）。
  - 在 commit 之前被結束：SQLite 依 WAL 回復，那一晚什麼都沒寫入。
  - 在 commit 之後、`end_run` 之前被結束：紀錄會留下，只是沒有 end 列。
  - 推論不會造成資料庫損毀（這是 SQLite 的既有保證，沒有在 Windows 上實測）。
- **對 F-2 的影響：**
  - 新 scheduler 會在啟動後 3 分鐘補跑一次（`scheduler.py` 926 行）。重啟時刻加 3 分鐘落在 22:13 之後時，不屬於不補跑的時段（727～741 行），所以會補跑。
  - 補跑寫入的是當晚 T 日的紀錄，t0 不早於 22:10，依補充十第 3 點會是 `late = 0`，或者在已經寫入時記為 `no_new_session`。
  - 所以**一般情形下不會讓 F-2 的 `a` 增加**。但如果補跑本身失敗（例如強制重抓失敗），那一晚就可能漏記，和平常的單次失敗一樣。
- **對心跳比對的影響：**
  - 「沒有 end 列=」會加 1，coordinator 記成「中斷的執行」（補充十三第 2 點 (f)），當天通知 devops-sre。
  - 依確認書 (六)，單次的「沒有 end 列」增加由 devops-sre 處理並記錄，不轉 tech-architect，也不需要 L2。
  - 補跑之後，最近一次執行就換成新的那一筆，不會形成「中斷後沒有後續執行」。
- **對 D-5 第 6 點與 `gate_closed` 的影響：**
  - 一筆沒有 end 列的執行不會被當成「通過的執行」；它會被當成「前一次」來比對，比對的是 `code_digest` 和 `runtime_json`（`recorder.py` 537～548 行）。
  - 程式沒有改變時，它不會觸發重算。
  - 如果 R1 那次的 `git pull` 拉進了新的程式，重算本來就會發生，和有沒有被結束無關。
- **對 `verify` 的影響：** 已經 commit 的紀錄，會和其他紀錄一樣被核對。`verify` 本身怎麼處理沒有 end 列的執行，我沒有讀到相關程式，**未查證**；我判斷影響很小，因為紀錄的內容不依賴 end 列。
- **結論：** 被結束是 fail-closed 的事件，代價是一筆「中斷的執行」紀錄，加上一次由 devops-sre 處理、不升級的通知。這句話的作用是減少不必要的通知，不是為了保護紀錄，所以時段可以採保守的寫法。

### (b) 時段是否涵蓋兩次執行

- **開始時刻**：只在週一至週五（台北）的 22:10、23:10（`scheduler.py` 222～224、712～724 行）。不分是否休市，平日都會執行，所以「平日」的寫法正確。週末不執行。
- **持續時間**：沒有整次執行的逾時。但每一個外部等待都有上限：
  - 強制重抓只走 yfinance，一次 HTTP 請求（`deps.py` 178～189 行）。每次嘗試連線上限 2 秒、讀取上限 8 秒，失敗重試 1 次，中間等 1 秒（`http.py` 85、111～123 行）；用戶端另有 1 秒的節流（`yfinance.py` 422 行）。一般失敗的情形大約 21 秒以內。
    - 注意：httpx 的讀取逾時是指「兩段資料之間的等待」，不是整次請求的總時間。對方以極慢的速度一點一點送資料時，可以超過這個時間。
  - recorder 最多呼叫兩次 `load_benchmark`（`recorder.py` 420～422 行）。這條路徑是快取優先，剛重抓過時多半直接讀快取；最壞情形同上。
  - SQLite 每一次操作最多等 5 秒（`cache.py` 36 行等）。
  - D-5 第 6 點的重算：只在程式或環境改變時才做，耗時隨紀錄筆數增加；前幾年的紀錄只有數百筆，**沒有實測**。
  - `git rev-parse` 有 10 秒的逾時（`recorder.py` 202 行），但它只在模組載入時執行一次，不是每次執行都跑。
  - 推論：正常或一般失敗的執行，大約在一兩分鐘內結束。沒有實測。
- **所以「晚上 10 點到 11 點半」**涵蓋 22:10 和 23:10 兩次執行的正常與一般失敗時段，前後都有餘裕。23:10 那一次「一定」在 23:30 前結束：**程式上沒有保證**；超過的就是卡住（E），而卡住正是 R2 要請 CEO 重新執行的理由，所以不影響這句話的用途。
- **22:10 之前的啟動補跑時段，不必避開**：
  - 舊 scheduler 的啟動補跑，只發生在它自己啟動後 3 分鐘，不會和 CEO 這一次的重新執行重疊。
  - 新 scheduler 的啟動補跑，是由這一次重新執行觸發的，而 R1、R2 已經要求「出現 `Done.` 之前不執行其他一鍵檔」。
  - 補充十第 3 點的不補跑時段（平日 13:30～22:10），只決定新 scheduler 要不要補跑，不會讓重新執行有任何風險。
- **其他 job**（不在本題範圍，只列事實）：族群動能的擷取與判定在平日 17～21 點的整點過後（:30、:45、:50）執行。被結束時，新 scheduler 啟動當下會再跑一次擷取，啟動後再跑一次判定（`scheduler.py` 893、907 行），所以不需要把避開時段往前延伸。股利同步沒有啟動補跑，錯過的話等下一個時點。這些屬於 ADR-0012、ADR-0016 的範圍，我沒有再深入查證。

## 驗證
- 讀過：
  - `scheduler.py` 222～229、712～741、837～936 行；
  - `recorder.py` 355～473、530～559 行；
  - `http.py` 1～200 行；
  - `deps.py` 150～189 行；
  - `yfinance.py` 410～434 行；
  - `dev-up.bat` 277～302 行；
  - 風控 RC-408、RC-409。
- 沒有查證：
  - 實際的執行耗時；
  - `verify` 怎麼處理沒有 end 列的執行；
  - `taskkill` 在 Windows 上中斷 SQLite 寫入的實際結果；
  - 其他 job 被結束時的完整後果。

## 下一步
1. coordinator：R1、R2 的「避開時段」那一句照原句使用；把本確認作為 RC-408 要求的書面確認存檔，列入追蹤清單（接線 PR 合併前置）。
2. devops-sre：確認書 (五) 第 4 點依 RC-412 改為引用 R1、R2 的條件；如有需要，在 (二) 的「中斷的執行」補一句：「重新執行 `dev-up.bat` 時剛好遇到執行中的那一次，也會留下沒有 end 列的一筆，可由啟動補跑接手」。和前一份的 R1～R8 放在同一個補正 commit。
3. 沒有需要 CEO 決定的事。

---

相關路徑：
- `/home/user/AICompany/work/reviews/2026-11-21-重啟請求定稿與手冊0.2及0.3節與attestation告知RC407至RC421-風控.md`
- `/home/user/AICompany/work/dispatch/2026-11-20-預測記錄條件通知-CEO-草稿.md`
- `/home/user/AICompany/apps/stock-desk/docs/族群動能-主機部署手冊.md`
- `/home/user/AICompany/apps/stock-desk/dev-up.bat`
- `/home/user/AICompany/.claude/worktrees/agent-a352324c9d164984b/apps/stock-desk/backend/app/scheduler.py`
- `/home/user/AICompany/.claude/worktrees/agent-a352324c9d164984b/apps/stock-desk/backend/app/forecast/recorder.py`
- `/home/user/AICompany/.claude/worktrees/agent-a352324c9d164984b/apps/stock-desk/backend/app/forecast/claims.py`
- `/home/user/AICompany/.claude/worktrees/agent-a352324c9d164984b/apps/stock-desk/backend/app/env_status.py`
- `/home/user/AICompany/.claude/worktrees/agent-a352324c9d164984b/apps/stock-desk/backend/app/data/http.py`
- `/home/user/AICompany/.claude/worktrees/agent-a352324c9d164984b/apps/stock-desk/backend/app/api/deps.py`
- `/home/user/AICompany/.claude/worktrees/agent-a352324c9d164984b/apps/stock-desk/backend/app/data/cache.py`
- `/home/user/AICompany/.claude/worktrees/agent-a352324c9d164984b/apps/stock-desk/backend/app/data/market_panel.py`
- `/home/user/AICompany/.claude/worktrees/agent-a352324c9d164984b/apps/stock-desk/backend/app/research/sector_biased/store.py`
- `/home/user/AICompany/.claude/worktrees/agent-a352324c9d164984b/apps/stock-desk/backend/scripts/cg2_register.py`
- `/home/user/AICompany/.claude/worktrees/agent-ab5f1bf75d430b1de/apps/stock-desk/backend/scripts/forecast_status.py`

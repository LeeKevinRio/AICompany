# stock-desk「警示評估：標的載入失敗」本機檢查手冊

- 日期：2026-10-07（週三）
- 撰寫：devops-sre（只讀程式碼與文件，未改程式、未連網、未啟動服務、未讀 `.env`、未開啟任何 DB）
- 讀者：CEO（Windows，用 `apps\stock-desk\dev-up.bat` 啟動），以及接手排查的工程同事
- 適用分支：`product/stock-desk`
- 對應任務單：`work/dispatch/2026-10-06-任務單-單一標的收盤價不合法不中斷整輪警示檢查.md`（devops-sre 評估已落地於 ab1a703）
- 狀態：log 字串與層級由程式碼逐字取得（`app/alerts/engine.py`、`app/scheduler.py`）；「backend 視窗的 log 長相」已在沙盒用 Python 標準 logging 驗過行為；**CEO 本機實際輸出尚未實測**。

---

## 0. 一句話（給 CEO）

警示每輪檢查時，若某一個標的的資料「載入時出錯」，系統現在**只略過那個標的的規則，其他標的照常檢查**，並在 log 留一行 WARNING。
你平常不用看；要確認「警示有沒有默默漏檢」時，在 scheduler 視窗（或 log）搜 `failed_symbols=` 與 `snapshot load failed`。
**連續好幾輪都不是 0，或所有標的都失敗，才需要處理**（第 3、4 節）。

---

## 1. 兩種 log：格式、層級、出現位置

### 1.1 每標的 WARNING（「snapshot load failed」）

| 項目 | 內容 |
| --- | --- |
| 逐字 | `alert evaluation: snapshot load failed (market=<市場>, <例外類別>); <N> rule(s) skipped this tick` |
| 範例 | `alert evaluation: snapshot load failed (market=TW, ValueError); 2 rule(s) skipped this tick` |
| 層級 | WARNING |
| 次數 | 每個「載入失敗的標的」一行（一輪內同一標的只載入一次、不重試），後面接 Python traceback（`exc_info`） |
| 內容 | 只有市場、例外類別名、被略過的規則數 `N`。**刻意不含標的代號與規則 id**（與啟動時的診斷行一致）；細節看 traceback |
| 來源 | `app/alerts/engine.py::_load_isolated`，logger 名稱 `app.alerts.engine` |
| 該標的的後果 | 這一輪它的每條規則都被標為「略過」（沿用該規則類型原本的略過理由），下一輪會重新嘗試載入 |

### 1.2 排程摘要行（只在 scheduler）

| 項目 | 內容 |
| --- | --- |
| 逐字 | `alert evaluation: <E> rules evaluated, <F> fired, failed_symbols=<K>` |
| 層級 | `K > 0` 時 **WARNING**；`K = 0` 時 INFO |
| 次數 | 每輪警示評估一行（預設每 60 分鐘，由設定頁或環境變數 `SCHEDULER_ALERT_INTERVAL_MINUTES` 決定；啟動時 `scheduler jobs registered: ... alert_evaluation every <n> min ...` 那行會印實際值） |
| 欄位 | `E`＝啟用中的規則總數（**含**被略過的）；`F`＝這輪實際觸發的事件數；`K`＝載入失敗的**標的**數（以標的計，不是以規則計） |
| 來源 | `app/scheduler.py::evaluate_alerts_tick`（約 L411-419），logger 名稱 `scheduler` |
| 另一行 | 設定頁關閉警示時只印 `alert evaluation: disabled in settings; skipping tick`，不會有摘要行 |

### 1.3 出現位置對照

| 觸發來源 | 每標的 WARNING | 摘要行 | 看哪裡 |
| --- | --- | --- | --- |
| scheduler 排程（定時） | 有 | **有** | scheduler 視窗／容器 |
| `POST /api/alerts/evaluate`（畫面「立即檢查」） | 有（同一個 `evaluate_alerts` 引擎） | **沒有**（API 回應也**不帶** `load_failures`，只在 log） | backend 視窗／容器 |

兩個注意：

1. **backend 視窗的 WARNING 長相不同**：`app/main.py` 沒有設定 logging，uvicorn 也只設定自己的 logger，所以 `app.alerts.engine` 的 WARNING 走 Python 預設的備援輸出（stderr），**只有訊息本身，沒有時間與等級前綴**，後面接 traceback；INFO 不會出現。搜字串仍然搜得到，但要靠上下文判斷時間。scheduler 則有 `時間 等級 訊息` 前綴（`app/scheduler.py::main` 的 `basicConfig`）。
2. API 回應裡看得到「被略過」的規則（`outcomes[].status="skipped"` 與 `reason`），但那個理由是該規則類型**既有**的略過理由，跟「正常沒資料所以略過」長得一樣，**無法**單靠回應分辨是否為載入失敗。要確認就是看 log。

---

## 2. 手動檢查指令

### 2.1 Docker Compose（`apps/stock-desk/compose.yaml`，服務名：`backend`、`scheduler`、`frontend`）

在 `apps/stock-desk` 目錄執行。PowerShell 沒有 grep，Windows 請用 2.2 的 `Select-String` 寫法；以下 bash 寫法適用 WSL／Git Bash／Linux／macOS。

```bash
cd apps/stock-desk

# 1) Per-tick summary lines that reported failures (scheduler only)
docker compose logs scheduler | grep 'failed_symbols=[1-9]'

# 2) Every per-symbol warning (scheduler + backend both can emit it)
docker compose logs scheduler backend | grep 'snapshot load failed'

# 3) Last 24h of summaries, to read the trend (clean ticks are INFO and show failed_symbols=0)
docker compose logs --since 24h scheduler | grep 'alert evaluation:'

# 4) The traceback behind a warning: 25 lines after the match (exception class + frames)
docker compose logs scheduler | grep -A25 'snapshot load failed'

# 5) Is the scheduler even running, and how often does it tick?
docker compose ps scheduler
docker compose logs scheduler | grep 'scheduler jobs registered'
```

### 2.2 本機直跑（`dev-up.bat` / `dev-up.sh`，沒有 compose）

`dev-up.bat` 為 backend、scheduler、frontend 各開一個 `cmd /k` 視窗，**不把 log 寫到檔案**；視窗被關掉 log 就沒了。三種做法：

1. 直接在 `stock-desk scheduler` 視窗往上捲，找 `failed_symbols=` 或 `snapshot load failed`（視窗內可按 `Ctrl+F`）。
2. 想留下 log 供事後 grep：先關掉現有 scheduler 視窗（兩個 scheduler 會讓每則警示發兩次，**不要同時跑兩個**），在 PowerShell 於 backend 目錄重開並 tee 到檔案：

```powershell
cd <repo>\apps\stock-desk\backend
$env:PYTHONUTF8 = '1'
# 2>&1: Python logging writes to stderr. Tee-Object keeps the window output too.
uv run python -m app.scheduler 2>&1 | Tee-Object -FilePath $env:TEMP\stock-desk-scheduler.log
```

   之後在**另一個** PowerShell 視窗查（Windows 的 grep 等價）：

```powershell
Select-String -Path $env:TEMP\stock-desk-scheduler.log -Pattern 'failed_symbols=[1-9]'
Select-String -Path $env:TEMP\stock-desk-scheduler.log -Pattern 'snapshot load failed' -Context 0,25
# Count of failing ticks vs. all ticks
(Select-String -Path $env:TEMP\stock-desk-scheduler.log -Pattern 'failed_symbols=[1-9]').Count
(Select-String -Path $env:TEMP\stock-desk-scheduler.log -Pattern 'alert evaluation: \d+ rules evaluated').Count
```

   `dev-up.sh`（Linux／macOS／WSL）等價寫法：把 scheduler 那一行的輸出導到檔案或用 `| tee /tmp/stock-desk-scheduler.log`，再用 `grep 'failed_symbols=[1-9]' /tmp/stock-desk-scheduler.log`。
3. 只想立刻驗一次、不等整點：畫面「立即檢查」或
   `curl.exe -s -X POST http://localhost:8000/api/alerts/evaluate`，然後看 **backend 視窗**有沒有 `snapshot load failed`（此路徑沒有摘要行，API 回應也沒有失敗標的數）。

> 這份手冊的指令都是**唯讀**（看 log、讀 API 回應），不改任何資料。`POST /api/alerts/evaluate` 會真的跑一輪評估並寫入觸發事件（與按畫面按鈕相同），但不發 webhook；冷卻時間內不會重複產生事件。

### 2.3 判讀

先認清一個限制：**摘要行只有「失敗標的數 K」，沒有「標的總數」**，每標的 WARNING 也不含代號。所以用下面兩個可得到的數字判斷：

| 觀察 | 判讀 |
| --- | --- |
| `failed_symbols=0`（INFO） | 該輪乾淨。「略過」若仍出現，是資料本身沒有（例如沒有收盤價），與本手冊無關 |
| 偶發單輪 `failed_symbols=1~2`，下一輪回 0 | 暫時性（資料源瞬斷、單一標的資料異常剛好被修）。記一筆即可，不必處理 |
| **連續 N 輪都 > 0**（建議門檻：**連續 3 輪**，預設間隔下約 3 小時；間隔改過就依實際間隔換算） | 不是暫時性。看 traceback 的例外類別（第 3 節）。若連續輪次的 WARNING 出現的 **市場與例外類別都相同**，通常是同一個標的或同一個原因反覆失敗 |
| 同一輪裡，所有 WARNING 的 `N rule(s) skipped` **加總 ＝ 摘要行的 `rules evaluated`** | **所有規則都被略過＝所有標的都失敗**。這是**系統性故障**（資料庫打不開／被鎖、資料層整體壞掉、依賴的服務全掛、剛上線的程式 bug），不是個別標的問題。立刻進第 3 節，視為優先處理 |
| 一輪裡 WARNING 行數很多，且例外類別相同（例如全是 `OperationalError`） | 同上，系統性。同一類別對應單一根因的機率高 |
| 有 `failed_symbols=` 摘要行但一輪都沒有 `snapshot load failed` | 不應發生（兩者同源）。可能是 log 被截斷或你只看了其中一個服務；兩個服務都查 |
| 連 `alert evaluation:` 行都沒有 | 不是本問題：scheduler 沒跑、警示被設定關閉、或當機。回到 `docker compose ps scheduler`／`dev-up.bat` 的 `[OK] scheduler running` 狀態行 |

補充：SQLite 單檔、backend 與 scheduler 共用同一個檔（compose 為 volume `stock-desk-data`、本機直跑為 `backend\data\stock-desk.db`），資料庫被鎖或路徑不一致是系統性故障的常見來源，可對照 `work/stock-desk-族群動能無資料-檢查手冊-2026-10-03.md` 的步驟 3（兩個 DB 檔在哪裡）。

---

## 3. 遇到時的處置順序

不含任何祕密；**不要把 `.env` 內容、token、完整 traceback 中若出現的金鑰貼給任何人**（traceback 一般不含，但貼之前自行掃一遍）。

### 步驟 1：確認範圍（1 分鐘）

1. 取最近一輪的摘要行：`E`（規則數）、`K`（失敗標的數）。
2. 加總同一輪各 WARNING 的 `N rule(s) skipped`，與 `E` 比。相等＝系統性，跳到步驟 3 的「系統性」列；不等＝個別標的，照單項處理。
3. 確認是不是剛更新程式後才開始（`git log -1 --format=%h` 對照第一次出現的時間）。剛更新後才出現，優先懷疑程式 bug。

### 步驟 2：看 traceback 的例外類別（最後一行 `XxxError: ...`）

下表是**依程式結構推得的啟發式**，不是窮舉；以實際 traceback 為準。資料源的「預期失敗」（網路逾時、HTTP 錯誤）依 `app/data/interface.py` 的約定本來就**不該丟例外**，會以狀態值回傳；所以能走到這裡的例外，多半是「非預期」，傾向資料內容異常或程式 bug。

| 例外類別（常見） | 傾向 | 先做什麼 | 轉給 |
| --- | --- | --- | --- |
| `sqlite3.OperationalError`（`database is locked`／`unable to open database file`／`no such table`） | 資料層：DB 被鎖、路徑錯、schema 沒遷移 | 確認只有一個 scheduler；確認 backend 與 scheduler 的 `STOCK_DESK_DB_PATH` 同一個檔；compose 下確認 volume 掛載正常 | devops-sre；schema 問題給 data-engineer |
| `ValueError`（訊息含 `must be positive`／`must be non-negative`／`timezone-aware`／`must not be blank`） | 資料內容不合法（例如收盤價為 0 或負、時間沒帶時區、空欄位）進了資料模型驗證 | 記下市場；請工程用 traceback 找出標的。**這正是這次修正要隔離的那一類**，單一標的出現屬預期降級 | data-engineer（資料品質）；若 traceback 落在 `app/alerts/` 或 `app/advice/` 則給 dev-lead |
| `pydantic.ValidationError` | 同上，資料或設定欄位格式不符 | 同上 | data-engineer／dev-lead |
| `KeyError`／`AttributeError`／`TypeError`／`IndexError`（frame 落在 `app/alerts/`、`app/advice/`、`app/portfolio/` 等產品程式） | 程式 bug（多半是新版本引入或遇到沒想過的資料形狀） | 記下第一次出現時間與當時的 commit；**不要自行改程式** | dev-lead（必要時附 qa-automation 補回歸測試） |
| 與匯率／估值相關的例外（traceback 的 frame 出現 `fx`、`valuator`、`valuation`，且市場多為 US 等外幣標的） | 匯率或估值這一段（外幣標的換算成本幣時） | 看是否只有外幣市場的標的失敗、台股標的正常；若是，問題收斂在匯率資料來源 | data-engineer；估值邏輯給 dev-lead |
| `httpx.*`／`requests.*`／`TimeoutError`／`ConnectionError`（frame 落在 `app/data/providers/`） | 資料源連線。**不該走到這裡**（預期失敗應回傳狀態值而非丟例外），本身就是缺陷 | 先確認本機網路與資料源是否可達；再當成缺陷回報 | data-engineer |
| `MemoryError`／`RecursionError` 或整輪所有標的同一例外且 frame 在共用程式 | 系統性程式 bug 或環境問題 | 重啟 scheduler 看是否重現；重現則停止處置、整理 traceback | dev-lead；環境給 devops-sre |

### 步驟 3：依範圍選動作

| 情況 | 動作 |
| --- | --- |
| 個別標的、單輪或偶發 | 記一筆，不處理。下一輪自動重試 |
| 個別標的、連續 ≥ 3 輪 | 把 traceback（**去掉個人持倉資訊**）與市場交給上表負責人。**暫時不用刪規則**：該標的的規則只是被略過，不會誤觸發，不影響其他標的 |
| 系統性（加總相等或例外類別一致且量大） | 1) 先看 DB 路徑／鎖／磁碟空間（步驟 2 第一列）；2) 看是否剛更新程式，是則請 dev-lead 評估回滾到上一個 commit；3) 重啟 scheduler 一次（compose：`docker compose restart scheduler`；本機：關 scheduler 視窗後重開 dev-up）；4) 仍重現就升給 dev-lead 與 CEO，並說明「警示目前整輪被略過、不會有通知」 |
| 懷疑自己漏掉了該來的警示 | 以「沒有警示」不等於「沒有觸發條件」看待：先查摘要行是否有失敗，再用畫面「立即檢查」確認；**不要**把 log 當成投資判斷依據，警示只是提醒 |

回報格式建議（貼給工程）：`第一次出現時間、連續幾輪、K 與 E、例外類別、市場、是否剛更新程式（commit 短 hash）`。**不要附 `.env`、token、持倉數量／金額。**

---

## 4. 自動化告警選項與成本（簡述，升 CEO 決定）

目前**沒有任何自動通知**：失敗只會躺在 log，要人去看。若 CEO 想要「失敗就推播」，選項如下（皆未實作，成本為估計，以實作前評估為準）：

| 選項 | 做法 | 成本 | 取捨 |
| --- | --- | --- | --- |
| A. 維持現況＋每週手動看一次 | 照本手冊 2.1／2.2 跑一次 grep | 0 元；約 2 分鐘／次 | 最簡單；發現延遲最長（至多一週），可能長期漏檢 |
| B. 程式內重用既有 webhook 通道 | 摘要行為 WARNING（`failed_symbols>0`，尤其連續 N 輪）時，由 scheduler 對**已設定的** Discord／Telegram webhook 發一則維運通知 | 0 元（不需新服務）；dev-lead 約 0.5～1 天（需先 tech-architect 決定是否沿用警示通知通道，另需**風控審通知文案**，因為屬面向使用者的字面）| 成本最低、最貼近需求；通知通道與投資警示共用，要避免與警示混淆 |
| C. 外部心跳／死人開關（如 healthchecks.io 類服務） | scheduler 每輪成功就 ping 一次；沒 ping 就通知 | 免費方案通常夠個人使用（付費約每月數美元，**以實作前查證為準**）；需要對外連線與一個外部服務的 URL（視為祕密，走環境變數）| 能抓到「scheduler 整個掛掉」，但抓不到「有跑但全部標的失敗」除非把 `failed_symbols` 一併回報 |
| D. 日誌集中＋告警（Loki／Grafana 或雲端 log 服務） | 收 compose 日誌，對 `failed_symbols=[1-9]` 設規則 | 自架：0 元授權但要維運主機與設定，約 1～2 天；雲端託管：通常有免費額度，超過要付費（**需另行查證方案價格**）| 對單人本機工具明顯過重，不建議 |

建議（devops-sre 意見，不是決定）：先 A，等實際遇到過才升級；若 CEO 要自動化，選 B（成本最低、不引入新依賴）。**B、C 都會對外連線，D 與 C 若涉及付費或新增外部服務，需 CEO 明確同意後才進行；任何通知文案需 risk-compliance-officer 審查。**

---

## 5. 附：相關程式與文件位置

| 項目 | 位置 |
| --- | --- |
| 每標的隔離與 WARNING | `apps/stock-desk/backend/app/alerts/engine.py`（`evaluate_alerts`、`_load_isolated`、`EvaluationResult.load_failures`） |
| 排程摘要行 | `apps/stock-desk/backend/app/scheduler.py`（`evaluate_alerts_tick`） |
| 手動評估 API | `apps/stock-desk/backend/app/api/alerts.py`（`POST /api/alerts/evaluate`） |
| 服務名與共用 volume | `apps/stock-desk/compose.yaml`（`backend`／`scheduler`／`frontend`、`stock-desk-data`） |
| 本機啟動 | `apps/stock-desk/dev-up.bat`、`dev-up.sh` |
| 同類手冊（格式來源） | `work/stock-desk-族群動能無資料-檢查手冊-2026-10-03.md` |

---

## 6. 回滾

本手冊只新增這一個文件，並在 `work/.gitignore` 加一行放行；未改程式、設定、資料。要退回：刪除本檔並移除該行 `!stock-desk-警示評估載入失敗-檢查手冊-2026-10-07.md`。

# stock-desk「族群動能排行」無資料：根因分析與本機檢查手冊

- 日期：2026-10-03（週六）
- 撰寫：devops-sre（只讀程式碼與文件，未改程式、未讀 `.env`、未開啟 `backend/data/*.db`）
- 讀者：CEO（Windows，用 `apps\stock-desk\dev-up.bat` 啟動）
- 適用分支：`product/stock-desk`
- 狀態：**根因由程式碼推得，尚未在 CEO 本機實測**。第 3 節的檢查就是用來確認到底是哪一個。

---

## 0. 一句話（給 CEO）

族群排行要靠「平日收盤後成功抓一次全市場資料」才會有第一份榜單，而且要先做過一次「歷史暖身」；
你的電腦目前很可能還沒有這兩樣東西，今天又是週六（系統週末抓不到資料），所以卡片說「沒有資料日期」。
這不是畫面壞掉，也不是網路日曆服務連不上，是本機資料庫裡還沒有可用的榜單。

---

## 1. 畫面兩句話各對應什麼

兩句都是同一個條件的兩個表現：**資料庫裡沒有「可用的 board（榜單）」**。不是兩個獨立故障。

| 畫面文字 | 出處 | 觸發條件 |
| --- | --- | --- |
| 「本次無法向交易日曆確認資料是否過舊…」 | 前端 `frontend/app/components/SectorMomentumCard.tsx`：`calendarUnconfirmed = data.data.trading_days_behind === null`；字串在 `frontend/app/lib/adviceWording.ts` 的 `AS_OF_CALENDAR_UNCONFIRMED_STATEMENT` | 後端 `app/api/sectors.py::_data_meta`（L473）在 `board is None` 時回 `trading_days_behind = null` |
| 「本卡未取得全市場收盤資料的日期…本次不呈現族群動能排行」 | 後端 `app/api/sectors.py::build_sector_momentum`（約 L227～L266、L255-266）：`board is None or card is None` → `InsufficientChecks(data_as_of_known=False)` → `insufficient_reason = "as_of_unknown"`；字串在 `app/api/sectors_wording.py` 的 `AS_OF_UNKNOWN_MAIN` | 同上：沒有 board |

補充兩點，避免誤會：

1. 「交易日曆」不是外部網路服務。它是用市場 DB 裡「有 ok 收盤資料的日期」自己湊出來的日曆（`app/data/market_panel.py::ok_sessions`），所以沒資料就沒日曆，兩句同時出現。
2. board 還有一種「有但被忽略」的情況：`usable_board()`（`app/api/sectors.py` L374，風控 R-5）會把 `market_expected_count <= 0` 的 board 當成沒有。此時後端視窗會印
   `sector card: board <id> has no expected stock; ignored`。

反推：若 CEO 的電腦曾經成功有過週五的 board，週六打開卡片應該**不會**出這兩句（週六只是比週五多 0 個交易日，不算過舊）。
所以週末無資料本身不是原因，真正的原因是「從來沒有可用 board」。這回答了「為何沒有上週五的 board」：因為它從來沒被產生過。

---

## 2. 為什麼會沒有 board：資料怎麼流（程式碼依據）

```
scheduler 視窗（app/scheduler.py）
  pit_snapshot_capture（啟動即跑一次；平日 17:30 / 19:30 / 21:30 Asia/Taipei）
    └─ capture_pit_snapshot() -> capture_once() 寫「市場 DB」pit_snapshot_runs
    └─ 抓完立刻接 refresh_sector_board()
  sector_board_refresh（啟動後 SECTOR_REFRESH_STARTUP_DELAY = 2 分鐘；平日 17:45 / 19:45 / 21:45）
    └─ SectorBoardService.refresh()：取市場 DB 最近一個 ok 的 bars 日 t，算 board，寫「主 DB」sector_board
backend 視窗（app/api/sectors.py）
  只讀主 DB 最新 board，沒有 board（或 expected 為 0）就顯示你看到的畫面
```

兩個關卡，**缺一不可**：

**關卡 1：要有「通過自證交易日」的成功擷取**（`app/data/providers/twse_snapshot.py::_certify_session`）
- TWSE 的 `STOCK_DAY_ALL` 不帶日期。系統把「現在的台北日期」當候選交易日，再向 FinMind 抽 3 檔（含 2330）比對當天收盤價與成交量，**完全相符才承認**，否則四種資料全部記 `failed`、`session_date` 為空。
- 所以以下情況擷取**必定失敗**：
  - 週六、週日、休市日啟動（候選日沒有交易，FinMind 查無資料）。**今天週六就是這種**。
  - 平日收盤後、FinMind 還沒更新前（程式排在 17:30 起，就是為了等它）。
  - 平日開盤中或盤前（candidate=今天，但今天的資料還沒出）。
  - **scheduler 的環境沒有 `FINMIND_API_TOKEN`**：`FinMindAdapter.get_daily_bars` 沒 token 直接回 unavailable，等同查無資料，**任何一天都失敗**。
- `dev-up.bat` 不會設 token，程式也**不會讀 `.env`**（`app/` 底下沒有 dotenv；`.env` 只對 docker compose 有效）。token 只有在「啟動 dev-up 的那個環境」本來就有時才會被子視窗繼承（見 `dev-up.bat` L130 的註解）。從檔案總管雙擊 dev-up，只會帶到 Windows 使用者／系統層級的環境變數。
- 失敗時 scheduler 視窗只會看到 `status=failed`，**看不到原因**；原因只寫在市場 DB 的 `pit_snapshot_runs.reason`（第 3 節 SQL 會印出來）。這是診斷上的缺口，見第 6 節。

**關卡 2：要有至少 60 個交易日的歷史，board 才有成分股**（`app/sectors/universe.py::eligible`）
- 成分股必須同時滿足：上市滿 60 個「看得到的交易日」（`min_listing_sessions = 60`），以及最近 20 日裡至少 18 日有成交且成交值中位數 ≥ 1,000 萬（`_liquid`）。
- 一個全新資料庫只靠每日擷取，要累積約 60 個交易日（約 12 週）才會有第一檔合格成分股。ADR-0012 D-3 的設計是靠「暖身 CLI」一次補 80 個交易日以上的歷史：
  `uv run python -m app.services.pit_snapshot --warmup --since 2026-06-01`（需要 `FINMIND_API_TOKEN`）。
- 沒暖身時，即使擷取成功，board 也會被算成 `market_expected_count = 0`，被 R-5 忽略，畫面一樣是同兩句。
- **暖身只能在 D0 之前做**（D0 ＝ 四種資料第一次在同一天都 ok 的日子）。第一次四種資料都成功的擷取就會產生 D0，之後 `--warmup` 會拒絕執行（`WarmupAfterD0Error`）。**所以順序是先暖身、再讓平日擷取成功**。這一點在 `apps/stock-desk/docs/族群動能-主機部署手冊.md` 第 2 節有寫，但 `dev-up.bat` 沒有任何提示。

其他不會擋 board、但之後會遇到的事：
- 方法版本沒登記時 scheduler 視窗會印 `sector-rel-v1.0-L5-H5 is not registered; run register-version first`。這只影響 D0 登記與判定關卡，不影響 board 產生。
- board 出現後，卡片先會變成別的「資料不足」原因：每個最近 5 個交易日都要有各自成功的除權息預告擷取（`app/sectors/coverage.py::ex_dividend_feed_covered`），所以排行要等到**連續 5 個交易日都成功擷取**才會出現（休市日順延）。這是設計行為，不是故障。

---

## 3. 逐步檢查（照順序做，每步都標了該看什麼）

下列指令預設在 PowerShell。`<repo>` 換成你的 repo 路徑。

### 步驟 1：scheduler 視窗有沒有在跑

1. `dev-up.bat` 最後應有一行：`[OK]   scheduler running - window 'stock-desk scheduler'`。若是 `[FAIL] scheduler not running`，直接看該視窗的錯誤訊息。
2. 工作列應有三個視窗：`stock-desk backend`、`stock-desk scheduler`、`stock-desk frontend`。**沒有 scheduler 視窗**＝你用的是舊版 `dev-up.bat`（舊版只開 backend 與 frontend；現行版本是 commit `518b1e5` 起才會開 scheduler）。處置：關掉全部視窗，在 repo 內 `git pull --ff-only origin product/stock-desk` 後重跑 `dev-up.bat`。
3. 用指令確認（任何 PowerShell 視窗）：

```powershell
Get-CimInstance Win32_Process | Where-Object { $_.Name -like 'python*' -and $_.CommandLine -like '*app.scheduler*' } | Select-Object ProcessId, CreationDate
```

有輸出＝scheduler 在跑，`CreationDate` 是它的啟動時間；沒輸出＝沒在跑。

### 步驟 2：scheduler 視窗的 log 字樣（逐字）

視窗用 `cmd /k` 開著，往上捲就有。**dev-up 不會把 log 寫到檔案，視窗若被關掉就看不到**，直接跳步驟 4。
log 格式為 `時間 等級 訊息`。依序應該看到：

| 順序 | 逐字訊息（節錄開頭即可比對） | 意義 |
| --- | --- | --- |
| 1 | `scheduler jobs registered: data_refresh at start-up then ...` 結尾為 `... pit_snapshot_capture and sector_board_refresh on weekdays at 17,19,21 (Asia/Taipei)` | 兩個族群排程已登記。沒有這行或結尾沒有 `pit_snapshot_capture` ＝跑的是舊版程式 |
| 2 | `scheduler heartbeat 2026-...` | scheduler 已啟動 |
| 3 | 4 行 `pit capture <日期或None> <kind>: status=<...> rows=<n> skipped_already_ok=<...>`，kind 依序為 `listing`、`classification`、`dividend_announce`、`bars` | 啟動時那一次擷取的結果 |
| 4 | `sector board refresh: session=<日期或None> board=<id或None> stats=None notes=<...>` | 擷取後接著算 board 的結果 |

判讀：

| 看到什麼 | 代表 | 下一步 |
| --- | --- | --- |
| `pit capture None listing: status=failed rows=0 skipped_already_ok=False`（4 行都是 `None` 和 `failed`） | 交易日無法自證，四種資料全失敗 | 看同一段是否有 `FinMind adapter unavailable: FINMIND_API_TOKEN environment variable is not set`（→ 補 token，見第 4 節 A），否則到步驟 4 SQL 看 `reason` |
| `pit capture 2026-10-02 bars: status=ok rows=...`（日期是真的日期，四行皆 ok） | 擷取成功 | 看第 4 項 notes |
| `pit capture <日期> bars: status=partial` | 收盤資料覆蓋率低於 0.98，不算 ok | 步驟 4 SQL 看 `reason` 的覆蓋率；回報 dev-lead |
| `notes=no_ok_bars_run` | 市場 DB 完全沒有 ok 的收盤資料 | 關卡 1 沒過 |
| `notes=no_visible_bars` | 有 ok 日期，但當天看得到的資料為空 | 通常是暖身資料晚於該日才寫入（不是錯誤），等下個交易日擷取 |
| `notes=board_unchanged` | board 已存在且沒變 | 正常 |
| `board=TW-...`（有 board_id）且 backend 視窗印 `has no expected stock; ignored` | board 有，但成分股為 0 | 關卡 2 沒過：沒暖身，見第 4 節 B |
| `sector-rel-v1.0-L5-H5 is not registered; run register-version first` | 版本未登記 | 與本問題無關，之後處理 |
| `scheduled job pit_snapshot_capture failed; it stays scheduled` 加 traceback | 擷取本身丟例外（網路、TWSE 403／解析失敗等） | 把整段 traceback 截圖給工程團隊 |
| `sector board refresh after capture failed; the capture stands` 加 traceback | 擷取成功但算 board 出錯 | 同上截圖 |

（board_id 格式為 `TW-<日期>-<時間戳>`。）

### 步驟 3：兩個 DB 檔在哪裡、多大

程式沒有設環境變數時，路徑是**相對於啟動時的工作目錄**：`dev-up.bat` 讓 backend 與 scheduler 都在 `apps\stock-desk\backend` 啟動，所以兩邊預設讀同一組：

- 主 DB：`apps\stock-desk\backend\data\stock-desk.db`（`STOCK_DESK_DB_PATH`）
- 市場 DB：`apps\stock-desk\backend\data\stock-desk-market.db`（`STOCK_DESK_MARKET_DB_PATH`）

`dev-up.bat` **沒有**設這兩個變數。只有在你另外設了使用者／系統環境變數時，路徑才會不同；若 backend 與 scheduler 看到不同的值（例如其中一個從你手動設過變數的 PowerShell 啟動），就會「排程寫的、API 讀不到」，這是 `backend/README.md` 提過的老問題。

```powershell
# What this PowerShell session sees (empty = default under backend\data)
$env:STOCK_DESK_DB_PATH; $env:STOCK_DESK_MARKET_DB_PATH
# What a freshly double-clicked dev-up.bat would inherit (User level)
[Environment]::GetEnvironmentVariable('STOCK_DESK_DB_PATH','User'); [Environment]::GetEnvironmentVariable('STOCK_DESK_MARKET_DB_PATH','User')
# Is the FinMind token visible to a freshly double-clicked dev-up.bat? Prints True/False only, never the value
[bool][Environment]::GetEnvironmentVariable('FINMIND_API_TOKEN','User') -or [bool][Environment]::GetEnvironmentVariable('FINMIND_API_TOKEN','Machine')
```

若第三條印 `False`，scheduler 幾乎確定沒有 token（除非你是從已設好 `$env:FINMIND_API_TOKEN` 的 PowerShell 內執行 dev-up）。

### 步驟 4：唯讀 SQL（看擷取結果與 board）

只讀、不會改任何東西（用 SQLite `mode=ro` 開啟）。**一定要在 `apps\stock-desk\backend` 目錄下執行**，路徑才會與 scheduler 一致。整段貼上：

```powershell
cd <repo>\apps\stock-desk\backend
$env:PYTHONUTF8 = '1'
@'
import os, sqlite3
from pathlib import Path

def open_ro(env, default):
    p = Path(os.environ.get(env, default)).resolve()
    size = p.stat().st_size if p.exists() else None
    print("==", env, "->", p, "| exists:", p.exists(), "| bytes:", size)
    if not p.exists():
        return None
    return sqlite3.connect(p.as_uri() + "?mode=ro", uri=True)

def show(conn, title, sql):
    print("--", title)
    try:
        rows = conn.execute(sql).fetchall()
    except Exception as exc:
        print("   ERROR:", exc)
        return
    if not rows:
        print("   (no rows)")
    for r in rows:
        print("  ", r)

m = open_ro("STOCK_DESK_MARKET_DB_PATH", "./data/stock-desk-market.db")
if m:
    show(m, "A. latest 12 live capture runs (run_id, kind, session_date, recorded_at_utc, source, status, rows, expected, reason)",
         "SELECT run_id, kind, session_date, recorded_at, source, status, row_count, expected_count, substr(reason,1,200) "
         "FROM pit_snapshot_runs WHERE source <> 'finmind_warmup' ORDER BY run_id DESC LIMIT 12")
    show(m, "B. totals by source/kind/status (source, kind, status, runs, first_session, last_session)",
         "SELECT source, kind, status, COUNT(*), MIN(session_date), MAX(session_date) FROM pit_snapshot_runs GROUP BY 1,2,3 ORDER BY 1,2,3")
    show(m, "C. distinct sessions with an ok bars run (count, first, last) - board needs >= 60 (about 80 recommended)",
         "SELECT COUNT(DISTINCT session_date), MIN(session_date), MAX(session_date) FROM pit_snapshot_runs WHERE kind='bars' AND status='ok' AND session_date IS NOT NULL")
    show(m, "D. D0 (first session where all 4 kinds are ok; None = not reached yet, warm-up still allowed)",
         "SELECT MIN(session_date) FROM (SELECT session_date FROM pit_snapshot_runs WHERE kind='bars' AND status='ok' AND session_date IS NOT NULL "
         "INTERSECT SELECT session_date FROM pit_snapshot_runs WHERE kind='listing' AND status='ok' AND session_date IS NOT NULL "
         "INTERSECT SELECT session_date FROM pit_snapshot_runs WHERE kind='classification' AND status='ok' AND session_date IS NOT NULL "
         "INTERSECT SELECT session_date FROM pit_snapshot_runs WHERE kind='dividend_announce' AND status='ok' AND session_date IS NOT NULL)")
    m.close()

d = open_ro("STOCK_DESK_DB_PATH", "./data/stock-desk.db")
if d:
    show(d, "E. latest 5 boards (board_id, data_as_of, computed_at, data_source, expected_count, missing_count) - expected_count 0 = ignored by the card",
         "SELECT board_id, data_as_of, computed_at, data_source, market_expected_count, market_missing_count "
         "FROM sector_board ORDER BY data_as_of DESC, computed_at DESC LIMIT 5")
    show(d, "F. method registry (method_version, accumulation_start)",
         "SELECT method_version, accumulation_start FROM sector_method_registry")
    d.close()
'@ | uv run python -
```

（已在沙盒用暫存 DB 驗過此腳本可執行；沙盒沒有 CEO 的真實資料，所以輸出判讀是依程式邏輯推得。）
若 PowerShell 貼上多行有問題，把 `@'` 到 `'@` 中間的內容存成 `%TEMP%\diag.py`，改執行 `uv run python $env:TEMP\diag.py`（仍要在 backend 目錄）。

也可以直接問 API 現在回什麼（backend 要在跑）：

```powershell
curl.exe -s "http://localhost:8000/api/sectors/momentum?market=TW"
```

看 `"insufficient_reason":"as_of_unknown"` 與 `"data_as_of":null`，與畫面一致。

**輸出判讀（對照表）**

| 結果 | 根因 | 下一步 |
| --- | --- | --- |
| 開頭 `exists: False`（市場 DB） | 檔案不在預期位置：scheduler 沒跑過，或路徑指到別處 | 回步驟 1、3 |
| 市場 DB 檔案存在但 A 無資料（no rows） | scheduler 從未成功進到擷取 | 回步驟 1、2，看視窗 traceback |
| A 全部是 `session_date=None` 且 `status=failed` | 交易日無法自證。`reason` 欄會寫原因：`FinMind 交叉比對失敗：2330 於候選交易日 ... 查無資料` ＝週末／休市／盤前／沒 token；`連線失敗`／`回傳 HTTP 403`／`回應非 JSON` ＝TWSE 端問題 | 週末：等平日。平日收盤後仍失敗：檢查 token（第 4 節 A）；TWSE 403／連線：稍後重試，持續失敗請回報 |
| A 有真實日期且 `bars` 為 `partial` | 覆蓋率 < 0.98 | 回報 dev-lead（`reason` 有分子分母） |
| C 的天數 < 60，E 無資料或 `expected_count = 0` | 關卡 2：沒有足夠歷史 | 若 D 為 None：做暖身（第 4 節 B）。若 D 已有日期：見第 4 節 D |
| C ≥ 60，E 有資料且 `expected_count > 0`，但畫面仍無 | 前後端讀到不同 DB，或 backend 沒重啟／讀舊檔 | 比對步驟 3 兩個視窗的環境變數；重啟 backend |
| E 有 `expected_count > 0` 的 board，畫面已不再出現這兩句 | 問題已解，之後只剩「除權息預告需連續 5 個交易日」的等待 | 等待即可 |

---

## 4. 立即可做的補救

### A. 讓 scheduler 拿得到 FinMind token（最常見）

token 是你自己的祕密，**不要貼給任何人、不要寫進 repo**。兩種做法擇一（要重啟 dev-up 才生效）：

```powershell
# 1) Persist at user level (new windows inherit it). Replace the placeholder yourself.
setx FINMIND_API_TOKEN "<your token>"
# then close ALL stock-desk windows and run dev-up.bat again from a NEW window

# 2) Or only for this session: set it, then launch dev-up from the SAME PowerShell window
$env:FINMIND_API_TOKEN = "<your token>"
cmd /c <repo>\apps\stock-desk\dev-up.bat
```

重啟後，scheduler 視窗應不再出現 `FinMind adapter unavailable`。

### B. 暖身歷史（只能做一次、必須在 D0 之前）

先確認步驟 4 的 D 為 `None`（還沒到 D0），再在**已設好 token** 的視窗執行：

```powershell
cd <repo>\apps\stock-desk\backend
uv run python -m app.services.pit_snapshot --warmup --since 2026-06-01
```

- 逐檔抓 FinMind，約千檔以上，有節流，要跑一段時間（部署手冊估數十分鐘到數小時）。**中途斷線或 Ctrl-C，重跑同一條指令即可續跑**（已完成的會顯示 already done）。
- 結尾會印 `warm-up: N done, M failed, K already done`；有 failed 就重跑直到 0。FinMind 若回 HTTP 402／429（額度用完），**等約一小時再重跑**（此額度說明未經本次查證，以 FinMind 實際回應為準）。
- 此命令只寫市場 DB，不動持倉、設定等其他資料。
- 暖身寫入的時間戳是「執行當下」，所以它只對**暖身之後的交易日**可見：今天（週六）做完，第一份可用 board 會出現在下週一（2026-10-05）收盤後的擷取。**無法回頭補出上週五的 board**（ADR-0012 C-11／D-3：不回填）。

### C. 手動觸發一次擷取＋重算 board（不必等排程）

這兩條都在 `apps\stock-desk\backend` 目錄執行，並且與 scheduler 讀寫**同一組 DB**（同樣的預設路徑規則；若你有設 `STOCK_DESK_*_DB_PATH`，要在同樣環境變數下執行）。

```powershell
cd <repo>\apps\stock-desk\backend
# 1) Capture once and print a per-kind summary (does NOT build the board). Needs FINMIND_API_TOKEN.
uv run python -m app.services.pit_snapshot
# 2) Capture + build the board in one go, with log lines visible:
uv run python -c "import logging; logging.basicConfig(level=logging.INFO, format='%(asctime)s %(levelname)s %(message)s'); from app.scheduler import capture_pit_snapshot; print(capture_pit_snapshot())"
# 3) Only rebuild the board from what is already in the market DB:
uv run python -c "import logging; logging.basicConfig(level=logging.INFO, format='%(asctime)s %(levelname)s %(message)s'); from app.scheduler import refresh_sector_board; print(refresh_sector_board())"
```

（第 3 條已在沙盒以暫存 DB 驗證可執行，輸出 `notes=('no_ok_bars_run',)`。第 1、2 條需要對外網路與 token，未在沙盒實跑。）

**週末執行會怎樣？** 會寫入、但不會「寫入當日空資料」：
- 週末候選交易日查無資料，`capture_once` 會寫 4 筆 `status=failed`、`session_date` 為空的 run（約 4 列），只是失敗紀錄。
- 這些列不會被當成資料日：board 與來源指紋只採 `status='ok'` 且有 `session_date` 的 run（`app/data/market_panel.py`）；它們也不會算進 D0，**不會讓暖身被拒絕**。
- 但市場 DB 是只增不刪（C-10），這 4 列會永久留著。所以不要為了好玩在週末重複狂按；有效的手動擷取只在「平日收盤後（建議 19:30 之後，等 FinMind 更新）」。
- 平日盤中手動執行同樣會失敗並留下 4 列失敗紀錄。

### D. 已經到過 D0 但歷史不足（步驟 4 的 D 有日期、C < 60）

此時 `--warmup` 會拒絕（`WarmupAfterD0Error`，by design），目前**沒有支援的補救 CLI**。選項：
1. 等：用每日擷取累積到 60 個交易日（約 12 週）才會有成分股。成本為零，但 3 個月內看不到排行。
2. 要提早，需要 tech-architect 出 ADR 修訂（例如重置市場 DB 重新暖身，或調整 D0 規則），並經 CEO 核可。**不要自行刪 DB 檔**（市場 DB 是只增不刪的稽核資料）。

### 預期時間表（假設今天起照做且 token 正確）

| 時間 | 預期 |
| --- | --- |
| 本週末 | 設 token、重啟 dev-up、跑暖身到 `0 failed` |
| 2026-10-05（週一）19:30 以後或當天晚上啟動時 | 擷取成功，D0 產生，**畫面那兩句消失**（會換成別的「資料不足」原因） |
| 連續 5 個交易日擷取都成功後（約 2026-10-09 或順延） | 排行有機會出現；之後還有判定關卡（需要累積樣本，卡片會用「累積中」類文字說明，這是預期的） |

電腦需要在 17:30 前後保持開機且 scheduler 視窗開著；啟動時那一次擷取也會補跑，所以晚上才開機也可以（只要當天 FinMind 已更新）。

---

## 5. 根因排序（本機最可能，依機率由高到低）

我沒有 CEO 本機的資料，以下是依程式邏輯與 `dev-up.bat` 行為推的機率排序，**以第 3 節檢查結果為準**：

| 排名 | 原因 | 對應你問的 (a)-(e) | 為什麼這樣排 |
| --- | --- | --- | --- |
| 1 | 從沒有過一次「平日收盤後、帶 FinMind token」的成功擷取 | (b) 的主因，含 (e) | 日期自證需要 token 與交易日；dev-up 不設 token、程式不讀 `.env`；今天週六啟動必失敗。**沒有 board 就不會出現週五榜單，(e) 的答案就在這裡** |
| 2 | 沒做歷史暖身，成分股為 0，board 被忽略 | (c) 的「需要 N 日資料」 | 需 ≥ 60 個交易日（程式常數 `min_listing_sessions = 60`），dev-up 不跑暖身，也無提示 |
| 3 | 啟動時機不對（盤中、盤前、週末），而且之後沒開機到 17:30 | (c) | 擷取只在平日 17:30／19:30／21:30 與啟動時跑；scheduler 若沒開著就沒有補跑 |
| 4 | scheduler 沒在跑、或用舊版 dev-up.bat | (a) | 現行版本已會開 scheduler 並檢查，但舊檔案或 `[FAIL]` 仍可能 |
| 5 | TWSE 連不上、HTTP 403、回應解析失敗 | (b) 的其他分支 | 程式會捕捉並記 `failed`（原因在 `reason`）；平常機率低於 token 問題，但 TWSE 403 實務上可能發生 |
| 6 | backend 與 scheduler 讀到不同 DB 檔 | (d) | dev-up 兩邊都在 `backend\` 啟動且沒設路徑，預設一致；只有你另外設環境變數或手動從不同目錄啟動才會發生 |
| — | `sector_refresh` 還沒跑 | (c) 的啟動延遲 | **不成立**：擷取成功後立即接著算 board（`capture_pit_snapshot` 內），另有 2 分鐘後的補跑（`SECTOR_REFRESH_STARTUP_DELAY = 2 分鐘`）；即使排在 17/19/21 時，也不是「要等到那時」才第一次有 board |

**最可能（一句話，給 CEO）**：你的電腦還沒有成功抓過一次平日收盤後的全市場資料（缺 FinMind token 或時機不對），而且也還沒做歷史暖身，所以系統手上沒有可用的榜單；週六不影響，只要曾經有過週五榜單，今天仍會顯示。

---

## 6. 建議修法（給 tech-architect／dev-lead，本次未實作）

| # | 建議 | 理由 | 備註 |
| --- | --- | --- | --- |
| 1 | 卡片的 `as_of_unknown` 狀態附上「最近一次擷取嘗試時間、結果與失敗原因（reason）」 | 現況 CEO 只看到「沒資料」，原因藏在 DB `reason`，scheduler 視窗也不印 | 注意風控：這是新增使用者可見文案，要走 risk-compliance-officer 審查（章程 0-5）；技術細節可只放「詳細」區 |
| 2 | scheduler 擷取失敗時，把 `outcome.reason` 印進 log（目前 `capture_pit_snapshot` 只印 status/rows） | 一行就能分辨 token／週末／TWSE 403 | 小改動，不涉及文案 |
| 3 | scheduler 啟動時 log 印出主 DB 與市場 DB 的**絕對路徑**，並對「`FINMIND_API_TOKEN` 未設定」印明確 WARNING 一次 | 解決 (d) 與 token 的盲點，且不印 token 值 | 只印布林是否存在 |
| 4 | `dev-up.bat` 啟動前檢查：沒有 token、或市場 DB 沒有暖身紀錄時，印提示與下一步命令 | 現行腳本完全不提暖身 | 屬 devops-sre，可另開 `chore`／`ci` 任務 |
| 5 | 提供「週末／休市日啟動時回補上一個交易日」 | 目前 D-3 規定以「現在日期」自證，週末必失敗 | **與 ADR-0012 D-3、C-11（不回填）牴觸**，需 tech-architect 出 ADR 修訂並經風控評估；FinMind 有日期，可改為取最近一個交易日候選，但要重新設計自證 |
| 6 | board 為空時啟動後立即 refresh | **不必要**：capture 已經串接 refresh，且 2 分鐘後還有一次 | 不建議做，避免重複 |
| 7 | 提供「一鍵檢查」子命令（把第 3 節 SQL 與 log 判讀包成 `python -m app.services.pit_snapshot --status`） | CEO 不必貼大段 here-string | 唯讀；dev-lead 實作 |
| 8 | 暖身狀態納入 API／卡片（例如「歷史累積 X/60 個交易日」） | 讓「為何不夠」可被看見 | 同 1，需風控審文案 |

---

## 7. 回滾

本手冊只新增這一個文件，未改任何程式或設定。要退回：刪除本檔即可。
第 4 節的補救操作中，**會改變資料的只有**暖身（寫市場 DB，只增不刪）與手動擷取（寫市場 DB）；兩者都不影響持倉、設定、警示等其他資料。

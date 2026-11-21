# backend README 程式事實核對

- 審查者：dev-lead
- 日期：2026-11-21
- 轉存：coordinator，逐字轉存 subagent 最終回報

---

## 本次結論

**有不成立／部分成立。** 共 10 項，5 項成立，5 項部分成立，沒有完全不成立的項目。只做核對，我沒有改檔、沒有 commit、也沒有 push。

需要修正的有三處：
- 第 109～110 行（第 5 項）：漏掉了「有設環境變數就寫到變數指的地方」。另外「和預測紀錄帳同一個檔」這句要有前提才成立。
- 第 54 行（第 1 項）：跳過是看 scheduler 自己這個程序的環境變數。`.env` 要先被載入程序才會生效，scheduler 不會自己去讀 `.env`。
- 第 64 行（第 10 項，不在這次 diff 內）：「唯一一顆 SQLite 檔」不準確，程式裡還有另外兩顆 SQLite 檔。

另外一件事要先說：執行過程中我在接線版 worktree 不小心建了一個 `.venv`，已經刪掉，詳情見「驗證」。

## 各部門回報（dev-lead）

**程式版本**
- product 版：`/home/user/AICompany/apps/stock-desk/backend/`，checkout 在 d5cb830。它和 base 9e0d81c 在 `apps/stock-desk` 底下沒有任何差異。
- 接線版：`/home/user/AICompany/.claude/worktrees/agent-a352324c9d164984b/apps/stock-desk/backend/`，分支 `test/f2-short-window-carryover`，head 7f2f8cd。
- 下面這幾個檔，兩版內容完全相同：`seed.py`、`cache.py`、`deps.py`、`main.py`、`portfolio/summary.py`、`alerts/engine.py`、`positions/store.py`、`alerts/store.py`。

**1. `forecast_record` 遇到變數就跳過：部分成立**
- 成立的部分：
  - 接線版 `scheduler.py` 699～700 行判斷 `FORECAST_RECORD_DB_ENV in os.environ`，所以空值也算有設。
  - 每次跳過只記一行固定的 WARNING（668～671 行、783～786 行），不會走到 INFO 那一行。
  - 這個 job 不論在什麼狀況下都會註冊（928～936 行）。
  - 測試 `test_s19a_a_refused_target_does_not_call_the_recorder`（env-set、env-empty）通過。
- `.env` 的部分：
  - 經 `dev-up.bat` 啟動時成立。流程是：第 11 行 `DEVUP_SRC_DIR=%~dp0`，94～96 行在 `apps\stock-desk\.env` 存在時設 `UV_ENV_FILE`，166 行在 backend 目錄啟動 scheduler 並繼承這個變數。
  - 我在 scratchpad 實測，Linux 上的 uv 0.11.32 遇到 `STOCK_DESK_DB_PATH=` 會把變數設成空字串，跳過條件就會成立。
- 不成立的部分有兩點：
  - scheduler 本身不讀 `.env`（697 行；測試 `test_s19a_the_scheduler_reads_no_env_file`）。如果不經 `UV_ENV_FILE`、`--env-file` 或 compose 的 `env_file` 直接啟動，`.env` 裡設了也不會讓它跳過。
  - 檢查的是 scheduler 程序自己的環境，不是整台主機。只對 API 程序設變數，不會讓 `forecast_record` 跳過。
- 應寫成的事實：scheduler 程序環境裡有這個變數（含空值）就跳過；`.env` 只有在被載入進 scheduler 程序（`dev-up.bat` 的 `UV_ENV_FILE`）時才會造成跳過。

**2. 正式登記與 bootstrap 拒絕：成立**
- 接線版 `claims.py`：
  - 403～404 行：環境變數裡有這個 key（含空值）就拒絕。
  - 405～406 行加上 385～390 行：直接讀 `<backend>/../.env`，regex `^\s*STOCK_DESK_DB_PATH\s*=`，比對前會先去掉 BOM，空值也算。
  - 拒絕字句在 305～306 行，呼叫點在 546 行。
- 這個檢查不依賴啟動方式。測試 `test_4_the_environment_names_a_database` 與 `test_4_the_env_file_names_a_database` 通過。
- 措辭備註：程式裡「正式登記」就是 `bootstrap --production` 這一條路徑；`register` 不論什麼條件都拒絕正式 DB（33～37 行）。「正式登記與 bootstrap」讀起來像兩條路，實際上是同一條。
- 旁支發現：`.env` 若寫成 `export STOCK_DESK_DB_PATH=...`，uv 會載入（scratchpad 實測），但 405 行的 regex 比對不到。這一點不影響 README 字面。

**3. 預測紀錄只寫 `<backend>/data/stock-desk.db`：成立**
- 接線版 `scheduler.py`：666 行 `BACKEND_DIR` 由模組位置推得，686～688 行定出目標路徑。
- 701～708 行：`resolve(strict=True)` 之後必須等於目標路徑，且是一般檔案；811 行 `ledger_store(target)`。
- 指數重抓走 `deps.py` 65 行的 `PriceBarCache()`，也就是 `resolve_db_path()`；通過 701～708 行的檢查後，那就是同一個檔。
- 測試 `test_s19a_the_default_target_calls_the_recorder` 通過。
- README 沒寫但屬實的兩個前提：
  - 檔案必須已經存在，scheduler 不會自己建。
  - scheduler 的 cwd 必須是 backend 目錄，否則會以 `target_not_default` 或 `target_unresolved` 跳過。

**4. Compose 顯式設定變數：成立**
- `compose.yaml` 第 19 行（backend）、第 43 行（scheduler）都設 `STOCK_DESK_DB_PATH=/app/data/stock-desk.db`。

**5. `seed.py` 的路徑規則：部分成立**
- 程式事實本身成立：
  - `seed.py` 559 行：有 `--db-path` 時用 `Path(args.db_path)`，不讀環境變數；沒有時用 `resolve_db_path()`。
  - `cache.py` 28 行、99～102 行：讀環境變數，沒有就用 `./data/stock-desk.db`。
  - 路徑都不經 resolve，所以相對於 cwd。
- README 第 113 行（`--db-path` 相對 cwd、不需要設變數）成立。
- README 第 109～110 行只說「寫進預設主 DB（相對於 cwd 的 `./data/stock-desk.db`）」，漏了「有設 `STOCK_DESK_DB_PATH` 就寫到它指的檔」。
- 「和預測紀錄帳是同一個檔」要兩個前提同時成立：cwd 是 backend 目錄，而且沒設變數。
- 應寫成的事實：不加 `--db-path` 時寫進 `resolve_db_path()` 的結果，也就是變數值，或相對於 cwd 的 `./data/stock-desk.db`。在 backend 目錄、沒設變數的情況下，就是預測紀錄帳那個檔。

**6. 寫入範圍：成立**
- 寫入的表：
  - `price_bars_cache`：`cache.put`，`seed.py` 438 行，INSERT 在 `cache.py` 215 行。
  - `positions`：`seed.py` 447 行，INSERT 在 `positions/store.py` 218 行。
  - `alert_rules`：`seed.py` 458 行，INSERT 在 `alerts/store.py` 161 行。
- 標的：`seed.py` 108、112、114 行，318～322 行，市場 TW（104 行）。
- 標記 `[demo_synthetic]` 只在 `app/demo/` 內使用（330～331 行、393～406 行、493 行、498 行），用途是 seed 自己的冪等比對與 `--reset` 判斷。
- 旁支發現：三個 store 的建構子在衝突檢查之前就會 mkdir 並建 schema（`cache.py` 143～147 行、`positions/store.py` 174～178 行、`alerts/store.py` 103～107 行；`seed.py` 560～562 行）。這不在這次 diff 內，但第 148 行「一律不寫」只對「資料列」成立，對「檔案與表」不成立。它也和「拒絕寫入主 DB」任務的約束 (b) 有關。

**7. 寫進主 DB 後不會被排除：成立**
- 在 `app/demo/` 以外 grep `DEMO_NOTE_PREFIX`、`_is_demo` 和 `note` 過濾，兩版都沒有任何一處依 note 排除資料。
- 估值：`portfolio/summary.py` 260 行 `store.list_all()` 讀全部持倉；`positions/store.py` 198 行的 SQL 沒有 WHERE。
- `data_refresh`：product `scheduler.py` 292～294 行（接線版 350 行）用 `list_all()` 取全部持倉。
- 警示評估：`alerts/engine.py` 409 行 `list_rules(enabled_only=True)`；`alerts/store.py` 142 行只過濾 `enabled`。示範規則預設 `enabled=True`（`alerts/models.py` 149 行）。
- 另外：playbook 會用 bars 的 `source`（不是 note）辨識示範資料（`playbook/engine.py` 73 行、`service.py` 587 行），那不是這三條路徑之一。

**8. API 讀主 DB 的方式：成立（程式部分）**
- `deps.py` 的 store 都用預設建構子：54 行 `PositionStore()`、65 行 `PriceBarCache()`、247 行 `AlertStore()` 等，全部走 `resolve_db_path()`，每個程序各自讀自己的環境。
- 「只能」與「不要這樣做」是規範，不是程式事實。

**9. `seed.py` 衝突訊息：成立**
- `seed.py` 243～244 行，字面是「（建議）把示範資料放進獨立的資料庫，例如加上 --db-path ./data/demo.db，或設定環境變數 STOCK_DESK_DB_PATH=./data/demo.db 後重跑；」，由 579 行印到 stderr。
- README 沒提的兩處同類說法：`--help` 555 行（「未指定時沿用 STOCK_DESK_DB_PATH」），以及 docstring 47 行。

**10. 未改動的第 64、66 行：第 66 行成立，第 64 行部分成立**
- 第 66 行：`compose.yaml` 19、43 行設變數，21、45 行掛 volume，Dockerfile 第 7 行 `WORKDIR /app`。
- 第 64 行：`resolve_db_path()` 讀這個變數（`cache.py` 99～102 行），WAL 在 170 行。但「唯一一顆 SQLite 檔」不成立，另外還有：
  - 市場 DB：`STOCK_DESK_MARKET_DB_PATH`，預設 `./data/stock-desk-market.db`（`market_panel.py` 95 行、239～241 行）。
  - 研究 DB：預設 `./data/stock-desk-research.db`（`research/sector_biased/store.py` 46 行、126 行）。
- 這兩顆在 compose 沒有顯式設定，依 `WORKDIR /app` 會落在 `/app/data`，也就在 volume 裡，所以第 66～69 行的持久化結論不受影響。
- 應寫成的事實：這個變數決定「主 DB」（快取、持倉、設定、警示等共用）；市場與研究資料各有獨立的 SQLite 檔。

## 驗證

**實際執行的指令**
- `git diff 9e0d81c d5789608`（含 `--stat`），以及各 checkout 的 `git log`、`git status`、`merge-base`。
- 對兩版 `app/`、`dev-up.bat`、`compose.yaml`、`Dockerfile` 做 grep、sed、cmp。
- 測試：在接線版目錄執行 `PYTHONDONTWRITEBYTECODE=1 <product .venv>/bin/python -m pytest -q -p no:cacheprovider tests/test_forecast_scheduler_wiring.py tests/test_forecast_claims_bootstrap.py -k "s19a or production_target or test_4_the_environment or test_4_the_env_file"`，結果 **14 passed, 111 deselected, 1 warning**。這些測試都用 `tmp_path`。
- uv 載入行為：在 scratchpad 寫了三個假的 env 檔（`/tmp/claude-0/-home-user-AICompany/3f76d891-50d3-55e1-b39d-925b8a90241a/scratchpad/envprobe/`），用 `UV_ENV_FILE=… uv run --no-project python -I -c …` 測。結果如下：
  - 空值會載入為 `''`。
  - Windows 上已有的變數優先於檔案。
  - `export KEY=` 這種寫法也會被載入。

**我造成的副作用**
- 第一次用 `uv run --frozen --no-sync pytest` 時，uv 在接線版的 `apps/stock-desk/backend/.venv` 建了一個空的 venv（88K，被 gitignore），pytest 也因為沒有 fastapi 而失敗。
- 那個 `.venv` 我已經 `rm -rf` 刪掉。事後確認三個 checkout 的 `git status --short` 都是空的，a2a08 的 HEAD 仍是 d5789608。

**沒有查證的事**
- 沒有在 Windows 上實測 uv 與 `dev-up.bat`，只在 Linux 上用 uv 0.11.32 實測。
- 沒有執行 `seed.py`，第 5、6 項只讀了程式碼。
- 沒有讀 `.env*`，沒有碰 `backend/data/`，沒有執行任何 `.bat`。
- 登記一鍵檔分支（`feat/nm5-cg2-oneclick`）是怎麼呼叫 bootstrap、有沒有帶 `UV_ENV_FILE`，我沒有追。
- 第 8 項只核對了程式事實，「只能」那句規範是否妥當不在我的範圍。

## 下一步

1. 交給 devops-sre 依上面三處應寫成的事實改字。第 64 行是原本就有的文字，要不要在這支 PR 一起改，請 tech-architect 或 coordinator 決定。
2. 第 6 項「store 在衝突檢查前就建檔、建表」與第 2 項 `export` 寫法的漏洞，建議記進追蹤清單，併入「拒絕寫入主 DB」任務評估。這兩點都不擋這支 README PR。
3. README 改完再交 qa-reviewer（含 Codex），diff 送風控知悉（RC-460）。

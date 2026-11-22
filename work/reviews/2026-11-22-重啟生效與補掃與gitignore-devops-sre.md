# 重啟生效、補掃、gitignore、log 輪替現況（RC-621 第 4、6 點；RC-622 第 3 點）

- 角色：devops-sre
- 日期：2026-11-22
- 方式：只讀。用了 Read、Grep、`git show`、`git grep`、`git ls-tree`、`git check-ignore`、`git rev-parse`、`git status`、`git diff --stat`。
- 沒讀 `.env*`（含 `.env.example`），沒碰 `apps/stock-desk/backend/data/`，沒執行 `.bat`，沒改 repo、沒 commit。
- 查證基準：`origin/product/stock-desk` @ `668b0a8596edc11f2fae271dd3333e6769bf1356`（`668b0a8 docs: 存檔 T-3 實機驗收第二輪證據與判讀`）。以下路徑除非另註，都是這個 commit 上的檔案。
- 下文只寫事實與出處，不擬 CEO 字面，不含指令或 `git pull` 的步驟建議。

---

## 一、本次結論

1. **RC-622 第 3 點：重新啟動之後，新值不一定生效。** 查到五種「新值不一定被用上」的情形，其中一種就是 security-engineer 第 3 點推論的「舊的系統環境變數蓋過 `.env` 新值」。文件的寫法支持這個推論，但實際行為沒有在 Windows 實機驗證過；CEO 機器上有沒有這種舊值，團隊不得而知。
2. **RC-621 第 4 點：補掃結果。** 沒有查到新的「憑證在 URL 且 R-1 之前會寫進 log」的路徑。但有兩條殘留路徑和一個測試面的結論要交風控判定（見 2.4）。補掃範圍與限制見第二節。
3. **RC-621 第 6 點：** 在 `origin/product/stock-desk`（`668b0a8`）上，`logs/scheduler.log`、`logs/api.log` 被根目錄 `.gitignore:34` 的 `*.log` 忽略。
4. **log 輪替：** 部署手冊沒有輪替說明；`compose.yaml` 沒有 `logging:` 設定，所以沒有 `max-size`、`max-file`。

---

## 二、各部門回報（devops-sre）

### 2.1 RC-622 第 3 點：對 CEO 而言「寫入新值、用平常方式重新啟動」實際是什麼

「平常的方式」依文件有三種。CEO 實際用哪一種，團隊沒有紀錄（RC-618 已寫明不知道）。三種都列，不替他選。

#### A. `dev-up.bat`（`local-run` skill 與 README 都寫是 CEO 日常用法）

**新值寫在哪一類設定、程式從哪裡讀**

- 設定類別：兩處之一，或兩處都有。
  1. 檔案 `apps\stock-desk\.env`（純文字，`KEY=VALUE` 一行一個；已被 `.gitignore`）。bat 在檔案存在時才設定 `UV_ENV_FILE` 指向它（`dev-up.bat:91-105`），後端與 scheduler 兩個視窗的 `uv run` 讀取；前端不讀（README「環境變數與配置」表）。
  2. Windows 的系統環境變數（README 與 `local-run` skill 都寫「已設過的同名變數優先於 `.env`」；`dev-up.bat:26-27` 註解同）。
- 程式端：`app/` 內沒有 dotenv 載入程式碼，只用 `os.environ` 讀（README 同寫；`finmind.py:101`、`alpha_vantage.py:229`、`notify.py:110-112`）。所以 `.env` 的內容要靠 bat 設的 `UV_ENV_FILE` 才進得了程式。
- 四種憑證對應的變數名（供步驟回覆撰寫者核對用，不進 RC-618 字面）：FinMind `FINMIND_API_TOKEN`、Alpha Vantage `ALPHA_VANTAGE_API_KEY`、Discord `ALERT_DISCORD_WEBHOOK_URL`、Telegram `ALERT_TELEGRAM_BOT_TOKEN`（另有 `ALERT_TELEGRAM_CHAT_ID`，Telegram 需兩者並存）。
- `.env` 與 `git pull` 的關係：`.env` 是未追蹤檔，bat 只擋「已追蹤檔案有未提交改動」，未追蹤檔不影響（`local-run` skill）；pull 不會動它。

**重新啟動的實際動作（依 bat 與 skill 所述）**

1. 停止：關掉三個 stock-desk 視窗即可（`local-run` skill「停止」）。
2. 啟動：雙擊 `apps\stock-desk\dev-up.bat`。bat 依序：檢查工具 → 確認分支與工作樹乾淨 → `git pull --ff-only` → 檢查 8000／3000 與舊 scheduler → `uv sync --locked`／`npm install --no-save` → 開 backend 視窗 → `/health` 通過後開 scheduler 與 frontend 視窗（`dev-up.bat:116-167`）。
3. 這一輪要從頭走完，新值才有機會被兩個 `uv run` 讀到。中途任何一步失敗，後面都不會跑（見下節 (b)）。

**重新啟動之後新值是否一定生效：不一定。以下是查到的情形**

| 編號 | 情形 | 依據 | 備註 |
|---|---|---|---|
| (a) | 舊的系統環境變數蓋過 `.env` 新值 | README、`local-run` skill、`dev-up.bat:26-27` 三處都寫「系統環境變數優先於 `.env`」 | 這是 security-engineer 第 3 點的推論，**文件支持**。部署手冊 0.2 還明寫可以用 `'User'`／`'Machine'` scope 永久設定環境變數；用過的話，這些值會一直留著、並且優先。〔uv 在 `UV_ENV_FILE` 與同名環境變數並存時的實際行為，本次沒有另外查證，只引用 repo 文件的說法；bat 的 `.env` 載入段落 `local-run` skill 自己標明「未在 Windows 實機驗證」〕 |
| (b) | 沒有真的重新啟動 | `dev-up.bat` 遇到已追蹤檔案有未提交改動、不在 `product/stock-desk`、`git pull --ff-only` 失敗、或 8000／3000／舊 scheduler 的詢問被答 N 時，會停止（`dev-up.bat:116-124`、`:ensure_scheduler_free`；`local-run` skill） | 停止的當下，如果舊視窗還開著，舊程式仍在用舊值；如果舊視窗已先關掉，則推播與資料更新是停著的。兩種都不會讓新值生效 |
| (c) | 只重啟了一部分程序 | backend 與 scheduler 是兩個獨立程序，各自在自己的視窗裡讀值（`dev-up.bat:150,166`） | 只重開其中一個，另一個仍是舊值。bat 的路徑是三個視窗一起重開，只有手動關掉部分視窗後再啟動才會出現 |
| (d) | `.env` 檔不在 bat 讀的位置 | bat 讀 `apps\stock-desk\.env`（`dev-up.bat:94`）；部署手冊 0.2 寫的 `.env` 位置是 `apps/stock-desk/backend/.env`，而且手冊明說那個檔「只當作你自己記值的地方」、程式不會自動讀 | 兩份文件指的是兩個不同路徑的檔案。依手冊做過的人，新值若寫在 `backend\.env`，`dev-up.bat` 不會讀到。bat 找不到 `apps\stock-desk\.env` 時只印一行 `[ENV]` 提示就照常啟動（`dev-up.bat:100-104`） |
| (e) | 變數名稱不符 | `local-run` skill、README 都提到「看到未設定但明明填了，先查檔案位置與變數名稱」 | 這條只涵蓋「未設定」的情形 |

**團隊從輸出端分不出新舊值的原因（事實）**

- 啟動時兩個視窗各印一行「FINMIND token／Alpha Vantage key／Discord webhook／Telegram：已設定／未設定」，只印狀態不印值（`app/env_status.py`；README）。(a) 的情形下，舊值仍是「已設定」，這行看不出差別。
- `local-run` skill 對這行的處理指引只涵蓋「填了卻顯示未設定」，沒有涵蓋「顯示已設定但用的是舊值」。
- 〔推論，未實測〕舊值若已被服務端作廢，(a) 的症狀會是推播失敗或取資料失敗；若服務端沒有作廢（FinMind、Alpha Vantage 能不能作廢未查證），沒有任何症狀。

**期間副作用相關的事實（供 RC-622 第 1、2 點的同仁參考）**

- 從關掉舊視窗到新的 scheduler 視窗起來之間，scheduler 是停著的，其間排程到點的工作不會跑。bat 全程含 `git pull`、`uv sync`、`npm install`，耗時沒有量測。
- `local-run` skill 寫明：出錯時視窗不自動關閉。

#### B. 部署手冊（`apps/stock-desk/docs/族群動能-主機部署手冊.md`，主機直跑、PowerShell）

- 設定類別：手冊 0.2（第 36-58 行）寫程式**不會**自動讀 `.env`；`apps/stock-desk/backend/.env` 只是「記值的地方」，實際生效要靠 PowerShell 把內容設成環境變數。給的片段是 `'Process'` scope（只影響當前 PowerShell 視窗，API 與 scheduler 兩個視窗各要跑一次）；手冊也提到可改 `'User'`／`'Machine'` scope 永久設定，並寫「`.env` 內容一有變動要重新設一次」。
- 重新啟動：手冊第 3 節寫「停掉舊的 uvicorn／scheduler 視窗（Ctrl-C，或依你自己的程序監督工具），再依首次部署步驟 5、6 重新啟動」。步驟 6 前面寫「務必也載入同一份環境變數」（手冊第 142 行）。
- 新值不一定生效的情形：
  - 載入片段沒有重跑。換了 `.env` 檔，已經開著的視窗環境不變；新開的視窗不重跑片段也不會有新值。
  - 曾用 `'User'`／`'Machine'` scope 設過的舊值，仍會留在系統裡；片段是用 `'Process'` scope 覆寫當前視窗，但沒用片段、直接開新視窗時，讀到的是系統裡的舊值。
  - 手冊同時寫了監督工具（NSSM、工作排程器）可包住程序，那種情況下重啟要用該工具的方式；本手冊沒有寫細節（第 150-152 行）。
- 手冊沒有寫「如何確認新值已生效」。

#### C. Docker（README「選用：Docker 啟動」；`compose.yaml`）

- 設定類別：`apps/stock-desk/.env`，由 `compose.yaml` 的 `env_file`（`required: false`）讀入 backend、scheduler、frontend 三個 service（`compose.yaml:9-11, 31-33, 55-57`）。
- 優先關係：`compose.yaml` 的 `environment:` 只列了 `TZ`、`STOCK_DESK_DB_PATH`、`BACKEND_INTERNAL_URL`，**沒有**列四種憑證變數。這種寫法下，主機 shell 的環境變數不會自動帶進容器；這是依 Docker 官方文件的行為推論，本次未實測。
- 重新啟動：README 只明寫過 `docker compose up --build`；另在資料備份段寫「一般重啟／重建請只用 `docker compose down`（不帶 `-v`）或 `docker compose restart`」。
- **`restart` 不會重新讀 `env_file`。** Docker 官方文件對 `docker compose restart` 的說明是：compose 設定的變更（含環境變數）重啟後不會反映。〔引用官方文件所述，本次未實測〕所以照 README 那句「一般重啟請用 `docker compose restart`」去做，新值**不會**生效；要讓容器重建才會重新讀入。README 沒有針對「換憑證要怎麼重啟」另外寫。
- `restart: unless-stopped` 的容器，在 Docker 重啟或主機重開後會用容器建立時的環境，不重讀 `.env`。〔同上，依官方行為推論〕

### 2.2 RC-621 第 4 點：補掃結果

**範圍與方法**

- `git grep` 對 `origin/product/stock-desk`，排除 `apps/stock-desk/frontend`、`work/`、`docs/`；搜尋 `httpx`、`requests`、`urllib`、`aiohttp`、`http.client`、`urlopen`、`curl.exe`、`Invoke-WebRequest`、`fetch(` 等。
- 實際會對外發 HTTP 且碰到憑證的檔案：
  - `apps/stock-desk/backend/scripts/fundamentals_spike.py`
  - `apps/stock-desk/scripts/verify_market_data.py`、`verify_sector_data.py`、`verify_intraday_quotes.py`
  - `scripts/spike_phase8_sources.py`（repo 根目錄）
  - `apps/stock-desk/backend/app/services/pit_snapshot.py` 的暖身 CLI（`python -m app.services.pit_snapshot --warmup`，部署手冊第 2 節）
- `apps/stock-desk/backend/scripts/` 其餘腳本（`r2_first_run.py`、`pipeline_acceptance_real.py`、`attest_sector_gate.py`、`n118_*`、`n172_*`、`n177_*`、`unfinished_bar_probe.py`、`v1_announce_lead_probe.py`、`c8_*`、`drawdown_rule_diff.py`、`n207_preflight/`）：grep 沒有命中任何 token、apikey、webhook 或對外 HTTP 呼叫；多數明寫只讀本機 DB 或標準函式庫、無網路。
- `apps/stock-desk/scripts/measure_sector_momentum_latency.py`：只打本機後端，不帶憑證。
- `dev-up.bat`／`dev-up.sh`、`.github/workflows/`、`compose.yaml` 內的 `curl`／`urlopen`：只打 `localhost` 的 `/health` 與前端；workflows 內沒有 secrets 引用。
- `apps/web`：只命中前端的 `ShareCard.tsx`，與憑證無關。
- 測試 `apps/stock-desk/backend/tests/`：
  - 沒有任何測試以 `os.environ` 讀取四種真憑證；
  - `conftest.py:294-310` 有 socket 防護，對非本機的連線直接擋下；
  - `tests/fixtures/` 是靜態 JSON／CSV／HTML 檔。

**各路徑的憑證位置與寫出的可能（逐一）**

| 路徑 | 憑證放哪 | 會寫出憑證的管道 | 結論 |
|---|---|---|---|
| `fundamentals_spike.py` | FinMind `token`、Alpha `apikey` 在 URL query（`:1514-1515`、`:1557`），走 `urllib` | 沒有用 `logging`；輸出一律經 `say()` 套 `Redactor`（`:2196-2200`），以環境變數裡的實際值做取代；程式自述「no files」；唯一的 `print` 在 `:2197` 的 sink | 輸出面有遮罩；沒有寫檔、沒有 log。遮罩只認環境變數裡那個值，不認格式 |
| `verify_intraday_quotes.py` | FinMind 走 `Authorization: Bearer`（`:1216`），不在 URL；Alpha 只在 `--include-alpha-vantage` 時用 | 報告與原始 JSON 寫到 `work/research/`（`:1681-1682`），寫入前經 `scrub_text`／`scrub_obj`（精確值取代，加 `token=`、`apikey=`、`Bearer` 的格式取代） | 有遮罩，格式取代範圍也有涵蓋 |
| `verify_market_data.py` | 經 `FinMindAdapter`、`AlphaVantageAdapter` 帶 query 參數 | 報告寫檔（`:1082`）；`:191` 的連線失敗訊息、`:647` 的 `str(exc)` 會進報告；它不呼叫 `configure_logging()`；`RateLimitedClient` 的 warning 記的是路徑（`url`），參數是另外傳的 `params`，不在其中（`app/data/http.py:235-251`） | 本次沒找到會把 query 帶進報告的管道；報告內容沒有逐行核對（見下） |
| `verify_sector_data.py` | FinMind `token` 在 query（`:375`） | 報告寫檔（`:722`）；另有 `coverage_log`（`:230`）只寫日期與比例；`:376-390` 的錯誤訊息是 `連線失敗：{exc}` | 同上 |
| `scripts/spike_phase8_sources.py` | FinMind `params["token"]`、Alpha `"apikey"` 在 query（`:354,416,446,458,516,541`） | 只 `print` 結果；錯誤用 `{exc!r}`（`:151,163,242`）；不呼叫 `configure_logging()`、不寫檔 | 沒找到 R-1 前會寫出憑證的管道 |
| `pit_snapshot.py --warmup` | FinMind `token` 在 query（`:318`） | 不呼叫 `configure_logging()`（全 repo 只有 `main.py:49`、`scheduler.py:786` 呼叫）；錯誤字串 `連線失敗（…）：{exc}` 會存進市場 DB 的 `market_backfill_progress.last_error` 並印到終端（`:330`、`:400-467`） | 見下面殘留說明 |

**共通的判斷依據與限制（事實）**

- httpx 0.28.1 以 INFO 記錄含 query 的完整 URL（前次盤點 F-7）。上面這些腳本都沒有呼叫 `configure_logging()`，也沒有 `basicConfig`（全 repo 搜尋）。沒有 handler 時，Python 預設只輸出 WARNING 以上到 stderr，INFO 不會輸出。所以這些路徑不走「R-1 前 INFO 寫出完整 URL」的那條機制。
- 全 repo 非測試程式碼中，`raise_for_status` 只出現在 `notify.py:82`，是 R-1 已處理的路徑；`HTTPStatusError`（訊息會含完整 URL）沒有其他呼叫點。
- 上面「`{exc}` 是否會含 URL」的判斷是〔推論，未實測〕：httpx 的連線類例外（`ConnectError`、`ConnectTimeout` 等）訊息通常是底層錯誤文字，不含 URL。我沒有逐一對各 provider 實跑驗證。
- 〔未查證〕FinMind 在 `status` 非 200 時回的 `msg` 內容會不會回顯 token。`pit_snapshot.py:330` 與 `verify_sector_data.py:386-390` 會把 `payload` 或 `msg` 印出／存下。
- 我沒有逐行讀過各腳本寫出的歷史報告檔，也沒有讀 `work/research/` 下既有的報告內容（避免碰到值）。這些腳本過去有沒有被 CEO 在本機跑過，團隊不知道。

### 2.3 RC-621 第 6 點：`.gitignore` 結果

- 分支與 commit：`origin/product/stock-desk` = 本機 `product/stock-desk` = `668b0a8596edc11f2fae271dd3333e6769bf1356`（兩者 `git rev-parse` 相同）。
- 這次用的是本機 `check-ignore`，它讀的是工作樹的 `.gitignore`。為確保對得上 `origin/product/stock-desk`，我另外確認了：`git status --porcelain -- .gitignore apps/stock-desk/backend/.gitignore` 無輸出、`git diff --stat origin/product/stock-desk -- .gitignore apps/stock-desk/backend/.gitignore` 無輸出，即兩個檔案和 origin 上的一致。
- `git check-ignore -v logs/scheduler.log logs/api.log` 輸出：
  - `.gitignore:34:*.log	logs/scheduler.log`
  - `.gitignore:34:*.log	logs/api.log`
  - exit code 0（兩個都被忽略）。加 `--no-index` 結果相同。
- `git ls-tree -r --name-only origin/product/stock-desk` 沒有任何 `logs/` 底下的追蹤檔。
- 涵蓋範圍：只表示這兩個檔名不會被 `git add` 帶進來。**不涵蓋**：Docker json-file 的 log、PowerShell transcript 檔、`dev-up.bat` 視窗內容的複製或截圖、以及被另存成別的副檔名的檔案。
- `apps/stock-desk/backend/.gitignore` 另有 `/data/`、`*.db`、`*.db-shm`、`*.db-wal`。

### 2.4 要交風控另判的項目（補掃衍生）

依 RC-621 第 4 點「另外送我判定，不回改本則」，列出，不自行定性：

1. `pit_snapshot --warmup` 與 `verify_sector_data.py` 把 FinMind 回傳的 `payload`／`msg` 原樣存進 DB 或報告；是否會回顯 token 未查證。
2. 三支 `apps/stock-desk/scripts/verify_*.py` 與 `fundamentals_spike.py` 的遮罩，都是「環境變數裡的當下值」加格式規則；若 CEO 跑腳本之前就已換過值，遮罩只認新值，舊值若出現在別處不會被遮。這是設計上的限制，不是已發生的事。
3. 這幾支腳本的歷史執行紀錄與輸出報告是否留在 CEO 本機，團隊觀測不到。

### 2.5 第 4 項：log 輪替現況（只列現況）

- **部署手冊**（`apps/stock-desk/docs/族群動能-主機部署手冊.md`）：
  - 有 log 附加寫入：`uv run uvicorn … *>> ..\..\..\logs\api.log`（第 140 行）、`uv run python -m app.scheduler *>> ..\..\..\logs\scheduler.log`（第 144 行）；第 137-138 行有建 `logs\` 資料夾的步驟。
  - **沒有任何 log 輪替、大小上限、保存期間、清理的說明。** 全文搜尋「輪替」「rotat」「max-size」「logrotate」，沒有命中。第 5 節只有用 `Select-String` 掃 `logs\scheduler.log` 最近幾行的監控寫法。
  - 手冊提到可用 NSSM 或工作排程器包起來（第 150-152 行），沒有寫它們的 log 設定。
- **`compose.yaml`**：三個 service（backend、scheduler、frontend）**都沒有 `logging:` 區塊**，沒有 `max-size`、`max-file`，也沒有指定 logging driver。依 Docker 官方文件，預設 driver 是 json-file、沒有大小上限〔依官方文件所述，本次未在 CEO 主機驗證〕。
- **`dev-up.bat`／`dev-up.sh`**：不導向檔案，輸出只在視窗（sh 為終端機）裡；沒有輪替議題，但也沒有保存。
- 已有的追蹤紀錄：ADR-0029 第 274 行、第 350 行（待補項 7）、`work/dispatch/2026-10-17-後續追蹤清單.md` 第 781 行都已列為待辦，尚未處理。
- 補充：`work/reviews/2026-10-26-產品審視-devops-sre.md` 第 98 行曾建議讓 scheduler 同時寫到 `backend/data/logs/scheduler.log`（輪替）。本次查到的現行 `logging_setup.py` 是否已實作此項，我沒有讀實作，未查證。

---

## 三、驗證

**實際執行的唯讀指令（輸出已看）**

- `git rev-parse HEAD origin/product/stock-desk`：兩者皆 `668b0a8596edc11f2fae271dd3333e6769bf1356`；`git branch --show-current`：`product/stock-desk`。
- `git status --porcelain -- .gitignore apps/stock-desk/backend/.gitignore`、`git diff --stat origin/product/stock-desk -- …`：皆無輸出。
- `git check-ignore -v logs/scheduler.log logs/api.log`：`.gitignore:34:*.log`，兩者皆命中；`--no-index` 同。
- `git ls-tree -r --name-only origin/product/stock-desk | grep '^logs/'`：無輸出。
- `git show origin/product/stock-desk:.gitignore | sed -n 30,36p`：第 34 行為 `*.log`。
- `git grep` 針對 `compose.yaml`、手冊、`dev-up.bat`、`scripts/`、`tests/`、`.github/` 的各項搜尋（如上各節）。

**讀過的檔案**

- 風控定稿 `work/reviews/2026-11-22-憑證輪換告知範圍擴大定稿RC618至RC622-風控.md`（全文）。
- `.claude/skills/local-run/SKILL.md`、`apps/stock-desk/README.md`（第 1-140、255-285 行）、`apps/stock-desk/dev-up.bat`（第 1-35、88-167、225-310 行）、`apps/stock-desk/compose.yaml`（全文）、部署手冊（第 36-62、98-102、134-222 行及全文 grep）、`app/data/http.py`、`app/services/pit_snapshot.py`、各腳本相關段落。

**沒有做、沒有驗證**

- 沒有在 Windows 實機跑 `dev-up.bat`，沒有驗證 `UV_ENV_FILE` 與同名系統環境變數並存時 uv 的實際取捨。
- 沒有實測 Docker `restart` 與 `up` 對 `env_file` 的處理，只引用官方文件的說法。
- 沒有查 CEO 機器上有沒有舊的系統環境變數，也沒有辦法在不看設定的前提下查（RC-622 第 3 點禁止）。
- 沒有讀 `.env*`、`backend/data/`、`work/research/` 既有報告內容。
- 補掃只涵蓋 `origin/product/stock-desk` 這個 commit；其他分支、worktree（`.claude/worktrees/`）沒有掃。
- httpx 例外訊息是否含 URL、FinMind 回應是否回顯 token，皆未實測。

---

## 四、下一步

- **風控（risk-compliance-officer）**
  - 取用 2.1 的事實作為 RC-622 第 3 點的輸入；2.1 的 (a)～(e) 與 Docker `restart` 的情形是步驟回覆要不要寫、怎麼寫的判斷依據。
  - 判定 2.4 三項。
- **creative-lead**
  - 步驟回覆要先決定對象：`dev-up.bat`、部署手冊、Docker 三種，各自步驟不同。CEO 實際用哪種，不得要求他去查設定來回答；可行的作法是只問他「平常怎麼啟動」這類憑記憶的問題，是否允許這樣問由風控判定。
  - 注意 README 的「一般重啟請用 `docker compose restart`」若被照抄進步驟，新值不會生效。
- **security-engineer**
  - 收 (a)：「舊系統環境變數蓋過 `.env`」有文件支持，但實機未驗；以及 2.4 第 2 點的遮罩限制。
- **devops-sre（我，另開分支、另送 qa-reviewer，不在本次）**
  - 部署手冊補 log 輪替說明；`compose.yaml` 加 `logging:` 的 `max-size`、`max-file`（設定變更要先經 qa-reviewer）。
  - README 與 `local-run` skill 補「換憑證後怎麼重啟才會讀到新值」的寫法，處理 Docker `restart` 與兩個 `.env` 路徑不一致（`apps\stock-desk\.env` 對 `backend\.env`）。這兩項是文件落差，等風控與 CEO 對步驟回覆定案後再改。
- **tech-architect**
  - RC-621 第 1 點改寫 D-10 時，補掃的結論是「沒有新增會寫出憑證的路徑」，但上述〔推論〕與〔未查證〕項目要保留為殘留紀錄。
- **CEO**：本次沒有需要決定或操作的事。

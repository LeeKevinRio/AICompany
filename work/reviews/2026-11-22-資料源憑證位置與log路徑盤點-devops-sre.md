# 資料源憑證位置與 log 路徑盤點（回應 security-engineer 判定「下一步」）

- 作者：devops-sre
- 日期：2026-11-22
- 方法：只用 Read、Grep、非變更性 git（`git log`、`git show`、`git grep`）與 `sed`/`grep` 讀程式碼。未讀 `.env*`，未碰 `apps/stock-desk/backend/data/`，未執行 `.bat`，未改檔、未 commit。報告不含任何 token、金鑰或 URL 值；只記「程式怎麼組 URL」。
- 路徑縮寫：`B/` = `apps/stock-desk/backend/app/`。

## 本次結論

1. 資料源中，**只有 FinMind 與 Alpha Vantage 把憑證放在 query 參數**（`token`、`apikey`）。Telegram 把 bot token 放在 URL 路徑，Discord 把整條 webhook URL（含 token）當作 URL。其餘資料源（證交所、櫃買、台銀、Yahoo、證交所 OpenAPI）沒有憑證；程式碼內也沒有 SEC 呼叫點。沒有任何一個來源把憑證放在 header。
2. R-1 合併前，**scheduler 行程**在 INFO 等級會把含憑證的完整 URL 寫進 log，這由程式碼與 httpx 0.28.1 原始碼共同支持（見第 2 節事實）。**API 行程**在該時點沒有 root handler，httpx 的 INFO 不會輸出（推論，見第 2 節）。
3. 這比 security-engineer 判定書的範圍多一項：判定書只點名 Telegram／Discord；本盤點確認 **FinMind token 與 Alpha Vantage apikey 也在同一條路徑上**（scheduler 的 `pit_snapshot_capture` 走 FinMind）。若 CEO 要輪換，名單不止通知通道。
4. `redact_url()` 目前涵蓋的名稱（`token`、`apikey`、`api_key` 與 Telegram／Discord 路徑）**與現有盤點結果沒有落差**；但規則是精確比對名稱，日後新增帶其他名稱的憑證（例如 `access_token`、`key`）不會被遮蔽。
5. CEO 主機上 scheduler 與 backend 的 log 位置：依手冊是 `logs\api.log`、`logs\scheduler.log`（附加寫入）；`dev-up.bat` 完全不導向檔案，輸出只留在兩個 cmd 視窗；Docker 路徑另列。

## 各部門回報（devops-sre）

### 1. 各資料源的憑證位置

| 來源 | 憑證位置 | 出處（檔案:行號） |
|---|---|---|
| FinMind（`api.finmindtrade.com`） | **query 參數 `token`** | `B/data/providers/finmind.py:111-117`（`params` 內 `"token": token`，env 名 `finmind.py:71`）；另一個呼叫點 `B/services/pit_snapshot.py:313-319`（同樣 `"token": token`，`pit_snapshot.py:389` 自 env 讀） |
| Alpha Vantage（`www.alphavantage.co`） | **query 參數 `apikey`** | `B/data/providers/alpha_vantage.py:289-294`（env 名 `alpha_vantage.py:147`） |
| Telegram（`api.telegram.org`） | **URL 路徑** `/bot<token>/sendMessage`，不是 query | `B/alerts/notify.py:42`（樣板）、`notify.py:113-117`（組 URL） |
| Discord webhook | **整條 URL 本身即憑證**（token 在 `/webhooks/<id>/<token>` 路徑），由 env 讀入後直接當請求 URL | `B/alerts/notify.py:38`（env 名）、`notify.py:110` |
| yfinance（`query1.finance.yahoo.com`，直接呼叫 chart API，沒有用 `yfinance` PyPI 套件） | 沒有憑證；只有 `User-Agent: Mozilla/5.0` header。query 為 `period1`、`period2`、`interval` | `B/data/providers/yfinance.py:143`、`yfinance.py:653-657` |
| 證交所 `www.twse.com.tw` STOCK_DAY | 沒有憑證；query 為 `response`、`date`、`stockNo` | `B/data/providers/twse.py:97-103` |
| 櫃買 `www.tpex.org.tw` tradingStock | 沒有憑證；query 為 `code`、`date`、`id`、`response` | `B/data/providers/tpex.py:220-227` |
| 證交所 OpenAPI（`openapi.twse.com.tw`）：快照、上市清單、公司基本資料、除權息 | 沒有憑證；`get(path)` 不帶 params | `B/data/providers/twse_snapshot.py:363,435`、`B/directory/providers.py:205,403`、`B/dividends/providers.py:355` |
| 櫃買 OpenAPI 清單 | 沒有憑證；不帶 params | `B/directory/providers.py:293` |
| 台銀牌告匯率（`rate.bot.com.tw`） | 沒有憑證；日期在路徑，CSV 端點 | `B/data/providers/fx.py:12,68,170` |
| SEC | 程式碼內沒有呼叫點（`git grep` 搜 `sec.gov` 與 `SEC_` 無命中） | — |
| 共用 client | `RateLimitedClient` 包 `httpx.Client(base_url=...)`，`params`/`headers` 原樣轉給 httpx，不做任何遮蔽 | `B/data/http.py:172,188,231` |

範圍說明：我以 `httpx` 為搜尋條件掃過 `B/` 下全部 `*.py`；`requests`、`aiohttp`、`urllib.request` 沒有命中（`yfinance.py:123` 的 `urllib.parse.quote` 只用於組路徑）。這個範圍之外（`scripts/`、`tests/`、`backend/scripts/`）未掃。

### 2. R-1 合併（`3903df1`，2026-10-26T08:18:47Z，台灣時間 16:18）之前，INFO 會不會寫出含憑證的完整 URL

**事實**
- F-1：合併前一版（`cb4e51a^`）的 `B/scheduler.py:782` 是 `logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")`，位於 `main()`（scheduler 的行程進入點，`scheduler.py:780-783`）。`git show cb4e51a^:apps/stock-desk/backend/app/scheduler.py` 查得。`basicConfig` 不帶 `handlers`、`filename`，等於在 root logger 裝一個寫 stderr 的 handler 並把 root 等級設為 INFO，所以未另行壓低的第三方 logger（含 `httpx`）INFO 都會輸出。
- F-2：本機 httpx 版本為 0.28.1（`apps/stock-desk/backend/uv.lock:274-275`）。我讀了本機 uv 快取內 httpx 的 `_client.py`（路徑 `/root/.cache/uv/archive-v0/-XgywpEEkBqop_4_/httpx/_client.py`，`httpx-0.28.1.dist-info` 同目錄）：第 1025-1031 行與第 1740-1745 行都是 `logger.info('HTTP Request: %s %s "%s %d %s"', request.method, request.url, ...)`（同步、非同步各一）。`request.url` 是含 query 的完整 URL。
- F-3：`cb4e51a^` 時 `git grep` 搜 `logging.basicConfig`、`dictConfig`、`getLogger("httpx"`、`setLevel` 在 `apps/stock-desk/backend`（排除 tests）只命中 `scheduler.py:782`；也就是 R-1 前沒有任何程式把 `httpx` 壓在 INFO 以上，也沒有遮蔽。
- F-4：`cb4e51a^` 的 `B/main.py` 無 `logging` 字樣（grep 無命中）。
- F-5：呼叫鏈在 scheduler 行程內成立：`scheduler.py:122` 在 `cb4e51a^` 已 import `capture_once`，`PIT_CAPTURE_JOB_ID = "pit_snapshot_capture"` 在 `:168`，`:484-485` 的 job 函式呼叫 `capture_once`；`pit_snapshot.py:313-319` 以 `token` query 送 FinMind；`pit_snapshot.py:450` 用 `RateLimitedClient`（即 `httpx.Client`）。Alpha Vantage 經 `app.api.deps`（`scheduler.py:98` import）取得的 provider，其 `apikey` query 在 `alpha_vantage.py:289-294`。
- F-6：憑證進入 query 的時點（`git log -S`）：FinMind `"token": token` 於 `d76deb4`（2026-07-23，Phase 2）進入 `finmind.py`；`pit_snapshot.py` 的 FinMind 呼叫於 `9a57a03`（2026-09-25）；Alpha Vantage `"apikey": api_key` 於 `7fde131`（2026-07-28，Phase 7）。`basicConfig` INFO 自 `dbd8d4f`（2026-07-23）起存在（引 security-engineer 判定書；我未重驗該 commit）。
- F-7：Telegram／Discord 的 URL 組法見第 1 節；`notify.py` 送出用 `httpx.Client()`（`notify.py:120,144`），同樣走 httpx 的 INFO 記錄。

**推論（未驗證）**
- I-1：只要 scheduler 行程在 R-1 前實際發出過 FinMind／Alpha Vantage／Telegram／Discord 的請求，`HTTP Request: GET <完整 URL> "HTTP/1.1 200 OK"` 這類行就會出現在該行程的 stderr，其中 FinMind 為 `...&token=<值>`，Alpha Vantage 為 `...&apikey=<值>`，Telegram 為 `/bot<值>/sendMessage`，Discord 為完整 webhook。因 F-1 到 F-3 同時成立，我判斷此推論可靠；但我**沒有**實際執行行程觀察輸出，也沒有讀任何 log 檔。
- I-2：API 行程（`uvicorn app.main:app`）在 R-1 前沒有 root handler（F-4），uvicorn 只設定自己的 `uvicorn`、`uvicorn.error`、`uvicorn.access` logger；httpx INFO 沒有 handler 接，只剩 Python 的 lastResort handler（僅 WARNING 以上）。所以 API 行程的外發 URL 不應寫出。這是對 Python logging 行為的推論，未實測；且 uvicorn 的 access log 記的是進來的請求路徑，不是外發 URL。
- I-3：同樣道理，WARNING 等級的失敗訊息（例如 `yfinance.py:659`、`twse.py:123` 的 `logger.warning("... %s", exc)`）會帶 `exc` 文字。`httpx.TransportError` 的訊息通常不含完整 URL，但這依 httpx／httpcore 版本，我沒有驗證；`notify.py:82` 有 `raise_for_status()`，該例外文字**會**含 URL，`notify.py:95-96` 的註解自己也這麼寫。這條路徑在 R-1 前是否寫出完整 URL，我沒有重驗（R-1 後以 `describe_failure` 處理）。
- I-4：以上全部限於「行程在 R-1 前跑過」。CEO 的行程何時換成 R-1 後版本，團隊觀測不到（同判定書）。

**未查證**
- 通道、FinMind token、Alpha Vantage key 在 CEO 主機上是否設定過；`notify_webhooks` 是否為真；scheduler 是否真的送出過請求；舊 log 是否仍在。
- R-1 前 `uvicorn --reload`（`dev-up.bat:150`）的子行程是否與上述 API 推論一致；未實測。

### 3. CEO 主機上 scheduler、backend 的 log 可能位置（只記位置，不讀內容）

**A. 依主機部署手冊（`apps/stock-desk/docs/族群動能-主機部署手冊.md`）**
- 手冊第 137-144 行：在 `apps\stock-desk\backend` 目錄下以 `*>>` 附加（不覆蓋）導向：
  - API：`..\..\..\logs\api.log`，也就是 repo 根目錄的 `logs\api.log`。
  - scheduler：`..\..\..\logs\scheduler.log`，也就是 repo 根目錄的 `logs\scheduler.log`。
- 手冊第 336-337 行的監控範例用的是絕對路徑 `C:\stock-desk\logs\scheduler.log`；若 CEO 把 checkout 放在別處，實際位置跟著 checkout 走。
- 手冊第 148-152 行也提到可改用 `Start-Transcript` 或 NSSM、工作排程器包住啟動；這些會產生**手冊未指定的位置**（transcript 檔、NSSM 的 stdout／stderr 檔、工作排程器歷程）。我無法知道 CEO 用哪一種。
- 重導是附加寫入，R-1 的程式更新不會改動舊內容（同判定書）。
- `.gitignore` 是否涵蓋根目錄 `logs\`：我用 `git check-ignore` 查詢，指令在本環境沒有輸出（前一輪合併指令 exit 1，原因是檢查失敗，不是已確認被忽略）。**未查證**，列入下一步。

**B. 依 `dev-up.bat`（只 grep，沒有執行）**
- 啟動指令在第 150 行與第 166 行：`start "stock-desk backend" cmd /k "... uvicorn app.main:app --reload --port 8000"`、`start "stock-desk scheduler" cmd /k "... python -m app.scheduler"`。檔內沒有任何 `>`／`>>`／`tee` 導向，所以 **dev-up.bat 啟動的兩個行程，輸出只在各自的 cmd 視窗（`/k` 保持開啟）**，不寫檔案。位置：cmd 視窗的捲動緩衝區（記憶體內）。
- 衍生的位置性事實：若 CEO 曾從視窗複製、截圖、或用 `Start-Transcript`／console 紀錄工具存過內容，那些副本位置我不知道。這點與 `.env` 不同，`dev-up.bat` 第 26 行說 `.env` 由 `UV_ENV_FILE` 載入，與 log 位置無關。
- 兩種啟動方式可能並存：手冊的 PowerShell 做法與 `dev-up.bat`，CEO 用過哪個，我無法從 repo 判斷。

**C. Docker 路徑（另列）**
- `apps/stock-desk/compose.yaml` 的 `backend`、`scheduler` 兩個 service 沒有 `logging:` 設定（grep `log` 只命中 `volumes` 註解），Dockerfile 的 `CMD` 為 uvicorn（`backend/Dockerfile:20`），沒有導向檔案。所以輸出走容器 stdout／stderr，由 Docker 預設 logging driver 處理（預設為 json-file，**〔推論〕**未在 CEO 主機上驗證）。
- 位置（依 Docker 慣例）：Linux 主機為 `/var/lib/docker/containers/<container-id>/<container-id>-json.log`；Docker Desktop for Windows 為其 WSL2 虛擬機內的同名路徑，不在 Windows 檔案系統上直接可見。這些是 Docker 文件所述的一般位置，**不是我在 CEO 主機驗證過的**。
- ADR-0029 第 274 行已記載 compose 無 logging driver 選項、json-file 預設無大小上限；`docker compose logs backend` 與 `docker compose logs scheduler` 是讀取入口（只記入口，不建議執行）。
- 資料卷 `stock-desk-data`（`compose.yaml:69-75`，掛在 `/app/data`）放 SQLite，不放 log。
- 手冊第 6 節說明 compose 的 backend／scheduler 不能用於「判定」，所以 CEO 主機上的 Docker 路徑可能只是歷史啟動方式；是否用過，我不知道。

### 4. `redact_url()` 涵蓋範圍與第 1 點的落差

**現況（`B/logging_setup.py:52-64`，在 `product/stock-desk` 上）**
1. Telegram：`api.telegram.org/bot` 之後的路徑段。
2. 任何主機上的 `/bot<數字>:<密文>` 形狀。
3. Discord：`/webhooks/<id>/<token>` 的 token 段（id 保留）。
4. Query：`[?&;]` 後接 `token=`、`apikey=`、`api_key=`（`re.IGNORECASE`，所以 `apiKey=`、`TOKEN=` 都符合）。

**與第 1 節的對照**
- FinMind `token`：涵蓋。Alpha Vantage `apikey`：涵蓋。Telegram 路徑：涵蓋。Discord 路徑：涵蓋。其他資料源沒有憑證，無落差。
- 結論：**現有盤點範圍內，沒有落差。**

**結構性限制（非現況落差，但影響日後）**
- L-1：規則以名稱精確比對。`access_token=`、`key=`、`secret=`、`auth=`、`password=` 這類名稱不會被遮蔽（前綴要是 `?`／`&`／`;` 加上精確名稱）。目前沒有資料源使用這些名稱，所以屬「新增來源時要同步補規則」。
- L-2：header 憑證（`Authorization`、`X-API-Key`）不在 `redact_url()` 範圍；目前也沒有任何來源把憑證放 header。
- L-3：URL 編碼過的 `=`（`%3D`）不會被比對。httpx 輸出的 query 是 `=` 原樣，所以對 httpx 的行不成立；對其他文字（例外訊息）未驗證。
- L-4：遮蔽生效的前提是 `configure_logging()` 自己裝 handler；當 root 已有 handler 時只套第 1 條（把 httpx、httpcore 壓在 WARNING），handler 不帶過濾（`logging_setup.py:108-114`）。判定書同樣指出 uvicorn handler 的行為未實測，我的第 2 節 I-2 與此相同。
- L-5：`redact_url` 只作用在經 `configure_logging` 裝的 handler 的輸出；**已寫進舊 log 檔的內容不會被改**。

## 驗證

**已執行（皆只讀）**
- `Read`：判定書全文、`logging_setup.py` 全文。
- `Grep`／`sed`／`grep`：`B/` 下 `httpx`、`requests`、`urllib`、`apikey`、`token`、`Authorization`、`params=`、`headers=`；各 provider 的 `params` 區塊；`compose.yaml`、`dev-up.bat`、部署手冊的 log 與導向字樣。
- `git log -1 --format='%H %ci' 3903df1`：`3903df119942cb4254a73e118d06327a9a763663`、`2026-10-26 08:18:47 +0000`。
- `git show cb4e51a^:apps/stock-desk/backend/app/scheduler.py`（`logging.` 命中與第 778-786 行）、`git show cb4e51a^:.../main.py`（無 logging 字樣）、`git grep ... cb4e51a^`（只命中 `scheduler.py:782`）。
- `git log -S'"token": token'`、`-S'"apikey": api_key'`：得出第 2 節 F-6 的 commit 與日期。
- 讀本機 uv 快取的 httpx 0.28.1 `_client.py`：確認 INFO 行含 `request.url`。`uv.lock:274-275` 確認專案鎖定 0.28.1。

**未驗證**
- 任何 log 檔、`.env*`、`backend/data/` 的內容或是否存在（依守則未碰）。
- 通道與資料源憑證是否設定過；scheduler 是否真的送過請求。
- I-1 到 I-3 的行程實測；Docker 預設 logging driver 在 CEO 主機的實際值。
- 根目錄 `logs\` 是否被 `.gitignore` 涵蓋（`git check-ignore` 本輪沒有得到有效輸出）。
- `scripts/`、`tests/`、`backend/scripts/` 內的 httpx 呼叫點，以及 `R-1` 之後新增的資料源。
- 掃描未包含 `product/stock-desk` 以外的分支；我讀的是工作區目前檢出的內容，與判定書指的 `product/stock-desk` 是否同一 HEAD，我未核對。
- `dbd8d4f` 的 `basicConfig` 引自判定書，未重驗。

## 下一步

- **security-engineer**：請把輪換名單依第 1 節擴充：FinMind token、Alpha Vantage key 與 Telegram／Discord 同屬 R-1 前 scheduler INFO 路徑的曝險（F-5、F-6）；CEO 字面是否要加入這兩項，由你與風控決定。FinMind／Alpha Vantage 輪換同樣只有帳號持有人能做，新值也只能進主機環境設定。
- **風控、creative-lead**：CEO 字面若列通道，請同步考量資料源兩項；字面約束照判定書（不得叫 CEO 貼內容）。
- **devops-sre（我）**：(a) 補掃 `scripts/`、`tests/`、`backend/scripts/` 的外發呼叫點；(b) 用一次受控的 `git check-ignore` 確認根目錄 `logs\` 是否被忽略，並把結果回報；(c) 部署手冊增補 log 輪替與 Docker `logging` 選項（`max-size`、`max-file`）的待補項，另開 `chore`／`docs` 分支，不在本次盤點範圍；(d) `redact_url` 的規則擴充（L-1）建議在新增資料源時由 devops-sre 與 dev-lead 同步檢查，列入 `qa-reviewer` 清單。
- **qa-reviewer**：審本報告第 2 節 F-1 到 F-7 的引用是否與你自己的重跑一致。
- **CEO**：本報告不要求任何動作；待風控審定字面後再回覆。

## 回滾方式

本次為只讀盤點，沒有任何 repo、環境或設定變更；除本報告檔外沒有產出，無需回滾。刪除本報告檔即可還原。

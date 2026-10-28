# ADR-0002：flight-deals 技術棧與資料源

- 狀態：accepted（CEO 2026-10-26 核可）
- 日期：2026-10-25
- 決策者：tech-architect（草案）、CEO（2026-10-26 核可，連同「總經理對 PRD 的收斂裁決」照現狀核可）
- 適用範圍：僅 `product/flight-deals` 產品線（`apps/flight-deals/`）；不約束員工線 main 與其他產品線
- 編號附註：本產品線自 origin/main `e1349aa` 長出，當時 main 的 `docs/adr/` 只有 0001 與 0007，0002 未被占用（總經理 2026-10-25 以 `git ls-tree` 確認）。其他產品線另有各自的 0002，跨線引用時請加產品名。
- 落檔者：總經理（依 tech-architect 草案落檔，並附「總經理對 PRD 的收斂裁決」與「本機實測附錄」兩節）

## Context（背景）

CEO 要一個個人用的機票低價監看器：在網頁後台設定監看條件，系統定時查價、記錄價格歷史，價格達條件就推 Telegram。只有一位使用者，在本機執行。需求以 `work/flight-deals-PRD.md`（v0.1）為最終依據，摘要如下：

- 監看條件：出發地（預設 TPE）、目的地、日期（固定日期，或「最早出發～最晚回程」彈性窗加旅程天數上下限）、預算門檻（TWD）、來回或單程、經濟艙 1 人。
- 推播條件三種：價格 ≤ 門檻、比上次通知跌 X%、創新低。同價不重複推。
- 網頁功能：監看 CRUD、價格歷史與最便宜時段、資料源健康狀態、Telegram 測試發送。

資料源事實（2026-10-25 由總經理查證，本 ADR 直接採用）：

| 來源 | 事實 | 查證日期 |
| --- | --- | --- |
| Amadeus Self-Service | 多個第三方來源稱自助 API 已於 2026-07-17 停用、只剩 Enterprise 合約；官方文件頁沒看到相關聲明 | 2026-10-25 |
| Travelpayouts（Aviasales）Data API | 免費，要註冊取 token（header `X-Access-Token`）。資料是 Aviasales 使用者過去 48 小時搜尋的**快取價**，不是即時價；文件自述適合做靜態頁。預設幣別 RUB，可用 `currency` 參數改。TPE 出發的覆蓋可能稀疏。rate limit 文章**未查** | 2026-10-25 |
| fast-flights（PyPI 3.x，反向工程 Google Flights protobuf） | 免費、不用 key、即時價、TPE 覆蓋完整。但非官方，Google 改版就會壞；純 requests 常拿到空白頁；不同版本 API 不同（舊 `create_filter`/`FlightData`，新 `create_query`/`FlightQuery`）。本機實測見附錄 | 2026-10-25 |
| Telegram Bot API `sendMessage` | 免費。stock-desk 線的雷：httpx INFO log 和 `str(exc)` 都會印出含 bot token 的完整 URL | 2026-10-25 |
| LINE Notify / Messaging API | LINE Notify 已於 2025-03 終止；Messaging API 要另建 channel | 2026-10-25 |

本機工具：uv 0.12.1、Python 3.11（uv 可自動裝 3.12）、Node 24。

限制條件：
- 公司 skill `data-source-integration` 的必要條件：adapter、`as_of`/`source`、快取、rate limit、指數退避、離線 fixture、timeout、契約測試、降級策略，以及「不得以假資料冒充真實資料」。
- 章程 §0-3：祕密只走環境變數。
- 章程 §0-5：建議類文案要過風險閘門。

## Options（選項比較）

### 技術棧

| 方案 | 優點 | 缺點 | 風險 |
| --- | --- | --- | --- |
| **S1** FastAPI + Jinja2 伺服端樣板 + 少量原生 JS，單一 Python process | 只有一條 build 鏈；只有三四頁，夠用；部署就是一個 `uv run` | 互動性有限；圖表要手寫或用靜態 JS | 原生 JS 長大後失控（以 C-14 限制） |
| S2 FastAPI + Vite/React | 互動強、生態成熟 | 多一條 Node build 鏈和一套依賴，對單人三四頁太重 | 維護面加倍 |
| S3 CLI + Windows 工作排程器，不做網頁 | 最簡單 | 不符合 PRD 的網頁 CRUD 需求 | — |
| S4 Django | 內建 admin 和 ORM | 對這個規模偏重，和公司 FastAPI 慣例不一致 | 學習與慣例分歧 |

### 排程

| 方案 | 優點 | 缺點 | 風險 |
| --- | --- | --- | --- |
| **P1** APScheduler 3.x 跑在同一個 process，記憶體 jobstore，啟動時從 `watch` 表重建排程 | 單一 process、單一真相來源 | 網頁沒開就不會掃描 | uvicorn 多 worker 或 reload 會重複啟動排程（以 C-7 防） |
| P2 另起一個 scheduler process | 網頁和排程隔離 | 兩個 process 共寫 SQLite，要管兩個生命週期 | 對單一使用者是過度設計 |
| P3 作業系統排程器呼叫 CLI | 機器醒著就跑 | 設定散在 OS 層，不進 git | 不可攜，不易測 |

### 資料源

| 方案 | 優點 | 缺點 | 風險 |
| --- | --- | --- | --- |
| **D-A** fast-flights 為主，Travelpayouts 為備援（有 token 才啟用） | 主源即時且覆蓋完整；備援合法、穩定 | 兩源語意不同（即時 vs 48h 快取），不能互相替代 | 主源隨時可能壞；違反 Google 條款的灰色地帶（見下方風險定性） |
| D-B Travelpayouts 為主，fast-flights 為備援 | 主源合規 | TPE 覆蓋稀疏、非即時，「創新低」幾乎沒有意義 | 核心價值（即時低價）做不出來 |
| D-C 只用 Travelpayouts | 最合規 | 同 D-B，而且沒有即時能力 | 產品價值低 |
| D-D Amadeus | 曾是官方自助 API | 據查自助入口已停用 | **不可依賴，否決** |
| D-E 自建 Playwright 爬 Google Flights 或 OTA | 抗改版能力可能較強 | 多一個瀏覽器依賴，維護成本高，條款風險相同或更高 | 本 ADR 不採用，需要時另開 ADR |
| D-F 付費商用航班 API | 合規、穩定 | 要花錢，費率未查證 | 依交接協定，花錢須升級 CEO |

## Decision（決策）

**D-1 技術棧：採 S1。**
- 單一 Python 服務放在 `apps/flight-deals/`：FastAPI、Jinja2（autoescape 開啟）、httpx、SQLite（WAL）。
- 套件管理用 uv，品質工具 ruff、mypy strict、pytest。
- 不開 Vite/React，不新增 Node build 鏈。
- 和 stock-desk 線慣例對齊，但**不共用 code、不 import 該線任何東西**。
- 資料存取用標準函式庫 `sqlite3`，所有 SQL 集中在 `storage` 套件，schema migration 用編號 SQL 檔加 `schema_version` 表。不引入 ORM（理由：單人小 schema，少一個依賴）。
- 套件版本號（含 APScheduler 鎖 3.x 主版、fast-flights、Python 版本）由實作時以 `uv add` 查證後寫進 `pyproject.toml` 和 `uv.lock`。**本 ADR 不指定版本號。**

**D-2 資料源：採 D-A，並加三項修正。**
1. **兩源分開算。** `price_observation` 必須帶 `source` 和 `price_kind`（`live` 或 `cached`）。通知規則、「創新低」基準線、「較上次通知下跌」都只在同一個 `price_kind` 內比較。快取價永遠不能刷新即時價的歷史低點。備援是「降級資料」，不是替代品；UI 和通知都要明示「快取價，非即時，資料時間 X」。
2. **查價結果分四種狀態。** adapter 回傳 `SourceResult`，狀態為 `ok`、`no_data`、`blocked`、`error` 其中之一。fast-flights 拿到空白頁或解析不出內容時判為 `blocked`，**不得記成「沒有航班」**。
3. **降級順序。** 單次查詢：主源在重試上限內仍失敗，就對同一組日期改查備援（若備援已啟用）。`source_health` 用斷路器追蹤連續失敗：連續 N 次失敗就進 `open`，冷卻期內不打主源，冷卻後 `half_open` 試一次。
   - 主源和備援都失敗：該次掃描標記失敗；若監看連續 K 次掃描都沒有成功資料，監看狀態轉為 `stale`。
   - 維運通知「查價失敗」每個來源每個 Asia/Taipei 日最多推一次，用 dedupe key 保證。
   - N、K、冷卻時間、節流間隔、每次掃描的查詢上限都是設定值，放在 config 並附預設值。這些預設值是**本公司自訂的起始值**，不是外部規格，上線後調整。

其他規定：
- **日期取樣。** 每個監看每次掃描最多查 `max_pairs_per_scan` 組日期對（預設 12）。彈性窗產生的日期對超過上限時，採等距取樣，**每次掃描輪換偏移**，讓覆蓋率隨時間累積。本次取樣結果寫進 `scan_run.sampled_pairs`，UI 要明示。「最便宜時段」只能說是「在已取樣日期中」最便宜。
- **全域預算。** 除了單一監看的上限，再設全域每小時查詢上限。所有掃描在單一 worker thread 序列執行，查詢之間節流並加 jitter。
- **fast-flights 的使用限制。** 只能在 `sources/google_flights.py` 內 import。實作前要在安裝版本上實測 API 名稱和回傳格式，並錄成 fixture。**任何把查詢送到第三方伺服器代抓的 fetch 模式（fast-flights 的 `integration=` 參數、Bright Data、SearchApi、遠端 Playwright serverless）都禁止使用。** 需要本機無頭瀏覽器時，要另開 ADR。
- **Travelpayouts 的啟用條件。** 只有在環境變數 `FLIGHT_DEALS_TRAVELPAYOUTS_TOKEN` 存在、而且 rate limit 文章已查證並寫進 config 時才啟用。`as_of` 用來源回傳的資料時間（`found_at`）；來源沒有提供時，`as_of_basis` 記為 `fetch_time`，UI 要標「資料時間未知」，**不得用抓取時間冒充資料時間**。
- **fixture 不能上線。** `fixture` source 只在測試環境啟用；正式啟動時 config 若含 fixture，就直接拒絕啟動。
- **Amadeus：否決，不建 adapter。**

**D-3 排程：採 P1，並加三項修正。**
- 用 APScheduler 3.x 的 `BackgroundScheduler`，ThreadPool 設 1 個 worker，job 設 `coalesce=True`、`max_instances=1`。
- jobstore 用記憶體。`watch` 表是唯一真相來源：啟動時和每次 CRUD 之後，從 `watch` 表重建或更新 job。不用 SQLAlchemy jobstore。
- 每個監看的掃描間隔預設 360 分鐘，下限由 config 定。
- **「啟動時補跑一次」改為「只補跑已逾期的監看」**（`last_scanned_at + interval < now`），而且逐一錯開。理由：開發時頻繁重啟會在短時間內大量打 Google，正好是被封鎖的觸發條件。
- 排程在 FastAPI lifespan 內啟動和關閉，只允許單一 worker，啟動時要防止重複啟動。

**D-4 通知：採 `Notifier` Protocol，MVP 只實作 `telegram`。**
- LINE 留 adapter 介面但不實作。
- 用 `sendMessage` 純文字，**不設 `parse_mode`**，避免 Markdown/HTML 注入和跳脫錯誤。
- timeout 5 秒，失敗不拋出，但**一定要寫進 `notification` 表**（`status=failed`、`attempts`、遮蔽後的 `last_error`），下次掃描在重試上限內重送。
- 文案只陳述事實：航線、日期、價格、幣別、來源、資料時間、價格種類，加一句「價格為查到當下的參考值，實際以航空公司或訂票網站為準」。不含「建議購買」「快買」這類語氣。
- 同價不重推：每個（監看, `price_kind`）維護 `alert_state`，加上 `notification.dedupe_key` UNIQUE。
- 「重新武裝」規則預設：價格回升到門檻以上之後，再次跌破門檻才重推。

**D-5 安全。**
- 祕密只走環境變數：`FLIGHT_DEALS_TELEGRAM_BOT_TOKEN`、`FLIGHT_DEALS_TELEGRAM_CHAT_ID`、`FLIGHT_DEALS_TRAVELPAYOUTS_TOKEN`。`.env.example` 只放假值。
- 伺服器只綁 `127.0.0.1`，加 `TrustedHostMiddleware`，只允許 `127.0.0.1` 和 `localhost`（防 DNS rebinding；光靠綁 IP 和 CSRF header 防不住）。
- 所有寫入型請求（含 Telegram 測試發送）一律用 `fetch()` 並帶自訂 header `X-Flight-Deals-Client`，伺服端缺 header 就回 403。不使用原生 HTML form POST。
- log 從第一個 commit 起就要遮蔽：
  - httpx 和 httpcore 的 logger 等級設 WARNING 以上。
  - root logger 掛 redaction filter，遮蔽 `bot<digits>:<token>` 這類 pattern，以及所有已載入的祕密值。
  - 外部錯誤一律先經 `redact()` 才能進 log 或 DB。

**D-6 時間與金額。**
- 時間戳（`*_at`、`as_of`）一律存 UTC ISO 8601，顯示時轉 Asia/Taipei。
- **旅行日期**（出發日、回程日）是當地日曆日，存 `YYYY-MM-DD`，**不帶時區、不做時區換算**。避免把出發日當成 UTC 時間轉換而差一天。
- 金額存整數 `amount_minor` 加 ISO 4217 幣別碼。各幣別的小數位數只能在單一 `currency` 模組定義。
- **MVP 不做匯率換算。** 觀測值幣別和監看幣別不一致時，照樣記錄，但不參與通知判斷，並當成資料品質問題顯示在 UI 上。

## 總經理對 PRD 的收斂裁決（2026-10-25；CEO 2026-10-26 照現狀核可）

tech-architect 草案寫於 PRD 落地前，以下是兩者對齊後的裁決：

| 項目 | PRD | 架構草案 | 裁決 |
| --- | --- | --- | --- |
| 刪除監看（FR-A8） | 硬刪除，歷史一併移除 | 軟刪除 `archived_at` | **依 PRD 硬刪除**：外鍵 `ON DELETE CASCADE`，schema 移除 `archived_at` |
| 修改後舊歷史區分（FR-A6） | 由架構決定 | 未定 | `watch.revision` 整數，改動路線、日期、行程型態時 +1；`scan_run` 與 `price_observation` 帶 `watch_revision`；UI 把舊 revision 的紀錄標「舊設定」；通知規則的基準線只看目前 revision |
| 過期監看（FR-A9） | 自動標「已過期」 | 狀態只有 active/paused/stale | `watch.status` 加 `expired`，掃描前判定 |
| 直飛／轉機（開放問題 6） | 不納入 | — | **納入**為監看欄位 `max_stops`（NULL=不限），fast-flights 原生支援、成本極低；託運行李不做 |
| 下跌比例（開放問題 2） | 建議 5% | — | 全域預設 5%（500 bp），全域設定可調 |
| 掃描頻率（開放問題 4） | 待 CEO | 預設 360 分鐘 | 預設 360 分鐘（每日 4 次）；不用付費 API |
| 執行位置（開放問題 3） | 待 CEO | — | CEO 本機；接受「機器沒開就不掃」，README 載明 |
| Travelpayouts（CEO 決策 1） | — | 建議註冊 | **MVP 不實作該 adapter**，只留 `FlightPriceSource` port；CEO 若註冊取 token 再開第二批 |
| 降級功能（CEO 決策 4） | — | 人工查價連結、手動輸入價格 | **做「人工查價連結」**（每筆價格與每個監看都附 Google Flights 搜尋網址，純產生 URL 不抓取）；**不做手動輸入價格** |
| 無頭瀏覽器（CEO 決策 3） | — | 預設不允許 | 不允許；要用另開 ADR |
| 合併訊息筆數（FR-C9） | 由架構決定 | — | 一則訊息最多列 5 筆 |
| 過期標示時間（FR-D4） | 可設定 | — | 預設 24 小時 |

## Consequences（後果）

好處：
- 單一 process、單一 build 鏈，CEO 一個指令就能啟動。
- 資料源可以替換，主源壞了，其餘功能照常運作。
- 即時價和快取價分開記錄，通知不會因為混用而誤報「創新低」。

代價與壞處：
- **網頁沒開就不會掃描。** 筆電睡眠或關機期間的低價會錯過；補跑只能補上「現在」的價格，補不回當時的價格。
- **主源天生脆弱。** fast-flights 壞掉時，即時監看能力歸零，要等上游修好或另開 ADR 換方案。
- **只看得到取樣日期。** 彈性窗內沒被取樣的日期對看不到；「最便宜時段」是取樣下的結論，不是全量結論。
- **掃描變慢。** 所有掃描序列執行加節流，監看數量多時一輪會拉長。
- 不用 ORM，migration 要手寫。
- 不做匯率換算，非 TWD 的價格無法用於通知。

被約束的事：
- 新增資料源、通知通道、headless browser 依賴、遠端存取或多使用者需求，都要開新 ADR。

## 失效條件（任一成立就重新評估，開新 ADR 取代本則）

1. fast-flights 連續 14 天無法取得有效資料，而且上游沒有修復版本（天數由 CEO 確認）。
2. Google 對本機 IP 持續回應封鎖或 CAPTCHA。
3. 需求擴大到多使用者、遠端存取（手機外網看後台），或要部署到雲端。這時 127.0.0.1 加 header 的防線不夠，要加認證。
4. Travelpayouts 的條款、額度或資料語意改變，或者證實對 TPE 主要航線幾乎沒有覆蓋。
5. 需要匯率換算，或需要多人、多艙等。
6. 單一 process 的掃描量撐不住設定的間隔，或 SQLite 寫入衝突造成錯誤。

---

## 模組邊界與 import 方向

套件根目錄為 `apps/flight-deals/src/flight_deals/`。

| 套件 | 職責 | 可 import |
| --- | --- | --- |
| `domain/` | 純資料模型與純邏輯：日期對展開與取樣、通知規則判斷、dedupe key 產生、幣別表、查票連結產生 | 只能用 stdlib |
| `ports.py` | `FlightPriceSource`、`Notifier` 等 Protocol，以及 `SourceResult` 型別 | `domain` |
| `sources/` | `google_flights`、`fixture` 兩個 adapter（`travelpayouts` 留待第二批），含快取、節流、退避、timeout | `domain`、`ports`、`redact`；第三方只能用 httpx，fast_flights 只能在 `google_flights.py` 用 |
| `notify/` | `telegram` adapter | `domain`、`ports`、`redact`、httpx |
| `storage/` | sqlite 連線、migration、repository | `domain` |
| `services/` | 掃描流程、通知流程、健康狀態、查詢用讀取模型 | `domain`、`ports`、`storage`；**不 import 具體 adapter**，adapter 由外部注入 |
| `scheduler/` | APScheduler 接線 | `services` |
| `web/` | FastAPI routes、Jinja2 templates、靜態 JS | `services`；**不直接 import `storage`、`sources`、`notify`** |
| `config.py`、`logging_setup.py`、`redact.py` | 讀環境變數設定、log 遮蔽 | 只能用 stdlib |
| `app.py`（composition root） | **唯一**組裝具體 adapter、建立 FastAPI app 和排程的地方 | 全部 |

方向只能往下：`web` 或 `scheduler` → `services` → `ports` 或 `storage` → `domain`。禁止反向 import，禁止循環 import。
實作上用一支 pytest 以 `ast` 掃描 import，不新增依賴，進 CI。

## 資料表 schema 草案（SQLite，WAL，`foreign_keys=ON`，設 `busy_timeout`）

```sql
CREATE TABLE watch (
  id INTEGER PRIMARY KEY,
  name TEXT NOT NULL,
  origin TEXT NOT NULL DEFAULT 'TPE' CHECK (length(origin) = 3),
  destination TEXT NOT NULL CHECK (length(destination) = 3),
  trip_type TEXT NOT NULL CHECK (trip_type IN ('round_trip','one_way')),
  date_mode TEXT NOT NULL CHECK (date_mode IN ('fixed','flexible')),
  depart_date TEXT, return_date TEXT,                -- fixed mode, local calendar date YYYY-MM-DD
  window_start TEXT, window_end TEXT,                -- flexible mode, local calendar dates
  min_trip_days INTEGER, max_trip_days INTEGER,
  max_stops INTEGER,                                 -- NULL = any
  cabin TEXT NOT NULL DEFAULT 'economy' CHECK (cabin = 'economy'),
  adults INTEGER NOT NULL DEFAULT 1 CHECK (adults = 1),
  currency TEXT NOT NULL DEFAULT 'TWD',
  budget_amount_minor INTEGER,                       -- NULL = no budget rule
  notify_on_new_low INTEGER NOT NULL DEFAULT 1,
  scan_interval_minutes INTEGER NOT NULL DEFAULT 360,
  status TEXT NOT NULL DEFAULT 'active' CHECK (status IN ('active','paused','stale','expired')),
  revision INTEGER NOT NULL DEFAULT 1,
  sample_offset INTEGER NOT NULL DEFAULT 0,          -- rotating sampling cursor
  last_scanned_at TEXT,                              -- UTC
  created_at TEXT NOT NULL, updated_at TEXT NOT NULL
);

CREATE TABLE scan_run (
  id INTEGER PRIMARY KEY,
  watch_id INTEGER NOT NULL REFERENCES watch(id) ON DELETE CASCADE,
  watch_revision INTEGER NOT NULL,
  started_at TEXT NOT NULL, finished_at TEXT,
  status TEXT NOT NULL CHECK (status IN ('running','ok','partial','failed')),
  sampled_pairs TEXT NOT NULL,                       -- JSON [[depart, return|null], ...]
  query_results TEXT NOT NULL DEFAULT '[]',          -- JSON per pair: source, status(ok/no_data/blocked/error)
  queries_used INTEGER NOT NULL DEFAULT 0,
  error_summary TEXT                                 -- redacted, truncated
);

CREATE TABLE price_observation (
  id INTEGER PRIMARY KEY,
  scan_run_id INTEGER NOT NULL REFERENCES scan_run(id) ON DELETE CASCADE,
  watch_id INTEGER NOT NULL REFERENCES watch(id) ON DELETE CASCADE,
  watch_revision INTEGER NOT NULL,
  source TEXT NOT NULL,                              -- 'google_flights' | 'travelpayouts'
  price_kind TEXT NOT NULL CHECK (price_kind IN ('live','cached')),
  depart_date TEXT NOT NULL, return_date TEXT,
  amount_minor INTEGER NOT NULL CHECK (amount_minor > 0),
  currency TEXT NOT NULL,
  as_of TEXT NOT NULL,                               -- UTC
  as_of_basis TEXT NOT NULL CHECK (as_of_basis IN ('source_reported','fetch_time')),
  fetched_at TEXT NOT NULL,                          -- UTC
  carrier TEXT, stops INTEGER, duration_minutes INTEGER
);
CREATE INDEX ix_obs_watch_pair ON price_observation(watch_id, price_kind, depart_date, return_date, fetched_at);
CREATE INDEX ix_obs_watch_price ON price_observation(watch_id, price_kind, amount_minor);

CREATE TABLE alert_state (
  watch_id INTEGER NOT NULL REFERENCES watch(id) ON DELETE CASCADE,
  price_kind TEXT NOT NULL,
  last_notified_amount_minor INTEGER,
  last_notified_at TEXT,
  armed INTEGER NOT NULL DEFAULT 1,
  PRIMARY KEY (watch_id, price_kind)
);

CREATE TABLE notification (
  id INTEGER PRIMARY KEY,
  watch_id INTEGER REFERENCES watch(id) ON DELETE CASCADE,  -- NULL for ops / test
  kind TEXT NOT NULL CHECK (kind IN ('price_alert','ops_source_failure','test','daily_digest')),  -- daily_digest 由 migration 0002 加入
  rule TEXT CHECK (rule IN ('below_budget','drop_pct','new_low')),
  observation_id INTEGER REFERENCES price_observation(id) ON DELETE SET NULL,
  channel TEXT NOT NULL DEFAULT 'telegram',
  dedupe_key TEXT NOT NULL UNIQUE,                   -- e.g. 'ops:google_flights:2026-10-25' (Asia/Taipei date)
  status TEXT NOT NULL CHECK (status IN ('pending','sent','failed','suppressed')),
  attempts INTEGER NOT NULL DEFAULT 0,
  message_text TEXT NOT NULL,
  created_at TEXT NOT NULL, sent_at TEXT,
  last_error TEXT                                    -- redacted
);

CREATE TABLE source_health (
  source TEXT PRIMARY KEY,
  enabled INTEGER NOT NULL,
  breaker_state TEXT NOT NULL CHECK (breaker_state IN ('closed','open','half_open')),
  consecutive_failures INTEGER NOT NULL DEFAULT 0,
  open_until TEXT,
  last_success_at TEXT, last_failure_at TEXT,
  last_error TEXT                                    -- redacted, truncated
);

CREATE TABLE app_setting (key TEXT PRIMARY KEY, value TEXT NOT NULL, updated_at TEXT NOT NULL);
CREATE TABLE schema_version (version INTEGER NOT NULL);
```

說明：
- `scan_run`（UI 顯示「本次取樣日期」和逐組查詢結果需要它）、`alert_state`（同價不重推需要它）、`app_setting`（FR-E4 全域設定）、`schema_version`。
- `test` 類通知的 dedupe_key 要含時間戳，才能每次都送出。

## 對實作的約束（qa-reviewer 可逐條檢查）

- **C-1** `apps/flight-deals/` 底下沒有 `package.json`、Vite 或 React。
- **C-2** `fast_flights` 只出現在 `sources/google_flights.py`（grep 可驗）。
- **C-3** 自動 import 方向測試存在且通過；`web/` 沒有 import `storage`、`sources`、`notify`。
- **C-4** 每個 adapter 都有：timeout、指數退避且有重試上限、客戶端節流、TTL 快取、fixture 契約測試。契約測試要驗 `source`、`as_of`、`price_kind`、`amount_minor`（int）、`currency`。
- **C-5** 測試全程不連外網：conftest 擋 socket 連線。真實連線的 smoke 測試標成 opt-in marker，由人執行。
- **C-6** 空白頁或解析失敗回 `blocked`，有測試覆蓋，而且不會寫出 `price_observation`。
- **C-7** 排程在 lifespan 內啟動；設 `coalesce`、`max_instances=1`、單一 worker thread；有防止重複啟動的機制；啟動時只補跑逾期監看，而且錯開。
- **C-8** 通知判斷只比較同一個 `price_kind`，有測試覆蓋「快取價不刷新即時價歷史低點」。
- **C-9** `dedupe_key` 有 UNIQUE 約束；維運通知每個來源每個 Asia/Taipei 日最多一則，有測試。
- **C-10** Telegram 請求沒有 `parse_mode`；失敗時寫進 `notification.status=failed`，不拋出。
- **C-11** 有測試證明：用假 token 觸發 httpx 錯誤和 log 時，輸出（log 與 DB 的 `last_error`）不含 token 原文。
- **C-12** 只綁 127.0.0.1；有 Host 白名單；寫入路由缺自訂 header 時回 403，有測試。
- **C-13** 時間戳全部是 UTC；旅行日期沒有任何時區換算；金額是整數，沒有 float 存價。
- **C-14** 原生 JS 只放 `web/static/`，不引入前端框架，不從外部 CDN 載入。
- **C-15** 正式 config 含 `fixture` source 時拒絕啟動，有測試。
- **C-16** 產品 `.gitignore` 加上 `.venv/`、`*.sqlite*`、`*.db`、資料目錄。
- **C-17** 通知與 UI 文案沒有建議語氣；文案模板定稿後交 risk-compliance-officer 看一次。純事實價格通知預期是「不適用」，由他確認。
- **C-18** 依賴版本鎖在 `uv.lock`；ADR 和程式碼註解不寫死外部額度數字。

---

## fast-flights 抓 Google Flights 的風險定性

- **技術面：高風險，判定為「一定會壞，只是不知道什麼時候」。**
  - 它是反向工程的非官方 protobuf 介面，版本間 API 已經改過，純 requests 可能拿到空白頁。
  - 會壞的訊號是 `blocked` 和 `error` 比率上升，交給斷路器和 `source_health` 處理，不要當成例外狀況。
- **服務條款面：中度風險，灰色地帶，這不是法律意見。**
  - Google 的服務條款一般性禁止透過 Google 提供的介面以外的方式自動存取服務；Google Flights 沒有公開 API。以上兩點**依記憶，未查證**，請 risk-compliance-officer 對照現行條款確認。
  - 實際影響：不需要登入，所以沒有帳號被停權的風險；主要後果是本機 IP 被節流或要求 CAPTCHA，以及使用行為本身牴觸條款。
  - 個人、低頻使用時，實務上被追究的機率低，**但不會因此變成合規**。
- **因此限定以下條件**，任一被打破，這個方案就失效：
  1. 只限 CEO 個人本機使用。
  2. 不公開部署、不散布、不商業化、不轉售資料。
  3. 低頻使用（D-2、D-3 的上限和節流）。
  4. 不使用第三方代抓。
- **fast-flights 壞掉時，產品還能交付什麼：**
  1. 監看 CRUD、價格歷史（停在最後一筆）、取樣紀錄，全部照常。
  2. 資料源健康頁明示主源故障，監看轉 `stale`，Telegram 每天最多一則維運通知。CEO 會知道「沒消息」不等於「沒降價」。
  3. 有 Travelpayouts token 且第二批已實作時，繼續推快取價通知，明確標示非即時。
  4. 每個監看與每筆價格都有「人工查價連結」，CEO 點了自己去看。這只是產生網址給人點，不是抓取。
  - 交付不了的部分：即時、全覆蓋的自動低價偵測。這是產品的核心價值，主源壞掉期間就是降級營運。

## 實作期偏離紀錄（2026-10-25 第一批，dev-lead 回報、qa-reviewer 評估「全部可接受」，CEO 核可本 ADR 時一併確認）

| 項目 | ADR 原文 | 實作 | 理由 |
| --- | --- | --- | --- |
| 掃描間隔 | D-3 每個監看各自 `scan_interval_minutes` | 改為全域設定（`app_setting`），`watch` 表無此欄 | 單一使用者，逐監看設定是過度設計；**這是 D-3 字面變更，CEO 須知情** |
| schema 增補 | — | `watch.consecutive_failed_scans`；`scan_run.trigger / total_pairs / limit_reached / global_limit_reached / queries_used`；`notification.price_kind`；新表 `notification_item`（合併通知內每組日期與價格，供 FR-C3 同組合同價去重）、`scheduler_event`（記錄被略過的重疊掃描） | FR-B3／B7／C3／E5 需要這些欄位 |
| 金額 | D-6 整數 `amount_minor` | TWD 依 ISO 4217 取 2 位小數，`amount_minor = TWD × 100` | 幣別小數位只在 `domain/currency.py` 定義 |
| 觀測筆數 | — | 每輪每組日期只存最便宜一筆報價 | 控制資料量；詳情頁只需最低價 |
| 推播重試 | D-4 下次掃描重送 | 在下一輪掃描**開頭**重試，不在同一輪結尾 | 避免同一輪重複觸發 |
| Telegram 未設定 | — | 通知標為 `suppressed`：不重試、不佔去重額度 | 日後設定好也不補發，README 載明 |
| 首次掃描 | D-3 只補跑逾期 | 新增監看後 10 秒排第一次掃描 | 讓使用者建立後很快看到結果；仍受全域每小時上限 |
| 立即查價 | — | 經 scheduler 非同步執行，API 回 202 | 不阻塞請求 |
| 預設 port | — | 8795（原 8765 被 CEO 本機另一專案占用） | 2026-10-26 實機驗收時發現 |

qa-reviewer 列為第二批前必修（加 Travelpayouts 之前）：多來源時第一個來源失敗後備援成功仍記 `partial`；`no_data` 與幣別不符會直接 return 不試備援；`item_key`／`dedupe_key` 不含 `watch_revision`。

## 需要 CEO 決定的事項

CEO 2026-10-26 回覆：ADR 與收斂裁決照現狀核可（第 5 項）。第 1～4 項未另行指示，依本 ADR 預設執行：不註冊 Travelpayouts、不引入無頭瀏覽器、不設登入自動啟動；fast-flights 的使用限制以 README「使用限制（必讀）」為準。任一項日後可翻案，翻案時更新本節。

1. **要不要註冊 Travelpayouts 帳號取 token？** 建議要，它是唯一合規又免費的備援。有 token 後由 data-engineer 用 CEO 最常看的 3～5 條航線做一次覆蓋率探測，再決定值不值得依賴。
2. **要不要書面確認接受 fast-flights 的條款灰色風險？** 這包含接受「只限個人本機、不得公開或散布」的限制。
3. **如果純 requests 長期拿空白頁，要不要允許引入本機無頭瀏覽器（Playwright 等）？** 預設不允許，要允許就另開 ADR。第三方遠端代抓模式直接禁止。
4. **機器沒開就不會掃描，這個限制能不能接受？** 要不要由 devops-sre 設定登入時自動啟動？
5. 上表「總經理對 PRD 的收斂裁決」各項是否同意。

---

## 附錄：本機實測（總經理，2026-10-25，Windows 11、Python 3.11、fast-flights 3.1.0）

- 安裝：`fast-flights 3.1.0` 帶入 `primp 2.0.1`、`protobuf 7.36.2`、`selectolax 1.0.2`；**套件漏宣告 `typing_extensions` 相依**，import 會失敗，`pyproject.toml` 必須顯式加入。
- API：`from fast_flights import FlightQuery, Passengers, create_query, get_flights`；`create_query(flights=[FlightQuery(date="YYYY-MM-DD", from_airport, to_airport, max_stops=...)], seat="economy", trip="one-way"|"round-trip", passengers=Passengers(adults=1), language="zh-TW", currency="TWD")` → `get_flights(query)` 回 `fast_flights.parser.ResultList`（list 子類，另有 `.metadata` 含航空公司代碼與中文名）。
- 單筆元素是 dataclass `fast_flights.model.Flights`，欄位 `type`（航空公司二碼）、`price`（int，已是要求的幣別）、`airlines`（名稱 list）、`flights`（航段 list，每段有 `from_airport{code,name}`、`to_airport`、`departure{date:(y,m,d), time:(h,m)}`、`arrival`、`duration` 分鐘、`plane_type`）、`carbon`。**回傳不含訂票深層連結**，FR-D5 的查票連結要自行組 Google Flights 搜尋網址。
- 實測：TPE→NRT 單程 0.9 秒 18 筆；來回 1.0 秒 18 筆；TPE→BKK 連續 5 天 5 次查詢各 0.6 秒、皆成功，未見封鎖。
- 錯誤行為：過去日期拋 `fast_flights.FlightsNotFound`（訊息 `no flights found; received error`）；不存在的機場代碼拋 `IndexError`（套件內部解析失敗）。adapter 必須攔截廣義例外並依 D-2 分類為 `no_data` / `blocked` / `error`。
- 實測錄下的來回程 fixture 存在總經理暫存區，交由 dev-lead 複製進 `tests/fixtures/`。

## FD-2 增補：機場中文名稱自動完成（2026-10-26，tech-architect 評估；不另開 ADR；總經理落檔）

範圍：出發地／目的地欄位的中英文與代碼自動完成，列表、詳情、推播改顯示「中文短名 代碼」。屬 D-1 範圍：不新增依賴，模組邊界、資料源、schema 都不變。

決策：
- 對照表為 `domain/airports.py` 內的 frozen dataclass 常數（否決 JSON 資料檔：domain 維持沒有 I/O，型別交給 mypy 檢查）。欄位：`code`、`kind`（airport|city）、`city_code`、`zh_name`、`display_name`、`en_name`、`country_zh`、`aliases`、`city_query_verified`、`verified_note`。代碼全表唯一；IATA 城市碼與機場碼撞碼時只保留機場列。
- 搜尋與排序是 domain 純函式；端點 `GET /api/airports?q=` 經 `services/airports.py` 轉呼叫（`web` 依 `test_architecture.py` 不得直接 import `domain`）。排序：代碼完全命中 > 中文前綴 > 英文前綴 > 包含，同層依表內順序，最多 10 筆。否決「整表送前端由 JS 排序」，因為規則會有兩份實作。
- 城市代碼只有經實測可查價者（`city_query_verified=True`）可選。2026-10-26 fast-flights 3.1.0 實測：TYO、OSA 成功；LON 失敗（套件內部 IndexError），不開放。其他城市由 dev-lead 批次實測後逐筆開放，每筆附 `verified_note`。
- 顯示名稱在讀取時由 `route_label` 推導，不寫進 DB；表外代碼回退成只顯示代碼。修改監看時，舊代碼沒改動可豁免對照表檢查；掃描不受影響。
- 推播只加事實性地名，C-17 判定不重新送審；新字串納入 BANNED_PHRASES 測試。
- 總經理裁決（PM 開放問題，CEO 可翻案）：空欄位不列常用項；同城市群組互飛拒絕；舊監看修改時，未改動的舊代碼可豁免對照表檢查（依 C-21；改成別的代碼就必須在表內）；TPE 短名「台北桃園」、TSA「台北松山」；收錄範圍 100～150 筆（台灣、日、韓、港澳、東南亞、中國主要城市、歐美大洋洲主要城市）。

新增約束：
- **C-19** 對照表每筆 `code` 符合 `^[A-Z]{3}$` 且全表唯一；`city_code` 只出現在機場且指向 `kind=city`；`city_query_verified=True` 必附 `verified_note`；`display_name` 不超過 8 字。有測試。
- **C-20** `GET /api/airports` 任何輸入都不回傳超過 10 筆；`q` 超過 32 字元回 422；回應帶 `Cache-Control`。有測試。
- **C-21** 出發地／目的地必須在對照表內且可選（未驗證的城市不可選）；同城市群組不可互飛；只有修改時沿用的舊代碼可豁免。有測試。
- **C-22** 排序與筆數上限只在 `domain/airports.py` 定義；`web/static/app.js` 不含比對或排序邏輯，不使用 `innerHTML`。
- **C-23** 對照表檔頭載明出處、查證日期、查證人；每筆代碼對照 IATA 官方查詢頁，不得憑記憶填寫；qa-reviewer 抽查至少 15 筆或 10%（取較多者），結果記在任務單。
- **C-24** FD-2 不新增 migration、不新增執行期依賴；`domain/links.py` 查票連結維持用代碼。
- **C-25** 推播訊息在 5 筆、最長 `display_name` 的情況下長度小於 `notify/telegram.py` 的 `MAX_MESSAGE_LENGTH`。有測試。

## FD-3 增補：查價穩定性與體驗修補（2026-10-26，tech-architect 評估；不另開 ADR；總經理落檔）

範圍：fast-flights 部分結果無價格時整批失敗、同一 DB 重複啟動排程、立即查價後需手動重新整理、403／400 回應缺安全標頭。屬 D-2、D-3、D-5 範圍內的修補：不新增依賴、不新增 migration、不改模組 import 方向。

### Context
- 2026-10-26 實測（fast-flights 3.1.0）：上游 `parse_js` 對每筆結果讀 `k[1][0][1]` 當價格；TPE→SHA 4 筆中有 2 筆（廈門航空經 XMN）的 `k[1]` 是 `[[], "<token>"]`，拋 `IndexError`，整批被判為 `blocked`，有價格的 2 筆（TWD 12,655、14,763）一併遺失。原始 payload 錄為 `tests/fixtures/payload_TPE_SHA.json`。
- 排程防重複啟動目前只在單一 process 內有效；同一 DB 開兩個實例會雙重掃描。
- 立即查價回 202 後頁面不會更新。
- TrustedHost 的 400 與缺 header 的 403 都沒有安全標頭。

### Decision
1. **容錯解析（方案 A）。** `sources/google_flights.py` 改呼叫公開 API `fetch_flights_html` 取得 HTML，解析交給純函式模組 `sources/google_payload.py`（stdlib only、無 I/O，輸出沿用 `_records.py` 的 record 形狀）。只解析價格（必要）與航空公司、轉機數、時長（選用，取不到填 None）。逐筆分 priced／unpriced（只認實測形狀 `k[1][0] == []`）／malformed。否決「先 `get_flights` 失敗再 fallback」與「只等上游」（另行向上游回報）。C-2 不變；解析在 `call_with_timeout` 之外。
2. **狀態判定細化（D-2 第 2 點與 C-6 的解讀）。** 找不到 `script.ds:1`、JSON 失敗或頂層形狀不符 → `blocked`；`errorHasStatus` 或 `payload[3][0] is None` → `no_data`；有 itinerary 但 0 筆有價格且無 malformed → `no_data`（`all_unpriced`）；0 筆有價格且有 malformed → `blocked`；≥1 筆有價格 → `ok` 附計數。`no_data` 不計入斷路器失敗。實作補充（dev-lead 2026-10-26，qa-reviewer 同意）：抓取階段（`fetch_flights_html` 本身）拋出的例外一律判 `error`（可重試、計入斷路器）；`payload[3][0] == []`（空清單）判 `blocked`，只有 `None` 才是 `no_data`。
3. **計數可見。** `ports.ParseStats(itineraries, priced, unpriced, malformed)` 掛在 `SourceResult.parse_stats`；`scan_run.query_results` 的 try 存整數計數，說明文字由 `services/views.py` 讀取時組成；只有 unpriced 時不寫 `error_summary`。
4. **版本絆線。** pyproject 維持 `<4`；`google_flights.py` 的 `VERIFIED_FAST_FLIGHTS_VERSION` 必須等於安裝版本（測試以 `importlib.metadata` 比對），升級時重跑 live smoke 並重錄 fixture。fetch 模式禁令擴及 `fetch_integration` 參數。
5. **跨 process 排程鎖（D-3 擴充）。** 鎖檔 `<db_path>.lock`，Windows `msvcrt.locking`（非阻塞、位移放檔頭之後），其他平台 `fcntl.flock`；process 結束 OS 自動釋放，殘留鎖檔無害、永不刪除。否決 `O_EXCL`+PID（PID 重用；Windows `os.kill(pid,0)` 會終止對方）。實作在 `scheduler/lock.py`（stdlib），路徑由 `app.py` 推導並注入；`cli.main` 在建 app 與 migrate 之前取鎖，失敗印原因並 exit 2。否決「第二實例只開網頁」（記憶體 jobstore 不跨 process 同步，CRUD 與立即查價會無聲失效）。
6. **立即查價自動更新。** 新增 `GET /api/watches/{id}/scan-status`（白名單欄位 `watch_id`、`scan_run_id`、`status`、`started_at`、`finished_at`；`Cache-Control: no-store`；不需 client header；404 於監看不存在）。前端先取基準 id 再 POST，每 2 秒輪詢、上限 90 秒，id 變化且非 running 就 reload；逾時提示不暗示失敗。
7. **安全標頭（D-5 補強）。** 純 ASGI `SecurityHeadersMiddleware` 放使用者 middleware 最外層，順序由外到內：SecurityHeaders → TrustedHost → ClientHeader(403) → router；只補缺少的標頭。500 由 `ServerErrorMiddleware` 產生、包不到，明文排除。

### Consequences
- 好處：部分無價格航線恢復可用且略過筆數可見；同一 DB 不可能雙重排程；立即查價結果自動呈現；非 500 回應都帶安全標頭。
- 代價：Google payload 格式改由我們維護（靠 fixture 契約測試、malformed 計數、live smoke 發現漂移）；`no_data` 盲點（軟性封鎖看不出）；malformed 被略過時最低價可能偏高（只會漏報不會誤報）；鎖不支援網路磁碟；慢查價超過 90 秒仍要手動重新整理；500 頁無安全標頭。

### 新增約束
- **C-26** `sources/google_payload.py` 只 import stdlib、全文無 `fast_flights` 字串；`google_flights.py` 不再 import `get_flights`；以 `payload_TPE_SHA.json` 契約測試（itineraries=4、priced=2、unpriced=2、malformed=0、金額 1265500／1476300）；至少四種變體（全無價格、價格非 int、`payload[3][0]=None`、頂層形狀錯）與 `extract_payload` 五種 HTML 案例；解析在 timeout 之外。
- **C-27** 狀態判定逐列有測試；`no_data` 不增加 `consecutive_failures`；google source 每個非 error 結果都有 `parse_stats`；`query_results` 只存整數計數、說明文字由 views 組成；只有 unpriced 時 `error_summary` 為 NULL；不得寫出 0 元或虛構價格。
- **C-28** 鎖在 `scheduler/lock.py`（stdlib）；`scheduler/` 不 import `storage`；路徑在 `app.py` 推導；`cli.main` 在 `create_app` 前取鎖、失敗 return 2；無「啟動排程但未持鎖」路徑；不刪鎖檔、不用 `os.kill`；測試涵蓋假鎖、同 process 互斥、子程序持鎖互斥、子程序 `os._exit` 後可取得；`.gitignore` 含 `*.db.lock`。
- **C-29** 安全標頭由純 ASGI middleware 加上、為最後一個 `add_middleware`；400（Host）、403、404、422、`/static/` 都帶齊四個標頭且各有測試；route 自設同名標頭不被覆蓋；500 排除。
- **C-30** scan-status 端點只回五個白名單欄位、`no-store`、404、不需 header、無寫入，各有測試；前端輪詢 ≥2 秒、≤90 秒、完成 reload、逾時提示無「失敗」字樣、無 `innerHTML`。
- **C-31** `VERIFIED_FAST_FLIGHTS_VERSION` 存在且測試比對安裝版本；`test_no_third_party_fetch_modes` 加 `fetch_integration`；pyproject 維持 `<4`。

## FD-4 增補：通知與維運體驗（2026-10-26，tech-architect 評估；不另開 ADR；總經理落檔）

範圍：每日摘要推播、`telegram-setup` CLI、Windows 登入自動啟動、列表漲跌。屬 D-3、D-4、D-5 範圍。不新增執行期依賴；新增 migration 0002；新增頂層 stdlib 模組 `autostart.py`。
**翻案：**「需要 CEO 決定的事項」第 4 項（不設登入自動啟動）改為「提供安裝腳本，使用者自行安裝」；CEO 2026-10-26 指示「下一批開始開發」時已知此方向。

### Context
- `notification.kind` 的 CHECK 不含 `daily_digest`；SQLite 無法修改 CHECK，只能重建表。
- 現行 migration runner 用 `foreign_keys=ON` 的連線並把整段 SQL 包在 `BEGIN` 內（`storage/db.py:36,72`）。此狀態下 `DROP TABLE notification` 會經 CASCADE 刪光 `notification_item`；`ALTER TABLE RENAME` 會改寫子表 FK；transaction 內設 `PRAGMA foreign_keys` 不生效。
- 列表最低價是「目前 revision、即時價、監看幣別、各日期對最新一筆」再取最低（簡稱快照）。彈性窗每輪輪換取樣，所以「每輪最低價」不能拿來比漲跌。
- 記憶體 jobstore 啟動時從「現在」重算下次執行時間，關機期間錯過的 cron 不算 misfire。
- 本機實測（總經理 2026-10-26）：uv 建的 `.venv\Scripts\pythonw.exe` 存在；APScheduler 3.11.3 的 `CronTrigger` 接受 `timezone=`。schtasks 的 ONLOGON 權限與預設電源／72 小時條件依記憶未查證，且偵測需跑子程序，故不採。

### Decision
1. **每日摘要排程。** 唯一送出入口是 `services/digest.py` 的 `DigestService.send_if_due(now)`（冪等）：摘要已啟用、台北時間已過今天的摘要時間、`digest:<Asia/Taipei 日期>` key 尚不存在，三者成立才送；只補當天、不補前一天。呼叫時機：cron job `daily-digest`（`CronTrigger(hour, minute, timezone=Asia/Taipei)`）、啟動時一次性 `digest-catchup`（排在補跑掃描之後）、每小時 `digest-check`（處理睡眠喚醒）、設定變更時排一次性 job。所有送出在 scheduler 單一 worker 上執行，web request thread 不得送摘要，設定 listener 只排 job。`next_run_time()`（健康頁下次掃描）排除摘要 job。時區常數由 `services` 轉出給 `scheduler`。
2. **摘要設定。** `app_setting` 新增 `digest_enabled`（`"0"/"1"`）、`digest_time`（`"HH:MM"`）；預設放 `config.Tunables`（啟用、`08:00`）。驗證在 `domain/validation.py`：時間 `^([01]\d|2[0-3]):[0-5]\d$`；開關只接受 bool 或 `"0"/"1"/"true"/"false"`；DB 值不合法回預設。整數設定與摘要設定的 key 清單分開。沿用 `on_settings_changed` 重建 `daily-digest` 並排一次補推檢查。
3. **去重、狀態與重送。** dedupe key `digest:<YYYY-MM-DD>`（Asia/Taipei，`domain/rules.py::digest_key`）。Telegram 未設定記 `suppressed`、視為今日已處理。失敗由 `retry_pending` 重送，條件為嘗試次數未達上限且 key 日期等於今天；跨日不再送。摘要的 `watch_id`、`rule`、`price_kind`、`observation_id` 皆 NULL。
4. **Migration 0002（重建 `notification`）。** 依 SQLite 官方 12 步：建 `notification_new`（kind CHECK 加 `daily_digest`，其餘相同）→ 複製 → 刪舊表 → 改名 → 重建索引。runner 擴充：migration 檔首行 `-- flight-deals: foreign_keys=off` 時在 `BEGIN` 前設 `PRAGMA foreign_keys=OFF`；COMMIT 前執行 `PRAGMA foreign_key_check`，有列就 ROLLBACK 拋出；寫入 `schema_version` 後 COMMIT；關閉連線。既有 DB（版本 ≥1）套用前先以 `Connection.backup()` 備份為 `<stem>.pre-v<N>.db`。應用層以 `Literal` 收斂 kind。
5. **快照與漲跌（列表、摘要共用）。** 快照抽成 `services/price_snapshot.py`（純 Python，輸入已載入的觀測）：只取目前 revision、`live`、監看幣別、`depart_date ≥ 今日（Asia/Taipei）`，各日期對最新一筆。**列表最低價一併改成排除已出發日期**（行為變更）。列表「較前一輪」：R 為符合條件觀測的最大 `scan_run_id`，拿全部快照最低價減 `scan_run_id < R` 的快照最低價；無前一輪「—」。摘要「較前一日」：目前快照最低價減 `fetched_at` 早於今日台北 00:00 的快照最低價。只輸出整數 `delta_minor` 與方向（up/down/flat），不做 float 百分比。不新增逐監看查詢。
6. **摘要組字。** 純函式 `domain/messages.py::daily_digest_message`，輸入 domain frozen dataclass（`DigestRow`、`DigestSourceRow`）。每個啟用中監看（`active`、`stale`）一行（名稱 >20 字截斷、路線、快照最低價與日期、漲跌、資料過舊標記、stale 標記；無價格寫「尚無價格」）。表頭／表尾：資料源狀態標籤（不放 `last_error`）、上次掃描台北時間、24 小時內 `failed` 的 `scan_run` 筆數（單一 COUNT）、漲跌定義、`DISCLAIMER`、`SAMPLED_ONLY_NOTE`。無監看送短訊。最多 `DIGEST_MAX_WATCH_LINES=20` 行，超過加「另有 N 個監看未列出」；整則 > `DIGEST_MAX_CHARS=3800` 從尾端刪監看行並更新 N；表尾永遠保留。摘要文字不經 `redact`。新模板依 C-17 送 risk-compliance-officer。
7. **`flight-deals telegram-setup`。** `notify/telegram.py` 新增 `TelegramSetupClient`（`get_updates(offset, long_poll_seconds)` 永不拋出、回候選聊天與遮蔽錯誤；`send_test(chat_id)`；timeout 大於 long-poll；401／409 各有說明）。`app.py` 匯出 `build_telegram_setup_client(token, *, transport=None)`，先 `register_secret(token)`。`cli.py` 改 subparsers（無子命令照舊啟動）。token 先讀 env／`.env`，沒有就 `getpass`；不接受 argv。輪詢最多 60 秒（`monotonic`、`sleep` 可注入）；多個聊天列出讓使用者選；`print` 輸出 `FLIGHT_DEALS_TELEGRAM_CHAT_ID=<id>`；`input` 詢問是否送測試。結束碼 0／1／2。不寫檔、不取鎖、不建 app、不開 DB。
8. **登入自動啟動。** 新增頂層 stdlib 模組 `autostart.py`（`expected_command(project_dir)` 回 `"<project>\.venv\Scripts\pythonw.exe" -m flight_deals.cli --background`；`install`／`uninstall`／`status` 只操作 `HKCU\Software\Microsoft\Windows\CurrentVersion\Run` 的 `flight-deals` 值；registry 介面可注入）。`ports.py` 新增 `AutostartProbe` Protocol 與 `AutostartStatus(registered, points_here)`；`app.py` 注入 `ViewService`；非 Windows 或例外回 None，頁面不顯示。CLI 子命令 `autostart install|uninstall|status`；`install-autostart.bat`／`uninstall-autostart.bat` 只呼叫 `uv run --project "%~dp0." flight-deals autostart ...`；install 前確認 `pythonw.exe` 存在。`--background` 模式：log 寫 DB 同目錄 `flight-deals.log`（RotatingFileHandler，掛 `RedactingFilter` 與 `RedactingFormatter`），不用 stdout／stderr；鎖被佔用時寫 log 並 exit 2。`load_config` 遇相對 `FLIGHT_DEALS_DB_PATH` 以 `PROJECT_DIR` 為基準。`dev-up.bat` 的程序偵測要實測涵蓋 pythonw 背景實例。

### Consequences
- 好處：機器開著就會每天固定時間收到摘要，關機或睡眠錯過的當天補上；Telegram 設定不必翻 API；登入後背景啟動、不提權、無視窗；列表漲跌與顯示價格語意一致。
- 代價：migration runner 變複雜、首次升級多一個備份檔；改摘要時間後可能立刻補推；摘要用快照最低價可能含久未重查的日期對（靠「資料已過舊」標記）；列表最低價改排除已出發日期；自動啟動偵測不到「在工作管理員被停用」；背景實例只能看 log 檔；`.venv` 被刪會無聲失敗；睡眠時仍不掃描。
- 被約束的事：改用 schtasks、VBScript、或讓伺服器執行期跑子程序，都要回到本節重評。

### 新增約束
- **C-32 摘要排程、設定、去重**：`send_if_due` 是唯一送出入口且冪等，假時鐘測試涵蓋準點、關機補推、睡眠喚醒補推、同日第二次不送、跨日不補、停用不送、改時間重排、suppressed 視為已處理、失敗只在同日重送；dedupe key `digest:<日期>` 有 UNIQUE 測試；設定 listener 不直接送（測試斷言無 notifier 呼叫）；`next_run_time()` 排除摘要 job；`digest_time` 拒絕 `8:00`、`24:00`、`08:00:00`、空字串，`digest_enabled` 拒絕 `"yes"`，DB 值不合法回預設；`scheduler/` 仍只 import `services`。
- **C-33 Migration 0002**：測試在已有資料的 v1 DB（≥1 筆 notification、2 筆 notification_item）上遷移後筆數不變、`daily_digest` 可寫、不合法 kind 仍拒；`notification_item` 插入不存在的 id 失敗（FK 仍有效）；`foreign_key_check` 為空；索引存在；備份檔在 DB 同目錄且符合 `*.db` gitignore；新 DB 不產生備份；不得在 `foreign_keys=ON` 下 DROP／RENAME `notification`。
- **C-34 快照、漲跌與摘要組字**：快照只在 `services/price_snapshot.py`（`latest_per_pair` 定義只能一處）；已出發日期排除有測試；漲跌只用整數；`list_page` SQL 次數不比 FD-3 多（計數 fake repository）；`daily_digest_message` 在 domain、無 I/O；200 監看／80 字名稱／最長 display_name 下長度 < `MAX_MESSAGE_LENGTH`、含 `DISCLAIMER` 與「另有」、≤20 行；無監看短訊有測試；新字串納入 `all_static_texts()` 通過 BANNED_PHRASES；摘要不含 `last_error`；通知紀錄頁 kind 標籤「每日摘要」；風控結論記任務單。
- **C-35 telegram-setup**：`cli` 的 ALLOWED 只多 `autostart`，不含 `notify`、`redact`、`domain`；`getUpdates` 只在 `notify/telegram.py`；token 不從 argv；MockTransport 測成功、多候選、60 秒逾時（假 monotonic）、401、409、httpx 例外，每種情況 stdout／stderr／caplog 不含 token；monkeypatch `input`、`getpass`；子命令不呼叫 `acquire_scheduler_lock`、`create_app`、`Database`（monkeypatch 一呼叫就失敗）；不寫檔。
- **C-36 自動啟動**：只寫 `HKCU\...\Run` 的 `flight-deals` 值，`autostart.py`、`web/`、`services/` 無 schtasks、reg.exe、`.vbs`、`subprocess`（grep）；`autostart.py` stdlib only、列入 `STDLIB_ONLY`、ALLOWED 空集合；測試用假 registry 不碰真實 HKCU；probe 非 Windows 或例外回 None；兩支 bat 無祕密、無 `runas`；`--background` 的 file handler 掛遮蔽 filter 與 formatter、有 token 不進 log 的測試；相對 DB 路徑以 `PROJECT_DIR` 解析有測試；`.gitignore` 加 `*.log`。

## FD-5 增補：行程條件擴充（人數、艙等、航空公司、去程出發時段）（2026-10-28，tech-architect 評估；不另開 ADR；總經理落檔）

範圍：監看新增成人／兒童人數、四種艙等、航空公司篩選（最多 5 家）、去程出發時段；查票連結改為精確的 Google Flights tfs 網址；去重 key 納入 revision。屬 D-1、D-2、D-4、D-6 範圍：不新增執行期依賴、不改 import 方向；新增 migration 0003；`ports.py` 新增一個 Protocol。失效條件第 5 項「需要多人、多艙等」由本節處理；匯率換算仍須另開。

### Context
- 2026-10-28 實測（fast-flights 3.1.0，TPE→NRT 2026-12-10 單程）：`create_query(seat=)` 接受 economy／premium-economy／business／first；`Passengers(adults, children, ...)`；`FlightQuery(airlines=[...], earliest_departure_hour, latest_departure_hour, ...)` 皆生效；payload 的 price 是整組乘客總價（1 成人 6,202、2 成人 9,736、2 成人 1 兒童 18,509、1 成人商務 20,904；指定 BR 且 06～12 時出發得 2 筆、最早 07:55）。
- 文字查詢連結 `?q=Flights to ... on ...` 會把單程當成來回並自動補回程；加上人數、艙等只落到首頁。fast-flights 的 `?tfs=` 網址可精確重現查詢。
- `watch.cabin`、`watch.adults` 的 CHECK 寫死 economy／1，SQLite 只能重建表；`watch` 是 scan_run、price_observation、alert_state、notification 的父表。
- SQLite 3.26 以上的 `ALTER TABLE RENAME` 不論 foreign_keys 開關都會改寫其他表 FK 中被改名表的舊名；`DROP TABLE` 在 foreign_keys=OFF 時不做隱含 DELETE。因此安全順序是「建 watch_new → 複製 → DROP watch → RENAME watch_new TO watch」，**禁止先把舊表改名**（子表 FK 會被改寫成指向舊名）。
- `price_item_key`／`price_message_key` 不含 revision，`notified_item_keys` 跨 revision 查詢；改回先前條件時同組合同價會被舊 key 擋掉而無聲漏推。

### Decision
1. **Schema（migration 0003 `0003_watch_trip_options.sql`，FK-off 標記）**：依 12 步重建 `watch`：cabin 四值（`economy`／`premium_economy`／`business`／`first`）、adults 1～9、children 0～8、`adults + children <= 9`（本公司自訂上限）、`airlines` 為大寫排序去重的逗號字串（NULL＝不限，最多 5 家，CHECK 以長度與 GLOB 限制）、`dep_hour_from`／`dep_hour_to` 同為 NULL 或同為 0～23 且 from < to。`price_observation` 以 `ADD COLUMN depart_time TEXT`（"HH:MM"，可 NULL）。同一檔回填舊 `notification_item.item_key` 的 revision 段（經 `observation_id → price_observation.watch_revision`，相關子查詢；取不到的列不動）。migration 內不得設 `legacy_alter_table`。
2. **revision**：人數、艙等、航空公司（集合，與勾選順序無關）、出發時段納入 `search_shape()`；名稱、預算、通知開關不納入。alert_state 重置沿用既有行為。
3. **查詢**：`domain.search_for(spec, pair, currency)` 是唯一的 `FlightSearch` 建構點，掃描與查票連結共用；`FlightSearch.cache_key()` 含全部新欄位。艙等在 domain 用 snake_case，只在 `google_flights.py` 對映成 fast-flights 字串。航空公司與 max_stops 去程回程都帶；**出發時段只套去程**（回程時段另開批次）。
4. **解析**：`google_payload.py` 多取第一段 `segment[8]` 的出發時刻（`[h, m]`→"HH:MM"、`[h]`→"HH:00"，其餘 None），屬選用欄位，取不到不計 malformed、不影響狀態判定；出發地當地時間不換算。**抵達時刻本批不存**（跨日需日差欄位）。
5. **價格語意**：存整組總價、不存每人價（成人與兒童票價不同，除法無意義且違反 D-6 整數原則）；價格旁一律加「（N 人總價）」或「（A 大 C 小總價）」，由 domain 純函式（`pax_label`、`pax_full_label`、`cabin_label`、`total_price_note`）產生；預算門檻語意為整組總價；推播表頭加「（來回・2 大 1 小・商務艙）」，有篩選時加一行「篩選：航空公司 …；去程出發 06–12 時」。
6. **航空公司對照表**：`domain/airlines.py` frozen dataclass（`code` 符合 `^[A-Z0-9]{2}$` 且不得兩碼皆數字、`display_name` ≤ 6 字、`verified_note`），30～50 家，查證紀律同 C-23；表單為 `<details>` 折疊的 checkbox 清單，伺服端限 5 家；屬 Google 套用的**硬篩選**，解析端不做後過濾（codeshare 判定以 Google 為準，文案不宣稱「只搭該航空」）。修改監看時表外但未改動的舊代碼可豁免。
7. **查票連結**：`ports.BookingLinkBuilder.url(search) -> str | None`，由 `sources/google_flights.py` 的 `GoogleFlightsLinkBuilder` 以 `build_query` 的 tfs 產生（不連網）；`app.py` 注入 `ViewService` 與 `NotificationService`；`price_alert_message` 改由參數接收每筆連結。builder 失敗或舊 revision 的價格列回退到 `domain/links.py` 文字查詢並註明「此連結只帶航線與日期，人數、艙等、篩選請在頁面上重選」。否決把 tfs 存進 DB、否決在 domain 重寫 protobuf 編碼。
8. **去重**：`price_item_key` 與 `price_message_key` 加 `r{revision}`；舊訊息 key 不回填（新格式不會相撞），舊 item key 由 0003 回填。
9a. **解析兩個結果區段（總經理 2026-10-28 實測後追加，取代 FD-3 Decision 2 的「只讀 `payload[3][0]`」）**：Google 的內嵌資料有「最佳航班」`payload[2][0]` 與「其他航班」`payload[3][0]` 兩段，上游 fast-flights 與 FD-3 的解析器只讀後者，而前者常更便宜（TPE→NRT 經濟 1 人 best 4,868 vs other 6,202；SHA fixture best 4,633 vs 原記錄 12,655），導致自 FD-1 起最低價偏高。自 FD-5 起兩段合併、去重（航空碼＋航段出發／到達碼＋出發時刻＋價格相同視為同一筆），`ParseStats` 另計 `best`／`other`。狀態表新增一列：**`payload[2]` 與 `payload[3]` 皆為整段 None 或缺席 → `no_data`，子原因 `no_embedded_results`**（實錄形狀為整段 `None`；`payload[3]` 為其他非 list 形狀或 `payload[3][0]` 非 list 仍判 `blocked`；`payload[3][0] == []` 仍依 FD-3 判 `blocked`）（實測只在「來回＋商務艙＋多人」出現，瀏覽器開同一 tfs 連結可見結果，屬 Google 非同步載入），不計斷路器失敗、不觸發維運告警、監看不轉 stale；UI 說明「Google 未在頁面內嵌此查詢的結果，無法自動查價；請用查票連結人工查看」。
9. **總經理對 PRD 的裁示**：FR-A6～A9「去程與回程各段都套用」改為只套去程；FR-A5「每段都必須是所選航空、不符不進紀錄」改為不做後過濾；成人＋兒童 ≤ 9；時段整點、from < to、不跨午夜、兩邊同填或同空；不顯示每人價；tfs 連結與 revision 去重納入本批；改人數時只靠靜態提示文字。

### Consequences
- 好處：可監看全家出遊、商務艙、指定航空與時段；連結點進去與推播是同一組條件；改回舊條件不再漏推。
- 代價：再次重建父表（遷移風險、首次升級備份）；查票連結依賴 fast-flights 內部編碼，升版要重錄 golden；回程時段、抵達時刻、嬰兒票、跨午夜時段、每人價都不支援；航空公司篩選語意以 Google 為準；已推過的舊訊息內連結仍是文字查詢。
- 被約束的事：新增回程時段或抵達時刻要回到本節增補；改 tfs 產生方式或把連結存進 DB 要重評第 7 點。

### 新增約束
- **C-37 Migration 0003**：首行 FK-off 標記；順序為建 `watch_new` → 複製（明列欄位、id 原樣）→ DROP `watch` → RENAME；grep 不得出現 `RENAME TO watch_old` 或先改名 `watch`；不設 `legacy_alter_table`。在含資料的 v2 DB（≥2 個 watch 其一 revision > 1、scan_run、price_observation、alert_state、price_alert notification、2 筆 notification_item）上測試：各表筆數不變、舊欄位逐欄相等、新欄位為預設；`foreign_key_check` 為空；`sqlite_master` 子表 DDL 仍含 `REFERENCES watch(id)` 且全庫不含 `watch_new`；插入不存在 watch_id 的 scan_run 失敗；刪 watch 會 cascade 到五張子表。CHECK 拒絕 adults=0／10、children=9、合計 10、`cabin='luxury'`、`airlines='br'`／`'BR,'`／6 家、hour 24、單邊時段、from ≥ to、`depart_time='7:55'`；接受 `premium_economy`、`'BR,CI'`。舊 item_key 已補 `r{rev}`、`observation_id` 為 NULL 的列不變。備份 `*.pre-v3.db` 存在、新 DB 不備份、schema 無 view／trigger；測試斷言 `sqlite3.sqlite_version_info >= (3, 26, 0)`。
- **C-38 Domain、驗證、revision、去重**：`WatchSpec` 新欄位有型別（`Cabin` Literal、`airlines: tuple[str, ...]`）；驗證錯誤訊息繁中且逐條有測試（人數界線、合計 9、未知／重複航空、超過 5 家、時段單邊／等值／反向／非整數）；修改時表外但未改動的航空代碼可豁免；`search_shape()` 含六個新欄位、不含名稱／預算／通知開關，各有「變更才 +1」測試，勾選順序不同不 +1；`cache_key()` 含新欄位（兩組只差人數不共用快取）；`search_for` 是唯一建構點（grep `FlightSearch(` 只在 domain 與測試）；去重 key 含 `r{revision}`，有「rev1 推過 → 改艙等 → 改回 → 同價會推」與「同 revision 同價不重推」測試。
- **C-39 Adapter 與解析**：解析同時讀 `payload[2][0]` 與 `payload[3][0]` 並去重，有「只有 best」「只有 other」「兩段皆有且重疊」「兩段皆 None → `no_embedded_results` 不計失敗」四種測試；SHA fixture 契約改為 itineraries 9、priced 7、unpriced 2、最低 463300；艙等對映只在 `google_flights.py`；`build_query` 以假物件斷言 Passengers 收到 adults 與 children、航空兩段都帶且空清單不傳、時段只在去程、seat 四值對映正確；`google_payload.py` 仍 stdlib only，出發時刻測試涵蓋 `[7,55]`、`[7]`、`[]`、None、`[24,0]`、`["7",55]`，異常不改 ParseStats 與狀態；`payload_TPE_SHA.json` 契約數字不變；新錄一份有指定航空與時段的 fixture 並斷言 `depart_time` 落在時段內；來回 payload 是否只含去程的查證寫進任務單。
- **C-40 顯示與文案**：`pax_label`、`cabin_label`、`total_price_note` 在 domain、無 I/O；列表、詳情、推播、摘要、通知紀錄頁的價格旁都有總價註記且各有斷言；`views.py` 不得再寫死「經濟艙」或 `adults: 1`；C-25 重驗（5 筆、tfs 連結、最長條件）與 C-34 重驗（200 監看、最長標籤、≤20 行、表尾保留）；新字串納入 `all_static_texts()` 通過 BANNED_PHRASES；時段文案不得寫「X 點前」。
- **C-41 航空公司對照表**：每筆 code 符合二字規則且唯一、`display_name` ≤ 6 字、檔頭載明出處／日期／查證人；qa 抽查 ≥10 筆或 20%（取多者）記任務單；live smoke 至少 3 家（含 1 家 LCC、1 家含數字代碼）；表單為 checkbox 清單、無新前端元件、無 `innerHTML`；5 家上限以伺服端驗證為準且有測試。
- **C-42 查票連結**：`BookingLinkBuilder` 定義在 `ports.py`、實作只在 `sources/google_flights.py`、`fast_flights` 仍只出現在該檔（新增 import 名稱要同步更新 C-26 測試並記任務單）；不連網（測試把 `fetch_flights_html` monkeypatch 成一呼叫就失敗）；golden 測試以固定 FlightSearch（單程、2 大 1 小、商務艙、BR、06–12）斷言完整 URL，與 `VERIFIED_FAST_FLIGHTS_VERSION` 綁定；逐欄變更（人數、兒童、艙等、航空、時段、轉機、單程／來回）任一改變 tfs 都改變；builder 拋例外回退文字連結並帶註明（有測試）；舊 revision 列用文字連結；`web/` 無新 import；總經理在瀏覽器手動開 3 條連結（單程、多人、商務艙）驗收並記任務單。

## FD-6 增補：探索模式（一個月內哪天最便宜）與兩個提示小項（2026-10-29，tech-architect 評估；不另開 ADR；總經理落檔）

範圍：對指定月份的每個出發日各查一次（≤31 格）在背景執行，產出價格日曆與最便宜前 5 名，可從結果預填建立監看；小項 (a)「未內嵌結果」比例提示；小項 (b) 表單靜態提示。屬 D-2、D-3、D-6 範圍：不新增執行期依賴、不改 import 方向；新增 migration 0004（純新增）、兩個 services 模組、domain 一個 Protocol。

### Context
- `queries_used_since` 目前只加總 `scan_run.queries_used`，探索的查詢若不併入會繞過全域每小時上限。
- 排程只有一個 worker；快取與節流是 source 實例上的狀態，探索與掃描必須用同一組實例才真的共用。
- `expand_pairs` 只收「回程日 ≤ window_end」的日期對。C-37 已要求 SQLite ≥ 3.26，window function 可用；json1 未查證、不依賴。
- 單一 worker 下掃描與探索本來就序列執行；中途額度變少只來自重試、POST 後 job 開始前的掃描、以及軟上限。

### Decision
1. **Schema：migration `0004_exploration.sql`**（只有 CREATE TABLE／CREATE INDEX，無 FK-off 標記）。`exploration`（條件欄位 `condition_key`、origin、destination、trip_type、month "YYYY-MM"、trip_days、max_stops、adults、children、cabin、airlines、dep_hour_from/to、currency；人數／艙等／航空／時段 CHECK 逐字沿用 0003；trip_days 單程必 NULL；進度 `status` queued/running/done/failed、`total` 1–31、`done` 0–total、`queries_used`；`created_at`、`started_at`、`finished_at`、`error_summary`；索引 `(condition_key, created_at)`、`(created_at)`、`(started_at)`）。`exploration_cell`（FK CASCADE、depart_date、return_date、status pending/ok/no_data/blocked/error/skipped、reason、source、price_kind、from_cache、attempts、amount_minor、currency、carrier、stops、duration_minutes、depart_time、as_of、fetched_at、error；PK `(exploration_id, depart_date)`；CHECK `(status='ok') = (amount_minor IS NOT NULL)`）。不設 `rejected`：額度不足回 409、不建列。
2. **Domain**：`SearchConditions` Protocol；`search_for(cond, pair, currency)` 仍是唯一 `FlightSearch` 建構點；`ExplorationSpec`（條件＋year、month、trip_days、currency）與 `condition_key()`（`v1|` 前綴、航空排序去重、NULL 寫 `-`）；`dates.month_pairs(spec, today)`（只取 ≥ 今日台北的出發日，來回 `return = depart + trip_days` 可跨月）、`dates.month_weeks`（stdlib calendar，週一起）；`validate_exploration` 呼叫監看驗證既有函式，月份限當月到第 11 個月後，旅程天數 1～30（總經理依 PRD 裁定）。
3. **執行模型**：`services/exploration.py::ExplorationService`（create／run／recover_interrupted／purge_expired／status）；sources 與 `ScanService` 為同一組實例（`app.py` 組裝）；新 `services/source_query.py` 抽出「依序試各 source、斷路器、record_success/failure、no_data 子原因」供掃描與探索共用（既有掃描測試不改一行須全綠）。`create`：驗證 → 24 小時內同 key 的 `done` 且無 skipped 格 → 200 reused；已有 queued/running：同 key 回其 id、否則 409 busy；排程未跑 409 scheduler_off；`hourly_left - reserve < total` 409 quota（附 hourly_left、needed；**`exploration_reserve_for_scans` 設定預設 12，總經理裁定**）；通過才在同一 transaction 寫探索列與全部 `pending` 格並排 job 回 202。job `explore:<id>`（date trigger、misfire None、max_instances 1）：每格查前以最新 `queries_used_since` 算剩餘，不足標 `skipped/global_hourly_limit`，斷路器開著標 `skipped/breaker_open`；每格更新與 `done += 1`、`queries_used += attempts` 同一 transaction；完成設 `done`，有略過寫說明；例外時剩餘格 `skipped/interrupted`、狀態 `failed`；斷路器新開啟沿用維運通知。探索不寫 `price_observation`／`alert_state`／價格通知、不改 `watch`。`queries_used_since` 改為 scan_run 與 exploration 加總。`ScanScheduler.start` 先 `recover_interrupted()`。每小時 `exploration-purge` 刪 `created_at` 超過 7 天且不在 queued/running 者。`next_run_time()` 排除 `explore:` 與 purge；健康頁顯示「探索進行中（done/total），排程掃描會在探索完成後依序執行」。
4. **查價與快取**：每格 `search_for(spec, pair, spec.currency)`；快取命中 attempts=0 不扣額度；解析與狀態判定沿用 FD-3／FD-5 9a；每格只存最便宜一筆，無同幣別報價時仍存並設 `reason=currency_mismatch`、不參與排名與分位。
5. **端點**：`GET /explore`（表單＋最近 7 天清單）；`POST /api/explorations`（需 header；202／200 reused／409 code quota|busy|scheduler_off／422）；`GET /explorations/{id}`（404 頁）；`GET /api/explorations/{id}/status`（只回 exploration_id、status、total、done；no-store；不需 header；404）；`GET /watches/new?from_exploration=<id>&depart=YYYY-MM-DD` 或 `&mode=month`（只預填不寫入；id 或 depart 不合時空白表單加提示）。前端輪詢 ≥2 秒、進度用 textContent、done/failed 時 reload、120 秒無進度或超過 `total×30+60` 秒停止並提示「仍在背景執行，可稍後重新整理」（不得含「失敗」）。
6. **預填語意**：單格 → 固定日期＋全部條件與 max_stops；整月 → 彈性窗：`window_start = max(月初, 今天)`，單程 `window_end = 月底`，來回 `window_end = 月底 + trip_days` 且 `min = max = trip_days`；表單顯示「每輪最多查 N 組，輪換取樣」；探索價格不匯入監看歷史。
7. **日曆讀取模型**：新 `services/exploration_views.py`；`weeks` 二維（週一起、月外 None）；每格日期、星期、狀態標籤、金額、航空、轉機、出發時刻、分位（`views.price_levels` 抽成模組層純函式兩處共用；只算 ok、同幣別、live；附文字「低／中／高」）、`booking_url`／`booking_note`；前 5 名排除 currency_mismatch／no_data／skipped，同價依日期；無價格標籤：pending「查詢中」、no_data 有篩選時 `NO_MATCH_LABEL`、no_data「無資料」、no_embedded_results「未內嵌結果」、blocked「被擋」、error「錯誤」、skipped/global_hourly_limit「額度不足略過」、breaker_open「資料源暫停略過」、interrupted「中斷未查」；價格旁 `total_price_note`；日曆文案註明「探索結果為查詢當下參考值」並附 DISCLAIMER。
8. **小項 (a)**：`HealthService.no_embedded_summary(now)` 在 Python 端算（一次 SELECT 24 小時 `scan_run.query_results` ＋ 一個 `exploration_cell` 計數；分母排除 skipped／pending／from_cache；分母 ≥10 且比例 ≥50% 才提示）；列表 `list_watches_with_last_results` 改用 window function 帶出目前 revision 最近 3 次已完成 run，「一輪命中」＝至少一筆非 skipped 且所有非 skipped 皆 no_embedded_results，全部 skipped 中斷連續；最近 3 輪全命中才標示；門檻（3 輪、10 筆、50%）放 config Limits。
9. **小項 (b)**：只改 `watch_form.html`、探索表單與 `app.js`：來回、艙等 business/first、成人＋兒童 ≥2 時顯示靜態提示「依實測，此組合 Google 常未內嵌結果，可能無法自動查價，可用查票連結人工查看」；後端零變更。
10. **總經理對 PRD 的裁示**：不設 rejected；中途不足略過剩餘格；有略過或 failed 不重用、同條件進行中回原 id；同時只允許一個探索；條件含 max_stops；探索價格不匯入監看歷史也不推播；整月監看每輪仍只查 `max_pairs_per_scan` 組；24 小時未內嵌比例含探索格；加「探索須保留 N 次給掃描」設定（預設 12）；重啟中斷不續跑；7 天從 created_at 起算；當月排除今天以前；進度只更新計數、日曆完成時整頁出現；旅程天數 1～30。

### Consequences
- 好處：一次看完整月最低價分布並可直接轉成監看；額度、節流、快取、斷路器與掃描同一套；重啟、清除、重用有明確狀態；未內嵌問題在列表與健康頁可見。
- 代價：一次探索可能用掉每小時上限的一半以上，之後掃描可能部分略過；探索期間掃描順延（典型 1～3 分鐘，最壞約 20 分鐘）；中途不足有缺格且不重用；重啟中斷不續跑；探索價格不進「創新低」基準；抽共用查價函式有重構風險（靠既有測試不改、全綠把關）；「連續 3 輪」只看目前 revision。
- 被約束的事：多個探索並行、暫停續跑、探索價格匯入歷史、改用 json1，都要回到本節重評。

### 新增約束
- **C-43 Migration 0004**：檔內只有 CREATE TABLE／CREATE INDEX，無 FK-off 標記、DROP、RENAME（grep）；在 v3 DB 上遷移後既有表筆數不變、`foreign_key_check` 為空、`*.pre-v4.db` 存在；CHECK 拒絕 `month='2026-13'`／`'2026-1'`、`total=0`／`32`、`done > total`、`status='rejected'`、單程帶 trip_days、cell ok 無金額、非 ok 有金額、`amount_minor=0`、`depart_time='7:55'`；人數／艙等／航空／時段 CHECK 測試案例與 0003 逐條相同；刪 exploration 會 CASCADE 刪 cell。
- **C-44 Domain**：`SearchConditions` 在 domain；`search_for` 接受 `WatchSpec` 與 `ExplorationSpec`；grep `FlightSearch(` 仍只在 domain 與測試；等價的 `ExplorationSpec` 與 `WatchSpec` 產生相同 `cache_key()`；`condition_key()` 有 `v1|` 前綴、與勾選順序無關、任一條件改變 key 就變；`month_pairs` 涵蓋當月排除今天以前、跨年、閏年 2 月、單程 return None、最多 31 格；`month_weeks` 週一起算補 None；`validate_exploration` 繁中訊息、月份界線測試、人數等驗證呼叫既有函式。
- **C-45 執行與額度**：探索只經 `explore:<id>` job 執行（misfire None）；POST 期間 fake source 呼叫 0 次；sources 與 ScanService 為同一批物件（`is`）；`services/` 不 import `sources`；探索跑完 `price_observation`／`alert_state`／price_alert 筆數不變、watch 逐欄不變；`queries_used_since` 含 `exploration.queries_used`；409 quota 含 hourly_left 與 needed、busy、reused 規則各有測試；每格更新與 done／queries_used 同一 transaction（第 k 格後拋例外 → done == k）；中途額度歸零 → 剩餘 `skipped/global_hourly_limit`、狀態 done、error_summary 有說明；斷路器開 → `breaker_open`；`recover_interrupted` 在 start 排 job 前呼叫；purge 只刪超過 7 天且不在 queued/running；`next_run_time()` 排除 `explore:` 與 purge；`scheduler/` 仍只 import services；抽出 `services/source_query.py` 後既有掃描測試檔無修改且全綠。
- **C-46 端點與輪詢**：status 端點四個白名單欄位、no-store、不需 header、404、無寫入；POST 缺 header 403；頁面 404；`from_exploration` 不合時回 200 空白表單加提示；前端輪詢 ≥2 秒、120 秒無進度或超過 `total×30+60` 秒停止、完成 reload、逾時文案無「失敗」、無 `innerHTML`；導覽列新增「探索」。
- **C-47 日曆與預填**：`weeks` 結構與各標籤逐一斷言；分位文字「低／中／高」；`price_levels` 只定義一處且詳情頁輸出不變；前 5 名排除 currency_mismatch／no_data／skipped、同價依日期；每個 ok 格有 tfs 連結、builder 失敗退回文字連結並註明；價格旁總價註記；整月預填規則測試斷言 `expand_pairs` 的出發日集合等於該月未來日子；新字串納入 `all_static_texts()` 通過 BANNED_PHRASES；日曆含「探索結果為查詢當下參考值」與 DISCLAIMER。
- **C-48 小項 (a)(b)**：(a) 不使用任何 `json_` SQL 函式（grep storage/）；比例計算為純函式、分母排除 skipped／pending／from_cache；測試涵蓋 9 筆全命中不提示、10 筆 5 筆提示、10 筆 4 筆不提示、含探索格；列表連續 3 輪只看目前 revision，有 3 輪命中／2＋1 ok／1 輪全 skipped 中斷／修改後重算四種測試；`list_page` SQL 次數不增；門檻在 config。(b) 後端檔案零變更；提示元素預設 hidden、編輯頁初次載入也判斷；文案無保證語氣並納入模板禁用字檢查。

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

## FD-7 增補：Telegram 雙向指令、資料保留與列表效能（2026-10-29，tech-architect 評估；不另開 ADR；總經理落檔）

範圍：Telegram 長輪詢指令（`/help`、`/start`、`/list`、`/watch N`、`/scan N`、`/digest`、`/status`、`/pause N`、`/resume N`）、指令紀錄、資料保留與每日清除、清除前備份、VACUUM、健康頁資料維護區塊、列表索引與查詢改寫。屬 D-3、D-4、D-5 範圍：不新增執行期依賴、不改 import 方向表。新增 migration 0005、`domain/commands.py`、`services/commands.py`、`services/retention.py`、`ports.TelegramInbox`。
**修訂既有條文**：C-32「`send_if_due` 是唯一送出入口」限縮為 `daily_digest` 的唯一入口；D-4「失敗下次重送」不適用 `command`、`manual_digest`；FD-4 Decision 7 的設定精靈改為不推進 offset，FD-4 SW10「服務執行中也能用精靈」作廢。

### Context
- 單一 worker；長輪詢 25 秒若在 worker 上跑會擋住掃描與探索。`getUpdates` 與 webhook／另一個消費者互斥（409）；update 要以更大 offset 呼叫才算確認；現行精靈會推進 offset、吞掉服務未處理的指令。
- `scan_run.trigger` CHECK 只有三值且 scan_run 是觀測的父表；`notification.kind` 要加值須重建（同 0002）。外鍵子表 `price_observation.scan_run_id`、`notification.observation_id`、`notification_item.notification_id` 都沒有索引。
- 清除會影響快照（列表、摘要、`/list`）、「較前一輪」（每組日期第 2 新觀測）、「較前一日」（台北零時前最新一筆）、創新低基準（目前 revision 全部觀測）、去重（`notification_item`）。列表 SQL 目前以 window function 物化整張 scan_run（FD-6 bench 200 ms）。

### Decision
1. **輪詢模型**：`services/commands.py::CommandPoller` daemon thread（`start`／`stop`／`wake`／`status`／可單測的 `poll_once`），只在 token 存在、chat id 為正整數、且 `create_app(start_scheduler=True)` 已持排程鎖時於 lifespan 內啟動（scheduler.start 之後、shutdown 之前停止）；長輪詢 25 秒、HTTP timeout 35 秒；開關 `telegram_commands_enabled` 關閉時不發 HTTP、只等 Event（最多 30 秒醒一次）；關閉或 stop 後收到的批次整批丟棄不推進 offset；退避 2～300 秒指數（429 以 retry_after 為下限）、409 每 60 秒、401 轉 `stopped_unauthorized` 停止；例外一律攔下遮蔽記錄；`stop()`＝設 Event → 5 秒內取 processing lock → join 1 秒。新 port `ports.TelegramInbox.get_updates(offset, long_poll_seconds) -> InboxResult`（`InboundUpdate(update_id, kind, chat_id, chat_type, text, sent_at)`），實作 `notify/telegram.py::TelegramCommandClient`（永不拋出、錯誤先遮蔽、只訂閱 message 類），`app.py` 組裝前先 `register_secret`。
2. **授權、重放、積壓**：授權＝`kind=="message"` 且 `chat_type=="private"` 且 `chat_id ==` 設定整數；不符只 `ignored_count += 1`（記憶體、本次啟動起算），不存文字、不回覆、不寫紀錄、log 不含文字與對方 chat id；授權 chat 的 `edited_message` 不執行不回覆；chat id 為負數（群組）不啟動並顯示「不支援群組」。積壓：`sent_at < now − 10 分鐘` 不執行只計數，每批結束若 N>0 回一則「服務停機期間有 N 則指令未處理，請重新傳送」（dedupe `cmd-backlog:<bot_id>:<max update_id>`）。每則處理順序：以 `cmd:<bot_id>:<update_id>` 插入 `command` 列（回 None 即已處理、跳過）→ 解析執行 → 送回覆一次並更新 → 寫 `state.telegram_update_offset = update_id+1`（最多執行一次）。`bot_id`＝token 冒號前數字，另存 `state.telegram_offset_bot_id`，換 bot 歸零。每批最多 20 則。
3. **解析與分派**：`domain/commands.py::parse_command(text)` 純函式（NFKC → strip → >64 字 `too_long` → 首 token 小寫 → 去 `@bot` 後綴）；參數須符合 `^[1-9][0-9]{0,8}$` 且為監看 id；非 `/` 開頭回格式提示。`services/commands.py::CommandService.handle(cmd, now) -> CommandReply` 同步，依賴 Repository、WatchService、SettingsService、HealthService、BookingLinkBuilder 與 `app.py` 注入的 callable（`schedule_scan`、`scan_pending`、`schedule_manual_digest`、`next_run_time`、`scheduler_running`）；**不 import `scheduler`、`notify`**。讀取模型重用 `Snapshot.build`、`delta_since_previous_run`、`latest_per_pair`、`describe_source`、`queries_used_since`、`active_exploration_view`（不用 HTML dict）。回覆組字在 `domain/messages.py`，`COMMAND_REPLY_MAX_CHARS=3800`、`/list` 最多 30 行加「另有 N 個未列出」、免責句與總價註記永遠保留、納入 BANNED_PHRASES；送出與入庫前皆 `redact`。`/pause`／`/resume` 先判斷是否已是目標狀態再呼叫 `WatchService.set_enabled`。
4. **`/scan`**：依序檢查存在 → 未停用 → 未過期 → 排程運作中 → 本小時剩餘額度 >0 → 未在查價中（否則回「已在查價中」不另回結果）→ 探索進行中則註明順延；通過後記 `watch_id → (update_id, notification_id)`（thread lock）並呼叫 `schedule_scan`；`ScanScheduler.trigger_command_scan(watch_id)` 排 `cmdscan:<id>` job（`replace_existing`）：`scan.scan_watch(id, "manual")` 後呼叫 `services.commands.on_scan_finished(id, outcome)`；結果回覆記 `command` 列，dedupe `cmd:<bot_id>:<update_id>:result`；`on_watch_deleted` 一併移除；`next_run_time()` 把 `cmdscan:` 算成掃描。**否決 `scan_run.trigger='command'`**（須重建觀測父表）。
5. **`/digest`**：排 `manual-digest:<update_id>` job，在 worker 上 `DigestService.send_manual(now, key)` → `NotificationService.send_manual_digest` 寫 kind `manual_digest`（dedupe `digest-manual:<bot_id>:<update_id>`）；不碰 `digest:<日期>`、不進重送、不設冷卻；指令當下回「已排入」；`next_run_time()` 排除。
6. **Migration `0005_notification_kinds_and_indexes.sql`**（FK-off 標記）：依 0002 順序重建 `notification`（kind 加 `command`、`manual_digest`）並重建 `ix_notification_created`；同檔建索引 `ix_notification_observation(observation_id)`、`ix_notification_item_notification(notification_id)`、`ix_price_observation_scan_run(scan_run_id)`、`ix_scan_run_watch_id(watch_id, id)`、`ix_scan_run_watch_rev(watch_id, watch_revision, id)`；不得 CREATE／DROP／RENAME `scan_run` 或 `price_observation`。`NotificationKind` 加兩值，標籤「指令」「手動摘要」；`command` 列 `message_text` 為「指令 → 回覆」（指令截 64 字並遮蔽），回覆只送一次、失敗記 failed 不回滾效果。
7. **資料保留 `services/retention.py::RetentionService.maintain(now)`**（冪等）：到期＝台北時間 ≥ `digest_time + 30 分鐘` 且 `state.retention_last_date != 今天`；呼叫時機比照摘要（cron `maintenance`、每小時 `maintenance-check`、啟動 `maintenance-catchup` 排在 digest-catchup 之後）；執行期間持有 `ScanService.lock`。設定：`retention_days`（30–3650，預設 180）、`notification_retention_days`（30–3650，預設 365）、`retention_keep_runs`（3–100，預設 10）、`telegram_commands_enabled`、`vacuum_enabled`（預設開）；`retention_backups_keep=7` 在 Limits。刪 scan_run 條件：`finished_at < now − retention_days` 且不在該監看最近 N 個已完成 run 且不在保護集合；**保護集合**（目前 revision、`depart_date ≥ 今日台北`）：每 (depart_date, return_date, price_kind, currency) 最新 2 筆觀測、台北零時前最新 1 筆、每 (price_kind, currency) 的 `MIN(amount_minor)` 那筆（同價取最小 id；**此項不限出發日**，因 `min_amount` 基準本身不看出發日，dev-lead 實作、qa-reviewer 同意）所在的整輪。`scheduler_event` 同期清除。刪通知條件：`created_at < now − notification_retention_days`，但監看仍在且任一 item `depart_date ≥ 今日` 的 `price_alert` 保留（去重相容）。絕不碰 watch、使用者設定、alert_state、source_health、exploration、running 的 run。每批 ≤500 id 一個 transaction。備份：候選 >0 且今日 `<stem>.retention-<YYYYMMDD>.db` 不存在才先備份（暫存檔 + `os.replace`），失敗整次不刪；只保留最新 7 份（嚴格 regex，絕不動 `pre-v*`）。結果寫 `app_setting` 的 `state.*` 與一筆 scheduler_event；`state.retention_last_date` 只在全部完成後寫。檔案操作只在 `storage/db.py`、刪除 SQL 只在 `storage/repository.py`。
8. **VACUUM**：清除完成後，`vacuum_enabled` 且上次為空或滿 7 天且 `disk free ≥ 2×（主檔＋WAL）` 才執行；autocommit 專用連線、busy_timeout、`VACUUM` 後 `PRAGMA wal_checkpoint(TRUNCATE)`，記錄前後大小；不足略過並記原因。WAL 下 VACUUM 期間寫入可能等待（依記憶，dev-lead 在 bench DB 實測耗時記任務單）。
9. **索引與列表**：`list_watches_with_last_results` 改單一 SQL：每監看以相關子查詢取「最新 1 個已完成 run」與「目前 revision 最新 `rounds` 個」各 `ORDER BY id DESC LIMIT` 再 UNION；不得對整張 scan_run 做 window function；`EXPLAIN QUERY PLAN` 無 `SCAN scan_run`；FD-6 bench 中位數 <100 ms；SQL 次數不變。另量寫入 ≤120%、健康頁 <300 ms、180 天穩態（約 17 萬筆）列表耗時（>300 ms 開後續）。
10. **健康頁與設定頁**：「指令輪詢」列（運作中／已關閉／未設定 Telegram／已停止（token 無效）、最近連線失敗與遮蔽原因、最近指令時間、忽略數「本次啟動以來」）；「資料維護」區塊（UNION ALL COUNT 固定表名、`page_count*page_size`、WAL 大小、記憶體快取 5 分鐘、註明統計時間；上次清除／備份／VACUUM 結果與保留期）；詳情頁註明「價格紀錄保留最近 N 天」；設定頁五個新設定，調降保留期提示「下次清除將刪除超過 X 天的資料」。
11. **精靈修訂**：`telegram-setup` 一律 `offset=None`（不確認），非空結果間 sleep 2 秒；`CONFLICT_TEXT` 改為「指令輪詢運作中，請先在設定頁關閉指令功能或停止服務再執行」，結束碼非零；README 修正 FD-4 SW10。
12. **總經理裁示（14 項，照架構）**：401 停止並顯示第四種狀態；忽略計數記憶體起算；精靈不確認 update；網頁已排立即查價時 `/scan` 只回「已在查價中」；`/scan` 待回覆清單記憶體、重啟遺失；10 分鐘以 `message.date` 對本機時鐘；含未出發 item 的 price_alert 留到 365 天後；另保護歷史最低價所在的 run；VACUUM 為滿 7 天後第一次清除完成時執行；備份 7 份、清除於摘要後 30 分鐘；保留期上限 3650、keep_runs 上限 100；指令列同 365 天；效能門檻用 FD-6 原基準；健康頁筆數快取 5 分鐘。

### Consequences
- 好處：手機可查詢與操作，探索進行中也能即時回覆；掃描路徑零改動；重放與積壓語意明確；清除前後列表、摘要、`/list`、創新低基準、去重都不變；DB 成長有上限、外鍵子表有索引、列表查詢量不隨總 run 數成長。
- 代價：多一條 thread、關機最多多等 5 秒；指令「最多一次」（當機可能少一則回覆、`/scan` 結果回覆重啟後遺失）；只支援私訊與數字 chat id；token 失效要重啟；精靈與服務互相 409；通知紀錄頁會被指令列擠占；受保護的 run 與未出發的價格通知會留到保留期之後；7 份備份最多約 8 倍 DB 空間；VACUUM 期間寫入可能等待；清除期間掃描順延；健康頁筆數最多落後 5 分鐘；價格歷史變短。
- 被約束的事：多 chat、群組、webhook、修改條件的指令、讓輪詢做查價、把 trigger 存成 command、改用 incremental vacuum，都要回到本節重評。

### 新增約束
- **C-49 輪詢模型**：`threading.Thread(` 只在 `services/commands.py`（既有例外：`sources/_support.py` 的查價逾時 thread，FD-3 起即存在）；該檔不 import `scheduler`、`notify`、`httpx`；只在持鎖 lifespan 內啟動（`start_scheduler=False`、缺 token、chat id 非整數、負數各有測試）；假 inbox＋假時鐘測 `poll_once`：關閉時 HTTP 0 次、關閉後最多再完成 1 個進行中請求且不處理不推進、重開恢復、網路／5xx／429 退避遞增上限 300、409 每 60 秒、401 停止、例外不外拋；`stop()` 後無 DB 寫入；長輪詢期間 scheduler 仍可跑 job；`getUpdates`、`api.telegram.org` 只在 `notify/telegram.py`。
- **C-50 授權、重放、積壓、遮蔽**：別的 chat／群組／edited／非 private → sendMessage 0 次、notification 不變、caplog 與 DB 無訊息文字、ignored_count 增；同 update_id 兩次只執行一次；claim 後存 offset 前拋例外、重啟不重複執行；offset 在 `state.telegram_update_offset`、bot_id 不同歸零；3 則積壓（2 則逾 10 分鐘）執行 1 則並回 N=2 說明，全在 10 分鐘內不回；每批 ≤20；假 token 觸發 401／409／網路例外／逾時與各指令錯誤路徑，stdout／stderr／caplog／notification／健康頁／回覆全文不含 token 與 `bot\d+:`。
- **C-51 指令、回覆與紀錄**：`parse_command` 在 domain stdlib，測試涵蓋 `/LIST`、`/list@mybot`、全形「／list」、>64 字、`/watch`、`/watch abc`、`/watch 0`、`/watch 1 2`、`/add`、`/edit`、`/delete`、`/set`、`你好`；寫入型只有 pause／resume／scan／digest 且不改 watch 條件欄位；`/list` 與 `list_page` 逐監看相等、`/watch` 前 3 與詳情頁 `top[:3]` 相等；200 監看最長名稱下回覆 <`MAX_MESSAGE_LENGTH`（≤3800）含「另有」與免責；新字串進 BANNED_PHRASES（加「建議」「最佳時機」「現在買」「划算」）；`/scan` 五分支測試、額度 0 時 fake source 0 次、`cmdscan:` 結束恰一則 `:result`、`scan_run.trigger` 仍 `manual`；`/digest` 產生 `manual_digest`、`digest:<日期>` 不受影響、連傳兩次兩則、重送不含兩 kind、poller thread 不送摘要；回覆失敗記 failed 且效果仍在；單指令例外回「指令執行失敗」後續照常；紀錄頁標籤；新回覆樣板送 risk-compliance-officer。
- **C-52 Migration 0005 與效能**：FK-off 標記；`CREATE TABLE` 只有 `notification_new`；全檔不含 `scan_run`／`price_observation` 的 CREATE TABLE、DROP、RENAME；v4 DB 遷移後筆數不變、`foreign_key_check` 空、`*.pre-v5.db` 存在、新 DB 不備份、兩 kind 可寫、不合法 kind 仍拒、item 指向不存在 id 失敗、六個索引存在（重建的 `ix_notification_created` 加五個新索引）；列表 SQL `EXPLAIN QUERY PLAN` 無 `SCAN scan_run`、不含 `OVER (`；SQL 次數不變；FD-6 bench <100 ms；寫入 ≤120%；健康頁 <300 ms（原始輸出記任務單）。
- **C-53 清除與備份**：假時鐘測未到時間不跑、同日第二次不跑、啟動補跑、持有 `ScanService.lock`；181／179 天 run 依規則刪或留；最近 N 輪保留、只有 6 輪全留、`keep_runs=2` 回 422；**FR-R6**：彈性窗某組日期最新觀測落在 N 輪之前時，清除前後 `list_page`、`DigestService.compose`、`/list` 輸出字串完全相同且 `min_amount` 不變；366／364 天通知四種 kind 前刪後留、含未出發 item 的舊 price_alert 保留、清除後同價不再推；watch／alert_state／exploration／使用者設定／running run 逐筆不變；每批 ≤500、第 k 批後拋例外無孤兒且可續跑；備份：有候選且今日未備份才先備份（可開啟、筆數一致）、無候選不備份、同日不重複、備份失敗刪除 0 筆且健康頁顯示原因、第 8 份出現刪最舊、`pre-v*` 不動；`VACUUM`、備份 unlink 只在 `storage/db.py`。
- **C-54 VACUUM、健康頁、設定與架構測試**：VACUUM 三條件各有測試（磁碟空間 monkeypatch）、執行後筆數不變、`integrity_check` ok、記錄前後大小；五個新設定界線 422 原值不變、兩開關不合法回預設、缺 header 403；健康頁四種輪詢狀態斷言、統計時間、`stats()` 5 分鐘內不重查；`next_run_time()` 排除 `maintenance*`、`manual-digest:`，包含 `cmdscan:`；精靈 offset 永遠 None、409 文案含「指令輪詢」、結束碼非零；`scheduler/` 仍只 import services；新文案通過 BANNED_PHRASES；UI 需 e2e；真實 Telegram 收發由 CEO 或總經理手動驗收。`tests/test_architecture.py` 的 ALLOWED 不變，新增上述 grep 測試。

## FD-8 增補：180 天穩態列表效能（快照讀取改用保護集合）（2026-10-29，tech-architect 評估；不另開 ADR；總經理落檔）

範圍：列表、每日／手動摘要、`/list`、`/watch`、`/scan` 結果回覆的快照讀取改成 SQL 端前置篩選；`retention_snapshot_runs` 改成和讀取共用同一個 SQL 片段；新增 migration `0006_snapshot_index.sql`（只新增一個索引）。屬 D-3、D-4、D-5 範圍：不新增執行期依賴、不改 import 方向表、不改 `services/price_snapshot.py` 的任何函式簽章與語意。
**修訂既有條文**：C-34「`latest_per_pair` 定義只能一處」改為「快照語意的權威定義只在 `services/price_snapshot.py`；SQL 端的前置篩選只在 `storage/repository.py::_snapshot_keep_select` 一處」；C-52「列表 SQL 不含 `OVER (`」限縮為 `LIST_WATCHES_SQL`（`list_watches_with_last_results`），單一監看範圍內的快照 window 不受此限；FD-7 Decision 9「180 天穩態 >300 ms 開後續」由本節結案。
**總經理裁決（代 CEO 回覆 PRD 開放問題 8）**：以 <300 ms 為通過門檻、<100 ms 為目標；不為了達到 100 ms 增加複雜度。

### Context
- FD-7 實測：180 天穩態（20 監看 × 每天 4 輪 × 180 天 = 14,400 輪、172,800 筆觀測）列表中位數 1,165 ms，FD-6 基準庫 23 ms，掃描寫入 121.9 ms。原因是 list_page、摘要、`/list`、`/watch`、`/scan` 結果都用 `observations_for_watch(watch_id, revision=...)` 讀出目前 revision 全部觀測（每監看約 8,640 筆），再在 Python 建 `Snapshot`。
- `Snapshot` 的四個輸出（`cheapest`、`delta_since_previous_run`、`delta_since(midnight)`、`cheapest_pairs`）只依賴每組日期（live、監看幣別、未出發）的最新 2 筆和台北零時前最新 1 筆。FD-7 保護集合正是這個規則（外加 retention 專用的最低價那一筆），FR-R6 已證明清除後輸出不變。
- 現有索引 `ix_obs_watch_pair(watch_id, price_kind, depart_date, return_date, fetched_at)` 沒有 `watch_revision`、`currency`、`id`，window 一定要回表和排序；retention 規劃在穩態庫要 644 ms。
- 詳情頁的 trend（最近 `TREND_POINTS` 輪每輪最低價）、distribution（跨 kind 每組最新、含已出發日期）、recent（前 30 筆）、`has_prices` 都要完整的目前 revision 觀測，不在保護集合語意內。

### 方案比較
| 方案 | 優點 | 缺點 | 結論 |
|---|---|---|---|
| A. 一監看一查詢 `snapshot_observations_for_watch` | SQL 次數與 FD-3 相同（C-34）；四個呼叫端只換一行；成本只看單一監看的索引範圍 | 20 監看仍 20 次 round-trip（每次 <5 ms 即達標） | **採用** |
| B. 整批一查詢 | 列表只要 2 次 SQL | 回傳形狀改變、scope 跨監看、window 成本隨總觀測數成長（等於 FD-7 Decision 9 否決的全表 window） | 否決 |
| C. 每組日期相關子查詢 `LIMIT 2` | 讀取量和組數成正比 | 與 retention 的 window 是兩套語法，會漂移 | 否決 |
| D. Python 端快取 Snapshot | 不改 SQL | 失效時機散在各處 | 否決 |

### Decision
1. **讀取介面**：新增 `Repository.snapshot_observations_for_watch(watch_id, *, revision, currency, today, midnight) -> list[ObservationRecord]`。回傳該監看該 revision、`price_kind='live'`、`currency` 相符、`depart_date >= today` 的觀測中，每組 (depart_date, return_date) 依 `fetched_at DESC, id DESC` 的前 2 筆，加上 `fetched_at < midnight` 中最新的 1 筆，去重後依 `fetched_at DESC, id DESC` 排序。`views.list_page`、`DigestService.compose`、`CommandService._snapshot`、`CommandService.top_prices` 改用它，一監看一次 SQL；`Snapshot.build`、`cheapest_pairs`、`eligible`、`latest_per_pair`、`snapshot_min` 簽章與實作不變。列表與 `/list` 也傳 `taipei_midnight(now)`，多一筆零時前資料不影響輸出（見 3）。否決整批一查詢。
2. **單一定義**：`storage/repository.py` 定義唯一的片段產生函式 `_snapshot_keep_select(scope_sql: str) -> str`，產生 `SELECT id, scan_run_id FROM (...)`，內含唯一的具名視窗 `WINDOW snap AS (PARTITION BY watch_id, price_kind, currency, depart_date, return_date ORDER BY fetched_at DESC, id DESC)`，保留條件 `depart_date >= :today AND (rn <= 2 OR (fetched_at < :midnight AND (newer_fetched_at IS NULL OR newer_fetched_at >= :midnight)))`，其中 `rn = ROW_NUMBER() OVER snap`、`newer_fetched_at = LAG(fetched_at) OVER snap`。`scope_sql` 只能是 repository 模組層級常數（不得含使用者輸入；參數一律綁定）。讀取端 scope＝單一監看、單一 revision、live、指定幣別、`depart_date >= :today`；retention scope＝`price_observation JOIN watch` 目前 revision（全部監看、全部 kind／currency、不限出發日）。`retention_snapshot_runs` 改為「`_snapshot_keep_select(RETENTION_SCOPE)` 的 scan_run_id」UNION「原有 `rn_min = 1` 分支」，`rn_min` 分支只屬於 retention。
3. **等價性論證**：E＝`eligible(observations_for_watch(...))`，S＝新讀取結果，S ⊆ E。對每組日期 p，把 E 中 p 的觀測依 (fetched_at, id) 由新到舊排成 o1、o2、…。S 包含每組的 o1、o2，以及零時前最新那筆 m_p。
   - `cheapest`／`cheapest_pairs`：只用每組 o1，o1 ∈ S。
   - `delta_since(midnight)`：基準是每組 m_p，m_p ∈ S（不需任何前提；`fetched_at` 為固定寬度秒級 ISO 字串，midnight 為整秒，SQL 字串比較與 Python datetime 比較一致）。
   - `delta_since_previous_run`：L＝max(scan_run_id)。**A1**（同一輪對同一組日期最多寫一筆；`ScanService._query_pair` 每組只寫 cheapest 一筆）成立時，p 在第 L 輪最多一筆，排除後最新的是 o1 或 o2，皆在 S。**A2**（同一監看內 (fetched_at, id) 順序和 scan_run_id 順序一致；同監看掃描由 `ScanService.lock` 序列化、id 自增、fetched_at 取自掃描時鐘）成立時，E 中 scan_run_id 最大的那筆是所在組的 o1，所以 L(S)=L(E)。
   - S 非空若且唯若 E 非空。引理：任何滿足「每組 o1、o2、m_p ⊆ S ⊆ E」的 S 都產生相同輸出，所以多出來的零時前資料不影響。
   - 讀取端不包含 retention 的最低價那筆，因為快照四個輸出都不讀第 3 新以後的觀測；`min_amount`（創新低基準）仍是獨立的 `MIN()` 查詢。
4. **索引**：migration `0006_snapshot_index.sql` 只有 `CREATE INDEX ix_obs_snapshot ON price_observation(watch_id, watch_revision, price_kind, currency, depart_date, return_date, fetched_at DESC, id DESC, scan_run_id);`。不需要 FK-off 標記，不 CREATE／DROP／RENAME 任何表，不刪既有索引（`ix_obs_watch_pair` 是否冗餘另案評估）。
5. **詳情頁不變**：`views.detail_page` 繼續用 `observations_for_watch(watch.id, revision=watch.revision)`。在 steady180 量測並記入任務單，>300 ms 另開後續任務。
6. **效能門檻**（暖機 1 次後 10 次中位數，原始輸出記任務單）：steady180 的 `list_page` <300 ms（目標 <100 ms）、`DigestService.compose` <300 ms、`/list` <300 ms、單監看 `snapshot_observations_for_watch` <10 ms；FD-6 基準庫 `list_page` <100 ms；一輪掃描寫入（steady180、12 組）≤ 146 ms（121.9 ms × 120%）；`retention_snapshot_runs` 在 steady180 不超過 644 ms；詳情頁與 migration 0006 耗時只記錄。基準庫重用 FD-7 的 `steady180.db` 與 `base50k.db`（先複製再遷移，原檔不動）。
7. **SQLite 版本**：`WINDOW` 子句與 `LAG` 需 SQLite ≥ 3.25；由實作者於測試斷言 `sqlite3.sqlite_version_info >= (3, 25, 0)` 並記錄本機版本。

### Consequences
- 好處：列表、摘要、`/list`、`/watch`、`/scan` 回覆讀進 Python 的列數變成和「未出發組數」成正比（steady180 每監看 168 列 vs 8,640 列）；**實測更正（2026-10-29 總經理落檔）**：SQL 端的 window 仍要走完該監看未出發範圍的覆蓋索引，耗時仍與每監看觀測數線性相關，只是常數縮小約 6 倍（單監看 50.6 → 8.3 ms；列表 1,165 → 184.8 ms），尚未真正「脫鉤」；若日後要達 <100 ms 目標，需回到本節重評（例如每組日期有界子查詢，即方案 C，或維護快照物化表）；retention 規劃也受惠於同一索引；讀取與清除共用一個 SQL 定義，FR-R6 的「清除不改輸出」從測試保證變成結構保證。
- 代價：快照語意有 Python（權威）和 SQL（前置篩選）兩處表述，靠引理和等價性測試維繫，改一邊必須同步改另一邊並重跑等價測試；多一個 9 欄索引，每筆觀測寫入多維護一個索引；`delta_since_previous_run` 的等價依賴 A2，系統時鐘倒退超過同一監看兩輪間隔時新舊讀取可能不同（FR-R6 早已依賴同一前提，已知且接受）；詳情頁在穩態仍是全量讀取。
- 被約束的事：快照新增任何需要「第 3 新以後」觀測的輸出、`Snapshot` 改讀非 live 或其他幣別、改 `latest_per_pair` 的排序鍵、讓同一輪對同一組寫多筆，都必須回到本節重評，並同步修改 `_snapshot_keep_select`。

### 新增約束
- **C-55 讀取介面與呼叫端**：`Repository.snapshot_observations_for_watch(watch_id, *, revision, currency, today, midnight) -> list[ObservationRecord]` 存在且只執行 1 次 SQL；`views.list_page`、`DigestService.compose`、`CommandService._snapshot`、`CommandService.top_prices` 改呼叫它；`grep observations_for_watch src/` 的呼叫端只剩 `views.detail_page`（以及 repository 定義本身）；`services/price_snapshot.py` 的 diff 為空；`list_page` SQL 次數和 FD-7 相同（計數 fake repository，20 監看＝1＋20），摘要與 `/list` 也是一監看一次；`/watch` 前 3 名等於詳情頁 `top[:3]`（C-51）仍有測試且通過。
- **C-56 單一定義**：`storage/repository.py` 只有一個 `_snapshot_keep_select`；`WINDOW snap AS` 在 `src/` 全域只出現 1 次（grep 測試）；`snapshot_observations_for_watch` 和 `retention_snapshot_runs` 的 SQL 都由它組成；`scope_sql` 引數只是模組層級常數（grep 或 AST 測試：呼叫端不得傳 f-string 或變數拼接）；`rn_min` 分支只在 `retention_snapshot_runs`；`OVER (`、`OVER snap` 只出現在 `storage/repository.py`（grep 測試）。
- **C-57 等價性測試**：真實 SQLite 加隨機資料（多組日期、live 與 cached、兩種幣別、兩個 revision、已出發與未出發、單程 `return_date` 為 NULL、同秒多筆；生成時遵守 A1、A2），多個種子下比對 `Snapshot.build(observations_for_watch 全量)` 和 `Snapshot.build(snapshot_observations_for_watch)` 的 `cheapest`、`delta_since_previous_run()`、`delta_since(midnight)`，以及 `cheapest_pairs` 的完整清單，全部相等。具名案例各一個測試：(a) 同一組連續兩輪都有取樣（基準＝第 2 新）；(b) 某組最新一輪沒取樣（基準＝該組最新）；(c) `fetched_at` 相同、id 不同（含跨輪），以 id 決勝；(d) 最新一輪只寫 cached 或他幣（L 取自 eligible）；(e) `fetched_at` 正好等於 midnight（不算零時前）和前 1 秒（算）；(f) 某組只有零時後的觀測（delta 為 None）；(g) 已出發與舊 revision 不回傳；(h) 無觀測（cheapest 與兩種 delta 都是 None）；(i) 同一組有 ≥5 筆時回傳筆數 ≤3。A1 守護測試：`ScanService.scan_watch` 在同一輪對同一組日期最多寫入 1 筆觀測（取樣含重複組時也一樣）。retention 等價：測試內保留 FD-7 版 `retention_snapshot_runs` SQL 原文當對照，隨機資料下新舊回傳的 run 集合相同；FR-R6 與 C-53 全部測試原樣通過。
- **C-58 Migration 0006 與查詢計畫**：`0006_snapshot_index.sql` 只含 1 行 `CREATE INDEX ix_obs_snapshot`（欄位順序如 Decision 4），全檔沒有 CREATE TABLE、DROP、RENAME、FK-off 標記；v5 DB 遷移後各表筆數不變、`foreign_key_check` 為空、`integrity_check` 為 ok、索引存在且欄位順序正確（`PRAGMA index_xinfo` 斷言，含 `fetched_at`、`id` 為 desc）。`EXPLAIN QUERY PLAN` 斷言：(1) 單獨 EXPLAIN 讀取 scope 下的 `_snapshot_keep_select`，必須含 `ix_obs_snapshot` 和 `COVERING INDEX`，不得含 `SCAN price_observation` 和 `USE TEMP B-TREE`；(2) 完整讀取 SQL 不得含 `SCAN price_observation`、`SCAN watch`（最外層取整列只能是 rowid 查找，最外層 ORDER BY 允許一個 temp b-tree）；(3) 若 (1) 的「無 TEMP B-TREE」做不到，回報原始 plan 給 tech-architect 裁決，不得自行放寬。原始 plan 輸出記任務單。
- **C-59 效能與紀錄**：依 Decision 6 逐項量測，原始輸出和步驟（DB 複本路徑、遷移耗時、暖機與次數）記在 `work/tasks/FD-8.md`；任一門檻未過，不得標 done。
- **C-60 模組邊界**：`tests/test_architecture.py` 的 ALLOWED 不變；`services/retention.py` 的 diff 只能是零或僅呼叫端參數調整，且不含 SQL 字串；services 的非 docstring 字串常值不出現整字 `price_observation`、`OVER`、`WINDOW`（AST 整字比對；既有識別字 `FAILED_SCAN_WINDOW`、`NO_EMBEDDED_WINDOW` 與 docstring 不在此限，2026-10-29 總經理裁定）；新的 repository 方法沒有網頁或排程的 import。

## FD-9 增補：多目的地比價與三項收尾（2026-10-29，tech-architect 評估；不另開 ADR；總經理落檔）

範圍：固定一組日期、對 2～8 個目的地各查一次的「多目的地比價」，在背景執行，結果依總價排序，可預填新增監看；外加三項文案收尾（`/scan` 零查詢輪、詳情頁「已出發」空狀態、旅程天數 N–N）。屬 D-2、D-3、D-6 範圍：不新增執行期依賴、不改 import 方向表；新增 migration 0007（純新增）、`services/comparison.py`、`services/comparison_views.py`、兩個 domain 型別。
**總經理裁示（納入，不再開放）**：固定 1 位成人、預設經濟艙（CEO 只要單人）；不做 Telegram `/compare`；額度不足整體拒絕（與探索 C-45 一致，不採部分完成）；城市代碼與轄下機場同時選算重複；目的地 2～8；比價與探索互斥；不寫監看歷史、不推播；24 小時重用、7 天清除（自 created_at 起算）；日期下限採「今天」（與既有 `check_not_past` 一致）；migration 0007。

### Context
- 0004 的 `exploration` 以「單一目的地＋月份」為形狀：`destination NOT NULL length=3`、`month NOT NULL`、`total 1–31`、來回時 trip_days 必填 1–30，cell 的 PK 是 `(exploration_id, depart_date)`。比價是「單一日期組＋多目的地」，形狀正好相反。
- `active_exploration()` 有三處呼叫：`ExplorationService.create`、`commands.py`、`retention.py`。`queries_used_since` 加總的是 scan_run 和 exploration；健康頁的未內嵌比例讀 `exploration_cell_counts_since`。
- 單一 worker 加 `scan_lock`，掃描、探索、清除本來就序列執行；`create` 的互斥只靠 `ExplorationService._create_lock`（實例層級）。
- `domain/airports.py` 已有 `city_code` 與 `city_group()`，TYO/OSA/SEL/BJS/NYC 有轄下機場對應。
- `explore.html` 的表單元素 id 是頁面唯一的（`f-origin`、`lb-origin`…），同一頁放兩張表單會撞 id。

### 方案比較
| 方案 | 優點 | 缺點 | 風險 | 結論 |
|---|---|---|---|---|
| A. 重用 `exploration`＋`exploration_cell`，加 `kind`，cell 改 PK | 少兩張表；active／purge／recover 自然涵蓋兩種 | 要重建兩張表（FK-off、資料搬移）；`month`、`destination`、`total`、trip_days 的 CHECK 都要改成依 kind 分支；探索的每個 repository 查詢都要加 `kind` 篩選；`exploration_views`／`watch_prefill` 分支變多 | C-43 的 CHECK 測試語意改變；漏加 `kind` 篩選會讓比價出現在探索清單或被當成可重用 | 否決 |
| B. 新表 `comparison`／`comparison_cell`，服務平行 | 0007 純新增；探索的 schema、查詢、測試零變更；CHECK 可以照比價的形狀精準定義 | active、purge、recover、額度加總要在兩處各寫一次；`_run` 迴圈約 25 行重複 | 互斥漏檢（靠共用 lock 和交叉檢查的測試把關） | **採用** |
| C. 通用 `query_batch` 父表，探索和比價都遷過去 | 長期最一致 | 要重建探索資料與全部 FD-6 測試，超出本批範圍 | 回歸面最大 | 否決 |
| 服務 X. 抽出共用 cell 迴圈，`ExplorationService._run` 改用它 | 迴圈只寫一份 | 動到 FD-6 已驗收的執行路徑；兩邊的 repo 寫入鍵與最終狀態規則不同 | 探索回歸 | 否決，只共用 `SourceQuery`／`cell_update`／`CellUpdate` |
| 頁面 Y. `/explore` 加分頁或第二區塊 | 一頁完成 | id 衝突要重新命名；分頁要靠 JS；`explore_page()` 和既有樣板變動大 | 探索頁 e2e 回歸 | 否決，改用子頁 `/explore/compare`，`/explore` 只放入口 |

### Decision
1. **Schema：migration `0007_comparison.sql`**（只有 CREATE TABLE／CREATE INDEX，沒有 FK-off 標記）。
   - `comparison`：`id`；`condition_key` CHECK `GLOB 'cmp1|*'`；`origin` 3 碼；`destinations` TEXT，依輸入順序以逗號分隔，CHECK `length(destinations) = total*4-1`；`trip_type`；`depart_date`、`return_date` 符合 `YYYY-MM-DD` GLOB；單程時 return 必為 NULL，來回時 return 必填且 ≥ depart；`max_stops`、`cabin`、`adults`、`children` 的 CHECK 逐字沿用 0003／0004（domain 永遠寫 1／0）；不設 airlines／dep_hour 欄位；`currency`；`status` queued/running/done/failed；`total` 2–8；`done` 0–total；`queries_used`；`created_at`、`started_at`、`finished_at`、`error_summary`。索引 `(condition_key, created_at)`、`(created_at)`、`(started_at)`。
   - `comparison_cell`：FK CASCADE；`position` 0–7；`destination` 3 碼；狀態與結果欄位和 `exploration_cell` 相同（CHECK 逐字沿用）；PK `(comparison_id, position)`，UNIQUE `(comparison_id, destination)`；CHECK `(status='ok') = (amount_minor IS NOT NULL)`。
   - 不設 `rejected` 狀態：被拒絕的比價不建列。
2. **Domain**：`models.ComparisonTarget`（滿足 `SearchConditions`，`airlines=()`、時段 None、`adults=1`、`children=0`）；`models.ComparisonSpec`（origin、destinations 輸入順序不重複、trip_type、depart_date、return_date、max_stops、cabin、currency，`adults=1`、`children=0` 固定；`.pair`、`.target(code)`、`.condition_key()`，鍵格式 `cmp1|origin|D1,D2,..(排序)|trip_type|depart|return或-|max_stops或-|1|0|cabin|currency`）；`search_for(spec.target(d), spec.pair, spec.currency)` 仍是唯一的 `FlightSearch` 建構點；`validation.validate_comparison(raw, today)`：目的地 2～8、不得重複（同代碼或城市對其轄下機場；同城市兩個機場如 NRT＋HND 允許）、不得等於出發地或與出發地同城市；日期今天到今天+365；`date_input` 為 `fixed`（來回要填回程日，可同日）或 `stay`（只限來回，旅程天數 1～30）；單程時忽略回程日與天數；一律忽略 adults／children／airlines／dep_hour_*。
3. **執行模型**：`ComparisonService`（create／run／recover_interrupted／purge_expired／status／quota／get），sources 與 `ScanService`／`ExplorationService` 是同一個 list 物件。`create` 依序：驗證 → 24h 內同 key 且 `done` → 200 reused → 有 queued/running 的比價：同 key 回 200 joined、否則 409 busy → 有進行中的探索 409 busy → 排程未跑 409 scheduler_off → 可用額度 < N 時 409 quota → 同一 transaction 寫入父列與 N 個 pending 格 → 排 `compare:<id>` job → 202。`create` 持有 `app.py` 建立、與 `ExplorationService` 共用的 `batch_create_lock`；`ExplorationService.create` 加一步：有進行中的比價就 409 busy。job `compare:<id>`（date trigger、misfire None、max_instances 1）取得 `scan_lock` 後依 position 逐格查；額度 ≤0 → `skipped/global_hourly_limit` 停止；斷路器全開 → `breaker_open` 停止；每格寫入與 `done += 1`、`queries_used += attempts` 同一 transaction。結束時有任何 skipped 即 `failed`（附原因），否則 `done`；例外時其餘格 `interrupted`、狀態 `failed`。`ScanScheduler.start` 先呼叫兩個 `recover_interrupted()`；新增每小時 job `comparison-purge`；`next_run_time()` 排除 `compare:` 和 `comparison-purge`。`queries_used_since` 加總三張表；健康頁未內嵌比例另讀 `comparison_cell_counts_since`。
4. **讀取模型與頁面**：`services/comparison_views.py::ComparisonViewService`。排序為模組層級純函式：可排名（ok、同幣別）依 `(amount_minor, position)`，其餘依 position 排後。每列有非空狀態文字；skipped 列不給查票連結與「建立監看」，其他列有 tfs 連結（builder 失敗退回文字連結並註明）；價格旁附 `total_price_note(1,0)`。頁面頂部顯示條件摘要（含「1 位成人」）、`COMPARISON_REFERENCE_NOTE`＋`DISCLAIMER`、排序說明、超過 24 小時提醒、`?reused=1` 且 done 的重用說明、failed 的未完成說明。路由：`GET /explore/compare`、`GET /comparisons/{id}`、`POST /api/comparisons`、`GET /api/comparisons/{id}/status`（四欄、no-store）、`GET /watches/new?from_comparison=<id>&destination=<CODE>`。`/explore` 加入口卡片，`explore_page()`、`settings_page()` 新增 `active_comparison` key。
5. **三項收尾**：F1 `command_scan_result_message` 在 `queries_used == 0` 時輸出「本輪排定 N 組日期」，其他逐字不變；F2 `detail_page` 新增 `top_empty_note`：有紀錄、`top` 為空且目前 revision 所有觀測出發日都早於今天（台北）時為 `DETAIL_ALL_DEPARTED`；F3 新增 `domain/trip_labels.stay_range_label(min, max)`，相等「N 天」、不同「A–B 天」；`views.dates_text` 改用它（`/watch` 自動同口徑），`watch_detail.html` 改用 view 的 `stay_label`。
6. **文案**：新字串全部放 `domain/messages.py` 並納入 `all_static_texts()`；`BANNED_PHRASES` 追加「推薦」「最佳」；比價頁與收尾文案送 risk-compliance-officer。

### Consequences
- 好處：探索的 schema、查詢、執行路徑與測試完全不動；比價的 CHECK 精準；額度、節流、快取、斷路器、worker 與掃描／探索同一套；`done` 代表全部查完，重用規則簡單；三項收尾單點修改。
- 代價：active／recover／purge／額度加總兩處維護；`_run` 迴圈約 25 行重複（第三種批次時回本節重評方案 C）；比價最多佔每小時 8 次，期間掃描順延；額度不足時連 2 個目的地也整體拒絕；中斷的結果不重用；Telegram `/scan`、`/status` 在比價期間不提比價（已知缺口，掃描不會丟）；7 天從 created_at 起算；航空名稱沿用探索呈現。
- 被約束的事：多人、航空與時段篩選、多組日期、多出發地、比價監看、寫入價格歷史、部分完成、Telegram `/compare`、第三種背景批次，都要回到本節重評。

### 新增約束
- **C-61 Migration 0007**：檔名 `0007_comparison.sql`；只有 CREATE TABLE（`comparison`、`comparison_cell`）與 CREATE INDEX；無 FK-off 標記、DROP、RENAME、ALTER，無對 `exploration*` 的敘述（grep）。在有資料的 v6 DB 上遷移後既有表筆數不變、`foreign_key_check` 空、`integrity_check` ok、`*.pre-v7.db` 存在；新 DB 不備份。CHECK 必須拒絕：key 非 `cmp1|` 開頭；`total` 1 或 9；`done > total`；`status='rejected'`；單程帶 return；來回缺 return；return 早於 depart；`depart_date='2026-1-5'`；`destinations` 長度與 total 不符；cell `position` 8 或 -1；`destination='TO'`；同比價重複 destination；ok 無金額；非 ok 有金額；`amount_minor=0`；`depart_time='7:55'`。人數與艙等 CHECK 案例與 0003 逐條相同；刪除比價 CASCADE 刪格。
- **C-62 Domain 與驗證**：`ComparisonSpec`、`ComparisonTarget` 在 `domain/models.py`；grep `FlightSearch(` 只在 domain 與測試；`ComparisonTarget` 與等價 `WatchSpec` 的 `cache_key()` 相同；`condition_key()` 有 `cmp1|` 前綴、與目的地順序無關、`stay` 與等價 `fixed` 同鍵、任一條件改變鍵就變、含 `|1|0|`；`ExplorationSpec.condition_key()` golden 不變。`validate_comparison` 422 矩陣：目的地非 list、含非字串或空白、1 個、9 個、同代碼重複、TYO＋NRT（兩種順序）、等於出發地、與出發地同城市、表外代碼、未驗證城市（SPK）、昨天、今天+366、回程早於出發、回程超上限、天數 0／31／"abc"、天數使回程超上限、max_stops=3、艙等不合法；允許：NRT＋HND、今天、今天+365、回程等於出發日、單程帶回程或天數（忽略）、`adults=3`／`children=2`／airlines（忽略，spec 為 1／0／()）。
- **C-63 執行、額度、互斥**：比價只經 `compare:<id>` job（misfire None）；POST 期間 fake source 0 次；三個服務 sources 同物件（`is`）。五種結果各有測試且被拒不建列、查詢 0 次：invalid 422；reused（24h 內 done、順序不同亦算、可用額度 0 也能重用；超過 24h+1 分或最近為 failed 不重用）；busy（同 key 進行中 → 200 joined；不同 key → 409；探索進行中 → 409 帶 `progress_url=/explorations/<id>`；反向：比價進行中探索 POST → 409、body 無 `id`、message 含 `/comparisons/<id>`）；scheduler_off；quota（可用 0／N−1 → 409 附 hourly_left、needed；N／N+1 → 202）。barrier 同時 POST 恰建一筆。額度足夠時對外查詢恰為 N，destination 與 position 對應、日期組相同。第 k 格後拋例外 → `done == k`、failed、其餘 `interrupted`；中途額度歸零 → `global_hourly_limit`、failed、`error_summary` 有原因；斷路器開 → `breaker_open`、failed；blocked／no_data 不中斷；全部未內嵌時 `consecutive_failures` 不變、斷路器關、無維運通知。`recover_interrupted` 在排 job 前呼叫；purge 只刪超過 7 天且不在 queued/running；`next_run_time()` 排除 `compare:` 與 `comparison-purge`。`queries_used_since` 含 comparison；未內嵌比例含比價格。跑完後 `price_observation`／`alert_state`／`notification` 筆數不變、watch 逐欄不變。`comparison.quota()` 與 `exploration.quota()` 同資料下相等。
- **C-64 端點與輪詢**：status 恰四 key、no-store、不需 header、404、無寫入；POST 缺 header 403；`/comparisons/{id}` 404 頁含 `COMPARISON_NOT_FOUND`；`/explore/compare` 200；導覽列項目數不變，compare 兩頁「探索」有 `aria-current`。`from_comparison` 不合法 id／目的地不在比價內／該列 skipped → 200 空白表單加提示；合法時逐欄斷言預填、watch 筆數不變。前端輪詢 ≥2 秒、120 秒無進度或超過 `total×30+60` 秒停、done/failed reload、逾時文案不含「失敗」；`app.js` 無 `innerHTML`；C-46 既有探索輪詢測試不修改且通過。
- **C-65 結果表**：排序純函式涵蓋 AC-S1（7,800／9,200／11,000／無資料／被擋）、AC-S2（同價依輸入順序）、currency_mismatch 排有價格之後；無價格列 label 非空且非「0」；skipped 列無 `booking_url`／`watch_url`，其他都有，builder 拋例外退回文字連結帶 `booking_note`；有價格列含「（1 人總價）」；摘要含「1 位成人」；`DISCLAIMER` 與 `COMPARISON_REFERENCE_NOTE` 在頁面；24h 提醒、`reused=1` 且 done 的重用說明、failed 未完成說明各有斷言；`comparison_page` 恰 2 次 SQL，`compare_page` SQL 次數不隨歷史筆數增加。
- **C-66 文案與風控**：新字串由 `comparison_static_texts()` 納入 `all_static_texts()` 並通過 `BANNED_PHRASES`；`BANNED_PHRASES` 追加「推薦」「最佳」（若既有測試斷言 tuple 全等，回報 tech-architect）；測試掃 `compare.html`、`comparison.html`、`app.js` 新增區段不含「建議」「最佳」「現在買」「划算」「推薦」；風控結論記任務單。
- **C-67 不傷探索與模組邊界**：`exploration.py` diff 只限 `create_lock` 參數與 comparison busy 分支；`exploration_views.py` diff 只限 `explore_page()` 新增 `active_comparison`；`ExplorationSpec`、`month_pairs`、`validate_exploration`、0004 檔案、`retention.py`、`commands.py` diff 為空；既有探索測試檔不修改且全綠；`tests/test_architecture.py` ALLOWED 不變；`services/` 不 import `sources`／`scheduler`／`web`；`scheduler/` 仍只 import services。
- **C-68 三項收尾**：F1 `queries_used==0` 輸出含「本輪排定 12 組日期」、不含「對外查詢 0 次」；`queries_used=5` 逐字「本輪取樣 N 組日期，對外查詢 5 次」。F2 全部已出發時有 `top_empty_note`、頁面不含「尚未查到價格。」；無紀錄仍「尚未查到價格。」；有未出發價格時表格不變。F3 `stay_range_label(4,4)=="4 天"`、`(3,5)=="3–5 天"`；`dates_text` 輸出「旅程 4 天」；`/watch`、列表、詳情同口徑。AC-F4：只能修改直接斷言上述三字串的既有期望值，逐條列任務單附理由；其餘 957 項不修改且全綠。
- **C-69 UI e2e（qa-e2e；無人值守時依 e2e-fallback）**：(1) `/explore` 入口卡片；(2) 表單預設值（TPE／來回／經濟艙／無人數欄位）；(3) 自動完成鍵盤與滑鼠各加入目的地、移除一個、chip 顯示中文名＋代碼、滿 8 個不可再加；(4) TYO＋NRT 送出 → 欄位旁錯誤；(5) 預覽 N 與可用額度隨增減更新；(6) 進度頁計數遞增、完成自動載入結果表、關閉再開仍接續；(7) 結果表排序與各原因文字；(8) 375px 只有 `table-wrap` 橫向捲動；(9) 「建立監看」預填、頂部提示、未寫入監看；(10) 探索與比價互斥訊息與進度連結；(11) 比價進行中 `/explore` 與設定頁提示；(12) 實測：3 個目的地真實比價、健康頁本小時用量剛好加 3；手動開 3 條 tfs 連結核對條件。
- **C-70 效能紀錄**：8 個目的地比價實測總耗時；FD-6 基準庫加 50 筆比價後 `compare_page`、`comparison_page` 暖機 1 次後 10 次中位數 <100 ms；原始輸出記 `work/tasks/FD-9.md`。

## FD-10 增補：出發星期篩選、探索跨多月與三項收尾（2026-10-31，tech-architect 評估；不另開 ADR；總經理落檔）

範圍：彈性窗監看與探索新增「出發星期」多選（預設全選＝不篩）；探索可選連續 1～3 個月（總格數 ≤31）；條件摘要顯示星期；三項收尾（`/status`／`/scan` 比價順延、健康頁比價筆數、`exploration.html` 寫死字串移入 messages）。屬 D-2、D-6 範圍：不新增執行期依賴、不改 import 方向表；新增 migration 0008（`watch` ADD COLUMN＋`exploration` 重建）、新增 domain 模組 `domain/weekdays.py`。星期只在本機展開日期時過濾，**不會送進 Google 查詢**（`FlightSearch`、`cache_key()`、`search_for` 不變）。

**總經理裁示（納入，不再開放）**：星期預設全選＝不篩，且全選時與現況輸出逐字相同；星期改變算條件變更、換 revision；跨月上限 3 個月、總格數 ≤31；探索 `condition_key` 從 v1 升為 v2，兩版互不重用，v1 舊紀錄照舊可讀；比價與固定日期監看不適用；三項收尾納入本批；migration 編號 0008；`mode=month` 預填帶入星期；月份範圍顯示「2026 年 12 月～2027 年 2 月」、單月沿用既有格式；探索頁 h1 暫定「探索出發日價格」與說明句送風控定稿。

**修訂既有條文**：C-44「`condition_key()` 有 `v1|` 前綴」改為 `v2|`，「`month_pairs` 最多 31 格」保留給舊介面包裝，production 改用 `range_pairs`、超過上限回 422 不截斷；C-62「`ExplorationSpec.condition_key()` golden 不變」由本節取代（golden 改 v2，列 AC-F4）；C-67 各項「diff 為空」只適用 FD-9，本批依本節修改 `ExplorationSpec`、`validate_exploration`、`commands.py`、`exploration_views.py`，`retention.py` 仍須 diff 為空；FD-6 Decision 2 新增 `month_to`（可 NULL）與 `depart_weekdays`；FD-6 Decision 7 `weeks` 保留、新增 `calendar_months`；FD-9 Consequences「`/scan`、`/status` 不提比價」由本節結案；C-47 整月預填等價測試擴充到月份範圍與星期。

### Context
- 彈性窗每輪最多取樣 12 組，日期組越多、週五／週六的組合越少被抽到；探索每個出發日耗 1 次額度。
- `first_pair`／`is_expired` 是「還有沒有未來日期」的 O(1) 判斷；若不看星期會出現「判定未過期但展開為空」。
- `exploration.condition_key` 的 CHECK 寫死 `GLOB 'v1|*'`，SQLite 無法 ALTER CHECK，只能重建表；`exploration` 是 `exploration_cell` 的父表（FK CASCADE），重建順序依 FD-5 Context。
- `exploration_cell` PK `(exploration_id, depart_date)` 跨月仍唯一；`total 1–31` 即本批上限。
- `domain/dates.py` import `validation.MAX_DAYS_AHEAD`，validation.py 不能反向 import dates.py；需展開日期的檢查由 services 呼叫 domain 純函式（與 `EXPLORATION_NO_DATES` 做法一致）。
- `timeutil.weekday_label(day)`／`WEEKDAY_LABELS` 已存在，是星期名稱唯一來源。
- 探索表單預估格數目前由 `app.js::estimateCells` 用 JS 日期運算；JS `getDay()` 以 0＝週日，與 Python 0＝週一不同，規則會出現兩份且易錯位。
- `views.has_filters` 只代表「Google 端的篩選」，星期篩選不該算進去。

### 方案比較
| 項目 | 採用 | 否決與理由 |
|---|---|---|
| 星期儲存 | bitmask 整數 `NOT NULL DEFAULT 127`（與順序無關、CHECK 一句、全選單一值、ADD COLUMN 既有列自動全選） | 逗號字串：正規形難用 CHECK 表達、全選要在 NULL 與 `"0,…,6"` 間正規化 |
| domain 型別 | `tuple[int, ...]` 排序去重（與 `airlines` 一致） | `frozenset`：序列化仍要排序、與慣例不一致 |
| JSON 編號 | 0–6、0＝週一（等於 `date.weekday()`、bit 位置、`month_weeks` 欄序） | ISO 1–7：每層 ±1 換算 |
| 探索表 | 只重建 `exploration`：保留 `month` 為起始月、新增 `month_to` NULL、`depart_weekdays`；cell 不動 | 改名 `month_from`／`month_to` 兩表重建：回歸面大；只 ADD COLUMN 仍掛 `v1|`：違反互不重用 |
| 「未查（星期篩選）」 | 顯示層推導、不寫列 | 新增 cell 狀態：要重建 cell、稀釋 total 與額度語意 |
| 預估格數 | 伺服端給「每月各星期可查日數」，JS 只加總 | 預覽 API（成本高）；JS `getDay()` 自算（規則兩份且 0 意義不同） |

### Decision
1. **Migration `0008_depart_weekdays_and_exploration_range.sql`**（首行 `-- flight-deals: foreign_keys=off`）：`ALTER TABLE watch ADD COLUMN depart_weekdays INTEGER NOT NULL DEFAULT 127 CHECK (typeof(depart_weekdays) = 'integer' AND depart_weekdays BETWEEN 1 AND 127);`（不重建 watch，revision 與 `sample_offset` 不動；「固定日期一律存 127」由 domain 保證）。依 0003 順序重建 `exploration`：建 `exploration_new` → `INSERT … SELECT`（明列欄位、id 原樣）→ DROP → RENAME → 重建 `idx_exploration_condition`、`idx_exploration_created`、`idx_exploration_started`。0004 其他 CHECK 逐字沿用，變動三處：`condition_key TEXT NOT NULL`（拿掉欄位層 GLOB）；`month_to TEXT CHECK (month_to IS NULL OR (month_to GLOB 'YYYY-MM' AND substr(month_to,6,2) BETWEEN '01' AND '12' AND month_to > month))`；`depart_weekdays INTEGER NOT NULL DEFAULT 127 CHECK (... BETWEEN 1 AND 127)`。表層 CHECK：`((condition_key GLOB 'v1|*' AND month_to IS NULL AND depart_weekdays = 127) OR condition_key GLOB 'v2|*')`。「最多 3 個月」不寫進 CHECK。其他表不動；備份 `*.pre-v8.db` 由 runner 產生。
2. **Domain 型別**：新增 `domain/weekdays.py`（stdlib only）：`ALL_WEEKDAYS`、`ALL_WEEKDAYS_MASK=127`、`normalize_weekdays`、`weekdays_to_mask`、`weekdays_from_mask`、`is_all_weekdays`。`WatchSpec.depart_weekdays: tuple[int, ...] = ALL_WEEKDAYS`，`search_shape()` 末端加正規化星期 tuple。`ExplorationSpec` 新增 `end_year`／`end_month`（None＝單月）、`depart_weekdays`；`year`／`month` 語意為起始月；`condition_key()` 改 v2（結束月寫實際值、星期寫 mask 十進位）。`FlightSearch`、`search_for`、`cache_key()` 不變。
3. **日期展開**：`expand_pairs` 簽章不變，固定日期或全選走原碼快速路徑，否則只在出發日層過濾（回程不篩）；`first_pair` 考慮星期（最多檢查 7 天，O(1)）；新增 `weekday_filter_leaves_nothing(spec, today)`；探索新增 `range_months`、`range_pairs`（各月依序、過濾星期、不截斷）、`month_weekday_counts(year, month, today)`；`month_pairs` 保留為 `range_pairs(...)[:MAX_MONTH_CELLS]` 只給既有測試，`services/` 不得呼叫；`sample_pairs` 不改。
4. **驗證與 422**（validation.py 不 import dates.py）：監看 `depart_weekdays` 只接受 0～6 的 int list，空 list `WEEKDAYS_REQUIRED`，格式錯 `WEEKDAYS_INVALID`，新增缺 key＝全選、修改缺 key＝沿用，固定日期忽略並存全選。探索 `month_to` 缺／空／等於 `month` ＝單月；格式錯 `MONTH_INVALID`、早於起始 `MONTH_TO_BEFORE`、跨月 > `EXPLORATION_MAX_SPAN_MONTHS=3` 回 `MONTH_SPAN_TOO_LONG`。需展開的檢查在 services：`WatchService` 以 `weekday_filter_leaves_nothing` 回 `WEEKDAYS_NO_MATCH_WINDOW`；`ExplorationService.create` 先算 `range_pairs`：0 格且全選 → `EXPLORATION_NO_DATES`（逐字）；0 格有篩選 → `WEEKDAYS_NO_MATCH_MONTHS`；超過 `max_cells` → `{"month_to": EXPLORATION_TOO_MANY_CELLS}`；皆在重用、busy、額度之前，不寫列、不查詢；刪除 `[: self._max_cells]` 截斷。
5. **revision**：沿用 `search_shape` 比較；集合變動 +1，連帶既有 `reset_progress`（`sample_offset=0`、失敗輪數 0）與 `reset_alert_state`；不新增程式路徑。
6. **探索讀取模型**：`exploration_page` 新增 `calendar_months: [{year, month, label, weeks}]`，`weeks` 保留＝第一個月；無 cell 的日子依序判定 `weekday_filtered`（label「未查（星期篩選）」）→ past → out_of_range；分位與前 5 對全部 cell 計算；`month_label` 改 `month_range_label`；`exploration_conditions` 接上 `depart_weekdays_label`；最近清單 `month` 改範圍標籤；預填：單格固定日期不帶星期，`mode=month` 改月份範圍（`window_start=max(起始月1日,今天)`、`window_end=min(結束月月底+stay, 今天+365)`）並帶入星期。
7. **條件摘要**：唯一 helper `domain/trip_labels.depart_weekdays_label(weekdays) -> str | None`（全選 None；否則週一到週日順序頓號連接加「出發」；不做「週末」「平日」縮寫；名稱取 `timeutil.WEEKDAY_LABELS`）；`views.dates_text` 彈性窗非全選接「，{label}」（列表、詳情、`/watch` 同口徑）；`DigestRow.weekdays_label`；`messages.month_range_label`（單月＝`month_label`，跨月「A～B」）；新字串放 `domain/messages.py`、納入 `all_static_texts()`、過 BANNED_PHRASES、送風控。
8. **前端**：監看表單「出發星期」checkbox 群組 `data-show-when="date_mode=flexible"`，`collectWatch` 只在彈性窗送；探索表單起始月／結束月兩個 select、星期群組永遠顯示；預估格數由伺服端 `data-weekday-counts` 給每月各星期可查日數，JS 只加總，超過 `data-max-cells` 停用送出並顯示 `data-over-limit-text`；`app.js` 不得用 `getDay`／`getUTCDay`／`innerHTML`；全選單月時預估文字與現況逐字相同。
9. **三項收尾**：F1 `CommandStatus.comparison`，比價進行中 `/status` 在探索行後加「比價：比價進行中，掃描順延（已查 d／共 t）」、`/scan` 加 `COMMAND_SCAN_COMPARISON_DEFERRED`，皆以 `Repository.active_comparison()` 判斷，無比價時逐字不變，`schedule_scan` 仍只呼叫一次；F2 `Repository.table_counts()` 在 exploration 後加 `comparison`、`comparison_cell`，`MAINTENANCE_TABLE_LABELS` 加標籤，`retention.py` diff 為空；F3 `messages.EXPLORATION_STALE_FALLBACK` 逐字搬入，view 放 `stale_fallback`，樣板 `{{ e.stale_note or e.stale_fallback }}`，渲染逐字不變。
10. **不變**：比價、固定日期監看、`views.has_filters`、`FlightSearch`／查票連結、價格推播文案、各 status 端點白名單、`tests/test_architecture.py` ALLOWED。

### Consequences
- 好處：只看週五、週六時組數約減為 2/7，取樣覆蓋輪數同比例下降、探索額度同比例下降；三個月合計 ≤31 格一次看完；全選路徑與 FD-9 原碼相同、現有監看零變化；v1／v2 在 key 與 CHECK 層隔離；星期規則只在 Python 一處。
- 代價：再一次重建父表；`search_shape` 多一欄；改星期會重置漲跌基準與取樣游標；「最多 3 個月」只有 domain 守；預估格數可能高估（只在含第 12 個月且回程超出可查範圍時，可能誤停用按鈕，使用者可縮小範圍）；跨月分位以整段為母體；`exploration_quota_message` 跨月時換措辭；`month_pairs` 留測試用包裝；價格推播不顯示星期。
- 被約束的事：回程星期、比價星期、節日曆或連假判定、自動推薦星期、跨月超過 3 個月或 31 格、把星期送進 Google 查詢、把「未查」寫成 cell 列，都要回到本節重評。

### 新增約束
- **C-71 Migration 0008**：檔名 `0008_depart_weekdays_and_exploration_range.sql`，首行 FK-off 標記；對 `watch` 只有一句 ADD COLUMN；`exploration` 依「建 `exploration_new` → 明列欄位複製 → DROP → RENAME → 重建 3 個索引」；grep 不得出現 `RENAME TO exploration_old`、`legacy_alter_table`，不得有針對 `exploration_cell`、`comparison*`、`scan_run`、`price_observation` 的 CREATE／DROP／ALTER。測試環境為有資料的 v7 DB（≥2 watch 含 revision>1 彈性窗；scan_run、price_observation、alert_state、notification 各 ≥1；2 筆 exploration（done 含 cell、failed 含 skipped cell）；1 筆含 cell 的 comparison）。遷移後：各表筆數不變；watch 舊欄位逐欄相等、`depart_weekdays=127`、revision 與 `sample_offset` 不變；exploration 舊欄位逐欄相等（`condition_key` 位元組相同）、`month_to IS NULL`、`depart_weekdays=127`；`foreign_key_check` 空、`integrity_check` ok；`exploration_cell` DDL 仍含 `REFERENCES exploration(id)`、全庫不含 `exploration_new`；插入不存在父 id 的 cell 失敗、刪 exploration CASCADE；3 個索引存在且欄位不變；`*.pre-v8.db` 存在、新庫不備份。CHECK 拒絕：watch `depart_weekdays` 0／128／1.5／`'127'`；exploration v1 key 帶 `month_to`、v1 weekdays 48、`v3|` 前綴、`month_to = month`、`month_to < month`、`'2027-2'`、`'2027-13'`、weekdays 0／128。接受：v2＋`month_to` NULL＋48；v2＋`'2027-02'`。C-43 既有 CHECK 測試不修改且全綠。
- **C-72 Domain 型別與 revision**：`domain/weekdays.py` 只用 stdlib；127 種非空子集 mask↔tuple 來回相等；bit i 對應 `weekday()==i`。`search_shape()` 末端為正規化星期。測試：全選→(4,) +1；(4,)→(4,5) +1；(5,4) 與 (4,5) 不 +1；全選→全選、修改缺 key 不 +1；改回全選再 +1；固定日期送任何星期存全選不 +1；+1 後 `sample_offset=0`、`consecutive_failed_scans=0`、`alert_state` 重置；改名稱不 +1；遷移後 spec 的 `search_shape()` 等於遷移前加全選。`FlightSearch(` 仍只在 domain 與測試；`FlightSearch`、`search_for`、`cache_key()` diff 為空。
- **C-73 驗證矩陣**：`depart_weekdays` 422：`[]`、`"4,5"`、`[7]`、`[-1]`、`[true]`、`[4.0]`、`["4"]`、`{}`；允許 `[4,4]`→(4,)、缺 key。固定日期送 `[7]` 不報錯存全選；比價送星期被忽略。AC-D5（12/1～12/3 只選週六）422「所選日期區間內沒有符合出發星期的日子」且 watch 筆數不變；單程、單日窗、當天週五只選週五允許；已過期監看只改名稱不出星期錯誤。探索 `month_to` 422：早於起始、跨 4 月、超出 12 個月、格式錯；允許缺 key／空／等於起始（spec 與 key 相同）。格數 31 允許、32 回 422（`month_to`）；只選週五 0 天 → 422（`depart_weekdays`）；全選 0 天 → `EXPLORATION_NO_DATES`。每種 422 斷言：exploration 筆數不變、fake source 0 次、不排 job、不檢查額度（額度 0 仍回 422 非 409）。
- **C-74 展開、首組與取樣**：測試內保留 FD-9 `expand_pairs` 原文對照，全選時逐組相等（單程／來回、跨月、跨年、2028-02-29、起始在過去、單日窗、min=max、366 天窗、1–60 天）；全選路徑不呼叫星期過濾（monkeypatch 斷言）。AC-D3 12 組、AC-D4 24 組（`window_start` 為週五要包含）；有篩選時輸出＝全選輸出中出發日符合者、回程任意、已排序。隨機矩陣下 `first_pair(spec) == (expand_pairs(spec)[0] if any else None)` 且 `is_expired` 一致；`first_pair` 候選日 ≤7。`sample_pairs` diff 為空；AC-D15：篩選後 ≤12 組一輪全涵蓋且出發日皆週五；>12 組時連續 ceil(T/12) 輪聯集＝全部。`range_pairs` 依月份、依星期、不截斷；`month_pairs == range_pairs[:31]`；C-44 既有 `month_pairs` 測試不修改；`services/` 不出現 `month_pairs(`。
- **C-75 探索 v2 key、重用與舊資料**：v2 golden 有測試（v1 golden 改 v2，列 AC-F4）；勾選順序不同 key 相同；全選與缺 key 相同；單月 `month_to` 缺或等於起始 key 相同；起始、結束、星期任一改變 key 就變；`ComparisonSpec.condition_key()` golden 不變。AC-M8：1 小時前 done 的 v1 紀錄，以單月全選 POST → created 非 reused；v2 3 小時前 done → reused、0 次查詢。AC-M10：v1 舊結果頁與最近清單不含星期「出發」字樣、不含「～」。AC-M11：purge 對 v1／v2 一視同仁。
- **C-76 日曆與前 5 名**：`calendar_months` 每元素有 year、month、label、weeks，`weeks == calendar_months[0].weeks`；未選星期日子 `status=="weekday_filtered"`、label「未查（星期篩選）」、優先於 past／out_of_range、DB cell 數等於 `total`、不顯示價格或連結。**全選單月**：固定 fixture 渲染 `exploration.html` 與 `explore.html`，HTML 與 FD-9 版快照逐字相同（快照在本批改檔前錄製）。跨月：每月一個 h3（單月不出現）；免責句與圖例各 1 次；前 5 跨月合併、同價依日期、每列完整日期。`views.has_filters` diff 為空。
- **C-77 摘要與文案**：`depart_weekdays_label` 在 `src/` 只定義一處；全選 None；(4,5)「週五、週六出發」；(6,0,2)「週一、週三、週日出發」；127 種組合不含「週末」「平日」「假日」。`dates_text` 彈性窗非全選接星期、固定日期永不接；`/watch`、列表、詳情、摘要都有含星期斷言；全選輸出逐字不變（既有測試不修改）。摘要 C-34 長度測試在每監看帶 6 個星期時仍通過。`month_range_label` 單月＝`month_label`。新字串在 `domain/messages.py`、納入 `all_static_texts()`、過 BANNED_PHRASES；掃描三個樣板與 `app.js` 新增區段不含「建議」「推薦」「最佳」「划算」「現在買」「週末」。風控結論記任務單。
- **C-78 三項收尾**：F1 比價進行中 `/status` 含「比價：比價進行中，掃描順延（已查 d／共 t）」、`/scan` 含「比價進行中，掃描順延」且 `schedule_scan` 恰 1 次；無比價無探索時兩回覆逐字同 FD-9；探索進行中既有提示不變。F2 健康頁維護區在「探索」後依序「比價」「比價明細」，其他列不變；`table_counts` 仍 1 次 SQL；`retention.py` diff 為空。F3 `exploration.html` 原始碼不含該字串、`messages.py` 含；stale 與非 stale 渲染與 FD-9 逐字相同。
- **C-79 模組邊界**：ALLOWED 不變；`domain/weekdays.py` 只 import stdlib；`validation.py` 不 import `domain.dates`；`services/` 不新增對 `sources`／`scheduler`／`web` 的 import；`app.js` 不含 `getDay`、`getUTCDay`、`innerHTML`；各 status 端點白名單不變（C-30、C-46、C-64 既有測試不修改）。
- **C-80 UI e2e**（qa-e2e；無人值守依 e2e-fallback）：(1) 新增監看彈性窗預設 7 天全勾，切固定日期隱藏、切回保留；(2) 全部取消送出：欄位旁錯誤、焦點移至錯誤；(3) AC-D5 訊息；(4) 編輯既有監看預設全勾、只改名稱不換 revision、只選週五後詳情顯示「週五出發」與新 revision；(5) 列表、詳情條件摘要含星期；(6) 探索表單預設起始＝結束、7 天全勾、預估文字與 FD-9 逐字相同；(7) 週五＋週六、三個月：預估即時更新；(8) 三個月全選：按鈕停用、顯示「請縮小月份範圍或減少星期」；(9) 結束月早於起始送出：`month_to` 旁錯誤；(10) 跨月結果頁分月標題、「未查（星期篩選）」文字、免責句一次；(11) 375px 只有 table-wrap 捲動；(12) v1 舊結果網址正常無星期／範圍字樣；(13) 「以所選月份建立彈性窗監看」預填起訖與星期、未寫入；(14) 健康頁比價兩列；(15) 實機 Telegram 比價進行中 `/status`／`/scan`（CEO 或總經理手動）。
- **C-81 效能**（暖機 1 次後 10 次中位數，原始輸出記 `work/tasks/FD-10.md`）：`expand_pairs` 366 天窗 × 旅程 1–60 天（最壞）與 3–9 天，各測全選、(4,)、(4,5)：全選 ≤ 同次執行 FD-9 對照的 110%，有篩選 ≤ 全選；`first_pair` <1 ms；一輪掃描寫入（steady180、12 組）≤146 ms；31 格跨 3 月 `exploration_page` <100 ms、`explore_page` <100 ms；migration 0008 在 steady180 複本耗時只記錄。
- **C-82 既有期望值保護（AC-F4）**：只能修改直接斷言以下項目的既有期望值，逐條列任務單附理由：`ExplorationSpec.condition_key()` v1 golden（含 C-62）；schema 最新版本 7→8；探索表單 h1、說明句、月份欄位 label 與 name 結構；`table_counts` 列數；`/status`、`/scan` 直接斷言比價行為的測試；其他本節明列形狀變更。`expand_pairs`、`sample_pairs`、`month_pairs`、C-43、C-61 既有測試不得修改；其餘既有測試（1166 項）不得修改且全綠。

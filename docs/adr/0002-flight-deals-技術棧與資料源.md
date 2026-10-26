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
  kind TEXT NOT NULL CHECK (kind IN ('price_alert','ops_source_failure','test')),
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

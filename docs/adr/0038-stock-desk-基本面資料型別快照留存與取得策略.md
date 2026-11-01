# ADR-0038：stock-desk 基本面資料型別、快照留存與取得策略

- 狀態：proposed（送 CEO 核可前須完成 P-1～P-12 的 spike 對照修訂）
- 日期：2026-11-01
- 決策者：tech-architect（草案）、CEO（核可）
- 依據：PRD `work/prd/2026-11-01-財務頁籤-N179.md`（FR-1～FR-14、欄位總表 D-01～D-18、Q8～Q17）；CEO 裁示 #90～#96；三份研究（data-engineer、quant-researcher、creative-lead，2026-11-01）
- 與既有 ADR 的關係：
  - **部分取代 ADR-0025**：D-12 Phase 5「基本面」的分期，在「財務頁籤的資訊展示＋公布日快照留存」範圍內提前（CEO #90、#95）；D-9「沒有資料源時顯示『資料不足』」在財務頁籤改用 D-5 的三分類。ADR-0025 其餘條文（含「基本面只列示、不解讀」、不得新增付費服務、不得以 LLM 或記憶補值、Phase 5 其他項目）不變。ADR-0025 狀態行加註本 ADR 編號。
  - ADR-0002：不取代。基本面同樣走可替換的抽象介面（`FundamentalsProvider`），但位置在 `app/fundamentals/`，不在 `app/data/`（ADR-0012 §7 的位置解讀只針對市場快照）。
  - ADR-0012 C-7、C-8：不受影響。不寫市場 DB，不用 `pit_` 前綴（比照 ADR-0016 K-19）。
  - ADR-0026：新 DB 檔不在庫存還原點範圍內；備份組新增一個檔（D-3）。ADR-0026 D-9 定案時須納入。
  - ADR-0005、ADR-0009：不消耗 Alpha Vantage 額度，不碰價格鏈。

> **落檔註記（tech-writer，2026-11-01）**
>
> 1. **來源與類別**：本檔是 `work/reviews/2026-11-01-ADR0038基本面資料型別-tech-architect.md` 第五節「ADR-0038 草案」的轉錄，屬記錄決策脈絡（B 類）。Context 至 Consequences 為草案主文照轉錄；附錄 A、B、C、D 分別為同一節後面的「對實作的約束」（C-1～C-32）、「測試」（T-1～T-26）、「VETO」（VETO-1～VETO-12）、「參考檔案」，皆照轉錄。tech-writer 落檔時**沒有讀 code、沒有執行程式**，也沒有替草案補任何技術細節。
> 2. **ADR-0025 尚未加註**：上方「部分取代 ADR-0025」與「ADR-0025 狀態行加註本 ADR 編號」是草案對**未來**動作的敘述。本 ADR 仍是 proposed，ADR-0025 現階段**沒有**被修改；加註要等 CEO 核可本 ADR 之後才處理（見「待決」）。
> 3. **行號與事實未重驗**：文內 `檔案:行號`（含 `app/data/interface.py:46-89`、`app/dividends/store.py:9-14,476-485`、`app/data/market_panel.py:21-35,217-236`、`app/data/sqlite_util.py:84-129`、`forecast/band.py:6-8`、`dirdef/definition.py:8` 等）是 tech-architect 撰寫時的快照，tech-writer 未逐條重驗，抽驗請以內容定位。來源評估檔自己標明：SEC 端點、欄位（`filed`、`accn`、`fy`、`fp`、`frame`）、流量限制、User-Agent 格式全部是未實測的假設，依賴這些的地方已列成 P-x；文內標〔推論〕者亦為草案自己的標註。
> 4. **一處指向文字調整**：草案 Consequences 末句原為「見下方 C-x、T-x、VETO」，落檔後附錄位置改為附錄 A、B、C，故該句改為指向附錄；除此之外正文未改動。
> 5. **未收錄的部分**：來源評估檔第一至四節（本次結論、各部門回報、驗證、下一步）與「需要 CEO 裁示的事項」CEO-1～CEO-6 屬轉存的過程性說明，本檔不收錄，需要時請讀來源檔。
> 6. **本 ADR 尚未經審查**：來源評估檔建議 qa-reviewer 加 Codex 第二意見，檢查 C、T 清單能否逐條驗證；此建議尚未執行。

---

## Context（背景）

1. 系統沒有任何基本面資料。`PriceBar` 只能裝「一檔、一天、OHLCV」，放不進會計期間、公布日、申報文件、重編等屬性（`app/data/interface.py:46-89`）。ADR-0014 已否決把不同形狀的資料塞進同一個介面。
2. CEO 要求從第一天起依公布日留存快照，而且不必等 UI（#95）。即時留存沒辦法事後補，晚一天就少一天的證據（量化回應 2.3、2.6）。
3. 用途只限展示（#90）。基本面不得進 signals、advice、alerts、forecast、outlook、playbook 與決策卡（FR-9、AC-16）。
4. 既有先例：
   - `dividend_events` 是 upsert，不是 PIT（`app/dividends/store.py:9-14,476-485`）。只有 `dividend_sync_runs` 是 append-only。
   - 市場 DB 每張表都有 append-only trigger，而且 `recorded_at` 只由 store 時鐘填入（`app/data/market_panel.py:21-35,217-236`）。
   - 研究 DB 以 import、字串、檔案三層隔離（`tests/test_research_isolation.py`）。
   - `add_missing_columns` 在 `BEGIN IMMEDIATE` 內重讀 schema 再遷移（N-154，`app/data/sqlite_util.py:84-129`）。
5. 外部資料源全部未實測，spike 由 CEO 在本機執行（#92）。凡依賴資料源事實的參數都列為 P-x。

## Options（選項比較）

### 型別放哪裡
| 方案 | 優點 | 缺點 | 風險 |
|---|---|---|---|
| L1 擴充 `PriceBar`／`MarketDataProvider` | 少一個抽象 | 形狀不同，ADR-0014 已否決同類作法 | 污染價格鏈與快取 |
| L2 新型別放 `app/data/interface.py` | 符合 ADR-0012 §7 的位置解讀 | advice 等模組本來就 import `app.data.*`，邊界只能逐個符號守 | 日後被順手接線 |
| **L3 新套件 `app/fundamentals/` 自帶介面（採用）** | 守門測試可以用套件層級一刀切 | 與 ADR-0012 §7 的位置解讀不同（CEO 知悉） | 低 |

### 放在哪個 DB 檔
| 方案 | 優點 | 缺點 | 風險 |
|---|---|---|---|
| D1 主 DB | 不增加需要備份的檔；和持倉同一個隱私邊界 | advice、playbook 開的就是這個檔，邊界只靠程式；ADR-0026 還原點要另外排除；寫入者多一類 | 庫存還原時快照被一起回捲 |
| D2 市場 DB | 性質相近（外部觀察、PIT） | 要修改 accepted 的 ADR-0012 C-8、T-3；與 `market_panel` 耦合 | 修改已核可的邊界 |
| **D3 獨立 DB（採用）** | 檔案層面隔離 advice 鏈；沒有跨檔引用，單獨還原也不會對不上（ADR-0027 否決 A3 的理由在這裡不成立）；不受庫存還原點影響 | 要定期備份的檔多一個 | 漏備份就失去無法重建的即時快照，以 C-26 處理 |

### 存什麼粒度
| 方案 | 優點 | 缺點 | 風險 |
|---|---|---|---|
| G1 只存對照後的項目（OCF、CapEx 等） | 小、好讀 | 對照錯誤會固化進快照；改規則後舊觀察無法重套 | 「公司未提供」不好判定 |
| **G2 存標籤白名單內的原始 fact（採用）** | 對照規則在讀取時套用、有版本；白名單擴充時如實標成回補 | 讀取時要多一步對照 | 低 |
| G3 只存整份原始回應 | 保真度最高 | 每份可能數 MB；讀取時要即時解析 | 頁面變慢；可在 P-7 決定是否作為 G2 的補充 |

### 怎麼取得
| 方案 | 優點 | 缺點 | 風險 |
|---|---|---|---|
| S1 開頁時抓 | 即時 | 違反 FR-11 第 1 點 | 否決 |
| **S2 排程：先查新申報，有新申報才抓 companyfacts（採用）** | 請求最少，符合「有新公布才重抓全量」 | 依賴申報清單端點（P-6） | P-6 不成立就退到 S3 |
| S3 排程：每次都抓整份 companyfacts | 簡單 | 流量較大 | 仍遠低於限流〔推論〕 |
| S4 只有 CLI 手動執行 | 最省 | 錯過即時留存 | 違反 #95 的目的 |

## Decision（決策）

### D-1 模組與型別

1. 新套件 `app/fundamentals/`：
   - `env.py`：只放兩個環境變數名稱常數，不 import 任何 `app.*`。
   - `models.py`：型別定義。
   - `items.py`：項目登記、各市場的項目清單、標籤白名單與對照規則，有版本。
   - `interface.py`：`FundamentalsProvider` ABC。
   - `store.py`：寫入端。
   - `reader.py`：唯讀端，F2 才做。
   - `sec_edgar.py`：SEC adapter。
   - `sync.py`：協調與 CLI。
   - `derive.py`：純函式，F2 才做。
2. 型別一律 pydantic `frozen`。時間全部 timezone-aware UTC；日期用 `date`。

   Literal 型別（F1 就要有）：
   - `Market`：沿用 `app.data.interface.Market`。
   - `Acquisition = Literal["live", "backfill"]`：即時留存／回補。
   - `PublishedOnBasis = Literal["source_reported", "statutory_deadline"]`：來源實際公布日，或以法定期限作為保守假設（台股月營收「次月 10 日」，FR-14）。
   - `FetchStatus = Literal["ok", "unchanged", "failed"]`。
   - `PeriodSpan = Literal["quarter", "ytd", "annual", "ttm", "month", "instant"]`。

   Literal 型別（定義在 F1，使用在 F2）：
   - `Nature = Literal["reported", "derived"]`：公司公布／依財報計算。
   - `MissingReason = Literal["company_not_reported", "source_unavailable", "not_applicable"]`：公司未提供／資料來源暫無／不適用（#94）。

   資料型別：
   - `FactRecord`（F1）：一筆快照列的讀回形式，欄位對應 D-2。
   - `DisplayValue`（F2）：`item`、`period`、`nature`、`value: Decimal | None`、`missing: MissingReason | None`、`unit`、`currency`、`scale`、`provenance`。
     - 不變式：`value` 與 `missing` 恰有一個不是 None；`value` 不是 None 時 `provenance` 必填。
   - `Provenance`（F2）：`source`、`filing_refs`、`concepts`、`fact_ids`、`published_on`、`published_on_basis`、`recorded_at`（取得時間）、`is_original`（衍生值的 `is_original` 為「全部組成項都是原始公布值」）。
3. 項目代碼（`items.py`）：
   - 美股第一版：`operating_cash_flow`、`capital_expenditure`、`free_cash_flow`、`dividends_paid`、`share_repurchase_paid`、`shareholder_distribution_total`、`revenue`、`net_income`、`diluted_earnings_per_share`、`latest_filing_date`。
   - 候選（待 Q3）：`stock_based_compensation`。
   - 台股特有：`monthly_revenue`。
   - 各市場的項目清單分開登記；沒登記在某市場的項目，在該市場**不產生任何值，也不產生缺值**（FR-14）。
   - **每股盈餘一律命名 `diluted_earnings_per_share`**；`app/fundamentals/` 內不得出現名為 `EPS`、`eps` 的識別字（`EPS` 已是 epsilon 常數，見 `forecast/band.py:6-8`、`dirdef/definition.py:8`）。
4. 衍生值與缺值都是**讀取時**的結果，不寫進快照（D-5）。

### D-2 儲存（獨立 DB，只新增不覆蓋）

1. 檔案：`STOCK_DESK_FUNDAMENTALS_DB_PATH`，預設 `./data/stock-desk-fundamentals.db`。變數名稱與預設路徑只出現在 `app/fundamentals/store.py` 與 tests 裡。WAL（`enable_wal`）、自己的 `busy_timeout`；不 import `app.data.cache`。
2. Schema（v1）：

   ```sql
   CREATE TABLE IF NOT EXISTS fundamental_fetch_runs (
       run_id INTEGER PRIMARY KEY AUTOINCREMENT,
       recorded_at TEXT NOT NULL,          -- store clock, UTC fixed width
       trigger TEXT NOT NULL CHECK (trigger IN ('scheduled', 'cli')),
       market TEXT NOT NULL CHECK (market IN ('TW', 'US')),
       symbol TEXT NOT NULL,
       issuer_ref TEXT,                    -- e.g. zero-padded CIK; NULL if mapping failed
       source TEXT NOT NULL,
       allowlist_version TEXT NOT NULL,
       status TEXT NOT NULL CHECK (status IN ('ok', 'unchanged', 'failed')),
       payload_sha256 TEXT,
       fact_count INTEGER NOT NULL,
       new_fact_count INTEGER NOT NULL,
       reason TEXT                         -- internal English diagnostic; never a URL or User-Agent
   );

   CREATE TABLE IF NOT EXISTS fundamental_facts (
       fact_id INTEGER PRIMARY KEY AUTOINCREMENT,
       fact_hash TEXT NOT NULL UNIQUE,
       first_run_id INTEGER NOT NULL,
       recorded_at TEXT NOT NULL,          -- copied from first run, store clock
       acquisition TEXT NOT NULL CHECK (acquisition IN ('live', 'backfill')),
       market TEXT NOT NULL CHECK (market IN ('TW', 'US')),
       symbol TEXT NOT NULL,               -- symbol at capture time
       issuer_ref TEXT NOT NULL,
       source TEXT NOT NULL,
       taxonomy TEXT NOT NULL,
       concept TEXT NOT NULL,              -- raw source concept name
       unit TEXT NOT NULL,                 -- raw unit, e.g. 'USD', 'USD/shares'
       currency TEXT,                      -- ISO 4217 derived from unit; NULL if non-monetary
       scale INTEGER NOT NULL DEFAULT 0,   -- amount = value * 10^scale
       value TEXT NOT NULL,                -- Decimal text exactly as published
       period_start TEXT,                  -- NULL for instant facts
       period_end TEXT NOT NULL,
       fiscal_year INTEGER,                -- source attribute only, never a key
       fiscal_period TEXT,                 -- source attribute only, never a key
       form TEXT,
       filing_ref TEXT NOT NULL,           -- filing identity (SEC accession)
       published_on TEXT NOT NULL,
       published_on_basis TEXT NOT NULL CHECK (published_on_basis IN ('source_reported', 'statutory_deadline')),
       frame TEXT
   );

   CREATE TABLE IF NOT EXISTS fundamental_filings_seen (    -- new-filing detection, PIT evidence
       obs_id INTEGER PRIMARY KEY AUTOINCREMENT,
       run_id INTEGER NOT NULL,
       recorded_at TEXT NOT NULL,
       market TEXT NOT NULL, issuer_ref TEXT NOT NULL, source TEXT NOT NULL,
       filing_ref TEXT NOT NULL, form TEXT, filing_date TEXT, accepted_at TEXT,
       UNIQUE (source, issuer_ref, filing_ref)
   );

   CREATE TABLE IF NOT EXISTS fundamental_issuer_observations (
       obs_id INTEGER PRIMARY KEY AUTOINCREMENT,
       run_id INTEGER NOT NULL,
       recorded_at TEXT NOT NULL,
       market TEXT NOT NULL, symbol TEXT NOT NULL, issuer_ref TEXT, source TEXT NOT NULL,
       content_hash TEXT NOT NULL,
       entity_name TEXT, sic_code TEXT, fiscal_year_end TEXT, entity_kind TEXT   -- availability: P-8, P-9
   );
   ```

   - 四張表都加 `BEFORE UPDATE`、`BEFORE DELETE` 的 `RAISE(ABORT, 'append-only')` trigger。
   - 寫入只用 `INSERT` 或 `INSERT ... ON CONFLICT(...) DO NOTHING`。
   - 禁止 `INSERT OR REPLACE`、`REPLACE`、`ON CONFLICT ... DO UPDATE`、`UPDATE`、`DELETE`。REPLACE 會刪掉舊列，而 SQLite 未開 `recursive_triggers` 時不會觸發 DELETE trigger，所以靠 trigger 擋不住。
   - `fundamental_issuer_observations` 只有在內容雜湊和該 issuer 最新一列不同時才新增。
3. **fact 身分**：`fact_hash` = SHA-256（canonical JSON），內容依序為 `market, issuer_ref, source, taxonomy, concept, unit, period_start, period_end, filing_ref, value`。
   - 同一 fact 重抓：不新增列。
   - 後續申報給同一期間的值（不論相同或不同）：因 `filing_ref` 不同而新增列。重編與比較期重報因此自然並存，舊列原值不變。
4. **期間身分是 `(period_start, period_end)`**。`fiscal_year`、`fiscal_period`、`form` 只是來源屬性，不得當鍵。〔推論：companyfacts 的 fy、fp 屬於「申報文件」而非該 fact 本身的期間，待 P-1 驗證〕
5. **即時留存或回補的判定**：在寫入交易內由 store 決定，不接受呼叫端傳入。
   - 令 `prev_ok` 為同一 `(market, issuer_ref, source)` 在本次之前最後一筆 `ok` 或 `unchanged` 的 `recorded_at`。
   - 沒有 `prev_ok`：本次新增的 fact 一律標 `backfill`。
   - 有 `prev_ok`：`published_on` ≥ `prev_ok` 換算到來源當地時區（SEC 為 America/New_York）的日期，標 `live`；否則標 `backfill`。
   - 這是保守的便利標籤。`recorded_at` 與 `published_on` 都保留，quant 可以自訂更嚴格的定義（Q-b）。
6. **交易紀律**：一次 issuer 寫入用一個 `BEGIN IMMEDIATE`（`isolation_level=None`），順序如下：
   1. 取得寫入鎖之後才讀時鐘；
   2. 讀 `prev_ok`；
   3. 寫入 run 列；
   4. 寫入 facts、申報清單、issuer 觀察；
   5. `COMMIT`。

   任一步失敗就整筆 ROLLBACK 並往外拋，不留半套。adapter 回報失敗時，另寫一筆 `failed` run，不寫 fact。
7. **遷移**：
   - 只允許 `CREATE TABLE IF NOT EXISTS`、`CREATE INDEX IF NOT EXISTS`、`CREATE TRIGGER IF NOT EXISTS`，以及 `add_missing_columns`（N-154）。新欄位只能 nullable 或常數預設。
   - 不得 DROP、RENAME 或重建表。
   - ADR-0026 D-6 生效後，以 component `fundamentals` 依其規則補版本紀錄與遷移前備份。
8. **讀取端**（F2 的 `reader.py`）：
   - 以 `PRAGMA query_only = ON` 開連線，不執行任何 DDL；表不存在就當作沒有資料。
   - backend 程序只讀；寫入者只有 scheduler 程序與 CLI。
9. 數值一律以 TEXT 存 Decimal 原文，讀回時轉 `Decimal`；拒絕 NaN、Infinity；不得用 REAL。

### D-3 備份

新 DB 檔的備份等級為「最高」，等同市場 DB，因為即時留存無法重建。F1 上線前，devops-sre 必須：
- 更新部署手冊第 4 節；
- 把這個檔列入備份程序；
- 在 `.env.example` 加 `STOCK_DESK_FUNDAMENTALS_DB_PATH` 的註解範例。

這個檔與主 DB、市場 DB 之間沒有互相引用，所以不受 ADR-0026 D-9 第 2-1 點的備份順序限制。

### D-4 取得與排程

1. **開頁不打外部**：API 與頁面只經 `reader.py` 讀本機。request path 的 import 圖不得到達 `app.data.http`、`app.fundamentals.sec_edgar`、`app.fundamentals.sync`。不提供「立即更新」之類在請求中觸發抓取的功能。
2. **排程 job `fundamentals_sync`**（在 `app/scheduler.py`）：
   - 每天兩個時點，Asia/Taipei 08:10 與 20:10。不分平日假日，因為抓取冪等而且量很小。
   - 時點的分鐘數不得與既有 job 重疊（:30、:45、:50，以及 data_refresh 的各點）。
   - 啟動時也跑一次，但受第 4 點的重查間隔限制。
   - `max_instances=1`、`coalesce=True`，外層用 `_guarded` 包住。
   - 標的由 scheduler 從 `get_position_store().list_all()` 取出 `market == "US"` 的代號去重後傳入；`app.fundamentals` 不讀持倉。
3. **CLI**：`python -m app.fundamentals.sync`（trigger 記為 `cli`），呼叫同一個函式。
4. **每次、每個 issuer 的請求預算**：
   - 距離上一次嘗試未滿重查間隔（預設 6 小時；`failed` 預設 1 小時），就跳過，不發請求、不寫列。
   - 否則最多 1 個申報清單請求，加上「有新申報（或從未抓過）時」最多 1 個 companyfacts 請求。
   - ticker→CIK 對照每天最多更新 1 次。
   - 回應雜湊等於上次 `ok` 時，記為 `unchanged`。
5. **HTTP**：用自己的 `RateLimitedClient` 實例；最小間隔常數不得高於 spike 查證出的上限的一半（P-5），查證前預設每秒 1 個請求；連線 timeout 與重試沿用 `app/data/http.py` 的預設。
6. **User-Agent**：
   - 只從 `STOCK_DESK_SEC_USER_AGENT` 讀取。未設定或只有空白時，**不發任何請求**，寫一筆 `failed` run，`reason='user_agent_unset'`。
   - 這個值不得出現在 log、`reason`、例外訊息、fixture 或任何 commit 中。
   - `env_status` 只顯示「已設定／未設定」；`.env.example` 只放空值。
7. **不消耗 Alpha Vantage 額度**：`app.fundamentals` 的 import 圖不得到達 `app.data.providers`、`app.data.quota`、`app.data.service`、`app.services`。第一版不取股價。
8. **失敗保留舊值**：本來就只新增不覆蓋，失敗只多一筆 `failed` run。讀取端回傳最後一份成功的資料、它的取得時間，以及最近一次嘗試的狀態（AC-11）。
9. **持倉移除或下市**：不再抓取，但既有快照不刪（AC-13）。沒有任何清理或保留期限機制。
10. **新鮮度與逾期**（F2）：讀取時用純函式判斷「已超過預期申報期限仍沒有新資料」；門檻參數由 quant 登記（Q-d）。

### D-5 缺值三分類與衍生值（F2 實作，規則現在定）

1. **缺值判定**由單一純函式 `classify_missing(...)` 負責：
   - 只有三點同時成立才判 `company_not_reported`：
     - (a) 該期的申報文件已成功收進快照（`fundamental_facts` 或 `fundamental_filings_seen` 有該 `filing_ref`）；
     - (b) 該項目在該 taxonomy 的對照規則標為 verified；
     - (c) 該申報文件沒有任何白名單標籤的 fact 對到該項目。
   - `not_applicable`：只依 `items.py` 版本化規則，搭配 `fundamental_issuer_observations`（P-8）判定；不得 import `app.leverage`。
   - 其餘一律 `source_unavailable`，包括判不出標的類型、幣別與市場對不上（`currency != MARKET_CURRENCY[market]`）、對照規則缺漏。
2. **衍生值**（`derive.py`，不讀 DB、不讀時鐘）：
   - 單季 = 本期 YTD − 前一期 YTD，兩者必須同一個 `period_start`；Q4 = 全年 − 9 個月 YTD。
   - TTM = 最近 4 個單季之和；FCF = OCF − CapEx；合計 = 股利 + 回購。
   - 任一組成項缺值，結果就是缺值；不補 0、不內插、不用 OCF 代替 FCF。
   - 衍生值的 `published_on` 取組成項中最晚的一個（預設，待 Q-c）。
   - 缺值分類的傳遞優先序：`source_unavailable` > `not_applicable` > `company_not_reported`（預設，待 Q-e）。
3. 衍生值不得寫回任何表。

### D-6 與 point-in-time 的關係

1. 兩條時間軸並存：
   - `published_on`：來源宣稱的公布日，申報文件層級。
   - `recorded_at`：本系統實際看到的時刻，store 時鐘。
2. 「我們何時知道」的視圖 = `recorded_at ≤ t`。「依公布日」的視圖 = `published_on ≤ t`；對 `backfill` 列使用時，須附偏誤標示（比照研究 DB 的 `backfill_non_pit`）。
3. `is_original`：讀取時判定。若該值所屬申報文件，是同一 `(concept, unit, period)` 已存 fact 中最早公布的一份，就是 true。能否從回補資料重建「首次公布值」，待 P-2。
4. 本 ADR 不核可任何把基本面用於篩選、排序、模型或訊號的用途。要用就須另立 ADR 並經 quant 的研究計畫（量化回應 2.4 (b)(c)）。

### D-7 模組邊界

1. **哪些模組可以 import `app.fundamentals`**（白名單）：
   - `app.fundamentals.*`
   - `app.scheduler`
   - `app.api.fundamentals`（F2）
   - `app.main`（F2，只為了 include router）
   - `app.env_status`（只能 import `app.fundamentals.env`）

   其餘每個 `app.*` 模組的可達集合都不得包含 `app.fundamentals`，特別包括 advice、signals、playbook、alerts、forecast、outlook、kelly、portfolio、sectors、services、backtest、leverage、`app.api.deps` 與其他 router。
2. **`app.fundamentals` 自己可以 import 什麼**（白名單）：
   - 標準函式庫、pydantic、httpx
   - `app.data.sqlite_util`、`app.data.http`
   - `app.data.interface`（只取 `Market`）
   - `app.positions.models`（只取 `MARKET_CURRENCY`）
3. F2 的 store 或 reader getter 放在 `app/api/fundamentals.py` 或 `app/fundamentals/` 內，**不得**放進 `app/api/deps.py`，因為它被所有 router 與 scheduler 共用。
4. `app/advice/context.py` 的 `FIELD_LABELS`、`KNOWN_FIELDS` 不新增任何財報欄位，以快照測試釘住。

### D-8 分期

- **F1 快照留存**（#95：spike 完成且本 ADR accepted 後開工，可以和出清包並行）：
  - 內容：`env`、`models`、`items`（美股白名單）、`interface`、`store`、`sec_edgar`、`sync`、CLI、scheduler job、守門測試、`env_status` 一行、部署手冊與備份（D-3）。
  - 沒有 API router、沒有前端改動、沒有使用者字面；CLI 只輸出筆數與狀態。
  - 建議拆成 F1a（store、models、守門測試）與 F1b（adapter、sync、CLI、job）。
- **F2 財務頁籤**（排在出清包 N-164/N-165/N-166 與 N-172a 上線之後）：
  - 內容：`derive`、`reader`、`app/api/fundamentals.py`、前端、風控字面、art-lead 排版、qa-e2e、risk-gate。
- **F3 台股**（台股 spike 之後）：adapter、月營收、`statutory_deadline` 公布日；必要時修訂本 ADR，或另立 ADR 取代。

### D-9 spike 前後的分界（待決，送核可前須逐條對照）

| 編號 | 待 spike 確認 | 影響 | 不成立時 |
|---|---|---|---|
| P-1 | companyfacts 每個 fact 帶 `filed`、`accn`、`form`、`start`、`end`、`fy`、`fp`、`frame`；`fy`、`fp` 屬於申報文件而非 fact 本身 | D-2 第 3、4 點的身分與期間鍵 | 缺 `accn` 或 `filed`：結構性問題，修訂本 ADR 才能開工 |
| P-2 | 是否保留舊申報（含比較期）的值 | `is_original`、回補資料能否重建首次公布值 | 回補只能標「最新值」，`is_original` 對回補列回 None |
| P-3 | 各項目的標籤白名單（含 CapEx、股利、回購、營收的替代標籤）與 verified 清單 | `items.py` v1 | 未 verified 的項目一律 `source_unavailable` |
| P-4 | ticker→CIK 對照來源；含類股代號（如 BRK.B）與 ETF 查不到的情形 | 對照失敗的處理 | 對照失敗寫 `failed` run，`issuer_ref` 為 NULL |
| P-5 | 現行流量限制與 User-Agent 格式 | D-4 第 5、6 點的常數 | 依查證值調整 |
| P-6 | 申報清單端點的欄位（申報日、受理時間、編號）；是否支援條件式請求；companyfacts 在申報後多久更新 | S2 是否可行、`fundamental_filings_seen` 欄位 | 退到 S3 |
| P-7 | 每個 issuer 的回應大小 | 是否另存壓縮後的原始回應（G3 作為補充） | 預設只存雜湊 |
| P-8 | SIC、實體類型能否取得；ETF 如何辨識 | `not_applicable` 的依據 | 判不出就 `source_unavailable` |
| P-9 | 會計年度結束日能否取得 | 會計年度標籤、逾期判斷 | 由期間起迄推算並標為推論 |
| P-10 | 台股來源、公布時間戳、月營收 | F3 | F3 不開工 |
| P-11 | 下次財報日有沒有可靠來源（D-14） | 不在本 ADR 範圍 | 不放 |
| P-12 | 持股中是否有以非美元申報、或 IFRS 的公司 | 幣別判定 | 走 `source_unavailable`（幣別不符） |

不需要 spike 的待決事項：
- Q-a（PRD Q8）顯示最新值或首次公布值：儲存兩者都支援，F2 前定。
- Q-b（Q9）回補資料能否視為 PIT：quant。
- Q-c（Q10）衍生值的公布日規則：quant。
- Q-d（Q13）逾期門檻：quant。
- Q-e 衍生值缺值分類的傳遞規則：PM 加 quant；字面交風控。

## Consequences（後果）

**好處**
- 快照可以在沒有 UI、沒有使用者字面的情況下先開始累積，「從第一天起」的證據不會再流失。
- 在檔案、import、字串三層，加上執行時，都與 advice 鏈隔離。「不進訊號」由測試保證，不靠承諾。
- 重編與比較期重報自然並存；對照規則改了不必重抓，也不必改寫舊列。
- 價格鏈、Alpha Vantage 額度、`price_bars_cache`、主 DB、市場 DB 都不受影響。

**代價與壞處**
- 要定期備份的 DB 多一個；漏備份就永久失去即時快照（以 D-3 處理）。
- 「即時留存」的判定以每天兩次查詢為準：一份申報從公布到被標成 `live`，最多可能差約半天到一天，而且這份落差就記在標籤裡〔推論〕。8-K 新聞稿早於 10-Q 的落差不在範圍內（Q17）。
- 標籤白名單沒涵蓋的標籤，等擴充之後才收進來，而且只能標成 `backfill`。
- 讀取時才套用對照規則與衍生計算，F2 的讀取邏輯比直接存成品複雜。
- scheduler 會帶著 CEO 的聯絡資訊，每天自動對 SEC 發請求。
- 台股要等 F3；本 ADR 的台股相關部分（月營收、`statutory_deadline`）只定了形狀，沒有實測。

**被本決策約束的事**：見下方附錄 A（C-x）、附錄 B（T-x）、附錄 C（VETO）。

## 待決

1. **CEO 核可本 ADR**：核可前須先完成 P-1～P-12 的 spike 對照修訂（見 D-9）；Q-a～Q-e 的口徑由 quant、PM 回覆（見 D-9 末段）。
2. **ADR-0025 的加註尚未處理**：本 ADR 寫明「部分取代 ADR-0025」，並要在 ADR-0025 狀態行加註本 ADR 編號。但本 ADR 目前仍是 proposed，**ADR-0025 現階段不得加註、不得修改**；要等 CEO 核可本 ADR 之後，才處理 ADR-0025 的加註（加註範圍以本檔「與既有 ADR 的關係」第一點為準）。

---

## 附錄 A：對實作的約束（C-1～C-32，逐條可檢查）

逐條轉錄自來源評估檔第五節後段。

| 編號 | 約束 | 對應測試 |
|---|---|---|
| C-1 | 新套件 `app/fundamentals/`，模組依 D-1 第 1 點；F1 不建 `reader.py`、`derive.py`、`app/api/fundamentals.py` | T-1 |
| C-2 | `app.fundamentals.*` 自己的 import 只在 D-7 第 2 點白名單內；不得 import `app.data.cache`、`app.positions.store`、`app.data.providers.*`、`app.data.quota`、`app.data.service`、`app.services.*`、`app.leverage.*`、`app.api.*` | T-2 |
| C-3 | 白名單之外的每個 `app.*` 模組，可達集合都不含 `app.fundamentals`；`app.env_status` 只能 import `app.fundamentals.env` | T-1 |
| C-4 | `STOCK_DESK_FUNDAMENTALS_DB_PATH`、預設路徑與 `fundamental_` 開頭的表名，只出現在 `app/fundamentals/` 與 tests；`STOCK_DESK_SEC_USER_AGENT` 只出現在 `app/fundamentals/env.py`、`app/env_status.py`、tests 與 `.env.example`（值為空） | T-3 |
| C-5 | 基本面 DB 只含 D-2 的四張表（以後的遷移另計）；主 DB、市場 DB、研究 DB 都不含 `fundamental_*` 表 | T-4 |
| C-6 | 四張表都有 append-only trigger；`app/fundamentals/` 的 SQL 字串不得含 `UPDATE`、`DELETE`、`REPLACE`、`DO UPDATE` | T-5 |
| C-7 | `recorded_at`、`acquisition`、`first_run_id` 由 store 在 `BEGIN IMMEDIATE` 之後自行決定；寫入方法的簽章不得有這些參數 | T-7、T-8 |
| C-8 | 遷移只能用 `IF NOT EXISTS` 的 DDL 與 `add_missing_columns`；不得 DROP、RENAME、重建表 | T-9 |
| C-9 | 數值一律存 TEXT Decimal 原文；不得用 REAL；拒絕非有限值 | T-15 |
| C-10 | 期間鍵是 `(period_start, period_end)`；`fiscal_year`、`fiscal_period` 不得出現在任何 `UNIQUE`、`GROUP BY` 或配對鍵中 | T-16 |
| C-11 | `fact_hash` 依 D-2 第 3 點的欄位與順序計算；同一 fact 重抓不新增列 | T-6 |
| C-12 | 每次嘗試恰好一筆 run（跳過時不寫）；`reason` 是英文診斷，不含 URL、User-Agent、回應原文 | T-10、T-11 |
| C-13 | job id 為 `fundamentals_sync`，時點依 D-4 第 2 點且分鐘數不與既有 job 重疊；`max_instances=1`、`coalesce`、`_guarded` | T-14 |
| C-14 | 請求預算與重查間隔依 D-4 第 4 點 | T-13 |
| C-15 | 只用自己的 `RateLimitedClient` 實例；只連 SEC 主機（清單常數，待 P-5、P-6）；最小間隔依 D-4 第 5 點 | T-12、T-13 |
| C-16 | User-Agent 未設定時零請求；值不出現在 log 與例外訊息；`env_status` 只輸出已設定／未設定 | T-11、T-24 |
| C-17 | 不碰 Alpha Vantage：import 圖檢查，加上執行後額度帳本不變 | T-12 |
| C-18 | （F2）request path 的可達集合不含 `app.data.http`、`app.fundamentals.sec_edgar`、`app.fundamentals.sync` | T-19 |
| C-19 | `MissingReason` 是封閉的三值 Literal；缺值不寫進任何表 | T-20 |
| C-20 | 缺值判定由單一純函式負責，依 D-5 第 1 點；預設 `source_unavailable` | T-20 |
| C-21 | 衍生值純函式化，不讀 DB、不讀時鐘、不寫回；缺值不補 0、不內插 | T-21 |
| C-22 | 各市場項目清單分開登記；未登記的項目不輸出值也不輸出缺值 | T-22 |
| C-23 | 每股盈餘命名為 `diluted_earnings_per_share`；`app/fundamentals/` 內不得有名為 `EPS`、`eps` 的識別字 | T-17 |
| C-24 | 沒有任何刪除或清理快照的程式路徑；持倉移除後只是停止抓取 | T-5、T-14 |
| C-25 | 幣別不符的列照存；讀取時判 `source_unavailable` | T-20 |
| C-26 | F1 上線前，部署手冊與備份程序已納入新 DB（等級最高），由 devops-sre 負責 | 審查清單 |
| C-27 | CLI 與 job 呼叫同一個函式，只差 trigger | T-14 |
| C-28 | F1 不新增 router、不改前端、不新增使用者字面；CLI 只輸出筆數與狀態 | 審查清單、T-1 |
| C-29 | `FIELD_LABELS`、`KNOWN_FIELDS` 不變 | T-18 |
| C-30 | `not_applicable` 不 import `app.leverage`；所需資訊只來自自己的 issuer 觀察，或由呼叫端注入 | T-2、T-20 |
| C-31 | 讀取端 `query_only`、不執行 DDL；表不存在就當作沒有資料 | T-19 |
| C-32 | （F2）API 回應順序不得以任何財務數值為鍵 | T-23 |

## 附錄 B：測試（T-1～T-26）

逐條轉錄自來源評估檔第五節後段。

| 編號 | 測試 | 期別 |
|---|---|---|
| T-1 | 掃描全部 `app.*`：白名單外的模組都不可達 `app.fundamentals`（含 `app.api.deps`）；附反向測試 | F1a |
| T-2 | `app/fundamentals/` 每個檔的 import 都在白名單內；附反向測試；新增檔案必須被掃到 | F1a |
| T-3 | 字串掃描（含 docstring）：DB 變數名、表名、User-Agent 變數名的出現位置；附反向測試 | F1a |
| T-4 | 各 store 初始化後，用 `sqlite_master` 斷言各檔的表集合 | F1a |
| T-5 | 對每張表做 UPDATE、DELETE 都觸發 abort；SQL 字串靜態掃描；附反向測試 | F1a |
| T-6 | 重編：同一期間、不同申報文件、不同值 → 兩列，舊列原值不變；同一 fact 重抓 → `new_fact_count=0` | F1a |
| T-7 | 首次抓取全部標 `backfill`；`published_on` ≥ `prev_ok` 標 `live`，< 標 `backfill`；寫入簽章沒有 `recorded_at`、`acquisition` | F1a |
| T-8 | 另一連線持有 `BEGIN IMMEDIATE` 時，寫入會等待；時鐘在鎖之後才讀；失敗時整筆 rollback | F1a |
| T-9 | 舊檔缺欄位時自動補上；兩個建構子同時遷移，不出現 duplicate column 錯誤（比照 `test_schema_migration_race.py`） | F1a |
| T-10 | adapter 失敗 → 一筆 `failed` run，fact 數不變 | F1b |
| T-11 | User-Agent 未設定 → mock transport 零請求、run 為 `failed`、`reason=user_agent_unset`；以哨兵值確認 caplog 與例外訊息都不含 User-Agent | F1b |
| T-12 | sync 前後 Alpha Vantage 額度帳本不變；transport 只收到 SEC 主機的請求 | F1b |
| T-13 | 每個 issuer 每次 ≤ 1 個清單請求 + ≤ 1 個 companyfacts 請求；重查間隔內零請求；以假時鐘驗最小間隔 | F1b |
| T-14 | job 註冊的 id、時點、旗標都正確，分鐘數不和既有 job 重疊；只抓 US 持倉；移除持倉後不再抓取、快照仍在；CLI 與 job 走同一個函式 | F1b |
| T-15 | Decimal TEXT 往返完全相同；NaN、Inf 被拒；schema 沒有 REAL | F1a |
| T-16 | 同一 fy、fp 但起迄不同的兩筆 fact 是不同期間；後續申報裡的比較期 fact 對到它自己的期間 | F1a |
| T-17 | `app/fundamentals/` 沒有 `EPS`、`eps` 識別字；附反向測試 | F1a |
| T-18 | `FIELD_LABELS` 等於釘住的集合 | F1a |
| T-19 | （F2）router 可達集合檢查；用一個任何請求都 raise 的 transport，TestClient 仍回 200 並給出本機資料 | F2 |
| T-20 | （F2）`classify_missing` 真值表：三條件、幣別不符、判不出類型、未 verified | F2 |
| T-21 | （F2）單季相減、Q4 = 全年 − 9 個月；組成項缺值 → 缺值（不是 0）；公布日取最晚；讀取後表的列數不變 | F2 |
| T-22 | （F2）美股輸出永遠不含 `monthly_revenue` | F2 |
| T-23 | （F2）FCF 高低排列不同的兩組資料，輸出順序相同 | F2 |
| T-24 | `env_status` 只顯示 SEC User-Agent 的已設定／未設定 | F1b |
| T-25 | fixture 取自 spike 的真實公開 SEC 回應片段，契約測試依 `data-source-integration` 的要求 | F1b |
| T-26 | （F2）取得失敗後，讀取端仍回傳舊值、舊的取得時間與最近一次失敗狀態（AC-11） | F2 |

## 附錄 C：VETO（出現任一項，tech-architect 會否決）

逐條轉錄自來源評估檔第五節後段。

- VETO-1 把基本面放進 `price_bars_cache`，或擴充 `PriceBar`、`ProviderResult`、`MarketDataProvider`、`DataStatus`。
- VETO-2 快照表有任何 UPDATE、DELETE、REPLACE、upsert 路徑，或照 `dividend_events` 的 upsert 寫法實作。
- VETO-3 advice、signals、playbook、alerts、forecast、outlook、kelly、portfolio、sectors、services、backtest、`app.api.deps` 任一個可達 `app.fundamentals`；或 `FIELD_LABELS` 新增財報欄位。
- VETO-4 開頁或 API 請求過程中對外抓取；或提供在請求中觸發抓取的「立即更新」。
- VETO-5 使用 Alpha Vantage（含它的財報端點）或任何付費來源。
- VETO-6 User-Agent 或聯絡資訊寫進程式碼、compose、`.env.example`（非空值）、log、fixture、commit。
- VETO-7 把衍生值寫進快照；把缺值存成 0；內插；用 OCF 代替 FCF。
- VETO-8 `recorded_at` 或 `acquisition` 可由呼叫端指定。
- VETO-9 每股盈餘使用 `EPS`、`eps` 命名。
- VETO-10 用 fy、fp 當期間鍵。
- VETO-11 台股 spike 完成前寫台股 adapter。
- VETO-12 F1 夾帶 router、前端或使用者字面，或 F2 早於出清包與 N-172a 上線。

## 附錄 D：參考檔案（絕對路徑）

逐條轉錄自來源評估檔第五節末段。

- `/home/user/AICompany/work/prd/2026-11-01-財務頁籤-N179.md`
- `/home/user/AICompany/work/dispatch/2026-10-17-決策包二補遺-新增CEO事項.md`（#90～#96，第 112～120 行）
- `/home/user/AICompany/docs/adr/0025-stock-desk-產品定位改為提供投資建議.md`（D-9 第 453～472 行、D-12 第 501 行）
- `/home/user/AICompany/docs/adr/0001-record-architecture-decisions.md`
- `/home/user/AICompany/docs/adr/0005-stock-desk-指數來源與美股額度管理.md`（狀態行部分取代的先例）
- `/home/user/AICompany/apps/stock-desk/backend/app/data/interface.py`
- `/home/user/AICompany/apps/stock-desk/backend/app/data/sqlite_util.py`
- `/home/user/AICompany/apps/stock-desk/backend/app/data/market_panel.py`
- `/home/user/AICompany/apps/stock-desk/backend/app/dividends/store.py`
- `/home/user/AICompany/apps/stock-desk/backend/app/scheduler.py`
- `/home/user/AICompany/apps/stock-desk/backend/app/env_status.py`
- `/home/user/AICompany/apps/stock-desk/backend/app/advice/context.py`
- `/home/user/AICompany/apps/stock-desk/backend/tests/import_graph.py`
- `/home/user/AICompany/apps/stock-desk/backend/tests/test_research_isolation.py`
- `/home/user/AICompany/apps/stock-desk/docs/族群動能-主機部署手冊.md`（第 4 節 備份）

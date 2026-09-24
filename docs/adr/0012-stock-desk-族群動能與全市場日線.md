# ADR-0012：stock-desk 族群動能排行與全市場日線

- 狀態：proposed
- 日期：2026-09-24
- 決策者：tech-architect（草案）；待 CEO 核可
- 適用範圍：僅 `product/stock-desk` 產品線（本 ADR 不存在於 main）
- 相依：
  - ADR-0002：SQLite WAL、單機、「所有市場資料存取走抽象介面」。本 ADR D-3 對後者做擴充解讀，見 §7。
  - ADR-0005：指數路徑恆標 `backup`。
  - ADR-0009：交易日新鮮度。
  - ADR-0010：單一請求 IO 預算。
  - skill `backtest-protocol`、skill `data-source-integration`。
- 輸入：
  - `work/stock-desk-族群動能-PRD.md`（第三版，已併入風控第二次裁定 R-A～R-C）
  - `work/stock-desk-族群動能-資料評估.md`（data-engineer）
  - `work/stock-desk-族群動能-方法論.md`（quant-researcher，v1 草案第三版）
  - `work/stock-desk-族群動能-派工單.md` §4（風控預審：APPROVE_WITH_CONDITIONS；成分股技術面分數 VETO）
  - `work/stock-desk-族群動能-派工單.md` §5（風控第二次裁定：三態 `gate_status`、第一階段不列歷史比例、主視圖 q_net、成交金額倍數）
- 修訂：
  - v1（2026-09-24）：初稿，當時上述輸入都還沒有。
  - v3（2026-09-24）：併入 PRD、資料評估、方法論第二版與風控預審。移除成分股分數；新增覆蓋率、市場範圍標記、point-in-time 缺口機制、多資產籃子回測器；全市場日線改放獨立 SQLite 檔。
  - v4（2026-09-24）：併入風控第二次裁定（派工單 §5）、方法論第三版、PRD 第三版。
    - 刪除 `wording_tier`，改為三態 `gate_status` 加 `not_evaluated_reason`（NE-1～NE-8）；`not_evaluated` 時所有統計欄位回 null，回應不出現任何比例數字。
    - D9 費率未查證即 `not_evaluated`（NE-3，屬 G0 前提）。
    - 主視圖 q 定為 q_net；判定用 p_net 對 max(q_gross, 50%) 加 5pp，顯著水準 α/m。
    - `method_version = sector-rel-v1.0-L5-H5`；回看窗 L 與持有期 H 拆成兩個參數；m 持久化於 `sector_method_registry`。
    - 成交金額倍數改名 `turnover_value_ratio_5_20`，只放「詳細」，不入排名。
    - 前瞻 PIT 快照：D0 起逐日保存上市名單、產業分類、`TWT48U_ALL`、日線，每筆帶 `recorded_at`，只增不刪、不回填。
    - 回看窗除權息固定採排除（方法論 §2.4 選項 2）。
    - 刪除「書面接受分類 look-ahead 即放行」例外的所有痕跡；`backfill_non_pit` 只存研究 DB，API 不得讀取；新增 D-14 與 T-10 偏誤版研究隔離。
    - 預期時程統一為約 3.1 年（理由見 D-12）。
    - dev-lead「v3 殘留差異」註記結案。

## Context（背景）

CEO 在 2026-09-24 裁定開第一階段：首頁新增「族群動能排行」卡，只呈現近 L 日的相對強弱，不做「預測會漲」。第一階段只用日線。

風控兩次裁定（派工單 §4、§5）的要點：
- 否決成分股的技術面分數。
- **第一階段主視圖與「詳細」都不列任何歷史比例數字**，因為存活者偏差、分類 look-ahead、除權息無歷史來源這三項的影響幅度無法估計。
- `gate_status` 分三態：`passed`／`failed`／`not_evaluated`。`not_evaluated` 時不得出現比例數字，也不得用「未達門檻」句；D9 費率未查證時只能是 `not_evaluated`。
- 轉態的主路徑是前瞻累積：ETL 上線日 D0 起，逐日保存 PIT 上市名單、產業分類、除權息公告。
- 偏誤版回測只能作內部研究，並標示「含已知偏誤，不得上畫面」。
- 主視圖呈現 p_net 對 q_net；判定用 p_net 對 max(q_gross, 50%) 加 5pp；p_net 與 q_gross 並排 VETO。
- 「均量」VETO，改為成交金額倍數，只放「詳細」、不入排名。
- 覆蓋率門檻（族群 ≥ 90%、整體 ≥ 98%）已核可（R-E）。

方法論第三版的定案內容：
- 排名只用單一變數 `R_g(t,L) − R_EW(t,L)`。`method_version = sector-rel-v1.0-L5-H5`；L 只能是 5 或 20，與 H 不連動，由版本靜態決定。
- 回看窗內遇到除權息日的成分股排除；標籤用前瞻保存的除權息事件做乘法還原。
- 時序：t 收盤出排行 → t+1 開盤進 → t+H 收盤出，樣本不重疊。
- 三態：NE-1～NE-8 任一成立為 `not_evaluated`；否則 G1～G6 全過為 `passed`、任一不過為 `failed`；顯著水準 α/m。

既有程式的限制：
- 既有資料鏈只抓持倉（`scheduler.refresh_market_data` 註解明寫 “not to crawl a universe”）。
- `MarketDataProvider` 的形狀是「單一序列、一段區間」。
- `PriceBarCache.put()` 是最後寫入者勝出，不看來源；混源會觸發 ADR-0009 D-7 的揭露句。
- `market_trading_days()` 在每一次 `/api/advice` 都會被呼叫。
- `run_backtest` 只能回測單一資產。
- `app/signals` 明文不出 score。
- `SecurityDirectoryStore._connect` 沒有設 `busy_timeout`。

資料評估確認的外部事實（本環境不能連外；標「未驗證」者待 CEO 本機查證）：
- **全市場端點**：
  - `STOCK_DAY_ALL` 只給**當日**上市快照，約 1,379 筆，含開高低收、量、成交金額、`Change`。已有 fixture，CEO 實測 PASS。
  - TPEx mainboard 同樣只給當日，而且混了大量非普通股。
  - 可指定歷史日期的全市場端點（`MI_INDEX` 等）未驗證。
- **歷史回補**：唯一已驗證、效率又可行的路徑是 FinMind `TaiwanStockPrice` 逐檔抓，一檔一次請求拿整段；額度未驗證。
- **產業分類**：上市只有 `t187ap03_L` 的**當下快照**，`apply_sectors` 只做 UPDATE、不留歷史；上櫃沒有任何來源。
- **存活者偏差**：所有候選來源只列目前掛牌的股票，已下市名單沒有來源。
- **除權息**：沒有歷史還原因子。`TWT48U_ALL` 只有未來預告，而且只涵蓋上市。
- **成本費率**：未查證，`CostModel.verified_on=None`。

## Options（選項比較）

### A. 模組邊界

| 方案 | 優點 | 缺點 | 風險 |
| --- | --- | --- | --- |
| **A1 新 package `app/sectors/`（純計算加自有 store）；籃子引擎放 `app/backtest/basket.py`；評估放 `app/backtest/sector_eval.py`；編排放 `app/services/sector_board.py`（採用）** | 排名有獨立的位置；讀未來資料的碼和線上碼分屬不同 package，可以用 import-graph 硬性隔離 | 要多寫一組邊界測試 | 低 |
| A2 併入 `app/signals` | 少一個 package | `signals` 明文不出 score，而且它被 advice、alerts 廣泛依賴 | 排名可能流進建議卡，否決 |
| A3 併入 `app/advice` | 無 | 風控 §4.1-d 禁止首頁卡出現規則引擎輸出；也會把 ADR-0010 的 IO 預算帶進首頁 | 否決 |
| A4 全部放進 `app/backtest` | 線上和回測天然共碼 | 線上路徑和計算 forward return 的碼同在一個 package | 否決 |

### B. 全市場日線的儲存

| 方案 | 優點 | 缺點 | 風險 |
| --- | --- | --- | --- |
| B1 共用 `price_bars_cache` | 只有一張價格表 | 最後寫入者勝出會污染持倉列並觸發混源揭露；扭曲 ADR-0009 的 coverage 語意；`market_trading_days` 的掃描量暴增（資料評估 §6 也同意） | 否決 |
| B2 新表放在同一個 SQLite 檔（v1 的決定） | 不多一個檔案 | 大量只增不刪的快照列會和使用者資料共用備份與 WAL；回補期間和持倉查詢搶同一把寫鎖（資料評估 §6-2） | v3 推翻 |
| **B3 新表放獨立 SQLite 檔 `STOCK_DESK_MARKET_DB_PATH`，預設 `./data/stock-desk-market.db`（採用）** | 寫鎖隔離；只增不刪的 PIT 快照集中在一個檔，紀律好守；主 DB 維持小 | 多管一個檔；API 讀取要開兩個連線。**v4 更正：PIT 快照的 `recorded_at`、上市名單、分類都無法事後重建，此檔遺失等於前瞻累積歸零，必須備份** | 中；列為最高備份等級，寫進 devops 手冊 |
| B4 DuckDB／Parquet | 分析快 | 偏離 ADR-0002 | 否決 |

表名採 `market_daily_bars`，不用資料評估建議的 `sector_universe_daily_bars`。理由有兩個：
- 這張表存的是市場日線這個資料事實，裡面包含 B_EW 要用、但不參與族群排名的「其他業」股票，母體和族群母體不一樣。
- 以消費功能命名，日後其他用途（例如持倉資料鏈改從這張表取價，須另立 ADR）會出現語意錯置。

擷取紀錄表為 `pit_snapshot_runs`（v4 取代 v3 的 `market_ingest_log`），吸收資料評估 §8.1 提的 `status`、`row_count`／`expected_count`，並涵蓋上市名單、分類、除權息三種快照（D-2）。

### C. 計算時點

| 方案 | 優點 | 缺點 | 風險 |
| --- | --- | --- | --- |
| **C1 盤後批次預先算好落表，首頁只讀（採用）** | 請求零 HTTP、SQL 條數固定，滿足 PRD FR-8「P95 ≤ 2 秒」；所有結果出自同一個 `method_version` | 排程沒跑就是舊資料，由常駐揭露處理；統計超過 20 個交易日未重算即為 NE-4 | 冷啟動時整卡回 `insufficient_data` |
| C2 請求時即時計算 | 無 | 統計要整段歷史加上 1 萬次 bootstrap，請求內算不完；最後還是得落表，等於 C1 再加上兩邊不一致的風險 | 否決 |
| C3 批次加上程序內 memo | 無 | API 和 scheduler 兩個程序各持一份 | 不需要 |

### D. 回測與線上的關係

| 方案 | 優點 | 缺點 | 風險 |
| --- | --- | --- | --- |
| **D1 同一段純函式，以 `PointInTimePanel` 守門；線上只算最新一日，評估器逐日呼叫（採用）** | 同時滿足方法論 T9 和風控 §4.3-f | 逐日回放較慢，約 2,600 日，粗估數十秒內 | 低 |
| D2 線上和回測各寫一套 | 無 | 兩套必然漂移 | 否決 |
| D3 評估器另寫向量化版本 | 快 | 需要額外的 T2 一致性測試 | v1 不採用；日後要引入，T2 必須同批落地 |

### E. 新依賴

| 方案 | 優點 | 缺點 | 風險 |
| --- | --- | --- | --- |
| **E1 不新增（採用）**：用 pandas、numpy（block bootstrap、置換檢定）、`CronTrigger`、stdlib；既有 `wilson_interval`、`walk_forward_splits`、`CostModel`、`PerformanceMetrics` 都能直接用 | 供應鏈零變動 | 檢定要自己寫 | 低 |
| E2 scipy／statsmodels | 功能齊全 | 多一個依賴 | 真有需要時另立案 |

### F. 成分股列示

| 方案 | 優點 | 缺點 | 風險 |
| --- | --- | --- | --- |
| **F1 用成分股自己的近 5 日還原漲跌幅（和 S_A 同一個變數）；取最大 2 檔加最小 1 檔；同分依代碼（採用）** | 風控條件式核可；能呈現族群內部的離散程度 | 排在最前面的必然是已經漲最多的（方法論 §7.2 已揭露） | 低 |
| F2 技術面分數 | 無 | 風控 VETO | 否決；要做須依 §4.1-g 另立任務 |
| F3 規則引擎輸出 | 無 | 風控 §4.1-d 禁止 | 否決 |

### G. 多資產籃子回測器

| 方案 | 優點 | 缺點 | 風險 |
| --- | --- | --- | --- |
| **G1 新的通用引擎 `app/backtest/basket.py`：不認識「族群」，只接受「決策日 → 目標籃子」的策略（採用）** | 可重用；和 `run_backtest` 同構，策略只拿得到 ≤ t 的切片 | 多一個引擎要維護 | 低 |
| G2 把 `run_backtest` 擴充成多資產 | 只有一個引擎 | 要改動既有單資產引擎與它的 golden 測試；兩者的成交時序不同 | 否決 |
| G3 直接寫在 `sector_eval.py` 裡 | 檔案最少 | 引擎和族群定義耦合 | 否決 |

### H. 偏誤版研究的隔離

| 方案 | 優點 | 缺點 | 風險 |
| --- | --- | --- | --- |
| H1 與判定統計放同一張表，以欄位區分 | 簡單 | 只靠一個 WHERE 條件把關，任何一處漏寫就會外洩到 API | 否決 |
| **H2 獨立 package `app/research/sector_biased/`＋獨立 DB 檔 `STOCK_DESK_RESEARCH_DB_PATH`＋hindsight 視圖工廠只在研究 package 內＋repository 拒收（採用）** | import 層、檔案層、型別層、執行期四層防線 | 多一個 package 與一個檔 | 低 |

## Decision（決策）

- **D-1 套件配置與依賴方向**

  ```
  app/data/panel.py               # MarketPanel / PointInTimePanel (pure, pandas, no I/O)
  app/data/market_panel.py        # PIT snapshot store (market DB, append-only): runs, bars, listing, classification, dividend announcements
  app/data/providers/twse_snapshot.py   # MarketSnapshotProvider over STOCK_DAY_ALL
  app/services/pit_snapshot.py    # daily capture of the four snapshot kinds + pre-D0 warm-up backfill CLI (network)
  app/sectors/                    # pure core + own store (main DB)
      definition.py  models.py  universe.py  index.py  ranking.py
      constituents.py  coverage.py  gate.py  store.py
  app/backtest/basket.py          # generic point-in-time multi-asset basket engine
  app/backtest/sector_eval.py     # labels, stats, NE/G checks on forward_pit only; the ONLY place forward returns exist
  app/research/sector_biased/     # biased hindsight research; own DB; never reachable from the API
  app/services/sector_board.py    # orchestration + CLI (approve, register-version)
  app/api/sectors.py              # read-only router
  ```

  依賴方向：
  - `api.sectors` → `{sectors 純核心, sectors.store, data.market_panel（唯讀）, positions.store（只讀持有旗標）}`
  - `services.pit_snapshot` → `{data.market_panel, data.providers.*, directory.providers, dividends.providers}`
  - `services.sector_board` → `{data.market_panel, sectors.*, backtest.sector_eval}`
  - `backtest.sector_eval` → `{sectors 純核心, backtest.basket, costs, splits, episodes, report, event_study}`
  - `backtest.basket` → `{data.panel, costs, report}`
  - `research.sector_biased` → `{sectors 純核心, backtest.*, data.panel, data.market_panel（唯讀）}`
  - `sectors 純核心` → `{data.panel, data.interface, data.calendar, positions.sectors}`

  禁止事項：
  - **`app.sectors` 不得 import `app.advice`、`app.signals`、`app.backtest`、`app.directory`、`app.research`。**
  - `app.backtest.basket` 不得 import `app.sectors`。
  - 除 `app.research` 自身外，任何 `app.*` 模組都不得 import `app.research`。

- **D-2 全市場日線與前瞻 PIT 快照（市場 DB，只增不刪）**
  - 市場 DB 內的表：
    - `pit_snapshot_runs`：每次擷取寫一列。
      - 欄位：`run_id`（PK）、`kind` ∈ {`bars`, `listing`, `classification`, `dividend_announce`}、`session_date`、`recorded_at`、`source`、`status` ∈ {`ok`, `partial`, `failed`, `quality_failed`}、`row_count`、`expected_count`、`content_hash`、`reason`。
      - 取代 v3 的擷取紀錄表。
    - `market_daily_bars`：
      - 主鍵 `(run_id, symbol)`，`WITHOUT ROWID`；次索引 `(session_date, symbol)`、`(symbol, session_date)`。
      - 欄位：`session_date`、`market`、`exchange`、開高低收（Decimal 字串）、`shares`（成交股數）、`traded_value`（成交金額，元）、`change`（可為 NULL）、`source`。
    - `pit_listing_rows`、`pit_classification_rows`、`pit_dividend_announce_rows`：
      - 以 `(content_hash, key)` 為主鍵的內容定址表，內容相同時跨日只存一份；每日的 run 以 `content_hash` 指向它。
      - 分類列帶 `sector_code`、`sector_name`；除權息列保存 `TWT48U_ALL` 的全部原始欄位。
  - **只增不刪**：所有表只允許 INSERT；要更正就寫一個新的 run。store 不提供 UPDATE／DELETE 方法，並以 SQLite trigger 擋下。
  - **`recorded_at` 由 store 以自身時鐘填入**，呼叫端不得傳入。
  - **不回填**：`session_date` 只能是資料能自證的交易日（見 D-3）。事後才取得的資料寫成新的 run，`recorded_at` 就是實際取得的時間，對當時的決策不可見。
  - **判定端的可見性**：第 t 日的決策只讀 `recorded_at ≤ cutoff(t)` 的 run；`cutoff(t)` 是 t 當地 23:59:59（Asia/Taipei）。標籤屬結果端，可以讀之後才寫入的 run。
  - **缺日沿用**：某個 kind 在第 t 日沒有 `ok` run 時，沿用最近一份可見的 run，視圖標記 `carried_forward=true`。任一 kind 連續超過 5 個交易日沒有新的 `ok` run，受影響的樣本視為無效，不計入 N，並記入執行紀錄。
  - bars run 要標 `ok`，覆蓋率 `row_count / expected_count` 必須 ≥ 0.98；`expected_count` 取當日可見上市名單中應有交易的檔數。
  - 主來源優先：同一 `session_date` 有多個 `ok` 的 bars run 時，讀取端先取 `twse_snapshot`，其次 `finmind`；不覆寫任何列。
  - 全市場資料不寫也不讀 `price_bars_cache` 及它的兩張 log 表。

- **D-3 provider 介面與資料來源**
  - 在 `app/data/interface.py` 新增 `MarketSnapshotProvider.get_latest_snapshot() -> SnapshotResult`。這個方法沒有日期參數，因為 `STOCK_DAY_ALL` 本身就只給當日。
  - **交易日由資料自證（DE-1'）**：
    - payload 帶交易日時，以 payload 為準。
    - payload 不帶交易日時，不得用時鐘推定。改用 FinMind 逐檔抽 3 檔（固定清單加隨機抽樣，seed 要記錄），比對 `expected_session` 那天的收盤價與成交量；完全相符才認定快照屬於該日，否則記 `failed`。
  - 上市名單取自 `STOCK_DAY_ALL` 當日代號集合與 `t187ap03_L` 的交集（正向篩選）；分類取自 `t187ap03_L`；除權息取自 `TWT48U_ALL`。三者都是每日全量。
  - 暖身回補只走 CLI：`python -m app.services.pit_snapshot --warmup --since YYYY-MM-DD`。
    - 用 FinMind 逐檔抓 D0 前至少 80 個交易日的日線（上市天數 60 加流動性 20 日窗）。以 symbol 為最小重試單位，一檔一個 transaction，checkpoint 記在 `market_backfill_progress`。
    - 寫成 `kind='bars'`、`source='finmind_warmup'` 的 run，`recorded_at` 必須早於 D0。**暖身必須在 D0 前完成**；D0 之後 CLI 拒絕執行暖身。
    - 節流沿用現有下限：FinMind 0.3 秒、TWSE 0.5 秒。
    - D0 之後漏抓的日子**不補**（不回填原則），該日依 D-2 沿用前一份。
    - 更長的歷史只能由 `app/research/sector_biased/` 抓取並寫入研究 DB（D-14）。
    - **scheduler 不觸發暖身、補洞或研究。**
  - `MI_INDEX` 如果經 CEO 本機查證可用，另外修訂本 ADR 把它納入。
  - TPEx 第一階段不抓。

- **D-4 報酬與除權息（依方法論第三版 §2.4，已定案）**
  - 報酬函式只有一處，在 `index.py`。算法是期初等權、期間持有：`R_g(t,L) = mean_{i∈C_g(t,L)} (P_i(t)/P_i(t−L) − 1)`。C_g(t,L) 指第 t 日合格、(t−L, t] 內沒有除權息日、而且價格完整的成分股。
  - **回看窗（用於排行）**：成分股在 (t−L, t] 內有除權息日時，該窗排除這一檔，並計入 `ex_date_excluded_count`。判斷依據是 `recorded_at ≤ cutoff(t)` 的 `TWT48U_ALL`。`TWT48U_ALL` 的 `ok` run 沒涵蓋最近 L 個交易日時，整卡回 `insufficient_data`。
  - **標籤（只在 `sector_eval`）**：用前瞻保存的除權息公告，加上除權息日當天快照的參考價（`close − change`），算出乘法還原因子。`change` 是否以除權息參考價為基準，待 DE-5 查證；查證前標籤因子不可用，判定端為 NE-1。
  - v3 的 `reference_chain` 不用於排行，只保留為上述標籤因子的算法來源。
  - 保險：成分股在窗內單日報酬超過漲跌幅上限加容差時，排除該窗並記錄。

- **D-5 計算時點：盤後批次**
  - scheduler 新增兩個 job，都用 `CronTrigger`、時區 Asia/Taipei、只在平日跑、`max_instances=1`、`coalesce=True`，啟動時各補跑一次：
    - `pit_snapshot_capture`：17:30、19:30、21:30 各跑一次。四種 kind 各自獨立成敗，當日已 `ok` 的 kind 就跳過。分類只抓 `TwseSectorProfileAdapter` 並做 resolve，**不跑**會寫入 positions 的完整目錄同步。
    - `sector_board_refresh`：只在當日 bars run 為 `ok` 時才計算。
  - `sector_board_refresh` 的流程：
    1. 寫入當日的 `sector_board`、`sector_board_members`、`sector_board_excluded`。
    2. 每新完成一個不重疊的 H 日樣本，就呼叫 `sector_eval`，在 `forward_pit` 資料上重算統計與 NE／G 判定；`sector_rank_stats`、`sector_gate_checks` 只新增、不修改。
  - 評估失敗不影響 board 本身。超過 20 個交易日未重算時，API 讀取端判定為 NE-4（`stale_recompute`）。

- **D-6 共用計算碼、參數、版本鎖定、look-ahead 守門**
  - `definition.py` 是唯一定義處，v1 凍結值以方法論第三版 §11.1 為準：

    ```python
    @dataclass(frozen=True)
    class SectorMomentumDefinition:
        method_version: str               # "sector-rel-v1.0-L5-H5"; must encode lookback/holding exactly
        lookback_days: Literal[5, 20]     # L; static per version; drives all five screen spots
        holding_days: int                 # H; independent of L; re-rank interval == H (non-overlapping)
        market_scope: Literal["twse_only"]
        ranking_signal: Literal["rel_return_L"]       # C1, single variable
        benchmark: Literal["equal_weight_market"]     # B_EW, never charged cost
        ex_dividend_lookback: Literal["exclude_window"]
        label_adjustment: Literal["pit_multiplicative_factor"]
        constituent_rule: Literal["top2_bottom1"]
        universe: UniverseRules           # listing age 60, liquidity median NT$10m & >=18 of 20 days, codes 20/91
        coverage: CoverageRules           # members >= 5, sector >= 0.90, overall >= 0.98 (risk R-E approved)
        gate: GateRules                   # N >= 150, N_eff >= 60, b = max(q_gross, 0.5), effect 5pp, alpha/m
        open_limit_up_factor: float       # 1.095
    ```

  - 建構時驗證：`method_version` 字串中的 `L{n}`、`H{n}` 必須分別等於 `lookback_days`、`holding_days`；L 只能是 5 或 20。
  - **不得依任何統計結果在執行期間切換 L 或 H。** 要切換就是開新版本，依方法論 §11.2：凍結 → m 加 1 → 送風控限縮複審 → 告知 CEO。
  - **判定用 α/m**：Wilson 與 bootstrap 區間的信賴水準為 1 − 0.05/m；置換檢定門檻為 0.05/m。
  - **m 的持久化**：存在主 DB 表 `sector_method_registry`，只增不刪。
    - 欄位：`method_version, lookback_days, holding_days, frozen_commit, registered_at, accumulation_start, first_forward_eval_at, counts_toward_m`。
    - 某版本第一次在 `forward_pit` 資料上算統計時，寫入 `first_forward_eval_at` 並設 `counts_toward_m=1`。看過偏誤研究後才提出的版本，同樣設 `counts_toward_m=1`。
    - m = `counts_toward_m=1` 的版本數；每列統計記錄 `m_at_evaluation`。
    - 程式判定以此表為準；`work/stock-desk-族群動能-回測紀錄.md` 是給人看的紀錄。
  - 線上與評估器共用 `universe.eligible`、`index.member_returns`、`ranking.rank_sectors`、`constituents.list_constituents`、`coverage.assess`，這些函式只接受 `PointInTimePanel`。
  - `PointInTimePanel` 帶 `regime` ∈ {`pit`, `hindsight`}。`MarketPanel.as_of(t)` 只產生 `pit`：只含 `session_date ≤ t` 且 `recorded_at ≤ cutoff(t)` 的列，存取範圍外的列直接拋錯。`hindsight` 視圖只能由研究 package 建立（D-14）。
  - 分類與上市名單套用同一套可見性規則：第 t 日的族群歸屬 = `recorded_at ≤ cutoff(t)` 的最新分類快照。
  - forward return、標籤、成本扣除只存在於 `basket.py` 與 `sector_eval.py`。

- **D-7 成分股**
  - 取族群內合格且有資料的成分股，依 `(−return_L, symbol)` 排序，取位置 `[0, 1, −1]`；成分股不超過 3 檔時全列。
  - 缺資料的成分股計入 `missing_count`。
  - 不產生、不儲存任何分數，不附歷史比例，不帶任何規則引擎輸出。
  - `held`（是否持有）由 API 在讀取時查 positions 表得出。

- **D-8 三態判定（依方法論第三版 §6.3）**
  - 令 `b = max(q_gross, 0.5)`。
  - **G0（前提）= NE-1～NE-8 全不成立。** 任一成立即 `not_evaluated`。D9 費率未查證（`CostModel.verified_on is None`）屬於 G0，即 NE-3。

    | # | 條件 | `not_evaluated_reason` | 判定位置 |
    | --- | --- | --- | --- |
    | NE-1 | 判定資料不是 PIT：母體缺當時已下市個股、分類不是當時分類、除權息沒有當時的紀錄，三者任一 | `pit_history_missing` | `sector_eval` |
    | NE-2 | 前瞻有效樣本 N < 150，或 N_eff < 60 | `accumulating` | `sector_eval` |
    | NE-3 | D9 費率未查證（`verified_on` 為 null） | `fee_unverified` | `gate.py`（讀取時） |
    | NE-4 | 距上次重算超過 20 個交易日 | `stale_recompute` | `gate.py`（讀取時） |
    | NE-5 | board 與統計的 `method_version` 不一致 | `version_mismatch` | `gate.py`（讀取時） |
    | NE-6 | 資料品質檢查未過（未來日期、重複、覆蓋率） | `data_quality` | `sector_eval` |
    | NE-7 | look-ahead 與偏誤自檢未全過 | `lookahead_tests_failed` | `sector_eval` |
    | NE-8 | 資料為 `demo_synthetic` | `demo_data` | `sector_eval` |

    - 多個原因同時成立時，`not_evaluated_reason` 取編號最小的一項（前端依此選用風控核可句），`not_evaluated_reasons` 列出全部。
    - NE-7 的執行期自檢：每次判定都在真實資料上跑 T-5（50 個隨機日的未來擾動）、T-9（線上與判定一致）、T-10 的來源檢查、T-13 的基準一致。CI 單元測試是另一道門，沒過就不得合併。
  - **`failed`**：G0 成立、統計已算出，但 G1～G6 有任一不成立：
    - G1：N ≥ 150 且 N_eff ≥ 60。
    - G2：Wilson 與 block bootstrap 的下界都 > b，信賴水準 1 − 0.05/m。
    - G3：p_net − b ≥ 5pp。
    - G4：置換檢定 p < 0.05/m，且扣成本後的平均超額 > 0。
    - G5：分段看、各相位看、剔除最常出現的族群後看，p_net 都 > b。
    - G6：最近 12 個月的 p_net > b。
  - **`passed`**：G0 成立，而且 G1～G6 全過。
  - **轉態與核准**：核准紀錄存在主 DB 的 `sector_gate_approvals`，只增不刪，只能用 CLI `python -m app.services.sector_board approve --kind ... --run-id ... --reviewer ...` 寫入。
    - 某版本**第一次**離開 `not_evaluated` 時，必須有 `kind='first_transition_risk'` 的紀錄（即已重送風控）；沒有就維持 `not_evaluated`，原因碼為 `pending_review`。這個碼是本 ADR 提議的，不在 NE-1～NE-8 內，待 quant 與風控確認。
    - `passed` → `failed`：自動、立即。
    - `failed` → `passed`：需要同一 `run_id` 的 `kind='quarterly_qa'` 紀錄；沒有就維持 `failed`。
  - 有效的 `gate_status` 只在 `app/sectors/gate.py` 一處組合，來源是：`sector_eval` 的候選結果、讀取時算出的 NE-3／4／5、核准紀錄。前端只依 `gate_status` 與 `not_evaluated_reason` 選用風控核可字面，**不得**自行由數字推導；`not_evaluated` 時不得使用「未達門檻」句。
  - 以下情況整卡回 `insufficient_data`：沒有 board、`data_as_of` 未知、整體覆蓋率 < 98%，或 `TWT48U_ALL` 沒涵蓋最近 L 日。

- **D-9 基準**
  - 門檻判定和主視圖一律用 B_EW，母體和還原方式都與族群相同。
  - B_EW 是對照組，**不扣成本**；族群一方每個樣本扣一次來回成本。
  - 加權指數只在「詳細」作參考（風控 R-C）：由 `sector_board_refresh` 從既有指數路徑（`backup`）取得並落表，API 以 `reference_taiex_return_L` 輸出；不用於排名，也不用於判定。
  - B_BH（買進持有）只出現在研究報告。

- **D-10 API**：`GET /api/sectors/momentum?market=TW`
  - 收合態顯示的族群數 `headline_count` 是伺服器常數，預設 3、上限 5。
  - 零 HTTP；兩個 DB 合計 SQL ≤ 7 條，條數不隨族群數或個股數增加。

  ```python
  GateStatus = Literal["passed", "failed", "not_evaluated"]
  NotEvaluatedReason = Literal[
      "pit_history_missing",      # NE-1
      "accumulating",             # NE-2
      "fee_unverified",           # NE-3
      "stale_recompute",          # NE-4
      "version_mismatch",         # NE-5
      "data_quality",             # NE-6
      "lookahead_tests_failed",   # NE-7
      "demo_data",                # NE-8
      "pending_review",           # D-8 first transition (proposed; pending quant/risk)
  ]

  class Accumulation(BaseModel):          # always present; feeds 「目前已累積 {n} 個」
      accumulated_samples: int
      accumulation_start: str | None      # D0
      required_samples: int               # 150

  class HistoricalStat(BaseModel):        # rank 1 only; forward_pit only; None unless passed/failed
      rank_scope: Literal["rank_1"]
      method_version: str
      m_at_evaluation: int
      sample_count: int                   # N
      effective_sample_count: float       # N_eff
      beat_count_net: int
      beat_count_gross: int
      base_rate_net: float                # q_net: the main-view comparator (risk §5-2, decided)
      base_rate_gross: float              # q_gross: enters the gate via b; detail view only
      ci_low_net: float                   # Wilson, level 1 - 0.05/m
      ci_high_net: float
      bootstrap_low_net: float            # circular block bootstrap, block length 4
      bootstrap_high_net: float
      benchmark: Literal["equal_weight_market"]
      sample_start: str                   # out-of-sample (forward_pit) period start
      sample_end: str                     # out-of-sample (forward_pit) period end
      stats_as_of: str                    # last sample whose forward window completed
      computed_at: str
      run_id: str

  class GateCheck(BaseModel):
      gate: Literal["G1", "G2", "G3", "G4", "G5", "G6"]
      passed: bool
      detail: str | None

  class Coverage(BaseModel):
      expected_count: int
      missing_count: int
      suspended_count: int | None         # None: no suspension-list source; counted as missing
      ex_date_excluded_count: int
      coverage_ratio: float | None

  class ConstituentItem(BaseModel):
      symbol: str
      name: str
      return_L: float | None              # signed; no rank-number field
      held: bool

  class SectorItem(BaseModel):
      rank: int
      sector_code: str
      sector_name: str                    # official classification only
      sector_return_L: float | None
      benchmark_return_L: float | None
      rel_return_L: float | None
      up_count: int
      constituent_count: int
      turnover_value_ratio_5_20: float | None   # descriptive; detail view only; NOT a ranking input
      reference_taiex_return_L: float | None    # detail view only; reference, not a comparator
      coverage: Coverage
      top_contributor_share: float | None
      single_stock_dominated: bool
      constituents: list[ConstituentItem] # top2 then bottom1

  class ExcludedSector(BaseModel):
      sector_code: str
      sector_name: str
      reason_code: Literal["too_few_members", "low_coverage", "unranked_category"]
      coverage: Coverage

  class SectorMomentumResponse(BaseModel):
      market: str
      status: PayloadStatus
      reason: str | None
      method_version: str | None
      lookback_days: int | None
      holding_days: int | None
      data_as_of: str | None              # latest complete session; one date for the whole board
      market_scope: Literal["twse_only"]  # drives 「僅上市」 tag
      benchmark: Literal["equal_weight_market"]
      coverage: Coverage | None
      headline_count: int
      sectors: list[SectorItem]           # full ranking incl. tail (PRD FR-2 詳細)
      excluded_sectors: list[ExcludedSector]
      gate_status: GateStatus
      not_evaluated_reason: NotEvaluatedReason | None     # lowest-numbered reason; None unless not_evaluated
      not_evaluated_reasons: list[NotEvaluatedReason]     # all reasons; [] unless not_evaluated
      accumulation: Accumulation
      historical_stat: HistoricalStat | None              # MUST be None when not_evaluated
      gate_checks: list[GateCheck] | None                 # MUST be None when not_evaluated
      fee_verified_on: str | None
      disclosures: list[str]              # risk-approved, always rendered
      data: DataMeta                      # reused unchanged
      as_of: str                          # response production time (company convention)
  ```

  - 比例由前端計算。主視圖顯示 `beat_count_net / sample_count` 對 `base_rate_net`，兩者都已扣來回成本。「詳細」列出 p_gross、q_gross、p_net、q_net 四個數字並標明口徑。**p_net 與 q_gross 不得並排。**
  - `historical_stat` 只取 `data_regime='forward_pit'` 的統計；`backfill_non_pit`（偏誤研究）不經 API（D-14）。
  - 分名次統計只放研究報告，不進 API（方法論 §6.1）。
  - 回應 schema 的欄位名不得含 `volume`、`hit_rate`、`win_rate`、`score`、`rating`、`confidence`、`action`。
  - 沿用 `DataMeta`，不加欄位，各欄對應如下：
    - `status`：有 board 時為 `cached_stale`，沒有時為 `unavailable`。
    - `source`：`data_as_of` 那天所採用的 bars run 來源。
    - `staleness_minutes`：取自該 run 的 `recorded_at`。
    - `is_within_ttl`：`data_as_of ≥ expected_session(...)`。
    - `bar_count`：計算視窗的交易日數。
    - `last_bar_date`：等於 `data_as_of`。
    - `trading_days_behind`：由 `pit_snapshot_runs`（bars、`ok`）的觀測日曆經 `trading_days_behind_market` 算出；為 `None` 時，前端對應 `AS_OF_CALENDAR_UNCONFIRMED_STATEMENT`。
    - `reason`：揭露字面須經風控核可。

- **D-11 資料截至日（as-of）**
  - 第一階段固定 `market_scope="twse_only"`，`data_as_of` 為上市最新一個 bars run 為 `ok` 的交易日。整張 board 只有這一個日期。
  - 日後要納入上櫃，必須升 `method_version`。屆時上市與上櫃的截至日不同時，取較早的一天；或只算已更新的那個市場，但前提是該市場範圍的變體有同版本的統計（風控 §4.5-1）。

- **D-12 存活者偏差與 point-in-time 缺口期間的系統行為**
  - **缺口未解前，`gate_status` 恆為 `not_evaluated`，主視圖與「詳細」都不出現任何比例數字。**
    - 判定只讀 `forward_pit`，也就是 D0 之後、依 D-2 可見性規則讀得到的資料。
    - D0 之前沒有當時的上市名單、分類、除權息紀錄，所以任何以 D0 前資料算出的統計都屬 NE-1，不寫入 `sector_rank_stats`。
    - D0 之後，N < 150 或 N_eff < 60 時為 NE-2；費率未查證時同時帶 NE-3。
    - API 一律帶 `accumulation`，供風控定稿句「目前已累積 {n} 個」使用；`historical_stat` 與 `gate_checks` 皆為 null。
  - **沒有例外通道。** 風控不接受書面放行分類 look-ahead（派工單 §5-4），方法論第三版也已刪除 T6 例外。程式中不存在任何接受清單、環境變數或 DB 開關可以繞過 NE-1～NE-8。CEO 若依章程 §0.5 仍要放行，須另立 ADR 修訂本條，風控的否決紀錄保留。
  - **D0**：四種 kind 第一次全部 `ok` 的交易日。寫入 `sector_method_registry.accumulation_start` 後不可更改；只有在 CEO 依方法論 §9（制度變更）裁定時，才以新版本重設。
  - **往前累積的機制**（資料表見 D-2）：
    1. 上市名單：每日保存。日後下市的股票會留在當時的快照裡，藉此解決存活者偏差。
    2. 產業分類：每日保存 `t187ap03_L` 的解析結果。改類時新舊內容分屬不同 run；第 t 日取 `recorded_at ≤ cutoff(t)` 的最新一份。
    3. 除權息：每日保存 `TWT48U_ALL` 全量，並保存當日 bars 的 `change`（參考價），供標籤因子使用。
    4. 日線：每日保存 `STOCK_DAY_ALL`。
    - 每筆都帶 `recorded_at`，只增不刪、不回填；缺日沿用前一份，連續缺超過 5 個交易日的樣本不計入。
  - **偏誤版回測**（D-14）：只存研究 DB，標示「含已知偏誤，不得上畫面」，API 不得讀取。它用 D0 前的資料，與判定資料不重疊，所以不計入 m。
  - **轉態路徑 (b)（回補）**：須先依方法論 §12 送風控。在那之前，一切回補結果都屬偏誤研究，不影響 `gate_status`。
  - **預期時程：約 3.1 年**（N ≥ 150，每年約 49 個不重疊的 5 日樣本）。v3 的較長估計作廢，理由如下：
    - 方法論第三版規定參數在 D0 前凍結並 commit。前瞻段是凍結後才產生的，沒有任何參數用它擬合過，所以整段都算樣本外。walk-forward 的 504 日訓練窗在這裡沒有擬合用途，只保留 126 日一段的測試窗幾何作分段報告，因此不需要從前瞻段扣掉訓練窗。
    - 3.1 年是**下限**：缺日作廢的樣本、N_eff < 60（序列相依）都會拉長時程。CEO 本機 scheduler 的常駐率直接決定累積速度。

- **D-13 多資產籃子回測器**
  - 介面：`app/backtest/basket.py` 的 `run_basket_backtest(panel: MarketPanel, strategy: BasketStrategy, *, schedule, cost_model, execution) -> BasketResult`。

    ```python
    #: Decides on a point-in-time view; returns target weights by symbol (may be empty).
    BasketStrategy = Callable[[PointInTimePanel], Mapping[str, float]]
    ```

  - 引擎自己持有完整面板，策略只拿得到 `panel.as_of(t)`。
  - 成交規則（方法論 §5.1）：
    - t+1 開盤成交；籃子名單固定為第 t 日的判定結果。
    - t+1 開盤價 ≥ 參考價 × 1.095 的成分股從籃子剔除。參考價取 close − change；沒有 change 時用前一日收盤價並揭露。
    - t+H 收盤出場；下一次決策在 t+H 收盤，樣本**不重疊**。
    - 成本：籃子一方每個樣本用 `CostModel` 扣一次完整來回；B_EW 對照組**不扣成本**。
  - 輸出：每個樣本的 `excess_gross`、`excess_net`，以及 `PerformanceMetrics` 全部欄位。診斷版（收盤 t → 收盤 t+H）另列，不作判定。
  - 引擎不認識族群。`sector_eval` 負責把族群排名包成 `BasketStrategy`，並負責 q、檢定與三態判定。

- **D-14 偏誤版研究的隔離（Options H2；方法論 §5.4、T10）**
  - 程式只能放在 `app/research/sector_biased/`；結果只能寫入 `STOCK_DESK_RESEARCH_DB_PATH`（預設 `./data/stock-desk-research.db`）。API 程序永不開啟此檔。
  - 每一列輸出、每一份報告、每一張圖都帶 `bias_label="含已知偏誤，不得上畫面"`，並寫明三項偏誤的方向：存活者偏差造成往上高估；分類 look-ahead 偏向動能；未還原的除權息使高殖利率族群被低估。
  - `hindsight` 視圖（忽略 `recorded_at`）只能由 `app.research.sector_biased.hindsight_view()` 建立。
  - `app.sectors.store.SectorStatsRepository.save()`／`load()` 只接受同時滿足以下條件的紀錄：`regime="pit"`、`data_regime="forward_pit"`、`source_run_ids` 全部存在於市場 DB 的 `pit_snapshot_runs`。其餘一律拋 `BiasedDataRejected`。
  - 看過偏誤研究後才提出的新版本要計入 m（D-6）。

### 對實作的約束（逐條可檢查）

- **C-1** `app.sectors` 各模組 transitively 可達的 `app.*` 模組，必須落在白名單 `{app.sectors.*, app.data.panel, app.data.interface, app.data.calendar, app.positions.sectors}` 之內。唯一例外：`app.sectors.store` 可以 import `app.data.cache`，但只能用 `resolve_db_path`。
- **C-2** **`app.sectors` 不得可達 `app.advice`。** 也不得可達 `app.signals`、`app.backtest`、`app.directory`、`app.research`、`app.playbook`、`app.kelly`、`app.portfolio`、`app.alerts`、`app.api`、`app.services`、`app.data.providers`、`app.data.service`、`app.data.http`、`httpx`。
- **C-3** `app.advice`、`app.playbook`、`app.kelly`、`app.portfolio`、`app.alerts`、`app.signals` 都不得可達 `app.sectors`；族群排行不接推播與警示。
- **C-4** `app.backtest.basket` 不得 import `app.sectors`；`app.backtest.*` 不得 import `app.sectors.store` 或 `app.research`。
- **C-5** `app.api.sectors` 的直接 import 不得包含 `app.advice`、`app.signals`、`app.backtest`、`app.research`、`app.data.service`、`app.services.market`、`app.portfolio`。
- **C-6** 端點零 HTTP，SQL ≤ 7 條，條數不隨族群數或個股數增加。
- **C-7** 市場 DB 與研究 DB 的資料不寫也不讀 `price_bars_cache` 與它的兩張 log；持倉資料鏈不讀市場 DB。
- **C-8** 市場 DB 放 `pit_snapshot_runs`、`market_daily_bars`、`pit_*_rows`、`market_backfill_progress`；研究 DB 放偏誤研究結果；主 DB 放 board、`sector_rank_stats`、`sector_gate_checks`、`sector_gate_approvals`、`sector_method_registry`。
- **C-9** 新增的 store 一律設 `busy_timeout`。
- **C-10** 市場 DB 所有表只允許 INSERT，UPDATE／DELETE 由 trigger 擋下；`recorded_at` 不得由呼叫端傳入；D0 後不回填。
- **C-11** 暖身回補只能在 D0 前以 CLI 執行；scheduler 不觸發暖身、補洞或研究。
- **C-12** 快照的交易日不得由時鐘推定，必須由資料自證（D-3）。
- **C-13** `refresh_market_data` 與 `DATA_REFRESH_LOOKBACK_DAYS` 不變。
- **C-14** 純核心只接受 `PointInTimePanel`；`regime="pit"` 的實例只能由 `MarketPanel.as_of()` 產生；判定端的可見性一律是 `recorded_at ≤ cutoff(t)`。
- **C-15** forward return、標籤、成本扣除只存在於 `basket.py` 與 `sector_eval.py`；研究 package 內的複本受 C-27 隔離。
- **C-16** 定義只有一處；`method_version` 必須與 `lookback_days`、`holding_days` 一致；L ∈ {5, 20}；API 不跨版本配對；切換版本須寫入 `sector_method_registry`。
- **C-17** 成分股依 `(−return_L, symbol)` 排序，取 `[0, 1, −1]`；不使用 advice 或 signals 的輸出；`app/sectors` 內不得出現 score／rating 類識別字。
- **C-18** 報酬函式只有一處；回看窗排除窗內有除權息的成分股；`TWT48U_ALL` 沒涵蓋最近 L 日時，整卡回 `insufficient_data`。
- **C-19** 判定用 p_net 對 `b = max(q_gross, 0.5)`、效果量 ≥ 5pp、信賴水準 1 − 0.05/m，門檻只能調嚴；主視圖呈現 p_net 對 q_net；p_net 與 q_gross 不得並排。
- **C-20** 有效 `gate_status` 只在 `app/sectors/gate.py` 組合；核准紀錄只增不刪。
- **C-21** `sector_rank_stats`、`sector_gate_checks`、`sector_gate_approvals`、`sector_method_registry` 只能新增列。唯一例外是 registry 的 `first_forward_eval_at`，允許由 NULL 寫入一次。
- **C-22** `backfill_non_pit` 與 `forward_pit` 分開存：前者只在研究 DB，後者在主 DB；API 只回 `forward_pit`。
- **C-23** `gate_status == "not_evaluated"` 時，`historical_stat is None` 且 `gate_checks is None`，回應中不含任何比例數字。
- **C-24** 程式中不存在任何可以繞過 NE-1～NE-8 的開關、清單或環境變數。
- **C-25** `CostModel.verified_on is None` 時，NE-3 必定成立，`gate_status` 必為 `not_evaluated`。
- **C-26** `turnover_value_ratio_5_20` 不得作為 `rank_sectors` 的輸入，只放「詳細」；回應 schema 欄位名不得含 `volume`、`hit_rate`、`win_rate`、`score`、`rating`、`confidence`、`action`。
- **C-27** 除 `app.research` 自身外，任何 `app.*` 模組都不得可達 `app.research`；字串 `STOCK_DESK_RESEARCH_DB_PATH` 只出現在 `app/research/` 與 tests；`hindsight_view` 只在 `app/research/` 內定義與呼叫；`SectorStatsRepository` 拒收非 PIT 紀錄。
- **C-28** `rank` 只在族群層級；`historical_stat` 只在卡片層級出現一次；整張 board 只有一個 `data_as_of`。
- **C-29** `demo_synthetic` 資料必定觸發 NE-8。
- **C-30** 使用者看得到的字面全部要經風控核可，並逐字寫死在常數與測試裡；`not_evaluated` 時不得使用「未達門檻」句。

## 測試策略（全部離線；對應方法論 §8 T1～T10）

- **T-1** `tests/test_sectors_boundary.py`：沿用 `import_graph`，涵蓋 C-1～C-5。
  - 列舉 `app/sectors` 下的每一個檔案，確認都在守門清單內。
  - 驗證模組名稱都能解析，避免拼錯導致測試形同虛設。
  - 加一個 teeth test（故意違規時，測試確實會失敗）。
  - 掃描 advice 輸出欄位名與 score 類識別字。
- **T-2** 零 IO：注入「任何呼叫都拋錯」的 resolver 與 transport，端點仍回 200；以 `set_trace_callback` 計算兩個 DB 合計的 SQL 條數 ≤ 7，而且 10 個與 40 個族群時條數相同。
- **T-3** 資料鏈隔離：擷取與暖身前後，`price_bars_cache` 與兩張 log 的 checksum 不變；主 DB 內不存在 `market_daily_bars`。
- **T-4** PIT 儲存：
  - UPDATE／DELETE 一律失敗（store 不提供方法，trigger 也會擋下）；
  - `recorded_at` 無法由呼叫端傳入；
  - 無法自證日期時記 `failed`；
  - 缺日時沿用前一份並標 `carried_forward`，連續缺超過 5 個交易日的樣本作廢；
  - `cutoff(t)` 之後寫入的 run，對第 t 日的決策不可見；
  - D0 之後暖身 CLI 拒絕執行。
- **T-5** 未來擾動不變性（方法論 T1）：隨機取 50 個 t，把 t 之後（以 `recorded_at` 為準）的所有列（價格、名單、分類、事件）換成雜訊，第 t 日的輸出必須逐位元相同；`PointInTimePanel` 存取範圍外的資料必須拋錯。
- **T-6** Shift 測試（方法論 T3a、T3b）：注入洩漏時，比例必須明顯上升；延遲 1 日的結果要記錄。
- **T-7** 除權息不洩漏（方法論 T4）：排除清單只依 `recorded_at ≤ cutoff(t)` 的公告；測試路徑上必須真的有除權息事件。
- **T-8** 存活者偏差與分類 PIT（方法論 T5、T6）：
  - 在 t+k 下市的股票，必須出現在第 t 日的母體中；
  - 在 t+k 改類的股票，第 t 日必須仍屬舊族群；
  - 沒有 PIT 分類即為 NE-1，**沒有例外**。
- **T-9** 線上與判定一致（方法論 T9）：同一個第 t 日，board 的輸出必須逐欄等於 `sector_eval` 的回放結果。
- **T-10** 偏誤版研究隔離（方法論 T10）：
  - import 邊界守門 C-4、C-5、C-27，寫法比照 C-1～C-5：`GUARDED_MODULES` 列出 `app.api.sectors`、`app.sectors.*`、`app.services.sector_board`、`app.backtest.sector_eval`、`app.backtest.basket`，全部不得可達 `app.research`；另列舉 `app/research/` 下的檔案，確認都有被掃到；加 teeth test。
  - 以字串與識別字掃描，確認 `STOCK_DESK_RESEARCH_DB_PATH`、`hindsight_view` 只出現在允許的位置。
  - 把 hindsight 或 `backfill_non_pit` 紀錄交給 `SectorStatsRepository`，必須拋 `BiasedDataRejected`。
  - 研究 DB 存在且有資料時，API 回應必須和研究 DB 不存在時完全相同。
- **T-11** 三態：
  - NE-1～NE-8 與 `pending_review` 各有一個單獨成立的案例，每個案例都驗證 `historical_stat is None`、`gate_checks is None`，且 `not_evaluated_reason` 取編號最小者；
  - `verified_on=None` 時必定出現 NE-3；
  - NE-4 邊界：第 20 個交易日不成立，第 21 個交易日成立；
  - G1～G6 各自單獨不過時，結果為 `failed`；
  - `failed` → `passed` 需要 `quarterly_qa` 紀錄；首次轉態需要 `first_transition_risk` 紀錄。
- **T-12** 參數與描述欄位：
  - `method_version` 與 L、H 不一致時建構失敗；L=10 時建構失敗；
  - 擾動 `turnover_value_ratio_5_20` 時名次完全不變；
  - m 由 registry 計算，並寫入 `m_at_evaluation`。
- **T-13** 基準與安慰劑（方法論 T7、T8）：B_EW 成分等於同日合格母體；B_EW 不扣成本；打亂標籤或平移訊號後，比例落在 q 的區間內。
- **T-14** Schema 與字面：
  - 掃描 OpenAPI schema，確認沒有 C-26 禁止的欄位名；
  - `not_evaluated` 時，回應 JSON 不含任何比例數值；
  - 風控定稿字面在前端與後端兩邊逐字釘住。

## Consequences（後果）

- **好處**
  - 首頁零 HTTP，滿足 PRD FR-8；持倉資料鏈與 ADR-0009、ADR-0010 都不受影響。
  - 線上與判定用同一段程式碼、同一個 `method_version`，一致性可以用測試證明。
  - 三態與資料缺口都由機器判定，沒有繞過通道。
  - 偏誤資料有四層隔離。
  - 前瞻累積的資料是最乾淨的樣本外資料。
- **代價（照實計）**
  - **第一階段不列任何歷史比例**，最快約 3.1 年後才可能判定（這是下限），而判定結果最可能是 `failed`（方法論 §0-3）。**這是本 ADR 最大的代價，必須由 CEO 接受。**
  - 市場 DB 只增不刪、不可重建，遺失就等於累積歸零，必須列為最高備份等級。
  - 三個 DB 檔（主、市場、研究）各需一套備份策略；研究 DB 可以重建，可不備份。
  - 暖身回補必須在 D0 前、於 CEO 本機以 CLI 完成，約 1,100 次 FinMind 請求（額度未驗證）。
  - D0 之後漏抓的日子不回填，連續缺超過 5 日的樣本作廢；CEO 本機 scheduler 的常駐率直接決定累積速度。
  - 除息旺季時，部分族群會因成分股被大量排除而不列入排行（方法論 §13-9）。
  - 首頁報酬是排除除權息窗後的數字，可能和個股頁的未還原走勢不同，需要揭露句。
  - 資料量：前瞻每年約 1,100 × 245 ≈ 27 萬列日線；名單、分類、除權息用內容定址去重。實際量待實測。
  - 只含上市，「僅上市」標記常駐；上櫃的記憶體股、IC 設計股都會缺席。
  - 新增 2 個 job、約 12 張表；API 程序與 scheduler 程序的限流不共享。
- **已知限制**
  - `cutoff(t)` 取當地 23:59:59，所以 21:30 之後的更正要到次日才對決策可見。
  - `pending_review` 原因碼待 quant 與風控確認。
  - 持倉資料鏈若要改從市場面板取價，須另立 ADR。

## 與既有 ADR 的關係（§7）

- **ADR-0002**：不取代。本 ADR 把「走 `MarketDataProvider`」擴充解讀為「走 `app/data` 內可替換的抽象介面」，並新增同層的 `MarketSnapshotProvider`；另外多兩個 SQLite 檔（市場 DB、研究 DB），技術棧不變。請 CEO 核可時一併裁定。
- **ADR-0009、ADR-0010**：不修訂（見 C-7、C-12）。
- **ADR-0005**：B_TAIEX／B_BH 沿用 `backup` 紀律。
- **ADR-0004、ADR-0006**：不涉及。

## 開放問題答覆（§8）

**data-engineer（依資料評估）**

| # | 題目 | 答覆 | 狀態 |
| --- | --- | --- | --- |
| DE-1 | 可指定日期的全市場端點 | `STOCK_DAY_ALL` 只給當日；TPEx 只給當日，且混有非普通股；`MI_INDEX` 未驗證 | 已定案：前瞻用每日快照（D-3）；`MI_INDEX` **待 CEO 本機查證** |
| DE-1' | payload 是否帶交易日 | 未知 | **待 CEO 本機查證**；查證前走交叉比對 |
| DE-2 | FinMind 額度 | 逐檔已驗證；額度未知 | 已定案：只用於暖身與日期自證；額度**待查證** |
| DE-3 | 速率界線 | 未知 | **待查證**；先沿用現有下限 |
| DE-4 | 上櫃產業別；非普通股排除 | 上櫃無來源；以 `t187ap03_L` 正向篩選 | 已定案：`twse_only` 加白名單母體 |
| DE-5 | `change` 是否以參考價為基準；`TWT48U_ALL` 能否算出乘法因子 | 未知 | **待查證**；查證前標籤因子不可用（NE-1） |
| DE-6 | 資料量 | 前瞻每年約 27 萬列日線，快照去重 | **待實測** |
| DE-7 | 資料公布時間 | 建議 17:00 之後 | 已定案：17:30／19:30／21:30 加日期自證；實際時間**待查證** |
| DE-8 | 已下市股票 | 無來源 | 前瞻累積自然解決；路徑 (b) **待查證** |
| DE-9 | 歷史產業分類 | 無來源 | 前瞻累積；路徑 (b) 依方法論 §12 |
| DE-10 | 成本費率 | 未查證 | 在查證前即為 NE-3；**待查證** |

**quant-researcher（依方法論第三版，全部定案；門檻只能調嚴）**

- **Q-1 母體與權重**：等權，期初等權、期間持有。條件：上市滿 60 個交易日；20 日成交金額中位數 ≥ NT$1,000 萬，且 20 日內有成交 ≥ 18 天；族群成分 ≥ 5 檔；族群覆蓋率 ≥ 90%、整體 ≥ 98%。排除代碼 91；代碼 20 不排名但計入 B_EW。
- **Q-2 基準**：判定與主視圖用 B_EW（不扣成本）；加權指數只在「詳細」作參考。
- **Q-3 訊號**：只用 C1（`rel_return_L`）；C2～C6 已登記但未啟用；同名次依代碼排序；上漲家數與成交金額倍數只當描述欄位。
- **Q-4 時序與統計**：t+1 開盤進、t+H 收盤出，樣本不重疊。統計用 Wilson、circular block bootstrap（區塊長度 4、1 萬次、記錄 seed）、置換檢定；顯著水準 α/m。
- **Q-5 判定**：G0（NE-1～NE-8 全不成立）加 G1～G6，詳見 D-8。
- **Q-6 缺口處理**：見 D-12。
- **Q-7 q**：每週全部合格族群的平均，分 gross、net 兩種。主視圖用 q_net；判定用 b = max(q_gross, 50%)。風控已於 §5-2 定案。
- **Q-8 成本**：每個樣本扣一次完整來回；策略層依實際週轉；滑價 0／10／20 bps。
- **Q-9 歷史長度**：路徑 (a) 需要 D0 前至少 80 個交易日作暖身；2016 年起的長歷史只供偏誤研究使用。

**其他部門**

- **quant-researcher 與 risk-compliance-officer**：確認 `pending_review` 原因碼。
- **creative-lead 與 risk-compliance-officer**：起草並審定 NE-3～NE-8 與 `pending_review` 的原因句，以及混源、同一檔兩種價格的揭露句。
- **product-manager**：PRD 第三版已併入 R-A～R-C；N 維持 3。
- **devops-sre**：三個 DB 的備份（市場 DB 為最高等級）、scheduler 常駐監控、暖身回補操作手冊。
- **CEO**：
  - 是否接受第一階段不列歷史比例，且累積時程下限約 3.1 年；
  - D0 日期（v1 參數須在 D0 前 commit，暖身須在 D0 前完成）；
  - 三個 DB 檔的配置；
  - §7 對 ADR-0002 的擴充解讀。

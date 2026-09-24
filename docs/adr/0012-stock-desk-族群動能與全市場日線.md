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
  - `work/stock-desk-族群動能-PRD.md`（狀態 spec）
  - `work/stock-desk-族群動能-資料評估.md`（data-engineer）
  - `work/stock-desk-族群動能-方法論.md`（quant-researcher，v1 草案第二版）
  - `work/stock-desk-族群動能-派工單.md` §4（風控預審：APPROVE_WITH_CONDITIONS；成分股技術面分數 VETO）
- 修訂：
  - v1（2026-09-24）：初稿，完成時上述輸入都還沒有。
  - v3（2026-09-24）：併入上述全部輸入。
    - 移除成分股分數。
    - 統計欄位與門檻改依方法論。
    - 新增覆蓋率、市場範圍標記、point-in-time 缺口機制、多資產籃子回測器。
    - 全市場日線改放獨立 SQLite 檔。
    - dev-lead 的「待修訂」註記結案。
- **v3 殘留差異（dev-lead 註記，2026-09-24，下一版 v4 修正）**：v3 依方法論第二版撰寫，晚於它的兩份輸入尚未吸收：
  1. 風控第二次裁定（派工單 §5）已定案：主視圖 q 配 **q_net**（第 2 點）；「均量」改「成交金額 5 日均／20 日均」且只放詳細（第 3 點）；`not_evaluated` 時主視圖**與詳細**皆不列任何比例數字，故 D-12「『詳細』可以照實列出兩段統計」與 §8 相關待裁定題目作廢，`backfill_non_pit` 不得露出（第 4 點）。
  2. 方法論第三版：`not_evaluated_reason` 列舉 NE-1～NE-8、`not_evaluated` 時統計欄位回 null；D9 費率未查證即 `not_evaluated`；`method_version` 命名為 `sector-rel-v1.0-L5-H5`，回看窗 L 與持有期 H 為兩個參數；判定用 α/m；刪除 T6 例外；T10 偏誤版研究與 API 隔離。
  3. 預期時程：方法論第三版為參數於 D0 前凍結、前瞻段全段視同樣本外，約 3.1 年（N ≥ 150）；v3 D-12 加上 504 日訓練窗得「5 年以上」，兩者須統一。
- 修訂：v3 為目前版本。

## Context（背景）

CEO 在 2026-09-24 裁定開第一階段：首頁新增「族群動能排行」卡，只呈現「近 5 日相對強弱」加上「歷史比例」，不做「預測會漲」。第一階段只用日線。

風控核可族群層級的框架，但附了條件：
- 否決成分股的技術面分數；
- 規定歷史比例的呈現方式與降級門檻；
- 規定資料時效、覆蓋率、存活者偏差、point-in-time 分類與除權息的處理。

方法論的定案內容：
- 排名訊號 S_A：近 5 日等權族群報酬，減去等權全市場（B_EW）報酬。
- 時序：第 t 日收盤出訊號，第 t+1 日開盤進場，第 t+5 日收盤出場。
- 門檻 G0～G7，方法論事前就預期結果多半會降級。

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
| B2 新表放在同一個 SQLite 檔（v1 的決定） | 不多一個檔案 | 約 260 萬列可重建資料，會和不可重建的使用者資料共用備份與 WAL；回補期間和持倉查詢搶同一把寫鎖（資料評估 §6-2） | v3 推翻 |
| **B3 新表放獨立 SQLite 檔 `STOCK_DESK_MARKET_DB_PATH`，預設 `./data/stock-desk-market.db`（採用）** | 寫鎖隔離；可重建資料和不可重建資料分開；主 DB 備份維持小 | 多管一個檔；API 讀取要開兩個連線 | 低，檔案遺失的處置寫進 devops 手冊 |
| B4 DuckDB／Parquet | 分析快 | 偏離 ADR-0002 | 否決 |

表名採 `market_daily_bars`，不用資料評估建議的 `sector_universe_daily_bars`。理由有兩個：
- 這張表存的是市場日線這個資料事實，裡面包含 B_EW 要用、但不參與族群排名的「其他業」股票，母體和族群母體不一樣。
- 以消費功能命名，日後其他用途（例如持倉資料鏈改從這張表取價，須另立 ADR）會出現語意錯置。

log 表命名為 `market_ingest_log`，吸收資料評估 §8.1 提的 `status`、`actual_count`、`expected_count`。

### C. 計算時點

| 方案 | 優點 | 缺點 | 風險 |
| --- | --- | --- | --- |
| **C1 盤後批次預先算好落表，首頁只讀（採用）** | 請求零 HTTP、SQL 條數固定，滿足 PRD FR-8「P95 ≤ 2 秒」；所有結果出自同一個 `definition_version` | 排程沒跑就是舊資料，由常駐揭露與 20 交易日降級處理 | 冷啟動時整卡回 `insufficient_data` |
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

## Decision（決策）

- **D-1 套件配置與依賴方向**

  ```
  app/data/panel.py               # PointInTimePanel / MarketPanel (pure, pandas, no I/O)
  app/data/market_panel.py        # store: market_daily_bars, market_ingest_log (market DB)
  app/data/market_panel_sync.py   # snapshot ingest + FinMind backfill CLI (network)
  app/data/providers/twse_snapshot.py   # MarketSnapshotProvider over STOCK_DAY_ALL
  app/directory/classification_history.py  # sector_classification_history store (main DB)
  app/sectors/                    # pure core + own store (main DB)
      definition.py  models.py  universe.py  index.py  ranking.py
      constituents.py  coverage.py  degrade.py  limitations.py  store.py
  app/backtest/basket.py          # generic point-in-time multi-asset basket engine
  app/backtest/sector_eval.py     # labels, stats, gate G0–G7; the ONLY place forward returns exist
  app/services/sector_board.py    # orchestration + CLI (approve-gate, rebuild)
  app/api/sectors.py              # read-only router
  ```

  依賴方向：
  - `api.sectors` → `{sectors 純核心, sectors.store, data.market_panel（唯讀）, positions.store（只讀持有旗標）}`
  - `services.sector_board` → `{data.market_panel, directory.classification_history, sectors.*, backtest.sector_eval}`
  - `backtest.sector_eval` → `{sectors 純核心, backtest.basket, costs, splits, episodes, report}`
  - `backtest.basket` → `{data.panel, costs, report}`
  - `sectors 純核心` → `{data.panel, data.interface, data.calendar, positions.sectors}`

  禁止事項：
  - **`app.sectors` 不得 import `app.advice`、`app.signals`、`app.backtest`、`app.directory`。**
  - `app.backtest.basket` 不得 import `app.sectors`。

- **D-2 全市場日線是獨立資料鏈，放在獨立檔案**
  - 市場 DB 內的兩張表：
    - `market_daily_bars`
      - 主鍵 `(trade_date, exchange, symbol)`，`WITHOUT ROWID`；另建次索引 `(symbol, trade_date)`。
      - 欄位：`market`、`exchange`、開高低收（存 Decimal 字串）、`volume`（股）、`turnover`（成交金額，元）、`change`（可為 NULL）、`source`。
    - `market_ingest_log`
      - 主鍵 `(exchange, trade_date)`。
      - `status` 只能是 `complete`、`partial`、`empty_unconfirmed`、`closed`、`failed` 之一。
      - 另有 `source`、`actual_count`、`expected_count`、`fetched_at`、`last_attempt_at`、`reason`。
  - `complete` 的條件：`actual_count / expected_count` 達到 `min_overall_coverage`。
  - `empty_unconfirmed` 要等之後有交易日 `complete`，才升級成 `closed`。這個判定不回饋給 `freshness.judge()`。
  - 寫入規則是「主來源優先、備援只補缺」：`twse_snapshot` 可以覆寫 `finmind` 的列，反過來不行。這和 `PriceBarCache.put()` 刻意不同。
  - 全市場資料不寫也不讀 `price_bars_cache` 及它的兩張 log 表。

- **D-3 provider 介面與資料來源**
  - 在 `app/data/interface.py` 新增 `MarketSnapshotProvider.get_latest_snapshot() -> SnapshotResult`。這個方法沒有日期參數，因為 `STOCK_DAY_ALL` 本身就只給當日。
  - **交易日由資料自證（DE-1'）**：
    - payload 帶交易日時，以 payload 為準。
    - payload 不帶交易日時，不得用時鐘推定。改用 FinMind 逐檔抽 3 檔（固定清單加隨機抽樣，seed 要記錄），比對 `expected_session` 那天的收盤價與成交量；完全相符才認定快照屬於該日，否則記 `failed`。
  - 歷史回補與漏抓補洞一律走 CLI：`python -m app.data.market_panel_sync --backfill --since YYYY-MM-DD`。
    - 用 FinMind 逐檔抓，以 symbol 為最小重試單位。
    - checkpoint 記在 `market_backfill_progress`。
    - 一檔一個 transaction。
    - 節流沿用現有下限：FinMind 0.3 秒、TWSE 0.5 秒。
    - **scheduler 不觸發回補，也不觸發補洞。**
  - `MI_INDEX` 如果經 CEO 本機查證可用，另外修訂本 ADR 把它納入。
  - TPEx 第一階段不抓。

- **D-4 報酬與除權息**
  - 報酬函式只有一處，在 `index.py`。算法是期初等權、期間持有：`R_g(t,L) = mean_i(P_i(t)/P_i(t−L) − 1)`。
  - 還原方式由 `definition.adjustment_method` 決定，線上和回測一定用同一種：
    - (a) `reference_chain`：日報酬 `r_t = change_t / (close_t − change_t)`，逐日連乘。這是乘法因子，符合方法論 §2.4 的前提。**前提是 CEO 本機查證 `Change` 和 FinMind 的 `spread` 都以除權息參考價為基準（DE-5）。** 查證通過就優先用這個。
    - (b) `ex_date_excluded`：成分股在視窗內遇到除權息日就排除。除權息日期從上線日起每天同步 `TWT48U_ALL` 累積，只涵蓋上市。
  - 兩種方式都不成立的日期，歸到 D-12 的 `dividend_adjustment_gap`。
  - 額外加一道保險：成分股在視窗內單日報酬超過漲跌幅上限加容差，就排除該檔並記錄。

- **D-5 計算時點：盤後批次**
  - scheduler 新增三個 job。全部用 `CronTrigger`、時區 Asia/Taipei、只在平日跑、`max_instances=1`、`coalesce=True`，並在啟動時各補跑一次：
    - `market_snapshot_ingest`：17:30、19:30、21:30 各跑一次。
    - `sector_board_refresh`：只在當日 ingest 狀態為 `complete` 時才計算。
    - `classification_snapshot`：每日一次，只抓 `TwseSectorProfileAdapter` 並做 resolve，**不跑**會寫入 positions 的完整目錄同步。
  - `sector_board_refresh` 的流程：
    1. 寫入當日的 `sector_board`、`sector_board_members`、`sector_board_excluded`。
    2. 每新完成一個不重疊的 5 日樣本，就呼叫 `sector_eval` 重算統計與門檻；`sector_rank_stats`、`sector_gate_checks` 只新增、不修改。
  - 評估失敗不影響 board 本身；API 讀取時會依 `stats_stale` 降級。

- **D-6 共用計算碼、定義版本鎖定、look-ahead 守門**
  - `definition.py` 是唯一定義處，v1 的凍結值以方法論 §11.1 為準：

    ```python
    @dataclass(frozen=True)
    class SectorMomentumDefinition:
        version: str                      # e.g. "sector-rel-return-v1.0-L5"; any change => new version
        market_scope: Literal["twse_only"]
        ranking_signal: Literal["rel_return_5d"]      # S_A; S_B registered for testing only
        benchmark: Literal["equal_weight_market"]     # B_EW
        adjustment_method: Literal["reference_chain", "ex_date_excluded"]
        constituent_rule: Literal["top2_bottom1"]
        universe: UniverseRules           # listing age, liquidity, excluded codes (20 unranked, 91 excluded)
        coverage: CoverageRules           # min members 5, sector >= 0.90, overall >= 0.98 (risk to confirm)
        schedule: Literal["t_close_signal_t1_open_t5_close_non_overlapping"]
        gate: GateRules                   # G0–G7 thresholds; may only be tightened
    ```

  - 線上和評估器共用 `universe.eligible`、`index.member_returns`、`ranking.rank_sectors`、`constituents.list_constituents`、`coverage.assess`。這些函式只接受 `PointInTimePanel`。
  - `PointInTimePanel` 只能由 `MarketPanel.as_of(t)` 建立，建立時就把資料截到 ≤ t；存取 t 之後的列會直接拋錯。
  - `ClassificationView.at(t)` 只取 `observed_on ≤ t` 的分類。
  - forward return、標籤、成本扣除只存在於 `basket.py` 與 `sector_eval.py`。

- **D-7 成分股**
  - 取族群內合格且有資料的成分股，依 `(−return_5d, symbol)` 排序，取位置 `[0, 1, −1]`；成分股不超過 3 檔時全列。
  - 缺資料的成分股計入 `missing_count`。
  - 不產生、不儲存任何分數，不附歷史比例，不帶任何規則引擎輸出。
  - `held`（是否持有）由 API 在讀取時查 positions 表得出。

- **D-8 門檻與降級：兩段判定**
  - **評估器**依方法論 §6.3 算出 G0～G5，以及 G6 前半（最近 12 個月的 p ≤ q_gross），並輸出 `gate_candidate`。
    - 門檻判定一律拿扣成本後的 p_net 和 q_gross 比。
    - G0 的內容：不是 `demo_synthetic`、D-12 的缺口都已解除或已登記接受、品質檢查通過、look-ahead 測試全綠。
  - **核准**：`gate_candidate=passed` 還不夠，必須在 `sector_gate_approvals` 有對應同一個 `definition_version` 與 `run_id` 的列，`gate_status` 才會是 `passed`。
    - 這一列由 CLI `approve-gate` 寫入，只在每季檢視時經 qa-reviewer 確認後執行。
    - 候選結果是 `failed` 時立即生效，不需要核准。
  - **讀取時**由 `degrade.py` 單一路徑判定。以下任一條件成立，`wording_tier` 就是 `strength_only`：
    - `gate_status` 不是 `passed`；
    - `stats_stale`：`stats_panel_through` 之後又出現超過 20 個 `complete` 交易日；
    - `definition_mismatch`；
    - `forward_divergence`：上線後滿 26 個樣本，且二項檢定 p < 0.05；
    - 整體覆蓋率降級。
  - 前端只依 `wording_tier` 選用風控定稿句，不得自己推導。
  - 整卡回 `insufficient_data` 的情況：沒有 board、`data_as_of` 未知、或整體覆蓋率低於門檻。

- **D-9 基準**
  - 門檻判定和主視圖一律用 B_EW，母體和還原方式都與族群相同。
  - B_TAIEX（加權指數）、B_BH（買進持有）只出現在研究報告，走指數路徑並標 `backup`；第一階段 API 不輸出。

- **D-10 API**：`GET /api/sectors/momentum?market=TW`
  - 收合態顯示的族群數 `headline_count` 是伺服器常數，預設 3、上限 5。
  - 零 HTTP；兩個 DB 合計 SQL ≤ 7 條，而且條數不隨族群數或個股數增加。

  ```python
  GateStatus = Literal["passed", "failed", "not_evaluated"]
  WordingTier = Literal["probability", "strength_only"]
  DataRegime = Literal["forward_pit", "backfill_non_pit"]

  class Coverage(BaseModel):
      expected_count: int
      missing_count: int
      suspended_count: int | None          # None: no suspension-list source (all counted as missing)
      coverage_ratio: float | None

  class BaseRate(BaseModel):
      gross: float                         # q_gross (gate comparator)
      net: float                           # q_net (display pairing pending risk)

  class RankStats(BaseModel):
      rank_position: int
      data_regime: DataRegime
      definition_version: str
      run_id: str
      cost_basis: Literal["net_round_trip"]
      beat_count: int
      sample_count: int
      effective_sample_count: float | None
      base_rate: BaseRate
      wilson_low: float | None
      wilson_high: float | None
      bootstrap_low: float | None
      bootstrap_high: float | None
      bootstrap_block_length: int
      permutation_p_holm: float | None
      mean_excess_gross: float | None
      mean_excess_net: float | None
      median_excess_net: float | None
      stats_as_of: str                     # last sample whose forward window completed
      stats_panel_through: str             # panel date the evaluator ran on
      oos_start: str | None
      oos_end: str | None
      computed_at: str

  class GateCheck(BaseModel):
      gate: str                            # "G0".."G7"
      passed: bool | None                  # None = not evaluable
      detail: str | None

  class DegradeReason(BaseModel):
      code: str
      message: str                         # risk-approved sentence

  class ConstituentItem(BaseModel):
      symbol: str
      name: str
      exchange: str
      return_5d: float | None              # adjusted, signed
      held: bool

  class SectorItem(BaseModel):
      rank: int
      sector_code: str
      sector_name: str                     # official classification only
      sector_return_5d: float | None
      benchmark_return_5d: float | None
      rel_return_5d: float | None
      rel_return_20d: float | None
      up_count: int
      constituent_count: int
      turnover_ratio_5_20: float | None    # traded value basis (wording pending risk)
      coverage: Coverage
      top_contributor_share: float | None
      single_stock_dominated: bool
      constituents: list[ConstituentItem]  # order: top2 then bottom1, no rank numbers

  class ExcludedSector(BaseModel):
      sector_code: str
      sector_name: str
      reason_code: Literal["too_few_members", "low_coverage", "unranked_category"]
      coverage: Coverage

  class SectorMomentumResponse(BaseModel):
      market: str
      status: PayloadStatus
      reason: str | None
      definition_version: str | None
      data_as_of: str | None               # latest complete session; one date for the whole board
      market_scope: Literal["twse_only"]   # drives 「僅上市」 tag
      benchmark: Literal["equal_weight_market"]
      adjustment_method: str | None
      coverage: Coverage | None
      headline_count: int
      sectors: list[SectorItem]            # full ranking incl. tail (PRD FR-2 詳細)
      excluded_sectors: list[ExcludedSector]
      gate_status: GateStatus
      wording_tier: WordingTier
      degraded_reasons: list[DegradeReason]
      rank1_stats: RankStats | None        # card-level, once; regime used for the gate
      rank_stats_detail: list[RankStats]   # per rank position, per regime (detail view)
      gate_checks: list[GateCheck]
      pit_regime_start: str | None
      limitations: list[str]               # D-12 gap codes, always echoed
      disclosures: list[str]               # risk-approved, always rendered
      data: DataMeta                       # reused unchanged
      as_of: str                           # response production time (company convention)
  ```

  - 百分比 p 由前端用 `beat_count / sample_count` 計算，只准透過單一格式化函式。
  - 回應 schema 不得出現 `hit_rate`、`win_rate`、`score`、`rating`、`confidence`、`action`。
  - 沿用 `DataMeta`，不加欄位，各欄對應如下：
    - `status`：有 board 時為 `cached_stale`，沒有時為 `unavailable`。
    - `source`：`data_as_of` 那天的實際來源。
    - `staleness_minutes`：取 ingest 的 `fetched_at`。
    - `is_within_ttl`：`data_as_of ≥ expected_session(...)`。
    - `bar_count`：計算視窗的交易日數。
    - `last_bar_date`：等於 `data_as_of`。
    - `trading_days_behind`：由 ingest log 的觀測日曆經 `trading_days_behind_market` 算出；值為 `None` 時，前端對應 `AS_OF_CALENDAR_UNCONFIRMED_STATEMENT`。
    - `reason`：揭露字面須經風控核可。

- **D-11 資料截至日（as-of）**
  - 第一階段固定 `market_scope="twse_only"`，`data_as_of` 為上市最新一個 `complete` 的交易日。整張 board 只有這一個日期。
  - 日後要納入上櫃，必須升 `definition_version`。屆時上市與上櫃的截至日不同時，取較早的一天；或只算已更新的那個市場，但前提是該市場範圍的變體有同版本的統計（風控 §4.5-1）。

- **D-12 存活者偏差與 point-in-time 缺口期間的系統行為**
  - `limitations.py` 定義四個缺口碼，每個都附偵測方式與解除條件：
    - `classification_pit_gap`：缺歷史分類。
    - `survivorship_gap`：缺已下市名單。
    - `dividend_adjustment_gap`：缺除權息或還原資料。
    - `suspension_list_missing`：缺暫停交易名單。缺這份名單時，暫停交易股一律計入缺漏，偏向保守。
  - 評估器把樣本拆成兩段分開存，**永不合併成一個數字**：
    - `backfill_non_pit`：用現行分類、只含現存股的回補期間。
    - `forward_pit`：從 `pit_regime_start` 開始的期間。
  - `pit_regime_start` 取下列三個日期中最晚的一個：
    - 分類歷史的首次觀測日；
    - 每日快照開始累積的日期；
    - 還原方法可以使用的起始日。
  - **缺口未解前，`wording_tier` 是否恆為 `strength_only`？答案是「是」。** 只要門檻評估用的那段期間落在任何未解除、也未登記接受的缺口內，G0 就不成立，`gate_candidate` 為 `not_evaluated`，所以 `wording_tier` 一定是 `strength_only`。此時 `degraded_reasons` 逐條列出缺口碼，`limitations` 常駐回傳。
  - 「詳細」可以照實列出兩段統計。但 `backfill_non_pit` 那段能不能露出、要附什麼揭露句，待風控裁定。
  - **例外登記**：CEO 與風控若書面接受某個缺口，要在 `limitations.py` 的 `ACCEPTED_LIMITATIONS` 常數新增一筆，並經 qa-reviewer 審查。每筆要寫明缺口碼、核准人、日期、文件路徑、風控定稿的揭露句。不得用環境變數或 DB 開關代替。
  - **上線後往前累積的機制**：
    1. **分類**：`classification_snapshot` 每日把分類寫進主 DB 的 `sector_classification_history`。
       - 欄位：`symbol, market, sector_code, sector_name, source, observed_on, superseded_on`。
       - 只在分類有變化時開新列；`superseded_on` 只寫入一次。
       - 生效日保守地取 `observed_on`。
       - 兩次成功觀測之間超過 10 個交易日，這段期間標記 `classification_pit_gap`。
       - 這張表無法重建，放主 DB 並列入備份。
    2. **存活者偏差**：每日快照含當日所有交易中的上市股，所以從累積起始日開始，日後下市的股票和它當時的分類會被自然保留。
    3. **除權息**：`reference_chain` 查證通過的話，從快照有 `Change` 那天起就能用；否則每日同步 `TWT48U_ALL` 把預告的除權息日期存下來，從上線日起累積。
    4. `forward_pit` 這段就是方法論 §6.3 講的前瞻紀錄。
  - **預期時程**：`forward_pit` 要達到 G1（N ≥ 150、N_eff ≥ 60），加上 504 日的訓練窗，約需 5 年以上。

- **D-13 多資產籃子回測器**
  - 介面：`app/backtest/basket.py` 的 `run_basket_backtest(panel: MarketPanel, strategy: BasketStrategy, *, schedule, cost_model, execution) -> BasketResult`。

    ```python
    #: Decides on a point-in-time view; returns target weights by symbol (may be empty).
    BasketStrategy = Callable[[PointInTimePanel], Mapping[str, float]]
    ```

  - 引擎自己持有完整面板，策略只拿得到 `panel.as_of(t)`。
  - 成交規則：
    - t+1 開盤成交。
    - 開盤價 ≥ 參考價 × 1.095 的成分股從籃子剔除。參考價取 close − change；沒有 change 時用前一日收盤價並揭露。
    - t+H 收盤出場。
    - 成本走 `CostModel`，每個樣本扣完整一次來回。
  - 輸出：每個樣本的 excess（扣成本前與扣成本後），以及 `PerformanceMetrics` 的全部欄位。
  - 引擎不認識族群。`sector_eval` 負責把族群排名包成 `BasketStrategy`，並負責 q、檢定與門檻。

### 對實作的約束（逐條可檢查）

- **C-1** `app.sectors` 各模組 transitively 可達的 `app.*` 模組，必須落在白名單 `{app.sectors.*, app.data.panel, app.data.interface, app.data.calendar, app.positions.sectors}` 之內。唯一例外：`app.sectors.store` 可以 import `app.data.cache`，但只能用 `resolve_db_path`。
- **C-2** **`app.sectors` 不得可達 `app.advice`。** 也不得可達 `app.signals`、`app.backtest`、`app.directory`、`app.playbook`、`app.kelly`、`app.portfolio`、`app.alerts`、`app.api`、`app.services`、`app.data.providers`、`app.data.service`、`app.data.http`、`httpx`。
- **C-3** `app.advice`、`app.playbook`、`app.kelly`、`app.portfolio`、`app.alerts`、`app.signals` 都不得可達 `app.sectors`；族群排行不接推播與警示。
- **C-4** `app.backtest.basket` 不得 import `app.sectors`；`app.backtest.*` 都不得 import `app.sectors.store`。
- **C-5** `app.api.sectors` 的直接 import 不得包含 `app.advice`、`app.signals`、`app.backtest`、`app.data.service`、`app.services.market`、`app.portfolio`。
- **C-6** 端點零 HTTP，SQL ≤ 7 條，條數不隨族群數或個股數增加。
- **C-7** 全市場資料不寫也不讀 `price_bars_cache` 與它的兩張 log；持倉資料鏈不讀 `market_daily_bars`。
- **C-8** 市場相關三張表（`market_daily_bars`、`market_ingest_log`、`market_backfill_progress`）放在 `STOCK_DESK_MARKET_DB_PATH`；分類歷史、board、統計、核准紀錄放主 DB。
- **C-9** 新增的 store 一律設 `busy_timeout`。
- **C-10** 寫入規則為主來源優先、備援只補缺；回補一檔一個 transaction；scheduler 不觸發回補與補洞。
- **C-11** 快照的交易日不得由時鐘推定。
- **C-12** `refresh_market_data` 與 `DATA_REFRESH_LOOKBACK_DAYS` 不變。
- **C-13** 純核心只接受 `PointInTimePanel`，而它只能由 `as_of()` 建立。
- **C-14** forward return、標籤、成本扣除只存在於 `basket.py` 與 `sector_eval.py`。
- **C-15** 定義只有一處；所有結果以 `definition_version` 為鍵；API 不跨版本拼湊資料。
- **C-16** 成分股依 `(−return_5d, symbol)` 排序、取 `[0, 1, −1]`；不使用 advice 或 signals 的輸出；`app/sectors` 裡不得出現 score／rating 類識別字。
- **C-17** 報酬函式只有一處，還原方式由定義決定。
- **C-18** 門檻判定用 p_net 對 q_gross；門檻值只能比方法論 §6.3 更嚴，不能放寬。
- **C-19** `gate_status=passed` 必須有對應 `run_id` 的核准紀錄；`failed` 立即生效。
- **C-20** 降級判定只存在於 `degrade.py`。
- **C-21** `sector_rank_stats`、`sector_gate_checks`、`sector_gate_approvals`、`sector_classification_history` 只能新增列。唯一例外是分類歷史的 `superseded_on`，允許由 NULL 寫入一次。
- **C-22** `backfill_non_pit` 與 `forward_pit` 兩段分開存、分開回傳。
- **C-23** D-12 的缺口未解除也未登記接受時，`wording_tier` 必須是 `strength_only`；接受紀錄只能以程式常數登記並經 qa 審查。
- **C-24** 回應 schema 不含 `hit_rate`、`win_rate`、`score`、`rating`、`confidence`、`action`。
- **C-25** `rank1_stats` 只在卡片層級出現一次。
- **C-26** 整張 board 只有一個 `data_as_of`。
- **C-27** `demo_synthetic` 資料一律為 `not_evaluated`。
- **C-28** 使用者看得到的字面全部要經風控核可，並逐字寫死在常數與測試裡。

## 測試策略（全部離線；對應方法論 T1～T9）

- **T-1** `tests/test_sectors_boundary.py`：沿用 `import_graph`，涵蓋 C-1～C-5。
  - 列舉 `app/sectors` 下的檔案，確認每一個都被測到。
  - 驗證模組名稱都能解析，避免拼錯導致測試形同虛設。
  - 加一個 teeth test（故意違規時測試確實會紅）。
  - 掃描 advice 輸出的欄位名與 score 類識別字。
- **T-2** 零 IO：注入「任何呼叫就拋錯」的 resolver 與 transport，端點仍回 200；用 `set_trace_callback` 計算兩個 DB 合計 SQL ≤ 7，而且 10 個族群與 40 個族群時條數相同。
- **T-3** 資料鏈隔離：ingest 與回補前後，`price_bars_cache` 與兩張 log 的 checksum 不變；主 DB 裡不存在 `market_daily_bars`。
- **T-4** ingest：
  - 覆蓋率不足時不得標 `complete`；
  - 主來源優先；
  - 無法自證日期時記 `failed`；
  - 冪等；
  - 回補能從 checkpoint 續跑。
- **T-5** 未來擾動不變性：隨機取 50 個 t，把 t 之後的資料全部換成雜訊，第 t 日的輸出必須逐位元相同；`PointInTimePanel` 存取 t 之後的資料必須拋錯。
- **T-6** Shift 測試：注入洩漏時，比例必須明顯上升；延遲 1 日的結果要記錄。
- **T-7** 除權息不洩漏：兩種還原方法都要測，而且測試路徑上必須真的有除權息事件。
- **T-8** 存活者偏差與分類 point-in-time：會下市的股票必須出現在下市前的母體裡；分類在 `observed_on` 之前不得生效；缺口期間的樣本歸入 `backfill_non_pit`。
- **T-9** 線上與回測一致：同一個第 t 日，board 的輸出必須逐欄等於 `sector_eval` 的回放結果。
- **T-10** 門檻與降級：
  - G0～G7 每一項各自失敗時都要降級；
  - 用 fake clock 測 `stats_stale` 的邊界：第 20 個交易日不降級，第 21 個降級；
  - 有候選結果但沒有核准紀錄時為 `strength_only`；
  - 缺口未登記接受時恆為 `strength_only`；
  - `demo_synthetic` 為 `not_evaluated`。
- **T-11** 基準與安慰劑：B_EW 的成分等於合格母體；打亂標籤或平移訊號後，比例要落在 q 的區間內。
- **T-12** 掃描 OpenAPI schema 確認 C-24；風控定稿字面在前端與後端兩邊逐字釘住。

## Consequences（後果）

- **好處**
  - 首頁零 HTTP，滿足 PRD FR-8；持倉資料鏈與 ADR-0009、ADR-0010 都不受影響。
  - 線上與回測同一段碼、同一個版本，可以用測試證明兩者一致。
  - 資料缺口變成機器可判定的降級條件，不靠人記得。
  - 可重建的資料和不可重建的資料分開存放。
- **代價（照實計）**
  - **長期停在描述模式**：缺口未解前 `wording_tier` 恆為 `strength_only`；完全靠往前累積的話，要 5 年以上才可能評估門檻。**這是本 ADR 最大的代價，必須由 CEO 接受。**
  - **資料量**：約 260 萬列（2016 年起、約 1,000 檔、約 2,600 個交易日）。資料評估以現有 schema 估每列 300～400 B；本案的精簡 schema 應該更小，但還沒實測。
  - **回補與補洞只能在 CEO 本機用 CLI 跑**。`STOCK_DAY_ALL` 只給當日，機器關機那幾天漏掉的資料，只能靠 FinMind 逐檔補，每次約 1,000 個請求。
  - 兩個 DB 檔要分別訂備份策略；市場 DB 遺失就要重新回補。
  - API 程序和 scheduler 程序的限流沒有共享。
  - 首頁用還原後的報酬，個股頁用未還原價格，同一檔股票會看到兩個不同數字，需要揭露句。
  - 第一階段只含上市，所以「僅上市」標記常駐；上櫃的記憶體股、IC 設計股都會缺席。
  - 新增 3 個 job、約 12 張表，維運負擔增加。
- **已知限制**
  - 分類的生效日一律取觀測日，最多會晚一個觀測間隔。
  - `market_ingest_log` 的休市判定不回饋給 ADR-0009。
  - 持倉資料鏈若要改從市場面板取價，須另立 ADR。

## 與既有 ADR 的關係（§7）

- **ADR-0002**：不取代。本 ADR 把「走 `MarketDataProvider`」擴充解讀為「走 `app/data` 內可替換的抽象介面」，並新增同層的 `MarketSnapshotProvider`；另外多一個 SQLite 檔，技術棧不變。請 CEO 核可時一併裁定。
- **ADR-0009、ADR-0010**：不修訂（見 C-7、C-12）。
- **ADR-0005**：B_TAIEX／B_BH 沿用 `backup` 紀律。
- **ADR-0004、ADR-0006**：不涉及。

## 開放問題答覆（§8）

**data-engineer（依資料評估）**

| # | 題目 | 答覆 | 狀態 |
| --- | --- | --- | --- |
| DE-1 | 可指定日期的全市場端點 | `STOCK_DAY_ALL` 只給當日；TPEx 只給當日且混了非普通股；`MI_INDEX` 未驗證 | 已定案（D-3）；`MI_INDEX` **待 CEO 本機查證** |
| DE-1' | payload 是否帶交易日 | 未知 | **待 CEO 本機查證**；查證前走交叉比對 |
| DE-2 | FinMind 全市場查詢與額度 | 不依賴全市場查詢；逐檔已驗證；額度未知 | 已定案：逐檔回補；額度**待查證** |
| DE-3 | 速率界線 | 未知 | **待查證**；先沿用現有下限 |
| DE-4 | 上櫃產業別；非普通股排除 | 上櫃無來源；非普通股以 `t187ap03_L` 白名單排除 | 已定案：`twse_only` 加白名單母體 |
| DE-5 | 除權息 | 無歷史來源 | 已定案（D-4）；`Change`／`spread` 語意**待查證** |
| DE-6 | 資料量 | 估 3 年 400～550 MB | **待實測**（先灌一個月資料） |
| DE-7 | 資料公布時間 | 建議 17:00 之後 | 已定案：17:30／19:30／21:30 加日期自證；實際時間**待查證** |
| DE-8 | 已下市股票 | 無來源 | **待查證**（FinMind）；查證前依 D-12 處理 |
| DE-9 | 歷史產業分類 | 無來源 | 已定案：往前累積；是否有歷史來源**待查證** |
| DE-10 | 成本費率 | 未查證 | **待查證**；查證前附 `UNVERIFIED_RATES_NOTE` |

**quant-researcher（依方法論，全部定案；門檻只能調嚴）**

- **Q-1 母體與權重**：等權、期初等權期間持有；上市滿 60 日；20 日成交金額中位數 ≥ 1,000 萬元，且 20 日內有成交的天數 ≥ 18；族群成分股 ≥ 5 檔；排除代碼 91；代碼 20 不排名但計入 B_EW。
- **Q-2 基準**：判定一律用 B_EW；B_TAIEX 只供參考。
- **Q-3 訊號**：S_A 為主訊號；S_B 只登記用於檢定；同名次依代碼排序；上漲家數比與量能只當描述欄位。
- **Q-4 時序與統計**：t 收盤出訊號 → t+1 開盤進場 → t+5 收盤出場，樣本不重疊。統計方法用 Wilson 區間、circular block bootstrap（區塊長度 4、1 萬次、記錄 seed）、置換檢定、Holm 多重比較校正；walk-forward 為 504／126／126。
- **Q-5 門檻**：G0～G7。
- **Q-6 缺口處理**：見 D-12。
- **Q-7 q 的算法**：每週全部族群的平均，gross 與 net 各一份；主視圖要配哪一份**待風控裁定**。
- **Q-8 成本**：每個樣本扣完整一次來回成本；策略層依實際週轉計算；滑價 0／10／20 bps。
- **Q-9 回測起點**：從 2016-01-01 起，最短 5.3 年。

**其他部門**

- **product-manager**：修改 PRD FR-3 的「排名依據」與基準舉例；N 維持 3。
- **risk-compliance-officer**：
  - q 在主視圖配 q_net 還是 q_gross；
  - 覆蓋率門檻 90%／98%；
  - 「均量」是否改稱「成交金額」；
  - `backfill_non_pit` 能否露出；
  - 各缺口碼、混源、同一檔兩種價格的揭露句。
- **devops-sre**：cron 時點、兩個 DB 的備份（主 DB 必須備份）、回補與補洞的操作手冊。
- **CEO**：
  - 是否接受 D-12 的長期描述模式；
  - 是否書面接受任何缺口（依 C-23 登記）；
  - §7 對 ADR-0002 的擴充解讀。

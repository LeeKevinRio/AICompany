# ADR-0012：stock-desk 族群動能排行與全市場日線

- 狀態：accepted（CEO 2026-09-25 書面核可五項裁決事項，見派工單 §12）
- 日期：2026-09-24
- 決策者：tech-architect（草案）；CEO 核可（2026-09-25）
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
  - `work/stock-desk-族群動能-方法論.md`（quant-researcher，v1 草案第五版；D-8 的 T 對照表以其 §8.3 為準，**API 欄位命名一律以本 ADR D-10 為唯一權威**；方法論 §4 已同步改用 D-10 名稱（qa 複審 blocking，dev-lead 裁定 2026-09-24）。對照：方法論舊稱 `coverage_threshold` ＝ `sector_coverage_threshold`；`data_completeness_ratio` ＝ `coverage.completeness_ratio`（巢狀於整卡 `coverage`），顯示值 `completeness_pct_display`、門檻 `overall_coverage_threshold`；`excluded_reason` ＝ `ExcludedSector.reason_code`）
  - `work/stock-desk-族群動能-派工單.md` §4（風控預審：APPROVE_WITH_CONDITIONS；成分股技術面分數 VETO）
  - `work/stock-desk-族群動能-派工單.md` §5（風控第二次裁定：三態 `gate_status`、第一階段不列歷史比例、主視圖 q_net、成交金額倍數）
  - `work/stock-desk-族群動能-派工單.md` §6（風控逐字審：NE 原因句定稿、NR-2、§6.2 (a)(c)、§6.3 H-2 與空狀態、§6.4 `pending_review` 採用）
  - qa-reviewer 規格審查（2026-09-24，NEEDS_CHANGES；派工單 §7）
  - `work/stock-desk-族群動能-派工單.md` §8（風控裁定：整體覆蓋率只算缺漏＋可計算比例下限、`ex_dividend_exclusion` 與歸因順序、NE-1 詳細依 `pit_gaps` 條件化、T8 揭露）
  - `work/stock-desk-族群動能-派工單.md` §9（風控逐字審：可計算比例降級句、`InsufficientPanel` IP-1～IP-6）
  - `work/stock-desk-族群動能-派工單.md` §10（風控逐字審：整卡不足其餘四種原因句、同名不同義欄位分立）
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
  - v5（2026-09-24）：併入 qa 規格審查（NEEDS_CHANGES）與風控逐字審（派工單 §6）。
    - C-23／T-14 改為「不含任何歷史比例統計數值」，新增「受 `gate_status` 管制欄位總表」，明列永遠顯示的描述欄位。
    - NE-7 改為方法論 §8 T1～T9 任一未過；D-8 新增方法論 T ↔ ADR T ↔ runtime／CI 對照表；T10 不屬 NE-7。
    - 補三條機械測試：T-18（C-15 識別字掃描）、T-16（C-21 SQLite trigger，registry 有兩個「NULL→值一次」的例外）、T-17（C-24 靜態掃描）。
    - `pending_review` 改為已採用（風控 §6.4）；核准 CLI 的執行者、書面憑據、`--review-doc` 必填（C-31）。
    - NR-2：NE-8 永遠優先；卡片層級示範資料警告依 `data_source` 驅動（C-29）。
    - 同一集合 C_g(t,L)（C-32）、門檻由 API 輸出（C-33）、`held: bool | None`（C-34）、成分股 ≥ 3 不變量（C-35）。
    - 補齊缺測試的約束，新增約束 ↔ 測試對照表。
    - 明文記錄對 backtest-protocol 鐵律 3 的已知偏離，列入 CEO 核可事項。
    - 時程：使用者可見的「約 3 年」是風控定稿的簡化說法，內部下限為 3.1 年。
    - DE-5 歸類與方法論一致（NE-1）。
  - v6（2026-09-24）：併入風控裁定（派工單 §8、§9、§10）與方法論第五版。
    - 整卡可計算比例：`computable_ratio` 須 ≥ `computable_ratio_min`（暫定 0.80）；整體 98% 只算缺漏（`completeness_ratio`）（C-37）。
    - 整卡不足五碼 `insufficient_reason`，順序固定，改動須重送風控（C-42）；不足狀態的回應內容依 IP-1、IP-5、IP-6（C-43）。
    - 可計算比例降級時輸出 e、a、b、c、x：同一檔只計一次，歸屬順序為缺漏 → 除權息 → 公司行動；x 由 API 給出，為百分比、小數一位、無條件捨去（C-37）。
    - 除權息 tag 由後端判定（`ex_date_tag_ratio_min`），並輸出全市場三類排除計數（C-38）。
    - `reason_code` 新增 `ex_dividend_exclusion`，歸因順序固定、只取一個；輸出 `computable_count`、`expected_count`（C-39）。
    - `pit_gaps`：NE-1 成立 ⇔ 清單非空，矛盾時改判 NE-6；`accumulation_start` 為 null 時前端用句 2'（C-40）。
    - `HistoricalStat` 新增 `delta_real`、`delta_shuffle`（A 類受管制）；T8 沒產出這兩個數即未通過（C-41）。
    - 對齊方法論第四、五版：C_g(t,L) 由 `universe.calculation_set()` 單一函式產生；補第③類排除計數；`ci_passed_commit` 機制（C-36、T-22）；T-6～T-9、T-13、T-15 對齊 §8.2。
    - dev-lead 併入派工單 §10：`no_sector_computable` 輸出 `excluded_reason_counts`（{n1}／{n2}／{n3}）；③④⑤ 比例與門檻欄位分立、前端模板各自綁定；族群卡不得使用 `AS_OF_DATE_UNKNOWN_FULL_STATEMENT`（C-44、C-45、T-28）。
    - 同步「受 `gate_status` 管制欄位總表」與「約束 ↔ 測試對照」。

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
- 風控裁定（§8、§9、§10）：
  - 整體 98% 只算資料缺漏，另設整卡可計算比例下限（暫定 80%）；
  - 新增 `ex_dividend_exclusion` 與歸因順序；
  - NE-1 的「詳細」依 `pit_gaps` 條件化；
  - `passed`／`failed` 時揭露 T8 標籤打亂對照；
  - 整卡不足有五種原因，判斷順序固定，五種原因句皆已定稿；
  - 不足狀態下不得出現任何排名或歷史統計。

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
  - 報酬函式只有一處，在 `index.py`。算法是期初等權、期間持有：`R_g(t,L) = mean_{i∈C_g(t,L)} (P_i(t)/P_i(t−L) − 1)`。
    - E_g(t)（應計成員）：第 t 日 PIT 母體中屬於族群 g、通過證券類別、上市天數、流動性門檻的成分。有暫停交易名單時，暫停交易者移出，另計 `suspended_count`。
    - C_g(t,L)（計算集合）：E_g(t) 扣除三類排除——① 缺漏、② 窗內除權息、③ 公司行動保險。只由 `universe.calculation_set()` 這一個函式產生（方法論第五版 §2.2）。
    - **三類排除的歸屬**：同一檔同時符合多類時只計一次，歸屬順序為 ① → ② → ③（風控 §9）。族群層級與全市場層級都適用，因此 |E| − ① − ② − ③ ＝ |C|。
    - **C_g(t,L) 是族群報酬、`up_count`／`constituent_count`、成分股列示三者共用的唯一集合**（風控 §6.2 (a)，C-32）。B_EW 同理，使用 E_M(t) 與 C_M(t,L)。
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
        coverage: CoverageRules           # members >= 5, sector >= 0.90, overall completeness >= 0.98 (missing only),
                                          # computable_ratio_min 0.80 (provisional; tighten only), ex_date_tag_ratio_min 0.05 (risk §8)
        gate: GateRules                   # N >= 150, N_eff >= 60, b = max(q_gross, 0.5), effect 5pp, alpha/m
        open_limit_up_factor: float       # 1.095
    ```

  - 建構時驗證：`method_version` 字串中的 `L{n}`、`H{n}` 必須分別等於 `lookback_days`、`holding_days`；L 只能是 5 或 20。
  - **不得依任何統計結果在執行期間切換 L 或 H。** 要切換就是開新版本，依方法論 §11.2：凍結 → m 加 1 → 送風控限縮複審 → 告知 CEO。
  - **判定用 α/m**：Wilson 與 bootstrap 區間的信賴水準為 1 − 0.05/m；置換檢定門檻為 0.05/m。
  - **m 的持久化**：存在主 DB 表 `sector_method_registry`，只增不刪。主 DB 四張判定相關表都用 SQLite trigger 實作只增不刪（C-21）：

    ```sql
    -- same UPDATE/DELETE pair for sector_rank_stats, sector_gate_checks, sector_gate_approvals
    CREATE TRIGGER IF NOT EXISTS sector_rank_stats_no_update
    BEFORE UPDATE ON sector_rank_stats BEGIN SELECT RAISE(ABORT, 'append-only'); END;
    CREATE TRIGGER IF NOT EXISTS sector_rank_stats_no_delete
    BEFORE DELETE ON sector_rank_stats BEGIN SELECT RAISE(ABORT, 'append-only'); END;

    CREATE TRIGGER IF NOT EXISTS sector_method_registry_no_delete
    BEFORE DELETE ON sector_method_registry BEGIN SELECT RAISE(ABORT, 'append-only'); END;
    -- the only permitted UPDATEs: first_forward_eval_at NULL -> value once (with counts_toward_m -> 1),
    -- and accumulation_start (D0) NULL -> value once; every other column must stay identical
    CREATE TRIGGER IF NOT EXISTS sector_method_registry_update_guard
    BEFORE UPDATE ON sector_method_registry
    WHEN NOT (
        NEW.method_version IS OLD.method_version
        AND NEW.lookback_days IS OLD.lookback_days
        AND NEW.holding_days IS OLD.holding_days
        AND NEW.frozen_commit IS OLD.frozen_commit
        AND NEW.registered_at IS OLD.registered_at
        AND (NEW.accumulation_start IS OLD.accumulation_start
             OR (OLD.accumulation_start IS NULL AND NEW.accumulation_start IS NOT NULL))
        AND (NEW.first_forward_eval_at IS OLD.first_forward_eval_at
             OR (OLD.first_forward_eval_at IS NULL AND NEW.first_forward_eval_at IS NOT NULL
                 AND NEW.counts_toward_m = 1))
        AND (NEW.counts_toward_m IS OLD.counts_toward_m
             OR (OLD.first_forward_eval_at IS NULL AND NEW.first_forward_eval_at IS NOT NULL))
    )
    BEGIN SELECT RAISE(ABORT, 'append-only'); END;
    ```

    - `accumulation_start` 的例外是 v5 新增：版本登記通常早於 D0，而 D-12 規定 D0 要寫入 registry，所以需要一次 NULL→值。
    - 欄位：`method_version, lookback_days, holding_days, frozen_commit, registered_at, accumulation_start, first_forward_eval_at, counts_toward_m`。
    - 某版本第一次在 `forward_pit` 資料上算統計時，寫入 `first_forward_eval_at` 並設 `counts_toward_m=1`。看過偏誤研究後才提出的版本，同樣設 `counts_toward_m=1`。
    - m = `counts_toward_m=1` 的版本數；每列統計記錄 `m_at_evaluation`。
    - 程式判定以此表為準；`work/stock-desk-族群動能-回測紀錄.md` 是給人看的紀錄。
  - 線上與評估器共用 `universe.eligible`、`universe.calculation_set`、`index.member_returns`、`ranking.rank_sectors`、`constituents.list_constituents`、`coverage.assess`，這些函式只接受 `PointInTimePanel`。
  - `PointInTimePanel` 帶 `regime` ∈ {`pit`, `hindsight`}。`MarketPanel.as_of(t)` 只產生 `pit`：只含 `session_date ≤ t` 且 `recorded_at ≤ cutoff(t)` 的列，存取範圍外的列直接拋錯。`hindsight` 視圖只能由研究 package 建立（D-14）。
  - 分類與上市名單套用同一套可見性規則：第 t 日的族群歸屬 = `recorded_at ≤ cutoff(t)` 的最新分類快照。
  - forward return、標籤、成本扣除只存在於 `basket.py` 與 `sector_eval.py`。

- **D-7 成分股**
  - 成分股候選集合就是 D-4 的 C_g(t,L)，由 `universe.calculation_set()` 產生。族群報酬、`up_count`／`constituent_count`、成分股列示三者都從這個回傳值推導，不得各自重算。依 `(−return_L, symbol)` 排序，取位置 `[0, 1, −1]`。
  - 三類排除都不在 C_g(t,L) 內，各自計數：① → `missing_count`，② → `ex_date_excluded_count`，③ → `corporate_action_excluded_count`。同一檔只計一次，歸屬順序 ① → ② → ③。族群最小成分數（|C_g| ≥ `min_constituents`）與族群覆蓋率（|C_g| ÷ |E_g| ≥ `sector_coverage_threshold`）都把三類排除計入。
  - **族群排除的歸因順序**（風控 §8-2；取第一個成立者，不得並列），結果寫入 `reason_code`：
    0. `unranked_category`：代碼 20（其他業）。最先判定，不進入後面的歸因。
    1. `too_few_members`：結構性不足，|E_g(t)| < `min_constituents`。
    2. `low_coverage`：只扣第①類缺漏就已經不足，也就是 |E_g| − ① < `min_constituents`，或 (|E_g| − ①) ÷ |E_g| < `sector_coverage_threshold`。
    3. `ex_dividend_exclusion`：只扣①時兩項都達標，再扣②、③之後才不達標。
    - 缺漏與除權息並存、而且只看缺漏就已不足時，取 `low_coverage`。
    - 每個被排除的族群都輸出 `computable_count`（c = |C_g(t,L)|）與 `expected_count`（e = |E_g(t)|），供 `ex_dividend_exclusion` 的定稿短語代入。
  - **不變量**：有排名的族群 |C_g(t,L)| ≥ `min_constituents`（5），所以 `constituents` 恆為 3 檔；空狀態句已撤除（風控 §6.3）。計算時若發現有排名族群的 `constituents` 少於 3 檔（只可能是 bug），該族群改列 `excluded_sectors`，`reason_code='low_coverage'`，寫一筆內部紀錄 `internal_reason='constituent_invariant_violated'`（不經 API 輸出），並讓當日判定帶上 NE-6（`data_quality`）。
    - 原因碼沿用風控建議的 `low_coverage`，不另開新碼。理由：新碼需要新的風控定稿句，而這條路徑只在程式錯誤時才會出現。代價是當日該族群的「資料覆蓋率低於 {門檻}%」一句可能與實際覆蓋率不符，可追溯性由 NE-6 與內部紀錄補足。若風控認為不可接受，改開 `data_integrity` 新碼並送審字面。
  - 不產生、不儲存任何分數，不附歷史比例，不帶任何規則引擎輸出。
  - `held` 由 API 在讀取時查 positions 表得出。查詢失敗時為 None，前端不渲染持有徽章，並把「列示順序僅依近 5 日漲跌幅，不代表任何優先順序。」帶回主視圖（風控 §6.3 H-2）。

- **D-8 三態判定（依方法論第三版 §6.3）**
  - 令 `b = max(q_gross, 0.5)`。
  - **G0（前提）= NE-1～NE-8 全不成立。** 任一成立即 `not_evaluated`。D9 費率未查證（`CostModel.verified_on is None`）屬於 G0，即 NE-3。

    | # | 條件 | `not_evaluated_reason` | 判定位置 |
    | --- | --- | --- | --- |
    | NE-1 | 判定資料不是 PIT：母體缺當時已下市個股、分類不是當時分類、除權息沒有當時**可用**的紀錄，三者任一；DE-5（`change` 語意）未查證也屬此條。NE-1 成立 ⇔ `pit_gaps` 非空（D-12） | `pit_history_missing` | `sector_eval`＋`gate.py`（讀取時以同一函式重算 `pit_gaps`） |
    | NE-2 | 前瞻有效樣本 N < 150，或 N_eff < 60 | `accumulating` | `sector_eval` |
    | NE-3 | D9 費率未查證（`verified_on` 為 null） | `fee_unverified` | `gate.py`（讀取時） |
    | NE-4 | 距上次重算超過 20 個交易日 | `stale_recompute` | `gate.py`（讀取時） |
    | NE-5 | board 與統計的 `method_version` 不一致 | `version_mismatch` | `gate.py`（讀取時） |
    | NE-6 | 資料品質檢查未過（未來日期、重複、覆蓋率） | `data_quality` | `sector_eval` |
    | NE-7 | 方法論 §8 的 T1～T9 任一未通過（判定依據：runtime 實跑項目，加上部署版本的 CI 門結果，見下方對照表；T10 不屬此條） | `lookahead_tests_failed` | `sector_eval`＋`gate.py`（讀取時比對 commit） |
    | NE-8 | 資料為 `demo_synthetic` | `demo_data` | `sector_eval` |

    - **`not_evaluated_reason` 的選取規則**：資料來源為 `demo_synthetic` 時一律為 `demo_data`（NE-8 永遠優先，排除「取編號最小者」規則，風控 §6.1 NR-2）；其他情況取成立者中編號最小的一項；`pending_review` 排最後。`not_evaluated_reasons` 列出全部成立者。前端依 `not_evaluated_reason` 選用風控 §6.1 的定稿句。
    - **NE-7 ＝ 方法論 §8 的 T1～T9 任一未通過**（dev-lead 裁定以方法論為準；T10 不屬 NE-7，由 CI 與 D-14 的結構防線處理）。
      - 「通過」須同時滿足：runtime 項目在本次判定中於真實前瞻資料上實跑並通過；CI 項目在目前部署的 commit 上為綠燈（`ci_passed_commit` 與部署 commit 比對不符即 NE-7）。
      - runtime 狀態 `skipped_insufficient_n` 只允許在 N < 30（NE-2 期間）；N ≥ 150 後 skip 一律視為未通過。前瞻期沒有下市或改類事件時，T5／T6 runtime 記為 `vacuous`，由 CI 覆蓋並揭露。
      - 只能在合成資料上驗證的項目列為 CI 門：沒過不得合併、不得部署；以部署版本的 commit 為憑，執行期不重跑。
      - 執行期結果寫入 `sector_gate_checks`（`check_kind='selfcheck'`，含 seed 與數值，只增不刪），不經 API 輸出。狀態只有 `pass`、`fail`、`skipped_insufficient_n`、`vacuous` 四種（C-36）。
      - **`ci_passed_commit` 機制**：
        - **build 階段**：`scripts/attest_sector_gate.py` 只在乾淨工作樹（`git status --porcelain` 為空）上執行 NE-7 的 CI 測試集合（pytest marker `sector_ne7`：T-5～T-9、T-13 的 CI 半部，加上 T-15）。全綠才寫 `app/_build/ci_attestation.json`，內容為 `ci_passed_commit`、`suite_hash`（測試檔清單與內容的 SHA-256）、`passed_at`；未全綠則刪除舊檔。此檔列入 `.gitignore`。
        - **判定時**（scheduler 程序的 `services.sector_board`）：`running_commit = git rev-parse HEAD`。以下任一情況即為 NE-7：工作樹不乾淨、讀不到 git、缺 attestation、`running_commit != ci_passed_commit`、`suite_hash` 不符。`running_commit` 寫入該次統計列。
        - **讀取時**（`gate.py`）：輸入由 services 層在程序啟動時讀好後傳入，符合 C-24。`stats.running_commit` 與目前部署的 `ci_passed_commit` 不符即為 NE-7。
        - 這是本機的自我證明，不是外部 CI 簽章；執行期不查 GitHub。
        - **部署期間的預期行為**（qa 複審 medium）：API 程序與 scheduler 程序切換到新 commit 的時點不同時，讀取端會因 `stats.running_commit` 與部署的 `ci_passed_commit` 不符而短暫判為 NE-7，直到 scheduler 以新 commit 重新判定為止。這是預期行為、不是故障，不發告警；本機部署腳本應同時重啟兩個程序並在啟動後立即補跑一次判定（D-5）以縮短此窗口。交 devops-sre 納入部署手冊。
        - T-1～T-4、T-10～T-12、T-14、T-16～T-21、T-23～T-28 屬合併門，不屬 NE-7，也不進 attestation 集合。

      | 方法論 | ADR 測試 | runtime（真實資料，每次判定） | CI（合成資料，合併門） |
      | --- | --- | --- | --- |
      | T1 未來擾動不變性 | T-5 | 是：隨機 50 個決策日，把 `recorded_at > cutoff(t)` 的所有列換成雜訊，逐位元比對 | 是：另測 `PointInTimePanel` 越界時拋錯 |
      | T2 向量化與逐日一致 | T-15 | v1 不適用：評估器與線上排行呼叫同一個函式物件 | 是：結構斷言同一函式物件、沒有第二份實作；日後引入向量化時，逐列相等測試須在 CI 與 runtime 同批落地 |
      | T3a 注入洩漏的正向對照 | T-6 | 是：以 t+H 收盤注入洩漏，比例必須大幅上升；真實訊號若已接近洩漏版，判為疑似洩漏 | 是：閾值 δ_leak 以合成資料校準後凍結於版本 |
      | T3b 延遲 1 日 | T-6 | 是：只看是否執行並記錄，不以結果構成 NE-7 失敗 | 是 |
      | T4 除權息不洩漏 | T-7 | 是：前瞻段含至少一筆除權息事件時實跑；尚無事件時記 `vacuous` 並以 CI 為準 | 是：測試路徑上必須有事件 |
      | T5 存活者偏差 | T-8 | 是：第 t 日母體等於第 t 日可見的名單快照，不是最新的 directory；無下市事件時 `vacuous` | 是：合成一檔 t+k 下市的股票 |
      | T6 分類 PIT | T-8 | 是：第 t 日族群歸屬等於 `recorded_at ≤ cutoff(t)` 的最新分類快照；無改類事件時 `vacuous` | 是：合成一檔 t+k 改類的股票；無例外 |
      | T7 基準一致 | T-13 | 是：B_EW 成分等於同日合格母體 | 是 |
      | T8 安慰劑 | T-13 | 是：判定用「時間平移」安慰劑，\|Δ 中位數\| < 2.5pp；N < 30 時記 `skipped_insufficient_n`。「打亂產業標籤」只作診斷、不列 gate，但**必須產出** `delta_shuffle` 與 `delta_real` 並寫入統計列；沒有產出即為 T8 未通過（方法論第五版 §8.3）。兩數也是 `pending_review` 首次轉態複審的必審項（風控 §8-4 T8-3） | 是：teeth test（刻意漏算成本、刻意偏袒小族群時必須失敗） |
      | T9 線上與判定一致＋同一集合 | T-9 | 是：board 第 t 日結果逐欄等於 `sector_eval` 回放；族群報酬、`up_count`、成分股三者集合相等 | 是 |
      | T10 偏誤版隔離 | T-10 | 不屬 NE-7；`SectorStatsRepository` 的拒收在執行期恆生效（fail-closed） | 是：import 邊界、字串掃描 |

    - **NE-7 的 runtime 清單 = T-5、T-6、T-7、T-8、T-9、T-13**（T-13 含時間平移安慰劑）；T-10 不在清單內，runtime 只做 fail-closed。
    - 本對照表與 quant-researcher 方法論第五版 §8.3 一致；日後不一致時以方法論為準，並回頭修訂本表。
  - **`failed`**：G0 成立、統計已算出，但 G1～G6 有任一不成立：
    - G1：N ≥ 150 且 N_eff ≥ 60。
    - G2：Wilson 與 block bootstrap 的下界都 > b，信賴水準 1 − 0.05/m。
    - G3：p_net − b ≥ 5pp。
    - G4：置換檢定 p < 0.05/m，且扣成本後的平均超額 > 0。
    - G5：分段看、各相位看、剔除最常出現的族群後看，p_net 都 > b。
    - G6：最近 12 個月的 p_net > b。
  - **`passed`**：G0 成立，而且 G1～G6 全過。
  - **轉態與核准**：核准紀錄存在主 DB 的 `sector_gate_approvals`（只增不刪，C-21），只能用 CLI 寫入：`python -m app.services.sector_board approve --kind {first_transition_risk|quarterly_qa} --run-id ... --operator {ceo|dev-lead} --reviewer ... --review-doc <path>`。
    - **`pending_review`（已採用，風控 §6.4）**：
      - 每個 `method_version` 第一次離開 `not_evaluated` 時，不論候選結果是 `passed` 還是 `failed`，都先進入 `pending_review`。
      - 進入條件：NE-1～NE-8 全不成立（NE-8 永遠優先）。
      - 期間 `gate_status='not_evaluated'`、`not_evaluated_reason='pending_review'`，`historical_stat`、`gate_checks` 皆為 None；候選 gate 結果不以任何欄位、任何形式傳出 API。
      - 要有 `kind='first_transition_risk'` 紀錄才會離開。
    - `passed` → `failed`：自動、立即。
    - `failed` → `passed`：需要同一 `run_id` 的 `kind='quarterly_qa'` 紀錄；沒有就維持 `failed`。
    - **CLI 執行者與書面憑據（C-31）**：
      - `first_transition_risk`：由 CEO 或 dev-lead 執行，前提是 risk-compliance-officer 已出具**書面 APPROVE**。風控複審資料包必須附上 `delta_shuffle`、`delta_real` 及其 bootstrap 區間（T8-3）。若 Δ_shuffle ≥ Δ_real 的一半，風控保留要求主視圖加註或更名的權利；Δ_real ≤ 0 時照實寫明（方法論第五版 §8.4）。
      - `quarterly_qa`：由 dev-lead 執行，前提是 qa-reviewer 已出具**書面確認**。
      - `--operator`、`--reviewer`、`--review-doc` 都必填。CLI 會驗證審查文件存在於 repo 內、內文含該 `run_id` 與 `method_version`，並把文件路徑與 git blob hash 寫進核准列。
      - 除 CEO 與 dev-lead 依上述書面憑據執行外，唯讀職能（qa-reviewer、risk-compliance-officer）與其他任何 agent 都不得代寫；沒有書面憑據時，任何人都不得寫入。
      - CLI 的 operator 與文件檢查只是減速帶，不是強制機制（與 ADR-0007 揭露的現況一致）。這條規則的效力來自規範與審查，違反即違規。
  - 有效的 `gate_status` 只在 `app/sectors/gate.py` 一處組合，來源是：`sector_eval` 的候選結果、讀取時算出的 NE-3／4／5、核准紀錄。前端只依 `gate_status` 與 `not_evaluated_reason` 選用風控核可字面，**不得**自行由數字推導；`not_evaluated` 時不得使用「未達門檻」句。
  - **整卡 `insufficient_data`**：依下列順序判斷，取第一個成立者寫入 `insufficient_reason`（風控 §9 IP-3；順序寫入 C-42，調整須重送風控）：
    1. `as_of_unknown`：`data_as_of` 未知，包括沒有任何 board。
    2. `ex_dividend_feed_gap`：`TWT48U_ALL` 的 `ok` run 沒涵蓋最近 L 個交易日。
    3. `overall_completeness_low`：整體資料完整率 `completeness_ratio` < `overall_coverage_threshold`（0.98）。完整率指全體應計成員 E_M(t) 中只扣第①類缺漏後的比例（風控 §8-1）。
    4. `computable_ratio_low`：整卡可計算比例 `computable_ratio`（= |C_M(t,L)| ÷ |E_M(t)|）< `computable_ratio_min`。暫定 0.80，最終值依方法論第五版 §2.3 的事先登記規則提出，只可調嚴、不得低於 0.80。
    5. `no_sector_computable`：沒有任何族群可以列入排行（PRD FR-6-4）。
    - 五種原因各用各的原因句（IP-4），皆已由風控定稿：④ 見派工單 §9，①②③⑤ 見 §10。① 為本卡獨立常數，**不得**使用個股頁的 `AS_OF_DATE_UNKNOWN_FULL_STATEMENT`（§10 更正 §4.5-4，C-45）。
    - ③④⑤ 的比例與門檻同名不同義（③ `completeness_ratio`／`overall_coverage_threshold`，④ `computable_ratio`／`computable_ratio_min`，⑤ `sector_coverage_threshold`），前端模板各自綁定對應欄位，不得共用變數（C-44）。
    - 不足狀態下回應的內容見 D-10 與 C-43（IP-1、IP-5、IP-6）。

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
      "pending_review",           # D-8 first transition (adopted, risk §6.4)
  ]

  class Accumulation(BaseModel):          # always present; feeds 「目前已累積 {n} 個」
      accumulated_samples: int
      accumulation_start: str | None      # D0; None before D0 -> front end uses risk sentence 2' (派工單 §8-3)
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
      delta_real: float                   # p_net - q_net, percentage points, net of cost (risk §8-4 T8-2)
      delta_shuffle: float                # mean over label shuffles of (p_net - q_net), percentage points; diagnostic, not a gate
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

  class Coverage(BaseModel):              # counts attribute each name once: missing -> ex-date -> corporate action
      expected_count: int                 # |E|: eligible members (suspended removed only when a list exists)
      calculation_count: int              # |C| == expected - missing - ex_date - corporate_action
      missing_count: int                  # category 1
      ex_date_excluded_count: int         # category 2
      corporate_action_excluded_count: int  # category 3
      suspended_count: int | None         # None: no suspension-list source; suspended names counted as missing
      coverage_ratio: float | None        # sector: |C| / |E| (all three categories count)
      completeness_ratio: float | None    # card: 1 - missing / |E| (category 1 only; risk §8-1)

  class ConstituentItem(BaseModel):
      symbol: str
      name: str
      return_L: float | None              # signed; no rank-number field
      held: bool | None                   # None when the positions lookup failed; front end renders no badge (risk §6.3 H-2)

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
      reason_code: Literal["unranked_category", "too_few_members", "low_coverage", "ex_dividend_exclusion"]
      computable_count: int               # c = |C_g(t,L)|
      expected_count: int                 # e = |E_g(t)|
      coverage: Coverage

  PitGap = Literal["pit_universe", "pit_classification", "pit_ex_dividend", "de5_unverified"]  # fixed order
  InsufficientReason = Literal[           # fixed evaluation order (C-42); first match wins
      "as_of_unknown",
      "ex_dividend_feed_gap",
      "overall_completeness_low",
      "computable_ratio_low",
      "no_sector_computable",
  ]

  class ExcludedReasonCounts(BaseModel):  # {n1}/{n2}/{n3} for no_sector_computable (派工單 §10); sum == ranked-eligible sectors
      too_few_members: int
      low_coverage: int
      ex_dividend_exclusion: int

  class SectorMomentumResponse(BaseModel):
      market: str
      status: PayloadStatus
      insufficient_reason: InsufficientReason | None   # non-null iff status == "insufficient_data" (IP-1, C-42)
      reason: str | None
      method_version: str | None
      lookback_days: int | None
      holding_days: int | None
      data_as_of: str | None              # one date for the whole board; still output when insufficient (IP-6)
      market_scope: Literal["twse_only"]  # drives 「僅上市」 tag
      benchmark: Literal["equal_weight_market"]
      data_source: str                    # e.g. "twse_snapshot" | "demo_synthetic"; drives the NE-8 card-level warning (IP-6)
      coverage: Coverage | None
      min_constituents: int               # same constant object the gate uses (definition.coverage)
      sector_coverage_threshold: float    # same constant object the gate uses (0.90)
      overall_coverage_threshold: float   # same constant object the gate uses (0.98, completeness)
      computable_ratio: float | None      # |C_M(t,L)| / |E_M(t)|, raw value used by the gate
      computable_ratio_min: float         # same constant object the gate uses (0.80 provisional)
      computable_ratio_pct_display: float | None  # {x} of reason ④: computable_ratio * 100 floored to one decimal (risk §9)
      completeness_pct_display: float | None      # {x} of reason ③: completeness_ratio * 100 floored to one decimal (risk §10)
      market_expected_count: int | None           # {e}
      market_missing_count: int | None            # {a}
      market_ex_date_excluded_count: int | None   # {b}; also {m} of the ex-date tag
      market_corporate_action_excluded_count: int | None  # {c} in risk §9 (not the per-sector computable_count)
      market_ex_date_excluded_ratio: float | None # {b} / {e}
      ex_date_tag_ratio_min: float                # same constant object (0.05)
      ex_date_tag: bool                   # ratio >= ex_date_tag_ratio_min, or any sector excluded as ex_dividend_exclusion
      excluded_reason_counts: ExcludedReasonCounts | None  # {n1}/{n2}/{n3}; non-null iff insufficient_reason == "no_sector_computable"
      headline_count: int
      sectors: list[SectorItem]           # full ranking incl. tail; [] when insufficient (IP-5)
      excluded_sectors: list[ExcludedSector]  # [] when insufficient (IP-5)
      gate_status: GateStatus
      not_evaluated_reason: NotEvaluatedReason | None     # demo_data first, else lowest NE-1..NE-7, pending_review last; None unless not_evaluated
      not_evaluated_reasons: list[NotEvaluatedReason]     # all reasons; [] unless not_evaluated
      pit_gaps: list[PitGap]                              # non-empty iff NE-1 holds; fixed order; [] otherwise
      accumulation: Accumulation
      historical_stat: HistoricalStat | None              # MUST be None when not_evaluated (incl. pending_review) or insufficient_data (IP-5)
      gate_checks: list[GateCheck] | None                 # MUST be None when not_evaluated (incl. pending_review) or insufficient_data (IP-5)
      fee_verified_on: str | None
      disclosures: list[str]              # risk-approved, always rendered
      data: DataMeta                      # reused unchanged
      as_of: str                          # response production time (company convention)
  ```

  - 比例由前端計算。主視圖顯示 `beat_count_net / sample_count` 對 `base_rate_net`，兩者都已扣來回成本。「詳細」列出 p_gross、q_gross、p_net、q_net 四個數字並標明口徑。**p_net 與 q_gross 不得並排。**
  - `historical_stat` 只取 `data_regime='forward_pit'` 的統計；`backfill_non_pit`（偏誤研究）不經 API（D-14）。
  - 分名次統計只放研究報告，不進 API（方法論 §6.1）。
  - 回應 schema 的欄位名不得含 `volume`、`hit_rate`、`win_rate`、`score`、`rating`、`confidence`、`action`。
  - **受 `gate_status` 管制欄位總表**：

    | 類別 | 欄位 | `not_evaluated`（含 `pending_review`） | `failed` | `passed` |
    | --- | --- | --- | --- | --- |
    | A. 歷史比例統計（受管制） | `historical_stat` 整個物件：`beat_count_net`、`beat_count_gross`、`sample_count`、`effective_sample_count`、`base_rate_net`、`base_rate_gross`、`ci_low_net`、`ci_high_net`、`bootstrap_low_net`、`bootstrap_high_net`、`delta_real`、`delta_shuffle`、`m_at_evaluation`、`sample_start`、`sample_end`、`stats_as_of` | None | 有值（「詳細」照實列出，並附 T8-1、T8-2） | 有值（「詳細」附 T8-1、T8-2） |
    | A. 門檻明細（受管制） | `gate_checks` | None | 有值 | 有值 |
    | A. 候選判定結果（永不輸出） | `sector_eval` 的候選 gate 結果 | 不存在於 API | 不存在於 API | 不存在於 API |
    | B. 判定狀態（永遠輸出） | `gate_status`、`not_evaluated_reason`、`not_evaluated_reasons`、`pit_gaps`、`accumulation`（只有 n、起算日、需求數）、`fee_verified_on` | 輸出（NE-1 時 `pit_gaps` 非空） | 輸出（原因為 None／[]，`pit_gaps` 為 []） | 輸出（同左） |
    | C. 描述欄位（不受 gate 管制，永遠輸出） | `sector_return_L`、`benchmark_return_L`、`rel_return_L`、`up_count`、`constituent_count`、`coverage`（含 `calculation_count`、三類排除計數、`coverage_ratio`、`completeness_ratio`）、`turnover_value_ratio_5_20`、`reference_taiex_return_L`、`top_contributor_share`、`single_stock_dominated`、`constituents`、`excluded_sectors`（含 `reason_code`、`computable_count`、`expected_count`）、`min_constituents`、`sector_coverage_threshold`、`overall_coverage_threshold`、`computable_ratio`、`computable_ratio_min`、`computable_ratio_pct_display`、`completeness_pct_display`、`market_expected_count`、`market_missing_count`、`market_ex_date_excluded_count`、`market_corporate_action_excluded_count`、`market_ex_date_excluded_ratio`、`ex_date_tag_ratio_min`、`ex_date_tag`、`excluded_reason_counts`、`insufficient_reason`、`data_source`、`data` | 輸出 | 輸出 | 輸出 |

    - A 類在 `not_evaluated` 時是整個物件為 None，不是個別欄位為 null。B、C 類不因 `gate_status` 改變。
    - `turnover_value_ratio_5_20`、`reference_taiex_return_L` 只放「詳細」，這是呈現規則，不是 gate 管制。
    - `ex_date_tag` 為 true 時，主視圖常駐定稿 tag「除權息排除 {m} 檔」，{m} = `market_ex_date_excluded_count`；「詳細」列出全市場三類排除檔數（風控 §8-1 C1-2、C1-3）。前端不得自行判斷是否顯示 tag。
    - `pit_gaps` 驅動 NE-1 詳細句 G 的缺口清單，依固定順序以「、」串接，前端不得推導（風控 §8-3）。
    - **不足狀態**（`status == "insufficient_data"`，C-43）：
      - `sectors`、`excluded_sectors` 為 []，`historical_stat`、`gate_checks` 為 None（IP-5）。
      - `data_as_of`、`data_source`、`data`（DataMeta）、`insufficient_reason`、e／a／b／c／x 相關欄位、`excluded_reason_counts` 照常輸出（IP-6）；資料不可得時為 None。
      - `insufficient_reason` 必為非 null，前端依它傳入非 null 的原因句（IP-1）。
      - B 類欄位照常輸出供紀錄，但前端不得渲染任何 NE 句、歷史句、排名、族群名稱或成分股（IP-5）。
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
    - API 一律帶 `accumulation`，供風控定稿句「目前已累積 {n} 個」使用。`accumulation_start` 為 null（尚未到 D0）時，前端改用句 2'（派工單 §8-3）。`historical_stat` 與 `gate_checks` 皆為 null。
    - **`pit_gaps`**（風控 §8-3；方法論第五版 §6.3）：由 `app/sectors/gate.py` 的單一函式 `pit_gaps(pit_status, de5_verified_on, window)` 計算，判定端與讀取端共用。
      - 輸入：`pit_status` 由 services 層從 `pit_snapshot_runs` 一次查詢彙總後傳入，不增加 C-6 的 SQL 上限；`de5_verified_on` 取自 `app/data/providers/twse_snapshot.py::CHANGE_SEMANTICS_VERIFIED_ON`，由 services 傳入，符合 C-1、C-24。
      - 各項成立條件：
        - `pit_universe`：判定期間內，有任一決策日沒有有效的上市名單快照。缺漏後沿用前一份、且在 5 個交易日內，仍算有效。尚未有 D0 時必定成立。
        - `pit_classification`：同上，對象換成分類快照。
        - `pit_ex_dividend`：同上，對象換成 `TWT48U_ALL` 快照。
        - `de5_unverified`：`de5_verified_on is None`。
      - 輸出順序固定為上列順序。
      - NE-1 成立 ⇔ 清單非空。若判出 NE-1 但清單為空，改判 NE-6（`data_quality`）並寫錯誤紀錄，不得輸出「NE-1 但沒有缺口」的狀態。
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
  - **預期時程：內部下限約 3.1 年**（N ≥ 150，每年約 49 個不重疊的 5 日樣本）。使用者可見句寫「約需 3 年」，是風控定稿（派工單 §5-4）的簡化說法，兩者不矛盾；工程與規格文件一律用 3.1 年下限。v3 的較長估計作廢，理由如下：
    - 方法論規定參數在 D0 前凍結並 commit。前瞻段是凍結之後才產生的，沒有任何參數用它擬合過，所以整段都算樣本外。walk-forward 的 504 日訓練窗在這裡沒有擬合用途，只保留每 126 日一段的測試窗幾何作分段報告，因此不需要從前瞻段扣掉訓練窗。這是對 backtest-protocol 鐵律 3 的已知偏離，見 Consequences。
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
- **C-15** forward return、標籤、成本扣除只存在於 `basket.py` 與 `sector_eval.py`；研究 package 內的複本受 C-27 隔離。機械檢查：識別字 `forward_return*`、`excess_gross`、`excess_net`、`label_return*`、`round_trip_cost` 只能在 `app/backtest/basket.py`、`app/backtest/sector_eval.py`、`app/research/**` 定義。既有的 `app/backtest/event_study.py::forward_returns` 列入白名單：它在 v4 之前就存在，且 C-2 已保證 `app.sectors` 碰不到它（T-18）。
- **C-16** 定義只有一處；`method_version` 必須與 `lookback_days`、`holding_days` 一致；L ∈ {5, 20}；API 不跨版本配對；切換版本須寫入 `sector_method_registry`。
- **C-17** 成分股依 `(−return_L, symbol)` 排序，取 `[0, 1, −1]`；不使用 advice 或 signals 的輸出；`app/sectors` 內不得出現 score／rating 類識別字。
- **C-18** 報酬函式只有一處；回看窗排除窗內有除權息的成分股；`TWT48U_ALL` 沒涵蓋最近 L 日時，整卡回 `insufficient_data`。
- **C-19** 判定用 p_net 對 `b = max(q_gross, 0.5)`、效果量 ≥ 5pp、信賴水準 1 − 0.05/m，門檻只能調嚴；主視圖呈現 p_net 對 q_net；p_net 與 q_gross 不得並排。
- **C-20** 有效 `gate_status` 只在 `app/sectors/gate.py` 組合；核准紀錄只增不刪。
- **C-21** 主 DB 的 `sector_rank_stats`、`sector_gate_checks`、`sector_gate_approvals`、`sector_method_registry` 只能新增列。實作方式是 SQLite trigger（`BEFORE UPDATE`／`BEFORE DELETE` 一律 `RAISE(ABORT)`，SQL 見 D-6），store 也不提供 UPDATE／DELETE 方法。唯一例外在 `sector_method_registry`：`first_forward_eval_at`（同時 `counts_toward_m` 改為 1）與 `accumulation_start` 各允許一次由 NULL 寫入值，其餘欄位必須不變（T-16）。
- **C-22** `backfill_non_pit` 與 `forward_pit` 分開存：前者只在研究 DB，後者在主 DB；API 只回 `forward_pit`。
- **C-23** `gate_status == "not_evaluated"`（含 `pending_review`）時，回應不含任何歷史比例統計數值：`historical_stat is None`、`gate_checks is None`。因此 `beat_count_*`、`sample_count`、`effective_sample_count`、`base_rate_*`（p／q 的 gross／net）、`ci_*`、`bootstrap_*`、`m_at_evaluation` 都不會出現在回應的任何位置；候選 gate 結果在任何狀態下都不輸出。D-10「受 `gate_status` 管制欄位總表」的 C 類描述欄位不受 gate 管制，永遠輸出（T-14）。
- **C-24** 程式中不存在任何可以繞過 NE-1～NE-8 的開關、清單或環境變數。機械檢查：`app/sectors/gate.py`、`app/sectors/coverage.py`、`app/backtest/sector_eval.py` 不得使用 `os.environ`、`os.getenv`、`getenv`，不得 import `os`、`dotenv`、`configparser`、`tomllib`、`yaml`、`app.settings`；`gate.py` 另不得 import `sqlite3`，只吃 store 讀好的列。判定結果只能由三樣東西決定：NE 條件、統計列、核准列（T-17）。
- **C-25** `CostModel.verified_on is None` 時，NE-3 必定成立，`gate_status` 必為 `not_evaluated`。
- **C-26** `turnover_value_ratio_5_20` 不得作為 `rank_sectors` 的輸入，只放「詳細」；回應 schema 欄位名不得含 `volume`、`hit_rate`、`win_rate`、`score`、`rating`、`confidence`、`action`。禁用字掃描以子字串比對，唯一白名單複合詞為 `corporate_action`（D-10 自己定義的第③類「公司行動」排除計數，與規則引擎的 `action` 無關；dev-lead 施工裁定 2026-09-25）。
- **C-27** 除 `app.research` 自身外，任何 `app.*` 模組都不得可達 `app.research`；字串 `STOCK_DESK_RESEARCH_DB_PATH` 只出現在 `app/research/` 與 tests；`hindsight_view` 只在 `app/research/` 內定義與呼叫；`SectorStatsRepository` 拒收非 PIT 紀錄。
- **C-28** `rank` 只在族群層級；`historical_stat` 只在卡片層級出現一次；整張 board 只有一個 `data_as_of`。
- **C-29** `demo_synthetic` 資料必定觸發 NE-8，且 `not_evaluated_reason` 必為 `demo_data`（NE-8 永遠優先，風控 §6.1 NR-2）。卡片層級的示範資料警告由 `data_source` 驅動，不受 `gate_status` 影響，屬絕對底線（T-11、T-14）。
- **C-30** 使用者看得到的字面全部要經風控核可，並逐字寫死在常數與測試裡；`not_evaluated` 時不得使用「未達門檻」句。
- **C-31** 核准列只能由 CLI 寫入。
  - `first_transition_risk`：由 CEO 或 dev-lead 依風控書面 APPROVE 執行。
  - `quarterly_qa`：由 dev-lead 依 qa-reviewer 書面確認執行。
  - `--operator`（`ceo`／`dev-lead`）、`--reviewer`、`--review-doc` 必填。CLI 驗證審查文件存在、內文含該 `run_id` 與 `method_version`，並記錄文件路徑與 git blob hash。
  - 唯讀職能與其他 agent 不得代寫；沒有書面憑據時任何人都不得寫入（T-19）。
- **C-32** C_g(t,L) 只由 `universe.calculation_set()` 產生。族群報酬、`up_count`／`constituent_count`、成分股列示三者都從它的回傳值推導，不得各自重算。三類排除（缺漏、窗內除權息、公司行動保險）同一檔只計一次，歸屬順序 ① → ② → ③，並計入族群覆蓋率與最小成分數判定（T-9、T-15、T-20）。
- **C-33** API 輸出 `min_constituents`、`sector_coverage_threshold`、`overall_coverage_threshold`、`computable_ratio_min`、`ex_date_tag_ratio_min`，值直接取自 `SectorMomentumDefinition.coverage`，與 gate 用同一個常數物件。每個族群輸出實際的 `coverage.coverage_ratio`，整卡輸出 `completeness_ratio` 與 `computable_ratio`。前端不得寫死這些數字（T-20、T-23、T-24）。
- **C-34** `held` 型別為 `bool | None`：持倉查詢成功才是 bool，失敗為 None。為 None 時前端不渲染徽章，並把「列示順序」句帶回主視圖（T-20）。
- **C-35** 有排名的族群，`constituents` 恆為 3 檔（|C_g(t,L)| ≥ `min_constituents`）。不變量破壞時，該族群改列 `excluded_sectors`（`reason_code='low_coverage'`），當日判定帶 NE-6，並寫錯誤紀錄（T-20）。
- **C-36** NE-7 的「通過」＝ runtime 項目本次實跑通過，且 `running_commit == ci_passed_commit`（工作樹乾淨、`suite_hash` 相符）。讀取時，`stats.running_commit` 與目前部署的 `ci_passed_commit` 不符即為 NE-7。runtime 狀態只允許四種：
  - `pass`、`fail`；
  - `skipped_insufficient_n`：限 T3a、T8，且只在 N < 30；
  - `vacuous`：限 T4 ③、T5、T6。
  N ≥ 150 之後出現 `skipped_insufficient_n` 視同 `fail`；T8 沒產出 `delta_shuffle`、`delta_real` 也視同 `fail`（T-22）。
- **C-37** 整卡可計算比例 `computable_ratio` = |C_M(t,L)| ÷ |E_M(t)| 低於 `computable_ratio_min` 時，整卡為 `insufficient_data`，原因碼 `computable_ratio_low`。整體 98% 門檻只看 `completeness_ratio`（只扣缺漏）。
  - API 輸出：e（`market_expected_count`）、a（`market_missing_count`）、b（`market_ex_date_excluded_count`）、c（`market_corporate_action_excluded_count`）、x（`computable_ratio_pct_display`）。
  - 同一檔只計一次，歸屬順序缺漏 → 除權息 → 公司行動，因此 e − a − b − c ＝ |C_M|。
  - **x 由 API 處理**：百分比、小數一位、無條件捨去（`math.floor(ratio * 1000) / 10`）；前端直接顯示，不得再四捨五入（T-23）。`completeness_pct_display` 同一規則。
- **C-38** `ex_date_tag` 只由後端計算。成立條件任一即可：全市場除權息排除比例 `market_ex_date_excluded_ratio` ≥ `ex_date_tag_ratio_min`，或本次有任一族群 `reason_code` 為 `ex_dividend_exclusion`。前端不得自行判斷（T-24）。
- **C-39** 族群排除原因只取一個，依序為 `unranked_category` → `too_few_members` → `low_coverage` → `ex_dividend_exclusion`，取第一個成立者，不得並列。每個被排除族群輸出 `computable_count`、`expected_count`（T-20）。
- **C-40** `pit_gaps` 只由 `gate.pit_gaps()` 計算，順序固定。NE-1 成立 ⇔ 清單非空；判出 NE-1 但清單為空時改判 NE-6。前端不得推導（T-25）。
- **C-41** `delta_real`、`delta_shuffle` 屬 A 類受管制欄位：`not_evaluated` 與 `insufficient_data` 時不出現；`passed`／`failed` 時有值，「詳細」附 T8-1、T8-2 定稿句。標籤打亂不影響 `gate_status`（T-26）。
- **C-42** 整卡不足的判斷順序固定為 `as_of_unknown` → `ex_dividend_feed_gap` → `overall_completeness_low` → `computable_ratio_low` → `no_sector_computable`，取第一個成立者。`status == "insufficient_data"` 時 `insufficient_reason` 必為非 null。**調整順序須重送風控**（風控 §9 IP-3）（T-27）。
- **C-43** 不足狀態下，`sectors == []`、`excluded_sectors == []`、`historical_stat is None`、`gate_checks is None`（IP-5）；`data_as_of`、`data_source`、`data` 照常輸出（IP-6）。前端不得渲染任何排名、族群名稱、成分股、NE 句或歷史句，只渲染該原因的定稿句、三類排除檔數與 IP-6 常駐項。傳給 `InsufficientPanel` 的 reason 不得為 null（IP-1）（T-27）。
- **C-44** ③④⑤ 的 {x}／{門檻} 同名不同義，API 分立欄位：③ `completeness_pct_display`／`overall_coverage_threshold`、④ `computable_ratio_pct_display`／`computable_ratio_min`、⑤ `sector_coverage_threshold`。前端每個原因句模板只綁定自己的欄位，不得共用變數；{a}、{e} 在 ③④ 同名同義，取自同一欄位。⑤ 的 {n1}／{n2}／{n3} 取自 `excluded_reason_counts`，依 C-39 歸因順序計數，三者相加等於可排名族群總數（派工單 §10）（T-28）。
- **C-45** 族群卡不得使用個股頁常數 `AS_OF_DATE_UNKNOWN_FULL_STATEMENT`；① `as_of_unknown` 用本卡獨立常數（派工單 §10 定稿）。交易日曆無法確認時沿用 `AS_OF_CALENDAR_UNCONFIRMED_STATEMENT` 維持（T-28）。

## 測試策略（全部離線；對應方法論 §8 T1～T10）

- **T-1** `tests/test_sectors_boundary.py`：沿用 `import_graph`，涵蓋 C-1～C-5。
  - 列舉 `app/sectors` 下的每一個檔案，確認都在守門清單內。
  - 驗證模組名稱都能解析，避免拼錯導致測試形同虛設。
  - 加一個 teeth test（故意違規時，測試確實會失敗）。
  - C-2 的 `httpx`：掃描 `app/sectors/**` 的 `import httpx`／`from httpx`，含 `importlib` 或字串 `"httpx"` 形式的動態 import，並附 teeth test。
  - C-17 原始碼掃描：`app/sectors/**` 的識別字、屬性、字串常數不得含 `score`、`rating`、`AdviceCard`、`matched_rules`、`direction_weights`、`ACTION_DIRECTION`（比照 `test_playbook_boundary.py::_identifiers`）。
- **T-2** 零 IO：注入「任何呼叫都拋錯」的 resolver 與 transport，端點仍回 200；以 `set_trace_callback` 計算兩個 DB 合計的 SQL 條數 ≤ 7，而且 10 個與 40 個族群時條數相同。
- **T-3** 資料鏈與檔案配置：
  - C-7 前半：擷取與暖身前後，`price_bars_cache` 與兩張 log 的 checksum 不變。
  - C-7 後半：import-graph 斷言 `app.services.market`、`app.data.service`、`app.portfolio.*`、`app.advice.*` 不可達 `app.data.market_panel`；字串 `STOCK_DESK_MARKET_DB_PATH` 只出現在 `app/data/market_panel.py` 與 tests。
  - C-8：三個 DB 初始化後，以 `sqlite_master` 斷言每個檔只含 C-8 指定的表。主 DB 內沒有 `market_daily_bars` 與 `pit_*`；市場 DB 內沒有 `sector_*`。
  - C-13：`DATA_REFRESH_LOOKBACK_DAYS == 540`；`refresh_market_data` 的既有測試不修改且全綠。
- **T-4** PIT 儲存：
  - UPDATE／DELETE 一律失敗（store 不提供方法，trigger 也會擋下）；
  - `recorded_at` 無法由呼叫端傳入；
  - 無法自證日期時記 `failed`；
  - 缺日時沿用前一份並標 `carried_forward`，連續缺超過 5 個交易日的樣本作廢；
  - `cutoff(t)` 之後寫入的 run，對第 t 日的決策不可見；
  - D0 之後暖身 CLI 拒絕執行。
  - C-11：`build_scheduler()` 註冊的 job id 集合恰為既有兩個再加 `pit_snapshot_capture`、`sector_board_refresh`；import-graph 斷言 `app.scheduler` 不可達 `app.research`；scheduler 原始碼不引用暖身函式。
- **T-5** 未來擾動不變性（方法論 T1）：隨機取 50 個 t，把 t 之後（以 `recorded_at` 為準）的所有列（價格、名單、分類、事件）換成雜訊，第 t 日的輸出必須逐位元相同；`PointInTimePanel` 存取範圍外的資料必須拋錯。
- **T-6** Shift 測試（方法論 T3a、T3b）：
  - T3a 通過條件：p_leak − p_real ≥ δ_leak，且 p_real ≤ p_leak − δ_leak。δ_leak 在 CI 以合成資料校準，寫入 `method_version` 凍結。CI teeth test：已知有洩漏的管線必須被判為疑似洩漏。
  - T3b 只要求實際執行並寫入紀錄。
  - N < 30 時 T3a 記 `skipped_insufficient_n`。
  - runtime 與 CI 都執行。
- **T-7** 除權息不洩漏（方法論 T4）：
  - ① 每個決策日的排除清單，都能追溯到 `recorded_at ≤ cutoff(t)` 的公告；cutoff(t) 之後才記錄的公告，不得讓任何成分股被排除。
  - ② 標籤因子只用當時保存的快照計算，且與全庫重建的結果一致。
  - ③ 評估期間沒有除權息事件時，runtime 記 `vacuous` 並揭露。
  - CI 的合成路徑必須含除權息事件。runtime 與 CI 都執行。
- **T-8** 存活者偏差與分類 PIT（方法論 T5、T6）：
  - runtime：
    - 每個決策日的母體，等於 `recorded_at ≤ cutoff(t)` 的名單快照（不是最新 directory）；
    - 前瞻期內每一檔後來下市的股票，下市前的決策日都在母體內；
    - 每次實際改類，生效前都歸舊族群；
    - 沒有下市或改類事件時記 `vacuous`，不算失敗，並揭露。
  - CI：合成一檔 t+k 下市的股票，它必須出現在第 t 日母體；合成一檔 t+k 改類的股票，第 t 日必須仍屬舊族群。
  - 沒有 PIT 分類即為 NE-1，**沒有例外**。
- **T-9** 線上與判定一致，加上同一集合（方法論 T9）：
  - 同一個第 t 日，board 輸出的名次、R_g、k／n、成分股順序、三類排除計數與 `method_version`，逐欄等於 `sector_eval` 的回放結果。
  - 同一集合：R_g、「上漲 k／n 家」、成分股列示三者的成員集合完全相等，且都等於 `universe.calculation_set()` 的回傳值。
  - teeth test：故意讓其中一個集合多出一檔，測試必須失敗。
  - runtime 與 CI 都執行。
- **T-10** 偏誤版研究隔離（方法論 T10）：
  - import 邊界守門 C-4、C-5、C-27，寫法比照 C-1～C-5：`GUARDED_MODULES` 列出 `app.api.sectors`、`app.sectors.*`、`app.services.sector_board`、`app.backtest.sector_eval`、`app.backtest.basket`，全部不得可達 `app.research`；另列舉 `app/research/` 下的檔案，確認都有被掃到；加 teeth test。
  - 以字串與識別字掃描，確認 `STOCK_DESK_RESEARCH_DB_PATH`、`hindsight_view` 只出現在允許的位置。
  - 把 hindsight 或 `backfill_non_pit` 紀錄交給 `SectorStatsRepository`，必須拋 `BiasedDataRejected`。
  - 研究 DB 存在且有資料時，API 回應必須和研究 DB 不存在時完全相同。
- **T-11** 三態：
  - NE-1～NE-8 與 `pending_review` 各有一個單獨成立的案例，每個案例都驗證 `historical_stat is None`、`gate_checks is None`；
  - 優先序（方法論第五版 §6.3）：NE-8 最先（例如 NE-1 與 NE-8 並存時為 `demo_data`，NR-2）；其餘取 NE-1～NE-7 中編號最小者；`pending_review` 最後；
  - `pending_review` 只在 NE-1～NE-8 全不成立時出現；候選為 `passed` 與 `failed` 兩種情況都要測，而且回應中找不到候選結果；
  - `verified_on=None` 時必定出現 NE-3；
  - NE-4 邊界：第 20 個交易日不成立，第 21 個交易日成立；
  - G1～G6 各自單獨不過時，結果為 `failed`；
  - `failed` → `passed` 需要 `quarterly_qa` 紀錄；首次轉態需要 `first_transition_risk` 紀錄。
- **T-12** 參數與描述欄位：
  - `method_version` 與 L、H 不一致時建構失敗；L=10 時建構失敗；
  - 擾動 `turnover_value_ratio_5_20` 時名次完全不變；
  - m 由 registry 計算，並寫入 `m_at_evaluation`。
- **T-13** 基準與安慰劑（方法論 T7、T8）：
  - T7：B_EW 成員等於 C_M(t,L)；B_EW 不扣成本。
  - T8 ② 時間平移（判定用）：k 取 4 ≤ k ≤ N−4，Δ_k = p_k − q_k（扣成本後）的中位數絕對值須 < 2.5pp。N < 30 時記 `skipped_insufficient_n`。
  - T8 ① 標籤打亂（只作診斷，但必須輸出）：在族群大小不變的前提下打亂 1,000 次（記錄 seed），產出 `delta_shuffle` 與 `delta_real` 並寫入統計列；沒有產出即為 T8 未通過。
  - CI teeth test：在沒有個股效果、也沒有族群效果的合成資料上，Δ 接近 0；刻意漏算成本、或刻意偏袒小族群時，測試必須失敗。
  - runtime 與 CI 都執行。
- **T-14** Schema、欄位管制與字面：
  - 掃描 OpenAPI schema，確認沒有 C-26 禁止的欄位名。
  - C-23：`not_evaluated`（含 `pending_review`）時，遞迴走訪回應 JSON，不得出現任何 A 類鍵名：`beat_count_net`、`beat_count_gross`、`sample_count`、`effective_sample_count`、`base_rate_net`、`base_rate_gross`、`ci_low_net`、`ci_high_net`、`bootstrap_low_net`、`bootstrap_high_net`、`delta_real`、`delta_shuffle`、`m_at_evaluation`。同時斷言 B、C 類欄位全部存在，且在資料可得時有值。
  - C-28：`historical_stat` 只在頂層出現一次；`rank` 只在 `SectorItem` 裡；整份回應只有一個 `data_as_of`。
  - C-29：`data_source == "demo_synthetic"` 時，前端在任何 `gate_status` 下都渲染卡片層級的警告句（絕對底線）。
  - 風控定稿字面在前端與後端兩邊逐字釘住。

- **T-15** 方法論 T2（v1 結構斷言，CI，屬 NE-7 的 CI 集合）：斷言 `sector_eval` 與 `services.sector_board` 取得的 `universe.calculation_set`、`ranking.rank_sectors` 是同一個函式物件，且 repo 內沒有第二份實作。日後引入向量化版本時，逐列相等測試須在 CI 與 runtime 同批落地。
- **T-16** C-21 只增不刪：
  - 對四張表各做一次 UPDATE 與一次 DELETE，都必須拋 `sqlite3.IntegrityError`（來自 `RAISE(ABORT)`）。
  - `sector_method_registry`：
    - `first_forward_eval_at` 由 NULL 寫入值（同時 `counts_toward_m` 改為 1），第一次成功，第二次失敗；
    - 同一次 UPDATE 順帶改其他欄位，失敗；
    - `accumulation_start` 由 NULL 寫入值，第一次成功，第二次失敗。
  - 以 `sqlite_master` 斷言每張表的 trigger 都存在。teeth test：在暫存 DB 拿掉一個 trigger，存在性檢查必須失敗。
- **T-17** C-24、C-20 靜態掃描：
  - AST 掃描 `app/sectors/gate.py`、`app/sectors/coverage.py`、`app/backtest/sector_eval.py`：不得出現 `os.environ`、`os.getenv`、`getenv`，不得 import `os`、`dotenv`、`configparser`、`tomllib`、`yaml`、`app.settings`；`gate.py` 不得 import `sqlite3`。
  - C-20：對 `gate_status` 的賦值（含 dict key、關鍵字參數）只出現在 `app/sectors/gate.py`。
  - teeth test：對一個含 `os.environ.get("X")` 的暫存檔跑同一掃描，必須報錯。
- **T-18** C-15 識別字掃描：AST 掃描 `app/**` 的函式、變數、屬性與 dataclass 欄位名。名稱符合 `forward_return*`、`excess_gross`、`excess_net`、`label_return*`、`round_trip_cost` 者，其定義只能出現在 `app/backtest/basket.py`、`app/backtest/sector_eval.py`、`app/research/**`，以及白名單 `app/backtest/event_study.py`。附 teeth test。
- **T-19** C-31 核准 CLI，以下情況一律拒絕：
  - 缺 `--operator`、`--reviewer`、`--review-doc` 任一；
  - `--operator` 不是 `ceo`／`dev-lead`；
  - `quarterly_qa` 的 operator 不是 `dev-lead`；
  - 審查文件不存在，或內文不含 `run_id`／`method_version`。
  - 成功時，核准列須寫入文件路徑與 git blob hash。
- **T-20** 描述欄位與成分股（C-17、C-18、C-32～C-35）：
  - **同一集合**（風控 §6.2 (a) 的 qa 斷言）：
    - 每個族群的 `constituent_count == coverage.calculation_count == |universe.calculation_set()|`；
    - `up_count` 以同一集合計算，`constituents` 每一檔都屬於該集合；
    - `expected_count − missing − ex_date − corporate_action == calculation_count`（同一檔只計一次，歸屬 ① → ② → ③）；
    - 最小成分數與 `coverage_ratio` 都以 |C| 判定。
  - **排除歸因**（風控 §8-2，C-39）：
    - 三碼各一個單獨成立的案例：`too_few_members`（|E| < 5）、`low_coverage`（只有缺漏）、`ex_dividend_exclusion`（沒有缺漏，只因除權息或公司行動）；
    - 並存案例：缺漏與除權息並存、只看缺漏就已不足時，必為 `low_coverage`；
    - 每個被排除族群：`computable_count == |C_g|`、`expected_count == |E_g|`；同一族群只輸出一個 `reason_code`。
  - **門檻輸出**（風控 §6.2 (c)、§6.4-2、§8）：回應中的 `min_constituents`、`sector_coverage_threshold`、`overall_coverage_threshold`、`computable_ratio_min`、`ex_date_tag_ratio_min`，與 `SectorMomentumDefinition.coverage` 的值逐一相等；前端 wording 模組與元件原始碼不得含 `90%`、`98%`、`80%`、`5%`、`5 檔` 字面。
  - **`held`**：持倉查詢拋錯時，所有 `held is None`；前端不渲染徽章，並顯示「列示順序」句。
  - **不變量**：有排名族群的 `constituents` 長度恆為 3。以故障注入讓某族群只剩 2 檔時，該族群改列 `excluded_sectors`（`low_coverage`），當日判定帶 NE-6。
  - **C-18**：`TWT48U_ALL` 的 `ok` run 沒涵蓋最近 L 日時，整卡回 `insufficient_data`。
- **T-21** C-9：每個新 store 的連線執行 `PRAGMA busy_timeout`，回傳值 > 0。
- **T-22** NE-7 判定機制（C-36）：
  - attestation：測試集合未全綠時不產生 `ci_attestation.json`，並刪除舊檔；工作樹不乾淨時拒絕產生。
  - 判定時：commit 不符、缺 attestation、`suite_hash` 不符、讀不到 git、工作樹不乾淨，五者各自單獨觸發 NE-7。
  - 讀取時：統計列 `running_commit` 與部署的 `ci_passed_commit` 不符，觸發 NE-7。
  - 狀態：
    - N < 30 時，T3a／T8 可為 `skipped_insufficient_n`，不觸發 NE-7（對外原因為 NE-2）；
    - N ≥ 150 時出現 `skipped_insufficient_n`，觸發 NE-7；
    - T5／T6 沒有事件時為 `vacuous`，不觸發 NE-7；
    - T8 沒產出 `delta_shuffle`、`delta_real`，觸發 NE-7；
    - T-10 的 `BiasedDataRejected` 讓本次判定中止，不寫入任何統計列。
- **T-23** 整卡可計算比例與 e、a、b、c、x（C-37）：
  - 邊界：`computable_ratio` 恰等於 `computable_ratio_min` 時不降級；略低時整卡 `insufficient_data`，`insufficient_reason='computable_ratio_low'`。
  - 旺季案例：資料完整（`completeness_ratio` ≥ 0.98），但除權息排除使 `computable_ratio` < 0.80 時，原因必為 `computable_ratio_low`，不是 `overall_completeness_low`。
  - 計數：`market_expected_count − market_missing_count − market_ex_date_excluded_count − market_corporate_action_excluded_count == |C_M|`。同時缺漏又除權息的那一檔只計入缺漏；同時除權息又有公司行動的那一檔只計入除權息。
  - 捨去：`computable_ratio = 0.79999` 時 `computable_ratio_pct_display == 79.9`（不可為 80.0）；等於 0.80 時為 80.0。`completeness_pct_display` 同一規則。前端直接顯示此值，不再四捨五入。
- **T-24** 除權息 tag（C-38）：
  - `market_ex_date_excluded_ratio` 恰等於門檻時，`ex_date_tag` 為 true；
  - 略低於門檻、且沒有 `ex_dividend_exclusion` 族群時，為 false；
  - 低於門檻、但有任一 `ex_dividend_exclusion` 族群時，為 true；
  - 前端只依 `ex_date_tag` 顯示 tag，原始碼不含比例判斷。
- **T-25** `pit_gaps`（C-40）：
  - 四種缺口各一個單獨成立的案例，清單只含該項；多項並存時順序固定；
  - `accumulation_start is None` 時前三項必定成立，前端渲染句 2'、不渲染句 2；
  - 以故障注入讓 NE-1 旗標成立但清單為空，必須改判 NE-6；
  - NE-1 不成立時清單為 []。
- **T-26** T8 對照（C-41）：
  - `not_evaluated` 與 `insufficient_data` 時，回應不含兩個 Δ 鍵；
  - `passed`／`failed` 時兩者都有值，「詳細」渲染 T8-1、T8-2 定稿句，代入值與 API 一致；
  - 單獨改變 `delta_shuffle`，`gate_status` 不變。
- **T-27** 整卡不足（C-42、C-43；風控 §9 IP-1、IP-3～IP-6）：
  - 五碼各一個單獨成立的案例；兩兩並存時取順序較前者，例如 `ex_dividend_feed_gap` 與 `computable_ratio_low` 並存時取前者。
  - `status == "insufficient_data"` 時 `insufficient_reason` 必為非 null。
  - 回應中 `sectors == []`、`excluded_sectors == []`、`historical_stat is None`、`gate_checks is None`；`data_as_of`、`data_source`、`data` 照常存在。
  - 前端：不渲染任何族群名稱、成分股、NE 句或歷史句；每一碼都傳入各自非 null 的原因句，不得出現退回字面「資料不足，無法計算。」；「資料截至」徽章、過舊／日曆提示、示範資料警告照常顯示。
  - 順序常數被改動時，本測試必須失敗（守門「改動須重送風控」）。
- **T-28** 同名不同義與獨立常數（C-44、C-45；派工單 §10）：
  - 同一份 payload 下，③④ 句中的 {a}、{e} 取自同一欄位且值相等；③ 句只綁 `completeness_pct_display`／`overall_coverage_threshold`，④ 句只綁 `computable_ratio_pct_display`／`computable_ratio_min`，⑤ 句只綁 `sector_coverage_threshold`；以不同門檻值的 fixture 斷言 ③ 句不印 ④ 的門檻、④ 句不印 ③ 的門檻。
  - `no_sector_computable` 時 `excluded_reason_counts` 非 null，三個計數相加等於可排名族群總數；其他狀態為 None。
  - 前端原始碼掃描：族群卡元件與 wording 模組不得引用 `AS_OF_DATE_UNKNOWN_FULL_STATEMENT`；`as_of_unknown` 渲染本卡獨立常數。

**約束 ↔ 測試對照**

| 約束 | 測試 | 約束 | 測試 | 約束 | 測試 |
| --- | --- | --- | --- | --- | --- |
| C-1 | T-1 | C-16 | T-12 | C-31 | T-19 |
| C-2 | T-1 | C-17 | T-1、T-20 | C-32 | T-9、T-15、T-20 |
| C-3 | T-1 | C-18 | T-7、T-20 | C-33 | T-20、T-23、T-24 |
| C-4 | T-10 | C-19 | T-11 | C-34 | T-20 |
| C-5 | T-1、T-10 | C-20 | T-17 | C-35 | T-20 |
| C-6 | T-2 | C-21 | T-16 | C-36 | T-22 |
| C-7 | T-3 | C-22 | T-10 | C-37 | T-23 |
| C-8 | T-3 | C-23 | T-14 | C-38 | T-24 |
| C-9 | T-21 | C-24 | T-17 | C-39 | T-20 |
| C-10 | T-4 | C-25 | T-11 | C-40 | T-25 |
| C-11 | T-4 | C-26 | T-12、T-14 | C-41 | T-26 |
| C-12 | T-4 | C-27 | T-10 | C-42 | T-27 |
| C-13 | T-3 | C-28 | T-14 | C-43 | T-27 |
| C-14 | T-5 | C-29 | T-11、T-14 | C-44 | T-28 |
| C-15 | T-18 | C-30 | T-14、T-26、T-27 | C-45 | T-28 |

方法論 T1～T10 與 ADR 測試、runtime／CI 的對照見 D-8。

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
  - 除息旺季時，部分族群會因成分股被大量排除而不列入排行，原因碼為 `ex_dividend_exclusion`（方法論 §13-9）。整卡可計算比例若低於 `computable_ratio_min`（暫定 80%），整張卡降級為不足（C-37）。最終值要等 CEO 本機量測後，依方法論第五版 §2.3 的事先登記規則定案。
  - 前端依碼選句的欄位變多（`insufficient_reason`、`not_evaluated_reason`、`pit_gaps`、`reason_code`、`ex_date_tag`），每一碼的字面都已經風控定稿（派工單 §6、§8、§9、§10）。
  - 首頁報酬是排除除權息窗後的數字，可能和個股頁的未還原走勢不同，需要揭露句。
  - 資料量：前瞻每年約 1,100 × 245 ≈ 27 萬列日線；名單、分類、除權息用內容定址去重。實際量待實測。
  - 只含上市，「僅上市」標記常駐；上櫃的記憶體股、IC 設計股都會缺席。
  - 新增 2 個 job、約 12 張表；API 程序與 scheduler 程序的限流不共享。
  - **對 backtest-protocol 鐵律 3（walk-forward 分割）的已知偏離**：判定資料（`forward_pit`）不切訓練窗，整段視為樣本外；walk-forward 只保留每 126 日一段的測試窗幾何，用於分段報告（G5）。理由是 v1 參數在 D0 前凍結並 commit，沒有任何參數用前瞻資料擬合（方法論第四版 §5.3）。偏誤版研究仍依鐵律 3 分列樣本內與樣本外。此偏離列入 CEO 核可事項。
- **已知限制**
  - `cutoff(t)` 取當地 23:59:59，所以 21:30 之後的更正要到次日才對決策可見。
  - `pending_review` 已由風控採用（§6.4），方法論第四版 §6.3 已補列。
  - 核准 CLI 的 operator 與文件檢查只是減速帶；「唯讀職能與其他 agent 不得代寫」的效力來自規範與審查（ADR-0007 揭露的現況）。
  - 成分股不變量破壞時，`reason_code='low_coverage'` 那句可能與實際覆蓋率不符（見 D-7），另寫錯誤紀錄。
  - `ci_passed_commit` 是本機 build 的自我證明，不是外部 CI 簽章；能擋下未測試的 commit 與被改動的工作樹，擋不住刻意偽造。
  - 前瞻期內沒有下市、改類或除權息事件時，T4 ③、T5、T6 的 runtime 為 `vacuous`，這段期間只有 CI 合成案例提供保證。
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
| DE-5 | `change` 是否以參考價為基準；`TWT48U_ALL` 能否算出乘法因子 | 未知 | **待查證**。查證前，前瞻段的除權息紀錄不足以還原標籤，歸 NE-1（`pit_history_missing`），與方法論第四版一致（結構性來源缺口，非單次品質問題）。排行本身不受影響（回看窗採排除法，D-4） |
| DE-6 | 資料量 | 前瞻每年約 27 萬列日線，快照去重 | **待實測** |
| DE-7 | 資料公布時間 | 建議 17:00 之後 | 已定案：17:30／19:30／21:30 加日期自證；實際時間**待查證** |
| DE-8 | 已下市股票 | 無來源 | 前瞻累積自然解決；路徑 (b) **待查證** |
| DE-9 | 歷史產業分類 | 無來源 | 前瞻累積；路徑 (b) 依方法論 §12 |
| DE-10 | 成本費率 | 未查證 | 在查證前即為 NE-3；**待查證** |
| DE-11 | 除息旺季的三類排除量級 | 未量測 | **待 CEO 本機量測**：過去至少 3 年、L=5 窗的 \|C_M\|÷\|E_M\| 與三類各自佔比；結果交 quant-researcher，依方法論第五版 §2.3 提出 `computable_ratio_min` 最終值（只可調嚴，不低於 0.80） |

**quant-researcher（依方法論第五版，全部定案；門檻只能調嚴）**

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

- **quant-researcher**：方法論第四版已補列 `pending_review` 並提供 §8.3 對照表；D-8 對照表已對齊。
- **creative-lead 與 risk-compliance-officer**：
  - 已定稿：
    - NE-3～NE-8、`pending_review`、NE-8 卡片警告句（派工單 §6.1）；
    - `ex_dividend_exclusion` 短語、「除權息排除 {m} 檔」tag、NE-1 詳細句 1／G／2'、T8-1／T8-2（§8）；
    - `computable_ratio_low` 的主視圖句與詳細句（§9）；
    - `as_of_unknown`、`ex_dividend_feed_gap`、`overall_completeness_low`、`no_sector_computable` 四種不足原因句（§10）。
  - 待辦：混源揭露句。
  - 若風控不接受 D-7 在不變量破壞時沿用 `low_coverage`，另起草 `data_integrity` 的原因句。
- **qa-reviewer**：複審 v5（本版回應其 NEEDS_CHANGES）。
- **product-manager**：PRD 第三版已併入 R-A～R-C；N 維持 3。
- **devops-sre**：三個 DB 的備份（市場 DB 為最高等級）、scheduler 常駐監控、暖身回補操作手冊。
- **CEO**：
  - 是否接受第一階段不列歷史比例，且累積時程下限約 3.1 年（使用者可見句寫「約 3 年」）；
  - 是否核可對 backtest-protocol 鐵律 3 的已知偏離（判定資料不切訓練窗，見 Consequences）；
  - D0 日期（v1 參數須在 D0 前 commit，暖身須在 D0 前完成）；
  - 三個 DB 檔的配置；
  - §7 對 ADR-0002 的擴充解讀。

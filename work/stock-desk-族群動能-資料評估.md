# stock-desk 族群動能板 — 資料評估（data-engineer）

- 派工單：`work/stock-desk-族群動能-派工單.md`
- 依據：`.claude/skills/data-source-integration/SKILL.md`
- 範圍聲明：**本輪只寫本檔案，不改動 `apps/stock-desk/backend` 任何程式碼，不 commit。**
- 沙盒限制：本環境對 `twse.com.tw` / `tpex.org.tw` / `finmindtrade.com` 的 egress 已知被擋（CONNECT 403，與
  `app/directory/providers.py`、`work/stock-desk-已知限制與後續.md` 記錄的既有限制一致），本檔**未實測**任何端點；
  凡標「待 CEO 本機驗證」者，一律依現有 `apps/stock-desk/scripts/verify_market_data.py` 與
  `app/directory/sync.py --verify-sectors` 的既有驗證慣例補測，不新開驗證機制。
- 現況引用：以下對既有程式碼的敘述皆來自本次實地讀取（列出檔案路徑與行為），不是回憶；對外部端點規格的敘述區分「repo 內已有
  fixture／CEO 已實測」與「僅依公開常識、未在本次查證」兩類，逐項標明。

---

## 1. 全市場每日日線來源選項比較

| 來源 | 一次請求涵蓋量 | 歷史回補方式 | Rate limit（本環境認知） | 是否需 token | Repo 現況 |
| --- | --- | --- | --- | --- | --- |
| **TWSE `STOCK_DAY_ALL`**（`/v1/exchangeReport/STOCK_DAY_ALL`） | **當日**全部上市個股 OHLCV，一次請求 ~1,379 檔（`tests/fixtures/twse_openapi_stock_day_all.json` 樣本欄位：`Code/Name/TradeVolume/TradeValue/OpeningPrice/HighestPrice/LowestPrice/ClosingPrice/Change/Transaction`）。**這是「當日快照」，不是可查歷史某日的資料集**——`app/directory/providers.py` 模組說明明寫此端點是「同日快照」，且 `fetch()` 呼叫不帶 `date` 參數。 | **不適用於回補**：沒有可指定歷史日期的參數；只能拿到「呼叫當下最新一個交易日」。回補歷史必須改走下一列或 FinMind。 | 未知（本環境未實測）；既有 adapter 用 `min_interval_seconds=0.5`（`app/directory/providers.py:194`）沿用即可 | 否 | **已有 adapter**：`TwseDirectoryAdapter`（`app/directory/providers.py:187-272`），**CEO 2026-08-12 本機實測 PASS**（1379 筆）；目前只取 `Code`/`Name`，OHLCV 欄位存在但未被程式讀取——擴充成本低（parser 加欄位即可），**已有 fixture** |
| **TWSE `MI_INDEX`（`type=ALL`，帶歷史 `date` 參數）** | 依公開文件慣例，一次請求可拿「指定某一個歷史交易日」的全上市個股收盤行情 | **可回補**：一個交易日一次請求，5 年 ≈ 1,225 個交易日 → 約 1,225 次請求（若端點真如公開文件所述支援任意歷史日期） | 未知 | 否 | **repo 內完全沒有這支 adapter，也沒有 fixture**；端點路徑與欄位**未在本次查證**，僅依公開常識假設存在，**待 CEO 本機驗證**（含日期是否可回溯、是否有起始日限制） |
| **TPEx `tpex_mainboard_daily_close_quotes`**（`/openapi/v1/tpex_mainboard_daily_close_quotes`） | **當日**全部上櫃有價證券行情，一次請求；**CEO 2026-08-12 實測回傳 10,400～10,489 筆**——遠高於上櫃「公司」數量（~800 家），可推斷此集合把普通股以外的證券（債券 ETF、可轉債、受益憑證等）都含在內，欄位本身**沒有工具類型標記可篩**（`app/directory/providers.py:15-59`）。同樣不帶歷史 `date` 參數，是「當日快照」 | 不適用；同 `STOCK_DAY_ALL` | 未知；既有 adapter 用 0.5s | 否 | **已有 adapter**：`TpexDirectoryAdapter`（`app/directory/providers.py:275-362`），**CEO 已實測 PASS**，**已有 fixture**（`tests/fixtures/tpex_openapi_mainboard_daily_close_quotes.json`）；只取代號/名稱，OHLCV 欄位未讀 |
| **TPEx 個股日成交資訊逐檔**（現有 `TpexAdapter`，`/www/zh-tw/afterTrading/tradingStock`） | 一檔一個月一次請求 | 可回補，但一檔一個月一次 call | 未知；`min_interval_seconds=0.5`（`app/data/providers/tpex.py:203`） | 否 | **已有 adapter**（`app/data/providers/tpex.py`），但**端點本身尚未完整驗證**——header 自己承認「a second run confirming bars actually parse is still owed」（`tpex.py:11-28`），本次沙盒亦無法補測 |
| **FinMind `TaiwanStockPrice`（逐檔，`data_id=<symbol>`，指定 `start_date`/`end_date`）** | 一檔一次請求可拿**整段日期範圍**（不像 TWSE/TPEx 逐月），5 年區間 = 1 次請求/檔 | 回補效率最高：全市場 ~1,800 檔（見 §2）× 1 次請求 ≈ 1,800 次 | **未知確切數字**——`work/stock-desk-phase8-spike-盤點.md:33` 已記錄「免費層有 request/hour 限制（確切數字不確定）」；本次同樣**未能查證**（無網路），依 skill 紅線不得憑記憶寫死額度，僅能沿用既有 `RateLimitedClient(min_interval_seconds=0.3)`（`app/data/providers/finmind.py:91`）當保守下限，**待 CEO 本機以有效 token 測試實際 429/額度回應** | **是**（`FINMIND_API_TOKEN` 環境變數，CEO 本機已有；值不進本檔） | **已有 adapter**（`app/data/providers/finmind.py`），**CEO 2026-08-16 本機實測 PASS**，且與 TWSE 交叉比對 21/21 零容差；**已有 fixture** |
| **FinMind 按日期查全市場（不帶 `data_id`）** | 若 FinMind 平台真支援「省略 `data_id` 回傳當天全市場」，一次請求可覆蓋全部 | 若支援且可回溯歷史日期，回補效率同 `MI_INDEX` | 未知 | 是 | **完全未查證，僅為理論可能性**——公開文件是否真有此用法本次無法確認，**不建議規劃依賴**，僅列出待 CEO 有空查證 |

**本節結論（供 tech-architect 裁決，非本檔拍板）**：

- 目前 repo 兩個「一次全市場」端點（`STOCK_DAY_ALL`、TPEx mainboard）都只給「當日」快照，**只適合當每日增量的候選**，不能拿來做歷史回補；且兩者都缺乏可靠的「這是不是普通股」欄位，套用在族群分類前必須先用 `t187ap03_L`／`TwseSectorProfileAdapter` 已建立的「有明確產業別代碼」名單做正向篩選，而不是逆向猜測要排除誰。
- 歷史回補唯一在 repo 內已驗證、且效率上可行的路徑是 **FinMind 逐檔 `TaiwanStockPrice`**（一檔一次請求即可拿完整區間）；TWSE/TPEx 逐月端點回補全市場的請求量高兩個數量級（見 §2），不建議作為主要回補管道。
- `MI_INDEX` 型「歷史日期＋全市場」端點若存在，會是**每日增量**與**歷史回補**都適用的最佳解，但**這支 adapter 完全不存在於 repo，本次沙盒也無法查證**——這是本評估最大的未知，見 §7 第 1 項。

---

## 2. 回補量體估算（以 3～5 年估）

前提與依據（皆標明推算基礎，非精確值）：

- 上市（TW）常態掛牌檔數：以 `TwseDirectoryAdapter` 2026-08-12 實測 1,379 筆為基礎，扣除明顯非普通股（ETF、TDR 等，`t187ap03_L` 只涵蓋「有產業別代碼」的普通股公司，2026-08-12 該端點回傳 1,095 筆），**普通股母體估 ~1,000～1,100 檔**。
- 上櫃（TPEx）常態掛牌檔數：`TpexDirectoryAdapter` 回傳 10,489 筆是「全部有價證券」，遠高於普通股家數；依公開常識上櫃普通股約 800 家上下（**未在本次查證，待 CEO 用 `t187ap03_O` 或等效資料集比對後修正**，見 §4）。
- 族群動能所需母體（排除 ETF／TDR／債券等，見 §4）：**估 ~1,800～1,900 檔**。
- 台股年交易日數：約 240～245 日（無假日表，`app/data/cache.py::market_trading_days` 也是「觀測而非表列」，ADR-0009 已知限制同）。

| 回補年期 | 交易日數（估） | 總列數（1,850 檔估） | SQLite 大小估算（含索引） |
| --- | --- | --- | --- |
| 3 年 | ~735 | ~1,360,000 列 | 依 `price_bars_cache` 現有 schema（`symbol/market/trade_date` TEXT、OHLC 4 個 TEXT、`volume` INTEGER、`currency/source` TEXT、`as_of/fetched_at` 兩個 ISO 字串 TEXT）估**每列原始資料 ~150～200 bytes**；現表有 2 個次要索引（`idx_price_bars_cache_lookup` 與主鍵欄位重複、`idx_price_bars_cache_market_date`），連同索引膨脹估**每列總成本 300～400 bytes** → **約 400～550 MB** |
| 5 年 | ~1,225 | ~2,270,000 列 | **約 680～910 MB** |

**這是估算，不是實測**——`sqlite3_analyzer` 或實際灌一批 fixture 資料測量頁面碎片化程度會更準；建議正式排回補前，先用 1 個月的真實資料量做一次小規模灌測，反推每列實際 bytes 再校正上表。

**回補耗時與分批策略**：

- **若走 FinMind 逐檔（本評估建議的回補主路徑）**：~1,850 次請求 × `min_interval_seconds=0.3`（現有 `FinMindAdapter` 設定）≈ 555 秒理論下限（~9 分鐘），但這只是節流間隔，不含每次請求的實際延遲、重試退避、以及**未知的 FinMind 帳號級額度**（§1、§7）——若額度是「每小時 N 次」，回補會被迫拆成多個時段跑，需要**可斷點續傳**：以「已成功寫入的 symbol 清單」為 checkpoint（例如一張 `sector_universe_backfill_progress(symbol, market, last_success_at)` 表，或簡單的 JSON checkpoint 檔），中斷後從未完成清單續跑，而不是整批重來。
- **若走 TWSE/TPEx 逐檔逐月既有 adapter（`TwseAdapter`/`TpexAdapter`）當備援或交叉驗證**：5 年 = 60 個月/檔，1,850 檔 × 60 次請求 × 0.5 秒間隔 ≈ 15.4 小時理論下限——**不建議作為全市場回補的主路徑**，只適合小規模抽樣交叉比對（比照既有 `scripts/verify_market_data.py` 的抽樣比對慣例）。
- **若 `MI_INDEX`（歷史日期＋全市場）驗證成功**：5 年 ≈ 1,225 次請求（TWSE）+ 同量級（TPEx 對應端點，同樣待驗證）× 0.5 秒間隔 ≈ 10～20 分鐘量級，是效率最高的方案，但目前完全未驗證（§7 第 1 項）。
- **分批建議（不論走哪個來源）**：一律以「一個交易日」或「一檔股票」為最小可重試單位（不要用「一整個市場一次性大交易」），單批失敗只影響一個單位，寫入採 `INSERT ... ON CONFLICT DO UPDATE`（沿用 `PriceBarCache.put` 現有 upsert 語意），全程記錄成功/失敗清單，失敗的「浮上檯面」而非略過不提——這是 skill 紅線「資料異常要浮上檯面，不得靜默補值」的具體落地。
- 回補應在離峰時段跑（例如收盤後、非交易時段），且與正式每日增量 ETL（§3）分開排程，避免回補跑到一半時增量 ETL 又對同一批標的送重複請求。

---

## 3. 每日增量 ETL

**時機**：

- TWSE 收盤 13:30，公告時間 ADR-0009 D-2 已定義 `publish_cutoff=15:00`（**該時間點本身「未查證」，是刻意設偏晚**，ADR-0009 原文自承）；TPEx 收盤同為 13:30，公告時間點本評估同樣沿用 ADR-0009 的偏晚假設，未另行查證。
- 建議增量 ETL 排在 **Asia/Taipei 17:00 之後**（比 ADR-0009 的 15:00 cutoff 再晚 2 小時的緩衝，因為 `STOCK_DAY_ALL`／TPEx mainboard 兩個候選端點是否在 15:00 就已更新到當日**未查證**），並且**當天執行失敗時，隔天執行要能補上前一天缺的那一天**（見降級策略）。
- 若 CEO 驗證後確認 `STOCK_DAY_ALL` 在 cutoff 前就已可拿到當日資料，時間可提早；這屬於「查證當下記錄查證日期」的範疇，不在此臆測。

**與現有排程／D-8 冷卻的關係（重要：不是同一套機制，且不應該共用）**：

- 現有 `app/scheduler.py::refresh_market_data`（`DATA_REFRESH_LOOKBACK_DAYS=540`）只對**持倉裡實際有的標的**跑 `load_bars`，走 `MarketDataService` 的完整降級梯子（含 ADR-0009 的 `judge()`、`price_bars_fetch_log`、`price_bars_attempt_log`、D-8 冷卻）。這套機制的設計前提是「**使用者請求觸發**的按需抓取，一次一檔」，冷卻表以 `(symbol, market)` 為鍵。
- 全市場 ETL 是**排程觸發、批次、push 式**的，語意完全不同：它不是「使用者想看某檔於是去問來源」，而是「每天固定把全市場抓回來」。若硬套用 `price_bars_fetch_log`/`price_bars_attempt_log`（一檔一列的冷卻表），1,800+ 檔會在同一批寫入時對這兩張表灌入等量的列，且 ADR-0009 D-3 的「連續區間合併」語意（為了處理使用者忽前忽後查詢不同區間）對「每天固定追加一天」的批次寫入毫無用處，只會多出無意義的 I/O。
- **本評估建議**：全市場 ETL **不沿用** `price_bars_fetch_log`/`price_bars_attempt_log`，改用一張**以（market, trade_date）為鍵**的輕量 log（例如 `sector_universe_fetch_log(market, trade_date, source, row_count, fetched_at)`），語意是「今天這個市場的全市場快照有沒有抓過、抓了幾筆」，一天一列而非一檔一列——量級差兩個數量級（每天 2 列 vs 每天 1,800+ 列）。這張表的角色類似 ADR-0009 的 fetch log，但粒度是市場層級的批次結果，不是個股層級的請求覆蓋範圍，**這點需要 tech-architect 在 ADR 裡明確拍板**，避免日後有人誤以為兩套 log 可以合併。
- 排程本身：現有 `build_scheduler` 只有 `interval` trigger（`app/scheduler.py:188-213`），新工作若要「每天固定本地時間跑一次」，需要 APScheduler 的 `cron` trigger（套件本身已含 `apscheduler.triggers.cron`，repo 目前未使用過）——是否要開這個新的 trigger 型別、是否要跟既有 `data_refresh`/`alert_evaluation` 同一個 `BlockingScheduler` process，還是切成獨立 process/服務，**列為需要 tech-architect 裁決的點**（見 §6）。

**失敗降級**：

1. 主來源（`STOCK_DAY_ALL` / TPEx mainboard，若驗證後採用）失敗或回應非預期 schema → 記一筆 `sector_universe_fetch_log` 失敗紀錄（不是靜默跳過），當天族群動能卡以**前一個成功交易日**的資料計算，並在畫面上比照既有 `DataMetaStatusBadge`／「資料截至」慣例明示「資料截至 {上次成功日期}」而非今天，不得用今天的日期冒充。
2. 主來源失敗時，備援嘗試 FinMind 逐檔補（僅補當天缺的那些檔，不整批重跑），適用既有 `FINMIND_API_TOKEN` 機制與現有 `FinMindAdapter`；FinMind 也失敗則整個市場停在「資料截至前一日」狀態。
3. 兩者皆失敗 → 明確錯誤狀態，記錄 log 供 devops-sre 監控告警（監控機制本身列管 devops-sre，data-engineer 只保證失敗會被記下來、不會被吞掉）。
4. **不得**用內插值、前一日收盤複製貼上等方式「填補」缺失的交易日資料——這是 skill 與公司章程的紅線，缺漏必須是缺漏，不是偽裝成有資料。

**資料品質檢查**：

- **缺漏日期**：以「昨天有資料的市場，今天預期也該有」為基準（比照 `PriceBarCache.market_trading_days` 的「觀測而非表列」精神，但這裡改成觀測全市場快照 log 而非逐筆 bar）；連續 N 個預期交易日沒有新快照即浮上告警，而非等使用者發現卡片沒更新。
- **重複列**：`INSERT ... ON CONFLICT(symbol, market, trade_date) DO UPDATE` 天然去重（沿用 `PriceBarCache.put` 既有語意），但**同一天若跑了兩個不同來源**（例如主來源+FinMind 補檔）要留意「誰覆蓋誰」——`PriceBarCache.put` 目前對此的既有語意是「不看舊列的 source，最新寫入者贏」（`app/data/cache.py:184-189` docstring），沿用到新表前要在 ADR 裡明確寫下這個取捨是否仍然成立，或改採「主來源優先，備援只補缺」的規則（後者較適合批次 ETL，因為批次 ETL 沒有「誰是最新請求」的概念）。
- **型別／幣別錯置**：沿用既有 `_util.parse_decimal_cell`/`parse_int_cell`/`parse_roc_date` 的嚴格解析與跳過（unparseable row 直接略過並記 log，不猜測），幣別固定 `TWD`（同 `twse.py`/`tpex.py` 現況），任何非台股標的（如未來若混入非 TW 市場）一律拒收而非硬轉。
- **未來日期**：解析出的 `trade_date > today` 一律拒收並記警告（防禦 ROC 日期換算錯誤，`twt48u_all` fixture 已顯示這類端點常見 ROC 日期陷阱）。
- **新鮮度**：`as_of`／`fetched_at` 兩欄比照現有 `PriceBar` schema 帶上，讓下游（quant-researcher 的訊號計算、前端徽章）可以獨立判斷這批資料多舊，不依賴「今天有沒有跑過 ETL」這種隱含狀態。
- **除權息未還原的影響（重要，需明確揭露給 quant-researcher）**：`app/dividends/providers.py` 現有的除權息模組**只涵蓋 TWSE 上市的「即將除權息預告」**（`TWT48U_ALL`），是**前瞻公告**，不是歷史還原因子序列，也**完全不涵蓋 TPEx**。也就是說，repo 內**沒有任何**可以把歷史收盤價還原成除權息調整後價格的機制。族群動能若直接拿原始收盤價算 5/20 日報酬，個股在除權息當天會出現一個非真實下跌的價格跳空，可能被排名邏輯誤判為「轉弱」；族群層級因為是等權平均，單一成分股的跳空會被稀釋但不會消失，尤其在除權息旺季（Q3 台股股東會後）族群排名可能出現系統性雜訊。**這是資料層面的已知限制，不是本次要解決的範圍**（派工單明寫「第一階段只用現有資料型態」），但必須明確告知 quant-researcher 在訊號設計時知道這個限制存在，由 quant-researcher 決定要不要在方法論裡處理（例如用成交量加權或排除除權息當週等）。

---

## 4. 族群分類

- **上市（TWSE）產業別**：已有完整落地路徑——`TwseSectorProfileAdapter`（`app/directory/providers.py:380-471`）抓 `t187ap03_L`，經 `app/directory/twse_sector_codes.py` 兩碼代碼轉中文名稱，寫入 `security_directory.sector`（`app/directory/store.py`），且已與 `app/positions/sectors.py` 的 36 類封閉清單對齊（2026-08-12 CEO 實測、風控與 CEO 已核可清單內容）。**族群動能的上市股分類可以直接複用這條既有管線**，不需要新建。
- **上櫃（TPEx）產業別**：**目前 repo 完全沒有這塊資料**。`app/directory/sync.py` 模組說明明寫「上櫃與 ETF 不在這個資料集裡，其 `sector` 維持 NULL」；`sector_backfill.py` 也把「目錄有此代號但沒有產業別」列為明確的跳過原因之一。候選來源：
  - **TWSE OpenAPI 上櫃版本的公司基本資料**（依公開常識，MOPS 公司基本資料通常以 `t187ap03_X` 命名，`_L`=上市已驗證，上櫃可能是 `_O` 或類似字尾）——**本次完全未查證路徑與欄位名稱，是純猜測**，待 CEO 在有網路環境用瀏覽器或 `curl` 對照 TWSE OpenAPI 的 Swagger 目錄（`app/dividends/providers.py` 開頭的教訓：`TWT49U` 這種「依公開常識猜的端點」曾經是死路，需要對照官方目錄而非用猜的）。
  - **FinMind `TaiwanStockInfo`**（依 FinMind 生態圈的一般公開文件慣例，這類 dataset 通常同時涵蓋上市與上櫃並帶 `industry_category` 欄位）——**同樣未在本次查證**，且 `work/stock-desk-phase8-需求.md`／`phase8-spike-盤點.md` 也把「FinMind 是否有可用的產業分類 dataset」列為待確認事項，不是本次新發現的疑問，是既有的未解問題。
  - 兩者都需要 CEO 本機或有網路環境驗證 **端點是否存在、欄位名稱、是否需要額外的 dataset 授權層級**，才能進入實作。**在驗證完成前，本評估不建議承諾上櫃族群分類的交付時程**。
- **分類變更與下市櫃處理**：沿用既有 `security_directory` 的 upsert-only 語意（`app/directory/store.py` docstring：「a name refresh must not blank out a category」）——**建議**族群動能的分類快取比照同一原則：每次同步只更新「有抓到新分類」的欄位，若某代號本次同步查無資料（可能已下市、可能只是來源當天沒回報），**保留上次已知分類並標記「上次確認日期」**，而不是清空；連續 N 次同步都查無此代號，才視為候選下市，交由後續流程（例如週期性人工核對或比對 `security_directory` 是否已被標記下市——目前 repo 沒有明確的「下市」欄位，這也是需要 tech-architect 一併裁決的資料模型缺口）。
- **ETF／存託憑證等非產業別排除**：`app/positions/sectors.py` 封閉清單已把「存託憑證」單獨列一類（代碼 91，CEO 2026-08-12 裁決），這代表**產業別分類本身有能力區分「有明確產業歸屬」與「特殊工具類」**，但**沒有能力區分「ETF」**——因為 ETF 根本不在 `t187ap03_L` 這個「公司」清單裡，不會被賦予任何產業別代碼，`sector` 直接是 NULL。所以排除 ETF 的正確做法是：**族群動能的候選母體＝「在 `t187ap03_L`／上櫃對應資料集裡查得到有效產業別代碼的代號」的正選（allow-list），而不是從全市場清單裡用代碼形態或名稱關鍵字排除 ETF（deny-list）**——這與 `app/directory/providers.py` 目前對 `security_directory`（涵蓋 ETF）的處理方式刻意不同：目錄要「查得到代號」就收，族群動能要「查得到產業別」才收，兩者用途不同，母體不應該共用同一份清單而不加篩選。

---

## 5. 大盤基準

- **加權股價指數（TAIEX，^TWII）**：**不需要新接**——`app/services/index.py:309` 已把 `BenchmarkIndex(series_symbol="^TWII", ...)` 設為 TW 市場的既有基準，`app/playbook/service.py` 現有規則引擎已經在用 `^TWII` 當加權指數基準，`app/data/providers/yfinance.py:125` 已將 `^TWII` 對應到 `("TW", "TWD")` 並**經 `scripts/verify_market_data.py --index-symbol ^TWII` 驗證過**（`yfinance.py:36`）。族群動能「近 5/20 日相對大盤報酬」可直接複用這條既有管線讀 `^TWII` 日線，不需要新 adapter、新驗證。
- **櫃買指數（TPEx 加權指數）**：**repo 目前沒有任何來源**。若要對上櫃股單獨算「相對大盤」，理論上該用櫃買指數而非加權指數（兩個市場走勢常脫鉤）。依公開常識 yfinance 的台灣櫃買指數代號可能是 `^TWOII`（**本次完全未查證，僅為猜測**，比照 `^TWII` 的既有驗證模式，需要 CEO 用 `scripts/verify_market_data.py --index-symbol ^TWOII` 補測）。
- **改用等權全市場（本評估建議的替代方案）**：既然族群動能本身就需要抓全市場個股日線（§1～§3），**用自己抓到的全市場資料算一個等權平均報酬當基準，不需要額外的外部指數來源**，可以避開：(a) 櫃買指數來源未知的問題；(b) ADR-0005 已經明確否決的「用 ETF 代理指數」陷阱（0050 有經理費與折溢價，"明確禁止以 0050 代理"台灣 50 指數）——等權全市場基準是我們自己算的原始數字，沒有代理工具的失真問題，但也有自己的取捨：等權（每檔權重相同）vs 現有 `^TWII` 是市值加權，兩者衡量的「大盤」概念不同，等權對中小型股的表現更敏感，這個選擇本身是方法論決策，**交由 quant-researcher 在方法論文件裡定案**，本節只負責列出「等權基準的資料成本是零（沿用族群動能既有的全市場抓取），不需要額外驗證」這個事實。
- **建議裁決點**：加權指數（已驗證、零成本）vs 等權全市場（零額外資料成本、方法論意義不同）vs 櫃買指數（未驗證、僅上櫃族群適用）三者如何搭配，列入 tech-architect ADR 一併拍板，本檔不代為決定。

---

## 6. 儲存方案建議

**不建議直接沿用 `price_bars_cache`**，理由：

1. **語意不符**：`price_bars_cache` 三張表（`price_bars_cache`／`price_bars_fetch_log`／`price_bars_attempt_log`）是為「使用者持有的少量標的、請求觸發、逐檔逐區間追蹤覆蓋範圍」設計的（ADR-0009 全文），族群動能是「排程觸發、全市場、每天固定追加一天」，兩者的覆蓋範圍語意（`covered_start`/`covered_end` 的合併/取代規則）對全市場批次寫入沒有意義，硬套只會製造 1,800+ 倍的無用寫入量（見 §3）。
2. **量體風險**：§2 估算 3～5 年全市場資料是 400～900MB 量級，而目前 `price_bars_cache` 服務的是「使用者實際持倉的幾十檔標的」，量體差距是兩到三個數量級。混在同一張表、同一個 SQLite 檔案裡，會讓：
   - `PriceBarCache.market_trading_days`（`app/data/cache.py:457-501`，`SELECT DISTINCT trade_date ... WHERE market = ?`）掃描的資料量暴增（雖有 `idx_price_bars_cache_market_date` 索引，但索引本身的大小與維護成本會隨列數線性成長）；
   - ADR-0010 剛解決的「/api/advice 整書估值變慢」問題背後的教訓——**單一 SQLite 檔案的寫入是序列化的**（`busy_timeout=5000ms`），全市場 ETL 若與持倉查詢／`/api/advice`／警示評估共用同一個資料庫檔案的寫鎖，即使錯開時間排程，仍有「回補作業意外拖長，撞上使用者開著頁面查看警示」的風險，這正是 ADR-0010 想避免的那類問題（雖然場景不同，但「大量批次寫入 vs 即時讀取共用同一把鎖」的風險模式相同）。
3. **不同的失敗語意**：族群動能全市場快照允許「今天缺一天，明天補上」，但 `price_bars_cache` 的 `record_fetch`/`find_foreign_bars`/`delete_by_source` 這些方法都是為「單一標的的資料完整性」設計，硬塞全市場資料會讓這些既有方法的呼叫端（例如警示引擎、持倉估值）在完全不知情的狀況下，讀到語意不同的資料而出錯。

**建議方向（供 tech-architect 裁決，data-engineer 不越權拍板）**：

- **新表**，暫名 `sector_universe_daily_bars`：欄位比照 `price_bars_cache` 的 `PriceBar` schema（`symbol/market/trade_date/open/high/low/close/volume/currency/source/as_of/fetched_at`），主鍵 `(symbol, market, trade_date)`；獨立的 `sector_universe_fetch_log(market, trade_date, source, row_count, fetched_at)` 取代 per-symbol 覆蓋範圍語意（§3 已述）。
- **是否共用同一個 SQLite 檔案，還是切成獨立資料庫檔案**：這是本評估認為**最需要 tech-architect 拍板**的一點。共用檔案的好處是「不新增架構層」（比照 `security_directory` 當初的裁決理由）；獨立檔案的好處是把大量批次寫入的鎖爭用隔離開，避免影響既有持倉/警示路徑的低延遲需求（ADR-0010 剛解決的問題）。**本檔傾向獨立檔案**，但這牽涉到 `STOCK_DESK_DB_PATH` 既有慣例、備份/部署流程是否要多管一個檔案，超出 data-engineer 職權，需要 tech-architect 出 ADR。
- 需要 tech-architect 裁決的清單：
  1. 新表是否與 `price_bars_cache` 同檔案；
  2. `sector_universe_fetch_log` 的粒度（market+date）是否要進一步拆分成「主來源/備援」兩軌，方便追蹤混源情況（比照 ADR-0009 D-7 的混源揭露慣例）；
  3. 全市場 ETL 排程要不要跟現有 `app/scheduler.py` 同一個 process（§3 已提出 cron trigger 的新需求）；
  4. 上櫃族群缺乏產業別資料期間，第一階段是否要「先只做上市族群動能，上櫃排除」——這是產品範圍問題也是資料可行性問題，需要 tech-architect／product-manager 一起看；
  5. 除權息未還原的資料品質限制（§3 末段）要不要在方法論定案前就先在 ADR 裡明文記錄成已知限制，避免後續被誤認為 bug。

---

## 7. 風險與未知清單

| # | 項目 | 風險 | 待驗證方式 |
| --- | --- | --- | --- |
| 1 | **TWSE「歷史日期＋全市場」端點（`MI_INDEX` 或等效）是否存在、欄位為何** | 若不存在，全市場回補只能走 FinMind 逐檔或 TWSE/TPEx 逐檔逐月（§2 估算 15+ 小時），且每日增量也可能被迫改走 FinMind | **待 CEO 本機驗證**：先用瀏覽器或 `curl` 對照 TWSE OpenAPI／`exchangeReport` 的官方 Swagger 目錄確認端點是否存在（比照 `app/dividends/providers.py` 的教訓，不要憑猜測寫死路徑），若存在再寫最小 adapter 試打一天 |
| 2 | **FinMind 免費層實際 rate limit／額度** | 直接決定回補與每日增量的可行時窗；`work/stock-desk-phase8-spike-盤點.md` 已記錄此為既有未知，非本次新增 | **待 CEO 本機用有效 `FINMIND_API_TOKEN` 小量測試**（例如連續打 50～100 次觀察是否出現 429 或額度回應），記錄查證日期 |
| 3 | **TPEx 上櫃產業別來源** | 沒有這塊資料，族群動能第一階段可能被迫排除上櫃股或延後交付 | **待 CEO 查證** TWSE OpenAPI 是否有上櫃對應的 `t187ap03_*` 資料集，或 FinMind `TaiwanStockInfo` 是否存在且含 `industry_category`（§4） |
| 4 | **TPEx mainboard 全量快照混雜非普通股證券** | 若不篩選，族群分類母體會混入無意義的債券/受益憑證代號 | 待與 §4 的「上櫃產業別來源」一併解決：用產業別正選清單自然排除，不需要額外的證券類型篩選機制 |
| 5 | **櫃買指數（`^TWOII`）是否可用** | 若不可用，上櫃股的「相對大盤」只能用加權指數（市場不同、失真）或改走等權全市場基準（§5） | **待 CEO 本機**用 `scripts/verify_market_data.py --index-symbol ^TWOII` 驗證 |
| 6 | **`app/data/providers/tpex.py` 現有 TPEx 逐檔 adapter 尚未完整驗證** | 若族群動能拿它當交叉比對或備援來源，繼承既有未驗證風險 | 沿用該檔案自己記載的驗證指令：`uv run python ../scripts/verify_market_data.py --tpex-symbol 6147`（`app/data/providers/tpex.py:20-24`），**待 CEO 本機補測** |
| 7 | **除權息未還原對族群動能訊號的影響幅度** | 目前只能定性描述「除權息當天會有假跳空」，沒有量化過對排名結果的實際干擾程度 | 屬 quant-researcher 方法論範疇，data-engineer 只負責揭露限制存在，不代為評估影響幅度 |
| 8 | **全市場批次寫入對既有 SQLite 檔案鎖爭用的實際影響** | §6 是理論推演（`busy_timeout=5000ms`、WAL 模式），沒有實測過「1,800+ 檔全市場 upsert 進行中，同時打 `/api/advice`」的實際延遲 | 建議在 tech-architect 裁決儲存方案後，用一批合成資料（比照現有 `app/demo/series.py` 的示範資料手法）做一次本機壓測，量測數字後回填 ADR，而不是憑本檔的理論估算下最終結論 |
| 9 | **上市普通股 / 上櫃普通股實際家數** | §2 的回補量體估算依賴這兩個數字，本次用 `t187ap03_L` 1,095 筆與公開常識 800 家估算，未實測上櫃對應數字 | 待 §4 的上櫃產業別來源查證解決後一併確認實際家數，回頭校正 §2 的量體估算 |
| 10 | **已下市／下櫃個股的歷史資料與名單來源（§8.3）** | **本評估風險最高項**：目前所有候選來源都只列「現在還掛牌」的證券，直接回補會系統性排除下市公司，造成存活者偏差，可能讓歷史命中率呈現得比真實情況更好看，與派工單「歷史機率不得誤導」的裁定衝突 | **待 CEO／有網路環境查證** FinMind 是否保留已下市代號的歷史日線與下市日期、TWSE/TPEx 是否有可程式化的「終止上市（櫃）」名單端點；查證結果出來前不得對外承諾回測無存活者偏差 |
| 11 | **point-in-time 產業分類無歷史來源（§8.3）** | `t187ap03_L` 只回傳「今天」的分類，`security_directory.apply_sectors` 是 UPDATE-only 不留歷史；回補期間的回測只能用「現在的分類」套用到過去，屬 look-ahead 風險 | 無法事後補救；只能從 ETL 上線當天起改用版本化的 `security_sector_history` 表往後累積，回補期間的限制需在方法論與交付文件中明確揭露 |
| 12 | **上櫃除權息日曆／還原價完全無來源（§8.4）** | 上櫃族群的除權息造成的價格跳空無法排除或標記，且此限制無法回補（`TWT48U_ALL` 本身也是「僅上市、無歷史」） | 待 CEO／有網路環境查證 TPEx OpenAPI 或 FinMind 是否有對應的除權息 dataset；查證前不得假設存在 |
| 13 | **手續費／證交稅現行生效版本（§8.5）** | 本沙盒無法查證官方現行法規與生效區間（含 ETF／一般股票稅率是否不同、當沖優惠稅率落日條款），錯誤或過期數字會直接扭曲對外呈現的「扣成本後報酬」 | **待 CEO 或有網路環境人員**查證財政部《證券交易稅條例》、證交所／櫃買中心公告或券商公開資訊，並記錄查證日期後寫入設定檔（schema 見 §8.5） |
| 14 | **上市／上櫃快照「完整」判準門檻與 as-of 不一致揭露字面（§8.1、§8.2）** | 覆蓋率門檻（例如 90%）與跨市場日期不一致時的使用者可見字面，本檔只提出設計方向，尚未定案，也未經風控核可 | 門檻由 quant-researcher／tech-architect 訂定；揭露字面比照既有慣例（ADR-0009 D-7、ADR-0010「需風控核可的揭露點」）另案送風控核可，本檔不代為定稿 |

---

## 8. 風控預審回應（2026-09-24 補充）

risk-compliance-officer 預審回饋的五點，逐項回應如下；凡屬「查證」與「schema/資料模型」問題，data-engineer 負責回答；凡屬「這個限制要不要接受、影響多大」的方法論判斷，明確交棒 quant-researcher／product-manager／CEO，本節不代為裁決。

### 8.1 as-of 取「全市場最新完整交易日」——上市／上櫃日期不一致的偵測與處理

- **偵測**：不能只靠「HTTP 200」判斷一天的快照算不算完整，必須用 §8.2 的覆蓋率門檻來定義「完整」——`sector_universe_fetch_log` 的雛型（§3、§6）需擴充為 `sector_universe_fetch_log(market, trade_date, status, actual_count, expected_count, fetched_at)`，其中 `status` 只有在 `actual_count` 達到門檻（建議相對於近期中位數的比例，例如 ≥90%，實際門檻交 quant-researcher／tech-architect 訂）時才標記 `COMPLETE`；未達門檻的一天**不記為成功**，觸發 §3 已定義的降級路徑（用前一個成功日、明示「資料截至」）。
- **上市／上櫃不一致的處理**：兩個市場各自獨立判斷「最後一個 COMPLETE 交易日」（`twse_last_complete`、`tpex_last_complete`）。
  - **一致**（同一天）：全站 as-of 用該日期，不需要特別揭露。
  - **不一致**（例如 TWSE 今天完整、TPEx 卡在前一天）：**board 層級**（同時橫跨兩個市場的排名，例如「全市場族群動能總表」）的 as-of 一律取 **兩者較舊者**（`min(twse_last_complete, tpex_last_complete)`），不得取較新者冒充兩個市場都更新到那一天；**單一市場層級**（例如使用者只看上市族群）可以用該市場自己的 as-of，不受另一市場拖累。兩種情況都必須讓使用者看到「上市資料截至 X、上櫃資料截至 Y」兩個獨立日期，不得合併成一個模糊的「資料截至」——這點與 ADR-0009 D-7 的「混源資料要在 `reason` 裡列出每個來源」是同一種誠實揭露精神，但這裡是「跨市場日期不一致」而不是「跨 provider 混源」，字面需要另外設計，**列入需風控核可的揭露點**，不在本檔定案文案。
  - 這條規則需要前端把「單一 as-of 徽章」改成「可能兩個日期」的呈現，超出 data-engineer 範圍，交接 frontend-engineer／tech-architect。

### 8.2 覆蓋率：每日應有檔數 vs 實有檔數、缺漏清單

- **應有檔數（分母）**：取自 §4 定義的「產業別正選清單」（在 `t187ap03_L`／上櫃對應資料集裡查得到有效產業別代碼的代號），**不是**目錄裡的全部代號（那會把 ETF／債券也算進分母，錯誤地拉低覆蓋率）。此清單目前只有「今天最新版」，沒有歷史版本——回測時若拿今天的名單當歷史某一天的分母，會與 §8.3 的 point-in-time 問題連動失真，見 8.3。
- **實有檔數（分子）**：`sector_universe_daily_bars` 該交易日、該 market 的 distinct symbol 數。
- **缺漏清單**：分母減分子的差集，**逐檔列出**而非只給一個數字，建議落地為 `sector_universe_daily_gap(trade_date, market, symbol, sector, reason)`；`reason` 目前只能誠實填 `unknown`（因為 repo 沒有停牌／暫停交易的資訊來源可以判斷「為什麼缺」），**不得**臆測成「可能停牌」這種未經查證的理由字面。
- **兩種覆蓋率都要能查（供 quant-researcher／前端使用）**：
  - **整體覆蓋率** = 該市場當日 actual / expected。
  - **族群覆蓋率** = 該產業別當日 actual / expected（groupby `security_directory.sector`）。族群覆蓋率低時（例如某族群只有 5 檔、缺 2 檔）該族群的排名可信度會下降，**門檻與是否要因此降級呈現**是 quant-researcher 的方法論決策（派工單本身已經有「命中率未顯著高於 50% 就降級措辭」的先例，覆蓋率門檻可以比照同一套治理），data-engineer 只保證分子分母資料本身是對的、可查詢。

### 8.3 回測必須含已下市櫃個股（存活者偏差）與 point-in-time 產業分類

**這是本次補充中風險最高的一項**，逐一拆解：

- **現有分類儲存是「覆蓋現值」，不是時間序列**：`SecurityDirectoryStore.apply_sectors`（`app/directory/store.py:235-276`）明文是 **UPDATE-only**，每次同步只更新「現在」的產業別，不保留舊值的生效區間；來源 `t187ap03_L` 本身也只回傳「今天」的分類，TWSE 從未提供「回溯查某公司在 2022 年的官方產業別代碼」的端點（本次查證範圍內未見，也不預期存在——分類異動通常只在官方最新名冊上生效，沒有官方回溯記錄的公開管道）。
  - **結論**：**在本次族群動能上線之前的 3～5 年回補期間，沒有任何來源能提供當時真正生效的產業分類**；唯一能做的是拿「現在的分類」往回套用到歷史每一天，這是方法論上明確的 look-ahead 風險（例如某公司 2023 年轉型、官方分類跟著改了，回測用「現在的新分類」去評價 2021 年的它，等於用未來才成立的事實去分類過去）。
  - **建議（上線後生效，不解決回補期間的缺口）**：ETL 上線那天起，改成**只增不覆蓋**的版本化表，例如 `security_sector_history(symbol, market, sector, source, effective_from, observed_on)`——每次同步偵測到分類與目前生效值不同才開一筆新紀錄（同 §6 的「新表」精神），從此往後的回測才有真正的 point-in-time 分類可用；上線前的歷史區段，**必須在交付文件與使用者可見的「歷史機率」附近明確揭露這個限制**，不得暗示回測用了「當時」的分類。這是需要寫進 ADR 的已知限制，不是 bug。
- **下市／下櫃清單缺失＝結構性存活者偏差**：`security_directory` 目前沒有「下市/下櫃」欄位或狀態（§4 已指出這是資料模型缺口）；本檔評估過的所有全市場來源——`STOCK_DAY_ALL`、TPEx mainboard、`t187ap03_L`——**都只列「現在還掛牌」的證券**。若直接拿「今天的上市櫃清單」往回抓 3～5 年歷史（無論走 §2 哪一個回補路徑），這段期間內下市的公司會被**系統性排除**。
  - 這不是效能或成本問題，是**資料完整性/誠實性**問題：下市公司通常是體質轉差、股價已重挫的公司，排除它們會讓「歷史命中率」呈現得比真實情況更好看——這與派工單裁定的「歷史機率不能是誤導性斷言，需附樣本數與失效條件」直接衝突，若不處理，等於在統計方法上先天做了對排名有利的篩選。
  - **候選來源（本次完全未查證，只列出待查方向）**：FinMind 生態圈的股票主檔／日線資料集是否連已下市代號都保留歷史日線與下市日期，是最可能的候選（因為 FinMind 定位就是「歷史資料庫」而非即時行情），但**具體 dataset 名稱、是否含下市日期欄位、免費層是否能查到已下市代號，本次沙盒完全無法確認**；TWSE／TPEx 官方是否有可程式化的「終止上市（櫃）公司名單」端點也待查。
  - **裁決點（不由本檔拍板）**：在查證結果出來前，**不能承諾族群動能的回測沒有存活者偏差**。這件事必須明確交給 product-manager／quant-researcher／CEO 決定：第一階段是否接受「已知有存活者偏差」這個限制並在畫面上加註警語，還是要先投入查證與開發成本補齊下市清單再開放回測結果對外呈現。**風控在核可任何「歷史命中率 X%」的字面前，應該把這條列為前提條件之一**。

### 8.4 除權息：全市場日線能否取得還原價或除權息日清單

- **還原價**：本檔評估過的每一個全市場／個股候選來源（`STOCK_DAY_ALL`、`MI_INDEX`（若存在）、TPEx mainboard、既有 `TwseAdapter`/`TpexAdapter`、`FinMindAdapter` 的 `TaiwanStockPrice`）在 repo 內顯示的欄位都是**原始收盤價**（`ClosingPrice`/`close` 等），沒有任何一個來源在現有 fixture 或既有 adapter 裡出現「還原後收盤價」欄位。**結論：repo 現有資料鏈沒有任何一個來源能直接取得全市場的還原價。**
- **除權息日清單**：既有 `app/dividends/providers.py`（`TWT48U_ALL`）**只涵蓋上市（TWSE）**，且模組文件明文「這是預告表，沒有歷史可以回補」（"``TWT48U_ALL`` only ever lists *upcoming* ex-dates; there is no endpoint to fetch past occurrences from"，`app/dividends/providers.py:100-107`）——也就是說即使現在開始每天同步，也只能從**上線那天起**往後累積一份上市除權息日曆，**回補不到過去 3～5 年**；上櫃完全沒有對應來源（同檔案「Coverage limitation」段落明寫上櫃留待未來、guessing 一個端點只會製造第二個未驗證的風險面）。
- **結論與緩解建議**：
  1. **無法排除歷史（回補期間）的除權息雜訊**——3～5 年回補資料無法取得還原價，也無法取得完整的歷史除權息日曆來排除，這段期間的族群動能訊號會原封不動帶著除權息造成的假跳空。
  2. **上線後可以局部緩解上市部分**：持續同步 `TWT48U_ALL`，從上線那天起為上市股累積除權息日曆，讓 quant-researcher 在**未來**的訊號計算中排除或標記這些交易日；上櫃仍無解，除非查證到 TPEx OpenAPI 或 FinMind 是否有對應的除權息 dataset（**本次完全未查證，僅為待查方向，不得假設存在**）。
  3. **方向性風險需明確告知 quant-researcher**：除權息造成的價格跳空方向性地偏向「除息後看起來下跌」，可能系統性拉低「曾經上榜族群」的表現評估，程度需要 quant-researcher 評估是否顯著到必須修正或在方法論裡揭露，data-engineer 不代為判斷影響幅度。

### 8.5 成本模型：手續費與證交稅的查證與設定檔規劃

- **本次無法查證具體稅率／費率數字**：本環境無外網，完全無法對照財政部《證券交易稅條例》、證交所／櫃買中心公告或券商手續費公開資訊確認目前生效的稅率版本與生效區間（例如當沖證交稅減半是否仍在落日期限內、ETF 與一般股票證交稅率是否仍不同）。依 skill 紅線「不憑記憶寫死費率、額度或 API 規格——查證當下文件並記錄查證日期」，**本檔刻意不寫出任何具體百分比**，避免未經查證的監理數字被直接用在使用者看得到的「扣成本後報酬」呈現上——這類數字錯誤或過期的後果，比抓錯一個資料端點嚴重得多，因為會直接扭曲對外呈現的回測結果。
- **交棒查證**：手續費／證交稅（含一般股票與 ETF 是否適用不同稅率、當沖是否有優惠稅率與其落日條款）的現行生效版本，**需 CEO 或有網路環境的人員查證官方來源並記錄查證日期**，這是本項回應唯一無法在本沙盒內完成的部分。
- **設定檔規劃（data-engineer 可先設計容器，不等稅率數字到位）**：建議比照 repo 既有「有版本、有查證日期」的慣例（`app/directory/twse_sector_codes.py` 開頭的 Provenance/Version 寫法），把費率放進一個獨立、可版本化的設定檔（存放位置與載入機制由 tech-architect 指定），每筆紀錄至少包含：

  | 欄位 | 說明 |
  | --- | --- |
  | `instrument_type` | 例如 `stock` / `etf`，因為兩者證交稅率可能不同 |
  | `side` | `buy` / `sell`（台股手續費買賣雙邊都收，證交稅目前僅賣方課徵，需查證後確認是否仍然如此） |
  | `rate` | 稅率／費率數值 |
  | `effective_from` / `effective_to` | 生效區間，`effective_to` 可為空表示現行有效 |
  | `legal_basis` | 法規／公告名稱與條號 |
  | `source_url` | 查證來源網址 |
  | `verified_at` / `verified_by` | 查證日期與查證人 |

  **這個「生效區間」設計不是形式主義**：回測若跨越稅率調整的生效日（例如當沖稅率優惠曾多次延長／到期），必須套用**當時**生效的稅率，而不是用今天的稅率去算五年前的交易成本——這與 §8.3 point-in-time 分類的精神是同一件事，都是「回測要用當時的事實，不是現在的事實」。
- **職權邊界**：稅率數字的查證與法規引用屬於待辦（列管 CEO／devops-sre 協助），設定檔 schema 與「依生效日取值」的讀取邏輯可由 data-engineer 在 tech-architect 核准儲存方案後實作；成本模型本身如何套用到回測（例如買賣各算一次、如何判定當沖）屬於 quant-researcher 的方法論範疇，本節不代為決定。

---

## 五行摘要（供交接）

1. 全市場一次性快照端點（`STOCK_DAY_ALL`、TPEx mainboard）已在 repo 驗證可用但只給「當日」資料，只能當每日增量候選，歷史回補需另找路徑。
2. 3～5 年全市場歷史回補建議走 FinMind 逐檔（唯一已驗證且效率可行的路徑，~1,850 次請求量級），TWSE/TPEx 逐月方式回補全市場要 15+ 小時不建議採用；資料量估 3 年 ~400～550MB、5 年 ~680～910MB（估算非實測）。
3. 上市產業別可直接複用既有 `t187ap03_L` 管線；**上櫃產業別 repo 完全沒有**，是本次最大的產品範圍缺口，需 CEO 查證候選端點後才能承諾交付範圍。
4. 加權指數（`^TWII`）已是現成、已驗證的基準，零額外成本；等權全市場基準也可行且不需外部依賴；櫃買指數未驗證。
5. 建議新表 `sector_universe_daily_bars`＋獨立的 (market, date) 粒度 fetch log，**不建議**沿用 `price_bars_cache`（語意與量體都不符），是否與現有 DB 同檔案、排程機制如何接入，列為需 tech-architect 出 ADR 裁決的清單（§6）。
6.（風控預審補充，§8）**最需要在開放回測前解決或明確揭露的兩項風險**：(a) 目前所有候選來源都只列現存掛牌證券，直接回補會有存活者偏差；(b) 產業分類與除權息資料都沒有歷史／point-in-time 來源，回補期間只能用「現在」的事實套用到過去——兩者查證結果出來前，不建議對外承諾回測結果無這兩類系統性偏誤；成本模型的稅率／費率數字本次同樣因無網路而未查證，未查證前不得寫死任何具體數字。

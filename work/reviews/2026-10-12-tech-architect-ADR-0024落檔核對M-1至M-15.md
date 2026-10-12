# ADR-0024 落檔核對意見 M-1～M-15（tech-architect，2026-10-12 第一次核對；coordinator 轉錄）

行號為 tech-writer 初稿 `docs/adr/0024-stock-desk-日線價格幣別閘門與代號准入.md` 的行號。若與 R-1～R-37（第二次評估）衝突，以 R 清單為準。

- **M-1 L5（狀態）**：「CEO 核可本 ADR 不以 W-a～W-d 核可為前提；W-a～W-d 與 T-5～T-9 是 F-9b 合併的前提，不是 ADR accepted 的前提（tech-architect 2026-10-12 核對回覆）。」〔已被 R-1 取代：風控第 6 題改為 T-5～T-9 裁示結果是 ADR 核可前提，T-1～T-4 字面不是〕
- **M-2 L38（Context 2 第一點）**：原句「Alpha Vantage／yfinance 為 "USD"（yfinance.py L172）」改為：「Alpha Vantage 為 `"USD"`；yfinance 個股（role 1）為 `"USD"`（`yfinance.py` L172），指數（role 2）取自 `INDEX_SYMBOL_METADATA`（L122-126），FX 路徑 `fetch_chart_closes` 為 placeholder（L242-265）；三者都不讀上游。」
- **M-3 L57（繞過者）**：改為：「繞過 `load_bars` 者：即時與 cache_only 估值器（`deps.py` L163-185，進入 `valuation.py` L451-454）；指數路徑（`IndexProviderBridge` 包在 `MarketDataService` 內，`deps.py` L131-137，**仍經服務層**，因此仍受 D-1 閘門涵蓋）。」
- **M-4 L62-71（Options）**：補回原評估兩張比較表＋`_check_currency` 處置一列（表頭註明「tech-architect 2026-10-12 原評估，任務單轉錄時未收；本次核對時補交」）。〔R-10 已擴充：改四欄並增列 E/H/F/G、I/J/K 兩組〕
  - 表 1 閘門放哪一層：A adapter 自行擋（最貼近來源／只能回報事實、快取列擋不到／不採作為閘門，adapter 負責誠實回報 D-6）；B `load_bars`（改動小／估值器不經過 `valuation.py` L451-454，最大傷害留著／不採）；C 讀快取時過濾不符列（不必動服務流程／靜默截斷序列、擋不到即時路徑／不採，即 C-2）；D API 各端點（可就地顯示原因／分散、漏掉 scheduler、alerts／不採）；**E `MarketDataService`**（唯一入口，涵蓋所有消費者含估值器、指數／建構參數改必填牽動測試／**採用**）。
  - 表 2 美股准入規則：**A 形狀白名單（採用）**（零成本、離線可做、保住 `BRK.B`／`BF.B`／`BRK-B`，AV 格式 2 字母以上字尾全擋／誤擋特別股、權證、單位，單一字母 `.L`／`.T` 擋不到／誤擋只損可用性，依 `yfinance.py` 檔頭 2026-08-16 記錄目前無美股持倉，F-9a 核實）；B 已知交易所字尾黑名單（誤擋少／漏清單外字尾、需維護／漏網即錯價）；C AV `SYMBOL_SEARCH` 查幣別（依據接近權威／吃 25 req/day、欄位待實證／離線做不了）；D 美股官方掛牌清單（最權威／新資料源需另立 ADR／範圍大）。
  - `_check_currency` 處置理由：「`check_price_bars` 整個在 app 內零呼叫；只接幣別這一項，其餘檢查（重複列、未來日期、OHLC）的處置政策屬 F-2 範圍，不在本 ADR 內接上。」
- **M-5 L93（D-4）**（核對補充，非原文，須標註）：「admission 以 `canonical_us_symbol` 正規化後的形式判斷，但不改寫傳給下游的 symbol。」「admission 與幣別規則都是必填建構參數；指數服務顯式傳入『只檢查幣別、不檢查形狀』，不得以預設值省略。」「market 查不到預期幣別時 fail-closed（回 UNAVAILABLE）。」
- **M-6 L100-102（D-5）**（核對補充）：「注入的是 market → 預期幣別的查表函式（由 `MARKET_CURRENCY` 提供），每次呼叫依該次的 `market` 參數查，不得在建構時固定成單一幣別。理由：指數服務是 TW、US 共用的同一個實例（`deps.py` L131-137，market 只是快取鍵的一個維度）。」
- **M-7 L85（D-2）**（核對補充）：「『照記 `record_attempt`』指沿用既有時點（`service.py` L184 成功、L241 全層拒答），不新增記錄點。幣別檢查必須放在 `_try_provider` 內、早於 L182 的 `cache.put`。」〔與 R-24 D-9 的標記寫入並存：記錄點不新增，L241 帶入標記參數〕
- **M-8 L127（C-1）**：「即時層（`_try_provider` 結果）＋五條快取讀出路徑：layer 0 的三個 `_cached_result` 出口（`_try_session_fresh_cache`，含 R-8 冷卻期回快取）、`_fall_back_to_cache`、`get_cached_bars`、增量抓取的合併讀回（`service.py` L191 的 `merged.bars`）。各至少一個測試。實作建議在 `_cached_result`（L446）與合併讀回兩處各設檢查點。」
- **M-9 L132（C-6）**：加「釘住測試建議放在 `tests/test_api_deps.py`（已引用 `deps._default_resolver`／`_default_index_resolver`）。」
- **M-10 L142-148（好處）**：加「被准入規則拒絕的代號不呼叫任何來源、不扣 AV 額度。現況下這類持倉每天的 scheduler 刷新（`scheduler.py` L295）都會白白耗掉一次 AV 額度。」
- **M-11 L153（壞處 2）**：改為「單一字母的 Yahoo 式字尾（如 `.L`、`.T`）形狀上與類別股（`.B`）相同，白名單無法區分。緩解：yfinance 會把 `.` 轉成 `-`（`us_symbols.py` L132-139），這類代號大概率查無資料；AV 的外國字尾慣例為 3 字母。兩者都待 F-9d 連網實證；殘留的部分由 F-9c 的 `meta.currency` 檢查補防（僅 yfinance 路徑）。」〔併 R-31 R-a〕
- **M-12 L155（壞處 4）**：以盤點取代「待查證」——production 3 處（`deps.py` L96 TW、L102 US、L131 指數）、測試 45 處 8 檔：`test_service.py` 32（helper `_service` L97-106；`_us_bar` L48-62 為 `symbol="2330"`、`market="US"`，美股准入會擋，須顯式寬鬆 admission 或改字母代號）、`test_us_market_chain.py` 3、`test_fast_fail.py` 3、`test_demo_seed.py` 2、`test_adr0019_pending.py` 2、`test_api_advice.py` 1、`test_services_index_bridge.py` 1（須傳指數用「只檢查幣別」）、`test_scheduler_data_refresh.py` 1。建議 `tests/` 共用 helper 提供「`MARKET_CURRENCY` 查表」與「全部放行 admission」兩個顯式值；production 不給預設值；不得為少改測試而設成可選。〔R-29 為摘要版〕
- **M-13 L157（壞處 6）**：「行事曆汙染併入 F-9e 處置：清除 admission 不通過序列的列，行事曆隨之修正；不在 `market_trading_days`／`market_has_session` 加幣別過濾（舊列幣別欄位寫死，無效）。F-9b 合併後應儘速執行 F-9e；執行前，『資料過舊』提示可能因外國交易日而誤報（F-9a 盤點會輸出受影響的日數）。」並補「F-9e 的 dry-run 輸出須包含『清除後各市場減少的行事曆日數』，供 CEO 判斷。」〔與 R-30 合併〕
- **M-14 L193-205（尚缺的事實）**：補「8｜美股 root 長度（1–5 個字母）的官方規格｜D-4 美股白名單｜F-9d」「9｜AV `SYMBOL_SEARCH` 是否回傳幣別欄位（後續方案 C 的前提）｜後續擴充，本 ADR 不依賴｜F-9d（可選）」。〔R-36 另增「AV 對 `.L` 的實際反應」「單一字母字尾清單」，編號請順延〕
- **M-15 L218（F-9b 驗收）**：加「qa-e2e 依 `e2e-fallback` skill 以 fixture 造出受閘門擋下的狀態（執行與判斷分離）；確認原因句可見、無價格數字、無價格單位標籤。」

## 失效條件（第一次核對意見）
- 保留 1、4、5、6。
- 第 2 條改寫：「連網實證顯示 AV 或 yfinance 會接受單一字母外國字尾並回傳非美元價格，或 `BRK.B` 類代號在任一來源的實際格式與假設不同 → 重審 D-4 美股白名單。」
- 第 3 條改寫：「連網實證顯示存在 K 以外的台股外幣計價樣式，或有 K 字尾但以 TWD 計價的合法商品（會被誤擋）→ 重審 D-4 台股樣式。」
- 新增：「新增任何不經 `MarketDataService` 取得日線價格的 production 路徑 → 重審 D-1。」「`MarketDataService` 新增快取讀出口 → C-1 必須同步補測試，否則視為閘門有缺口。」「F-9a 盤點或日後回報顯示有合法美股商品被白名單誤擋 → 重審白名單；任何代號列入例外須經 tech-architect 與風控。」「F-9c 在 F-9b 之前合併 → 視同 F7-R12 (ii) 殘留擴大，回報風控。」
- 〔第二次評估 R-34／R-35 另增 7～11；請 tech-writer 合併兩次意見並去重，最後重新編號，註明各條出處〕

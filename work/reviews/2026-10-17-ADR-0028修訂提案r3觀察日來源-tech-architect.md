# ADR-0028 r3 提案（附件 B'-3）：觀察交易日集合的輸入來源（tech-architect）

- 審查者：tech-architect（唯讀）
- 日期：2026-10-17
- 轉存：coordinator，逐字轉存 subagent 最終回報

---

# ADR-0028 r3 提案（附件 B'-3）：觀察交易日集合的輸入來源 — tech-architect

這份是唯讀評估，我沒有改任何檔案，也沒有讀 `.env` 或 `*.db`。

## 一、結論

**建議採方案 A′：在讀取側判定。** 仍然讀 `price_bars_cache` 的列，但每一列要同時通過「定案時間」「品質」「非占位」三項判準，而且同一天要有至少兩個序列，才算「確認交易日」。不改 schema，不讀市場 DB，也不動 `market_trading_days`。

- **否決 B（寫入側 `final` 旗標欄）。** 要遷移主 DB，但 ADR-0026 的 `schema_migrations` 還沒實作。而且「同一天有幾個序列」是跨列的統計，寫入時算不出來，讀取時還是得再算一次。
- **否決 C（市場 DB 的 ok bars run）。** 會牴觸已核可的 ADR-0012 C-7「持倉資料鏈不讀市場 DB」，現在有測試釘住；而且市場 DB 只有台股。
- **否決 E（維持現狀、永遠不翻轉 R4c）。** 當作基準線列出。

**對 R4b、R4c 能不能走到的影響：**
- 實作後，**R4b × observed 照建構就走不到**：證據列必須在 VS-4 之後取得，但 R4b 的時點在 VS-3 之前，而 VS-3 < VS-4。只有時鐘或參數出錯時才會出現。
- **R4c × observed 從 VS-4（台股 15:00）起才可能成立**，條件是至少兩個序列在 15:00 之後重新取得。
- R4c 仍然要等三件事都成立才能翻轉成 LM-24：D-9 實作合併、data-engineer 的確認回報經風控單項確認、qa 審查。在那之前一律維持 LM-71＋LM-26。

**順帶發現兩個問題：**
1. **ADR-0028 現行狀態機本來就有窮舉漏洞。** 非 official 日曆下，D 是週末、而且 `price_date == D` 時，沒有任何規則成立。方案 A′ 還會多一種情況：`P < price_date < D`。r3 一併補上（A-47）。
2. **ADR-0027 有同類風險。** D-7.3「大盤 T 日 bar 已經存在」和 D-8.1「聯集大盤實際有 bar 的日期」都會吃到暫定的大盤 bar。這不在 r3 範圍，列在第四節。

## 二、選項比較

### 我自己查證的程式事實
- `market_trading_days` 只做 `SELECT DISTINCT trade_date ... WHERE market=? AND trade_date BETWEEN ? AND ?`。它不排除示範資料、沒有時間條件、也沒有最少檔數（`cache.py:459-503`，SQL 在 486-493）。
- 姊妹方法 `market_has_session` 預設排除 `demo_synthetic`（`cache.py:358-378`）。
- `price_bars_cache` 每列都有 `fetched_at`。upsert 會同時覆寫價格和 `fetched_at`（`cache.py:38-54`、`219-228`），所以 `fetched_at` 就是「寫入這列現值的那次抓取」的時間。
- 寫快取的入口只有兩個：
  - `service.py:352-353`：`fetched_at = self._clock()`，預設 UTC 時鐘，見 `:264`；
  - 示範資料 `demo/seed.py:438`，source 是 `demo_synthetic`（`demo/series.py:47`）。
- `check_price_bars` 在 `app/` 內沒有任何呼叫者（`quality.py:41`）。
- 指數服務和持倉共用同一個 `_default_cache()`（`api/deps.py:172-183`）。
- VS-4 的來源：TW 15:00 Asia/Taipei、US 18:00 America/New_York（`freshness.py:109-121`）。
- 市場 DB：
  - 只寫 `market='TW'`（`market_panel.py:543-544`、`672`）；
  - 排程是平日 17:30、19:30、21:30 Asia/Taipei，另外啟動時立刻跑一次（`scheduler.py:170-173`、`659-672`）；
  - 同一個 session 已經有 ok run，之後的擷取就跳過（`pit_snapshot.py:151-153`）；
  - 暖身回補每一天寫一個單檔的 ok run，不檢查覆蓋率（`market_panel.py:633-689`）；
  - 交易日要經 FinMind 交叉比對（`twse_snapshot.py:316-350`）。
- ADR-0012（accepted）C-7 有測試：`app.portfolio.*`、`app.api.portfolio`、`app.services.market` 都不可達 `app.data.market_panel`（`tests/test_market_panel_boundary.py:127-151`）。
- `session_calendar.py`、`close_state.py`、`market_hours.py` 都還不存在。所以這次沒有既有實作要遷移。
- ADR-0026 是 proposed；backend 內 grep 不到 `schema_migrations`。

### 比較表

| 方案 | 做法 | schema／遷移（與 ADR-0026 的關係） | R4b × observed | R4c × observed | 測試守門 | 主要風險 |
|---|---|---|---|---|---|---|
| **A′ 讀取側判準（建議）** | 新增唯讀方法 `market_session_evidence` 回傳原始列；純函式依 SE-1～SE-6 加支持度分類；VS-4 與 R3 共用 `final_after` | **零**：不加欄、不改 DDL，不需要 `schema_migrations`，也不受 ADR-0026 進度影響 | 走不到（VS-3 < VS-4，而且證據列的 `fetched_at` 不晚於 now）；只在異常時出現 | 15:00 起，至少兩個序列在定案時間後重抓就成立 | 分類器表格測試（每個判準各一個「只違反這一條」的 fixture）；三態日曆測試；R4b 走不到的性質測試；`final_after` 只能有一個定義（grep）；`market_trading_days` 既有測試不改；C-7 import graph 不變 | 讀取成本比 DISTINCT 大（有窗口上限）；依賴 VS-4 正確（和 R3 同一個假設，見 F-3）；書很小時一直停在 weekday_assumed |
| B 寫入側 `final` 旗標欄 | `price_bars_cache` 加 `final_evidence`，由 `service.py` 寫入時計算 | 要在主 DB `ALTER TABLE ADD COLUMN`。依 ADR-0026 D-6.6 要新立 component（例如 `price_cache`，擁有 cache 與兩張 log），v1、v2（ADR-0019 的 `tail_fetched_at`）以 inferred 補記，v3 才是旗標；還要做遷移前整檔備份。ADR-0026 尚未實作，所以只能等它，或像 ADR-0019 D-3 那樣臨時 ALTER，但 ADR-0026 已經否決臨時 ALTER（D3 選項） | 同 A′ | 同 A′ | 除了 A′ 的全部測試，還要加：旗標與判準不漂移；遷移回填（inferred）；trigger 和備份 | 有兩個真相來源；支持度仍要在讀取時算；VS-4 一旦依 F-3 改成 (market, source) 鍵就要再回填一次；示範資料寫入者要記得寫 0 |
| C 市場 DB ok bars run，加 `recorded_at ≥ VS-4` | 確認日＝`pit_snapshot_runs` 中 `kind='bars'`、`status='ok'`、`recorded_at ≥ final_after` 的 session | 市場 DB 不改 schema（`recorded_at` 已有），但市場 DB 本來也沒有 `schema_migrations` | 走不到 | 最早要到 17:30（排程）；排程沒有常駐就永遠到不了；只有台股 | 要先修訂 ADR-0012 C-7、T-3 和既有測試，才能寫測試 | **牴觸 accepted 的 C-7**，要 CEO 修訂；美股沒有來源；啟動時跑得太早又被 `_already_ok_today` 凍結的 session，會永久變成未確認，要改 `pit_snapshot`（ADR-0012 的範圍）；暖身回補的單檔 ok run 證據強度不同 |
| D 方案 A′ 與 C 的聯集（台股） | 兩邊確認日取聯集 | 同 C | 走不到 | 15:00 起 | 兩套守門都要 | 同 C 的 C-7 牴觸；複雜度最高 |
| E 維持 DISTINCT，永遠不翻轉 | 不改 | 零 | **到得了**（暫定 bar） | 到得了，但永遠只用 LM-71＋LM-26 | 無新增 | 占位列與暫定列繼續汙染 P 和 `lag_sessions`（ADR-0016 L216 已知限制）；observed basis 永遠只是名義上的區分 |

### 建議 A′ 的理由
1. 唯一不改 schema、也不牴觸 accepted ADR 的方案。ADR-0012 C-7、ADR-0016 F5、ADR-0009、ADR-0024 都依賴 `market_trading_days`，A′ 完全不動它們。
2. 「定案」只有一個判準：R3 判定 `close` 和日曆證據都用 `final_after(market, d)`。不會出現兩種定案的定義。
3. 台股、美股都適用。美股的字面一律是 LM-72，但 P、R5、`lag_sessions` 的正確性都會改善。
4. 方向單調：把常數調嚴（支持度提高、排除更多來源）只會更保守。之後要放寬，才需要送風控。
5. 把 r2' A-38 的 WARNING 從「預期可達」變成「異常訊號」，風控要求的「拿掉不可達註記」在 r3 實作後可以改寫成精確的說法。

### 為什麼要三態，而不是只換一個集合
如果只把集合換成「確認日」，那些只有暫定列的真實交易日，會在日曆範圍內被判成休市。結果 P 往前跳過那一天，`price_date` 落在 (P, D) 之間，沒有規則承接。所以未確認日改用週一至週五推定，basis 標 weekday_assumed。

### 關於「通過品質檢查」
A′ 只在**讀取側**對日曆證據套用 `check_price_bars` 的 OHLC 檢查，不接到寫入閘門。寫入閘門牽涉 ADR-0009 和 ADR-0024 的降級梯子，要另案處理。

### 和 ADR-0019 的關係
A′ 讀的是列層的 `fetched_at`，問的是「這一列的現值是不是在定案時間後寫入」。ADR-0019 L280 否決的是「用列的 `fetched_at` 推導序列的取得時間」，兩者不同。A′ 也不顯示這個時間（K-13），K-9 談的是 coverage 判定，同樣不受影響。

## 三、建議修訂文字（交 tech-writer；編號接續 r2'，從 A-42 起）

> 前提：先套用 r2' 的 A-38～A-40，再套用本節（理由見第四節）。修訂紀錄依 r1 的慣例保留被取代的原文。

**A-42｜文首**
- 在「r1 修訂」下一行新增：
  `- r3 修訂：2026-10-17，依 tech-architect 修訂提案 A-42～A-53（附件 B'-3：觀察交易日集合的輸入來源）`
- 在「與既有 ADR 的關係」新增四點：
  - **ADR-0012（accepted）**：遵守 C-7。`ObservedSessionCalendar` 不讀市場 DB（D-9 第 7 點）。
  - **ADR-0016、ADR-0009、ADR-0024**：`market_trading_days`、`market_has_session` 的語意與 SQL 不變（CS-18）。
  - **ADR-0019**：D-9 讀列層的 `fetched_at`，只用來判斷這一列是不是證據。它不是序列的取得時間，也不得顯示（K-13）；K-9 不受影響。
  - **ADR-0026**：本 ADR 不新增欄位、不改 DDL，不採用 `schema_migrations`。

**A-43｜Context 新增一點（放在「日曆」之後）**
- **觀察日曆現況**（r3）：
  - `market_trading_days` 是 `SELECT DISTINCT trade_date`，不排除示範資料、沒有時間條件、沒有最少檔數〔事實：`app/data/cache.py:459-503`〕；`market_has_session` 則排除 `demo_synthetic`〔事實：`:358-378`〕。
  - upsert 同時覆寫價格與 `fetched_at`〔事實：`:219-228`〕。live 寫入者只有 `service.py`，`fetched_at` 取服務時鐘〔事實：`app/data/service.py:352-353`〕。
  - `check_price_bars` 在 `app/` 內沒有呼叫者〔事實：`app/data/quality.py:41`〕。
  - 指數序列和持倉共用同一份快取〔事實：`app/api/deps.py:172-183`〕。
  - 市場 DB 只有台股，排程是平日 17:30／19:30／21:30，另外啟動時跑一次〔事實：`app/data/market_panel.py:543-544`、`app/scheduler.py:170-173,659-672`〕。持倉鏈不可達市場 DB〔事實：ADR-0012 C-7；`tests/test_market_panel_boundary.py:127-151`〕。

**A-44｜Options：新增第三張表「觀察交易日集合的輸入來源」（r3）**

| 方案 | 優點 | 缺點 | 風險 |
|---|---|---|---|
| **A′ 快取列，加上讀取側的定案、品質、占位判準與支持度（採用）** | 零 schema；不牴觸 C-7；台股美股都適用；和 R3 共用定案判準 | 讀取成本比 DISTINCT 大；書很小時停在 weekday_assumed | 依賴 VS-4 正確（F-3） |
| B 寫入側 `final` 旗標欄 | 查詢簡單 | 主 DB 遷移要先有 ADR-0026；支持度仍要在讀取時算；有兩個真相來源 | 漂移；VS-4 改鍵就要再回填 |
| C 市場 DB ok bars run，加 `recorded_at ≥ VS-4` | 全市場覆蓋率 ≥ 0.98，經 FinMind 自證 | 牴觸 ADR-0012 C-7；只有台股；最早 17:30 | 啟動時太早的 run 被凍結，該日變成永久未確認 |
| D A′ ∪ C | 證據最多 | 同 C，而且最複雜 | 同 C |
| E 維持 DISTINCT，不翻轉 | 零成本 | R4b 到得了；占位列繼續汙染 P | observed 只是名義上的區分 |

**A-45｜D-1 `session_calendar.py` 的第二個子點，整句取代**
- 原文：「`ObservedSessionCalendar` 包裝現有的 `TradingCalendar`，不改它的語意。」
- 新文：「`ObservedSessionCalendar` 依 D-9 由確認證據建構。日曆範圍內的休市判定，交給只餵確認日的 `TradingCalendar`；未確認日另外處理（D-9 第 5 點）。`TradingCalendar` 本身的語意不變（CS-8）。」

**A-46｜新增 §D-9（放在 D-8 之後）**

### D-9 觀察交易日集合的輸入（r3，附件 B'-3）
1. **唯一來源**：
   - `PriceBarCache` 新增唯讀方法 `market_session_evidence(market, start, end) -> tuple[SessionEvidenceRow, ...]`。它原樣回傳 `[start, end]` 內該市場每一列的 `(symbol, trade_date, open, high, low, close, volume, source, fetched_at)`，不做過濾也不做分類。
   - 分類由 `session_calendar.py` 的純函式 `classify_session_evidence(rows, *, market, now) -> SessionEvidence` 負責。`SessionEvidence = {confirmed: frozenset[date], unconfirmed: frozenset[date]}`。
2. **一列算證據的條件**（SE-1～SE-6 全部成立）：
   - **SE-1**：`source` 不在 `NON_EVIDENCE_SOURCES`（v1 = {`demo_synthetic`}）。
   - **SE-2**：`final_after(market, trade_date) ≤ fetched_at ≤ now`。
     - `final_after` ＝ `trade_date` 當地日期的 VS-4（引用 `policy_for(market).publish_cutoff`），時區用 VS-1。
   - **SE-3**：`check_price_bars([該列])` 沒有 `OHLC_INVALID`。直接重用 `app.data.quality`，不另寫一份。
   - **SE-4**：`volume > 0`，用來排除占位列。
   - **SE-5**：不是指數序列。v1 以代號開頭為 `^` 判定，待 data-engineer 確認。
   - **SE-6**：`fetched_at` 可以解析，而且帶時區。
3. **支持度**：某天至少有 `SESSION_EVIDENCE_MIN_SERIES`（v1 = 2）個不同 symbol 各有一列證據，才算 **confirmed**。
4. **三態**：
   - **confirmed**：見第 3 點；
   - **unconfirmed**：那天至少有一列不是示範資料，但沒達到 confirmed；
   - **absent**：其餘。
5. **日曆語意**：令 R ＝ [min(confirmed), max(confirmed)]；confirmed 為空時，R 為空。

| 那一天 | `is_session` | `basis_for` |
|---|---|---|
| ∈ confirmed | True | observed |
| ∈ unconfirmed | 週一至週五規則 | weekday_assumed |
| ∈ R，而且是 absent | False | observed |
| ∉ R | 週一至週五規則 | weekday_assumed |

   `previous_session`、`next_session` 都依上表的 `is_session` 逐日推。`OfficialSessionCalendar` 退回時，用的就是這份日曆。
6. **讀取次數與窗口**：
   - 每次 build，每個市場最多呼叫一次 `market_session_evidence`；
   - `end = D`，`start = max(該市場各列 price_date 的最小值 − 7 日, D − 400 日)`；
   - 超出窗口的 `lag_sessions` 依 R6 給 null。
7. **不採用的輸入**：
   - `market_trading_days`：語意不變，留給既有消費者；
   - 市場 DB：ADR-0012 C-7；
   - `price_bars_fetch_log`、`price_bars_attempt_log`：那是序列的 coverage，不是交易日證據。
8. **和 R3 同一個判準**：R3 的「`acquired_at ≥ D 的 VS-4`」改寫成「`acquired_at ≥ final_after(market, D)`」。R3 和 SE-2 呼叫同一個函式。
9. **名詞**：本 ADR 的 basis＝observed 指上表的 confirmed，或 R 內的 absent。它和 ADR-0027 D-8 的「觀察日」（市場 DB ok bars ∪ 大盤 bar）是不同資料鏈的不同定義，互不替代。這是 C-7 造成的，屬於刻意的設計。

**A-47｜D-4 狀態機：改 R2″，新增 R2‴**
- **R2″ 改**：
  - 原條件「`basis == official`、D 不是交易日，而且 `price_date == D`」，改成「D 不是交易日（任何 basis），而且 `price_date == D`」。
  - 狀態仍是 `date_anomaly`。`sub_reason` 依 basis 分成 `official_conflict` 與 `not_a_session`。
  - 理由：原表在非 official basis、D 是週末、而且 `price_date == D` 時，沒有規則成立。
- **R2‴ 新增**（放在 R2″ 之後、R3 之前）：

| 規則 | 條件 | 狀態 | `reference_date` |
|---|---|---|---|
| **R2‴（r3 新增）** | P 不為 None，而且 `P < price_date < D` | `date_anomaly`，`sub_reason = unconfirmed_session`，記 WARNING（列的日期落在日曆不認為是交易日的日子，例如週末的暫定列，或示範列） | price_date |

- 表後補一句：「`date_anomaly` 的 `sub_reason`（`future_date`／`before_open`／`official_conflict`／`not_a_session`／`unconfirmed_session`）只用於 log 和 CS-11 的窮舉；字面一律是 LM-70。」
- 表後再補一句：「R0～R6 對 `price_date` 相對於 (P, D) 的位置必須窮舉，由 CST-2 的性質測試釘住。」

**A-48｜D-5：改寫 r2' A-38 的表後三點**（兩列表格不變）
- **第一點，原文**：「R4b 這一列，以現行程式來說是到得了的……不是『不可達』的斷言。」
  **新文**：
  - R4b × observed：D-9 實作之前（現行 `market_trading_days` 口徑）是到得了的。
  - D-9 實作之後，SE-2 要求 `fetched_at ≥ final_after(D)`、`fetched_at ≤ now`，而 R4b 要求 now < VS-3 < VS-4，所以只有時鐘或參數出錯時才可能出現。
  - 這一列的 LM-71＋LM-26 與 WARNING 保留，當作縱深防禦；WARNING 代表異常。
- **第二點，原文**：「R4c 的切換：翻轉這一列的 PR 合併之前，data-engineer 的確認回報……只經 qa 審查不夠。」
  **新文**：翻轉 R4c × observed 為 LM-24 的 PR，要以下三點都成立才可以合併：
  - (a) D-9 已經實作合併，CST-5～CST-8 綠燈；
  - (b) data-engineer 的確認回報經風控單項確認。回報至少要含：
    - Phase 1 探測 §6.3 至少三輪的結果，證明所用來源在 VS-4 之後回傳的當日 bar 都是定案值（F-2、F-3 沒有觸發）；
    - §6.4 唯讀複本診斷 A～D 的數字；
    - SE-4、SE-5 的確認；
  - (c) qa 審查。只經 qa 審查不夠。
- **第三點，原文**：「觀察日集合的輸入來源還沒決定（附件 B'-3）。決定之前，R4c × observed 不會切換。」
  **新文**：「觀察日集合的輸入來源依 D-9（r3）。」

**A-49｜D-6 新增第 7～10 點**
7. （r3）VS-4 之後、但還不到兩個序列在定案時間後重抓之前（通常是盤後資料刷新跑完之前），當日 basis 仍是 weekday_assumed，台股顯示 LM-71＋LM-26。方向保守。
8. （r3）只有暫定列、而且從沒在 VS-4 之後重抓的日期，依週一至週五推定。如果那天其實休市（例如來源在假日送出占位列），`lag_sessions` 可能多算一天。現行口徑也一樣，不是退步。
9. （r3）指數列不算證據。持有的台股只有一檔時，永遠達不到支持度 2，basis 一律是 weekday_assumed。
10. （r3）`check_price_bars` 只在讀取側用於日曆證據，不擋寫入。寫入側的品質閘門另案處理。

**A-50｜對實作的約束：新增 CS-17～CS-24**
- **CS-17**：`final_after(market, trade_date)` 只有一個定義，放在 `session_calendar.py`，引用 VS-1、VS-4。R3 和 SE-2 都呼叫它。其他模組不得出現 `publish_cutoff` 與 `trade_date` 或 `acquired_at` 的行內比較（grep）。
- **CS-18**：`market_trading_days`、`market_has_session` 的 SQL 與 docstring 語意不變（`tests/test_market_calendar_staleness.py` 等既有測試不修改，而且要綠燈）。`session_calendar.py` 不得呼叫 `market_trading_days`（grep）。
- **CS-19**：`ObservedSessionCalendar` 的唯一資料來源是 `market_session_evidence`，經 `classify_session_evidence` 分類。`session_calendar.py`、`close_state.py` 和 `app.portfolio.*` 不可達 `app.data.market_panel`（沿用 ADR-0012 T-3 的測試）。`session_calendar.py` 不讀兩張 log 表（grep）。
- **CS-20**：`price_bars_cache` 的寫入者只有 `app/data/service.py` 和 `app/demo/seed.py`（AST／grep 列舉 `.put(` 的呼叫點）。新增寫入者要先修訂本 ADR，因為 SE-2 的前提是 `fetched_at` 就是寫入當下的時鐘。
- **CS-21**：`NON_EVIDENCE_SOURCES`、`SESSION_EVIDENCE_MIN_SERIES` 和 SE-5 的判定，各自只定義一次。測試斷言 `NON_EVIDENCE_SOURCES ⊇ {app.demo.series.DEMO_SOURCE}`。往放寬方向改（降低支持度、納入指數、移除 SE-4），要先經風控單項確認；常數註解要寫明這一點。
- **CS-22**：每次 build，每個市場最多一次 evidence 讀取，`now` 和 CS-3 是同一次時鐘讀值（測試計數）。
- **CS-23**：本 ADR 不改 `price_bars_cache` 的 DDL，也不寫 `schema_migrations`。測試以 `sqlite_master` 斷言 DDL 和改動前相同。
- **CS-24**：每個市場都必須 VS-2 < VS-3 < VS-4（`market_hours` 的測試）。這是「R4b × observed 照建構走不到」的前提。

**A-51｜測試要求：新增 CST-5～CST-8；CST-2 補一句**
- **CST-2 補**：再加一個性質測試：對任意 (P, D, price_date)，R0～R6 恰好一條成立（含 R2″ 改寫和 R2‴）。
- **CST-5**：分類器的表格測試。
  - SE-1～SE-6 每一條各一個「只違反這一條」的 fixture；
  - TW 邊界：14:59:59+08:00 不算證據，15:00:00+08:00 算；
  - US 邊界：18:00 America/New_York，夏令與冬令各一例；
  - 支持度 1 對 2；
  - `fetched_at > now`；
  - 同一列 10:30 先寫入、16:00 被 upsert 覆寫後變成證據；
  - 指數列的 volume 為 0。
- **CST-6**：三態日曆的測試。confirmed、unconfirmed、R 內 absent、R 外，四種日子分別對 `is_session`、`basis_for`、`previous_session` 驗證。
- **CST-7**：可達性測試。
  - R4c × observed：台股 15:00:00 時有兩個序列的證據，就成立；
  - R4b × observed：在 `fetched_at ≤ now` 而且 CS-24 成立的前提下，任何輸入都不會出現（性質測試）。
- **CST-8**：回歸測試。既有的 playbook、price_change、market calendar staleness 測試不修改，而且要綠燈（CS-8、CS-18）。

**A-52｜失效條件、待決事項、未查證事項**
- **失效條件新增**：
  - **F-7**：§6.3 發現某個所用來源在 VS-4 之後仍回傳未定案的 bar。走 F-3，把 VS-4 升級成 (market, source) 鍵；已翻轉的 R4c 退回 LM-71＋LM-26，直到重新確認。
  - **F-8**：ADR-0012 C-7 被修訂、允許持倉鏈讀市場 DB 時，重新評估方案 C／D。
  - **F-9**：寫入側接上品質閘門時，重新檢查 SE-3、SE-4 是否變成重複，但不得因此刪除。
- **待決事項新增**：
  - **風控**：r3 設計的單項確認（見第五節第 1 點）；R2″ 改寫、R2‴ 對應 LM-70 是否屬實。
  - **data-engineer**：SE-4、SE-5 的確認；R4c 翻轉前的確認回報內容（依 A-48）。
  - **CEO**：知悉方案 C 被否決，因此 ADR-0027 和 ADR-0028 對「觀察日」各用不同定義。
- **未查證事項新增**：SE-5 以 `^` 開頭判定指數〔推論〕；各來源在真實交易日時 volume 的語意〔未查證〕。

**A-53｜修訂紀錄**
- 新增 r3 區塊：「r3（2026-10-17）依 tech-architect 修訂提案 A-42～A-53（附件 B'-3）套用。」
- 被取代的原文要逐字保留：A-45 的 D-1 子句、A-47 的 R2″ 條件、A-48 的 r2' A-38 三點。其餘各條是新增，沒有被取代的原文。

## 四、相依與排序

1. **和 r2'（A-22～A-41）沒有內容衝突，但有先後順序。**
   - r3 改寫 r2' A-38 表後的三點，並延伸 A-39 的翻轉條件，所以要**先套用 r2'，再套用 r3**。
   - r3 只讓條件更嚴：多加「D-9 已實作」這個翻轉前提，並且說清楚 R4b 能不能走到。所以不會放寬 A-38、A-39 已經過風控的條件。
   - r2' 等待風控確認的 A-36 只影響 ADR-0027。coordinator 可以決定讓 ADR-0028 的部分（A-38～A-40）先套用，或者 r2' 整批套用後再套 r3，兩種都不影響 r3 的內容。
   - **A-39（CS-12 的 observed 段）建議在套用 r3 時補一句**：「並且 D-9 已實作（A-48 (a)）」。這一句我併在 A-48 的 (a)，tech-writer 套用時請在 CS-12 加上對 A-48 的引用。
2. **實作順序**：
   - D-9 要和 `ObservedSessionCalendar` 第一次實作放在同一個 PR（T1-17 系列）。現在還沒有實作，所以沒有舊口徑要遷移。
   - 翻轉 R4c 是之後另開的 PR。
3. **資料**：§6.3 要在交易日分時段跑，最早 2026-10-19（週一，以官方休市表為準）。之後 data-engineer 出確認回報，送風控單項確認，才能翻轉。
4. **ADR-0026**：A′ 和它沒有相依；只有改選 B 才會卡在 ADR-0026 核可與實作之後。
5. **ADR-0027（不在 r3 範圍，建議另外修訂）**：
   - D-7.3「大盤 T 日 bar 已經存在」、D-8.1「聯集大盤實際有 bar 的日期」用的大盤 bar 來自同一份快取，會被盤中的暫定 bar 滿足。
   - data-engineer 回報 `judge()` 在 15:00 後看到最新日的 bar 就不再重抓〔轉引 data-engineer 回報 L21-23，我沒有重讀 `judge`〕。
   - 這表示 T 日的大盤收盤，可能是暫定值，進入 PIT 輸入。
   - 另外，啟動時的 capture 加上 `_already_ok_today`（`scheduler.py:671-672`、`pit_snapshot.py:151-153`），可能凍結一個太早的 ok run。
   - 建議 ADR-0027 下一輪修訂把大盤 bar 這一項改成「`fetched_at ≥ final_after(TW, T)`」，直接引用本 ADR 的 CS-17。要的話我可以另外起草。這件事不擋 r3。

## 五、待確認事項

1. **風控（單項確認）**：
   - (a) SE-1～SE-6 加上支持度 2，作為設計，是否滿足你的條件「只來自通過品質檢查的最終日線，不含盤中、暫定或占位列」。這只是設計層的確認；翻轉 R4c 仍然要你確認 data-engineer 的實測回報。
   - (b) 未確認日改用週一至週五推定、basis 標 weekday_assumed、顯示 LM-71＋LM-26，可不可以接受。
   - (c) R2″ 擴大到非 official、新增 R2‴，都對應 LM-70。LM-70 在「列的日期落在未確認日或非交易日」時讀起來是否屬實；如果不屬實，要另外請 creative-lead 起草片段。
   - (d) 支持度要 1 還是 2。我建議 2：提高門檻只會讓字面更保守，不會讓字面不實。
   - (e) CS-21：之後任何放寬都要送你。
2. **data-engineer**：
   - (a) 快取中所有指數序列的代號是否都以 `^` 開頭（SE-5）；
   - (b) TWSE、TPEx、FinMind、Yahoo 在真實交易日會不會給 `volume = 0`（例如指數或冷門股），假日的占位列是否 `volume = 0`（SE-4）；
   - (c) §6.3 的判讀矩陣要加一欄：VS-4 之後的當日 bar 是否已定案（F-7）；
   - (d) §6.4 用唯讀複本試算新口徑：DISTINCT 和 confirmed 的日期差異、未確認日有幾天、15:00 之後達到支持度 2 的時間分布；
   - (e) 確認服務時鐘一律帶時區（SE-6）。
   - 確認回報依 A-48 (b) 的內容送風控。
3. **quant**：確認 r3 不影響事先宣告的任何登記定義。事先宣告的 σ_d 和稽核都讀市場 DB，不讀 `ObservedSessionCalendar`；ADR-0027 的 `next_session(T)` 是對未來日期，推定規則不變。我推論沒有影響，請確認。
4. **CEO**：
   - (a) 核可採 A′：不加表，不修 ADR-0012；
   - (b) 知悉 ADR-0027 和 ADR-0028 的「觀察日」定義不同，原因是 C-7；
   - (c) 知悉 D-6 第 7 點：盤後資料刷新之前會多一段時間顯示「未能確認」類的字面。PM 也要一併知悉。
5. **dev-lead**（實作時）：D-9 第 6 點的窗口數值（−7 日／400 日）可以在 PR 中依實測調整，但 CS-22「每市場一次讀取」不得違反；有調整就在 PR 中說明並交 qa。

---

**驗證與範圍**：
- **親自讀過**：
  - ADR-0028 全文；
  - r2' 提案全文；
  - 風控附件 B 確認全文；
  - data-engineer 回報全文；
  - ADR-0026 D-6 相關段落（grep）、ADR-0019 D-3～K-13、ADR-0012 C-1／C-7／C-8／T-3（grep）、ADR-0027 D-7、D-8；
  - 程式：`cache.py` 全檔、`services/market.py`、`data/calendar.py`、`data/quality.py`、`data/freshness.py:60-128`、`data/service.py:300-379`、`market_panel.py:1-170, 460-800`、`services/pit_snapshot.py:1-300`、`twse_snapshot.py:25-364`、`scheduler.py:167-176, 600-715`、`api/deps.py:160-184`、`tests/test_market_panel_boundary.py:120-152`；
  - grep：`market_trading_days`、`.put(` 的呼叫點、`DEMO_SOURCE`、`schema_migrations`、三個新模組是否存在。
- **轉引、未自行查證**：`judge()` 在 15:00 後不重抓（data-engineer L21-23）；各轉接器沒有過濾當日暫定 bar（L20-22）。
- **沒做的事**：沒有跑任何程式、測試或 git，沒有連網，沒有修改任何檔案，沒有讀 `.env` 或 `*.db`。
- 這是唯讀的架構文件，Codex 不適用。

**相關檔案**
- /home/user/AICompany/docs/adr/0028-stock-desk-估值狀態判定與交易所時段參數.md
- /home/user/AICompany/work/reviews/2026-10-17-ADR-0027與0028修訂提案r2prime-tech-architect.md（A-38～A-40）
- /home/user/AICompany/work/reviews/2026-10-17-ADR-r2附件B單項確認-風控.md（L136-140）
- /home/user/AICompany/work/reviews/2026-10-17-探測指令補查項-data-engineer回報.md（L12-23）
- /home/user/AICompany/apps/stock-desk/backend/app/data/cache.py（L38-54、L219-228、L358-378、L459-503）
- /home/user/AICompany/apps/stock-desk/backend/app/data/service.py（L264、L352-353）
- /home/user/AICompany/apps/stock-desk/backend/app/data/quality.py（L41-63）
- /home/user/AICompany/apps/stock-desk/backend/app/data/freshness.py（L109-121）
- /home/user/AICompany/apps/stock-desk/backend/app/data/market_panel.py（L543-544、L633-689）
- /home/user/AICompany/apps/stock-desk/backend/app/services/pit_snapshot.py（L151-153）
- /home/user/AICompany/apps/stock-desk/backend/app/scheduler.py（L170-173、L659-672）
- /home/user/AICompany/apps/stock-desk/backend/tests/test_market_panel_boundary.py（L127-151）
- /home/user/AICompany/docs/adr/0012-stock-desk-族群動能與全市場日線.md（C-7 L793、T-3 L875）
- /home/user/AICompany/docs/adr/0026-stock-desk-庫存版本化軟刪除與還原點.md（D-6 L282-301）
- /home/user/AICompany/docs/adr/0027-stock-desk-預測紀錄帳-儲存-PIT輸入-排程與定義登記.md（D-7.3 L312、D-8.1 L335）

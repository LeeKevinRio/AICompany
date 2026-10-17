# ADR-0028：stock-desk 估值狀態判定與交易所時段參數

- 狀態：proposed
- 日期：2026-10-16
- 決策者：tech-architect（草案）；待 CEO 核可。立案依據：T1-01／T1-02 評估附件 B-8；coordinator 分配編號〔事實：`work/reviews/2026-10-16-T1-01與T1-02-tech-architect評估.md:4,320-335`〕。
- r1 修訂：2026-10-16，依 tech-architect 修訂提案 A-1～A-21
- r2 修訂：2026-10-17，依 tech-architect 修訂提案 A-22～A-41
- r3 修訂：2026-10-17，依 tech-architect 修訂提案 A-42～A-53（附件 B'-3：觀察交易日集合的輸入來源），含 r3′ 補正（風控 r3 單項確認 R-1～R-3、S-1～S-5）
- 適用範圍：僅 product/stock-desk。
- 與既有 ADR 的關係：
  - 不取代任何 ADR。
  - **ADR-0009**：引用 D-2 的 `publish_cutoff`，不修訂。
  - **ADR-0014**：遵守 D-7(d)、I-10、D-11。
  - **ADR-0019**：與 D-4、D-5 的單一取得時間基準一致，不讀 `tail_fetched_at`。
  - **ADR-0016**：AC-B5a-6 依 D-8 的 `change_mode` 判斷。
  - **ADR-0025**：是 AV-1 的延伸，實作 D-9 休市日、F-6 與 D-12 Phase 1。
  - **ADR-0027（同批）**：本 ADR 提供 `SessionCalendar` 與 VS-6，由 ADR-0027 使用。
    - T1 評估 B-3 原本寫「AV-17 共用 VS-2」〔轉引 `:247`〕。ADR-0027 M-1 核可後改用 VS-6；M-1 駁回時仍用 VS-2。
  - **ADR-0012（accepted）**：遵守 C-7。`ObservedSessionCalendar` 不讀市場 DB（D-9 第 7 點）。
  - **ADR-0016、ADR-0009、ADR-0024**：`market_trading_days`、`market_has_session` 的語意與 SQL 不變（CS-18）。
  - **ADR-0019**：D-9 讀列層的 `as_of` 與 `fetched_at`，R3 另外讀當日 bar 的 `PriceBar.as_of`。這些時間都只用來判斷「是否定案」，一律取較早者（CS-17）。它們不是序列的取得時間，不取代 `acquired_at`（ADR-0019 D-5），也不得顯示（K-13）。K-9 不受影響。
  - **ADR-0026**：本 ADR 不新增欄位、不改 DDL，不採用 `schema_migrations`。
- 標註約定同 ADR-0027。

---

## 評估摘要
- **採用**：證據優先、時鐘為輔。
  - 新增純函式 `app/data/close_state.py`，由 `build_summary` 逐列呼叫。
  - 新增純常數模組 `app/data/market_hours.py`；新增 `app/data/session_calendar.py`（protocol，官方與觀察兩種實作）。
  - 前端只把列舉值對應到字面。
- **補兩個設計缺口**（風控第一批 2.18 節）：
  - 交易日開盤前另立狀態 `pre_open`，不得套用 LM-27。
  - 推算模式下，平日不即時標「休市」（不變式 CS-9）。另新增 `session_basis` 欄位，處理推算模式下「今天其實沒開市」時，LM-27、LM-24 會失真的問題。
- **否決**：
  - 只靠時鐘推算；
  - 放在 `valuation.py`；
  - 由前端推算；
  - 重用 `intraday_session`。

## Context（背景）
- **PRD 的要求**：四種狀態與 AC-B5a-1～6〔事實：`work/stock-desk-新定位-PRD-2026-10-16.md:252-268`〕；官方休市日 NP-B5b〔`:270-277`〕。
- **估值器的時鐘**：
  - 估值器預設時鐘是 UTC，`today = self._clock().date()`〔事實：`app/portfolio/valuation.py:343,382`〕；`build_summary` 另外又讀一次時鐘〔事實：`app/portfolio/summary.py:206`〕。
  - 〔推論〕台北 00:00～08:00 時，UTC 日期是前一天。所以狀態判定的 D 不得取自估值器的 `today`。
- **現有常數**：
  - 09:00 開盤常數，標示未查證〔事實：`app/data/quote_params.py:29-32`〕；
  - P-6 的 13:25 是盤中報價的試撮避讓點，不是收盤時間〔事實：`:46-50`〕；
  - TW 的 `publish_cutoff` 是 15:00、US 是 18:00〔事實：`app/data/freshness.py:109-121`〕；
  - `latest_completed_session` 只看週一至週五〔事實：`:83-89`〕。
- **日曆**：已知範圍之外改用週一至週五規則〔事實：`app/data/calendar.py:74-85`〕；playbook 依賴這個推定〔事實：`:39-43`〕。
- **觀察日曆現況**（r3）：
  - `market_trading_days` 是 `SELECT DISTINCT trade_date`，不排除示範資料、沒有時間條件、沒有最少檔數〔事實：`app/data/cache.py:459-503`〕；`market_has_session` 則排除 `demo_synthetic`〔事實：`:358-378`〕。
  - upsert 同時覆寫價格與 `fetched_at`〔事實：`:219-228`〕。live 寫入者只有 `service.py`，`fetched_at` 取服務時鐘〔事實：`app/data/service.py:352-353`〕。
  - `check_price_bars` 在 `app/` 內沒有呼叫者〔事實：`app/data/quality.py:41`〕。
  - 指數序列和持倉共用同一份快取〔事實：`app/api/deps.py:172-183`〕。
  - 市場 DB 只有台股，排程是平日 17:30／19:30／21:30，另外啟動時跑一次〔事實：`app/data/market_panel.py:543-544`、`app/scheduler.py:170-173,659-672`〕。持倉鏈不可達市場 DB〔事實：ADR-0012 C-7；`tests/test_market_panel_boundary.py:127-151`〕。
  - 每列另有 `as_of`。它是日線轉接器在呼叫開始、送出請求之前讀的時鐘〔事實：`app/data/cache.py:50、207、227`；`app/data/providers/twse.py:88`〕。`fetched_at` 則是 provider 回傳之後才讀的服務時鐘〔事實：`app/data/service.py:352-353`〕。所以一次跨越 VS-4 的抓取，`fetched_at` 會晚於資料實際被取得的時間。
  - R3 的 `acquired_at` 是序列層的 `ProviderResult.as_of`，走快取路徑時是 `tail_fetched_at`〔事實：ADR-0019 D-4、D-5〕。如果後來那次完整抓取沒有回傳當日 bar，當日那一列不會被覆寫，`acquired_at` 就會晚於該列實際寫入的時間〔推論〕。
- **風控第一批 2.18 節的兩個設計缺口**〔事實：`work/reviews/2026-10-16-新定位第一批字面逐字審-LM01至LM28-風控.md:190-192`〕：
  - 開盤前沒有對應狀態，不得套用 D1（LM-27）；
  - 官方休市表不可得時，平日不即時標「休市」。
- **字面條件**：LM-25「推算模式下，平日不即時標休市」、LM-27「開盤前不得套用」〔事實：同檔 `:315,317`〕。

## Options（選項比較）

| 方案 | 優點 | 缺點 | 風險 |
|---|---|---|---|
| **A 後端純函式：bar 日期＋交易所時鐘＋可替換日曆（採用）** | 可以用字面時間戳做表格驅動測試；前端零推算 | 狀態比 PRD 多；參數未查證前不能出貨 | 字面工作量增加 |
| B 只靠時鐘 | 簡單 | 抓不到資料時仍會標「收盤」 | 過度宣稱 |
| C 前端推算 | 不必改後端 | 違反 ADR-0014 D-7(d) | 時區與假日錯誤 |
| D 重用 `intraday_session` | 少一份定義 | 依賴報價模組；13:25 的語意不對 | 碰到 AV-1 的精神 |

**推算模式下「今天是否開市」的呈現**（字面層的選擇，後端兩案一樣）

| 方案 | 優點 | 缺點 | 風險 |
|---|---|---|---|
| O1 沿用 LM-24、LM-27，同區塊加 LM-26 | 不必新字面 | 平日若其實休市，「交易時段內」「今日收盤資料尚未取得」是錯的 | 事實不精確 |
| **O2 新狀態字面「今日是否開市未能確認，顯示 {P} 收盤價」（意思；逐字由 creative-lead 起草）（建議）**<br>（r1，A-20）台股用 O2-b（LM-71）、美股用 O2-c（LM-72）；O1 不核可（風控第三批） | 不宣稱開市，也不宣稱休市 | 多一句字面；美股永遠走這條 | 低 |

**觀察交易日集合的輸入來源**（r3）

| 方案 | 優點 | 缺點 | 風險 |
|---|---|---|---|
| **A′ 快取列，加上讀取側的定案、品質、占位判準與支持度（採用）** | 零 schema；不牴觸 C-7；台股美股都適用；和 R3 共用定案判準 | 讀取成本比 DISTINCT 大；書很小時停在 weekday_assumed | 依賴 VS-4 正確（F-3） |
| B 寫入側 `final` 旗標欄 | 查詢簡單 | 主 DB 遷移要先有 ADR-0026；支持度仍要在讀取時算；有兩個真相來源 | 漂移；VS-4 改鍵就要再回填 |
| C 市場 DB ok bars run，加 `recorded_at ≥ VS-4` | 全市場覆蓋率 ≥ 0.98，經 FinMind 自證 | 牴觸 ADR-0012 C-7；只有台股；最早 17:30 | 啟動時太早的 run 被凍結，該日變成永久未確認 |
| D A′ ∪ C | 證據最多 | 同 C，而且最複雜 | 同 C |
| E 維持 DISTINCT，不翻轉 | 零成本 | R4b 到得了；占位列繼續汙染 P | observed 只是名義上的區分 |

## Decision（決策）

### D-1 模組
- `close_state.py`：純函式，不做 IO，不讀時鐘。
- `market_hours.py`：純常數，不讀環境變數。每個參數都附 `verified_on: date | None` 與出處。
- `session_calendar.py`：
  - protocol 的方法：`is_session(day)`、`previous_session(day) -> date | None`、`next_session(day) -> date`、`basis_for(day) -> Literal["official", "observed", "weekday_assumed"]`。
  - `ObservedSessionCalendar` 依 D-9 由確認證據建構。日曆範圍內的休市判定，交給只餵確認日的 `TradingCalendar`；未確認日另外處理（D-9 第 5 點）。`TradingCalendar` 本身的語意不變（CS-8）。
  - `OfficialSessionCalendar`（T1-13）：查得到就用官方答案，查不到就退回觀察日曆並揭露。

### D-2 輸入
與 T1 評估 B-2 相同〔轉引 `:228-238`〕：
- `now` 與估值器來自同一次時鐘讀值；
- `price_date` 取 `PriceInfo.as_of`；
- `acquired_at` 透過不序列化的內部欄位傳遞。
- `bar_as_of`（當日 bar 的 `PriceBar.as_of`）比照 `acquired_at`，以不序列化的內部欄位傳遞；只用於 R3，不得顯示（ADR-0019 K-13）。

### D-3 參數（數值待 T1-07 填入）

| 編號 | 參數 | TW | US | 用途 |
|---|---|---|---|---|
| VS-1 | 時區 | 引用 `freshness.policy_for(m).timezone` | 同左 | 本地時間 |
| VS-2 | `session_open` | 待查證（現有程式寫 09:00） | 待查證 | 開盤前與交易時段的分界 |
| VS-3 | `session_close` | 待查證（現有註解寫 13:30） | 待查證 | 與 P-6 分開 |
| VS-4 | `close_final_after` | 引用 `TW_POLICY.publish_cutoff` | 引用 `US_POLICY.publish_cutoff` | 判斷收盤是否定案 |
| VS-5 | 官方日曆涵蓋年度 | 待 T1-07、T1-13 | 無來源 | 超出就退回觀察日曆 |
| **VS-6（新增）** | `pre_open_order_start`（盤前委託開始） | 08:30〔推論，未查證〕 | 不定義（v1 不用） | 只供 ADR-0027 的逾時線使用；語意是交易所事實，不是預測帳政策 |

**出貨閘門**：VS-1～VS-5 任一 `verified_on` 為 None，T1-17 不得合併；VS-6 為 None，ADR-0027 不得寫入前瞻紀錄。

### D-4 狀態機（由上往下，第一條成立就採用）

先定義：
- `local = now.astimezone(VS-1)`、`D = local.date()`（**不得**使用估值器的 `today`）、`t = local.time()`；
- `P = previous_session(D)`、`basis = basis_for(D)`；
- 若 `is_session(D)`，依 t 分成三段：`t < VS-2` 為 `pre_open`；`VS-2 ≤ t < VS-3` 為 `in_session`；`t ≥ VS-3` 為 `post_close`。

| 規則 | 條件 | 狀態 | `reference_date` |
|---|---|---|---|
| R0 | `price_date is None` | 不輸出狀態 | — |
| R1 | `price_kind != "daily_close"` | `not_applicable` | — |
| R2 | `price_date > D` | `date_anomaly`，記 WARNING | price_date |
| **R2′（新增）** | 交易日、開盤前，而且 `price_date == D` | `date_anomaly`（開盤前不可能有當日 bar） | price_date |
| **R2″（新增；r3 改，A-47）** | D 不是交易日（任何 basis），而且 `price_date == D` | `date_anomaly`（官方日曆與資料衝突） | price_date |
| **R2‴（r3 新增）** | P 不為 None，而且 `P < price_date < D` | `date_anomaly`，`sub_reason = unconfirmed_session`，記 WARNING（列的日期落在日曆不認為是交易日的日子，例如週末，或 official basis 下的官方休市日） | price_date |
| R3（r3′ 改，A-46′） | 交易日、`price_date == D`，而且 `is_final(market, D, acquired_at, bar_as_of)` | `close` | D |
| R3′ | 交易日、`price_date == D`，但不滿足 R3 | `provisional_today` | D |
| **R4a（改）** | 交易日、開盤前，而且 `price_date == P` | **`pre_open`**（新狀態，取代 B-5 的 `close`） | P |
| R4b | 交易日、交易時段內，而且 `price_date == P` | `prior_close_reference`／`in_session` | P |
| R4c | 交易日、收盤後，而且 `price_date == P` | `prior_close_reference`／`after_close_pending` | P |
| R5 | D 不是交易日，而且 `price_date == P` | `market_closed` | P |
| R6 | `price_date < P`，或 P 為 None | `lagging`，附 `lag_sessions`（算不出來就給 null） | price_date |

（r3，A-47）R2″ 的狀態仍是 `date_anomaly`，`sub_reason` 依 basis 分成 `official_conflict` 與 `not_a_session`。

`date_anomaly` 的 `sub_reason`（`future_date`／`before_open`／`official_conflict`／`not_a_session`／`unconfirmed_session`）只用於 log 和 CS-11 的窮舉；字面一律是 LM-70。

R0～R6 對 `price_date` 相對於 (P, D) 的位置必須窮舉，由 CST-2 的性質測試釘住。

- **逐列輸出** `valuation_state = {state, sub_reason, reference_date, session_date: D, session_basis: basis, state_valid_until}`。
  - `state_valid_until` 是下一個 VS 切點，或本地午夜，由後端算好；只供前端的資料取得層決定何時重新取得（風控條件：狀態依台北時間在渲染時計算，不得沿用舊狀態）。
- **book 層級**：`calendar_basis` 只要有一列不是 official，就標 observed。前端據此常駐 LM-26（AC-B5a-5）。
- **推算模式下的平日**：`basis_for(D) == weekday_assumed` 時，`is_session(D)` 依週一至週五規則為真，所以平日永遠不會走到 R5。這就是風控的底線，以 CS-9 釘住。
- **AC-B5a-6**：依 `change_mode == "close_only"` 決定是否顯示（沿用 B-5）。
- **補充**（r1，A-19）：`date_anomaly` 與 `provisional_today` 不改變估值，也不改變總額（CS-2、CS-4）。
  - `build_summary` 另外輸出 book 層的 `valuation_state_counts: dict[state, int]`，供總額區塊做同區塊揭露（PT-b 的條件；`date_anomaly` 的總額揭露字面由 PM 與 creative-lead 另案處理）。

### D-5 字面對應（前端對應表；字面一律由 creative-lead 起草、風控核可）

（r1，A-16：整表取代）

| 狀態／條件 | 市場 | 字面 |
|---|---|---|
| `close` | TW、US | LM-23 |
| `pre_open` | TW、US | LM-23（日期代 P）＋LM-28；**不得用 LM-27** |
| R4b `in_session`，basis＝official | TW | LM-27 |
| R4c `after_close_pending`，basis＝official | TW | LM-24 |
| R4b／R4c，basis＝weekday_assumed | TW | LM-71（O2-b），與 LM-26 同區塊 |
| R4b `in_session`，basis＝observed（r2，A-38） | TW | LM-71＋LM-26 同區塊；不得用 LM-27；`build_summary` 記 WARNING |
| R4c `after_close_pending`，basis＝observed（r2，A-38） | TW | 確認之前：LM-71＋LM-26；確認之後：LM-24 |
| R4b／R4c，任何 basis | US | LM-72（O2-c），與 LM-26 同區塊 |
| `market_closed` | TW、US | LM-25；basis ≠ official 時，同區塊加 LM-26 |
| `lagging` | TW、US | LM-67；k 為 null 時用 LM-68 |
| `provisional_today` | TW、US | LM-69 |
| `date_anomaly` | TW、US | LM-70，價格照常顯示（見 D-4 補充，r1 A-19） |
| `not_applicable` | — | 不輸出估值狀態字面，現行顯示不變 |

（r2，A-38；r3 改，A-48）observed 兩列的說明：
- R4b × observed：D-9 實作之前（現行 `market_trading_days` 口徑）是到得了的。
  - D-9 實作之後，SE-2 要求 `min(as_of, fetched_at) ≥ final_after(D)`、`max(as_of, fetched_at) ≤ now`，而 R4b 要求 now < VS-3 < VS-4，所以只有時鐘或參數出錯時才可能出現。
  - 這一列的 LM-71＋LM-26 與 WARNING 保留，當作縱深防禦；WARNING 代表異常。
  - 不得以「照建構走不到」為由，刪除或降級這一列的對應、WARNING 或 CS-11 的窮舉（含 CST-7 的性質測試）。
- 翻轉 R4c × observed 為 LM-24 的 PR，要以下三點都成立才可以合併：
  - (a) D-9 已經實作合併，CST-5～CST-8 綠燈；
  - (b) data-engineer 的確認回報經風控單項確認。回報至少要含：
    - Phase 1 探測 §6.3 至少三輪的結果，證明所用來源在 VS-4 之後回傳的當日 bar 都是定案值（F-2、F-3 沒有觸發）；
    - §6.4 唯讀複本診斷 A～D 的數字；
    - SE-4、SE-5 的確認；
    - (i) §6.4 的試算必須用已合併版本的 `PriceBarCache.market_session_evidence` 讀唯讀複本，再交給已合併版本的 `classify_session_evidence` 分類。不得另寫 SQL，也不得重寫判準。回報要附所用 commit SHA 與呼叫方式。
    - (ii) 列出樣本期（§6.4 唯讀複本涵蓋的全部日期）內被判成 confirmed、但其實是週末（依 VS-1 的當地日期）或 TWSE 官方休市日的台股日子。休市表要註明官方出處與查證日期。**台股這個數字必須為 0，否則不得翻轉。** 美股同時列出被判成 confirmed 的週末，應為 0；不為 0 時列入回報，但不屬於 R4c 翻轉條件。
    - (iii) §6.3 判讀矩陣 F-7 那一欄的結果：逐來源、逐輪列出「VS-4 之後的當日 bar 是否已定案」。任何一格為否，F-7 即觸發，不得翻轉。
  - (c) qa 審查。只經 qa 審查不夠。
- 觀察日集合的輸入來源依 D-9（r3）。

對應表必須窮舉。任何狀態組合沒有核可字面，T1-17 就不得合併。

### D-6 已知限制（照實揭露）
1. 推算模式下，平日的休市無法即時判定。O2 會照實說明「未能確認」。
2. 官方年表不含颱風假之類的臨時休市：當天會顯示交易日的狀態，隔天可能出現假的 `lagging`，方向保守。不得以「沒人有這天的 bar」反推休市（ADR-0009 已否決的方案 E）。
3. 官方日曆判定休市時，freshness 仍只看週一至週五，可能同時出現「休市」標籤與「可能未含最近交易日」徽章。不修訂 ADR-0009（Q-B6）。
4. 台股是否有週六補行交易日，未查證〔推論〕。推算模式會把週六判為休市；若真有補行，隔天觀察到 bar 後會自動修正。
5. 美股沒有官方休市日來源，永遠走推算模式（Q-B4）。
6. （r1，A-21）美股的 D 是美國當地日期，所以美股字面一律不得含「今日」（LM-72 沒有含）。
7. （r3）VS-4 之後、但還不到兩個序列在定案時間後重抓之前（通常是盤後資料刷新跑完之前），當日 basis 仍是 weekday_assumed，台股顯示 LM-71＋LM-26。方向保守。
8. （r3）只有暫定列、而且從沒在 VS-4 之後重抓的日期，依週一至週五推定。如果那天其實休市（例如來源在假日送出占位列），`lag_sessions` 可能多算一天。現行口徑也一樣，不是退步。
9. （r3）指數列不算證據。持有的台股只有一檔時，永遠達不到支持度 2，basis 一律是 weekday_assumed。
10. （r3′）`check_price_bars` 只在讀取側用於日曆證據，不擋寫入；寫入側的品質閘門另案處理。「通過品質檢查」的範圍見 D-9 第 2 點。
11. （r3′）R 內完全沒有任何列（包括示範列）的平日，會判為休市（observed）。P 會跳過那一天，`lag_sessions` 可能少算。現行 `market_trading_days` 口徑也一樣，不是退步。
12. （r3′）`as_of` 是轉接器在呼叫開始時讀的時鐘。跨月份的抓取，`as_of` 早於實際取得當月資料的時間，所以 15:00 前開始、15:00 後才回來的抓取一律不算證據。方向保守。日線轉接器目前讀的是行內 `datetime.now(UTC)`，不是注入的時鐘，所以測試 fixture 要明確指定 `as_of`，不得依賴轉接器自己蓋的章。

### D-7 與 ADR-0027 的日曆分工

| 問題 | 使用的日曆 |
|---|---|
| 估值狀態、`valid_until_session` 的預估、逾時線的 `next_session(T)` | `SessionCalendar`（官方優先，退回推算） |
| 結算日、缺日稽核 | 只用觀察日 |

### D-8 缺項原因列舉值
放在 ADR-0027 D-13，不放本 ADR。理由：
- 它是 `MissingItem` 的欄位；
- 本 ADR 的狀態只供顯示（CS-4），不得被 outlook、plan、forecast 讀取，兩者不應共用列舉；
- 估值列缺價時顯示「—」（R0），沒有缺項清單。

### D-9 觀察交易日集合的輸入（r3，附件 B'-3）
1. **唯一來源**：
   - `PriceBarCache` 新增唯讀方法 `market_session_evidence(market, start, end) -> tuple[SessionEvidenceRow, ...]`。它原樣回傳 `[start, end]` 內該市場每一列的 `(symbol, trade_date, open, high, low, close, volume, source, as_of, fetched_at)`，不做過濾也不做分類。
   - 分類由 `session_calendar.py` 的純函式 `classify_session_evidence(rows, *, market, now) -> SessionEvidence` 負責。`SessionEvidence = {confirmed: frozenset[date], unconfirmed: frozenset[date]}`。
2. **一列算證據的條件**（SE-1～SE-6 全部成立）：
   - **SE-1**：`source` 不在 `NON_EVIDENCE_SOURCES`（v1 = {`demo_synthetic`}）。
   - **SE-2**（r3′）：`is_final(market, trade_date, as_of, fetched_at)` 成立，也就是 `final_after(market, trade_date) ≤ min(as_of, fetched_at)`；另外要 `max(as_of, fetched_at) ≤ now`。
     - `final_after` ＝ `trade_date` 當地日期的 VS-4（引用 `policy_for(market).publish_cutoff`），時區用 VS-1。
   - **SE-3**：`check_price_bars([該列])` 沒有 `OHLC_INVALID`。直接重用 `app.data.quality`，不另寫一份。
   - **SE-4**：`volume > 0`，用來排除占位列。
   - **SE-5**（r3′）：symbol 不在 `INDEX_SERIES_SYMBOLS` 內，**而且**不以 `^` 開頭。
     - `INDEX_SERIES_SYMBOLS` 是指數登記集合的鍵（現為 `app/data/providers/yfinance.py:122-126` 的 `INDEX_SYMBOL_METADATA`），定義見 CS-25。
     - 兩個條件是聯集排除（fail-closed）。只改用登記集合、拿掉 `^` 判定，會讓不在登記內的 `^` 代號重新成為證據，那是放寬。
   - **SE-6**（r3′）：`as_of` 與 `fetched_at` 都能解析，而且都帶時區。任一不符，該列就不算證據。
   - **「通過品質檢查」的範圍**（r3′）：`check_price_bars` 的五類檢查（`app/data/quality.py:41-63`）對日曆證據的對應如下：
     - OHLC_INVALID 由 SE-3 涵蓋；
     - FUTURE_DATE 由 SE-2 涵蓋（`final_after(trade_date) ≤ now`）；
     - DUPLICATE_ROW 因為 PK `(symbol, market, trade_date)`〔事實：`cache.py:52`〕，結構上不會發生；
     - MISSING_TRADING_DAY（跨列）與 CURRENCY_MISMATCH 和「那天有沒有開市」無關，不適用。
     - 本 ADR 說的「通過品質檢查」只指以上範圍。
3. **支持度**：某天至少有 `SESSION_EVIDENCE_MIN_SERIES`（v1 = 2）個不同 symbol 各有一列證據，才算 **confirmed**。
4. **三態**：
   - **confirmed**：見第 3 點；
   - **unconfirmed**（r3′）：那天在 `[start, end]` 內至少有一列（任何 source，**包括示範資料**），但沒達到 confirmed；
   - **absent**：那天沒有任何列。
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
8. **和 R3 同一個判準**（r3′）：D-4 的 R3 條件改成「交易日、`price_date == D`，而且 `is_final(market, D, acquired_at, bar_as_of)`」。
   - `bar_as_of` 是 `price_date == D` 那根 bar 的 `PriceBar.as_of`。
   - `acquired_at` 或 `bar_as_of` 任一為 None，就不成立，落到 R3′。
   - R3 和 SE-2 呼叫同一個 `is_final`（CS-17）。
9. **名詞**：本 ADR 的 basis＝observed 指上表的 confirmed，或 R 內的 absent。它和 ADR-0027 D-8 的「觀察日」（市場 DB ok bars ∪ 大盤 bar）是不同資料鏈的不同定義，互不替代。這是 C-7 造成的，屬於刻意的設計。

## Consequences（後果）
- **好處**：
  - 標籤由證據驅動；開盤前與推算模式都有明確的狀態；
  - 前端零推算；日曆可替換；
  - ADR-0027 共用同一套日曆與時間參數。
- **代價**：
  - 狀態從 4 個變成 8 個，再加 `session_basis`，字面工作量增加；
  - 參數未查證之前不能出貨；
  - 美股永遠顯示「未能確認」類的字面（若採 O2）；
  - 限制 2、3 會讓新鮮度低報，方向保守。

## 對實作的約束（逐條可檢查）
- **CS-1**：`close_state.py`、`market_hours.py`、`session_calendar.py` 不可達 `app.data.quote_params`、`app.data.intraday_session`、`app.data.quote_quality`、`app.services.quotes`、`app.data.providers.twse_mis`（import graph）。
- **CS-2**：`valuation.py` 不出現 VS 常數，也不呼叫狀態判定；唯一呼叫點是 `build_summary`。
- **CS-3**：一次 build 只讀一次時鐘；D 由 `now.astimezone(VS-1)` 取得（注入固定時鐘的測試，含台北 07:00 等於 UTC 前一天 23:00 的案例）。
- **CS-4**：advice、alerts、kelly、playbook、signals、limits、outlook、plan、forecast 都不讀 `valuation_state`（grep）。
- **CS-5**：前端狀態元件不出現 `new Date(`、`Date.now`、時段常數，也不 import `tradingCalendar.ts`。重新取得只能放在資料取得層，依 `state_valid_until` 排程。
- **CS-6**：不得移除既有的 `data_status`／`is_within_ttl` 徽章。
- **CS-7**：`market_hours` 的每個 VS 都有 `verified_on` 與出處欄位（測試）。VS-4 必須引用 `publish_cutoff`，不得複製數值（grep）。
- **CS-8**：`TradingCalendar` 的既有語意不變（playbook 的測試維持綠燈）。
- **CS-9**：`basis_for(D) == weekday_assumed` 而且 D 是平日時，不得輸出 `market_closed`（性質測試）。
- **CS-10**：`pre_open` 永遠不對應到 LM-27（前端對應表測試）。
- **CS-11**（r1 改，A-17）：字面對應表窮舉所有 (state, sub_reason, session_basis, market) 組合（`every state has a template`）。
  - （r2，A-39）R4b × observed 必須有對應（LM-71＋LM-26）。另加測試：這個組合出現時，`build_summary` 記 WARNING。`close_state.py` 維持純函式，不做 log。
- **CS-12**（r1 改，A-17；r2 改，A-39）：
  - LM-27 只在 `market=TW` 而且 `basis=official` 時渲染；
  - LM-24 只在 `market=TW`，而且 `basis=official`，或 `basis=observed`、`sub_reason=after_close_pending` 時渲染；
    - LM-24 在 `basis=observed`、`sub_reason=after_close_pending` 時渲染，要等翻轉 PR 合併後才生效。合併前，data-engineer 的確認回報要經過風控單項確認，並由 qa 審查。
    - 這一列的翻轉只能以 PR 修改對應表與測試落地，不設執行期旗標，也不得用設定值切換。
  - 正反兩個方向都要有測試。
  - 日後美股若接上官方日曆，LM-24、LM-27 要先依時區重審，才能擴用到美股。
- **CS-13**：字面、掃描器、測試在同一個 commit（PV-1）。
- **CS-14**：ADR-0027 使用的逾時線只引用 VS-6（或 M-1 駁回時引用 VS-2），不得另寫一份時間常數（grep）。
- **CS-15**（r1 新，A-18）：`market=US` 時永遠不渲染 LM-71；`market=TW` 時永遠不渲染 LM-72（前端對應表測試）。
  - （r2，A-39）(b) `basis=official` 時永遠不渲染 LM-71。這是風控的 suggested，成本很低，我採用。
- **CS-16**（r1 新，A-19）：`valuation_state_counts` 只給前端的總額與估值元件讀；CS-4 的 grep 範圍擴到這個欄位。
- **CS-17**（r3′）：`final_after(market, trade_date)` 與 `is_final(market, trade_date, *stamps)` 各只有一個定義，都放在 `session_calendar.py`，引用 VS-1、VS-4。
  - `is_final` 的語意：stamps 至少一個，全部不為 None 而且帶時區，並且 `final_after ≤ min(stamps)`。不符合就回 False。
  - SE-2 呼叫 `is_final(m, d, as_of, fetched_at)`，R3 呼叫 `is_final(m, D, acquired_at, bar_as_of)`。
  - 其他模組不得出現 `publish_cutoff` 與 `trade_date`、`acquired_at`、`as_of`、`fetched_at` 的行內比較。`final_after(` 只能在 `is_final` 內被呼叫（grep）。
- **CS-18**（r3）：`market_trading_days`、`market_has_session` 的 SQL 與 docstring 語意不變（`tests/test_market_calendar_staleness.py` 等既有測試不修改，而且要綠燈）。`session_calendar.py` 不得呼叫 `market_trading_days`（grep）。
- **CS-19**（r3）：`ObservedSessionCalendar` 的唯一資料來源是 `market_session_evidence`，經 `classify_session_evidence` 分類。`session_calendar.py`、`close_state.py` 和 `app.portfolio.*` 不可達 `app.data.market_panel`（沿用 ADR-0012 T-3 的測試）。`session_calendar.py` 不讀兩張 log 表（grep）。
- **CS-20**（r3）：`price_bars_cache` 的寫入者只有 `app/data/service.py` 和 `app/demo/seed.py`（AST／grep 列舉 `.put(` 的呼叫點）。新增寫入者要先修訂本 ADR，因為 SE-2 的前提是 `fetched_at` 就是寫入當下的時鐘。
- **CS-21**（r3′）：`NON_EVIDENCE_SOURCES`、`SESSION_EVIDENCE_MIN_SERIES`、SE-5 的判定式各只定義一次。測試斷言 `NON_EVIDENCE_SOURCES ⊇ {app.demo.series.DEMO_SOURCE}`。
  - **通則**：任何會讓更多列成為證據，或讓更多日子成為 confirmed 或 basis＝observed 的改動，合併前都要先經風控單項確認。下列只是舉例，不是窮舉：
    1. 降低 `SESSION_EVIDENCE_MIN_SERIES`；
    2. 從 `NON_EVIDENCE_SOURCES` 移除來源；
    3. 納入指數，或縮小 SE-5 的排除範圍（包括從 `INDEX_SERIES_SYMBOLS` 移除代號、拿掉 `^` 判定）；
    4. 放寬或移除 SE-2、SE-3、SE-4、SE-6；
    5. 讓 `final_after` 提早（包括改 VS-4，或改成 (market, source) 鍵後某來源提早）；
    6. 改動三態表，讓 unconfirmed 或 R 外的日子變成 observed；
    7. 新增 CS-20 寫入者；
    8. 把 `is_final` 從「取較早者」改成取較晚者或單一時鐘（包括 SE-2 只看 `fetched_at`、R3 只看 `acquired_at`）；
    9. 改動 unconfirmed 與 absent 的界線，讓更多日子落到 R 內 absent（例如讓只有示範列的日子回到 absent）；
    10. 讓 R 擴大（R 的定義不再是 confirmed 的區間）；
    11. 替換或增加 `ObservedSessionCalendar` 的輸入來源（D-9 第 7 點列為不採用的輸入）。
  - 往收緊方向改不必送風控。方向判斷不了的，一律視為放寬。
  - 這幾個常數與 `is_final` 的註解都要寫明這條通則。
- **CS-22**（r3）：每次 build，每個市場最多一次 evidence 讀取，`now` 和 CS-3 是同一次時鐘讀值（測試計數）。
- **CS-23**（r3）：本 ADR 不改 `price_bars_cache` 的 DDL，也不寫 `schema_migrations`。測試以 `sqlite_master` 斷言 DDL 和改動前相同。
- **CS-24**（r3）：每個市場都必須 VS-2 < VS-3 < VS-4（`market_hours` 的測試）。這是「R4b × observed 照建構走不到」的前提。
- **CS-25**（r3′）：SE-5 的指數登記集合只有一個定義。
  - D-9 的實作 PR 要把 `INDEX_SYMBOL_METADATA` 搬到不依賴 HTTP 的純常數模組（暫定 `app/data/index_registry.py`，名稱 dev-lead 可以改）。`app/data/providers/yfinance.py` 改成 import 它，不得留兩份。
  - `session_calendar.py` 不得 import `app.data.providers.*`（import graph）。
  - 測試要斷言兩件事：`app.services.index.MARKET_BENCHMARK` 的每個 `series_symbol`，以及 `app.leverage.index_mapping` 中所有非 None 的 `series_symbol`，都屬於 `INDEX_SERIES_SYMBOLS`；CS-1 的 import graph 測試維持綠燈。

## 測試要求
- **CST-1**：表格驅動測試，涵蓋：
  - VS-2、VS-3、VS-4 各自的前 1 秒與當下；
  - 00:00、08:59:59 為 `pre_open`，09:00 為 `in_session`（以待查證的值代入）；
  - 週六；官方休市日；推算模式的平日休市（O2）；
  - R2、R2′、R2″、R3′、R6；`intraday_quote`；
  - US 夏令時間切換日前後各一個案例；台北與 UTC 跨日的案例。
- **CST-2**：R0～R6 每條至少一例。
  - （r3）再加一個性質測試：對任意 (P, D, price_date)，R0～R6 恰好一條成立（含 R2″ 改寫和 R2‴）。
- **CST-3**：CS-9 的性質測試：推算模式下任意平日都不會是 `market_closed`。
- **CST-4**：官方日曆失敗時退回推算，book 的 `calendar_basis` 為 observed。
- **CST-5**（r3、r3′）：分類器的表格測試。
  - SE-1～SE-6 每一條各一個「只違反這一條」的 fixture；
  - TW 邊界：14:59:58+08:00 不算證據，15:00:00+08:00 算；
  - US 邊界：18:00 America/New_York，夏令與冬令各一例；
  - 支持度 1 對 2；
  - `fetched_at > now`；
  - 同一列 10:30 先寫入、16:00 被 upsert 覆寫後變成證據；
  - 指數列的 volume 為 0。
  - **R-1**：`as_of` 14:59:58+08:00、`fetched_at` 15:00:01+08:00，這一列不算證據。反向的 `as_of` 15:00:01、`fetched_at` 14:59:58 也不算。
  - TW、US 的邊界 fixture，`as_of` 與 `fetched_at` 都設成同一個邊界值。
  - `as_of > now`，不算證據。
  - `as_of` 沒有時區，不算證據（SE-6）。
  - `trade_date` 晚於 now 的當地日期，不算證據（S-3：FUTURE_DATE 由 SE-2 涵蓋）。
  - 「10:30 寫入、16:00 被 upsert 覆寫」這一例，覆寫後 `as_of`、`fetched_at` 兩欄都要 ≥ 15:00 才算證據。
  - **S-5**：`INDEX_SERIES_SYMBOLS` 內的代號不算證據；不在登記集合內、但以 `^` 開頭的代號也不算證據。
- **CST-6**（r3、r3′）：三態日曆的測試。confirmed、unconfirmed、R 內 absent、R 外，四種日子分別對 `is_session`、`basis_for`、`previous_session` 驗證。
  - 只有示範列的平日：unconfirmed，`is_session` 為 True，basis 是 weekday_assumed；
  - 只有示範列的週六：unconfirmed，`is_session` 為 False，basis 是 weekday_assumed；
  - R 內完全沒有列的平日：absent，False，observed（D-6 第 11 點）。
- **CST-7**（r3、r3′）：可達性測試。
  - R4c × observed：台股 15:00:00 時，有兩個序列的證據列，而且 `as_of`、`fetched_at` 都 ≥ 15:00:00+08:00，就成立。
  - R4b × observed：在 `max(as_of, fetched_at) ≤ now`，而且 CS-24 成立的前提下，任何輸入都不會出現（性質測試）。
- **CST-8**（r3）：回歸測試。既有的 playbook、price_change、market calendar staleness 測試不修改，而且要綠燈（CS-8、CS-18）。
- **CST-9**（r3′，R3 同口徑）：
  - `acquired_at` 15:00:01+08:00、`bar_as_of` 14:59:58+08:00：R3′（`provisional_today`）；
  - `acquired_at` 16:00+08:00、`bar_as_of` 14:00+08:00（快取路徑，當日列沒有被後來的抓取覆寫）：R3′；
  - 兩者都是 15:00:00+08:00：R3（`close`）；
  - `acquired_at` 或 `bar_as_of` 為 None：R3′；
  - grep：`close_state.py` 不出現 `publish_cutoff`。
- **qa-e2e**：375 與 1280 寬度實機驗收 AC-B5a-1～6，加上 `pre_open` 與推算模式。

## 失效條件
- **F-1**：盤中價接線。LM-27、LM-28 失效，依 ADR-0014 重審。
- **F-2**：T1-07 發現有來源會回傳當日暫定 bar。修訂 ADR-0009，R3′ 只是縱深防禦。
- **F-3**：各來源的定案時間不同。VS-4 升級成 (market, source) 鍵。
- **F-4**：交易所時段變更（例如延長交易、補行交易日）。
- **F-5**：官方休市日來源持續不可得（ADR-0025 F-6）。
- **F-6**：納入新的市場。
- **F-7**（r3）：§6.3 發現某個所用來源在 VS-4 之後仍回傳未定案的 bar。走 F-3，把 VS-4 升級成 (market, source) 鍵；已翻轉的 R4c 退回 LM-71＋LM-26，直到重新確認。
- **F-8**（r3）：ADR-0012 C-7 被修訂、允許持倉鏈讀市場 DB 時，重新評估方案 C／D。
- **F-9**（r3）：寫入側接上品質閘門時，重新檢查 SE-3、SE-4 是否變成重複，但不得因此刪除。

## 待決事項
- **PM**：
  - Q-B1：`pre_open` 是否沿用 LM-23；
  - Q-B2：新狀態；
  - Q-B3：推算模式的讀法；
  - Q-B4：Phase 1 是否涵蓋 US；
  - Q-B5：AC-B5a-6 與 CEO 2026-10-03 裁定 5 的關係。
- **風控**：
  - 已裁示（r1，A-20）：O1 或 O2（台股用 O2-b（LM-71）、美股用 O2-c（LM-72）；O1 不核可，風控第三批）；`pre_open` 沿用 LM-23（字面見 D-5：LM-23 日期代 P ＋LM-28，不得用 LM-27）。
  - 已裁示（r2，A-40）：`basis=observed` 的對應（風控 v0.6 核對 A-16：R4c 有條件用 LM-24；R4b 維持 LM-71＋LM-26）。
  - 新增（r2，A-40）：data-engineer 觀察日確認回報的單項確認。
  - 新增（r3，A-52）：r3 設計的單項確認（見第五節第 1 點）；R2″ 改寫、R2‴ 對應 LM-70 是否屬實。
  - 新狀態的字面。
- **data-engineer**：
  - Q-B7：各日線來源在盤中或收盤剛結束時，會不會回傳當日、尚未定案的 bar；
  - VS-2～VS-6 的查證；
  - 週六補行交易日。
  - 新增（r2，A-40）：觀察日集合來源的確認。
  - 新增（r3，A-52）：SE-4、SE-5 的確認；R4c 翻轉前的確認回報內容（依 A-48）。
  - 新增（r3′，A-52′）：
    - (f) 確認所有寫入 `price_bars_cache` 的轉接器，`PriceBar.as_of` 都不晚於第一個請求送出的時間；
    - (g) A-48 (b) (i)～(iii) 的回報內容。
- **CEO**：接受新狀態；#15 連網環境。
  - 新增（r3，A-52）：知悉方案 C 被否決，因此 ADR-0027 和 ADR-0028 對「觀察日」各用不同定義。
- **tech-architect**：Q-B6（ADR-0009 是否吃官方假日表），在 T1-13 時另案處理。

## 未查證事項
- 所有 VS 的數值；08:30 盤前委託；週六補行交易日；US 的交易時段。
- B-2 所引的 `valuation.py` 與 ADR-0019 行號，除了 343、382、223 以外，都轉引自 T1 評估。
- （r3、r3′，A-52、A-52′）新增：
  - 快取中是否有指數序列既不在 `INDEX_SERIES_SYMBOLS`、也不以 `^` 開頭〔未查證，待 data-engineer〕；
  - 各來源在真實交易日時 volume 的語意〔未查證〕；
  - 所有日線轉接器都在送出請求前蓋 `as_of`〔已查 `twse.py:88`，其餘轉接器只 grep 了 `now = datetime.now(UTC)` 的位置，推論〕；
  - 快取路徑下 `acquired_at` 晚於當日列寫入時間的情境〔推論，CST-9 釘住〕。

---

## 修訂紀錄

> r1（2026-10-16）依 tech-architect 修訂提案 A-1～A-21 套用；本 ADR 適用 A-16～A-21，A-1～A-15 見 ADR-0027。
> 提案來源：`work/reviews/2026-10-16-ADR-0027與0028修訂提案A1至A21-tech-architect.md` 附件 A。
> 被改寫或取代的原文逐字保留於下；「新增」類條目沒有被取代的原文。引用區塊內的文字即 r1 之前的原文。

**A-16（D-5 字面對應表，整表取代）**
- r1（2026-10-16，tech-architect A-16）：原整表——
  > | 狀態／條件 | 字面 |
  > |---|---|
  > | `close` | LM-23 |
  > | `pre_open` | 建議沿用 LM-23「{MM/DD} 收盤價」，以 P 代入，待 PM Q-B1 與風控單項確認；否則另起草新字面。**不得用 LM-27** |
  > | `prior_close_reference`／`in_session`，`basis = official` | LM-27 |
  > | `prior_close_reference`／`after_close_pending`，`basis = official` | LM-24 |
  > | R4b、R4c，`basis = weekday_assumed` | O1 或 O2（風控裁示；建議 O2） |
  > | `market_closed` | LM-25；推算模式下同區塊加 LM-26 |
  > | `lagging`、`provisional_today`、`date_anomaly` | 新字面（Q-B2）；`lagging` 不得用「前一收盤」 |

  改為見 §D-5。原表之後的「對應表必須窮舉。任何狀態組合沒有核可字面，T1-17 就不得合併。」保留不變。

**A-17（CS-11、CS-12）**
- r1（2026-10-16，tech-architect A-17）：CS-11 原文——
  > - **CS-11**：字面對應表窮舉所有（state, sub_reason, session_basis）組合（`every state has a template`）。

  改為見 §對實作的約束 CS-11。
- r1（2026-10-16，tech-architect A-17）：CS-12 原文——
  > - **CS-12**：`basis = weekday_assumed` 的 R4b、R4c，不渲染 LM-27、LM-24，除非風控書面核可 O1。

  改為見 §對實作的約束 CS-12（提案註明：O1 已不核可，「除非風控書面核可 O1」刪除）。

**A-18（CS-15）**
- r1（2026-10-16，tech-architect A-18）：CS-15 為新增，無被取代原文；見 §對實作的約束。

**A-19（D-4 補充、CS-16）**
- r1（2026-10-16，tech-architect A-19）：D-4 補充與 CS-16 為新增，無被取代原文；見 §D-4 末段、§對實作的約束。

**A-20（Options 第二表、待決事項）**
- r1（2026-10-16，tech-architect A-20）：O2 列加註「台股用 O2-b（LM-71）、美股用 O2-c（LM-72）；O1 不核可（風控第三批）」，無被取代原文；見 §Options 推算模式呈現表。
- r1（2026-10-16，tech-architect A-20）：待決事項風控項原文——
  > - **風控**：O1 或 O2；`pre_open` 沿用 LM-23 的單項確認；新狀態的字面。

  改為見 §待決事項 風控（「O1 或 O2」與「`pre_open` 沿用 LM-23」改為已裁示；新增「`basis=observed` 的對應」待風控確認；「新狀態的字面」維持）。

**A-21（D-6 第 6 點）**
- r1（2026-10-16，tech-architect A-21）：新增第 6 點，無被取代原文；見 §D-6。

---

> r2（2026-10-17）依 tech-architect 修訂提案 A-22～A-41 套用；本 ADR 適用 A-38～A-41，A-22～A-37 見 ADR-0027。檔頭狀態維持 proposed。
> 套用順序與提案來源（後者取代前者的對應條目）：
> 1. r2：`work/reviews/2026-10-17-ADR-0027與0028修訂提案A22至A41-tech-architect.md` 附件 A（A-38～A-41）。
> 2. r2'：`work/reviews/2026-10-17-ADR-0027與0028修訂提案r2prime-tech-architect.md` 附件 A。A-38 整條取代 r2 版；A-39 只改 CS-12 的 observed 一段，CS-11、CS-15 (b) 同 r2；A-40 加一點，其餘同 r2；A-41 未列，照 r2 原文。
> 3. r2''（`work/reviews/2026-10-17-ADR-0027修訂提案r2雙撇A36增補-tech-architect.md`）不動 ADR-0028 的任何條目。
> 風控確認依據：`work/reviews/2026-10-17-ADR-r2附件B單項確認-風控.md`、`work/reviews/2026-10-17-A-15-事先宣告v0.9核對與A36及B0單項確認-風控.md`。
> 被改寫或取代的原文逐字保留於下；「新增」類條目沒有被取代的原文。引用區塊內的文字即 r2 之前的原文。
> 原文與新文中的「附件 B'-x」，指提案檔內的編號，不是本 ADR 的章節。
> 本次套用不含 ADR-0028 r3（觀察日來源，另案）。

**A-38（D-5 字面對應表）**
- r2（2026-10-17，tech-architect A-38，r2' 整條取代 r2 版）：D-5 表中 observed 一列原文——
  > | R4b／R4c，basis＝observed | TW | 暫時比照 LM-71＋LM-26，待風控單項確認。我的建議：observed 是正面證據，可以比照 official 用 LM-27／LM-24 |

  改為見 §D-5（拆成 R4b、R4c 兩列，表後加說明）。

**A-39（CS-11、CS-12、CS-15）**
- r2（2026-10-17，tech-architect A-39）：CS-11 補一句、CS-15 加 (b)，無被取代原文；見 §對實作的約束。
- r2（2026-10-17，tech-architect A-39，r2' 只改 observed 一段）：CS-12 原文——
  > - **CS-12**（r1 改，A-17）：LM-24、LM-27 只在 `market=TW` 而且 `basis=official` 時渲染。日後美股若接上官方日曆，LM-24、LM-27 要先依時區重審，才能擴用到美股。

  改為見 §對實作的約束 CS-12（美股一句保留）。

**A-40（待決事項）**
- r2（2026-10-17，tech-architect A-40，r2' 加一點）：待決事項風控項原文——
  > - 新增（r1，A-20）：`basis=observed` 的對應（見 D-5），待風控確認。

  改為見 §待決事項 風控（已裁示）。另新增風控一項（觀察日確認回報的單項確認）與 data-engineer 一項（觀察日集合來源的確認），無被取代原文。

**A-41（檔頭）**
- r2（2026-10-17，tech-architect A-41）：檔頭新增「r2 修訂」一行，無被取代原文。

---

> r3（2026-10-17）依 tech-architect 修訂提案 A-42～A-53（附件 B'-3），含 r3′ 補正（風控 r3 單項確認 R-1～R-3、S-1～S-5）套用。檔頭狀態維持 proposed。
> 套用順序與提案來源（後者取代前者的對應條目）：
> 1. r3：`work/reviews/2026-10-17-ADR-0028修訂提案r3觀察日來源-tech-architect.md` 第三節（A-42～A-53）。
> 2. r3′：`work/reviews/2026-10-17-ADR-0028修訂提案r3prime補正-tech-architect.md` 第二節（A-42′～A-53′）。以 r3 提案文字為基準，取代或補充對應條目；r3′ 修改的是 r3 還沒落檔的提案文字，不是已落檔的條文，所以不另外保留 r3 提案原文。
> 3. ADR-0027 r3 提案中針對本 ADR 的 A-84（CS-12 補「不設執行期旗標」）：`work/reviews/2026-10-17-ADR-0027修訂提案r3-A54至A86含r2讀法確認-tech-architect.md`。
> 風控確認依據：`work/reviews/2026-10-17-ADR-0028-r3單項確認-風控.md`（APPROVE WITH CONDITIONS；R-1～R-3 由 r3′ 處理）。tech-architect 對 r2 套用讀法的確認：同上 ADR-0027 r3 提案第六節 6.3。
> 被改寫或取代的原文逐字保留於下（A-53′ 指定保留：A-45 的 D-1 子句、A-47 的 R2″ 條件、A-48 的 r2' A-38 三點、D-4 R3 原條件）；「新增」類條目沒有被取代的原文。引用區塊內的文字即 r3 之前的原文。
> 原文與新文中的「附件 B'-x」「第五節第 1 點」，指提案檔內的編號與章節，不是本 ADR 的章節。

**A-42／A-42′（文首）**
- r3（2026-10-17，tech-architect A-42，r3′ 改寫）：檔頭新增「r3 修訂」一行、「與既有 ADR 的關係」新增四點（ADR-0012、ADR-0016／0009／0024、ADR-0019、ADR-0026），無被取代原文；見檔頭。其中 ADR-0019 一點採 A-42′ 的整點取代文字。

**A-43／A-43′（Context）**
- r3（2026-10-17，tech-architect A-43，r3′ 加兩點）：Context 新增「觀察日曆現況」，無被取代原文；見 §Context。

**A-44（Options）**
- r3（2026-10-17，tech-architect A-44）：Options 新增第三張表「觀察交易日集合的輸入來源」，無被取代原文；見 §Options。

**A-45（D-1）**
- r3（2026-10-17，tech-architect A-45）：D-1 `session_calendar.py` 第二個子點原文——
  > - `ObservedSessionCalendar` 包裝現有的 `TradingCalendar`，不改它的語意。

  改為見 §D-1。

**A-46／A-46′（D-9、D-2、D-4 R3）**
- r3（2026-10-17，tech-architect A-46，r3′ 改寫第 1、4、8 點與 SE-2、SE-5、SE-6，並加「通過品質檢查」的範圍一段）：D-9 為新增，無被取代原文；見 §D-9。D-2 末尾新增 `bar_as_of` 一點，無被取代原文。
- r3′（2026-10-17，tech-architect A-46′ 第 8 點，A-53′ 指定保留）：D-4 R3 原條件——
  > | R3 | 交易日、`price_date == D`，而且 `acquired_at ≥ D 的 VS-4` | `close` | D |

  條件改為見 §D-4 R3 與 §D-9 第 8 點。

**A-47／A-47′（D-4）**
- r3（2026-10-17，tech-architect A-47）：D-4 R2″ 原文——
  > | **R2″（新增）** | `basis == official`、D 不是交易日，而且 `price_date == D` | `date_anomaly`（官方日曆與資料衝突） | price_date |

  條件改為見 §D-4 R2″。提案載明的理由：原表在非 official basis、D 是週末、而且 `price_date == D` 時，沒有規則成立。
- r3（2026-10-17，tech-architect A-47，r3′ 改寫 R2‴ 狀態欄括號）：R2‴ 為新增，無被取代原文；表後兩句同為新增；見 §D-4。

**A-48／A-48′（D-5 表後說明）**
- r3（2026-10-17，tech-architect A-48，r3′ 改寫第一點第二子點、第一點末加一句、(b) 加三項）：D-5 表後原文（即 r2' A-38 的表後三點）——
  > （r2，A-38）observed 兩列的說明：
  > - **R4b 這一列，以現行程式來說是到得了的**：`market_trading_days` 只做 `SELECT DISTINCT trade_date`，沒有排除未定案的 bar〔轉引 data-engineer 2026-10-17 回報 L12-23〕。WARNING 是出現非最終資料的訊號，不是「不可達」的斷言。
  > - **R4c 的切換**：翻轉這一列的 PR 合併之前，data-engineer 的確認回報（觀察日集合只來自通過品質檢查的最終日線，不含盤中、暫定或占位列）**要先送風控單項確認**；只經 qa 審查不夠。
  > - 觀察日集合的輸入來源還沒決定（附件 B'-3）。決定之前，R4c × observed 不會切換。

  改為見 §D-5。

**A-49／A-49′（D-6）**
- r3（2026-10-17，tech-architect A-49，r3′ 改寫第 10 點並新增第 11、12 點）：D-6 新增第 7～12 點，無被取代原文；見 §D-6。

**A-50／A-50′（對實作的約束）**
- r3（2026-10-17，tech-architect A-50，r3′ 改寫 CS-17、CS-21 並新增 CS-25）：CS-17～CS-25 為新增，無被取代原文；見 §對實作的約束。

**A-51／A-51′（測試要求）**
- r3（2026-10-17，tech-architect A-51，r3′ 補 CST-5、CST-6、CST-7 並新增 CST-9）：CST-2 補一句、CST-5～CST-9 為新增，無被取代原文；見 §測試要求。

**A-52／A-52′（失效條件、待決事項、未查證事項）**
- r3（2026-10-17，tech-architect A-52，r3′ 改寫未查證事項首項並補待決、未查證各項）：F-7～F-9、待決事項與未查證事項皆為新增，無被取代原文；見各節。

**A-53／A-53′（修訂紀錄）**
- r3（2026-10-17，tech-architect A-53）：本區塊為新增，無被取代原文。

**A-84（ADR-0027 r3 提案，CS-12）**
- r3（2026-10-17，tech-architect A-84，載於 ADR-0027 r3 提案）：CS-12 observed 子項之後新增一句（不設執行期旗標），無被取代原文；見 §對實作的約束 CS-12。提案載明：這是恢復 r2 A-38「切換方式」的原意，r2' 整條取代時漏帶。

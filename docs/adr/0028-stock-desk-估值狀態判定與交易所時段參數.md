# ADR-0028：stock-desk 估值狀態判定與交易所時段參數

- 狀態：proposed
- 日期：2026-10-16
- 決策者：tech-architect（草案）；待 CEO 核可。立案依據：T1-01／T1-02 評估附件 B-8；coordinator 分配編號〔事實：`work/reviews/2026-10-16-T1-01與T1-02-tech-architect評估.md:4,320-335`〕。
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
| **O2 新狀態字面「今日是否開市未能確認，顯示 {P} 收盤價」（意思；逐字由 creative-lead 起草）（建議）** | 不宣稱開市，也不宣稱休市 | 多一句字面；美股永遠走這條 | 低 |

## Decision（決策）

### D-1 模組
- `close_state.py`：純函式，不做 IO，不讀時鐘。
- `market_hours.py`：純常數，不讀環境變數。每個參數都附 `verified_on: date | None` 與出處。
- `session_calendar.py`：
  - protocol 的方法：`is_session(day)`、`previous_session(day) -> date | None`、`next_session(day) -> date`、`basis_for(day) -> Literal["official", "observed", "weekday_assumed"]`。
  - `ObservedSessionCalendar` 包裝現有的 `TradingCalendar`，不改它的語意。
  - `OfficialSessionCalendar`（T1-13）：查得到就用官方答案，查不到就退回觀察日曆並揭露。

### D-2 輸入
與 T1 評估 B-2 相同〔轉引 `:228-238`〕：
- `now` 與估值器來自同一次時鐘讀值；
- `price_date` 取 `PriceInfo.as_of`；
- `acquired_at` 透過不序列化的內部欄位傳遞。

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
| **R2″（新增）** | `basis == official`、D 不是交易日，而且 `price_date == D` | `date_anomaly`（官方日曆與資料衝突） | price_date |
| R3 | 交易日、`price_date == D`，而且 `acquired_at ≥ D 的 VS-4` | `close` | D |
| R3′ | 交易日、`price_date == D`，但不滿足 R3 | `provisional_today` | D |
| **R4a（改）** | 交易日、開盤前，而且 `price_date == P` | **`pre_open`**（新狀態，取代 B-5 的 `close`） | P |
| R4b | 交易日、交易時段內，而且 `price_date == P` | `prior_close_reference`／`in_session` | P |
| R4c | 交易日、收盤後，而且 `price_date == P` | `prior_close_reference`／`after_close_pending` | P |
| R5 | D 不是交易日，而且 `price_date == P` | `market_closed` | P |
| R6 | `price_date < P`，或 P 為 None | `lagging`，附 `lag_sessions`（算不出來就給 null） | price_date |

- **逐列輸出** `valuation_state = {state, sub_reason, reference_date, session_date: D, session_basis: basis, state_valid_until}`。
  - `state_valid_until` 是下一個 VS 切點，或本地午夜，由後端算好；只供前端的資料取得層決定何時重新取得（風控條件：狀態依台北時間在渲染時計算，不得沿用舊狀態）。
- **book 層級**：`calendar_basis` 只要有一列不是 official，就標 observed。前端據此常駐 LM-26（AC-B5a-5）。
- **推算模式下的平日**：`basis_for(D) == weekday_assumed` 時，`is_session(D)` 依週一至週五規則為真，所以平日永遠不會走到 R5。這就是風控的底線，以 CS-9 釘住。
- **AC-B5a-6**：依 `change_mode == "close_only"` 決定是否顯示（沿用 B-5）。

### D-5 字面對應（前端對應表；字面一律由 creative-lead 起草、風控核可）

| 狀態／條件 | 字面 |
|---|---|
| `close` | LM-23 |
| `pre_open` | 建議沿用 LM-23「{MM/DD} 收盤價」，以 P 代入，待 PM Q-B1 與風控單項確認；否則另起草新字面。**不得用 LM-27** |
| `prior_close_reference`／`in_session`，`basis = official` | LM-27 |
| `prior_close_reference`／`after_close_pending`，`basis = official` | LM-24 |
| R4b、R4c，`basis = weekday_assumed` | O1 或 O2（風控裁示；建議 O2） |
| `market_closed` | LM-25；推算模式下同區塊加 LM-26 |
| `lagging`、`provisional_today`、`date_anomaly` | 新字面（Q-B2）；`lagging` 不得用「前一收盤」 |

對應表必須窮舉。任何狀態組合沒有核可字面，T1-17 就不得合併。

### D-6 已知限制（照實揭露）
1. 推算模式下，平日的休市無法即時判定。O2 會照實說明「未能確認」。
2. 官方年表不含颱風假之類的臨時休市：當天會顯示交易日的狀態，隔天可能出現假的 `lagging`，方向保守。不得以「沒人有這天的 bar」反推休市（ADR-0009 已否決的方案 E）。
3. 官方日曆判定休市時，freshness 仍只看週一至週五，可能同時出現「休市」標籤與「可能未含最近交易日」徽章。不修訂 ADR-0009（Q-B6）。
4. 台股是否有週六補行交易日，未查證〔推論〕。推算模式會把週六判為休市；若真有補行，隔天觀察到 bar 後會自動修正。
5. 美股沒有官方休市日來源，永遠走推算模式（Q-B4）。

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
- **CS-11**：字面對應表窮舉所有（state, sub_reason, session_basis）組合（`every state has a template`）。
- **CS-12**：`basis = weekday_assumed` 的 R4b、R4c，不渲染 LM-27、LM-24，除非風控書面核可 O1。
- **CS-13**：字面、掃描器、測試在同一個 commit（PV-1）。
- **CS-14**：ADR-0027 使用的逾時線只引用 VS-6（或 M-1 駁回時引用 VS-2），不得另寫一份時間常數（grep）。

## 測試要求
- **CST-1**：表格驅動測試，涵蓋：
  - VS-2、VS-3、VS-4 各自的前 1 秒與當下；
  - 00:00、08:59:59 為 `pre_open`，09:00 為 `in_session`（以待查證的值代入）；
  - 週六；官方休市日；推算模式的平日休市（O2）；
  - R2、R2′、R2″、R3′、R6；`intraday_quote`；
  - US 夏令時間切換日前後各一個案例；台北與 UTC 跨日的案例。
- **CST-2**：R0～R6 每條至少一例。
- **CST-3**：CS-9 的性質測試：推算模式下任意平日都不會是 `market_closed`。
- **CST-4**：官方日曆失敗時退回推算，book 的 `calendar_basis` 為 observed。
- **qa-e2e**：375 與 1280 寬度實機驗收 AC-B5a-1～6，加上 `pre_open` 與推算模式。

## 失效條件
- **F-1**：盤中價接線。LM-27、LM-28 失效，依 ADR-0014 重審。
- **F-2**：T1-07 發現有來源會回傳當日暫定 bar。修訂 ADR-0009，R3′ 只是縱深防禦。
- **F-3**：各來源的定案時間不同。VS-4 升級成 (market, source) 鍵。
- **F-4**：交易所時段變更（例如延長交易、補行交易日）。
- **F-5**：官方休市日來源持續不可得（ADR-0025 F-6）。
- **F-6**：納入新的市場。

## 待決事項
- **PM**：
  - Q-B1：`pre_open` 是否沿用 LM-23；
  - Q-B2：新狀態；
  - Q-B3：推算模式的讀法；
  - Q-B4：Phase 1 是否涵蓋 US；
  - Q-B5：AC-B5a-6 與 CEO 2026-10-03 裁定 5 的關係。
- **風控**：O1 或 O2；`pre_open` 沿用 LM-23 的單項確認；新狀態的字面。
- **data-engineer**：
  - Q-B7：各日線來源在盤中或收盤剛結束時，會不會回傳當日、尚未定案的 bar；
  - VS-2～VS-6 的查證；
  - 週六補行交易日。
- **CEO**：接受新狀態；#15 連網環境。
- **tech-architect**：Q-B6（ADR-0009 是否吃官方假日表），在 T1-13 時另案處理。

## 未查證事項
- 所有 VS 的數值；08:30 盤前委託；週六補行交易日；US 的交易時段。
- B-2 所引的 `valuation.py` 與 ADR-0019 行號，除了 343、382、223 以外，都轉引自 T1 評估。

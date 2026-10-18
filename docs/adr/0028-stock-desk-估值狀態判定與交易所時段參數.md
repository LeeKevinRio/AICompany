# ADR-0028：stock-desk 估值狀態判定與交易所時段參數

- 狀態：proposed
- 日期：2026-10-16
- 決策者：tech-architect（草案）；待 CEO 核可。立案依據：T1-01／T1-02 評估附件 B-8；coordinator 分配編號〔事實：`work/reviews/2026-10-16-T1-01與T1-02-tech-architect評估.md:4,320-335`〕。
- r1 修訂：2026-10-16，依 tech-architect 修訂提案 A-1～A-21
- r2 修訂：2026-10-17，依 tech-architect 修訂提案 A-22～A-41
- r3 修訂：2026-10-17，依 tech-architect 修訂提案 A-42～A-53（附件 B'-3：觀察交易日集合的輸入來源），含 r3′ 補正（風控 r3 單項確認 R-1～R-3、S-1～S-5）
- r3″ 更正：2026-10-17，依 tech-architect r3″ 更正 A-87～A-95（r3 套用後的接合、參照與編修；A-87、A-91 為收緊，其餘方向不變）
- A-96″／A-97′ 修訂：2026-10-17，依 tech-architect ADR-0028 A-96″（D-6 第 13 點、CS-4 補充、CS-26、CS-27、CST-10～CST-12；風控 2026-10-17 A-96′ 單項確認 K-1～K-16）。A-96″ 為不變＋收緊，A-97′ 為收緊。`/api/leverage` 歸類、K-14 (i) 觸發條件、CST-10 結構性質前提，經風控 2026-10-17 A-96″ 回送確認（K-17～K-33）。
- CS-17 修訂：2026-10-18，依風控 2026-10-18 ADR-0027 C9-7、Q-3 與 CS-17 提案確認第二節第 3 項（`work/reviews/2026-10-18-ADR-0027-C9-7與Q-3及CS-17提案確認-風控.md`）。方向不變，條件是 AST 斷言；被取代的原文逐字保留於修訂紀錄末段。
- 適用範圍：僅 product/stock-desk。
- 與既有 ADR 的關係：
  - 不取代任何 ADR。
  - **ADR-0009**：引用 D-2 的 `publish_cutoff`，不修訂。
  - **ADR-0014**：遵守 D-7(d)、I-10、D-11。
  - **ADR-0016**：AC-B5a-6 依 D-8 的 `change_mode` 判斷。
  - **ADR-0025**：是 AV-1 的延伸，實作 D-9 休市日、F-6 與 D-12 Phase 1。
  - **ADR-0027（同批）**：本 ADR 提供 `SessionCalendar` 與 VS-6，由 ADR-0027 使用。
    - T1 評估 B-3 原本寫「AV-17 共用 VS-2」〔轉引 `:247`〕。ADR-0027 M-1 核可後改用 VS-6；M-1 駁回時仍用 VS-2。
  - **ADR-0012（accepted）**：遵守 C-7。`ObservedSessionCalendar` 不讀市場 DB（D-9 第 7 點）。
  - **ADR-0016、ADR-0009、ADR-0024**：`market_trading_days`、`market_has_session` 的語意與 SQL 不變（CS-18）。
  - **ADR-0019**（r3、r3′；r3″ 合併，A-88）：`acquired_at` 依 ADR-0019 D-4、D-5 的單一取得時間基準。本 ADR 的模組不讀 `tail_fetched_at` 欄（ADR-0019 K-3 的用途限制）；走快取路徑時，`acquired_at` 的值等於它，是經由 ADR-0019 D-5 的序列取得時間間接取得（見 Context「觀察日曆現況」）。D-9 讀列層的 `as_of` 與 `fetched_at`，R3 另外讀當日 bar 的 `PriceBar.as_of`。這些時間都只用來判斷「是否定案」，一律取較早者（CS-17）。它們不是序列的取得時間，不取代 `acquired_at`（ADR-0019 D-5），也不得顯示（K-13）。K-9 不受影響。
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
| R2（r3″ 補 sub_reason，A-90） | `price_date > D` | `date_anomaly`，`sub_reason = future_date`，記 WARNING | price_date |
| **R2′（新增；r3″ 補 sub_reason，A-90）** | 交易日、開盤前，而且 `price_date == D` | `date_anomaly`，`sub_reason = before_open`（開盤前不可能有當日 bar） | price_date |
| **R2″（新增；r3 改，A-47；r3″ 改狀態欄，A-89）** | D 不是交易日（任何 basis），而且 `price_date == D` | `date_anomaly`（D 依日曆不是交易日，卻有 D 日期的列；basis＝official 時即官方日曆與資料衝突。`sub_reason` 見表後） | price_date |
| **R2‴（r3 新增）** | P 不為 None，而且 `P < price_date < D` | `date_anomaly`，`sub_reason = unconfirmed_session`，記 WARNING（列的日期落在日曆不認為是交易日的日子，例如週末，或 official basis 下的官方休市日） | price_date |
| R3（r3′ 改，A-46′） | 交易日、`price_date == D`，而且 `is_final(market, D, acquired_at, bar_as_of)` | `close` | D |
| R3′ | 交易日、`price_date == D`，但不滿足 R3 | `provisional_today` | D |
| **R4a（改）** | 交易日、開盤前，而且 `price_date == P` | **`pre_open`**（新狀態，取代 B-5 的 `close`） | P |
| R4b | 交易日、交易時段內，而且 `price_date == P` | `prior_close_reference`／`in_session` | P |
| R4c | 交易日、收盤後，而且 `price_date == P` | `prior_close_reference`／`after_close_pending` | P |
| R5 | D 不是交易日，而且 `price_date == P` | `market_closed` | P |
| R6 | `price_date < P`，或 P 為 None | `lagging`，附 `lag_sessions`（算不出來就給 null） | price_date |

（r3，A-47；r3″ 補對應，A-90）R2″ 的狀態仍是 `date_anomaly`；basis＝official 時 `sub_reason = official_conflict`，其他 basis（observed、weekday_assumed）時為 `not_a_session`。

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

（r2，A-38；r3 改，A-48；r3″ 改，A-91、A-92）observed 兩列的說明：
- R4b × observed：D-9 實作之前（現行 `market_trading_days` 口徑）是到得了的。
  - D-9 實作之後，SE-2 要求 `min(as_of, fetched_at) ≥ final_after(D)`、`max(as_of, fetched_at) ≤ now`，而 R4b 要求 now < VS-3 < VS-4，所以只有時鐘或參數出錯時才可能出現。
  - 這一列的 LM-71＋LM-26 與 WARNING 保留，當作縱深防禦；WARNING 代表異常。
  - 不得以「照建構走不到」為由，刪除或降級這一列的對應、WARNING 或 CS-11 的窮舉（含 CST-7 的性質測試）。
- 翻轉 R4c × observed 為 LM-24 的 PR，要以下三點都成立才可以合併：
  - (a) D-9 已經實作合併，CST-5～CST-9 綠燈；
  - (b) data-engineer 的確認回報經風控單項確認。回報至少要含：
    - Phase 1 探測指令（`work/research/2026-10-16-Phase1資料源探測指令-CEO本機代跑.md`，下稱「探測指令」）§6.3 至少三輪的結果，證明所用來源在 VS-4 之後回傳的當日 bar 都是定案值（F-2、F-3 沒有觸發）；
    - 探測指令 §6.4.3 唯讀複本診斷 A～D 的數字；
    - SE-4、SE-5 的確認；
    - (i) 探測指令 §6.4.4 的新口徑試算必須用已合併版本的 `PriceBarCache.market_session_evidence` 讀唯讀複本，再交給已合併版本的 `classify_session_evidence` 分類。不得另寫 SQL，也不得重寫判準。回報要附所用 commit SHA 與呼叫方式。
    - (ii) 列出樣本期（探測指令 §6.4 所用唯讀複本涵蓋的全部日期）內被判成 confirmed、但其實是週末（依 VS-1 的當地日期）或 TWSE 官方休市日的台股日子。休市表要註明官方出處與查證日期。**台股這個數字必須為 0，否則不得翻轉。** 美股同時列出被判成 confirmed 的週末，應為 0；不為 0 時列入回報，但不屬於 R4c 翻轉條件。
    - (iii) 探測指令 §6.3.3a（判讀矩陣的 F-7 補充欄）的結果：逐來源、逐輪列出「VS-4 之後的當日 bar 是否已定案」。任何一格為否，F-7 即觸發，不得翻轉。
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
13. （A-96″）個股詳細頁有下列幾類數字和日期，都出自同一個 loader（`load_bars`）讀進的日線，而且都不讀 `valuation_state`：
    - 前端以 `/api/bars` 的列計算或直接呈現的：
      - 關鍵價位，以及關鍵價位面板的停損與目標參考；
      - 六項觀察條件；
      - 操作卡（`DecisionCard`）的收盤、停損、停利；
      - K 線圖（`PriceChart`），會把每一列直接畫成 K 棒；
      - 技術分析結論句（取最後一列收盤）；
      - 頁尾「關鍵價位參考」與「六項觀察條件」兩組（收盤、日期、根數）。
    - 後端以各端點自己載入的列計算的：
      - 指標（`/api/signals`）；
      - 操作摘要與建議卡（`/api/advice`），含頁尾「操作摘要」組的資料日期句（`asOfStatement`）；
      - 槓桿專章的持有期間與報酬拆解（`/api/leverage`，只有持股才有）（風控 2026-10-17 A-96″ 回送確認）。
    - 資料列有日期異常時，照樣進入這些計算。本 ADR 不改變計算，只要求揭露（CS-26）。
    - 這同時適用於持股與「確認未持有」的標的。非持股沒有 `build_summary` 列；CS-26 第 1 點的逐列標記落地之前，非持股完全沒有日期異常的檢查。
    - **涵蓋限制**：逐列標記只抓得到日曆判定為非交易日的列；observed／weekday_assumed basis 下的平日休市列不會被標記（同第 1 點）。
    - **涵蓋限制（K-27）**：槓桿專章的指數列（`load_index_bars`，用於侵蝕情境與報酬拆解的指數側）不在逐列標記範圍內；指數列的日期異常揭露另案處理（CS-26 第 6 點）。
    - **已知限制（K-32；dev-lead 2026-10-17 查證 B-3～B-5）**：
      - **窗口**：各端點 `load_bars` 回看 540、1200 日，`/api/bars` 最多 2000 日；evidence 窗口下限是 D−400。窗口外的列落在 R 之外，依週一至週五規則判定，所以非 official basis 下，窗口外的平日休市列不會被標記，和第 1 點屬同一類涵蓋限制。端點的 `end` 仍是伺服器的 `date.today()`，不作為 D。不得用調整 `load_bars` 窗口的方式對齊，那會改變計算的輸入（CS-4、CS-26 第 4 點）。
      - **市場鍵**：快取依 `bar.market` 寫入，ladder 沒有檢查 `bar.market` 是否等於請求的 market。目前各 adapter 都寫死市場，到不了；萬一發生，該列不在請求市場的 evidence 內，方向是多標（K-33 另案）。
      - **並行刪除**：示範資料清除（`delete_by_source`）剛好和請求同時發生時，已回傳的示範列可能不在 evidence 內，方向是多標。
      - 上述情形都不會讓異常列少標。
    - 要不要在資料層剔除異常列，屬於第 10 點「寫入側品質閘門另案」，本點不處理。

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

### D-9 觀察交易日集合的輸入（r3）
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
  - （A-96″，澄清，方向不變）CS-4 只約束上列的後端計算模組。前端顯示層可以讀 `valuation_state`，以及 CS-26 的逐列 `date_anomaly` 標記與 envelope 的 `date_anomaly_rows`、`anomaly_valid_until`，但只能用來做同區塊揭露，不得改變任何計算或計算的輸入。
    - 這句只是澄清現行範圍，不得被讀成禁止日後改採「附原因、不渲染」的 fail-closed 做法。那屬於顯示面變更，要另外送風控。
  - （A-96″，收緊）**grep 範圍擴大**：
    - 被檢查的字串：`row_date_anomaly`、`date_anomaly`、`date_anomaly_rows`、`anomaly_valid_until`、`last_bar_date_anomaly`。
    - 禁止範圍是上列模組的**計算 package**，不得呼叫或讀取這些字串：
      - 現存的是 `app/advice`、`app/alerts`、`app/kelly`、`app/playbook`、`app/signals`；
      - limits、outlook、plan、forecast，以落地時的 package 路徑為準；
      - 另加 `app/leverage`（風控 2026-10-17 A-96″ 回送確認）。
    - 這是落實 CS-26 第 4 點「計算不變」。
  - **envelope 組裝層例外（K-5）**：
    - 除了 `close_state.py` 內 D-4 狀態機自己的呼叫之外，只有 `app/api/{bars,signals,advice,leverage}.py` 可以呼叫 `row_date_anomaly`。
    - 呼叫時機只能在該端點的計算完成之後，用途只限附加標記。
    - 其他 `app/api/*.py` 和任何計算 package 都不得呼叫（grep）。
  - **「計算不變」性質測試**：適用 `/api/bars`、`/api/signals`、`/api/advice`，以及 `/api/leverage`（風控 2026-10-17 A-96″ 回送確認）。
    - 同一份 `load_bars` 輸入跑兩次：(a) 正常組裝；(b) 用 stub 把 `row_date_anomaly` 換成永遠回 None。
    - 除了 `date_anomaly`、`date_anomaly_rows`、`anomaly_valid_until`、`last_bar_date_anomaly` 四個欄位，兩次的回應 payload 必須逐位相同。
    - 用 spy 斷言 `row_date_anomaly` 的第一次呼叫，晚於該端點的計算函式回傳；計算函式的簽章不接受任何異常標記參數。
    - 兩次組裝注入同一個固定時鐘，`as_of`、`generated_at` 等時間欄位因此相同；排除欄位只限上列四個，不得再增列（K-20）。
- **CS-5**：前端狀態元件不出現 `new Date(`、`Date.now`、時段常數，也不 import `tradingCalendar.ts`。重新取得只能放在資料取得層，依 `state_valid_until` 排程。
- **CS-6**：不得移除既有的 `data_status`／`is_within_ttl` 徽章。
- **CS-7**：`market_hours` 的每個 VS 都有 `verified_on` 與出處欄位（測試）。VS-4 必須引用 `publish_cutoff`，不得複製數值（grep）。
- **CS-8**：`TradingCalendar` 的既有語意不變（playbook 的測試維持綠燈）。
- **CS-9**：`basis_for(D) == weekday_assumed` 而且 D 是平日時，不得輸出 `market_closed`（性質測試）。
- **CS-10**：`pre_open` 永遠不對應到 LM-27（前端對應表測試）。
- **CS-11**（r1 改，A-17）：字面對應表窮舉所有 (state, sub_reason, session_basis, market) 組合（`every state has a template`）。
  - （r2，A-39）R4b × observed 必須有對應（LM-71＋LM-26）。另加測試：這個組合出現時，`build_summary` 記 WARNING。`close_state.py` 維持純函式，不做 log。
- **CS-12**（r1 改，A-17；r2 改，A-39；r3″ 改，A-87）：
  - LM-27 只在 `market=TW` 而且 `basis=official` 時渲染；
  - LM-24 只在 `market=TW`，而且 `basis=official`，或 `basis=observed`、`sub_reason=after_close_pending` 時渲染；
    - LM-24 在 `basis=observed`、`sub_reason=after_close_pending` 時渲染，要等翻轉 PR 合併後才生效。合併前，D-9 要已經實作合併，而且 CST-5～CST-9 綠燈（D-5「observed 兩列的說明」第二點 (a)）；data-engineer 的確認回報要經過風控單項確認，並由 qa 審查。翻轉 PR 的完整合併條件以 D-5 該點 (a)～(c) 為準。
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
  - 其他模組不得出現 `publish_cutoff` 與 `trade_date`、`acquired_at`、`as_of`、`fetched_at` 的行內比較。
  - `final_after(` 只能在 `session_calendar.py` 內被呼叫，恰好兩處：`is_final`，以及 `final_session_evidence`（grep 加 AST）。
  - `final_session_evidence` 只把 `final_after` 的回傳值原樣放進它回傳的稽核 payload。這個值不得出現在任何比較、布林運算、條件式，或 `min`／`max`／`sorted` 的參數中，也不得傳給 payload 建構以外的任何呼叫（AST 斷言）。payload 中各 run 是否定案，一律在同一函式內呼叫 `is_final` 取得。
  - `final_session_evidence` 的回傳值只能由 ADR-0027 A-77 第 7 項的 X2 寫入函式讀取，原樣寫入 `set_i_check`，不得作為任何判定的輸入（AST 列舉呼叫點）。X2 寫入函式判定「d ∉ (i)」只能經 `final_sessions()`（也就是 `is_final`），不得拿 `set_i_check.final_after` 比較時戳。
  - `final_sessions` 與 `session_calendar.py` 內的其他函式，一律經 `is_final` 判定，不得呼叫 `final_after(`。
  - 增列呼叫位置或放寬上述限制，依 CS-21 通則視為放寬，合併前送風控單項確認。
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
- **CS-26**（A-96″，收緊；風控 2026-10-17 A-96 條件、A-96′ 單項確認 K-1～K-16）：個股詳細頁中由日線列衍生的數字與日期，在所用日線含日期異常列時，要在同一區塊揭露。
  - 持股價格區塊在 `valuation_state = date_anomaly` 時渲染 LM-70（PM AC-B5a-10），依 CS-27。
  1. **觸發條件：逐列標記，涵蓋實際進入計算的日線。**
     - **判定函式**：`close_state.py` 抽出純函式 `row_date_anomaly(trade_date, *, D, phase, calendar) -> sub_reason | None`。
       - D、phase 依 D-4「先定義」；D 不是交易日時，phase 為 None。calendar 是同一個 `SessionCalendar`。
       - D-4 的 R2、R2′、R2″、R2‴ 改成呼叫它，輸出不變（CST-2 維持綠燈）。
     - **判定規則**：
       - `trade_date > D` → `future_date`；
       - `trade_date == D`、D 是交易日，而且在 `pre_open` → `before_open`；
       - `trade_date == D`、D 不是交易日 → basis＝official 時為 `official_conflict`，否則為 `not_a_session`；
       - `trade_date < D`，而且 `is_session(trade_date)` 為 False → `unconfirmed_session`。
         - 這一項對 `P < trade_date < D` 的列就是 R2‴；對 `trade_date < P`（含 P 為 None）的歷史列是延伸。
         - D-4 本身仍只在 `price_date > P` 時套用 R2‴；`price_date < P` 或 P 為 None 時仍走 R6，估值狀態不變。
       - 其他情形 → None。`trade_date == P` 時必為 None。
     - **`/api/bars/{symbol}` 的欄位**：
       - 每一列帶 `date_anomaly: Literal["future_date","before_open","official_conflict","not_a_session","unconfirmed_session"] | None`，由後端逐列計算；
       - envelope 帶 `date_anomaly_rows: int`，等於標記非 None 的列數；
       - envelope 帶 `anomaly_valid_until`：語意同 D-4 的 `state_valid_until`，前端資料層依它重新取得。
     - **其他端點（K-14）**：
       - 凡是個股頁取用、而且由 `load_bars` 的列計算出來的端點，envelope 都帶 `date_anomaly_rows: int` 與 `anomaly_valid_until`。
       - 計算用同一個 `row_date_anomaly` 和同一個 calendar 建構函式，作用在**該端點自己載入的列**上，不得沿用 `/api/bars` 的結果。
       - v1 涵蓋 `/api/signals`、`/api/advice`。
       - `/api/leverage` 納入（K-17）。只對 `load_bars` 載入的 ETF 列計算，不含 `load_index_bars` 的指數列；計數範圍是傳入 `build_leverage_chapter` 的全部 ETF 列，不得縮成 `opened_at` 之後或與指數 inner join 之後的列，縮小視為放寬，須送風控（K-18）。
       - `/api/signals`、`/api/advice`、`/api/leverage` 的 envelope 另帶 `last_bar_date_anomaly: bool`（必填），由同一個 `row_date_anomaly` 對該端點自己載入、日期等於 `data.last_bar_date` 的那一列計算（K-26）。
       - 上列各欄位都是必填：`/api/bars` 的逐列 `date_anomaly`（值可以是 null，但欄位必須存在）、`date_anomaly_rows`、`anomaly_valid_until`，以及其他端點的 `date_anomaly_rows`、`anomaly_valid_until`、`last_bar_date_anomaly`。前端型別不得標成 optional。
     - **後端計算約束**（每個端點、每次請求）：
       - 只讀一次時鐘，D 由 `now.astimezone(VS-1)` 取得（同 CS-3）。各端點現行的 `end = date.today()`（`bars.py:89`、`signals.py:94`、`advice.py:156`、`leverage.py:95`）不得當作 D；窗口本身不在本條範圍內。
       - calendar 和 `build_summary` 用同一個建構函式（官方優先，退回 D-9 觀察日曆），不得另建。
       - 最多一次 `market_session_evidence` 讀取，窗口依 D-9 第 6 點，用該端點所載各列日期的最小值代入。
         - **讀取順序（K-29）**：evidence 讀取一律在該端點的 `load_bars` 回傳之後，以請求的 market 讀取。`load_bars` 的即時與增量路徑在回傳前已寫入 `price_bars_cache`（dev-lead 2026-10-17 查證 A 段），而 `PriceBarCache` 各方法不共用 transaction（B-1），所以順序是唯一的保證。
         - **`/api/advice`（K-31）**：該端點在同一請求內另呼叫 `build_summary`（`advice.py:167`），後者依 CS-22 每次 build、每個市場最多讀一次 evidence。由 dev-lead 在 T1-17 實作時擇一，並在 PR 說明載明：
           - (a) **重用**：同市場時重用 `build_summary` 那一次讀取與 calendar。前提是該次讀取的窗口依 D-9 第 6 點涵蓋兩者所需的日期，而且 `build_summary` 的輸出不變（CST-2 維持綠燈）。
           - (b) **第二次讀取**：異常標記另讀一次。條件是在 `load_bars` 與 `build_summary` 都回傳之後讀取，只供 envelope 附加標記，不回饋 `build_summary`；CST-11 對 `/api/advice` 的計數明定為「`build_summary` 一次＋標記一次，至多兩次」。
           - (a)(b) 以外的做法，依 K-16 回送風控。
       - 只在 envelope 組裝層、計算完成之後附加（CS-4 例外）。
     - **持股與非持股一體適用**：各端點都不讀 `valuation_state`，也不依是否持有分流。
     - **回送條件（K-16）**：實作時出現以下任一情形，要回送風控，不得自行降級成只標 `> P`，也不得改由前端判定：
       - 共用的 calendar 建構函式重用不了，要另建一份日曆；
       - 每個請求的 evidence 讀取超過一次（`/api/advice` 依 K-31 除外，見本點第四款）；
       - 會違反 CS-1 或 CS-19 的可達性。
       - （風控 2026-10-17，依 dev-lead 查證裁定）dev-lead 查證列出的 B-1～B-6（`work/reviews/2026-10-17-load_bars與evidence一致性查證-dev-lead.md`），已分別由讀取順序（K-29）、CST-10 日層級前提（K-23）、CST-11 fixture 約束（K-30）與 D-6 第 13 點已知限制（K-32）處理，本身不觸發回送。下列情形仍須回送風控：(a) 任一端點每個請求的 evidence 讀取超過一次，`/api/advice` 依 K-31 的 (a)(b) 除外；(b) 把 `load_bars` 的列併入 evidence、calendar 輸入或分類結果；(c) evidence 讀取移到 `load_bars` 回傳之前；(d) K-33 的市場閘門落地之前，有 adapter 改由 provider 回應決定 market。
     - **前端觸發（K-14 (i)）**：每個登記區塊依第 2 點表內登記的「觸發來源」觸發，不得只看 `/api/bars`。
       - 來源 `bars`：傳入該區塊的 bars 陣列中，任一列 `date_anomaly != null`；
       - 來源 `signals`、`advice`、`leverage`：該 envelope 的 `date_anomaly_rows > 0`。
       - **前端不得另寫判定。**
     - 前端揭露元件不得出現 `new Date(`、`Date.now`、時段常數，也不得 import `tradingCalendar.ts`（比照 CS-5）。
  2. **揭露範圍與位置**
     - **範圍**：以封閉清單 `BARS_DERIVED_BLOCKS: Readonly<Record<BlockId, readonly ("bars"|"signals"|"advice"|"leverage")[]>>` 登記，值是觸發來源：

       | BlockId | 區塊 | 觸發來源 |
       |---|---|---|
       | `KeyLevelsPanel` | 關鍵價位，含停損與目標參考 | bars |
       | `EntryObservationPanel` | 六項觀察條件 | bars、signals、advice |
       | `DecisionCard` | 收盤、停損、停利格 | bars、advice、signals |
       | `PriceChart` | K 線圖 | bars、signals（MA 疊圖） |
       | `TechOneLiner` | 技術分析結論句（`buildTechOneLiner`） | bars |
       | `KeyLevelsFooterGroup` | 頁尾「關鍵價位參考」（`buildKeyLevelsFooterItems`） | bars |
       | `EntryFooterGroup` | 頁尾「六項觀察條件」（`buildEntryFooterItems`） | bars |
       | `OperationSummaryFooterGroup` | 頁尾「操作摘要」（`buildSummaryFooterItems`） | advice |
       | `IndicatorOverviewChipsRow` | 指標概覽 chips | signals |
       | `TechnicalIndicatorsPanel` | 指標卡 | signals |
       | `OperationSummaryPanel` | 操作摘要 | advice |
       | `AdviceCardView` | 建議卡 | advice |
       | `LeverageChapterView` | 槓桿專章（風控 2026-10-17 A-96″ 回送確認） | leverage |

     - **觸發來源的完整性**：每個區塊登記的來源，必須 ⊇ 它在 `page.tsx` 實際取用的 envelope。
       - 以 AST 收集該區塊 JSX props 與 builder 參數中引用的 `bars`、`signals`、`advice`、`leverage` query 物件；
       - `entryLevels` 視為 bars，`entryObservation` 視為 bars＋signals＋advice。
       - 判斷不了的一律登記全部四個來源。
       - AST 另掃描每個登記區塊的元件模組，以及它在 `position/[symbol]/`、`app/lib/` 內 import 的模組：凡直接呼叫 `useBars`、`useSignals`、`useAdvice`、`useLeverageChapter` 或其他取用 `/api/*` 的 hook，該來源也必須在登記內，否則失敗（K-22）。
       - 刪除任何區塊已登記的來源，或縮小技術分析區段的聯集，視為放寬，須送風控。AST 測試做不到時，改採整頁聯集（K-14 (ii)），不得刪除測試。
     - **位置**：
       - (a) 原則：每個區塊在同一區塊內渲染揭露，不收合、不放在 `<details>` 內，也不只用 hover 或 tooltip。
       - (b) **技術分析區段**：`PriceChart`、`TechOneLiner`、`IndicatorOverviewChipsRow`、`TechnicalIndicatorsPanel` 共用一個主視圖揭露。
         - 觸發來源是四者的聯集，也就是 bars ∪ signals；
         - 位置在主視圖，緊鄰「資料截至 {MM-DD}」徽章，與圖、結論句同在一區，不在 `<details>` 內；
         - `TechnicalIndicatorsPanel` 位在 `<details>` 內，它的揭露由這個主視圖揭露承擔，不必在 `<details>` 內重複。
         - 顯示條件不綁 `PriceChart` 是否掛載：區段內任一成員讀取點有渲染（含 compact 徽章、`DataMetaStatusBadge` 的 `lastBarDate`、「共 N 根日線」），而且聯集來源有異常，就渲染（K-25）。重新啟用 TradingView 頁籤時，揭露位置與字面須送風控。
       - (c) **`AdviceCardView`**：卡片本身收在 `<details>` 內（CEO 2026-09-19）。揭露放在 `<details>` 之前、同一個 `<section>` 內，收合時也看得到。
       - (d) **頁尾三組**（`KeyLevelsFooterGroup`、`EntryFooterGroup`、`OperationSummaryFooterGroup`）：在各自組內帶揭露。頁尾區本身是 `<details>`，這是唯一允許揭露落在 `<details>` 內的地方，而且不取代 `KeyLevelsPanel`、`EntryObservationPanel`、`OperationSummaryPanel` 在主視圖的揭露。這個例外不得延伸到其他 `<details>`。
       - (e) 其餘區塊依 (a)。
       - (f) **`LeverageChapterView`**（K-19）：專章有渲染（`chapter_status ≠ not_applicable`），而且 leverage envelope 的 `date_anomaly_rows > 0` 時，不論 `chapter_status` 為何，都在專章容器內、標題列之下渲染揭露，不在 `AssumptionsList` 的 `<details>` 內。揭露字面不得暗示指數列（侵蝕情境、拆解的指數側）已經檢查。非持股回 404、不渲染專章時，也不渲染專章揭露。
     - **讀取點列舉（K-2）**：
       - 範圍：`position/[symbol]/` 底下每一個讀取點，包括 `page.tsx` 的行內運算式和 builder 函式的參數。讀取點指：
         - `bars.data.bars`；
         - `bars.data.data.last_bar_date`、`bars.data.data.first_bar_date`；
         - 所有名為 `bars` 的 prop。
       - 每個讀取點都要歸入 `BARS_DERIVED_BLOCKS` 的某一項，或歸入封閉豁免清單 `BARS_NON_NUMERIC_USES`。沒有歸類，測試就失敗（AST 契約測試）。
       - 技術分析區段的 bars 日期呈現（徽章與「共 N 根日線」）歸入 `PriceChart`，因為它們描述的是 K 線圖所畫的那份序列。
       - `BARS_NON_NUMERIC_USES` 在 v1 只有兩項：
         - `PriceUnitBadge`：只檢查幣別；
         - `tvExchangeHint`：只讀 `source`。
       - 要增列豁免，須修訂本條並送風控。
       - 讀取點另含 `bars.data.data.bar_count`、`bars.data.data.trading_days_behind`。`source`、`status`、`staleness_minutes`、`is_within_ttl`、`reason` 是取得來源與時效的 provenance，不由列日期衍生，不列入讀取點，也不新增豁免；`BARS_NON_NUMERIC_USES` 仍只有兩項（K-28）。
       - **資料新舊判斷（K-28）**：某 envelope 的 `last_bar_date_anomaly` 為 True（`/api/bars` 則為最後一列 `date_anomaly != null`）時，前端顯示層一律把該 envelope 的 `trading_days_behind` 視同 null：不得據以省略「資料過舊」提示，改走既有「無法向交易日曆確認」路徑（`resolveAsOfStatement` 的 null 分支）。這屬於顯示層揭露，不改變任何計算或計算的輸入（CS-4 澄清）。
     - **日期呈現（K-3）**：
       - 頁面上每一處呈現 bars 日期的地方，該日期所對應的列（`bars` 陣列中 `date` 等於該值的列）如果 `date_anomaly != null`，就不得用正常資料日期的樣式呈現。
         - 找不到對應列時，同樣不得用正常樣式（風控 2026-10-17 A-96″ 回送確認）。
       - 涵蓋：
         - compact 徽章；
         - `DataMetaStatusBadge` 的 `lastBarDate`，主視圖與 `<details>` 內都算；
         - 「共 N 根日線（first ~ last）」；
         - `EntryObservationPanel` 的 `dataAsOfDates.bars`；
         - 關鍵價位面板與頁尾的 `closeDate`。
       - 「旁邊看得到同一揭露」以主視圖徽章為準。`<details>` 內的呈現不得用正常日期的樣式，但不必另外重複揭露。
       - **其他 envelope 的資料日期（K-26）**：下列呈現在該 envelope 的 `last_bar_date_anomaly` 為 True 時，不得用正常資料日期的樣式：
         - 指標的 compact 與完整 `DataMetaStatusBadge`（主視圖與「詳細」內）、`TechnicalIndicatorsPanel` 的 `lastBarDate`；
         - `OperationSummaryPanel`、`DecisionCard`、`AdviceCardView` 的「資料截至」徽章與 `DataMetaStatusBadge`；
         - `EntryObservationPanel` 的 `dataAsOfDates.signals`、`dataAsOfDates.advice`；
         - 操作摘要的 `asOfStatement`（含頁尾）；
         - 專章的 `holding.last_bar_date`、`drag.last_bar_date`。
       - 呈現的日期不等於該 envelope 的 `data.last_bar_date`，又沒有逐日旗標時（例如專章的 `drag.window.end_date`），依「找不到對應列」規則：該 envelope 的 `date_anomaly_rows > 0` 時，不得用正常樣式。日後改成提供逐日旗標，才可以縮小。
     - **不得反向保證（K-4）**：
       - 沒有異常列時，不出現揭露；
       - 也不得出現任何宣稱日期已經過檢查、或資料沒有問題的保證字面（例子見風控 2026-10-17 A-96′ 單項確認 K-4）。
       - 理由：本條的檢查涵蓋不全（D-6 第 13 點涵蓋限制），這類保證不屬實。
  3. **字面**：
     - 交 creative-lead 起草、風控逐字審，不得有「仍可參考」之類的弱化語氣；
     - `sub_reason` 不渲染成字面（同 D-4）；
     - 字面核可之前，T1-17 不得合併（比照 D-5 末句）。
  4. **計算不變**：揭露不改變任何計算，也不改變計算的輸入（CS-4 性質測試）。
  5. **行動計畫鏈的前提**：本條的核可，以「ADR-0027 的行動計畫鏈不會吃進日期異常的價格」為前提〔推論〕。依據是 ADR-0027 FL-25 的 fixture，以及 A-75 (iv) 官方休市日的單一定義（ADR-0027 A-96″ 增補）。
  6. **另案**（風控 2026-10-17 A-96″ 回送確認）：
     - (a) 指數列標記（G-2）：tech-architect 在 T1-17 合併前，於 `work/` 開立任務單，評估以指數所屬市場的 calendar 對 `load_index_bars` 的列逐列標記，含 evidence 讀取次數（D-9 第 6 點以市場為單位）與 CS-19 可達性；提案於 T1-17 合併後 30 日內送風控。期間依 K-27 照實揭露涵蓋限制。
     - (b) D-4 R6 對 `price_date < P` 週末列的處理（G-4）：下一次修訂 D-4，或 CS-26／CS-27 字面送風控逐字審時（以先到者為準），tech-architect 附評估。在此之前，持股價格區塊與 CS-26 揭露兩句並存，風控已確認兩句都屬實。
     - (c) **市場閘門（B-4，K-33）**：dev-lead 在 T1-17 合併前於 `work/` 開立任務單，評估在 ladder 加「`bar.market` 不等於請求的 market 就拒絕」的閘門（收緊）。觸發條件：任何 adapter 改由 provider 回應決定 market，或新增 adapter 時，這個閘門必須先合併。在此之前依 K-32 列為已知限制。
- **CS-27**（A-97′，收緊；風控 2026-10-17 A-97 條件）：個股詳細頁顯示的持股價格與估值狀態，取自 `build_summary` 同一列的輸出（`valuation_state`，以及同一個 `price_date`），用和庫存頁同一個前端狀態元件、同一張 D-5 對應表呈現。
  - 個股頁不得另外計算狀態，也不得用 bars 的 `last_bar_date` 代替 `reference_date`。
  - 前端契約測試：同一檔在兩頁的價格、日期、字面 ID 逐位相同（PV-52、AC-B5a-10）。
  - 非持股（沒有 `build_summary` 列）不顯示估值狀態，維持現行徽章。**這類標的的日期異常由 CS-26 第 1 點的逐列標記涵蓋，不得有沒有檢查的情形。** 契約測試：非持股、bars 含異常列時，渲染 CS-26 的揭露（AC-B5a-13）。
  - （採用風控 suggested）同一頁上有多顆日期徽章時，每顆都要標明它指的是什麼，例如「日線資料截至」「估值價格日期」，不得出現兩個沒有說明的日期。字面交 creative-lead 起草、風控審。
- 排入 T1-17，由 dev-lead（`app/api/*`、`close_state.py`）與 frontend-engineer 承接，qa-e2e 驗收。

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
- **CST-10**（K-7、K-8）：`row_date_anomaly` 的性質測試。
  - **與 D-4 一致**：在 P 不為 None 而且 `price_date > P`，或 `price_date ≥ D` 的輸入上，結果和 D-4 R2～R2‴ 的 `sub_reason` 逐位相同（P 為 None 而且 `price_date < D` 時，D-4 走 R6，不在比較範圍）。
  - **全定義域**：對任意 `trade_date < D`，結果是 `unconfirmed_session`，若且唯若 `is_session(trade_date)` 為 False；否則為 None。`trade_date == P` 時必為 None。
  - **結構性質**（K-8、K-23）：`basis_for(trade_date) ≠ official`、`trade_date` 是平日，而且在同一次、依請求 market 讀取的 `market_session_evidence` 分類結果中，`trade_date` 屬於 confirmed 或 unconfirmed（同市場、該日至少有一列，任何 symbol、任何 source，不要求是同一列）時，`row_date_anomaly` 對該列必為 None。
    - **餘集不得留白**：平日、R 內 absent（basis＝observed）→ `unconfirmed_session`；平日、在 R 之外 → None。兩者各一個 fixture。
    - **不得自證**（K-24）：端點不得把自己載入的列併入 evidence、calendar 的輸入或分類結果，也不得以「該列不在 evidence 內」為由略過 `row_date_anomaly`，或覆寫它的結果。結果一律由同一個 calendar 判定；R 之外依週一至週五規則得到 None，屬於 D-9 第 5 點本身的結果，不算略過。違反任一項都是放寬，須送風控。
  - 五個 `sub_reason` 各一個 fixture；歷史週末列（`< P`）→ `unconfirmed_session`。
- **CST-11**（K-14、K-15）：每個端點的契約測試。
  - `/api/bars`：
    - 每一列都有 `date_anomaly` 欄；
    - `date_anomaly_rows` 等於非 None 的列數；
    - `anomaly_valid_until` 跨過 VS-2 時，`before_open` 消失。
  - `/api/signals`、`/api/advice`：`date_anomaly_rows` 等於「對該端點自己載入的列逐列呼叫 `row_date_anomaly`」得到的非 None 列數。`last_bar_date_anomaly` 等於對 `data.last_bar_date` 那一列呼叫 `row_date_anomaly` 是否非 None（K-26）。
  - 每個端點、每次請求都只讀一次時鐘，最多一次 evidence 讀取（計數）；`/api/advice` 的 evidence 讀取次數依 CS-26 第 1 點 K-31 所選方式計數，選 (b) 時至多兩次。
    - 「只讀一次時鐘」與計數的對象，是 envelope 組裝層為 `row_date_anomaly`、`anomaly_valid_until` 取得 D 與 phase 的那一次讀取。各端點既有的 `date.today()`、`now_iso()`、`build_leverage_chapter` 的 `generated_at` 不在計數內，但 D 不得取自它們。不得因既有讀取而刪除或放寬本項計數（K-21）。
  - 同一序列在持股與非持股時，結果相同。
  - `/api/leverage`：計數含傳入 `build_leverage_chapter` 的全部 ETF 列（K-18），不含指數列；指數列有異常、ETF 列無異常時，`date_anomaly_rows == 0`（範圍界定，K-27）。非持股回 404，「持股與非持股相同」一格不適用，改以前端斷言非持股不渲染專章與其揭露。`last_bar_date_anomaly` 等於對 `data.last_bar_date` 那一列呼叫 `row_date_anomaly` 是否非 None（K-26）。
  - （採用風控 suggested K-9）早於 D−400、落在證據窗口外的週末列，依週一至週五規則標成 `unconfirmed_session`。
  - **呼叫順序**（K-29）：用 spy 斷言每個端點的 `market_session_evidence` 呼叫晚於 `load_bars` 回傳；`/api/advice` 依 K-31 所選方式計數。
  - **fixture 約束**（K-30）：端點契約測試用 `MarketDataService`，接上與 evidence 讀取同一個 `tmp_path` 快取；改用 `FakePriceService` 等不寫快取的 `PriceService` 時，必須先把同一批列 seed 進該快取。另加一格刻意不 seed 的對照：R 內平日、快取中當日沒有任何列 → 該列為 `unconfirmed_session`（CST-10 餘集，端點層級）。
- **CST-12**：前端契約與 e2e。
  - `BARS_DERIVED_BLOCKS` 的鍵恰好等於 CS-26 第 2 點的表；`BARS_NON_NUMERIC_USES` 恰好是兩項；
  - 讀取點 AST 列舉：沒有歸類就失敗；
  - 觸發來源 ⊇ 實際取用的 envelope（AST）；
  - 每個來源各一個 fixture：只有該來源有異常時，登記了它的區塊都揭露；
  - 揭露 DOM 不在 `<details>` 內，只有頁尾三組（`KeyLevelsFooterGroup`、`EntryFooterGroup`、`OperationSummaryFooterGroup`）例外，這三組斷言揭露在組內；建議卡的揭露在 `<details>` 之外、同一 `<section>` 內；
  - 主視圖徽章旁看得到揭露；K-3 列舉的每一處日期呈現，對應列異常時都不是正常樣式；
  - 沒有異常時不出現揭露，全頁 DOM 也不含 K-4 所指的保證字面（掃描清單由 creative-lead 定稿後寫入測試）；
  - 非持股含異常列時渲染揭露（CS-27）；
  - 375 與 1280 寬度實機驗收（AC-B5a-13）。
  - K-3「找不到對應列」各一個 fixture；K-26 列舉的每一處，在 `last_bar_date_anomaly` 為 True 時都不是正常樣式；
  - K-28：`last_bar_date_anomaly` 為 True、`trading_days_behind` 為 0 時，`asOfStatement` 走 null 分支；
  - 技術分析區段圖表未掛載時，徽章旁的揭露仍在（K-25）；
  - 專章在 `chapter_status` 為 ok、partial、insufficient_data 時，只要 `date_anomaly_rows > 0` 都渲染揭露，而且不在 `<details>` 內（K-19）。
- **qa-e2e**：375 與 1280 寬度實機驗收 AC-B5a-1～6，加上 `pre_open` 與推算模式。

## 失效條件
- **F-1**：盤中價接線。LM-27、LM-28 失效，依 ADR-0014 重審。
- **F-2**：T1-07 發現有來源會回傳當日暫定 bar。修訂 ADR-0009，R3′ 只是縱深防禦。
- **F-3**：各來源的定案時間不同。VS-4 升級成 (market, source) 鍵。
- **F-4**：交易所時段變更（例如延長交易、補行交易日）。
- **F-5**：官方休市日來源持續不可得（ADR-0025 F-6）。
- **F-6**：納入新的市場。
- **F-7**（r3；r3″ 補參照，A-92）：探測指令（`work/research/2026-10-16-Phase1資料源探測指令-CEO本機代跑.md`）§6.3 發現某個所用來源在 VS-4 之後仍回傳未定案的 bar。走 F-3，把 VS-4 升級成 (market, source) 鍵；已翻轉的 R4c 退回 LM-71＋LM-26，直到重新確認。
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
  - 已裁示（r3，A-52；r3″ 更新，A-93）：r3 設計的單項確認為 APPROVE WITH CONDITIONS，沒有 VETO（`work/reviews/2026-10-17-ADR-0028-r3單項確認-風控.md`）。R2″ 改寫、R2‴ 都對應 LM-70，風控認定屬實，不必另外起草。required R-1～R-3 已由 r3′ 寫入（SE-2 與 CST-5 的 R-1 fixture、CS-21 通則、D-5「observed 兩列的說明」第二點 (b) (i)～(iii)）。R-4 屬於 ADR-0027，不在本 ADR。
  - 新狀態的字面。
  - （A-96″）個股頁異常揭露與多徽章指涉標籤的字面逐字審；G-2、G-4 另案（CS-26 第 6 點）。
- **data-engineer**：
  - Q-B7：各日線來源在盤中或收盤剛結束時，會不會回傳當日、尚未定案的 bar；
  - VS-2～VS-6 的查證；
  - 週六補行交易日。
  - 新增（r2，A-40）：觀察日集合來源的確認。
  - 新增（r3，A-52）：SE-4、SE-5 的確認；R4c 翻轉前的確認回報內容（依 D-5「observed 兩列的說明」第二點 (b)）。
  - 新增（r3′，A-52′）：
    - 確認所有寫入 `price_bars_cache` 的轉接器，`PriceBar.as_of` 都不晚於第一個請求送出的時間；
    - D-5「observed 兩列的說明」第二點 (b) (i)～(iii) 的回報內容。
- **CEO**：接受新狀態；#15 連網環境。
  - 新增（r3，A-52）：知悉方案 C 被否決，因此 ADR-0027 和 ADR-0028 對「觀察日」各用不同定義。
- **tech-architect**：Q-B6（ADR-0009 是否吃官方假日表），在 T1-13 時另案處理。
- **creative-lead**：CS-26 各區塊的異常揭露字面、CS-27 多徽章的指涉標籤。不得有「仍可參考」，也不得有 K-4 所指的保證字面。
- **dev-lead**：（A-96″）`load_bars` 與 evidence 的一致性已查證，依 K-29～K-33 處理。T1-17 實作時，依 CS-26 第 1 點 K-31 為 `/api/advice` 擇一，並在 PR 說明載明；B-4 任務單在 T1-17 合併前開立。

## 未查證事項
- 所有 VS 的數值；08:30 盤前委託；週六補行交易日；US 的交易時段。
- B-2 所引的 `valuation.py` 與 ADR-0019 行號，除了 343、382、223 以外，都轉引自 T1 評估。
- （r3、r3′，A-52、A-52′）新增：
  - 快取中是否有指數序列既不在 `INDEX_SERIES_SYMBOLS`、也不以 `^` 開頭〔未查證，待 data-engineer〕；
  - 各來源在真實交易日時 volume 的語意〔未查證〕；
  - 所有日線轉接器都在送出請求前蓋 `as_of`〔已查 `twse.py:88`，其餘轉接器只 grep 了 `now = datetime.now(UTC)` 的位置，推論〕；
  - 快取路徑下 `acquired_at` 晚於當日列寫入時間的情境〔推論，CST-9 釘住〕。
- （A-96″）「非 official basis 下的平日列一定是 session」是依 D-9 第 4、5 點所做的推論，以 CST-10 釘住。`load_bars` 回傳的列，在回傳當下都已寫入 `price_bars_cache`（同市場、同日期），已由 dev-lead 2026-10-17 查證（`work/reviews/2026-10-17-load_bars與evidence一致性查證-dev-lead.md`，探針 6 passed）。「一定落在同一次 evidence 讀取內」不成立（B-1～B-6），所以 CST-10 改用日層級前提，不依賴這一點。evidence 讀取尚未實作，實際讀取順序〔未查證〕，以 CST-11 的呼叫順序斷言釘住（K-29）。

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

---

> r3″（2026-10-17）依 tech-architect「ADR-0028 r3″ 更正」A-87～A-95 套用（`work/reviews/2026-10-17-ADR-0028-r3雙撇更正A87至A95-tech-architect.md`）。只更正 r3 套用後的接合、參照與編修：A-87、A-91 為收緊，其餘方向不變，沒有放寬，依 CS-21 通則不必送風控。檔頭狀態維持 proposed。
> 被改寫或取代的原文逐字保留於下；引用區塊內的文字即 r3″ 之前（commit 1d69acd）的原文。

**A-87（CS-12）**
- r3″：observed 子項原文——
  > - LM-24 在 `basis=observed`、`sub_reason=after_close_pending` 時渲染，要等翻轉 PR 合併後才生效。合併前，data-engineer 的確認回報要經過風控單項確認，並由 qa 審查。

  改為見 §對實作的約束 CS-12（補 D-9 前提，對應 r3 提案第四節第 1 點）。

**A-88（與既有 ADR 的關係：ADR-0019）**
- r3″：刪除的原點——
  > - **ADR-0019**：與 D-4、D-5 的單一取得時間基準一致，不讀 `tail_fetched_at`。

  併入 r3′ 的 ADR-0019 點，該點原文——
  > - **ADR-0019**：D-9 讀列層的 `as_of` 與 `fetched_at`，R3 另外讀當日 bar 的 `PriceBar.as_of`。這些時間都只用來判斷「是否定案」，一律取較早者（CS-17）。它們不是序列的取得時間，不取代 `acquired_at`（ADR-0019 D-5），也不得顯示（K-13）。K-9 不受影響。

  改為見檔頭。「D-4、D-5」讀作 ADR-0019 的條號；「不讀 `tail_fetched_at`」保留，補依據 K-3。

**A-89、A-90（D-4 R2、R2′、R2″ 與表後第一句）**
- r3″：三列原文——
  > | R2 | `price_date > D` | `date_anomaly`，記 WARNING | price_date |
  > | **R2′（新增）** | 交易日、開盤前，而且 `price_date == D` | `date_anomaly`（開盤前不可能有當日 bar） | price_date |
  > | **R2″（新增；r3 改，A-47）** | D 不是交易日（任何 basis），而且 `price_date == D` | `date_anomaly`（官方日曆與資料衝突） | price_date |

  表後第一句原文——
  > （r3，A-47）R2″ 的狀態仍是 `date_anomaly`，`sub_reason` 依 basis 分成 `official_conflict` 與 `not_a_session`。

  改為見 §D-4。條件欄與 LM-70 對應不變。

**A-91（D-5 第二點 (a)）**
- r3″：原文——
  > - (a) D-9 已經實作合併，CST-5～CST-8 綠燈；

  改為見 §D-5（納入 CST-9）。

**A-92（外部參照自足化，比照 ADR-0027 A-85）**
- r3″：替換的片段原文——
  - D-5 第二點 (b)：「Phase 1 探測 §6.3 至少三輪的結果」「§6.4 唯讀複本診斷 A～D 的數字」「(i) §6.4 的試算必須用」「（§6.4 唯讀複本涵蓋的全部日期）」「(iii) §6.3 判讀矩陣 F-7 那一欄的結果」；
  - F-7：「§6.3 發現某個所用來源」；
  - D-9 標題：「（r3，附件 B'-3）」；
  - 待決事項 data-engineer：「（依 A-48）」。

  改為見各處。§6.x 指 `work/research/2026-10-16-Phase1資料源探測指令-CEO本機代跑.md` 的章節；F-7 補充欄實際是 §6.3.3a。

**A-93（待決事項 風控）**
- r3″：原文——
  > - 新增（r3，A-52）：r3 設計的單項確認（見第五節第 1 點）；R2″ 改寫、R2‴ 對應 LM-70 是否屬實。

  改為見 §待決事項 風控（已裁示：APPROVE WITH CONDITIONS）。

**A-94（待決事項 data-engineer 標號）**
- r3″：原文——
  >     - (f) 確認所有寫入 `price_bars_cache` 的轉接器，`PriceBar.as_of` 都不晚於第一個請求送出的時間；
  >     - (g) A-48 (b) (i)～(iii) 的回報內容。

  改為見 §待決事項 data-engineer。(f)(g) 原本接續提案第五節第 2 點的 (a)～(e)，ADR 內沒有對應，所以拿掉標號。

**A-95（檔頭、修訂紀錄）**
- r3″：檔頭新增「r3″ 更正」一行，本區塊為新增，無被取代原文。

---

> A-96″／A-97′（2026-10-17）依 tech-architect「ADR-0028 A-96″」套用（`work/reviews/2026-10-17-ADR-0028-A96雙撇-tech-architect.md`；風控 `work/reviews/2026-10-17-ADR-0028-A96A97單項確認-風控.md` K-1～K-16）。A-96″ 為不變＋收緊，A-97′ 為收緊，沒有放寬。CS-4 原句、CST-2 原文不變。A-96、A-96′ 的建議版沒有落過檔，不進本紀錄。風控 2026-10-17 A-96″ 回送確認（K-17～K-28）：leverage 納入；觸發條件採 (i)；CST-10 結構性質前提不構成放寬（餘集另有斷言）；G-1、G-3 併入本次，G-2、G-4 另案。方向仍為不變＋收緊。依 dev-lead 2026-10-17 查證增補 K-29～K-33：evidence 讀取順序、CST-11 fixture 約束、`/api/advice` 讀取方式擇一、已知限制三項、市場閘門另案。方向：收緊加照實揭露。K-31 (b) 是 K-16 的明定例外，不減少揭露。
> 套用順序與提案來源（後者取代前者的對應條目）：
> 1. TA：`work/reviews/2026-10-17-ADR-0028-A96雙撇-tech-architect.md` 第二節（第三節 ADR-0027 A-96″ 增補另開 commit，本次不套用）。
> 2. 風控回送確認：`work/reviews/2026-10-17-ADR-0028-A96雙撇回送項確認-風控.md` 第四節 T-1～T-16。
> 3. 風控增補：`work/reviews/2026-10-17-ADR-0028-A96雙撇回送確認增補-dev-lead查證-風控.md` 第四節：T-1 修正（K-17～K-28 改為 K-17～K-33）、T-13′ 取代 T-13、T-14′ 取代 T-14、T-17～T-25。
> 依據文件：風控原始條件 `work/reviews/2026-10-17-ADR-0028-A96A97單項確認-風控.md`（K-1～K-16）；dev-lead 查證 `work/reviews/2026-10-17-load_bars與evidence一致性查證-dev-lead.md`。
> 被取代的 T-13、T-14，以及 TA 條文中帶有待確認標記的句子，都是尚未落檔的提案文字，不是現行 ADR 原文，所以不另外保留；標記依 T-2 一律改成「（風控 2026-10-17 A-96″ 回送確認）」。

**A-96″（D-6 第 13 點）**：新增，無被取代原文；見 §D-6。

**A-96″（CS-4）**：原句不變，新增子項，無被取代原文；見 §對實作的約束 CS-4。

**A-96″（CS-26）／A-97′（CS-27）**：新增，無被取代原文。

**A-96″（CST-10～CST-12）**：新增，無被取代原文。

**A-96″（檔頭、待決事項、未查證事項）**：新增，無被取代原文。

---

> CS-17 修訂（2026-10-18）依風控 `work/reviews/2026-10-18-ADR-0027-C9-7與Q-3及CS-17提案確認-風控.md` 第二節第 3 項套用，逐字照寫，取代 CS-17 第 3 子點的末句，前兩子點不變。檔頭狀態維持 proposed。

**CS-17（第 3 子點末句）**
- 2026-10-18（風控 C9-7 與 Q-3 及 CS-17 提案確認，第二節第 3 項）：方向：不變。新增的呼叫位置只產生稽核值，不參與任何判定，由 AST 斷言保證；任何日子成為定案的條件不變。依 CS-21 通則，本條屬「方向判斷不了即視為放寬」的範圍，所以送風控單項確認（風控 2026-10-18）。被取代的原文「`final_after(` 只能在 `is_final` 內被呼叫（grep）。」逐字保留。

# tech-architect 回覆：F-11 PRD 開放問題 Q4、Q6 與模組邊界檢視（唯讀；由 coordinator 逐字轉存，2026-10-13）

## 一、本次結論

- **F11-A-1（Q4：確認，不需新 ADR，但附條件）**
  - F-11 沒有新增資料源、端點、策略，也沒有新的跨套件依賴邊，不修改任何 accepted ADR 的決策內容，屬於 ADR-0002 與 backtest-protocol 範圍內的報告層擴充。
  - 這個「不需 ADR」的結論只在 F11-A-14～F11-A-32 的約束全部成立時才成立。觸發失效條件任一條，就要回頭重審。
- **F11-A-2（Q4：Kelly 匯入不受影響，已讀碼確認）**
  - 匯入路徑完全不讀 `report`、`curves`。它從 `run.result` 與 `run.folds` 自己重新歸屬回合。
  - 因此新增的回應欄位不會改到 p、b、n。
  - 真正會牽動 Kelly 的是兩件事：
    - `BacktestRequest` 是否變動（它決定 `spec_hash` 與 bootstrap seed）。
    - `episodes.py` 既有函式與 dataclass 是否變動。
  - 兩者都列為硬約束（F11-A-14、F11-A-17）。
- **F11-A-3（Q6：否，F-11 第一版不含「同期指數報酬」欄）**
  - 有一條 cache-only 路徑在字面上能滿足三個前提：零網路、符合 ADR-0010 D-1、被 ADR-0024 C-1 的出口涵蓋。
  - 但它有三個問題，任一個都足以否決：
    1. 指數快取的涵蓋範圍取決於使用者是否逛過其他頁面，同一個請求可能得到不同結果。
    2. 涵蓋範圍多半只有最近約 540 天，多年期回測的大部分往返會缺值。
    3. 指數報酬與往返報酬的口徑不可比。
  - 要補齊涵蓋就得修訂 ADR-0010 D-4（排程預熱），這等於要 ADR，與 Q4 的前提矛盾。
  - L-15 建議整條移出第一版（見 F11-A-11）。
- **F11-A-4（回應形狀：與 PRD 建議不同）**
  - 建議**不要**把新欄位放進 `report`（也就是不擴充 `PerformanceMetrics`、`SegmentReport`、`WalkForwardReport`）。
  - 改在 `BacktestResponse` 新增一個與 `curves` 同層的兄弟欄位（暫名 `round_trip_detail`）。
  - 理由：`PerformanceMetrics` 另有兩個隱藏消費者，其中一個會落地進研究 DB（F11-A-8）。
- **F11-A-5（計算落點）**
  - 回合層計算一律在 `app/backtest/episodes.py`。
  - 組裝、日期對照與樣本旗標判定在 `app/backtest/report.py`。
  - 門檻常數放新檔 `app/backtest/display_params.py`。
  - 字面放新檔 `app/api/backtest_wording.py`。
  - 前端只渲染。明細見 F11-A-12。

## 二、各部門回報

### tech-architect

#### Q4：是否需要 ADR，以及 Kelly 讀取欄位盤點

- **F11-A-6 判定依據**

| 需要 ADR 的觸發點 | F-11 是否觸及 | 依據 |
|---|---|---|
| 新資料源、新的請求內 IO | 否（Q6 否決後） | 回測仍只有一次 `load_bars`（`app/api/backtest.py` L449-451） |
| 新端點，或改 `BacktestRequest` | 否（列為約束 F11-A-14） | |
| 新策略，或改 engine | 否 | ADR-0006 Consequences：改 engine 需新 ADR |
| 新的跨套件 import 邊 | 否 | `app.backtest` 內部新增檔案；`app.api` → `app.backtest` 是既有方向 |
| 改 accepted ADR 的決策 | 否 | ADR-0006 D-5 已把 `episodes.py` 定為回合定義的唯一來源，F-11 是在其中擴充 |

- **F11-A-7 Kelly 匯入讀取的欄位（事實，`app/api/kelly.py`）**
  - 從 `run.response` 只讀四項：`status`（L1447）、`as_of`（L1553）、`rates_verified`（L1554）、`dividend_adjustment["reason_code"]`（L1555）。
  - 其餘全部來自 `run.result` 與 `run.folds`：
    - `oos_window(run.folds)` 加上 `attribute_round_trips(...)`（L1456-1457）。
    - `_measured_columns`（L1271-1295）。
    - `episode_returns` 加上 `bootstrap_fraction_ci`（L1477-1482）。
  - **完全不讀 `response.report` 與 `response.curves`。**
  - `spec_hash` 是由 `body.model_dump(mode="json")` 序列化後取雜湊（L1251-1257），bootstrap seed 再取自 `spec_hash`（L1260-1268）。只要 `BacktestRequest` 多一個欄位（即使有預設值），同一份規格的 hash 與 seed 就會改變，f* 區間也跟著變，直接違反 FR-12、AC-14。
- **F11-A-8 讀碼發現的隱藏消費者（PRD 未列）**
  - `PerformanceMetrics` 也被 `app/research/sector_biased/study.py` 使用（L231-233、L263-273）。它經 `jsonable()` 整包寫進研究 DB（L439-445）。
  - `SegmentReport` 與 `build_segment_report` 也被 `app/backtest/basket.py` 使用（L59、L600、L747）。
  - 若把逐筆清單、最糟 N 筆、樣本旗標放進 `PerformanceMetrics`，會有兩個後果：
    - ADR-0012 的 hindsight 研究資料列會無聲多出未經風控審查的新欄位，與舊列 schema 不一致。
    - basket 回測也會開始帶逐筆清單。
  - 這是 PRD「放在 `report` 內」建議的主要風險，所以 F11-A-4 改為兄弟欄位。

#### 回應形狀：方案比較

| 方案 | 優點 | 缺點 | 風險 |
|---|---|---|---|
| P1：擴充 `PerformanceMetrics` | 前端表格的 row renderer 改動最小 | 研究 DB 與 basket 連帶改變（F11-A-8）；B&H 欄也會出現一堆 None 欄位 | 研究資料列 schema 漂移；未審欄位進入 ADR-0012 產物 |
| P2：`WalkForwardReport` 新增第三個 key | 符合 PRD「放 report 內」 | 會破壞既有釘住測試 `tests/test_api_backtest.py` L54「report 只有 in/out 兩鍵」（「不混合」的守門語意）；`api/backtest.py` docstring 寫明 `report` 就是 `walk_forward_report` 的原樣輸出，要一起改 | 低。可接受為備案 |
| **P3：`BacktestResponse` 新增兄弟欄位（採用）** | 有 `curves` 的先例（同一 run、同一 `_walk_forward_bounds`）；`report` 鍵集合與所有既有測試不動；研究與 basket 零影響 | 前端要從兩棵樹組出同一張表（`curves` 已經是這樣） | 兩次歸屬可能不一致：以「純函式且決定性」加上不變式測試封住（F11-A-20） |

#### Q6：同期指數報酬可得性

- **F11-A-9 現況事實（讀碼）**
  - 回測管線只載入單一標的（`load_bars`，走 live 梯子並 `cache_first`）。
  - 基準指數有現成路徑：`app/services/index.py` 的 `MARKET_BENCHMARK`（TW 為 `^TWII`、US 為 `^GSPC`，L302-305）、`IndexSeriesService.get_cached_bars`（L206-210，ADR-0010 D-1 的 cache-only 讀取）。
  - 這條路徑包在 `MarketDataService(scope="index")` 內（`app/api/deps.py` L162-170），所以 ADR-0024 C-1 的 `get_cached_bars` 出口也涵蓋它。
  - 指數快取**只會因為其他功能的 live 讀取而順帶寫入**：
    - `/api/signals`（預設回看 540 天，`app/signals/window.py` L22）
    - playbook（180 天，`app/playbook/service.py` L62）
    - 族群看板的 TAIEX 參考（`app/scheduler.py` L443-458，只有 TW）
    - 槓桿 ETF 頁
  - 排程預熱 `refresh_market_data` 只暖持倉標的、不暖指數（`app/scheduler.py` L281-301）。ADR-0010 D-4 也明寫該 job「仍只呼叫 `refresh_market_data`」。
- **F11-A-10 方案比較**

| 方案 | 優點 | 缺點 | 風險 |
|---|---|---|---|
| A：請求內 live 讀 `load_market_benchmark` | 涵蓋最完整 | 新增請求內網路呼叫，違反前提 | 直接否決 |
| B：請求內 cache-only 讀指數 | 零 HTTP；ADR-0024 閘門涵蓋；被拒收時回 `UNAVAILABLE` 即可視為缺漏 | (1) 有沒有值取決於使用者是否逛過訊號頁等頁面，同一請求結果不一定相同，回測從「現算現回」變成依賴隱藏狀態；(2) 涵蓋多半只到最近約 540 天，多年期回測大部分往返缺值；(3) 口徑不可比：策略 bars 預設已還原除權息，`^TWII` 與 `^GSPC` 是價格指數（ADR-0005 決策 5、L118 的 `price`）；往返報酬以進場前權益為分母、含部位比重，指數是 100% 曝險的價格漲跌；(4) 依 PX-6 須新增指數來源與新鮮度揭露區塊；指數路徑依 ADR-0024 D-4 不帶任何使用者面字面，T-16 未起草；`CACHE_ONLY_MISS_REASON` 的「此標的」放在回測頁會指錯對象 | 「最糟 N 筆」旁邊並列兩個不可比的數字，容易被讀成「跑輸大盤幾個百分點」 |
| C：排程預熱指數，再用 B 讀取 | 涵蓋較穩定 | 要修訂 ADR-0010 D-4；預熱窗 540 天仍不足以涵蓋長回測 | 需要 ADR，與 Q4 前提矛盾 |
| **D：第一版不含（採用）** | 零 IO、零新字面、不碰 ADR | 少了一個脈絡欄位 | 無。任務單原文就是「若可得」 |

- **F11-A-11 對 PRD 的連帶修正**
  - FR-2 與 AC-2 中的「（及可得時的同期指數報酬）」在第一版不成立，回測回應中不得出現任何指數欄位。
  - L-15 移出第一版。建議也不放「未載入基準指數」固定句，因為它會暗示有一個待補的功能。L-13 邊界說明句已經涵蓋「只含可由價格資料驗證的欄位」。最終是否需要這句，由風控裁示。
  - 日後若要做，前置條件：
    - (a) 另立 ADR，或修訂 ADR-0010 D-4，處理預熱與涵蓋窗。
    - (b) quant 定口徑：價格指數或含息、是否按曝險加權、日期對齊。
    - (c) 任一端日期缺值就給 null，不得取最近交易日代替。
    - (d) 風控審並列語意。
    - (e) 讀取不得放進 Kelly 會走到的計算段。

#### PRD「A. 計算口徑」「B2. 呈現」的模組邊界檢視

- **F11-A-12 建議落點**

| 項目 | 落點 | 說明 |
|---|---|---|
| 逐筆回合（進出 bar、損益、報酬） | `app/backtest/episodes.py`（既有 `Episode`） | 不新增欄位 |
| 持有 bar 數（D-4） | `episodes.py` 新純函式 | `exit_idx - entry_idx`；交易日或日曆日由 quant 定 |
| 平均獲利、平均虧損（D-6） | `episodes.py` 新純函式 | 用與 `stats_from_returns` 相同的切分（>0、<0）與 `fmean` |
| 最糟 N 筆（D-10） | `episodes.py` 新純函式 | 排序與同值規則（依進場 bar）只定義在這裡 |
| 最長連敗與起訖（D-11） | `episodes.py` 新純函式 | 平局規則由 quant 定後寫死在這裡 |
| 在場時間比例（D-12） | 建議 `episodes.py`，以持股是否超過 `POSITION_EPSILON` 判定 | 與回合用同一條「空手線」，才有可測的對帳不變式（F11-A-20 (e)）。若 quant 堅持用 `weights > 0`，改放 `report.py`，並說明兩種定義可能不一致的情境 |
| payoff ratio、profit factor | 不新增 | 前端直接讀既有的 `round_trip_payoff_ratio`、`profit_factor` |
| `N_MIN_DISPLAY`、`N_WORST` | 新檔 `app/backtest/display_params.py`（`Final`） | 不放 `app/kelly/`。`test_kelly_boundary.py` 既有的 `FORBIDDEN_PACKAGES` 已保證 `app.kelly` 碰不到這兩個常數 |
| 樣本不足旗標、空狀態代碼、B&H 在場比例 | `app/backtest/report.py` 新函式（暫名 `walk_forward_round_trip_detail(result, folds)`） | 共用 `_walk_forward_bounds`；bar index 轉日期也在這裡做 |
| 接上回應 | `app/api/backtest.py::execute_backtest` 與 `BacktestResponse` | 放在單一管線內（約束 32） |
| 新字面 | 新檔 `app/api/backtest_wording.py`，以 labels 模型隨回應下發 | 比照 `kelly_wording.py` 與 C8-3(a) |
| 前端型別 | `apps/stock-desk/frontend/app/lib/types.ts` | 手動同步（該檔 L295-305 的慣例） |
| 前端渲染 | 新元件（暫名 `apps/stock-desk/frontend/app/backtest/RoundTripDetail.tsx`），由 `BacktestReportView.tsx` 掛載；新增的表格列接在 `metricRows` 之後 | 只做格式化 |

- **F11-A-13 B2 呈現中被藏在前端的判斷，建議改由後端下發**
  - (a) FR-10 的三種空狀態（區段內無部位、有部位但回合全被排除、欄位不適用）：後端下發代碼（例如 `empty_state: "no_position" | "excluded_only" | null`），前端用代碼對應後端下發的字面。前端不得自行用 n、排除數、在場比例組合推論。
  - (b) Buy & Hold 欄的在場時間 100%：由後端欄位下發（B&H 路徑未定義時為 null），前端不得寫死 100%。回合層新列在 B&H 欄一律顯示「—」，這是固定版面規則，不是數值判斷，允許。
  - (c) 「—」與 0 的區辨（最長連敗、平均虧損等）：一律由後端以 null 或數值表達，前端只做 null 轉成「—」。
  - (d) 清單收合、順序斷言、375 寬捲動容器屬純 UI，留在前端，沒有邊界問題。
  - (e) 幣別：沿用既有 `marketCurrency(report.market)`（`BacktestReportView.tsx` L151），不另建第二套。
  - (f) 回應大小：每列 5 個欄位，數百筆約數十 KB，比既有逐 bar 的 `curves` 小一個量級。不需分頁，但禁止夾帶逐 fill 或逐 bar 的新清單（F11-A-21）。

### 對實作的約束（逐條可由 qa-reviewer 檢查）

- **F11-A-14** `BacktestRequest` 的欄位集合、型別、預設值不變。加測試釘住 `BacktestRequest.model_fields` 的鍵集合等於 F-11 前的清單。理由見 F11-A-7（`spec_hash`、seed）。
- **F11-A-15** `PerformanceMetrics`、`SegmentReport`、`WalkForwardReport`、`SegmentCurves`、`WalkForwardCurves` 的欄位集合與順序不變。`tests/test_api_backtest.py` L46-81、L164-188 不得修改，且維持綠燈。
- **F11-A-16** 新資料只出現在 `BacktestResponse` 的**一個**新欄位（暫名 `round_trip_detail`），內部依 `in_sample`、`out_of_sample` 分開。`report is None` 時它也必須是 None（以測試釘住，比照 `curves`）。任何「全期合併」的鍵都不得出現。
- **F11-A-17** `Episode`、`EpisodeExtraction`、`RoundTripStats`、`RoundTripAttribution` 的欄位不變。`extract_episodes`、`attribute_round_trips`、`oos_window`、`stats_from_returns`、`round_trip_stats`、`episode_returns`、`wilson_interval`、`bootstrap_fraction_ci` 的簽章與行為不變，`episodes.py` 只能新增純函式。既有守門測試 `test_the_module_contains_no_kelly_shaped_arithmetic` 維持綠燈。
- **F11-A-18** 平均獲利、平均虧損用與 `stats_from_returns` 相同的切分與 `statistics.fmean` 計算。測試對每個兩側都非空的區段斷言 `mean_win / -mean_loss == round_trip_payoff_ratio`，用 `==` 而非近似比較。
- **F11-A-19** 新程式碼一律以 bar index 歸屬與篩選，不得做日期字串比較（C5 約束 23、33）。日期只在 `report.py` 組裝時，以 `result.dates[idx]` 查表取得。
- **F11-A-20** 不變式測試，每項至少一個 fixture：
  - (a) 清單筆數等於 `num_round_trips`。
  - (b) 清單 `realized_pnl` 加總等於同區段歸屬物件的損益加總。
  - (c) 最糟 N 筆是清單的子集，排序與同值規則依 D-10，總數不足 N 時全列。
  - (d) 最長連敗不隨 fill 數改變（AC-4）。
  - (e) 若採持股判定在場時間：在場 bar 數至少等於區段內完整回合的持有 bar 數總和；n、跨界排除數、期末未平倉數三者皆為 0 時，在場 bar 數為 0。
  - (f) 兄弟欄位與 `report` 對同一區段的 n 相等（防兩次歸屬漂移）。
- **F11-A-21** 清單列的鍵集合恰為 `{entry_date, exit_date, holding_bars, return_on_entry_equity, realized_pnl}`（名稱可調，數量與語意不可調），以測試釘住。不得有價位、自由文字、fill 明細或指數欄位。
- **F11-A-22** `N_MIN_DISPLAY`、`N_WORST` 只在 `app/backtest/display_params.py` 各定義一次（grep 賦值次數為 1）。`app/kelly/**`、`app/advice/**`、`app/api/kelly.py` 都不得出現這兩個名稱、新回應欄位名或樣本旗標名（grep 測試）。`tests/test_kelly_boundary.py` 維持綠燈。
- **F11-A-23** 樣本不足旗標在 `report.py` 判定後下發。前端原始碼不得出現門檻常數，也不得拿回合數與任何數值比較（vitest 原始碼掃描）。
- **F11-A-24** 前端對新欄位只能做格式化（`formatPercent`、`formatNumber`、`formatMoneyNumber`、日期）與 null 轉「—」。不得排序、篩選、加總、平均、相除、計算連敗或比較門檻，也不得持有新的中文字面（`componentWordingScan` 涵蓋新元件）。
- **F11-A-25** `types.ts` 與後端模型在同一個 PR 內同步，欄位名逐字一致，註解標明來源檔。後端以測試釘住新模型的 JSON 鍵集合，使任何一側改名都會讓測試轉紅。
- **F11-A-26（golden）** 在功能 commit **之前**，先獨立 commit 一組 golden 回歸。內容是固定 fixture 下 F-11 前的輸出，F-11 後必須逐值相同：
  - (a) 全部 `STRATEGY_IDS` 的 `POST /api/backtest` 完整回應（排除 `as_of` 與新欄位）。
  - (b) `POST /api/kelly-inputs/{symbol}/import-backtest` 的 HTTP 狀態與回應、`kelly_inputs` 落地列、`kelly_import_attempts` 落地列（排除時間戳）。
  - (c) `POST /api/event-study` 的完整輸出。
- **F11-A-27** 單次回測請求的價格服務呼叫次數維持 1 次 `get_daily_bars`、0 次指數讀取，以計數假 resolver 測試釘住。`execute_backtest` 與回測路由不得新增 `IndexServiceResolver` 依賴。
- **F11-A-28** 新明細在 `execute_backtest` 內產生（單一管線，約束 32）。Kelly 匯入因此會順帶算出明細，但不得讀取（F11-A-22 的 grep 已涵蓋）。
- **F11-A-29** 以下檔案不得出現在 F-11 的 diff 中（`git diff --stat` 檢查）：
  - `app/backtest/engine.py`、`strategies.py`、`costs.py`、`splits.py`、`event_study*.py`、`basket.py`
  - `app/api/event_study.py`、`app/api/kelly.py`、`app/api/kelly_wording.py`
  - `app/kelly/**`、`app/research/**`
- **F11-A-30** 新字面集中在 `app/api/backtest_wording.py`，以 labels 模型隨回應下發。該檔不得 import 或續引 `KELLY_BOUNDARY_TRIP_EXCLUSION`（FR-8）。句中若含門檻數字，由後端以 `display_params` 常數格式化。占位字面要有守門測試，禁止出貨。
- **F11-A-31** 既有 `BacktestMetricLabels` 的兩個欄位與來源（`kelly_wording`）不變。新 labels 用新模型或新欄位承載，不得改寫既有兩鍵。
- **F11-A-32** 若 quant 對 D-12 改採 `weights > 0`，F11-A-20 (e) 改寫為「兩種定義的差異情境逐一列舉並各有測試」，由 qa-reviewer 確認後才能進 build。

## 三、驗證

- **實際讀過（全文或相關段落）**
  - PRD `work/stock-desk-F-11-回測報告補欄位-PRD.md` 全文
  - 任務單 `work/dispatch/2026-10-13-任務單-F-11-回測報告補逐筆往返與樣本標示.md`
  - 先前評估 `work/research/2026-10-13-外部交易提示詞-架構評估-tech-architect.md`
  - `work/stock-desk-C5-Kelly-架構評估.md`（約束 7-37）
  - ADR-0006 L17-245、ADR-0010 全文
  - 後端：
    - `app/api/backtest.py` 全文、`app/backtest/episodes.py` 全文、`app/backtest/report.py` 全文
    - `app/api/kelly.py` L1240-1309、L1430-1592
    - `app/services/index.py` 全文、`app/services/market.py` L60-195、`app/data/service.py` 全文
    - `app/api/deps.py` L120-170
    - `app/scheduler.py` L275-301、L420-458
    - `app/research/sector_biased/study.py` L225-284、L385-448
    - `app/backtest/sector_eval.py` L1180-1238
  - 前端：`BacktestReportView.tsx` L1-100
  - 測試：`tests/test_api_backtest.py` L40-189
- **只用 grep 查到相關條文（未讀全文）**
  - ADR-0002、ADR-0005、ADR-0018、ADR-0024（ADR-0024 只看了 grep 命中的 D-4、C-1、C-6、失效條件 13 相關行）
  - `engine.py` 欄位、`types.ts` 介面位置、`basket.py` 的引用點
  - `tests/test_backtest_episodes.py` L425-433、`tests/test_kelly_boundary.py` L39
- **沒有讀的**
  - `backtest-protocol` SKILL 本次未重讀
  - `scripts/c8_regression_comparison.py`
  - 前端測試檔
  - `basket.py` 的回應是否對外提供（F11-A-8 對 basket 的影響屬推論）
- **事實與推論分開**
  - F11-A-7、F11-A-9 是讀碼事實。
  - 「指數快取多半只涵蓋最近約 540 天、且取決於使用者瀏覽」是依程式中的回看常數與預熱範圍推得的推論，沒有讀 DB 驗證。依指示，未讀任何 `*.db`。
- **ADR 狀態**
  - ADR-0010、ADR-0018、ADR-0024 為 proposed，ADR-0002、ADR-0006 為 accepted。
  - Q6 的否決不依賴 proposed ADR 是否核可，因為「涵蓋範圍不確定」與「口徑不可比」是程式事實與資料性質。
- **紀律**：全程唯讀，沒有改任何檔案、沒有執行任何指令、沒有讀 `.env`、沒有指定任何套件版本。

## 四、下一步

1. product-manager 修 PRD：
   - FR-2、AC-2、L-15 依 F11-A-11 移除指數欄。
   - 「其餘」的回應形狀改採 F11-A-4（P3）。
   - FR-10 依 F11-A-13 (a) 改為後端下發空狀態代碼。
   - D-12 依 F11-A-12 補一句待 quant 擇定判定方式。
2. quant-researcher 的 Q2 增列一題：D-12 在場時間用持股判定還是 `weights > 0`（F11-A-32）。
3. risk-compliance-officer：確認 L-15 整條移除時不需要替代句（F11-A-11）。
4. dev-lead 依 F11-A-26 先送 golden 回歸 commit，再做功能。qa-reviewer 以 F11-A-14～F11-A-32 逐條勾稽。
5. ADR：本案不出新 ADR。若 CEO 日後要求同期指數報酬，由 tech-architect 另出 ADR-0010 D-4 修訂草案。

## 失效條件（任一成立即重審本回覆）

1. CEO 或 PM 要求加入同期指數報酬，或任何第二條價格序列：Q6 重審，需修訂 ADR-0010 D-4 或另立 ADR，Q4 結論同步失效。
2. 為了出場原因或其他欄位而修改 `engine.py` 或 `strategies.py`：依 ADR-0006 Consequences 需新 ADR。
3. `N_MIN_DISPLAY` 或樣本旗標被拿去拒收、改值、進入任何計算或閘門：屬 ADR-0006 管轄，需 ADR 與 CEO 裁決。
4. 改採 P1（擴充 `PerformanceMetrics`）：研究 DB 與 basket 受影響，回 tech-architect，並同步 ADR-0012 的負責人。
5. `BacktestRequest` 需新增欄位（例如讓使用者調 N）：`spec_hash` 的可重現性受影響，回 tech-architect。
6. Kelly 匯入改為讀取 `response.report` 或新欄位：違反 F11-A-22，重審。
7. 事件研究被要求併入樣本下限（Q12 若 CEO 改裁併入）：事件研究的回應形狀屬 ADR-0008，另行評估。

## 需 CEO 知悉事項

1. F-11 第一版不含「同期指數報酬」。任務單原文是「若可得」，不影響出貨。日後要做的話，需修訂 ADR-0010 的排程預熱，並經 quant 與風控處理口徑，屬另案排序。
2. F-11 不另立 ADR。架構約束以本回覆 F11-A-14～F11-A-32 為準，由 qa-reviewer 逐條檢查。

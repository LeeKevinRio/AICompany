# ADR-0006：Stock Desk Kelly 輸入的來源、鍵值與模組邊界

- 狀態：proposed
- 日期：2026-08-19
- 決策者：tech-architect（草案）、CEO（待核可）；風控文案另案審查

> **2026-08-19 修訂註記**：依 quant D-9 意見與 tech-architect 收斂裁決修訂
> （來源：`work/stock-desk-C5-Kelly-架構收斂裁決.md`）。本次為 ADR-0001 允許的
> 「核可前原地修訂」（狀態維持 `proposed`，尚未經 CEO 核可），非附錄補記；
> 修訂範圍為 Context 事實 5、Options 新增兩組方案列、D-2/D-3/D-5/D-6 全文改寫、
> D-9 改為已解除、Consequences 新增四點。狀態維持 proposed（待 CEO 核可）。

## Context（背景）

第 5 條上限「分數 Kelly 部位上限」自建立以來恆為 not_evaluable：
`PortfolioContext.win_rate` / `payoff_ratio` 兩欄存在（app/advice/limits.py:495-497），
但全系統無任何路徑賦值。C5 要為這兩個輸入建立來源。CEO 已裁決三項：
混合方案（回測帶入＋手動可覆寫並存）、時效沿用淨值 7/30 天、手動輸入設區間檢查
（p∈(0,1)、b>0，超出拒收不 clamp）。本 ADR 只決定**架構**，不決定文案，
亦不調整 kelly_fraction_cap（0.25）/ kelly_position_cap（0.10）這兩個已核准的硬上界。

實地盤點確立五個既有事實，構成本決策的限制條件：

1. 回測**完全無狀態**：`POST /api/backtest` 現算現回，不落地任何 run，
   沒有 backtest_id 可以指涉（app/api/backtest.py:319-424）。
2. `profit_factor` 是「毛利／毛損」，**不是** Kelly 的 b（平均獲利／平均虧損）。
   兩者關係為 PF = (p/(1-p))·b，僅在 p=0.5 時相等（app/backtest/report.py:121-137）。
3. 第 5 條上限目前被 `app/advice/book_limits.py` 歸類為**書本層**上限，
   這個歸類只在「Kelly 輸入永遠是 None」的前提下成立。
4. `SettingsStore.save()` 每次寫入所有 section，且該表的 updated_at 無法回答
   「使用者何時輸入這一項」（app/settings/store.py:52-57）。
5. `report.py` 的 `win_rate`/`profit_factor` 以 **fill** 為統計單位；每日再平衡
   使滿倉期間每日產生微額賣出，實測 10 次真實進出產生 72 筆 closing fill
   （中位 NT$0.02），fill 層與回合層 p 最大差 21pp、風控額度差 50%
   （quant D-9 §2.1）。此問題超出 C5 範圍，但決定了 C5 的 p/b 必須另立
   回合層欄位，不得取用既有 fill 層欄位。

## Options（選項比較）

| 方案 | 優點 | 缺點 | 風險 |
| --- | --- | --- | --- |
| 鍵 (symbol, market) 單一生效列 | 與 cap 5 的單一答案、與持倉分組鍵一致；生效者是資料事實 | 同標的多策略只能留一筆 | 使用者誤以為舊值還在（UI 標示來源策略化解） |
| 鍵 (symbol, strategy_id) 多列 | 可並存多策略 | manual 無 strategy；仍須額外 active 指標 | 選列規則寫錯即張冠李戴（PRD 風險 4） |
| 存進 AppSettings section | 沿用既有 API | 整包重寫、section 時間戳不可用、schema 漂移會整段落回預設 | 靜默清空所有 Kelly 輸入 |
| 新表 kelly_inputs + app/kelly/ | 每列獨立時間戳；不動既有契約 | 多一組路由與模組 | 無重大 |
| 帶入＝server 依規格重跑 | 來源與時間戳皆 server 產生、不可偽造 | 每次帶入多跑一次回測 | 資料配額（有 cache，影響小） |
| 帶入＝前端送數字 | 最省 | backtest 徽章變成前端自述 | 系統替未驗證數字背書 |
| 帶入＝回測結果落地後引用 id | 可有真 backtest_id | 範圍加倍、回測轉為有狀態 | 舊報告反覆帶入的新鮮度漏洞 |
| f*≤0 → 上限 0 + violated + 專屬句 | 與既有 >= 即 violated 慣例一致；擋加碼 | 候選頁也顯示 violated | 文案可能被讀成「叫我賣光」 |
| f*≤0 → not_evaluable | 畫面乾淨 | 把「有資料且結論為負」謊報為缺資料 | 違反模組首要慣例 |

### f\* 信賴區間計算位置（2026-08-19 修訂新增，四案，本案採 D）

| 方案 | 優點 | 缺點 | 風險 |
| --- | --- | --- | --- |
| A. `app/api/kelly.py` 直接組裝 bootstrap | 不新增模組；D-8 已允許 api 觸及兩邊 | 路由層變胖；數值邏輯要靠 HTTP 測試才測得到；本 repo 路由一律薄 | 迴圈日後被複製到第二處，f* 算式唯一性靠人自律 |
| B. `app/advice/kelly_estimate.py` 純函式 | 可直接 import `kelly_fraction`，唯一性最直觀 | p/b 估計量會出現第二份，否則得開 `advice → backtest` 邊 | 風控政策模組開始依賴回測模組；manual 路徑被綁進 pandas/numpy 堆疊 |
| C. `app/kelly/estimate.py` | 與儲存同模組，好找 | 仍受約束 13 限制、一樣要注入；讓「儲存模組」依賴回測引擎 | `app/kelly` 從 source-agnostic 變成 backtest-coupled |
| **D. `app/backtest/episodes.py` + 注入 `fraction_fn`（採用）** | 樣本定義、p/b、bootstrap 三者同源同檔；不新增任何跨域 import；純函式可單測；api 仍是唯一組裝點（符合 D-8） | 多一層注入的間接性 | 注入被人補上 default 實作就破功 → 以「keyword-only 必填、無 default」+ 守門測試封住 |

### `kelly_import_attempts` 是否新增（2026-08-19 修訂新增，兩案，本案採納）

| 方案 | 優點 | 缺點 | 風險 |
| --- | --- | --- | --- |
| 不記錄嘗試（僅 `kelly_inputs` 單列覆蓋，不新增 attempts 表） | 不多一張表、不多一組讀寫路徑 | 無法計算 `K_observed`/`K_distinct_specs`，無法滿足選擇偏誤揭露義務；422 被拒的嘗試無留痕 | D-9 揭露七要點之一（選擇偏誤揭露）落空，quant 認可的 MVP 緩解方案（attempts + K_observed + 區間落地）無法成立 |
| **新增 append-only `kelly_import_attempts`（採用）** | 與 D-2「生效輸入」管轄不同實體（嘗試事件 vs 生效值），不與「不保留歷史」規則衝突；repo 已有 append-only 先例（`app/alerts/store.py` 的 `alert_events`）；可回應選擇偏誤揭露義務 | 多一張表、多一組讀寫路徑 | 若讀寫路徑未隔離，恐被誤用於回答「目前生效值」→ 以獨立檔案 `app/kelly/attempts.py`（`KellyAttemptStore`）與 `kelly_inputs` 的 store class 隔離封住 |

## Decision（決策）

**D-1 鍵值**：Kelly 輸入以 `(symbol_upper, market)` 為主鍵，每鍵一筆生效值。
`strategy_id` 是來源欄位，不是鍵的一部分。手動輸入的 `strategy_id` 為 NULL。

**D-2 儲存（2026-08-19 修訂全文改寫）**：新增 SQLite 表 `kelly_inputs`
（同一 DB），新模組 `app/kelly/`（`models.py` + `store.py` + `sample_gate.py`
+ `attempts.py`）。`kelly_inputs` 比照淨值只存最新一筆、不保留歷史；但同列
同時保有生效值（win_rate/payoff_ratio）與帶入原始值（backtest_win_rate/
backtest_payoff_ratio），滿足追溯而不需歷史表。source ∈ {manual, backtest,
backtest_overridden}。

來源追溯欄位（僅 backtest 系有值，2026-08-19 修訂改寫）：strategy_id、
window_start、window_end、oos_start_date、oos_end_date、produced_at、
rates_verified、dividend_reason_code、adjust_dividends，以及回合層五計數
**oos_round_trips / oos_win_trips / oos_loss_trips / oos_excluded_boundary_trips
/ oos_open_trip_at_end**（取代原 `oos_closing_trades`；理由：該欄位受
Context 事實 5 所述微額 fill 污染，若落地會誤導稽核者）。

另新增區間與可重現性欄位：p_ci_low、p_ci_high、f_star、f_star_ci_low、
f_star_ci_high、bootstrap_seed、bootstrap_draws、
bootstrap_degenerate_no_loss_draws、bootstrap_degenerate_no_win_draws
（退化重抽計數依方向分列——n_loss==0 記 f\*=p̂（以 `fraction_fn(p̂, inf)` 由既有
算式自然產生）、n_win==0 對稱記 -inf 墊底；兩方向對區間的影響端不同，合併計數
會讓稽核者無從判讀。落地前必須斷言 f_star_ci_low / f_star_ci_high 皆為有限值，
非有限即 500 不寫入。quant-researcher 2026-08-19 確認，見
`work/stock-desk-C5-Kelly-架構收斂裁決.md` 附註）、
spec_hash、low_sample_warning、k_observed_at_write。**落地的 f_star 僅供稽核
與區間對照；上限計算一律以生效 p/b 重新呼叫 `kelly_fraction`，禁止讀取此
落地欄位。**

updated_at 一律 server 戳記。過期的列不自動刪除——刪了就無法區分
「從未輸入」與「已過期」。

**新增 append-only 表 `kelly_import_attempts`**，實作於獨立檔案
`app/kelly/attempts.py`（`KellyAttemptStore`，不得與 `kelly_inputs` 的 store
class 共用），同一 DB、同一連線紀律（比照 `app/alerts/store.py`）。每一次
`import-backtest`（**含 422 被拒者**）寫一列：

```sql
CREATE TABLE IF NOT EXISTS kelly_import_attempts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    symbol TEXT NOT NULL,              -- upper-normalized, same rule as kelly_inputs
    market TEXT NOT NULL,
    strategy_id TEXT NOT NULL,
    request_spec TEXT NOT NULL,        -- canonical JSON of the validated BacktestRequest
    spec_hash TEXT NOT NULL,           -- sha256 of request_spec; also the bootstrap seed source
    outcome TEXT NOT NULL,             -- 'ok' | 'rejected'  (gate verdict, NOT storage result)
    reason_code TEXT,                  -- NULL when ok
    win_rate REAL, payoff_ratio REAL, kelly_fraction REAL,
    oos_round_trips INTEGER, oos_win_trips INTEGER, oos_loss_trips INTEGER,
    oos_excluded_boundary_trips INTEGER, oos_open_trip_at_end INTEGER,
    oos_start_date TEXT, oos_end_date TEXT, oos_observations INTEGER,
    f_star_ci_low REAL, f_star_ci_high REAL,
    attempted_at TEXT NOT NULL         -- server UTC ISO
);
CREATE INDEX IF NOT EXISTS idx_kelly_attempts_symbol_time
ON kelly_import_attempts (symbol, market, attempted_at DESC);
```

要點：模組內不得出現 `UPDATE` 或 `DELETE` 語句（grep 可驗）；
`DELETE /api/kelly-inputs/{symbol}` 不得連帶刪 attempts——刪了就是把 K
往低報；`outcome` 定義為「閘門判定」而非「是否寫入成功」，attempts 可先寫、
輸入列後寫，不需跨 store 交易；attempts 寫入失敗則整個 import 失敗
（500），不得靜默放行；任何回答「目前生效輸入是什麼」的程式路徑禁止讀
attempts，唯一讀取用途是計數（K_observed / K_distinct_specs）與未來 P1 的
分佈顯示；request_spec 不含任何金鑰，可安全落地。`kelly_inputs`「只存
最新一筆」規則不變。

**D-3 帶入流程（2026-08-19 修訂全文改寫 422 條件）**：帶入必須是使用者主動
點擊（承接產業別回填紅線）。因回測無狀態，帶入實作為
`POST /api/kelly-inputs/{symbol}/import-backtest`，body 為一份回測請求規格，
server 當場重跑、取自己算出的 out_of_sample.strategy 的 p、b 與 provenance
後才寫入。422 且不寫入之情況：`status != ok`、OOS p/b 為 None、
body symbol/market 與路徑不符，以及三項樣本量閘門——**完整回合數
`n < MIN_OOS_ROUND_TRIPS`、獲利回合 `n_win < MIN_OOS_WIN_TRIPS(=5)`、
虧損回合 `n_loss < MIN_OOS_LOSS_TRIPS(=5)`**。三常數宣告於
`app/kelly/sample_gate.py`（比照 `app/settings/net_worth.py` 型態），每道
閘門各自 `reason_code`（`low_round_trips`/`low_win_trips`/`low_loss_trips`/
`pb_none`/`symbol_mismatch`/`insufficient_data`），422 訊息指名閘門並附
實際數字。**`MIN_OOS_ROUND_TRIPS` 之值待 CEO 裁決**（quant 建議 20，並列
50；20 ≤ n < 50 為軟性警示帶，仍寫入但強制 `low_sample_warning`）。
**422 是常態路徑而非錯誤**，UI 與文案照此設計。不做自動帶入、背景重算、
批次匯入。

**D-4 新鮮度錨點**：manual 以 updated_at 計齡；backtest 系以 **OOS 區段結束日
oos_end_date** 計齡，不以執行時間計齡（執行時間會讓重跑舊區間偽裝成新鮮）。
7/30 天沿用 CEO 裁決,常數與淨值的分開宣告（同值不同義）。
本項改寫 PRD FR-3 一條驗收條件（「40 天前產出的報告」在無狀態架構下不存在），
由 product-manager 更新、CEO 知會。

**D-5 計算位置與 f* 語意（2026-08-19 修訂全文改寫）**：
- f* 唯一定義維持 `app/advice/limits.py::kelly_fraction`，不得出現第二份
  算式；`app/backtest/episodes.py` 以注入方式取得此算式（見下一點），不構成
  第二份定義。
- b 不是 profit_factor。既有 fill 層 `win_rate`/`profit_factor`
  （Context 事實 5）**語意不動，但 C5 全面禁止取用**。`app/backtest/report.py`
  的 PerformanceMetrics 新增回合層欄位 **`round_trip_win_rate`** /
  **`round_trip_payoff_ratio`**（統計單位為完整持倉回合，非 closing fill；
  分子分母為回合報酬率＝回合已實現損益 ÷ 進場前一日 equity；成對命名，
  避免與 fill 層 `win_rate` 被讀者誤配成一組）。任何以 PF 充當 b、或以
  fill 層數字充當 p/b 的程式碼視為 BLOCKING。
- 新增 `app/backtest/episodes.py`，為全 repo 唯一一份回合抽取、OOS 歸屬
  計數、p/b 估計、Wilson 區間、joint bootstrap 區間定義。**f* 算式不進入
  此模組**，經 keyword-only、無 default 的 `fraction_fn` 注入取得；
  `app/api/kelly.py` 是唯一組裝點，傳入 `app.advice.limits.kelly_fraction`，
  點估計與 bootstrap 走同一 callable。`report.py` 的回合層顯示欄位亦由此
  模組供給，因此 p/b 估計量在 repo 中只有一份。
- **區間為揭露專用**：`p_ci_*`、`f_star_ci_*`、`low_sample_warning` 一律
  不得進入 `kelly_allowed_weight`、不得改寫生效 win_rate/payoff_ratio、
  不得作為任何 clamp 依據（與既有 clamp 禁令同級）。落地的 `f_star` 僅供
  稽核與區間對照，上限計算必須以生效 p/b 重新呼叫 `kelly_fraction`。
- f*≤0 時：第 5 條回 violated＋專屬句（期望值非正、可容許部位 0%、不提供加碼額度），
  不得沿用一般句型、不得出現操作字眼。
- f*≤0 時 notional_caps **不放入** kelly_fraction 項（0 額度作 binding cap 會推導出
  清倉股數）；改由 suggest_quantity_range 專屬句揭露。f*>0 時照常參與。

**D-6 風險層介面（2026-08-19 修訂全文改寫）**：新增 frozen model
`KellyInputs`（win_rate / payoff_ratio / source / age_days / anchored_at /
strategy_id / oos_start_date / oos_end_date / **oos_round_trips** /
**ci_includes_no_edge**），以單一欄位 `PortfolioContext.kelly: KellyInputs | None`
**取代**現有兩個裸欄位。**`oos_closing_trades` 移除**（受 Context 事實 5
所述微額 fill 污染，落地會誤導稽核者），改為 **`oos_round_trips`**；新增
**`ci_includes_no_edge`**（`f_star_ci_low <= 0` 的布林事實，由
`app/api/kelly.py` 算好傳入）。**CI 數值（p_ci_\*/f_star_ci_\*）、bootstrap
參數與其餘樣本結構欄位一律不進入 `PortfolioContext`**；`limits.py` 只得
分支、不得計算任何統計量（延續「不讀時鐘不碰 store」限制）。過期判定寫在
`_check_kelly_fraction` 之內（比照 `NET_WORTH_EXPIRED_DETAIL`）。年齡由
`book.py` 新增 builder 計算。

**D-7 第 5 條上限改列逐檔層**：book_limits.PER_SYMBOL_LIMIT_IDS 加入 kelly_fraction，
書本層彙總改走 _aggregate；build_book_level_context 的 kelly 恆為 None（守門測試）。
連帶更正 limits.py:495、book.py:44/:208/:478-483、book_limits.py:10-11/:69-77/:139-141
的「Kelly 無資料來源」敘述。

**D-8 API 邊界**：新 router app/api/kelly.py：GET /api/kelly-inputs、
GET|PUT|DELETE /api/kelly-inputs/{symbol}?market=、POST .../import-backtest。
不擴充 AppSettingsPatch。輸入驗證寫在 app/kelly/models.py（p gt0 lt1、b gt0,
超界 422 不 clamp）。

**D-9 方法論前置（2026-08-19 修訂：已解除）**：quant-researcher 已於
2026-08-19 出具意見（`work/stock-desk-C5-Kelly-D9-量化意見.md`）：
(a) 硬門檻採**完整回合數**，`n_win`/`n_loss` 各 ≥5，`n` 值待 CEO 裁決；
(b) b = 回合報酬率均值比，OOS 採**完全包含**歸屬、以 index 判定，跨界回合
與期末未平倉回合排除且分別計數；(c) 揭露七要點，MVP 緩解方案 = attempts
表 + K_observed + 區間落地。**回測帶入路徑待 `MIN_OOS_ROUND_TRIPS` 定值後
即可開工**；quant 其餘結論已納入 D-2/D-3/D-5/D-6。手動輸入路徑、儲存層、
設定頁 UI 原本即不受此前置阻擋，持續可並行。

## Consequences（後果）

- 第 5 條成為真正會攔下加碼的上限;由 not_evaluable 轉可評估只會增加約束,
  不可能放寬任何既有上限;偽造 p/b 經 0.25/0.10 兩道硬上界後最寬僅總資產 10%,
  gaming 在量上有界（唯一例外 f*≤0 區間,已由 D-5 排除規則處理）。
- 代價:帶入多跑一次回測;無 backtest_id,追溯靠欄位組重建;兩裸欄位移除須一次改完;
  第 5 條帳本頁顯示語意變更（逐檔比較取最差）,知會 PM 與風控;FR-3 一條 AC 改寫。
- 不改 kelly caps 的值與上界;與 ADR-0002~0005 無衝突。
- **（2026-08-19 修訂新增）** `kelly_import_attempts` 單調成長且永不刪除是
  刻意的——刪除會讓 K（選擇偏誤揭露所需計數）低報。
- **（2026-08-19 修訂新增）** 「樣本外」在本系統只代表區段位置、不代表已防
  過擬合（walk-forward 不做參數擬合），此事實成為強制顯示內容。
- **（2026-08-19 修訂新增）** 排除跨界回合會優先移除存續較長的回合（實測
  1.73 倍），此為已知限制，須照實寫進揭露文案，不得包裝成保守作法。
- **（2026-08-19 修訂新增）** `report.py` 既有 `win_rate`/`profit_factor`
  微額 fill 污染（Context 事實 5）另立任務處理：在 `report.py` 層修
  （改 `_trade_stats` 統計單位）屬 bug fix，不需 ADR，但須 PM 排期、
  risk-compliance-officer 重審顯示語意、附新舊數字回歸對照；若動到
  `engine.py`（no-trade band / 再平衡最小門檻）則需新 ADR。兩者皆不阻擋
  C5 開工，C5 只需遵守新增的「禁用既有欄位」約束（見
  `work/stock-desk-C5-Kelly-架構評估.md` 第 25 條）。

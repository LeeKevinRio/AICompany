# ADR-0006：Stock Desk Kelly 輸入的來源、鍵值與模組邊界

- 狀態：proposed
- 日期：2026-08-19
- 決策者：tech-architect（草案）、CEO（待核可）；風控文案另案審查

## Context（背景）

第 5 條上限「分數 Kelly 部位上限」自建立以來恆為 not_evaluable：
`PortfolioContext.win_rate` / `payoff_ratio` 兩欄存在（app/advice/limits.py:495-497），
但全系統無任何路徑賦值。C5 要為這兩個輸入建立來源。CEO 已裁決三項：
混合方案（回測帶入＋手動可覆寫並存）、時效沿用淨值 7/30 天、手動輸入設區間檢查
（p∈(0,1)、b>0，超出拒收不 clamp）。本 ADR 只決定**架構**，不決定文案，
亦不調整 kelly_fraction_cap（0.25）/ kelly_position_cap（0.10）這兩個已核准的硬上界。

實地盤點確立四個既有事實，構成本決策的限制條件：

1. 回測**完全無狀態**：`POST /api/backtest` 現算現回，不落地任何 run，
   沒有 backtest_id 可以指涉（app/api/backtest.py:319-424）。
2. `profit_factor` 是「毛利／毛損」，**不是** Kelly 的 b（平均獲利／平均虧損）。
   兩者關係為 PF = (p/(1-p))·b，僅在 p=0.5 時相等（app/backtest/report.py:121-137）。
3. 第 5 條上限目前被 `app/advice/book_limits.py` 歸類為**書本層**上限，
   這個歸類只在「Kelly 輸入永遠是 None」的前提下成立。
4. `SettingsStore.save()` 每次寫入所有 section，且該表的 updated_at 無法回答
   「使用者何時輸入這一項」（app/settings/store.py:52-57）。

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

## Decision（決策）

**D-1 鍵值**：Kelly 輸入以 `(symbol_upper, market)` 為主鍵，每鍵一筆生效值。
`strategy_id` 是來源欄位，不是鍵的一部分。手動輸入的 `strategy_id` 為 NULL。

**D-2 儲存**：新增 SQLite 表 `kelly_inputs`（同一 DB），新模組 `app/kelly/`
（models.py + store.py）。比照淨值只存最新一筆、不保留歷史；但同列同時保有
生效值（win_rate/payoff_ratio）與帶入原始值（backtest_win_rate/backtest_payoff_ratio），
滿足追溯而不需歷史表。source ∈ {manual, backtest, backtest_overridden}。
來源追溯欄位（僅 backtest 系有值）：strategy_id、window_start、window_end、
oos_start_date、oos_end_date、oos_closing_trades、produced_at、rates_verified、
dividend_reason_code、adjust_dividends。updated_at 一律 server 戳記。
過期的列不自動刪除——刪了就無法區分「從未輸入」與「已過期」。

**D-3 帶入流程**：帶入必須是使用者主動點擊（承接產業別回填紅線）。因回測無狀態，
帶入實作為 `POST /api/kelly-inputs/{symbol}/import-backtest`，body 為一份回測請求規格，
server 當場重跑、取自己算出的 out_of_sample.strategy 的 p、b 與 provenance 後才寫入。
insufficient_data、OOS p/b 為 None、symbol 不符、成交筆數低於門檻者一律 422 不寫入。
不做自動帶入、背景重算、批次匯入。

**D-4 新鮮度錨點**：manual 以 updated_at 計齡；backtest 系以 **OOS 區段結束日
oos_end_date** 計齡，不以執行時間計齡（執行時間會讓重跑舊區間偽裝成新鮮）。
7/30 天沿用 CEO 裁決,常數與淨值的分開宣告（同值不同義）。
本項改寫 PRD FR-3 一條驗收條件（「40 天前產出的報告」在無狀態架構下不存在），
由 product-manager 更新、CEO 知會。

**D-5 計算位置與 f* 語意**：
- f* 唯一定義維持 `app/advice/limits.py::kelly_fraction`，不得出現第二份算式。
- b 不是 profit_factor。`app/backtest/report.py` 的 PerformanceMetrics 新增
  `payoff_ratio` = mean(獲利)/mean(|虧損|)（無虧損筆或無成交筆時 None）。
  任何以 PF 充當 b 的程式碼視為 BLOCKING。
- f*≤0 時：第 5 條回 violated＋專屬句（期望值非正、可容許部位 0%、不提供加碼額度），
  不得沿用一般句型、不得出現操作字眼。
- f*≤0 時 notional_caps **不放入** kelly_fraction 項（0 額度作 binding cap 會推導出
  清倉股數）；改由 suggest_quantity_range 專屬句揭露。f*>0 時照常參與。

**D-6 風險層介面**：新增 frozen model `KellyInputs`（win_rate/payoff_ratio/source/
age_days/anchored_at/strategy_id/oos_start_date/oos_end_date/oos_closing_trades），
以單一欄位 `PortfolioContext.kelly: KellyInputs | None` **取代**現有兩個裸欄位。
過期判定寫在 _check_kelly_fraction 之內（比照 NET_WORTH_EXPIRED_DETAIL）。
limits.py 不讀時鐘不碰 store；年齡由 book.py 新增 builder 計算。

**D-7 第 5 條上限改列逐檔層**：book_limits.PER_SYMBOL_LIMIT_IDS 加入 kelly_fraction，
書本層彙總改走 _aggregate；build_book_level_context 的 kelly 恆為 None（守門測試）。
連帶更正 limits.py:495、book.py:44/:208/:478-483、book_limits.py:10-11/:69-77/:139-141
的「Kelly 無資料來源」敘述。

**D-8 API 邊界**：新 router app/api/kelly.py：GET /api/kelly-inputs、
GET|PUT|DELETE /api/kelly-inputs/{symbol}?market=、POST .../import-backtest。
不擴充 AppSettingsPatch。輸入驗證寫在 app/kelly/models.py（p gt0 lt1、b gt0,
超界 422 不 clamp）。

**D-9 方法論前置**：「回測帶入」路徑在 quant-researcher 出具意見前不得開工——
(a) OOS 成交筆數最低門檻;(b) b 定義與跨樣本持倉歸屬確認;(c) 選擇偏誤揭露義務。
手動輸入路徑、儲存層、設定頁 UI 不受此前置阻擋,可並行。

## Consequences（後果）

- 第 5 條成為真正會攔下加碼的上限;由 not_evaluable 轉可評估只會增加約束,
  不可能放寬任何既有上限;偽造 p/b 經 0.25/0.10 兩道硬上界後最寬僅總資產 10%,
  gaming 在量上有界（唯一例外 f*≤0 區間,已由 D-5 排除規則處理）。
- 代價:帶入多跑一次回測;無 backtest_id,追溯靠欄位組重建;兩裸欄位移除須一次改完;
  第 5 條帳本頁顯示語意變更（逐檔比較取最差）,知會 PM 與風控;FR-3 一條 AC 改寫。
- 不改 kelly caps 的值與上界;與 ADR-0002~0005 無衝突。

# C5 Kelly 架構評估:實作約束清單(tech-architect,2026-08-19)

> 決策本體見 docs/adr/0006(proposed,待 CEO 核可)。本檔為逐條可被 qa-reviewer
> 檢查的實作約束(協調人代 tech-architect 落檔,內容照其口述)。

**變更紀錄**
- 2026-08-19 tech-architect 收斂 D-9 後定版,約束 1-37(來源:
  `work/stock-desk-C5-Kelly-架構收斂裁決.md`)。

## 資料與儲存
1. kelly_inputs 主鍵 (symbol, market),symbol 大寫正規化(比照 _group_positions)。
2. strategy_id 不參與主鍵;manual 來源 strategy_id 必為 NULL(不得填假 id)。
3. updated_at 一律 server 戳記;輸入模型不得接受 updated_at(比照 NetWorthInput)。
4. source=backtest 時 backtest_* 原始值==生效值;使用者改動後 source→backtest_overridden
   且原始值不得被覆蓋。
5. 不新增歷史表/軟刪除;過期列保留。

## 輸入驗證
6. p gt=0 lt=1、b gt=0,超界 422(說明理由+聲明不自行改值);全程式禁 min/max/round clamp。
7. 【2026-08-19 改為新版】import-backtest 422 且不寫入之情況:status != ok、
   OOS p/b 為 None、body symbol/market 與路徑不符、**OOS 完整回合數
   n < MIN_OOS_ROUND_TRIPS、獲利回合 n_win < MIN_OOS_WIN_TRIPS(=5)、
   虧損回合 n_loss < MIN_OOS_LOSS_TRIPS(=5)**。三常數宣告於
   app/kelly/sample_gate.py(比照 net_worth.py 型態),MIN_OOS_ROUND_TRIPS
   之值為 CEO 裁決(quant 建議 20、並列 50)。每道閘門有各自 reason_code
   (low_round_trips/low_win_trips/low_loss_trips/pb_none/symbol_mismatch/
   insufficient_data),422 訊息指名閘門並附實際數字。

## 計算
8. 全 repo 僅一處 Kelly 算式:limits.py::kelly_fraction。
9. 【2026-08-19 改為新版】禁以 profit_factor 當 b(含變數命名混用);report.py
   的 PerformanceMetrics **新增** round_trip_win_rate 與 round_trip_payoff_ratio,
   統計單位為**完整持倉回合**(非 closing fill),分子分母為**回合報酬率**
   (回合已實現損益 ÷ 進場前一日 equity)。兩新欄位成對命名(禁止只叫
   payoff_ratio)。既有 win_rate/profit_factor 的值與語意不得更動。
10. f*≤0:第 5 條 violated、專屬常數 detail、notional_caps 不含 kelly_fraction 鍵。
11. 專屬句禁「建議/應該/賣出/清倉/減碼至/最佳倉位」。

## 模組邊界
12. limits.py 禁 import app/kelly、禁讀時鐘、禁碰 DB;年齡在 book.py builder 算。
13. app/kelly 禁 import app/advice(單向:advice ← api → kelly)。
14. PortfolioContext 以單一 kelly 欄位取代 win_rate/payoff_ratio 裸欄位;
    改完全 repo 無 ctx.win_rate 直接存取。
15. PER_SYMBOL_LIMIT_IDS 含 kelly_fraction;build_book_level_context 的 kelly 恆 None
    (守門測試)。
16. 敘述性註解同步更正:limits.py:495、book.py:44/:208/:478-483、
    book_limits.py:10-11/:69-77/:139-141。

## 不得更動
17. kelly caps 值與上界(0.25/0.10)、MAX_*_CEILING、_breaches 的 >= 語意、
    net_worth.py、strategies.py 參數、engine 的 violated 擋 add。
18. 既有風控核可文案不得順手改。

## 送審範圍(風控,B2 列管連動)
19. limits.py:798(not_evaluable 句)與 :806-808(「勝率 {}%」f-string——首次顯示
    真實數字,列管前提解除須重審)。※行號以 HEAD 1dcddc7 為準(原列管紀錄 :645,653 已漂移)。
20. 【2026-08-19 改為新版,原六類保留並追加五類送審句】
    - 原有:Kelly 過期句(與「從未輸入」不同句)、f*≤0 專屬句、quantity_range 零額度句、
      FR-5 回測揭露句(策略名/OOS 起訖/**完整回合數**/費率未查證/除權息狀態)、
      FR-6 手動揭露句、FR-4 徽章。
    - 追加(a) 區間顯示句,含「此區間涵蓋『沒有優勢』的可能」。
    - 追加(b) K_observed 選擇偏誤句(K=1 亦須顯示短版)。
    - 追加(c)「本系統 walk-forward 不做參數擬合,out_of_sample 僅代表區段位置」句。
    - 追加(d) 422 樣本不足說明句——**422 是常態路徑,其訊息屬面向使用者文案,
      一併送審**。
    - 追加(e)「歷史頻率不等於下一筆的機率」正面處理句。
    - **限制**:選擇偏誤句(追加 b)MVP 只能定性,不得引用 quant §3.1 具體數字,
      除非模擬表已固化為版控常數且產生腳本入版控(P2)。
21. 前端 LimitsCheckList/KellyInputsSection 不得自行判斷新鮮度或改寫後端句
    (比照 NetWorthSection 三約束)。

## 新增約束(22-37,2026-08-19 tech-architect 收斂 D-9 後定版,全文照抄
`work/stock-desk-C5-Kelly-架構收斂裁決.md` 最終增量清單)

22. (回合定義)以累計持股跨越 POSITION_EPSILON(具名常數,值 1e-9,絕對股數容差,
    須註明理由)判定進出場;回合已實現損益為 [entry_idx, exit_idx] 區間內所有
    fill 的 realized_pnl 之和。
23. (歸屬規則)OOS 回合須 entry_idx >= oos_start 且 exit_idx < oos_stop(完全包含)。
    跨界回合與期末未平倉回合排除且分別計數落地。**禁止以日期字串比較判定歸屬**;
    oos_start/oos_stop 一律取自 fold 幾何(folds[0].test_start/folds[-1].test_stop),
    不得由報表日期回推(report.build_segment_report 現行的日期字串篩選不得被新
    路徑沿用)。
24. (計量分母)回合報酬率分母固定為 equity_curve[entry_idx - 1](entry_idx == 0
    時取 initial_cash)。**禁止對原始 TWD 損益直接取平均**。
25. (禁用既有欄位)禁以 report.py 既有 win_rate、profit_factor(含任何換算)作為
    C5 的 p 或 b,變數命名亦禁混用;**禁以 num_closing_trades 作為任何門檻的
    計數**;**Kelly 揭露文案不得引用 fill 層的 win_rate/profit_factor 任一數字**。
    違反視為 BLOCKING。
26. (測試)七項缺一即視為未完成——(1) 歸屬純度;(2) 邊界敏感度(oos_start 前後
    各移 1 根,回合集合變化至多一筆);(3) look-ahead 位移偵測(價格整體前移 1 根,
    p 與 b 必須顯著改變);(4) 加總不變量(起訖皆空手區段的回合損益總和 == 該
    區段權益變化);(5) f* 注入守門(常數 fraction_fn 產生退化區間、spy 呼叫次數
    == draws + 1);(6) Trade.bar_index 不變量(每筆 trade 滿足
    dates[t.bar_index] == t.date);(7) attempts 完整性(422 亦落一列;DELETE
    輸入後 K_observed 不變)。
27. (區間落地)帶入必須同時落地 n / n_win / n_loss / 跨界排除數 / 期末未平倉數 /
    oos_observations / p 的 Wilson 95% CI / f* 的 joint bootstrap 95% CI /
    bootstrap_seed / bootstrap_draws / bootstrap_degenerate_no_loss_draws /
    bootstrap_degenerate_no_win_draws / spec_hash /
    low_sample_warning / k_observed_at_write。bootstrap 可重現:
    bootstrap_seed = int(spec_hash[:8], 16);對外宣告範圍限定「同一 spec 且同一
    批 bars」。**退化抽樣禁止靜默丟棄**(quant 2026-08-19 已確認定案):
    n_loss == 0 時記 f* = p̂——實作上以 `fraction_fn(p_hat, float("inf"))` 呼叫
    注入的 callable,由既有唯一算式的 IEEE 算術自然產生,episodes.py 不寫特殊
    分支算式;n_win == 0 時**不可**交 fraction_fn 自然處理(b̂ 不存在;b̂=0 會回
    None 造成下尾靜默截斷、反保守),對稱記 float("-inf") 墊底。兩方向計數分列
    (合併會讓稽核者無從判讀)。**落地前防禦性斷言**:f_star_ci_low /
    f_star_ci_high 皆須為有限值,非有限即 500 不寫入(閘門下屬
    should-not-happen,發生即代表閘門被繞過)。
28. (單一算式與計算位置,取代原暫置)新增 app/backtest/episodes.py,負責回合
    抽取、OOS 歸屬計數、p/b 估計、Wilson 區間、joint bootstrap 區間,為全 repo
    唯一一份 p/b 與回合定義。**f* 算式不得出現在此模組**,經 keyword-only、無
    default 的 fraction_fn 注入;app/api/kelly.py 傳入
    app.advice.limits.kelly_fraction;點估計與 bootstrap 走同一 callable。
    report.py 的回合層顯示欄位亦由此模組供給。
29. (嘗試紀錄)新增 append-only 表 kelly_import_attempts,實作於**獨立檔案**
    app/kelly/attempts.py(KellyAttemptStore,不得與 kelly_inputs 共用 class),
    同一 DB、同一連線紀律(比照 app/alerts/store.py)。每一次 import-backtest
    (**含 422 被拒者**)寫一列,欄位見 ADR-0006 修訂版 D-2 schema(改寫自
    收斂裁決檔裁決 2)。outcome 定義為閘門判定而非寫入結果。attempts 寫入失敗
    即整個 import 失敗(500),不得靜默放行。kelly_inputs「只存最新一筆」規則
    不變。
30. (選擇偏誤顯示)K_observed = COUNT(*) WHERE symbol=? AND market=?(含
    rejected、含所有策略、不設時間窗);同時落地 K_distinct_specs =
    COUNT(DISTINCT spec_hash)。以 K_observed 為主顯示並在揭露中寫明其定義與
    兩者偏誤方向;K_observed >= 2 必顯示完整選擇偏誤揭露句,K_observed == 1
    顯示短版。
31. (同源約束)p 與 b 必須來自同一次 run、同一 adjust_dividends 狀態、同一
    cost model;由構造保證——單一 request handler 內只存在一個 BacktestResult
    物件,且 request body **禁止**接受 p / b / f* 任一數字。
32. (單一回測管線)POST /api/kelly-inputs/{symbol}/import-backtest 必須重用
    app/api/backtest.py 的 BacktestRequest 與**同一個 run 編排函式**(將現行
    endpoint 內的編排抽為模組級函式,行為零變更、附回歸測試)。禁止在 kelly
    路徑另建第二套請求模型或第二條 run 管線。import 方向單向:
    api/kelly → api/backtest,反向禁止。
33. (trade 索引)app/backtest/engine.py 的 Trade 新增必填欄位 bar_index: int
    (無 default),由唯一建構點填入。C5 新路徑一律以 index 做歸屬,禁止任何
    日期字串比較。
34. (區間只用於揭露)p_ci_*、f_star_ci_*、low_sample_warning 一律不得進入
    kelly_allowed_weight、不得改寫生效 win_rate/payoff_ratio、不得作為 clamp
    依據(與第 6 條同級)。落地的 f_star 僅供稽核與區間對照;**上限計算必須以
    生效 p/b 重新呼叫 kelly_fraction,禁止讀取落地的 f_star**。
35. (attempts 讀寫隔離)任何回答「目前生效輸入是什麼」的路徑禁止讀
    kelly_import_attempts;唯一讀取用途為 K 計數與後續分佈顯示。
    app/kelly/attempts.py 內不得出現 UPDATE/DELETE 語句。
    DELETE /api/kelly-inputs/{symbol} 不得連帶刪除 attempts。生效值顯示一律
    讀 kelly_inputs 自身欄位,禁止由 attempts 反推。
36. (風險層介面收斂)KellyInputs(D-6)欄位為 win_rate / payoff_ratio / source /
    age_days / anchored_at / strategy_id / oos_start_date / oos_end_date /
    oos_round_trips / ci_includes_no_edge;oos_closing_trades 移除。CI 數值、
    bootstrap 參數與其餘樣本結構欄位不得進入 PortfolioContext;
    ci_includes_no_edge 由 app/api/kelly.py 算好傳入,limits.py 只得分支、
    不得計算任何統計量(延續第 12 條)。
37. (模組邊界擴充,延續第 13 條)app/backtest 禁止 import app/advice 與
    app/kelly;app/advice 禁止 import app/backtest;app/kelly 禁止 import
    app/advice 與 app/backtest(sample_gate 只吃純量,不得吃回測型別)。三者的
    組裝點只有 app/api/kelly.py。依賴方向:advice ← api → {kelly, backtest}。

## 升級 CEO/PM 事項
- **PRD 事實錯誤更正**:profit_factor≠b(PF=(p/(1-p))·b),PRD 相關文字須改;
- **FR-3 一條 AC 不可達**(回測無落地,無「舊報告」可看)——新鮮度錨點改採 OOS 區段
  結束日(D-4),PM 更新 AC、CEO 知會(7/30 天數不變)。
- **(2026-08-19 追加)** MIN_OOS_ROUND_TRIPS 取 20 或 50(風險胃納;quant 建議
  20+強制揭露)——**未定值前回測帶入路徑不得開工**,手動路徑與儲存層不受阻擋。
- **(2026-08-19 追加)** kelly_import_attempts 新表需 CEO 核可(已納入 ADR-0006
  修訂版)。
- **(2026-08-19 追加)** report.py 既有 win_rate/profit_factor 微額 fill 污染:
  另立任務、PM 排期、知會 risk-compliance-officer;report 層修=bug fix 不需
  ADR,engine 層修(no-trade band)=需新 ADR。
- **(2026-08-19 追加)** P3 保守帶入(90% 信賴下界+獨立 source 值)是否納入
  路線圖;若採納需 ADR-0006 新增 source 值。

## 待 quant 回覆(已結案)
- **(2026-08-19 新增,同日結案)** bootstrap 退化抽樣處理規則:quant-researcher
  已回覆確認——n_loss==0 採 f* = p̂ 極限(以 `fraction_fn(p̂, inf)` 自然產生)、
  n_win==0 對稱記 -inf、計數欄位依方向拆列、落地前有限值斷言。定案內容已併入
  第 27 條與 ADR-0006 修訂版 D-2,全文見
  `work/stock-desk-C5-Kelly-架構收斂裁決.md` 附註。無其他待回覆項。

## 開工順序
- 可立即並行:手動輸入路徑+儲存層+設定頁 UI。
- **(2026-08-19 更新)** 回測帶入路徑:quant-researcher 已回答三題(門檻/b
  定義與跨樣本歸屬/選擇偏誤揭露,詳見 ADR-0006 修訂版 D-9「已解除」),結論
  已納入第 7、22–37 條。**唯一剩餘阻擋**:MIN_OOS_ROUND_TRIPS 數值待 CEO
  裁決(quant 建議 20、並列 50),定值前回測帶入路徑不得開工;手動路徑與
  儲存層不受阻擋。

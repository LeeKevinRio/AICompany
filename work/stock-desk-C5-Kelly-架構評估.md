# C5 Kelly 架構評估:實作約束清單(tech-architect,2026-08-19)

> 決策本體見 docs/adr/0006(proposed,待 CEO 核可)。本檔為逐條可被 qa-reviewer
> 檢查的實作約束(協調人代 tech-architect 落檔,內容照其口述)。

## 資料與儲存
1. kelly_inputs 主鍵 (symbol, market),symbol 大寫正規化(比照 _group_positions)。
2. strategy_id 不參與主鍵;manual 來源 strategy_id 必為 NULL(不得填假 id)。
3. updated_at 一律 server 戳記;輸入模型不得接受 updated_at(比照 NetWorthInput)。
4. source=backtest 時 backtest_* 原始值==生效值;使用者改動後 source→backtest_overridden
   且原始值不得被覆蓋。
5. 不新增歷史表/軟刪除;過期列保留。

## 輸入驗證
6. p gt=0 lt=1、b gt=0,超界 422(說明理由+聲明不自行改值);全程式禁 min/max/round clamp。
7. import-backtest 422 且不寫入之情況:status!=ok、OOS win_rate/payoff_ratio 為 None、
   body symbol/market 與路徑不符、OOS 成交筆數低於 quant 門檻。

## 計算
8. 全 repo 僅一處 Kelly 算式:limits.py::kelly_fraction。
9. 禁以 profit_factor 當 b(含變數命名混用);report.py 新增 payoff_ratio=
   mean(wins)/mean(|losses|)。
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
20. 新句:Kelly 過期句(與「從未輸入」不同句)、f*≤0 專屬句、quantity_range 零額度句、
    FR-5 回測揭露句(策略名/OOS 起訖/成交筆數/費率未查證/除權息狀態)、FR-6 手動揭露句、
    FR-4 徽章。
21. 前端 LimitsCheckList/KellyInputsSection 不得自行判斷新鮮度或改寫後端句
    (比照 NetWorthSection 三約束)。

## 升級 CEO/PM 事項
- **PRD 事實錯誤更正**:profit_factor≠b(PF=(p/(1-p))·b),PRD 相關文字須改;
- **FR-3 一條 AC 不可達**(回測無落地,無「舊報告」可看)——新鮮度錨點改採 OOS 區段
  結束日(D-4),PM 更新 AC、CEO 知會(7/30 天數不變)。

## 開工順序
- 可立即並行:手動輸入路徑+儲存層+設定頁 UI。
- 阻擋中:回測帶入路徑,待 quant-researcher 回答三題(門檻/b 定義與跨樣本歸屬/選擇偏誤揭露)。

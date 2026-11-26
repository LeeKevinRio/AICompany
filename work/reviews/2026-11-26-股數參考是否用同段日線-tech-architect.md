# 「股數參考」是否用到同一段日線

- 審查者：tech-architect
- 日期：2026-11-26
- 轉存：coordinator，逐字轉存 subagent 最終回報

---

## 本次結論
有用到。「股數參考」的數字由後端算好再傳給前端。後端計算時用到兩樣東西，都出自同一個 `load_bars` 呼叫取回的 540 天原始日線：最新那根的收盤價，以及用整段日線算出的 ATR(14)。後端建議卡的「最新收盤」也出自這次呼叫。`/api/bars` 在預設參數下用同一個視窗、同一個 `load_bars` 取資料。所以 RC-763 與 RC-772 第 2 項的第二行應採 **A 版**。

## 各部門回報（tech-architect，唯讀查證）
1. **數字從哪來：取後端回傳值，前端只做格式化。**
   - `DecisionCard.tsx:387-391`：股數格顯示 `model.required.quantityRangeShares`。
   - `operationSummary.ts:283-287`：這個值只是把後端 `card.quantity_range.min_shares / max_shares` 套上千分位，再加「股」字。前端沒有自己計算。
2. **計算有沒有用到日線，是不是同一段：有，是同一段。**
   - 取日線：`api/advice.py:183-192` 呼叫 `load_bars`，視窗是 `DEFAULT_LOOKBACK_DAYS`，也就是 `signals/window.py:22` 的 540 天。
   - 收盤：`advice.py:203-207` 取最新一根 bar。`:220` 把它的 close 放進 `PortfolioContext`。
   - ATR：`advice.py:208` 用同一份 `loaded.bars` 跑 `compute_signals`。`:225` 用 `atr_from_signals` 取出 ATR 後放進 context。
   - 呼叫鏈：
     - `engine.py:408` 呼叫 `suggest_quantity_range(risk_budget, portfolio, …)`，算出的結果在 `:414` 填入 `quantity_range`。
     - `limits.py:1744` 用 `ctx.price_twd()`，也就是 close×fx（`:889-893`），把各條上限換算成股數。所以所有方向（加碼、減碼）的股數都用到收盤。
     - `limits.py:1646-1649` 計算 cap 4 的上限時用 `atr_max_shares`，`:1012-1017` 用到 `ctx.atr`。quant ε-2 說 cap 4 的 ATR 取自同一段日線，這點已證實。
   - 與 `/api/bars` 是否同源：`api/bars.py:87-96` 預設 `lookback_days = DEFAULT_LOOKBACK_DAYS`，同樣呼叫 `load_bars`。
3. **RC-763、RC-772 第 2 項第二行：採 A 版。** 依據有兩點：
   - 股數格不受「—」影響，照常顯示（`DecisionCard.tsx:387-391`）。
   - 它的輸入（收盤、ATR）出自同一段日線。

## 驗證
- 只用 Read / Grep 讀過上列檔案，行號都是實際讀到的。沒有跑測試，也沒有查執行期資料。
- 有三點限制，請照實轉達：
  - **「同一段」的精確意思**：`/api/bars` 與 `/api/advice` 是兩次各自呼叫 `load_bars`，視窗和取數邏輯相同，但不是記憶體裡同一份物件。兩次請求之間如果來源資料更新，取回的內容理論上可能不同。A 版寫「同一段／批日線」在語意上成立。如果風控要求精確到「同一次讀取」，就要改成「同一視窗」這類說法。
  - **持股市值另有來源**：持股的現值 `position_market_value_twd` 來自本機快取的持倉估值（`advice.py:193`、ADR-0010 D-1），不是這段日線。這不影響 A 版成立，因為收盤與 ATR 已經直接用到這段日線。
  - **前端參數未查證**：前端實際呼叫 `/api/bars` 時有沒有覆寫 `lookback_days`，我沒有查（`queries.ts` 裡搜不到對應字串，也沒有再往別處找）。

## 下一步
- 請 coordinator 轉告 risk-compliance-officer 與 creative-lead：RC-763、RC-772 第 2 項第二行定案用 A 版。
- 如果風控在意「同一次讀取」與「同一視窗」的差別，請 creative 依上面第一點限制微調後送風控。
- 前端 `/api/bars` 的實際 lookback 參數，交 frontend-engineer 補查。

相關路徑：
- /home/user/AICompany/apps/stock-desk/frontend/app/position/[symbol]/DecisionCard.tsx
- /home/user/AICompany/apps/stock-desk/frontend/app/lib/operationSummary.ts
- /home/user/AICompany/apps/stock-desk/backend/app/api/advice.py
- /home/user/AICompany/apps/stock-desk/backend/app/advice/engine.py
- /home/user/AICompany/apps/stock-desk/backend/app/advice/limits.py
- /home/user/AICompany/apps/stock-desk/backend/app/api/bars.py
- /home/user/AICompany/apps/stock-desk/backend/app/signals/window.py
- /home/user/AICompany/work/reviews/2026-11-26-前端調整字面逐字審RC760至RC772-風控.md

# report status 缺日加註定稿與補充八第二版確認（RC-229～RC-232）

- 審查者：risk-compliance-officer
- 日期：2026-11-19
- 轉存：coordinator，逐字轉存 subagent 最終回報

---

## 本次結論

**判定：APPROVE 附條件。** 我採 B，只改一處：「日後驗證重算」改為「日後驗證時重算」。我已逐條對過，補充八第二版沒有偏離 RC-217～RC-228。TA 收緊 `no_gaps_found` 的那一處我同意，沒有異議。另外有一處小漏洞，列為 RC-229。

1. **字面**：用 B，加一個「時」。
   - 原因：「驗證重算」可以讀成「日後會驗證（證實）」，帶一點保證的意味。改成「驗證時重算」之後，只描述「之後會重算一次」這個事實。
   - 不用 A：「驗證層」這個東西目前還不存在。
   - 不用 C：「缺交易日」會被讀成整體缺料。
2. **位置**：同意放在 `render_execution_status` 回傳內容的最後一行，也就是格點行之後、重審觸發之前。
   - 這一段也會進 harness 的 `result.output`（`tests/forecast_pipeline_harness.py:467`）。不過那是跑完就刪的完整明細，不在 CEO 的回貼白名單內，所以不影響 #150 與 RC-162。
3. **一律印出**：同意。`render_execution_status` 不論有沒有 claim，都會印出「F-2 計數」那一行（第 427 行），所以加註也一律印出，不因有沒有紀錄、有沒有缺日、有沒有 claim 而分支。
4. **其他輸出**：現階段只放這一處就夠。日後若有操作者文件說明 `report status` 的 F-2 或格點數值，要引用同一句字面，那份文件照樣送我審。方向性畫面依第 6 點 (c) 另行處理。

## 各部門回報（risk-compliance-officer）

- **[RC-229] required**：補充八第 5 點 (i) 寫「(c)～(h) 照樣適用」，可是 (c) 的 SQL 限定為讀 `price_bars_cache`，定期重做要讀的是 `forecast_input_series`。照字面兩者互相矛盾，結果等於定期重做沒有 SQL 範圍限制。
  - 請 TA 在 (i) 另寫一句範圍：只能讀 `forecast_input_series.bars_json` 解析出的 `session_date`，不得讀其他欄位或其他表，也不得輸出任何依列計算的計數。
  - 對應的 AST 測試與合成 DB 測試比照 (c)。
- **[RC-230] required**：關於加註這一行本身：
  - 字面要與下面的定稿逐字相同，包括全形標點。
  - 測試釘住四件事：
    - 這一行是 `render_execution_status` 的最後一個元素；
    - 零 claim、有缺口、無缺口三種情形下，這一行都出現，而且完全相同；
    - 其他各行不因這一行而改變；
    - `render_status` 中，它排在重審觸發各行之前。
  - 要增修，必須重送風控。
- **[RC-231] suggested**：補充八第 6 點 (b) 只涵蓋 F-2 與格點。請 quant 確認重審觸發的 n̂、c₁ 會不會因為缺 T 而失去格點，或因特徵跨過缺口而偏離。若會，這一行的適用範圍要擴及重審觸發，字面重送我。
- **[RC-232] required**：補充八檔頭與「性質」裡的「依風控 RC-217～RC-228 附條件核可」，改為「RC-217～RC-232」。

## 驗證

- 讀過的檔案：
  - creative-lead 草稿：`/home/user/AICompany/work/reviews/2026-11-19-report-status缺日加註字面草稿-creative-lead.md`
  - TA 第二版：`/home/user/AICompany/work/reviews/2026-11-19-補充八定稿第二版-併入風控RC217至RC228-tech-architect.md`（全文）
  - `/home/user/AICompany/apps/stock-desk/backend/app/forecast/report.py` 第 379～467 行
  - `/home/user/AICompany/apps/stock-desk/backend/tests/forecast_pipeline_harness.py` 第 462～468 行
- 以 grep 確認 `render_execution_status` 只有兩個呼叫者：`render_status` 與 harness。
- 本次唯讀，沒有執行程式，也沒有改任何檔案。
- 尚未核對：加這一行之後，是否會動到任何已釘住的 digest 或已登記雜湊。這屬於 TA 與 qa 的範圍，請 qa 在接線 PR 確認。

## 下一步

1. **dev-lead**：在接線 PR 依 RC-230 逐字放入這一行並加測試，PR 說明附上本判定的出處。
2. **tech-architect**：補 RC-229，並依 RC-232 更新檔頭。
3. **quant**：回覆 RC-231。

定稿全文：`加註：核心不偵測資料來源缺少的交易日；F-2 計數與格點數值可能與日後驗證時重算的結果不同，F-2 計數可能偏低。`

**整體判定：APPROVE 附條件（RC-229～RC-232），沒有 VETO。**

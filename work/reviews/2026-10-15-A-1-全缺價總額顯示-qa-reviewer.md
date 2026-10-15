# A-1 全缺價總額顯示「—」審查（27dc826）— qa-reviewer

> 轉存：coordinator，2026-10-15，子 agent 回報逐字轉存。Codex 第二意見未執行（環境不可用）。

---

## Summary
A-1 的改動範圍小、正確。`no_data` 時四格金額改為 null，由既有的 `formatMoney` 顯示「—」，`pnlColorClass` 顯示中性色。`partial`、`complete` 路徑沒變，沒有新字面，後端沒動。我沒找到 blocking 問題。Codex 在本環境不可用，所以本次是單家審查，需要 CEO 書面接受或另補跑。實際跑 vitest 與 tsc 不在我的工具範圍內，下文「自我揭露」有說明。

## 逐項結論
1. **只在 `no_data` 換「—」：成立。**
   - `SummaryCards.tsx` L67-71：`noData = totals.status === "no_data"`，四個值各自是 `noData ? null : totals.xxx`。
   - L80、L103、L105、L116、L118、L134、L136 都只是把傳入值換成這四個變數。
   - `partial` 與 `complete` 傳入的仍是原字串。`complete` 且真實為 0 時，會經 `formatMoney("0")` 顯示 NT$0，這是正確的。
   - 沒有新增 JSX 字面，「—」來自 `format.ts`。
   - `git diff --stat` 內只有 `SummaryCards.tsx` 與新測試，後端未動。
2. **`formatMoney(null)` 與 `pnlColorClass(null)`：讀碼確認如實作者所述。**
   - `format.ts` L159：`if (value === null) return "—"`。
   - `format.ts` L259：`if (value === null) return "text-neutral-400"`，也就是中性灰，不會是漲跌色。
3. **其他 `totals` 使用者：沒有同類缺口。**
   - Grep 全 `app/`（排除測試）：`PortfolioTotals` 的四個金額欄位只被 `SummaryCards.tsx` 讀取。
   - `types.ts` L260-263 型別仍是 `string`。把它改成可為 null 是 tech-architect 評估的選項，本 commit 在元件層處理，沒有改型別，影響面最小。
   - `page.tsx` L57 只把 `summary.data.totals` 傳給 `SummaryCards`。
   - `usePortfolioSummary` 只有 `page.tsx` 一處使用。
   - 持倉表 `PositionsTable.tsx` L468、L475 讀的是逐檔 `valuation.*_twd`，型別為 `string | null`，需求總綱也寫「逐檔正確」。
   - `RiskGauge.tsx` 沒有 `formatMoney`、`no_data` 或 `status ===`，不在 totals 路徑上。它走自己的風險 API（`types.ts` L648、L666 為 `number | null`），不屬於這個缺陷。
   - 總綱 NP-B4 提到「警示、風險上限、建議引擎可能消費該欄位」。前端沒有這類消費者，後端有沒有要由 tech-architect 確認，不影響本 commit。
   - `cost_twd` 沒有顯示在畫面上，所以沒有漏網。
4. **測試有牙：成立，有輕微弱點。**
   - 用 `renderToStaticMarkup` 渲染真實元件，再用正則取出四個金額格。
   - `no_data` 的兩個案例都覆蓋：全 0 payload，以及帶非零 payload。後者能證明是依 status 遮蔽，不是依值是否為 0。
   - 另外檢查沒有 `NT$0`、沒有裸 `0`、沒有漲跌色。
   - `partial` 與 `complete` 驗證金額原樣顯示且沒有「—」。
   - `complete` 且全 0 的案例驗證只有 `no_data` 會遮蔽。
   - 作者自述反向驗證有 2 則轉紅，我沒有重跑，但從測試結構看合理。
   - 輕微弱點：`complete` 且全 0 的斷言是 `cells[0]).toContain("0")`，偏鬆，改成 `toBe("NT$0")` 會更嚴。
   - 輕微弱點：金額格正則 `<p class="mt-1 [^"]*">` 綁定 className 結構，樣式一改就會抓到 0 格。但每個案例都有 `toHaveLength(4)` 或 `toEqual`，不會假綠。
   - 檔案放在 `lib/__tests__/` 卻測 component，與既有慣例是否一致我沒有逐一比對。屬風格問題，不阻擋。
5. **是否需要 qa-e2e：需要。**
   - 這是首頁可見金額的畫面變更，依 `ui-delivery-checklist` 與總綱 §4.1 的 A-1 欄位（`qa-reviewer＋qa-e2e`）。
   - 建議 e2e 以全缺價的資料，驗證首頁兩排四格都是「—」且為灰色，橫幅仍在，持倉表逐檔正常。
   - 另外要驗證 `partial` 與 `complete` 畫面沒有回歸。

## 各檔問題
### apps/stock-desk/frontend/app/components/SummaryCards.tsx
- 無 blocking。
- [可維護性][low] non-blocking：`PortfolioTotals` 型別仍宣告金額為 `string`，「no_data 時值無意義」這件事只靠元件層約定。未來若有新元件讀 `totals.*`，會再踩同一個坑。建議後續由 tech-architect 在 `Totals` 可為 null 的評估中一併處理，不需要在本 PR 做。

### apps/stock-desk/frontend/app/lib/__tests__/summaryCardsNoDataTotals.test.ts
- [可維護性][low] non-blocking：`complete` 全 0 案例的 `toContain("0")` 偏鬆，建議改為精確比對 `"NT$0"`。其餘見上文第 4 項。

## Codex 第二意見
未取得。`codex` 在本環境執行失敗（`codex: No such file or directory`，exit 127）。本次只有 Claude 單家審查，不是跨廠商審查。依先前慣例，建議 CEO 書面接受單家審查，或在有 Codex 的環境補跑。

## 唯讀權限判準常數
未觸及。這是 `27dc826~1..27dc826` 的 diff，只有前端元件與測試兩個檔，沒有 `scripts/validate_agents.py`，也沒有 `READONLY_AGENTS` 或 `READONLY_ALLOWED_BASH` 字樣。我是用 Read 讀 diff 輸出與 `--stat` 目測判斷，沒有跑那兩道 grep（Bash 不得 pipe）。內容是前端 UI 變更，與 agent 權限邊界無關，也沒有 shadow 定義的跡象。

## 自我揭露
- 沒有重跑 vitest 與 tsc，也沒有重跑反向驗證。作者自述的「80 檔 2251 passed、tsc 0 錯、2 則轉紅」未經我驗證。我的 Bash 只准 `git diff` 與 `codex`。
- 「其他 `totals` 使用者」是靠 Grep 與讀碼判斷，沒有逐一讀完 `PositionsTable.tsx` 全檔。
- 後端與警示、風險上限、建議引擎是否消費 `Totals` 並把 null 或 0 當真值，不在本 commit 範圍，我沒查。

## Verdict
PASS（附帶：Codex 缺席，需 CEO 書面接受單家審查；UI 變更仍須 qa-e2e 實機驗收）
BLOCKING_ISSUES=false

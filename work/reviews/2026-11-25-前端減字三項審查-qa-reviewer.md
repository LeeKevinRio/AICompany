# 前端減字三項審查

- 審查者：qa-reviewer
- 日期：2026-11-25
- 轉存：coordinator，逐字轉存 subagent 最終回報

---

## 本次結論

**PASS_WITH_NOTES，BLOCKING_ISSUES=false。**
- 這次是單家審查：Codex 依 CEO 決策 #58 不可用，沒有跨廠商第二意見，所以不是完整的雙家 review。
- RC-718 的 qa 核對項 7 項全部符合，沒有 critical 或 high。
- 實作者揭露的偏離（RC-717 第 1 項只檢查去註解後的程式碼）可以接受，建議風控在 risk-gate 確認。
- qa-e2e 要做。理由在下方第 3 點。
- 實作者回報的 typecheck、vitest、build 結果我沒有獨立重跑。

## 各部門回報

### 一、RC-718 qa 核對項逐項判定

1. **diff 只有四個檔加新測試檔，backend 零差異：符合。**
   - `git diff --stat` 共 5 個檔：`BacktestReportView.tsx`、`backtestFrontendBoundary.test.ts`、新增 `frontendTrimThreeLiterals.test.ts`、`PendingAlertsPanel.tsx`、`SettingsForm.tsx`。
   - 路徑全在 `apps/stock-desk/frontend/app/` 下，沒有 backend 路徑。
   - 沒有碰 `scripts/validate_agents.py`。

2. **三句字串和定稿完全一致：符合。**
   - 第一句：diff 新增行 `除 ATR 停損倍數外，每一項數字都是分數（例如 0.15 = 15%）。`
     - 「除」「ATR」後各一個半形空格，`0.15 = 15%` 兩個等號旁是半形空格，其餘標點是全形，與定稿一致。
     - 位置在 `SettingsForm.tsx` 約 463 行。
   - 第二句：原始碼是 `Buy &amp; Hold 為同期間、未計交易成本的被動持有基準。`，仍是 `&amp;`，與定稿一致。
   - 第三句：`費率未查證：本次回測使用的手續費／交易稅／滑價率尚未對照主要來源查證，報告數字應視為待查證狀態。`
     - 在同一個 JSX 行，沒有跨行。
     - 舊的跨行寫法（`verified_on 為` 換行 `null）`）已整段移除，所以不會有換行空白被吃掉或多出來的問題。
   - 新測試檔 `frontendTrimThreeLiterals.test.ts:20-22` 的三個常數與上述字面逐字相同。
     - 第一句用原始碼斷言，第三句用渲染後的警示元素斷言。
     - 第二句用渲染 HTML 斷言：`SENTENCE_2` 寫 `&amp;`，符合 React 輸出。

3. **`BASELINE_RUNS` 只少三項：符合。**
   - diff 只刪三行：`"文件說明"`、`"為"`、`"見後端"`，沒有新增。
   - 其中 `"為"` 只刪一次。
   - 指定的四段字面仍在：`為同期間`、`滑價率尚未對照主要來源查證`，以及 `未計交易成本的被動持有基準`、`報告數字應視為待查證狀態`。
   - 後兩段不在 diff 的刪除行，所以沒被動到。
   - 整個測試檔我沒有逐行讀，這點靠 diff 認定。

4. **2b 警示框的 `role`、class、位置、出現條件都沒變：符合。**
   - diff 的 context 行顯示 `{!report.rates_verified && (`、`<p role="alert"`、`className="mt-3 rounded-md border border-amber-800 bg-amber-950/40 px-4 py-2 text-sm text-amber-300"` 都沒有 +/- 標記。
   - 只改了內文字串，另外在上方加了一則 JSX 註解。
   - 位置沒有搬動。
   - `backtestAssumptionsDisclosure.test.ts:125` 的前綴 `費率未查證：本次回測使用的手續費／交易稅／滑價率` 仍然成立。
   - `backtestRoundTripRender.test.ts:779` 只比對 `費率未查證：`，也仍然成立。
   - 這兩個測試是否轉綠，我沒有獨立實跑，只能靠實作者全量回報，並以讀碼確認它們依賴的字面沒變。

5. **`ObservedValues` 只對 key 套 `signalFieldLabel`，沒有 `filter`：符合。**
   - diff 只把 `${key}` 換成 `${signalFieldLabel(key)}`，並加 import。
   - `.join("　")`、`: `、`value ?? "—"` 都不變。
   - 我用 Grep 查 `PendingAlertsPanel.tsx` 的 `filter(`、`.slice(`、`.sort(`，結果是 0 筆。
   - `format.ts:493-497` 的 `signalFieldLabel` 找不到標籤時，會回退到 `unevaluableAlertFieldLabel(value)`，再回退到原 key，所以未知鍵不會被丟掉，`bar_as_of` 和 `signals_as_of` 保留顯示。

6. **RC-717 四項 required 測試：符合。**
   - 第 1 項：`frontendTrimThreeLiterals.test.ts:29-38`
     - 原始碼含第一句且剛好 1 次，這個斷言對全文。
     - 不含 `app/advice/limits.py` 和「一一對應」，這兩個斷言對去註解後的程式碼，見下方偏離判定。
   - 第 2 項（2b）：`:41-50`
     - 先確認 `rates_verified` 是 false。
     - 用 regex 取出所有 `<p role="alert">`，篩出含「費率未查證」的，斷言剛好 1 個，再 `toBe(SENTENCE_3)`。
     - 這是針對元素、不是整頁斷言，符合風控要求。
   - 第 3 項（2a）：`:52-55`
     - 第二句出現 2 次（兩個樣本段各 1 次），且不含「見後端」。
   - 第 4 項（第 3 項主案）：`:57-93`
     - 價格事件 fixture 有四個鍵：`close`、`threshold`、`currency`、`bar_as_of`。
     - 斷言含「最新收盤價: 605」和「bar_as_of: 2026-11-24」，並斷言整行 `toBe` 且項目數是 4。
     - `signal_condition` fixture 斷言含 `signals_as_of`。
   - 改回舊字會變紅的實測，是實作者自述（6 個變紅，`signals_as_of` 那項只防案 C，預期不紅）。我沒有獨立重現。
   - 從讀碼看，第 1 到第 5 項斷言在舊字下確實會失敗。

7. **每個改動處都有英文註解並註明 RC 編號：符合。**
   - `SettingsForm.tsx`：`RC-712 / RC-718`
   - `BacktestReportView.tsx`：兩處，`RC-713 / RC-717 / RC-718` 和 `RC-714 / RC-717 / RC-718`
   - `PendingAlertsPanel.tsx`：`RC-716 / RC-718`
   - `backtestFrontendBoundary.test.ts`：`RC-717`
   - 新測試檔：檔頭有 `RC-712 ~ RC-718`
   - 註解皆為英文。
   - `SettingsForm.tsx` 的註解說「backend path removed」，與實際相符。

### 二、風控 risk-gate 項的順帶複查（供風控參考）

我用 Grep 查 `frontend/app` 整個目錄，找 `limits.py`、`見後端`、`verified_on`、`一一對應`，結果如下：
- 畫面字面（JSX 文字）已無 `見後端`、`一一對應`、`app/advice/limits.py`、`verified_on 為`。
- 剩下的 `limits.py` 都在註解或 `__tests__` 內，`SettingsForm.tsx` 在第 28、32、47、100、113 行。
- 剩下的 `verified_on` 都是程式識別字、型別欄位或註解。
  - `SettingsForm.tsx:152`、`:429`、`:435`、`:496-502` 是程式識別字。
  - `BacktestReportView.tsx:638` 是我們新加的註解。
- 其他 diff 變動只在註解與測試，沒有其他使用者看得到的字面變動。

### 三、偏離判定：可以接受

**判定：可以接受。**

理由：
- RC-718 risk-gate 原文寫的是「畫面字面」沒有 `app/advice/limits.py`，風控要防的是使用者看到的工程詞和不實對應。
- 第 28、32、47、100、113 行是開發者註解，不會渲染到畫面，也不在這批改動範圍。
- 若連註解都要清掉，會多動 5 個註解行，擴大 diff，反而偏離「只動這四個檔、只刪字」的合併條件。
- 第一句全文「剛好 1 次」仍對原始碼全文斷言，沒有放寬。
- 去註解的 regex 有保守性。
  - 它會誤砍 `// ` 後面的字，但只會讓斷言更寬鬆（少看到內容）。
  - 在 `SettingsForm.tsx` 現況下沒有誤判風險。
- RC-717 第 1 項字面寫「原始碼不含」，與實作者的做法有字面差異，所以要風控確認。

**建議風控在 risk-gate 確認兩點**：
1. 接受「畫面字面」的解讀，不要求清除註解。
2. 若要求連註解都不含，另開一案，由 frontend-engineer 處理那 5 個註解行。

### 四、Notes（不擋件）

- [可維護性][low] `frontendTrimThreeLiterals.test.ts:30-31` 的去註解 regex 是簡易版，不是 parser。
  - 目前沒問題；若日後 `SettingsForm.tsx` 在字串內出現 ` // `，可能誤刪。
  - 這一條只讓測試更寬鬆，不會誤報紅。
  - 建議在測試註解寫明限制，不改也可以。
- [可維護性][low] 新測試檔用 regex 取 `<p role="alert"...>` 的內文。
  - 若日後警示框改用別的標籤，測試會因為抓不到而失敗，不會悄悄通過，所以風險可接受。

### 五、唯讀權限判準常數

未觸及。
- 我只能跑兩條指定的 `git diff`，不能加管線，所以無法跑 `grep -x` 管線。
- 改由 `--stat` 檔案清單確認：沒有 `scripts/validate_agents.py`。
- 另外我讀完整份 diff，沒有任何 `READONLY_AGENTS` 或 `READONLY_ALLOWED_BASH` 的 +/- 行。
- 這份 diff 全是 `apps/stock-desk/frontend/app/` 下的檔案，沒有 `.claude/agents`，所以：
  - 異動 agent 名單為空。
  - 沒有常數值被改，也沒有 shadow 定義（既沒新增 `.py`，也沒有 `.claude/agents` 異動）。
  - 沒有對應的 ADR 需求。

## 驗證

- **未獨立重跑**：typecheck、全量 vitest（118 檔、3116 測試）、build 的結果全部來自實作者回報，我沒有重跑。
  - 原因是我的 Bash 權限只有兩條 `git diff`，無法執行。
  - 這三項請以 CI 為準，合併前由 coordinator 或 CI 確認。
- 我實際做的是讀碼和 Grep：
  - diff 全文逐行；
  - worktree 內 `frontend/app` 的殘留字面 Grep；
  - `PendingAlertsPanel.tsx` 的過濾寫法 Grep；
  - `signalFieldLabel` 實作；
  - 兩個既有測試（`backtestAssumptionsDisclosure.test.ts`、`backtestRoundTripRender.test.ts`）的字面依賴。
- 「改回舊字會變紅」是實作者自述，我只以讀碼推論，沒有實測。
- 沒有讀 `.env*`，沒有碰 `backend/data/`，沒有寫入 worktree，沒有看其他 `.claude/worktrees/` 目錄。
- 單家審查：Codex 不可用（CEO 決策 #58），沒有第二意見。

### 是否要做 qa-e2e：要做

**理由**：
- CLAUDE.md §2 寫「涉及 UI 再加 qa-e2e 實機驗收」，風控也寫明「不代為豁免」。
- 這批改動的是三個使用者看得到的畫面字面，屬於 UI 改動，即使只是文字。
- SSR 的 `renderToStaticMarkup` 單測沒有涵蓋的部分：真實瀏覽器的版面換行、警示框視覺與位置、設定頁實際顯示。
- 第 3 項要看到真實的警示事件卡，確認 `bar_as_of`、`signals_as_of` 在畫面上仍可見，鍵名是中文標籤。

**建議 e2e 範圍（從小）**：
1. 設定頁「風險預算」說明句，確認「ATR 停損倍數」被排除的新句顯示正確。
2. 跑一次費率未查證的回測，確認 `role="alert"` 的 amber 框、位置（免責框之後、notes 之前）和新句。
3. 回測報告兩個樣本段的 Buy & Hold 句，確認 `&` 顯示正常。
4. 有警示事件時，確認事件列「最新收盤價: …　threshold: …　currency: …　bar_as_of: …」顯示。

## 下一步

1. qa-e2e：照上面四點做實機驗收。
2. risk-compliance-officer：risk-gate 時確認偏離判定（註解不算畫面字面），並逐字比對三句。
3. coordinator：
   - 合併時確認 #156 期間尚未開始，並走修訂八流程（獨立工作樹、`--no-ff`、全套 CI 對等、fast-forward push）。
   - 以 CI 結果確認 typecheck、vitest、build 綠燈，因為我沒有獨立重跑。
4. 若風控堅持連註解都不含 `limits.py`，退回 frontend-engineer 另案處理，不阻擋這批。

### 我跑過的指令

只有這兩條，逐字照打：
1. `git diff --stat fa9dd420 3ea244bd991c30ba085546219603d5210cb19ef5`
2. `git diff fa9dd420 3ea244bd991c30ba085546219603d5210cb19ef5`

### 讀過的檔案

- `/home/user/AICompany/work/reviews/2026-11-25-前端減字三項逐字審RC712至RC718-風控.md`（全文）
- `/home/user/AICompany/work/reviews/2026-11-25-前端減字三項實作交件-frontend-engineer.md`（全文）
- `/home/user/AICompany/.claude/skills/code-review-checklist/SKILL.md`
- `/home/user/AICompany/.claude/skills/ui-delivery-checklist/SKILL.md`
- Grep 範圍（皆在 `/home/user/AICompany/.claude/worktrees/agent-a3b8c88b329ce0ede/apps/stock-desk/frontend/app/` 下）：
  - 整個 `frontend/app` 目錄（`limits.py`、`見後端`、`verified_on`、`一一對應`）
  - `backtest/__tests__/` 中的 `backtestAssumptionsDisclosure.test.ts` 與 `backtestRoundTripRender.test.ts`
  - `components/PendingAlertsPanel.tsx`（`filter(`、`.slice(`、`.sort(`）
  - `lib/format.ts`（`signalFieldLabel`）

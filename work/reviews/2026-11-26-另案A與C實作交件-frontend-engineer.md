# 另案 A 與 C 實作交件

- 審查者：frontend-engineer
- 日期：2026-11-26
- 轉存：coordinator，逐字轉存 subagent 最終回報

---

## 本次結論
另案 A、另案 C 已完成，分成兩個 commit（A 在前、C 在後）。typecheck、全量 vitest、build 都過。沒有 push、merge、rebase、amend。沒有動作被拒絕，但有兩次 Bash 因為「指令太複雜、無法確認留在 worktree 內」被擋，我改用 Edit/Write 和 scratchpad 腳本完成，沒有繞過任何權限。

- base SHA：`bd840afd5e026efcd70a24ee4160699216888f27`（分支 `fix/settings-example-and-alert-labels`）
- commit 1（A）：`587767d8296757e605fdaaa89b55c0b3d15f5420`
- commit 2（C）：`d1f1c5b4db8a41a341db267cb218d0ecc9c0137f`

## 各部門回報（frontend-engineer）

**git diff --stat**
- commit 1（A）：2 個檔案，+36 / -4
  - `apps/stock-desk/frontend/app/settings/SettingsForm.tsx`：+11 / -4（合計）
  - `apps/stock-desk/frontend/app/backtest/__tests__/frontendTrimThreeLiterals.test.ts`：+29（合計）
- commit 2（C）：4 個檔案，+248 / -10
  - `apps/stock-desk/frontend/app/backtest/__tests__/frontendTrimThreeLiterals.test.ts`：12 行變動
  - `apps/stock-desk/frontend/app/components/PendingAlertsPanel.tsx`：14 行變動
  - `apps/stock-desk/frontend/app/lib/__tests__/alertObservedLabels.test.ts`：新增 161 行
  - `apps/stock-desk/frontend/app/lib/alertObservedLabels.ts`：新增 71 行
- 零差異：以 `git diff --stat bd840afd HEAD` 對 `backend/`、`format.ts`、`alertFields.ts`、`DataStatusBadge.tsx`、`AlertStatusStrip.tsx` 查，輸出為空。

**定稿字面在原始碼中的實際內容**
- `SettingsForm.tsx` 說明句（`:463` 附近）：`除 ATR 停損倍數外，每一項數字都是分數（例如 0.01 = 1%）。`
- `SettingsForm.tsx` 的 `description`（`:98` 附近）：`此標的市值占總資產(已估值部位市值,不含現金)的上限（比例，例如 0.01 代表 1%）。`
- `alertObservedLabels.ts` 的 `OBSERVED_KEY_LABELS` 是 `Map`，共 11 筆：
  - `close` = 資料日收盤價
  - `threshold` = 設定的門檻
  - `currency` = 幣別
  - `bar_as_of` = `signals_as_of` = 資料日期（日線收盤，非即時）。兩鍵共用常數 `AS_OF_LABEL`
  - `field` = 判斷欄位
  - `value` = 該欄位數值
  - `op` = 比較方式
  - `compared_to` = 比較對象數值
  - `violated_limit_ids` = 觸發的上限
  - `violated_count` = 觸發的上限數量
- 值轉換只做三個鍵：
  - `op` 查 `COMPARISON_OP_OPTIONS`。
  - `field` 走 `signalFieldLabel`，它本身會退回原字串。
  - `violated_limit_ids` 用「、」切開，逐個查 `LIMIT_SELECTOR_OPTIONS`，再用「、」接回。
  - 未知的鍵或值退回原字串；null 顯示「—」。
- `PendingAlertsPanel.tsx` 現在是 `entries.map(([key, value]) => observedEntryText(key, value)).join("　")`。「: 」、「　」、「—」都沒變，沒有 `filter`、`sort`、`slice`。
- 每個改動處都有英文註解，標註 RC-730～RC-739。模組檔頭有 RC-733 要求的失效條件註解，指向 `backend/app/alerts/notify.py` 的 `ALERT_DISCLAIMER_LINE`，並寫明兩個日期鍵日後不同源時也要重審。

## 驗證
- `npm ci`：成功，但有 npm audit 的漏洞提示，我沒有處理。
- `npm run typecheck`（`tsc --noEmit`）：無錯誤輸出。
- 全量 vitest：119 個檔案、3148 個測試全過（commit 2 之後）。
  - A 的測試檔單獨跑是 10 個測試全過。
  - 新增測試：A 4 個（RC-738 A1～A4）。C 的 `alertObservedLabels.test.ts` 對應 RC-738 C1～C8，用 `it.each` 加 8 個運算代碼，另有原型名稱（`constructor`、`toString`）案例。
  - 更新舊測試：RC-717 第 1 項改成新字串，三個舊斷言保留。RC-717 第 4 項改成新字面，項目數 4 與日期值出現這兩個斷言保留。
- `npm run build`：成功（Next 16.3.3，路由列表正常產出）。
- 「改回舊字會變紅」實測，每次還原後確認檔案回到正確內容：

| 項目 | 結果 |
|---|---|
| A：`:463` 改回「0.15 = 15%」 | 3 個測試紅 |
| A：`:98` 改回「0.15 代表 15%」 | 2 個測試紅 |
| C：`close` 標籤改回「最新收盤價」 | 4 個紅 |
| C：日期標籤改回舊括號（日線，非即時） | 5 個紅 |
| C：`field` 標籤改成 `field` | 3 個紅 |
| C：`violated_count` 標籤改成 `violated_count` | 2 個紅 |
| C：`op` 值不轉換 | 10 個紅 |
| C：`violated_limit_ids` 值不轉換 | 3 個紅 |
| C：加 `.slice(0)` | 1 個紅 |

## 偏離與沒有查證的事項
1. A 測試的 RC-738 A3（兩句都含 0.01 與 1%）是用測試檔內的常數斷言。真正鎖原始碼的是 A1 和 A2，也就是「各出現 1 次」和「舊字面消失」。A3 本身偏弱，只是照 RC-738 列項加上。
2. `LIMIT_SELECTOR_OPTIONS` 含 `any`（任一上限）。若後端 `violated_limit_ids` 出現 `any`，會顯示「任一上限」而不是原字串。後端實際只會出現 5 個具體 id，我認為無影響，但屬於實作細節，供風控核對。
3. 為避免型別強制斷言，值查表改用 `COMPARISON_OP_OPTIONS.find` 與 `LIMIT_SELECTOR_OPTIONS.find`，沒有直接呼叫 `comparisonOpLabel` 與 `limitSelectorLabel`。`format.ts` 零改動，結果與定稿一致。
4. 全量 vitest 在 commit 1 時沒有單獨跑，只跑了 A 的測試檔。全量是在 commit 2 之後跑的。
5. 沒有做 375 與 1280 實機畫面驗收，也沒有查證首頁免責文字。這屬於 qa-e2e 與 risk-gate 的範圍，我只做了原始碼層驗證。
6. 沒有讀 `.env*`，沒有碰 `backend/data/`，沒有執行 `.bat`，沒有碰其他 worktree。
7. 工作樹乾淨。`/tmp/claude-0/` 下有幾個備份暫存檔（`SF.bak`、`L.bak`、`P.bak`、`npmci.log`），在 repo 之外，未被追蹤。

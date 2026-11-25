# 前端減字三項實作交件

- 審查者：frontend-engineer
- 日期：2026-11-25
- 轉存：coordinator，逐字轉存 subagent 最終回報

---

## 本次結論
前端減字三項已完成並 commit，只 commit、沒有 push、merge、rebase 或 amend。
- 分支：`fix/frontend-trim-three`
- base SHA：`fa9dd420`
- head SHA：`3ea244bd991c30ba085546219603d5210cb19ef5`
- typecheck、全量 vitest、build 皆通過（CI 的 frontend job 沒有 lint 步驟，所以沒跑）。

## 各部門回報
**diff 範圍**：`git diff --stat fa9dd420 HEAD` 共 5 個檔、112 行新增、9 行刪除，沒有別的檔。路徑都在 `apps/stock-desk/frontend/app/` 下：
- `backtest/BacktestReportView.tsx`（9 行）
- `backtest/__tests__/backtestFrontendBoundary.test.ts`（4 行）
- `backtest/__tests__/frontendTrimThreeLiterals.test.ts`（新增 97 行）
- `components/PendingAlertsPanel.tsx`（7 行）
- `settings/SettingsForm.tsx`（4 行）

backend 零差異。

**三句在原始碼中的實際字面**
1. `SettingsForm.tsx:463`：`除 ATR 停損倍數外，每一項數字都是分數（例如 0.15 = 15%）。`
2. `BacktestReportView.tsx:340`：`Buy &amp; Hold 為同期間、未計交易成本的被動持有基準。`（原始碼寫 `&amp;`，渲染後是 `&`，與原本寫法一致。）
3. `BacktestReportView.tsx:642`：`費率未查證：本次回測使用的手續費／交易稅／滑價率尚未對照主要來源查證，報告數字應視為待查證狀態。`
   - 我把整句寫在同一個 JSX 行，沒有跨行，所以中間不會多出或少掉空格。
   - `role="alert"`、class、位置、出現條件都沒動。

**第 3 項**：`PendingAlertsPanel.tsx` 只把 `${key}` 換成 `${signalFieldLabel(key)}`，並加了 import。分隔符、冒號、「—」、項目數量和順序都沒變，沒有 `filter`。

**BASELINE_RUNS**：只移除「文件說明」、「為」（一次）、「見後端」。其餘項目都在，也沒有新增。

**註解**：五個改動處都有英文註解，註明 RC-712～RC-718。

## 驗證
在 `apps/stock-desk/frontend`，先照 `.github/workflows/stock-desk.yml` 確認 CI 步驟（`npm ci`、typecheck、test、build），再實跑：
- `npm ci`：成功。
- `npm run typecheck`：通過。新測試第一次寫完時有一個 `m[1]` 可能是 undefined 的型別錯誤，我已改成 `?? ""`，沒有用 any 或強制斷言。
- 全量 `npm test`（vitest）：118 個檔、3116 個測試全過（含新增的 6 個）。
- `npm run build`：成功。
- `backtestFrontendBoundary.test.ts`：移除三項後通過。
- `backtestAssumptionsDisclosure.test.ts` 與 `backtestRoundTripRender.test.ts` 在全量中都過。

**新測試檔 `frontendTrimThreeLiterals.test.ts`，6 個測試，對應 RC-717 四項：**
1. SettingsForm 原始碼含第一句全文且剛好 1 次。
2. SettingsForm 去掉註解後的程式碼不含 `app/advice/limits.py` 與「一一對應」。
3. 渲染出的費率警示 `role="alert"` 元素，文字 `toBe` 第三句全文。我先篩出含「費率未查證」的 alert，確認剛好 1 個再斷言。
4. 渲染結果中第二句出現 2 次（兩個樣本段各 1 次），且不含「見後端」。
5. 價格事件 fixture（`close`、`threshold`、`currency`、`bar_as_of`）：輸出含「最新收盤價: 605」與「bar_as_of: 2026-11-24」，項目數是 4，整行逐字相等。
6. `signal_condition` fixture：`signals_as_of: 2026-11-24` 有出現。

**「改回舊字會變紅」實測**：我暫時把三處改回舊字，並把 `signalFieldLabel(key)` 改回 `key`，再跑這兩個測試檔。
- 結果：6 個測試變紅（25 過、6 失敗）：
  - `backtestFrontendBoundary` 的 BASELINE 測試 1 個；
  - 新測試的第 1、2、3、4、5 項各 1 個，共 5 個。
- 第 6 項（`signals_as_of`）沒有紅，因為這項只防案 C，沒有舊字會讓它變紅，這是預期的。
- 測完已從備份還原三個檔。`git status` 乾淨，commit 內容是新字，全量測試也是在還原後重跑的。

## 下一步
1. qa-reviewer 照 RC-718 的 qa 核對項審查，再交 risk-compliance-officer 做 risk-gate。
2. 是否要 qa-e2e 由 qa 判定。
3. coordinator 合併時，另需確認 #156 期間尚未開始，並走修訂八流程。

**需要你知道的偏離與沒有查證的事項**
- **偏離指示的一處**：第 2 個測試（不含 `app/advice/limits.py` 與「一一對應」）我只檢查去掉註解後的程式碼，沒有檢查整個原始碼。
  - 原因：`SettingsForm.tsx` 的第 28、32、47、100、113 行是開發者註解，本來就引用 `limits.py`。畫面上看不到，我也沒有改動。
  - 如果風控要求連註解都不含，需要另外處理這幾行註解，我沒有擅自改。
  - 第 1 個測試（第一句全文剛好 1 次）仍是對原始碼全文斷言。
- 去註解用的是簡單 regex，不是完整 parser。
- 沒有跑 qa-e2e，也沒有實機看畫面。我沒有啟動 `next dev` 或 preview，沒有程序需要關閉。
- 沒有跑 lint，因為 CI 沒有這一步。
- 沒有核對 `UNVERIFIED_RATES_NOTE` 等 backend 字面，因為這批不改 backend，且 backend 零差異。
- 沒有讀 `.env*`，沒有碰 `backend/data/` 和其他 worktree，沒有執行 `.bat`。
- 過程中有兩次指令被 worktree 隔離機制擋下（組合太複雜）。我拆成單純指令後才執行，沒有繞過。
- `npm ci` 後有產生 `node_modules` 和 build 產物。這些都在 `.gitignore` 內，`git status` 乾淨。

# 風控整改分支併入產品線（信任缺陷）交件

- 審查者：frontend-engineer
- 日期：2026-10-26
- 轉存：coordinator，逐字轉存 subagent 最終回報

---

## 本次結論
已把 origin/product/stock-desk（f66fc9d）以 `--no-ff` merge commit 併進 `fix/stock-desk-risk-remediation`，完整 CI 全綠後已 push。
- merge commit：`b4cbc5dfc3dec9db31baa27eb6ee080046f9f3cb`
  - 第一個 parent 是 4c9e1fe，第二個 parent 是 f66fc9d。
  - 標題為「chore: 合併產品線（信任缺陷修正）進風控整改分支」，結尾有兩行 trailer。
- 沒有 rebase、沒有 force push。
- push 第一次就成功，`4c9e1fe..b4cbc5d`，已設定 upstream。
- 兩邊對同一處給出不同字面的情況沒有出現，所以沒有停下來回報。
- 紅線：沒有讀 `.env`；沒有碰 `apps/stock-desk/backend/data/*.db`；測試全用既有的 tmp_path；沒有寫入祕密。
- 我沒有在這次 merge 中改任何一行程式碼，只解了一處文字衝突。

## 衝突解法逐檔
只有一個檔案衝突：`apps/stock-desk/frontend/app/lib/__tests__/componentWordingScan.test.ts`。
- 衝突位置在 `SCANNED_FILES` 陣列末尾，兩邊都在 `PriceUnitBadge.tsx` 條目之後各加了新條目。
- 解法：兩邊全部保留，沒有刪任何條目或守門斷言。
  - 我方 4 條：`../riskRemediationWording.ts`、`../limitNotices.ts`、`../../position/[symbol]/UnvalidatedNotice.tsx`、`../../position/[symbol]/StopQualifier.tsx`。
  - 產品線 1 條：`../quantityAbsenceWording.ts`（含其「股數成因 Q-a／Q-b／D-a／D-b」註解）。
  - 兩邊各自的註解行也都保留。
- 解完確認檔內沒有任何衝突標記。

## 四個語意重疊檔核對結論
我比對了「4c9e1fe 與 merge 後」及「merge-base 6b20774 與產品線」的差異。

1. `apps/stock-desk/frontend/app/lib/adviceWording.ts`：沒有衝突。
   - 產品線只改了 `QUANTITY_RANGE_ABSENCE_TEXT` 與 `QUANTITY_RANGE_ABSENT_SHORT` 的說明註解，字面一字未改（C-0 沿用）。
   - 我方改的是 `CONFIDENCE_PREFIX` 的孤兒註解，兩處互不重疊。
   - `CONFIDENCE_PREFIX` 仍然只有測試在引用。
2. `apps/stock-desk/frontend/app/lib/operationSummary.ts`：沒有衝突。
   - 產品線新增 `blockedAction`、`quantityAbsenceCause`，並讓 `quantityAbsenceReason` 依成因取字面（D-a、D-b、C-0）。
   - 我方新增 `topMatchedRuleId`。
   - 兩邊是互相獨立的欄位。
3. `apps/stock-desk/frontend/app/position/[symbol]/DecisionCard.tsx`：沒有衝突，兩邊並存。
   - merge 後相對 4c9e1fe 的差異只有四處：
     - 把 `QUANTITY_RANGE_ABSENT_SHORT` 的 import 換成 `QUANTITY_ABSENT_SHORT_BY_CAUSE`。
     - 兩處註解。
     - `quantityText` 的取值改為依成因取字。
   - 股數成因是在「股數參考」格內依成因顯示（`DecisionCard.tsx:386-389` 設定 `quantityText`，`:497` 渲染）。
   - 4-T 只移走了停利格，股數格仍在三格容器內，所以股數成因的呈現位置沒有消失。
   - `quantityAbsenceCause.test.ts` 與我方的 `riskRemediationItem4.test.ts`（三格容器）都通過。
   - 以下整改字面在 merge 前後逐字相同，因為相關檔案完全沒被產品線改到：1-L（`UnvalidatedNotice.tsx`）、2-V／2-M／2-R／2-O（`limitNotices.ts`，2-R 只在 `hold` 時顯示）、4-Q／4-E（`StopQualifier.tsx`）、4-附全形括號（`OperationSummaryPanel.tsx`）、3-S／3-F／3-N、5-BT。
   - 我另外驗證了這些檔案 `git diff 4c9e1fe HEAD` 為空：`riskRemediationWording.ts`、`limitNotices.ts`、`UnvalidatedNotice.tsx`、`StopQualifier.tsx`、`OperationSummaryPanel.tsx`、`KeyLevelsPanel.tsx`、`layout.tsx`、`backtest/`、`alerts/`、`engine.py`、`backtestCurveWording.ts`、`entryObservationWording.ts`、`sectionTaglines.ts`。
4. `apps/stock-desk/README.md`：沒有衝突，也沒有字面重疊。
   - 產品線改的是「快速啟動」「資料存放與備份」「環境變數」等區段，第 6 行 3-F 全文沒被動，仍是我方版本。
   - 前端 `riskRemediationWording.test.ts` 的 README 與 3-F parity 測試通過，證實這點。

其他你點名的項目（信任缺陷這邊，由 merge 帶進來）：
- `isEntryObservationPending` 在 `lib/entryObservation.ts:177`，只讀 `isPending`。
- 用到它的地方是 `position/[symbol]/page.tsx:151` 與 `EntryObservationPanel.tsx`。
- R1～R4 tripwire 與 E-4 守門測試（`entryObservationPending.test.ts`、`entryObservationE4Guard.test.ts`）都保留且通過。
- 空持倉顯示「尚無持倉」／「—」的測試（`summaryCardsEmptyBook.test.ts` 等）也通過。
- 產品線的 `limits.py`／`book_limits.py` 改動不涉及 Kelly（diff 內搜尋 kelly 無結果），沒有影響 5-K 範圍。

觀察（不是衝突，不用處理，供你知悉）：2330 型卡片（action 為 hold 且 `blocked_action` 為 add）股數格現在會印 Q-b「加碼參考被風險上限擋下」。同一張卡的上限區塊也有被擋句「加碼建議被第 N 條上限（…）擋下。」，兩者字面不同、位置不同，沒有矛盾，只是同一件事會在兩處各說一次。

## CI 結果（merge commit b4cbc5d 之上）
前端（`apps/stock-desk/frontend`）
- `npm run typecheck`（`tsc --noEmit`）：`TSC_EXIT=0`
- `npx vitest run`：`Test Files  91 passed (91)`，`Tests  2505 passed (2505)`，`VITEST_EXIT=0`
- `npm run build`：`BUILD_EXIT=0`

後端（`apps/stock-desk/backend`）
- `uv run ruff check .`：`All checks passed!`，`EXIT=0`
- `uv run ruff format --check .`：`441 files already formatted`，`EXIT=0`
- `uv run mypy app tests`（strict）：`Success: no issues found in 436 source files`，`EXIT=0`
- pytest：
  ```
  TOTAL                                       19165    500    97%
  Required test coverage of 90% reached. Total coverage: 97.39%
  8149 passed, 2 xfailed, 18 warnings in 1385.47s (0:23:05)
  BT_EXIT=0
  ```
  - 用 `nohup setsid bash r.sh` 脫離執行，pytest 由 Python runner（`run_tests.py` 呼叫 `pytest.main`，參數含 `--cov=app --cov-report=term-missing --cov-fail-under=90`）啟動，命令列沒有 "pytest" 字樣，沒有被 pkill 打斷。
  - 與合併前相比：vitest 從 2413 增為 2505（+92），pytest 從 8089 增為 8149（+60）。

輸出檔在 `/tmp/claude-0/-home-user-AICompany/3f76d891-50d3-55e1-b39d-925b8a90241a/scratchpad/`：`m_tsc.txt`、`m_vitest.txt`、`m_build.txt`、`m_ruff.txt`、`m_fmt.txt`、`m_mypy.txt`、`m_bt.txt`；merge 訊息檔是 `merge_msg.txt`。

## 仍待處理
- C-9 的 dev-lead 書面確認；這批 merge 帶進來的產品線文件裡是否已含，我沒有檢查，請 coordinator 確認。
- 5-K 仍未做，等 CEO 對「停用會拿掉 10% 封頂」的裁定。

HEAD：b4cbc5dfc3dec9db31baa27eb6ee080046f9f3cb（`fix/stock-desk-risk-remediation`，已 push，工作區乾淨）。

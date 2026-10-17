# B0 R-1／R-2：持倉查詢非成功狀態一律視為持倉未確定（frontend-engineer 回報）

- 審查者：frontend-engineer；commit 9daee65（父 8d6d1f3），未 push、未合併。coordinator 機械核對：非測試檔 diff 排除註解後只剩型別、resolver 判斷與 page.tsx 呼叫引數，page.tsx 其餘變動位於 JSX 註解 {/* */} 內，無字面常數或可見文字異動
- 日期：2026-10-17
- 轉存：coordinator，逐字轉存 subagent 最終回報

---

## 本次結論
R-1、R-2 已完成並 commit，新 commit 為 `9daee65`（分支 `fix/stock-desk-b0-hold-stop-anchor`，接在 8d6d1f3 之後）。沒有 push、沒有 merge，沒有啟動 server，也沒有讀 `.env` 或 `*.db`。node_modules 是從主工作樹 `cp -a` 過來的，驗證完已刪除，`git status` 乾淨。

## 各部門回報（frontend-engineer）

**方案選擇：方案 2**（判斷收進 resolver）。
- `resolveKeyLevelsAnchor` 的第一個參數從 `PositionsResponse | undefined` 改成 `PositionsAnchorInput = {isSuccess: boolean; data: PositionsResponse | undefined}`。
- 判斷改成 `const book = positions.isSuccess ? positions.data : undefined; if (!book) return holding-unknown`。
- `page.tsx` L128 改成傳整個 `positions` query 結果，`useQuery` 的結果直接符合這個 slice。
- 不是 success 就一律是 `holding-unknown`，包含 error 但帶舊 data。
- 重抓進行中時 status 仍是 success，所以沿用最後一次成功資料，這是風控 2b 已核准的已知限制。

**槓桿查詢啟用條件（`leverageHolding.ts`）：邏輯不需要改。**
- `isLeverageQueryEnabled` 本來就是 `isError` 優先，所以 error 帶舊 data 時一律啟用，不看舊清單，改問後端。
- 這和新行為同一原則：非 success 的 data 不採信，以後端為準。
- 我只做了兩件事：補一行 doc 註解說明這點，並在 `leverageHolding.test.ts` 新增一個案例，釘住 `{isError: true, data: 持有／未持有／空清單}` 三種都回 true。

**diff 摘要**（9 個檔案，+103/−44）

| 檔案 | 變動 |
|---|---|
| `app/lib/keyLevelsAnchor.ts` | 新增 `PositionsAnchorInput`，resolver 改依 `isSuccess` 判斷；L14-15 的「pending／failed」改寫成「非 success 狀態：載入中、失敗，含重抓失敗仍帶舊資料；重抓進行中沿用最後一次成功資料」 |
| `app/position/[symbol]/page.tsx` | L128 傳 `positions` 而非 `positions.data`；L479-484 的 JSX 註解（`{/* */}`，不渲染）改寫成同上說法 |
| `app/position/[symbol]/DecisionCard.tsx`、`KeyLevelsPanel.tsx`、`app/lib/keyLevels.ts` | 各一處註解改寫成同上說法 |
| `app/lib/leverageHolding.ts` | 只加 doc 註解 |
| `keyLevelsHoldingUnknown.test.ts` | 刪除 L224-229 的原始碼掃描測試；新增 `ok()`、`NO_DATA` helper，既有呼叫點改用 slice；新增「status error 帶舊 data」案例（持有、空清單各一），斷言 resolver 回 `holding-unknown`，且面板輸出與 `NO_DATA` 完全相同，沒有 LM-16／LM-17／LM-53／「未持有此標的」／「相對成本損益」；另加一個「重抓進行中沿用最後成功資料」的案例，把已知限制寫成可執行的文件 |
| `keyLevelsAnchorMismatch.test.ts` | 呼叫點機械式改成 slice，行為與斷言不變 |
| `leverageHolding.test.ts` | 新增 1 個案例（見上） |

## 驗證

**反向驗證**（兩種接線都做了，都已還原）
1. resolver 改回只看 `data`（`const book = positions.data`）：vitest 變成 2 failed / 2256 passed。紅的正是 R-2 新增的兩個案例（stale 持有、stale 空清單）。
2. `page.tsx` 改回 `resolveKeyLevelsAnchor(positions.data, …)`：`tsc --noEmit` 報 TS2345（`NoInfer<PositionsResponse> | undefined` 不能指派給 `PositionsAnchorInput`）。
   - 因為 L224 的原始碼掃描已刪，頁面接線改由型別檢查把關。
   - vitest 本身看不到頁面層，這點要說明。
   - 要是你想再多一層保險，e2e 補「先持有、focus 觸發重抓並注入 500」的情境，風控已列為 suggested。

**最終結果**（還原後）
- `tsc --noEmit`：exit 0，無錯誤。
- `vitest run`：80 個檔案全過，**2258 passed / 2258**。
- 測試數 2255 到 2258 是 +3：−1（刪掃描測試）+2（stale 兩案例）+1（進行中案例）+1（槓桿案例）。

**commit：`9daee65`**，trailer 為指定的 Co-Authored-By 與 Claude-Session。

**確認沒有字面常數或可見文字變動的依據**
- 我對非測試檔做了 `git diff -U0`，排除所有 `//`、`*`、`/*` 開頭的註解行後，剩下的變動只有：
  - `PositionsAnchorInput` 介面；
  - resolver 的參數型別與 `book` 判斷（共 3 行）；
  - `page.tsx` L128 的呼叫引數；
  - `page.tsx` 那段 `{/* */}` JSX 註解的內文行（因為它不是 `//` 開頭，被篩出來；它是 JSX 註解，不會渲染）。
- 沒有任何 string literal、`KEY_LEVELS_*`／`DECISION_CARD_*`／`LM-*` 常數、JSX 文字節點被動到：`decisionCardWording.ts` 完全沒在 diff 裡；`KeyLevelsPanel.tsx`、`DecisionCard.tsx`、`keyLevels.ts` 的 diff 都只是註解行。
- 既有的字面斷言測試（含 `buildStopBasisHeld`、LM-53 等）全部原樣通過，也間接證明字面沒變。
- 建議 coordinator 照風控指示用 `git -C … diff 8d6d1f3..9daee65 -- ':!*__tests__*'` 機械核對一次。

**新 commit hash：`9daee65`**

## 下一步
1. qa-reviewer 增量審查，範圍為 `8d6d1f3..9daee65`（含 R-3 的 8d6d1f3）。
2. coordinator 機械核對 diff 無字面常數異動，符合就不必再送風控。
3. 待辦登記沿用風控清單：2b fetch 逾時、2c 頁面層持有狀態一致性、LM-19 負號、M2 優先序。
4. CEO 裁示 #23、#24，並決定 Codex 例外是否接受。

**已知限制**：重抓進行中沿用最後一次成功的持倉資料（`api.ts` 的 fetch 沒有逾時，所以這段時間沒有上限），已在註解與測試中明寫。

相關路徑：`/home/user/AICompany/.claude/worktrees/agent-a90e4192ba546bc4d/apps/stock-desk/frontend/app/lib/keyLevelsAnchor.ts`、`.../app/position/[symbol]/page.tsx`、`.../app/lib/__tests__/keyLevelsHoldingUnknown.test.ts`、`.../app/lib/__tests__/leverageHolding.test.ts`。

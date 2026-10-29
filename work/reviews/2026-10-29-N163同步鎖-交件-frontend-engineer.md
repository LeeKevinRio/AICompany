# N-163 同步 ref 鎖追加交件

- 審查者：frontend-engineer
- 日期：2026-10-29
- 轉存：coordinator，逐字轉存 subagent 最終回報

---

## N-163 追加 commit 交件：同步 ref 鎖（已修、已推送）

分支 `fix/stock-desk-exit-pending-focus`，追加 commit `74979dd`（前一個是 3ceef60），已 push。字面、送出 API、核取方塊都沒動。

### 做了什麼
1. **[required] 同步 ref 鎖**
   - `submit` 一開頭檢查 `submittingRef.current || mutation.isPending`，通過後立刻設成 `true`，再呼叫 `mutate`。
   - `onSettled` 把 ref 設回 `false`。`onSettled` 在成功與失敗都會跑，所以失敗後可再送。
   - `cancel` 的防護也改成 `submittingRef.current || mutation.isPending`。
   - 我沿用 `mutate` 加 `onSettled`，沒改成 `mutateAsync().finally`。原因：`mutateAsync` 失敗時會 reject，需要額外吞例外，否則出現 unhandled rejection。現有寫法已經走 react-query 的 `mutation.isError` 與 ErrorPanel 錯誤流程。兩者的鎖釋放時機相同，沒有更穩，反而多一個風險點。
2. **[required] NB-4**：Step 3 按鈕上方的 N-163 說明註解改成全英文。我順手把第 140 行殘留的中文「取消」也改成 cancel。檔頭既有、逐字引用視覺規範與按鈕字面的註解，是原本就有的，沒動。
3. **[suggested] NB-2**：兩顆按鈕改成 `aria-disabled={mutation.isPending || undefined}`。閒置時屬性不渲染，pending 時為 `"true"`。Tailwind 的 `aria-disabled:` 變體本來就只匹配 `[aria-disabled=true]`，所以沒有影響。tsc、vitest、`next build` 全過，沒有其他測試受影響。

### 落點
`apps/stock-desk/frontend/app/playbook/EmergencyExitControl.tsx`
- 宣告 `submittingRef`：74 行（含說明註解）
- `cancel` 防護：93 行
- `submit` 檢查與取得鎖：103–104 行
- `onSettled` 釋放鎖：112–114 行
- 兩顆按鈕 `aria-disabled`：282 行與 290 行
- 說明註解：約 269–280 行

### 測試
檔案是 `app/playbook/__tests__/EmergencyExitPortal.test.ts`。
- **新增**：`holds a synchronous ref lock across the mutate call and releases it on success and failure`
  - 斷言有 `const submittingRef = useRef(false);`。
  - 斷言檢查位置早於取得鎖，取得鎖位置早於 `mutation.mutate(`。
  - 斷言 `onSettled` 內重置 ref，且全檔只有一處 `= true`、一處 `= false`。這樣「只在 `onSuccess` 釋放」會被擋下。
- **更新**（斷言收緊或對應新寫法，沒有放寬）：
  - `refuses to submit again while pending or locked ...`
  - `refuses to cancel while pending or locked, whatever triggers it`
  - `Step 3 buttons use aria-disabled ...`：改匹配 `|| undefined` 寫法，且仍斷言兩顆都有。

變異驗證：把釋放鎖那行改成 no-op，新增的鎖測試失敗，復原後全過。

**擋不到**：這是原始碼掃描，不能證明同一 tick 雙擊真的只送 1 筆 POST。那要靠 qa-automation 的實測。另外，如果元件在 pending 中被卸載，`onSettled` 不會觸發。但卸載後 ref 也隨元件消失，不影響行為。

### CI（前端）
- `tsc --noEmit`：無錯誤。
- `vitest run`：96 個檔案、2587 條測試全過（上一輪是 2586 條，這次新增 1 條）。
- `next build`：成功，8 個路由。

### 給重入短測的重點
- 同一 tick 內連續兩次啟動「確認送出全部出清」（例如在同一個 evaluate 內呼叫兩次 `click()`），POST 應該恰好 1 筆。
- 失敗後再按「確認送出全部出清」，應該能再送（POST 筆數累加，不會被鎖死）。
- 成功後重新開啟流程再送，也應該能送。

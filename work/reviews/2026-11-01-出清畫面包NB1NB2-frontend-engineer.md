# 出清畫面包 NB-1／NB-2 測試補強

- 審查者：frontend-engineer
- 日期：2026-11-01
- 轉存：coordinator，逐字轉存 subagent 最終回報

---

## 本次結論

**NB-1 與 NB-2 已補上，只改了兩個測試檔，沒有動任何來源檔。前端 CI 全綠，已推送。**
- 分支：`origin/fix/stock-desk-exit-feedback`，HEAD `b3d6284`，快轉推送，無 force。
- 受測的來源版本不變：`git diff 47f8ad9..HEAD` 只列出兩個檔案，都在 `__tests__/` 下。
- NB-3、NB-6 依指示未做。
- 我的工作樹與 node_modules 硬連結已移除。`git worktree list` 裡還有 `scratchpad/e2e_exitfb`（停在 `47f8ad9`），那是實機驗收用的，不是我的，我沒有動。

## 各部門回報

### frontend-engineer（本人）

| commit | 內容 |
|---|---|
| `…` test（NB-1） | `playbook/__tests__/exitFlowStructure.test.ts`：持久化掃描的 `exitFiles` 加入 `lib/exitReceiptStore.ts` 與 `lib/exitReceiptContext.tsx`（FE-C5、VETO-3）。 |
| `b3d6284` test（NB-2） | `lib/__tests__/emergencyExitSettle.test.ts`：(c4) 矩陣每個情境加 `expectedStatus`，並移除常數 `step` 的重複斷言。 |

- **NB-1**：加入後，同一個 `exitFiles` 也用在其他掃描（`exit_confirm` 持有者清單、`scope:`／`useIsMutating`），新增的兩個檔案都通過。
- **NB-2** 的預期值：
  - `normal`、`c3 subscriber throws`：success。
  - `c1 sink throws`、`c2 reducer throws`、`mutationFn rejects`：error。
  - 先斷言 status 等於預期，再走對應分支。
  - 常數 `step` 那行拿掉，Step 3 的失敗面板條件由 `exitFlowStructure` 的 `showFailure` 逐字掃描承擔，註解已寫明。

### 其他部門
本輪沒有其他部門參與。

## 驗證

**前端 CI**，在 HEAD `b3d6284`：
```
npm run typecheck   tsc --noEmit，無輸出（通過）
npm test            Test Files 110 passed (110)；Tests 2852 passed (2852)
npm run build       ✓ Compiled successfully；├ ○ /playbook
```

**變異驗證**（暫時破壞，已還原，`git status` 乾淨）
- 在 store 加一行 `localStorage` 參照：持久化掃描失敗。
- 在 `onSuccess` 吞例外：(c1)、(c2) 與改寫後的 (c4) 都失敗。

**後端**：這一輪沒有改動，沒有重跑；最近一次後端 CI 在 `47f8ad9` 全綠（8535 passed，覆蓋率 97.44%）。

沒讀 `.env`，沒碰 `data/*.db`，沒寫入任何祕密。

## 下一步

1. **qa-e2e**：實機驗收的受測版本仍是 `47f8ad9` 的行為，`b3d6284` 只多了測試，驗收結果可沿用。
2. **N-181**：NB-3、NB-6 已記入追蹤，未做。
3. **遺留，無變動**：
   - 「我已閱讀，繼續」使用 `aria-disabled`，qa 腳本須查 `aria-disabled`。
   - 視覺規範 §7 補註未做。
   - FE-C23：本分支不得早於 N-166 上線。
   - NB-4 的 commit 排序問題（`52e40da`、`59232cf` 在來源 commit 之前）不重排，整體合併即可。

分支：`origin/fix/stock-desk-exit-feedback`（HEAD `b3d6284`）。
變更檔案（`apps/stock-desk/frontend/app/` 下）：`playbook/__tests__/exitFlowStructure.test.ts`、`lib/__tests__/emergencyExitSettle.test.ts`。

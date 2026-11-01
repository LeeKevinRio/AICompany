# 出清畫面包 FE-R1～FE-R5（FE-R3 待 TA）

- 審查者：frontend-engineer
- 日期：2026-11-01
- 轉存：coordinator，逐字轉存 subagent 最終回報

---

## 本次結論

**FE-R1、FE-R2、FE-R4、FE-R5 已完成，另外實查了「送出中取消／Esc 是否仍鎖住」。FE-R3 我停下來沒有改，原因是修法會改到 ADR-0037 的 FE-C4 條文，需要轉給 tech-architect。**

已推送：`origin/fix/stock-desk-exit-feedback`，HEAD `69cd00d`，快轉，無 force。工作樹與 node_modules 硬連結已移除，主 checkout 完好。CI 全綠。

- **FE-R1**：已完成。
- **FE-R2**：已完成，為常駐守門測試。
- **FE-R4**：`132e0c6` 已符合，逐條對照見下。
- **FE-R5**：沒有實作任何「上一次送出」顯示，程式內也沒有從 mutation cache 推導的狀態。
- **取消／Esc 實查**：送出中仍鎖住，source 與實機都確認。
- **FE-R3 待決**：見「各部門回報」的 FE-R3 段，請轉 tech-architect。

## 各部門回報

### frontend-engineer（本人）

**本輪 commit**

| commit | 內容 |
|---|---|
| `8493a82` fix | FE-R1：`emergencyExitMutationOptions` 加 `networkMode: "always" as const`，只限出清這一支。`providers.tsx` 的 `new QueryClient()` 字面不變，沒有 `defaultOptions`、`setMutationDefaults`。出清 options 沒有 `retry`、`scope`、`mutationKey`。結構測試同步（工廠內 `networkMode` 只出現一次）。 |
| `69cd00d` test | FE-R2：新增 `emergencyExitOffline.test.ts`。 |

**FE-R2 的測試內容**（真的 `QueryClient`、`MutationObserver`、`onlineManager`，每個測試後還原 online 狀態）
- `setOnline(false)` 後 mutate，fetch mock 以 `TypeError` reject：
  - `mutationFn` 恰好 1 次；
  - 最終 status 為 `error`；
  - 過程中所有觀察到的 state，`isPaused` 都為 false，且確實看到過 `pending`。
- `setOnline(true)` 並呼叫 `resumePausedMutations()` 後，呼叫次數仍為 1，cache 裡沒有任何 paused mutation。
- 離線失敗不寫回執；使用者之後重試，恰好多 1 次請求。
- **對照組**：去掉 `networkMode` 後，同樣情境是 `pending` + `isPaused: true` 且 `mutationFn` 從未被呼叫，證實 VETO 的前提。
- 源碼掃描：`networkMode: "always"` 在 `queries.ts` 只出現一次；工廠內無 `retry`、`retryDelay`、`scope`、`mutationKey`；`providers.tsx` 不含 `networkMode`。
- 變異驗證：移除 `networkMode` 後，這個檔案 6 個測試中 6 個失敗（離線測試因為暫停而逾時）。已還原。

**FE-R4 逐條對照 FE-C8**（`132e0c6` 的 `playbook/useEmergencyExitFlow.ts` 已符合，本輪沒有改）

| 要求 | 現況 |
|---|---|
| 依賴陣列恰為 `[receipt?.seq, scrolledSeq, isOpen]` | 第 149 行 `[receiptSeq, scrolledSeq, isOpen]`，其中 `const receiptSeq = receipt?.seq`（第 129 行） |
| 條件是 `!isOpen` | `shouldScrollForReceipt(receiptSeq, scrolledSeq, isOpen)`，成立條件為 `receiptSeq > scrolledSeq && !isOpen`（`lib/exitReceipt.ts`） |
| effect 執行當下重讀 `getSnapshot()` | 第 131 行 `receiptStore.getSnapshot()`，判斷用重讀的 `latest.scrolledSeq`，不用 render 期間的值 |
| 先捲動，再 `scrollHandled` | `scrollIntoView` 與必要的修正之後，第 148 行才呼叫 `scrollHandled(seq)`；不需要捲動時也標記 |
| 對話框開著時到達的回執，關閉後捲一次 | `exitReceipt.test`、`exitReceiptStore.test` 有「寫入時開著、關閉後捲一次、再跑不捲」；`exitFlowStructure` 掃描依賴與順序 |

風控文中說的「`markScrolled`、依賴只有 `[receiptSeq]`、標記不通知」是 `04baf82` 的舊寫法，已在 `132e0c6` 改掉。

**取消與 Esc 的實查：送出中仍鎖住**
- **原始碼**：
  - `EmergencyExitDialog.tsx` 的 `cancel()` 第一行 `if (lockRef.current || isPending) return;`；
  - Esc 處理 `event.key === "Escape" && !isPending`，再經 `cancel()`；
  - `useEmergencyExitFlow.ts` 的 `close()` 也有同一個守門；
  - 取消與送出兩顆鈕在 pending 時為 `aria-disabled`。
- **實機**（Chromium、production build、API 全部 mock）：POST 延遲 2 秒，送出後按「取消」（`force`）、按 Esc、對「送出中…」再點一次、按 Enter，對話框仍開著、停在第 3 步，POST 恰好 1 筆；回應到達後對話框關閉並出現橫幅。
- 腳本與輸出在 scratchpad `exitfb_ci/smoke_r.js`、`smoke_out3.json`。

**實機另驗 Q-1（離線）**
- 離線按送出（POST 以 `internetdisconnected` abort，並 `setOffline`）：2 秒內出現 NB-6 面板（標籤加三段字面逐字正確），沒有「送出中…」殘留。
- 恢復連線並等 3 秒：沒有新請求。
- 再按一次送出：多恰好 1 筆，橫幅出現，對話框關閉。

**FE-R3：停下來說明（需 tech-architect 收斂）**
- **現況**：FE-C4 要求定義層 `onSuccess` 以 try/catch 包住 `receipts.accept()`，並用 `void Promise.reject(e)` 外拋，不得讓例外外漏。這會讓 mutation 維持 `success`，頁面的 mutate 層 `onSuccess` 照樣關閉對話框。若 `accept()` 拋出，畫面上就是「2xx 已到、對話框關了、沒有橫幅、也沒有 NB-6」。
- **任何滿足風控不變式的修法，都必須改 FE-C4 的條文。** 我分析了兩條路，沒有實作任何一條：
  1. **（風控傾向，我也建議）去掉吞例外。** `accept()` 拋出就直接讓例外傳出 `onSuccess`，落到 `mutation.ts:273` 的失敗分支。結果是 status 變 `error`，對話框不關，顯示 NB-6。NB-6 第 1 句「也可能已受理」為真，使用者再送一次會拿到 S1 的完整重述。需要改：FE-C4 的「try/catch、不得外漏」兩條，以及 FE-T13(c)（改成驗證：sink 拋出時 mutation 為 `error`、`mutate` 層 `onSuccess` 不執行、NB-6 條件成立）。
     - 附帶要確認一點：`accept()` 本身是純 reducer 加通知訂閱者的迴圈。真正可能拋出的是訂閱者（React 的 `useSyncExternalStore` 回呼），而那時 state 已經更新、橫幅其實已寫入。這時畫面會同時出現橫幅和 NB-6，兩者都為真，可以接受，但請 tech-architect 確認是否要讓 `accept()` 先寫入、再吞訂閱者例外。
  2. **保留吞例外，由頁面補救。** mutate 層 `onSuccess` 檢查 store 的 `receipt.seq` 是否在送出後前進；若沒有，不關對話框，並以頁面層旗標顯示 NB-6。這需要新的頁面狀態、修改 FE-C9 的失敗面板顯示條件，也等於在 FE-C4「mutate 層只關閉對話框」之外多加邏輯。
- 其餘未改，沒有為此動任何程式碼。若採 1，改動約 10 行加一個測試。

### 其他部門
本輪沒有其他部門參與。

## 驗證

**前端 CI**，在 HEAD `69cd00d`：
```
npm run typecheck   tsc --noEmit，無輸出（通過）
npm test            Test Files 110 passed (110)；Tests 2843 passed (2843)
npm run build       ✓ Compiled successfully；├ ○ /playbook
```

**後端 CI**，在同一個工作樹上重跑（本輪後端沒有改動，`git diff` 後端為空）。原文在 `…/scratchpad/exitfb_ci/backend_ci_4.log`：
```
ruff check .                         All checks passed!
ruff format --check .                459 files already formatted
mypy app tests                       Success: no issues found in 453 source files
pytest --cov=app --cov-fail-under=90 Required test coverage of 90% reached. Total coverage: 97.44%
                                     8535 passed, 2 xfailed, 32 warnings in 898.38s (0:14:58)
```

**未驗證**
- 實機 smoke 只跑了離線與取消／Esc 兩段，之前的情境沒有在這個 HEAD 上重跑。
- Firefox、WebKit 沒測。
- 「送出中離開頁面、之後請求失敗」的殘留（風控 Q-2）我沒有做，這是風控明示接受、由 N-171 承接的缺口，不是本包的缺陷。
- 沒讀 `.env`，沒碰 `data/*.db`，沒寫入任何祕密。

## 下一步

1. **tech-architect／coordinator**：裁定 FE-R3 走路 1 還是路 2，並修改 ADR-0037 的 FE-C4 條文與 FE-T13(c)。裁定後我可以在 `fix/stock-desk-exit-feedback` 上實作。
2. **tech-architect**：ADR-0037 的 Consequences 把 `networkMode` 改為「已裁定 `'always'`」，新增 FE-C24（定義層 `networkMode: "always"`，不得有 `retry`、`scope`）。程式與測試已先符合這個條文。
3. **qa-reviewer**：實查 FE-R1、FE-R4 與取消／Esc 的結論；本報告給了行號與實機輸出。
4. **qa-e2e**：Q-1 和 Q-2 照風控的寫法；Q-1 我已用 mock 路由演練過一輪，但不是驗收。
5. **PM**：PM-8（FR-8a／FR-8b 註明離線立即失敗顯示 NB-6、不暫停、不自動送出）。
6. **未完成，前幾輪遺留，無變動**：
   - 「我已閱讀，繼續」使用 `aria-disabled`，qa 腳本須查 `aria-disabled`。
   - 視覺規範 §7 要求在 `work/stock-desk-快市排程-視覺規範.md` 補註，我沒做。
   - FE-C23：本分支不得早於 N-166 上線。

分支：`origin/fix/stock-desk-exit-feedback`（HEAD `69cd00d`）。
主要檔案（`apps/stock-desk/frontend/app/` 下）：`lib/queries.ts`、`lib/__tests__/emergencyExitOffline.test.ts`、`playbook/__tests__/exitFlowStructure.test.ts`、`playbook/useEmergencyExitFlow.ts`、`playbook/EmergencyExitDialog.tsx`。

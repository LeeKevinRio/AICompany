# 出清畫面包對齊 ADR-0037 FE-C1～C23

- 審查者：frontend-engineer
- 日期：2026-11-01
- 轉存：coordinator，逐字轉存 subagent 最終回報

---

## 本次結論

**已依 tech-architect 的 ADR-0037 D 版逐條對齊（FE-C1／C2／C4／C8／C21／C22 為本輪變動），並補上 FE-T13、FE-T14。完整 CI 全綠，已推送。**
- 分支：`origin/fix/stock-desk-exit-feedback`，HEAD `132e0c6`，快轉推送，沒有 force。
- 工作樹與 node_modules 硬連結已移除，主 checkout 完好。
- 這一輪只動前端，後端沒改。

**需要你知道的三點**
1. **commit 順序**：我先 commit 了 `52e40da`（測試）再 commit 了 `132e0c6`（來源與測試更新）。`52e40da` 單獨看會缺 `132e0c6` 裡新增的 `ExitReceiptStoreContext` 匯出，不能單獨通過。要整體合併，不要逐個 cherry-pick。我沒有 rebase 重排，因為你的規則禁止。
2. **FE-C21 的 hook 名稱**：規格寫 `useExitReceipt`，我保留原名 `useExitReceiptStore`，掃描時兩個名稱都納入。
3. **FE-T4 的「store 有回執」那一組**：static markup 看不到有回執的 store，因為 `getServerSnapshot` 依 FE-C1 固定回初始空狀態。我改成兩半：
   - `PlaybookPageStates`（抽換 flow，注入回執）驗橫幅；
   - 新增 `PlaybookPageRealFlow`（真實 flow、真實 store）驗接線，並證實 store 已有回執時 server 渲染仍是空狀態。

## 各部門回報

### frontend-engineer（本人）

**本輪 commit**

| commit | 內容 |
|---|---|
| `52e40da` test | 頁面以真實 flow 與 Providers store 渲染四種 `/today` 狀態；沒有 `ExitReceiptStoreProvider` 時明確報錯，不靜默退回 module 層 store。 |
| `132e0c6` refactor | 對齊 FE-C1／C2／C4／C8／C21／C22。含 FE-T1、T3、T5 修訂與 FE-T13、T14。 |

**FE-C 對照表**（路徑省略 `apps/stock-desk/frontend/app/`）

| 項 | 落點 | 測試 |
|---|---|---|
| FE-C1 | `lib/exitReceiptStore.ts` 工廠；`lib/exitReceiptContext.tsx` 的 `useState(() => createExitReceiptStore())`；`providers.tsx` 保留 `new QueryClient()` 字面。頁面只以 `useSyncExternalStore(subscribe, getSnapshot, getServerSnapshot)` 讀取。 | `exitFlowStructure`：store 模組無頂層 `let`／`var`、無 `globalThis`／`window`、全 app 無頂層 `createExitReceiptStore()`；`providers.tsx` 無 `defaultOptions`／`mutationCache`／`setMutationDefaults`／`key=`、不 import playbook；playbook 內無持有回執副本的 `useState`／`useReducer`／`useRef`。`entryObservationPending` 的 R4 絆線在套件內全綠。變異驗證：加 `defaultOptions` 後兩個測試失敗。 |
| FE-C2 | `lib/exitReceipt.ts`：state `{receipt, scrolledSeq}`，action 只有 `accepted` 與 `scrollHandled`。`scrollHandled` 取 max，有變動才通知訂閱者，這是依 FE-C2 改掉了前一版「標記不通知」。 | `exitReceipt.test`、`exitReceiptStore.test`（FE-T1）：初始值、seq 1→2 取代、`scrollHandled` 不動 receipt 且重複呼叫回同一參照、未知 action 同一參照、`@ts-expect-error` 驗證沒有 clear／reset／set、兩個 store 互不影響、`getServerSnapshot` 固定初始值、store 只暴露五個成員 |
| FE-C3 | `ExitReceiptBanner` 只吃 store 的 receipt | `exitFlowStructure`：playbook 內無 `mutation.data`／`mutation.isSuccess`／`useMutationState`／`getMutationCache` |
| FE-C4 | `lib/queries.ts` 的 `emergencyExitMutationOptions(queryClient, receipts: ExitReceiptSink)`。定義層 `onSuccess`：同步、第一個動作、try/catch、catch 內 `void Promise.reject(error)`，不碰 UI 狀態。`useEmergencyExit(receipts)` 改由呼叫端傳入 sink，`queries.ts` 只以 type 引入 `ExitReceiptSink`，不再 import context。flow 的 mutate 層 `onSuccess` 只關對話框。 | `exitFlowStructure`：`receipts.accept(` 全 app 僅一處且位於 try/catch 內、第一個語句；無 async／await；`onSuccess` 內無 `setIsOpen`、`lockRef`、focus、scroll；playbook 無 `.accept(`；全 app 無 `setMutationDefaults`／`new MutationCache`。變異驗證：拿掉 try/catch 後 T13(c) 與掃描失敗。 |
| FE-C5～C7、C9～C20 | 沿用，無本輪變動 | 既有測試全綠 |
| FE-C8 | `lib/exitReceipt.ts` 的 `shouldScrollForReceipt(receiptSeq, scrolledSeq, isOpen)`；flow 的 effect 依賴恰為 `[receiptSeq, scrolledSeq, isOpen]`，執行當下 `getSnapshot()` 重讀，捲動後同步 `scrollHandled`。已刪 `lastHandledSeq`。 | `exitReceipt.test`（含 isOpen 真值表、「寫入時對話框開著，關閉後才捲」）；`exitReceiptStore.test`（StrictMode 雙跑只捲一次、跨頁面實例）；`exitFlowStructure`：依賴恰三項、內含 `getSnapshot()`、無 `today`、無 `lastHandledSeq`。變異驗證：拿掉 `isOpen` 或略過 isOpen 判斷，測試失敗。 |
| FE-C21 | `ExitReceiptBanner` 與 `useExitReceiptStore` 只被 `playbook/page.tsx`、`useEmergencyExitFlow.ts`、`ExitReceiptBanner.tsx`（與定義它的 context 檔）使用。`providers.tsx` 只 import `./lib/exitReceiptContext`；`queries.ts` 只 import `./exitReceiptStore` 的型別。 | `exitFlowStructure` import 範圍掃描 |
| FE-C22 | 出清相關檔案無 `scope:`、`useIsMutating`、`useMutationState`、`getMutationCache`；`lockRef` 只在頁面實例的 flow、對話框與 page（page 僅傳遞）。 | `exitFlowStructure` |
| FE-C23 | 本分支含 N-166 `36c7ceb` 與 NB-6 字面，上線耦合條件成立 | — |

**新增測試**
- **FE-T13**（`emergencyExitSettle.test`）：
  - (a) subscribe 後送出，resolve 前 unsubscribe，resolve 後 store 有 seq 1，mutate 層 `onSuccess` 的 spy 沒有被呼叫。
  - (b) `accept` 被呼叫當下 status 為 `pending`。
  - (c) sink 拋出例外：status 仍為 `success`、data 存在、例外被 `void Promise.reject` 外拋（測試以 spy 接住，不讓測試器看到 unhandled rejection），之後的 cancel／invalidate 仍有執行。
  - (d) 請求失敗時 store 不變。
- **FE-T14**：兩個 observer（舊頁面、新頁面），兩種到達順序，各自斷言 seq 為 2、最後到達的那份是顯示的回執、`accept` 恰好各一次。另證實兩次 POST 都送出，沒有任何客戶端閘門（VETO-4）。

**我們已經做了、規格也要求的設計決定**
- 對話框開著時延後捲動，是因為定義層寫入發生在 success dispatch 之前。回執可能比對話框關閉早一個 frame 出現，延後後在關閉時才捲。

### 其他部門
本輪沒有其他部門參與。

## 驗證

**前端 CI**，在 HEAD `132e0c6`：
```
npm run typecheck   tsc --noEmit，無輸出（通過）
npm test            Test Files 109 passed (109)；Tests 2837 passed (2837)
npm run build       ✓ Compiled successfully；├ ○ /playbook
```

**後端 CI**，在同一個工作樹上（HEAD `132e0c6`）重跑一次，`Popen(start_new_session=True)`、runner 有 `__main__` guard。後端這一輪沒有改動，為求完整仍重跑。原文在 `…/scratchpad/exitfb_ci/backend_ci_3.log`：
```
ruff check .                         All checks passed!
ruff format --check .                459 files already formatted
mypy app tests                       Success: no issues found in 453 source files
pytest --cov=app --cov-fail-under=90 Required test coverage of 90% reached. Total coverage: 97.44%
                                     8535 passed, 2 xfailed, 32 warnings in 777.16s (0:12:57)
```

**變異驗證**：下列破壞各自讓對應測試失敗，之後已還原。
- 拿掉 `onSuccess` 的 try/catch。
- 捲動 effect 去掉 `isOpen` 依賴。
- `providers.tsx` 加 `defaultOptions`。
- `shouldScrollForReceipt` 忽略 `isOpen`。

**未重跑的部分**
- 實機 smoke 沒有重跑。上一輪 smoke 在 FE-C4／C8 之前，這一輪的改動（捲動 effect 依賴與延後、定義層 try/catch、sink 傳入方式）尚未在 Chromium 上演練。這是我沒做的驗證，由 qa-e2e 的 FE-T12 修訂版承接。
- 你提到的 product 線上 `get_cap1_weight` 改 `get_cap1_reading` 的測試 import：這是 product 上的 fix，我的分支沒有，所以我沒有動。合併時由你處理。
- 沒讀 `.env`，沒碰 `data/*.db`，沒寫入任何祕密。

## 下一步

1. **qa-e2e**：執行修訂版 FE-T12，重點是這一輪沒有演練過的行為。
   - 送出中按返回，POST 用延遲 mock，回來時橫幅出現且只捲一次。
   - 第一次還在飛行時從新頁面再送一次：POST 恰好 2 筆，橫幅是最後到達的那份，沒有 pageerror。
   - 第一份回執到達時第二個對話框正開著：對話框不關閉，捲動延到關閉之後。
   - 對話框關閉時焦點歸還與緊接著的捲動，不會讓焦點落到 `<body>`。
   - AC-62～AC-64。
2. **風控／PM**（tech-architect 列出的兩項殘留）：
   - 送出中離開頁面、之後請求失敗，失敗不會顯示在任何地方，是否需要揭露。
   - 出清 mutation 的 `networkMode`（離線時暫停、恢復連線後自動送出）。
   - 這兩項我沒有動，也沒有新字面。
3. **tech-writer**：ADR-0037 落檔，狀態 proposed，待 CEO 核可。
4. **coordinator**：把本分支合進產品線時，會遇到的衝突在 product 線上的 `get_cap1_weight` → `get_cap1_reading` 測試 import；同時 `52e40da` 與 `132e0c6` 要一併合併。
5. **前一輪仍待辦（無變動）**：
   - 「我已閱讀，繼續」使用 `aria-disabled`，qa 腳本須查 `aria-disabled`。
   - 視覺規範 §7 要求在 `work/stock-desk-快市排程-視覺規範.md` 補註，我沒做。
   - FE-C23：本分支不得早於 N-166 上線。

分支：`origin/fix/stock-desk-exit-feedback`（HEAD `132e0c6`）。
主要檔案（`apps/stock-desk/frontend/app/` 下）：`lib/exitReceipt.ts`、`lib/exitReceiptStore.ts`、`lib/exitReceiptContext.tsx`、`lib/queries.ts`、`playbook/useEmergencyExitFlow.ts`；測試 `lib/__tests__/exitReceipt.test.ts`、`exitReceiptStore.test.ts`、`emergencyExitSettle.test.ts`、`playbook/__tests__/exitFlowStructure.test.ts`、`PlaybookPageRealFlow.test.ts`。

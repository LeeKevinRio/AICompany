# 出清畫面包 ADR-0037 補充一 S-1 實作

- 審查者：frontend-engineer
- 日期：2026-11-01
- 轉存：coordinator，逐字轉存 subagent 最終回報

---

## 本次結論

**ADR-0037 補充一 S-1 已實作：INV-1 成立，FE-C4 (a)～(g) 與 FE-T13(c1)～(c5) 都做完。完整 CI 全綠，已推送。**
- 分支：`origin/fix/stock-desk-exit-feedback`，HEAD `47f8ad9`，快轉推送，無 force。
- 工作樹與 node_modules 硬連結已移除，主 checkout 完好。
- FE-C24 依你的說明已符合，沒有改。
- 路 2 否決，沒有實作。

**有一件事要先講，qa-reviewer 看 commit 時會碰到：**
- `59232cf`（測試）排在 `47f8ad9`（來源）之前。`59232cf` 單獨看會缺 `47f8ad9` 才加入的 `reducer` 注入點，不能單獨通過測試。
- 這跟上一輪的 `52e40da` 是同一個疏忽。我沒有 rebase 重排，因為規則禁止。請整體審查，不要逐個 cherry-pick。

## 各部門回報

### frontend-engineer（本人）

**本輪 commit**

| commit | 內容 |
|---|---|
| `59232cf` test | store 寫入順序與訂閱者例外隔離的測試。 |
| `47f8ad9` fix | 不再吞例外；`accept()` 順序固定；FE-T13(c1)～(c5)。 |

**FE-C4 (a)～(g) 對照**

| 項 | 落點 | 測試 |
|---|---|---|
| (a) `onSuccess` 本體只有 `receipts.accept(response)`，無 try／catch／`.catch` | `lib/queries.ts` 的 `emergencyExitMutationOptions`。註解寫明吞例外會造成什麼畫面。 | `exitFlowStructure`：`onSuccess` 區段逐字比對只有一個語句，且不含 `try`、`catch`、`.catch(`、`Promise.reject`、async／await |
| (b) 順序：reducer → 提交 snapshot → 逐一通知，每個訂閱者各自 try/catch，例外交給注入的 `onSubscriberError`，預設 `void Promise.reject(e)` | `lib/exitReceiptStore.ts` 的 `dispatch`；`createExitReceiptStore(options)` 新增 `onSubscriberError`；另外在 handler 本身拋出時退到 `void Promise.reject`，不中斷其他訂閱者。`scrollHandled` 走同一條路徑，同樣隔離。 | `exitReceiptStore.test`：通知時 snapshot 已提交；一個訂閱者拋出不影響其他、不外漏、只回報一次；`scrollHandled` 同樣隔離 |
| (c) 第 2 步之前只有 reducer，不得加驗證、log、格式化 | `dispatch` 在 commit 之前只有 `const next = reduce(state, action); if (next === state) return;` | `exitFlowStructure` 把 commit 之前的內容逐字比對為這兩個語句 |
| (d) 定義層不碰 UI | 同現況，mutate 層只負責關對話框與釋放鎖 | `exitFlowStructure`：`onSuccess` 內無 `setIsOpen`、`lockRef`、focus、scroll |
| (e) 不在 render／effect／MutationCache config／`setMutationDefaults`／cache 訂閱寫回執 | 同現況 | `exitFlowStructure`（`.accept(` 只在 `queries.ts` 一處；全 app 無 `setMutationDefaults`、`new MutationCache`、`getMutationCache`） |
| (f) 不得用頁面旗標或比對 `receipt.seq` 決定關對話框或顯示失敗面板 | 未新增任何旗標；失敗面板條件仍是 `isError && step === "final"` | `exitFlowStructure`（失敗面板條件逐字） |
| (g) 失敗面板不呈現例外內容 | `ExitFailurePanel` 只收 `wording`；對話框與 flow 不傳遞 `error` | `exitFlowStructure`：對話框與面板不含 `error.message`、`.error`、`error={`、`ApiError`；page 不用 `flow.error` |

**FE-T13(c)**（`emergencyExitSettle.test.ts`，每次 mutate 都加 `.catch(noop)`，比照 `useMutation.ts:56`）
- **(c1) sink 拋出**：status `error`，`error` 就是拋出的例外；mutate 層 `onSuccess` 0 次、`onError` 與 `onSettled` 各 1 次；`cancelQueries`、`invalidateQueries` 各恰好 1 次且順序為 cancel 再 invalidate；沒有 unhandled rejection。
- **(c2) reducer 拋出**（真的 store，透過 `reducer` 注入點）：snapshot 與寫入前同一個參照，訂閱者 0 次通知，mutation 為 `error`。
- **(c3) 訂閱者拋出**（真的 store、兩個訂閱者）：`accept()` 正常返回，seq 為 1，response 是該次回應，第一個訂閱者 1 次、第二個訂閱者 1 次，`onSubscriberError` 恰好 1 次且參數是該例外，mutation 為 `success`，mutate 層 `onSuccess` 1 次、`onError` 0 次。另有 (c3b)：預設行為確實以 `void Promise.reject` 外拋，handler 自己拋出也不會中斷迴圈。
- **(c4) INV-1 矩陣**，情境為正常、c1、c2、c3、`mutationFn` reject：
  - 沒有「status 為 `success` 但 seq 沒前進」的組合；
  - status 為 `error` 時 `isError` 為 true，Step 3 的失敗面板條件成立，且沒有半寫入的回執（seq 沒變）。
- **(c5) 源碼掃描**：`onSuccess` 本體不含 try／catch；寫入路徑的順序、commit 之前只有 reducer 與 no-op 判斷、每個訂閱者呼叫包在 try/catch、`state = next` 只出現一次。
- (a)(b)(d) 沿用：卸載後仍寫入、寫入時 status 仍為 pending、失敗時 store 不變。FE-T14 沿用。

**變異驗證**：下列破壞各自讓對應測試失敗，之後已還原且 `git status` 乾淨。
- 在 `onSuccess` 吞例外：(c1)、(c2)、(c4) 與 FE-C4 掃描失敗。
- 先通知後提交：寫入順序掃描、FE-T13 (a)、FE-T14 失敗。
- 去掉每個訂閱者的 try/catch：(c3)、(c3b)、store 單元測試與掃描失敗。

**本輪沒有改的**
- `networkMode: "always"`（FE-C24、FE-R1）與 `emergencyExitOffline.test.ts` 沿用 `8493a82`、`69cd00d`，未動。

### 其他部門
本輪沒有其他部門參與。

## 驗證

**前端 CI**，在 HEAD `47f8ad9`：
```
npm run typecheck   tsc --noEmit，無輸出（通過）
npm test            Test Files 110 passed (110)；Tests 2852 passed (2852)
npm run build       ✓ Compiled successfully；├ ○ /playbook
```

**後端 CI**，在同一工作樹重跑（本輪後端沒有改動），`Popen(start_new_session=True)`，runner 有 `__main__` guard。原文在 `…/scratchpad/exitfb_ci/backend_ci_5.log`：
```
ruff check .                         All checks passed!
ruff format --check .                459 files already formatted
mypy app tests                       Success: no issues found in 453 source files
pytest --cov=app --cov-fail-under=90 Required test coverage of 90% reached. Total coverage: 97.44%
                                     8535 passed, 2 xfailed, 32 warnings in 863.14s (0:14:23)
```

**未驗證**
- 實機沒有重跑 smoke。這一輪的錯誤路徑（sink 或 reducer 拋出）無法在 production build 中注入，只在 node 環境用真的 `QueryClient`、`MutationObserver` 與真的 store 驗證。
- 「對話框不關、顯示 NB-6」是依 INV-1 與 `isError && step === "final"` 這兩個既有條件推得，並以矩陣測試確認條件成立。沒有在瀏覽器裡實際看過這一個畫面，這項請 qa-e2e 或 qa-reviewer 用注入手法驗。
- Firefox、WebKit 沒測。沒讀 `.env`，沒碰 `data/*.db`，沒寫入任何祕密。

## 下一步

1. **qa-reviewer**：整包審查。重點：
   - FE-C4 (b) 的提交順序（`lib/exitReceiptStore.ts` 的 `dispatch`）；
   - FE-C24 的四個禁用鍵與 `emergencyExitOffline.test.ts`；
   - FE-T13(c4) 的矩陣；
   - 前幾輪的送出中取消／Esc 鎖住、FE-C8 對照。
2. **coordinator／tech-writer**：補充一檔頭連結與 ADR-0037 的落檔。
   - 我沒有碰 `docs/adr/`。
   - 補充一提到的 CEO 知悉事項（改到 Decision 2 字樣是否要開 ADR-0038）由你轉。
3. **風控**：知悉 INV-1 與 FE-C4 (g)。
   - 前端內部錯誤（reducer bug）也會顯示成 NB-6。
   - 補充一 S-3 已記載：定義層 `onSettled` 在 success 路徑拋出時，橫幅與 NB-6 會同時在畫面上，兩者都為真。
4. **未完成，前幾輪遺留，無變動**：
   - 「我已閱讀，繼續」使用 `aria-disabled`，qa 腳本須查 `aria-disabled`。
   - 視覺規範 §7 要求在 `work/stock-desk-快市排程-視覺規範.md` 補註，我沒做。
   - FE-C23：本分支不得早於 N-166 上線；合併時 product 線上有 `get_cap1_weight` → `get_cap1_reading` 的測試 import 修正，由你處理。
   - 出清 POST 的用戶端逾時：補充一 S-4 列為另案，我沒有動。

分支：`origin/fix/stock-desk-exit-feedback`（HEAD `47f8ad9`）。
主要檔案（`apps/stock-desk/frontend/app/` 下）：`lib/exitReceiptStore.ts`、`lib/queries.ts`、`lib/__tests__/emergencyExitSettle.test.ts`、`lib/__tests__/exitReceiptStore.test.ts`、`playbook/__tests__/exitFlowStructure.test.ts`。

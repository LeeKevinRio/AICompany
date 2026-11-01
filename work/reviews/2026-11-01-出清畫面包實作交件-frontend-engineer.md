# 出清畫面包實作交件（NB-6 未接）

- 審查者：frontend-engineer
- 日期：2026-11-01
- 轉存：coordinator，逐字轉存 subagent 最終回報

---

## 本次結論

**整包完成約九成，但 NB-6 失敗字面還沒接上，所以這個分支目前不可上線、不可合併。**
- 原因：dev-lead 尚未在 N-166 分支加 NB-6 合併後版本（含 #87 修訂的第 3 句）。我做完時 `git fetch` 兩次，`origin/fix/stock-desk-exit-idempotency` 仍是 `7bf61ee`，沒有新 commit。依指示，我沒有自擬字面。
- 影響：對話框送出失敗時，目前仍用舊的紅色共用 `ErrorPanel`，標籤是「全部出清送出失敗」，還會附後端訊息。這違反風控必改項 9、10 的 NB-6 部分，也違反必改項 11 的「FR-8b 字面不得晚於 FR-8a 上線」。FR-8a（失敗也重新取得 `/today`）已經做了。
- 出清失敗面板元件（`ExitFailurePanel`）和標籤行捲入邏輯已完成並有測試，只差接字面。

已推送：`origin fix/stock-desk-exit-feedback`，從 N-166 的 `7bf61ee` 長出來，共 7 個 commit。沒有碰 N-166 分支，沒有碰 `product/stock-desk`，沒有 force push。工作樹與 node_modules 硬連結已移除，主 checkout 的 node_modules 完好。

等 dev-lead push 後的接線步驟（約半小時）：
1. `git fetch`，再 `git merge origin/fix/stock-desk-exit-idempotency`（不 rebase）。
2. 在 `app/lib/playbookView.ts` 鏡射標籤與三句內文，型別是 `ExitFailureWording`。
3. 在 `app/lib/__tests__/exitWordingMirror.test.ts` 加守門測試，讀 `wording.py` 逐字比對，並另外逐字斷言第 3 句修訂版。
4. 在 `EmergencyExitDialog.tsx` 把 `<ErrorPanel …/>` 換成 `<ExitFailurePanel wording={…} scrollContainerRef={scrollRef}/>`，`scrollRef` 已備好。
5. 重跑 CI。

另一件小事：視覺規範 §7 要求實作後在 `work/stock-desk-快市排程-視覺規範.md` 的 §2.4、§4.4 補註。我只改了 `apps/stock-desk/`，這件沒做。

## 各部門回報

### frontend-engineer（本人）

**Commit 清單**（均帶兩行 trailer）

| commit | 內容 |
|---|---|
| `ac8dbcd` fix | 後端 `wording.py`：`EXIT_CONFIRM_FREEZE_DEGRADED` 改為 Q8 1b 修訂字面，註解同步。新增 `EXIT_CONFIRM_CHECKS_UPDATED`（N1）。測試：修訂字面逐字、降級與正式清單只差第 2 句、N1 逐字與禁用詞。 |
| `3a733a8` feat | 前端鏡射降級句與 N1。守門測試直接讀 `wording.py` 的常數逐字比對，並 grep 確認舊句「兩者於送出後的執行結果中顯示」不存在於任何前端原始檔。 |
| `876b76d` fix | `useEmergencyExit` 改成 `onSettled`，先 `cancelQueries` 再 `invalidateQueries`，兩者都不 await、不回傳 promise（FE-C13）。測試 FE-T6、FE-T7。 |
| `dcf1d1b` feat | 純函式：回執 reducer、R-1～R-6 換句規則、台北日界、焦點交接判斷。測試 FE-T1、T2、T3、T8、T9、T10、T11。 |
| `bf7384a` refactor | 出清流程提升到頁面層：`EmergencyExitControl` 拆成三個單元。狀態列改不透明 `bg-black`。 |
| `2f60ccf` test | 頁面四種 `/today` 狀態的結構測試（FE-T4）與架構守門（FE-T5）。 |
| `bbd823e` feat | `ExitFailurePanel` 元件與標籤行捲入邏輯。字面尚未接。 |

**待裁項，照預設實作，已標明**
- **Q15**：離開 `/playbook` 再回來視同重新整理，採方案 A。回執在頁面元件記憶體內，離開頁面即結束，沒有任何持久化。
- **FE-C18 heldAt 更新規則**：照 TA 前提 3 實作。成功取得且逐句相同時，`heldAt` 更新為新的 `dataUpdatedAt`。
  - 同樣待風控確認：送出前同步檢查到 R-4 成立、而且確認過的是正式句時，這次點擊改為 R-5 退步，不送出（PRD Q16）。
- **FE-C20 焦點交接**：照 TA 的三條件實作，限定在 `preventScroll`。待 PM 補 FR-13g。

**需要你知道的實作決定與偏離**
1. 「我已閱讀，繼續」由原生 `disabled` 改成 `aria-disabled`，點擊時由 handler 擋下。
   - 理由：R-3 換句可能在使用者焦點正好停在這顆鈕時把它關掉。原生 `disabled` 會把焦點丟到 `<body>`，違反 AC-46 的「activeElement 沒有被搬動」。
   - 與 N-163 對 Step 3 兩顆鈕的處理一致。
   - qa 腳本若以 `disabled` 屬性判斷這顆鈕，要改查 `aria-disabled`。
2. 兩步共用同一個 `<h2>` 節點，因為 N1 的 `role="status"` 容器（V-43）要在標題下方、且跨步驟是同一個節點。
3. FR-3 捲動多做了一層修正（必改項 12）：`scrollIntoView` 之後若橫幅第一行仍被狀態列蓋住，用實測的狀態列下緣再補捲。快市啟動情境的 V-9 仍須 qa-e2e 實測。
4. 橫幅不渲染 `pending_directives`。該型別已存在，訊息本身已含日期，也沒有規格要求渲染；若日後要渲染，必須全部列出，並先送風控。
5. 測試與字面掃描清單跟進：`Cap1DisclosureBlock.test.ts`、`componentWordingScan.test.ts`（舊檔換成新的五個檔）、`EmergencyExitPortal.test.ts`（改掃新結構）。

**UI 自檢清單（ui-delivery-checklist）**
- 第 1、5、6 節：通過。無新增色值、無假資料。
- 2.6：「我已閱讀，繼續」的 disabled 三通道齊備（`aria-disabled`、opacity、`cursor-not-allowed`）。
- 3.2：觸發鈕 class 照視覺規範 V-35 與 success 時逐字相同，未加 `whitespace-nowrap`，屬規範白名單。

### 對照表

路徑省略 `apps/stock-desk/frontend/app/`。「flow」=`playbook/useEmergencyExitFlow.ts`，「dialog」=`playbook/EmergencyExitDialog.tsx`，「state」=`lib/exitDialogState.ts`，「receipt」=`lib/exitReceipt.ts`。

**FE-C1～C20**

| 項 | 落點 | 測試 |
|---|---|---|
| C1 回執 state 只在頁面層 | flow 的 `useReducer(exitReceiptReducer, null)` | `exitFlowStructure`「only one receipt reducer」；`exitReceipt` |
| C2 action 只有 accepted、無清除 | receipt 的 reducer | `exitReceipt`（`@ts-expect-error` 驗證沒有 clear、source 只有一個 `type:`） |
| C3 橫幅不由 mutation 推導 | `playbook/ExitReceiptBanner.tsx` 只吃 receipt | `exitFlowStructure`（grep 無 `mutation.data`、`useMutationState`） |
| C4 只在 mutate 層級 onSuccess dispatch | flow 的 `submit` | `exitFlowStructure`（`dispatchReceipt` 只有一處且在 onSuccess） |
| C5 不持久化 | 全部 exit 檔案 | `exitFlowStructure`（無 storage、cookie、history.state 等） |
| C6 role=status 無條件、無 class、無 key | `playbook/page.tsx` | `PlaybookPageStates`（四態各 1 個且緊接 h1 列）；`exitFlowStructure` |
| C7 隱藏判斷為純函式，與閘門同一次 render | `receipt` 的 `isReceiptModeReasonHidden`，page 呼叫 | `exitReceipt`（真值表）；`PlaybookPageStates`（逐字、空白差異、非 success 一律保留） |
| C8 捲動依賴只有 seq | flow 的 effect `[receiptSeq]` | `exitReceipt`；`exitFlowStructure`（deps 掃描、`lastHandledSeq` 初始值） |
| C9 reset 只在打開時；失敗面板 `isError && step==="final"` | flow 的 `open()`、dialog 的 `showFailure` | `exitFlowStructure` |
| C10 observer、isOpen、鎖、ref 在頁面層；ModeStatusBar 不 import 對話框 | flow、page | `exitFlowStructure`；`EmergencyExitPortal` |
| C11 對話框只依 isOpen 掛載 | page 的 `{flow.isOpen && (…)}` | `EmergencyExitPortal`；`PlaybookPageStates` |
| C12 觸發鈕兩處同一判斷式、共用 ref | page、`playbook/ExitTriggerButton.tsx` | `PlaybookPageStates`；`exitFlowStructure` |
| C13 先 cancel 再 invalidate，不 await | `lib/queries.ts` 的 `emergencyExitMutationOptions` | `emergencyExitSettle`（FE-T7）；`queryContract`（FE-T6 d） |
| C14 R-1 開啟時決定，存於對話框 state | state 的 `createExitDialogState`；page 的 `exitToday` | `exitDialogState`；`exitFlowStructure`（`exit_confirm` 只經 isSuccess） |
| C15 純 reducer，刪 render 內比對 | state 的 `exitDialogReducer` | `exitDialogState`；`exitFlowStructure`（無 `setChecks`、無 render 比對） |
| C16 layout effect，deps 四項，第一行讀鎖 | dialog 的 `useLayoutEffect` | `exitFlowStructure`（deps 與首行逐字）；`exitDialogState`（鎖住時同一參照） |
| C17 submit 順序：鎖判斷、R-4、取鎖、mutate | dialog 的 `submit` → `planSubmit`，flow 的 `submit` | `EmergencyExitPortal`；`exitDialogState`（planSubmit） |
| C18 R-4 評估時機與 heldAt | state 的 `isExitChecksStale`；dialog 的計時器、visibilitychange、focus、continue 與 submit 同步檢查 | `exitDialogState`；`taipeiDay`（FE-T9） |
| C19 關閉焦點歸還帶 preventScroll | flow 的 effect | `EmergencyExitPortal`；`exitFlowStructure`（所有 `.focus(` 均帶 preventScroll） |
| C20 換位焦點交接三條件 | `lib/exitFocus.ts`；`ExitTriggerButton` 的 layout effect | `exitFocus`（FE-T11 真值表） |

**FE-1～FE-8**

| 項 | 落點 | 測試 |
|---|---|---|
| FE-1 方案 B | page 的 h1 列 | `PlaybookPageStates`（V-33 結構、非 success 無 sticky） |
| FE-2 隱藏條件只綁 `today.isSuccess` | page | `exitFlowStructure`（呼叫第一參數為 `today.isSuccess`，不含 trigger 等） |
| FE-3 生命週期 | `receipt`、flow | `exitReceipt`；`exitFlowStructure` |
| FE-4 每份新回執至多捲一次 | flow | `exitReceipt`；`exitFlowStructure` |
| FE-5 焦點回歸 preventScroll | flow | 同 C19 |
| FE-6 N1 | dialog 的 `role=status` 容器；`playbookView.ts` 鏡射 | `exitDialogState`（R-6 條件）；`exitWordingMirror` |
| FE-7 失敗面板 | `playbook/ExitFailurePanel.tsx`、`lib/exitFailureReveal.ts` | `ExitFailurePanel`；`exitFailureReveal`。**字面未接。** |
| FE-8 後備觸發鈕無新字面 | `ExitTriggerButton` | `PlaybookPageStates`（四態皆無 aria-*、title、disabled、彩色） |

**F-1～F-10**

| 項 | 落點 | 測試 |
|---|---|---|
| F-1 | page 的 `exitToday` | `exitFlowStructure`（無 `data?.exit_confirm`）；`exitDialogState`（錯誤狀態帶舊 block 也不採用） |
| F-2 | state 的 `replaceChecks` | `exitDialogState`（R-2、R-3、AC-46～48、AC-53） |
| F-3 | `playbookView.ts` | `exitWordingMirror` |
| F-4、F-5、F-8 | `ExitTriggerButton`、page | `PlaybookPageStates` |
| F-6 | page | `exitFlowStructure` |
| F-7 | flow、`ExitTriggerButton` | `exitFlowStructure`；實機行為交 qa-e2e |
| F-9 | state 的 `confirmedSource` | `exitDialogState`（AC-49、AC-50、AC-54） |
| F-10 | `playbookView.ts`、`wording.py` | `exitWordingMirror`、`test_playbook_wording.py` |

**風控必改項 1～12**

| 項 | 狀態與落點 | 測試 |
|---|---|---|
| 1、2 橫幅與對話框撐過 `/today` 失敗 | 完成。flow、dialog | `PlaybookPageStates`、`exitFlowStructure`；實機見下方 S2、S4 |
| 3 失敗不得用舊資料渲染狀態列 | 完成。page 維持 `isSuccess` 閘門 | `PlaybookPageStates`（有資料的 error 態不見模式標籤） |
| 4 隱藏條件 | 完成 | 同 C7 |
| 5 移除即卸載 | 完成 | `PlaybookPageStates`（無 sr-only、aria-hidden、min-h） |
| 6、7 橫幅內部與頁面其他區塊 | 完成。`ExitReceiptBanner`，其餘區塊沒動 | `PlaybookPageStates`（順序） |
| 8 狀態列 `bg-black` | 完成。`ModeStatusBar` | `exitFlowStructure` |
| 9 NB-6 面板 | **元件完成，字面未接** | `ExitFailurePanel` |
| 10 字面單一來源與守門 | 降級句與 N1 完成。**NB-6 四段未做** | `exitWordingMirror`（已做變異驗證） |
| 11 `onSettled` | 完成。**與 NB-6 字面同包上線的條件未達成** | `emergencyExitSettle` |
| 12 FR-3 捲動 | 程式完成。快市 V-9 阻擋條件待 qa-e2e | `exitReceipt` |

### 其他部門
本次沒有其他部門參與。

## 驗證

**後端 CI**，在 `ac8dbcd` 上以 `Popen(start_new_session=True)` 跑，runner 有 `if __name__ == "__main__":` guard。之後的 commit 只動前端檔案，所以沒有重跑。
```
ruff check .                  All checks passed!
ruff format --check .         457 files already formatted
mypy app tests                Success: no issues found in 451 source files
pytest --cov=app --cov-fail-under=90
                              Required test coverage of 90% reached. Total coverage: 97.44%
                              8500 passed, 2 xfailed, 32 warnings in 789.96s (0:13:09)
```
原文在 `/tmp/claude-0/-home-user-AICompany/3f76d891-50d3-55e1-b39d-925b8a90241a/scratchpad/exitfb_ci/backend_ci_1.log`。

**前端 CI**，在最終 HEAD `bbd823e` 上：
```
npm run typecheck   tsc --noEmit，無輸出（通過）
npm test            Test Files 107 passed (107)；Tests 2779 passed (2779)
npm run build       ✓ Compiled successfully；Generating static pages (8/8)；├ ○ /playbook
```

**變異驗證**：暫時破壞下列項目，對應守門測試都會失敗，之後已還原且 `git status` 乾淨。
- 鏡射字面被改一個字。
- 頁面改用 `today.data?.exit_confirm`。
- 捲動 effect 多加依賴。
- 換句時不清勾選。
- 移除 `cancelQueries`。
- 第 3 步確認降級句也退步。

**實機 smoke**（不是驗收結論；驗收仍由 qa-e2e 執行）：Chromium 跑 production build，所有 `/api/playbook/*` 都在 context 層級 mock，沒有任何請求到後端。腳本與輸出在 scratchpad `exitfb_ci/smoke.js`、`smoke_out.json`。
- **S1**：success 下走完三步送出，對話框關閉，焦點回到狀態列內的觸發鈕。橫幅出現，`/today` 重新取得後橫幅的 `mode_reason` 被卸載，整頁該句恰 1 次，在狀態列。
- **S2**：出清成功後重新取得 `/today` 失敗，狀態列卸載。橫幅保有 `mode_reason`；觸發鈕換到 h1 列且恰 1 個，焦點交接成功（落在 h1 列的鈕，不在 body）；沒有 sticky 元素。
- **S3**：`/today` 載入中開對話框，顯示修訂降級句。全部勾選後 `/today` 回來，只有第 2 句被換成正式句並清掉勾選，其餘勾選保留，N1 出現，「繼續」為 `aria-disabled`，焦點仍在 input。
- **S4**：第 3 步送出 500，且 `/today` 重新取得也失敗。對話框仍在，失敗面板（目前是舊 ErrorPanel）在，「確認送出全部出清」可再按，焦點仍在該鈕。
- **S5**（375 寬）：第 2 步，背景重新取得失敗。勾選與句子都不變，無 N1，對話框保持開啟。
- **S6**（假時鐘 23:00 台北，快轉 2 小時）：R-4 計時器觸發，換成降級句，只清第 2 句，N1 出現。
- **S7**：第 3 步確認正式句後時鐘跳過午夜再按送出：退回第 2 步，`POST` 為 0 筆，N1 出現。
- 全程 `pageerrors` 為空，console 只有 mock 的 500。

**未驗證**
- 只用 Chromium 驗過；Firefox、WebKit 沒測。
- 焦點交接依賴 React 的 commit 順序（TA 已註明），仍需 qa-e2e 在三家瀏覽器實測。
- qa-e2e 的 FE-T12 全數未做：`role=status` 節點恆等、`scrollY` 差為 0、AC-55 延遲 mock、AC-60 三條序列、V-34 位移實測、快市 V-9。
- visibilitychange 與 window focus 兩個 R-4 評估時機，只有程式碼與靜態掃描，沒有實機演練。
- 沒讀 `.env`，沒碰 `data/*.db`，沒寫入任何祕密。

## 下一步

1. **dev-lead**：在 N-166 分支加 NB-6 合併後版本（標籤加三句，第 3 句用 #87 修訂版）並 push，通知我。我接著做上面「本次結論」的接線五步。若 N-166 也修改了 `wording.py`，我的 `ac8dbcd` 與它在同一檔，merge 時可能要處理衝突。
2. **風控**：確認 FE-C18（成功取得且逐句相同時更新 `heldAt`），以及 Q16（送出前同步檢查到 R-4，把點擊轉為退步）。
3. **PM**：補 FR-13g，承接焦點交接（FE-C20）。
4. **qa-reviewer**：請特別看「我已閱讀，繼續」改 `aria-disabled` 的決定，以及 `useLayoutEffect` 依賴刻意只列四項（repo 沒有 eslint 規則會擋）。
5. **qa-e2e**：執行 FE-T12。對照 V-12、V-38(c)，加做「關閉後 `/today` 才恢復」情境。
6. **tech-writer**：ADR-0036 落檔。我沒有碰 `docs/adr/`。
7. 另外：主 checkout 的 `work/prd/2026-10-29-出清後回饋畫面-N164N165.md` 有未提交的修改，不是我改的，應是 PM 還在編輯。

分支：`origin/fix/stock-desk-exit-feedback`（HEAD `bbd823e`）。
主要檔案（`apps/stock-desk/` 下）：
- 後端：`backend/app/playbook/wording.py`、`backend/tests/test_playbook_wording.py`
- 前端元件：`frontend/app/playbook/page.tsx`、`useEmergencyExitFlow.ts`、`EmergencyExitDialog.tsx`、`ExitTriggerButton.tsx`、`ExitReceiptBanner.tsx`、`ExitFailurePanel.tsx`、`ModeStatusBar.tsx`
- 前端純函式：`frontend/app/lib/exitReceipt.ts`、`exitDialogState.ts`、`taipeiDay.ts`、`exitFocus.ts`、`exitFailureReveal.ts`、`queries.ts`、`playbookView.ts`

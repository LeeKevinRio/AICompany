# 出清畫面包：NB-6 接線與 Q15 方案 D

- 審查者：frontend-engineer
- 日期：2026-11-01
- 轉存：coordinator，逐字轉存 subagent 最終回報

---

## 本次結論

**NB-6 與風控 2026-11-01 的 FE-1～FE-8 都已做完並推送。上一輪的阻擋點（NB-6 字面未接）已解除，CI 全綠。**

分支 `origin/fix/stock-desk-exit-feedback`，HEAD `04baf82`，快轉推送，沒有 force。工作樹與 node_modules 硬連結已移除，主 checkout 完好。

- **merge**：`git merge origin/fix/stock-desk-exit-idempotency`（HEAD `36c7ceb`）無衝突，沒有 rebase，`wording.py` 沒有任何字被改。
- **NB-6**：dev-lead 只加了第 3 段 `EXIT_RESULT_UNCONFIRMED_RETRY`，內容與風控 #87 修訂版逐字相同。標籤、第 1 句、第 2 句我依你的授權補進 `wording.py`（逐字取自風控 2026-10-31「N-166 已知限制與 NB-6 合併後字面」第 3 項）。命名沿用既有常數：
  - `EXIT_RESULT_UNCONFIRMED_LABEL`
  - `EXIT_RESULT_UNCONFIRMED_STATES`
  - `EXIT_RESULT_UNCONFIRMED_BADGE`
- **Q15 改採方案 D**：回執移到 Providers 範圍的記憶體 store，不是 module singleton，不持久化。
- **FE-2 的寫法是我自己選的，待 tech-architect 確認**（見各部門回報）。
- 其餘未完成或待裁項見「下一步」。

## 各部門回報

### frontend-engineer（本人）

**本輪 commit（前一輪的 7 個 commit 不變）**

| commit | 內容 |
|---|---|
| `6c4f581` | merge N-166 `36c7ceb`，無衝突 |
| `ecb4428` feat | 後端補 NB-6 的標籤、第 1 句、第 2 句常數，逐字照抄。測試逐字釘住，並確認不含「安全／放心／未確認／請關閉／視窗」，也不含合併前的「只暫停了」。 |
| `74f2513` fix | 風控 FE-5、FE-6、FE-8：`heldAt` 更新條件，焦點旗標抽成純函式，加測試。 |
| `0c8b3f2` feat | NB-6 前端鏡射與失敗面板接線。`EXIT_FAILURE_WORDING` 鏡射四段，對話框失敗時改用 `ExitFailurePanel`，不再附後端訊息。守門測試讀 `wording.py` 逐字比對。 |
| `04baf82` refactor | 風控 FE-1～FE-4（Q15 方案 D）：回執 store、hook 層寫入、捲動標記放 store。 |

**風控 2026-11-01 的 FE-1～FE-8 對照**

| 項 | 落點 | 測試 |
|---|---|---|
| FE-1 Providers 範圍 store | `lib/exitReceiptStore.ts` 只放 `{seq, response}` 與已捲過標記，沿用 append-only reducer。`lib/exitReceiptContext.tsx` 的 `ExitReceiptStoreProvider` 用 `useState(() => createExitReceiptStore())` 建立。`providers.tsx` 包住所有路由。不持久化，新文件載入即清空。 | `exitReceiptStore.test`（兩個 store 獨立）；`exitFlowStructure`（無頂層實例、context 內 `useState`、store 不含 `exit_confirm`、鎖、mutation）；VETO-3 的持久化掃描涵蓋新檔 |
| FE-2 頁面卸載後回執仍寫入 | 見下方「FE-2 的寫法」 | `emergencyExitSettle`（無 listener 時 hook 層 `onSuccess` 仍寫入；失敗不寫入；第二份取代第一份）；`exitFlowStructure`（`receiptStore.accept` 只在 hook 層一處） |
| FE-3 已捲標記放在 store | `useEmergencyExitFlow.ts` 的捲動 effect 依賴只有 `[receiptSeq]`，執行當下讀 `store.getScrolledSeq()`，捲動前 `markScrolled`。標記不通知、不改 snapshot。 | `exitReceiptStore.test`（跨頁面實例：看過的不再捲；不在頁面時到達的回來捲一次；無回執不捲）；`exitFlowStructure` |
| FE-4 只在 `/playbook` 渲染 | `ExitReceiptBanner` 只由 `page.tsx` 渲染 | `exitFlowStructure`（掃全 app，使用者清單固定） |
| FE-5 `heldAt` | `lib/exitDialogState.ts`。更新條件：success、`dataUpdatedAt > heldAt`、持有正式句、與 R-3 同一個比較（句數也要同）、鎖未取得。同一次評估先處理新資料，再用更新後的 `heldAt` 評估 R-4。error 與重試等待不更新。計時器依賴 `[heldAt, tick]`，新 `heldAt` 會重設午夜計時。 | `exitDialogState.test` 新增：跨日後新取得內容相同（更新、無 N1、第 3 步不退步）；順序顛倒的反例（顛倒會出 N1，單次評估不會）；等於或較舊的 `dataUpdatedAt` 不動；降級句不動；鎖住不動；句數不同算變動 |
| FE-6 送出前 R-4 | `planSubmit`／`planAdvance`。第 3 步改走退步，第 2 步「繼續」原地換句不前進。點擊被消耗，`POST` 0 筆。不呼叫 `mutation.reset()`。 | `exitDialogState.test`：退步、重新勾選後下一次點擊 `submit` 恰好一次，第二次點擊被鎖擋下；第 2 步原地換句。`exitFlowStructure`：`reset()` 只在 `open()` 一處 |
| FE-7 先 cancel 再 invalidate | `queries.ts` 的 `emergencyExitMutationOptions.onSettled` | `queryContract`（FE-T6 d）；`emergencyExitSettle`（FE-T7） |
| FE-8 焦點交接 | `lib/exitFocus.ts` 的 `recordTriggerUnmount`／`consumeTriggerMount`。每次卸載覆寫旗標，每次掛載消耗（不論有沒有交接）。只呼叫一次 `focus({preventScroll:true})`，沒有 rAF 或計時器。關閉時若觸發鈕已持有焦點就不再移動，避免同一次 commit 搬兩次。 | `exitFocus.test` 殘留旗標真值表；`exitFlowStructure`（所有 `.focus(` 都帶 `preventScroll`） |

**FE-2 的寫法（待 tech-architect 確認）**
- 回執改由 `useEmergencyExit` 的**hook 層 `onSuccess`** 寫進 store。hook 層 callback 屬於 mutation 本身，不依賴 observer 是否還訂閱。
- 閉包只捕獲 Providers 範圍的 store，所以頁面已卸載（例如送出中按瀏覽器返回）回應才到，回執仍會寫入，回來時從 store 讀到。
- 頁面的 mutate 層 `onSuccess` 只負責關對話框，不碰 store。測試證實：沒有 listener 時 mutate 層 callback 不執行，hook 層仍執行。
- 同一個 hook 層的 `onSettled`（cancel 再 invalidate）也會在卸載後執行。
- 殘留風險：送出中離開再回來，新頁面實例的鎖是 false，使用者可再送一次。這是風控列給 tech-architect 的 info，依 EX-2 不擋。

**其他要知道的事**
- 失敗面板 `ExitFailurePanel` 的視覺、結構與捲入邏輯沿用上一輪，沒有改動。
- 主 checkout 的 PRD 檔案之前有未提交修改，我沒有碰。

### 其他部門
本次沒有其他部門參與。

## 驗證

**後端 CI**，在 `ecb4428` 上以 `Popen(start_new_session=True)` 跑，runner 有 `if __name__ == "__main__":` guard。之後的 commit 只動前端。原文在 `…/scratchpad/exitfb_ci/backend_ci_2.log`。
```
ruff check .                         All checks passed!
ruff format --check .                459 files already formatted
mypy app tests                       Success: no issues found in 453 source files
pytest --cov=app --cov-fail-under=90 Required test coverage of 90% reached. Total coverage: 97.44%
                                     8535 passed, 2 xfailed, 32 warnings in 763.78s (0:12:43)
```

**前端 CI**，在最終 HEAD `04baf82` 上：
```
npm run typecheck   tsc --noEmit，無輸出（通過）
npm test            Test Files 108 passed (108)；Tests 2816 passed (2816)
npm run build       ✓ Compiled successfully；├ ○ /playbook
```

**變異驗證**
- 移除 hook 層 `accept`：4 個測試失敗。
- `heldAt` 的 `>` 改成 `!==`：1 個失敗。
- 移除 `markScrolled`：1 個失敗。
- 旗標不消耗：3 個失敗。
- 以上都已還原，工作樹乾淨。

**實機 smoke**（Chromium、production build、所有 `/api/playbook/*` 都在 context 層級 mock；不是驗收結論）
- S1～S7 沿用上一輪結果，在新架構上重跑一次：行為一致，`pageerrors` 為空。
- **S8（Q15 方案 D 與 FE-2）**：從 `/positions` 以 SPA 導覽進排程台，走完三步送出，POST 延遲 1.5 秒。送出中按返回回到 `/positions`，回應在不在排程台時到達。
  - 返回排程台後：橫幅在，是同一份回執。
  - 此時 `/today` 重新取得已失敗、狀態列不在，橫幅保有 `mode_reason`，整頁該句 1 次。
  - 再離開再回來：橫幅逐字相同。
- **S9（375×667）**：送出 500 後失敗面板為標籤加三段共 4 個 `<p>`，字面與風控定稿相同，class 為 `border-neutral-500`，沒有附後端訊息。標籤行完整落在對話框可視範圍內，焦點仍在「確認送出全部出清」。
- 腳本與輸出在 scratchpad `exitfb_ci/smoke.js`、`smoke_out2.json`。

**未驗證**
- S8 沒有量測「看過的回執回來不再捲動」的 `scrollY`，只驗了橫幅內容；捲動次數由 `exitReceiptStore.test` 的模擬覆蓋。
- Firefox、WebKit 沒測。
- qa-e2e 的 FE-T12 全數未做：節點恆等、三種 `/today` 狀態的逐 frame 取樣、AC-55 延遲 mock、AC-60、AC-62～AC-64、快市 V-9。
- 沒讀 `.env`，沒碰 `data/*.db`，沒寫入任何祕密。

## 下一步

**仍未完成或待裁**
1. **FE-2 寫法**：待 tech-architect 確認 hook 層 `onSuccess` 是否為認可的寫法。若認為要改，改動範圍只在 `queries.ts` 的 `emergencyExitMutationOptions`。
2. **FR-13g**：焦點交接仍待 PM 以 FR-13g 承接。風控已 CONDITIONAL APPROVE，Chromium 上失效即判 AC-62 不通過，需 qa-e2e 實測。
3. **前一輪已知項目，沒有變動**：
   - 「我已閱讀，繼續」使用 `aria-disabled`，不是原生 `disabled`；qa 腳本須查 `aria-disabled`。
   - 視覺規範 §7 要求在 `work/stock-desk-快市排程-視覺規範.md` 補註。我只改了 `apps/stock-desk/`，這件沒做。
4. **N-166 合併順序**：本分支含 N-166 的 `36c7ceb`，上線前提是 N-166 先合併。NB-6 字面與 FR-8a 已在同一分支，必改項 11 的「同包上線」條件現在成立。
5. **ADR-0036**：Decision 1 應改為 D 版，依風控與 tech-architect 的修訂由 tech-writer 落檔。我沒有碰 `docs/adr/`。
6. **qa-reviewer**：請特別看
   - FE-2 的 hook 層寫法。
   - 失敗面板不再使用共用 `ErrorPanel`，但該檔案本身沒有改動。
   - 單一 commit 有輕微混合：`04baf82` 內含 store、hook 層寫入與捲動標記三件事，它們互相依賴，拆開無法各自通過型別檢查。

分支：`origin/fix/stock-desk-exit-feedback`（HEAD `04baf82`）。
主要檔案（`apps/stock-desk/` 下）：
- 後端：`backend/app/playbook/wording.py`、`backend/tests/test_playbook_wording.py`
- 前端 store：`frontend/app/lib/exitReceiptStore.ts`、`exitReceiptContext.tsx`、`frontend/app/providers.tsx`
- 前端流程：`frontend/app/lib/queries.ts`、`exitDialogState.ts`、`exitFocus.ts`、`playbookView.ts`、`frontend/app/playbook/useEmergencyExitFlow.ts`、`EmergencyExitDialog.tsx`、`ExitTriggerButton.tsx`、`ExitFailurePanel.tsx`、`page.tsx`

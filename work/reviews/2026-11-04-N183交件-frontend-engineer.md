# N-183 補償捲動小修交件（395fa8c）

- 審查者：frontend-engineer
- 日期：2026-11-04
- 轉存：coordinator，逐字轉存 subagent 最終回報

---

## 本次結論
N-183 四項都做完，已 push 到 `fix/stock-desk-receipt-compensation-n183`，基底是 `origin/product/stock-desk`（6d994e3）。worktree 已移除，沒有 merge 進 product，沒有 rebase 或 force push。
- 行為只改第 1 點，沒有動任何 JSX、class、字面或色值。
- f3 疑點判斷不是 bug，不列解讀點。依據是程式碼加上 qa 報告的數字，我沒有開瀏覽器實測。
- 遠端 CI 我沒查。

## 各部門回報

### 條款對照
1. paused 不再當 refetch 結束：
   - `app/lib/receiptCompensation.ts` 新增純函式 `fetchStatusSignal(status)`。fetching 回 true，idle 回 false，paused 回 null。
   - `app/playbook/useReceiptCompensation.ts` 的 effect 遇到 null 就直接 return，所以 `fetchingRef` 和 controller 都維持原狀。
   - 這樣 `paused` 時 phase 仍是 `waiting`，連線恢復後真正的 fetching → idle 才進 stabilize 並判定。
   - 我另外抽出純函式，是因為專案的測試是純 Node 的 vitest，hook 本身不好直接測。
2. 補行為測試，在 `app/lib/__tests__/receiptCompensation.test.ts` 新增一個 describe：
   - (a) fetching → paused 不判定，也沒有 scrollBy，phase 維持 waiting。接著 fetching → idle 才補償一次，量到 `160-(277+16)`。
   - (a) arm 時 refetch 已在進行中，之後 paused 仍不判定，idle 才判定。
   - (b) arm 之前 refetch 已 fetching → idle 結束：不判定、phase 維持 waiting，再來一次 idle 也不判定，要等下一次 fetching → idle 才補償。註解寫明這是交件解讀點 4 的已知限制，並說明這個測試只鎖住現況，要改須連同規格一起改。
3. `exitFlowStructure.test.ts` 的 lib 與 hook 結構測試：
   - 對 `receiptCompensation.ts` 和 `useReceiptCompensation.ts` 各自擋 `innerHeight|visualViewport|clientHeight`，並保留對 `OVER_HALF` 的檢查。
   - 手動捲動偵測：hook 的檢查加了 `onscroll`（不分大小寫），lib 也加了。
   - 另外加了兩條防回退：hook 必須使用 `fetchStatusSignal(fetchStatus)`，且不得再出現 `fetchStatus ===`。
4. f3 疑點：下一節。

補償的其他邏輯完全沒動，仍符合 PRD v5.5c FR-3 與規範 r3.5a §4.2：觸發 `top < barBottom+12`，目標 `barBottom+16`，同步點 2 個 frame 且上限 60，每份回執額度 1 次，手動捲動只看輸入事件。

### f3 疑點結論：不是 bug
- 事實：T0 之後程式捲動 0 次，文件高度從 3721 縮到 850（錯誤版面取代頁面），狀態列已卸載。
- 375×667 的 maxScroll 是 183，`scrollY` 從 150 變 63，沒有碰到 maxScroll，所以不是瀏覽器的鉗制。
- 差值 150−63=87，剛好等於狀態列常態高度 87px（V-9 的 87→127）。
- 原因判斷：狀態列是 `sticky top-0`，仍佔文件流（`ModeStatusBar.tsx:47`）。它卸載後，錨點上方的內容少了 87px，瀏覽器的 scroll anchoring 為了保持視覺位置，把 `scrollY` 減了 87。
- 交叉驗證，三個寬度都吻合：
  - 375×812：150−87=63，被 maxScroll=38 鉗制，所以是 38。
  - 1280×900：104−87=17，被 maxScroll=0 鉗制，所以是 0。
  - 375×667：63 不超過 183，不被鉗制，所以是 63。
- 產品碼裡會捲動的呼叫點只有以下幾處，補償的呼叫在 `barBottom===null` 時回 0，所以 f3 路徑上不會呼叫：
  - `useEmergencyExitFlow.ts` 的首捲（`scrollIntoView` 加 `scrollBy` 微調）；
  - 補償用的 `scrollBy`；
  - `positions/page.tsx`；
  - `EditAlertRuleModal`；
  - `ExitFailurePanel` 的容器內捲動，這個不是 window。
- 限制：這是從程式碼和 qa 數字推論，沒有在瀏覽器裡實測 anchoring。要確認的話，可以在 f3 流程對 `window.scrollBy` 打點，並對照 `overflow-anchor: none` 的結果。
- 這與 qa-e2e 報告的結論一致，即 AC-33 的「`scrollY` 差 0px」寫法有問題。

## 驗證
CI 數字，都是在 worktree 內本機執行，先 `npm ci`：
- `tsc --noEmit`：exit 0。
- `vitest run`：114 個檔案、2985 個測試全部通過。上一輪自報是 2882，這次多出的數字包含本次新增的測試。
- `next build`：成功，路由表正常輸出。我是用 `| tail` 看輸出，沒有直接取 exit code，成功是依輸出判斷。
- 沒有跑 `validate_agents.py`，因為沒動 `.claude/` 或 agents。
- Codex 第二意見這次沒有跑，要走 qa-reviewer。

commit 清單（兩個都帶指定的 trailer）：
- `eb10f96` fix: 離線 paused 不再視為 refetch 結束，補行為測試鎖住已知限制（N-183）
- `395fa8c` test: 收緊補償安全閥與手動捲動偵測的結構測試（N-183）

變更檔案，都在 `/home/user/AICompany/apps/stock-desk/frontend/app/` 底下：
- `lib/receiptCompensation.ts`：新增 `fetchStatusSignal`。
- `playbook/useReceiptCompensation.ts`：paused 時跳過，不更新狀態。
- `lib/__tests__/receiptCompensation.test.ts`：新增 4 個測試，包含 paused 與已知限制。
- `playbook/__tests__/exitFlowStructure.test.ts`：結構測試改嚴。

## 下一步
1. 交 qa-reviewer 審查，Codex 第二意見待環境可用時補跑。
2. 沒有新增解讀點。已知限制維持交件解讀點 4，現在有測試鎖住。
3. PM 與 art-lead 照 qa-e2e 報告修 AC-33 和 V-47(b) 的 `scrollY` 寫法。f3 的原因說明可以直接附給他們。
4. 上一輪審查的 low 項目（`dispose` 設 `phase="done"` 加上 `arm` 同 seq 冪等，StrictMode 下可能讓掛載當下 arm 的回執永久失效）這次沒處理，因為不在 N-183 範圍。

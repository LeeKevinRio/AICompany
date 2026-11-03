# 出清橫幅遮擋補償修正交件（db2ee33）

- 審查者：frontend-engineer
- 日期：2026-11-03
- 轉存：coordinator，逐字轉存 subagent 最終回報

---

## 本次結論
狀態列在捲動後才長高時，橫幅第一段被蓋住的 BLOCKING 已修，已推上 `origin/fix/stock-desk-exit-feedback`（b3d6284 → db2ee33，非 force，沒有 rebase 或 merge）。這是靜態與單元層的驗證。實機重跑尚未做，需要 qa-automation 重跑。worktree 已移除。

## 條款對照
所有檔案都在 `apps/stock-desk/frontend/app/` 下。

| 條款 | 對應 code | 對應測試 |
|---|---|---|
| FR-3 (i) 首捲偏移取 max(固定偏移, 即時高度+16) | `playbook/useEmergencyExitFlow.ts` 的 scroll effect。`scrollIntoView` 套用 `scroll-mt-40` / `lg:scroll-mt-32`，再用 `receiptScrollCorrection` 以即時 `barBottom + 16` 補差。兩步合起來的結果等於 max()。這段本來就在，這次沒有改動。 | `lib/__tests__/exitReceipt.test.ts` 既有案例 |
| FR-3 (ii) 同步完成點 | `lib/receiptCompensation.ts` 的 `fetchingChanged` 與 `stabilize`：refetch 結束後，狀態列高度連續 2 個 frame 相同才判定（上限 60 個 frame 後仍判一次）。重新掛載的情況，因為由該實例 arm，所以以重新掛載後的第一次 refetch 為準。 | `receiptCompensation.test.ts` 的「waits for the refetch to end」、「judges only after the bar height is equal for two consecutive frames」、「gives up waiting after the frame cap」 |
| FR-3 (iii) 條件與動作 | `receiptCompensationDelta`：`top < barBottom+12` 才觸發，補償量為 `top − (barBottom+16)`。使用者手動捲動用 `wheel`、`touchmove`、`keydown` 偵測，見 `playbook/useReceiptCompensation.ts`，不看 `scrollY`。 | 真值表（8 個案例，含 2⁴ 窮舉）、`isScrollKey`、結構測試「detects manual scrolling from input events」 |
| FR-3 (iv) 額度 1 次、不搬焦點、不平滑 | controller 的 `quotaUsed`。`behavior:"auto"`，沒有 `.focus()`。 | 「(d) quota」、「(d) a second receipt has its own quota」、結構測試「scrolls instantly, never moves focus」 |
| FR-3 (v) 安全閥 | 程式內沒有套用安全閥，不可達時照常捲到 `scrollY=0`，由瀏覽器夾住。 | 結構測試「applies no safety valve」 |
| AC-68(h) 真值表 | `receiptCompensationDelta` | `lib/__tests__/receiptCompensation.test.ts` |
| V-47(a) 遮擋時補一次 | controller 的 `judge` | 「(a) obstructed at the sync point」，含 C 組 277px 的 −133 |
| V-47(b) 不遮擋不補 | 同上 | 「(b) not obstructed」、「hysteresis」12 到 16 之間不補 |
| V-47(c) 手動捲動不補 | `userInput()` 只在 arm 之後才計入 | 「(c)」、「input before arm does not count」 |
| V-47(d) 額度、第二份獨立 | `arm(seq)` 換 seq 時重置額度 | 兩個 (d) 案例 |
| V-47(e) SPA 換頁 | 只有 scroll effect 通過 `shouldScrollForReceipt` 之後才 `arm`。已顯示過的回執回來時 effect 提早 return，所以不捲也不補。 | 結構測試「armed only by the scroll effect」 |
| V-47(f) 277px | 同 (a) | 同 (a) |
| V-47(g) 字面與結構不變 | 沒有改任何 JSX、字面或 class。 | 既有字面與結構測試全綠 |
| 狀態列卸載時不多捲 | `barBottom === null` 時 delta 為 0 | 「status bar unmounted」 |
| NB-1 掃描 | 該修正已在先前的 commit `d52e27c`，`exitFlowStructure.test.ts` 的 `exitFiles` 已含 `exitReceiptStore.ts` 與 `exitReceiptContext.tsx`。這次沒有重複改。 | 既有測試 |

## 觸發點選了哪一種
我選 `/today` refetch 結束（從 fetching 變 idle），不用 ResizeObserver。理由有三點。
1. 規範的「同步完成點」就是 refetch 結束，行為最貼近。
2. ResizeObserver 會在之後的背景輪詢長高時也觸發，而規範 §4.2 第 3 點明列「不補」。
3. 不需要新訂閱，也不碰 store。

實作上，`page.tsx` 把 `today.fetchStatus` 傳給 `useEmergencyExitFlow`。傳進去而不是在 hook 內開 query，是因為既有的 Cap1 測試整個 mock 了 `lib/queries`，hook 內自己用 react-query 的 hook 會報 `No QueryClient`。flow 檔也不能出現 `today` 這個字，結構測試有規定。

補償額度和「已 arm」的狀態存在頁面實例的 ref 中，沒有加進 store，所以守住 FE-C2 與 INV-1，也沒有任何持久化。

## 解讀點
沒有碰到規格互相矛盾，也沒有新增面向使用者的字面。以下是我自行做的實作判斷，供你們確認。
1. **「首捲偏移改為 max()」**：現有程式已經是 `scrollIntoView` 加即時修正，數學上等於 max()。實機失敗的原因是出清當下狀態列才 87px，不是首捲邏輯錯。我沒有重寫這段，只在報告說明。
2. **狀態列卸載（沒有 sticky 元素）時完全不補償**，即使橫幅 `top < 12`。理由是沒有東西能遮住橫幅，也符合 V-47(f3)。
3. **arm 時機**：不論首捲有沒有實際發生，都會 arm。這是為了「頁面頂端出清、之後狀態列長高並遮住」的情況。
4. **arm 時 refetch 已在進行中**，就視為已看到 fetching。若 refetch 在 arm 之前就已結束，補償會等到下一次 refetch。這是極小的競態，已知。
5. **Space 鍵算捲動鍵**，依規範列表。在按鈕上按 Space 的 keydown 也會計入「使用者已手動捲動」，但這發生在 arm 之前（確認送出時），不影響。
6. **重新掛載競態**：若首捲後、同步完成點之前就 SPA 離開再回來，該回執已標記為已捲，所以不補。

## CI 數字
都是在 worktree 內本機跑的。後端沒動，所以沒跑。
- `npx tsc --noEmit`：exit 0，無錯誤輸出。
- `npx vitest run`：**2882 passed (2882)**，共 111 個檔案。這次新增 1 個測試檔與 5 個結構測試。
- `npx next build`：Compiled successfully，8 個靜態頁面產生。build 輸出寫著 "Skipping validation of types"，型別檢查由上面的 tsc 負責。
- 不是 CI 綠燈。遠端 CI 我沒有查。
- `ui-delivery-checklist` 自檢：本次沒有改 JSX、class、字面、色值或互動狀態，對比、input 狀態、響應式、假數據等項目不適用，沒有新增任何顯示的數字。是否真的不被遮擋，只能靠實機驗。

## commit 清單
1. `dbaabe0` feat: 出清橫幅遮擋補償的判斷與控制器（規範 r3.5a §4.2，AC-68）
2. `db2ee33` fix: 狀態列捲動後才長高時補償一次捲動，橫幅第一段不再被蓋住（FR-3，AC-6、AC-32、AC-33、AC-64(c)）

兩個 commit 都帶了你指定的 trailer。

## 給 qa-automation 重跑實機的注意事項
- **必須能控制 `/today` refetch 的回應時機**（route intercept 或延遲回應），否則只能量 T1，要標「T0 未量」。補償在 refetch 結束，加上狀態列高度連續 2 個 frame 不變之後才發生，約再 1 到 2 個 frame 才落定。T1 要等這段時間，再等 500ms 確認 `scrollY` 不再變。
- **預期的程式捲動次數**：C 組、tall2 是首捲 1 次加補償 1 次。規格主情境 87→127px 因為首捲已用即時高度，可能補償 0 次，允許。tall1 與已顯示過的回執回來，補償必須是 0 次。
- **手動捲動的負向案例（V-47(c)）**：要送真正的 `wheel`、`touchmove` 或捲動鍵事件。單純 `window.scrollTo` 不會被判成使用者輸入，因為程式用事件偵測，不看 `scrollY`。
- **補償觸發需要 refetch 先從 fetching 變 idle**：測試端若讓 `/today` 永遠不回或根本不重新取得，就不會有補償。
- **刻意預期的行為**：
  - `/today` refetch 失敗、狀態列卸載時，補償 0 次。
  - 狀態列高度超過視窗 50% 時，程式沒有套安全閥，一律補償或捲到 `scrollY=0`。是否 `OVER_HALF_VIEWPORT` 由驗收端依規範 §4.2 的可達性判準判斷，並列出完整量測值。
- **重驗清單照 PRD AC-68**：三種寬度，C 組含 1280 的原 −3px，tall1、tall2，87→127px 主情境，再加 B、A、D、E、F、G 回歸。用最新 HEAD（db2ee33）和 `git diff --stat b3d6284..db2ee33` 確認產品碼差異。這次產品碼動了 `useEmergencyExitFlow.ts`、`page.tsx`，並新增 `receiptCompensation.ts` 與 `useReceiptCompensation.ts`。
- **環境提醒**：把 `node_modules` 做成 symlink 會讓 `next build`（Turbopack）失敗，錯誤是 "points out of the filesystem root"。我改用複製才過。

## 相關檔案
所有路徑都在 `apps/stock-desk/frontend/app/` 下。
- `lib/receiptCompensation.ts`（新增）
- `lib/__tests__/receiptCompensation.test.ts`（新增）
- `playbook/useReceiptCompensation.ts`（新增）
- `playbook/useEmergencyExitFlow.ts`（修改）
- `playbook/page.tsx`（修改）
- `playbook/__tests__/exitFlowStructure.test.ts`（修改）

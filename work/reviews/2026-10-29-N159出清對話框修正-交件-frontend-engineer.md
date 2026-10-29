# N-159 EXIT 對話框 portal 修正交件

- 審查者：frontend-engineer
- 日期：2026-10-29
- 轉存：coordinator，逐字轉存 subagent 最終回報

---

## 本次結論
N-159 已修。EXIT 對話框改用 React portal 渲染到 `document.body`，脫離 `ModeStatusBar` 的 containing block。已 push `fix/stock-desk-exit-dialog-portal`，commit `f11124e`，基底為 origin/product/stock-desk。我沒有在真實瀏覽器量測，所以「遮罩覆蓋整個視窗、面板落在視窗內、捲動後仍成立」這三項要靠 qa-e2e 實機複驗。

## 根因
`ModeStatusBar.tsx:28` 是 `sticky top-0 z-10 … backdrop-blur`。祖先帶 `backdrop-filter` 時，`position:fixed` 後代的 containing block 會變成該祖先，不再是 viewport。`EmergencyExitControl` 的 `fixed inset-0` 遮罩於是被限在條帶的約 86px 高度內，面板置中後上緣跑出視窗外（1280×900 時 y=-70），其餘頁面也沒有變暗。

## 修法
我選 portal，沒有移除 `backdrop-blur`。移除會改變條帶的視覺規範（art-lead 已定稿），而且只是繞開這一次，之後條帶加 `transform`、`filter` 等屬性還會再犯。portal 讓對話框結構上就不依賴祖先樣式。
- 遮罩和面板用 `createPortal(…, document.body)` 渲染。
- 只在 client mount 之後才渲染，用 `useSyncExternalStore`（server snapshot 為 false，client 為 true），避免 SSR 和 hydration 出問題。
- 面板加 `max-h-[calc(100vh-2rem)] overflow-y-auto`。遮罩的 `p-4` 上下共 2rem，所以面板必在視窗內，視窗高度不足時面板內可捲動。
- 遮罩的 z-index 從 `z-20` 改成 `z-50`，與專案內其他三個 dialog 一致。脫離條帶後，要確保蓋過頁面上其他有 z-index 的元素。這是我多加的小改動，你如果要保留 `z-20` 可以還原。

## 改動落點
- `apps/stock-desk/frontend/app/playbook/EmergencyExitControl.tsx`
  - `:4` import `createPortal`
  - `:27` `useIsClientMounted`
  - `:64` 使用 hook
  - `:101-113` 說明註解與 `createPortal(`
  - `:118` 遮罩 `fixed inset-0 z-50`
  - `:120` 面板 `max-h` 與 `overflow-y-auto`
  - `:200` `document.body`
- `apps/stock-desk/frontend/app/playbook/__tests__/EmergencyExitPortal.test.ts`：新增。
- `ModeStatusBar.tsx` 沒動。

## 未改動項
- Step 2、Step 3 的所有字面、核取方塊、按鈕 disabled 條件、送出 API 一律沒動。
- `role="dialog"`、`aria-modal="true"`、`aria-label` 保留。
- 原本就沒有 Esc 關閉、焦點管理和焦點限制，所以沒有東西需要「維持」，我也沒有新增，避免超出範圍。如果你要加，可比照 `EditPositionModal` 另開追蹤項。

## 測試
檔案是 `app/playbook/__tests__/EmergencyExitPortal.test.ts`，共 6 個。repo 沒有 jsdom 或 testing-library（見 `vitest.config.ts`），對話框也要點擊後才掛載，所以用原始碼結構掃描：
1. imports createPortal from react-dom and targets document.body
2. renders the dialog root (role=dialog, aria-modal) inside the portal call
3. uses fixed positioning only inside the portal, never in the inline tree
4. only mounts the portal after the client has mounted (SSR safe)
5. keeps the panel inside the viewport and scrollable when the viewport is short
6. ModeStatusBar still embeds the control but renders no dialog or fixed layer itself

我把測試套回舊版 `EmergencyExitControl.tsx` 驗證過，6 個中有 5 個會失敗（第 6 個本來就該過），確認它有擋住這個缺陷。其餘既有測試一個都沒改、沒放寬。

## ui-delivery-checklist 自檢
- 第 0 節：Step 2、Step 3 風控字面逐字未動，通過。
- 第 1 節對比：沒有新增或更動任何文字色與底色，通過。
- 第 2 節：沒有新增 input 或按鈕，原有的狀態沿用。
- 第 3 節：3.1 的 `html` 與 `body` 加 `overflow-x: clip` 屬全站層級，本次沒碰。面板 `w-full max-w-lg` 加 `p-4` 邊距，375px 寬可容納。面板高度已受限並可內捲。
- 第 4 節：無動效。
- 第 5 節：沒有捏造數據，仍然全為後端渲染字串。
- 第 6 節：沒有 inline 色值，只用既有 Tailwind class。
- 結論：無違反項，也沒有走白名單。
- 未驗證：375px 與 1280×900 的實機畫面尚未驗證，需 qa-e2e 驗收。

## CI 原文數字（前端，後端未動未跑）
- `tsc --noEmit`：無輸出，exit 0。
- `vitest run`：Test Files 92 passed (92)，Tests 2511 passed (2511)，Duration 13.10s。
- `next build`：Compiled successfully in 8.5s，8/8 靜態頁產生完成，路由 `/playbook` 正常。
- `node_modules` 是用 `cp -a` 從主 checkout 複製，沒有安裝任何套件。

## 下一步
交 qa-reviewer 審查，再由 qa-e2e 在 1280×900 與 375px 實機複驗：遮罩全視窗、Step 2 標題與第一條事實可見、Step 3「二次確認」標題可見、頁面捲動後仍成立、矮視窗下面板可內捲。我沒有 merge 也沒有 push `product/stock-desk`，未讀 `.env`，未碰 `*.db`。

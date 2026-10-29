# N-163 送出中焦點留在對話框內交件

- 審查者：frontend-engineer
- 日期：2026-10-29
- 轉存：coordinator，逐字轉存 subagent 最終回報

---

## N-163 交件：全部出清送出中焦點掉出對話框（已修、已推送）

分支 `fix/stock-desk-exit-pending-focus`，commit `3ceef60`，已 push 到 origin。`apps/stock-desk/` 存在，起點 HEAD 為 82f5460（含 833c6d7）。我沒有 merge 或 push `product/stock-desk`。

### 1. 修法與理由
我選 (b)：送出中的「取消」和「確認送出全部出清」不再用原生 `disabled`，改用 `aria-disabled={mutation.isPending}`，並在 handler 擋住。

不選 (a) 的原因如下。
- (a) 要在進入 pending 時把焦點搬到標題。失敗後焦點會停在標題，不在「確認送出全部出清」，等於改掉你要求不變的行為。
- 要維持原行為，得在失敗後再把焦點搬回按鈕。這要多一個依賴 pending 或 error 的 effect，更容易回歸。
- (b) 不搬焦點。按下的那顆按鈕一直是 activeElement，所以送出中、失敗後、Tab 循環都不用動。

四項要求的做法：
- **點擊無效**：`submit()` 和 `cancel()` 開頭都有 `if (mutation.isPending) return;`。`aria-disabled` 的按鈕仍可被 Enter、Space、點擊啟動，所以 `submit` 的重入防護是必要的，沒有它會重複送出不可逆的 POST。`cancel` 內的防護是縱深防禦。
- **Esc 無效**：原有的 `!mutation.isPending` 鎖沒動。
- **螢幕閱讀器**：`aria-disabled="true"` 會讀出「不可用」。按鈕仍可聚焦，所以螢幕閱讀器使用者能聽到「送出中…」。
- **Tab 限制**：`FOCUSABLE_SELECTOR` 只排除 `[disabled]`，不排除 aria-disabled。送出中兩顆按鈕仍在可聚焦清單內，`trapTabTarget` 照常在「取消」和「送出」之間循環。`focusTrap.ts` 沒有改。

額外加了 `event.currentTarget.focus()`。Safari 點擊按鈕時不會聚焦它，沒有這行的話，pending 前焦點可能不在按鈕上。Chromium 上這行無作用。

視覺：Tailwind 4 沒有 `disabled:` 對 aria-disabled 的效果，所以改用 `aria-disabled:cursor-not-allowed`、`aria-disabled:opacity-50`、`aria-disabled:hover:bg-*`，hover 不再亮起。我在 build 後的 CSS 確認這四條都有輸出，選擇器為 `[aria-disabled=true]:hover`，特異度高於原 hover，會蓋過。

字面、API、核取方塊、Step 2 按鈕的原生 disabled（依核取方塊決定）都沒動。

### 2. 落點
- `apps/stock-desk/frontend/app/playbook/EmergencyExitControl.tsx`
  - `cancel` 防護：86–89 行
  - `submit` 防護與聚焦：94–100 行
  - 「取消」按鈕 `aria-disabled`：271–272 行
  - 「確認送出」按鈕 `aria-disabled`：279–280 行
  - 兩顆按鈕上方有 N-163 說明註解
- `apps/stock-desk/frontend/app/playbook/__tests__/EmergencyExitPortal.test.ts`：檔尾新增 `describe`（182 行起）與兩個輔助函式 `functionBody`、`finalStepSource`。既有斷言沒有改動或放寬。

### 3. 測試名稱
`describe("EmergencyExitControl keeps focus inside the dialog while submitting (N-163)")` 下 6 條：
1. Step 3 buttons use aria-disabled while pending, never the native disabled attribute
2. styles the aria-disabled state (cursor, opacity, no hover highlight) on both buttons
3. refuses to submit again while pending (a focused aria-disabled button can still be activated)
4. refuses to cancel while pending, whatever triggers it
5. focuses the clicked submit button before the request starts (browsers that do not focus on click)
6. does not move or drop focus when the pending state flips (failure keeps focus on 確認送出)

**能擋到：**
- Step 3 的按鈕被改回原生 `disabled`，或 `disabled:` 樣式回來。
- `aria-disabled` 被拿掉或少一顆。
- `submit` 或 `cancel` 的 pending 防護被移除，或順序移到 `mutate` 或 `setStep` 之後。
- 聚焦那行被移除。
- 焦點 effect 被改成依賴 pending 或 error。
- 有人新增 `.blur(` 或另一處 `.focus()`（斷言 `.focus()` 恰好 4 處）。

**擋不到：**
- 真實瀏覽器的焦點行為。專案沒有 jsdom，這類測試只是原始碼掃描。
- 瀏覽器對 aria-disabled 的實際朗讀。
- Tailwind 實際產出的 CSS。我另外手動確認過一次，測試不會自動擋。
- 失敗與成功路徑的焦點落點。靠既有掃描間接保證，以及我沒有動那些程式碼。

我做過變異驗證：把元件還原成修改前版本，這 6 條全數失敗。

### 4. CI 數字（前端）
- `tsc --noEmit`：無錯誤。
- `vitest run`：96 個檔案、2586 條測試全過（修前 2580 條，新增 6 條）。
- `next build`：成功，8 個路由。

`node_modules` 從主 checkout `cp -a`，沒有安裝，也沒有被 git 追蹤。

### 5. ui-delivery-checklist 自檢
- 2.6 disabled 三通道：降透明度、`cursor-not-allowed`、`aria-disabled="true"` 都有。取消鈕原本缺 `cursor-not-allowed`，這次補上。
- 2.8 互動元素狀態：hover 在 aria-disabled 下被抑制，focus-visible 沿用瀏覽器預設。
- 1.x 對比：沒有新增色值。opacity-50 沿用既有做法。
- 其餘第 3 到 6 節：沒有新增版面、動效、顏色、假數據，不適用。
- 用戶可見字面未動，不需走風控。

### 6. 給實機驗收（qa-e2e / qa-automation）的重點
沿用 N-161 的 mock runner，第 1 節加三項：
1. **送出中 Tab**：送出中按 Tab 和 Shift+Tab 多次，`activeElement` 一直在對話框內（「取消」和「送出中…」之間循環）。修前是 body，然後跳到「stock-desk」連結。1280x900 和 375x812 都量。
2. **Esc 與點擊**：送出中 Esc、點「取消」、點或 Enter「送出中…」都無效。對話框仍在，只有 1 筆 POST（驗證沒有重複送出）。兩顆按鈕的 `aria-disabled` 為 `"true"`，且沒有 `disabled` 屬性。
3. **失敗與成功**：失敗後 activeElement 仍是「確認送出全部出清」，Tab 仍限制在對話框內，Esc 後焦點回觸發鈕。成功後關閉，焦點回「全部出清」。

提醒：QA 上一輪只驗過 headless Chromium。這次的 `event.currentTarget.focus()` 主要為 Safari 設計，在 Safari 上的實機行為沒人驗過。

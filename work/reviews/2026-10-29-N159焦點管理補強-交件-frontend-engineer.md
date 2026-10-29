# N-159 焦點管理、Esc 與 qa 小項補強交件

- 審查者：frontend-engineer
- 日期：2026-10-29
- 轉存：coordinator，逐字轉存 subagent 最終回報

---

## 本次結論
審查 NB-1 到 NB-6 全數補上，追加 commit `bad902c`，已 push 到 `fix/stock-desk-exit-dialog-portal`（f11124e..bad902c）。字面、核取方塊、按鈕 disabled 條件、送出 API 都沒動。

## 產品線合併
我跑了 `git fetch origin product/stock-desk`，遠端是 `ea2e780`，已經是本分支的祖先，產品線尚未更新。依你的指示不併，也沒有 rebase。等產品線 push 新內容後，需再用 merge commit 併入一次。

## 改動落點
全部在 `apps/stock-desk/frontend/app/playbook/EmergencyExitControl.tsx`：
- **焦點移入：**
  - 落點在 `:66-70` 的 ref 和 `:108-115` 的 effect（依 `[step]`）。
  - 每一步開啟時，焦點移到該步驟的標題 `<h2 ref={headingRef} tabIndex={-1}>`（`:184` 和 `:229`）。
  - 選標題不選第一個核取方塊，理由是核取方塊會讓使用者一開啟就能按 Space 勾選，繞過「逐條讀完才勾」的流程摩擦。標題也能讓螢幕閱讀器先讀出步驟名稱。
  - Step 2 切到 Step 3 時標題元素更換，焦點會重新落在新標題。
- **焦點歸還：**
  - 落點是同一個 effect 的 `:114`（`wasOpen` 時 `triggerRef.current?.focus()`）。
  - 觸發按鈕掛 `ref={triggerRef}`（`:150`）。
  - 取消、Esc、送出成功都會經過 `setStep("idle")`，所以三條路徑都會把焦點還給「全部出清」。
- **Esc：**
  - 落點在 `:120-128`，是掛在 document 的 keydown 監聽，只在對話框開啟時註冊。
  - Esc 經 `cancelRef.current()` 走 `cancel()`，等同按「取消」，不會呼叫 `mutate`。
  - 送出中（`mutation.isPending`）Esc 無效，與 Step 3 取消鈕 disabled、`EditPositionModal` 的做法一致。
- **焦點限制：** `EditPositionModal` 本來就有，所以照做。
  - 落點是 `:6` import 共用的 `focusTrap`（`FOCUSABLE_SELECTOR`、`trapTabTarget`）、`:132` 的 `handleDialogKeyDown`，掛在 `:172-176` 的 role=dialog 根節點。
- **高度：**
  - 落點在 `:179`，寫成 `max-h-[calc(100vh-2rem)] supports-[height:100dvh]:max-h-[calc(100dvh-2rem)]`。
  - 兩個裸 `max-h` 的先後由 Tailwind 的值排序決定，`dvh` 可能被 `vh` 蓋掉，所以用 `supports-[]` 變體，保證在支援 dvh 的瀏覽器勝出。
  - 我檢查了 build 後的 CSS，`@supports (height:100dvh)` 區塊在 `max-h-[calc(100vh-2rem)]` 規則之後（位移 43953 > 14379），順序正確。

## 測試
全部在 `app/playbook/__tests__/EmergencyExitPortal.test.ts`，原本 6 則，現為 11 則：
- NB-3：「only mounts the portal after the client has mounted」現在斷言 `useSyncExternalStore(subscribeNoop, () => true, () => false)`。
- NB-4：新增 `FIXED_CLASS = /(?<![\w-])fixed(?![\w-])/`，已套用在 #3 和 #6。
- NB-6：新增「keeps the overlay at z-50, above every other fixed layer (same as the other dialogs)」。
- dvh：「keeps the panel inside the viewport and scrollable when the viewport is short」補斷言 `100vh` 退路和 `supports-[height:100dvh]:max-h-[calc(100dvh-2rem)]`。
- 新增 describe「EmergencyExitControl focus management, Esc and focus trap (N-159 a11y)」，共 4 則：
  - moves focus to the step heading on every step (not to a checkbox)
  - returns focus to the 全部出清 trigger after any close, via the step -> idle transition
  - closes on Esc through cancel(), locked while submitting, and never calls the submit
  - traps Tab inside the dialog with the shared trapTabTarget helper

repo 沒有 jsdom，這些都是原始碼掃描。

**能擋到：**
- 兩個標題的 ref 和 tabIndex 被拿掉。
- 焦點歸還路徑被拿掉。
- Esc 不再經 cancel、不再鎖 pending，或誤接到 submit。
- 焦點限制 helper 或其掛載位置被移走。
- z-50、vh 和 dvh 退路被改掉。
- server snapshot 被改成 true。

**擋不到：** 實際的焦點移動和 Tab 循環行為，仍需 qa-e2e 在真實瀏覽器驗。

## CI 原文數字（前端）
- `tsc --noEmit`：無輸出，exit 0。
- `vitest run`：Test Files 92 passed (92)，Tests 2516 passed (2516)。前一版是 2511，多出 5 則。
- `next build`：Compiled successfully in 10.8s，`/playbook` 路由正常。
- 後端未動，未跑。

## 給 qa-e2e 的實機複驗項
- 開啟後焦點在標題。
- Step 2 切到 Step 3 後焦點在新標題。
- Tab 和 Shift+Tab 在對話框內循環。
- Esc 關閉且 API 不發出。
- 取消、Esc、送出成功後焦點回到「全部出清」按鈕。
- 標題被 programmatic focus 時會出現瀏覽器預設的 focus outline，我沒有隱藏它，如視覺上不想要需 art-lead 定奪。

未讀 `.env`、未碰 `*.db`、未 push `product/stock-desk`。

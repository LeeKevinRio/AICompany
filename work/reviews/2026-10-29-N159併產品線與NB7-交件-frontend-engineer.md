# N-159 併產品線與 NB-7 交件

- 審查者：frontend-engineer
- 日期：2026-10-29
- 轉存：coordinator，逐字轉存 subagent 最終回報

---

## 本次結論
產品線已用 merge commit 併入，NB-7 的兩條斷言已補上，前端 CI 全綠，已 push `fix/stock-desk-exit-dialog-portal`。

## Commit
- **merge commit：`c2e668b`**
  - 將 `origin/product/stock-desk` 的 `7cebaf6` 併入本分支。
  - 用 `--no-ff -F <檔案>` 帶入訊息，沒有 rebase。
  - 沒有衝突。
  - 該次 merge 的 diff 沒動 `package.json` 和 `package-lock.json`，沿用原本複製的 `node_modules`，沒有安裝任何套件。
- **新 commit：`12216d4`**，`test: 全部出清 Esc 監聽補斷言，鎖住僅開啟時註冊與依賴項 (N-159 輕審 NB-7)`。
- push 結果：`bad902c..12216d4`。

## NB-7 斷言
- 落點在 `apps/stock-desk/frontend/app/playbook/__tests__/EmergencyExitPortal.test.ts`，加在「closes on Esc through cancel(), locked while submitting, and never calls the submit」那一則。
- 新增兩條：
  - `/if \(step === "idle"\) return;/`
  - `/\[step, mutation\.isPending\]/`
- 這兩條擋住的回歸：Esc 監聽變成對話框關閉時也註冊，或依賴項被改動。
- 元件本身這次沒有改動。

## CI 原文數字（merge 之後，前端）
- `tsc --noEmit`：無輸出，exit 0。
- `vitest run`：Test Files 96 passed (96)，Tests 2580 passed (2580)。
- `next build`：Compiled successfully in 953ms，`/playbook` 路由正常。
- 後端未動，未跑。

## 備註
- `next build` 的編譯時間只有 953ms，是因為前一輪的 build 快取（元件沒變），不是跳過編譯。
- 未讀 `.env`，未碰 `*.db`，未 push 或 merge 到 `product/stock-desk`。
- 實機的焦點與 Tab 循環行為仍待 qa-e2e 驗收，這是前一份報告已列出的項目。

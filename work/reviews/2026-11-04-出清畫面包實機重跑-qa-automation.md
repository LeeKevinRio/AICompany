# 出清回饋畫面修正包實機重跑代跑（受測 db2ee33，只交事實）

- 審查者：qa-automation
- 日期：2026-11-04
- 轉存：coordinator，逐字轉存 subagent 最終回報

---

## 本次結論（只交事實，不下 Verdict）

我已對 `db2ee33` 重跑實機驗收，三種寬度（375×812、375×667、1280×900）全部跑完，T0 和 T1 都量到了，沒有「T0 未量」的案例。

- 事實檔：`/tmp/claude-0/-home-user-AICompany/3f76d891-50d3-55e1-b39d-925b8a90241a/scratchpad/e2e_exitfb_out2/facts.md`。上一輪的輸出目錄沒有被改動。
- 結構：
  - 第 A 部分是本輪的補償捲動重驗。
  - 第 B 部分是回歸，章節 1 到 11 沿用上一輪編號。
  - 第 12 到 15 節是無法驗收項、需判斷事項、檔案索引、清理。

產品碼差異（`git diff --stat 47f8ad9 db2ee33`，原文在 facts 的 0.1）：
- 共 7 個檔案、568 行新增、14 行刪除。
- 其中 4 個是產品碼：
  - `apps/stock-desk/frontend/app/lib/receiptCompensation.ts`（新增）
  - `apps/stock-desk/frontend/app/playbook/useReceiptCompensation.ts`（新增）
  - `apps/stock-desk/frontend/app/playbook/useEmergencyExitFlow.ts`（16 行變動）
  - `apps/stock-desk/frontend/app/playbook/page.tsx`（2 行變動）
- 另 3 個是 `__tests__` 下的測試碼，不進 production build。
- backend 沒有被動。

核心數字，T1 取 `getBoundingClientRect()` 原值，橫幅 top − barBottom／第一個 `<p>` top − barBottom：

| 案例 | 結果 |
|---|---|
| C 組，375×812 與 375×667，87→277px | 16／33，`elementFromPoint` 命中橫幅。上一輪是 −117／−100。 |
| C 組，1280×900，87→131px | 16／33。上一輪是 −3／+14。 |
| 87→127px 主情境，375 兩個高度 | T0 為 73／90，T1 為 33／50。補償 0 次，只有首捲 1 次。 |
| 5.e tall2，375 兩個高度 | T1 為 16／33，上一輪是 −53。 |
| 5.e tall1，三個寬度 | 程式捲動 0 次，`scrollY` 恆為 0。 |
| 已顯示過的回執再回來，兩次 | 程式捲動 0 次，`scrollY` 差 0。 |
| 使用者輸入（wheel、ArrowDown×3、CDP touchmove），C277 與 A127，三個寬度 | 補償全為 0 次。 |
| 對照組：測試端 `window.scrollTo` | 補償 1 次（375 寬 −203、1280 寬 −89）。 |
| f4 第二份新回執 | 首捲 1 加補償 1，額度獨立。 |

回歸：sc7 的 A、B、D、E、F、G 最終值與上一輪完全相同，只有 C 和 5.e tall2 改變。

## 各部門回報

**需要 qa-e2e 判斷的事項**
1. **tall2 超過視窗 50%（AC-68(i)）。**
   - 375×667：T0 height 391、T1 height 477，50% 線 333.5，兩個時點都超過。
   - 375×812：T0 391（50% 線 406，未超過）、T1 477（超過）。
   - T1 時 `scrollY`=207，所需上捲量為 0，用 §4.2 的算術是可達。
   - 1280×900 的 tall2 是 211，未超過。
   - AC-68(i) 寫「立即升級 PM 與風控」，這個判斷我沒有做。
   - A.3 的 f2 步驟第二次長高也到 477，同樣超過 375 兩個寬度的 50% 線。
2. **程式捲動怎麼計次。**
   - tall2 共 3 次呼叫：掛載時 `scrollIntoView` 加 `scrollBy(-247)`，補償 `scrollBy(-86)`。
   - 前兩者是上一輪就有的首捲後微調（`receiptScrollCorrection`）。
   - PRD AC-33 寫「總數 ≤ 2（初次 ≤ 1、補償 ≤ 1）」。
   - B、D、E 與 375×667 的 G 同樣在 T0 前就是 2 次呼叫。
3. **重新取得失敗而狀態列卸載（f3）。**
   - T0 之後程式捲動 0 次。
   - 但 `scrollY` 在 T0→T1 有變：375×812 為 150→38，375×667 為 150→63，1280×900 為 104→0。
   - A.5 顯示文件高度由 3721（1280 寬為 2571）縮到 850（1280 寬為 900），也就是頁面被錯誤版面取代。
   - AC-33 寫「`scrollY` 差 0px」，如何判定交你。
4. **額度用完後狀態列再長高（f2）。**
   - 該步驟 0 次程式捲動。
   - `scrollY` 207→407，疑為 scroll anchoring，我沒驗證。
   - 橫幅被遮：375 寬 −184，1280 寬 −64。
   - 這是 V-47(d) 的預期行為，只記錄事實。
5. **使用者輸入後橫幅被遮的程度（f1）。**
   - T1 時橫幅被遮，C277 在 375 寬為 −187～−237，A127 在 375 寬為 −37～−87。
   - V-47(c) 說這是刻意取捨，不判。
6. **1280 寬的 A 組。** 狀態列 87→87，沒有長高，所以「87→127」只在 375 寬成立。

**自加的路徑**（細節在 facts 的 13.B）
- 用 route `hang` 攔住出清後的第一次 `/today`，T0 量完才釋放。
- 使用者輸入用 `page.mouse.wheel`、鍵盤 ArrowDown、CDP touch。鍵盤沒用 Space，因為焦點在按鈕上會被按下。
- f2、f3、f4 的流程、tall1／tall2 的受控 `/today` 都是我加的。
- 新增 `comp_ac` 腳本補 AC-19、AC-62(a)、AC-63(c)，因為上一輪沒有逐字做這三項。
- DB 沿用上一輪已 seed 的拋棄式複本，沒有重新 seed。
- **我改了 `check_real.py`**：
  - 上一輪它把 `until=2026-11-27` 和第一次出清的 `execution_date=2026-11-02` 寫死。
  - 本機時鐘已到 2026-11-03，直接跑會得到 11 筆「API message == wording.py expected : False」，那是比對參數過期，不是畫面差異。
  - 改成 `until` 取自回應的 `freeze_until`、`pending` 的日期取自第一次出清回應。
  - 改後 12 筆 `message` 與 12 筆 `attribution` 與 `wording.py` 逐字相等。
  - 日期換成 `D` 後，與上一輪的回應逐字相同。
  - 這次比對用的 `wording.py` 來自 `git archive db2ee33` 匯出的副本，該副本已刪除。

**與預期可能不符的觀察**
- `pageerror: Cannot read properties of null (reading 'innerText')` 在 `s1` 情境出現 420 次，上一輪是 378 次。console 記錄沒有保存 stack，我用單獨小腳本沒重現。疑為我的取樣器，未證實。
- 寫入型請求缺 `X-Stock-Desk-Client` 的次數為 0（364 筆情境記錄，出清 POST 共 299 筆）。
- 重新取得失敗時，375×667 的 `scrollY`=63 低於 `maxScroll`=183，原因我沒有進一步驗證。
- tall1 在 375×667 的 T1 橫幅 top 為 500，超過 0.66×視窗（440.22），沒有補捲，與上一輪相同。

## 驗證（provenance）

- **儀器**
  - Playwright 1.63.0，路徑 `/opt/node-tools/node_modules/playwright/index.js`。
  - Chromium 153.0.8010.12，路徑 `/opt/pw-browsers/chromium-1243/chrome-linux64/chrome`。
  - 前綴為 `/opt/`；runner 開頭有 fail-closed 斷言，沒有安裝任何東西。
- **受測樹**
  - `origin/fix/stock-desk-exit-feedback` = `db2ee33b48a07ee75e001387ddcf0fb57ef5d8de`。
  - 用 `git worktree add --detach` 開在 scratchpad 下，結束時 `status --short` 為空。
  - `package.json`、`package-lock.json`、`uv.lock`、`pyproject.toml` 四個檔與主 checkout 的 `cmp` 皆為 0。
- **build**
  - `next build` 加 `next start`，production build 成功。
  - `node_modules` 用 `cp -al` 硬連結，Turbopack 沒有失敗，所以沒有改用複製。
- **資料**
  - 所有 DB 都在 `/tmp/claude-0/-home-user-AICompany/3f76d891-50d3-55e1-b39d-925b8a90241a/scratchpad/e2e_exitfb_db2/`。
  - 每次寫入前做 realpath 前綴斷言。
  - 沒讀 `.env`，沒碰 `apps/stock-desk/backend/data/*.db`。
  - 寫入請求都帶 `X-Stock-Desk-Client`。
- **收尾**
  - `next`、`uvicorn`、Chromium 都已停止，`localhost:3000` 與 `127.0.0.1:8000` 皆無回應。
  - worktree 已移除，`git worktree list` 沒有它（清單中其他 worktree 不是我建的）。
  - 主 checkout 只有開始前就存在的兩項變動：`docs/adr/0035-…` 與 `work/reviews/2026-11-03-ADR0035補充四與N171評估-tech-architect.md`，不是我造成的。
  - 我沒有改任何產品碼，沒有跑 pytest、vitest 或 typecheck。
- **不可驗**：INV-1 注入、螢幕報讀、Firefox、WebKit、真實午夜與真實歷史資料（同上一輪）。

## 下一步

1. qa-e2e 讀 `facts.md`：
   - A.1 到 A.3 看 T0／T1 逐案例數字。
   - A.4 看 50% 線與可達性。
   - 第 13.C 節看上列需判斷事項。
2. 若採納「tall2 超過 50%」這項，由 qa-e2e 依 AC-68(i) 升級 PM 與風控，我不自行處理。
3. 計次與 f3 的 `scrollY` 差，需要 PM 或 art-lead 釐清規格。
4. 截圖只在 scratchpad，只有兩張我實際看過：`comp5e_375x667_tall2.png` 與 `comp_375x667_C_barGrowsAfterExit_bottom__277.png`。判讀完畢可刪。
5. 腳本在 `/tmp/claude-0/-home-user-AICompany/3f76d891-50d3-55e1-b39d-925b8a90241a/scratchpad/e2e_exitfb_scripts2/`。本輪新增的是 `sc_comp.js`；`lib.js` 加了 `__h.meas()` 與額外的捲動呼叫記錄；`mkcomp.py`、`mkcmp.py`、`mkhead2.py`、`tail2.md`、`assemble2.sh` 是 facts 產生器；其餘沿用上一輪。

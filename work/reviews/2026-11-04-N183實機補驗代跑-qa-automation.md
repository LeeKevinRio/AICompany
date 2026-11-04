# N-183 輕量實機補驗代跑（395fa8c，只交事實）

- 審查者：qa-automation
- 日期：2026-11-04
- 轉存：coordinator，逐字轉存 subagent 最終回報

---

## 本次結論
N-183（395fa8c）的四項重驗已用 production build 實機跑完，我只交事實，不下 Verdict。完整事實在 `/tmp/claude-0/-home-user-AICompany/3f76d891-50d3-55e1-b39d-925b8a90241a/scratchpad/e2e_n183_out/facts.md`（234 行）。

- **項目 1（375×667，C 組，離線）**
  - 出清後的 `/today` refetch 進行中切離線，react-query 的 `['playbook-today']` 直接觀測到 `fetchStatus: "paused"`。
  - 轉換序列：`failed[fetching]` t=4147，1 秒後 `pause[paused]` t=5147，恢復連線時 `continue[fetching]` t=6999，`success[idle]` t=7344。
  - 離線區間（page `offline` 事件 t=3795 到 `online` 事件 t=7000）內，程式捲動呼叫 0 次。離線前有 1 次 `scrollIntoView`（回執首捲，t=3729，比 offline 事件早 66ms）。
  - 離線穩定期間與重試進行中，量測都是 scrollY 150、barBottom 87、banner top − barBottom = 73。
- **項目 2（恢復連線）**
  - 重試請求結束後，`scrollBy` 剛好 1 次（`top:-133`，scrollY 340 → 207）。
  - T1：barTop 0、barBottom 277、height 277、scrollY 207、banner top − barBottom = 16、第一個 `<p>` − barBottom = 33。
  - `elementFromPoint` 命中橫幅的 `<p>`。T1 後 500ms 內 scrollY 差 0。
- **項目 3（線上正常路徑）**
  - C 組補償 `scrollBy` 在 375×667 和 1280×900 都是 1 次。
  - 375×667：barBottom 277、scrollY 207、banner − barBottom = 16、`<p>` − barBottom = 33。
  - 1280×900：barBottom 131、scrollY 129、banner − barBottom = 16、`<p>` − barBottom = 33。
  - 與上一輪（db2ee33）同案例逐欄比對，全部相同。
- **項目 4（離線期間手動捲動）**
  - 真實 `mouse.wheel(0,-120)` 和真實 `ArrowUp` x3 各跑一次，scrollY 都是 150 → 30。
  - 兩者離線區間內程式捲動 0 次，恢復連線後 `scrollBy` 也是 0 次。
  - T1：barTop 113、barBottom 390、height 277、scrollY 30、banner − barBottom = 80、`<p>` − barBottom = 97，`elementFromPoint` 命中橫幅 `<p>`。
- **額外（1280×900 離線）**：同樣觀測到 paused，離線區間 0 次，恢復後 `scrollBy` 1 次（`top:-19`），T1 為 16 和 33。

每個案例的 barTop、barBottom、height、scrollY、兩個差值、`elementFromPoint`、程式捲動呼叫清單，都在 facts.md 的 A 章表格裡。

## 各部門回報
- **需要 qa-e2e 判斷的事**
  1. 我進入 paused 的方式是：先讓 `/today` 被 route 掛住，`setOffline(true)` 之後把掛住的請求釋放成 `abort`，讓 react-query 的 `retry:1` 因離線而暫停。這種觸發方式能否代表「refetch 進行中切離線」，請判斷。
  2. 項目 4 手動捲動後，T1 的 banner − barBottom = 80（不是 16），barTop = 113（scrollY=30，狀態列尚未黏頂）。這是否符合「不得再補償」，請判斷。
  3. T0、離線期間、重試進行中三個時點 banner − barBottom 都是 73，因為 bar 仍是 87px 舊高度。277px 新 bar 要到重試的回應 mock 才出現，這是 C 組本來的時序。
- **我自己加的路徑**
  1. 把掛住的 `/today` 釋放成 `abort`（見上）。我沒有實測「只掛住、不釋放」時 `setOffline` 後 fetchStatus 會不會變 paused，所以沒用這條當證據。
  2. 用 React fiber 找 QueryClient 並訂閱 QueryCache，唯讀、未改任何產品檔。
  3. 1280×900 的離線主流程（清單只指定 375×667）。
  4. 離線後固定等 2800ms，越過 1000ms 的 retryDelay，才做手動輸入或恢復連線。
  5. 手動輸入選向上，因為頁面在底部，向下捲不會動。
  6. 沿用的 `sc_comp.js` 只在末行 `module.exports` 加了 helper 匯出。
- **與預期不符的觀察**
  - 沒有發現與重驗清單預期不符的程式捲動次數或數值。
  - 每個離線案例的 console 有 1 筆 `Failed to load resource: net::ERR_FAILED`（`http://localhost:8000/api/playbook/today`），是我刻意 abort 造成的。線上案例 console 為空。
  - 每案只跑 1 次，沒有重複次數的統計。
- **provenance**
  - playwright 模組 `/opt/node-tools/node_modules/playwright/index.js`（1.63.0）。
  - Chromium `/opt/pw-browsers/chromium-1243/chrome-linux64/chrome`（153.0.8010.12）。
  - 兩者都在 `/opt/` 前綴內，runner 的 fail-closed 斷言通過，沒有安裝任何東西。

## 驗證
- 實際執行了三組指令：`n183_offline 375x667`、`n183_offline 1280x900`、`n183_online 375x667 1280x900`。所有案例的 ERROR 欄皆為空。
- 受測樹：HEAD 確認為 `395fa8c4128a56c64a0aafc276f1e6ee4b5ec16c`。`git diff --stat 395fa8c~2 395fa8c` 是 4 個檔案、87 增 5 刪，全在 `apps/stock-desk/frontend/app/` 底下。
- 環境：
  - 前端用 `next build`（exit 0）加 `next start`，`node_modules` 以 `cp -al` 建立。
  - 後端 DB 是拋棄式目錄 `e2e_n183_db/base/`，寫入前做了 realpath 前綴斷言（`PREFIX_OK`）。
  - 行程環境證明在 `e2e_n183_out/be_base_env_proof.txt`。
  - 沒讀 `.env`，沒碰 `data/*.db`。
- 寫入請求缺 `X-Stock-Desk-Client` 的次數是 0（POST 帶 `1`）。
- 結束清理：next 和 uvicorn 已停（localhost:3000 和 :8000 都連不上），`wt_n183` worktree 已移除，主 repo 前端 `node_modules` 完好（65 項）。
- 未驗：沒跑 vitest 或 tsc；`/today` 是 mock 而非真實後端回應；沒測「不釋放掛住請求」時的 fetchStatus。

## 下一步
1. 交 qa-e2e 讀 facts.md 和截圖出具 Verdict（本檔不含 Verdict）。
2. 驗收結束後，截圖和 facts 可從 scratchpad 刪除。

截圖（只在 scratchpad `/tmp/claude-0/-home-user-AICompany/3f76d891-50d3-55e1-b39d-925b8a90241a/scratchpad/e2e_n183_out/`）：
- `n183_375x667_off_main.png`
- `n183_375x667_off_wheel.png`
- `n183_375x667_off_key.png`
- `n183_1280x900_off_main.png`
- `comp_375x667_C_barGrowsAfterExit_bottom__277.png`
- `comp_1280x900_C_barGrowsAfterExit_bottom__277.png`

原始資料也在同一目錄：`facts_n183_*.json`、`console_n183_*.json`。腳本在 `.../scratchpad/e2e_n183_scripts/`（`sc_n183.js` 為新增，`mkfacts_n183.py` 產生 facts 表格）。

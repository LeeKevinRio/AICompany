# 證據交件（e2e-fallback 代跑）— 前端減字三項 — qa-automation

以 e2e-fallback 代跑，代跑者：qa-automation。本文件只列事實，不下 PASS / FAIL，判讀交 qa-e2e。

## 0. 受測版本與環境
- worktree：`/home/user/AICompany/.claude/worktrees/agent-a3b8c88b329ce0ede`，分支 `fix/frontend-trim-three`，HEAD = `3ea244bd991c30ba085546219603d5210cb19ef5`。跑前與跑後 `git status --short` 皆無輸出，產品碼未動；未執行任何 install（worktree 內本來就有 `node_modules`）。
- 前端：`npx next dev --webpack --port 3101`（於 `apps/stock-desk/frontend`），Next 16.3.3。log：`<SP>/next-dev.log`。`<SP>` = `/tmp/claude-0/-home-user-AICompany/3f76d891-50d3-55e1-b39d-925b8a90241a/scratchpad/e2e-trim3`。
- 後端沒起。所有 `http://localhost:8000/**` 由 Playwright `page.route` 攔截回合成 fixture。未讀 `.env*`、未碰 `backend/data/`、未執行 `.bat`、未用真實 DB、無真實持倉。
- Playwright：`/opt/node-tools/node_modules/playwright/index.js`；Chromium：`/opt/pw-browsers/chromium-1243/chrome-linux64/chrome`。
- provenance（stdout 原文）：`playwrightModule` = `/opt/node-tools/node_modules/playwright/index.js`、`chromiumExecutable` = `/opt/pw-browsers/chromium-1243/chrome-linux64/chrome`、`trustedPrefix` = `/opt/`。runner 開頭 fail-closed 斷言通過（stdout 未以 `e2e-fallback: ABORT` 開頭，exit 0，stderr 空）。
- 截圖：deviceScaleFactor 1、viewport 高 900；375 與 1280 各自獨立 browser context，每個情形各開一頁。

## 1. 跑法與產出檔
- 指令：`cd <SP> && PW_CHROME=/opt/pw-browsers/chromium-1243/chrome-linux64/chrome OUT_DIR=<SP> BASE_URL=http://localhost:3101 NODE_PATH=/opt/node22/lib/node_modules:/opt/node-tools/node_modules node runner.js > stdout.txt 2> stderr.txt`
- 檔案（皆在 `<SP>/`）：`runner.js`、`genfix.mts`、`rtf.mts`、`fixtures.json`、`stdout.txt`（= `raw-output.json`）、`stderr.txt`、`summary.txt`（由 raw-output 抽出的可讀版，內容未改寫）、`next-dev.log`、`shots/`（18 張 png）。
- 腳本只跑一次，沒有改過。runner 內有一個沒用到的殘留變數 `bh`（一個沒被使用的 locator），不影響輸出。

## 2. Fixture（全為合成資料）
- `/health`：`{status:"ok", service:"synthetic", as_of:"2026-11-25T02:00:00Z"}`。
- `/api/settings`（GET）：依 `SettingsResponse` 型別構造。risk_budget：max_position_weight 0.15、max_sector_weight 0.3、max_gross_exposure 1、max_loss_per_trade 0.02、atr_stop_multiple 2、kelly_fraction_cap 0.25、kelly_position_cap 0.1；cost_model `verified_on: null`；alerts `enabled: true`；net_worth view `freshness: "absent"`；`settings_fallback: null`、`cap1_migration: null`。
- `/api/backtest`（POST）：依 `BacktestResponse` 型別構造。做法是把 repo 內既有測試 fixture `app/backtest/__tests__/roundTripFixtures.ts` 的 `makeResponse()` 複製到 scratchpad（`rtf.mts`，原檔未動），用 `node --experimental-strip-types` 產出 JSON（`genfix.mts`），再把 `notes` 改成 `["synthetic note one","synthetic note two"]`。其餘沿用該 fixture：`rates_verified: false`、`data_warning: null`、`curves: null`、`metric_labels` 是占位字串 `<win-rate-label>`／`<round-trips-label>`、`notes` 內為英文占位字。
- `/api/alerts/events`：兩筆，`rule_id`/`id` 1 與 2，symbol 2330、market TW、`acknowledged: false`。
  - (a) `price_above`，observed = `{close: 605, threshold: 600, currency: "TWD", bar_as_of: "2026-11-24"}`。
  - (b) `signal_condition`，observed = `{"rsi14.last": 71.2, threshold: 70, signals_as_of: "2026-11-24"}`。
- `/api/alerts`：`{items: [], as_of}`。其餘 `/api/*` 回 404 `{"detail":"no fixture"}`。

## 3. 情形 1：設定頁「風險預算」說明句（頁面 `/settings`）
- 選取器：區塊 `section:has(> h2:text-is("風險預算（RiskBudget）"))`；說明句 該區塊內 `p:has-text("除 ATR 停損倍數外")`。matchCount：區塊 1、說明句 1（375 與 1280 相同）。
- innerText（逐字，375 與 1280 一致，程式比對為 true）：
```
除 ATR 停損倍數外，每一項數字都是分數（例如 0.15 = 15%）。
```
- class：`mt-1 text-xs text-neutral-500`
- computed style（兩寬度相同）：color `oklch(0.556 0 none)`、fontSize `12px`、fontWeight `400`、display `block`、lineHeight `16px`、marginTop `4px`、borderTopWidth `0px`、backgroundColor `rgba(0, 0, 0, 0)`。
- 區塊 innerText 開頭（逐字，前 200 字）：`風險預算（RiskBudget）` / 空行 / 上列說明句 / 空行 / `單一標的佔比上限` / 空行 / `此標的市值占總資產(已估值部位市值,不含現金)的上限（比例，例如 0.15 代表 15%）。預設值：0.1` / 空行 / `硬性上界 0.5：單一標的超過總資產(已估值部位市值,不含現金)的一半時，分散化已無實質意義。放寬需修改程式碼並經風控與 CEO 同意。` / 空行 / `單一產業佔比上限`。
- 橫向捲動：375 → scrollWidth 375 / clientWidth 375（body 375）；1280 → 1280 / 1280（body 1280）。
- 截圖：`<SP>/shots/375-case1-section.png`、`<SP>/shots/375-case1-fullpage.png`、`<SP>/shots/1280-case1-section.png`、`<SP>/shots/1280-case1-fullpage.png`
- console（兩寬度相同）：
  - `[info] %cDownload the React DevTools for a better development experience: https://react.dev/link/react-devtools font-weight:bold`
  - `[log] [HMR] connected`
  - `[error] Failed to load resource: the server responded with a status of 404 (Not Found)`（對應下方 `/api/directory/search` 無 fixture）
- requestfailed：空（兩寬度）。
- network（兩寬度相同，前端靜態資源之外的 `:8000` 請求）：
```
200 GET http://localhost:3101/settings
200 GET http://localhost:8000/api/alerts
200 GET http://localhost:8000/api/settings
404 GET http://localhost:8000/api/directory/search?q=0&limit=1
```
  （另有 `localhost:3101` 的 `_next/static/*`、`icon.svg` 皆 200，完整清單見 `summary.txt`。）

## 4. 情形 2：回測報告、費率未查證（頁面 `/backtest`）
- 互動：填 `#bt-symbol`=`2330`、`#bt-start`=`2024-01-01`、`#bt-end`=`2026-07-20`（其餘欄位用預設），點 `button:text-is("執行回測")`，由攔截回 fixture。
- 選取器與 matchCount（375 與 1280 相同）：
  - 警示框 `p[role="alert"]:has-text("費率未查證")`：1
  - 頁面全部 `[role="alert"]`：2（另一個不在報告區塊的子元素清單內，來源未查證，見第 8 節）
  - Buy & Hold 句 `p` hasText `Buy & Hold 為同期間、未計交易成本的被動持有基準。`：2
  - 表頭 `th` hasText `Buy & Hold`：2
  - 報告區塊 `section:has(> div > h2:has-text("回測報告"))`：1
- 警示框 innerText（逐字，兩寬度一致）：
```
費率未查證：本次回測使用的手續費／交易稅／滑價率尚未對照主要來源查證，報告數字應視為待查證狀態。
```
- class：`mt-3 rounded-md border border-amber-800 bg-amber-950/40 px-4 py-2 text-sm text-amber-300`
- computed style（兩寬度相同）：color `oklch(0.879 0.169 91.605)`、fontSize `14px`、fontWeight `400`、display `block`、borderTopWidth `1px`、borderTopStyle `solid`、四邊 borderColor `oklch(0.473 0.137 46.201)`、borderTopLeftRadius `6px`、backgroundColor `oklab(0.279 0.0538405 0.0550473 / 0.4)`、paddingTop `8px`、paddingLeft `16px`、marginTop `12px`、lineHeight `20px`。
- DOM 前後兄弟（父層 `section`，共 14 個子元素，警示框 index 4）：
  - previousSibling：`<p class="mt-2 rounded-md border border-neutral-700 bg-neutral-900/60 px-4 py-2 text-sm text-neutral-300">`，innerText 開頭 `本回測報告呈現的所有數字皆屬歷史統計描述，不代表未來會重演。`（免責框）
  - nextSibling：`<div class="mt-2 rounded-md border border-neutral-700 bg-neutral-900/60 px-4 py-2 text-sm text-neutral-300">`，innerText 開頭 `synthetic note one` / `synthetic note two` / 空行 / `除權息資料最近同步時間：尚未同步過`（notes 清單）
  - 子元素順序（index：tag，role）：0 div（標題列）、1 p（來源）、2 div（假設框「先看以下假設…」）、3 p（免責框）、4 p role=alert（費率未查證）、5 div（notes）、6 p（曲線圖空白說明）、7 div（費率格）、8 p（Walk-forward）、9 p（unattributed_tail）、10 div（樣本內）、11 div（樣本外）、12 section、13 section。逐項 class 與 innerText 開頭見 `summary.txt`。因 `data_warning` 為 null，報告內沒有 data_warning 警示框。
- Buy & Hold 句（兩個樣本段各一，4 個值在 375 與 1280 一致）：
  - innerText：`Buy & Hold 為同期間、未計交易成本的被動持有基準。`
  - textContent：`Buy & Hold 為同期間、未計交易成本的被動持有基準。`
  - innerHTML：`Buy &amp; Hold 為同期間、未計交易成本的被動持有基準。`
  - 兩個樣本段的此句 innerText 完全相同。class 為 `mt-1 text-xs text-neutral-500`（由 style 推得：12px、`oklch(0.556 0 none)`、marginTop 4px）。
  - 表頭 `th` innerText：`Buy & Hold`、`Buy & Hold`。
- 橫向捲動：375 → 375 / 375（body 375）；1280 → 1280 / 1280。
- 截圖：`<SP>/shots/375-case2-alert.png`、`375-case2-report-block.png`、`375-case2-fullpage.png`、`1280-case2-alert.png`、`1280-case2-report-block.png`、`1280-case2-fullpage.png`（皆在 `<SP>/shots/`）。
- console（兩寬度相同）：`[info] %cDownload the React DevTools ...`、`[log] [HMR] connected`。無 error。
- requestfailed：空。
- network（`:8000`）：`200 POST http://localhost:8000/api/backtest`。頁面與 `_next/static/*` 皆 200。

## 5. 情形 3：有待處理的警示事件
- 讀碼結果：`PendingAlertsPanel` 這個元件已從首頁退役。`app/components/PendingAlertsPanel.tsx` 現在只匯出 `AlertEventList`（事件列 markup），由 `app/components/AlertStatusStrip.tsx` 在「有事件」狀態重用，`AlertStatusStrip` 掛在首頁 `app/page.tsx`。所以事件列實際出現在首頁 `/`，不是獨立的 `PendingAlertsPanel` 面板。首頁需要 `/health` 回 200 才會渲染該區。
- 選取器：事件列 `li:has(button:text-is("標記已處理"))`；observed 行 該列內 `p.text-xs`；外框 `div:has(> ul > li:has(button:text-is("標記已處理")))`。matchCount：事件列 2、observed 行 2、外框 1（兩寬度相同）。
- observed 行 innerText（逐字，兩寬度一致；全形空格 U+3000 為分隔）：
  - (a) 價格門檻事件：`最新收盤價: 605　threshold: 600　currency: TWD　bar_as_of: 2026-11-24`
  - (b) signal_condition 事件：`14 日 RSI 最新值: 71.2　threshold: 70　signals_as_of: 2026-11-24`
- 整列 innerText（逐字）：
  - (a)：`2330（TW）・價格高於門檻` / `2026/11/25 09:30（台北時間）` / 空行 / `synthetic price threshold event` / 空行 / 上列 observed 行 / 空行 / `標記已處理`
  - (b)：`2330（TW）・訊號條件` / `2026/11/25 09:30（台北時間）` / 空行 / `synthetic signal condition event` / 空行 / 上列 observed 行 / 空行 / `標記已處理`
- observed 行 class：`mt-1 text-xs text-neutral-500`；computed style（兩列、兩寬度相同）：color `oklch(0.556 0 none)`、fontSize `12px`、fontWeight `400`、display `block`、lineHeight `16px`、marginTop `4px`。
- 橫向捲動：375 → 375 / 375；1280 → 1280 / 1280。
- 截圖（`<SP>/shots/`）：`375-case3-row1.png`、`375-case3-row2.png`、`375-case3-strip.png`、`375-case3-fullpage.png`、`1280-case3-row1.png`、`1280-case3-row2.png`、`1280-case3-strip.png`、`1280-case3-fullpage.png`。
- console（兩寬度相同）：`[info] %cDownload the React DevTools ...`、`[log] [HMR] connected`，加 3 筆 `[error] Failed to load resource: the server responded with a status of 404 (Not Found)`（對應下列三個無 fixture 的請求）。
- requestfailed：空。
- network（`:8000`，兩寬度相同）：
```
200 GET http://localhost:8000/health
404 GET http://localhost:8000/api/portfolio/limits
200 GET http://localhost:8000/api/alerts
200 GET http://localhost:8000/api/alerts/events?unacknowledged=true
200 GET http://localhost:8000/api/settings
404 GET http://localhost:8000/api/sectors/momentum?market=TW
404 GET http://localhost:8000/api/portfolio/summary
```
- 因 `/api/portfolio/summary` 無 fixture，首頁上方的投資組合摘要區與風險儀表呈現錯誤狀態；本次未對那些區塊取證。

## 6. dev server
- 我啟動的 PID：8937（`npm exec next dev --webpack --port 3101`），子程序 8949、8950、8961（next-server）。結束時只對這四個 PID 下 `kill`，沒有被權限系統拒絕。
- 之後 `pgrep -af next` 無任何輸出，`curl http://localhost:3101/` 回 `000`（連不上）。dev server 已停掉。

## 7. 偏離
- 首頁沒有 `PendingAlertsPanel` 面板（見第 5 節），情形 3 改在首頁的 `AlertStatusStrip` 內取事件列證據。
- 回測 fixture 沿用既有測試 fixture（`curves: null`、占位 `metric_labels`、英文占位 `notes`），所以曲線圖區顯示空白說明，標籤列用占位字。這只影響這些欄位的畫面，不影響費率警示框與 Buy & Hold 句。
- 事件 (a) 的 `rule_type` 我用 `price_above`（指令只說「價格門檻事件」，未指定是 above 或 below）。
- 「價格門檻」事件的 observed 行中，`close` 被 `signalFieldLabel` 顯示為「最新收盤價」，其餘鍵（`threshold`、`currency`、`bar_as_of`、`signals_as_of`）顯示原始鍵名；這是畫面實際字面，原樣記錄。

## 8. 沒有查證的事項
- 情形 2 頁面上 `[role="alert"]` 共 2 個，另一個不在報告區塊的子元素清單內，也沒有逐一輸出其節點；來源未查證（未驗證是否為 Next dev 的 route announcer）。
- 未顯式展開任何 `<details>` 或收合區；未測試互動後的狀態（例如點「標記已處理」）。
- 沒有逐項比對 `node_modules` 與 lockfile。
- 沒有目視檢查截圖內容；截圖僅為證據檔，判讀交 qa-e2e。
- 沒有取得 dev server 的 stdout 以外的後端 log（後端未起）。
- 全部資料為合成 fixture，沒有真實資料源參與。

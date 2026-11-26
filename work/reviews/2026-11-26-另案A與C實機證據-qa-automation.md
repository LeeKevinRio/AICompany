# 證據交件（e2e-fallback 代跑）— 另案 A 與 C — qa-automation

以 e2e-fallback 代跑，代跑者：qa-automation。本文件只列事實，不下 PASS / FAIL，判讀交 qa-e2e。
`<SP>` = `/tmp/claude-0/-home-user-AICompany/3f76d891-50d3-55e1-b39d-925b8a90241a/scratchpad/e2e-alertlabels`

## 0. 受測版本與環境
- worktree：`/home/user/AICompany/.claude/worktrees/agent-afee5c89f91a45a9a`，分支 `fix/settings-example-and-alert-labels`，HEAD = `d1f1c5b4db8a41a341db267cb218d0ecc9c0137f`。跑後 `git status --short` 無輸出，產品碼未動。未執行任何 install（`apps/stock-desk/frontend/node_modules` 本來就有；worktree 根目錄無 `node_modules`，與本次無關）。
- 前端：`npx next dev --webpack --port 3102`（於 `apps/stock-desk/frontend`），Next 16.3.3，log：`<SP>/next-dev.log`。
- 後端未起；`http://localhost:8000/**` 全由 `page.route` 攔截回合成 fixture。未讀 `.env*`、未碰 `backend/data/`、未執行 `.bat`、無真實 DB。
- Playwright：`/opt/node-tools/node_modules/playwright/index.js`；Chromium：`/opt/pw-browsers/chromium-1243/chrome-linux64/chrome`。
- provenance（stdout 原文）：`playwrightModule` = `/opt/node-tools/node_modules/playwright/index.js`、`chromiumExecutable` = `/opt/pw-browsers/chromium-1243/chrome-linux64/chrome`、`trustedPrefix` = `/opt/`。fail-closed 斷言通過（stdout 未以 `e2e-fallback: ABORT` 開頭，exit 0，stderr 空）。
- deviceScaleFactor 1、viewport 高 900；375 與 1280 各自獨立 browser context，每情形各開一頁。

## 1. 跑法與產出
- 指令：`cd <SP> && PW_CHROME=/opt/pw-browsers/chromium-1243/chrome-linux64/chrome OUT_DIR=<SP> BASE_URL=http://localhost:3102 NODE_PATH=/opt/node22/lib/node_modules:/opt/node-tools/node_modules node runner.js > stdout.txt 2> stderr.txt`
- 檔案（`<SP>/`）：`runner.js`、`fixtures.json`、`stdout.txt`（= `raw-output.json`，含完整 console／requestfailed／network 原始清單）、`stderr.txt`、`next-dev.log`、`shots/`（14 張 png）。
- 腳本只跑一次，沒有重跑。runner 由前例 `e2e-trim3/runner.js` 複製後改：移除回測情形與 `/api/backtest` 路由，新增 `/api/portfolio/summary`、`/api/portfolio/limits` 路由，改寫兩個情形函式，新增 observed 行的 `scrollWidth`／`clientWidth`／`overflow`／`overflowX`／`textOverflow`／`whiteSpace` 量測。原目錄未動。

## 2. Fixture（全為合成資料）
- `/health` 200；`/api/settings` GET 沿用前例 fixture（max_position_weight 0.15 等；`defaultValue` 顯示的 0.1 來自前端常數，與 fixture 無關）；`/api/alerts` 回空 items；`/api/portfolio/summary`：`status:"no_data"`、`positions:[]`、`change_mode:"close_only"`（空組合，依 `PortfolioSummaryResponse` 型別自行構造）；`/api/portfolio/limits`：`limits:[]` 等空殼（依 `PortfolioLimitsResponse` 型別自行構造）。其餘 `/api/*` 回 404 `{"detail":"no fixture"}`。
- 事件鍵已對照 `backend/app/alerts/engine.py` 第 233-238、281-287、349-352 行，三筆皆 symbol 2330、market TW、`acknowledged:false`、`triggered_at` `2026-11-25T01:30:00Z`：
  - (a) `rule_type` `price_above`，observed `{close:605, threshold:600, currency:"TWD", bar_as_of:"2026-11-24"}`
  - (b) `rule_type` `signal_condition`，observed `{field:"rsi14.last", value:28.4, op:"lt", compared_to:30, signals_as_of:"2026-11-24"}`
  - (c) `rule_type` `risk_limit_breach`，observed `{violated_limit_ids:"single_position_weight、gross_exposure", violated_count:2}`（engine 實際型別為 float(len)，fixture 的 JSON 數字 `2` 無小數點）

## 3. 情形 1（另案 A）：設定頁 `/settings`
- 選取器：區塊 `section:has(> h2:text-is("風險預算（RiskBudget）"))`；說明句 區塊內 `p:has-text("除 ATR 停損倍數外")`；欄位說明 區塊內 `p:has-text("例如 0.01 代表 1%")`。matchCount：區塊 1、說明句 1、欄位說明 1（375 與 1280 相同）。
- 說明句 innerText（逐字，兩寬度一致）：
```
除 ATR 停損倍數外，每一項數字都是分數（例如 0.01 = 1%）。
```
- 「單一標的佔比上限」欄位說明 `<p>` innerText（逐字，兩寬度一致；說明與「預設值」在同一個 `<p>`，innerText 與 textContent 相同）：
```
此標的市值占總資產(已估值部位市值,不含現金)的上限（比例，例如 0.01 代表 1%）。預設值：0.1
```
  「預設值：…」那一行即該 `<p>` 內的 `預設值：0.1`，**沒有獨立的一行元素**（讀碼 `SettingsForm.tsx:296-298` 為 `{spec.description}預設值：{String(spec.defaultValue)}` 同一個 `<p>`）。
- 該 `<p>` class `mt-1 text-xs text-neutral-500`；computed：fontSize `12px`、color `oklch(0.556 0 none)`、lineHeight `16px`、marginTop `4px`、display `block`。說明句 computed 同。
- 該 `<p>` scrollWidth／clientWidth：375 → 301 / 301；1280 → 403 / 403。
- 頁面橫向捲動：375 → scrollWidth 375 / clientWidth 375（body 375）；1280 → 1280 / 1280（body 1280）。
- 截圖（`<SP>/shots/`）：`375-case1-section.png`、`375-case1-field.png`、`375-case1-fullpage.png`、`1280-case1-section.png`、`1280-case1-field.png`、`1280-case1-fullpage.png`。
- console（兩寬度相同）：`[info] %cDownload the React DevTools for a better development experience: https://react.dev/link/react-devtools font-weight:bold`、`[log] [HMR] connected`、`[error] Failed to load resource: the server responded with a status of 404 (Not Found)`。
- requestfailed：空（兩寬度）。
- network（`:8000`，兩寬度相同）：`200 GET http://localhost:8000/api/alerts`、`200 GET http://localhost:8000/api/settings`、`404 GET http://localhost:8000/api/directory/search?q=0&limit=1`（404 對應 console 的 error）。頁面與 `_next/static/*`、`icon.svg` 皆 200，完整清單見 `<SP>/stdout.txt`。

## 4. 情形 2（另案 C）：首頁 `/` 警示事件列
- 選取器：事件列 `li:has(button:text-is("標記已處理"))`；observed 行 `li:has(button:text-is("標記已處理")) p.text-xs`。matchCount：事件列 3、observed 行 3（兩寬度相同）。
- observed 行 innerText（逐字，兩寬度一致；分隔為全形空格 U+3000）：
  - (a)：`資料日收盤價: 605　設定的門檻: 600　幣別: TWD　資料日期（日線收盤，非即時）: 2026-11-24`
  - (b)：`判斷欄位: 14 日 RSI 最新值　該欄位數值: 28.4　比較方式: 小於（<）　比較對象數值: 30　資料日期（日線收盤，非即時）: 2026-11-24`
  - (c)：`觸發的上限: 單一標的佔比上限、總曝險上限　觸發的上限數量: 2`
- 整列 innerText（逐字）：
  - (a)：`2330（TW）・價格高於門檻` / `2026/11/25 09:30（台北時間）` / 空行 / `synthetic price threshold event` / 空行 / observed 行 / 空行 / `標記已處理`
  - (b)：`2330（TW）・訊號條件` / 同時間行 / 空行 / `synthetic signal condition event` / 空行 / observed 行 / 空行 / `標記已處理`
  - (c)：`2330（TW）・風險上限被觸發` / 同時間行 / 空行 / `synthetic risk limit event` / 空行 / observed 行 / 空行 / `標記已處理`
- observed 行 class `mt-1 text-xs text-neutral-500`；computed：fontSize `12px`、color `oklch(0.556 0 none)`、lineHeight `16px`、marginTop `4px`、display `block`。
- 截斷量測（三筆、兩寬度的 `overflow`／`overflowX` 皆 `visible`、`textOverflow` 皆 `clip`、`whiteSpace` 皆 `normal`）：
  - 375：三筆 scrollWidth 283 / clientWidth 283。
  - 1280：三筆 scrollWidth 932 / clientWidth 932。
  - 未量測行高或換行行數（`whiteSpace: normal`，375 下文字是否換行未取值）。
- 頁面橫向捲動：375 → 375 / 375（body 375）；1280 → 1280 / 1280（body 1280）。
- 截圖（`<SP>/shots/`）：`375-case2-row1.png`、`-row2`、`-row3`、`375-case2-fullpage.png`、`1280-case2-row1.png`、`-row2`、`-row3`、`1280-case2-fullpage.png`。
- console（兩寬度相同）：React DevTools `[info]`、`[log] [HMR] connected`、1 筆 `[error] Failed to load resource: the server responded with a status of 404 (Not Found)`（對應 `/api/sectors/momentum?market=TW` 無 fixture）。
- requestfailed：空。
- network（`:8000`，兩寬度相同）：`200 GET /health`、`200 GET /api/portfolio/limits`、`200 GET /api/alerts`、`200 GET /api/alerts/events?unacknowledged=true`、`200 GET /api/settings`、`404 GET /api/sectors/momentum?market=TW`、`200 GET /api/portfolio/summary`（皆 `http://localhost:8000` 開頭）。

## 5. dev server
- 我啟動的 PID 3653（`npm exec next dev --webpack --port 3102`），子程序 3665、3666、3677（next-server）。結束時只對這四個 PID 下 `kill`。
- 過程中我第一次的收尾指令（含 `pkill -f "next-server"`）被權限系統拒絕，該指令**完全沒有執行**；我改為只 kill 上述四個 PID，這次沒被拒。之後 `ps` 無任何 next 程序，`curl http://localhost:3102/` 連不上（exit 7，000）。dev server 已停。

## 6. 偏離
- 首頁 `/api/portfolio/summary`、`/api/portfolio/limits` 的 fixture 是我依型別自行構造的空殼；上方組合區在此 fixture 下的呈現，本次未取證。
- 情形 1 的「預設值」沒有獨立元素，故以同一個 `<p>` 的 innerText 呈現（見第 3 節）。
- 沒有重跑腳本，沒有改動受測應用。

## 7. 沒有查證的事項
- 未目視檢查截圖內容；截圖僅為證據檔，判讀交 qa-e2e。
- `/api/sectors/momentum`、`/api/directory/search` 仍無 fixture（404）。
- 未驗證 `alertObservedLabels` 對其他鍵的顯示；未測試點擊「標記已處理」後的狀態。
- 未量測 375 下 observed 行是否換行、行高。
- 全部資料為合成 fixture，無真實資料源。截圖只存於 `<SP>/shots/`，未複製到他處。

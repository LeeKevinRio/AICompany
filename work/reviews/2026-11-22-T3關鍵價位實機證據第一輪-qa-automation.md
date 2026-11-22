# 證據交件（e2e-fallback 代跑）— qa-automation

以 e2e-fallback 代跑，代跑者：qa-automation。本文件只列事實，不下 PASS / FAIL，判讀交 qa-e2e。

## 0. 受測版本
- 分支 `fix/keylevels-nonpositive-bars`，worktree HEAD = `49c2ca3259d0ddaa334a55419f40aa9624af70b0`（detached，`git status --short` 無輸出，產品碼未動）。
- 受測前端：`apps/stock-desk/frontend`（Next 16.3.3 / React 19.2.8）。

## 1. 前端啟動方式與環境
- 指令（於 worktree 的 `apps/stock-desk/frontend`）：`npx next dev --webpack --port 3100`（即 `npm run dev` 的同一指令，只是把 port 3000 改成 3100）。log：`/tmp/claude-0/-home-user-AICompany/3f76d891-50d3-55e1-b39d-925b8a90241a/scratchpad/e2e-t3/next-dev.log`。
- 後端沒起。前端 API 基底為預設 `http://localhost:8000`，全部由 Playwright `page.route('http://localhost:8000/**')` 攔截並以自製 fixture 回應。未碰 `apps/stock-desk/backend/data/`、未讀 `.env*`、未執行 `.bat`、未用真實 DB。
- 環境偏離（須揭露）：worktree 內原本沒有 `node_modules`。我用 `cp -a` 把主 checkout（`/home/user/AICompany/apps/stock-desk/frontend/node_modules`，唯讀來源，未改動）複製進本 worktree 的 `apps/stock-desk/frontend/node_modules`（已被 `.gitignore`，`git status` 乾淨）。沒有執行任何 install。複製進來的 next 16.3.3 / react 19.2.8 與 package.json 宣告版本一致；未逐項比對 lockfile。
- Dev server 未能由我收掉：`pkill` 被權限系統拒絕，所以 `next dev`（port 3100）仍在背景執行，請 CEO / 具權責者處理。
- Playwright：`/opt/node-tools/node_modules/playwright/index.js`（1.63.0，位於 `/opt/` 前綴內）；Chromium：`/opt/pw-browsers/chromium-1243/chrome-linux64/chrome`。附錄舊記載的 1.56.1 / chromium-1194 在本環境不存在，以第 2 節探測結果為準。`provenance` 原文見 `raw-output.json` 開頭，trustedPrefix = `/opt/`，runner 開頭 fail-closed 斷言通過（未 ABORT）。
- 截圖：deviceScaleFactor 1，viewport 高 900；375 與 1280 各自獨立 browser context。

## 2. 跑法
- runner 腳本：`/tmp/claude-0/-home-user-AICompany/3f76d891-50d3-55e1-b39d-925b8a90241a/scratchpad/e2e-t3/runner.js`
- 指令：
  `cd <scratchpad>/e2e-t3 && PW_CHROME=/opt/pw-browsers/chromium-1243/chrome-linux64/chrome OUT_DIR=$PWD BASE_URL=http://localhost:3100 NODE_PATH=/opt/node22/lib/node_modules:/opt/node-tools/node_modules node runner.js > stdout.txt 2> stderr.txt`
- 未經改寫的 stdout：`.../e2e-t3/stdout.txt`（與 `raw-output.json` 內容相同）；stderr：`.../e2e-t3/stderr.txt`（空）。
- 每個情形的頁面 URL：`http://localhost:3100/position/<symbol>?market=TW`。
- 面板選取器：`section:has(h2:text-is("關鍵價位參考"))`；決策卡選取器：`section[aria-label="決策摘要"]`。每個情形 matchCount 皆為 1。
- 腳本曾修改一次（第一次跑時正常標的面板選取器 `section:has(> h2…)` 比對為 0，改成 `section:has(h2…)`；同時把「頁面是否含價格單位」改成列出含該字串的最內層 section 標題）。以下數據皆為第二次（最終）跑的輸出。

## 3. Fixture 內容（全為合成資料，無任何真實持倉）
- 日線：80 根，日期由 2026-09-01 起逐日（含週末，純合成），open 100、high 105、low 95、volume 1000、currency TWD、source `synthetic-fixture`，close = `100 + (i % 7)`。
  - 異常標的 `9999`：第 41 根（index 40）`low: "0"`；最後一根（index 79，日期 2026-11-19）`close: "-1"`。
  - 正常標的 `8888`：未做任何改動，最後一根 close = 102，日期 2026-11-19。
- `/api/bars/<sym>`：status ok，data.status `fresh`、source `synthetic-fixture`。
- `/api/signals/<sym>`：status `insufficient_data`、reason `synthetic fixture: no signals`、signals null。
- `/api/advice/<sym>`：status ok，`held: false`、`position_ids: []`，卡片 action `add`、quantity_range 500~1000 股、1 條命中規則（`uptrend_ma_stack`）、confidence medium、無 limits_check；portfolio_context 全為 null（fx_to_twd 1）。
- `/api/positions`：`{"items": [], ...}`（空持倉，故錨點為「未持有」）。
- `/api/directory/resolve/<sym>`：`{"found": false}`（標題只顯示代號）。
- 其他 `/api/*` 回 404 `{"detail":"no fixture"}`（本次實際沒有被呼叫）。

## 4. 各情形證據

### 情形 1：375px、異常標的、面板
- 截圖：`.../e2e-t3/shots/1-375-abnormal-panel-element.png`（區塊）、`.../e2e-t3/shots/1-375-abnormal-panel-fullpage.png`（整頁）
- innerText（逐字）：
```
關鍵價位參考

目前沒有可用的日線資料，本面板無法計算任何關鍵價位。
```
- computed style：
  - section：fontSize 16px、color rgb(237, 237, 237)、display block
  - h2「關鍵價位參考」：fontSize 18px、color oklch(0.97 0 none)、display block、fontWeight 600
  - p「目前沒有可用的日線資料，本面板無法計算任何關鍵價位。」：fontSize 14px、color oklch(0.708 0 none)、display block、fontWeight 400
- 含「價格單位」字串的最內層 section：只有 `技術分析`（面板內無）。
- 頁面橫向捲動：scrollWidth 375 / clientWidth 375。
- console：`[info] %cDownload the React DevTools for a better development experience: https://react.dev/link/react-devtools font-weight:bold`、`[log] [HMR] connected`。無 error。requestfailed：空。
- network（原始）：
```
200 GET http://localhost:8000/api/signals/9999?market=TW
200 GET http://localhost:8000/api/bars/9999?market=TW
200 GET http://localhost:8000/api/advice/9999?market=TW
200 GET http://localhost:8000/api/positions
200 GET http://localhost:8000/api/directory/resolve/9999
```

### 情形 2：375px、異常標的、決策卡
- 截圖：`.../e2e-t3/shots/2-375-abnormal-card-element.png`、`.../e2e-t3/shots/2-375-abnormal-card-fullpage.png`
- innerText（逐字，空行為原樣）：
```
資料截至 11-19
未持有

未持有此標的，以最新收盤 — 試算；此數字不是任何進場暗示。

進場評估
規則評估未命中防禦型規則，建設性規則命中 1 條。 這不構成進場理由。
▸
未經歷史驗證

最新收盤

—

 

停損參考

—

 

股數參考

500 ~ 1,000 股

 

依固定規則產生的操作參考，規則與價位未經歷史驗證；可能有誤，照做也可能虧損，是否採用由你決定。日線收盤資料，非即時。
```
- 事實：決策卡內無「價格單位」字串，無「距最新收盤」字串，無百分比；「最新收盤」與「停損參考」兩格皆顯示「—」。含「價格單位」字串的最內層 section 只有 `技術分析`（頁面上方技術分析區塊的 chip；該區塊的 bars 檢查走 PriceUnitBadge，不經 computeKeyLevels）。
- computed style（前 14 筆，完整清單在 `raw-output.json` 的 `results[1].styles`）：
  - 「資料截至 11-19」span：12px、oklch(0.708 0 none)、display block
  - 「未持有」span：12px、oklch(0.708 0 none)、display block
  - 說明 p（「未持有此標的，以最新收盤 — 試算；…」）：12px、oklch(0.708 0 none)、block
  - 「進場評估」span：24px、oklch(0.828 0.111 230.318)、block、weight 700
  - 「規則評估未命中防禦型規則，建設性規則命中 1 條。」span：14px、oklch(0.922 0 none)、block
  - 「這不構成進場理由。」span：14px、oklch(0.879 0.169 91.605)、display inline、weight 600
  - 「▸」span：12px、oklch(0.708 0 none)
  - 「這個結論所依據的規則、門檻與權重，都還沒用歷史資料驗證過。」p（`<details>` 內，收合狀態下的 DOM 文字）：14px、oklch(0.708 0 none)
  - 「最新收盤」標籤 p：14px、oklch(0.708 0 none)、block
  - 「—」（收盤值）p：20px、oklch(0.97 0 none)、block、weight 700、class 含 `font-mono`
  - 「停損參考」標籤 p：14px、oklch(0.708 0 none)、block
  - 「—」（停損值）p：20px、oklch(0.97 0 none)、block、weight 700
  - 「股數參考」標籤 p：14px、oklch(0.708 0 none)、block
- 頁面橫向捲動：375 / 375。
- console、requestfailed、network：與情形 1 相同（symbol 為 9999；console 僅 React DevTools info 與 HMR log；無 error）。

### 情形 3：1280px、異常標的、面板
- 截圖：`.../e2e-t3/shots/3-1280-abnormal-panel-element.png`、`.../e2e-t3/shots/3-1280-abnormal-panel-fullpage.png`
- innerText：與情形 1 逐字相同（程式比對 `===` 為 true）。
- computed style：與情形 1 相同數值（section 16px / rgb(237, 237, 237) / block；h2 18px / oklch(0.97 0 none) / block / 600；p 14px / oklch(0.708 0 none) / block / 400）。
- 含「價格單位」字串的最內層 section：只有 `技術分析`。橫向捲動：1280 / 1280。
- console / requestfailed / network：同情形 1（無 error，5 筆 200 請求）。

### 情形 4：1280px、異常標的、決策卡
- 截圖：`.../e2e-t3/shots/4-1280-abnormal-card-element.png`、`.../e2e-t3/shots/4-1280-abnormal-card-fullpage.png`
- innerText：與情形 2 逐字相同（`===` 為 true）。
- computed style：與情形 2 相同數值（逐項見 `raw-output.json` 的 `results[3].styles`）。
- 無「價格單位」、無「距最新收盤」、無百分比；收盤與停損兩格為「—」。橫向捲動 1280 / 1280。
- console / requestfailed / network：同情形 1。

### 情形 5：375px、正常標的、面板
- 截圖：`.../e2e-t3/shots/5-375-normal-panel-element.png`、`.../e2e-t3/shots/5-375-normal-panel-fullpage.png`
- innerText（逐字）：
```
關鍵價位參考
價格單位：新台幣
收盤 102.00（2026-11-19）

收盤 102.00，位於近 80 根區間上緣。

價位階梯

本面板各參考價位由高至低排列；橫條為各價位相對基準價的百分比距離，右為高於基準價，左為低於基準價。

項目	價位	相對基準價	

+20% 固定停利
停利參考（固定算式，非分析結果）
	122.40	+20.0%	


2R（賺賠比 2:1）
停利參考（固定算式，非分析結果）
	118.32	+16.0%	


MA20
拉回觀察參考
MA20 ±3%
	103.00	+1.0%	


MA60
拉回觀察參考
MA20 ±3%
	102.95	+0.9%	


基準價（最新收盤，試算）
MA20 ±3%
	102.00	—	


近 60 日低點
拉回觀察參考
	95.00	-6.9%	


−8% 固定停損
停損參考
大字所示
	93.84	-8.0%	


2×ATR(14)
停損參考
	81.71	-19.9%	

有「MA20 ±3%」標籤的列，價位皆在該範圍內。

停損參考

93.84

▸
固定算式・未還原價・可能無法依此價成交
▸
查看計算依據
```
- computed style（節錄；完整在 `raw-output.json` 的 `results[4].styles`）：
  - h2「關鍵價位參考」：18px、oklch(0.97 0 none)、block、600
  - 價格單位 chip「價格單位：新台幣」：12px、oklch(0.87 0 none)、display block、class 含 `whitespace-nowrap rounded border border-neutral-700`
  - 「收盤 102.00（2026-11-19）」span：14px、oklch(0.708 0 none)、block
  - 「收盤 102.00，位於近 80 根區間上緣。」p：14px、oklch(0.922 0 none)、block
  - 停損值「93.84」p：20px、oklch(0.97 0 none)、block、weight 700、`font-mono`
- 含「價格單位」字串的最內層 section：`決策摘要`、`技術分析`、`關鍵價位參考`。橫向捲動 375 / 375。
- console：同前（僅 React DevTools info 與 HMR log）；requestfailed 空；network 為 8888 的 5 筆 200。

### 情形 6：1280px、正常標的、面板
- 截圖：`.../e2e-t3/shots/6-1280-normal-panel-element.png`、`.../e2e-t3/shots/6-1280-normal-panel-fullpage.png`
- innerText：與情形 5 逐字相同（`===` 為 true）。
- computed style 同情形 5 之數值（`raw-output.json` 的 `results[5].styles`）。橫向捲動 1280 / 1280。
- console / requestfailed / network：同情形 5。

## 5. 未涵蓋與限制（如實）
- 本次 advice fixture 固定為未持有（positions 空）；未涵蓋「持有」錨點的畫面。
- 本次 signals 固定為 `insufficient_data`，技術指標區沒有指標內容；未涵蓋 signals ok 的版面。
- 異常標的同時含 low=0（中段）與 close=-1（最新一根），未分別單獨跑；單一欄位的各種組合由單元測試涵蓋，不在本次實機範圍。
- 未顯式展開 `<details>`（決策卡的「▸ 未經歷史驗證」、面板的「查看計算依據」）；innerText 內的收合內容是 DOM 文字，不代表可見。
- 後端未起，所有資料為合成 fixture，沒有真實資料源參與。

## 6. 所有產出檔（絕對路徑）
- `/tmp/claude-0/-home-user-AICompany/3f76d891-50d3-55e1-b39d-925b8a90241a/scratchpad/e2e-t3/runner.js`
- `/tmp/claude-0/-home-user-AICompany/3f76d891-50d3-55e1-b39d-925b8a90241a/scratchpad/e2e-t3/stdout.txt`
- `/tmp/claude-0/-home-user-AICompany/3f76d891-50d3-55e1-b39d-925b8a90241a/scratchpad/e2e-t3/stderr.txt`
- `/tmp/claude-0/-home-user-AICompany/3f76d891-50d3-55e1-b39d-925b8a90241a/scratchpad/e2e-t3/raw-output.json`
- `/tmp/claude-0/-home-user-AICompany/3f76d891-50d3-55e1-b39d-925b8a90241a/scratchpad/e2e-t3/next-dev.log`
- 截圖目錄 `/tmp/claude-0/-home-user-AICompany/3f76d891-50d3-55e1-b39d-925b8a90241a/scratchpad/e2e-t3/shots/`，內含 12 張 png（每個情形 `-element.png` 與 `-fullpage.png` 各一）。

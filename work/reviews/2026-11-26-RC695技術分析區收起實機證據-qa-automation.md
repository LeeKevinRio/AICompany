# 證據交件（e2e-fallback 代跑）— qa-automation

以 e2e-fallback 代跑，代跑者：qa-automation。本文件只列事實，不下 PASS / FAIL，判讀交 qa-e2e。截圖只放 scratchpad，未搬動。

## 0. 受測版本與環境
- worktree `/home/user/AICompany/.claude/worktrees/agent-ac1b2db2a6f4826f8`，分支 `fix/technical-section-unusable-bars`，`git rev-parse HEAD` = `1dd244c3548cdcda923497fb2598895698eedcaf`；啟動前與結束後 `git status --short` 皆無輸出，產品碼未動。
- worktree 的 `apps/stock-desk/frontend/node_modules` 本來就存在，未安裝、未複製任何東西。
- 前端：於 `apps/stock-desk/frontend` 執行 `npx next dev --webpack --port 3104`（npx 解析到專案已有的 `node_modules/.bin/next`，Next 16.3.3；未下載任何東西）。log：`/tmp/claude-0/-home-user-AICompany/3f76d891-50d3-55e1-b39d-925b8a90241a/scratchpad/e2e-rc695/next-dev.log`。
- 後端沒起；`http://localhost:8000/**` 全由 `page.route` 攔截回合成 fixture。未讀 `.env*`、未碰 `backend/data/`、未執行 `.bat`、未用真實 DB。
- Playwright：`/opt/node-tools/node_modules/playwright/index.js`（npm root -g 為 `/opt/node22/lib/node_modules`，執行時 NODE_PATH 兩者並列）；Chromium：`/opt/pw-browsers/chromium-1243/chrome-linux64/chrome`。兩者皆在 `/opt/` 內；runner 開頭 fail-closed 斷言通過（未 ABORT）。stdout 的 provenance 原文：
```
"playwrightModule": "/opt/node-tools/node_modules/playwright/index.js",
"chromiumExecutable": "/opt/pw-browsers/chromium-1243/chrome-linux64/chrome",
"trustedPrefix": "/opt/"
```
  Playwright 版本號我沒有在本次重新查（前例記載為 1.63.0，本次未驗證）。附錄記載的 1.56.1 / chromium-1194 本環境不存在。
- 每個情形：viewport 寬 375 或 1280、高 900、deviceScaleFactor 1，375 與 1280 各用獨立 browser context。

## 1. 跑法與檔案
- fixture 產生器：`/tmp/claude-0/-home-user-AICompany/3f76d891-50d3-55e1-b39d-925b8a90241a/scratchpad/e2e-rc695/genfix.js`；fixture：`/tmp/claude-0/-home-user-AICompany/3f76d891-50d3-55e1-b39d-925b8a90241a/scratchpad/e2e-rc695/fixtures.json`
- runner：`/tmp/claude-0/-home-user-AICompany/3f76d891-50d3-55e1-b39d-925b8a90241a/scratchpad/e2e-rc695/runner.js`（主跑，三個情形）；`/tmp/claude-0/-home-user-AICompany/3f76d891-50d3-55e1-b39d-925b8a90241a/scratchpad/e2e-rc695/runner2.js`（補跑，見第 2 節）
- 指令：`cd /tmp/claude-0/-home-user-AICompany/3f76d891-50d3-55e1-b39d-925b8a90241a/scratchpad/e2e-rc695 && PW_CHROME=/opt/pw-browsers/chromium-1243/chrome-linux64/chrome OUT_DIR=$PWD BASE_URL=http://localhost:3104 NODE_PATH=/opt/node22/lib/node_modules:/opt/node-tools/node_modules node runner.js > stdout.txt 2> stderr.txt`（exit 0，stderr 空）
- 未經改寫的 stdout：`/tmp/claude-0/-home-user-AICompany/3f76d891-50d3-55e1-b39d-925b8a90241a/scratchpad/e2e-rc695/stdout.txt`（等同 `raw-output.json`）；補跑：`/tmp/claude-0/-home-user-AICompany/3f76d891-50d3-55e1-b39d-925b8a90241a/scratchpad/e2e-rc695/stdout-badstale.txt`、`/tmp/claude-0/-home-user-AICompany/3f76d891-50d3-55e1-b39d-925b8a90241a/scratchpad/e2e-rc695/raw-output-badstale.json`。
- 截圖目錄：`/tmp/claude-0/-home-user-AICompany/3f76d891-50d3-55e1-b39d-925b8a90241a/scratchpad/e2e-rc695/shots/`，命名 `<寬>-<情形>-section-closed.png`（details 收合）、`-section-open.png`（展開後）、`-fullpage.png`。情形代號：bad（情形 1）、good（情形 2）、loading（情形 3）、badstale（補跑）。
- 頁面 URL：`http://localhost:3104/position/<symbol>?market=TW`，symbol：bad=9001、good=9002、loading=9003、badstale=9004。
- 腳本調整（照實）：第一版 runner 一次就跑完；之後為補跑新增 `runner2.js`（相對 runner.js 只改三處：case 清單可由環境變數 CASES 指定、等待條件把 badstale 視同 bad、輸出檔名可由 OUT_NAME 指定），並在 genfix.js 增加 badstale fixture 後重新產生 fixtures.json（原三個情形內容未變，生成是決定性的，我沒有逐位元比對重產前後的檔案）。主跑結果未重跑。

## 2. Fixture（全為合成資料）
- 日線 80 根，日期自 2026-09-01 逐日（含週末），open 100、high 105、low 95、volume 1000、currency TWD、source `synthetic-fixture`，close = `100 + (i % 7)`；最後一根日期 2026-11-19、close 102。
- 壞值（bad / badstale）：index 40 的 `close: "0"`，index 60 的 `high: "-1"`。good / loading 無改動。
- `/api/bars`：status ok、data.status `fresh`。`/api/signals`：status ok，technical 七項（moving_averages、rsi、macd、bollinger、atr、kd、volume_zscore）皆 ok（series 為空、只有 last 值），risk 的 volatility、drawdown ok，beta insufficient_data。`/api/advice`：insufficient_data、held false。`/api/positions`：空。`/api/directory/resolve/<sym>`：`{"found": false}`。其餘 404。
- 壞值情形也給 signals ok，目的是讓「指標卡不顯示」不是因為 signals 沒資料。
- 補跑 badstale：同 bad，但 bars 與 signals 的 data 改成 `status: cached_stale`、`staleness_minutes: 125`、`is_within_ttl: false`、`reason: "synthetic stale reason"`。原因：data.status 為 fresh 時 DataMetaStatusBadge 不輸出任何文字（見下），主跑的「徽章 matchCount」會是 0 而不是收起造成的，所以補一組能顯示徽章的資料。
- 情形 3：`/api/bars/9003` 的 route 延遲 20000 ms 才回；signals、advice 正常回。量測點為頁面 domcontentloaded 且技術分析區出現後再等 3000 ms，此時 bars 請求已發出、尚無回應。

## 3. 選取器（matchCount 所用，完整輸出在 raw-output.json 的 selectors）
- 區塊：`section:has(h2:text-is("技術分析"))`（matchCount 皆 1）
- 定稿句（區塊內）：`<區塊> p:text-is("目前沒有可用的日線資料，技術分析區的圖表與指標不顯示。")`；全頁版：`p:text-is("...同句...")`
- 圖表：`<區塊> [role="img"][aria-label="日K線與均線圖"]`
- 指標列（chips）：`<區塊> [role="tabpanel"] ul:has(li)`
- 一句結論：`<區塊> p:text-matches("^近 \\d+ 根日線，收盤")`
- 指標卡：`<區塊> details h4`（含「指標速覽」「技術指標」「風險量測」三個群組標題，共 14 個 h4：7 張技術指標卡 + 4 張風險卡）
- 根數行：`<區塊> details p:text-matches("^共 \\d+ 根日線")`
- 資料來源行：`<區塊> details p:has-text("資料來源：")`；徽章：`<區塊> details p:has-text("資料來源：") > *`
- 骨架：`<區塊> .animate-pulse`

## 4. 情形 1：壞值日線（symbol 9001）

### 4.1 收合（details 未展開）狀態，375 與 1280 同
- matchCount：定稿句（區塊內）1、定稿句（全頁）1、圖表 0、指標列 0、一句結論 0、指標卡 h4 0、根數行 0、骨架 0、資料來源行 2、資料來源行內子元素（徽章）0、tabpanel 1。
- 區塊 innerText（逐字，375 與 1280 相同）：
```
技術分析
價格單位：新台幣
資料截至 11-19
日線
指標

目前沒有可用的日線資料，技術分析區的圖表與指標不顯示。

▸
詳細：七張指標卡與風險量測
```
- 截圖：`/tmp/claude-0/-home-user-AICompany/3f76d891-50d3-55e1-b39d-925b8a90241a/scratchpad/e2e-rc695/shots/375-bad-section-closed.png`、`/tmp/claude-0/-home-user-AICompany/3f76d891-50d3-55e1-b39d-925b8a90241a/scratchpad/e2e-rc695/shots/1280-bad-section-closed.png`；整頁 `375-bad-fullpage.png`、`1280-bad-fullpage.png`。

### 4.2 定稿句 computed style（兩個寬度共同）與換行
- 元素：`<p class="mt-3 text-sm text-neutral-400">`，color `oklch(0.708 0 none)`、fontSize `14px`、fontWeight `400`、lineHeight `20px`、display `block`、whiteSpace `normal`、overflowWrap `normal`、wordBreak `normal`、marginTop `12px`、textAlign `start`。
- 375：rect width 309、height 40；Range.getClientRects 的不同 top 數 = 2（top 747、767），即 2 行；scrollWidth 309 / clientWidth 309。畫面上第一行斷在「…圖表與指」，第二行為「標不顯示。」（見截圖）。
- 1280：rect width 958、height 20；不同 top 數 = 1（top 427），1 行；scrollWidth 958 / clientWidth 958。

### 4.3 展開 `<details>` 後（點 summary，details.open = true）
- matchCount（375 與 1280 相同）：資料來源行 2、資料來源行內子元素（徽章）0、指標卡 h4 0、指標速覽 0、根數行 0、定稿句 1、圖表 0、指標列 0、一句結論 0。
- 展開後的資料來源行 innerText（逐字）：`資料來源：synthetic-fixture`、`資料來源：synthetic-fixture`（共兩行，各自一個 p）。
- 展開後區塊 innerText（逐字，375 與 1280 相同）：
```
技術分析
價格單位：新台幣
資料截至 11-19
日線
指標

目前沒有可用的日線資料，技術分析區的圖表與指標不顯示。

▸
詳細：七張指標卡與風險量測

資料來源：synthetic-fixture

資料來源：synthetic-fixture

頁尾「技術分析」涵蓋本區資料來源、揭露事項與計算方式說明。
```
- 截圖：`/tmp/claude-0/-home-user-AICompany/3f76d891-50d3-55e1-b39d-925b8a90241a/scratchpad/e2e-rc695/shots/375-bad-section-open.png`、`/tmp/claude-0/-home-user-AICompany/3f76d891-50d3-55e1-b39d-925b8a90241a/scratchpad/e2e-rc695/shots/1280-bad-section-open.png`。
- 徽章事實：此 fixture 的 data.status 為 fresh，DataMetaStatusBadge 沒有輸出任何元素或文字，所以「徽章」matchCount 為 0。主視圖上「日線」「指標」旁也是空的。這不是收起造成的，good 情形同樣沒有徽章文字。為此做了 badstale 補跑（4.5）。

### 4.4 橫向捲動與 console / network
- 橫向捲動：收合與展開兩種狀態，375：docScrollWidth 375 / docClientWidth 375 / bodyScrollWidth 375 / innerWidth 375；1280：四值皆 1280。無橫向捲動。
- console 原始（375、1280 相同）：
```
[info] %cDownload the React DevTools for a better development experience: https://react.dev/link/react-devtools font-weight:bold
[log] [HMR] connected
```
- requestfailed：空（兩個寬度）。
- network 原始（localhost:8000 部分，375 與 1280 相同；另有 8 筆 localhost:3104 的頁面與 `_next/static` 資源，皆 200，完整清單在 raw-output.json 的 `network`）：
```
200 GET http://localhost:8000/api/signals/9001?market=TW
200 GET http://localhost:8000/api/bars/9001?market=TW
200 GET http://localhost:8000/api/advice/9001?market=TW
200 GET http://localhost:8000/api/positions
200 GET http://localhost:8000/api/directory/resolve/9001
```

### 4.5 補跑 badstale（symbol 9004，data.status = cached_stale）
- matchCount（收合與展開、375 與 1280 相同）：定稿句 1、圖表 0、指標列 0、一句結論 0、指標卡 h4 0、根數行 0、資料來源行 2、資料來源行內子元素（徽章）4。
- 區塊 innerText（收合，逐字）：
```
技術分析
價格單位：新台幣
資料截至 11-19
日線
快取資料
指標
快取資料

目前沒有可用的日線資料，技術分析區的圖表與指標不顯示。

▸
詳細：七張指標卡與風險量測
```
- 展開後兩行資料來源行 innerText（逐字，兩行相同）：`資料來源：synthetic-fixture快取資料，資料截至 2026-11-19（125 分鐘前取得，可能未含最近交易日）synthetic stale reason`
- 子元素 innerText（4 個，依序）：`快取資料，資料截至 2026-11-19（125 分鐘前取得，可能未含最近交易日）`、`synthetic stale reason`、同前、`synthetic stale reason`。
- 截圖：`/tmp/claude-0/-home-user-AICompany/3f76d891-50d3-55e1-b39d-925b8a90241a/scratchpad/e2e-rc695/shots/375-badstale-section-closed.png`、`375-badstale-section-open.png`、`1280-badstale-section-closed.png`、`1280-badstale-section-open.png`。
- console / requestfailed：與 4.4 相同（僅 React DevTools info 與 HMR log；requestfailed 空）。橫向捲動：375 與 1280 皆無（scrollWidth = clientWidth = 視窗寬）。

## 5. 情形 2：正常日線（symbol 9002，兩個寬度結果相同）
- matchCount：定稿句（區塊內與全頁）0、圖表 1、指標列 1、一句結論 1、指標卡 h4 14（展開後逐字列出：指標速覽、技術指標、移動平均線（MA5／MA20／MA60）、RSI（14 日相對強弱指標）、KD 隨機指標（9,3,3）、MACD（12,26,9）、布林通道（20 日，2 倍標準差）、ATR（14 日真實波幅均值）、成交量 Z 分數（20 日）、風險量測、最大回撤、目前回撤、年化波動度、Beta（相對比較基準指數的敏感度））、根數行 1、資料來源行 2、骨架 0。
- 一句結論 innerText：`近 80 根日線，收盤 102.00。`；根數行 innerText（展開後）：`共 80 根日線（2026-09-01 ~ 2026-11-19）。`
- 區塊 innerText（收合，逐字，375 與 1280 相同。注意 `\t` 為原樣，來自圖表區的空白文字）：
```
技術分析
價格單位：新台幣
資料截至 11-19
日線
指標
\t
\t

\t
\t
◐
RSI 中區帶（30–70）
◐
K 值中區帶（20–80）
◐
%B 通道內（0–1）
◐
成交量接近近期平均（|z|<2）

近 80 根日線，收盤 102.00。

▸
詳細：七張指標卡與風險量測
```
- 展開後完整 innerText（含各指標卡內文與兩行資料來源）太長，原文在 `/tmp/claude-0/-home-user-AICompany/3f76d891-50d3-55e1-b39d-925b8a90241a/scratchpad/e2e-rc695/raw-output.json` 的 `results[<375 good / 1280 good>].data.open.sectionInnerText`。資料來源行：`資料來源：synthetic-fixture` x2，無徽章（data.status = fresh）。
- 截圖：`/tmp/claude-0/-home-user-AICompany/3f76d891-50d3-55e1-b39d-925b8a90241a/scratchpad/e2e-rc695/shots/375-good-section-closed.png`、`375-good-section-open.png`、`1280-good-section-closed.png`、`1280-good-section-open.png`、整頁 `*-good-fullpage.png`。
- 橫向捲動：375 與 1280 皆無（收合與展開皆 scrollWidth = clientWidth = 視窗寬）。
- console：同 4.4（僅 React DevTools info 與 HMR log）；requestfailed 空。network 的 localhost:8000 部分同 4.4，symbol 為 9002（5 筆皆 200）。

## 6. 情形 3：日線載入中（symbol 9003，bars 延遲 20000 ms，兩個寬度結果相同）
- 區塊 innerText（逐字，details 收合）：
```
技術分析
價格單位：新台幣
指標
▸
詳細：七張指標卡與風險量測
```
- matchCount：定稿句（區塊內與全頁）0、骨架（`.animate-pulse`）1、圖表 0、指標列 0、一句結論 0、根數行 0、資料來源行 1（signals 那一行，DOM 有、details 收合）、指標卡 h4 14（signals 已回，DOM 有，details 收合所以畫面上不可見）、指標速覽 1。
- 截圖：`/tmp/claude-0/-home-user-AICompany/3f76d891-50d3-55e1-b39d-925b8a90241a/scratchpad/e2e-rc695/shots/375-loading-section-closed.png`、`/tmp/claude-0/-home-user-AICompany/3f76d891-50d3-55e1-b39d-925b8a90241a/scratchpad/e2e-rc695/shots/1280-loading-section-closed.png`、整頁 `*-loading-fullpage.png`。375 截圖可見灰色骨架塊，與左下角 Next dev 的「N」圓形指示器重疊在「詳細」列上（見第 8 節）。
- 橫向捲動：375 與 1280 皆無。本情形沒有展開 details（腳本只對 bad、good 展開）。
- console：同 4.4；requestfailed 空。
- 請求（原始，`requests` 事件）：signals、bars、advice、positions、directory 五筆都有發出；network 的回應清單只有 signals、advice、positions、directory 四筆 200，**沒有 bars 的回應**（被延遲住，量測時尚未回）。
```
200 GET http://localhost:8000/api/signals/9003?market=TW
200 GET http://localhost:8000/api/advice/9003?market=TW
200 GET http://localhost:8000/api/positions
200 GET http://localhost:8000/api/directory/resolve/9003
```

## 7. Dev server
- 我啟動的是 `npx next dev --webpack --port 3104`，npm exec 的 PID 為 16922（記在 `/tmp/claude-0/-home-user-AICompany/3f76d891-50d3-55e1-b39d-925b8a90241a/scratchpad/e2e-rc695/devserver.pid`）。
- `kill 16922` 之後 port 3104 仍回 200，因為 npx 的子行程 16935（node .../node_modules/.bin/next dev）被重新掛到 PID 1 繼續運作，其子行程 16946 為 next-server。這兩個都是我這次啟動的（命令列含本 worktree 路徑與 port 3104），我另外 `kill 16946 16935`。之後 `ps` 看不到任何 next dev / next-server 行程，`curl http://localhost:3104/` 連線被拒（curl exit 7）。已停掉。
- 全程沒有用 pkill。

## 8. 偏離與未查證事項
- 前例的 fixture 沒有沿用：前例 e2e-t3 目錄在 scratchpad 已不存在，runner 與 fixture 是依 e2e-f1、e2e-trim3 的骨架與本次需求重寫，不是複製 e2e-t3。
- 補跑 badstale 與 `runner2.js` 不在你要求的清單內，是我加的（理由見第 2 節）。
- 用 Range.getClientRects 的不同 top 數當作「行數」，另有 rect 高度（40px / 20px，lineHeight 20px）可交叉；沒有用肉眼逐行核對以外的方法。
- 畫面左下角的圓形「N」是 Next dev 的 dev indicator，只在 dev server 出現，截圖會遮到靠左下的內容，非產品元素。沒有嘗試關掉它。
- 指標卡 matchCount 以 `details h4` 計，含三個群組標題；若判讀者要用「卡」的另一個定義，請用 raw-output.json 的 h4Titles 自行算。
- signals 的 series 為空陣列，圖表（lightweight-charts canvas）在 good 情形有掛載，但沒有驗證 canvas 內畫了什麼，也沒有 MA 疊線（均線資料不足的提示字串 matchCount = 0，但 series 實為空）。
- 只測 TW 市場、單一日線型態；沒有測 insufficient_data、bars error、refetch error 保留舊壞值等分支，也沒有測 US 市場。
- 沒有查證 Playwright 版本號、沒有比對 lockfile 與 node_modules 版本；Next 版本取自 dev server 輸出「next-server (v16.3.3)」。
- 沒有跑 vitest / typecheck / build，也沒有看 `next-dev.log` 以外的 dev server 輸出做分析（log 在 `/tmp/claude-0/-home-user-AICompany/3f76d891-50d3-55e1-b39d-925b8a90241a/scratchpad/e2e-rc695/next-dev.log`）。
- 沒有修改任何產品碼、依賴宣告或 repo 內其他檔案；repo 內只寫了本檔。

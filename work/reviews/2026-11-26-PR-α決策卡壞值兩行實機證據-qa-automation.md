# 證據交件（e2e-fallback 代跑）— PR-α 決策卡壞值兩行

以 e2e-fallback 代跑，代跑者：qa-automation。本文件只列事實，不下 PASS / FAIL，判讀交 qa-e2e。截圖只放 scratchpad，未搬動。所有畫面資料皆為合成示範資料。

SCRATCH = `/tmp/claude-0/-home-user-AICompany/3f76d891-50d3-55e1-b39d-925b8a90241a/scratchpad/e2e-pr-alpha`（下文簡稱 `$S`）

## 0. 受測版本與環境
- worktree `/home/user/AICompany/.claude/worktrees/agent-ab70a3d6cf0357925`，分支 `fix/decision-card-unusable-bars`；`git rev-parse HEAD` = `8875f82f8f0f6009882060b2f14ed94bb3430b7b`（與指定相同）。啟動前、結束後 `git status --short` 皆無輸出，產品碼未動。
- 前端目錄是 `apps/stock-desk/frontend`（worktree 根沒有 `frontend/`），其 `node_modules` 本來就存在，未安裝、未複製任何東西。
- 前端：`cd apps/stock-desk/frontend && npx next dev --webpack --port 3105`（npx 解析到既有 `node_modules/.bin/next`，next-server v16.3.3）。log：`$S/next-dev.log`。
- 後端沒起；`http://localhost:8000/**` 全由 `page.route` 攔截回合成 fixture。未讀 `.env*`、未碰 `backend/data/`、未執行 `.bat`、未用真實 DB。
- Playwright 模組：`/opt/node-tools/node_modules/playwright/index.js`，package.json 的 version 為 `1.63.0`；Chromium：`/opt/pw-browsers/chromium-1243/chrome-linux64/chrome`。兩者皆在 `/opt/` 內，runner 開頭 fail-closed 斷言通過（未 ABORT），stderr 空，exit 0。stdout 的 provenance 原文：
```
"playwrightModule": "/opt/node-tools/node_modules/playwright/index.js",
"chromiumExecutable": "/opt/pw-browsers/chromium-1243/chrome-linux64/chrome",
"trustedPrefix": "/opt/"
```
- 每個情形：寬 375 或 1280、高 900、deviceScaleFactor 1，375 與 1280 各用獨立 browser context。

## 1. 跑法與檔案
- 指令：`cd $S && PW_CHROME=/opt/pw-browsers/chromium-1243/chrome-linux64/chrome OUT_DIR=$S BASE_URL=http://localhost:3105 NODE_PATH=/opt/node22/lib/node_modules:/opt/node-tools/node_modules PW_MODULE=/opt/node-tools/node_modules/playwright/index.js node $S/runner.js > stdout.txt 2> stderr.txt`
- fixture 產生器 `$S/genfix.js`、fixture `$S/fixtures.json`、runner `$S/runner.js`；未經改寫 stdout `$S/stdout.txt`（等同 `$S/raw-output.json`）；我另用 python 把 raw-output 摘成 `$S/summary.txt`（只是閱讀用摘要，非原始證據）。
- 截圖 `$S/shots/<寬>-<情形>-card.png`（決策卡）、`-tech-closed.png`（技術分析區，details 收合）、`-tech-open.png`（good_held、badstale_held 展開後）、`-fullpage.png`。
- 情形代號與 symbol：bad_held=9101、bad_candidate=9102、bad_noaction=9103、good_held=9104、badstale_held=9105；URL `http://localhost:3105/position/<symbol>?market=TW`。

### 腳本相對前例（`e2e-rc695`）改了什麼（照實）
- 複製後重寫，不是小修：`genfix.js` 改為產 5 個情形，新增 `advice()` 產生 held / candidate / no_action 的完整 AdviceResponse，新增 positions fixture；`runner.js` 的 `installRoutes` 改吃每個情形自己的 positions；把前例的 loading 延遲分支、`counts()` 移除；新增決策卡區塊的取字、兩格值、兩行說明的 probe（computed style、行數、是否在 `<details>`、與三格 grid 的相對位置）。
- 安全斷言段、provenance 段、`json()`、`collector()` 與前例相同。
- 與骨架差異：我用 `PW_MODULE` 傳絕對路徑（斷言仍通過），骨架預設是 bare specifier。
- 原目錄 `e2e-rc695` 未動。

## 2. Fixture（合成）
- 日線 80 根，日期自 2026-09-01 逐日，open 100、high 105、low 95、volume 1000、currency TWD、source `synthetic-fixture`，close = `100 + (i % 7)`；最後一根 2026-11-19、close 102。壞值情形：index 40 的 `close:"0"`、index 60 的 `high:"-1"`。
- bars / signals / advice 的 `data.status` 皆 `fresh`，badstale_held 三者皆 `cached_stale`、`staleness_minutes:125`、`is_within_ttl:false`、`reason:"synthetic stale reason"`。
- advice：`status:"ok"`，card.action 為 `hold`（held、candidate）或 `insufficient_data`（no_action）。
  - held：`held:true`、`position_ids:[1]`、`/api/positions` 回一筆該 symbol、market TW、quantity "1000"、avg_cost "100"、currency TWD 的持倉（anchorSource 為 `cost`）。
  - candidate：`held:false`、positions 空（anchorSource 為 `close-not-held`）。
  - no_action：card.action `insufficient_data`、`held:false`、positions 空。
  - held / candidate 的 `quantity_range` = 1000~2000、`restores_compliance:true`、basis "synthetic basis"；no_action 為 null。matched_rules 空、limits_check 空。
- 其餘端點：`/api/directory/resolve/<sym>` 回 `{"found":false}`，其他一律 404（`{"detail":"no fixture"}`）。

## 3. 選取器（matchCount 用）
- 決策卡：`section[aria-label="決策摘要"]`（matchCount 皆 1）
- 第一行：`p:text-is("「最新收盤」與「停損參考」兩格不顯示數字：目前沒有可用的日線資料。")`（卡內加前綴 `section[aria-label="決策摘要"] `；另有全頁版與 `p:has-text("兩格不顯示數字")` 部分比對版）
- 第二行：`p:text-is("本卡依規則得出的結論與「股數參考」也用到同一批日線資料，可能同樣受到影響。")`（同上；部分比對版 `p:has-text("也用到同一批日線資料")`）
- 技術分析區：`section:has(h2:text-is("技術分析"))`；定稿句：`<區塊> p:text-is("目前沒有可用的日線資料，技術分析區的圖表與指標不顯示。")` 與全頁版；圖表 `<區塊> [role="img"][aria-label="日K線與均線圖"]`；指標卡標題 `<區塊> details h4`
- 格值：`section[aria-label="決策摘要"] p:text-is("<標籤>")` 取其 nextElementSibling 的 innerText。
- 完整選取器字串與全部 matchCount 在 `$S/raw-output.json` 的每筆 `data.selectors`、`data.matchCount`。

## 4. 情形 1・壞值 + 持有（bad_held，9101）
### 決策卡 innerText（逐字，375 與 1280 相同；`\xa0` 為不可見佔位的 nbsp，`\n` 為換行）
```
資料截至 11-19\n續抱參考\n依規則\n▸\n未經歷史驗證\n\n最新收盤\n\n—\n\n\xa0\n\n停損參考\n\n—\n\n\xa0\n\n股數參考\n\n1,000 ~ 2,000 股\n\n\xa0\n\n「最新收盤」與「停損參考」兩格不顯示數字：目前沒有可用的日線資料。\n\n本卡依規則得出的結論與「股數參考」也用到同一批日線資料，可能同樣受到影響。\n\n依固定規則產生的操作參考，規則與價位未經歷史驗證；可能有誤，照做也可能虧損，是否採用由你決定。日線收盤資料，非即時。
```
（上列為 375 的原樣；1280 的 innerText 與 375 一致，原文在 raw-output.json。）
- 格值：最新收盤「—」、停損參考「—」、股數參考「1,000 ~ 2,000 股」。
- matchCount（375、1280 相同）：第一行（卡內）1、全頁 1、部分比對 1；第二行（卡內）1、全頁 1、部分比對 1。
- 兩行 computed style（兩寬度相同的欄位）：
  - 第一行 `<p class="mt-2 text-xs text-neutral-400">`：color `oklch(0.708 0 none)`、fontSize `12px`、fontWeight `400`、lineHeight `16px`、display `block`、whiteSpace `normal`、overflowWrap `normal`、wordBreak `normal`、marginTop `8px`、textAlign `start`。
  - 第二行 `<p class="mt-1 text-xs text-neutral-400">`：同上，marginTop `4px`。
- 行數（Range.getClientRects 不同 top 數）：375：第一行 2 行（top 544、560；rect 309×32）、第二行 2 行（top 580、596；rect 309×32）；scrollWidth = clientWidth = 309。1280：兩行各 1 行（rect 958×16）；scrollWidth = clientWidth = 958。
- 位置：兩行 `closest('details')` 皆為 null（不在 `<details>` 內）；父層 `SECTION`（決策卡本身）。與三格 grid 的相對位置：375 grid 底 536，第一行 top 544（差 8）、第二行 top 580（差 44）；1280 grid 底 276，第一行 top 284（差 8）、第二行差 28。兩行 top 皆大於 grid 底（`belowGrid` true）。
- 技術分析區（`<details>` 收合，detailsOpen false）：定稿句 matchCount（區塊內、全頁）皆 1；圖表 0、指標卡 h4 0。區塊 innerText（逐字）：
```
技術分析\n價格單位：新台幣\n資料截至 11-19\n日線\n指標\n\n目前沒有可用的日線資料，技術分析區的圖表與指標不顯示。\n\n▸\n詳細：七張指標卡與風險量測
```
- 橫向捲動：375 docScrollWidth 375 / docClientWidth 375；1280 兩者 1280。無橫向捲動。
- console 原始（兩寬度相同）：
```
[info] %cDownload the React DevTools for a better development experience: https://react.dev/link/react-devtools font-weight:bold
[log] [HMR] connected
[error] Failed to load resource: the server responded with a status of 404 (Not Found)
```
  該 404 是 `GET http://localhost:8000/api/leverage/9101?market=TW`：持有情形頁面會發 leverage 查詢，我的 fixture 沒給該端點所以回 404（見 network）。這是 fixture 缺口造成，不是頁面對壞值的反應；沒有進一步確認頁面在該 404 下的呈現與正式情形一致。
- requestfailed：空。
- network 原始（localhost:8000；另有 8 筆 localhost:3105 頁面與 `_next/static` 資源皆 200，完整在 raw-output.json）：
```
200 GET http://localhost:8000/api/signals/9101?market=TW
200 GET http://localhost:8000/api/bars/9101?market=TW
200 GET http://localhost:8000/api/advice/9101?market=TW
200 GET http://localhost:8000/api/positions
200 GET http://localhost:8000/api/directory/resolve/9101
404 GET http://localhost:8000/api/leverage/9101?market=TW
```
- 截圖：`$S/shots/375-bad_held-card.png`、`$S/shots/1280-bad_held-card.png`、`$S/shots/375-bad_held-tech-closed.png`、`$S/shots/1280-bad_held-tech-closed.png`、`$S/shots/375-bad_held-fullpage.png`、`$S/shots/1280-bad_held-fullpage.png`。

## 5. 情形 2・壞值 + 未持有（bad_candidate，9102）
- 決策卡 innerText（逐字，375 與 1280 相同）：
```
資料截至 11-19\n未持有\n\n未持有此標的，以最新收盤 — 試算；此數字不是任何進場暗示。\n\n進場評估\n本次未支持進場\n▸\n未經歷史驗證\n\n最新收盤\n\n—\n\n\xa0\n\n停損參考\n\n—\n\n\xa0\n\n股數參考\n\n1,000 ~ 2,000 股\n\n\xa0\n\n「最新收盤」與「停損參考」兩格不顯示數字：目前沒有可用的日線資料。\n\n本卡依規則得出的結論與「股數參考」也用到同一批日線資料，可能同樣受到影響。\n\n依固定規則產生的操作參考，規則與價位未經歷史驗證；可能有誤，照做也可能虧損，是否採用由你決定。日線收盤資料，非即時。
```
- 格值：最新收盤「—」、停損參考「—」、股數參考「1,000 ~ 2,000 股」。
- 兩行 matchCount：第一行 1、第二行 1（卡內與全頁相同）。computed style 與情形 1 逐欄相同（第一行 marginTop 8px、第二行 4px，fontSize 12px、lineHeight 16px、color `oklch(0.708 0 none)`）。
- 行數：375 各 2 行（第一行 top 610、626；第二行 646、662；rect 309×32）；1280 各 1 行（rect 958×16）。
- 位置：不在 `<details>`（closest 為 null）；belowGrid true，375 grid 底 602、第一行 top 610（差 8）、第二行差 44；1280 差 8 與 28。
- 技術分析區：收合（detailsOpen false），定稿句 matchCount 1；區塊 innerText 與情形 1 逐字相同。
- 橫向捲動：無（375/375、1280/1280）。
- console：只有 React DevTools info 與 `[HMR] connected` log（無 error）。requestfailed 空。network（8000）：signals、bars、advice、positions、directory 各一筆，皆 200（9102）；沒有 leverage 請求。
- 截圖：`$S/shots/{375,1280}-bad_candidate-{card,tech-closed,fullpage}.png`。

## 6. 情形 3・壞值 + no_action（bad_noaction，9103）
- 決策卡 innerText（逐字，375 與 1280 相同）：
```
資料截至 11-19\n未持有\n\n未持有此標的，以最新收盤 — 試算；此數字不是任何進場暗示。\n\n資料不足\n本次不提供操作評估\n\n最新收盤\n\n—\n\n\xa0\n\n停損參考\n\n—\n\n\xa0\n\n股數參考\n\n—\n\n\xa0\n\n「最新收盤」與「停損參考」兩格不顯示數字：目前沒有可用的日線資料。\n\n依固定規則產生的操作參考，規則與價位未經歷史驗證；可能有誤，照做也可能虧損，是否採用由你決定。日線收盤資料，非即時。
```
- 格值：最新收盤「—」、停損參考「—」、股數參考「—」。
- matchCount：第一行 1（卡內、全頁、部分比對皆 1）；第二行 0（卡內、全頁、部分比對皆 0）。
- 第一行 style 與情形 1 相同；375 為 2 行（top 554、570，rect 309×32），1280 為 1 行（rect 958×16）；不在 `<details>`；belowGrid true，與 grid 底差 8。
- 技術分析區：收合，定稿句 matchCount 1，區塊 innerText 與情形 1 逐字相同。
- 橫向捲動：無。console：僅 React DevTools info 與 `[HMR] connected`。requestfailed 空。network（8000）：signals、bars、advice、positions、directory 各一筆 200（9103）。
- 截圖：`$S/shots/{375,1280}-bad_noaction-{card,tech-closed,fullpage}.png`。

## 7. 情形 4・正常日線 + 持有（good_held，9104）
- 決策卡兩行說明 matchCount：第一行 0、第二行 0（卡內、全頁、部分比對皆 0）。
- 決策卡 innerText（逐字，375 與 1280 相同）：
```
資料截至 11-19\n價格單位：新台幣\n續抱參考\n依規則\n▸\n未經歷史驗證\n\n最新收盤\n\n102.00\n\n\xa0\n\n停損參考\n\n93.84\n\n距最新收盤 -8.0%\n\n▸\n固定算式・未還原價・可能無法依此價成交\n\n股數參考\n\n1,000 ~ 2,000 股\n\n\xa0\n\n依固定規則產生的操作參考，規則與價位未經歷史驗證；可能有誤，照做也可能虧損，是否採用由你決定。日線收盤資料，非即時。\n\n基準價（最新收盤）\n\n停損參考與停利參考以最新收盤 102.00（2026-11-19）為基準計算；相對成本的損益另列於下。\n\n相對成本損益 +2.0%
```
- 格值：最新收盤「102.00」、停損參考「93.84」、股數參考「1,000 ~ 2,000 股」。
- 技術分析區：定稿句 matchCount 0；收合時 detailsOpen false，區塊 innerText 開頭 `技術分析\n價格單位：新台幣\n資料截至 11-19\n日線\n指標\n\t\n\t\n…`，含「近 80 根日線，收盤 102.00。」；點 summary 展開後 detailsOpen true，圖表 matchCount 1、指標卡 h4 14。展開後截圖 `$S/shots/{375,1280}-good_held-tech-open.png`，決策卡截圖 `$S/shots/{375,1280}-good_held-card.png`。
- 橫向捲動：收合與展開皆無（375/375、1280/1280）。
- console：React DevTools info、`[HMR] connected`、`[error] Failed to load resource: the server responded with a status of 404 (Not Found)`（同情形 1，`/api/leverage/9104?market=TW` 404，fixture 缺口）。requestfailed 空。network（8000）：signals、bars、advice、positions、directory 皆 200，加 `404 GET http://localhost:8000/api/leverage/9104?market=TW`。

## 8. 情形 5・badstale（badstale_held，9105，bars/signals/advice 的 data.status 皆 cached_stale，advice 為 held）
- 決策卡 innerText（逐字，375 與 1280 相同）：
```
資料截至 11-19\n快取資料\n續抱參考\n依規則\n▸\n未經歷史驗證\n\n最新收盤\n\n—\n\n\xa0\n\n停損參考\n\n—\n\n\xa0\n\n股數參考\n\n1,000 ~ 2,000 股\n\n\xa0\n\n「最新收盤」與「停損參考」兩格不顯示數字：目前沒有可用的日線資料。\n\n本卡依規則得出的結論與「股數參考」也用到同一批日線資料，可能同樣受到影響。\n\n依固定規則產生的操作參考，規則與價位未經歷史驗證；可能有誤，照做也可能虧損，是否採用由你決定。日線收盤資料，非即時。
```
- 兩行 matchCount：第一行 1、第二行 1。style、行數、位置與情形 1 逐欄相同（375 各 2 行、1280 各 1 行；不在 `<details>`；belowGrid true）。
- 資料來源徽章：決策卡徽章列 innerText（逐字）`資料截至 11-19\n快取資料`；徽章元素 `SPAN: 快取資料`。技術分析區（收合）innerText（逐字）：
```
技術分析\n價格單位：新台幣\n資料截至 11-19\n日線\n快取資料\n指標\n快取資料\n\n目前沒有可用的日線資料，技術分析區的圖表與指標不顯示。\n\n▸\n詳細：七張指標卡與風險量測
```
  定稿句 matchCount 1（detailsOpen false）。展開後 detailsOpen true、圖表 0、指標卡 h4 0。
- 橫向捲動：收合與展開皆無。console：React DevTools info、`[HMR] connected`、一筆 404 error（`/api/leverage/9105?market=TW`，fixture 缺口）。requestfailed 空。network（8000）：signals、bars、advice、positions、directory 皆 200，加 `404 GET http://localhost:8000/api/leverage/9105?market=TW`。
- 截圖：`$S/shots/{375,1280}-badstale_held-{card,tech-open,fullpage}.png`。本情形我沒有另外抓決策卡內「資料來源：」字樣（決策卡裡沒有該字樣，只在技術分析區 details 內，展開後的逐字文字在 raw-output.json 的 `tech.open.innerText`）。

## 9. Dev server
- 我啟動：`npm exec next dev --webpack --port 3105`，PID 4493（記於 `$S/devserver.pid`），掛在 PID 1 下。結束前以 `ps -eo pid,ppid,args` 對命令列確認該 port 3105 的行程鏈為：4493（npm exec）→ 4505（sh）→ 4506（node .../node_modules/.bin/next dev）→ 4517（next-server v16.3.3），命令列皆含本 worktree 路徑與 port 3105。我逐一 `kill 4517 4506 4505 4493`，全程沒有用 pkill、沒有被拒。
- 之後 `ps` 查不到任何 next 相關行程，`curl http://localhost:3105/` 連線被拒（curl exit 7）。已停掉。

## 10. 偏離與未查證事項
- 前例 fixture 沒有直接沿用，見第 1 節「腳本改了什麼」。
- 未持有（candidate）與 no_action 的 positions 皆為空，anchorSource 為 `close-not-held`，所以卡內多出「未持有」徽章與「未持有此標的，以最新收盤 — 試算…」一句；這是 fixture 構造的結果，沒有測 anchorSource 為 `holding-unknown` / `close-unknown` 的組合。
- 持有情形的 fixture 讓頁面多發 leverage 請求並收到 404（我沒給該端點）；console 的 error 因此出現在 held 三個情形與 good_held。沒有另外補該端點重跑，未查證補上後畫面是否有差。
- 「行數」用 Range.getClientRects 的不同 top 數，另有 rect 高度（16 的倍數）可交叉，沒有用其他方法。
- 畫面左下角若出現圓形「N」是 Next dev indicator，只在 dev server 出現，非產品元素，截圖可能遮到靠左下內容；我沒有目視逐張核對每張截圖，也沒有嘗試關掉它。
- 情形 4 只比對兩行說明 matchCount、卡內逐字與技術分析區展開；沒有驗證圖表 canvas 內畫了什麼（signals 的 series 為空）。
- 只測 TW 市場、日線單一型態、`hold` 動作；沒有測 add / reduce 等其他動作、bars 為 insufficient_data / error、refetch 錯誤保留舊壞值、US 市場、bars 為空陣列。
- 沒有跑 vitest / typecheck / build，沒有讀 `next-dev.log` 做分析。
- 沒有修改任何產品碼、依賴宣告或 repo 內其他檔案；repo 內只寫了本檔。

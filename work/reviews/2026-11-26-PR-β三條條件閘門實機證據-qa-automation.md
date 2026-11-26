# 證據交件（e2e-fallback 代跑）— PR-β 三條條件閘門

以 e2e-fallback 代跑，代跑者：qa-automation。本文件只列事實，不下 PASS / FAIL，判讀交 qa-e2e。截圖只放 scratchpad，未搬動。所有畫面資料皆為合成示範資料。

`$S` = `/tmp/claude-0/-home-user-AICompany/3f76d891-50d3-55e1-b39d-925b8a90241a/scratchpad/e2e-pr-beta`

## 0. 受測版本與環境
- worktree `/home/user/AICompany/.claude/worktrees/agent-a56fbb59886a97c8a`，分支 `fix/entry-conditions-unusable-gate`。`git rev-parse HEAD` = `bf4a5fd58ee67972bae97446614dff446c44584c`（與指定相同）。啟動前 `status --short` 無輸出，結束後亦無輸出。產品碼未動。
- `apps/stock-desk/frontend/node_modules` 本來就存在，未安裝任何東西。
- 前端：`npx next dev --webpack --port 3106`（next-server v16.3.3）。PID 鏈：6864（npm exec，ppid 1）、6876（sh）、6877（node .../node_modules/.bin/next）、6888（next-server）。
- 後端沒起，`http://localhost:8000/**` 全由 `page.route` 回合成 fixture。未讀 `.env*`、未碰 `backend/data/`、未執行 `.bat`、未用真實 DB。
- Playwright 模組：`/opt/node-tools/node_modules/playwright/index.js`，package.json version `1.63.0`。Chromium：`/opt/pw-browsers/chromium-1243/chrome-linux64/chrome`。皆在 `/opt/` 前綴內，runner 開頭 fail-closed 斷言通過，stderr 空、exit 0。stdout 的 provenance 原文：
```
"playwrightModule": "/opt/node-tools/node_modules/playwright/index.js",
"chromiumExecutable": "/opt/pw-browsers/chromium-1243/chrome-linux64/chrome",
"trustedPrefix": "/opt/"
```
- 寬 375 / 1280，高 900，deviceScaleFactor 1，各用獨立 browser context。

## 1. 跑法與檔案
- 指令：`cd $S && PW_CHROME=/opt/pw-browsers/chromium-1243/chrome-linux64/chrome OUT_DIR=$S BASE_URL=http://localhost:3106 NODE_PATH=/opt/node22/lib/node_modules:/opt/node-tools/node_modules PW_MODULE=/opt/node-tools/node_modules/playwright/index.js node $S/runner.js > stdout.txt 2> stderr.txt`
- 檔案：`$S/genfix.js`、`$S/fixtures.json`、`$S/runner.js`、未經改寫 stdout `$S/stdout.txt`（等同 `$S/raw-output.json`）、`$S/next-dev.log`、`$S/devserver.pid`。`$S/summary.txt` 是我另行摘錄的閱讀用檔案，不是原始證據（內容為第二次跑的結果，已被第三次覆蓋前的版本，數字以 raw-output.json 為準）。
- 截圖在 `$S/shots/<寬>-<情形>-<部位>.png`，部位：`entry-closed`（面板，details 收合）、`entry-open`（面板，明細展開）、`footer-open`（頁尾展開）、`keylevels`、`card`（決策卡）、`tech`、`fullpage`。
- 情形：`a_last_close0`（symbol 9201）、`c_early_close0`（9202）、`normal_held`（9203）。URL `http://localhost:3106/position/<symbol>?market=TW`。

### 腳本相對前例（`e2e-pr-alpha`）改了什麼（照實）
- 複製後修改，原目錄未動。
- `genfix.js`：改成 3 個情形；RSI 由 55 改 50、z 由 0.1 改 0.5；新增每個情形的 `/api/leverage/<symbol>` fixture（`status ok`、`chapter: null`、`position_id: 1`、`index_bars_available: false`）。
- `runner.js`：`installRoutes` 新增 `/api/leverage/<symbol>`；`runCase` 整段重寫（六項觀察條件面板、頁尾、關鍵價位、決策卡、技術分析的取字與量測，另加選取器出現位置的掃描 `hitLocations`）。安全斷言、provenance、`json()`、`collector()` 與前例相同。
- 跑了 3 次：第 1 次全部情形報錯，原因是我寫的選取器 `section[aria-label="六項觀察條件"]` 同時命中面板與頁尾的同名群組（strict mode violation），把面板選取器改成加 `.rounded-lg`；第 2 次跑完；第 3 次加了 `hitLocations` 掃描，最終證據是第 3 次。
- 取字順序：先取面板（收合）→ 點開面板明細 → 點開頁尾 → 取關鍵價位、決策卡、技術分析。這三個區塊取字時，面板明細與頁尾是展開的，但各自區塊本身的 `<details>` 沒動（技術分析 `detailsOpen` 皆 false）。

## 2. Fixture（合成）
- 日線 80 根，自 2026-09-01 逐日，open 100、high 105、low 95、volume 1000、TWD、source `synthetic-fixture`，close = `100 + (i % 7)`；最後一根日期 2026-11-19、close 102。
  - (a) `bars[79].close = "0"`（最新一根）；(c) `bars[40].close = "0"`（較早一根）；normal 無壞值。
- signals：`status ok`，RSI 最新值 50、volume_zscore 0.5，其他指標合成值；advice：`status ok`、`held: true`、`position_ids: [1]`、`matched_rules: []`、`action: hold`、`quantity_range` 1000~2000；`/api/positions` 回一筆該 symbol 的持倉（quantity "1000"、avg_cost "100"）。
- bars / signals / advice 的 `data.status` 皆 `fresh`。其餘端點：`/api/directory/resolve/<sym>` 回 `{"found":false}`，`/health` 回 ok，其他 404。

## 3. 各情形結果（375 與 1280 的文字相同，差異另註）

### 3.1 情形 (a) 最新一根 close 為 0、(c) 較早一根 close 為 0
兩個情形、兩個寬度，以下事實全部相同。

**六項觀察條件面板 innerText（逐字，明細收合，預設狀態）**
```
六項觀察條件\n\n目前六條條件均無法判定。\n\n—\n—\n—\n—\n—\n—\n▸\n詳細：六條逐項明細
```
明細展開後六列（`li[aria-label]` 的 aria-label 逐字）：
```
位階：—，無法判定
收盤與 MA60：—，無法判定
距 MA20：—，無法判定
RSI(14)：—，無法判定
成交量 z：—，無法判定
防禦型規則：—，無法判定
```
展開後完整 innerText 在 `$S/raw-output.json` 的 `data.entry.openInnerText`；展開後新增的內容含 E-1 句、六列、E-2、E-3、「資料截至：日線 11-19｜指標 11-19｜規則評估 11-19」、頁尾指引句。
截圖：`$S/shots/{375,1280}-{a_last_close0,c_early_close0}-entry-closed.png`、`-entry-open.png`。

**三條各自狀態文字（動能 / 成交量 / 規則）**：`RSI(14)：—，無法判定`、`成交量 z：—，無法判定`、`防禦型規則：—，無法判定`。每列 innerText：`—\nRSI(14)\n30–70（不含端點）\n—\n無法判定`、`—\n成交量 z\n−2～2（不含端點）\n—\n無法判定`、`—\n防禦型規則\n= 0（未持有時無法判定）\n—\n無法判定`。

**matchCount（選取器逐字在 raw-output.json 的 `data.selectors`）**
| 項目 | 選取器 | matchCount |
| --- | --- | --- |
| 「目前六條條件均無法判定。」 | `p:text-is("目前六條條件均無法判定。")` | 1 |
| 計數句「6 條中成立」 | 面板內 `<面板> p:has-text("6 條中成立")`；全頁 `:text("6 條中成立")` | 0；0 |
| 「命中 0 條」 | 面板內 `<面板> :text("命中 0 條")` | 0（展開前後皆 0） |
| 「命中 0 條」 | 全頁 `:text("命中 0 條")` | 2（見下，皆不在六項觀察條件面板） |
| RSI「50」 | 面板內 `<面板> :text-is("50")`；`:text-is("50.0")`；全頁 `:text-is("50")` | 0；0；0 |
| z 值「0.5」 | 面板內 `:text-is("0.5")`；`:text-is("0.50")`；全頁 `:text-is("0.5")` | 0；0；0 |
- 面板選取器：`section[aria-label="六項觀察條件"].rounded-lg`，matchCount 1；寬鬆版 `section[aria-label="六項觀察條件"]` matchCount 2（頁尾有同名群組）。
- 全頁「命中 0 條」的 2 筆，位置由 `hitLocations.hits0` 掃出：
  - `SPAN.text-sm.text-neutral-400`，所在 section aria-label「建議卡」，文字「命中 0 條」，在未展開的 `<details>` 內；
  - `P.text-sm.text-neutral-400`，文字「規則共 0 條，可評估 0 條，命中 0 條，資料完整度 100.00%。」，在未展開的 `<details>` 內。
  - 這兩筆是建議卡，不是六項觀察條件面板。我沒有點開建議卡的 details，也沒有對它做其他驗證。

**頁尾（點開「本頁揭露與計算依據」後；details 展開前 `open=false`、後 `open=true`）**
- RC-860 全文「未持有此標的，或持有狀態未定時，本條一律無法判定，不因未命中而視為成立；沒有可用日線時，本條也無法判定。」選取器 `footer[aria-label="本頁揭露與計算依據"] span:text-is("<全文>")` matchCount 1；全頁 `:text-is("<全文>")` matchCount 1。
- RC-802 兩句在頁尾：
  - 「RSI(14) 無法取得時，本條無法判定；30、70 兩端點本身不算成立。」頁尾 matchCount 1、全頁 1；
  - 「z 值無法取得時，本條無法判定；−2、2 兩端點本身不算成立。」頁尾 matchCount 1、全頁 1。
- 三句 computed style（相同）：`class="block text-xs text-neutral-400"`、color `oklch(0.708 0 none)`、fontSize `12px`、fontWeight `400`、lineHeight `16px`、display `block`、whiteSpace `normal`、overflowWrap `normal`、wordBreak `normal`、textOverflow `clip`、overflowX / overflowY `visible`、maxWidth `none`、textAlign `start`、`title` 屬性 null。
- 截斷量測（RC-860 / RC-802 動能 / RC-802 成交量）：

| 寬 | 句 | width | rect 高 | scrollWidth / clientWidth | scrollHeight / clientHeight | 行數 | 有 overflow 的祖先 | 在視窗內 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 375 | RC-860 | 289px | 48 | 289 / 289 | 48 / 48 | 3 | 無（`ancestors: []`） | true |
| 375 | 動能 | 289px | 32 | 289 / 289 | 32 / 32 | 2 | 無 | true |
| 375 | 成交量 | 289px | 32 | 289 / 289 | 32 / 32 | 2 | 無 | true |
| 1280 | RC-860 | 938px | 16 | 938 / 938 | 16 / 16 | 1 | 無 | true |
| 1280 | 動能 | 938px | 16 | 938 / 938 | 16 / 16 | 1 | 無 | true |
| 1280 | 成交量 | 938px | 16 | 938 / 938 | 16 / 16 | 1 | 無 | true |
  - (a)(c) 兩情形的數字一致；`rect.y` 兩情形相同（375：RC-860 1432、動能 1278、成交量 1363；1280：1216、1142、1179）。
  - 行數由 `Range.getClientRects` 的不同 top 數得出。
- 頁尾截圖：`$S/shots/<寬>-<情形>-footer-open.png`。頁尾完整 innerText 在 raw-output.json `data.footer.innerText`。
- 橫向捲動：375 `docScrollWidth 375 / docClientWidth 375`；1280 皆 1280。

**同頁關鍵價位面板**（innerText 逐字）：
```
關鍵價位參考\n\n目前沒有可用的日線資料，本面板無法計算任何關鍵價位。
```
**同頁決策卡**（`section[aria-label="決策摘要"]`，innerText 逐字）：
```
資料截至 11-19\n續抱參考\n依規則\n▸\n未經歷史驗證\n\n最新收盤\n\n—\n\n\xa0\n\n停損參考\n\n—\n\n\xa0\n\n股數參考\n\n1,000 ~ 2,000 股\n\n\xa0\n\n「最新收盤」與「停損參考」兩格不顯示數字：目前沒有可用的日線資料。\n\n本卡依規則得出的結論與「股數參考」也用到同一批日線資料，可能同樣受到影響。\n\n依固定規則產生的操作參考，規則與價位未經歷史驗證；可能有誤，照做也可能虧損，是否採用由你決定。日線收盤資料，非即時。
```
**同頁技術分析區**（details 收合，`detailsOpen=false`，innerText 逐字）：
```
技術分析\n價格單位：新台幣\n資料截至 11-19\n日線\n指標\n\n目前沒有可用的日線資料，技術分析區的圖表與指標不顯示。\n\n▸\n詳細：七張指標卡與風險量測
```
截圖：`$S/shots/<寬>-<情形>-keylevels.png`、`-card.png`、`-tech.png`、`-fullpage.png`。

**console 原始輸出**（四組 context × 情形皆相同）：
```
[info] %cDownload the React DevTools for a better development experience: https://react.dev/link/react-devtools font-weight:bold
[log] [HMR] connected
```
**requestfailed**：空。
**network 原始清單**（localhost:8000，順序為收到順序；(a) symbol 9201，(c) symbol 9202）：
```
200 GET http://localhost:8000/api/signals/<sym>?market=TW
200 GET http://localhost:8000/api/bars/<sym>?market=TW
200 GET http://localhost:8000/api/advice/<sym>?market=TW
200 GET http://localhost:8000/api/positions
200 GET http://localhost:8000/api/directory/resolve/<sym>
200 GET http://localhost:8000/api/leverage/<sym>?market=TW
```
另有 8 筆 `localhost:3106` 頁面與 `_next/static` 資源，全為 200，完整在 raw-output.json。與前例不同，這次沒有 404（leverage fixture 已補）。

### 3.2 情形 3 正常日線、持有、無防禦型命中（normal_held，9203）
375 與 1280 的文字相同。

**面板 innerText（收合）**
```
六項觀察條件\n\n6 條中成立 5 條。\n\n●\n○\n●\n●\n●\n●\n▸\n詳細：六條逐項明細
```
明細展開後六列 aria-label：
```
近 80 根位階：70%，成立
收盤與 MA60：102.00 vs 102.95，未成立
距 MA20：-1.0%，成立
RSI(14)：50.0，成立
成交量 z：0.50，成立
防禦型規則：命中 0 條，成立
```
展開後完整 innerText 在 raw-output.json `data.entry.openInnerText`（含「價格單位：新台幣」行）。截圖：`$S/shots/{375,1280}-normal_held-entry-closed.png`、`-entry-open.png`。

**matchCount**：「目前六條條件均無法判定。」0；計數句面板內 `p:has-text("6 條中成立")` 1（全頁 `:text("6 條中成立")` 見 raw-output.json `matchCount.countSentenceAnyPartial`）；面板內「命中 0 條」1（全頁 3，另 2 筆在建議卡 details 內）；面板內 `:text-is("50.0")` 1、`:text-is("0.50")` 1（`:text-is("50")`、`:text-is("0.5")` 在面板內為 0，面板印的是 1 位與 2 位小數）。
**頁尾**：RC-860、RC-802 兩句各 matchCount 1；375 寬行數 3 / 2 / 2、scrollWidth = clientWidth（289）；1280 寬各 1 行、938 / 938。
**同頁**：關鍵價位、決策卡、技術分析的 innerText 在 raw-output.json（`data.keyLevels` / `data.decisionCard` / `data.tech`）。決策卡：最新收盤 102.00、停損參考 93.84、股數參考 1,000 ~ 2,000 股。
**console**：同上兩行。**requestfailed**：空。**network**：同上六筆，皆 200。
**備註**：此情形規則條件為「成立」（持有、命中 0 條）。RC-862 (f) 寫的「持有、有防禦型命中時是未成立」我沒有跑，因為指示要求的是無命中情形。

## 4. 沒有查證 / 偏離
- 沒有跑 RC-862 (b)(d)(e)(g) 與 (f) 的「有防禦型命中」「未持有」兩種。
- 沒有對照改動前版本（base commit）的畫面，所以無法說明哪些是這個分支造成的。
- 沒有點開建議卡、技術分析、關鍵價位的 `<details>`，只取預設狀態的 innerText；面板明細與頁尾是我點開的。
- `hitLocations` 回傳的 `visible: true`（含在未展開 `<details>` 內的元素）是我用 `getBoundingClientRect` 寬高 > 0 判斷的結果，對收合的 details 內容不可靠，請以 `insideClosedDetails` 為準。
- 沒有查證 leverage fixture 的 `chapter: null` 與真實後端回傳是否一致；它只是讓該請求回 200。
- `summary.txt` 不是第 3 次跑的輸出（第 3 次後沒有重產），請勿當證據。
- 沒有做視覺判讀；截圖我沒有逐張看過，只靠 innerText 與量測值。
- 沒有檢查截圖中的色彩對比、可讀性。

## 5. 收尾
- dev server 已停：只 kill 了 6888、6877、6876、6864（kill 前用 `ps -eo pid,ppid,args` 確認命令列皆含 `--port 3106` 或指向本 worktree 的 `next`，且父子關係成鏈）。kill 後 `ps` 查無 next 行程，`curl localhost:3106` 連線失敗（exit 7）。未使用 pkill，沒有被拒絕。`ss` 不存在，所以沒用它確認 port。
- 結束後 worktree `git status --short` 無輸出；repo 內只新增本檔。

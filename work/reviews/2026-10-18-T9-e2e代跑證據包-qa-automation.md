# T-9 e2e 代跑證據包（qa-automation）

- 審查者：qa-automation
- 日期：2026-10-18
- 轉存：coordinator，逐字轉存 subagent 最終回報

---

## 本次結論
T-9（commit 6e4a854）五種狀態、375 與 1280 各一輪，證據已收集完成。五種狀態都實際進入，不是靠推測：
- cost
- close-unknown
- close-not-held
- holding-unknown（positions 500）
- holding-unknown（延遲載入中）

全程沒有外連：runner 記錄的 `externalReq` 在 10 輪裡都是 `[]`，`failed` 也都是 `[]`。
本包沒有 Verdict，也沒有 BLOCKING_ISSUES，判定由 qa-e2e 負責。
資料全部是合成示範資料：2330，64 根日線，最後一根 2026-10-14，收盤 1031.5。

## 證據表
以下數字 375 與 1280 一致，除非另註。

| 項目 | cost | close-unknown | close-not-held | holding-unknown（500） | holding-unknown（延遲中） |
|---|---|---|---|---|---|
| 進入狀態的方式 | 真實 POST 持倉，均價 900 | 注入：positions 回應的 `avg_cost` 改成 `"0"` | 無持倉（positions items 為 []） | 注入：GET positions 回 500，前端重試共 2 次 | 注入：GET positions 延遲 7000ms |
| 決策卡「停損／停利」 | 1,027.50／1,039.50 | —／— | 1,027.50／1,039.50（基準價（最新收盤，試算）） | —／— | —／— |
| 面板主視圖兩個大字 | 1,027.50／1,039.50 | 1,027.50／1,039.50 | 1,027.50／1,039.50 | —／— | —／— |
| LM-117 全文在 DOM 的出現次數（dom／innerText／rawHtml，rawHtml 含 RSC script） | 0／0／0 | 0／0／0 | 0／0／0 | 1／1／1 | 1／1／1 |
| LM-117 是否在 `<details>` 外、是否緊接兩個大字 | 不適用 | 不適用 | 不適用 | `insideDetails=false`；`prevElementSibling` 是 `div.grid`，內含「停損參考／—／停利參考／—」；`nextElementSibling` 是 `<details>`；與 grid 的垂直間距 12px | 同左 |
| LM-116 在頁尾「關鍵價位參考」群組的位置 | 第 3 項（共 20 項） | 第 3 項 | 第 3 項 | 第 3 項 | 第 3 項 |
| LM-116 出現次數（dom／rawHtml） | 1／1 | 1／1 | 1／1 | 1／1 | 1／1 |
| 舊句「代表可用日線根數尚未達最低計算門檻」（dom／innerText／rawHtml；整句另掃一次） | 0／0／0 | 0／0／0 | 0／0／0 | 0／0／0 | 0／0／0 |
| 決策卡內有無 LM-116／LM-117（含片段「持倉狀態未能確定」「該項目沒有可顯示的數字」） | 皆無 | 皆無 | 皆無 | 皆無 | 皆無 |
| 375 `scrollWidth`／`clientWidth`（documentElement） | 375／375 | 375／375 | 375／375 | 375／375 | 375／375 |
| 1280 `scrollWidth`／`clientWidth` | 1280／1280 | 1280／1280 | 1280／1280 | 1280／1280 | 1280／1280 |
| 超出 viewport 的元素 | 無 | 無 | 無 | 無 | 無 |
| LM-117 字級（computed） | 不適用 | 不適用 | 不適用 | 14px，行高 20px，class `mt-3 text-sm text-neutral-300`，顏色 `lab(84.92 0 0)` | 同左 |
| LM-117 折行 | 不適用 | 不適用 | 不適用 | 375 約 2 行（高 40）；1280 約 1 行（高 20） | 同左 |
| 面板主視圖「停損參考」「停利參考」標籤字級 | 14px | 14px | 14px | 14px | 14px |
| 決策卡內「停損參考」「停利參考」標籤字級 | 14px | 14px | 14px（頁面有「—」之外的數字） | 14px | 14px |
| 面板 `<details>` 內同名小標字級 | 12px | 12px | 12px | 12px 或不存在 | 12px 或不存在 |
| LM-116 的 `li` 字級、折行 | 12px；375 約 4 行，1280 約 2 行，顏色 `lab(66.128 0 0)` | 同左 | 同左 | 同左 | 同左 |
| LM-116 是否在 `<details>` 內 | 是（頁尾整塊 `<details>`，預設收合） | 是 | 是 | 是 | 是 |

補充事實：
- `<details>` 收合時，LM-116 的 `innerText` 次數是 0，`dom` 是 1。展開後 `innerText` 是 1。
  - 收合時 `getClientRects().length > 0`，`innerText` 卻是 0，兩者不一致。
  - 我只記錄這個現象，沒有進一步判讀。
- 延遲情境的 during 快照：
  - 時間是 375 為 962ms，1280 為 979ms。
  - 此時 positions 請求已發出（310ms／295ms），仍在延遲中，尚未 continue。
  - continue 時間是 7311ms／7295ms。
  - 延遲結束後的 settled 快照，兩個大字回到 1,027.50／1,039.50，LM-117 為 0 次。
- close-unknown 與 holding-unknown 時，決策卡的「停損／停利」顯示「—」，下方只有「相對成本損益：未取得持倉成本，無法計算」，決策卡內沒有任何成因句。
- close-unknown 時，同一頁面板大字顯示 1,027.50／1,039.50。
- 面板主視圖內，LM-117 緊接在 grid 與 `<details>` 之間，沒有重複渲染。
- holding-unknown 狀態下，面板 `<details>` 內：
  - 沒有價位階梯，也沒有基準價句。
  - 2R 與 +20% 固定停利兩個小項是「—」。
  - 移動停利觀察仍是 1,026.75。

### 截圖與原始證據的完整路徑
根目錄：`/tmp/claude-0/-home-user-AICompany/3f76d891-50d3-55e1-b39d-925b8a90241a/scratchpad/e2e-t9/`

檔名格式是 `shots/<狀態>-<寬度>-<類型>.png`：
- 狀態：`cost`、`closeunknown`、`closenotheld`、`hu500`、`hudelay`
- 寬度：`375`、`1280`
- 類型：
  - `panel-main`：面板主視圖，`<details>` 全收合。
  - `panel-open`：面板，`<details>` 展開。
  - `footer-open`：頁尾「本頁揭露與計算依據」展開。
  - `page-closed`、`page-open`：整頁。
- `hudelay-*-settled-panel-main.png`：延遲結束後的面板主視圖。

例如：`/tmp/claude-0/-home-user-AICompany/3f76d891-50d3-55e1-b39d-925b8a90241a/scratchpad/e2e-t9/shots/hu500-375-panel-main.png`

其他檔案：
- 原始 runner 輸出（含完整 `innerText`、各元素 rect、字級）：`runner-cost.json`、`runner-closeunknown.json`、`runner-closenotheld.json`、`runner-hu500.json`、`runner-hudelay.json`（路徑前綴同上）
- 彙整輸出：`summary.txt`（由 `summarize.py` 產出）
- API 回應本體：`api/<狀態>-<寬度>-bodies.json`
- 腳本：`runner.js`、`run_scenario.sh`、`start_backend.sh`、`start_frontend.sh`、`stop_backend.sh`、`post_positions.sh`、`seed_cache.py`、`summarize.py`
- build 日誌：`logs/next-build.log`

我實際看過的畫面：
- `hu500-375-panel-main.png`：停損參考「—」、停利參考「—」，其下是 LM-117（折成 2 行），再下是「查看計算依據」。
- `hu500-375-footer-open.png`：頁尾「關鍵價位參考」群組第 3 項是新的 LM-116 句。

## 驗證
**Provenance**
- worktree：`/home/user/AICompany/.claude/worktrees/t9-dash-notice`。
- HEAD：`6e4a8547831d040021366d448d959e2ceb363e32`。
- 開工與收工的 `git status --porcelain --ignored`，都只有 `apps/stock-desk/frontend/tsconfig.tsbuildinfo`（原本就被 ignore）。
- 後端 `app.__file__` 指向該 worktree 的 `apps/stock-desk/backend/app/__init__.py`，詳見 `appfile-cost.txt`、`appfile-notheld.txt`。
- 儀器（取自 runner stdout 的 `provenance`，五輪一致）：
  - `playwrightModule` = `/opt/node22/lib/node_modules/playwright/index.js`
  - `chromiumExecutable` = `/opt/pw-browsers/chromium-1194/chrome-linux/chrome`
  - `trustedPrefix` = `/opt/`
  - runner 開頭有 fail-closed 前綴斷言，沒有觸發 ABORT，五輪 exit 0。
  - 照 SKILL 判準一，請 qa-e2e 以環境既定前綴另行核對。
- 沒有執行 `playwright install`。

**指令與環境**
- 前端：
  - `cp -a` 主工作目錄的 `node_modules` 進 worktree。
  - `rm -rf .next` 後執行 `npx --no-install next build`，exit 0。
  - 再用 `next start --port 3000`。
- 後端：uvicorn `--port 8000`，`BASE_URL=http://localhost:3000`。
- 兩個 scratch DB 目錄（`run-cost/`、`run-notheld/`）：
  - 每個目錄放三個 db，由三個環境變數指過去：`STOCK_DESK_DB_PATH`、`STOCK_DESK_MARKET_DB_PATH`、`STOCK_DESK_RESEARCH_DB_PATH`。
  - 合成 bars 由 `seed_cache.py` 寫入。
  - 持倉經真實的 `POST /api/positions` 建立（2330，TW，1000 股，均價 900；HTTP 201）。
- 所有行程的 `HTTP_PROXY`／`HTTPS_PROXY`／`ALL_PROXY` 都是 `http://127.0.0.1:9`（大小寫兩組），`NO_PROXY=127.0.0.1,localhost`（大小寫兩組）。
- 沒有使用 `--proxy-server`，瀏覽器用 `ctx.route` 中止所有非 loopback 請求。
- `ALPHA_VANTAGE_API_KEY`、`FINMIND_API_TOKEN` 已 unset。
- 沒有讀 `.env`。
- runner 指令是 `run_scenario.sh <label> <MODE>`：
  - `cost none`
  - `closeunknown zerocost`
  - `hu500 fail`
  - `hudelay delay`（延遲 7000ms）
  - `closenotheld none`
  - 其中 `cost`、`closeunknown`、`hu500`、`hudelay` 共用同一個有持倉的後端；`closenotheld` 另起一個無持倉的後端。
- 每輪都 375（viewport 375x812）與 1280（1280x900）各跑一次。
- 查程序用 `ps -eo pid,comm`，沒有用 `pgrep -f`。

**收工狀態**
- 已停掉前端（含 next-server 子行程 3318）與後端，`ps -eo pid,comm` 沒有殘留 node／next／uvicorn／python／chrome。
- 3000 與 8000 皆連不上（curl exit 7）。
- 已刪除 worktree 內複製的 `node_modules`、`.next`、`next-env.d.ts`。
- worktree 的 `git status --porcelain` 為空，HEAD 仍是 6e4a854。
- 主工作樹 `git status --porcelain` 為空。
- 沒有 commit，沒有修改任何 repo 檔案。
- `apps/stock-desk/backend/data/*.db` 只做 `stat`，沒有讀內容、沒有 hash。收工時：
  - `stock-desk-market.db`：98304 bytes，2026-10-04 15:09:46.826306790。
  - `stock-desk.db`：159744 bytes，2026-10-04 14:15:41.470506705。
  - 這與 B0 證據包記錄的大小與時間戳相同；本次開工前也 `stat` 過一次，數值一致。

**自我揭露與限制**
1. **close-unknown 是注入的**。
   - 後端 `POST /api/positions` 是否拒收 `avg_cost=0`，我沒有試。
   - 我在 runner 用 `ctx.route` 攔截 GET positions，把 `avg_cost` 改成 `"0"`，其餘欄位用真實回應。
   - 後端與受測程式都沒有被動過。
   - 注入內容在 `runner-closeunknown.json` 的 `positionsEvents`。
2. **500 與延遲也是注入的**，不是後端真的失敗。重試次數與間隔是前端 react-query 的行為。
3. **延遲情境的 during 快照時間點**：375 為 962ms，1280 為 979ms，都在 positions 尚未回應時。延遲 7 秒是人為製造，不代表真實使用者會遇到的長度。
4. **展開 `<details>` 的方式**：用 `document.querySelectorAll('details').forEach(d => d.open = true)` 一次展開全部，沒有逐一點擊 summary。
5. **LM-116 的「位置」指**頁尾 `section[aria-label="關鍵價位參考"]` 內 `ul > li` 的第 3 項（共 20 項）。
6. **「LM-117 緊接在兩個大字之後」的判法**：`prevElementSibling` 是含兩個大字的 `div.grid`，`nextElementSibling` 是 `<details>`。
7. **合成資料局限**：價格單調遞增，所有持有案例的損益都是正值；沒有覆蓋多批次持倉、幣別不符，也沒有 2330 以外的標的。
8. **字級量測範圍**：只量了 LM-117、LM-116、兩個標籤的 computed `font-size`、`line-height`、顏色。沒有量對比度比值，也沒有做視覺規範比對。
9. **`rawHtml` 欄位**包含 RSC payload script 內的文字，但 LM-117 與 LM-116 在各狀態的 `rawHtml` 次數與 `dom` 次數一致。
10. **runner 沒有出錯**：五輪 stderr 都是 0 bytes，沒有重跑。

## 下一步
交 qa-e2e 判定：
1. 先做儀器來源查核：以環境既定前綴 `/opt/` 比對 `provenance`。
2. 查核通過後，依上方證據表與截圖判讀。特別對照以下事實：
   - 在 `holding-unknown`（500 與延遲中）兩種狀態，LM-117 在 DOM 恰好 1 次，且在 `<details>` 外、緊接兩個大字。
   - 在 `cost`、`close-unknown`、`close-not-held`，LM-117 為 0 次。
   - LM-116 在五種狀態都是頁尾「關鍵價位參考」第 3 項，各出現 1 次；舊句在整頁 0 次。
   - 決策卡內沒有 LM-116 與 LM-117。
   - 在 `close-unknown` 與 `holding-unknown`，決策卡的「—」旁沒有成因句，這就是 frontend 回報所說的 S-1 範圍。
   - 在 `close-unknown`，面板大字顯示數值，決策卡顯示「—」。
   - 375 沒有橫向溢位；LM-117 為 14px，與「停損參考」標籤（面板主視圖與決策卡）的 14px 相同。
   - LM-116 的 `li` 是 12px，這是頁尾整體的字級；`<details>` 內同名標籤也是 12px。
3. 注入情境（close-unknown 的 `avg_cost="0"`、500、延遲）需要 qa-e2e 判斷是否採信為對應狀態的代表。

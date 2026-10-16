# T1-12 Totals null e2e 代跑證據包 — qa-automation

> 轉存：coordinator，2026-10-16，子 agent 回報逐字轉存。主工作樹的未追蹤／修改檔是 quant v0.5（待風控核對後才 commit），與代跑無關；背景 pytest 由 coordinator 啟動。

---

## 本次結論
T1-12 實機代跑已完成，no_data、partial、complete、空帳四個情境，各在 375 與 1280 寬度跑過。以下只交事實，不下 Verdict，判讀由 qa-e2e 負責。證據根目錄（下稱 `$O`）：
`/tmp/claude-0/-home-user-AICompany/3f76d891-50d3-55e1-b39d-925b8a90241a/scratchpad/e2e-t112/`

重點事實：
- no_data 時 API `totals` 的五個金額欄位全為 JSON `null`（含 `cost_twd`），不是 `"0"`。
- no_data 時四格在 375 與 1280 兩個寬度都逐字為 `—`。整頁可見文字沒有 `null`、`NaN`、`undefined`、`NT$0`。
- partial 與 complete 的數值與上一輪 A-1 相同。
- 空帳（零持倉）時 API 為 `no_data` 加五欄 `null`，畫面四格也是 `—`。

## 各部門回報（qa-automation 代跑）

### 0. Provenance 與前後狀態
- runner stdout 的 `provenance` 在八份輸出中都一樣：
  - `playwrightModule=/opt/node22/lib/node_modules/playwright/index.js`
  - `chromiumExecutable=/opt/pw-browsers/chromium-1194/chrome-linux/chrome`
  - `trustedPrefix=/opt/`
- runner 開頭保留 fail-closed 斷言，`ABORT` 未觸發，exit=0，stderr 全空。
- 開工時 HEAD 為 `192a2b6dde603c3cf73b54de35443370eee4944f`，分支 `fix/stock-desk-t1-12-totals-null`。結束時 HEAD 相同。
- worktree 的 `git status --porcelain` 前後皆為空。
- 啟動前後端時 `app.__file__` 都指向 worktree：`/home/user/AICompany/.claude/worktrees/agent-af2ae34c07c9586f7/apps/stock-desk/backend/app/__init__.py`，記錄在 `$O/appfile-{nodata,partial,complete,empty}.txt`。seed 腳本另外 assert 路徑含 `agent-af2ae34c07c9586f7`。
- 未安裝任何東西。`node_modules` 用 `cp -a` 複製，沒有 symlink。`rm -rf .next` 後執行 `npx --no-install next build`，exit=0，log 在 `$O/next-build.log`，其中有一行 `Skipping validation of types`。接著用 `next start --port 3000`。
- 啟動前 3000 與 8000 皆無監聽（用 `/proc/net/tcp` 與 curl 確認；環境沒有 `ss`）。
- 後端用主工作樹 `.venv` 的 uvicorn，`--port 8000`，`BASE_URL=http://localhost:3000`。
- 每個情境各用一份新的 scratch SQLite，在 `$O/run-{nodata,partial,complete,empty}/`。`STOCK_DESK_DB_PATH`、`STOCK_DESK_MARKET_DB_PATH`、`STOCK_DESK_RESEARCH_DB_PATH` 都指向 scratch。
- 未讀 `.env`；`ALPHA_VANTAGE_API_KEY`、`FINMIND_API_TOKEN` 已 unset。
- 所有行程 proxy 都是 `http://127.0.0.1:9`（大小寫兩組），`NO_PROXY=127.0.0.1,localhost`（大小寫兩組）。瀏覽器用 `ctx.route` 中止非 loopback 請求，沒有使用 `--proxy-server`。四情境 × 兩寬度的 `externalReq` 全為 `[]`。
- `apps/stock-desk/backend/data/*.db` 只做過前後兩次 `stat`，逐字相同：
  - `stock-desk-market.db 98304 2026-10-04 15:09:46.826306790 +0000`
  - `stock-desk.db 159744 2026-10-04 14:15:41.470506705 +0000`
  - 沒有讀、複製或取 hash。
- 資料性質：
  - 缺價是空快取加來源不可達自然產生，沒有 mock。
  - partial 與 complete 的有價資料是**合成示範資料**，用 `PriceBarCache.put` 寫入 scratch 快取，close = 基準 + 0.5×序號，來源標記 `twse`，非真實行情。2330 基準 1000、2317 基準 200，最後一根 bar 日期 2026-10-14。
  - 持倉全部走真實的 `POST /api/positions`（HTTP 201）。

### 1. 腳本（皆在 `$O`，全文可讀）
`runner.js`、`seed_cache.py`、`start_backend.sh`、`stop_backend.sh`、`start_frontend.sh`、`post_positions.sh`、`run_scenario.sh`、`summarize.py`。

各情境的持倉：
- no_data：`2330:1000:900`、`2317:2000:150`、`0050:500:100`，不 seed。
- partial：`2330:1000:900`、`2317:2000:150`，只 seed 2330。
- complete：同 partial 的持倉，seed 2330 與 2317。
- empty：不 POST 任何持倉，不 seed。

### 2. API 原值（`$O/api/<label>-summary.txt`，curl 直取；瀏覽器收到的 body 在 `runner-<label>.json` 的 `summaryBodies`，四情境兩者一致）
**no_data**（三檔皆無快取），`totals` 逐字：
`{"cost_twd":null,"market_value_twd":null,"unrealized_pnl_twd":null,"asset_contribution_twd":null,"fx_contribution_twd":null,"status":"no_data"}`
- 三檔 `valuation` 皆為 `{"status":"insufficient_data","missing":["price"],"price":null,"fx":null,"fx_open":null,"pnl_original":null,"pnl_twd":null,"asset_contribution_twd":null,"fx_contribution_twd":null}`。
- 各檔 `market_value_twd:null`、`cost_twd:null`、`change:null`。
- http=200，耗時 7.03 秒。

**partial**：
`{"cost_twd":"900000","market_value_twd":"1031500.0","unrealized_pnl_twd":"131500.0","asset_contribution_twd":"131500.0","fx_contribution_twd":"0","status":"partial"}`
- 2330 `valuation.status:"ok"`，price `1031.5`，`as_of 2026-10-14`，`data_status:"cached_stale"`。
- 2317 `insufficient_data`、`missing:["price"]`。

**complete**：
`{"cost_twd":"1200000","market_value_twd":"1494500.0","unrealized_pnl_twd":"294500.0","asset_contribution_twd":"294500.0","fx_contribution_twd":"0","status":"complete"}`
- 兩檔皆 `ok`、`cached_stale`。

**空帳**：
- `/api/portfolio/summary` 逐字：`{"as_of":"2026-10-16T19:29:59.860785+00:00","totals":{"cost_twd":null,"market_value_twd":null,"unrealized_pnl_twd":null,"asset_contribution_twd":null,"fx_contribution_twd":null,"status":"no_data"},"positions":[],"fx_disclosures":[],"change_mode":"close_only"}`，http=200。
- `/api/positions` 逐字：`{"items":[],"as_of":"2026-10-16T19:29:59.873545+00:00"}`，http=200。

### 3. DOM 逐字與 computed color
值取自各卡標籤 `<p>` 的下一個 `<p>`；`textContent` 與 `innerText` 一致。

顏色（`getComputedStyle().color` 原樣）：
- A：`lab(96.52 -0.0000298023 0.0000119209)`，class `text-neutral-100`
- B：`lab(66.128 -0.0000298023 0.0000119209)`，class `text-neutral-400`
- C：`lab(64.4125 63.0291 19.2068)`，class `text-rose-400`

**no_data 與空帳**（375 與 1280 兩個寬度完全相同）：

| 卡 | 值逐字 | color | class |
|---|---|---|---|
| 總資產（市值） | `—` | A | `mt-1 text-3xl font-bold text-neutral-100` |
| 未實現損益 | `—` | B | `mt-1 text-3xl font-bold text-neutral-400` |
| 標的貢獻 | `—` | B | `mt-1 text-xl font-semibold text-neutral-400` |
| 匯率貢獻 | `—` | B | `mt-1 text-xl font-semibold text-neutral-400` |

- 值元素寬度（clientWidth，無溢出）：375 時前兩卡為 301，後兩卡為 309；1280 時前兩卡為 446，後兩卡為 454。
- `[role=status]` 橫幅，no_data 與空帳相同，只有一個：`所有部位皆無法估值，總計無法計算。`
- 掃描結果（可見文字 `innerText` 與 DOM 文字節點，排除 `<script>`／`<style>`），no_data 與空帳 × 兩寬度皆相同：
  - `visibleNull`、`visibleNaN`、`visibleNTD0`、`visibleUndefined` 全為 false。
  - `domNull`、`domNaN`、`domNTD0`、`domUndefined` 全為 `[]`。
  - 文字節點恰為 `0`、`0.00`、`NT$0`、`NT$0.00`、`null`、`NaN`、`undefined` 的 `exactNodes` 為 `[]`。
- no_data 的持倉列（三檔同形，只有代號不同）：
  - 375：`2330\n\n—\n資料不足\n\n查無價格資料\n\n台幣損益％\n\n—\n\n台幣損益\n\n—\n\n收盤漲跌\n\n—\n\n \n\n▸`
  - 1280：`2330\n\n—\n資料不足\n\n查無價格資料\n\n—\n\n—\n\n—\n\n \n\n▸`
  - 展開列（hidden）文字，例：`市場台股（TW）類型股票數量1,000平均成本（原幣）NT$900.00建倉日期—原幣損益—標的貢獻—匯率貢獻—到庫存修改`
- 空帳的持倉區（1280 `bodyText` 原文）：`持倉明細\n\n尚無持倉\n\n新增持倉`，`[role=row]` 為 `[]`。
- 風險儀表（no_data 與空帳）：
  - 五條都顯示 `無法評估`。
  - no_data 另有 `未納入 3 檔` 標籤，出現在第 1、2、4、5 條；空帳沒有該標籤。
  - 比值欄為 `—／15.00%`、`—／30.00%`、`—／100.00%`、`—／1.00%`、`—／—`。
  - 完整 `bodyText` 在各 `runner-*.json`。

**partial**（375 與 1280 相同）：

| 卡 | 值逐字 | color |
|---|---|---|
| 總資產（市值） | `NT$1,031,500` | A |
| 未實現損益 | `NT$131,500` | C（`text-rose-400`） |
| 標的貢獻 | `NT$131,500` | C |
| 匯率貢獻 | `NT$0` | B（`text-neutral-400`） |

- 橫幅：`部分部位無法估值，總計僅含可估值部位。`
- `visibleNTD0:true`，`exactNodes` 有 2 筆 `NT$0`：
  1. 匯率貢獻卡 `<p class="mt-1 text-xl font-semibold text-neutral-400">NT$0</p>`（可見）。
  2. 2330 展開列內 `<span class="text-neutral-400">NT$0</span>`（`hiddenAncestor:true`）。
- 其餘 null／NaN／undefined 掃描皆空。
- 持倉列：2330 為 `NT$1,031.50`、`10/14 收盤`、`資料較舊`、`+14.61%`、`NT$131,500`、`+0.05%`、`較 10/13 收盤`。2317 為 `—`、`資料不足`、`查無價格資料`，其餘 `—`。

**complete**（375 與 1280 相同）：

| 卡 | 值逐字 | color |
|---|---|---|
| 總資產（市值） | `NT$1,494,500` | A |
| 未實現損益 | `NT$294,500` | C |
| 標的貢獻 | `NT$294,500` | C |
| 匯率貢獻 | `NT$0` | B |

- 無 `[role=status]` 橫幅。
- `exactNodes` 有 3 筆 `NT$0`：匯率貢獻卡（可見）加兩檔展開列內的匯率貢獻 span（hidden）。
- 持倉列：2330 同 partial；2317 為 `NT$231.50`、`10/14 收盤`、`資料較舊`、`+54.33%`、`NT$163,000`、`+0.22%`、`較 10/13 收盤`。
- null／NaN／undefined 掃描皆空。

**橫向溢出**：四情境 × 兩寬度的 `docScrollWidth` 都等於 `innerWidth`（375／1280）。

### 4. 截圖（fullPage，皆在 `$O/shots/`）
- `nodata-375.png`、`nodata-1280.png`
- `partial-375.png`、`partial-1280.png`
- `complete-375.png`、`complete-1280.png`
- `empty-375.png`、`empty-1280.png`

我只目視看了兩張，其餘由 qa-e2e 判讀：
- `nodata-375.png`：頂端有橘色橫幅；四格皆為短橫線，無 `NT$0`；三檔持倉各有「資料不足」徽章。前兩格（text-3xl）的 `—` 看起來比後兩格（text-xl）長。
- `empty-1280.png`：橫幅加四格 `—`，持倉區顯示「尚無持倉」與「新增持倉」按鈕。

原始 runner stdout 在 `$O/runner-{nodata,partial,complete,empty}.json`，內含 provenance、四格資料、掃描結果、`rows`、`bodyText`、完整 DOM、console、response、failed、`externalReq`。

### 5. console／network 原始清單
- console（含 `pageerror`）：四情境 × 兩寬度的 `consoleAll` 全為 `[]`。
- 4xx／5xx response：無。所有 `/api/*` 皆 200。完整 response 清單在 `runner-*.json` 的 `responses`。
- `requestfailed`（`failed` 欄）：
  - 全部是 `net::ERR_ABORTED`，目標皆為 `http://localhost:3000/position/<symbol>?...&_rsc=...`（Next prefetch，頁面結束時被取消）。逐筆原文在 `runner-*.json`。
  - 空帳兩個寬度都是 `[]`。
  - 其他三情境 375 為 1～3 筆，1280 為 3～8 筆。
- 後端 log 在 `$O/backend-*.log`，前端 log 在 `$O/frontend.log`，我沒有額外判讀。

## 驗證（前後狀態與清理）
- 前後端已停：`ps -eo pid,comm` 查無 uvicorn、node、next、npm；8000 與 3000 curl 皆 000。
- 已刪除複製的 `frontend/node_modules`、`.next`、`next-env.d.ts`。
- 清理後 `git status --porcelain --ignored` 與開工前**逐行相同**（`$O/ignored-before.txt` 對 `ignored-after.txt`）。
- 後端以 `PYTHONDONTWRITEBYTECODE=1` 啟動，沒有新建 `__pycache__`。worktree 內開工前就有 24 筆 gitignored 的 `__pycache__`，加上 `.coverage`、`.mypy_cache`、`.ruff_cache`，我**沒有刪**，原樣保留。這與「刪除 `__pycache__`」的指示不同，原因是它們不是我產生的。
- worktree 的 `git status --porcelain`：空。
- **主工作樹的 `git status --porcelain` 不是空的**，這與要求不符：
  - 開工前：已有 2 筆未追蹤檔（`work/research/2026-10-16-A-15-合成計算/mc_f2b_cum.out` 與 `mc_f2b_cum.py`）。
  - 結束時：多了 1 筆 ` M work/research/2026-10-15-3日5日方向判斷-事先宣告草案.md`。
  - 我沒有碰主工作樹任何檔案；這些變動來自其他並行的行程。前後兩份記錄在 `$O/main-status-before.txt`、`main-status-after.txt`。
- 未 commit，未動受測程式、測試或依賴宣告。

## 下一步（交 qa-e2e）
- 請依 skill 第 6 節先做儀器來源查核，以既定前綴 `/opt/` 為準，不要以 `provenance.trustedPrefix` 為準。
- 請判讀 AC-B4b-4 與四個情境的證據。

## 自我揭露
1. **no_data 的 runner 跑了兩次**（後端沒重啟，`as_of` 不同）。第一次的 DOM 掃描誤把 Next 嵌在 `<script>` 裡的 RSC payload 當成 DOM 文字，掃出 31 筆 `null` 與 27 筆 `undefined`。這是我的掃描範圍寫太寬，不是畫面內容。我已把掃描改成排除 `<script>`／`<style>`／`<noscript>` 並重跑，採用第二次。第一次原始輸出保留在 `$O/runner-nodata-run1-scriptIncluded.json`。該檔的 `visible*` 欄位（只看可見文字）在兩次都是 false。
2. 切換情境時，第一次 `stop_backend.sh` 只 sleep 1 秒，舊的 nodata uvicorn（pid 19857）在 partial 啟動時仍在收尾；之後 partial 的新 uvicorn（pid 20264）正常起來。我確認 partial 的 API 與畫面都是 partial 資料，證據一致。我隨後把 stop 腳本改成等到行程結束，complete 與 empty 的切換無此現象。
3. **空帳畫面的事實**：持倉區顯示「尚無持倉」，同時頂端橫幅仍是「所有部位皆無法估值，總計無法計算。」。零持倉時也出現這句橫幅，我只記錄，不判斷是否合宜。
4. **匯率貢獻格在 partial／complete 為 `NT$0`**：API `fx_contribution_twd:"0"`，持倉都是台股。本次沒測 US 部位與匯率非 0 的情境。
5. 本輪沒有測 `cost_twd` 的畫面呈現，因為四格卡片都不顯示 `cost_twd`。我只記錄它在 no_data 與空帳的 API 為 `null`。
6. 環境沒有 `ss`。我用 `/proc/net/tcp` 與 curl 確認埠狀態，`/proc/net/tcp6` 不存在。
7. 開工時有一個非我啟動的 `python -m pytest -q -p no:cacheprovider`（pid 17436）在跑，我沒有碰它。
8. 上一輪 A-1 的證據目錄（`e2e-a1/`）在這個 scratchpad 已不存在，腳本我是參照該報告內文重寫的，欄位與做法對齊，但程式碼不是原檔。
9. 截圖與 `runner-*.json` 只留在 `$O`，按 skill 第 6 節屬一次性證據，判讀完可刪。
10. 本報告不含 Verdict 或 `BLOCKING_ISSUES`。

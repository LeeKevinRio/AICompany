# e2e-fallback 代跑證據包：A1 no_data 總額卡片（只交事實，不下 Verdict）

代跑者：qa-automation。受測：worktree `/home/user/AICompany/.claude/worktrees/agent-ad774916e922ab469`，分支 `fix/stock-desk-a1-no-data-totals`。
產出根目錄（以下簡稱 `$O`）：`/tmp/claude-0/-home-user-AICompany/3f76d891-50d3-55e1-b39d-925b8a90241a/scratchpad/e2e-a1/`

## 0. Provenance 與前後狀態
- runner stdout 的 `provenance`（六份皆相同）：`playwrightModule=/opt/node22/lib/node_modules/playwright/index.js`、`chromiumExecutable=/opt/pw-browsers/chromium-1194/chrome-linux/chrome`、`trustedPrefix=/opt/`。runner 開頭保留 fail-closed 斷言，`ABORT` 未觸發，exit=0。
- 後端 `app.__file__` = `/home/user/AICompany/.claude/worktrees/agent-ad774916e922ab469/apps/stock-desk/backend/app/__init__.py`（來自 worktree，見 `$O/appfile-*.txt`）。
- 未安裝任何東西。`node_modules` 以 `cp -a` 複製，`rm -rf .next` 後 `npx --no-install next build`（成功，log 在 `$O/next-build.log`），再 `next start --port 3000`。
- 開始前 `ps -eo pid,comm` 與 `ss` 確認 3000／8000 未占用。
- HEAD 前後皆為 `27dc826718b2a1a58cbf22a3c036ac1525e6a0b0`。
- `git status --porcelain` 前後皆為空，結束後也是。
- 主工作樹 `git status --porcelain` 為空，未動。
- `apps/stock-desk/backend/data/*.db` 只 `stat` 兩次，前後逐字相同：
  - `stock-desk-market.db 98304 2026-10-04 15:09:46.826306790 +0000`
  - `stock-desk.db 159744 2026-10-04 14:15:41.470506705 +0000`
- 沒有讀、複製、hash 或寫入這兩個 db。
- 資料庫：每個情境一份新建 scratch SQLite，在 `$O/run-nodata/`、`run-partial/`、`run-complete/`。`STOCK_DESK_DB_PATH`、`STOCK_DESK_MARKET_DB_PATH`、`STOCK_DESK_RESEARCH_DB_PATH` 都指向 scratch，uvicorn cwd 也在 scratch。
- 未讀 `.env`；`ALPHA_VANTAGE_API_KEY`、`FINMIND_API_TOKEN` 已 unset。
- 所有行程 proxy 皆為 `http://127.0.0.1:9`（大小寫兩組），`NO_PROXY=127.0.0.1,localhost`（大小寫）。
- 瀏覽器 `ctx.route` abort 非 loopback 請求：三情境 × 兩寬度的 `externalReq` 皆為空 `[]`，沒有外連嘗試。
- 未使用 Chromium `--proxy-server`。
- 資料性質：缺價為「空快取＋來源不可達」自然產生。有價資料為**合成示範資料**：`PriceBarCache.put` 寫入的合成 bars，close = 基準 + 0.5×序號，來源標記 `twse`，非真實行情。

## 1. 造資料與啟動腳本全文（皆在 `$O`）
`seed_cache.py`：
```python
"""Seed synthetic daily bars into a scratch price cache (STOCK_DESK_DB_PATH). Usage: seed_cache.py SYM [SYM ...]"""
import sys
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal

from app.data.cache import PriceBarCache
from app.data.interface import PriceBar
import app

assert "agent-ad774916e922ab469" in app.__file__, app.__file__
cache = PriceBarCache()  # path from STOCK_DESK_DB_PATH
print("cache db:", cache.db_path)
now = datetime.now(UTC)
end = date(2026, 10, 14)
days = [d for d in (end - timedelta(days=i) for i in range(90)) if d.weekday() < 5]
base = {"2330": Decimal("1000"), "2317": Decimal("200")}
for sym in sys.argv[1:]:
    p0 = base[sym]
    bars = []
    for i, d in enumerate(sorted(days)):
        c = p0 + Decimal(i) * Decimal("0.5")
        bars.append(PriceBar(symbol=sym, market="TW", date=d, open=c, high=c + 1, low=c - 1, close=c,
                             volume=1_000_000, currency="TWD", as_of=now, source="twse"))
    cache.put(bars, source="twse", fetched_at=now)
    print(sym, len(bars), "bars, last close", bars[-1].close, "on", bars[-1].date)
```
`start_backend.sh`：
```bash
#!/bin/bash
# usage: start_backend.sh <label>   (fresh scratch DBs per label)
O=/tmp/claude-0/-home-user-AICompany/3f76d891-50d3-55e1-b39d-925b8a90241a/scratchpad/e2e-a1
L=$1
WB=/home/user/AICompany/.claude/worktrees/agent-ad774916e922ab469/apps/stock-desk/backend
PY=/home/user/AICompany/apps/stock-desk/backend/.venv/bin
mkdir -p $O/run-$L; cd $O/run-$L || exit 1
rm -f ./*.db ./*.db-wal ./*.db-shm
unset ALPHA_VANTAGE_API_KEY FINMIND_API_TOKEN ALPHA_VANTAGE_DAILY_LIMIT
export HTTP_PROXY=http://127.0.0.1:9 HTTPS_PROXY=http://127.0.0.1:9 ALL_PROXY=http://127.0.0.1:9
export http_proxy=http://127.0.0.1:9 https_proxy=http://127.0.0.1:9 all_proxy=http://127.0.0.1:9
export NO_PROXY=127.0.0.1,localhost no_proxy=127.0.0.1,localhost
export STOCK_DESK_DB_PATH=$O/run-$L/stock-desk.db STOCK_DESK_MARKET_DB_PATH=$O/run-$L/market.db STOCK_DESK_RESEARCH_DB_PATH=$O/run-$L/research.db
export PYTHONPATH=$WB
shift
if [ $# -gt 0 ]; then $PY/python $O/seed_cache.py "$@" > $O/seed-$L.log 2>&1; cat $O/seed-$L.log; fi
$PY/python -c "import app; print('app.__file__', app.__file__)" | tee $O/appfile-$L.txt
nohup $PY/uvicorn app.main:app --host 127.0.0.1 --port 8000 > $O/backend-$L.log 2>&1 &
echo $! > $O/backend.pid
for i in $(seq 1 40); do curl -s -o /dev/null http://127.0.0.1:8000/health && break; sleep 0.5; done
curl -sS -w ' http=%{http_code}\n' http://127.0.0.1:8000/health
```
`post_positions.sh`（走真實的 `POST /api/positions`）：
```bash
#!/bin/bash
# usage: post_positions.sh SYM:QTY:COST ...   (TW stocks, via the real POST /api/positions)
for a in "$@"; do IFS=: read s q c <<< "$a"
  curl -sS -w ' http=%{http_code}\n' -H 'Content-Type: application/json' -X POST http://127.0.0.1:8000/api/positions \
   -d "{\"symbol\":\"$s\",\"market\":\"TW\",\"quantity\":\"$q\",\"avg_cost\":\"$c\",\"currency\":\"TWD\",\"instrument_type\":\"stock\"}"
done
```
- `start_frontend.sh`：`next start --port 3000`，同樣 proxy／NO_PROXY 環境，`NEXT_TELEMETRY_DISABLED=1`。
- `run_scenario.sh`：curl 取 `/api/portfolio/summary` 與 `/api/positions`，再以 `PW_CHROME=/opt/pw-browsers/chromium-1194/chrome-linux/chrome` 跑 runner。
- `runner.js`：骨架來自 skill 第 5 節，擴充為 375 與 1280 各開獨立 context，擷取 DOM、computed color、截圖、console、response、requestfailed。腳本全文在 `$O/runner.js`。

各情境的指令：
- no_data：`start_backend.sh nodata`（不 seed），`post_positions.sh 2330:1000:900 2317:2000:150 0050:500:100`，`run_scenario.sh nodata`。
- partial：`start_backend.sh partial 2330`，`post_positions.sh 2330:1000:900 2317:2000:150`，`run_scenario.sh partial`。
- complete：`start_backend.sh complete 2330 2317`，同上兩檔持倉，`run_scenario.sh complete`。

## 2. API 原值（`$O/api/<label>-summary.txt`，curl 直取；瀏覽器自己收到的 body 在 `runner-<label>.json` 的 `summaryBodies`）

**no_data**（持倉 2330、2317、0050，全無快取）。`totals` 逐字：
`{"cost_twd":"0","market_value_twd":"0","unrealized_pnl_twd":"0","asset_contribution_twd":"0","fx_contribution_twd":"0","status":"no_data"}`
- 三檔 `valuation` 皆為 `{"status":"insufficient_data","missing":["price"],"price":null,...}`，`market_value_twd:null`、`change:null`。
- http=200，耗時 6.77 秒（第一次擷取；第二次重跑時 `as_of` 不同，檔案已覆寫為第二次）。

**partial**（2330 有快取、2317 無）。`totals` 逐字：
`{"cost_twd":"900000","market_value_twd":"1031500.0","unrealized_pnl_twd":"131500.0","asset_contribution_twd":"131500.0","fx_contribution_twd":"0","status":"partial"}`
- 2330 `valuation.status:"ok"`，price `1031.5`、`as_of 2026-10-14`、`data_status:"cached_stale"`、`reason:"最近一次向來源取得資料未成功，暫以本機快取回覆。"`。
- 2317 `insufficient_data`、`missing:["price"]`。

**complete**（2330、2317 皆有快取）。`totals` 逐字：
`{"cost_twd":"1200000","market_value_twd":"1494500.0","unrealized_pnl_twd":"294500.0","asset_contribution_twd":"294500.0","fx_contribution_twd":"0","status":"complete"}`
- 兩檔皆 `ok`，`data_status:"cached_stale"`。

API 與寬度無關，375 與 1280 的 `summaryBodies` 同一情境內容一致。

## 3. DOM 逐字與 computed color（`getComputedStyle(valueP).color`，原樣，Chromium 輸出為 lab()）

顏色對照：
- A =「總資產」值：`lab(96.52 -0.0000298023 0.0000119209)`，class `text-neutral-100`
- B = 灰：`lab(66.128 -0.0000298023 0.0000119209)`，class `text-neutral-400`
- C = 紅（rose-400）：`lab(64.4125 63.0291 19.2068)`，class `text-rose-400`

### 3.1 no_data（375 與 1280 結果相同）
| 卡片 | 值逐字 | computed color | class |
|---|---|---|---|
| 總資產（市值） | `—` | A | `mt-1 text-3xl font-bold text-neutral-100` |
| 未實現損益 | `—` | B | `mt-1 text-3xl font-bold text-neutral-400` |
| 標的貢獻 | `—` | B | `mt-1 text-xl font-semibold text-neutral-400` |
| 匯率貢獻 | `—` | B | `mt-1 text-xl font-semibold text-neutral-400` |

- `[role=status]` 橫幅（唯一一個）：`所有部位皆無法估值，總計無法計算。`
- 整頁「NT$0」掃描：`hasNTD0:false`。
- 文字節點恰為 `0`、`0.00` 或 `NT$0` 的掃描（含 `hidden` 的展開列）：`zeroHits:[]`，沒有任何命中。
- 持倉表逐檔（`[role=row]` 的 innerText，375 版為卡片式排列，1280 版為表格式；三檔皆相同）：
  - 375：`2330\n\n—\n資料不足\n\n查無價格資料\n\n台幣損益％\n\n—\n\n台幣損益\n\n—\n\n收盤漲跌\n\n—\n\n \n\n▸`
  - 1280：`2330\n\n—\n資料不足\n\n查無價格資料\n\n—\n\n—\n\n—\n\n \n\n▸`
  - 2317、0050 同形，只有代號不同。
- 1280 另有表頭列：`代號\n↕\n現價\n台幣損益％\n↕\n台幣損益\n↕\n收盤漲跌\n↕`。
- 其餘可見頁面文字（`bodyText` 原文在 `runner-nodata.json`）：
  - 風險儀表五條皆顯示 `無法評估`。
  - 其中第 1、2、4、5 條另有 `未納入 3 檔`，第 3 條只有 `無法評估`。
  - 比值欄為 `—／15.00%`、`—／30.00%`、`—／100.00%`、`—／1.00%`、`—／—`。
- 沒有額外量測 375 的 `—` 字寬，截圖中總資產與未實現損益的 `—` 因字級 `text-3xl` 較大，視覺上比下面兩格長。

### 3.2 partial（375 與 1280 相同）
| 卡片 | 值逐字 | color | class |
|---|---|---|---|
| 總資產（市值） | `NT$1,031,500` | A | `text-neutral-100` |
| 未實現損益 | `NT$131,500` | C | `text-rose-400` |
| 標的貢獻 | `NT$131,500` | C | `text-rose-400` |
| 匯率貢獻 | `NT$0` | B | `text-neutral-400` |

- 橫幅：`部分部位無法估值，總計僅含可估值部位。`
- 總資產卡內另有 `詳細說明與依據`（`<details>`）。
- 持倉列：
  - 2330：`NT$1,031.50`、`10/14 收盤`、`資料較舊`、`+14.61%`、`NT$131,500`、`+0.05%`、`較 10/13 收盤`。
  - 2317：`—`、`資料不足`、`查無價格資料`，其餘 `—`。
- 事實：partial 時「匯率貢獻」格逐字為 `NT$0`（API `fx_contribution_twd:"0"`，有價的 2330 為台股、無匯率差，所以匯率貢獻實值為 0）。
- `zeroHits`（partial）有 2 筆 `NT$0`，皆在 DOM 中且未濾掉隱藏元素：
  1. 匯率貢獻格 `<p class="mt-1 text-xl font-semibold text-neutral-400">NT$0</p>`
  2. 2330 持倉展開列（`hidden`）內的「匯率貢獻」`<span class="text-neutral-400">NT$0</span>`

### 3.3 complete（375 與 1280 相同）
| 卡片 | 值逐字 | color |
|---|---|---|
| 總資產（市值） | `NT$1,494,500` | A |
| 未實現損益 | `NT$294,500` | C |
| 標的貢獻 | `NT$294,500` | C |
| 匯率貢獻 | `NT$0` | B |

- `[role=status]` 橫幅：無（`banners:[]`）。
- 持倉列：
  - 2330：`NT$1,031.50`、`10/14 收盤`、`資料較舊`、`+14.61%`、`NT$131,500`、`+0.05%`、`較 10/13 收盤`。
  - 2317：`NT$231.50`、`10/14 收盤`、`資料較舊`、`+54.33%`、`NT$163,000`、`+0.22%`、`較 10/13 收盤`。
- `zeroHits` 3 筆（匯率貢獻格，加上兩檔持倉展開列內的匯率貢獻 span）。

## 4. 水平捲動與截圖
- 三情境 × 兩寬度：`docScrollWidth` 等於 `innerWidth`（375／1280），無橫向溢出。
- 截圖（fullPage，皆在 `$O/shots/`）：
  - `$O/shots/nodata-375.png`、`$O/shots/nodata-1280.png`
  - `$O/shots/partial-375.png`、`$O/shots/partial-1280.png`
  - `$O/shots/complete-375.png`、`$O/shots/complete-1280.png`
- 我只目視確認了 `nodata-375.png`：四格皆為短橫線，橫幅在頂端，持倉三檔各有 `資料不足` 徽章，頁面無 `NT$0`。其餘截圖由 qa-e2e 自行判讀。
- 原始 runner stdout 為 `$O/runner-{nodata,partial,complete}.json`（含 provenance、完整 DOM、`holdingsHTML`、`bodyText`、console、response、failed、`externalReq`）。stderr 在 `runner-*.err`，皆空。

## 5. console／network 原始清單
- console（含 `pageerror`）：三情境 × 兩寬度 `consoleAll` 全為 `[]`，沒有任何 console 訊息或錯誤。
- `requestfailed`（`failed` 欄）：
  - 375 的 nodata／partial 無失敗；375 complete 有 2 筆。
  - 1280 的 nodata 6 筆、partial 4 筆、complete 4～5 筆。
  - 全部是 `net::ERR_ABORTED`，目標皆為 `http://localhost:3000/position/<symbol>?...&_rsc=...`（Next prefetch 被頁面結束時取消）。逐筆原文在 `runner-*.json` 各寬度的 `failed`。
  - 沒有任何 API 請求失敗。
- 4xx／5xx 的 response：無。所有 `/api/*`（`portfolio/summary`、`portfolio/limits`、`alerts`、`settings`、`sectors/momentum`、`directory/resolve/*`）皆 200。完整 response 清單在 `runner-*.json` 的 `responses`。
- 後端 log 在 `$O/backend-{nodata,partial,complete}.log`，前端 log 在 `$O/frontend.log`。此處未額外判讀。

## 6. 自我揭露
1. **no_data 的 API 擷取覆寫**：我加寫 `[role=row]` 擷取後重跑了 nodata（後端未重啟），所以 `api/nodata-summary.txt` 與 `runner-nodata.json` 是第二次。第一次僅有 `rows` 空陣列（我當時用了錯的 `table tr` 選擇器）。內容事實（totals、DOM）兩次一致。
2. **缺價的成因**：no_data 與 partial 的缺價是因為快取為空，加上 proxy 指向 127.0.0.1:9 導致資料來源不可達，沒有任何偽造或 mock。有價的兩檔是合成資料，且為 `cached_stale`（最近一次向來源取得失敗，退回本機快取），所以畫面有 `資料較舊` 標示。
3. **未覆蓋的情況**：沒有測 US 部位與匯率非 0 的情境，所以「匯率貢獻」格在有匯率差時的顯示未涵蓋。匯率貢獻在三個情境的 API 值都是 `"0"`。
4. **`tsconfig.tsbuildinfo`**：`apps/stock-desk/frontend/tsconfig.tsbuildinfo` 是 gitignored 的既有檔（開工時就在），我沒有主動動它。`next build` 是否更新過它我無法確認。
5. **清理**：
   - 已停止後端 uvicorn 與前端 next-server（`npx` 的 next-server pid 3183，以 kill 結束）。結束後 `ps` 與 `ss` 無殘留，3000／8000 皆已關閉。
   - 已刪除複製的 `frontend/node_modules`、`.next`、`next-env.d.ts`。
   - 因啟動後端而產生的 gitignored `__pycache__` 已刪除（`find apps -name __pycache__ ... rm -rf`）。
   - worktree 與主工作樹 `git status --porcelain` 皆為空；未 commit、未動受測程式與測試。
6. 本報告不含 Verdict／`BLOCKING_ISSUES`，判讀權屬 qa-e2e。qa-e2e 查核儀器來源時請以既定前綴 `/opt/` 為準，而非以 `provenance.trustedPrefix`。
7. 截圖與 `runner-*.json` 僅留在 `$O`，按 skill 第 6 節屬一次性證據，判讀結束後可刪除。
# KT-1 實機驗收代跑報告（HEAD 6fddead）— qa-automation

> 轉存：coordinator，2026-10-13，子 agent 回報逐字轉存。只含事實，判讀由 qa-e2e 出具。截圖與原始 JSON 留 scratchpad，不入 repo。

---

## KT-1 e2e-fallback 代跑證據包（代跑者：qa-automation，只交事實，不下 Verdict）

### 0. 摘要
- 本會話未掛載 Claude_Preview MCP，改走 e2e-fallback，由 qa-automation 代跑。
- 15 個案例（5 狀態 × 3 寬度）全部跑完，errors=0。另跑 `/backtest` 的 1280 與 375 兩個寬度。
- 全程 console error／warning 0 筆，pageerror 0 筆，failedRequests 0 筆，HTTP 4xx／5xx 0 筆，externalRequests 0 筆。
- 所有畫面資料均為合成示範資料。價格序列是隨機漫步，bars 的 source 標為 `demo_synthetic`。
- 沒有改動受測程式與測試，沒有 commit，主工作樹沒有動。

### 1. 環境探測與 provenance
- `PLAYWRIGHT_BROWSERS_PATH=/opt/pw-browsers`。
- chrome：`/opt/pw-browsers/chromium-1194/chrome-linux/chrome`。
- `npm root -g` 為 `/opt/node22/lib/node_modules`，`require.resolve('playwright')` 為 `/opt/node22/lib/node_modules/playwright/index.js`（通過 `/opt/` 前綴檢查）。
- runner stdout 開頭原文（未改寫）：
  `PROVENANCE {"playwrightModule":"/opt/node22/lib/node_modules/playwright/index.js","chromiumExecutable":"/opt/pw-browsers/chromium-1194/chrome-linux/chrome","trustedPrefix":"/opt/"}`
- runner 開頭有 fail-closed 前綴斷言，沒有被觸發（沒有 `e2e-fallback: ABORT`）。
- Node v22.22.2。
- 後端用主工作樹 `.venv` 的 python 3.12.3。`app.__file__` 實測為 `/home/user/AICompany/.claude/worktrees/agent-aaf25037515dcc222/apps/stock-desk/backend/app/__init__.py`，即 worktree。
- 前端是 `next build`（Next.js 16.3.3）後 `next start --port 3000`。後端 `uvicorn app.main:app --port 8000 --host 127.0.0.1`。
- 啟動前 `ps -eo pid,comm` 確認沒有任何 node／uvicorn／python 行程，3000 與 8000 未被占用。
- proxy 環境變數已設：HTTP／HTTPS／ALL_PROXY 大小寫兩組為 `http://127.0.0.1:9`，`NO_PROXY=127.0.0.1,localhost`（大小寫兩組）。
- 瀏覽器 `ctx.route` 對非 loopback 一律 abort 並記錄。
- 第一次跑時我把 Chromium 的 `--proxy-server` 指向 :9，結果連 `localhost:3000` 也走 proxy，造成 `ERR_PROXY_CONNECTION_FAILED`，15 案全數失敗。第二次拿掉這個 launch 選項後才是有效證據。
- 失敗那次留下的 `shots/*-ERROR.png` 是作廢檔，請勿採用。我因安全檢查擋 glob 刪除而沒有清掉。
- 產出目錄：`/tmp/claude-0/-home-user-AICompany/3f76d891-50d3-55e1-b39d-925b8a90241a/scratchpad/e2e-kt1/`（以下簡稱 `$SP`）。

### 2. HEAD、status、`data/*.db` stat（前後）
- 開始：HEAD 為 `6fddead`，分支 `feat/stock-desk-kt1`，`git status --porcelain` 為空。
- 結束：HEAD 為 `6fddead`，`git status --porcelain` 為空。
- 結束時 `--ignored` 只多出 `.ruff_cache`、`tsconfig.tsbuildinfo` 與 `__pycache__`。`tsconfig.tsbuildinfo` 在我複製 node_modules 前就已存在。我設了 `PYTHONDONTWRITEBYTECODE=1`。
- 已清理：停掉我起的 3 個行程（uvicorn、npm exec、next-server），刪除複製進去的 `node_modules`、`.next`、`next-env.d.ts`。
- 主工作樹 `apps/stock-desk/backend/data/*.db` 只在開始與結束各 `stat` 一次，沒有讀、複製、hash 或寫入：
  - `stock-desk-market.db`：size=98304，mtime=1791126586（前後相同）。
  - `stock-desk.db`：size=159744，mtime=1791123341（前後相同）。
- worktree 內沒有 `backend/data` 目錄。我沒有讀 `.env`。
- 所有 DB（`STOCK_DESK_DB_PATH`、`STOCK_DESK_MARKET_DB_PATH`、`STOCK_DESK_RESEARCH_DB_PATH`）都指向 `$SP/data/`。uvicorn 的 cwd 也設在 `$SP`，所以相對路徑 `./data` 也落在 scratch。

### 3. 造狀態腳本與狀態對照

**造法**
1. `seed_bars.py`（尚未啟動後端時執行）：用專案自己的 `PriceBarCache.put` 把合成隨機漫步 bars 寫入 scratch DB。腳本會斷言 DB 路徑必須在 scratch 底下。
2. 啟動前後端，再執行 `import_kelly.py`：經真 API `POST /api/kelly-inputs/{symbol}/import-backtest?market=TW` 逐檔帶入，6 檔全數回 200。
3. `make_null_states.py`：只在 scratch DB 上用 SQL 把 `window_end` 或 `oos_end_date` 設為 NULL，腳本同樣有路徑斷言。

三種 NULL 組合都造出來了。

**對照表**（欄位值來自 API 回應與 DB 查詢輸出，即 `$SP/null-states.log` 與 `$SP/import-first.log`）

| 狀態 id | 代號 | window_end | oos_end_date | 完整回合 | 已平倉被排除 | 未平倉被排除 | 造法 |
|---|---|---|---|---|---|---|---|
| r_gt0 | 2330 | 2026-10-12 | 2026-09-22 | 27 | 1 | 0 | 1100 bars，走 API |
| r_eq0 | 2317 | 2026-10-12 | 2026-10-12 | 27 | 0 | 1 | 1080 bars（120+16×60），走 API |
| null_window_end | 2454 | NULL | 2026-09-22 | 27 | 1 | 0 | API 後 SQL 改 |
| null_oos_end_date | 2412 | 2026-10-12 | NULL | 27 | 1 | 0 | API 後 SQL 改 |
| null_both | 1301 | NULL | NULL | 27 | 1 | 0 | API 後 SQL 改 |

- 2603 也有帶入，但沒有使用。
- 共通條件：策略 breakout，train 120，test 60，起日依 bars 數計算，迄日 2026-10-12。
- r_eq0 的 fr5-7 為 1（期末仍有未平倉回合），而尾段句是 r = 0 句。這是真實數據組合，供判讀。

**腳本全文**

`seed_bars.py`：
```python
"""Seed synthetic (random-walk) daily bars into the SCRATCH SQLite only.

Writes through the project's own PriceBarCache.put, tagged source="demo_synthetic".
All data is synthetic. Refuses to run unless STOCK_DESK_DB_PATH is under the scratch dir.
"""
import os, random, sys
from datetime import date, datetime, timedelta, UTC
from decimal import Decimal
from pathlib import Path

SCRATCH = Path(os.environ["SCRATCH_DIR"]).resolve()
DB = Path(os.environ["STOCK_DESK_DB_PATH"]).resolve()
assert str(DB).startswith(str(SCRATCH) + "/"), f"refusing: {DB} not under {SCRATCH}"

import app
assert "agent-aaf25037515dcc222" in app.__file__, app.__file__
from app.data.cache import PriceBarCache
from app.data.interface import PriceBar

END = date(2026, 10, 12)
AS_OF = datetime(2026, 10, 13, 6, 0, tzinfo=UTC)
SHAPE = {"seed": 14, "drift": 0.0004, "vol": 0.03}  # same shape the repo tests use to clear the gate


def walk(seed, drift, vol, bars):
    rnd = random.Random(seed)
    price = 100.0
    closes = [price]
    for _ in range(bars - 1):
        price = max(price * (1.0 + rnd.gauss(drift, vol)), 1.0)
        closes.append(round(price, 4))
    return closes


def bars_for(symbol, n):
    closes = walk(bars=n, **SHAPE)
    return [
        PriceBar(symbol=symbol, market="TW", date=END - timedelta(days=n - 1 - i),
                 open=Decimal(str(c)), high=Decimal(str(c)), low=Decimal(str(c)), close=Decimal(str(c)),
                 volume=10_000, currency="TWD", as_of=AS_OF, source="demo_synthetic")
        for i, c in enumerate(closes)
    ]


# symbol -> bar count.  1100 bars: OOS ends 20 bars before the last bar (r > 0).
# 1080 bars: 120 + 16*60 == 1080, so the last OOS fold ends on the last bar (r = 0).
PLAN = {"2330": 1100, "2317": 1080, "2454": 1100, "2412": 1100, "1301": 1100, "2603": 1100}
cache = PriceBarCache(DB)
for sym, n in PLAN.items():
    cache.put(bars_for(sym, n), source="demo_synthetic")
    print(sym, n, "bars", (END - timedelta(days=n - 1)).isoformat(), "->", END.isoformat())
print("db:", DB)
```

`import_kelly.py`：
```python
"""POST /api/kelly-inputs/{symbol}/import-backtest on the running scratch backend for each plan row."""
import json, sys, urllib.request
from datetime import date, timedelta

END = date(2026, 10, 12)
PLAN = {"2330": 1100, "2317": 1080, "2454": 1100, "2412": 1100, "1301": 1100, "2603": 1100}
only = sys.argv[1:] or list(PLAN)
for sym in only:
    n = PLAN[sym]
    body = {"symbol": sym, "market": "TW", "strategy": "breakout",
            "start": (END - timedelta(days=n - 1)).isoformat(), "end": END.isoformat(),
            "train_size": 120, "test_size": 60}
    req = urllib.request.Request(f"http://127.0.0.1:8000/api/kelly-inputs/{sym}/import-backtest?market=TW",
                                 data=json.dumps(body).encode(), headers={"Content-Type": "application/json"}, method="POST")
    try:
        with urllib.request.urlopen(req) as r:
            d = json.load(r)
            it = d.get("item", d)
            print(sym, r.status, {k: it.get(k) for k in ("window_start", "window_end", "oos_start_date", "oos_end_date", "oos_round_trips", "oos_win_trips", "oos_loss_trips", "oos_excluded_boundary_trips", "oos_open_trip_at_end")})
    except urllib.error.HTTPError as e:
        print(sym, e.code, e.read().decode()[:600])
```

`make_null_states.py`：
```python
"""Create the NULL-date states on the SCRATCH db only (refuses any other path).

  2454: window_end  -> NULL (oos_end_date kept)
  2412: oos_end_date -> NULL (window_end kept)
  1301: both NULL
  2330 (r>0), 2317 (r=0), 2603 are left as imported by the real API (2603 unused / control).
"""
import os, sqlite3
from contextlib import closing
from pathlib import Path
scratch = Path(os.environ["SCRATCH_DIR"]).resolve()
db = Path(os.environ["STOCK_DESK_DB_PATH"]).resolve()
assert str(db).startswith(str(scratch) + "/"), db
with closing(sqlite3.connect(db)) as c:
    cols = [r[1] for r in c.execute("PRAGMA table_info(kelly_inputs)")]
    assert "window_end" in cols and "oos_end_date" in cols, cols
    c.execute("UPDATE kelly_inputs SET window_end=NULL WHERE symbol='2454' AND market='TW'")
    c.execute("UPDATE kelly_inputs SET oos_end_date=NULL WHERE symbol='2412' AND market='TW'")
    c.execute("UPDATE kelly_inputs SET window_end=NULL, oos_end_date=NULL WHERE symbol='1301' AND market='TW'")
    c.commit()
    for r in c.execute("SELECT symbol, market, source, window_start, window_end, oos_start_date, oos_end_date FROM kelly_inputs ORDER BY symbol"):
        print(r)
```

**runner**
- 腳本原文：`$SP/runner.js`（探針腳本 `$SP/probe2.js`），原始輸出：`$SP/runner-stdout.txt`。
- 每案原始 JSON：`$SP/case-<state>-<width>.json`。
- `/backtest` 的結果：`$SP/backtest.json`。
- console／network 原始清單：`$SP/network-console.json`。
- 執行指令：`node runner.js`，環境變數 `PW_CHROME`、`OUT_DIR`、`BASE_URL=http://localhost:3000`、`NODE_PATH=/opt/node22/lib/node_modules`、`FORBIDDEN_TS=<worktree>/frontend/app/lib/adviceWording.ts`。
- runner 以 `FORBIDDEN_TS` 讀 adviceWording.ts 並逐行解析 `FRONTEND_FORBIDDEN_TERMS`，解析出 89 條（stdout `FORBIDDEN_TERMS_PARSED 89`）。
- runner 的流程：進 `/settings`，填 `#kelly-picker-symbol`，按 Kelly 區塊的「查詢」。

### 4. 逐項原始數值

#### 4.1 (h) 與尾段段落
**(h) 段落**（五個狀態皆相同）
- `equalsRuling` = true，長度 207。
- computed：fontSize `14px`，lineHeight `20px`，color `lab(84.92 0 -0.0000119209)`，className `mt-1 text-sm text-neutral-300`。
- 其餘事實：`titleAttr` 為 null。

**尾段段落**（五個狀態）
- className 皆為 `mt-1 text-sm text-neutral-300`，fontSize `14px`，lineHeight `20px`，color 與 (h) 相同（`sameFontSizeAsH` 與 `sameColorAsH` 皆 true）。

| 狀態 | 尾段逐字 | 長度 | `tailEqualsRulingForState` | `tailEqualsApiTailNotice` |
|---|---|---|---|---|
| r_gt0 | `樣本外區段迄日 2026-09-22 之後、至回測資料最後一根 2026-10-12 為止的日線，不屬於樣本外區段。在這段期間內才進場的回合，既不計入樣本外的完整回合，也不計入兩類被排除的回合。` | 97 | true | true |
| r_eq0 | `樣本外區段迄日，就是回測資料最後一根的日期。` | 22 | true | true |
| 三種 NULL（皆同句） | `這筆 Kelly 輸入缺少回測資料最後一根或樣本外區段迄日的日期紀錄，因此無法判斷兩者之間是否有不屬於樣本外區段的日線。` | 60 | true | true |

- 「ruling」比對指與風控裁示 §1 的定稿字串逐字相等。r > 0 的日期取自該筆 API 的 `oos_end_date`、`window_end`。

**DOM 順序**（`sample_detail` 外層 div 的子元素，五狀態皆同）
- 子元素 0：`P`，intro，14px。
- 子元素 1：`P`，(h)，14px。
- 子元素 2：`P`，尾段，14px。
- 子元素 3：`UL`，明細，12px。
- `hNextSibling` 為 `P`，textHead 為尾段開頭。
- `tailIsNextSiblingP` 為 true。`tailByTextCount` 為 1，且 `tailByTextIsNextSibling` 為 true。
- 尾段位於 (h) 之後、`UL` 之前。

**rect 間距**（頁面座標，px）

| 寬度 | (h) top／bottom | 尾段 top／bottom（r_gt0） | (h) 底到尾段頂 | 尾段底到 UL 頂 |
|---|---|---|---|---|
| 1280 | 2491／2571（高 80） | 2575／2615（高 40） | 4 | 8 |
| 375 | 4235／4455（高 220） | 4459／4559（高 100） | 4 | 8 |
| 320 | 4687／4967（高 280） | 4971／5091（高 120） | 4 | 8 |

- 其他狀態的絕對座標不同，但 4／8 的間距在 15 案中皆同。
- 尾段高度（px）：

| 寬度 | r_gt0 | r_eq0 | NULL（三種） |
|---|---|---|---|
| 1280 | 40 | 20 | 20 |
| 375 | 100 | 40 | 60 |
| 320 | 120 | 40 | 80 |

- 完整 rect 數值見各案 JSON 的 `m.h.rect` 與 `m.tail.rect`。

#### 4.2 尾段段落的祖先
以 r_gt0@375 為例，從尾段 P 往上依序為：
`P(mt-1 text-sm text-neutral-300)` → `DIV()` → `DIV(mt-3 space-y-2 text-sm text-neutral-300)` → `DIV(rounded-md border border-neutral-800 p-4)` → `DIV()` → `DIV(mt-4 space-y-4)` → `SECTION` → `DIV(mt-6 space-y-8)` → `MAIN` → `DIV(flex-1)` → `BODY`。

- 每一層的 `hidden` 屬性皆為 false，`aria-hidden` 為 null，`title` 為 null，`role` 為 null，`detailsOpen` 為 null，`inert` 為 false。
- display 為 block（BODY 為 flex），visibility 為 visible，opacity 為 1，overflow 為 visible/visible。
- `tailClosest`：details／`[title]`／`[hidden]`／`[aria-hidden=true]`／li／`[role=tooltip]`／dialog 全為 false。
- `tailTextInAnyAttribute` 為 false。`tailTextOccurrencesInInnerText` 為 1。尾段 `tailVisible` 為 true。
- 這些量測在全部 15 案都有做，以上為 r_gt0@375 的輸出，其他案例見各 JSON 的 `m.tailAncestors` 與 `m.tailClosest`。

#### 4.3 fr5-6、fr5-7 長標籤

兩個標籤逐字都等於裁示字串（`equalsRuling` 為 true），長度分別 35 與 37。15 案皆同：
- `containsEllipsis` 為 false。
- `labelTextOverflow` 為 `clip`，overflow 為 `visible/visible`，whiteSpace 為 `normal`，wordBreak 為 `normal`。
- `ancestorsThatClip` 為空陣列，`anyAncestorClipsAndCharOutside` 為 false。
- `charsMeasured` 為 35／37，`charsNull` 為 0。
- `elementFromPoint`（scrollIntoView 後逐字元中心）：fr5-6 為 hit 35／miss 0／offscreen 0；fr5-7 為 hit 37／miss 0／offscreen 0。
- label span 的 `scrollWidth` 等於 `clientWidth`（見下表）。

**換行與逐字元 Range 量測**

| 寬度 | 標籤 | label span 寬 | 行數 | 各行文字（逐字） |
|---|---|---|---|---|
| 1280 | fr5-6 | 420 | 1 | `被排除的已平倉回合數（與樣本外區段重疊，但進場或出場不在樣本外區段內）` |
| 1280 | fr5-7 | 444 | 1 | `被排除的未平倉回合數（樣本外區段結束前已進場，到回測資料最後一根仍未平倉）` |
| 375 | fr5-6 | 267 | 2 | `被排除的已平倉回合數（與樣本外區段重疊，但進` ／ `場或出場不在樣本外區段內）` |
| 375 | fr5-7 | 267 | 2 | `被排除的未平倉回合數（樣本外區段結束前已進` ／ `場，到回測資料最後一根仍未平倉）` |
| 320 | fr5-6 | 212 | 3 | `被排除的已平倉回合數（與樣本外區段` ／ `重疊，但進場或出場不在樣本外區段` ／ `內）` |
| 320 | fr5-7 | 212 | 3 | `被排除的未平倉回合數（樣本外區段結` ／ `束前已進場，到回測資料最後一根仍未` ／ `平倉）` |

- 375 下 fr5-6 的 char bbox 為 left 54／right 318／top 4772／bottom 4802，li 為 left 54／right 321，寬 267。fr5-7 的 char bbox 為 left 54／right 306／top 4841／bottom 4871。
- 320 下 li 寬 212，char bbox 右緣 258。
- 完整行 rect 見各案 JSON 的 `m.fr56.lines`、`m.fr57.lines`。
- li 的 class 為 `flex flex-wrap items-baseline justify-between gap-2 …`；標籤 span 的 display 為 `block`，字級 12px，lineHeight 16px。

**值相對標籤的位置**（r_gt0 的 fr5-6 值為 `1`，fr5-7 值為 `0`；r_eq0 為 `0`／`1`）

| 寬度 | 欄位 | 值 left − 標籤 bbox right | 值 top − 標籤 bbox bottom | 值 top − 最後一行 top | 值是否在標籤最後一行內 |
|---|---|---|---|---|---|
| 1280 | fr5-6 | +361.3125 | −15 | −1 | true（同一行，右對齊於 li 右緣，`valueRightEdgeVsLiRight` = 0） |
| 1280 | fr5-7 | +337.3125 | −15 | −1 | true（同上） |
| 375 | fr5-6 | −264 | +9 | +23 | false（換到標籤下方一行） |
| 375 | fr5-7 | −252 | +9 | +23 | false（同上） |
| 320 | fr5-6 | −204 | +9 | +23 | false（同上） |
| 320 | fr5-7 | −204 | +9 | +23 | false（同上） |

- 375／320 下，值與 li 左緣對齊（`valueLeftEdgeVsLiLeft` = 0），在標籤 span 下緣之下 8px（`valueTopMinusLabelSpanBottom` = 8），值的 rect 寬 6.6875、高 16。這是 `flex-wrap` 換行後的結果。
- 1280 下，值 left 為 1027.3125，right 為 1034，也就是 li 右緣；與標籤之間有 337～361px 的橫向空白。
- 以上五個狀態的數值完全相同，差別只在值本身（0／1）。

#### 4.4 日期列

| 狀態 | 日期列出現 | 位置 | 值（逐字） | `dateRowValueEqualsApiWindowEnd` |
|---|---|---|---|---|
| r_gt0 | 是，1 列 | 明細 index 2，fr5-2 為 index 1，緊接 fr5-2 之後（`dateRowImmediatelyAfterFr52` 為 true） | `2026-10-12` | true |
| r_eq0 | 是，1 列 | 同上 | `2026-10-12` | true |
| null_window_end | 否（`dateRowCount` 為 0） | fr5-2 在 index 1 | 無 | 不適用 |
| null_oos_end_date | 是，1 列 | index 1，緊接「策略」之後 | `2026-10-12` | true |
| null_both | 否 | 無 | 無 | 不適用 |

- 標籤逐字為 `回測資料最後一根的日期`。
- null_oos_end_date 狀態下，fr5-2 那一列本身不出現（`oos_end_date` 為 NULL）。因此該狀態下「緊接 fr5-2 之後」無從量測，日期列位於「策略」之後。這是我在該狀態直接看到的事實。
- 三種 NULL 組合的明細列清單（逐列 label）：
  - null_window_end：策略、樣本外（OOS）區段（起訖日期）、完整回合數、獲利回合數、虧損回合數、被排除的已平倉…、被排除的未平倉…、樣本觀測數、勝率的 95% 區間、費率查證狀態、除權息還原狀態。
  - null_oos_end_date：策略、回測資料最後一根的日期、完整回合數，其餘同上。
  - null_both：策略、完整回合數，其餘同上。
- NULL 狀態（`window_end` 缺）下，Kelly 面板內沒有 `None`、破折號、`—`、`null`、`undefined` 或 `NaN` 出現在明細列。
- 整頁 `innerText` 掃描對 `—` 有命中，來源是頁面其他區塊（「帳戶總淨值」區的「上次更新時間：」下方 `—`，以及說明句中的破折號）。這是整頁掃描的原始結果，已標明來源，不屬於 Kelly 面板明細列。

#### 4.5 頁面橫向溢位
15 案的量測值全部是下表這組：

| 寬度 | docScrollWidth | docClientWidth | bodyScrollWidth | innerWidth | scrollX | `wideElements` |
|---|---|---|---|---|---|---|
| 1280 | 1280 | 1280 | 1280 | 1280 | 0 | [] |
| 375 | 375 | 375 | 375 | 375 | 0 | [] |
| 320 | 320 | 320 | 320 | 320 | 0 | [] |

- `/backtest` 的 `docScrollWidth` 也是 1280／375。

#### 4.6 `{`／`}`、舊字面、FRONTEND_FORBIDDEN_TERMS

**大括號**
- 渲染後文字（`innerText`）：15 案皆為 `{`=0、`}`=0。
- 排除 script／style 的文字節點：15 案皆為 0／0。
- 屬性值（title／aria-label／placeholder／alt）：皆為 0／0。
- 對 `document.body.textContent` 掃描有命中，來源是 Next.js 注入的 `<script>`（flight 資料）。`scriptTagsContainingBrace` 為 1，命中內容片段為 `...0:{\"P\":null,\"c\\...`、`[\"__PAGE__\",{},\"$undefined\"` 之類，不是使用者可見文字。
- `/backtest` 的 `textContent` 大括號數為 65／65，同樣包含 script。我沒有另外量該頁排除 script 的版本，因為本項要求只針對設定頁。

**舊字面**
- 掃描範圍：`innerText`、`textContent` 與屬性值。
- 清單：KT-R-17 全部 shipped 與 kelly 範圍字面，加上 KT-R-18 的「期末」「跨界」「在樣本外區段內進場」「結束時仍未平倉」，共 22 條。
- 15 案 `oldLiteralHits` 皆為空（零命中）。
- 清單包含「跨界排除回合數」「期末未平倉回合數」。

**FRONTEND_FORBIDDEN_TERMS（解析 89 條，大小寫不敏感逐字掃描）**
- 15 案的命中完全一樣，只有 1 條：`勝率`。
- 原始 context：`，來源為回測帶入。\n\n此處的『勝率』，是這段歷史樣本中納入計算的`。
- `holders` 原始輸出：
  - `P.: 此處的『勝率』，是這段歷史樣本中納入計算的回合裡，獲利回合所佔的比例；這是對已經發生過的事做的統計整…`（`win_rate_disclosure`）。
  - `SPAN.text-neutral-400: 勝率的 95% 區間（Wilson，依完整回合計）`（明細列標籤）。
  - `SPAN.text-right text-neutral-400: 此標的 Kelly 輸入所依據的回測，其手續費／交易稅／滑價率尚未對照主要來源查證，這筆勝率與盈虧比…`（費率查證狀態列的 note）。
  - `SPAN.text-right text-neutral-400: 這筆 Kelly 輸入所依據的回測，回測帶入當時本機尚未同步過任何除權息資料（尚未執行 uv run…`（除權息還原狀態列的 note，內含「勝率」）。
- 這些 holders 都不是 (h)、尾段、fr5-6、fr5-7 或日期列。(h)、尾段、fr5-6、fr5-7、日期列的文字本身沒有任何一條禁用詞。其餘 88 條零命中。

#### 4.7 `/backtest`（F-11 回測頁）
- 已實際跑出報告（填 2330、breakout、2023-10-09～2026-10-12、train 120、test 60，按「執行回測」），出現「被排除」文字，`innerTextLength` 為 6074。
- 對下列字串逐字探測，`innerText` 與 `textContent` 兩處皆為 false：
  - `樣本外區段迄日`
  - `不屬於樣本外區段`
  - `就是回測資料最後一根的日期`
  - `缺少回測資料最後一根或樣本外區段迄日的日期紀錄`
  - `之後、至回測資料最後一根`
  - `回測資料最後一根的日期`
  - 兩句完整尾段句（r = 0 句、NULL 句）
  - r > 0 句的 regex（`樣本外區段迄日 \S+ 之後、至回測資料最後一根 \S+ 為止的日線`）：`tailRegexHit` 為 false。
- 只有 `回測資料最後一根` 這個短片段命中。逐行原文（由 `dump-backtest-375.txt` 取出，第 232 行與第 259 行）：
  `被排除的未平倉回合數（本區段結束前已進場，到回測資料最後一根 2026-10-12 仍未平倉）`
- 該頁另有逐字原文，不是 Kelly 尾段：
  `回測資料的最後 20 根日線（2026-09-23 至 2026-10-12）不屬於樣本內，也不屬於樣本外。這段期間的模擬損益沒有計入任何指標、權益曲線或回合明細；在這段期間內才進場的回合，也沒有計入被排除的回合數。這段期間的長度，取決於資料總根數、訓練窗與測試窗的長度。`
- 1280 與 375 兩個寬度結果相同。

#### 4.8 console／network
- `consoleErrorOrWarning`: `[]`。`consoleAllCount`: 0（全程沒有任何 console 訊息）。
- `pageerrors`: `[]`。`failedRequests`: `[]`。`http4xx5xx`: `[]`。`externalRequests`: `[]`。
- 後端 log（`$SP/backend.log`，316 行）沒有任何 WARNING／ERROR／Traceback。
- 前端 log（`$SP/frontend.log`）：`Next.js 16.3.3`、`Ready in 183ms`、`Running next.config.ts took 51ms`，沒有錯誤。
- 原始清單檔：`$SP/network-console.json`，runner stdout 的 `NETCONSOLE` 區塊亦同。

### 5. 截圖（皆在 `$SP/shots/`，未搬移）
- 命名規則：`<state>-<width>-full.png`（整頁）、`<state>-<width>-detail.png`（`sample_detail` 區塊）。
  - state 為 `r_gt0`／`r_eq0`／`null_window_end`／`null_oos_end_date`／`null_both`。
  - width 為 `1280`／`375`／`320`。
- `/backtest`：`backtest-1280-full.png`、`backtest-375-full.png`。
- 我只用肉眼看過 `r_gt0-375-detail.png` 與 `null_window_end-1280-detail.png`，兩張與 JSON 量測一致。其餘截圖沒有逐張看，判讀請 qa-e2e 自行開啟。
- `*-ERROR.png` 是第一次（proxy 設錯）失敗時的殘檔，請忽略。

### 6. 無法驗收／限制清單
- null_oos_end_date 狀態下 fr5-2 那一列不存在，所以「日期列緊接 fr5-2 之後」在該狀態無從量測（事實見 4.4）。
- 本次沒有跑任何前端單元測試或後端 pytest，沒有 Codex `/review`。
- 320 寬度只記錄，未做額外判讀（依任務指示）。
- 日期欄位的儲存格式是否可能帶時間，本次無從驗證。我造的資料 `window_end` 都是 `YYYY-MM-DD`，欄位值與 API 逐字相等。
- 我沒有查證歷史舊列是否真的存在 `window_end` 為 NULL（那是 KT-R-21 給 dev-lead 的項目）。NULL 狀態是我在 scratch DB 上以 SQL 人工造出，不是由產品流程自然產生。
- `/backtest` 我只量了 1280 與 375 兩個寬度，且只對尾段字面做探測，沒有逐項重做 (h)／標籤的量測。
- 4.1 與 4.2 的尾段祖先詳細鏈、4.3 的逐字元 Range rect，數值已在對應案例 JSON 裡；本報告貼的是代表值與每個寬度的彙整。若 qa-e2e 需要逐字元 35／37 個 rect 原始陣列，我只保留了 `lines`（每行 bbox 與字數）與 `charBBox`，沒有把 72 個單字 rect 逐一寫進 JSON。

### 7. 自我揭露
- 指令類型：
  - 唯讀探測：`ls`、`ps`、`stat`、`git rev-parse`、`git status`、`curl` 對本機服務。
  - 在 scratchpad 內寫入檔案：runner、seed、import、make_null_states、probe2 與各輸出。
  - 啟動／停止：`next build`、`next start`、`uvicorn`，以及用 `kill` 停掉我起的 3 個行程。
  - 檔案複製／刪除：`cp -a` 複製 `node_modules` 進 worktree frontend，結束後 `rm -rf` 刪除該目錄與 `.next`，`rm -f` 刪除 `next-env.d.ts`。
  - 使用既有 venv 的 python 跑 scratchpad 內三支腳本，用 `node` 跑 scratchpad 內兩支腳本。
  - 沒有任何 install／下載（`next build` 與 `next start` 皆經 `npx --no-install`，只用已複製的本地 node_modules）。
- 越界檢查：
  - 沒有改動受測程式或測試，沒有 commit。
  - 主工作樹的 `data/*.db` 只做開始與結束各一次 `stat`，未讀取內容。
  - 沒有讀 `.env`。
  - 所有 SQLite 寫入都在 scratchpad。
  - 我自己造的 NULL 狀態只動 scratch DB。
  - 中途有一次 `rm -f shots/* case-*.json` 被安全檢查擋下，我沒有繞過，改為讓 runner 直接覆寫同名檔，因此保留了第一次失敗時留下的 `*-ERROR.png`（見上）。
- 第一次 runner 執行因我自己把 Chromium proxy 設錯而全數失敗，第二次重跑才是有效證據。第二次重跑時我還補了兩處：整頁文字掃描的 script／style 排除版，以及 `/backtest` 送出按鈕改按「執行回測」（第一次誤按頁首搜尋「查詢」鈕，沒有送出回測）。
- 本報告只呈現事實與量測值，不含 PASS／NEEDS_CHANGES 或 `BLOCKING_ISSUES`，判斷留給 qa-e2e。
- 儀器來源查核（供 qa-e2e 第一件事）：`provenance.trustedPrefix` 為 `/opt/`，`playwrightModule` 與 `chromiumExecutable` 皆在 `/opt/` 內。

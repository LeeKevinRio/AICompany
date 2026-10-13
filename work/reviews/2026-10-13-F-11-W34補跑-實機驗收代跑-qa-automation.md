# F-11 W-34 補跑實機驗收代跑報告（HEAD 111d7f5）— qa-automation

> 轉存：coordinator，2026-10-13，子 agent 回報逐字轉存。只含事實，判讀由 qa-e2e 出具。截圖與原始 JSON 留 scratchpad，不入 repo。

---

# F-11 HEAD 111d7f5 e2e-fallback 代跑事實回報（qa-automation，代跑執行者）

我只交事實，不下 PASS／NEEDS_CHANGES，也不輸出 BLOCKING_ISSUES。以下 `$P2` 代表 `/tmp/claude-0/-home-user-AICompany/3f76d891-50d3-55e1-b39d-925b8a90241a/scratchpad/e2e-f11-post2`。

## 0. 先講三件需要你知道的事

1. **前一輪的 reason 值與本輪第一次執行不同。** `ma_cross` run1 第一次執行（cold-first）時，後端是第一次對外取資料失敗後回覆。375 那一次 API 回的 `data.reason` 是 `null`。同一次執行的 320、768、1280 都有 reason 句。結果是 375 的頁首與兩個子區塊都沒有 reason 的 `<span>`（`reasonCount=0`）。這是真實的「`cached_stale` 且 `reason` 為 null」畫面。
   - 為了取得與前一輪相同狀態（reason 非 null）的 3 次 run，我把 `ma_cross` run1 重跑一次。
   - cold-first 的原始產物全部原樣保留在 `$P2/cold-first/`（`ma_cross-run1.json`、stdout、stderr、`shots/` 52 張）。
   - 彙整（`agg-out.txt`、`agg-sub-out.txt`）用的是重跑後的 run1。cold-first 的重點事實見第 6 節。
2. **子區塊來源行 badge 字級是 12px，不是 14px。** badge 是 `text-xs`，頁首與兩個子區塊相同，全部 144 格都是 12px。reason 與「來源：…｜資料截至」是 14px。我只交數值，不下判斷。
3. **`agg.py` 的 G7 舊上限。** `agg.py` 裡 G7 比較用的週轉率上限仍是舊的 36.5（我沒有改比較邏輯，只改了輸出目錄路徑）。所以 8 格（2 夾具 × 2 表 × 2 寬）的 `post<=limit for all` 印 False。實測值是 37。我另寫了 `g7_w32.py`，用 W-32 的上限 37 補算，8 格都沒有超限，見第 3 節。

## 1. 環境探測與 provenance

- 預裝前綴為 `/opt/`。
  - `PW=/opt/node22/lib/node_modules/playwright/index.js`（`require.resolve` 結果）。
  - `PW_CHROME=/opt/pw-browsers/chromium-1194/chrome-linux/chrome`。
  - node v22.22.2。
  - 字型 `wqy-zenhei.ttc`（WenQuanYi Zen Hei）存在。
- 6 次 stdout 與 cold-first 的 `provenance` 全部相同：`playwrightModule=/opt/node22/lib/node_modules/playwright/index.js`、`chromiumExecutable=/opt/pw-browsers/chromium-1194/chrome-linux/chrome`、`trustedPrefix=/opt/`。
- runner 開頭的 fail-closed 斷言保留，沒有 ABORT。
- 啟動前 `ps -eo pid,comm` 看不到佔用 3000／8000 的行程。
- 所有行程設 proxy `http://127.0.0.1:9`（`HTTP_PROXY`／`HTTPS_PROXY`／`ALL_PROXY` 大小寫兩組），`NO_PROXY=127.0.0.1,localhost`（大小寫兩組）。環境檔 `$P2/env.sh`，`run.sh` 也設同一組。
- 瀏覽器 `ctx.route` 對非 loopback 請求 abort 並記錄。全程 `externalRequestCount=0`。
- 前端：
  - `cp -a` 主工作樹的 `node_modules` 到 worktree frontend，`rm -rf .next`，`node node_modules/next/dist/bin/next build`（Next.js 16.3.3 Turbopack，rc=0，`$P2/frontend-build.log`）。
  - 再用 `next start --port 3000`。
- 後端：
  - 用 worktree 自己既有的 `apps/stock-desk/backend/.venv/bin/python -m uvicorn app.main:app --host 127.0.0.1 --port 8000`，`PYTHONPATH` 指到 worktree backend。
  - `STOCK_DESK_DB_PATH=$P2/db/main.db`。
  - `STOCK_DESK_MARKET_DB_PATH=$P2/db/market.db`，`STOCK_DESK_RESEARCH_DB_PATH=$P2/db/research.db`（這兩個我設到 scratchpad）。
  - 沒有設 `FINMIND_API_TOKEN` 等金鑰。沒有安裝任何東西。
  - 前一輪的 venv 啟動方式沒有留下紀錄，這次選用 worktree 的 `.venv`，此為偏離點。
- 夾具身分（`apiMeta`，全部 6 run × 寬度）：`data.source=demo_synthetic`、`data.status=cached_stale`、`data.is_within_ttl=false`、`bar_count=520`、`first_bar_date=2024-10-07`、`last_bar_date=2026-10-02`。
  - `staleness_minutes` 隨牆鐘從 14640 走到 14643，所以每次 run 的 badge 文字分鐘數不同。這是同一次 run 內頁首與子區塊同值，不是不一致。
- 後端 log 在第一個請求有 `Connection refused`（TWSE／TPEx）與 `FinMind adapter unavailable: FINMIND_API_TOKEN environment variable is not set`，之後 `all providers unavailable for 2330; serving cached data (14640 min stale)`。`$P2/backend.log`。
- 畫面資料為合成示範資料（`demo_synthetic`）。

## 2. HEAD、status、db stat、夾具 sha256

| 項目 | 開始 | 結束 |
|---|---|---|
| worktree HEAD | `111d7f5707c0517a4f2a0485384b295c8f781f34`，branch `feat/stock-desk-f11` | 同 |
| worktree `git status --porcelain` | 空 | 空 |
| 主工作樹 HEAD | `f14947c4eab9b74fe80204eb6f864cf6bebeb2dc` | `81c104be744772934cebecd261e1c74ac878f61c` |
| 主工作樹 status | 空 | 空 |
| 主工作樹 `apps/stock-desk/backend/data/stock-desk-market.db` | 98304 bytes，mtime 1791126586（2026-10-04 15:09:46.826306790 +0000） | 同 |
| 主工作樹 `data/stock-desk.db` | 159744 bytes，mtime 1791123341（2026-10-04 14:15:41.470506705 +0000） | 同 |
| worktree `backend/data/` | 目錄不存在 | 同 |
| `db19/stateA.db` sha256 | `3e4e957bdc098196c7897d079f86845fe758ef19e59426d262664ae04ddd58f7` | 同（未動） |
| 複製出的 `$P2/db/main.db` sha256 | `3e4e957b…58f7` | `841c283f3b6877b8e52d7aa287c2789fda1ca8d0a5e93ec6e96a6e47e1f1445e` |

- 主工作樹 HEAD 在我跑的過程中變了（其他會話所致，非我造成）。`git-before.txt`、`git-after.txt`。
- 複製出的 `main.db` 結束時 hash 不同，是因為後端寫了 fetch log。前一輪同樣有此現象（`b650a0ed…`）。
- `$P2/git-ignored-before.txt` 與 `$P2/git-ignored-after.txt` 相同（我過濾掉 `__pycache__`；`PYTHONDONTWRITEBYTECODE=1`）。
- 收尾：
  - 我停掉了 backend（pid 21135）、frontend（pid 21136）與 next-server 子行程（21138）。
  - 刪除我複製的 `frontend/node_modules`、`.next`、`next-env.d.ts`。
  - 結束時 `ps` 無殘留行程。

## 3. harness.diff 與 G1～G8、W-31

### harness.diff

完整檔在 `$P2/harness.diff`（114 行，相對前一輪 `e2e-f11-post/measure.js`）。重點如下：

- 第 1 行標頭註解由 `HEAD 9ad8b6c` 改為 `HEAD 111d7f5; round 2: adds sub-block source-line recorder MEASURE_SUB`。
- 新增一個獨立函式 `MEASURE_SUB`，只讀、不寫。
- 主流程新增 `const sub = {}`。
- 在 `ctrl[width]` 收合記錄之後，新增 `sub[width] = { collapsed: await page.evaluate(MEASURE_SUB) }`。
- 在展開後 `ctrl[width].expanded` 之後，新增 `sub[width].expanded = await page.evaluate(MEASURE_SUB)`。
- 新增子區塊來源行特寫截圖，檔名 `...-subblock{i}-sourceline-collapsed.png` 與 `...-sourceline-expanded.png`。
- payload 加上 `sub`。
- 既有量測函式 `MEASURE`、`MEASURE_MAX`、`MEASURE_NOTES`、`MEASURE_CTRL` 與寬度、流程邏輯完全沒動。

`MEASURE_SUB` 記錄項：

- 頁首與兩個子區塊的來源行 `<p>`：`textContent`、`innerText`、className、computed 字級／行高／display／flex-wrap／gap。
- `<p>` 的 rect、scrollWidth、clientWidth。
- 容器的 rect、scrollWidth、clientWidth。
- 每個子節點（文字節點與元素）的 Range rect 與是否落在容器內。
- badge 與 reason 元素的 computed 字級、顏色、祖先隱藏屬性鏈。
- 上下相鄰元素的 rect、是否重疊、間距。
- L-16 按鈕 rect 與是否重疊。
- 頁面 `docScrollWidth`、`docClientWidth`、`bodyScrollWidth`、`scrollX`。
- 子區塊直接子節點順序。

### 執行

指令為 `run.sh <fixture> <run> 768,320`，6 次（`ma_cross` run1 重跑過，見 0.1）。

- 與前一輪不同：這次 6 個 run 都帶 `EXTRA_WIDTHS=768,320`。前一輪只有 run1 帶。
- `$P2/runs.txt`：全部 rc=0，stderr 全空。

### G1～G8、W-31 彙整輸出

完整原樣輸出在 `$P2/agg-out.txt`（764 行）。因篇幅，這裡貼 `$P2/agg-gsummary.txt` 的摘錄（同一份輸出中含 G1、G2、G3、G4、G5、G6、G7、G8、W-31a／b 的行）。

- G1（所有 4 組 fixture × 寬度）：`docScrollWidth`、`docClientWidth`、`bodyScrollWidth`、`bodyClientWidth` 在 375 都是 375、1280 都是 1280；`docOverflowsX=False`，`scrollX=0`。容器捲到最大時 `docScrollWidth` 也維持 375／1280。
- G6：第一欄寬 45 值 × 每格，375 全為 112（min=max=112）、1280 全為 176（min=max=176），`all equal: True`（8 格）。
- G5（375，4 格）：x_view 策略欄左緣 min=max=150；`container rect.left 37`（基準 37）；`x_rel = 113`；`post<=baseline for all 45: True`。基準值分別為 158.71875、156.765625、158.578125、156.765625。
- G7（原樣 agg 輸出的比較行）：existing-row heights，375 為最大回撤 57、勝率（依完整回合計）57、其餘 13 列 37（含 週轉率 37）；1280 為 15 列全 37。其中 `週轉率` 為 37，8 格都有一行 `limit(from record)={'最大回撤': 57, '勝率（依完整回合計）': 57, '週轉率': 36.5} ... post<=limit for all: False`，原因見 0.3。
- G7 補算（`$P2/g7_w32.py`，輸出 `$P2/g7_w32-out.txt`）：用 W-32 的上限（週轉率 37；375 最大回撤與勝率 57、其餘 37；1280 全 37）。8 格（2 夾具 × 2 表 × 375／1280）週轉率 3 次 run 都是 `[37, 37, 37]`，`rows exceeding limit: []`。
- G8（8 格）：每格 `cells examined: 189; max(scrollWidth-clientWidth) = 0; scrollWidth>clientWidth violations: 0; Range outside td rect violations: 0; 'scrollWidth unreliable' cells: 0; observation Range.right > td.right-12: 0`。
- G2、G3、G4（8 格）：
  - 定義列區塊 `block.left=38 block.right=337 width=299`（375），scrollLeft=0 與 max（221）兩種狀態都與可視範圍左右邊距為 0，`within visible(+-1) all runs: True`。
  - G3：`block scrollWidth=299 clientWidth=299`、字級 14px、`position=sticky`、`details ancestor=False`、`hidden ancestor=False`、`td colSpan=3`。tr 高度 137／225／197／236.5（在場時間比例列 236.5）。
  - G4：四個錨點列 `nextTrIsDefinition = True`；其他列沒有。
- W-31（375）：
  - W-31a 容器 `scrollWidth 520`（`<=520: True`）。
  - W-31b 在 `scrollLeft=221` 時 Buy & Hold td 20 列 × 3 run，左邊距 min 95、右邊距 min 0，`all within visible +-1: True`、`failing: []`。
  - 1280 的 W-31 為 375-only，值只記錄（容器 scrollWidth 820）。
- 其他欄位（`tableLayout=fixed`、`firstChildTag=COLGROUP`、`colCount=3`，320／768 的 extra 記錄等）都在 `$P2/agg-out.txt`。

## 4. 子區塊專屬（B 1～8）

完整輸出在 `$P2/agg-sub-out.txt`（1470 行，逐項 × 寬度 × 狀態 × run）。壓縮版在 `$P2/compact-sub-out.txt`。檢查彙整在 `$P2/scan-sub-out.txt`，由 `scan_sub.py` 產生。

範圍：2 夾具 × 3 run × 寬度（375、1280、320、768）× 狀態（收合、展開）× 3 行（頁首、樣本內、樣本外）= 144 格。

### 4.1 B1：badge 存在且非 compact、常駐可見

- `badgeCount` 全部為 1（144 格）。
- `reasonCount` 在重跑後的 6 個 run 全部為 1（cold-first 的 375 例外，見第 6 節）。
- badge 的 className 為 `ml-1.5 rounded bg-neutral-800 px-1.5 py-0.5 text-xs text-neutral-400`。這是 `DataMetaStatusBadge` 非 compact 的 `cached_stale` 外觀；文字是完整句，不是「快取資料」單詞。
- reason 的 className 為 `ml-1.5 text-sm text-neutral-400`。
- 祖先鏈（badge 與 reason）：
  - `anyHiddenAttr=false`、`anyDisplayNone=false`、`anyVisibilityHidden=false`、`anyOpacityZero=false`、`anyAriaHidden=false`。
  - `anyTitleAttr=false`、`anyTooltipRole=false`、`insideDetails=false`、`insideTitleOrTooltip=false`。
  - 144 格全部如此（`hiddenFlag: 0`）。

### 4.2 B2：與頁首逐字比較

原字串（run 內頁首與兩個子區塊對照，以 `ma_cross` run3 為例，分鐘數隨 run 不同）：

- **來源與資料截至（頁首與子區塊相同）**：`來源：demo_synthetic｜資料截至 2026-10-02`。
  - 頁首與子區塊 144 格的前三個子節點（`來源：`、`demo_synthetic`、`｜資料截至 2026-10-02`）串接完全相等（`prefixMismatch: 0`）。
  - 原有的「來源：…｜資料截至 …」文字沒有被改掉。
- **badge 文字（頁首）**：`快取資料，資料截至 2026-10-02（14643 分鐘前取得，可能未含最近交易日）`。
- **badge 文字（子區塊，同一 run）**：與頁首同字串。各 run 的分鐘數：run1 14640、run2 14641、run3 14643（`ma_cross`）。`five_conditions` 的 run 內也是頁首與子區塊同值。
- **reason 文字（頁首）**：`最近一次向來源取得資料未成功，暫以本機快取回覆。`
- **reason 文字（子區塊）**：同字串。
- `textMismatchVsHeader: 0`（badge 與 reason 對頁首完全相等，144 格中的 96 個子區塊格）。
- 整行 `innerText`（例）：
  `來源：demo_synthetic\n｜資料截至 2026-10-02\n快取資料，資料截至 2026-10-02（14643 分鐘前取得，可能未含最近交易日）\n最近一次向來源取得資料未成功，暫以本機快取回覆。`

### 4.3 B3：computed 字級

| 項目 | 子區塊 | 頁首 |
|---|---|---|
| 來源行 `<p>`（含前綴文字） | 14px，行高 20px | 14px，行高 20px |
| 「來源：…｜資料截至 …」文字 | 14px | 14px |
| badge | **12px**，行高 16px | **12px**，行高 16px |
| reason | 14px，行高 20px | 14px，行高 20px |

- 子區塊其他內文（開頭句、設定相依句）：14px。
- badge 顏色 `lab(66.128 -0.0000298023 0.0000119209)`，背景 `lab(15.204 0 -0.00000596046)`。
- reason 顏色與前綴文字相同。
- 全部 144 格的 `(是否頁首, 種類, 字級)` 只出現四種組合：頁首 badge 12px、頁首 reason 14px、子區塊 badge 12px、子區塊 reason 14px。

### 4.4 B4：不溢位、不遮擋

以下 2 夾具 × 3 run 值相同（`line_docTop` 與按鈕距離隨夾具不同，另列）。

| 寬 | 狀態 | 行 `<p>` sw／cw | 行 rect（寬×高） | 容器 sw／cw | 行內各元素 Range 在容器內 | 行內元素間重疊 | 與上下相鄰元素重疊 | 與 L-16 按鈕重疊 |
|---|---|---|---|---|---|---|---|---|
| 375 | 收合、展開 | 301／301 | 301×112 | 301／301（子區塊） | 全部 true | 無 | 無 | 無 |
| 1280 | 收合、展開 | 822／822 | 822×48 | 822／822 | 全部 true | 無 | 無 | 無 |
| 320 | 收合、展開 | 246／246 | 246×140 | 246／246 | 全部 true | 無 | 無 | 無 |
| 768 | 收合、展開 | 694／694 | 694×76 | 694／694 | 全部 true | 無 | 無 | 無 |

- 頁首行的容器是整個報告 `<section>`：375 為 341／341、1280 為 862／862。
- 144 格的 `lineSW>CW`、`containerSW>CW`、`badgeSW>CW`、`reasonSW>CW`、`nodeOutsideContainer`、`prevNextOverlap`、`buttonOverlap`、`childOverlap` 全部為 0。
- badge 與 reason 元素本身的 `scrollWidth/clientWidth`：
  - 375：badge 295／295，reason 295／295。
  - 1280：badge 425／425，reason 336／336。
  - 320：badge 240／240。
- 行內版面（Range rect，單位 px）：
  - 375：
    - 第 1 排：「來源：」37–79，「demo_synthetic」79–177.0625，「｜資料截至 2026-10-02」185.0625–330.296875。
    - 第 2 排：badge 49.00–318.42（range 2 行文字，rect 高 36）。
    - 第 3 排：reason 43–337（2 行，rect 高 40）。
    - 共 3 排。
  - 1280：
    - 前綴 229–369.0625，「｜資料截至」377.0625–522.296875，badge 542.296875–955.71875（1 行）。
    - reason 在第 2 排，235–571（1 行）。
    - 共 3 個不同 row top。
  - 320：badge 2 行、reason 2 行，共 4 排。
  - 768：badge 1 行、reason 1 行，共 3 排。
- 相鄰元素間距（子區塊）：上一個元素（開頭句）與本行間距 8px，下一個元素（設定相依句）與本行間距 8px。頁首行：上 4px、下 12px。
- 頁面層級（`docScrollWidth`／`docClientWidth`／`bodyScrollWidth`／`scrollX`）：
  - 375：375／375／375／0。
  - 1280：1280／1280／1280／0。
  - 320：320／320／320／0。
  - 768：768／768／768／0。
  - 收合與展開兩種狀態、2 夾具 × 3 run 都相同。
- L-16 按鈕位置：
  - 375，樣本內：按鈕 docTop 減去來源行 bottom docTop，`ma_cross` 為 775，`five_conditions` 為 889。
  - 375，樣本外：按鈕 docTop 減去來源行 bottom docTop，`ma_cross` 為 1003，`five_conditions` 為 832。
  - 這個距離是正值，來源行在按鈕上方。

### 4.5 B5：子區塊 DOM 順序

兩個子區塊、兩夾具 × 3 run 一致，直接子節點為：

| 索引 | 元素 | 內容（前段） |
|---|---|---|
| 0 | `h3` | `樣本內：完整回合明細`（樣本外為 `樣本外：完整回合明細`） |
| 1 | `p` | `本子區塊呈現的是以歷史價格資料模擬的結果，不是對未來報酬或損失幅度的預測。所列欄位皆由本次回測的價格資料與設定算出，不含當時的新聞或事件說明。`（L-13 開頭句） |
| 2 | `p`（來源行） | `來源：demo_synthetic｜資料截至 2026-10-02` + badge + reason |
| 3 | `p` | `本區段的回合報酬率與已實現損益，以及由它們算出的各項，依本次回測的成本設定計入成本；…`（L-12 設定相依句） |
| 4 | `div` | 內含 `h4` `本區段排除的回合`、dl 與說明段（排除回合小節） |
| 5 | `div` | 回合報酬率最低的幾筆（含按鈕、table） |
| 6 | `div` | 隱藏的完整明細（`hidden`） |

- 來源行 `sourceLineIndexInChildren=2`。
- 前一輪 `agg-out.txt` 的子區塊序列另有細部（h3、p、p、p、h4、dl、p、h4、p、table、button、div hidden、table hidden）。
- 以上結構與前一輪順序相同，只是第 2 項多了 badge 與 reason。

### 4.6 B6：展開與收合兩種狀態

- 兩個狀態都量（`sub[width].collapsed` 與 `.expanded`）。
- 樣本內來源行位置（`docTop`）：收合與展開相同。
  - `ma_cross`：375 為 6888／6888，1280 為 4462／4462，320 為 7504／7504，768 為 4710／4710。
  - `five_conditions` 見 `$P2/agg-sub-out.txt` 末段「source line docTop collapsed vs expanded」。
- 樣本外來源行會往下移，因為上方樣本內展開後變高。`ma_cross` 的 `docTop` 收合→展開：
  - 375：7959→8102。
  - 1280：5069→5152。
  - 320：8743→8886。
  - 768：5385→5508。
- 展開後頁面層級溢出：`docScrollWidth=docClientWidth=bodyScrollWidth`，`scrollX=0`，4 個寬度皆如此。
- 展開後 badge 與 reason 的 rect、scrollWidth、fontSize 與收合相同。
- 按鈕文字：收合為 `展開全部 1 筆完整回合明細`（樣本外 `展開全部 2 筆完整回合明細`），展開後為 `收合全部 …`。

### 4.7 B7：375 的 L-16 按鈕

- `ma_cross` 與 `five_conditions` 的 375，收合與展開，兩個按鈕皆為 `height=44`、`textLineCount=1`、`whiteSpace=normal`、`fontSize=14px`，寬度 203.578125、`left=37`、`scrollWidth/clientWidth=202/202`。
- 320、768、1280 也都是高 44、`textLineCount=1`（`scan-sub-out.txt` 最末行）。

### 4.8 B8：console 與 network（全 6 run + cold-first）

- `consoleErrors=[]`、`consoleWarnings=[]`、`consoleOther=[]`、`failedRequests=[]`、`externalRequests=[]`，`externalRequestCount=0`。
- `pageerror` 沒有出現（已併入 `consoleErrors`，為空）。
- 逐 run 原始清單在 `$P2/agg-sub-out.txt` 尾段與各 `stdout-*.txt`。

### 4.9 補充：`gap-2` 間距特寫（qa-reviewer 提到的）

截圖路徑：

- 375：`$P2/shots/ma_cross-run1-w375-subblock0-sourceline-collapsed.png`（樣本外為 `...subblock1...`）。
- 1280：`$P2/shots/ma_cross-run1-w1280-subblock0-sourceline-collapsed.png`（樣本外為 `...subblock1...`）。
- 展開狀態用 `...sourceline-expanded.png`。
- 全部 run、寬度的特寫都在 `$P2/shots/`（檔名含 `sourceline`）。全頁與表格截圖也在同目錄。

量測：

- 「來源：」與「demo_synthetic」是相鄰文字節點，Range 邊界相接（375：79 與 79），中間沒有 gap。
- 「demo_synthetic」與 `<span>｜資料截至 …` 之間多了 8px：375 為 177.0625→185.0625，1280 為 369.0625→377.0625。
- 我看過兩張特寫：375 版面是第 1 排 `來源：demo_synthetic  ｜資料截至 2026-10-02`，第 2 排 badge 晶片，第 3 排 reason 句（2 行）。1280 版面是 `來源：demo_synthetic  ｜資料截至 2026-10-02  [badge 晶片]`，reason 句在第 2 排。

## 5. 無法驗收

這些狀態沒有 e2e 夾具，實機沒有看到：

- `backup`、`unavailable`、`fresh` 帶 `reason`：無法驗收，由渲染測試負責。
- `cached_stale` 且 `is_within_ttl` 為 true：無法驗收。本夾具 `is_within_ttl=false`。
- `reason` 為 null 的 `cached_stale`：本輪重跑 6 個 run 都沒有。只有 cold-first 的 375 偶然出現（第 6 節）。

## 6. cold-first 的事實（`ma_cross` run1 第一次執行）

- 不屬於 3 個 run 的彙整，原始產物在 `$P2/cold-first/`。
- API：`apiMeta` 的 375 為 `reason=null`、`staleness_minutes=14640`、`is_within_ttl=false`、`status=cached_stale`。320、768、1280 的 reason 為 `最近一次向來源取得資料未成功，暫以本機快取回覆。`。
- DOM（收合與展開都一樣）：
  - 375：頁首、樣本內、樣本外三行 `reasonCount=0`、`badgeCount=1`。
  - 其他三個寬度：三行 `reasonCount=1`、`badgeCount=1`。
- 375 的樣本內來源行 `innerText`：`來源：demo_synthetic\n｜資料截至 2026-10-02\n快取資料，資料截至 2026-10-02（14640 分鐘前取得，可能未含最近交易日）`。行 rect 301×64，sw／cw 301／301。
- 頁面溢出 375／1280／768／320 皆無。console／network 全空。
- 原因觀察：第一個請求觸發對外取資料失敗（後端 log 有 `Connection refused`），該次回覆 reason 為 null；同一 run 稍後的請求才帶 reason 句。這是我從 log 與資料推得的現象，沒有讀後端程式碼確認機制。

## 7. 其他需要揭露的偏離

- `agg.py` 只改了 `O` 的目錄路徑（`e2e-f11-post` → `e2e-f11-post2`），比較邏輯與 G7 的舊 36.5 上限沒動（見 0.3）。
- `scan_sub.py` 的 `ex` 字典有三個鍵 `badgeFont<14`、`reasonFont<headerPrefixFont`、`orderMismatch` 我沒有寫對應的計算，輸出 0 只是沒填值，不是「檢查通過」。字級與順序請看 4.3 與 4.5 的實測值。
- `EXTRA_WIDTHS=768,320` 這次 6 個 run 都帶，前一輪只有 run1。
- 我在主工作樹 backend 做過一次 `ls data`（只列檔名），與 `stat` 兩個 db。除此之外沒有讀、複製、hash 或寫入 `apps/stock-desk/backend/data/*.db`，也沒有讀 `.env`。
- 後端 DB 路徑都指到 scratchpad，沒有碰主工作樹 db。

## 8. 自我揭露

- 指令類型：
  - 唯讀探測：`ls`、`ps`、`stat`、`sha256sum`、`curl`（只打本機 3000、8000）、`git status/rev-parse`、`grep`、`diff`。
  - 檔案複製與刪除：`cp -a` 主工作樹 `node_modules` 到 worktree，`rm -rf` 我自己建的 `node_modules`、`.next`、`next-env.d.ts`。
  - 建置與服務：`next build`、`next start`、`python -m uvicorn`。
  - 量測與彙整：`node measure.js`（經 `run.sh`）、`python3 -I agg.py` 與我寫的 `agg_sub.py`、`scan_sub.py`、`compact_sub.py`、`g7_w32.py`。
- 沒有執行任何安裝、更新、下載。沒有改動受測程式與測試。沒有 commit。沒有碰主工作樹。
- 有越界嗎：我認為沒有。唯一接近邊界的是 `ls data`（只列名稱）。
- 判斷：全程只交事實與數值，沒有下 Verdict。

## 9. 產物清單（`$P2`）

- 腳本：`measure.js`、`harness.diff`、`run.sh`、`env.sh`、`agg.py`、`agg_sub.py`、`scan_sub.py`、`compact_sub.py`、`g7_w32.py`。
- 彙整輸出：`agg-out.txt`、`agg-gsummary.txt`、`agg-sub-out.txt`、`compact-sub-out.txt`、`scan-sub-out.txt`、`g7_w32-out.txt`。
- 原始：`raw/*.json`、`stdout-*.txt`、`stderr-*.txt`、`runs.txt`、`backend.log`、`frontend.log`、`frontend-build.log`。
- 環境與狀態：`git-before.txt`、`git-after.txt`、`git-ignored-*.txt`、`data-db-stat-*.txt`、`fixture-sha256-*.txt`。
- 截圖：`shots/`（312 張）、`cold-first/shots/`（52 張）。
- 截圖只留在 scratchpad，沒有複製到別處。驗收爭議釐清後可刪除。

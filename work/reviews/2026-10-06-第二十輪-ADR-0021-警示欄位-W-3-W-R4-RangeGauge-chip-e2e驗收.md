# 第二十輪：ADR-0021 警示欄位（W-3／W-R4／W-1）、D-10 補拍、chip 四態、console 404、D-11 基線——實機驗收證據（e2e-fallback 代跑）

- 日期：2026-10-06。取證時間 2026-10-06T15:10Z～15:27Z（UTC，見 `start-time.txt`、`end-time.txt`）。
- 受測 commit：`product/stock-desk` 的 `3e249fdd6f38fd75feede1d1a1e1d270d4965369`。開跑前後 HEAD 相同。
- 代跑者：qa-automation。**本檔只交事實證據，不下 Verdict、不輸出 `BLOCKING_ISSUES`；判斷權屬 qa-e2e。**
  各項表中的「對照預期」欄僅是「量測值與派工單所列數值條件是否一致」的事實比對，不是驗收判定。
- 證據位置（scratchpad，不在 repo 內）：`/tmp/claude-0/-home-user-AICompany/3f76d891-50d3-55e1-b39d-925b8a90241a/scratchpad/e2e-20/`
  - 原始輸出：`runner-stdout-S.json`（設定頁，8 run）、`runner-stdout-P.json`（個股頁，12 run）、`runner-stdout-H.json`（首頁，4 run）、`runner-stdout-BL.json`（D-11 基線，8 run）、`runner-rc-*.txt`（皆 `rc=0`）、`runner-stderr-*.txt`（皆空）、`probe-innertext-output.json`。
  - 腳本：`runner.js`（由 `_parts_*.js` 組成）、`adjust-db20.py`、`start-backend.sh`、`run-state.sh`、`proof.sh`、`summarize-P.py`。
  - 環境證明與稽核：`process-env-proof.txt`、`git-state-before.txt`／`git-state-after.txt`、`stat-data-before.txt`／`stat-data-after.txt`、`frontend-build.log`、`backend-1.log`、`frontend-1.log`／`frontend-2.log`。
  - 截圖：全部來自 `next build --webpack` ＋ `next start --port 3000`，沒有任何一張來自 dev。
- 資料與啟動方式：
  - 全部是合成示範資料（API `data.source`＝`demo_synthetic`，`data.status`＝`cached_stale`）。複本 DB 在 `scratchpad/db20/e2e.db`（由 `db19/stateA.db` 複製；已複製的 db19 本身是先前輪次的 tmp 複本，非 `backend/data/`）。
  - 舊規則直接寫入複本 SQLite（`adjust-db20.py`，只開 `scratchpad/db20/e2e.db`）。新增 4 條：id 4 `beta.value` value 型（2330，啟用）、id 5 `close` 對 `ref=beta.value`（00631L，**已停用**）、id 6 `position.weight` value 型（0050，啟用）、id 7 `ma5.last` 對 `ref=ma20.last`（00675L，對照組，可評估）。原有 id 1～3 保留。
  - 三個資料集的取得：後端為真實 uvicorn 回傳全部 7 條規則；瀏覽器端以 `ctx.route` 攔截 `GET /api/alerts`，只保留指定 id（`BETAV`＝[4]、`BETAREF`＝[5]、`POSW`＝[6]），另跑一組不攔截的 `NALL`（全部 7 條）。`PATCH` 一律打到真實後端（W-R4 的 422 是**真實後端回應，不是 mock**）。
  - 啟動：後端 `uvicorn app.main:app --port 8000`（無 reload）、`STOCK_DESK_DB_PATH`／`STOCK_DESK_MARKET_DB_PATH`／`STOCK_DESK_RESEARCH_DB_PATH` 皆指 `scratchpad/db20/`；前端 `next start --port 3000`。啟動前設死埠 proxy `http://127.0.0.1:9`、`NO_PROXY=127.0.0.1,localhost`；瀏覽器端以 `ctx.route` abort 所有非 loopback 請求（`externalRequests` 全部 run 為 0）。
  - 儀器：`provenance.playwrightModule`＝`/opt/node22/lib/node_modules/playwright/index.js`、`provenance.chromiumExecutable`＝`/opt/pw-browsers/chromium-1194/chrome-linux/chrome`、`provenance.trustedPrefix`＝`/opt/`；四個 runner 的 stdout 皆如此（runner 有 fail-closed 前綴斷言）。
  - 預設 viewport 高度 812（寬 375／390）。

## 流程偏差與如實揭露（先看這段）

1. **前端埠 3020 → 3000（第一批設定頁證據作廢，已隔離）。**一開始前端用 3020，後端 CORS 只允許 `http://localhost:3000`（`app/main.py` `FRONTEND_DEV_ORIGIN`），瀏覽器 console 出現 CORS error、`/api/settings` 與 `/api/alerts`（未攔截的 run）被擋，`NALL` 找不到表格。該批原樣保留在 `run1-invalid-port3020/`，**不採用**；改用 3000 後整批重跑（S 批）。這是我選埠造成的環境問題，不是產品缺陷。
2. **個股頁第一批 P 作廢（漏跑 `expandAll`，已隔離）。**第一次 P 批 runner 漏了「展開所有 `<details>`」，gauge 在收合的 details 內，`innerText` 為空字串、gauge 元素截圖逾時 30 秒。該批原樣保留在 `run2-P-without-expand/`，**不採用**；補上展開步驟後整批重跑。`probe-innertext-output.json` 可證實：收合時 `innerText=""`、`textContent` 有字。
3. **首頁 H 批重跑一次**（為了補「持倉明細全寬截圖」）；第一次的原始 json 留在 `run3-H-first/`，數值與重跑一致。
4. **工作樹出現非我造成的 tracked 變更。**開跑前 `git status --short` 只有兩個 `work/` 檔；結束時另出現：`apps/stock-desk/backend/app/alerts/engine.py`、`backend/tests/test_adr0021_field_evaluability.py`、`backend/tests/test_alerts_engine.py`（皆為 **staged `M `**，即別人已 `git add`）與 `docs/adr/0020-…單一來源.md`（` M`）。我全程沒有 `git add`／commit／編輯任何 tracked 檔；`engine.py` mtime 為 15:13:01，晚於我後端啟動時間（約 15:10，Python 已載入模組），這些變更不在本次驗收的程式路徑（顯示層），但**受測 commit 嚴格說是「HEAD ＋ 他人未提交變更」**。我自己造成的檔案變更：僅 `apps/stock-desk/frontend/.next/`（`next build` 產物，git-ignored）。
5. 設定頁的 console 計數：**載入階段** vs **互動階段**分開記（`loadPhase`）。W-R4 故意送出會 422 的 PATCH，瀏覽器會多一筆 `Failed to load resource: the server responded with a status of 422`，這筆屬操作階段，不計入載入階段。

## HEAD 與 DB 稽核

- HEAD 前：`3e249fdd6f38fd75feede1d1a1e1d270d4965369`（branch `product/stock-desk`）；HEAD 後：`3e249fdd6f38fd75feede1d1a1e1d270d4965369`。**相同。**
- `stat` 前後（`diff` 無輸出，兩檔逐字相同；`Access` 時間 14:16:29／14:16:30 早於本輪開始，表示本輪沒有讀取）：
  - `stock-desk.db`：Size 159744、Modify 2026-10-04 14:15:41.470506705 +0000、Change 同、Inode 500014。
  - `stock-desk-market.db`：Size 98304、Modify 2026-10-04 15:09:46.826306790 +0000、Change 同、Inode 501649。
- 全程未對 `backend/data/*.db` 做 sha256sum／sqlite3／cat／開檔；也未讀 `.env`。
- 環境證明（`process-env-proof.txt`，3 段）：backend pid 29078、next-server pid 30835（前一個 29267 已因埠 3020 改 3000 而停掉），皆有 `HTTP_PROXY=HTTPS_PROXY=ALL_PROXY=http://127.0.0.1:9`、`NO_PROXY=127.0.0.1,localhost`，backend 的三個 `STOCK_DESK_*_DB_PATH` 皆指 `scratchpad/db20/`。收尾已只殺自己啟動的 backend／next-server，`ps` 無殘留。

## 逐項事實

### 1. W-3 可見性（設定頁警示規則清單）

表頭欄序：代號｜類型｜條件｜狀態｜建立時間｜操作；表容器 `overflow-x-auto`，table `min-w-[620px]`。容器 scrollWidth／clientWidth：375 為 620／299、390 為 620／314；初始 `scrollLeft=0`。頁面 `docScrollWidth`＝375／390（無頁面水平溢出）。notice 元素：`div.mt-0.5.max-w-[9rem].border-l-2.border-amber-400.pl-1.5.text-xs.leading-snug.text-amber-400`，位於第一欄 `td` 內、`代號（市場）` 那個 div 之下。

逐字文字：`不會觸發（欄位不提供）`（innerText 與 textContent 相同）。

| 資料集 | 寬 | 規則（條件欄原文） | 狀態欄原文 | notice rect（left／right／width×height） | 行數與折行 | scrollWidth／clientWidth | scrollHeight／clientHeight | 右緣 ≤ 容器可視右緣 | 右緣 ≤ viewport | 與代號 div 距離 | 狀態欄 rect.left／是否在初始可視範圍 |
|---|---|---|---|---|---|---|---|---|---|---|---|
| BETAV | 375 | `beta.value 大於（>） 1.5` | `啟用中` | 50／156.02／106.02×33 | 2：`不會觸發（欄位不`／`提供）` | 104／104 | 33／33 | 是（容器 right 338） | 是 | 2px | 377.8／否（容器右緣 338） |
| BETAV | 390 | 同上 | `啟用中` | 50／156.02／106.02×33 | 2（同） | 104／104 | 33／33 | 是（353） | 是 | 2px | 377.8／否（353） |
| BETAREF | 375 | `close 大於（>） 相對指標的 beta` | `已停用` | 50／152.03／102.03×33 | 2：`不會觸發（欄位`／`不提供）` | 100／100 | 33／33 | 是 | 是 | 2px | 384.77／否 |
| BETAREF | 390 | 同上 | `已停用` | 50／152.03／102.03×33 | 2（同） | 100／100 | 33／33 | 是 | 是 | 2px | 384.77／否 |
| POSW | 375 | `position.weight 大於（>） 0.3` | `啟用中` | 50／149.39／99.39×33 | 2：`不會觸發（欄位`／`不提供）` | 97／97 | 33／33 | 是 | 是 | 2px | 389.38／否 |
| POSW | 390 | 同上 | `啟用中` | 50／149.39／99.39×33 | 2（同） | 97／97 | 33／33 | 是 | 是 | 2px | 389.38／否 |
| NALL（7 條，3 條有 notice） | 375／390 | id4／id5／id6 三條 | `啟用中`／`已停用`／`啟用中` | 三條皆 50／128.53／78.53×49.5 | 3：`不會觸發`／`（欄位不提`／`供）` | 77／77 | 50／50 | 是 | 是 | 2px | 425.72／否（4 個無 notice 的對照規則也是 425.72） |

- 量測的 notice 計算樣式（所有 run 相同）：`color: oklch(0.828 0.189 84.429)`；經 canvas 轉 sRGB 為 `rgb(255, 185, 0)`；`border-left-color` 同色、寬 `2px`；`fontSize 12px`、`lineHeight`＝leading-snug、`maxWidth 144px`（＝9rem）、`overflow: visible`、`overflow-x: visible`、`text-overflow: clip`（無 ellipsis 設定）、`white-space` 為預設可換行、`display: block`、`opacity: 1`、`visibility: visible`。
- 建置後 CSS 內 `--color-amber-400` 定義為 `oklch(82.8% .189 84.429)`（從 `.next/static` 內 CSS 以 grep 取得），與量到的 computed color 相同。
- notice 自身祖先中，`overflow` 非 visible 的只有 table 容器 `DIV`（`overflow-x: auto`，即上述 `overflow-x-auto` 捲動容器）；沒有 `overflow: hidden`、沒有 `text-overflow: ellipsis`。notice 與狀態欄文字區塊矩形不相交（`notOverlappingStatusText: true`）。
- 只有清單裡 id4／id5／id6 三條有 notice；`NALL` 的 id1／id2／id3／id7（價格、`drawdown.max_drawdown`、風險上限、`ma5.last` 對 `ma20.last`）皆無 notice（`hasNotice: false`）。
- **事實註記（不下判斷）**：(a) 狀態欄「啟用中／已停用」與 notice 在同一列 DOM 並存，但 table 為 `min-w-[620px]`，在 375／390 的初始水平捲動位置（`scrollLeft=0`）下**狀態欄在容器可視範圍之外**（left 377.8～425.72 > 容器 right 338／353），需把容器捲到最右（捲到底 scrollLeft＝321／306 後狀態欄 right 為 112.25～166.64，皆在容器內，見 `*-alert-list-viewport-scrolled-end.png`）才看得到。notice 本身在第一欄，初始就完整可見。(b) 清單在整頁中的位置偏下：`NBETAV` run 中 notice 的文件座標 top＝4786px（需垂直捲動才進第一屏）；所列「初始可視範圍」我以「水平 `scrollLeft=0`、不水平捲動」衡量，並另用 `scrollIntoView` 後的 viewport 截圖呈現使用者看到的畫面。(c) `NALL` 的 notice 因條件欄較寬，第一欄被擠窄，notice 寬降為 78.53、折 3 行（`供）` 單獨成行），仍 scrollWidth＝clientWidth、scrollHeight＝clientHeight。
- 截圖（375／390 各一組；`<w>` 為 375 或 390）：
  - `NBETAV-settings-<w>-alert-list-viewport-initial.png`、`NBETAV-settings-<w>-alert-table-initial.png`、`NBETAV-settings-<w>-alert-list-viewport-scrolled-end.png`
  - `NBETAREF-settings-<w>-…`、`NPOSW-settings-<w>-…`（同三種後綴）
  - `NALL-settings-<w>-alert-list-viewport-initial.png`、`…-alert-table-initial.png`、`…-scrolled-end.png`、`…-full-all-open.png`
- 對照預期（事實比對）：notice 在第一欄代號下方：符合；全文完整（scrollWidth≤clientWidth、無 ellipsis、無 hidden）：符合；computed color＝amber-400：符合；與狀態欄並存：同列 DOM 並存符合，但狀態欄在 `scrollLeft=0` 時位於可視範圍外（見註記 a）。

### 2. W-R4 路徑（舊 value 型 beta 規則只改比較值並送出）

流程（`NBETAV`，375／390 各一次；打真實後端）：進設定頁 → 點該列「編輯」→ 對話框 `編輯警示規則「2330」`（比較值原為 `1.5`）→ 只把 `#edit-alert-value` 改成 `2` → 點「儲存變更」。

- 送出的請求（原樣）：`PATCH http://localhost:8000/api/alerts/4`，body `{"params":{"condition":{"field":"beta.value","op":"gt","value":2,"ref":null}}}`。
- 後端回應（原樣）：HTTP **422**，`content-type: application/json`，body
  `{"detail":[{"type":"alert_field_unevaluable","loc":["body","params"],"msg":"警示不提供 beta.value（相對指標的 beta）作為條件，請改用其他欄位。","input":{"condition":{"field":"beta.value","op":"gt","value":2,"ref":null}},"ctx":{"field":"beta.value（相對指標的 beta）"}}]}`
- 對話框內顯示（原樣）：對話框仍開啟；`[role="alert"]` 元素 1 個，`class="space-y-1 rounded-md border border-red-900 bg-red-950/40 px-4 py-3 text-sm text-red-300"`，文字 **`警示不提供 beta.value（相對指標的 beta）作為條件，請改用其他欄位。`**（與 W-4 字串逐字相等：`equalsW4: true`；對話框完整 innerText 也含該句，`containsW4Verbatim: true`）。顏色 computed `oklch(0.808 0.114 19.571)`（`text-red-300`）。
- 重送後規則未變動：`GET /api/alerts` 內 id 4 的 params 仍為 `value: 1.5`、`updated_at` 仍為 `2026-10-03T07:54:05.423364Z`（`ruleUnchanged: true`）。
- 對話框內同時顯示：`訊號欄位：相對指標的 beta`＋`不會觸發（欄位不提供）`（K-9 notice 區塊）、欄位下拉 `相對指標的 beta` 為第一個 option（共 20 個 option＝19 項選單＋該舊欄位）、W-1 句常駐。
- 版面事實：對話框 `max-h-full overflow-y-auto`，scrollHeight／clientHeight 在 375＝855／746、390＝855／746。**送出當下，錯誤框 rect top 740.5、bottom 806.5，而對話框可視底緣 780**（375 與 390 皆同）：即錯誤框下半段在對話框可視區之外，需在對話框內往下捲才能看到完整三行；送出當下 viewport 截圖只看到錯誤框前兩行被切斷（`NBETAV-settings-375-wr4-dialog-after-submit-viewport.png`），捲到底後完整可見（`…-after-submit-scrolled-bottom.png`）。錯誤框水平方向在對話框內（`insideDialogHoriz: true`）、docScrollWidth＝viewport。
- 操作階段 console：1 筆 `Failed to load resource: the server responded with a status of 422 (Unprocessable Entity)`，loc `http://localhost:8000/api/alerts/4`（預期，因故意送出）。
- 截圖：`NBETAV-settings-<w>-wr4-dialog-opened.png`、`…-wr4-dialog-after-submit-viewport.png`、`…-wr4-dialog-after-submit-scrolled-bottom.png`、`…-wr4-dialog-element.png`（<w>＝375／390）。
- 對照預期（事實比對）：422：符合；對話框內逐字顯示 W-4：符合；非靜默失敗：符合（有顯示）；送出當下需在對話框內捲動才完整可見：見上（事實，供 qa-e2e 判斷）。

### 3. W-1（新增規則表單選「訊號條件」）

- 在 `#alert-type` 選「訊號條件」後：`#alert-field-note`（`p.mt-1.text-xs.text-neutral-400`，`aria-describedby` 指向它）逐字 **`警示不提供 Beta 作為條件，可在個股頁「風險量測」區查看。`**，與 W-1 字串相等：預設欄位（`close`）、改選 `rsi14.last`、改選 `drawdown.max_drawdown` 後三次皆 `true`。
- 可見性量測：`display: block`、`visibility: visible`、`opacity: 1`、`clientRects` 1 個、無 `sr-only`、無 `title`、無 `clip`／`clip-path`（`clip: auto`、`clip-path: none`）、祖先無非 visible overflow；rect 375＝left 37／right 338／寬 301×高 32，390＝left 37／right 353／寬 316×高 32；`fontSize 12px`、color `oklch(0.708 0 none)`（neutral-400）；折 2 行（375：`…「風險量測」區`／`查看。`；390：`…「風險量測」區查`／`看。`），`scrollWidth＝clientWidth`（301／301、316／316）。
- 欄位下拉選單：**19 個 option**，value 依序為 `close, ma5.last, ma20.last, ma60.last, rsi14.last, macd.last, macd.signal, macd.histogram, bollinger.middle, bollinger.upper, bollinger.lower, bollinger.bandwidth, bollinger.percent_b, atr14.last, kd.k, kd.d, volume_z.last, volatility.annualized, drawdown.max_drawdown`；任何 value 或 label 含 `beta`（不分大小寫）者：0 個；`beta.value`／`position.weight`／`position.unrealized_pnl_pct` 出現在選單：0 個。（label 逐字：最新收盤價、5 日均線最新值、20 日均線最新值、60 日均線最新值、14 日 RSI 最新值、MACD 快慢線差最新值、MACD 訊號線最新值、MACD 柱狀圖最新值、布林通道中軌、布林通道上軌、布林通道下軌、布林通道寬度、布林通道 %B、ATR(14) 最新值、KD 指標 K 值、KD 指標 D 值、成交量 z 分數最新值、年化波動度、區間最大回撤。）
- 截圖：`NBETAV-settings-<w>-w1-viewport-default-field.png`、`NBETAV-settings-<w>-w1-create-form.png`。
- 對照預期（事實比對）：常駐可見：符合；19 項、無 Beta：符合。

### 4. D-10 補拍（RangeGauge，2330，改寫 `/api/bars/2330` 最後一根收盤；合成資料）

| 資料集 | 寬 | 位階 | 標籤文字 | 標籤寬 | 標籤 left／right 距 figure | 距 card 左／右 | 距 viewport 左／右 | figure scrollW／clientW | figcaption scrollW／clientW | 與其他文字重疊 | docScrollWidth |
|---|---|---|---|---|---|---|---|---|---|---|---|
| GHIGH100 | 375 | 100 | `收盤位於 100%` | 98.03 | 183.98／**0.98** | 196.98／13.98 | 229.98／46.98 | 291／283（差 8） | 283／283 | 0 | 375 |
| GHIGH100 | 390 | 100 | 同 | 98.03 | 198.98／**0.98** | 211.98／13.98 | 244.98／46.98 | 306／298（差 8） | 298／298 | 0 | 390 |
| GLOW0 | 375 | 0 | `收盤位於 0%` | 81.22 | **9.39**／192.39 | 22.39／205.39 | 55.39／238.39 | 283／283 | 283／283 | 0 | 375 |
| GLOW0 | 390 | 0 | 同 | 81.22 | **9.39**／207.39 | 22.39／220.39 | 55.39／253.39 | 298／298 | 298／298 | 0 | 390 |

- 標籤 rect：GHIGH100 375 ＝ left 229.98／right 328.02、figure left 46／right 329；GHIGH100 390 ＝ left 244.98／right 343.02、figure right 344；GLOW0 左緣距 figure 左 9.39。標籤單行。「距 figure 右」欄在 GHIGH100 為 0.98（正值＝標籤右緣在 figure 內），與 round 19 的 −49.02 相比由超出變為在內。
- figure scrollWidth 比 clientWidth 大 8px 僅出現在位階 100（375／390），是游標圓點（thumb，`h-4 w-4`＝16px、`-translate-x-1/2`）在右端溢出 8px；GLOW0（圓點在左端）scrollWidth 等於 clientWidth。thumb 溢出為 art-lead 已接受項目。
- 範圍文字：`近 252 根區間`、`區間最低 705.36`、`區間最高 1,004.44`（皆單行）。
- 截圖（全寬卡片）：`GHIGH100-2330-375-gauge-card-0-fullwidth.png`、`GHIGH100-2330-390-gauge-card-0-fullwidth.png`、`GLOW0-2330-375-gauge-card-0-fullwidth.png`、`GLOW0-2330-390-gauge-card-0-fullwidth.png`；另有 `…-gauge-0.png`（figure 本體）。目視：100% 時 `收盤位於 100%` 右緣貼近卡片右內緣、末字「%」完整；0% 時標籤左緣在卡片內。
- 對照預期（事實比對）：標籤在 figure 可視範圍內：符合（兩側距離皆 ≥ 0）；頁面無水平溢出：符合（docScrollWidth＝viewport）。

### 5. chip 四態

**個股頁**（DataMetaStatusBadge，位於「決策摘要」「技術分析」兩顆、「操作摘要」；以改寫 `data.status`／`data.reason` 取得 backup／unavailable／fresh；BREAL 為真實後端 `cached_stale`）。下表為同一頁面所有 chip 的 computed 值（同一狀態在各處完全相同，已去重）：

| 資料集 | 寬 | chip 文字 | computed color（原值）→ sRGB | border（寬／style／color 原值 → sRGB） | 疊合後背景 sRGB | 對比 | rect（寬×高） | 折行 |
|---|---|---|---|---|---|---|---|---|
| BUNAV（`unavailable`） | 375／390 | `資料不足` | `oklch(0.922 0 none)` → **rgb(229, 229, 229)** | **1px／solid／`oklch(0.556 0 none)` → rgb(115, 115, 115)** | rgb(38, 38, 38) | 12.01 | 62×22 | 單行 |
| BBACKUP（`backup`） | 375／390 | `備援源` | `oklch(0.879 0.169 91.605)` → rgb(255, 210, 48) | 0px／solid（無框線） | rgb(55, 26, 8) | 11.05 | 48×20 | 單行 |
| BREAL（真實 `cached_stale`） | 375／390 | `快取資料` | `oklch(0.708 0 none)` → rgb(161, 161, 161) | 0px／solid（無框線） | rgb(38, 38, 38) | 5.86 | 60×20 | 單行 |
| BFRESH（`fresh`） | 375／390 | 無 chip（`chips` 長度 0） | — | — | — | — | — | — |

- 建置後 CSS：`--color-neutral-200: oklch(92.2% 0 none)`、`--color-neutral-500: oklch(55.6% 0 none)`；與 `資料不足` 的 computed color／border color 相同（即 neutral-200／neutral-500）。`資料不足` chip class：`ml-1.5 rounded border border-neutral-500 bg-neutral-800 px-1.5 py-0.5 text-xs text-neutral-200`；字級 12px。
- 技術分析標題列：`techPairOverlaps`、`techFinePairOverlaps`、決策列 `pairOverlaps` 皆為空陣列（無元素兩兩重疊）；所有 12 個個股頁 run docScrollWidth＝viewport。
- 截圖：`BUNAV-2330-<w>-badge-row-tech-title.png`、`BUNAV-2330-<w>-badge-row-decision.png`、`BUNAV-2330-<w>-decision-card.png`；`BBACKUP-…`、`BREAL-…`、`BFRESH-…` 同三種後綴（<w>＝375／390）。

**首頁**（DataStatusBadge，持倉明細；改寫 `GET /api/portfolio/summary`：2330→`backup`、0050→`fresh`、00631L→`unavailable`、00675L→`price: null`（`status: insufficient_data`）；`HOMEREAL` 為真實後端 4 檔皆 `cached_stale`、`is_within_ttl: false`）：

| 資料集 | 寬 | chip 文字 | computed color → sRGB | border | 疊合後背景 | 對比 | rect | 折行 |
|---|---|---|---|---|---|---|---|---|
| HOMEMIX（00631L、00675L） | 375／390 | `資料不足`（2 個） | `oklch(0.922 0 none)` → rgb(229, 229, 229) | 1px solid `oklch(0.556 0 none)` → rgb(115, 115, 115) | rgb(38, 38, 38) | 12.01 | 62×22／62×20 | 單行 |
| HOMEMIX（2330） | 375／390 | `備援源` | `oklch(0.879 0.169 91.605)` → rgb(255, 210, 48) | 0px | rgb(55, 26, 8) | 11.05 | 48×20 | 單行 |
| HOMEMIX（0050，`fresh`） | 375／390 | 無 chip | — | — | — | — | — | — |
| HOMEREAL（4 檔） | 375／390 | `資料較舊`（4 個） | `oklch(0.708 0 none)` → rgb(161, 161, 161) | 0px | rgb(38, 38, 38) | 5.86 | 60×20 | 單行 |

- 首頁 chip class：`資料不足`＝`whitespace-nowrap rounded border border-neutral-500 bg-neutral-800 px-1.5 py-0.5 text-xs text-neutral-200`；`備援源`＝`whitespace-nowrap rounded bg-amber-900/40 px-1.5 py-0.5 text-xs text-amber-300`；`資料較舊`＝`whitespace-nowrap rounded bg-neutral-800 px-1.5 py-0.5 text-xs text-neutral-400`。
- 截圖：`HOMEMIX-home-<w>-holdings-list-fullwidth.png`、`HOMEREAL-home-<w>-holdings-list-fullwidth.png`、`…-home-viewport.png`（只是首屏，無 chip）。
- 對照預期（事實比對）：資料不足 color＝rgb(229, 229, 229)：符合；border＝neutral-500（`oklch(0.556 0 none)`＝rgb(115, 115, 115)）：符合。

### 6. console 404

- 載入階段（`loadPhase`）：個股頁 2330（P 批 12 run＋BL 2 run）、個股頁 00675L（槓桿頁，BL 2 run）、首頁（H 批 4 run＋BL 2 run）、設定頁（S 批 8 run＋BL 2 run）：**console error 皆為 0**、`pageerror` 0、`requestfailed` 0、`non2xx`（載入階段）0、`externalRequests` 0、dev overlay 0。
- `GET /api/directory/resolve/<sym>`：個股頁每次載入 1 筆、首頁每次載入 4 筆，**全部 HTTP 200**，body 逐字形如 `{"found":false,"symbol":"2330","directory_synced":false,"as_of":"2026-10-06T15:12:13.084104+00:00"}`（`found:false`；這是 tmp 環境目錄未同步，`directory_synced:false`）。設定頁不呼叫該端點。另以 `curl` 對 `ZZZZ9` 驗證：`200`、`{"found":false,"symbol":"ZZZZ9","directory_synced":false,...}`。
- 唯一的 console error 是 W-R4 操作階段故意造成的 422（見項目 2），不屬載入階段。
- 對照預期（事實比對）：載入期間 console error 數為 0：符合；resolve 查無回 200 found:false：符合。

### 7. D-11 基線（`BL` 批，無任何改寫）

| 頁面 | 寬 | 載入後 `document.documentElement.scrollWidth`／`window.innerWidth` | `body.scrollWidth` | 展開所有 `<details>` 後 docScrollWidth（展開數） | `docOverflow`／`bodyOverflow` |
|---|---|---|---|---|---|
| 首頁 `/` | 375 | 375／375 | 375 | 375（3） | false／false |
| 首頁 `/` | 390 | 390／390 | 390 | 390（3） | false／false |
| 個股頁 `/position/2330?market=TW` | 375 | 375／375 | 375 | 375（6） | false／false |
| 個股頁 | 390 | 390／390 | 390 | 390（6） | false／false |
| 設定頁 `/settings` | 375 | 375／375 | 375 | 375（0） | false／false |
| 設定頁 | 390 | 390／390 | 390 | 390（0） | false／false |
| 槓桿頁 `/position/00675L?market=TW` | 375 | 375／375 | 375 | 375（8） | false／false |
| 槓桿頁 | 390 | 390／390 | 390 | 390（8） | false／false |

- `rect.right > innerWidth` 的元素：首頁、個股頁、槓桿頁為 0 個；設定頁有（`offenders`）：資料來源表（`table.min-w-[480px]`，right 518）與警示規則表（`table.min-w-[620px]`，right 658）及其內部 th／td，皆位於 `overflow-x-auto` 容器內，頁面 scrollWidth 仍等於 viewport。
- 其他 run（S／P／H）每個 run 結尾也都量 docScrollWidth，皆等於 innerWidth（375 或 390）。
- 對照預期（事實比對）：375 下四頁 `document.scrollWidth` ≤ viewport：符合（皆等於 375）。

## 未通過項

依派工單所列數值條件，**本輪沒有量到與條件不一致的項目**。以下是供 qa-e2e 判斷的事實註記（不是缺陷判定），重現步驟都在上文：

1. 項目 1：狀態欄「啟用中／已停用」在 375／390 的 `scrollLeft=0` 不在初始水平可視範圍（需把表容器捲到底）。重現：開 `/settings`，viewport 375 或 390，找警示規則表，看 `statusRect.left`（377.8～425.72）對容器 right（338／353）。
2. 項目 1：整份清單在頁面下方（NBETAV 的 notice 文件座標 top 4786px），第一屏看不到。
3. 項目 2：送出 422 後，錯誤框 bottom 806.5 超出對話框可視底緣 780，需在對話框內捲動才完整可見（375／390 相同）。重現：`/settings` 點 id 4 規則「編輯」、比較值改 `2`、點「儲存變更」。
4. 項目 1（NALL）：notice 在寬條件欄擠壓下折 3 行、`供）` 單獨成行（仍完整不被裁）。

## 自我揭露

- 代跑者只量測與搬運，不下判斷。「對照預期」是數值比對，不取代 qa-e2e 的 Verdict。
- 目視過的截圖：`NBETAV-settings-375-alert-list-viewport-initial.png`、`NALL-settings-390-alert-list-viewport-initial.png`、`NBETAV-settings-375-wr4-dialog-after-submit-viewport.png`、`NBETAV-settings-375-wr4-dialog-after-submit-scrolled-bottom.png`、`NBETAV-settings-390-w1-viewport-default-field.png`、`GHIGH100-2330-375-gauge-card-0-fullwidth.png`、`GLOW0-2330-390-gauge-card-0-fullwidth.png`、`BUNAV-2330-{375,390}-badge-row-tech-title.png`、`BBACKUP-2330-375-badge-row-tech-title.png`、`HOMEMIX-home-375-holdings-list-fullwidth.png`。其餘截圖未逐張目視，由量測值支撐。
- 截圖只留在 scratchpad，未複製到任何其他位置；驗收結束後可刪。
- amber-400／neutral-200／neutral-500 的色值核對來自建置後 CSS 變數 grep，不是第三方查表。

## coordinator 判定（2026-10-06；qa-e2e 工具在本環境不可用，依 e2e-fallback 由 coordinator 依量測事實判定，CEO 可推翻）

- **風控 W-3 版位核可條件（required）**：達成。「不會觸發（欄位不提供）」於 375／390 三個資料集皆在第一欄「代號（市場）」下方、初始水平可視範圔內完整可見、無裁切（scrollWidth＝clientWidth、overflow visible、無 ellipsis）、可換行（2～3 行）、與「狀態」欄同列並存；computed color 為 amber-400；附截圖與 rect。
- **W-R4（required）**：達成。真實後端 422 `loc=["body","params"]`，對話框 `[role=alert]` 逐字等於 W-4，規則未被改動，不靜默失敗。
- **W-1**：達成（常駐、三種欄位狀態皆逐字、下拉 19 項無 beta／position.*）。
- **D-10**：達成（標籤在 figure 內；thumb 8px 溢出為 art-lead 已接受）。**D-10 關閉。**
- **O-3 chip**：達成（「資料不足」rgb(229,229,229)＋neutral-500 框線，對比 12.01；「快取資料」rgb(161,161,161) 無框線，可區分）。**O-3 關閉。**
- **D-6 console 404**：達成（30 個載入 run console error 0，resolve 回 200 found:false）。**D-6 關閉。**
- **D-11 基線**：達成（四頁 375／390 document.scrollWidth＝viewport）。

### 事實註記處置
- a（狀態欄不在初始水平可視範圍）：不影響 W-3 核可條件（風控條件針對 W-3 本身）；狀態欄在 `overflow-x-auto` 容器內可捲動，與 L-16 既有結論一致。列 **D-12（suggested）**：清單於窄幅時把「狀態」欄前移或改為第一欄副標，交 art-lead 評估。
- b（清單在頁面下方需垂直捲動）：設定頁結構既有，不屬本輪範圍；不處置。
- c（W-R4 錯誤框在對話框內 bottom 806.5 > 可視底 780，被切半）：**W-R8（required，ADR-0021 落地收尾）**——送出失敗後錯誤框須進入可視範圍（例如 `scrollIntoView` 或把錯誤框置於送出按鈕上方／對話框頂部）。交 frontend-engineer，不涉新字面；修後 e2e 補拍此路徑。
- d（NALL 折 3 行、「供）」單獨成行）：完整未裁，可接受；若 art-lead 認為斷行不佳可調 `max-w`，列 suggested。

### 流程偏差（coordinator 承擔）
- 偏差 4：e2e 進行中，coordinator 派 dev-lead 修改 backend `engine.py` 等三檔（工作樹，未 commit；HEAD 未變）。該變更屬警示評估路徑，不在本輪顯示層受測範圔；後端於 15:10 載入模組、檔案 15:13 才改，實際受測後端程式為 HEAD 版本。**嚴格而言本輪受測內容為「HEAD 3e249fd＋他人未提交變更」**，記錄為流程偏差；後續輪次 e2e 期間 coordinator 不再派任何會改動 `apps/` 工作樹的任務。
- 偏差 1～3（埠 3020 CORS、漏 expandAll、首頁重跑）為 qa-automation 自行隔離並重跑，作廢批次原樣保留於 scratchpad，不採用。

### 列管更新
| 編號 | 內容 | 狀態 |
|---|---|---|
| D-10 | RangeGauge 標籤 clamp | **關閉** |
| O-3 | 「資料不足」chip 加重 | **關閉** |
| D-6 | resolve 404 → 200 found:false | **關閉** |
| W-3 版位 | 風控 e2e 條件 | **達成** |
| W-R4 | 對話框顯示 W-4 | **達成**；衍生 W-R8 |
| W-R8（新） | 422 後錯誤框需進入對話框可視範圍 | required → frontend-engineer |
| D-12（新） | 窄幅清單「狀態」欄不在初始水平可視範圍 | suggested → art-lead |

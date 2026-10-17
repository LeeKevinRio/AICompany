# B-16 空帳總曝險一致 e2e-fallback 代跑證據包（qa-automation，只交事實）

- 審查者：qa-automation；worktree 分支 fix/stock-desk-empty-book-gross-exposure，HEAD 59e0e6a
- 日期：2026-10-17
- 轉存：coordinator，逐字轉存 subagent 最終回報

---

# B-16 空帳總曝險一致 e2e-fallback 代跑證據包（qa-automation 代跑，只交事實，不下 Verdict）

## 本次結論（事實摘要）
- 三個情境，375 與 1280 兩種寬度都已實機跑完。每個情境都量了卡片（個股頁）與總覽（首頁風險儀表）的第 3 條。
- 情境 1（空帳＋淨值 5,000,000，合成）：卡片與總覽第 3 條都是「無法評估」，detail 逐字等於 `EMPTY_BOOK_DETAIL` 套入 `{name}`=「總曝險上限」。卡片文字內沒有「通過」二字，整個「風險上限檢查」區也沒有。
- 情境 2（空帳＋無淨值）：卡片與總覽第 3 條都保留淨值缺漏原因「缺少組合總市值，無法計算總曝險。可在設定頁輸入「帳戶總淨值（新台幣）」後啟用這條上限。」，沒有被空帳句蓋掉。
- 情境 3（持 1 檔＋淨值）：第 3 條為「通過」，觀察值 20.63%，上限 100.00%。1,031.50×1000÷5,000,000 = 20.63%，與畫面一致。
- 全程無外連：6 輪（3 情境×2 寬度）`externalReq` 皆為 `[]`。console 皆為空。
- 判讀與 Verdict 由 qa-e2e 負責。

## 1. Provenance
- Worktree：`/home/user/AICompany/.claude/worktrees/agent-a883d70b5e83d1f98`，分支 `fix/stock-desk-empty-book-gross-exposure`，HEAD `59e0e6a96fde078093e4693b09f2aea94167e004`。開工前後 `git status --porcelain` 皆為空，`--ignored` 前後一致，HEAD 前後相同。
- 儀器（取自三個情境的 runner stdout，完全一致）：
  - `playwrightModule` = `/opt/node22/lib/node_modules/playwright/index.js`
  - `chromiumExecutable` = `/opt/pw-browsers/chromium-1194/chrome-linux/chrome`
  - `trustedPrefix` = `/opt/`
  - runner 開頭有 fail-closed 前綴斷言，未觸發 ABORT，每次 exit 0。請 qa-e2e 以環境既定前綴 `/opt/` 自行核對，不以封包自述為準。
- 後端：`app.__file__` = `/home/user/AICompany/.claude/worktrees/agent-a883d70b5e83d1f98/apps/stock-desk/backend/app/__init__.py`（檔案 `appfile-s1.txt`、`appfile-s2.txt`、`appfile-s3.txt`）。用主工作樹 `.venv`，`PYTHONPATH` 指向該 worktree 的 backend。
- 前端：
  - `node_modules` 由主工作樹 `cp -a`（確認為實體目錄，非 symlink）。
  - `rm -rf .next` 後 `npx --no-install next build`，exit 0（`next-build.log`）。log 內有「Skipping validation of types」一行，原文照列。
  - 再用 `next start --port 3000`。
- 環境：
  - 所有行程的大小寫 proxy 皆為 `http://127.0.0.1:9`，`NO_PROXY=127.0.0.1,localhost`（大小寫兩組）。
  - 沒有 `--proxy-server`。
  - `ALPHA_VANTAGE_API_KEY`、`FINMIND_API_TOKEN` 已 unset，沒有讀 `.env`。
  - 後端 `BASE_URL=http://localhost:3000`。
  - 每個情境用新的 scratch 目錄 `run-<label>/`，`STOCK_DESK_DB_PATH`、`STOCK_DESK_MARKET_DB_PATH`、`STOCK_DESK_RESEARCH_DB_PATH` 三個都指向它。
  - 瀏覽器用 `ctx.route` 中止所有非 loopback 請求並記錄 `externalReq`。
- 開跑前的 port 檢查：本機沒有 `ss` 指令，我第一次的檢查句型因此是無效的（`ss` 不存在，fallback 印出了「free」）。實際改以 `ps -eo pid,comm` 確認當時沒有 next、uvicorn 行程。啟動後 `ps` 只看到我自己的一組 next 與一個 uvicorn。
- 資料（全為合成示範資料）：
  - 價格：2330，64 根日線，最後一根 2026-10-14，收盤 1031.5，由 `seed_cache.py` 寫入 scratch 價格快取。
  - 淨值：經真實 `PUT /api/settings` 寫入 5,000,000（新台幣，合成值）。
  - 持倉：經真實 `POST /api/positions` 建立，2330、TW、1000 股、均價 900，只在情境 3。
- 我實際操作的順序：
  - 情境 1：先 PUT 淨值，不建持倉（`GET /api/positions` 回 `{"items":[]...}`）。
  - 情境 2：不 PUT 淨值（`GET /api/settings` 的 `net_worth.freshness`=`absent`），不建持倉。
  - 情境 3：先 POST 持倉，再 PUT 淨值。
- 證據根目錄（scratchpad）：`/tmp/claude-0/-home-user-AICompany/3f76d891-50d3-55e1-b39d-925b8a90241a/scratchpad/e2e-b16/`
  - 腳本：`runner.js`、`start_backend.sh`、`start_frontend.sh`、`stop_backend.sh`、`run_scenario.sh`、`post_positions.sh`、`seed_cache.py`、`direct_api.sh`、`summarize.py`
  - 未經改寫的 runner stdout：`runner-s1.json`、`runner-s2.json`、`runner-s3.json`

## 2. 我用的頁面與 selector

| 項目 | URL | selector |
|---|---|---|
| 卡片（個股頁） | `http://localhost:3000/position/2330` | 標題 `h2`/`h3` 文字為「風險上限檢查」所在的 `section`（頁面元件 `LimitsCheckList.tsx`、`AdviceCardView.tsx`）；第 3 條是該區 `ul > li`，文字以「第 3 條」開頭 |
| 總覽（首頁） | `http://localhost:3000/` | 標題 `h2`=「風險儀表」的父層（`RiskGauge.tsx`）；主視圖列是 `ul > li.border-t`；詳細列在 `details` 內的 `li` |

- 卡片在「建議卡」`<details>`（summary 文字 `▸\n建議卡\n命中 3 條`，情境 3 為「命中 4 條」）內，預設收合。runner 以真實點擊 summary 展開後才取值。展開前「風險上限檢查」標題的 `getClientRects().length > 0` 為 true（`cardClosedVisible`）。
- 總覽主視圖的第 3 條不需展開即可見；詳細判定句要點「詳細：各項判定依據、假設與資料來源」summary 才看得到，runner 也是真實點擊。

## 3. 情境 1：空帳＋有效淨值 5,000,000

375 與 1280 文字、class、顏色完全相同，只有座標不同。

### 卡片第 3 條逐字 innerText
```
第 3 條・總曝險上限
無法評估

帳本內沒有任何持倉，總曝險上限沒有可評估的部位，本次不計算，回報 not_evaluable。

觀察值：—　上限：100.00%
```
- `EMPTY_BOOK_DETAIL`（`limits.py` 約 L419）原文為：`帳本內沒有任何持倉，{name}沒有可評估的部位，本次不計算，回報 not_evaluable。`，`{name}`=「總曝險上限」，畫面字面與之相符。
- 「通過」二字：第 3 條 innerText 為 false，整個「風險上限檢查」區 innerText 也為 false。

### class 與 computed color
- `li` 的 class：`rounded-md border border-neutral-800 p-3 text-sm`。
- chip（「無法評估」）class：`inline-flex items-center justify-center rounded-md border px-2 py-0.5 text-xs font-semibold border-dashed border-amber-700 bg-amber-950/40 text-amber-300`
  - 文字色：`lab(86.4156 6.13147 78.3961)`，canvas 轉換為 `rgba(255, 210, 48, 1.000)`
  - 背景：`oklab(0.279003 0.0538332 0.0550504 / 0.4)`，轉換為 `rgba(70, 25, 0, 0.400)`
  - 邊框：`lab(47.2709 42.9082 69.2966)`，轉換為 `rgba(187, 77, 0, 1.000)`，邊框為虛線（dashed）
- detail `<p>`：class `mt-1 text-neutral-400`，文字色 `lab(66.128 -0.0000298023 0.0000119209)`，轉換為 `rgba(161, 161, 161, 1.000)`。
- 說明：瀏覽器回傳的 `getComputedStyle` 值是 `lab()`/`oklab()` 字串，我另用 canvas 轉成 rgba 當參考，兩種都保留在 JSON（`colorRgb` 等欄位）。rgba 是 canvas 轉換值，不是 computed 原字串。

### 同一頁整區「風險上限檢查」第 1、2、4、5 條（事實，與本次改動無直接關聯）
- 第 1 條：缺少總資產或部位市值，無法計算單一標的佔比。
- 第 2 條：此標的目前沒有持倉，單一產業佔比上限沒有可分類的部位，本次不計算，回報 not_evaluable。
- 第 4 條：缺少總資產，無法換算單筆可承受虧損。
- 第 5 條：此標的尚未輸入 Kelly 所需的勝率與盈虧比（可透過手動輸入或回測帶入取得），本條上限目前無法評估。
- 以上五條 chip 都是「無法評估」。

### 總覽（首頁）第 3 條
- 主視圖列逐字 innerText：
```
第 3 條・總曝險上限
無法評估
—／100.00%
```
- chip class 與 computed color 與卡片 chip 完全相同（同一組 class：`...border-dashed border-amber-700 bg-amber-950/40 text-amber-300`）。
- 展開詳細後，第 3 條詳細項逐字：
```
第 3 條・總曝險上限

帳本內沒有任何持倉，總曝險上限沒有可評估的部位，本次不計算，回報 not_evaluable。
```
- 總覽其餘四條詳細也都是 `帳本內沒有任何持倉，{name}沒有可評估的部位，本次不計算，回報 not_evaluable。`。
- 與卡片的一致性（事實）：卡片與總覽第 3 條的狀態都是「無法評估」，detail 字面逐字相同，chip class 相同，觀察值與上限顯示都是 `—`／`100.00%`。
- 假設與限制清單（總覽詳細內，共 2 條）的第二條逐字：`總曝險以「已估值部位市值合計」為分子、使用者自報的帳戶總淨值新台幣 5,000,000 元為分母，輸入時間為 2026-10-18 02:45（台北時間）；此淨值由使用者自行輸入，系統未加以查核。`。這句仍提到「已估值部位市值合計」為分子，但同一頁的第 3 條卻是空帳不計算。我只記錄事實，不判斷。
- API（未經改寫，直接 GET，檔案見第 6 節）：
  - `/api/advice/2330?market=TW`：`{"index": 3, "id": "gross_exposure", "name": "總曝險上限", "status": "not_evaluable", "detail": "帳本內沒有任何持倉，總曝險上限沒有可評估的部位，本次不計算，回報 not_evaluable。", "observed": null, "threshold": 1.0}`
  - `/api/portfolio/limits`：`{"index": 3, "limit_id": "gross_exposure", "name": "總曝險上限", "status": "not_evaluable", "observed": null, "threshold": 1.0, "detail": "帳本內沒有任何持倉，總曝險上限沒有可評估的部位，本次不計算，回報 not_evaluable。", "worst_symbol": null, "evaluated_count": 0, "excluded": []}`
  - advice 的 `held`=false。
- 版面：375 與 1280 的 `documentElement.scrollWidth` 都等於視窗寬（375／1280），無橫向溢位。375 的卡片中，第 3 條 chip 與標題同列（其餘四條 chip 換到標題下一行）。我從截圖看到這個現象，沒有量測它的原因。

## 4. 情境 2：空帳＋無淨值

375 與 1280 相同。
- 卡片第 3 條逐字 innerText：
```
第 3 條・總曝險上限
無法評估

缺少組合總市值，無法計算總曝險。可在設定頁輸入「帳戶總淨值（新台幣）」後啟用這條上限。

觀察值：—　上限：100.00%
```
- 總覽第 3 條：
  - 主視圖列：`第 3 條・總曝險上限\n無法評估\n—／100.00%`
  - 詳細：`第 3 條・總曝險上限\n\n缺少組合總市值，無法計算總曝險。可在設定頁輸入「帳戶總淨值（新台幣）」後啟用這條上限。`
- chip class 與顏色與情境 1 完全相同（`border-dashed border-amber-700 bg-amber-950/40 text-amber-300`）。
- 句內沒有出現「帳本內沒有任何持倉」字樣（卡片第 3 條、總覽第 3 條皆無）。
- 同一頁第 1 條 detail 在卡片仍是「缺少總資產或部位市值，無法計算單一標的佔比。」，總覽詳細第 1 條則是 `帳本內沒有任何持倉，單一標的佔比上限沒有可評估的部位，本次不計算，回報 not_evaluable。`。這是事實紀錄，不是本次改動範圍。
- 總覽假設與限制（2 條）的第二條逐字：`缺少現金與融資餘額資料，總曝險無法計算；該上限會回報 not_evaluable，不以總資產代入而讓比率恆為 100%。`
- API：
  - advice：`{"index": 3, "id": "gross_exposure", ..., "status": "not_evaluable", "detail": "缺少組合總市值，無法計算總曝險。可在設定頁輸入「帳戶總淨值（新台幣）」後啟用這條上限。", "observed": null, "threshold": 1.0}`
  - `/api/portfolio/limits`：同一 detail 與狀態。

## 5. 情境 3（對照）：持有 2330 一檔（1000 股，均價 900）＋淨值 5,000,000

375 與 1280 相同。
- 卡片第 3 條逐字 innerText：
```
第 3 條・總曝險上限
通過

組合總曝險 20.63%（已估值部位市值合計 ÷ 自報帳戶總淨值），低於上限 100.00%。分子（已估值部位市值合計）由系統計算，分母（帳戶總淨值）由使用者自報，兩者來源不同。本比率假設持倉清單完整；未登錄的部位不計入分子，會讓曝險看起來偏低。自報淨值的輸入時間為 2026-10-18 02:49（台北時間）。

觀察值：20.63%　上限：100.00%
```
- chip 文字「通過」，class：`inline-flex items-center justify-center rounded-md border px-2 py-0.5 text-xs font-semibold border-neutral-600 bg-transparent text-neutral-300`。文字色 `lab(84.92 0 -0.0000119209)`（轉換 `rgba(212, 212, 212, 1.000)`），邊框 `rgba(82, 82, 82, 1.000)`。通過的 chip 在此產品是中性灰，不是綠色。
- 總覽主視圖列：`第 3 條・總曝險上限\n通過\n20.63%／100.00%`。詳細句與卡片完全相同。
- API：`status` 為 `passed`，`observed` 為 0.2063，`threshold` 為 1.0（advice 與 `/api/portfolio/limits` 兩者）。
- 驗算：1000 股×收盤 1031.5＝1,031,500；÷5,000,000＝20.63%，與 API、卡片、總覽三處相同。
- 同頁其他條（供對照）：第 1 條「已違反」（2330 佔總資產 100.00%，已達或超過上限 15.00%）、第 2 條「無法評估」（未填產業別）、第 4 條「通過」（0.39%）、第 5 條「無法評估」。
- network：卡片頁 `failed` 欄有一筆 `http://localhost:3000/position/2330?market=TW&_rsc=... net::ERR_ABORTED`（375 與 1280 各一，rsc 值不同）。時間點在 runner 從個股頁 `goto` 首頁時，是 Next 預取請求被導覽中止，我沒有進一步查證成因。console 為空。

## 6. API 回應本體與截圖路徑（皆在 scratchpad）

API（`.../e2e-b16/api/`）：
- 直接 GET 的未經改寫原文（含 `http=` 狀態行，皆為 200）：`s1-direct-advice.txt`、`s1-direct-portfolio-limits.txt`、`s1-direct-portfolio-summary.txt`、`s1-direct-settings.txt`、`s1-direct-positions.txt`，`s2-direct-*.txt`、`s3-direct-*.txt` 同名。
- 瀏覽器實際收到的回應本體（JSON，key 為完整 URL，涵蓋 `/api/advice`、`/api/portfolio/limits`、`/api/settings`、`/api/positions`、`/api/portfolio/summary` 等）：`s1-375-bodies.json`、`s1-1280-bodies.json`、`s2-375-bodies.json`、`s2-1280-bodies.json`、`s3-375-bodies.json`、`s3-1280-bodies.json`。
- 建立資料的請求回應：`s1-put-settings.txt`、`s3-put-settings.txt`、`s3-post-position.txt`、`s1-positions-direct.json`。

截圖（`.../e2e-b16/shots/`，檔名 `<label>-<寬度>-<種類>.png`）：
- `card.png`：「風險上限檢查」區元素截圖（卡片展開後）。
- `card-page-before-click.png`：點 summary 前的整頁。
- `card-page.png`：展開後的整頁。
- `overview-closed.png`：首頁風險儀表區（詳細收合）。
- `overview-open.png`：詳細展開。
- `home-page.png`：首頁整頁。
- 三個情境（`s1-`、`s2-`、`s3-`）×兩個寬度（375、1280）×上述六種，共 36 張。
- 我實際看過 `s1-375-card.png` 與 `s1-1280-overview-closed.png`：前者五條都是橘色虛線「無法評估」chip；後者五條 chip 也都是「無法評估」，第 3 條的觀察值欄顯示 `—／100.00%`。

## 7. 前後狀態
- worktree 收工後：已刪除複製的 `node_modules`、`.next`、`next-env.d.ts`。`git status --porcelain` 為空（與開工前 diff 無差異），`--ignored` 前後一致，HEAD 仍是 `59e0e6a`。
- 已停掉我啟動的 uvicorn 與 next（含 next-server），3000 與 8000 皆已釋放（`curl` 無回應），沒有殘留 node、next、uvicorn、chrome 行程。coordinator 的 pytest 行程我沒有碰（收尾時 `ps` 已看不到它，是自行結束）。
- `apps/stock-desk/backend/data/*.db`（只 `stat`，前後各一次，`db-stat-before.txt` 與 `db-stat-after.txt` 無差異）：
  - `stock-desk-market.db`：98304 bytes，2026-10-04 15:09:46.826306790
  - `stock-desk.db`：159744 bytes，2026-10-04 14:15:41.470506705
- 主工作樹 `git status --porcelain` 有一個 `work/stock-desk-新定位-PRD-2026-10-16.md` 為 modified，不是我改的（開工時是另一個 `work/research/...草案.md`），推測是 coordinator 或其他 agent 的檔案，我沒有碰。
- 沒有 commit，沒有修改受測程式碼。

## 8. 自我揭露與限制
1. **第一次 s1 跑出的證據作廢**：我的 runner 第一版沒有展開「建議卡」`<details>`，卡片第 3 條 innerText 為空（元素不可見）。我補上「真實點擊 summary」後重跑 s1，之後所有情境用同一版。第一次的殘檔移到 `.../e2e-b16/old-s1-attempt1/`，不在本包證據清單內。
2. **顏色轉換**：`colorRgb`/`backgroundRgb`/`borderRgb` 欄位是我用 canvas 把 `lab()`/`oklab()` 轉成 rgba 的參考值。原始 computed 字串在同一個 JSON 欄位旁邊。
3. **合成資料局限**：價格單調遞增、淨值 5,000,000 是人工給定；沒有測「淨值過期」「持有但無法估值」「多檔」「無法評估的非空帳」等組合，也沒有測 2330 以外標的。
4. **本次沒有量字級、對比度**：只記錄 class、computed color 與座標，沒有跟視覺規範比對。
5. **後端 log**：`backend-s1.log`、`backend-s2.log`、`backend-s3.log` 中有一行 `settings: quota configuration unreadable: ALPHA_VANTAGE_DAILY_LIMIT is not set; ...`，因為 `ALPHA_VANTAGE_DAILY_LIMIT` 未設，與本次改動無關。
6. **首頁輸入時間**：畫面中的「2026-10-18 02:4x（台北時間）」是 UTC+8，對應我跑的 2026-10-17 18:4x UTC。
7. 本包沒有任何 Verdict 或 `BLOCKING_ISSUES`。

## 下一步（qa-e2e 判讀所需檔案）
先做儀器來源查核（以環境既定前綴 `/opt/` 比對 `provenance`），再判讀：
- `runner-s1.json`、`runner-s2.json`、`runner-s3.json`（每個含 `widths.375`、`widths.1280` 的 `snaps.card`、`snaps.overviewClosed`、`snaps.overviewOpen`、`consoleAll`、`failed`、`externalReq`、`provenance`）。
- `api/s{1,2,3}-direct-advice.txt`、`api/s{1,2,3}-direct-portfolio-limits.txt`、`api/s{1,2,3}-direct-settings.txt`。
- `shots/s{1,2,3}-{375,1280}-card.png`、`shots/s{1,2,3}-{375,1280}-overview-closed.png`、`shots/s{1,2,3}-{375,1280}-overview-open.png`。
- 對照用原始碼（只讀）：`apps/stock-desk/backend/app/advice/limits.py` 的 `EMPTY_BOOK_DETAIL`（約 L419）。
- 審查文件：`work/reviews/2026-10-17-B16-空帳總曝險一致審查-qa-reviewer.md`、`work/reviews/2026-10-17-B16-空帳總曝險一致-dev-lead回報.md`。
- 所有檔案前綴：`/tmp/claude-0/-home-user-AICompany/3f76d891-50d3-55e1-b39d-925b8a90241a/scratchpad/e2e-b16/`。

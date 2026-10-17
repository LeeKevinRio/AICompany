> 轉存：coordinator，2026-10-17，子 agent 回報逐字轉存。

# B0 持有停損錨點 e2e-fallback 代跑證據包（qa-automation 代跑，只交事實，不下 Verdict）

## 本次結論
- 四個情境，375 與 1280 兩種寬度都已實機跑完。情境 4 的「載入中」與「失敗」兩種狀況都已重現。
- 全程沒有外連：所有請求只對 loopback，runner 記錄的 `externalReq` 在每一輪都是 `[]`。
- 畫面資料全部是**合成示範資料**：2330，64 根日線，最後一根 2026-10-14，收盤 1031.5。
- 判讀與 Verdict 由 qa-e2e 負責。
- 摘要事實放在最前面，原始逐字內容在後面各節。

## 1. Provenance
- 開工前確認：worktree `/home/user/AICompany/.claude/worktrees/agent-a90e4192ba546bc4d`，分支 `fix/stock-desk-b0-hold-stop-anchor`，HEAD `b5ff74a`。`git status --porcelain` 為空，`--ignored` 也為空。
- 儀器（取自每一輪 runner stdout 的 `provenance`，五個情境全部一致）：
  - `playwrightModule` = `/opt/node22/lib/node_modules/playwright/index.js`
  - `chromiumExecutable` = `/opt/pw-browsers/chromium-1194/chrome-linux/chrome`
  - `trustedPrefix` = `/opt/`
  - runner 開頭有 fail-closed 前綴斷言，沒有觸發 ABORT，每次 exit 0。
  - 照 SKILL 判準一，請 qa-e2e 以環境既定前綴 `/opt/` 另行核對，不以封包自述為準。
- 後端：`app.__file__` = `/home/user/AICompany/.claude/worktrees/agent-a90e4192ba546bc4d/apps/stock-desk/backend/app/__init__.py`。用主工作樹的 `.venv`，`PYTHONPATH` 指向該 worktree 的 backend。檔案：`appfile-<label>.txt`。
- 前端：
  - `node_modules` 由主工作樹 `cp -a` 複製。
  - `rm -rf .next` 後執行 `npx --no-install next build`，exit 0（`next-build.log`）。
  - 再用 `next start --port 3000`。
- 環境：
  - 所有行程的大小寫 proxy 都是 `http://127.0.0.1:9`，`NO_PROXY=127.0.0.1,localhost`（大小寫兩組）。
  - 沒有使用 `--proxy-server`。
  - `ALPHA_VANTAGE_API_KEY`、`FINMIND_API_TOKEN` 已 unset。
  - 沒有讀 `.env`。
  - 後端 `BASE_URL=http://localhost:3000`。
  - 每個情境用新的 scratch SQLite，`STOCK_DESK_DB_PATH`、`STOCK_DESK_MARKET_DB_PATH`、`STOCK_DESK_RESEARCH_DB_PATH` 三個都指向該情境的 `run-<label>/`。
  - 瀏覽器用 `ctx.route` 中止所有非 loopback 請求。
  - 開跑前 3000、8000 皆空閒，也沒有相關行程。
- 資料：
  - 合成 bars 由 `seed_cache.py` 寫入 scratch 價格快取。
  - 持倉經真實的 `POST /api/positions` 建立：2330，TW，1000 股，均價 900（情境 1、4）或 500（情境 2）。情境 3 不建持倉。
  - 情境 4「載入中」與「失敗」由 runner 的 `ctx.route` 注入（見第 5 節），後端與受測程式碼都沒有被動過。
- 使用的 scratchpad（證據根目錄）：`/tmp/claude-0/-home-user-AICompany/3f76d891-50d3-55e1-b39d-925b8a90241a/scratchpad/e2e-b0/`
  - 腳本：`runner.js`、`start_backend.sh`、`start_frontend.sh`、`seed_cache.py`、`run_scenario.sh`、`post_positions.sh`、`stop_backend.sh`、`compact.py`、`verify.py`、`summarize.py`
  - 未經改寫的 runner stdout：`runner-s1.json`、`runner-s2.json`、`runner-s3.json`、`runner-s4delay.json`、`runner-s4fail.json`
  - API 回應本體：`api/<label>-<width>-bodies.json`
  - 截圖：`shots/`

## 2. 情境 1：持有，均價 900（`/position/2330`）

375 與 1280 的文字、數值完全相同，只有座標不同。

### 決策卡（`section[aria-label="決策摘要"]`）逐字 innerText
```
資料截至 10-14 / 快取資料 / 價格單位：新台幣 / 續抱參考 / 依規則
最新收盤 1,031.50
停損參考 1,027.50　距最新收盤 -0.4%
停利參考 1,039.50　距最新收盤 +0.8%
股數參考 未提供股數
基準價（最新收盤）
停損參考與停利參考以最新收盤 1,031.50（2026-10-14）為基準計算；相對成本的損益另列於下。
相對成本損益 +14.6%
頁尾「本頁揭露與計算依據」涵蓋本區資料來源、揭露事項與計算方式說明。
```
- LM-17：`基準價（最新收盤）`
- LM-16：`停損參考與停利參考以最新收盤 1,031.50（2026-10-14）為基準計算；相對成本的損益另列於下。`
- LM-19：`相對成本損益 +14.6%`

### KeyLevelsPanel（展開「查看計算依據」後）
- 「停損參考」小節內，逐字依序是：
  - `停損參考與停利參考以最新收盤 1,031.50（2026-10-14）為基準計算；相對成本的損益另列於下。`
  - `相對成本損益 +14.6%`
  - `大字為 2×ATR(14) 與 −8% 兩者中較緊（虧損較小）者。`
- 主視圖兩個大字格：停損參考 `1,027.50`，停利參考 `1,039.50`。
- 價位階梯列由高到低：
  - `+20% 固定停利` 1,237.80（+20.0%）
  - `2R（賺賠比 2:1）` 1,039.50（+0.8%）
  - `基準價（最新收盤）` 1,031.50（距離欄為 `—`）
  - `2×ATR(14)` 1,027.50（-0.4%）
  - `MA20` 1,026.75
  - `MA60` 1,016.75
  - `近 60 日低點` 1,001.00
  - `−8% 固定停損` 948.98（-8.0%）
- 階梯裡沒有「最新收盤」或「收盤」列。
- `基準價（最新收盤）` 在整頁 DOM 出現 2 次（決策卡一次、階梯一次）。
- 頁尾「計算依據」中的基準價條目（開啟 `<details>` 後；這一行就是 LM-18 取代 `:251-252` 後的結果，並含 `:253` 未持有列）：
  `基準價：基準價=最新收盤（持有與未持有相同；未持有時為試算）未持有→基準價=最新收盤(試算)；此數字不是任何進場暗示。`

### 驗算
由 `api/s1-*-bodies.json` 裡的 bars 回應獨立計算（`verify.py`）：

| 項目 | 計算 | 結果 | 畫面 |
|---|---|---|---|
| 收盤 c | 最後一根 | 1031.5 | 1,031.50 |
| TR（最後 14 根） | 每根都是 2.0 | ATR(14) = 2.0 | |
| c−2·ATR | 1031.5 − 4 | 1027.5 | |
| 0.92c | | 948.98 | |
| 停損 max(c−2·ATR, 0.92c) | | 1027.5 | 1,027.50（決策卡、面板一致） |
| 2R = c+2(c−stop) | 1031.5 + 2×4 | 1039.5 | 1,039.50（兩處一致） |
| 1.2c | | 1237.8 | 階梯 1,237.80 |
| 距離（停損） | | −0.3878% | -0.4% |
| 距離（停利） | | +0.7756% | +0.8% |
| 相對成本損益 (c/900−1)×100 | | 14.611111% | +14.6% |

- 合成資料中 c−2·ATR 大於 0.92c，所以標題停損走 ATR 分支。
- 0.92c 這一支只以階梯的 `−8% 固定停損 948.98` 顯示，沒有被當成標題數字。

### 禁字掃描
DOM 全文字（排除 script、style、noscript）與 `innerText` 各掃一次。

| 字串 | 結果 |
|---|---|
| `基準價（持倉平均成本）` | 0 次 |
| `越過` | 0 次 |
| `最新收盤高於`、`最新收盤低於` | `最新收盤高於` 1 次（見下），`最新收盤低於` 0 次 |
| `高於此參考水位`、`低於此參考水位`、`此參考水位` | 0 次 |
| `本卡以你的持倉平均成本` | 0 次 |
| `持倉平均成本` | 1 次（見下） |

兩個命中都在頁尾的 `KEY_LEVELS_BASIS_CLOSE_DISTANCE` 條目，逐字如下：
> `距最新收盤：停損距離=(停損參考-最新收盤)/最新收盤×100%停利距離=(停利參考-最新收盤)/最新收盤×100%最新收盤高於停利參考、或低於停損參考時，該項距離改為：距離=(最新收盤-該參考)/該參考×100%停損參考與停利參考皆由基準價推得；此處距離之分母依上列條件為最新收盤或該參考本身，不是持倉平均成本，距離亦非持倉損益；距離為算式結果，不代表價格會依此幅度到達任一價位。`

- 這是實作回報偏離事項 6 所述的「死條件」，仍在頁尾：`最新收盤高於停利參考、或低於停損參考時，該項距離改為：距離=(最新收盤-該參考)/該參考×100%`。
- 「持倉平均成本」只出現在其中的否定句「不是持倉平均成本」。
- 這兩個詞只在頁尾 `<details>` 展開後才可見：`visibleCount` 在 details 關閉時為 0，展開後為 1。

### 「另列於下」（量測值）
| 位置 | 寬度 | LM-16 句 | LM-19 列 | 關係 |
|---|---|---|---|---|
| 決策卡 | 375 | top 538、bottom 570（折成 2 行），left 33、寬 309 | top 574、bottom 590，left 33 | 損益列 top − LM-16 bottom = 4px |
| 決策卡 | 1280 | top 304、bottom 320，left 161、寬 958 | top 324、bottom 340，left 161 | 差 4px |
| 面板（詳細內） | 375 | top 2780、bottom 2812，left 33 | top 2816，bottom 2832，left 33 | 差 4px |
| 面板（詳細內） | 1280 | top 1812、bottom 1828，left 161 | top 1832、bottom 1848，left 161 | 差 4px |

- 兩處都是：`pnlIsNextElementSiblingOfBasis=true`、`sameParent=true`、`sameLeft=true`、`pnlBelowBasis=true`。
- 決策卡內 LM-17 標籤 `<p>` 是 LM-16 句 `<p>` 的 `previousElementSibling`。
- 決策卡內沒有 `<details>`。
- 375 的 `documentElement.scrollWidth` = 375（無橫向溢位），1280 = 1280。
- 三行的 class 與前後相鄰行相同：`mt-2 text-xs text-neutral-400`、`mt-1 text-xs text-neutral-400`、`mt-1 text-xs text-neutral-400`。

### console 與 network
- console 為空，`failed` 為空，`externalReq` 為空。
- 全部 `localhost:8000` 回應為 200：`/api/directory/resolve/2330`、`/api/positions`、`/api/bars/2330?market=TW`、`/api/leverage/2330?market=TW`、`/api/signals/2330?market=TW`、`/api/advice/2330?market=TW`。

## 3. 情境 2：持有，均價 500（同一份合成 bars，全新 scratch DB）

- 與情境 1 相比（`verify.py` 的 s1 vs s2，兩種寬度都比）：
  - 決策卡四個數字格完全相同：最新收盤 1,031.50；停損 1,027.50 / -0.4%；停利 1,039.50 / +0.8%；股數 未提供股數。
  - 面板大字格相同。
  - 決策卡 innerText 逐行比對，唯一差異是損益列：`相對成本損益 +14.6%` 變成 `相對成本損益 +106.3%`。
  - 面板詳細展開後的 innerText 也只有這一行不同。
- 驗算：(1031.5/500 − 1)×100 = 106.3%。
- LM-17、LM-16 字面與情境 1 相同。
- 「另列於下」量測：決策卡與面板的間距、left、sibling 關係都與情境 1 相同（兩種寬度），也沒有橫向溢位。
- 禁字掃描：命中項與情境 1 完全相同（頁尾的 `最新收盤高於`、`持倉平均成本` 各 1 次）。
- console、failed、externalReq 皆為空。

## 4. 情境 3：未持有（同一檔，不建持倉）

決策卡逐字 innerText（375 與 1280 相同）：
```
資料截至 10-14 / 快取資料 / 未持有 / 價格單位：新台幣
未持有此標的，以最新收盤 1,031.50 試算；此數字不是任何進場暗示。
進場評估
本次未支持進場
最新收盤 1,031.50
停損參考 1,027.50　距最新收盤 -0.4%
停利參考 1,039.50　距最新收盤 +0.8%
股數參考 未提供股數
基準價（最新收盤，試算）
頁尾「本頁揭露與計算依據」涵蓋本區資料來源、揭露事項與計算方式說明。
```
- 標籤是 `基準價（最新收盤，試算）`，不是 LM-17。LM-17 出現 0 次，試算標籤出現 2 次（決策卡一次、階梯一次）。
- 決策卡與面板都**沒有** LM-16 句、**沒有** LM-19 列、**沒有** LM-53。
- 面板內展開後的基準句是 `未持有此標的，以最新收盤 1,031.50 試算；此數字不是任何進場暗示。`
- 公式列：頁尾 `基準價：基準價=最新收盤（持有與未持有相同；未持有時為試算）未持有→基準價=最新收盤(試算)；此數字不是任何進場暗示。`
- `:253` 那一列字面（`未持有→基準價=最新收盤(試算)；此數字不是任何進場暗示。`）原樣保留在該條目的第三行。
- 數值與情境 1 相同：停損 1,027.50，停利 1,039.50，1.2c = 1,237.80，已用同一份驗算確認。
- 禁字掃描命中項與情境 1 相同（只有頁尾那兩個）。
- 無橫向溢位，console、failed、externalReq 皆為空。
- 另有一點事實：情境 3 的 advice 為候選模式，主字是「進場評估」「本次未支持進場」。

## 5. 情境 4：成本未取得或持倉載入中（兩種都重現）

方法：用 `ctx.route` 攔截瀏覽器對 `GET /api/positions` 的請求。
- (a) delay：延遲 7000ms 後才 `route.continue()`，之後回正常資料（均價 900）。
- (b) fail：直接 `route.fulfill` HTTP 500，body `{"detail":"b0-e2e injected positions failure"}`。
這是**注入的故障**，不是後端真的失敗。

### (a) 載入中（`runner-s4delay.json`）
「during」快照是在 bars、advice 已回應、positions 仍被延遲時取的（375：t=4913ms，positions 在 7378ms 才回；1280：t=1245ms，positions 在 7368ms 才回）。

決策卡 during 逐字 innerText，兩種寬度相同：
```
資料截至 10-14 / 快取資料 / 價格單位：新台幣 / 續抱參考 / 依規則
最新收盤 1,031.50
停損參考 —
停利參考 —
股數參考 未提供股數
相對成本損益：未取得持倉成本，無法計算
頁尾「本頁揭露與計算依據」涵蓋本區資料來源、揭露事項與計算方式說明。
```
- LM-53 出現在決策卡中，位置是四格數字之下、頁尾指引句之上。
  - 375：top 514 / bottom 530，left 33。
  - 1280：top 280 / bottom 296，left 161。
- 這個狀態下決策卡**沒有** LM-17 標籤、**沒有** LM-16 句、**沒有**距離小字。
- 同一時刻的 KeyLevelsPanel（展開後）：
  - 主視圖大字仍顯示數值：停損 1,027.50，停利 1,039.50。
  - 詳細內是 LM-16 句，緊接著 LM-53 列：
    - `停損參考與停利參考以最新收盤 1,031.50（2026-10-14）為基準計算；相對成本的損益另列於下。`
    - `相對成本損益：未取得持倉成本，無法計算`
  - 階梯基準列標籤是 `基準價（最新收盤）`。
  - 面板內 LM-16 與 LM-53 兩行的間距同樣是 4px，同 parent、同 left。
- 因此同一個畫面上決策卡顯示「—」、面板顯示數值，且面板同時有 LM-16 與 LM-53。這是實作回報偏離事項 5 的實機呈現。
- 延遲結束後（settled）：決策卡回到情境 1 的完整內容（LM-17、LM-16、`相對成本損益 +14.6%`，停損 1,027.50、停利 1,039.50）。LM-53 出現 0 次。
- LM-53 是**短暫**顯示：375 約維持到 positions 回應的 7378ms，1280 約到 7368ms。實際持續時間取決於 positions 請求耗時。

### (b) 持倉查詢失敗（`runner-s4fail.json`）
- positions 被 500 兩次（前端自動重試了一次，間隔約 1 秒）。
- 之後穩定停在以下狀態，沒有恢復。決策卡逐字：
```
資料截至 10-14 / 快取資料 / 價格單位：新台幣 / 續抱參考 / 依規則
最新收盤 1,031.50
停損參考 —
停利參考 —
股數參考 未提供股數
相對成本損益：未取得持倉成本，無法計算
頁尾「本頁揭露與計算依據」涵蓋本區資料來源、揭露事項與計算方式說明。
```
- LM-53 位置同上：375 在 top 514，1280 在 top 280。
- 面板詳細內同樣是 LM-16 句後接 LM-53，大字格 1,027.50 / 1,039.50。
- console 有兩條 `error: Failed to load resource: the server responded with a status of 500 (Internal Server Error)`，對應 runner 注入的兩次 500。

## 6. 截圖路徑（只留在 scratchpad，未複製到他處）
`/tmp/claude-0/-home-user-AICompany/3f76d891-50d3-55e1-b39d-925b8a90241a/scratchpad/e2e-b0/shots/` 下，檔名為 `<label>-<寬度>-<card|closed|open|panel-open|during>.png`：
- `s1-375-card.png`、`s1-1280-card.png`、`s1-375-panel-open.png`、`s1-1280-panel-open.png`、`s1-*-closed.png`、`s1-*-open.png`
- `s2-*`、`s3-*` 同上
- `s4delay-375-during.png`、`s4delay-1280-during.png`，以及 `s4delay-*-card/closed/open/panel-open.png`
- `s4fail-375-card.png`、`s4fail-1280-card.png`，以及 `s4fail-*-closed/open/panel-open.png`

我實際看過的幾張畫面事實：
- `s1-375-card.png`：「基準價（最新收盤）」小字、LM-16 句（折成兩行）、「相對成本損益 +14.6%」三行由上而下排列，皆為小灰字。
- `s1-1280-card.png`：同樣三行排列，各自單行。
- `s1-375-panel-open.png`：階梯的「基準價（最新收盤）」列在 375 寬度標籤折成三行。展開的「查看計算依據」內，LM-16 句後接「相對成本損益 +14.6%」。
- `s4fail-375-card.png`：停損參考、停利參考為「—」，下面只有一行「相對成本損益：未取得持倉成本，無法計算」。

## 7. 前後狀態
- worktree `git status --porcelain`：開工前為空，收工後為空，兩者 diff 無差異；`--ignored` 開工前為空，收工後為空。HEAD 仍是 `b5ff74a`。
- 已停掉前後端，已刪除複製的 `node_modules`、`.next`、`next-env.d.ts`。
- 3000 與 8000 都回到空閒，沒有殘留 node、next、uvicorn、chrome、python 行程。
- `apps/stock-desk/backend/data/*.db`（只做 `stat`，前後各一次）：
  - `stock-desk-market.db`：98304 bytes，2026-10-04 15:09:46.826306790，前後相同。
  - `stock-desk.db`：159744 bytes，2026-10-04 14:15:41.470506705，前後相同。
  - 我 `diff` 兩份記錄時只差路徑字串（前一次用相對路徑，後一次用絕對路徑），大小與時間戳完全一致。
- 主工作樹 `git status --porcelain` 為空。
- 沒有 commit，沒有修改受測程式。

## 8. 自我揭露與限制
1. **合成資料局限**：
   - 價格呈單調遞增，每根 TR 都是 2.0，ATR 為 2.0。
   - c−2·ATR（1027.5）永遠大於 0.92c（948.98），所以「0.92c 為標題停損」的分支沒有被實機覆蓋，只在階梯列看到 948.98。
   - 這份資料也無法檢驗「均價 > 收盤」（虧損）情形，所有持有案例的損益都是正值。
2. **展開「詳細」的方式**：runner 用 `document.querySelectorAll('details').forEach(d => d.open = true)` 一次展開頁面上所有 `<details>`（含頁尾），不是逐一點擊 summary。我沒有點擊驗證 summary 的互動，也沒有量測展開動畫。
3. **情境 4 的時間**：
   - 「載入中」是以 7 秒人為延遲製造的，不代表真實使用者會遇到的延遲長度。
   - 375 那輪 bars 回應到 4148ms 才抵達（比 1280 慢），所以 375 的 during 快照時間點是 4913ms，1280 是 1245ms。
   - 兩者都是 positions 尚未回應的狀態。
4. **情境 4(b) 是注入的 500**，後端本身從未失敗。重試次數與間隔是前端 react-query 的行為。
5. **dev 資料來源標示**：bars 回應 `data.status` 為 `cached_stale`、`source` 為 `twse`（合成資料寫入快取後的標示），決策卡因此顯示「快取資料」徽章。這不是受測改動造成的。
6. **runner 小 bug**：第一次執行時，我自己的 runner 把 `tag` 變數漏傳進 `page.evaluate`，exit 1、沒有產出。
   - 我修好 runner 後重跑 s1，之後的 s1–s4 都是修正後的輸出。
   - 第一次失敗沒有產生可用證據，也沒有改動受測程式。
   - 那次失敗後有殘留 chrome 行程，我用 kill 清掉，最後再確認為無。
7. **本次不是 B0 的視覺規範比對**。我沒有量測字級、顏色對比等 computed style，只量了位置座標與 class 字串。
8. **未涵蓋**：
   - `close-unknown` 且 advice 不是 held 的組合（決策卡此時不印 LM-53）。
   - 幣別不符、持倉成本不可用的情形。
   - 多批次（lots）持倉。
   - 2330 以外的標的與美股。
9. 本包沒有任何 Verdict 或 `BLOCKING_ISSUES`。

## 下一步
- 請 qa-e2e 先做儀器來源查核（以環境既定前綴 `/opt/` 比對 `provenance`）。
- 查核通過後，以上述逐字內容、驗算、量測與截圖判讀。
- 判讀時特別對照的事實：
  - 頁尾仍留存的「最新收盤高於停利參考、或低於停損參考時…」死條件句與「不是持倉平均成本」否定句。
  - 載入中狀態下，決策卡顯示「—」與面板同時顯示數值、並同時出現 LM-16 與 LM-53。
  - 375 寬度下階梯基準列標籤折成多行。

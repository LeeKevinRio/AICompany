# dev-up-env 與 totals-redo 分支審查

- 審查者：qa-reviewer
- 日期：2026-10-26
- 轉存：coordinator，逐字轉存 subagent 最終回報

---

## 總覽
- 兩條分支我都沒找到 critical 或 high 問題，兩條都是 BLOCKING_ISSUES=false，可交 coordinator。
- Codex 第二意見：`codex --version` 回 `command not found`（exit 127）。依 CEO #58 走單家審查，這不是跨廠商審查。
- 兩條都沒有重跑測試。交件報告裡的 CI 數字（8086 passed、8128 passed、vitest 2310 passed）我無法佐證，請 coordinator 獨立重跑。
- 兩條都含 UI 或使用者可見行為，審查後仍須 qa-e2e 判斷是否重驗。

---

## 分支一：origin/fix/stock-desk-dev-up-env（devops-sre，5 commit）

BLOCKING_ISSUES=false

### Summary
dev-up 讀 `.env` 的做法正確。祕密只以布林值輸出，沒有任何洩漏路徑。bat 全檔維持 CRLF。README 改正的事實大致經得起查證，不確定處多半已自標〔未查證〕。bat 在 Windows 的行為全是推論，這點作者已揭露，我列為 medium。

### 逐項回答你的重點

1. **祕密載入狀態行不輸出值（含部分值）：成立。**
   - `app/env_status.py:34-52`：`_present()` 只回 `bool(env.get(name,"").strip())`，值立刻丟棄。輸出只剩 `已設定／未設定` 兩個標籤。
   - `log_env_status` 只把 `describe_env_status()` 的結果交給 logger，沒有任何值經過格式化、切片或傳給 logger。
   - `main.py` 的 lifespan 在 `configure_logging()` 之後呼叫，`scheduler.py main()` 同樣。兩邊 logger 命名空間（`app`、`scheduler`）都在 `logging_setup.INFO_NAMESPACES`（`logging_setup.py:42`），所以 INFO 看得到。
   - `tests/test_env_status.py` 走真實 lifespan 與 `scheduler.main()`，讀真實 stderr。它斷言不含值，也不含值的前 6 碼、後 6 碼與 `zz` 特徵片段（L74-80）。
   - bat 與 sh 只 echo `.env` 的路徑，不 echo 內容。
   - fixture 全是假值，沒有真祕密進檔。`.gitignore` 的 `.env`、`.env.*`、`!.env.example` 規則存在（`.gitignore:2-4`）。

2. **bat 維持 CRLF：成立。**
   - 我用 Grep 在 worktree 的 `dev-up.bat` 找「行尾不是 CR」的行，0 筆，所以每行都是 CRLF。
   - 與作者報告一致（285 行皆有 CR，`i/lf w/crlf attr/text eol=crlf`）。
   - `git diff --stat` 顯示 bat 只動 20 行（+19/-1），沒有整檔行尾重寫。
   - `dev-up.sh` 維持 100755（diff 無 mode 變更）。

3. **`.env` 不存在時的行為：正確。**
   - bat（`dev-up.bat:77-88`）：`if exist` 才設 `UV_ENV_FILE`；否則 `set "UV_ENV_FILE="` 清掉外部殘留值，印一行 `[ENV]` 提示，照常啟動。
   - sh（`dev-up.sh:66-76`）：`-f` 判斷；否則 `unset UV_ENV_FILE` 並印提示。`set -u` 下 `unset` 一個未設變數不會出錯。
   - 這個設計對應作者實測的事實：uv 對不存在的檔案會報錯、`UV_ENV_FILE` 設空字串等同沒設。
   - bat 的 2b 區塊在 `if (...)` 括號內的 echo 文字沒有括號或特殊字元；路徑用 `!ENV_FILE!` 延遲展開。我逐行讀過，沒找到語法問題，但這只是讀碼。

4. **README 改正的事實正確性。**
   - 三顆 DB 路徑與常數：我逐一核對，全部成立。
     - `data/cache.py:28` `./data/stock-desk.db`
     - `data/market_panel.py:95` `./data/stock-desk-market.db`，環境變數 `STOCK_DESK_MARKET_DB_PATH`（L96）
     - `research/sector_biased/store.py:45-46` `STOCK_DESK_RESEARCH_DB_PATH`、`./data/stock-desk-research.db`
   - 其餘 store（positions、settings、alerts、directory、dividends、kelly、playbook、sectors、quota）的註解都寫共用 `STOCK_DESK_DB_PATH`，與 README「使用者資料在主 DB」一致。
   - 研究 DB「API 程序不開這顆」：`store.py:3-4` 原文成立。
   - compose：`env_file required: false`（compose.yaml 11-13、34-36、58-60）、`restart: unless-stopped`、volume 掛 `/app/data`、`STOCK_DESK_DB_PATH=/app/data/stock-desk.db`，都與 README 敘述相符。
   - `Dockerfile` 的 `WORKDIR /app` 成立，所以市場／研究 DB 預設相對路徑落在同一 volume 的推論可成立。README 已標〔未在實際容器內查證〕。
   - 原生路徑備份：先停三個程序，成套複製 `*.db`、`*.db-wal`、`*.db-shm`。還原：先清舊的 `-wal`、`-shm` 再放回備份。這符合 SQLite WAL 行為，方向正確，作者也標了「尚未在 Windows 演練」。
   - Docker 段落改成「先 `docker compose stop` 再 tar」，並承認直接 tar 執行中的 WAL DB 不保證一致。舊 README 寫「不需要停機（SQLite WAL 支援線上備份）」搭配 tar，這個改正是對的。
   - 未能查證，維持作者的標記：uv `--env-file` 的最低版本、容器內有無 `sqlite3` CLI、Docker 與原生互搬流程、市場 DB 能否由資料源重建（以 ADR-0012 為準）、研究 DB 是否在一般運作下產生。我另外無法查證 uv 0.11.32 的實測結果，這只能採信作者。

5. **local-run skill 只改產品分支這份：成立。**
   - 本分支基底是 `product/stock-desk`，diff 只動 `.claude/skills/local-run/SKILL.md` 一份，沒有其他 skill 或 `docs/`。我沒有檢查 main 上有沒有同名檔案，因為我的 Bash 限定範圍只允許 diff 這條基底比較。
   - 手動指令補了 `--env-file ../.env`，相對於 `backend/` 工作目錄指到 `apps/stock-desk/.env`，路徑正確。

### 問題清單

#### `/home/user/AICompany/.claude/worktrees/agent-aa078b54360377fd2/apps/stock-desk/dev-up.bat`
- [Edge case][medium] 2b 區塊（L74-88）與 `start "..." cmd /k` 兩條（L133、L149）整段未在 Windows 實機驗證。
  - 核心假設是 `start` 開的子視窗會繼承父視窗的 `UV_ENV_FILE`。這在 Windows 一般成立，但沒有實測。
  - `.env` 以 Windows 記事本存成 BOM 或 CRLF 時，uv 的解析也沒測（作者只測 LF）。
  - 緩解已在：程式內狀態行會顯示「未設定」，所以失效不會靜默。
  - 建議：合併後請 CEO 在 Windows 雙擊一次，確認兩個視窗的狀態行都顯示「已設定」。這是合併前或合併後的驗收項，不擋件。
- [Edge case][low] bat 對 `UV_ENV_FILE` 是覆寫（L79、L84）。CEO 若在 Windows 系統環境已有自己的 `UV_ENV_FILE`，會被蓋掉。README 寫「系統環境變數優先」只對 `.env` 內的變數成立，對 `UV_ENV_FILE` 本身不成立。機率低，文字上可加一句。

#### `/home/user/AICompany/.claude/worktrees/agent-aa078b54360377fd2/apps/stock-desk/README.md`
- [可維護性][low] 資料表把市場 DB 寫成「只增不改」。`market_panel.py:29` 的 docstring 說 `market_backfill_progress` 是 checkpoint，不屬 append-only。建議改成「主要是只增不改」。
- [可維護性][low] 「關掉三個視窗就停止」的備份前置步驟，沒驗證 Windows 關視窗後 `uvicorn --reload` 的 worker 子程序是否一併結束。若殘留會持有 `-wal`。建議標〔未查證〕，或補一句「確認工作管理員沒有殘留 python」。
- [可維護性][low] 未改動的 `compose.yaml:70-71` 註解仍寫 volume 是 "the single SQLite file"，與 README 新說法衝突。不在本 diff 內，可後續順手改。

#### `/home/user/AICompany/.claude/worktrees/agent-aa078b54360377fd2/apps/stock-desk/backend/tests/test_env_status.py`
- [可維護性][low] `_assert_no_value_or_fragment` 用 `value[:6]` 當洩漏探針。Discord 假值的前 6 碼是 `https:`，若日後 stderr 出現任何 https 字樣就會誤紅。現在不會，只是脆弱。可改成避開通用前綴。

### 其他觀察（不構成問題）
- 每次 `TestClient(app)` 啟動都會多印一行 INFO，無副作用。
- `uvicorn --reload` 每次重載會再印一行，預期內。

### 唯讀權限判準常數
未觸及。
- 改了什麼：沒有。`git diff product/stock-desk...origin/fix/stock-desk-dev-up-env --name-only` 共 8 個檔，不含 `scripts/validate_agents.py`。
- 為何改：不適用。
- 有無對應 ADR：不需要。
- 因 Bash 不准接管線，第二道 grep 以「完整閱讀所有非文件 diff、逐行閱讀 README／SKILL diff，再用 Grep 在 worktree 的 `apps/` 與 `.claude/skills/local-run` 搜 `READONLY_AGENTS|READONLY_ALLOWED_BASH`」代替，0 筆。沒有 shadow 定義，也沒有常數值被改動。

### 合併建議
- 可合併進 `product/stock-desk`（走 fast-forward 或 merge 都行）。
- 合併後請 CEO 在 Windows 實機雙擊一次 `dev-up.bat`：分別在有 `.env` 與無 `.env` 兩種狀態各看一次。確認 backend 與 scheduler 兩個視窗的「環境設定載入狀態」行。這是 medium 項的實機驗收，不阻擋合併。
- 本分支沒有需要風控審查的建議類文案（只有操作說明與狀態標籤）。

### Verdict
PASS（單家審查，Codex 缺席）
BLOCKING_ISSUES=false

---

## 分支二：origin/fix/stock-desk-totals-redo（dev-lead，4 commit）

BLOCKING_ISSUES=false

### Summary
A-1、T1-12、B-16 三項都忠於原驗收條件與原審查指出的修正。B4 清單一行未動，沒有新增使用者字面，我沒找到任何把 null 當 0 的路徑。與 `fix/stock-desk-trust-defects` 在 `SummaryCards.tsx` 有「語意級」衝突，合併時會造成 TypeScript 型別錯誤，這是主要風險（medium）。

### 逐項回答你的重點

1. **忠於原驗收條件與原審查修正：成立。**
   - **A-1**：`SummaryCards.tsx:62-73` 的 `noData = totals.status === "no_data"`、四個值各自 `noData ? null : totals.xxx`，與原審查描述的 L67-71 邏輯相同。依 status 遮罩，不依數值。原審查兩個 low 項都處理了：`toContain("0")` 改成逐格 `toBe("NT$0")`，型別改 `string | null`。
   - **T1-12**：
     - B1：`Totals` 五欄改 `Decimal | None`（`summary.py:70-74`），`model_validator` 雙向強制（L77-90）：`no_data` 任一欄有值 raise，非 `no_data` 任一欄為 None raise。新增 `valued_market_value_twd`（L160-175）。
     - B2/B3：`book.py:575-585` 的 `_book_equity` 與 `settings.py:352` 都改用 helper。
     - T1～T5、F1～F4、C1/C2 都有對應檔案。
   - **B-16**：
     - `book_holding_count` 兩個 builder 都填 `len(groups)`（`book.py:1206`、`book.py:1413`）。分組鍵與 `book_limits._group_positions` 相同，都是 `(symbol.strip().upper(), market)`，我核對過兩邊程式。
     - `_check_gross_exposure` 的空帳檢查放在淨值缺漏、淨值過期之後（`limits.py:1289-1297`），與原審查確認的優先序一致。
     - `EMPTY_BOOK_DETAIL` 搬到 `limits.py:426`，與 `book_limits` 的 re-export 同一物件。字串與舊版逐字相同（我讀兩邊 diff 對照）。
     - `_book_level_check` 的覆寫與 `EMPTY_BOOK_UNCOMPUTABLE_IDS` 已移除。全 repo 已無殘留引用；`book_is_empty` 只剩 `_aggregate` 使用。
     - `_fully_valued` docstring 更新；T4 (b) 在 c17f92d 翻轉（diff 已核對）。
     - 原審查 M1（直接斷言 action／`quantity_range`）與 L1（`project_position` docstring ＋試算測試）都已納入。

2. **T1-12 的 B4「清單內檔案一行都不准改」：遵守。**
   - 我跑 `git diff 062099a 3834199 -- advice/limits.py advice/book_limits.py alerts api/advice.py api/portfolio.py playbook`，輸出為空。
   - T1-12 的 commit `--stat` 也沒有這些檔。
   - B-16 的 commit 才碰 `limits.py`、`book_limits.py`，那是 B-16 本身的檔案範圍，並非違反 B4。
   - `1927ecf` 我逐行讀過：只有 `limits.py` 的一則註解（把中文換成英文兩行），無邏輯變動，與交件報告一致。

3. **有無新增使用者字面：沒有。**
   - 新增的中文只有 `limits.py` 裡 `EMPTY_BOOK_DETAIL` 與「風控核可文案…」那行註解，兩者都是原樣搬移，且該句已由風控 2026-10-16 核可逐字沿用（含 `{name}` 只取 `LIMIT_NAMES`）。
   - 其餘新增字串：validator 的 `ValueError` 訊息為英文，且不是 API 使用者面向文案。前端「—」來自既有 `formatMoney(null)`；沒有新 JSX 字面。
   - 空帳橫幅「所有部位皆無法估值，總計無法計算。」本分支沒動。

4. **null 有沒有任何路徑被當成 0：沒找到。**
   - 後端 `app/` 全域 grep：除了 `portfolio/summary.py` 自己，沒有其他模組讀 `totals` 金額欄位（`advice/engine.py` 的 `totals` 是無關的字典；其他匹配都是註解）。
   - 內部分母改用 `valued_market_value_twd`。它的 0 是「空集合的和」，不是替缺值補數；完整性仍由 `valued/total` 計數與 `book_fully_valued` 另判。
   - helper 與 `build_summary` 逐位等價：兩者都只累加 `status == "ok"` 的列、同順序、同來源欄位（`build_summary` 對 `ok` 列斷言 `market_value_twd is not None`）。
   - 前端：`types.ts` 的五欄改 `string | null`；`SummaryCards` 是唯一讀 totals 金額的元件（Grep 確認 `page.tsx:57` 只往下傳）。`formatMoney(null)`→「—」、`pnlColorClass(null)`→中性灰，與原審查讀碼結果一致。新測試斷言畫面不含 `null` 或 `NaN`。
   - 殘留邊界：`book_holding_count=None`（手組 context）時 cap 3 回到舊行為，這是設計，docstring 有寫。

### 問題清單

#### 與 `fix/stock-desk-trust-defects` 的重疊點（你要求標出）
我用 `git diff product/stock-desk...origin/fix/stock-desk-trust-defects` 看過，重疊如下。

- `/home/user/AICompany/.claude/worktrees/agent-abc4c8865961c20c9/apps/stock-desk/frontend/app/components/SummaryCards.tsx`
  - [Bug（合併後）][medium] 兩邊都在同一區塊動手，會產生文字衝突，而且「機械式解衝突」會留下型別錯誤。
    - totals-redo（L62-73）：定義 `noData` 與 `marketValue`、`unrealizedPnl`、`assetContribution`、`fxContribution` 四個遮罩變數。四處 `formatMoney`／`pnlColorClass` 改吃這些變數。
    - trust-defects：在同位置定義 `const amount = (value: string): string | null => (totals.status === "no_data" ? null : value)`，四處改成 `amount(totals.xxx)`。
    - 合併後 `totals.xxx` 變成 `string | null`，餵給 `amount(value: string)` 會讓 `tsc` 報錯。如果只取 trust-defects 這邊的 hunk，CI 會紅；兩邊的 `const basis = ...` 下一行是衝突點。
    - 建議的解法：保留 totals-redo 的四個遮罩變數，丟掉 trust-defects 的 `amount` helper。再保留 trust-defects 的 `StatusBanner` 新增 `empty` 參數（它沒有與 totals-redo 在這個函式重疊）。
  - [Bug（合併後）][low] trust-defects 的 `StatusBanner` 變成 `{status, empty}`，`SummaryCards` 呼叫處改傳 `empty={totals.status === "no_data" && positions.length === 0}`。這與 totals-redo 沒有重疊，但應在合併後確認 `summaryCardsNoDataTotals.test.ts` 的 `render()` 用 `positions: []`：
    - 「no_data」案例（L47-71）此時會同時命中 trust-defects 的空帳橫幅「尚無持倉」。
    - 我檢查了這個測試：它斷言 `expect(html).toContain(SUMMARY_BANNER_NO_DATA)`（L54、L157）。
    - 合併後該斷言會失敗，因為 `positions: []` 且 `no_data` 時橫幅改成 `EMPTY_TITLE`。所以這兩個斷言是第二個衝突點。
    - 建議：合併後這兩個測試的 `render()` 改傳一筆 `UNVALUED` 持倉（trust-defects 的 `summaryBanner.test.ts` 已這樣處理），或把斷言改成空帳橫幅。
- `/home/user/AICompany/.claude/worktrees/agent-abc4c8865961c20c9/apps/stock-desk/frontend/app/lib/__tests__/summaryBanner.test.ts`
  - [可維護性][medium] 兩邊都改了同一個檔案。
    - totals-redo 改 `totals()`：no_data 回 null 金額的分支。
    - trust-defects 改 `render()` 與 `UNVALUED` 常數，並在 `no_data` 時傳 `[UNVALUED]`。
    - 兩個 hunk 相鄰，git 可能自動合併，也可能出現衝突；兩邊互補，合併後保留兩邊即可。
- `/home/user/AICompany/.claude/worktrees/agent-abc4c8865961c20c9/apps/stock-desk/frontend/app/lib/__tests__/summaryCardsNoDataTotals.test.ts`（totals-redo 新檔）與 trust-defects 的 `summaryCardsEmptyBook.test.ts`（新檔）
  - [可維護性][low] 兩個檔案測試範圍重疊。後者的註解（`summaryCardsEmptyBook.test.ts` 開頭）寫「totals are Decimal 0」，在 totals-redo 合併後已經過時，因為空帳的 API 現在回 null。
  - 建議合併後在 `summaryCardsEmptyBook.test.ts` 補一個「null 金額 ＋ `positions: []`」案例，並更新註解。
- `types.ts` 與後端檔案：trust-defects 沒有動，無重疊。
- 字面風險：trust-defects 的空帳橫幅重用既有的 `EMPTY_TITLE`（「尚無持倉」），沒有新字面。這解決了 totals-redo 交件報告所列的 PM Q-A1，兩邊不互斥。

#### `/home/user/AICompany/.claude/worktrees/agent-abc4c8865961c20c9/apps/stock-desk/backend/tests/test_advice_book.py:576-590`
- [可維護性][low] 零分母測試改成「兩列數量都是 0」，這是 dev-lead 標〔推論〕的寫法。
  - 原審查（2026-10-16）寫的是「第 2 列 `quantity="0"`」，但若第 1 列數量非 0，逐檔加總不會是 0。dev-lead 的推論合理，原審查的敘述不精確。
  - 這個測試只有負向斷言（`not any("未填產業別" ...)`）。
  - 他報告說拿掉 guard 會出 `ZeroDivisionError`，我沒重跑，採信但建議 coordinator 抽驗。
- 同檔 L7 左右的 `7.69%`：50,000 ÷ 650,000，計算正確。與原審查接受的偏離相同。

#### `/home/user/AICompany/.claude/worktrees/agent-abc4c8865961c20c9/apps/stock-desk/backend/app/advice/limits.py:422-428`
- [可維護性][low] `#: 風控核可文案,修改須重新送審…` 是中文註解，違反「程式碼與註解一律英文」。它是從 `book_limits.py` 原樣搬來的既有行，不是本次新增，所以不擋；後續可改成英文。

### 其他觀察
- B-16 測試數 18（原版 21）、T1-12 測試數 33（原版 30）：dev-lead 說差在 parametrize 寫法。我讀了 B-16 測試檔 L1-140，涵蓋範圍符合他列出的覆蓋項目，但我沒有逐一對照原 21 個案例，也沒有完整讀 T1-12 的 406 行新測試。
- UI 變更仍須 qa-e2e 判斷是否重驗（A-1 首頁四格、B-16 空帳加淨值時卡片與總覽第 3 條）。dev-lead 也明說原 e2e 證據包已不存在。

### 唯讀權限判準常數
未觸及。
- 改了什麼：沒有。`git diff product/stock-desk...origin/fix/stock-desk-totals-redo --name-only` 共 17 個檔（`apps/stock-desk/` 下的 backend、frontend 檔），不含 `scripts/validate_agents.py`，也沒有 `.claude/` 或 `docs/`。
- 為何改：不適用。
- 有無對應 ADR：不需要。
- 因不能接管線，第二道檢查以「讀完所有 app 原始碼 diff、既有測試 diff，再用 Grep 搜 worktree 的 `apps/`」代替，0 筆。沒有 shadow 定義，也沒有常數值被改動。

### 合併建議
1. 本分支可先合併進 `product/stock-desk`（它的基底是 f73c466）。
2. 之後 `fix/stock-desk-trust-defects` 合併時，解衝突的順序要注意：
   - `SummaryCards.tsx`：以 totals-redo 的遮罩變數為準，刪掉 trust-defects 的 `amount(value: string)` helper，保留它的 `empty` 橫幅。
   - `summaryCardsNoDataTotals.test.ts` 的 `positions: []` 與 `SUMMARY_BANNER_NO_DATA` 斷言：改傳 `UNVALUED` 持倉或改斷言。
   - `summaryBanner.test.ts`：保留兩邊。
   - 合併後必須重跑 `npm run typecheck` 與 `npx vitest run`，不能只看文字衝突是否消失。
3. 交 qa-e2e 判斷 375／1280 寬度重驗範圍（no_data、空帳、partial、complete 首頁四格；空帳加淨值時卡片與總覽第 3 條）。
4. 非擋件待辦（來自原紀錄，與本審查無關）：風控 2c 提醒端 `outcome.reason` 的空帳成因句、L3 前端 `PortfolioContextOut` 補 `book_holding_count`、PM Q-A1 空帳橫幅（trust-defects 已另處理）。

### Verdict
PASS（單家審查，Codex 缺席；UI 變更須 qa-e2e）
BLOCKING_ISSUES=false

---

## 自我揭露：我執行過的每一條 Bash 指令
全部都是 `git diff` 或 `codex --version`，沒有管線、沒有 `cd`、沒有寫入。
1. `codex --version` → exit 127，`command not found`。
2. `git diff product/stock-desk...origin/fix/stock-desk-dev-up-env --stat`
3. `git diff product/stock-desk...origin/fix/stock-desk-totals-redo --stat`
4. `git diff product/stock-desk...origin/fix/stock-desk-dev-up-env -- apps/stock-desk/dev-up.bat apps/stock-desk/dev-up.sh apps/stock-desk/backend/app`
5. `git diff product/stock-desk...origin/fix/stock-desk-dev-up-env --name-only`
6. `git diff product/stock-desk...origin/fix/stock-desk-totals-redo --name-only`
7. `git diff product/stock-desk...origin/fix/stock-desk-dev-up-env -- apps/stock-desk/README.md .claude/skills/local-run/SKILL.md`
8. `git diff product/stock-desk...origin/fix/stock-desk-totals-redo -- apps/stock-desk/backend/app apps/stock-desk/frontend/app/components apps/stock-desk/frontend/app/lib/types.ts`
9. `git diff product/stock-desk...origin/fix/stock-desk-totals-redo -- <既有測試 7 個檔>`（advice_helpers、test_advice_book、test_portfolio_summary、test_unusable_close_f1、test_unusable_fx_f1b、test_x3c_currency_market_mismatch、summaryBanner.test.ts）
10. `git diff 062099a 3834199 --stat`
11. `git diff c17f92d 1927ecf`
12. `git diff 3834199 c17f92d --stat`
13. `git diff 062099a 3834199 -- apps/stock-desk/backend/app/advice/limits.py apps/stock-desk/backend/app/advice/book_limits.py apps/stock-desk/backend/app/alerts apps/stock-desk/backend/app/api/advice.py apps/stock-desk/backend/app/api/portfolio.py apps/stock-desk/backend/app/playbook` → 輸出為空
14. `git diff 062099a 3834199 -- apps/stock-desk/frontend/app/components/SummaryCards.tsx`
15. `git diff 3834199 c17f92d -- apps/stock-desk/backend/tests/test_t1_12_totals_null.py`
16. `git diff product/stock-desk...origin/fix/stock-desk-trust-defects --stat`
17. `git diff product/stock-desk...origin/fix/stock-desk-trust-defects -- <SummaryCards.tsx、summaryBanner.test.ts、summaryCardsEmptyBook.test.ts>`

其他說明：
- 我不讀 `.env`，也沒碰 `*.db`。
- Glob 在 `/home/user/AICompany/work/reviews/` 與整個 worktrees 目錄各有一次逾時，不影響結果；之後改用較窄的 Glob 找到原審查紀錄。
- 交件報告兩份在主目錄 `/home/user/AICompany/work/reviews/` 讀到，不在 worktree 內。
- 我沒有完整讀完 `test_t1_12_totals_null.py`（406 行）與 `test_b16_empty_book_gross_exposure.py` 後半，也沒讀 `README.md` 以外的 docs。

審查對象路徑：
- `/home/user/AICompany/.claude/worktrees/agent-aa078b54360377fd2`（dev-up-env）
- `/home/user/AICompany/.claude/worktrees/agent-abc4c8865961c20c9`（totals-redo）

# 財務資料源 spike 審查（NEEDS_CHANGES，B-1）

- 審查者：qa-reviewer
- 日期：2026-11-01
- 轉存：coordinator，逐字轉存 subagent 最終回報

---

## 本次結論

**FAIL（NEEDS_CHANGES）　BLOCKING_ISSUES=true**

阻擋點只有一個：P-12 的判定邏輯有三處會誤判（B-1，high）。修法很小。腳本還沒交 CEO 跑，現在退回最便宜。

其餘面向都過：
- 安全清單全部通過，沒有發現外洩路徑。
- P-1、P-2、P-9 沒有 blocking 問題，但各有誤判傾向（NB-1～NB-3）。
- 請求間隔符合 SEC 規範，User-Agent 未設定時不發任何 SEC 請求。
- CEO 文件步驟清楚，commit 核對值與分支一致。

修完 B-1 後，`script_sha256_lf` 會變，CEO 文件的核對值和「最後修改腳本的 commit」都要同步更新。

### BLOCKING

**B-1　`fundamentals_spike.py:1923-1968`（`eval_p12`）【Bug／high】**

三個問題疊在一起，會讓 P-12 在 CEO 填了持股時給出錯誤的字面判定。

1. **基準公司被算進「持股」的判定。**
   - `checked = [describe(t) for t in (*SEC_TICKERS, *ev.holdings)]` 把 AAPL、AMZN、INTC 一起算進分子和分母。
   - 輸出會寫「none of N checked companies」，其中 N 包含這三家基準公司，不是 CEO 的持股。
2. **持股沒抓到時仍可判 `NOT_HOLD`。**
   - 條件是 `if ev.holdings and fetched:`，而 `fetched` 只要基準公司有抓到就非空。
   - 持股若是 ETF（companyfacts 404）或不在對照檔，會得到 `NOT_HOLD`。CEO 文件第 247 行把它寫成「您填的持股裡沒有」，這是錯的。
   - `test_run_with_holdings_missing_from_ticker_map_reports_it`（測試檔 3537-3541 行）只驗了 `MISSING` 那行，沒驗 P-12 的判定。
3. **用整份文件的幣別單位判斷，而不是申報幣別。**
   - 判定用的 `foreign_currency_units(rep.unit_tags)` 掃的是整份 companyfacts 所有標籤的單位。
   - 美國跨國公司常有零星的 EUR、JPY、CNY 單位（外幣債券、衍生性商品名目金額），而 ADR 要判的是申報幣別。
   - 我預期 AAPL 這類公司會被誤標為 HOLDS。這點是從我對 SEC 資料的印象推的，沒有實測。
   - 同函式已算好 `whitelist_units`（白名單標籤的單位），卻只拿來印，沒拿去判。
   - 測試只有 TWD 的 `foreign_facts()`，沒有「美國公司帶零星外幣單位」的案例。

建議修法：
- 只用 `ev.holdings` 判定。
- 任何一檔持股沒抓到，就不判 `NOT_HOLD`，改判 `INCONCLUSIVE` 並列出沒抓到的代號。
- 外幣判斷改看白名單標籤的單位，加上 `ifrs-full` 是否出現。
- 補兩個測試：「持股抓取失敗」和「美國公司帶零星外幣單位」。

### 重點 2：P 項門檻評估

**P-1**
- 邏輯正確。
- 以 `(start, end)` 為期間鍵比對，用「同期間出現多個 `fy`」加「同一 `accn` 只有一組 `(fy, fp)`」來判斷 `fy`、`fp` 是不是申報層級，推論成立。
- 真實資料多半會是 `PARTIAL`（`frame` 不是每筆都有），與文件預期一致。

**P-2**
- 130 天內申報的門檻合理。大型加速申報人約 60 天，非加速約 90 天，寬一些沒問題。
- 比較期在申報後約 365 天以上，所以不會被誤算成原始值。
- 但 90% 門檻會誤導，見 NB-1。

**已驗證標籤**
- 「400 天內還在用」合理。
- 「3 個會計年度」的實作有出入，見 NB-2。

**P-9**
- 已排除封面日（dei）和瞬時值，只看全年期間，這個修正是對的。
- 只用 AAPL 一家判斷。AAPL 最近一個年度在 9 月底，月份對得上，所以預期 `HOLDS`。
- 52/53 週制的公司可能跨月，但這次沒有影響。

**P-12**：見 B-1。

## 各部門回報

### qa-reviewer 審查（逐檔，4 檔全看）

**`apps/stock-desk/backend/scripts/fundamentals_spike.py`（2100 行）**

安全項目，結論為過：
- 只有 GET（`Request(..., method="GET")`），沒有 `data=`。
- 不碰 DB，不寫檔。唯一的檔案讀取是 `Path(__file__).read_bytes()`，用來算雜湊。
- 沒有 import `app`，只用標準函式庫。
- 三個祕密只從環境變數讀取。
- 所有輸出都經 `say` → `Redactor`，沒有直接 `print`：
  - 祕密本身，加上 URL 編碼與 `quote_plus` 形式。
  - email。
  - `token=`、`apikey=`、`Bearer`、`Authorization` 等片段。
- 印出的網址用 `shown_url`，FinMind 的 token 和 Alpha Vantage 的 key 不會出現在 `GET` 那行。
- 回應標頭白名單只留 etag、last-modified、content-length、content-encoding、date、cache-control、expires、retry-after、`x-ratelimit*`；cookie 與授權標頭不留，且有測試。
- 請求上限 30：`Budget.take()` 在送出前就會擲 `BudgetExceededError`，各區段都會被擋。
- 最壞請求數的算式我逐項核對過：
  - SEC：ticker 對照檔 1 + 備用 1，三家 companyfacts 3，TSM 1，持股 3，AAPL 申報清單 1 + 條件式重發 1，SPY 申報清單 1 + companyfacts 1，存取規範頁面 1，共 14。
  - 其他來源：TWSE 4、TPEx 3、FinMind 4、Alpha Vantage 1，共 12。
  - 合計 26，與文件一致。
- SEC 間隔：`www.sec.gov` 與 `data.sec.gov` 同一個桶，每次至少 0.25 秒，等於每秒最多 4 次，遠低於 10 req/s。
- `SEC_USER_AGENT` 沒設或不含 `@` 時，整段略過，不發請求。有測試。
- `.env.example` 只新增兩行空值（`SEC_USER_AGENT=`、`SPIKE_US_HOLDINGS=`），範例是 `example@example.invalid` 和 `AAA,BBB`。後端沒有 `BaseSettings`，空鍵不會讓啟動失敗。

NB（均不擋件）：

- **NB-1　`fundamentals_spike.py:1611-1665`（`eval_p2`）【Edge case／medium】**
  - 真實 SEC 資料中，XBRL 開始前的早期年度（例如 AAPL 的 FY2007、FY2008）只會以比較期出現，永遠沒有「原始年報」。每個標籤約 18 個舊年度會有約 2 個被計為「未保留」，比率約 88%，落在 90% 以下，結果多半是 `PARTIAL`。
  - 測試 `test_p2_partial_when_earliest_comparatives_lack_their_original_filing` 證實：只多一個舊比較年度就會翻成 `PARTIAL`。
  - `PARTIAL` 的白話解讀「部分年度只剩比較期」字面為真，但資訊量低，也不代表資料源有缺陷。
  - 建議：排除早於該標籤「最早原始申報年度」的期間再算比率，或把未保留的年度列在證據行，讓 tech-architect 一眼看出都是 XBRL 之前的年度。
- **NB-2　`fundamentals_spike.py:520-523`（`TagSummary.verified`）【Bug／medium】**
  - 實作是 `fps.get("FY", 0) >= 3`，數的是 `fp=="FY"` 的 fact 筆數，不是不同的會計年度數。
  - 一份 10-K 就帶三年比較期，單一申報即可滿足。
  - 文件寫「至少有 3 個會計年度」。這會讓 P-3 偏向過度樂觀，也可能把剛換上的新標籤判成已驗證。
  - 建議改數不同的全年期間（`(start, end)` 且約 12 個月）。
- **NB-3　`fundamentals_spike.py:1579-1588`（`eval_p1`）【可維護性／medium】**
  - 程式對 `accn, filed, form, end, fy, fp, start` 任何一個缺漏都判 `NOT_HOLD`。
  - 文件與 ADR 的 `NOT_HOLD` 只寫「缺 `accn` 或 `filed`」，且 handoff 把它解讀為「結構性問題，ADR 要先修訂才能開工 F1」。
  - 單一 fact 缺 `fy` 就會觸發同樣的警報，可能造成誤判。`detail` 有列出缺的欄位，人工可分辨。
  - 建議把 `accn`、`filed` 缺漏與其他欄位缺漏分成兩級，或把文件第 238 行改成程式的實際行為。
- **NB-4　`fundamentals_spike.py:362`、`:358-361`【Edge case／medium】**
  - `except` 沒接 `http.client.HTTPException`（例如 `IncompleteRead`）。數 MB 的 companyfacts 下載若被截斷，例外會往上冒，整個 SEC 區段被標成 `SEC/unexpected`，後面的 P 項證據全失。
  - 建議在 `except` 補上 `http.client.HTTPException`。
- **NB-5　`fundamentals_spike.py:350-368`【安全／low】**
  - urllib 預設會跟隨最多 10 次轉址。轉址不計入請求上限，也不套用 SEC 的間隔。
  - 轉址時 `Authorization: Bearer <FinMind token>` 會被帶往新位置。目標都是官方網域，風險很低。
  - 可選擇用自訂的 `HTTPRedirectHandler` 關掉轉址。
- **NB-6　`fundamentals_spike.py:827-831`【Edge case／low】**
  - `ticker_variants` 的「去點」寫法（`BRK.B` → `BRKB`）可能對到另一家公司的代號。
  - 對 P-4 的實測樣本影響不大，但持股若是點號類股，有誤對 CIK 的可能。
- **NB-7　`fundamentals_spike.py:1750-1764`（`eval_p5`）【Edge case／low】**
  - `statuses` 全為 `None`（網路全斷）時，「User-Agent 格式被接受」仍會印 `yes`。
  - 結果最終是 `INCONCLUSIVE`，不影響判定，只有證據行誤導。

**`apps/stock-desk/backend/tests/test_fundamentals_spike.py`（1592 行，93 項）**

- 項數核對：90 個 `def test_`，加上 `parametrize` 的 4 個案例（多出 3 項），共 93，與交件一致。
- 優點：
  - 遮蔽測試很扎實。它同時驗證假金鑰確實被拿去發請求，所以只有遮蔽擋住它們。
  - 上限測試把 `REQUEST_CAP` 降為 3，驗證第 4 次一定被擋。
  - 原始碼守則涵蓋：無 `sqlite3`、無 `app` import、只用標準函式庫、無寫檔呼叫、唯一的檔案讀取是讀自己、只有 GET、無 email 與金鑰字面值。
- P-1～P-9 的各判定分支都有測試。
- P-12 缺口見 B-1：沒有「持股抓取失敗」和「美國公司帶零星外幣單位」的案例。
- NB-8【low】：原始碼守則不禁止 `subprocess`、`os.system`、`ctypes`、`socket`、`http.client`。目前腳本沒用，但守則可再加固。

**`apps/stock-desk/.env.example`**：只加兩個空值鍵與假值範例，過。

**`work/research/財務資料源spike-執行指令-2026-11-01.md`（305 行）**

- 步驟清楚：新視窗確認 `UV_ENV_FILE` 為空、設環境變數、`git worktree`、`uv run --frozen`、核對版本、收尾清理。
- 不含真實 email，只有 `Your Name your@email.com`。
- 有明確提醒 CEO 不要把含 email 的那行貼回（第 79 行）。
- 版本核對值：
  - 預期 commit `f125ea2b…` 與分支一致。這個 commit 改了腳本（1102 行），而它之後到分支 HEAD 的差異只有 `.env.example` 與本文件，腳本沒再動過。
  - `script_sha256_lf` 為 `5fd19502…`。我的 Bash 限定只能用 `git diff`，無法重算，所以沒有核對到。CEO 端有自動比對（輸出第三行），可作為把關。
- NB-9【low，文件第 79 行】：寫「這三行的任何一行」，但環境變數其實有四行，建議改成「這幾行」或「以上任何一行」。
- **NB-10【隱私／medium，文件第 48、74–76 行】持股代號的提醒不足。**
  - 文件只說「代號不是祕密，會出現在輸出裡」。
  - 實際上持股代號還會經 CEO 回貼進對話，被整理進 `work/` 文件（會 commit），並以 CIK 形式出現在對 SEC 的請求中。CLAUDE.md §4 也提到 repo 可能設為 public。
  - 這不是建議類文案，不需風控審查，但建議加一句提醒：「持股代號會進入回傳內容與後續文件；不想留痕可不填，P-12 只能是 `INCONCLUSIVE`」。
  - 回答 data-engineer 的問題：不需風控或隱私另行把關，加提醒即可。

### 章程檢查

- 範圍：4 個檔案，均在 `apps/stock-desk/` 與 `work/research/` 內，沒有動 `.claude/`、`CLAUDE.md`、`docs/`。
- 祕密掃描：全 diff 搜尋 email、`sk-`、`AKIA`、`ghp_`、私鑰標頭、32 字元以上英數字串，只命中假值（`example@example.invalid`、`test.person@example.com`、`x@y.com`、`jane.doe+x@mail.example.org`、`your@email.com`）、SEC 標籤名稱和 commit 雜湊，沒有真實祕密。
- `git diff --check` 無輸出。
- trailer：我只被允許用 `git diff`，無法讀 commit message，只能採信 data-engineer 回報（6 個 commit 都帶指定的兩行 trailer）。合併前請另行核對。
- commit 數量：交件列出 6 個（`b1efdb9`、`382861b`、`bdc5dd7`、`f125ea2`、`369335a`、`fbe49d1`），與任務一致。

## 驗證

- 已讀：
  - 完整 diff，4 個檔案逐檔看過。
  - 兩份 data-engineer 交件。
  - ADR-0038 D-9 的 P 項表。
- 未跑：腳本與測試。我的 Bash 範圍只有 `git diff`，所以測試通過與否採信交件說明（pytest 8972 passed、ruff 與 mypy 全綠），未獨立驗證。
- **Codex 第二意見：未取得。** `codex --version` 回 `command not found`（exit 127）。**單家審查，Codex 待環境可用時補跑。**
- Bash 使用紀錄：
  - 用過：`git diff`（各種範圍與 `--stat`、`--name-only`、`--check`）、`codex --version`。
  - 我曾下過一個只看 `.env.example` 的 `git diff <range> -- apps/stock-desk/.env.example`，被權限系統拒絕。之後改跑任務指定的完整 `git diff <range>`，從輸出內容讀到 `.env.example` 的差異。這是任務明確要求審查的檔案，其內容就是假值。沒有讀任何真實的 `.env`，也沒有碰 `data/*.db`。
  - 沒有用到白名單以外的 Bash 指令。

### 唯讀權限判準常數

未觸及。
- 第一道（`--name-only`）：變更檔案為 `.env.example`、腳本、測試、CEO 文件，沒有 `scripts/validate_agents.py`。
- 第二道（找 `READONLY_AGENTS`、`READONLY_ALLOWED_BASH`）：全 diff 搜尋 0 命中。
- 因為 `--name-only` 的輸出本身就能直接比對，兩道我都以 Grep 與目視檢查完成，沒有接 pipe。

## 下一步

1. **退回 data-engineer 修 B-1**（P-12 三處）並補兩個測試。
   - 修完後重新計算 `script_sha256_lf`、更新 CEO 文件的核對值與最後修改腳本的 commit。
   - 順手處理 NB-2、NB-3。NB-1 建議一併處理，因為會直接影響 P-2 結論的可讀性。
2. 若時間緊，NB-4、NB-5、NB-9、NB-10 可只改文件或一行程式，成本低。
3. 修正後送回 qa-reviewer 重審，屆時請 Codex 補跑第二意見。
4. 重審通過後交 CEO 在本機執行，之後由 data-engineer 整理 P 項實測結果交 tech-architect 修訂 ADR-0038。
5. 這是純邏輯與文件類，不涉及 UI，不需要 qa-e2e。

## Verdict
NEEDS_CHANGES
BLOCKING_ISSUES=true

審查範圍的檔案：
- /home/user/AICompany/apps/stock-desk/backend/scripts/fundamentals_spike.py（分支 `origin/feat/stock-desk-fundamentals-spike`）
- /home/user/AICompany/apps/stock-desk/backend/tests/test_fundamentals_spike.py（同上）
- /home/user/AICompany/apps/stock-desk/.env.example（同上）
- /home/user/AICompany/work/research/財務資料源spike-執行指令-2026-11-01.md（同上）
- 交件：/home/user/AICompany/work/reviews/2026-11-01-財務資料源spike交件-data-engineer.md、/home/user/AICompany/work/reviews/2026-11-01-財務資料源spike併入P項-data-engineer.md

# N-16 冪等略過影響範圍查證（data-engineer，唯讀＋離線探針）

- 審查者：data-engineer（本次唯讀）
- 日期：2026-10-18
- 轉存：coordinator，逐字轉存 subagent 最終回報

---

## 一、本次結論（N-16）

本次仍是唯讀查證。我沒有修改 repo 檔案，也沒有 commit。`git status --short` 為空，沒有讀 `.env`，沒有碰 `data/*.db`，也沒有連網。

**結論：取決於資料源行為。**
- 「盤中資料被標成 ok、擋掉定案後 run」這條路，在程式上可達，但需要一個前提：盤中時 TWSE `STOCK_DAY_ALL` 與 FinMind 要同時回傳「當日、同一份」的暫定值。
- 若盤中 TWSE 回傳前一交易日資料或空資料，這條路**不可達**，程式會擋下。
- repo 內沒有任何實測紀錄可以決定哪一種成立。程式只比對「兩個來源相等」，不判斷是否收盤。
- 探針已驗證這個判斷（見第三段）。

## 二、逐項回答

### 1. 盤中資料會不會被標成 ok

**依程式路徑的判斷（事實）：**
- 日期完全靠自證，沒有其他日期檢查。
  - `STOCK_DAY_ALL` 沒有日期欄，模組自己的說明也這樣寫（`app/data/providers/twse_snapshot.py:36-48`）。
  - 候選日取牆上時鐘（Asia/Taipei）的當天（`twse_snapshot.py:203-204`）。
  - 候選日用 FinMind 抽樣交叉比對（`twse_snapshot.py:316-350`）。
    - 樣本是固定的 2330 加 2 檔隨機（`:137-138`、`:352-357`）。
    - 查無資料就失敗（`:331-337`）。
    - 收盤或成交量不等就失敗（`:338-343`）。
    - 失敗時整批 `session_date` 為 None，且不退回牆上時鐘（`:218-222` 的 `_all_failed_result`）。
- `app/services/pit_snapshot.py` 在 `:301-341` 的 FinMind 路徑以外的 bars ok 門檻，只有覆蓋率 0.98（`:229-249`）。程式裡沒有任何「是否收盤」的檢查。
- FinMind adapter 只用 `start <= bar.date <= end` 過濾（`app/data/providers/finmind.py:165`）。查無資料時回傳 unavailable（`:134-135`）。
- 啟動時一定會立刻擷取一次，不分時段、不分星期：`app/scheduler.py:658-672`，`next_run_time=started`。手動 CLI 擷取同樣沒有時段防護（`pit_snapshot.py:431-445`）。
- 15:00 是消費端「定案」的基準（`app/data/freshness.py:110`，`publish_cutoff=time(15, 0)`）。擷取端不看它。

**就你問的情境逐一判斷：**
- **TWSE 盤中回傳前一交易日資料：不會寫成當天的 session。**
  - 候選日是今天。FinMind 在盤前或盤中若沒有今天的列，交叉比對在 `:331-337` 失敗。
  - 若 FinMind 有今天的暫定列，與前一日資料的收盤與成交量不等，則在 `:338-343` 失敗。
- **TWSE 盤中回傳空資料：**
  - 若為空陣列，`_fetch_bars` 回報沒有可解析的列（`:383-384`），整批 failed。
- **會寫成當天 ok 的唯一條件：** 盤中 TWSE 回傳當日進行中的值，FinMind 也有當日列，而且 2330 與另外 2 檔隨機抽樣的收盤與成交量完全相同，覆蓋率又 ≥ 0.98。
  - 之後 17:30 的擷取被 `_already_ok_today` 略過（`pit_snapshot.py:151-153`、`:201-202`）。定案值永遠不會被寫入該 session。
  - 我沒有實測資料源，所以這個條件是否在現實中成立，無法判定。

**其他旁證（事實）：**
- 週末手動擷取：候選日是週六，FinMind 查無該日列，整批 failed（探針 S5）。這點與先前報告的結構性結論一致。
- 覆蓋率不足（partial）不會擋住後續的 ok：`_already_ok_today` 只看有沒有 ok run（探針 S4）。

### 2. 探針

- 探針：`/tmp/claude-0/-home-user-AICompany/3f76d891-50d3-55e1-b39d-925b8a90241a/scratchpad/probe-n16/probe_n16.py`。
  - 用真實的 `TwseSnapshotAdapter` + `capture_once` + `MarketPanelStore`。
  - TWSE 與 FinMind 兩端都用 `httpx.MockTransport`，市場 DB 放在探針目錄底下的臨時資料夾。
  - 沒有碰 repo 內的 DB，也沒有寫入 repo。
  - 候選日沒有覆寫，用的是預設的牆上時鐘邏輯。
- 探針腳本在 repo 外，沒有進 repo。
- 【限制】兩個資料源的行為都是我假設的輸入，不是真實資料。探針只證明「在這些假設下，程式會怎麼走」，不證明資料源真的這樣。

### 3. 結論（可達性）

這個衝突「取決於資料源行為」。
- 若盤中 TWSE 回傳前一日資料或空資料：**不可達**。
- 若盤中 TWSE 與 FinMind 都回傳同一份當日暫定值：**可達**，而且之後無法自行修復。
- 另外兩個放大因子，使它在可達時更容易發生：
  - 啟動時一定會跑一次，不分時段。
  - 覆蓋率 ≥ 0.98 只代表「有 bar 的比例」，不代表已定案。

## 三、驗證（探針實際輸出）

在假設 D = 2026-10-19（週一），台北時間，下列為探針的實際輸出重點：

| 情境 | 結果 |
|---|---|
| S1：10:00，TWSE 仍給前一日資料、FinMind 無 D 列；17:30 改為定案且 FinMind 有列 | 10:00 為 failed、`session_date=NULL`（原因為「FinMind 交叉比對失敗：2330 查無資料」）；17:30 為 ok。最終 bars run：`(4, None, failed)`、`(8, 2026-10-19, ok)` |
| S2：10:00，`STOCK_DAY_ALL` 回傳空陣列 | failed，原因「回應中沒有任何可解析的列」；沒有 ok run |
| S3：10:00，TWSE 與 FinMind 都給同一份暫定值；17:30 為定案值 | 10:00 為 **ok**；17:30 `skipped_already_ok=True`。市場 DB 只有一筆 bars run：`(4, 2026-10-19, recorded_at=02:00 UTC, ok, 100, 100)`。`final_after`＝07:00 UTC（15:00 台北），所以這筆 ok run 是定案前的，消費端依 A-78 不認，且定案值沒有再寫入 |
| S4：10:00，兩源一致但只涵蓋 90%；17:30 為定案 | 10:00 為 partial（覆蓋率 0.9）；17:30 為 ok，不被略過。run：`(4, partial)`、`(5, 2026-10-19T09:30 UTC, ok)` |
| S5：週六 11:00 手動擷取，TWSE 給週五資料、FinMind 無週六列 | failed、`session_date=NULL` |
| S6：10:00，TWSE 給前一日資料、FinMind 有當日暫定列 | failed，原因「收盤/成交量與 STOCK_DAY_ALL 不一致」 |

- 只有 S3 重現了衝突，而 S3 的前提正是尚未實測的資料源行為。
- S1、S2、S5、S6 驗證了「前一日資料或空資料不會被寫成當天 ok」。
- S4 驗證了「partial 不會擋住後續 ok」。
- 沒有跑 repo 的 pytest。

## 四、下一步

### CEO 本機代跑探測時，額外要看的資料

`work/research/2026-10-16-Phase1資料源探測指令-CEO本機代跑.md` 的 §6.3（`:1371` 起）已規劃分時段探測，推論 2（`:1387` 前後）也寫了同一個疑慮。要能判定這個衝突，請在 §6.3 的盤中輪（`t1030`，建議加 `all`）特別留下以下兩項，並在收盤後輪對照：

1. **盤中 `STOCK_DAY_ALL` 的內容**：筆數，以及 2330 與其他幾檔的 `ClosingPrice`、`TradeVolume` 是否等於前一交易日，還是進行中的值。收盤後再抓一次，比較哪一時點開始變成定案值。
2. **盤中 FinMind `TaiwanStockPrice` 有沒有當日列**：對 2330 與幾檔隨機股，查 `start_date=end_date=今天`。有的話，記下 close 與 Trading_Volume，並與同一時刻的 TWSE 值逐位比對。FinMind 當日列出現的時間點，是判斷衝突是否可達的關鍵。

判讀：
- 若盤中 TWSE 是前一日資料，或 FinMind 沒有當日列：衝突不可達，A-78 的下限可維持現狀。
- 若兩者盤中同時給出同一份當日暫定值：衝突可達，需要 tech-architect 處理。

**輔助證據（不碰 DB 內容的方式由 CEO 自己在本機做）：** 對本機市場 DB 查 `kind='bars' AND status='ok' AND source='twse_snapshot'` 的 run，把 `recorded_at` 轉成台北時間，看有沒有早於 15:00 的列。有的話，這個衝突已經在實際資料上出現過。我沒有讀 DB，這項需要 CEO 代查。

### 給 tech-architect
- 處理選項不變：
  - A：接受現況，缺日由 L1395 的揭露涵蓋。
  - B：把冪等略過改為「已有定案後 ok」。這要改 `pit_snapshot`，與 A-78「不改 `pit_snapshot`」衝突，需要修訂。
- 建議等 §6.3 的實測結果再決定；若結果是不可達，選項 A 就夠了。
- 若選 B，改動範圍很小：`_already_ok_today` 的判斷改看 `recorded_at ≥ final_after`。我可以依裁示實作並補離線 fixture 測試，探針的 S3 與 S4 可轉成測試。

### 給 coordinator
- 本題沒有需要風控的內容，不涉及面向使用者的文案。

**相關檔案（絕對路徑）**
- `/home/user/AICompany/apps/stock-desk/backend/app/services/pit_snapshot.py`
- `/home/user/AICompany/apps/stock-desk/backend/app/data/providers/twse_snapshot.py`
- `/home/user/AICompany/apps/stock-desk/backend/app/data/providers/finmind.py`
- `/home/user/AICompany/apps/stock-desk/backend/app/scheduler.py`
- `/home/user/AICompany/apps/stock-desk/backend/app/data/freshness.py`
- `/home/user/AICompany/work/research/2026-10-16-Phase1資料源探測指令-CEO本機代跑.md`
- `/tmp/claude-0/-home-user-AICompany/3f76d891-50d3-55e1-b39d-925b8a90241a/scratchpad/probe-n16/probe_n16.py`

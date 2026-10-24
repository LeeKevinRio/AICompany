# N-118 程式碼面查證與 CEO 本機唯讀腳本草稿

- 審查者：data-engineer
- 日期：2026-10-24
- 轉存：coordinator，逐字轉存 subagent 最終回報

---

# N-118 程式碼面查證與 CEO 本機唯讀腳本草稿（data-engineer，2026-10-24）

我沒有改 repo 任何檔，沒有跑 git 寫入指令（只讀了 `git log -S`、`git status`），沒有讀 `.env`，沒有打網路，沒有讀、開、查詢任何 `*.db` 內容。對 `apps/stock-desk/backend/data/` 只做了一次 `ls -la`（看到 `stock-desk-market.db` 98304 bytes、10/04 15:09），沒有取 sha256。腳本與測試都放在 scratchpad，測試只用 `tmp_path` 自建的假 DB。標記：【事實】是讀碼、讀 fixture 或測試結果，【推論】是我的判斷，【待查】是只有實際資料才能回答。

## 一、本次結論

1. **限制 e（`row_count` 口徑）：程式碼面可以定案。**
   - 【事實】`dividend_announce` run 的 `row_count` 是「通過 Code 檢查後、去重之前」的解析列數。
   - 它不是來源回應的原始列數，也不是實際寫入 `pit_dividend_announce_rows` 的列數。
   - key 重複時，後者覆蓋前者，所以 `row_count − stored_row_count` 等於被覆蓋掉的列數。
   - `stored_row_count ≠ row_count` 可以當作 run 層級的撞號偵測，整體等價於「這批有至少一組 key 撞號」，但定位不到是哪一檔。
   - 兩個誤差方向要注意：全同內容的重複列也會觸發，但沒有資訊損失；沒有 Code 的列兩個數字都看不到。
2. **限制 c（撤銷規則的前提）：程式碼面只能做兩件事。**
   - 能確認「沒有任何程式碼機制保證它成立」，而且有一個結構性缺口：`dividend_announce` 的 ok 沒有完整性檢查。
   - 能確認既有 fixture 對它完全無法發言。
   - 前提是否在真實資料成立，只能看 CEO 本機的歷史擷取資料。
3. **N-118 不能只靠程式碼面關閉。** 只能關閉 `row_count` 口徑那一半，限制 c 必須由 CEO 本機執行唯讀腳本。
4. **CEO 本機的證據仍有天花板。** 腳本只能數出「事件消失」，分不出「真撤銷」與「來源單批不完整」。我給了機械判準，但「消失事件是不是真撤銷」若要定論，還需要對照 TWSE 公告，那一步要有網路的人才能做。
5. **這份工作目錄裡的 DB 幾乎一定不是有效樣本。** 98304 bytes 連一份完整的全市場日線 run 都放不下【推論，只憑 stat 的大小】。CEO 本機的 DB 才有意義。

## 二、各部門回報

### 1. `row_count` 口徑（限制 e）

**資料流（逐步，行號為今天讀到的 working tree，經 `git log -S` 確認這幾段自首次提交 9a57a03 起未變）**

| 步驟 | 行為 | 檔案:行 | 標記 |
|---|---|---|---|
| 逐列解析 | 非 dict 的列、沒有 Code 或 Code 為空白的列只計入 `skipped`，不放進列表 | `app/data/providers/twse_snapshot.py:449-458` | 【事實】 |
| 放進列表 | 其餘每列都放進 `rows`，包含 `Date` 解析失敗（`ex_date=None`）者。`symbol` 先 `strip()` | `twse_snapshot.py:459-467` | 【事實】 |
| 空批 | `rows` 為空就整批視為失敗，所以 ok 的 run 至少 1 列 | `twse_snapshot.py:468-469` | 【事實】 |
| 記數 | `row_count=len(dividend_rows)`，這是去重前的列數 | `twse_snapshot.py:284` | 【事實】 |
| 傳遞 | `outcome.row_count` 原樣交給 `record_run`，`expected_count=None` | `app/services/pit_snapshot.py:166-175` | 【事實】 |
| 寫入 run | store 不重算，原值寫入 `INSERT ... row_count` | `app/data/market_panel.py:509-526`（欄位 :129） | 【事實】 |
| 寫入內容 | `keyed[key] = ...`，同 key 後者覆蓋前者；`key = f"{row.symbol}|{raw Date}"` | `market_panel.py:607-611` | 【事實】 |
| 實際寫入 | 只在該 `content_hash` 尚無列時插入 `keyed` 的內容 | `market_panel.py:618-630` | 【事實】 |

- **誰呼叫 `record_run`**：`app/` 內只有 `pit_snapshot.py` 的四處（:139、:166、:206、:251）。失敗 run 的 `row_count=0` 且沒有 `content_hash`。【事實，Grep】
- **store 註解**（`market_panel.py:601-603`）寫「撞號數會折進呼叫端看得到的 `row_count` 落差」。這句話在正式路徑上屬實，但落差來自 provider 傳進來的是去重前的列數，store 本身不計算也不驗證。【事實】
- **所以三個數字的關係**：
  - 來源回應列數 ≥ `row_count`，差額是被略過的非 dict 與無 Code 列。這個差額沒有存進 DB（只在整批失敗時出現在 reason 字串，`twse_snapshot.py:469`），任何讀端都看不到。
  - `row_count` ≥ `stored_row_count`，差額就是 key 撞號被覆蓋的列數。
  - key 撞號包含兩種：同 Code 同 Date 的兩列（例如權、息分列），以及 Code 只差前後空白的兩列（`strip()` 後相同）。
- **端到端驗證**：我用真正的 `_fetch_dividend_announce`（假 HTTP client）、`capture_once`、`MarketPanelStore`，在 `tmp_path` 的假 DB 上跑一份有重複的 payload。
  - 輸入：5 列，其中 1 列無 Code、3 列在 strip 後同一個 symbol 同日期。
  - 結果：4 個解析列、2 個 distinct key，探針算出 `row_count − stored = 2`，與預期一致。測試名 `test_row_count_deficit_equals_collapsed_rows_end_to_end`。【事實】
- **`stored_row_count ≠ row_count` 能否當撞號偵測**：
  - 在正式寫入路徑上，`stored < row_count` ⟺ 該批至少有一組 key 重複。【事實，讀碼加上述測試】
  - 限制一：定位不到哪個 key。被覆蓋的那列的內容已不在 DB（只剩後者）。
  - 限制二：全同內容的重複也會觸發，此時沒有資訊損失。WARNING 與 §4.2 揭露的字面不應寫成「資料遺失」。
  - 限制三：`stored > row_count`、`stored = 0`、ok 但 `content_hash` 為 NULL，在正式路徑上不應出現。出現就是寫入路徑或資料完整性問題，不是撞號。腳本分別計數。
  - 限制四：依賴「呼叫端傳的是去重前的列數」這個慣例。測試或手動寫入的 run 可以傳任意 `row_count`（`tests/test_market_panel_store.py` 大量使用 `row_count=1`），所以 TA 的讀端 WARNING 對這類 run 無意義。正式 DB 由 `pit_snapshot` 寫入，不受影響。
  - 限制五：兩個 run 若去重後內容相同，會共用同一個 `content_hash`，但 `row_count` 各自記錄，所以偵測是每個 run 獨立成立的。TA 寫的 `stored_row_count`（以 `content_hash` 計列數）可以直接用。
- **對 TA 的 (e)、(i9) 的含義**：`row_count` 的口徑可以定格為「去重前、略過無 Code 列之後的解析列數」。(i9) 的「同一批兩列同 key → `stored_row_count < row_count`」成立。真實資料中有沒有發生過，只有 CEO 本機輸出能回答，但那是發生率，不影響設計。

### 2. 限制 c 的可查證性

**c 的字面**：來源在除息日前的每個交易日都列出該事件。

**能從程式碼／fixture／文件判斷的**
- 【事實】程式與文件都宣稱預告表只列未來事件，過了日期就移除：`app/dividends/providers.py:99-102`、`app/dividends/coverage.py:11-13`、`app/dividends/sync.py` 檔頭。這只支持「除息日之後消失屬於過期」。
- 【事實】專案自己把「除息日前持續列出」當成**未驗證**的假設。`coverage.py:90-97` 把 ADR-0016 V-1 的 L 定義為「除息日前 L 天起每個 ok 同步都列出該事件」，並寫明 UNVERIFIED（`coverage.py:40-47`：本環境無法連 TWSE，預設取最小值 1）。所以 N-118 的 (c) 本質上是 V-1 判準 2（持續性）。
  - `scripts/v1_announce_lead_probe.py` 已有「持續性異常」段，但它以 `recorded_at` 對台北午夜比較，逐筆輸出（個股明細），沒有 `row_count` 對照。
  - 查 `work/` 沒有發現這支腳本被執行過的結果檔。【事實，Grep 零命中】
- 【事實】**結構性缺口：沒有任何程式碼保證一個 ok run 是完整的。**
  - bars 有 98% 覆蓋閘門（`pit_snapshot.py:181-` 一帶），但 `dividend_announce` 走 `_capture_simple_kind`，`expected_count=None`（:172）。
  - 只要回應是 JSON 陣列、至少 1 列有 Code 就記 ok（`twse_snapshot.py:443-470`）。
  - 所以來源回傳被截斷或漏列的單批回應，照樣記成 ok run，之後讀端會把缺漏的事件當成撤銷。
  - 這是 TA 提案「C1 在來源單批不完整時會少套一個因子」的結構性成因。程式碼面只能確認這個風險存在，無法量化。
- 【事實】有 Code 但 `Date` 解析失敗的列，`ex_date=None` 仍會存（`twse_snapshot.py:461-467`）。讀端依 D-4 不比較這些列，它們的消失看不到。腳本把這類 key 另計。
- 【事實】`tests/fixtures/twse_openapi_twt48u_all.json` 只有單一時點的 7 列合成資料（`Name` 為佔位），沒有跨日資料，也沒有重複 key。它對持續性完全無法發言。

**只能看實際歷史擷取資料的**
- 某事件是否在除息日前的某個 ok run 中消失，之後是否再出現。
- 消失是否呈整批特徵（一個 run 一次掉很多事件，暗示單批不完整），還是零星（較像真撤銷或改期）。
- 沒有 ok run 的交易日有多少（腳本只能看 ok run，看不到缺的日子，也沒有交易日曆）。
- 實際有沒有撞號，以及撞號發生率。
- 每個 session 只保留第一筆 ok run（`pit_snapshot.py:151-153,160-161`），所以只能檢驗「session 層級」的持續性，不是「日內」。

**程式碼與資料都回答不了的**：消失的事件是真撤銷，還是來源單批不完整。要靠對照 TWSE 公告，需要有網路的人。

### 3. CEO 本機唯讀查證腳本草稿

**檔案（皆在 scratchpad，尚未進 repo）**
- `/tmp/claude-0/-home-user-AICompany/3f76d891-50d3-55e1-b39d-925b8a90241a/scratchpad/n118/n118_dividend_persistence_probe.py`
- `/tmp/claude-0/-home-user-AICompany/3f76d891-50d3-55e1-b39d-925b8a90241a/scratchpad/n118/test_n118_probe.py`
- 示範用假 DB（自建）：`/tmp/claude-0/-home-user-AICompany/3f76d891-50d3-55e1-b39d-925b8a90241a/scratchpad/n118/fake/demo.db`

**設計**
- 只用標準函式庫（Python 3.10 以上），不 import `app.*`。
- 以 `sqlite3` 的 `file:...?mode=ro` URI 開檔，並下 `PRAGMA query_only=ON`。檔案不存在就拒絕（exit 2），不會新建。
- 只有兩條 SELECT：`pit_snapshot_runs`（kind、status、session_date、content_hash、row_count）與 `pit_dividend_announce_rows` 的 `(content_hash, key, symbol, ex_date)`。**不選 `raw_json`，不選 `Name`。**
- 不寫任何檔，只印 stdout。預設只輸出彙總計數。`--detail N` 才會列最多 N 筆 `vanished_*` 事件（代號、除息日、run id），預設為 0。
- SQLite 本身的副作用：讀 WAL 模式 DB 時旁邊可能出現 `-wal`／`-shm` 輔助檔，DB 檔本身位元組不變。這與既有 V-1 探針相同。

**事件分類（以 `session_date` 比較，與 D-4 第 2 點「`session_date` 早於 `ex_date`」一致）**
- 對每個 key（`symbol|原始 Date`），從第一個列出它的 ok run 起，到除息日前的最後一個 ok run 為止，看每個 run 有沒有列出它：
  - `persistent`：每個 run 都列出。
  - `vanished_gone`：某個 run 沒列出，之後到除息日前都沒再出現。
  - `vanished_returned`：某個 run 沒列出，之後又出現（有缺口）。
  - `single_observation`：除息日前只有 1 個 run，無法檢驗。
  - `first_seen_on_or_after_ex`：第一次被看到時已不早於除息日，不檢驗。
- `vanished_gone` 再細分：`reschedule_candidate`（同一個 symbol 在消失當下有一個前一個 run 沒有的新 key）、`symbol_relisted_existing`（同 symbol 還有別的既有 key）、`symbol_gone`（同 symbol 完全不在）。
- 事件另分 `closed`（最後一個 ok run 不早於除息日）與 `open`（還沒走完，消失者可能再出現）。
- 另輸出：相鄰 ok run 之間的「掉出」次數與最大單批掉出數與比例（整批不完整的特徵）、同一 session 多個 ok run 的數量、相鄰 ok run 相隔超過 4 天的次數、持續列出但最後一個 ok run 距除息日超過 3 天的事件數。
- `row_count` 段：ok run 數、`row_count == stored`／`stored < row_count`／`stored > row_count`／`stored == 0`／ok 但 hash 為 NULL／`row_count ≤ 0` 的數量、差額總和與最大差額、受影響的 distinct `content_hash` 數、不符的 run_id（最多列 20 個）、非 ok run 依 status 的數量。

**測試（自建假 DB，用真正的 `MarketPanelStore` 寫入，無網路）**

```
cd apps/stock-desk/backend
PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -m pytest -p no:cacheprovider \
    <scratchpad>/n118/test_n118_probe.py --rootdir <scratchpad>/n118 -q
...............                                                          [100%]
15 passed in 1.08s
```

涵蓋你要求的四種情形，另有邊界：
- **消失**：`test_disappearance_without_return_is_vanished_gone_symbol_gone`。
- **再出現**：`test_reappearance_is_vanished_returned_and_counts_the_gap`。
- **改期**：`test_reschedule_old_key_gone_new_key_added_is_candidate`，另有 `test_symbol_with_other_existing_event_is_not_called_a_reschedule`，確認同 symbol 還有既有事件時不誤判為改期。
- **key 重複**：`test_key_duplicate_in_one_batch_makes_stored_less_than_row_count`，以及前述端到端測試。
- 其他：持續列出且已 closed 的基準、open 事件、單次觀察與除息日後才首見不檢驗、failed run 不算缺席、`stored > row_count` 會被回報而不是被隱藏、byte 不變與寫入被拒（`DELETE`、`CREATE` 都拋 `OperationalError`）、不存在的檔不會被建立（exit 2）、SQL 只有 SELECT 且不含 `raw_json`、預設輸出不含代號與 `Name`（`--detail` 才出現代號，仍不含 `Name`）。

**在示範假 DB 上的實際輸出（節錄；該 DB 刻意含 1 個持續、1 個消失、1 個再出現、1 個改期、第 1 個 run 含重複 key）**

```
== N-118 probe: TWT48U_ALL persistence (c) and row_count (e) ==
usable ok runs (hash and session_date set) : 6
events (keys with a parsed ex_date)        : 7
  closed (last run on/after ex_date)       : 6
persistent                 :     3 / 0
vanished_gone              :     2 / 0
vanished_returned          :     1 / 0
single_observation         :     0 / 1
testable closed events (>=2 runs)      : 6
vanished_gone split (closed / open):
  reschedule_candidate      :     1 / 0
  symbol_relisted_existing  :     0 / 0
  symbol_gone               :     1 / 0
drop episodes (event, pair)                : 3
largest drop in one pair                   : 2
largest drop share of that pair's pending  : 0.400
ok runs                                    : 6
  row_count == stored                      : 5
  stored < row_count                       : 1
sum of (row_count - stored) where less     : 1
mismatch run_ids                           : [1]
non-ok dividend_announce runs by status   : failed=1
```

示範資料中「持續列出但最後一個 ok run 距除息日超過 7 天」顯示 3，是示範 DB 的 run 間隔造成（9/7 之後下一個 run 是 10/5），用來展示「未觀察到的尾段」指標會動，不代表任何真實結論。

**CEO 執行指令（比照決策包 #49 的形式；路徑用變數）**

草擬的決策包條目（編號由 coordinator 指派）：

| 編號 | 事項 | 選項 | 建議 | 依據 |
|---|---|---|---|---|
| 待指派 | **N-18／N-118 查證：除權息預告表是否在除息日前持續列出事件，以及擷取紀錄的 `row_count` 是否與實際寫入列數一致（N-17 撤銷規則的前提）**。腳本唯讀開啟您本機的市場 DB，只輸出彙總計數，不讀價格、不讀 `raw_json`、不寫檔、不改 DB、不需網路與祕密 | (a) 您在本機代跑一次並回貼 stdout（指令由 data-engineer 準備）；(b) 暫不處理（ADR-0027 D-9 因子路徑維持阻擋） | 建議 (a) | `work/reviews/2026-10-24-N118限制c與row_count查證-data-engineer.md`（待轉存）；`work/reviews/2026-10-24-N17因子修訂觸發提案-tech-architect.md` |

指令（腳本進 repo 前，請 coordinator 先把檔案放到 `$N118_DIR`；進 repo 後改用 `scripts/` 下的路徑）：

```
# set once; adjust to your machine
REPO=<path to your AICompany checkout>
N118_SCRIPT=<path to n118_dividend_persistence_probe.py>
export STOCK_DESK_MARKET_DB_PATH="$REPO/apps/stock-desk/backend/data/stock-desk-market.db"   # or the market DB your service really uses

# 1) aggregates only (paste the whole stdout back)
python3 -I "$N118_SCRIPT" --db-path "$STOCK_DESK_MARKET_DB_PATH"

# 2) optional, only if section (c) shows vanished_* > 0: list at most 30 vanished events
#    (symbol, ex-date, run ids; no names, no prices, no raw rows)
python3 -I "$N118_SCRIPT" --db-path "$STOCK_DESK_MARKET_DB_PATH" --detail 30
```

- 服務可以照常運行，腳本只讀、不取寫鎖。要更保守時，可先把 `.db`、`.db-wal`、`.db-shm` 三個檔一起複製到別處再跑；不需要的話直接跑即可。
- 不需要重導向到檔案，直接貼回 stdout。
- 退出碼：0 成功；2 表示讀不到 DB、表不存在或沒有任何 `dividend_announce` run。

**輸出如何判讀（機械判準。數字門檻是我的建議值，要由 TA 與風控確認後才算數）**

(c) 持續性，先看樣本夠不夠：
- 「testable closed events」建議至少 30，且 usable ok runs 建議至少 20。不足就判為**無法判定**，限制 c 維持【未驗證】，N-17 撤銷規則的前提不能算已查證。
- 同時看 `consecutive ok runs more than 4 days apart` 與 `persistent closed, last run >N days before ex_date`。這兩個數字大，代表「每個交易日」只觀察到一部分，證據要打折。

(c) 成立（在樣本內未被推翻）需同時滿足：
- 樣本足夠。
- `vanished_returned` 的 closed 數為 0。
- 沒有整批掉出的特徵：`largest drop in one pair` 小於 3，或 `largest drop share` 小於 0.10。
- `vanished_gone` 的 closed 事件（`reschedule_candidate` 與 `symbol_gone`）是 D-4 本來就視為撤銷或改期的情形，不算反例。但它們各自是不是真撤銷，需要 TWSE 公告對照，才能升級為「已驗證」。

(c) 不成立（任一即成立，TA 須退回修訂第 10 點與 D-4 第 2 點）：
- `vanished_returned` 的 closed 數 ≥ 1。這代表來源曾經漏列過後來又出現的事件，「每個交易日都列出」字面上為假，而且 D-4 的撤銷規則在中間視圖會誤判。
- 出現整批掉出特徵：單一 run 對的掉出數 ≥ 3，且掉出比例 ≥ 0.10。這暗示來源單批回應不完整，而 `dividend_announce` 沒有完整性閘門，這類 run 會被記為 ok。

對 TA 的影響：不成立時可考慮的方向是要求連續缺席 k 個 run 才視為撤銷、改記因子不可用（C2）、或加批次完整性防護。選哪個是 TA 的決定，後兩者涉及寫端或作廢定義，可能牽動 N-119。

(e) `row_count`：
- `stored < row_count` 的 run 數為 0：樣本內沒有發生撞號，WARNING 路徑的預期量為 0。
- 大於 0：撞號確實發生，`sum of (row_count − stored)` 是被覆蓋的列數。N-119（寫端改 key）的優先度應提高；是否造成資訊損失需用 `--detail` 之外的方式查，腳本不看內容。
- `stored > row_count`、`stored == 0`、ok 但 `content_hash` 為 NULL、ok 但 `row_count ≤ 0` 任一大於 0：不屬於撞號，是寫入路徑或資料完整性問題，須回報，不可併入撞號揭露。

### 4. 結論：N-118 能否只靠程式碼面關閉一部分

| 部分 | 程式碼面能否關閉 | 說明 |
|---|---|---|
| `row_count` 口徑（限制 e） | **能，建議現在關閉** | 口徑與覆蓋關係已用讀碼加端到端測試定案，(i9) 可定格。發生率是資訊性的，不阻擋設計。 |
| 限制 c（持續列出） | **不能** | 程式碼面只能證明「沒有機制保證」與「ok 沒有完整性檢查」，fixture 無法發言。必須由 CEO 本機執行腳本。 |
| 消失事件是否為真撤銷 | **不能，連 CEO 本機也不一定能** | DB 內看起來相同，需要對照 TWSE 公告，要有網路的人。 |

我的建議：coordinator 把 N-118 拆成兩項。row_count 口徑那項標為完成，限制 c 那項維持阻擋（D-9 結算與更正作業因子路徑實作前），等 CEO 回貼。

## 三、驗證

- **做過**：
  - Read／Grep：`market_panel.py`（:100-250、:440-700）、`pit_snapshot.py`（:95-195）、`twse_snapshot.py`（:166-300、:255-470）、`coverage.py`、`providers.py` 檔頭、`v1_announce_lead_probe.py`、`test_v1_announce_lead_probe.py` 開頭、`tests/fixtures/twse_openapi_twt48u_all.json` 結構、兩份相關 review、追蹤清單 N-118 條目。
  - `git log -S`：確認 `row_count=len(dividend_rows)` 與 `keyed[key] =` 都只有 9a57a03 一個提交引入。
  - 測試：自建假 DB 上 15 個測試全過（上節輸出）。測試與示範都用 `PYTHONDONTWRITEBYTECODE=1 -p no:cacheprovider`，沒有在 repo 留下檔案；事後 `git status` 沒有新增項目（既有的 `app/forecast`、`app/outlook`、`app/ops_alert` 等 untracked 與我無關）。
- **沒做**：
  - 沒有讀任何真實 DB 的內容或筆數，也沒有取 sha256。
  - 沒有量測真實的持續性或撞號發生率。
  - 沒有驗證 TWT48U_ALL 在除息日前後的實際行為（無網路）。
  - 沒有跑全專案測試套件、mypy 或 ruff。腳本草稿在進 repo 前須補這些，並過 qa-reviewer 審查。
- **假設與邊界**：
  - 「stored 與 row_count 差額等於被覆蓋列數」只對正式寫入路徑成立（`pit_snapshot` → `record_run`）。
  - 判準的數字門檻（30、20、3、0.10）是建議值，不是已核可的規則。
  - 腳本的 `recorded_at` 不參與任何比較，只用 `run_id` 與 `session_date`，與 ADR 第 5 點「不比較時鐘」一致。

## 四、下一步

1. **coordinator**：
   - 把本報告轉存為 `work/reviews/2026-10-24-N118限制c與row_count查證-data-engineer.md`。
   - 追蹤清單：N-118 拆為 N-118a（`row_count` 口徑，程式碼面完成）與 N-118b（限制 c，待 CEO 本機輸出）。
   - 決定腳本進 repo 的位置（建議 `apps/stock-desk/backend/scripts/n118_dividend_persistence_probe.py`，測試放 `tests/`，比照 `v1_announce_lead_probe`）。進 repo 需另走 commit 與 qa-reviewer 審查。
   - 若要發給 CEO，把上面那一列併入決策包。
2. **tech-architect**：
   - 可把 FL-64 (i9) 的 `row_count` 口徑定格為「去重前、略過無 Code 列之後的解析列數」。
   - 提案的 WARNING 與 §4.2 揭露字面要避免寫成「資料遺失」（全同重複沒有損失）。
   - 在 CEO 輸出回來之前，不要把限制 c 寫成已查證。
   - 同步評估「`dividend_announce` ok 沒有完整性檢查」是否要另立項（可能併入 N-119 的寫端案）。
3. **CEO**：在本機照上面的指令代跑一次，回貼 stdout。若 `vanished_gone` 大於 0，再跑 `--detail 30`。
4. **quant／風控**：確認判準的數字門檻，或指定其他門檻。
5. **（可選）CEO 或有網路的人**：若判為「成立」，對 `vanished_gone` 的事件抽查 TWSE 公告，確認是真撤銷或改期，才能把 c 從「樣本內未被推翻」升級為「已驗證」。

涉及檔案（絕對路徑）：
- /tmp/claude-0/-home-user-AICompany/3f76d891-50d3-55e1-b39d-925b8a90241a/scratchpad/n118/n118_dividend_persistence_probe.py
- /tmp/claude-0/-home-user-AICompany/3f76d891-50d3-55e1-b39d-925b8a90241a/scratchpad/n118/test_n118_probe.py
- /tmp/claude-0/-home-user-AICompany/3f76d891-50d3-55e1-b39d-925b8a90241a/scratchpad/n118/fake/demo.db
- /home/user/AICompany/apps/stock-desk/backend/app/data/market_panel.py
- /home/user/AICompany/apps/stock-desk/backend/app/data/providers/twse_snapshot.py
- /home/user/AICompany/apps/stock-desk/backend/app/services/pit_snapshot.py
- /home/user/AICompany/apps/stock-desk/backend/app/dividends/coverage.py
- /home/user/AICompany/apps/stock-desk/backend/app/dividends/providers.py
- /home/user/AICompany/apps/stock-desk/backend/scripts/v1_announce_lead_probe.py
- /home/user/AICompany/work/research/V-1-除權息列出前置天數-查證指令-2026-10-04.md
- /home/user/AICompany/work/reviews/2026-10-24-N17因子修訂觸發提案-tech-architect.md
- /home/user/AICompany/work/dispatch/2026-10-17-後續追蹤清單.md

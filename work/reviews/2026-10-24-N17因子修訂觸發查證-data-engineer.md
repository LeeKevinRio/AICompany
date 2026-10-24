# N-17 因子修訂觸發第一步查證

- 審查者：data-engineer
- 日期：2026-10-24
- 轉存：coordinator，逐字轉存 subagent 最終回報

---

# N-17 第一步查證回報（data-engineer，2026-10-24）

我沒有改任何檔、沒有 commit、沒有讀 `.env`、沒有打網路、沒有跑測試。`apps/stock-desk/backend/data/*.db` 只做了 `ls -la` 看大小與日期（stock-desk-market.db 98304 bytes、10/04 15:09），沒有讀內容、沒有取 sha256。現況核對：行號與我 2026-10-18 的前置查證（`work/reviews/2026-10-18-V14-03規章與缺bar機制及因子修訂前置查證-data-engineer.md` 第二節第 6 項）一致。以下標【事實】為讀碼或讀 ADR 字面，標【推論】為我的判斷，標【待查】為手上沒資料。

## 一、本次結論

1. 【事實】現有資料能偵測「同一個 key 的因子欄位值變了」，前提是修訂發生在除息日之前，而且落在不同 session 的 ok run。`pit_dividend_announce_rows` 只增不改，每一列保存來源逐字原值（`raw_json`），相鄰兩筆 ok run 可以逐 key 比對。
2. 【事實】能力有四個硬限制，第 4 點「完全看不到」只能由 TA 明定處理，不能由工程補：
   - 每個 session 最多一筆 ok 的 dividend_announce run（第一次成功就略過後續，`pit_snapshot.py:151-153,160-161`），同一 session 內的修訂看不到。
   - 預告表只列未來除息日，除息日之後的事後更正不會出現在這張表。
   - 同一個 key 在同一批資料裡重複時，後者靜默覆蓋前者（`market_panel.py:597-611`），偵測不到。
   - 「晚到」只能用 `run_id` 序號判定，不能用時鐘（與 ADR 現有的 R-11 一致）。
3. 【事實】實作缺口：
   - 沒有任何偵測方法。`scan_late_market_bars`、`ok_bars_runs_between`、`dividend_factor_corrected` 在 `apps/` 零命中。
   - `adjust_series_pit`、`AdjustedSeries` 在 `apps/` 零命中。`app/forecast`、`app/outlook` 目錄不存在。
   - 現有唯一的還原函式是 `back_adjust_bars`（`app/dividends/adjust.py:224`），ADR-0027 D-5.3 規定它不動。
   - 現有 PIT 視圖只載入 `(symbol, ex_date)`（`market_panel.py:1048-1052`），不載入現金股利、配股比。
4. 【推論】R-11 的讀端輪詢可以比照，但不能直接套用。bars 是「新 run 帶來新列」，announce 是「新 run 對同一 key 帶來不同的值」，所以多一個「與前一版比對」的步驟，要新增兩個唯讀方法。

## 二、各部門回報（data-engineer）

### 1. `pit_dividend_announce_rows` 與相關表的結構（檔案:行號）

**表結構**（`apps/stock-desk/backend/app/data/market_panel.py`）：

| 表 | 欄位／主鍵 | 行號 |
|---|---|---|
| `pit_snapshot_runs` | `run_id INTEGER PK AUTOINCREMENT`、`kind`（bars／listing／classification／dividend_announce）、`session_date`（可 NULL）、`recorded_at`、`source`、`status`（ok／partial／failed／quality_failed）、`row_count`、`expected_count`、`content_hash`、`reason` | :121-134 |
| `pit_dividend_announce_rows` | `content_hash`、`key`、`symbol`、`ex_date`（可 NULL）、`raw_json`；主鍵 `(content_hash, key)` | :189-198 |
| 追加專用保護 | 五張表都有 `BEFORE UPDATE/DELETE` trigger，`RAISE(ABORT,'append-only')`；`market_backfill_progress` 除外 | :217-236,:459-462 |

**這張表沒有 `run_id`、`as_of`、`fetched_at` 欄位。** 時間與順序全在 `pit_snapshot_runs`：`run_id` 提供序號，`recorded_at` 由 store 自己的時鐘填入、不接受呼叫端傳入（:499）。run 與內容用 `content_hash` 連結。

**寫入者與流程**：
- 寫入 `kind='dividend_announce'` 的是 `capture_once`（`app/services/pit_snapshot.py:116-132`）。順序是 listing、classification、dividend_announce、bars。
- 簡單 kind 的寫入在 `_capture_simple_kind`（`pit_snapshot.py:156-178`）。已有同 session 的 ok run 就直接略過，不寫新 run（:160-161）。
- 排程點：17:30、19:30、21:30（`scheduler.py:484-504`，我 10-18 的查證）。
- 提供者在 `twse_snapshot.py:430-470`（`_fetch_dividend_announce`）。
  - 資料來自 `TWT48U_ALL`。
  - 每列的所有欄位都逐字轉成字串，存成 `raw`（:459）。
  - `Date` 解析失敗時 `ex_date=None` 但仍然存（:461-464）。
  - 沒有 `Code` 的列只計入 skipped，不存（:452-458）。
- 內容寫入在 `_write_dividend_content`（`market_panel.py:594-631`）。
  - key ＝ `"{symbol}|{原始 Date 字串}"`（:610）。
  - `content_hash` ＝ 全批資料（key、symbol、ex_date、排序後的 raw JSON）的 SHA-256（:612-617）。
  - 該 `content_hash` 已有列就不重複插入（:618-622）。每個 session 仍會有自己的 run 指向同一個 `content_hash`（模組註解 :39-51）。
  - 同批資料內 key 重複時，「後者覆蓋前者」，沒有對外回報的通道（註解 :597-606）。

**run 結構歸納**：
- 每個 session 最多一筆 ok 的 dividend_announce run（第一次成功的那筆）。之後再擷取到的內容不會寫入。
- `status` 在這個 kind 實際只會是 ok 或 failed。provider 只回 ok 或 failed（`twse_snapshot.py:279-284`）。
- 整批失敗（沒有 session_date）時，四個 kind 各寫一筆 failed run，`session_date=NULL`、`content_hash=NULL`（`pit_snapshot.py:120-122,135-148`）。
- `run_id` 與 bars 等其他 kind 共用同一個序號，所以序號不連續屬於正常。任何以 `run_id` 範圍掃描的程式都必須先過濾 `kind` 與 `status='ok'`。
- 只增不改，修訂值以「新 session 的新 run，指向新 `content_hash`，帶新的一整份列」的方式出現。舊列不會被改動。

**相關但不屬於這條鏈的表**：
- 主 DB `dividend_sync_runs` 與 `dividend_events`（`app/dividends/store.py:55-103`），是持倉鏈（ADR-0016 D-5.2）。`dividend_events` 是 upsert（`store.py:473`），會覆蓋原值，沒有版本史。
- ADR-0027 FL-5 禁止 `app/forecast/**` 讀它。預測鏈要用市場 DB（D-4 第 2 點，ADR 行 872）。
- `price_bars_fetch_log` 只管 bars 快取，與除權息無關。市場 DB 沒有 per-fetch 的 attempt log。

### 2. 兩次擷取之間來源修正因子，現有資料能不能偵測

**因子的來源欄位**。這個預告表（`app/dividends/providers.py` 檔頭）每列有 `Date`、`Code`、`Exdividend`、`CashDividend`、`StockDividendRatio` 等欄位。
- 它不發佈前一日收盤價，也不發佈參考價。
- 因子由 `DividendEvent.adjustment_factor`（`app/dividends/models.py:147-185`）算出：`(前收 − 現金股利 − 權值) ÷ 前收`，前收由 `adjust.py:165-191` 從 bars 補。
- 只要 `stock_dividend_ratio` 非空，因子就不可用（`models.py:171-176`，ADR 的 `dividend_factor_unusable`「含配股」）。

所以因子可能因三條路徑改變，偵測難度不同：

| 修正路徑 | 在 announce rows 可偵測嗎 |
|---|---|
| `CashDividend` 數值變 | 可。同 key、不同 `raw_json` |
| `StockDividendRatio` 空白 ↔ 有值（因子在可用／不可用間翻轉） | 可。同上 |
| `Date` 改變（除息日移動） | 可偵測到「舊 key 消失、新 key 出現」，但無法證明兩者是同一個事件（見下） |
| 前收（`ex_date − 1` 的 bar）被更正 | 不在 announce rows，屬 bars 的問題 |

**配對鍵**：
- 現有的鍵是 `symbol|原始 Date 字串`。同一事件在兩個 run 都有同一個 key 時，可靠。
- 同 symbol 同日期的兩個不同事件（例如 權、息 分列）會撞同一個 key（`market_panel.py:607-611`，後者覆蓋）。這會導致「只剩一列」，偵測不出被吃掉的那一列。可以間接用 `row_count` 對照該 run 實際寫入列數來發現，我沒有看到現有程式做這個對照。
- 除息日改期：key 不同，無法機械區分「改期」與「撤銷一個、新增一個」。同 symbol 在相鄰 run 恰好一個舊 key 消失、一個新 key 出現，可以推定為改期，但這是推論。

**「修正」vs「新事件」vs「重複」的判法**（我建議的歸類，皆以相鄰兩筆 ok run 為單位）：
- 重複：`content_hash` 相同，或同 key 且因子投影相同（Name、認購相關欄位變了不算）。
- 修正：同 key，因子相關欄位（Exdividend、CashDividend、StockDividendRatio）正規化後不同。
- 新事件：key 在前一份沒有、後一份有，而且同 symbol 沒有消失的舊 key。
- 改期或撤銷：舊 key 在後一份消失，而且後一份的 `session_date` 仍早於該 key 的除息日；`session_date` 已晚於除息日的消失視為正常過期。這個分界要有「除息日當天表單是否還列出」的事實支持，手上沒有，標【待查】。

**正規化是必要的**：`raw_json` 存的是來源字串（例如 `"3.000000"`），`_cell` 把 `""`、`-`、`--`、`N/A` 等視為空白（`providers.py:146,208-214`）。比對時必須先經 `parse_dividend_row` 同一套解析，不能直接比 JSON 字串。

**空白到有值不等於修正**。檔頭明說空白是「金額尚未公布」（`providers.py:75-88`）。若空白時段已被結算使用（現金股利按 0 處理，`models.py:182-184` 讓因子為 None），列會落入 `dividend_factor_unusable` 作廢，之後補上數值屬於「作廢後補到資料」（`VOID_LATE_DATA_KINDS` 的 `dividend_factor`），不是 `dividend_factor_corrected`。歸哪一類取決於鏈尾列的 `status`，這一點 TA 要寫明。

**時間戳能不能判定晚到**：
- 能的部分：用序號。`run_id > settle_source_run_max`（ADR 行 508）就是結算當下市場 DB 還沒有的 run。ADR 行 1291 已規定判定視圖對除權息事件也只取 `run_id ≤ R`，所以對 announce 套同一個界限是一致的。
- 不能的部分：「修訂發佈於何時」。我們只知道哪個 session 第一次擷取到新值，`recorded_at` 是擷取時間，不是來源修訂時間。ADR 行 505 已規定不比較時鐘，這一點不是新問題。
- ADR-0028 的 `is_final` 只定義 bars 的定案。announce 沒有定案概念。

### 3. R-11 讀端輪詢機制，以及能否比照

R-11 是風控 2026-10-18 的逐字條文（`work/reviews/2026-10-18-ADR-0027剩餘待決項與v0.13提案審查-風控.md:141-151`），已落入 ADR-0027 D-3「晚到資料的觸發」（ADR 行 494-513，經 N-20、N-21、N-29 修訂）。要點：

- 誰偵測：每日結算排程（缺日稽核之後）與每次更正作業啟動時，呼叫單一函式 `scan_late_market_bars()`。它只經 `MarketPanelReader` 新增的唯讀方法 `ok_bars_runs_between(run_id_exclusive, run_id_inclusive)` 讀市場 DB，一條 SQL。寫端不動（行 495）。
- 掃描範圍：先經 `market_run_regression()` 取一次 `run_max`，範圍 `(W, run_max]`。W 是最近一個已有 `forecast_correction_job_end` 列的作業記下的 `market_scan_to`，首次為 0。只取 `kind='bars'`、`status='ok'`、`session_date IS NOT NULL`，再過 `is_final`（行 506）。
- 配對：鏈尾列 `status ≠ resolved`，結算窗 [T, T+h] 含 `session_date`，該標的在該 run 有一列，而且 `run_id > settle_source_run_max`（行 507）。
- 觸發項：`{kind: source_revision, run_id, recorded_at, session_date}`，身分以 `(run_id, recorded_at)` 成對，掃描範圍首尾相接不重疊（行 509）。
- 還原保護：W 大於目前 `MAX(run_id)` 時視為市場 DB 被還原，不產生觸發、W 不前進、揭露下限（行 512）。
- 預期量：因為 `_already_ok_today`，bars 的 `void_late_data_count` 預期接近 0（行 511）。同一個冪等略過，在 announce 也成立。

**能比照的部分**：W 與 `market_scan_to` 的首尾相接、`settle_source_run_max` 的序號比較、還原保護、「只讀、不由人工觸發」、觸發身分去重。

**不能直接套的部分**：
- bars 配對只問「這個 symbol 在新 run 有沒有一列」，announce 要問「新 run 的同 key 那一列與判定視圖內的版本相不相同」。
- 因此必須讀兩個 run 的列內容，不能只讀 run 表。
- 還要定義「判定視圖內的版本」是哪一份（見第 5 點）。

### 4. 現有讀取路徑與 ADR 條文

**現有讀取路徑**：
- PIT 視圖：`MarketPanelStore.load_panel_frames`（`market_panel.py:862-945`）。
- 除權息框架載入：`_load_dividend_frame`（:1031-1064），只選 `symbol, ex_date`，排除 `ex_date IS NULL`，每個 ok 與非 ok run 都載入，由 `panel.py` 的 ok 過濾（:584-590）篩選。
- 語意是所有可見 ok run 的聯集：`ex_dividend_announcements()`（`app/data/panel.py:853-856`）回傳 `drop_duplicates` 後的 `(symbol, ex_date)`。被撤銷或改期的舊事件仍留在聯集裡，所以「聯集裡有哪列」不能等同「現行公告」。
- 回看範圍：只多帶一個 `start` 之前最近的 ok run（`market_panel.py:883-905`），不是完整歷史。
- 唯讀端另有 `MarketPanelReader.dividend_announce_observations`（:1123-1156，SQL :295-304）：只回 `(run_id, recorded_at, symbol, ex_date)`，依 `recorded_at` 日期與代號過濾，docstring 規定持倉鏈不得呼叫。
- 還原：`app/dividends/adjust.py::back_adjust_bars`（:224-285）、`relevant_events`（:194-221）。公式是對每個 `ex_date` 之前的 bar 乘上該事件因子。`adjust_series_pit(bars, events, anchor=T)` 尚未實作。

**ADR-0027 相關條文**（行號為今天讀取時的行號，N 批一直在改檔，參考即可）：
- 行 256：`adjust_series_pit` 在介面清單。
- 行 872：D-4 第 2 點，還原用事件取 `pit_dividend_announce_rows` 的 PIT 視圖。
- 行 881：族群成員經 `adjust_series_pit(anchor=T)`。
- 行 901-904：D-5.1~5.4。
- 行 1291：D-9 第 1 點，市場 DB 讀一次 `R=MAX(run_id)`，只取 `run_id ≤ R`、ok run。
- 行 1348 與 1393：`split_or_reduction_suspected` 與 `dividend_factor_unusable`（含配股）。
- 行 494-513：D-3 晚到資料的觸發；第 6 點（行 510）是 N-17 的出處與「不得以未涵蓋代替」的阻擋字面。
- 行 2095、2110：D-11.4 第 11 點 (h) 的第 4 類 `dividend_factor_corrected`。
- 行 2114：「原因怎麼歸屬」的 N-17 註。
- 行 2130：差異驗證，`window_factors_json` 和前一列不同、兩個 `session_date` 都和前一列相同。
- 行 2131-2139：N-27／N-29 的適用範圍。`status ≠ resolved` 的新列只放行 (甲)、(乙) 兩支，其餘一律拒絕。
- 行 2148：`[dividend_factor_corrected]` 一律 FAIL_CLOSED。
- 行 2112：作廢列不因補到資料而 supersede，補到資料進 `forecast_void_late_diag`。
- 行 2646、2706：FL 測試格，以及 `dividend_factor` × 三 scope 在 N-17 落地前標「未涵蓋，不計」。

### 5. 偵測方案草案（給 tech-architect）

這一節全是【推論】，我對資料行為的假設已標【待查】。

**誰偵測**：比照 R-11，同一個排程點與同一個更正作業啟動點，新增唯讀函式 `scan_dividend_factor_revisions()`，與 `scan_late_market_bars()` 並列、共用同一個 W 與 `market_scan_to`、同一套還原保護。寫端不動。這樣掃描範圍不另起一套水位。

**讀什麼**：`MarketPanelReader` 新增兩個唯讀方法，各自一條 SQL，不開新連線：
1. `ok_dividend_runs_between(run_id_exclusive, run_id_inclusive)`：回傳 `run_id, session_date, recorded_at, content_hash`，條件 `kind='dividend_announce'`、`status='ok'`、`content_hash IS NOT NULL`、`session_date IS NOT NULL`。此外要多帶一筆基準：`run_id ≤ W` 的最近一筆 ok run，否則範圍內第一筆沒有前一版可比。
2. `dividend_announce_rows_for_hashes(content_hashes, symbols)`：用 `json_each` 帶代號集合（比照 `_ANNOUNCE_OBSERVATIONS_SQL`，:295-304，固定參數數量），回傳 `content_hash, key, symbol, ex_date, raw_json`。快速路徑是 `content_hash` 相同就不讀列。

**配對鍵**：事件身分 ＝ `(symbol, 原始 Date 字串)`（即現有 `key`）。因子投影 ＝ 經 `parse_dividend_row` 同一套解析後的 `(Exdividend, CashDividend, StockDividendRatio)`，Decimal 比較，不比字串。改期用「同 symbol 恰好一消一增」的推定，且在觸發項標明是推定。

**哪個版本是「判定視圖內的版本」**（TA 必須明定，這是最大的設計點）：
- 對鏈尾列（個股或族群成員 s）窗內的每個事件 key，取 `run_id ≤ settle_source_run_max` 之中、含此 key 的最新一筆 ok run 的那一列，當「判定時版本」。
- 因為預告表在除息日後不再列該事件，窗內事件的最後可見版本通常早於 T。這與聯集語意不同，要在條文裡寫清楚「取最新含此 key 的 run，不取聯集」。

**晚到判定**（序號）：run `r` 對鏈尾列是「因子修訂」觸發，當且僅當三項都成立：
- `r.run_id > settle_source_run_max`，而且 `r.run_id ≤ run_max`；
- `r` 含該事件 key，或者包含改期／撤銷的推定（見上），而且其因子投影與判定時版本不同；
- 事件除息日落在結算窗 [T, T+h] 內，或落在 (T+h 的 bars 補算所需之) 前收日 `ex_date−1` 涉及的範圍。最後一項的邊界請 TA 定，見下方限制 d。

**觸發項**：`{kind: dividend_factor_revision, run_id, recorded_at, session_date, event_key, change: cash|stock_ratio|flag|ex_date}`。身分仍是 `(run_id, recorded_at)` 成對，加 `event_key`，一個 run 可能對多個事件。去重、首尾相接的驗證比照第 5 子點。

**與 supersede 的接點**：
- 歸屬：鏈尾列 `status = resolved` → 觸發類別 `dividend_factor_corrected`，走 D-11.4 (h) 既有的差異驗證（行 2130）：`window_factors_json` 必須不同、兩個 `session_date` 不變。
- 鏈尾列 `status ≠ resolved` → 進 `forecast_void_late_diag` 的 `dividend_factor`（行 2112、471-478），不 supersede。
- 偵測只負責產生觸發。是否真的改了 `window_factors_json`，由更正作業用同一個 `scoring.py` 函式重算決定（行 2122「重算後沒有任何欄位改變的筆不寫入」）。這避免「announce 欄位變了但因子沒變」被誤 supersede，例如 Name 變了。

**做不到或需要來源端資料的地方**：
- a. 同一 session 內的修訂看不到（每 session 只留第一筆 ok run）。若要補，要改 `pit_snapshot` 的冪等略過（連動 N-16 與 ADR-0012 修訂，要 CEO 核可）。在那之前 §4.2 必須揭露解析度為「每個 session 一份」。
- b. 除息日之後的事後更正（實際權值重算、前收更正）不在預告表。需要另一個資料源，例如交易所發布的除權息結果表。這是資料源選型，屬 TA 與 CEO，不是我能決定的。我也無法在目前環境驗證該來源是否存在，因為網路不可用。
- c. 預告表本身不保證在除息日當天或之後仍列出該事件，我沒有資料。這決定了「消失」該歸為過期還是撤銷。
- d. 前收（`ex_date − 1` 的 bar）被更正屬於 bars 的晚到，不在 announce。R-11 第 3 子點配對要求 `session_date` 落在 [T, T+h]，但 `ex_date − 1` 可能早於 T（例如 `ex_date = T`）。這個邊界缺口請 TA 一併處理（擴大配對窗，或明定不涵蓋並揭露）。
- e. key 撞號（同 symbol 同日兩事件）無法偵測，目前是靜默覆蓋。建議 TA 要求寫端或讀端以 `row_count` 對實際寫入列數做對照；這屬寫端改動，要 ADR 修訂。
- f. 因子由可用變成不可用（例如新增配股比）時，鏈尾列若是 `resolved`，新列的 `status` 會變成作廢（`dividend_factor_unusable`）。但 N-27／N-29 的 (甲)、(乙) 兩支（行 2131-2139）沒有涵蓋這一種，會被拒絕並計入 `rejected_count`。這是 N-17 與 N-27 的交界缺口，請 TA 決定是否新增 (丙) 支，或明定不 supersede 並揭露。
- g. 所有 announce 的 `status` 非 ok 的 run（failed）不計入。連續 failed 造成的缺日由既有缺日機制處理，不屬 N-17。

## 三、驗證

- 做過：Grep 與 Read `market_panel.py`（:1-340、:440-670、:850-1170）、`pit_snapshot.py`（:100-280）、`twse_snapshot.py`（:255-470）、`dividends/providers.py`、`dividends/models.py`、`dividends/adjust.py`、`data/panel.py`（:575-635、:845-870）、ADR-0027 的 D-3／D-4／D-5／D-9／D-11.4 相關段、風控 R-11 逐字（review 檔 :141-151）、既有 10-18 前置查證檔、fixture `tests/fixtures/twse_openapi_twt48u_all.json`（讀的是欄位結構，不是 DB）。
- 確認不存在（Grep）：`adjust_series_pit`、`AdjustedSeries`（`apps/` 零命中）、`app/forecast`、`app/outlook`（目錄不存在）、`scan_late_market_bars`、`ok_bars_runs_between`、`dividend_factor_corrected`。
- 沒做：沒有跑任何程式或測試，沒有看市場 DB 任何內容或筆數，沒有實測 TWT48U_ALL 在除息日當天／之後的行為（無網路），沒有 scratchpad 實驗（本次不需要）。
- 事實與推論的邊界：第 5 點的方案、改期的推定、`session_date` 與除息日的過期分界，都是【推論】或【待查】。

## 四、下一步

1. **tech-architect**：以第二節第 5 點為底提案，需要明定：
   - (i) 判定時版本取「最新含此 key 的 run」而非聯集；
   - (ii) 修正、新事件、改期、撤銷、過期各自的歸屬，以及「空白到有值」歸 `dividend_factor_corrected` 還是 `forecast_void_late_diag`；
   - (iii) 限制 d（`ex_date − 1` 的 bars 配對窗）；
   - (iv) 限制 f（因子由可用變不可用時 supersede 的 (丙) 支）；
   - (v) 限制 a、b 要不要升 CEO（改冪等略過、另找資料源）；
   - (vi) §4.2 的解析度揭露字面。
2. **風控**：TA 提案後單項確認。提案成立前，維持 ADR 現有的 `dividend_factor` ×「未涵蓋，不計」，以及 N-17 作為 D-9 結算程式實作前的阻擋項。
3. **我（data-engineer）**：TA 提案定案後，可以起草兩個唯讀方法、`scan_dividend_factor_revisions()` 的讀端查詢，以及離線 fixture 測試（含：同 key 現金股利變、空白補值、配股比新增、改期、消失、同 session 兩版、撞 key、還原保護）。這之前我不動手。
4. **CEO（可能要）**：限制 b（除息日之後的事後更正需要另一個資料源）若 TA 認為要涵蓋，是付費或選型決策，我會列方案與成本再升級。

涉及的檔案（皆為絕對路徑）：
- /home/user/AICompany/apps/stock-desk/backend/app/data/market_panel.py
- /home/user/AICompany/apps/stock-desk/backend/app/services/pit_snapshot.py
- /home/user/AICompany/apps/stock-desk/backend/app/data/providers/twse_snapshot.py
- /home/user/AICompany/apps/stock-desk/backend/app/data/panel.py
- /home/user/AICompany/apps/stock-desk/backend/app/dividends/providers.py
- /home/user/AICompany/apps/stock-desk/backend/app/dividends/models.py
- /home/user/AICompany/apps/stock-desk/backend/app/dividends/adjust.py
- /home/user/AICompany/docs/adr/0027-stock-desk-預測紀錄帳-儲存-PIT輸入-排程與定義登記.md
- /home/user/AICompany/work/reviews/2026-10-18-ADR-0027剩餘待決項與v0.13提案審查-風控.md
- /home/user/AICompany/work/reviews/2026-10-18-V14-03規章與缺bar機制及因子修訂前置查證-data-engineer.md
- /home/user/AICompany/work/dispatch/2026-10-17-後續追蹤清單.md

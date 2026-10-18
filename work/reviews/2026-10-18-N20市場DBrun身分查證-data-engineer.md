# N-20 市場 DB run recorded_at 查證

- 審查者：data-engineer
- 日期：2026-10-18
- 轉存：coordinator，逐字轉存 subagent 最終回報

---

## 一、本次結論

前提大致成立，不必改市場 DB 的 schema。以 `(run_id, recorded_at)` 做「同一筆 run」的身分比對，在 ADR-0026 D-9.4 還原後能偵測重號。成立的範圍有兩個限制：

- 身分比對只能用「原字串相等」。`recorded_at` 在 run_id 上不是單調的，不能拿來排大小（見第二節 2）。
- 我找到一個 D-9.4 備份順序的洞，會造成永久誤報（見第二節 4）。

不需要為市場 DB 另出 ADR。N-20 的欄位與判定規則寫進 ADR-0027 的修訂即可。D-9.4 備份順序要補一條規定，歸 devops-sre 的 ADR-0026 修訂。

## 二、各部門回報（data-engineer）

### 1. run 表結構（事實）

表名是 `pit_snapshot_runs`，所有 kind（bars／listing／classification／dividend_announce）共用，不分 kind、不分 status。ADR-0027 的 `MAX(run_id)` 讀的就是這張表（ADR-0027 :432、:1090）。

| 欄位 | 型別／限制 |
|---|---|
| `run_id` | `INTEGER PRIMARY KEY AUTOINCREMENT` |
| `kind` | TEXT NOT NULL，有 CHECK |
| `session_date` | TEXT，可為 null |
| `recorded_at` | TEXT NOT NULL，沒有 CHECK、沒有 UNIQUE、沒有索引 |
| `source` | TEXT NOT NULL |
| `status` | TEXT NOT NULL，有 CHECK |
| `row_count` | INTEGER NOT NULL |
| `expected_count` | INTEGER，可為 null |
| `content_hash` | TEXT，可為 null |
| `reason` | TEXT，可為 null |

- DDL 在 `apps/stock-desk/backend/app/data/market_panel.py:121-134`。ADR-0012 :267 也把 `run_id` 列為規範性的「單調遞增、永不重用」。
- 時區與精度：
  - 預設 clock 是 `datetime.now(UTC)`（`market_panel.py:430`）。
  - 寫入的是 `recorded_at.isoformat()`（`:519`、`:664`）。
  - 所以是 UTC-aware 的 ISO8601 字串，Python 微秒精度。
  - **`isoformat()` 在微秒為 0 時省略小數**。我在 scratch 實測：同時存在 `2026-10-01T14:10:00+00:00` 與 `2026-10-01T14:10:00.000005+00:00` 兩種長度。
- 寫入者只有兩個函式，都在 `MarketPanelStore`：
  - `record_run`：`market_panel.py:466-557`，`recorded_at = self._clock()` 在 `:499`，INSERT 在 `:509-527`。
  - `record_symbol_backfill`：`:633-689`，`recorded_at` 在 `:653` 取一次，INSERT 在 `:657-666`。
  - `recorded_at` 不是參數，有測試鎖住（`tests/test_market_panel_store.py:236-259`）。
- 只有 `pit_snapshot.py` 呼叫 `record_run`（`app/services/pit_snapshot.py:139,166,206,251`）。
- `app/forecast/` 目前不存在，所以 r_now 的 reader 還沒實作。

### 2. `recorded_at` 是否只增不改（事實）

不改：成立。

- 全 app 沒有對 `pit_snapshot_runs` 的 UPDATE／DELETE（grep 只有 market_panel.py 自己）。
- 表上有 `pit_snapshot_runs_no_update` 與 `_no_delete` 兩個 BEFORE trigger，`RAISE(ABORT,'append-only')`（`:217-236`、`:459-462`）。
- trigger 由 `CREATE TRIGGER IF NOT EXISTS` 建立（`:228-235`），啟動時只建、不驗證存在。有檔案存取權的人可以 DROP trigger；這是自律層級的保護。
- 測試覆蓋 UPDATE／DELETE 被擋（`tests/test_market_panel_store.py:125-128`）。
- scratch 實測：trigger 兩個都在。

只增（隨 run_id 單調）：**不成立**。

- `recorded_at` 取在 `:499`，比 `connect`／交易早。兩個 `record_run` 並行時，先取 clock 的可能後 commit，結果是 `run_id` 較大但 `recorded_at` 較小。
  - 目前 scheduler 單行程，這個機率低，但程式沒有保證。
- 用牆上時鐘，沒有單調保護。NTP 往回調或主機時鐘校正，後面的 run 的 `recorded_at` 就會小於前面的。
- 同值：
  - 可能兩個 run 同一 `recorded_at`。
  - `record_symbol_backfill` 一次呼叫寫多個 run（每個交易日一個），共用同一個 `recorded_at`（`:653,664`）。這是設計行為。
  - scratch 實測：固定 clock 下 run 1、2 的 `recorded_at` 完全相同。
  - 正式 clock 下，不同交易的 `record_run` 同一微秒的機率低，但沒有 UNIQUE 擋。
  - 暖身 CLI 在 D0 之後拒絕執行（`:728-735` 的 docstring 註明）。

結論：`recorded_at` 在同一個時間線內不被改寫，但不是單調、也不是唯一。身分比對只能用「同一個 `run_id` 之下，原字串相等」；不能用大小比較，也不能拿 `recorded_at` 當鍵。

### 3. D-9.4 還原時的行為

實測是在 scratch 空 DB（用 `MarketPanelStore` 建在 `/tmp/claude-0/-home-user-AICompany/3f76d891-50d3-55e1-b39d-925b8a90241a/scratchpad/n20/`，腳本在 `.../scratchpad/n20_probe.py`）。流程是寫 3 個 run、`Connection.backup`、再寫 2 個 run（4、5）、整檔換回備份、再寫 1 個 run。沒有碰任何真實 DB。

- 事實（實測）：
  - AUTOINCREMENT 的序號存在 `sqlite_sequence`，是一般表。
  - `Connection.backup` 是頁複製，序號跟著回到備份時點（seq = 3）。
  - 還原後新 run 拿到 `run_id = 4`，和遺失時間線的 run 4 重號。
  - 重號的兩筆 `recorded_at` 不同：遺失時間線 `2026-10-02T14:10:00.123456+00:00`，新時間線 `2026-10-03T14:10:00.000999+00:00`。
  - 所以 `run_id` 單看會重號，`(run_id, recorded_at)` 能區分。
- 【推論】對應 ADR-0027 :1106 的【推論】標記，現已實測支持。但實測的是 `Connection.backup` 到新檔，不是 devops-sre 的完整程序（含 WAL 檔處理），所以仍標為【推論】。
- 「還原後 `run_id` 接續還原檔的序號」成立。ADR-0012 :267 的「永不重用」只在單一檔內成立。還原會破壞它，所以身分比對才有必要。
- 失敗的 INSERT 在 rollback 時，序號也一起 rollback。所以序號不會有洞，備份時 seq = `MAX(run_id)`（沒有 DELETE，trigger 擋）。【推論，依 SQLite 交易語意，未單獨實測】

偵測規則的涵蓋情形：

| 還原後狀況 | 偵測結果 |
|---|---|
| 參考 `run_id` 大於還原後的 `MAX(run_id)` | 查不到該 run，或 r_now 小於參考值，守衛成立 |
| 參考 `run_id` ≤ 還原後 `MAX`，但已是重號的新 run | `recorded_at` 不同，守衛成立（大小比較偵測不到這種） |
| 參考 run 是備份內的同一筆（正常 D-9.4 整組還原） | 身分相符，守衛不成立 |
| 重號的兩筆在同一微秒寫入 | 漏報，要兩個時間線的同號 run 在同一微秒寫入，實務上不可能；固定 clock 的測試環境除外 |

### 4. 發現的風險（事實加推論）

**ADR-0026 D-9.4 的備份順序會造成永久誤報。**

- 依據：ADR-0026 :342 寫的是「主 DB 與市場 DB 在同一時點各做一份 `Connection.backup`」。這是兩次獨立的備份，不是跨檔原子。
- 推論：
  - 如果市場 DB 先備份、主 DB 後備份，主 DB 備份可能含有引用市場 run N+1 的 `forecast_settle_eval.market_run_max`，而市場 DB 備份沒有 N+1。
  - 整組還原後，參考 run N+1 不存在，守衛成立。
  - 之後市場 DB 寫出新的 N+1，它的 `recorded_at` 和參考列所存的不同，守衛仍然成立，永遠不自行解除。
- 要求：備份順序規定為「先主 DB、後市場 DB」，這樣市場 DB 備份必定涵蓋主 DB 備份所引用的 run。這個規定要寫進 ADR-0026 D-9.4 與 manifest 檢查（manifest 已記 `最新市場 DB run_id`，ADR-0026 :343）。這條屬 devops-sre。

### 5. 最小補法

**必要：無，市場 DB 不需要加欄位、改精度或加唯一鍵。**

- 加唯一鍵不可行：`record_symbol_backfill` 設計上就會有同值。
- 改精度也不必要：微秒已足夠。

**實作約束（寫進 N-20 範圍，不需改 DDL）：**
1. 比對用原字串相等（SQL 的 `recorded_at = :stored`），不解析、不排序。理由：`isoformat()` 在微秒為 0 時長度不同，且 `recorded_at` 在 `run_id` 上不是單調。
2. `forecast_settle_eval.market_run_max_recorded_at` 與 `forecast_correction_job.market_scan_to_recorded_at` 要存「該次讀 R 時，同一次查詢讀到的 `recorded_at` 原字串」。reader 在同一個唯讀交易內一次取得 `MAX(run_id)` 與它的 `recorded_at`，不能分兩次讀。
3. reader 要處理市場 DB 為空（`MAX` 為 NULL）與 W = 0（ADR-0027 :426「首次為 0」，沒有對應的 run）：這兩種情形沒有參考 run，身分比對略過，不算不符。
4. 讀取方法放在 `market_panel.py`（env 字串與 DB 存取只在該檔，C-8），例如 `run_identity(run_id) -> (kind, session_date, recorded_at) | None`。

**選用加強（零 schema 成本）：** 身分一併比對 `kind` 與 `session_date`。這兩欄同樣不可改（trigger），可在極端情況（兩條時間線同一微秒）多一層保險。

**是否需要 ADR：**
- 市場 DB 端：不需要，沒有 schema 變動。
- ADR-0027：N-20 的新欄位與判定規則要走 tech-architect 的 ADR 修訂，這是他已規劃的範圍。「`recorded_at` 隨 `run_id` 單調」不得列為前提，建議把第二節 2 的結論寫入。
- ADR-0026 D-9.4：補「備份順序先主 DB、後市場 DB」，歸 devops-sre，同批送風控。

## 三、驗證

- 讀過：
  - `market_panel.py:1-760`（DDL、trigger、`record_run`、`record_symbol_backfill`）。
  - `tests/test_market_panel_store.py`（相關 grep）。
  - ADR-0012 :267；ADR-0026 :342-352；ADR-0027 :426-432、:1098-1109。
  - tech-architect 回覆檔第二節第 3 項。
- 實測（scratch 空 DB，用 `.venv` 的 Python 執行，程式碼的 migration 建表）：
  - 同瞬間兩 run 的 `recorded_at` 相同。
  - `isoformat` 省略零微秒。
  - 兩個 trigger 存在。
  - `sqlite_sequence` 與 backup 還原後的重號：備份後 seq = 3，還原後新 run = 4，與遺失時間線的 run 4 重號，`recorded_at` 不同。
- 日期、grep 結果、行號都是 2026-10-18 的工作樹。
- 未做：
  - 沒有讀 `.env`。
  - 沒有開 `apps/stock-desk/backend/data/*.db`（連 stat 都沒做）。
  - 沒有改任何專案檔案。
  - 沒有驗證並行 `record_run` 的實際交錯（第二節 2 的並行情形是依程式結構的推論）。
  - 沒有驗證 WAL 檔在完整還原程序中的處理。

## 四、下一步

1. **tech-architect**：
   - N-20 改採「原字串相等」。
   - 刪去 `recorded_at` 單調的任何隱含假設。
   - 補第二節 5 的實作約束 1～4。
   - 決定是否採用 `kind`／`session_date` 加強。
2. **devops-sre**：
   - ADR-0026 D-9.4 補備份順序（先主 DB、後市場 DB）。
   - 確認誤報時的解除程序，因為身分不符不會自行解除。
   - 驗證完整還原程序（含 WAL）的序號行為。
3. **qa-reviewer**：測試要有「還原後重號、`recorded_at` 不同」與「備份順序顛倒」兩格；兩格都用假 clock 與 scratch 空 DB。

相關檔案：
- /home/user/AICompany/apps/stock-desk/backend/app/data/market_panel.py
- /home/user/AICompany/apps/stock-desk/backend/tests/test_market_panel_store.py
- /home/user/AICompany/docs/adr/0012-stock-desk-族群動能與全市場日線.md
- /home/user/AICompany/docs/adr/0026-stock-desk-庫存版本化軟刪除與還原點.md
- /home/user/AICompany/docs/adr/0027-stock-desk-預測紀錄帳-儲存-PIT輸入-排程與定義登記.md
- /tmp/claude-0/-home-user-AICompany/3f76d891-50d3-55e1-b39d-925b8a90241a/scratchpad/n20_probe.py

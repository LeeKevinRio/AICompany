# NM-5 儲存層程式碼審查

- 審查者：qa-reviewer
- 日期：2026-11-14
- 轉存：coordinator，逐字轉存 subagent 最終回報

---

## 本次結論
**程式碼審查結論：PASS（BLOCKING_ISSUES=false）。** 範圍是 NM-5 第一批儲存層，head `bc07110`。
- 本次沒有重現任何測試。實作者回報的 10487 passed 與覆蓋率 97.68% 我沒驗證。
- 6 項 BLOCKING 判準都成立（逐項見「驗證」）。
- 有 1 項 medium（PIT 防線少一道檢查），建議在接線 PR 之前補。其餘列「凍結後待辦」。
- Codex 第二意見：`codex --version` 回 `command not found`，**單家審查**，沒有跨廠商意見。

## 各部門回報（qa-reviewer，依檔案）

### app/forecast/store.py
- **[PIT][medium] `_check_snapshot`（約 625–642 行）沒有檢查 bar 的時間戳不晚於擷取時間或 `created_at`。**
  - 它只檢查三件事：`captured_at <= created`、最後一根是 T、每根 `is_final`。
  - `is_final` 只擋太早（早於 15:00），不擋太晚。
  - 一份快照裡若有 `fetched_at` 或 `as_of` 在未來（時鐘錯亂或上游 bug）的 bar，仍會通過。
  - 它會被當成「定案」，並且寫進 `inputs_max_fetched_at`，也就是 D-2 第 4 點的 PIT 證明欄位。
  - 這違反 D-3 第 4 點「`captured_at ≤ created_at`」的精神，因為 bar 的取得時間必須不晚於它被擷取的時間。
  - 建議：在 store 驗證 `max(fetched_at) <= captured_at`。可再於 schema 加 `CHECK (inputs_max_fetched_at <= created_at)`，兩者格式相同，字串比較即可。
  - 建議實證：快照內一根 bar 的 `fetched_at` 比 store 時鐘晚 1 小時，`write_record` 應拒絕且不寫列。
- **[Edge case][low] `put_input_series` 同內容去重（359–381 行）。**
  - 相同 bars 但不同的 `source_status`、`reason`、`dropped_rows`、`staleness_minutes` 會被默默丟棄，只留第一次的列。
  - `test_a_snapshot_is_stored_once_per_content` 把這個行為釘住。
  - 因為 bars 已含 `source` 與 `fetched_at`，實際上很難碰撞。
  - 凍結後待辦：中繼資料不同時要嘛拒絕，要嘛文件明講「首次寫入為準」。
- **[Edge case][low] `write_record` 不核對 claim 是否為「記錄中 claim」（最後登記者）。**
  - 一個已被取代的 claim 仍可繼續寫新紀錄。
  - 這屬於 recorder 的 CG-2 職責，本批沒有 recorder。
  - 凍結後待辦：recorder 批要有測試。
- **[可維護性][low] `register_claim` 的 `rules_logic_sha256` 只檢查是 hex，沒有衍生或核對。**
  - 它由 claims CLI 批決定怎麼算，凍結後待辦。
- **[可維護性][low] `final_sessions` 每次都讀全部快照的 `bars_json`。**
  - 資料量小，沒有影響，之後 `report` 若頻繁呼叫再處理。

### app/forecast/schema.py
- **[Edge case][low]** `_ledger_objects`（約 232–245 行）用 `substr(name,1,9) = 'forecast_'` 比對前綴，區分大小寫。
  - SQLite 的表名不分大小寫，所以 `CREATE TABLE Forecast_audit` 逃過 K-5 的偵測。
  - 建議：改成 `lower(name)` 比對。
  - 建議實證：新增 `Forecast_x` 表後，`schema_status(...).complete` 應為 False。
- **[Edge case][low]** `late_cutoff_at` 在 DB 層沒有綁定 `data_as_of`。
  - 只有 `late = (created_at >= late_cutoff_at)` 這道 CHECK，所以非 store 的寫入者可以填一個很晚的 cutoff 讓 `late = 0`。
  - 台北沒有 DST，可用 `strftime` 對應 T 日 16:00 UTC，但這等於把時區寫進 DDL。
  - 與 SP-1 同類（繞過 store 本來就能亂寫），列待辦，並請 tech-architect 在裁示 SP-1 時一併判斷。

### app/forecast/canonical.py、app/data/session_calendar.py
- 沒有發現問題。
  - `canonical_price` 不經 28 位捨入，拒收 float，`17000.50` 與 `17000.5` 等值。
  - 時間戳一律轉 UTC 並含微秒。
  - `code_digest` 用「路徑加正規化內容雜湊」的清單，所以新增、改名、改內容都會讓雜湊改變。
  - CRLF 與 CR 先統一成 LF，`__pycache__` 排除。
  - `is_final` 取 `min` 時間戳，比對 `policy_for(market)` 的 cutoff 與 timezone，沒有複製數值。無 stamp、None、naive 時一律 False。

### tests
- **[可維護性][low] 幾個測試沒有鑑別力。**
  - `test_the_timestamp_fixture_is_store_format`（schema 測試末段）只比對常數的長度。
  - `test_timestamps_round_trip_exactly`（canonical 測試末段）是 Python 標準庫行為。
  - 兩者都無害，但不算實證。
- **[可維護性][low] `test_the_reachability_scan_has_teeth` 只證明 scheduler 能到達 `app.data`。**
  - 它沒有證明 forbidden 套件的偵測能抓到東西，而 forbidden 套件的 import 掃描另有獨立的 teeth 測試，所以不影響結論。
- **[建議實證]** 「`create_schema` 在 `app/` 內除 `schema.py` 外沒有任何呼叫者」目前只靠 `test_forecast_gate_closed` 與 store 的 SQL 掃描間接保證。
  - 可加一條測試：AST 掃 `app/**`，非 `schema.py` 的檔案不得引用 `create_schema`。
  - 這會把「沒有接線」直接釘住，列凍結後待辦。

## 驗證（逐項，皆為讀碼）
1. **沒有接線：成立。**
   - `git diff --name-only` 對 `app/main.py`、`app/scheduler.py` 沒有輸出，零 diff。
   - `create_schema` 在 diff 中只被測試 helper 呼叫。
   - `store.py` 沒有 CREATE，由 AST 測試釘住，並有 `test_the_store_creates_no_schema` 與 `test_writes_are_refused_on_an_incomplete_schema`。
2. **5 張表的 trigger 與 CHECK：成立。**
   - `TABLES` 迴圈為每張表產生 BEFORE UPDATE 與 BEFORE DELETE（沒有 WHEN），有測試逐表驗證。
   - `validation_status = 'unverified'`、`kind = 'forward'`、`trigger = 'scheduled'`、`series_kind = 'index_bars'`、`scope = market/TAIEX`、`horizon IN (3,5)` 都在。
   - `late = (created_at >= late_cutoff_at)`：兩邊同為 UTC 微秒固定格式，字串比較正確，臨界有測。
   - insufficient 與 `missing_json` 非空互為若且唯若，且 `band_def` 的 `up_pct`、`down_pct` 為 null（`has_keys` 用 `json_type IS NOT NULL`，所以允許 JSON null）。
   - `test_column_checks` 的正反例涵蓋這些約束。
3. **雜湊涵蓋範圍：成立。**
   - `content_sha256` 是正規化 `bars_json` 的 sha256，涵蓋九個鍵逐根，同內容同雜湊、任一值改變即改變。
   - `record_content_hash` 排除 `forecast_id`、`run_id`、`created_at`、`late` 與自身，其餘全含（含 `late_cutoff_at`），與 D-2 第 4 點一致。測試逐欄驗證。
   - `code_digest` 涵蓋 forecast、outlook、dirdef 與 `data/session_calendar.py`，與 D-2 第 1 點一致。不含 rules yaml 的決定合理，因為規則位元組在 `rules_bytes`，雜湊在紀錄的 `rules_sha256`。
4. **`is_final` 與時區：成立。**
   - 語意與 D-3 第 2 點、CS-17 一致（較早的 stamp 不早於 cutoff）。
   - `late_cutoff_at` 用 `TW_POLICY.timezone`，`is_final` 用 `policy_for(market)`，新檔沒有寫死 "Asia/Taipei" 或 15:00。
5. **hindsight 來源：成立。**
   - `test_forecast_hindsight_sources.py` 掃 forecast、outlook 全部 `*.py` 與 `session_calendar.py`。
   - 它檢查三個識別字（含註解與字串）、直接 import、動態 import（`__import__`、`importlib`）與可達性，每一項都有 teeth 測試。
   - `test_forecast_boundaries` 的模組清單也已更新。
6. **測試用 `tmp_path`：成立。**
   - 資料庫用 `tmp_path` 或 `:memory:`，沒有碰 `data/*.db`，也沒有讀 `.env`。
- **SP-1 實證如實，不判 BLOCKING。**
  - 預設連線改寫紀錄：`test_insert_or_replace_rewrites_a_record_on_a_default_connection` 直接斷言 label 變成 `bearish`。strict xfail 把漏洞釘住，修好時會翻紅，這個設計合理。
  - 緩解：`_connect` 設 `recursive_triggers = ON`，`test_a_replace_through_the_store_connection_is_refused` 實測被擋。
  - store 的 SQL 不含 REPLACE、UPDATE、DELETE，AST 測試帶 teeth，另有 `test_the_store_never_updates_deletes_or_replaces`。
  - 實作者的描述與程式碼相符，沒有誇大。緩解只及於 store 自己的連線。
- **唯讀權限判準常數：未觸及。**
  - 第一道：本批 diff 的 `--name-only` 清單內沒有 `scripts/validate_agents.py`。
  - 第二道：`git diff --name-only -G"READONLY_AGENTS|READONLY_ALLOWED_BASH"` 無輸出，沒有 shadow 定義，也沒有常數值異動。

## 下一步
1. dev-lead 在接線 PR 之前補上 M1（bar 時間戳不晚於擷取時間的檢查加測試），並順手處理 schema 的大小寫前綴問題。
2. tech-architect 裁示 SP-1，一併判斷 `late_cutoff_at` 要不要在 DB 層綁定。
3. 凍結後待辦：recorder 批要驗證「只寫記錄中 claim」，並釘住 `create_schema` 的呼叫者。去重中繼資料的處理、`rules_logic_sha256` 的來源，交 claims CLI 批決定。
4. 無 UI，本批 PASS 後回報 CEO。接線 PR 的 CG-1、CG-3、CG-4 由 qa-reviewer 另審。

相關檔案（均為 diff 內，位於 `apps/stock-desk/backend/`）：`app/forecast/store.py`、`app/forecast/schema.py`、`app/forecast/canonical.py`、`app/data/session_calendar.py`、`tests/test_forecast_store.py`、`tests/test_forecast_schema.py`、`tests/test_forecast_canonical.py`、`tests/test_forecast_hindsight_sources.py`。

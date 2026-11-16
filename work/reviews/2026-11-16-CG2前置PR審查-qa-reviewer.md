# CG-2 前置 PR 審查

- 審查者：qa-reviewer
- 日期：2026-11-16
- 轉存：coordinator，逐字轉存 subagent 最終回報

---

## 本次結論
程式碼審查結論（未重現 `12050 passed`，我不能跑測試）：**PASS，沒有 BLOCKING 項目。**

- worktree 在正確分支：`store.py:867` 有 `def bootstrap`。審查以 worktree 全文加 `git diff` 為準。
- 差異檔恰好 8 個，與交件一致。
- Codex 在本環境不可用（`codex: command not found`，exit 127），依 CEO #58 記為**單家審查**。
- 沒有 critical 或 high。以下都是低風險項或凍結後待辦。

## 各部門回報（BLOCKING 判準逐條）

**1. 單一交易與回滾：成立**
- `_write(fresh=True)`（`store.py:623-642`）：
  - `_open_connection` 用 `sqlite3.connect(db_path, isolation_level=None)`（`store.py:185`）。
  - 這是**自動提交模式**：Python 不會隱式發出 BEGIN，也不會在 DDL 前後隱式 COMMIT。
  - 交易邊界完全由程式自己的 `BEGIN IMMEDIATE`（`:632`）、`COMMIT`（`:638`）、`ROLLBACK`（`:641`）決定。
  - 因此 DDL 不可能在交易外自動提交。SQLite 的 DDL 本身是交易性的，`create_objects` 前置檢查 `conn.in_transaction`（`schema.py:397`）。
  - PRAGMA（`foreign_keys` 等）在 BEGIN 之前設定（`store.py:186-188`），沒有「PRAGMA 在交易內被忽略」的問題。
- 順序：BEGIN IMMEDIATE → `create_objects`（先檢查無物件，再建 5 表 15 trigger）→ `require_complete_schema` → h3 → h5 → COMMIT（`store.py:632-638, 891-893`）。
- `except BaseException` 在 `in_transaction` 為真時 ROLLBACK 再 `raise`（`:639-642`）。
  - body 內的例外（含 KeyboardInterrupt）經 generator 的 yield 點被捕捉。
  - COMMIT 自身失敗時交易仍在，也會進 ROLLBACK。
  - BEGIN 失敗發生在 try 之前，此時沒有交易，也沒有任何東西被建立。
- 我找不到任何路徑會留下「只有表、沒有登記」或「只有一列」：建表與兩列 INSERT 都在同一個交易，沒有中途 COMMIT。
- 兩次 bootstrap 競爭：後到者等 busy_timeout，之後在交易內看到物件，拋 `SchemaNotEmptyError`，什麼都沒改。
- 輸入驗證（張數、horizon (3,5)、不取代、`_prepare_claim`）都在開連線前（`:883-890`）。

**2. 「無帳本物件」檢查在交易內：成立**
- `create_objects` 在 `conn.in_transaction` 之後才呼叫 `_ledger_objects(conn)`（`schema.py:397-400`）。
- `_ledger_objects`（`schema.py:339-356`）：
  - 查 `sqlite_master`，涵蓋 table、trigger、index、view。
  - 以 `substr(lower(name|tbl_name),1,n)` 比對 `forecast_`、`plan_`，不分大小寫，名稱或所屬表任一命中。
  - 只排除 `sqlite_autoindex_*`，它們必附屬於已被偵測的表。
- 拒絕發生在任何 CREATE 之前，所以什麼都沒建。
- 小注記：名稱不帶前綴、只是引用 `forecast_` 表的 view，不會被抓到。這符合補充七「名稱或所屬表」的字面，不列問題。

**3. 既有行為不變：成立**
- `create_schema` 的名稱與簽章不變，仍是 BEGIN IMMEDIATE → 檢查 → 建立 → COMMIT，失敗回滾（`schema.py:405-420`）。
- `EXPECTED_OBJECTS` 的 diff 零行，只動函式與 docstring。
- `register_claim` 的簽章不變。驗證順序與訊息逐項比對 base，**一致**。
  - `_prepare_claim`（`store.py:562-607`）的檢查順序與 base 相同。
  - 交易內順序仍是：先讀時鐘、再查最大值、再查取代鏈、最後 INSERT（`_insert_claim`，`:918-979`）。
- recorder 走的 `_write()` 預設 `fresh=False`：仍先 `require_complete_schema`，schema 不存在就拒絕並回滾，不建表（`:636`）。

**4. 正式路徑仍無法建表：成立**
- 我用 Grep 掃 `app/`：
  - `create_schema` 在 `app/` 內零呼叫。
  - `.bootstrap(` 零呼叫。
  - `create_objects` 只有 `store.py:635`（在 `_write`）與 `schema.py:415`（在 `create_schema`）。
- `claims.py` 不在 diff 內。
- `_connect` 只由 `_write` 開啟，既有測試 `test_f4_connect_is_opened_only_on_the_write_path` 維持。
- AST 測試有牙齒：`test_the_boundary_scans_have_teeth`（`test_forecast_bootstrap.py:623-637`）對合成原始碼證明掃描會抓到違規。`_fresh_write_sites` 把 `**kw` 也算作帶參數，對 `_write(True)` 也有效。

**5. 時鐘：成立**
- 第一列沒有前一列，直接取時鐘（`store.py:908-909`）。
- 後續列「不晚於」就重讀 store 時鐘，最多 `CLOCK_WAIT_SECONDS`＝1.0 秒，每次 sleep 1 ms（`:910-916`）。
- `registered_at` 只來自 `self._now()`；`time.monotonic` 只用於 deadline（S-2）。
- 仍不晚就拋 `ForecastStoreError`，整筆回滾。
- `register_claim` 傳 `wait_for_later_clock=False`，進迴圈即拋，不等待，訊息與 base 相同。
- 等待期間持有 IMMEDIATE 鎖最多約 1 秒，小於其他寫入者的 busy_timeout 5 秒，可接受。

**6. `provisional_results_seen()`：成立**
- 經 `_read()`（`query_only`）讀取（`store.py:1477-1494`）。
- 依 `registered_at, rowid` 排序（表不是 WITHOUT ROWID，已確認）。
- 值不是 int 0 或 1（含 bool）就拋 `LedgerInconsistentError`。

**7. 零差異清單：成立**
- `git diff --stat` 的 8 個檔案裡，沒有 `claims.py`、harness、helpers、`pipeline_acceptance_real.py`、`uv.lock`、`main.py`、`scheduler.py`、`outlook/rules/**`。
- `registry.py`、`dirdef/__init__.py`、`definition.py`、`definitions.py` 的 diff 只有 docstring。
- 登記表的賦值沒有出現在 diff 內，仍為空。
- docstring 新增句子中，`UnpublishedVersionError` 確實存在於 `definitions.py:82`。

**8. 測試只用 `tmp_path`：成立**
- 新測試檔的資料庫都是 `tmp_path`（`:24, 128-130, 241, 396, 439, 467, 484`），沒有找到 `<backend>/data/` 路徑。
- `APP_ROOT` 只用來讀原始碼做 AST，不碰資料庫。

**兩處與交辦字面不符的判定**
- **(i) `WRITE_METHODS` 加 `"bootstrap"`：不算削弱，予以接受。**
  - 該集合是「允許開寫入交易的方法」上界，用 `<=` 比較（`test_forecast_store.py:1411`）。
  - 同一測試仍斷言 `readers & WRITE_METHODS == set()`（`:1415`），所以 `bootstrap` 不能走 `_read`。
  - `bootstrap` 是新增的寫入方法，不加反而讓測試誤報。
  - 另有 `test_s15_write_fresh_is_only_in_store_bootstrap` 把 `fresh` 釘在 `ForecastStore.bootstrap`，補強了這一項。
- **(ii) 斷言改成「呼叫者恰為 store.py 與 schema.py 內的 `create_schema`」：夠嚴到可接受，但有一處可補強（凍結後待辦）。**
  - 它只在模組層級鎖定 `store.py`，沒有鎖定 `store.py` 內「只有 `_write` 呼叫」。目前實況是只有 `_write`（`store.py:635`）。
  - 補強方式列在下方。這不阻擋合併。

**6 項自定解讀意見**
1. 重讀預算用 monotonic、時間取自 store 時鐘：同意。
2. 重讀也適用於時鐘倒退：同意。倒退超過 1 秒就拋錯並回滾，行為安全。
3. `create_objects` 不在交易內拋 `RuntimeError`：同意。這是程式員錯誤，不是資料狀態。
4. **`bootstrap` 不檢查目標檔存在：同意，但附條件。**
   - 錯路徑的後果是「在別處建一個新的空帳本」，不會碰到正式 DB。
   - 反向風險是：路徑誤指到既有的非帳本 DB（如主資料庫）時，會在它裡面建帳本物件。
   - 因此 CG-2 PR 的 CLI 必須有存在性與路徑檢查，並以測試證明。請 TA 把它列為 CG-2 PR 的驗收條件。
   - 輸入驗證失敗不建檔，已有測試 `test_the_inputs_are_checked_before_any_connection` 證明。
5. **`provisional_results_seen()` 不要求 schema 完整：同意。**
   - 缺表時會拋原始 `sqlite3.OperationalError`，而不是 `LedgerInconsistentError`；對不存在的檔案，`_read` 會建出空檔（既有行為，其他讀取同樣如此）。
   - CG-2 的提交後核對應先確認 `ledger_schema_status` 完整，再呼叫它。
6. `_write` 的 AST 斷言更嚴：同意。

## 驗證
我能確認的有：
- 逐行讀過 `store.py` 檔頭到 `:1300`，以及 `bootstrap`、`_write`、`_insert_claim`、`_later_registration_time`、`provisional_results_seen` 的 diff。
- 讀過 `schema.py` 全部 diff 與 `_ledger_objects`、`create_objects`。
- 讀過新測試的 AST 段（`:510-638`）。
- 用 Grep 對 `app/` 確認呼叫端。

我無法確認的有：
- 全套測試結果。
- 隱式交易行為在 3.12 與 3.13 的實測。這由 `isolation_level=None` 的文件語意保證，但建議實證（見下方）。

**唯讀權限判準常數**
未觸及。
- `--name-only` 的 8 個檔案不含 `scripts/validate_agents.py`。
- 我對該分支後端目錄 grep `READONLY_AGENTS|READONLY_ALLOWED_BASH` 為 0 筆，所以也沒有 shadow 定義。
- 第二道檢查我是用 grep 8 個變更檔所在目錄取代 `git diff | grep`，因為我被限制不得使用 pipe。因為差異檔只有那 8 個，這與原檢查等價。

## 下一步

**建議實證（讀碼無法完全確定，請 dev-lead 或 CI 跑，並貼出輸出）**
1. 拿一份複本在 `_insert_claim` 的第二列 INSERT 前注入例外，之後查詢 `sqlite_master` 是否為空，並比對檔案位元組。
   - 交件稱 `test_s15_a_failure_in_the_transaction_rolls_everything_back` 等已涵蓋。
   - 我要求補一個「真實 SQLite 在 COMMIT 時失敗」的情境，例如把 `sqlite3.Connection` 換成 wrapper 讓 `COMMIT` 拋錯，確認表與列都沒留下。
2. 在 Python 3.12 與 3.13 各跑 `pytest tests/test_forecast_bootstrap.py -k "rolls or fifteen or ddl"`，確認通過。

**凍結後待辦（非 BLOCKING）**
- `test_forecast_bootstrap.py:551-562`：補一條斷言，`store.py` 內 `create_objects` 的呼叫者只有 `ForecastStore._write`。
- 同一測試目前抓不到 `from ... import create_objects as x` 的別名呼叫；可補 import 別名掃描。目前 app/ 內沒有這種寫法。
- `store.py:589-607`：`definition_sha256` 與 `definition_logic_sha256` 現在在驗證 schema 之前計算（base 是在交易內才算）。
  - 這只影響「舊 schema 缺失」加「definition 計算本身拋錯」同時成立時，先出現哪個錯誤。
  - 對 `register_claim` 的正常路徑沒有行為差異，建議在 CG-2 PR 說明一行。
- CG-2 PR 驗收條件：bootstrap CLI 的路徑與存在性檢查，以及提交後核對先驗 `schema_status`（見解讀 4、5）。

**交接**
- 純邏輯與文件類，無 UI：回報 CEO；合併前 CI 須綠燈。
- 請 TA 另行判定 (i)、(ii) 兩點。

**相關檔案（絕對路徑）**
- /home/user/AICompany/.claude/worktrees/agent-aa23ba638139de497/apps/stock-desk/backend/app/forecast/store.py
- /home/user/AICompany/.claude/worktrees/agent-aa23ba638139de497/apps/stock-desk/backend/app/forecast/schema.py
- /home/user/AICompany/.claude/worktrees/agent-aa23ba638139de497/apps/stock-desk/backend/tests/test_forecast_bootstrap.py
- /home/user/AICompany/.claude/worktrees/agent-aa23ba638139de497/apps/stock-desk/backend/tests/test_forecast_store.py

BLOCKING_ISSUES=false

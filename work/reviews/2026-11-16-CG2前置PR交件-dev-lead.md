# CG-2 前置 PR 交件（store 單一交易 bootstrap）

- 審查者：dev-lead
- 日期：2026-11-16
- 轉存：coordinator，逐字轉存 subagent 最終回報

---

## 本次結論
前置 PR 分支 `feat/nm5-cg2-prereq-store-bootstrap` 已完成並 push。它從 `origin/product/stock-desk`（`d44efbb`，含補充七）開出，head 是 `10fbdf9b5f426dfea845a2293124323eadf72351`。補充七第 1～4、6 點與 docstring 修改都已落地。Python 3.12 與 3.13 全套測試都過，沒有失敗。合成資料跑 P-0、P-1 的 harness 都通過。

有兩點跟交辦字面不完全相符，請先過目：
- 我改了一個既有測試的一行：`tests/test_forecast_store.py` 的 `WRITE_METHODS` 白名單加入 `"bootstrap"`。它不是 `create_schema`／`register_claim` 的測試，而是「只有寫入方法可以開寫入交易」的白名單；補充七規定 `bootstrap` 要呼叫 `_write(fresh=True)`，不加這一項，既有測試一定會失敗。這是我自行判斷的，若 coordinator 認為這屬於「必須改既有測試就停下」，請告訴我。
- 「`app/` 中只有 store.py 呼叫 `create_objects`」按字面做不到，因為補充七第 1 點本身就規定 `create_schema`（在 schema.py 內）要呼叫它。測試的斷言改成：呼叫者恰好是 store.py 與 schema.py，而 schema.py 內只有 `create_schema` 呼叫它（第 3 點）。

## 各部門回報（dev-lead）

**Commits**
- `103ff15`：`feat: store 單一交易 bootstrap 與 schema.create_objects（ADR-0030 補充七）`
- `10fbdf9`：`docs: 登記表相關 docstring 改為不依登記狀態的寫法（ADR-0030 補充七第 7 點）`

**變更檔案**
- `apps/stock-desk/backend/app/forecast/schema.py`
  - 新增 `create_objects(conn)`：不在交易內就拋 `RuntimeError`；已有任何帳本物件就拋 `SchemaNotEmptyError`；否則依序執行 `EXPECTED_OBJECTS`。它本身不下 BEGIN、COMMIT、ROLLBACK。
  - `create_schema` 改為 BEGIN IMMEDIATE → `create_objects` → COMMIT，失敗時回滾；名稱、簽章、行為不變。
  - 末段 docstring 改寫。
- `apps/stock-desk/backend/app/forecast/store.py`
  - 新增 `ClaimInput`、`_PreparedClaim`、`_prepare_claim`、`ForecastStore._insert_claim(conn, prepared, *, wait_for_later_clock)`、`_later_registration_time`、`_write(*, fresh=False)`、`bootstrap(*, claims) -> tuple[str, str]`、`provisional_results_seen() -> list[tuple[str, int]]`。
  - 新增常數 `CLOCK_WAIT_SECONDS = 1.0`、`CLOCK_REREAD_INTERVAL_SECONDS = 0.001`。
  - `register_claim` 改走 `_prepare_claim` 加 `_insert_claim(wait_for_later_clock=False)`；簽章、驗證順序、錯誤訊息與交易內的順序（先讀時鐘、再查最大值、再查取代鏈、最後 INSERT）都不變。
  - 模組 docstring 的 "The store does not create the schema" 已改寫。
- `apps/stock-desk/backend/app/dirdef/registry.py`、`app/dirdef/__init__.py`、`app/dirdef/definition.py`、`app/forecast/definitions.py`：只改 docstring，改成不依登記狀態的寫法。去掉 docstring 後做 AST 比對，四檔都與 base 相同；登記表的賦值零差異，仍為空。
- `apps/stock-desk/backend/tests/test_forecast_bootstrap.py`：新檔，52 個測試。
- `apps/stock-desk/backend/tests/test_forecast_store.py`：`WRITE_METHODS` 加 `"bootstrap"`，只有這一行。

**`bootstrap` 的行為**
1. 開連線前先檢查：恰好兩個 `ClaimInput`，horizon 依序是 (3, 5)，兩個都沒有 `replaces_claim_id`，而且兩個都能通過 `_prepare_claim`。任一不成立就拋 `ForecastStoreError`，不開連線、不建檔。
2. 檢查通過後，在 `_write(fresh=True)` 內依序執行：BEGIN IMMEDIATE → `create_objects`（交易內檢查沒有帳本物件，不分大小寫，涵蓋名稱或所屬表）→ `require_complete_schema` → h3 列 → h5 列 → COMMIT。
3. 任何 `BaseException` 都會先 ROLLBACK 再往外拋。

## 驗證

**S-15 與 TA 第 3 節逐條對應（測試都在 `test_forecast_bootstrap.py`，另註明者除外）**
- 第 1 點／(a)：DDL 零差異
  - `test_s15_the_ddl_text_is_unchanged`：釘住 `EXPECTED_OBJECTS` 的 sha256 `efecca9b…6d47`。這個值我先在 base 的 schema.py 上算出，與新檔一致；`git diff` 也只顯示函式與 docstring 的差異。
  - `create_objects` 本身：`test_create_objects_refuses_outside_a_transaction`、`test_create_objects_commits_nothing_itself`、`test_create_objects_refuses_a_ledger_object_before_creating_any`。
- (a)：`create_schema`、`register_claim` 的既有測試一字未改就全過（`test_forecast_schema.py`、`test_forecast_store.py` 等；後者唯一的改動是上述白名單）。
- 第 2、3 點／(d)：
  - 0 與 1 各成功一次：`test_s15_bootstrap_registers_both_claims_with_the_typed_value[False/True]`。同一個測試也核對 schema 完整、`forward_claims` 恰好兩列、`runs()` 為空、`provisional_results_seen` 等於鍵入值、非帳本表內容不變。
  - 6 種既有物件（table、trigger、index、view、`plan_` 表、大小寫不同）各被拒絕：`test_s15_an_existing_ledger_object_is_refused_and_nothing_is_created[...]`。斷言 `sqlite_master` 不變、檔案位元組不變、時鐘一次都沒讀。
  - 回滾，共 5 種情境：`test_s15_a_failure_in_the_transaction_rolls_everything_back`
    - `clock_raises_before_the_second_row`
    - `keyboard_interrupt_before_the_second_row`
    - `keyboard_interrupt_on_the_first_row`
    - `registered_at_does_not_increase`
    - `registered_at_goes_back`

    另外兩個回滾測試：`test_a_failure_after_the_objects_are_created_rolls_them_back`、`test_a_failure_on_the_second_insert_rolls_the_first_row_back`。所有回滾測試都斷言：沒有帳本物件、非帳本表內容不變、主檔位元組不變、資料夾內沒有殘留檔。
  - 恰好 15 個 trigger：`test_s15_bootstrap_leaves_exactly_fifteen_triggers`。
  - 其他：
    - `test_bootstrap_stores_what_register_claim_would`：兩條路徑寫出的登記列逐欄相同。
    - `test_a_second_bootstrap_is_refused_and_changes_nothing`。
    - `test_the_inputs_are_checked_before_any_connection`：9 種情境。
- 第 4 點（時鐘）
  - 先同值、後變晚就成功：`test_s15_the_clock_is_re_read_until_it_is_later`。
  - 一直同值就回滾：`test_s15_a_clock_that_never_gets_later_is_given_up_within_the_wait`、`test_the_wait_is_bounded_in_real_time`。
  - `register_claim` 立即拒絕、不等待：`test_register_claim_never_waits`。
  - 時間只取自 store 時鐘：`test_registered_at_comes_from_the_store_clock`。
- `provisional_results_seen`：`test_provisional_results_seen_is_in_registration_order`、`test_provisional_results_seen_refuses_a_value_that_is_not_0_or_1`、`test_provisional_results_seen_reads_on_a_read_only_connection`。
- 第 6 點／(b)：AST 斷言
  - `test_s15_only_the_store_calls_create_objects`
  - `test_s15_no_app_module_calls_create_schema`
  - `test_s15_no_app_module_calls_bootstrap_in_the_prerequisite_pr`
  - `test_s15_write_fresh_is_only_in_store_bootstrap`
  - `test_s15_the_bootstrap_call_passes_fresh_true`
  - `test_s15_recorder_and_report_call_none_of_the_schema_paths`（recorder、report 各一）
  - `test_s15_schema_holds_no_insert`
  - `test_the_boundary_scans_have_teeth`（證明掃描本身會抓到違規）
  - 「`_connect` 只由 `_write` 開啟」由既有的 `test_forecast_store.py::test_f4_connect_is_opened_only_on_the_write_path` 驗證，照常通過。
- 第 5 點（結束碼）屬 CG-2 PR，本 PR 不做。

**(c) 零差異清單**
- 比對指令：`python3 /tmp/claude-0/-home-user-AICompany/3f76d891-50d3-55e1-b39d-925b8a90241a/scratchpad/check_prereq.py origin/product/stock-desk`。
- 以下檔案全部零差異：
  - `app/forecast/claims.py`
  - `tests/forecast_pipeline_harness.py`、`tests/dirdef_helpers.py`、`tests/outlook_helpers.py`
  - `scripts/pipeline_acceptance_real.py`、`uv.lock`
  - `app/main.py`、`app/scheduler.py`
  - 凍結包、事先宣告、C-8 紀錄檔
- `app/outlook/rules/**`：沒有任何變更。
- 差異檔恰好 8 個，就是上面「變更檔案」所列。

**(e) `code_digest`**
- 舊值（`origin/product/stock-desk`，用 `git archive` 匯出的 app/ 計算）：`af3aa64b5f7c12f07e26df511a78bd909306c8190a51bc604469ed383943f751`
- 新值（HEAD `10fbdf9`）：`a15e910cad72389e12429025f3fb64fe1ff6b67b58cdbbea25123bd44bb77461`

**全套測試（HEAD `10fbdf9`）**

| 環境 | `app.__file__` | 結果 | 覆蓋率 |
|---|---|---|---|
| Python 3.13.17（預設 venv） | 本 worktree 的 `apps/stock-desk/backend/app/__init__.py` | 12050 passed、2 xfailed、0 failed | 97.81%（門檻 90） |
| Python 3.12.3（專屬 venv `/tmp/claude-0/-home-user-AICompany/3f76d891-50d3-55e1-b39d-925b8a90241a/scratchpad/venv312-cg2prereq`） | 同上 | 12050 passed、2 xfailed、0 failed | 97.81% |

- 3.12 那個隔離匯入測試在這個 base 已經會過。
- `ruff check .`：All checks passed。
- `ruff format --check`：546 個檔都已格式化。
- `mypy app tests`：534 個檔沒有問題。

**合成資料 harness**
- 腳本：`/tmp/claude-0/-home-user-AICompany/3f76d891-50d3-55e1-b39d-925b8a90241a/scratchpad/run_harness_synthetic.py`，暫存資料夾與 backend 替身都在 scratchpad。
- 結果：`P-0: passed=True runs=21 failure_kinds=[]`、`P-1: passed=True runs=21 failure_kinds=[]`。重構後的 `create_schema` 與 `register_claim` 在 harness 裡照常通過。

## 下一步

**自定解讀**
1. 「重讀最多 1 秒」：等待預算用 `time.monotonic()` 計時，期間每隔 1 ms 重讀一次 store 時鐘。`registered_at` 一律取自 store 時鐘（S-2），monotonic 只用來決定何時放棄。測試裡用替身 `time` 模組，不碰全域的 `time`。
2. 重讀適用於任何「不晚於前一列」的情況，包括時鐘倒退。
3. `create_objects` 不在交易內時拋 `RuntimeError`，沒有另外新增例外類別。
4. `bootstrap` 不檢查目標檔是否存在（`sqlite3.connect` 會建空檔）；路徑與存在性的檢查交給 CG-2 PR 的 CLI，依補充四第 2 點。
5. `provisional_results_seen()` 不要求 schema 完整，只經 `_read()` 讀取。
6. 「`_write(fresh=True)` 只出現在 bootstrap」的 AST 斷言更嚴：store.py 內任何帶參數的 `_write(...)` 都只能出現在 bootstrap；其他模組不得以方法呼叫 `_write`。`app/api/settings.py` 有一個同名但無關的模組函式，所以只計 `x._write(...)` 形式。

**已知限制**
- 一直同值的回滾測試，實際各要等約 1 秒，共 3 個測試。
- 第 5 點（claims.py 的 `bootstrap --production`、結束碼 3、4、5、提交後核對）屬 CG-2 PR，尚未實作。

**後續**
1. 交 qa-reviewer 審查（含 Codex），合併後 CI 要綠燈。
2. 前置 PR 合併後，我把 `feat/nm5-cg2-registration` 同步到新的 product，實作補充七第 5 點。屆時要加的斷言是「呼叫 `bootstrap` 的模組只有 claims.py」，以及 RC-163 抽取規則的失敗條件（標題出現 0 次或超過 1 次、缺開頭圍欄、缺結尾圍欄），並以 CEO 那一次的 `git_head` 重做 (d) 比對。

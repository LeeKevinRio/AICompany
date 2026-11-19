# NM-5 接線 PR 範圍清單（dev-lead，2026-11-19）

- 分支：`feat/nm5-wiring`，起點 `origin/feat/nm5-cg2-registration`（`9d5bbf480948d3a94fcef0966293bbfca7702089`），再 merge `origin/product/stock-desk`（`da4ffc2`）。
- 合併時機：補充四第 4 點 (4)、第 6 點；補充七第 7 點——CG-2 登記 PR 合併、CEO 正式登記、coordinator 在 `work/` 留登記紀錄之後才合併。登記完成前不合併。
- 規格來源：`docs/adr/0030-stock-desk-預測紀錄帳核心-最小記錄器.md`（以下簡稱 ADR）全文；約束 C5-1～C5-5 見 `work/reviews/2026-11-15-NM5第五批F2視窗與WARNING裁示-tech-architect.md`。
- 程式路徑相對於 `apps/stock-desk/backend/`。
- 標記：〔做〕不需裁示，本 PR 實作；〔流程〕不改程式，由 qa／coordinator 在合併時核對；〔待裁示〕要 TA（或指名的人）回答後才能做。

---

## 一、要做的項目

### W-1 scheduler 註冊 job `forecast_record`〔做〕
- 依據：D-3 第 7 點；D-6 CG-4 與「job 只在該 PR 註冊」；K-3；補充二第 1 點與 S-4a；補充三（修訂版）第 2 點（scheduler 在模組層級 import recorder）；補充四第 1 點 (c)（scheduler 的 AST 檢查在接線 PR 套用）；K-10／S-6。
- 改檔：`app/scheduler.py`。
- 內容：
  - 模組層級 `from app.forecast.recorder import ...`；這是 scheduler 進入核心的唯一一條 import（K-3）。
  - job id `forecast_record`（取 `recorder.JOB_ID`），平日（mon-fri）22:10 與 23:10，`timezone="Asia/Taipei"`，`max_instances=1`，`coalesce=True`，`next_run_time` 為啟動時刻加 3 分鐘。
  - job 本體在執行時才取主 DB 路徑（`app.data.cache.resolve_db_path()`，與其他 store 同一個主 DB）與 index resolver（`app.api.deps.get_index_resolver()`），呼叫 `record_forecasts(store, load_benchmark=load_market_benchmark, resolver=...)`；`load_benchmark` 傳 `app.services.index.load_market_benchmark` 本身，不包裝。
  - 不加 18:10 那一次（D-3 第 7 點：要等 data-engineer 確認，目前沒有確認紀錄）。
  - job 沒有 T、`as_of`、時鐘或規則參數。
- 測試：
  - `tests/test_forecast_scheduler_wiring.py`（新）：觸發時點、時區、`max_instances`、`coalesce`、啟動補跑 3 分鐘；只有一個 `forecast*` job；job 呼叫 recorder 時 `load_benchmark is load_market_benchmark`（S-4a 的 `is` 斷言，以替身捕捉實際傳入的物件）；scheduler 對 `app.forecast`／`app.outlook`／`app.dirdef` 的 import 恰為 `app.forecast.recorder`（AST）；scheduler 可達的核心模組集合等於 recorder 可達的集合（import graph）。
  - `tests/test_forecast_recorder.py`：`WIRED_REFERRERS` 改為 `{"scheduler.py"}`；`_module_level_recorder_import_violations(scheduler) == []`；`_wiring_violations(scheduler) == []`。
- 解讀：見第三節 I-1～I-4。

### W-2 `tests/test_forecast_gate_closed.py` 改為「只允許 `forecast_record`，仍然沒有 route」〔做〕
- 依據：D-10 表最後一列；D-4 第 6 點、S-11；K-3。
- 改檔：`tests/test_forecast_gate_closed.py`。
- 內容：`forecast*` job 恰為 `["forecast_record"]`；`/api/forecast`、`/api/outlook` 仍無 route；`app.main` 仍不可達 `app.forecast`、`app.outlook`、`app.dirdef`、`app.ops_alert`；`app.scheduler` 仍不可達 `app.ops_alert`（D-10：暫不使用）。原有的三個 teeth 測試保留。

### W-3 schema 不存在／登記表為空時的行為〔做：測試〕
- 依據：補充四第 2 點「正式主 DB 上的核心 schema 只能由 `bootstrap` 建立。其他路徑遇到 schema 不存在時拒絕寫入，不建表」；D-6 CG-2；S-7；補充七第 6 點（recorder 不呼叫 `bootstrap`、`create_objects`、`create_schema`）。
- 改檔：`app/scheduler.py`（主 DB 檔不存在時不呼叫 recorder，見 I-3）；測試。
- 測試（`tests/test_forecast_scheduler_wiring.py`）：
  - 主 DB 有其他表、沒有帳本 schema：job 拋 `SchemaIncompleteError`，`sqlite_master` 沒有任何 `forecast_`／`plan_` 物件，原有表內容不變；
  - 主 DB 檔不存在：不建立檔案，不呼叫 recorder；
  - schema 完整但登記表為空：`gate_closed`，`records_written = 0`，沒有任何快照或紀錄列；
  - scheduler 不呼叫 `bootstrap`、`create_objects`、`create_schema`、`register_claim`（AST）。

### W-4 F-2 計數視窗（補充五第 1 點；CG-4 阻擋項）〔做〕
- 依據：失效條件 F-2；D-4 第 5 點；補充五第 1 點 (a)～(h)；C5-3。
- 改檔：`app/forecast/store.py`（唯讀查詢 `f2_status`，F-2 的計數與成立與否只在這裡導出）；`app/forecast/report.py`（`status` 改輸出新的 F-2 段，移除 `f2_window` 與 `F2_WEEKDAYS`，不再自己判斷平日）。
- 內容（逐款對應）：
  - (a) 平日以 `store._weekdays_after`（內部用 `app.data.freshness.next_weekday`）列舉，與 T2 同一個函式；日期以 Asia/Taipei 計；平日 D 要 `late_cutoff_at(D) <= now` 才進入視窗（`late_cutoff_at` 用 `app.outlook.inputs` 的唯一定義）。
  - (b) S_c ＝ max（`registered_at` 的台北日期，第一筆 `forecast_run.started_at` 的台北日期）；沒有任何 `forecast_run` 時沒有起點，不評估（輸出「視窗未滿」，計數為 0）。
  - (c) S_c 起（含 S_c 當日，若為平日）的合格平日序列，每連續 20 個為一個視窗，逐平日滾動；日曆範圍為首尾平日（含其間週末）；任一完整視窗成立即「曾成立」。
  - (d) 分子 ＝ 視窗日曆範圍內「全部快照定案 session 聯集」（`final_sessions`，與 n̂ 同一查詢）中該 claim 沒有 `late = 0` 紀錄的 session 數 ＋ 範圍內有任一次 `inputs_not_ready` 的台北日數（同日多次算一天，同日另有 `ok` 也計）。
  - (e) 分母 ＝ min（20，範圍內定案 session 數）；成立 ⇔ 分子 × 10 > 分母 × 3（整數比較，等同「大於 30%」）。
  - (f) 合格平日不足 20 個：範圍為 S_c 起的全部合格平日；分子 > 6 成立，否則「視窗未滿」。
  - (g) `report status` 依 claim 分列：最近一個完整視窗的起迄日、兩項分子、分母、是否成立、自起點以來曾否成立；不與任何標籤或對照並列。
- 測試（`tests/test_forecast_f2_window.py`，新）：補充五 S-10a 第 1 點列出的每一種情形各一個——起點早於第一筆 `forecast_run`；同日兩次 `inputs_not_ready` 算一天；未定案且一直沒紀錄的 session 計入 2；休市日多的視窗以 min（20，s）為分母；只有較早的視窗成立時「曾否成立」仍為成立；視窗未滿的兩種情形（> 6 成立、≤ 6 未滿）；當天不計入；另加 `late_cutoff_at` 臨界（23:59:59.999999／00:00:00）。AST／grep：F-2 只在 `store.py` 導出，`report.py` 沒有 `weekday()`；store 的 F-2 用 `_weekdays_after`（與 T2 同一個）。報告輸出：不含標籤字樣、`d4_violations` 為空。
- 既有測試調整：`tests/test_forecast_report.py::test_status_counts_the_f2_window` 改為驗新輸出。harness 的完整輸出收 `render_execution_status`，F-2 屬執行狀態，依補充五第 5 點可以列；C5-1、C5-2、C5-5 的既有測試不改。

### W-5 D-8 第 4 點的 WARNING（補充五第 2 點；CG-4 阻擋項）〔做〕
- 依據：D-8 第 4 點末句；補充五第 2 點；C5-4。
- 改檔：`app/forecast/recorder.py`。
- 內容：`record_forecasts` 在 `forecast_run_end` 寫入之後（不在任何寫入交易內），以 `store.review_trigger(claim_id, today=<store 時鐘的台北日期>)` 對每個前瞻 claim 判定；成立的 claim 各記一行 WARNING：固定英文字面＋`claim_id`＋`T1`／`T2`／`T1+T2`。不含 n̂、c₁、d₁、D_v、計數、日期或標籤。判定拋 `Exception` 時改記一行固定字面的 WARNING，照常回傳；不捕捉 `BaseException`。沒有 D_v 時不記。`RunResult` 與帳內任何列不受影響。
- 測試（`tests/test_forecast_review_warning.py`，新）：補充五 S-10a 第 2 點的四種情形——不成立不記；只有 T1；T1 與 T2 同時成立；判定拋例外記固定字面——各一個，並斷言 outcome、`records_written`、`error_class`、`content_hash` 與不判定時相同、log 行 fullmatch 固定格式；另加：只有 T2；`KeyboardInterrupt` 不被吞；判定在 end 列寫入之後（end 列已存在）；不在寫入交易內（判定時沒有開著的寫入連線）。

### W-6 `app/` 中隨接線狀態過時的 docstring〔做〕
- 依據：補充七第 7 點末項（前置 PR 改過的 docstring 到 CG-2 合併為止不得再改；本 PR 在 CG-2 合併之後才合併）。
- 改檔：`app/forecast/__init__.py`（「until the wiring PR」兩處）、`app/forecast/recorder.py`（`JOB_ID` 註解、模組 docstring 的「only log line」一句）、`app/scheduler.py` 模組 docstring 加 `forecast_record`。
- 測試：無（文字）；`ruff`／`mypy` 照跑。

### W-7 已登記雜湊與「不得動」檔案零差異〔做：證明〕
- 依據：派工的「不得動」清單；D-8 第 6 點；補充七「不改……已登記雜湊」。
- 內容：`app/dirdef/`、`app/outlook/rules/*.yaml`、`uv.lock`、所有 `.gitattributes`、事先宣告、C-8 紀錄檔、`scripts/pipeline_acceptance_real.py`、`pipeline-acceptance.bat`、`work/dispatch/` 兩份 CEO 操作說明、`scripts/cg2_register.py`、`scripts/verify_cg2_instruction.py`、兩個 `cg2-*.bat` 及其測試：對 `origin/feat/nm5-cg2-registration` 零差異（交件附 `git diff --stat`）。definition／rules 雜湊以既有 M-4、M-5 測試證明不變（交件附測試名稱與結果）。

---

## 二、不改程式、由 qa／coordinator 在合併時核對〔流程〕

- **P-1 CG-1**：ADR 狀態為 accepted（檔頭第 3 行），含 C-M1～C-M4 與 D-11 的明確同意。qa 在 PR 說明核對。
- **P-2 CG-3 備份紀錄的落點（值留待 coordinator 填，不編造）**：
  - 落點：新檔 `work/dispatch/<登記日>-CG3備份紀錄-接線PR.md`（`work/.gitignore` 已放行 `dispatch/**`），由 coordinator 在登記紀錄 commit 之後、本 PR 合併之前 commit 進本分支；PR 說明引用該檔與 commit。
  - 格式（逐行 `key=value`，ASCII，不加其他行內文字）：
    ```
    cg3_backup_path=~/<家目錄相對路徑>          # 補充四第 4 點 (4)：家目錄相對寫法
    cg3_backup_sha256=<64 位小寫十六進位>
    cg3_backup_second_sha256=<64 位小寫十六進位>  # 補充七附記三第 3 點：第二份備份，須與上一行相等
    cg3_backup_integrity_check=ok
    registration_record_commit=<40 位小寫十六進位> # 補充四第 4 點 (3) 的 coordinator 登記紀錄 commit
    ```
    檔頭可另有繁中說明段；上述五行各出現恰好一次。
  - 是否加一個 CI 測試強制這個檔存在且格式正確（會讓本分支在填值前紅燈），列為待裁示 Q-2。
- **P-3 CG-4**：qa-reviewer PASS（含 Codex）＋ CI 綠燈；本 PR 觸及 `app/forecast/**`，合併前 `report verify --all` 必須全部一致（正式主 DB 由 CEO 本機執行；登記後、接線前帳內 0 筆紀錄，預期輸出「verify：沒有紀錄」，結束碼 0）。W-4、W-5 是 CG-4 阻擋項，PR 說明逐條列出測試名稱。
- **P-4 S-14a 末項**：合併時 `work/` 中已有 coordinator 的登記紀錄 commit。
- **P-5 S-17**：qa PASS＋CI 綠燈；CG-3 備份（P-2）；不遷移（K-12，既有 `schema_version` 恆為 1 與「沒有遷移函式」的測試）；還原依 D-8 第 3 點由操作者在 `work/` 記錄（流程，不寫程式）。
- **P-6 D-8 第 3 點／F-8（整檔還原、更換、重建）**：操作者當日在 `work/` 記錄；核心期間沒有程式偵測，本 PR 不新增。
- **P-7 新增的使用者面字面送風控**：見第五節。

---

## 三、自定解讀（小解讀，不影響寫入條件、排程行為或使用者看得到的內容；CEO 可推翻）

- **I-1 主 DB 路徑**：job 用 `resolve_db_path()`（`STOCK_DESK_DB_PATH` 或預設 `./data/stock-desk.db`），與所有其他 store 同一個主 DB。docker compose 設了 `STOCK_DESK_DB_PATH`，那個檔案沒有帳本 schema，所以會依補充四第 2 點拒絕寫入。本 PR 不另加「目標必須是 `<backend>/data/stock-desk.db`」的條件（ADR 只對 `bootstrap` 規定）。若 TA 認為 recorder 也要限定目標，見 Q-3。
- **I-2 store 的取得**：scheduler 只 import `app.forecast.recorder`（K-3「只經 recorder 進入核心」照字面），所以 recorder 新增一個沒有時間參數的公開函式 `ledger_store(db_path)`，回傳以系統時鐘建立的 `ForecastStore`；K-10 的簽章測試照樣涵蓋它。
- **I-3 主 DB 檔不存在**：job 不呼叫 recorder，記一行固定 WARNING（避免 SQLite 在連線時建立空檔）。這只會讓寫入更少，不放寬任何條件。
- **I-4 misfire**：沿用 APScheduler 預設（與 sector 三個 job 相同，不另設 `misfire_grace_time`）；錯過的時點由 23:10 重試與啟動補跑涵蓋。啟動補跑不限平日（recorder 自己判 `no_new_session`）。
- **I-5 F-2 起點含 S_c 當日**：「S_c 以後」讀為含 S_c（S_c 為平日時計入），比不含更嚴。
- **I-6 F-2 沒有任何 `forecast_run`**：沒有起點，輸出「視窗未滿」，兩項分子 0。
- **I-7 F-2 分母為 0**（範圍內沒有任何定案 session）：分子 > 0 就成立（fail-closed，同 TA 裁示表「s＝0」列）。
- **I-8 WARNING 的判定範圍**：D-8 第 4 點「每個前瞻 claim 各自判定」，所以判全部前瞻 claim（含已被取代者），不只記錄中 claim；核心期間實際只有 2 個。判定在任何 outcome（含 `gate_closed`、`error`）的 end 列寫入之後都執行；end 列寫入本身失敗時不判定。
- **I-9 job 結果的 log**：scheduler 每次執行記一行 INFO：`run_id`、`outcome`、`records_written`、`error_class`（皆非標籤，D-4 第 3 點）。

---

## 四、待裁示（每題可以直接回答）

- **Q-1（TA，派工指定不得自定）CG-2 一鍵檔與其測試怎麼退役？** 本 PR 改了 `app/`，`tests/test_cg2_register_values.py::test_r1_the_app_tree_constant_is_the_app_tree_of_this_checkout` 在本分支必定失敗（`HEAD:apps/stock-desk/backend/app` 的 tree id 不再是 `9c157d86…`）。請選一項：
  - (a) 本 PR 刪除 `scripts/cg2_register.py`、`scripts/verify_cg2_instruction.py`、`cg2-preflight.bat`、`cg2-register.bat` 與它們的全部測試（`tests/test_cg2_register_*.py`、`tests/cg2_register_*.py`）；
  - (b) 只刪 R-1 tree id 那一支測試，其餘保留為歷史紀錄；
  - (c) 檔案全部保留，把 R-1 測試標成 skip 並附理由；
  - (d) 另開 PR 退役，本 PR 不動，接受這一支紅燈直到退役 PR 合併。
  另請答：退役要不要 ADR 依據（新增補充，或只在本 PR 說明引用 devops-sre 的註記）？裁示前我完全不動這些檔案。
- **Q-2（TA／coordinator）CG-3 紀錄要不要有 CI 測試把關？** 若要，我加一個測試：`work/dispatch/*-CG3備份紀錄-接線PR.md` 恰有一份，且五行格式（P-2）全對、兩個 sha256 相等。效果是本分支在 coordinator 填值前 CI 紅燈，填值後才綠，等於機械阻止提早合併。要／不要？
- **Q-3（TA）recorder 是否也要限定正式目標？** 目前只靠「schema 不存在就拒絕」。要不要另加「scheduler 的目標必須是 `<backend>/data/stock-desk.db` 且未設 `STOCK_DESK_DB_PATH`」？加了之後 docker compose 部署的 scheduler 永遠不記錄（與現狀實際效果相同，但理由從「沒有 schema」變成「路徑不符」）。要／不要？（不加不影響本 PR 其他項目。）
- **Q-4（TA）F-2 第二句（第 0 相位格點遺失率 > 20%）要不要在 `report status` 加「是否超過 20%」一欄？** 補充五只處理第一句；現行報告列「格點數」與「沒有 late = 0 紀錄的格點數」兩個計數，沒有門檻判定。加的話會多一句使用者面字面。要／不要？（不加不影響本 PR。）

---

## 五、新增的使用者面字面（操作者報告 `python -m app.forecast.report status`；log 以外，送風控）

實作後在交件報告逐字列出最終版本；預計為：
- 段標題：`ADR-0030 失效條件 F-2（連續 20 個平日的遺失計數；只含執行狀態，不含任何標籤或對照）`
- 每個 claim 一行（完整視窗）：`  {claim_id}：最近一個完整視窗 {起}～{迄}，沒有 late = 0 紀錄的定案 session 數 {a}，inputs_not_ready 日數 {b}，分母 {d}，{成立／未成立}；自起點以來曾否成立：{是／否}`
- 每個 claim 一行（視窗未滿）：`  {claim_id}：視窗未滿（自起點以來 {k} 個平日：{起}～{迄}），沒有 late = 0 紀錄的定案 session 數 {a}，inputs_not_ready 日數 {b}，{成立／視窗未滿}`
- 沒有任何執行時：`  {claim_id}：視窗未滿（尚無執行）`
- 移除的舊字面：`F-2 計數（最近 20 個平日：… 起至 …）：`、`  inputs_not_ready 日數：…`、`  {claim_id}：最新快照中出現、但沒有 late = 0 紀錄的定案 session 數：…`。

log 行（英文、只進 log，不送風控，列出備查）：
- `forecast_record: review trigger holds; claim_id=<id> trigger=<T1|T2|T1+T2>`
- `forecast_record: the review trigger check failed; the run outcome is unchanged`
- `forecast_record: the main database file does not exist; the run is skipped`
- `forecast_record run: run_id=<n> outcome=<outcome> records_written=<n> error_class=<class|none>`

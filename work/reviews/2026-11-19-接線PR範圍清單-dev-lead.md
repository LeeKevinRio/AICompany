# NM-5 接線 PR 範圍清單（dev-lead，2026-11-19）

- 分支：`feat/nm5-wiring`，起點 `origin/feat/nm5-cg2-registration`（`9d5bbf480948d3a94fcef0966293bbfca7702089`），再 merge `origin/product/stock-desk`（`da4ffc2`）。
- 合併時機：補充四第 4 點 (4)、第 6 點；補充七第 7 點——CG-2 登記 PR 合併、CEO 正式登記、coordinator 在 `work/` 留登記紀錄之後才合併。登記完成前不合併。
- 規格來源：`docs/adr/0030-stock-desk-預測紀錄帳核心-最小記錄器.md`（以下簡稱 ADR）全文；約束 C5-1～C5-5 見 `work/reviews/2026-11-15-NM5第五批F2視窗與WARNING裁示-tech-architect.md`；補充八（定稿第三版，待 append）；**補充九（待 append，風控審查見 `work/reviews/2026-11-19-補充九判定與F2字面定稿RC244至RC254-風控.md`）**，全文在 `work/reviews/2026-11-19-接線PR四題裁示與補充九定稿-tech-architect.md`。
- 2026-11-19 第二輪：依補充九、風控 RC-237～RC-254、qa 審查 `work/reviews/2026-11-19-接線PR審查-qa.md` 修改（見各項「第二輪」）。
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
- 改檔：測試（目標核對見 W-10，取代原「主 DB 檔不存在時不呼叫 recorder」）。
- 測試（`tests/test_forecast_scheduler_wiring.py`）：
  - 主 DB 有其他表、沒有帳本 schema：job 拋 `SchemaIncompleteError`，`sqlite_master` 沒有任何 `forecast_`／`plan_` 物件，原有表內容不變；
  - schema 完整但登記表為空（`test_an_empty_registry_closes_the_gate_and_writes_only_the_run_rows`）：`gate_closed`，`records_written = 0`；**不寫 `forecast_record`、`forecast_input_series`、`forecast_claim_registry` 列；`forecast_run` 與 `forecast_run_end`（`gate_closed`）照寫**（D-2 第 1～2 點；qa N-4）；
  - `KeyboardInterrupt` 穿透 `_guarded`（`test_a_keyboard_interrupt_passes_through_the_guarded_job`；qa N-5）；
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
- 內容：`app/dirdef/`、`app/outlook/rules/*.yaml`、`uv.lock`、所有 `.gitattributes`、事先宣告、C-8 紀錄檔、`scripts/pipeline_acceptance_real.py`、`pipeline-acceptance.bat`、`work/dispatch/` 兩份 CEO 操作說明、`scripts/cg2_register.py`、`scripts/verify_cg2_instruction.py`、兩個 `cg2-*.bat` 及其測試：對 `origin/feat/nm5-cg2-registration` 零差異（交件附 `git diff --stat`）。其中 `scripts/cg2_register.py`、`scripts/verify_cg2_instruction.py`、`cg2-preflight.bat`、`cg2-register.bat` 與只測它們的測試：本 PR 完全不動（不刪、不 skip、不重釘常數），**由退役 PR 刪除（補充九第 1 點）**；退役 PR 在 CEO 完成登記、coordinator 登記紀錄 commit 之後才開，接線 PR 先 merge 它再合併。在那之前 `test_r1_the_app_tree_constant_is_the_app_tree_of_this_checkout` 的紅燈照實保留。definition／rules 雜湊以既有 M-4、M-5 測試證明不變（交件附測試名稱與結果）。

### W-8 缺日（來源整列缺席）的特性測試（2026-11-19 補入，coordinator 轉 TA 裁示第 5 題）〔做〕
- 依據：`work/reviews/2026-11-19-缺日靜默丟列與登記先後裁示-tech-architect.md` 第 5 題；ADR D-8 第 3 點（已接受的限制，修補留給驗證層 ADR）。
- 改檔：只加 `tests/test_forecast_missing_session_characterization.py`。
- 內容：合成中間缺一個 session 的 bars，斷言 (1) 快照照原樣保存、缺口保留、沒有補值；(2) `dropped_rows_json` 不含該日；(3) outcome 與 `missing_json` 與沒有缺口時相同，missing code 不出 `MISSING_CODES`。docstring 引用 D-8 第 3 點並註明「已知限制，修補見後續 ADR」。
- 本 PR **不得**：改 `app/outlook/**`、`app/forecast/**`、`app/dirdef/**`、`app/data/session_calendar.py` 中與缺日有關的行為；新增 `DropReason` 值、`MISSING_CODES` 成員、outcome 值、表或欄位；在 `app/` 內新增交易日曆；以缺口或開盤值作為 recorder 的分支或拒收條件；改 `app/data/providers/yfinance.py`、`app/data/cache.py`、`app/services/index.py`。
- 已知盲點（只記，不處理）：補充五第 1 點 (d) 的 F-2 分子取「快照中定案 session 的聯集」，來源永久缺席的 session 不會進分子，F-2 會偏低。

- 2026-11-19 更新：依補充八（定稿第二版，待 append）S-18a「第 3 點 (d)」，特性測試再加「缺 T 本身」一組：結果為 `no_new_session`，或一筆 `late = 1` 的 T−1 紀錄；docstring 改引補充八第 2 點。另加 S-18a「第 3 點 (a)～(c)」守門測試（`tests/test_forecast_gap_disclosure.py`）：`DropReason` 只有 `"not_final"`；outcome 列舉與 `EXPECTED_OBJECTS` 的 DDL 雜湊不變；`session_calendar.py` 頂層只有 `is_final`；`app/` 提到休市／holiday 的檔案集合與 CG-2 head（`9d5bbf48`）相同、沒有日曆資料檔。`MISSING_CODES` 由既有 `tests/test_outlook_missing_codes.py` 釘住。

### W-9 `report status` 缺日加註（補充八（定稿第二版，待 append）第 6 點 (b)；CG-4 阻擋項）〔做〕
- 依據：補充八第 6 點 (b)、S-18a「第 6 點 (b)」；風控 RC-230 定稿（`work/reviews/2026-11-19-report-status缺日加註定稿RC229至RC232-風控.md`「定稿全文：」那一行）。
- 改檔：`app/forecast/report.py`（模組常數 `GAP_DISCLOSURE`，以腳本自風控報告抽出寫入；`render_execution_status` 的最後一個元素，所以在 `render_status` 中排在重審觸發之前；不因任何資料分支）。
- 測試：`tests/test_forecast_gap_disclosure.py`——常數與風控報告抽出的字面逐字相同；是最後一個元素；零 claim／有缺口／無缺口三種帳都出現且相同；其餘各行與加入前（測試內獨立組出的預期）逐行相同；`render_status` 中排在重審觸發之前；常數是單一字面、沒有在任何分支中使用（AST）。
- 第二行（風控 RC-233、RC-234 定稿，`work/reviews/2026-11-19-重審觸發缺日加註定稿RC233至RC236-風控.md`「第二行定稿全文：」）：常數 `REVIEW_GAP_DISCLOSURE`，`render_review_trigger` 的最後一個元素（即 `render_status` 的最後一個元素），零／一／兩個 claim 都恰好一次；不進 `render_execution_status` 與 harness 輸出。`N_HAT_NOTE` 不改（補充八第 3 點 (f)），有測試釘住。測試 `tests/test_forecast_gap_disclosure.py::test_r1`～`test_r7`；`tests/test_forecast_report.py::d4_violations` 只對這一行的核可字面免除「n̂ 須附固定標示」一條，其餘規則照查。
- 之後要增修這兩行須重送風控；PR 說明附 RC-230、RC-233／RC-234 出處。RC-231（n̂、c₁ 是否也受缺日影響）若答「會」，字面與適用範圍會再調整。

### W-10 scheduler 的正式目標（補充九第 3 點，收緊；第二輪）〔做〕
- 改檔：`app/scheduler.py`（`forecast_record_target`、`production_db_target`、`FORECAST_RECORD_REFUSALS`），取代原「只檢查檔案存在」。
- 內容：建立 store 前依序核對 (a) 程序環境變數沒有 `STOCK_DESK_DB_PATH`（空字串也算有設）；(b) `<backend>` 由模組位置導出（`BACKEND_DIR`），`resolve_db_path()` 以 `Path.resolve(strict=True)` 解析成功、等於 `<backend>/data/stock-desk.db`、為一般檔案。任一不成立：不呼叫 recorder，記一行固定英文 WARNING（不含路徑），正常返回；不開 SQLite 連線、不建檔、不讀 `.env`。recorder 與 `ledger_store` 不檢查目標。
- 測試：`test_s19a_a_refused_target_does_not_call_the_recorder`（環境變數有設、空字串、目標不同、檔案不存在、目標是目錄）、`test_s19a_each_refusal_is_one_fixed_line_without_a_path`、`test_s19a_the_default_target_calls_the_recorder`、`test_the_production_target_is_derived_from_the_module_location`、`test_s19a_the_scheduler_reads_no_env_file`（AST）與其 teeth。既有用暫存 DB 的測試改以 monkeypatch `production_db_target` 跑，job 沒有路徑參數（K-10）。

### W-11 F-2 第一句完整視窗分母為 0（補充九第 4 點，收緊；第二輪）〔做〕
- 改檔：`app/forecast/store.py`（`f2_status`）。完整視窗分母為 0 時不論分子判成立；視窗未滿 (f) 不變。原測試沒有「0/0 未成立」的預期，不需更新。
- 測試：`test_s19a_a_full_window_with_no_final_session_and_nothing_counted_holds`、`test_s19a_a_short_range_with_nothing_counted_is_still_not_held`；既有 `test_a_window_with_no_final_session_holds_on_any_not_ready_day`。

### W-12 F-2 第二句：第 0 相位格點遺失判定（補充九第 5 點，收緊；CG-4 阻擋項；第二輪）〔做〕
- 改檔：`app/forecast/store.py`（唯讀查詢 `grid_loss_status`，回傳 G、L、三態判定、曾否成立；經 `_read`）；`app/forecast/report.py`（第二句各行取代原格點行，只做格式化）。
- 測試（`tests/test_forecast_f2_window.py`）：`test_s19a_no_d_v_is_undecidable`、`test_s19a_d_v_whose_cutoff_has_not_passed_is_undecidable`、`test_s19a_one_of_five_is_not_held`、`test_s19a_two_of_nine_holds`、`test_s19a_an_earlier_prefix_held_and_ever_held_stays`、`test_the_grid_points_are_counted_only_once_their_cutoff_passed`、`test_the_grid_loss_query_needs_an_aware_now_and_only_reads`、`test_the_grid_loss_verdict_is_derived_in_store_py_only`（grep）、`test_the_report_prints_the_second_sentence_per_claim`、`test_the_undecidable_second_sentence_has_no_ever_held`。

### W-13 F-2 段的風控定稿字面（RC-238、RC-239、RC-242、RC-247～RC-252；第二輪）〔做〕
- 改檔：`app/forecast/report.py`（常數以腳本自風控報告抽出寫入，不手打）；`tests/approved_copy.py`（RC-244～254 報告依「項目：」標籤抽取，RC-237～243 報告依前一行標籤抽取，並斷言兩份報告的標籤恰為預期集合；RC-237 段標題、RC-238 分母 0 兩行列為作廢且不被使用）。
- 輸出順序（RC-252）：`執行狀態（…）`、`執行次數：…`、`inputs_not_ready 日數（全部期間，台北日期）：…`（這三行維持原相對位置，在段標題之前）→ 最近一次執行（RC-259）→ 段標題 → 第一句小標題 → 第一句各行 → 第二句小標題 → 第二句各行 → 行動句 → `GAP_DISCLOSURE` → 重審觸發各行 → `REVIEW_GAP_DISCLOSURE`。原「第 0 相位格點 {n} 個，其中沒有 late = 0 紀錄 {m} 個」行已移除（由第二句各行取代）。
- 測試（`tests/test_forecast_gap_disclosure.py`）：`test_rc252_every_constant_is_the_approved_text`、`test_rc252_the_superseded_texts_are_not_used`、`test_rc252_the_fixed_lines_are_printed_in_order_whatever_the_ledger`（零 claim／有缺口／無缺口）、`test_rc252_the_whole_status_order`、`test_rc252_the_fixed_lines_are_single_literals_never_in_a_branch`、`test_rc252_no_new_line_trips_the_d4_checks`；RC-230 四件事的測試改套 RC-251 字面（`test_the_line_is_the_risk_approved_text`、`test_1`～`test_4`）；第一句各行在 `tests/test_forecast_f2_window.py::test_the_report_prints_*`（模板代入後逐字比對）。harness：`tests/test_forecast_pipeline_harness.py::test_the_output_holds_no_n_hat_while_report_status_does`（第一行加註恰一次、第二行零次、段內固定行恰一次且不進 `render_summary`）。
- RC-240／qa N-1：`tests/test_forecast_report.py::test_rc240_the_n_hat_exemption_is_exactly_one_line`、`test_rc240_a_near_copy_of_the_exempt_line_is_still_caught`（多一字、改一字、少一字）。

### W-14 qa 第一輪意見（第二輪）〔做〕
- N-6：`tests/test_forecast_missing_session_characterization.py::test_a_missing_t_falls_back_to_the_previous_final_bar_late` 釘死唯一預期（`ok`＋兩筆 `late = 1` 的 T−1 紀錄），另加 `test_a_missing_t_after_t_minus_1_was_recorded_is_no_new_session`。
- N-2：`tests/test_forecast_scheduler_wiring.py::test_n2_only_the_scheduler_imports_the_core_from_outside_it`、`test_n2_the_core_package_imports_are_as_they_stand`（forecast→outlook、dirdef；outlook→dirdef）、`test_n2_the_whole_app_scans_have_teeth`。
- N-4、N-5：見 W-3。N-3：不做（TA 裁示不需要）。

### W-15 最近一次留下執行紀錄的執行（風控 RC-259）〔做〕
- 改檔：`app/forecast/report.py`（`LATEST_RUN_LINE`／`LATEST_RUN_NONE_LINE`，字面以腳本自 `work/reviews/2026-11-19-收盤定案時點定案與補充十判定RC255至RC264-風控.md` 的「項目：RC-259 …」抽出）。取值經既有唯讀查詢 `store.latest_run`（走 `_read`）：`run_id` 最大一筆的 `started_at` 換台北時間 `YYYY-MM-DD HH:MM`，outcome 原值，沒有 end 列印「沒有 end 列」；`report.py` 只做格式化。位置：`inputs_not_ready 日數（全部期間，台北日期）` 之後、F-2 段標題之前。
- 測試（`tests/test_forecast_gap_disclosure.py`）：`test_rc259_the_constants_are_the_approved_text`、`test_rc259_without_a_run_row_the_none_variant_is_printed`、`test_rc259_the_latest_run_is_the_highest_run_id_in_taipei_time`（ok、inputs_not_ready、沒有 end 列）、`test_rc259_both_variants_carry_the_note_and_pass_the_d4_checks`；harness 完整輸出恰一行、`render_summary` 不含（`tests/test_forecast_pipeline_harness.py::test_the_output_holds_no_n_hat_while_report_status_does`）。

### 待規格：補充十第 2、3 點（RC-255：須與 job 註冊同一次合併落地）
- 第 2 點（每次執行前強制 live 更新並核對 `B.as_of ≥ t0`）：等 data-engineer 的方法規格，未動手。
- 第 3 點（啟動補跑時段 [13:30, 22:10)）：等補充十最終版文字，未動手。

---

## 二、不改程式、由 qa／coordinator 在合併時核對〔流程〕

- **P-8 補充八第 5 點 (a) 帳外缺日比對（CG-4 的前置條件，不在本 PR 範圍）**：由 devops-sre 的 `feat/gap-check-oneclick` 一鍵檔與 CEO 執行。接線 PR 說明須附比對結果的 commit（qa 核對它早於合併 commit）與第 5 點 (b) 的 CEO 確認紀錄（S-18a「第 5 點 (a)」）；值由 coordinator 填。

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
  - 不加 CI 測試（補充九第 6 點；Q-2 裁示）。qa 在合併時人工核對：備份 sha256 等於補充四第 4 點 (3) 登記紀錄中的值，也等於登記回貼的 `backup_sha256`；路徑用家目錄相對寫法。**只填有出處的值；沒有出處的項目照實標「無出處」，不得推得或補填**（補充九第 6 點）。
- **P-3 CG-4**：qa-reviewer PASS（含 Codex）＋ CI 綠燈；本 PR 觸及 `app/forecast/**`，合併前 `report verify --all` 必須全部一致（正式主 DB 由 CEO 本機執行；登記後、接線前帳內 0 筆紀錄，預期輸出「verify：沒有紀錄」，結束碼 0）。W-4、W-5 是 CG-4 阻擋項，PR 說明逐條列出測試名稱。
- **P-4 S-14a 末項**：合併時 `work/` 中已有 coordinator 的登記紀錄 commit。
- **P-5 S-17**：qa PASS＋CI 綠燈；CG-3 備份（P-2）；不遷移（K-12，既有 `schema_version` 恆為 1 與「沒有遷移函式」的測試）；還原依 D-8 第 3 點由操作者在 `work/` 記錄（流程，不寫程式）。
- **P-6 D-8 第 3 點／F-8（整檔還原、更換、重建）**：操作者當日在 `work/` 記錄；核心期間沒有程式偵測，本 PR 不新增。
- **P-7 新增的使用者面字面送風控**：見第五節。

---

## 三、自定解讀與其處置（補充九第 7 點）

- **I-1 主 DB 路徑**：由補充九第 3 點取代並擴充為「必須等於預設正式目標」（W-10）。
- **I-2 store 的取得**：scheduler 經 `recorder.ledger_store(db_path)` 取得 store（K-3）；該函式沒有時間或時鐘參數，納入 K-10 的簽章測試（補充九第 7 點 (e)）。
- **I-3 主 DB 檔不存在**：併入補充九第 3 點 (b)（W-10）。
- **I-4 misfire**：同意，寫進 ADR（補充九第 7 點 (d)）：不另設 `misfire_grace_time`，沿用 APScheduler 預設；錯過的時點由 23:10 重試與啟動補跑涵蓋；啟動補跑不限平日。
- **I-5 F-2 起點含 S_c 當日**：同意，寫進 ADR（補充九第 7 點 (a)）；含 S_c 的讀法**不寬於**字面。
- **I-6 F-2 沒有任何 `forecast_run`**：同意，寫進 ADR（補充九第 7 點 (b)）：沒有 S_c、不評估，輸出「視窗未滿（尚無執行）」，兩項分子為 0。
- **I-7 F-2 分母為 0**：不同意，改依補充九第 4 點（完整視窗分母為 0 一律判成立；W-11）。
- **I-8 WARNING 的判定範圍**：同意，寫進 ADR（補充九第 7 點 (c)）：對全部前瞻 claim 判定（含已被取代者），在任何 outcome 的 end 列寫入之後判定；end 列寫入失敗時不判定；`report status` 只列記錄中 claim。
- **I-9 job 結果的 log**：scheduler 每次執行記一行 INFO：`run_id`、`outcome`、`records_written`、`error_class`（皆非標籤，D-4 第 3 點）。

---

## 四、已裁示（`work/reviews/2026-11-19-接線PR四題裁示與補充九定稿-tech-architect.md`）

- **Q-1**：本 PR 不動一鍵檔；另開退役 PR（補充九第 1 點），見 W-7。
- **Q-2**：不加 CI 測試（補充九第 6 點），見 P-2。
- **Q-3**：只在 scheduler 加目標限定（補充九第 3 點），見 W-10。
- **Q-4**：在 `store.py` 導出第二句判定（補充九第 5 點），見 W-12。

---

## 五、使用者面字面（操作者報告 `python -m app.forecast.report status`）與其出處

全部以腳本自下列風控報告抽出寫入 `app/forecast/report.py`，測試亦自同一報告抽出比對，不手打。之後增修須重送風控。

| 常數 | 用途 | 出處 |
|---|---|---|
| `LATEST_RUN_LINE`／`LATEST_RUN_NONE_LINE` | 最近一次留下執行紀錄的執行（有／沒有執行紀錄） | `work/reviews/2026-11-19-收盤定案時點定案與補充十判定RC255至RC264-風控.md`「項目：RC-259 最近一次執行（帳內有執行紀錄時）」「項目：RC-259 最近一次執行（帳內沒有執行紀錄時）」 |
| `F2_TITLE` | 段標題 | `work/reviews/2026-11-19-補充九判定與F2字面定稿RC244至RC254-風控.md`「項目：RC-248 段標題（取代 RC-237）」 |
| `F2_FIRST_HEADING` | 第一句小標題（一律印出） | 同上「項目：RC-248 第一句小標題」 |
| `F2_FULL_LINE` | 第一句完整視窗（分母大於 0） | `work/reviews/2026-11-19-接線PR-F2視窗字面判定RC237至RC243-風控.md`「RC-238 完整視窗（分母大於 0）：」 |
| `F2_FULL_ZERO_LINE` | 第一句完整視窗（分母為 0） | RC-244～254 報告「項目：RC-247 第一句完整視窗分母為 0（取代 RC-238 分母為 0 那一行）」 |
| `F2_SHORT_LINE` | 第一句視窗未滿 | RC-237～243 報告「RC-239 視窗未滿：」 |
| `F2_NO_WEEKDAY_LINE` | 有起點但沒有可計入的平日 | RC-237～243 報告「RC-242（suggested…）：」（coordinator 定案套用，CEO 可推翻） |
| `F2_NO_RUN_LINE` | 尚無執行 | 維持原字面 `  {claim_id}：視窗未滿（尚無執行）`（RC-239 佔位符說明：維持現狀） |
| `F2_SECOND_HEADING` | 第二句小標題（一律印出） | RC-244～254 報告「項目：RC-248 第二句小標題」 |
| `F2_SECOND_LINE` | 第二句有判定（G 大於 0） | 同上「項目：RC-249 第二句有判定（G 大於 0）」 |
| `F2_SECOND_UNDECIDABLE_LINE` | 第二句無從判定（G 為 0；不含「曾否成立」） | 同上「項目：RC-249 第二句無從判定（G 為 0）」 |
| `F2_ACTION_LINE` | 行動句（一律印出） | 同上「項目：RC-250 行動句」 |
| `GAP_DISCLOSURE` | 執行狀態段末行加註 | 同上「項目：RC-251 第一行加註（修訂 RC-230）」 |
| `REVIEW_GAP_DISCLOSURE` | 重審觸發段末行加註 | `work/reviews/2026-11-19-重審觸發缺日加註定稿RC233至RC236-風控.md`「第二行定稿全文：」（未改） |
| `N_HAT_NOTE` | n̂ 固定標示 | 未改（補充八第 3 點 (f)） |

作廢不用：RC-237 段標題、RC-238「完整視窗（分母為 0）」（有測試確認不被使用）。

log 行（英文、只進 log；RC-246：不含路徑，也不含要求修改設定的祈使句）：
- `forecast_record: STOCK_DESK_DB_PATH is set in the process environment; the run is skipped`
- `forecast_record: the main database does not resolve to an existing file; the run is skipped`
- `forecast_record: the main database is not the default production database; the run is skipped`
- `forecast_record: the main database is not a regular file; the run is skipped`
- `forecast_record: review trigger holds; claim_id=<id> trigger=<T1|T2|T1+T2>`
- `forecast_record: the review trigger check failed; the run outcome is unchanged`
- `forecast_record run: run_id=<n> outcome=<outcome> records_written=<n> error_class=<class|none>`
- 移除：`forecast_record: the main database file does not exist; the run is skipped`（由上列四句取代）。

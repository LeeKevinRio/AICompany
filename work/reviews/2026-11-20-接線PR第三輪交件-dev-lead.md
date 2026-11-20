# 接線 PR 第三輪交件

- 審查者：dev-lead
- 日期：2026-11-20
- 轉存：coordinator，逐字轉存 subagent 最終回報

---

## 本次結論

接線 PR 第三輪做完了，已推到 `origin/feat/nm5-wiring`。新的 head 是 `a5c343433a722e325fd01f78974fff5cb1942c6f`。

- 這輪完成三件事：
  - 補充十第 2 點：每次執行先強制重抓大盤，再核對 (i)(ii)(iii)，成立才呼叫 recorder。
  - 補充十第 3 點：平日台北 [13:30, 22:10) 不設啟動補跑。
  - 風控 RC-267 (a)：三行 WARNING 只以固定字串記錄。
- 最後一個 commit 之後重跑了全套：
  - 3.12 與 3.13 都是 12833 passed、1 failed、2 xfailed，coverage 97.83%。
  - 唯一失敗的是預期中的 `test_cg2_register_values.py::test_r1_the_app_tree_constant_is_the_app_tree_of_this_checkout`。
- `service.py`、`index.py` 的刪除行數是 0。
- `code_digest` 沒有變：`e8e0fb630a30361e3e0d2b34caa06b872c9e83609cc3b2b1b384581dc710d340`。

有兩處要請你看：
- 我改了一支既有的 forecast 守門測試（休市字樣的白名單），見「待決與偏離」第 1 點。
- 修正前的那次全套跑出一個與本輪無關的偶發失敗，見「驗證」的「修正前那一次」。

## 各項回報

**第 1 項：實作前確認的三件事**
1. **`tests/market_service_helpers.py` 不夠用，但能接著寫。**
   - 它只提供服務的建構（`index_service`／`build_service`，時鐘可以注入），沒有假 provider。
   - 所以我新增 `tests/force_refresh_helpers.py`，放假的指數來源（每根的 `as_of` 是請求時刻）、可調的時鐘、seed 函式，以及三張快取表的 `SELECT *` 傾印。
   - 等價測試就用這些寫成，helper 本身沒改。
2. **有釘住呼叫序列。**
   - `test_forecast_scheduler_wiring.py` 有 7 支測試，在 `get_index_resolver → {}` 的情況下要求 recorder 被呼叫：
     - `test_s19a_the_default_target_calls_the_recorder`
     - `test_s4a_the_job_passes_load_market_benchmark_itself`
     - `test_the_registered_job_runs_the_recorder_job`
     - `test_a_keyboard_interrupt_passes_through_the_guarded_job`
     - `test_without_the_ledger_schema_the_run_is_refused_and_nothing_is_created`
     - `test_the_guarded_job_logs_the_refusal_and_survives`
     - `test_an_empty_registry_closes_the_gate_and_writes_only_the_run_rows`
   - `test_forecast_recorder.py::test_s4a_the_job_passes_the_index_loader_itself` 也一樣。
   - 這 8 支都只多加一行：先換上成功的強制更新（`_refresh_ok`／`_fresh_refresh`），原有斷言一字不動。
   - `test_the_job_also_runs_three_minutes_after_start_up` 原本吃真實時鐘，平日白天跑就會落進不補跑的時段。我改成固定啟動時刻（週一 23:00），斷言從「誤差 30 秒內」收緊為逐值相等。
   - `test_scheduler.py`、`test_scheduler_data_refresh.py`、`test_scheduler_dividend_sync.py`、`test_scheduler_sector_jobs.py` 都沒有釘 forecast 的呼叫序列，沒動。
3. **沒有把 `_judge_bars` 標籤釘成全集的測試。** `test_f9a_service_currency_warning.py`、`test_f9b_cache_currency_gate.py` 都只斷言個別流程的標籤序列。

**commit 與對應測試**

| commit | 內容 | 對應測試 |
|---|---|---|
| `c9f7259609afbfc226ed72fd0f0c70e538255094` | merge `origin/product/stock-desk` | — |
| `b2907118721999ea13f0e9f3436fb4abcf005510` | `service.py`：`LiveRefreshOutcome`（含 `failed()`）與 `refresh_daily_bars_live` | `tests/test_service_force_refresh.py`，27 支，見下 |
| `dadc144c6a09fdb6a2bedea166428c9955fe3174` | `index.py`：穿透方法、`LiveRefreshService`、`ForcedBenchmarkRefresh`、`force_refresh_benchmark` | `tests/test_services_index_force_refresh.py`，26 支，見下 |
| `2d7d2c818a8b0fd5313cb5455165f714c6003e49` | `scheduler.py`：五步、三行常數、啟動補跑時段；隨改既有 scheduler 測試 | `tests/test_scheduler_forecast_refresh.py`，27 支，見下 |
| `f85e0e55d99b512512211c7c0fbd99e843ccd228` | 範圍清單：「待規格」改為已做的 W-16、W-17，列出三行字面與新增檔案 | — |
| `a5c343433a722e325fd01f78974fff5cb1942c6f` | 休市字樣白名單加入 `scheduler.py`，並釘死只有那一行 | `test_forecast_gap_disclosure.py::test_no_holiday_data_is_added_to_app` |

- 測試沒有另開 commit，跟各自的實作放在同一個 commit，所以每個 commit 單獨都是綠的。
- **`test_service_force_refresh.py`：**
  - 略過 layer 0 與 cooldown：`test_a_current_cache_inside_the_cooldown_is_still_asked_for`、`test_a_recent_failed_attempt_does_not_hold_the_refresh_back`。
  - 寫入欄位：`test_the_written_fields`（`as_of`、`fetched_at`、coverage）。
  - 回落到快取不算成功：`test_a_failed_ask_with_a_cache_on_hand_is_not_a_success`。
  - 盤中列的丟棄：`test_before_the_close_the_bar_of_the_day_is_dropped`、`test_at_22_10_...`、`test_an_answer_left_with_no_bar_...`。
  - 增量起點：`test_a_covered_cache_narrows_...`、`test_without_coverage_...`。
  - 被拒的快取整段重抓：`test_a_refused_cached_series_is_asked_for_in_full`（log 的 layer 是 `force_refresh_cache`）。
  - 即時回答被幣別閘拒絕：`test_a_live_answer_in_another_unit_...`、`test_after_a_refused_live_answer_...`。
  - 讀回失敗：`test_a_failed_read_back_...`、`test_a_refused_read_back_...`。
  - provider 例外：`test_a_raising_source_...`。
  - `complete=False` 不記 coverage：`test_a_partial_answer_...`。
  - 另有 `CurrencyLookupError` 往外拋、admission 拒絕、備援順序。
  - 等價：`test_t_eq_the_refresh_writes_what_the_ladder_writes`，四種起始狀態（空快取、coverage 完整的增量、快取被拒、即時回答被拒），三張表逐欄相同，provider 收到的請求也相同。
  - AST：`test_the_refresh_calls_no_layer_zero_or_fall_back_helper`，含 teeth 測試。
  - 我做了變異測試確認等價測試抓得到漂移：把「快取被拒」改成增量，或拿掉最後的 `record_attempt`，對應的測試都會失敗。
- **`test_services_index_force_refresh.py`：**
  - 範圍：台北日期減 `lookback_days`，跨 UTC 日界時也是台北日期。
  - 讀回取日期最大的一根。
  - 簽章與 AST：沒有時間參數，含 teeth。
  - 結構性缺漏回報不成功，三種例外往外拋。
  - 穿透方法。
  - K-2：`test_k2_the_index_module_does_not_reach_the_forecast_core`、`test_k2_no_services_module_reaches_the_forecast_core`，含 teeth。
  - 整合：`test_c1_...`、`test_c2_...`，走 recorder 自己的 `_fetch`，強制更新之後 provider 呼叫數仍是 1。另有「快取原本有 17:45 的 T 日列」與競態 `test_c3_the_race_is_the_documented_behaviour`。
- **`test_scheduler_forecast_refresh.py`：**
  - 成功時呼叫 recorder 一次，且用同一個 resolver 物件。
  - 傳入值等於 `recorder.MARKET` 與兩個常數之和（531）。
  - 四種不呼叫 recorder 的情形（拋出例外、`ok` 為假、沒有 B、B < t0）各記對應那一行，且不寫 `forecast_run`。
  - RC-267 (a)：
    - 該筆記錄的 `getMessage()`、`msg` 都與常數逐字相同，`args == ()`，`exc_info`、`exc_text`、`stack_info` 都是空的。
    - 注入的例外訊息含路徑、價格與日期，整段 log 都找不到這段訊息。
    - 經 guard 執行時也沒有 traceback。
    - 另有 AST 檢查：job 內每個 WARNING 呼叫只傳一個裸常數，不帶 keyword，含 teeth。
  - 第三行：B 早於 `latest_completed_session(t0)` 時照常呼叫 recorder 並記這一行。AST 確認這條規則在 scheduler 中只用在那一處 if，而且 if 內只有那一行 log。
  - `KeyboardInterrupt`、`SystemExit` 不被吞。
  - 補跑時段：13:27、13:30、22:06 不設補跑，且 `add_job` 沒有 `next_run_time` 參數；13:26、22:07、22:10、週六 16:00 設補跑。不設補跑時 job 沒有被暫停，下一次在平日 22:10 觸發。

**三行 WARNING 的字面**（照第 2 點逐字）
- `forecast_record: the live index refresh did not succeed; the run is skipped and the cache is not used`
- `forecast_record: the newest cached index bar predates this run's start; the run is skipped`
- `forecast_record: the refreshed index series ends before the latest weekday session (an exchange holiday or a row missing at the source); the run continues`

## 驗證

- **全套**（最後一個 commit `a5c3434` 之後，含 `--cov=app --cov-fail-under=90`）：

  | 版本 | 結果 | coverage | 耗時 |
  |---|---|---|---|
  | 3.12 | 12833 passed、1 failed（R-1）、2 xfailed | 97.83% | 41:32 |
  | 3.13 | 12833 passed、1 failed（R-1）、2 xfailed | 97.83% | 37:01 |

  - 輸出檔：`/tmp/claude-0/-home-user-AICompany/3f76d891-50d3-55e1-b39d-925b8a90241a/scratchpad/round3-full-312.log`、`/tmp/claude-0/-home-user-AICompany/3f76d891-50d3-55e1-b39d-925b8a90241a/scratchpad/round3-full-313.log`
- **修正前那一次**（head `f85e0e5`）：
  - 3.12 多一個失敗：`test_no_holiday_data_is_added_to_app`，已由 `a5c3434` 修正。
  - 3.13 再多一個 `tests/test_r2_first_run.py::test_normal_flow_console_output_is_ascii_and_has_no_symbols`：輸出中的 `db_sha256` 十六進位雜湊碰巧含有「2330」。這是 R2 一鍵檔既有測試的偶發失敗，與本輪無關。單獨重跑在兩個版本都通過，我沒有修它。
  - 輸出檔：`/tmp/claude-0/-home-user-AICompany/3f76d891-50d3-55e1-b39d-925b8a90241a/scratchpad/round3-full-312-pre-fix.log`、`/tmp/claude-0/-home-user-AICompany/3f76d891-50d3-55e1-b39d-925b8a90241a/scratchpad/round3-full-313-pre-fix.log`
- **ruff 與 mypy**：`ruff check`、`ruff format --check`（566 檔）、`mypy app tests`（552 檔）在兩個版本都全過。輸出檔：`/tmp/claude-0/-home-user-AICompany/3f76d891-50d3-55e1-b39d-925b8a90241a/scratchpad/round3-lint-final.log`
- **零刪除**：`git diff --numstat df536340 HEAD -- …service.py …index.py` 的結果是 `154 0`、`138 0`。
- **「不得動」清單零差異**：
  - `git diff --stat df536340 HEAD -- apps/stock-desk` 只有 9 檔：`service.py`、`scheduler.py`、`index.py`、4 個新測試檔、`test_forecast_recorder.py`、`test_forecast_scheduler_wiring.py`。最後一個 commit 另外改了 `test_forecast_gap_disclosure.py`。
  - 以下這些對 `df536340` 零差異（`git diff --stat` 為空）：`app/forecast`（含 recorder、store）、harness 兩檔、`app/data/providers`、`cache.py`、`app/dirdef`、`app/outlook`、`uv.lock`、`scripts/`、所有 `.gitattributes`、所有 `.bat`。
  - `git diff --stat 9d5bbf48 HEAD -- apps/stock-desk` 共 22 檔。其中 forecast 四檔是前兩輪的改動，本輪沒有碰。
- **`code_digest`**：兩個版本算出來都是 `e8e0fb630a30361e3e0d2b34caa06b872c9e83609cc3b2b1b384581dc710d340`，與前一輪相同。M-4、M-5、RC-163 的 16 支測試在兩個版本都通過。

## 待決與偏離

1. **改了一支既有守門測試。**
   - 第三行字面含「exchange holiday」，所以 `test_no_holiday_data_is_added_to_app` 的白名單要加入 `scheduler.py`，否則會失敗。
   - 理由是這屬字面、不是日曆資料。前一輪 `report.py` 也是同樣處理。
   - 我另加一個斷言，把 `scheduler.py` 提到休市的地方釘成那一行字面，所以檢查變得更緊，不是更鬆。
   - 不過它不屬於 scheduler 自己的測試，請 qa 確認。
2. **例外與 log 的取捨。** 強制更新拋出 `Exception` 時，scheduler 只記第一行，不記類別、訊息或 traceback（RC-267 (a)）。代價是這類程式錯誤在 scheduler 的 log 看不到細節。
3. **其他照規格的選擇：**
   - 啟動補跑的時刻改由既有的 `_utc_now()` 取（原本是 `datetime.now(UTC)`），三個有啟動時刻的 job 都受影響，預設行為不變。
   - `force_refresh_benchmark` 的時鐘取自模組私有的 `_system_now()`，不是參數，測試以 monkeypatch 控制。
   - `start` 用 `date.fromordinal` 計算，結果與 `timedelta` 相同。這樣不用改 `index.py` 既有的 `from datetime import` 那一行，才能維持零刪除。
4. **沒有再 merge。** 開工 merge 之後，`origin/product/stock-desk` 又多了 3 個 docs commit（含風控 RC-265～RC-274 報告），我沒有再 merge。範圍清單引用了那份報告的路徑，它目前只在 product 分支上。

## 沒做或沒驗到的

- **新程式碼沒有被測到的行**：
  - `service.py` 第 592、614 行，是 equity 路徑才有 wording 的分支，指數路徑走不到。
  - `index.py` 第 490 行，是 `_system_now` 的本體，測試裡一律被 monkeypatch 替換。
- **沒有加 scheduler 層級的整合測試**（真服務加 scheduler 的完整一次執行）。整合測試是在 `app.services` 層走 recorder 的 `_fetch`，scheduler 層用假的強制更新測。
- **兩次背景執行被中斷過。** 第一次全套是在背景任務的時限機制下被終止的（exit 143），不是測試失敗。之後改用 detached 方式重跑，上面的數字都來自 detached 重跑的結果。
- **鐵則**：沒有讀 `.env`、沒有碰 `data/*.db`、沒有執行 `.bat`，也沒有 force push、rebase 或 amend；一鍵檔與 R-1 測試沒動。

## 下一步

1. 請 qa-reviewer 審查（含 Codex 第二意見）：重點是 RC-267 (a) 的測試、等價測試的四種狀態，以及「待決與偏離」第 1 點的白名單擴充。
2. PR 說明附上：零刪除的 numstat、三行字面，以及 RC-255 的 `git log -S` 核對（本 PR 內第一次註冊 `forecast_record` 與第 2、3 點同一次合併）。
3. 退役 PR 合併後，merge `origin/product/stock-desk`，確認 R-1 的失敗消失，再跑一次兩個版本的全套。
4. `test_r2_first_run.py` 的偶發失敗請轉 devops-sre／qa-automation。

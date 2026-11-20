# 接線 PR 第四輪交件（測試補強）

- 審查者：dev-lead
- 日期：2026-11-20
- 轉存：coordinator，逐字轉存 subagent 最終回報

---

## 本次結論

接線 PR 第四輪（只補測試）做完了，已推到 `origin/feat/nm5-wiring`。新的 head 是 `59b23e29f69ccd72eef94baadca8b2bdf05d2b62`。

- 第 1～6 項都做完。`app/` 一行都沒改：`git diff --stat a5c343433a722e325fd01f78974fff5cb1942c6f HEAD -- apps/stock-desk/backend/app` 是空的。過程中沒有遇到非改 `app/` 不可的情況。
- **第 4 項（N-11）全部成立。** 視窗未滿時已成立者，第一個完整視窗也成立；進入完整視窗後「自起點以來 F-2 曾否成立」為「是」，不會撤銷。不需要 tech-architect 裁示。
- 最後一個 commit 之後重跑了全套：
  - 3.12 與 3.13 都是 13436 passed、1 failed、2 xfailed，coverage 97.83%。
  - 唯一失敗的仍是預期中的 R-1 tree id 那一支。
- `code_digest` 仍是 `e8e0fb630a30361e3e0d2b34caa06b872c9e83609cc3b2b1b384581dc710d340`。

## 各項回報

| commit | 項目 | 測試 |
|---|---|---|
| `958d17a638441583d39b4deb06a5505ff8d41ed2` | 第 6 項：merge `origin/product/stock-desk` | — |
| `1651172504ba61857a0e27bb3e95bf30dac90c93` | N-9：scheduler 接真服務的整合測試 | `tests/test_scheduler_forecast_integration.py`，共 7 支 |
| `65937b9c4b2bd9f6214242d6570f4ce4e49d7f72` | N-12：`report.py` 休市字樣的行層級釘選 | `test_forecast_gap_disclosure.py` 的 `test_n12_report_mentions_a_holiday_only_in_the_rc248_first_heading`、`test_n12_the_report_holiday_scan_has_teeth` |
| `0427d3082eab5bdd796dff0c47299b06422b2823` | N-10：禁用集合與 log 掃描補強 | 見下 |
| `8a581d6ddf3c3924758ee6507cffaa4d93331672` | N-11：性質測試 | `test_forecast_f2_window.py`，見下 |
| `59b23e29f69ccd72eef94baadca8b2bdf05d2b62` | 第 5 項：範圍清單補 W-18 與「PR 說明用的材料」 | — |

**N-9：scheduler 接真服務的整合測試**
- 組裝：真的 `IndexSeriesService(MarketDataService(scope="index", cache_first=True, primary=IndexProviderBridge(假來源)))`，加上真的 `force_refresh_benchmark` 與真的 recorder；帳本先登記 h3、h5 兩個核心 claim 並發布定義。
- 只替換 `get_index_resolver`、`production_db_target` 與時鐘。四個時鐘共用同一個可調時鐘：scheduler 的 `_utc_now`、`app.services.index._system_now`、服務時鐘、store 時鐘。
- **偏離派工字面，請你看一下：** store 時鐘沒有別的注入點（`ledger_store` 固定用系統時鐘），我把 scheduler 的 `ledger_store` 換成「同一檔、帶這個時鐘的 `ForecastStore`」。這也算在時鐘替換裡。另有一支測試確認強制更新、recorder 與 loader 都是真的。
- 7 支測試：
  - `test_n9_a_normal_run_records_with_bars_fetched_by_this_run`：outcome `ok`，寫 2 筆 `late = 0`；快照中 T 日 bar 的 `as_of ≥ t0`；假來源恰被問一次。
  - `test_n9_a_t_bar_cached_at_17_45_is_replaced_by_this_runs`：快照中 T 日 bar 的時間戳是本次的，`base_close` 是修正後的收盤；增量請求從當月 1 日開始。
  - `test_n9_a_failing_source_records_nothing_and_does_not_use_the_cache`（拋例外、UNAVAILABLE 兩種）：只記第一行；`forecast_run`、紀錄、快照都是空的。
  - `test_n9_an_answer_without_t_and_a_17_45_t_bar_in_the_cache_skips_the_run`：記第二行，不寫 `forecast_run`。
  - `test_n9_an_answer_without_t_and_no_t_in_the_cache_records_t_minus_1_late`（低成本那一支有加）：記第三行，outcome `ok`，寫 2 筆 `late = 1` 的 T−1 紀錄。
  - `test_n9_the_rig_replaces_only_the_resolver_the_target_and_the_clocks`。

**N-10**
- 實作前先確認了：`refresh_daily_bars_live` 本來就沒有呼叫 `get_daily_bars` 或 `get_cached_bars`，它只用 `self._cache.get`。
- `FORBIDDEN_HELPERS` 加入這兩個。既有的 `test_the_helper_scan_has_teeth` 會對集合逐一檢查，所以新成員也有 teeth。
- `_log_violations` 的屬性集合加入 `log`、`critical`，`test_the_log_scan_has_teeth` 多 3 個樣本。

**N-11：性質測試**
- `test_n11_a_held_short_range_is_still_held_after_the_first_full_window`：5 組合成帳，帳隨時間增長（分母 20、12、0、19，以及 4 個缺漏加 3 天 inputs_not_ready 的混合）。
- `test_n11_arithmetic_every_numerator_7_to_20_holds_on_every_denominator_0_to_20`：純算術，294 組。
- `test_n11_the_store_holds_every_numerator_7_to_20_on_every_denominator_0_to_20`：同樣 294 組，逐一建帳，經真的 `f2_status`。
- `test_n11_six_is_not_enough_on_a_full_window_of_20`。
- 結果：全部成立，沒有任何一組反例。

**第 5 項：範圍清單的 PR 說明材料**
- **S-20a 的基準是 `d01bd9ee`。**
  - recorder.py 相對登記 PR 是 +67／−3（`ledger_store` 與 `warn_review_triggers`），相對 `d01bd9ee` 零差異。
  - `forecast_pipeline_harness.py`、`pipeline_acceptance_real.py`、`pipeline-acceptance.bat` 相對 `d01bd9ee` 零差異。
  - store.py 相對 `d01bd9ee` 只差在唯讀查詢（`f2_status` 的分母 0 規則、`grid_loss_status`）。
  - `test_forecast_pipeline_harness.py` 的 +17 是第二輪 RC-259 那一行的斷言，屬測試，不是 harness 本體。
  - 請 tech-architect 確認：「harness 三檔」我是這樣解讀的。
- **`price_bars_cache` 的 `put` 呼叫端：**
  - `service.py:398`（ladder）與 `service.py:597`（新方法）：`as_of` 是 provider 回傳 bar 自帶的請求時刻，`fetched_at` 是服務時鐘。
  - `app/demo/seed.py:438`：非正式路徑，只寫 demo 標的，不寫任何 `^` 代號。
- **N-13 列為已知取捨：** 強制更新失敗時 scheduler 只記固定 WARNING；provider 層的失敗另由 `app.data.service` 的 logger 記錄，對照時間可以查到。

## 驗證

- **全套**（head `59b23e2`，含 `--cov=app --cov-fail-under=90`）：

  | 版本 | 結果 | coverage | 耗時 |
  |---|---|---|---|
  | 3.12 | 13436 passed、1 failed（R-1）、2 xfailed | 97.83% | 42:40 |
  | 3.13 | 13436 passed、1 failed（R-1）、2 xfailed | 97.83% | 37:30 |

- 全套輸出：
  - `/tmp/claude-0/-home-user-AICompany/3f76d891-50d3-55e1-b39d-925b8a90241a/scratchpad/round4-full-312.log`
  - `/tmp/claude-0/-home-user-AICompany/3f76d891-50d3-55e1-b39d-925b8a90241a/scratchpad/round4-full-313.log`
- **ruff 與 mypy**：兩個版本都全過（`ruff check`、`ruff format --check` 567 檔、`mypy app tests` 553 檔）。輸出：`/tmp/claude-0/-home-user-AICompany/3f76d891-50d3-55e1-b39d-925b8a90241a/scratchpad/round4-lint.log`
- **鐵則**：沒有讀 `.env`、沒有碰 `data/*.db`、沒有執行 `.bat`，也沒有 force push、rebase 或 amend；一鍵檔與 R-1 測試沒動。

## 下一步

1. 請 qa 複核 N-9～N-12。特別請看 N-9 對 `ledger_store` 的時鐘替換是否可以接受。
2. 請 tech-architect 確認兩件事：N-11 維持字面（結果已由測試證明不會撤銷），以及 S-20a「三檔」的讀法。
3. 退役 PR 合併後，merge `origin/product/stock-desk`，確認 R-1 的失敗消失，再跑一次兩個版本的全套。

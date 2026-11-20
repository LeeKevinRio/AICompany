# 接線 PR 第二輪交件

- 審查者：dev-lead
- 日期：2026-11-20
- 轉存：coordinator，逐字轉存 subagent 最終回報

---

## 本次結論

接線 PR 第二輪做完了。新的 head 是 `df536340daad96b897ff6893a76a319b53ac592d`，已推到 `origin/feat/nm5-wiring`。

- 你指示的 14 項中，第 1～11、13、14 項都已做完；第 12 項（qa N-3）依 TA 裁示不做。
- RC-259（最近一次執行那一行）也已提前做完。
- 補充十第 2、3 點**待規格**，我沒有動手：一項等 data-engineer 的方法規格，一項等補充十最終版。依 RC-255，這兩點要和 job 註冊同一次合併。
- 最後一個 commit 之後重跑了全套，3.12 與 3.13 都是 12753 通過、1 失敗。唯一失敗的是預期中的 R-1 tree id 測試（`test_cg2_register_values.py::test_r1_the_app_tree_constant_is_the_app_tree_of_this_checkout`），照補充九第 1 點保留紅燈，等退役 PR。
- 新的 `code_digest` 是 `e8e0fb630a30361e3e0d2b34caa06b872c9e83609cc3b2b1b384581dc710d340`。

## 各部門回報

**dev-lead：本輪 commit 與對應測試**

| commit | 內容 | 對應測試 |
|---|---|---|
| `ff5ddd81cef27b2aab4ad45a371da090ad685dce` | 補充九第 3 點：scheduler 只記錄進預設正式主 DB；含 qa N-4、N-5 | `test_forecast_scheduler_wiring.py`：`test_s19a_a_refused_target_does_not_call_the_recorder`（有設變數、空字串、目標不同、檔案不存在、目標是目錄）、`test_s19a_each_refusal_is_one_fixed_line_without_a_path`、`test_s19a_the_default_target_calls_the_recorder`、`test_the_production_target_is_derived_from_the_module_location`、`test_s19a_the_scheduler_reads_no_env_file` 與其 teeth、`test_a_keyboard_interrupt_passes_through_the_guarded_job`、`test_an_empty_registry_closes_the_gate_and_writes_only_the_run_rows`。既有測試改用 monkeypatch `production_db_target`，job 不加路徑參數（K-10）。 |
| `88faa9179534094d347c75e66e118fc2baf5b971` | 補充九第 4 點：完整視窗分母為 0 一律判成立 | `test_s19a_a_full_window_with_no_final_session_and_nothing_counted_holds`、`test_s19a_a_short_range_with_nothing_counted_is_still_not_held`。原本沒有「0/0 未成立」的預期，所以不必改舊測試。 |
| `2335e3c12b97875e8d12ae5faf5e0cdfffce54d8` | 補充九第 5 點：store 新增 `grid_loss_status`（回傳 G、L、三態判定、曾否成立，經 `_read`） | `test_s19a_no_d_v_is_undecidable`、`test_s19a_d_v_whose_cutoff_has_not_passed_is_undecidable`、`test_s19a_one_of_five_is_not_held`、`test_s19a_two_of_nine_holds`、`test_s19a_an_earlier_prefix_held_and_ever_held_stays`、`test_the_grid_points_are_counted_only_once_their_cutoff_passed`、`test_the_grid_loss_query_needs_an_aware_now_and_only_reads` |
| `861e8cb90e4791f259dfd228b1e54907d37e0e02` | 套用 F-2 段的風控定稿字面（RC-238、RC-239、RC-242、RC-247～RC-252）；含 RC-240／qa N-1 | `test_forecast_gap_disclosure.py`：`test_rc252_*` 六項、RC-230 四件事改套 RC-251 字面；`test_forecast_f2_window.py`：`test_the_report_prints_*`、`test_the_undecidable_second_sentence_has_no_ever_held`、`test_the_grid_loss_verdict_is_derived_in_store_py_only`；`test_forecast_report.py`：`test_rc240_the_n_hat_exemption_is_exactly_one_line`、`test_rc240_a_near_copy_of_the_exempt_line_is_still_caught`（多一字、改一字、少一字）；harness 測試補「段內固定行恰一次、不進 `render_summary`」 |
| `f6da84689af301f8f05ff0532768543f3820a936` | qa N-6：缺 T 的測試釘死唯一預期 | `test_a_missing_t_falls_back_to_the_previous_final_bar_late`（`ok` 加兩筆 `late = 1`）、`test_a_missing_t_after_t_minus_1_was_recorded_is_no_new_session` |
| `213162bc24a99ca8beb73cda499673d279295bb2` | qa N-2：全 `app/` 掃描 | `test_n2_only_the_scheduler_imports_the_core_from_outside_it`、`test_n2_the_core_package_imports_are_as_they_stand`、`test_n2_the_whole_app_scans_have_teeth` |
| `ce6c9470dda2abf3d70152ea9fe8b14333ceca2b` | RC-259：最近一次留下執行紀錄的執行 | `test_rc259_the_constants_are_the_approved_text`、`test_rc259_without_a_run_row_the_none_variant_is_printed`、`test_rc259_the_latest_run_is_the_highest_run_id_in_taipei_time`、`test_rc259_both_variants_carry_the_note_and_pass_the_d4_checks`；harness 完整輸出恰一行、`render_summary` 不含 |
| `e3c4f0373f4a2cb7206abaa26da05208413bc83f`、`df536340daad96b897ff6893a76a319b53ac592d` | 範圍清單更新（第 1、2、13、14 項與 RC-259、待規格項） | — |

另有一個 merge commit 用來取得 `origin/product/stock-desk` 上的新報告。

**範圍清單的變動**（`/home/user/AICompany/.claude/worktrees/agent-a36eaaf09f5b7743b/work/reviews/2026-11-19-接線PR範圍清單-dev-lead.md`）
- W-7：一鍵檔各項加註「由退役 PR 刪除（補充九第 1 點）」。
- P-2：加入「不加 CI 測試；只填有出處的值，沒有出處標『無出處』」。
- 第三節依補充九第 7 點改寫，I-5 寫成「不寬於」；第四節改為已裁示。
- 第五節是本輪全部使用者面字面的出處表（哪份報告、哪個項目），並列出四句拒絕原因的固定英文 log（RC-246：不含路徑，也不含要求改設定的祈使句）。

**字面如何寫入與比對**
- 所有字面都用腳本從風控報告抽出寫進 `report.py`，沒有手打。
- `tests/approved_copy.py` 改為依標籤抽取：RC-244～254 與 RC-255～264 兩份依「項目：」標籤；RC-237～243 那份依前一行的標籤。每份報告都斷言抽到的標籤集合恰為預期。
- 作廢的兩行（RC-237 段標題、RC-238 分母 0）有測試確認沒有被使用。
- 測試先從報告抽出模板，代入值後再與輸出逐字比對。

**執行狀態段的實際輸出順序**
1. 執行狀態
2. 執行次數
3. inputs_not_ready 日數（全部期間）
4. RC-259 最近一次執行
5. 段標題
6. 第一句小標題
7. 第一句各行
8. 第二句小標題
9. 第二句各行
10. 行動句
11. `GAP_DISCLOSURE`
12. 重審觸發各行
13. `REVIEW_GAP_DISCLOSURE`

前三行維持原本的相對位置，這點沒有疑義。原本的「第 0 相位格點 … 個」行已由第二句各行取代。

**有兩處不是逐字照你的指示做，請你看一下**
- **RC-259 的查詢**：我沒有新增函式，直接用 store 既有的唯讀查詢 `latest_run`（走 `_read`）。
- **休市資料守門測試**：`app/` 提到「休市」的檔案白名單多了 `forecast/report.py`，理由是 RC-248 小標題的字面含「不扣休市日」，屬字面而不是日曆資料；測試裡有註明這點。

## 驗證
- **全套測試**（含 `--cov=app --cov-fail-under=90`），在最後一個 commit 之後重跑：
  - 3.12：12753 passed、1 failed、2 xfailed，coverage 97.83%。
  - 3.13：12753 passed、1 failed、2 xfailed，coverage 97.83%。
  - 唯一失敗的是 R-1 tree id 那一支。
- **ruff 與 mypy**：ruff check、ruff format --check、mypy app tests，3.12 與 3.13 都全過。
- **「不得動」零差異**：
  - 以 `git diff --stat 9d5bbf48 HEAD -- apps/stock-desk` 檢查，有差異的只有 `app/forecast` 四檔、`app/scheduler.py` 與 tests。所以 `uv.lock`、`.gitattributes`、`app/dirdef`、規則 YAML、`app/outlook`、`app/data`、`app/services`、`scripts/`（含一鍵檔）、三個 `.bat`、cg2 測試、harness 本體 `tests/forecast_pipeline_harness.py` 全部零差異。
  - 根目錄 `.gitattributes`、事先宣告、C-8 紀錄、兩份 CEO 操作說明、`work/` 下兩個 `.gitattributes` 也零差異。
- **已登記雜湊不變**：dirdef 與規則檔零差異；M-4、M-5、RC-163 的測試在兩個版本都通過。
- **N_HAT_NOTE**：有測試釘住它與接線 PR 之前逐字相同。
- **測試輸出檔**：`/tmp/claude-0/-home-user-AICompany/3f76d891-50d3-55e1-b39d-925b8a90241a/scratchpad/full-312.log`、`/tmp/claude-0/-home-user-AICompany/3f76d891-50d3-55e1-b39d-925b8a90241a/scratchpad/full-313.log`。
- 鐵則都遵守：沒有讀 `.env`、沒有碰 `data/*.db`、沒有執行 `.bat`、沒有 force push、rebase 或 amend。

## 下一步
1. **待規格**：補充十第 2 點（data-engineer 的方法規格）與第 3 點（補充十最終版）。收到後實作，並與 job 註冊同一次合併（RC-255）。
2. **待退役 PR**：退役 PR 合併後，在本分支 merge `origin/product/stock-desk`，確認 R-1 的失敗消失，再跑一次全套（3.12、3.13）。
3. **合併前由 coordinator 補齊**：CG-3 值（沒有出處的照實標「無出處」）、帳外缺日比對的 commit 與 CEO 確認紀錄、CEO 本機執行 `report verify --all` 的結果；PR 說明要附 RC-230、RC-233／RC-234、RC-237～RC-254、RC-259 的出處。
4. **請 qa 重審**：N-1、N-2、N-4、N-5、N-6，以及 S-19a 第 3～5 點。
5. 若風控對補充九第 3～5 點再有改動，請通知我。

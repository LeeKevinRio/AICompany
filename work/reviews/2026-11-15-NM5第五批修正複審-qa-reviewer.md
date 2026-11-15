# NM-5 第五批修正複審

- 審查者：qa-reviewer
- 日期：2026-11-15
- 轉存：coordinator，逐字轉存 subagent 最終回報

---

## 本次結論
**PASS（程式碼審查結論，未重現測試；Codex 不可用，依 CEO #58 記為單家審查）**

`BLOCKING_ISSUES=false`。你列的 7 項 BLOCKING 判準都成立。白名單項本批沒做，dev-lead 有如實揭露，不列 BLOCKING。

限制：
- 沒跑過任何測試，`11682 passed` 未經重現。
- `codex --version` 回報 command not found，無第二意見。
- 舊版 `ZERO_WIDTH` 的字面字元我讀不出來，只能靠測試的 code point 釘死來確認值不變（見第 6 項）。

## 各部門回報（逐項判準）

1. **上次 BLOCKING：成立。**
   - `report.py` 的 `prediction_text`（約 L146 起）把 `unavailable` 輸出成 `unavailable:<reason>`。
   - `label_cells`（records）與 `render_compare`（`texts = {key: prediction_text(p) ...}`）都走同一個函式，格式一致。
   - `scoring.py` 的 `BaselinePrediction.from_stored`（L90–L116）要求 unavailable 一定有非空文字 reason，且有標籤的不得有 reason。
   - 舊資料缺 reason 時：`records` 拒絕輸出（exit 3），`compare` 列 `record_unreadable`。測試 `test_a_stored_unavailable_baseline_without_its_reason_is_never_printed_bare` 覆蓋。
   - `d4_violations`（`test_forecast_report.py`）新增 regex，擋 `B?=unavailable` 無原因、空原因、`None` 三種。
   - 反例共 6 個（含 B1、B8 結尾）。正例是 `test_compare_lists_an_unavailable_b2_with_its_reason_as_records_does`，並做 compare 與 records 的 cell 逐格比對。
2. **C5-1：成立。**
   - harness 輸出改用 `report.render_execution_status`，不含 `render_review_trigger`（`forecast_pipeline_harness.py` L461–L465）。
   - `render_summary` 不含 n̂、T1／T2。
   - 測試 `test_the_output_holds_no_n_hat_while_report_status_does`：完整輸出與 summary 對 7 個標記（n̂、`N_HAT_NOTE`、`T1=`、`T2=`、重審觸發、`c₁=`、`d₁=`）都不命中；`report status` 照列，且 `render_status` 等於兩段串接。
3. **C5-2：成立。**
   - `render_summary` 只剩 pass／fail、視窗 session 數、各 outcome 的執行次數、失敗種類、兩個 hash（L570–L585）。
   - `records_written`、失敗項目數都移除。
   - 我同意「視窗定案 session 數：21」可保留。理由：`WINDOW_SESSIONS` 是 `Final = 21` 的常數，`acceptance_window` 不足 21 就 raise `HarnessRefused`，所以不隨輸入或紀錄變動，不是紀錄筆數。
   - 「執行次數：ok=21」是 D-4 point 5 允許的執行狀態。
   - 測試 `test_the_summary_lists_no_record_count` 整份鎖死。
4. **C5-5、補充五第 3 點：成立。**
   - (a) `vacuous_failures` 對 `HORIZONS` 每個 h 要求 `compared_by_horizon[h]`。該旗標只有在「非 insufficient、baseline 可用、`compared.reason is None`」時才會設。`where` 只有 `P-0 h5` 這種規則加 horizon。
   - (b) `record_failures` 先判 `baseline_unavailable`，與 `label_differs` 互斥（`if / elif`）。該筆之後 `continue`，不會被誤報成標籤不符。
   - (c) `missing_not_iff_insufficient` 是 `insufficient != (missing != [])`，兩個方向都成立。
   - 反例 fixture 齊全：
     - `test_record_failures` 7 個 param，含兩個方向。
     - `test_vacuous_failures` 4 個 param。
     - 整體 fixture：全部 insufficient、h3 有 h5 沒有、`_SplitRules` 只讓 P-0 h5 全 insufficient、B2 在 130 根 bar 下不可用。
     - sigma 退化與短 bars 的舊測試也改成預期 vacuous。
   - 白名單：dev-lead 交件第 13–28、51、80、122 行明講沒做、等 TA 裁示 A 或 B，揭露屬實。
5. **數值不變：成立。**
   - `z_score` 是 `ret / (sigma_d * math.sqrt(horizon))`，與兩處原內聯算式（baselines `ret / (sigma.value * math.sqrt(horizon))`、scoring `forward_return / (threshold.sigma_d * math.sqrt(horizon))`）逐字相同。
   - 測試 `test_z_score_is_the_inline_formula_bit_for_bit` 用 `==` 比對 30 組。
   - AST 測試鎖定 `sqrt` 只出現在 `z_score`、scoring 沒有 `sqrt`，兩邊都呼叫 `z_score`。
   - `scoring` 的 `import math` 已移除，沒有殘留用法。
   - `git diff --stat` 顯示 `main.py`、`scheduler.py`、`outlook/rules/**`、`dirdef/**` 零 diff。規則檔本身沒動，所以四個規則雜湊不變。我沒讀 hash 測試的內容。
6. **待辦 1、2、5：成立。**
   - 待辦 1：`run_acceptance` 與 `refuse_production` 的 `backend_dir`、`env`、`cwd` 都是 keyword-only、無預設值（L189–L190；`run_acceptance` 的簽名在 diff 中）。`os`、`BACKEND_DIR`、`Path.cwd` 已從 harness 移除。測試用 `inspect.signature` 加原始碼字串雙重鎖定。我 grep 過，兩個函式的所有呼叫點都傳了 tmp_path 替身。
   - 待辦 2：`ZERO_WIDTH` 改成 `\u` escape，內容為 200b、200c、200d、2060、feff、00ad 六個 code point，與原 docstring 列的六種一致。測試以排序後的 code point 釘死，並檢查原始碼不含任何字面零寬字元。
   - 待辦 5：`_material_uses` 涵蓋 Name、Attribute、ImportFrom（含 alias）、字串引數（getattr）。結果必須恰為 `{forecast/report.py}`，`definitions.py` 本身不得使用，並有 6 個 teeth 反例與 docstring 排除測試。
7. **合成資料與 tmp_path：成立。**
   - 新測試全用 `tmp_path`、`synthetic_series` 與 `_stand_in`。
   - `report.main(... "--db", str(ledger))` 指向 tmp 帳。
   - 沒看到任何路徑指向真實 `data/`。

## 驗證
- 方法：讀完 11 檔的完整 diff，並對 worktree 檢查 `WINDOW_SESSIONS`、`acceptance_window`、`refuse_production` 與呼叫點。
- 未做：沒有跑測試，Codex 不可用，單家審查。

**凍結後待辦（皆非 BLOCKING，不影響紀錄、PIT、雜湊、正式 DB 或 D-4）**
- `test_forecast_registered_material.py` 的 `_material_uses`：下標寫法 `vars(mod)["registered_ruleset"]`、字串拼接的 `getattr`、`__all__` 清單都抓不到。這是測試層的深度防禦，建議補成「任何出現該字串常數的 AST 節點」。severity low。
- `test_forecast_claims_cli.py` 的 `test_a_spaced_phrase_in_the_rules_is_a_scan_hit`：`"零 風險"` 改成 ` `。我看不出舊字面是普通空白還是 NBSP，若舊的是普通空白，此測試的覆蓋形式略有改變。severity low。
- `FailureKind.verify_inconsistent` 的 `where` 含 `item.problem`。目前值是固定代碼（例如 `registered_material_rejected`），不含標籤。建議之後加測試鎖定它不可帶標籤字樣。severity low。

## 下一步
1. 放行這批（單家審查註記）。
2. 等 TA 裁示 missing code 白名單選 A 或 B，再做下一批。該批須補「code 屬於 §2.5 四類」的反例 fixture。
3. 上述三項低風險待辦併入凍結後清單。

審查範圍：`518046f9..a2c2f38f`，worktree `/home/user/AICompany/.claude/worktrees/agent-ad78bd45a459a429e/apps/stock-desk/backend/`。

BLOCKING_ISSUES=false

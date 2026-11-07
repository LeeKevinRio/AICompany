# N-199 交件（偵測工具新增 N-197 (b) 事後檢查）

- 審查者：data-engineer
- 日期：2026-11-07
- 轉存：coordinator，逐字轉存 subagent 最終回報

---

## 本次結論
N-199 已完成並 push 到 `origin feat/stock-desk-n199-probe-checks`，沒有 merge 進 product。

- head commit：`e13f3164707b63828789ca7c664f15a79af0e3e2`
- worktree：`/tmp/claude-0/-home-user-AICompany/3f76d891-50d3-55e1-b39d-925b8a90241a/scratchpad/wt_n199`
- 相對 commit 的 parent，diff 只有兩個檔（+756／-5）：
  - `apps/stock-desk/backend/scripts/n177_n190_backtrack_probe.py`
  - `apps/stock-desk/backend/tests/test_n177_n190_backtrack_probe.py`
- `git diff --stat origin/product/stock-desk` 會多出 12 個檔、約 2800 行刪除。這是我 push 之後才看到的：origin/product/stock-desk 在我開 worktree 之後又往前走了，分支底子是 3994a0e。不是我改的，合併前要 rebase 或確認。

做了什麼：
- 實作 N199-A、N199-B、N199-C（C 列為 required，SQL 註解寫 `required, risk R6`）。
- 照 spec 加了四個 SQL 常數、`classify_n199`、`ENUM_VALUES["batch_status"]`、報告摘要三列與三個章節。
- 加了 L12～L14。`SCRIPT_VERSION` 改為 "2"，`SCHEMA_VERSION` 維持 1。
- 追加項目：
  - stdout 在 `n199_c_rows=` 之後加印 `script_sha256_lf=`、`db_sha256_before=`、`db_sha256_after=`、`run_at_utc=`。值取自 report.json 的 meta，只在 exit 0 印出。
  - docstring 的 RC-6 段落加了「Only the CEO reads the report files; no agent reads them.」。
  - 加了 R12：預設禁止讀報告，只有同一次測試執行中、由測試在 tmp_path 自建的合成 DB 所產生的報告可以讀；不得對非測試自建的 DB 手動執行工具。
  - 原工具文字本來就沒有「coordinator 轉交」的路徑。
- 唯讀約束沒有放寬：
  - `mode=ro`、`query_only`、只用 stdlib；
  - 前後 SHA-256；
  - exit codes 0、2、3、4 不變，命中時仍是 exit 0；
  - `--out-dir` 必須在 repo 外；
  - `open(..., "x")`。

## T1～T12 的 node id
前綴都是 `apps/stock-desk/backend/tests/test_n177_n190_backtrack_probe.py::`。

- T1：`test_n199_t1_fill_not_booked_is_listed_with_every_column`
- T2：`test_n199_t2_fill_not_booked_misses`
- T3：`test_n199_t3_same_batch_blocked_hits_and_seconds`
- T4：`test_n199_t4_same_batch_blocked_misses`
- T5：`test_n199_t5_multi_executed_buys`
- T6：`test_n199_t6_s11_parity_with_the_store_g1_condition`
  - 400 組隨機 book，固定 seed 199；
  - 與 `store.BATCH_LEFT_PLANNED_SQL` 組出的集合比對，預期集合大於等於 10 筆。
- T7：`test_n199_t7_real_store_paths`
  - 只用 `claim_directive`、`settle`、`record_directives`；
  - (i)、(ii)、(iii) 都在同一個測試裡。
- T8：`test_n199_t8_s2_covers_the_new_constants`
  - SQL 常數數量釘為 25+4。
- T9：
  - `test_n199_t9_report_sections_stdout_and_json`：三列三節、stdout、JSON，以及追加的四行、白名單、不含 symbol。
  - `test_n199_t9_a_v1_report_is_still_a_usable_previous_json`：v1 報告當 `--previous-json`。
- T10：`test_n199_t10_unexpected_values_are_sanitized_and_free_text_stays_out`
- T11：`test_n199_t11_hits_leave_exit_zero_hash_and_two_files`
- T12：`test_n199_t12_fixed_wording_has_no_advice_words`

另外動到的測試：
- `test_rc6_the_module_documents_that_the_report_is_private` 新增斷言：docstring 有 CEO 專讀句，且不含 "coordinator"。
- 這個測試沒有獨立的 node id，不計入 T1～T12。

## CI 數字
在最終程式碼上，從 worktree 的 backend 目錄、借用主 checkout 的 `.venv` 跑完：
- `ruff check`：All checks passed。
- `ruff format --check`：494 files already formatted。
- `mypy app tests`：Success, no issues found in 485 source files。
- `pytest --cov=app --cov-fail-under=90`：9908 passed、1 skipped、2 xfailed，耗時 859.74 秒。
- 總覆蓋率 97.62%，門檻 90% 達成。
- 工具測試檔單獨跑是 134 passed、1 skipped。

## 與 spec 的偏離
1. **既有測試被改了四處。** spec 說「既有測試原樣綠燈」，但版本、頂層鍵、限制代碼的改動本身就會讓它們失敗，所以只改了預期值：
   - `version=1` 改成 `version=2`；
   - 頂層鍵集合加入 `"n199"`；
   - 兩處限制代碼清單從 `L1..L11` 改成 `L1..L14`。
2. **N199-B 以 (已成交列, 待結算列) 配對計一列。** 同一批有兩筆已成交加一筆 pending 時，B 計 2 列。這是照 spec 的 SQL 與 JSON 形狀，不是去重。T9 的世界資料因此是 B=2。
3. **Snapshot 新增的四個欄位帶 default**（`field(default_factory=...)`），放在 dataclass 尾端，以免動到既有建構方式。
4. **T6 用單一 DB、400 個 symbol 各一個 book**，沒有逐 book 開 400 個 DB。每組 book 的條件仍獨立。
5. **T7 的 (iii) 另開一個新 DB。** 原因：(i) 之後再走 (ii) 的流程，批次已經 open，G1 會擋下第二張 R1 的 claim。新 DB 讓兩張 R1 都在批次仍是 planned 時被 claim，最後一張再 `settle`，得到 C=1、A=0。
6. T8 對「新常數只以綁定參數執行」的檢查，除了數 `?` 的個數，還檢查原始碼含 `conn.execute(N199_BATCH_BUYS_SQL, key)`。
7. 我自己的一個疏失：中途兩次因為又改了腳本，把已經在跑的完整 pytest 砍掉重跑，所以上面的 CI 數字是最後一版程式碼的結果。

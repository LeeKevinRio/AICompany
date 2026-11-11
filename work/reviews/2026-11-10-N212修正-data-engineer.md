# N-212修正（TA與qa意見、P-8b）

- 審查者：data-engineer
- 日期：2026-11-10
- 轉存：coordinator，逐字轉存 subagent 最終回報

---

## 本次結論
N-212 依 TA A 組與 qa F1～F8 修改完成，並加做 coordinator 追加的 P-8b。已推送，新 head 為 8df88d6fabdb1cc75faecb2611583e9ae0a7d8e9（原 b3c59247 的 fast-forward，無 force、無 rebase）。

兩點偏離任務單，請知悉：
- 分支 `feat/n212-n207-preflight` 已被另一個 worktree（agent-a76f658044d99f915）佔用，我無法在自己的 worktree checkout 同名分支。改用本地分支 `n212-local` 追蹤 `origin/feat/n212-n207-preflight`，以 `git push -u origin HEAD:refs/heads/feat/n212-n207-preflight` 推送，第一次即成功。
- 全套 pytest 是在 P-8b 加入之前跑的。P-8b 加入後我只重跑了 `tests/test_n207_preflight.py`。P-8b 只動 scripts 與該測試檔，不影響 `app/` 覆蓋率。

沒有出現規格與實測不符的情形：T30 補齊八個值後，實測 P-4a=7、P-4c=4，預期值未改。

## 各部門回報（data-engineer）
三個 commit，皆為繁中 Conventional Commits，並附兩行 Co-Authored-By 與 Claude-Session：
1. `6398ae9` fix: N-212 參數守衛改用 json_type 並補 p3 範圍註解與測試
2. `f141dfa` fix: N-212 runner 整數守衛、最外層 catch-all、URI 改用 as_uri 並補外洩測試
3. `8df88d6` feat: N-212 新增 P-8b 盤點項（RC-110 第 1 點）

### 必做項與對應測試
測試都在 `apps/stock-desk/backend/tests/test_n207_preflight.py`。

1. **TA A-7（含 qa F1）**
   - 測試：`test_guard_non_integer_key_is_an_error`
     - 對 p1、p2、p3 各跑 `null`、`true`、`false`、`3.0`、`5.5`、`"3"`、`[3]`、`{"a":1}`，結果皆為 ERROR。
   - 測試：`test_guard_payload_that_is_not_an_object_is_an_error`
     - payload 為 `'3'`、`"x"`、`[1,2]`、`null`、`true`、`3.0`，結果皆為 ERROR。
   - 測試：`test_guard_invalid_json_is_an_error`
     - 壞 JSON 結果為 ERROR。
   - 測試：`test_guard_absent_key_applies_the_default`
     - key 不存在時套用預設值。
   - 測試：`test_guard_integer_key_is_used`、`test_guard_only_looks_at_the_current_row`、`test_guard_is_evaluated_with_batches_present`
   - 測試：`test_sql_default_literals_equal_ruleparams_defaults`
     - 已改成解析新 CASE 結構的預設值字面常數。
2. **多值逗號格式**
   - 整數守衛：`test_any_bad_cell_turns_the_whole_line_into_error`、`test_bool_cell_is_not_an_integer`。
   - 逐字釘住整行輸出：`test_multi_value_lines_are_pinned_verbatim`，釘住 `P-2\t1,2,1,1,0` 與 `P-3\t4,9`。
   - 順序寫入 docstring：`test_runner_docstring_documents_the_cell_order`。
3. **TA A-1**
   - 測試：`test_p3_header_states_its_pre_deployment_scope_and_has_no_entry_stopped_condition`。
   - p3 檔頭已加英文註解，p3 沒有 `entry_stopped` 條件。
4. **TA A-5**
   - 測試：`test_p5_positive_and_negative`、`test_p5_counts_a_null_status_on_a_table_without_the_constraint`。
   - 現況原本就是讀原檔；現在以 `_run_p5_file` 明確執行磁碟上的 `p5.sql` 原文，並斷言 `SQL_DIR` 指向打包目錄。
5. **qa F2**
   - 測試：`test_p4_t30_seeding_gives_p4a_7_and_p4c_4`。
   - 種入 0、1、2、-1、'x'、0.5、'1'、1.0，並斷言型別序列為 integer×4、text、real、integer×2。
6. **qa F3 與 TA A-洩漏 (c)**
   - 測試：`test_catch_all_prints_only_the_fixed_string`、`test_catch_all_covers_read_only_uri`、`test_nul_in_path_is_an_error_without_traceback`。
   - `main` 外層加 catch-all，只印 `PREFLIGHT\tERROR`（`ABORTED_LINE`）並回 1。
   - `read_only_uri` 已放進 `run` 的 try，捕捉 `sqlite3.Error`、`ValueError`、`OSError`；其餘例外落到 `main` 的 catch-all。
7. **qa F4**（subprocess）
   - 測試：`test_cli_missing_file_prints_no_path_and_empty_stderr`、`test_cli_corrupt_file_prints_no_path_and_empty_stderr`、`test_cli_directory_as_db_path_prints_no_path_and_empty_stderr`、`test_cli_empty_file_is_an_error_not_a_zero`、`test_cli_very_long_path_prints_no_path_and_empty_stderr`。
   - NUL 路徑無法放進 argv，所以用 in-process 的 `main` 測（見第 6 項）。
8. **TA A-洩漏 (a)(b)**
   - 測試：`test_items_is_a_fixed_tuple_and_the_runner_never_scans_a_directory`
     - 以 AST 確認 runner 內沒有 glob、listdir、iterdir、scandir、walk 等呼叫。
   - 測試：`test_output_has_one_tab_separated_line_per_item_and_no_symbol`
     - 現在種入 `high_volatility=1` 的代號 HVONE1、HVONE2、6488。
     - 測試先直接執行 p4b 的 SQL，確認這些代號確實會被列出，再斷言 runner 輸出不含它們。p4b 若被誤納入，測試就會失敗。
   - 既有的 `test_runner_never_reads_p4b` 仍在。
9. **TA suggested 與 qa F5**
   - 測試：`test_path_with_special_characters_is_opened`
     - 路徑參數：`a b#c?d%`、`含 中文?#路徑`、`x?mode=rw#y`、前後有空白。
     - 斷言 URI 等於 `resolve().as_uri() + "?mode=ro"`，且只含一個 `?`。
10. **F6、F7**
    - F6：冗餘斷言我保留，並在同一個測試補上 p4b 的實質斷言；正則斷言才是真正承擔鑑別力的部分。
    - F7：AST import 檢查擋不住 `__import__` 或 importlib 動態載入。這個腳本約 100 行、風險極低，只記錄、不改。

### P-8b（coordinator 追加）
- `p8b.sql` 照 TA 原文，已加進 `ITEMS`，排在 P-8 之後（P-2、P-3 的列位置不變）。
- 測試：
  - `test_p8b_empty_tables_answer_zero`
  - `test_p8b_confirmed_without_total_deploy_key_is_one`（A8 狀態）
  - `test_p8b_confirmed_with_total_deploy_key_is_zero`（反例）
  - `test_p8b_total_deploy_key_alone_is_zero`
  - `test_p8b_a_parameter_row_also_counts_as_confirmed`
  - `test_p8b_sql_error_is_an_error_line`
  - `test_p8b_is_wired_after_p8_and_literals_match_the_store`

## 驗證（實際輸出）
- `ruff check .`：All checks passed。
- `ruff format --check scripts tests/test_n207_preflight.py`：11 files already formatted。
- `mypy app`（strict）：Success, no issues found in 189 source files。
- `tests/test_n207_preflight.py`（含 P-8b）：199 passed。
- 全套 `pytest --cov=app --cov-fail-under=90`（P-8b 之前、含 F1～F8 修改後）：10100 passed、1 skipped、2 xfailed；覆蓋率 97.62%，門檻 90% 已達。
- 使用的是主 checkout 的 venv（python 3.13）。`app` 是從該 venv 載入，可能指向主 checkout 的 app。
- 全程未讀 `.env`、未碰 `data/*.db`，測試皆用 `tmp_path`。

### 修改後 SQL 全文
p1.sql
```sql
-- P-1: number of symbols whose batch count differs from batches_per_target (bpt).
-- Read-only pre-deployment inventory item. Prints one count; never a symbol or an amount.
-- Current parameter row: WHERE / ORDER BY identical to PlaybookStore.active_params;
-- on_date is Taipei today (UTC+8, Taiwan has no DST). Defaults mirror RuleParams().
-- Pre-deployment every symbol is on round 1 (no batch_round column yet).
-- Drafted by data-engineer; semantics pending tech-architect review.
-- Parameter guard (TA A-7): key absent -> RuleParams default; payload not a JSON object, or key
-- present but not a JSON integer (null / true / real / text / ...) -> NULL -> the runner prints
-- ERROR; a payload that is not valid JSON makes json_type fail -> ERROR. The app would reject
-- the same rows, so an inventory that silently applied the default would point the wrong way.
WITH cur AS (
  SELECT payload FROM playbook_rule_params
  WHERE effective_date <= date('now', '+8 hours')
  ORDER BY effective_date DESC, version DESC LIMIT 1
),
bpt AS (
  SELECT CASE
    WHEN NOT EXISTS (SELECT 1 FROM cur) THEN 3
    WHEN json_type((SELECT payload FROM cur)) <> 'object' THEN NULL
    WHEN json_type((SELECT payload FROM cur), '$.batches_per_target') IS NULL THEN 3
    WHEN json_type((SELECT payload FROM cur), '$.batches_per_target') = 'integer'
      THEN json_extract((SELECT payload FROM cur), '$.batches_per_target')
    ELSE NULL
  END AS v
)
-- The outer CASE forces bpt to be evaluated even when the table is empty.
SELECT CASE WHEN (SELECT v FROM bpt) IS NULL THEN NULL ELSE (
  SELECT COUNT(*) FROM (
    SELECT symbol FROM playbook_batches
    GROUP BY symbol
    HAVING COUNT(*) <> (SELECT v FROM bpt)
  )
) END;
```

p2.sql
```sql
-- P-2: five counts, comma-joined by the runner, in this order:
--   (1) symbols whose MAX(batch_no) > bpt
--   (2) symbols whose MIN(batch_no) <> 1
--   (3) symbols whose MIN(batch_no) < 1
--   (4) symbols with a gap: COUNT(*) <> MAX - MIN + 1
--   (5) rows whose batch_no is not stored as INTEGER (typeof(batch_no) <> 'integer')
-- Read-only pre-deployment inventory item. Prints one count; never a symbol or an amount.
-- Current parameter row: WHERE / ORDER BY identical to PlaybookStore.active_params;
-- on_date is Taipei today (UTC+8, Taiwan has no DST). Defaults mirror RuleParams().
-- Drafted by data-engineer; semantics pending tech-architect review.
-- Parameter guard (TA A-7): key absent -> RuleParams default; payload not a JSON object, or key
-- present but not a JSON integer (null / true / real / text / ...) -> NULL -> the runner prints
-- ERROR; a payload that is not valid JSON makes json_type fail -> ERROR. The app would reject
-- the same rows, so an inventory that silently applied the default would point the wrong way.
WITH cur AS (
  SELECT payload FROM playbook_rule_params
  WHERE effective_date <= date('now', '+8 hours')
  ORDER BY effective_date DESC, version DESC LIMIT 1
),
bpt AS (
  SELECT CASE
    WHEN NOT EXISTS (SELECT 1 FROM cur) THEN 3
    WHEN json_type((SELECT payload FROM cur)) <> 'object' THEN NULL
    WHEN json_type((SELECT payload FROM cur), '$.batches_per_target') IS NULL THEN 3
    WHEN json_type((SELECT payload FROM cur), '$.batches_per_target') = 'integer'
      THEN json_extract((SELECT payload FROM cur), '$.batches_per_target')
    ELSE NULL
  END AS v
),
per_symbol AS (
  SELECT MIN(batch_no) AS mn, MAX(batch_no) AS mx, COUNT(*) AS cnt
  FROM playbook_batches
  GROUP BY symbol
)
SELECT
  -- The CASE forces bpt to be evaluated even when the table is empty.
  CASE WHEN (SELECT v FROM bpt) IS NULL THEN NULL
       ELSE COALESCE(SUM(mx > (SELECT v FROM bpt)), 0) END,
  COALESCE(SUM(mn <> 1), 0),
  COALESCE(SUM(mn < 1), 0),
  COALESCE(SUM(cnt <> mx - mn + 1), 0),
  (SELECT COUNT(*) FROM playbook_batches WHERE typeof(batch_no) <> 'integer')
FROM per_symbol;
```

p3.sql
```sql
-- SCOPE (TA A-1): this file equals the ADR-0043 D1 enabled-symbol count ONLY on the schema that
-- exists before N-207 is deployed. Before deployment playbook_batches has no entry_stopped
-- column, so every symbol in the list counts as enabled. After N-207 is deployed this file
-- must NOT be used again to decide R-14. Do not add an entry_stopped condition: before
-- deployment it would fail with a missing-column error.
-- P-3: two values, comma-joined by the runner: (1) distinct symbols in playbook_batches,
-- (2) n_targets in force. (1) > (2) means STOP-2. Definition per R-14.
-- Read-only pre-deployment inventory item. Prints one count; never a symbol or an amount.
-- Current parameter row: WHERE / ORDER BY identical to PlaybookStore.active_params;
-- on_date is Taipei today (UTC+8, Taiwan has no DST). Defaults mirror RuleParams().
-- Drafted by data-engineer; semantics pending tech-architect review.
-- Parameter guard (TA A-7): key absent -> RuleParams default; payload not a JSON object, or key
-- present but not a JSON integer (null / true / real / text / ...) -> NULL -> the runner prints
-- ERROR; a payload that is not valid JSON makes json_type fail -> ERROR. The app would reject
-- the same rows, so an inventory that silently applied the default would point the wrong way.
WITH cur AS (
  SELECT payload FROM playbook_rule_params
  WHERE effective_date <= date('now', '+8 hours')
  ORDER BY effective_date DESC, version DESC LIMIT 1
),
nt AS (
  SELECT CASE
    WHEN NOT EXISTS (SELECT 1 FROM cur) THEN 5
    WHEN json_type((SELECT payload FROM cur)) <> 'object' THEN NULL
    WHEN json_type((SELECT payload FROM cur), '$.n_targets') IS NULL THEN 5
    WHEN json_type((SELECT payload FROM cur), '$.n_targets') = 'integer'
      THEN json_extract((SELECT payload FROM cur), '$.n_targets')
    ELSE NULL
  END AS v
)
SELECT COUNT(DISTINCT symbol),
       CASE WHEN (SELECT v FROM nt) IS NULL THEN NULL ELSE (SELECT v FROM nt) END
FROM playbook_batches;
```

## 下一步
1. qa-reviewer 在 head 8df88d6 上重審：
   - 核對 A-洩漏 (a)(b)(c)。
   - 獨立重跑全套 pytest（我在 P-8b 之後沒有重跑全套）。
   - Codex 第二意見先前無法取得，需補。
2. devops-sre 覆核 p1、p2、p3、p8b 的 SQL 文字。
3. tech-architect 可確認一點：p1、p2、p3 的 `json_type(...) <> 'object'` 依 TA 原文，payload 為 SQL NULL 時會落到「key 不存在、套預設值」。`playbook_rule_params.payload` 是 `TEXT NOT NULL`，所以實務上不會發生。
4. F5 的 Windows 路徑：改用 `as_uri()` 後，`file:///C:/...` 形式由標準函式庫產生，但我只在 Linux 驗證過。

相關檔案（絕對路徑，皆在 `/home/user/AICompany/.claude/worktrees/agent-a3b6c1373ab2cb1b6/apps/stock-desk/backend/` 下）：
- `scripts/n207_preflight/p1.sql`、`p2.sql`、`p3.sql`、`p8b.sql`
- `scripts/n207_preflight/run_preflight.py`
- `tests/test_n207_preflight.py`

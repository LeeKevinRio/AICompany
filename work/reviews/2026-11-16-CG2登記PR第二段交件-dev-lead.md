# CG-2 登記 PR 第二段交件（bootstrap CLI）

- 審查者：dev-lead
- 日期：2026-11-16
- 轉存：coordinator，逐字轉存 subagent 最終回報

---

## 本次結論
CG-2 登記 PR 的第二段已完成並 push。分支是 `feat/nm5-cg2-registration`，head 為 `2ce29a9c0789f4ca15f1644a288931ae640ccad4`（`git ls-remote` 已確認）。
- product 以 merge 併入，沒有衝突，也沒有 rebase。
- `git merge-base --is-ancestor 8b22c114f201e34218758452da310617baab42da HEAD`：成立，結束碼 0。
- Python 3.12 與 3.13 全套測試都通過，各 12161 passed，0 failed。
- `store.py`、`schema.py` 與其他指定檔案都是零差異。

有三點需要 TA 或 coordinator 確認，都是在「不放寬既有邊界」與「照字面做」之間取捨：

1. **沒有在 claims.py 做 `mode=ro` 的提早表檢查。**
   - 附記第 3 點要求這項檢查只用 `mode=ro`。但做這項檢查，claims.py 就必須自己呼叫 `sqlite3.connect` 和 `execute`，而既有測試 `test_claims_writes_only_through_the_store_and_has_a_plain_main_block` 禁止 claims.py 出現這兩種呼叫；補充七第 6 點也寫明「既有的 claims.py 測試不放寬」。
   - 我改成完全依靠交易內的檢查：`create_objects` 拋 `SchemaNotEmptyError`，CLI 以結束碼 4 結束。補充七第 3 點本來就規定以交易內的檢查為準，交易外的檢查只用來提早停止，而一鍵檔的 R-4 已經涵蓋這個提早停止。
   - 測試 `test_4_existing_ledger_objects_are_refused_in_the_transaction` 確認結束碼為 4，而且主檔位元組、物件清單、資料夾內容都不變。
   - 如果 TA 仍要求 claims.py 自己做這項提早檢查，需要先核可放寬上述測試，例如只允許一個 `mode=ro` 的唯讀 helper。
2. **改了 `tests/test_forecast_boundaries.py` 的 import 白名單一行**：加入 `app.forecast.schema.SchemaNotEmptyError`。補充七第 5 點規定交易內的 `SchemaNotEmptyError` 要回結束碼 4，claims.py 必須能辨認這個類別。性質和前置 PR 的 `WRITE_METHODS` 一樣，但這一項沒有明文許可。
3. **`claims.py` 的 `_parser` 與 `main` 的 AST 和 product 不同。**
   - `_parser` 加了 1 行 `_add_bootstrap_parser(commands)`；`main` 在 `parse_args` 之後加了 4 行，遇到 `bootstrap` 子命令就交給 `bootstrap_main`。
   - 補充六第 6 點 (d) 允許「CLI 分支」，而這兩個函式不在 harness 的呼叫路徑上；`__main__` 區塊的既有測試要求它維持 `raise SystemExit(main())`，所以子命令一定要經過 `main`。
   - harness 會呼叫到的 `register`、`production_path_refusal`、`_phrase_scan_lines`、`_same_file`，以及 `claim_id`、`count_m`、`m_eff`、`RegistrationRefused`，AST 都與 product 相同。
   - coordinator 說「既有頂層函式只能新增」，按字面這兩個函式不符，請確認可以接受。

## 各部門回報（dev-lead）

**Commits**（接在 `c79e831` 之後）
- `cba794b`：merge `origin/product/stock-desk`。用的是 git 預設的 merge 訊息，沒有署名行；因為禁止 amend，所以沒有補上。
- `3ebe8f4`：`feat: claims CLI 新增 bootstrap --production（…）`
- `2ce29a9`：`test: RC-163 抽取規則遇標題 0 次或多次、缺圍欄時一律判失敗`

**變更檔案**（相對於 product）
- `app/forecast/claims.py`
  - 新增頂層定義：`BOOTSTRAP_COMMAND`、`EXIT_POST_COMMIT_CHECK_FAILED=5`、`BOOTSTRAP_HORIZONS`、固定句表 `BOOTSTRAP_PATH_REFUSALS`／`BOOTSTRAP_REFUSALS`／`POST_COMMIT_CHECK_FAILED`、`BootstrapRefused`、`_add_bootstrap_parser`、`repo_relative_path_ok`、`env_file_sets_db_path`、`production_target`、`git_blob`、`bootstrap_claim_inputs`、`post_commit_check`、`bootstrap_main`。
  - 加入 CLI 分支（見上面第 3 點）。模組 docstring 沒有動。
- `app/dirdef/registry.py`、`app/dirdef/v1_0.py`：第一段的登記值，merge 後不變。
- 測試：
  - 新增 `tests/test_forecast_claims_bootstrap.py`。
  - `test_forecast_bootstrap.py`：斷言翻轉。
  - `test_forecast_boundaries.py`：import 白名單加一行。
  - `test_cg2_registration_values.py`：RC-163 抽取規則改為遇錯一律失敗。
  - 另有第一段已改的 5 個測試檔。

**8 項清單逐項對應的測試**
1. 呼叫邊界
   - `test_forecast_bootstrap.py::test_s15_only_the_claims_cli_calls_bootstrap`：全 `app/` 中呼叫 `bootstrap` 的模組恰為 `{"forecast/claims.py"}`。
   - `test_forecast_claims_bootstrap.py`：
     - `test_claims_calls_bootstrap_from_its_bootstrap_branch_only`：claims.py 內只有 `bootstrap_main` 呼叫它。
     - `test_the_bootstrap_branch_calls_no_other_write_path`：分支內不呼叫 `register_claim`、`register`、`_write`、`_connect`、`create_objects`、`create_schema`、`execute`、`connect`，也不呼叫其他寫入方法。
     - `test_the_bootstrap_branch_calls_only_bootstrap_and_read_queries_on_the_store`：對 store 只呼叫 `{bootstrap, ledger_schema_status, forward_claims, runs, provisional_results_seen}`。
     - `test_the_post_commit_check_reads_only`：成功一次只有一個寫入交易（`fresh=True`）。
2. 建立 store 前的檢查（結束碼 4，不建立任何檔案）
   - `test_4_the_production_database_is_missing`：另斷言該路徑仍不存在、data 夾是空的。
   - `test_4_the_production_database_resolves_elsewhere`：symlink 指到別處。
   - `test_4_the_production_database_is_not_a_regular_file`
   - `test_4_the_environment_names_a_database[""/"other.db"]`
   - `test_4_the_env_file_names_a_database[3 種寫法]`
   - `test_an_env_file_without_the_key_does_not_refuse`：對照組。
   - `test_no_test_here_names_the_real_backend`：每個 `claims.main` 呼叫都帶替身 `backend_dir`。
3. 結束碼
   - 4：
     - `test_4_existing_ledger_objects_are_refused_in_the_transaction[4 種]`
     - `test_4_a_second_bootstrap_is_refused`
     - `test_4_the_two_claims_must_be_h3_then_h5[reversed/one/h3_twice/three]`
     - `test_4_a_replacement_is_refused`
   - 3：
     - `test_3_a_store_refusal_writes_nothing`：等時鐘逾時。
     - `test_3_an_unpublished_version[definition/rule_set]`
     - `test_3_a_banned_phrase_is_refused`
     - 第 5、6 項所列的格式與核對測試。
   - 預期外的例外：`test_unexpected_exceptions_propagate[RuntimeError/OperationalError]`。
   - 所有 3 與 4 的測試都經 `_refused` 斷言：主檔 sha256、`sqlite_master`、非帳本表、data 夾內容都不變，stdout 為空，stderr 恰為固定句。
4. 提交後核對（結束碼 5）
   - `test_5_a_failed_post_commit_check_stops_without_retry`，共 5 種情境：schema 不完整、兩列不符、`runs` 非空、兩列的值不符、`LedgerInconsistentError`。斷言 bootstrap 只呼叫一次（不重試），且兩列已提交。
   - 先驗 schema：`test_5_the_schema_is_checked_before_the_typed_value_is_read`（執行期）、`test_the_post_commit_check_reads_the_schema_first`（AST 順序）。
5. `provisional_results_seen`
   - `test_bootstrap_registers_both_claims_with_the_typed_value[0/1]`：兩列的值與鍵入值相同，輸出有 `provisional_results_seen=<0|1>`。
   - `test_3_a_typed_value_that_is_not_0_or_1_writes_nothing`：10 種無效輸入，含空白、`01`、`true`、全形 `１`。
   - `test_2_the_typed_value_has_no_default`：不給這個參數時 argparse 結束碼 2，不寫入。
   - `test_the_typed_value_has_no_default_and_no_other_source`（AST）：參數為 required，沒有 `default`、沒有 `choices`，分支內不讀環境變數或檔案。
6. `prereg_doc_path` 格式與 `--prereg-doc-sha256`
   - `test_3_the_prereg_path_format_is_checked_not_converted`：12 種，涵蓋 `./`、`..`、`\`、磁碟代號、絕對路徑、`//`、結尾 `/`、前置空白、空字串。
   - `test_3_the_review_refs_format`
   - `test_3_the_prereg_sha256_format`
   - `test_3_the_prereg_blob_must_match_the_sha256`
   - `test_3_the_working_tree_bytes_do_not_count`
   - `test_3_the_prereg_blob_must_exist_at_the_commit[path_not_in_the_commit/commit_not_in_the_repo]`
   - `test_the_stored_blob_is_the_commits_not_the_working_tree`
   - `test_3_the_frozen_commit_format`
   - 這些測試用的是 `tmp_path` 內的臨時 git repo。
7. RC-163 抽取規則：`test_cg2_registration_values.py`
   - `test_rc163_the_extraction_rule_fails_closed`，共 7 種：標題 0 次、標題 2 次、沒有圍欄、圍欄落在下一個標題之下、圍欄不是 yaml、缺結尾圍欄、結尾圍欄後有空白。
   - 另有 `test_rc163_the_extraction_rule_has_teeth`，以及在 HEAD 上比對 blob 的 `test_rc163_the_rule_file_blob_is_the_freeze_pack_block`。
8. 回傳內容
   - `test_bootstrap_registers_both_claims_with_the_typed_value`：逐行 fullmatch `OUTPUT_FORMS` 共 16 行，並斷言不含 tmp 路徑、`/`、`\`、`|`、`outlook-market`、`dirdef-v`、`stock-desk`。
   - `test_the_output_names_the_registered_hashes`：輸出的雜湊等於實際登記列的值。
   - 所有拒絕測試同樣檢查 stderr 不含路徑與代號。

## 驗證

**零差異**（比對 `origin/product/stock-desk`，用 scratchpad 腳本 `/tmp/claude-0/-home-user-AICompany/3f76d891-50d3-55e1-b39d-925b8a90241a/scratchpad/check_cg2.py`）
- 以下檔案全部零差異：
  - `tests/forecast_pipeline_harness.py`、`tests/dirdef_helpers.py`、`tests/outlook_helpers.py`
  - `scripts/pipeline_acceptance_real.py`、`uv.lock`
  - 兩份規則 YAML
  - `app/forecast/store.py`、`app/forecast/schema.py`、`app/main.py`、`app/scheduler.py`
  - 凍結包、事先宣告、C-8 紀錄檔
- `app/` 的差異只在 `dirdef/registry.py`、`dirdef/v1_0.py`、`forecast/claims.py`。
- 前置 PR 改過的四個 docstring（registry.py、`dirdef/__init__.py`、definition.py、definitions.py）都沒有再改。

**`code_digest`**（HEAD）：`75e82809220a3450a59df611917e0de73dd39fb896b8e2958d7215c59355b72b`。它和 M（前置 PR 合併 commit）上的值不同，因為改了 claims.py 和 registry、也新增了 `v1_0.py`。

**全套測試**（HEAD `2ce29a9`）

| 環境 | `app.__file__` | 結果 | 覆蓋率 |
|---|---|---|---|
| Python 3.13.17（預設 `.venv`） | 本 worktree 的 `apps/stock-desk/backend/app/__init__.py` | 12161 passed、2 xfailed、0 failed | 97.81% |
| Python 3.12.3（專屬 venv `/tmp/claude-0/-home-user-AICompany/3f76d891-50d3-55e1-b39d-925b8a90241a/scratchpad/venv312-cg2`，merge 後重新 `uv sync`） | 同上 | 12161 passed、2 xfailed、0 failed | 97.81% |

- `ruff check .`、`ruff format --check`：全過。
- `mypy app tests`：537 個檔沒有問題。

**給 devops-sre 的介面說明**
```
python -m app.forecast.claims bootstrap --production \
  --rules-version outlook-market-v1.0-h3 --rules-version outlook-market-v1.0-h5 \
  --definition-version dirdef-v1.0 \
  --frozen-commit <40 碼小寫 hex，建議取 HEAD> \
  --prereg-doc-path work/research/2026-10-15-3日5日方向判斷-事先宣告草案.md \
  --prereg-doc-sha256 7c45b0ba79e04a7a74a2b8bc91603cb0bfbd78101b51ab8403cc4ed45a4b406e \
  --review-refs "<repo 相對路徑，以單一空白分隔>" \
  --provisional-results-seen <CEO 鍵入的 0 或 1，原樣傳入>
```
- 目標固定是 `<backend>/data/stock-desk.db`，`<backend>` 由模組位置導出，沒有 `--db` 參數。
- 不要傳 `--replaces-claim-id`；傳了就以結束碼 4 拒絕。
- 結束碼：
  - 0：登記成功，提交後核對也成立。
  - 2：參數用法錯誤（argparse），包括漏給 `--provisional-results-seen`。
  - 3：其他拒絕，不寫入。
  - 4：路徑、環境變數、`.env`、已有帳本物件（交易內判定）、h3／h5 順序、取代，不寫入。
  - 5：已提交但核對不成立。不得重試，一鍵檔應 STOP。
- 拒絕時 stdout 為空，stderr 只有一行固定句，各句見 `claims.BOOTSTRAP_PATH_REFUSALS`、`BOOTSTRAP_REFUSALS`、`POST_COMMIT_CHECK_FAILED`。
- 成功時 stdout 恰好 16 行，依序為：
  1. `bootstrap=ok`
  2. `banned_phrase_scan_h3=hits 0 rules_strings <n> definition_strings <n> phrases <n>`
  3. `banned_phrase_scan_h5=hits 0 rules_strings <n> definition_strings <n> phrases <n>`
  4. `registered_rows=2`
  5. `frozen_commit=<40hex>`
  6. `prereg_doc_sha256=<64hex>`
  7. `definition_sha256=<64hex>`
  8. `definition_logic_sha256=<64hex>`
  9. `rules_sha256_h3=<64hex>`
  10. `rules_logic_sha256_h3=<64hex>`
  11. `registered_at_h3=<YYYY-MM-DDTHH:MM:SS.ffffff+00:00>`
  12. `rules_sha256_h5=<64hex>`
  13. `rules_logic_sha256_h5=<64hex>`
  14. `registered_at_h5=<同上格式>`
  15. `provisional_results_seen=<0|1>`
  16. `post_commit_check=ok`

**PR 說明草稿要點**
- M-1：「harness 通過」的回貼尚未產生。CEO 那一次的 `git_head` 必須能到達 M，並以那個 head 重做 (d) 比對與 RC-163 比對。
- M-2：
  - 路徑 `work/research/2026-10-15-3日5日方向判斷-事先宣告草案.md`
  - blob `d1e4d06a4e1c1a06158ad33a481050fe44bf8ae1`
  - sha256 `7c45b0ba…406e`
  - 最後一次變更在 `ed9275321b0be82bce5c8f3f97a2e31bb3abeb34`（RC-153～157）
  - 指令 `git cat-file blob HEAD:<path> | sha256sum`
- M-3：
  - 路徑 `work/dispatch/2026-11-15-C8決策紀錄-F2B.md`
  - blob `e664f147f2c5339e321ae333b7ce3c7d35ebcda7`
  - sha256 `c942642c…a54f`
  - 自 `7883f12e846d23b86670092dad01e543763bdc4b` 起零差異
- M-4：
  - logic `4cc1fe80054a017f47030805a486ad81e1bda249d730c7c1f6bd2c73c01d1afa`
  - full `2a58bca61c647931ecaf56aa5d17e4bfffc048c30944f3550feceadbfdacc4d0`
  - 以測試釘住
- M-5：h3 `f4f366a5…3443`／`ddd3c51a…4484`，h5 `0a385de3…707c`／`e5310b8e…f1bb`，以測試釘住。
- M-6：禁詞比對命中 0（每個規則集 159 個字串，定義 12 個字串，禁詞 10 個）。
- M-7：**尚未落實。** 兩份 YAML 與 M-2、M-3 兩份文件都是 `i/lf w/lf`，但沒有 `eol=lf` 屬性，只有 `uv.lock` 有 `attr/text eol=lf`。屬性要放在哪裡（例如 `apps/stock-desk/backend/.gitattributes` 加 YAML，`work/` 底下另加一個 `.gitattributes`），要在 CG-2 PR 內決定，而且不得讓 main 綁定產品路徑。我沒有自行決定，請指派。
- M-8：屬一鍵檔，由 devops-sre 負責。本 PR 已提供第 2、3 點的每個拒絕條件、整筆回滾與「回傳不含路徑」的 CLI 層測試。
- M-9：待 qa（含 Codex）、風控、CI 與 `report verify --all`。
- R-1～R-8：屬一鍵檔，本 PR 沒有做。
- `definition_sha256` 計算時點（qa 提的）：前置 PR 起，`definition_sha256` 和 `definition_logic_sha256` 在 `_prepare_claim` 內、交易開始之前就算好，原本是在交易內才算。值不變，物件是 frozen。
- `git merge-base --is-ancestor 8b22c114f201e34218758452da310617baab42da HEAD`：成立（結束碼 0）。

## 下一步

**自定解讀**
1. `--provisional-results-seen` 是必填參數，由一鍵檔把 CEO 的鍵入原樣傳進來；CLI 只接受字串 `0` 或 `1`，其他值都以結束碼 3 拒絕，也不做 trim。
2. 用 `--rules-version` 給兩次的方式表達「一次給齊 h3、h5，依此順序」：以已登記的 horizon 判斷順序，不符就回結束碼 4。版本未發布則回 3。
3. `--replaces-claim-id` 保留成選填參數，只是為了讓「取代」這個拒絕條件可以測試；只要給了就回 4。
4. `--review-refs` 以單一空白分隔，每一段都要符合 repo 相對路徑的格式；不檢查檔案是否存在。
5. 拒絕時只印固定句，不帶例外文字，因為例外文字可能含 claim_id。
6. 禁詞比對在登記前、對兩個規則集各跑一次；有命中就回 3，輸出只有計數。
7. `.env` 的鍵名比對方式和 `scripts/pipeline_acceptance_real.py` 相同（utf-8-sig、`^\s*STOCK_DESK_DB_PATH\s*=`），但沒有 import 那支腳本。環境變數只要存在就拒絕，空值也一樣。

**已知限制**
- 本節開頭的三點待確認。
- M-7 尚未落實。
- merge commit 沒有署名行。
- claims.py 的模組 docstring 仍寫「結束碼 0、2、3、4」與「production registration 由 CG-2 PR 決定」，已經過時。因為 (d) 沒有列 docstring，我沒有改；新行為寫在新函式的 docstring 裡。

**後續**
1. TA 或 coordinator 裁示上面三點與 M-7 的屬性位置。
2. 交 qa-reviewer 審查（含 Codex）。
3. devops-sre 依上面的介面說明實作一鍵檔與預檢。
4. CEO 在能到達 M 的 head 上跑真實資料驗收。之後以那一次的 `git_head` 重做 (d) 比對與 RC-163 比對，再合併。

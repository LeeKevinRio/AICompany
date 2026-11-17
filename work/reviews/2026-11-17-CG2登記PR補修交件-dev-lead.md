# CG-2 登記 PR 補修交件（補充七附記二與 RC-180～RC-183）

- 審查者：dev-lead
- 日期：2026-11-17
- 轉存：coordinator，逐字轉存 subagent 最終回報

---

## 本次結論
重啟前要求的四項，在重啟前就已經 commit 並 push 了。這一輪沒有新增程式或測試，只在 `5be3b953437da2b327a1fbaf37c581571e16cd2c` 上重跑驗證：Python 3.12 與 3.13 全套各 12180 passed、0 failed，ruff、mypy 全過。

- head：`5be3b953437da2b327a1fbaf37c581571e16cd2c`，本地與遠端一致（`git ls-remote` 已確認），工作樹乾淨。
- 有一項我自行改了既有測試，請 TA 或 coordinator 確認：
  - 檔案：`tests/test_pipeline_acceptance_real_eol.py::test_the_backend_attribute_file_pins_uv_lock_to_lf`。
  - 原因：這個測試原本把 `apps/stock-desk/backend/.gitattributes` 釘成只有 `uv.lock` 一行；照附記二第 5 點加兩行之後，它在 3.13 全套中失敗。
  - 改法：改成逐位元組釘住三行，`uv.lock` 那一行仍是第一行、內容不變（commit `5be3b95`）。
  - 這是附記二第 5 點的直接結果，但不在任何零差異清單內，也沒有明文許可。

## 各部門回報（dev-lead）

**四項的現況**（自 `2ce29a9` 起的 commit）
1. 附記二第 6 點（模組 docstring）：已在 `da586a9` 完成。
   - 只動了 `body[0]`，寫出 `bootstrap --production` 與結束碼 0、2、3、4、5，不含雜湊、claim_id 值，也沒有「已登記／未登記」字樣。
   - 由 `test_the_module_docstring_names_bootstrap_and_every_exit_code` 驗證。
2. RC-180：已在 `da586a9` 完成，測試名稱見下面「驗證」。
3. RC-181（claims 側）：已在 `da586a9` 完成。
   - `Desk.state()` 改為以邏輯狀態為主要證據：`iterdump` 全文，加上 `journal_mode`、`user_version`、`application_id`、`page_size`。
   - 主檔 sha256 與資料夾清單，只在主檔旁沒有 `-wal` 時才比較。
   - 用到 `state()` 的拒絕測試（`_refused` 及其他直接比較 `state()` 的測試）都套用這個判定。
   - 既有的拒絕測試都建立在沒有 `-wal` 的合成 DB 上，所以原本並沒有對有 `-wal` 的情境比對雜湊；這次改的是「雜湊不再是唯一證據」。
   - 合成 DB 另外設了 `user_version=7`、`application_id=21316`，讓這兩個 pragma 的比對有意義。
4. RC-183：已在 `dc30ed4` 完成。
   - 三個 `.gitattributes` 的內容由 `test_rc183_each_gitattributes_file_holds_exactly_its_lines[3 個檔]` 逐行釘住，多一行或少一行都會失敗。
   - `test_rc183_the_lines_use_no_wildcard_and_only_text_eol_lf` 檢查屬性只有 `text eol=lf`，且沒有萬用字元。

**其他已完成**
- 附記二第 4 點（`da586a9`）：`store.bootstrap` 回傳之後，到印出成功輸出為止，任何 `Exception` 只印固定句，以結束碼 5 結束；組輸出的部分抽成 `bootstrap_output`。`BaseException` 不捕捉。
- 附記二第 7 點（`da586a9`）：`git_blob` 呼叫 git 時移除所有 `GIT_*` 環境變數，並加 `--no-replace-objects`。
- 兩次 merge product：`7736573`、`e59a1ef`，訊息都是 `chore: 合併 origin/product/stock-desk`，附署名行與 Claude-Session 行。
- 舊的 merge `cba794b` 沒有署名行，要在 PR 說明揭露。

## 驗證

**全套測試**（head `5be3b95`；輸出在 `/tmp/claude-0/-home-user-AICompany/3f76d891-50d3-55e1-b39d-925b8a90241a/scratchpad/final_313.txt` 與 `/tmp/claude-0/-home-user-AICompany/3f76d891-50d3-55e1-b39d-925b8a90241a/scratchpad/final_312.txt`）

| 環境 | `app.__file__` | 結果 | 覆蓋率 |
|---|---|---|---|
| 3.13.17（預設 `.venv`） | 本 worktree 的 `apps/stock-desk/backend/app/__init__.py` | 12180 passed、2 xfailed、0 failed | 97.81% |
| 3.12.3（專屬 venv `/tmp/claude-0/-home-user-AICompany/3f76d891-50d3-55e1-b39d-925b8a90241a/scratchpad/venv312-cg2`，已重新 `uv sync`） | 同上 | 12180 passed、2 xfailed、0 failed | 97.81% |

- `ruff check .`：All checks passed。`ruff format --check`：549 個檔都已格式化。`mypy app tests`：537 個檔沒有問題。
- `code_digest`（HEAD）：`3f7366ad6e98e7530a953cc781648cfda7b97077cbfd0c874d9fefd3f004060b`

**RC-180 測試名稱**（給 qa 親自重驗，都在 `tests/test_forecast_claims_bootstrap.py`）
- `test_rc180_a_refused_bootstrap_makes_no_logical_write`，共 4 種：`[forecast_object-no_wal]`、`[forecast_object-wal]`、`[plan_object-no_wal]`、`[plan_object-wal]`。
  - 共同斷言：結束碼 4；執行前後 `iterdump` 相同；四個 pragma 不變。
  - trace 驗證：用 trace callback 包住 store 的連線；只開一條連線，有 `BEGIN IMMEDIATE`，最後一句是 `ROLLBACK`，沒有 `COMMIT`，也沒有任何 CREATE、INSERT、UPDATE、DELETE、DROP、ALTER、VACUUM、REPLACE 或 `PRAGMA journal_mode`。
  - 有 `-wal` 的兩種：另開一條 holder 連線，讓含未 checkpoint 列的 `-wal` 一直留在主檔旁，並斷言 dump 看得到那一列；不比對檔案雜湊。
  - 沒有 `-wal` 的兩種：`.db` 的 sha256 不變，資料夾內只有 `stock-desk.db`。
- `test_rc180_the_write_statement_pattern_has_teeth`：證明上述語句比對確實會擋下寫入語句。
- `test_rc180_an_exit_3_store_refusal_makes_no_logical_write`：結束碼 3，情境是等時鐘逾時，觸發交易內的 `ForecastStoreError`。
  - `iterdump` 與四個 pragma 不變，最後一句是 `ROLLBACK`，沒有 `COMMIT`，sha256 不變，沒有側檔。
  - 這條路徑在交易內確實執行過 CREATE 與第一列 INSERT，之後整筆回滾，所以這裡不斷言「trace 不到寫入語句」，改以邏輯狀態與 ROLLBACK 作證。
- `test_rc180_an_exit_3_input_refusal_opens_no_connection`：鍵入值無效時，一條連線都沒有開。

**S-15b 逐條證據**
- 第 1 點：claims.py 沒有 `connect`、`execute`；既有測試 `test_claims_writes_only_through_the_store_and_has_a_plain_main_block` 沒有改，照常通過。R-4 屬一鍵檔。
- 第 2 點：`tests/test_forecast_boundaries.py` 對 product 的 diff 恰好兩行，性質不同，分開列出：
  - (a) import 白名單加 `"app.forecast.schema.SchemaNotEmptyError",`，只有這一行，屬附記二第 2 點。
  - (b) 第一段就加的模組清單 `"dirdef/v1_0.py",`，因為新增了 `app/dirdef/v1_0.py`。
- 第 3 點：遞移集合的 AST 比對（對 `origin/product/stock-desk`）
  - `register`、`production_path_refusal`、`_phrase_scan_lines`、`_same_file`、`claim_id`、`count_m`、`m_eff`、`RegistrationRefused`：全部相同。
  - `_parser` 的 diff 只有 `+    _add_bootstrap_parser(commands)` 一行。
  - `main` 的 diff 只在 `args = _parser().parse_args(argv)` 之後加了 4 行：
    ```
    +    if args.command == BOOTSTRAP_COMMAND:
    +        return bootstrap_main(
    +            args, env=os.environ if env is None else env, backend_dir=backend_dir, clock=clock
    +        )
    ```
- 第 4 點：`test_5_an_exception_after_the_commit_is_the_fixed_sentence`，核對中、組輸出中各注入 `OperationalError` 與 `RuntimeError`，共 4 種，都斷言結束碼 5、stderr 恰為固定句加換行、stdout 為空、不重試。另有 `test_a_base_exception_after_the_commit_is_not_caught`。
- 第 5 點：見下面 RC-183。
- 第 6 點：逐一比對頂層節點，結果如下。
  - product 既有的節點中，只有 `body[0]`、`_parser`、`main` 不同。
  - 其餘差異都是新增：3 個 import（`hashlib`、`stat`、`subprocess`）、`from app.forecast.schema import SchemaNotEmptyError`、各個常數與固定句表、`BootstrapRefused`，以及 bootstrap 分支的函式 `_add_bootstrap_parser`、`repo_relative_path_ok`、`env_file_sets_db_path`、`production_target`、`git_blob`、`bootstrap_claim_inputs`、`post_commit_check`、`bootstrap_main`、`bootstrap_output`。
- 第 7 點：
  - `test_git_blob_ignores_git_variables_that_point_elsewhere`：`GIT_DIR`、`GIT_WORK_TREE` 指向另一個 repo 時，仍取得本 checkout 的 blob。
  - `test_git_blob_ignores_replace_refs`：git 一般讀到的是 replace 後的內容，`git_blob` 仍取得原始 blob。

**RC-183 證據**
- `git ls-files --eol`：四個檔與 `uv.lock` 都是 `i/lf w/lf attr/text eol=lf`。
- `git check-attr eol text`：五個檔都是 `eol: lf`、`text: set`。
- blob id 與加屬性前相同：

| 檔案 | blob id |
|---|---|
| h3.yaml | `1b032ac5438c7eed7b515a87e5b716ccedce6ce0` |
| h5.yaml | `eec7cad331e3dc6a1dda99ba0bcea2c7a43ac313` |
| 事先宣告（M-2） | `d1e4d06a4e1c1a06158ad33a481050fe44bf8ae1` |
| C-8 紀錄檔（M-3） | `e664f147f2c5339e321ae333b7ce3c7d35ebcda7` |
| `uv.lock` | `36173efab5298c852c55e673d1a5532c49d62ce6` |

- 四個檔與 `uv.lock` 的工作樹 sha256，加屬性前後用 `sha256sum -c` 比對，全部 OK。
- 用 blob 重算：
  - `git cat-file blob HEAD:work/dispatch/2026-11-15-C8決策紀錄-F2B.md | sha256sum` 得 `c942642c1958e6259545c4f64b4202fbafecf585f1f2cbe513961190af0ea54f`，等於 `c8_decision_sha256` 的登記值。
  - 事先宣告的 blob 重算為 `7c45b0ba79e04a7a74a2b8bc91603cb0bfbd78101b51ab8403cc4ed45a4b406e`，等於 M-2。
- 兩個新的 `.gitattributes` 沒有被忽略：`git check-ignore` 結束碼 1，`-v` 顯示由 `!research/**`、`!dispatch/**` 放行。
- 零差異：對 `origin/product/stock-desk` 的 `git diff --stat` 為空，涵蓋 `uv.lock`、`store.py`、`schema.py`、harness 三檔、`scripts/pipeline_acceptance_real.py`。另外以比對腳本確認：兩份 YAML、`main.py`、`scheduler.py` 與四個凍結檔零差異，前置 PR 改過的四個 docstring 也沒有再動。
- 未改：repo 根目錄的 `.gitattributes`、`work/.gitignore`。

**介面說明（更新後的結束碼表）**

| 結束碼 | 意義 | 是否寫入 | 輸出 |
|---|---|---|---|
| 0 | 已提交且核對成立 | 寫入兩列 | stdout 16 行，格式同上一輪 |
| 2 | argparse 用法錯誤，包括漏給 `--provisional-results-seen` | 不寫入 | argparse 訊息 |
| 3 | 其他拒絕：鍵入值、格式、prereg 核對、未發布版本、禁詞、store 的 `ForecastStoreError`（例如等時鐘逾時） | 沒有邏輯寫入 | stderr 一行固定句 |
| 4 | 路徑、環境變數、`.env`、h3／h5 順序、取代，以及交易內的 `SchemaNotEmptyError` | 沒有邏輯寫入 | stderr 一行固定句 |
| 5 | 已提交，但核對不成立，或核對、組輸出時發生任何 `Exception` | 已寫入，不得重試，一鍵檔應 STOP | stderr 只有 `POST_COMMIT_CHECK_FAILED`，stdout 為空 |

- 預期外的例外（提交前）與任何 `BaseException` 都不捕捉，會直接往外拋；一鍵檔把任何非 0 的結束碼都視為 STOP。

## 下一步
1. 請 TA 或 coordinator 確認 `test_pipeline_acceptance_real_eol.py` 的那個改動。
2. qa 重驗 RC-180 與本批內容（含 Codex）。
3. devops-sre 依上面的結束碼表實作一鍵檔，包括 R-4 的 `mode=ro` 提早檢查、R-2 的換行證據與 `--frozen-commit` 的綁定。
4. CEO 在能到達 M 的 head 上跑真實資料驗收後，以那一次的 `git_head` 重做 (d) 比對與 RC-163 比對，再合併。

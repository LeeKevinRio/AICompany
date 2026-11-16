# CG-2 登記 PR 審查（app 與 CLI）

- 審查者：qa-reviewer
- 日期：2026-11-16
- 轉存：coordinator，逐字轉存 subagent 最終回報

---

## 本次結論（程式碼審查結論，未重現 12161 passed）

**PASS，BLOCKING_ISSUES=false。** 單家審查（Codex 不可用：`codex --version` 回 command not found，依 CEO #58 記為單家審查）。判準 1～11 逐項讀碼，沒有找到會讓登記值錯誤、交易不完整或正式庫在錯誤條件下被寫入的問題。以下 medium 與凍結後待辦各項，不阻擋放行。

## 各部門回報（依判準）

1. **登記值：成立。**
   - `app/dirdef/v1_0.py` 第 17-63 行逐欄對 `tests/dirdef_helpers.py` 的 `DIRDEF_V1_0_G7` 與凍結包 L642-673 表格，全部一致。比對的欄位包含 K3/K5、EPS、SIGMA 三項、B2 兩項、`MAJORITY_TIE_ORDER`、NEFF、SEASON、CHECKPOINTS 兩組、`MIN_MEAN_RECALL=1/3`、`BASKET_EXCLUSION_REASON_ORDER`（採更正後順序）、description、`MARKET_PRICE_INDEX_DEVIATION`。
   - `f2_variant="F2-B"`；`c8_decision_sha256=c942642c…ea54f`（第 42 行）；`c8_decision_ref` 是 C8 紀錄的路徑。
   - `registry.py` 登記 `dirdef-v1.0` 與 h3、h5。
   - `test_cg2_registration_values.py`：M-3 第 143 行、M-4 第 153-164 行、M-5 第 188-200 行釘住兩個 definition 雜湊與四個規則雜湊。
   - 第 167 行：logic 雜湊等於替身 `dirdef_v1_0()`。第 172-182 行：兩者只差 `c8_decision_ref` 與 `c8_decision_sha256`，而且差異集合 ⊆ `DEFINITION_NON_LOGIC_FIELDS`。
   - 我讀不出雜湊的實際數值是否與替身重算一致，這要靠跑測試（見建議實證）。
2. **正式路徑寫入只有一條：成立。**
   - `claims.py` 第 507-561 行：`bootstrap_main` 只呼叫 `store.bootstrap`，之後只呼叫唯讀查詢（`ledger_schema_status`、`forward_claims`、`runs`、`provisional_results_seen`）。
   - `register`（第 214-265 行）與 `production_path_refusal`（第 150-174 行）沒有改動，`main` 的 register 分支維持拒絕正式路徑。
   - `test_s15_only_the_claims_cli_calls_bootstrap` 以 AST 釘住 `app/` 內只有 `claims.py` 呼叫 `bootstrap`。
   - 登記表非空之後：`store.bootstrap` 在交易內 `create_objects` 遇到既有 `forecast_`/`plan_` 物件即拒絕（`SchemaNotEmptyError`），沒有別的登記方式。
3. **建立 store 之前的檢查：成立。**
   - `production_target`（第 378-403 行）：`backend_dir` 預設為 `APP_ROOT.parent`，由模組位置導出；先檢查環境變數鍵名（`in env`，連空值也拒絕）與 `.env` 的鍵名；再做 `resolve(strict=True)`，比對 `backend_dir.resolve(strict=True)/data/stock-desk.db`，最後檢查是一般檔案。
   - 目標檔不存在就 `strict=True` 拋 `OSError`，結束碼 4，因此不可能由 `sqlite3.connect` 建出新檔。
   - symlink（檔案或 `data/` 資料夾）解析後與預期位置不符，會被拒絕。相對路徑不存在：路徑從模組位置導出，不看 cwd。大小寫：兩端都走 `resolve` 取得實際大小寫。
   - 傳給 store 的是已 resolve 的 `target`。
   - 沒有找到繞過路徑。
4. **結束碼與不寫入：成立。**
   - 3、4 發生在 `store.bootstrap` 之前，或由交易 rollback 保證不寫入。`SchemaNotEmptyError` 是 `RuntimeError`，不是 `ForecastStoreError`，所以先捕捉為 4，順序正確。
   - `_open_connection` 只設 pragma，不改檔案標頭。
   - 5 是在 commit 之後核對失敗，不重試。
   - 拒絕時只印固定句到 stderr，stdout 為空。
5. **`provisional_results_seen`：成立。** 第 350-354 行 `required=True`、無預設值、無 `choices`（改由第 433 行比對字串 `0`/`1`，非此即 exit 3）；不取自環境變數或檔案。以 `typed == "1"` 傳給兩個 `ClaimInput`；`post_commit_check` 逐列比對 `(claim, int(seen))`；輸出第 558 行有此行。
6. **`prereg_doc_path` 與 blob：成立。**
   - 格式檢查（第 357-367 行）不轉換。
   - `git_blob` 讀的是 `<frozen_commit>:<path>` 的 blob，不是工作樹。
   - 注入：`frozen_commit` 先過 `^[0-9a-f]{40}$`，且 argv 為 list、不經 shell，路徑檢查拒絕 `/` 開頭、`..`、反斜線，所以沒有選項注入的可能。
   - 失敗（`OSError`/逾時/非 0 結束碼）回 `None`，空 blob 也拒絕，exit 3。
7. **回傳內容：成立。** 計數為 16 行（`bootstrap=ok`、2 行 scan、`registered_rows`、frozen_commit、prereg sha、兩個 definition 雜湊、h3 與 h5 各 3 行、provisional、`post_commit_check=ok`），不含路徑與代號。
8. **RC-163：成立。** `freeze_pack_block`（測試檔第 115-133 行）：標題出現次數不是一次、找不到開頭圍欄、找不到結尾圍欄，一律 `FreezePackBlockError`；有 7 個失敗案例；與 YAML 以 `HEAD` 的 blob 比對（第 207-214 行）。
9. **(d) 允許範圍：成立。**
   - `git diff --name-only` 的 12 個檔，`app/` 只有 `registry.py`、`v1_0.py`、`claims.py`。
   - `store.py`、`schema.py`、三個測試輔助、`pipeline_acceptance_real.py`、`uv.lock`、兩份 YAML、`main.py`、`scheduler.py` 皆零差異（以相關路徑的 `--name-only` 輸出為空確認）。
   - `claims.py` 的 diff 只有 import、`_add_bootstrap_parser`、`main` 開頭的分派，以及新增區段；`register`、`production_path_refusal`、`_same_file` 未動，與 dev-lead 揭露一致。
10. **測試隔離：成立。** `desk.main` 一律傳入 `backend_dir=tmp 替身` 與 `env`；test 第 618-619 行以 AST 斷言所有 `main(` 呼叫都帶 `backend_dir`、且不引用 `BACKEND_DIR`；子行程測試傳 `cli.backend` 並以 `cwd=tmp_path` 執行。未找到會落到真實 `<backend>/data/` 的測試或預設值。
11. **既有測試改動：全為合理翻轉，沒有削弱。**
    - 「登記表為空」翻成「恰好為 CG-2 那組」（`set(...) ==`），仍是釘死版本集合。
    - K-11 改寫（`test_forecast_pipeline_harness.py`）：新增 placeholder 規則集與正式登記互斥，唯讀性仍保留。
    - `test_forecast_boundaries.py`：import 白名單加 `SchemaNotEmptyError`，只多一個 schema 例外類別，範圍有限，且與 `claims.py` 實際 import 相符；白名單加 `dirdef/v1_0.py` 亦屬必要。
    - `test_forecast_bootstrap.py`：呼叫者集合由 `set()` 變為 `{"forecast/claims.py"}`，是補充七第 6 點預告的翻轉。
    - `test_forecast_claims_cli.py` 的子行程測試保留未登記版本被拒，並加上登記版本寫入 tmp 的案例。

### Findings

- [medium] `claims.py` 第 539 行 `post_commit_check`（含 `store.forward_claims()` 等）若拋出 `sqlite3.Error` 等預期外例外，已 commit 的情況下會以 traceback 結束（結束碼 1，不是 5），traceback 可能含路徑。符合「預期外例外不捕捉」的字面規格，但操作員會看到「已寫入但結束碼不是 5」。建議在運行手冊註明：若 bootstrap 出現非 3/4/5 的非零結束碼，先唯讀檢查資料庫，不得重試。是否要把 commit 之後的例外轉為 5，請 TA 判定。
- [低 / 凍結後待辦] `claims.py` 第 372-375 行 `.env` 檔存在但無讀取權限時，`open` 拋 `OSError`，結束碼 1 且 traceback 含路徑。仍是 fail-closed，不寫入。
- [低 / 凍結後待辦] `_ENV_FILE_KEY` 不涵蓋 `export STOCK_DESK_DB_PATH=` 寫法。與 `scripts/r2_first_run.py` 的既有作法一致（該腳本編碼 `errors="replace"`，這裡是 `ignore`，無實質差異）。
- [低 / 凍結後待辦] `--review-refs` 逐段檢查不擋段中內嵌的 tab/換行（只擋頭尾空白）。
- [低 / 凍結後待辦] `git_blob` 繼承環境中的 `GIT_DIR` 等變數，可能指向別的 repo。建議以環境變數白名單或明確傳入 `-C` 與清掉 `GIT_*`。
- [低 / 凍結後待辦] `--frozen-commit` 只驗格式，沒有驗證該 commit 上的規則檔位元組等於登記的 `rules_sha256`。目前由 `test_cg2_registration_values.py` 以 `HEAD` 把關，操作員人工確認 frozen_commit 即可。
- [低 / 凍結後待辦] M-2、M-3 與 RC-163 的測試讀 `HEAD:<path>`。凍結之後若有人改動這些文件，測試會失敗；這屬於刻意釘死，但建議改釘 frozen commit 的雜湊值，並於註解說明。argparse 前綴縮寫（如 `--prov`）亦未關閉（`allow_abbrev`），風險很低。

### 對 dev-lead 三點待確認與 7 項自定解讀的意見

- 我未逐一對照三點待確認與 7 項自定解讀的原文，下列意見只針對你點名的取捨。
- **不做 `mode=ro` 的提早表檢查、完全依靠交易內檢查：同意。**
  - 提早檢查本身就是 TOCTOU：檢查與寫入之間狀態可能改變，而交易內 `BEGIN IMMEDIATE` 之後再 `create_objects` 才是權威檢查。
  - 失敗路徑只會多開一條連線並設三個 pragma，不改檔案，rollback 後庫維持不變。
  - 提早檢查不能取代交易內檢查，只能提供較早的錯誤訊息，價值有限。

## 驗證

- 已執行：`git diff` 分檔閱讀全部 12 個檔；讀 worktree 的 `claims.py`、`v1_0.py`、`tests/dirdef_helpers.py`、`tests/test_cg2_registration_values.py`、`store.py` 相關段落；對凍結包 L642-673。
- 我無法跑測試；12161 passed（3.12 與 3.13）未重現。
- **唯讀權限判準常數：未觸及。** 以 `git diff origin/product/stock-desk...origin/feat/nm5-cg2-registration --name-only -- scripts/validate_agents.py` 檢查，無輸出。這次 diff 不含 `.claude/agents` 異動，常數也沒有在別的檔案出現新增或修改；我僅就這一道檢查所能涵蓋的範圍作結論。

### 建議實證（讀碼無法確定的）

1. 在 `apps/stock-desk/backend/` 跑 `python -m pytest tests/test_cg2_registration_values.py tests/test_forecast_claims_bootstrap.py tests/test_forecast_boundaries.py tests/test_forecast_pipeline_harness.py -q`，確認 `definition_logic_sha256` 重算值為 `4cc1fe80…1afa`、`definition_sha256` 為 `2a58bca6…c4d0`。
2. 在 CEO 正式庫的複本（不要碰原檔）上演練：`bootstrap --production` 指向一個放在臨時 `backend_dir` 的複本（含非空 `forecast_` 表），確認 exit 4、檔案雜湊不變。

## 下一步

1. 轉 TA 判定 `_parser`/`main` 分派，以及 commit 後例外是否需轉成結束碼 5（medium 項）。
2. 上述低風險項目列入凍結後待辦。
3. 一鍵檔不在這次範圍；上線前由 devops-sre 依操作手冊執行「建議實證」第 2 項。

BLOCKING_ISSUES=false

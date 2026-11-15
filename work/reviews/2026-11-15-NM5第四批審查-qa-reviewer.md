# NM-5 第四批程式碼審查

- 審查者：qa-reviewer
- 日期：2026-11-15
- 轉存：coordinator，逐字轉存 subagent 最終回報

---

## 本次結論

**程式碼審查結論：PASS（無 BLOCKING_ISSUES）。單家審查，Codex 不可用。**

- Codex 不可用：`codex --version` 回 exit 127（command not found），依 CEO #58 記「單家審查」。
- 我不能執行測試。`11423 passed` 與覆蓋率 97.77% 未經重現，只算 dev-lead 自述。
- 工作樹停在舊 commit，我只讀 `git diff f52bff6..c4e0361`。行號是 diff 新側（`+`）的 hunk 行號，約略值，未對照檢出的檔案。
- BLOCKING 判準 1～5 逐條讀碼都成立。#139 四類（紀錄或登記表被改寫、PIT 失守、雜湊改變、正式資料庫被寫入）未發現。
- 第 3 節列出五項「凍結後待辦」，不擋行。

## 各部門回報（dev-lead 交付物）

### 判準 1：不接線，成立
- 14 個異動檔裡，`app/main.py`、`app/scheduler.py`、`app/dirdef/**`、`app/outlook/**`（含 `rules/`）、`app/api/**` 零 diff。`git diff --name-only -- <這些路徑>` 為空。
- diff 內 `app/` 沒有 `record_forecasts` 或 recorder 的呼叫者。`claims.py` 只有 `__main__` 進入點。
- claims CLI 只經 `ForecastStore.register_claim` 寫入。AST 測試（`test_claims_writes_only_through_the_store…`）禁止 `execute/connect` 與 SQL 字串。
- 沒有建表路徑：`store` 仍「不建 schema」，`_write` 以 `require_complete_schema` 檢查。

### 判準 2：K-2 與雜湊，成立
- `banned_phrases.py` 只有 docstring 與常數，無任何 import（含 `__future__`）。值與順序與舊 `loader.py` 逐字相同（我對過 diff 的 `-`、`+`）。
- `loader.py` 用 `from app.advice.banned_phrases import BANNED_PHRASES as BANNED_PHRASES` 再匯出。`definitions.py` 改從葉模組 import。
- `app/advice/__init__.py` 在工作樹（本批未改）無 import。
- 測試涵蓋：
  - 葉模組無 import；
  - loader 再匯出同一物件（`is`）；
  - 只有葉模組定義與含禁詞常數；
  - 可達集合與 `app.api*` 無交集；
  - 可達的 advice 模組恰為 `{app.advice, app.advice.banned_phrases}`。
- `executed_app_modules` 把父套件 `__init__` 也算進可達集合，比原本的檢查更嚴。
- `app/outlook/rules/**` 零 diff，兩份 YAML 位元組不動。`test_the_k2_move_keeps_the_three_hashes` 釘住 logic 雜湊（h3 `ddd3c51a…`、h5 `e5310b8e…`）與 G7 替身雜湊。
- 實際值未重算，建議實證（見第 3 節）。

### 判準 3：S-12a 第 1～9 點，逐條讀碼成立

| 點 | 結果 |
|---|---|
| 1 比對基準 | `_differs(None)` 改回 True，`passed is None` 視為不同。測試有 A ok → B gate_closed ×2 → 回 A 通過、沒有通過執行時重算、error 與無 end 列不當基準。 |
| 2 取值時點 | `LOADED` 在 import 時取值一次。`warn_if_disk_differs` 在 `begin_run` 之後、只記固定字面一行 WARNING，不含標籤或雜湊。測試涵蓋原始檔、鎖檔、讀不到三種情形，outcome 與 content_hash 不變，run 列仍記 `LOADED`。函式內 import、`importlib`、`__import__` 的 AST 檢查與牙齒測試都有。scheduler 的模組層級 import 檢查函式已備好，未接線（本批不該接）。 |
| 4 無定案 bar | 只有 (a) bar 時 `candidate_t` 等於最大 S；只有 (b) bar 時為 null。 |
| 5 source_status | 4 種 DataStatus 配同一組 bars，T、label、band_def、baseline、missing 逐位相同，`source_status` 照實記錄。AST 掃描只豁免 `MissingItem` 內的 `self.source_status`（見 (a)）。 |
| 6 取代鏈 | `replacement_violations` 是唯一定義，登記（寫入交易內）與 CG-2 都呼叫。三個反例在純函式、store 登記、CG-2、CLI 四處都有測試。先前的「同 horizon」檢查被併入，訊息仍相容。 |
| 7 原子寫入 | `write_run_records` 在同一個 `_write`（`BEGIN IMMEDIATE`）內插入 snapshot 與全部 record。驗證都在開交易前完成，插入段任何一筆失敗整筆 ROLLBACK。`records_written` 只在成功後才設為 `len(written)`。測試注入第二筆失敗（trigger 觸發、I/O 錯誤），snapshot 與 record 皆 0 列，下次執行兩筆出自同一份快照。 |
| 8 失敗歸類 | `_market_snapshot`、`store.snapshot`、registry 與 bars 讀取都在 try 之外，錯誤往外傳，記 `error` 與例外類別。程式端（`compute_outlook`、`_record_content`、`ForecastStoreError`）記 `gate_closed`／`SemanticsChanged`。`LedgerInconsistentError` 是 `RuntimeError`，不是 `ForecastStoreError`（`ValueError`）的子類，所以 `except ForecastStoreError` 不會吞它。兩類各 3 個測試，且測試確認兩類之後仍會重算。 |
| 9 唯讀 | `_read` 加 `PRAGMA query_only = ON`。`_connect` 只在 `_write` 內被呼叫，`stored_records` 改走 `_read`。AST 與連線旗標（唯讀 1、寫入 0）測試都有。 |

### 判準 4：claims CLI，成立
- **必填欄位**：`--frozen-commit`、`--prereg-doc`、`--review-refs`、`--provisional-results-seen`（`choices 0/1`，操作者明示）都是 argparse `required`，缺少即 exit 2。空白值與空檔由 store 驗證拒絕，exit 3。
- **`replace_reason`**：與 `replaces_claim_id` 同在才行，單給 reason、缺 reason、空白 reason 都被拒。
- **append-only**：寫入只經 `register_claim`；重複登記、`INSERT OR REPLACE`、UPDATE、DELETE 都以 append-only 被拒（trigger）。
- **禁詞比對**：`registration_phrase_scan` 對規則集與定義的所有字串值做 NFKC 加去空白，在登記前執行。原字、半形空白、全形空白、定義內字串都被拒且無新列。測試未見 NBSP 與其他 Unicode 空白案例（交件稱有 NBSP）。
- **正式路徑一律拒絕**：
  - 拒絕範圍：名為 `stock-desk.db` 者、`<backend>/data/` 與 `./data/` 的正式庫、`STOCK_DESK_DB_PATH` 指向的檔案、這些檔案所在資料夾內的任何檔案、不存在的檔案。
  - 比對方式：以 `samefile` 與 `resolve()` 比對，symlink、hardlink、`..` 都涵蓋。
  - 位元組不變：7 種情形的測試都確認被比對的檔案位元組不變，錯誤訊息不含路徑值。

### 判準 5：測試用合成資料與 `tmp_path`
- 絕大多數成立。唯一例外見待辦 3（子程序測試會對真實 backend 的 `data/` 做存在性檢查，不讀不寫）。

### dev-lead 四處解讀的意見（TA 另行確認）
- **(a) `MissingItem` 內 `self.source_status` 的豁免：夠窄，同意。**
  - 實際用到只有 `app/outlook/missing.py:76-82` 的驗證器，欄位型別是 `SourceStatus`（`fetch_failed`／`not_yet_published`），與 `DataStatus` 無關。我 grep 到 `app/outlook` 內沒有其他 `source_status`、`.status`、`DataStatus`。
  - 豁免條件是「最內層 ClassDef 名為 `MissingItem` 且 `self.source_status`」，`other.source_status` 與別的類別都會被抓（有牙齒測試）。
  - 弱點見待辦 5。
- **(b) 改抓 `Exception`：不會把帳本端錯誤吞成 `SemanticsChanged`，同意。**
  - `Exception` 只包 `compute_outlook` 與 `_record_content`，輸入 `market` 已在 try 外讀好、解析好。帳本端讀取（含 `LedgerInconsistentError`、`sqlite3.Error`）在 try 外或落在 `except ForecastStoreError` 之外，會往外傳成 `error`。測試 3 個 ledger 案例（`InvalidOperation`、registry 列消失、`bars_json` 不可讀）都驗證 `error`。
  - 兩個副作用（待辦 1、2，皆 fail-closed）：
    - 它也吞 `MemoryError`、`RecursionError`。
    - `error_class` 都標成 `SemanticsChanged`，原例外類別不留。
- **(c) WARNING 提前落地、比對含 `runtime_json`：同意。**
  - 這只增加一行 log，不改 run 列、雜湊、outcome。
  - 比對範圍與 D-5 的觸發條件（`code_digest` 加 `runtime_json`）一致，沒有放寬。
  - 唯一疑慮是函式在 try 之外（待辦 1）。
- **(d) 依 ADR-0030、不套 N-84：同意，屬 TA 裁量。**
  - 修訂版 S-12a 與 D-1 第 2 點未列「已有 run 就拒絕前瞻登記」。
  - 風險：CLI 允許「已有 run 後才登記前瞻 claim」，PIT 保證只靠操作者明示 `provisional_results_seen` 與當日 `work/` commit。這是 CG-2 登記 PR 該處理的流程問題，不是本批的缺陷。

## 驗證（讀碼與未能驗證的項目）

- 已做：逐檔讀完 `app/` 的 diff 與測試 diff。
  - `app/` 側：`recorder.py`、`store.py`、`claims.py`、`definitions.py`、`banned_phrases.py`、`loader.py`。
  - 測試側：`test_forecast_recorder`、`test_forecast_store`、`test_forecast_claims_cli`、`test_forecast_boundaries`、`import_graph`、`test_outlook_rule_files`、`test_kelly_boundary`。
- 唯讀權限判準常數：**未觸及。**
  - `git diff base...head -G"READONLY_AGENTS|READONLY_ALLOWED_BASH" --name-only` 為空。
  - `scripts`、`.claude` 路徑零異動。
  - 無 agent 名單異動、無 shadow 定義、常數值未改。
  - 本批只動 `apps/stock-desk/backend`。
- 未能驗證，建議實證，皆需 dev-lead 或 CI 執行：
  1. 在 c4e0361 跑 `test_forecast_boundaries.py`、`test_outlook_rule_files.py::test_the_k2_move_keeps_the_three_hashes`、`test_forecast_recorder.py`、`test_forecast_claims_cli.py`，確認全綠且不依賴整套測試順序。
  2. 獨立重算兩份 YAML 的 sha256 與兩個 logic 雜湊，對照修訂版與交件表。YAML 兩個 sha256 的修訂版基準值我沒有看到，只確認 `app/outlook/rules/**` 零 diff。
  3. 確認 `python -m app.forecast.claims` 在 CI 環境的雙向 import（子程序測試已涵蓋，但未重現）。

### 凍結後待辦（皆不觸及 #139 四類）

1. **`warn_if_disk_differs()` 的例外範圍（`recorder.py` 約 302 行呼叫處，約 223–239 行定義）。**
   - 它在 `begin_run` 之後、`try` 之前執行，只抓 `OSError`。若 `runtime_info` 或 `code_digest` 拋出其他例外（例如鎖檔解析失敗），run 列已存在卻沒有 end 列，例外直接外拋。
   - 後果：該次不記錄，被解讀為「中斷」，之後會重算。屬 fail-closed，但 WARNING 理應不影響執行。
   - 建議：納入 `try` 內，或把比對本身的例外視為「不同」。
   - 建議實證：確認 `runtime_info` 可能拋哪些例外。
2. **`_reproduces`（約 496–536 行）的 `except Exception`。**
   - 會吞 `MemoryError` 與 `RecursionError`，且 `SemanticsChanged` 蓋掉真實例外類別，排錯困難。
   - 另外，`expected_record_columns` 若拋出非 `ForecastStoreError` 的 `ValueError` 或 `ArithmeticError`（例如驗證器內的 Decimal 轉換），現在會往外成 `error`，原本是 `SemanticsChanged`。兩者都 fail-closed。
   - 建議實證：確認 `_record_content` 驗證是否把所有程式端錯誤包成 `ForecastStoreError`。
3. **子程序測試碰到真實 `data/` 路徑（`test_the_module_runs_and_refuses_with_the_empty_production_registries`）。**
   - `claims.main` 未覆寫 `backend_dir`，`_same_file` 對真實 `<backend>/data/stock-desk.db` 做 `exists()`（只檢查存在，不開檔）。與檔頭「no test opens, stats …」及判準 5 的字面不符。
   - 建議：在 claims 加一個測試用環境變數覆寫 backend，或把子程序測試改成只測 import。
4. **禁詞掃描未涵蓋零寬字元（`definitions.py` 的 `squeeze`，約 191 行）。**
   - `str.split()` 不移除 U+200B／U+200D／軟連字號。`保​證` 不會命中。
   - 風險低：規則來自受控 repo，且 loader 已有一道原字比對。
   - 建議：CG-2 登記 PR 時一併補。
5. **`MissingItem` 豁免只比對類別名（掃描函式 `_status_branches`）。**
   - 任何掃描範圍內名為 `MissingItem` 的類別都會被豁免。目前範圍只有 recorder 與 `app/outlook/**`，風險可忽略。
   - 建議：改成限定在 `outlook/missing.py`。

## 下一步

1. 請 TA 確認 (a)～(d)，我的意見是都同意。
2. 請 dev-lead 評估待辦 1（`warn_if_disk_differs` 的 try 範圍）與待辦 3，皆可在接線 PR 或 CG-2 登記 PR 前處理。
3. 純後端，不需要 qa-e2e。回報 CEO：程式碼審查通過，但整套測試與覆蓋率需 CI 重現後才算完成。
4. 接線 PR 的前置項目（沿用 dev-lead 清單）：
   - 套用 scheduler 的模組層級 import 檢查；
   - 把 `WIRED_REFERRERS` 改為 `{"scheduler.py"}`；
   - 做 `_job_wiring_violations` 的 `is` 斷言。

相關檔案（皆在 `/home/user/AICompany/apps/stock-desk/backend/` 下）：`app/advice/banned_phrases.py`、`app/advice/loader.py`、`app/forecast/recorder.py`、`app/forecast/store.py`、`app/forecast/claims.py`、`app/forecast/definitions.py`、`tests/test_forecast_claims_cli.py`、`tests/test_forecast_recorder.py`、`tests/test_forecast_boundaries.py`。

# NM-5 第五批審查

- 審查者：qa-reviewer
- 日期：2026-11-15
- 轉存：coordinator，逐字轉存 subagent 最終回報

---

## 本次結論

程式碼審查結論：**BLOCKING_ISSUES（1 項）**。其餘八項判準，我讀碼都成立。

**單家審查。** 沙盒裡 `codex` 指令不存在（`command not found`），沒有跨廠商第二意見，依 CEO #58 照實記錄。我沒有執行測試。`11607 passed`、覆蓋率 97.76% 都未經我重現。

BLOCKING：`compare`（以及內含它的 harness 輸出）列出模型標籤和四個基準時，會把 `unavailable` 的原因丟掉。這違反 D-4 第 3 點「`unavailable` 照列原因」，也就是 CEO #139 所說「輸出違反 D-4」。
- `scoring.py:105` 的 `ComparedRecord.from_row` 只取每個基準的 `["label"]`，原因欄位到這裡就沒了。
- `report.py:234-240` 的 `render_compare` 用這份只有標籤的資料組出 `B2=unavailable（不適用）`。
- 對照：`records` 子命令走 `report.py:136-143` 的 `_prediction_text`，會印 `unavailable:<reason>`。同一份資料在兩個子命令的輸出不一致。
- 測試沒擋到：`test_forecast_report.py:214-237` 的 `d4_violations` 不檢查 `unavailable` 有沒有附原因。`compare` 的測試（331-366 行）也沒有帶 `unavailable` 基準的列。第 271 行只在「放行」的正例裡出現過 `unavailable:...`。
- 修法：`ComparedRecord` 保留完整的基準預測（label 加 reason），`render_compare` 對 `unavailable` 輸出 `unavailable:<reason>`。再補兩個測試：一個 compare 帶 B2 `unavailable` 的反例，一個讓 `d4_violations` 對「`unavailable` 沒附原因」報錯。
- 真實資料上 B2 不足 120 個可投票位置時會出現，不是理論情境。

## 各部門回報（逐項判準）

1. **不接線：成立。**
   - `git diff c4e0361..518046f -- app/main.py app/scheduler.py app/outlook app/dirdef` 輸出為空。
   - report 的 `--db` 只接既有檔案，不建表、不登記。
   - 唯一在 `app/` 外建表的是 harness 的 `_create_ledger`，建在 `work_dir` 的暫存檔，而且先過 `refuse_production`（AST 測試鎖了順序，`test_forecast_pipeline_harness.py:488-498`）。
2. **report 唯讀：成立，但有一個小缺口。**
   - 所有讀取都走 `store._read()`，內含 `PRAGMA query_only=ON`（`store.py:533-540`）。
   - report 模組沒有 `_connect`、`connect`、`execute`、SQL 字面（AST 測試 `test_forecast_report.py:596-629`）。
   - 測試也斷言檔案位元組不變、不存在的路徑不會被建立（562-593、632-640 行）。
   - 小缺口見下方待辦 3。
3. **輸出限制：BLOCKING 一項，其餘成立。**
   - 暫定對照的固定標示與 n̂ 附註，逐字等於 ADR D-5 第 5 點與 D-4 第 5 點。測試 `test_forecast_report.py:676-681` 以字面釘住。
   - 未到期紀錄只列 T、late、是否證據不足、雜湊與執行結果（`report.py:126-133`、`157-172`）。`compare` 與 harness 的 `has_passed` 過濾一致。
   - 四個基準與模型同列、同格式、模型在最後。
   - 禁用字樣與 n 的正反例各有（`test_forecast_report.py:240-273` 十六個反例）。
   - 唯一缺口就是上面的 `unavailable` 原因。
4. **scoring 隔離：成立。**
   - 只有 report import scoring。`test_forecast_report.py:684-687` 與 `test_forecast_scoring.py:227-247` 檢查 store、recorder、schema 不可達 scoring。
   - forward return 類識別字：`app/forecast` 內只有 `scoring.py`（`test_c15_identifiers.py` 的新測試，我也用 grep 對過）。
5. **verify：成立。**
   - 規則位元組與定義 JSON 取自登記表（`definitions.registered_ruleset`、`registered_definition`）。
   - 它們各自核對 `rules_sha256`、兩個 logic 雜湊與 `definition_sha256`，再掃禁詞，並且不快取。
   - `RECOMPUTED_COLUMNS` 恰為 `label`、`band_def`、`baseline_predictions_json`、`missing_json`、`content_hash`（`recorder.py:141-147`）。
   - 快照另以 `content_sha256(stored.bars)` 核對（`report.py:298`）。
   - 竄改測試 8 種（`test_forecast_report.py:403-494`）涵蓋五個欄位、快照位元組、登記規則與登記定義。
6. **harness：成立。**
   - 正式路徑拒絕：`refuse_production` 呼叫 `claims.production_path_refusal`，並額外擋 `<backend>/data/` 之下（`forecast_pipeline_harness.py:183-191`）。測試 `test_forecast_pipeline_harness.py:308-339`。
   - 取數只回答給定的 bars，`reason` 標 `synthetic_timestamps`（308-317 行）。AST 測試禁止 `price_bars_cache`、`app.data.cache`、`app.services`（465-475 行）。
   - K-11：`injected_registry` 只存在於 `tests/`。`app/` 內沒有重綁 registry 的路徑，也沒有 import tests（398-448 行，附牙齒測試）。正式 registry 是空的唯讀對映（369-377 行）。
   - 視窗由 `acceptance_window` 機械決定，取執行日前最近 21 個定案 session（320-325 行）。
   - 兩行標示逐字等於 D-7 第 5 點（85-90 行）。
7. **第四批收尾：成立。**
   - (a) 豁免同時比對模組 `outlook/missing.py` 與類別 `MissingItem`（`test_forecast_recorder.py:551-575`），並有三種反例。
   - (b) `_reproduces` 剩一個 `try`，body 恰為 `compute_outlook` 與 `_record_content`，只捕捉 `Exception`（`recorder.py:526-529`）。測試的 AST 檢查與 8 個牙齒反例成立。
   - 待辦 1：`warn_if_disk_differs` 改捕捉 `Exception`，`KeyboardInterrupt` 照常外傳，有測試。
   - 待辦 3：子程序測試改成 `--help` 與帶替身路徑的 `-c`，並有 AST 檢查（`test_forecast_claims_cli.py:592-647`）。
   - 待辦 4：`squeeze` 移除六種零寬字元。
   - 兩份 YAML 與四個規則雜湊不變。`app/outlook/rules/**` 與 `app/outlook`、`app/dirdef` 為零 diff。
8. **測試只用合成資料與 `tmp_path`：成立，附一個建議。**
   - 所有 `run_acceptance` 與 `refuse_production` 呼叫都傳 `backend_dir`、`env`、`cwd` 替身。AST 守門在 `test_forecast_pipeline_harness.py:501-514`。
   - `claims.main` 的呼叫也都帶 `backend_dir`（`test_forecast_claims_cli.py:625-647`）。
   - 我 grep 了整個 `backend/` 的 `.py`，只有這幾個檔案碰這些函式，`test_forecast_claims.py` 沒有 `main(` 呼叫。
   - 修正完整，我沒找到其他漏洞。
   - 但 harness 本身的預設值仍指向真實路徑（待辦 1）。

### 對三個待確認點的意見（TA／quant 另行確認）

- **`expected_record_columns` 的 `ForecastStoreError` 一律記 `error`：我同意。**
  - 內容已先在 try 內經 `check_record_content` 驗過。它與寫入路徑共用 `_record_content`，所以走到帳本端時只剩快照參照與帳本讀取問題，歸 `error` 合理。
  - 這是 fail-closed：該 run 不寫紀錄，下一次會重試。
  - 測試 `test_b_a_ledger_side_refusal_after_the_pure_calls_is_an_error` 與 `test_b_the_write_path_validates...` 覆蓋。
- **實現標籤沒套 `f2_variant`：可接受，等 TA 確認。**
  - 它只用在暫定對照，標示已寫明「可能與日後正式結算不同」。
  - 使用的是紀錄自己的 `K_h`、`EPS`、`sigma_d`。
  - F-2 計數視窗定義為「今天之前最近 20 個平日、且不早於登記日」，輸出同列已寫明起訖日，可以接受。
- **P-0 不恆等於 B6：我同意。** engine 的第 (0) 步先判 insufficient，harness 只對非 insufficient 紀錄斷言等於基準，並要求 insufficient 紀錄的 missing 非空，邏輯一致。

### 凍結後待辦（不阻擋）

1. **harness 預設值（低）：** `forecast_pipeline_harness.py:375-377` 的 `backend_dir=BACKEND_DIR`，以及 `389-390` 的 `Path.cwd()` 與 `os.environ`，預設會讓比對碰到真實 `<backend>/data/`，只讀路徑存在性、不開檔。現在靠測試端 AST 守門。建議改成 keyword-only 且無預設值。真實資料一鍵檔再明確傳入真實值。
2. **零寬字元用裸字元寫（低，可維護性）：** `definitions.py:259` 的 `ZERO_WIDTH` 是六個肉眼不可見的字元。審查者讀不出內容，也容易被編輯器吞掉。建議改 `"​"` 這類跳脫寫法。
3. **report 連線沒有 `mode=ro`（低）：** `store.py:167-173` 的 `_open_connection` 用 `sqlite3.connect(path)`，靠 `query_only` 與 `report.py:488` 的 `is_file()` 擋。正式 DB 是 WAL，建議實證：讀取時 `-shm` 檔案的產生是否可接受。可為 report 另開 `file:...?mode=ro` 的 URI。
4. **D-8 第 4 點「首次成立時 recorder 記 WARNING」未實作：** 交件已揭露。這是 ADR 條文要求，須在接線 PR 之前落地，請列入下一批。
5. **K-11 補強（低）：** `definitions.registered_ruleset` 與 `registered_definition` 是 `app/` 內接受呼叫者傳入位元組的新函式。目前只有 report 使用，沒有走進 recorder 的 CG-2 路徑。建議加一個 AST 測試，鎖定只有 `report.py` 可呼叫它們。
6. **`compare` 的 `RecordUnreadableError` 與 `verify` 的非 `LEDGER_ERRORS` 例外（低）：** `verify` 在 `stored_market_snapshot` 解析時若拋出 `decimal.InvalidOperation` 之類例外，不在 `LEDGER_ERRORS` 內，會直接 traceback 而不是結束碼 3。不影響安全，輸出也不含標籤。建議實證。
7. **`status` 的格點遺失計數（低）：** 沒有 late=0 紀錄的格點，包含最新尚未輪到記錄的格點。F-2 的定義請 TA 確認要不要排除。

## 驗證

- 執行過的指令：`git diff --stat` 與分檔 `git diff c4e0361..518046f`（只讀）、`codex --version`（結果：不存在）。
- 我只讀 diff 與 worktree 檔案，沒有讀 `.env`、沒有碰 `data/*.db`、沒有跑測試。
- 唯讀權限判準常數：未觸及。
  - 本批 diff 不含 `scripts/validate_agents.py`，也沒有 `READONLY_AGENTS` 或 `READONLY_ALLOWED_BASH` 的異動。
  - 兩者也沒有 shadow 定義或值改動，因為整批只動 `apps/stock-desk/backend/**`。
  - 檢查是以 `git diff --stat` 的檔案清單與 grep 取得，沒有另外對全文跑那兩道 `grep -E`，這點如實註記。
- 重點 worktree 檔案（`/home/user/AICompany/.claude/worktrees/agent-ac6740f4f9f9cd706/apps/stock-desk/backend/` 之下）：
  - `app/forecast/report.py`
  - `app/forecast/scoring.py`
  - `app/forecast/store.py`
  - `app/forecast/recorder.py`
  - `app/forecast/definitions.py`
  - `tests/forecast_pipeline_harness.py`
  - `tests/test_forecast_report.py`
  - `tests/test_forecast_pipeline_harness.py`

## 下一步

1. **退回 dev-lead 修 BLOCKING：** `compare` 補上 `unavailable` 的原因（`scoring.py:105`、`report.py:234-240`），並補上兩個測試：compare 帶 B2 `unavailable` 的反例，以及讓 `d4_violations` 擋「`unavailable` 沒附原因」。修完後我只需要重審 `scoring.py`、`report.py`、`test_forecast_report.py` 與 harness 輸出測試，其餘不用重審。
2. **TA／quant** 確認：實現標籤不套 `f2_variant`、F-2 視窗定義、待辦 7 的格點遺失計數。
3. **dev-lead**：待辦 1、2、5 可併入 BLOCKING 修正的同一批。待辦 4（recorder 的 WARNING）排進下一批或接線 PR。
4. **devops-sre 與 dev-lead**：真實資料一鍵檔，待 BLOCKING 修完後再做，順序依補充四第 6 點（CG-2 登記不得早於 harness 通過）。

Verdict: NEEDS_CHANGES
BLOCKING_ISSUES=true

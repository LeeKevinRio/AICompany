# NM-5 第三批 recorder 交件

- 審查者：dev-lead
- 日期：2026-11-15
- 轉存：coordinator，逐字轉存 subagent 最終回報

---

## 本次結論

NM-5 第三批（recorder）做完了，已推上 `feat/nm5-forecast-storage`。
- **新 head：`f52bff641580e7a249f755453b573fbb085b507f`**。從 `5c70a30` 往上加了 6 個 commit，沒有 amend、rebase、force push 或 merge。
- 分支名被別的 worktree 佔用，所以我開了本地分支 `nm5-batch3-recorder` 追蹤它，用 `HEAD:refs/heads/feat/nm5-forecast-storage` 推送，一次就成功。
- CI 等效五項全綠：**11279 passed、1 skipped、2 xfailed**，總覆蓋率 **97.76%**，耗時 1062.73 秒，exit 0。`app/forecast`、`app/outlook`、`app/dirdef`、`session_calendar` 每個檔案的行覆蓋率都是 100%（`recorder.py` 200/200）。
- lax float 收緊前後，兩份 YAML 與兩個 `rules_logic_sha256` **逐位相同**，所以沒有觸發停止點。
- **硬性停止點：無。** 但有兩個我自行判斷的做法，都是收緊、fail-closed，請 TA 確認（見「下一步」第 1、2 點）。另有一項批次前就存在的 K-2 可達性事實要回報（第 3 點）。

## 各部門回報（dev-lead）

**這批改了什麼，各對應哪一點**

1. **`app/forecast/recorder.py`（新增；對應 D-1 第 3 點）**
   - 進入點是 `record_forecasts(store, *, load_benchmark, resolver)`。
     - 依補充二第 1 點，取數函式以參數傳入；`BenchmarkLoader[R]` 是 Protocol。
     - mypy 靜態確認 `load_market_benchmark` 符合這個 Protocol。
     - 參數沒有 T、`as_of`、`clock` 類（K-10、S-6），時鐘只取 `store.now()`。
   - 執行順序如下。
     - 第一個寫入是 `begin_run`，在讀任何市場資料之前（D-2 第 1 點）。
     - 接著依序：CG-2 核對 → 跨 commit 核對 → 決定 T → 擷取快照 → 計算 → 寫入。
     - 每次執行都寫 `forecast_run_end`，outcome 是五種之一。
   - 例外怎麼處理。
     - 一般 `Exception` 記為 `error`。
     - `KeyboardInterrupt`、`SystemExit` 不寫 end 列（D-2 第 2 點）。
     - `error_class` 只經 `exception_class_name`。
   - **CG-2 執行期核對**（D-6、K-9、S-7、S-14）。
     - 記錄中 claim 恰好 (market,3)、(market,5) 兩個，`scope_key` 必須是 TAIEX。
     - 以下五項都要等於 `definitions.py` 的回傳結果：`rules_sha256`（含 horizon）、`rules_logic_sha256`、`definition_sha256`、`definition_logic_sha256`。
     - 其餘前瞻 claim 都要出現在其後某列的 `replaces_claim_id`。
     - 任一不成立就記 `gate_closed`，`error_class=WriteGateClosedError`，不呼叫取數函式，也不寫任何紀錄。
   - **跨 commit 核對**（D-5 第 3、6 點）。
     - 用登記的快照，以目前程式重算每個記錄中 claim 的全部紀錄。
     - `label`、`band_def`、`baseline_predictions_json`、`missing_json`、`content_hash` 要逐位相同。
     - 不同就記 `gate_closed`，`error_class=SemanticsChanged`，不寫紀錄。
   - **決定 T**：依補充二第 2 點的 (a)(b) 分流。
     - (a) 時重抓一次，仍有 (a) 就記 `inputs_not_ready`，`candidate_t` 填最大的 S。
     - (b) 時該 bar 列入 `dropped_rows_json`，T 不變。
     - 「now 已過 S 日 15:00」直接用 `is_final(TW, S, now)` 判定，沿用 CS-17 唯一的比較式，沒有另寫一份。
   - 每個記錄中 claim 都已有 T 的紀錄時，記 `no_new_session`，`candidate_t` 照填。
   - 主預測與 B1、B2、B6、B8 用同一份快照（D-4 第 1 點），兩個 claim 的計算都做完之後才寫入。
2. **`store.py`（D-5 第 3、6 點）**
   - 新增 `now`、`latest_run_before`、`has_record`、`stored_records`、`snapshot`、`expected_record_columns`；`ClaimRow` 帶出兩個 logic 雜湊。
   - `content_hash` 涵蓋的欄位改由 `_record_columns` 單一推導，`write_record` 與重算共用。原有 store 測試全綠。
3. **`errors.py`**
   - 依 D-10，`WriteGate` 改為 CG-1～CG-4。
   - 依 D-5 第 6 點，新增 `SemanticsChanged`。類別名稱照 ADR 字面，訊息只含筆數。
4. **`definitions.py`**：新增 `get_ruleset_entry`，給 CG-2 比對登記表的 horizon 與 sha。
5. **`inputs.py`**：新增 `non_final_rows`。沒有任何定案 bar 時，也能列出未定案的列（補充二第 2 點）。
6. **lax float 收緊（TA 第 4 題）**：`weight` 與 `value` 改用同一個 strict float 型別 `AggregationNumber`。
   - 補了 `true`、`false`、`"1"`、`"1.0"`、`.inf`、`-.inf`、`.nan`、`null` 的拒收反例。
   - 另有一條測試證明 int 視為同值 float，雜湊相同。
7. **qa medium**：outlook `_OPS`、advice `COMPARISON_OPS`、`ComparisonOp` 三者的 key 集合相同（共 8 個）。測試以 AST 讀兩邊原始檔，outlook 本身沒有 import advice。
8. **TA 其餘檢查**
   - `OUTLOOK_RULE_FIELDS` 恰好等於凍結包 §3 的 9 個欄位。
   - `PIT_ITEM` 在 `app/` 內只定義一次，值是 `inputs_max_fetched_at`（補充二第 4 點）。
   - 快照中每根 bar 都是 `fetched_at == as_of`（recorder 寫入的快照也有測試）。
   - SP-A：只改 `name` 時 `rules_logic_sha256` 會變，只改 `explanation` 時不變。

**兩份 YAML 與 `rules_logic_sha256`（收緊前後實測，逐位相同）**
- h3.yaml sha256：`f4f366a5d5e66fd7fd49c916f5bb31401e84c2f23b3bb7a534f55be406fb3443`
- h5.yaml sha256：`0a385de3e2f4118bc1e7c2c5dd1a667ce0a9067399ccd1b6e7c4dbab19d5707c`
- h3 `rules_logic_sha256`：`ddd3c51a1cb9b30a3e957a5a98888ca48916deb35f66027f2f49e7b824f34484`
- h5 `rules_logic_sha256`：`e5310b8e6ce14525e81616eedd4368d45a682cb8a4647129ea5617a41cedf1bb`
- 兩份 YAML 裡的 `weight` 與 `value` 全部是 float，沒有 bool、int 或字串，測試已釘住。四個值也都在測試裡釘住。

**本批測試涵蓋**（`tests/test_forecast_recorder.py` 75 條，全部用合成的 FX-B 資料、`tmp_path`、`FakeClock`）
- **五種 outcome 各有測試**；中斷時沒有 end 列。
- **第一個寫入在讀市場資料之前**：取數函式被呼叫時，表的列數是 run 1 列、其他 0 列。
- **CG-2**：
  - 正例：含取代 claim 的情形。
  - 反例：沒有 claim、只有一個 horizon、後登記的 claim 沒有取代前一個、定義未發布、規則未發布、定義文字變了、定義邏輯變了、規則位元組不同、`rules_logic` 不同、規則登記在另一個 horizon、規則檔讀不到、`scope_key` 不是 TAIEX。
- **跨 commit**：
  - 複製一份程式樹，改 engine.py 一個位元組（`gt` 改成 `<`），執行中的程式也同步改 → 記 `gate_closed`。
  - 只改註解 → 照常寫入，而且確實重算了 2 筆。
  - 只改 `runtime_json` → 有重算。
  - 程式沒變 → 不重算。
  - 重算時程式拒收 → 視為不同。
  - 重算時讀 DB 失敗 → 記 `error`。
- **S-4a**：
  - (a) 重抓恰好一次後記 `inputs_not_ready`，不寫紀錄，也不改用前一天。
  - TA 反例：時鐘晚於次日 15:00 → 記 `inputs_not_ready`。
  - 序列中間有未定案 bar → 記 `inputs_not_ready`，`candidate_t` 是那個 S。這也處理了 qa low 提的缺口問題。
  - (b) LA-G2-5：時鐘在次日 10:05，早於 15:00 → `content_hash` 與取數端不回傳該 bar 時相同，該 bar 列入 `dropped_rows_json`。
  - 正式路徑的呼叫者：`app/` 內目前沒有任何檔案引用進入點。已寫好接線後要用的 AST 檢查與 `is` 檢查，各附反例測試。
- **`late` 臨界**：23:59:59.999999 → 0，00:00:00 → 1。
- **K-4**：四個寫入函式只由 recorder 呼叫。
- **K-2 可達性**：recorder 到不了 `app.services`、`app.portfolio`、`app.positions` 等 11 個禁區。
- **D-3 第 5 點**：hindsight 掃描已涵蓋 recorder。

**檔案**（都在 `/home/user/AICompany/.claude/worktrees/agent-a26c48e22e94b6a29/apps/stock-desk/backend/` 底下）
- 新增：`app/forecast/recorder.py`、`tests/test_forecast_recorder.py`
- 修改程式：
  - `app/forecast/store.py`、`errors.py`、`definitions.py`、`__init__.py`（只改說明文字）
  - `app/outlook/inputs.py`、`app/outlook/engine.py`（只改 `PIT_ITEM` 的註解）
  - `app/dirdef/rules.py`
- 修改測試：`test_dirdef_rules.py`、`test_dirdef_rules_aggregation_invalidation.py`、`test_dirdef_v1_0_fields.py`、`test_forecast_boundaries.py`、`test_forecast_definitions.py`、`test_forecast_errors.py`、`test_forecast_hindsight_sources.py`、`test_forecast_store.py`、`test_outlook_core_boundaries.py`、`test_outlook_inputs.py`、`test_outlook_lookahead.py`、`test_outlook_rule_files.py`
- 刻意零 diff：`app/main.py`、`app/scheduler.py`、`app/dirdef/registry.py`、`data/*.db`。登記表仍然是空的，沒有註冊 job。

**Commits（依序）**
1. `e93e71c` fix: weight、value 改 strict float（TA 第 4 題）
2. `282577c` test: TA 檢查與 qa medium
3. `603d34c` feat: store 唯讀查詢與 `_record_columns`
4. `8b8f5d7` feat: CG 閘門列舉、`SemanticsChanged`、`get_ruleset_entry`
5. `9d826c9` feat: `non_final_rows`
6. `f52bff6` feat: recorder

## 驗證

在 `apps/stock-desk/backend` 執行，HEAD = `f52bff6`：
- `uv sync --frozen`：Checked 46 packages
- `uv run ruff check .`：All checks passed!
- `uv run ruff format --check .`：524 files already formatted
- `uv run mypy app tests`：Success: no issues found in 513 source files
- `uv run pytest --cov=app --cov-report=term-missing --cov-fail-under=90`：11279 passed、1 skipped、2 xfailed，總覆蓋率 97.76%，1062.73 秒，exit 0
- 沒有讀 `.env`、沒有碰任何 `.db`、沒有連網，也沒有用任何真實 `^TWII` 資料。

## 下一步

1. **請 TA 確認：跨 commit 核對的觸發條件比 D-5 第 6 點字面嚴。**
   - 字面是「與前一次執行不同」。照字面做會有漏洞：
     - 程式 A 寫入紀錄後，程式 B 的第一次執行記 `gate_closed`；
     - B 的第二次執行，前一次執行也是 B，於是跳過重算；
     - 結果用新語意寫進舊 claim。
   - 我的做法：與前一次執行不同，**或**與最後一次通過兩道核對的執行不同，任一成立就重算。通過的執行指 outcome 為 ok、no_new_session、inputs_not_ready 的那幾次。
   - 字面條件觸發時一定會觸發，只會多做重算，不會漏。測試 `test_a_label_changing_byte_closes_the_gate` 已證明第三次執行仍記 `gate_closed`。
2. **請 TA 確認：`code_digest` 與 `runtime_json` 在 recorder 模組 import 時取一次（`LOADED`），不是每次執行重讀磁碟。**
   - 原因：排程程序長時間執行，若中途 `git pull`，每次執行重讀磁碟會讓舊程式蓋上新的 digest；重啟後新程式就跳過重算。
   - `runtime_json` 記這些內容：Python 版本與 build、`platform.platform()`、machine、`uv.lock` 的 sha256。
   - 因為 `platform.platform()` 含核心版本，換核心時會重算一次；結果一致就照常寫入。
   - `code_commit` 由 `git rev-parse HEAD` 取得，失敗時記 `unknown`，只作為出處。
3. **回報一項批次前就存在的事實（K-2）。**
   - `definitions.py` 依 K-2 允許 import `app.advice.loader.BANNED_PHRASES`。但 `app.advice.loader` 遞移可達 `app.advice.context`、`app.advice.limits` 與 `app.api.kelly_wording`，所以 `app.forecast`（從 store 起就是如此，recorder 也一樣）實際上可達 `app.api`。
   - 我加了測試，釘住「recorder 可達的 advice 與 api 模組，只限經這條 import 到達的那些」。
   - K-2 字面是「不得 import `app.api`」，這條遞移路徑是否可接受，請 TA 裁示。
4. **我自行定的兩個小規格，請審查確認。**
   - 完全沒有定案 bar 時（含取數端沒有回傳任何 bar），記 `inputs_not_ready`，`candidate_t` 為 null。
   - `source_status` 照實記錄，不另設拒收規則（qa 第二批「另請判定 A」）。若要求不是 backup 時拒收，需要 TA 定規格。
5. **已知限制。**
   - 取數視窗是執行日往前 500＋31 天。T 比執行日早 31 天以上時，涵蓋範圍會少於「T 前 500 日」，照實記錄根數，不擴大。
   - D-8 第 4 點的 n̂ 首次觸發 WARNING 不在本批。
   - 接線 PR 要做的事：把 `WIRED_REFERRERS` 改成 `{"scheduler.py"}`，並對註冊的 job 跑 `_job_wiring_violations`（`is` 斷言）。
6. **送審**：交 qa-reviewer 審查，含 Codex 第二意見。

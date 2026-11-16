# CG-2 登記 PR 第一段交件（登記值完成，bootstrap 停下待裁決）

- 審查者：dev-lead
- 日期：2026-11-16
- 轉存：coordinator，逐字轉存 subagent 最終回報

---

## 本次結論
**這次只交了一部分。第 1、2 項（登記值、規則檔位元組）完成並已 push；第 3、4 項（`bootstrap --production` 與它的測試）照指示停下，沒有實作。** 原因是：在不改 `store.py`／`schema.py`、也不放寬既有的 K-4 邊界測試的前提下，做不出「schema 加兩列登記放在同一個交易」，提交後也核對不了兩列的 `provisional_results_seen`。第 5 項 (d) 的自我檢查已做，結果附在下面。

- 分支 `feat/nm5-cg2-registration`，從 `origin/product/stock-desk`（`5087abb4d4acc4dca7bda071e8afab20dea9b248`）開出，已 push。沒有開 PR，也沒有合併。
- 只有一個 commit：`c79e8313cfdcc44eedb21aa2d60b4e4ef1764356`，也就是 head 的 40 碼 hash。

## 各部門回報（dev-lead）

### 已完成
- 新檔 `apps/stock-desk/backend/app/dirdef/v1_0.py`：只放 `DIRDEF_V1_0` 物件常數，值照凍結包 G7 逐字。
  - `f2_variant="F2-B"`。
  - `c8_decision_ref="work/dispatch/2026-11-15-C8決策紀錄-F2B.md"`。
  - `c8_decision_sha256` 是那個檔的 blob sha256。
- `apps/stock-desk/backend/app/dirdef/registry.py`：只加了一行 import，以及兩個登記表的賦值（`dirdef-v1.0`、`outlook-market-v1.0-h3`、`outlook-market-v1.0-h5`）。
- 新測試 `apps/stock-desk/backend/tests/test_cg2_registration_values.py`，涵蓋：
  - M-2～M-5 的值與 M-6 禁詞比對，都用測試釘住。
  - 補充六第 6 點 (c)：logic 雜湊等於測試替身 `dirdef_v1_0()` 的；兩個 full 雜湊的差異只在 `{c8_decision_ref, c8_decision_sha256}`，是 `DEFINITION_NON_LOGIC_FIELDS` 的子集。
  - RC-163：從凍結包抽出區塊，與 YAML 的 blob 比對；另有一個測試證明抽取規則確實會擋錯。
- 原本斷言「登記表為空」的 6 個測試檔，改成斷言恰好是 CG-2 的版本：
  - `test_dirdef_v1_0_fields.py`、`test_forecast_definitions.py`、`test_forecast_claims_cli.py`（fresh process 那個測試）
  - `test_forecast_boundaries.py`（模組清單加入 `dirdef/v1_0.py`）
  - `test_forecast_pipeline_harness.py`（K-11 改為「唯讀，而且只含 CG-2 版本、不含 P0／P1 佔位版本」）
  - `test_outlook_rule_files.py`

### 停下的原因（第 3 點 bootstrap，需要上游裁決）
1. **單一交易做不到。**
   - `schema.create_schema()` 自己會 BEGIN 和 COMMIT；`ForecastStore.register_claim()` 也自己開 `BEGIN IMMEDIATE`，而且先要求 schema 完整。兩者沒辦法合進同一個交易。
   - 唯一不改 `store.py` 的做法是在 `claims.py` 裡自己開連線、執行 SQL。但既有測試 `test_forecast_boundaries.py::test_claims_writes_only_through_the_store_and_has_a_plain_main_block`（K-4）禁止 `claims.py` 出現 `execute`／`connect` 呼叫與 INSERT 字串，而 `store.py` 的定位是「唯一 INSERT 五張表的模組」。
2. **提交後核對不到 `provisional_results_seen`。** `ClaimRow` 和 store 的所有唯讀查詢都不回傳這個欄位。`schema_status`（用 `ledger_schema_status()`）、登記列數（用 `forward_claims()`）、`forecast_run` 列數（用 `runs()`）都可以不改 store 就核對，只有這一欄不行。

**建議（請 tech-architect 和 coordinator 裁決）：**
- 甲案（推薦）：
  - 在 `store.py` 加一個方法：同一個 `BEGIN IMMEDIATE` 內先確認沒有任何帳本物件，再執行 `schema.EXPECTED_OBJECTS` 的 DDL，再把 `register_claim` 的驗證加 INSERT 抽成共用的內部函式，跑兩次，最後 COMMIT。
  - 另加一個唯讀查詢，回傳各列的 `provisional_results_seen`。
  - `schema.py` 可能要加一個不自己管交易的建表函式，或由 store 直接用 `EXPECTED_OBJECTS`。
  - 代價：超出補充六第 6 點 (d) 的允許範圍，CEO 的真實資料驗收要在新 head 重跑，或先修 ADR 把這兩檔列入 (d)。
- 乙案：放寬 K-4 測試，讓 `claims.py` 自己寫 SQL。這會在 store 之外複製一份登記 INSERT，屬於架構變更，我不建議。
- 拆成兩個交易違反補充四第 2 點，不可行。

## 驗證

### 固定值核對（全部與 coordinator 紀錄一致）

| 項目 | 路徑 | blob id | sha256 |
|---|---|---|---|
| M-2 事先宣告 v0.32 | `work/research/2026-10-15-3日5日方向判斷-事先宣告草案.md` | `d1e4d06a4e1c1a06158ad33a481050fe44bf8ae1` | `7c45b0ba79e04a7a74a2b8bc91603cb0bfbd78101b51ab8403cc4ed45a4b406e` |
| M-3 C-8 紀錄檔 | `work/dispatch/2026-11-15-C8決策紀錄-F2B.md` | `e664f147f2c5339e321ae333b7ce3c7d35ebcda7` | `c942642c1958e6259545c4f64b4202fbafecf585f1f2cbe513961190af0ea54f` |

- 計算指令：`git cat-file blob HEAD:<path> | sha256sum`（測試裡用同一種方式）。
- M-2 最後一次變更在 `ed9275321b0be82bce5c8f3f97a2e31bb3abeb34`（RC-153～157）。
- M-3 最後一次變更在 `7883f12e846d23b86670092dad01e543763bdc4b`，`git diff 7883f12 HEAD -- <path>` 為空。
- M-4（`dirdef-v1.0`）：
  - `definition_logic_sha256`：`4cc1fe80054a017f47030805a486ad81e1bda249d730c7c1f6bd2c73c01d1afa`，等於測試替身的同名雜湊。
  - `definition_sha256`：`2a58bca61c647931ecaf56aa5d17e4bfffc048c30944f3550feceadbfdacc4d0`（替身是 `a0d0a34d…d6e2`）。
- M-5：

| 規則集 | `rules_sha256` | `rules_logic_sha256` |
|---|---|---|
| h3 | `f4f366a5d5e66fd7fd49c916f5bb31401e84c2f23b3bb7a534f55be406fb3443` | `ddd3c51a1cb9b30a3e957a5a98888ca48916deb35f66027f2f49e7b824f34484` |
| h5 | `0a385de3e2f4118bc1e7c2c5dd1a667ce0a9067399ccd1b6e7c4dbab19d5707c` | `e5310b8e6ce14525e81616eedd4368d45a682cb8a4647129ea5617a41cedf1bb` |

- 凍結包 §4.1、§4.2 抽出的區塊，與兩個 YAML 的 blob 位元組完全相同（各 8,290 bytes）。
- M-6 禁詞比對：命中 0；每個規則集掃 159 個字串，定義掃 12 個字串，禁詞共 10 個。

### 測試（都在 HEAD `c79e831` 上跑）

| 環境 | `app` 來源 | 結果 | 覆蓋率 |
|---|---|---|---|
| Python 3.13.17（預設 `.venv`） | 本 worktree 的 `apps/stock-desk/backend/app/__init__.py` | 12018 passed, 2 xfailed, 0 failed | 97.81%（門檻 90%） |
| Python 3.12.3（專屬 venv `/tmp/claude-0/-home-user-AICompany/3f76d891-50d3-55e1-b39d-925b8a90241a/scratchpad/venv312-cg2`） | 同上 | 12017 passed, 1 failed, 2 xfailed | 97.81% |

- 3.12 唯一的失敗是已知問題 `tests/test_pipeline_acceptance_real_bars.py::test_the_isolated_import_is_silent_and_loads_no_forbidden_module`，我沒有改它。
- 先前在 `scratchpad/venv312` 跑出的 3.12 結果已作廢，沒有採用。

### 靜態檢查
- `ruff check .`：All checks passed。
- `ruff format --check .`：547 個檔都已格式化。
- `mypy app tests`：535 個檔沒有問題。

### (d) 自我檢查
比對腳本是 `/tmp/claude-0/-home-user-AICompany/3f76d891-50d3-55e1-b39d-925b8a90241a/scratchpad/check_d.py`，比對 `origin/product/stock-desk` 與 HEAD。
- 差異檔清單：
  - `app/dirdef/registry.py`、`app/dirdef/v1_0.py`
  - 7 個測試檔：`test_cg2_registration_values.py`（新）、`test_dirdef_v1_0_fields.py`、`test_forecast_boundaries.py`、`test_forecast_claims_cli.py`、`test_forecast_definitions.py`、`test_forecast_pipeline_harness.py`、`test_outlook_rule_files.py`
- 零差異：`tests/forecast_pipeline_harness.py`、`tests/dirdef_helpers.py`、`tests/outlook_helpers.py`、`scripts/pipeline_acceptance_real.py`、`uv.lock`、`h3.yaml`、`h5.yaml`、凍結包、事先宣告、C-8 紀錄檔。
- `app/` 在 (d) 範圍以外的差異：無。
- `claims.py` 本批零差異；10 個頂層定義的 AST 都相同，包括 `register`、`production_path_refusal`、`main`、`_same_file`、`_parser`。

### 自定解讀
1. `c8_decision_ref` 直接取 C-8 紀錄檔在 git 裡的路徑字串（UTF-8 原樣）。
2. `rules_version` 依凍結包 §4 取 `outlook-market-v1.0-h3`／`-h5`；YAML 內的 `version: "1.0.0"` 不在 logic 雜湊內。
3. RC-163 抽取規則：取標題行（`### 4.1 h3.yaml`／`### 4.2 h5.yaml`）之後第一個 "```yaml" 行，與其後第一個 "```" 行之間的所有行，原樣串接。比對的是 HEAD 的 blob；CEO 驗收那一次的 `git_head` 屆時另外核對。
4. `registry.py`、`definitions.py`、`dirdef/__init__.py`、`definition.py` 的 docstring 仍寫著「登記表為空」，已經過時。因為 (d) 沒有列 docstring，我刻意沒改。

## 下一步
1. **（需裁決）** tech-architect 與 coordinator 決定 bootstrap 採甲案或乙案；採甲案要一併決定 (d) 怎麼處理（修 ADR，或在新 head 重跑驗收）。裁決後我再實作第 3、4 點，包括：
   - 五個拒絕條件（結束碼 4）與整筆回滾測試；
   - `prereg_doc_path` 格式檢查與 `--prereg-doc-sha256` 核對；
   - `provisional_results_seen` 0／1 各一個成功測試、一個無效輸入測試；
   - 回傳內容不含路徑的測試。
2. 給 devops-sre 的介面說明（`bootstrap --production` 的參數、結束碼、回傳每一行的格式），要等 bootstrap 定案後才能提供，本批沒有。
3. 第 1、2 項的部分可以先交 qa-reviewer（含 Codex）預審，但 CG-2 PR 整體要等 bootstrap 完成才算交件。過時的 docstring 留到接線 PR 或 ADR 放行後再更新。

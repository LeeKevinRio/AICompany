# NM-5 第二批程式碼審查

- 審查者：qa-reviewer
- 日期：2026-11-15
- 轉存：coordinator，逐字轉存 subagent 最終回報

---

## 本次結論
程式碼審查結論：**PASS，BLOCKING_ISSUES=false**。
- 七項 BLOCKING 判準我讀碼後都成立。
- 沒有 critical 或 high。medium 有 1 項，另有 low 和「凍結後待辦」。
- 我不能執行測試。`11156 passed` 與覆蓋率 97.73% 未經重現，建議 CI 或 coordinator 重跑。
- 無法執行 `/review`：`codex --version` 回報 `codex: command not found`。這次是**單家審查（只有 Claude）**，沒有跨廠商第二意見，依章程第 3 節須在 PR 前補一輪。

## 各部門回報（依 BLOCKING 判準逐項）
所有路徑都在 `apps/stock-desk/backend/` 之下。分支未 checkout，行號依 diff 內檔案行序，可能差幾行。

1. **不接線，成立。**
   - 27 個異動檔中，沒有 `app/main.py`、`app/scheduler.py`、`app/dirdef/registry.py`。
   - `app/forecast/recorder.py` 不存在。
   - `test_outlook_core_boundaries.py` 的 `test_the_recorder_does_not_exist_yet` 和 `test_dirdef_v1_0_fields.py` 的 `test_nothing_is_registered` 兩個測試都釘住這點。
2. **PIT 與 look-ahead，成立。**
   - 特徵只讀 `snapshot_view` 的 `closes_by_lag`，lag 0 是 T。`app/outlook/inputs.py` 的 `snapshot_view` 遇到晚於 T 的 bar 會 `FutureBarError`，`evaluate_outlook` 和 `compute_baselines` 都經過它。
   - `app/outlook/engine.py` 的 `evaluate_outlook` 把 `features.sigma.value is None` 或 `E-PIT-UNVERIFIED` 判為 `blocked`，`aggregate` 直接回 `insufficient`。
   - 第 (0) 步和 FX-F5 有測試（`test_fx_f5_*`、`test_a_naive_fetch_stamp_is_pit_unverified`）。
   - `_cut_snapshot` 和 `_cut_and_compute` 只在 `app/outlook` 內。`test_the_decision_session_cut_is_never_named_outside_outlook` 掃全 `app/`。
   - ADR-0030 D-3 第 5 點：`test_forecast_hindsight_sources.py` 新增 `{"outlook/baselines.py", "outlook/engine.py", "outlook/inputs.py"} <= names`，新檔納入掃描。
   - 實作者留的例外：`late_cutoff_at` 搬到 `app/outlook/inputs.py`，`app/forecast/store.py` 改 import 並 re-export。**合理。**
     - 該函式只把 T 對應到截止時刻，不讀 bar、不算標籤、不能選 T。
     - 依賴方向 forecast → outlook 符合 K-2，也讓 `late` 和 `E-PIT-UNVERIFIED` 共用同一個定義。
     - `test_the_store_uses_the_one_cutoff_definition` 和 `ALLOWED_OUTSIDE == {"late_cutoff_at"}` 且只有 `forecast/store.py` 使用，這兩個測試都釘住。
3. **engine 實作 D-2.3，成立。**
   - `aggregate`（engine.py）：完整度 `Fraction(evaluable, len) < Fraction(min_completeness)`；W 是命中的多方權重減空方權重，以 `Fraction` 計算；`abs(w) < Fraction(theta)` 判 range；`range_basis` 由有無 range 規則命中決定。
   - engine 內沒有規則參數的數值常數：`test_the_engine_holds_no_rule_parameter_value` 確認沒有 float 字面值，整數只限 {0,1,3,5,20,60,120}。
   - `holds` 在 `app/outlook/engine.py` 定義，`^def holds\(` 全 `app/` 只出現一處。
   - `test_w_and_theta_are_compared_as_fractions` 用 0.1+0.2 做反例，有鑑別力。
   - 「`missing` 非空 ⇔ insufficient」：min_completeness=1.0 時，凍結包 2.5 的推導成立（σ120＝0 的特例會連帶 σ_d＝0）。
4. **TA Q1、Q2，成立。**
   - `app/dirdef/rules.py`：`invalidation: OutlookCondition`，守門 (a) 欄位在 `OUTLOOK_RULE_FIELDS` 內、(b) 欄位集合等於 condition 的。
   - `test_dirdef_rules_aggregation_invalidation.py` 各有反例：子集、缺 ref、多欄位、未列欄位；兩個欄位集合也測了順序和重複不影響。
   - `test_invalidation_is_the_negation_of_the_condition_on_the_grid`：27×9×9×5 格，用 `nextafter` 取邊界值，檢查 `holds(invalidation) != holds(condition)`。
   - `AggregationNumber = float, strict, allow_inf_nan=False`，加 `theta>0`、`0<min_completeness<=1`。測試覆蓋 bool、0、負值、nan、inf、>1、字串、null。
   - `theta: 2` 與 `2.0` 的雜湊相等有測試（`test_theta_2_and_2_0_give_one_logic_hash_and_3_another`）。pydantic strict float 收 int 並轉 float 是我的讀法，見下方「建議實證」。
5. **兩份 YAML：未獨立重算，採信 coordinator 的 sha256。**
   - `test_outlook_rule_files.py` 釘 sha256（f4f366a5…／0a385de3…）、8,290 bytes、LF、單一結尾換行，並檢查 h5 只是 h3 改 horizon。
   - 通過規則載入器和 banned phrases。
   - 預期與凍結包第 4 節逐位元組相同。
6. **常數，成立。**
   - G7 值在 `tests/dirdef_helpers.py` 的 `DIRDEF_V1_0_G7`，我逐項看過：K=0.43、EPS=1e-12、SIGMA_WINDOW=60、SIGMA_MIN_VALID=55、SIGMA_FLOOR=0.001、B2_WINDOW=250、B2_MIN_REALIZED=120、MAJORITY_TIE_ORDER=(range, bullish, bearish)、NEFF_BLOCK_LEN3/5=3/5、SEASON_MONTHS=(6,7,8,9)、檢查點 (30,60,100,150,250,500)、ALPHA_FAMILY=0.05 等，都對得上。
   - `n_snapshot` 是唯一導出函式。`app/` 內沒有 315 字面值，`test_n_snapshot_is_315` 釘住 315。
   - `n_min`、`market_checkpoint_count`、`alpha_star` 各只有一個函式，並有測試。
7. **測試全用合成資料，成立。**
   - 資料來自凍結包 2.10 的對數水準與 `la_series` 決定性序列；`FakeIndexService` 不連網。
   - `test_outlook_rc143_pit.py` 的 ledger 用 `tmp_path`。
   - 我沒看到真實 `^TWII` 值。

### 另請判定

**A. `inputs` 以 Protocol 接收，不 import `app.services.index`（給 TA 的意見，供 SP-B）。**
- 意圖仍成立，建議 TA 以「經 `app.services.index` 取得」解讀。
- 理由：
  - ADR-0030 K-2 禁止 `app.outlook` 到達 `app.portfolio`、`app.positions`。
  - 實測 `test_the_index_service_reaches_packages_the_outlook_may_not` 證明 `app.services.index` 會到達這兩者。
  - 字面 import 與 K-2 矛盾。
  - 測試用真的 `load_market_benchmark` 產生 answer，並有靜態 `_AS_ANSWER: IndexSeriesAnswer = LoadedBenchmark(...)` 檢查。
- 殘留風險 [可維護性][low]：Protocol 只驗形狀，`inputs.py` 的 `capture_market_snapshot` 只檢 `series_symbol == "^TWII"` 和每根 bar 的 symbol，不驗 `status`、`source` 是否為 ADR-0005 的 backup 路徑。
- 建議條件：recorder 批要有測試，證明唯一呼叫點把 `load_market_benchmark(...)` 的回傳值傳入；`status != backup` 的處置由 recorder 決定並列入規格。

**B. `OUTLOOK_RULE_FIELDS` 由空集合改為 9 個欄位，並改掉釘「必須為空」的測試：理由成立。**
- ADR-0030 CG-2（約第 174 行）寫明「`OUTLOOK_RULE_FIELDS` 已設定」。原「必須為空」的釘子只是等凍結，新釘子是凍結包 G3 的 9 個欄位。
- 失守的是 fail-closed 的 `test_with_the_empty_field_list_every_rule_set_is_refused`，已改為 `test_with_the_production_field_list_a_fixture_field_is_refused`，仍驗證「清單外欄位會被拒」。
- 風險 [low]：欄位集合提前在第二批落地，早於 CG-2 登記批；因不接線且不登記，無實際影響。

**C. 現行程式下必定通過、沒有鑑別力的測試：沒有發現會讓 PIT、標籤或雜湊失守的。**
- `test_every_result_keeps_missing_iff_insufficient` [low]：engine 自己違反會 raise，此測試是重複檢查。
- `test_the_field_table_covers_exactly_the_rule_fields` [low]：名稱說「exactly」，只檢查 9 欄各有 requirement（單向）。反向由 LA-G2-7 的 `test_la_g2_7_every_feature_name_in_the_engine_is_a_rule_field` 補上。
- LA-G2-1、LA-G2-2 的篡改測試：通過路徑是 `_cut_snapshot` 在切片時丟掉晚於 T 的 bar。但這正是 recorder 實際使用的路徑，不算空測；`test_la_g2_3_*` 另外驗證 `snapshot_view` 的拒收。

### Findings
- [可維護性][medium] `app/outlook/engine.py` 的 `_OPS`：8 個比較運算與 `app/advice/engine.py` 的 `COMPARISON_OPS`（約 124-131 行）重複定義。
  - K-2 不允許 outlook import `app.advice.*`，所以重複是被迫的。
  - 風險：「`holds` 是 `app/` 內唯一求值器」的測試只 grep `def holds(`，不涵蓋 advice 的求值器。兩份運算表日後可能分歧。
  - 要求：不阻擋。建議在 `test_outlook_core_boundaries.py` 加一個測試，斷言兩份運算表的 key 集合相同；或將運算表抽到 `app/dirdef` 共用。
  - 此項依 CEO #139 規則不屬於 PIT、標籤或雜湊，但分歧可能導致標籤與凍結包不符，故列 medium。
- [Edge case][low] `app/outlook/engine.py` 的 `evaluate_outlook`：若 `min_completeness < 1` 的規則集遇到無法評估的規則，會 raise `OutlookInvariantError`，不會落帳。
  - `test_a_completeness_below_one_that_hides_a_root_cause_is_refused` 釘的就是這個行為。
  - 凍結的兩份 YAML 為 1.0，不受影響，列凍結後待辦：若日後放寬，須先決定放寬時 missing 的語意。
- [可維護性][low] `app/outlook/engine.py` 的 `PIT_ITEM = "inputs_max_fetched_at"` 是暫定名，等 TA 裁（FX-F5「item 由 TA 定」）。測試 `test_fx_f5_*` 也釘了此字串，TA 改名時須同批改測試。
- [Edge case][low] `app/outlook/inputs.py` 的 `capture_market_snapshot`：中間若有未定案 bar 被丟掉、後面有定案 bar，快照在序列上會有缺口，lag 以快照位置計而非交易日曆。`dropped` 有記錄，但沒有測試證明缺口時特徵語意。屬凍結後待辦，建議 recorder 批決定是否視為 `inputs_not_ready`。

## 驗證
- 唯讀權限判準常數：**未觸及**。
  - 第一道：本批 27 個異動檔全在 `apps/stock-desk/backend/`，不含 `scripts/validate_agents.py`。
  - 第二道：`git diff <base> <head> -G"READONLY_AGENTS|READONLY_ALLOWED_BASH" --name-only` 無輸出（我用 `-G` 取代 pipe + grep，只准單一指令）。
  - 沒有 shadow 定義，也沒有成員資格或值的異動。
- 跨廠商：Codex 不可用，單家審查。
- 本次僅讀 diff，沒有執行測試、沒有讀 `.env`、沒有碰 `apps/stock-desk/backend/data/*.db`。

### 建議實證（讀碼無法確定，請 CI 或 coordinator 確認）
1. `theta: 2` 與 `2.0` 雜湊相同，依賴 pydantic strict float 接受 int 並轉成 float。測試 `test_theta_2_and_2_0_give_one_logic_hash_and_3_another` 本身覆蓋此點，重跑即可實證。
2. `11156 passed` 與覆蓋率 97.73% 需重跑。
3. mypy strict：`_AS_ANSWER: IndexSeriesAnswer = LoadedBenchmark(series_symbol="^TWII")` 這個靜態檢查，只有跑 mypy 才驗證得到。

## 下一步
1. 實作者回報的 SP-A、SP-B、SP-C 仍交 TA 裁示。我對 SP-B 的意見在上面「另請判定 A」。
2. 本批可進入 `risk-gate` 或 CEO 彙整；但章程要求跨廠商第二意見，請在可用 Codex 的環境補跑 `/review`，再放行 PR。
3. 凍結後待辦：
   - 兩份運算表 key 一致測試或共用運算表。
   - `min_completeness < 1` 時 `missing` 的語意。
   - 快照缺口時的 lag 語意。
   - `PIT_ITEM` 正式命名。
   - recorder 批對 `status`、`source` 的處置，以及唯一呼叫點的測試。
4. 本報告不需退回實作者。

相關檔案（均相對 `/home/user/AICompany/apps/stock-desk/backend/`）：`app/outlook/engine.py`、`app/outlook/inputs.py`、`app/outlook/baselines.py`、`app/outlook/volatility.py`、`app/dirdef/rules.py`、`app/dirdef/definition.py`、`app/forecast/store.py`、`app/outlook/rules/h3.yaml`、`app/outlook/rules/h5.yaml`，以及 `tests/` 下的 `test_outlook_*`、`test_dirdef_*`、`outlook_helpers.py`、`dirdef_helpers.py`。

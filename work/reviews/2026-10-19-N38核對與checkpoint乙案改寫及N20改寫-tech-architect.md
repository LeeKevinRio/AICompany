# N-38 核對、checkpoint 乙案改寫、N-39、N-20 改寫

- 審查者：tech-architect
- 日期：2026-10-19
- 轉存：coordinator，逐字轉存 subagent 最終回報

---

# tech-architect 回報：N-38 核對、checkpoint 依乙案改寫、N-39、N-20 改寫

這份只是提案，我沒有改任何檔案。沒有讀 `.env`，沒有碰 `*.db`，也沒有跑 git 或程式。

---

## 一、本次結論

**N-38 不成立，但缺口只有一個，而且很窄。甲案也修不了它。**

1. **缺口 G-1**：待重算集合中 `reason = write_validation_failed` 的項，沒有期限上限的終局。
   - 依據【事實】：ADR D-9 第 5 點「待重算」，字串「這一種不是資料尚未到齊，不適用事先宣告 N-29 (b) 的期限，不因到期改記作廢；處理路徑只有一條：查出根因，修正程式或本條，送風控。」（本次讀取時 L1222 一帶）；事先宣告 L1575「因寫入驗證被拒而待重算的列，不適用本期限」。
   - 後果【推論】：只要有一筆這種項的 T 落在前綴內，n_complete 就停住。其他紀錄照常結算、n(S) 照常增加，閘門卻可能永遠擋住 F-2 的判定，包括退出期限。這就是風控所說「負面那一側放行」。
   - 其餘各種紀錄都有到得了、而且有上限的終局（逐項見第二節 1）。
2. **甲案也有同一個閘門**（風控第四節 coordinator 第 3 點寫明「閘門仍以終局可達為前提」），所以改走甲案解決不了 G-1。
   - 我依指示附上甲案字面，寫成相對乙案的差異清單（第二節 2-H）。
   - 我建議的做法是：**用補法 α 修補閘門，然後仍採乙案**。補法 α：這類項不讓閘門等待，但會使該檢查點的正面結果不認列。
   - α 屬統計定義，要 quant 登記進 v0.22 第 2 點，再由風控裁定。α 不被採用時，第 2 點不得落檔。
3. **另有兩個定義缺口**：
   - **G-2**：ADR 沒有明文寫證據不足的紀錄要結算。這類紀錄的 `threshold_snapshot` 不存在時，`realized_*` 怎麼算也沒有定義。這不影響「終局」的判定，但要在 D-9 實作前補上。
   - **G-3**：「前綴有變動」原本的列舉用「例如」，無法機械檢查。我改成封閉列舉，並加了第 0 相位格點的雜湊比對。
4. **N-39**：現行條文沒有規定「T 日 snapshot」指 daily 列還是 checkpoint 列。我也找到一個更早就存在的漏洞：同一 T 的 daily 列沒有承接 checkpoint 列結果的規則【推論】。這兩點都已給字面。
5. **N-20**：已依風控第二節 C 改寫。兩個 suggested 都**採用**：
   - 身分用 `{recorded_at, kind, session_date}` 三欄，主 DB 端存成一個 JSON 欄，欄數不變；
   - 把 `forecast_gap_audit.market_run_current` 的歷史最大值納入參考候選。

   這兩項會連動 ADR-0026（devops-sre 的平行稿）與 ADR-0029 E-2，要同批送風控。

| 項 | 方向 | CEO | 擋 |
|---|---|---|---|
| G-1 補法 α | 收緊。另一面：前綴少一筆紀錄時，負面結果可能少一筆支持 | 知悉 | D_v（v0.22 第 2 點的前提） |
| checkpoint 批（乙案） | 補定義（兩面），放寬面照風控原文並陳 | 知悉 | D_v |
| N-39 | 補定義（收緊） | 否 | D_v |
| N-20 批 | 收緊 | 否 | 不擋 D_v；身分比對的程式不得早於 ADR-0026 2-1 落檔 |

---

## 二、各部門回報（tech-architect）

### 評估摘要

- **採用**：
  - 乙案，加上補法 α；
  - 前綴變動改為封閉列舉，加格點雜湊比對；
  - views 一律只讀 daily 列，同一 T 先算 checkpoint 列、daily 列承接其結果；
  - N-20 丙案：身分三欄、參考候選三方、守衛函式在同一個市場 DB 唯讀交易內讀出 r_now 與身分。
- **否決**：
  - 以改走甲案解決 G-1：甲案有同一個閘門；
  - G-1 採「閘門無限期等待」：負面那一側會放行；
  - 身分比對只用 `recorded_at`：可以，但三欄的成本是零，又只會更嚴；
  - 由呼叫端傳入 r_now：做不到「同一次讀取」。

### 方案比較（G-1）

| 方案 | 優點 | 缺點 | 風險 |
|---|---|---|---|
| **α：這類項視同終局、不計入 n、不屬於 P_j，該檢查點強制「延後且前綴有變動」（採用）** | 判定時點有上限；正面結果拿不到好處；負面結果照常生效 | P_j 少了那一筆，負面結果可能因此少一筆支持 | 最多一筆對 n_j ≥ 30 的影響；需要揭露 |
| β：這類項在閘門中視同作廢、計入 W | 最壞情境計入 W | W 與實際作廢混在一起，報表語意不清 | 修程式的時點會改變 W |
| γ：被這類項擋住、n(S) 已到 150 時，條件二直接成立 | 退出期限不被延後 | 非退出期限的檢查點仍被無限期擋住，條件一永遠不判 | 一個程式錯誤就可能讓模型下架 |
| 甲案 | — | 閘門相同，G-1 照樣存在 | 同乙案 |

### 方案比較（N-20 兩個 suggested）

| 方案 | 優點 | 缺點 | 風險 |
|---|---|---|---|
| **身分三欄、存成 JSON 欄（採用）** | 兩條時間線要三欄全同才會漏報；主 DB 欄數與原案相同 | ADR-0026 (b)(c) 要比對同樣的三欄 | 兩份 ADR 不一致：同批送審 |
| 身分只用 `recorded_at` | 與 ADR-0026 現稿一致 | 漏報只差一個條件 | 只有固定 clock 的測試環境才會出現 |
| **參考候選加 gap_audit 歷史最大值（採用）** | 結算連日失敗、而缺日稽核照跑時，參考值不會過時 | 多一個 JSON 欄；ADR-0026 參考 run 的取法與 ADR-0029 列舉都要改 | 低 |
| 不納入 | 改動少 | 結算失敗期間若市場 DB 被單獨還原到參考值之後，守衛偵測不到；缺日稽核可能據此做出永久的未觀察平日登記【推論】 | 永久性的錯誤登記 |

---

### 1. N-38 核對結果

**(1) 證據不足與作廢的紀錄，是否都寫 `forecast_outcome` 列？**

- **作廢：會寫。**【事實】
  - D-3 `forecast_outcome` 的「狀態：`status ∈ {resolved, unresolvable_missing_data, excluded_corporate_action}`」（本次讀取 L315）；
  - D-9.2 ⑥「結算或作廢的寫入 `forecast_outcome`」。
  - 作廢之後是吸收態：「依 R10-3，作廢列不會再被 supersede，所以鏈尾固定。」（L393）【事實】。不會因 X2 列入待重算【推論】：依 L382，鏈尾已是作廢列時不重算。
- **證據不足：會寫，但 ADR 沒有明文。**【推論】依據下列【事實】：
  - 評估集合 U 是「沒有任何 `forecast_outcome` 列的 `forecast_record`」，「不分 `trigger`、`late`」，不依 label 篩選（D-9.2 ②）；
  - 「等待與否只依可用的 T+h 資料是否存在，不讀 label」（D-9.2「全量評估」）；
  - 「所以等待期滿時，每一筆都恰為 `resolved` 或作廢之一」（D-9 第 3 點 `missing_bar_after_wait` 的期限子點）。
  - ADR 的 D-9 段落內沒有 `insufficient` 的規則（grep 0 筆）；「`hit` 為 null」只寫在事先宣告 L1471。
  - **G-2（定義缺口）**：事先宣告 L1469 規定 `realized_z`、`realized_label` 依該筆的 `threshold_snapshot` 計算。證據不足的紀錄可能根本沒有 σ_d，例如 `SIGMA_MIN_VALID` 不足。這時結果沒有定義。
    - 如果 `scoring.py` 因此拋例外，整個結算評估都不寫入，屬於系統性停擺，不是閘門特有的問題。
    - 補法要交 quant 定義、TA 落字（見第四節）。
  - 證據不足的紀錄若結算為 resolved，之後可能因 X2 順延而列入待重算，和其他 resolved 列一樣。所以 quant 的句子要加但書（字面見第四節）。

**(2) E 內每一種紀錄的終局與期限上限**

| 紀錄種類 | 到得了的終局 | 期限上限 | 依據 |
|---|---|---|---|
| 尚未結算（T+h 未觀察、`valid_until` 未過、等待中） | 結算或作廢 | 第 h＋5 個觀察日（D_5） | 【事實】D-9 第 3 點期限子點 |
| resolved 鏈尾、不在待重算集合 | 已是終局 | — | 【事實】D-11.1 鏈尾 |
| 作廢鏈尾 | 已是終局（吸收） | — | 【事實】L393 |
| 待重算 (b)：已確認的 X2 事件，還沒經過更正作業 | 下一個更正作業處理 | 一次作業（x2 是第一類觸發） | 【事實】D-3「晚到資料的觸發」第 1 點；D-11.4 第 11 點 (g) (b) |
| 待重算 (a)：`shift_*` 三種 | 結算，或依 N-29 (b) 改記作廢 | 順延後 T+h 之後第 5 個觀察日，由已完成的作業判定；每個新觀察日都會觸發重查 | 【事實】事先宣告 L1575；ADR 第四類觸發。重複的 X2 確認會再延長，上限是 X2 確認的筆數【推論】 |
| **待重算 `write_validation_failed`** | **只有人工修正程式或條文之後才到得了** | **沒有** | **【事實】D-9 第 5 點「待重算」；事先宣告 L1575 → G-1** |
| 不在 E 的紀錄（逾時、on-demand、PIT 違規確認） | 不相關 | — | 【事實】D-11.1 |

- 系統性停擺不是閘門造成的問題【事實】。結算或更正作業持續失敗時，D-7 第 2 點的前置條件會讓驗證快照整個不寫（字串「本次執行的結算評估已 commit…本次晚到掃描與更正作業已完成」），所以檢查點本來就不會判定。閘門特有的危害，只在「單一紀錄卡住、其他紀錄照常結算」的情形出現；G-1 是唯一符合這個情形的紀錄種類。

**(3) job_end「進出待重算集合」能否由已存資料機械判定？能。**【推論】依據下列【事實】：

- 每一列 job_end 的 `pending_json` 都存下作業結束時的完整集合，依 `forecast_id` 排序（D-3 `pending_json`）；
- job_end 依 `correction_job_id` 遞增寫入（D-3「晚到資料的觸發」第 5 點「沒有 `correction_job_id` 大於本作業、已有 end 列的作業」）；
- snapshot 存了 `e_read_job_end_seq`（D-11 第 2 點）；
- T 取 `forecast_record.data_as_of`。

判定方法：把 (prev 的序號, 本筆的序號] 之間每一列 job_end 的集合，和它前一列 job_end 的集合比較，取對稱差。

- 要逐列比較，不能只比兩端。原因是「重查後沒有任何欄位改變」這種出口不寫 supersede 列，只能從集合差看出來。
- (b) 集合（尚未處理的 X2）不經 job_end，改由事件序號判定。
- 讀取要經 D-11.4 第 11 點 (g) 那一個 `store.py` 函式，並新增「以序號區間為參數」的讀法。

**結論**：(1)、(3) 都成立。(2) 有缺口 G-1。依指示附上甲案字面（2-H）。但 G-1 在甲、乙兩案都存在，我建議以 α 修補後仍採乙案，交風控裁定。

---

### 2. checkpoint 批：(2a)～(2c) 的乙案逐字字面

**通則**：
- 行號是本次讀取當下的值，tech-writer 套用期間曾漂移約 4 行。一律以字串定位，落檔前 `grep -cF` 確認唯一。
- 標【α】的句子，要等 quant 登記、風控裁定之後才落；不採用時刪掉，而且第 2 點不得落檔。

#### 2-A　(2a) D-11 第 2 點

**定位**：在唯一字串 ``- `bootstrap_seeds_json`：鍵為 `"{purpose}|{block_len}"`，值為 seed。`` 那一行**之前**、同一層插入。效果等同接在 D-11 第 2 點的 UNIQUE 之後。不用 UNIQUE 那一行定位，因為它全檔有 2 處，另一處（L2930）是 A-5 的引文。

> - （N-23 Q3；風控 R-Q3-3）另加 `UNIQUE(claim_id, checkpoint_n) WHERE eval_kind = 'checkpoint'`：同一檔內，每個 claim 的每個檢查點只判定一次。
> - （N-23 Q3；風控 2026-10-19 乙案裁定；事先宣告 §4.5「檢查點的判定樣本、時點與 seed」v0.22，V22-01～V22-04）**checkpoint 列的判定樣本、時點與寫入**。統計面依事先宣告；本點只規定機械規則。
>   - **終局**：E 內的紀錄，在讀 E 的同一個 read transaction 內（RC‴-1）有 outcome 列、而且不在待重算集合（D-11.4 第 11 點 (g)「待重算路徑的狀態片段」的 (a)、(b) 兩個集合；事先宣告 N-29 (b) (i)）時，稱為終局。證據不足與作廢的紀錄，依 D-9 第 1、3 點寫入 outcome 列之後即為終局。作廢列依 R10-3 不再 supersede。resolved 列（含證據不足的 resolved 列）列入待重算的期間不是終局。
>   - 【α】**沒有期限的待重算項不讓閘門等待**：
>     - 最近一個已有 `forecast_correction_job_end` 列的作業，其 `pending_json` 中 `reason = write_validation_failed` 的項，不適用事先宣告 N-29 (b) 的期限（D-9 第 5 點「待重算」），沒有期限上限的終局。
>     - 計算下一子點的 U 時，這類紀錄視同終局；但不計入 n（比照 N-29 (b) (i)），也不屬於 P_j。它們列入 `checkpoint_timing.unbounded_pending`。
>     - `unbounded_pending` 非空的 checkpoint 列，`delay_kinds` 與 `prefix_change_kinds` 都含 `unbounded_pending`，依下文「延後判定規則」處理。
>     - 這類項重查後成為 `shift_*` 時，自該次作業起照常列為非終局。
>   - **n_complete 與 P_j**：
>     - 令 U 為 E 內尚未終局的紀錄中最早的 T（沒有時 U ＝ +∞）。n_complete 是 T < U 的第 0 相位格點中，符合事先宣告 §4.1 n 條件的個數。
>     - P_j 是依決策日 T 升冪、前 n_j 個符合 §4.1 n 條件的第 0 相位格點；多對象合併時以決策日為單位。T\*_j 是其中最後一個格點的決策日。
>     - 兩者只由 `validation.py` 的單一函式 `checkpoints_due(claim_id, *, e_view) -> CheckpointsDue`（名稱暫定）計算。`e_view` 是本筆 snapshot 經 `store.py` 讀 E 的函式，在同一個 read transaction 內的回傳物件。
>     - 回傳 `n_complete`、`unbounded_pending`，以及到期的 n_j，升冪。到期的 n_j 指：事先宣告 §4.5 的檢查點中 ≤ n_complete、而且本檔內還沒有同一 `checkpoint_n` 的 checkpoint 列者。
>     - 簽章不接受 n、n_complete、檢查點清單、樣本或判定結果（AST）。
>     - checkpoint 列上的 §4.3 (a)～(f)、§4.2 各項指標、作廢率與 W，以及 D-12 的 `fail_normal`、`fail_w`、`void_rate`，一律只在 P_j 的紀錄上計算，各紀錄取同一 `e_view` 的鏈尾。P_j 只由同一模組的單一函式 `checkpoint_sample(claim_id, n_j, *, e_view)` 取得。
>     - checkpoint 列的 `n` ＝ n_j。
>   - **寫入時點**：
>     - 驗證快照寫入 T 的 daily 列時，若 `checkpoints_due` 回傳的到期集合非空，就在同一個交易內，為其中最小的 n_j 寫一列 checkpoint 列（`checkpoint_n = n_j`，`computed_for_session = T`）。其餘到期的 n_j，依升冪由之後各筆寫入成功的 daily snapshot 判定。
>     - 寫入驗證：本交易為每個 claim 寫入的 checkpoint 列，與上述規則恰好相符；不符就整個交易 rollback（D-7 第 2 點 Q3 全有或全無）。
>     - 所以檢查點只在「n_complete 達到 n_j、較小的檢查點都已判定、而且寫入成功的第一筆 daily snapshot」判定：不能提前，不能延到之後任何一筆，也不得補寫或重判。
>     - T 的快照沒有寫入時，T 不留任何 checkpoint 列，之後也不補寫 T 的列。
>   - **記錄欄位**（全部由寫入函式自行填入，不接受呼叫端傳入）：
>     - daily 列的 `stats_json` 另記：
>       - `n_complete`；
>       - `phase0_grid_sha256`：取寫入當下 `observed_sessions(as_of=None)` 導出的第 0 相位格點中、決策日 ≤ `computed_for_session` 者，依日期升冪，以 ISO 日期字串組成 JSON 陣列（`separators=(",", ":")`，UTF-8），再取 sha256。
>     - checkpoint 列的 `stats_json` 另記 `checkpoint_timing = {prev_daily_session, skipped_observed_sessions, n_at_eval, n_complete, prefix_last_session, delayed, delay_kinds, prefix_changed, prefix_change_kinds, unbounded_pending, n_first_reached_session, gate_delay_observed_sessions}`：
>       - `prev_daily_session`：該 claim 在本檔內、`computed_for_session` < T 的最新一筆 daily 列（下稱 prev）的 `computed_for_session`；沒有時為 null。
>       - `skipped_observed_sessions`：|寫入當下的 `observed_sessions(as_of=None)` ∩ (prev, T)|，不含兩端；prev 為 null 時為 null。
>       - `n_at_eval`：同一 T 的 daily 列的 n。
>       - `prefix_last_session`：T\*_j。
>       - `delay_kinds`：⊆ {`no_prev_daily`, `sessions_skipped`, `multi_due`, `unbounded_pending`}，固定排序。各值的成立條件：
>         - `no_prev_daily` ⇔ prev 為 null；
>         - `sessions_skipped` ⇔ `skipped_observed_sessions ≥ 1`；
>         - `multi_due` ⇔ prev 的 `stats_json.n_complete ≥ n_j`，或 prev 沒有記下 `n_complete`；
>         - `unbounded_pending`【α】依上文。
>       - `delayed` ⇔ `delay_kinds` 非空。
>       - `prefix_change_kinds`：⊆ {`no_prev_daily`, `outcome_superseded`, `e_event`, `pending_set_changed`, `grid_changed`, `unbounded_pending`, `undeterminable`}，固定排序。任一項成立就記入；`prefix_changed` ⇔ 非空。各值的成立條件：
>         - `no_prev_daily`：prev 為 null；
>         - `outcome_superseded`：存在 `outcome_id > ` prev 的 `e_read_outcome_seq`、`supersedes_id IS NOT NULL`、而且所屬紀錄的 T ≤ T\*_j 的 `forecast_outcome` 列；
>         - `e_event`：存在 `event_id > ` prev 的 `e_read_event_seq` 的 `forecast_ledger_events`，而且 (i) `kind ∈ {x2_confirmed_non_session, unobserved_weekday}`，或 (ii) `kind ∉ E_NEUTRAL_EVENTS`、而且 payload 指向 T ≤ T\*_j 的紀錄，或沒有可以歸屬到單一紀錄的 `forecast_id`；
>         - `pending_set_changed`：`correction_job_id` 落在 (prev 的 `e_read_job_end_seq`, 本筆的 `e_read_job_end_seq`] 內、而且已有 `forecast_correction_job_end` 的每一個作業，以其 `pending_json` 的 `forecast_id` 集合，與前一個已有 end 列的作業的集合（沒有時為空集合）比較；任一個對稱差中有 T ≤ T\*_j 的紀錄；
>         - `grid_changed`：用寫入當下的 `observed_sessions(as_of=None)` 重算第 0 相位格點，取決策日 ≤ `prev_daily_session` 者，依上述格式算出的 sha256，不等於 prev 的 `stats_json.phase0_grid_sha256`；
>         - `unbounded_pending`【α】：`unbounded_pending` 非空；
>         - `undeterminable`：prev 缺少上述任一比較基準（三個序號或 `phase0_grid_sha256`），或任一項判斷不了。
>       - 以上各項只由單一函式 `checkpoint_prefix_changed(...)` 判定（AST）。讀 `pending_json` 經 D-11.4 第 11 點 (g) 讀取待重算集合的同一個 `store.py` 函式，新增以 job_end 序號區間為參數的讀法（AST 列舉呼叫點）。
>       - `n_first_reached_session`：本檔內該 claim、`n ≥ n_j` 的最早一筆 daily 列的 `computed_for_session`。
>       - `gate_delay_observed_sessions`：|`observed_sessions(as_of=None)` ∩ (`n_first_reached_session`, T]|。
>   - **延後判定規則**（事先宣告 §4.5 v0.22 第 4 點）：
>     - `delayed` 與 `prefix_changed` 都為真的 checkpoint 列：正面結果（升為 `better_than_baseline`、重新上架）不認列；負面結果（降級、F-2 下架）照常生效。
>     - 記法比照 A-28 (ii)：`stats_json.raw_checkpoint_result` 照寫，`suppressed_positive.cause = checkpoint_delayed`。多個原因同時成立時，依 D-11.4 第 12 點 (ii) 的優先序取第一個。
>     - 比照 A-28 (iii)：在 n＝150（族群 250）時正面結果不認列，F-2 條件二成立，不得因此延後退出期限。
>     - `delayed` 為真、`prefix_changed` 為假的列，正面結果照常認列。理由：依事先宣告 §4.5 v0.22 第 1～3 點，它的樣本與 seed 與準時判定逐位相同。
>   - LM-74（「到事先宣告的期限，仍未能證明優於基準」）在 `cause = checkpoint_delayed` 的情形下同樣屬實：有效狀態不是 `better_than_baseline`，原始結果另記於 `stats_json.raw_checkpoint_result`，並在 §4.2「延後判定的檢查點」揭露。
>   - 不得提供以操作者指定的 claim、n_j 或日期，寫入、延後或重判 checkpoint 列的 CLI、API 或參數（grep／AST）。
>   - §4.2「延後判定的檢查點」（事先宣告 v0.22，V22-05）的資料來源是上述欄位：
>     - 列出 `delayed` 為真、`n_at_eval > checkpoint_n`，或 `gate_delay_observed_sessions ≥ 1` 的每一列 checkpoint 列，依 `delay_kinds` 分列；
>     - 每列附：claim、`checkpoint_n`、`n_at_eval`、`n_complete`、`prefix_last_session`、`computed_for_session`、`prev_daily_session`、`skipped_observed_sessions`、`prefix_changed` 與 `prefix_change_kinds`、`unbounded_pending`、`n_first_reached_session`、`gate_delay_observed_sessions`，以及正面結果是否不認列（含 `raw_checkpoint_result`）；
>     - 另列 `prefix_changed` 為真、而且 F-2 條件一不成立的檢查點。
>   - 本點與事先宣告 §4.5 v0.22 同批生效，不得單獨落檔。本點不改檢查點的值、退出期限與 5% 門檻。

錄存：
- 無被取代原文。
- 修訂紀錄要註明：TA 2026-10-18 原稿（`work/reviews/2026-10-18-N23風控補充項回覆-tech-architect.md` 第二節 2）從未寫入本 ADR，依風控 2026-10-19 裁定不落檔。
- 註明延後種類不沿用 `snapshot_skipped`。這樣才符合 coordinator 的機械核對：`snapshot_skipped` 要是 0 筆。

#### 2-B　(2b) `cause` 列舉，三處

1. **L1313**：
   - 定位字串（唯一）：``記法比照 A-28 (ii)：`stats_json.raw_checkpoint_result` 照寫；`suppressed_positive` 加必填欄位 `cause ∈ {suspended_f3, db_restored}`。``
   - 把 `` `cause ∈ {suspended_f3, db_restored}`。 `` 改為 `` `cause ∈ {suspended_f3, db_restored, checkpoint_delayed}`（`checkpoint_delayed` 依本點 N-23 Q3）。 ``
2. **L1816**：
   - 定位字串（唯一）：``cause ∈ {suspended_f3, db_restored}}`（`cause` 必填；`db_restored` 依 D-11 第 2 點 N-5 甲案）；``
   - 改為：``cause ∈ {suspended_f3, db_restored, checkpoint_delayed}}`（`cause` 必填；`db_restored` 依 D-11 第 2 點 N-5 甲案；`checkpoint_delayed` 依 D-11 第 2 點 N-23 Q3）；``
3. **L1817**：照風控第四節 tech-writer 第 2 點的兩句，逐字套用：
   - 「同一個檢查點兩個原因同時成立時，`cause = suspended_f3`（與第 12 點的優先序一致）。」這一句全檔有 2 處，只改 L1817，不改 L3831 的引文。
   - 在「不得因為 `cause` 只記一個值而只計一邊。」之後，接風控給的 N-23 Q3 那一句。

錄存：三處的被取代原文，逐字錄進修訂紀錄的新批段「N-23 checkpoint 批（乙案）」，不在正文加〔取代〕。L1314 的 db_restored LM-74 一句不改。

#### 2-C　(2c) FL-71 (i)

**定位字串**（唯一）：`任一 claim 的 checkpoint 列寫入失敗 → 該 T 的 daily 與 checkpoint 列全部不寫。`。在句末、「Q3 部分 claim」那一句之前接：

> （N-23 Q3；事先宣告 v0.22 LG-33）checkpoint 列：
> (1) 同一份資料，T 略過與未略過兩個 fixture，窗內沒有更正 → 兩列的 `raw_checkpoint_result`、§4.3 各值與 `bootstrap_seeds_json` 逐位相同；略過者 `delay_kinds = ["sessions_skipped"]`、`prefix_changed` 為假，正面結果認列。
> (2) 略過，而且 prev 之後有 T ≤ T\*_j 紀錄的 supersede 列 → `prefix_change_kinds` 含 `outcome_superseded`；正面結果不認列、`cause = checkpoint_delayed`；負面結果生效。
> (3) supersede 只涉及 T > T\*_j 的紀錄 → 正面結果認列。
> (4) 較早的格點仍在等待、n(S) ≥ 30 而 n_complete < 30 → 不寫 checkpoint 列。該格點終局之後的第一筆才寫，樣本恰為前 30 個格點（spy `checkpoint_sample`），`gate_delay_observed_sessions` 等於 fixture 值。
> (5) 證據不足的格點寫入 outcome 列之後，閘門打開；作廢的格點也一樣。
> (6) 30 與 60 同時到期 → 只寫 30，下一筆寫 60，60 那一列的 `delay_kinds` 含 `multi_due`。
> (7) prev 之後有 `x2_confirmed_non_session` 或 `unobserved_weekday` 事件 → `prefix_change_kinds` 含 `e_event`。沒有任何事件、但觀察日集合使 prev 的第 0 相位格點改變 → 含 `grid_changed`。
> (8) prev 之後，某作業的 `pending_json` 加入或移除一筆 T ≤ T\*_j 的紀錄，而且沒有 supersede 列 → 含 `pending_set_changed`。
> (9) n＝150 延後判定、前綴有變動、原始結果是正面 → 有效狀態不是 `better_than_baseline`，`withdraw_reason = f2_deadline`，`cause = checkpoint_delayed`。
> (10) 與 `db_restored` 同時成立 → `cause = db_restored`，§4.2「整檔還原」與「延後判定的檢查點」兩列都計入。與 `suspended_f3` 同時成立 → `cause = suspended_f3`；`positive_suppressed_during_f3` 不因 `checkpoint_delayed` 而設定。
> (11) prev 沒有 `n_complete` → `delay_kinds` 含 `multi_due`。prev 缺少 `phase0_grid_sha256` → `prefix_change_kinds` 含 `undeterminable`。
> (12) 同一 n 的 daily 列與 checkpoint 列，以及延後與準時的 checkpoint 列，`bootstrap_seeds_json` 都相同；`eval_key` 為 `n{n}`。
> (13)【α】T ≤ T\*_j 的一筆待重算項 `reason = write_validation_failed` → 閘門不等它，checkpoint 列照寫；`unbounded_pending` 含該 `forecast_id`，該筆不在 P_j；正面結果不認列，負面結果生效。該項重查後成為 `shift_*` → 自該作業起照常擋住閘門。
> (14) 同一 claim 第二列 `checkpoint_n = 30` → UNIQUE 拒絕。`checkpoints_due`、`checkpoint_sample`、`checkpoint_prefix_changed` 在 `app/` 內各恰好一個定義；簽章不接受 n、n_complete、檢查點清單、樣本或判定結果（AST）。`app/` 與事先宣告內沒有 `snapshot_skipped`（grep）。
> (15) 單一對象與多對象各一組。

錄存：無被取代原文；方向「收緊（測試）」。

#### 2-D　D-11.2 的 seed，兩處，正文附〔取代〕

1. **定位字串**（唯一）：``- `eval_key` 前瞻用 ISO 日期 `YYYY-MM-DD`，重放用 `freeze_commit`；``。整行換成：
   > - `eval_key` 前瞻用該列的 `n`，寫成 `n{n}`（十進位、不補零，例如 `n30`；daily 列取 daily 列的 n，checkpoint 列取 n_j；事先宣告 §4.3 seed 規則第 1 點，v0.22），重放用 `freeze_commit`。同一 n 跨日共用 seed 是刻意的。〔N-23 Q3 取代（事先宣告 v0.22 V22-03）：原寫「`eval_key` 前瞻用 ISO 日期 `YYYY-MM-DD`，重放用 `freeze_commit`；」〕
2. **定位字串**（唯一）：``- **`eval_kind` 刻意不放進導出式**：同一個 session 的 daily 列與 checkpoint 列用同一組 seed，checkpoint 不能換一組亂數重抽。``。整行換成：
   > - **`eval_kind` 刻意不放進導出式**：同一 n 的 daily 列與 checkpoint 列用同一組 seed，延後與準時判定的 checkpoint 列 seed 相同。checkpoint 不能換一組亂數重抽，判定日也不能移動 seed。n(S) ＝ n_j 時，依本點「checkpoint 列的判定樣本、時點與寫入」，同一天的 daily 列與 checkpoint 列樣本相同、seed 相同，結果逐位相同。另一面（照實並陳）：同一 n 的期間（最長到 n 增加為止）不再每天換一組亂數，所以只因蒙地卡羅雜訊造成的降級會減少；檢查點當天的 bootstrap 結果若剛好偏有利，在 n 增加之前也不會被重抽挑戰。只因資料變動造成的降級不受影響（事先宣告 §4.5 v0.22 第 3 點）。〔N-23 Q3 取代（V22-03）：原寫「同一個 session 的 daily 列與 checkpoint 列用同一組 seed，checkpoint 不能換一組亂數重抽。」〕

#### 2-E　Consequences 的殘餘句

- **定位**：唯一字串 `（剩餘待決項，N-5 甲案）**甲案的殘餘**`，在那一點之後、同一層插入風控第四節 tech-writer 第 3 點的全文，逐字照抄。
- **要風控確認一處改字**：在「延後長度受既有的等待期限與待重算期限限制【推論，未量測】」之後，插入下面這句：
  > （`write_validation_failed` 的待重算項沒有期限，依 D-11 第 2 點不讓閘門等待，改使該檢查點的正面結果不認列）

  理由：不加這句，「有上限」對 G-1 不屬實。不採用 α 時不加這句，但這時整批不得落檔。

#### 2-F　TA 2026-10-18 下一步第 7 點：給 CEO 的成本句（不入 ADR）

> 乙案下，只有「延後判定、而且判定窗內有涉及前綴的更正」，才會讓正面結果延後認列，或在 n＝150／250 時下架。閘門可能讓檢查點與退出期限在日曆上晚於 n 首次到達的日子才判定，延後有上限，而且會揭露。

#### 2-G　錄存規則

- 修訂紀錄新開一段：「N-23 checkpoint 批（乙案；D-11 第 2、3 點、D-11.4 第 2b 點與第 12 點 (ii)、Consequences、FL-71 (i)、FL-54 (e)；方向：補定義（兩面））」。
- 逐項記：方向、CEO、風控出處。
- 被取代的原文：
  - 2-B 的三處，逐字錄存；
  - 2-D 的兩處，正文已有〔取代〕，修訂紀錄寫「已逐字錄存於正文〔取代〕，本段不重錄」。
- 放寬面的原文附在方向欄。不得只標收緊（風控第四節 tech-writer 第 7 點）。

#### 2-H　甲案字面（依指示附上；我不建議採用）

甲案 ＝ 2-A～2-C，套用下列差異：

1. 2-A「延後判定規則」的觸發條件，改為只有 `delayed`（拿掉「與 `prefix_changed` 都為真」）。刪去「`delayed` 為真、`prefix_changed` 為假…照常認列」一句。
2. 刪去 `prefix_changed`、`prefix_change_kinds`、`phase0_grid_sha256` 與 `checkpoint_prefix_changed`。§4.2 的列舉也同步刪去。
3. 保留：P_j、閘門、n_complete、`delay_kinds`（含 `multi_due`，也就是 Q-f 第 (iii) 項）、【α】、LM-74 一句。
4. 2-D 不套用：seed 照日期。2-C 第 (12) 格改為「同一 session 的 daily 列與 checkpoint 列 seed 相同」。
5. 2-C 刪去第 (1)、(3)、(7)、(8) 格；第 (2) 格改為「略過 → 正面結果不認列」。
6. Consequences 再加一句甲案的殘餘：
   > 延後擷取資料會移動判定日，進而移動 seed，而且不會被標成延後（quant 2026-10-18 Q-d 甲案）。

**甲案仍有 G-1**，要不要加 α 和乙案一樣，都要裁定。

---

### 3. N-39：區間、n、期間出自同一列

**查證**：
- 【事實】`required_disclosures` 規定「優於基準」時要附「D-4 的區間、n、期間」（D-11.4 第 2b 點）。
- 【事實】`validation_status` 與 `display_state`「取自同一列 T 日 snapshot」（D-11.4 第 6 點 S1；FL-54 (e)）。
- 【事實】全檔沒有規定，同一 T 同時有 daily 列與 checkpoint 列時，「T 日 snapshot」指哪一列；三個值取自哪裡也沒有規定。grep「區間」只命中第 2b 點與 FL-52 (e)。
- 【推論】更早就存在的漏洞：D-11 第 3 點規定 daily 列「只能維持或降級」，但沒有規定同一 T 的 daily 列要以 checkpoint 列的結果為起點。照字面，checkpoint 列的升級不會反映在 daily 列上。

**N39-1**：D-11.4 第 2b 點。定位字串（唯一）：`「優於基準」時另加 D-2 的開盤基準句，以及 D-4 的區間、n、期間。`，在句末接：

> （N-23 Q3；風控 2026-10-19 N-39）D-4 的區間、n、期間，與同一回應中的 `validation_status`、`display_state`，出自同一列 snapshot：該 claim `computed_for_session = T`、`eval_kind = 'daily'` 的那一列（下稱 T 日 snapshot）。
> - 區間依事先宣告 §4.10 D-4 的定義，取該列 `stats_json` 所記的值；n 取該列的 `n` 欄位；期間取該列 `stats_json` 所記的樣本首末決策日（`sample_first_session`、`sample_last_session`，鍵名暫定，本批新增，由寫入函式自行填入）。
> - 這三個值與狀態，由 `views.outlook_view` 的同一次 snapshot 讀取一起帶出（`OutlookView` 加 `validation_disclosure = {computed_for_session, interval, n, period_start, period_end}`，名稱暫定）。前端、API、plan、匯出不得另讀 snapshot，也不得以 checkpoint 列或其他日期的列的值代入或混用。
> - checkpoint 列只供 D-12、§4.2、稽核與 quant 的檢查點檢討紀錄讀取，任何顯示面都不讀（AST 列舉呼叫點）。
> - 延後判定時，檢查點當天 daily 列的 n 可能大於 `checkpoint_n`。這時畫面上的 n 是 daily 列的 n，不得改寫成 `checkpoint_n`。

**N39-2**：D-11 第 3 點。定位字串（唯一）：``3. **升降規則**：只有 `checkpoint` 列可以把狀態升為 `better_than_baseline`；`daily` 列只能維持或降級。``，在句末接：

> （N-23 Q3；N-39）同一 claim、同一 T 有 checkpoint 列時，checkpoint 列先計算。同一 T 的 daily 列，以該 checkpoint 列寫入後的有效狀態與 `display_state`（含 `display_reasons_json.withdraw`）為「維持或降級」的起點，再以 daily 列自己的樣本，依事先宣告 §4.5「每天重算」判定當天是否降級；沒有 checkpoint 列時，以前一筆 daily 列為起點。所以檢查點的升級或下架在同一 T 的 daily 列生效；daily 列的樣本較大、沒有通過時，當天就降級。〔推論：與事先宣告 §4.5「最近一個檢查點通過 §4.3，而且之後沒有觸發當日降級」一致；同一 T 的順序請 quant 在 v0.22 確認〕

**N39-3**：FL-54 (e)。定位字串（唯一）：`（`outlook_view` 只讀一次 snapshot 列）；`，在其後接：

> （N-39）同一 T 有 checkpoint 列（n＝30、升級）與 daily 列（n＝35）→ 回應的 `validation_status`、`display_state`、區間、n＝35、期間都等於 daily 列，checkpoint 列被讀 0 次（spy）。daily 列在 n＝35 的樣本上沒有通過 → 當天顯示降級後的狀態，不出現「優於基準」。`views`、`app/plan/**`、`app/api/**` 讀 checkpoint 列的地方是 0 處（AST）。

錄存：無被取代原文。方向：補定義（收緊）；CEO：否；風控 required。

---

### 4. N-20 批：範圍說明與 ADR-0027 字面

#### 4-A　後續追蹤清單 N-20 列

在現有各括號之後，接上新括號：

> 〔2026-10-19 tech-architect 依風控第二節 C 改寫範圍：
> - 刪去「`recorded_at` 只增不改」前提，改為「不改寫（append-only trigger，屬自律層級）；不單調、不唯一；只以原字串相等比對，不解析、不比較大小、不作為鍵」；
> - 身分 ＝ `{recorded_at, kind, session_date}`（採風控 suggested 1）；主 DB 存成 `forecast_settle_eval.market_run_max_identity_json`、`forecast_correction_job.market_scan_to_identity_json`、`forecast_gap_audit.market_run_current_identity_json`；
> - 參考候選加 `forecast_gap_audit.market_run_current` 的歷史最大值（採風控 suggested 2）；
> - 守衛函式在同一個市場 DB 唯讀交易內，讀出 `MAX(run_id)`、它的身分與各候選 run 的身分；空的市場 DB 以 0 計；
> - 以 ADR-0026 D-9 第 2-1 點為前提，身分比對的程式不得早於該點落檔；
> - 殘餘漏報【推論】；
> - (1c)、FL-67 (n)、(1e)、D-9.2「處理終點」、ADR-0029 E-2（失效條件 5）同批改寫；
> - 字面見 `work/reviews/` 本份 TA 回覆第二節 4〕

#### 4-B　ADR-0027 字面

**N20-1　D-7 第 2 點「還原疑似時的共同守衛」**

定位：L797 子點內，從 ``` `market_run_regression(r_now, *, store) -> MarketRunRegression | None` ``` 起，到「參考值依 D-9.2「R 倒退」的定義，以一次主 DB 唯讀查詢取得。」（唯一）為止，整段換成下文。同一子點後段「回傳的 `MarketRunRegression` 是 frozen 型別，屬性為…逐字一致；」也換成下文最後一項。

> `market_run_regression(*, store, market_reader) -> MarketRunCheck`，是 `app/forecast/` 內的單一函式，名稱暫定。它依序做兩次讀取，之後不再讀：
> - (1) 以一次主 DB 唯讀查詢，取得參考候選（D-9.2「R 倒退」）與各候選存下的 run 身分；
> - (2) 經 `MarketPanelReader.read_run_head(run_ids)`（`market_panel.py` 內的單一唯讀方法，名稱暫定），在同一個市場 DB 唯讀交易內，讀出 `MAX(run_id)`、該 run 的身分，以及各候選 `run_id` 在市場 DB 中的身分（不存在時為 None）。
>
> r_now ＝ 這一次讀到的 `MAX(run_id)`。呼叫端不傳入 r_now、參考值或身分。（N-23 Q7；風控 2026-10-19）市場 DB 沒有任何 run（`MAX(run_id)` 為 null）時，r_now 以 0 計，身分為 None；參考值大於 0 時守衛因此成立，不得因 null 無法比較而略過判定（fail-closed）。
> - （N-20；data-engineer 2026-10-18 查證；風控 2026-10-19 R-Q7-5 丙案）**run 身分**：`{recorded_at, kind, session_date}`，取市場 DB `pit_snapshot_runs` 該列的原值。市場 DB 的 run 不改寫：靠 append-only trigger，屬自律層級，有檔案存取權的人可以 DROP trigger。`recorded_at` 不單調、也不唯一，所以身分只以原字串相等比對，不解析、不比較大小、不排序、不作為鍵；`session_date` 兩邊都是 null 時算相等。
> - **守衛成立**，若且唯若至少有一個參考候選 c（值為 v_c，存下的身分為 id_c）符合下列任一項：
>   - (a) r_now < v_c（`regression_kind = run_regressed`）；
>   - (b) v_c > 0、r_now ≥ v_c，而且市場 DB 中 `run_id = v_c` 的列不存在，或它的身分與 id_c 有任一欄不相等（`regression_kind = reference_identity_mismatch`）。
>
>   v_c ＝ 0 的候選沒有參考 run，不適用 (b)，不算不符。成立的候選有多個時，回報 v_c 最大的一個；同值時依 `settle_eval` → `correction_job` → `gap_audit` 取第一個；該候選 (a) 成立時記 `run_regressed`，否則記 `reference_identity_mismatch`。
> - 本點在 D-9 程式實作前落檔，所以不存在身分為 null 的候選列。若晚於 D-9 程式落地，既有列的身分以 null 遷移（D-2 第 5 點），這類候選只適用 (a)。這屬於放寬，屆時另送風控。
> - **前提**（風控 2026-10-19）：身分比對以 ADR-0026 D-9 第 2-1 點（先主 DB、後市場 DB 的備份順序，以及 manifest 檢查）為前提；該點落檔之前不得實作 (b)。解除路徑只有一條：用 manifest 檢查通過的備份組整組重做（ADR-0026 D-9 第 4 點），或修訂本點。不得新增解除用的 CLI、狀態或旗標。
> - **殘餘**〔推論〕：
>   - 兩條時間線的同號 run，身分三欄全部相同時會漏報。這要同一 kind、同一 `session_date`、同一微秒寫入，實務上只會出現在固定 clock 的測試環境。
>   - 還原時遺失、而且主 DB 從未引用過的 run，本守衛偵測不到。主 DB 沒有讀過它們，帳內也沒有依賴它們的列。
> - 回傳 `MarketRunCheck{market_run_current, market_run_current_identity, regression: MarketRunRegression | None}`（frozen）。
>   - `MarketRunRegression` 的屬性為：`market_run_current`（＝ r_now）、`regression_kind ∈ {run_regressed, reference_identity_mismatch}`、`reference_kind ∈ {settle_eval, correction_job, gap_audit}`、`reference_value`、`reference_id`、`reference_started_at`、`reference_recorded_at`、`current_recorded_at`。
>   - `current_recorded_at` 是市場 DB 中 `run_id = reference_value` 那一列的 `recorded_at`，不存在時為 None。
>   - 屬性名稱與 D-9.2「R 倒退」的例外屬性、ADR-0029 E-2 逐字一致。
>
> 〔N-20 取代：原寫「…」〕（tech-writer 逐字引入被換掉的兩段原文）

**N20-2　D-9.2**

- **①**：定位字串（唯一）`① 讀 R。之後不再讀市場 DB 的 `MAX(run_id)`。`，換成：
  > ① 經 D-7 第 2 點 `market_run_regression()` 讀 R（R ＝ 回傳的 `market_run_current`；R 的身分寫入 `forecast_settle_eval.market_run_max_identity_json`）。之後不再讀市場 DB 的 `MAX(run_id)`。〔N-20 取代：原寫「① 讀 R。之後不再讀市場 DB 的 `MAX(run_id)`。」〕
- **R 倒退首句**：定位字串（唯一）`R 小於參考值時，視為市場 DB 被還原`，換成：
  > ① 的回傳中守衛成立時（R 小於參考值，或參考 run 的身分不符，D-7 第 2 點），視為市場 DB 被還原
- **參考值一句**：定位字串（唯一）`參考值 ＝ 最後一列 `forecast_settle_eval.market_run_max`` 所在那一句，整句換成：
  > 參考候選（N-20）：(i) 最後一列 `forecast_settle_eval` 的 `market_run_max` 與 `market_run_max_identity_json`；(ii) 最近一個已有 `forecast_correction_job_end` 的作業的 `market_scan_to` 與 `market_scan_to_identity_json`；(iii) `forecast_gap_audit` 中 `market_run_current` 最大的一列（同值時取 `audit_id` 最大者）的 `market_run_current` 與 `market_run_current_identity_json`。沒有列的一方不計；三方都沒有時，沒有參考值，不檢查。「參考值」指 D-7 第 2 點所回報的那一個候選的值。〔N-20 取代：原句〕
- **定位字串**（唯一）`參考值以一次主 DB 唯讀查詢取得，不讀市場 DB`，所在那一句換成：
  > 參考候選以一次主 DB 唯讀查詢取得；R 與各候選的現行身分，在同一個市場 DB 唯讀交易內讀出（D-7 第 2 點），所以不違反 ①「之後不再讀市場 DB 的 `MAX(run_id)`」。〔N-20 取代〕
- **例外屬性**：定位字串（唯一）``例外屬性（關鍵字必填）：`source`（恆為 `settlement`）``，同一句：
  - 加入 `regression_kind`、`reference_recorded_at`、`current_recorded_at`；
  - `reference_kind` 加 `gap_audit`；
  - `reference_id` 加「或 `audit_id`」；
  - `reference_started_at` 加「（gap_audit 時為 `audit_now`）」。
- **處理終點**：定位字串（唯一）`處理終點不變：直到 devops-sre 依 ADR-0026 D-9.4 處理並修訂本點`，整個子點換成：
  > 處理終點：直到 devops-sre 依 ADR-0026 D-9 第 4 點處理並修訂本點（比照 D-3「晚到資料的觸發」第 8 點）。本判定不存跨執行狀態，但不會因為新寫入的 run 而解除：（N-20）R 再度不小於參考值之後，參考 run 的身分仍要相符，本判定才不再成立。
  > - 市場 DB 單獨被還原時，主 DB 引用的 run 不是不存在，就是與還原後重號的新 run 身分不同，所以本判定持續成立，結算評估持續不寫入（fail-closed）。
  > - 依 ADR-0026 D-9 第 4 點、以 manifest 檢查通過的備份組整組還原時，主 DB 的參考值與身分一起回到備份，身分相符，本判定自行解除，不需要人工解除。
  > - 解除路徑只有這一條，或修訂本點；不得以手動改寫 DB、刪除參考列或關閉守衛代替（ADR-0026 D-9 第 4 點）。
  > - 被還原期間遺失的 run 不會因此回來〔推論〕；殘餘的漏報見 D-7 第 2 點。
  >
  > 〔N-20 取代：原寫「…」〕（逐字引入現行整個子點）

**N20-3　D-3 `forecast_settle_eval`**

定位字串（唯一）``- `market_run_max INTEGER NOT NULL`（R）；``，在其後插入：

> - （N-20）`market_run_max_identity_json`：R 那一列 run 的身分（D-7 第 2 點），與 R 取自同一次 `market_run_regression()` 的回傳值。R ＝ 0 時為 null，R > 0 時必須非 null（寫入驗證）；

**N20-4　D-3 `forecast_correction_job`**

定位字串（唯一）``寫入驗證（不成立就拒絕寫入）：`market_scan_from` 等於上述 W；`market_scan_from ≤ market_scan_to`。``，在該子點之後、同一層插入：

> - （N-20）`market_scan_to_identity_json`：`market_scan_to` 那一列 run 的身分，作業開始時與 `triggers_json` 同一個交易寫入。
>   - `market_scan_to` 取自掃描的 `run_max` 時，身分取自同一次 `market_run_regression()` 回傳的 `market_run_current_identity`；
>   - 還原保護（第 8 點）成立、`market_scan_to` ＝ W 時，照抄前一個已完成作業的值；
>   - `market_scan_to` ＝ 0 時為 null。
>   - 寫入驗證：值 > 0 ⇒ 非 null；照抄的情形，與所抄的值逐位相同。

另外，「晚到資料的觸發」第 2 點，定位字串（唯一）``先取一次 `run_max = MAX(run_id)` ``，改為：

> 先經 D-7 第 2 點 `market_run_regression()` 取一次 `run_max`（＝ 回傳的 `market_run_current`）〔N-20 取代：原寫「先取一次 `run_max = MAX(run_id)`」〕

**N20-5　D-3 `forecast_gap_audit`**

- `market_run_current` 那一行之後插入：
  > - （N-20）`market_run_current_identity_json`：`market_run_current` 那一列 run 的身分，取自同一次 `market_run_regression()` 的回傳值。`market_run_current` ＝ 0 時為 null，> 0 時必須非 null；
- (1a) 第二欄，定位字串（唯一）``成立時為 `{reference_kind, reference_value, reference_id, reference_started_at}` ``，改為：
  > 成立時為 `{regression_kind, reference_kind, reference_value, reference_id, reference_started_at, reference_identity, current_identity}`（`reference_identity` 是該候選存下的身分；`current_identity` 是市場 DB 中 `run_id = reference_value` 那一列的現行身分，不存在時為 null）
- (1b) 句末「所以守衛期間每一次成功的稽核都留下一列。」之後接：
  > `market_run_current_identity_json` 同。

**N20-6　(1c)**

定位：L657 那一子點，以字串 `在本交易內依 D-9.2「R 倒退」的參考值定義重算一次` 定位，整個子點換成：

> - （N-23 Q7；N-20）在本交易內以一次主 DB 查詢重讀參考候選，連同本次 `market_run_regression()` 回傳的市場 DB 讀值（`market_run_current`、它的身分，以及各候選 run 的現行身分；由稽核函式持有，不接受呼叫端傳入），依 D-7 第 2 點的守衛定義重算一次：`market_run_regression_json` 非 null，若且唯若重算的守衛成立；非 null 時各鍵等於重算的值。所以 `market_run_current ≥ reference_value` 而 json 非 null 是合法的（`regression_kind = reference_identity_mismatch`）；〔N-20 取代：原寫「…」〕

**N20-7　FL-67 (n)**（L2373，定位字串全部唯一）

- ``鍵恰為 `reference_kind`、`reference_value`、`reference_id`、`reference_started_at` `` → 改成 N20-5 的七個鍵。
- 「參考值取自 `forecast_settle_eval`、取自更正作業各一格」→ 句末加「、取自 `forecast_gap_audit` 歷史最大值一格」。
- 從「寫入驗證四種拒絕各一格：」起，到「…而 `market_run_current` 小於重算的參考值；」止，換成：
  > 寫入驗證四種拒絕各一格：json 非 null 而本交易寫入了 `unobserved_weekday` 事件、json 非 null 而交易內重算的守衛不成立、json 各鍵與交易內重算不符、json 為 null 而交易內重算的守衛成立；
  > （N-20）身分格：
  > (i) 參考 run 存在、`market_run_current ≥ reference_value`、`recorded_at` 原字串不同 → 非 null，`regression_kind = reference_identity_mismatch`，沒有新的 `unobserved_weekday` 列；
  > (ii) `recorded_at` 相同而 `kind` 不同、`session_date` 不同，各一格 → 同上；
  > (iii) 同一時刻的兩種字串形式（`…T14:10:00+00:00` 與 `…T14:10:00.000000+00:00`）→ 視為不同；
  > (iv) 參考 run 不存在、而 r_now ≥ 參考值 → 成立，`current_identity` 為 null；
  > (v) 兩個候選同值、只有一個身分不符 → 成立，回報依 D-7 第 2 點的取法；
  > (vi) 參考值為 0 → 不比對身分；
  > (vii) 還原後重號：用假 clock 與 scratch 空 DB（流程同 data-engineer 2026-10-18 的實測）。市場 DB 單獨換回備份、再寫 run 使 r_now ≥ 參考值 → 成立，之後再寫任意多個 run 仍成立；主 DB 也換回同一組備份 → 不成立；
  > (viii) 備份順序顛倒的組（主 DB 引用了市場 DB 備份沒有的 run）→ 整組還原後守衛成立；
  > (ix) `read_run_head` 在一個唯讀交易內完成（spy：開始一次、結束一次，中間沒有其他交易）；`market_run_regression` 的簽章沒有 r_now、參考值或身分參數（AST）。
  >
  > 〔N-20 取代：原寫「…」〕

**FL-71 (e)**：定位字串（唯一）``市場 DB 沒有任何 run、參考值大於 0 → 拋 `MarketRunRegressedError`，`market_run_current = 0`。``，在句末接：

> （N-20）參考 run 身分不符、R ≥ 參考值 → 同樣在 ② 之前拋出，`regression_kind = reference_identity_mismatch`。`forecast_settle_eval.market_run_max_identity_json` 等於同一次讀取的身分。

**N20-8　(1e)（第二批，CEO #42）**

- **如果 (1e) 尚未落檔**：(1e) 以下列版本落檔：
  - `market_run_now` 改名為 `market_run_current`（風控 A 段）；
  - 揭露欄位清單加 `regression_kind`；
  - 把「共同守衛不存跨執行狀態，市場 DB 還原後新寫入的 run 使 r_now 再度不小於參考值之後，稽核列回到 null，被還原期間遺失的 run 不會因此回來；還原後新寫入、`run_id` 不大於 W 的 run，之後也不會被掃到〔推論：還原後 `run_id` 由還原檔的序號接續〕。」換成：
    > （N-20）共同守衛不存跨執行狀態，但只有參考 run 的身分相符時才解除（D-7 第 2 點）：市場 DB 單獨被還原時，稽核列持續非 null，直到依 ADR-0026 D-9 第 4 點整組還原，或修訂本點。被還原期間遺失的 run 不會因此回來；還原後新寫入、`run_id` 不大於 W 的 run，之後也不會被掃到〔推論：還原後 `run_id` 由還原檔的序號接續；data-engineer 2026-10-18 以 `Connection.backup` 實測支持，完整還原程序（含 WAL）未驗證〕。
- **如果 (1e) 已先落檔**：以上一句的舊字為定位，換成新句，並附〔N-20 取代〕。
- CEO 不同意 #42、改用備用句時：備用句不含解除的敘述，不必改。

**N20-9　ADR-0029（proposed，原地修訂；依失效條件 5 送風控知悉）**

- D-7 事件目錄 E-2 的 payload 欄位：
  - 加 `regression_kind`、`reference_recorded_at`、`current_recorded_at`；
  - `reference_kind ∈ {settle_eval, correction_job, gap_audit}`；
  - `reference_id` 加 `audit_id`；
  - `reference_started_at` 加 `audit_now`。
- L219 的屬性清單同步。
- L220 那一句（「…若在 ADR-0027 增列 E-2 的屬性…」）換成已完成的敘述。
- Consequences 的「**E-2 停止出現，不代表已處理**」：把「新寫入的 run 使 R 再度不小於參考值時，判定就不再成立，結算評估恢復執行；」改為：
  > 新寫入的 run 不會使判定解除；只有參考 run 的身分相符（例如依 ADR-0026 D-9 第 4 點整組還原）時才解除（ADR-0027 N-20）；
- 部署手冊待補項第 4 點：「說明守衛會自己解除」改為「說明守衛只在參考 run 身分相符時解除」。
- OA-10 加身分不符一格。
- render 的三個新標籤常數送風控知悉。
- 舊字依該 ADR 的慣例逐字保留。

**N20-10　ADR-0026（devops-sre 平行稿，要對齊）**

- (b)、(c) 的身分改為三欄：
- 參考 run 的取法加上 gap_audit 候選；
- 「兩者相等」一句擴為三方；
- 欄位名用上述三個 `*_identity_json`。

這幾點與 N-20 同批送風控。

#### 4-C　兩個 suggested 的回答

1. **比對 `kind`／`session_date`：採用。**
   - 兩欄都受 trigger 保護、不改寫，同一時間線內不會誤報，只會更嚴。
   - 主 DB 端存成一個 JSON 身分欄，取代原案的單一 `recorded_at` 欄，所以欄數不變；市場 DB 也沒有 schema 變動。
   - 代價：ADR-0026 的 manifest 檢查要比對同樣的三欄。
2. **把 `market_run_current` 的歷史最大值納入參考值：採用。**
   - 理由【推論】：結算評估連日失敗時（例如 E-1），`forecast_settle_eval` 的參考值會停住；缺日稽核依步驟隔離照常執行。
   - 這段期間若市場 DB 被單獨還原到參考值之後的某一點，原本的兩方候選都偵測不到。
   - 缺日稽核卻可能依縮小的觀察日集合，做出永久的未觀察平日登記。
   - 用最大值、不用最後一列，是因為守衛成立時稽核照常寫列，`market_run_current` 不單調。
   - 代價：多一個 JSON 欄、一個候選，還要改 ADR-0026 參考 run 的取法與 ADR-0029 的列舉。

### 對實作的約束（qa-reviewer 可以逐條檢查）

1. `checkpoints_due`、`checkpoint_sample`、`checkpoint_prefix_changed` 在 `app/` 內各恰好一個定義，只由驗證快照的寫入路徑呼叫；簽章不接受 n、n_complete、檢查點清單、樣本或判定結果（AST）。
2. partial UNIQUE `(claim_id, checkpoint_n) WHERE eval_kind='checkpoint'` 存在（`sqlite_master`）。
3. `checkpoint_timing` 的各鍵、daily 列的 `n_complete` 與 `phase0_grid_sha256`，都由寫入函式自行填入（AST：寫入函式的簽章沒有這些參數）。
4. `app/` 與 ADR 正文沒有 `snapshot_skipped`（grep）。
5. 任何顯示面都不讀 `eval_kind = 'checkpoint'` 的列；D-4 的三個值與 `validation_status` 出自 `outlook_view` 的同一次讀取（AST、spy）。
6. 沒有任何以操作者指定的 claim、n_j 或日期，寫入、延後或重判 checkpoint 的 CLI、API 或參數。
7. `market_run_regression` 在 `app/forecast/` 內恰好一個定義；簽章沒有 r_now、參考值或身分參數。`read_run_head` 是 `market_panel.py` 內唯一讀身分的方法，在一個唯讀交易內完成（AST、spy）。
8. 身分比對只用 SQL 的 `=` 或 Python 的 `==` 比原字串；`recorded_at` 不出現在 `ORDER BY`、`<`、`>`、`datetime.fromisoformat` 的呼叫裡（AST／grep）。
9. 禁止：解除守衛用的 CLI、狀態表、旗標；手動解除的程式路徑。
10. ADR-0026 D-9 第 2-1 點落檔之前，(b) 身分比對不得合併進主幹（PR 檢查）。

---

## 三、驗證

**讀過的檔案**：
- 風控 2026-10-19 裁定全文；quant 2026-10-18 回覆全文；data-engineer 2026-10-18 查證全文；我的 2026-10-18 補充項回覆全文；
- ADR-0029 的 D-2、D-7、失效條件、Consequences 相關段落；ADR-0026 D-9（工作樹，含 devops-sre 的 2-1 點稿）；
- 後續追蹤清單 N-20、N-34、N-38～N-40 各列；`回報格式.md`。

**ADR-0027 工作樹讀過的段落**（行號是本次讀取當下的值，期間漂移約 4 行）：
- L275～L474（D-3 `forecast_record`、`forecast_outcome`、更正作業、晚到觸發、`forecast_settle_eval`）；
- L640～L664（`forecast_gap_audit`，第一批已套用）；
- L797～L805（D-7 第 2 點）；
- L1060～L1119（D-9 第 1～3 點）；
- L1196～L1225（D-9 第 5 點待重算）；
- L1262～L1331（D-11 第 1～4 點）；
- L1350～L1361、L1395～L1434（D-11.4 第 2、6 點）；
- L1687～L1694（(g) 待重算片段）；
- L1805～L1829（第 12 點）；
- L1893～L1934（D-12）；
- L2373（FL-67 (n)）、L2408～L2456（FL-71）、L2660～L2671（FL-54）。

**事先宣告讀過的段落**：L945、L1044～L1066、L1469～L1471、L1575，以及 grep 命中的各行。

**定位字串**：本文用到的每一個定位字串都用 Grep 驗過唯一，下列除外：
- `UNIQUE(claim_id, computed_for_session, eval_kind)`； 有 2 處，所以改用 `bootstrap_seeds_json` 那一行定位；
- 「同一個檢查點兩個原因同時成立時…」有 2 處，只改 L1817。

**現況**：
- N-23 補充項第一批已經套用（修訂紀錄 L4487 一帶的段落標題；`market_run_current`、D-7 第 2 點的 null 一句、FL-71 (e) 的空市場 DB 格都在）；
- checkpoint 批與 N-20 都還沒套用；
- `work/reviews/` 已有 6 份 2026-10-19 的檔案。

**未查證**：
- 證據不足的紀錄在 σ_d 缺漏時，`threshold_snapshot` 實際是否存在（G-2）；
- 第 0 相位格點雜湊的實際大小；
- `pit_snapshot_runs` 的序號是否真的沒有洞（第 (iv) 格靠 fixture 構造）；
- WAL 還原程序（N-40）；
- 各延後上限的實際長度（都是推論）。

**請 CEO 親自確認**：不需要操作。只需要知悉三件事：成本句（第二節 2-F）、G-1 的處理方向，以及延後判定的殘餘仍由您負最終責任。

---

## 四、下一步

### checkpoint 批（照改清單）

1. **風控**：
   - 裁定 G-1 補法 α（或 β、γ，或其他）；
   - 逐字確認 2-A～2-E 與 N39-1～N39-3；
   - 確認 Consequences 加的那一句 α 但書；
   - 裁定甲案差異清單（2-H）是否仍需要。
2. **quant**：
   - 把 α 寫進 v0.22 第 2 點（建議句：「最近一個已完成作業的 `pending_json` 中 `reason = write_validation_failed` 的項，不適用 N-29 (b) 期限；閘門不等待它：計算 U 時視同終局，但不計入 n、不屬於 P_j，該檢查點視為延後判定、而且前綴有變動」）；
   - 把第 2 點那句改為：
     > 證據不足與作廢的紀錄，outcome 列寫入之後即為終局；其中 resolved 的列與其他 resolved 列一樣，列入待重算（§6.3 N-29 (b)）期間不是終局。
   - 第 4 點的「例如 X2 確認、未觀察平日登記」改引 ADR-0027 D-11 第 2 點的封閉列舉；
   - 確認 N39-2 同一 T 的計算順序；
   - 定義 G-2：證據不足的紀錄在 `threshold_snapshot` 缺項時，`realized_*` 怎麼算；
   - LG-33 對照 2-C 的 15 格。
3. **tech-writer**：風控確認之後，2-A～2-E、N39-1～N39-3 與 v0.22 同一批落檔。依 2-G 錄存。2-B、2-D 都附被取代原文。
4. **coordinator（機械核對）**：
   - `snapshot_skipped` 0 筆；
   - `checkpoints_due` 定義 1 處；
   - 沒有 `checkpoint_delayed` 的 `cause ∈ {suspended_f3, db_restored}`，只剩修訂紀錄的引文；
   - seed 脈絡中的「ISO 日期」只剩〔取代〕引文；
   - 追蹤清單 N-38 註記「G-1 不成立，待 α 裁定」，N-39 註記「已提字面」；
   - 新增追蹤項 G-2（擋 D-9）。

### N-20 批（照改清單）

1. **devops-sre**：ADR-0026 的 2-1 點依 N20-10 對齊（身分三欄、參考候選三方、欄位名）。N-40 的 WAL 驗證結果回報。
2. **風控**：N20-1～N20-9 與 ADR-0026 修訂同批確認；ADR-0029 依失效條件 5 知悉。
3. **tech-writer**：N20-1～N20-7 與 N20-9 同批落檔，附〔N-20 取代〕並逐字錄存原文。N20-8 依 CEO #42 的結果與 (1e) 的落檔順序擇一。
4. **dev-lead／data-engineer**：`MarketPanelReader.read_run_head` 放在 `market_panel.py`。在 ADR-0026 2-1 落檔之前，不實作 (b)。
5. **coordinator**：
   - N-20 列換上 4-A 的括號；
   - 機械核對：`market_run_max_recorded_at`、`market_scan_to_recorded_at` 都是 0 筆（改用 `*_identity_json`）；
   - ADR-0029 內沒有「新寫入的 run 使 R 再度不小於參考值時，判定就不再成立」。

**相關檔案**：
- /home/user/AICompany/docs/adr/0027-stock-desk-預測紀錄帳-儲存-PIT輸入-排程與定義登記.md
- /home/user/AICompany/docs/adr/0026-stock-desk-庫存版本化軟刪除與還原點.md
- /home/user/AICompany/docs/adr/0029-stock-desk-維運告警通道.md
- /home/user/AICompany/work/research/2026-10-15-3日5日方向判斷-事先宣告草案.md
- /home/user/AICompany/work/reviews/2026-10-19-N23補充項與checkpoint乙案裁定-風控.md
- /home/user/AICompany/work/reviews/2026-10-18-checkpoint略過Qa至Qf回覆-quant.md
- /home/user/AICompany/work/reviews/2026-10-18-N20市場DBrun身分查證-data-engineer.md
- /home/user/AICompany/work/reviews/2026-10-18-N23風控補充項回覆-tech-architect.md
- /home/user/AICompany/work/reviews/2026-10-19-ADR0026備份順序與manifest檢查修訂-devops-sre.md
- /home/user/AICompany/work/dispatch/2026-10-17-後續追蹤清單.md

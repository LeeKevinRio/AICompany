# N-64、N-66 缺日原因判定缺口落字起草

- 審查者：tech-architect
- 日期：2026-10-23
- 轉存：coordinator，逐字轉存 subagent 最終回報

---

## 本次結論

1. 我起草了 N-64、N-66 的修補字面，共 11 段可落檔，另有 4 段表數同步。全程只用 Read、Grep、Glob，沒有改任何檔。可落檔的 11 段如下：
   - N-64：A-1～A-5
   - N-66：B-1～B-5
   - 共用：A-2 的判定順序裡也含 N-66 的第 4、5 項
   - 表數同步：C-1～C-4，和 v0.26 有衝突（見下方衝突點）
   - 9 個插入點都用 Grep 在 ADR-0027 確認過，各出現 1 次。
2. **N-64 採甲案**，三部分：
   - **列集合**：取全部 S 的 run 的範圍快照聯集。
   - **`reason`**：在範圍快照含該範圍的 run 中，取 `run_id` 最大的那個（決定 run）來判定。
   - **判定順序**：`db_restored` → `late_only` → 決定 run → 決定嘗試 → `scheduler_down`。被蓋過的原因存在新欄 `forecast_gaps.basis_json`。
   - 否決或列為備選的方案：取最後一個 run 而不看快照、嚴重度優先序（備選）、「任一 run 已寫入就不是缺日」的日層級擴充讀法、取第一個 run（備選）、每個 run 各寫一列。
   - 這個取法和 D-3 `plan_coverage_log` L759 處理同一 T 多次作業的方式相同：應有集合取聯集，原因取含該標的的最後一次作業。
3. **N-66 採 A 案**：
   - 新增兩張表 `forecast_record_attempt`／`forecast_record_attempt_end`，和 `forecast_run`／`forecast_run_end` 同型。
   - 新增原因值 `record_start_failed`，列舉從八值變九值。
   - 〔事實〕查證時多發現一個同源缺口：`inputs_not_ready` 在 ADR-0027 沒有任何存放處。依據有三：
     - D-7 第 2 點 Q4 寫「本次執行沒有 T」；
     - L910 的 `detected_by_run_id` 寫「未寫入 `forecast_run` 時為 null」；
     - L723 的 `forecast_ledger_events.kind` 列舉裡沒有這個值。
   - 〔推論〕照現行字面，`inputs_not_ready` 的缺日會落到 `scheduler_down`，FL-63 的期望值稽核做不到。A 案一併修掉。
4. **和 ADR-0029 的關係**：字面不用改，失效條件 1、5 都不觸發。前置段失敗本來就會發 E-3d（`step = record`）；N-64 的帳目矛盾走現有的 E-3d（`step = gap_audit`）。新表與 `basis_json` 明文禁止告警讀取，也不拿來做跨執行判斷。
5. **CEO 層級**：整批是知悉，原因是表數加 2，以及帳目矛盾時稽核會停擺。有一個條件式放寬點：A-2 第 2 項「`late_only` 先於 run 的原因」。我判斷它和 FL-67 (h) 一致，方向是不變；風控如果認定原字面有「run 原因優先」的讀法，這項就是放寬（TG-c 計數會變少），要 CEO **明確同意**。
6. **和 v0.26 TA 的衝突點**：
   - D-3 `forecast_replay`／`forecast_replay_outcome`、D-4 第 3 點、D-9 第 7 點、FL-7、FL-69 都沒有動。
   - **非動不可的衝突**有兩處：
     - 表數，在 L89、L202 M-11、L2306。quant v0.26 草案第二節第 15 點可能為重放嘗試紀錄加一張表。
     - 待決事項 CEO 段的編號。v0.26 預定用第 18 項。
   - **需留意的**有三處：
     - A-3 的插入點 L693 緊接在 `forecast_replay_outcome` 區塊的末行 L692 之後，只是行位相鄰，語意不衝突；
     - FL-76 的編號；
     - 用詞相近：重放用「嘗試紀錄」，記錄一步用「記錄嘗試」。

---

## 各部門回報

### tech-architect

#### 〇、方案比較（〔事實〕〔推論〕分開標）

〔事實〕兩個 F-3 都不讀 `reason`：
- D-11 第 6 點的逾時率以排程紀錄中 `late=1` 的比例計，而且寫明「缺日不進分母」（L2093-2094）。
- 失效條件 F-3 是「連續 60 個觀察日的缺日率超過 30%」（L3045）。缺日率以列計還是以日計，我沒有查到（未查證）。

〔事實〕D-8 第 5 點：只有 `late_only` 會改變渲染（不渲染 TG-b），TG-c 的計數也不含它。

**N-64**

| 方案 | 對缺日列數 | 對 F-3 | 可操縱性 | 揭露 | 結論 |
|---|---|---|---|---|---|
| 甲：列集合取全部 S 的 run 快照聯集；`reason` 取快照含該範圍、`run_id` 最大的 run；`db_restored`、`late_only` 先判；沒有 run 時依記錄嘗試 | 列數不受 `reason` 規則影響；聯集使列數不少於「只取最後快照」的讀法 | 不讀 `reason`，所以不變；〔推論〕缺日率若以列計，聯集偏嚴 | 在首次判定 S 的稽核之前，可以再觸發一次 run（重開機觸發啟動補跑）來改 `reason`，但不能減列；把範圍移出自選也消不掉列；列寫入後只增不改，可操縱的時間窗以此為上限 | 被蓋過的原因留在 `basis_json`，事先宣告 §6.3 分列 | **採用** |
| 甲-2：取最後一個 run，不看快照 | 列集合如果也取最後快照，把範圍移出自選就能減列（放寬） | 缺日率可能偏低 | 高 | 同甲 | 否決 |
| 乙：依嚴重度取優先序 | 同甲 | 同甲 | 之後的 run 只能把原因升級，不能降級 | 同甲 | 備選。排序是主觀判斷，要另送風控；`reason` 不再對應任何一個 run 的最終狀態，和 `plan_coverage_log` 的取法不一致 |
| 丙：任一 run 已寫入就不是缺日 | 〔事實〕這已經是 D-8 第 2 點首句的存在性規則，本身不決定 `reason`，不能單獨成案；擴成日層級時，沒寫入的範圍的列會消失 | 擴充讀法會讓缺日率偏低（放寬） | 擴充讀法下，只要讓一個範圍寫入就能整日消掉 | — | 存在性規則保留；否決日層級擴充 |
| 丁：取第一個 run | 同甲 | 同甲 | 最低（之後的 run 改不了） | 同甲 | 備選。23:10 重試的實際結果被忽略，例如 22:10 逾時、23:10 拒寫時記成 `timeout`，蓋掉每次都會重演的拒寫 |
| 戊：每個 run 各寫一列 | 違反 `UNIQUE(session, claim_id, scope_key)`；列數隨重試次數增加 | 偏高，而且可以被灌高 | 高 | — | 否決 |

**N-66**

| 方案 | 優點 | 缺點／風險 | 結論 |
|---|---|---|---|
| A：記錄嘗試兩張表，加 `record_start_failed` | 原因分辨得出來；`inputs_not_ready` 有了存放處；和 run／run_end、FL-18 同型；不改 `forecast_run` | 表數加 2，和 v0.26 衝突；開始列本身寫不進去時仍記 `scheduler_down`（殘餘） | **採用** |
| A′：單表加 `entry_kind`（比照 `plan_coverage_log`） | 表數只加 1 | 欄位條件與寫入驗證比較複雜 | 備選（如果要壓低表數） |
| B：只新增原因值，不持久化 | 不加表 | 稽核沒有依據可分辨，只能看 log 或告警，違反「只依持久化紀錄判定」（D-8 第 2 點 N-51、N-52 子點） | 否決 |
| C：把 `forecast_run` 提前寫，`data_as_of` 可為 null | 不加表 | 要動 `forecast_run` 的定義、A-25、run_end 的寫入驗證（`scopes_done + scopes_missed` ＝ 快照數）、FL-18，以及所有以 `data_as_of` ＝ T 為前提的引用 | 否決 |
| D：維持現狀，只改揭露 | 成本最低 | `scheduler_down` 會誤導根因判斷（F-3 是升級給 devops-sre 的）；`inputs_not_ready` 仍然沒有存放處 | 否決 |
| E：用 E-3d 或 log 推定 | — | 違反上述原則；把告警持久化給稽核讀，會觸發 ADR-0029 失效條件 1 | 否決 |
| 沿用 `record_error`，不新增值 | 列舉不變 | 混淆兩件事：「有 run」時以範圍為單位、「沒有 run」時寫 `'*'`；V25-05 的定義是「只依 `forecast_run_end`」，也得跟著改 | 否決 |

---

#### 一、落字：N-64

**A-1　D-8 第 2 點「有範圍快照時」一項（句末接字）**
- 插入點：`有範圍快照時，逐 scope 寫列；沒有快照（例如 scheduler 停機）時，寫 `scope_key='*'`。`（L1155，1 處）的句號之後
- 逐字：
```
（N-64；tech-architect 2026-10-23）同一觀察日 S 有多個 S 的 run（定義見上方 N-64、N-66 子點）時，「範圍快照」指全部 S 的 run 的範圍快照的聯集，聯集中每一個沒有 `late=0` 排程紀錄的範圍各寫一列；不得只取最後一個 run 的快照，也不得因之後的 run 不含某個範圍而不寫該範圍的列。沒有任何 S 的 run 時（含只有記錄嘗試），寫 `scope_key='*'`。
```
- 方向：補定義（收緊：相對「只取最後快照」的讀法，列數不會變少，也排除了靠調整自選來消掉缺日列）。
- CEO：否。
- 被取代原文：無（句末接字）。

**A-2　D-8 第 2 點 `reason` 判定的 N-64、N-66 子點（插入）**
- 插入點：在 L1155（A-1 那一行）**之前**另起各行，接在 L1154（以 `` `reason` 的封閉列舉因此共八值 `` 起句的那一行）之後，縮排 5 格。
- 逐字：
```
     - （N-64、N-66；tech-architect 2026-10-23）**同一觀察日有多個 run 或記錄嘗試時的判定**（本子點優先於上方各項的排列順序；上方各項只描述單一 run 或單一嘗試的狀態）：
       - **S 的 run**：`trigger = scheduled`、`data_as_of = S` 的 `forecast_run`，取稽核交易內讀到的全部列；22:10、23:10 重試與啟動補跑寫入的都算，不論是否逾時。on-demand 的 run 不算。
       - **S 的記錄嘗試**：D-3 `forecast_record_attempt` 中符合下列任一項的列：(a) 它的 `forecast_record_attempt_end` 為 `outcome ∈ {inputs_not_ready, error_before_run}`，而且 `candidate_t = S`；(b) 沒有 end，或 end 為 `outcome = error_before_run` 而 `candidate_t` 為 null，而且 `started_at` ∈ [P 的 `late_cutoff_at`, S 的 `late_cutoff_at`)。P 是稽核所讀觀察日集合中早於 S 的最晚一日，不存在時不設下界；`late_cutoff_at` 以 D-7.4 的同一個函式計算。end 為 `outcome = run_written` 的嘗試不是記錄嘗試，依它寫入的 run 判定。
       - **缺日列存不存在不受本子點影響**：只依本點首句（沒有 `late=0` 的排程紀錄）；任一 run 已為該範圍寫入 `late=0` 紀錄，該範圍就沒有缺日列。列的集合依本點「有範圍快照時」一項的 N-64 句末。
       - **`reason` 依下列順序取第一個成立者**：
         1. S 落在 `db_restored` 標記的區間：`db_restored`；
         2. 該範圍只有 `late=1` 的排程紀錄：`late_only`；
         3. 有 S 的 run，其範圍快照含該範圍：取其中 `run_id` 最大的一個（決定 run），只依決定 run 判定：沒有 end → `job_error`；該範圍列在其 end 的 `refused_scopes_json` → `write_rejected`；其 end 的 `outcome = error` → `record_error`；`outcome = timeout` → `timeout`。決定 run 的 end 為 `ok` 或 `partial`、而該範圍不在 `refused_scopes_json` 時，屬帳目矛盾：稽核拋 `GapAuditRunInconsistencyError`（`app/forecast/errors.py`），整個稽核交易 rollback，不寫任何缺日列與 `forecast_gap_audit` 列，依 D-7 第 2 點記 WARNING，發 ADR-0029 E-3d（`step = gap_audit`）；不得改記其他值。claim 的 `registered_at` 晚於決定 run 的 `recorded_at` 時同樣適用本項；缺日義務從哪一日開始另案（見後續追蹤）；
         4. 沒有 S 的 run，而有 S 的記錄嘗試：取其中 `attempt_id` 最大的一個（決定嘗試）：end 為 `outcome = inputs_not_ready` → `inputs_not_ready`；沒有 end，或 `outcome = error_before_run` → `record_start_failed`；
         5. 以上都不成立：`scheduler_down`。
       - 同一個 run 內 `write_rejected` 先於 `timeout`、`record_error`（上方 N-51、N-52 一項）照舊，是第 3 項在決定 run 內的判定。
       - **只依持久化的紀錄判定**：`inputs_not_ready`、`record_start_failed` 只依 D-3 `forecast_record_attempt` 與 `forecast_record_attempt_end`；第 3 項只依 `forecast_run`、`forecast_scope_snapshot`、`forecast_run_end`。不得以 log、告警、`forecast_ledger_events`、`plan_coverage_log` 或 job 層事件推定。
       - **`forecast_gaps` 的參照欄**：第 3 項的列，`run_id` 填決定 run；第 4 項的列，`attempt_id` 填決定嘗試；其餘為 null。`basis_json` 依 D-3 `forecast_gaps` N-64 子點，列出該列也適用、但不是決定者的其他 S 的 run 與記錄嘗試。
       - 理由：取最後一個，使 `reason` 描述該範圍最後一次嘗試的結果，與 D-3 `plan_coverage_log`「衍生計數」中同一 T 多次作業的取法一致（應有集合取聯集；略過原因取含該標的的最後一次作業）。只在範圍快照含該範圍的 run 中取，之後一次不含該範圍的 run 就蓋不掉它的原因。`db_restored`、`late_only` 是區間與紀錄的事實，不依 run 判定，所以放在前面；`late_only` 先於 run 的原因，與 D-8 第 5 點的渲染及 FL-67 (h)「只有逾時紀錄 → `late_only`」一致。
       - 另一面（照實並陳）：之後的 run 可以改變一列的 `reason`（例如重開機觸發啟動補跑後再中止，使 `write_rejected` 變成 `record_error` 或 `job_error`），但改變不了列數；被蓋過的原因留在 `basis_json`，依事先宣告 §6.3「缺日」揭露。帳目矛盾時缺日稽核整次不寫，`gap_judged_through` 停止前進，驗證快照依 D-7 第 2 點的前置條件不寫，直到查明（比照 N-46 的停擺代價）。
```
- 方向：補定義（兩面）。
  - 收緊面：原因分辨得出來；帳目矛盾時 fail-closed；`db_restored` 先於 `late_only`，可能把原本是 `late_only` 的列移進 TG-c 計數。
  - 條件式放寬面：第 2 項 `late_only` 先於 run 的原因。我判為不變，理由是和 FL-67 (h)、D-8 第 5 點一致；風控如果判為放寬，就要 CEO 明確同意。
  - 多 run 時的值原本沒有定義，本項選定了一種，所以會動到現有的值。
- CEO：知悉（停擺代價）。第 2 項如果被判為放寬，要**明確同意**。
- 被取代原文：無（插入）。

**A-3　D-3 `forecast_gaps` 新增欄位（插入）**
- 插入點：含 `` `scope_key = '*'` 代表整個 claim。 `` 的那一行（L693，1 處）**之後**，縮排 2 格。
- 逐字：
```
  - （N-64、N-66；tech-architect 2026-10-23）**新增欄位**：
    - `attempt_id NULL`：D-8 第 2 點 N-64、N-66 子點第 4 項的決定嘗試（D-3 `forecast_record_attempt`）；其餘為 null。
    - `basis_json NOT NULL`：該列也適用、但不是決定者的其他 S 的 run 與記錄嘗試（定義同 D-8 第 2 點 N-64、N-66 子點）。JSON 陣列，每一項恰為 `{kind, id, reason_alone}`：`kind ∈ {run, attempt}`；`id` 是 `run_id` 或 `attempt_id`；`reason_alone` 是只看該項、依同子點第 3 項或第 4 項會得的值。依 (`kind`, `id`) 排序、不重複；沒有時為 `[]`。已為該範圍寫入紀錄（含 `late=1`）的 run 不列入。第 1、2 項成立的列，列出全部適用的 run 與記錄嘗試。
  - **寫入者**：只有 `audit.py` 的缺日稽核函式（AST 列舉呼叫點），`reason`、`run_id`、`attempt_id`、`basis_json` 由同一次判定自行填入，不接受呼叫端傳入。
  - **寫入驗證**（任一項不成立，整個稽核交易都不寫入，記 WARNING；比照 `forecast_gap_audit`）：
    - `run_id` 非 null ⇔ `reason ∈ {job_error, write_rejected, record_error, timeout}`；`attempt_id` 非 null ⇔ `reason ∈ {inputs_not_ready, record_start_failed}`；
    - `scope_key = '*'` ⇔ 該 `session` 沒有任何 S 的 run；
    - 在本交易內依 D-8 第 2 點 N-64、N-66 子點重算一次：`reason`、`run_id`、`attempt_id`、`basis_json` 都等於重算的值。
  - **用途限制**：`attempt_id`、`basis_json` 不屬於 `E_CHANGING_EVENTS`，不影響 E、n、W 或任何判定。只有 `audit.py`、`validation.py` 的缺日揭露（事先宣告 §6.3「缺日」）與稽核工具可以讀；`views`、API route、匯出與 `app.ops_alert.*` 不讀（AST）。
```
- 方向：補定義（收緊：新增持久化與寫入驗證）。
  - `run_id` 對 `timeout`、`job_error` 原本沒寫填不填，現在規定要填；`db_restored`、`late_only` 的列規定為 null。
- CEO：否。
- 被取代原文：無（插入）。
- 〔事實〕dev-lead 已查證 `app/forecast/` 在所有分支都不存在，沒有遷移問題（TA 2026-10-21 報告 L45）。

**A-4　FL-18（句末接字）**
- 插入點：`- **FL-18**：每個 run 不是有 `forecast_run_end` 列，就是被稽核成 `job_error`。`（L2376，1 處）的句號之後
- 逐字：
```
（N-64）「被稽核成 `job_error`」指：該 run 是某缺日列的決定 run 時，該列記 `job_error`；不是決定 run 時，該 run 出現在該列的 `basis_json`（`reason_alone = job_error`）；該 run 的範圍都已由它或其他 run 寫入、沒有缺日列可記時，不記（D-8 第 2 點 N-64、N-66 子點）。
```
- 方向：補定義。照實並陳：這段縮窄了 FL-18 原句的字面讀法。〔事實〕原句在單一 run 的情形下也有漏洞：沒有 end 的 run 如果已寫完全部範圍，就不會有缺日列。
- CEO：否。
- 被取代原文：無（句末接字；依風控 D-1 判準）。

**A-5　FL-76（插入）**
- 插入點：以 `  - (k) 全部寫入 → `outcome = ok`，`failed` 為假，E-3d 0 則` 開頭的那一行（L2388，1 處）**之後**。
- 逐字：
```
- **FL-76**（N-64、N-66；D-8 第 2 點 N-64、N-66 子點；D-3 `forecast_gaps` N-64 子點與 `forecast_record_attempt`；D-7 第 7 點 N-66 子點；ADR-0029 E-3d）：fixture 用 FL-74 的離線假市場 DB、假主 DB 與假的 `app.services.index`；各格的範圍快照只含該格列出的範圍，每個範圍各有 h＝3、h＝5 兩個 claim；以假 store 時鐘控制 22:10、23:10 與啟動補跑的時刻；稽核都在 S 的 `late_cutoff_at` 之後執行。各格的 run 都只含尚未寫入的範圍（重試遇到已寫入範圍的處理不在本格範圍）。
  - (a) 22:10 拒寫、23:10 中止：兩次的範圍快照都只有 B；22:10 B 拋 `LabeledThresholdSnapshotIncompleteError`；23:10 B 拋 `sqlite3.OperationalError` → B 的兩個 claim 各一列 `reason = record_error`，`run_id` 為 23:10 的 run，`basis_json` 恰為一項 `{kind: run, id: 22:10 的 run_id, reason_alone: write_rejected}`。
  - (b) 之後的 run 不含該範圍：22:10 的範圍快照只有 B，B 被拒寫；23:10 之前把 B 移出自選、加入 A，23:10 的範圍快照只有 A，寫入，`outcome = ok` → B 仍各一列 `reason = write_rejected`，`run_id` 為 22:10 的 run，`basis_json = []`；A 沒有缺日列；缺日列數與沒有 23:10 時相同。
  - (c) 22:10 沒有 end、23:10 逾時：兩次的範圍快照都是 B、C；22:10 在寫入任何範圍之前程序終止（沒有 end）；23:10 寫入 B 後期限已到 → C 各一列 `reason = timeout`，`run_id` 為 23:10 的 run，`basis_json` 恰為 22:10 的 run 一項（`reason_alone = job_error`）；B 沒有缺日列；FL-18 依其 N-64 句末成立。
  - (d) 逾時之後只有晚到紀錄：22:10 的範圍快照是 B、C，寫入 B 後期限已到；S 的 `late_cutoff_at` 之後，啟動補跑的範圍快照只有 C，寫入 C（`late=1`）→ C 各一列 `reason = late_only`，`run_id` 為 null，`basis_json` 恰為 22:10 的 run 一項（`reason_alone = timeout`），不含補跑的 run。
  - (e) 沒有 run、兩次嘗試：22:10 在判定候選 T 之前拋 `sqlite3.OperationalError`；23:10 候選 T ＝ S，依 D-7 第 3 點記 `inputs_not_ready` → 每個 claim 一列 `scope_key = '*'`、`reason = inputs_not_ready`，`attempt_id` 為 23:10 的嘗試，`basis_json` 恰為 22:10 的嘗試一項（`reason_alone = record_start_failed`）；22:10 的 end 為 `outcome = error_before_run`、`error_class = OperationalError`、`candidate_t` 為 null；E-3d 只有 22:10 的一則（`exception_class = OperationalError`）。
  - (f) 嘗試沒有 end：唯一一次嘗試在寫入開始列之後、判定候選 T 之前注入 `KeyboardInterrupt` → 不被記錄一步接住，沒有 end；稽核 → `record_start_failed`，`attempt_id` 為該次嘗試。
  - (g) 歸屬窗：沒有 end 的嘗試，`started_at` 早於 P 的 `late_cutoff_at` → 不是 S 的記錄嘗試；S 沒有其他 run 或嘗試 → `scheduler_down`，`attempt_id` 為 null，`basis_json = []`。`started_at` 恰等於 S 的 `late_cutoff_at` → 同樣不是 S 的記錄嘗試；早 1 微秒 → 是，記 `record_start_failed`。
  - (h) 沒有任何 run 與嘗試 → `scheduler_down`，`run_id`、`attempt_id` 為 null。
  - (i) 開始列寫不進去：讓開始列的寫入拋例外 → 沒有任何 `forecast_record_attempt` 列；例外到達編排函式，E-3d 一則（`step = record`）；稽核 → `scheduler_down`。
  - (j) end 寫不進去：(e) 的 22:10 再讓 `error_before_run` 的 end 寫入拋例外 → E-3d 的 `exception_class` 仍為 `OperationalError`；WARNING 一行，只含兩個例外的類別名稱，fixture 例外訊息的哨兵字串不出現；該嘗試沒有 end，`basis_json` 中該項的 `reason_alone` 仍為 `record_start_failed`。單獨一次嘗試、`inputs_not_ready` 的 end 寫入拋例外 → 例外往外拋，E-3d 一則；稽核 → `record_start_failed`。
  - (k) 帳目矛盾：以直接 SQL 插入（繞過 store 的寫入驗證）造出 end 為 `ok`、範圍快照含 C、而 C 沒有紀錄的 run → `GapAuditRunInconsistencyError`；沒有新的 `forecast_gaps` 與 `forecast_gap_audit` 列，`gap_judged_through` 不前進；E-3d 一則（`step = gap_audit`）。
  - (l) `db_restored` 優先：S 落在 `db_restored` 標記的區間，22:10 的範圍快照是 B、C，寫入 B 後期限已到 → C 各一列 `reason = db_restored`，`run_id` 為 null，`basis_json` 恰為 22:10 的 run 一項（`reason_alone = timeout`）。
  - (m) FL-63 的「交易日 10:00 啟動」fixture，之後沒有其他 run 與嘗試 → D 的每個 claim 一列 `scope_key = '*'`、`reason = inputs_not_ready`，`attempt_id` 為該次嘗試；該嘗試的 end 為 `outcome = inputs_not_ready`、`candidate_t = D`；E-3d 0 則。
  - (n) `run_written`：每一個 `trigger = scheduled` 的 `forecast_run` 恰好對到一列 `outcome = run_written` 的 end，兩者在同一個交易內寫入（spy）；`forecast_run` 寫入成功而 end 的寫入被注入失敗 → 兩者都不留；on-demand 的 POST 不寫 `forecast_record_attempt`。
  - (o) 寫入驗證：D-3 `forecast_gaps` N-64 子點與 `forecast_record_attempt` 所列每一項各一格違反 → 拒絕。
  - (p) AST：`forecast_record_attempt`、`forecast_record_attempt_end` 只有 `recorder.py` 的記錄一步寫入，只有 `audit.py` 與稽核工具讀取；`views.py`、API route、匯出與 `app/ops_alert/**` 不讀。`forecast_gaps` 的 `attempt_id`、`basis_json` 只有 `audit.py`、`validation.py` 與稽核工具讀取。記錄一步前置段的 `except Exception` 與範圍迴圈的 `except Exception` 不在同一個函式內；FL-74 (b) 照舊成立。
```
- 方向：收緊（測試）。
- CEO：否。
- 被取代原文：無（插入）。

---

#### 二、落字：N-66

**B-1　D-8 第 2 點「該日沒有任何 run」一項（句中插入）**
- 插入點：`該日沒有任何 run：`scheduler_down``（L1146，1 處）
- 換成：
```
該日沒有任何 run，也沒有該日的記錄嘗試（N-66；判定見本點 N-64、N-66 子點）：`scheduler_down`
```
- 方向：補定義（收緊：原因分辨得出來；列數不變）。
- CEO：否。
- **被取代原文**：`該日沒有任何 run：`scheduler_down``

**B-2　D-8 第 2 點「輸入未就緒」一項（句末接字）**
- 插入點：`輸入未就緒：`inputs_not_ready``（L1150，1 處）的行末
- 逐字：
```
（N-66：只依 D-3 `forecast_record_attempt_end` 判定，見本點 N-64、N-66 子點第 4 項）
```
- 方向：補定義（不變：指明存放處）。
- CEO：否。
- 被取代原文：無（句末接字）。

**B-3　D-8 第 2 點列舉計數（句中改字）**
- 插入點：`` `reason` 的封閉列舉因此共八值，與事先宣告 §6.3「缺日」第 1 點 v0.25 列舉相同：`scheduler_down`、`inputs_not_ready`、`timeout`、`job_error`、`late_only`、`db_restored`、`write_rejected`、`record_error`。 ``（L1154 句末，1 處）
- 換成：
```
`reason` 的封閉列舉因此共九值，與事先宣告 §6.3「缺日」第 1 點（N-66 同批修訂後）列舉相同：`scheduler_down`、`inputs_not_ready`、`timeout`、`job_error`、`late_only`、`db_restored`、`write_rejected`、`record_error`、`record_start_failed`（N-66；各值的判定順序見下方 N-64、N-66 子點）。
```
- 方向：補定義（列舉加值）。依附事先宣告同步（Q-1）。
- CEO：否。
- **被取代原文**：即上述插入點的整串字句。

**B-4　D-3 新表 `forecast_record_attempt`／`forecast_record_attempt_end`（插入）**
- 插入點：含 `` `forecast_run` 與 `forecast_scope_snapshot`：在同一個交易內寫入（A-25）。 `` 的那一行（L282，1 處）**之後**，和 L281 同一層。
- 逐字：
```
- （N-66；tech-architect 2026-10-23）`forecast_record_attempt(attempt_id INTEGER PRIMARY KEY AUTOINCREMENT, started_at)` 與 `forecast_record_attempt_end(attempt_id PK, outcome ∈ {run_written, inputs_not_ready, error_before_run}, candidate_t NULL, run_id NULL, error_class NULL, ended_at)`：排程記錄一步每一次執行的開始與結束，比照 `forecast_run`／`forecast_run_end`。兩張都只增不改（D-2 第 2 點）。沒有 end 列就代表記錄一步在寫入 `forecast_run` 之前中斷。
  - **開始列**：排程記錄一步的第一個寫入，以獨立交易寫入，在讀取市場 DB 與判定候選 T 之前。每一次排程記錄一步恰好一列；on-demand（D-7 第 8 點）不寫。`started_at` 由 store 時鐘填入（D-2 第 3 點）。開始列寫入失敗時，例外往外拋，記錄一步依 D-7 第 2 點標為失敗，不寫 end。
  - **end 列**，依 `outcome`：
    - `run_written`：與 A-25 的 `forecast_run`、`forecast_scope_snapshot` 在同一個交易內寫入；`run_id` 為該 run，`candidate_t` ＝ 該 run 的 `data_as_of`，`error_class` 為 null。每一個 `trigger = scheduled` 的 `forecast_run` 恰好對到一列 `run_written`。
    - `inputs_not_ready`：候選 T 依 D-7 第 3 點記為 `inputs_not_ready` 時，以獨立交易寫入；`candidate_t` 為該候選 T，`run_id`、`error_class` 為 null。這是「記 `inputs_not_ready`」唯一的持久化處（D-8 第 2 點）。寫入失敗時，例外往外拋，記錄一步依 D-7 第 2 點標為失敗。
    - `error_before_run`：開始列之後、A-25 交易 commit 之前拋出 `Exception` 時，依 D-7 第 7 點 N-66 子點以獨立交易盡力寫入；`candidate_t` 為已判定的候選 T，尚未判定時為 null；`run_id` 為 null；`error_class` 的規則同 `forecast_run_end.error_class`。
  - **寫入者**：只有 `recorder.py` 的記錄一步（AST 列舉呼叫點）。
  - **寫入驗證**（任一項不成立就拒絕寫入）：end 的 `attempt_id` 指向已存在的開始列；`outcome = run_written` ⇔ `run_id` 非 null，而且該 run 的 `trigger = scheduled`、`data_as_of = candidate_t`；`outcome = inputs_not_ready` ⇒ `candidate_t` 非 null；`error_class` 非 null ⇔ `outcome = error_before_run`。`forecast_run` 的寫入另加驗證：`trigger = scheduled` ⇒ 同一交易內恰好寫入一列指向它的 `run_written`。
  - **用途限制**：不屬於 `E_CHANGING_EVENTS`，不影響 E、n、W 或任何判定，只用於 D-8 第 2 點的 `reason`。只有 `audit.py` 與稽核工具可以讀；`views`、API route、匯出、`app.ops_alert.*` 與編排函式不讀（AST）。告警不以這兩張表為來源，也不據以做跨執行的判斷（ADR-0029 失效條件 1）。
```
- 方向：補定義（收緊：新增持久化與寫入驗證）。
- CEO：知悉（表數；比照 G-5、待決事項 CEO 第 14、16 項的先例）。
- 被取代原文：無（插入）。

**B-5　D-7 第 7 點 N-66 子點（插入）**
- 插入點：以 `範圍明細只在 `refused_scopes_json`。` 結尾的那一行（L968，1 處）**之後**，縮排 3 格（和 N-52 子點同一層），放在「8. **on-demand**」之前。
- 逐字：
```
   - （N-66；tech-architect 2026-10-23）**記錄一步的前置段**（寫入 D-3 `forecast_record_attempt` 開始列之後、A-25 交易 commit 之前，含判定候選 T 與第 3 點的重抓）：
     - 前置段拋出 `Exception` 時：以獨立交易盡力寫入 `forecast_record_attempt_end`（`outcome = error_before_run`）；再以不帶參數的 `raise` 拋出原例外，由編排函式依第 2 點「步驟隔離」接住，發 ADR-0029 E-3d（`step = record`，`exception_class = type(exc).__name__`），與現行相同，只發這一則。end 寫入本身失敗時，記一行 WARNING，只含兩個例外的類別名稱，仍拋出原例外；該嘗試沒有 end，依 D-8 第 2 點記 `record_start_failed`。`KeyboardInterrupt`、`SystemExit` 等不是 `Exception` 的例外不接（比照 FL-71 (b)）。
     - 前置段的 `except Exception` 放在與範圍迴圈不同的函式內；本點 N-52 子點與 FL-74 (b)「同一函式恰好一個 `except Exception`」不變。
     - 候選 T 記為 `inputs_not_ready` 時，寫入 `outcome = inputs_not_ready` 的 end 之後正常返回；`RecordStepResult` 與 ADR-0029 E-3d 的處理不變（`inputs_not_ready` 不算失敗）。
     - 理由：D-8 第 2 點原本只能以「沒有任何 run」判定，記錄一步在寫入 `forecast_run` 之前失敗或中斷時會被記成 `scheduler_down`；`inputs_not_ready` 也沒有存放處。另一面（照實並陳）：開始列本身寫不進去時（例如主 DB 無法寫入），該次執行仍記 `scheduler_down`，只能由 E-3d 與 log 察覺。
```
- 方向：補定義（收緊）。E-3d 的次數與欄位都不變。
- CEO：否。
- 被取代原文：無（插入）。
- 〔事實〕FL-74 (b) 要求「同一函式恰好一個 `except Exception`」。所以前置段的 except 必須放在另一個函式，否則會和 FL-74 (b) 衝突。

---

#### 三、表數與 CEO 段（**和 v0.26 衝突**，兩種寫法並列）

〔事實〕quant v0.26 草案第二節第 15 點寫「若新增一張表，連帶要改：M-11 表數 17→18，全部表數 22→23（L89、L202、L2306）」，第 21 點預定新增「待決事項 CEO 段第 18 項」。

**寫法甲（本批先落檔）**：

| 段 | 插入點（各 1 處） | 換成／插入 | 被取代原文 |
|---|---|---|---|
| C-1 | `- 表數多（22 張），寫入規則有一部分在 trigger 裡。`（L89） | `- 表數多（24 張），寫入規則有一部分在 trigger 裡。` | 原行整句 |
| C-2 | `- 22 張表，加上 trigger 與部分唯一索引，遷移與測試成本高。`（L2306） | `- 24 張表，加上 trigger 與部分唯一索引，遷移與測試成本高。` | 原行整句 |
| C-3 | L202 兩處：`新增 17 張表（`；`` V15-04 加 `plan_coverage_log`）並取欄位聯集 `` | `新增 19 張表（`；`` V15-04 加 `plan_coverage_log`；N-66 加 `forecast_record_attempt`、`forecast_record_attempt_end`）並取欄位聯集 `` | 兩串原文 |
| C-4 | `V25-02～V25-04（N-68）知悉（見修訂紀錄 v0.25 同步批）。`（L3071 行末）之後另起一行 | 見下方 | 無（插入） |

C-4 的逐字：
```
18. （N-64、N-66，知悉）M-11 的表數隨 `forecast_record_attempt`、`forecast_record_attempt_end` 由 17 張改為 19 張，全部表數由 22 張改為 24 張。另請知悉兩項停擺與殘餘：N-64 帳目矛盾時缺日稽核整次不寫、驗證快照停寫，直到查明（比照 N-46）；N-66 的開始列寫不進去時，該次執行仍記 `scheduler_down`。
```
- 方向：不變（計數）。CEO：知悉。

**寫法乙（v0.26 先落檔、而且加了一張表）**：
- C-1、C-2 改成「23 → 25」。
- C-3 改成「新增 18 張表（ → 新增 20 張表（」，聯集句接在 v0.26 新增的表名之後，插入點要以 v0.26 落檔後的字串重新 Grep。
- C-4 改編為「19.」，字句改為「由 18 張改為 20 張，全部表數由 23 張改為 25 張」。
- 如果改採 A′ 單表，以上每一個加 2 都改成加 1。

---

#### 四、事先宣告要同步之處（只列，不寫；交 quant）

- **Q-1** §6.3「缺日」第 1 點，L1744：
  - `reason ∈ {…}` 加 `record_start_failed`，成為九值；
  - 〔v0.25 取代〕註裡的「兩者只依 ADR-0027 `forecast_run_end` 的紀錄判定」要補一句：`inputs_not_ready`、`record_start_failed` 依 `forecast_record_attempt_end` 判定。
  - 依先例屬句中改字，要錄存原列舉。
- **Q-2** 同一點：登記多 run 判定的三件事：列集合取 S 的 run 快照聯集、判定順序五項、「S 的 run」與「S 的記錄嘗試」的定義。可以只引用 ADR-0027 D-8 第 2 點 N-64、N-66 子點。
- **Q-3** §6.3「缺日」第 2 點，L1745「缺日、逾時、作廢三者合併揭露（R-8）。」：新增兩項揭露：
  - 依 `reason` 分列的缺日列數；
  - `basis_json` 中有 `reason_alone` 和該列 `reason` 不同的列數，依（`reason`, `reason_alone`）分列。
- **Q-4** §6.3 F-3 上限表（L1752）：〔推論〕不用改，逾時率以排程紀錄計，不讀 `reason`。
- **Q-5** L753「§6.3 缺日的既有原因值」、L1693 重放的 `inputs_not_ready` 比照句：不用改。
- **Q-6** 附錄 C：
  - LG-27（L2439）不用改；
  - 要不要加一格對應 FL-76，由 quant 定；
  - 其他以 `reason` 為期望值的 LG 格，未查證。
- **Q-7** 版號：〔推論〕依 V25-05 先例屬補定義，不升 dirdef。請 quant 確認。
- 〔事實〕v0.26 草案沒有碰 §6.3「缺日」（L1742-1746），所以 Q 項和 v0.26 沒有字面衝突。可以併入 v0.26，也可以另開一版，由 quant 決定。

#### 五、修訂紀錄骨架（交 tech-writer）

- 段名：「N-64、N-66 缺日原因批（D-3 `forecast_gaps`、`forecast_record_attempt`／`_end`；D-7 第 7 點；D-8 第 2 點；FL-18；FL-76；M-11 表數；待決事項 CEO 段）」。
- 逐項的方向與 CEO 層級，照第一～三節。
- 被取代原文要錄存的有：B-1、B-3、C-1、C-2、C-3。其餘段都是插入或句末接字。
- L5021「`audit.py` 遇到同一觀察日有多個 run 時的 `reason` 判定，等 … 第六節第 1 點定案」：風控確認後在句末加〔已決〕，原文不改。

#### 對實作的約束（逐條，qa-reviewer 可以檢查）

1. `reason` 依 A-2 的五項順序判定，只讀持久化的表（FL-76 (a)～(m)）。
2. 列集合取全部 S 的 run 快照聯集；把範圍移出自選也不能消掉列（FL-76 (b)）。
3. 帳目矛盾時拋 `GapAuditRunInconsistencyError`，整次稽核不寫，不得改記其他值（FL-76 (k)）。
4. 開始列是記錄一步的第一個寫入；`run_written` 和 A-25 在同一交易；前置段的 except 放在另一個函式（FL-76 (i)(n)(p)）。
5. `forecast_gaps` 的三欄（`run_id`、`attempt_id`、`basis_json`）在交易內重算後必須一致（FL-76 (o)）。
6. 禁止事項：
   - 以 log、告警或 job 事件推定 `inputs_not_ready`、`record_start_failed`、`scheduler_down`；
   - 告警或編排函式讀新表或 `basis_json`；
   - 前置段和範圍迴圈共用同一個 `except Exception` 函式。

---

## 驗證

- 只用 Read、Grep、Glob，沒有 Edit、Write 或 commit，沒有讀 `.env`，沒有碰 `*.db`。
- **讀過的段落**：
  - **ADR-0027**（`/home/user/AICompany/docs/adr/0027-stock-desk-預測紀錄帳-儲存-PIT輸入-排程與定義登記.md`）：
    - L261-290：D-2、D-3 `forecast_run`／`forecast_run_end`；
    - L690-774：`forecast_gaps`、`forecast_gap_audit`、`plan_coverage_log`；
    - L830-1168：D-7、D-8；
    - L2091-2101：D-11 第 6 點；
    - L2370-2377：FL-14～FL-18；
    - L2597 FL-67 (n)；
    - L3053-3077：待決事項；
    - L4960-5023：修訂紀錄末段。
  - **ADR-0029**（`/home/user/AICompany/docs/adr/0029-stock-desk-維運告警通道.md`）：L60-89、L200-219、L315-326，另 Grep E-3d 相關各列。
  - **事先宣告**（`/home/user/AICompany/work/research/2026-10-15-3日5日方向判斷-事先宣告草案.md`）：L1740-1772，另 Grep 缺日、`inputs_not_ready`。
  - **TA 前案**：`/home/user/AICompany/work/reviews/2026-10-21-記錄一步批落字起草-tech-architect.md` 全文。
  - **v0.26 草案**：`/home/user/AICompany/work/reviews/2026-10-23-v0.26重放執行閘門批草案-quant.md`，Grep 加 L270-289。
  - **追蹤清單**：`/home/user/AICompany/work/dispatch/2026-10-17-後續追蹤清單.md` L148-151。
- **插入點唯一性**（Grep `-o`，ADR-0027 各 1 處）：
  - L282、L693、L968、L1146、L1150、L1154（B-3 的整串）、L1155、L2376、L2388；
  - 表數字串：L89、L202（兩串）、L2306、L3071。
- **機械核對清單**：預期值把本稿字句的出現次數都算進去，**不含** tech-writer 之後加的修訂紀錄段。現值都已 Grep 確認。

| 字串（ADR-0027） | 現值 | 落檔後 |
|---|---|---|
| `N-64` | 0 | 21 |
| `N-66` | 0 | 23 |
| `forecast_record_attempt`（含 `_end` 的子字串） | 0 | 20 |
| `forecast_record_attempt_end` | 0 | 8 |
| `attempt_id` | 0 | 17 |
| `basis_json` | 0 | 16 |
| `reason_alone` | 0 | 9 |
| `record_start_failed` | 0 | 10 |
| `error_before_run` | 0 | 9 |
| `run_written` | 0 | 8 |
| `GapAuditRunInconsistencyError` | 0 | 2 |
| `FL-76` | 0 | 1 |
| `共八值`／`共九值` | 1／0 | 0／1 |
| `該日沒有任何 run：`／`該日沒有任何 run，也沒有該日的記錄嘗試` | 1／0 | 0／1 |
| `表數多（22 張）`／`表數多（24 張）`（寫法甲） | 1／0 | 0／1 |
| `- 22 張表，加上`／`- 24 張表，加上`（寫法甲） | 1／0 | 0／1 |
| `新增 17 張表（`／`新增 19 張表（`（寫法甲） | 1／0 | 0／1 |

  - 落檔後，其餘 6 個插入點字串（L282、L693、L968、L1150、L1155、L2376、L2388 中未被改字者）仍各 1 處。
  - ADR-0029 與事先宣告：本批 diff 為空。
- **未查證**：
  - 失效條件 F-3 的「缺日率」以列計還是以日計、是否排除 `late_only`；
  - 23:10 重試遇到範圍快照含已寫入範圍時的處理（ADR 沒有定義；FL-76 刻意避開）；
  - 「已決定 T 卻沒有寫入 `forecast_run`」的正常路徑是否存在（`RecordStepResult` 的「沒有 T、或沒有寫入 `forecast_run`」暗示可能有）；
  - 事先宣告 §4.2 有沒有依 `reason` 分列；
  - 程式碼本身（依 dev-lead 前案，記錄一步還沒實作）。

---

## 下一步

1. **coordinator**：把 A-1～A-5、B-1～B-5、C-1～C-4 送 risk-compliance-officer 逐字確認。要裁定的點：
   - (i) N-64 採甲案（取快照含該範圍、`run_id` 最大的 run）；備選是乙案（嚴重度）、丁案（第一個 run）；
   - (ii) 列集合取聯集；
   - (iii) 判定順序。`late_only` 先於 run 的原因如果被判為放寬，要送 CEO 明確同意；
   - (iv) 帳目矛盾時 fail-closed 停擺。備選是記 `job_error` 加 WARNING；
   - (v) N-66 採 A 案，新值命名 `record_start_failed`（備選名 `record_aborted_before_run`）；兩張表或改 A′ 單表；
   - (vi) 記錄嘗試的歸屬窗 [P 的 `late_cutoff_at`, S 的 `late_cutoff_at`)；
   - (vii) 用 `basis_json` 揭露被蓋過的原因。
2. **coordinator 和 v0.26 TA 協調**，四件事：
   - 表數與 CEO 段編號：依落檔先後選寫法甲或乙；
   - FL-76 編號：v0.26 如果先用掉，本稿順延，只有 A-5 標題一處要改；
   - L692／L693 相鄰插入的合併順序；
   - 重放的「嘗試紀錄」表名要避開 `forecast_record_attempt`。
3. **quant-researcher**：判定 Q-1～Q-7，決定併入 v0.26 還是另開一版。
4. **dev-lead**：查證三件事，結果回給 TA：
   - 有沒有「決定 T 之後不寫 `forecast_run`」的正常返回路徑；有的話，`forecast_record_attempt_end.outcome` 要加值；
   - 重試遇到已寫入範圍時怎麼處理；
   - 前置段 except 放在另一個函式是否可行。
   - 定案之前，`audit.py` 的多 run 判定與 `record_start_failed` 先不要實作。
5. **追蹤清單新增兩項**：
   - 新登記的 claim，缺日義務從哪一日開始，沒有定義。在已有 `forecast_run` 的觀察日登記新的前瞻 claim 之前必須定案，否則會觸發 A-2 第 3 項的停擺。擋：D_v 之後的新 claim 登記。
   - 失效條件 F-3 缺日率的計數單位。
6. **tech-writer**：風控確認後依第五節骨架落檔，和事先宣告的同步在同一個 commit。之後依 CLAUDE.md 送 qa-reviewer（含 Codex 第二意見）。

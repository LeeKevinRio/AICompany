# N-64、N-66 缺日原因批寫法乙落字稿

- 審查者：tech-architect
- 日期：2026-10-24
- 轉存：coordinator，逐字轉存 subagent 最終回報

---

# N-64、N-66 缺日原因批：寫法乙落字稿（依 v0.26 落檔後的現行檔重新定位）

## 本次結論

1. **稿子可以直接送風控逐字確認。** 字面以原稿為底，有四處變動：
   - 表數與待決事項 CEO 段改用寫法乙：M-11 由 18 張改為 20 張，全部表數由 23 張改為 25 張，CEO 段為第 20 項。
   - 全部定位串都依 a58f641 落檔後的 ADR-0027 重新 Grep 過，每一串恰好 1 處。
   - 新增 D-1：在 L5165 句末加〔已決（N-64）〕。
   - 新增 E：本批的修訂紀錄段，逐字附上，預期值已把它算進去。
2. **表名 `forecast_record_attempt` 保留，不改。**
   - 〔事實〕v0.26 的 R-1 是把**重放那一側**由 `forecast_replay_attempt` 改名為 `forecast_replay_execution_log`，理由正是要避開和本批的 `forecast_record_attempt` 只差 rep／rec。改名已經在對方完成，本批不再有字形衝突。
   - 〔事實〕`attempt_id` 在 ADR 中出現 0 次，因為重放一側用的是 `log_row_id`、`execution_seq`。
   - **但中文用語要改。** 原稿的「記錄嘗試」和 v0.26 的「嘗試紀錄」（ADR 現有 16 處）只是兩個詞前後對調，「記錄」和「紀錄」又容易混，和 R-1 是同一種風險。我把它全稿一律改成「**記錄一步嘗試**」（共 13 處）。B-4 另加一項「與重放的區分」，寫明兩者不是同一件事，並禁止互相讀寫。
3. **N-64 仍採甲案，N-66 仍採 A 案（兩張表）。**
   - 〔事實〕v0.26 的 `forecast_replay_execution_log` 用的是單表加 `entry_kind`，也就是原稿 A′ 的形狀，所以現在兩種寫法都有先例。
   - 協調已定為加 2 張表，本稿照辦。風控如果要求改 A′ 單表，表數要改成 19／24，K3、K4 等計數也要重算。
4. **事先宣告要改字，不能寫「不需改字」。** 原因是 ADR 的 B-3 寫「與事先宣告 §6.3『缺日』第 1 點列舉相同」，事先宣告的列舉也要從八值變九值。給 quant 的建議字面見下方 Q-1～Q-3，要和 ADR 同一個 commit。
5. **CEO 部分。**
   - 只需要知悉的有第 20 項，內容是表數，加上兩個停擺與殘餘代價。
   - 有一個條件式項目：A-2 第 2 項是「`late_only` 優先於 run 的原因」。風控如果判為放寬，就要另立第 21 項，請 CEO **明確同意**；字句已備好（C-5）。

## 各部門回報

### tech-architect

#### 一、完整落字稿

Grep 次數一律以 `-o` 計（每一次出現算 1）。Grep 的 count 模式算的是行數，不能拿來核對。

**C-1　評估摘要（句中改字）**
- old（L89，1 處）：`- 表數多（23 張），寫入規則有一部分在 trigger 裡。`
- new：`- 表數多（25 張），寫入規則有一部分在 trigger 裡。`

**C-2　Consequences（句中改字）**
- old（L2397，1 處）：`- 23 張表，加上 trigger 與部分唯一索引，遷移與測試成本高。`
- new：`- 25 張表，加上 trigger 與部分唯一索引，遷移與測試成本高。`

**C-3a　M-11（句中改字）**
- old（L202，1 處）：`新增 18 張表（`
- new：`新增 20 張表（`

**C-3b　M-11 聯集句（句中插入）**
- old（L202，1 處；落檔後重新 Grep 的結果）：`；V26-04 加 `forecast_replay_execution_log`）並取欄位聯集`
- new：`；V26-04 加 `forecast_replay_execution_log`；N-66 加 `forecast_record_attempt`、`forecast_record_attempt_end`）並取欄位聯集`

**B-1　D-8 第 2 點（句中改字）**
- old（L1196，1 處）：`該日沒有任何 run：`scheduler_down``
- new：`該日沒有任何 run，也沒有該日的記錄一步嘗試（N-66；判定見本點 N-64、N-66 子點）：`scheduler_down``

**B-3　D-8 第 2 點列舉計數（句中改字）**
- old（L1204 句末，1 處）：`` `reason` 的封閉列舉因此共八值，與事先宣告 §6.3「缺日」第 1 點 v0.25 列舉相同：`scheduler_down`、`inputs_not_ready`、`timeout`、`job_error`、`late_only`、`db_restored`、`write_rejected`、`record_error`。 ``
- new：`` `reason` 的封閉列舉因此共九值，與事先宣告 §6.3「缺日」第 1 點（N-66 同批修訂後）列舉相同：`scheduler_down`、`inputs_not_ready`、`timeout`、`job_error`、`late_only`、`db_restored`、`write_rejected`、`record_error`、`record_start_failed`（N-66；各值的判定順序見下方 N-64、N-66 子點）。 ``

**D-1　修訂紀錄 v0.25 同步批「落檔後的閘門」（句末接字）**
- 定位串（L5165，1 處）：`不再擋重放執行閘門 (d)；見修訂紀錄 v0.26 同步批。本項原文不改〕`。在它之後接上：
```
〔已決（N-64）：多個 run 時的 `reason` 判定見 D-8 第 2 點 N-64、N-66 子點；見修訂紀錄 N-64、N-66 缺日原因批。本項原文不改〕
```
- 注意：較短的串 `見修訂紀錄 v0.26 同步批。本項原文不改〕` 在檔內有 3 處，不能拿來定位。

**C-4　待決事項 CEO 第 20 項（插入）**
- 插入位置：以下這一行（L3215，1 處）**之後**另起一行：`19. （V26-04，知悉）M-11 的表數隨 `forecast_replay_execution_log` 由 17 張改為 18 張，全部表數由 22 張改為 23 張。`
```
20. （N-64、N-66，知悉）M-11 的表數隨 `forecast_record_attempt`、`forecast_record_attempt_end` 由 18 張改為 20 張，全部表數由 23 張改為 25 張。另請知悉兩項停擺與殘餘：N-64 帳目矛盾時缺日稽核整次不寫、驗證快照停寫，直到查明（比照 N-46）；N-66 的開始列寫不進去時，該次執行仍記 `scheduler_down`。
```

**C-5（條件式：只在風控判 A-2 第 2 項為放寬時才落檔）**
- 插入位置：C-4 之後另起一行。
```
21. （N-64，明確同意）同一觀察日先有失敗的排程紀錄、之後只有晚到紀錄時，缺日原因記為 `late_only`，不記該次失敗的原因（D-8 第 2 點 N-64、N-66 子點第 2 項）；`late_only` 不計入 TG-c，相對「依 run 的原因記」的讀法，TG-c 的計數較少。CEO 明確同意之前本批不落檔。
```

**A-5　FL-76（插入）**
- 插入位置：以 `  - (k) 全部寫入 → `outcome = ok`，`failed` 為假，E-3d 0 則` 開頭的那一行（L2479，1 處）**之後**。
- 〔事實〕FL-76 目前在 ADR 中出現 0 次（現有最大是 FL-75，在 L3087），保留給本批可用。
```
- **FL-76**（N-64、N-66；D-8 第 2 點 N-64、N-66 子點；D-3 `forecast_gaps` N-64 子點與 `forecast_record_attempt`；D-7 第 7 點 N-66 子點；ADR-0029 E-3d）：fixture 用 FL-74 的離線假市場 DB、假主 DB 與假的 `app.services.index`；各格的範圍快照只含該格列出的範圍，每個範圍各有 h＝3、h＝5 兩個 claim；以假 store 時鐘控制 22:10、23:10 與啟動補跑的時刻；稽核都在 S 的 `late_cutoff_at` 之後執行。各格的 run 都只含尚未寫入的範圍（重試遇到已寫入範圍的處理不在本格範圍）。
  - (a) 22:10 拒寫、23:10 中止：兩次的範圍快照都只有 B；22:10 B 拋 `LabeledThresholdSnapshotIncompleteError`；23:10 B 拋 `sqlite3.OperationalError` → B 的兩個 claim 各一列 `reason = record_error`，`run_id` 為 23:10 的 run，`basis_json` 恰為一項 `{kind: run, id: 22:10 的 run_id, reason_alone: write_rejected}`。
  - (b) 之後的 run 不含該範圍：22:10 的範圍快照只有 B，B 被拒寫；23:10 之前把 B 移出自選、加入 A，23:10 的範圍快照只有 A，寫入，`outcome = ok` → B 仍各一列 `reason = write_rejected`，`run_id` 為 22:10 的 run，`basis_json = []`；A 沒有缺日列；缺日列數與沒有 23:10 時相同。
  - (c) 22:10 沒有 end、23:10 逾時：兩次的範圍快照都是 B、C；22:10 在寫入任何範圍之前程序終止（沒有 end）；23:10 寫入 B 後期限已到 → C 各一列 `reason = timeout`，`run_id` 為 23:10 的 run，`basis_json` 恰為 22:10 的 run 一項（`reason_alone = job_error`）；B 沒有缺日列；FL-18 依其 N-64 句末成立。
  - (d) 逾時之後只有晚到紀錄：22:10 的範圍快照是 B、C，寫入 B 後期限已到；S 的 `late_cutoff_at` 之後，啟動補跑的範圍快照只有 C，寫入 C（`late=1`）→ C 各一列 `reason = late_only`，`run_id` 為 null，`basis_json` 恰為 22:10 的 run 一項（`reason_alone = timeout`），不含補跑的 run。
  - (e) 沒有 run、兩次嘗試：22:10 在判定候選 T 之前拋 `sqlite3.OperationalError`；23:10 候選 T ＝ S，依 D-7 第 3 點記 `inputs_not_ready` → 每個 claim 一列 `scope_key = '*'`、`reason = inputs_not_ready`，`attempt_id` 為 23:10 的嘗試，`basis_json` 恰為 22:10 的嘗試一項（`reason_alone = record_start_failed`）；22:10 的 end 為 `outcome = error_before_run`、`error_class = OperationalError`、`candidate_t` 為 null；E-3d 只有 22:10 的一則（`exception_class = OperationalError`）。
  - (f) 嘗試沒有 end：唯一一次嘗試在寫入開始列之後、判定候選 T 之前注入 `KeyboardInterrupt` → 不被記錄一步接住，沒有 end；稽核 → `record_start_failed`，`attempt_id` 為該次嘗試。
  - (g) 歸屬窗：沒有 end 的嘗試，`started_at` 早於 P 的 `late_cutoff_at` → 不是 S 的記錄一步嘗試；S 沒有其他 run 或嘗試 → `scheduler_down`，`attempt_id` 為 null，`basis_json = []`。`started_at` 恰等於 S 的 `late_cutoff_at` → 同樣不是 S 的記錄一步嘗試；早 1 微秒 → 是，記 `record_start_failed`。
  - (h) 沒有任何 run 與嘗試 → `scheduler_down`，`run_id`、`attempt_id` 為 null。
  - (i) 開始列寫不進去：讓開始列的寫入拋例外 → 沒有任何 `forecast_record_attempt` 列；例外到達編排函式，E-3d 一則（`step = record`）；稽核 → `scheduler_down`。
  - (j) end 寫不進去：(e) 的 22:10 再讓 `error_before_run` 的 end 寫入拋例外 → E-3d 的 `exception_class` 仍為 `OperationalError`；WARNING 一行，只含兩個例外的類別名稱，fixture 例外訊息的哨兵字串不出現；該嘗試沒有 end，`basis_json` 中該項的 `reason_alone` 仍為 `record_start_failed`。單獨一次嘗試、`inputs_not_ready` 的 end 寫入拋例外 → 例外往外拋，E-3d 一則；稽核 → `record_start_failed`。
  - (k) 帳目矛盾：以直接 SQL 插入（繞過 store 的寫入驗證）造出 end 為 `ok`、範圍快照含 C、而 C 沒有紀錄的 run → `GapAuditRunInconsistencyError`；沒有新的 `forecast_gaps` 與 `forecast_gap_audit` 列，`gap_judged_through` 不前進；E-3d 一則（`step = gap_audit`）。
  - (l) `db_restored` 優先：S 落在 `db_restored` 標記的區間，22:10 的範圍快照是 B、C，寫入 B 後期限已到 → C 各一列 `reason = db_restored`，`run_id` 為 null，`basis_json` 恰為 22:10 的 run 一項（`reason_alone = timeout`）。
  - (m) FL-63 的「交易日 10:00 啟動」fixture，之後沒有其他 run 與嘗試 → D 的每個 claim 一列 `scope_key = '*'`、`reason = inputs_not_ready`，`attempt_id` 為該次嘗試；該嘗試的 end 為 `outcome = inputs_not_ready`、`candidate_t = D`；E-3d 0 則。
  - (n) `run_written`：每一個 `trigger = scheduled` 的 `forecast_run` 恰好對到一列 `outcome = run_written` 的 end，兩者在同一個交易內寫入（spy）；`forecast_run` 寫入成功而 end 的寫入被注入失敗 → 兩者都不留；on-demand 的 POST 不寫 `forecast_record_attempt`。
  - (o) 寫入驗證：D-3 `forecast_gaps` N-64 子點與 `forecast_record_attempt` 所列每一項各一格違反 → 拒絕。
  - (p) AST：`forecast_record_attempt`、`forecast_record_attempt_end` 只有 `recorder.py` 的記錄一步寫入，只有 `audit.py` 與稽核工具讀取；`views.py`、API route、匯出、`app/ops_alert/**` 與重放執行函式不讀，重放執行函式也不寫。`forecast_gaps` 的 `attempt_id`、`basis_json` 只有 `audit.py`、`validation.py` 與稽核工具讀取。記錄一步前置段的 `except Exception` 與範圍迴圈的 `except Exception` 不在同一個函式內；FL-74 (b) 照舊成立。
```

**A-4　FL-18（句末接字）**
- 定位串（L2467，1 處）：`- **FL-18**：每個 run 不是有 `forecast_run_end` 列，就是被稽核成 `job_error`。`。在句號之後接上：
```
（N-64）「被稽核成 `job_error`」指：該 run 是某缺日列的決定 run 時，該列記 `job_error`；不是決定 run 時，該 run 出現在該列的 `basis_json`（`reason_alone = job_error`）；該 run 的範圍都已由它或其他 run 寫入、沒有缺日列可記時，不記（D-8 第 2 點 N-64、N-66 子點）。
```

**A-1　D-8 第 2 點（句末接字）**
- 定位串（L1205，1 處）：`有範圍快照時，逐 scope 寫列；沒有快照（例如 scheduler 停機）時，寫 `scope_key='*'`。`。在句號之後接上：
```
（N-64；tech-architect 2026-10-23）同一觀察日 S 有多個 S 的 run（定義見上方 N-64、N-66 子點）時，「範圍快照」指全部 S 的 run 的範圍快照的聯集，聯集中每一個沒有 `late=0` 排程紀錄的範圍各寫一列；不得只取最後一個 run 的快照，也不得因之後的 run 不含某個範圍而不寫該範圍的列。沒有任何 S 的 run 時（含只有記錄一步嘗試），寫 `scope_key='*'`。
```

**A-2　D-8 第 2 點 N-64、N-66 子點（插入）**
- 插入位置：以 `   - 有範圍快照時，逐 scope 寫列；` 開頭的那一行（L1205）**之前**，也就是接在 L1204（B-3 那一行）之後。縮排 5 格。
- 和原稿相比的改動：「記錄嘗試」改為「記錄一步嘗試」；不得據以推定的來源加上 `forecast_replay_execution_log`；「另案（見後續追蹤）」改為指名 N-84。
```
     - （N-64、N-66；tech-architect 2026-10-23）**同一觀察日有多個 run 或記錄一步嘗試時的判定**（本子點優先於上方各項的排列順序；上方各項只描述單一 run 或單一嘗試的狀態）：
       - **S 的 run**：`trigger = scheduled`、`data_as_of = S` 的 `forecast_run`，取稽核交易內讀到的全部列；22:10、23:10 重試與啟動補跑寫入的都算，不論是否逾時。on-demand 的 run 不算。
       - **S 的記錄一步嘗試**：D-3 `forecast_record_attempt` 中符合下列任一項的列：(a) 它的 `forecast_record_attempt_end` 為 `outcome ∈ {inputs_not_ready, error_before_run}`，而且 `candidate_t = S`；(b) 沒有 end，或 end 為 `outcome = error_before_run` 而 `candidate_t` 為 null，而且 `started_at` ∈ [P 的 `late_cutoff_at`, S 的 `late_cutoff_at`)。P 是稽核所讀觀察日集合中早於 S 的最晚一日，不存在時不設下界；`late_cutoff_at` 以 D-7.4 的同一個函式計算。end 為 `outcome = run_written` 的嘗試不是記錄一步嘗試，依它寫入的 run 判定。
       - **缺日列存不存在不受本子點影響**：只依本點首句（沒有 `late=0` 的排程紀錄）；任一 run 已為該範圍寫入 `late=0` 紀錄，該範圍就沒有缺日列。列的集合依本點「有範圍快照時」一項的 N-64 句末。
       - **`reason` 依下列順序取第一個成立者**：
         1. S 落在 `db_restored` 標記的區間：`db_restored`；
         2. 該範圍只有 `late=1` 的排程紀錄：`late_only`；
         3. 有 S 的 run，其範圍快照含該範圍：取其中 `run_id` 最大的一個（決定 run），只依決定 run 判定：沒有 end → `job_error`；該範圍列在其 end 的 `refused_scopes_json` → `write_rejected`；其 end 的 `outcome = error` → `record_error`；`outcome = timeout` → `timeout`。決定 run 的 end 為 `ok` 或 `partial`、而該範圍不在 `refused_scopes_json` 時，屬帳目矛盾：稽核拋 `GapAuditRunInconsistencyError`（`app/forecast/errors.py`），整個稽核交易 rollback，不寫任何缺日列與 `forecast_gap_audit` 列，依 D-7 第 2 點記 WARNING，發 ADR-0029 E-3d（`step = gap_audit`）；不得改記其他值。claim 的 `registered_at` 晚於決定 run 的 `recorded_at` 時同樣適用本項；缺日義務從哪一日開始另案（後續追蹤清單 N-84）；
         4. 沒有 S 的 run，而有 S 的記錄一步嘗試：取其中 `attempt_id` 最大的一個（決定嘗試）：end 為 `outcome = inputs_not_ready` → `inputs_not_ready`；沒有 end，或 `outcome = error_before_run` → `record_start_failed`；
         5. 以上都不成立：`scheduler_down`。
       - 同一個 run 內 `write_rejected` 先於 `timeout`、`record_error`（上方 N-51、N-52 一項）照舊，是第 3 項在決定 run 內的判定。
       - **只依持久化的紀錄判定**：`inputs_not_ready`、`record_start_failed` 只依 D-3 `forecast_record_attempt` 與 `forecast_record_attempt_end`；第 3 項只依 `forecast_run`、`forecast_scope_snapshot`、`forecast_run_end`。不得以 log、告警、`forecast_ledger_events`、`plan_coverage_log`、`forecast_replay_execution_log` 或 job 層事件推定。
       - **`forecast_gaps` 的參照欄**：第 3 項的列，`run_id` 填決定 run；第 4 項的列，`attempt_id` 填決定嘗試；其餘為 null。`basis_json` 依 D-3 `forecast_gaps` N-64 子點，列出該列也適用、但不是決定者的其他 S 的 run 與記錄一步嘗試。
       - 理由：取最後一個，使 `reason` 描述該範圍最後一次嘗試的結果，與 D-3 `plan_coverage_log`「衍生計數」中同一 T 多次作業的取法一致（應有集合取聯集；略過原因取含該標的的最後一次作業）。只在範圍快照含該範圍的 run 中取，之後一次不含該範圍的 run 就蓋不掉它的原因。`db_restored`、`late_only` 是區間與紀錄的事實，不依 run 判定，所以放在前面；`late_only` 先於 run 的原因，與 D-8 第 5 點的渲染及 FL-67 (h)「只有逾時紀錄 → `late_only`」一致。
       - 另一面（照實並陳）：之後的 run 可以改變一列的 `reason`（例如重開機觸發啟動補跑後再中止，使 `write_rejected` 變成 `record_error` 或 `job_error`），但改變不了列數；被蓋過的原因留在 `basis_json`，依事先宣告 §6.3「缺日」揭露。帳目矛盾時缺日稽核整次不寫，`gap_judged_through` 停止前進，驗證快照依 D-7 第 2 點的前置條件不寫，直到查明（比照 N-46 的停擺代價）。
```

**B-2　D-8 第 2 點（句末接字）**
- 定位串（L1200，1 處）：`輸入未就緒：`inputs_not_ready``。在行末接上：
```
（N-66：只依 D-3 `forecast_record_attempt_end` 判定，見本點 N-64、N-66 子點第 4 項）
```

**B-5　D-7 第 7 點 N-66 子點（插入）**
- 插入位置：以 `範圍明細只在 `refused_scopes_json`。` 結尾的那一行（L1018，1 處）**之後**，放在「8. **on-demand**」之前。縮排 3 格，和 N-52 子點同一層。
```
   - （N-66；tech-architect 2026-10-23）**記錄一步的前置段**（寫入 D-3 `forecast_record_attempt` 開始列之後、A-25 交易 commit 之前，含判定候選 T 與第 3 點的重抓）：
     - 前置段拋出 `Exception` 時：以獨立交易盡力寫入 `forecast_record_attempt_end`（`outcome = error_before_run`）；再以不帶參數的 `raise` 拋出原例外，由編排函式依第 2 點「步驟隔離」接住，發 ADR-0029 E-3d（`step = record`，`exception_class = type(exc).__name__`），與現行相同，只發這一則。end 寫入本身失敗時，記一行 WARNING，只含兩個例外的類別名稱，仍拋出原例外；該嘗試沒有 end，依 D-8 第 2 點記 `record_start_failed`。`KeyboardInterrupt`、`SystemExit` 等不是 `Exception` 的例外不接（比照 FL-71 (b)）。
     - 前置段的 `except Exception` 放在與範圍迴圈不同的函式內；本點 N-52 子點與 FL-74 (b)「同一函式恰好一個 `except Exception`」不變。
     - 候選 T 記為 `inputs_not_ready` 時，寫入 `outcome = inputs_not_ready` 的 end 之後正常返回；`RecordStepResult` 與 ADR-0029 E-3d 的處理不變（`inputs_not_ready` 不算失敗）。
     - 理由：D-8 第 2 點原本只能以「沒有任何 run」判定，記錄一步在寫入 `forecast_run` 之前失敗或中斷時會被記成 `scheduler_down`；`inputs_not_ready` 也沒有存放處。另一面（照實並陳）：開始列本身寫不進去時（例如主 DB 無法寫入），該次執行仍記 `scheduler_down`，只能由 E-3d 與 log 察覺。
```

**A-3　D-3 `forecast_gaps` 新增欄位（插入）**
- 插入位置：含 `` `scope_key = '*'` 代表整個 claim。 `` 的那一行（L743，1 處）**之後**，縮排 2 格，放在 L744 的 `forecast_gap_audit` 之前。
- 〔事實〕這一行緊接在 v0.26 新表 `forecast_replay_execution_log` 區塊（L721～742）之後，但本批不碰該區塊。原稿 L692／L693 的相鄰問題已經不存在。
```
  - （N-64、N-66；tech-architect 2026-10-23）**新增欄位**：
    - `attempt_id NULL`：D-8 第 2 點 N-64、N-66 子點第 4 項的決定嘗試（D-3 `forecast_record_attempt`）；其餘為 null。
    - `basis_json NOT NULL`：該列也適用、但不是決定者的其他 S 的 run 與記錄一步嘗試（定義同 D-8 第 2 點 N-64、N-66 子點）。JSON 陣列，每一項恰為 `{kind, id, reason_alone}`：`kind ∈ {run, attempt}`；`id` 是 `run_id` 或 `attempt_id`；`reason_alone` 是只看該項、依同子點第 3 項或第 4 項會得的值。依 (`kind`, `id`) 排序、不重複；沒有時為 `[]`。已為該範圍寫入紀錄（含 `late=1`）的 run 不列入。第 1、2 項成立的列，列出全部適用的 run 與記錄一步嘗試。
  - **寫入者**：只有 `audit.py` 的缺日稽核函式（AST 列舉呼叫點），`reason`、`run_id`、`attempt_id`、`basis_json` 由同一次判定自行填入，不接受呼叫端傳入。
  - **寫入驗證**（任一項不成立，整個稽核交易都不寫入，記 WARNING；比照 `forecast_gap_audit`）：
    - `run_id` 非 null ⇔ `reason ∈ {job_error, write_rejected, record_error, timeout}`；`attempt_id` 非 null ⇔ `reason ∈ {inputs_not_ready, record_start_failed}`；
    - `scope_key = '*'` ⇔ 該 `session` 沒有任何 S 的 run；
    - 在本交易內依 D-8 第 2 點 N-64、N-66 子點重算一次：`reason`、`run_id`、`attempt_id`、`basis_json` 都等於重算的值。
  - **用途限制**：`attempt_id`、`basis_json` 不屬於 `E_CHANGING_EVENTS`，不影響 E、n、W 或任何判定。只有 `audit.py`、`validation.py` 的缺日揭露（事先宣告 §6.3「缺日」）與稽核工具可以讀；`views`、API route、匯出與 `app.ops_alert.*` 不讀（AST）。
```

**B-4　D-3 新表（插入）**
- 插入位置：含 `` `forecast_run` 與 `forecast_scope_snapshot`：在同一個交易內寫入（A-25）。 `` 的那一行（L282，1 處）**之後**，和 L281 同一層。
- 和原稿相比的改動：首段加「（下稱「記錄一步嘗試」）」，末尾加「與重放的區分」一項。
```
- （N-66；tech-architect 2026-10-23）`forecast_record_attempt(attempt_id INTEGER PRIMARY KEY AUTOINCREMENT, started_at)` 與 `forecast_record_attempt_end(attempt_id PK, outcome ∈ {run_written, inputs_not_ready, error_before_run}, candidate_t NULL, run_id NULL, error_class NULL, ended_at)`：排程記錄一步每一次執行的開始與結束（下稱「記錄一步嘗試」），比照 `forecast_run`／`forecast_run_end`。兩張都只增不改（D-2 第 2 點）。沒有 end 列就代表記錄一步在寫入 `forecast_run` 之前中斷。
  - **開始列**：排程記錄一步的第一個寫入，以獨立交易寫入，在讀取市場 DB 與判定候選 T 之前。每一次排程記錄一步恰好一列；on-demand（D-7 第 8 點）不寫。`started_at` 由 store 時鐘填入（D-2 第 3 點）。開始列寫入失敗時，例外往外拋，記錄一步依 D-7 第 2 點標為失敗，不寫 end。
  - **end 列**，依 `outcome`：
    - `run_written`：與 A-25 的 `forecast_run`、`forecast_scope_snapshot` 在同一個交易內寫入；`run_id` 為該 run，`candidate_t` ＝ 該 run 的 `data_as_of`，`error_class` 為 null。每一個 `trigger = scheduled` 的 `forecast_run` 恰好對到一列 `run_written`。
    - `inputs_not_ready`：候選 T 依 D-7 第 3 點記為 `inputs_not_ready` 時，以獨立交易寫入；`candidate_t` 為該候選 T，`run_id`、`error_class` 為 null。這是「記 `inputs_not_ready`」唯一的持久化處（D-8 第 2 點）。寫入失敗時，例外往外拋，記錄一步依 D-7 第 2 點標為失敗。
    - `error_before_run`：開始列之後、A-25 交易 commit 之前拋出 `Exception` 時，依 D-7 第 7 點 N-66 子點以獨立交易盡力寫入；`candidate_t` 為已判定的候選 T，尚未判定時為 null；`run_id` 為 null；`error_class` 的規則同 `forecast_run_end.error_class`。
  - **寫入者**：只有 `recorder.py` 的記錄一步（AST 列舉呼叫點）。
  - **寫入驗證**（任一項不成立就拒絕寫入）：end 的 `attempt_id` 指向已存在的開始列；`outcome = run_written` ⇔ `run_id` 非 null，而且該 run 的 `trigger = scheduled`、`data_as_of = candidate_t`；`outcome = inputs_not_ready` ⇒ `candidate_t` 非 null；`error_class` 非 null ⇔ `outcome = error_before_run`。`forecast_run` 的寫入另加驗證：`trigger = scheduled` ⇒ 同一交易內恰好寫入一列指向它的 `run_written`。
  - **用途限制**：不屬於 `E_CHANGING_EVENTS`，不影響 E、n、W 或任何判定，只用於 D-8 第 2 點的 `reason`。只有 `audit.py` 與稽核工具可以讀；`views`、API route、匯出、`app.ops_alert.*` 與編排函式不讀（AST）。告警不以這兩張表為來源，也不據以做跨執行的判斷（ADR-0029 失效條件 1）。
  - **與重放的區分**（v0.26）：重放執行函式不寫也不讀這兩張表；重放 (d) 的嘗試紀錄只在 D-3 `forecast_replay_execution_log`，這兩張表也不記重放。「記錄一步嘗試」只指這兩張表的列，與 D-9 第 7 點 V26-04 子點的「嘗試紀錄」不同指。
```

**E　修訂紀錄段（附加在檔尾 L5217 之後）**
- 先空一行，再放一行 `---`，再空一行，然後放入下列全文。
- 兩個〔 〕佔位要由 tech-writer 填入，填入的字不得含下方預期值清單中的任何鍵串。例如風控確認檔名寫成 `N64N66…`（不帶連字號），就不會被計入 `N-64`。
- E-3 引用的落字稿檔名是我建議 coordinator 轉存時用的名稱：`/home/user/AICompany/work/reviews/2026-10-24-N64N66缺日原因寫法乙落字稿-tech-architect.md`。如果實際轉存的名稱不同，E-3 要跟著改，但不影響任何計數。
```
**N-64、N-66 缺日原因批（後續追蹤清單 N-64、N-66；評估摘要、M-11、D-3、D-7 第 7 點、D-8 第 2 點、Consequences、FL-18、FL-76、待決事項；方向：逐項標示，見各項）**
- 來源與套用範圍：
  - tech-architect 2026-10-23 起草：`work/reviews/2026-10-23-N64N66缺日原因判定起草-tech-architect.md`；表數與待決事項依同日協調改採該檔第三節寫法乙，字面以 2026-10-24 寫法乙落字稿為準：`work/reviews/2026-10-24-N64N66缺日原因寫法乙落字稿-tech-architect.md`。
  - 風控逐字確認：〔風控確認檔路徑〕。風控改字之處以風控為準。
  - CEO：表數與停擺代價知悉（待決事項 CEO 第 20 項）；其餘否。
  - 與事先宣告〔版號〕的 `reason` 九值與多 run 判定同步同一個 commit，不適用相鄰 commit 寬限。
- 逐項（被取代的原文：判準同 v0.25 同步批段）：
  - A-1 D-8 第 2 點「有範圍快照時」一項的 N-64 句末：方向：補定義（收緊：列集合取聯集，列數不會少於只取最後一個 run 快照的讀法）。CEO：否。句末接字，無被取代原文。
  - A-2 D-8 第 2 點 N-64、N-66 子點：方向：補定義（兩面）：收緊面是原因分辨得出來、帳目矛盾時 fail-closed、`db_restored` 先於 `late_only`；第 2 項 `late_only` 先於 run 的原因判為不變（與 D-8 第 5 點、FL-67 (h) 一致）。CEO：知悉（停擺代價，第 20 項）。插入，無被取代原文。
  - A-3 D-3 `forecast_gaps` 新增欄位 `attempt_id`、`basis_json` 與寫入驗證：方向：補定義（收緊：新增持久化與寫入驗證）。CEO：否。插入，無被取代原文。
  - A-4 FL-18 句末：方向：補定義（照實並陳：縮窄原句的字面讀法）。CEO：否。句末接字，無被取代原文。
  - A-5 FL-76：方向：收緊（測試）。CEO：否。插入，無被取代原文。
  - B-1 D-8 第 2 點「該日沒有任何 run」一項：方向：補定義（收緊：原因分辨得出來；列數不變）。CEO：否。被取代的原文——
    > - 該日沒有任何 run：`scheduler_down`
  - B-2 D-8 第 2 點「輸入未就緒」一項句末：方向：補定義（不變：指明存放處）。CEO：否。句末接字，無被取代原文。
  - B-3 D-8 第 2 點 `reason` 列舉計數：方向：補定義（列舉加值 `record_start_failed`，與事先宣告同步）。CEO：否。被取代的原文——
    > `reason` 的封閉列舉因此共八值，與事先宣告 §6.3「缺日」第 1 點 v0.25 列舉相同：`scheduler_down`、`inputs_not_ready`、`timeout`、`job_error`、`late_only`、`db_restored`、`write_rejected`、`record_error`。
  - B-4 D-3 新表 `forecast_record_attempt`／`forecast_record_attempt_end`：方向：補定義（收緊：新增持久化與寫入驗證）。CEO：表數知悉（第 20 項）。插入，無被取代原文。
  - B-5 D-7 第 7 點 N-66 子點：方向：補定義（收緊）；E-3d 的次數與欄位不變。CEO：否。插入，無被取代原文。
  - C-1～C-3 表數三處（評估摘要、M-11、Consequences）：方向：不變（計數）。CEO：知悉（第 20 項）。被取代的原文——
    > - 表數多（23 張），寫入規則有一部分在 trigger 裡。
    > - 23 張表，加上 trigger 與部分唯一索引，遷移與測試成本高。
    > 新增 18 張表（第九、十批加
    改為：評估摘要與 Consequences 的「23 張」改為「25 張」；M-11 的「新增 18 張表」改為「新增 20 張表」；在 `forecast_replay_execution_log` 之後加「；N-66 加 `forecast_record_attempt`、`forecast_record_attempt_end`」。編輯註記：本段之前各批次條目引用的表數是當時的原文，不改。
  - C-4 待決事項 CEO 第 20 項：方向：不變（揭露）。插入，無被取代原文。
  - D-1 v0.25 同步批段「落檔後的閘門」一項：句末加〔已決（N-64）〕，原文不改，無被取代原文。
- 照實並陳：
  - N-64：之後的 run 可以改變一列的 `reason`，改變不了列數；被蓋過的原因留在 `basis_json`。帳目矛盾時缺日稽核整次不寫、`gap_judged_through` 停止前進、驗證快照停寫，直到查明（比照 N-46）。
  - N-64：列集合取聯集，失效條件 F-3 的缺日率若以列計，比只取最後一個 run 快照的讀法偏嚴〔推論；計數單位見後續追蹤清單 N-85〕。
  - N-66：開始列本身寫不進去時，該次執行仍記 `scheduler_down`，只能由 E-3d 與 log 察覺。
- 待決事項與同批規則：
  - 本批內部不拆開；A-2 與 B-1～B-5 不得單獨先落檔。
  - 落檔後的閘門：`audit.py` 的多 run `reason` 判定、`record_start_failed`、記錄一步的開始列與 end 列，依本批字面實作；dev-lead 查證（後續追蹤清單 N-86）回覆 tech-architect 之前不實作。
  - 不在本批：新登記 claim 的缺日義務從哪一日開始（後續追蹤清單 N-84；在已有 `forecast_run` 的觀察日登記新的前瞻 claim 之前必須定案）；失效條件 F-3 缺日率的計數單位（N-85）。
```

**C-5 成立時，E 要連帶修改**
- 「CEO：」一行改為：`  - CEO：A-2 第 2 項明確同意（待決事項 CEO 第 21 項）；表數與停擺代價知悉（第 20 項）；其餘否。`
- A-2 一項中，「第 2 項 `late_only` 先於 run 的原因判為不變（與 D-8 第 5 點、FL-67 (h) 一致）。CEO：知悉（停擺代價，第 20 項）。」改為：「第 2 項 `late_only` 先於 run 的原因屬放寬（風控認定）。CEO：知悉（停擺代價，第 20 項）；第 2 項明確同意（第 21 項）。」
- C-4 一項之後加一行：`  - C-5 待決事項 CEO 第 21 項：方向：不變（揭露）。插入，無被取代原文。`
- 這三處改動都不增減任何鍵串。

**事先宣告（給 quant 的部分；以下是 TA 的建議字面，依文首 L10 由 quant 具名提出並定稿，V 編號也由 quant 定）**
- **Q-1 句中改字**（必要；不改的話，ADR B-3 會和事先宣告矛盾）
  - old（L1802，1 處；`write_rejected, record_error}` 的 Grep 計數為 1）：`` `reason ∈ {scheduler_down, inputs_not_ready, timeout, job_error, late_only, db_restored, write_rejected, record_error}`。 ``
  - new：`` `reason ∈ {scheduler_down, inputs_not_ready, timeout, job_error, late_only, db_restored, write_rejected, record_error, record_start_failed}`。〔v0.27 取代（V27-xx；後續追蹤清單 N-66）：原寫「`reason ∈ {scheduler_down, inputs_not_ready, timeout, job_error, late_only, db_restored, write_rejected, record_error}`」。`record_start_failed` 是記錄一步在寫入 ADR-0027 `forecast_run` 之前失敗或中斷；它與 `inputs_not_ready` 只依 ADR-0027 `forecast_record_attempt_end` 的紀錄判定（D-8 第 2 點）〕 ``
  - 既有的〔v0.25 取代…〕註接在新註之後，原文不動。
- **Q-2 插入**：放在 L1802 之後、L1803 `- **不補造**` 之前，縮排 2 格。
  - `  - **同一觀察日有多個排程執行時**（v0.27，V27-xx；後續追蹤清單 N-64）：缺日列的集合、`reason` 的判定順序，以及被蓋過的原因如何保存，依 ADR-0027 D-8 第 2 點 N-64、N-66 子點與 D-3 `forecast_gaps` 的 `basis_json`；本文件不另定。`
- **Q-3 句末接字**：定位串是 `缺日、逾時、作廢三者合併揭露（R-8）。`（L1803，1 處），在其後接上：
  - `〔v0.27 註（V27-xx）：缺日另依 `reason` 分列列數；`basis_json` 中有 `reason_alone` 與該列 `reason` 不同的列，依（`reason`, `reason_alone`）分列列數。本點原文不改〕`

#### 二、落檔順序

1. **句中改字先套。** 理由有兩個：這幾處的原文之後會被 E 逐字引用，E 落檔後定位串會變成 2 處；而且套完不增減行數。依序為 C-1（L89）、C-3a、C-3b（L202）、B-1（L1196）、B-3（L1204）、C-2（L2397）。
2. **由檔尾往前做插入與句末接字。** 依序為 D-1（L5165）→ C-4（L3215 之後；C-5 如果成立，接在 C-4 之後）→ A-5（L2479 之後）→ A-4（L2467）→ A-1（L1205 句末）→ A-2（L1205 那一行之前）→ B-2（L1200）→ B-5（L1018 之後）→ A-3（L743 之後）→ B-4（L282 之後）。
3. **最後**在檔尾附加 E。
4. 事先宣告依 Q-1 → Q-3 → Q-2 的順序套用。和 ADR 同一個 commit。
5. 交叉檢查結果：沒有任何一段新字句含有其他步驟的完整定位串。
   - A-1 句末的 `` 寫 `scope_key='*'`。 `` 不構成 A-1 定位串。
   - FL-76 的 (k) 開頭是「(k) 帳目矛盾」，不會撞到 A-5 定位串「(k) 全部寫入」。
   - E-13 用的是「『該日沒有任何 run』」，不含「run：」。

#### 三、落檔後預期值

計算方式：以 `-o` 計 ADR-0027 全檔的出現次數。預期值 ＝ 落檔前實測值 ＋ 正文各段增量 ＋ D-1 ＋ E。不含 C-5；C-5 成立時，`N-64` 再加 2、`N-66` 再加 1。

| 字串 | 落檔前 | 正文增量（逐段） | D-1 | E | 預期 |
|---|---|---|---|---|---|
| `N-64` | 0 | B-1 1、B-2 1、B-3 1、A-1 2、A-2 3、A-3 4、A-4 2、A-5 5、C-4 2，小計 21 | 3 | 7 | **31** |
| `N-66` | 0 | C-3b 1、B-1 2、B-2 2、B-3 3、A-1 1、A-2 1、A-3 4、A-4 1、A-5 3、B-4 2、B-5 1、C-4 2，小計 23 | 2 | 6 | **31** |
| `forecast_record_attempt`（含 `_end` 的子字串） | 0 | C-3b 2、B-2 1、A-2 4、A-3 1、A-5 6、B-4 2、B-5 2、C-4 2，小計 20 | 0 | 4 | **24** |
| `forecast_record_attempt_end` | 0 | C-3b 1、B-2 1、A-2 2、A-5 1、B-4 1、B-5 1、C-4 1，小計 8 | 0 | 2 | **10** |
| `attempt_id` | 0 | A-2 2、A-3 6、A-5 6、B-4 3，小計 17 | 0 | 1 | **18** |
| `basis_json` | 0 | A-2 2、A-3 4、A-4 1、A-5 9，小計 16 | 0 | 2 | **18** |
| `reason_alone` | 0 | A-3 2、A-4 1、A-5 6，小計 9 | 0 | 0 | **9** |
| `record_start_failed` | 0 | B-3 1、A-2 2、A-3 1、A-5 5、B-5 1，小計 10 | 0 | 2 | **12** |
| `error_before_run` | 0 | A-2 3、A-5 2、B-4 3、B-5 1，小計 9 | 0 | 0 | **9** |
| `run_written` | 0 | A-2 1、A-5 2、B-4 5，小計 8 | 0 | 0 | **8** |
| `GapAuditRunInconsistencyError` | 0 | A-2 1、A-5 1 | 0 | 0 | **2** |
| `FL-76` | 0 | A-5 1 | 0 | 2 | **3** |
| `記錄一步嘗試` | 0 | B-1 1、A-1 1、A-2 5、A-3 2、A-5 2、B-4 2，小計 13 | 0 | 0 | **13** |
| `forecast_replay_execution_log` | 15 | A-2 1、B-4 1；C-3b 一出一進，淨 0 | 0 | 1 | **18** |
| `嘗試紀錄` | 16 | B-4 2 | 0 | 0 | **18** |
| `forecast_gaps` | 13 | A-2 2、A-5 4 | 0 | 1 | **20** |
| `N-84`／`N-85`／`N-86` | 0／0／0 | A-2 有 `N-84` 1 | 0 | 1／2／1 | **2／2／1** |
| `共九值` | 0 | B-3 1 | 0 | 0 | **1** |
| `共八值` | 1 | B-3 減 1 | 0 | 1 | **1**（只在 E 的引文中） |
| `該日沒有任何 run：` | 1 | B-1 減 1 | 0 | 1 | **1**（只在 E） |
| `該日沒有任何 run，也沒有該日的記錄一步嘗試` | 0 | B-1 1 | 0 | 0 | **1** |
| `表數多（23 張）`／`表數多（25 張）` | 1／0 | 減 1／加 1 | 0 | 1／0 | **1（只在 E）／1** |
| `- 23 張表，加上`／`- 25 張表，加上` | 1／0 | 減 1／加 1 | 0 | 1／0 | **1（只在 E）／1** |
| `新增 18 張表（`／`新增 20 張表（` | 1／0 | 減 1／加 1 | 0 | 1／0 | **1（只在 E）／1** |
| `20. （N-64、N-66，知悉）` | 0 | C-4 1 | 0 | 0 | **1** |

**落檔後應為 0 的串**
- `記錄嘗試`
- `forecast_replay_attempt`
- `；V26-04 加 `forecast_replay_execution_log`）並取欄位聯集`（C-3b 已套用的證據）
- 正文中（E 以外）的 `共八值`、`表數多（23 張）`

**落檔後仍各為 1 的定位串**
- L282、L743、L1018、L1200、L1205 的 A-1 全串、L2467、L2479、L3215、L5165 的長串。

**其他核對**
- `\bforecast_record\b`（字詞邊界）的次數不變，本批新字句沒有單獨的 `forecast_record`。若不加邊界，`forecast_record` 會多出 24 次，這不是錯誤。
- ADR-0029：本批 diff 為空。

**事先宣告**（假設 quant 照 Q-1～Q-3 的建議字面落檔；不含 quant 自己加的修訂紀錄列與狀態行）

| 字串 | 落檔前 | 預期 | 怎麼算 |
|---|---|---|---|
| `record_start_failed` | 0 | 2 | Q-1：列舉 1、註 1 |
| `forecast_record_attempt_end` | 0 | 1 | Q-1 |
| `N-66` | 0 | 2 | Q-1 1、Q-2 1 |
| `N-64` | 0 | 1 | Q-2 |
| `basis_json` | 0 | 2 | Q-2 1、Q-3 1 |
| `reason_alone` | 0 | 2 | Q-3 |
| `write_rejected, record_error}` | 1 | 1 | 移進〔取代〕註，仍是 1 |
| `write_rejected, record_error, record_start_failed}` | 0 | 1 | Q-1 |

#### 四、方向判定與 CEO 層級

| 項 | 方向 | CEO |
|---|---|---|
| A-1 | 補定義（收緊：列數不會變少；移出自選也消不掉列） | 否 |
| A-2 | 補定義（兩面）。收緊面：原因分辨得出來、fail-closed、`db_restored` 先於 `late_only`（可能讓 TG-c 計數變多）。第 2 項判為不變 | 知悉（停擺）；第 2 項如果被判為放寬，要**明確同意**（C-5） |
| A-3 | 補定義（收緊） | 否 |
| A-4 | 補定義。照實並陳：縮窄了 FL-18 的字面讀法；但原字面在單一 run 時本來就無法成立，而且資訊保留在 `basis_json`。請風控確認不是測試放寬 | 否 |
| A-5 | 收緊（測試） | 否 |
| B-1、B-3 | 補定義（收緊：列數不變，原因分得出來）。〔事實〕ADR 中沒有任何規則以 `scheduler_down` 的次數為觸發條件（Grep 只命中 L1196、L1204），所以拆值不會使任何告警或判定變少 | 否 |
| B-2 | 補定義（不變） | 否 |
| B-4 | 補定義（收緊） | 表數知悉 |
| B-5 | 補定義（收緊；E-3d 不變） | 否 |
| C-1～C-4、D-1、E | 不變（計數、揭露） | C-1～C-4 知悉 |
| Q-1／Q-2／Q-3 | 補定義（列舉加值）／補定義（引用）／收緊（揭露） | 否 |

**給 CEO 的白話句子（第 20 項，知悉）**
> 系統每天晚上自動記錄預測，同一天有時會重試好幾次。這次我們把兩件事講清楚：
> 第一，「那天哪幾檔沒記到」以所有嘗試合起來算，不會因為後來把某檔從清單拿掉，那天的缺漏就消失；「為什麼沒記到」以最後一次有處理到該檔的那次為準，前幾次的原因另外留底，不會被抹掉。
> 第二，以前程式如果在一開始準備階段就出錯，會被誤記成「排程根本沒跑」；現在會先寫一筆「已開始執行」的紀錄，分得出是沒跑，還是跑了但一開始就壞掉。為此資料庫多兩張表：預測帳由 18 張變 20 張，全部由 23 張變 25 張。
> 代價有兩個。一是帳本如果自己出現前後對不上（理論上不該發生），每天的缺漏檢查會整個停下來、統計也暫停更新，直到有人查明，我們寧可停下來也不要記錯。二是如果連「已開始執行」那一筆都寫不進資料庫（例如硬碟出問題），那天仍只能記成「排程沒跑」，要靠維運通知才會發現。

**給 CEO 的白話句子（第 21 項，只在風控判為放寬時才需要明確同意）**
> 同一天前面幾次嘗試失敗、後來補跑但已經過了截止時間才記到時，那天的原因記為「只有逾時補記」，不記前面失敗的原因。這種日子不算進畫面上的缺漏次數（日期清單仍完整列出），所以缺漏次數可能比另一種算法少。需要您明確同意。

#### 五、與 v0.26 的交互

- **V24-01、V25-02、V25-03（相位、涵蓋率、作廢率、W 的分母）：沒有影響。**
  - 〔事實〕這幾個定義的計入對象是 `forecast_record`、`forecast_outcome` 的列與 label。缺日不計入 n（ADR D-8 第 4 點；事先宣告 L1803），也不是紀錄列。
  - 本批只改缺日列的集合與 `reason`，不改紀錄列。
- **`forecast_gaps` 的 `reason` 值域**：由八值變九值；另加 `attempt_id`、`basis_json` 兩欄，都不屬於 `E_CHANGING_EVENTS`。
  - F-3 逾時率只讀 `late=1`，不變。
  - F-3 缺日率：列集合取聯集之後，若以列計，結果偏嚴。計數單位由 N-85 待定〔推論〕。
  - TG-c 不含 `late_only`：`record_start_failed` 照樣計入，和原本的 `scheduler_down` 一樣，所以計數不變。
- **V26-04 重放：流程沒有影響。**
  - 〔事實〕重放不產生缺日列（事先宣告 L1733：O 中不成立的日期不產生重放紀錄）。
  - 重放的嘗試只寫 `forecast_replay_execution_log`；該表「存放處的選擇」也寫明不寫 `forecast_run_end`，因為只有記錄一步可以寫入。
  - 本批新增兩道雙向隔離：B-4 末項加 FL-76 (p)，禁止重放執行函式讀寫新表；A-2 禁止以 `forecast_replay_execution_log` 推定缺日原因。
  - `forecast_replay_execution_log` 的 schema 測試要求「欄位集合恰為上列」，本批不動它。
- **表名**：保留 `forecast_record_attempt`，理由見本次結論第 2 點。
  - 它和既有表 `forecast_record` 共用前綴，只影響不加邊界的 grep 計數。先例是 `forecast_run`／`forecast_run_end`。
  - 我評估過的替代名稱是 `forecast_record_step_log`（A′ 單表，比照 v0.26），不採用，因為協調已定為兩張表。

#### 六、給 quant 的問題清單（可直接交辦）

- **Q-1**（必要，和 ADR 同一個 commit）：是否照上方建議，把 §6.3「缺日」第 1 點（L1802）的列舉由八值改為九值，並以〔取代〕註錄存原列舉？V 編號與版號（v0.27 或其他）請你定。
- **Q-2**：多 run 的判定（列集合、判定順序、「S 的 run」與「S 的記錄一步嘗試」的定義），要只引用 ADR-0027 D-8 第 2 點 N-64、N-66 子點（建議字面 Q-2），還是在事先宣告逐項登記？
- **Q-3**：是否新增兩項揭露：依 `reason` 分列的缺日列數；`reason_alone` 和 `reason` 不同的列，依（`reason`, `reason_alone`）分列？要放在 §6.3「缺日」第 2 點（建議 Q-3），還是 §4.2？
- **Q-4**：請確認 F-3 上限表（L1810）不必改，因為逾時率只讀 `late=1`。F-3 缺日率以列計還是以日計、是否排除 `late_only`，屬於 N-85（由 quant 提、風控審）。本批不處理，但聯集讀法在以列計時偏嚴，請一併評估。
- **Q-5**：請確認 L772「§6.3 缺日的既有原因值」與 L1733 重放的 `inputs_not_ready` 比照句不必改。
- **Q-6**：附錄 C 中 LG-27 不必改；我 Grep 過，沒有其他 LG 格以缺日 `reason` 為期望值。是否要新增一格對應 FL-76？建議至少涵蓋三種情形：(b)「移出自選也不減列」、(d)「`late_only` 優先」、(e)／(m)「`inputs_not_ready` 有存放處」。
- **Q-7**：依文首 L10 的規則變更流程，本批要以單項版（v0.27）具名提出並送風控，還是併入其他版？方向欄建議為：Q-1 補定義（列舉加值）、Q-2 補定義（引用）、Q-3 收緊（揭露）。A-2 第 2 項如果被風控判為放寬，事先宣告的方向欄也要同步標示。

#### 對實作的約束（逐條，qa-reviewer 可以檢查）

1. `reason` 依 A-2 的五項順序判定，只讀持久化的表（FL-76 (a)～(m)）。
2. 列集合取全部 S 的 run 的快照聯集；把範圍移出自選也不能消掉列（FL-76 (b)）。
3. 帳目矛盾時拋 `GapAuditRunInconsistencyError`，整次稽核不寫，不得改記其他值（FL-76 (k)）。
4. 開始列是記錄一步的第一個寫入；`run_written` 和 A-25 在同一個交易；前置段的 except 放在另一個函式（FL-76 (i)(n)(p)）。
5. `forecast_gaps` 的 `run_id`、`attempt_id`、`basis_json` 在交易內重算後必須一致（FL-76 (o)）。
6. 重放執行函式不讀也不寫 `forecast_record_attempt*`；`audit.py` 不讀 `forecast_replay_execution_log`（FL-76 (p)、A-2）。
7. 禁止事項：以 log、告警、job 事件或重放紀錄推定 `inputs_not_ready`、`record_start_failed`、`scheduler_down`；告警或編排函式讀新表或 `basis_json`；前置段和範圍迴圈共用同一個 `except Exception` 函式。

## 驗證

- 全程只用 Read、Grep、Glob，沒有寫檔、沒有 commit，沒有讀 `.env`，也沒有碰 `*.db`。
- **讀過的檔與段落**
  - ADR-0027（`/home/user/AICompany/docs/adr/0027-stock-desk-預測紀錄帳-儲存-PIT輸入-排程與定義登記.md`）：L200-203、L262-291、L690-779、L995-1024、L1071-1076、L1180-1214、L2440-2489、L3190-3229、L5110-5217。
  - 事先宣告（`/home/user/AICompany/work/research/2026-10-15-3日5日方向判斷-事先宣告草案.md`）：L1-14、L1798-1811，另 Grep 缺日相關各串與附錄 C 的 LG 列。
  - 原稿：`/home/user/AICompany/work/reviews/2026-10-23-N64N66缺日原因判定起草-tech-architect.md` 全文。
  - R-1 的出處：`/home/user/AICompany/work/reviews/2026-10-23-v0.26之ADR同步追加5a至5f-tech-architect.md` L11-28、L145-224。
  - 追蹤清單：`/home/user/AICompany/work/dispatch/2026-10-17-後續追蹤清單.md` 的 N-64、N-66、N-84、N-85、N-86 列。
  - ADR-0029：Grep「失效條件」與 `gap_audit`。
- **落檔前實測（Grep `-o`）**
  - 定位串各恰好 1 處：C-1、C-2、C-3a、C-3b、B-1、B-2、B-3（全串）、A-1（全串）、L282、L743、L1018、FL-18 全行、FL-74 (k) 開頭、CEO 第 19 項全行、L5165 的長串。
  - 為 0 的串：`N-64`、`N-66`、`N-84`～`N-86`、`FL-76`、`forecast_record_attempt`、`attempt_id`、`basis_json`、`reason_alone`、`record_start_failed`、`error_before_run`、`run_written`、`GapAuditRunInconsistencyError`、`記錄嘗試`、`記錄一步嘗試`、`_attempt`。
  - 既有的值：`forecast_replay_execution_log` 15（分布在 13 行）、`嘗試紀錄` 16、`forecast_gaps` 13、`共八值` 1。
  - 待決事項 CEO 段目前的最大編號是 19；FL 目前最大是 FL-75（L3087）。
- **預期值是逐段人工點數的。** 對原稿共有的字串，我和原稿第 336-354 行的預期值互相核對過：K3 20、K4 8、`attempt_id` 17、`basis_json` 16、`reason_alone` 9、`record_start_failed` 10、`run_written` 8、`error_before_run` 9、`N-64` 21、`N-66` 23，都一致。建議 coordinator 落檔後用 `grep -o … | wc -l` 機械複核。
- **未查證**
  - TG-b／TG-c 在畫面上有沒有依 `reason` 顯示文字。如果有，新值 `record_start_failed` 需要 creative-lead 起草文案、風控審查（D-8 L1193 的規則）。
  - 失效條件 F-3 缺日率的計數單位（N-85）。
  - dev-lead 的三點查證（N-86）。

## 下一步

1. **coordinator**
   - 把本份回報逐字轉存為 `/home/user/AICompany/work/reviews/2026-10-24-N64N66缺日原因寫法乙落字稿-tech-architect.md`（E-3 引用這個名稱）。
   - 把 C-1～C-4、B-1～B-5、A-1～A-5、D-1、E 送 risk-compliance-officer 逐字確認，連同 quant 的 Q-1～Q-3 定稿。要請風控裁定的點：
     - (i) 甲案；
     - (ii) 列集合取聯集；
     - (iii) 判定順序，以及 A-2 第 2 項是否屬放寬，這一點決定 C-5 要不要落檔；
     - (iv) fail-closed 停擺；
     - (v) A 案兩張表、新值命名，以及中文用語改為「記錄一步嘗試」；
     - (vi) 歸屬窗；
     - (vii) `basis_json`；
     - (viii) A-4 不屬於測試放寬。
2. **quant-researcher**：回覆 Q-1～Q-7，並依 L10 的流程具名提出事先宣告的同步版。
3. **CEO**：知悉第 20 項。第 21 項只在風控判為放寬時，才送決策包請 CEO 明確同意；同意之前本批不落檔。
4. **dev-lead**：回覆 N-86。回覆之前，`audit.py` 的多 run 判定與 `record_start_failed` 先不要實作。
5. **tech-writer**：風控確認後依第二節的順序落檔，和事先宣告同一個 commit；落檔後用第三節的預期值機械核對，再送 qa-reviewer（含 Codex 第二意見）。
